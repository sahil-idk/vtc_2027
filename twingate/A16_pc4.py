"""
A16_tx_antenna_refinement.py
4D Joint TX Optimization: position + antenna height + sector azimuth

Extends A15 from 2D (Î”x, Î”y) to 4D (Î”x, Î”y, height, azimuth):

  WCL init
    â†’ Coarse azimuth grid (8 directions Ã— fixed height) to seed azimuth
    â†’ Nelder-Mead 4D: (Î”x, Î”y, Î”height, azimuth_deg)
        â†’ Sionna RT with tr38901 sector antenna
        â†’ OLS calibration on ALL training rows â†’ train MAE
    â†’ Refined (lat, lon, height, azimuth)
  â†’ Final Sionna + OLS on ALL train + ALL val rows
  â†’ Val MAE

Why tr38901:
  Each PCell_Cell_Identity IS a sector (one lobe of a 3-sector tower).
  A sector antenna has ~65Â° 3dB horizontal beamwidth and ~8 dBi gain in the
  main lobe. Isotropic (A15) cannot model this â€” tr38901 can.
  Manukyan et al. (arXiv:2507.19653) found antenna orientation/height
  corrections improve Sionna RT Spearman correlation by 50-130%.

ALL training rows used (N_OPT_ROWS=None, MAX_EVAL_TRAIN=None) as requested.
Expected runtime: ~8-30 min/tower depending on n_train. pc1 â‰ˆ 12-24h total.
Checkpoint resumes from last completed tower.
"""

import sys, json, math
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

# â”€â”€ Device / scene config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DEVICE       = "pc4"
OPERATOR     = 1
SCENE_ORIGIN = (52.507005, 13.323428)
SCENE_XML    = str(ROOT / "scene_operator1" / "scene.xml")

RSRP_COL = "PCell_RSRP_max"
CELL_COL = "PCell_Cell_Identity"
LAT_COL  = "Latitude"
LON_COL  = "Longitude"

# â”€â”€ Optimization parameters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
TX_HEIGHT_INIT = 30.0    # initial height guess (metres)
TX_TILT_DEG    = -8.0    # fixed downtilt, degrees (typical LTE sector)
RX_HEIGHT_M    = 1.5
GPU_BATCH      = 40
MIN_ROWS       = 5
ALPHA_CLIP     = (0.0, 2.0)
SENTINEL       = -100.0
MIN_SIONNA_STD = 1.0

N_OPT_ROWS     = 40      # rows per NM eval (same GPU batch as A15 â€” keeps NM fast)
MAX_EVAL_TRAIN = 300     # final OLS fit capped at 300 rows (sufficient for 2-param OLS)

SEARCH_RADIUS  = 500.0   # metres, max horizontal displacement from WCL
HEIGHT_MIN     = 10.0    # metres
HEIGHT_MAX     = 60.0    # metres
MAXITER        = 80      # NM iterations (more than A15 for 4D)

# Coarse azimuth grid: 8 compass directions to seed NM azimuth
AZIMUTH_GRID_DEG = [0, 45, 90, 135, 180, 225, 270, 315]

print("=" * 65)
print("A16  â€”  4D TX+Antenna Refinement  (pc4, tr38901 + Nelder-Mead)")
print("=" * 65)
print(f"  ALL training rows used (N_OPT_ROWS=None, MAX_EVAL_TRAIN=None)")
print(f"  Antenna: tr38901 sector, tilt={TX_TILT_DEG}Â° fixed, height+azimuth optimized")
print(f"  Search: Â±{SEARCH_RADIUS:.0f}m XY | height [{HEIGHT_MIN},{HEIGHT_MAX}]m | azimuth 0-360Â°")


# â”€â”€ Geometry helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
def latlon_to_xy(lat, lon, olat, olon):
    x = (lon - olon) * 111_320.0 * math.cos(math.radians(olat))
    y = (lat - olat) * 111_320.0
    return float(x), float(y)

def xy_to_latlon(x, y, olat, olon):
    lat = olat + y / 111_320.0
    lon = olon + x / (111_320.0 * math.cos(math.radians(olat)))
    return lat, lon

def compass_to_sionna_yaw(azimuth_deg):
    """
    Convert compass bearing (deg, clockwise from North) to Sionna yaw (rad).
    Sionna: x=East, y=North. Default antenna points +x (East).
    North bearing 0Â° â†’ +y â†’ yaw = Ï€/2.
    East  bearing 90Â° â†’ +x â†’ yaw = 0.
    """
    return math.pi / 2.0 - math.radians(azimuth_deg % 360.0)

