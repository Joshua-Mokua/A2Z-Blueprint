# Risk Module — Architecture

**Module key:** `risk` · **Organ role:** Immune System Primary (market risk · operational risk · RWA · stress testing · risk-based pricing)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (3)

- `82_oprisk.py` — 175 LOC
- `89_capital_risk_engines.py` — 948 LOC
- `125_chief_risk_centre.py` — 346 LOC

## Engines (15)

- `utils/market_risk.py` — 354 LOC · (undocumented)
- `utils/market_risk_factors.py` — 644 LOC · (undocumented)
- `utils/market_risk_limits.py` — 970 LOC · (undocumented)
- `utils/market_risk_sensitivities.py` — 664 LOC · (undocumented)
- `utils/market_risk_var.py` — 815 LOC · (undocumented)
- `utils/operational_risk.py` — 578 LOC · (undocumented)
- `utils/risk_based_pricing.py` — 472 LOC · (undocumented)
- `utils/risk_weighted_assets.py` — 543 LOC · (undocumented)
- `utils/compliance_risk_assessment.py` — 775 LOC · (undocumented)
- `utils/flexcube_integration_readiness.py` — 348 LOC · (undocumented)
- `utils/stress_test_harness.py` — 325 LOC · (undocumented)
- `utils/scalability_validator.py` — 329 LOC · (undocumented)
- `utils/cross_organ_event_bus.py` — 298 LOC · (undocumented)
- `utils/super_user_registry.py` — 347 LOC · (undocumented)
- `utils/notification_broadcaster.py` — 265 LOC · (undocumented)

## Module boundaries

- **Organ role**: Immune System Primary (market risk · operational risk · RWA · stress testing · risk-based pricing)
- **Cross-organ links**: credit, treasury, compliance, finance, admin, bsc

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
