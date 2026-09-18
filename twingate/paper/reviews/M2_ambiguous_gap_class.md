# Review Finding M2 — The "Ambiguous" Gap Class Was Undefined in Methods, and Mischaracterized in Results

**Status:** ✅ fixed · **Severity:** Reviewer-would-reject-on-this · **Section(s) affected:** §III-A (Gap Classification), §IV-A (Gate 1 Results)

Note: this is unrelated to the paper's own **M2** metric (dead-zone detection
F1 = 0.77, Table II). This is review finding "M2" from `TODO.md`'s
methodology list — the naming collision is coincidental.

---

## 1. The gap

§III-A ("TypeA vs. TypeB Classification") defined exactly two classes:

> "**TypeA (protocol gap):** A gap is TypeA if it spans a measurement session boundary... **TypeB (coverage hole):** A gap is TypeB if it is not TypeA and at least one other distinct vehicle logs a gap centroid within 100 m of it..."

That reads as an exhaustive two-way split. §IV-A then reported a third class with a real count and no prior definition:

> "...4 TypeA gaps..., 57 TypeB gaps..., and 13 ambiguous gaps whose session context is inconclusive."

## 2. A second, sharper problem found while checking the code

Cross-checking against `twingate/G1_completeness.py`:

```python
df["gap_type"] = "Ambiguous"                 # default
df.loc[df["type_a"], "gap_type"] = "TypeA"   # session-boundary gaps
df.loc[df["type_b"], "gap_type"] = "TypeB"   # session-boundary-free + corroborated gaps
```

"Ambiguous" = not a session-boundary gap, **and** not corroborated by another
vehicle. The old §IV-A phrase — "whose session context is inconclusive" —
is not just vague, it's inaccurate: an Ambiguous gap's session-boundary
status is never in doubt (it has already definitively failed that test,
which is *how* it avoided being TypeA). What's actually unresolved is
cross-vehicle corroboration, which has nothing to do with session context.

## 3. Phrasing issue, not a methodology issue

Same category as finding M1: the classifier itself (`G1_completeness.py`)
is internally consistent and does something reasonable — a genuine third
bucket for "neither confirmed protocol noise nor confirmed coverage hole."
Nothing needed to be recomputed and no numbers changed. The problem was
purely in the write-up: (a) the bucket was never defined in Methods, and
(b) the one place Results did describe it, the description named the
wrong criterion.

## 4. Applied fix

**§III-A**, added after the TypeB definition:

> "Ambiguous: A gap that is neither TypeA (not session-boundary-aligned) nor TypeB (not corroborated by another vehicle within $d_\text{recur}$) is labeled Ambiguous: insufficient evidence to classify it as either a protocol interruption or a coverage hole. Ambiguous gaps are reported but never used to certify or reject a dead zone."

**§IV-A**, corrected the mischaracterization:

> Before: "...13 ambiguous gaps whose session context is inconclusive."
> After: "...13 ambiguous gaps lacking cross-vehicle corroboration."

No numbers, tables, or other sections touched.
