# Finance Module — Architecture

**Module key:** `finance` · **Organ role:** Circulatory & Energy Distribution System (GL · close · accruals · operating segments · financial intelligence)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (4)

- `46_trade_finance.py` — 748 LOC
- `70_retailer_finance.py` — 167 LOC
- `116_finance_hub.py` — 156 LOC
- `122_chief_finance_centre.py` — 344 LOC

## Engines (12)

- `utils/accruals_synthesizer.py` — 384 LOC · (undocumented)
- `utils/finance_audit_compliance.py` — 795 LOC · (undocumented)
- `utils/finance_close_orchestrator.py` — 1014 LOC · (undocumented)
- `utils/finance_hub_render.py` — 2564 LOC · 
- `utils/finance_intelligence_dashboard.py` — 913 LOC · (undocumented)
- `utils/operating_segments.py` — 516 LOC · (undocumented)
- `utils/flexcube_integration_readiness.py` — 348 LOC · (undocumented)
- `utils/stress_test_harness.py` — 325 LOC · (undocumented)
- `utils/scalability_validator.py` — 329 LOC · (undocumented)
- `utils/cross_organ_event_bus.py` — 298 LOC · (undocumented)
- `utils/super_user_registry.py` — 347 LOC · (undocumented)
- `utils/notification_broadcaster.py` — 265 LOC · (undocumented)

## Module boundaries

- **Organ role**: Circulatory & Energy Distribution System (GL · close · accruals · operating segments · financial intelligence)
- **Cross-organ links**: credit, treasury, operations, risk, admin, bsc

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
