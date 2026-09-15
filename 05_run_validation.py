"""
Stage 4: Validation runner for prototype refined tower positions.
Runs checks 1, 2, 3, 5, 6 from 03_validate_refinement.py's methodology.
Check 4 (multi-start) is skipped for the prototype (too expensive).

Usage:
  python 05_run_validation.py <operator>

Prototype limits:
  - MAX_VAL_ROWS = 40   (one PathSolver call per forward pass)
  - N_BOOT = 50         (bootstrap null sample)
"""
import sys
import math
import numpy as np
import pandas as pd
from scipy.stats import pearsonr

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, PathSolver

TX_HEIGHT_M = 30.0
RX_HEIGHT_M = 1.5
MAX_VAL_ROWS = 40   # cap: keeps each forward pass to exactly one PathSolver call
N_BOOT       = 50   # bootstrap null iterations (prototype; use 200 for full run)

SCENE_ORIGINS = {
    1: (52.507005, 13.323428),
    2: (52.506112, 13.321908),
}


# ---- geometry helpers -------------------------------------------------------

def latlon_to_scene_xy(lat, lon, origin_lat, origin_lon):
    x = (lon - origin_lon) * 111_320.0 * math.cos(math.radians(origin_lat))
    y = (lat - origin_lat) * 111_320.0
    return x, y


def haversine(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi    = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dlambda/2)**2
    return 2*R*np.arcsin(np.sqrt(a))


# ---- Sionna forward pass ----------------------------------------------------

def power_dbm_from_paths(paths):
    a_r = np.array(dr.detach(paths.a[0]))
    a_i = np.array(dr.detach(paths.a[1]))
    plin = (a_r**2 + a_i**2).sum(axis=-1).squeeze(axis=(1, 2, 3))
    return 10.0 * np.log10(np.maximum(plin, 1e-30)) + 30.0


def sim_power(rx_lats, rx_lons, tower_lat, tower_lon,
              scene, solver, origin_lat, origin_lon):
    """
    Single PathSolver call: simulate received power (dBm) at rx positions
    from a transmitter at (tower_lat, tower_lon).
    ASSUMES len(rx_lats) <= 40 (one-batch constraint for prototype).
    """
    tx_x, tx_y = latlon_to_scene_xy(tower_lat, tower_lon, origin_lat, origin_lon)
    scene.add(Transmitter(name='tx_v', position=[float(tx_x), float(tx_y), TX_HEIGHT_M]))
    for i, (lat, lon) in enumerate(zip(rx_lats, rx_lons)):
        xi, yi = latlon_to_scene_xy(float(lat), float(lon), origin_lat, origin_lon)
        scene.add(Receiver(name=f'rx_v_{i}', position=[float(xi), float(yi), RX_HEIGHT_M]))

    paths = solver(scene=scene, max_depth=5, diffraction=True)
    power = power_dbm_from_paths(paths)

    scene.remove('tx_v')
    for i in range(len(rx_lats)):
        scene.remove(f'rx_v_{i}')
    return power


# ---- Checks (inlined from 03_validate_refinement.py) ------------------------

def check1_convergence(ref_row):
    return {
        'converged': bool(ref_row['converged']),
        'n_iterations': int(ref_row['n_iterations']),
        'flag': 'OK' if ref_row['converged'] else 'DID NOT CONVERGE',
    }


def check2_holdout_mae(val_rows, wcl_lat, wcl_lon, ref_lat, ref_lon,
                       scene, solver, origin_lat, origin_lon):
    rlat = val_rows.Latitude.values
    rlon = val_rows.Longitude.values
    measured = val_rows.PCell_RSRP_max.values
    pred_wcl     = sim_power(rlat, rlon, wcl_lat, wcl_lon, scene, solver, origin_lat, origin_lon)
    pred_refined = sim_power(rlat, rlon, ref_lat,  ref_lon,  scene, solver, origin_lat, origin_lon)
    mae_wcl     = float(np.mean(np.abs(measured - pred_wcl)))
    mae_refined = float(np.mean(np.abs(measured - pred_refined)))
    imp = mae_wcl - mae_refined
    return {
        'mae_wcl_db':     mae_wcl,
        'mae_refined_db': mae_refined,
        'improvement_db': imp,
        'flag': 'IMPROVED' if imp > 0 else 'NO IMPROVEMENT',
    }


