# Review Finding C1 — "Layers" (Intro) vs. "Gates" (Method) Vocabulary Never Explicitly Reconciled

**Status:** ✅ fixed (Option A applied) · **Severity:** ⚪ Polish ·
**Section(s) affected:** §III "TWINGATE Framework" (where the bridge
should be added), §I "Introduction" (where the vocabulary this bridges
originates)

---

## 1. The plain-English version

The paper uses two different vocabularies to describe the same
underlying structure, and never explicitly says they're the same
structure. §I introduces three **"readiness layers"**: Measurement
quality, Geometric fidelity, and Functional coverage accuracy — each
gets its own named subsection. §III then introduces two
**"Gates"**: Gate 1 and Gate 2. A reader has to work out for themselves
that "Measurement quality" is Gate 1's job, "Geometric fidelity" is
Gate 2's job, and "Functional coverage accuracy" is... somewhere else,
computed from both. Nothing in the paper states this mapping directly;
it's inferable, with effort, from Contributions bullet 1 (which lists
the three layers and says they're "drawn from two independent evidence
sources") plus separately reading the Method and Results sections and
piecing together which metric comes from where. This is a pure
readability issue — nothing here is wrong or contradictory, unlike
M1/M2/etc. — but a reviewer skimming for structure loses time
re-deriving a mapping the authors already know and could just state.

## 2. What's actually true about the mapping (verified against the text, not just the original finding's guess)

This is worth stating carefully, because it turns out to be more
specific — and more interesting — than "three layers, two gates,
roughly line up":

- **Measurement quality → $C$ → Gate 1 alone.** §IV-A computes $C$
  entirely from Gate 1's TypeB gap recurrence between training and
  held-out days. Gate 2 plays no role.
- **Geometric fidelity → M1 → Gate 2 alone.** M1 (RSRP MAE) is computed
  entirely from Gate 2's calibrated Sionna predictions against measured
  RSRP. Gate 1 plays no role.
- **Functional coverage accuracy → M2 → *jointly*, from both gates.**
  This is the detail easy to miss: §IV-C's M2 computation (the
  $-113$dBm threshold check, precision/recall against "the 364
  TypeB-zone rows") scores Gate 2's predictions specifically at the
  locations Gate 1's classifier identified as TypeB. M2 is not a
  Gate-2-only metric the way M1 is — it's Gate 2's output evaluated
  against Gate 1's labels, structurally closer to the twin-gate
  convergence check (§IV-B) than to M1.

So the honest bridging statement isn't just "layer X maps to gate Y" —
it's "two of the three metrics are single-gate, and the third is
already a joint measurement between the two gates, foreshadowing the
twin-gate convergence result later." That's a more precise and more
interesting claim than the generic version, and it directly reinforces
the paper's own already-established thesis (from the C7 fix) that
joint, cross-gate evidence is what the paper is really about.

## 3. The paragraph today, in full (§III opening, before the architecture figure)

```
This section presents the TWINGATE architecture, which couples
empirical gap classification with physics-based ray tracing, as
illustrated in Fig.~\ref{fig:architecture}. The figure displays the
complete processing path from drive-test data to twin-gate coupling,
expanded to show each pipeline's internal stages: gap detection and
classification for Gate~1, scene construction and 4D optimization for
Gate~2. Both pipelines run in parallel on the same RSRP logs, neither
told what the other found until the final convergence check.
```

This paragraph introduces Gate 1 and Gate 2 by name and function, but
never once uses the words "measurement quality," "geometric fidelity,"
or "functional coverage accuracy" — the exact vocabulary §I spent three
subsections establishing. The figure caption right after it (not shown
here, already reviewed separately) comes close to bridging the gap
mechanically, but likewise never uses the Introduction's layer names, so
even a reader who reads the caption carefully doesn't get the explicit
reconciliation.

## 4. Proposed fixes — each shown as the full revised paragraph

**Option A (recommended) — add the explicit mapping sentence to the
end of the §III opening paragraph:**

