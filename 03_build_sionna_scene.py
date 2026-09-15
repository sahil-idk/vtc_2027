"""
03_build_sionna_scene.py  (v3 -- diffraction enabled, heavily commented)
---------------------------------------------------------------------------
WHAT THIS SCRIPT IS FOR, IN THE CONTEXT OF THE DIGITAL TWIN ARCHITECTURE
---------------------------------------------------------------------------
This script is "Gate 2" of the DT-QUEST two-gate architecture: the
independent physics oracle that checks whether the digital twin we could
build from this dataset actually reproduces reality, using a completely
different method (ray tracing over real 3D geometry) than the dataset
itself was collected with. Gate 1 (separate scripts) checks whether the
*input data* is trustworthy. Gate 2 checks whether a *twin built from that
data* would actually work. The two are deliberately independent so that
Gate 2's verdict isn't circular -- it doesn't just re-derive the same
numbers the dataset already contains, it re-computes them from first-
principles physics (Maxwell's equations approximated via geometric ray
tracing) and geography (real building footprints from OpenStreetMap).

Because this is meant to stand in for "how would a real physical radio
signal actually travel through this city block", the RECONSTRUCTION HAS TO
BE PHYSICALLY COMPLETE -- meaning we must not throw away entire categories
of real propagation behaviour just because they're more expensive to
compute. This version fixes exactly that gap: earlier versions only traced
line-of-sight (LOS) paths and specular ("mirror-like") reflections off
building walls. Real radio waves also DIFFRACT -- they bend around sharp
edges like building corners and rooftops, which is how a phone deep inside
a building's radio "shadow" (no straight line to the tower, no clean
mirror-bounce path either) still receives *any* signal at all in real life.
Without diffraction enabled, every receiver in a genuinely shadowed spot
gets zero valid paths and is silently excluded from the results -- which
quietly biases the whole validation towards only the "easy", well-connected
locations. That is not an acceptable simplification for a digital twin that
is supposed to represent the real radio-coverage picture, including the
weak spots -- the weak spots are often the ones that matter most for
infrastructure decisions (e.g. "do we need another RSU/small-cell here?").
So: diffraction is now switched on, and this comment block, plus the
comments throughout the file below, explain exactly what that changes and
why every other line of this pipeline exists.

---------------------------------------------------------------------------
CHANGES IN THIS VERSION (v3) VS THE PREVIOUS ONE (v2)
---------------------------------------------------------------------------
  - Diffraction is now enabled in the ray-tracing solver call (see the
    `run_sionna()` function below, in the `solver(...)` call). This lets
    Sionna find valid propagation paths for receivers that have no direct
    line-of-sight and no clean specular-reflection path either -- exactly
    the "shadowed" locations that were previously all being marked as
    "zero valid paths" and dropped from the comparison.
  - `max_depth` (the maximum number of "bounces"/interactions a traced ray
    is allowed before Sionna gives up on that path) is raised from 5 to 6,
    because a physically realistic diffracted path often involves bending
    around one edge AND THEN reflecting off a nearby wall before reaching
    the receiver -- that's two interactions, and the solver needs a depth
    budget large enough to find such combined paths.
  - Every function and most individual lines now carry a detailed comment
    explaining not just *what* the line does mechanically, but *why* it is
    needed and what would go wrong if it were removed or misconfigured.
    The goal is that someone with no prior Sionna/ray-tracing/RF background
    can read this file top-to-bottom and understand the full pipeline.

---------------------------------------------------------------------------
CHANGES CARRIED OVER FROM v2 (still true in this version)
---------------------------------------------------------------------------
  - Uses the modern, standalone `sionna-rt` package (PathSolver API) rather
    than the older `sionna.rt` module with `scene.compute_paths()`.
  - Fetches OpenStreetMap (OSM) building geometry directly from the public
    Overpass API -- no manual Blender/Blosm export step required. Buildings
    are approximated as simple extruded rectangular boxes (their real,
    possibly irregular footprint is replaced by its bounding rectangle),
    which is a deliberately coarse first-pass approximation of the true
    3D city geometry -- accurate enough to get real, physically meaningful
    numbers quickly. Refining this to true building footprints/roof shapes
    is a natural follow-up once the basic pipeline is validated.
  - Uses OUR OWN OpenCelliD-geolocated tower positions (produced by
    02_geolocate_towers.py) as the transmitter locations, rather than
    guessing a tower's location from "wherever the strongest signal sample
    in the dataset happened to be" (which would be circular -- it would
    validate the dataset using a position derived FROM the dataset).
  - Automatically picks one focused, manageably-sized sub-area of the city
    (the densest cluster of receiver points, plus a margin) instead of
    trying to build a 3D scene and ray-trace the entire city at once,
    which would be extremely slow and is unnecessary for validation
    purposes.

---------------------------------------------------------------------------
PREREQUISITES (software you need installed before running this)
---------------------------------------------------------------------------
  pip install sionna-rt requests

  `sionna-rt` bundles its own compatible versions of Mitsuba (the physical
  rendering/ray-tracing engine underneath Sionna) and Dr.Jit (the
  just-in-time GPU/CPU compiler Mitsuba is built on) -- do NOT separately
  pip install a plain `sionna` package, since that is the older, different,
  TensorFlow-based package and the two will conflict if both are present.
  If you previously installed that older package (e.g. from an earlier
  version of this project's environment.yml), remove it first:
      pip uninstall sionna tensorflow
      pip install sionna-rt

  Internet access is required for the FIRST run against a given city
  bounding box, because this script queries the public Overpass API for
  building data. After that first successful query, the raw result is
  cached to disk (see CACHE_DIR below) and reused automatically -- no
  network access needed on subsequent runs for the same area.
---------------------------------------------------------------------------

HOW TO RUN THIS SCRIPT:
    python 03_build_sionna_scene.py --operator 1
    python 03_build_sionna_scene.py --operator 2

    Optional: --n-sample <integer> controls how many receiver points get
    ray-traced (default defined below as N_SAMPLE_POINTS). Start small
    while validating the pipeline; increase once you trust the output.
"""

# `from __future__ import annotations` lets us write type hints like
# `list[dict]` (using the built-in lowercase `list`/`dict`) even on Python
# versions where that syntax wasn't natively supported yet. It doesn't
# change the program's behaviour at all -- it only affects how type hints
# are interpreted, purely for readability/tooling purposes.
from __future__ import annotations

# `argparse` lets this script accept command-line flags such as
# `--operator 1` and `--n-sample 500` when you run it from a terminal.
import argparse
# `hashlib` is used purely to turn a bounding-box's coordinates into a
# short, filesystem-safe cache filename (see fetch_osm_buildings below).
import hashlib
# `math` gives us basic trigonometric/logarithm functions (cosine, log10)
# that we need for coordinate conversion and converting linear radio power
# into decibels.
import math
# `time` is used only to pause briefly between retries when a network
# request fails, and to be polite to the free public Overpass servers.
import time
# The Python standard library's built-in XML parser. OpenStreetMap's
# Overpass API can return data in XML format, and this lets us read it
# without needing any extra third-party XML library installed.
import xml.etree.ElementTree as ET
# `Path` is a modern, convenient way to work with filesystem paths (e.g.
# joining directories, checking if a file exists) instead of raw strings.
from pathlib import Path

# NumPy: fast numerical array operations (we use it for vectorised
# trigonometry when converting many latitude/longitude points at once).
import numpy as np
# Pandas: the DataFrame library used throughout this whole project for
# loading and filtering the tabular V2X measurement data.
import pandas as pd
# The `requests` library lets Python make HTTP calls -- here, to query the
# Overpass API for OpenStreetMap building data.
import requests

# ---------------------------------------------------------------------------
# CONFIGURATION CONSTANTS
# Everything in this block is a "knob" you might reasonably want to change
# without touching the logic of the script itself. Each one is explained.
# ---------------------------------------------------------------------------

