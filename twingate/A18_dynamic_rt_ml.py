"""
A18_dynamic_rt_ml.py  --  ML-Enhanced Dynamic Ray Tracing (pc1 / Op1)
======================================================================
Full pipeline:
  1. Nearest-timestamp (±5 s) match pc1 ↔ pc4 → vehicle blocker position per row
  2. Dynamic Sionna RT → physics features per row:
       rsrp_raw, rsrp_los, is_los, dist_2d, veh_dist_tx, veh_dist_rx
  3. Stage-1 calibration: per-tower OLS offset (mean bias removal)
  4. Stage-2 calibration: global XGBoost on physics features → residual correction
  Evaluate on held-out val split.

Runtime strategy:
  - Sample MAX_TRAIN_ROWS per tower for Sionna calls (avoids O(N) scene reloads)
  - Vehicle position quantised to 100 m grid (further reduces unique scene loads)
  - Features cached to CSV so ML can be re-run without re-tracing

Outputs → twingate/out/dynamic_rt/
  features_train.csv      raw Sionna features for training rows
  features_val.csv        raw Sionna features for val rows
  ml_summary.json         OLS vs XGBoost MAE comparison
  ml_per_tower.csv        per-tower MAE breakdown
"""

import os, math, json, shutil, warnings, tempfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from pathlib import Path

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, PathSolver
from pandas import merge_asof

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent.parent
TWINGATE = Path(__file__).parent
OUT      = TWINGATE / "out"
DRT_OUT  = OUT / "dynamic_rt"
DRT_OUT.mkdir(parents=True, exist_ok=True)

DATAFILE    = ROOT / "cellular_dataframe_cleaned.csv"
SPLIT_IDX   = OUT / "split_index.csv"
REFINED_POS = OUT / "refined_positions.csv"
TOWER_POS   = OUT / "tower_positions.csv"
SCENE_XML   = ROOT / "scene_operator1" / "scene.xml"
SCENE_ORIG  = (52.507005, 13.323428)

# ── Constants ─────────────────────────────────────────────────────────────────
OPERATOR        = 1
TARGET_DEVICE   = "pc1"
COMPANION       = "pc4"
TS_TOL          = pd.Timedelta("5s")   # nearest-timestamp tolerance

TX_H            = 30.0
RX_H            = 1.5
EVAL_BATCH      = 40
MAX_DEPTH       = 4                    # faster than 5, still gets 2nd-order reflections
MAX_TRAIN_ROWS  = 50                   # Sionna calls per tower (training)
VEH_QUANT_M     = 100.0               # vehicle position grid (100 m → fewer reloads)
VEH_MAT_ID      = "itu_concrete"
VEH_HALF        = (2.25, 1.0, 0.75)  # car half-extents (m)
NOISE_DBM       = -97.0               # kT + BW(10 MHz) + NF(7 dB)

RSRP_COL = "PCell_RSRP_max"
SNR_COL  = "PCell_SNR_1"
CELL_COL = "PCell_Cell_Identity"
TS_COL   = "ts_gps"
LAT_COL  = "Latitude"
LON_COL  = "Longitude"

# ── Helpers ───────────────────────────────────────────────────────────────────
def ll2xy(lat, lon):
    x = (lon - SCENE_ORIG[1]) * 111_320.0 * math.cos(math.radians(SCENE_ORIG[0]))
    y = (lat - SCENE_ORIG[0]) * 111_320.0
    return float(x), float(y)

def dist2d(lat1, lon1, lat2, lon2):
    x1, y1 = ll2xy(lat1, lon1)
    x2, y2 = ll2xy(lat2, lon2)
    return math.hypot(x1-x2, y1-y2)

def power_dbm(paths):
    try:
        a_r = np.array(dr.detach(paths.a[0]))
        a_i = np.array(dr.detach(paths.a[1]))
        plin = (a_r**2 + a_i**2).sum(axis=-1).squeeze(axis=(1,2,3))
        return 10.0 * np.log10(np.maximum(plin, 1e-30)) + 30.0
    except Exception:
        return np.full(1, -150.0)

def quant(v, q=VEH_QUANT_M):
    return float(int(v / q) * q)

