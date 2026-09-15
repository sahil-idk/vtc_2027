"""
GZ-3 (all-towers): Real Sionna leave-one-device-out on ALL towers per operator.

Same methodology as 06_gz3_sionna_leaveout.py but:
  - N_TOWERS = None  (all towers in op{n}_towers_wcl_init.csv)
  - MAX_VAL_PER_TOWER = 40  (1 PathSolver batch each — keeps runtime ~10-15 min total)
  - Output files suffixed _all to distinguish from 5-tower prototype run

Usage:
  python 06b_gz3_all_towers.py          # both operators
  python 06b_gz3_all_towers.py 1        # operator 1 only
"""
import sys, json, math, time
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, PathSolver

# ---- Config -----------------------------------------------------------------
N_TOWERS          = None   # None = all towers
MAX_VAL_PER_TOWER = 40     # 1 PathSolver batch per tower
N_BOOT            = 200
EVAL_BATCH_SIZE   = 40
TX_HEIGHT_M       = 30.0
RX_HEIGHT_M       = 1.5
MIN_VAL_ROWS      = 5      # skip tower if fewer val rows than this

SCENE_ORIGINS = {
    1: (52.507005, 13.323428),
    2: (52.506112, 13.321908),
}

with open('calibration_offsets.json') as f:
    _cal = json.load(f)
OFFSET_DB = {1: _cal['1']['offset_db'], 2: _cal['2']['offset_db']}

FLAGGED_DEVICE = {1: 'pc4', 2: None}

# ---- Geometry ---------------------------------------------------------------

def latlon_to_scene_xy(lat, lon, origin_lat, origin_lon):
    x = (lon - origin_lon) * 111_320.0 * math.cos(math.radians(origin_lat))
    y = (lat - origin_lat) * 111_320.0
    return x, y

def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2-lat1)/2)**2
         + np.cos(p1)*np.cos(p2)*np.sin(np.radians(lon2-lon1)/2)**2)
    return 2*R*np.arcsin(np.sqrt(a))

# ---- Sionna forward pass ----------------------------------------------------

def power_dbm_from_paths(paths):
    a_r = np.array(dr.detach(paths.a[0]))
    a_i = np.array(dr.detach(paths.a[1]))
    plin = (a_r**2 + a_i**2).sum(axis=-1).squeeze(axis=(1, 2, 3))
    return 10.0 * np.log10(np.maximum(plin, 1e-30)) + 30.0

def sim_tower_batch(rx_lats, rx_lons, tower_lat, tower_lon,
                    scene, solver, origin_lat, origin_lon, offset_db):
    tx_x, tx_y = latlon_to_scene_xy(tower_lat, tower_lon, origin_lat, origin_lon)
    scene.add(Transmitter(name='tx_gz3', position=[float(tx_x), float(tx_y), TX_HEIGHT_M]))

    powers = []
    n = len(rx_lats)
    for start in range(0, n, EVAL_BATCH_SIZE):
        blats = rx_lats[start:start + EVAL_BATCH_SIZE]
        blons = rx_lons[start:start + EVAL_BATCH_SIZE]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = latlon_to_scene_xy(float(la), float(lo), origin_lat, origin_lon)
            scene.add(Receiver(name=f'rx_gz3_{i}', position=[float(xi), float(yi), RX_HEIGHT_M]))
        paths = solver(scene=scene, max_depth=5, diffraction=True)
        powers.extend((power_dbm_from_paths(paths) + offset_db).tolist())
        for i in range(len(blats)):
            scene.remove(f'rx_gz3_{i}')

    scene.remove('tx_gz3')
    return np.array(powers)

# ---- GZ-3 per operator ------------------------------------------------------

