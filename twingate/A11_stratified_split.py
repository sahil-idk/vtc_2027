"""
A11_stratified_split.py — TWINGATE Gate 2
Stratified 80/20 split by (device, cell_id) on ALL unflagged rows.
Guarantees every tower appears in BOTH train and val.
Generates and launches full_stratified_map.html.
"""
import json
import numpy as np
import pandas as pd
from pathlib import Path

ROOT = Path(__file__).parent.parent
OUT  = Path(__file__).parent / "out"
HERE = Path(__file__).parent

TRAIN_FRAC = 0.80
MIN_ROWS   = 5
SEED       = 42
rng        = np.random.default_rng(SEED)

# ── Load raw dataset + gap labels ────────────────────────────────────────────
print("Loading data...")
raw = pd.read_csv(ROOT / "cellular_dataframe_cleaned.csv", low_memory=False)
raw = raw.sort_values(["device", "ts_gps"]).reset_index(drop=True)
raw["_row"] = raw.index

gl  = pd.read_csv(OUT / "gap_labels.csv")   # has gap_type, Latitude, Longitude

# Merge gap type onto raw
df = raw.merge(gl[["_row", "gap_type"]], on="_row", how="left")
df["gap_type"] = df["gap_type"].fillna("Unflagged")

# Infer operator from device
op_map = {"pc1": 1, "pc4": 1, "pc2": 2, "pc3": 2}
df["operator"] = df["device"].map(op_map)

# Cell ID column name
cell_col = "PCell_Cell_Identity"
rsrp_col = "PCell_RSRP_max"
lat_col  = "Latitude"
lon_col  = "Longitude"

print(f"Raw rows: {len(df):,}")

# ── Filter: Unflagged + valid GPS + valid RSRP + valid cell_id ───────────────
clean = df[
    (df["gap_type"] == "Unflagged") &
    df[lat_col].notna() &
    df[lon_col].notna() &
    df[rsrp_col].notna() &
    df[cell_col].notna()
].copy()
clean = clean.rename(columns={cell_col: "cell_id",
                               rsrp_col: "measured_rsrp",
                               lat_col:  "Latitude",
                               lon_col:  "Longitude"})
clean["cell_id"] = clean["cell_id"].astype(str)

print(f"Unflagged + valid GPS + RSRP + cell_id: {len(clean):,}")
print(f"Unique towers: {clean['cell_id'].nunique()}")
print(f"By device:")
print(clean.groupby(["operator","device"]).size().to_string())
print()

# ── Stratified 80/20 by (device, cell_id) ───────────────────────────────────
print("Applying stratified 80/20 split by (device, cell_id)...")
clean["new_split"] = "unassigned"

skipped_tiny = 0
pair_stats = []

for (dev, cell), grp in clean.groupby(["device", "cell_id"]):
    n = len(grp)
    if n < MIN_ROWS:
        skipped_tiny += n
        continue

    n_val   = max(1, round(n * (1 - TRAIN_FRAC)))
    n_train = n - n_val

    pair_seed = abs(hash(dev + str(cell))) % (2**31)
    val_idx   = grp.sample(n=n_val, random_state=pair_seed).index
    train_idx = grp.index.difference(val_idx)

    clean.loc[train_idx, "new_split"] = "train"
    clean.loc[val_idx,   "new_split"] = "val"

    pair_stats.append({"device": dev, "cell_id": cell,
                        "n_total": n, "n_train": n_train, "n_val": n_val})

assigned = clean[clean["new_split"] != "unassigned"]
print(f"  Rows assigned (≥{MIN_ROWS} per pair): {len(assigned):,}")
print(f"  Rows skipped  (<{MIN_ROWS} per pair): {skipped_tiny:,}")
print()

pair_df = pd.DataFrame(pair_stats)
print("Split counts by operator/device:")
print(assigned.groupby(["operator", "device", "new_split"]).size().to_string())
print()
print(f"Total train: {(assigned['new_split']=='train').sum():,}")
print(f"Total val  : {(assigned['new_split']=='val').sum():,}")
print()

