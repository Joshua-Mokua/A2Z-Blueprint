# Operations Module — Redundant Components Scan

**Module key:** `operations` · **Organ role:** Muscular & Movement System (branch ops · CIMS · SLA · EDMS · approvals · fraud · clearing · projects · procurement · vendors · assets · contracts · SWIFT)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 50.0%

Per Phase 1 Technical Health: detect duplicated logic, unused imports, or redundant pages.

---

## Page overlap analysis

- `13_sla.py` — 7 tabs
- `14_branch_log.py` — 7 tabs
- `18_cims.py` — 7 tabs
- `30_rms.py` — 6 tabs
- `31_edms.py` — 6 tabs
- `37_approvals.py` — 4 tabs
- `44_incidents.py` — 5 tabs
- `51_agency_banking.py` — 4 tabs
- `59_cab.py` — 5 tabs
- `61_projects.py` — 6 tabs
- `62_p2p.py` — 6 tabs
- `63_assets.py` — 6 tabs
- `64_vendors.py` — 6 tabs
- `65_contracts.py` — 4 tabs
- `67_fraud.py` — 6 tabs
- `68_clearing.py` — 7 tabs
- `99_swift_cockpit.py` — 0 tabs
- `105_cims_capture.py` — 0 tabs
- `106_cims_process.py` — 0 tabs
- `107_cims_compliance.py` — 0 tabs
- `108_cims_closure.py` — 0 tabs
- `109_cims_live.py` — 0 tabs

## Engine overlap

- Engines: 6
- Cross-engine reference check: pending dedicated scan

## Recommendations

- Consolidate where two engines compute the same KPI
- Merge stub pages into full-feature pages
