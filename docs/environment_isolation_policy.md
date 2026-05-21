# Environment Isolation Policy — A2Z MIS 360

**Doctrine:** *No simulation artifacts may contaminate production DNA.*
(Joshua Master Prompt — Enterprise Banking Digital Twin Phase O8)

## Five environments

| Env | Mode | Purpose | Data root | Disposable |
|---|---|---|---|---|
| DEV | `dev` | Local developer workstation | `data/` | Yes (locally) |
| SIM | `sim` | Virtual Bank simulation / Digital Twin | `data/sim/` | **Yes** |
| UAT | `uat` | User Acceptance Testing | `data/uat/` | **Yes** between cycles |
| STAGING | `staging` | Pre-prod rehearsal | `data/staging/` | No |
| PROD | `prod` | Production / Ecobank live | `data/` | **No** (sacred) |

DEV writes to the same root as PROD by design — developers are working
on a local clone. The PROD root is sacred only on real production hosts
(deployed with `A2Z_ENV=prod` set).

## How the mode is resolved

In order of precedence:

1. Environment variable `A2Z_ENV` (e.g. `A2Z_ENV=sim`)
2. `data/environment.json` `{"mode": "..."}`
3. Default fallback: `dev`

## Promotion ladder (one-way)

```
  DEV  ─→  SIM  ─→  UAT  ─→  STAGING  ─→  PROD
   │              ↑
   └──────────────┘
   (DEV may also promote to UAT directly for ad-hoc fixture creation)
```

Demotions are forbidden. PROD is terminal — once data lives in PROD,
it can only move forward via the audit trail. There is no `PROD → DEV`
or `STAGING → SIM` path.

Promotion is recorded via `utils.audit_log` with severity `critical`
when the destination is PROD, otherwise `warning`.

## Code-level enforcement

### Single source of truth
- `utils.environment.get_environment()` — read the current mode
- `utils.environment.set_environment(target, set_by, reason)` — change it

### Write-side guards
- `utils.data_isolation_guard.guarded_write_path('bsc_actuals_2026-Q1.json')`
  returns the mode-appropriate absolute path (PROD → `data/...`,
  SIM → `data/sim/...`, etc).
- `utils.data_isolation_guard.is_write_allowed(path)` returns
  `(bool, reason)` for a candidate write.
- `utils.data_isolation_guard.assert_not_production('chaos injection')`
  raises `RuntimeError` if called in PROD.

### PROTECTED production files
The following files cannot be overwritten by non-PROD modes:
- `data/users.json`
- `data/hr.json`
- `data/kpi_library.json`
- `data/target_cascade.json`
- `data/bank_targets.json`
- `data/bsc_scores.json`
- `data/actuals_yoy.json`

## Promotion examples

### Promote SIM dataset to UAT (after a successful simulation cycle)

```python
from utils.environment import Environment
from utils.data_migration import promote_dataset

result = promote_dataset(
    src=Environment.SIM,
    dst=Environment.UAT,
    actor="300011",  # CIO
    reason="v10.474 simulation cycle complete; promoting BSC dataset",
    dry_run=False,
)
print(f"copied={result.files_copied} audit={result.audit_id}")
```

### Inventory before promotion

```python
from utils.data_migration import list_environment_inventory
print(list_environment_inventory(Environment.SIM))
```

## Onboarding checklist for new write-side engines

If your engine writes to disk, follow this pattern:

```python
from utils.data_isolation_guard import guarded_write_path

def persist_my_thing(period):
    target = guarded_write_path(f"my_thing_{period}.json")
    target.write_text(json.dumps(payload), encoding="utf-8")
```

That single helper ensures your engine writes to the right namespace
regardless of which environment it runs in.

## Audit evidence

Every environment change and dataset promotion creates an `audit_log`
entry with severity `warning` (intra-environment), `warning` (cross-
environment except PROD), or `critical` (when PROD is the destination
or `force=True` was used).

These entries are subject to the 7-year retention schedule per
`docs/data_retention_policy.md`.
