"""
A01_gap_classification.py — TWINGATE Gate 2, Step 1
Gap Classification Module. Fresh run; no prior artifacts reused.

Architecture: Core Architectural Principle 1 (Flag, Never Silently Remove).
Signals: TVD + session-boundary alignment + cross-pass recurrence + GPS continuity.
Threshold tau_tvd is sensitivity-swept; not carried over from any prior dataset.

Outputs → twingate/out/:
  gap_report.csv       one row per contiguous missingness run
  gap_labels.csv       one row per dataset row with gap_type label
  threshold_sweep.csv  TVD threshold sensitivity
"""

import pandas as pd
import numpy as np
from pathlib import Path

ROOT       = Path(__file__).parent.parent
DATAFILE   = ROOT / "cellular_dataframe_cleaned.csv"
OUT        = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

RSRP_COL   = "PCell_RSRP_max"
AREA_COL   = "area"
TS_COL     = "ts_gps"
DEVICE_COL = "device"
SESSION_COL = "measurement"
LAT_COL    = "Latitude"
LON_COL    = "Longitude"

AREA_LABELS       = ["Park", "Residential", "Avenue", "Highway", "Tunnel", "UNKNOWN"]
RECUR_DIST_M      = 100.0
TAU_TVD_SWEEP     = [0.05, 0.10, 0.15, 0.20]
TAU_TVD_SELECTED  = 0.10   # stable across sweep; see threshold_sweep.csv


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(phi1) * np.cos(phi2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(a))


def tvd(series_gap, series_device):
    def dist(s):
        c = s.value_counts(normalize=True)
        return np.array([c.get(a, 0.0) for a in AREA_LABELS])
    return 0.5 * np.sum(np.abs(dist(series_gap) - dist(series_device)))


def find_gaps(series):
    """Return list of (start_i, end_i) index positions for NaN runs."""
    null = series.isna().values
    gaps, in_gap, s = [], False, 0
    for i, v in enumerate(null):
        if v and not in_gap:
            in_gap, s = True, i
        elif not v and in_gap:
            in_gap = False
            gaps.append((s, i - 1))
    if in_gap:
        gaps.append((s, len(null) - 1))
    return gaps


def classify(tvd_val, session_aligned, recurs, tau):
    if tvd_val < tau and session_aligned:
        return "TypeA"
    if tvd_val >= tau and not session_aligned and recurs:
        return "TypeB"
    return "Ambiguous"


def run_classification(df, tau):
    dev_area = {d: g[AREA_COL].dropna()
                for d, g in df.groupby(DEVICE_COL)}

    records = []
    for dev, sub in df.groupby(DEVICE_COL):
        sub = sub.sort_values(TS_COL).reset_index(drop=True)
        gaps = find_gaps(sub[RSRP_COL])
        for s, e in gaps:
            gap_rows = sub.iloc[s:e + 1]
            tvd_val  = tvd(gap_rows[AREA_COL].dropna(), dev_area[dev])
            # Session-boundary: gap spans across a session change?
            prev_sess = sub.iloc[s - 1][SESSION_COL] if s > 0 else None
            next_sess = sub.iloc[e + 1][SESSION_COL] if e < len(sub) - 1 else None
            if prev_sess is None or next_sess is None:
                sess_aligned = True
            else:
                sess_aligned = (prev_sess != next_sess)
            lat_mid = gap_rows[LAT_COL].dropna().mean()
            lon_mid = gap_rows[LON_COL].dropna().mean()
            gps_frac = gap_rows[[LAT_COL, LON_COL]].notna().all(axis=1).mean()
            records.append(dict(
                device=dev, gap_start=s, gap_end=e, gap_len=e - s + 1,
                tvd=tvd_val, session_aligned=sess_aligned,
                gps_frac=gps_frac, lat_mid=lat_mid, lon_mid=lon_mid,
                recurs=False, gap_type=None, tau=tau
            ))

    gap_df = pd.DataFrame(records)
    if gap_df.empty:
        return gap_df

    # Cross-device (= cross-pass) recurrence
    for i in gap_df.index:
        if pd.isna(gap_df.at[i, "lat_mid"]):
            continue
        for j in gap_df.index:
            if j <= i or gap_df.at[i, "device"] == gap_df.at[j, "device"]:
                continue
            if pd.isna(gap_df.at[j, "lat_mid"]):
                continue
            if haversine_m(gap_df.at[i, "lat_mid"], gap_df.at[i, "lon_mid"],
                           gap_df.at[j, "lat_mid"], gap_df.at[j, "lon_mid"]) <= RECUR_DIST_M:
                gap_df.at[i, "recurs"] = True
                gap_df.at[j, "recurs"] = True

    gap_df["gap_type"] = gap_df.apply(
        lambda r: classify(r["tvd"], r["session_aligned"], r["recurs"], tau), axis=1)
    return gap_df


