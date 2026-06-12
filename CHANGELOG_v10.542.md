# CHANGELOG v10.542 — Phase P Batch P1: Cross-cutting BSC feed (LMS + Credit Admin)

Closes integration-parity gaps M1 (LMS) and M2 (Credit Admin) from
PARITY_UX_ASSESSMENT_2026_06_12.md.

## What changed
- NEW utils/api_bsc_bridge.py — neutral shared `emit_bsc_trigger(username)`
  (best-effort recompute via utils.core.update_bsc_from_modules). Documents
  the CBS-vs-module actuals-source precedence rule (CBS-derived wins).
- utils/api_lms_routes.py — decision route now recomputes BSC after a
  successful, audited decision (before return).
- utils/api_credit_admin_routes.py — disburse route now recomputes BSC
  after a successful, audited clearance (before return).
- NEW tests/test_p1_bsc_feed_parity.py — 5 source-scan regression tests.

## Deliberately NOT changed
- The Pipeline / G381-protected provider+route path is untouched. Pipeline's
  local emit_bsc_trigger remains; consolidating it onto the shared bridge is
  a future pure-import-swap, deferred for zero blast radius.

## Gate
- pytest tests/test_p1_bsc_feed_parity.py -> 5 passed.
- py_compile on all three .py files -> OK.

## Parity dimension closed
- Integration parity: LMS + Credit-Admin React mutations now feed BSC,
  matching Pipeline. The credit chain is observable end-to-end on the
  measurement plane.