# Tower coverage check
towers_in_train = set(assigned[assigned["new_split"]=="train"]["cell_id"])
towers_in_val   = set(assigned[assigned["new_split"]=="val"  ]["cell_id"])
towers_both     = towers_in_train & towers_in_val
towers_only_tr  = towers_in_train - towers_in_val
towers_only_val = towers_in_val   - towers_in_train
print(f"Tower coverage check:")
print(f"  Towers in BOTH train and val : {len(towers_both)}  ✅")
print(f"  Towers only in train         : {len(towers_only_tr)}")
print(f"  Towers only in val           : {len(towers_only_val)}")
print()

# Save split index
assigned[["_row","device","cell_id","operator","new_split"]].to_csv(
    OUT / "stratified_split_index.csv", index=False)
print(f"Saved: {OUT}/stratified_split_index.csv")

# ── Compute stats for sidebar ────────────────────────────────────────────────
sr = pd.read_csv(OUT / "sionna_raw.csv")   # existing predictions

# How many of the stratified-split rows already have Sionna predictions?
sionna_rows = set(sr["_row"])
assigned["has_sionna"] = assigned["_row"].isin(sionna_rows)

stats = {
    "total_raw":       len(df),
    "total_unflagged": len(clean),
    "total_assigned":  len(assigned),
    "train_total":     int((assigned["new_split"]=="train").sum()),
    "val_total":       int((assigned["new_split"]=="val"  ).sum()),
    "op1_train": int(len(assigned[(assigned["operator"]==1)&(assigned["new_split"]=="train")])),
    "op1_val":   int(len(assigned[(assigned["operator"]==1)&(assigned["new_split"]=="val")])),
    "op2_train": int(len(assigned[(assigned["operator"]==2)&(assigned["new_split"]=="train")])),
    "op2_val":   int(len(assigned[(assigned["operator"]==2)&(assigned["new_split"]=="val")])),
    "pc1_train": int(len(assigned[(assigned["device"]=="pc1")&(assigned["new_split"]=="train")])),
    "pc1_val":   int(len(assigned[(assigned["device"]=="pc1")&(assigned["new_split"]=="val")])),
    "pc2_train": int(len(assigned[(assigned["device"]=="pc2")&(assigned["new_split"]=="train")])),
    "pc2_val":   int(len(assigned[(assigned["device"]=="pc2")&(assigned["new_split"]=="val")])),
    "pc3_train": int(len(assigned[(assigned["device"]=="pc3")&(assigned["new_split"]=="train")])),
    "pc3_val":   int(len(assigned[(assigned["device"]=="pc3")&(assigned["new_split"]=="val")])),
    "pc4_train": int(len(assigned[(assigned["device"]=="pc4")&(assigned["new_split"]=="train")])),
    "pc4_val":   int(len(assigned[(assigned["device"]=="pc4")&(assigned["new_split"]=="val")])),
    "towers_both":     len(towers_both),
    "towers_only_tr":  len(towers_only_tr),
    "towers_only_val": len(towers_only_val),
    "sionna_in_train": int(assigned[assigned["new_split"]=="train"]["has_sionna"].sum()),
    "sionna_in_val":   int(assigned[assigned["new_split"]=="val"  ]["has_sionna"].sum()),
}

# ── Sample for map ────────────────────────────────────────────────────────────
print("Sampling points for map...")

def sample_group(df, cols, n_each):
    parts = []
    for _, g in df.groupby(cols):
        parts.append(g.sample(min(len(g), n_each), random_state=42))
    return pd.concat(parts, ignore_index=True)

sampled = sample_group(assigned, ["device", "new_split"], 800)

# Also include ALL flagged rows (TypeA/TypeB/Ambiguous) for context
flagged_all = df[df["gap_type"] != "Unflagged"].dropna(subset=["Latitude","Longitude"])
flagged_samp = sample_group(flagged_all, ["gap_type","device"], 300)

