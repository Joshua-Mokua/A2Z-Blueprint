# A2Z Blueprint MIS 360 — CHANGELOG v10.498

**Batch:** v10.498 Stage C Batch 1
**Date shipped:** 2026-05-22
**Status:** in-progress
**Audit gates added:** G383, G384, G385, G386, G387
**Master Prompt at time of ship:** v5.40

---

## What shipped

First batch of Stage C enforcement gates wiring the v10.497 constitutional
governance program into mechanical audit checks. Five CRITICAL-severity
gates that enforce constitutional doctrine from
`docs/architecture/`.

Per the rollout schedule in `REVIVAL_LEDGER.md::stage_c_enforcement_rollout_plan`,
CRITICAL gates carry no grace period. They ship at full severity from this
batch.

**Initial expected state:** several of these gates WILL FAIL on first run.
That is by design. The failures are the work backlog. Subsequent batches
(Stage C Batch 2+, and Phase 1 Step 1.4+ for the auth rename) drive
violations to zero.

This is the first batch under the **CM1 doctrine** (CHANGELOG_MASTER.md):
every batch from v10.498 onwards ships with a CHANGELOG. This file is the
canonical instance of that doctrine.

## New modules

None.

## Modified modules

- `scripts/audit.py` — appended 5 new gate function definitions,
  prepended 5 new registry tuples (G383–G387)

## New API endpoints

None.

## New audit gates

| Gate ID | Function | Severity | Source artifact |
|---|---|---|---|
| **G383** | `gate_v10498_no_require_role_collision` | CRITICAL | ROLE_GOVERNANCE OI-1 |
| **G384** | `gate_v10498_event_bus_publisher_purity` | CRITICAL | TELEMETRY_MAP T2 / CANONICAL_DEPENDENCY_MAP D2 |
| **G385** | `gate_v10498_react_no_tenant_strings` | CRITICAL | FRONTEND_GOVERNANCE FE3 |
| **G386** | `gate_v10498_no_unregistered_model_in_production` | CRITICAL | AI_GOVERNANCE AI1 |
| **G387** | `gate_v10498_agent_scope_declared` | CRITICAL | AI_GOVERNANCE AI7 |

### G383 — no require_role collision

Resolves the longest-standing constitutional violation (OI-1, surfaced in
Stage A survey). Both `utils/auth.py` and `utils/auth_jwt.py` historically
exported a symbol named `require_role` with incompatible signatures:

- `utils/auth.py::require_role` — alias for `require_access(module_name)`
  (Streamlit page-level RBAC)
- `utils/auth_jwt.py::require_role` — factory `(roles: list[str]) → Depends`
  (FastAPI handler RBAC)

The fix per ROLE_GOVERNANCE: rename the Streamlit symbol to
`require_module_access`. G383 enforces that the Streamlit symbol is renamed
AND that no callsite still imports `require_role` from `utils.auth`.

**Expected to FAIL on first run** until the rename ships (Phase 1 Step 1.4+).

### G384 — event bus publisher purity

Enforces TELEMETRY_MAP T2 + CANONICAL_DEPENDENCY_MAP D2: only Managers and
engines may publish events. Transports (FastAPI handlers, Streamlit pages,
router modules under `utils/api_*.py`) MUST NOT call `event_bus.publish()`
or `cross_organ_event_bus.publish()` directly.

Scans:
- `utils/api.py`
- `utils/api_*.py` router modules
- `pages/*.py`

Pass criterion: zero direct `event_bus.publish(` or
`cross_organ_event_bus.publish(` calls in transport surface.

Status on first run: **unknown until executed**. We have not surveyed
existing transport modules for these patterns. Any findings become Stage C
Batch 2 work.

### G385 — React no tenant strings

Enforces FRONTEND_GOVERNANCE FE3: brand identity is tenant data, never
code. Scans `frontend/web/src/**/*.{tsx,ts,jsx,js}` for hardcoded tenant
strings ("Ecobank", "FLEXCUBE"). Skips test/spec/stories/mocks directories.

