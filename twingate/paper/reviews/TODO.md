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

- [x] ✅ **M7 — No deployment ever satisfies all three criteria; Table I's binary "No" fights the body text's noise-floor argument** *(fixed — reframed around 6dB, not 3dB)*
  Op.1 failed $C$; both operators failed the paper's self-imposed M1<3dB
  bar, and Table I's bolded "No" fought the body text's own noise-floor
  argument for why 3.02dB should basically count. Author decision after
  reviewing the 4-agent research (see addendum doc): drop the 3dB
  framing entirely rather than patch it — verified via independent
  literature/citation checks (see below) that 3GPP TS 36.133's already-cited
  absolute RSRP accuracy bound (±6dB) is the correct standards citation
  for M1's comparison type, and every pipeline stage already clears it
  for both operators. Reframed M1 from a binary pass/fail gate into a
  quantitative indicator of digital-twin replication fidelity (geometry,
  material, scattering), citing MART-6G (verified primary-source,
  precisely worded — see resolution note in the addendum) as a comparable
  ray-tracing DT platform landing in the same error magnitude.
  📄 Full history: [`M7_no_deployment_fully_passes.md`](./M7_no_deployment_fully_passes.md),
  [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md)
  **Applied fix:** Table I's "M1<3dB?" column removed entirely (structure
  and caption); §III-C-6's M1 definition rewritten to state MAE is
  tracked as a fidelity indicator, not a pass/fail gate, citing 3GPP
  TS36.133 ±6dB plus MART-6G (new bib entry `yu2025mart6g`) as
  corroborating context; the "M1 acceptance threshold" paragraph rewritten
  to report both operators clearing the 6dB bound comfortably (no more
  near-miss framing, no more asymmetric Op.1/Op.2 treatment — problem (a)
  dissolves since neither operator is a "miss" anymore); Conclusion and
  Abstract updated to match (positive framing, not "approaching"/"close
  to but not yet crossing"). Verified: `main.tex` compiles cleanly
  end-to-end (installed a full TeX toolchain in this session specifically
  to check — zero errors, zero undefined citations/references).

- [ ] 🟠 **M8 — Limitations section lists only distant weaknesses, not the nearest ones**
  Current bullets: dataset scope, dynamic scatterers, Doppler, search
  radius/cost. Missing: single dominant TypeB cluster as the sole evidence
  base for $C$ and convergence; classifier thresholds never cross-validated
  against a second confirmed dead zone; M1 not crossing its own threshold.
  **Fix:** add two bullets covering these (see full review for exact text).

- [x] ✅ **M9 — Gate 2's narrative reads as accuracy-chasing; the paper's best replication evidence is filed elsewhere and never cross-referenced** *(fixed)*
  Table I and its prose narrated every stage in MAE terms only. The one
  physical-plausibility sentence for Op.1 ("realistic rooftop/mast
  heights") was immediately followed, same paragraph, by a pivot back to
  the MAE number, with no connection stated. Meanwhile the paper's
  strongest replication evidence — the twin-gate blind prediction of a
  26.3dB drop at a location the optimizer never saw — sat in the
  Discussion section, never referenced from Table I's discussion.
  📄 Detailed writeup: [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md) (§2, "M9")
  **Applied fix:** softened "realistic rooftop/mast heights" to what was
  actually checked ("heights not clamped to the search-space boundary"),
  explicitly labeled as corroborating not definitive evidence; added a
  new paragraph in §IV-C right after the Stage 4 discussion, forward-
  referencing the twin-gate blind prediction and explicitly ranking it as
  the primary fidelity evidence with M1 as a supporting statistic only.

- [x] ✅ **M10 — The optimizer's MAE-minimization objective is never stated as a proxy for the paper's actual geometric-recovery goal** *(fixed — highest leverage item in this batch)*
  Confirmed in code (`A19_gate2_final.py`'s Nelder-Mead objective):
  literally and exclusively minimizes calibrated training-day MAE.
  Defensible (RSRP is the only observable when tower topology isn't
  released) but was never stated as a proxy relationship anywhere in the
  paper.
  📄 Detailed writeup: [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md) (§2, "M10")
  **Applied fix:** new paragraph inserted in §III-C-3 right after Eq. 4
  (the objective equation), stating the proxy relationship explicitly
  ("we emphasize that MAE is the optimization objective, not the
  pipeline's actual target...") and flagging the already-admitted
  multi-modality caveat as the reason MAE improvement is necessary but
  not sufficient evidence of correct geometry, forward-referencing the
  held-out protocol and blind dead-zone prediction as the additional
  evidence. Text-only, no new experiment.

- [~] 🟠 **M11 — Missing per-tower / OSM-grounded position plausibility check** *(attempted, blocked — compound gap, moved to leftovers)*
  Nothing in the pipeline checks whether optimized tower positions land
  near a plausible physical siting location (an OSM building/mast) rather
  than wherever numerically minimizes MAE. The existing plausibility
  check (height/azimuth ranges) is aggregate-only and computed only for
  Operator 1 — Operator 2, which carries the paper's entire headline
  convergence result, doesn't get even that weaker check.
  📄 Detailed writeup: [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md) (§2, "M11"),
  [`M11_osm_plausibility_check.md`](./M11_osm_plausibility_check.md)
  **Attempted, blocked by two independent gaps.** (a) The same incomplete
  tower-coordinate data already blocking M4 Path A (pc4 missing entirely;
  pc1/pc2/pc3 don't reproduce Table I's published numbers). (b) Real OSM
  building-footprint data is entirely unreachable from this sandbox —
  tested directly against six Overpass/OSM hosts (`overpass-api.de`,
  `overpass.kumi.systems`, `overpass.openstreetmap.ru`,
  `overpass.private.coffee`, `www.openstreetmap.org`,
  `download.geofabrik.de`), every one blocked by organization network
  policy, confirming a domain-family-level block rather than a transient
  issue. No substitute/approximated geometry was used — same
  don't-fabricate-data principle applied for M4. Tracked as a compound
  leftover alongside M4 (they unblock together, see
  [`LEFTOVERS_GPU_REQUIRED.md`](./LEFTOVERS_GPU_REQUIRED.md)), not a
  separate independent item. **Not applied.** No changes to `main.tex`.

- [x] ✅ **M12 — "Physics, Not Curve-Fitting" discussion defends itself using MAE deltas, risking circularity** *(fixed)*
  §V's anti-curve-fitting argument partly relied on an MAE-delta
  (removing Sionna costs 1.81dB) — logically valid but rhetorically
  self-referential given M10's gap.
  📄 Detailed writeup: [`M7_addendum_dt_readiness_and_v2x_thresholds.md`](./M7_addendum_dt_readiness_and_v2x_thresholds.md) (§2, "M12")
  **Applied fix:** one added sentence noting this argument only rules out
  calibration-alone explaining the accuracy, and pointing to the blind
  location-specific prediction (described in the next sentence) as the
  evidence that independently supports the *specific* recovered geometry
  being correct. Applied alongside M9/M10 in the same edit pass.

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

- [x] ✅ **C4 — Beyraghi/Rauf citations set up a contrast in the intro that's never paid off in Discussion** *(fixed — Option F)*
  Intro: Beyraghi's calibration "assumes known tower positions, a luxury
  public V2X datasets do not have" — foreshadowed a comparison that
  never arrived; `\cite{beyraghi2025ris}` and `\cite{rauf2026kpi}` each
  appeared exactly once, both in §I, never referenced again. Original
  fix draft (one sentence in §V-A stating TWINGATE's MAE is "an order
  of magnitude larger" than Beyraghi's 0.32dB) was flagged by the author
  as handing a reviewer a ready-made "our number is worse" quote.
  Verified the actual Beyraghi paper (arXiv 2510.09478) directly before
  settling on a fix: confirmed known BS positions and the 5.69/0.32dB
  figures are accurate, but found an additional uncredited nuance — the
  0.32dB figure is a region-averaged number over 70 filtered regions
  (outliers excluded), not a per-point no-exclusions MAE like M1.
  📄 Detailed writeup: [`C4_beyraghi_contrast_unpaid.md`](./C4_beyraghi_contrast_unpaid.md)
  **Applied fix (Option F):** removed the specific "5.69 to 0.32dB"
  figures from the §I citation itself; reworded to state the
  qualitative point only (material calibration alone, given known
  positions, substantially narrows the gap to region-averaged measured
  coverage) plus the newly-verified region-averaging caveat. No numeric
  anchor remains anywhere in the paper for comparison against TWINGATE's
  own M1 figures, and no compensating sentence was needed in §V-A
  (unchanged). Verified: `main.tex` compiles cleanly end-to-end, zero
  errors/undefined references.

- [ ] ⚪ **C5 — "Coupling" (method) vs. "Convergence" (result) terminology split never flagged as intentional**
  **Fix:** one clause at the start of §III-D noting method vs. outcome framing.

- [ ] ⚪ **C6 — §V-A re-derives numbers already stated in §IV-B before making its new argument**
  The falsifiability framing is genuinely new; the numeric recap before it
  isn't.
  **Fix:** trim the redundant recap, lead straight into the new argument.

- [x] ✅ **C7 — The paper's best thesis sentence is buried in the Conclusion** *(fixed)*
  "...two methods built from entirely different evidence... converge on the
  same anomaly is stronger validation than either metric alone, and is this
  paper's central claim" — originally appeared only on the last page. §I's
  Contributions bullet 4 stated the same *result* (twin-gate convergence,
  26.3dB vs 30.4dB) but never stated the *claim* (why that convergence is
  stronger evidence than either signal alone) — a reader who stopped after
  §I never got the thesis.
  📄 Detailed writeup: [`C7_buried_thesis_statement.md`](./C7_buried_thesis_statement.md)
  **Applied fix (Option A — both changes):** new sentence added to the §I
  Contributions preamble, before the enumerated list, stating the thesis
  directly ("The central claim underlying the contributions below is
  that when two independently derived signals... converge on the same
  physical anomaly... that agreement is stronger evidence of
  digital-twin readiness than either signal could establish on its
  own."); bullet 4 now ends with a callback clause ("...the strongest
  single piece of evidence for the claim above"). Conclusion's version
  left untouched — it now reads as confirmation, not first encounter.
  Verified: `main.tex` compiles cleanly end-to-end, zero errors/undefined
  references. No numbers, tables, or other sections touched.

- [ ] ⚪ **C8 — Op1's "one training TypeB gap, observed by a single vehicle" reads in tension with the ≥2-vehicle TypeB definition**
  **Fix:** clarify as "(corroborated by exactly one other vehicle, the
  minimum for TypeB status)."

- [x] ✅ **C9 — Table/figure narration is a strength — no action needed**
  Table I and Table II are both walked through in multi-paragraph prose.
  Noted so it doesn't get "fixed" by accident.

---

## Suggested order of attack

1. M2, M3, M5 (🔴 — cheapest, most reviewer-visible, all text-only fixes) — ✅ done
2. M1, C2, C7 (framing/claim-calibration cluster — do together, they interact) — M1 ✅ done; C2, C7 still open
3. ~~M7 + M10 together~~ — ✅ done, plus M9 and M12 folded into the same pass (all four interact: M10 reframes what M1 is *for*, M7 reframes what the table *shows*, M9 connects it to the paper's strongest evidence, M12 is a one-sentence companion). Verified end-to-end with a real LaTeX compile.
4. M8 (remaining methodology honesty pass; M6 ✅ done)
5. ~~M11~~ — attempted, blocked (compound gap: stale tower coordinates + no OSM network access), tracked with M4 in `LEFTOVERS_GPU_REQUIRED.md`; both unblock together once a GPU environment with the full rerun is available
6. C1, C3, C4, C5, C6, C8 (polish pass, do last so it doesn't get overwritten by the fixes above)
