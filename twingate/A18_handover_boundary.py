"""
A18_handover_boundary.py — Cross-Cell Handover Boundary Prediction

Tests whether Gate 2's already-refined tower geometry (from A16, with
diffuse scattering) correctly predicts WHICH cell is stronger on either
side of a real, held-out-day serving-cell handover.

Ground truth: sustained PCell_Cell_Identity transitions (persistence
filter, default 10s) on the held-out day, restricted to transitions where
both the pre- and post-transition segment fall on the same day (excludes
the pseudo-transition at the very start of a day's drive).

Because every transition here is intra-operator (pc1 only ever reports
Operator 1 cells), we compare Sionna's RAW (uncalibrated) predicted power
between the two candidate towers rather than calibrated absolute RSRP —
this sidesteps the cross-cell OLS non-comparability limitation stated
for M2, since same-operator towers share a comparable EIRP/hardware family.

Metric — Handover Direction Accuracy (HDA): fraction of covered held-out
transitions where Sionna correctly ranks the stronger tower at BOTH the
last pre-transition point and the first post-transition point.
Secondary metric — ranking-flip rate: does the power margin move in the
correct direction between the two points, regardless of absolute
correctness at either point alone.

Usage: python A18_handover_boundary.py [--device pc1] [--persist-s 10]
Requires: out/{device}_refinement_results_scatter_s0p40.csv (from A16)
"""

import sys
import json
import math
import datetime
import numpy as np
import pandas as pd
from pathlib import Path

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import Transmitter, Receiver, PathSolver, PlanarArray, load_scene
from sionna.rt.radio_materials.scattering_pattern import LambertianPattern

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

_dev_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                 if a == "--device" and i+1 < len(sys.argv)), "pc1")
_persist_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv)
                     if a == "--persist-s" and i+1 < len(sys.argv)), "10")
DEVICE        = _dev_arg
MIN_PERSIST_S = float(_persist_arg)

_OP2_DEVICES = {"pc2", "pc3"}
OPERATOR     = 2 if DEVICE in _OP2_DEVICES else 1
SCENE_ORIGIN = (52.506112, 13.321908) if OPERATOR == 2 else (52.507005, 13.323428)
SCENE_XML    = str(ROOT / f"scene_operator{OPERATOR}" / "scene.xml")
SCATTER_S    = 0.4

REFINED_CSV = OUT / f"{DEVICE}_refinement_results_scatter_s0p40.csv"
OUT_CSV     = OUT / f"{DEVICE}_handover_boundary.csv"
OUT_SUMMARY = OUT / f"{DEVICE}_handover_boundary_summary.json"

CELL_COL = "PCell_Cell_Identity"
LAT_COL  = "Latitude"
LON_COL  = "Longitude"

TX_HEIGHT_M = 30.0
RX_HEIGHT_M = 1.5
GPU_BATCH   = 40


def latlon_to_xy(lat, lon, olat, olon):
    x = (lon - olon) * 111_320.0 * math.cos(math.radians(olat))
    y = (lat - olat) * 111_320.0
    return float(x), float(y)


def run_power_batch(rx_lats, rx_lons, tx_lat, tx_lon, scene, solver, olat, olon, tag):
    tx_x, tx_y = latlon_to_xy(tx_lat, tx_lon, olat, olon)
    name = f"tx_{tag}"
    scene.add(Transmitter(name=name, position=[tx_x, tx_y, TX_HEIGHT_M]))
    powers = []
    n = len(rx_lats)
    for start in range(0, n, GPU_BATCH):
        blats = rx_lats[start:start + GPU_BATCH]
        blons = rx_lons[start:start + GPU_BATCH]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = latlon_to_xy(float(la), float(lo), olat, olon)
            scene.add(Receiver(name=f"rx_{tag}_{i}", position=[xi, yi, RX_HEIGHT_M]))
        paths = solver(scene=scene, max_depth=5, diffraction=True)
        a_r = np.array(dr.detach(paths.a[0]))
        a_i = np.array(dr.detach(paths.a[1]))
        plin = (a_r ** 2 + a_i ** 2).sum(axis=-1).squeeze(axis=(1, 2, 3))
        p = 10.0 * np.log10(np.maximum(plin, 1e-30)) + 30.0
        powers.extend(p.tolist())
        for i in range(len(blats)):
            scene.remove(f"rx_{tag}_{i}")
    scene.remove(name)
    return np.array(powers)


