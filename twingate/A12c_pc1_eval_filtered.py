"""
A12c — pc1 OLS eval, sentinel rows (-270 dBm) filtered out before fitting.
"""
import json, numpy as np, pandas as pd
from pathlib import Path
from scipy import stats as scipy_stats

OUT = Path(__file__).parent / "out"
ALPHA_CLIP = (0.0, 2.0)
MIN_ROWS   = 3
SENTINEL   = -100.0   # rows with sionna_power_raw <= this are "no path found"

df = pd.read_csv(OUT / "pc1_full_sionna.csv")

valid = df[df["sionna_power_raw"] > SENTINEL].copy()
sents = len(df) - len(valid)
print(f"Total rows: {len(df):,}  Valid (>{SENTINEL} dBm): {len(valid):,}  Sentinel removed: {sents:,}")

train_df = valid[valid["new_split"] == "train"].copy()
val_df   = valid[valid["new_split"] == "val"].copy()
print(f"After filter: train={len(train_df):,}  val={len(val_df):,}\n")

# Baseline 1: global offset
goff = (train_df["measured_rsrp"] - train_df["sionna_power_raw"]).mean()
val_df["pred_global"] = val_df["sionna_power_raw"] + goff
mae_g = (val_df["measured_rsrp"] - val_df["pred_global"]).abs().mean()
print(f"[Baseline 1] Global offset = {goff:.3f} dB   Val MAE = {mae_g:.3f} dB")

# Baseline 2: per-tower mean (no Sionna)
tmean = train_df.groupby("cell_id")["measured_rsrp"].mean()
val_df["pred_tm"] = val_df["cell_id"].map(tmean)
shared = val_df[val_df["pred_tm"].notna()]
mae_tm = (shared["measured_rsrp"] - shared["pred_tm"]).abs().mean()
print(f"[Baseline 2] Per-tower mean (no Sionna)  Val MAE = {mae_tm:.3f} dB  (n={len(shared):,})")

# Per-tower OLS
coefs = {}
for cell, tr in train_df.groupby("cell_id"):
    va = val_df[val_df["cell_id"] == cell]
    if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
        continue
    x, y = tr["sionna_power_raw"].values, tr["measured_rsrp"].values
    if x.std() < 1e-6:
        alpha, b = 0.0, float(y.mean())
    else:
        slope, intercept, _, _, _ = scipy_stats.linregress(x, y)
        alpha = float(np.clip(slope, *ALPHA_CLIP))
        b = float(intercept)
    coefs[cell] = {"b": b, "alpha": alpha}

rows = []
for cell, va in val_df.groupby("cell_id"):
    if cell not in coefs:
        continue
    b, alpha = coefs[cell]["b"], coefs[cell]["alpha"]
    pred  = b + alpha * va["sionna_power_raw"].values
    resid = va["measured_rsrp"].values - pred
    for rid, pr, res in zip(va["_row"].values, pred, resid):
        rows.append({"_row": int(rid), "cell_id": cell,
                     "pred": float(pr), "residual": float(res), "alpha": alpha})

ols = pd.DataFrame(rows)
mae_ols  = ols["residual"].abs().mean()
rmse_ols = np.sqrt((ols["residual"] ** 2).mean())
n_tw = ols["cell_id"].nunique()
print(f"[Main]  Per-tower OLS + Sionna RT")
print(f"        Towers: {n_tw}  Val MAE = {mae_ols:.3f} dB  "
      f"Val RMSE = {rmse_ols:.3f} dB  (n={len(ols):,})")

alphas = [v["alpha"] for v in coefs.values()]
print(f"  alpha: mean={np.mean(alphas):.3f}  std={np.std(alphas):.3f}  "
      f"clipped@0={sum(a==0.0 for a in alphas)}  clipped@2={sum(a==2.0 for a in alphas)}")

rhos = []
for cell, va in val_df.groupby("cell_id"):
    if len(va) < 5:
        continue
    rho, _ = scipy_stats.spearmanr(va["sionna_power_raw"], va["measured_rsrp"])
    if not np.isnan(rho):
        rhos.append(rho)
print(f"  Spearman rho: n={len(rhos)}  median={np.median(rhos):.3f}  "
      f"positive={sum(r>0 for r in rhos)}/{len(rhos)}")

print()
print("=" * 60)
print(f"SUMMARY  pc1  |  {n_tw} towers  |  {len(ols):,} val rows")
print("=" * 60)
print(f"  {'Sionna global offset':<40} {mae_g:>8.3f} dB")
print(f"  {'Per-tower mean (no Sionna)':<40} {mae_tm:>8.3f} dB")
print(f"  {'Per-tower OLS + Sionna RT  [GATE-2]':<40} {mae_ols:>8.3f} dB")

results = {
    "device": "pc1", "operator": 1, "split": "stratified_80_20",
    "sentinel_threshold_dBm": SENTINEL, "sentinel_rows_removed": sents,
    "n_train": int(len(train_df)), "n_val": int(len(val_df)),
    "n_towers": int(n_tw),
    "global_offset_db": float(goff),
    "mae_global_offset": float(mae_g),
    "mae_per_tower_mean": float(mae_tm),
    "mae_per_tower_ols": float(mae_ols),
    "rmse_per_tower_ols": float(rmse_ols),
    "spearman_rho_median": float(np.median(rhos)) if rhos else None,
    "alpha_mean": float(np.mean(alphas)),
    "alpha_std": float(np.std(alphas)),
}
with open(OUT / "pc1_full_results.json", "w") as f:
    json.dump(results, f, indent=2)
ols.to_csv(OUT / "pc1_ols_val_predictions.csv", index=False)
print("Saved.")
