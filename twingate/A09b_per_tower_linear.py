"""
A09b_per_tower_linear.py -- TWINGATE Gate 2, definitive linear test
Per-tower linear regression: RSRP = b_i + alpha_i * sionna_power_raw
Fitted on training rows, evaluated on val rows.

This is the strongest possible linear use of Sionna RT spatial predictions.
If this can't beat the flat per-tower mean, no linear method will.

Baselines:
  - Flat per-tower mean  (A09a, no Sionna):      Op1=4.622  Op2=7.741
  - Per-tower offset A08 (Sionna, alpha=1):       Op1=9.191  Op2=7.655
  - WCL global baseline  (A03):                   Op1=10.866 Op2=12.238
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

OUT = Path(__file__).parent / "out"

df = pd.read_csv(OUT / "sionna_raw.csv")
with open(OUT / "baseline_results.json") as f:
    baseline = json.load(f)

print("Per-Tower Linear Regression (A09b)")
print("=" * 70)
print("Model: RSRP = b_i + alpha_i * sionna_power  (per tower, OLS on training)")
print()

all_results = {}

for op in [1, 2]:
    op_df = df[df["operator"] == op].copy()
    global_offset = baseline[str(op)]["calibration_offset_db"]
    wcl_mae = baseline[str(op)]["baseline_val_mae_db"]

    train = op_df[op_df["split"] == "train"].copy()
    val   = op_df[op_df["split"] == "val"].copy()

    # Fit per-tower OLS: RSRP = b_i + alpha_i * sionna_power
    tower_params = {}
    for cell_id, g in train.groupby("cell_id"):
        x = g["sionna_power_raw"].values
        y = g["measured_rsrp"].values
        n = len(x)

        if n < 5 or x.std() < 0.01:
            # Not enough data or no variation -> use per-tower mean (alpha=0)
            tower_params[cell_id] = {"alpha": 0.0, "b": float(y.mean()), "n": n, "method": "mean"}
        else:
            # OLS
            slope, intercept, r, pval, se = stats.linregress(x, y)
            # Clip slope to [0, 2] to avoid extrapolation disasters
            slope_clipped = float(np.clip(slope, 0.0, 2.0))
            # Refit intercept with clipped slope
            b_clipped = float(y.mean() - slope_clipped * x.mean())
            tower_params[cell_id] = {
                "alpha": slope_clipped,
                "alpha_raw": float(slope),
                "b": b_clipped,
                "n": n,
                "r": float(r),
                "method": "ols",
            }

    # Summary of fitted slopes
    alphas = [v["alpha"] for v in tower_params.values() if v["method"] == "ols"]
    rs     = [v["r"]     for v in tower_params.values() if v["method"] == "ols"]
    print(f"Operator {op} fitted slopes (n={len(alphas)} towers with OLS):")
    print(f"  alpha: median={np.median(alphas):.3f}  mean={np.mean(alphas):.3f}  "
          f"std={np.std(alphas):.3f}  [min={np.min(alphas):.2f}, max={np.max(alphas):.2f}]")
    print(f"  r:     median={np.median(rs):.3f}  "
          f"frac>0.3: {np.mean(np.array(rs)>0.3)*100:.1f}%")
    print()

    # Apply to val rows
    val = val.copy()
    val["pred_alpha"] = np.nan
    val["pred_mean_only"] = np.nan

    for cell_id, g_idx in val.groupby("cell_id").groups.items():
        p = tower_params.get(cell_id)
        if p is None:
            # Unseen tower: use global calibration
            val.loc[g_idx, "pred_alpha"] = val.loc[g_idx, "sionna_power_raw"] + global_offset
            val.loc[g_idx, "pred_mean_only"] = val.loc[g_idx, "sionna_power_raw"] + global_offset
        else:
            val.loc[g_idx, "pred_alpha"] = p["alpha"] * val.loc[g_idx, "sionna_power_raw"] + p["b"]
            val.loc[g_idx, "pred_mean_only"] = p["b"] + p["alpha"] * val.loc[g_idx, "sionna_power_raw"].mean()

    mae_linear  = float((val["measured_rsrp"] - val["pred_alpha"]).abs().mean())
    rmse_linear = float(np.sqrt(((val["measured_rsrp"] - val["pred_alpha"])**2).mean()))

    # Also test per-tower mean (b only, no Sionna): b_i from OLS = mean(rsrp) - alpha*mean(sionna)
    # which is not exactly mean(rsrp). Get true per-tower mean:
    tower_mean_rsrp = train.groupby("cell_id")["measured_rsrp"].mean()
    val2 = val.merge(tower_mean_rsrp.reset_index().rename(columns={"measured_rsrp": "mean_rsrp_train"}),
                     on="cell_id", how="left")
    val2["mean_rsrp_train"] = val2["mean_rsrp_train"].fillna(val2["measured_rsrp"].mean())
    mae_flat = float((val2["measured_rsrp"] - val2["mean_rsrp_train"]).abs().mean())

    print(f"Operator {op} val MAE:")
    print(f"  Flat per-tower mean  (no Sionna)     : {mae_flat:.3f} dB")
    print(f"  Per-tower linear OLS (Sionna spatial) : {mae_linear:.3f} dB")
    print(f"  Per-tower offset A08 (alpha=1 fixed)  : {9.191 if op==1 else 7.655:.3f} dB")
    print(f"  WCL global baseline  (A03)            : {wcl_mae:.3f} dB")
    print()

    improvement_vs_flat = mae_flat - mae_linear
    improvement_vs_wcl  = wcl_mae - mae_linear
    print(f"  vs flat per-tower mean: {improvement_vs_flat:+.3f} dB  ({'better' if improvement_vs_flat>0 else 'worse'})")
    print(f"  vs WCL baseline:        {improvement_vs_wcl:+.3f} dB  ({'better' if improvement_vs_wcl>0 else 'worse'})")
    print()

    if improvement_vs_flat > 0.1:
        verdict = "SIONNA LINEAR BEATS FLAT MEAN: genuine spatial contribution!"
    elif improvement_vs_flat > 0:
        verdict = "Marginal improvement over flat mean (< 0.1 dB): not significant."
    else:
        verdict = "Flat per-tower mean beats per-tower linear: Sionna spatial adds noise."
    print(f"  VERDICT: {verdict}")
    print()

    all_results[str(op)] = {
        "mae_per_tower_linear": mae_linear,
        "rmse_per_tower_linear": rmse_linear,
        "mae_flat_mean": mae_flat,
        "mae_wcl_baseline": wcl_mae,
        "improvement_vs_flat": float(improvement_vs_flat),
        "improvement_vs_wcl": float(improvement_vs_wcl),
        "median_alpha": float(np.median(alphas)),
        "median_r": float(np.median(rs)),
        "verdict": verdict,
    }

print("=" * 70)
print("All results summary:")
print(f"{'Method':<40} {'Op1 MAE':>10} {'Op2 MAE':>10}")
print(f"{'WCL global baseline (A03)':<40} {'10.866':>10} {'12.238':>10}")
print(f"{'Per-tower offset A08 (alpha=1)':<40} {'9.191':>10} {'7.655':>10}")
print(f"{'Per-tower linear OLS (A09b)':<40} {all_results['1']['mae_per_tower_linear']:>10.3f} {all_results['2']['mae_per_tower_linear']:>10.3f}")
print(f"{'Flat per-tower mean (no Sionna)':<40} {all_results['1']['mae_flat_mean']:>10.3f} {all_results['2']['mae_flat_mean']:>10.3f}")

with open(OUT / "per_tower_linear.json", "w") as f:
    json.dump(all_results, f, indent=2)
print(f"\nSaved: {OUT}/per_tower_linear.json")