Status on first run: **likely passes** — the v10.497 P0 shadcn pivot was
explicit about tenant isolation, and the React app is recent enough that
hardcoded tenant strings would be a known regression.

### G386 — no unregistered model in production

Enforces AI_GOVERNANCE AI1: every model influencing production decisions
must be registered in `utils/mlops_model_registry.py`. Iterates the
canonical 11-engine list from AI_GOVERNANCE.md Section "Production AI
engines" and verifies each imports from the registry (or carries a
`# G386:exempt — <reason>` marker for legitimate non-inference helpers).

Status on first run: **likely FAILS for most engines** — the registry
discipline is new doctrine; existing engines were authored before the
mlops_model_registry contract was formalized. Each remediation is a small
PR (~5-20 LOC per engine).

### G387 — agent scope declared

Enforces AI_GOVERNANCE AI7: every agent in `utils/agents/` declares an
`AGENT_SCOPE` dict at module level with the canonical schema (agent_id,
purpose, scope.{domains, data_read, data_write, tools_allowed,
actions_forbidden}, escalation, audit).

Uses AST inspection rather than text scanning — robust to formatting.

Status on first run: **may FAIL or pass vacuously**. The `utils/agents/`
directory has not been surveyed (OI-46). If it's empty, gate passes
vacuously. If it contains agent modules without AGENT_SCOPE declarations,
those become Stage C Batch 2 remediation work.

## Data files affected

None directly. Indirectly: `data/audit_baselines.json` may receive new
keys if any of the gates evolve to use the G163-style baseline-ratchet
pattern in future batches. Current batch is pure pass/fail, no ratchets.

## Tests added

None in this batch. The five gates ARE the tests. Integration tests
exercising the gates' behavior on synthetic violation/non-violation cases
will be authored in Stage C Batch 5 (test infrastructure batch).

## Open items resolved

| Open item | Status |
|---|---|
| OI-21 — Add Stage C gate `gate_canonical_dependency_map_sync` | Partially addressed via G384 (event bus publisher purity scope) |
| (Resolves no OIs fully — gates are the enforcement; OIs close when the gate's violations reach zero) | — |

## Open items added

| Open item | Title | Resolution wave |
|---|---|---|
| OI-63 | Audit historical event_bus.publish() callsites in transports | Stage C Batch 2 |
| OI-64 | Register existing 11 production AI engines with mlops_model_registry | Stage C Batch 2-3 |
| OI-65 | Survey `utils/agents/` for existing modules; backfill AGENT_SCOPE | Stage C Batch 2 (depends on `dir utils\agents /b` output) |

## Verification

- [ ] `scripts/audit.py` parses cleanly (Python syntax check)
- [ ] All five gate functions are importable
- [ ] Each gate runs individually via `python scripts/audit.py --only-gate <name>`
- [ ] Full audit suite includes G383–G387 in the report
- [ ] Failures (if any) match expected patterns documented above

## Breaking changes

None. The new gates are pure read-only verifiers. They do not modify
state or block any pre-existing behavior. Existing 382 gates are
untouched.

## Rollback procedure

```
git revert <stage_c_batch_1_commit_hash>
```

The change is a single commit; revert restores the prior audit gate suite
exactly (382 gates).

## Cross-references

- `docs/architecture/ROLE_GOVERNANCE.md` (G383 doctrine)
- `docs/architecture/RBAC_MATRIX.md` (G383 capability model)
- `docs/architecture/TELEMETRY_MAP.md` (G384 doctrine)
- `docs/architecture/CANONICAL_DEPENDENCY_MAP.md` (G384 doctrine)
- `docs/architecture/FRONTEND_GOVERNANCE.md` (G385 doctrine)
- `docs/architecture/AI_GOVERNANCE.md` (G386, G387 doctrine)
- `docs/architecture/REVIVAL_LEDGER.md` (Stage C enforcement rollout plan)
- `docs/architecture/CHANGELOG_MASTER.md` (CM1 doctrine — this file is its
  first instance going forward)

---

**End of CHANGELOG_v10498.md**
