# Treasury Module — Architecture

**Module key:** `treasury` · **Organ role:** Cash Flow Reservoir & Arterial Blood Pressure (ALM · FTP · FX · liquidity · market risk · VAR)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 60.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (3)

- `25_treasury.py` — 1071 LOC
- `110_treasury_live.py` — 44 LOC
- `123_head_treasury_centre.py` — 345 LOC

## Engines (21)

- `utils/benchmark_rates.py` — 868 LOC · (undocumented)
- `utils/funds_transfer_pricing.py` — 390 LOC · (undocumented)
- `utils/fx_position.py` — 433 LOC · (undocumented)
- `utils/liquidity_risk.py` — 609 LOC · (undocumented)
- `utils/liquidity_stress.py` — 744 LOC · (undocumented)
- `utils/market_risk.py` — 354 LOC · (undocumented)
- `utils/market_risk_factors.py` — 644 LOC · (undocumented)
- `utils/market_risk_limits.py` — 970 LOC · (undocumented)
- `utils/market_risk_sensitivities.py` — 664 LOC · (undocumented)
- `utils/market_risk_var.py` — 815 LOC · (undocumented)
- `utils/treasury_agents.py` — 862 LOC · (undocumented)
- `utils/treasury_alm.py` — 1221 LOC · (undocumented)
- `utils/treasury_connectivity.py` — 723 LOC · (undocumented)
- `utils/treasury_dashboard.py` — 755 LOC · (undocumented)
- `utils/treasury_dashboard_wiring.py` — 93 LOC · (undocumented)
- `utils/flexcube_integration_readiness.py` — 348 LOC · (undocumented)
- `utils/stress_test_harness.py` — 325 LOC · (undocumented)
- `utils/scalability_validator.py` — 329 LOC · (undocumented)
- `utils/cross_organ_event_bus.py` — 298 LOC · (undocumented)
- `utils/super_user_registry.py` — 347 LOC · (undocumented)
- `utils/notification_broadcaster.py` — 265 LOC · (undocumented)

## Module boundaries

- **Organ role**: Cash Flow Reservoir & Arterial Blood Pressure (ALM · FTP · FX · liquidity · market risk · VAR)
- **Cross-organ links**: finance, credit, risk, admin, bsc

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
