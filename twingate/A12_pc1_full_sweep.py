"""
A12_pc1_full_sweep.py — Full Sionna RT sweep for pc1, stratified split

Differences from A03:
  - pc1 ONLY (Op1 / Deutsche Telekom scene)
  - Uses stratified_split_index.csv (80/20 by device+cell_id) not temporal split
  - NO MAX_TRAIN_ROWS cap — all train rows fed through Sionna RT
  - NO EVAL_BATCH row cap — GPU batch size only (not a data limit)
  - After Sionna: fits per-tower OLS  RSRP = b_i + alpha_i * sionna_power_raw
  - Reports: global-offset baseline, per-tower mean baseline, per-tower OLS MAE

ML + Sionna RT pipeline:
  Step 1 — Sionna RT  : physics ray-trace  → sionna_power_raw per (tower, rx_position)
  Step 2 — Per-tower OLS : learned calibration  → b_i + alpha_i * sionna_power_raw
  Sionna is in the loop as the spatial feature generator.
"""

import json
import math
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as scipy_stats

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import Transmitter, Receiver, PathSolver, PlanarArray, load_scene

ROOT     = Path(__file__).parent.parent
DATAFILE = ROOT / "cellular_dataframe_cleaned.csv"
OUT      = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

STRAT_IDX  = OUT / "stratified_split_index.csv"
GAP_LABELS = OUT / "gap_labels.csv"

RSRP_COL   = "PCell_RSRP_max"
FREQ_COL   = "PCell_freq_MHz"
CELL_COL   = "PCell_Cell_Identity"
LAT_COL    = "Latitude"
LON_COL    = "Longitude"
DEVICE_COL = "device"

TX_HEIGHT_M = 30.0
RX_HEIGHT_M = 1.5
GPU_BATCH   = 40       # PathSolver batch size — GPU memory only, NOT a row cap
MIN_ROWS    = 3        # skip tower if fewer than this in either split
ALPHA_CLIP  = (0.0, 2.0)  # slope clip for per-tower OLS

OPERATOR    = 1
DEVICE      = "pc1"
SCENE_ORIGIN = (52.507005, 13.323428)
SCENE_XML    = str(ROOT / "scene_operator1" / "scene.xml")


def latlon_to_xy(lat, lon, orig_lat, orig_lon):
    x = (lon - orig_lon) * 111_320.0 * math.cos(math.radians(orig_lat))
    y = (lat - orig_lat) * 111_320.0
    return float(x), float(y)


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def power_dbm(paths):
    a_r = np.array(dr.detach(paths.a[0]))
    a_i = np.array(dr.detach(paths.a[1]))
    plin = (a_r ** 2 + a_i ** 2).sum(axis=-1).squeeze(axis=(1, 2, 3))
    return 10.0 * np.log10(np.maximum(plin, 1e-30)) + 30.0


def run_sionna_all(rx_lats, rx_lons, tx_lat, tx_lon,
                   scene, solver, orig_lat, orig_lon):
    """Run Sionna RT for ALL rx positions — no cap, GPU batches only."""
    tx_x, tx_y = latlon_to_xy(tx_lat, tx_lon, orig_lat, orig_lon)
    scene.add(Transmitter(name="tx_a12", position=[tx_x, tx_y, TX_HEIGHT_M]))
    powers = []
    n = len(rx_lats)
    for start in range(0, n, GPU_BATCH):
        blats = rx_lats[start:start + GPU_BATCH]
        blons = rx_lons[start:start + GPU_BATCH]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = latlon_to_xy(float(la), float(lo), orig_lat, orig_lon)
            scene.add(Receiver(name=f"rx_a12_{i}", position=[xi, yi, RX_HEIGHT_M]))
        paths = solver(scene=scene, max_depth=5, diffraction=True)
        powers.extend(power_dbm(paths).tolist())
        for i in range(len(blats)):
            scene.remove(f"rx_a12_{i}")
    scene.remove("tx_a12")
    return np.array(powers)


