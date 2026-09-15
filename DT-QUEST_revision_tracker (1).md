# DT-QUEST — ITSC 2026 Revision Tracker
**Manuscript 1179 · Status: rejected, revising for resubmission**
**Last updated:** this session (Berlin PC4 Type A/B check + dataset-scope decision)

> This file is the single source of truth for the revision. Update it every session. Do not rewrite paper prose until items marked 🔴 BLOCKING are cleared.

---

## 0. Reviews (verbatim reference)

> Full detailed breakdown below — self-contained, no need to reference the original prompt doc separately.

### Reviewer 1 (Review ID 3304)

**Overall verdict:** *"The paper is technically solid and relevant, and addressing these points would further improve its clarity, rigor, and presentation quality."* — no fundamental flaws identified; concerns are clarity, justification, and scope, not correctness. Lower-stakes than Reviewer 2, but still requires action.

| # | Point | What it's actually asking for |
|---|---|---|
| **R1.1** | Clarity and readability | Several sections have long, dense sentences; reduce dash overuse; simplify phrasing throughout. |
| **R1.2** | Sharpen the contributions statement | Contributions are relevant but not concisely stated. DT-QUEST's novelty *relative to existing data-quality and anomaly-detection approaches* needs to be more clearly emphasized — not just listed, but differentiated. |
| **R1.3** | Enhance reproducibility — justify thresholds | Explicit ask for justification of key numeric thresholds: **±3 dB** (cross-parameter consistency tolerance) and **95%** (constant-value screening cutoff) named directly. Implicitly extends to any threshold introduced later. |
| **R1.4** | Expand limitations and generalizability | Evaluation limited to **two datasets** and **urban scenarios at 5.9 GHz**. Wants clearer discussion of scalability — explicitly named: **high-mobility scenarios** and **different frequencies**. |
| **R1.5** | Minor structural/formatting fixes | Checklist, not open-ended: move Index Terms/Keywords after the abstract; fix sentence capitalization after line breaks; shorten figure titles/captions, move detail into main text; improve dense table readability; define all abbreviations at first occurrence. |

### Reviewer 2 (Review ID 3306)

**Overall verdict:** *"The problem is real and under-served, and the key insight that completeness is a poor quality proxy is well-illustrated. However, several issues need to be addressed before the paper is ready for publication."* — the framing and central insight are accepted; the *evidence* for several specific claims is found insufficient. This is the substantive review; every point requires new evidence or a retraction, not just rewording.

| # | Point | What it's actually asking for |
|---|---|---|
| **R2.1** | SUMO validation methodology insufficiently described | Three sub-asks: (a) 73–89% accuracy figures appear *before* the metric is formally defined — define it precisely, early. (b) Five iterative development phases tuned on the same two datasets raises overfitting concern — genuine property of the data, or artifact of fitting to these two datasets? (c) Explicitly asks: **was any held-out validation performed?** |
| **R2.2** | 16pp accuracy gap wrongly attributed entirely to completeness | PC1 and PC2–PC4 are **different vehicles** — different routes/environments/signal conditions confound the claim. Reviewer's proposed remedy: a **controlled experiment** — sub-sample PC1 down to PC2–PC4's completeness level and see if the accuracy drop reproduces. As submitted, the claim "overstates what the data supports." |
| **R2.3** | TiHAN corrections are circular | −75 dB SNR / +172.3 dB Rx Power corrections are **derived by aligning to 3GPP expected values**, then **validated against the same 3GPP model**. No independent ground truth exists. Ask: acknowledge directly, discuss how much confidence can actually be placed in the corrected dataset. |
| **R2.4** | Novelty vs. existing sensor-data-quality literature insufficiently articulated | Z-score, IQR, range-validation-against-known-bounds are **standard techniques**. Ask: state directly what a practitioner **could not** achieve by applying an existing framework (Teh et al. [17] named specifically) straight to V2X data, beyond the domain-specific 3GPP bounds in Table I. |
| **R2.5** | Only two datasets, each chosen to cleanly exemplify one trichotomy type — can't assess protocol completeness | No way to tell whether the five-check protocol catches everything, since the datasets were selected to each showcase one anomaly type. Ask: discuss known V2X quality failure modes **none of the five checks would catch**, state as an acknowledged limitation. |
| **R2.6** | "Generalizable, data-agnostic foundation" claim overstated | Framework only tested in **urban, 5.9 GHz, static/low-speed** scenarios. Already acknowledged in §V-E — reviewer's ask is narrower: **must also appear in the abstract and conclusion**, not just buried in limitations. |

### How this maps onto current status (cross-reference to §2 Open Items)

- **R2.2** — answered, and the answer *disproves* the original claim (MCAR experiment: 0.06pp effect, not 16pp). Needs a retraction, not a defense. See GZ-4.
- **R2.3** — TiHAN: demotion decided (§3), not yet written. Vienna analog (Senderkataster circularity): unresolved (§4).
- **R2.1(c)** — held-out validation: exactly what the WCL 60/40 split and GZ-3 null-test line of work answers. Mid-verification (real Sionna pipeline result pending).
- **R2.5** — directly what the Gap Classification Module's honest limitations (§6.6) speaks to, plus the general "failure modes not caught" subsection (GZ-10, still open).
- **R2.6 / R1.4** — Berlin-operator-split + Vienna-as-third-dataset (§1) is the direct answer; still needs the abstract/conclusion wording fix.
- **R1.3** — threshold justification table (GZ-8), not started, now has *more* thresholds to justify than originally (TVD cutoffs, recurrence distance, etc. from §6).

---

## 1. Dataset scope — DECISION MADE THIS SESSION

**Old scope:** TiHAN (India) + Berlin (Germany) — 2 datasets, both 5.9 GHz, urban only. This was R2.6's exact objection and part of R1.4.

**New scope, decided this session:**

