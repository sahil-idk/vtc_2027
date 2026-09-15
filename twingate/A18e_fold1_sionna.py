"""
A18e_fold1_sionna.py  —  3-way split unbiased evaluation
=========================================================
Fold 1 (truly unbiased):
  Train: Jun-22 only  (Sionna features, 50 rows/tower)
  Val  : Jun-23       (Sionna features, all rows with pc4 sync)
  Method F applied (fixed a priori, NOT selected on this val set)

Method F was selected by comparing A-F on the Jun-24 val set.
Evaluating it here on Jun-23 (entirely fresh) gives an unbiased estimate.

Jun-23 pc4 coverage: 19,720 rows → expected ~55% match → ~10,000 val rows
"""
import os, math, json, shutil, warnings, tempfile
import xml.etree.ElementTree as ET
import numpy as np, pandas as pd
from pathlib import Path

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, PathSolver
from pandas import merge_asof
from sklearn.linear_model import Ridge
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

ROOT     = Path(__file__).parent.parent
TWINGATE = Path(__file__).parent
OUT      = TWINGATE / "out"
DRT_OUT  = OUT / "dynamic_rt"
FOLD1_OUT = DRT_OUT / "fold1"
FOLD1_OUT.mkdir(exist_ok=True)

DATAFILE  = ROOT / "cellular_dataframe_cleaned.csv"
REFINED   = OUT / "refined_positions.csv"
TOWER_POS = OUT / "tower_positions.csv"
SCENE_XML = ROOT / "scene_operator1" / "scene.xml"
SCENE_ORIG = (52.507005, 13.323428)

OPERATOR       = 1
TARGET_DEVICE  = "pc1"
COMPANION      = "pc4"
TS_TOL         = pd.Timedelta("5s")
TX_H, RX_H     = 30.0, 1.5
EVAL_BATCH      = 40
MAX_DEPTH       = 4
MAX_TRAIN_ROWS  = 50
VEH_QUANT_M     = 100.0
VEH_MAT_ID      = "itu_concrete"
VEH_HALF        = (2.25, 1.0, 0.75)
NOISE_DBM       = -97.0
RSRP_COL = "PCell_RSRP_max"; SNR_COL = "PCell_SNR_1"
CELL_COL = "PCell_Cell_Identity"; TS_COL = "ts_gps"
LAT_COL  = "Latitude";          LON_COL = "Longitude"

TRAIN_DATE = "2021-06-22"   # train on this day only
VAL_DATE   = "2021-06-23"   # evaluate on this fresh day

def ll2xy(lat, lon):
    x = (lon - SCENE_ORIG[1]) * 111320.0 * math.cos(math.radians(SCENE_ORIG[0]))
    y = (lat - SCENE_ORIG[0]) * 111320.0
    return float(x), float(y)

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
    tree = ET.parse(SCENE_XML); root = tree.getroot()
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
    scene.add(Transmitter(name="tx_e", position=[tx_x, tx_y, TX_H]))
    full_all, los_all = [], []
    for start in range(0, len(rx_lats), EVAL_BATCH):
        blats = rx_lats[start:start+EVAL_BATCH]
        blons = rx_lons[start:start+EVAL_BATCH]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = ll2xy(float(la), float(lo))
            scene.add(Receiver(name=f"rx_e_{i}", position=[xi, yi, RX_H]))
        pf = solver(scene=scene, max_depth=MAX_DEPTH, diffraction=True)
        pl = solver(scene=scene, max_depth=0, diffraction=False)
        full_all.extend(power_dbm(pf).tolist())
        los_all.extend(power_dbm(pl).tolist())
        for i in range(len(blats)):
            scene.remove(f"rx_e_{i}")
    scene.remove("tx_e")
    return np.array(full_all), np.array(los_all)

