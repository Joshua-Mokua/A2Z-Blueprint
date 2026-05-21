# `data/sim/` — Simulation Environment Sandbox

**Disposable.** Anything in this directory is regenerable from the
Virtual Bank simulation pipeline and may be wiped without warning.

## What goes here

When `A2Z_ENV=sim` (or `data/environment.json` has `mode=sim`), every
write that would otherwise touch `data/<file>` is redirected here by:
- `utils.data_isolation_guard.guarded_write_path(...)`
- `utils.vb_actuals_bridge.refresh_actuals_from_virtual_bank(...)`
- `utils.virtual_bank_cbs_writer.persist_bank_to_cbs(...)` (when called with mode=sim)

Typical contents:
- `bsc_actuals_*.json` — simulation BSC submissions
- `audit_log.json` — simulation audit trail (separate from PROD audit)
- `sim_run_<timestamp>/` — disposable per-run artefacts

## What MUST NOT go here

Production data. Real customer KYC. Real staff records. If a record
mixes real PII with simulation data, the simulation isolation is broken.

## Promotion

Sim data can be promoted to UAT (and only UAT) via
`utils.data_migration.promote_dataset(src=sim, dst=uat)`. Promotion is
logged via `audit_log` with the actor identity.
