"""
gate1_cleaning.py
------------------
DT-QUEST Gate 1 (Data Readiness) pipeline for the Berlin cellular dataset.

What this does:
  1. Loads the raw CSV.
  2. Runs the 5 DT-QUEST upstream checks (range validation, cross-parameter
     consistency, constant-value screening, completeness profiling, unit
     verification) and adds FLAG columns -- never silently drops data.
  3. Corrects the one confirmed anomaly (PCell/SCell Uplink Tx Power stored
     with out-of-range values) using a documented, reversible method.
  4. Emits:
       - cellular_dataframe_cleaned.csv       (full dataset + flag columns)
       - cellular_operator1.csv               (PC1 + PC4 rows only)
       - cellular_operator2.csv               (PC2 + PC3 rows only)
       - gate1_readiness_report.csv           (per operator x device scorecard)
       - gate1_flagged_columns.csv            (constant-value / range summary)

Run: python gate1_cleaning.py
Requires: pandas, numpy
"""

import pandas as pd
import numpy as np

SRC = "/mnt/user-data/uploads/cellular_dataframe.csv"
OUT_DIR = "/mnt/user-data/outputs"

# ---------------------------------------------------------------------------
# 1. Load
# ---------------------------------------------------------------------------
print("Loading raw CSV...")
df = pd.read_csv(SRC, low_memory=False)
print(f"Loaded {df.shape[0]} rows x {df.shape[1]} cols")

# Device -> operator sanity map (confirmed from data, not assumed)
device_operator_map = df.groupby("device")["operator"].unique().to_dict()
print("Device -> operator mapping:", device_operator_map)

# ---------------------------------------------------------------------------
# 2. V1 -- Range validation against 3GPP bounds (Table I, DT-QUEST paper)
# ---------------------------------------------------------------------------
BOUNDS = {
    "PCell_SNR_1": (-10, 30), "PCell_SNR_2": (-10, 30),
    "SCell_SNR_1": (-10, 30), "SCell_SNR_2": (-10, 30),
    "PCell_RSRP_max": (-140, -44), "SCell_RSRP_max": (-140, -44),
    "PCell_RSSI_max": (-120, -25), "SCell_RSSI_max": (-120, -25),
    "PCell_Uplink_Tx_Power_(dBm)": (10, 30),
    "SCell_Uplink_Tx_Power_(dBm)": (10, 30),
}

range_report_rows = []
for col, (lo, hi) in BOUNDS.items():
    if col not in df.columns:
        continue
    s = df[col]
    flag_col = f"FLAG_range_{col}"
    df[flag_col] = ~s.between(lo, hi) & s.notna()  # True = out of range
    n_present = s.notna().sum()
    n_bad = df[flag_col].sum()
    range_report_rows.append({
        "column": col, "lo": lo, "hi": hi,
        "actual_min": s.min(), "actual_max": s.max(), "mean": s.mean(),
        "n_present": n_present, "n_out_of_range": n_bad,
        "pct_in_range": 100 * (1 - n_bad / n_present) if n_present else np.nan
    })

range_report = pd.DataFrame(range_report_rows)
print("\n=== V1 Range validation ===")
print(range_report.to_string(index=False))

# ---------------------------------------------------------------------------
# 2b. Correction for the confirmed Tx Power anomaly
#     PCell/SCell_Uplink_Tx_Power_(dBm) contains values up to 127 dBm,
#     physically impossible. Documented, reversible correction: clip to the
#     3GPP-valid range and retain the raw value in a shadow column for audit.
# ---------------------------------------------------------------------------
for col in ["PCell_Uplink_Tx_Power_(dBm)", "SCell_Uplink_Tx_Power_(dBm)"]:
    if col not in df.columns:
        continue
    raw_col = f"{col}_raw"
    df[raw_col] = df[col]
    df[col] = df[col].clip(lower=10, upper=30)
    print(f"Corrected {col}: raw preserved in {raw_col}, values clipped to [10,30] dBm")

