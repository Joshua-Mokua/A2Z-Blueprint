# CHANGELOG v10.547 — Phase P Batch P2: LMS-approval -> Credit-Admin handoff

Closes M4 from PARITY_UX_ASSESSMENT_2026_06_12.md — the missing live
handoff in the credit chain. Previously credit-admin cases existed only
via data generation; approving a loan in React created no case.

## What changed
- utils/core.py — CreditAdminManager.create_case_from_application(app,
  conditions, authority): creates a CALMS case from an approved LMS app.
  Idempotent (case id = 'CA'+application_id, matching generate_lms_data.py),
  so re-approval/retry no-ops instead of duplicating or resetting an
  in-flight case. Shape mirrors the generator byte-for-byte.
- utils/api_lms_routes.py — the decision route now calls the handoff on
  verdict 'approved' (best-effort; never fails a recorded decision) and
  surfaces credit_admin_case_id in the response (model allows extra).
- tests/test_p2_lms_credit_handoff.py — source-scan + behavioral
  (shape, condition mapping, idempotency, empty-conditions).

## Notes
- Conditions come from the approval payload (each becomes one unfulfilled
  required condition); empty conditions => all_conditions_met True but
  ready_for_disbursement stays False (a manager still clears explicitly).
- Frontend cross-link (LMS detail -> the new /credit-admin case) is a small
  follow-up; the case id is already in the decision response for it.

## Verification
- py_compile core.py + api_lms_routes.py -> OK
- standalone proof (id format, denorm, conditions, idempotency, empty) -> all pass
- behavioral pytest runs in the full-deps env (Josh)
