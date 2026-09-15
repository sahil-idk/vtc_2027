"""
A15_tx_position_refinement.py — TX Position Refinement via Sionna RT + Nelder-Mead

Fixes the core Gate-2 flaw: WCL gives a rough TX position (100-700m error).
Instead of accepting that error, we jointly optimize the TX position using
training data in a closed loop:

  WCL (initial guess)
     → Nelder-Mead outer loop: vary TX (Δx, Δy) in metres from WCL
         → Sionna RT with candidate TX position → sionna_power per train row
         → OLS fit on ALL train rows: RSRP = b + α·sionna_power
         → Train MAE (objective — val rows NEVER touched)
     → converge to refined TX position
  → Final Sionna + OLS on ALL train+val rows with refined position
  → Report val MAE

ML component : OLS (data-driven calibration)
Physics component: Sionna RT (geometry-aware propagation)
Optimization: Nelder-Mead (gradient-free, handles RT discontinuities)

Usage: python A15_tx_position_refinement.py [--full] [--device pc1|pc2|pc3|pc4]
  --full        : use ALL training rows during Nelder-Mead (slower but more accurate)
  --device <d>  : device to process (default: pc1)
  default: subsample N_OPT_ROWS during search, full rows for final eval

Split: TEMPORAL — Days 1-2 (June 22-23) = train, Day 3 (June 24) = val.
Matches the paper's held-out day claim and Gate-1 completeness evaluation.
"""

import sys
import json
import math
import numpy as np
import pandas as pd
from pathlib import Path
from scipy.optimize import minimize
from scipy.stats import linregress, spearmanr

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import Transmitter, Receiver, PathSolver, PlanarArray, load_scene

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "out"
OUT.mkdir(exist_ok=True)

FULL_MODE = "--full" in sys.argv

# --device argument
_dev_arg = next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "--device" and i+1 < len(sys.argv)), "pc1")

# ── Constants ────────────────────────────────────────────────────────────────
DEVICE = _dev_arg

# pc1/pc4 → Operator 1;  pc2/pc3 → Operator 2
_OP2_DEVICES = {"pc2", "pc3"}
OPERATOR     = 2 if DEVICE in _OP2_DEVICES else 1
SCENE_ORIGIN = (52.506112, 13.321908) if OPERATOR == 2 else (52.507005, 13.323428)
SCENE_XML    = str(ROOT / f"scene_operator{OPERATOR}" / "scene.xml")

RSRP_COL = "PCell_RSRP_max"
FREQ_COL = "PCell_freq_MHz"
CELL_COL = "PCell_Cell_Identity"
LAT_COL  = "Latitude"
LON_COL  = "Longitude"

TX_HEIGHT_M    = 30.0
RX_HEIGHT_M    = 1.5
GPU_BATCH      = 40
MIN_ROWS       = 5         # minimum train+val rows to attempt refinement
ALPHA_CLIP     = (0.0, 2.0)
SENTINEL       = -100.0    # exclude no-path-found rows
MIN_SIONNA_STD = 1.0       # fallback to tower mean if Sionna flat
N_OPT_ROWS     = 40        # rows used during Nelder-Mead (1 GPU batch)
MAX_EVAL_TRAIN = 300       # cap training rows used to fit final OLS (val still uses ALL val rows)
SEARCH_RADIUS  = 500.0     # metres — max TX displacement from WCL
MAXITER        = 60        # Nelder-Mead iterations

if FULL_MODE:
    N_OPT_ROWS = None
    MAX_EVAL_TRAIN = None
    print("FULL MODE: all training rows used during optimization and final OLS fit")
else:
    print(f"FAST MODE: {N_OPT_ROWS} NM rows, {MAX_EVAL_TRAIN} final OLS rows, {MAXITER} NM iters")


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
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))

def power_dbm(paths):
    a_r = np.array(dr.detach(paths.a[0]))
    a_i = np.array(dr.detach(paths.a[1]))
    plin = (a_r ** 2 + a_i ** 2).sum(axis=-1).squeeze(axis=(1, 2, 3))
    return 10.0 * np.log10(np.maximum(plin, 1e-30)) + 30.0


# ── Sionna batch runner ───────────────────────────────────────────────────────
_call_counter = [0]