| Dataset | Role | What it adds |
|---|---|---|
| TiHAN (India) | Illustrative Type-1 (value-offset) example only — **demoted**, see §3 | 5.9 GHz V2I, single vehicle |
| Berlin sidelink + cellular (Germany) | Primary case study, Type-2/Type-3 exemplar | 5.9 GHz + LTE Uu |
| **Berlin cellular, split by operator** | **New sub-analysis, not a new dataset** | Operator 1: 900–2600 MHz, bands {1,3,7,8}, mostly 20 MHz. Operator 2: 700–2600 MHz, bands {1,3,7,28}, mixed 10/15/20 MHz. **Verified via direct query — see §5.1.** Directly answers "only two datasets / limited bandwidth diversity" without new data collection. |
| **Vienna 4G/5G Drive-Test (Austria)** | **New third primary dataset** | LTE cellular, 3 operators, bands spanning 700 MHz–2.6 GHz(ish, TBD exact), externally-anchored TA-based tower positions (38.55 m RMSE / 27.95° azimuth error, validated — see §4). Widens frequency scope past 5.9 GHz V2X into full cellular Uu range. |

**Resulting claim for the paper:** "validated across three independently-collected datasets spanning two countries, three network operators beyond TiHAN's single vehicle, and a frequency range from 700 MHz to 5.9 GHz" — this is real, not aspirational, once §2's open items close.

**Review points this addresses:** R2.6 (scope), R1.4 (generalizability/scalability) — partially. Still urban-only across all three; still no high-mobility (100+ km/h) scenario. State that residual limitation explicitly, don't claim more than this.

---

## 2. Open items — ranked, with status

🔴 = blocking (nothing downstream can be finalized until this clears)
🟡 = in progress
🟢 = closed this session or earlier

| # | Item | Status | Owner review point |
|---|---|---|---|
| GZ-1 | Type A/B missingness, Berlin PC4 9,045-row gap | 🟢 **CLOSED this session** — see §5 | R2.2 (precondition for Gate-2 usability) |
| — | **SUMO removed as downstream fidelity validator (R2.1)** | 🟢 **DECIDED this session.** SUMO's accuracy check reduced to a distance-based 3GPP path-loss comparison wrapped in map-matching overhead — strictly dominated by the standalone 3GPP block + Sionna RT. Resolves R2.1(b) outright (overfitting concern moot, that pipeline no longer cited); simplifies R2.1(a) (MAE is well-defined, just needs early formal statement in §III — cheap text fix); R2.1(c) mechanism exists (60/40 split) but the number is still gated on GZ-3. **Open sub-decision, not yet answered:** keep any traffic/application-level claim at all (would need its own separately-scoped methodology), or retire SUMO to preprocessing-only/zero role. | R2.1 |
| GZ-3 | Null test: does random device exclusion also drop MAE ~1.3 dB? | 🟡 **PROXY TEST DONE — result is a YELLOW FLAG, see §5.3. Real Sionna-pipeline version still needed.** | Makes/breaks the Gate-2 result |
| GZ-5 | Tower-position sensitivity sweep (WCL jitter ±25/50/100m) | 🔴 Not started | Same |
| GZ-2 | Readiness-score vs. Sionna-MAE correlation across devices/towers (n>1) | 🔴 Not started, depends on GZ-3/5 | R2.4 (novelty) |
| GZ-7 | TiHAN circularity — demote or drop | 🟡 Decision made (demote), text not written | R2.3 |
| — | **Vienna tower-position circularity check** (does Senderkataster overlap the constraint set AND the validation set?) | 🔴 Not started — **new item, see §4** | R2.3 analog, Vienna-specific |
| — | **Vienna "Dec 3, 2025" duplicate-data block** | 🟢 **FOUND + FIXED this session — see §5.5.** Entire block confirmed as reconstructed duplicate of 4 earlier dates (99.96% accounted for); dropped. Corrected dataset: 847,839 rows (was 1,183,683). Coverage stats barely moved (47.9%→47.0%), nothing else needs correction. Flag to TU Wien authors alongside circularity question. | New — data integrity, affects any Vienna row-count citation |
| GZ-4 | 16pp claim retraction, write-up | 🟢 Evidence exists (MCAR experiment), text not written | R2.2 |
| GZ-8 | Threshold justification table | 🔴 Not started | R1.3 |
| GZ-10 | Failure-modes-not-caught limitations subsection | 🔴 Not started | R2.5 |
| R1.1/R1.5 | Mechanical (dashes, formatting, captions) | 🔴 Not started, do last | R1.1, R1.5 |
| — | **Sionna offset-fitting circularity check** — confirm the real pipeline's per-operator calibration offset is NOT fit against 3GPP-predicted values (would undermine the 3GPP/Sionna triangulation argument). My own GZ-3 proxy oracle *was* anchored to 3GPP for its offset — a property of the simplified proxy, not confirmed either way for the real pipeline. | 🔴 Not checked | R2.3 analog — triangulation argument validity |
| — | **V2AIX (ETSI ITS V2X message dataset, already cited as ref [15])** — candidate fourth dataset, no decision on inventory effort yet | 🔴 Not decided | R2.6/R1.4, if pursued |
| — | **Doppler / continuous ray tracing (Step 3 of Vienna redirect plan)** — agreed as good material, not decided if in-scope for this revision | 🟡 Deferred, not decided | Possible R2.4 strengthener, not required |
| — | **QuaDRiGa / hybrid stochastic multipath layer** | 🟢 Decided against for this revision — noted as future work only | N/A |

---

## 2A. Experiments still needed, with results that go directly into the paper (priority order)

