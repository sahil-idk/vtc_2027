# M7 Addendum — DT-Readiness Framing Audit & V2X-Specific Threshold Search (4-Agent Synthesis)

**Status:** research complete, synthesis below, **not yet applied** to `main.tex` · **Feeds into:** M7 (`M7_no_deployment_fully_passes.md`), and introduces four new candidate findings (M9–M12)

This document synthesizes four independent research passes commissioned to answer two questions: (1) is Gate 2's staged pipeline honestly framed as digital-twin *replication* rather than *accuracy-chasing*, and (2) does a better, V2X-specific citable RSRP accuracy threshold exist in the literature than the generic 3GPP UE-measurement spec TWINGATE currently uses? Two agents worked the literature-search question independently so their conclusions could be cross-checked rather than trusted from a single pass.

---

## Part 1 — The threshold question: what should M1's citation actually be?

### 1.1 What the literature search found (2 independent agents, converging)

**Agent B** re-examined the six V2X/C-V2X ray-tracing DT papers TWINGATE already cites (VaN3Twin, its 2026 real-time follow-up, Beyraghi, Rauf, Manukyan, Del Moro) specifically for a *stated acceptance criterion* (not just achieved error). **Finding: none of the six state one.** All validate either comparatively (beats a named baseline) or descriptively (reports an error, calls it "accurate"), never against a pre-declared numeric pass bar.

**Agent C** searched broadly beyond these six for any other V2X/C-V2X ray-tracing or simulation DT paper with a real-field-measurement validation and a stated threshold. Checked ~12 candidates. **Same conclusion, independently reached:** nothing cleanly matches TWINGATE's exact comparison type (single absolute predicted-vs-measured RSRP, unknown transmitter geometry). Best partial matches:
- **MART-6G** (arXiv 2502.14290) — states "power errors remain below 6 dB" for a ray-tracing DT validated against real field data including a V2V case — but the criterion is self-derived (same weakness class as TWINGATE's own 3 dB) and stated for the general task class, not the V2V case specifically.
- **"Demystifying VEINS"** (VTC2026, arXiv 2605.29988) — closest domain match, real V2X living-lab RSSI vs. simulated RSSI — but states no threshold at all, only that real trials commonly show ~5–6 dB mean RSSI offsets even uncalibrated.
- **Mavromatis et al. 2017** (arXiv 1710.02575) — explicitly *argues against* absolute-value RSRP/RSSI comparison in V2X validation, recommending trend-matching instead. Useful as a defensive citation, not a threshold source.

**Two independent agents concluding "no clean fit exists" is a real, load-bearing finding, not a search failure** — the literature genuinely appears not to have a directly-borrowable convention for this specific comparison type.

### 1.2 What the standards search found — a genuine positive result, with a caveat

**Agent D** searched V2X-specific standards (not generic cellular specs): 3GPP TS 22.186, TR 36.885/37.885, TS 23.285, ETSI ITS-G5, SAE J2945, IEEE 1609. **Items 1–6: nothing usable** — either no PHY-layer accuracy figures at all, or figures (BLER-vs-SNR curves, CCA thresholds, PER/CBR congestion targets) that don't translate into an RSRP accuracy tolerance without an undocumented derivation step.

**The positive result:** while chasing a lead, the agent downloaded and full-text-searched the actual primary-source PDF of **3GPP TS 36.133 Release 16.6.0** (via an accessible ATIS mirror — direct fetches of etsi.org/arib.or.jp/3gpp.org were blocked, same as in earlier research). It confirmed by direct quote that **TS 36.133 has a dedicated clause, §9.10, "V2X sidelink communication,"** with its own absolute RSRP-type accuracy requirements, distinct from the generic Uu (cellular-link) clause TWINGATE currently cites:

| Clause | Measurement | Normal condition | Extreme condition |
|---|---|---:|---:|
| §9.10.2.1 | S-RSRP (sync signal), stronger-signal regime | ±4.5 dB | ±9 dB |
| §9.10.2.1 | S-RSRP, weaker-signal regime | ±8 dB | ±11 dB |
| §9.10.3.1 | **PSSCH-RSRP** (measured on the actual sidelink data channel) | **±5 dB** | ±9.5 dB |
| §9.10.3.1 | PSSCH-RSRP, weaker-signal regime | ±8.5 dB | ±11.5 dB |

This is genuinely a stronger citation than what's currently used: it's the **right comparison type** (a single absolute measurement against a fixed accuracy envelope — not the two-cell differencing metric already investigated and correctly ruled out earlier), it's **explicitly V2X-scoped** in the standard's own terminology, and it's **primary-source-confirmed by direct quote**, not a secondary-source inference. (The agent also checked NR V2X: TS 38.133's analogous clause is marked "[TBD]" as of Release 16.4.0 — not yet finalized in that release, not checked further.)

