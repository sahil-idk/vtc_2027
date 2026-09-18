# Review Finding M7 — No Deployment Ever Fully "Passes," and the Table Doesn't Agree With Its Own Prose

**Status:** open — problem documented, fix options proposed below, **not yet applied** to `main.tex` · **Severity:** Weakens-the-paper · **Section(s) affected:** Table I (`tab:gate2`), the "M1 acceptance threshold" paragraph (§IV-C), and the Conclusion (§VI)

---

## 1. The plain-English version

Imagine a report card that shows a flat "F" in a column, with a comment
written directly underneath it saying "this is basically an A-, don't
worry about it." Both things can be defensible on their own — maybe the
grading cutoff really was arbitrary and the student really did just miss
it by a hair — but showing the reader a hard "F" and then immediately
arguing it doesn't really count is confusing at best, and looks like
trying to have it both ways at worst.

That's what's happening between Table I and the paragraph right after it.
And there's a second, bigger problem sitting underneath this one: **no
deployment in this paper ever satisfies all three readiness criteria at
once.** Operator 1 fails $C$ (it's $0.00$). Both operators fail M1 (the
table's own M1<3dB column reads "No" in every single row, for every
stage, for both operators). The paper never shows a reader what a
genuinely "ready" deployment would look like under its own framework —
only near-misses and one outright miss.

## 2. The exact text

Table I (`tab:gate2`), every row of the "M1 < 3dB?" column:

> Stage 0: No | Stage 1: No | Stage 2: No | Stage 3: No | **Stage 4: No**
> (for **both** Op.1 and Op.2, at every stage)

Immediately after the table, the "M1 acceptance threshold" paragraph
(§IV-C):

> "The achieved M1 of 3.02 dB falls below the 6 dB instrument bound and
> within 0.02 dB of the 3 dB fading floor, consistent with irreducible
> measurement variability rather than DT inaccuracy: Gate 2 approaches,
> but does not yet cross, the M1 < 3 dB criterion for Operator 1."

And the Conclusion (already touched by the M6 fix, unrelated part of the
same sentence untouched):

> "...geometric fidelity close to but not yet crossing its threshold for
> either operator (M1 = 3.02/4.04 dB)."

## 3. Three separate problems, not one

**(a) The table is binary; the prose isn't, and they're placed right next
to each other.** The table shows an unqualified "No" — no asterisk, no
footnote, nothing distinguishing Stage 4's 3.02 dB from Stage 0's
4.40 dB. The very next paragraph then argues 3.02 dB is "consistent with
irreducible measurement variability rather than DT inaccuracy" — i.e.,
argues it shouldn't really be read as a failure. A reader has to hold two
contradictory impressions at once: the table says clean miss, the prose
says basically-a-pass.

**(b) The forgiving argument is only made for Operator 1, but the
Conclusion applies matching soft language to both operators anyway.**
Op.1's Stage 4 MAE is 3.02 dB — 0.02 dB over the line, and the paper
makes a real, specific case for why that's noise. Op.2's Stage 4 MAE is
4.04 dB — **1.04 dB over the line**, a full order of magnitude further
off, with no comparable argument made anywhere for why *that* miss is
also "just noise." Yet the Conclusion's phrase "close to but not yet
crossing its threshold for **either** operator" treats the two misses as
symmetric near-misses. They aren't: one is a rounding error, the other
is a real, unexplained gap. Grouping them under one soft phrase overstates
how close Operator 2 actually is.

**(c) A smaller, related precision issue: calling 3 dB "the fading
floor."** The M1 < 3 dB threshold was originally chosen (§III-C-6, Gate 2
Evaluation Protocol) as roughly half of 3GPP TS 36.133's ±6 dB RSRP
measurement accuracy bound — a self-imposed, conservative criterion, not
itself a number taken from a shadow-fading study. TR 38.901's actual
shadow-fading standard deviation for the UMa scenario is cited elsewhere
in the same paragraph as **4–6 dB**, not 3 dB. Calling the self-chosen
3 dB threshold "the 3 dB fading floor" borrows the credibility of a
different, standards-cited number (4–6 dB) for a number the paper itself
picked. This is a minor wording precision issue on its own, but it
compounds problem (a): it makes the "3.02 is basically fine" argument
sound more externally-grounded than it actually is.

