# Admin Module — Architecture

**Module key:** `admin` · **Organ role:** Central Nervous System Coordination
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 100.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (1)

- `7_admin.py` — 9586 LOC

## Engines (6)

- `utils/admin_registry.py` — 154 LOC · (undocumented)
- `utils/admin_validation_engine.py` — 820 LOC · (undocumented)
- `utils/canonical_admin.py` — 411 LOC · utils/canonical_admin.py — Canonical hierarchy admin operations (LEAF MODULE).
- `utils/standards_registry.py` — 6148 LOC · (undocumented)
- `utils/standards_wiring_audit_engine.py` — 644 LOC · (undocumented)
- `utils/bsc_admin_panel.py` — 1132 LOC · (undocumented)

## Module boundaries

- **Organ role**: Central Nervous System Coordination
- **Cross-organ links**: hr, bsc, audit

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
