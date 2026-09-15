"""
05_compute_coverage_score.py
------------------------------
Step-by-step, dataset-agnostic implementation of the Gate-1 coverage score
and structural-missingness check developed in GATE1_COVERAGE_ANALYSIS.md.

Replaces completeness-% as the primary Gate-1 readiness signal. Two things
computed per device/slice:

  1. FEATURE-SPACE COVERAGE SCORE
     - distance-bin coverage (entropy of the row distribution across
       distance-to-serving-tower bins)
     - band-diversity coverage (entropy of the row distribution across
       frequency bands actually observed)
     - composite = unweighted average of the two (placeholder weighting --
       see "Open Question" in GATE1_COVERAGE_ANALYSIS.md; calibrate against
       Gate-2 fidelity once available, don't just trust 50/50)

  2. STRUCTURAL MISSINGNESS CHECK
     - co-missingness: do multiple fields go missing TOGETHER (whole-row
       dropout) or independently (scattered field-level noise)?
     - run-length: is missingness concentrated in a few long contiguous
       gaps (equipment/connectivity outage signature) or scattered as many
       short/isolated single-row gaps (more consistent with random noise)?

Both are intentionally generic (distance + frequency band are basic
dimensions in ~any cellular/V2X dataset), so this should transfer to other
datasets with only the CONFIG section below changed.

Run:
    python 05_compute_coverage_score.py --input cellular_dataframe_cleaned_v2.csv
"""

from __future__ import annotations

import argparse
import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# CONFIG -- the only section that should need editing for a new dataset
# ---------------------------------------------------------------------------
GROUP_COL = "device"            # column identifying each device/slice to score
DISTANCE_COL = "distance_m"     # precomputed distance-to-serving-tower (see
                                 # compute_distance_to_tower() below if you
                                 # need to derive this from GPS + tower coords)
BAND_COL = "PCell_freq_MHz"     # frequency/band column
KEY_MISSINGNESS_COLS = [        # fields checked together for co-missingness
    "PCell_Cell_Identity", "PCell_RSRP_max", "PCell_RSRQ_max",
    "PCell_RSSI_max", "PCell_SNR_1",
]
TIME_COL = "timestamp"          # used to order rows for run-length analysis
                                 # (falls back to row order if not present/parseable)

# Distance bin edges in meters -- chosen to span typical urban-macro-cell
# near/mid/far regimes. Adjust for other deployment types (e.g. small cells,
# rural macro) since the "far" regime differs a lot by scenario.
DISTANCE_BINS = [0, 30, 60, 100, 150, 250, 500, 1000, 5000]


# ---------------------------------------------------------------------------
# Helper: derive distance-to-serving-tower if you don't already have it
# ---------------------------------------------------------------------------
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def compute_distance_to_tower(df: pd.DataFrame, towers: pd.DataFrame,
                               tower_key_cols: list[str]) -> pd.DataFrame:
    """towers must have tower_key_cols + ['tower_lat','tower_lon'].
    Merges onto df and adds a DISTANCE_COL column. Not called by default --
    use this if your dataset doesn't already have a distance column.
    """
    merged = df.merge(towers[tower_key_cols + ["tower_lat", "tower_lon"]],
                       on=tower_key_cols, how="inner")
    merged[DISTANCE_COL] = haversine_m(merged["Latitude"], merged["Longitude"],
                                        merged["tower_lat"], merged["tower_lon"])
    return merged


# ---------------------------------------------------------------------------
# Step 1: entropy-based coverage score
# ---------------------------------------------------------------------------
def normalized_entropy(counts: np.ndarray) -> float:
    """0 = all mass in one bin (no coverage diversity); 1 = perfectly even
    spread across however many bins/categories actually have any data."""
    counts = np.asarray(counts, dtype=float)
    counts = counts[counts > 0]
    if len(counts) <= 1:
        return 0.0
    p = counts / counts.sum()
    entropy = -(p * np.log(p)).sum()
    max_entropy = np.log(len(counts))
    return float(entropy / max_entropy) if max_entropy > 0 else 0.0