**(d) The meta-point: the paper never shows what "ready" looks like.**
Stepping back from the table entirely — under this paper's own framework
($C$, M1, M2), no single deployment here ever satisfies all three at
once. Operator 1: $C=0.00$ (fails outright, by the paper's own account,
due to thin evidence rather than a wrong pipeline). Operator 2: $C=0.80$
(passes) and M2 F1$=0.77$ (passes), but M1$=4.04$ dB (fails, and not by a
rounding error per point (b) above). A reader finishes the paper having
seen the framework applied twice and never once seen it return a clean
"yes" on all three axes. That's not necessarily a flaw in the framework —
but the paper never says this plainly, which leaves the reader to notice
it themselves and wonder whether "readiness" as defined here is
achievable at all, or whether the bar was set somewhere no real deployment
can actually clear.

## 4. Why a reviewer would flag this

A reviewer evaluating a proposed acceptance criterion always asks two
things: (1) is the criterion applied consistently, and (2) has the paper
ever shown a case that meets it? Right now the answer to (1) is "no" —
the forgiving argument is applied to one number (3.02) and not the
symmetric-sounding other one (4.04) — and the answer to (2) is also "no."
Papers that propose a threshold framework are expected to either show at
least one clean pass, or explicitly own that they haven't yet and say why
that's still a meaningful contribution. This paper does neither
explicitly; a reader has to piece it together from a table and some
scattered sentences.

## 5. Fix options (not applied — for review)

**Option A — add an explicit uncertainty band to the M1 threshold.**
Redefine the criterion up front (where M1 < 3 dB is first introduced,
§III-C-6) as something like "M1 $\leq$ 3 dB, treated as met within
measurement-noise precision (±0.1 dB)," and update Table I's column
accordingly — Stage 4 Op.1 (3.02 dB) would then read "Yes (within noise)"
while Op.2 (4.04 dB) stays an honest "No," since 4.04 dB doesn't qualify
under any small band. This makes the table and prose agree, and makes the
asymmetry between the two operators visible and correct instead of
implied and blurred. Risk: an uncertainty band invented after seeing the
result can look like moving the goalposts to a skeptical reviewer, even
if the underlying argument (noise floor) is sound — worth being explicit
in the text that the band was chosen from the measurement-accuracy
literature, not fit to the result.

**Option B — keep the hard threshold, own the outcome explicitly instead.**
Leave Table I's binary "No" column exactly as-is (arguably more honest
than adding a band after the fact), and instead:
1. Fix the Conclusion's "close to but not yet crossing its threshold for
   either operator" phrasing to stop treating the two misses as
   symmetric — e.g., "...geometric fidelity within measurement noise of
   its threshold for Operator 1 (M1 = 3.02 dB) but not yet for Operator 2
   (M1 = 4.04 dB)..." — one honest sentence, no table change.
2. Add an explicit sentence (Discussion or Conclusion) owning the meta-point:
   something like "no single deployment studied here satisfies all three
   readiness criteria simultaneously; producing one is the direct target
   of future work, and this paper's contribution is the framework and its
   cross-validation test, not yet a positive 'ready' verdict."
3. Optionally soften "the 3 dB fading floor" wording (problem (c)) to
   something like "within 0.02 dB of our self-imposed 3 dB threshold,"
   removing the implied borrowed authority from the 4–6 dB shadow-fading
   figure.

**Recommendation between the two:** Option B is more defensible under
scrutiny — it doesn't require inventing a band that a reviewer could
challenge as post-hoc, and "own the miss, explain why it's still a
contribution" is generally a stronger position than "redefine the bar so
it's not a miss." Option A is worth considering only if there's a
principled, literature-backed uncertainty figure to cite for the ±0.1 dB
(or similar) band, decided *before* looking at which result it would flip.

## 6. What's NOT proposed

Not proposing to touch the M2 table, the twin-gate convergence numbers, or
any of the underlying MAE figures — this finding is entirely about how
the existing M1 numbers are framed in prose and in the table's verdict
column, not about the numbers themselves.

**Not yet applied.** This document is the problem statement and fix
options only, for review before any edit to `main.tex`.
