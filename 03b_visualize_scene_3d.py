"""
03b_visualize_scene_3d.py
-----------------------------
Companion to 03_build_sionna_scene.py -- renders the ACTUAL reconstructed
3D scene (real extruded building footprints, ground plane, and estimated
tower positions) as an interactive, freely rotatable/zoomable 3D view in
the browser, using Three.js.

WHY THIS EXISTS: 03_build_sionna_scene.py writes out a Mitsuba scene file
(scene.xml) plus a combined building mesh (scene_buildings.obj) for
Sionna's ray tracer to consume -- but there was previously no way to
actually LOOK at that geometry and confirm it looks right (real building
shapes, correct heights, towers in sensible positions) rather than just
trusting the math. This script reads those exact same output files and
displays them.

PREREQUISITE: run 03_build_sionna_scene.py for the operator you want to
view first (this script does not run Sionna or build any new geometry --
it only visualizes what 03 already produced).

This script must be run from the SAME directory as 03_build_sionna_scene.py,
since it imports that script's coordinate-conversion and bounding-box
functions directly, to guarantee the buildings, ground, and towers all
line up in EXACTLY the same local coordinate frame that was used when the
scene was actually built (recomputing that logic independently, even
slightly differently, would risk a subtle misalignment between the
buildings and the towers in the resulting picture).

Run:
    python 03b_visualize_scene_3d.py --operator 1
"""

from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_DIR = Path("gate2_testbed")


def load_sionna_script_module():
    """Dynamically imports 03_build_sionna_scene.py as a plain module (not
    running its __main__ block), so we can reuse its EXACT
    latlon_to_local_xy() and select_subarea_bbox() functions -- guarantees
    the same coordinate frame the actual scene was built in, rather than
    risking a subtly different reimplementation drifting out of sync.
    """
    script_path = Path(__file__).parent / "03_build_sionna_scene.py"
    if not script_path.exists():
        raise SystemExit(
            "Could not find 03_build_sionna_scene.py in the same directory as "
            "this script. Run this from your dt-sionna-rt project folder."
        )
    spec = importlib.util.spec_from_file_location("sionna_scene_module", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # safe: the file's Sionna imports are all
                                   # INSIDE run_sionna(), not at module level,
                                   # so this doesn't require Sionna installed
    return mod


def parse_obj(obj_path: Path) -> tuple[list, list]:
    """Minimal Wavefront OBJ parser -- just enough for the simple vertex +
    triangle-face files build_scene_xml() produces (no normals, no
    textures, no material groups to worry about).
    """
    vertices = []
    faces = []
    for line in obj_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            _, x, y, z = line.split()
            vertices.append([float(x), float(y), float(z)])
        elif line.startswith("f "):
            _, i, j, k = line.split()
            # OBJ face indices are 1-based; convert to 0-based for JS/Three.js
            faces.append([int(i) - 1, int(j) - 1, int(k) - 1])
    return vertices, faces


def build_viewer_html(vertices: list, faces: list, towers: list, title: str) -> str:
    vertices_json = json.dumps(vertices)
    faces_json = json.dumps(faces)
    towers_json = json.dumps(towers)

    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ margin: 0; overflow: hidden; font-family: sans-serif; background: #cfe0ea; }}
  #info {{
    position: absolute; top: 10px; left: 10px; z-index: 10;
    background: white; padding: 10px 14px; border-radius: 6px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 13px; line-height: 1.6;
  }}
  .dot {{ display:inline-block; width:10px; height:10px; border-radius:50%; margin-right:6px; }}
</style>
</head>
<body>
<div id="info">
  <strong>{title}</strong><br>
  <span class="dot" style="background:#8a8a8a"></span>reconstructed buildings (real footprints)<br>
  <span class="dot" style="background:#d62728"></span>estimated tower position<br>
  <span style="color:#666">drag to orbit &middot; scroll to zoom &middot; right-drag to pan</span>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<script>
const buildingVerts = {vertices_json};
const buildingFaces = {faces_json};
const towers = {towers_json};

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xcfe0ea);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth/window.innerHeight, 0.1, 5000);
const renderer = new THREE.WebGLRenderer({{antialias: true}});
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

