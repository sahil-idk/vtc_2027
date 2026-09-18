# TWINGATE Paper — Methodology & Curation Review TODO

Tracks findings from the VTC-reviewer-style methodology/curation pass over
`twingate/paper/main.tex` (numbers/reproducibility were explicitly out of
scope for this pass — see `../revision_prompts.md` and the codebase-mapping
discussion for that separate thread).

**How to use this file:** check an item off only after the fix has actually
been applied to `main.tex`. Where a detailed writeup exists, it's linked —
read that before editing. Items without a detailed writeup yet can be
tackled directly from the one-liner + fix summary here, or expanded into
their own file first if the fix needs more justification.

Severity key:
- 🔴 **Reviewer-would-reject-on-this** — a reviewer flags this before evaluating anything else
- 🟠 **Weakens-the-paper** — survives review but a sharp reviewer will use it against you
- ⚪ **Polish** — readability/consistency only

---

## Methodology

- [x] ✅ **M1 — "Independent metrics" claim contradicted by the paper's own text** *(fixed)*
  Contribution #1 said $C$, M1, M2 "independently assess" three readiness
  layers; §IV-C says "the same geometric corrections that reduce M1 also
  improve M2" — they move together by construction (both derive from the
  same calibrated Sionna prediction surface, Eq. 3). Only $C$ is genuinely
  independent — which is exactly what "twin-gate" (two gates) already
  implies, so this was a wording issue, not a methodology flaw.
  📄 Detailed writeup: [`M1_metric_independence.md`](./M1_metric_independence.md)
  **Applied fix:** Contribution #1 (§I) now reads "...drawn from two
  independent evidence sources, empirical recurrence and physics-based ray
  tracing, that jointly assess..." instead of claiming three independent
  metrics. §IV-C now has one added sentence after the M1/M2-correlation
  observation, explaining why it's expected (both derive from the same
  calibrated Sionna surface, Eq.~\eqref{eq:ols}) and naming $C$ as the one
  metric with genuinely independent evidence. No numbers, tables, or other
  sections touched.

