# Gate 1 Redesign: From Completeness to Coverage

**Status:** analysis complete, pending decision on composite-score weighting (see
"Open Question" at the end).

## 1. Why this analysis happened

The original DT-QUEST manuscript's central completeness claim (Berlin cellular,
16 percentage-point SUMO accuracy gap between the complete PC1 subset and the
incomplete PC2-PC4 subsets) was challenged by Reviewer 2:

> "PC1 and PC2-PC4 correspond to different vehicles, which may have traversed
> different routes, environments, and signal conditions. To isolate
> completeness as the sole cause, a controlled experiment is needed — for
> example, artificially sub-sampling PC1 to match the completeness level of
> PC2-PC4 and observing the resulting accuracy drop."

This document reports that controlled experiment, what it actually found, and
where it leads the Gate 1 (data-readiness) design.

## 2. Experiment 1 — controlled MCAR completeness test

**Design.** Using PC1 only (single vehicle, single route, identical physical
conditions in both arms — the confound Reviewer 2 raised is fully eliminated
by construction):

1. Geolocate PC1's serving towers via OpenCelliD (69/144 towers matched for
   Operator 1).
2. Compute real haversine distance from each row's GPS position to its
   serving tower.
3. Hold out a **fixed test set** (30% of eligible rows) — the *same* physical
   rows are scored in every condition below.
4. Fit a simple, transparent model on the remaining training pool: RSRP ~
   a_band + b_band * log10(distance), one 2-parameter fit per frequency band
   (ordinary least squares).
5. Score: percentage of held-out predictions within 6 dB of measured RSRP
   (accuracy metric defined precisely and up front, per Reviewer 2's
   methodological request).
6. **FULL condition**: train on the natural ~99.95%-complete training pool.
7. **DEGRADED condition**: randomly null out additional RSRP values in the
   training pool until its completeness matches PC4's real rate (79.04%),
   i.e. an extra ~20.9% MCAR (missing completely at random) dropout. Repeated
   over 5 random trials.

**Result.**

| Condition | Training rows | MAE | % within 6dB |
|---|---|---|---|
| FULL (99.95% complete) | 26,984 | 7.85 dB | 44.19% |
| DEGRADED (79.04%, 5 trials) | 21,374 avg | 7.85 dB | 44.13% ± 0.02 |
| **Gap** | | | **0.06 pp** |

A follow-up sweep down to 2% of the training pool (533 rows) still held
accuracy at ~44%, flat within noise. **Random removal of training rows, even
down to a tiny fraction of the original volume, does not measurably hurt this
prediction task.** The original paper's 16pp gap cannot be explained by row
*quantity* under this test. The simple 2-parameter-per-band model saturates
almost immediately; more rows past a very small number add no information the
model can use.

**Interpretation.** This directly reproduces Reviewer 2's suspicion: the old
16pp gap was very likely the PC1-vs-other-vehicles confound (different
routes/environments), not completeness. Completeness-as-primary-readiness-axis
does not survive this controlled test and should be retired as the headline
claim.

## 3. Finding — missingness is structured (MNAR), not random

Before concluding "missingness doesn't matter at all," the *mechanism* by
which PC4 actually lost data was checked, since the MCAR test above assumed
random single-row drops, which may not reflect reality.

**Co-missingness check.** In every device, `PCell_Cell_Identity` and
`PCell_RSRP_max` are missing together (~98.4-99.2% agreement) — this is
**whole-measurement dropout**, not an isolated field going blank while the
rest of the row stays intact.

**Run-length check (PC4).** Sorting PC4 by time and measuring the length of
each contiguous missing-data streak:

- 11 distinct gap events total
- lengths: median 9 rows, max **9,045 consecutive rows**
- Total missing: 9,698 rows across only 11 events

This is the signature of an **equipment/connectivity outage** (e.g. a tunnel,
a dead zone, a logging failure) — a handful of large contiguous blocks, not
thousands of independent random single-row failures. The MCAR test above,
while a valid test of "does row quantity matter," does not test what actually
happened to PC4.

## 4. Experiment 2 — blockwise (structured) degradation