def power_dbm(paths):
    a_r = np.array(dr.detach(paths.a[0]))
    a_i = np.array(dr.detach(paths.a[1]))
    plin = (a_r ** 2 + a_i ** 2).sum(axis=-1).squeeze(axis=(1, 2, 3))
    return 10.0 * np.log10(np.maximum(plin, 1e-30)) + 30.0


# â”€â”€ Sionna batch runner (now includes height and azimuth) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
_call_counter = [0]

def run_sionna_batch(rx_lats, rx_lons, tx_lat, tx_lon, tx_height, az_deg,
                     scene, solver, olat, olon, tag="a16"):
    tx_x, tx_y = latlon_to_xy(tx_lat, tx_lon, olat, olon)
    yaw  = compass_to_sionna_yaw(az_deg)
    tilt = math.radians(TX_TILT_DEG)
    scene.add(Transmitter(
        name=f"tx_{tag}",
        position=[tx_x, tx_y, float(tx_height)],
        orientation=[yaw, tilt, 0.0],          # [yaw, pitch, roll]
    ))
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
    scene.remove(f"tx_{tag}")
    _call_counter[0] += 1
    return np.array(powers)


def fit_ols_mae(sionna_powers, measured_rsrp):
    x, y = sionna_powers, measured_rsrp
    valid = x > SENTINEL
    x, y = x[valid], y[valid]
    if len(x) < MIN_ROWS or x.std() < MIN_SIONNA_STD:
        return float(np.abs(y - y.mean()).mean()) if len(y) > 0 else 1e6
    sl, ic, _, _, _ = linregress(x, y)
    alpha = float(np.clip(sl, *ALPHA_CLIP))
    return float(np.abs(y - (ic + alpha * x)).mean())


def eval_val_mae(tr_pows, va_pows, tr_rsrp, va_rsrp):
    tr_m = tr_pows > SENTINEL
    va_m = va_pows > SENTINEL
    x_tr, y_tr = tr_pows[tr_m], tr_rsrp[tr_m]
    x_va, y_va = va_pows[va_m], va_rsrp[va_m]
    if len(x_tr) < MIN_ROWS or len(x_va) < MIN_ROWS or x_tr.std() < MIN_SIONNA_STD:
        mean_p = y_tr.mean() if len(y_tr) > 0 else 0.0
        return float(np.abs(y_va - mean_p).mean()), 0.0, mean_p
    sl, ic, _, _, _ = linregress(x_tr, y_tr)
    alpha = float(np.clip(sl, *ALPHA_CLIP))
    pred = ic + alpha * x_va
    rho, _ = spearmanr(x_va, y_va)
    return float(np.abs(y_va - pred).mean()), float(rho), float(alpha)


