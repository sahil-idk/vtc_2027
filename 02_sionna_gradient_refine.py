"""
Stage 2: tower-position refinement via Sionna RT ray-tracing.

Method: Nelder-Mead (gradient-free, black-box) optimization of transmitter
(x,y) position in the scene's local coordinate frame, using Sionna RT's
PathSolver as the forward oracle.

NOTE on differentiability: Sionna RT 2.0.1 / Dr.Jit 1.3.1's reverse-mode
autodiff through PathSolver requires that ALL internal Dr.Jit symbolic loops
have a bounded `max_iterations`. This is not yet satisfied end-to-end --
Mitsuba's C++ scene operations (BVH traversal, scene.ray_test) use Dr.Jit
custom ops with unbounded loops that cannot be patched from Python. Therefore
gradient-free optimization is used here as a correct and robust alternative:
same objective, same constraints, no backward-pass requirement.

Objective:
  MSE(measured_RSRP - (simulated_power_dbm + fixed_offset_db))
  on a random sample of LOCALIZATION-set rows (never validation rows).

CONSTRAINTS (do not modify):
- fixed_offset_db is fit once (by 04_fit_calibration_offset.py) and passed
  in frozen -- co-optimizing it jointly with position allows the optimizer to
  absorb position error into the offset instead of finding a better position.
- Only LOCALIZATION rows (is_localization == True) are ever used here.
- Hard displacement bound of MAX_DISPLACEMENT_M from the WCL initialization --
  the optimizer returns a large penalty if exceeded.
- Run only the 5 highest-n_obs prototype towers before scaling up.

Usage:
  python 02_sionna_gradient_refine.py <operator> <scene_path> <fixed_offset_db>
  python 02_sionna_gradient_refine.py 1 scene_operator1/scene.xml 45.2
"""
import sys
import math
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, PathSolver

# --- Tunable constants -------------------------------------------------------
MAX_DISPLACEMENT_M  = 150.0   # hard bound from WCL; flag + don't trust if hit
N_PROTOTYPE_TOWERS  = 5       # run prototype on top-N towers only
EVAL_BATCH_SIZE     = 40      # receivers per PathSolver call
EVAL_MAX_SAMPLES    = 120     # max localization rows sampled per evaluation
PENALTY_LOSS        = 1e6     # returned when displacement bound exceeded

# Nelder-Mead settings
NM_XATOL  = 1.0    # x tolerance in metres (stop if simplex size < 1 m)
NM_FATOL  = 0.01   # f tolerance in dB^2 (stop when loss changes < 0.01 dB^2)
NM_MAXITER = 200   # absolute iteration cap

TX_HEIGHT_M = 30.0
RX_HEIGHT_M = 1.5

# Scene origins (median lat/lon of each operator's measurements, exactly as
# computed by 03_build_sionna_scene.py:select_subarea_bbox).
SCENE_ORIGINS = {
    1: (52.507005, 13.323428),
    2: (52.506112, 13.321908),
}
# -----------------------------------------------------------------------------


def latlon_to_scene_xy(lat, lon, origin_lat, origin_lon):
    """Project lat/lon to scene local metric frame (same as build script)."""
    x = (lon - origin_lon) * 111_320.0 * math.cos(math.radians(origin_lat))
    y = (lat - origin_lat) * 111_320.0
    return x, y


def power_dbm_from_paths(paths):
    """
    Per-receiver power in dBm.
    paths.a = (a_r, a_i), each TensorXf (num_rx, 1, 1, 1, num_paths).
    Power = 10 * log10(sum_paths(|a|^2)) + 30 dBm.
    """
    a_r_np = np.array(dr.detach(paths.a[0]))  # (num_rx, 1, 1, 1, num_paths)
    a_i_np = np.array(dr.detach(paths.a[1]))
    power_lin = (a_r_np**2 + a_i_np**2).sum(axis=-1).squeeze(axis=(1, 2, 3))
    return 10.0 * np.log10(np.maximum(power_lin, 1e-30)) + 30.0


def eval_loss(dx_m, dy_m, scene, rx_lats, rx_lons, measured_rsrp,
              origin_lat, origin_lon, wcl_x, wcl_y,
              fixed_offset_db, solver):
    """
    Forward pass at transmitter offset (dx_m, dy_m) from WCL.
    Returns MSE(measured - (simulated + offset)) in dB^2.
    Applies displacement penalty if |displacement| > MAX_DISPLACEMENT_M.
    """
    # Displacement check
    if math.hypot(dx_m, dy_m) > MAX_DISPLACEMENT_M:
        return PENALTY_LOSS

    tx_x = wcl_x + dx_m
    tx_y = wcl_y + dy_m

    # Add transmitter
    scene.add(Transmitter(name='tx_opt', position=[float(tx_x), float(tx_y), TX_HEIGHT_M]))

    # Add receivers in batches and collect simulated power
    sim_powers = []
    n = len(rx_lats)
    for start in range(0, n, EVAL_BATCH_SIZE):
        end = min(start + EVAL_BATCH_SIZE, n)
        for i in range(end - start):
            xi, yi = latlon_to_scene_xy(float(rx_lats[start + i]), float(rx_lons[start + i]),
                                         origin_lat, origin_lon)
            scene.add(Receiver(name=f'rx_opt_{i}', position=[float(xi), float(yi), RX_HEIGHT_M]))

        paths = solver(scene=scene, max_depth=5, diffraction=True)
        sim_powers.extend(power_dbm_from_paths(paths).tolist())

        for i in range(end - start):
            scene.remove(f'rx_opt_{i}')

    scene.remove('tx_opt')

    sim_arr = np.array(sim_powers)
    residuals = measured_rsrp - (sim_arr + fixed_offset_db)
    return float(np.mean(residuals**2))