### 1.3 The caveat neither literature-search agent could have caught, but matters

**§9.10 is scoped to PC5 sidelink** (direct vehicle-to-vehicle/vehicle-to-infrastructure communication) — **not Uu-mode** (phone-to-cell-tower network coverage). TWINGATE's actual measurement, `PCell_RSRP_max`, is Uu-mode: standard cellular network RSRP logged via MobileInsight from the UE's normal connection to a Deutsche Telekom/Vodafone tower. This project's own earlier literature scan (`DT_READINESS_LITERATURE_SCAN.md`) already established this explicitly: *"The Berlin V2X dataset backing TWINGATE is LTE Uu drive-test data only... no PC5/sidelink logs."*

So §9.10's figures don't literally govern TWINGATE's measurement interface — they're V2X-scoped in the standard's own terms, but for a different radio channel. Citing them as if they directly derive M1's threshold would repeat the same category of mismatch already caught and ruled out once before (the "relative RSRP accuracy" lead, which measured a different *comparison type*; this is a different *interface*, same underlying lesson: check the actual scope before citing).

**How to use it honestly:** as corroborating context, not as the primary derivation. Something like: *"Even the V2X-specific sidelink RSRP accuracy defined in the same specification (TS 36.133 §9.10.3.1, PSSCH-RSRP) is of a comparable order of magnitude (±5 dB normal condition) to the generic Uu figure used above, suggesting the chosen threshold is not an artifact of using the wrong measurement interface's accuracy figure."* This uses the finding for what it actually supports (consistency across V2X measurement types) without overclaiming direct applicability.

### 1.4 Revised recommendation for M7's threshold fix

Combining this with the earlier finding (checked in M7's original write-up: 6 dB is the *directly* correct citation for TWINGATE's comparison type, since M1 is a single-absolute-value comparison, matching the generic Uu absolute accuracy spec; but adopting 6 dB as the sole bar makes the criterion trivial, since even the no-physics Stage 0 baseline already clears it for both operators):

