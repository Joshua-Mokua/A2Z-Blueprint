# Compliance Module — Operational Dependencies

**Module key:** `compliance` · **Organ role:** Immune System Antibodies (KYC · AML · CBK returns · sanctions · tax · regulatory reporting · IRA insurance)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 60.0%

Per Phase 1 Functional Health: operational dependencies.

---

## Upstream dependencies

- **risk**: risk, incident
- **credit**: kyc, aml, customer
- **operations**: transaction, monitoring
- **admin**: audit_log, rbac
- **hr**: training, certification
- **bsc**: kpi, target

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
