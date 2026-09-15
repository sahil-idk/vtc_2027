"""
G1_completeness.py — Gate 1 Evaluation
Computes TypeA/TypeB gap statistics and completeness score for the paper.

Protocol:
  1. Split data by date: train = June 22-23, val = June 24
  2. Re-classify gaps using ONLY training data (temporal hold-out integrity)
     TypeA: gap aligns with a lap/session boundary (measurement changes)
     TypeB: gap recurs across at least 2 independent vehicles at the same
            geographic location (within RECUR_DIST_M) on training days
  3. Build training TypeB map (geographic cluster centroids)
  4. Detect all gaps on val day
  5. Match each val-day gap to the training TypeB map
  6. Completeness C = (val gaps at TypeB locations) / (all val gaps)

Outputs:
  out/g1_summary.json        — paper numbers
  out/g1_train_typeb.csv     — training TypeB cluster centroids
  out/g1_val_gaps.csv        — val-day gap events with match labels
  out/g1_full_report.csv     — all gap events with date/type labels
"""

import json, math
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "out"

DATAFILE     = ROOT / "cellular_dataframe_cleaned.csv"
RSRP_COL     = "PCell_RSRP_max"
TS_COL       = "ts_gps"
DEVICE_COL   = "device"
SESSION_COL  = "measurement"
LAT_COL      = "Latitude"
LON_COL      = "Longitude"
OPERATOR_COL = "operator"

TRAIN_DATES  = {"2021-06-22", "2021-06-23"}
VAL_DATE     = "2021-06-24"

# TypeB: gap centroid must match across ≥ MIN_VEHICLES vehicles
RECUR_DIST_M    = 100.0   # metres — cluster radius for TypeB matching
MIN_VEHICLES    = 2       # number of distinct vehicles to confirm TypeB
MIN_GAP_ROWS    = 1       # minimum gap length (rows) to count
MAX_GAP_ROWS    = 2000    # longer silences = vehicle stop, not radio gap

print("=" * 60)
print("G1  —  Gate 1 Completeness Evaluation")
print("=" * 60)


# ── Helpers ───────────────────────────────────────────────────────────────────
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(phi1) * np.cos(phi2)
         * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def detect_gaps(sub):
    """
    Find contiguous NaN runs in RSRP for a single (device, date) group.
    Returns list of dicts with gap metadata.
    """
    null  = sub[RSRP_COL].isna().values
    lats  = sub[LAT_COL].values
    lons  = sub[LON_COL].values
    sess  = sub[SESSION_COL].values
    rows  = sub.index.values

    gaps, in_gap, s = [], False, 0
    for i, v in enumerate(null):
        if v and not in_gap:
            in_gap, s = True, i
        elif not v and in_gap:
            in_gap = False
            length = i - s
            if MIN_GAP_ROWS <= length <= MAX_GAP_ROWS:
                gap_lats = lats[s:i]
                gap_lons = lons[s:i]
                valid    = ~(np.isnan(gap_lats) | np.isnan(gap_lons))
                lat_mid  = float(gap_lats[valid].mean()) if valid.any() else np.nan
                lon_mid  = float(gap_lons[valid].mean()) if valid.any() else np.nan
                # Session boundary: does gap span a measurement change?
                prev_sess = sess[s - 1] if s > 0 else None
                next_sess = sess[i]     if i < len(sess) else None
                sess_boundary = (prev_sess is not None and
                                 next_sess is not None and
                                 prev_sess != next_sess)
                gaps.append(dict(
                    gap_len=length, lat_mid=lat_mid, lon_mid=lon_mid,
                    sess_boundary=sess_boundary,
                ))
    if in_gap:
        length = len(null) - s
        if MIN_GAP_ROWS <= length <= MAX_GAP_ROWS:
            gap_lats = lats[s:]
            gap_lons = lons[s:]
            valid    = ~(np.isnan(gap_lats) | np.isnan(gap_lons))
            lat_mid  = float(gap_lats[valid].mean()) if valid.any() else np.nan
            lon_mid  = float(gap_lons[valid].mean()) if valid.any() else np.nan
            gaps.append(dict(gap_len=length, lat_mid=lat_mid, lon_mid=lon_mid,
                             sess_boundary=True))
    return gaps


