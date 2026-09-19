# Review Finding M8 — Limitations Section Lists Only Distant Weaknesses, Not the Nearest Ones

**Status:** documented, not yet applied · **Severity:** 🟠 Weakens-the-paper ·
**Section(s) affected:** §VI-A "Limitations and Future Work" (the bulleted
list just before the Conclusion)

---

## 1. The plain-English version

Every paper's Limitations section gets read by reviewers looking for one
thing: did the authors admit the weaknesses *closest to their own central
claim*, or only the ones far away from it? A Limitations list that only
mentions distant, easy-to-admit gaps (different city, different radio
generation, compute cost) while staying silent on the nearest, most
load-bearing weaknesses reads — fairly or not — as evasive, and invites a
reviewer to write the missing bullets *for* you, in the review, in a much
less charitable tone.

Right now, `main.tex`'s Limitations section (§VI-A) has exactly this
pattern. All four current bullets are true, but all four are "distant"
in the sense that none of them touches the paper's actual headline
result — the twin-gate convergence at the one confirmed Operator 2 dead
zone. The nearest weaknesses — the ones a sharp reviewer would raise
first, because they're about the specific evidence the paper's central
claim rests on — aren't mentioned at all.

## 2. What's currently there (§VI-A, four bullets)

```
- Single-dataset scope: one Berlin route, two LTE operators, June 2021;
  generalization to other cities/5G NR/high-mobility V2X unconfirmed.
- Dynamic scatterers: moving vehicles as secondary blockers/reflectors
  the static scene omits.
- Doppler and wideband metrics: fast fading invisible to the L3-filtered
  RSRP metric; delay spread/BLER would need I/Q logging not available.
- Search radius and compute cost: ±500m search radius may under-serve
  peripheral segments; 3-6 min/tower NM cost is offline-only.
```

These are all real limitations, and none should be removed. The
complaint is what's *missing*, not what's there.

## 3. What's missing — the two nearest weaknesses

### (a) The entire empirical validation rests on one dead zone

Re-reading §IV-A and the Twin-Gate Convergence section (§IV-B) together:

- Gate 1 finds "two distinct geographic clusters" of TypeB gaps across
  training days 1-2, but only **one** of them — the 56-gap Operator 2
  (Vodafone) cluster at (52.514°N, 13.349°E) — is treated as confirmed.
  The paper's own text calls the second, Operator 1 location "tentative
  ... treated as low-confidence, since its only corroboration is itself
  an Ambiguous event."
- Operator 1's own lone TypeB gap doesn't recur on the held-out day at
  all ($C=0.00$), and the paper explicitly says this "signal[s]
  insufficient measurement density to certify a dead zone... prompting
  additional drive-test passes rather than proceeding to Gate 2 on thin
  evidence" — i.e., Operator 1 never even reaches the twin-gate
  convergence test.
- So **every quantitative validation result that depends on there being
  a real, confirmed dead zone to test against** — $C=0.80$, the
  multi-KPI corroboration (RSRQ/SNR/MCS/throughput collapse), and the
  twin-gate convergence itself (26.3dB predicted vs. 30.4dB measured,
  "this paper's central claim" per the Conclusion) — comes from
  **one geographic location, one operator, one 350m stretch of road**.

