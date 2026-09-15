"""
A00_opencellid_lookup.py — TWINGATE Gate 2, Step 0
Tower position lookup via OpenCelliD bulk data.

Replaces WCL (Weighted Centroid Localization) with crowdsourced GPS positions.
Lookup priority:
  1. Exact ECI + TAC match (highest confidence)
  2. Exact ECI match ignoring TAC (OCID sometimes stores wrong TAC for LTE)
  3. WCL fallback — from training rows only (lowest confidence, flagged)

NOTE: eNB-ID sibling matching (ECI // 256) was tested and REMOVED.
The eNB_ID lookup with no geographic filter matched towers from other
German cities (same eNB_ID reused across PLMNs in different Bundesländer),
producing positions 100s of km from Berlin. MAE degraded to 67 dB for
affected towers. Only exact-ECI matches are trusted from OCID.

Inputs:
  - towers_operator{1,2}.csv           (from 01_extract_towers.py)
  - opencellid_germany.csv.gz          (bulk OCID dump, MCC=262)
  - twingate/out/sionna_raw.csv        (for WCL fallback, uses only train rows)

Outputs:
  - twingate/out/tower_positions.csv   (all towers with position + source tag)
  - twingate/out/position_report.txt   (hit rate summary)
"""

import math
import numpy as np
import pandas as pd
from pathlib import Path

ROOT   = Path(__file__).parent.parent
OUT    = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

OCID_PATH  = ROOT / "opencellid_germany.csv.gz"
SIONNA_CSV = OUT / "sionna_raw.csv"

OCID_COLS = ["radio","mcc","net","area","cell","unit","lon","lat",
             "range","samples","changeable","created","updated","averageSignal"]


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def load_ocid():
    print(f"Loading OCID bulk file: {OCID_PATH} ...")
    ocid = pd.read_csv(OCID_PATH, compression="infer", header=None, names=OCID_COLS)
    lte = ocid[ocid["radio"] == "LTE"].copy()
    lte["cell_int"] = lte["cell"].astype(np.int64)
    lte["enb_id"]   = lte["cell_int"] // 256
    print(f"  LTE rows in OCID: {len(lte):,}")
    return lte


def lookup_tower(row, ocid_op):
    """Return (lat, lon, source_tag) for one tower row.
    Only uses exact ECI matches. eNB-sibling matching is not used — see module docstring.
    """
    eci = int(row["PCell_Cell_Identity"])
    tac = int(row["PCell_TAC"])

    # Priority 1: exact ECI + TAC
    m = ocid_op[(ocid_op["cell_int"] == eci) & (ocid_op["area"] == tac)]
    if not m.empty:
        best = m.sort_values("samples", ascending=False).iloc[0]
        return best["lat"], best["lon"], "ocid_exact"

    # Priority 2: exact ECI, ignore TAC (OCID sometimes records wrong TAC for LTE)
    m = ocid_op[ocid_op["cell_int"] == eci]
    if not m.empty:
        best = m.sort_values("samples", ascending=False).iloc[0]
        return best["lat"], best["lon"], "ocid_eci_notac"

    return None, None, "MISSING"


def extract_wcl(train_df):
    """Extract already-computed WCL positions from sionna_raw train rows.
    sionna_raw.csv has cell_id=ECI and wcl_lat/wcl_lon pre-computed per cell."""
    wcl = {}
    for cell_id, g in train_df.groupby("cell_id"):
        row0 = g.dropna(subset=["wcl_lat", "wcl_lon"]).iloc[0] if g["wcl_lat"].notna().any() else None
        if row0 is not None:
            wcl[int(cell_id)] = (float(row0["wcl_lat"]), float(row0["wcl_lon"]))
    return wcl


