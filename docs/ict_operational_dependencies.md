# ICT Module — Operational Dependencies

**Module key:** `ict` · **Organ role:** Lungs - System-wide Oxygen Exchange (Flexcube integration · Observability · CICD · Cybersecurity · Disaster Recovery)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Per Phase 1 Functional Health: operational dependencies.

---

## Upstream dependencies

- **all_modules**: flexcube_adapter, flexcube_integration_readiness
- **admin**: super_user, audit_log, rbac
- **credit**: credit, loan
- **hr**: staff, branch
- **bsc**: kpi, bsc
- **observability**: uptime, metric, alert

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
