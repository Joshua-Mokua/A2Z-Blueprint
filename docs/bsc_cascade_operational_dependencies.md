# BSC & Target Cascade — Operational Dependencies

**Module key:** `bsc_cascade` · **Organ role:** Brain Intelligence, Direction & Decision Flow
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 100.0%

Per Phase 1 Functional Health: operational dependencies.

---

## Upstream dependencies

- **credit**: credit, loan, npl
- **hr**: staff, training, performance
- **admin**: kpi_library, role_kpis

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