def refine_one_tower(scene, cell_id, wcl_lat, wcl_lon, loc_rows,
                     fixed_offset_db, origin_lat, origin_lon, solver):
    """
    Nelder-Mead optimization for one tower's (x,y) position.
    Returns a result dict with refined lat/lon, displacement, and diagnostics.
    """
    wcl_x, wcl_y = latlon_to_scene_xy(wcl_lat, wcl_lon, origin_lat, origin_lon)

    # Sample localization rows
    rng = np.random.default_rng(int(cell_id) % (2**32))
    n = min(len(loc_rows), EVAL_MAX_SAMPLES)
    if len(loc_rows) > n:
        idx = rng.choice(len(loc_rows), size=n, replace=False)
        sampled = loc_rows.iloc[idx].reset_index(drop=True)
    else:
        sampled = loc_rows.reset_index(drop=True)

    rx_lats     = sampled.Latitude.values
    rx_lons     = sampled.Longitude.values
    meas_rsrp   = sampled.PCell_RSRP_max.values

    eval_count = [0]
    loss_history = []

    def objective(params):
        dx, dy = float(params[0]), float(params[1])
        loss = eval_loss(dx, dy, scene, rx_lats, rx_lons, meas_rsrp,
                         origin_lat, origin_lon, wcl_x, wcl_y,
                         fixed_offset_db, solver)
        loss_history.append(loss)
        eval_count[0] += 1
        if eval_count[0] % 10 == 0:
            print(f'      iter {eval_count[0]:3d}: dx={dx:+7.1f} dy={dy:+7.1f}  loss={loss:.4f} dB^2')
        return loss

    # Initial simplex: start at WCL (0, 0) with ±10 m perturbations
    x0 = np.array([0.0, 0.0])
    result = minimize(
        objective,
        x0,
        method='Nelder-Mead',
        options={
            'xatol':   NM_XATOL,
            'fatol':   NM_FATOL,
            'maxiter': NM_MAXITER,
            'initial_simplex': np.array([[0.,0.],[10.,0.],[0.,10.]]),
        }
    )

    dx_final, dy_final = float(result.x[0]), float(result.x[1])
    displacement_m = math.hypot(dx_final, dy_final)

    # Convert local (dx, dy) back to lat/lon
    R = 6_371_000.0
    refined_lat = wcl_lat + np.degrees(dy_final / R)
    refined_lon = wcl_lon + np.degrees(dx_final / (R * math.cos(math.radians(wcl_lat))))

    return {
        'cell_id':              cell_id,
        'refined_lat':          refined_lat,
        'refined_lon':          refined_lon,
        'displacement_from_wcl_m': displacement_m,
        'n_iterations':         result.nit,
        'n_evaluations':        result.nfev,
        'final_loss':           float(result.fun),
        'converged':            result.success,
        'termination_msg':      result.message,
        'loss_history':         loss_history,
        'hit_displacement_bound': displacement_m >= MAX_DISPLACEMENT_M * 0.95,
    }


def main(operator, scene_path, fixed_offset_db):
    origin_lat, origin_lon = SCENE_ORIGINS[operator]
    print(f'\n=== Operator {operator} ===')
    print(f'  Scene: {scene_path}')
    print(f'  Fixed offset: {fixed_offset_db:.3f} dB')
    print(f'  Scene origin: ({origin_lat:.6f}, {origin_lon:.6f})')

    measurements = pd.read_csv(f'op{operator}_measurements.csv')
    towers = pd.read_csv(f'op{operator}_towers_wcl_init.csv').sort_values('n_obs', ascending=False)

    scene = load_scene(scene_path)
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    solver = PathSolver()

    results = []
    for _, row in towers.head(N_PROTOTYPE_TOWERS).iterrows():
        cell_id  = int(row['cell_id'])
        wcl_lat  = row['wcl_lat']
        wcl_lon  = row['wcl_lon']
        print(f'\n  --- Tower {cell_id} (n_obs={int(row["n_obs"])}) ---')

        loc_rows = measurements[
            (measurements.PCell_Cell_Identity == cell_id) &
            (measurements.is_localization == True)
        ]
        if len(loc_rows) == 0:
            print('    No localization rows, skipping')
            continue

        print(f'    WCL=({wcl_lat:.5f},{wcl_lon:.5f}), {len(loc_rows)} localization rows')
        result = refine_one_tower(
            scene, cell_id, wcl_lat, wcl_lon, loc_rows,
            fixed_offset_db, origin_lat, origin_lon, solver
        )
        results.append(result)
        print(f'    Displacement: {result["displacement_from_wcl_m"]:.1f} m'
              f'  Converged: {result["converged"]}'
              f'  Evals: {result["n_evaluations"]}'
              f'  Final loss: {result["final_loss"]:.4f} dB^2')
        if result['hit_displacement_bound']:
            print('    WARNING: hit displacement bound -- likely diverging, do not trust')

    out_path = f'op{operator}_refined_towers_prototype.csv'
    out_df = pd.DataFrame([{k: v for k, v in r.items() if k != 'loss_history'}
                            for r in results])
    out_df.to_csv(out_path, index=False)
    print(f'\nSaved {out_path}')
    return results


if __name__ == '__main__':
    operator       = int(sys.argv[1])   if len(sys.argv) > 1 else 1
    scene_path     = sys.argv[2]         if len(sys.argv) > 2 else f'scene_operator{operator}/scene.xml'
    fixed_offset_db = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0
    main(operator, scene_path, fixed_offset_db)