**Design.** Same PC1 setup as Experiment 1, but instead of randomly nulling
21% of training rows, remove one **contiguous, distance-sorted block** of
21% of the training pool, in three positions:

| Removed block | Training rows | MAE | % within 6dB |
|---|---|---|---|
| Nearest 21% (near-tower) | 21,318 | 7.89 dB | 43.47% |
| Middle 21% | 21,318 | 7.86 dB | 44.03% |
| **Farthest 21% (cell-edge)** | 21,318 | **7.98 dB** | **42.67%** |
| (reference: FULL, no removal) | 26,984 | 7.85 dB | 44.19% |
| (reference: random 21% MCAR) | 21,374 avg | 7.85 dB | 44.13% |

**Result.** Losing the farthest/cell-edge distance regime costs **~1.5
percentage points** — small in absolute terms, but a real, repeatable effect
that random removal of the same amount of data does not produce at all.
**Which conditions go missing matters; how much data is missing, by itself,
mostly does not.**

## 5. The coverage score

Given (2)-(4), the readiness signal that should replace completeness-%% is a
measure of whether a device's data spans the range of physical conditions the
twin will need to predict for — not how many rows it has.

**Definition (v1, two axes, entropy-based, dataset-agnostic):**

For a given device/slice:

1. **Distance-bin coverage.** Bin serving-tower distance on a fixed schema
   (here: `[0,30,60,100,150,250,500,1000,5000]` m — chosen to span typical
   urban-macro-cell near/mid/far regimes). Compute the Shannon entropy of the
   row-count distribution across bins, normalized by the maximum possible
   entropy (uniform spread across however many bins are populated). Score of
   1.0 = perfectly even coverage across all distance regimes; low score =
   samples clustered in one or two regimes only.
2. **Band-diversity coverage.** Same entropy calculation over the frequency
   bands (`PCell_freq_MHz`) actually served to that device.
3. **Composite score** (v1, naive): unweighted average of the two.

**Result across the 4 Berlin cellular devices:**

| device | rows | distance coverage entropy | bands seen | band diversity entropy | composite score |
|---|---|---|---|---|---|
| pc1 | 38,540 | 0.834 | 3 (96.8% one band) | **0.130** | 0.482 |
| pc2 | 14,167 | 0.797 | 4 | 0.720 | 0.759 |
| pc3 | 21,655 | 0.830 | 3 | 0.691 | 0.761 |
| pc4 | 20,589 | 0.837 | 2 (97.3% one band) | **0.180** | 0.508 |

**The headline surprise: PC1 — ranked "best" by completeness (99.95%) — has
the worst band-diversity coverage, tied with PC4.** Both Operator 1 devices
(pc1, pc4) see almost exclusively the 1800MHz band (96.8% / 97.3% of rows);
Operator 2's devices (pc2, pc3) see a genuine 3-4-band mix. PC1 also has
essentially zero far-distance samples (2 rows beyond 1km, out of 38,540) —
invisible to a completeness metric, immediately visible to a coverage metric.

## 6. What this means for Gate 1

| Old Gate 1 | New Gate 1 |
|---|---|
| Completeness % as primary readiness signal | Completeness % demoted to a secondary diagnostic only |
| (no coverage concept) | **Feature-space coverage score** (distance-bin entropy + band-diversity entropy) as a primary axis |
| (no missingness-mechanism check) | **Structural missingness check**: co-missingness + run-length analysis, flags equipment-outage-style gaps distinctly from scattered noise |
| Value-correctness / representation checks (V1, V2, V3) | Unchanged — these are independently justified (TiHAN case) and not touched by this analysis |

## 7. Open question — composite score weighting

The 50/50 weighting of distance-coverage and band-diversity above is a
placeholder, not a fitted result. The principled next step, matching the
two-gate architecture's own logic: correlate each coverage sub-score (and
candidate combinations) against actual Gate 2 (Sionna RT) fidelity across
enough slices to let the weights be *derived* from evidence rather than
asserted. This is the same "let Gate 2 calibrate Gate 1" idea from the
original two-gate plan, now with a concrete, testable candidate metric to
calibrate.
