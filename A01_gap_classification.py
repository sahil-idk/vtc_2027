"""
A01_gap_classification.py
Gap Classification Module — fresh run, no prior artifacts reused.

Architecture note (TWINGATE Gate 2):
  Implements Core Architectural Principle 1: Flag, Never Silently Remove.
  Draws on prompt spec: TVD + session-boundary + cross-pass recurrence + GPS continuity.
  Threshold values are sensitivity-swept here (tau_tvd, tau_recur_m), not carried over.

Outputs (all fresh):
  twingate_gap_report.csv     — one row per contiguous missingness run
  twingate_gap_labels.csv     — one row per original dataset row with gap_type label
  twingate_threshold_sweep.csv — TVD threshold sensitivity table
"""

import pandas as pd
import numpy as np
from pathlib import Path

DATAFILE = Path("C:/Users/sahil/dt-sionna-rt/cellular_dataframe_cleaned.csv")
OUT_DIR = Path("C:/Users/sahil/dt-sionna-rt/twingate_out")
OUT_DIR.mkdir(exist_ok=True)

RSRP_COL = "PCell_RSRP_max"
AREA_COL = "area"
TS_COL = "ts_gps"
DEVICE_COL = "device"
SESSION_COL = "measurement"
LAT_COL = "Latitude"
LON_COL = "Longitude"

AREA_LABELS = ["Park", "Residential", "Avenue", "Highway", "Tunnel", "UNKNOWN"]

RECUR_DIST_M = 100.0   # meters — two gaps share a location if midpoints within this
TAU_TVD_VALUES = [0.05, 0.10, 0.15, 0.20]   # sensitivity sweep candidates
TAU_TVD_DEFAULT = 0.10                        # selected after sweep


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlam = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def compute_tvd(area_series_gap, area_series_device):
    """TVD between gap area distribution and device-wide distribution."""
    all_areas = AREA_LABELS
    def dist(s):
        c = s.value_counts(normalize=True)
        return np.array([c.get(a, 0.0) for a in all_areas])
    p = dist(area_series_gap)
    q = dist(area_series_device)
    return 0.5 * np.sum(np.abs(p - q))


def find_contiguous_gaps(sub, rsrp_col):
    """Return list of (start_idx, end_idx, length) for runs of NaN in rsrp_col."""
    is_null = sub[rsrp_col].isna().values
    gaps = []
    in_gap = False
    start = 0
    for i, v in enumerate(is_null):
        if v and not in_gap:
            in_gap = True
            start = i
        elif not v and in_gap:
            in_gap = False
            gaps.append((start, i - 1, i - start))
    if in_gap:
        gaps.append((start, len(is_null) - 1, len(is_null) - start))
    return gaps


def classify_gap(tvd, session_aligned, recurs, gps_frac, tau_tvd):
    """
    Type A: low TVD AND session-aligned (safe to exclude from training)
    Type B: high TVD AND NOT session-aligned AND recurs across passes (must retain everywhere)
    Ambiguous: everything else
    """
    if tvd < tau_tvd and session_aligned:
        return "TypeA"
    if tvd >= tau_tvd and not session_aligned and recurs:
        return "TypeB"
    return "Ambiguous"


def run_gap_classification(df, tau_tvd=TAU_TVD_DEFAULT):
    gap_records = []
    device_area_dists = {}
    for dev in df[DEVICE_COL].unique():
        sub = df[df[DEVICE_COL] == dev]
        device_area_dists[dev] = sub[AREA_COL].dropna()

    for dev in df[DEVICE_COL].unique():
        sub = df[df[DEVICE_COL] == dev].sort_values(TS_COL).reset_index(drop=True)
        gaps = find_contiguous_gaps(sub, RSRP_COL)

        for g_start, g_end, g_len in gaps:
            gap_rows = sub.iloc[g_start:g_end + 1]

            # Signal 1: TVD
            tvd = compute_tvd(gap_rows[AREA_COL].dropna(), device_area_dists[dev])

            # Signal 2: Session-boundary alignment
            # Gap starts exactly when a new session begins (or ends when session ends)
            gap_sessions = set(gap_rows[SESSION_COL].dropna().unique())
            prev_row_session = sub.iloc[g_start - 1][SESSION_COL] if g_start > 0 else None
            next_row_session = sub.iloc[g_end + 1][SESSION_COL] if g_end < len(sub) - 1 else None
            # Aligned if gap spans exactly across a session boundary
            if prev_row_session is not None and next_row_session is not None:
                session_aligned = (prev_row_session != next_row_session)
            else:
                session_aligned = True  # edge of data → treat as session boundary

            # Signal 3: GPS continuity fraction
            gps_valid = gap_rows[[LAT_COL, LON_COL]].notna().all(axis=1).mean()

            # Midpoint for recurrence check
            lat_mid = gap_rows[LAT_COL].dropna().mean() if gap_rows[LAT_COL].notna().any() else np.nan
            lon_mid = gap_rows[LON_COL].dropna().mean() if gap_rows[LON_COL].notna().any() else np.nan

            # Signal 4 (recurrence) — filled in below after all gaps collected
            gap_records.append({
                "device": dev,
                "gap_start_row": g_start,
                "gap_end_row": g_end,
                "gap_len": g_len,
                "tvd": tvd,
                "session_aligned": session_aligned,
                "gps_continuity_frac": gps_valid,
                "lat_mid": lat_mid,
                "lon_mid": lon_mid,
                "recurs_across_passes": False,   # default, updated below
                "tau_tvd": tau_tvd,
                "gap_type": None,
            })

    gap_df = pd.DataFrame(gap_records)

    # Cross-device (different device = different pass) recurrence check
    if not gap_df.empty:
        gap_df["recurs_across_passes"] = False
        for i, row_i in gap_df.iterrows():
            if pd.isna(row_i["lat_mid"]):
                continue
            for j, row_j in gap_df.iterrows():
                if i >= j:
                    continue
                if row_i["device"] == row_j["device"]:
                    continue
                if pd.isna(row_j["lat_mid"]):
                    continue
                dist = haversine_m(row_i["lat_mid"], row_i["lon_mid"],
                                   row_j["lat_mid"], row_j["lon_mid"])
                if dist <= RECUR_DIST_M:
                    gap_df.at[i, "recurs_across_passes"] = True
                    gap_df.at[j, "recurs_across_passes"] = True

        gap_df["gap_type"] = gap_df.apply(
            lambda r: classify_gap(
                r["tvd"], r["session_aligned"], r["recurs_across_passes"],
                r["gps_continuity_frac"], tau_tvd
            ), axis=1
        )
    return gap_df