# The Gate-1-cleaned dataset (produced by gate1_cleaning_v2.py earlier in
# this pipeline). This is our source of receiver positions (real GPS
# coordinates the measurement vehicle was at) and of which cell tower each
# measurement was actually connected to at that moment.
OUTPUT_DIR = Path("gate2_testbed")
CLEANED_CSV = OUTPUT_DIR / "cellular_dataframe_with_tower_groups.csv"

# When picking which part of the city to build a 3D scene for, we first
# divide the whole area into square grid cells of this size (in metres) and
# count how many receiver points fall in each cell. FOCUS_GRID_M controls
# the resolution of that counting grid -- smaller values find a more
# tightly localized "hotspot", larger values average over a wider area.
FOCUS_GRID_M = 150.0

# Once we've found the single busiest grid cell (the one with the most
# receiver points in it), we build our actual simulated area as a square of
# this size (in metres), centred on that busy cell. This is the "sub-area"
# whose buildings we will fetch and whose receivers we will ray-trace.
# 900m is a deliberately modest first-pass size: large enough to contain a
# meaningful chunk of real urban geometry, small enough that the OSM query
# and the resulting 3D scene stay fast to fetch and simulate.
FOCUS_SPAN_M = 900.0

# We add this many extra metres of margin AROUND the FOCUS_SPAN_M square
# when fetching building data. Why extra margin? A ray can still be blocked
# or reflected by a building that is physically OUTSIDE our exact receiver
# area but close to its edge -- without this margin, a tower or receiver
# right at the boundary might be missing nearby buildings that would
# realistically affect its signal.
BBOX_MARGIN_M = 250.0

# How many individual receiver points to actually ray-trace in one run.
# Ray-tracing every single measurement row in the dataset (hundreds of
# thousands of rows) would be extremely slow, and is unnecessary for
# validating whether the pipeline and the physics numbers are trustworthy.
# Start with a small number while debugging; raise it once you trust the
# results, for a statistically stronger final comparison.
N_SAMPLE_POINTS = 300

# ---------------------------------------------------------------------------
# RAY-TRACING PHYSICS KNOBS
# These control which propagation phenomena the solver models, and how hard
# it searches for valid paths. Turning more of these on (or raising
# MAX_RAY_DEPTH) generally finds MORE valid paths per receiver -- reducing
# the "zero valid paths" dropout rate -- at the cost of slower runtime per
# receiver. This is the main lever for the "not every receiver gets a valid
# path" issue: rather than changing any data row, tune these to make the
# RECONSTRUCTION more physically complete.
# ---------------------------------------------------------------------------

# Maximum number of interactions (bounces/diffractions) a traced ray path
# may have before the solver stops looking for more paths in that
# direction. Higher = more thorough (finds more complex, indirect paths to
# shadowed receivers) but slower. Can be overridden with --max-depth.
MAX_RAY_DEPTH = 6

# Direct, unobstructed line-of-sight paths. Leave this on -- it's the
# cheapest and most important propagation mechanism to include.
ENABLE_LOS = True

# "Mirror-like" reflections off flat surfaces (e.g. a building wall).
ENABLE_SPECULAR_REFLECTION = True

# Radio waves bending around sharp edges (building corners, rooflines).
# This is what lets receivers with no direct view AND no clean mirror-
# bounce still get a valid path -- the fix for the earlier "zero valid
# paths" over-exclusion. Can be overridden with --no-diffraction.
ENABLE_DIFFRACTION = True

# Scattering in many directions off rough/uneven surfaces (real building
# facades are rarely perfectly flat). This is a REAL additional physical
# mechanism we are currently choosing not to model, mainly for speed --
# turning it on is a reasonable next thing to try if the zero-path rate is
# still too high after enabling diffraction, since it can also recover
# paths to otherwise-shadowed receivers, via a different mechanism than
# diffraction. Can be overridden with --diffuse-reflection.
ENABLE_DIFFUSE_REFLECTION = False

# A ray physically passing THROUGH a material (e.g. through a window into
# a building interior). Left off -- we model every building as fully
# opaque, the standard assumption for outdoor macro-cell propagation
# studies (we are not attempting to model indoor penetration here).
ENABLE_REFRACTION = False

# Below this total received linear power, we treat the link as "no valid
# path found" and record NaN rather than an artificial, very-negative dB
# value. 1e-20 is chosen to be far below any physically plausible received
# power at these frequencies/distances, so it only catches genuine
# zero-path cases, not just very weak (but real) links.
NO_PATH_LINEAR_THRESHOLD = 1e-20

# When OpenStreetMap doesn't tell us how tall a building actually is (many
# buildings in the real OSM database are missing height/floor-count tags),
# we assume this height in metres as a reasonable generic urban building
# guess, rather than leaving the building with no height at all (which
# would make it physically transparent to radio waves in the simulation --
# clearly wrong).
DEFAULT_BUILDING_HEIGHT_M = 18.0

# The assumed height, in metres, at which each cell tower's antenna is
# mounted above ground. Real macro-cell antennas are typically mounted on
# rooftops or dedicated masts in this general range; we don't have the
# exact real mounting height for these specific towers, so this is a
# documented simplifying assumption, not a measured fact.
TOWER_HEIGHT_M = 25.0

# The assumed height, in metres, of the receiving antenna (i.e. the moving
# vehicle's cellular modem/antenna) above the ground. 1.5m is a standard
# assumption for a vehicle-mounted or handheld antenna in propagation
# modelling.
RECEIVER_HEIGHT_M = 1.5

# These are the Gate-1 quality-flag columns (added earlier in the pipeline
# by gate1_cleaning_v2.py) that mark a measurement's RF values as failing
# the corrected 3GPP physical-plausibility bounds. We use these flags below
# to only simulate receivers whose underlying measurement is trustworthy in
# the first place -- there is no point spending expensive ray-tracing
# compute validating against a measurement we already know is suspect.
RANGE_FLAG_COLS = [
    "FLAG_range_PCell_RSRP_max", "FLAG_range_PCell_RSRQ_max",
    "FLAG_range_PCell_RSSI_max", "FLAG_range_PCell_SNR_1",
]

# A list of public, free Overpass API endpoints (mirrors of the same
# OpenStreetMap query service, run by different volunteers/organisations).
# We try them in this order and fall back to the next one if an earlier one
# is slow, overloaded, or temporarily down -- see fetch_osm_buildings().
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

# The local folder where raw Overpass query results get saved after the
# first successful fetch for a given bounding box, so that re-running this
# script later for the SAME area doesn't need the internet again and is
# instant.
CACHE_DIR = OUTPUT_DIR / "osm_cache"


# ---------------------------------------------------------------------------
# COORDINATE HELPERS
# Real-world positions are given as latitude/longitude (degrees on a
# sphere), but Sionna's ray tracer works in a flat, local X/Y/Z metre-based
# coordinate system (like a small flat map, not a globe). These two
# functions convert back and forth between the two representations for a
# small local area, where the curvature of the Earth is negligible.
# ---------------------------------------------------------------------------
def latlon_to_local_xy(lat, lon, origin_lat, origin_lon):
    """Convert real-world latitude/longitude coordinates into a flat,
    local X/Y coordinate system measured in metres, relative to a chosen
    'origin' point (origin_lat, origin_lon) that becomes local (0, 0).

    This uses the "equirectangular" approximation: it treats the small
    patch of the Earth's surface we care about as if it were flat, which
    introduces negligible error over an area as small as ~1km across (our
    scene is only ~900m-1400m wide), but would NOT be accurate over
    hundreds of kilometres.

    Why the cosine term matters: lines of longitude get physically closer
    together as you move away from the equator (they all meet at the
    poles), so one degree of longitude corresponds to fewer real metres at
    higher latitudes. Berlin is at roughly 52.5 degrees north, so this
    correction is significant and must not be skipped -- without the
    cos(latitude) factor, east-west distances would be calculated as
    roughly 1.65x too large at Berlin's latitude.
    """
    # Accept either single numbers or whole pandas Series/arrays of
    # coordinates, and make sure NumPy can do fast vectorised math on them.
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    # 111,320 metres is the standard, widely-used approximate length of
    # one degree of latitude (or of longitude AT the equator) on Earth's
    # surface. Multiplying the longitude difference by cos(origin latitude)
    # corrects for the "longitude lines converge near the poles" effect
    # described above.
    x = (lon - origin_lon) * 111_320.0 * math.cos(math.radians(origin_lat))
    # Latitude doesn't need the cosine correction: lines of latitude are
    # (very nearly) equally spaced from equator to pole, so one degree of
    # latitude is approximately 111,320 metres everywhere on Earth.
    y = (lat - origin_lat) * 111_320.0
    return x, y