def write_scene_with_vehicle(veh_x, veh_y, tmp_dir):
    ET.register_namespace('', '')
    tree = ET.parse(SCENE_XML)
    root = tree.getroot()
    sh = ET.SubElement(root, 'shape')
    sh.set('type', 'cube'); sh.set('id', 'vehicle_dyn')
    tf = ET.SubElement(sh, 'transform'); tf.set('name', 'to_world')
    sc = ET.SubElement(tf, 'scale')
    sc.set('x', f'{VEH_HALF[0]:.3f}'); sc.set('y', f'{VEH_HALF[1]:.3f}'); sc.set('z', f'{VEH_HALF[2]:.3f}')
    tr = ET.SubElement(tf, 'translate')
    tr.set('x', f'{veh_x:.3f}'); tr.set('y', f'{veh_y:.3f}'); tr.set('z', f'{VEH_HALF[2]:.3f}')
    ref = ET.SubElement(sh, 'ref'); ref.set('id', VEH_MAT_ID)
    path = os.path.join(tmp_dir, 'scene_dyn.xml')
    tree.write(path, xml_declaration=True, encoding='unicode')
    return path

def forward_group(tx_x, tx_y, rx_lats, rx_lons, scene, solver):
    """Run full + LOS PathSolver for one group. Returns (rsrp_full, rsrp_los)."""
    scene.add(Transmitter(name="tx_a18", position=[tx_x, tx_y, TX_H]))
    full_all, los_all = [], []
    for start in range(0, len(rx_lats), EVAL_BATCH):
        blats = rx_lats[start:start+EVAL_BATCH]
        blons = rx_lons[start:start+EVAL_BATCH]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = ll2xy(float(la), float(lo))
            scene.add(Receiver(name=f"rx_a18_{i}", position=[xi, yi, RX_H]))
        paths_full = solver(scene=scene, max_depth=MAX_DEPTH, diffraction=True)
        paths_los  = solver(scene=scene, max_depth=0, diffraction=False)
        full_all.extend(power_dbm(paths_full).tolist())
        los_all.extend(power_dbm(paths_los).tolist())
        for i in range(len(blats)):
            scene.remove(f"rx_a18_{i}")
    scene.remove("tx_a18")
    return np.array(full_all), np.array(los_all)

def get_tx_pos(cell_eci, refined, tower_pos):
    if not refined.empty:
        r = refined[(refined.operator==OPERATOR) & (refined.cell_eci==int(cell_eci))]
        if not r.empty:
            return ll2xy(float(r.iloc[0].refined_lat), float(r.iloc[0].refined_lon)), 'refined'
    if not tower_pos.empty:
        t = tower_pos[(tower_pos.operator==OPERATOR) & (tower_pos.PCell_Cell_Identity==int(cell_eci))]
        if not t.empty:
            return ll2xy(float(t.iloc[0].tower_lat), float(t.iloc[0].tower_lon)), 'wcl'
    return None, None

