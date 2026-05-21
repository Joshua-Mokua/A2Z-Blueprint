# ICT Module — Architecture

**Module key:** `ict` · **Organ role:** Lungs - System-wide Oxygen Exchange (Flexcube integration · Observability · CICD · Cybersecurity · Disaster Recovery)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (9)

- `6_integrate.py` — 309 LOC
- `50_cybersecurity.py` — 118 LOC
- `72_observability.py` — 196 LOC
- `86_flexcube.py` — 324 LOC
- `91_systems_view.py` — 45 LOC
- `96_it_digital_pt1.py` — 44 LOC
- `97_it_digital_pt2.py` — 44 LOC
- `98_platform_health.py` — 46 LOC
- `119_platform_hub.py` — 153 LOC

## Engines (18)

- `utils/flexcube_adapter.py` — 1729 LOC · utils/flexcube_adapter.py — FLEXCUBE Integration Adapter Layer.
- `utils/flexcube_connection.py` — 358 LOC · (undocumented)
- `utils/flexcube_mappings.py` — 304 LOC · (undocumented)
- `utils/flexcube_staging.py` — 281 LOC · (undocumented)
- `utils/flexcube_integration_readiness.py` — 348 LOC · (undocumented)
- `utils/it_api_gateway.py` — 527 LOC · (undocumented)
- `utils/it_cbk_compliance.py` — 650 LOC · (undocumented)
- `utils/it_cicd.py` — 462 LOC · (undocumented)
- `utils/it_cloud_architecture.py` — 410 LOC · (undocumented)
- `utils/it_data_encryption.py` — 502 LOC · (undocumented)
- `utils/it_digital_banking.py` — 575 LOC · (undocumented)
- `utils/it_disaster_recovery.py` — 539 LOC · (undocumented)
- `utils/it_itsm.py` — 519 LOC · (undocumented)
- `utils/it_multi_tenancy.py` — 493 LOC · (undocumented)
- `utils/it_observability.py` — 435 LOC · (undocumented)
- `utils/virtual_bank_core.py` — 1167 LOC · (undocumented)
- `utils/virtual_bank_simulator.py` — 1323 LOC · (undocumented)
- `utils/virtual_bank_readiness.py` — 659 LOC · (undocumented)

## Module boundaries

- **Organ role**: Lungs - System-wide Oxygen Exchange (Flexcube integration · Observability · CICD · Cybersecurity · Disaster Recovery)
- **Cross-organ links**: all_modules, admin, credit, hr, bsc, observability

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
