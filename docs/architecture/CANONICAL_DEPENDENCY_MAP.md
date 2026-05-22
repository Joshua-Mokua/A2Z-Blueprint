# A2Z Blueprint MIS 360 — Canonical Dependency Map

**Type:** Constitutional artifact, domain-specific governance
**Authority level:** Domain (consumes from `CANONICAL_TRUTH_REGISTRY.md` + `ORGANS_REGISTRY.md`)
**Status:** `canonical_with_unknown_subareas`
**Version:** v1.0 (introduced v10.497 governance batch, Stage B Wave 3)
**Last updated:** 2026-05-22
**Owner:** Architecture / Doctrine
**Machine-readable equivalent:** `CANONICAL_DEPENDENCY_MAP.json`

---

## Purpose

This document declares **how organs depend on each other** in the A2Z system. It is the blueprint for the cross-organ event bus, the import graph for canonical interfaces, and the shadow-dependency detection rules.

Per C3 expansion of Stage A scope: this artifact prevents:
- **Shadow dependencies** — modules importing from non-canonical paths
- **Circular dependencies** — cycles in the organ import graph
- **Constitutional drift** — silent erosion of organ boundaries

Per SYSTEM_CONSTITUTION Article I §1.1: organs interconnect through a **cross-organ event bus**, not through cross-imports. Direct imports between organs are constrained; coordination flows through `utils/event_bus.py` and `utils/cross_organ_event_bus.py`.

---

## Doctrine

**D1 — Imports are stratified.** Imports flow from higher layers down to lower layers, never up. The strata (top to bottom):
1. **Transports** — `utils/api.py`, FastAPI routers, Streamlit `pages/*.py`, React frontend
2. **Manager classes** — `utils/core.py` Managers
3. **Engines & domain modules** — `utils/*_engine.py`, `utils/*.py` domain logic
4. **Canonical foundations** — `utils/role_taxonomy.py`, `utils/auth_jwt.py`, `utils/auth.py`, `utils/config.py`, `utils/db.py`
5. **Data** — `data/*.json`, `data/*.xlsx` (no imports; pure data)

A module at stratum N may import from strata > N (lower numbers, more foundational). Importing from a lower-numbered stratum from a higher-numbered module is a violation.

**D2 — Organs coordinate through the event bus, not through direct imports.** When organ A needs to notify organ B of a state change, organ A publishes an event to `utils/event_bus.py`; organ B subscribes. Direct cross-organ imports are restricted to canonical foundations.

**D3 — Canonical foundations are universally importable.** `role_taxonomy`, `auth_jwt`, `config`, and `db` may be imported from any layer without violating stratification. They are the system's "stdlib."

**D4 — Shadow dependencies are CRITICAL violations.** A module importing from outside its declared dependency set (per this map) is a shadow dependency. Stage C gate `gate_canonical_dependency_map_sync` enforces.

**D5 — Circular dependencies are forbidden.** The import graph must be a DAG. Cycles are CRITICAL violations.

---

## Stratification

### Stratum 1 — Transports