def classify_gaps_for_period(period_df, label="train"):
    """
    Detect and classify gaps for a given time period.
    Returns a DataFrame of gap events with TypeA/TypeB labels.
    """
    records = []
    for (dev, op), grp in period_df.groupby([DEVICE_COL, OPERATOR_COL]):
        grp = grp.sort_values(TS_COL).reset_index(drop=True)
        for g in detect_gaps(grp):
            records.append(dict(device=dev, operator=int(op), period=label, **g))
    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # TypeA: session-boundary gap (HO / RLF proxy — measurement column changes)
    df["type_a"] = df["sess_boundary"]

    # Cross-vehicle recurrence: for each pair of gaps from different vehicles,
    # mark both if they are within RECUR_DIST_M
    df["recurs_vehicles"] = 0
    lats = df["lat_mid"].values
    lons = df["lon_mid"].values
    devs = df["device"].values

    for i in range(len(df)):
        if np.isnan(lats[i]):
            continue
        matched_devs = set()
        for j in range(len(df)):
            if i == j or devs[i] == devs[j] or np.isnan(lats[j]):
                continue
            if haversine_m(lats[i], lons[i], lats[j], lons[j]) <= RECUR_DIST_M:
                matched_devs.add(devs[j])
        df.at[i, "recurs_vehicles"] = len(matched_devs)

    # TypeB: NOT session-boundary AND recurs across ≥ MIN_VEHICLES other vehicles
    df["type_b"] = (~df["type_a"]) & (df["recurs_vehicles"] >= MIN_VEHICLES - 1)

    df["gap_type"] = "Ambiguous"
    df.loc[df["type_a"], "gap_type"] = "TypeA"
    df.loc[df["type_b"], "gap_type"] = "TypeB"

    return df


def build_typeb_clusters(train_gaps):
    """
    Cluster TypeB gap centroids from training into distinct geographic holes.
    Returns DataFrame with one row per cluster, with centroid and vehicle count.
    """
    tb = train_gaps[train_gaps["gap_type"] == "TypeB"].dropna(
        subset=["lat_mid", "lon_mid"])
    if tb.empty:
        return pd.DataFrame()

    coords = tb[["lat_mid", "lon_mid"]].values

    # Convert to metres for clustering
    olat, olon = coords[:, 0].mean(), coords[:, 1].mean()
    xs = (coords[:, 1] - olon) * 111_320 * math.cos(math.radians(olat))
    ys = (coords[:, 0] - olat) * 111_320
    xy = np.column_stack([xs, ys])

    if len(xy) < 2:
        tb = tb.copy()
        tb["cluster"] = 0
    else:
        Z      = linkage(xy, method="single")
        labels = fcluster(Z, t=RECUR_DIST_M, criterion="distance") - 1
        tb = tb.copy()
        tb["cluster"] = labels

    clusters = []
    for cid, grp in tb.groupby("cluster"):
        clusters.append(dict(
            cluster_id     = int(cid),
            operator       = int(grp["operator"].mode()[0]),
            n_gaps         = int(len(grp)),
            n_vehicles     = int(grp["device"].nunique()),
            centroid_lat   = float(grp["lat_mid"].mean()),
            centroid_lon   = float(grp["lon_mid"].mean()),
            lat_std_m      = float(grp["lat_mid"].std() * 111_320) if len(grp) > 1 else 0.0,
        ))
    return pd.DataFrame(clusters)


