"""
A17_multipath_richness.py — M4: Multipath Richness + LOS/NLOS Accuracy

Reuses A16's already-refined TX positions and diffuse-scattering scene
(S=0.4, Lambertian). No re-optimization: for each tower, refits OLS
calibration at the refined position (same train pass A16 already does),
then extracts per-path richness metrics for every held-out day-3 (val) row.

Metrics extracted per val row:
  tau_rms_ns      — power-weighted RMS delay spread (ns)
  phi_spread_deg  — power-weighted circular RMS azimuth spread (deg)
  n_valid_paths   — count of valid paths
  los_flag        — 1 if any valid path has an all-NONE interaction
                     sequence (direct line), else 0

Validation on held-out day 3:
  M4a — LOS/NLOS accuracy: measured RSRP mean/std, LOS vs NLOS (Welch t-test)
  M4b — richness vs residual: correlate tau_rms / n_valid_paths against
        |measured - calibrated Sionna prediction|

Usage: python A17_multipath_richness.py [--device pc1]
Requires: out/{device}_refinement_results_scatter_s0p40.csv (from A16)
"""

import sys
import json
import math
import datetime
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.stats import linregress, ttest_ind, pearsonr, spearmanr

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import Transmitter, Receiver, PathSolver, PlanarArray, load_scene
from sionna.rt.radio_materials.scattering_pattern import LambertianPattern
from sionna.rt.constants import InteractionType

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

_dev_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                 if a == "--device" and i+1 < len(sys.argv)), "pc1")
DEVICE = _dev_arg

_OP2_DEVICES = {"pc2", "pc3"}
OPERATOR     = 2 if DEVICE in _OP2_DEVICES else 1
SCENE_ORIGIN = (52.506112, 13.321908) if OPERATOR == 2 else (52.507005, 13.323428)
SCENE_XML    = str(ROOT / f"scene_operator{OPERATOR}" / "scene.xml")
SCATTER_S    = 0.4

REFINED_CSV = OUT / f"{DEVICE}_refinement_results_scatter_s0p40.csv"
OUT_CSV     = OUT / f"{DEVICE}_richness_val.csv"
OUT_SUMMARY = OUT / f"{DEVICE}_richness_summary.json"

RSRP_COL = "PCell_RSRP_max"
CELL_COL = "PCell_Cell_Identity"
LAT_COL  = "Latitude"
LON_COL  = "Longitude"

TX_HEIGHT_M    = 30.0
RX_HEIGHT_M    = 1.5
GPU_BATCH      = 40
MIN_ROWS       = 5
ALPHA_CLIP     = (0.0, 2.0)
SENTINEL       = -100.0
MIN_SIONNA_STD = 1.0


def latlon_to_xy(lat, lon, olat, olon):
    x = (lon - olon) * 111_320.0 * math.cos(math.radians(olat))
    y = (lat - olat) * 111_320.0
    return float(x), float(y)


def run_batch(rx_lats, rx_lons, tx_lat, tx_lon, scene, solver, olat, olon, tag, need_rich):
    """Runs one batched Sionna call. Always returns power_dbm (num_rx,).
    If need_rich, also returns a dict of per-row richness arrays."""
    tx_x, tx_y = latlon_to_xy(tx_lat, tx_lon, olat, olon)
    name = f"tx_{tag}"
    scene.add(Transmitter(name=name, position=[tx_x, tx_y, TX_HEIGHT_M]))
    n = len(rx_lats)
    for i, (la, lo) in enumerate(zip(rx_lats, rx_lons)):
        xi, yi = latlon_to_xy(float(la), float(lo), olat, olon)
        scene.add(Receiver(name=f"rx_{tag}_{i}", position=[xi, yi, RX_HEIGHT_M]))

    paths = solver(scene=scene, max_depth=5, diffraction=True)

    a_r = np.array(dr.detach(paths.a[0]))
    a_i = np.array(dr.detach(paths.a[1]))
    p_per_path = np.squeeze(a_r ** 2 + a_i ** 2, axis=(1, 2, 3))   # (num_rx, num_paths)
    p_total = p_per_path.sum(axis=-1)
    power = 10.0 * np.log10(np.maximum(p_total, 1e-30)) + 30.0

    rich = None
    if need_rich:
        tau   = np.squeeze(np.array(dr.detach(paths.tau)),   axis=1)   # (num_rx, num_paths)
        phi   = np.squeeze(np.array(dr.detach(paths.phi_r)), axis=1)   # (num_rx, num_paths)
        valid = np.squeeze(np.array(dr.detach(paths.valid)), axis=1)   # (num_rx, num_paths)
        inter = np.squeeze(np.array(dr.detach(paths.interactions)), axis=2)  # (depth, num_rx, num_paths)

        wsum = p_per_path.sum(axis=-1)
        wsum_safe = np.where(wsum <= 0, 1.0, wsum)

        tau_mean = (p_per_path * tau).sum(axis=-1) / wsum_safe
        tau_rms_ns = np.sqrt(np.maximum(
            (p_per_path * (tau - tau_mean[:, None]) ** 2).sum(axis=-1) / wsum_safe, 0.0
        )) * 1e9

        cos_bar = (p_per_path * np.cos(phi)).sum(axis=-1) / wsum_safe
        sin_bar = (p_per_path * np.sin(phi)).sum(axis=-1) / wsum_safe
        R = np.clip(np.sqrt(cos_bar ** 2 + sin_bar ** 2), 1e-9, 1.0)
        phi_spread_deg = np.degrees(np.sqrt(np.maximum(-2.0 * np.log(R), 0.0)))

        n_valid = valid.sum(axis=-1)

        is_direct = np.all(inter == InteractionType.NONE, axis=0)   # (num_rx, num_paths)
        los_flag = np.any(is_direct & valid, axis=-1).astype(int)

        rich = {
            "tau_rms_ns": tau_rms_ns,
            "phi_spread_deg": phi_spread_deg,
            "n_valid_paths": n_valid,
            "los_flag": los_flag,
        }

    for i in range(n):
        scene.remove(f"rx_{tag}_{i}")
    scene.remove(name)

    return power, rich


