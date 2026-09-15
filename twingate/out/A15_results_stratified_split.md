# A15 TX Position Refinement — Stratified 80/20 Split Results

## Split Type

**Random Stratified 80/20 Split** (within device × cell_id groups)

The dataset is partitioned by randomly assigning 80% of each tower's measurements to `train`
and 20% to `val`, stratified so that every (device, cell\_id) pair has representation in both sets.
This is **not a temporal split** — train and val rows are drawn from the same calendar days.

### Date Coverage Per Device

| Device | Split | Row Count | Dates Covered |
|--------|-------|-----------|---------------|
| pc1 | train | 42,971 | June 22, 23, 24 |
| pc1 | val   | 10,703 | June 22, 23, 24 |
| pc2 | train | 33,692 | June 22, 23, 24 |
| pc2 | val   |  8,499 | June 22, 23, 24 |
| pc3 | train | 43,439 | June 22, 23, 24 |
| pc3 | val   | 10,843 | June 22, 23, 24 |
| pc4 | train | 33,692 | June 22, 23, 24 |
| pc4 | val   |  8,397 | June 22, 23, 24 |
| **Total** | train | **153,794** | all 3 days |
| **Total** | val   |  **38,442** | all 3 days |

**Split file:** `twingate/out/stratified_split_index.csv`

### Key Property

Train and val rows **overlap in time** — measurements from the same days appear in both sets.
Shadow fading conditions on a given day are spatially and temporally correlated, meaning
adjacent measurements (in time) in train and val will have correlated channel conditions.
This makes the validation slightly optimistic compared to a true temporal hold-out.

---

## Method: A15 TX Position Refinement

Each tower's TX position is initialized via Weighted Centroid Localization (WCL):
RSRP-power-weighted mean of all training GPS positions for that cell.

The Nelder-Mead optimizer then searches (Δx, Δy) in metres from the WCL position,
running Sionna RT at each candidate TX location. At each evaluation:
- All training rows for that tower are passed to Sionna as receiver locations (full mode)
- OLS calibration (RSRP = b + α·sionna\_power, α ∈ [0, 2]) is fitted on training rows
- Training MAE is the objective function (val rows never seen during optimization)

After convergence, the refined TX position is used to evaluate val MAE on **all val rows**.

**Mode used:** `--full` (all training rows in every NM iteration, no subsampling)

**Scene mapping:**
- pc1, pc4 → `scene_operator1` (origin 52.507005°N, 13.323428°E) — Deutsche Telekom
- pc2, pc3 → `scene_operator2` (origin 52.506112°N, 13.321908°E) — Vodafone

**NM parameters:** search radius 500m, maxiter 60, xatol 10m, fatol 0.02 dB

---

## Results by Device

| Device | Operator | Towers Done | WCL Val MAE | Refined Val MAE | Gain | Improved | Worsened | Δ Mean | Δ Median | Δ Max |
|--------|----------|-------------|-------------|-----------------|------|----------|----------|--------|----------|-------|
| pc1 | Op1 (Telekom) | 102 / 102 ✓ | 3.784 dB | **2.626 dB** | +1.158 dB | 84 | 14 | 64m | 43m | 414m |
| pc2 | Op2 (Vodafone) | 105 / 105 ✓ | 4.123 dB | **2.904 dB** | +1.218 dB | 92 | 9  | 71m | 50m | 412m |
| pc3 | Op2 (Vodafone) | 55 / 115 ⚠ | 3.806 dB | **2.903 dB** | +0.903 dB | 49 | 4  | 76m | 58m | 374m |
| pc4 | Op1 (Telekom) | — | — | — | — | — | — | — | — | — |

> ⚠ pc3 run was stopped early (55/115 towers). pc4 was not run.
> These runs were halted when the split-type mismatch with the paper was identified.

### Weighted Aggregate (pc1 + pc2 + pc3 partial)

Weighted by n\_val across completed towers:

| | Val MAE |
|--|---------|
| WCL baseline (weighted) | ~3.90 dB |
| Refined (weighted) | ~2.74 dB |
| Gain | ~+1.16 dB |

---

## Limitation of This Split for the Paper

The paper (Section II-B) states:
> *"Days 1–2 (22–23 June) serve as training data; day 3 (24 June) is held out strictly for validation."*

The stratified split **does not match this claim**: val rows span all three days, and the
train set includes June 24 measurements. This creates two issues:

1. **Temporal leakage** — shadow fading and channel conditions are correlated within a day,
   so train/val rows from the same day are not fully independent.
2. **Consistency with Gate-1** — Gate-1's completeness score (C = 0.80) is evaluated on
   Day 3 (June 24) only. Using a different val set for Gate-2 means the two gates are
   validated on different data, weakening the twin-gate convergence argument.

A temporal split (Day 3 held out) addresses both issues and is the subject of the
companion document `A15_results_temporal_split.md`.
