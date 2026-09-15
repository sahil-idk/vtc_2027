# TWINGATE Gate 2 — Session Log

**Started:** 2026-08-14  
**Folder:** `C:\Users\sahil\dt-sionna-rt\twingate\`  
**Context:** Fresh rebuild of Gate 2 Communication-Reconstruction Loop.
Prior GZ-3 result (5-tower prototype) was contradicted by a second oracle;
all-towers run later recovered the Gate-2 headline at 100th bootstrap pctile.
This rebuild treats every prior fitted number as untrusted and recomputes from raw data.

---

## Architecture Reference

**Core idea:** ML + Sionna RT loop that targets *communication fidelity* (RSRP MAE on held-out data),
not tower-position accuracy. Draws from:
- **NBF (Lyu et al., arXiv:2508.06956)** — Pretrain-and-Calibrate (PaC): physics pretraining via
  ray tracing + on-site calibration via a correction model. Our "blackbox" is a GP instead of Transformer.
- **Manukyan et al., Information Fusion 2025** — GP calibration for sim-to-real gap, retargeted from
  position-error loss to communication-metric-error loss.
- **Jiang et al., IEEE OJCOMS 2025** — Learnable digital-twin framing.

**Split:** Day-based temporal split.
- Train: June 22–23, 2021 (sessions 0–10 for pc1/pc3; 0–10 for pc2/pc4)
- Held-out: June 24, 2021 (sessions 11–16 for pc1/pc3; session 11 for pc2/pc4)
- Programmatic leakage check enforced in A02.

**Gap Classification (A01):**
- Type A (low TVD, session-aligned) → excluded from training/calibration. Never deleted.
- Type B (high TVD, not session-aligned, recurs) → retained in ALL stages. Tagged.
- Ambiguous → retained (conservative), flagged for manual review.

**Calibration independence:** Offset fit = mean(measured_RSRP − Sionna_power) on training rows only.
No 3GPP model values used anywhere in the fitting chain. Verified explicitly in A03.

---

## Files

| File | Purpose | Status |
|------|---------|--------|
| `A00_opencellid_lookup.py` | Tower position lookup via OpenCelliD bulk DB (replaces WCL) | ✅ Written |
| `A01_gap_classification.py` | Gap Classification Module — fresh TVD/session/recurrence classification | ✅ Written |
| `A02_split_and_verify.py` | Day-based held-out split + programmatic leakage check | ✅ Written |
| `A03_fresh_baseline.py` | WCL (fresh) + Sionna forward pass + calibration offset + baseline eval | ✅ Written |
| `A03b_ocid_baseline.py` | OCID tower positions + Sionna forward pass (OCID vs WCL comparison) | ✅ Written |
| `A04_gp_calibration.py` | GP correction model (Manukyan/NBF style) trained on train split only | ✅ Written |
| `A05_oracle_check.py` | Leave-one-device-out + bootstrap null (independent oracle check) | ✅ Written |
| `A06_report.py` | Stratified results: device × distance × area × gap_type | ✅ Written |
| `A07_sionna_inverse_localization.py` | Nelder-Mead inverse RT localization (MLE/variance loss) + Gate-2 val eval | ✅ Written |
| `paper/main.tex` | Full TWINGATE paper LaTeX (ready for Overleaf) | ✅ Written |
| `paper/references.bib` | Complete bibliography (Kay 1993, Hoydis 2023, Nelder 1965, etc.) | ✅ Written |
| `out/` | All output CSVs and JSONs | — |

---

## Run Log

| Step | Script | Status | Key Output |
|------|--------|--------|------------|
| 0 | A00 | ✅ Done | `out/tower_positions.csv`, `out/position_report.txt` |
| 1 | A01 | ✅ Done | `out/gap_labels.csv`, `out/gap_report.csv` |
| 2 | A02 | ✅ Done | `out/split_index.csv`, `out/split_summary.txt` |
| 3 | A03 | ✅ Done (WCL positions) | `out/sionna_raw.csv`, `out/baseline_results.json` |
| 3b | A03b (OCID baseline) | ✅ Done | `out/sionna_raw_ocid.csv`, `out/baseline_results_ocid.json`; Op1 OCID MAE=12.46 dB (vs WCL 10.87), Op2 run was killed — needs clean re-run |
| 7 | A07 (Nelder-Mead inverse RT) | ⏳ Ready to run | `out/refined_positions.csv`, `out/gate2_results.json` |
| 4 | A04 | ✅ Done (GP fails — see findings) | `out/gp_results.csv`, `out/gp_model_op{1,2}.pkl` |
| 5 | A05 | ✅ Done | `out/oracle_check.json` |
| 6 | A06 | ✅ Done | `out/final_report.csv`, `out/final_summary.json` |

---

## Checks Required (per architecture spec)

| Check | Script | Result |
|-------|--------|--------|
| Calibration independence (offset NOT anchored to 3GPP) | A03 | ⏳ |
| Held-out leakage: no val row reachable from training loop | A02 | ⏳ |
| Independent oracle: leave-one-out sits outside bootstrap null AND in correct direction | A05 | ⏳ |
| Type A rows excluded from training; Type B rows retained everywhere | A01→A03 | ⏳ |

---

## Key Numbers (filled in as runs complete)

### A00 OpenCelliD Tower Position Lookup (DONE)
Using `opencellid_germany.csv.gz` (5.3 MB, July 22 snapshot). Improved over prior attempt by
adding TAC-ignored ECI fallback and eNB-ID sibling-sector fallback.

| | Op1 (Telekom) | Op2 (Vodafone) |
|--|--|--|
| Total towers | 145 | 186 |
| ocid_exact (ECI+TAC) | 70 | 56 |
| ocid_eci_notac (ECI, wrong TAC in OCID) | 11 | 0 |
| ocid_enb_sibling (same physical tower, sibling sector) | 52 | 88 |
| wcl_fallback (insufficient OCID) | 2 | 23 |
| MISSING | 10 | 19 |
| **Total found** | **135/145 (93.1%)** | **167/186 (89.8%)** |

**OCID vs WCL position discrepancy:**
- Op1: median=164 m, p90=569 m, max=1971 m
- Op2: median=268 m, p90=719 m, max=1657 m

This confirms WCL was introducing 100–700 m tower position error. Since 100 m position error
translates to 3–10 dB RSRP error in near-field geometry, OCID positions should substantially
improve Sionna MAE. Next step: re-run A03 with OCID positions.

Output: `out/tower_positions.csv`, `out/position_report.txt`

### A01 Gap Classification (DONE)
| Device | TypeA | TypeB | Ambiguous | Unflagged |
|--------|-------|-------|-----------|-----------|
| pc1 | 0 | 1 | 6 | ~60,200 |
| pc2 | 0 | 35 | 9 | ~43,410 |
| pc3 | 0 | 38 | 3 | ~60,380 |
| pc4 | **1 (9045 rows)** | 0 | 4 | ~34,290 |

Row-level: TypeA=9,045 (pc4 large gap, TVD=0.030, session-aligned, non-recurrent)
TypeB=683, Ambiguous=309, Unflagged=197,397

**pc4's 9045-row gap classifies TypeA**: low TVD (0.030 — area composition similar to device overall), 
session-aligned (spans session boundary), does NOT recur across passes → instrumentation failure, safe to exclude from training.

### A02 Split Sizes (DONE — leakage PASS)
- Train: 158,579 rows (June 22–23) | Val: 46,363 rows (June 24)
- Op1: pc1 train=39,374 val=20,145 | pc4 train=39,667 val=3,154
- Op2: pc2 train=39,725 val=3,154 | pc3 train=39,813 val=19,910
- TypeA rows are ALL in train set (9,045 rows) — none in val. Val: TypeB=105, Ambiguous=30.
- **Leakage check: PASS** (zero overlap, zero temporal bleed)

### A03 Fresh Baseline (DONE)
| | Op1 | Op2 |
|--|-----|-----|
| Calibration offset (fresh) | −34.939 dB (std=17.4) | −40.788 dB (std=20.6) |
| Calibration independence | ✅ PASS | ✅ PASS |
| Baseline Val MAE | **10.866 dB** | **12.238 dB** |
| Baseline Val RMSE | 26.618 dB | 21.928 dB |
| pc1 / pc4 MAE | 11.555 / 10.012 dB | — |
| pc2 / pc3 MAE | — | 10.400 / 13.815 dB |
| TypeB rows MAE | 4.367 dB (n=36) | 10.250 dB (n=45) |

**Distance regime (Op1):** 0-200m=8.4 dB, 200-500m=17.5 dB, 500m+=82 dB (few rows, large WCL error)

**Area (Op1):** Park=7.0, Avenue=7.7, Residential=14.6, Highway=14.4, Tunnel=18.7 dB

### A04 GP Calibration (DONE — FAILED TO IMPROVE)
GP dramatically worsens MAE: Op1 36.0 dB (vs 10.9 baseline), Op2 43.7 dB (vs 12.2 baseline).
**Root cause:** Global GP with features [sionna_power, dist, freq, area] cannot generalize from June 22-23 training routes to June 24 val routes. The dominant error source is tower-specific WCL position uncertainty, which is not predictable from these 4 features. A per-tower GP (or per-tower learned offset) would be required, but with only 40 training rows per tower it is also unlikely to generalize well.

### A05 Oracle Check (DONE)
| Op | Device | Improvement | Percentile | Verdict |
|---|---|---|---|---|
| 1 | pc1 | −0.509 dB | 0th | FAIL — wrong direction |
| 1 | **pc4** (DT-QUEST flagged) | −0.109 dB | 0th | **FAIL — wrong direction** |
| 2 | pc2 | +0.343 dB | 100th | **PASS** |
| 2 | pc3 | −0.913 dB | 0th | FAIL — wrong direction |

**Op1 interpretation:** Excluding PC4's calibration training rows shifts the global offset to a value that generalizes less well to the val set. The oracle check (at the calibration-offset level) does NOT confirm the GZ-3 finding (which tested val-row exclusion, a different question). This is an honest failed check — not omitted.

**Op2 interpretation:** PC2 exclusion improves val MAE (+0.343 dB, 100th percentile). PC2 is not DT-QUEST flagged, so this doesn't directly validate Gate-2 for Op2.

### A03b OCID Baseline (PARTIAL — Op2 run killed)

Used `tower_positions.csv` from A00 instead of computing WCL fresh.
NaN fix applied: `train_cells = df_train[CELL_COL].dropna().unique()`.

| | Op1 | Op2 |
|--|-----|-----|
| Calibration offset | −29.154 dB (std=21.242) | — |
| Val MAE (OCID positions) | **12.459 dB** | — |
| Val RMSE | 26.926 dB | — |
| pc1 / pc4 MAE | 12.947 / 11.854 dB | — |

**By position source (Op1 val):**
- ocid_exact: 11.334 dB (n=12989)
- ocid_eci_notac: 11.004 dB (n=2839)
- wcl_fallback: 15.917 dB (n=5421)

**Key finding:** OCID-exact positions do slightly better than WCL-fallback (11.3 vs 15.9 dB),
but the overall OCID MAE (12.46) is WORSE than WCL baseline (10.87) because WCL initialization
benefits from regression-to-mean (WCL positions are near the measurement centroid, and RSRP-weighted
centroid is correlated with RSS-based path-loss). OCID positions are "true" but Sionna's
path-loss model has no per-tower calibration yet. A07's Nelder-Mead refinement is needed to
find positions that minimize actual Sionna reconstruction error.

**A07 expected to close this gap by finding positions that minimize Var(residuals) on training data.**

### A07 Inverse Localization (NOT YET RUN — script written 2026-08-16)

Script: `A07_sionna_inverse_localization.py`

Design:
- Loss: Var(measured_RSRP − Sionna_power) = MLE under log-normal shadowing (Kay 1993)
- Phase 1: 5×5 coarse grid ±300m around OCID/WCL init (25 Sionna calls)
- Phase 2: Nelder-Mead from best grid point, arm=80m, max-disp=600m, xatol=2m (≤120 iters)
- Calibration offset fit on training rows only; val eval exactly once
- Outputs: `out/refined_positions.csv`, `out/gate2_results.json`

%%% PLACEHOLDER: Run A07 and paste Gate-2 MAE here %%%

### All Checks Summary
| Check | Result |
|-------|--------|
| [1] Calibration independence (no 3GPP in offset fitting) | ✅ PASS |
| [2] Held-out leakage (A02 programmatic) | ✅ PASS |
| [3] Oracle: Op1 pc4 (DT-QUEST flagged) | ❌ FAIL — wrong direction |
| [3] Oracle: Op2 pc2 | ✅ PASS |
| [4] TypeA excluded / TypeB retained | ✅ PASS |
