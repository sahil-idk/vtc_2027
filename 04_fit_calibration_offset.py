"""
Stage 3 (of the pipeline): fit a single global additive calibration offset
per operator from the LOCALIZATION set.

Method:
  For each of the top N_TOWERS towers:
    1. Place transmitter at WCL position in scene local coordinates.
    2. Sample up to BATCH_SIZE * MAX_BATCHES localization-set receivers.
    3. Run PathSolver (no gradients).
    4. Derive simulated power from paths.a (real/imag parts).
    5. Collect residual = measured_RSRP - simulated_power per row.
  offset = mean(residuals) across all towers / rows for this operator.

CONSTRAINT (do not remove): offset is fit ONCE here and FROZEN afterward.
Co-optimizing offset jointly with position in gradient descent allows the
optimizer to cheat by absorbing position error into the offset rather than
finding a better position -- already flagged as a real failure mode.

Output: calibration_offsets.json  {operator -> {offset_db, std_db, n_samples}}
"""
import json
import math
import numpy as np
import pandas as pd
import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
import sionna.rt as rt
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, PathSolver

N_TOWERS    = 5    # use top N towers by n_obs (same as gradient prototype)
BATCH_SIZE  = 40   # receivers per PathSolver call (4 GB VRAM limit)
MAX_BATCHES = 3    # at most N_TOWERS * BATCH_SIZE * MAX_BATCHES samples
MAX_DIST_M  = 1800.0  # filter receivers beyond this from scene origin
TX_HEIGHT_M = 30.0
RX_HEIGHT_M = 1.5

# Scene origins: median Latitude/Longitude of each operator's measurements,
# exactly as computed by 03_build_sionna_scene.py's select_subarea_bbox().
SCENE_ORIGINS = {
    1: (52.507005, 13.323428),
    2: (52.506112, 13.321908),
}


def latlon_to_scene_xy(lat, lon, origin_lat, origin_lon):
    """
    Project geographic coordinates to the scene's local metric frame.
    Matches the exact formula in 03_build_sionna_scene.py:335-339.
    Returns (x_m, y_m) in metres from scene origin.
    """
    x = (lon - origin_lon) * 111_320.0 * math.cos(math.radians(origin_lat))
    y = (lat - origin_lat) * 111_320.0
    return x, y


def power_dbm_from_paths(paths):
    """
    Derive per-receiver received power in dBm from a Paths object.
    paths.a is (a_r, a_i), each TensorXf with shape
    (num_rx, num_rx_ant, num_tx, num_tx_ant, num_paths).
    Power = sum over paths of |a_r + j*a_i|^2, then 10*log10 + 30 dBm.
    """
    a_r_np = np.array(dr.detach(paths.a[0]))  # (num_rx, 1, 1, 1, num_paths)
    a_i_np = np.array(dr.detach(paths.a[1]))
    # Sum |a|^2 over paths (last axis), squeeze 3 antenna dims
    power_lin = (a_r_np**2 + a_i_np**2).sum(axis=-1).squeeze(axis=(1, 2, 3))  # (num_rx,)
    return 10.0 * np.log10(np.maximum(power_lin, 1e-30)) + 30.0


def run_batch(scene, tx_pos, rx_lats, rx_lons, origin_lat, origin_lon, solver):
    """
    One PathSolver call: place tx + receivers, run, return power_dbm, cleanup.
    """
    scene.add(Transmitter(name='tx_cal', position=[float(p) for p in tx_pos]))
    for i, (lat, lon) in enumerate(zip(rx_lats, rx_lons)):
        x, y = latlon_to_scene_xy(float(lat), float(lon), origin_lat, origin_lon)
        scene.add(Receiver(name=f'rx_cal_{i}', position=[float(x), float(y), RX_HEIGHT_M]))

    paths = solver(scene=scene, max_depth=5, diffraction=True)
    power = power_dbm_from_paths(paths)

    scene.remove('tx_cal')
    for i in range(len(rx_lats)):
        scene.remove(f'rx_cal_{i}')

    return power