def detect_sustained_transitions(df, device, min_persist_s):
    d = df[df["device"] == device].dropna(subset=[CELL_COL, "ts_gps"]).sort_values("ts_gps").reset_index(drop=True)
    cid = d[CELL_COL].values
    change = np.concatenate([[True], cid[1:] != cid[:-1]])
    seg_id = np.cumsum(change)
    d["seg_id"] = seg_id
    segs = d.groupby("seg_id").agg(
        start_ts=("ts_gps", "first"), end_ts=("ts_gps", "last"),
        date=("_date", "first"), cell=(CELL_COL, "first"),
        first_lat=(LAT_COL, "first"), first_lon=(LON_COL, "first"),
        last_lat=(LAT_COL, "last"), last_lon=(LON_COL, "last"),
    ).reset_index()
    segs["dur_s"]         = (segs["end_ts"] - segs["start_ts"]).dt.total_seconds()
    segs["prev_cell"]     = segs["cell"].shift()
    segs["prev_date"]     = segs["date"].shift()
    segs["prev_last_lat"] = segs["last_lat"].shift()
    segs["prev_last_lon"] = segs["last_lon"].shift()

    transitions = segs.iloc[1:].copy()
    transitions = transitions[transitions["date"] == transitions["prev_date"]]  # exclude day-boundary pseudo-transitions
    sustained = transitions[transitions["dur_s"] >= min_persist_s].copy()
    return sustained


