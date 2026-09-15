"""
A17_dynamic_rt.py  --  Dynamic Ray Tracing with Companion Vehicle Blockers
===========================================================================
For each pc1 measurement row on the validation day, places the companion
device (pc4) as a vehicle-shaped mesh in the Sionna RT scene at its
GPS-synchronised position, then traces paths and classifies them as LOS/NLOS.

Differences from A07/A08 (static scenes):
  - Vehicle blocker geometry changes per time-window
  - Paths traced twice: full (depth-5 + diffraction) and LOS-only (depth-0)
  - LOS/NLOS classification derived from LOS-path power floor
  - Metrics: RSRP MAE, RSRP RMSE, Bias, SNR MAE, LOS-MAE, NLOS-MAE

Strategy to keep scene reloads manageable:
  - Rows grouped by (cell_eci, pc4_25m_cell)
  - One scene load per group; all RX in the group are batched per PathSolver call
  - Typical: ~150-300 groups for pc1+op1+val → ~30-60 min total

SNR definition:
  SNR_dB = RSRP_dBm - NoisePower_dBm
  NoisePower = kT + 10*log10(BW_Hz) + NF_dB
             = -174 + 70 + 7 = -97 dBm  (LTE 10 MHz, 7 dB NF)

Outputs (twingate/out/dynamic_rt/):
  per_row_predictions.csv   per-row RSRP sim + measured + LOS flag
  summary_metrics.json      aggregate metrics (all / LOS / NLOS)
  static_vs_dynamic.csv     per-tower MAE comparison (static scene vs dynamic)
"""

import os, math, json, shutil, warnings, tempfile
import xml.etree.ElementTree as ET
import numpy as np
import pandas as pd
from pathlib import Path

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
warnings.filterwarnings('ignore')

import mitsuba as mi
mi.set_variant('cuda_ad_mono_polarized')
import drjit as dr
from sionna.rt import load_scene, Transmitter, Receiver, PlanarArray, PathSolver

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT     = Path(__file__).parent.parent
TWINGATE = Path(__file__).parent
OUT      = TWINGATE / "out"
DRT_OUT  = OUT / "dynamic_rt"
DRT_OUT.mkdir(parents=True, exist_ok=True)

DATAFILE       = ROOT / "cellular_dataframe_cleaned.csv"
GAP_LABELS     = OUT / "gap_labels.csv"
SPLIT_IDX      = OUT / "split_index.csv"
REFINED_POS    = OUT / "refined_positions.csv"
SCENE_XML_BASE = ROOT / "scene_operator1" / "scene.xml"
SCENE_ORIGIN   = (52.507005, 13.323428)

# ── Constants ─────────────────────────────────────────────────────────────────
OPERATOR       = 1
TARGET_DEVICE  = "pc1"
COMPANION      = "pc4"

TX_H           = 30.0       # metres (from A07 / A08 refined pipeline)
RX_H           = 1.5
EVAL_BATCH     = 30         # receivers per PathSolver call

VEH_HALF_X     = 2.25       # half car length  (total 4.5 m)
VEH_HALF_Y     = 1.00       # half car width   (total 2.0 m)
VEH_HALF_Z     = 0.75       # half car height  (total 1.5 m)
VEH_MAT_ID     = "itu_concrete"   # best available metal proxy in scene

VEH_QUANT_M    = 25.0       # quantise companion position to 25 m grid for batching
MAX_TOWERS     = None        # None = all towers present in pc1 val rows

# SNR parameters (LTE 10 MHz, 7 dB NF, 290 K)
NOISE_DBM      = -97.0

RSRP_COL   = "PCell_RSRP_max"
SNR_COL    = "PCell_SNR_1"   # measured SINR from cellular_df (dB)
TS_COL     = "ts_gps"
LAT_COL    = "Latitude"
LON_COL    = "Longitude"
CELL_COL   = "PCell_Cell_Identity"   # real cell ECI from cellular_dataframe

# ── Helpers ───────────────────────────────────────────────────────────────────
def ll2xy(lat, lon, orig_lat=SCENE_ORIGIN[0], orig_lon=SCENE_ORIGIN[1]):
    x = (lon - orig_lon) * 111_320.0 * math.cos(math.radians(orig_lat))
    y = (lat - orig_lat) * 111_320.0
    return float(x), float(y)


