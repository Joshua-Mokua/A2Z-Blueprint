# Reporting & Analytics Module — Architecture

**Module key:** `reporting_analytics` · **Organ role:** Vital Signs Monitoring & Diagnostic Systems (reporting · analytics workbench · NLQ · anomaly · branch ranking · SBU drilldown · benchmarking · competitor intelligence)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (9)

- `11_competitor.py` — 44 LOC
- `28_ra.py` — 446 LOC
- `87_benchmarking.py` — 418 LOC
- `93_competitor_intelligence.py` — 45 LOC
- `101_analytics_workbench.py` — 494 LOC
- `102_analytics_advanced.py` — 549 LOC
- `113_branch_ranking.py` — 463 LOC
- `114_sbu_drilldown.py` — 48 LOC
- `118_competitor_hub.py` — 126 LOC

## Engines (6)

- `utils/flexcube_integration_readiness.py` — 348 LOC · (undocumented)
- `utils/stress_test_harness.py` — 325 LOC · (undocumented)
- `utils/scalability_validator.py` — 329 LOC · (undocumented)
- `utils/cross_organ_event_bus.py` — 311 LOC · (undocumented)
- `utils/super_user_registry.py` — 417 LOC · (undocumented)
- `utils/notification_broadcaster.py` — 265 LOC · (undocumented)

## Module boundaries

- **Organ role**: Vital Signs Monitoring & Diagnostic Systems (reporting · analytics workbench · NLQ · anomaly · branch ranking · SBU drilldown · benchmarking · competitor intelligence)
- **Cross-organ links**: all_modules, bsc, admin

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
