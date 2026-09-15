"""
02_estimate_towers_from_data.py  (v2 -- adds consistency check, organized output folder)
---------------------------------------------------------------------------
WHY THIS SCRIPT EXISTS, AND WHY IT REPLACES THE EARLIER OPENCELLID-BASED ONE
---------------------------------------------------------------------------
Sionna RT (or any ray tracer) needs an explicit 3D position for both ends
of a link -- this is a physics requirement, not a design choice. The V2X
dataset only logs the UE (vehicle) side: real, GPS-measured
Latitude/Longitude, plus which cell tower it was connected to
(PCell_Cell_Identity etc.) and what it measured from that connection
(RSRP, RSRQ, SNR...). The tower's OWN physical position is never in the
dataset -- that's infrastructure-side information a UE-side logging app
has no access to.

The earlier version of this step looked the tower's position up in an
external database (OpenCelliD). That approach had two real problems:
  1. It's a manual, fragile, country-specific dependency -- roughly half
     of our towers had no match at all in OpenCelliD's crowdsourced data.
  2. It doesn't belong in a "proper architecture" meant to generalize
     across arbitrary V2X datasets.

THIS SCRIPT INSTEAD ESTIMATES EACH TOWER'S POSITION DIRECTLY FROM THE
DATASET ITSELF, using Weighted Centroid Localization (WCL): every time the
vehicle connects to a given cell, that's a real GPS fix "near" that
tower. Collect enough such fixes, weight each one by how STRONG the
measured signal was (stronger signal implies the vehicle was physically
closer to the tower at that moment), and the weighted average position of
all those fixes is a reasonable estimate of the tower's true location.

NOTE ON AN ALTERNATIVE APPROACH CONSIDERED AND RULED OUT: some published
drive-test datasets (e.g. the Vienna 4G/5G Drive-Test Dataset, Wiedner et
al. 2026) localize towers using Timing Advance (TA) -- a network-reported
round-trip-delay value that converts directly to a real distance, giving
much better accuracy (they report 38.55m RMSE against ground truth) than
RSRP-based methods can achieve, since TA doesn't depend on an assumed
path-loss model the way RSRP-to-distance conversion would. We checked: the
Berlin V2X dataset used here has NO Timing Advance column (confirmed by
directly inspecting all 171 columns) and no other distance-related field.
This is a genuine dataset limitation, not a gap in our method -- TA-based
localization is structurally impossible here, so RSRP-weighted centroid
is the correct fallback (and notably, it's also what the Vienna paper
itself falls back to for 5G NR cells, where TA-based grouping isn't
possible either -- so we're in the same well-precedented position their
own 5G NR estimation is in, just for our whole dataset).

---------------------------------------------------------------------------
THE CIRCULARITY RISK, AND HOW THIS SCRIPT AVOIDS IT
---------------------------------------------------------------------------
If we used a cell's RSRP measurements to ESTIMATE that cell's tower
position, and then LATER used those same measurements' RSRP values to
check whether Sionna's ray-traced prediction matches reality, we would
partly be validating the data against a position that was itself derived
from that same data -- a circular argument that proves nothing.

The fix: for every cell, we split its rows into two DISJOINT groups before
doing anything else:
  - LOCALIZATION SET: used ONLY to estimate the tower's position here.
  - VALIDATION SET: held out, untouched by the localization step -- the
    ONLY rows 03_build_sionna_scene.py is allowed to sample from.

---------------------------------------------------------------------------
NEW IN THIS VERSION: RSRP-MONOTONICITY CONSISTENCY CHECK
---------------------------------------------------------------------------
Since we have no independent ground truth to validate our tower position
estimates against (unlike the Vienna paper's TA-validated subset), the
best available substitute is an INTERNAL consistency check -- the same
epistemic fallback the Vienna paper itself uses for its un-validated 5G NR
estimates. The physical expectation, if a tower's estimated position is
roughly correct: measurements taken FARTHER from that estimated position
should show WEAKER (more negative) RSRP, on average -- signal strength
should fall off with distance. We test this directly: compute the
correlation between each localization row's distance-from-the-estimated-
centroid and its RSRP. A meaningfully negative correlation supports the
estimate being physically sensible; a near-zero or positive correlation
is a red flag that this particular tower's estimate is unreliable (e.g.
too few fixes, fixes clustered in a way that doesn't triangulate well, or
a data quality issue specific to that cell) and it gets flagged
accordingly rather than silently trusted at the same confidence as every
other tower.

Run: python 02_estimate_towers_from_data.py
"""