This isn't a hidden flaw — the paper's own text is honest about it
locally (Operator 1's $C=0.00$ is reported plainly, not hidden) — but
it is never stated as a *limitation of the overall evidentiary base* in
the one place (§VI-A) a reviewer checks for exactly this kind of
self-assessment. Right now a reader has to reconstruct "the entire
central claim rests on n=1 confirmed dead zone" themselves by
cross-referencing three separate subsections; nothing tells them to.

### (b) Classifier thresholds are tuned/checked against that same single instance, never cross-validated against a second independent one

Two thresholds matter for the paper's results:

- $d_\text{recur} = 100$m (the Gate 1 gap-matching radius, §III-A /
  §IV-A "Threshold sensitivity")
- $\tau = -113$dBm (the Gate 2/M2 dead-zone detection threshold, §IV-C,
  "close to the mean Sionna prediction at TypeB locations
  ($-115.6$dBm) found independently")

M3 (already fixed, see `M3_threshold_sensitivity.md`) added a real
sensitivity sweep showing $C$ is monotonic in $d_\text{recur}$ and that
100m is fixed a priori rather than cherry-picked to maximize $C$ — that
was a good, honest fix. But a sensitivity sweep over $d_\text{recur}$ is
not the same thing as **cross-validating the threshold against a second,
independently confirmed dead zone**. Both thresholds are currently
justified using properties of the *same* Operator 2 cluster they're then
evaluated against (the $-113$dBm threshold is explicitly derived from
that cluster's own mean predicted RSRP). There is no second confirmed
dead zone anywhere in the dataset to check whether either threshold
generalizes to a geometrically different location. This is the natural,
more specific companion to (a): not just "the evidence base is thin,"
but "the specific numeric knobs were never checked against anything
beyond that thin evidence base."

## 4. A third candidate that's *already been superseded* — flagging so it isn't re-added by mistake

The original finding (surfaced in the framing-audit subagent's pass,
recorded in `TODO.md`) listed a third missing bullet: **"M1 not crossing
its own threshold."** This is now stale and should **not** be added as
written. It was true when M8 was first identified, back when §III-C-6
defined M1<3dB as a binary pass/fail readiness criterion and Table I
scored every stage against it. Since then, M7/M9/M10/M12 (already
applied, see `TODO.md`) removed that framing entirely: M1 is no longer a
pass/fail gate at all, both operators' Stage 4 M1 (3.02dB / 4.04dB) are
now described as falling "comfortably within" the 3GPP TS 36.133 ±6dB
bound, and Table I's "M1<3dB?" column is gone. Re-adding a Limitations
bullet about "M1 not crossing its own threshold" would directly
contradict that already-applied fix and reintroduce the exact
accuracy-chasing framing the paper just moved away from.

If a third bullet is wanted here, the more accurate modern equivalent —
consistent with M9/M10's own already-applied language — would be
something like: *M1's fidelity reading is corroborating, not
independently dispositive, evidence that the recovered geometry is
literally correct (as opposed to merely MAE-minimizing); the strongest
evidence for that is the twin-gate convergence, which itself only exists
for the one Operator 2 dead zone (see bullet (a))*. This would actually
reinforce, rather than duplicate, (a) and (b) rather than being a third
independent point — which is arguably a reason to fold it into (a)
instead of adding a separate bullet. Recommend leaving it out as a
separate bullet and only mentioning it, if at all, as a clause inside
bullet (a).

## 5. Proposed fix text (two new bullets, drafted, not yet applied)

Adding to the existing `itemize` list in §VI-A, after "Single-dataset
scope" (since these are thematically closest to it) and before "Dynamic
scatterers":

> \item \textbf{Single confirmed dead zone:} the measurement-quality
> criterion ($C=0.80$), the multi-KPI corroboration, and the twin-gate
> convergence result — this paper's central validation claim — are all
> demonstrated against one geographic dead zone (the Operator~2 cluster
> at $52.514^\circ$N, $13.349^\circ$E). Operator~1's only candidate
> location does not recur on the held-out day ($C=0.00$) and is
> explicitly not carried forward to Gate~2. A second independently
> confirmed dead zone, ideally from a different operator or route
> segment, would be needed to show the pipeline's central result
> generalizes beyond this one instance.
>
> \item \textbf{Thresholds validated against the same instance they are
> evaluated on:} the Gate~1 matching radius ($d_\text{recur}=100$\,m)
> and the Gate~2 detection threshold ($\tau=-113$\,dBm) are both fixed
> \emph{a priori} rather than tuned to maximize $C$ or F1 (Sections
> \ref{sec:gate1results}, \ref{sec:gate2results}), but neither has been
> checked against a second, independently confirmed dead zone; both are
> derived from and evaluated on properties of the same Operator~2
> cluster discussed above.

(Exact LaTeX wording, section/label references, and placement to be
finalized at apply-time — the above is a draft matching the paper's
existing register, not final copy.)

## 6. Why this is worth doing (and the honest cost)

**Upside:** these are the two bullets a competent reviewer is most
likely to write themselves if the authors don't. Naming them first, in
the authors' own words, converts "the authors missed this" into "the
authors know this and are being upfront about it" — the single highest-
leverage thing a Limitations section can do. Both bullets are also
*already true and already visible* elsewhere in the paper's own text
(§IV-A, §IV-B) — this isn't inventing a new weakness, only surfacing an
existing one where reviewers actually look for it.

**Cost / risk:** stating "central claim rests on n=1 confirmed dead
zone" this plainly, right before the Conclusion restates that same
claim as "this paper's central claim," is a real rhetorical risk — it
could read as undercutting the paper's own headline result one section
before it's made. This is a judgment call for the author, not something
to apply unilaterally.

## 7. Options

- **A — apply both bullets as drafted.** Most complete, most honest,
  matches the pattern already used for M1/M7/M9/M10 (name the gap
  precisely rather than paper over it).
- **B — apply bullet (a) only, fold (b) into it as a subordinate clause**
  (per §4's suggestion) to avoid the list reading as three separate
  restatements of "we only have one dead zone."
- **C — soften bullet (a)'s wording** (e.g., move "this paper's central
  validation claim" out of the bullet itself, let the Conclusion's own
  existing "single urban deployment" sentence carry some of that weight,
  and keep the Limitations bullet narrower/more technical) if the
  rhetorical risk in §6 is judged too sharp as currently drafted.
- **D — do nothing / decline.** Leave §VI-A as-is. Not recommended (this
  is exactly the "nearest weakness" gap the finding is about), but
  included since the final call is the author's.

**Not applied.** No changes to `main.tex` — this document only lays out
the finding, the already-superseded third candidate, and drafted fix
text for review.
