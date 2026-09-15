"""
G1_G2_link.py — Gate 1 → Gate 2 Connection Evaluation

Answers the key DT question:
  "Does the physics model (Gate 2) independently reproduce the coverage holes
   that Gate 1 identified empirically?"

No Sionna re-run needed. Uses existing prediction files:
  - per_tower_val_rows_op1/op2.csv  (Sionna predictions on val rows, with gap_type)
  - g1_train_typeb.csv              (TypeB cluster centroids from Gate 1)
  - cellular_dataframe_cleaned.csv  (GPS coords, joined via _row)

For each row in the val predictions:
  - Is it near a Gate 1 TypeB cluster? (within TYPEB_RADIUS_M)
  - What does Sionna predict there vs. background rows?

The DT "passes" this check if Sionna systematically predicts lower signal
at TypeB locations than at background locations — meaning the physics model
captures the coverage hole structure independently of the empirical Gate 1
classification.
"""

import json, math
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "out"

TYPEB_RADIUS_M = 150.0   # match radius: rows within this of a TypeB centroid
                          # (slightly larger than Gate 1's 100m to capture approach rows)

print("=" * 60)
print("G1→G2 Link: Does the DT reproduce empirical dead zones?")
print("=" * 60)


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    a = (np.sin(np.radians(lat2 - lat1) / 2) ** 2
         + np.cos(phi1) * np.cos(phi2)
         * np.sin(np.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def main():
    # Load TypeB cluster centroids from Gate 1
    tb_path = OUT / "g1_train_typeb.csv"
    if not tb_path.exists():
        print("ERROR: run G1_completeness.py first to generate g1_train_typeb.csv")
        return
    tb_clusters = pd.read_csv(tb_path)
    print(f"Gate 1 TypeB clusters: {len(tb_clusters)}")
    print(tb_clusters[["cluster_id","operator","centroid_lat",
                        "centroid_lon","n_gaps"]].to_string(index=False))

    # Load GPS coordinates for all rows
    print("\nLoading GPS coords...")
    gps = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv",
                      low_memory=False,
                      usecols=["Latitude", "Longitude"])
    gps["_row"] = gps.index

    # Load per-tower val predictions (have _row, sionna_power_cal, gap_type)
    p1 = pd.read_csv(OUT / "per_tower_val_rows_op1.csv")
    p2 = pd.read_csv(OUT / "per_tower_val_rows_op2.csv")
    preds = pd.concat([p1, p2], ignore_index=True)
    print(f"Val predictions: {len(preds)} rows  "
          f"(op1={len(p1)}, op2={len(p2)})")

    # Join GPS
    preds = preds.merge(gps, on="_row", how="left")
    preds = preds.dropna(subset=["Latitude", "Longitude"])
    print(f"After GPS join: {len(preds)} rows")

    # For each prediction row, compute min distance to any TypeB centroid
    clats = tb_clusters["centroid_lat"].values
    clons = tb_clusters["centroid_lon"].values
    cops  = tb_clusters["operator"].values

    def min_dist_to_typeb(row):
        lats = preds.loc[row.name, "Latitude"] if hasattr(row, "name") else row["Latitude"]
        lons = preds.loc[row.name, "Longitude"] if hasattr(row, "name") else row["Longitude"]
        dists = [haversine_m(lats, lons, clats[i], clons[i])
                 for i in range(len(clats))
                 if cops[i] == row["operator"]]
        return min(dists) if dists else 1e9

    print("\nLabeling rows by proximity to TypeB clusters...")
    preds["dist_to_typeb_m"] = preds.apply(min_dist_to_typeb, axis=1)
    preds["near_typeb"] = preds["dist_to_typeb_m"] <= TYPEB_RADIUS_M

    n_near = preds["near_typeb"].sum()
    n_back = (~preds["near_typeb"]).sum()
    print(f"  Rows near TypeB zone   : {n_near}")
    print(f"  Background rows        : {n_back}")

    # ── Core comparison: Sionna prediction at TypeB vs background ─────────────
    # Use calibrated Sionna prediction (sionna_power_cal or sionna_cal_pt)
    # Try multiple column names for compatibility across pipeline versions
    cal_col = None
    for cname in ["sionna_cal_pt", "sionna_power_cal", "sionna_cal"]:
        if cname in preds.columns:
            cal_col = cname
            break
    if cal_col is None:
        cal_col = "sionna_power_raw"
        print(f"  WARNING: no calibrated col found, using {cal_col}")
    else:
        print(f"  Using prediction column: {cal_col}")

    near = preds[preds["near_typeb"] & preds[cal_col].notna() & (preds[cal_col] > -200)]
    back = preds[~preds["near_typeb"] & preds[cal_col].notna() & (preds[cal_col] > -200)]

    print(f"\n{'─'*50}")
    print("Sionna predicted RSRP (calibrated):")
    print(f"  At TypeB locations : {near[cal_col].mean():.2f} dB  "
          f"(median {near[cal_col].median():.2f}, n={len(near)})")
    print(f"  Background         : {back[cal_col].mean():.2f} dB  "
          f"(median {back[cal_col].median():.2f}, n={len(back)})")
    drop = back[cal_col].mean() - near[cal_col].mean()
    print(f"  Predicted signal drop at TypeB zone: {drop:.2f} dB")

    # Statistical test
    if len(near) > 5 and len(back) > 5:
        t, p = stats.ttest_ind(near[cal_col], back[cal_col], equal_var=False)
        print(f"  Welch t-test: t={t:.2f}  p={p:.4f}  "
              f"({'significant' if p < 0.05 else 'not significant'})")

    # Measured RSRP comparison (for context — TypeB rows themselves are NaN)
    meas_near = preds[preds["near_typeb"] & preds["measured_rsrp"].notna()]
    meas_back = preds[~preds["near_typeb"] & preds["measured_rsrp"].notna()]
    if len(meas_near) > 0 and len(meas_back) > 0:
        meas_drop = meas_back["measured_rsrp"].mean() - meas_near["measured_rsrp"].mean()
        print(f"\nMeasured RSRP (approach rows with valid signal):")
        print(f"  Near TypeB  : {meas_near['measured_rsrp'].mean():.2f} dB  "
              f"(n={len(meas_near)})")
        print(f"  Background  : {meas_back['measured_rsrp'].mean():.2f} dB  "
              f"(n={len(meas_back)})")
        print(f"  Measured drop at TypeB approach: {meas_drop:.2f} dB")

    # ── Per-operator breakdown ─────────────────────────────────────────────────
    print(f"\n{'─'*50}")
    print("Per-operator breakdown:")
    for op in [1, 2]:
        nr = near[near["operator"] == op]
        bk = back[back["operator"] == op]
        if len(nr) == 0:
            print(f"  Op{op}: no TypeB-zone rows in val predictions")
            continue
        drop_op = bk[cal_col].mean() - nr[cal_col].mean()
        print(f"  Op{op}: TypeB={nr[cal_col].mean():.2f} dB  "
              f"background={bk[cal_col].mean():.2f} dB  "
              f"drop={drop_op:.2f} dB  (n_near={len(nr)})")

    # ── DT validation verdict ─────────────────────────────────────────────────
    print(f"\n{'═'*60}")
    print("VERDICT")
    if drop > 3.0:
        verdict = "PASS"
        msg = (f"The physics model predicts {drop:.1f} dB lower signal at "
               f"Gate 1 TypeB locations vs. background — consistent with the "
               f"empirically identified coverage hole.")
    elif drop > 0.5:
        verdict = "PARTIAL"
        msg = (f"The physics model predicts {drop:.1f} dB lower signal at "
               f"TypeB locations — a statistically detectable but modest "
               f"prediction of the coverage hole.")
    else:
        verdict = "FAIL"
        msg = (f"The physics model predicts similar signal at TypeB locations "
               f"({drop:.1f} dB drop) — the OSM scene does not capture the "
               f"blocker causing the coverage hole.")

    print(f"  {verdict}: {msg}")

    # Save
    summary = {
        "typeb_clusters": len(tb_clusters),
        "n_rows_near_typeb": int(n_near),
        "n_rows_background": int(n_back),
        "sionna_pred_typeb_mean": float(near[cal_col].mean()) if len(near) > 0 else None,
        "sionna_pred_background_mean": float(back[cal_col].mean()) if len(back) > 0 else None,
        "predicted_signal_drop_db": float(drop),
        "verdict": verdict,
    }
    with open(OUT / "g1_g2_link_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    preds[["_row","operator","device","near_typeb",
           "dist_to_typeb_m", cal_col, "measured_rsrp"]].to_csv(
        OUT / "g1_g2_link_rows.csv", index=False)

    print(f"\nSaved: out/g1_g2_link_summary.json, out/g1_g2_link_rows.csv")


if __name__ == "__main__":
    main()