May import from: Strata 2, 3, 4, 5.
MUST NOT import from: other transports (Streamlit pages don't import FastAPI handlers and vice versa).

| Surface | Canonical entry |
|---|---|
| FastAPI | `utils/api.py` |
| FastAPI routers | `utils/api_*.py` (cascade, capacity_feedback, branding, + 10 unverified) |
| Streamlit | `pages/*.py` |
| React | `frontend/web/src/**` |

### Stratum 2 — Manager classes

May import from: Strata 3, 4, 5.
MUST NOT import from: Stratum 1 (transports).

| Manager | Source |
|---|---|
| `UserManager`, `CascadeManager`, etc. | `utils/core.py` |

Managers are the canonical multi-record interfaces. They are stratified above engines because they orchestrate engines.

### Stratum 3 — Engines & domain modules

May import from: Strata 4, 5.
MUST NOT import from: Strata 1, 2.

| Layer | Examples |
|---|---|
| BSC engines | `bsc_engine`, `bsc_score_computation`, `canonical_bsc_writer`, etc. |
| Cascade engines | `cascade_*` family |
| Actuals engines | All `*_actuals_engine.py` |
| Domain logic | risk, credit, treasury, compliance, customer, etc. |

### Stratum 4 — Canonical foundations

May import from: Stratum 5.
MUST NOT import from: Strata 1, 2, 3.

| Foundation | Module |
|---|---|
| Role taxonomy & RBAC | `utils/role_taxonomy.py` |
| Authentication (FastAPI) | `utils/auth_jwt.py` |
| Authentication (Streamlit) | `utils/auth.py` (transitional) |
| Org hierarchy | `utils/org_hierarchy_config.py`, `utils/hierarchy_synth.py` |
| Tenant config | `utils/config.py` |
| Database | `utils/db.py` |
| KPI canonical | `utils/kpi_alias_resolver.py`, `utils/kpi_aggregation_rules.py` |
| Staff resolution | `utils/staff_role_resolver.py`, `utils/staff_field_resolver.py`, `utils/staff_name_resolver.py` |
| Event bus | `utils/event_bus.py`, `utils/cross_organ_event_bus.py` |

### Stratum 5 — Data

Pure data. No imports.

`data/*.json`, `data/*.xlsx`, `data/_schemas/*.json`, generator script outputs (`cbs_data/`).

---

## Canonical dependency table (organ A → organ B)

This table declares **the permitted direct imports** between organs. Imports not listed here are shadow dependencies.

| From organ | To organ | Reason | Type |
|---|---|---|---|
| All transports | `utils/auth_jwt.py` | Authentication | Direct import |
| All transports | `utils/auth.py` (Streamlit only) | Streamlit page auth | Direct import |
| All transports | `utils/core.py` (Manager classes) | Multi-record operations | Direct import |
| All transports | `utils/config.py` | Tenant configuration | Direct import |
| FastAPI handlers | `utils/role_taxonomy.py` | RBAC tier checks | Direct import |
| FastAPI handlers | Specific engine for the endpoint's domain | Domain computation | Direct import |
| Streamlit pages | `utils/page_shared.py` | Shared page utilities | Direct import |
| Streamlit pages | `utils/page_smoke.py` | Page smoke tests | Direct import |
| Manager classes | Domain engines | Engine orchestration | Direct import |
| Manager classes | `utils/role_taxonomy.py` | Role-based filtering | Direct import |
| Manager classes | `utils/event_bus.py` | Publish state-change events | Direct import |
| Domain engines | `utils/role_taxonomy.py` | Role classification for computation | Direct import |
| Domain engines | `utils/kpi_alias_resolver.py` | KPI ID resolution | Direct import |
| Domain engines | `utils/staff_*_resolver.py` | Staff field resolution | Direct import |
| Domain engines | `utils/db.py` | Data access | Direct import |
| Domain engines | `utils/event_bus.py` | Event publish/subscribe | Direct import |
| BSC engines | `utils/cascade_*` | Cascade integration | Direct import |
| BSC engines | `utils/kpi_*` modules | KPI computation | Direct import |
| BSC engines | `utils/pillar_*` modules | Pillar computation | Direct import |
| Cascade engines | `utils/hierarchy_synth.py` | Hierarchy walks | Direct import |
| Cascade engines | `utils/role_taxonomy.py` | Role-based cascade | Direct import |
| Actuals engines | `utils/canonical_bsc_writer.py` | Write BSC actuals | Direct import |
| Actuals engines | `utils/db.py` | Data access | Direct import |
| Live actuals | All `*_actuals_engine.py` | Overlay refresh | Direct import |
| VB actuals bridge | `utils/cbs_baseline.py` | Baseline computation | Direct import |
| VB actuals bridge | `utils/virtual_bank_*` | Virtual bank state | Direct import |
| ML engines | `utils/mlops_model_registry.py` | Model lookup | Direct import |
| ML engines | `utils/mlops_adjudication_log.py` | Adjudication emit | Direct import |
| Cross-sell bandit | `utils/cross_sell_nba.py` | NBA logic | Direct import |
| Audit engines | All read targets | Read-only verification | Direct import |
| Audit engines | `scripts/audit.py` callers | Gate invocations | (gates call audit engines, not vice versa) |
| All audit emitters | `utils/_audit` in api.py | API audit events | Direct import |
| Treasury engines | `utils/treasury_alm.py` | ALM helpers | Direct import |
| Treasury engines | `utils/fx_position.py` | FX state | Direct import |
| Compliance engines | `utils/sanctions_screening.py` | Sanctions checks | Direct import |
| Compliance engines | `utils/transaction_monitoring.py` | TM rules | Direct import |

---

## Event bus contract

### Purpose

Per D2: organs that need to coordinate state changes do so via the event bus, not direct imports. This enables:
- Loose coupling between organs
- Multiple subscribers per event
- Replayability (events persist; can be replayed in `utils/workflow_replay.py`)
- Audit trail (events are inspectable)

### Canonical interface

`utils/event_bus.py` — single-process pub/sub (in-memory)
`utils/cross_organ_event_bus.py` — cross-organ coordination (likely with persistence)

(**OI-19** — Bodies of these two modules not yet surveyed. Wave 4 TELEMETRY_MAP will document the API contract.)

### Event categories observed

From session memory + Master Prompt context:

| Category | Examples |
|---|---|
| BSC updates | `bsc.score.computed`, `bsc.target.cascaded`, `bsc.actual.updated` |
| Pipeline events | `pipeline.deal.created`, `pipeline.deal.moved`, `pipeline.deal.won/lost` |
| HR lifecycle | `hr.staff.registered`, `hr.staff.transferred`, `hr.staff.terminated` |
| Risk alerts | `risk.threshold.breached`, `risk.limit.warning` |
| Compliance | `compliance.case.escalated`, `compliance.aml.flagged` |
| CBS sync | `cbs.baseline.refreshed`, `cbs.transaction.streamed` |
| API audit | `api.endpoint.called`, `api.audit.emitted` |
| System health | `vitals.organ.degraded`, `vitals.regression.detected` |

### Publication rules

1. Only Managers and engines may publish events
2. Transports MUST NOT publish events directly (they call Managers, which publish)
3. Events MUST include `event_type`, `timestamp`, `actor` (if known), `payload`, `source_module`
4. Subscribers MUST be idempotent (events may be replayed)

---

## Shadow-dependency detection

Stage C gate `gate_canonical_dependency_map_sync` will enforce. Detection rules:

### Rule 1 — Transport-to-transport imports forbidden

```python
# VIOLATION
# In pages/3_pipeline.py:
from utils.api import pipeline_deals  # transport-to-transport
```

```python
# OK
# In pages/3_pipeline.py:
from utils.api_client import call_api  # uses canonical API client
```

### Rule 2 — Engine importing from transport forbidden

```python
# VIOLATION
# In utils/bsc_engine.py:
from utils.api import _audit  # engine importing transport function

# Fix: emit event via event_bus; transport's audit emit happens at route level
```

### Rule 3 — Cross-organ direct import without declared edge

If `utils/credit_actuals_engine.py` imports `utils/treasury_alm.py`, and that edge isn't in the dependency table above, it's a shadow dependency.

Permitted exceptions:
- Stratum 4 canonical foundations (role_taxonomy, auth_jwt, config, db, event_bus) are universally importable
- Stratum 3 modules within the same organ family may cross-import freely (e.g. BSC engines may import each other)

### Rule 4 — Circular imports CRITICAL

Any import cycle (A → B → A) is a CRITICAL violation. Python's import system tolerates some cycles via lazy imports, but the canonical doctrine forbids them.

---

## Foundation contracts (Stratum 4)

These modules are imported widely. Their stability is constitutional.

### `utils/role_taxonomy.py`

Per `ROLE_GOVERNANCE.md`. Already canonical.

Contract surface:
- `classify_role`, `get_profitability_tier`, `get_branch_scope`, `get_sbu`, `can_be_tagged`
- `list_all_classified_roles`, `list_roles_by_tier`, `list_roles_by_sbu`
- `validate_role_coverage`, `self_test`
- 5 tier constants, 3 scope constants, 7 SBU constants, `RoleClassification` dataclass

Stability: API-compatible additions allowed; removals forbidden.

### `utils/auth_jwt.py`

Per `CANONICAL_TRUTH_REGISTRY.md::authentication_and_session_tokens`.

Contract surface:
- `get_current_user`, `create_access_token`, `decode_token`, `revoke_token`, `_is_revoked`
- `require_admin`, `require_role`
- `warn_if_default_secret`

Stability: API-compatible additions allowed. `require_role` signature evolution permitted (OI-10 adds `tier=`, `sbu=`, `seniority_max=` kwargs while remaining backward-compatible with `list[str]` calls).

### `utils/config.py`

Tenant configuration loader. Exposes:
- Org name, regulator, brand colors, IP notice
- Currency, locale, period boundaries
- Feature flags

Stability: canonical config schema; new fields require `CANONICAL_TRUTH_REGISTRY` update.

### `utils/db.py`

Database access layer. Likely transitional (JSON files → PostgreSQL migration referenced in audit gates `gate_pg_migration_progress`, `gate_pg_migration_baseline`, `gate_pg_production_cutover`).

Stability: read API stable; write API may evolve with migration.

### `utils/event_bus.py` + `utils/cross_organ_event_bus.py`

Pub/sub for organ coordination. Wave 4 TELEMETRY_MAP will document the API surface.

---

## Known dependency hotspots

### Hotspot 1 — BSC ↔ Cascade

The BSC engines and cascade engines are tightly coupled by domain (target → cascade → score → actuals → audit). Permitted cross-imports per the table above. Internal organization:

```
bsc_universal_contract ←─ bsc_engine ─→ bsc_score_computation
                                    ↓
                          canonical_bsc_writer
                                    ↑
       cascade_bsc_360_engine ←─ CascadeManager ─→ cascade_bsc_actuals_engine
       cascade_bsc_harmonize_engine                cascade_bsc_linkage_engine
```

### Hotspot 2 — Actuals engines → live_actuals

All 14 actuals engines feed into `live_actuals.py` for real-time refresh. The dependency direction is engines → live_actuals (live_actuals subscribes); not the reverse.

### Hotspot 3 — Hierarchy ↔ Role taxonomy

`hierarchy_synth.py` consumes `role_taxonomy.py` for tier-based synthesis decisions. `role_taxonomy.py` consumes `org_hierarchy_config.json` for the role classification map. Both ultimately read from the same canonical data file, but they don't import each other (the dependency is via the data file, not module imports).

### Hotspot 4 — Auth ↔ Users

`auth_jwt.py` and `auth.py` both read `data/users.json` for authentication and access checks. `UserManager` in `core.py` is the canonical interface for user lookups. Recommendation (Stage C): auth modules should call into `UserManager` rather than reading `users.json` directly.

(**OI-20** — Verify whether auth modules use `UserManager` or direct file reads. If direct reads, this is a violation of D4 shadow dependency rule but with a transitional grace period because it's been the historical pattern.)

---

## Frontend dependency rules

### React import discipline

`frontend/web/src/` follows TypeScript module conventions:

| Layer | Imports |
|---|---|
| `pages/*` | components, lib, providers |
| `components/*` | other components, lib, ui primitives |
| `components/ui/*` | lib, no other components (primitives have no dependencies) |
| `lib/*` | other lib modules only |
| `providers/*` | lib, no components |

Cross-page imports are forbidden. Components may not import pages. lib may not import components or providers.

### Brand color flow

```
data/org_config.json
  ↓ (HTTP)
GET /api/branding
  ↓
BrandingProvider
  ↓ (sets CSS vars)
--brand-primary, --brand-secondary, --brand-accent
  ↓ (used by)
shadcn primitives + Tailwind classes
```

No component ever imports a brand string directly from JSON. The chain above is canonical.

### Token flow

```
frontend/web/src/lib/tokens.ts  (semantic hex, source of truth)
  ↓ (manually maintained or build-time derived)
frontend/web/src/index.css  (HSL components in CSS variables)
  ↓ (wrapped by)
tailwind.config.js  (hsl(var(--token) / <alpha-value>))
  ↓
shadcn primitives, components, pages (use Tailwind classes)
```

`tokens.ts` is the source. `index.css` is `derived`. No component reads hex from anywhere else.

---

## Dependency map for the 8 unknown subdirectories

When the 8 `utils/*/` subdirectories are surveyed in subsequent waves, their dependency edges must be added to this map. Expected patterns:

| Subdir | Hypothesized imports |
|---|---|
| `utils/agents/` | `utils/treasury_agents.py`, `mlops_*`, `event_bus` |
| `utils/arena/` | `virtual_bank_*`, `scenario_simulator`, `event_bus` |
| `utils/cert/` | `audit_trail_certification`, `enterprise_discharge_audit` |
| `utils/channels/` | `channel_*` top-level modules |
| `utils/chaos/` | `stress_test_harness`, `disaster_recovery`, `system_invariants` |
| `utils/ml/` | `mlops_*`, `model_governance`, `fairness_testing` |
| `utils/scenarios/` | `scenario_simulator`, `target_scenario_simulator`, `macro_*` |
| `utils/uncertainty/` | `stress_*`, `risk_*`, `chaos/`, `cert/` |

Each subdirectory's actual imports will be verified when its contents are surveyed.

---

## Open items

| ID | Title | Resolution wave |
|---|---|---|
| OI-19 | `utils/event_bus.py` + `utils/cross_organ_event_bus.py` API surface | Wave 4 TELEMETRY_MAP |
| OI-20 | Verify whether `auth_jwt.py` and `auth.py` go through `UserManager` or direct `users.json` reads | Stage C |
| OI-21 | Add Stage C gate `gate_canonical_dependency_map_sync` | Stage C |
| OI-22 | Generate full import graph (could be visualized) from `utils/*.py` by AST parsing | Optional follow-up |
| OI-23 | Resolve 8 utils subdirectories' actual import edges | Wave 5 |
| OI-24 | `utils/db.py` migration state (JSON → PG) impact on stratum 4 stability | Stage C |

---

**End of CANONICAL_DEPENDENCY_MAP.md**
