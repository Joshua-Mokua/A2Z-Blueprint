# Operations Module — Operational Dependencies

**Module key:** `operations` · **Organ role:** Muscular & Movement System (branch ops · CIMS · SLA · EDMS · approvals · fraud · clearing · projects · procurement · vendors · assets · contracts · SWIFT)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Per Phase 1 Functional Health: operational dependencies.

---

## Upstream dependencies

- **credit**: disbursement, credit
- **compliance**: aml, kyc, sanctions
- **finance**: reconciliation, settlement
- **risk**: fraud, incident, operational_loss
- **admin**: audit_log, rbac, approval
- **bsc**: sla, tat, throughput
- **all_modules**: edms, cims, sla

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
