# CHANGELOG v10.584 — Batch B19: credit workflow state machine (foundation)

The credit operating model, admin-configurable. This batch lays the LMS-side
foundation: the offer loop, the mid-analysis info-request loop, shared
visibility, and config-driven policy. Credit-Admin two-layer authorization and
committee voting layer on top in the next batches (their states already exist
in the graph).

## Principle
Config chooses the route; code enforces the integrity of whatever route is
chosen. The transition graph + guards are HARDCODED (a JSON edit can never let
an unsigned offer reach disbursement — proven by test). The bank's POLICY is
config.

## Config (admin-configurable) — run scripts\add_credit_workflow.py
Adds `credit_workflow` to lms_config.json:
  committee_mode:                        authority_tier | committee_voting
  signed_offer_attachment:               reference | file_upload
  require_line_manager_offer_validation: bool
  require_analyst_confirmation:          bool
  credit_admin_two_layer_authorization:  bool
  offer_letter:                          { template_label, validity_days, sla_days }

## State machine (hardcoded — utils/api_lms_mutations.py)
LMS_WORKFLOW_TRANSITIONS graph + is_valid_lms_transition + handoff_trigger_status
(the status at which the CALMS case is created, per policy).

New live statuses: info_requested, offer_issued, offer_signed, offer_validated,
analyst_confirmed (plus the existing submitted/assigned/approved/declined/
credit_admin/disbursed). The graph also already defines ca_authorization_requested
and ca_authorized for the next (Credit-Admin) batch.

Flow: submitted -> assigned -> (info_requested <-> assigned) -> approved
  -> offer_issued (auto on approval; routes back to the deal owner)
  -> offer_signed (owner marks signed + attaches signed copy)
  -> offer_validated (line manager validates — checks & balances)
  -> analyst_confirmed (analyst confirms to credit admin)
  -> credit_admin (CALMS case created at the configured handoff trigger).
Optional steps (validation / analyst confirmation) are skipped per config; the
handoff trigger shifts accordingly.

## Visibility / timeline (utils/core.py)
Every workflow action appends a shared `history` event {event, by, at, note}
plus stamps on the offer/info-request sub-objects — so the analyst, deal owner,
and credit admin share one timeline (who's handling it, when, time taken).
New LoanApplicationManager methods: request_info, provide_info, issue_offer,
sign_offer, validate_offer, confirm_to_credit_admin, _log_event.

## Endpoints (utils/api_lms_routes.py)
- POST /api/lms/applications/{id}/request-info        (analyst)
- POST /api/lms/applications/{id}/provide-info        (deal owner)
- POST /api/lms/applications/{id}/sign-offer          (deal owner + attachment)
- POST /api/lms/applications/{id}/validate-offer      (line manager)
- POST /api/lms/applications/{id}/confirm-to-credit-admin (analyst)
The decision route no longer creates the CALMS case on approval — it now issues
the offer (offer_issued). The CALMS case is created at the configured handoff
trigger via _maybe_handoff_to_credit_admin().

## Behaviour change to verify
Approving an application no longer jumps straight to Credit Admin. It now routes
back to the deal owner for the Letter of Offer. Walk the chain in /api/docs:
decision approve -> sign-offer -> validate-offer -> confirm-to-credit-admin, and
confirm the CALMS case appears only at the final step.

## Not in this batch (next)
- Credit-Admin two-layer authorization endpoints (states ready in the graph).
- committee_mode=committee_voting wiring (credit_committee.py).
- Frontend wiring of the whole chain.

## Tests
tests/test_batchB19_credit_workflow.py — 7 tests; the integrity guard
(no credit_admin before a signed offer) is the key one.
