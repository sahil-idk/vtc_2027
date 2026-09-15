"""
A10_random_split.py -- TWINGATE Gate 2 split redesign
Implements a session-level random split instead of the temporal split,
addressing the professor's concern that train(June22-23) is a tiny,
potentially unrepresentative segment.

Steps:
  1. Load sionna_raw.csv + GPS coords + gap_type + session IDs
  2. Filter to Unflagged rows only (TypeB, Ambiguous removed)
  3. Per-device: randomly assign 12/17 sessions to train, 5/17 to val
  4. Save new split CSV
  5. Generate a local HTML map (Leaflet, open in browser)
  6. Rerun per-tower linear regression (A09b logic) on the new split
  7. Report MAE comparison old vs new

Fixed seed = 42 for reproducibility.
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from scipy import stats

OUT = Path(__file__).parent / "out"
HERE = Path(__file__).parent
SEED = 42
TRAIN_SESSIONS_PER_DEVICE = 12   # out of 17 total
rng = np.random.default_rng(SEED)

# ── 1. Load and merge ────────────────────────────────────────────────────────
sr  = pd.read_csv(OUT / "sionna_raw.csv")
gl  = pd.read_csv(OUT / "gap_labels.csv")
si  = pd.read_csv(OUT / "split_index.csv")

sr_full = (
    sr
    .merge(gl[["_row", "Latitude", "Longitude", "gap_type"]], on="_row", how="left", suffixes=("_sr", "_gl"))
    .merge(si[["_row", "measurement"]], on="_row", how="left")
)

gap_col = "gap_type_gl" if "gap_type_gl" in sr_full.columns else "gap_type"

# ── 2. Filter flagged ────────────────────────────────────────────────────────
before = len(sr_full)
sr_clean = sr_full[sr_full[gap_col] == "Unflagged"].copy()
after = len(sr_clean)

print(f"Rows after removing TypeB/Ambiguous: {after:,}  (removed {before-after})")
print(f"  TypeB: {(sr_full[gap_col]=='TypeB').sum()},  Ambiguous: {(sr_full[gap_col]=='Ambiguous').sum()}")
print()

# ── 3. Session-level random split ───────────────────────────────────────────
print("Session assignment (new random split, seed=42):")
print(f"  Per device: {TRAIN_SESSIONS_PER_DEVICE} train sessions, "
      f"{17-TRAIN_SESSIONS_PER_DEVICE} val sessions  (out of 17 total)")
print()

sr_clean["new_split"] = "unassigned"

for dev, grp in sr_clean.groupby("device"):
    sessions = sorted(grp["measurement"].unique())
    assert len(sessions) == 17, f"Expected 17 sessions for {dev}, got {len(sessions)}"
    shuffled = rng.permutation(sessions).tolist()
    train_sess = set(shuffled[:TRAIN_SESSIONS_PER_DEVICE])
    val_sess   = set(shuffled[TRAIN_SESSIONS_PER_DEVICE:])
    sr_clean.loc[sr_clean["device"] == dev, "new_split"] = (
        sr_clean.loc[sr_clean["device"] == dev, "measurement"]
        .map(lambda s: "train" if s in train_sess else "val")
    )
    train_rows = grp[grp["measurement"].isin(train_sess)]
    val_rows   = grp[grp["measurement"].isin(val_sess)]
    print(f"  {dev}: train sessions={sorted(train_sess)}")
    print(f"       val   sessions={sorted(val_sess)}")
    print(f"       train rows={len(train_rows):,}  val rows={len(val_rows):,}")
    print()

print("New split summary:")
print(sr_clean.groupby(["operator", "device", "new_split"]).size().to_string())
print()
print("Old temporal split summary (for comparison):")
print(sr_clean.groupby(["operator", "device", "split"]).size().to_string())
print()

# Save new split assignments
sr_clean[["_row", "new_split"]].to_csv(OUT / "new_split_index.csv", index=False)
print(f"Saved: {OUT}/new_split_index.csv")
print()

# ── 4. Per-tower linear regression on NEW split ──────────────────────────────
with open(OUT / "baseline_results.json") as f:
    baseline = json.load(f)

print("=" * 70)
print("Per-Tower Linear Regression on NEW random split (A09b logic)")
print("=" * 70)

new_results = {}

for op in [1, 2]:
    op_df = sr_clean[sr_clean["operator"] == op].copy()
    global_offset = baseline[str(op)]["calibration_offset_db"]
    wcl_mae = baseline[str(op)]["baseline_val_mae_db"]

    train = op_df[op_df["new_split"] == "train"].copy()
    val   = op_df[op_df["new_split"] == "val"].copy()

    # Flat per-tower mean (no Sionna spatial)
    tower_mean_rsrp = train.groupby("cell_id")["measured_rsrp"].mean()
    val2 = val.merge(tower_mean_rsrp.reset_index().rename(columns={"measured_rsrp": "mean_rsrp"}),
                     on="cell_id", how="left")
    val2["mean_rsrp"] = val2["mean_rsrp"].fillna(val2["measured_rsrp"].mean())
    mae_flat = float((val2["measured_rsrp"] - val2["mean_rsrp"]).abs().mean())

    # Per-tower OLS: RSRP = b_i + alpha_i * sionna_power_raw
    tower_params = {}
    for cell_id, g in train.groupby("cell_id"):
        x = g["sionna_power_raw"].values
        y = g["measured_rsrp"].values
        n = len(x)
        if n < 5 or x.std() < 0.01:
            tower_params[cell_id] = {"alpha": 0.0, "b": float(y.mean()), "n": n}
        else:
            slope, intercept, r, pval, se = stats.linregress(x, y)
            slope_clip = float(np.clip(slope, 0.0, 2.0))
            b_clip = float(y.mean() - slope_clip * x.mean())
            tower_params[cell_id] = {"alpha": slope_clip, "b": b_clip, "n": n, "r": float(r)}

    # Apply to val
    val = val.copy()
    val["pred_linear"] = np.nan
    for cell_id, g_idx in val.groupby("cell_id").groups.items():
        p = tower_params.get(cell_id)
        if p is None:
            val.loc[g_idx, "pred_linear"] = val.loc[g_idx, "sionna_power_raw"] + global_offset
        else:
            val.loc[g_idx, "pred_linear"] = p["alpha"] * val.loc[g_idx, "sionna_power_raw"] + p["b"]

    mae_linear = float((val["measured_rsrp"] - val["pred_linear"]).abs().mean())
    rmse_linear = float(np.sqrt(((val["measured_rsrp"] - val["pred_linear"])**2).mean()))

    alphas = [v["alpha"] for v in tower_params.values() if "r" in v]
    print(f"\nOperator {op}:")
    print(f"  Train rows: {len(train):,}  (was {2689 if op==1 else 4271:,} on temporal split)")
    print(f"  Val   rows: {len(val):,}  (was {21249 if op==1 else 22031:,} on temporal split)")
    print(f"  Towers with OLS fit: {len(alphas)}")
    print(f"  Median alpha: {np.median(alphas):.3f}  (was 0.887/1.258 on old split)")
    print()
    print(f"  WCL global baseline (A03)             : {wcl_mae:.3f} dB")
    print(f"  Flat per-tower mean  (no Sionna)       : {mae_flat:.3f} dB  (was {4.622 if op==1 else 7.741:.3f})")
    print(f"  Per-tower linear OLS (Sionna, new split): {mae_linear:.3f} dB  (was {3.460 if op==1 else 5.112:.3f})")
    print(f"  RMSE: {rmse_linear:.3f} dB")
    print(f"  Improvement vs WCL  : {wcl_mae - mae_linear:+.3f} dB")
    print(f"  Improvement vs flat : {mae_flat - mae_linear:+.3f} dB")

    new_results[str(op)] = {
        "mae_per_tower_linear_new_split": mae_linear,
        "rmse_per_tower_linear_new_split": rmse_linear,
        "mae_flat_mean_new_split": mae_flat,
        "mae_wcl_baseline": wcl_mae,
        "n_train": int(len(train)),
        "n_val": int(len(val)),
        "median_alpha": float(np.median(alphas)) if alphas else 0.0,
    }

with open(OUT / "new_split_results.json", "w") as f:
    json.dump(new_results, f, indent=2)

# ── 5. Generate HTML map ─────────────────────────────────────────────────────
print()
print("Generating HTML map...")

# Sample points for map (downsample for browser performance)
MAX_POINTS = 5000
map_df = sr_clean.copy()
map_df["gap_type_map"] = map_df[gap_col]
map_df = map_df[["Latitude", "Longitude", "device", "operator", "split", "new_split", "gap_type_map"]].dropna(subset=["Latitude", "Longitude"])

# Downsample evenly across device + split combos (pandas-safe)
def safe_sample(df, group_cols, n_each):
    parts = []
    for _, g in df.groupby(group_cols):
        parts.append(g.sample(min(len(g), n_each), random_state=42))
    return pd.concat(parts, ignore_index=True)

sampled     = safe_sample(map_df, ["device", "split"],     MAX_POINTS // 8)
sampled_new = safe_sample(map_df, ["device", "new_split"], MAX_POINTS // 8)

# Tower positions
tp = pd.read_csv(OUT / "tower_positions.csv")
towers_json = []
for _, row in tp.iterrows():
    if pd.notna(row.get("wcl_lat")) and pd.notna(row.get("wcl_lon")):
        towers_json.append({
            "lat": row["wcl_lat"], "lon": row["wcl_lon"],
            "op": int(row.get("operator", 0)),
            "cell_id": str(row.get("cell_id", ""))
        })

points_old = sampled[["Latitude","Longitude","device","split","gap_type_map"]].rename(
    columns={"gap_type_map":"gap_type"}).to_dict("records")
points_new = sampled_new[["Latitude","Longitude","device","new_split","gap_type_map"]].rename(
    columns={"gap_type_map":"gap_type"}).to_dict("records")

device_colors = {"pc1": "#2196F3", "pc2": "#FF9800", "pc3": "#4CAF50", "pc4": "#9C27B0"}

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>TWINGATE Train/Val Split Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  body {{ margin:0; font-family: sans-serif; }}
  #header {{ background:#1a237e; color:white; padding:12px 20px; }}
  #header h2 {{ margin:0 0 4px; font-size:18px; }}
  #header p {{ margin:0; font-size:13px; opacity:0.85; }}
  #controls {{ padding:10px 20px; background:#f5f5f5; border-bottom:1px solid #ddd; display:flex; gap:16px; flex-wrap:wrap; align-items:center; }}
  #controls label {{ font-size:13px; cursor:pointer; display:flex; align-items:center; gap:6px; }}
  #map {{ height: calc(100vh - 130px); }}
  .legend {{ background:white; padding:10px; border-radius:6px; box-shadow:0 1px 4px rgba(0,0,0,0.3); font-size:12px; line-height:1.8; }}
  .legend-dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:5px; }}
  .stats {{ background:#e8eaf6; padding:8px 16px; font-size:13px; border-radius:4px; }}
  .tab {{ padding:6px 16px; cursor:pointer; border:1px solid #999; border-radius:4px; background:#fff; font-size:13px; }}
  .tab.active {{ background:#1a237e; color:white; border-color:#1a237e; }}
</style>
</head>
<body>
<div id="header">
  <h2>TWINGATE: Train / Val Split Visualization — Berlin C-V2X Dataset</h2>
  <p>Showing Sionna RT prediction rows only (n≈{len(map_df):,}). Sampled for display.</p>
</div>
<div id="controls">
  <button class="tab active" onclick="showMode('temporal')">Current Temporal Split</button>
  <button class="tab" onclick="showMode('random')">New Random Session Split</button>
  &nbsp;|&nbsp;
  <label><input type="checkbox" id="chk_pc1" checked onchange="refresh()"> <span style="color:#2196F3">■</span> pc1 (Op1)</label>
  <label><input type="checkbox" id="chk_pc4" checked onchange="refresh()"> <span style="color:#9C27B0">■</span> pc4 (Op1)</label>
  <label><input type="checkbox" id="chk_pc2" checked onchange="refresh()"> <span style="color:#FF9800">■</span> pc2 (Op2)</label>
  <label><input type="checkbox" id="chk_pc3" checked onchange="refresh()"> <span style="color:#4CAF50">■</span> pc3 (Op2)</label>
  <label><input type="checkbox" id="chk_towers" checked onchange="refresh()"> <span style="color:#f44336">▲</span> Towers</label>
  <label><input type="checkbox" id="chk_flagged" checked onchange="refresh()"> <span style="color:#f44336">●</span> Flagged</label>
  <div class="stats" id="stats_box">Temporal split: Train=6,960 | Val=43,280 rows (Sionna subset)</div>
</div>
<div id="map"></div>
<script>
const oldPoints = {json.dumps(points_old)};
const newPoints = {json.dumps(points_new)};
const towers = {json.dumps(towers_json[:200])};
const deviceColors = {json.dumps(device_colors)};

let mode = 'temporal';
let map = L.map('map').setView([52.495, 13.32], 13);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution: '&copy; OpenStreetMap contributors', maxZoom: 19
}}).addTo(map);

let layers = [];

function clearLayers() {{
  layers.forEach(l => map.removeLayer(l));
  layers = [];
}}

function refresh() {{
  clearLayers();
  const show = {{
    pc1: document.getElementById('chk_pc1').checked,
    pc2: document.getElementById('chk_pc2').checked,
    pc3: document.getElementById('chk_pc3').checked,
    pc4: document.getElementById('chk_pc4').checked,
  }};
  const showTowers = document.getElementById('chk_towers').checked;
  const showFlagged = document.getElementById('chk_flagged').checked;
  const pts = mode === 'temporal' ? oldPoints : newPoints;
  const splitKey = mode === 'temporal' ? 'split' : 'new_split';

  pts.forEach(p => {{
    if (!show[p.device]) return;
    if (!showFlagged && p.gap_type !== 'Unflagged') return;
    const isTrain = p[splitKey] === 'train';
    const isFlagged = p.gap_type !== 'Unflagged';
    const baseColor = deviceColors[p.device] || '#888';
    const fillColor = isFlagged ? '#f44336' : baseColor;
    const opacity = isTrain ? 1.0 : 0.45;
    const radius = isFlagged ? 5 : 3;
    const marker = L.circleMarker([p.Latitude, p.Longitude], {{
      radius, color: isTrain ? '#222' : '#aaa', weight: 0.5,
      fillColor, fillOpacity: opacity
    }}).bindPopup(`<b>${{p.device}}</b><br>Split: ${{p[splitKey]}}<br>Type: ${{p.gap_type}}`);
    marker.addTo(map);
    layers.push(marker);
  }});

  if (showTowers) {{
    towers.forEach(t => {{
      const col = t.op === 1 ? '#e53935' : '#e65100';
      const m = L.marker([t.lat, t.lon], {{
        icon: L.divIcon({{
          html: `<div style="background:${{col}};width:10px;height:10px;border-radius:2px;border:1px solid #222;"></div>`,
          iconSize:[10,10], iconAnchor:[5,5]
        }})
      }}).bindPopup(`Tower ${{t.cell_id}}<br>Op${{t.op}}`);
      m.addTo(map); layers.push(m);
    }});
  }}

  // Legend
  const legend = L.control({{position:'bottomright'}});
  legend.onAdd = () => {{
    const div = L.DomUtil.create('div','legend');
    div.innerHTML = `
      <b>${{mode==='temporal'?'Temporal Split':'Random Session Split'}}</b><br>
      <span class="legend-dot" style="background:#555;opacity:1"></span>Train (solid/dark border)<br>
      <span class="legend-dot" style="background:#888;opacity:0.5"></span>Val (faded)<br>
      <span class="legend-dot" style="background:#2196F3"></span>pc1 (Op1)<br>
      <span class="legend-dot" style="background:#9C27B0"></span>pc4 (Op1)<br>
      <span class="legend-dot" style="background:#FF9800"></span>pc2 (Op2)<br>
      <span class="legend-dot" style="background:#4CAF50"></span>pc3 (Op2)<br>
      <span class="legend-dot" style="background:#f44336"></span>Flagged (TypeB/Amb)<br>
      <div style="margin-top:4px"><b>Towers:</b> Op1=<span style="color:#e53935">■</span> Op2=<span style="color:#e65100">■</span></div>
    `;
    return div;
  }};
  legend.addTo(map); layers.push(legend);
}}

function showMode(m) {{
  mode = m;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  event.target.classList.add('active');
  const box = document.getElementById('stats_box');
  if (m === 'temporal') {{
    box.textContent = 'Temporal split: Train=6,960 | Val=43,280 rows (in Sionna subset). Train = June 22-23 only.';
  }} else {{
    box.textContent = 'Random session split (seed=42): Train≈35K | Val≈15K rows. All 17 sessions randomly assigned 12/5.';
  }}
  refresh();
}}

refresh();
</script>
</body>
</html>"""

map_path = HERE / "split_map.html"
map_path.write_text(html, encoding="utf-8")
print(f"HTML map written to: {map_path}")
print("Open split_map.html in your browser to view the map.")
print()
print("=" * 70)
print("SUMMARY")
print("=" * 70)
print(f"\n{'Method':<50} {'Op1':>8} {'Op2':>8}")
print(f"{'WCL global baseline (A03, temporal split)':<50} {'10.866':>8} {'12.238':>8}")
print(f"{'Per-tower linear OLS (A09b, OLD temporal split)':<50} {'3.460':>8} {'5.112':>8}")
print(f"{'Flat per-tower mean (new random split)':<50} {new_results['1']['mae_flat_mean_new_split']:>8.3f} {new_results['2']['mae_flat_mean_new_split']:>8.3f}")
print(f"{'Per-tower linear OLS (NEW random session split)':<50} {new_results['1']['mae_per_tower_linear_new_split']:>8.3f} {new_results['2']['mae_per_tower_linear_new_split']:>8.3f}")
