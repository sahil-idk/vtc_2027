"""
GZ-3: Real Sionna leave-one-device-out MAE test + trajectory continuity check.

Answers:
  1. Does excluding the DT-QUEST-flagged device (PC4 in Op1) improve real Sionna-oracle MAE?
  2. Is that improvement larger than random row exclusion (bootstrap null)?
  3. Does Sionna produce continuous, physically-realistic RSRP as the vehicle moves
     (i.e., does simulated RSRP track the measured RSRP and decrease with distance)?

Device mapping:
  Operator 1: pc1, pc4  (PC4 was flagged by DT-QUEST's completeness check)
  Operator 2: pc2, pc3

Usage:
  python 06_gz3_sionna_leaveout.py          # both operators
  python 06_gz3_sionna_leaveout.py 1        # operator 1 only
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
N_TOWERS          = 5     # top-N towers per operator (prototype scope)
MAX_VAL_PER_TOWER = 80    # max validation rows per tower (2 Sionna batches of 40)
N_BOOT            = 200   # bootstrap null iterations
EVAL_BATCH_SIZE   = 40
TX_HEIGHT_M       = 30.0
RX_HEIGHT_M       = 1.5

SCENE_ORIGINS = {
    1: (52.507005, 13.323428),
    2: (52.506112, 13.321908),
}

with open('calibration_offsets.json') as f:
    _cal = json.load(f)
OFFSET_DB = {1: _cal['1']['offset_db'], 2: _cal['2']['offset_db']}

# PC4 is the DT-QUEST-flagged device for Op1 (completeness gap, Type A).
# PC3 has no flag — but the proxy oracle (§5.3) found PC3's exclusion improved
# fidelity more than PC4's. GZ-3 tests whether the real Sionna oracle agrees.
FLAGGED_DEVICE = {1: 'pc4', 2: None}   # Op2 has no flagged device (pc2/pc3 both clean)

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
    """
    Simulate calibrated received power (dBm) at all rx positions from a fixed tower.
    Handles batching internally (EVAL_BATCH_SIZE receivers per PathSolver call).
    Returns numpy array of shape (n_rx,).
    """
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

def run_gz3_operator(operator):
    origin_lat, origin_lon = SCENE_ORIGINS[operator]
    offset_db = OFFSET_DB[operator]
    flagged   = FLAGGED_DEVICE[operator]

    print(f'\n{"="*65}')
    print(f'GZ-3  Operator {operator}  |  calibration offset = {offset_db:.3f} dB')
    print(f'Flagged device (DT-QUEST): {flagged}')
    print(f'{"="*65}')

    meas_df   = pd.read_csv(f'op{operator}_measurements.csv')
    towers_df = pd.read_csv(f'op{operator}_towers_wcl_init.csv').sort_values('n_obs', ascending=False)

    devices = sorted(meas_df['device'].dropna().unique())
    print(f'Devices in Op{operator}: {devices}')

    scene  = load_scene(f'scene_operator{operator}/scene.xml')
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    solver = PathSolver()

    # ---- Collect simulated RSRP for all sampled validation rows -------------
    all_rows = []   # list of dicts

    for _, tower in towers_df.head(N_TOWERS).iterrows():
        cell_id  = int(tower['cell_id'])
        wcl_lat  = float(tower['wcl_lat'])
        wcl_lon  = float(tower['wcl_lon'])

        val = meas_df[
            (meas_df.PCell_Cell_Identity == cell_id) &
            (meas_df.is_localization == False)
        ].copy().reset_index(drop=True)

        if len(val) == 0:
            print(f'\n  Tower {cell_id}: 0 validation rows — skipping')
            continue

        # Stratified sample by device (proportional, up to MAX_VAL_PER_TOWER total)
        if len(val) > MAX_VAL_PER_TOWER:
            parts = []
            for dev, grp in val.groupby('device'):
                n_dev = max(1, round(MAX_VAL_PER_TOWER * len(grp) / len(val)))
                rng = np.random.default_rng(cell_id + hash(dev) % (2**20))
                parts.append(grp.sample(min(len(grp), n_dev), random_state=int(rng.integers(1<<31))))
            sampled = pd.concat(parts).sample(
                min(MAX_VAL_PER_TOWER, sum(len(p) for p in parts)),
                random_state=cell_id).reset_index(drop=True)
        else:
            sampled = val

        dev_counts = sampled['device'].value_counts().to_dict()
        print(f'\n  Tower {cell_id}: {len(sampled)} val rows | {dev_counts}')

        t0 = time.time()
        sim_powers = sim_tower_batch(
            sampled.Latitude.values, sampled.Longitude.values,
            wcl_lat, wcl_lon, scene, solver, origin_lat, origin_lon, offset_db
        )
        mae_tower = float(np.mean(np.abs(sampled.PCell_RSRP_max.values - sim_powers)))
        print(f'    Sionna done in {time.time()-t0:.1f}s  |  tower MAE = {mae_tower:.2f} dB')

        # Compute distance from tower for continuity analysis
        dists = haversine_m(
            sampled.Latitude.values, sampled.Longitude.values,
            wcl_lat, wcl_lon
        )

        for idx in range(len(sampled)):
            row = sampled.iloc[idx]
            all_rows.append({
                'tower_id':   cell_id,
                'wcl_lat':    wcl_lat,
                'wcl_lon':    wcl_lon,
                'device':     row['device'],
                'measured':   float(row['PCell_RSRP_max']),
                'simulated':  float(sim_powers[idx]),
                'lat':        float(row['Latitude']),
                'lon':        float(row['Longitude']),
                'dist_m':     float(dists[idx]),
            })

    df = pd.DataFrame(all_rows).dropna(subset=['measured', 'simulated'])
    df['residual'] = df['measured'] - df['simulated']
    df.to_csv(f'gz3_op{operator}_all_rows.csv', index=False)
    print(f'\n  Total rows collected: {len(df)}  |  towers: {df["tower_id"].nunique()}')

    if len(df) == 0:
        print('  ERROR: no rows collected, cannot run GZ-3.')
        return None

    # ---- 1. Baseline MAE ----------------------------------------------------
    baseline_mae = float(np.mean(np.abs(df['residual'])))
    baseline_rmse = float(np.sqrt(np.mean(df['residual']**2)))
    print(f'\n  Baseline MAE  = {baseline_mae:.3f} dB')
    print(f'  Baseline RMSE = {baseline_rmse:.3f} dB  (n={len(df)})')

    # ---- 2. Leave-one-device-out MAE ----------------------------------------
    print(f'\n  Leave-one-device-out:')
    device_results = {}
    for dev in devices:
        subset = df[df['device'] != dev]
        if len(subset) < 5:
            print(f'    Excl {dev}: too few rows ({len(subset)}), skip')
            continue
        mae  = float(np.mean(np.abs(subset['residual'])))
        rmse = float(np.sqrt(np.mean(subset['residual']**2)))
        imp  = baseline_mae - mae
        n_ex = len(df) - len(subset)
        device_results[dev] = {
            'mae':         mae,
            'rmse':        rmse,
            'improvement': imp,
            'n_excluded':  n_ex,
            'n_remaining': len(subset),
        }
        flag = '<-- DT-QUEST FLAGGED' if dev == flagged else ''
        print(f'    Excl {dev}: MAE={mae:.3f} dB  imp={imp:+.3f} dB  n_excl={n_ex}  {flag}')

    # ---- 3. Bootstrap null --------------------------------------------------
    if not device_results:
        print('  No device results — skip bootstrap.')
        return None

    best_dev  = max(device_results, key=lambda d: device_results[d]['improvement'])
    n_excl    = device_results[best_dev]['n_excluded']
    real_imp  = device_results[best_dev]['improvement']

    print(f'\n  Bootstrap null (n={N_BOOT}, n_excl={n_excl} rows each)...')
    rng = np.random.default_rng(42)
    null_imps = []
    for i in range(N_BOOT):
        idx_excl = rng.choice(len(df), size=n_excl, replace=False)
        mask = np.ones(len(df), dtype=bool)
        mask[idx_excl] = False
        null_mae = float(np.mean(np.abs(df['residual'].values[mask])))
        null_imps.append(baseline_mae - null_mae)
        if (i + 1) % 50 == 0:
            print(f'    boot {i+1}/{N_BOOT}: running null mean = {np.mean(null_imps):+.4f} dB')

    null_arr = np.array(null_imps)
    pctile   = float((null_arr < real_imp).mean() * 100)

    print(f'\n  Best device to exclude: {best_dev}  (real improvement: {real_imp:+.3f} dB)')
    print(f'  Null distribution: mean={null_arr.mean():+.4f} dB  std={null_arr.std():.4f} dB')
    print(f'  Percentile: {pctile:.1f}%')
    sig_str = 'SIGNIFICANT (>95%)' if pctile > 95 else 'NOT SIGNIFICANT'
    print(f'  --> {sig_str}')

    flagged_result = device_results.get(flagged, {}) if flagged else {}
    flagged_pctile = None
    if flagged and flagged != best_dev:
        flag_imp = flagged_result.get('improvement', None)
        if flag_imp is not None:
            flagged_pctile = float((null_arr < flag_imp).mean() * 100)
            print(f'\n  DT-QUEST-flagged device ({flagged}) rank:')
            print(f'    improvement={flag_imp:+.3f} dB  percentile={flagged_pctile:.1f}%')

    # ---- 4. Trajectory / continuity check -----------------------------------
    print(f'\n  === Continuity Check: RSRP vs Distance from Tower ===')

    continuity_results = {}
    for dev in devices:
        dev_df = df[df['device'] == dev]
        if len(dev_df) < 5:
            continue

        # Overall RSRP-distance correlation (all towers combined)
        r_meas, _ = pearsonr(dev_df['dist_m'], dev_df['measured'])
        r_sim,  _ = pearsonr(dev_df['dist_m'], dev_df['simulated'])

        # Smoothness: sort by distance, compute std of consecutive diffs
        sorted_df = dev_df.sort_values('dist_m')
        smooth_meas = float(np.std(np.diff(sorted_df['measured'].values)))  if len(sorted_df) > 1 else np.nan
        smooth_sim  = float(np.std(np.diff(sorted_df['simulated'].values))) if len(sorted_df) > 1 else np.nan

        # Sim-vs-measured correlation
        r_sv_m, _ = pearsonr(dev_df['measured'], dev_df['simulated'])

        continuity_results[dev] = {
            'n_rows':               len(dev_df),
            'rsrp_dist_corr_meas':  float(r_meas),
            'rsrp_dist_corr_sim':   float(r_sim),
            'sim_vs_meas_corr':     float(r_sv_m),
            'smoothness_meas_db':   float(smooth_meas),
            'smoothness_sim_db':    float(smooth_sim),
            'meas_plausible':       bool(r_meas < -0.1),
            'sim_plausible':        bool(r_sim  < -0.1),
            'sim_tracks_meas':      bool(r_sv_m >  0.3),
        }
        print(f'\n  Device {dev}  (n={len(dev_df)}):')
        print(f'    RSRP-dist corr: measured={r_meas:.3f}  simulated={r_sim:.3f}')
        print(f'    Sim tracks measured: r={r_sv_m:.3f}  {"OK (r>0.3)" if r_sv_m > 0.3 else "WEAK"}')
        print(f'    Smoothness (std of dist-sorted diffs): meas={smooth_meas:.2f} dB  sim={smooth_sim:.2f} dB')

    # Per-device-per-tower detail
    print(f'\n  Per-tower continuity:')
    traj_rows = []
    for cell_id in df['tower_id'].unique():
        for dev in devices:
            sub = df[(df['tower_id'] == cell_id) & (df['device'] == dev)].sort_values('dist_m')
            if len(sub) < 3:
                continue
            r_sim, _ = pearsonr(sub['dist_m'], sub['simulated'])
            r_meas, _ = pearsonr(sub['dist_m'], sub['measured'])
            r_sv_m, _ = pearsonr(sub['measured'], sub['simulated'])
            mae = float(np.mean(np.abs(sub['residual'])))
            print(f'    Tower {cell_id} | {dev}: n={len(sub)}  '
                  f'r_dist_sim={r_sim:.3f}  r_dist_meas={r_meas:.3f}  '
                  f'r_sim_vs_meas={r_sv_m:.3f}  MAE={mae:.2f} dB')
            for _, row in sub.iterrows():
                traj_rows.append({
                    'tower_id':  cell_id,
                    'device':    dev,
                    'dist_m':    row['dist_m'],
                    'measured':  row['measured'],
                    'simulated': row['simulated'],
                    'residual':  row['residual'],
                    'lat':       row['lat'],
                    'lon':       row['lon'],
                })

    pd.DataFrame(traj_rows).to_csv(f'gz3_op{operator}_trajectories.csv', index=False)
    print(f'\n  Trajectories saved -> gz3_op{operator}_trajectories.csv')

    # ---- 5. Save summary ----------------------------------------------------
    summary = {
        'operator':       operator,
        'n_rows':         len(df),
        'n_towers':       int(df['tower_id'].nunique()),
        'offset_db':      offset_db,
        'baseline_mae':   baseline_mae,
        'baseline_rmse':  baseline_rmse,
        'devices':        devices,
        'flagged_device': flagged,
        'device_results': device_results,
        'bootstrap': {
            'best_device':        best_dev,
            'real_improvement':   real_imp,
            'null_mean':          float(null_arr.mean()),
            'null_std':           float(null_arr.std()),
            'percentile':         pctile,
            'significant':        pctile > 95,
            'flagged_percentile': flagged_pctile,
        },
        'continuity': continuity_results,
    }

    out = f'gz3_op{operator}_summary.json'
    with open(out, 'w') as f:
        json.dump(summary, f, indent=2)
    print(f'  Summary -> {out}')

    return summary


# ---- Main -------------------------------------------------------------------

def main():
    ops = [int(a) for a in sys.argv[1:]] if len(sys.argv) > 1 else [1, 2]
    summaries = {}
    for op in ops:
        summaries[op] = run_gz3_operator(op)

    print('\n' + '='*65)
    print('GZ-3  FINAL CROSS-OPERATOR SUMMARY')
    print('='*65)
    for op, s in summaries.items():
        if s is None:
            print(f'Op{op}: FAILED (no data)')
            continue
        b = s['bootstrap']
        flagged = s['flagged_device']
        print(f'\nOperator {op}:')
        print(f'  Baseline MAE  = {s["baseline_mae"]:.3f} dB  (n={s["n_rows"]}, {s["n_towers"]} towers)')
        print(f'  Leave-one-device-out results:')
        for dev, r in s['device_results'].items():
            tag = '<-- FLAGGED' if dev == flagged else ''
            print(f'    excl {dev}: MAE={r["mae"]:.3f} dB  imp={r["improvement"]:+.3f} dB  {tag}')
        print(f'  Best device to exclude: {b["best_device"]}  imp={b["real_improvement"]:+.3f} dB  '
              f'boot_pctile={b["percentile"]:.1f}%  '
              f'-> {"SIGNIFICANT" if b["significant"] else "NOT SIGNIFICANT"}')
        if flagged and b.get('flagged_percentile') is not None:
            print(f'  Flagged device ({flagged}) percentile: {b["flagged_percentile"]:.1f}%')
        print(f'  Continuity (sim RSRP decreases with distance from tower):')
        for dev, c in s['continuity'].items():
            ok = 'OK' if c['sim_plausible'] else 'FAIL'
            track = 'tracks' if c['sim_tracks_meas'] else 'weak'
            print(f'    {dev}: r_dist={c["rsrp_dist_corr_sim"]:.3f} [{ok}]  '
                  f'sim_vs_meas r={c["sim_vs_meas_corr"]:.3f} [{track}]')

    with open('gz3_combined_summary.json', 'w') as f:
        json.dump({str(k): v for k, v in summaries.items()}, f, indent=2)
    print('\nCombined summary -> gz3_combined_summary.json')


if __name__ == '__main__':
    main()
