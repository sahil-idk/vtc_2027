"""
A18d_loto_cv.py  —  Leave-One-Tower-Out cross-validation
=========================================================
Uses CACHED Sionna features (no re-run needed).

For each of the 49 val towers:
  - Training set: all training-feature rows EXCLUDING that tower
  - Test set    : that tower's val rows
  - Method F applied: OLS(LOS) + log-dist+XGB(NLOS)

This tests genuine generalisation — if a tower was never seen in training,
can the model still predict its RSRP?

Also runs nested method comparison inside each fold to check if
Method F is consistently the best (or just lucky on the Jun-24 val set).
"""
import json, numpy as np, pandas as pd
from pathlib import Path
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

DRT_OUT = Path(__file__).parent / "out" / "dynamic_rt"
NOISE   = -97.0

df_tr = pd.read_csv(DRT_OUT / "features_train.csv")
df_vl = pd.read_csv(DRT_OUT / "features_val.csv")

# Fill NaN distances
for col in ['dist_tx_rx_m', 'dist_veh_tx_m', 'dist_veh_rx_m']:
    med = df_tr[col].median()
    df_tr[col] = df_tr[col].fillna(med)
    df_vl[col] = df_vl[col].fillna(med)

NLOS_FEAT = ['dist_tx_rx_m', 'dist_veh_tx_m', 'dist_veh_rx_m']
ALL_FEAT  = ['rsrp_raw', 'rsrp_los', 'is_los', 'los_minus_tot',
             'dist_tx_rx_m', 'dist_veh_tx_m', 'dist_veh_rx_m']

def mae_cal(meas, pred):
    if len(meas) < 2: return np.nan
    return float(np.mean(np.abs(meas - pred - np.mean(meas - pred))))

def method_A_ols(tr, vl):
    off = tr.groupby('cell_eci')[['rsrp_meas','rsrp_raw']].apply(
        lambda g: float(np.mean(g.rsrp_meas - g.rsrp_raw)), include_groups=False).to_dict()
    glob = float(np.mean(tr.rsrp_meas - tr.rsrp_raw))
    pred = vl.rsrp_raw.values + np.array([off.get(c, glob) for c in vl.cell_eci])
    return pred

def method_F(tr, vl):
    """OLS for LOS, log-dist+XGB for NLOS."""
    # LOS part
    pred = method_A_ols(tr, vl).copy()

    nlos_tr = tr[~tr.is_los.astype(bool)].copy()
    nlos_vl = vl[~vl.is_los.astype(bool)].copy()

    if len(nlos_vl) == 0:
        return pred

    if len(nlos_tr) < 5:
        # fallback: global mean for NLOS
        pred[~vl.is_los.values.astype(bool)] = float(np.mean(tr.rsrp_meas))
        return pred

    # Build per-tower dummies — fit on available NLOS towers
    enc = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    td_tr = enc.fit_transform(nlos_tr[['cell_eci']])
    td_vl = enc.transform(nlos_vl[['cell_eci']])

    log_d_tr = np.log10(np.maximum(nlos_tr.dist_tx_rx_m.values, 1.0)).reshape(-1,1)
    log_d_vl = np.log10(np.maximum(nlos_vl.dist_tx_rx_m.values, 1.0)).reshape(-1,1)

    X_tr_nlos = np.hstack([log_d_tr, td_tr])
    X_vl_nlos = np.hstack([log_d_vl, td_vl])

    pl = Ridge(alpha=1.0)
    pl.fit(X_tr_nlos, nlos_tr.rsrp_meas.values)
    nlos_pred_pl = pl.predict(X_vl_nlos)

    # XGB residual correction
    y_resid = nlos_tr.rsrp_meas.values - pl.predict(X_tr_nlos)
    if len(nlos_tr) >= 10:
        xgb = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                           random_state=42, n_jobs=-1, verbosity=0)
        xgb.fit(X_tr_nlos, y_resid)
        nlos_pred_pl = nlos_pred_pl + xgb.predict(X_vl_nlos)

    idx_nlos = np.where(~vl.is_los.values.astype(bool))[0]
    pred[idx_nlos] = nlos_pred_pl
    return pred

# ── LOTO loop ─────────────────────────────────────────────────────────────────
val_towers = df_vl.cell_eci.unique()
print(f"LOTO CV over {len(val_towers)} towers  "
      f"(train={len(df_tr)} rows, val={len(df_vl)} rows)")
print("="*65)

loto_records = []
all_preds_F   = np.full(len(df_vl), np.nan)
all_preds_OLS = np.full(len(df_vl), np.nan)

