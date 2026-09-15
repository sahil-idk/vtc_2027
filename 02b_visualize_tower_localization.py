"""
02b_visualize_tower_localization.py
--------------------------------------
Companion to 02_estimate_towers_from_data.py -- makes the Weighted Centroid
Localization (WCL) process visible on a real map, instead of just numbers.

WHAT THIS SHOWS, AND WHY IT'S USEFUL
---------------------------------------------------------------------------
02_estimate_towers_from_data.py already computed everything this script
needs: for each cell tower, a set of real GPS fixes (split into
localization/validation groups) and an estimated tower position. This
script doesn't recompute anything -- it just reads those existing outputs
and draws them on an actual OpenStreetMap basemap (so real roads are
visible), so you can SEE:
  - the vehicle's real GPS trace hugging the road network
  - each fix as a circle, colored by localization/validation group and
    sized by how much weight it contributed (bigger circle = stronger
    RSRP = pulled the estimate more towards itself)
  - the resulting estimated tower position as a star marker
  - a dashed circle at the weighted_spread_m radius, showing how tightly
    (or loosely) the fixes clustered around the estimate

This is purely a visualization layer on top of already-computed data --
it changes nothing about the estimation itself.

PREREQUISITES: run 02_estimate_towers_from_data.py first (this script
reads gate2_testbed/cellular_dataframe_with_tower_groups.csv and
gate2_testbed/towers_operator{op}_estimated.csv, which that script
produces).

Run:
    python 02b_visualize_tower_localization.py --operator 1
    python 02b_visualize_tower_localization.py --operator 1 --cell-identity 12345
"""

from __future__ import annotations
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_DIR = Path("gate2_testbed")
CLEANED_CSV = OUTPUT_DIR / "cellular_dataframe_with_tower_groups.csv"
CELL_ID_COLS = ["operator", "PCell_MCC", "PCell_MNC", "PCell_TAC", "PCell_Cell_Identity"]

# How many of the operator's busiest towers (by total row count) to include
# on the map by default, if no specific --cell-identity is given. Each gets
# its own toggleable layer, so the map stays readable even with several.
# Some towers have thousands of fixes -- plotting all of them makes the
# map sluggish and visually cluttered without adding real insight (the
# WCL estimate itself still used every row; this only affects what gets
# DRAWN). Cap the number of fixes actually plotted per tower, sampling
# down if there are more than this.
MAX_FIXES_TO_PLOT_PER_TOWER = 400

TOP_N_TOWERS = 5


def build_map_html(towers_to_plot: list[dict], center_lat: float, center_lon: float) -> str:
    """Builds a single self-contained HTML file with an interactive Leaflet
    map. `towers_to_plot` is a list of dicts, one per tower, each containing
    its estimated position/spread plus every fix (lat, lon, rsrp, group)
    that belongs to it.
    """
    data_json = json.dumps(towers_to_plot)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Tower localization on the road network</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
  body {{ margin: 0; font-family: sans-serif; }}
  #map {{ height: 100vh; width: 100%; }}
  .legend {{
    position: absolute; top: 10px; right: 10px; z-index: 1000;
    background: white; padding: 10px 14px; border-radius: 6px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 13px; line-height: 1.6;
  }}
  .legend .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }}
  .legend h4 {{ margin: 0 0 6px; font-size: 14px; }}
</style>
</head>
<body>
<div id="map"></div>
<div class="legend">
  <h4>Tower localization (WCL)</h4>
  <div><span class="dot" style="background:#1f77b4"></span>localization fix</div>
  <div><span class="dot" style="background:#2ca02c"></span>validation fix</div>
  <div><span class="dot" style="background:#d62728"></span>estimated tower</div>
  <div style="margin-top:6px; color:#666;">circle size = signal weight<br>dashed ring = weighted spread</div>
</div>
<script>
const towers = {data_json};

const map = L.map('map').setView([{center_lat}, {center_lon}], 15);
L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}}).addTo(map);

const groupColors = {{ localization: '#1f77b4', validation: '#2ca02c' }};
const layerControl = {{}};

