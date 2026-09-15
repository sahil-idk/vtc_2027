"""
04_compute_pathloss_comparison.py
------------------------------------
The actual "how much loss are we getting before cleaning vs after cleaning"
comparison, using Sionna RT as the physics oracle (Angle C from the plan).

Method:
  1. Empirical downlink path loss is estimated from measured RSRP using an
     ASSUMED eNB reference-signal transmit power (documented below -- this
     is a necessary assumption since eNB Tx power isn't logged in this UE-
     side dataset; only the anomalous uplink Tx Power field is, and that is
     deliberately excluded per TX_POWER_ANOMALY_CAUSE.md):

        PL_empirical = ASSUMED_ENB_TX_POWER_DBM - RSRP

  2. "BEFORE cleaning" = every row with RSRP present, regardless of any
     Gate-1 flag (equivalent to having no upstream quality checks at all).
  3. "AFTER cleaning" = Gate-1-cleaned dataset (v2, corrected 3GPP bounds),
     restricted to rows where RSRP/RSRQ/RSSI/SNR ALL pass range validation
     (FLAG_range_* columns == False). This is the "DT-ready" subset.
     Both BEFORE and AFTER are derived from the SAME cellular_dataframe_
     cleaned_v2.csv file -- it's a strict superset of the raw data (only
     flag columns were added; RSRP/RSRQ/RSSI/SNR values themselves were
     never modified), so no separate raw CSV is needed for this comparison.
  4. Sionna RT's simulated received power (step 3 output) is converted to
     simulated path loss the same way, using the SAME assumed eNB Tx power,
     and used as ground truth. MAE/RMSE are computed for BEFORE vs AFTER
     against this oracle, matched by row_index.

Tune ASSUMED_ENB_TX_POWER_DBM if you have a better estimate for the actual
Berlin V2X eNB configuration (e.g. from operator documentation).

Run: python 04_compute_pathloss_comparison.py
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path

CLEANED_CSV = "cellular_dataframe_cleaned_v2.csv"

# Documented assumption -- typical total conducted eNB Tx power for a fully
# loaded 20 MHz LTE macro cell (~43 dBm is a common real-world default;
# adjust if you have operator-specific info).
ASSUMED_ENB_TX_POWER_DBM = 43.0

RANGE_FLAG_COLS = [
    "FLAG_range_PCell_RSRP_max", "FLAG_range_PCell_RSRQ_max",
    "FLAG_range_PCell_RSSI_max", "FLAG_range_PCell_SNR_1",
]


def empirical_path_loss(rsrp_series):
    return ASSUMED_ENB_TX_POWER_DBM - rsrp_series


def sionna_path_loss(rx_power_dbm_series):
    return ASSUMED_ENB_TX_POWER_DBM - rx_power_dbm_series


def fit_offset(measured_pl, sionna_pl, train_frac=0.3, seed=42):
    """Fit the additive calibration offset. Per the discipline in
    GATE1_COVERAGE_ANALYSIS.md's companion recipe: this MUST be called only
    on the Gate-1 DT-ready (clean) subset, never on raw/unfiltered data --
    otherwise a separately-fit offset per condition can silently absorb the
    very cleaning effect we're trying to measure, recreating exactly the
    circularity Reviewer 2 flagged elsewhere in the paper.

    NOTE ON WHAT THIS OFFSET ACTUALLY MEANS: algebraically, offset =
    measured_pl - sionna_pl = sionna_rx_power_dbm - RSRP (the assumed eNB
    Tx power constant cancels out of both terms). So this offset is NOT a
    measurement of the real eNB's transmit power -- it's compensating for
    Sionna's own internal, arbitrary reference power scale versus real
    RSRP. An earlier version of this function checked the fitted offset
    against a "physically plausible eNB Tx power" range (30-50 dB), which
    was checking the wrong thing entirely. The correct sanity check is
    CROSS-OPERATOR CONSISTENCY: since this offset should just reflect a
    fixed property of Sionna's reference scale, it should come out
    similar across different operators run through the same code and
    material model, regardless of how different their real-world path
    loss looks. See the consistency check in the __main__ block below.
    """
    common_idx = measured_pl.index.intersection(sionna_pl.index)
    measured_pl = measured_pl.loc[common_idx]
    sionna_pl = sionna_pl.loc[common_idx]
    if len(common_idx) < 10:
        return np.nan

    rng = np.random.RandomState(seed)
    train_mask = rng.rand(len(common_idx)) < train_frac
    train_idx = common_idx[train_mask] if train_mask.sum() >= 3 else common_idx
    offset = (measured_pl.loc[train_idx] - sionna_pl.loc[train_idx]).mean()
    return offset


def apply_and_score(measured_pl, sionna_pl, offset):
    """Apply a PRE-FIT offset (from fit_offset, on clean data) and score
    against whatever measured_pl/sionna_pl is passed in -- this can be the
    raw/unfiltered condition or the cleaned condition; the offset itself
    does not change between the two, which is the point.
    """
    common_idx = measured_pl.index.intersection(sionna_pl.index)
    if len(common_idx) < 3 or pd.isna(offset):
        return np.nan, np.nan, 0
    calibrated_sionna = sionna_pl.loc[common_idx] + offset
    diff = (measured_pl.loc[common_idx] - calibrated_sionna).dropna()
    if len(diff) == 0:
        return np.nan, np.nan, 0
    mae = diff.abs().mean()
    rmse = np.sqrt((diff ** 2).mean())
    return mae, rmse, len(diff)


def run_for_operator(op: int):
    print(f"\n=== Operator {op} ===")
    sionna = pd.read_csv(f"sionna_predictions_operator{op}.csv", index_col="row_index")
    n_total = len(sionna)
    n_nan = sionna["sionna_rx_power_dbm"].isna().sum()
    if n_nan:
        print(f"  {n_nan} / {n_total} Sionna predictions are NaN (no matching serving "
              f"tower or a ray-tracing failure) -- excluded from this comparison.")
    sionna = sionna.dropna(subset=["sionna_rx_power_dbm"])
    sionna["pl_sionna"] = sionna_path_loss(sionna["sionna_rx_power_dbm"])

    # BEFORE = every row with RSRP present, regardless of any Gate-1 flag
    # (i.e. what you'd get with no upstream quality checks at all).
    # AFTER  = only rows that pass ALL range-validation checks (the
    # DT-ready subset). Both come from the same cleaned_v2 file since it's
    # a strict superset of the raw data -- only flag columns were added,
    # RSRP/RSRQ/RSSI/SNR values themselves were never modified.
    df_full = pd.read_csv(CLEANED_CSV, low_memory=False)
    df_op = df_full[df_full["operator"] == op]

    raw_matched = df_op.loc[df_op.index.intersection(sionna.index)]
    raw_pl = empirical_path_loss(raw_matched["PCell_RSRP_max"])

    clean_mask = ~df_op[RANGE_FLAG_COLS].any(axis=1)
    cleaned_ok = df_op[clean_mask]
    cleaned_matched = cleaned_ok.loc[cleaned_ok.index.intersection(sionna.index)]
    cleaned_pl = empirical_path_loss(cleaned_matched["PCell_RSRP_max"])

    # Fit the calibration offset ONCE, using only the Gate-1 DT-ready
    # (clean) subset. This same offset is then applied to BOTH the raw and
    # cleaned evaluations below -- fitting a separate offset per condition
    # would let calibration silently absorb the cleaning effect itself.
    offset = fit_offset(cleaned_pl, sionna["pl_sionna"])
    print(f"  Calibration offset (fit on clean data only): {offset:.2f} dB")

    mae_before, rmse_before, n_before = apply_and_score(raw_pl, sionna["pl_sionna"], offset)
    mae_after, rmse_after, n_after = apply_and_score(cleaned_pl, sionna["pl_sionna"], offset)

    print(f"BEFORE cleaning: n={n_before}, MAE={mae_before:.2f} dB, RMSE={rmse_before:.2f} dB")
    print(f"AFTER  cleaning: n={n_after}, MAE={mae_after:.2f} dB, RMSE={rmse_after:.2f} dB")

    return {
        "operator": op, "calibration_offset_dB": round(offset, 2) if pd.notna(offset) else np.nan,
        "n_before": n_before, "mae_before": mae_before, "rmse_before": rmse_before,
        "n_after": n_after, "mae_after": mae_after, "rmse_after": rmse_after,
    }


if __name__ == "__main__":
    summary = []
    for op in (1, 2):
        pred_path = Path(f"sionna_predictions_operator{op}.csv")
        if not pred_path.exists():
            print(f"\n=== Operator {op} ===\n  SKIPPED: {pred_path} not found yet "
                  f"(run 03_build_sionna_scene.py --operator {op} first)")
            continue
        summary.append(run_for_operator(op))

    if not summary:
        raise SystemExit("No sionna_predictions_operator*.csv files found -- nothing to compare.")

    summary_df = pd.DataFrame(summary)
    summary_df.to_csv("pathloss_before_after_summary.csv", index=False)
    print("\n=== Summary (saved to pathloss_before_after_summary.csv) ===")
    print(summary_df.to_string(index=False))

    # Cross-operator consistency check on the calibration offset -- this is
    # the CORRECT sanity check (see fit_offset()'s docstring for why the
    # earlier "physically plausible eNB Tx power" absolute-range check was
    # testing the wrong thing). Since the offset just reflects a fixed
    # property of Sionna's internal reference scale, it should come out
    # similar across operators even though their real-world path loss
    # differs. A large spread here is the actual signal of a remaining bug
    # (e.g. scene scale, coordinate frame, antenna orientation) -- not an
    # absolute value outside some assumed physical range.
    offsets = summary_df["calibration_offset_dB"].dropna()
    if len(offsets) >= 2:
        spread = offsets.max() - offsets.min()
        CONSISTENCY_THRESHOLD_DB = 15.0
        print(f"\nCalibration offset spread across operators: {spread:.2f} dB "
              f"(values: {offsets.tolist()})")
        if spread > CONSISTENCY_THRESHOLD_DB:
            print(f"  *** WARNING: offsets differ by more than "
                  f"{CONSISTENCY_THRESHOLD_DB:.0f} dB across operators -- this is "
                  f"the real signal of a remaining bug (likely something "
                  f"operator-specific: scene geometry, tower matching, or a data "
                  f"contamination issue like the numerical-floor bug fixed "
                  f"earlier). Do not trust these MAE/RMSE numbers until resolved. ***")
        else:
            print(f"  OK: offsets agree within {CONSISTENCY_THRESHOLD_DB:.0f} dB -- "
                  f"consistent with a correctly-functioning pipeline.")

    # Quick bar chart
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.arange(len(summary_df))
    width = 0.35
    ax.bar(x - width / 2, summary_df["mae_before"], width, label="Before cleaning")
    ax.bar(x + width / 2, summary_df["mae_after"], width, label="After cleaning")
    ax.set_xticks(x)
    ax.set_xticklabels([f"Operator {o}" for o in summary_df["operator"]])
    ax.set_ylabel("MAE vs Sionna RT oracle (dB)")
    ax.set_title("Path-loss MAE: before vs after Gate-1 cleaning")
    ax.legend()
    plt.tight_layout()
    plt.savefig("pathloss_before_after_chart.png", dpi=150)
    print("Saved chart -> pathloss_before_after_chart.png")
