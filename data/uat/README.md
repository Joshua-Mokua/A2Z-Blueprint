# `data/uat/` — User Acceptance Testing Sandbox

**Disposable.** UAT data should be reset between testing cycles.

## What goes here

When `A2Z_ENV=uat`, all writes are namespaced here. Typical contents:
- UAT-specific BSC actuals
- UAT-specific scenario library
- UAT audit log

## Promotion

UAT data can only be promoted to STAGING (and only after a successful
UAT sign-off, recorded via `utils.data_migration.promote_dataset()`).