def local_xy_to_latlon(x, y, origin_lat, origin_lon):
    """The exact inverse of latlon_to_local_xy() above: given a flat local
    X/Y position in metres (relative to the same origin point), recover
    the real-world latitude/longitude. Used when we've computed a bounding
    box in convenient local metres and need to turn its corners back into
    real coordinates to actually query OpenStreetMap (which speaks in
    latitude/longitude, not metres).
    """
    lat = origin_lat + (y / 111_320.0)
    lon = origin_lon + (x / (111_320.0 * math.cos(math.radians(origin_lat))))
    return float(lat), float(lon)


# ---------------------------------------------------------------------------
# STEP A: pick one focused, manageably-sized sub-area to actually simulate
# ---------------------------------------------------------------------------
def select_subarea_bbox(df: pd.DataFrame) -> dict:
    """Given all of one operator's cleaned receiver rows (each with a real
    GPS Latitude/Longitude), automatically find the single busiest ~900m
    square patch of the city and return its bounding box (plus a safety
    margin). We do this instead of simulating the whole city because:
      (a) fetching and ray-tracing a whole city's worth of buildings would
          be extremely slow and unnecessary for a first validation pass,
      (b) picking the DENSEST cluster of real measurements maximizes how
          many receiver points we can usefully compare against the physics
          oracle from a single, reasonably-sized 3D scene.
    """
    # Pick the median GPS position of all the rows as our local coordinate
    # system's origin point. Using the median (rather than e.g. the very
    # first row) makes this choice robust to a handful of stray/outlier
    # GPS points that might otherwise skew the origin to an odd location.
    origin_lat = float(df["Latitude"].median())
    origin_lon = float(df["Longitude"].median())

    # Convert every receiver's real GPS position into flat local metres,
    # relative to that origin, so we can do simple grid arithmetic on them.
    x, y = latlon_to_local_xy(df["Latitude"], df["Longitude"], origin_lat, origin_lon)

    # Work on a copy so we don't accidentally modify the caller's DataFrame
    # (a defensive habit -- functions generally shouldn't have surprising
    # side effects on data the caller passed in).
    df = df.copy()

    # Assign every receiver point to a square grid cell of size
    # FOCUS_GRID_M, by dividing its local X/Y position by the cell size and
    # rounding down. Two points with the same (grid_x, grid_y) fall in the
    # same physical square patch of the city.
    df["grid_x"] = np.floor(x / FOCUS_GRID_M).astype(int)
    df["grid_y"] = np.floor(y / FOCUS_GRID_M).astype(int)

    # Count how many receiver rows fall into each (grid_x, grid_y) cell,
    # sort so the busiest cell is first, and take that top row. This finds
    # the single most heavily-sampled ~150m patch of the whole dataset for
    # this operator.
    top_cell = (df.groupby(["grid_x", "grid_y"]).size()
                .sort_values(ascending=False).reset_index(name="count").iloc[0])

    # Convert that winning grid cell's index back into a real local X/Y
    # centre point (adding 0.5 cells to get the CENTRE of the cell, not its
    # corner).
    cx = (int(top_cell["grid_x"]) + 0.5) * FOCUS_GRID_M
    cy = (int(top_cell["grid_y"]) + 0.5) * FOCUS_GRID_M

    # Build a square bounding box of size FOCUS_SPAN_M around that centre
    # point, then grow it further by BBOX_MARGIN_M on every side so nearby
    # buildings just outside our "official" receiver area are still
    # included in the 3D scene (see BBOX_MARGIN_M's comment above for why).
    half = FOCUS_SPAN_M / 2.0
    x_min, x_max = cx - half - BBOX_MARGIN_M, cx + half + BBOX_MARGIN_M
    y_min, y_max = cy - half - BBOX_MARGIN_M, cy + half + BBOX_MARGIN_M

    # Convert the four corners of that local-metres bounding box back into
    # real latitude/longitude, since that's the coordinate system
    # OpenStreetMap's Overpass API expects for its bounding-box queries.
    min_lat, min_lon = local_xy_to_latlon(x_min, y_min, origin_lat, origin_lon)
    max_lat, max_lon = local_xy_to_latlon(x_max, y_max, origin_lat, origin_lon)

    # Return everything downstream code will need: the chosen origin (so
    # every later coordinate conversion in this run uses the SAME local
    # coordinate system), the final lat/lon bounding box, and how many
    # receiver points landed in the winning cell (just for a human-readable
    # progress message).
    return {
        "origin_lat": origin_lat, "origin_lon": origin_lon,
        "min_lat": min(min_lat, max_lat), "max_lat": max(min_lat, max_lat),
        "min_lon": min(min_lon, max_lon), "max_lon": max(min_lon, max_lon),
        "grid_count": int(top_cell["count"]),
    }


