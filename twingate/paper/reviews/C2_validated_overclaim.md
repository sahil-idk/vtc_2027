# Review Finding C2 — "Each Validated on a Held-Out Temporal Split" Overclaims

**Status:** ✅ fixed (Option B applied) · **Severity:** 🟠 Weakens-the-paper ·
**Section(s) affected:** §I "Contributions," bullet 1

---

## 1. The plain-English version

"Validated" is a loaded word in a methods paper: it implies the thing
being validated *passed* whatever test it was checked against, not
merely that it was *measured* on held-out data. Contributions bullet 1
currently says all three of TWINGATE's readiness metrics ($C$, M1, M2)
are "each validated on a held-out temporal split." Read literally, that
says every metric, for every deployment, passes its held-out check. But
that isn't what the paper's own Results section reports: Operator 1's
$C=0.00$ is an explicit, stated *failure* to certify a dead zone on the
held-out day, and M1 (since the M7 fix) is no longer even framed as a
pass/fail quantity at all — it's a fidelity indicator, not a threshold
test. "Validated" describes neither case accurately. What's actually
true, and provable from the paper's own protocol description, is that
all three metrics were *computed* — correctly, honestly, following a
strict held-out discipline — on the temporal split. That's a materially
weaker (and correct) claim than "validated."

## 2. The paragraph today, in full (§I, Contributions bullet 1)

```
Development of a DT readiness framework: three quantitative
metrics ($C$, M1, M2), drawn from two independent evidence
sources, empirical recurrence and physics-based ray tracing,
that jointly assess measurement quality, geometric fidelity, and
functional coverage accuracy, each validated on a held-out
temporal split.
```

## 3. Why "validated" specifically doesn't hold up

- **$C$:** Operator 1's own lone TypeB gap doesn't recur on day 3
  ($C=0.00$) — the paper's own §IV-A text says this "signal[s]
  insufficient measurement density to certify a dead zone." That is a
  reported non-validation, not a validation, for one of the two
  deployments this metric is computed on.
- **M1:** since the M7/M9/M10/M12 reframing (already applied), M1 is
  explicitly *not* a pass/fail criterion any more — §III-C-6 now states
  MAE is "tracked as a quantitative indicator... rather than a binary
  pass/fail gate." A metric the paper itself says is not evaluated
  against a pass/fail bar cannot simultaneously be described as
  "validated" in the Contributions list without contradicting that
  later, more careful framing.
- **M2:** this one is closer to defensible (F1$=0.77$ against ground-
  truth-adjacent labels is a real accuracy check), but bundling it into
  "each validated" alongside $C$ and M1 drags it down to the same
  overclaim by association — a reader can't tell from the bullet that
  M2's situation is different from the other two.

The common thread: "validated" asserts an evaluative outcome
(pass/fail, and specifically pass) for all three metrics uniformly,
when the paper's own Results section shows genuinely mixed, metric-
specific outcomes. "Computed" or "evaluated" claims only that the
measurement was made under the stated held-out discipline — which is
true, defensible, and still a real methodological strength (most
competing work on this same dataset doesn't even do that, per §V-A's
own comparison to `teh2023dt`/`partani2025qos`) — without asserting
anything about whether the result was favorable.

## 4. Relationship to M6

This is the direct, previously-flagged companion to M6 (already fixed).
M6's resolution note explicitly left this open: "The 'validated' →
'evaluated' word-choice question remains open and independent, same
pattern as still-open curation finding C2." M6 touched a *different*
sentence (the Conclusion's opening claim) and left "validated" as-is
there per author decision at the time. C2 is this same word-choice
question applied to a second, independent location (Contributions
bullet 1) — the two can be decided independently; resolving C2 doesn't
require revisiting M6's already-settled sentence, and vice versa.

## 5. Proposed fixes — each shown as the full revised paragraph

**Option A — "computed"** (the original wording suggested when this
finding was first logged):

> Development of a DT readiness framework: three quantitative
> metrics ($C$, M1, M2), drawn from two independent evidence
> sources, empirical recurrence and physics-based ray tracing,
> that jointly assess measurement quality, geometric fidelity, and
> functional coverage accuracy, each computed on a held-out
> temporal split.

Minimal, one-word change. "Computed" is accurate and unambiguous, but
it's a word the rest of the paper doesn't otherwise use for this exact
claim — it would be a one-off term specific to this sentence.

**Option B — "evaluated" (recommended)**:

> Development of a DT readiness framework: three quantitative
> metrics ($C$, M1, M2), drawn from two independent evidence
> sources, empirical recurrence and physics-based ray tracing,
> that jointly assess measurement quality, geometric fidelity, and
> functional coverage accuracy, each evaluated on a held-out
> temporal split.

Same fix, different word. "Evaluated" is not a new term introduced just
for this sentence — it's already the paper's own established vocabulary
for this exact claim: §IV-B's Twin-Gate Convergence intro says
"...convergence, all evaluated exclusively on the held-out day~3," and
the Conclusion itself says "TWINGATE evaluates all three readiness
criteria across the complete four-device Berlin deployment" — the
identical three-metric claim, in the identical section of the argument,
already using "evaluates." Using "evaluated" here makes Contributions
bullet 1 consistent with the Conclusion's own wording for the same
claim, rather than introducing a third synonym ("validated" now,
"computed" as a fix) into the mix. This is the stronger option on
consistency grounds alone, independent of the overclaim issue.

**Option C — decline.** Leave "validated" as-is. Not recommended: this
is a one-word, zero-numbers, zero-risk fix for a real overclaim already
flagged as a standing item since M6; there's no rhetorical downside
analogous to C4's numeric-comparison risk here.

## 6. What NOT to change

- Don't touch the Conclusion's "constructed and validated end-to-end"
  sentence (line ~880) — that's M6's sentence, already resolved by
  author decision to keep "validated" there. C2 is scoped to
  Contributions bullet 1 only.
- Don't touch "validating the DT without ground-truth tower
  coordinates" in Contributions bullet 4 (twin-gate convergence) — that
  claim is about a single, specific, genuinely-passed cross-validation
  result (the twin-gate agreement), not the three-metrics-jointly claim
  bullet 1 makes; it doesn't have the same overclaim problem.

## 7. Resolution

**Applied: Option B.** `main.tex` §I Contributions bullet 1 now reads:

> Development of a DT readiness framework: three quantitative
> metrics ($C$, M1, M2), drawn from two independent evidence
> sources, empirical recurrence and physics-based ray tracing,
> that jointly assess measurement quality, geometric fidelity, and
> functional coverage accuracy, each evaluated on a held-out
> temporal split.

This matches the wording already used for the identical three-metric
claim in §IV-B ("...all evaluated exclusively on the held-out day~3")
and the Conclusion ("TWINGATE evaluates all three readiness
criteria..."), so the fix also removes an internal inconsistency, not
just the overclaim. The Conclusion's own "constructed and validated
end-to-end" sentence (M6's scope) was left untouched, per §6. Verified:
`main.tex` compiles cleanly end-to-end (pdflatex+bibtex+2×pdflatex),
zero errors, zero undefined references. No numbers, tables, or other
sections touched.
