"""
A12b_pc1_eval.py — Evaluation only, reads pc1_full_sionna.csv
Fixes the _row itertuples bug in A12, re-runs all three comparisons.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats as scipy_stats

OUT = Path(__file__).parent / "out"

ALPHA_CLIP = (0.0, 2.0)
MIN_ROWS   = 3

df = pd.read_csv(OUT / "pc1_full_sionna.csv")
train_df = df[df["new_split"] == "train"].copy()
val_df   = df[df["new_split"] == "val"].copy()

print(f"Loaded: {len(train_df):,} train / {len(val_df):,} val rows")
print(f"Towers: train={train_df['cell_id'].nunique()}  val={val_df['cell_id'].nunique()}")

# ── Baseline 1: Global offset ──────────────────────────────────────────────────
global_offset = (train_df["measured_rsrp"] - train_df["sionna_power_raw"]).mean()
val_df["pred_global"] = val_df["sionna_power_raw"] + global_offset
mae_global = (val_df["measured_rsrp"] - val_df["pred_global"]).abs().mean()
print(f"\n[Baseline 1] Global offset = {global_offset:.3f} dB")
print(f"             Val MAE = {mae_global:.3f} dB")

# ── Baseline 2: Per-tower mean (no Sionna) ────────────────────────────────────
tower_mean = train_df.groupby("cell_id")["measured_rsrp"].mean()
val_df["pred_tower_mean"] = val_df["cell_id"].map(tower_mean)
shared_val = val_df[val_df["pred_tower_mean"].notna()]
mae_tower_mean = (shared_val["measured_rsrp"] - shared_val["pred_tower_mean"]).abs().mean()
print(f"\n[Baseline 2] Per-tower mean (no Sionna)")
print(f"             Val MAE = {mae_tower_mean:.3f} dB  (n={len(shared_val):,})")

# ── Main: Per-tower OLS  RSRP = b_i + alpha_i * sionna_power_raw ──────────────
tower_coefs = {}
for cell, tr_grp in train_df.groupby("cell_id"):
    va_grp = val_df[val_df["cell_id"] == cell]
    if len(tr_grp) < MIN_ROWS or len(va_grp) < MIN_ROWS:
        continue
    x = tr_grp["sionna_power_raw"].values
    y = tr_grp["measured_rsrp"].values
    if x.std() < 1e-6:
        alpha, b = 0.0, float(y.mean())
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
    x_val  = va_grp["sionna_power_raw"].values
    y_true = va_grp["measured_rsrp"].values
    pred   = b + alpha * x_val
    resid  = y_true - pred
    rows_idx = va_grp["_row"].values  # use column directly, not itertuples
    for row_id, pr, res in zip(rows_idx, pred, resid):
        preds_ols.append({
            "_row":             int(row_id),
            "cell_id":          cell,
            "pred_ols":         float(pr),
            "residual":         float(res),
            "alpha":            alpha,
            "b":                b,
        })

ols_df = pd.DataFrame(preds_ols)
mae_ols  = ols_df["residual"].abs().mean()
rmse_ols = np.sqrt((ols_df["residual"] ** 2).mean())
n_towers = ols_df["cell_id"].nunique()

print(f"\n[Main]  Per-tower OLS + Sionna RT  (RSRP = b_i + alpha_i * sionna_power_raw)")
print(f"        Towers with OLS fit : {n_towers}")
print(f"        Val MAE             = {mae_ols:.3f} dB")
print(f"        Val RMSE            = {rmse_ols:.3f} dB  (n={len(ols_df):,})")

alphas = [v["alpha"] for v in tower_coefs.values()]
print(f"\n  alpha (slope) stats:")
print(f"    mean={np.mean(alphas):.3f}  std={np.std(alphas):.3f}"
      f"  min={np.min(alphas):.3f}  max={np.max(alphas):.3f}")
print(f"    clipped at 0 : {sum(a == 0.0 for a in alphas)} towers")
print(f"    clipped at 2 : {sum(a == 2.0 for a in alphas)} towers")

# Spearman rho per tower on val
rhos = []
for cell, va_grp in val_df.groupby("cell_id"):
    if len(va_grp) < 5:
        continue
    rho, _ = scipy_stats.spearmanr(va_grp["sionna_power_raw"], va_grp["measured_rsrp"])
    if not np.isnan(rho):
        rhos.append(rho)
print(f"\n  Per-tower Spearman rho on val (Sionna vs measured RSRP):")
print(f"    n_towers={len(rhos)}  median={np.median(rhos):.3f}"
      f"  mean={np.mean(rhos):.3f}  std={np.std(rhos):.3f}")
print(f"    positive rho: {sum(r > 0 for r in rhos)}/{len(rhos)} towers")

print(f"\n{'='*65}")
print(f"SUMMARY  —  pc1, stratified 80/20 split, {n_towers} towers")
print(f"{'='*65}")
print(f"  {'Method':<42} {'Val MAE (dB)':>12}")
print(f"  {'-'*54}")
print(f"  {'Sionna global offset (WCL baseline)':<42} {mae_global:>12.3f}")
print(f"  {'Per-tower mean (no Sionna)':<42} {mae_tower_mean:>12.3f}")
print(f"  {'Per-tower OLS + Sionna RT  [GATE-2]':<42} {mae_ols:>12.3f}")

ols_df.to_csv(OUT / "pc1_ols_val_predictions.csv", index=False)

results = {
    "device": "pc1", "operator": 1, "split": "stratified_80_20",
    "n_train_rows": int(len(train_df)), "n_val_rows": int(len(val_df)),
    "n_towers": int(n_towers),
    "global_offset_db":      float(global_offset),
    "mae_global_offset":     float(mae_global),
    "mae_per_tower_mean":    float(mae_tower_mean),
    "mae_per_tower_ols":     float(mae_ols),
    "rmse_per_tower_ols":    float(rmse_ols),
    "spearman_rho_median":   float(np.median(rhos)) if rhos else None,
    "spearman_rho_mean":     float(np.mean(rhos))   if rhos else None,
    "alpha_mean":            float(np.mean(alphas)),
    "alpha_std":             float(np.std(alphas)),
}
with open(OUT / "pc1_full_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved: out/pc1_full_results.json")
print(f"Saved: out/pc1_ols_val_predictions.csv")
