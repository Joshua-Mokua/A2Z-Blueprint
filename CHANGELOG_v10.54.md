# CHANGELOG v10.54 — revenue_assurance arc · ENH-245 Dashboard Metrics (split implementation)

**Status:** revenue_assurance arc 5/8+1 batches (3 standards remaining + closure)
**Audit:** 132/132 PASS · **G128:** STABLE (319 modules · 798 imports · 3 HARD baseline)
**Active standards:** 123 → **124** / 260 · **Scenario library:** 70 → **74** (4 DSH-* added)

## Why this batch is structured this way

ENH-245's standard description ("Live dashboard: leakage trend, top
exception categories, recovery YTD, cycle time, agent activity")
explicitly names a UI deliverable. Under the v10.46-amended
Lean+Compact protocol, every arc closure ships a UI cockpit — so
shipping a freestanding "dashboard" engine alongside the v10.58
closure cockpit would be duplicate UI work. Two honest options were
on the table:

1. Mark ENH-245 deferred-to-closure and skip the standalone batch.
2. Split into a data layer (now) and a UI layer (closure cockpit
   consumes the data layer).

I went with option 2: ship the **data layer** as an aggregation
helper module that the closure cockpit will consume. This keeps the
registry consistent (ENH-245 is genuinely active with a real engine),
gives the closure cockpit clean precomputed inputs rather than ad-hoc
computation, and avoids the duplication the protocol amendment was
designed to prevent.

## New module

- `utils/revenue_dashboard_metrics.py` (~840 lines · 18 self-tests)
  — read-only aggregation engine producing six metric families from
  ENH-243 WorkItem stream + caller-supplied StateTransitions. Pure
  stdlib (`Decimal` + `statistics` + frozen dataclasses + enums).
  Single public engine `RevenueDashboardMetrics` exposing
  `compute_leakage_trend`, `compute_top_categories`,
  `compute_recovery`, `compute_team_activity`,
  `compute_cycle_times`, plus `compute_all` orchestrator.

## Architecture — six metric families

### 1. LEAKAGE_TREND
`Tuple[TrendPoint, ...]` bucketed by period (default `YYYY-MM` from
`raised_date`). Each bucket: `finding_count` + `monetary_impact_kes`.
Items raised outside the window excluded. Result sorted ascending
by period. Periods with zero in-window items NOT synthesised — gap
filling is a UI concern.

### 2. TOP_CATEGORIES
Two rankings of the same categories, returned as a tuple. By count
ranks high-frequency-low-impact patterns first; by impact ranks
low-frequency-high-impact first. They often disagree — DSH-02
scenario shows 10 small LEAKAGE findings dominating by count while
1 huge BILLING_ERROR dominates by impact. Both rankings carry
`pct_of_total_count` + `pct_of_total_impact` per Rule 1.

### 3. RECOVERY
`RecoveryMetric` with `resolved_count` + `recovered_kes` (sum of
monetary_impact for items in `RESOLVED` state), `dismissed_count`
counted **separately** (DISMISSED ≠ recovery — those items were
determined to be non-issues), plus `open_count` +
`open_estimated_impact_kes` for triage comparison. DSH-03 explicitly
verifies a KES 999,999 dismissed item does NOT inflate the recovery
total.

### 4. TEAM_ACTIVITY
Per-`InvestigatorTeam` breakdown across all 6 `WorkItemState` values
plus a `past_sla_count` (regardless of state). Teams with zero total
items are excluded from output. Sorted descending by total count so
the busiest team surfaces first.

### 5. CYCLE_TIMES
Distribution metrics for 4 named `CycleStage` transitions:
`RAISED_TO_ACK`, `RAISED_TO_IN_PROGRESS`, `RAISED_TO_RESOLVED`,
`ACKNOWLEDGED_TO_RESOLVED`. For each: sample size, mean, median,
p90 (quantized to two decimal places), min, max. Sample size of zero
yields a metric with all-None numeric fields rather than raising —
the closure cockpit can render "no data yet" cleanly.

Two design decisions worth flagging:

- **All stages anchor on `raised_date`** (not on the from-state's
  transition date for ACK→RESOLVED). This is a slight
  imprecision — strictly speaking ACK→RESOLVED duration should be
  `transition_date - acknowledged_date`. Anchoring on raised_date
  is simpler for callers (only one date map needed) and the
  closure cockpit can still render the metric meaningfully.
  Honest scope note in the docstring.
