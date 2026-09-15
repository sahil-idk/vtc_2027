"""
A18c_nlos_approaches.py
=======================
Uses cached features_train.csv / features_val.csv (no Sionna re-run needed).

NLOS challenge: Sionna rsrp_raw ≈ -150 dBm for ALL NLOS rows (noise floor),
so that feature carries zero information for NLOS prediction.

Five approaches compared:
  A  OLS only (baseline)
  B  Conditional: OLS (LOS) + log-distance path-loss (NLOS)
  C  Conditional: OLS (LOS) + XGBoost on geometry only (NLOS)
  D  Global XGBoost with NLOS rows upweighted 7x
  E  Neural net (small MLP) with balanced class sampling
"""
import json, numpy as np, pandas as pd
from pathlib import Path

DRT_OUT   = Path(__file__).parent / "out" / "dynamic_rt"
NOISE_DBM = -97.0

df_tr = pd.read_csv(DRT_OUT / "features_train.csv")
df_vl = pd.read_csv(DRT_OUT / "features_val.csv")
print(f"Train: {len(df_tr)}  Val: {len(df_vl)}")

los_tr  = df_tr.is_los.values.astype(bool)
los_vl  = df_vl.is_los.values.astype(bool)
nlos_tr = ~los_tr;  nlos_vl = ~los_vl

print(f"  Train  LOS={los_tr.sum()}  NLOS={nlos_tr.sum()}")
print(f"  Val    LOS={los_vl.sum()}  NLOS={nlos_vl.sum()}")

# ── Helper ─────────────────────────────────────────────────────────────────────
def mae_cal(meas, pred):
    if len(meas) == 0: return np.nan, np.nan
    offset = float(np.mean(meas - pred))
    return float(np.mean(np.abs(meas - pred - offset))), offset

def report(name, pred_all, meas_all, los_mask):
    overall, _ = mae_cal(meas_all, pred_all)
    los_mae, _ = mae_cal(meas_all[los_mask], pred_all[los_mask])
    nlos_mae, _= mae_cal(meas_all[~los_mask], pred_all[~los_mask])
    print(f"  {name:<35} overall={overall:.3f} dB  LOS={los_mae:.3f} dB  NLOS={nlos_mae:.3f} dB")
    return {'name': name, 'overall': overall, 'los': los_mae, 'nlos': nlos_mae}

# ── Per-tower OLS offset ───────────────────────────────────────────────────────
offsets = (df_tr.groupby('cell_eci')[['rsrp_meas','rsrp_raw']]
           .apply(lambda g: float(np.mean(g.rsrp_meas - g.rsrp_raw)),
                  include_groups=False)
           .to_dict())
global_off = float(np.mean(df_tr.rsrp_meas - df_tr.rsrp_raw))

def apply_ols(df):
    return df.rsrp_raw.values + np.array([
        offsets.get(c, global_off) for c in df.cell_eci])

all_results = []
print("\n" + "="*70)

# ── A: OLS baseline ───────────────────────────────────────────────────────────
pred_ols = apply_ols(df_vl)
all_results.append(report("A: OLS baseline", pred_ols,
                           df_vl.rsrp_meas.values, los_vl))

# ── B: OLS (LOS) + log-distance path loss (NLOS) ─────────────────────────────
# For NLOS: RSRP ≈ a * log10(dist) + per_tower_mean
# Fit on NLOS training rows
from sklearn.linear_model import Ridge

nlos_tr_df = df_tr[nlos_tr].copy()
nlos_vl_df = df_vl[nlos_vl].copy()

# Fill NaN distances with column median
for col in ['dist_tx_rx_m', 'dist_veh_tx_m', 'dist_veh_rx_m']:
    med = df_tr[col].median()
    nlos_tr_df[col] = nlos_tr_df[col].fillna(med)
    nlos_vl_df[col] = nlos_vl_df[col].fillna(med)
    df_tr[col]      = df_tr[col].fillna(med)
    df_vl[col]      = df_vl[col].fillna(med)

# Per-tower NLOS mean offset (shift) + global slope on log10(dist)
X_nlos_tr = np.log10(np.maximum(nlos_tr_df.dist_tx_rx_m.values, 1.0)).reshape(-1,1)
y_nlos_tr = nlos_tr_df.rsrp_meas.values

# Add per-tower dummies for offset
from sklearn.preprocessing import OneHotEncoder
enc = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
tower_dummies_tr = enc.fit_transform(nlos_tr_df[['cell_eci']])
tower_dummies_vl = enc.transform(nlos_vl_df[['cell_eci']])

X_nlos_tr_full = np.hstack([X_nlos_tr, tower_dummies_tr])
X_nlos_vl_full = np.hstack([
    np.log10(np.maximum(nlos_vl_df.dist_tx_rx_m.values, 1.0)).reshape(-1,1),
    tower_dummies_vl
])

nlos_pl_model = Ridge(alpha=1.0)
nlos_pl_model.fit(X_nlos_tr_full, y_nlos_tr)
print(f"  [B] log-distance slope = {nlos_pl_model.coef_[0]:.2f} dB/decade")

pred_B = pred_ols.copy()
pred_B[nlos_vl] = nlos_pl_model.predict(X_nlos_vl_full)
all_results.append(report("B: OLS(LOS) + log-dist(NLOS)", pred_B,
                           df_vl.rsrp_meas.values, los_vl))

