# CHANGELOG v10.585 — Batch B20: Credit-Admin two-layer authorization

Adds the "approval AND confirmation" layer on the CALMS case: a credit-admin
officer requests authorization once conditions are met, then a credit-admin
MANAGER authorizes, and only then can the case be disbursed. Governed by the
`credit_admin_two_layer_authorization` policy toggle (B19 config); when off,
the legacy single-step disburse applies.

## Principle
Reuses the existing `ready_for_disbursement` gate — the two-layer just changes
WHO sets it and WHEN. Under two-layer, conditions being met no longer makes a
case ready; only manager authorization does. The disburse path is unchanged
(still gates on ready_for_disbursement).

## core.py — CreditAdminManager
- fulfill_condition: only auto-sets ready_for_disbursement when two-layer is OFF
  (config). When on, conditions-met sets all_conditions_met but NOT ready.
- request_authorization(case_id, by, note): Layer 1. Requires all_conditions_met;
  sets authorization_requested + by/at.
- authorize(case_id, by, note): Layer 2. Requires a pending request; sets
  authorized + by/at and ready_for_disbursement=True.
- _two_layer_enabled(): reads the policy toggle.
- New cases initialize authorization_requested / authorized = False.

## Models (api_credit_admin_models.py)
- CreditAdminCase gains authorization_requested(+by/at) and authorized(+by/at).
- CreditAdminPermissions gains can_request_authorization + can_authorize.
- New request bodies: RequestAuthorizationRequest, AuthorizeRequest.

## Permissions (api_credit_admin_permissions.py)
- can_request_authorization: in scope, all_conditions_met, not yet requested,
  two-layer on, not disbursed.
- can_authorize: CA manager-tier, in scope, request pending, not yet authorized.
- can_disburse: now gates on ready_for_disbursement (correct for both modes).

## Endpoints (api_credit_admin_routes.py)
- POST /api/credit-admin/cases/{id}/request-authorization   (officer / in scope)
- POST /api/credit-admin/cases/{id}/authorize               (CA manager-tier)
- Disburse guardrail (api_credit_admin_mutations.case_can_be_disbursed) now
  returns a clean 400 while authorization is pending (instead of a 500).

## Verify (/api/docs, two-layer default ON)
Fulfill all conditions on a case -> /disburse is blocked ("authorization not yet
requested") -> POST /request-authorization (officer) -> still blocked ("awaiting
manager authorization") -> POST /authorize (manager) -> /disburse now succeeds.

## Tests
tests/test_batchB20_credit_admin_authorization.py — 4 tests; the no-disburse-
before-authorize gate is the key one.

## Next
committee_mode=committee_voting wiring, then the frontend for the whole chain.