def main():
    print("=" * 65)
    print("A12  —  pc1 Full Sionna RT Sweep (stratified split)")
    print("=" * 65)

    # ── Load data ──────────────────────────────────────────────────────────────
    print("\nLoading raw dataset...")
    df = pd.read_csv(DATAFILE, low_memory=False)
    df["_row"] = df.index

    strat  = pd.read_csv(STRAT_IDX)   # _row, device, cell_id, operator, new_split
    gaps   = pd.read_csv(GAP_LABELS)  # _row, gap_type, operator

    # Filter to pc1 only, merge split and gap labels
    pc1_rows = df[df[DEVICE_COL] == DEVICE].copy()
    pc1_rows = pc1_rows.merge(strat[["_row", "new_split"]], on="_row", how="inner")
    pc1_rows = pc1_rows.merge(gaps[["_row", "gap_type"]], on="_row", how="left")
    pc1_rows["gap_type"] = pc1_rows["gap_type"].fillna("Unflagged")

    # Unflagged only, valid RSRP and GPS
    clean = pc1_rows[
        (pc1_rows["gap_type"] == "Unflagged") &
        pc1_rows[RSRP_COL].notna() &
        pc1_rows[LAT_COL].notna() &
        pc1_rows[LON_COL].notna()
    ].copy()

    df_train = clean[clean["new_split"] == "train"]
    df_val   = clean[clean["new_split"] == "val"]

    print(f"  pc1 train rows (Unflagged): {len(df_train):,}")
    print(f"  pc1 val rows   (Unflagged): {len(df_val):,}")

    # ── WCL tower positions from training rows only ────────────────────────────
    print("\nComputing WCL tower positions from training rows...")
    wcl = (
        df_train.groupby(CELL_COL)[[LAT_COL, LON_COL, RSRP_COL]]
        .apply(lambda g: pd.Series({
            "wcl_lat": np.average(g[LAT_COL], weights=10 ** (g[RSRP_COL] / 10)),
            "wcl_lon": np.average(g[LON_COL], weights=10 ** (g[RSRP_COL] / 10)),
            "n_train": len(g),
        }), include_groups=False)
        .reset_index()
    )
    print(f"  {len(wcl)} towers with training rows")

    # ── Load Sionna scene ──────────────────────────────────────────────────────
    print("\nLoading Sionna RT scene (Op1)...")
    orig_lat, orig_lon = SCENE_ORIGIN
    scene  = load_scene(SCENE_XML)
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    solver = PathSolver()
    print("  Scene loaded. Starting full sweep...")

    # ── Main tower loop ────────────────────────────────────────────────────────
    all_rows = []
    skipped  = 0

    for idx, tower in wcl.iterrows():
        cell     = tower[CELL_COL]
        tw_lat   = tower["wcl_lat"]
        tw_lon   = tower["wcl_lon"]

        tr = df_train[df_train[CELL_COL] == cell]
        va = df_val[df_val[CELL_COL] == cell]

        if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
            skipped += 1
            print(f"  Tower {cell}: SKIP (tr={len(tr)} va={len(va)} < {MIN_ROWS})")
            continue

        print(f"  Tower {cell}: tr={len(tr):4d} va={len(va):4d} — running Sionna...",
              end="", flush=True)

        tr_powers = run_sionna_all(
            tr[LAT_COL].tolist(), tr[LON_COL].tolist(),
            tw_lat, tw_lon, scene, solver, orig_lat, orig_lon)

        va_powers = run_sionna_all(
            va[LAT_COL].tolist(), va[LON_COL].tolist(),
            tw_lat, tw_lon, scene, solver, orig_lat, orig_lon)

        print(f" done  power_range=[{tr_powers.min():.1f},{tr_powers.max():.1f}] dBm")

        def make_rows(subset, powers, spl):
            rows = []
            for (_, row), pw in zip(subset.iterrows(), powers):
                dist = haversine_m(float(row[LAT_COL]), float(row[LON_COL]),
                                   tw_lat, tw_lon)
                rows.append({
                    "_row":             int(row["_row"]),
                    "cell_id":          cell,
                    "new_split":        spl,
                    "measured_rsrp":    float(row[RSRP_COL]),
                    "sionna_power_raw": float(pw),
                    "dist_m":           dist,
                    "freq_mhz":         float(row[FREQ_COL]) if FREQ_COL in row and pd.notna(row.get(FREQ_COL)) else np.nan,
                    "area":             row.get("area", np.nan),
                    "wcl_lat":          tw_lat,
                    "wcl_lon":          tw_lon,
                })
            return rows

        all_rows.extend(make_rows(tr, tr_powers, "train"))
        all_rows.extend(make_rows(va, va_powers, "val"))

    print(f"\nSweep complete. Towers processed: {len(wcl) - skipped}  Skipped: {skipped}")

    result_df = pd.DataFrame(all_rows)
    result_df.to_csv(OUT / "pc1_full_sionna.csv", index=False)
    print(f"Saved: out/pc1_full_sionna.csv  ({len(result_df):,} rows)")

    # ── Evaluation ────────────────────────────────────────────────────────────
    train_df = result_df[result_df["new_split"] == "train"].copy()
    val_df   = result_df[result_df["new_split"] == "val"].copy()

    print(f"\n{'='*65}")
    print(f"EVALUATION  —  pc1  ({len(train_df):,} train / {len(val_df):,} val rows)")
    print(f"{'='*65}")

    # ── Baseline 1: Global offset (A03-style) ──────────────────────────────────
    global_offset = (train_df["measured_rsrp"] - train_df["sionna_power_raw"]).mean()
    val_df = val_df.copy()
    val_df["pred_global"] = val_df["sionna_power_raw"] + global_offset
    mae_global = (val_df["measured_rsrp"] - val_df["pred_global"]).abs().mean()
    print(f"\n[Baseline 1] Global offset = {global_offset:.3f} dB")
    print(f"             Val MAE = {mae_global:.3f} dB")

    # ── Baseline 2: Per-tower mean (no Sionna) ────────────────────────────────
    tower_mean = train_df.groupby("cell_id")["measured_rsrp"].mean()
    val_df["pred_tower_mean"] = val_df["cell_id"].map(tower_mean)
    shared_val = val_df[val_df["pred_tower_mean"].notna()]
    mae_tower_mean = (shared_val["measured_rsrp"] - shared_val["pred_tower_mean"]).abs().mean()
    print(f"\n[Baseline 2] Per-tower mean (no Sionna)")
    print(f"             Val MAE = {mae_tower_mean:.3f} dB  (n_val={len(shared_val):,})")

    # ── Main: Per-tower OLS with Sionna  RSRP = b_i + alpha_i * sionna_power ──
    tower_coefs = {}
    for cell, tr_grp in train_df.groupby("cell_id"):
        va_grp = val_df[val_df["cell_id"] == cell]
        if len(tr_grp) < MIN_ROWS or len(va_grp) < MIN_ROWS:
            continue
        x = tr_grp["sionna_power_raw"].values
        y = tr_grp["measured_rsrp"].values
        if x.std() < 1e-6:
            alpha = 0.0
            b = float(y.mean())
        else:
            slope, intercept, _, _, _ = scipy_stats.linregress(x, y)
            alpha = float(np.clip(slope, *ALPHA_CLIP))
            b     = float(intercept)
        tower_coefs[cell] = {"b": b, "alpha": alpha}

    preds_ols = []
    for cell, va_grp in val_df.groupby("cell_id"):
        if cell not in tower_coefs:
            continue
        b, alpha = tower_coefs[cell]["b"], tower_coefs[cell]["alpha"]
        pred = b + alpha * va_grp["sionna_power_raw"].values
        residuals = va_grp["measured_rsrp"].values - pred
        for r, pr, res in zip(va_grp.itertuples(), pred, residuals):
            preds_ols.append({
                "_row":         r._row,
                "cell_id":      cell,
                "measured_rsrp": r.measured_rsrp,
                "sionna_power_raw": r.sionna_power_raw,
                "pred_ols":     float(pr),
                "residual":     float(res),
                "alpha":        alpha,
                "b":            b,
            })

    ols_df = pd.DataFrame(preds_ols)
    mae_ols  = ols_df["residual"].abs().mean()
    rmse_ols = np.sqrt((ols_df["residual"] ** 2).mean())
    n_towers_ols = ols_df["cell_id"].nunique()

    print(f"\n[Main]  Per-tower OLS  (RSRP = b_i + alpha_i * sionna_power_raw)")
    print(f"        Towers with OLS fit: {n_towers_ols}")
    print(f"        Val MAE  = {mae_ols:.3f} dB")
    print(f"        Val RMSE = {rmse_ols:.3f} dB  (n_val={len(ols_df):,})")

    # Per-tower OLS coefficient summary
    alphas = [v["alpha"] for v in tower_coefs.values()]
    print(f"\n  alpha (slope) stats:")
    print(f"    mean={np.mean(alphas):.3f}  std={np.std(alphas):.3f}"
          f"  min={np.min(alphas):.3f}  max={np.max(alphas):.3f}")
    print(f"    clipped at 0 : {sum(a == 0.0 for a in alphas)} towers")
    print(f"    clipped at 2 : {sum(a == 2.0 for a in alphas)} towers")

    # Spearman correlation check: does Sionna rank-order RSRP within towers?
    rhos = []
    for cell, va_grp in val_df.groupby("cell_id"):
        if len(va_grp) < 5:
            continue
        rho, _ = scipy_stats.spearmanr(
            va_grp["sionna_power_raw"], va_grp["measured_rsrp"])
        if not np.isnan(rho):
            rhos.append(rho)
    print(f"\n  Per-tower Spearman rho on val (Sionna vs measured RSRP):")
    print(f"    n_towers={len(rhos)}  median={np.median(rhos):.3f}"
          f"  mean={np.mean(rhos):.3f}  std={np.std(rhos):.3f}")
    print(f"    positive rho: {sum(r > 0 for r in rhos)}/{len(rhos)} towers")

    # ── Summary table ─────────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print(f"SUMMARY  —  pc1, stratified 80/20 split, {n_towers_ols} towers")
    print(f"{'='*65}")
    print(f"  {'Method':<40} {'Val MAE (dB)':>12}")
    print(f"  {'-'*52}")
    print(f"  {'Sionna global offset (baseline)':<40} {mae_global:>12.3f}")
    print(f"  {'Per-tower mean (no Sionna)':<40} {mae_tower_mean:>12.3f}")
    print(f"  {'Per-tower OLS + Sionna RT [GATE-2]':<40} {mae_ols:>12.3f}")

    # ── Save results ──────────────────────────────────────────────────────────
    ols_df.to_csv(OUT / "pc1_ols_val_predictions.csv", index=False)

    results = {
        "device": DEVICE,
        "operator": OPERATOR,
        "split": "stratified_80_20",
        "n_train_rows": int(len(train_df)),
        "n_val_rows":   int(len(val_df)),
        "n_towers":     int(n_towers_ols),
        "global_offset_db":       float(global_offset),
        "mae_global_offset":      float(mae_global),
        "mae_per_tower_mean":     float(mae_tower_mean),
        "mae_per_tower_ols":      float(mae_ols),
        "rmse_per_tower_ols":     float(rmse_ols),
        "spearman_rho_median":    float(np.median(rhos)) if rhos else None,
        "spearman_rho_mean":      float(np.mean(rhos))   if rhos else None,
        "alpha_mean":             float(np.mean(alphas)),
        "alpha_std":              float(np.std(alphas)),
    }
    with open(OUT / "pc1_full_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved: out/pc1_full_results.json")
    print(f"Saved: out/pc1_ols_val_predictions.csv")
    print("\nDone.")


if __name__ == "__main__":
    main()
