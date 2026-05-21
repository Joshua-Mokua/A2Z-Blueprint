# Compliance Module — Architecture

**Module key:** `compliance` · **Organ role:** Immune System Antibodies (KYC · AML · CBK returns · sanctions · tax · regulatory reporting · IRA insurance)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 60.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (7)

- `24_compliance.py` — 608 LOC
- `74_cbk_returns.py` — 1414 LOC
- `76_sanctions.py` — 198 LOC
- `103_compliance_dashboard.py` — 385 LOC
- `107_cims_compliance.py` — 766 LOC
- `112_compliance_live.py` — 44 LOC
- `126_compliance_centre.py` — 346 LOC

## Engines (21)

- `utils/aml_monitoring.py` — 451 LOC · (undocumented)
- `utils/api_compliance.py` — 449 LOC · (undocumented)
- `utils/cbk_regulatory_reporting.py` — 1351 LOC · utils/cbk_regulatory_reporting.py — v10.62: CBK returns.
- `utils/compliance_dashboard.py` — 502 LOC · (undocumented)
- `utils/compliance_risk_assessment.py` — 775 LOC · (undocumented)
- `utils/compliance_training.py` — 555 LOC · (undocumented)
- `utils/finance_audit_compliance.py` — 795 LOC · (undocumented)
- `utils/insurance_ira_compliance.py` — 990 LOC · (undocumented)
- `utils/it_cbk_compliance.py` — 650 LOC · (undocumented)
- `utils/kra_tax_compliance.py` — 748 LOC · (undocumented)
- `utils/kyc_aml_risk.py` — 585 LOC · (undocumented)
- `utils/kyc_onboarding.py` — 738 LOC · (undocumented)
- `utils/regulatory_reporting.py` — 437 LOC · (undocumented)
- `utils/sanctions_screening.py` — 501 LOC · (undocumented)
- `utils/tax_compliance.py` — 600 LOC · (undocumented)
- `utils/flexcube_integration_readiness.py` — 348 LOC · (undocumented)
- `utils/stress_test_harness.py` — 325 LOC · (undocumented)
- `utils/scalability_validator.py` — 329 LOC · (undocumented)
- `utils/cross_organ_event_bus.py` — 298 LOC · (undocumented)
- `utils/super_user_registry.py` — 347 LOC · (undocumented)
- `utils/notification_broadcaster.py` — 265 LOC · (undocumented)

## Module boundaries

- **Organ role**: Immune System Antibodies (KYC · AML · CBK returns · sanctions · tax · regulatory reporting · IRA insurance)
- **Cross-organ links**: risk, credit, operations, admin, hr, bsc

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