// Lighting -- ambient for base visibility, directional for shading so the
// extruded building shapes and heights are actually visible as 3D, not flat.
scene.add(new THREE.AmbientLight(0xffffff, 0.55));
const sun = new THREE.DirectionalLight(0xffffff, 0.7);
sun.position.set(300, 500, 400);
scene.add(sun);

// Ground plane, matching the scale used in the actual Sionna scene.
const groundGeo = new THREE.PlaneGeometry(2000, 2000);
const groundMat = new THREE.MeshStandardMaterial({{color: 0x9fae9f, side: THREE.DoubleSide}});
const ground = new THREE.Mesh(groundGeo, groundMat);
ground.rotation.x = -Math.PI / 2;  // Three.js planes are XY by default; rotate flat onto XZ
scene.add(ground);

// The actual reconstructed building geometry -- built directly from the
// same vertex/face data written into scene_buildings.obj by
// 03_build_sionna_scene.py. Three.js uses a Y-up coordinate convention,
// while our scene data is Z-up (Z = height) -- swap Y and Z per vertex so
// "up" in the 3D view matches real building height, not a sideways axis.
const geo = new THREE.BufferGeometry();
const posArray = new Float32Array(buildingVerts.length * 3);
buildingVerts.forEach((v, idx) => {{
  posArray[idx*3+0] = v[0];   // x stays x
  posArray[idx*3+1] = v[2];   // z (height) becomes Three.js's up-axis
  posArray[idx*3+2] = v[1];   // y becomes Three.js's depth axis
}});
geo.setAttribute('position', new THREE.BufferAttribute(posArray, 3));
geo.setIndex(buildingFaces.flat());
geo.computeVertexNormals();

const buildingMat = new THREE.MeshStandardMaterial({{
  color: 0x8a8a8a, side: THREE.DoubleSide, flatShading: true
}});
const buildingMesh = new THREE.Mesh(geo, buildingMat);
scene.add(buildingMesh);

// Estimated tower positions, as red spheres at their real assumed height.
towers.forEach(t => {{
  const sphereGeo = new THREE.SphereGeometry(4, 16, 16);
  const sphereMat = new THREE.MeshStandardMaterial({{color: 0xd62728}});
  const sphere = new THREE.Mesh(sphereGeo, sphereMat);
  sphere.position.set(t.x, t.height, t.y);  // same Y/Z swap as buildings above
  scene.add(sphere);
  // A thin vertical line from ground to tower, so its height is visually
  // obvious even when the sphere itself is far from the camera.
  const lineGeo = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(t.x, 0, t.y), new THREE.Vector3(t.x, t.height, t.y)
  ]);
  scene.add(new THREE.Line(lineGeo, new THREE.LineBasicMaterial({{color: 0xd62728}})));
}});

// Camera start position: looking down at an angle over the whole scene,
// roughly centred, far enough back to see the full ~900m-ish extent.
camera.position.set(200, 250, 400);
camera.lookAt(0, 0, 0);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.target.set(0, 10, 0);
controls.update();

window.addEventListener('resize', () => {{
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
}});

