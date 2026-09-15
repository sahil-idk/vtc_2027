"""
Generate full_split_map.html — shows ALL 207,434 rows with counts,
gap types, temporal split, and Sionna coverage subset.
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path

OUT  = Path(__file__).parent / "out"
HERE = Path(__file__).parent

# ── Load all datasets ────────────────────────────────────────────────────────
gl = pd.read_csv(OUT / "gap_labels.csv")
si = pd.read_csv(OUT / "split_index.csv")
sr = pd.read_csv(OUT / "sionna_raw.csv")

# Merge gap + split info (full 207k dataset)
full = gl.merge(si[["_row", "split", "date_str"]], on="_row", how="left")
full["split"]    = full["split"].fillna("unknown")
full["date_str"] = full["date_str"].fillna("unknown")

# Mark which rows have Sionna predictions
full["has_sionna"] = full["_row"].isin(sr["_row"])

# Drop rows with no GPS
full = full.dropna(subset=["Latitude", "Longitude"])

print(f"Full dataset with GPS: {len(full):,} rows")

# ── Compute counts for stats panel ──────────────────────────────────────────
def cnt(mask): return int(mask.sum())

stats = {
    "total": cnt(full["_row"].notna()),
    "op1_total":      cnt(full["operator"] == 1),
    "op2_total":      cnt(full["operator"] == 2),
    "unflagged":      cnt(full["gap_type"] == "Unflagged"),
    "typeA":          cnt(full["gap_type"] == "TypeA"),
    "typeB":          cnt(full["gap_type"] == "TypeB"),
    "ambiguous":      cnt(full["gap_type"] == "Ambiguous"),
    "train_unflagged": cnt((full["split"]=="train") & (full["gap_type"]=="Unflagged")),
    "val_unflagged":   cnt((full["split"]=="val")   & (full["gap_type"]=="Unflagged")),
    "has_sionna":     cnt(full["has_sionna"]),
    "no_sionna":      cnt(~full["has_sionna"]),
    "op1_train": cnt((full["operator"]==1) & (full["split"]=="train")),
    "op1_val":   cnt((full["operator"]==1) & (full["split"]=="val")),
    "op2_train": cnt((full["operator"]==2) & (full["split"]=="train")),
    "op2_val":   cnt((full["operator"]==2) & (full["split"]=="val")),
    "pc1_total": cnt(full["device"]=="pc1"),
    "pc2_total": cnt(full["device"]=="pc2"),
    "pc3_total": cnt(full["device"]=="pc3"),
    "pc4_total": cnt(full["device"]=="pc4"),
    "sionna_train": cnt(full["has_sionna"] & (full["split"]=="train")),
    "sionna_val":   cnt(full["has_sionna"] & (full["split"]=="val")),
}

print("Key stats:")
for k, v in stats.items():
    print(f"  {k}: {v:,}")

# ── Sample points for map rendering ─────────────────────────────────────────
# Sample each group proportionally for browser performance (~15k total)
SAMPLE_N = 600   # per (device, gap_type, split) group

def sample_group(df, cols, n):
    parts = []
    for _, g in df.groupby(cols):
        parts.append(g.sample(min(len(g), n), random_state=42))
    return pd.concat(parts, ignore_index=True)

# Unflagged rows (coloured by device)
uf = full[full["gap_type"] == "Unflagged"]
sampled_uf = sample_group(uf, ["device", "split"], SAMPLE_N)

# Flagged rows (TypeA, TypeB, Ambiguous) — show all (small numbers)
flagged = full[full["gap_type"] != "Unflagged"]

# All sampled
sampled = pd.concat([sampled_uf, flagged], ignore_index=True)
print(f"\nSampled for map: {len(sampled):,} points")

# Build point records
device_colors = {"pc1": "#1565C0", "pc2": "#E65100", "pc3": "#2E7D32", "pc4": "#6A1B9A"}
gap_colors    = {"TypeA": "#B71C1C", "TypeB": "#F9A825", "Ambiguous": "#546E7A"}

points = []
for _, r in sampled.iterrows():
    gt = r["gap_type"]
    dev = r["device"]
    is_train = (r["split"] == "train")
    has_sio  = bool(r["has_sionna"])
    if gt != "Unflagged":
        color = gap_colors.get(gt, "#888")
    else:
        color = device_colors.get(dev, "#888")
    points.append({
        "lat": round(r["Latitude"], 6),
        "lon": round(r["Longitude"], 6),
        "device": dev,
        "split": r["split"],
        "gap": gt,
        "sio": has_sio,
        "op": int(r["operator"]),
        "color": color,
        "train": is_train,
    })

# Tower positions
tp = pd.read_csv(OUT / "tower_positions.csv")
towers = []
for _, row in tp.iterrows():
    if pd.notna(row.get("wcl_lat")) and pd.notna(row.get("wcl_lon")):
        towers.append({
            "lat": round(float(row["wcl_lat"]), 6),
            "lon": round(float(row["wcl_lon"]), 6),
            "op":  int(row.get("operator", 0)),
        })

# ── Write HTML ───────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>TWINGATE Full Dataset Split Map</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:#f0f4f8}}
#header{{background:#0d47a1;color:#fff;padding:12px 20px}}
#header h2{{font-size:17px;margin-bottom:3px}}
#header p{{font-size:12px;opacity:.85}}
#main{{display:flex;height:calc(100vh - 58px)}}
#sidebar{{width:310px;min-width:310px;background:#fff;border-right:1px solid #ddd;overflow-y:auto;padding:14px;font-size:13px}}
#map{{flex:1}}
.section{{margin-bottom:14px;border-bottom:1px solid #eee;padding-bottom:10px}}
.section h3{{font-size:12px;font-weight:700;text-transform:uppercase;color:#555;margin-bottom:8px;letter-spacing:.5px}}
.stat-row{{display:flex;justify-content:space-between;margin:3px 0;line-height:1.5}}
.stat-label{{color:#444}}
.stat-val{{font-weight:700;color:#0d47a1}}
.stat-val.warn{{color:#e53935}}
.stat-val.ok{{color:#2e7d32}}
.chip{{display:inline-block;width:11px;height:11px;border-radius:2px;margin-right:5px;vertical-align:middle}}
label.chk{{display:flex;align-items:center;gap:6px;cursor:pointer;padding:3px 0;font-size:12px}}
.tab-btn{{padding:5px 12px;border:1px solid #bbb;border-radius:4px;cursor:pointer;font-size:12px;background:#fff;margin:2px}}
.tab-btn.active{{background:#0d47a1;color:#fff;border-color:#0d47a1}}
.funnel{{background:#f8f9fa;border-radius:6px;padding:10px;font-size:12px;line-height:2}}
.funnel .row{{display:flex;justify-content:space-between}}
.funnel .arrow{{text-align:center;color:#aaa;font-size:16px}}
</style>
</head>
<body>
<div id="header">
  <h2>TWINGATE — Full Berlin C-V2X Dataset: Split & Coverage Map</h2>
  <p>All {stats['total']:,} GPS rows • {stats['has_sionna']:,} with Sionna RT predictions ({round(stats['has_sionna']/stats['total']*100,1)}% coverage)</p>
</div>
<div id="main">
<div id="sidebar">

  <div class="section">
    <h3>View</h3>
    <button class="tab-btn active" onclick="setView('all')" id="btn_all">Full Dataset</button>
    <button class="tab-btn" onclick="setView('sionna')" id="btn_sionna">Sionna Subset</button>
  </div>

  <div class="section">
    <h3>Data Funnel</h3>
    <div class="funnel">
      <div class="row"><span>Raw dataset</span><span><b>{stats['total']:,}</b></span></div>
      <div class="arrow">↓ gap classification</div>
      <div class="row"><span>Unflagged</span><span class="stat-val ok">{stats['unflagged']:,}</span></div>
      <div class="row"><span style="color:#B71C1C">TypeA (pc4 fail)</span><span class="stat-val warn">{stats['typeA']:,}</span></div>
      <div class="row"><span style="color:#F9A825">TypeB (dropout)</span><span class="stat-val warn">{stats['typeB']:,}</span></div>
      <div class="row"><span style="color:#546E7A">Ambiguous</span><span>{stats['ambiguous']:,}</span></div>
      <div class="arrow">↓ Sionna RT filter</div>
      <div class="row"><span>Has Sionna prediction</span><span class="stat-val ok">{stats['has_sionna']:,}</span></div>
      <div class="row"><span>No Sionna coverage</span><span class="stat-val warn">{stats['no_sionna']:,}</span></div>
    </div>
  </div>

  <div class="section">
    <h3>Temporal Split (current)</h3>
    <div class="stat-row"><span class="stat-label">Op1 train (Jun 22-23)</span><span class="stat-val">{stats['op1_train']:,}</span></div>
    <div class="stat-row"><span class="stat-label">Op1 val   (Jun 24)</span><span class="stat-val">{stats['op1_val']:,}</span></div>
    <div class="stat-row"><span class="stat-label">Op2 train (Jun 22-23)</span><span class="stat-val">{stats['op2_train']:,}</span></div>
    <div class="stat-row"><span class="stat-label">Op2 val   (Jun 24)</span><span class="stat-val">{stats['op2_val']:,}</span></div>
    <div class="stat-row" style="margin-top:6px"><span class="stat-label">Unflagged train</span><span class="stat-val">{stats['train_unflagged']:,}</span></div>
    <div class="stat-row"><span class="stat-label">Unflagged val</span><span class="stat-val">{stats['val_unflagged']:,}</span></div>
  </div>

  <div class="section">
    <h3>Sionna Subset Split</h3>
    <div class="stat-row"><span class="stat-label">Sionna train rows</span><span class="stat-val warn">{stats['sionna_train']:,} ⚠</span></div>
    <div class="stat-row"><span class="stat-label">Sionna val rows</span><span class="stat-val">{stats['sionna_val']:,}</span></div>
    <div class="stat-row" style="color:#888;font-size:11px;margin-top:4px"><span>Train rows capped at 40/tower in A03</span></div>
  </div>

  <div class="section">
    <h3>Per-Device</h3>
    <div class="stat-row"><span><span class="chip" style="background:#1565C0"></span>pc1 (Op1)</span><span class="stat-val">{stats['pc1_total']:,}</span></div>
    <div class="stat-row"><span><span class="chip" style="background:#6A1B9A"></span>pc4 (Op1)</span><span class="stat-val">{stats['pc4_total']:,}</span></div>
    <div class="stat-row"><span><span class="chip" style="background:#E65100"></span>pc2 (Op2)</span><span class="stat-val">{stats['pc2_total']:,}</span></div>
    <div class="stat-row"><span><span class="chip" style="background:#2E7D32"></span>pc3 (Op2)</span><span class="stat-val">{stats['pc3_total']:,}</span></div>
  </div>

  <div class="section">
    <h3>Layer Controls</h3>
    <label class="chk"><input type="checkbox" id="chk_train" checked onchange="refresh()"><span class="chip" style="background:#1565C0;opacity:1"></span>Train rows</label>
    <label class="chk"><input type="checkbox" id="chk_val" checked onchange="refresh()"><span class="chip" style="background:#1565C0;opacity:.4"></span>Val rows</label>
    <label class="chk"><input type="checkbox" id="chk_typeA" checked onchange="refresh()"><span class="chip" style="background:#B71C1C"></span>TypeA (pc4 fail)</label>
    <label class="chk"><input type="checkbox" id="chk_typeB" checked onchange="refresh()"><span class="chip" style="background:#F9A825"></span>TypeB (dropout)</label>
    <label class="chk"><input type="checkbox" id="chk_ambig" checked onchange="refresh()"><span class="chip" style="background:#546E7A"></span>Ambiguous</label>
    <label class="chk"><input type="checkbox" id="chk_towers" checked onchange="refresh()"><span class="chip" style="background:#e53935;border-radius:0"></span>WCL Towers</label>
    <label class="chk"><input type="checkbox" id="chk_sionna_only" onchange="refresh()">Sionna-covered only</label>
  </div>

  <div class="section">
    <h3>Legend</h3>
    <div style="font-size:12px;line-height:2">
      <div><span class="chip" style="background:#1565C0"></span>pc1 — Op1 (solid=train, faded=val)</div>
      <div><span class="chip" style="background:#6A1B9A"></span>pc4 — Op1</div>
      <div><span class="chip" style="background:#E65100"></span>pc2 — Op2</div>
      <div><span class="chip" style="background:#2E7D32"></span>pc3 — Op2</div>
      <div><span class="chip" style="background:#B71C1C"></span>TypeA — pc4 gap (bad data)</div>
      <div><span class="chip" style="background:#F9A825"></span>TypeB — signal dropout zone</div>
      <div><span class="chip" style="background:#546E7A"></span>Ambiguous</div>
      <div><span class="chip" style="background:#e53935;border-radius:0"></span>WCL tower position</div>
    </div>
  </div>

</div>
<div id="map"></div>
</div>

<script>
const ALL_POINTS = {json.dumps(points)};
const TOWERS = {json.dumps(towers[:300])};
const STATS = {json.dumps(stats)};

let map = L.map('map').setView([52.493, 13.31], 13);
L.tileLayer('https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  attribution:'&copy; OpenStreetMap contributors', maxZoom:19
}}).addTo(map);

let layers = [];
let currentView = 'all';

function clearLayers(){{ layers.forEach(l=>map.removeLayer(l)); layers=[]; }}

function setView(v){{
  currentView = v;
  ['btn_all','btn_sionna'].forEach(id=>document.getElementById(id).classList.remove('active'));
  document.getElementById(v==='all'?'btn_all':'btn_sionna').classList.add('active');
  refresh();
}}

function refresh(){{
  clearLayers();
  const showTrain  = document.getElementById('chk_train').checked;
  const showVal    = document.getElementById('chk_val').checked;
  const showTypeA  = document.getElementById('chk_typeA').checked;
  const showTypeB  = document.getElementById('chk_typeB').checked;
  const showAmbig  = document.getElementById('chk_ambig').checked;
  const showTowers = document.getElementById('chk_towers').checked;
  const sionnaOnly = document.getElementById('chk_sionna_only').checked;

  const pts = ALL_POINTS.filter(p => {{
    if (sionnaOnly && !p.sio) return false;
    if (currentView === 'sionna' && !p.sio) return false;
    if (p.gap === 'TypeA') return showTypeA;
    if (p.gap === 'TypeB') return showTypeB;
    if (p.gap === 'Ambiguous') return showAmbig;
    if (p.train && !showTrain) return false;
    if (!p.train && !showVal) return false;
    return true;
  }});

  pts.forEach(p => {{
    const opacity = p.train ? 0.85 : 0.35;
    const r = (p.gap !== 'Unflagged') ? 5 : 3;
    const m = L.circleMarker([p.lat, p.lon], {{
      radius: r,
      color: 'transparent', weight: 0,
      fillColor: p.color,
      fillOpacity: opacity
    }}).bindPopup(
      `<b>${{p.device}}</b> (Op${{p.op}})<br>Split: ${{p.split}}<br>Type: ${{p.gap}}<br>Sionna: ${{p.sio?'✅':'❌'}}`
    );
    m.addTo(map); layers.push(m);
  }});

  if (showTowers) {{
    TOWERS.forEach(t => {{
      const col = t.op===1 ? '#e53935' : '#e65100';
      const m = L.marker([t.lat,t.lon], {{icon: L.divIcon({{
        html:`<div style="background:${{col}};width:8px;height:8px;border:1.5px solid #fff;border-radius:1px"></div>`,
        iconSize:[8,8],iconAnchor:[4,4]
      }})}}).bindPopup(`Tower Op${{t.op}}`);
      m.addTo(map); layers.push(m);
    }});
  }}
}}

refresh();
</script>
</body>
</html>"""

out_path = HERE / "full_split_map.html"
out_path.write_text(html, encoding="utf-8")
print(f"\nWritten: {out_path}")
print(f"Points in map: {len(points):,}")
