# DT Readiness Literature Scan: What Published C-V2X Digital Twins Validate, and What TWINGATE Should Replicate

**Purpose.** TWINGATE currently validates *Uu-mode* (tower/network) coverage for C-V2X using C (Gate 1), M1 + M2 (Gate 2), and twin-gate convergence. This document surveys published Digital Twin implementations for C-V2X / vehicular cellular networks, extracts what scenarios and thresholds they use to validate themselves, and cross-references every candidate against what TWINGATE already has — so any addition deepens the existing readiness definition rather than bolting on a disconnected metric.

**Scope reminder (from this session's findings, restated here so this doc stands alone).** The Berlin V2X dataset backing TWINGATE is LTE Uu drive-test data only: RSRP/RSRQ/SNR/MCS/datarate at 1 Hz GPS resolution (confirmed: every `ts_gps` timestamp has exactly one row — no sub-second samples survive in the cleaned CSV), two operators, three days, no PC5/sidelink logs. Every candidate below is filtered through that constraint.

---

## 1. Executive Summary

**The single strongest, lowest-cost recommendation: add the multi-KPI corroboration of the Gate-1 dead zone (RSRQ/SNR/MCS/datarate, already computed this session) into the paper.** It costs nothing further, uses data already in hand, and is the only candidate here that directly strengthens *both* C and M2 simultaneously without new simulation.

**The strongest new-simulation candidate: handover / cell-boundary prediction accuracy.** No paper found does this specific thing (RT-predicted cell-boundary location vs. real handover location) for Uu-mode C-V2X, which makes it a genuine gap rather than a replication exercise — but the *motivation* for why it matters is well-grounded in the literature (Lucas-Estañ et al., published IEEE *Network* 2023, ties V2X service continuity directly to session/UPF handover behavior and cites exact 3GPP TS 22.186 reliability targets). It also converts a limitation TWINGATE already states in print (M2's cross-cell exclusion) into a contribution, rather than adding new scope.

**One important literature finding that changes the calculus on the M4 metric you're holding back:** VaN3Twin's real-time follow-up paper (Pegurri et al., arXiv 2601.16559) validates its C-V2X digital twin using *exactly* an LoS/NLOS transition-classification accuracy metric (their η_k) alongside RSSI MAE — i.e., a peer C-V2X DT paper treats LOS/NLOS classification as a first-class, citable DT-validation dimension, not a diagnostic side-note. This doesn't mean add M4 now (you asked to hold it), but it means M4 has real literature standing for whenever you revisit it — it is not an invented metric.

No published paper found translates a 3GPP V2X reliability/latency target (TS 22.186) into an RSRP/SINR coverage threshold usable directly by an RT-based DT — doing so requires a link-level (BLER-vs-SINR) simulation step that is a materially larger undertaking than anything else in this document. This is flagged in detail in §3–4 rather than recommended for the current scope.

---

## 2. Literature Table

| Paper | Venue (published/preprint) | RT tool | Uu / PC5 | Scenario / experiment | Threshold cited | Link |
|---|---|---|---|---|---|---|
| VaN3Twin (Pegurri et al., 2025) | arXiv preprint (already cited in TWINGATE bib as `pegurri2025van3twin`) | Sionna RT, in ms-van3t/ns-3 | Multi-RAT (incl. Uu) | Full-stack V2X NDT; validated packet-reception disagreement vs. field measurements | Self-defined: 50–70% reduction in packet-reception disagreement vs. stochastic models | [arxiv.org/abs/2505.14184](https://arxiv.org/abs/2505.14184) |
| **Predicting Networks Before They Happen** (Pegurri et al., 2026) | arXiv preprint | Sionna RT via VaN3Twin, real-time | Uu + PC5-like 60 GHz UP | Live Tokyo testbed, 3 vehicles; predicts RSSI **and** LoS/NLOS transitions ahead of a latency deadline | RSSI: max avg error **1.01 dB**, 95th-pct **3.05 dB**; LoS classification robustness η_k up to **100%** at low perturbation, degrading to **~75%** at 1 m position error | [arxiv.org/html/2601.16559v2](https://arxiv.org/html/2601.16559v2) |
| **DT-CoVeSS** (Twardokus & Rahbari) | **Published**, IEEE INFOCOM Workshops (DTwin 2025) | Sionna RT | **PC5 sidelink only** — explicitly "the first time" DT benefits reach sidelink C-V2X | High-fidelity multipath emulation for C-V2X security evaluation; automated scene construction from open geospatial data | Not a coverage-accuracy paper — security/fidelity focused, no RSRP threshold given | [ieeexplore.ieee.org/iel8/11152714/11152715/11152971.pdf](https://ieeexplore.ieee.org/iel8/11152714/11152715/11152971.pdf) |
| **Direct-V2X Support with 5G Network-Based Communications** (Lucas-Estañ et al.) | **Published**, IEEE *Network*, vol. 37, no. 4, pp. 200–207, 2023 | None (analytical E2E latency model, not RT) | Uu (V2N2V) | Analytical E2E latency model for Cooperative Lane Change (CLC) service over 5G, single- and multi-MNO | **3GPP TS 22.186**: CLC low automation — 90% of packets <25 ms; CLC high automation — 99.99% of packets <10 ms. Uses MCS target BLER 0.1 (low)/1e-5 (high) | [ieeexplore.ieee.org/document/10293232](https://ieeexplore.ieee.org/document/10293232) |
| Rauf et al. (2026) | arXiv preprint (already cited as `rauf2026kpi`) | Sionna RT | Uu | Sionna RT vs. real 5G OAI testbed VNA measurements | Self-defined KPI deviation; identifies material mismatch + near-field transition as dominant error sources | [arxiv.org/abs/2605.10352](https://arxiv.org/abs/2605.10352) |
| Beyraghi et al. (2025) | arXiv preprint (already cited as `beyraghi2025ris`) | Sionna RT | Uu | Calibrated RT for RIS placement, UK city cellular network | RSRP mean error reduced from −5.69 dB to −0.32 dB via material calibration (assumes known BS positions) | [arxiv.org/abs/2510.09478](https://arxiv.org/abs/2510.09478) |
| Manukyan et al. (2025) | arXiv preprint (already cited as `manukyan2025sionna`) | Sionna RT | Uu | Sionna RT fidelity vs. real 4G/5G measurements, Rome | Finds antenna position/orientation dominates over material choice — directly supports TWINGATE's Gate-2 geometry-first design | [arxiv.org/abs/2507.19653](https://arxiv.org/abs/2507.19653) |
| Del Moro et al. | arXiv preprint (already cited as `delmoro2025dt`) | N/A (analytical) | Uu | Site geometry vs. calibration uncertainty decomposition | Formal argument: geometric error dominates over calibration error | [arxiv.org/abs/2607.09334](https://arxiv.org/abs/2607.09334) |
| ITU-R P.2040-1 | Published ITU-R Recommendation | N/A | N/A | Effects of building materials/structures on radiowave propagation >100 MHz — cited by VaN3Twin real-time for concrete/wood/metal material assignment | Material property reference tables — an alternative/supplementary citation to 3GPP TR 38.901 for material parameterization | Cited via VaN3Twin real-time paper's reference [22] |

**Note on what's absent.** No paper was found — published or preprint — that (a) validates handover/cell-boundary prediction against real drive-test data using RT for Uu-mode cellular, or (b) translates a 3GPP V2X reliability target into an RSRP/SINR coverage acceptance threshold for an RT-based DT. Both are real gaps, not oversights in the search — see §4.

---

## 3. Citable Thresholds Found

| Threshold | Source | Already used by TWINGATE? | What using it further would require |
|---|---|---|---|
| ±6 dB UE RSRP measurement accuracy | 3GPP TS 36.133 | **Yes** — basis for the M1 < 3 dB criterion | — |
| LOS shadow-fading σ = 4 dB, NLOS σ = 6 dB (UMa) | 3GPP TR 38.901 | **Yes** — cited in M1 discussion; also the source of TWINGATE's scattering coefficient S=0.4 | — |
| CLC (Cooperative Lane Change): 90%/<25 ms (low automation), 99.99%/<10 ms (high automation); BLER targets 0.1/1e-5 | **3GPP TS 22.186**, via Lucas-Estañ et al. (published IEEE *Network* 2023) | No | A link-level BLER-vs-SINR curve to translate the latency/reliability target into an RSRP or SINR coverage threshold. Sionna RT alone gives geometry and path loss, not BLER — this needs Sionna's separate link-level/PHY module (LDPC coding, modulation, an explicit BLER simulation), which is new infrastructure for this project, not an RT parameter change. **Category (d) in §4.** |
| Material property tables for concrete/wood/metal | ITU-R P.2040-1 | No (TWINGATE currently uses TR 38.901's `itu_concrete` preset only) | Could diversify material assignment (e.g., distinguishing vehicle bodies as metal vs. buildings as concrete) if a scenario needs it — minor addition, not currently blocking anything |

---

## 4. Candidate Experiments

### 4a. Multi-KPI corroboration of the Gate-1 dead zone
**Feasibility: (a) — mostly already covered, remaining part is (b), trivial.** Already computed this session (RSRQ −5.5 dB, SNR −13 dB, MCS −9.2 index, datarate 13.4× lower, all p<10⁻¹⁴⁰ on held-out day 3, at the exact Gate-1 TypeB centroid). Zero new RT runs, zero new data. What's needed: write it into §IV.A (strengthens C — the dead zone is a multi-KPI, operationally real phenomenon, not an RSRP-gap labeling artifact) and into the M2 results section (strengthens M2 — ties predicted low RSRP to actual throughput collapse, the practical consequence the Introduction already motivates the paper around).
**How it deepens the existing definition:** turns C from "these gaps recur" into "these gaps recur *and* correspond to real service failure"; turns M2 from "the DT predicts a dip" into "the DT predicts where V2X communication effectively fails."

### 4b. Handover / cell-boundary prediction accuracy
**Feasibility: (b) — buildable, but real new methodology, not a quick add.**
No paper in the literature scan validates this exact thing for Uu-mode C-V2X with RT, which makes it more novel than replicative — but the motivation is well-grounded: Lucas-Estañ et al. (published, IEEE *Network* 2023) frames V2X service continuity explicitly around session/UPF handover events and cites concrete 3GPP TS 22.186 reliability numbers for exactly the kind of maneuver-coordination service (Cooperative Lane Change) that depends on uninterrupted connectivity during mobility.

What it needs against the existing pipeline:
- **Ground truth**: already exists and is unused for this purpose — Gate 1's TypeA (session-boundary/handover) events, currently only used to *exclude* rows from coverage-hole analysis.
- **New methodology required**: M2 currently excludes cross-cell RSRP ranking explicitly because per-tower OLS calibration (`b_i`, `α_i`) makes absolute predicted levels non-comparable across towers (this limitation is already stated in the current paper). A joint calibration approach is needed — e.g. a single shared `α` per operator with only `b_i` varying per tower, or a rank-based (not absolute-value) cross-cell comparison — so that "which tower does Gate 2 predict as strongest at this point" becomes a well-posed question.
- **Test**: at each Gate-1 TypeA event location, does the tower Gate 2 predicts as strongest change across the event, matching the real serving-cell change in the MobileInsight log?
**How it deepens the existing definition:** converts a stated limitation (M2's cross-cell exclusion) directly into a new validated capability, using data already collected. This is the most "deepening rather than adding" candidate found.

### 4c. LOS/NLOS transition tracking (M4, currently held back)
**Feasibility: (a) — already built and run (A17), held out of the paper per your instruction, not re-proposed here.**
New literature context only: VaN3Twin's real-time paper validates its own C-V2X DT using precisely this kind of metric (LoS/NLOS classification robustness, η_k, alongside RSSI accuracy) in a live urban 60 GHz V2X testbed. This is worth knowing for whenever M4 is revisited — it means the metric has direct peer precedent as a legitimate DT-validation axis, not something TWINGATE invented to pad the metric count. Not actioned further here per your explicit hold.

### 4d. 3GPP TS 22.186-grounded M2 threshold via link-level BLER simulation
**Feasibility: (d) — bigger undertaking, new simulation infrastructure.**
Would replace M2's empirically-derived −116 dBm threshold with one traceable to an actual C-V2X reliability requirement (e.g., CLC's 99.99%/BLER 1e-5). Requires: (1) a modulation/coding scheme assumption, (2) an SINR-to-BLER curve (link-level simulation — Sionna has a separate PHY/LDPC module for this, distinct from the RT module TWINGATE currently uses), (3) mapping the resulting required SINR back to an RSRP coverage threshold given a noise-floor/interference assumption. None of this exists in the current pipeline. Recommend treating this as a possible journal-extension item, not a near-term addition — the effort is comparable to building a second simulation subsystem, not tuning a parameter.

---

## 5. Explicit Out-of-Scope

- **PC5 sidelink validation.** The Berlin V2X dataset is Uu-only; DT-CoVeSS confirms sidelink C-V2X DT validation is a distinct research track with its own data requirements (commercial C-V2X sidelink hardware, different waveform properties) that this dataset cannot support. Not fixable by more Sionna runs.
- **Sub-second Doppler / fast-fading validation (M3).** Confirmed this session: the cleaned dataset has exactly one row per `ts_gps` timestamp (1 Hz). Coherence times at realistic V2X speeds are single-digit-to-tens of milliseconds — three orders of magnitude faster than the available sampling. No RT capability fixes a data resolution limit.
- **Dynamic companion-vehicle blocking.** Ruled out this session on cost/architecture grounds: Sionna's `Scene.add()` only accepts Transmitter/Receiver/RadioMaterialBase, not arbitrary meshes, so a moving vehicle blocker requires a full scene-XML reload per row; 94.5% of pc1 rows have a companion vehicle within 50 m/2 s, eliminating any batching shortcut. Not revisited here. (Note: VaN3Twin's real-time architecture shows this kind of dynamic-scene RT *is* achievable at production quality — but as a wholesale architecture built for it, not a bolt-on to TWINGATE's current batched pipeline.)
- **Multi-city generalization.** Single Berlin deployment; the paper already states this as a limitation. No literature substitute closes this — would need a second city's dataset.

---

## 6. Prioritized Recommendation List

1. **Add the multi-KPI dead-zone corroboration to the paper** (§4a). Zero marginal cost, strengthens C and M2 simultaneously, already computed.
2. **Scope and build handover/cell-boundary prediction** (§4b). Real new contribution, well-motivated by published literature (Lucas-Estañ, IEEE *Network* 2023) and directly converts a stated limitation into a capability. This is the recommended next big build after (1).
3. **Hold M4 as currently instructed**, but note its literature standing (VaN3Twin real-time, §4c) for whenever it's revisited — it is not a padding metric, it has direct peer precedent in a published-adjacent C-V2X DT paper.
4. **Defer the TS 22.186 / link-level BLER threshold work** (§4d) to a longer-horizon (journal extension) decision — it is real and citable but requires new simulation infrastructure disproportionate to the current paper's scope.
