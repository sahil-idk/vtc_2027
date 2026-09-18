# Review Finding M1 — The "Three Independent Metrics" Claim Is Not Supported by the Paper's Own Text

**Status:** ✅ fixed · **Severity:** Weakens-the-paper · **Section(s) affected:** §I (Contributions), §IV-C (Gate 2 Results / M2 discussion), abstract

**Resolution note:** the abstract already framed this correctly ("two
signals of coverage failure that come from completely independent
sources") — the mismatch was isolated to Contribution #1's wording and a
missing clarifying sentence in §IV-C. Applied Option A (§6 below) exactly
as written: Contribution #1 now attributes independence to the two
evidence sources rather than the three metrics, and §IV-C now states
explicitly why M1/M2 correlation is expected and that $C$ is the metric
with genuinely independent evidence. Option B (showing a case where M1
and M2 diverge) was not pursued — the "twin-gate" (two gates) framing
already justifies the two-source claim without needing new analysis.

---

## 1. The claim as written

`main.tex`, Contribution #1 (§I):

> "Development of a DT readiness framework: three quantitative metrics ($C$, M1, M2) that **independently** assess measurement quality, geometric fidelity, and functional coverage accuracy, each validated on a held-out temporal split."

This sentence is the paper's justification for proposing a *framework* rather than a single accuracy number: the pitch is that $C$, M1, and M2 are three separable checks, each capable of failing on its own, so a deployment passing all three is stronger evidence of readiness than passing any one.

## 2. Where the paper contradicts it

`main.tex`, §IV-C (Gate 2: RSRP Fidelity, discussing the M2 threshold):

> "The same geometric corrections that reduce M1 also improve M2 (unrefined, non-scattering geometry yields materially lower precision), confirming Gate 2's corrections improve functional coverage accuracy, not merely average signal-level error."

The paper presents this as a positive consistency check. Read as an independence claim, it says the opposite: M1 and M2 move together every time Gate 2's geometry or calibration changes. That is the definition of *not* independent.

## 3. Why this happens mechanically

M1 and M2 are both computed from a single object, the calibrated Sionna prediction defined in Eq. (3):

$$\hat{P}_i(\boldsymbol\theta) = b_i + \alpha_i \cdot P_\text{Sionna}(\boldsymbol\theta, \mathbf{r}_i)$$

- **M1** = mean $|\text{measured RSRP} - \hat P_i|$ over all validation rows (a continuous error metric).
- **M2** = threshold $\hat P_i$ at $-113$ dBm and score against Gate 1's TypeB labels (a binarized view of the *same* prediction surface).

M2 is a thresholded readout of the exact quantity M1 already scores continuously. A geometry refinement that makes $\hat P_i$ more accurate everywhere will, absent a contrived counter-example (getting better on average while specifically getting worse at the low-signal tail), also make the thresholded decision more accurate at any given subset of points — including the TypeB rows. Monotone joint improvement across pipeline stages (as Table I and §IV-C report) is the expected behavior of two readouts of one underlying quantity, not evidence of two separable capabilities.

## 4. What *is* actually independent

$C$ genuinely is independent of M1/M2: `G1_completeness.py` computes it purely from RSRP measurement-gap recurrence across vehicles and days, without touching Sionna, ray tracing, or tower geometry at any point.

So the paper's evidence supports a **two-way** split — Gate 1's $C$ (empirical, independent) vs. Gate 2's $\{$M1, M2$\}$ (physics-based, correlated with each other) — not the **three-way** independent split the abstract and Contribution #1 claim.

## 5. Why a reviewer will flag this

This is a standard objection to any paper proposing multiple evaluation metrics as a "framework": if two of the metrics always move together, a reviewer will ask either (a) to see a case where they diverge, proving the second metric adds information the first doesn't, or (b) for the independence claim to be dropped or narrowed. Right now §IV-C's own sentence hands the reviewer this objection pre-packaged — it explicitly states the correlation as if it were a virtue.

## 6. Fix options

**Option A — text-only, cheapest.** Reframe the independence claim to the *evidence sources* rather than the three metrics:

> "...three quantitative metrics ($C$, M1, M2), drawn from two independent evidence sources — empirical recurrence and physics-based ray tracing — that assess measurement quality, geometric fidelity, and functional coverage accuracy..."

And add one clarifying sentence after the §IV-C correlation statement:

> "This correlation is expected: M1 and M2 both derive from the same refined geometry and calibrated prediction surface, whereas $C$ alone is evaluated from a source Gate 2 never sees."

**Option B — stronger, requires new analysis.** Find and report a case where M1 and M2 diverge — e.g., a tower or region with good average MAE but poor dead-zone classification, or vice versa. This would be genuine evidence that M2 earns its place as a distinct readiness axis rather than a restatement of M1, and would let the paper keep the three-way independence claim honestly. Not a text-only fix; requires pulling per-tower M1/M2 breakdowns that don't currently exist in the repo's output files.

## 7. Recommendation

Ship Option A now (zero new experiments, removes the internal contradiction). Treat Option B as a possible strengthening item if there's appetite for one more analysis pass before submission — it would meaningfully upgrade the framework's core pitch from "three metrics" to "three metrics, two of which we've shown can disagree."