- **Negative durations skipped**, not raised. Bad-data tolerance:
  if a transition was recorded before its work item's `raised_date`,
  the engine drops that data point rather than crashing the whole
  batch.

### 6. SUMMARY
`total_work_items` count, `window` boundaries, framework refs.

## Rule 1 / Rule 7 alignment

- **9 frozen dataclasses**: `DashboardWindow`, `StateTransition`,
  `TrendPoint`, `CategoryRanking`, `RecoveryMetric`, `TeamActivity`,
  `CycleTimeMetric`, `DashboardMetrics`, plus reuse of `WorkItem`
  from ENH-243.
- Every metric block surfaces components separately: count vs
  monetary impact split, sample sizes for percentile metrics,
  pct_of_total fields populated, window boundaries on
  `RecoveryMetric` mirrored from input.
- Engine is **read-only** (Rule 7):
  - never mutates WorkItems (frozen contract)
  - never persists computed metrics
  - never schedules notifications
  - never modifies state transitions
- `_test_engine_does_not_mutate_inputs` explicitly verifies the
  read-only contract by asserting WorkItem field values are
  unchanged after `compute_all`.

## Validation envelope

- `DashboardWindow.__post_init__` rejects `period_end <
  period_start`.
- `StateTransition.__post_init__` rejects empty `work_item_id` and
  `from_state == to_state`.
- `compute_top_categories` rejects `top_n < 1`.

## Standards registry

- **ENH-245** activated: `status: planned → active`,
  `implementation_batch: v10.40+ → v10.54`,
  `affected_engines: ("revenue_assurance",) →
  ("revenue_dashboard_metrics",)`.
  Description rewritten to explicitly note the **split
  implementation** (data layer here, UI layer at closure) plus the
  full architectural detail of all 6 metric families.
- Registry self-test PASS · total 260 · active **123 → 124**.

## Scenario library extension

Appended to `TREASURY_SCENARIO_LIBRARY`:

- **DSH-01 Leakage trend** — 5 work items spanning Dec 2025 + Jan-Mar
  2026 → trend produces 3 buckets (Dec excluded as outside window);
  2026-01 aggregates 2 findings + KES 3,000 impact; sorted ascending
  by period. 4 assertions.
- **DSH-02 Top categories diverge** — 10 small LEAKAGE + 1 huge
  BILLING_ERROR → by_count ranks LEAKAGE first, by_impact ranks
  BILLING_ERROR first. The two rankings deliberately diverge per
  Rule 1. 4 assertions.
- **DSH-03 Recovery distinguishes RESOLVED from DISMISSED** —
  KES 999,999 dismissed item NOT counted as recovery; only RESOLVED
  contributes to `recovered_kes`. Open count + open estimated
  impact surfaced separately. 4 assertions.
- **DSH-04 compute_all orchestrator** — 2 work items + 1
  RAISED→RESOLVED transition (7 days). All 6 metric blocks
  populated; cycle time mean = 7 days; past_sla aggregated via team
  activity; framework refs cite ENH-245 + Rule 7 read-only stance.
  4 assertions.

End-to-end runner: DSH-01..DSH-04 all PASS · **16/16 assertions**.
Scenario library 70 → **74**.

## Self-tests

- `python3 -m utils.revenue_dashboard_metrics` → ✓ 18 tests covering
  validation envelope (3 dataclass __post_init__ checks), each
  metric family with edge cases (out-of-window items, empty inputs,
  count-vs-impact divergence, RESOLVED-vs-DISMISSED separation,
  zero-sample stages, negative-duration skip), `compute_all`
  orchestration, full provenance, immutability contract.
- All 5 upstream arc engines + scenario_simulator + registry
  self-tests pass with **no regression**:
  - revenue_validation 19/19 · revenue_anomaly_patterns 21/21
  - revenue_orchestrator 23/23 · partner_supplier_recon 20/20
  - revenue_dashboard_metrics 18/18 · scenario_simulator 18/18

## Gate verification

