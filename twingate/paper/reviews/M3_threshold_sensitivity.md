# Review Finding M3 — "Threshold Sensitivity" Is Asserted, Never Shown

**Status:** open · **Severity:** Reviewer-would-reject-on-this · **Section(s) affected:** §IV-A (Gate 1 Results)

---

## 1. The text as written

§IV-A, the full "Threshold sensitivity" paragraph:

> "**Threshold sensitivity.** Completeness is robust to the matching radius $d_\text{recur}$, chosen to match GPS centroid uncertainty at 1\,Hz sampling."

One sentence, under a heading that promises a sensitivity analysis, delivering none.

## 2. Why this is high severity

$d_\text{recur} = 100$\,m is one of exactly two parameters in Gate 1's entire
classification rule (§III-A, "Classifier and Validation"). Every TypeB
label — and therefore the headline result $C = 0.80$ (Eq. 4) — is a direct
downstream function of this one distance cutoff. A metric that sensitive
to a single knob is exactly the kind of thing a reviewer checks for
cherry-picking: *"would $C$ still be 0.80 at 90\,m or 120\,m, or does it
collapse?"* Nothing in the paper answers this. The paragraph's own title
sets up the expectation of a sweep and then doesn't deliver one — which
is more conspicuous than if the paragraph didn't exist at all.

## 3. A second issue inside the same sentence

"Chosen to match GPS centroid uncertainty" is a legitimate **a priori
design justification** — it explains why 100\,m was picked *before*
looking at results, which is a real defense against "you tuned this to
maximize your score." But that is a different claim from "**robust**,"
which asserts an *empirical* finding (the result doesn't change much
under variation) that was never measured. The sentence conflates the two:
a justification for the initial choice is not evidence of robustness to
that choice.

## 4. Two fix paths

**Path A — run the actual sensitivity check (recommended if there's appetite for one more experiment).**
`twingate/G1_completeness.py` already implements the full classification
and completeness pipeline; `RECUR_DIST_M` (line ~46) is the only constant
that needs to change. Rerun at a small grid, e.g. $d_\text{recur} \in
\{50, 75, 100, 125, 150\}$\,m, and report how $C$ (and the TypeB/Ambiguous
split sizes) move. If $C$ stays in a similar range across that grid, the
paper gets to make a real "robust" claim backed by a table; if it doesn't,
that's worth knowing before submission, not after review.

Estimated cost: a few reruns of an existing script — no new infrastructure,
no new data.

**Path B — text-only, no new experiment.**
Replace the unsupported robustness claim with the honest, narrower thing
that's actually true:

> "$d_\text{recur} = 100$\,m was fixed a priori to GPS centroid uncertainty
> at 1\,Hz sampling rather than tuned on the data; we did not sweep this
> parameter, since it follows from measurement geometry rather than being
> fit to the completeness score."

This removes the false claim without requiring new numbers, at the cost
of no longer being able to say "robust."

## 5. Recommendation

Path A is cheap enough (one existing script, five reruns) that it's worth
doing if there's any time before submission — it would let the paper keep
a real sensitivity claim instead of retreating from one. Path B is the
fallback if there isn't time: it's honest and defensible, just weaker.

**Not yet applied.** Waiting on a decision between Path A and Path B
before touching `main.tex`.
