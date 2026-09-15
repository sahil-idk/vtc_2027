"""
A18b_retrain_xgb.py
Re-runs only the ML calibration stage using cached features from A18.
XGBoost now trains on OLS-calibrated residual so it improves ON TOP of OLS.
"""
import json, numpy as np, pandas as pd
from pathlib import Path

DRT_OUT   = Path(__file__).parent / "out" / "dynamic_rt"
NOISE_DBM = -97.0

FEAT_COLS = ['rsrp_raw', 'rsrp_los', 'is_los', 'los_minus_tot',
             'dist_tx_rx_m', 'dist_veh_tx_m', 'dist_veh_rx_m']

def mae_cal(meas, pred):
    offset = float(np.mean(meas - pred))
    return float(np.mean(np.abs(meas - pred - offset))), offset

def rmse_cal(meas, pred):
    offset = float(np.mean(meas - pred))
    return float(np.sqrt(np.mean((meas - pred - offset)**2)))

df_tr = pd.read_csv(DRT_OUT / "features_train.csv")
df_vl = pd.read_csv(DRT_OUT / "features_val.csv")
print(f"Train: {len(df_tr)}  Val: {len(df_vl)}")

# ── Stage 1: per-tower OLS ────────────────────────────────────────────────────
offsets = (df_tr.groupby('cell_eci')
           .apply(lambda g: float(np.mean(g.rsrp_meas - g.rsrp_raw)))
           .to_dict())
global_off = float(np.mean(df_tr.rsrp_meas - df_tr.rsrp_raw))

def apply_ols(df):
    return df.rsrp_raw + df.cell_eci.map(lambda c: offsets.get(c, global_off))

df_tr['rsrp_ols'] = apply_ols(df_tr)
df_vl['rsrp_ols'] = apply_ols(df_vl)

ols_mae, ols_off = mae_cal(df_vl.rsrp_meas.values, df_vl.rsrp_ols.values)
ols_rmse = rmse_cal(df_vl.rsrp_meas.values, df_vl.rsrp_ols.values)
print(f"OLS  MAE={ols_mae:.3f} dB  RMSE={ols_rmse:.3f} dB  bias={ols_off:.2f} dB")

# ── Stage 2: XGBoost on OLS residual ─────────────────────────────────────────
from xgboost import XGBRegressor

X_tr = df_tr[FEAT_COLS].values.astype(float)
y_tr = (df_tr.rsrp_meas - df_tr.rsrp_ols).values   # residual AFTER OLS

model = XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.04,
                     subsample=0.8, colsample_bytree=0.8,
                     random_state=42, n_jobs=-1)
model.fit(X_tr, y_tr)

X_vl = df_vl[FEAT_COLS].values.astype(float)
df_vl['rsrp_xgb2'] = df_vl.rsrp_ols + model.predict(X_vl)

xgb_mae,  xgb_off  = mae_cal(df_vl.rsrp_meas.values, df_vl.rsrp_xgb2.values)
xgb_rmse = rmse_cal(df_vl.rsrp_meas.values, df_vl.rsrp_xgb2.values)
print(f"XGB2 MAE={xgb_mae:.3f} dB  RMSE={xgb_rmse:.3f} dB  bias={xgb_off:.2f} dB")

imp = dict(zip(FEAT_COLS, model.feature_importances_))
print(f"Feature importances: {imp}")

# LOS / NLOS breakdown
los = df_vl.is_los.values.astype(bool)
if los.sum() > 5:
    xgb_mae_los,  _ = mae_cal(df_vl.rsrp_meas[los].values,  df_vl.rsrp_xgb2[los].values)
    ols_mae_los,  _ = mae_cal(df_vl.rsrp_meas[los].values,  df_vl.rsrp_ols[los].values)
    print(f"LOS  OLS={ols_mae_los:.3f} dB  XGB={xgb_mae_los:.3f} dB")
if (~los).sum() > 5:
    xgb_mae_nlos, _ = mae_cal(df_vl.rsrp_meas[~los].values, df_vl.rsrp_xgb2[~los].values)
    ols_mae_nlos, _ = mae_cal(df_vl.rsrp_meas[~los].values, df_vl.rsrp_ols[~los].values)
    print(f"NLOS OLS={ols_mae_nlos:.3f} dB  XGB={xgb_mae_nlos:.3f} dB")

# SNR MAE
snr_v = df_vl.snr_meas.notna().values
if snr_v.sum() > 5:
    snr_sim  = df_vl.rsrp_xgb2.values - NOISE_DBM
    snr_m    = df_vl.snr_meas.values
    snr_mae, _ = mae_cal(snr_m[snr_v], snr_sim[snr_v])
    print(f"SNR MAE (vs SINR, XGB): {snr_mae:.3f} dB")
    snr_sim_ols = df_vl.rsrp_ols.values - NOISE_DBM
    snr_mae_ols, _ = mae_cal(snr_m[snr_v], snr_sim_ols[snr_v])
    print(f"SNR MAE (vs SINR, OLS): {snr_mae_ols:.3f} dB")

# Save
df_vl.to_csv(DRT_OUT / "val_predictions_ml2.csv", index=False)
summary = {
    'val_rows': len(df_vl),
    'train_rows': len(df_tr),
    'los_fraction_val': float(los.mean()),
    'raw_sionna_mae': float(mae_cal(df_vl.rsrp_meas.values, df_vl.rsrp_raw.values)[0]),
    'ols_mae': ols_mae, 'ols_rmse': ols_rmse,
    'xgb_ols_residual_mae': xgb_mae, 'xgb_ols_residual_rmse': xgb_rmse,
    'xgb_mae_los':  float(xgb_mae_los)  if los.sum() > 5  else None,
    'xgb_mae_nlos': float(xgb_mae_nlos) if (~los).sum() > 5 else None,
    'snr_mae_xgb': float(snr_mae) if snr_v.sum() > 5 else None,
    'snr_mae_ols': float(snr_mae_ols) if snr_v.sum() > 5 else None,
}
with open(DRT_OUT / "ml_summary2.json", "w") as f:
    json.dump(summary, f, indent=2)
print(f"\nSaved → {DRT_OUT}/ml_summary2.json")
print(json.dumps(summary, indent=2))
