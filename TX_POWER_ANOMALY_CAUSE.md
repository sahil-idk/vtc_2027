# Tx Power Anomaly — Diagnostic Notes (cause.md)

**Field:** `PCell_Uplink_Tx_Power_(dBm)` (also `SCell_Uplink_Tx_Power_(dBm)`, but that
column is 100% empty in this dataset — SCell never reports uplink Tx power here).

## Status: unresolved, flag-only, do not correct

## What we know

- **Correct 3GPP valid range** (TS 36.101 §6.3.2): minimum controlled output power
  **−40 dBm**; maximum per UE power class: **23 dBm** (Class 3, standard handset,
  most common) / 26 dBm (Class 2) / 31 dBm (Class 1, vehicle-mounted/high-power).
  So the paper's stated range of `[10, 30]` dBm was itself wrong — real valid
  range is roughly `[−40, 26]` dBm (up to 31 for high-power classes).

- **Even under the corrected, wider bound**, 29–48% of rows per device
  (pc1: 48.2%, pc4: 38.6%, pc2: 28.5%, pc3: 37.3%) still fall outside
  `[−40, 26]` dBm. Actual data range is `[0, 127]` dBm, mean 42.8 dBm.

- **Restricting to `direction == "uplink"` rows only** (where this field is most
  semantically meaningful) still leaves ~23% out of range, up to 126.8 dBm.
  `direction == "downlink"` rows are worse (~43% out of range).

- **Values cluster with high downlink activity**: rows with Tx Power > 60 dBm
  consistently show `PCell_Uplink_Num_RBs` near the max (~970–998 out of ~1000)
  and `PCell_Uplink_TB_Size` near max (~28,000–30,000), and are overwhelmingly
  `direction == "downlink"`.

- **Not a simple unit/scale bug**: dividing by 10, 100, or by `Num_RBs` does not
  recover a plausible dBm value. Correlation between Tx Power and Num_RBs / TB_Size
  is weak and slightly *negative* (−0.26), so it isn't a linear function of those
  fields either. Values are continuous floats (not integer-encoded sentinels like
  97/127/255 seen elsewhere in 3GPP RSRP-Range encodings), so it's not simply an
  "invalid" placeholder code either.

- **By scenario**: A3U (uplink data-rate test) is comparatively clean (~7%
  out-of-range); A2D/A2U/A3D scenarios are all ~40–44% out-of-range.

- **By area**: Tunnel is comparatively clean (~10%); Park/Residential/Avenue/
  Highway are all ~27–36% out-of-range — not isolated to one geography.

## Working hypotheses (untested)

1. The logging tool may be writing a **different underlying quantity** into this
   column during downlink-heavy periods (e.g., some derived/interim value from
   the modem's power-headroom or TA calculation) rather than true measured
   uplink Tx power.
2. It could be a **modem API misread** (e.g., reading an invalid/garbage
   register value when the UE isn't actively power-controlling uplink, similar
   in spirit to the "sentinel value" issues seen in Android RIL implementations
   for LTE signal strength fields).
3. Not yet ruled out: correlation with a specific `PCell_Cell_ID` / tower or
   antenna configuration (not checked yet — worth doing if this field turns out
   to be needed later).

## Decision taken

- **Do not clip, offset-correct, or otherwise "fix" this field.** Any correction
  would be a guess dressed up as a measurement.
- **Flag only** (`FLAG_range_PCell_Uplink_Tx_Power_(dBm)` in the cleaned CSVs),
  keep the raw value untouched, and **exclude this field from Sionna RT / twin
  validation** — everything else on the same row (RSRP, RSRQ, RSSI, SNR, GPS)
  is unaffected and usable normally.
- If uplink Tx power is ever needed later (e.g., for an uplink path-loss
  angle), revisit hypothesis #3 first (cell/antenna correlation) before trying
  anything else.
