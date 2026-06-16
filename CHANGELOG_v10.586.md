# CHANGELOG v10.586 — Batch B21: committee voting (reuses CreditCommitteeEngine)

Wires committee decisions into the live LMS flow when the bank's policy is
committee_mode == "committee_voting". Reuses the EXISTING, fully-tested
utils/credit_committee.py CreditCommitteeEngine — no committee logic is
duplicated. (Audit note: there were two parallel committee modules
[credit_committee.py + credit_workflow.py], neither wired live; this batch wires
the richer of the two and leaves the other for later consolidation.)

## Adapter (NEW) — utils/api_lms_committee.py
Thin wiring only: builds a CommitteeCharter from admin config (falls back to the
engine's default charter), decides whether a facility is committee-tier, converts
stored votes -> engine types, runs engine.evaluate(), and maps the DecisionResult
back to the live string-status flow. Exposes committee_required, charter_from_config,
committee_member_ids, evaluate_committee.

## Config (admin-configurable) — run scripts\add_committee_config.py
Adds credit_workflow.committee: refer_above_kes, voting_rule, min_quorum_count,
authority_limit_kes, independent_member_min, required_roles, members[]. Adding it
does NOT change behaviour — committee only activates when committee_mode is set to
"committee_voting" in admin config. Default charter: MCC, 5 members, simple
majority, quorum 3, CRO required, 1 independent min.

## core.py — LoanApplicationManager
- refer_to_committee(app_id, by, note): status -> referred_to_committee, inits the
  committee record.
- record_committee_vote(app_id, member_id, vote, rationale, by): records/replaces a
  member's vote.
- resolve_committee(app_id, result, by, authority, note): stores the engine result;
  approved -> 'approved' (offer loop continues), rejected -> 'declined'.

## Endpoints (api_lms_routes.py)
- POST /api/lms/applications/{id}/committee/refer    (manager)
- POST /api/lms/applications/{id}/committee/vote     {member_id, vote, rationale}
- POST /api/lms/applications/{id}/committee/resolve   (manager) — runs the engine;
  on approval auto-issues the Letter of Offer (offer loop).
- Decision route guard: in committee_voting mode, a committee-tier facility cannot be
  decided directly — it must go through refer -> vote -> resolve. No-op in the
  default authority_tier mode (backward-compatible).

## Engine behaviour (via the real engine, verified)
- amount above the charter's authority_limit -> ESCALATED before any vote.
- quorum incl. required role (CRO) + majority YES -> APPROVED.
- majority NO -> REJECTED. required role absent -> QUORUM_FAILED.

## Verify (/api/docs — set committee_mode='committee_voting' first)
On a committee-tier application: /committee/refer -> /committee/vote (m1..m5) ->
/committee/resolve. Approve path then issues the offer; walk on through
sign-offer -> validate-offer -> confirm-to-credit-admin as in B19.

## Tests
tests/test_batchB21_committee.py — 6 tests (approve / reject / quorum-fail /
escalate / charter build / required-off-by-default).

## Document gate (your other ask) — already enforced
submit-to-credit already blocks (400 + missing list) until every required document
is provided. The "stage locks at Credit Assessment until submitted" piece is a
frontend UX lock over that existing backend — it folds into the frontend batch.

## Next
Frontend: surface the whole chain (pipeline -> credit -> offer -> committee ->
authorize -> disburse) with the shared timeline + the Credit-Assessment stage lock.
