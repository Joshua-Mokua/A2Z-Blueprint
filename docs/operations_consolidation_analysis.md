# OPERATIONS — Module Consolidation Analysis

**Generated:** 2026-05-15 (v10.460 real cross-page analysis)
**Module key:** `operations`

## Summary

- Total pages: **22**
- Substantial pages (≥300 LOC): **10**
- Tab candidates (<100 LOC + <2 tabs): **1**
- Average LOC per page: **478.6**
- Average tabs per page: **1.36**
- Function duplications detected: **3**
- Consolidation opportunity score: **6.4/100**

## Recommendation

LOW consolidation opportunity. Module appears well-distributed with 10/22 substantial pages.

## Tab candidates (1)

| Page | LOC | Tabs | Functions | Suggested parent | Reason |
|---|---|---|---|---|---|
| `109_cims_live.py` | 47 | 0 | 0 | `103_compliance_dashboard.py` | Page is small (47 LOC) and has only 0 tab block(s) — likely tab candidate |

## Function duplications

| Function | Occurrences | Pages |
|---|---|---|
| `main` | 5 | `99_swift_cockpit.py`, `105_cims_capture.py`, `106_cims_process.py` + 2 more |
| `get_open` | 2 | `13_sla.py`, `18_cims.py` |
| `get_all` | 2 | `13_sla.py`, `14_branch_log.py` |

## Action items

- Review 1 tab-candidate page(s) for merge into parent pages
- Extract 3 duplicate function(s) into a shared `utils/` helper module
- Module is well-structured; no urgent consolidation needed