def power_dbm(paths):
    """Convert Sionna Paths object → dBm array, shape (n_rx,)."""
    try:
        a_r = np.array(dr.detach(paths.a[0]))
        a_i = np.array(dr.detach(paths.a[1]))
        plin = (a_r ** 2 + a_i ** 2).sum(axis=-1).squeeze(axis=(1, 2, 3))
        return 10.0 * np.log10(np.maximum(plin, 1e-30)) + 30.0
    except Exception:
        return np.full(1, -150.0)


def has_los(paths):
    """True if any path has non-negligible power (used for LOS-only solver run)."""
    p = power_dbm(paths)
    return bool(p.max() > -130.0)


def calibrated_mae(measured, simulated):
    offset = float(np.mean(measured - simulated))
    calibrated = simulated + offset
    return float(np.mean(np.abs(measured - calibrated))), float(offset)


def rmse(measured, simulated):
    offset = float(np.mean(measured - simulated))
    return float(np.sqrt(np.mean((measured - (simulated + offset)) ** 2)))


def bias(measured, simulated):
    return float(np.mean(measured - simulated))


def snr_mae_thermal(rsrp_meas, rsrp_sim):
    """SNR MAE using thermal noise floor (no interference modelled)."""
    snr_meas = rsrp_meas - NOISE_DBM
    snr_sim  = rsrp_sim  - NOISE_DBM
    offset   = float(np.mean(snr_meas - snr_sim))
    return float(np.mean(np.abs(snr_meas - (snr_sim + offset))))


def snr_mae_measured(snr_meas_arr, rsrp_sim):
    """SNR MAE vs actual measured SINR from drive-test logs."""
    valid = ~np.isnan(snr_meas_arr)
    if valid.sum() < 5:
        return None
    snr_sim = rsrp_sim[valid] - NOISE_DBM
    snr_m   = snr_meas_arr[valid]
    offset  = float(np.mean(snr_m - snr_sim))
    return float(np.mean(np.abs(snr_m - (snr_sim + offset))))


def quant(v, q=VEH_QUANT_M):
    return float(int(v / q) * q)


# ── Scene XML modification: inject vehicle blocker ────────────────────────────
def write_scene_with_vehicle(veh_x, veh_y, tmp_dir):
    """Write a modified scene XML with a vehicle cube at (veh_x, veh_y, VEH_HALF_Z)."""
    ET.register_namespace('', '')
    tree = ET.parse(SCENE_XML_BASE)
    root = tree.getroot()

    sh = ET.SubElement(root, 'shape')
    sh.set('type', 'cube')
    sh.set('id', 'vehicle_dynamic')

    tf = ET.SubElement(sh, 'transform')
    tf.set('name', 'to_world')

    sc = ET.SubElement(tf, 'scale')
    sc.set('x', f'{VEH_HALF_X:.3f}')
    sc.set('y', f'{VEH_HALF_Y:.3f}')
    sc.set('z', f'{VEH_HALF_Z:.3f}')

    tr = ET.SubElement(tf, 'translate')
    tr.set('x', f'{veh_x:.3f}')
    tr.set('y', f'{veh_y:.3f}')
    tr.set('z', f'{VEH_HALF_Z:.3f}')

    ref = ET.SubElement(sh, 'ref')
    ref.set('id', VEH_MAT_ID)

    tmp_path = os.path.join(tmp_dir, 'scene_dyn.xml')
    tree.write(tmp_path, xml_declaration=True, encoding='unicode')
    return tmp_path


