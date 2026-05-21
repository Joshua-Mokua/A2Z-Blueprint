# BSC_CASCADE — Module Consolidation Analysis

**Generated:** 2026-05-15 (v10.460 real cross-page analysis)
**Module key:** `bsc_cascade`

## Summary

- Total pages: **2**
- Substantial pages (≥300 LOC): **2**
- Tab candidates (<100 LOC + <2 tabs): **0**
- Average LOC per page: **3708.0**
- Average tabs per page: **6.5**
- Function duplications detected: **1**
- Consolidation opportunity score: **15.0/100**

## Recommendation

LOW consolidation opportunity. Module appears well-distributed with 2/2 substantial pages.

## Function duplications

| Function | Occurrences | Pages |
|---|---|---|
| `hl_status` | 2 | `1_perform.py`, `12_cascade.py` |

## Action items

- Extract 1 duplicate function(s) into a shared `utils/` helper module
- Module is well-structured; no urgent consolidation needed
