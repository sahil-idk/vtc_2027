# Review Finding M11 — Missing Per-Tower OSM Plausibility Check: Attempted, Blocked by Two Independent Gaps

**Status:** attempted, blocked (see below) · **Severity:** Weakens-the-paper · **Section(s) affected:** §IV-C (Gate 2 Results)

---

## 1. The plain-English version

Nothing in the pipeline checks whether an optimized tower's *position*
(as opposed to its height or azimuth, which do get a weak aggregate
check) lands anywhere physically plausible — near an actual building or
mast — rather than just wherever numerically minimizes training error
within the 500 m search box. This was flagged in the framing audit
(`M7_addendum_dt_readiness_and_v2x_thresholds.md`, finding M11 there,
same finding) as the single largest remaining evidentiary gap in the
"this is genuine digital-twin replication" story: everything else
(scattering physics, material properties, antenna pattern) is either
standards-derived or independently checked, but the recovered
*positions themselves* are never checked against anything outside the
optimizer's own objective.

## 2. What was attempted

The proposed fix needs two ingredients, both described in the original
finding as "already existing, no new data needed": (a) the per-tower
optimized coordinates, and (b) the OSM building-footprint layer already
used to build the Sionna scene. Checked both directly in this session:

**(a) Per-tower coordinates — same gap already documented for M4.**
`twingate/out/{device}_gate2_final.csv` exists for pc1, pc2, pc3 but not
pc4, and per the M4 investigation, these are not the run that produced
Table I's published numbers (pc1 has only 30 of ~130 towers; the
combined Op.2 val MAE recomputed from pc2+pc3 is 3.36 dB, not the
published 4.04 dB). This is the identical blocker already tracked in
`LEFTOVERS_GPU_REQUIRED.md`.

**(b) OSM building geometry — a second, independent, and more complete
blocker.** The actual scene geometry (`scene_operator1/`,
`scene_operator2/`) is gitignored and not present in this checkout — as
expected, since it's a large generated artifact. The natural fallback
is to fetch the same public OSM building data the original pipeline
uses (`03_build_sionna_scene.py` queries the public Overpass API
directly, with mirror fallback across `overpass-api.de`,
`overpass.kumi.systems`, and `overpass.openstreetmap.ru`). **Tested all
three directly from this session, plus the plain OSM website and a
Geofabrik extract mirror as further fallbacks — every one of them is
blocked by this sandbox's network egress policy**, not merely slow or
rate-limited:

```
overpass-api.de:443            — connect_rejected (organization policy)
overpass.kumi.systems:443      — connect_rejected (organization policy)
overpass.openstreetmap.ru:443  — connect_rejected (organization policy)
overpass.private.coffee:443    — connect_rejected (organization policy)
www.openstreetmap.org:443      — connect_rejected (organization policy)
download.geofabrik.de:443      — connect_rejected (organization policy)
```

This isn't a per-domain fluke (compare to the earlier 3GPP-spec-PDF
blocks in the M7 research, which were single hosts) — the entire OSM
domain family is blocked at the organization-policy level in this
sandbox. There is currently no way to obtain real building-footprint
geometry for the Berlin scene from this environment, independent of the
GPU/Sionna question entirely.

## 3. Why this is a *compound* blocker, not just M4's blocker again

M4's Path A needed one thing: a GPU + Sionna environment to rerun
`A19_gate2_final.py` to completion. M11 needs that too (to get complete,
correct tower coordinates for all four devices) — but *even with that
solved*, M11 additionally needs network access to OSM building data (or
the locally-generated scene files, which are a byproduct of that same
rerun and would exist once it's done). So M11 is unblocked at the same
time as M4, provided the environment that runs the A19 rerun also has
either internet access to OSM/Overpass or keeps the generated
`scene_operator{1,2}/` directories around afterward — worth calling out
explicitly when that rerun happens, since `scene_operator1/` and
`scene_operator2/` being gitignored means they could easily be deleted
between the rerun and this analysis if nobody is told to keep them.

## 4. What was *not* done, and why

Did not attempt the analysis on the partial/stale pc1/pc2/pc3 data using
some substitute for building geometry (e.g., a synthetic or
approximated footprint layer) — that would produce numbers with no real
evidentiary value and a false appearance of rigor, the same failure
mode already avoided once for M4. If real building data and complete
tower coordinates aren't both available, the honest answer is "not yet
checked," not a fabricated approximation.

## 5. What would actually unblock this

1. Complete the M4-blocking rerun: `A19_gate2_final.py` for all four
   devices, full mode, in a GPU + Sionna environment, confirmed to
   reproduce the published Table I numbers (see
   `LEFTOVERS_GPU_REQUIRED.md` for the exact steps).
2. In that same environment (or one with equivalent access), either (a)
   keep the generated `scene_operator1/scene.xml` and
   `scene_operator2/scene.xml` files after the rerun (they already
   contain the OSM-derived building mesh geometry actually used for ray
   tracing — extracting building footprint locations from the scene XML
   directly is the most faithful option since it's the exact geometry
   Sionna traced against, not a fresh OSM pull that might have drifted
   from what was originally fetched), or (b) confirm that environment
   has outbound access to the public Overpass API.
3. For each tower's final optimized `(refined_lat, refined_lon)`,
   compute distance to the nearest building footprint/mesh vertex.
   Report, per operator: the fraction of towers within a reasonable
   siting distance (e.g. a few meters, consistent with rooftop/mast
   mounting) of a building, and whether that fraction correlates with
   per-tower MAE improvement (a real correlation would be positive,
   independent evidence; a null result is also worth reporting honestly,
   per the original finding's framing).
4. Companion, lower-cost fix once (1) is done regardless of (2)/(3):
   extend the existing Operator 1 aggregate height/azimuth
   plausibility check (already in `main.tex` after the M9 fix) to
   Operator 2 using the same complete, correct per-tower data — this
   piece needs no OSM/network access at all, only the completed rerun.

## 6. Recommendation

Track alongside M4 in `LEFTOVERS_GPU_REQUIRED.md` as a compound
blocker (GPU rerun + either OSM network access or retained scene files),
not as a separate, independent leftover — they unblock together. Do not
attempt a partial version with substitute data.

**Not applied.** No changes to `main.tex` — this document only records
what was attempted and exactly why it's blocked.