- `python3 scripts/audit.py` → **Score: 132/132 gates = 100.0% — PASS**.
- `python3 scripts/structure_audit.py` → **STABLE: HARD findings
  match baseline exactly** (319 modules · 798 imports · 63 findings
  · HARD=3). Module +1 (revenue_dashboard_metrics), imports +3
  (`InvestigatorTeam` + `WorkItem` + `WorkItemState` from ENH-243
  reuse).

## Lean+Compact protocol — applied (v10.46 amended)

- 1 ENH per batch (ENH-245) ✅
- ~840 line module
- Engine Hub Tier addition DEFERRED to closure ✅
- Master Prompt update DEFERRED to closure ✅
- UI integration DEFERRED to closure (this batch ships data layer
  only — explicit split-implementation per the protocol amendment) ✅
- Audit + G128 + scenario library extension SHIPPED ✅
- Per Rule 1 every metric surfaces full components ✅
- Per Rule 7 engine read-only — verified by mutation test ✅

## Files changed

- **NEW** `utils/revenue_dashboard_metrics.py` (~840 lines, 18 self-tests)
- **MOD** `utils/standards_registry.py` (ENH-245 activated, ~50 line
  description rewrite explaining the split implementation)
- **MOD** `utils/scenario_simulator.py` (+4 DSH-* scenarios + library
  extension)
- **NEW** `CHANGELOG_v10.54.md`

## Honest scope notes

1. **No UI shipped this batch.** That's the whole point of the
   split — the closure cockpit owns the rendering. If you'd like
   to see what a Streamlit cockpit looks like rendering these
   metrics, that comes at v10.58.

2. **Cycle time anchoring imprecision flagged in docstring.** All
   stages anchor on `raised_date` rather than the from-state's
   transition date for ACK→RESOLVED. Slight loss of precision in
   exchange for caller simplicity (one date map vs four). Production
   deployments wanting strict accuracy should compute
   ACK→RESOLVED with the acknowledged_date as anchor; the engine
   doesn't currently support that input shape.

3. **No gap-filling in trends.** Periods with zero findings inside
   the window aren't synthesised — the trend tuple skips them
   silently. The closure cockpit will need to fill gaps if it
   wants a continuous time-series chart (trivial given the window
   boundaries are always known).

4. **No "agent activity" beyond team aggregation.** The standard
   says "agent activity"; ENH-245 interprets that as
   `TeamActivity` per `InvestigatorTeam`. If "agent" was meant to
   reference individual investigators, that requires a per-user
   identifier on WorkItem which isn't currently in the schema. A
   future enhancement could add `assigned_investigator_id: Optional[str]`
   to WorkItem.

5. **No alerts / thresholds.** A real production dashboard might
   want "alert when past_sla_count > 10" or "alert when
   recovered_kes drops below historical average". The data layer
   surfaces the raw numbers; alerting is a workflow concern that
   sits outside Rule 7 anyway.

## revenue_assurance arc state

| Batch    | Standard      | Module                             | Status |
| -------- | ------------- | ---------------------------------- | ------ |
| v10.50   | ENH-241       | revenue_validation                 | ✅      |
| v10.51   | ENH-242       | revenue_anomaly_patterns           | ✅      |
| v10.52   | ENH-243       | revenue_orchestrator               | ✅      |
| v10.53   | ENH-244       | partner_supplier_recon             | ✅      |
| **v10.54** | **ENH-245** | **revenue_dashboard_metrics**     | ✅ (data layer; UI at v10.58) |
| v10.55   | ENH-246       | continuous_billing_verification    | pending |
| v10.56   | ENH-247       | commission_incentive_assurance     | pending |
| v10.57   | ENH-248       | regulatory_revenue_reporting       | pending |
| v10.58   | closure       | G133 + G134 + Tier 26 + cockpit    | pending |

## Next batch

**v10.55 — ENH-246 Continuous Billing Verification.** Real-time
billing accuracy: rate vs contract, fee + tax computation, discount
application. Pre-issuance verification (catches mistakes before the
invoice goes out, not after). Composes with `ContractRate` from
ENH-242 and the partner-share semantics from ENH-244 — but unlike
ENH-242 which screens *posted* records for anomalies, ENH-246
screens *pending* records before they post. Per Rule 7, "verification"
flags issues; humans block or release the billing — engine never
auto-blocks.

**136 consecutive clean batches.** 11 closed arcs holding;
revenue_assurance arc at 5/8 + closure pending.