> This section presents the TWINGATE architecture, which couples
> empirical gap classification with physics-based ray tracing, as
> illustrated in Fig.~\ref{fig:architecture}. The figure displays the
> complete processing path from drive-test data to twin-gate coupling,
> expanded to show each pipeline's internal stages: gap detection and
> classification for Gate~1, scene construction and 4D optimization for
> Gate~2. Both pipelines run in parallel on the same RSRP logs, neither
> told what the other found until the final convergence check.
> Concretely, the three readiness layers introduced in
> Section~\ref{sec:intro} map onto this architecture as follows:
> Gate~1 alone produces the measurement-quality metric $C$; Gate~2
> alone produces the geometric-fidelity metric M1; and the
> functional-coverage-accuracy metric M2 is computed jointly, by
> evaluating Gate~2's calibrated predictions against the dead-zone
> locations Gate~1 identifies---already a first, narrower instance of
> the twin-gate cross-checking developed further in
> Section~\ref{sec:coupling}.

This costs one sentence (two, technically, but they read as one unit),
introduces no new numbers or claims, and uses only labels
(`sec:intro`, `sec:coupling`) that already exist in the document. It
also does real work beyond pure bridging: by pointing out that M2 is
already a joint metric, it sets up the twin-gate convergence result
(§IV-B) as a natural escalation of something the reader has already
seen once, rather than a new idea appearing out of nowhere.

**Option B — lighter touch: a forward-pointer in §I instead of a new
paragraph in §III.** Rather than adding text to §III, add a short
parenthetical to the end of Contributions bullet 1 pointing the reader
to where the mapping is made concrete:

> Development of a DT readiness framework: three quantitative
> metrics ($C$, M1, M2), drawn from two independent evidence
> sources, empirical recurrence and physics-based ray tracing,
> that jointly assess measurement quality, geometric fidelity, and
> functional coverage accuracy, each evaluated on a held-out
> temporal split (Section~\ref{sec:method} details how each metric
> maps onto Gate~1 and Gate~2).

Cheaper (one clause, no new paragraph), but weaker: it tells the reader
a mapping exists and where to look, rather than just stating it. A
reader who takes the pointer still has to do the same reconstruction
work Option A eliminates entirely.

**Option C — both.** Apply Option B's short pointer in §I (cheap,
sets expectation) and Option A's full sentence in §III (delivers on
it). Most complete; total cost is still just two sentences across the
whole paper.

**Option D — decline.** Leave both sections as-is. Defensible — this
is the lowest-severity item in the entire review (⚪ Polish, not 🟠) and
arguably the paper already contains everything needed to reconstruct
the mapping. Not recommended only because Option A is nearly free and
the M2-is-already-joint observation is a genuine, free insight worth
surfacing, not just plumbing.

## 5. What NOT to change

- Don't rename "layers" to "gates" or vice versa anywhere — the two
  vocabularies serve different purposes (layers = problem
  decomposition in the Introduction; gates = architectural components
  in the Method) and collapsing them into one term would lose that
  distinction, not clarify it.
- Don't move the Introduction's three `\subsection*` blocks — this
  finding is about adding a bridge, not restructuring the sections that
  need bridging.
- Don't touch the Figure~\ref{fig:architecture} caption — it already
  does its own job (describing what the figure shows) and doesn't need
  to duplicate the Introduction's layer vocabulary on top of that.

## 6. Resolution

**Applied: Option A.** `main.tex` §III's opening paragraph now ends
with the mapping sentence appended (nothing removed — the original
paragraph, including its figure reference, is unchanged):

> ...Both pipelines run in parallel on the same RSRP logs, neither told
> what the other found until the final convergence check. Concretely,
> the three readiness layers introduced in Section~\ref{sec:intro} map
> onto this architecture as follows: Gate~1 alone produces the
> measurement-quality metric $C$; Gate~2 alone produces the
> geometric-fidelity metric M1; and the functional-coverage-accuracy
> metric M2 is computed jointly, by evaluating Gate~2's calibrated
> predictions against the dead-zone locations Gate~1
> identifies---already a first, narrower instance of the twin-gate
> cross-checking developed further in Section~\ref{sec:coupling}.

Figure~\ref{fig:architecture} and its caption are completely untouched,
per §5's "what NOT to change." Verified: `main.tex` compiles cleanly
end-to-end (pdflatex+bibtex+2×pdflatex), zero errors, zero undefined
references. No numbers, tables, or other sections touched.
