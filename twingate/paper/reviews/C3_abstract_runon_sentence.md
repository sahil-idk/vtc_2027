# Review Finding C3 — Abstract's Final Sentence Is One ~70-Word Run-On Stacking Four Results

**Status:** documented, not yet applied · **Severity:** ⚪ Polish ·
**Section(s) affected:** Abstract (final sentence)

---

## 1. The plain-English version

The Abstract's last sentence tries to do five things at once: report
four separate numeric results ($C=0.80$; RSRP error 3.02/4.04dB; F1
$=0.77$; 86.5% recovery) and then land a one-clause takeaway about what
it all means, all inside a single ~70-word sentence with no full stop.
Every clause in it is individually clear, but stacked together the
sentence asks a reader to hold four unrelated numbers in short-term
memory before finally getting the payoff ("showing that DT readiness
can be established..."). This is exactly the kind of sentence an
abstract shouldn't end on — abstracts are often read fastest and least
carefully of any part of the paper, and the very last sentence is what
a skimming reader is most likely to actually retain. A run-on here
costs the paper its strongest possible closing note.

## 2. The paragraph today, in full (Abstract, final sentence)

```
Applied to a real two-operator LTE drive-test corpus from Berlin,
TWINGATE reaches a dead-zone completeness of $C=0.80$, reduces RSRP
error to 3.02\,dB and 4.04\,dB across the two operators (well within
the 3GPP~TS~36.133 accuracy bound), independently flags the same dead
zone with F1\,$=$\,0.77, and recovers 86.5\,\% of a measured 30.4\,dB
coverage collapse purely from ray-traced geometry, showing that DT
readiness can be established directly from drive-test data, with no
ground-truth infrastructure needed.
```

This is one sentence, roughly 73 words, built from five coordinated
clauses ("reaches...", "reduces...", "flags...", "recovers...",
"showing...") chained with commas and a final "and." Structurally nothing
is wrong with it — every clause is grammatical and every number is
accurate — but a sentence this long, ending an abstract, is a readability
problem independent of content.

## 3. Proposed fixes — each shown as the full revised passage

**Option A — split off the closing "takeaway" clause as its own
sentence** (closest to the original finding's literal suggestion: stop
stacking, give the payoff its own sentence):

> Applied to a real two-operator LTE drive-test corpus from Berlin,
> TWINGATE reaches a dead-zone completeness of $C=0.80$, reduces RSRP
> error to 3.02\,dB and 4.04\,dB across the two operators (well within
> the 3GPP~TS~36.133 accuracy bound), independently flags the same dead
> zone with F1\,$=$\,0.77, and recovers 86.5\,\% of a measured
> 30.4\,dB coverage collapse purely from ray-traced geometry. These
> results show that DT readiness can be established directly from
> drive-test data, with no ground-truth infrastructure needed.

Two sentences (~57 words, ~19 words). Minimal rewording — only the comma
before "showing" becomes a period, and "showing" becomes "These results
show." Keeps all four results together as one parallel list (which
reads acceptably even at length, since the four clauses are genuinely
parallel and coordinate — "reaches X, reduces Y, flags Z, and recovers
W"), and gives the takeaway sentence room to land on its own. The
imbalance (57 vs. 19 words) is intentional: the short second sentence
reads as a deliberate, punchy close rather than an afterthought.

**Option B (recommended) — split the four results into two natural
pairs, keeping the takeaway attached to the second pair:**

> Applied to a real two-operator LTE drive-test corpus from Berlin,
> TWINGATE reaches a dead-zone completeness of $C=0.80$ and reduces
> RSRP error to 3.02\,dB and 4.04\,dB across the two operators (well
> within the 3GPP~TS~36.133 accuracy bound). It also independently
> flags the same dead zone with F1\,$=$\,0.77 and recovers 86.5\,\% of
> a measured 30.4\,dB coverage collapse purely from ray-traced
> geometry, showing that DT readiness can be established directly from
> drive-test data, with no ground-truth infrastructure needed.

Two more evenly balanced sentences (~38 words, ~40 words). The split
point isn't arbitrary: the first sentence groups the two single-gate
results ($C$ from Gate~1 alone, M1/RSRP-error from Gate~2 alone, per
the C1 fix's own mapping), and the second groups the two joint/
cross-gate results (F1 detection and the 86.5% blind-recovery figure,
both tied to the twin-gate convergence story) — so the grouping tracks
a real structural distinction in the paper, not just a word-count
target, and keeps the "showing that..." payoff attached to the
sentence about the paper's strongest (joint) evidence, echoing the
thesis statement now stated up front per the already-applied C7 fix.

**Option C — decline.** Leave the sentence as one run-on. Not
recommended: this is a zero-numbers, zero-risk readability fix, and
the Abstract's last sentence is disproportionately high-traffic real
estate to leave in its current form.

## 4. What NOT to change

- Don't alter any of the four numbers or their qualifiers (e.g., "well
  within the 3GPP~TS~36.133 accuracy bound," already fixed under M7) —
  this finding is purely about sentence boundaries, not content.
- Don't touch the rest of the Abstract — the earlier sentences
  (framing, the two-signal cross-check description, the twin-gate
  coupling explanation) aren't run-ons and aren't in scope for C3.

**Not applied.** No changes to `main.tex` — this document only lays out
the finding and drafted fix text (Options A and B, full passages) for
review.