| # | Experiment | Blocks | Status |
|---|---|---|---|
| 1 | **Real Sionna leave-one-out + bootstrap null** (GZ-3) — proxy version done (§5.3), real oracle version not | R2.1(c), R2.2's replacement claim, GZ-2, effectively everything downstream | 🔴 Not run — single highest priority |
| 2 | **WCL tower-position sensitivity sweep**, real oracle (GZ-5) | Credibility of the Gate-2 headline number | 🔴 Not run on real pipeline (proxy-only so far) |
| 3 | **Readiness-score vs. Sionna-MAE correlation, n>1 devices/towers** (GZ-2) | R2.4 (novelty) | 🔴 Not run, blocked on #1 |
| 4 | **Azimuth construction/holdout split**, Vienna | R2.3 (Vienna circularity, independent of TU Wien's answer) | 🔴 Not implemented |
| 5 | **Threshold sensitivity sweep** — original (±3dB, 95%, r>0.9, Z-score) + new Gap Classification Module thresholds (TVD cutoff, recurrence distance) | R1.3 | 🔴 Not started, list has grown since original scope |
| 6 | **Sionna offset-fitting audit** — confirm not anchored to 3GPP | Triangulation argument's validity | 🔴 Not checked (same item as row above, tracked once here) |

---

## 3. TiHAN decision

**Chosen: Option (a) — demote to illustrative Type-1 example.**
Paper keeps TiHAN as the exemplar for "value-offset errors undetected without external bounds," but adds an explicit sentence: *no independent ground truth exists to validate the −75 dB / +172.3 dB correction; this is presented as an illustrative case, not a validated result.* This directly matches what R2 asked for. Costs one honest sentence, keeps dataset diversity in the title's favor. No new work required — text-only fix, queue for §6 rewrite pass.

---

## 4. Vienna tower-position estimate — circularity risk, NOT yet resolved

Flagged in conversation, not yet checked against data:

- Vienna's LTE tower positions come from Eller et al. (2022) TA-based MLE localization, **constrained** during search to candidate sites from Austria's Senderkataster registry.
- Vienna's own validation (38.55 m RMSE / 27.95° azimuth) is against "reference metadata... available for part of the deployment" — **the paper does not specify whether this reference set is Senderkataster itself or independent operator-confirmed ground truth.**
- Eller et al.'s *original* 2022 method paper validated against 190 sites with **operator-confirmed** ground truth (stronger claim) — but it's unconfirmed whether Vienna's own dataset validation reused that same class of reference, or fell back to Senderkataster (weaker, circular risk).

**Action needed, not yet done:** Email TU Wien authors (Wiedner et al.) directly, ask: "Is the reference metadata used for the 38.55m RMSE validation independent of the Senderkataster candidate-constraint set used during estimation?" If yes → cite the number as-is. If no/unclear → describe Vienna's positions in the paper as *"plausibility-consistent with the constraining registry"* rather than *"validated against independent ground truth."*

**Azimuth-specific issue (separate, confirmed real):** Vienna computes sector azimuth as the RSRP-weighted centroid direction of the *same* phone measurements used later for fidelity comparison. **Must** split each tower's rows into a construction set (azimuth derivation) and held-out validation set before any Sionna comparison — same fix as Berlin's WCL circularity. Not yet implemented.

---

## 5. Session log — verified findings

### 5.1 Berlin operator/bandwidth split (verified via direct query on `cellular_dataframe_cleaned.csv`)

```
operator 1: 103,554 rows | bands {1,3,7,8} | freq 900–2600 MHz | mostly 20 MHz, small 5 MHz slice
operator 2: 103,880 rows | bands {1,3,7,28} | freq 700–2600 MHz | mixed 10/15/20 MHz
device↔operator mapping: PC1,PC4 → operator 1 | PC2,PC3 → operator 2
```
Confirmed real and usable as-is for the "dataset diversity" claim in §1.

### 5.2 Berlin PC4, 9,045-row missingness gap — Type A/B verification (GZ-1, CLOSED)

**Method:** reconstructed true time order via `ts_gps` (file is NOT stored in device/time order). Found missingness run-lengths on `PCell_RSRP_max`; confirmed the 9,045-row run matches prior working notes (indices 19947–28991, time span 2021-06-23 09:29:50 → 12:15:24, duration 2h45m).

**Four checks run, all pointing to instrumentation failure, not hazard zone:**

| Check | Result |
|---|---|
| GPS/altitude/speed present during gap? | 100% present (9045/9045) — vehicle was tracked continuously |
| Area-type composition inside gap vs. rest of PC4 | Inside: Residential 33.5% / Park 32.8% / Avenue 22.4% / Highway 10.8% / **Tunnel 0.5%**. Outside: 30.6% / 33.9% / 20.7% / 12.7% / **0.5%**. Near-identical — not tunnel-dominated. |
| Vehicle actually moving during gap? | 70.7% of gap rows have speed > 5 km/h, across highway/avenue/park/residential |
| Session-boundary alignment | `measurement` = 4 before gap → 5,6,7 during gap → 8 after. Outage spans 3 logged sessions, all operator 1, scenario A3U/platoon |
| All RF fields null simultaneously? | Yes — PCell_RSRP/SNR/RSSI/Cell_ID/Tx_Power AND SCell equivalents all 0/9045 non-null, while GPS/operator/scenario labels stayed populated |

**Conclusion: Type A (instrumentation/connectivity failure), not Type B (hazard zone).** Safe to treat as excludable missingness. AV-safety objection ("don't delete a tunnel and call it improved readiness") does not apply to this specific gap.

**What this unblocks, precisely:** the Gate-2 result (Sionna-oracle MAE 11.51→10.21 dB after excluding PC4) is now safe to build on. **It does NOT resolve R2.3 (circularity) or R2.2 (16pp gap) — those are separate, already-answered-elsewhere or still-open items.** See §2 for what's still required before this result is citable as evidence of anything (null test, sensitivity sweep).

**Reproducibility note:** run-length detection has a known numpy `is True` identity-comparison bug if reimplemented carelessly — use `== True` or plain bool cast, not `is True`, when re-deriving this on updated data.

**v2 dataset re-verification:** re-ran on `cellular_dataframe_cleaned_v2.csv` (columns `PCell/SCell_Uplink_Tx_Power_(dBm)_raw` dropped, `FLAG_range_PCell/SCell_RSRQ_max` added — everything the gap classifier uses is byte-identical to v1). Result: identical, same 1 gap on PC4, same TVD (0.030), same everything. File: `gap_classification_berlin_v2.csv`. **No change needed to any Berlin finding in this document.**

### 5.3 GZ-3 null test — proxy oracle result (⚠️ YELLOW FLAG, real Sionna re-run still required)

**Constraint:** the actual Sionna RT / WCL pipeline that produced 11.51→10.21 dB was built in a prior session; its code and tower-position artifacts were not available in this session. Ran an independent proxy instead — this is NOT a reproduction of the original result, it's a different, defensible check.

**Method:** rebuilt WCL tower positions from raw `cellular_dataframe_cleaned.csv` (RSRP-weighted centroid per `PCell_Cell_Identity`, cells with ≥5 obs), computed distance via haversine, predicted path loss via 3GPP TR 37.885 UMa-NLOS, derived measured path loss from RSRP with a single globally-fitted additive calibration offset (fit once on the full set, applied identically everywhere — same discipline as the real pipeline's per-operator offset). Script: `gz3_null_test_berlin.py` (in outputs).

**Result — leave-one-device-out on 187,736 rows, 299 estimated towers:**

| Excluded device | Rows excluded | MAE delta vs. baseline (12.826 dB) |
|---|---|---|
| PC1 | 57,302 | +0.524 dB (worse) |
| PC2 | 40,530 | +0.031 dB (~flat) |
| **PC4** | 32,426 | **+0.164 dB (worse)** |
| **PC3** | 57,478 | **−0.755 dB (biggest improvement)** |

**Bootstrap null (500 random same-sized row exclusions, unrelated to device):** mean +0.000 dB, std 0.010 dB, 95% CI [−0.019, +0.018] dB. PC4's actual delta (+0.164 dB) sits at the **100th percentile, z ≈ +16.5** — statistically far from chance, but in the **wrong direction**: under this oracle, excluding PC4 does not improve fidelity, it slightly hurts it. PC3 — never flagged by the >1%-gap rule — is the device whose exclusion actually helps most.

**Robustness check:** result is stable across 5 configurations (min-obs-per-cell 5 vs 20, distance cap 2000m vs 5000m, assumed EIRP 40/43/46 dBm — EIRP cancels via the offset fit as expected). Not a fragile artifact of parameter choice.

**What this means, precisely:**
- Does **not** disprove the Sionna-oracle result — different oracle (parametric urban model vs. ray-traced real geometry), legitimately can disagree. PC4's specific routes may pass through geometry only ray tracing resolves.
- **Does** mean the "excluding PC4 improves fidelity" claim is **not robust across independent physics oracles** — exactly what GZ-3 was designed to catch, and it's a genuine yellow flag, not a clean pass.
- **Before 11.51→10.21 dB goes in the paper as evidence of anything**, this exact leave-one-out + bootstrap-null test needs to be rerun **inside the actual Sionna pipeline**, checking all four devices, not just PC4. If PC3 also wins there, the current Gate-2 headline result is not usable as stated and needs to be replaced or reframed around whichever device (if any) survives.

### 5.4 Gap Classification / Triage Module — generalized beyond PC4, new architecture component

**Motivation (from conversation):** the DT-readiness architecture needs to distinguish *instrumentation failure* (safe to exclude) from *genuine environmental coverage dead zones* (must be preserved/flagged, never deleted — this is the actual AV-safety-relevant signal). §5.2's PC4 check was n=1; generalized the same 4-signal test across all 4 devices at a lower detection threshold (≥0.1% of device rows) to see if the classifier holds up on more than one case.

**Result — 6 gaps found total (script + full table: `gap_classification_table.csv`, `gz3_null_test_berlin.py` reusable for the WCL/distance scaffolding):**

| Device | Gaps | Length range | Area-composition TVD* | Dominant area | Session-boundary aligned |
|---|---|---|---|---|---|
| PC4 | 1 | 9,045 rows | **0.030** (matches route mix) | Residential, 33.5% (not dominant) | Yes |
| PC2 | 5 | 51–111 rows | **0.667** (every gap identical, wildly different from route mix) | **Park, 100% every single gap** | No (4 of 5) |
| PC1, PC3 | 0 | — | — | — | — |

*TVD = total variation distance between the gap's area-label composition and the device's overall route composition. Switched from chi-square p-value after finding p=0.000 at n=9,045 was a large-sample-size artifact (statistically "significant" for a practically tiny difference), not a real discriminator — TVD is the honest, scale-invariant version.

**Decisive additional check — location recurrence:** pulled GPS midpoints for all 5 PC2 gaps. **3 of the 5 occur at the identical coordinate (52.514, 13.348) on three separate calendar days** (June 22, June 23, June 24). An instrumentation glitch does not reproduce at the same physical location on different drive-throughs; a terrain-based propagation effect does.

**Physical corroboration — OSM Overpass query at (52.5143, 13.3480):** confirmed `natural=wood` (broadleaved), `tree_row`, `scrub`, and adjacent `wetland=marsh` at that exact site. Dense broadleaved canopy is a well-documented real RF attenuation mechanism. This is not circumstantial — three independent signals (statistical composition, cross-day recurrence, physical land-cover data) all point the same direction.

**Conclusion: PC4 = Type A (instrumentation failure, safe to exclude). PC2's 5 gaps = Type B (genuine environmental dead zone — must be flagged and retained, not deleted).** The classifier generalizes correctly on the first out-of-sample test.

**New architecture component for the paper — "Gap Classification / Triage Module":**
Sits immediately after V4 (completeness profiling), before any exclusion/correction decision. For every structurally-missing run:
1. Compute area-composition TVD vs. the device's overall route mix.
2. Check session/logging-boundary alignment.
3. Check cross-pass location recurrence (same GPS coordinate, repeat dropout, independent day/session).
4. (Optional, strong corroboration) cross-check against OSM land-cover tags at the location.

**Classification rule (draft, needs threshold justification pass — add to GZ-8):** Type A if TVD is low AND aligned to a session boundary. Type B if TVD is high AND not session-aligned AND (ideally) recurs across independent passes. Ambiguous otherwise → flag for manual review, do not auto-classify.

**Downstream consequence — this is the actual novel contribution.**

**REVISED THIS SESSION — the row-level flag is a column, not a bypass.** Original design routed Type-B gaps around the pipeline into a separate "Flagged Hazard-Zone Density" side metric. Corrected design, per direct feedback: **hazard-zone awareness is a component of DT-readiness itself, not a side output** — a dataset that correctly identifies and retains its dead zones is *more* DT-ready than one that doesn't, even though those specific rows carry degraded signal. Completeness and readiness are different axes; a Type-B row is "incomplete" in the naive sense but not "unready" — it's a rare, hard-won negative-result data point, and penalizing it for missingness punishes the dataset for correctly reporting reality.

**Schema change:** every row gets a `dt_confidence_class` column ∈ {`measured`, `type_a_gap_excluded`, `type_b_hazard_zone`, `ambiguous_gap`}. This travels *with* the row through the rest of the pipeline instead of forking off:
- **Type A rows:** flag persists, row excluded from calibration/training *by filter*, not deletion — still physically present, just marked "don't fit on this."
- **Type B rows:** flag persists, **never** filtered by default, and — critically — **no correction or imputation is ever applied.** There is no legitimate correction for a genuine dead zone; the true value there really is near-zero signal. Running V5/offset correction on it would mean manufacturing fake data.
- **Ambiguous:** flag persists, downstream tools decide per use case.

**Readiness score component (new):** *Hazard-Zone Awareness*, corroboration-weighted (recurrence count, OSM cross-check, TVD magnitude) rather than raw flagged-row count — a raw count is gameable (mislabel ordinary noise as Type B to inflate the score); weighting by corroboration strength closes that gap.

**Extension enabled by the column-based design (new, not in original spec):** Type B rows are locations with unusually high confidence about the true outcome (near-zero signal), so they double as an **implicit no-signal ground-truth check on the ray-tracing oracle** — does Sionna's simulated coverage also predict degraded signal at those exact flagged coordinates? Agreement is real evidence the twin captures genuine physical effects (foliage, geometry) and should count *toward* fidelity confidence; disagreement (oracle predicts strong signal at a confirmed hazard zone) is a red flag the reconstruction is missing something, and should count *against* readiness. This is a genuinely new, testable fidelity sub-check, not just a documentation requirement.

**New companion metric, redefined:** not a standalone hazard-zone-density side output — folded into the readiness score as the Hazard-Zone Awareness component above. Diagram updated to reflect this (Type B arrow now feeds into V5/corrections labeled "flag stays, no correction applied," and the final output block is "DT-Readiness Score + Hazard-Zone Awareness," not a separate box).

**Still needed before this goes in the paper:** exact TVD/recurrence thresholds need justification (not just "looked right on 6 examples") — feed into GZ-8. Test on Vienna once tower/gap analysis is done there, for a second independent generalization check.

### 5.5 🔴 MAJOR FINDING — Vienna's "Dec 3, 2025" block is a confirmed duplicate, not new data

**This resolves the "timestamp outside Vienna's stated collection window" anomaly flagged earlier in this project** (paper states collection ran March 2024–March 2025; `phone_data_lte.parquet` contained a large block dated December 2025, previously noted as unverified). That anomaly is now explained decisively, not just flagged.

**How this was found:** while attempting the Vienna generalization test for the Gap Classification Module (§6.6 item 2), an initial cross-operator-simultaneity check on Dec 3, 2025 data surfaced a suspicious exact match — two rows from Oct 27, 2024 and Dec 3, 2025, same operator, same coordinates to 6 decimal places, same time-of-day to the millisecond. Followed it all the way through rather than treating it as noise.

**Verification, in order:**

1. **Operator-A-only check:** of 39,513 rows sharing an exact millisecond time-of-day between Oct 27, 2024 and Dec 3, 2025, **39,256 (99.4%) had identical latitude, longitude, and RSRP** (diff < 1e-6). Not explainable by chance at that precision and volume.
2. **All-operator check:** 141,372 rows (42.1% of the entire Dec 3, 2025 block) were confirmed exact duplicates of Oct 27, 2024, across all three operators.
3. **Full-scope check — which dates "Dec 3, 2025" actually comes from:**

| Source date | Rows duplicated into "Dec 3, 2025" | % of that source date |
|---|---|---|
| Oct 26, 2024 | 63,046 | 66.2% |
| Oct 27, 2024 | 141,372 | 54.8% |
| Oct 28, 2024 | 106,860 | 55.5% |
| Mar 8, 2025 | 24,135 | 99.5% |
| **Sum** | **335,413** | — |

Dec 3, 2025's actual row count: 335,558. **335,413 / 335,558 = 99.96% accounted for.** The entire block is a reconstructed concatenation of four earlier real sessions — almost certainly a data-export/reprocessing artifact (e.g., a repackaging step that mislabeled a processing/export timestamp as the measurement timestamp) — **not new data collected in December 2025.**

**Correction applied — full "Dec 3, 2025" block dropped (whole date, not a partial per-row dedup):**

| | Before correction | After correction |
|---|---|---|
| Total rows | 1,183,397 | **847,839** (−28.4%) |
| Row-level tower coverage (all operators) | 47.92% | **47.04%** |
| Date coverage | Oct 2024, Feb 2025, Mar 2025, "Dec 2025" | Oct 2024, Feb 2025, Mar 2025 only |

**Reassurance — nothing else in this document needs retroactive correction.** Coverage-percentage stats reported earlier in this project (47.9% overall, per-operator breakdowns) move by less than 1 point once the block is dropped — those findings stand. **What does need correcting everywhere Vienna's dataset size is cited: 847,839 unique rows, not 1,183,683.**

**Cleaned file:** `phone_data_lte_TRULY_clean.parquet` (in outputs).

**Action needed:** flag to the TU Wien authors alongside the §4 circularity question — may affect their own published statistics too — and this needs a footnote in our paper regardless of their response, since we cite this dataset directly.

---

## 6. Architecture Specification — Gap Classification / Triage Module (full detail)

> This section is written at paper-ready detail — pull directly from here for the Methods/Architecture section draft. Supersedes the short version previously in §5.4; that section is kept for the session log/provenance trail, this one is the canonical spec.

### 6.1 Motivation and where it sits in the pipeline

The original DT-QUEST framework's five checks (V1–V5, Fig. 1 of the submitted manuscript) end at **V4 — Completeness Profiling**, which distinguishes random gaps from *structured* ones via co-missingness and run-length analysis, but stops there: it flags a structured gap and hands it straight to the correction stage (Fig. 1's "Flag & Document" path), which currently treats all structured missingness identically.

This is the exact gap Reviewer 2 pointed at implicitly with the AV-safety framing in the paper's own introduction: *"For Level 4–5 autonomous vehicles, communication dropouts during maneuvers like merging or emergency braking can be catastrophic."* A structured gap caused by a modem crash and a structured gap caused by driving under dense tree canopy are **statistically similar** (both are contiguous, both correlate with something) but **operationally opposite**: one is noise to remove before training a fidelity model, the other is the single most safety-relevant thing the digital twin could represent.

**The Gap Classification / Triage Module is inserted between V4 and the correction stage.** It does not replace V4 — it takes V4's output (a list of structured missingness runs) and adds a second-stage decision: *is this gap safe to exclude, or does it need to be preserved as a modeled hazard zone?*

Updated pipeline order:
```
V1 Range validation → V2 Cross-parameter consistency → V3 Constant-value screening
→ V4 Completeness profiling (detects structured gaps)
→ [NEW] Gap Classification / Triage Module (classifies each structured gap: Type A / Type B / Ambiguous)
→ V5 Unit verification
→ Type-specific corrections:
      Type A gap  → Flag & Exclude (existing "Flag & Document" path, safe to drop from calibration/training)
      Type B gap  → Flag & PRESERVE (new path — retained in the DT output as a documented low-confidence /
                     hazard-zone region, never dropped from the final twin)
      Ambiguous   → Flag for manual review, do not auto-classify either way
```

### 6.2 The four signals — formal definitions

For every structured missingness run *g* (a contiguous block of rows on a given device where the target RF field, e.g. `PCell_RSRP_max`, is null), define:

**Signal 1 — Area-composition Total Variation Distance (TVD).**
Let the device's overall route have an area-label distribution $P_{\text{route}}$ (proportions across categories: Residential, Park, Avenue, Highway, Tunnel, etc.), and let the gap itself have area-label distribution $P_{g}$ over the same categories. Define:
$$\text{TVD}(g) = \frac{1}{2}\sum_{c \in \text{categories}} \left| P_g(c) - P_{\text{route}}(c) \right|$$
Range: $[0, 1]$. TVD → 0 means the gap's terrain-type mix looks like a random slice of the whole drive (consistent with an instrumentation failure, which has no reason to correlate with terrain). TVD → 1 means the gap is dominated by a narrow terrain profile the rest of the route doesn't share.

*Why TVD and not a chi-square goodness-of-fit test:* chi-square p-values are sample-size-sensitive — on PC4's 9,045-row gap, chi-square returned p = 0.000 for a difference (33.5% vs. 30.6% Residential, etc.) that is practically negligible. At large N, chi-square will flag essentially any nonzero deviation as "significant," making it useless as a discriminator here. TVD is scale-invariant and reports magnitude directly, which is what the classification actually needs.

**Signal 2 — Session-boundary alignment.**
Let $s(i)$ be the logged session/measurement-round identifier (`measurement` column) for row $i$. For a gap spanning rows $[i_{\text{start}}, i_{\text{end}}]$:
$$\text{boundary\_aligned}(g) = \left[ s(i_{\text{start}} - 1) \neq s(i_{\text{start}}) \right]$$
True if the gap begins exactly where a new logging session starts (consistent with a device/modem restart producing a clean dropout at a session boundary). False if the gap begins mid-session, with no logging-side event to explain it.

**Signal 3 — Location recurrence across independent passes.**
Define a "pass" as a distinct calendar day (or, more strictly, a distinct top-level measurement session, if the dataset's session granularity supports it). For each gap $g$, compute its GPS midpoint $(\text{lat}_g, \text{lon}_g)$ (median of in-gap coordinates). Two gaps $g_1, g_2$ from **different passes** are considered *recurrent at the same location* if:
$$\text{haversine}\big((\text{lat}_{g_1}, \text{lon}_{g_1}), (\text{lat}_{g_2}, \text{lon}_{g_2})\big) < d_{\text{recur}}$$
for a distance threshold $d_{\text{recur}}$ (empirically, the confirmed PC2 recurrence was <5 m apart across three separate days — a conservative default of $d_{\text{recur}} = 50$ m is proposed pending a formal sensitivity check, see §6.6). This is **the decisive signal**: an instrumentation fault has no mechanism to reproduce at the same physical coordinate on a different day; a terrain-based propagation effect does, by definition.

**Signal 4 — GPS/telemetry continuity during the gap.**
$$\text{gps\_present}(g) = \frac{1}{|g|}\sum_{i \in g} \mathbb{1}[\text{Latitude}_i \text{ is not null}]$$
Not independently diagnostic (both Type A and Type B gaps can have full GPS continuity — the device usually keeps tracking position even when the cellular radio drops), but a **necessary precondition**: if GPS is also absent, the gap may instead indicate a full device power-off, which is a third category (equipment-off, not equipment-fault-while-running) requiring different handling — worth a footnote rather than folding into Type A/B directly.

### 6.3 Classification decision rule (draft — pending formal threshold justification, GZ-8)

```
INPUT: structured gap g, with signals TVD(g), boundary_aligned(g), recurs(g), gps_present(g)

IF gps_present(g) < 0.5:
    CLASSIFY g as "Equipment-off" (separate footnote category, not Type A/B)

ELSE IF TVD(g) <= τ_TVD  AND  boundary_aligned(g) == True:
    CLASSIFY g as Type A (instrumentation failure)
    → safe to exclude from calibration/training data

ELSE IF TVD(g) >= τ_TVD_high  AND  boundary_aligned(g) == False  AND  recurs(g) == True:
    CLASSIFY g as Type B (environmental dead zone)
    → MUST be preserved in DT output, flagged, never deleted

ELSE:
    CLASSIFY g as "Ambiguous"
    → flag for manual review; do not auto-classify in either direction
```

**Thresholds used in the worked example (§6.4), not yet formally justified:** $\tau_{\text{TVD}} \approx 0.05$ (PC4's 0.030 clears it), $\tau_{\text{TVD-high}} \approx 0.5$ (PC2's 0.667 clears it), $d_{\text{recur}} = 50$ m. These are currently "looked right on 6 examples," not sensitivity-tested — **this is explicitly flagged as needing the same rigor as the paper's other five thresholds (±3 dB, 95%, etc.) — see GZ-8, §2.**

### 6.4 Worked example (the actual data this rule was built and tested on)

| Device | Gap | Length | TVD | Boundary-aligned | Recurs (different day, <50m) | GPS continuity | → Classification |
|---|---|---|---|---|---|---|---|
| PC4 | 1 gap | 9,045 rows (20.9% of device) | 0.030 | Yes | No | 100% | **Type A** |
| PC2 | gap @ (52.51566, 13.36973) | 111 rows | 0.667 | Yes | — (isolated location) | 100% | Ambiguous (boundary-aligned but high TVD — flag for review) |
| PC2 | gap @ (52.51425, 13.34688) | 80 rows | 0.667 | No | **Yes** — matches next two rows | 100% | **Type B** |
| PC2 | gap @ (52.51431, 13.34799) | 66 rows | 0.667 | No | **Yes** | 100% | **Type B** |
| PC2 | gap @ (52.51432, 13.34804) | 64 rows | 0.667 | No | **Yes** | 100% | **Type B** |
| PC2 | gap @ (52.50724, 13.34788) | 51 rows | 0.667 | No | No | 100% | Ambiguous |

Note on re-reading the raw table: the three recurring PC2 gaps (80, 66, 64 rows) sit within ~15 m of each other across June 22, 23, and 24 — three independent drive-throughs of the same physical point, three dropouts. The other two PC2 gaps (111 rows, 51 rows) share the gap's local signature (100% Park, high TVD) but were only observed once each in this dataset — correctly flagged Ambiguous rather than Type B under the strict recurrence rule, since a single occurrence can't yet rule out a one-off cause. **This is the rule working as intended** — it doesn't over-claim Type B status without the corroborating repeat observation.

**Physical corroboration (independent of the statistical rule):** OSM Overpass query at the recurring coordinate (52.5143, 13.3480) returned `natural=wood` (broadleaved), `tree_row`, `scrub`, and adjacent `wetland=marsh`. Dense broadleaved canopy attenuation is a documented real propagation mechanism — this is a third, independent line of evidence agreeing with the statistical classification, not required by the rule itself but a strong sanity check worth keeping in the pipeline as an optional corroboration step for any dataset where OSM coverage is good (all three of TiHAN/Berlin/Vienna's coverage areas qualify).

### 6.5 Downstream consequence — the actual novel contribution

**For Type A gaps:** unchanged from the current "Flag & Document" path — excluded from any calibration, training, or fidelity-comparison dataset, exactly as PC4 was for the (still-unverified, see GZ-3/§5.3) Gate-2 result.

**For Type B gaps — this is new:** must be retained in the digital twin's final output as an explicitly-documented low-confidence / degraded-coverage region. Concretely, this means:
- The region is **not** deleted from any downstream simulation or coverage map.
- It is tagged with a confidence flag (e.g., "measured dead zone, N independent confirming passes, physical corroboration: [wood/tunnel/underpass/etc.]").
- If the ray-tracing oracle (Sionna) is available for that region, it can optionally attempt to *explain* the dead zone physically (e.g., adding a foliage-attenuation material property to the affected building/vegetation geometry) rather than just flagging it — a natural extension, not required for the base module.

**New companion metric — Flagged Hazard-Zone Density.** Alongside the existing coverage-entropy readiness score, define for a given route/device:
$$\text{HZD} = \frac{\sum_{g \,:\, \text{class}(g) = \text{Type B}} |g|}{\text{total route rows}}$$
— the fraction of the route classified as a genuine, confirmed communication dead zone. This is a **safety-relevant output in its own right**, independent of and complementary to the readiness/coverage score: a route can have excellent data-completeness readiness and still contain real dead zones the AV will drive through. Reporting HZD alongside the readiness score directly answers "does this framework treat real coverage gaps as a signal to preserve, not just noise to clean" — which was the open question this whole module was built to answer.

### 6.6 What still needs to happen before this is paper-ready

1. **Threshold justification (feeds GZ-8):** $\tau_{\text{TVD}}$, $\tau_{\text{TVD-high}}$, and $d_{\text{recur}}$ are currently set by inspection of 6 examples, not derived or swept. Minimum bar before submission: a sensitivity sweep showing the PC4/PC2 classification is stable across a reasonable range of each threshold (e.g., $\tau_{\text{TVD}} \in [0.02, 0.10]$, $d_{\text{recur}} \in [20\text{m}, 100\text{m}]$).
2. **Second independent generalization test on Vienna — ATTEMPTED, result: inconclusive, and for an interesting reason.** Vienna has no `area` labels (Signal 1 unavailable at all), so the test used a proxy detection method: silent time-gaps (>30s, vs. ~0.3–0.5s median cadence) instead of null-value runs, since Vienna's `rsrp_dbm` field has **zero missing values** — rows are apparently only logged when a serving-cell reading is decodable, unlike Berlin's raw retention of null-RF rows during real dropouts. First pass surfaced what looked like a strong finding (11 cross-operator-simultaneous gap clusters, mostly on "Dec 3, 2025") — **this turned out to be entirely an artifact of the duplicate-data issue found in §5.5.** Once the confirmed-duplicate "Dec 3, 2025" block was fully removed, only **2 genuine candidate gaps remained in the entire cleaned Vienna dataset, with zero cross-operator simultaneity and zero cross-day recurrence.** Honest conclusion: **Vienna's release structure does not produce Berlin-style structured missingness at all** — not a failure of the classifier, but a real difference in how the two datasets retain (or don't retain) failed-connection rows. This is itself a valid, citable limitation: the module's Signal 1 and its core detection method both require a dataset that (a) has terrain/area labels and (b) retains null-valued rows during real signal loss — Vienna satisfies neither. State this explicitly in the paper rather than forcing a second test that the data doesn't support.
3. **Formal statistical test for Signal 3 (recurrence)** beyond a fixed distance threshold — worth considering a proper spatial clustering approach (e.g., DBSCAN on gap midpoints with day-of-pass as a categorical constraint) rather than pairwise distance checks, once more than 6 gaps are available to test against.
4. **Explicit limitation to state in the paper:** this module depends on (a) an `area`-type label being present in the dataset (TiHAN has none — Vienna has none either, only Berlin does) and (b) enough independent passes over the same route to test recurrence (single-pass datasets like TiHAN's one-vehicle collection cannot use Signal 3 at all). State this as a known applicability boundary, not a silent gap.
5. **Relationship to the existing Data Quality Trichotomy needs a wording update.** This module doesn't add a fourth anomaly type — it **bifurcates Type 3 (Completeness Errors)** into two operationally distinct subtypes (3a: recoverable/instrumentation, 3b: environmentally-genuine/must-preserve). The paper's trichotomy language and Fig. 1 diagram both need updating to reflect this split, not a full rewrite — flag for the §V rewrite pass.

---

## 7. Next actions, in order

0. **NEW — Gap Classification Module (§6).** Threshold justification pass (§6.6, item 1) → feeds GZ-8. Vienna generalization test done, result is a documented limitation not a pass (§6.6, item 2) — no further action needed there beyond writing it up.
1. **GZ-3 — rerun the leave-one-out + bootstrap null INSIDE the real Sionna pipeline** (proxy version done, see §5.3 — result is a yellow flag, not a resolution). This is now the single highest-priority open item; the Gate-2 headline number cannot be used until this runs on the actual oracle.
2. **GZ-5 — WCL tower-position sensitivity sweep** on Berlin, ±25/50/100 m jitter. (Note: a fresh WCL implementation now exists in `gz3_null_test_berlin.py` and can be reused/extended for this.)
3. **Vienna circularity check + duplicate-data disclosure** — email TU Wien authors per §4 AND §5.5 together; in parallel, implement construction/holdout row split for azimuth regardless of their answer, and use the corrected 847,839-row count in any future Vienna work.
4. **GZ-2 — readiness-score vs. fidelity correlation**, once 1–3 give a trustworthy per-tower MAE.
5. Draft §V-D "Tower-Position Uncertainty as a Bounded Input" section (content outline already agreed in conversation, not yet drafted).
6. GZ-8 threshold table (now includes §6.6 item 1's thresholds too), GZ-10 limitations subsection, GZ-4 retraction text, TiHAN demotion text (§3).
7. Response-to-reviewers letter — only after 1–6.
8. R1.1/R1.5 mechanical pass — last.

---

## 8. Files/data referenced this session

- `cellular_dataframe_cleaned.csv` — Berlin cellular, 207,434 rows, 171 columns, includes `area` (with real `Tunnel` label), `ts_gps`, `operator`, `measurement` (session id), per-PCell/SCell RF fields. **Not time-sorted in file order** — always resort by `ts_gps` within device before any sequential/run-length analysis.
- `cell_info_final_lte.csv`, `phone_data_lte.parquet` — Vienna, per earlier inventory (see prior session notes — 1,597 LTE tower rows / 159 unique eNB, 1,183,683 phone rows, 47.9% row-level tower-match rate).
- Vienna city model rasters (BKM/GLM) — inventoried, not yet used in a scene build.
- `gz3_null_test_berlin.py` — WCL + 3GPP-proxy-oracle + leave-one-out + bootstrap null, reusable scaffolding for GZ-3 and GZ-5.
- `gap_classification_table.csv` / `gap_classification_berlin_v2.csv` — full 6-gap Berlin tables underlying §6.4 (v1 and v2, confirmed identical).
- `phone_data_lte_TRULY_clean.parquet` — Vienna, "Dec 3, 2025" duplicate block fully removed, 847,839 rows. **Use this file, not the raw upload, for any further Vienna work.**
- `vienna_gaps_TRULY_clean.csv` — the 2 genuine (non-duplicate-artifact) candidate gaps found in cleaned Vienna data, underlying §6.6 item 2's conclusion.
