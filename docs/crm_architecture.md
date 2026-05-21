# CRM & Customer Functions Module — Architecture

**Module key:** `crm` · **Organ role:** Sensory & Interaction Systems (pipeline · customer 360 · propositions · campaigns · cross-sell · channels · NPS · behavioral intelligence · onboarding · cards · bancassurance · merchant acquiring)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (22)

- `3_pipeline.py` — 2028 LOC
- `5_products.py` — 761 LOC
- `16_commission.py` — 533 LOC
- `17_campaigns.py` — 482 LOC
- `27_propositions.py` — 44 LOC
- `34_customer360.py` — 3314 LOC
- `38_nps.py` — 111 LOC
- `45_crosssell.py` — 1091 LOC
- `47_digital_channels.py` — 121 LOC
- `48_contact_centre.py` — 91 LOC
- `49_bancassurance.py` — 119 LOC
- `66_partnerships.py` — 616 LOC
- `69_consent.py` — 173 LOC
- `73_channels.py` — 1271 LOC
- `78_onboarding.py` — 196 LOC
- `79_cards.py` — 179 LOC
- `80_merchant.py` — 156 LOC
- `91_customer_behavioral_intelligence.py` — 516 LOC
- `92_propositions_workbench.py` — 44 LOC
- `94_campaigns_management.py` — 446 LOC
- `104_tf_mobile.py` — 309 LOC
- `117_propositions_hub.py` — 132 LOC

## Engines (11)

- `utils/flexcube_integration_readiness.py` — 348 LOC · (undocumented)
- `utils/stress_test_harness.py` — 325 LOC · (undocumented)
- `utils/scalability_validator.py` — 329 LOC · (undocumented)
- `utils/cross_organ_event_bus.py` — 311 LOC · (undocumented)
- `utils/super_user_registry.py` — 417 LOC · (undocumented)
- `utils/notification_broadcaster.py` — 265 LOC · (undocumented)
- `utils/cross_sell_bandit.py` — 1276 LOC · (undocumented)
- `utils/customer_behavioral.py` — 0 LOC · (undocumented)
- `utils/dormancy_intelligence.py` — 687 LOC · (undocumented)
- `utils/deposit_intelligence.py` — 413 LOC · (undocumented)
- `utils/lending_intelligence.py` — 476 LOC · (undocumented)

## Module boundaries

- **Organ role**: Sensory & Interaction Systems (pipeline · customer 360 · propositions · campaigns · cross-sell · channels · NPS · behavioral intelligence · onboarding · cards · bancassurance · merchant acquiring)
- **Cross-organ links**: credit, operations, compliance, bsc, admin, treasury

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
