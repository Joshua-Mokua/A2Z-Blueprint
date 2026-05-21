# CHANGELOG — v10.186

**Drop:** v10.186
**Standard:** ENH-162 — What-If Scenario Simulator for Hybrid Scheduling
**Module:** Resource Optimization
**Status:** active

---

## Summary

Seventh drop of the Resource Optimization arc. A read-only projection
engine that lets managers ask "what happens if I shift Team A to 60%
remote?" and get a deterministic answer that composes the prior six
drops in this arc — work-mode (ENH-156), forecasts (ENH-157), TSL
targets (ENH-158), balancing rules (ENH-159), utilisation bands
(ENH-160), and wellbeing-pressure proxies (ENH-161).

The engine refuses to invent a productivity penalty for remote work.
If the caller wants to model that, they pass a `ProductivityProfile`.
Without one, the engine defaults all factors to 1.0 and surfaces
`PRODUCTIVITY_DELTA_FROM_MODE` in the deferral list — operators are
told what assumption they're getting.

---

## Files added

- `utils/hybrid_scheduling_simulator.py` — engine (~430 LOC)
- `tests/test_hybrid_scheduling_simulator_v10_186.py` — 40 tests across
  12 classes

## Files modified

- `utils/standards_registry.py` — ENH-162 set to `status='active'`,
  `affected_engines=('hybrid_scheduling_simulator',)`,
  `implementation_batch='v10.186'`
- `pages/7_admin.py` — Tier 32 Resource Optimization Suite gains a seventh
  entry under `hybrid_scheduling_simulator`

## Audit gates

No new gates this drop (closure-tier gates G156/G157 land at v10.190 with
the arc closure ceremony). Audit holds at **155/155 PASS = 100.0%**.

---

## Engine surface

### Inputs

`HybridScenario`:
- `scenario_id`, `description`
- `team_assignments: Tuple[TeamAssignment, ...]`
- `productivity_profile: Optional[ProductivityProfile]`

`TeamAssignment`:
- `team_key`, `channel_key`
- `work_mode_mix: Tuple[Tuple[str, float], ...]` — must sum to 1.0
- `headcount`, `forecast_arrivals_per_hour`

`ProductivityProfile`: `remote_factor`, `hybrid_factor`, `onsite_factor`,
`field_factor` — all default to 1.0.

### Validation

Mix validation runs at projection time, not at scenario construction.
Three rules:

1. Mix must sum to 1.0 (within 1e-6)
2. Modes must be one of `REMOTE / HYBRID / ONSITE / FIELD`
3. Fractions must be non-negative
4. Mix must be non-empty

All four rules are enforced by tests.

### Outputs

`ScenarioProjection`:
- `team_projections: Tuple[TeamProjection, ...]`
- `n_teams_meeting_target` / `n_teams_with_target` — `None` when no
  TSL engine attached
- `n_teams_under_pressure` — count of teams with `wellbeing_pressure_flag`
- `aggregate_effective_headcount`
- `productivity_profile_supplied` — bool flag exposing the assumption

`TeamProjection` per team:
- `raw_headcount`, `effective_headcount` (raw × weighted productivity)
- `projected_sl` — Erlang C service level under projected staffing
  (None if no TSL target)
- `sl_target`, `meets_target`
- `utilization_band_projected` — proxy from offered-load / capacity
  ratio: `under_used` < 0.50, `balanced` < 0.85, `stretched` < 0.95,
  `breach` otherwise. Vocabulary matches ENH-160.
- `wellbeing_pressure_flag` — True when band ≥ stretched

### Composition

All optional. Engine constructor:

```python
HybridSchedulingSimulator(
    tsl_engine=None,        # ENH-158
    utilization_engine=None,  # ENH-160 (reserved for future use)
    balancing_engine=None,    # ENH-159 (reserved for future use)
)
```

If `tsl_engine` is attached and a target exists for the channel, the
engine computes Erlang C service level using the engine's own
`service_level()` primitive (same math as ENH-158). If no target, SL
fields stay `None`.

### Comparison

`compare(baseline, [alt1, alt2, ...])` runs every scenario and returns
a `ScenarioComparison` with per-alternative deltas:
- `effective_headcount_delta`
- `n_teams_under_pressure_delta`
- `n_teams_meeting_target_delta`

### Determinism

Same scenario in → same projection out. Tested explicitly. No
randomness, no timestamps fed into the math (the
`projected_at` ISO timestamp is the only non-deterministic field
and is not used in any downstream computation).

### Honest deferrals (declared in `board_summary()`)

1. **TRAVEL_TIME_REGRESSION** — no commute model. Onsite shifts
   ignore travel time entirely.
2. **PRODUCTIVITY_DELTA_FROM_MODE** — defaults to 1.0 across all
   modes unless caller supplies a `ProductivityProfile`. The engine
   refuses to invent productivity deltas — operator declares them.
3. **LIVE_WHATIF_DASHBOARD** — projection data only. Streamlit
   cockpit UI integration lands at the arc closure ceremony.
4. **MULTI_OBJECTIVE_OPTIMIZATION** — engine evaluates given
   scenarios. It does not search the scenario space for an optimum.

---

## Validation

### Tests

```
PASSED: 40 | FAILED: 0
```

Coverage spans:

- `TestModuleShape` — public surface (5 tests)
- `TestRegistry` — ENH-162 active and wired (3)
- `TestHubIntegration` — Tier 32 entry present + ordering (2)
- `TestMixValidation` — sum=1.0, unknown mode, negatives, empty (5)
- `TestEffectiveHeadcount` — math + multi-team aggregation (3)
- `TestTSLComposition` — none-when-absent, populated-when-attached,
  unknown-channel, zero-HC breach (4)
- `TestUtilizationBandProxy` — under_used / breach / stretched /
  balanced (4)
- `TestScenarioComparison` — single + multi alternative (2)
- `TestDeterminism` — same input same output (1)
- `TestEdgeCases` — empty teams, JSON round-trip (2)
- `TestHonestDeferrals` — all 4 deferrals + reg-basis +
  productivity-flag (3)
- `TestNoRegression` — ENH-156..161 still active (6)

### Audit

```
Score: 155/155 gates = 100.0% — PASS
```

---

## What this unlocks

ENH-163 (Resource Investment Case Generator) is the next drop. It will
consume scenario projections from this engine and turn them into a
business-case package: NPV, payback, headcount cost delta, expected SL
improvement — the artefact that goes into a board paper.

---

## Notes

- Engine is pure Python deterministic. No solver, no ML, no scipy.
- Service-level math reuses `utils.tsl_optimization.service_level` —
  no duplication of Erlang C.
- The utilisation band proxy uses a nominal AHT of 180s when no TSL
  target is available. This is a coarse projection, not a substitute
  for ENH-160 once observations roll in.
- Regulatory basis: Internal Hybrid Work Framework + BSC People+Customer
  + Kenya Employment Act §10.