def match_val_to_typeb(val_gaps, typeb_clusters):
    """
    For each val-day gap, check if it falls within RECUR_DIST_M of a training TypeB cluster.
    Returns val_gaps DataFrame with 'matches_typeb' column.
    """
    if typeb_clusters.empty:
        val_gaps = val_gaps.copy()
        val_gaps["matches_typeb"] = False
        return val_gaps

    clat = typeb_clusters["centroid_lat"].values
    clon = typeb_clusters["centroid_lon"].values

    def check(row):
        if np.isnan(row["lat_mid"]) or np.isnan(row["lon_mid"]):
            return False
        for i in range(len(clat)):
            if haversine_m(row["lat_mid"], row["lon_mid"], clat[i], clon[i]) <= RECUR_DIST_M:
                return True
        return False

    val_gaps = val_gaps.copy()
    val_gaps["matches_typeb"] = val_gaps.apply(check, axis=1)
    return val_gaps


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("Loading dataset...")
    df = pd.read_csv(DATAFILE, low_memory=False,
                     usecols=[DEVICE_COL, TS_COL, SESSION_COL,
                               LAT_COL, LON_COL, RSRP_COL, OPERATOR_COL])
    df[TS_COL] = pd.to_datetime(df[TS_COL], unit="s", errors="coerce")
    if df[TS_COL].isna().all():
        # Try string parse
        df[TS_COL] = pd.to_datetime(pd.read_csv(
            DATAFILE, low_memory=False, usecols=[TS_COL])[TS_COL], errors="coerce")

    df["date_str"] = df[TS_COL].dt.strftime("%Y-%m-%d")
    print(f"  Total rows: {len(df):,}")
    print(f"  Dates: {sorted(df['date_str'].dropna().unique())}")

    train_df = df[df["date_str"].isin(TRAIN_DATES)].copy()
    val_df   = df[df["date_str"] == VAL_DATE].copy()
    print(f"  Train rows: {len(train_df):,}  |  Val rows: {len(val_df):,}")

    # ── Step 1: classify training gaps ───────────────────────────────────────
    print("\nClassifying training gaps (days 1-2)...")
    train_gaps = classify_gaps_for_period(train_df, label="train")
    print(f"  Total train gaps detected: {len(train_gaps)}")
    if not train_gaps.empty:
        print(train_gaps.groupby(["operator", "gap_type"]).size().to_string())

    # ── Step 2: build TypeB cluster map from training ─────────────────────────
    print("\nBuilding TypeB coverage-hole map from training...")
    typeb_clusters = build_typeb_clusters(train_gaps)
    print(f"  TypeB clusters: {len(typeb_clusters)}")
    if not typeb_clusters.empty:
        print(typeb_clusters[["cluster_id","operator","n_gaps",
                               "n_vehicles","centroid_lat","centroid_lon",
                               "lat_std_m"]].to_string(index=False))

    # ── Step 3: detect all val-day gaps ─────────────────────────────────────
    print("\nDetecting val-day gaps (day 3)...")
    val_gaps = classify_gaps_for_period(val_df, label="val")
    print(f"  Total val gaps detected: {len(val_gaps)}")
    if not val_gaps.empty:
        print(val_gaps.groupby(["device", "gap_type"]).size().to_string())

    # ── Step 4: match val gaps to training TypeB map ─────────────────────────
    if not val_gaps.empty:
        val_gaps = match_val_to_typeb(val_gaps, typeb_clusters)

    # ── Step 5: compute completeness ──────────────────────────────────────────
    print("\n" + "=" * 60)
    n_train_typea  = int((train_gaps["gap_type"] == "TypeA").sum()) if not train_gaps.empty else 0
    n_train_typeb  = int((train_gaps["gap_type"] == "TypeB").sum()) if not train_gaps.empty else 0
    n_train_ambig  = int((train_gaps["gap_type"] == "Ambiguous").sum()) if not train_gaps.empty else 0
    n_typeb_clusters = len(typeb_clusters)

    n_val_total    = len(val_gaps)

    # C is defined over TypeB val gaps only (paper Eq. 3):
    # C = |TypeB val gaps that match training TypeB cluster| / |TypeB val gaps|
    # TypeA and Ambiguous val gaps are excluded from both numerator and denominator.
    val_typeb = val_gaps[val_gaps["gap_type"] == "TypeB"] if not val_gaps.empty else pd.DataFrame()
    n_val_typeb        = len(val_typeb)
    n_val_matched      = int(val_typeb["matches_typeb"].sum()) if not val_typeb.empty else 0
    n_val_unmatched    = n_val_typeb - n_val_matched

    completeness = n_val_matched / n_val_typeb if n_val_typeb > 0 else 0.0

    # Cluster recall: fraction of training TypeB clusters with ≥1 val-day gap
    if not typeb_clusters.empty and not val_gaps.empty:
        matched_val = val_gaps[val_gaps["matches_typeb"]]
        clat = typeb_clusters["centroid_lat"].values
        clon = typeb_clusters["centroid_lon"].values
        cluster_matched = []
        for i in range(len(clat)):
            hit = any(
                haversine_m(r["lat_mid"], r["lon_mid"], clat[i], clon[i]) <= RECUR_DIST_M
                for _, r in matched_val.iterrows()
                if not np.isnan(r["lat_mid"])
            )
            cluster_matched.append(hit)
        cluster_recall = sum(cluster_matched) / len(cluster_matched)
    else:
        cluster_recall = 0.0

    print("GATE 1 RESULTS")
    print(f"  Training TypeA gaps : {n_train_typea}")
    print(f"  Training TypeB gaps : {n_train_typeb}")
    print(f"  Training Ambiguous  : {n_train_ambig}")
    print(f"  TypeB clusters (train): {n_typeb_clusters}")
    print()
    print(f"  Val-day total gaps  : {n_val_total}  (all types)")
    print(f"  Val-day TypeB gaps  : {n_val_typeb}  (denominator for C)")
    print(f"  Val TypeB matched   : {n_val_matched}  (within {RECUR_DIST_M}m of training cluster)")
    print(f"  Val TypeB unmatched : {n_val_unmatched}")
    print()
    print(f"  Completeness C      : {completeness:.4f}  ({n_val_matched}/{n_val_typeb})")
    print(f"  Cluster recall      : {cluster_recall:.3f}  ({100*cluster_recall:.1f}%)")

    # Per-operator breakdown
    print("\nPer-operator breakdown:")
    for op in [1, 2]:
        tr_tb = train_gaps[(train_gaps["gap_type"]=="TypeB") & (train_gaps["operator"]==op)] if not train_gaps.empty else pd.DataFrame()
        # Per-operator C also uses TypeB-only denominator
        vg_op = val_gaps[(val_gaps["operator"]==op) & (val_gaps["gap_type"]=="TypeB")] if not val_gaps.empty else pd.DataFrame()
        vg_m  = vg_op[vg_op["matches_typeb"]] if not vg_op.empty and "matches_typeb" in vg_op.columns else pd.DataFrame()
        c_op  = len(vg_m)/len(vg_op) if len(vg_op) > 0 else float('nan')
        print(f"  Op{op}: train TypeB={len(tr_tb)}  val_gaps={len(vg_op)}  "
              f"matched={len(vg_m)}  C={c_op:.2f}" if not math.isnan(c_op) else
              f"  Op{op}: train TypeB={len(tr_tb)}  val_gaps={len(vg_op)}  matched={len(vg_m)}  C=N/A")

    # Spatial stability of TypeB clusters
    if not typeb_clusters.empty:
        print(f"\nTypeB cluster spatial spread (lat_std): "
              f"{typeb_clusters['lat_std_m'].mean():.1f}m mean")

    # ── Save outputs ──────────────────────────────────────────────────────────
    summary = {
        "train_typea_gaps":      n_train_typea,
        "train_typeb_gaps":      n_train_typeb,
        "train_ambiguous_gaps":  n_train_ambig,
        "typeb_clusters":        n_typeb_clusters,
        "val_total_gaps":        n_val_total,
        "val_typeb_gaps":        n_val_typeb,
        "val_typeb_matched":     n_val_matched,
        "val_typeb_unmatched":   n_val_unmatched,
        "completeness_C":        round(completeness, 4),
        "completeness_C_formula": f"{n_val_matched}/{n_val_typeb}",
        "cluster_recall":        round(cluster_recall, 4),
    }
    with open(OUT / "g1_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    if not typeb_clusters.empty:
        typeb_clusters.to_csv(OUT / "g1_train_typeb.csv", index=False)
    if not val_gaps.empty:
        val_gaps.to_csv(OUT / "g1_val_gaps.csv", index=False)

    all_gaps = pd.concat([train_gaps, val_gaps], ignore_index=True) if (
        not train_gaps.empty and not val_gaps.empty) else (
        train_gaps if not train_gaps.empty else val_gaps)
    if not all_gaps.empty:
        all_gaps.to_csv(OUT / "g1_full_report.csv", index=False)

    print(f"\nSaved: out/g1_summary.json, out/g1_train_typeb.csv, "
          f"out/g1_val_gaps.csv, out/g1_full_report.csv")


if __name__ == "__main__":
    main()
