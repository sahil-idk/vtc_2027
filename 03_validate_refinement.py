"""
Stage 3: does the gradient-refined position actually improve anything, or did
it just find a plausible-looking local minimum that doesn't generalize?

*** NOT EXECUTED -- depends on Stage 2's output, which requires Sionna ***
Structurally complete and ready to run once Stage 2 produces real refined
positions. Every check here reuses a pattern already validated elsewhere in
this project (GZ-3's leave-one-out + bootstrap null, the -0.1 RSRP-distance
plausibility check, the WCL parameter-sensitivity sweep) -- consistent
methodology, not new philosophy per tower-refinement step.

Six checks, each answering a distinct "did this actually work" question:

1. Convergence diagnostics       -- did the optimizer actually converge, or
                                     stop on iteration limit / oscillate?
2. Held-out MAE improvement      -- THE test that matters: is validation-set
                                     error lower with the refined position
                                     than with plain WCL?
3. Displacement sanity check     -- did it move a physically plausible
                                     distance, or hit the divergence bound?
4. Multi-start robustness        -- does it converge to the same place from
                                     a jittered initialization?
5. Plausibility check (reused)   -- does RSRP still decrease with distance
                                     from the refined position, on held-out
                                     data, at least as well as WCL did?
6. Bootstrap significance        -- is the improvement distinguishable from
                                     what random WCL perturbation of similar
                                     magnitude would produce by chance?

A tower's refinement should only be TRUSTED (used in place of WCL downstream)
if it passes checks 1, 2, 5, and 6. Checks 3 and 4 are diagnostic /
early-warning, not pass/fail gates on their own.
"""
import numpy as np
import pandas as pd
from scipy.stats import pearsonr


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1); dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi/2)**2 + np.cos(p1)*np.cos(p2)*np.sin(dlambda/2)**2
    return 2*R*np.arcsin(np.sqrt(a))


def check1_convergence(refined_row):
    """Did it converge cleanly, or hit the iteration cap / never stabilize?"""
    return {
        'converged': refined_row['converged'],
        'n_iterations': refined_row['n_iterations'],
        'flag': 'OK' if refined_row['converged'] else 'DID NOT CONVERGE -- hit iteration cap, do not trust'
    }


def check2_holdout_mae(val_rows, wcl_lat, wcl_lon, refined_lat, refined_lon, sim_power_fn):
    """
    THE core test. sim_power_fn(lat, lon, tower_lat, tower_lon) must call your
    actual Sionna forward pass (frozen, no gradient) on the VALIDATION rows --
    never the localization rows used to fit the refined position.
    """
    measured = val_rows.PCell_RSRP_max.values
    pred_wcl = sim_power_fn(val_rows.Latitude.values, val_rows.Longitude.values, wcl_lat, wcl_lon)
    pred_refined = sim_power_fn(val_rows.Latitude.values, val_rows.Longitude.values, refined_lat, refined_lon)

    mae_wcl = np.mean(np.abs(measured - pred_wcl))
    mae_refined = np.mean(np.abs(measured - pred_refined))
    return {
        'mae_wcl_db': mae_wcl,
        'mae_refined_db': mae_refined,
        'improvement_db': mae_wcl - mae_refined,
        'flag': 'IMPROVED' if mae_refined < mae_wcl else 'NO IMPROVEMENT -- refinement not justified for this tower'
    }


def check3_displacement(refined_row, max_displacement_m=150.0):
    d = refined_row['displacement_from_wcl_m']
    flag = 'OK'
    if d >= max_displacement_m * 0.95:
        flag = 'HIT DISPLACEMENT BOUND -- likely diverging, do not trust without investigation'
    elif d < 1.0:
        flag = 'NEGLIGIBLE MOVEMENT -- refinement found nothing, WCL was already fine here'
    return {'displacement_m': d, 'flag': flag}


def check4_multistart_robustness(cell_id, refine_fn, wcl_lat, wcl_lon, n_starts=3, jitter_m=30.0):
    """Rerun Stage 2's refine_one_tower from n_starts jittered initializations.
    refine_fn must be Stage 2's refine_one_tower, imported and called here."""
    rng = np.random.default_rng(hash(cell_id) % (2**32))
    results = []
    for _ in range(n_starts):
        dlat = rng.normal(0, jitter_m) / 111000
        dlon = rng.normal(0, jitter_m) / (111000 * np.cos(np.radians(wcl_lat)))
        r = refine_fn(wcl_lat + dlat, wcl_lon + dlon)
        results.append((r['refined_lat'], r['refined_lon']))
    positions = np.array(results)
    spread_m = haversine(positions[:, 0].mean(), positions[:, 1].mean(),
                          positions[:, 0], positions[:, 1]).max()
    return {
        'multistart_spread_m': spread_m,
        'flag': 'STABLE' if spread_m < 20.0 else 'UNSTABLE -- different starts converge to different places, loss landscape is multimodal for this tower, do not trust'
    }


