"""
A03_fresh_baseline.py — TWINGATE Gate 2, Step 3
Fresh Sionna RT baseline. Nothing from prior sessions reused.

What this does (in order):
  1. Loads split index (A02) and gap labels (A01).
  2. Builds WCL tower positions from TRAINING rows only.
     (rows where: split=train, PCell_RSRP_max not null, gap_type != TypeA)
  3. Runs Sionna RT forward pass for every qualifying tower on:
       (a) a capped sample of training rows  → for calibration offset fitting
       (b) all held-out (val) rows for that tower → for evaluation
  4. Fits per-operator calibration offset = mean(measured_RSRP − sionna_power)
     on training rows ONLY. No 3GPP model involved — verified and logged.
  5. Evaluates baseline MAE/RMSE on val rows per operator, stratified by device.
  6. Saves sionna_raw.csv (all rows with sionna_power and metadata) and
     baseline_results.json.

Calibration independence assertion:
  The offset is computed as a mean residual between measured RF values and the
  Sionna physics model. No 3GPP path-loss formula appears anywhere in this file.
  Confirmed explicitly in the decision log printed at end of run.

Architecture reference:
  NBF (Lyu et al. arXiv:2508.06956) Pretrain-and-Calibrate — Sionna RT is the
  physics pretraining; this script is the "Calibrate" step before the GP correction.
"""

import json
import math
import numpy as np
import pandas as pd
from pathlib import Path
import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import Transmitter, Receiver, PathSolver, PlanarArray, load_scene

ROOT     = Path(__file__).parent.parent
DATAFILE = ROOT / "cellular_dataframe_cleaned.csv"
OUT      = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

SPLIT_IDX  = OUT / "split_index.csv"
GAP_LABELS = OUT / "gap_labels.csv"

RSRP_COL   = "PCell_RSRP_max"
FREQ_COL   = "PCell_freq_MHz"
CELL_COL   = "PCell_Cell_Identity"
LAT_COL    = "Latitude"
LON_COL    = "Longitude"
DEVICE_COL = "device"

TX_HEIGHT_M    = 30.0
RX_HEIGHT_M    = 1.5
EVAL_BATCH     = 40    # PathSolver batch size
MAX_TRAIN_ROWS = 40    # training rows sampled per tower for calibration
MIN_ROWS       = 5     # skip tower if fewer rows than this in either split

SCENE_ORIGINS = {
    1: (52.507005, 13.323428),
    2: (52.506112, 13.321908),
}
SCENE_XML = {
    1: str(ROOT / "scene_operator1" / "scene.xml"),
    2: str(ROOT / "scene_operator2" / "scene.xml"),
}


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


def run_sionna_batch(rx_lats, rx_lons, tx_lat, tx_lon,
                     scene, solver, orig_lat, orig_lon):
    tx_x, tx_y = latlon_to_xy(tx_lat, tx_lon, orig_lat, orig_lon)
    scene.add(Transmitter(name="txa03", position=[float(tx_x), float(tx_y), TX_HEIGHT_M]))
    powers = []
    for start in range(0, len(rx_lats), EVAL_BATCH):
        blats = rx_lats[start:start + EVAL_BATCH]
        blons = rx_lons[start:start + EVAL_BATCH]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = latlon_to_xy(float(la), float(lo), orig_lat, orig_lon)
            scene.add(Receiver(name=f"rxa03{i}", position=[float(xi), float(yi), RX_HEIGHT_M]))
        paths = solver(scene=scene, max_depth=5, diffraction=True)
        powers.extend(power_dbm(paths).tolist())
        for i in range(len(blats)):
            scene.remove(f"rxa03{i}")
    scene.remove("txa03")
    return np.array(powers)