device_colors = {"pc1": "#1565C0", "pc2": "#E65100", "pc3": "#2E7D32", "pc4": "#6A1B9A"}
gap_colors    = {"TypeA": "#B71C1C", "TypeB": "#F9A825", "Ambiguous": "#78909C"}

points = []
for _, r in sampled.iterrows():
    points.append({
        "lat":   round(float(r["Latitude"]), 6),
        "lon":   round(float(r["Longitude"]), 6),
        "dev":   r["device"],
        "split": r["new_split"],
        "op":    int(r["operator"]),
        "sio":   bool(r["has_sionna"]),
        "color": device_colors.get(r["device"], "#888"),
        "flag":  "Unflagged",
    })

for _, r in flagged_samp.iterrows():
    if pd.isna(r[lat_col]) or pd.isna(r[lon_col]):
        continue
    points.append({
        "lat":   round(float(r[lat_col]), 6),
        "lon":   round(float(r[lon_col]), 6),
        "dev":   r["device"],
        "split": "flagged",
        "op":    int(r["operator"]),
        "sio":   False,
        "color": gap_colors.get(r["gap_type"], "#888"),
        "flag":  r["gap_type"],
    })

# Tower positions (WCL)
tp = pd.read_csv(OUT / "tower_positions.csv")
towers_json = []
for _, row in tp.iterrows():
    if pd.notna(row.get("wcl_lat")) and pd.notna(row.get("wcl_lon")):
        # Is this tower in both splits?
        cid = str(int(row.get("cell_id", 0)))
        coverage = "both" if cid in towers_both else ("train_only" if cid in towers_in_train else "val_only")
        towers_json.append({
            "lat": round(float(row["wcl_lat"]), 6),
            "lon": round(float(row["wcl_lon"]), 6),
            "op":  int(row.get("operator", 0)),
            "cid": cid,
            "cov": coverage,
        })

print(f"Map points: {len(points):,}  (unflagged: {len(sampled)}, flagged: {len(flagged_samp)})")

