# TWINGATE Revision Prompts
Sequential prompts to trigger one at a time. Each is self-contained.
Working file: `C:\Users\sahil\dt-sionna-rt\twingate\paper\main.tex`

---

## PROMPT 1 — Standards Research: Establish the <3 dB Acceptability Threshold

**Context.**  
We are writing a V2X digital twin (DT) framework paper called TWINGATE. Gate 2 achieves
RSRP MAE of 2.59 dB (Op. 1, 183 towers) and 2.90 dB (Op. 2, 220 towers) on a held-out day
using inverse ray tracing (Sionna RT) with a 4D Nelder-Mead optimizer. We want to argue
that sub-3 dB MAE is not an arbitrary milestone but a principled, standard-backed acceptability
threshold for DT fidelity. Currently the paper shows this number without any normative anchor.

**Task.**  
1. Search the following sources to find the most defensible normative bound for RSRP prediction
   accuracy in an LTE planning / DT context:
   - **3GPP TS 36.133** "Requirements for support of radio resource management" —
     look for RSRP measurement accuracy tables (typical values: ±6 dB normal, ±11 dB
     difficult conditions). If our MAE is below the measurement noise floor itself, that
     is a strong claim.
   - **3GPP TR 36.956 / TS 37.571** or similar measurement accuracy specs.
   - **ITU-R M.2135** (already in references.bib as `itu2135`) — check if it specifies
     acceptable propagation model error for IMT evaluation (often 5–10 dB).
   - **ETSI TR 103 195-2** for 5G evaluation methodology if available.
   - Academic precedent: papers such as Beyraghi 2025 (arXiv:2510.09478, already cited
     as `beyraghi2025ris`) and Rauf 2026 (arXiv:2605.10352, cited as `rauf2026kpi`)
     for what MAE values they achieve and treat as acceptable.

2. Write a **2–3 sentence justification paragraph** to be inserted into the Gate 2 results
   section of main.tex (around line 610, after the Table II discussion) that:
   - Names the standard and its RSRP accuracy specification,
   - States that our 2.59/2.90 dB MAE falls within (or below) that bound,
   - Concludes this constitutes the M1 DT readiness criterion being met.

3. Add any missing BibTeX entries needed for these standards to `references.bib`.

