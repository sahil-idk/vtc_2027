"""
02_geolocate_towers.py
------------------------
Geolocate the distinct towers (from step 1) using OpenCelliD.

You need a free API key from https://opencellid.org/ (sign up, then
Account -> "API Access Token"). Free tier is rate-limited (historically
~1000 requests/day) -- if you have many hundred towers, prefer the BULK
CSV method described below instead of the live API.

--------------------------------------------------------------------------
OPTION A (recommended if you have >100 towers): bulk CSV download
--------------------------------------------------------------------------
1. Go to https://opencellid.org/downloads.php (requires free login)
2. Download the full country dump for Germany: MCC 262 (filename like
   "262.csv.gz")
3. Place it in this directory as "opencellid_germany.csv.gz"
4. Run this script with --mode bulk

Bulk file columns (per OpenCelliD docs): radio,mcc,net,area,cell,unit,lon,
lat,range,samples,changeable,created,updated,averageSignal
  - "net"  = MNC
  - "area" = LAC (GSM/UMTS) or TAC (LTE) -- same field, different meaning
  - "cell" = Cell ID. For LTE this is USUALLY the full 28-bit ECI, but some
    entries only have the eNodeB-level ID. The script tries an exact match
    on PCell_Cell_Identity first, then falls back to matching on the
    eNodeB ID (Cell_Identity >> 8) if no exact match is found.

--------------------------------------------------------------------------
OPTION B: live API (fine for a small number of towers)
--------------------------------------------------------------------------
Run with --mode api --api-key YOUR_KEY

--------------------------------------------------------------------------
Run:
    python 02_geolocate_towers.py --mode bulk
    python 02_geolocate_towers.py --mode api --api-key YOUR_KEY
--------------------------------------------------------------------------
"""

import argparse
import time
import pandas as pd
import requests


def geolocate_bulk(towers: pd.DataFrame, bulk_csv_path: str) -> pd.DataFrame:
    print(f"Loading bulk OpenCelliD file: {bulk_csv_path} (this can be large)...")
    OCID_COLS = ["radio", "mcc", "net", "area", "cell", "unit", "lon", "lat",
             "range", "samples", "changeable", "created", "updated", "averageSignal"]
    ocid = pd.read_csv(bulk_csv_path, compression="infer", header=None, names=OCID_COLS)
    ocid = ocid[ocid["radio"].isin(["LTE"])].copy()

    results = []
    for _, row in towers.iterrows():
        mcc = int(row["PCell_MCC"])
        mnc = int(row["PCell_MNC"])
        tac = int(row["PCell_TAC"])
        eci = int(row["PCell_Cell_Identity"])
        enb_id = eci >> 8

        match = ocid[(ocid["mcc"] == mcc) & (ocid["net"] == mnc) &
                     (ocid["area"] == tac) & (ocid["cell"] == eci)]
        match_type = "exact_eci"
        if match.empty:
            match = ocid[(ocid["mcc"] == mcc) & (ocid["net"] == mnc) &
                         (ocid["area"] == tac) & (ocid["cell"] == enb_id)]
            match_type = "enb_id_fallback"
        if match.empty:
            results.append({**row.to_dict(), "tower_lat": None, "tower_lon": None,
                             "match_type": "NOT_FOUND"})
            continue

        best = match.iloc[0]
        results.append({**row.to_dict(), "tower_lat": best["lat"],
                         "tower_lon": best["lon"], "match_type": match_type})

    return pd.DataFrame(results)


def geolocate_api(towers: pd.DataFrame, api_key: str) -> pd.DataFrame:
    base_url = "https://opencellid.org/cell/get"
    results = []
    for _, row in towers.iterrows():
        params = {
            "key": api_key, "mcc": int(row["PCell_MCC"]),
            "mnc": int(row["PCell_MNC"]), "lac": int(row["PCell_TAC"]),
            "cellid": int(row["PCell_Cell_Identity"]), "format": "json",
        }
        try:
            r = requests.get(base_url, params=params, timeout=10)
            data = r.json()
            lat, lon = data.get("lat"), data.get("lon")
        except Exception as e:
            lat, lon = None, None
            print(f"  lookup failed for cell {row['PCell_Cell_Identity']}: {e}")
        results.append({**row.to_dict(), "tower_lat": lat, "tower_lon": lon})
        time.sleep(1.0)  # be polite to the free-tier rate limit
    return pd.DataFrame(results)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["bulk", "api"], required=True)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--bulk-csv", default="opencellid_germany.csv.gz")
    args = ap.parse_args()

    for op in (1, 2):
        towers = pd.read_csv(f"towers_operator{op}.csv")
        print(f"\nOperator {op}: geolocating {len(towers)} towers ({args.mode} mode)...")

        if args.mode == "bulk":
            out = geolocate_bulk(towers, args.bulk_csv)
        else:
            if not args.api_key:
                raise SystemExit("--api-key required for --mode api")
            out = geolocate_api(towers, args.api_key)

        found = out["tower_lat"].notna().sum()
        print(f"  Geolocated {found} / {len(out)} towers "
              f"({100*found/len(out):.1f}%)")

        out_path = f"towers_operator{op}_geolocated.csv"
        out.to_csv(out_path, index=False)
        print(f"  Saved -> {out_path}")

    print("\nDone. Next step: 03_build_sionna_scene.py")
