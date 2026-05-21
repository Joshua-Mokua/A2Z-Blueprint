# Finance Module — Operational Dependencies

**Module key:** `finance` · **Organ role:** Circulatory & Energy Distribution System (GL · close · accruals · operating segments · financial intelligence)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Per Phase 1 Functional Health: operational dependencies.

---

## Upstream dependencies

- **credit**: provision, ifrs9
- **treasury**: liquidity, treasury
- **operations**: transaction, ops
- **risk**: risk_weight, capital
- **admin**: audit_log, rbac
- **bsc**: kpi, actual, target

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