def run_gz3_all(operator):
    origin_lat, origin_lon = SCENE_ORIGINS[operator]
    offset_db = OFFSET_DB[operator]
    flagged   = FLAGGED_DEVICE[operator]

    print(f'\n{"="*65}')
    print(f'GZ-3 (ALL TOWERS)  Operator {operator}  |  offset={offset_db:.3f} dB')
    print(f'Flagged device: {flagged}')
    print(f'{"="*65}')

    meas_df   = pd.read_csv(f'op{operator}_measurements.csv')
    towers_df = pd.read_csv(f'op{operator}_towers_wcl_init.csv').sort_values('n_obs', ascending=False)

    devices = sorted(meas_df['device'].dropna().unique())
    n_total = len(towers_df) if N_TOWERS is None else N_TOWERS
    print(f'Devices: {devices}  |  Towers to process: {n_total}')

    scene  = load_scene(f'scene_operator{operator}/scene.xml')
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    solver = PathSolver()

    all_rows   = []
    n_skipped  = 0
    t_start    = time.time()

    tower_iter = towers_df if N_TOWERS is None else towers_df.head(N_TOWERS)

    for tower_idx, (_, tower) in enumerate(tower_iter.iterrows()):
        cell_id = int(tower['cell_id'])
        wcl_lat = float(tower['wcl_lat'])
        wcl_lon = float(tower['wcl_lon'])

        val = meas_df[
            (meas_df.PCell_Cell_Identity == cell_id) &
            (meas_df.is_localization == False)
        ].copy().reset_index(drop=True)

        if len(val) < MIN_VAL_ROWS:
            n_skipped += 1
            continue

        # Stratified sample: proportional per device, cap at MAX_VAL_PER_TOWER
        if len(val) > MAX_VAL_PER_TOWER:
            parts = []
            for dev, grp in val.groupby('device'):
                n_dev = max(1, round(MAX_VAL_PER_TOWER * len(grp) / len(val)))
                rng_seed = int((cell_id + hash(dev)) % (2**31))
                parts.append(grp.sample(min(len(grp), n_dev), random_state=rng_seed))
            sampled = pd.concat(parts)
            if len(sampled) > MAX_VAL_PER_TOWER:
                sampled = sampled.sample(MAX_VAL_PER_TOWER, random_state=cell_id % (2**31))
            sampled = sampled.reset_index(drop=True)
        else:
            sampled = val

        sim_powers = sim_tower_batch(
            sampled.Latitude.values, sampled.Longitude.values,
            wcl_lat, wcl_lon, scene, solver, origin_lat, origin_lon, offset_db
        )

        dists = haversine_m(sampled.Latitude.values, sampled.Longitude.values, wcl_lat, wcl_lon)

        for idx in range(len(sampled)):
            row = sampled.iloc[idx]
            all_rows.append({
                'tower_id':  cell_id,
                'device':    row['device'],
                'measured':  float(row['PCell_RSRP_max']),
                'simulated': float(sim_powers[idx]),
                'dist_m':    float(dists[idx]),
                'lat':       float(row['Latitude']),
                'lon':       float(row['Longitude']),
            })

        elapsed = time.time() - t_start
        n_done  = tower_idx + 1 - n_skipped
        rate    = n_done / elapsed if elapsed > 0 else 1
        eta     = (n_total - n_done) / rate if rate > 0 else 0
        print(f'  [{tower_idx+1:3d}/{n_total}] Tower {cell_id}: n={len(sampled)} | '
              f'elapsed={elapsed:.0f}s eta={eta:.0f}s', flush=True)

    df = pd.DataFrame(all_rows).dropna(subset=['measured', 'simulated'])
    df['residual'] = df['measured'] - df['simulated']
    df.to_csv(f'gz3_op{operator}_all_rows_all.csv', index=False)

    n_towers_used = df['tower_id'].nunique()
    print(f'\n  Towers processed: {n_towers_used} (skipped {n_skipped} with <{MIN_VAL_ROWS} val rows)')
    print(f'  Total rows: {len(df)}')

    if len(df) == 0:
        print('  ERROR: no rows.')
        return None

    # ---- Baseline MAE -------------------------------------------------------
    baseline_mae  = float(np.mean(np.abs(df['residual'])))
    baseline_rmse = float(np.sqrt(np.mean(df['residual']**2)))
    print(f'\n  Baseline MAE  = {baseline_mae:.3f} dB')
    print(f'  Baseline RMSE = {baseline_rmse:.3f} dB')

    # ---- Leave-one-device-out -----------------------------------------------
    print(f'\n  Leave-one-device-out:')
    device_results = {}
    for dev in devices:
        subset = df[df['device'] != dev]
        if len(subset) < 10:
            continue
        mae  = float(np.mean(np.abs(subset['residual'])))
        rmse = float(np.sqrt(np.mean(subset['residual']**2)))
        imp  = baseline_mae - mae
        n_ex = len(df) - len(subset)
        device_results[dev] = {
            'mae': mae, 'rmse': rmse,
            'improvement': imp,
            'n_excluded': n_ex, 'n_remaining': len(subset),
        }
        tag = '  <-- DT-QUEST FLAGGED' if dev == flagged else ''
        print(f'    Excl {dev}: MAE={mae:.3f} dB  imp={imp:+.3f} dB  n_excl={n_ex}{tag}')

    if not device_results:
        return None

    best_dev = max(device_results, key=lambda d: device_results[d]['improvement'])
    n_excl   = device_results[best_dev]['n_excluded']
    real_imp = device_results[best_dev]['improvement']

    # ---- Bootstrap null -----------------------------------------------------
    print(f'\n  Bootstrap null (n={N_BOOT}, excl {n_excl} rows each)...')
    rng = np.random.default_rng(42)
    null_imps = []
    for i in range(N_BOOT):
        idx_excl = rng.choice(len(df), size=n_excl, replace=False)
        mask = np.ones(len(df), dtype=bool)
        mask[idx_excl] = False
        null_imps.append(baseline_mae - float(np.mean(np.abs(df['residual'].values[mask]))))
        if (i + 1) % 50 == 0:
            print(f'    boot {i+1}/{N_BOOT}: running null mean = {np.mean(null_imps):+.4f} dB')

    null_arr = np.array(null_imps)
    pctile   = float((null_arr < real_imp).mean() * 100)

    print(f'\n  Best device: {best_dev}  imp={real_imp:+.3f} dB')
    print(f'  Null: mean={null_arr.mean():+.4f} dB  std={null_arr.std():.4f} dB')
    print(f'  Percentile: {pctile:.1f}%  -> {"SIGNIFICANT" if pctile > 95 else "NOT SIGNIFICANT"}')

    flagged_pctile = None
    if flagged and flagged != best_dev and flagged in device_results:
        flag_imp = device_results[flagged]['improvement']
        flagged_pctile = float((null_arr < flag_imp).mean() * 100)
        print(f'  Flagged ({flagged}): imp={flag_imp:+.3f} dB  percentile={flagged_pctile:.1f}%')

    # ---- Continuity check ---------------------------------------------------
    print(f'\n  === Continuity (all towers combined) ===')
    continuity_results = {}
    for dev in devices:
        sub = df[df['device'] == dev].sort_values('dist_m')
        if len(sub) < 5:
            continue
        r_dist_meas, _ = pearsonr(sub['dist_m'], sub['measured'])
        r_dist_sim,  _ = pearsonr(sub['dist_m'], sub['simulated'])
        r_sv_m,      _ = pearsonr(sub['measured'], sub['simulated'])
        smooth_meas    = float(np.std(np.diff(sub['measured'].values)))
        smooth_sim     = float(np.std(np.diff(sub['simulated'].values)))
        continuity_results[dev] = {
            'n': len(sub),
            'rsrp_dist_corr_meas': float(r_dist_meas),
            'rsrp_dist_corr_sim':  float(r_dist_sim),
            'sim_vs_meas_corr':    float(r_sv_m),
            'smoothness_meas_db':  smooth_meas,
            'smoothness_sim_db':   smooth_sim,
            'sim_plausible':       bool(r_dist_sim < -0.1),
            'sim_tracks_meas':     bool(r_sv_m > 0.3),
        }
        ok    = 'OK' if r_dist_sim < -0.1 else 'FAIL'
        track = 'tracks' if r_sv_m > 0.3 else 'weak'
        print(f'  {dev} (n={len(sub)}): r_dist_sim={r_dist_sim:.3f} [{ok}]  '
              f'r_sim_vs_meas={r_sv_m:.3f} [{track}]  '
              f'smooth_sim={smooth_sim:.1f} dB')

    # ---- Save ---------------------------------------------------------------
    summary = {
        'operator': operator, 'n_rows': len(df),
        'n_towers': n_towers_used, 'n_skipped': n_skipped,
        'offset_db': offset_db,
        'baseline_mae': baseline_mae, 'baseline_rmse': baseline_rmse,
        'devices': devices, 'flagged_device': flagged,
        'device_results': device_results,
        'bootstrap': {
            'best_device': best_dev,
            'real_improvement': real_imp,
            'null_mean': float(null_arr.mean()),
            'null_std':  float(null_arr.std()),
            'percentile': pctile,
            'significant': bool(pctile > 95),
            'flagged_percentile': flagged_pctile,
        },
        'continuity': continuity_results,
    }
    out = f'gz3_op{operator}_summary_all.json'
    with open(out, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f'\n  Saved -> {out}')
    return summary


