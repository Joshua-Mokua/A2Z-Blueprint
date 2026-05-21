# Risk Module — Operational Dependencies

**Module key:** `risk` · **Organ role:** Immune System Primary (market risk · operational risk · RWA · stress testing · risk-based pricing)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Per Phase 1 Functional Health: operational dependencies.

---

## Upstream dependencies

- **credit**: credit_risk, npl
- **treasury**: market_risk, var
- **compliance**: compliance, kyc
- **finance**: capital, rwa
- **admin**: audit_log, rbac
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