from __future__ import annotations
import math
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# KNOBS -- the things you might reasonably want to tune
# ---------------------------------------------------------------------------

CLEANED_CSV = "cellular_dataframe_cleaned_v2.csv"

# All Gate-2 testbed outputs (tower estimates, the augmented dataset, and
# -- from 03_build_sionna_scene.py onward -- the OSM cache, 3D scenes, and
# Sionna predictions) now live under this single folder instead of being
# scattered across the working directory. Keeps the growing number of
# pipeline artifacts organized and makes it obvious what belongs to this
# testbed vs. earlier Gate-1 outputs.
OUTPUT_DIR = Path("gate2_testbed")

# A cell needs at least this many Gate-1-clean rows total before we'll even
# attempt to estimate its tower's position at all. Below this, the
# localization/validation split would leave too few rows in either half to
# be meaningful, so we mark the tower as "insufficient data" rather than
# guessing from too little evidence.
MIN_ROWS_FOR_ESTIMATION = 20

# Fraction of a cell's rows randomly assigned to the LOCALIZATION set (used
# to estimate tower position). The remainder becomes the VALIDATION set
# (held out for Gate-2 Sionna comparison later).
LOCALIZATION_FRACTION = 0.6

# A tower's RSRP-vs-distance correlation must be more negative than this
# threshold to be considered "consistent" (physically sensible: signal
# weakens with distance from the estimated position). Towers that fail
# this check are still saved (never silently dropped) but flagged with
# position_confidence = "low" so downstream steps can choose to exclude
# them or treat their results with extra caution.
CONSISTENCY_CORRELATION_THRESHOLD = -0.1

RANGE_FLAG_COLS = [
    "FLAG_range_PCell_RSRP_max", "FLAG_range_PCell_RSRQ_max",
    "FLAG_range_PCell_RSSI_max", "FLAG_range_PCell_SNR_1",
]

CELL_ID_COLS = ["operator", "PCell_MCC", "PCell_MNC", "PCell_TAC", "PCell_Cell_Identity"]


# ---------------------------------------------------------------------------
def haversine_m(lat1, lon1, lat2, lon2):
    """Great-circle distance in metres between two lat/lon points."""
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def stable_seed_for_cell(cell_key: tuple) -> int:
    """Deterministic, reproducible per-cell random seed -- see v1 docstring
    for why this matters (reproducible splits regardless of row order)."""
    key_str = "_".join(str(x) for x in cell_key)
    return int(hashlib.md5(key_str.encode()).hexdigest(), 16) % (2**31)


