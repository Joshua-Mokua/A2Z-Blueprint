# Operations Module — Data Relationships

**Module key:** `operations` · **Organ role:** Muscular & Movement System (branch ops · CIMS · SLA · EDMS · approvals · fraud · clearing · projects · procurement · vendors · assets · contracts · SWIFT)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Per Phase 1 Data Health: entity relationships within this module's data domain.

---

## Core entities

- **Staff** (`staff_code` PK) → **Role** → **Branch** → **Region**
- **KPI** (`kpi_id` PK) → **Role** (role_kpis) → **Target** → **Actual**
- **BSC scorecard** keyed by `(staff_code, period)` → 4 pillar scores

