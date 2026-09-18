# Review Finding M4 — The Ablation Table Can't Rule Out "More Knobs, Not Better Physics"

**Status:** open · **Severity:** Weakens-the-paper · **Section(s) affected:** Table I (`tab:gate2`), §IV-C (Gate 2 Results)

---

## 1. The plain-English version

Imagine a student takes practice tests before a real exam. If they study
from last year's practice questions and then do well on a brand-new exam
they've never seen, that's real evidence they learned something useful.
But if you only ever see their **new-exam score**, and never see how they
did on the **practice questions**, you can't fully rule out a different
explanation: maybe they memorized specific quirks of the practice set in
a way that happened to transfer a little, without genuinely understanding
the material. The two stories — "really learned it" vs. "memorized enough
surface patterns to get lucky" — can produce the exact same new-exam score.
The only way to tell them apart is to look at the practice-test score too.

Table I is built the same way. Each pipeline "stage" hands the simulator
more adjustable knobs to twist until its prediction matches reality:

| Stage | What gets added | Knobs added |
|---|---|---|
| 0 | Nothing — just each tower's historical average signal | 0 |
| 1 | Real ray-tracing physics + a simple per-tower correction; tower position fixed from a crowd-sourced database | 2 (the correction's slope and offset) |
| 2 | "Move the tower left/right/forward/back" | +2 (2D position) |
| 3 | "Move the tower up/down" and "rotate which way it faces," plus a more realistic (directional) antenna shape | +2 (height, azimuth) |
| 4 | A physics detail about how radio waves scatter off rough surfaces | +0 new free parameters, but a materially different physics model |

Every added stage gives the optimizer more freedom, and every added stage's
reported error goes down. That is exactly what you'd expect if the
simulator is genuinely recovering the tower's real position and
orientation. **It is also exactly what you'd expect if the extra freedom
were just letting the optimizer bend the simulation to fit noise and
coincidences in the specific days it was allowed to look at.** These two
very different explanations produce the same-looking table. The only way
to distinguish "real geometry recovered" from "more elaborate curve-
fitting" is to look at how well each stage fits the days it trained on,
next to how well it does on the day it never saw. The paper currently
shows only the second number.

## 2. Where this shows up in the paper

Table I (`tab:gate2`), reproduced structurally:

> Pipeline Stage | Description | Op.1 MAE (dB) | Op.2 MAE (dB) | M1 < 3dB?
> Stage 0 ... Stage 4, each row showing only the **held-out day-3** MAE.

§IV-C then narrates the table stage by stage ("Stage 3 reaches 3.03 dB...",
"Adding diffuse scattering (Stage 4) narrows Operator 1 to 3.02 dB...") —
all held-out numbers, with no training-fit number anywhere alongside them
for comparison.

## 3. Why this matters, technically

The paper's own evaluation protocol (§III-C-6, "Gate 2 Evaluation
Protocol") is actually a real defense against exactly this concern, it's
just never stated as one:

> "Tower positions and OLS parameters are finalized on training data; in a
> single final pass we run Sionna forward at each refined position, apply
> training-fit calibration, and compute RSRP MAE against day-3
> measurements, **with no further parameter update.**"

That "look once, no do-overs" rule matters a lot: if a given stage's added
freedom were mainly fitting noise specific to the training days, there is
no mechanical reason that noise-fitting should *also* reduce error on a
day it was never allowed to see — and it would need to do so consistently,
across four separate stages, for two separate operators, for the pattern
in Table I to appear by that route. So the fact that held-out error keeps
dropping stage after stage is genuinely decent evidence against pure
overfitting. The paper simply never says this out loud, and never shows
the side-by-side comparison that would make it visually obvious rather
than something the reader has to take on faith.

## 4. What's already sitting in the repo, unused

Checked the actual output files already on disk. For Stage 3/4
(`twingate/A19_gate2_final.py`), the training-day fit quality is **already
computed and saved** — every row of `twingate/out/{device}_gate2_final.csv`
has a `refined_opt_mae` column (the calibrated training MAE at the
optimized tower position) sitting right next to `refined_val_mae` (the
held-out number that made it into the paper). Nobody has pulled it in.

For the earlier stages (0–2, computed by different, earlier scripts), a
quick check did not turn up an equivalent saved training-fit number — so
getting those would need a small rerun rather than being free.

## 5. Two fix paths

**Path A — show the real numbers (recommended, partially free).**
Add a "Train MAE" column (or a compact footnote) to Table I, at minimum
for Stages 3–4 where the data already exists in
`out/{device}_gate2_final.csv` (aggregate `refined_opt_mae`, weighted by
`n_train`, the same way `refined_val_mae` is already weighted by `n_val`
for the paper's headline numbers). If train and held-out MAE move together
(both improving, staying close), that's a real, visible answer to the
overfitting question instead of an implicit one. Stages 0–2 would need a
small rerun of their respective scripts to capture the analogous number,
if not already loggable from existing checkpoints.

**Path B — text-only, no new numbers.**
Add a sentence to §IV-C (or right after Table I) making the existing
protocol's implicit defense explicit:

> "Because each stage's added parameters are optimized only against
> training-day MAE and evaluated exactly once on day 3 with no further
> tuning, a stage that were mainly fitting training noise would show flat
> or worsening held-out error, not the improving error each stage actually
> shows; the monotonic held-out improvement across stages is therefore
> itself evidence the added geometric freedom is capturing real structure,
> not noise."

This costs nothing beyond a sentence, and is honest — it doesn't manufacture
certainty the paper doesn't have, it just states the argument the protocol
already supports.

## 6. Recommendation

Do both, in order: Path B first (cheap, immediate, closes the gap in the
argument regardless of what any new number shows), then Path A for
Stage 3/4 specifically since that data costs nothing to pull in and would
let the paper make an even stronger, visually-checkable claim instead of
an argued one. Stages 0–2's training MAE is a nice-to-have, not essential
— the overfitting risk is concentrated in the later stages anyway, since
that's where the free parameters (height, azimuth) are actually added.

**Not yet applied.** Waiting on a decision on how far to take this
(Path B only, or B + partial A) before touching `main.tex`.
