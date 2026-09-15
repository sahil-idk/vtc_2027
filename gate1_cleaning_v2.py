"""
gate1_cleaning_v2.py
---------------------
DT-QUEST Gate 1 (Data Readiness) pipeline, v2 -- using VERIFIED 3GPP bounds
(cross-checked against the actual standards, not just the paper's Table I).

Bound corrections made vs. the original paper / v1 script:
  - SNR (RS-SINR) floor changed from -10 dB to -20 dB
    (matches Android CellSignalStrengthLte RSSNR convention / typical
    modem reporting range; -10 dB is not an enforced 3GPP limit and was
    producing false-positive flags)
  - RSRQ bounds added: [-34, +2.5] dB (modern/extended range, TS 36.133)
  - Tx Power bounds changed from [10,30] dBm to [-40,26] dBm
    (TS 36.101 6.3.2: min controlled output power -40 dBm; max per
    power class 23 dBm [Class 3, typical] / 26 dBm [Class 2])
    IMPORTANT: Tx Power is FLAGGED ONLY, never corrected/clipped --
    diagnostics show the bad values (up to 127 dBm) do not reduce to a
    plausible number under any simple unit/scale transform, and the
    anomaly correlates with direction + high RB/TB-size activity rather
    than being pure noise. Treat as Type-3 (document, exclude from twin
    use for this field only) rather than Type-1 (correctable offset).
  - RSRP / RSSI bounds unchanged (RSRP confirmed correct against TS
    36.133 Table 9.1.4-1; RSSI is industry convention, not a single
    3GPP table, and the paper's range is reasonable as-is)

Run: python gate1_cleaning_v2.py
"""

import pandas as pd
import numpy as np
import os

SRC = "/mnt/user-data/uploads/cellular_dataframe.csv"
OUT_DIR = "/mnt/user-data/outputs"
os.makedirs(OUT_DIR, exist_ok=True)

print("Loading raw CSV...")
df = pd.read_csv(SRC, low_memory=False)
print(f"Loaded {df.shape[0]} rows x {df.shape[1]} cols")

# ---------------------------------------------------------------------------
# VERIFIED bounds (see docstring for sourcing)
# ---------------------------------------------------------------------------
BOUNDS = {
    "PCell_SNR_1": (-20, 30), "PCell_SNR_2": (-20, 30),
    "SCell_SNR_1": (-20, 30), "SCell_SNR_2": (-20, 30),
    "PCell_RSRP_max": (-140, -44), "SCell_RSRP_max": (-140, -44),
    "PCell_RSSI_max": (-120, -25), "SCell_RSSI_max": (-120, -25),
    "PCell_RSRQ_max": (-34, 2.5), "SCell_RSRQ_max": (-34, 2.5),
}
# Flag-only, never corrected -- see rationale above
TXPOWER_BOUNDS = {
    "PCell_Uplink_Tx_Power_(dBm)": (-40, 26),
    "SCell_Uplink_Tx_Power_(dBm)": (-40, 26),
}

# ---------------------------------------------------------------------------
# V1 -- range validation with corrected bounds
# ---------------------------------------------------------------------------
range_rows = []
for col, (lo, hi) in {**BOUNDS, **TXPOWER_BOUNDS}.items():
    if col not in df.columns:
        continue
    s = df[col]
    flag_col = f"FLAG_range_{col}"
    df[flag_col] = ~s.between(lo, hi) & s.notna()
    n_present = s.notna().sum()
    n_bad = df[flag_col].sum()
    range_rows.append({
        "column": col, "lo": lo, "hi": hi,
        "actual_min": s.min(), "actual_max": s.max(), "mean": s.mean(),
        "n_present": n_present, "n_out_of_range": int(n_bad),
        "pct_in_range": round(100 * (1 - n_bad / n_present), 2) if n_present else np.nan
    })
range_report = pd.DataFrame(range_rows)
print("\n=== V1 Range validation (corrected bounds) ===")
print(range_report.to_string(index=False))

# Tx Power: flag only. Preserve raw value unmodified, no clipping/correction.
for col in TXPOWER_BOUNDS:
    if col in df.columns:
        print(f"NOTE: {col} is flagged-only (Type-3 handling), not corrected. "
              f"See FLAG_range_{col} to exclude from downstream twin/Sionna use.")

# ---------------------------------------------------------------------------
# V3 -- constant-value screening (unchanged methodology)
# ---------------------------------------------------------------------------
const_rows = []
for col in df.columns:
    s = df[col].dropna()
    if len(s) < 100:
        continue
    top_frac = s.value_counts(normalize=True).iloc[0]
    if top_frac >= 0.95:
        const_rows.append({"column": col, "pct_constant": round(top_frac * 100, 2),
                            "constant_value": s.mode().iloc[0]})
const_report = pd.DataFrame(const_rows)

# ---------------------------------------------------------------------------
# V4 -- readiness scorecard per (operator, device), now including corrected
# range-validation flag rates so the true regional impact is visible
# ---------------------------------------------------------------------------
rf_cols = ["PCell_RSRP_max", "PCell_RSRQ_max", "PCell_RSSI_max", "PCell_SNR_1", "PCell_SNR_2"]
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
        "pct_snr_flagged_NEW": round(g["FLAG_range_PCell_SNR_1"].mean() * 100, 2),
        "pct_txpower_flagged_NEW": round(
            g["FLAG_range_PCell_Uplink_Tx_Power_(dBm)"].mean() * 100, 2),
    })
readiness_report = pd.DataFrame(readiness_rows).sort_values(["operator", "device"])
print("\n=== V4 Readiness scorecard (corrected bounds) ===")
print(readiness_report.to_string(index=False))

# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------
df.to_csv(f"{OUT_DIR}/cellular_dataframe_cleaned_v2.csv", index=False)
df[df["operator"] == 1].to_csv(f"{OUT_DIR}/cellular_operator1_v2.csv", index=False)
df[df["operator"] == 2].to_csv(f"{OUT_DIR}/cellular_operator2_v2.csv", index=False)
range_report.to_csv(f"{OUT_DIR}/gate1_range_validation_v2.csv", index=False)
const_report.to_csv(f"{OUT_DIR}/gate1_flagged_columns_v2.csv", index=False)
readiness_report.to_csv(f"{OUT_DIR}/gate1_readiness_report_v2.csv", index=False)

print("\nSaved v2 outputs (corrected bounds) to", OUT_DIR)
print("Gate 1 v2 pipeline complete.")