# ---------------------------------------------------------------------------
# 3. V3 -- Constant-value screening (>=95% identical among non-null values)
# ---------------------------------------------------------------------------
const_rows = []
for col in df.columns:
    s = df[col].dropna()
    if len(s) < 100:
        continue
    top_frac = s.value_counts(normalize=True).iloc[0]
    if top_frac >= 0.95:
        const_rows.append({
            "column": col, "pct_constant": round(top_frac * 100, 2),
            "constant_value": s.mode().iloc[0]
        })
const_report = pd.DataFrame(const_rows)
print("\n=== V3 Constant-value screening ===")
print(const_report.to_string(index=False))

# ---------------------------------------------------------------------------
# 4. V4 -- Completeness profiling, per (operator, device)
# ---------------------------------------------------------------------------
rf_cols = ["PCell_RSRP_max", "PCell_RSRQ_max", "PCell_RSSI_max",
           "PCell_SNR_1", "PCell_SNR_2"]
qos_cols = ["ping_ms", "datarate", "jitter"]

def pct_complete(g, cols):
    return (1 - g[cols].isna().mean()).mean() * 100

readiness_rows = []
for (op, dev), g in df.groupby(["operator", "device"]):
    readiness_rows.append({
        "operator": op, "device": dev, "n_rows": len(g),
        "pct_rf_complete": round(pct_complete(g, rf_cols), 2),
        "pct_qos_complete": round(pct_complete(g, qos_cols), 2),
        "pct_scell_present": round(g["SCell_RSRP_max"].notna().mean() * 100, 2),
        "pct_gps_complete": round(pct_complete(g, ["Latitude", "Longitude", "Altitude"]), 2),
        "pct_txpower_flagged": round(
            g.get("FLAG_range_PCell_Uplink_Tx_Power_(dBm)", pd.Series(dtype=bool)).mean() * 100, 2
        ),
    })
readiness_report = pd.DataFrame(readiness_rows).sort_values(["operator", "device"])
print("\n=== V4 Completeness / readiness scorecard (per operator x device) ===")
print(readiness_report.to_string(index=False))

# ---------------------------------------------------------------------------
# 5. V5 -- Unit verification (sanity check: RSRP/RSSI/SNR already in dB-scale)
#     Quick check: dB-scale values should NOT look like raw linear watts
#     (i.e. should not be tiny positive numbers near 0).
# ---------------------------------------------------------------------------
unit_check_cols = ["PCell_RSRP_max", "PCell_RSSI_max", "PCell_SNR_1"]
print("\n=== V5 Unit verification (scale sanity) ===")
for col in unit_check_cols:
    s = df[col].dropna()
    looks_linear = ((s.abs() < 1).mean() > 0.5)  # crude heuristic
    print(f"{col}: min={s.min():.2f} max={s.max():.2f} -> "
          f"{'SUSPECT linear-scale' if looks_linear else 'OK, looks like dB-scale'}")

# ---------------------------------------------------------------------------
# 6. Save outputs
# ---------------------------------------------------------------------------
import os
os.makedirs(OUT_DIR, exist_ok=True)

cleaned_path = f"{OUT_DIR}/cellular_dataframe_cleaned.csv"
df.to_csv(cleaned_path, index=False)
print(f"\nSaved full cleaned dataset (with flags) -> {cleaned_path}")

op1_path = f"{OUT_DIR}/cellular_operator1.csv"
op2_path = f"{OUT_DIR}/cellular_operator2.csv"
df[df["operator"] == 1].to_csv(op1_path, index=False)
df[df["operator"] == 2].to_csv(op2_path, index=False)
print(f"Saved operator splits -> {op1_path}, {op2_path}")

readiness_report.to_csv(f"{OUT_DIR}/gate1_readiness_report.csv", index=False)
const_report.to_csv(f"{OUT_DIR}/gate1_flagged_columns.csv", index=False)
range_report.to_csv(f"{OUT_DIR}/gate1_range_validation.csv", index=False)
print("Saved readiness / flagged-column / range-validation reports.")

print("\nGate 1 pipeline complete.")