for i, tower in enumerate(val_towers):
    # Hold out this tower from training
    tr_fold = df_tr[df_tr.cell_eci != tower].copy()
    vl_fold = df_vl[df_vl.cell_eci == tower].copy()
    vl_idx  = df_vl.index[df_vl.cell_eci == tower].tolist()

    if len(vl_fold) == 0:
        continue

    pred_ols = method_A_ols(tr_fold, vl_fold)
    pred_f   = method_F(tr_fold, vl_fold)

    mae_ols = mae_cal(vl_fold.rsrp_meas.values, pred_ols)
    mae_f   = mae_cal(vl_fold.rsrp_meas.values, pred_f)

    los_frac = float(vl_fold.is_los.mean())
    n_nlos   = int((~vl_fold.is_los.astype(bool)).sum())

    print(f"  [{i+1:2d}/{len(val_towers)}] tower={tower}  "
          f"n={len(vl_fold):3d}  LOS={los_frac*100:.0f}%  "
          f"OLS={mae_ols:.2f}dB  F={mae_f:.2f}dB")

    loto_records.append({
        'cell_eci': int(tower), 'n_val': len(vl_fold), 'los_frac': los_frac,
        'n_nlos': n_nlos, 'mae_ols_loto': mae_ols, 'mae_F_loto': mae_f,
        'seen_in_train': int(tower in df_tr.cell_eci.values)
    })

    for j, vi in enumerate(vl_idx):
        all_preds_F[df_vl.index.get_loc(vi)]   = pred_f[j]
        all_preds_OLS[df_vl.index.get_loc(vi)] = pred_ols[j]

df_res = pd.DataFrame(loto_records)
print()

# Global LOTO metrics (aggregate all out-of-fold predictions)
valid = ~np.isnan(all_preds_F)
meas  = df_vl.rsrp_meas.values
los   = df_vl.is_los.values.astype(bool)

loto_ols_overall = mae_cal(meas[valid], all_preds_OLS[valid])
loto_F_overall   = mae_cal(meas[valid], all_preds_F[valid])
loto_F_los       = mae_cal(meas[valid & los],  all_preds_F[valid & los])
loto_F_nlos      = mae_cal(meas[valid & ~los], all_preds_F[valid & ~los])
loto_ols_los     = mae_cal(meas[valid & los],  all_preds_OLS[valid & los])
loto_ols_nlos    = mae_cal(meas[valid & ~los], all_preds_OLS[valid & ~los])

print("="*65)
print("LOTO RESULTS  (tower held out of training for each fold)")
print(f"  OLS  overall={loto_ols_overall:.3f} dB  "
      f"LOS={loto_ols_los:.3f} dB  NLOS={loto_ols_nlos:.3f} dB")
print(f"  F    overall={loto_F_overall:.3f} dB  "
      f"LOS={loto_F_los:.3f} dB  NLOS={loto_F_nlos:.3f} dB")
print()

# Compare to within-deployment results (from A18c)
print("COMPARISON: within-deployment (A18c) vs LOTO")
print(f"  {'Method':<20} {'Within-deploy':>15} {'LOTO (unbiased)':>16}")
print(f"  {'OLS overall':<20} {'5.230 dB':>15} {loto_ols_overall:>15.3f} dB")
print(f"  {'Method-F overall':<20} {'3.055 dB':>15} {loto_F_overall:>15.3f} dB")
print(f"  {'Method-F LOS':<20} {'2.985 dB':>15} {loto_F_los:>15.3f} dB")
print(f"  {'Method-F NLOS':<20} {'3.500 dB':>15} {loto_F_nlos:>15.3f} dB")
print("="*65)

# Per-tower breakdown
df_res.to_csv(DRT_OUT / "loto_per_tower.csv", index=False)
summary = {
    'loto_ols_overall': loto_ols_overall, 'loto_ols_los': loto_ols_los,
    'loto_ols_nlos': loto_ols_nlos,
    'loto_F_overall': loto_F_overall, 'loto_F_los': loto_F_los,
    'loto_F_nlos': loto_F_nlos,
    'within_deploy_F_overall': 3.055, 'within_deploy_F_los': 2.985,
    'within_deploy_F_nlos': 3.500,
    'n_towers': len(val_towers), 'n_val_rows': int(valid.sum())
}
with open(DRT_OUT / "loto_summary.json", "w") as f:
    json.dump(summary, f, indent=2)
print(f"Saved → {DRT_OUT}/loto_summary.json")
