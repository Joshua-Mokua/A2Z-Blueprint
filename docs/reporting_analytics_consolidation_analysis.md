# REPORTING_ANALYTICS — Module Consolidation Analysis

**Generated:** 2026-05-15 (v10.460 real cross-page analysis)
**Module key:** `reporting_analytics`

## Summary

- Total pages: **9**
- Substantial pages (≥300 LOC): **5**
- Tab candidates (<100 LOC + <2 tabs): **3**
- Average LOC per page: **292.6**
- Average tabs per page: **1.0**
- Function duplications detected: **1**
- Consolidation opportunity score: **20.5/100**

## Recommendation

LOW consolidation opportunity. Module appears well-distributed with 5/9 substantial pages.

## Tab candidates (3)

| Page | LOC | Tabs | Functions | Suggested parent | Reason |
|---|---|---|---|---|---|
| `11_competitor.py` | 44 | 0 | 0 | `15_optimize.py` | Page is small (44 LOC) and has only 0 tab block(s) — likely tab candidate |
| `93_competitor_intelligence.py` | 45 | 0 | 0 | `90_remaining_ifrs.py` | Page is small (45 LOC) and has only 0 tab block(s) — likely tab candidate |
| `114_sbu_drilldown.py` | 48 | 0 | 0 | `113_branch_ranking.py` | Page is small (48 LOC) and has only 0 tab block(s) — likely tab candidate |

## Function duplications

| Function | Occurrences | Pages |
|---|---|---|
| `main` | 3 | `101_analytics_workbench.py`, `102_analytics_advanced.py`, `118_competitor_hub.py` |

## Action items

- Review 3 tab-candidate page(s) for merge into parent pages
- Extract 1 duplicate function(s) into a shared `utils/` helper module
- Module is well-structured; no urgent consolidation needed
