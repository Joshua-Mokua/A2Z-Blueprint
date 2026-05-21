# CHANGELOG v10.176 — ENH-228 Legal Dashboard

**Status:** ENH-228 active. 7 of 9 Legal arc standards complete. Audit 153/153 PASS unchanged. 30/30 tests pass.

## What this drop ships

`utils/legal_dashboard.py` (~430 LOC) — cross-engine cockpit composition for the Legal arc. Pulls `board_summary()` from the 6 source engines (ENH-222..227) and produces a unified GC-level Legal Health Score 0-100 with EXCELLENT/GOOD/CONCERNING/CRITICAL banding (mirrors ENH-198 compliance risk categorisation).

### Composition design — 4 enums + 2 frozen dataclasses

- `HealthBand` (4): EXCELLENT 85-100 / GOOD 70-84 / CONCERNING 50-69 / CRITICAL 0-49
- `DashboardSection` (7): CONTRACTS / MATTERS / SPEND / OBLIGATIONS / HOLDS / COUNSEL / CLAUSES
- `AlertSeverity` (4): LOW / MEDIUM / HIGH / CRITICAL — inverse of health for heatmap
- `DataAvailability` (3): FULL / PARTIAL / UNAVAILABLE — honest tracking when source engines fail
- `SectionView` frozen dataclass: section + availability + health + severity + headline + raw
- `DashboardComposition` frozen dataclass: timestamp + overall + band + sections + counts + divisor

### Per-section health rollup — examiner-reproducible math

```
obligations_health = (n_total - CRITICAL - BREACHED) / n_total × 100
matters_health     = (n_total - n_critical_open) / n_total × 100
spend_health       = (n_budgets_total - n_at_or_over_limit) / n_budgets_total × 100
holds_health       = (n_acks_total - n_overdue) / n_acks_total × 100
counsel_health     = n_active / n_total × 100
clauses_health     = n_playbooks_published / n_playbooks_total × 100

overall_health     = mean(usable sections)   # excludes UNAVAILABLE
```

Equal weighting across 6 sections. No ML/heuristic black boxes — regulator-explainable.

### Honest data availability

When a source engine is `None` or its `board_summary()` raises, the section is marked `UNAVAILABLE` and **excluded from the average** rather than reporting fabricated zeros. The `divisor` field documents how many sections actually contributed. `partial_data` flag flips True if any section is missing.

This matters: a regulator looking at the dashboard sees `divisor: 5` and `partial_data: true` and knows one engine is dead, not that the score genuinely averaged six zeros.

### Risk heatmap — 7 cells

Composes `CONTRACTS` (hard-coded MEDIUM until ENH-221 grows an engine — currently META_ONLY) plus the 6 section severities. Severity inverts health: LOW (≥85) / MEDIUM (≥70) / HIGH (≥50) / CRITICAL (<50).

## Honest deferrals (named in board_summary)

- **REAL_TIME_REFRESH** — caching/streaming is operator-side
- **TREND_ANALYSIS** — DEFERRED to ENH-230 (analytics arc, next drop after ENH-229)
- **DOCUMENT_REPOSITORY_HEALTH** — DEFERRED to ENH-229 (document management, next drop)
- **CUSTOMIZABLE_WIDGETS** — UI personalization operator-side
- **DRILL_DOWN_LINKS** — cockpit navigation operator-side

## Tests — 30 across 11 classes

- TestModuleShape (5) — 4 enums + dataclass exports
- TestRegistry (1) — ENH-228 active with `affected_engines=("legal_dashboard",)`
- TestHubIntegration (1) — Tier 31 entry exists
- TestEmptyEngineWiring (3) — all None → CRITICAL / 6 unavail / heatmap intact
- TestFullEngineWiring (2) — all wired empty → 100/EXCELLENT
- TestObligationsHealthDrop (1) — 3 of 4 ok → 75/MEDIUM
- TestBrokenEngineHandling (2) — RuntimeError + non-dict both → UNAVAILABLE
- TestHealthBanding (4) — 4 thresholds verified
- TestSeverityFromHealth (2) — health → severity inversion
- TestHonestDeferrals (1) — all 5 deferral surfaces named
- TestPortfolioSummary (2) — engine name + UTC ISO timestamp
- TestNoRegression (6) — ENH-222 through ENH-227 still report correctly

## Apply order

1. `utils/legal_dashboard.py` → `utils/`
2. `utils/standards_registry.py` (ENH-228 activation)
3. `pages/7_admin.py` (Tier 31 hub entry)
4. `tests/test_legal_dashboard_v10_176.py` → `tests/`
5. `CHANGELOG_v10.176.md` → root

`python scripts/audit.py` reports `Score: 153/153 gates = 100.0% — PASS`.

## Next

**v10.177 ENH-229 Legal Document Management** — centralized repository, version control, retention, e-discovery surface. Wires existing `utils/document_management.py` for Legal-specific use. After that: **v10.178 ENH-230 Legal Analytics & Reporting** — analytics rollup. Then **v10.179 LEGAL MODULE CLOSURE CEREMONY** — G154 + G155 audit gates locking the 9-standard arc.

8 standards complete after this drop. 1 + closure to go before AML/Compliance gets a sibling Phase 4 module closure.
