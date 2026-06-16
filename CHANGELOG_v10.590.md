# CHANGELOG v10.590 — Batch B24: scope-signature hotfix (simulation-caught)

The credit-chain simulation harness surfaced a real runtime defect: the B19-B21
LMS workflow endpoints (sign-offer, validate-offer, confirm-to-credit-admin, and
all three committee endpoints) called is_app_in_scope(app, user) with the wrong
signature — is_app_in_scope expects (app, visible_codes: Set, caller_staff_code),
so passing the user dict made every scope check fail. Result: the entire offer
loop + committee flow 403'd ("Application is out of scope") for legitimate deal
owners and managers — the chain was unreachable past LMS approval via the API.

## Fix — utils/api_lms_routes.py
All 8 wrong-signature checks corrected to the working pattern (same as the
decision/assign routes):
    if not user.get('is_admin') and not is_app_in_scope(
            app, get_visible_staff_codes(user), str(user.get('staff_code','') or '')):
        raise HTTPException(403, "Application is out of scope")
Adds the admin bypass that was also missing.

## Not a bug (verified)
- Decision response label "decision_approved" is cosmetic; the stored status is
  actually offer_issued (record_decision -> approved -> issue_offer). The offer
  loop is reachable.
- Credit-admin authorization endpoints (B20) already used the correct
  is_case_in_scope(case, visible_codes) signature — no fix needed.

## Tests
tests/test_batchB24_scope_signature.py — guards against the wrong signature
returning + asserts the corrected form on >=8 endpoints. 2 passed.

## Re-run the simulation after applying
  python scripts\simulate_credit_chain.py
Expected: offer loop + committee now reachable. NOTE: for the committee happy
path to APPROVE (not escalate) a 150M deal, run scripts\add_committee_config.py
first so the charter authority (500M) covers it; otherwise the default charter
(100M authority) correctly escalates a 150M facility.