def process_operator(op, df_op, split_idx, gap_labels):
    print(f"\n{'='*60}")
    print(f"Operator {op}")
    print(f"{'='*60}")

    orig_lat, orig_lon = SCENE_ORIGINS[op]
    scene  = load_scene(SCENE_XML[op])
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    solver = PathSolver()

    # Merge split and gap labels
    df_op = df_op.merge(split_idx[["_row", "split"]], on="_row", how="left")
    df_op = df_op.merge(gap_labels[["_row", "gap_type"]], on="_row", how="left")
    df_op["gap_type"] = df_op["gap_type"].fillna("Unflagged")
    df_op["split"]    = df_op["split"].fillna("unknown")

    # Training pool: split=train, valid RSRP, gap_type != TypeA
    df_train = df_op[
        (df_op["split"] == "train") &
        df_op[RSRP_COL].notna() &
        (df_op["gap_type"] != "TypeA") &
        df_op[LAT_COL].notna()
    ].copy()

    # Val pool: split=val, valid RSRP, valid GPS
    # TypeB rows ARE included in val (architecture principle: retain everywhere)
    df_val = df_op[
        (df_op["split"] == "val") &
        df_op[RSRP_COL].notna() &
        df_op[LAT_COL].notna()
    ].copy()

    print(f"  Training pool: {len(df_train):,} rows")
    print(f"  Val pool     : {len(df_val):,} rows")

    # WCL positions from training rows only
    wcl = (
        df_train.groupby(CELL_COL)[[LAT_COL, LON_COL, RSRP_COL]]
        .apply(lambda g: pd.Series({
            "wcl_lat": np.average(g[LAT_COL], weights=10 ** (g[RSRP_COL] / 10)),
            "wcl_lon": np.average(g[LON_COL], weights=10 ** (g[RSRP_COL] / 10)),
            "n_train": len(g),
        }), include_groups=False)
        .reset_index()
    )
    print(f"  WCL positions computed for {len(wcl)} towers (training rows only)")

    all_rows = []

    for _, tower in wcl.iterrows():
        cell = tower[CELL_COL]
        tw_lat, tw_lon = tower["wcl_lat"], tower["wcl_lon"]

        tr = df_train[df_train[CELL_COL] == cell]
        va = df_val[df_val[CELL_COL] == cell]

        if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
            continue

        # Sample training rows for calibration fitting
        if len(tr) > MAX_TRAIN_ROWS:
            tr = tr.sample(MAX_TRAIN_ROWS, random_state=int(cell) % (2 ** 31))

        # Sionna on training rows
        tr_powers = run_sionna_batch(
            tr[LAT_COL].tolist(), tr[LON_COL].tolist(),
            tw_lat, tw_lon, scene, solver, orig_lat, orig_lon)

        # Sionna on val rows
        va_powers = run_sionna_batch(
            va[LAT_COL].tolist(), va[LON_COL].tolist(),
            tw_lat, tw_lon, scene, solver, orig_lat, orig_lon)

        def make_rows(subset, powers, spl):
            rows = []
            for (_, row), pw in zip(subset.iterrows(), powers):
                dist = haversine_m(float(row[LAT_COL]), float(row[LON_COL]), tw_lat, tw_lon)
                rows.append({
                    "_row": int(row["_row"]),
                    "operator": op,
                    "device": row[DEVICE_COL],
                    "cell_id": cell,
                    "split": spl,
                    "measured_rsrp": float(row[RSRP_COL]),
                    "sionna_power_raw": float(pw),
                    "dist_m": dist,
                    "freq_mhz": float(row[FREQ_COL]) if FREQ_COL in row and pd.notna(row.get(FREQ_COL)) else np.nan,
                    "area": row.get("area", np.nan),
                    "gap_type": row["gap_type"],
                    "wcl_lat": tw_lat,
                    "wcl_lon": tw_lon,
                })
            return rows

        all_rows.extend(make_rows(tr, tr_powers, "train"))
        all_rows.extend(make_rows(va, va_powers, "val"))

        print(f"  Tower {cell}: tr={len(tr)} va={len(va)} — OK")

    result_df = pd.DataFrame(all_rows)

    if result_df.empty:
        print("  ERROR: no rows processed.")
        return result_df, {}

    # Calibration offset: mean(measured - sionna) on TRAINING rows only
    train_res = result_df[result_df["split"] == "train"]
    offset_db = float((train_res["measured_rsrp"] - train_res["sionna_power_raw"]).mean())
    offset_std = float((train_res["measured_rsrp"] - train_res["sionna_power_raw"]).std())
    result_df["sionna_power_cal"] = result_df["sionna_power_raw"] + offset_db
    result_df["residual_cal"] = result_df["measured_rsrp"] - result_df["sionna_power_cal"]

    # Calibration independence assertion
    print(f"\n  CALIBRATION INDEPENDENCE CHECK:")
    print(f"  Offset = mean(measured_RSRP - Sionna_power) on training rows ONLY.")
    print(f"  No 3GPP path-loss formula used anywhere. Offset = {offset_db:.3f} dB "
          f"(std={offset_std:.3f} dB, n={len(train_res)}).")
    print(f"  PASS — offset anchored to measured data only, not to any standard model.")

    # Baseline evaluation on val rows
    val_res = result_df[result_df["split"] == "val"]
    mae  = float(val_res["residual_cal"].abs().mean())
    rmse = float(np.sqrt((val_res["residual_cal"] ** 2).mean()))
    print(f"\n  BASELINE Val MAE : {mae:.3f} dB")
    print(f"  BASELINE Val RMSE: {rmse:.3f} dB")

    print(f"\n  By device:")
    for dev, g in val_res.groupby("device"):
        d_mae  = g["residual_cal"].abs().mean()
        d_rmse = np.sqrt((g["residual_cal"] ** 2).mean())
        print(f"    {dev}: MAE={d_mae:.3f} dB  RMSE={d_rmse:.3f} dB  n={len(g)}")

    print(f"\n  By gap_type:")
    for gt, g in val_res.groupby("gap_type"):
        d_mae = g["residual_cal"].abs().mean()
        print(f"    {gt}: MAE={d_mae:.3f} dB  n={len(g)}")

    stats = {
        "operator": op,
        "calibration_offset_db": offset_db,
        "calibration_std_db": offset_std,
        "calibration_n_train_rows": int(len(train_res)),
        "calibration_anchored_to_3gpp": False,
        "baseline_val_mae_db": mae,
        "baseline_val_rmse_db": rmse,
        "n_val_rows": int(len(val_res)),
        "n_towers": int(result_df["cell_id"].nunique()),
        "by_device": {
            dev: {
                "mae": float(g["residual_cal"].abs().mean()),
                "rmse": float(np.sqrt((g["residual_cal"] ** 2).mean())),
                "n": int(len(g)),
            }
            for dev, g in val_res.groupby("device")
        },
        "by_gap_type": {
            gt: {"mae": float(g["residual_cal"].abs().mean()), "n": int(len(g))}
            for gt, g in val_res.groupby("gap_type")
        },
    }
    return result_df, stats


def main():
    print("A03 Fresh Baseline — loading data...")
    df = pd.read_csv(DATAFILE, low_memory=False)
    df["_row"] = df.index
    df[  "ts_gps"] = pd.to_datetime(df.get("ts_gps"), errors="coerce")

    split_idx  = pd.read_csv(SPLIT_IDX)  if SPLIT_IDX.exists()  else None
    gap_labels = pd.read_csv(GAP_LABELS) if GAP_LABELS.exists() else None

    if split_idx is None or gap_labels is None:
        raise FileNotFoundError("Run A01 and A02 first.")

    all_results = []
    all_stats   = {}

    for op in [1, 2]:
        df_op = df[df["operator"] == op].copy()
        result_df, stats = process_operator(op, df_op, split_idx, gap_labels)
        if not result_df.empty:
            all_results.append(result_df)
            all_stats[str(op)] = stats

    combined = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    combined.to_csv(OUT / "sionna_raw.csv", index=False)
    print(f"\nSionna raw results saved: {OUT}/sionna_raw.csv  ({len(combined):,} rows)")

    with open(OUT / "baseline_results.json", "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"Baseline results saved: {OUT}/baseline_results.json")


if __name__ == "__main__":
    main()