# ---------------------------------------------------------------------------
# STEP B: fetch real building geometry for that bounding box from OSM
# ---------------------------------------------------------------------------
def fetch_osm_buildings(bbox: dict) -> list[dict]:
    """Ask the public OpenStreetMap Overpass API for every building
    footprint inside our chosen bounding box, and parse the response into a
    simple Python list of buildings (each with its outline coordinates and
    an estimated height). Results are cached to disk so repeated runs for
    the same bounding box don't need the internet again.
    """
    # Make sure the local cache folder exists (does nothing if it's
    # already there).
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Build a cache filename that's unique to this specific bounding box,
    # by hashing its four corner coordinates. Using a hash (rather than the
    # raw numbers) keeps the filename short and guaranteed filesystem-safe.
    key = f"{bbox['min_lat']:.5f}_{bbox['min_lon']:.5f}_{bbox['max_lat']:.5f}_{bbox['max_lon']:.5f}"
    cache_path = CACHE_DIR / f"{hashlib.md5(key.encode()).hexdigest()}.xml"

    if cache_path.exists():
        # We've already fetched this exact area before -- just read the
        # raw XML we saved last time instead of hitting the network again.
        print(f"  Using cached OSM data: {cache_path}")
        xml_text = cache_path.read_text(encoding="utf-8")
    else:
        # Overpass QL (query language) query: "give me every 'way' (a line
        # or polygon shape in OSM) tagged as a 'building', inside this
        # bounding box, and also give me the underlying 'node' points (the
        # actual coordinate vertices) needed to draw those ways' outlines."
        # [out:xml] asks for the response in XML format; [timeout:60] tells
        # the server to give up and return an error after 60 seconds rather
        # than hanging forever on a huge query.
        query = f"""
        [out:xml][timeout:60];
        (
          way["building"]({bbox['min_lat']},{bbox['min_lon']},{bbox['max_lat']},{bbox['max_lon']});
        );
        out body;
        >;
        out skel qt;
        """
        # Public Overpass mirrors will reject requests that use the
        # default, generic User-Agent that the `requests` library sends by
        # default (this looks like anonymous bot traffic to their abuse
        # filters). Identifying ourselves properly with a descriptive
        # User-Agent avoids being blocked with an HTTP 406 error.
        headers = {
            "User-Agent": "DT-QUEST-research-pipeline/1.0 (Berlin V2X DT-QUEST project)"
        }

        # We'll try each mirror in OVERPASS_URLS in turn, and for each
        # mirror we'll retry up to 3 times with an increasing wait, since
        # these free public servers occasionally time out or are briefly
        # overloaded -- a transient failure shouldn't stop the whole
        # pipeline if simply waiting and retrying would succeed.
        xml_text = None
        last_error = None
        for mirror in OVERPASS_URLS:
            for attempt in range(3):
                try:
                    print(f"  Querying {mirror} for bbox {key} "
                          f"(attempt {attempt + 1}/3) ...")
                    # Send the query as an HTTP POST request (Overpass
                    # expects the query text in a form field called
                    # "data"). timeout=90 is OUR client-side timeout (how
                    # long we're willing to wait for a reply), separate
                    # from the [timeout:60] INSIDE the query (which tells
                    # the SERVER how long it's allowed to keep processing).
                    r = requests.post(mirror, data={"data": query},
                                       headers=headers, timeout=90)
                    # Raise an exception if the server responded with an
                    # HTTP error status code (4xx/5xx), so it gets caught
                    # by the `except` block below and treated as a
                    # retry-able failure rather than silently continuing
                    # with a garbage/empty response.
                    r.raise_for_status()
                    xml_text = r.text
                    break  # success -- stop retrying this mirror
                except requests.exceptions.RequestException as e:
                    last_error = e
                    wait = 5 * (attempt + 1)  # 5s, then 10s, then 15s
                    print(f"    failed ({e}); retrying in {wait}s...")
                    time.sleep(wait)
            if xml_text is not None:
                break  # success -- stop trying further mirrors

        if xml_text is None:
            # Every mirror failed on every attempt -- give up loudly with a
            # clear, actionable error message rather than continuing with
            # no building data (which would silently produce a scene with
            # no obstructions at all -- physically wrong and misleading).
            raise RuntimeError(
                f"All Overpass mirrors failed for bbox {key}. Last error: {last_error}\n"
                f"Try again in a few minutes -- the free Overpass instances are "
                f"occasionally overloaded. Progress so far (operator 1's cached OSM "
                f"data and predictions) is unaffected."
            )

        # Save the raw response to our local cache so future runs for this
        # exact bounding box are instant and don't need the network.
        cache_path.write_text(xml_text, encoding="utf-8")
        # A short pause out of politeness to the free, volunteer-run
        # Overpass service, so we're not hammering it with back-to-back
        # requests.
        time.sleep(1.0)

    # Parse the XML text into a navigable tree structure.
    root = ET.fromstring(xml_text)

    # Build a lookup dictionary from each OSM "node" (a single point with
    # an ID, latitude, and longitude) to its (lat, lon) coordinates, so we
    # can quickly resolve the vertex IDs referenced by each building's
    # outline in the next step.
    nodes = {n.attrib["id"]: (float(n.attrib["lat"]), float(n.attrib["lon"]))
             for n in root.findall("node")}

    buildings = []
    # Each OSM "way" is a sequence of node references that, together,
    # trace out a shape (here, a building's footprint outline).
    for way in root.findall("way"):
        # Look up the real coordinates for every node this way references,
        # skipping any reference to a node we don't have data for (this can
        # happen at the very edge of our query area).
        refs = [nd.attrib["ref"] for nd in way.findall("nd") if nd.attrib["ref"] in nodes]

        # A valid closed polygon (like a building footprint) needs at
        # least 4 points, and its first and last point must be the SAME
        # point (that's what makes it a closed shape rather than an open
        # line). If either condition fails, skip this way -- it's not a
        # usable building outline for our purposes.
        if len(refs) < 4 or refs[0] != refs[-1]:
            continue

        # OSM "tags" are the key-value metadata attached to a way (e.g.
        # building=yes, height=20, building:levels=6). Collect them into a
        # simple dictionary for easy lookup.
        tags = {t.attrib["k"]: t.attrib["v"] for t in way.findall("tag")}

        # Only keep ways that are actually tagged as a building -- the
        # query already filtered for this, but double-checking here is
        # cheap and defensive.
        if "building" not in tags:
            continue

        # Resolve every referenced node ID into its actual (lat, lon)
        # coordinate, giving us the full outline of this building.
        coords = [nodes[r] for r in refs]

        # Try to determine a realistic height for this building. OSM data
        # quality varies a lot -- many buildings have no height information
        # at all. We try, in order of preference: (1) an explicit "height"
        # tag (given in metres, sometimes with a trailing "m" we need to
        # strip off), (2) a "building:levels" tag (number of floors), which
        # we convert to an approximate height using 3 metres per floor (a
        # standard rule-of-thumb for typical residential/office floor
        # height), (3) if neither is present or parseable, fall back to our
        # generic DEFAULT_BUILDING_HEIGHT_M constant defined above.
        height = DEFAULT_BUILDING_HEIGHT_M
        if "height" in tags:
            try:
                height = float(tags["height"].replace("m", "").strip())
            except ValueError:
                # The height tag existed but wasn't a clean number (e.g.
                # "approx 20" or some other free-text value) -- keep the
                # default rather than crashing on bad OSM data.
                pass
        elif "building:levels" in tags:
            try:
                # max(3.0, ...) guards against a building absurdly claiming
                # 0 levels, which would otherwise produce a building with
                # zero height (physically meaningless).
                height = max(3.0, float(tags["building:levels"]) * 3.0)
            except ValueError:
                pass

        buildings.append({"latlon": coords, "height_m": height})

    print(f"  Found {len(buildings)} buildings")
    return buildings


