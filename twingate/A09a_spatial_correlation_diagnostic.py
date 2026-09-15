"""
A09a_spatial_correlation_diagnostic.py -- TWINGATE Gate 2 diagnostic
Per-tower Spearman correlation between Sionna RT spatial predictions and
actual RSRP variation, after removing the per-tower mean (delta analysis).

Questions answered:
  1. Does Sionna's relative spatial pattern correlate with measured RSRP?
  2. What is the optimal per-tower slope alpha for: RSRP = mean_rsrp + alpha * delta_sionna?
  3. Does per-tower linear regression beat the flat per-tower mean?

Uses sionna_raw.csv from A03 (no new Sionna calls needed).
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

print("Spatial Correlation Diagnostic (A09a)")
print("=" * 70)
print("Question: Does Sionna RT spatial variation correlate with measured RSRP?")
print("After removing per-tower mean from both, do residuals track each other?")
print()

results = {}

for op in [1, 2]:
    op_df = df[df["operator"] == op].copy()
    global_offset = baseline[str(op)]["calibration_offset_db"]
    wcl_mae = baseline[str(op)]["baseline_val_mae_db"]

    train = op_df[op_df["split"] == "train"].copy()
    val   = op_df[op_df["split"] == "val"].copy()

    # --- Per-tower means on training data ---
    tower_stats = (
        train.groupby("cell_id")
        .agg(
            mean_sionna=("sionna_power_raw", "mean"),
            mean_rsrp=("measured_rsrp", "mean"),
            n_train=("measured_rsrp", "count"),
        )
    )

    # --- Val set: compute delta_sionna and delta_rsrp per row ---
    val = val.merge(tower_stats.reset_index(), on="cell_id", how="left")
    val["mean_sionna"] = val["mean_sionna"].fillna(val["sionna_power_raw"].mean())
    val["mean_rsrp_train"] = val["mean_rsrp"].fillna(val["measured_rsrp"].mean())

    val["delta_sionna"] = val["sionna_power_raw"] - val["mean_sionna"]
    val["delta_rsrp"]   = val["measured_rsrp"] - val["mean_rsrp_train"]

    # --- Global spatial correlation (across all val rows) ---
    rho, pval = stats.spearmanr(val["delta_sionna"], val["delta_rsrp"])
    pearson_r, _ = stats.pearsonr(val["delta_sionna"].fillna(0), val["delta_rsrp"].fillna(0))

    # --- Per-tower spatial correlation on TRAINING data ---
    tower_spearman = []
    tower_slope = []
    tower_n = []

    for cell_id, g in train.groupby("cell_id"):
        if len(g) < 5:
            continue
        m_s = g["sionna_power_raw"].mean()
        m_r = g["measured_rsrp"].mean()
        ds = g["sionna_power_raw"] - m_s
        dr = g["measured_rsrp"] - m_r

        if ds.std() < 0.01:
            continue

        rho_t, _ = stats.spearmanr(ds, dr)
        # OLS slope: dr = alpha * ds
        slope = float(np.sum(ds * dr) / np.sum(ds ** 2))

        tower_spearman.append(rho_t)
        tower_slope.append(slope)
        tower_n.append(len(g))

    tower_spearman = np.array(tower_spearman)
    tower_slope    = np.array(tower_slope)

    median_rho   = float(np.median(tower_spearman))
    pct25_rho    = float(np.percentile(tower_spearman, 25))
    pct75_rho    = float(np.percentile(tower_spearman, 75))
    median_slope = float(np.median(tower_slope))
    frac_pos_rho = float(np.mean(tower_spearman > 0))
    frac_pos_rho_02 = float(np.mean(tower_spearman > 0.2))

    print(f"\nOperator {op}  (WCL baseline MAE = {wcl_mae:.3f} dB)")
    print(f"  Global Spearman(delta_sionna, delta_rsrp) on val: rho = {rho:+.4f}  p = {pval:.3e}")
    print(f"  Global Pearson r on val                         : r   = {pearson_r:+.4f}")
    print()
    print(f"  Per-tower Spearman (training, {len(tower_spearman)} towers with n>=5):")
    print(f"    Median rho    : {median_rho:+.4f}")
    print(f"    25th / 75th   : {pct25_rho:+.4f} / {pct75_rho:+.4f}")
    print(f"    Frac rho > 0  : {frac_pos_rho*100:.1f}%  (random = 50%)")
    print(f"    Frac rho > 0.2: {frac_pos_rho_02*100:.1f}%")
    print()
    print(f"  Per-tower OLS slope alpha (dr = alpha * ds):")
    print(f"    Median alpha  : {median_slope:+.4f}  (ideal = 1.0, useless = 0.0)")
    print(f"    Frac alpha > 0: {np.mean(tower_slope > 0)*100:.1f}%")

    # --- Per-tower linear regression on val ---
    # Predict: rsrp = mean_rsrp_train + alpha_global * delta_sionna
    #   where alpha_global = median OLS slope on training
    for alpha_test in [0.0, median_slope, 1.0]:
        val["pred_linear"] = val["mean_rsrp_train"] + alpha_test * val["delta_sionna"]
        mae_lin = float((val["measured_rsrp"] - val["pred_linear"]).abs().mean())
        label = f"alpha={alpha_test:.3f}"
        tag = ""
        if alpha_test == 0.0:
            tag = "  <- flat per-tower mean (no Sionna spatial)"
        elif alpha_test == median_slope:
            tag = "  <- optimal OLS slope"
        print(f"  Val MAE with {label}: {mae_lin:.3f} dB{tag}")

    print()
    # --- Verdict ---
    if abs(rho) < 0.05 and median_rho < 0.1:
        verdict = "SIONNA SPATIAL = NOISE. Position errors destroy spatial prediction."
    elif median_rho > 0.2 and median_slope > 0.15:
        verdict = "SIONNA SPATIAL HAS SIGNAL. Linear calibration may help."
    else:
        verdict = "MARGINAL CORRELATION. Sionna spatial adds little beyond per-tower mean."
    print(f"  VERDICT: {verdict}")

    results[str(op)] = {
        "global_spearman_val": float(rho),
        "global_pval": float(pval),
        "global_pearson_val": float(pearson_r),
        "per_tower_median_spearman": median_rho,
        "per_tower_p25_spearman": pct25_rho,
        "per_tower_p75_spearman": pct75_rho,
        "per_tower_median_slope": median_slope,
        "frac_towers_positive_rho": float(frac_pos_rho),
        "frac_towers_rho_gt_02": float(frac_pos_rho_02),
        "n_towers_analyzed": int(len(tower_spearman)),
        "verdict": verdict,
    }

with open(OUT / "spatial_diagnostic.json", "w") as f:
    json.dump(results, f, indent=2)

print("\n" + "=" * 70)
print("Summary:")
for op_str, r in results.items():
    print(f"  Op{op_str}: global Spearman={r['global_spearman_val']:+.3f}, "
          f"median per-tower rho={r['per_tower_median_spearman']:+.3f}, "
          f"median slope={r['per_tower_median_slope']:+.3f}")
print(f"\nSaved: {OUT}/spatial_diagnostic.json")
