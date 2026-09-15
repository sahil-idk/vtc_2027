# A15 TX Position Refinement — Temporal Split Results

## Split Type

**Temporal Split** — strict day-based hold-out

| Split | Dates | Description |
|-------|-------|-------------|
| Train | June 22–23, 2021 (Days 1–2) | Used for WCL init, NM optimization, OLS fitting |
| Val   | June 24, 2021 (Day 3)       | Evaluated exactly once after all params finalized |

This matches the paper's explicit claim (Section II-B):
> *"Days 1–2 (22–23 June) serve as training data; day 3 (24 June) is held out strictly for validation."*

And is consistent with Gate-1: the completeness score C = 0.80 is evaluated on June 24 data only.

### Row Counts by Device (pc1, Operator 1)

| Device | Split | Row Count | Dates |
|--------|-------|-----------|-------|
| pc1 | train | 39,132 | June 22–23 only |
| pc1 | val   | 15,616 | June 24 only |

**Total towers (with ≥5 train and val rows):** 126

Note: train count is lower than the stratified split (39,132 vs 42,971) because June 24
training rows are excluded. Val count is higher (15,616 vs 10,703) because all June 24
rows are in val rather than 20% of all-days rows.

### Scene Mapping

| Device | Operator | Scene | Origin |
|--------|----------|-------|--------|
| pc1 | Op1 (Deutsche Telekom) | scene_operator1 | 52.507005°N, 13.323428°E |
| pc4 | Op1 (Deutsche Telekom) | scene_operator1 | 52.507005°N, 13.323428°E |
| pc2 | Op2 (Vodafone) | scene_operator2 | 52.506112°N, 13.321908°E |
| pc3 | Op2 (Vodafone) | scene_operator2 | 52.506112°N, 13.321908°E |

---

## Method: A15 TX Position Refinement (same as stratified run)

- WCL initialization from June 22–23 training GPS points (RSRP-power weighted centroid)
- Nelder-Mead searches (Δx, Δy) within 500m radius, 60 max iterations
- Full mode: all training rows used in every NM evaluation (no subsampling)
- OLS calibration: RSRP = b + α·sionna\_power, α ∈ [0, 2], fitted on train rows only
- Val evaluated once after NM convergence, using all June 24 rows

**Checkpoint file:** `twingate/out/pc1_refinement_results_temporal.csv`

---

## Results — pc1 (Operator 1, Temporal Split)

> Results pending — run launched 2026-09-07, PID 17188
> Log: `twingate/out/a15_pc1_temporal.log`

| Metric | Value |
|--------|-------|
| Towers completed | — / 126 |
| WCL val MAE (Jun 24, weighted) | — dB |
| Refined val MAE (Jun 24, weighted) | — dB |
| Gain | — dB |
| Towers improved | — |
| Towers worsened | — |
| Mean TX correction | — m |
| Median TX correction | — m |

---

## Comparison: Stratified vs Temporal Split (pc1)

| | Stratified 80/20 | Temporal (Day 3) |
|--|-----------------|-----------------|
| Train rows | 42,971 (all 3 days) | 39,132 (days 1–2 only) |
| Val rows | 10,703 (all 3 days, 20%) | 15,616 (day 3 only, 100%) |
| Towers | 102 | 126 |
| WCL val MAE | 3.784 dB | TBD |
| Refined val MAE | 2.626 dB | TBD |
| Gain | +1.158 dB | TBD |
| Improved / Worsened | 84 / 14 | TBD |
| Matches paper claim? | No | **Yes** |
| Gate-1 consistency? | No (different val data) | **Yes (same Jun 24 val)** |

---

## Why This Split Matters

The temporal split is stricter in one key way: the model must generalize across **days**,
not just across measurement points within the same days. Between-day variation includes:

- Different traffic density (different vehicle positions, different blocker configurations)
- Day-to-day shadow fading variation (measured ~3 dB std in urban LTE at 1.8 GHz)
- Potential network changes (cell reconfigurations, load-balancing between days)

If the temporal val MAE is close to the stratified val MAE, it confirms the DT's
spatial generalization is robust to between-day channel variation — a stronger claim
than the stratified result alone.

This document will be updated with final results when the run completes.