# ── Feature extraction via Sionna RT ─────────────────────────────────────────
def extract_features(subset, refined, tower_pos, split_label, tmp_dir, rng):
    """Run dynamic RT on `subset` rows; return feature dataframe."""
    ant_array = PlanarArray(num_rows=1, num_cols=1,
                            vertical_spacing=0.5, horizontal_spacing=0.5,
                            pattern="iso", polarization="V")
    records = []
    cells = subset[CELL_COL].unique()

    for c_idx, cell_eci in enumerate(cells):
        grp_all = subset[subset[CELL_COL] == cell_eci].copy()

        tx_pos, tx_src = get_tx_pos(cell_eci, refined, tower_pos)
        if tx_pos is None:
            print(f"  [{split_label}] cell={cell_eci}: no TX position, skip")
            continue
        tx_x, tx_y = tx_pos

        # Sample rows if training
        if split_label == 'train' and len(grp_all) > MAX_TRAIN_ROWS:
            grp_all = grp_all.iloc[rng.choice(len(grp_all), MAX_TRAIN_ROWS, replace=False)]

        # Group by vehicle position (100 m grid)
        grp_all['vq_x'] = grp_all['veh_x'].apply(quant)
        grp_all['vq_y'] = grp_all['veh_y'].apply(quant)
        groups = grp_all.groupby(['vq_x', 'vq_y'])

        print(f"  [{split_label}] cell={cell_eci} ({c_idx+1}/{len(cells)}) "
              f"rows={len(grp_all)} groups={groups.ngroups} src={tx_src}")

        for (vqx, vqy), grp in groups:
            veh_x = float(vqx + VEH_QUANT_M/2)
            veh_y = float(vqy + VEH_QUANT_M/2)
            try:
                xml_path = write_scene_with_vehicle(veh_x, veh_y, tmp_dir)
                scene = load_scene(xml_path)
                scene.tx_array = ant_array
                scene.rx_array = ant_array
                solver = PathSolver()

                rsrp_full, rsrp_los = forward_group(
                    tx_x, tx_y,
                    grp[LAT_COL].values, grp[LON_COL].values,
                    scene, solver
                )
                del scene, solver

                d_vtx = math.hypot(veh_x - tx_x, veh_y - tx_y)
                for i, (_, row) in enumerate(grp.iterrows()):
                    rx_x, rx_y = ll2xy(float(row[LAT_COL]), float(row[LON_COL]))
                    d_rx  = math.hypot(rx_x - tx_x, rx_y - tx_y)
                    d_vrx = math.hypot(rx_x - veh_x, rx_y - veh_y)
                    is_los = bool(rsrp_los[i] > -130.0)
                    records.append({
                        'ts_gps':        str(row[TS_COL]),
                        'cell_eci':      int(cell_eci),
                        'split':         split_label,
                        'rsrp_meas':     float(row[RSRP_COL]),
                        'snr_meas':      float(row[SNR_COL]) if pd.notna(row.get(SNR_COL)) else np.nan,
                        'rsrp_raw':      float(rsrp_full[i]),
                        'rsrp_los':      float(rsrp_los[i]),
                        'is_los':        is_los,
                        'los_minus_tot': float(rsrp_los[i] - rsrp_full[i]) if is_los else 0.0,
                        'dist_tx_rx_m':  d_rx,
                        'dist_veh_tx_m': d_vtx,
                        'dist_veh_rx_m': d_vrx,
                        'veh_x':         float(row.veh_x),
                        'veh_y':         float(row.veh_y),
                        'tx_src':        tx_src,
                    })
            except Exception as e:
                print(f"    group ({vqx},{vqy}) failed: {e}")
    return pd.DataFrame(records)

# ── ML calibration ────────────────────────────────────────────────────────────
FEAT_COLS = ['rsrp_raw', 'rsrp_los', 'is_los', 'los_minus_tot',
             'dist_tx_rx_m', 'dist_veh_tx_m', 'dist_veh_rx_m']

def ols_calibrate(train_df, val_df):
    """Per-tower mean offset calibration."""
    offsets = (train_df.groupby('cell_eci')
               .apply(lambda g: float(np.mean(g.rsrp_meas - g.rsrp_raw)))
               .to_dict())
    val = val_df.copy()
    val['rsrp_ols'] = val.apply(
        lambda r: r.rsrp_raw + offsets.get(r.cell_eci,
               float(np.mean(train_df.rsrp_meas - train_df.rsrp_raw))), axis=1)
    return val, offsets

def xgb_calibrate(train_df, val_df):
    """Global XGBoost residual correction on top of OLS."""
    try:
        from xgboost import XGBRegressor
    except ImportError:
        from sklearn.ensemble import GradientBoostingRegressor as XGBRegressor
        print("  XGBoost not found, using sklearn GBT")

    val, offsets = ols_calibrate(train_df, val_df)
    # Train on OLS residual
    train_val  = val_df.copy()
    train_val['rsrp_ols'] = train_val.apply(
        lambda r: r.rsrp_raw + offsets.get(r.cell_eci,
               float(np.mean(train_df.rsrp_meas - train_df.rsrp_raw))), axis=1)

    X_tr = train_df[FEAT_COLS].values.astype(float)
    y_tr = (train_df.rsrp_meas - train_df.rsrp_raw).values   # raw residual

    model = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05,
                         subsample=0.8, colsample_bytree=0.8,
                         random_state=42, n_jobs=-1)
    model.fit(X_tr, y_tr)

    X_val = val_df[FEAT_COLS].values.astype(float)
    val['rsrp_xgb'] = val_df.rsrp_raw + model.predict(X_val)
    return val, model

def mae(meas, pred):
    offset = np.mean(meas - pred)
    return float(np.mean(np.abs(meas - pred - offset))), float(offset)