# ── Generate HTML ─────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>TWINGATE Stratified Split Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:#f0f4f8;font-size:13px}}
#hdr{{background:#1a237e;color:#fff;padding:11px 18px}}
#hdr h2{{font-size:16px;margin-bottom:2px}}
#hdr p{{font-size:11px;opacity:.85}}
#wrap{{display:flex;height:calc(100vh - 54px)}}
#side{{width:300px;min-width:300px;overflow-y:auto;background:#fff;border-right:1px solid #ddd;padding:12px}}
#map{{flex:1}}
h3{{font-size:11px;font-weight:700;text-transform:uppercase;color:#555;margin:12px 0 6px;letter-spacing:.4px;border-top:1px solid #eee;padding-top:8px}}
h3:first-child{{border-top:none;margin-top:0}}
.row{{display:flex;justify-content:space-between;padding:2px 0;line-height:1.6}}
.val{{font-weight:700;color:#1a237e}}
.ok{{color:#2e7d32}}
.warn{{color:#c62828}}
.chip{{display:inline-block;width:10px;height:10px;border-radius:2px;vertical-align:middle;margin-right:5px}}
label{{display:flex;align-items:center;gap:6px;cursor:pointer;padding:2px 0}}
.badge{{display:inline-block;background:#e8eaf6;border-radius:10px;padding:1px 8px;font-size:11px;color:#3949ab;font-weight:700}}
</style>
</head>
<body>
<div id="hdr">
  <h2>TWINGATE — Stratified 80/20 Split by (Device × Tower) — All Unflagged Rows</h2>
  <p>Every tower guaranteed in both train and val &nbsp;|&nbsp; {stats['total_assigned']:,} assigned rows &nbsp;|&nbsp; Seed=42</p>
</div>
<div id="wrap">
<div id="side">

  <h3>Split Strategy</h3>
  <div style="background:#e8eaf6;border-radius:6px;padding:8px;line-height:1.8;font-size:12px">
    Stratified random split<br>
    Ratio: <b>80% train / 20% val</b><br>
    Stratify key: <b>(device, cell_id)</b><br>
    Min rows/pair: <b>5</b> &nbsp; Seed: <b>42</b>
  </div>

  <h3>Data Funnel</h3>
  <div class="row"><span>Raw dataset</span><span class="val">{stats['total_raw']:,}</span></div>
  <div class="row"><span>Unflagged + valid GPS/RSRP/cell</span><span class="val">{stats['total_unflagged']:,}</span></div>
  <div class="row"><span>Assigned (≥5 rows/pair)</span><span class="val">{stats['total_assigned']:,}</span></div>
  <div class="row"><span>&nbsp;&nbsp;→ Train</span><span class="val ok">{stats['train_total']:,}</span></div>
  <div class="row"><span>&nbsp;&nbsp;→ Val</span><span class="val ok">{stats['val_total']:,}</span></div>

  <h3>Tower Coverage ✅</h3>
  <div class="row"><span>Towers in BOTH splits</span><span class="badge">{stats['towers_both']}</span></div>
  <div class="row"><span>Train-only towers</span><span class="val warn">{stats['towers_only_tr']}</span></div>
  <div class="row"><span>Val-only towers</span><span class="val warn">{stats['towers_only_val']}</span></div>

  <h3>Existing Sionna Predictions</h3>
  <div class="row"><span>Sionna rows in train split</span><span class="val">{stats['sionna_in_train']:,}</span></div>
  <div class="row"><span>Sionna rows in val split</span><span class="val">{stats['sionna_in_val']:,}</span></div>
  <div style="color:#888;font-size:11px;margin-top:4px">Rows needing NEW Sionna: {stats['train_total']-stats['sionna_in_train']:,} train + {stats['val_total']-stats['sionna_in_val']:,} val</div>

  <h3>By Operator</h3>
  <div class="row"><span>Op1 train</span><span class="val">{stats['op1_train']:,}</span></div>
  <div class="row"><span>Op1 val</span><span class="val">{stats['op1_val']:,}</span></div>
  <div class="row"><span>Op2 train</span><span class="val">{stats['op2_train']:,}</span></div>
  <div class="row"><span>Op2 val</span><span class="val">{stats['op2_val']:,}</span></div>

  <h3>By Device</h3>
  <div class="row"><span><span class="chip" style="background:#1565C0"></span>pc1 train</span><span class="val">{stats['pc1_train']:,}</span></div>
  <div class="row"><span><span class="chip" style="background:#1565C0;opacity:.4"></span>pc1 val</span><span class="val">{stats['pc1_val']:,}</span></div>
  <div class="row"><span><span class="chip" style="background:#6A1B9A"></span>pc4 train</span><span class="val">{stats['pc4_train']:,}</span></div>
  <div class="row"><span><span class="chip" style="background:#6A1B9A;opacity:.4"></span>pc4 val</span><span class="val">{stats['pc4_val']:,}</span></div>
  <div class="row"><span><span class="chip" style="background:#E65100"></span>pc2 train</span><span class="val">{stats['pc2_train']:,}</span></div>
  <div class="row"><span><span class="chip" style="background:#E65100;opacity:.4"></span>pc2 val</span><span class="val">{stats['pc2_val']:,}</span></div>
  <div class="row"><span><span class="chip" style="background:#2E7D32"></span>pc3 train</span><span class="val">{stats['pc3_train']:,}</span></div>
  <div class="row"><span><span class="chip" style="background:#2E7D32;opacity:.4"></span>pc3 val</span><span class="val">{stats['pc3_val']:,}</span></div>

  <h3>Layer Controls</h3>
  <label><input type="checkbox" id="lyr_train" checked onchange="refresh()"><span class="chip" style="background:#555"></span>Train (solid)</label>
  <label><input type="checkbox" id="lyr_val" checked onchange="refresh()"><span class="chip" style="background:#555;opacity:.35"></span>Val (faded)</label>
  <label><input type="checkbox" id="lyr_flagged" checked onchange="refresh()"><span class="chip" style="background:#B71C1C"></span>Flagged rows</label>
  <label><input type="checkbox" id="lyr_towers" checked onchange="refresh()"><span class="chip" style="background:#e53935;border-radius:0"></span>WCL towers</label>
  <label><input type="checkbox" id="lyr_sio" onchange="refresh()"><span class="chip" style="background:#00acc1"></span>Sionna-covered only</label>
  <div style="margin-top:8px;font-size:11px;color:#888">
    Tower squares: <span style="color:#e53935">■</span>=both splits &nbsp; <span style="color:#f9a825">■</span>=train-only
  </div>

  <h3>Legend</h3>
  <div style="line-height:2;font-size:12px">
    <div><span class="chip" style="background:#1565C0"></span>pc1 (Op1)</div>
    <div><span class="chip" style="background:#6A1B9A"></span>pc4 (Op1)</div>
    <div><span class="chip" style="background:#E65100"></span>pc2 (Op2)</div>
    <div><span class="chip" style="background:#2E7D32"></span>pc3 (Op2)</div>
    <div><span class="chip" style="background:#B71C1C"></span>TypeA (pc4 fail)</div>
    <div><span class="chip" style="background:#F9A825"></span>TypeB (dropout)</div>
    <div><span class="chip" style="background:#78909C"></span>Ambiguous</div>
  </div>

</div>
<div id="map"></div>
</div>
<script>
const PTS = {json.dumps(points)};
const TWR = {json.dumps(towers_json)};

const map = L.map('map').setView([52.493, 13.313], 13);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png',{{
  attribution:'&copy; OpenStreetMap contributors',maxZoom:19
}}).addTo(map);

let layers=[];
function clearLayers(){{layers.forEach(l=>map.removeLayer(l));layers=[];}}

function refresh(){{
  clearLayers();
  const showTrain   = document.getElementById('lyr_train').checked;
  const showVal     = document.getElementById('lyr_val').checked;
  const showFlagged = document.getElementById('lyr_flagged').checked;
  const showTowers  = document.getElementById('lyr_towers').checked;
  const sioOnly     = document.getElementById('lyr_sio').checked;

  PTS.forEach(p=>{{
    if (sioOnly && !p.sio) return;
    if (p.flag !== 'Unflagged'){{
      if (!showFlagged) return;
    }} else {{
      if (p.split==='train' && !showTrain) return;
      if (p.split==='val'   && !showVal  ) return;
    }}
    const isTrain = p.split==='train';
    const opacity = p.flag==='Unflagged' ? (isTrain ? 0.85 : 0.30) : 0.9;
    const r = p.flag!=='Unflagged' ? 5 : 3;
    const m = L.circleMarker([p.lat,p.lon],{{
      radius:r, color:'transparent', weight:0,
      fillColor:p.color, fillOpacity:opacity
    }}).bindPopup(`<b>${{p.dev}}</b> (Op${{p.op}})<br>Split: ${{p.split}}<br>Type: ${{p.flag}}<br>Sionna: ${{p.sio?'✅':'❌ (needs rerun)'}}`);
    m.addTo(map); layers.push(m);
  }});

  if (showTowers){{
    TWR.forEach(t=>{{
      const col = t.cov==='both' ? '#e53935' : (t.cov==='train_only' ? '#f9a825' : '#9c27b0');
      const m = L.marker([t.lat,t.lon],{{icon:L.divIcon({{
        html:`<div style="background:${{col}};width:9px;height:9px;border:1.5px solid #fff"></div>`,
        iconSize:[9,9],iconAnchor:[4,4]
      }})}}).bindPopup(`Tower ${{t.cid}}<br>Op${{t.op}}<br>Coverage: ${{t.cov}}`);
      m.addTo(map); layers.push(m);
    }});
  }}
}}

refresh();
</script>
</body>
</html>"""

out_path = HERE / "full_stratified_map.html"
out_path.write_text(html, encoding="utf-8")
print(f"\nMap written: {out_path}")
