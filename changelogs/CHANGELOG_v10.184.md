# CHANGELOG v10.184 — ENH-160 Real-Time Utilization Dashboard

## What this drop ships

Fifth standard of the Resource Optimization arc. Greenfield —
inspect-first found 7 dashboard modules in `utils/`, all module-
specific (audit, finance, legal, ops, product, revenue,
treasury); none aggregate workforce utilization.

`utils/utilization_dashboard.py` (~340 LOC) is the **data layer**
for a manager-facing utilization dashboard. It is not a UI — UI
integration lives in the cockpit at arc closure (~v10.190). The
engine ingests `UtilizationObservation` records and emits
classified `UtilizationSnapshot` records with optional service-
level enrichment.

## Engine surface

- `UtilizationBand` enum: UNDER_USED < BALANCED < STRETCHED <
  BREACH (default thresholds 0.50 / 0.85 / 0.95, configurable
  per engine instance with strict ordering validation)
- Frozen dataclasses with `to_dict()`:
  - `UtilizationObservation` — channel/team/manager,
    agents_available/busy, optional load data, observed_at
  - `UtilizationSnapshot` — derived from observation, includes
    band classification + optional TSL enrichment fields
  - `TeamRollup` — team-level aggregation
- `UtilizationDashboardEngine`:
  - constructor takes optional `tsl_engine` (composition with
    ENH-158 for SL enrichment)
  - `submit_observation()` — append + derive snapshot
  - `list_snapshots(manager_id=, team_key=, channel_key=)` —
    privacy-aware filter
  - `latest_per_channel(manager_id=)` — most recent per
    (channel, team) pair
  - `team_rollup(team_key, manager_id=)` — team-level aggregation
  - `list_breaches(manager_id=)` — current BREACH-band channels
  - `board_summary()` with regulatory_basis + 4 honest deferrals

## Privacy by design

Per ENH-156's manager-only-sees-own-team principle, every query
accepts an optional `manager_id` parameter. When present, results
are scoped to snapshots whose `manager_id` matches. Without the
parameter, the engine returns full data — caller is responsible
for handling that case (e.g., HR_ADMIN role gating in the UI).

Test `TestPrivacyFilter` covers: own-team filter, unknown-manager
returns empty, no-manager returns all.

## TSL composition

When constructed with a `TSLOptimizationEngine`, snapshots get
three extra fields populated when target + observed load data
are available:

- `target_sl` — from the channel's TSL target
- `current_sl` — Erlang-C-derived SL at observed staffing /
  arrivals / AHT (delegates to `utils.tsl_optimization.
  service_level`)
- `sl_meets_target` — boolean comparison

When TSL engine is absent or target is missing, all three are
None — engine never fabricates SL values.

## Threshold validation

Engine constructor validates `0 < lower < upper < breach <= 1`.
Misordered or out-of-range thresholds raise ValueError at
construction. Test `TestThresholdValidation` covers 4 invalid
cases.

## Honest deferrals

| Deferral | Reason |
|---|---|
| REAL_TIME_TELEPHONY_FEED | No live ACD/PBX integration; caller pushes observations explicitly |
| BREAK_TIME_DETECTION | Observations report busy vs available only; no break-vs-unavailable distinction |
| ADHERENCE_TRACKING | Engine reports utilization, not schedule adherence |
| HISTORICAL_TREND_PERSISTENCE | In-memory snapshots; PG migration TBD |

## Tests — 27 across 11 classes

- `TestModuleShape` (1)
- `TestRegistry` (1) — ENH-160 active, batch v10.184
- `TestHubIntegration` (1)
- `TestObservationValidation` (5) — empty channel/team/manager,
  busy>available, negative values
- `TestThresholdValidation` (1, 4 cases) — engine constructor
  rejects misordered / out-of-range thresholds
- `TestBandClassification` (5) — under_used / balanced /
  stretched / breach / zero-available
- `TestTSLEnrichment` (3) — enriches when target exists, no
  enrichment without load data, no enrichment for unknown
  channel
- `TestPrivacyFilter` (3) — manager scope, unknown manager,
  no-manager returns all
- `TestLatestPerChannel` (1) — picks most recent per
  (channel, team)
- `TestTeamRollup` (2) — aggregation correctness, empty team safe
- `TestBreaches` (1)
- `TestHonestDeferrals` (1) — all 4 deferrals named
- `TestNoRegression` (2) — audit still 155/155, v10.183 still
  works

**27/27 PASS.**

## Apply order

1. `utils/utilization_dashboard.py`
2. `utils/standards_registry.py` — ENH-160 active, batch v10.184
3. `pages/7_admin.py` — Tier 32 entry appended
4. `tests/test_utilization_dashboard_v10_184.py` — 27 tests
5. `python scripts/audit.py` → 155/155 PASS

## Resource Optimization arc roadmap

| Standard | Engine | Status |
|---|---|---|
| ENH-156 | work_mode_declaration | active (v10.180) |
| ENH-157 | workload_forecasting | active (v10.181) |
| ENH-158 | tsl_optimization | active (v10.182) |
| ENH-159 | cross_channel_balancing | active (v10.183) |
| ENH-160 | utilization_dashboard | **active (v10.184)** |
| ENH-161 | (wellbeing_burnout) | planned |
| ENH-162 | (whatif_scheduler) | planned |
| ENH-163 | (resource_investment_case) | planned |
| ENH-164 | (integrity_culture_score) | planned |
| ENH-165 | (executive_resource_dashboard) | planned |

Half the Resource Optimization arc is active. Five standards to
go before module closure (~v10.190).