function animate() {{
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}}
animate();
</script>
</body>
</html>
"""


def main(op: int):
    mod = load_sionna_script_module()

    scene_dir = OUTPUT_DIR / f"scene_operator{op}"
    obj_path = scene_dir / "scene_buildings.obj"
    if not obj_path.exists():
        raise SystemExit(f"{obj_path} not found -- run "
                          f"'python 03_build_sionna_scene.py --operator {op}' first.")

    print(f"Loading building mesh from {obj_path} ...")
    vertices, faces = parse_obj(obj_path)
    print(f"  {len(vertices)} vertices, {len(faces)} triangles")

    # Recompute the SAME bounding box / local-coordinate origin that was
    # used when this scene was actually built, so towers line up correctly
    # with the buildings. This mirrors run_for_operator()'s own logic
    # exactly, using the real functions imported from 03_build_sionna_scene.py.
    df = pd.read_csv(mod.CLEANED_CSV, low_memory=False)
    df_op = df[(df["operator"] == op) & df["Latitude"].notna() & df["Longitude"].notna()].copy()
    clean_mask = ~df_op[mod.RANGE_FLAG_COLS].any(axis=1)
    df_op_clean = df_op[clean_mask]
    df_val = df_op_clean[df_op_clean["tower_estimate_group"] == "validation"]
    bbox = mod.select_subarea_bbox(df_val)

    towers_df = pd.read_csv(OUTPUT_DIR / f"towers_operator{op}_estimated.csv")
    towers_df = towers_df.dropna(subset=["tower_lat", "tower_lon"])

    # IMPORTANT FILTER: towers_operator{op}_estimated.csv lists EVERY tower
    # estimated anywhere across this operator's whole territory (potentially
    # kilometres apart, spanning the entire city) -- but the 3D scene we're
    # visualizing only reconstructed buildings for one small ~900m-wide
    # sub-area. Plotting every tower unconditionally would place most of
    # them far outside the small patch of real buildings, making the scene
    # look like two disconnected pieces of geometry floating apart from
    # each other. Restrict to towers whose real lat/lon actually falls
    # inside the same bounding box the buildings were fetched for.
    n_total_towers = len(towers_df)
    in_bbox_mask = (
        towers_df["tower_lat"].between(bbox["min_lat"], bbox["max_lat"]) &
        towers_df["tower_lon"].between(bbox["min_lon"], bbox["max_lon"])
    )
    towers_df = towers_df[in_bbox_mask]
    print(f"  Restricting to towers within the visualized area: "
          f"{len(towers_df)} / {n_total_towers} towers fall inside this bbox")

    tx, ty = mod.latlon_to_local_xy(towers_df["tower_lat"], towers_df["tower_lon"],
                                     bbox["origin_lat"], bbox["origin_lon"])
    tx, ty = list(tx), list(ty)
    print(f"  {len(tx)} tower positions plotted at height {mod.TOWER_HEIGHT_M}m")

    # RECENTERING FIX: select_subarea_bbox()'s "origin_lat/origin_lon" is
    # the MEDIAN of the operator's ENTIRE validation dataset -- not the
    # centre of this specific small visualized sub-area. That's fine for
    # the actual Sionna run (every position -- buildings, receivers,
    # towers -- is shifted by the exact same amount, so relative distances,
    # and therefore ray-tracing results, are completely unaffected). But it
    # means everything can end up sitting thousands of metres away from
    # Three.js's world origin (0,0,0), while our ground plane is fixed at
    # that literal origin -- exactly the "disconnected floating geometry"
    # bug. Fix: recentre PURELY FOR VISUALIZATION on the buildings' own
    # bounding-box centre, so the scene always renders near (0,0,0)
    # regardless of where the underlying origin_lat/origin_lon happens to
    # fall. This only affects this picture -- it does not touch
    # select_subarea_bbox() itself or anything the real Sionna run uses.
    verts_arr = np.array(vertices)
    center_x = (verts_arr[:, 0].min() + verts_arr[:, 0].max()) / 2.0
    center_y = (verts_arr[:, 1].min() + verts_arr[:, 1].max()) / 2.0
    print(f"  Recentering visualization on buildings' bounding-box centre "
          f"(offset was {center_x:.0f}m, {center_y:.0f}m from world origin)")

    vertices = [(vx - center_x, vy - center_y, vz) for vx, vy, vz in vertices]
    towers = [{"x": float(x - center_x), "y": float(y - center_y), "height": mod.TOWER_HEIGHT_M}
              for x, y in zip(tx, ty)]

    html = build_viewer_html(vertices, faces, towers,
                              title=f"Reconstructed 3D scene -- Operator {op}")
    out_path = OUTPUT_DIR / f"scene_3d_viewer_operator{op}.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nSaved -> {out_path}")
    print("Open this file in a browser to explore the actual reconstructed geometry.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--operator", type=int, choices=[1, 2], required=True)
    args = ap.parse_args()
    main(args.operator)
