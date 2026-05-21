# CRM — Module Consolidation Analysis

**Generated:** 2026-05-15 (v10.460 real cross-page analysis)
**Module key:** `crm`

## Summary

- Total pages: **22**
- Substantial pages (≥300 LOC): **11**
- Tab candidates (<100 LOC + <2 tabs): **3**
- Average LOC per page: **578.8**
- Average tabs per page: **1.82**
- Function duplications detected: **1**
- Consolidation opportunity score: **8.2/100**

## Recommendation

LOW consolidation opportunity. Module appears well-distributed with 11/22 substantial pages.

## Tab candidates (3)

| Page | LOC | Tabs | Functions | Suggested parent | Reason |
|---|---|---|---|---|---|
| `27_propositions.py` | 44 | 0 | 0 | `25_treasury.py` | Page is small (44 LOC) and has only 0 tab block(s) — likely tab candidate |
| `48_contact_centre.py` | 91 | 1 | 0 | `45_crosssell.py` | Page is small (91 LOC) and has only 1 tab block(s) — likely tab candidate |
| `92_propositions_workbench.py` | 44 | 0 | 0 | `90_remaining_ifrs.py` | Page is small (44 LOC) and has only 0 tab block(s) — likely tab candidate |

## Function duplications

| Function | Occurrences | Pages |
|---|---|---|
| `main` | 2 | `104_tf_mobile.py`, `117_propositions_hub.py` |

## Action items

- Review 3 tab-candidate page(s) for merge into parent pages
- Extract 1 duplicate function(s) into a shared `utils/` helper module
- Module is well-structured; no urgent consolidation needed
