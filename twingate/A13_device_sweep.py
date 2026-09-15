"""
A13_device_sweep.py — Full Sionna RT sweep for any single device.
Usage: python A13_device_sweep.py <device>
  device: pc1 | pc2 | pc3 | pc4

Identical pipeline to A12/A12e but parameterised:
  - No MAX_TRAIN_ROWS cap — all train rows go through Sionna RT
  - Stratified 80/20 split from stratified_split_index.csv
  - Sentinel filter (sionna_power_raw <= -100 dBm)
  - Sionna std guard (towers with train std < 1.0 dBm use per-tower mean)
  - Per-tower OLS: RSRP = b_i + alpha_i * sionna_power_raw
  - Saves out/<device>_full_sionna.csv and out/<device>_results.json
"""

import sys, json, math, numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import linregress, spearmanr
import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import Transmitter, Receiver, PathSolver, PlanarArray, load_scene

if len(sys.argv) < 2 or sys.argv[1] not in ("pc1", "pc2", "pc3", "pc4"):
    print("Usage: python A13_device_sweep.py <pc1|pc2|pc3|pc4>")
    sys.exit(1)

DEVICE = sys.argv[1]
OPERATOR = 1 if DEVICE in ("pc1", "pc4") else 2

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

SCENE_ORIGINS = {1: (52.507005, 13.323428), 2: (52.506112, 13.321908)}
SCENE_XML     = {1: str(ROOT / "scene_operator1" / "scene.xml"),
                 2: str(ROOT / "scene_operator2" / "scene.xml")}

RSRP_COL = "PCell_RSRP_max"
FREQ_COL = "PCell_freq_MHz"
CELL_COL = "PCell_Cell_Identity"
LAT_COL  = "Latitude"
LON_COL  = "Longitude"

TX_HEIGHT_M    = 30.0
RX_HEIGHT_M    = 1.5
GPU_BATCH      = 40
MIN_ROWS       = 3
ALPHA_CLIP     = (0.0, 2.0)
SENTINEL       = -100.0
MIN_SIONNA_STD = 1.0


def latlon_to_xy(lat, lon, olat, olon):
    x = (lon - olon) * 111_320.0 * math.cos(math.radians(olat))
    y = (lat - olat) * 111_320.0
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
                   scene, solver, olat, olon):
    tx_x, tx_y = latlon_to_xy(tx_lat, tx_lon, olat, olon)
    scene.add(Transmitter(name="tx_a13", position=[tx_x, tx_y, TX_HEIGHT_M]))
    powers = []
    for start in range(0, len(rx_lats), GPU_BATCH):
        blats = rx_lats[start:start + GPU_BATCH]
        blons = rx_lons[start:start + GPU_BATCH]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = latlon_to_xy(float(la), float(lo), olat, olon)
            scene.add(Receiver(name=f"rx_a13_{i}", position=[xi, yi, RX_HEIGHT_M]))
        paths = solver(scene=scene, max_depth=5, diffraction=True)
        powers.extend(power_dbm(paths).tolist())
        for i in range(len(blats)):
            scene.remove(f"rx_a13_{i}")
    scene.remove("tx_a13")
    return np.array(powers)


