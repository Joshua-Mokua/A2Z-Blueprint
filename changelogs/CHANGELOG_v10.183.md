# CHANGELOG v10.183 — ENH-159 Cross-Channel Resource Balancing Engine

## What this drop ships

Fourth standard of the Resource Optimization arc and the first
**integration layer** of this arc — sits downstream of ENH-157
(workload forecasts) and ENH-158 (TSL targets), composing them
to produce concrete agent-shift recommendations across channels.

`utils/cross_channel_balancing.py` (~340 LOC) takes a list of
`ChannelInput` records (forecast load, planned agents, allowable
transfer destinations, optional minimum-floor) and produces a
`BalanceRecommendation` with per-channel outcomes and batched
`AgentShift` records.

## Engine surface

- `BalanceOutcome` enum — SHORTAGE_RESOLVED / SHORTAGE_PARTIAL /
  SHORTAGE_UNRESOLVED / SURPLUS_GIVING / BALANCED
- Three frozen dataclasses with `to_dict()`:
  - `ChannelInput` — input contract with construction-time
    validation
  - `AgentShift` — proposed move (from, to, n_agents, rationale)
  - `ChannelOutcome` — post-rebalance per-channel record with
    initial/final agents, initial/final gap, initial/final SL
  - `BalanceRecommendation` — full plan with timestamp
- `CrossChannelBalancingEngine`:
  - constructor takes a `TSLOptimizationEngine` (composition,
    not inheritance)
  - `balance(channels: List[ChannelInput]) -> BalanceRecommendation`
  - `get_recommendation()` / `list_recommendations()`
  - `board_summary()` with regulatory_basis + algorithm name +
    4 honest deferrals

## Algorithm

1. Compute per-channel `required_agents` via Erlang C (delegates
   to `utils.tsl_optimization.required_agents`)
2. Compute `sl_initial` at planned headcount (delegates to
   `utils.tsl_optimization.service_level`)
3. Sort shortage channels by gap descending (worst first)
4. Greedy: for each shortage, find best donor — a channel that
   - lists this recipient in its `transferable_to` tuple, AND
   - would still meet its own `required_agents` after giving 1, AND
   - would still respect its `min_agents_after_giving` floor
5. Among eligible donors, pick the one with biggest post-shift
   surplus (greedy)
6. Move 1 agent at a time until shortage resolved or no donor
7. Coalesce 1-by-1 shifts from same (from, to) into batched
   `AgentShift` records
8. Compute `sl_final` at post-shift headcount, label outcomes

## Idempotence

Same inputs → same shifts. The greedy is fully deterministic:
shortage ranking is stable-sorted by gap, donor ranking is
stable-sorted by post-shift surplus. Test
`TestIdempotence.test_same_input_same_shifts` verifies.

## Honest deferrals (named in `board_summary()`)

| Deferral | Reason |
|---|---|
| REAL_TIME_SKILLS_MATRIX | No HRIS skills feed integrated; caller declares `transferable_to` lists explicitly per channel |
| AUTO_REBALANCE_TRIGGER | No scheduled / event-triggered re-balancing; caller invokes `balance()` manually |
| COST_OPTIMIZED_LP_SOLVER | Greedy heuristic only — no LP/MILP optimisation across cost+SL+shift constraints. The standard's name suggests "optimization" but at v10.183 it's a heuristic with the LP swap-in deferred. |
| SKILL_DECAY_MODEL | No model of skill atrophy when agent is moved away from primary channel for extended periods |

The `algorithm` field in `board_summary()` reads "greedy
shortage-first heuristic" so operators see the method, not just
the deferral list.

## Tests — 23 across 11 classes

- `TestModuleShape` (1)
- `TestRegistry` (1) — ENH-159 active, batch v10.183
- `TestHubIntegration` (1)
- `TestChannelInputValidation` (4) — empty key, negative
  arrivals, negative agents, negative min floor
- `TestEngineConstruction` (1) — None TSL engine rejected
- `TestBalanceCore` (5) — empty channels reject, duplicate
  reject, missing TSL reject, simple shortage resolved,
  unresolved when no transferability, balanced when adequate
- `TestTransferability` (2) — shifts only when transferable,
  min_agents_after_giving floor respected
- `TestIdempotence` (1) — same input, same shifts
- `TestShiftCoalescing` (1) — 1-by-1 shifts merged
- `TestRecommendationQueries` (2) — get returns None for
  unknown, list chronological
- `TestHonestDeferrals` (1) — all 4 deferrals named, algorithm
  string present
- `TestNoRegression` (2) — audit still 155/155, v10.182 TSL
  still works

**23/23 PASS.**

## Apply order

1. `utils/cross_channel_balancing.py` — new engine
2. `utils/standards_registry.py` — ENH-159 active, batch v10.183
3. `pages/7_admin.py` — Tier 32 entry appended after ENH-158
4. `tests/test_cross_channel_balancing_v10_183.py` — 23 tests
5. `python scripts/audit.py` → 155/155 PASS

## Resource Optimization arc roadmap

| Standard | Engine | Status |
|---|---|---|
| ENH-156 | work_mode_declaration | active (v10.180) |
| ENH-157 | workload_forecasting | active (v10.181) |
| ENH-158 | tsl_optimization | active (v10.182) |
| ENH-159 | cross_channel_balancing | **active (v10.183)** |
| ENH-160 | (utilization_dashboard) | planned |
| ENH-161 | (wellbeing_burnout) | planned |
| ENH-162 | (whatif_scheduler) | planned |
| ENH-163 | (resource_investment_case) | planned |
| ENH-164 | (integrity_culture_score) | planned |
| ENH-165 | (executive_resource_dashboard) | planned |

Four standards active. The arc's compositional structure is
solidifying: ENH-157 produces forecasts → ENH-158 produces
required staffing → ENH-159 reconciles supply vs demand across
channels. ENH-160 (utilization dashboard) will surface the
post-balance state to managers.