# ── C: OLS (LOS) + XGBoost geometry-only (NLOS) ──────────────────────────────
from xgboost import XGBRegressor

NLOS_FEAT = ['dist_tx_rx_m', 'dist_veh_tx_m', 'dist_veh_rx_m']

X_nc_tr = nlos_tr_df[NLOS_FEAT].values.astype(float)
y_nc_tr = nlos_tr_df.rsrp_meas.values

xgb_nlos = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.04,
                         subsample=0.8, colsample_bytree=0.8,
                         random_state=42, n_jobs=-1)
xgb_nlos.fit(X_nc_tr, y_nc_tr)

X_nc_vl = nlos_vl_df[NLOS_FEAT].values.astype(float)
pred_C = pred_ols.copy()
pred_C[nlos_vl] = xgb_nlos.predict(X_nc_vl)
all_results.append(report("C: OLS(LOS) + XGB-geom(NLOS)", pred_C,
                           df_vl.rsrp_meas.values, los_vl))

# ── D: Global XGBoost with NLOS upweighted 7x ────────────────────────────────
ALL_FEAT = ['rsrp_raw', 'rsrp_los', 'is_los', 'los_minus_tot',
            'dist_tx_rx_m', 'dist_veh_tx_m', 'dist_veh_rx_m']
NLOS_WEIGHT = 7.0

sample_weights = np.where(nlos_tr, NLOS_WEIGHT, 1.0)
X_all_tr = df_tr[ALL_FEAT].values.astype(float)
y_all_tr = df_tr.rsrp_meas.values

xgb_weighted = XGBRegressor(n_estimators=300, max_depth=5, learning_rate=0.04,
                              subsample=0.8, colsample_bytree=0.8,
                              random_state=42, n_jobs=-1)
xgb_weighted.fit(X_all_tr, y_all_tr, sample_weight=sample_weights)

X_all_vl = df_vl[ALL_FEAT].values.astype(float)
pred_D = xgb_weighted.predict(X_all_vl)
all_results.append(report("D: XGB global + NLOS weight×7", pred_D,
                           df_vl.rsrp_meas.values, los_vl))

# ── E: sklearn MLP + Random Forest (NLOS upweighted) ─────────────────────────
from sklearn.neural_network import MLPRegressor
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

scaler = StandardScaler()
X_sc_tr = scaler.fit_transform(df_tr[ALL_FEAT].values.astype(float))
X_sc_vl = scaler.transform(df_vl[ALL_FEAT].values.astype(float))

mlp = MLPRegressor(hidden_layer_sizes=(128, 128, 64), activation='relu',
                   max_iter=300, random_state=42, learning_rate_init=1e-3,
                   early_stopping=True, validation_fraction=0.1, n_iter_no_change=20)
mlp.fit(X_sc_tr, y_all_tr, sample_weight=sample_weights)
pred_E_mlp = mlp.predict(X_sc_vl)
all_results.append(report("E1: MLP sklearn + NLOS wt×7", pred_E_mlp,
                           df_vl.rsrp_meas.values, los_vl))

rf = RandomForestRegressor(n_estimators=300, max_depth=8, random_state=42, n_jobs=-1)
rf.fit(X_all_tr, y_all_tr, sample_weight=sample_weights)
pred_E_rf = rf.predict(X_all_vl)
all_results.append(report("E2: RandomForest + NLOS wt×7", pred_E_rf,
                           df_vl.rsrp_meas.values, los_vl))

# ── F: Best conditional — OLS(LOS) + log-dist(NLOS) with nn correction ───────
# Use log-dist predictions for NLOS, then add XGB correction on log-dist error
y_nlos_ols_pred   = nlos_pl_model.predict(X_nlos_tr_full)
y_nlos_ols_resid  = nlos_tr_df.rsrp_meas.values - y_nlos_ols_pred

xgb_nlos_resid = XGBRegressor(n_estimators=300, max_depth=4, learning_rate=0.04,
                                subsample=0.8, random_state=42, n_jobs=-1)
xgb_nlos_resid.fit(X_nlos_tr_full, y_nlos_ols_resid)

pred_F = pred_B.copy()  # start from log-dist NLOS predictions
nlos_resid_pred = xgb_nlos_resid.predict(X_nlos_vl_full)
pred_F[nlos_vl] = pred_F[nlos_vl] + nlos_resid_pred
all_results.append(report("F: OLS(LOS) + log-dist+XGB(NLOS)", pred_F,
                           df_vl.rsrp_meas.values, los_vl))

# ── Summary table ──────────────────────────────────────────────────────────────
print("\n" + "="*70)
print(f"{'Method':<40} {'Overall':>8} {'LOS':>8} {'NLOS':>8}")
print("-"*70)
for r in all_results:
    print(f"  {r['name']:<38} {r['overall']:>7.3f}  {r['los']:>7.3f}  {r['nlos']:>7.3f}")
print("="*70)

# Save
with open(DRT_OUT / "nlos_approaches.json", "w") as f:
    json.dump(all_results, f, indent=2)
print(f"Saved → {DRT_OUT}/nlos_approaches.json")