def main():
    print("=" * 65)
    print(f"A13  —  {DEVICE} (Op{OPERATOR}) Full Sionna RT Sweep")
    print("=" * 65)

    df   = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv", low_memory=False)
    df["_row"] = df.index
    strat = pd.read_csv(OUT / "stratified_split_index.csv")
    gaps  = pd.read_csv(OUT / "gap_labels.csv")

    dev_rows = df[df["device"] == DEVICE].copy()
    dev_rows = dev_rows.merge(strat[["_row", "new_split"]], on="_row", how="inner")
    dev_rows = dev_rows.merge(gaps[["_row", "gap_type"]], on="_row", how="left")
    dev_rows["gap_type"] = dev_rows["gap_type"].fillna("Unflagged")

    clean = dev_rows[
        (dev_rows["gap_type"] == "Unflagged") &
        dev_rows[RSRP_COL].notna() &
        dev_rows[LAT_COL].notna() &
        dev_rows[LON_COL].notna()
    ].copy()

    train_raw = clean[clean["new_split"] == "train"]
    val_raw   = clean[clean["new_split"] == "val"]
    print(f"  {DEVICE} train={len(train_raw):,}  val={len(val_raw):,}")

    # WCL tower positions from training rows
    olat, olon = SCENE_ORIGINS[OPERATOR]
    wcl = (
        train_raw.groupby(CELL_COL)[[LAT_COL, LON_COL, RSRP_COL]]
        .apply(lambda g: pd.Series({
            "wcl_lat": np.average(g[LAT_COL], weights=10 ** (g[RSRP_COL] / 10)),
            "wcl_lon": np.average(g[LON_COL], weights=10 ** (g[RSRP_COL] / 10)),
            "n_train": len(g),
        }), include_groups=False)
        .reset_index()
    )
    print(f"  {len(wcl)} towers from training rows")

    print(f"\nLoading Sionna scene (Op{OPERATOR})...")
    scene  = load_scene(SCENE_XML[OPERATOR])
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    solver = PathSolver()
    print("  Scene loaded. Starting sweep...")

    ckpt_path = OUT / f"{DEVICE}_full_sionna.csv"
    # Resume: load already-processed towers from checkpoint
    done_cells = set()
    if ckpt_path.exists():
        existing = pd.read_csv(ckpt_path)
        done_cells = set(existing["cell_id"].unique())
        print(f"  Checkpoint found: {len(done_cells)} towers already done, resuming...")
    else:
        existing = pd.DataFrame()

    skipped = processed = 0

    for _, tower in wcl.iterrows():
        cell   = tower[CELL_COL]
        tw_lat = tower["wcl_lat"]
        tw_lon = tower["wcl_lon"]

        if cell in done_cells:
            print(f"  Tower {cell}: already done (checkpoint), skipping")
            processed += 1
            continue

        tr = train_raw[train_raw[CELL_COL] == cell]
        va = val_raw[val_raw[CELL_COL] == cell]

        if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
            skipped += 1
            print(f"  Tower {cell}: SKIP (tr={len(tr)} va={len(va)})")
            continue

        print(f"  Tower {cell}: tr={len(tr):4d} va={len(va):4d} ...", end="", flush=True)

        tr_pw = run_sionna_all(tr[LAT_COL].tolist(), tr[LON_COL].tolist(),
                               tw_lat, tw_lon, scene, solver, olat, olon)
        va_pw = run_sionna_all(va[LAT_COL].tolist(), va[LON_COL].tolist(),
                               tw_lat, tw_lon, scene, solver, olat, olon)

        print(f" done [{tr_pw.min():.1f},{tr_pw.max():.1f}]")

        def make_rows(subset, powers, spl):
            out = []
            for (_, row), pw in zip(subset.iterrows(), powers):
                dist = haversine_m(float(row[LAT_COL]), float(row[LON_COL]), tw_lat, tw_lon)
                out.append({
                    "_row": int(row["_row"]), "cell_id": cell, "new_split": spl,
                    "measured_rsrp": float(row[RSRP_COL]),
                    "sionna_power_raw": float(pw),
                    "dist_m": dist,
                    "freq_mhz": float(row[FREQ_COL]) if FREQ_COL in row and pd.notna(row.get(FREQ_COL)) else float("nan"),
                    "wcl_lat": tw_lat, "wcl_lon": tw_lon,
                })
            return out

        tower_rows = make_rows(tr, tr_pw, "train") + make_rows(va, va_pw, "val")
        tower_df   = pd.DataFrame(tower_rows)
        # Append to checkpoint file immediately after each tower
        write_header = not ckpt_path.exists()
        tower_df.to_csv(ckpt_path, mode="a", header=write_header, index=False)
        done_cells.add(cell)
        processed += 1

    total_done = len(done_cells)
    print(f"\nSweep done: {total_done} towers done, {skipped} skipped")
    raw_df = pd.read_csv(ckpt_path)
    print(f"Saved: out/{DEVICE}_full_sionna.csv  ({len(raw_df):,} rows)")

    # ── Evaluation ─────────────────────────────────────────────────────────────
    valid  = raw_df[raw_df["sionna_power_raw"] > SENTINEL].copy()
    tr_v   = valid[valid["new_split"] == "train"]
    va_v   = valid[valid["new_split"] == "val"]
    print(f"\nAfter sentinel filter: train={len(tr_v):,}  val={len(va_v):,}")

    tmean = tr_v.groupby("cell_id")["measured_rsrp"].mean()

    # Global offset
    goff  = (tr_v["measured_rsrp"] - tr_v["sionna_power_raw"]).mean()
    va_v  = va_v.copy()
    va_v["pred_global"] = va_v["sionna_power_raw"] + goff
    mae_g = (va_v["measured_rsrp"] - va_v["pred_global"]).abs().mean()

    # Per-tower mean
    va_v["pred_tm"] = va_v["cell_id"].map(tmean)
    mae_tm = (va_v["measured_rsrp"] - va_v["pred_tm"]).abs().dropna().mean()

    # Per-tower OLS
    coefs = {}
    fallback = []
    for cell, tr in tr_v.groupby("cell_id"):
        va_g = va_v[va_v["cell_id"] == cell]
        if len(tr) < MIN_ROWS or len(va_g) < MIN_ROWS:
            continue
        x, y = tr["sionna_power_raw"].values, tr["measured_rsrp"].values
        if x.std() < MIN_SIONNA_STD:
            fallback.append(cell)
            continue
        sl, ic, _, _, _ = linregress(x, y)
        coefs[cell] = {"b": float(ic), "alpha": float(np.clip(sl, *ALPHA_CLIP))}

    out_rows = []
    for cell, va_g in va_v.groupby("cell_id"):
        y_true = va_g["measured_rsrp"].values
        if cell in coefs:
            b, alpha = coefs[cell]["b"], coefs[cell]["alpha"]
            pred   = b + alpha * va_g["sionna_power_raw"].values
            method = "ols"
        elif cell in fallback and cell in tmean:
            pred   = np.full(len(va_g), tmean[cell])
            method = "mean_fallback"
        else:
            continue
        resid = y_true - pred
        for rid, pr, res in zip(va_g["_row"].values, pred, resid):
            out_rows.append({"_row": int(rid), "cell_id": cell,
                             "pred": float(pr), "residual": float(res), "method": method})

    ols_df  = pd.DataFrame(out_rows)
    mae_ols  = ols_df["residual"].abs().mean()
    rmse_ols = float(np.sqrt((ols_df["residual"] ** 2).mean()))

    rhos = []
    for cell, va_g in va_v[va_v["cell_id"].isin(coefs)].groupby("cell_id"):
        if len(va_g) < 5:
            continue
        rho, _ = spearmanr(va_g["sionna_power_raw"], va_g["measured_rsrp"])
        if not np.isnan(rho):
            rhos.append(rho)

    alphas = [v["alpha"] for v in coefs.values()]

    print(f"\n{'='*65}")
    print(f"FINAL SUMMARY  —  {DEVICE}  |  {ols_df['cell_id'].nunique()} towers  |  {len(ols_df):,} val rows")
    print(f"{'='*65}")
    print(f"  {'Method':<44} {'Val MAE (dB)':>10}  {'RMSE':>8}")
    print(f"  {'-'*62}")
    print(f"  {'Sionna global offset':<44} {mae_g:>10.3f}  {'—':>8}")
    print(f"  {'Per-tower mean (no Sionna)':<44} {mae_tm:>10.3f}  {'—':>8}")
    print(f"  {'Per-tower OLS + Sionna RT  [GATE-2]':<44} {mae_ols:>10.3f}  {rmse_ols:>8.3f}")
    print(f"\n  Spearman rho (OLS towers): median={np.median(rhos):.3f}  "
          f"positive={sum(r>0 for r in rhos)}/{len(rhos)}")
    print(f"  alpha: mean={np.mean(alphas):.3f}  OLS towers={len(coefs)}  fallback={len(fallback)}")

    results = {
        "device": DEVICE, "operator": OPERATOR, "split": "stratified_80_20",
        "sentinel_dBm": SENTINEL, "min_sionna_std_dBm": MIN_SIONNA_STD,
        "n_train": int(len(tr_v)), "n_val": int(len(va_v)),
        "n_towers_ols": len(coefs), "n_towers_fallback": len(fallback),
        "mae_global_offset": float(mae_g),
        "mae_per_tower_mean": float(mae_tm),
        "mae_per_tower_ols": float(mae_ols),
        "rmse_per_tower_ols": float(rmse_ols),
        "spearman_rho_median": float(np.median(rhos)) if rhos else None,
        "alpha_mean": float(np.mean(alphas)) if alphas else None,
        "alpha_std": float(np.std(alphas)) if alphas else None,
    }
    with open(OUT / f"{DEVICE}_results.json", "w") as f:
        json.dump(results, f, indent=2)
    ols_df.to_csv(OUT / f"{DEVICE}_ols_predictions.csv", index=False)
    print(f"\nSaved: out/{DEVICE}_results.json  out/{DEVICE}_ols_predictions.csv")


if __name__ == "__main__":
    main()