def check5_plausibility(val_rows, tower_lat, tower_lon, correlation_threshold=-0.1):
    """Reuses the existing established check: does RSRP decrease with distance
    from this tower, on held-out data? Same threshold as the existing WCL
    plausibility check (-0.1) -- apply identically to the refined position."""
    dist = haversine(val_rows.Latitude.values, val_rows.Longitude.values, tower_lat, tower_lon)
    r, _ = pearsonr(dist, val_rows.PCell_RSRP_max.values)
    return {
        'rsrp_distance_correlation': r,
        'flag': 'PLAUSIBLE' if r < correlation_threshold else 'IMPLAUSIBLE -- RSRP does not decrease with distance from this position, low-confidence flag'
    }


def check6_bootstrap_significance(val_rows, wcl_lat, wcl_lon, refined_lat, refined_lon,
                                    sim_power_fn, n_boot=200, seed=42):
    """
    Is the improvement in check2 bigger than what you'd get by randomly
    perturbing WCL by the SAME displacement magnitude, in a random direction?
    Directly mirrors GZ-3's leave-one-out bootstrap-null logic, applied here
    to position refinement instead of device exclusion.
    """
    rng = np.random.default_rng(seed)
    measured = val_rows.PCell_RSRP_max.values
    real_displacement_m = haversine(wcl_lat, wcl_lon, refined_lat, refined_lon)

    real_mae = np.mean(np.abs(measured - sim_power_fn(val_rows.Latitude.values, val_rows.Longitude.values,
                                                        refined_lat, refined_lon)))
    wcl_mae = np.mean(np.abs(measured - sim_power_fn(val_rows.Latitude.values, val_rows.Longitude.values,
                                                       wcl_lat, wcl_lon)))
    real_improvement = wcl_mae - real_mae

    null_improvements = np.empty(n_boot)
    for i in range(n_boot):
        angle = rng.uniform(0, 2 * np.pi)
        dlat = (real_displacement_m * np.cos(angle)) / 111000
        dlon = (real_displacement_m * np.sin(angle)) / (111000 * np.cos(np.radians(wcl_lat)))
        rand_lat, rand_lon = wcl_lat + dlat, wcl_lon + dlon
        rand_mae = np.mean(np.abs(measured - sim_power_fn(val_rows.Latitude.values, val_rows.Longitude.values,
                                                            rand_lat, rand_lon)))
        null_improvements[i] = wcl_mae - rand_mae

    pctile = (null_improvements < real_improvement).mean() * 100
    return {
        'real_improvement_db': real_improvement,
        'null_mean_db': null_improvements.mean(),
        'null_std_db': null_improvements.std(),
        'percentile': pctile,
        'flag': 'SIGNIFICANT' if pctile > 95 else 'NOT DISTINGUISHABLE FROM RANDOM DISPLACEMENT -- gradient did not find genuine structure'
    }


def run_all_checks(cell_id, refined_row, val_rows, wcl_lat, wcl_lon, sim_power_fn, refine_fn=None):
    print(f"\n=== Validation report: cell {cell_id} ===")
    c1 = check1_convergence(refined_row); print("1. Convergence:      ", c1)
    c2 = check2_holdout_mae(val_rows, wcl_lat, wcl_lon,
                             refined_row['refined_lat'], refined_row['refined_lon'], sim_power_fn)
    print("2. Held-out MAE:     ", c2)
    c3 = check3_displacement(refined_row); print("3. Displacement:     ", c3)
    c5 = check5_plausibility(val_rows, refined_row['refined_lat'], refined_row['refined_lon'])
    print("5. Plausibility:     ", c5)
    c6 = check6_bootstrap_significance(val_rows, wcl_lat, wcl_lon,
                                        refined_row['refined_lat'], refined_row['refined_lon'], sim_power_fn)
    print("6. Bootstrap sig.:   ", c6)

    trust = c1['converged'] and c2['flag'] == 'IMPROVED' and c5['flag'] == 'PLAUSIBLE' and c6['flag'] == 'SIGNIFICANT'
    print(f"\n--> TRUST REFINEMENT: {trust}")
    return {'cell_id': cell_id, 'trust': trust, **c1, **c2, **c3, **c5, **c6}


if __name__ == '__main__':
    print("This module is meant to be imported and called per-tower after Stage 2 runs.")
    print("See run_all_checks() for the full per-tower report.")
