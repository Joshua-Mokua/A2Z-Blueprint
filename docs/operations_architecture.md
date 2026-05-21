# Operations Module — Architecture

**Module key:** `operations` · **Organ role:** Muscular & Movement System (branch ops · CIMS · SLA · EDMS · approvals · fraud · clearing · projects · procurement · vendors · assets · contracts · SWIFT)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Module architecture per the doctrine Phase 1 Technical Health review. Identifies pages, engines, boundaries, and dependencies.

---

## Pages (22)

- `13_sla.py` — 836 LOC
- `14_branch_log.py` — 1266 LOC
- `18_cims.py` — 1591 LOC
- `30_rms.py` — 215 LOC
- `31_edms.py` — 237 LOC
- `37_approvals.py` — 150 LOC
- `44_incidents.py` — 136 LOC
- `51_agency_banking.py` — 103 LOC
- `59_cab.py` — 139 LOC
- `61_projects.py` — 635 LOC
- `62_p2p.py` — 246 LOC
- `63_assets.py` — 190 LOC
- `64_vendors.py` — 598 LOC
- `65_contracts.py` — 143 LOC
- `67_fraud.py` — 261 LOC
- `68_clearing.py` — 292 LOC
- `99_swift_cockpit.py` — 450 LOC
- `105_cims_capture.py` — 742 LOC
- `106_cims_process.py` — 742 LOC
- `107_cims_compliance.py` — 766 LOC
- `108_cims_closure.py` — 744 LOC
- `109_cims_live.py` — 47 LOC

## Engines (6)

- `utils/flexcube_integration_readiness.py` — 348 LOC · (undocumented)
- `utils/stress_test_harness.py` — 325 LOC · (undocumented)
- `utils/scalability_validator.py` — 329 LOC · (undocumented)
- `utils/cross_organ_event_bus.py` — 311 LOC · (undocumented)
- `utils/super_user_registry.py` — 417 LOC · (undocumented)
- `utils/notification_broadcaster.py` — 265 LOC · (undocumented)

## Module boundaries

- **Organ role**: Muscular & Movement System (branch ops · CIMS · SLA · EDMS · approvals · fraud · clearing · projects · procurement · vendors · assets · contracts · SWIFT)
- **Cross-organ links**: credit, compliance, finance, risk, admin, bsc, all_modules

## Architecture style

- Streamlit multipage app with API-first engines under `utils/`
- PostgreSQL via `utils/db` adapter where available
- React-readiness target: zero `unsafe_allow_html` excess + minimal raw HTML
- BSC integration via `_bsc_trigger()` hooks
- RBAC via `require_access()` gates
