"""
A04_gp_calibration.py — TWINGATE Gate 2, Step 4
Gaussian-Process correction model (Manukyan et al. / NBF PaC style).

Draws from:
  - Manukyan et al., "Bridging the Sim-to-Real Gap in RF Localization with
    Large-Scale Synthetic Pretraining," Information Fusion 2025. GP calibration
    for sim-to-real gap, retargeted from position-error loss to RSRP-error loss.
  - NBF (Lyu et al., arXiv:2508.06956) Pretrain-and-Calibrate: Sionna RT is
    the physics pretrain; GP is the lightweight blackbox correction model.

What this does:
  1. Loads sionna_raw.csv (A03 output).
  2. Per operator, trains a GP on TRAINING rows only:
       features: [sionna_power_raw, log10(dist_m+1), freq_mhz, area_enc]
       target  : measured_rsrp - sionna_power_raw  (residual = correction to learn)
  3. Applies GP posterior mean to val rows → gp_corrected_rsrp.
  4. Evaluates corrected MAE/RMSE vs baseline, stratified by device/area/gap_type/distance.
  5. Saves gp_results.csv and gp_summary.json.

Note: GP uncertainty (posterior std) is also saved — provides point-wise confidence
on reconstructed RSRP, as advocated by Physics-Informed Diffusion Models (2025).
"""

import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import Matern, RBF, WhiteKernel, ConstantKernel
from sklearn.preprocessing import StandardScaler

OUT      = Path(__file__).parent / "out"
SIONNA   = OUT / "sionna_raw.csv"
BASELINE = OUT / "baseline_results.json"

AREA_MAP = {"Park": 0, "Residential": 1, "Avenue": 2,
            "Highway": 3, "Tunnel": 4, "UNKNOWN": 5}
DIST_BINS = [0, 200, 500, np.inf]
DIST_LABS = ["0-200m", "200-500m", "500m+"]


def dist_regime(d):
    for i, (lo, hi) in enumerate(zip(DIST_BINS, DIST_BINS[1:])):
        if lo <= d < hi:
            return DIST_LABS[i]
    return DIST_LABS[-1]


def build_features(df):
    X = np.column_stack([
        df["sionna_power_raw"].values,
        np.log10(df["dist_m"].clip(lower=1).values + 1),
        df["freq_mhz"].fillna(df["freq_mhz"].median()).values,
        df["area"].map(AREA_MAP).fillna(5).values,
    ])
    return X


def eval_metrics(y_true, y_pred, label=""):
    residuals = y_true - y_pred
    mae  = float(np.abs(residuals).mean())
    rmse = float(np.sqrt((residuals ** 2).mean()))
    if label:
        print(f"    {label}: MAE={mae:.3f} dB  RMSE={rmse:.3f} dB  n={len(y_true)}")
    return mae, rmse


