"""
A19_gate2_final.py — Unified Gate-2 Pipeline (Task 1)

Replaces two previously mismatched, never-combined scripts:
  - A16_tx_antenna_refinement.py : 4D (dx,dy,dh,azimuth) + tr38901 sector
                                    antenna, but NO scattering, and it was
                                    accidentally built on the STRATIFIED
                                    split (out/stratified_split_index.csv)
                                    instead of the proper temporal split.
  - A16_tx_refinement_scatter.py : 2D (dx,dy) position-only + isotropic
                                    antenna + scattering. This is what
                                    actually produced the numbers currently
                                    sitting in the paper's Table I, despite
                                    the paper's text describing the 4D
                                    sector-antenna method.

This script does the 4D optimization AND the scattering AND uses the
correct temporal split, all in one place, so the methodology described in
the paper and the numbers it reports finally come from the same run.

It also fixes the Gate-1/Gate-2 circularity flagged by review: for
Operator 2 (pc2, pc3) — the only operator with a Gate-1-confirmed dead
zone — training rows within ZONE_EXCLUDE_RADIUS_M of the TypeB centroid
are dropped from that device's training set BEFORE WCL init, BEFORE the
Nelder-Mead search, and BEFORE the final OLS calibration fit. Operator 1
(pc1, pc4) gets no exclusion — there is no Gate-1-confirmed dead zone
there to leak from (C=0.00).

It also fixes a carrier-frequency bug present in every prior script (A15,
A16-antenna, A16-scatter): none of them ever set scene.frequency, so Sionna
silently used its load_scene() default of 3.5 GHz, while the real Berlin
V2X measurements span 700 MHz-2.7 GHz and are dominated by 1800 MHz for
both operators. Frequency is ~constant per tower (5/321 towers show more
than one band), so this script sets scene.frequency to each tower's own
actual measured band (mode of PCell_freq_MHz) before its Sionna calls.

Only reads: cellular_dataframe_cleaned.csv, out/gap_labels.csv.
Does NOT read any of: sionna_raw.csv, per_tower_val_rows_op*.csv,
g1_g2_link_rows.csv, pc*_a16_results.csv, pc*_refinement_results_*.csv —
all confirmed stale or from a mismatched pipeline run.

Usage:
  python A19_gate2_final.py --device pc2
  python A19_gate2_final.py --device pc2 --dry-run --max-towers 2 --maxiter 10

Outputs (real run):
  out/{device}_gate2_final.csv               per-tower results
  out/{device}_gate2_final_summary.json       run metadata + weighted MAE
  out/{device}_gate2_final_val_predictions.csv  per-row calibrated val predictions

Outputs (--dry-run):
  out/{device}_gate2_final_dryrun.csv / _dryrun_summary.json / _dryrun_val_predictions.csv
  (separate filenames so a dry run can never be mistaken for or collide
  with a real run's checkpoint)

Split: TEMPORAL — Days 1-2 (June 22-23) = train, Day 3 (June 24) = val.
"""

import sys
import gc
import json
import math
import time
import datetime
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.optimize import minimize
from scipy.stats import linregress, spearmanr

# Windows consoles default to a cp1252-family codec that can't encode
# characters like the ones this script prints; force UTF-8 so a print
# statement can never crash a multi-hour run after expensive Sionna calls.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import Transmitter, Receiver, PathSolver, PlanarArray, load_scene
from sionna.rt.radio_materials.scattering_pattern import LambertianPattern

ROOT = Path(__file__).parent.parent
OUT = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

# ── CLI ──────────────────────────────────────────────────────────────────────
ap = argparse.ArgumentParser()
ap.add_argument("--device", required=True, choices=["pc1", "pc2", "pc3", "pc4"])
ap.add_argument("--dry-run", action="store_true",
                 help="cap towers and iterations, write to *_dryrun.* files")
ap.add_argument("--max-towers", type=int, default=None,
                 help="limit number of towers processed (mainly for --dry-run)")