def check3_displacement(ref_row, max_m=150.0):
    d = float(ref_row['displacement_from_wcl_m'])
    if d >= max_m * 0.95:
        flag = 'HIT DISPLACEMENT BOUND'
    elif d < 1.0:
        flag = 'NEGLIGIBLE MOVEMENT'
    else:
        flag = 'OK'
    return {'displacement_m': d, 'flag': flag}


def check5_plausibility(val_rows, tower_lat, tower_lon, threshold=-0.1):
    dist = haversine(val_rows.Latitude.values, val_rows.Longitude.values, tower_lat, tower_lon)
    r, _ = pearsonr(dist, val_rows.PCell_RSRP_max.values)
    return {
        'rsrp_distance_correlation': float(r),
        'flag': 'PLAUSIBLE' if r < threshold else 'IMPLAUSIBLE',
    }


def check6_bootstrap(val_rows, wcl_lat, wcl_lon, ref_lat, ref_lon,
                     scene, solver, origin_lat, origin_lon,
                     n_boot=N_BOOT, seed=42):
    rng = np.random.default_rng(seed)
    rlat = val_rows.Latitude.values
    rlon = val_rows.Longitude.values
    measured = val_rows.PCell_RSRP_max.values

    disp_m = float(haversine(wcl_lat, wcl_lon, ref_lat, ref_lon))

    mae_wcl     = float(np.mean(np.abs(measured - sim_power(rlat, rlon, wcl_lat, wcl_lon, scene, solver, origin_lat, origin_lon))))
    mae_refined = float(np.mean(np.abs(measured - sim_power(rlat, rlon, ref_lat,  ref_lon,  scene, solver, origin_lat, origin_lon))))
    real_imp = mae_wcl - mae_refined

    null_imps = []
    for i in range(n_boot):
        angle = rng.uniform(0, 2*math.pi)
        dlat = (disp_m * math.cos(angle)) / 111_000.0
        dlon = (disp_m * math.sin(angle)) / (111_000.0 * math.cos(math.radians(wcl_lat)))
        rand_lat, rand_lon = wcl_lat + dlat, wcl_lon + dlon
        rand_mae = float(np.mean(np.abs(measured - sim_power(rlat, rlon, rand_lat, rand_lon, scene, solver, origin_lat, origin_lon))))
        null_imps.append(mae_wcl - rand_mae)
        if (i+1) % 10 == 0:
            print(f'      boot {i+1}/{n_boot}: null_imp={null_imps[-1]:.3f} dB')

    null_imps = np.array(null_imps)
    pctile = float((null_imps < real_imp).mean() * 100)
    return {
        'real_improvement_db': real_imp,
        'null_mean_db':        float(null_imps.mean()),
        'null_std_db':         float(null_imps.std()),
        'percentile':          pctile,
        'flag': 'SIGNIFICANT' if pctile > 95 else 'NOT SIGNIFICANT',
    }


# ---- Main -------------------------------------------------------------------

