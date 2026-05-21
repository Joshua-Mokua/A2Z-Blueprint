# COMPLIANCE — Module Consolidation Analysis

**Generated:** 2026-05-15 (v10.460 real cross-page analysis)
**Module key:** `compliance`

## Summary

- Total pages: **7**
- Substantial pages (≥300 LOC): **5**
- Tab candidates (<100 LOC + <2 tabs): **1**
- Average LOC per page: **537.3**
- Average tabs per page: **1.43**
- Function duplications detected: **1**
- Consolidation opportunity score: **11.4/100**

## Recommendation

LOW consolidation opportunity. Module appears well-distributed with 5/7 substantial pages.

## Tab candidates (1)

| Page | LOC | Tabs | Functions | Suggested parent | Reason |
|---|---|---|---|---|---|
| `112_compliance_live.py` | 44 | 0 | 0 | `113_branch_ranking.py` | Page is small (44 LOC) and has only 0 tab block(s) — likely tab candidate |

## Function duplications

| Function | Occurrences | Pages |
|---|---|---|
| `main` | 2 | `103_compliance_dashboard.py`, `107_cims_compliance.py` |

## Action items

- Review 1 tab-candidate page(s) for merge into parent pages
- Extract 1 duplicate function(s) into a shared `utils/` helper module
- Module is well-structured; no urgent consolidation needed
