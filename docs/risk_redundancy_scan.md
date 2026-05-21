# Risk Module — Redundant Components Scan

**Module key:** `risk` · **Organ role:** Immune System Primary (market risk · operational risk · RWA · stress testing · risk-based pricing)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 55.0%

Per Phase 1 Technical Health: detect duplicated logic, unused imports, or redundant pages.

---

## Page overlap analysis

- `82_oprisk.py` — 6 tabs
- `89_capital_risk_engines.py` — 0 tabs
- `125_chief_risk_centre.py` — 6 tabs

## Engine overlap

- Engines: 15
- Cross-engine reference check: pending dedicated scan

## Recommendations

- Consolidate where two engines compute the same KPI
- Merge stub pages into full-feature pages
