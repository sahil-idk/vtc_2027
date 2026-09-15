"""
A12e — pc1 final eval with two fixes:
  1. Sentinel rows (sionna_power_raw <= -100 dBm) excluded.
  2. Towers with Sionna train std < MIN_SIONNA_STD fall back to per-tower mean.
     Rationale: if Sionna variation < 1 dBm across tower coverage, the spatial
     signal is weaker than WCL position error noise — OLS fit is ill-conditioned.
"""
import json, numpy as np, pandas as pd
from pathlib import Path
from scipy.stats import linregress, spearmanr

OUT = Path(__file__).parent / "out"
ALPHA_CLIP    = (0.0, 2.0)
MIN_ROWS      = 3
SENTINEL      = -100.0   # exclude no-path-found rows
MIN_SIONNA_STD = 1.0     # dBm; towers with less variation use per-tower mean fallback

df = pd.read_csv(OUT / "pc1_full_sionna.csv")
valid = df[df["sionna_power_raw"] > SENTINEL].copy()
train_df = valid[valid["new_split"] == "train"].copy()
val_df   = valid[valid["new_split"] == "val"].copy()

print(f"pc1  train={len(train_df):,}  val={len(val_df):,}  towers={val_df['cell_id'].nunique()}")

# Per-tower mean (used as fallback and baseline)
tmean = train_df.groupby("cell_id")["measured_rsrp"].mean()

# Per-tower OLS with Sionna std guard
coefs = {}
fallback_towers = []
for cell, tr in train_df.groupby("cell_id"):
    va = val_df[val_df["cell_id"] == cell]
    if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
        continue
    x, y = tr["sionna_power_raw"].values, tr["measured_rsrp"].values
    if x.std() < MIN_SIONNA_STD:
        fallback_towers.append(cell)
        continue
    sl, ic, _, _, _ = linregress(x, y)
    alpha = float(np.clip(sl, *ALPHA_CLIP))
    b     = float(ic)
    coefs[cell] = {"b": b, "alpha": alpha}

print(f"Towers using OLS    : {len(coefs)}")
print(f"Towers using fallback (std < {MIN_SIONNA_STD} dBm): {len(fallback_towers)}")
print(f"  fallback tower IDs: {[int(c) for c in sorted(fallback_towers)]}")

# Build val predictions
rows = []
for cell, va in val_df.groupby("cell_id"):
    y_true = va["measured_rsrp"].values
    if cell in coefs:
        b, alpha = coefs[cell]["b"], coefs[cell]["alpha"]
        pred  = b + alpha * va["sionna_power_raw"].values
        method = "ols"
    elif cell in fallback_towers and cell in tmean:
        pred   = np.full(len(va), tmean[cell])
        method = "mean_fallback"
    else:
        continue
    resid = y_true - pred
    for rid, pr, res in zip(va["_row"].values, pred, resid):
        rows.append({"_row": int(rid), "cell_id": cell,
                     "pred": float(pr), "residual": float(res), "method": method})

out_df = pd.DataFrame(rows)
ols_only = out_df[out_df["method"] == "ols"]
overall  = out_df

mae_ols_only = ols_only["residual"].abs().mean()
rmse_ols_only = np.sqrt((ols_only["residual"]**2).mean())
mae_overall   = overall["residual"].abs().mean()
rmse_overall  = np.sqrt((overall["residual"]**2).mean())

print(f"\nOLS-only towers  : MAE={mae_ols_only:.3f} dB  RMSE={rmse_ols_only:.3f} dB  (n={len(ols_only):,})")
print(f"Overall (OLS+fallback): MAE={mae_overall:.3f} dB  RMSE={rmse_overall:.3f} dB  (n={len(overall):,})")

# Baselines over same rows as 'overall'
shared_idx = out_df["_row"].values
val_shared = val_df[val_df["_row"].isin(shared_idx)].copy()

goff = (train_df["measured_rsrp"] - train_df["sionna_power_raw"]).mean()
val_shared = val_shared.merge(out_df[["_row"]], on="_row")
val_shared["pred_global"] = val_shared["sionna_power_raw"] + goff
val_shared["pred_tm"]     = val_shared["cell_id"].map(tmean)
mae_g  = (val_shared["measured_rsrp"] - val_shared["pred_global"]).abs().mean()
mae_tm = (val_shared["measured_rsrp"] - val_shared["pred_tm"]).abs().dropna().mean()

# Spearman rho on OLS towers (val)
rhos = []
for cell, va in val_df[val_df["cell_id"].isin(coefs)].groupby("cell_id"):
    if len(va) < 5:
        continue
    rho, _ = spearmanr(va["sionna_power_raw"], va["measured_rsrp"])
    if not np.isnan(rho):
        rhos.append(rho)
print(f"\nSpearman rho (OLS towers, val): n={len(rhos)}  "
      f"median={np.median(rhos):.3f}  positive={sum(r>0 for r in rhos)}/{len(rhos)}")

alphas = [v["alpha"] for v in coefs.values()]
print(f"alpha: mean={np.mean(alphas):.3f}  std={np.std(alphas):.3f}  "
      f"clipped@0={sum(a==0.0 for a in alphas)}  clipped@2={sum(a==2.0 for a in alphas)}")

print()
print("=" * 65)
print(f"FINAL SUMMARY  —  pc1  |  {out_df['cell_id'].nunique()} towers  |  {len(out_df):,} val rows")
print("=" * 65)
print(f"  {'Method':<44} {'Val MAE (dB)':>10}  {'RMSE':>8}")
print(f"  {'-'*62}")
print(f"  {'Sionna global offset':<44} {mae_g:>10.3f}  {'—':>8}")
print(f"  {'Per-tower mean (no Sionna)':<44} {mae_tm:>10.3f}  {'—':>8}")
print(f"  {'Per-tower OLS + Sionna RT  [GATE-2]':<44} {mae_overall:>10.3f}  {rmse_overall:>8.3f}")

results = {
    "device": "pc1", "operator": 1, "split": "stratified_80_20",
    "sentinel_dBm": SENTINEL, "min_sionna_std_dBm": MIN_SIONNA_STD,
    "n_train": int(len(train_df)), "n_val": int(len(val_df)),
    "n_towers_ols": len(coefs), "n_towers_fallback": len(fallback_towers),
    "mae_global_offset": float(mae_g),
    "mae_per_tower_mean": float(mae_tm),
    "mae_per_tower_ols_combined": float(mae_overall),
    "rmse_per_tower_ols_combined": float(rmse_overall),
    "mae_ols_towers_only": float(mae_ols_only),
    "spearman_rho_median": float(np.median(rhos)) if rhos else None,
    "alpha_mean": float(np.mean(alphas)), "alpha_std": float(np.std(alphas)),
}
with open(OUT / "pc1_full_results.json", "w") as f:
    json.dump(results, f, indent=2)
out_df.to_csv(OUT / "pc1_ols_val_predictions.csv", index=False)
print("\nSaved: out/pc1_full_results.json  out/pc1_ols_val_predictions.csv")