# ---------------------------------------------------------------------------
# STEP C: turn the building list into an actual 3D scene file Sionna can load
# ---------------------------------------------------------------------------
def build_scene_xml(bbox: dict, buildings: list[dict], out_path: Path) -> tuple[Path, list[tuple]]:
    """Write out a Mitsuba scene description file (an XML format Sionna's
    underlying rendering engine understands) that places a flat ground
    plane plus one rectangular "box" per real building, at the correct
    real-world position, footprint size, and height. This is a
    deliberately simplified representation of the true, often irregular
    building shapes -- each building's real polygon outline is replaced by
    its bounding rectangle (the smallest rectangle that fully contains it).
    That's a coarse but fast-to-build approximation; refining this to the
    buildings' true polygon shapes is a natural improvement to make later,
    once this simpler version's results are validated as directionally
    sensible.
    """
    # We'll also return the flat local-XY bounding box of every building we
    # place, purely so other code (or a human debugging this) can inspect
    # exactly where Sionna thinks each building is, in the same local
    # coordinate system used everywhere else in this script.
    building_boxes = []

    # Start assembling the scene file as a list of XML text lines. Every
    # Mitsuba scene needs: a root <scene> element, at least one material
    # definition (bsdf = "bidirectional scattering distribution function",
    # i.e. how a surface reflects/absorbs radio energy), and one <shape>
    # per physical object in the world.
    lines = [
        '<scene version="3.0.0">',
        # "itu_concrete" is one of Sionna's built-in materials, implementing
        # the ITU-R P.2040 recommendation's frequency-dependent formula for
        # how concrete reflects and absorbs radio energy. We reuse this
        # SAME material for the ground and for every building -- a
        # simplification, since a real city has many different materials
        # (glass, brick, metal, wood...), but concrete is a broadly
        # reasonable default for generic urban structures.
        '  <bsdf type="itu_concrete" id="itu_concrete"/>',
        # A single large, thin, flat box acting as the ground plane, so
        # rays have a floor to reflect off (and can't nonsensically pass
        # underneath the world). 2000m x 2000m comfortably covers our
        # ~1400m-wide scene (900m span + 250m margin on each side) with
        # room to spare. 0.1m thickness keeps it "flat" while still being a
        # solid, ray-tracer-friendly 3D object rather than a zero-thickness
        # mathematical plane.
        '  <shape type="cube" id="ground">',
        '    <transform name="to_world">',
        '      <scale x="2000" y="2000" z="0.1"/>',
        '      <translate x="0" y="0" z="-0.1"/>',
        '    </transform>',
        '    <ref id="itu_concrete"/>',
        '  </shape>',
    ]

    # Now add one box-shaped "shape" element per real building.
    for i, b in enumerate(buildings):
        # Pull out just the latitudes and just the longitudes of this
        # building's outline points, so we can convert them to local metres
        # in one batch call.
        lats = [c[0] for c in b["latlon"]]
        lons = [c[1] for c in b["latlon"]]
        x, y = latlon_to_local_xy(lats, lons, bbox["origin_lat"], bbox["origin_lon"])

        # The bounding rectangle of this building's true outline: the
        # smallest axis-aligned rectangle that fully contains every one of
        # its real corner points. This is the coarse "box" approximation
        # mentioned above -- a building shaped like an L or a curve gets
        # flattened into its enclosing rectangle.
        x_min, x_max, y_min, y_max = x.min(), x.max(), y.min(), y.max()
        building_boxes.append((float(x_min), float(y_min), float(x_max), float(y_max)))

        # Mitsuba's built-in "cube" primitive is defined as a 2x2x2 unit
        # cube centred on the origin, BEFORE any scale/translate transform
        # is applied. So to get a box of real width (x_max - x_min), we
        # need to scale by HALF that width (since the cube's un-scaled
        # half-width is 1, and scale multiplies that half-width). The
        # max(..., 1.0) floors ensure we never create a degenerate,
        # zero-size box (which could happen for a building whose footprint
        # is smaller than our numerical precision) -- always at least 1
        # metre so Mitsuba has a valid, non-degenerate shape to work with.
        sx = max((x_max - x_min) / 2.0, 1.0)
        sy = max((y_max - y_min) / 2.0, 1.0)
        sz = max(b["height_m"] / 2.0, 1.0)

        # After scaling, we translate the box so it sits centred over its
        # real footprint's centre point horizontally, and so its BASE
        # sits on the ground (z=0) rather than being centred vertically on
        # the ground -- hence translating up by sz (half the building's
        # height), so the box spans from z=0 (ground level) up to z=height.
        tx, ty, tz = (x_min + x_max) / 2.0, (y_min + y_max) / 2.0, sz

        lines += [
            f'  <shape type="cube" id="building_{i}">',
            '    <transform name="to_world">',
            f'      <scale x="{sx:.3f}" y="{sy:.3f}" z="{sz:.3f}"/>',
            f'      <translate x="{tx:.3f}" y="{ty:.3f}" z="{tz:.3f}"/>',
            '    </transform>',
            '    <ref id="itu_concrete"/>',
            '  </shape>',
        ]

    lines.append("</scene>")
    # Write the assembled XML text out to disk as a real file -- Sionna's
    # `load_scene()` function (used later, in run_sionna()) needs an actual
    # file path to read, not just a Python string in memory.
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path, building_boxes


# ---------------------------------------------------------------------------
# STEP D: run the actual ray-tracing physics simulation, one receiver at a time
# ---------------------------------------------------------------------------
def to_hz(freq_series: pd.Series) -> pd.Series:
    """Small safety helper (currently unused directly in the main flow
    below, since we read PCell_freq_MHz which is already a clean MHz value
    -- kept here in case a future dataset provides frequency in a less
    consistent/mixed unit and this heuristic conversion is needed again).
    Looks at the median value of a frequency column: if it's suspiciously
    small (under 100,000), it's almost certainly expressed in MHz rather
    than Hz, and gets multiplied up to Hz. Real cellular frequencies in Hz
    are on the order of 10^8 to 10^10 (hundreds of millions to tens of
    billions), so anything smaller than 100,000 is essentially certain to
    actually be MHz, not Hz.
    """
    med = freq_series.dropna().median()
    if med is not None and med < 100_000:
        return freq_series * 1e6
    return freq_series