def get_tx_pos(cell_eci, refined, tower_pos):
    if not refined.empty:
        r = refined[(refined.operator==OPERATOR)&(refined.cell_eci==int(cell_eci))]
        if not r.empty:
            return ll2xy(float(r.iloc[0].refined_lat), float(r.iloc[0].refined_lon)), 'refined'
    if not tower_pos.empty:
        t = tower_pos[(tower_pos.operator==OPERATOR)&(tower_pos.PCell_Cell_Identity==int(cell_eci))]
        if not t.empty:
            return ll2xy(float(t.iloc[0].tower_lat), float(t.iloc[0].tower_lon)), 'wcl'
    return None, None

def extract_features(subset, refined, tower_pos, label, tmp_dir, rng,
                     max_train=None, cache_dir=None):
    """Incrementally resumable: saves per-tower CSV immediately, skips done towers."""
    ant = PlanarArray(num_rows=1,num_cols=1,vertical_spacing=0.5,
                      horizontal_spacing=0.5,pattern="iso",polarization="V")

    all_cells = list(subset[CELL_COL].unique())
    # Find already-done towers from per-tower cache files
    done = set()
    if cache_dir:
        cache_dir.mkdir(exist_ok=True)
        for f in cache_dir.glob(f"{label}_*.csv"):
            try: done.add(int(f.stem.split("_")[1]))
            except: pass
    if done:
        print(f"  Resuming {label}: {len(done)}/{len(all_cells)} towers already cached")

    for c_idx, cell_eci in enumerate(all_cells):
        if int(cell_eci) in done:
            print(f"  [{label}] {cell_eci} ({c_idx+1}/{len(all_cells)}) — cached, skip")
            continue
        grp = subset[subset[CELL_COL]==cell_eci].copy()
        tx_pos, src = get_tx_pos(cell_eci, refined, tower_pos)
        if tx_pos is None: continue
        tx_x, tx_y = tx_pos
        if max_train and len(grp) > max_train:
            grp = grp.iloc[rng.choice(len(grp), max_train, replace=False)]
        grp['vq_x'] = grp['veh_x'].apply(quant)
        grp['vq_y'] = grp['veh_y'].apply(quant)
        groups = grp.groupby(['vq_x','vq_y'])
        print(f"  [{label}] {cell_eci} ({c_idx+1}/{len(all_cells)}) "
              f"rows={len(grp)} groups={groups.ngroups} src={src}", flush=True)
        tower_records = []
        for (vqx,vqy), g in groups:
            veh_x = float(vqx+VEH_QUANT_M/2); veh_y = float(vqy+VEH_QUANT_M/2)
            try:
                xml = write_scene_with_vehicle(veh_x, veh_y, tmp_dir)
                scene = load_scene(xml); scene.tx_array = ant; scene.rx_array = ant
                solver = PathSolver()
                rf, rl = forward_group(tx_x, tx_y, g[LAT_COL].values, g[LON_COL].values, scene, solver)
                del scene, solver
                d_vtx = math.hypot(veh_x-tx_x, veh_y-tx_y)
                for i, (_,row) in enumerate(g.iterrows()):
                    rx_x, rx_y = ll2xy(float(row[LAT_COL]), float(row[LON_COL]))
                    tower_records.append({'ts_gps': str(row[TS_COL]), 'cell_eci': int(cell_eci),
                        'rsrp_meas': float(row[RSRP_COL]),
                        'snr_meas': float(row[SNR_COL]) if pd.notna(row.get(SNR_COL)) else np.nan,
                        'rsrp_raw': float(rf[i]), 'rsrp_los': float(rl[i]),
                        'is_los': bool(rl[i] > -130.0),
                        'los_minus_tot': float(rl[i]-rf[i]) if rl[i]>-130 else 0.0,
                        'dist_tx_rx_m': math.hypot(rx_x-tx_x, rx_y-tx_y),
                        'dist_veh_tx_m': d_vtx,
                        'dist_veh_rx_m': math.hypot(rx_x-veh_x, rx_y-veh_y),
                        'veh_x': veh_x, 'veh_y': veh_y, 'tx_src': src})
            except Exception as e:
                print(f"    group ({vqx},{vqy}) failed: {e}", flush=True)
        # Save this tower immediately
        if tower_records and cache_dir:
            pd.DataFrame(tower_records).to_csv(
                cache_dir / f"{label}_{int(cell_eci)}.csv", index=False)

    # Combine all per-tower CSVs
    parts = []
    if cache_dir:
        for f in sorted(cache_dir.glob(f"{label}_*.csv")):
            try: parts.append(pd.read_csv(f))
            except: pass
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