def fit_operator(operator):
    origin_lat, origin_lon = SCENE_ORIGINS[operator]
    scene_path   = f'scene_operator{operator}/scene.xml'
    towers_csv   = f'op{operator}_towers_wcl_init.csv'
    meas_csv     = f'op{operator}_measurements.csv'

    print(f'\n=== Operator {operator} ===')
    print(f'  Scene: {scene_path} | origin=({origin_lat:.6f},{origin_lon:.6f})')

    scene = load_scene(scene_path)
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')

    towers = pd.read_csv(towers_csv).sort_values('n_obs', ascending=False)
    meas   = pd.read_csv(meas_csv)
    solver = PathSolver()
    all_residuals = []

    for _, tower in towers.head(N_TOWERS).iterrows():
        cell_id  = int(tower['cell_id'])
        wcl_lat  = tower['wcl_lat']
        wcl_lon  = tower['wcl_lon']
        tx_x, tx_y = latlon_to_scene_xy(wcl_lat, wcl_lon, origin_lat, origin_lon)

        print(f'  Tower {cell_id}: WCL=({wcl_lat:.5f},{wcl_lon:.5f})'
              f' -> scene ({tx_x:.0f},{tx_y:.0f}) m')

        loc = meas[(meas.PCell_Cell_Identity == cell_id) &
                   (meas.is_localization == True)].copy()
        if len(loc) == 0:
            print('    No localization rows, skipping')
            continue

        # Filter receivers outside scene bounds
        rx_x, rx_y = latlon_to_scene_xy(
            loc.Latitude.values, loc.Longitude.values, origin_lat, origin_lon)
        in_bounds = (np.abs(rx_x) < MAX_DIST_M) & (np.abs(rx_y) < MAX_DIST_M)
        loc = loc[in_bounds].reset_index(drop=True)

        n_target = BATCH_SIZE * MAX_BATCHES
        if len(loc) > n_target:
            rng = np.random.default_rng(cell_id % (2**32))
            idx = rng.choice(len(loc), size=n_target, replace=False)
            loc = loc.iloc[idx].reset_index(drop=True)

        print(f'    {len(loc)} rows after bounds/sampling filter')
        if len(loc) == 0:
            continue

        tower_residuals = []
        for start in range(0, len(loc), BATCH_SIZE):
            batch = loc.iloc[start:start + BATCH_SIZE]
            sim_pow = run_batch(
                scene, [float(tx_x), float(tx_y), TX_HEIGHT_M],
                batch.Latitude.values, batch.Longitude.values,
                origin_lat, origin_lon, solver
            )
            measured = batch.PCell_RSRP_max.values
            tower_residuals.extend((measured - sim_pow).tolist())

        mean_r = np.mean(tower_residuals)
        print(f'    Mean residual: {mean_r:.2f} dB  ({len(tower_residuals)} samples)')
        all_residuals.extend(tower_residuals)

    if not all_residuals:
        print(f'  ERROR: no residuals for operator {operator}')
        return None

    offset = float(np.mean(all_residuals))
    std    = float(np.std(all_residuals))
    n      = len(all_residuals)
    print(f'\n  Offset operator {operator}: {offset:.3f} dB  (std={std:.3f} dB, n={n})')
    return {'operator': operator, 'offset_db': offset, 'std_db': std, 'n_samples': n}


def main():
    results = {}
    for op in [1, 2]:
        r = fit_operator(op)
        if r:
            results[str(op)] = r

    out = 'calibration_offsets.json'
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)

    print('\n=== Summary ===')
    for op, r in results.items():
        print(f'  Op{op}: offset={r["offset_db"]:.3f} dB  std={r["std_db"]:.3f} dB  n={r["n_samples"]}')
    print(f'Saved -> {out}')


if __name__ == '__main__':
    main()