def run_sionna(scene_xml: Path, towers: pd.DataFrame, receivers: pd.DataFrame,
               bbox: dict) -> pd.DataFrame:
    """The core physics step: for every receiver point, place its ACTUAL
    serving cell tower (the one the real measurement was connected to) and
    the receiver itself into the 3D scene, run Sionna's ray tracer between
    that exact pair, and record the resulting received signal power. This
    is done one (tower, receiver) pair at a time -- a scene containing
    every tower and every receiver simultaneously would compute paths
    between EVERY tower and EVERY receiver, summing power from towers a
    device wasn't even connected to, which would silently corrupt the
    result. Isolating exactly one transmitter and one receiver per call is
    what guarantees the received power we compute corresponds to the real,
    physical serving link, not a meaningless aggregate.
    """
    # These imports happen INSIDE the function (rather than at the top of
    # the file) so that simply importing this Python module (e.g. if
    # another script wanted to reuse a helper function from it) doesn't
    # require Sionna/Mitsuba to be installed unless you actually call this
    # specific function. `mitsuba` is the underlying physical rendering
    # engine; the `sionna.rt` classes are Sionna's radio-specific layer on
    # top of it.
    import mitsuba as mi
    from sionna.rt import PlanarArray, PathSolver, Receiver, Transmitter, load_scene

    # Load the 3D scene file we built in Step C. `merge_shapes=True` tells
    # Mitsuba it's allowed to internally combine/optimize shapes that share
    # the same material for faster rendering -- a performance optimization
    # that doesn't change the physical result.
    scene = load_scene(str(scene_xml), merge_shapes=True)

    # Print which underlying compute backend ("variant") Mitsuba picked.
    # Variants named "cuda_..." mean it's using your NVIDIA GPU; variants
    # named "llvm_..." mean it fell back to running on the CPU instead
    # (slower, but still functionally correct). "_mono_" means it's
    # tracking a single (scalar) signal channel rather than full
    # dual-polarization detail -- a simplification for speed that doesn't
    # affect whether a path is found, only some polarization-dependent
    # power details.
    print(f"  Mitsuba variant in use: {mi.variant()}")

    # An "antenna array" describes the physical antenna pattern (how
    # strongly it radiates/receives energy in different directions) used
    # at each transmitter and receiver. Here we use the simplest possible
    # configuration: a single antenna element (num_rows=1, num_cols=1) --
    # i.e. not a multi-antenna/MIMO array -- at both ends.
    #   - "tr38901" (used for the transmitter) is a standard 3GPP antenna
    #     radiation pattern commonly used for base-station antennas in
    #     propagation studies.
    #   - "dipole" with "cross" polarization (used for the receiver) is a
    #     simple, generic antenna pattern reasonable for a mobile/vehicle
    #     receiver, without needing exact real hardware specifications we
    #     don't have.
    scene.tx_array = PlanarArray(num_rows=1, num_cols=1, vertical_spacing=0.5,
                                  horizontal_spacing=0.5, pattern="tr38901", polarization="V")
    scene.rx_array = PlanarArray(num_rows=1, num_cols=1, vertical_spacing=0.5,
                                  horizontal_spacing=0.5, pattern="dipole", polarization="cross")

    # Convert every geolocated tower's real-world latitude/longitude into
    # the same local X/Y metre coordinate system used for the scene
    # geometry, so towers and buildings line up correctly in the same
    # coordinate space.
    tx_x, tx_y = latlon_to_local_xy(towers["tower_lat"], towers["tower_lon"],
                                     bbox["origin_lat"], bbox["origin_lon"])
    towers = towers.copy()
    towers["x_m"], towers["y_m"] = tx_x, tx_y

    # Build a lookup table indexed by cell identity (the unique ID
    # identifying which specific cell/tower a device is connected to), so
    # that for each receiver row we can instantly find its correct serving
    # tower's position, rather than searching through the whole towers
    # table every time.
    towers_by_cell = towers.set_index(towers["PCell_Cell_Identity"].astype(int))

    # The PathSolver object is Sionna's actual ray-tracing engine -- the
    # thing that computes how radio waves would travel through our 3D
    # scene between a transmitter and receiver, accounting for direct
    # line-of-sight, reflections, diffraction, etc. We create ONE solver
    # and reuse it across all receivers (it doesn't hold per-link state).
    solver = PathSolver()

    # We'll accumulate one result dictionary per receiver into this list,
    # and turn it into a DataFrame at the end.
    results = []

    # Counters purely for the human-readable summary printed at the end of
    # this function -- they don't affect the actual computation, just help
    # a person running this script understand how much data was usable.
    n_no_tower = 0
    n_no_path = 0
    # Track the tx-rx distance for every zero-path failure, so we can
    # report at the end whether these failures cluster at long range
    # (suggesting a genuine scene-fidelity gap worth improving with better
    # geometry or more ray-tracing depth) or are scattered randomly across
    # distances (more consistent with occasional geometric bad luck, less
    # worth chasing further).
    no_path_distances = []

    # The main loop: one full ray-tracing computation per sampled receiver.
    for idx, row in receivers.iterrows():
        # Which cell tower was this specific real-world measurement
        # actually connected to? We look this up directly from the
        # dataset's own PCell_Cell_Identity column -- this is what makes
        # the comparison meaningful: we're checking whether physics
        # predicts the SAME received power as was actually measured for
        # THIS SPECIFIC real connection, not some arbitrary nearby tower.
        cell_id = row.get("PCell_Cell_Identity", None)

        # If this row doesn't have a valid serving-cell identity, or if we
        # were never able to geolocate that specific tower (see
        # 02_geolocate_towers.py), we cannot ray-trace this receiver at
        # all -- there's no known transmitter position to trace from. We
        # record this outcome explicitly as NaN (rather than skipping the
        # row silently), so downstream analysis can see exactly how many
        # receivers were excluded and why.
        if pd.isna(cell_id) or int(cell_id) not in towers_by_cell.index:
            n_no_tower += 1
            results.append({"row_index": idx, "sionna_rx_power_dbm": np.nan})
            continue

        # Look up this receiver's actual serving tower's position.
        t = towers_by_cell.loc[int(cell_id)]
        # set_index can return either a single row (a pandas Series) or,
        # if multiple tower entries happened to share the same cell
        # identity, a small DataFrame of matching rows. In the rare
        # duplicate case, we just take the first match rather than
        # crashing -- a reasonable, documented simplification.
        if isinstance(t, pd.DataFrame):
            t = t.iloc[0]

        # Convert this receiver's real GPS position into the same local
        # metre coordinate system as everything else in the scene.
        rx_x, rx_y = latlon_to_local_xy(row["Latitude"], row["Longitude"],
                                         bbox["origin_lat"], bbox["origin_lon"])

        # Ground-plane distance between this transmitter and receiver, in
        # metres -- computed now (cheap) purely so we can log it if this
        # link turns out to have zero valid paths, for the failure
        # diagnostic printed at the end of this function.
        tx_rx_distance_m = math.hypot(rx_x - float(t["x_m"]), rx_y - float(t["y_m"]))

        # Set the scene's operating radio frequency to match what this
        # SPECIFIC real measurement actually used (different rows can be
        # on different LTE bands, e.g. 1800MHz vs 2600MHz) -- this matters
        # physically because how strongly a building blocks/reflects a
        # radio wave, and how fast signal strength naturally decays with
        # distance, both depend on frequency. If this particular row is
        # missing a frequency value for some reason, we fall back to a
        # generic 1.8 GHz (a common LTE band) as a reasonable default
        # rather than crashing.
        freq_mhz = row.get("PCell_freq_MHz", None)
        scene.frequency = float(freq_mhz) * 1e6 if pd.notna(freq_mhz) else 1.8e9

        # Give this transmitter/receiver pair unique names within the
        # scene, based on the row's index, so multiple iterations of this
        # loop never collide with each other's object names.
        tx_name, rx_name = f"tx_{idx}", f"rx_{idx}"

        # Create the transmitter object at the real (converted) tower
        # position, at our assumed TOWER_HEIGHT_M mounting height.
        tx = Transmitter(name=tx_name,
                          position=[float(t["x_m"]), float(t["y_m"]), TOWER_HEIGHT_M])
        # Create the receiver object at the real (converted) GPS position
        # of this specific measurement, at our assumed vehicle antenna
        # height.
        rx = Receiver(name=rx_name, position=[float(rx_x), float(rx_y), RECEIVER_HEIGHT_M])

        # Actually add both objects into the live scene so the solver can
        # see them.
        scene.add(tx)
        scene.add(rx)

        # Point the transmitter's antenna directly at the receiver. Real
        # cell-tower antennas are typically fixed and don't "aim" at every
        # single device individually the way this does -- this is a
        # simplifying assumption that gives the transmitter the most
        # favourable possible orientation towards this receiver, so we're
        # not artificially penalizing the link with an arbitrary antenna
        # orientation we don't actually know the real value of.
        tx.look_at(rx)

        try:
            # THIS IS THE KEY PHYSICS CALL, AND THE MAIN CHANGE IN THIS
            # VERSION OF THE SCRIPT. We ask the solver to find every valid
            # way a radio wave could travel from this transmitter to this
            # receiver through our 3D scene, subject to the following
            # settings:
            #
            #   max_depth=6
            #       The maximum number of physical "interactions"
            #       (bounces/reflections/diffractions) a traced ray path is
            #       allowed to have before the solver gives up looking for
            #       more paths along that direction. Raised from 5 to 6 (vs
            #       the previous version of this script) specifically to
            #       give the solver enough depth budget to find paths that
            #       COMBINE a diffraction (bending around an edge) with a
            #       subsequent reflection off a nearby wall -- a physically
            #       common way for signal to reach an otherwise-shadowed
            #       receiver, which needs more than a single interaction to
            #       resolve.
            #
            #   los=True
            #       Consider the direct, unobstructed line-of-sight path,
            #       if one geometrically exists between transmitter and
            #       receiver (i.e. no building in the way at all).
            #
            #   specular_reflection=True
            #       Consider "mirror-like" reflections: a ray bouncing off
            #       a flat surface (like a building wall) at a clean,
            #       predictable angle, the way light reflects off a mirror.
            #
            #   diffraction=True   <-- THE MAIN CHANGE IN THIS VERSION
            #       Consider DIFFRACTED paths: radio waves bending AROUND
            #       sharp edges (like a building's corner or roofline)
            #       rather than passing straight through or reflecting off
            #       a flat face. This is the real physical mechanism that
            #       lets a receiver with NO direct line-of-sight and NO
            #       clean mirror-bounce path still receive some signal in
            #       real life -- for example, standing just around the
            #       corner from a tower's direct view. Without this
            #       enabled, every such "shadowed" receiver was previously
            #       reported as having zero valid paths at all, which
            #       silently and systematically excluded exactly the
            #       hardest, most informative locations from our
            #       validation -- precisely the opposite of what a
            #       trustworthy digital-twin reconstruction should do.
            #
            #   diffuse_reflection=False
            #       Diffuse ("scattered in many directions at once, like
            #       light off a rough/matte surface") reflections are left
            #       OFF. This is a real, additional propagation mechanism
            #       we are choosing not to model yet -- a documented
            #       simplification, not a bug -- because it is
            #       computationally more expensive and its contribution is
            #       typically smaller than specular reflection and
            #       diffraction for the frequencies and geometry here.
            #       Worth revisiting later if the resulting accuracy still
            #       has a gap that diffuse scattering could plausibly
            #       explain.
            #
            #   refraction=False
            #       Refraction (a ray physically passing THROUGH a
            #       material, like light bending through glass or water)
            #       is left off. We are modelling every building as an
            #       opaque concrete obstruction, which is the standard,
            #       reasonable assumption for outdoor macro-cell
            #       propagation modelling -- we are not attempting to model
            #       signal passing through windows into building interiors.
            #
            #   synthetic_array=True
            #       An internal Sionna performance optimisation for how it
            #       computes results for antenna arrays -- doesn't change
            #       the physical propagation model, only how efficiently
            #       it's computed given our single-element antenna
            #       configuration above.
            #
            #   seed=41
            #       A fixed random seed for any randomised sampling the
            #       solver does internally (e.g. how it samples candidate
            #       ray directions). Fixing this makes the results exactly
            #       reproducible between runs -- re-running this exact
            #       script again will produce identical numbers, which is
            #       important for being able to trust and debug the
            #       pipeline.
            paths = solver(scene=scene, max_depth=MAX_RAY_DEPTH, los=ENABLE_LOS,
                            specular_reflection=ENABLE_SPECULAR_REFLECTION,
                            diffraction=ENABLE_DIFFRACTION,
                            diffuse_reflection=ENABLE_DIFFUSE_REFLECTION,
                            refraction=ENABLE_REFRACTION,
                            synthetic_array=True, seed=41)

            # `paths.cir()` extracts the "channel impulse response" -- for
            # every valid path the solver found, this gives its complex
            # amplitude `a` (how much the signal was attenuated/phase-
            # shifted along that path) and its time delay `tau` (how long
            # that path took to arrive, relevant for multipath timing
            # effects we aren't using directly here). We only need `a`,
            # hence the underscore for the unused `_tau`. `out_type="numpy"`
            # asks for a plain NumPy array rather than a
            # framework-specific tensor type, since that's simplest for us
            # to do plain arithmetic on next.
            a, _tau = paths.cir(normalize_delays=False, out_type="numpy")

            # Sum the POWER (squared magnitude, |a|^2) contributed by every
            # individual path the solver found, to get the total received
            # power at this receiver from this transmitter, combining all
            # the different ways the signal could have travelled (direct,
            # reflected, diffracted, and any combination thereof, up to our
            # max_depth budget). This is safe to sum across "everything in
            # the scene" specifically BECAUSE this scene contains exactly
            # one transmitter and one receiver at this point in the loop --
            # if it contained multiple transmitters, this same summing
            # logic would incorrectly combine power from towers the device
            # wasn't even connected to.
            p_rx_linear = float(np.sum(np.abs(a) ** 2))

            # If that total is essentially zero, it means the solver
            # genuinely found NO valid path at all between this specific
            # transmitter and receiver, even with diffraction now enabled
            # -- meaning this location really is fully radio-shadowed under
            # our current geometry and interaction settings. Converting a
            # near-zero number to decibels (10*log10(~0)) would produce an
            # extremely large negative number that is a numerical
            # artefact, not a real physical measurement -- so we instead
            # explicitly record this as NaN (missing), which correctly
            # excludes it from any downstream averaging rather than
            # letting one such value silently distort the results.
            if p_rx_linear < NO_PATH_LINEAR_THRESHOLD:
                p_rx_dbm = np.nan
                n_no_path += 1
                no_path_distances.append(tx_rx_distance_m)
            else:
                # Convert the total linear received power into decibels
                # relative to one milliwatt-equivalent scale consistent
                # with the rest of this pipeline's dBm conventions (see
                # 04_compute_pathloss_comparison.py's calibration step,
                # which handles converting this into an absolute dBm value
                # via a fitted offset, since Sionna's internal power scale
                # isn't automatically referenced to a known real-world
                # transmit power).
                p_rx_dbm = 10 * math.log10(p_rx_linear)

        except Exception as e:
            # If the solver call itself raised an unexpected error (rather
            # than just finding zero paths, which is handled above as a
            # normal, expected outcome), record this receiver as NaN too,
            # but print a warning so a human notices if this is happening
            # unexpectedly often (which could indicate a scene/geometry
            # problem worth investigating, rather than just "no signal
            # here").
            p_rx_dbm = np.nan
            print(f"  WARNING: ray-tracing failed for row {idx}: {e}")

        results.append({"row_index": idx, "sionna_rx_power_dbm": p_rx_dbm})

        # Remove this iteration's transmitter and receiver from the scene
        # before the next loop iteration. Without this, every previous
        # iteration's tx/rx objects would still be sitting in the scene,
        # growing the object count every time and eventually reintroducing
        # exactly the "summing power across unrelated transmitters" problem
        # this per-receiver, one-tx-one-rx design is meant to avoid.
        scene.remove(tx_name)
        scene.remove(rx_name)

    # Print a plain-language summary of how many receivers were excluded,
    # and specifically why -- this is important for honesty about what
    # fraction of the real dataset this validation actually covers.
    if n_no_tower:
        print(f"  {n_no_tower} receivers had no matching geolocated serving tower -- "
              f"left as NaN (excluded from comparison, not silently dropped).")
    if n_no_path:
        print(f"  {n_no_path} receivers had zero valid propagation paths even with "
              f"diffraction enabled (fully obstructed under current "
              f"max_depth={MAX_RAY_DEPTH} settings) -- left as NaN rather than an "
              f"artificial numerical-floor value.")
        # Compare the typical distance of FAILED links against all attempted
        # links: if failures cluster at noticeably longer range, that's a
        # real signal this is a genuine scene-fidelity gap at long distance
        # (worth improving geometry/max_depth for) rather than just random
        # geometric bad luck scattered evenly across all distances.
        if no_path_distances:
            median_fail_dist = float(np.median(no_path_distances))
            print(f"  Zero-path failures: median tx-rx distance = "
                  f"{median_fail_dist:.0f}m (min={min(no_path_distances):.0f}m, "
                  f"max={max(no_path_distances):.0f}m). Compare this against the "
                  f"typical distance range for this operator (see the distance "
                  f"stats printed by run_for_operator) -- if failures are "
                  f"concentrated well above the typical range, that points to a "
                  f"genuine long-range scene-fidelity gap (worth trying "
                  f"ENABLE_DIFFUSE_REFLECTION=True or a larger MAX_RAY_DEPTH); if "
                  f"they're spread similarly to the overall distance distribution, "
                  f"it's more consistent with occasional geometric bad luck "
                  f"(a specific building placement blocking that one link) rather "
                  f"than a systematic gap.")

    # Turn our list of per-receiver result dictionaries into a proper
    # DataFrame, indexed by the original row_index, so it can be easily
    # matched back up against the original measurement rows in
    # 04_compute_pathloss_comparison.py.
    return pd.DataFrame(results).set_index("row_index")