def main():
    print("=" * 65)
    print(f"A18  —  Cross-Cell Handover Boundary Prediction  ({DEVICE}, persist>={MIN_PERSIST_S:.0f}s)")
    print("=" * 65)

    if not REFINED_CSV.exists():
        print(f"ERROR: {REFINED_CSV} not found. Run A16 for {DEVICE} first.")
        sys.exit(1)
    refined = pd.read_csv(REFINED_CSV)
    refined_pos = {float(r.cell_id): (r.refined_lat, r.refined_lon) for r in refined.itertuples()}
    print(f"  Loaded {len(refined_pos)} refined tower positions from A16")

    df = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv", low_memory=False)
    df["ts_gps"] = pd.to_datetime(df["ts_gps"], errors="coerce")
    df["_date"]  = df["ts_gps"].dt.date
    VAL_DATE     = datetime.date(2021, 6, 24)

    sustained = detect_sustained_transitions(df, DEVICE, MIN_PERSIST_S)
    val = sustained[sustained["date"] == VAL_DATE].copy()
    print(f"  {DEVICE} held-out (day-3) sustained transitions (persist>={MIN_PERSIST_S:.0f}s): {len(val)}")

    val["from_covered"] = val["prev_cell"].astype(float).isin(refined_pos)
    val["to_covered"]   = val["cell"].astype(float).isin(refined_pos)
    covered = val[val["from_covered"] & val["to_covered"]].reset_index(drop=True)
    print(f"  Covered by A16 refined set (both cells): {len(covered)} "
          f"({100*len(covered)/max(len(val),1):.1f}%)")

    if len(covered) == 0:
        print("No covered transitions -- nothing to evaluate.")
        sys.exit(0)

    print(f"\nLoading Sionna scene (Op{OPERATOR}) with diffuse scattering S={SCATTER_S:.2f}...")
    scene = load_scene(SCENE_XML)
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    mat = scene.radio_materials["itu_concrete"]
    mat.scattering_coefficient = SCATTER_S
    mat.scattering_pattern     = LambertianPattern()
    solver = PathSolver()
    print("  Scene loaded.\n")

    olat, olon = SCENE_ORIGIN

    # Build query list: for each event, need (from@A, to@A, from@B, to@B)
    # A = last point on old cell, B = first point on new cell
    queries = []
    for idx, row in covered.iterrows():
        queries.append((idx, "A", "from", row.prev_cell, row.prev_last_lat, row.prev_last_lon))
        queries.append((idx, "A", "to",   row.cell,      row.prev_last_lat, row.prev_last_lon))
        queries.append((idx, "B", "from", row.prev_cell, row.first_lat,     row.first_lon))
        queries.append((idx, "B", "to",   row.cell,      row.first_lat,     row.first_lon))

    qdf = pd.DataFrame(queries, columns=["event_idx", "point", "role", "cell_id", "lat", "lon"])
    qdf["cell_id"] = qdf["cell_id"].astype(float)

    n_towers = qdf["cell_id"].nunique()
    print(f"  Total power queries: {len(qdf)}  across {n_towers} unique towers")

    power_lookup = {}
    for i, (cell_id, grp) in enumerate(qdf.groupby("cell_id")):
        tx_lat, tx_lon = refined_pos[cell_id]
        lats = grp["lat"].tolist()
        lons = grp["lon"].tolist()
        p = run_power_batch(lats, lons, tx_lat, tx_lon, scene, solver, olat, olon, tag=f"h{i}")
        for (ridx, _row), pw in zip(grp.iterrows(), p):
            power_lookup[ridx] = pw
        if (i + 1) % 20 == 0 or (i + 1) == n_towers:
            print(f"    ...evaluated tower {i+1}/{n_towers}", flush=True)

    qdf["power_dbm"] = qdf.index.map(power_lookup)

    records = []
    for idx, row in covered.iterrows():
        sub = qdf[qdf["event_idx"] == idx]
        pA_from = sub[(sub["point"] == "A") & (sub["role"] == "from")]["power_dbm"].values[0]
        pA_to   = sub[(sub["point"] == "A") & (sub["role"] == "to")]["power_dbm"].values[0]
        pB_from = sub[(sub["point"] == "B") & (sub["role"] == "from")]["power_dbm"].values[0]
        pB_to   = sub[(sub["point"] == "B") & (sub["role"] == "to")]["power_dbm"].values[0]

        correct_A = bool(pA_from > pA_to)   # before switch: 'from' should be stronger
        correct_B = bool(pB_to > pB_from)   # after switch:  'to' should be stronger
        hda_correct = correct_A and correct_B
        margin_A = pA_from - pA_to
        margin_B = pB_to - pB_from
        flip_correct = bool(margin_B > margin_A)  # margin moved in the right direction

        records.append({
            "event_idx": idx,
            "from_cell": row.prev_cell, "to_cell": row.cell,
            "dur_s": row.dur_s,
            "pA_from": pA_from, "pA_to": pA_to,
            "pB_from": pB_from, "pB_to": pB_to,
            "correct_A": correct_A, "correct_B": correct_B,
            "hda_correct": hda_correct, "flip_correct": flip_correct,
            "margin_A_dB": margin_A, "margin_B_dB": margin_B,
        })

    rec_df = pd.DataFrame(records)
    rec_df.to_csv(OUT_CSV, index=False)

    hda = rec_df["hda_correct"].mean()
    flip_rate = rec_df["flip_correct"].mean()
    correct_rows = rec_df[rec_df["hda_correct"]]
    correct_margin = correct_rows[["margin_A_dB", "margin_B_dB"]].mean().mean() if len(correct_rows) else float("nan")

    print(f"\n{'='*65}")
    print(f"A18 RESULTS — {DEVICE}, persist>={MIN_PERSIST_S:.0f}s, N={len(rec_df)} covered transitions")
    print(f"{'='*65}")
    print(f"  Handover Direction Accuracy (HDA): {hda*100:.1f}%  ({int(rec_df['hda_correct'].sum())}/{len(rec_df)})")
    print(f"  Ranking-flip rate (softer):        {flip_rate*100:.1f}%  ({int(rec_df['flip_correct'].sum())}/{len(rec_df)})")
    print(f"  Mean margin at correct calls:       {correct_margin:.2f} dB")

    summary = {
        "device": DEVICE, "min_persist_s": MIN_PERSIST_S,
        "n_val_transitions": int(len(val)), "n_covered": int(len(covered)),
        "hda": float(hda), "flip_rate": float(flip_rate),
        "mean_margin_correct_db": float(correct_margin) if correct_margin == correct_margin else None,
    }
    with open(OUT_SUMMARY, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved: {OUT_CSV.name}  {OUT_SUMMARY.name}")


if __name__ == "__main__":
    main()