def coverage_score_for_group(g: pd.DataFrame) -> dict:
    g = g.dropna(subset=[DISTANCE_COL, BAND_COL])

    dist_binned = pd.cut(g[DISTANCE_COL], bins=DISTANCE_BINS)
    dist_counts = dist_binned.value_counts()
    distance_coverage = normalized_entropy(dist_counts.values)
    n_dist_bins_populated = int((dist_counts > 0).sum())

    band_counts = g[BAND_COL].value_counts()
    band_diversity = normalized_entropy(band_counts.values)
    n_bands = int(len(band_counts))

    composite = 0.5 * distance_coverage + 0.5 * band_diversity  # placeholder weighting

    return {
        "n_rows": len(g),
        "distance_bins_populated": f"{n_dist_bins_populated}/{len(DISTANCE_BINS) - 1}",
        "distance_coverage_entropy": round(distance_coverage, 3),
        "n_bands_seen": n_bands,
        "band_diversity_entropy": round(band_diversity, 3),
        "composite_coverage_score": round(composite, 3),
        "distance_range_m": (f"[{g[DISTANCE_COL].min():.0f}, "
                              f"{g[DISTANCE_COL].max():.0f}]") if len(g) else "n/a",
    }


# ---------------------------------------------------------------------------
# Step 2: structural missingness check (co-missingness + run-length)
# ---------------------------------------------------------------------------
def structural_missingness_for_group(g: pd.DataFrame) -> dict:
    present_cols = [c for c in KEY_MISSINGNESS_COLS if c in g.columns]
    miss = g[present_cols].isna()

    # Co-missingness: do the key fields go missing TOGETHER?
    # Measured as agreement rate between the anchor field's missingness
    # (first column, typically the cell/serving-station identifier) and
    # every other field's missingness.
    anchor = miss[present_cols[0]]
    co_missing_rates = {
        col: round((miss[col] == anchor).mean() * 100, 2) for col in present_cols[1:]
    }
    whole_row_dropout = all(rate > 95 for rate in co_missing_rates.values())

    # Run-length: are missing rows concentrated in a few long streaks
    # (equipment/connectivity outage) or scattered as many short streaks
    # (closer to random noise)?
    g_sorted = g.sort_values(TIME_COL) if TIME_COL in g.columns else g
    missing_flags = g_sorted[present_cols[0]].isna().values
    runs = []
    cur = 0
    for v in missing_flags:
        if v:
            cur += 1
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    runs = pd.Series(runs, dtype=float)

    n_missing_total = int(missing_flags.sum())
    n_gap_events = len(runs)
    median_run_length = float(runs.median()) if n_gap_events else 0.0
    max_run_length = float(runs.max()) if n_gap_events else 0.0
    is_structured = bool(n_gap_events > 0 and median_run_length > 3)

    return {
        "anchor_missing_pct": round(anchor.mean() * 100, 2),
        "co_missing_rates": co_missing_rates,
        "whole_row_dropout": whole_row_dropout,
        "n_missing_total": n_missing_total,
        "n_gap_events": n_gap_events,
        "median_gap_run_length": median_run_length,
        "max_gap_run_length": max_run_length,
        "missingness_pattern": ("STRUCTURED (equipment/connectivity-outage-like)"
                                 if is_structured else
                                 "scattered (more consistent with random noise)"),
    }


# ---------------------------------------------------------------------------
def main(input_csv: str):
    print(f"Loading {input_csv} ...")
    df = pd.read_csv(input_csv, low_memory=False)
    print(f"Loaded {df.shape[0]} rows x {df.shape[1]} cols")

    if DISTANCE_COL not in df.columns:
        raise SystemExit(
            f"Column '{DISTANCE_COL}' not found. This script expects distance-"
            f"to-serving-tower to already be computed (see "
            f"compute_distance_to_tower() docstring if you need to derive it "
            f"from GPS + a geolocated-towers table first)."
        )

    print("\n=== Step 1: Feature-space coverage score, per group ===")
    coverage_rows = []
    for name, g in df.groupby(GROUP_COL):
        row = {GROUP_COL: name}
        row.update(coverage_score_for_group(g))
        coverage_rows.append(row)
    coverage_df = pd.DataFrame(coverage_rows).sort_values(GROUP_COL)
    print(coverage_df.to_string(index=False))
    coverage_df.to_csv("gate1_coverage_score.csv", index=False)
    print("Saved -> gate1_coverage_score.csv")

    print("\n=== Step 2: Structural missingness check, per group ===")
    missing_rows = []
    for name, g in df.groupby(GROUP_COL):
        row = {GROUP_COL: name}
        row.update(structural_missingness_for_group(g))
        missing_rows.append(row)
    missing_df = pd.DataFrame(missing_rows).sort_values(GROUP_COL)
    print(missing_df.to_string(index=False))
    missing_df.to_csv("gate1_structural_missingness.csv", index=False)
    print("Saved -> gate1_structural_missingness.csv")

    print("\nDone. See GATE1_COVERAGE_ANALYSIS.md for the full narrative and "
          "the controlled experiments that motivated these two checks.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="cellular_dataframe_cleaned_v2.csv")
    args = ap.parse_args()
    main(args.input)
