# Legal Module — Architecture

**Module key:** `legal` · **Organ role:** Bony Skeleton & Constitutional Framework (cases · documents · holds · board governance · spend · contracts)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (3)

- `26_legal.py` — 817 LOC
- `84_board.py` — 170 LOC
- `124_company_secretary_centre.py` — 345 LOC

## Engines (13)

- `utils/legal_analytics.py` — 707 LOC · (undocumented)
- `utils/legal_case_management.py` — 362 LOC · utils/legal_case_management.py — ENH-223 Legal Case Management.
- `utils/legal_dashboard.py` — 550 LOC · (undocumented)
- `utils/legal_document_management.py` — 650 LOC · (undocumented)
- `utils/legal_hold_management.py` — 456 LOC · (undocumented)
- `utils/legal_spend_management.py` — 436 LOC · (undocumented)
- `utils/board_reporting.py` — 471 LOC · (undocumented)
- `utils/flexcube_integration_readiness.py` — 348 LOC · (undocumented)
- `utils/stress_test_harness.py` — 325 LOC · (undocumented)
- `utils/scalability_validator.py` — 329 LOC · (undocumented)
- `utils/cross_organ_event_bus.py` — 298 LOC · (undocumented)
- `utils/super_user_registry.py` — 347 LOC · (undocumented)
- `utils/notification_broadcaster.py` — 265 LOC · (undocumented)

## Module boundaries

- **Organ role**: Bony Skeleton & Constitutional Framework (cases · documents · holds · board governance · spend · contracts)
- **Cross-organ links**: admin, hr, credit, risk, bsc

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
