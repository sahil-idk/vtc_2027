# Review Finding C4 — Beyraghi/Rauf Citations Set Up a Contrast in the Intro That's Never Paid Off in Discussion

**Status:** documented, not yet applied — revised after author flagged
numeric-comparison risk, see §5b · **Severity:** 🟠 Weakens-the-paper ·
**Section(s) affected:** §I "Geometric fidelity" subsection (where the
setup currently lives), §V-A "Why TWINGATE Is Physics, Not
Curve-Fitting" (where the payoff should, but currently doesn't, land)

---

## 1. The plain-English version

When a paper sets up a comparison — "here's what prior work achieved,
and here's the harder version of the problem we're solving instead" —
a reader expects that comparison to come back later, once the paper's
own numbers are on the table, so they can actually judge the tradeoff
being claimed. Right now, TWINGATE's Introduction does exactly this
setup with a specific, well-chosen prior result (Beyraghi et al.'s
city-scale calibration), and then never comes back to it. The
comparison is raised, a reason is given for why it doesn't directly
apply, and then the thread is simply dropped — the reader is left to
notice on their own, dozens of pages later, that TWINGATE's own
accuracy numbers are meaningfully different from the number they were
shown, without ever being told exactly what that difference means.

## 2. The setup (currently in §I, "Geometric fidelity")

```
Rauf et al.~\cite{rauf2026kpi} similarly identify material mismatch and
near-field effects as primary Sionna~RT error sources, and city-scale
calibration~\cite{beyraghi2025ris} reduces RSRP error from 5.69 to
0.32\,dB through material optimization alone, but that result assumes
known tower positions, a luxury public V2X datasets do not have.
Recovering accurate tower geometry from RSRP alone is therefore a
prerequisite, not an optional refinement.
```

This is good writing — it names a specific, strong prior number
(0.32dB), explains precisely why TWINGATE can't just replicate that
result (no known tower positions), and uses that gap to motivate the
paper's own contribution (geometry recovery as "a prerequisite, not an
optional refinement"). It sets up a clear expectation: *TWINGATE's own
residual error, once reported, should be read against this number and
this explanation.*

## 3. Where the payoff should be, and currently isn't (§V-A)

§V-A ("Why TWINGATE Is Physics, Not Curve-Fitting") is the section that
directly discusses the paper's own residual accuracy and what it means
— the natural place for the promised comparison to land. It currently
ends with:

```
This falsifiability (each gate evaluated on data it never fit) is what
distinguishes TWINGATE from prior V2X DT studies on this same dataset
that report accuracy without a comparably strict held-out
discipline~\cite{teh2023dt,partani2025qos}.
```

