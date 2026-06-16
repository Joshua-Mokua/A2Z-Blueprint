# CHANGELOG v10.587 — Batch B22a: LMS credit-workflow frontend (centerpiece)

The first of two frontend halves that surface the credit operating model built in
B19–B21. This half wires the LMS application-detail page to the full workflow:
info-request loop, the offer loop (issue→sign→validate), analyst confirmation,
committee voting, and a shared workflow timeline. Half two (B22b) adds the
Credit-Admin authorization UI and the pipeline Credit-Assessment stage lock.

## Backend — utils/api_lms_permissions.py
resolve_application_permissions + _all_false now return 8 workflow permission
flags (status + role + config derived), so the UI is backend-driven, not guessing:
  can_request_info, can_provide_info, can_sign_offer, can_validate_offer,
  can_confirm_to_credit_admin, can_refer_committee, can_vote_committee,
  can_resolve_committee
(LoanApplicationPermissions has extra="allow" — flags pass through cleanly.)

## Types — frontend/web/src/types/lms.ts
- New nested types: LoanAppHistoryEvent, LoanAppOffer, LoanAppInfoRequest,
  LoanAppCommitteeVote, LoanAppCommittee.
- LoanApplication += history / offer / info_request / committee / credit_admin_case_id.
- LoanApplicationPermissions += the 8 optional workflow flags.
- APPLICATION_STATUSES += info_requested, referred_to_committee, offer_issued,
  offer_signed, offer_validated, analyst_confirmed; statusTone extended.
- Request bodies: RequestInfoRequest, ProvideInfoRequest, SignOfferRequest,
  ValidateOfferRequest, ConfirmToCreditAdminRequest, CommitteeVoteRequest,
  ResolveCommitteeRequest.

## Fetchers — frontend/web/src/lib/api.ts
requestLmsInfo, provideLmsInfo, signLmsOffer, validateLmsOffer,
confirmLmsToCreditAdmin, referLmsCommittee, voteLmsCommittee, resolveLmsCommittee.

## Hook — frontend/web/src/hooks/useLmsMutations.ts
+8 mutations mirroring the existing discriminated MutationResult pattern.

## Component — frontend/web/src/components/Timeline.tsx (NEW)
Vertical workflow timeline rendering the application's history events.

## Page — frontend/web/src/pages/LmsApplicationDetail.tsx
Permission-gated workflow panels (request-info, provide-info, sign-offer,
validate-offer, confirm-to-credit-admin, refer-to-committee, committee vote +
resolve) + a "Workflow timeline" card. The "no actions" fallback now accounts
for all workflow permissions.

## Verify (Josh's env — canonical gate)
  pushd frontend\web && pnpm tsc --noEmit && popd
Then in the browser: open an assigned application as the analyst (request-info),
as the owner (provide-info / sign-offer), as the manager (validate / decision),
and walk the offer loop. Committee panel appears at referred_to_committee.

## Notes / honesty
- Committee vote UI uses a free-text member-id + vote select (no hardcoded
  members). A richer member picker waits until the charter is exposed to the
  frontend — deferred, not faked.
- esbuild syntax-checked here; the authoritative TS gate is `pnpm tsc --noEmit`
  in your environment. A small type round-trip is possible and expected.

## Next (B22b)
Credit-Admin authorization panels (request-authorization + authorize) +
PipelineDealDetail Credit-Assessment stage lock surfacing the existing
doc-gated submit-to-credit.
