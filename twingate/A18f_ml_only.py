"""
A18f_ml_only.py  —  ML fitting on cached Fold-1 tower features
===============================================================
No Sionna/mitsuba imports. Reads tower_cache CSVs directly,
assembles train/val DataFrames, applies Method F, saves results.
"""
import json, numpy as np, pandas as pd
from pathlib import Path
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

FOLD1_OUT = Path(__file__).parent / "out" / "dynamic_rt" / "fold1"
CACHE_DIR = FOLD1_OUT / "tower_cache"

# ── Load cached features ───────────────────────────────────────────────────────
train_files = sorted(CACHE_DIR.glob("train_*.csv"))
val_files   = sorted(CACHE_DIR.glob("val_*.csv"))

print(f"Cache: {len(train_files)} train towers, {len(val_files)} val towers")

df_tr = pd.concat([pd.read_csv(f) for f in train_files], ignore_index=True)
df_vl = pd.concat([pd.read_csv(f) for f in val_files],   ignore_index=True)

print(f"Loaded: {len(df_tr)} train rows, {len(df_vl)} val rows")

# ── Fill NaN distances ─────────────────────────────────────────────────────────
for col in ['dist_tx_rx_m', 'dist_veh_tx_m', 'dist_veh_rx_m']:
    med = df_tr[col].median()
    df_tr[col] = df_tr[col].fillna(med)
    df_vl[col] = df_vl[col].fillna(med)

# ── Coerce types ───────────────────────────────────────────────────────────────
df_tr['is_los'] = df_tr['is_los'].astype(str).str.lower().isin(['true','1'])
df_vl['is_los'] = df_vl['is_los'].astype(str).str.lower().isin(['true','1'])
df_tr['cell_eci'] = df_tr['cell_eci'].astype(int)
df_vl['cell_eci'] = df_vl['cell_eci'].astype(int)

# ── Method F ───────────────────────────────────────────────────────────────────
def mae_cal(meas, pred):
    if len(meas) < 2: return np.nan
    return float(np.mean(np.abs(meas - pred - np.mean(meas - pred))))

def method_F(tr, vl):
    # LOS: per-tower OLS offset
    off = tr.groupby('cell_eci')[['rsrp_meas','rsrp_raw']].apply(
        lambda g: float(np.mean(g['rsrp_meas'] - g['rsrp_raw'])),
        include_groups=False).to_dict()
    glob = float(np.mean(tr.rsrp_meas - tr.rsrp_raw))
    pred = vl.rsrp_raw.values + np.array([off.get(c, glob) for c in vl.cell_eci])

    # NLOS: log-distance + per-tower Ridge + XGB residual
    nlos_tr = tr[~tr.is_los].copy()
    nlos_vl = vl[~vl.is_los].copy()

    if len(nlos_vl) == 0:
        return pred

    if len(nlos_tr) < 5:
        pred[~vl.is_los.values] = float(np.mean(tr.rsrp_meas))
        return pred

    enc = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
    td_tr = enc.fit_transform(nlos_tr[['cell_eci']])
    td_vl = enc.transform(nlos_vl[['cell_eci']])

    log_d_tr = np.log10(np.maximum(nlos_tr.dist_tx_rx_m.values, 1.0)).reshape(-1,1)
    log_d_vl = np.log10(np.maximum(nlos_vl.dist_tx_rx_m.values, 1.0)).reshape(-1,1)

    X_tr = np.hstack([log_d_tr, td_tr])
    X_vl = np.hstack([log_d_vl, td_vl])

    pl = Ridge(alpha=1.0)
    pl.fit(X_tr, nlos_tr.rsrp_meas.values)
    nlos_pred = pl.predict(X_vl)

    y_resid = nlos_tr.rsrp_meas.values - pl.predict(X_tr)
    if len(nlos_tr) >= 10:
        xgb = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                           random_state=42, n_jobs=-1, verbosity=0)
        xgb.fit(X_tr, y_resid)
        nlos_pred = nlos_pred + xgb.predict(X_vl)

    idx_nlos = np.where(~vl.is_los.values)[0]
    pred[idx_nlos] = nlos_pred
    return pred

# ── Evaluate ───────────────────────────────────────────────────────────────────
print("\nFitting Method F ...")
pred = method_F(df_tr.copy(), df_vl.copy())
meas = df_vl.rsrp_meas.values
los  = df_vl.is_los.values

res = {
    'fold': 1, 'train_date': '2021-06-22', 'val_date': '2021-06-23',
    'n_train': len(df_tr), 'n_val': len(df_vl),
    'los_frac': float(los.mean()),
    'mae_overall': mae_cal(meas,        pred),
    'mae_los':     mae_cal(meas[los],   pred[los]),
    'mae_nlos':    mae_cal(meas[~los],  pred[~los]),
}

print("\n" + "="*65)
print(f"FOLD 1 RESULTS  (Method F, trained Jun-22, evaluated Jun-23)")
print(f"  Train rows  : {res['n_train']}  (50/tower, Jun-22)")
print(f"  Val rows    : {res['n_val']}  LOS={res['los_frac']*100:.1f}%")
print(f"  Overall MAE : {res['mae_overall']:.3f} dB")
print(f"  LOS MAE     : {res['mae_los']:.3f} dB")
print(f"  NLOS MAE    : {res['mae_nlos']:.3f} dB")
print("="*65)

print("\nCROSS-FOLD SUMMARY (Method F):")
print(f"  Fold 1 (Jun23 val, unbiased)  : {res['mae_overall']:.3f} dB")
print(f"  Fold 2 (Jun24 val, method sel): 3.055 dB")
print(f"  LOTO   (zero-shot towers)     : 12.250 dB")

# Save
df_vl_out = df_vl.copy()
df_vl_out['pred_F'] = pred
df_vl_out.to_csv(FOLD1_OUT / "val_predictions_fold1.csv", index=False)

with open(FOLD1_OUT / "fold1_summary.json", "w") as f:
    json.dump(res, f, indent=2)

print(f"\nSaved → {FOLD1_OUT}/fold1_summary.json")
print(f"Saved → {FOLD1_OUT}/val_predictions_fold1.csv")