1. **Primary "hard pass" bar: 3GPP TS 36.133's generic Uu absolute RSRP accuracy, ±6 dB** — already correctly cited, correct comparison type, and every pipeline stage clears it for both operators. This is where TWINGATE gets to report an honest, standards-defensible "Yes."
2. **Corroborating V2X-specific context: TS 36.133 §9.10.3.1's PSSCH-RSRP accuracy (±5 dB)** — cited explicitly as showing the accuracy figure isn't an artifact of the wrong interface, with the Uu/PC5 distinction stated plainly so it can't be mistaken for a direct derivation.
3. **Self-imposed stretch target: keep ~3 dB (or revise toward half of the V2X figure, ~2.5 dB, if a tighter target is wanted), explicitly labeled as an internal engineering target, not a standards-derived one.** This is what actually differentiates the pipeline stages (Stage 0 doesn't get close; Stage 3/4 does) — 6 dB alone provides zero discrimination across the ablation.
4. **Explicitly state the literature gap** (§1.1 above) as the reason no V2X-DT-paper-derived threshold is being borrowed: the field doesn't have one to borrow, and pretending otherwise would be worse than owning that TWINGATE is proposing its own.

This is a refinement of, not a reversal of, the plan already on record in `M7_no_deployment_fully_passes.md` §7 — the two-tier (hard bar + stretch target) structure stands; this section adds a genuinely stronger, primary-source-confirmed V2X-specific corroborating citation, and closes the "is there literature precedent" question definitively (answer: no clean fit exists, confirmed by two independent searches).

---

## Part 2 — DT-readiness framing audit (Agent A)

Agent A read `main.tex` in full plus `A19_gate2_final.py`'s objective function, and produced four new candidate findings distinct from (but complementary to) M1–M7. Full detail in the agent's original report; summarized here with the proposed fixes.

### M9 — Gate 2's narrative reads as accuracy-chasing; the paper's best replication evidence is filed elsewhere and never cross-referenced

Table I and its surrounding prose narrate every stage purely in MAE terms. The one explicit physical-plausibility sentence for Operator 1 ("recovers sector azimuths spanning the full compass range and realistic rooftop/mast heights") is immediately followed, same paragraph, by a pivot back to "Stage 3 reaches 3.03 dB" — the two are never connected. Meanwhile the paper's *strongest* replication evidence — the twin-gate blind prediction of a 26.3 dB drop at a location the optimizer never saw — sits in the Discussion section and is never referenced from the Table I discussion, where a skeptical reader is actually forming their opinion.

**Proposed fix:** (a) soften "realistic rooftop/mast heights" to what was actually checked ("heights not clamped to the search-space boundary") and explicitly state the plausibility check is corroborating, not definitive, evidence; (b) add a forward-reference from §IV-C to the twin-gate blind-prediction evidence, ranking it explicitly as the primary fidelity evidence with M1 as necessary-but-not-sufficient supporting statistic. Full drafted replacement text in the agent's report.

### M10 — The optimizer's MAE-minimization objective is never stated as a proxy for the paper's actual geometric-recovery goal *(highest leverage, lowest cost of the four)*

Confirmed directly in code: `A19_gate2_final.py`'s Nelder-Mead objective is, literally and exclusively, calibrated training-day MAE. This is defensible — RSRP is the only observable available when tower topology isn't released, and correct geometry should predict real RSRP better than incorrect geometry under a faithful forward model — but **the paper never states this proxy relationship explicitly anywhere.** The reader is left to infer it from scattered pieces (the NeRF analogy, the "Physics, Not Curve-Fitting" discussion, the overfitting-check paragraph), none of which actually asserts "MAE is the proxy; geometric fidelity is the goal" as a stated methodological position.

**Proposed fix:** one paragraph inserted in §III-C-3 right after Eq. 4, explicitly stating the proxy relationship and flagging the known limitation (§III-C-3 already admits the objective is multi-modal in azimuth — i.e., MAE improvement is necessary but not sufficient evidence of correct geometric recovery). No new experiment required. Full drafted text in the agent's report.

### M11 — Missing per-tower / OSM-grounded position plausibility check

Nothing in the pipeline checks whether optimized tower *positions* land near a plausible physical siting location (an OSM building, mast, etc.) rather than wherever numerically minimizes MAE within the 500 m search box. The existing plausibility check (height/azimuth ranges) is aggregate and only computed for Operator 1 — Operator 2, which carries the paper's entire headline convergence result, doesn't get even that weaker check.

**Proposed fix:** a small new analysis (not new data — the OSM building layer and optimized coordinates already exist) computing each tower's distance to the nearest building footprint, reported alongside a check of whether this correlates with per-tower MAE improvement. Companion fix: extend the existing Op.1 aggregate sanity check to Op.2. This is the one item in this addendum that requires code/analysis work, not just prose — flagged for later, not blocking.

### M12 — The "Physics, Not Curve-Fitting" discussion defends itself using MAE deltas, risking circularity

§V's argument against the "this is just curve-fitting" objection uses, in part, an MAE-delta argument (removing Sionna costs 1.81 dB) — logically valid, but rhetorically self-referential given M10's gap. **Proposed fix:** one added sentence explicitly noting this argument establishes the calibration parameters alone can't explain the accuracy, but doesn't independently establish the *specific* recovered geometry is correct — pointing the reader to the twin-gate blind prediction as the evidence that actually does that. Minor companion fix to M9/M10.

---

## Recommendation

- **M7's threshold fix**: proceed with the two-tier structure already drafted (§7 of `M7_no_deployment_fully_passes.md`), now strengthened with the TS 36.133 §9.10 V2X-specific corroborating citation (used honestly, with the Uu/PC5 caveat stated). No further literature search needed — two independent passes converged on "no clean V2X-DT-paper threshold exists," which is itself the answer.
- **M10** should be applied alongside M7's fix — they interact directly (M10 reframes what Table I's M1 column is *for*; M7 reframes what its verdict *means*). Recommend doing them in the same edit pass.
- **M9, M12** are cheap, text-only, and complementary — good candidates for the same pass.
- **M11** requires actual analysis work (not just prose) — track separately, don't let it block the others.

**Not yet applied.** Awaiting review before any edit to `main.tex`.