towers.forEach((tower, idx) => {{
  const layerGroup = L.layerGroup();

  // Each real GPS fix, sized by its RSRP-derived weight (normalized to a
  // readable pixel radius range) and colored by which group it belongs to.
  const maxWeight = Math.max(...tower.fixes.map(f => f.weight));
  tower.fixes.forEach(fix => {{
    const radius = 3 + 9 * (fix.weight / maxWeight);
    L.circleMarker([fix.lat, fix.lon], {{
      radius: radius,
      color: groupColors[fix.group],
      fillColor: groupColors[fix.group],
      fillOpacity: 0.55,
      weight: 1
    }}).bindPopup(
      `RSRP: ${{fix.rsrp.toFixed(1)}} dBm<br>Group: ${{fix.group}}`
    ).addTo(layerGroup);
  }});

  // The estimated tower position itself, as a distinct star-like marker.
  const towerIcon = L.divIcon({{
    html: '<div style="font-size:22px;color:#d62728;">&#9733;</div>',
    className: '', iconSize: [22, 22], iconAnchor: [11, 11]
  }});
  L.marker([tower.tower_lat, tower.tower_lon], {{icon: towerIcon}})
    .bindPopup(
      `Estimated tower position<br>` +
      `Cell Identity: ${{tower.cell_identity}}<br>` +
      `Confidence: ${{tower.position_confidence}}<br>` +
      `RSRP-distance correlation: ${{tower.correlation}}<br>` +
      `Localization rows: ${{tower.n_localization_rows}}`
    ).addTo(layerGroup);

  // Dashed circle showing the weighted_spread_m diagnostic -- how far,
  // on average, the contributing fixes were from the final estimate.
  L.circle([tower.tower_lat, tower.tower_lon], {{
    radius: tower.weighted_spread_m,
    color: '#888', weight: 1, dashArray: '4 4', fill: false
  }}).addTo(layerGroup);

  layerGroup.addTo(map);
  layerControl['Cell ' + tower.cell_identity + ' (' + tower.position_confidence + ')'] = layerGroup;
}});

L.control.layers(null, layerControl, {{collapsed: false}}).addTo(map);
</script>
</body>
</html>
"""


def select_towers(op: int, cell_identity: int | None) -> pd.DataFrame:
    towers = pd.read_csv(OUTPUT_DIR / f"towers_operator{op}_estimated.csv")
    if cell_identity is not None:
        selected = towers[towers["PCell_Cell_Identity"] == cell_identity]
        if selected.empty:
            raise SystemExit(f"Cell identity {cell_identity} not found in "
                              f"towers_operator{op}_estimated.csv")
        return selected
    # Default: the busiest towers by total row count (localization + validation),
    # since these have the most data behind them and make the clearest example.
    towers["total_rows"] = towers["n_localization_rows"] + towers["n_validation_rows"]
    return towers.sort_values("total_rows", ascending=False).head(TOP_N_TOWERS)


def main(op: int, cell_identity: int | None):
    print(f"Loading tower estimates and dataset for operator {op} ...")
    selected_towers = select_towers(op, cell_identity)
    df = pd.read_csv(CLEANED_CSV, low_memory=False)
    df_op = df[df["operator"] == op]

    towers_to_plot = []
    all_lats, all_lons = [], []

    for _, t in selected_towers.iterrows():
        mask = (
            (df_op["PCell_MCC"] == t["PCell_MCC"]) &
            (df_op["PCell_MNC"] == t["PCell_MNC"]) &
            (df_op["PCell_TAC"] == t["PCell_TAC"]) &
            (df_op["PCell_Cell_Identity"] == t["PCell_Cell_Identity"]) &
            (df_op["tower_estimate_group"].isin(["localization", "validation"]))
        )
        rows = df_op[mask].dropna(subset=["Latitude", "Longitude", "PCell_RSRP_max"])
        n_total_fixes = len(rows)
        if n_total_fixes > MAX_FIXES_TO_PLOT_PER_TOWER:
            rows = rows.sample(n=MAX_FIXES_TO_PLOT_PER_TOWER, random_state=42)

        fixes = []
        for _, row in rows.iterrows():
            weight = 10 ** (row["PCell_RSRP_max"] / 10.0)
            fixes.append({
                "lat": float(row["Latitude"]), "lon": float(row["Longitude"]),
                "rsrp": float(row["PCell_RSRP_max"]),
                "group": row["tower_estimate_group"], "weight": weight,
            })
            all_lats.append(row["Latitude"])
            all_lons.append(row["Longitude"])

        towers_to_plot.append({
            "cell_identity": int(t["PCell_Cell_Identity"]),
            "tower_lat": float(t["tower_lat"]), "tower_lon": float(t["tower_lon"]),
            "weighted_spread_m": float(t["weighted_spread_m"]),
            "position_confidence": t["position_confidence"],
            "correlation": t["rsrp_distance_correlation"],
            "n_localization_rows": int(t["n_localization_rows"]),
            "fixes": fixes,
        })
        print(f"  Cell {int(t['PCell_Cell_Identity'])}: {len(fixes)} fixes plotted "
              f"(of {n_total_fixes} total) ({t['position_confidence']} confidence)")

    center_lat = float(np.mean(all_lats))
    center_lon = float(np.mean(all_lons))

    html = build_map_html(towers_to_plot, center_lat, center_lon)
    out_path = OUTPUT_DIR / f"tower_localization_map_operator{op}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nSaved map -> {out_path}")
    print("Open this file in a browser to explore it (toggle towers on/off "
          "using the layer control in the top-right).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--operator", type=int, choices=[1, 2], required=True)
    ap.add_argument("--cell-identity", type=int, default=None,
                     help="Visualize one specific cell instead of the busiest few.")
    args = ap.parse_args()
    main(args.operator, args.cell_identity)