def method_F(tr, vl):
    for col in ['dist_tx_rx_m','dist_veh_tx_m','dist_veh_rx_m']:
        med = tr[col].median()
        tr[col] = tr[col].fillna(med); vl[col] = vl[col].fillna(med)

    off = {c: float(np.mean(g.rsrp_meas-g.rsrp_raw))
           for c,g in tr.groupby('cell_eci')}
    glob = float(np.mean(tr.rsrp_meas-tr.rsrp_raw))
    pred = tr.rsrp_raw.values + np.array([off.get(c,glob) for c in tr.cell_eci])  # train OLS
    pred_v = vl.rsrp_raw.values + np.array([off.get(c,glob) for c in vl.cell_eci])

    nlos_tr = tr[~tr.is_los.astype(bool)].copy()
    nlos_vl = vl[~vl.is_los.astype(bool)].copy()

    if len(nlos_tr) >= 5 and len(nlos_vl) > 0:
        enc = OneHotEncoder(sparse_output=False, handle_unknown='ignore')
        td_tr = enc.fit_transform(nlos_tr[['cell_eci']])
        td_vl = enc.transform(nlos_vl[['cell_eci']])
        ld_tr = np.log10(np.maximum(nlos_tr.dist_tx_rx_m.values,1.0)).reshape(-1,1)
        ld_vl = np.log10(np.maximum(nlos_vl.dist_tx_rx_m.values,1.0)).reshape(-1,1)
        X_tr = np.hstack([ld_tr, td_tr]); X_vl = np.hstack([ld_vl, td_vl])
        pl = Ridge(alpha=1.0).fit(X_tr, nlos_tr.rsrp_meas.values)
        resid = nlos_tr.rsrp_meas.values - pl.predict(X_tr)
        xgb = XGBRegressor(n_estimators=200,max_depth=4,learning_rate=0.05,
                           random_state=42,n_jobs=-1,verbosity=0)
        xgb.fit(X_tr, resid)
        nlos_pred = pl.predict(X_vl) + xgb.predict(X_vl)
        idx = np.where(~vl.is_los.values.astype(bool))[0]
        pred_v[idx] = nlos_pred
    return pred_v

def mae_cal(meas, pred):
    if len(meas) < 2: return np.nan
    return float(np.mean(np.abs(meas-pred-np.mean(meas-pred))))

