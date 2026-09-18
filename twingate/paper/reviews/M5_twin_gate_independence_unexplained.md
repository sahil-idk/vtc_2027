# Review Finding M5 — Twin-Gate "Independence" Was Asserted, Not Explained

**Status:** open · **Severity:** Reviewer-would-reject-on-this · **Section(s) affected:** §III-D (Twin-Gate Coupling)

---

## 1. The plain-English version

The paper's single strongest piece of evidence is this: Gate 1 (working
purely from real drive-test logs) flags one stretch of road as a dead
zone, and Gate 2 (working purely from a physics simulation, built and
tuned without ever being told where that dead zone is) independently
predicts a big signal drop at that exact same spot. Two methods, built
from completely different evidence, agreeing on the same anomaly, is
what makes this paper's central claim credible instead of coincidental.

But here's the obvious hole a skeptical reader pokes at: **Gate 2's
simulation was tuned using real drive-test data too** — the same
vehicles that logged the dead zone also logged hundreds of ordinary
"here's the signal at this GPS point" rows nearby, all of which fed into
fitting the tower's position and calibration. If some of *those* training
rows happened to sit right next to (or inside) the dead zone, then Gate 2
isn't really predicting the dead zone "from first principles" — it might
just be echoing back a pattern it was shown directly, the same way a
student "predicts" an answer they were handed during the open-book part
of the test. If that were true, the headline convergence result would be
a foregone conclusion, not evidence of anything.

**The paper's current text tells the reader this isn't a problem, without
telling them why.** It says Gate 2's predictions used "no information
about those locations during optimization" — but doesn't say *how* that
was arranged. Readers are asked to just trust it.

## 2. Where this shows up in the paper

§III-D, "Twin-Gate Coupling," the relevant sentence:

> "Concretely, we evaluate Gate~2's refined predictions at the GPS
> locations Gate~1 identified as TypeB, using no information about those
> locations during optimization, which was fitted purely to minimize
> training RSRP MAE."

That's the entire defense. No mechanism, no radius, no step in the
pipeline named. A reviewer reading this has every right to ask: *"How do
you know? Show me."*

## 3. What actually enforces this, in the code

Checked `twingate/A19_gate2_final.py`. The mechanism is real, specific,
and already implemented — it's just never surfaced in the paper text:

```python
TYPEB_CENTROID_LAT = 52.514
TYPEB_CENTROID_LON = 13.349
ZONE_EXCLUDE_RADIUS_M = 150.0
APPLY_ZONE_EXCLUSION = (OPERATOR == 2)   # only where Gate 1 confirmed a dead zone

# ... later, before WCL init / Nelder-Mead / OLS calibration:
if APPLY_ZONE_EXCLUSION:
    train_all["_dist_typeb"] = haversine_m(train_all[LAT_COL], train_all[LON_COL],
                                            TYPEB_CENTROID_LAT, TYPEB_CENTROID_LON)
    train_all = train_all[train_all["_dist_typeb"] > ZONE_EXCLUDE_RADIUS_M].copy()
```

In plain terms: for Operator 2, every training row within 150 m of the
Gate 1 dead-zone centroid is thrown out **before** the tower's starting
position is estimated, **before** the position/height/orientation search
runs, and **before** the final calibration is fit. The refined tower
geometry that later gets evaluated at the dead zone is built entirely
from data that never touched the dead zone. Operator 1 gets no such
exclusion, because Operator 1 has no Gate-1-confirmed dead zone to leak
from in the first place (`C = 0.00` there).

This is a real, specific, correct defense against exactly the objection
above. It just currently exists only in code comments, not in the paper
a reviewer actually reads.

## 4. Why this is high severity, not just a nice-to-have

This isn't a minor supporting detail — it's the thing that makes the
paper's central claim (twin-gate convergence) mean anything at all. Every
other result in the paper (C, M1, M2) is explicitly evaluated on a
held-out day; if the one exception — the headline convergence check — is
the one place where "no leakage" is merely asserted rather than shown,
that's exactly where a careful reviewer will focus, and exactly where the
paper is currently weakest on the page (even though it's strong in the
actual implementation).

## 5. The fix

Text-only, no new experiment — the mechanism already exists and is
already correct, it just needs to be stated. Add the specifics directly
into §III-D, right where independence is currently just asserted:

> "...using no information about those locations during optimization,
> which was fitted purely to minimize training RSRP MAE: for Operator 2,
> training rows within 150 m of the Gate 1 TypeB centroid are excluded
> before WCL initialization, before the Nelder-Mead search, and before
> the final OLS calibration fit, so the refined tower geometry is derived
> entirely from rows outside the zone under test."

## 6. Recommendation

Apply immediately — this is the cheapest possible fix (one inserted
clause, no new data, no risk of contradicting anything else in the
paper) for one of the highest-severity findings in the whole review,
since it directly defuses the most obvious objection to the paper's
central claim.

**Applied.** See `main.tex` §III-D.

## 7. Empirical spot-check: does the predicted drop survive the exclusion, for real?

Section 5's fix explains the mechanism in the paper. This section checks
it actually works, using real computed output rather than just reading
the code.

`twingate/out/pc2_gate2_final_val_predictions.csv` and
`pc3_gate2_final_val_predictions.csv` are Operator-2 runs, so
`APPLY_ZONE_EXCLUSION` was active for both — the 150 m TypeB-centroid
training rows were genuinely excluded before these predictions were
generated. Computing the same near-zone-vs-background comparison the
paper's convergence claim rests on, directly from these files:

| | Rows | Mean predicted power (calibrated) |
|---|---:|---:|
| Near TypeB (≤150 m) | 161 | **−113.07 dBm** |
| Background (>150 m) | 14,904 | **−88.89 dBm** |
| **Predicted drop** | | **24.18 dB** (Welch $t=-22.47$, $p=8.8\times10^{-52}$) |

This confirms, with a real run rather than an assumption, that excluding
the nearby training rows does not make the predicted dead zone disappear
— Gate 2 still independently lands on a large, highly significant signal
drop at the same location Gate 1 flagged, using geometry fit entirely
from rows outside that zone. That is exactly the property §III-D's fix
now claims in words.

**Caveat, so this isn't overstated:** this does **not** reproduce the
paper's published headline numbers (26.3 dB drop, 364 near-zone rows) —
it's close in direction and rough magnitude (24.18 dB vs. 26.3 dB) but
not an exact match, and the row count differs (161 vs. 364). That's
consistent with the same provenance gap already documented in
`M4_overfitting_risk_ablation_table.md` §7 and
`LEFTOVERS_GPU_REQUIRED.md`: these checked-in files are from an earlier
or partial run, not the exact run behind Table I / the published
convergence figures. What this spot-check verifies is narrower but still
real: **the mechanism M5 documents genuinely produces the claimed effect
direction and significance**, on the data that's actually available right
now. Reproducing the exact published 26.3 dB figure is the same
GPU-dependent rerun already tracked in `LEFTOVERS_GPU_REQUIRED.md`, not a
new blocker.
