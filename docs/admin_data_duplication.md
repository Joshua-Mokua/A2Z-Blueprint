# Admin Module — Data Duplication Risk

**Module key:** `admin` · **Organ role:** Central Nervous System Coordination
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 100.0%

Per Phase 1 Data Health: assess where the same data is stored in multiple places and reconciliation risks.

---

## Known duplications

- Staff list lives in `users.json` AND `staff_register.xlsx`
- KPI definitions in `kpi_library.json` AND embedded in code
- Target values in `target_cascade.json` AND inline defaults

## Reconciliation strategy

- Treat `users.json` as canonical staff source
- Treat `kpi_library.json` as canonical KPI source
- Treat `target_cascade.json` as canonical target source
- Remove embedded fallbacks; fail-fast on missing canonical data