def main():
    print("A00 OpenCelliD Lookup")
    print("=" * 60)

    ocid_lte = load_ocid()

    # Load Sionna raw (for WCL fallback) — train rows only
    # sionna_raw.csv: cell_id=ECI, wcl_lat/wcl_lon pre-computed per cell
    wcl_by_op = {1: {}, 2: {}}
    if SIONNA_CSV.exists():
        sionna = pd.read_csv(SIONNA_CSV)
        train_rows = sionna[sionna["split"] == "train"]
        print(f"  Sionna train rows for WCL: {len(train_rows):,}")
        for op in [1, 2]:
            wcl_by_op[op] = extract_wcl(train_rows[train_rows["operator"] == op])
    else:
        print("  WARNING: sionna_raw.csv not found, WCL fallback unavailable")

    all_results = []
    report_lines = []

    for op in [1, 2]:
        towers = pd.read_csv(ROOT / f"towers_operator{op}.csv")
        mnc    = int(towers["PCell_MNC"].iloc[0])
        ocid_op = ocid_lte[(ocid_lte["mcc"] == 262) & (ocid_lte["net"] == mnc)]

        print(f"\n{'='*60}")
        print(f"Operator {op}  (MNC={mnc})  |  {len(towers)} towers in dataset")
        print(f"  OCID LTE entries for this operator: {len(ocid_op):,}")

        wcl_data = wcl_by_op[op]

        counts = {"ocid_exact": 0, "ocid_eci_notac": 0, "ocid_enb_sibling": 0,
                  "wcl_fallback": 0, "MISSING": 0}

        for _, row in towers.iterrows():
            eci = int(row["PCell_Cell_Identity"])
            lat, lon, src = lookup_tower(row, ocid_op)

            if lat is None and eci in wcl_data and wcl_data[eci][0] is not None:
                lat, lon = wcl_data[eci]
                src = "wcl_fallback"

            if lat is None:
                counts["MISSING"] += 1
                src = "MISSING"
            else:
                counts[src] += 1

            # Distance from WCL to OCID position (quality check)
            wcl_pos = wcl_data.get(eci, (None, None))
            if lat and wcl_pos[0] and "ocid" in src:
                dist_m = haversine_m(lat, lon, wcl_pos[0], wcl_pos[1])
            else:
                dist_m = None

            all_results.append({
                "operator":             op,
                "PCell_MCC":            int(row["PCell_MCC"]),
                "PCell_MNC":            mnc,
                "PCell_TAC":            int(row["PCell_TAC"]),
                "PCell_Cell_Identity":  eci,
                "PCell_Cell_ID":        int(row["PCell_Cell_ID"]),
                "PCell_freq_MHz":       row.get("PCell_freq_MHz", None),
                "n_rows":               int(row.get("n_rows", 0)),
                "mean_rsrp":            row.get("mean_rsrp", None),
                "tower_lat":            lat,
                "tower_lon":            lon,
                "position_source":      src,
                "ocid_vs_wcl_dist_m":  round(dist_m, 1) if dist_m is not None else None,
                "wcl_lat":             wcl_pos[0] if wcl_pos else None,
                "wcl_lon":             wcl_pos[1] if wcl_pos else None,
            })

        total = len(towers)
        found = total - counts["MISSING"]
        print(f"  Results:")
        for k, v in counts.items():
            print(f"    {k:20s}: {v:3d}")
        print(f"  TOTAL FOUND: {found}/{total}  ({100*found/total:.1f}%)")

        # WCL vs OCID distance stats for quality check
        dists = [r["ocid_vs_wcl_dist_m"] for r in all_results
                 if r["operator"] == op and r["ocid_vs_wcl_dist_m"] is not None]
        if dists:
            dists = sorted(dists)
            print(f"  OCID-vs-WCL distance (m):  "
                  f"median={dists[len(dists)//2]:.0f}  "
                  f"p90={dists[int(0.9*len(dists))]:.0f}  "
                  f"max={dists[-1]:.0f}  n={len(dists)}")

        report_lines.append(f"Op{op} (MNC={mnc}): found {found}/{total} ({100*found/total:.1f}%)")
        for k, v in counts.items():
            report_lines.append(f"  {k}: {v}")

    out_df = pd.DataFrame(all_results)
    out_csv = OUT / "tower_positions.csv"
    out_df.to_csv(out_csv, index=False)
    print(f"\nSaved: {out_csv}")

    report_txt = OUT / "position_report.txt"
    report_txt.write_text("\n".join(report_lines))
    print(f"Saved: {report_txt}")

    print("\n\nSUMMARY")
    print("=" * 60)
    for line in report_lines[:6]:
        print(line)
    print("\nPosition sources:")
    print("  ocid_exact       — ECI + TAC matched (highest confidence)")
    print("  ocid_eci_notac   — ECI matched, TAC mismatch in OCID (high confidence)")
    print("  ocid_enb_sibling — sibling sector (same eNB, co-located, good confidence)")
    print("  wcl_fallback     — RSRP-weighted centroid from training rows (lower confidence)")
    print("  MISSING          — not in OCID, insufficient training data for WCL")


if __name__ == "__main__":
    main()
