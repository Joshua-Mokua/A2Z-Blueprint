# ICT Module — Data Inconsistency Scan

**Module key:** `ict` · **Organ role:** Lungs - System-wide Oxygen Exchange (Flexcube integration · Observability · CICD · Cybersecurity · Disaster Recovery)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Per Phase 8 Anti-Deterioration: detect data inconsistencies (referential integrity, type mismatches, orphan records).

---

## Consistency checks

- Staff codes in BSC must exist in users.json
- KPI IDs in scorecards must exist in kpi_library.json
- Roles in target_cascade must match users.json roles

## Known inconsistencies

- Some BSC rows reference roles missing from cascade (esp. credit roles)
- Period strings vary in format

## Mitigations

- Foreign-key constraints in PostgreSQL schema
- Validation pass on app startup
