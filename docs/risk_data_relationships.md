# Risk Module — Data Relationships

**Module key:** `risk` · **Organ role:** Immune System Primary (market risk · operational risk · RWA · stress testing · risk-based pricing)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Per Phase 1 Data Health: entity relationships within this module's data domain.

---

## Core entities

- **Staff** (`staff_code` PK) → **Role** → **Branch** → **Region**
- **KPI** (`kpi_id` PK) → **Role** (role_kpis) → **Target** → **Actual**
- **BSC scorecard** keyed by `(staff_code, period)` → 4 pillar scores