# ---------------------------------------------------------------------------
# TOP-LEVEL ORCHESTRATION: runs all the steps above, in order, for one operator
# ---------------------------------------------------------------------------
def run_for_operator(op: int, n_sample: int):
    """Runs the full Gate-2 pipeline -- pick an area, fetch its buildings,
    build a 3D scene, ray-trace a sample of real receivers against their
    real serving towers -- for a single cellular operator (1 or 2), and
    saves the resulting predictions to a CSV file for the next script
    (04_compute_pathloss_comparison.py) to consume.
    """
    print(f"\n=== Operator {op} ===")

    # Load the DATA-DRIVEN estimated tower positions for this operator,
    # produced by 02_estimate_towers_from_data.py using RSRP-weighted
    # centroid localization -- no external database dependency. Every
    # tower here already has a real position estimate; there's no
    # "dropna" needed the way there was for OpenCelliD matches, since a
    # tower only appears in this file at all if it had enough data to
    # produce an estimate in the first place.
    towers = pd.read_csv(OUTPUT_DIR / f"towers_operator{op}_estimated.csv")
    print(f"Using {len(towers)} data-driven estimated towers "
          f"(median position spread: {towers['weighted_spread_m'].median():.1f}m)")

    # Load the full dataset, which now includes the tower_estimate_group
    # column (added by 02_estimate_towers_from_data.py) marking each row
    # as "localization" (used to estimate its tower's position -- MUST
    # NOT be used for validation, or we'd be checking Sionna's prediction
    # against the same data that built the geometry it's being checked
    # against), "validation" (held out, safe to ray-trace against), or
    # "excluded" (didn't pass Gate-1 checks or its cell had too little
    # data to localize at all).
    df = pd.read_csv(CLEANED_CSV, low_memory=False)
    df_op = df[(df["operator"] == op) & df["Latitude"].notna() &
               df["Longitude"].notna()].copy()

    # Further restrict to rows that PASS every Gate-1 range-validation
    # check (RSRP, RSRQ, RSSI, SNR all within their corrected, real 3GPP-
    # justified bounds -- see gate1_cleaning_v2.py). There's no point
    # spending expensive ray-tracing compute validating a measurement we
    # already know is physically implausible before we even start.
    clean_mask = ~df_op[RANGE_FLAG_COLS].any(axis=1)
    df_op_clean = df_op[clean_mask]

    # THE CIRCULARITY GUARD: only rows in the "validation" group are
    # eligible to be ray-traced. This is the disjoint hold-out split --
    # every row used to ESTIMATE a tower's position is permanently
    # ineligible to also be used to CHECK whether Sionna's prediction at
    # that tower's estimated position matches reality.
    n_before_holdout = len(df_op_clean)
    df_op_clean = df_op_clean[df_op_clean["tower_estimate_group"] == "validation"]
    print(f"  {len(df_op_clean)} / {n_before_holdout} Gate-1-clean rows are in the "
          f"held-out VALIDATION group (the rest were used to estimate tower "
          f"positions, or belong to a tower with insufficient data, and are "
          f"correctly excluded here to avoid circularity)")

    # STEP A: automatically pick the busiest ~900m square patch of this
    # operator's driving area to build our 3D scene around.
    bbox = select_subarea_bbox(df_op_clean)
    print(f"Selected sub-area centered at grid cell with {bbox['grid_count']} points")
    print(f"  bbox lat=[{bbox['min_lat']:.5f},{bbox['max_lat']:.5f}] "
          f"lon=[{bbox['min_lon']:.5f},{bbox['max_lon']:.5f}]")

    # Filter down to just the receiver rows that physically fall inside
    # that chosen bounding box -- these are the only ones we'll actually
    # simulate, since they're the ones our 3D scene's buildings will
    # actually cover.
    in_bbox = (df_op_clean["Latitude"].between(bbox["min_lat"], bbox["max_lat"]) &
               df_op_clean["Longitude"].between(bbox["min_lon"], bbox["max_lon"]))
    scene_receivers_pool = df_op_clean[in_bbox]
    print(f"  {len(scene_receivers_pool)} cleaned receiver points fall inside this sub-area")

    # ITU-R P.2040 -- the recommendation defining how Sionna's "itu_concrete"
    # material behaves at different frequencies -- is only officially
    # validated for frequencies between 1 GHz and 100 GHz. German LTE Band
    # 28 operates at 700 MHz, which is BELOW that validated range. Rather
    # than silently extrapolating a physical model outside the range its
    # own creators validated it for (which would be scientifically
    # dishonest and would previously crash Sionna's material lookup
    # outright), we explicitly exclude those receivers here and say so.
    below_1ghz = scene_receivers_pool["PCell_freq_MHz"] < 1000
    n_excluded = int(below_1ghz.sum())
    if n_excluded:
        print(f"  Excluding {n_excluded} / {len(scene_receivers_pool)} receiver points served "
              f"by sub-1GHz bands (e.g. Band 28 / 700MHz) -- outside ITU-R P.2040's "
              f"validated 1-100 GHz range for the concrete material model.")
    scene_receivers_pool = scene_receivers_pool[~below_1ghz]

    # From everything that's left, take a random sample of n_sample rows
    # to actually ray-trace. random_state=42 fixes the random seed so this
    # sample is exactly reproducible across runs -- re-running the script
    # picks the SAME sample of receivers every time, which matters for
    # being able to compare results across code changes fairly.
    sample = scene_receivers_pool.sample(n=min(n_sample, len(scene_receivers_pool)), random_state=42)

    # STEP B: fetch (or load from cache) the real OpenStreetMap building
    # footprints for our chosen bounding box.
    print("Fetching OSM buildings for this sub-area...")
    buildings = fetch_osm_buildings(bbox)

    # STEP C: turn those buildings (plus a ground plane) into an actual
    # Mitsuba scene XML file on disk, in a dedicated per-operator
    # subdirectory so operator 1 and operator 2's scene files never
    # collide or overwrite each other.
    scene_dir = OUTPUT_DIR / f"scene_operator{op}"
    scene_dir.mkdir(parents=True, exist_ok=True)
    scene_xml, building_boxes = build_scene_xml(bbox, buildings, scene_dir / "scene.xml")
    print(f"  Scene written -> {scene_xml} ({len(building_boxes)} building boxes)")

    # We only need to actually place (and ray-trace against) the specific
    # towers that our SAMPLED receivers are actually connected to -- no
    # point adding a transmitter to the scene for some other tower nobody
    # in our sample ever used.
    serving_cells = set(sample["PCell_Cell_Identity"].dropna().astype(int))
    towers_in_use = towers[towers["PCell_Cell_Identity"].astype(int).isin(serving_cells)]
    if towers_in_use.empty:
        # Defensive fallback: if, for some reason, none of our geolocated
        # towers match this particular sample's serving cells (e.g. an
        # unlucky random sample), fall back to using every geolocated
        # tower for this operator rather than running with zero
        # transmitters at all.
        print("  WARNING: none of the geolocated towers match this sub-area's serving "
              "cells -- falling back to ALL geolocated towers for this operator.")
        towers_in_use = towers

    # STEP D: the actual physics simulation, described in detail in
    # run_sionna() above.
    print(f"Running sionna-rt over {len(sample)} receiver points, "
          f"{len(towers_in_use)} transmitters...")
    preds = run_sionna(scene_xml, towers_in_use, sample, bbox)

    # Save the resulting per-receiver predictions to a CSV file, which
    # 04_compute_pathloss_comparison.py will load next to compare against
    # the real measured values.
    out_path = OUTPUT_DIR / f"sionna_predictions_operator{op}.csv"
    preds.to_csv(out_path)
    print(f"Saved {preds['sionna_rx_power_dbm'].notna().sum()} / {len(preds)} "
          f"successful predictions -> {out_path}")