def main(operator):
    origin_lat, origin_lon = SCENE_ORIGINS[operator]
    print(f'\n=== Validation: Operator {operator} ===')

    refined_df = pd.read_csv(f'op{operator}_refined_towers_prototype.csv')
    towers_df  = pd.read_csv(f'op{operator}_towers_wcl_init.csv')
    meas_df    = pd.read_csv(f'op{operator}_measurements.csv')

    scene = load_scene(f'scene_operator{operator}/scene.xml')
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    solver = PathSolver()

    all_results = []

    for _, ref_row in refined_df.iterrows():
        cell_id = int(ref_row['cell_id'])
        wcl_row = towers_df[towers_df.cell_id == cell_id].iloc[0]
        wcl_lat = float(wcl_row['wcl_lat'])
        wcl_lon = float(wcl_row['wcl_lon'])
        ref_lat = float(ref_row['refined_lat'])
        ref_lon = float(ref_row['refined_lon'])

        val_all = meas_df[
            (meas_df.PCell_Cell_Identity == cell_id) &
            (meas_df.is_localization == False)
        ].reset_index(drop=True)

        print(f'\n=== Cell {cell_id}: {len(val_all)} validation rows ===')

        # Check 1 and 3 don't need Sionna
        c1 = check1_convergence(ref_row)
        c3 = check3_displacement(ref_row)
        print(f'  Check 1 (convergence):  {c1}')
        print(f'  Check 3 (displacement): {c3}')

        if len(val_all) == 0:
            print('  No validation rows -- skipping checks 2, 5, 6')
            all_results.append({'cell_id': cell_id, 'trust': False, 'reason': 'no_val_rows',
                                 **c1, **c3})
            continue

        # Sample up to MAX_VAL_ROWS for Sionna checks
        rng = np.random.default_rng(cell_id % (2**32))
        if len(val_all) > MAX_VAL_ROWS:
            idx = rng.choice(len(val_all), size=MAX_VAL_ROWS, replace=False)
            val_rows = val_all.iloc[idx].reset_index(drop=True)
        else:
            val_rows = val_all

        print(f'  Using {len(val_rows)} val rows for checks 2, 5, 6')

        # Check 5 (no Sionna needed)
        c5 = check5_plausibility(val_rows, ref_lat, ref_lon)
        print(f'  Check 5 (plausibility): {c5}')

        # Check 2 (2 Sionna calls)
        print('  Running check 2 (held-out MAE)...')
        c2 = check2_holdout_mae(val_rows, wcl_lat, wcl_lon, ref_lat, ref_lon,
                                 scene, solver, origin_lat, origin_lon)
        print(f'  Check 2 (held-out MAE): {c2}')

        # Check 6 (N_BOOT+2 Sionna calls)
        print(f'  Running check 6 (bootstrap n={N_BOOT})...')
        c6 = check6_bootstrap(val_rows, wcl_lat, wcl_lon, ref_lat, ref_lon,
                               scene, solver, origin_lat, origin_lon)
        print(f'  Check 6 (bootstrap):    {c6}')

        trust = (c1['converged'] and
                 c2['flag'] == 'IMPROVED' and
                 c5['flag'] == 'PLAUSIBLE' and
                 c6['flag'] == 'SIGNIFICANT')
        print(f'\n  --> TRUST REFINEMENT: {trust}')

        all_results.append({
            'cell_id':          cell_id,
            'trust':            trust,
            'converged':        c1['converged'],
            'displacement_m':   c3['displacement_m'],
            'disp_flag':        c3['flag'],
            'mae_wcl_db':       c2['mae_wcl_db'],
            'mae_refined_db':   c2['mae_refined_db'],
            'improvement_db':   c2['improvement_db'],
            'mae_flag':         c2['flag'],
            'rsrp_dist_corr':   c5['rsrp_distance_correlation'],
            'plaus_flag':       c5['flag'],
            'boot_pctile':      c6['percentile'],
            'boot_flag':        c6['flag'],
            'wcl_lat':          wcl_lat,
            'wcl_lon':          wcl_lon,
            'refined_lat':      ref_lat,
            'refined_lon':      ref_lon,
        })

    out = f'op{operator}_validation_report.csv'
    pd.DataFrame(all_results).to_csv(out, index=False)
    print(f'\nSaved -> {out}')

    print('\n=== FINAL SUMMARY ===')
    trusted = [r for r in all_results if r.get('trust')]
    print(f'Trusted towers: {len(trusted)}/{len(all_results)}')
    for r in all_results:
        imp_str = f"{r.get('improvement_db', 'N/A'):.2f} dB" if isinstance(r.get('improvement_db'), float) else 'N/A'
        print(f"  Cell {r['cell_id']}: TRUST={r['trust']}  imp={imp_str}  "
              f"boot={r.get('boot_pctile', 'N/A')}%  "
              f"disp={r.get('displacement_m', 'N/A'):.1f} m  "
              f"{r.get('disp_flag', '')} | {r.get('mae_flag', '')} | {r.get('plaus_flag', '')} | {r.get('boot_flag', '')}")


if __name__ == '__main__':
    operator = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    main(operator)