- [x] ✅ **M2 — "Ambiguous" gap class used in Results but never defined in Methods** *(fixed)*
  §III-A defined TypeA/TypeB as if exhaustive. §IV-A reported "13 ambiguous
  gaps whose session context is inconclusive" with no prior definition —
  and that description was itself inaccurate (Ambiguous gaps are defined
  by *lack of cross-vehicle corroboration*, not by session-context
  ambiguity; a gap's session-boundary status is never in doubt by the time
  it's labeled Ambiguous). Phrasing-only, same category as M1 — the
  classifier code was already correct and consistent.
  📄 Detailed writeup: [`M2_ambiguous_gap_class.md`](./M2_ambiguous_gap_class.md)
  **Applied fix:** §III-A now has an explicit "Ambiguous" definition
  paragraph after TypeB. §IV-A's "whose session context is inconclusive"
  was corrected to "lacking cross-vehicle corroboration." No numbers,
  tables, or other sections touched.

- [x] ✅ **M3 — "Threshold sensitivity" paragraph is one unsupported sentence** *(fixed)*
  §IV-A: "Completeness is robust to the matching radius $d_\text{recur}$..."
  — no sweep, table, or figure backed this. Sweep run with the
  author-provided dataset: $C$ = 0.00 / 0.50 / **0.80** / 0.875 / 1.00 at
  $d_\text{recur}$ = 50 / 75 / **100** / 125 / 150\,m. The "robust" claim
  was false — $C$ swings the full 0–1 range — but the mechanism is
  defensible: a larger radius mechanically makes matching easier, so
  $C \to 1$ at 150m is the metric saturating (trivial), not validation;
  the paper's 100m was fixed a priori from GPS uncertainty, well short of
  that ceiling, not chosen to maximize $C$.
  📄 Detailed writeup + full table: [`M3_threshold_sensitivity.md`](./M3_threshold_sensitivity.md)
  Raw sweep outputs: `twingate/out/g1_summary_d{50,75,100,125,150}.json`.
  **Applied fix:** replaced the paragraph in §IV-A with the real five-point
  sweep stated inline (no dedicated table — judged disproportionate for a
  secondary robustness check next to two headline results tables, and a
  standalone "C=1.00" cell risks a bad first read before the explanation
  lands). The new text gives the numbers, immediately explains the
  monotonic trend as the metric's expected saturation behavior rather than
  a red flag, and states explicitly that 100m was fixed a priori rather
  than chosen to maximize $C$.

- [~] 🟠 **M4 — Ablation table shows no train-vs-val gap, so overfitting risk is unverifiable from the paper** *(Path B fixed, Path A blocked)*
  Table I reports held-out MAE only per stage; a stage that overfits more
  free parameters (height, azimuth, scattering) to training data wouldn't
  be distinguishable from genuine geometric recovery using this table alone.
  📄 Detailed writeup: [`M4_overfitting_risk_ablation_table.md`](./M4_overfitting_risk_ablation_table.md)
  **Path B — applied.** `main.tex` §IV-C now has a new "Overfitting check"
  paragraph explaining why the train-fit/evaluate-once protocol already
  defends against this.
  **Path A — attempted, blocked, moved to leftovers.** Tried pulling
  `refined_opt_mae` from `twingate/out/{device}_gate2_final.csv` for a
  real Train MAE column, but a sanity check against Table I's own
  published numbers failed first: recomputing Op.2's weighted val MAE
  from those same files gives **3.36 dB on 101 towers**, not the paper's
  **4.04 dB on 104 towers** — and `pc4_gate2_final.csv` doesn't exist in
  the repo at all. Needs a full `A19_gate2_final.py` rerun across all 4
  devices in a GPU + Sionna environment, not available in this session.
  Tracked as its own leftover item, kept separate from the rest of this
  review (which is entirely text-only or CPU-only) so it doesn't block
  progress: 📄 [`LEFTOVERS_GPU_REQUIRED.md`](./LEFTOVERS_GPU_REQUIRED.md).
  Full numbers and reasoning also in the original writeup, §7.

- [x] ✅ **M5 — Twin-gate independence is asserted, not explained** *(fixed)*
  §III-D: "using no information about those locations during optimization"
  — the actual mechanism (training rows within 150m of the TypeB centroid
  excluded before WCL/NM/OLS, per the Op2 zone-exclusion logic) was never
  described in the text, leaving the obvious "of course they converge,
  that's where the data is" objection unanswered on the page — even
  though the mechanism in `A19_gate2_final.py` genuinely defends against
  it, it just wasn't surfaced.
  📄 Detailed writeup: [`M5_twin_gate_independence_unexplained.md`](./M5_twin_gate_independence_unexplained.md)
  **Applied fix:** §III-D now states the exclusion explicitly: for
  Operator 2, training rows within 150m of the Gate 1 TypeB centroid are
  excluded before WCL initialization, before the Nelder-Mead search, and
  before the final OLS calibration fit, so the refined tower geometry is
  derived entirely from rows outside the zone under test. No numbers,
  tables, or other sections touched.
  **Empirically verified, not just asserted** (writeup §7): computed the
  near-TypeB-vs-background comparison directly from `pc2`/`pc3`'s actual
  zone-exclusion-applied predictions — drop is real and significant
  (24.18 dB, Welch $p=8.8\times10^{-52}$, same direction as the paper's
  published 26.3 dB). Confirms the mechanism the fix describes genuinely
  works, not just that it's correctly coded.

- [x] ✅ **M6 — Conclusion's opening claim overclaims generalization** *(fixed)*
  "TWINGATE demonstrates that a physics-accurate digital twin... can be
  constructed and validated end-to-end" had zero scope marker, contradicting
  the same paragraph's later "these results are established on a single
  urban deployment... not yet confirmed" four sentences on, with no
  paragraph break between the two.
  📄 Detailed writeup: [`M6_conclusion_overclaim.md`](./M6_conclusion_overclaim.md)
  **Applied fix:** opening sentence now reads "Using the Berlin V2X
  dataset, TWINGATE demonstrates that a physics-accurate digital twin...
  can be constructed and validated end-to-end..." — the dataset-naming
  version, per author decision. "Validated" left as-is (not swapped to
  "evaluated"). The "validated" → "evaluated" word-choice question remains
  open and independent, same pattern as still-open curation finding C2.

- [ ] 🟠 **M7 — No deployment ever satisfies all three criteria; Table I's binary "No" fights the body text's noise-floor argument** *(documented, fix not yet applied)*
  Op1 fails $C$; both operators fail M1. The paper never shows what a
  "pass" looks like under its own framework, and Table I's bolded "No" for
  M1 sits in tension with prose arguing 3.02 dB is within measurement
  noise. Sharper than originally scoped — three compounding issues, not
  one: (a) the forgiving noise-floor argument is only made for Op.1's
  3.02 dB (0.02 dB over); Op.2's 4.04 dB (1.04 dB over — an order of
  magnitude further off) gets no comparable defense, yet the Conclusion's
  "close to but not yet crossing... for either operator" treats both as
  symmetric near-misses; (b) calling the self-chosen 3 dB threshold "the
  fading floor" borrows credibility from a different, actually-cited
  number (TR 38.901's 4-6 dB shadow-fading σ); (c) the meta-point that no
  deployment here ever satisfies $C$, M1, and M2 simultaneously is never
  stated plainly anywhere.
  📄 Detailed writeup: [`M7_no_deployment_fully_passes.md`](./M7_no_deployment_fully_passes.md)
  📄 **Final threshold synthesis (4-agent research, 2 independent literature
  searches + 1 primary-source-confirmed standards find):**
  [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md)
  — the earlier "relative RSRP accuracy ~2-3dB" lead was superseded (it
  measured the wrong comparison type, as originally flagged pending
  verification). Two independent agents confirmed no V2X/C-V2X DT paper
  states a borrowable acceptance threshold for TWINGATE's exact
  comparison type — a real literature gap, not a search failure. A third
  agent found something better: 3GPP TS 36.133 §9.10 ("V2X sidelink
  communication") has its own **primary-source-confirmed** absolute
  RSRP-type accuracy figures (PSSCH-RSRP ±5dB, S-RSRP ±4.5dB, normal
  condition) — right comparison type, genuinely V2X-scoped, from the same
  spec already cited. Caveat: scoped to PC5 sidelink, not TWINGATE's
  actual Uu-mode measurement — usable as corroborating context (shows the
  accuracy figure isn't an interface artifact), not as a direct
  derivation. **Final recommended plan:** (1) keep 3GPP TS36.133's generic
  Uu ±6dB as the primary standards-cited hard-pass bar (already correctly
  cited, correct comparison type, every stage clears it for both
  operators — resolves problem (c) and the "no deployment passes"
  meta-point at a stroke); (2) add the §9.10 V2X-specific figure as
  explicitly-labeled corroborating context; (3) keep ~3dB (or revise
  toward ~2.5dB) as an explicitly self-imposed stretch target, since 6dB
  alone is trivial (even Stage 0's no-physics baseline clears it — zero
  discrimination across the ablation); (4) fix the Conclusion's symmetric
  Op.1/Op.2 phrasing regardless (Option B, unchanged). Awaiting review
  before touching `main.tex`.

- [ ] 🟠 **M8 — Limitations section lists only distant weaknesses, not the nearest ones**
  Current bullets: dataset scope, dynamic scatterers, Doppler, search
  radius/cost. Missing: single dominant TypeB cluster as the sole evidence
  base for $C$ and convergence; classifier thresholds never cross-validated
  against a second confirmed dead zone; M1 not crossing its own threshold.
  **Fix:** add two bullets covering these (see full review for exact text).

- [ ] 🟠 **M9 — Gate 2's narrative reads as accuracy-chasing; the paper's best replication evidence is filed elsewhere and never cross-referenced**
  Table I and its prose narrate every stage in MAE terms only. The one
  physical-plausibility sentence for Op.1 ("realistic rooftop/mast
  heights") is immediately followed, same paragraph, by a pivot back to
  the MAE number, with no connection stated. Meanwhile the paper's
  strongest replication evidence — the twin-gate blind prediction of a
  26.3dB drop at a location the optimizer never saw — sits in the
  Discussion section and is never referenced from Table I's discussion,
  where a skeptical reader is actually forming their opinion.
  📄 Detailed writeup: [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md) (§2, "M9")
  **Proposed fix (not applied):** soften "realistic rooftop/mast heights"
  to what was actually checked (not boundary-clamped); add a
  forward-reference from §IV-C to the twin-gate blind-prediction evidence,
  explicitly ranking it as primary fidelity evidence with M1 as
  supporting statistic only.

- [ ] 🔴 **M10 — The optimizer's MAE-minimization objective is never stated as a proxy for the paper's actual geometric-recovery goal** *(highest leverage, lowest cost of this batch)*
  Confirmed in code (`A19_gate2_final.py`'s Nelder-Mead objective):
  literally and exclusively minimizes calibrated training-day MAE.
  Defensible (RSRP is the only observable when tower topology isn't
  released) but never stated as a proxy relationship anywhere in the
  paper — the reader has to infer it from scattered pieces (NeRF analogy,
  "Physics, Not Curve-Fitting" discussion, overfitting-check paragraph),
  none of which actually asserts "MAE is the proxy; geometric fidelity is
  the goal."
  📄 Detailed writeup: [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md) (§2, "M10")
  **Proposed fix (not applied):** one paragraph inserted in §III-C-3 after
  Eq. 4, stating the proxy relationship explicitly and flagging the
  known multi-modality caveat (already admitted elsewhere in the paper)
  as the reason MAE improvement is necessary but not sufficient evidence
  of correct geometry. No new experiment required — text-only.

- [ ] 🟠 **M11 — Missing per-tower / OSM-grounded position plausibility check**
  Nothing in the pipeline checks whether optimized tower positions land
  near a plausible physical siting location (an OSM building/mast) rather
  than wherever numerically minimizes MAE. The existing plausibility
  check (height/azimuth ranges) is aggregate-only and computed only for
  Operator 1 — Operator 2, which carries the paper's entire headline
  convergence result, doesn't get even that weaker check.
  📄 Detailed writeup: [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md) (§2, "M11")
  **Proposed fix (not applied, requires actual analysis, not just prose):**
  compute each tower's distance to the nearest OSM building footprint
  (data already exists — building layer + optimized coordinates), check
  correlation with per-tower MAE improvement; extend the existing Op.1
  aggregate check to Op.2 as a cheap companion fix. Track separately from
  the text-only items — don't let it block them.

- [ ] ⚪ **M12 — "Physics, Not Curve-Fitting" discussion defends itself using MAE deltas, risking circularity**
  §V's anti-curve-fitting argument partly relies on an MAE-delta
  (removing Sionna costs 1.81dB) — logically valid but rhetorically
  self-referential given M10's gap.
  📄 Detailed writeup: [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md) (§2, "M12")
  **Proposed fix (not applied):** one added sentence noting this argument
  only rules out calibration-alone explaining the accuracy, and pointing
  to the twin-gate blind prediction as the evidence that independently
  supports the *specific* recovered geometry being correct. Minor
  companion fix, best applied alongside M9/M10.

---

## Curation (how it reads)

- [ ] ⚪ **C1 — "Layers" (intro) vs. "Gates" (method) vocabulary never explicitly reconciled**
  Reader has to infer the C/M1/M2 ↔ Gate1/Gate2 mapping from a single
  Contributions bullet.
  **Fix:** one bridging sentence at the start of §III mapping each layer to
  its gate.

- [ ] 🟠 **C2 — "each validated on a held-out temporal split" overclaims**
  "Validated" implies a pass; neither operator cleanly passes all three.
  **Fix:** change to "each computed on a held-out temporal split."

- [ ] ⚪ **C3 — Abstract's final sentence is one ~70-word run-on stacking four results**
  **Fix:** split into two sentences (see full review for the exact rewrite).

- [ ] 🟠 **C4 — Beyraghi/Rauf citations set up a contrast in the intro that's never paid off in Discussion**
  Intro: Beyraghi's calibration "assumes known tower positions, a luxury
  public V2X datasets do not have" — foreshadows a comparison that never
  arrives.
  **Fix:** add one sentence in §V-A explicitly contrasting TWINGATE's
  higher residual MAE (unknown geometry) against Beyraghi's 0.32 dB
  (known geometry, calibration-only).

- [ ] ⚪ **C5 — "Coupling" (method) vs. "Convergence" (result) terminology split never flagged as intentional**
  **Fix:** one clause at the start of §III-D noting method vs. outcome framing.

- [ ] ⚪ **C6 — §V-A re-derives numbers already stated in §IV-B before making its new argument**
  The falsifiability framing is genuinely new; the numeric recap before it
  isn't.
  **Fix:** trim the redundant recap, lead straight into the new argument.

- [ ] 🟠 **C7 — The paper's best thesis sentence is buried in the Conclusion**
  "...two methods built from entirely different evidence... converge on the
  same anomaly is stronger validation than either metric alone, and is this
  paper's central claim" — first appears on the last page.
  **Fix:** pull a version of this sentence forward into the §I Contributions
  preamble.

- [ ] ⚪ **C8 — Op1's "one training TypeB gap, observed by a single vehicle" reads in tension with the ≥2-vehicle TypeB definition**
  **Fix:** clarify as "(corroborated by exactly one other vehicle, the
  minimum for TypeB status)."

- [x] ✅ **C9 — Table/figure narration is a strength — no action needed**
  Table I and Table II are both walked through in multi-paragraph prose.
  Noted so it doesn't get "fixed" by accident.

---

## Suggested order of attack

1. M2, M3, M5 (🔴 — cheapest, most reviewer-visible, all text-only fixes)
2. M1, C2, C7 (framing/claim-calibration cluster — do together, they interact)
3. **M7 + M10 together** (🔴/🟠 — the threshold fix and the "MAE is a proxy, not the goal" fix directly interact: M10 reframes what Table I's M1 column is *for*, M7 reframes what its verdict *means*; do in the same pass)
4. M9, M12 (cheap, text-only, complementary to M10 — same pass or immediately after)
5. M4, M6, M8 (remaining methodology honesty passes)
6. M11 (requires actual analysis work, not just prose — don't let it block the text-only items above)
7. C1, C3, C4, C5, C6, C8 (polish pass, do last so it doesn't get overwritten by the fixes above)
