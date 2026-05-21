# CHANGELOG v10.182 — ENH-158 Target Service Level (TSL) Optimization Engine

## What this drop ships

Third standard of the Resource Optimization arc. Greenfield —
inspect-first showed no existing TSL/Erlang/queueing-theory code
in the repo. The platform's `cash_forecasting`, `workload_
forecasting` (just shipped at v10.181), and `rwa_optimization`
all sit upstream of this engine; none of them compute staffing
requirements from a service-level target.

`utils/tsl_optimization.py` (~430 LOC) computes the minimum
number of agents required to hit a target service level (e.g.
"80% of calls answered in 30 seconds") given forecast load and
average handle time, using Erlang C steady-state queueing math.

## Engine surface

- **Erlang math primitives** (free functions, exposed):
  - `erlang_b(traffic, agents)` — building block
  - `erlang_c_wait_probability(traffic, agents)` — P(wait > 0)
  - `service_level(traffic, agents, aht_seconds, threshold_
    seconds)` — fraction served within threshold
  - `required_agents(arrivals_per_hour, aht_seconds, target_
    pct, threshold_seconds, max_agents=500)` — smallest N
    meeting target

- **Domain types**:
  - `TSLChannelType` enum (CALL_CENTER, BRANCH_TELLER, BRANCH_
    BACK_OFFICE, DIGITAL_SUPPORT, EMAIL_QUEUE, OTHER)
  - `StaffingOutcome` enum (SHORTAGE, SURPLUS, EXACT)
  - `TSLTarget` frozen dataclass — channel + target_pct +
    threshold_seconds + aht_seconds, with input validation in
    `__post_init__`
  - `StaffingPlan` frozen dataclass — captures requested load,
    required vs planned agents, achieved SL with both staffings,
    outcome label, timestamp

- **Engine class** `TSLOptimizationEngine`:
  - `set_target() / get_target() / list_targets()`
  - `optimize_staffing(channel_key, arrivals_per_hour,
    planned_agents=None, max_agents=500)` — produces a
    StaffingPlan
  - `compare_scenarios(channel_key, arrivals_per_hour,
    candidate_targets, aht_seconds)` — read-only what-if for
    multiple TSL pairs against same load
  - `get_plan() / list_plans()`
  - `board_summary()` with regulatory_basis + 4 honest deferrals

## Erlang C math — textbook validation

Probe and tests verify the engine matches classical queueing
results:

| Configuration | Expected | Engine |
|---|---|---|
| 5 erlangs, 8 agents, 180s AHT, 20s threshold | SL ≈ 0.88 | 0.88 ✓ |
| 100 cph, 180s AHT → required for 80/20 | 8 agents | 8 ✓ |
| Traffic ≥ agents (unstable) | SL = 0 | 0 ✓ |
| Zero traffic, ≥1 agent | SL = 1 | 1 ✓ |
| Tighter target → ≥ agents required | monotonic | monotonic ✓ |

`test_classic_erlang_c_textbook` is the headline assertion
(asserts SL is within [0.85, 0.92] for the 5-erlang/8-agent/20s
case). Engine returns 0.880.

## Outcome labelling

`optimize_staffing(planned_agents=N)` produces:
- `SHORTAGE` when `planned < required` — and the actually-
  achieved SL is ALSO computed at planned headcount, so
  operators see the gap in both staffing units AND service-level
  units
- `SURPLUS` when `planned > required`
- `EXACT` when `planned == required` (or no planned passed)

This dual reporting matters: a 1-agent shortage in a 50-agent
team is operationally trivial; a 1-agent shortage in a 3-agent
team can crater the SL. The engine reports both views.

## Honest deferrals (named in `board_summary()`)

| Deferral | Reason |
|---|---|
| ABANDONMENT_MODELLING_ERLANG_A | Erlang C assumes infinite-patience queue. Real call centres see abandonment — Erlang A models that. Engine ships pure Erlang C. |
| SHRINKAGE_FACTOR_ROLLUP | Engine returns "agents on the phones." Caller adjusts for shrinkage (breaks, training, coaching) externally. |
| INTRADAY_INTERVAL_OPTIMIZATION | Engine returns hourly-equivalent staffing. 30-min interval re-staffing is out of v10.182 scope. |
| MULTI_SKILL_ROUTING | Single-skill agents only at v10.182. No overflow / skill-routing. |

The engine also exposes `model = "Erlang C (M/M/N steady-state)"`
in `board_summary()` so the model assumption is visible to
anyone reading the output.

## Tests — 27 across 9 classes

- `TestModuleShape` (1)
- `TestRegistry` (1) — ENH-158 active, batch v10.182
- `TestHubIntegration` (1)
- `TestErlangCMath` (8) — textbook example, monotonicity in
  agents, zero-traffic edge, unstable system, `required_agents`
  correctness, invalid target_pct (4 bad values), negative
  arrivals, zero AHT
- `TestTSLTarget` (4) — invalid pct (4 cases), negative
  threshold, zero AHT, empty channel key
- `TestEngineOptimize` (5) — plan creation, shortage outcome,
  surplus outcome, missing target rejection, zero load
- `TestScenarioComparison` (2) — per-target output shape,
  monotonicity in target_pct
- `TestHonestDeferrals` (2) — all 4 deferrals named, model
  string present
- `TestNoRegression` (3) — audit still 155/155, v10.181
  workload_forecasting still works, v10.180 work_mode_
  declaration still works

**27/27 PASS.**

## Apply order

1. `utils/tsl_optimization.py` — new engine
2. `utils/standards_registry.py` — ENH-158 active, batch v10.182
3. `pages/7_admin.py` — Tier 32 entry appended after ENH-157
4. `tests/test_tsl_optimization_v10_182.py` — 27 tests
5. Run `python scripts/audit.py` → 155/155 PASS

## Audit

`Score: 155/155 gates = 100.0% — PASS` (unchanged — engine drop,
not a closure ceremony).

## Resource Optimization arc roadmap

| Standard | Engine | Status |
|---|---|---|
| ENH-156 | work_mode_declaration | active (v10.180) |
| ENH-157 | workload_forecasting | active (v10.181) |
| ENH-158 | tsl_optimization | **active (v10.182)** |
| ENH-159 | (cross_channel_balancing) | planned |
| ENH-160 | (utilization_dashboard) | planned |
| ENH-161 | (wellbeing_burnout) | planned |
| ENH-162 | (whatif_scheduler) | planned |
| ENH-163 | (resource_investment_case) | planned |
| ENH-164 | (integrity_culture_score) | planned |
| ENH-165 | (executive_resource_dashboard) | planned |

Three standards down, seven to go before the Resource
Optimization arc closure ceremony at ~v10.190.
