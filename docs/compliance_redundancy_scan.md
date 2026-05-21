# Compliance Module — Redundant Components Scan

**Module key:** `compliance` · **Organ role:** Immune System Antibodies (KYC · AML · CBK returns · sanctions · tax · regulatory reporting · IRA insurance)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 60.0%

Per Phase 1 Technical Health: detect duplicated logic, unused imports, or redundant pages.

---

## Page overlap analysis

- `24_compliance.py` — 6 tabs
- `74_cbk_returns.py` — 7 tabs
- `76_sanctions.py` — 6 tabs
- `103_compliance_dashboard.py` — 0 tabs
- `107_cims_compliance.py` — 0 tabs
- `112_compliance_live.py` — 0 tabs
- `126_compliance_centre.py` — 6 tabs

## Engine overlap

- Engines: 21
- Cross-engine reference check: pending dedicated scan

## Recommendations

- Consolidate where two engines compute the same KPI
- Merge stub pages into full-feature pages