def process_operator(op, df_op, baseline_offset):
    print(f"\n{'='*60}")
    print(f"Operator {op} — GP Calibration")
    print(f"{'='*60}")

    train = df_op[df_op["split"] == "train"].copy()
    val   = df_op[df_op["split"] == "val"].copy()

    # TypeA rows excluded from training (architecture principle 1)
    train_fit = train[train["gap_type"] != "TypeA"].copy()
    print(f"  Train rows (fit, excl TypeA): {len(train_fit):,}")
    print(f"  Val rows                    : {len(val):,}")

    if len(train_fit) < 10:
        print("  SKIP: too few training rows for GP.")
        return val, {}

    X_train = build_features(train_fit)
    y_train = (train_fit["measured_rsrp"] - train_fit["sionna_power_raw"]).values

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)

    # Kernel: Matérn (spatial/power correlation) + noise
    kernel = (ConstantKernel(1.0, (1e-3, 1e3))
              * Matern(length_scale=1.0, length_scale_bounds=(1e-2, 1e2), nu=1.5)
              + WhiteKernel(noise_level=1.0, noise_level_bounds=(1e-3, 1e2)))

    gp = GaussianProcessRegressor(kernel=kernel, alpha=0.0,
                                  n_restarts_optimizer=3, normalize_y=True)

    # Subsample if training set too large for GP (O(n³) cost)
    MAX_GP_ROWS = 500
    if len(X_train_s) > MAX_GP_ROWS:
        idx = np.random.RandomState(42).choice(len(X_train_s), MAX_GP_ROWS, replace=False)
        gp.fit(X_train_s[idx], y_train[idx])
        print(f"  GP fitted on {MAX_GP_ROWS} subsampled rows (of {len(X_train_s)})")
    else:
        gp.fit(X_train_s, y_train)
        print(f"  GP fitted on {len(X_train_s)} rows")

    print(f"  Learned kernel: {gp.kernel_}")

    # Predict on val
    X_val = build_features(val)
    X_val_s = scaler.transform(X_val)
    y_pred_corr, y_std = gp.predict(X_val_s, return_std=True)

    val = val.copy()
    val["gp_correction"]   = y_pred_corr
    val["gp_corr_std"]     = y_std
    val["gp_rsrp"]         = val["sionna_power_raw"] + baseline_offset + y_pred_corr
    val["gp_residual"]     = val["measured_rsrp"] - val["gp_rsrp"]
    val["dist_regime"]     = val["dist_m"].apply(dist_regime)

    # Baseline uses sionna_power_cal (already in sionna_raw.csv from A03)
    print(f"\n  Baseline  (Sionna + global offset):")
    baseline_mae, baseline_rmse = eval_metrics(
        val["measured_rsrp"].values, val["sionna_power_cal"].values, "overall")
    print(f"  GP-corrected:")
    gp_mae, gp_rmse = eval_metrics(
        val["measured_rsrp"].values, val["gp_rsrp"].values, "overall")
    print(f"  Improvement: {gp_mae - baseline_mae:+.3f} dB MAE "
          f"({'improvement' if gp_mae < baseline_mae else 'WORSE'})")

    print(f"\n  GP Val MAE by device:")
    dev_stats = {}
    for dev, g in val.groupby("device"):
        m, r = eval_metrics(g["measured_rsrp"].values, g["gp_rsrp"].values, dev)
        dev_stats[dev] = {"mae": m, "rmse": r, "n": int(len(g))}

    print(f"\n  GP Val MAE by distance regime:")
    dist_stats = {}
    for dr, g in val.groupby("dist_regime"):
        m, r = eval_metrics(g["measured_rsrp"].values, g["gp_rsrp"].values, dr)
        dist_stats[dr] = {"mae": m, "rmse": r, "n": int(len(g))}

    print(f"\n  GP Val MAE by gap_type:")
    gap_stats = {}
    for gt, g in val.groupby("gap_type"):
        m, r = eval_metrics(g["measured_rsrp"].values, g["gp_rsrp"].values, gt)
        gap_stats[gt] = {"mae": m, "rmse": r, "n": int(len(g))}

    print(f"\n  GP Val MAE by area:")
    area_stats = {}
    for ar, g in val.groupby("area"):
        m, r = eval_metrics(g["measured_rsrp"].values, g["gp_rsrp"].values, str(ar))
        area_stats[str(ar)] = {"mae": m, "rmse": r, "n": int(len(g))}

    # Save GP model
    model_path = OUT / f"gp_model_op{op}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"gp": gp, "scaler": scaler, "offset_db": baseline_offset}, f)
    print(f"\n  GP model saved: {model_path}")

    stats = {
        "operator": op,
        "baseline_mae": baseline_mae, "baseline_rmse": baseline_rmse,
        "gp_mae": gp_mae, "gp_rmse": gp_rmse,
        "improvement_mae_db": float(baseline_mae - gp_mae),
        "gp_kernel": str(gp.kernel_),
        "n_val": int(len(val)),
        "by_device": dev_stats,
        "by_dist_regime": dist_stats,
        "by_gap_type": gap_stats,
        "by_area": area_stats,
    }
    return val, stats


def main():
    print("A04 GP Calibration — loading sionna_raw.csv...")
    df = pd.read_csv(SIONNA)
    print(f"  Rows: {len(df):,}")

    with open(BASELINE) as f:
        baseline = json.load(f)

    all_val = []
    all_stats = {}

    np.random.seed(42)
    for op in [1, 2]:
        df_op = df[df["operator"] == op].copy()
        offset = baseline[str(op)]["calibration_offset_db"]
        val_df, stats = process_operator(op, df_op, offset)
        if not val_df.empty:
            all_val.append(val_df)
            all_stats[str(op)] = stats

    combined = pd.concat(all_val, ignore_index=True) if all_val else pd.DataFrame()
    combined.to_csv(OUT / "gp_results.csv", index=False)
    with open(OUT / "gp_summary.json", "w") as f:
        json.dump(all_stats, f, indent=2)
    print(f"\nGP results saved: {OUT}/gp_results.csv")
    print(f"GP summary saved: {OUT}/gp_summary.json")


if __name__ == "__main__":
    main()
