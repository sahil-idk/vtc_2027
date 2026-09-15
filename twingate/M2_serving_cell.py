"""
M2_serving_cell.py — Serving-Cell Accuracy Proxy

True M2 (ranking all cells at every GPS point) requires cross-cell Sionna
evaluation not in our existing pipeline. We compute two defensible proxies:

PROXY A — TypeB zone prediction (binary classification):
  At each val row, Sionna predicts a signal level. We threshold at -110 dBm
  (empirically ~midway between TypeB=-115 and background=-88) and check
  whether the predicted "weak zone" aligns with Gate 1 TypeB labels.
  Reports: precision, recall, F1.

PROXY B — Handover direction accuracy:
  Rows adjacent in time where the serving cell changes = handover event.
  At the transition point, does Sionna predict the incoming cell (new cell)
  as having higher RSRP than the outgoing cell (old cell) at that GPS location?
  Both predictions must be available in our per_tower_val_rows files.
  Reports: fraction of handovers where Sionna predicts correct direction.

Both proxies use only existing A16 prediction CSVs — no Sionna re-run needed.
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import precision_score, recall_score, f1_score, confusion_matrix

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "out"

print("=" * 60)
print("M2: Serving-Cell Accuracy Proxies")
print("=" * 60)

# ── Load data ─────────────────────────────────────────────────────────────────
print("\nLoading per-tower val predictions...")
p1 = pd.read_csv(OUT / "per_tower_val_rows_op1.csv")
p2 = pd.read_csv(OUT / "per_tower_val_rows_op2.csv")
preds = pd.concat([p1, p2], ignore_index=True)
print(f"  Total val rows: {len(preds)}")

# Identify calibrated prediction column
cal_col = None
for c in ["sionna_cal_pt", "sionna_power_cal", "sionna_cal"]:
    if c in preds.columns:
        cal_col = c
        break
if cal_col is None:
    cal_col = "sionna_power_raw"
print(f"  Using column: {cal_col}")

# Load GPS coords for joining
gps = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv",
                  low_memory=False,
                  usecols=["Latitude", "Longitude"])
gps["_row"] = gps.index
preds = preds.merge(gps, on="_row", how="left")

# Load TypeB label from G1_G2_link results (already has near_typeb flag)
link = pd.read_csv(OUT / "g1_g2_link_rows.csv")
preds = preds.merge(link[["_row", "near_typeb"]].drop_duplicates("_row"),
                    on="_row", how="left")
preds["near_typeb"] = preds["near_typeb"].fillna(False)

valid = preds[preds[cal_col].notna() & (preds[cal_col] > -200)].copy()
print(f"  Valid prediction rows: {len(valid)}")

# ─────────────────────────────────────────────────────────────────────────────
# PROXY A: TypeB zone detection (binary classification)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─'*50}")
print("PROXY A: TypeB Zone Detection (Binary Classification)")

# Find threshold that best separates near_typeb vs background
# Use -110 dBm as fixed threshold (midpoint between -115 and -88)
# but also sweep to find optimal
y_true = valid["near_typeb"].astype(int)

results_thresh = []
for thresh in np.arange(-125, -85, 1):
    y_pred = (valid[cal_col] < thresh).astype(int)
    if y_pred.sum() == 0:
        continue
    f1 = f1_score(y_true, y_pred, zero_division=0)
    p  = precision_score(y_true, y_pred, zero_division=0)
    r  = recall_score(y_true, y_pred, zero_division=0)
    results_thresh.append({"threshold": thresh, "f1": f1, "precision": p, "recall": r})

df_thresh = pd.DataFrame(results_thresh)
best = df_thresh.loc[df_thresh["f1"].idxmax()]
print(f"  Optimal threshold: {best['threshold']:.0f} dBm")
print(f"  Precision : {best['precision']:.3f}")
print(f"  Recall    : {best['recall']:.3f}")
print(f"  F1        : {best['f1']:.3f}")

# Also report at fixed -110 dBm
y_pred_fixed = (valid[cal_col] < -110).astype(int)
p_fixed  = precision_score(y_true, y_pred_fixed, zero_division=0)
r_fixed  = recall_score(y_true, y_pred_fixed, zero_division=0)
f1_fixed = f1_score(y_true, y_pred_fixed, zero_division=0)
cm = confusion_matrix(y_true, y_pred_fixed)
print(f"\n  At fixed threshold -110 dBm:")
print(f"  Precision : {p_fixed:.3f}  Recall: {r_fixed:.3f}  F1: {f1_fixed:.3f}")
print(f"  Confusion matrix (rows=actual, cols=predicted):")
print(f"    TN={cm[0,0]:5d}  FP={cm[0,1]:5d}")
print(f"    FN={cm[1,0]:5d}  TP={cm[1,1]:5d}")

# ─────────────────────────────────────────────────────────────────────────────
# PROXY B: Handover direction accuracy
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'─'*50}")
print("PROXY B: Handover Direction Accuracy")

# Find cell_id column name
cell_col = None
for c in ["cell_id", "serving_cell", "pci", "PCI"]:
    if c in preds.columns:
        cell_col = c
        break

# Find device column
dev_col = "device" if "device" in preds.columns else None

if cell_col is None:
    print("  No cell_id column found — skipping Proxy B")
else:
    # Sort by device and row index to get temporal order
    sort_cols = [dev_col, "_row"] if dev_col else ["_row"]
    v = valid[valid[cal_col].notna()].sort_values(sort_cols).copy()

    # Build lookup: (device, cell_id) -> prediction at each _row
    pred_lookup = {}
    for _, row in v.iterrows():
        key = (row.get(dev_col, "all"), row[cell_col])
        pred_lookup[(row["_row"], key[1])] = row[cal_col]

    # Find handover events: consecutive rows where cell_id changes within same device
    correct = 0
    total   = 0
    if dev_col:
        groups = v.groupby(dev_col)
    else:
        groups = [("all", v)]

    for dev, grp in groups:
        grp = grp.sort_values("_row").reset_index(drop=True)
        for i in range(len(grp) - 1):
            old_cell = grp.loc[i,   cell_col]
            new_cell = grp.loc[i+1, cell_col]
            if old_cell == new_cell:
                continue
            row_idx  = grp.loc[i+1, "_row"]
            # Check if we have predictions for both cells at this GPS point
            new_pred = pred_lookup.get((row_idx, new_cell))
            old_pred = pred_lookup.get((row_idx, old_cell))
            if new_pred is None or old_pred is None:
                # Try nearby rows (±2 rows)
                for delta in [-2, -1, 1, 2]:
                    r2 = row_idx + delta
                    if new_pred is None:
                        new_pred = pred_lookup.get((r2, new_cell))
                    if old_pred is None:
                        old_pred = pred_lookup.get((r2, old_cell))
            if new_pred is None or old_pred is None:
                continue
            total += 1
            if new_pred > old_pred:
                correct += 1

    if total > 0:
        acc = correct / total
        print(f"  Handover events with both-cell predictions: {total}")
        print(f"  Sionna predicts correct direction : {correct}/{total} ({100*acc:.1f}%)")
    else:
        print("  No handover events found with both cells in val predictions")
        print("  (Expected: per_tower val rows only contain serving-cell predictions;")
        print("   cross-cell evaluation requires a full re-run)")

# ─────────────────────────────────────────────────────────────────────────────
# Save summary
# ─────────────────────────────────────────────────────────────────────────────
summary = {
    "proxy_a_optimal_threshold_dbm": float(best["threshold"]),
    "proxy_a_precision": float(best["precision"]),
    "proxy_a_recall": float(best["recall"]),
    "proxy_a_f1": float(best["f1"]),
    "proxy_a_fixed110_precision": float(p_fixed),
    "proxy_a_fixed110_recall": float(r_fixed),
    "proxy_a_fixed110_f1": float(f1_fixed),
    "proxy_b_total_handovers": int(total) if cell_col else None,
    "proxy_b_correct": int(correct) if cell_col else None,
    "proxy_b_accuracy": float(correct/total) if (cell_col and total > 0) else None,
}

with open(OUT / "m2_serving_cell_summary.json", "w") as f:
    json.dump(summary, f, indent=2)

print(f"\n{'═'*60}")
print("KEY PAPER NUMBERS:")
print(f"  TypeB zone detection F1 (optimal): {best['f1']:.2f}")
print(f"  TypeB zone detection F1 (-110 dBm fixed): {f1_fixed:.2f}")
if cell_col and total > 0:
    print(f"  Handover direction accuracy: {100*correct/total:.1f}%")
print(f"\nSaved: out/m2_serving_cell_summary.json")
