# CHANGELOG v10.589 — Batch B23: debt clearing + MIS V1 documentation

Clears the two number-distorting debts before the Ecobank hierarchy rework, and
captures the V1 baseline so future sessions resume against evidence.

## D1 — Dashboard pipeline alignment (CLEARED)
utils/api.py md_dashboard: the pipeline block now surfaces validated_value,
pending_value and pending_validation (pipeline_summary already computed them).
frontend: types/dashboard.ts gains the optional fields; Dashboard.tsx headline is
now "Assured Pipeline Value" (validated) with "{pending} pending assurance" as the
sub — matching the funnel/tiles instead of the raw consolidated sum.

## D2 — Pipeline->credit lifecycle sync (CLEARED)
utils/api.py submit-to-credit: on success, the deal now auto-advances one stage in
its configured product-class flow (asset: Credit Assessment -> Offer / Proposal),
never into a Closed stage. Config-driven via stage_flows; best-effort (a stage-sync
failure never fails a valid submission). Pairs with the B22b Credit-Assessment lock
so a submitted deal moves forward rather than sitting frozen.
DECISION (Joshua, 2026-06-16): advance exactly one configured stage on submit.

## Docs
- RELEASE_MIS_V1.md (repo root) — what the MIS-V1 tag contains + how to revert.
- docs/DEBT_LEDGER.md — tracked debt inventory (D1/D2 cleared, D3/D4 open, plus
  feature vs hierarchy-phase classification).

## Tests
tests/test_batchB23_debt_clearing.py — 3 tests (asset flow has a non-terminal
next stage after Credit Assessment; md_dashboard exposes the validated split;
submit advances the stage). 3 passed.

## Verify
  python -m pytest tests\test_batchB23_debt_clearing.py -q
  pushd frontend\web && pnpm tsc --noEmit && popd
Browser: MD dashboard shows Assured Pipeline Value (not raw sum). Submit a deal to
credit at Credit Assessment -> it advances to Offer / Proposal and the lock clears.

## Remaining debt (do not distort numbers; see DEBT_LEDGER.md)
D3 credit_workflow.py consolidation; D4 committee charter exposure to frontend.

## Next
Complete simulation + stress test of the full chain before client onboarding.