ap.add_argument("--maxiter", type=int, default=80,
                 help="Nelder-Mead max iterations (default 80, lower for --dry-run)")
ap.add_argument("--skip-cells", type=str, default="",
                 help="comma-separated cell_ids to skip for now (revisit later); "
                      "e.g. towers that reproducibly OOM on this machine")
args = ap.parse_args()

DEVICE = args.device
DRY_RUN = args.dry_run
MAX_TOWERS = args.max_towers
SKIP_CELLS = {float(c) for c in args.skip_cells.split(",") if c.strip()}
MAXITER = args.maxiter

SUFFIX = "_dryrun" if DRY_RUN else ""

# ── Constants ────────────────────────────────────────────────────────────────
_OP2_DEVICES = {"pc2", "pc3"}
OPERATOR = 2 if DEVICE in _OP2_DEVICES else 1
SCENE_ORIGIN = (52.506112, 13.321908) if OPERATOR == 2 else (52.507005, 13.323428)
SCENE_XML = str(ROOT / f"scene_operator{OPERATOR}" / "scene.xml")

RSRP_COL = "PCell_RSRP_max"
CELL_COL = "PCell_Cell_Identity"
LAT_COL = "Latitude"
LON_COL = "Longitude"
FREQ_COL = "PCell_freq_MHz"

TX_HEIGHT_INIT = 30.0
TX_TILT_DEG = -8.0
RX_HEIGHT_M = 1.5
GPU_BATCH = 8  # reduced from 40: this machine has only 4GB VRAM / 16GB RAM,
# and large towers (1000+ training rows) were reproducibly OOM-killing at the
# larger batch size. Smaller batch = same total rows processed, less peak
# memory per Sionna call, no change to results (full mode still uses every row).
MIN_ROWS = 5
ALPHA_CLIP = (0.0, 2.0)
SENTINEL = -100.0
MIN_SIONNA_STD = 1.0

SEARCH_RADIUS = 500.0   # m, max horizontal displacement from WCL
HEIGHT_MIN = 10.0
HEIGHT_MAX = 60.0
AZIMUTH_GRID_DEG = [0, 45, 90, 135, 180, 225, 270, 315]

SCATTER_S = 0.4          # TR 38.901 Table 7.4.2-1 concrete at 2 GHz

# ── Gate-1/Gate-2 independence fix ──────────────────────────────────────────
TYPEB_CENTROID_LAT = 52.514
TYPEB_CENTROID_LON = 13.349
ZONE_EXCLUDE_RADIUS_M = 150.0   # same radius used for convergence val-row selection
APPLY_ZONE_EXCLUSION = (OPERATOR == 2)   # only where Gate 1 confirmed a dead zone

print("=" * 70)
print(f"A19 — Unified Gate-2 Pipeline  ({DEVICE}, Operator {OPERATOR})")
print(f"  4D (dx,dy,dh,azimuth) + tr38901 sector antenna + scattering S={SCATTER_S}")
print(f"  Temporal split (proper, date-based)")
print(f"  Zone exclusion: {'ON — dropping training rows within '  + str(ZONE_EXCLUDE_RADIUS_M) + 'm of TypeB centroid' if APPLY_ZONE_EXCLUSION else 'N/A (Operator 1, no confirmed dead zone)'}")
print(f"  Full mode: ALL training rows used, no subsampling")
if DRY_RUN:
    print(f"  *** DRY RUN *** max_towers={MAX_TOWERS} maxiter={MAXITER}")
print("=" * 70)


# ── Geometry helpers ─────────────────────────────────────────────────────────
def latlon_to_xy(lat, lon, olat, olon):
    x = (lon - olon) * 111_320.0 * math.cos(math.radians(olat))
    y = (lat - olat) * 111_320.0
    return float(x), float(y)


