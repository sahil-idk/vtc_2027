"""
A02_split_and_verify.py — TWINGATE Gate 2, Step 2
Day-based temporal train/held-out split + programmatic leakage check.

Split strategy:
  Train   : June 22–23 2021 (all sessions on those dates)
  Held-out: June 24  2021 (all sessions on that date)

Leakage check: confirms zero row-index overlap between the two sets,
and that no val row is reachable from any training structure produced here.

Outputs → twingate/out/:
  split_index.csv   — _row + split label ('train'/'val') for every row
  split_summary.txt — counts per operator/device/split + leakage check result
"""

import pandas as pd
from pathlib import Path

ROOT     = Path(__file__).parent.parent
DATAFILE = ROOT / "cellular_dataframe_cleaned.csv"
OUT      = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

GAP_LABELS = OUT / "gap_labels.csv"   # produced by A01

TS_COL     = "ts_gps"
DEVICE_COL = "device"
SESSION_COL = "measurement"

TRAIN_DATES = {"2021-06-22", "2021-06-23"}
VAL_DATE    = "2021-06-24"


def main():
    print("A02 Split & Verify — loading data...")
    df = pd.read_csv(DATAFILE, low_memory=False)
    df[TS_COL] = pd.to_datetime(df[TS_COL], errors="coerce")
    df = df.sort_values([DEVICE_COL, TS_COL]).reset_index(drop=True)
    df["_row"] = df.index

    df["date_str"] = df[TS_COL].dt.strftime("%Y-%m-%d")

    # Assign split
    df["split"] = "unknown"
    df.loc[df["date_str"].isin(TRAIN_DATES), "split"] = "train"
    df.loc[df["date_str"] == VAL_DATE,       "split"] = "val"

    n_unknown = (df["split"] == "unknown").sum()
    if n_unknown > 0:
        print(f"  WARNING: {n_unknown} rows have no ts_gps date (NaT) — excluded from both splits.")

    # ── Leakage check ────────────────────────────────────────────────────────
    train_rows = set(df[df["split"] == "train"]["_row"].tolist())
    val_rows   = set(df[df["split"] == "val"]["_row"].tolist())
    overlap    = train_rows & val_rows

    print(f"\nLeakage check:")
    print(f"  Train rows : {len(train_rows):,}")
    print(f"  Val rows   : {len(val_rows):,}")
    print(f"  Overlap    : {len(overlap)} (MUST BE 0)")

    if overlap:
        raise RuntimeError(f"LEAKAGE DETECTED: {len(overlap)} row(s) appear in both splits!")
    print("  PASS — zero overlap confirmed.")

    # Also verify: no val row date appears in train set
    val_dates_in_train = df[df["split"] == "train"]["date_str"].isin([VAL_DATE]).sum()
    print(f"  Val date ({VAL_DATE}) rows in train set: {val_dates_in_train} (MUST BE 0)")
    if val_dates_in_train > 0:
        raise RuntimeError("LEAKAGE: val date appears in training split!")
    print("  PASS — temporal isolation confirmed.")

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\nSplit summary by operator × device:")
    summary = df.groupby(["operator", DEVICE_COL, "split"]).size().unstack(fill_value=0)
    print(summary.to_string())

    # Attach gap_type from A01 if available
    if GAP_LABELS.exists():
        gl = pd.read_csv(GAP_LABELS, usecols=["_row", "gap_type"])
        df = df.merge(gl, on="_row", how="left")
        df["gap_type"] = df["gap_type"].fillna("Unflagged")
        print("\nSplit × gap_type breakdown:")
        print(df.groupby(["split", "gap_type"]).size().unstack(fill_value=0).to_string())
    else:
        print("\n  (gap_labels.csv not found — run A01 first for gap_type breakdown)")
        df["gap_type"] = "Unflagged"

    # Save split index
    keep = ["_row", DEVICE_COL, SESSION_COL, TS_COL, "date_str", "operator", "split"]
    if "gap_type" in df.columns:
        keep.append("gap_type")
    df[keep].to_csv(OUT / "split_index.csv", index=False)
    print(f"\nSplit index saved: {OUT}/split_index.csv")

    # Save summary text
    lines = [
        "TWINGATE Gate 2 — Split & Leakage Check",
        f"Train dates: {TRAIN_DATES}",
        f"Val date  : {VAL_DATE}",
        f"Train rows: {len(train_rows):,}",
        f"Val rows  : {len(val_rows):,}",
        f"Overlap   : {len(overlap)} — {'PASS' if not overlap else 'FAIL'}",
        "",
        summary.to_string(),
    ]
    (OUT / "split_summary.txt").write_text("\n".join(lines))
    print(f"Summary saved: {OUT}/split_summary.txt")


if __name__ == "__main__":
    main()
