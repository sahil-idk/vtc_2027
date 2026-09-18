# Review Finding M3 — "Threshold Sensitivity" Is Asserted, Never Shown

**Status:** ✅ fixed · **Severity:** Reviewer-would-reject-on-this · **Section(s) affected:** §IV-A (Gate 1 Results)

**Resolution note:** applied as prose, not a dedicated table. Reasoning:
this paper already carries two headline results tables (Gate 2 pipeline,
M2 detection); a third table for a secondary robustness check on one
parameter reads as disproportionate and risks a reviewer's eye landing on
"$C=1.00$" before reaching the explanation of why that's expected. Inline
prose lets the sentence give the real numbers and the saturation
explanation in the same breath, in a controlled order.

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

## 5. Path A was run — actual results

Dataset provided by the author (`cellular_dataframe_2.parquet`, converted
to `cellular_dataframe_cleaned.csv`, gitignored, not committed). Baseline
run first confirmed an exact match to the paper (4 TypeA / 57 TypeB / 13
Ambiguous / $C=12/15=0.80$) before sweeping `RECUR_DIST_M` over
$\{50, 75, 100, 125, 150\}$\,m:

| $d_\text{recur}$ (m) | train TypeB | train Ambiguous | val TypeB (denom.) | matched | $C$ |
|---:|---:|---:|---:|---:|---:|
| 50  | 56 | 14 | 5  | 0  | 0.000 |
| 75  | 57 | 13 | 10 | 5  | 0.500 |
| **100** | **57** | **13** | **15** | **12** | **0.800** (paper's value) |
| 125 | 58 | 12 | 16 | 14 | 0.875 |
| 150 | 58 | 12 | 16 | 16 | 1.000 |

Raw per-radius outputs saved to
`twingate/out/g1_summary_d{50,75,100,125,150}.json`.

**Finding: the "robust" claim was false.** $C$ moves monotonically across
the full 0–1 range over a 100\,m window — the opposite of robust.

**But the mechanism explains why, and it's a usable, honest story.** A
larger radius can only make cross-vehicle matching easier, so $C \to 1$ is
a trivial ceiling as $d_\text{recur} \to \infty$ (confirmed: exactly that
happens at 150\,m — every held-out gap matches, which is the metric
saturating, not the DT being validated). The authors did not pick the
radius that maximizes $C$; they fixed $d_\text{recur}=100$\,m from an
independent physical argument (GPS centroid uncertainty at 1\,Hz),
well short of the saturation point. That is a stronger anti-cherry-picking
argument than the original false "robustness" sentence.

## 6. Recommended replacement text

> "**Threshold sensitivity.** $C$ increases monotonically with
> $d_\text{recur}$, from 0.00 at 50\,m to 1.00 at 150\,m (Table
> [sensitivity]), since a larger matching radius can only make
> corroboration easier; $C \to 1$ is a trivial ceiling, not evidence of
> validation. We fix $d_\text{recur}=100$\,m *a priori* from GPS centroid
> uncertainty at 1\,Hz sampling, well short of this ceiling, rather than
> selecting it to maximize $C$."

Open decision: present the sweep as a small inline table (more convincing
to a reviewer, costs a few lines of layout) or as prose only summarizing
the two endpoints and the 100\,m value. **Not yet applied to `main.tex`**
pending that choice.
