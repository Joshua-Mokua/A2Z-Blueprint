# Credit Module — Architecture

**Module key:** `credit` · **Organ role:** The heart of the bank
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 38.6%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (14)

- `21_loan_applications.py` — 682 LOC
- `22_credit_analysis.py` — 982 LOC
- `23_credit_admin.py` — 286 LOC
- `24_credit_committee.py` — 0 LOC
- `25_credit_monitoring.py` — 0 LOC
- `26_drr.py` — 0 LOC
- `27_ifrs9.py` — 0 LOC
- `38_credit_workbench.py` — 0 LOC
- `39_ews.py` — 131 LOC
- `40_collateral.py` — 109 LOC
- `70_retailer_finance.py` — 167 LOC
- `71_bid_bond.py` — 178 LOC
- `72_specialized_credit.py` — 0 LOC
- `82_credit_approvals.py` — 955 LOC

## Engines (8)

- `utils/credit_workflow.py` — 1002 LOC · (undocumented)
- `utils/credit_committee.py` — 988 LOC · (undocumented)
- `utils/credit_risk_scoring.py` — 428 LOC · (undocumented)
- `utils/credit_alt_scoring.py` — 759 LOC · (undocumented)
- `utils/credit_risk_irb.py` — 709 LOC · (undocumented)
- `utils/credit_underwriting.py` — 0 LOC · (undocumented)
- `utils/ifrs9_engine.py` — 0 LOC · (undocumented)
- `utils/analytics_credit_workbench.py` — 512 LOC · (undocumented)

## Module boundaries

- **Organ role**: The heart of the bank
- **Cross-organ links**: hr, risk, operations, finance, crm, pipeline

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
