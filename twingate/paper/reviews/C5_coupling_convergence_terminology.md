# Review Finding C5 — "Coupling" (Method) vs. "Convergence" (Result) Terminology Split Never Flagged as Intentional

**Status:** documented, not yet applied · **Severity:** ⚪ Polish ·
**Section(s) affected:** §III-D "Twin-Gate Coupling" (where the
clarifying clause should be added), §IV-B "Twin-Gate Convergence"
(the section this bridges to)

---

## 1. The plain-English version

The paper uses two different names for what is, mechanically, the same
underlying idea, and never says so explicitly. §III-D (Method) is
titled **"Twin-Gate Coupling"** — it describes the *mechanism*: how
Gate 1's labels are withheld from Gate 2's training, so that if Gate 2
independently predicts a signal drop at Gate 1's identified location,
that agreement means something. §IV-B (Results) is titled **"Twin-Gate
Convergence"** — it reports the *outcome* of running that mechanism: the
actual 26.3dB predicted drop against the 30.4dB measured collapse. A
reader who notices both section titles ("Coupling" vs. "Convergence")
without being told they refer to the same thing might reasonably wonder
whether these are two distinct concepts, or whether one is a subset of
the other, or whether the terminology is just inconsistent — none of
which is true, but nothing in the text rules those readings out. This
is the lowest-stakes item in the whole review (nothing is factually
wrong, and a careful reader works it out from context), but it costs a
reviewer a moment of doubt at exactly the section carrying the paper's
central claim (per the already-applied C7 fix) — not the place to leave
any ambiguity, however small.

## 2. The two sections as they exist today, in full

**§III-D, "Twin-Gate Coupling" (Method), opening paragraph:**

```
The two gates are not independent evaluation tracks but a closed
validation loop: Gate~1 classifies dead zones \emph{empirically} from
measurement statistics, Gate~2 reconstructs the radio environment
\emph{from physics}, and a faithful DT should cause both to converge on
the same anomalies. Concretely, we evaluate Gate~2's refined
predictions at the GPS locations Gate~1 identified as TypeB, using no
information about those locations during optimization, which was
fitted purely to minimize training RSRP MAE: for Operator~2, training
rows within 150\,m of the Gate~1 TypeB centroid are excluded before WCL
initialization, before the Nelder-Mead search, and before the final OLS
calibration fit, so the refined tower geometry is derived entirely from
rows outside the zone under test. A signal drop at these
locations means the DT has reproduced the dead zone from first
principles; if not, the OSM scene is likely missing the physical
blocker. Section~\ref{sec:discussion} develops why this coupling is a
meaningfully strong validation signal, not merely a consistency check.
```

**§IV-B, "Twin-Gate Convergence" (Results), opening paragraph:**

```
The central DT validation question is whether the physics model
independently reproduces the coverage holes Gate~1 found empirically.
We evaluate calibrated Sionna predictions (Operator~2, pc2$+$pc3,
Stage~4 refined positions with diffuse scattering) at the 364
validation GPS rows within 150\,m of the Gate~1 TypeB centroid, against
14,807 background rows elsewhere on the route.
```

Notice §III-D's own text already uses the word "converge" once
("...should cause both to converge on the same anomalies") — the
overlap is already half-visible in the prose, just never stated as
"this is why the two section titles use related-but-different words."

## 3. Proposed fixes — each shown as the full revised passage

**Option A (recommended) — add one clarifying clause to §III-D's
opening paragraph, right after the sentence that already uses
"converge":**

> The two gates are not independent evaluation tracks but a closed
> validation loop: Gate~1 classifies dead zones \emph{empirically} from
> measurement statistics, Gate~2 reconstructs the radio environment
> \emph{from physics}, and a faithful DT should cause both to converge
> on the same anomalies. We refer to this cross-checking mechanism as
> \emph{coupling} here, as a design choice; Section~\ref{sec:convergence_result}
> reports the resulting numeric agreement itself as \emph{twin-gate
> convergence}, the outcome this coupling is designed to produce.
> Concretely, we evaluate Gate~2's refined predictions at the GPS
> locations Gate~1 identified as TypeB, using no information about
> those locations during optimization, which was fitted purely to
> minimize training RSRP MAE: for Operator~2, training rows within
> 150\,m of the Gate~1 TypeB centroid are excluded before WCL
> initialization, before the Nelder-Mead search, and before the final
> OLS calibration fit, so the refined tower geometry is derived
> entirely from rows outside the zone under test. A signal drop at
> these locations means the DT has reproduced the dead zone from first
> principles; if not, the OSM scene is likely missing the physical
> blocker. Section~\ref{sec:discussion} develops why this coupling is a
> meaningfully strong validation signal, not merely a consistency
> check.

Costs two sentences, inserted mid-paragraph, uses only the
already-existing `sec:convergence_result` label, and resolves the
ambiguity at the exact point a reader would first form it (the first
time "coupling" appears as a named mechanism, before they've even
reached the "Convergence" section title later in the paper).

**Option B — lighter touch: a parenthetical on the section title
itself**, rather than new body text:

> \subsection{Twin-Gate Coupling (Method)}

paired with, unchanged, in §IV-B:

> \subsection{Twin-Gate Convergence}

This signals the method/result distinction to anyone scanning the
table of contents or section headers, at the cost of zero body text,
but is a weaker fix than Option A: it labels the *sections* as
method-vs-result without ever explaining *why* the same underlying idea
gets two different nouns, so a reader who does read the body text
still doesn't get the explicit "these are the same mechanism, named
differently for its design (coupling) vs. its measured outcome
(convergence)" statement Option A provides.

**Option C — both.** Apply Option B's title parenthetical and Option
A's clarifying clause together. Marginal extra cost over Option A
alone; probably unnecessary if Option A is applied, since Option A
already does the heavier-lifting explanatory work Option B's title tag
would only partially anticipate.

**Option D — decline.** Leave both sections exactly as titled today.
Defensible — this is the lowest-severity finding in the review (⚪
Polish) and the overlap is already partly visible in §III-D's own
"converge" wording. Not recommended only because Option A is a
two-sentence, zero-numbers, zero-risk fix for a section that carries
the paper's single most important result.

## 4. What NOT to change

- Don't rename either section title as part of Option A — the fix is
  entirely in §III-D's body text; §IV-B is untouched under Option A.
- Don't touch the M2 metric description immediately preceding §III-D
  (lines 521–528, "Dead-zone detection accuracy") — that's a separate
  paragraph describing a different (though related) cross-gate
  evaluation, already covered by the C1 fix's discussion of M2 as a
  joint metric; C5 is scoped to the Coupling/Convergence naming split
  specifically.
- Don't touch §IV-B's own text under any option here — the ambiguity
  this finding addresses is resolved by clarifying §III-D once, before
  the reader ever reaches §IV-B; there's nothing wrong with §IV-B's own
  wording that needs fixing.

**Not applied.** No changes to `main.tex` — this document only lays out
the finding and drafted fix text (Options A, B, and C, full passages)
for review.
