"""
A08_per_tower_calibration.py -- TWINGATE Gate 2, Option A
Per-tower offset calibration using pre-computed Sionna predictions from A03.

Instead of a single global offset per operator, fit a separate
offset per tower on training rows:
    offset_i = mean(measured_RSRP - sionna_power_raw)  [training rows, tower i]

Apply to val rows. Fall back to global offset for towers with no training rows.

Inputs:  twingate/out/sionna_raw.csv  (from A03)
         twingate/out/baseline_results.json  (A03 global baseline)
Outputs: twingate/out/per_tower_calibration.json
         twingate/out/per_tower_val_rows.csv
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

OUT = Path(__file__).parent / "out"

df = pd.read_csv(OUT / "sionna_raw.csv")
with open(OUT / "baseline_results.json") as f:
    baseline = json.load(f)

print("Per-Tower Calibration (A08)")
print("=" * 60)

results = {}

for op in [1, 2]:
    op_df = df[df["operator"] == op].copy()
    global_offset = baseline[str(op)]["calibration_offset_db"]
    wcl_mae = baseline[str(op)]["baseline_val_mae_db"]

    train = op_df[op_df["split"] == "train"].copy()
    val   = op_df[op_df["split"] == "val"].copy()

    # Per-tower offset on training rows
    tower_offsets = (
        train.groupby("cell_id")
        .apply(lambda g: float(np.mean(g["measured_rsrp"] - g["sionna_power_raw"])), include_groups=False)
        .rename("tower_offset")
    )
    n_towers_with_train = len(tower_offsets)

    # Merge per-tower offset into val rows; fall back to global offset
    val = val.merge(tower_offsets.reset_index(), on="cell_id", how="left")
    n_fallback = val["tower_offset"].isna().sum()
    val["tower_offset"] = val["tower_offset"].fillna(global_offset)

    val["sionna_cal_pt"] = val["sionna_power_raw"] + val["tower_offset"]
    val["residual_pt"]   = val["measured_rsrp"] - val["sionna_cal_pt"]

    mae  = float(val["residual_pt"].abs().mean())
    rmse = float(np.sqrt((val["residual_pt"] ** 2).mean()))
    improvement = wcl_mae - mae

    by_device = {
        dev: {
            "mae":  float(g["residual_pt"].abs().mean()),
            "n":    int(len(g)),
        }
        for dev, g in val.groupby("device")
    }

    # Also compute by gap_type
    by_gap = {
        gt: {
            "mae": float(g["residual_pt"].abs().mean()),
            "n":   int(len(g)),
        }
        for gt, g in val.groupby("gap_type")
    }

    print(f"\nOperator {op}:")
    print(f"  Global offset (A03 WCL baseline)  : {global_offset:+.3f} dB  ->  MAE = {wcl_mae:.3f} dB")
    print(f"  Per-tower offsets (n_towers={n_towers_with_train}, {n_fallback} val rows use global fallback)")
    print(f"  Per-tower calibration val MAE      : {mae:.3f} dB")
    print(f"  RMSE                               : {rmse:.3f} dB")
    print(f"  Improvement over WCL baseline      : {improvement:+.3f} dB")
    print(f"  By device:")
    for dev, ds in by_device.items():
        print(f"    {dev}: MAE={ds['mae']:.3f} dB  n={ds['n']}")

    results[str(op)] = {
        "method": "per_tower_offset_calibration",
        "wcl_baseline_mae_db":   wcl_mae,
        "per_tower_mae_db":      mae,
        "per_tower_rmse_db":     rmse,
        "improvement_db":        improvement,
        "n_towers_with_offset":  n_towers_with_train,
        "n_val_fallback_rows":   int(n_fallback),
        "global_offset_db":      global_offset,
        "by_device":             by_device,
        "by_gap_type":           by_gap,
        "tower_offsets": {
            str(int(k)): float(v)
            for k, v in tower_offsets.items()
        },
    }

    val.to_csv(OUT / f"per_tower_val_rows_op{op}.csv", index=False)

with open(OUT / "per_tower_calibration.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nSaved:")
print(f"  {OUT}/per_tower_calibration.json")
print(f"  {OUT}/per_tower_val_rows_op1.csv")
print(f"  {OUT}/per_tower_val_rows_op2.csv")
