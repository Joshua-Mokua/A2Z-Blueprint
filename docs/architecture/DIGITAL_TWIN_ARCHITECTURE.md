# A2Z Blueprint MIS 360 — Digital Twin Architecture

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md`)
**Status:** `canonical`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 5)
**Last updated:** 2026-05-22
**Owner:** Simulation / Training
**Authoritative sources:**
- Generator scripts at project root (`generate_cbs.py`, `generate_staff.py`, `compute_actuals.py`)
- `utils/virtual_bank_*.py` family (8 modules)
- `data/cbs_baseline_*.json` (snapshots)

**Machine-readable equivalent:** `DIGITAL_TWIN_ARCHITECTURE.json`

---

## Purpose

This document declares the **digital twin** — the simulated bank operating beside the real one. The twin exists so:

- Engines can be exercised against deterministic data
- New features can be tested without touching production
- Stress scenarios and chaos experiments have safe ground
- Training arenas (`utils/arena/`) have a realistic battlefield
- Regulatory submissions can be rehearsed before live filing

Per Article I §1.1 of SYSTEM_CONSTITUTION.md: the system is an organism. The digital twin is its mirror — a body the system can practice in.

---

## Doctrine

**DT1 — The twin is deterministic.** Given the same seed and parameters, the twin produces identical data. Non-determinism is a violation; reproducibility is enforced by `gate_seed_determinism` (G — scripts/audit.py:34424).

**DT2 — Generated data is canonical for its scope.** `data/cbs_baseline_*.json` is the canonical CBS snapshot. Live actuals (`utils/live_actuals.py`) overlay the baseline. Manual BSC Excel uploads override only when explicitly provided.

**DT3 — Twin and production share canonical interfaces.** The same Manager classes (`UserManager`, `CascadeManager`, etc.), engines, and audit gates operate on twin data and production data. No "test mode" branches in business logic.

**DT4 — Scenario libraries are append-only.** Once a scenario is published in `utils/scenarios/`, it persists for replay. Modifications create new scenario versions; old ones remain for historical comparison.

**DT5 — The training arena is the twin's gymnasium.** `utils/arena/` exercises staff (or AI agents) against scenarios. Drills are scored, scored sessions are replayable.

---

## Simulation parameters (current state)

From session memory and `gate_virtual_bank_simulation_implemented` (G — scripts/audit.py:15188):

| Parameter | Value | Notes |
|---|---|---|
| Customers | 700,000 | Synthetic CIFs (range `100000001`–`100700000`) |
| Accounts | 1,197,425 | Format `ECO` + 10 digits |
| Transactions | 50,000 (sample) | Configurable per scenario |
| Branches | 35 | Spread across regions per `org_hierarchy_config.json` |
| RMs | 232 | Per role taxonomy classification (portfolio_owner + service) |
| Staff (total) | 487 | Sample slice; full register is 1,439 (users.json) |
| Deposits | KES 11.5T | Aggregate balance |
| Loans | KES 2.6T | Aggregate outstanding |
| NPL ratio | 11.1% | Simulated (matches Kenya market benchmark) |

These parameters are configurable via the generator scripts. Production deployment with real CBS feeds replaces the generators with live ingestion.

---

## Core organs (8 virtual bank modules + 10 supporting)

### Virtual bank engine family

| Module | Responsibility | Authority |
|---|---|---|
| `utils/virtual_bank.py` | Umbrella module | canonical |
| `utils/virtual_bank_core.py` | Core simulation state | canonical |
| `utils/virtual_bank_simulator.py` | Time-stepped simulator | canonical |
| `utils/virtual_bank_cbs_writer.py` | Writes CBS-shaped data to `cbs_data/` and `data/cbs_baseline_*.json` | canonical |
| `utils/virtual_bank_kpi_unifier.py` | Maps simulator outputs to canonical KPI IDs | canonical |
| `utils/virtual_bank_readiness.py` | Readiness checks before simulation runs | canonical |
| `utils/virtual_bank_seed.py` | Deterministic random seed management | canonical |
| `utils/vb_actuals_bridge.py` | Bridges simulator outputs to actuals engines | canonical |

### Supporting simulation modules

| Module | Responsibility |
|---|---|
| `utils/cbs_baseline.py` | CBS baseline computation |
| `utils/simulation_clock.py` | Logical time advancement |
| `utils/tick_scheduler.py` | Tick-based event scheduling |
| `utils/scenario_simulator.py` | Run individual scenarios |
| `utils/target_scenario_simulator.py` | Target-based scenarios |
| `utils/hybrid_scheduling_simulator.py` | Hybrid scheduling |
| `utils/strategy_simulator.py` | Strategy-level simulation |
| `utils/macro_state.py` | Macroeconomic state |
| `utils/macro_calendar.py` | Macro event calendar |
| `utils/macro_bridge.py` | Bridge macro state to simulation |
| `utils/macro_evolution.py` | Macro evolution rules |

### Scenarios subdirectory (resolves part of OI-23)

`utils/scenarios/` — **canonical** scenario library per `gate_v10479_o3c_scenario_library` (G365 — scripts/audit.py:55344).

Expected contents (hypothesis until uploaded; OI-39):
- Per-domain scenario definitions (risk, compliance, treasury, credit, market, customer behavior)
- Scenario parameters (severity, duration, affected segments)
- Expected outcomes for replay verification

**OI-39** — Joshua to provide `dir utils\scenarios /b` output for explicit enumeration in a follow-up amendment.

---

## Generator scripts (project root)

These produce the twin's seed data:

| Script | Output | Responsibility |
|---|---|---|
| `generate_cbs.py` | `cbs_data/*` (large), `data/cbs_baseline_*.json` | Generate accounts, customers, transactions |
| `generate_staff.py` | `data/staff_register.xlsx`, `data/users.json` (sync) | Generate staff with roles aligned to taxonomy |
| `compute_actuals.py` | `data/actuals_*.xlsx`, BSC actuals JSON files | Compute KPI actuals from generated CBS data |

### Generator contract

1. **Deterministic** — accept a seed parameter; identical seed produces identical output
2. **Validated** — output passes `gate_role_taxonomy_alignment` (every generated staff role classifies), `gate_canonical_retail_chain` (synthesized hierarchy obeys canonical structure), `gate_cbs_writer_integrity` (CBS data shape valid)
3. **Idempotent on re-run** — running twice with same seed and parameters produces same data (deletes/regenerates without divergence)
4. **Versioned** — generator script changes are tracked in CHANGELOG_MASTER; old data files remain replayable with the generator version that produced them

### Role distribution rule (per `_v10398_joshua_hq_canonical`)

`generate_staff.py` must produce a staff register where:
- Exactly 1 staff at tier 0 (the MD)
- C-suite (tier 1) maps 1-to-1 with declared Chief roster
- Heads/Sr Mgrs/Mgrs distributed per `role_manager_whitelist` constraints
- Branch staff distributed across 35 branches
- Every role classifies via `role_taxonomy.classify_role()`
- `validate_role_coverage()` returns `default: 0`

---

## CBS baseline lifecycle

### Snapshot generation

```
generate_cbs.py (seed S, params P)
       ↓
cbs_data/* (raw simulated data)
       ↓
utils/virtual_bank_cbs_writer.py
       ↓
data/cbs_baseline_YYYY_Mon.json (point-in-time snapshot)
       ↓
data/branch_actuals.json (aggregated)
```

### Live overlay

```
data/cbs_baseline_YYYY_Mon.json
       ↓
utils/live_actuals.py (real-time refresh)
       ↓
       + manual BSC Excel override (if provided)
       ↓
Current period actuals
       ↓
data/bsc_actuals_YYYY_Mon.json
```

### Period rotation

When a new period begins:
1. `compute_actuals.py` snapshots the current period as `cbs_baseline_YYYY_Mon.json`
2. The previous period's snapshot becomes immutable historical
3. New period inherits the closing balances as opening balances
4. YoY comparisons read from snapshot files

`gate_cbs_baseline` (scripts/audit.py:34026) enforces snapshot integrity.

---

## Audit gates (the certification ladder for the twin)

| Gate | ID | Line | Purpose |
|---|---|---|---|
| `gate_virtual_bank_foundation` | — | 28413 | Foundation modules exist |
| `gate_virtual_bank_simulation_implemented` | — | 15188 | Simulation actually runs |
| `gate_virtual_bank_readiness` | — | 34337 | Readiness checks pass |
| `gate_seed_determinism` | — | 34424 | Same seed → same output |
| `gate_cbs_writer_integrity` | — | 34539 | CBS writer produces valid shapes |
| `gate_cbs_baseline` | — | 34026 | Baseline snapshots are integrity-checked |
| `gate_branch_single_source` | — | 34638 | Branch data has single source of truth |
| `gate_accruals_synthesizer` | — | 35463 | Accruals synthesizer correct |
| `gate_v10479_o3c_scenario_library` | G365 | 55344 | Scenario library complete |
| `gate_v10480_o4a_simulation_clock_tick_scheduler` | G366 | 55557 | Clock + scheduler operational |
| `gate_v10481_o4b_macro_economic_state` | G367 | 55814 | Macro economic state tracked |

---

## Scenario library architecture

### Scenario shape (canonical target)

```json
{
  "scenario_id": "macro_recession_2026Q3",
  "version": 1,
  "domain": "macro",
  "severity": "high",
  "duration_periods": 4,
  "parameters": {
    "gdp_shock_pct": -3.5,
    "interest_rate_delta_bps": 300,
    "fx_shock_pct": 15
  },
  "affected_segments": ["all"],
  "expected_outcomes": {
    "npl_ratio_delta_pct": "+4 to +7",
    "deposit_outflow_pct": "8 to 12",
    "loan_demand_delta_pct": "-25 to -15"
  },
  "owner": "Treasury / Risk",
  "shipped_in_batch": "v10.479",
  "replay_count": 0,
  "last_replayed": null
}
```

### Scenario categories

| Category | Examples |
|---|---|
| **Macro** | Recession, FX shock, rate shock, sovereign downgrade |
| **Operational** | Branch outage, channel failure, CBS downtime |
| **Credit** | Sector crisis, large default, NPL spike |
| **Compliance** | Sanctions hit, AML alert wave, regulator action |
| **Cyber** | Phishing wave, ransomware, account takeover |
| **Customer behavior** | Mass dormancy, run on deposits, mass onboarding |

### Replay engine

`utils/workflow_replay.py` consumes scenario definitions + event bus history to reconstruct what happened. This is the canonical disaster-recovery + post-incident-analysis mechanism.

---

## Training arena (`utils/arena/`, resolves OI-23 for arena/)

Per `gate_v10485_o7a_training_arena` (G371 — scripts/audit.py:57139): the arena is a structured environment where staff (or AI agents) are exercised against scenarios.

### Arena contract

| Component | Purpose |
|---|---|
| Scenario injection | Load scenario from library; instantiate state |
| Decision capture | Record actor decisions (human or agent) at each step |
| Outcome scoring | Compare actor decisions to expected/optimal outcomes |
| Replay | Save session for later analysis |
| Drill ledger | Append-only record per `gate_v10486_o7b_drill_scoring_replay` (G372) |

### Arena module family (hypothesized, OI-40)

`utils/arena/` likely contains:
- Session orchestrator
- Decision capture
- Scoring engine
- Ledger writer
- Replay API

**OI-40** — Joshua to provide `dir utils\arena /b` for explicit enumeration.

---

## Macro state engine

### Purpose

Real banks operate against a macro environment (rates, GDP, FX, sector growth). The twin models this so scenarios can perturb it.

### Modules

| Module | Responsibility |
|---|---|
| `utils/macro_state.py` | Current macro state |
| `utils/macro_calendar.py` | Scheduled macro events (rate decisions, GDP releases) |
| `utils/macro_bridge.py` | Bridge macro state to simulation inputs |
| `utils/macro_evolution.py` | Time-step evolution rules |

### Macro state shape

```json
{
  "period": "2026-Q2",
  "gdp_growth_pct": 4.8,
  "inflation_pct": 6.2,
  "central_bank_rate_pct": 13.0,
  "fx_kes_per_usd": 158.5,
  "kes_yields": {
    "91_day": 14.2,
    "182_day": 15.1,
    "364_day": 15.8,
    "10_year": 16.4
  },
  "sector_outlook": {
    "agriculture": "stable",
    "manufacturing": "weak",
    "services": "stable",
    "real_estate": "weak"
  }
}
```

Per `gate_v10481_o4b_macro_economic_state` (G367), this state is consumed by stress tests, scenario runs, and forward-looking provisions.

---

## CBS data lineage (regulator-grade)

For audit/regulatory purposes, every cell in a report must be traceable back to source.

### Lineage chain

```
generate_cbs.py (seed S, params P)
     │
     │ produces (deterministically)
     ▼
cbs_data/accounts.csv (CIF, account, balance, RM code, ...)
     │
     │ filtered/joined by
     ▼
utils/virtual_bank_kpi_unifier.py (maps CBS columns to canonical KPI IDs)
     │
     │ aggregated by
     ▼
utils/<domain>_actuals_engine.py
     │
     │ written via
     ▼
data/bsc_actuals_YYYY_Mon.json (canonical period actuals)
     │
     │ consumed by
     ▼
BSC dashboards, reports, regulatory submissions
```

`gate_transaction_lineage` and related gates verify this chain is intact.

---

## Production deployment vs twin

| Aspect | Twin (current) | Production (future) |
|---|---|---|
| Data source | `generate_cbs.py` | Live CBS via Flexcube |
| Refresh | Manual / scheduled | Real-time streaming |
| Determinism | Yes (seed-based) | No (real events) |
| Modifiable | Yes (regenerate any time) | No (audit immutability) |
| Used for | Development, scenarios, training | Live operations |
| Same engines? | Yes — canonical | Yes — canonical |
| Same audit gates? | Yes | Yes |

Per `gate_flexcube_*` family (7 gates, scripts/audit.py:1938-3714): the Flexcube adapter is the canonical production data ingress. Switching from twin to production flips the data source but leaves engines untouched.

---

## Scenarios as living artifacts

Scenarios participate in the **revival ledger** (Wave 6). When a scenario is created:

1. JSON definition added to `utils/scenarios/`
2. Entry created in `REVIVAL_LEDGER.md` with date, rationale, owner
3. Audit gate `gate_v10479_o3c_scenario_library` validates the addition
4. Scenario becomes available for `scenario_simulator.run(scenario_id)` invocations

When a scenario is replayed:
- `replay_count` incremented
- `last_replayed` updated
- Drill ledger entry per `gate_v10486_o7b_drill_scoring_replay`

---

## Open items

| ID | Title | Resolution wave |
|---|---|---|
| OI-39 | Enumerate `utils/scenarios/` contents | Follow-up batch (Joshua dir output) |
| OI-40 | Enumerate `utils/arena/` contents | Follow-up batch |
| OI-41 | Document scenario JSON schema (canonical) | Stage C |
| OI-42 | Macro state schema validation | Stage C |
| OI-43 | Twin → production cutover playbook | Wave 6 REVIVAL_LEDGER |
| OI-44 | CBS data lineage gate (`gate_transaction_lineage` body verification) | Stage C |

---

**End of DIGITAL_TWIN_ARCHITECTURE.md**