def estimate_tower_position(localization_rows: pd.DataFrame) -> dict:
    """The core Weighted Centroid Localization (WCL) calculation, now also
    returning the RSRP-vs-distance consistency check described above.
    """
    lat = localization_rows["Latitude"].values
    lon = localization_rows["Longitude"].values
    rsrp = localization_rows["PCell_RSRP_max"].values

    # 10**(RSRP_dBm/10) as the weight -- see v1 docstring: the standard
    # dBm-to-watts "-30" offset cancels out of the normalized weighted
    # average, so this simpler form gives identical relative weights.
    weights = 10 ** (rsrp / 10.0)

    est_lat = float(np.sum(weights * lat) / np.sum(weights))
    est_lon = float(np.sum(weights * lon) / np.sum(weights))

    distances = haversine_m(lat, lon, est_lat, est_lon)
    weighted_spread_m = float(np.sum(weights * distances) / np.sum(weights))

    # --- NEW: RSRP-monotonicity consistency check ---
    # Pearson correlation between each fix's distance from the estimated
    # centroid and its measured RSRP. Physically, we expect this to be
    # NEGATIVE: farther away should mean weaker signal. We only compute
    # this if there's enough variation in distance to make a correlation
    # meaningful (all fixes at ~identical distance would make any
    # correlation numerically unstable and uninformative).
    if len(distances) >= 5 and np.std(distances) > 1.0:
        correlation = float(np.corrcoef(distances, rsrp)[0, 1])
    else:
        correlation = np.nan

    if np.isnan(correlation):
        position_confidence = "unknown"
    elif correlation < CONSISTENCY_CORRELATION_THRESHOLD:
        position_confidence = "high"
    else:
        position_confidence = "low"

    return {
        "tower_lat": est_lat,
        "tower_lon": est_lon,
        "weighted_spread_m": round(weighted_spread_m, 1),
        "n_localization_rows": len(localization_rows),
        "rsrp_distance_correlation": round(correlation, 3) if not np.isnan(correlation) else np.nan,
        "position_confidence": position_confidence,
    }


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)
    print(f"Output folder: {OUTPUT_DIR.resolve()}")

    print(f"\nLoading {CLEANED_CSV} ...")
    df = pd.read_csv(CLEANED_CSV, low_memory=False)
    print(f"Loaded {df.shape[0]} rows")

    clean_mask = ~df[RANGE_FLAG_COLS].any(axis=1)
    df_clean = df[clean_mask].dropna(subset=CELL_ID_COLS[1:] + ["Latitude", "Longitude", "PCell_RSRP_max"])
    print(f"{len(df_clean)} rows are Gate-1-clean with a valid cell ID, GPS position, and RSRP")

    df["tower_estimate_group"] = "excluded"

    tower_rows = []
    n_towers_estimated = 0
    n_towers_insufficient = 0
    n_towers_low_confidence = 0

    for cell_key, group in df_clean.groupby(CELL_ID_COLS):
        if len(group) < MIN_ROWS_FOR_ESTIMATION:
            n_towers_insufficient += 1
            continue

        seed = stable_seed_for_cell(cell_key)
        rng = np.random.RandomState(seed)
        is_localization = rng.rand(len(group)) < LOCALIZATION_FRACTION

        localization_rows = group[is_localization]
        validation_rows = group[~is_localization]

        if len(localization_rows) < 5 or len(validation_rows) < 5:
            n_towers_insufficient += 1
            continue

        estimate = estimate_tower_position(localization_rows)
        estimate.update(dict(zip(CELL_ID_COLS, cell_key)))
        estimate["n_validation_rows"] = len(validation_rows)
        tower_rows.append(estimate)
        n_towers_estimated += 1
        if estimate["position_confidence"] == "low":
            n_towers_low_confidence += 1

        df.loc[localization_rows.index, "tower_estimate_group"] = "localization"
        df.loc[validation_rows.index, "tower_estimate_group"] = "validation"

    print(f"\nTowers estimated: {n_towers_estimated}")
    print(f"  of which LOW CONFIDENCE (RSRP does not decrease with distance "
          f"as expected): {n_towers_low_confidence}")
    print(f"Towers with insufficient data (skipped, not guessed): {n_towers_insufficient}")

    towers_df = pd.DataFrame(tower_rows)

    for op in sorted(towers_df["operator"].unique()):
        op_towers = towers_df[towers_df["operator"] == op]
        out_path = OUTPUT_DIR / f"towers_operator{op}_estimated.csv"
        op_towers.to_csv(out_path, index=False)
        n_low = (op_towers["position_confidence"] == "low").sum()
        print(f"  Operator {op}: {len(op_towers)} towers -> {out_path} "
              f"({n_low} low-confidence)")
        print(f"    median weighted_spread_m = {op_towers['weighted_spread_m'].median():.1f}m, "
              f"median rsrp_distance_correlation = "
              f"{op_towers['rsrp_distance_correlation'].median():.3f}")

    out_csv = OUTPUT_DIR / "cellular_dataframe_with_tower_groups.csv"
    df.to_csv(out_csv, index=False)
    print(f"\nSaved full dataset with tower_estimate_group column -> {out_csv}")
    print(df["tower_estimate_group"].value_counts())


if __name__ == "__main__":
    main()
