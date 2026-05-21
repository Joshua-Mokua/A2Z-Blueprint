# Treasury Module — Redundant Components Scan

**Module key:** `treasury` · **Organ role:** Cash Flow Reservoir & Arterial Blood Pressure (ALM · FTP · FX · liquidity · market risk · VAR)
**Generated:** 2026-05-15 (v10.453 doctrine doc generator)
**Honest health at v10.452:** 60.0%

Per Phase 1 Technical Health: detect duplicated logic, unused imports, or redundant pages.

---

## Page overlap analysis

- `25_treasury.py` — 0 tabs
- `110_treasury_live.py` — 0 tabs
- `123_head_treasury_centre.py` — 6 tabs

## Engine overlap

- Engines: 21
- Cross-engine reference check: pending dedicated scan

## Recommendations

- Consolidate where two engines compute the same KPI
- Merge stub pages into full-feature pages