def run_full(rx_lats, rx_lons, tx_lat, tx_lon, scene, solver, olat, olon, tag, need_rich=False):
    """Runs run_batch over all rows in GPU_BATCH chunks, concatenating results."""
    powers = []
    rich_acc = {"tau_rms_ns": [], "phi_spread_deg": [], "n_valid_paths": [], "los_flag": []} if need_rich else None
    for start in range(0, len(rx_lats), GPU_BATCH):
        blats = rx_lats[start:start + GPU_BATCH]
        blons = rx_lons[start:start + GPU_BATCH]
        p, r = run_batch(blats, blons, tx_lat, tx_lon, scene, solver, olat, olon, tag, need_rich)
        powers.append(p)
        if need_rich:
            for k in rich_acc:
                rich_acc[k].append(r[k])
    powers = np.concatenate(powers)
    if need_rich:
        rich_acc = {k: np.concatenate(v) for k, v in rich_acc.items()}
    return powers, rich_acc


def main():
    print("=" * 65)
    print(f"A17  —  Multipath Richness + LOS/NLOS Accuracy (M4)  ({DEVICE})")
    print("=" * 65)

    if not REFINED_CSV.exists():
        print(f"ERROR: {REFINED_CSV} not found. Run A16 for {DEVICE} first.")
        sys.exit(1)
    refined = pd.read_csv(REFINED_CSV)
    print(f"  Loaded {len(refined)} refined tower positions from A16 ({REFINED_CSV.name})")

    df = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv", low_memory=False)
    df["_row"] = df.index
    gaps = pd.read_csv(OUT / "gap_labels.csv")

    df["_date"] = pd.to_datetime(df["ts_gps"], errors="coerce").dt.date
    VAL_DATE = datetime.date(2021, 6, 24)
    df["new_split"] = df["_date"].apply(lambda d: "val" if d == VAL_DATE else "train")

    dev_df = df[df["device"] == DEVICE].copy()
    dev_df = dev_df.merge(gaps[["_row", "gap_type"]], on="_row", how="left")
    dev_df["gap_type"] = dev_df["gap_type"].fillna("Unflagged")

    clean = dev_df[
        (dev_df["gap_type"] == "Unflagged") &
        dev_df[RSRP_COL].notna() &
        dev_df[LAT_COL].notna() &
        dev_df[LON_COL].notna() &
        dev_df["_date"].notna()
    ].copy()

    train_all = clean[clean["new_split"] == "train"]
    val_all   = clean[clean["new_split"] == "val"]
    print(f"  {DEVICE} train={len(train_all):,}  val={len(val_all):,}\n")

    print(f"Loading Sionna scene (Op{OPERATOR}) with diffuse scattering S={SCATTER_S:.2f}...")
    scene  = load_scene(SCENE_XML)
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    mat = scene.radio_materials["itu_concrete"]
    mat.scattering_coefficient = SCATTER_S
    mat.scattering_pattern     = LambertianPattern()
    solver = PathSolver()
    print("  Scene loaded.\n")

    olat, olon = SCENE_ORIGIN

    ckpt_path = OUT_CSV
    if ckpt_path.exists():
        done_df = pd.read_csv(ckpt_path)
        done_cells = set(done_df["cell_id"].unique())
        print(f"  Checkpoint: {len(done_cells)} towers already done, resuming...")
    else:
        done_cells = set()

    for _, row in refined.iterrows():
        cell = row["cell_id"]
        if cell in done_cells:
            print(f"  Tower {int(cell)}: already done (checkpoint)")
            continue

        ref_lat, ref_lon = row["refined_lat"], row["refined_lon"]
        tr = train_all[train_all[CELL_COL] == cell]
        va = val_all[val_all[CELL_COL] == cell]

        if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
            print(f"  Tower {int(cell)}: SKIP (tr={len(tr)} va={len(va)})")
            continue

        print(f"  Tower {int(cell)}: tr={len(tr):4d} va={len(va):4d}", end="", flush=True)

        try:
            tr_powers, _ = run_full(tr[LAT_COL].tolist(), tr[LON_COL].tolist(),
                                     ref_lat, ref_lon, scene, solver, olat, olon,
                                     tag="a17tr", need_rich=False)
            tr_rsrp = tr[RSRP_COL].values
            valid_mask = tr_powers > SENTINEL
            x, y = tr_powers[valid_mask], tr_rsrp[valid_mask]

            if len(x) < MIN_ROWS or x.std() < MIN_SIONNA_STD:
                print("  SKIP (flat/insufficient Sionna signal for OLS)")
                continue

            sl, ic, _, _, _ = linregress(x, y)
            alpha = float(np.clip(sl, *ALPHA_CLIP))
            intercept = float(ic)

            va_powers, va_rich = run_full(va[LAT_COL].tolist(), va[LON_COL].tolist(),
                                           ref_lat, ref_lon, scene, solver, olat, olon,
                                           tag="a17va", need_rich=True)
            va_rsrp = va[RSRP_COL].values
            va_pred = intercept + alpha * va_powers
            residual_db = np.abs(va_rsrp - va_pred)

            va_valid = va_powers > SENTINEL
            n_out = int(va_valid.sum())
            print(f"  → alpha={alpha:.3f}  n_val_used={n_out}", flush=True)

            rec_df = pd.DataFrame({
                "cell_id":         cell,
                "row_id":          va["_row"].values[va_valid],
                "tau_rms_ns":      va_rich["tau_rms_ns"][va_valid],
                "phi_spread_deg":  va_rich["phi_spread_deg"][va_valid],
                "n_valid_paths":   va_rich["n_valid_paths"][va_valid],
                "los_flag":        va_rich["los_flag"][va_valid],
                "measured_rsrp":   va_rsrp[va_valid],
                "predicted_rsrp":  va_pred[va_valid],
                "residual_db":     residual_db[va_valid],
            })
            write_hdr = not ckpt_path.exists()
            rec_df.to_csv(ckpt_path, mode="a", header=write_hdr, index=False)
            done_cells.add(cell)

        except Exception as e:
            print(f"\n  Tower {int(cell)}: ERROR — {e}  (skipping)", flush=True)

    # ── Aggregate analysis ────────────────────────────────────────────────────
    all_results = pd.read_csv(ckpt_path)
    print(f"\n{'='*65}")
    print(f"M4 RESULTS  —  {DEVICE}  |  {len(all_results)} val rows, "
          f"{all_results['cell_id'].nunique()} towers")
    print(f"{'='*65}")

    los = all_results[all_results["los_flag"] == 1]["measured_rsrp"]
    nlos = all_results[all_results["los_flag"] == 0]["measured_rsrp"]
    print(f"\n  M4a — LOS/NLOS accuracy:")
    print(f"    LOS  rows: {len(los):6d}   mean={los.mean():.2f} dBm  std={los.std():.2f} dB")
    print(f"    NLOS rows: {len(nlos):6d}   mean={nlos.mean():.2f} dBm  std={nlos.std():.2f} dB")
    if len(los) > 1 and len(nlos) > 1:
        t_stat, p_val = ttest_ind(los, nlos, equal_var=False)
        print(f"    Welch t = {t_stat:.2f}, p = {p_val:.2e}")
    else:
        t_stat, p_val = float("nan"), float("nan")

    print(f"\n  M4b — richness vs.\\ residual error:")
    valid_r = all_results.dropna(subset=["tau_rms_ns", "residual_db"])
    r_tau, p_tau = pearsonr(valid_r["tau_rms_ns"], valid_r["residual_db"])
    r_n, p_n     = pearsonr(valid_r["n_valid_paths"], valid_r["residual_db"])
    print(f"    corr(tau_rms_ns, residual_db)    = {r_tau:+.3f}  (p={p_tau:.2e})")
    print(f"    corr(n_valid_paths, residual_db) = {r_n:+.3f}  (p={p_n:.2e})")

    summary = {
        "device": DEVICE,
        "n_val_rows": int(len(all_results)),
        "n_towers": int(all_results["cell_id"].nunique()),
        "los_n": int(len(los)), "los_mean_dbm": float(los.mean()), "los_std_db": float(los.std()),
        "nlos_n": int(len(nlos)), "nlos_mean_dbm": float(nlos.mean()), "nlos_std_db": float(nlos.std()),
        "welch_t": float(t_stat), "welch_p": float(p_val),
        "corr_taurms_residual": float(r_tau), "corr_taurms_residual_p": float(p_tau),
        "corr_nvalid_residual": float(r_n), "corr_nvalid_residual_p": float(p_n),
    }
    with open(OUT_SUMMARY, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved: {OUT_CSV.name}  {OUT_SUMMARY.name}")


if __name__ == "__main__":
    main()
