# CHANGELOG v10.178 — ENH-230 Legal Analytics & Reporting

**Status:** ENH-230 active. **All 9 of 9 Legal arc standards complete.** Audit 153/153 PASS unchanged. 28/28 tests pass.

## What this drop ships

`utils/legal_analytics.py` (~570 LOC) — analytics rollup engine over the 8 prior Legal arc engines (ENH-222..229). Fulfills the `TREND_ANALYSIS` deferral surfaced by ENH-228 dashboard. **This is the last engine before the closure ceremony in v10.179.**

### KPI catalogue — 10 deterministic metrics

| KPI                            | Source     | Higher is better |
|--------------------------------|------------|------------------|
| matter_close_rate              | ENH-223    | yes              |
| matter_critical_open_rate      | ENH-223    | no               |
| spend_budget_utilization       | ENH-225    | no               |
| counsel_active_rate            | ENH-224    | yes              |
| obligation_compliance_rate     | ENH-222    | yes              |
| hold_acknowledgment_rate       | ENH-227    | yes              |
| clause_governance_rate         | ENH-226    | yes              |
| document_privilege_rate        | ENH-229    | yes              |
| document_purgeable_rate        | ENH-229    | yes              |
| discovery_response_open        | ENH-229    | no (count)       |

`obligation_compliance_rate` reads `alert_counts["BREACHED"]` from the obligation engine, **not** `n_breached` (the formal status counter). Alerts are deadline-derived in real time; the formal status counter only moves on operator-driven workflows. The KPI uses the more reliable signal and the comment in the source says so.

Each KPI carries `higher_is_better` flag for direction-aware composition. The composite `portfolio_health_score` averages percentage KPIs only (count KPIs excluded), inverting "lower is better" KPIs before averaging — examiner-reproducible math.

### Trend computation

The engine accepts an optional `prior_snapshot: Dict[str, float]` — a flat `{name: value}` dict from a previous snapshot. Each KPI compares current vs prior and classifies trend as IMPROVING / STABLE / DETERIORATING / INSUFFICIENT_DATA with a 1-percentage-point stability band. When `prior_snapshot` is None, every trend is honestly INSUFFICIENT_DATA.

`snapshot_to_dict()` flattens current snapshot for re-use as next period's `prior_snapshot` input — no auto-persistence (operator-side responsibility).

### Report kinds — 4 types

- **KPI_SNAPSHOT** — one-shot view with all 10 KPIs + efficiency metrics
- **TREND_ANALYSIS** — KPI deltas vs prior_snapshot; returns `REPORT_INSUFFICIENT` outcome if no prior supplied
- **EFFICIENCY_REPORT** — derived efficiency metrics (spend per matter, assignments per counsel)
- **COMPLIANCE_PROFILE** — cross-engine compliance posture

### Efficiency metrics

- `spend_per_matter_by_currency` — cross-engine ENH-223 + ENH-225 ratio
- `assignments_per_counsel` — ENH-224 derived ratio

When source engines are unavailable, efficiency metrics return `"UNAVAILABLE — needs ENH-XXX"` strings rather than fabricated zeros.

## Honest deferrals (named in board_summary)

- **ML_PREDICTIVE_MODELING** — no outcome prediction, deterministic ratios only
- **OPPOSING_COUNSEL_DATABASE** — engine has no opposing-counsel data; ENH-224 tracks OUR counsel
- **BENCHMARK_COMPARISONS** — industry benchmarks operator-side
- **NATURAL_LANGUAGE_QUERY**
- **VISUALIZATION_RENDERING** — chart libraries cockpit-side
- **DRILLDOWN_NAVIGATION** — cockpit-side
- **TIME_SERIES_PERSISTENCE** — engine accepts prior_snapshot; auto-persistence is operator-side

## Tests — 28 across 14 classes

- TestModuleShape (6) — 5 enums + dataclass exports + counts
- TestRegistry (1) — ENH-230 active
- TestHubIntegration (1) — Tier 31 entry
- TestEmptyEngines (2) — all None unavailable + partial_data flag
- TestAllWired (2) — full wiring + reasonable health score
- TestBreachedObligationDropsScore (1) — alert_counts driven KPI
- TestTrendComputation (4) — IMPROVING / DETERIORATING / INSUFFICIENT_DATA / no-prior
- TestSnapshotRoundTrip (1) — flatten round-trip
- TestReportKinds (2) — KPI_SNAPSHOT + EFFICIENCY_REPORT shape
- TestPortfolioHealth (2) — None when empty + direction-aware
- TestEfficiency (1) — unavailable strings
- TestHonestDeferrals (1) — all 7 deferral surfaces named
- TestPortfolioSummary (1) — engine name + basis
- TestNoRegression (3) — ENH-228 + ENH-229 + ENH-227 untouched

## Apply order

1. `utils/legal_analytics.py` → `utils/`
2. `utils/standards_registry.py` (ENH-230 activation, removed orphan duplicate fragment)
3. `pages/7_admin.py` (Tier 31 hub entry)
4. `tests/test_legal_analytics_v10_178.py` → `tests/`
5. `CHANGELOG_v10.178.md` → root

`python scripts/audit.py` reports `Score: 153/153 gates = 100.0% — PASS`.

## Legal arc — final scoreboard

| Std     | Engine                       | Batch    |
|---------|------------------------------|----------|
| ENH-221 | (META_ONLY)                  | prior    |
| ENH-222 | obligation_tracking          | v10.170  |
| ENH-223 | legal_case_management        | v10.171  |
| ENH-224 | outside_counsel_portal       | v10.172  |
| ENH-225 | legal_spend_management       | v10.173  |
| ENH-226 | clause_library               | v10.174  |
| ENH-227 | legal_hold_management        | v10.175  |
| ENH-228 | legal_dashboard              | v10.176  |
| ENH-229 | legal_document_management    | v10.177  |
| ENH-230 | legal_analytics              | v10.178  |

8 fully-engineered standards + 1 META_ONLY (ENH-221 contract review).

## Next

**v10.179 LEGAL MODULE CLOSURE CEREMONY** — final drop in the Legal arc.

- `pages/28_legal_arc_cockpit.py` — module cockpit with ≤7 G4-compliant tabs covering all 9 standards
- `utils/api_legal.py` — module API with cross-engine `/board` endpoint + per-engine endpoints + JWT auth via `Depends(get_current_user)` + audit logging
- `pages/7_admin.py` Tier 4E — Legal Arc Closure marker
- `scripts/audit.py` G154 (`legal_module_closed`) + G155 (`legal_arc_ui_integrated`) audit gates
- `app.py` cockpit page registration
- `tests/test_legal_arc_closure_v10_179.py` — closure ceremony tests

Audit will move from 153/153 to 155/155 after the closure.
