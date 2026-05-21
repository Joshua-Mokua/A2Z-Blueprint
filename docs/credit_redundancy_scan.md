# Credit Module — Redundant Components Scan

**Module key:** `credit` · **Organ role:** The heart of the bank
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 38.6%

Per Phase 1 Technical Health: detect duplicated logic, unused imports, or redundant pages.

---

## Page overlap analysis

- `21_loan_applications.py` — 6 tabs
- `22_credit_analysis.py` — 7 tabs
- `23_credit_admin.py` — 5 tabs
- `39_ews.py` — 5 tabs
- `40_collateral.py` — 4 tabs
- `70_retailer_finance.py` — 6 tabs
- `71_bid_bond.py` — 6 tabs
- `82_credit_approvals.py` — 8 tabs

## Engine overlap

- Engines: 8
- Cross-engine reference check: pending dedicated scan

## Recommendations

- Consolidate where two engines compute the same KPI
- Merge stub pages into full-feature pages
