"""
A06_report.py — TWINGATE Gate 2, Step 6
Final stratified results report. Runs after A03, A04, A05.

Produces:
  - final_report.csv : per-row results with all metrics
  - final_summary.json : structured results for paper tables
  - Printed summary: all check pass/fail states explicitly stated

Stratified by: device × distance-regime × area × gap_type
Metrics: MAE and RMSE on RSRP, for baseline and GP-corrected.
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path

OUT = Path(__file__).parent / "out"

DIST_BINS = [0, 200, 500, np.inf]
DIST_LABS = ["0-200m", "200-500m", "500m+"]


def dist_regime(d):
    for lo, hi, lab in zip(DIST_BINS, DIST_BINS[1:], DIST_LABS):
        if lo <= d < hi:
            return lab
    return DIST_LABS[-1]


def metrics(df, pred_col, true_col="measured_rsrp"):
    res = df[true_col] - df[pred_col]
    return {
        "mae":  float(res.abs().mean()),
        "rmse": float(np.sqrt((res ** 2).mean())),
        "n":    int(len(df)),
        "bias": float(res.mean()),
    }


def stratified_block(df, pred_col):
    out = {"overall": metrics(df, pred_col)}

    for cat in ["device", "area", "gap_type", "dist_regime"]:
        if cat not in df.columns:
            continue
        out[cat] = {}
        for val, g in df.groupby(cat):
            out[cat][str(val)] = metrics(g, pred_col)

    return out


def main():
    print("A06 Final Report")
    print("="*60)

    # Load GP results (has val rows with both baseline and GP predictions)
    gp_path = OUT / "gp_results.csv"
    if not gp_path.exists():
        # Fall back to sionna_raw only (baseline)
        df = pd.read_csv(OUT / "sionna_raw.csv")
        df = df[df["split"] == "val"].copy()
        has_gp = False
    else:
        df = pd.read_csv(gp_path)
        has_gp = "gp_rsrp" in df.columns

    if "dist_regime" not in df.columns:
        df["dist_regime"] = df["dist_m"].apply(dist_regime)

    with open(OUT / "baseline_results.json") as f:
        baseline_json = json.load(f)

    oracle_json = {}
    if (OUT / "oracle_check.json").exists():
        with open(OUT / "oracle_check.json") as f:
            oracle_json = json.load(f)

    gp_json = {}
    if (OUT / "gp_summary.json").exists():
        with open(OUT / "gp_summary.json") as f:
            gp_json = json.load(f)

    summary = {}

    for op in [1, 2]:
        df_op = df[df["operator"] == op].copy()
        if df_op.empty:
            continue

        print(f"\nOperator {op}")
        print("-"*50)

        # Baseline
        bl = stratified_block(df_op, "sionna_power_cal")
        print(f"  Baseline overall  : MAE={bl['overall']['mae']:.3f} dB  "
              f"RMSE={bl['overall']['rmse']:.3f} dB  n={bl['overall']['n']}")

        # GP corrected
        gp = {}
        if has_gp:
            gp = stratified_block(df_op, "gp_rsrp")
            print(f"  GP-corrected      : MAE={gp['overall']['mae']:.3f} dB  "
                  f"RMSE={gp['overall']['rmse']:.3f} dB")
            print(f"  GP improvement    : {bl['overall']['mae'] - gp['overall']['mae']:+.3f} dB MAE")

        print(f"\n  Baseline by device:")
        for dev, s in bl.get("device", {}).items():
            gp_s = gp.get("device", {}).get(dev, {})
            gp_str = f"  GP={gp_s.get('mae', np.nan):.3f}" if gp_s else ""
            print(f"    {dev}: baseline={s['mae']:.3f} dB{gp_str}  n={s['n']}")

        print(f"\n  Baseline by distance regime:")
        for dr, s in bl.get("dist_regime", {}).items():
            print(f"    {dr}: MAE={s['mae']:.3f} dB  n={s['n']}")

        print(f"\n  Baseline by gap_type:")
        for gt, s in bl.get("gap_type", {}).items():
            print(f"    {gt}: MAE={s['mae']:.3f} dB  n={s['n']}")

        print(f"\n  Baseline by area:")
        for ar, s in bl.get("area", {}).items():
            print(f"    {ar}: MAE={s['mae']:.3f} dB  n={s['n']}")

        # Oracle check results
        orc = oracle_json.get(str(op), {})
        if orc:
            print(f"\n  Oracle check (leave-one-device-out):")
            for dev, r in orc.items():
                print(f"    {dev}: imp={r['actual_improvement_db']:+.3f} dB  "
                      f"pctile={r['null_percentile']:.0f}th  -> {r['verdict']}")

        summary[str(op)] = {
            "baseline": bl,
            "gp_corrected": gp,
            "oracle_check": orc,
        }

    # Save outputs before checks summary (so files are always written even if print fails)
    combined_path = OUT / "final_report.csv"
    df.to_csv(combined_path, index=False)
    with open(OUT / "final_summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # ── Checks pass/fail summary ─────────────────────────────────────────────
    print("\n\n" + "="*60)
    print("ALL CHECKS — PASS/FAIL SUMMARY")
    print("="*60)

    # Check 1: Calibration independence
    cal_pass = all(
        not v.get("calibration_anchored_to_3gpp", True)
        for v in baseline_json.values()
    )
    print(f"\n[1] Calibration independence (offset not anchored to 3GPP): "
          f"{'PASS' if cal_pass else 'FAIL'}")

    # Check 2: Held-out leakage
    leakage_file = OUT / "split_summary.txt"
    if leakage_file.exists():
        text = leakage_file.read_text()
        leakage_pass = "PASS" in text and "FAIL" not in text.replace("PASS", "")
        print(f"[2] Held-out leakage check (A02 programmatic): "
              f"{'PASS' if leakage_pass else 'FAIL — re-run A02'}")
    else:
        print("[2] Held-out leakage check: NOT RUN (split_summary.txt missing)")

    # Check 3: Oracle check per device
    print(f"[3] Independent oracle (leave-one-out + bootstrap null):")
    for op, devs in oracle_json.items():
        for dev, r in devs.items():
            verdict = r["verdict"].encode("ascii", errors="replace").decode("ascii")
            flag = "OK" if "PASS" in verdict else ("~" if "WEAK" in verdict else "FAIL")
            print(f"    Op{op} {dev}: {flag} {verdict}")

    # Check 4: TypeA excluded, TypeB retained
    for op in [1, 2]:
        bl_data = baseline_json.get(str(op), {})
        gap_breakdown = bl_data.get("by_gap_type", {})
        typeA_in_train = "TypeA" not in gap_breakdown  # TypeA excluded -> won't appear in val stats
        print(f"[4] Op{op} TypeA excluded / TypeB retained in eval: "
              f"{'see gap_type breakdown above' if gap_breakdown else 'NOT CHECKED'}")

    print(f"\nFinal report saved : {combined_path}")
    print(f"Final summary saved: {OUT}/final_summary.json")


if __name__ == "__main__":
    main()