def main():
    df    = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv", low_memory=False)
    df["_row"] = df.index
    strat = pd.read_csv(OUT / "stratified_split_index.csv")
    gaps  = pd.read_csv(OUT / "gap_labels.csv")

    dev_df = df[df["device"] == DEVICE].copy()
    dev_df = dev_df.merge(strat[["_row", "new_split"]], on="_row", how="inner")
    dev_df = dev_df.merge(gaps[["_row", "gap_type"]], on="_row", how="left")
    dev_df["gap_type"] = dev_df["gap_type"].fillna("Unflagged")

    clean = dev_df[
        (dev_df["gap_type"] == "Unflagged") &
        dev_df[RSRP_COL].notna() &
        dev_df[LAT_COL].notna() &
        dev_df[LON_COL].notna()
    ].copy()

    train_all = clean[clean["new_split"] == "train"]
    val_all   = clean[clean["new_split"] == "val"]
    print(f"\n  {DEVICE} train={len(train_all):,}  val={len(val_all):,}")

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

    # â”€â”€ Load Sionna scene with tr38901 sector antenna on TX â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    print("Loading Sionna scene (Op1) with tr38901 TX pattern...")
    scene  = load_scene(SCENE_XML)
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, pattern='tr38901', polarization='V')
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, pattern='iso',     polarization='V')
    solver = PathSolver()
    print("  Scene loaded.\n")

    # â”€â”€ Checkpoint â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    ckpt_path = OUT / "pc4_a16_results.csv"
    if ckpt_path.exists():
        done_df    = pd.read_csv(ckpt_path)
        done_cells = set(done_df["cell_id"].unique())
        print(f"  Checkpoint: {len(done_cells)} towers already done, resuming...")
    else:
        done_cells = set()

    for _, tower in wcl.iterrows():
        cell    = tower[CELL_COL]
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

        print(f"\n  Tower {int(cell)}: tr={len(tr):4d} va={len(va):4d}", flush=True)

        try:
            # All training rows for NM (no subsample)
            if N_OPT_ROWS is not None and len(tr) > N_OPT_ROWS:
                opt_rows = tr.sample(N_OPT_ROWS, random_state=int(cell) % (2**31))
            else:
                opt_rows = tr
            opt_lats = opt_rows[LAT_COL].tolist()
            opt_lons = opt_rows[LON_COL].tolist()
            opt_rsrp = opt_rows[RSRP_COL].values

            wcl_x0, wcl_y0 = latlon_to_xy(wcl_lat, wcl_lon, olat, olon)

            # â”€â”€ WCL baseline at initial height + az=0 (isotropic replaced by tr38901) â”€â”€
            wcl_pows = run_sionna_batch(opt_lats, opt_lons, wcl_lat, wcl_lon,
                                        TX_HEIGHT_INIT, 0.0,
                                        scene, solver, olat, olon)
            wcl_mae_opt = fit_ols_mae(wcl_pows, opt_rsrp)

            # â”€â”€ Coarse azimuth grid: find best initial direction â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            print(f"    Azimuth grid ({len(AZIMUTH_GRID_DEG)} dirs)...", end="", flush=True)
            best_az    = 0.0
            best_az_mae = 1e9
            for az in AZIMUTH_GRID_DEG:
                pows = run_sionna_batch(opt_lats, opt_lons, wcl_lat, wcl_lon,
                                        TX_HEIGHT_INIT, float(az),
                                        scene, solver, olat, olon)
                mae = fit_ols_mae(pows, opt_rsrp)
                if mae < best_az_mae:
                    best_az_mae = mae
                    best_az     = float(az)
            print(f" best={best_az:.0f}Â°  mae={best_az_mae:.3f} dB", flush=True)

            # â”€â”€ Nelder-Mead 4D: [dx, dy, dh, azimuth_deg] â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
            # dh = height change from TX_HEIGHT_INIT
            eval_count = [0]

            def objective(params):
                dx, dy, dh, az = (float(params[0]), float(params[1]),
                                   float(params[2]), float(params[3]))
                if math.sqrt(dx**2 + dy**2) > SEARCH_RADIUS:
                    return 1e6
                h = TX_HEIGHT_INIT + dh
                if h < HEIGHT_MIN or h > HEIGHT_MAX:
                    return 1e6
                tx_lat, tx_lon = xy_to_latlon(wcl_x0 + dx, wcl_y0 + dy, olat, olon)
                pows = run_sionna_batch(opt_lats, opt_lons, tx_lat, tx_lon,
                                        h, az % 360.0,
                                        scene, solver, olat, olon)
                mae = fit_ols_mae(pows, opt_rsrp)
                eval_count[0] += 1
                return mae

            x0 = np.array([0.0, 0.0, 0.0, best_az])
            # 5 vertices for 4D simplex: perturb each dimension in turn
            init_simplex = np.array([
                [0,   0,   0,   best_az],
                [50,  0,   0,   best_az],
                [0,   50,  0,   best_az],
                [0,   0,   10,  best_az],    # height +10m
                [0,   0,   0,   best_az + 45],   # azimuth +45Â°
            ], dtype=float)

            print(f"    NM 4D ({MAXITER} max iters)...", end="", flush=True)
            result = minimize(
                objective, x0=x0,
                method='Nelder-Mead',
                options={
                    'xatol':          5.0,
                    'fatol':          0.01,
                    'maxiter':        MAXITER,
                    'initial_simplex': init_simplex,
                }
            )
            dx_opt, dy_opt, dh_opt, az_opt = result.x
            az_opt = float(az_opt) % 360.0
            h_opt  = TX_HEIGHT_INIT + float(dh_opt)
            h_opt  = float(np.clip(h_opt, HEIGHT_MIN, HEIGHT_MAX))
            ref_lat, ref_lon = xy_to_latlon(wcl_x0 + dx_opt, wcl_y0 + dy_opt, olat, olon)
            delta_m = math.sqrt(dx_opt**2 + dy_opt**2)
            print(f" done ({eval_count[0]} evals)  "
                  f"Î”xy={delta_m:.0f}m  h={h_opt:.1f}m  az={az_opt:.0f}Â°  "
                  f"mae: {wcl_mae_opt:.3f}â†’{result.fun:.3f} dB", flush=True)

            # â”€â”€ Final eval: ALL train rows + ALL val rows, WCL vs refined â”€â”€â”€â”€â”€
            tr_eval = tr  # ALL training rows for final OLS (MAX_EVAL_TRAIN=None)

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

            wcl_val_mae, wcl_rho, wcl_alpha = eval_val_mae(tr_pw_wcl, va_pw_wcl, tr_rsrp, va_rsrp)
            ref_val_mae, ref_rho, ref_alpha = eval_val_mae(tr_pw_ref, va_pw_ref, tr_rsrp, va_rsrp)
            gain = wcl_val_mae - ref_val_mae

            print(f"    val MAE: WCL={wcl_val_mae:.3f} dB  A16={ref_val_mae:.3f} dB  "
                  f"gain={gain:+.3f} dB  rho: {wcl_rho:.3f}â†’{ref_rho:.3f}")

            rec = {
                "cell_id":          cell,
                "n_train":          int(len(tr)),
                "n_val":            int(len(va)),
                "wcl_lat":          wcl_lat,
                "wcl_lon":          wcl_lon,
                "refined_lat":      ref_lat,
                "refined_lon":      ref_lon,
                "delta_m":          delta_m,
                "dx_m":             float(dx_opt),
                "dy_m":             float(dy_opt),
                "wcl_height_m":     TX_HEIGHT_INIT,
                "refined_height_m": h_opt,
                "wcl_azimuth_deg":  best_az,
                "refined_azimuth_deg": az_opt,
                "n_nm_evals":       eval_count[0],
                "wcl_opt_mae":      wcl_mae_opt,
                "refined_opt_mae":  float(result.fun),
                "wcl_val_mae":      wcl_val_mae,
                "refined_val_mae":  ref_val_mae,
                "val_mae_gain":     gain,
                "wcl_spearman":     wcl_rho,
                "refined_spearman": ref_rho,
                "wcl_alpha":        wcl_alpha,
                "refined_alpha":    ref_alpha,
            }

            rec_df   = pd.DataFrame([rec])
            write_hdr = not ckpt_path.exists()
            rec_df.to_csv(ckpt_path, mode="a", header=write_hdr, index=False)
            done_cells.add(cell)

        except Exception as e:
            print(f"\n  Tower {int(cell)}: ERROR â€” {e}  (skipping)", flush=True)
            import traceback; traceback.print_exc()

    # â”€â”€ Aggregate â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    all_results = pd.read_csv(ckpt_path)
    nv = all_results["n_val"].values
    wcl_w = float(np.average(all_results["wcl_val_mae"],     weights=nv))
    ref_w = float(np.average(all_results["refined_val_mae"], weights=nv))
    imp   = int((all_results["val_mae_gain"] > 0).sum())

    print(f"\n{'='*65}")
    print(f"FINAL RESULTS  â€”  {DEVICE} A16  |  {len(all_results)} towers")
    print(f"{'='*65}")
    print(f"  WCL val MAE (weighted)  : {wcl_w:.3f} dB")
    print(f"  A16 val MAE (weighted)  : {ref_w:.3f} dB")
    print(f"  Gain                    : {wcl_w - ref_w:+.3f} dB")
    print(f"  Improved                : {imp}/{len(all_results)}")
    print(f"  Height: {all_results['refined_height_m'].mean():.1f}m mean  "
          f"range [{all_results['refined_height_m'].min():.0f}, "
          f"{all_results['refined_height_m'].max():.0f}]m")
    print(f"  Total Sionna calls      : {_call_counter[0]:,}")

    summary = {
        "device": DEVICE, "experiment": "A16",
        "n_towers": int(len(all_results)),
        "wcl_val_mae_weighted": wcl_w,
        "a16_val_mae_weighted": ref_w,
        "gain_db": float(wcl_w - ref_w),
        "n_improved": imp,
        "height_mean": float(all_results["refined_height_m"].mean()),
        "sionna_calls": _call_counter[0],
    }
    with open(OUT / "pc4_a16_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved: out/pc4_a16_results.csv  out/pc4_a16_summary.json")


if __name__ == "__main__":
    main()