# ── PathSolver forward pass ───────────────────────────────────────────────────
def forward_batch(tx_x, tx_y, rx_lats, rx_lons, scene, solver,
                  max_depth=5, diffraction=True):
    """Trace paths for a batch of receivers. Returns (rsrp_array, los_bool_array)."""
    scene.add(Transmitter(name="tx_drt", position=[tx_x, tx_y, TX_H]))
    rsrp_full = []
    rsrp_los  = []

    for start in range(0, len(rx_lats), EVAL_BATCH):
        blats = rx_lats[start:start + EVAL_BATCH]
        blons = rx_lons[start:start + EVAL_BATCH]
        for i, (la, lo) in enumerate(zip(blats, blons)):
            xi, yi = ll2xy(float(la), float(lo))
            scene.add(Receiver(name=f"rx_drt{i}", position=[xi, yi, RX_H]))

        # Full paths
        paths_full = solver(scene=scene, max_depth=max_depth, diffraction=diffraction)
        rsrp_full.extend(power_dbm(paths_full).tolist())

        # LOS-only paths (depth=0 → direct ray only)
        paths_los = solver(scene=scene, max_depth=0, diffraction=False)
        los_pwr = power_dbm(paths_los)
        rsrp_los.extend(los_pwr.tolist())

        for i in range(len(blats)):
            scene.remove(f"rx_drt{i}")

    scene.remove("tx_drt")
    rsrp_full  = np.array(rsrp_full)
    los_flags  = np.array(rsrp_los) > -130.0   # LOS if direct path detected
    return rsrp_full, los_flags


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("A17  Dynamic Ray Tracing  (pc1 / Op1 / val day)")
    print("=" * 70)

    # Load split index
    split = pd.read_csv(SPLIT_IDX)
    split[TS_COL] = pd.to_datetime(split[TS_COL])
    val_ts = set(split[split.split == 'val'][TS_COL].astype(str))

    # Load cellular dataframe — get cell ECI + measured SNR + GPS per row
    print("Loading cellular dataframe...")
    cdf = pd.read_csv(
        DATAFILE,
        usecols=['device', TS_COL, LAT_COL, LON_COL, RSRP_COL, SNR_COL,
                 CELL_COL, 'operator']
    )
    cdf[TS_COL] = pd.to_datetime(cdf[TS_COL], errors='coerce')
    cdf = cdf.dropna(subset=[TS_COL, LAT_COL, LON_COL, RSRP_COL, CELL_COL])
    cdf[CELL_COL] = cdf[CELL_COL].astype(int)
    print(f"Cellular rows loaded: {len(cdf)}")

    refined = pd.read_csv(REFINED_POS) if REFINED_POS.exists() else pd.DataFrame()
    tower_pos = pd.read_csv(OUT / "tower_positions.csv") if (OUT / "tower_positions.csv").exists() else pd.DataFrame()
    print(f"Refined positions: {len(refined)}  |  Tower WCL positions: {len(tower_pos)}")

    # Filter pc1 + op1 + val rows
    pc1 = cdf[
        (cdf.device == TARGET_DEVICE) &
        (cdf.operator == OPERATOR) &
        (cdf[TS_COL].astype(str).isin(val_ts))
    ].copy()
    print(f"pc1 / Op1 / val rows: {len(pc1)}")

    # Companion vehicle GPS positions (for blocker placement)
    pc4 = cdf[cdf.device == COMPANION][[TS_COL, LAT_COL, LON_COL]].copy()
    pc4.columns = [TS_COL, 'veh_lat', 'veh_lon']

    merged = pc1.merge(pc4, on=TS_COL, how='inner')
    print(f"Rows with {COMPANION} sync: {len(merged)}")

    # Convert vehicle lat/lon to ENU
    merged['veh_x'], merged['veh_y'] = zip(*[
        ll2xy(la, lo) for la, lo in zip(merged.veh_lat, merged.veh_lon)
    ])
    # Quantise companion position for grouping
    merged['vq_x'] = merged['veh_x'].apply(lambda v: quant(v))
    merged['vq_y'] = merged['veh_y'].apply(lambda v: quant(v))

    # Tower list
    cell_ids = merged[CELL_COL].unique()
    if MAX_TOWERS is not None:
        cell_ids = cell_ids[:MAX_TOWERS]
    print(f"Towers to process: {len(cell_ids)}")

    # Setup Sionna objects (reused across scenes)
    array = PlanarArray(num_rows=1, num_cols=1,
                        vertical_spacing=0.5, horizontal_spacing=0.5,
                        pattern="iso", polarization="V")

    all_rows   = []    # per-row results
    tower_mets = []    # per-tower metrics for static vs dynamic comparison
    tmp_dir    = tempfile.mkdtemp(prefix="drt_")

    try:
        for t_idx, cell_id in enumerate(cell_ids):
            tower_rows = merged[merged[CELL_COL] == cell_id].copy()
            print(f"\n[{t_idx+1}/{len(cell_ids)}] cell={cell_id}  rows={len(tower_rows)}")

            # Get TX position: prefer refined, fall back to WCL/OCID
            ref_row = pd.DataFrame()
            if not refined.empty and 'cell_eci' in refined.columns:
                ref_row = refined[
                    (refined.operator == OPERATOR) &
                    (refined.cell_eci == int(cell_id))
                ]

            if not ref_row.empty:
                r = ref_row.iloc[0]
                tx_x, tx_y = ll2xy(float(r['refined_lat']), float(r['refined_lon']))
                print(f"  TX refined Gate-2: ({tx_x:.0f}, {tx_y:.0f})")
            elif not tower_pos.empty and 'PCell_Cell_Identity' in tower_pos.columns:
                tp_row = tower_pos[
                    (tower_pos.operator == OPERATOR) &
                    (tower_pos.PCell_Cell_Identity == int(cell_id))
                ]
                if not tp_row.empty:
                    t = tp_row.iloc[0]
                    tx_x, tx_y = ll2xy(float(t['tower_lat']), float(t['tower_lon']))
                    print(f"  TX from WCL/OCID: ({tx_x:.0f}, {tx_y:.0f})")
                else:
                    print(f"  No TX position for cell {cell_id}, skipping")
                    continue
            else:
                print(f"  No position data for cell {cell_id}, skipping")
                continue

            # Group by quantised companion vehicle position
            groups = tower_rows.groupby(['vq_x', 'vq_y'])
            print(f"  Vehicle position groups: {groups.ngroups}")

            tower_preds = []
            for (vqx, vqy), grp in groups:
                veh_x = float(vqx + VEH_QUANT_M / 2)
                veh_y = float(vqy + VEH_QUANT_M / 2)

                try:
                    xml_path = write_scene_with_vehicle(veh_x, veh_y, tmp_dir)
                    scene = load_scene(xml_path)
                    scene.tx_array = array
                    scene.rx_array = array
                    solver = PathSolver()

                    rx_lats = grp[LAT_COL].values
                    rx_lons = grp[LON_COL].values
                    meas    = grp[RSRP_COL].values

                    rsrp_sim, los_flags = forward_batch(
                        tx_x, tx_y, rx_lats, rx_lons, scene, solver
                    )

                    for i, (row_idx, row) in enumerate(grp.iterrows()):
                        snr_meas = float(row[SNR_COL]) if pd.notna(row.get(SNR_COL)) else None
                        tower_preds.append({
                            'ts_gps':      str(row[TS_COL]),
                            'cell_id':     cell_id,
                            'lat':         row[LAT_COL],
                            'lon':         row[LON_COL],
                            'rsrp_meas':   float(row[RSRP_COL]),
                            'rsrp_sim':    float(rsrp_sim[i]),
                            'snr_meas_db': snr_meas,
                            'snr_thermal_sim': float(rsrp_sim[i]) - NOISE_DBM,
                            'is_los':      bool(los_flags[i]),
                            'veh_x':       float(row.veh_x),
                            'veh_y':       float(row.veh_y),
                        })

                    del scene, solver

                except Exception as e:
                    print(f"  Group ({vqx:.0f},{vqy:.0f}) failed: {e}")
                    continue

            if not tower_preds:
                continue

            # Per-tower metrics
            df_t = pd.DataFrame(tower_preds)
            meas_all = df_t.rsrp_meas.values
            sim_all  = df_t.rsrp_sim.values

            mae_val, offset = calibrated_mae(meas_all, sim_all)
            df_t['rsrp_cal'] = df_t.rsrp_sim + offset

            los_mask  = df_t.is_los.values
            nlos_mask = ~los_mask
            snr_meas_arr = df_t.snr_meas_db.values.astype(float)

            metrics = {
                'cell_id':            int(cell_id),
                'n_rows':             len(df_t),
                'n_los':              int(los_mask.sum()),
                'n_nlos':             int(nlos_mask.sum()),
                'los_fraction':       float(los_mask.mean()),
                'rsrp_mae':           mae_val,
                'rsrp_rmse':          rmse(meas_all, sim_all),
                'rsrp_bias':          bias(meas_all, sim_all),
                'snr_mae_thermal':    snr_mae_thermal(meas_all, sim_all),
                'snr_mae_measured':   snr_mae_measured(snr_meas_arr, sim_all),
                'rsrp_mae_los':       calibrated_mae(meas_all[los_mask],  sim_all[los_mask])[0]  if los_mask.sum()  > 5 else None,
                'rsrp_mae_nlos':      calibrated_mae(meas_all[nlos_mask], sim_all[nlos_mask])[0] if nlos_mask.sum() > 5 else None,
            }
            tower_mets.append(metrics)
            all_rows.extend(tower_preds)

            print(f"  MAE={mae_val:.2f}dB  RMSE={metrics['rsrp_rmse']:.2f}dB  "
                  f"bias={metrics['rsrp_bias']:+.2f}dB  "
                  f"LOS={metrics['los_fraction']*100:.0f}%  "
                  f"SNR_MAE(measured)={metrics['snr_mae_measured']}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if not all_rows:
        print("\nNo results — check data / Sionna setup.")
        return

    # ── Save outputs ──────────────────────────────────────────────────────────
    df_rows = pd.DataFrame(all_rows)
    df_rows.to_csv(DRT_OUT / "per_row_predictions.csv", index=False)
    print(f"\nSaved: {DRT_OUT}/per_row_predictions.csv  ({len(df_rows)} rows)")

    df_tower = pd.DataFrame(tower_mets)
    df_tower.to_csv(DRT_OUT / "per_tower_metrics.csv", index=False)
    print(f"Saved: {DRT_OUT}/per_tower_metrics.csv")

    # Aggregate summary
    meas_all = df_rows.rsrp_meas.values
    sim_all  = df_rows.rsrp_sim.values
    los_mask = df_rows.is_los.values

    mae_all, _ = calibrated_mae(meas_all, sim_all)
    snr_meas_all = df_rows.snr_meas_db.values.astype(float)
    summary = {
        'total_rows':           len(df_rows),
        'towers':               len(df_tower),
        'los_fraction':         float(los_mask.mean()),
        'rsrp_mae_all':         mae_all,
        'rsrp_rmse_all':        rmse(meas_all, sim_all),
        'rsrp_bias_all':        bias(meas_all, sim_all),
        'snr_mae_thermal':      snr_mae_thermal(meas_all, sim_all),
        'snr_mae_vs_measured':  snr_mae_measured(snr_meas_all, sim_all),
        'rsrp_mae_los':         calibrated_mae(meas_all[los_mask],  sim_all[los_mask])[0]  if los_mask.sum()  > 5 else None,
        'rsrp_mae_nlos':        calibrated_mae(meas_all[~los_mask], sim_all[~los_mask])[0] if (~los_mask).sum() > 5 else None,
        'noise_floor_dbm':      NOISE_DBM,
        'snr_note':             'snr_mae_vs_measured uses PCell_SNR_1 from drive-test logs (SINR, includes interference)',
    }
    with open(DRT_OUT / "summary_metrics.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(f"Saved: {DRT_OUT}/summary_metrics.json")

    # Static vs dynamic comparison (load A07/A16 gate2_results if available)
    gate2 = OUT / "gate2_results.json"
    if gate2.exists():
        with open(gate2) as f:
            static_res = json.load(f)
        comparison = {
            'static_mae_op1':  static_res.get('op1_mae') or static_res.get('mae_op1'),
            'dynamic_mae_all': mae_all,
            'dynamic_los_fraction': float(los_mask.mean()),
            'note': 'dynamic includes companion vehicle blocker; static uses building-only scene',
        }
        with open(DRT_OUT / "static_vs_dynamic.json", "w") as f:
            json.dump(comparison, f, indent=2)
        print(f"Saved: {DRT_OUT}/static_vs_dynamic.json")

    print("\n" + "=" * 70)
    print("SUMMARY")
    print(f"  Total rows:      {summary['total_rows']}")
    print(f"  LOS fraction:    {summary['los_fraction']*100:.1f}%")
    print(f"  RSRP MAE (all):  {summary['rsrp_mae_all']:.3f} dB")
    print(f"  RSRP MAE (LOS):         {summary['rsrp_mae_los']}")
    print(f"  RSRP MAE (NLOS):        {summary['rsrp_mae_nlos']}")
    print(f"  RSRP RMSE:              {summary['rsrp_rmse_all']:.3f} dB")
    print(f"  RSRP Bias:              {summary['rsrp_bias_all']:+.3f} dB")
    print(f"  SNR MAE (thermal):      {summary['snr_mae_thermal']:.3f} dB  (noise floor={NOISE_DBM} dBm)")
    print(f"  SNR MAE (vs measured):  {summary['snr_mae_vs_measured']}  (vs PCell_SNR_1 SINR)")
    print("=" * 70)


if __name__ == "__main__":
    main()
