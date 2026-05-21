# Credit Module — Data Lineage

**Module key:** `credit` · **Organ role:** The heart of the bank
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 38.6%

Per Phase 1 Data Health: trace where each piece of data originates and how it flows through the module.

---

## KPI actuals lineage

1. CBS raw transactions → engines
2. Engines compute KPI actuals
3. Actuals stored in `balanced_scorecards.json` per period
4. BSC engine computes final scores per pillar weights
5. Scores rendered in pages + Chief Centre dashboards

## Audit chain

- Every write logged via `audit_log()` to audit trail
- Period locks prevent retroactive edits
