# Credit Module — Operational Dependencies

**Module key:** `credit` · **Organ role:** The heart of the bank
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 38.6%

Per Phase 1 Functional Health: operational dependencies.

---

## Upstream dependencies

- **hr**: hr_actuals, staff_performance
- **risk**: risk_factor, ifrs9
- **operations**: operations, ops_queue
- **finance**: provision, treasury
- **crm**: customer_360, client
- **pipeline**: pipeline_deal_id

## Data dependencies

- `data/users.json` (RBAC + cascade)
- `data/target_cascade.json` (targets per role)
- `data/kpi_library.json` (KPI definitions)
- `data/balanced_scorecards.json` (historical BSC scores)
- `data/actuals_*.xlsx` (period actuals)

## Infrastructure dependencies

- Python 3.11+, Streamlit, FastAPI
- PostgreSQL (where adapter is wired)
- File system for JSON and XLSX data persistence
