# Leftovers Requiring a GPU + Sionna Environment

Review items that are correctly diagnosed and have a clear fix path, but
can't be finished in this session because they need a full Sionna
ray-tracing rerun on a GPU machine — not available in this sandbox.
Tracked separately so they don't block the rest of the review, which is
all text-only or CPU-only fixes. Revisit these when a GPU environment is
available.

---

## M4 — Path A (real Train MAE numbers for Table I)

**Status:** blocked, not abandoned. Path B (the text-only fix) is already
applied — see `M4_overfitting_risk_ablation_table.md` for the full
writeup, §7 specifically for what's blocked and why.

**One-line summary:** Table I's ablation only shows held-out MAE per
stage, so a stage that overfits its added free parameters (height,
azimuth, scattering) to the training days would look identical to one
that genuinely recovers real tower geometry. The fix is to also show the
training-fit MAE next to it, so a reader can see the two move together
(good sign) rather than diverge (overfitting signature).

**Why it's blocked:** the training-fit MAE (`refined_opt_mae`) *looks*
already computed in `twingate/out/{device}_gate2_final.csv`, but a sanity
check against Table I's own published numbers failed: recomputing
Operator 2's weighted held-out MAE from those files gives 3.36 dB on 101
towers, not the paper's published 4.04 dB on 104 towers, and
`pc4_gate2_final.csv` doesn't exist in the repo at all. The checked-in
files are from a different or incomplete run than the one that produced
Table I. Using them anyway would introduce a new, worse inconsistency.

**What's needed to unblock:**
1. A machine with a GPU and Sionna/Mitsuba/DrJit installed (see
   `environment.yml` / `requirements.txt` at the repo root).
2. Run `python A19_gate2_final.py --device pc1`, `--device pc2`,
   `--device pc3`, `--device pc4` to completion (full mode, no
   `--dry-run`, no `--max-towers` cap). Expect this to take a while —
   the script itself notes 3-6 min/tower.
3. Confirm the resulting weighted `refined_val_mae` reproduces the
   paper's published Stage 4 numbers (3.02 dB Op.1 / 4.04 dB Op.2) within
   rounding, on the correct tower counts (124 Op.1 with 2 excluded, 104
   Op.2).
4. Only once that matches, pull the corresponding weighted
   `refined_opt_mae` (training MAE) into a new column or footnote in
   Table I, per the fix already drafted in
   `M4_overfitting_risk_ablation_table.md` §5 (Path A).

**Not needed:** any of the earlier Stage 0-2 scripts — the overfitting
risk is concentrated in Stage 3/4 where the free parameters (height,
azimuth) are actually added, per the original writeup's recommendation.

**Encouraging sign for when this rerun happens:** while verifying M5
separately (see `M5_twin_gate_independence_unexplained.md` §7), the
*same* partial/mismatched `pc2`/`pc3` files referenced above already show
the twin-gate predicted drop surviving zone exclusion (24.18 dB, Welch
$p=8.8\times10^{-52}$, in the same direction as the paper's published
26.3 dB) even though their aggregate MAE doesn't match Table I. That
doesn't unblock Path A on its own — the MAE mismatch and missing pc4
file are still real — but it's a reason to expect the eventual full
rerun will land close to the published numbers rather than surface a
new surprise.

---

## M11 — Per-tower OSM building-plausibility check

**Status:** blocked, compound cause. See `M11_osm_plausibility_check.md`
for the full writeup.

**One-line summary:** nothing in the pipeline checks whether an
optimized tower's *position* lands anywhere physically plausible (near
an actual building/mast) rather than just wherever numerically minimizes
training error. Fix needs the per-tower optimized coordinates plus the
OSM building-footprint layer used to build the Sionna scene.

**Why it's blocked — two independent causes, not one:**
1. **Same tower-coordinate gap as M4 above** — `pc4_gate2_final.csv` is
   missing, and pc1/pc2/pc3 don't reproduce Table I's published numbers.
2. **OSM building geometry is unreachable from this sandbox,
   independent of the GPU question.** `scene_operator{1,2}/` (the
   generated Sionna scene, gitignored) isn't present in this checkout,
   and the natural fallback — fetching the same public Overpass API data
   `03_build_sionna_scene.py` uses — is blocked outright: tested six
   hosts directly (`overpass-api.de`, `overpass.kumi.systems`,
   `overpass.openstreetmap.ru`, `overpass.private.coffee`,
   `www.openstreetmap.org`, `download.geofabrik.de`), all returned
   organization-policy connection rejections. This is a domain-family
   block, not a single flaky host.

**What's needed to unblock (in addition to M4's GPU rerun above):**
1. Complete M4's `A19_gate2_final.py` rerun for all four devices first —
   M11 needs the same complete, correct per-tower coordinates.
2. In that same environment, either (a) keep the generated
   `scene_operator1/scene.xml` and `scene_operator2/scene.xml` files
   after the rerun (they already contain the OSM-derived building mesh
   actually used for ray tracing — more faithful than a fresh OSM pull,
   since it's the exact geometry Sionna traced against), or (b) confirm
   that environment has outbound access to the public Overpass API.
3. For each tower's final `(refined_lat, refined_lon)`, compute distance
   to the nearest building footprint/mesh vertex; report per operator
   the fraction of towers within a plausible siting distance, and
   whether that correlates with per-tower MAE improvement.
4. Lower-cost companion, needs only step 1 (no OSM/network access):
   extend the existing Operator 1 aggregate height/azimuth plausibility
   check (already in `main.tex` after the M9 fix) to Operator 2.

**Relationship to M4:** M11 and M4 Path A unblock together — both need
the same completed GPU rerun. M11 additionally needs OSM building data
(or the retained scene files), so don't assume M4's rerun alone finishes
M11 too; the person running that rerun should be told to keep
`scene_operator1/` and `scene_operator2/` around afterward rather than
letting them get cleaned up as generated/gitignored artifacts.

**Not attempted:** any analysis using substitute/approximated building
geometry in place of the real OSM data — would produce numbers with no
real evidentiary value.