This sentence makes a *different* comparison (methodological rigor vs.
`teh2023dt`/`partani2025qos`, same dataset) — a good point, but not the
one the Introduction set up. Beyraghi and Rauf are never mentioned again
anywhere in the paper (confirmed: `\cite{beyraghi2025ris}` and
`\cite{rauf2026kpi}` each appear exactly once, both in §I). The reader
who remembered the Introduction's setup, and who now has TWINGATE's own
numbers in front of them (M1 = 3.02dB Op.1 / 4.04dB Op.2, an order of
magnitude larger than Beyraghi's 0.32dB), gets no help interpreting
that gap. A skeptical reviewer fills that silence themselves, and not
necessarily charitably — "your own number is 10x worse than the number
you cited" reads very differently depending on whether the paper
explains why, or leaves it for the reviewer to wonder about.

## 4. Why this matters

The explanation actually *exists* and is favorable to the paper — it's
already implicit in the Introduction's own wording ("that result assumes
known tower positions, a luxury public V2X datasets do not have").
TWINGATE's higher residual error is not a weaker calibration; it's the
cost of solving a strictly harder problem (joint geometry + material
recovery from RSRP alone, vs. material-only calibration against known,
surveyed positions). This is a genuinely strong point for the paper to
make explicitly — it reframes an apparently unfavorable number
comparison (3-4dB vs. 0.32dB) into evidence of the harder, more
realistic problem setting TWINGATE tackles. Leaving it unsaid wastes a
point that's already been half-made and gives up the framing to whoever
reads the numbers next.

## 5. Proposed fix (drafted, not yet applied)

Add one sentence to the end of §V-A, after the existing falsifiability
sentence, explicitly closing the loop the Introduction opened:

> This distinction between known and unknown tower geometry also
> explains why TWINGATE's residual error (3.02/4.04\,dB) is an order of
> magnitude larger than Beyraghi~et~al.'s~\cite{beyraghi2025ris}
> 0.32\,dB: that result calibrates material properties against known,
> surveyed transmitter positions, whereas TWINGATE must recover geometry
> and materials jointly from RSRP alone, a strictly harder inverse
> problem whose larger residual reflects the problem's difficulty, not a
> weaker calibration.

This costs one sentence, introduces no new numbers (both 3.02/4.04dB
and 0.32dB are already stated elsewhere in the paper — Table I and §I
respectively), and directly closes the setup/payoff loop using the
paper's own already-established reasoning.

## 5b. Author concern: does stating the numbers side by side put us at a disadvantage?

Raised after the first draft above: even though the *reasoning* favors
TWINGATE (harder problem, known-vs-unknown geometry), spelling out
"3.02/4.04dB is an order of magnitude larger than 0.32dB" in plain text
hands a reviewer a ready-made soundbite — "the authors' own paper says
their number is 10x worse" — that can be quoted out of the explanation
that justifies it. This is a fair concern independent of whether the
underlying logic is sound: a number comparison, once stated, can be
lifted out of context in a way a qualitative statement cannot. Three
lower-risk ways to close the same setup/payoff gap, without creating
that soundbite:

**Option E — pay off the citation without restating TWINGATE's own
number.** Keep the sentence in §V-A, but drop the explicit "order of
magnitude" / side-by-side figures and state only the qualitative
relationship:

> Because TWINGATE recovers tower geometry from RSRP alone rather than
> starting from known, surveyed positions as
> Beyraghi~et~al.~\cite{beyraghi2025ris} do, its residual error reflects
> the added burden of joint geometry-and-material inference, not a
> weaker material calibration.

This closes the loop (Beyraghi is referenced again, the "why" is given)
without ever placing TWINGATE's number next to theirs in the same
sentence. A reader who wants to compute the ratio still can (both
numbers are elsewhere in the paper — Table I and §I), but the paper
itself never hands a reviewer the "10x" framing pre-packaged.

**Option F — remove the specific numbers from the Introduction's
citation, so nothing needs a numeric payoff at all.** The actual
argument the Introduction needs is qualitative: material calibration
works well *when geometry is known*, and TWINGATE can't assume that.
The specific "5.69 to 0.32dB" figures aren't load-bearing for that
argument — they're what create the implicit high-water mark a reader
later measures TWINGATE against. Reword §I to:

> ...and city-scale calibration~\cite{beyraghi2025ris} shows material
> optimization alone can substantially reduce RSRP error when tower
> positions are known, but that result assumes known tower positions, a
> luxury public V2X datasets do not have.

With no number quoted in the setup, there is no specific figure for
§V-A to be measured against, and no explicit sentence is needed there
at all — the citation still does its job (motivating why geometry
recovery, not just material calibration, is TWINGATE's prerequisite)
without ever inviting a head-to-head comparison anywhere in the paper.
This is the option that most directly matches "use it without taking
the numbers."

**Option G — drop the Beyraghi citation from this contrast entirely.**
Keep Rauf~et~al.~\cite{rauf2026kpi} alone to motivate the "material
mismatch is a primary error source" point (it makes that point without
citing a specific competing accuracy figure at all), and cut
`\cite{beyraghi2025ris}` from §I. This fully removes the setup, so there
is nothing left to pay off, and removes this finding (C4) from the
review entirely rather than fixing it. Costs the paper a specific,
concrete, currently-well-written motivating detail (the 5.69→0.32dB
number is genuinely a strong, real result that supports "material
calibration matters"); the framework's `known-positions` motivation
still stands on Rauf's qualitative point alone, just less vividly.

**Recommendation given the concern:** Option F is the best fit — it
directly addresses "can we use the citation without taking the numbers"
by removing the number from where it's first introduced, rather than
trying to neutralize a comparison after committing to state it. It
keeps the citation and the intended motivating logic, produces no
quotable "our number is worse" sentence anywhere in the paper, and
needs no compensating sentence in §V-A (though Option E's softer
qualitative sentence could still be added there too, for extra
closure, if desired — the two are not mutually exclusive).

## 6. What NOT to change

- If applying Option A or E (payoff in §V-A), don't touch the
  Introduction's setup sentence — it's already well written and doesn't
  need to name the exact payoff location. (Option F changes the
  Introduction sentence itself, by design — see §5b.)
- Don't try to make the comparison sound better than it is (e.g.,
  don't imply the numbers are "close" or "comparable" — they aren't,
  and the paper's own point is *why* they shouldn't be expected to be).
- Don't fold this into the existing `teh2023dt`/`partani2025qos`
  sentence — that's a different comparison (methodological rigor on the
  same dataset) and merging the two would blur two distinct, both-valid
  points into one confusing one.

## 7. Options

- **A — apply as drafted.** One sentence at the end of §V-A, closing the
  loop with the exact reasoning the Introduction already implies.
- **B — apply, but move earlier in §V-A** (e.g., right after the "1.81dB
  from removing Sionna" sentence, since both are about interpreting the
  magnitude of TWINGATE's residual error) rather than tacked on at the
  very end after the falsifiability point, which is a separate argument.
- **C — shorter version**, cutting the explicit "order of magnitude"
  framing if it's judged to overstate the comparison's importance —
  e.g., "TWINGATE's higher residual error (3.02/4.04\,dB) versus
  Beyraghi~et~al.'s~\cite{beyraghi2025ris} 0.32\,dB reflects a strictly
  harder inverse problem: recovering geometry from RSRP alone, not
  calibrating materials against known positions."
- **D — decline.** Leaves the setup/payoff gap and the numeric-figure
  risk both unresolved; not recommended now that lower-risk options
  exist.
- **E — payoff without restating TWINGATE's number** (§5b). Keeps both
  citation and a §V-A callback sentence, but never places TWINGATE's
  figure next to Beyraghi's in the same sentence, so there's no
  ready-made "our number is worse" quote.
- **F — remove the numbers from the Introduction's citation itself**
  (§5b). Recommended. Directly answers "can we use the citation without
  taking the numbers" — keeps `\cite{beyraghi2025ris}` and its
  motivating logic, drops "5.69 to 0.32dB" from §I, and needs no
  compensating sentence in §V-A at all (E's qualitative sentence is an
  optional addition on top, not required).
- **G — drop the citation from this contrast entirely** (§5b). Removes
  the setup (and this finding) altogether by cutting
  `\cite{beyraghi2025ris}` from §I and relying on Rauf's qualitative
  point alone; costs the paper a concrete, currently well-written
  motivating detail.

**Not applied.** No changes to `main.tex` — this document only lays out
the finding, the original drafted fix, the numeric-comparison concern
raised after drafting it, and lower-risk alternatives, for review.