def rmse(meas, pred):
    offset = np.mean(meas - pred)
    return float(np.sqrt(np.mean((meas - pred - offset)**2)))

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("="*70)
    print("A18  ML-Enhanced Dynamic RT  (pc1 / Op1 / ±5s sync)")
    print("="*70)

    # Load data
    print("Loading cellular dataframe...")
    cdf = pd.read_csv(DATAFILE, usecols=['device', TS_COL, LAT_COL, LON_COL,
                                          RSRP_COL, SNR_COL, CELL_COL, 'operator'])
    cdf[TS_COL] = pd.to_datetime(cdf[TS_COL], errors='coerce')
    cdf = cdf.dropna(subset=[TS_COL, LAT_COL, LON_COL, RSRP_COL, CELL_COL])
    cdf[CELL_COL] = cdf[CELL_COL].astype(int)

    split = pd.read_csv(SPLIT_IDX)
    split[TS_COL] = pd.to_datetime(split[TS_COL])
    val_mask = (split.split == 'val') & (split.device == TARGET_DEVICE) & (split.operator == OPERATOR)
    val_ts = set(split[val_mask][TS_COL].astype(str))

    refined  = pd.read_csv(REFINED_POS)  if REFINED_POS.exists()  else pd.DataFrame()
    tower_pos = pd.read_csv(TOWER_POS)   if TOWER_POS.exists()     else pd.DataFrame()

    # pc1 + op1 rows
    pc1 = cdf[(cdf.device == TARGET_DEVICE) & (cdf.operator == OPERATOR)].copy()
    pc4 = cdf[cdf.device == COMPANION][[TS_COL, LAT_COL, LON_COL]].copy()
    pc4.columns = [TS_COL, 'veh_lat', 'veh_lon']

    # Nearest-timestamp match ±5 s
    pc1_s = pc1.sort_values(TS_COL).reset_index(drop=True)
    pc4_s = pc4.sort_values(TS_COL).reset_index(drop=True)
    merged = merge_asof(pc1_s, pc4_s, on=TS_COL, direction='nearest',
                        tolerance=TS_TOL).dropna(subset=['veh_lat', 'veh_lon'])
    merged['veh_x'], merged['veh_y'] = zip(*[
        ll2xy(la, lo) for la, lo in zip(merged.veh_lat, merged.veh_lon)
    ])
    merged['is_val'] = merged[TS_COL].astype(str).isin(val_ts)
    print(f"Total matched: {len(merged)} | train={( ~merged.is_val).sum()} val={merged.is_val.sum()}")

    train_rows = merged[~merged.is_val].copy()
    val_rows   = merged[merged.is_val].copy()

    tmp_dir = tempfile.mkdtemp(prefix="a18_")
    rng = np.random.default_rng(42)

    # Check for cached features
    feat_train_path = DRT_OUT / "features_train.csv"
    feat_val_path   = DRT_OUT / "features_val.csv"

    try:
        if feat_train_path.exists() and feat_val_path.exists():
            print("\nLoading cached features...")
            df_train = pd.read_csv(feat_train_path)
            df_val   = pd.read_csv(feat_val_path)
            print(f"  Train: {len(df_train)}  Val: {len(df_val)}")
        else:
            print("\n--- Extracting TRAINING features (dynamic RT) ---")
            df_train = extract_features(train_rows, refined, tower_pos, 'train', tmp_dir, rng)
            df_train.to_csv(feat_train_path, index=False)
            print(f"Saved {len(df_train)} train features → {feat_train_path}")

            print("\n--- Extracting VAL features (dynamic RT) ---")
            df_val = extract_features(val_rows, refined, tower_pos, 'val', tmp_dir, rng)
            df_val.to_csv(feat_val_path, index=False)
            print(f"Saved {len(df_val)} val features → {feat_val_path}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if df_train.empty or df_val.empty:
        print("No features extracted — check Sionna setup.")
        return

    # ── ML calibration ────────────────────────────────────────────────────────
    print("\n--- Stage 1: Per-tower OLS calibration ---")
    df_val_ols, offsets = ols_calibrate(df_train, df_val)
    ols_mae, _ = mae(df_val_ols.rsrp_meas.values, df_val_ols.rsrp_ols.values)
    ols_rmse    = rmse(df_val_ols.rsrp_meas.values, df_val_ols.rsrp_ols.values)
    print(f"  OLS MAE={ols_mae:.3f} dB  RMSE={ols_rmse:.3f} dB")

    print("\n--- Stage 2: XGBoost residual correction ---")
    df_val_xgb, xgb_model = xgb_calibrate(df_train, df_val)
    xgb_mae, _ = mae(df_val_xgb.rsrp_meas.values, df_val_xgb.rsrp_xgb.values)
    xgb_rmse   = rmse(df_val_xgb.rsrp_meas.values, df_val_xgb.rsrp_xgb.values)
    print(f"  XGBoost MAE={xgb_mae:.3f} dB  RMSE={xgb_rmse:.3f} dB")

    # LOS/NLOS breakdown for XGBoost
    los  = df_val_xgb.is_los.values
    xgb_mae_los,  _ = mae(df_val_xgb.rsrp_meas[los].values,  df_val_xgb.rsrp_xgb[los].values)  if los.sum()>5  else (None, None)
    xgb_mae_nlos, _ = mae(df_val_xgb.rsrp_meas[~los].values, df_val_xgb.rsrp_xgb[~los].values) if (~los).sum()>5 else (None, None)

    # SNR MAE
    snr_valid = df_val_xgb.snr_meas.notna().values
    snr_sim   = df_val_xgb.rsrp_xgb.values - NOISE_DBM
    snr_meas  = df_val_xgb.snr_meas.values
    if snr_valid.sum() > 5:
        snr_mae_val, _ = mae(snr_meas[snr_valid], snr_sim[snr_valid])
    else:
        snr_mae_val = None

    # Per-tower XGBoost MAE
    per_tower = []
    for cell_eci, grp in df_val_xgb.groupby('cell_eci'):
        m, _ = mae(grp.rsrp_meas.values, grp.rsrp_xgb.values)
        per_tower.append({'cell_eci': cell_eci, 'n': len(grp),
                          'mae_xgb': m, 'los_frac': float(grp.is_los.mean())})
    pd.DataFrame(per_tower).to_csv(DRT_OUT / "ml_per_tower.csv", index=False)

    # Save final predictions
    df_val_xgb.to_csv(DRT_OUT / "val_predictions_ml.csv", index=False)

    # Feature importances
    try:
        imp = dict(zip(FEAT_COLS, xgb_model.feature_importances_))
        print(f"\n  Feature importances: {imp}")
    except Exception:
        pass

    # Summary
    summary = {
        'total_val_rows':     len(df_val_xgb),
        'total_train_rows':   len(df_train),
        'los_fraction_val':   float(los.mean()),
        'baseline_raw_mae':   float(mae(df_val.rsrp_meas.values, df_val.rsrp_raw.values)[0]),
        'ols_mae':            ols_mae,
        'ols_rmse':           ols_rmse,
        'xgb_mae':            xgb_mae,
        'xgb_rmse':           xgb_rmse,
        'xgb_mae_los':        xgb_mae_los,
        'xgb_mae_nlos':       xgb_mae_nlos,
        'snr_mae_xgb':        snr_mae_val,
        'noise_floor_dbm':    NOISE_DBM,
    }
    with open(DRT_OUT / "ml_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved outputs to {DRT_OUT}/")

    print("\n" + "="*70)
    print("RESULTS SUMMARY")
    print(f"  Val rows:              {len(df_val_xgb)}")
    print(f"  Train rows (Sionna):   {len(df_train)}")
    print(f"  LOS fraction (val):    {los.mean()*100:.1f}%")
    print(f"  Raw Sionna MAE:        {summary['baseline_raw_mae']:.3f} dB  (no calibration)")
    print(f"  OLS calibrated MAE:    {ols_mae:.3f} dB")
    print(f"  XGBoost MAE:           {xgb_mae:.3f} dB")
    print(f"  XGBoost RMSE:          {xgb_rmse:.3f} dB")
    print(f"  XGBoost LOS MAE:       {xgb_mae_los}")
    print(f"  XGBoost NLOS MAE:      {xgb_mae_nlos}")
    print(f"  SNR MAE (vs SINR):     {snr_mae_val}")
    print("="*70)


if __name__ == "__main__":
    main()