4. Update the **M1 metric definition** wherever it first appears in the paper to explicitly
   state the threshold (e.g., "M1 < 3 dB, consistent with 3GPP TS 36.133 measurement
   accuracy") rather than just citing the achieved number.

**Do not** change Table II structure in this prompt — that is Prompt 3.

---

## PROMPT 2 — Abstract: Numbers as Evidence, Not Explanation

**Context.**  
The current abstract of `main.tex` (lines ~39–69) contains approximately 15 specific
numeric values: C=0.80, 403 towers, 2.59 dB, 2.90 dB, 183 and 220 towers, 6.04 dB, 91%
towers improving, F1=0.63, recall 82%, precision 57×, 27.2 dB, 30.3 dB, 90% depth
agreement, 17.2 km, four vehicles, three days. This is too many — it reads like a results
table, not a story.

**Editorial principle.**  
Numbers in an abstract are *evidence*, not *explanation*. Keep only the handful of numbers
that prove the system works. Everything else should be expressed as qualified prose
("substantially above random", "within 3 dB", "independently confirmed", "across all
operators"). A reader should finish the abstract knowing (a) what TWINGATE is, (b) why
it matters, (c) that it works on real data with a concrete result — not every metric.

**Task.**  
Rewrite the abstract with these rules:
- **Keep (evidence-level numbers):**  three layers of DT readiness (C, M1, M2),
  C = 0.80 (the headline Gate 1 result), RSRP MAE < 3 dB for both operators (M1 threshold
  met), F1 > 0.63 (M2), the twin-gate convergence signal (~30 dB drop, ~90% agreement).
- **Remove or soften (explanation-level numbers):** exact tower counts (183/220),
  exact dB improvement figures (+3.33/+6.04), exact % of towers improving (91.3/92.7%),
  exact recall (82%), exact precision multiple (57×), exact dataset dimensions (17.2 km,
  four vehicles — move to one mention of "Berlin V2X, three consecutive days" for context).
- **Strengthen the DT readiness narrative:** the first two sentences must establish what
  DT readiness means and why existing work doesn't address it before introducing TWINGATE.
- **No em-dashes** (`---`). Use colons, semicolons, or parentheses instead.
- Target length: 200–240 words (currently ~260).

Write the revised abstract and apply it to main.tex.

---

## PROMPT 3 — Table II: Framework Validation, Not Ablation Study

**Context.**  
We are proposing a framework (TWINGATE) and need to show it achieves an acceptable DT
fidelity level. Table II currently looks like an ablation study comparing four methods
against each other, with a "Gain vs. WCL-fixed" row. This framing invites reviewers to
ask "why these baselines?" and "what is the competition?" — undermining the framework
positioning.

The real story is: (1) starting from crowd-sourced positions, (2) our calibration
pipeline achieves M1 (RSRP MAE < 3 dB) on a held-out day, (3) each stage of the
pipeline contributes, (4) both operators independently satisfy the threshold.

**Task.**  
Restructure Table II with these specific changes:

1. **Rename the table caption** from "Gate 2 RSRP MAE on Held-Out Day 3 (June 24)"
   to "Gate 2 Calibration Pipeline — M1 Metric on Held-Out Day 3 (June 24)".

2. **Add a column** "M1 met?" with values No/No/No/**Yes** (bold) for the four method rows,
   where the threshold is <3 dB. This makes the framework's acceptance criterion explicit.

3. **Rename the row labels** to be pipeline-stage language rather than method-competition language:
   - "Per-tower mean (no RT)" → "Stage 0: per-cell mean (no ray tracing)"
   - "Sionna+OLS, WCL init" → "Stage 1: Sionna RT + OLS, crowd-sourced TX pos."
   - "2D NM (iso. ant.), refined TX" → "Stage 2: add position optimization (2D)"
   - "4D NM (TR38901), refined TX+az+h" → "Stage 3: add azimuth+height (4D, proposed)"

4. **Keep the footnote** for the WCL-fixed baseline MAE numbers (added in a prior session).

5. **Update the body text** below Table II (around lines 610–640 of main.tex) to reflect
   the framework-validation framing: "Stage 3 satisfies the M1 criterion (<3 dB) for both
   operators, whereas earlier stages do not — confirming that both position and
   antenna-orientation refinement are necessary components of the Gate 2 pipeline."

---

## PROMPT 4 — Limitations: Static Scatterers, Doppler, and Runtime

**Context.**  
The paper has a limitations or discussion section (search main.tex for `limitations`
or `\subsection*{Limitations}` or `discussion`). The user has identified these specific
gaps that need to be addressed honestly and technically:

(a) **Static scatterers**: Sionna RT assumes all scatterers are static. In a dense urban
    V2X platoon, moving vehicles act as blockers and reflectors. This is not modeled.

(b) **Doppler / frequency-selective fading**: RSRP does not capture frequency-selective
    fading. MobileInsight does not log I/Q samples, so wideband (e.g., delay spread,
    Doppler spread) validation is out of scope.

(c) **500 m search radius**: The inverse ray-tracing search radius for Gate 2 may be
    insufficient for towers serving peripheral route segments where training GPS coverage
    is sparse and WCL initialization is correspondingly poor.

(d) **Runtime**: 3–6 min/tower for Gate 2 is acceptable for offline DT construction but
    unsuitable for real-time update loops without parallelization or amortization.

**Doppler nuance to include** (important — this partially *defends* our approach):
For LTE at ~1.8 GHz and vehicle speeds up to 100 km/h:
- Max Doppler shift ≈ (100/3.6) / (3×10⁸) × 1.8×10⁹ ≈ 167 Hz
- Coherence time ≈ 1 / (2 × 167) ≈ 3 ms
- 3GPP TS 36.133 specifies RSRP averaging over ≥200 ms (L3 filter)
- Therefore, RSRP measurements *average over* many coherence times, so Doppler
  fading is statistically averaged out in the RSRP metric we validate against
- Conclusion: Doppler is a limitation for wideband metrics (delay spread, BER) but
  not for RSRP-based DT validation — this should be stated explicitly as a *bounded*
  limitation, not an uncaveated one

**Task.**  
Find or create the limitations section in main.tex. Write or expand it to cover all four
points above, incorporating the Doppler nuance as a bounded limitation. Structure it as
4 named sub-paragraphs (not subsections): **Dynamic scatterers.** **Wideband metrics.**
**Search radius.** **Computational cost.** Each should be 2–4 sentences. No em-dashes.

Add a citation to 3GPP TS 36.133 in references.bib if not already present, used to
support the RSRP averaging / coherence time argument.

---

## PROMPT 5 — Future Work: Concrete Extension Plan for Dynamic Scatterers

**Context.**  
The TWINGATE paper's Sionna RT scene models only static geometry (buildings, terrain).
Moving vehicles as dynamic blockers/reflectors are not modeled. This is a real gap
for dense urban V2X scenarios. Rather than just listing this as a limitation, we want
to outline a **concrete, credible extension path** in the future work section.

**Task.**  
Find the future work section (or add one after the conclusion if absent). Write a
paragraph titled **Dynamic scene extension.** covering:

1. **Vehicle density model**: A Poisson field of mobile blockers overlaid on the
   static Sionna scene. Each vehicle is modeled as a rectangular PEC/lossy-dielectric
   slab; the blockage probability as a function of inter-vehicle distance can be
   derived from the Poisson thinning theorem. This adds stochastic shadowing on
   top of the deterministic ray-tracing result.

2. **Doppler-aware validation metric**: Since RSRP averages out Doppler (see Prompt 4),
   the next metric beyond RSRP is Doppler spread estimated from CQI fluctuations or
   from MobileInsight's per-TTI RSRQ logs. Including Doppler spread as M3 would extend
   the DT readiness framework from signal-level to channel-level validation.

3. **Online DT update**: A Kalman-filter-based mechanism that uses incoming RSRP
   measurements to incrementally update per-tower OLS offsets, amortizing the
   3–6 min/tower offline cost into a continuous low-cost correction stream. Reference
   relevant work if found (e.g., online calibration, recursive least squares for
   path loss models).

4. Reference at least one existing paper that has attempted vehicle blockage modeling
   in ray tracing for V2X (search alphaXiv if needed for "vehicular blockage ray
   tracing" or "dynamic obstacle ray tracing V2X").

Write this paragraph (~150 words) and insert it in the future work section of main.tex.

---

## PROMPT 6 — Framework Framing Audit: C / M1 / M2 Consistency Pass

**Context.**  
TWINGATE is framed as a **DT readiness framework** defined by three measurable layers:
- **C** (completeness): fraction of training TypeB clusters confirmed on held-out day
- **M1** (geometric fidelity): per-tower RSRP MAE after Gate 2 calibration
- **M2** (functional coverage accuracy): dead-zone detection F1 score

The three-metric structure was introduced in the abstract and intro rewrite. However,
the body of the paper (Gate 1 results, Gate 2 results, M2 section, conclusion) may still
use the old "we show X" framing rather than "TWINGATE satisfies the C / M1 / M2 criteria."

**Task.**  
Do a focused pass through main.tex hitting these specific locations:

1. **Gate 1 results paragraph** (around line 500–520): Ensure the final sentence
   names C explicitly as a DT readiness metric, not just a classification accuracy number.
   "Gate 1 achieves C = 0.80, satisfying the measurement-quality criterion of the
   DT readiness framework."

2. **Gate 2 results paragraph** (around line 610–650): Ensure M1 is named explicitly
   and tied to the threshold. "Gate 2 achieves M1 = 2.59/2.90 dB for Operators 1/2,
   meeting the geometric-fidelity criterion (M1 < 3 dB)."

3. **M2 / dead-zone section** (search for `F1` or `dead.zone`): Ensure M2 is named.
   "The functional metric M2 reaches F1 = 0.63, completing the third readiness layer."

4. **Conclusion** (search for `\section{Conclusion}` or `\section*{Conclusion}`):
   Rewrite the opening 2–3 sentences so they summarize the framework by naming C, M1,
   M2 in order and their achieved values, then make the "DT readiness is a dataset
   property, not just a model property" claim explicitly.

5. **Introduction contributions list** (search for `\subsection*{Contributions}` or
   `\begin{enumerate}` near intro): Verify the four contributions still align with the
   current paper state. Update any contribution bullet whose wording no longer matches
   what the paper actually does.

Make only targeted edits — do not rewrite entire sections. The goal is consistency
of framework language, not a full rewrite.

---

## Execution order

Run these prompts in sequence. Each depends on earlier ones:

```
1 → establish threshold (needed by 3, 4, 6)
2 → abstract (can run after 1 for the M1 threshold wording)
3 → Table II (needs the threshold from 1)
4 → limitations (self-contained; can run after 1 for the 36.133 cite)
5 → future work (references dynamic scatterer gap established in 4)
6 → framing audit (run last, after all content changes are in)
```