def main():
    print("A01 Gap Classification — loading data...")
    df = pd.read_csv(DATAFILE, low_memory=False)
    df[TS_COL] = pd.to_datetime(df[TS_COL], errors="coerce")
    df = df.sort_values([DEVICE_COL, TS_COL]).reset_index(drop=True)
    df["_row"] = df.index
    print(f"  Rows: {len(df):,}  |  Devices: {sorted(df[DEVICE_COL].unique())}")
    print(f"  PCell_RSRP_max nulls: {df[RSRP_COL].isna().sum():,} "
          f"({100*df[RSRP_COL].isna().mean():.2f}%)")

    # Threshold sweep
    print("\nThreshold sensitivity sweep:")
    sweep = []
    for tau in TAU_TVD_SWEEP:
        g = run_classification(df, tau)
        vc = g["gap_type"].value_counts().to_dict() if not g.empty else {}
        sweep.append(dict(tau=tau, TypeA=vc.get("TypeA", 0),
                          TypeB=vc.get("TypeB", 0),
                          Ambiguous=vc.get("Ambiguous", 0),
                          total=len(g)))
        print(f"  tau={tau:.2f}: TypeA={vc.get('TypeA',0)}  "
              f"TypeB={vc.get('TypeB',0)}  Ambiguous={vc.get('Ambiguous',0)}")
    pd.DataFrame(sweep).to_csv(OUT / "threshold_sweep.csv", index=False)

    # Final classification
    print(f"\nFinal classification at tau={TAU_TVD_SELECTED}:")
    gap_df = run_classification(df, TAU_TVD_SELECTED)
    print(gap_df.groupby(["device", "gap_type"]).size().unstack(fill_value=0).to_string())
    print("\nGap details:")
    print(gap_df[["device","gap_len","tvd","session_aligned",
                  "recurs","gps_frac","gap_type"]].to_string(index=False))
    gap_df.to_csv(OUT / "gap_report.csv", index=False)

    # Propagate labels to row level
    print("\nPropagating labels to all rows...")
    df["gap_type"] = "Unflagged"

    device_subs = {}
    for dev, sub in df.groupby(DEVICE_COL):
        device_subs[dev] = sub.sort_values(TS_COL).reset_index(drop=True)

    for _, g in gap_df.iterrows():
        sub = device_subs[g["device"]]
        orig_rows = sub.iloc[int(g["gap_start"]):int(g["gap_end"]) + 1]["_row"].values
        df.loc[df["_row"].isin(orig_rows), "gap_type"] = g["gap_type"]

    label_cols = ["_row", DEVICE_COL, SESSION_COL, TS_COL,
                  LAT_COL, LON_COL, RSRP_COL, AREA_COL, "operator", "gap_type"]
    labels = df[[c for c in label_cols if c in df.columns]]
    labels.to_csv(OUT / "gap_labels.csv", index=False)

    print("Row-level gap_type counts:")
    print(labels["gap_type"].value_counts().to_string())

    print(f"\nDecision log:")
    print(f"  tau_tvd={TAU_TVD_SELECTED}, recur_dist={RECUR_DIST_M}m")
    print("  TypeA → excluded from training/calibration only. Never deleted from dataset.")
    print("  TypeB → retained in ALL stages (train, calibrate, evaluate). Tagged persistently.")
    print("  Ambiguous → retained conservatively. Flagged for manual review.")
    print("  Unflagged → participates normally in all stages.")
    print(f"\nOutputs: {OUT}/gap_report.csv, {OUT}/gap_labels.csv, {OUT}/threshold_sweep.csv")


if __name__ == "__main__":
    main()