# ---- Main -------------------------------------------------------------------

def main():
    ops = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else [1, 2]
    summaries = {}
    for op in ops:
        summaries[op] = run_gz3_all(op)

    print('\n' + '='*65)
    print('GZ-3 ALL-TOWERS  FINAL SUMMARY')
    print('='*65)
    for op, s in summaries.items():
        if not s:
            print(f'Op{op}: FAILED')
            continue
        b = s['bootstrap']
        flagged = s['flagged_device']
        print(f'\nOperator {op}  ({s["n_towers"]} towers, {s["n_rows"]} rows):')
        print(f'  Baseline MAE = {s["baseline_mae"]:.3f} dB')
        for dev, r in s['device_results'].items():
            tag = ' <-- FLAGGED' if dev == flagged else ''
            print(f'    excl {dev}: MAE={r["mae"]:.3f} dB  imp={r["improvement"]:+.3f} dB{tag}')
        print(f'  Best: {b["best_device"]}  imp={b["real_improvement"]:+.3f} dB  '
              f'boot={b["percentile"]:.1f}%  -> {"SIGNIFICANT" if b["significant"] else "NOT SIGNIFICANT"}')
        if flagged and b.get('flagged_percentile') is not None:
            print(f'  Flagged ({flagged}) percentile: {b["flagged_percentile"]:.1f}%')
        print(f'  Continuity:')
        for dev, c in s['continuity'].items():
            print(f'    {dev}: r_dist_sim={c["rsrp_dist_corr_sim"]:.3f}  '
                  f'r_sim_vs_meas={c["sim_vs_meas_corr"]:.3f}')

    with open('gz3_all_towers_combined.json', 'w') as f:
        json.dump({str(k): v for k, v in summaries.items()}, f, indent=2)
    print('\nCombined -> gz3_all_towers_combined.json')


if __name__ == '__main__':
    main()