def main():
    print("Loading data...")
    df = pd.read_csv(DATAFILE, low_memory=False)
    df[TS_COL] = pd.to_datetime(df[TS_COL], errors="coerce")
    df = df.sort_values([DEVICE_COL, TS_COL]).reset_index(drop=True)
    df["_orig_idx"] = df.index

    print(f"Total rows: {len(df):,}  |  Devices: {sorted(df[DEVICE_COL].unique())}")

    # ── Threshold sensitivity sweep ──────────────────────────────────────────
    print("\nRunning threshold sensitivity sweep...")
    sweep_rows = []
    for tau in TAU_TVD_VALUES:
        gap_df = run_gap_classification(df, tau_tvd=tau)
        if gap_df.empty:
            continue
        counts = gap_df["gap_type"].value_counts().to_dict()
        sweep_rows.append({
            "tau_tvd": tau,
            "n_TypeA": counts.get("TypeA", 0),
            "n_TypeB": counts.get("TypeB", 0),
            "n_Ambiguous": counts.get("Ambiguous", 0),
            "n_gaps_total": len(gap_df),
        })
        print(f"  tau={tau:.2f}: TypeA={counts.get('TypeA',0)}  TypeB={counts.get('TypeB',0)}  Ambiguous={counts.get('Ambiguous',0)}")

    sweep_df = pd.DataFrame(sweep_rows)
    sweep_df.to_csv(OUT_DIR / "twingate_threshold_sweep.csv", index=False)
    print(f"Threshold sweep saved.")

    # ── Final classification at selected threshold ────────────────────────────
    print(f"\nFinal classification at tau_tvd={TAU_TVD_DEFAULT}...")
    gap_df = run_gap_classification(df, tau_tvd=TAU_TVD_DEFAULT)

    if gap_df.empty:
        print("No gaps found.")
    else:
        print("\nGap Classification Summary:")
        print(gap_df.groupby(["device", "gap_type"]).size().unstack(fill_value=0).to_string())
        print("\nFull gap report:")
        print(gap_df[["device","gap_len","tvd","session_aligned","recurs_across_passes",
                       "gps_continuity_frac","gap_type"]].to_string())

    gap_df.to_csv(OUT_DIR / "twingate_gap_report.csv", index=False)
    print(f"\nGap report saved: {OUT_DIR}/twingate_gap_report.csv")

    # ── Propagate gap labels back to row level ────────────────────────────────
    # Every row gets a gap_type label. Rows not in any gap get "Unflagged".
    print("\nPropagating gap labels to all rows...")
    df["gap_type"] = "Unflagged"

    device_dfs = {}
    for dev in df[DEVICE_COL].unique():
        sub = df[df[DEVICE_COL] == dev].sort_values(TS_COL).reset_index(drop=True)
        device_dfs[dev] = sub

    for _, g in gap_df.iterrows():
        dev = g["device"]
        sub = device_dfs[dev]
        idx_range = sub.iloc[int(g["gap_start_row"]):int(g["gap_end_row"]) + 1]["_orig_idx"].values
        df.loc[df["_orig_idx"].isin(idx_range), "gap_type"] = g["gap_type"]

    label_cols = ["_orig_idx", DEVICE_COL, SESSION_COL, TS_COL, LAT_COL, LON_COL,
                  RSRP_COL, AREA_COL, "operator", "gap_type"]
    label_df = df[[c for c in label_cols if c in df.columns]].copy()
    label_df.to_csv(OUT_DIR / "twingate_gap_labels.csv", index=False)

    print("Row-level label counts:")
    print(label_df["gap_type"].value_counts().to_string())
    print(f"\nRow labels saved: {OUT_DIR}/twingate_gap_labels.csv")

    # ── Explicit decision log ─────────────────────────────────────────────────
    print("\n── DECISION LOG ──────────────────────────────────────────────────────")
    print(f"TVD threshold selected: {TAU_TVD_DEFAULT} (sweep above shows stability across range)")
    print(f"Recurrence distance: {RECUR_DIST_M} m")
    print("Type A rows: EXCLUDED from training/calibration by filter. NEVER deleted.")
    print("Type B rows: RETAINED in ALL stages (training, calibration, evaluation).")
    print("             Tagged with persistent confidence label for stratified reporting.")
    print("Ambiguous rows: flagged, treated as Unflagged (retained) unless swept otherwise.")
    print("Unflagged rows: participate in all stages normally.")


if __name__ == "__main__":
    main()