def xy_to_latlon(x, y, olat, olon):
    lat = olat + y / 111_320.0
    lon = olon + x / (111_320.0 * math.cos(math.radians(olat)))
    return lat, lon


def haversine_m(lat1, lon1, lat2, lon2):
    R = 6_371_000.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlmb = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))


def compass_to_sionna_yaw(azimuth_deg):
    return math.pi / 2.0 - math.radians(azimuth_deg % 360.0)


def power_dbm(paths):
    a_r = np.array(dr.detach(paths.a[0]))
    a_i = np.array(dr.detach(paths.a[1]))
    plin = (a_r ** 2 + a_i ** 2).sum(axis=-1).squeeze(axis=(1, 2, 3))
    return 10.0 * np.log10(np.maximum(plin, 1e-30)) + 30.0


# ── Sionna batch runner ───────────────────────────────────────────────────────
_call_counter = [0]
_call_time_total = [0.0]


def run_sionna_batch(rx_lats, rx_lons, tx_lat, tx_lon, tx_height, az_deg,
                      scene, solver, olat, olon, tag="a19"):
    t0 = time.time()
    tx_x, tx_y = latlon_to_xy(tx_lat, tx_lon, olat, olon)
    yaw = compass_to_sionna_yaw(az_deg)
    tilt = math.radians(TX_TILT_DEG)
    scene.add(Transmitter(
        name=f"tx_{tag}",
        position=[tx_x, tx_y, float(tx_height)],
        orientation=[yaw, tilt, 0.0],
    ))
    powers = []
    n_batches = 0
    for start in range(0, len(rx_lats), GPU_BATCH):
        blats = rx_lats[start:start + GPU_BATCH]
        blons = rx_lons[start:start + GPU_BATCH]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = latlon_to_xy(float(la), float(lo), olat, olon)
            scene.add(Receiver(name=f"rx_{tag}_{i}", position=[xi, yi, RX_HEIGHT_M]))
        paths = solver(scene=scene, max_depth=5, diffraction=True)
        powers.extend(power_dbm(paths).tolist())
        for i in range(len(blats)):
            scene.remove(f"rx_{tag}_{i}")
        n_batches += 1
        # For large towers a single run_sionna_batch() call can internally
        # loop over 50-100+ mini-batches; without a flush in here, Dr.Jit's
        # kernel/malloc cache accumulates across all of them before the
        # per-tower cleanup ever gets a chance to run, and can OOM mid-call.
        if n_batches % 4 == 0:
            dr.flush_malloc_cache()
    scene.remove(f"tx_{tag}")
    _call_counter[0] += 1
    _call_time_total[0] += time.time() - t0
    return np.array(powers)


def fit_ols(sionna_powers, measured_rsrp):
    """Returns (alpha, intercept, mae). Falls back to per-tower mean if flat."""
    x, y = sionna_powers, measured_rsrp
    valid = x > SENTINEL
    x, y = x[valid], y[valid]
    if len(x) < MIN_ROWS or x.std() < MIN_SIONNA_STD:
        mean_y = float(y.mean()) if len(y) > 0 else 0.0
        mae = float(np.abs(y - mean_y).mean()) if len(y) > 0 else 1e6
        return 0.0, mean_y, mae
    sl, ic, _, _, _ = linregress(x, y)
    alpha = float(np.clip(sl, *ALPHA_CLIP))
    pred = ic + alpha * x
    return alpha, float(ic), float(np.abs(y - pred).mean())


def fit_ols_mae(sionna_powers, measured_rsrp):
    _, _, mae = fit_ols(sionna_powers, measured_rsrp)
    return mae


