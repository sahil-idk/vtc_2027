"""
01_extract_towers.py
---------------------
Extract the distinct serving-cell identifiers per operator from the Gate-1
cleaned dataset. This tells you exactly how many real-world towers you need
to geolocate before building the Sionna scene, and how much measurement
"weight" each tower carries (rows served), so you can prioritize the busiest
towers if you don't want to geolocate all of them at once.

Input:  cellular_dataframe_cleaned_v2.csv  (output of gate1_cleaning_v2.py)
Output: towers_operator1.csv, towers_operator2.csv

Run: python 01_extract_towers.py
"""

import pandas as pd

SRC = "cellular_dataframe_cleaned_v2.csv"

ID_COLS = [
    "operator", "PCell_MCC", "PCell_MNC", "PCell_TAC",
    "PCell_Cell_Identity", "PCell_Cell_ID",
    "PCell_Downlink_frequency", "PCell_Uplink_frequency",
    "PCell_freq_MHz", "PCell_Band_Indicator",
    "PCell_Downlink_bandwidth_MHz", "PCell_Uplink_bandwidth_MHz",
]

print("Loading cleaned dataset...")
df = pd.read_csv(SRC, low_memory=False)
print(f"Loaded {df.shape[0]} rows")

# Only rows where the cell identity is actually present -- can't geolocate
# a tower we don't have an ID for.
have_id = df.dropna(subset=["PCell_Cell_Identity"])
print(f"{len(have_id)} / {len(df)} rows have a PCell_Cell_Identity "
      f"({100*len(have_id)/len(df):.2f}%)")

# Also grab a representative average receiver position + RSRP per tower --
# useful sanity check once towers are geolocated (does the tower's real
# position roughly match "where the average measurement was strongest"?).
agg = have_id.groupby(ID_COLS).agg(
    n_rows=("PCell_Cell_Identity", "size"),
    mean_rsrp=("PCell_RSRP_max", "mean"),
    mean_lat=("Latitude", "mean"),
    mean_lon=("Longitude", "mean"),
).reset_index()

agg = agg.sort_values(["operator", "n_rows"], ascending=[True, False])

for op, g in agg.groupby("operator"):
    out_path = f"towers_operator{op}.csv"
    g.to_csv(out_path, index=False)
    print(f"\nOperator {op}: {len(g)} distinct towers -> {out_path}")
    print(g[["PCell_Cell_Identity", "PCell_TAC", "n_rows", "mean_rsrp"]]
          .head(10).to_string(index=False))
    print(f"  (top 10 towers by row count shown; {len(g)} total)")

print("\nDone. Next step: 02_geolocate_towers.py")
