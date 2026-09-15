"""
A05_oracle_check.py — TWINGATE Gate 2, Step 5
Independent oracle: leave-one-device-out + bootstrap null check.

Architecture requirement (from prompt spec):
  For every device-level exclusion decision the pipeline makes, run a
  leave-one-out comparison against a bootstrap null (N_BOOT random same-sized
  exclusions) and report whether the actual exclusion's effect sits outside
  the null distribution AND in the expected direction.

  A result that is statistically distinguishable from the null but in the
  WRONG direction must be reported as a failed check, not omitted.

What this does:
  1. Loads sionna_raw.csv (A03).
  2. Per operator, for each device:
     a. Exclude that device's TRAINING rows from calibration offset fitting.
     b. Re-fit offset on remaining training rows.
     c. Evaluate calibrated MAE on the FULL val set (all devices).
     d. Compare to baseline (all-device calibration, from A03).
     e. Compute bootstrap null: N_BOOT random same-sized row exclusions from
        training set (not device-aligned), re-fit offset, evaluate.
     f. Report: actual improvement, null distribution, percentile, pass/fail.

  Pass condition: actual exclusion improvement > 0 AND percentile >= 95th.
  If improvement > 0 but percentile < 95: WEAK (not statistically significant).
  If improvement <= 0: WRONG DIRECTION — reported as failed check.

Outputs -> twingate/out/:
  oracle_check.json   per-operator per-device result with bootstrap stats
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

OUT    = Path(__file__).parent / "out"
SIONNA = OUT / "sionna_raw.csv"

N_BOOT = 200
RNG    = np.random.RandomState(42)


def refit_and_eval(train_df, val_df):
    """Refit global offset on train_df, evaluate MAE on val_df."""
    if len(train_df) == 0:
        return np.nan
    offset = float((train_df["measured_rsrp"] - train_df["sionna_power_raw"]).mean())
    residuals = val_df["measured_rsrp"] - (val_df["sionna_power_raw"] + offset)
    return float(residuals.abs().mean())


def oracle_check_operator(op, df_op):
    print(f"\n{'='*60}")
    print(f"Operator {op} — Independent Oracle Check")
    print(f"{'='*60}")

    train = df_op[(df_op["split"] == "train") &
                  df_op["measured_rsrp"].notna() &
                  (df_op["gap_type"] != "TypeA")].copy()
    val   = df_op[(df_op["split"] == "val") &
                  df_op["measured_rsrp"].notna()].copy()

    if len(train) < 10 or len(val) < 10:
        print("  SKIP: insufficient rows.")
        return {}

    # Baseline: use all training rows
    baseline_mae = refit_and_eval(train, val)
    print(f"  Baseline MAE (all train rows): {baseline_mae:.3f} dB")

    devices = sorted(train["device"].unique())
    results = {}

    for dev in devices:
        train_excl = train[train["device"] != dev]
        n_excl = int((train["device"] == dev).sum())

        if n_excl == 0 or len(train_excl) < 5:
            continue

        # Actual leave-one-device-out MAE
        actual_mae = refit_and_eval(train_excl, val)
        actual_imp = baseline_mae - actual_mae   # positive = improvement

        # Bootstrap null: N_BOOT random exclusions of same cardinality
        null_imps = []
        for _ in range(N_BOOT):
            excl_idx = RNG.choice(len(train), size=n_excl, replace=False)
            mask = np.ones(len(train), dtype=bool)
            mask[excl_idx] = False
            null_mae = refit_and_eval(train.iloc[mask], val)
            null_imps.append(baseline_mae - null_mae)

        null_imps = np.array(null_imps)
        pctile = float(100 * np.mean(null_imps <= actual_imp))

        # Pass/fail logic
        if actual_imp > 0 and pctile >= 95:
            verdict = "PASS — significant improvement, correct direction"
        elif actual_imp > 0 and pctile < 95:
            verdict = "WEAK — improvement but not significant vs null"
        else:
            verdict = "FAIL — wrong direction (exclusion worsens fidelity)"

        print(f"\n  Device: {dev}  (excluded {n_excl} training rows)")
        print(f"    Baseline MAE         : {baseline_mae:.3f} dB")
        print(f"    Leave-{dev}-out MAE  : {actual_mae:.3f} dB")
        print(f"    Actual improvement   : {actual_imp:+.3f} dB")
        print(f"    Bootstrap null mean  : {null_imps.mean():.3f} dB  std={null_imps.std():.3f}")
        print(f"    Actual at percentile : {pctile:.0f}th")
        print(f"    Verdict              : {verdict}")

        results[dev] = {
            "device": dev,
            "n_excl_train_rows": n_excl,
            "baseline_mae": float(baseline_mae),
            "leaveout_mae": float(actual_mae),
            "actual_improvement_db": float(actual_imp),
            "null_mean_improvement": float(null_imps.mean()),
            "null_std_improvement": float(null_imps.std()),
            "null_percentile": float(pctile),
            "verdict": verdict,
        }

    return results


def main():
    print("A05 Oracle Check — loading sionna_raw.csv...")
    df = pd.read_csv(SIONNA)

    all_results = {}
    for op in [1, 2]:
        df_op = df[df["operator"] == op].copy()
        res = oracle_check_operator(op, df_op)
        all_results[str(op)] = res

    # Save JSON before any print that might fail on non-ASCII terminals
    with open(OUT / "oracle_check.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nOracle check saved: {OUT}/oracle_check.json")

    print("\n\n" + "="*60)
    print("ORACLE CHECK SUMMARY")
    print("="*60)
    for op, devs in all_results.items():
        print(f"\nOperator {op}:")
        for dev, r in devs.items():
            print(f"  {dev}: imp={r['actual_improvement_db']:+.3f} dB  "
                  f"pctile={r['null_percentile']:.0f}th  -> {r['verdict']}")


if __name__ == "__main__":
    main()