# ---------------------------------------------------------------------------
# SCRIPT ENTRY POINT: only runs when this file is executed directly
# (e.g. `python 03_build_sionna_scene.py --operator 1`), not when it's
# imported as a module from somewhere else.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Set up the command-line argument parser: this script requires you to
    # specify which operator (1 or 2) to run, and optionally lets you
    # override how many receiver points to sample.
    ap = argparse.ArgumentParser()
    ap.add_argument("--operator", type=int, choices=[1, 2], required=True)
    ap.add_argument("--n-sample", type=int, default=N_SAMPLE_POINTS)
    ap.add_argument("--max-depth", type=int, default=MAX_RAY_DEPTH,
                     help="Max ray-tracing interaction depth. Higher finds more "
                          "paths (fewer 'zero valid paths' failures) but is slower.")
    ap.add_argument("--diffuse-reflection", action="store_true",
                     help="Enable diffuse (rough-surface) scattering, off by "
                          "default. Can recover paths to shadowed receivers via "
                          "a different mechanism than diffraction, at extra cost.")
    ap.add_argument("--no-diffraction", action="store_true",
                     help="Disable diffraction (on by default). Mainly useful "
                          "for reproducing the pre-diffraction-fix behaviour for "
                          "comparison, not recommended for normal use.")
    args = ap.parse_args()

    # Apply any CLI overrides to the module-level knobs before running.
    MAX_RAY_DEPTH = args.max_depth
    ENABLE_DIFFUSE_REFLECTION = args.diffuse_reflection
    ENABLE_DIFFRACTION = not args.no_diffraction

    # Actually run the full pipeline for the requested operator.
    run_for_operator(args.operator, args.n_sample)

    print("\nDone. Next step: 04_compute_pathloss_comparison.py")
