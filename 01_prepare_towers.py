"""
Stage 1 of the tower-refinement pipeline: operator filtering, WCL initialization,
and deterministic localization/validation split -- everything needed BEFORE
Sionna's differentiable optimization runs.

This script is fully self-contained and runs on plain pandas/numpy -- no Sionna
dependency. Run it first, on either machine; its output feeds directly into
02_sionna_gradient_refine.py.

Usage: python3 01_prepare_towers.py <path_to_cellular_dataframe_cleaned_v2.csv> <operator: 1 or 2>
"""
import sys
import pandas as pd
import numpy as np
import hashlib

MIN_OBS_PER_CELL = 5          # matches earlier WCL threshold -- see GZ-8 for sensitivity sweep obligation
LOCALIZATION_FRACTION = 0.6   # 60/40 split, matches established Gate-2 discipline


def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def deterministic_split(cell_id, n_rows, frac=LOCALIZATION_FRACTION):
    """
    Deterministic per-cell seeding, per the established discipline: reproducible,
    not dependent on global row order, and stable if the script is rerun.
    """
    seed_material = f"cell_{cell_id}".encode()
    seed = int(hashlib.sha256(seed_material).hexdigest(), 16) % (2**32)
    rng = np.random.default_rng(seed)
    idx = np.arange(n_rows)
    rng.shuffle(idx)
    n_loc = int(round(frac * n_rows))
    is_localization = np.zeros(n_rows, dtype=bool)
    is_localization[idx[:n_loc]] = True
    return is_localization


def wcl_estimate(lat, lon, rsrp_dbm):
    w = 10 ** (rsrp_dbm / 10.0)
    return np.average(lat, weights=w), np.average(lon, weights=w)


def main(csv_path, operator_filter):
    print(f"Loading {csv_path} ...")
    df = pd.read_csv(csv_path, low_memory=False)

    # --- operator filter ---
    df = df[df.operator == operator_filter].copy()
    print(f"Operator {operator_filter}: {len(df)} rows before completeness filter")

    # --- keep only rows with everything needed ---
    need = ['Latitude', 'Longitude', 'PCell_RSRP_max', 'PCell_Cell_Identity', 'PCell_freq_MHz', 'device']
    d = df[need].dropna().copy()
    d['PCell_Cell_Identity'] = d['PCell_Cell_Identity'].astype(int)
    print(f"Rows with complete Lat/Lon/RSRP/CellIdentity/freq: {len(d)}")

    # --- restrict to cells with enough observations for a stable WCL init ---
    counts = d.PCell_Cell_Identity.value_counts()
    valid_cells = counts[counts >= MIN_OBS_PER_CELL].index
    d = d[d.PCell_Cell_Identity.isin(valid_cells)].reset_index(drop=True)
    print(f"Cells with >= {MIN_OBS_PER_CELL} obs: {len(valid_cells)} | rows retained: {len(d)}")

    # --- per-cell WCL init + deterministic split ---
    records = []
    split_flags = np.zeros(len(d), dtype=bool)
    for cell_id, group in d.groupby('PCell_Cell_Identity'):
        idx = group.index.to_numpy()
        wcl_lat, wcl_lon = wcl_estimate(group.Latitude.values, group.Longitude.values, group.PCell_RSRP_max.values)
        is_loc = deterministic_split(cell_id, len(idx))
        split_flags[idx] = is_loc
        records.append({
            'cell_id': int(cell_id),
            'n_obs': len(idx),
            'wcl_lat': wcl_lat,
            'wcl_lon': wcl_lon,
            'n_localization': int(is_loc.sum()),
            'n_validation': int((~is_loc).sum()),
        })

    d['is_localization'] = split_flags
    d['split'] = np.where(d['is_localization'], 'localization', 'validation')

    towers = pd.DataFrame(records).sort_values('n_obs', ascending=False).reset_index(drop=True)

    print(f"\nTowers prepared: {len(towers)}")
    print(towers.head(10).to_string(index=False))
    print(f"\nLocalization/validation split check (should be ~60/40):")
    print(d.split.value_counts(normalize=True).round(3))

    out_rows = f'op{operator_filter}_measurements.csv'
    out_towers = f'op{operator_filter}_towers_wcl_init.csv'
    d.merge(towers[['cell_id', 'wcl_lat', 'wcl_lon']], left_on='PCell_Cell_Identity', right_on='cell_id') \
     .to_csv(out_rows, index=False)
    towers.to_csv(out_towers, index=False)
    print(f"\nSaved: {out_rows}")
    print(f"Saved: {out_towers}")
    return d, towers


if __name__ == '__main__':
    csv_path = sys.argv[1] if len(sys.argv) > 1 else 'cellular_dataframe_cleaned_v2.csv'
    operator = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    main(csv_path, operator)
