"""
A03b_ocid_baseline.py — TWINGATE Gate 2, Step 3b
Sionna RT baseline using OpenCelliD tower positions instead of WCL.

Identical to A03 except: tower positions come from tower_positions.csv (A00)
rather than being computed via WCL. For towers with MISSING OCID position,
falls back to WCL from tower_positions.csv.

Outputs:
  - twingate/out/sionna_raw_ocid.csv
  - twingate/out/baseline_results_ocid.json
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

SPLIT_IDX      = OUT / "split_index.csv"
GAP_LABELS     = OUT / "gap_labels.csv"
TOWER_POS_CSV  = OUT / "tower_positions.csv"    # from A00

RSRP_COL   = "PCell_RSRP_max"
FREQ_COL   = "PCell_freq_MHz"
CELL_COL   = "PCell_Cell_Identity"
LAT_COL    = "Latitude"
LON_COL    = "Longitude"
DEVICE_COL = "device"

TX_HEIGHT_M    = 30.0
RX_HEIGHT_M    = 1.5
EVAL_BATCH     = 40
MAX_TRAIN_ROWS = 40
MIN_ROWS       = 5

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
    scene.add(Transmitter(name="txa03b", position=[float(tx_x), float(tx_y), TX_HEIGHT_M]))
    powers = []
    for start in range(0, len(rx_lats), EVAL_BATCH):
        blats = rx_lats[start:start + EVAL_BATCH]
        blons = rx_lons[start:start + EVAL_BATCH]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = latlon_to_xy(float(la), float(lo), orig_lat, orig_lon)
            scene.add(Receiver(name=f"rxa03b{i}", position=[float(xi), float(yi), RX_HEIGHT_M]))
        paths = solver(scene=scene, max_depth=5, diffraction=True)
        powers.extend(power_dbm(paths).tolist())
        for i in range(len(blats)):
            scene.remove(f"rxa03b{i}")
    scene.remove("txa03b")
    return np.array(powers)


def process_operator(op, df_op, split_idx, gap_labels, tower_pos):
    print(f"\n{'='*60}")
    print(f"Operator {op}  [OCID positions]")
    print(f"{'='*60}")

    orig_lat, orig_lon = SCENE_ORIGINS[op]
    scene  = load_scene(SCENE_XML[op])
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    solver = PathSolver()

    df_op = df_op.merge(split_idx[["_row", "split"]], on="_row", how="left")
    df_op = df_op.merge(gap_labels[["_row", "gap_type"]], on="_row", how="left")
    df_op["gap_type"] = df_op["gap_type"].fillna("Unflagged")
    df_op["split"]    = df_op["split"].fillna("unknown")

    df_train = df_op[
        (df_op["split"] == "train") &
        df_op[RSRP_COL].notna() &
        (df_op["gap_type"] != "TypeA") &
        df_op[LAT_COL].notna()
    ].copy()

    df_val = df_op[
        (df_op["split"] == "val") &
        df_op[RSRP_COL].notna() &
        df_op[LAT_COL].notna()
    ].copy()

    print(f"  Training pool: {len(df_train):,} rows")
    print(f"  Val pool     : {len(df_val):,} rows")

    # Tower positions from A00 (OCID or WCL fallback)
    op_towers = tower_pos[tower_pos["operator"] == op].copy()
    op_towers = op_towers[op_towers["tower_lat"].notna()]
    pos_map = {
        int(r["PCell_Cell_Identity"]): (r["tower_lat"], r["tower_lon"], r["position_source"])
        for _, r in op_towers.iterrows()
    }

    # Also compute WCL for towers that are completely MISSING from OCID
    wcl_backup = (
        df_train.groupby(CELL_COL)[[LAT_COL, LON_COL, RSRP_COL]]
        .apply(lambda g: pd.Series({
            "wcl_lat": np.average(g[LAT_COL], weights=10 ** (g[RSRP_COL] / 10)),
            "wcl_lon": np.average(g[LON_COL], weights=10 ** (g[RSRP_COL] / 10)),
        }), include_groups=False)
        .reset_index()
    )

    # Merge to get all cells that appear in train (drop NaN cell IDs)
    train_cells = df_train[CELL_COL].dropna().unique()
    print(f"  Towers with OCID position    : {sum(1 for c in train_cells if int(c) in pos_map)}")
    print(f"  Towers needing WCL fallback  : {sum(1 for c in train_cells if int(c) not in pos_map)}")

    all_rows = []
    pos_source_counts = {}

    for cell in train_cells:
        eci = int(cell)
        tr = df_train[df_train[CELL_COL] == cell]
        va = df_val[df_val[CELL_COL] == cell]
        if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
            continue

        if eci in pos_map:
            tw_lat, tw_lon, pos_src = pos_map[eci]
        else:
            wcl_row = wcl_backup[wcl_backup[CELL_COL] == cell]
            if wcl_row.empty:
                continue
            tw_lat = float(wcl_row.iloc[0]["wcl_lat"])
            tw_lon = float(wcl_row.iloc[0]["wcl_lon"])
            pos_src = "wcl_only"

        pos_source_counts[pos_src] = pos_source_counts.get(pos_src, 0) + 1

        if len(tr) > MAX_TRAIN_ROWS:
            tr = tr.sample(MAX_TRAIN_ROWS, random_state=eci % (2 ** 31))

        tr_powers = run_sionna_batch(
            tr[LAT_COL].tolist(), tr[LON_COL].tolist(),
            tw_lat, tw_lon, scene, solver, orig_lat, orig_lon)

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
                    "tower_lat": tw_lat,
                    "tower_lon": tw_lon,
                    "position_source": pos_src,
                })
            return rows

        all_rows.extend(make_rows(tr, tr_powers, "train"))
        all_rows.extend(make_rows(va, va_powers, "val"))
        print(f"  Tower {eci}: [{pos_src}] tr={len(tr)} va={len(va)}")

    result_df = pd.DataFrame(all_rows)
    if result_df.empty:
        print("  ERROR: no rows processed.")
        return result_df, {}

    print(f"\n  Position source breakdown: {pos_source_counts}")

    train_res = result_df[result_df["split"] == "train"]
    offset_db = float((train_res["measured_rsrp"] - train_res["sionna_power_raw"]).mean())
    offset_std = float((train_res["measured_rsrp"] - train_res["sionna_power_raw"]).std())
    result_df["sionna_power_cal"] = result_df["sionna_power_raw"] + offset_db
    result_df["residual_cal"] = result_df["measured_rsrp"] - result_df["sionna_power_cal"]

    print(f"\n  CALIBRATION INDEPENDENCE CHECK:")
    print(f"  Offset = mean(measured_RSRP - Sionna_power) on training rows ONLY.")
    print(f"  No 3GPP path-loss formula used. Offset = {offset_db:.3f} dB (std={offset_std:.3f}, n={len(train_res)}).")
    print(f"  PASS — offset anchored to measured data only.")

    val_res = result_df[result_df["split"] == "val"]
    mae  = float(val_res["residual_cal"].abs().mean())
    rmse = float(np.sqrt((val_res["residual_cal"] ** 2).mean()))
    print(f"\n  BASELINE Val MAE  (OCID positions): {mae:.3f} dB")
    print(f"  BASELINE Val RMSE (OCID positions): {rmse:.3f} dB")

    print(f"\n  By device:")
    for dev, g in val_res.groupby("device"):
        d_mae  = g["residual_cal"].abs().mean()
        d_rmse = np.sqrt((g["residual_cal"] ** 2).mean())
        print(f"    {dev}: MAE={d_mae:.3f} dB  RMSE={d_rmse:.3f} dB  n={len(g)}")

    print(f"\n  By position_source:")
    for src, g in val_res.groupby("position_source"):
        print(f"    {src}: MAE={g['residual_cal'].abs().mean():.3f} dB  n={len(g)}")

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
        "position_source_counts": pos_source_counts,
        "by_device": {
            dev: {
                "mae": float(g["residual_cal"].abs().mean()),
                "rmse": float(np.sqrt((g["residual_cal"] ** 2).mean())),
                "n": int(len(g)),
            }
            for dev, g in val_res.groupby("device")
        },
        "by_position_source": {
            src: {
                "mae": float(g["residual_cal"].abs().mean()),
                "n": int(len(g)),
            }
            for src, g in val_res.groupby("position_source")
        },
    }
    return result_df, stats


def main():
    print("A03b OCID Baseline — loading data...")
    df = pd.read_csv(DATAFILE, low_memory=False)
    df["_row"] = df.index
    df["ts_gps"] = pd.to_datetime(df.get("ts_gps"), errors="coerce")

    if not TOWER_POS_CSV.exists():
        raise FileNotFoundError("Run A00_opencellid_lookup.py first.")
    tower_pos = pd.read_csv(TOWER_POS_CSV)
    print(f"  Tower positions loaded: {len(tower_pos)} towers "
          f"({tower_pos['tower_lat'].notna().sum()} with positions)")

    split_idx  = pd.read_csv(SPLIT_IDX)  if SPLIT_IDX.exists()  else None
    gap_labels = pd.read_csv(GAP_LABELS) if GAP_LABELS.exists() else None
    if split_idx is None or gap_labels is None:
        raise FileNotFoundError("Run A01 and A02 first.")

    all_results = []
    all_stats   = {}

    for op in [1, 2]:
        df_op = df[df["operator"] == op].copy()
        result_df, stats = process_operator(op, df_op, split_idx, gap_labels, tower_pos)
        if not result_df.empty:
            all_results.append(result_df)
            all_stats[str(op)] = stats

    combined = pd.concat(all_results, ignore_index=True) if all_results else pd.DataFrame()
    combined.to_csv(OUT / "sionna_raw_ocid.csv", index=False)
    print(f"\nSionna OCID results saved: {OUT}/sionna_raw_ocid.csv  ({len(combined):,} rows)")

    with open(OUT / "baseline_results_ocid.json", "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"Baseline OCID results saved: {OUT}/baseline_results_ocid.json")

    print("\n\nCOMPARISON SUMMARY (OCID positions vs WCL positions)")
    print("=" * 60)
    for op_str, stats in all_stats.items():
        print(f"Op{op_str}: MAE={stats['baseline_val_mae_db']:.3f} dB  "
              f"(position sources: {stats['position_source_counts']})")

    # Try to compare with WCL baseline
    wcl_json = OUT / "baseline_results.json"
    if wcl_json.exists():
        with open(wcl_json) as f:
            wcl_stats = json.load(f)
        print()
        for op_str in all_stats:
            ocid_mae = all_stats[op_str]["baseline_val_mae_db"]
            wcl_mae  = wcl_stats.get(op_str, {}).get("baseline_val_mae_db", None)
            if wcl_mae:
                delta = wcl_mae - ocid_mae
                print(f"Op{op_str}: WCL MAE={wcl_mae:.3f} dB  OCID MAE={ocid_mae:.3f} dB  "
                      f"Improvement={delta:+.3f} dB")


if __name__ == "__main__":
    main()