def run_sionna_batch(rx_lats, rx_lons, tx_lat, tx_lon,
                     scene, solver, olat, olon, tag="a15"):
    tx_x, tx_y = latlon_to_xy(tx_lat, tx_lon, olat, olon)
    name = f"tx_{tag}"
    scene.add(Transmitter(name=name, position=[tx_x, tx_y, TX_HEIGHT_M]))
    powers = []
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
    scene.remove(name)
    _call_counter[0] += 1
    return np.array(powers)


def fit_ols_mae(sionna_powers, measured_rsrp):
    """Fit OLS and return train MAE. Returns large value if Sionna is flat."""
    x, y = sionna_powers, measured_rsrp
    valid = x > SENTINEL
    x, y = x[valid], y[valid]
    if len(x) < MIN_ROWS or x.std() < MIN_SIONNA_STD:
        return float(np.abs(y - y.mean()).mean()) if len(y) > 0 else 1e6
    sl, ic, _, _, _ = linregress(x, y)
    alpha = float(np.clip(sl, *ALPHA_CLIP))
    pred  = ic + alpha * x
    return float(np.abs(y - pred).mean())


def main():
    # ── Load data ─────────────────────────────────────────────────────────────
    print("=" * 65)
    print(f"A15  —  TX Position Refinement  ({DEVICE}, Nelder-Mead + Sionna RT)")
    print("=" * 65)

    df    = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv", low_memory=False)
    df["_row"] = df.index
    gaps  = pd.read_csv(OUT / "gap_labels.csv")

    # ── Temporal split: Day 3 (June 24) = val, Days 1-2 (June 22-23) = train ──
    df["_date"] = pd.to_datetime(df["ts_gps"], errors="coerce").dt.date
    import datetime
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

    train_all = clean[clean["new_split"] == "train"]
    val_all   = clean[clean["new_split"] == "val"]
    print(f"  {DEVICE} train={len(train_all):,} (Jun 22-23)  val={len(val_all):,} (Jun 24)")

    # WCL tower positions from all training rows
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
    print(f"  {len(wcl)} towers from training rows\n")

    # Load Sionna scene
    print(f"Loading Sionna scene (Op{OPERATOR})...")
    scene  = load_scene(SCENE_XML)
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso', polarization='V')
    solver = PathSolver()
    print("  Scene loaded.\n")

    # Checkpoint
    ckpt_path = OUT / f"{DEVICE}_refinement_results_temporal.csv"
    if ckpt_path.exists():
        done_df = pd.read_csv(ckpt_path)
        done_cells = set(done_df["cell_id"].unique())
        print(f"  Checkpoint: {len(done_cells)} towers already done, resuming...")
    else:
        done_df    = pd.DataFrame()
        done_cells = set()

    tower_records = []

    for _, tower in wcl.iterrows():
        cell   = tower[CELL_COL]
        wcl_lat = tower["wcl_lat"]
        wcl_lon = tower["wcl_lon"]

        if cell in done_cells:
            print(f"  Tower {int(cell)}: already done (checkpoint)")
            continue

        tr = train_all[train_all[CELL_COL] == cell]
        va = val_all[val_all[CELL_COL] == cell]

        if len(tr) < MIN_ROWS or len(va) < MIN_ROWS:
            print(f"  Tower {int(cell)}: SKIP (tr={len(tr)} va={len(va)})")
            continue

        print(f"  Tower {int(cell)}: tr={len(tr):4d} va={len(va):4d}", end="", flush=True)

        try:
            # ── Optimization subset ───────────────────────────────────────────
            if N_OPT_ROWS is not None and len(tr) > N_OPT_ROWS:
                opt_rows = tr.sample(N_OPT_ROWS, random_state=int(cell) % (2**31))
            else:
                opt_rows = tr

            opt_lats = opt_rows[LAT_COL].tolist()
            opt_lons = opt_rows[LON_COL].tolist()
            opt_rsrp = opt_rows[RSRP_COL].values

            # ── WCL baseline (before refinement) ─────────────────────────────
            wcl_powers_opt = run_sionna_batch(opt_lats, opt_lons, wcl_lat, wcl_lon,
                                              scene, solver, olat, olon)
            wcl_mae_opt = fit_ols_mae(wcl_powers_opt, opt_rsrp)

            # ── Nelder-Mead: find (Δx, Δy) in metres that minimises train MAE ─
            eval_count = [0]
            wcl_x0, wcl_y0 = latlon_to_xy(wcl_lat, wcl_lon, olat, olon)

            def objective(delta_xy):
                dx, dy = float(delta_xy[0]), float(delta_xy[1])
                if math.sqrt(dx**2 + dy**2) > SEARCH_RADIUS:
                    return 1e6
                tx_lat, tx_lon = xy_to_latlon(wcl_x0 + dx, wcl_y0 + dy, olat, olon)
                pows = run_sionna_batch(opt_lats, opt_lons, tx_lat, tx_lon,
                                        scene, solver, olat, olon)
                mae  = fit_ols_mae(pows, opt_rsrp)
                eval_count[0] += 1
                return mae

            result = minimize(
                objective,
                x0=[0.0, 0.0],
                method='Nelder-Mead',
                options={
                    'xatol':   10.0,
                    'fatol':   0.02,
                    'maxiter': MAXITER,
                    'initial_simplex': np.array([[0,0],[50,0],[0,50]], dtype=float),
                }
            )

            dx_opt, dy_opt = float(result.x[0]), float(result.x[1])
            refined_mae_opt = float(result.fun)
            n_evals = eval_count[0]

            wcl_x, wcl_y  = latlon_to_xy(wcl_lat, wcl_lon, olat, olon)
            ref_lat, ref_lon = xy_to_latlon(wcl_x + dx_opt, wcl_y + dy_opt, olat, olon)
            delta_m = math.sqrt(dx_opt**2 + dy_opt**2)

            print(f"  → refined Δ={delta_m:.0f}m  "
                  f"opt_mae: {wcl_mae_opt:.3f}→{refined_mae_opt:.3f} dB  "
                  f"({n_evals} evals)", flush=True)

            # ── Full Sionna on train (capped) + ALL val rows, both positions ──
            # Cap training rows for OLS fitting (val rows always run in full for fair eval)
            if MAX_EVAL_TRAIN is not None and len(tr) > MAX_EVAL_TRAIN:
                tr_eval = tr.sample(MAX_EVAL_TRAIN, random_state=int(cell) % (2**31) + 1)
            else:
                tr_eval = tr
            tr_powers_wcl = run_sionna_batch(tr_eval[LAT_COL].tolist(), tr_eval[LON_COL].tolist(),
                                             wcl_lat, wcl_lon, scene, solver, olat, olon)
            va_powers_wcl = run_sionna_batch(va[LAT_COL].tolist(), va[LON_COL].tolist(),
                                             wcl_lat, wcl_lon, scene, solver, olat, olon)
            tr_powers_ref = run_sionna_batch(tr_eval[LAT_COL].tolist(), tr_eval[LON_COL].tolist(),
                                             ref_lat, ref_lon, scene, solver, olat, olon)
            va_powers_ref = run_sionna_batch(va[LAT_COL].tolist(), va[LON_COL].tolist(),
                                             ref_lat, ref_lon, scene, solver, olat, olon)

            def eval_val_mae(tr_pows, va_pows, tr_rsrp, va_rsrp):
                tr_mask = tr_pows > SENTINEL
                va_mask = va_pows > SENTINEL
                x_tr = tr_pows[tr_mask]; y_tr = tr_rsrp[tr_mask]
                x_va = va_pows[va_mask]; y_va = va_rsrp[va_mask]
                if len(x_tr) < MIN_ROWS or len(x_va) < MIN_ROWS or x_tr.std() < MIN_SIONNA_STD:
                    mean_pred = y_tr.mean() if len(y_tr) > 0 else 0
                    return float(np.abs(y_va - mean_pred).mean()), 0.0, mean_pred
                sl, ic, _, _, _ = linregress(x_tr, y_tr)
                alpha = float(np.clip(sl, *ALPHA_CLIP))
                pred  = ic + alpha * x_va
                val_mae = float(np.abs(y_va - pred).mean())
                rho, _  = spearmanr(x_va, y_va)
                return val_mae, float(rho), float(alpha)

            tr_rsrp = tr_eval[RSRP_COL].values
            va_rsrp = va[RSRP_COL].values

            wcl_val_mae, wcl_rho, wcl_alpha = eval_val_mae(tr_powers_wcl, va_powers_wcl,
                                                            tr_rsrp, va_rsrp)
            ref_val_mae, ref_rho, ref_alpha = eval_val_mae(tr_powers_ref, va_powers_ref,
                                                            tr_rsrp, va_rsrp)

            gain = wcl_val_mae - ref_val_mae
            print(f"      val MAE: WCL={wcl_val_mae:.3f} dB  Refined={ref_val_mae:.3f} dB  "
                  f"gain={gain:+.3f} dB  rho: {wcl_rho:.3f}→{ref_rho:.3f}")

            rec = {
                "cell_id":         cell,
                "n_train":         int(len(tr)),
                "n_val":           int(len(va)),
                "wcl_lat":         wcl_lat,
                "wcl_lon":         wcl_lon,
                "refined_lat":     ref_lat,
                "refined_lon":     ref_lon,
                "delta_m":         delta_m,
                "dx_m":            dx_opt,
                "dy_m":            dy_opt,
                "n_nm_evals":      n_evals,
                "wcl_opt_mae":     wcl_mae_opt,
                "refined_opt_mae": refined_mae_opt,
                "wcl_val_mae":     wcl_val_mae,
                "refined_val_mae": ref_val_mae,
                "val_mae_gain":    gain,
                "wcl_spearman":    wcl_rho,
                "refined_spearman": ref_rho,
                "wcl_alpha":       wcl_alpha,
                "refined_alpha":   ref_alpha,
            }
            tower_records.append(rec)

            rec_df = pd.DataFrame([rec])
            write_hdr = not ckpt_path.exists()
            rec_df.to_csv(ckpt_path, mode="a", header=write_hdr, index=False)
            done_cells.add(cell)

        except Exception as e:
            print(f"\n  Tower {int(cell)}: ERROR — {e}  (skipping)", flush=True)

    # ── Aggregate results ────────────────────────────────────────────────────
    all_results = pd.read_csv(ckpt_path)
    print(f"\n{'='*65}")
    print(f"FINAL RESULTS  —  {DEVICE}  |  {len(all_results)} towers")
    print(f"{'='*65}")

    improved  = all_results[all_results["val_mae_gain"] > 0]
    worsened  = all_results[all_results["val_mae_gain"] < 0]
    unchanged = all_results[all_results["val_mae_gain"] == 0]

    # Weighted by n_val
    nv = all_results["n_val"].values
    wcl_weighted = float(np.average(all_results["wcl_val_mae"],  weights=nv))
    ref_weighted = float(np.average(all_results["refined_val_mae"], weights=nv))

    print(f"\n  WCL val MAE (weighted)     : {wcl_weighted:.3f} dB")
    print(f"  Refined val MAE (weighted) : {ref_weighted:.3f} dB")
    print(f"  Overall gain               : {wcl_weighted - ref_weighted:+.3f} dB")
    print(f"\n  Towers improved : {len(improved)}/{len(all_results)}")
    print(f"  Towers worsened : {len(worsened)}/{len(all_results)}")
    print(f"\n  Refinement distance:")
    print(f"    mean={all_results['delta_m'].mean():.0f}m  "
          f"median={all_results['delta_m'].median():.0f}m  "
          f"max={all_results['delta_m'].max():.0f}m")
    print(f"\n  Spearman rho (val): "
          f"WCL median={all_results['wcl_spearman'].median():.3f}  "
          f"Refined median={all_results['refined_spearman'].median():.3f}")

    print(f"\n  Top 10 most-improved towers (by val MAE gain):")
    top = all_results.nlargest(10, "val_mae_gain")[
        ["cell_id", "n_train", "delta_m", "wcl_val_mae", "refined_val_mae", "val_mae_gain"]]
    print(top.to_string(index=False))

    summary = {
        "device": DEVICE, "n_towers": int(len(all_results)),
        "full_mode": FULL_MODE, "n_opt_rows": N_OPT_ROWS,
        "wcl_val_mae_weighted": wcl_weighted,
        "refined_val_mae_weighted": ref_weighted,
        "gain_db": float(wcl_weighted - ref_weighted),
        "n_improved": int(len(improved)),
        "n_worsened": int(len(worsened)),
        "delta_m_mean": float(all_results["delta_m"].mean()),
        "delta_m_median": float(all_results["delta_m"].median()),
        "spearman_wcl_median": float(all_results["wcl_spearman"].median()),
        "spearman_refined_median": float(all_results["refined_spearman"].median()),
    }
    with open(OUT / f"{DEVICE}_refinement_summary_temporal.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSaved: out/{DEVICE}_refinement_results_temporal.csv  out/{DEVICE}_refinement_summary_temporal.json")
    print(f"Total Sionna calls: {_call_counter[0]:,}")


if __name__ == "__main__":
    main()