def main():
    df = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv", low_memory=False)
    df["_row"] = df.index
    gaps = pd.read_csv(OUT / "gap_labels.csv")

    # ── Temporal split (proper — date based, NOT the stratified split) ───────
    df["_date"] = pd.to_datetime(df["ts_gps"], errors="coerce").dt.date
    VAL_DATE = datetime.date(2021, 6, 24)
    df["new_split"] = df["_date"].apply(lambda d: "val" if d == VAL_DATE else "train")

    dev_df = df[df["device"] == DEVICE].copy()
    dev_df = dev_df.merge(gaps[["_row", "gap_type"]], on="_row", how="left")
    dev_df["gap_type"] = dev_df["gap_type"].fillna("Unflagged")

    clean = dev_df[
        (dev_df["gap_type"] == "Unflagged") &
        dev_df[RSRP_COL].notna() &
        dev_df[LAT_COL].notna() &
        dev_df[LON_COL].notna() &
        dev_df["_date"].notna()
    ].copy()

    train_all = clean[clean["new_split"] == "train"].copy()
    val_all = clean[clean["new_split"] == "val"].copy()
    print(f"\n  {DEVICE} train={len(train_all):,} (Jun 22-23)  val={len(val_all):,} (Jun 24)")

    n_excluded = 0
    if APPLY_ZONE_EXCLUSION:
        train_all["_dist_typeb"] = haversine_m(
            train_all[LAT_COL], train_all[LON_COL],
            TYPEB_CENTROID_LAT, TYPEB_CENTROID_LON)
        before = len(train_all)
        excluded_rows = train_all[train_all["_dist_typeb"] <= ZONE_EXCLUDE_RADIUS_M]
        n_excluded = len(excluded_rows)
        if n_excluded > 0:
            per_tower_excl = (excluded_rows.groupby(CELL_COL).size()
                               .sort_values(ascending=False))
            print(f"  Zone exclusion: dropping {n_excluded}/{before} training rows "
                  f"within {ZONE_EXCLUDE_RADIUS_M}m of TypeB centroid")
            print(f"  Towers affected ({len(per_tower_excl)}):")
            print(per_tower_excl.to_string())
        train_all = train_all[train_all["_dist_typeb"] > ZONE_EXCLUDE_RADIUS_M].copy()
        print(f"  Training rows after exclusion: {len(train_all):,}")

    # ── WCL init (computed AFTER exclusion, so it never sees zone rows) ──────
    olat, olon = SCENE_ORIGIN
    wcl = (
        train_all.groupby(CELL_COL)[[LAT_COL, LON_COL, RSRP_COL]]
        .apply(lambda g: pd.Series({
            "wcl_lat": np.average(g[LAT_COL], weights=10 ** (g[RSRP_COL] / 10)),
            "wcl_lon": np.average(g[LON_COL], weights=10 ** (g[RSRP_COL] / 10)),
            "n_train": len(g),
        }), include_groups=False)
        .reset_index()
    )
    print(f"  {len(wcl)} towers from (post-exclusion) training rows\n")

    if MAX_TOWERS is not None:
        val_counts = val_all.groupby(CELL_COL).size()
        wcl["_n_val"] = wcl[CELL_COL].map(val_counts).fillna(0)
        eligible = wcl[wcl["_n_val"] >= MIN_ROWS].copy()
        if len(eligible) == 0:
            print("  WARNING: no towers have >= MIN_ROWS val rows; falling back to n_train sort")
            eligible = wcl
        # prefer towers actually affected by zone exclusion, so the dry run
        # exercises that path; fall back to largest n_train otherwise
        if APPLY_ZONE_EXCLUSION and n_excluded > 0:
            affected_ids = set(excluded_rows[CELL_COL].unique())
            eligible["_affected"] = eligible[CELL_COL].isin(affected_ids)
            eligible = eligible.sort_values(["_affected", "n_train"], ascending=[False, False])
        else:
            eligible = eligible.sort_values("n_train", ascending=False)
        wcl = eligible.head(MAX_TOWERS)
        print(f"  --max-towers {MAX_TOWERS}: restricting to {list(wcl[CELL_COL].astype(int))} "
              f"(n_train/n_val: {list(zip(wcl['n_train'].astype(int), wcl['_n_val'].astype(int)))})\n")

    # ── Scene: tr38901 sector antenna + diffuse scattering, both active ──────
    print(f"Loading Sionna scene (Op{OPERATOR}) with tr38901 TX pattern "
          f"+ scattering S={SCATTER_S}...")
    scene = load_scene(SCENE_XML)
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='tr38901', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    mat = scene.radio_materials["itu_concrete"]
    mat.scattering_coefficient = SCATTER_S
    mat.scattering_pattern = LambertianPattern()
    solver = PathSolver()
    print(f"  Scene loaded. tr38901 sector antenna + itu_concrete S={SCATTER_S}, "
          f"pattern={type(mat.scattering_pattern).__name__}\n")

    ckpt_path = OUT / f"{DEVICE}_gate2_final{SUFFIX}.csv"
    valpred_path = OUT / f"{DEVICE}_gate2_final{SUFFIX}_val_predictions.csv"
    summary_path = OUT / f"{DEVICE}_gate2_final{SUFFIX}_summary.json"

    if ckpt_path.exists():
        done_df = pd.read_csv(ckpt_path)
        done_cells = set(done_df["cell_id"].unique())
        print(f"  Checkpoint found: {len(done_cells)} towers already done, resuming...")
    else:
        done_cells = set()

    valpred_write_hdr = not valpred_path.exists()

    for _, tower in wcl.iterrows():
        cell = tower[CELL_COL]
        wcl_lat = tower["wcl_lat"]
        wcl_lon = tower["wcl_lon"]

        if cell in done_cells:
            print(f"  Tower {int(cell)}: already done (checkpoint)")
            continue

        if cell in SKIP_CELLS:
            print(f"  Tower {int(cell)}: DEFERRED via --skip-cells "
                  f"(not done, not skipped-for-real — revisit separately)")
            continue

        tr = train_all[train_all[CELL_COL] == cell]
        va = val_all[val_all[CELL_COL] == cell]

        if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
            print(f"  Tower {int(cell)}: SKIP (tr={len(tr)} va={len(va)}, "
                  f"post-exclusion insufficient rows)")
            continue

        # ── Set carrier frequency to this tower's actual measured band ───────
        # Sionna's load_scene() defaults to 3.5 GHz if never set; the real
        # LTE bands here are 700 MHz-2.7 GHz (dominated by 1800 MHz), so this
        # must be set per tower or the ray-tracing physics (wavelength,
        # free-space path loss, diffraction) run at the wrong frequency.
        freq_vals = pd.concat([tr[FREQ_COL], va[FREQ_COL]]).dropna()
        if len(freq_vals) > 0:
            tower_freq_mhz = float(freq_vals.mode().iloc[0])
        else:
            tower_freq_mhz = 1800.0  # dataset-wide dominant band, documented fallback
            print(f"  Tower {int(cell)}: WARNING no {FREQ_COL} data, "
                  f"falling back to {tower_freq_mhz} MHz")
        scene.frequency = tower_freq_mhz * 1e6

        t_tower_start = time.time()
        print(f"\n  Tower {int(cell)}: tr={len(tr):4d} va={len(va):4d}  "
              f"freq={tower_freq_mhz:.0f}MHz", flush=True)

        try:
            # FULL MODE: no subsampling anywhere
            opt_rows = tr
            opt_lats = opt_rows[LAT_COL].tolist()
            opt_lons = opt_rows[LON_COL].tolist()
            opt_rsrp = opt_rows[RSRP_COL].values

            wcl_x0, wcl_y0 = latlon_to_xy(wcl_lat, wcl_lon, olat, olon)

            wcl_pows = run_sionna_batch(opt_lats, opt_lons, wcl_lat, wcl_lon,
                                         TX_HEIGHT_INIT, 0.0, scene, solver, olat, olon)
            wcl_mae_opt = fit_ols_mae(wcl_pows, opt_rsrp)

            print(f"    Azimuth grid ({len(AZIMUTH_GRID_DEG)} dirs, "
                  f"{len(opt_rows)} rows each)...", end="", flush=True)
            best_az, best_az_mae = 0.0, 1e9
            for az in AZIMUTH_GRID_DEG:
                pows = run_sionna_batch(opt_lats, opt_lons, wcl_lat, wcl_lon,
                                         TX_HEIGHT_INIT, float(az),
                                         scene, solver, olat, olon)
                mae = fit_ols_mae(pows, opt_rsrp)
                if mae < best_az_mae:
                    best_az_mae, best_az = mae, float(az)
            print(f" best={best_az:.0f}° mae={best_az_mae:.3f} dB "
                  f"(avg {_call_time_total[0]/_call_counter[0]:.2f}s/call so far)", flush=True)

            eval_count = [0]

            def objective(params):
                dx, dy, dh, az = (float(params[0]), float(params[1]),
                                   float(params[2]), float(params[3]))
                if math.sqrt(dx ** 2 + dy ** 2) > SEARCH_RADIUS:
                    return 1e6
                h = TX_HEIGHT_INIT + dh
                if h < HEIGHT_MIN or h > HEIGHT_MAX:
                    return 1e6
                tx_lat, tx_lon = xy_to_latlon(wcl_x0 + dx, wcl_y0 + dy, olat, olon)
                pows = run_sionna_batch(opt_lats, opt_lons, tx_lat, tx_lon,
                                         h, az % 360.0, scene, solver, olat, olon)
                mae = fit_ols_mae(pows, opt_rsrp)
                eval_count[0] += 1
                return mae

            x0 = np.array([0.0, 0.0, 0.0, best_az])
            init_simplex = np.array([
                [0, 0, 0, best_az],
                [50, 0, 0, best_az],
                [0, 50, 0, best_az],
                [0, 0, 10, best_az],
                [0, 0, 0, best_az + 45],
            ], dtype=float)

            print(f"    NM 4D ({MAXITER} max iters, {len(opt_rows)} rows/eval)...",
                  end="", flush=True)
            t_nm = time.time()
            result = minimize(
                objective, x0=x0, method='Nelder-Mead',
                options={'xatol': 5.0, 'fatol': 0.01, 'maxiter': MAXITER,
                         'initial_simplex': init_simplex}
            )
            dx_opt, dy_opt, dh_opt, az_opt = result.x
            az_opt = float(az_opt) % 360.0
            h_opt = float(np.clip(TX_HEIGHT_INIT + float(dh_opt), HEIGHT_MIN, HEIGHT_MAX))
            ref_lat, ref_lon = xy_to_latlon(wcl_x0 + dx_opt, wcl_y0 + dy_opt, olat, olon)
            delta_m = math.sqrt(dx_opt ** 2 + dy_opt ** 2)
            print(f" done ({eval_count[0]} evals, {time.time()-t_nm:.0f}s)  "
                  f"Δxy={delta_m:.0f}m h={h_opt:.1f}m az={az_opt:.0f}°  "
                  f"mae: {wcl_mae_opt:.3f}->{result.fun:.3f} dB", flush=True)

            # Final eval: ALL train rows (post-exclusion) + ALL val rows
            tr_eval = tr
            print(f"    Final eval (tr={len(tr_eval)} va={len(va)})...", end="", flush=True)
            tr_pw_wcl = run_sionna_batch(tr_eval[LAT_COL].tolist(), tr_eval[LON_COL].tolist(),
                                          wcl_lat, wcl_lon, TX_HEIGHT_INIT, 0.0,
                                          scene, solver, olat, olon)
            va_pw_wcl = run_sionna_batch(va[LAT_COL].tolist(), va[LON_COL].tolist(),
                                          wcl_lat, wcl_lon, TX_HEIGHT_INIT, 0.0,
                                          scene, solver, olat, olon)
            tr_pw_ref = run_sionna_batch(tr_eval[LAT_COL].tolist(), tr_eval[LON_COL].tolist(),
                                          ref_lat, ref_lon, h_opt, az_opt,
                                          scene, solver, olat, olon)
            va_pw_ref = run_sionna_batch(va[LAT_COL].tolist(), va[LON_COL].tolist(),
                                          ref_lat, ref_lon, h_opt, az_opt,
                                          scene, solver, olat, olon)
            print(" done", flush=True)

            tr_rsrp = tr_eval[RSRP_COL].values
            va_rsrp = va[RSRP_COL].values

            wcl_alpha, wcl_ic, wcl_val_mae_train_fit = fit_ols(tr_pw_wcl, tr_rsrp)
            ref_alpha, ref_ic, ref_val_mae_train_fit = fit_ols(tr_pw_ref, tr_rsrp)

            def apply_cal(pows, alpha, ic):
                pred = ic + alpha * pows
                pred[pows <= SENTINEL] = np.nan
                return pred

            va_pred_wcl = apply_cal(va_pw_wcl, wcl_alpha, wcl_ic)
            va_pred_ref = apply_cal(va_pw_ref, ref_alpha, ref_ic)

            va_mask_wcl = va_pw_wcl > SENTINEL
            va_mask_ref = va_pw_ref > SENTINEL
            wcl_val_mae = (float(np.abs(va_rsrp[va_mask_wcl] - va_pred_wcl[va_mask_wcl]).mean())
                            if va_mask_wcl.sum() >= MIN_ROWS else float("nan"))
            ref_val_mae = (float(np.abs(va_rsrp[va_mask_ref] - va_pred_ref[va_mask_ref]).mean())
                            if va_mask_ref.sum() >= MIN_ROWS else float("nan"))
            wcl_rho = (float(spearmanr(va_pw_wcl[va_mask_wcl], va_rsrp[va_mask_wcl])[0])
                       if va_mask_wcl.sum() >= MIN_ROWS else 0.0)
            ref_rho = (float(spearmanr(va_pw_ref[va_mask_ref], va_rsrp[va_mask_ref])[0])
                       if va_mask_ref.sum() >= MIN_ROWS else 0.0)
            gain = wcl_val_mae - ref_val_mae

            print(f"    val MAE: WCL={wcl_val_mae:.3f} dB  Refined={ref_val_mae:.3f} dB  "
                  f"gain={gain:+.3f} dB  rho: {wcl_rho:.3f}->{ref_rho:.3f}  "
                  f"[tower took {time.time()-t_tower_start:.0f}s]")

            rec = {
                "cell_id": cell, "n_train": int(len(tr)), "n_train_excluded_zone": int(
                    excluded_rows[excluded_rows[CELL_COL] == cell].shape[0]
                    if APPLY_ZONE_EXCLUSION and n_excluded > 0 else 0),
                "n_val": int(len(va)),
                "wcl_lat": wcl_lat, "wcl_lon": wcl_lon,
                "refined_lat": ref_lat, "refined_lon": ref_lon,
                "refined_height_m": h_opt, "refined_azimuth_deg": az_opt,
                "delta_m": delta_m, "dx_m": float(dx_opt), "dy_m": float(dy_opt),
                "scatter_s": SCATTER_S, "tower_freq_mhz": tower_freq_mhz,
                "n_nm_evals": eval_count[0],
                "wcl_opt_mae": wcl_mae_opt, "refined_opt_mae": float(result.fun),
                "wcl_val_mae": wcl_val_mae, "refined_val_mae": ref_val_mae,
                "val_mae_gain": gain,
                "wcl_spearman": wcl_rho, "refined_spearman": ref_rho,
                "wcl_alpha": wcl_alpha, "refined_alpha": ref_alpha,
                "wcl_intercept": wcl_ic, "refined_intercept": ref_ic,
            }
            rec_df = pd.DataFrame([rec])
            rec_df.to_csv(ckpt_path, mode="a", header=not ckpt_path.exists(), index=False)
            done_cells.add(cell)

            # ── Per-row val predictions (refined geometry only) ───────────────
            dist_typeb = (haversine_m(va[LAT_COL], va[LON_COL],
                                       TYPEB_CENTROID_LAT, TYPEB_CENTROID_LON)
                          if OPERATOR == 2 else np.full(len(va), np.nan))
            vp = pd.DataFrame({
                "_row": va["_row"].values, "cell_id": cell, "device": DEVICE,
                "operator": OPERATOR, LAT_COL: va[LAT_COL].values, LON_COL: va[LON_COL].values,
                "measured_rsrp": va_rsrp, "sionna_power_raw": va_pw_ref,
                "sionna_power_cal": va_pred_ref, "dist_to_typeb_m": dist_typeb,
                "tower_freq_mhz": tower_freq_mhz,
            })
            vp.to_csv(valpred_path, mode="a", header=valpred_write_hdr, index=False)
            valpred_write_hdr = False

        except Exception as e:
            print(f"\n  Tower {int(cell)}: ERROR - {e}  (skipping)", flush=True)
            import traceback
            traceback.print_exc()

        # ── Release accumulated JIT/GPU memory ────────────────────────────────
        # Mitsuba/Dr.Jit compile a new kernel variant for every distinct batch
        # shape it sees; across ~100+ towers with wildly different row counts
        # (70 to 2000+), that cache grows without bound and eventually
        # exhausts memory. Flush it after every tower, not just at the end.
        gc.collect()
        dr.flush_malloc_cache()
        dr.flush_kernel_cache()

    # ── Aggregate ─────────────────────────────────────────────────────────────
    if not ckpt_path.exists():
        print("\nNo towers completed — nothing to aggregate.")
        return

    all_results = pd.read_csv(ckpt_path)
    nv = all_results["n_val"].values
    wcl_w = float(np.average(all_results["wcl_val_mae"], weights=nv))
    ref_w = float(np.average(all_results["refined_val_mae"], weights=nv))
    imp = int((all_results["val_mae_gain"] > 0).sum())

    print(f"\n{'='*70}")
    print(f"FINAL RESULTS — {DEVICE} (Operator {OPERATOR})  |  {len(all_results)} towers")
    print(f"{'='*70}")
    print(f"  WCL val MAE (weighted)     : {wcl_w:.3f} dB")
    print(f"  Refined val MAE (weighted) : {ref_w:.3f} dB")
    print(f"  Gain                       : {wcl_w - ref_w:+.3f} dB")
    print(f"  Towers improved            : {imp}/{len(all_results)}")
    print(f"  Total Sionna calls         : {_call_counter[0]:,}")
    print(f"  Total Sionna time          : {_call_time_total[0]:.0f}s "
          f"({_call_time_total[0]/max(_call_counter[0],1):.2f}s/call avg)")

    summary = {
        "device": DEVICE, "operator": OPERATOR, "experiment": "A19_gate2_final",
        "dry_run": DRY_RUN, "full_mode": True, "scatter_s": SCATTER_S,
        "zone_exclusion_applied": APPLY_ZONE_EXCLUSION,
        "zone_exclude_radius_m": ZONE_EXCLUDE_RADIUS_M if APPLY_ZONE_EXCLUSION else None,
        "n_training_rows_excluded": int(n_excluded),
        "n_towers": int(len(all_results)),
        "wcl_val_mae_weighted": wcl_w, "refined_val_mae_weighted": ref_w,
        "gain_db": float(wcl_w - ref_w), "n_improved": imp,
        "total_sionna_calls": _call_counter[0],
        "total_sionna_time_s": _call_time_total[0],
        "avg_sionna_call_time_s": _call_time_total[0] / max(_call_counter[0], 1),
    }
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved: {ckpt_path.name}  {summary_path.name}  {valpred_path.name}")


if __name__ == "__main__":
    main()