def main():
    print("="*65)
    print(f"A18e  Fold-1: Train={TRAIN_DATE}  Val={VAL_DATE}  (unbiased)")
    print("="*65)

    cdf = pd.read_csv(DATAFILE, usecols=['device',TS_COL,LAT_COL,LON_COL,
                                          RSRP_COL,SNR_COL,CELL_COL,'operator'])
    cdf[TS_COL] = pd.to_datetime(cdf['ts_gps'], errors='coerce')
    cdf = cdf.dropna(subset=[TS_COL,LAT_COL,LON_COL,RSRP_COL,CELL_COL])
    cdf[CELL_COL] = cdf[CELL_COL].astype(int)
    cdf['date'] = cdf[TS_COL].dt.strftime('%Y-%m-%d')

    refined  = pd.read_csv(REFINED)   if REFINED.exists()   else pd.DataFrame()
    tower_pos = pd.read_csv(TOWER_POS) if TOWER_POS.exists() else pd.DataFrame()
    rng = np.random.default_rng(42)

    pc1_tr = cdf[(cdf.device==TARGET_DEVICE)&(cdf.operator==OPERATOR)&(cdf.date==TRAIN_DATE)].copy()
    pc1_vl = cdf[(cdf.device==TARGET_DEVICE)&(cdf.operator==OPERATOR)&(cdf.date==VAL_DATE)].copy()
    pc4    = cdf[cdf.device==COMPANION][[TS_COL,LAT_COL,LON_COL]].copy()
    pc4.columns = [TS_COL,'veh_lat','veh_lon']

    def sync_pc4(pc1_sub):
        m = merge_asof(pc1_sub.sort_values(TS_COL), pc4.sort_values(TS_COL),
                       on=TS_COL, direction='nearest', tolerance=TS_TOL)
        m = m.dropna(subset=['veh_lat','veh_lon'])
        m['veh_x'],m['veh_y'] = zip(*[ll2xy(la,lo) for la,lo in zip(m.veh_lat,m.veh_lon)])
        return m

    train_rows = sync_pc4(pc1_tr)
    val_rows   = sync_pc4(pc1_vl)
    print(f"Train (Jun22 matched): {len(train_rows)} / {len(pc1_tr)}")
    print(f"Val   (Jun23 matched): {len(val_rows)} / {len(pc1_vl)}")

    TOWER_CACHE = FOLD1_OUT / "tower_cache"
    tmp = tempfile.mkdtemp(prefix="a18e_")
    try:
        feat_tr_path = FOLD1_OUT / "features_train_fold1.csv"
        feat_vl_path = FOLD1_OUT / "features_val_fold1.csv"

        # Always use incremental per-tower cache — safe to resume after any kill
        print("\n--- TRAIN features (Jun-22) ---")
        df_tr = extract_features(train_rows, refined, tower_pos,
                                 'train', tmp, rng, MAX_TRAIN_ROWS,
                                 cache_dir=TOWER_CACHE)
        df_tr.to_csv(feat_tr_path, index=False)
        print(f"Saved {len(df_tr)} train features → {feat_tr_path}")

        print("\n--- VAL features (Jun-23) ---")
        df_vl = extract_features(val_rows, refined, tower_pos, 'val', tmp, rng,
                                 cache_dir=TOWER_CACHE)
        df_vl.to_csv(feat_vl_path, index=False)
        print(f"Saved {len(df_vl)} val features → {feat_vl_path}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    pred = method_F(df_tr.copy(), df_vl.copy())
    meas = df_vl.rsrp_meas.values
    los  = df_vl.is_los.values.astype(bool)

    res = {
        'fold': 1, 'train_date': TRAIN_DATE, 'val_date': VAL_DATE,
        'n_train': len(df_tr), 'n_val': len(df_vl),
        'los_frac': float(los.mean()),
        'mae_overall': mae_cal(meas, pred),
        'mae_los':  mae_cal(meas[los],  pred[los]),
        'mae_nlos': mae_cal(meas[~los], pred[~los]),
    }
    print("\n" + "="*65)
    print(f"FOLD 1 RESULTS  (Method F, trained Jun-22, evaluated Jun-23)")
    print(f"  Overall MAE : {res['mae_overall']:.3f} dB")
    print(f"  LOS MAE     : {res['mae_los']:.3f} dB")
    print(f"  NLOS MAE    : {res['mae_nlos']:.3f} dB")
    print(f"  Val rows    : {res['n_val']}  LOS={res['los_frac']*100:.1f}%")
    print("="*65)

    # Compare folds
    print("\nCROSS-FOLD SUMMARY (Method F):")
    print(f"  Fold 1 (Jun23 val, unbiased): {res['mae_overall']:.3f} dB")
    print(f"  Fold 2 (Jun24 val, method selected here): 3.055 dB")

    with open(FOLD1_OUT/"fold1_summary.json","w") as f:
        json.dump(res, f, indent=2)
    print(f"\nSaved → {FOLD1_OUT}/fold1_summary.json")

if __name__=="__main__":
    main()
