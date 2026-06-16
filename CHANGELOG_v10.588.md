# CHANGELOG v10.588 — Batch B22b: Credit-Admin authorization UI + pipeline stage lock

Second frontend half. Completes the credit operating model in the UI: the
Credit-Admin two-layer authorization (B20) and the Credit-Assessment stage lock
over the existing document-gated submit (B9/B10).

## Credit-Admin authorization UI
### types/creditAdmin.ts
- CreditAdminPermissions += can_request_authorization?, can_authorize?
- CreditAdminCase += authorization_requested(_by/_at), authorized(_by/_at)
- Request bodies: RequestAuthorizationRequest, AuthorizeRequest (both { note? }).

### lib/api.ts
requestCreditAdminAuthorization, authorizeCreditAdminCase fetchers.

### hooks/useCreditAdminMutations.ts
+requestAuthorization (Layer 1) +authorize (Layer 2), same MutationResult shape.

### pages/CreditAdminCaseDetail.tsx
- Authorization status card (requested / awaiting / authorized, with who).
- CaAuthPanel ×2 — Layer-1 "Request authorization" (can_request_authorization)
  and Layer-2 "Authorize" (can_authorize). Disburse remains gated on
  ready_for_disbursement, which Layer 2 sets — so the chain is officer-requests
  -> manager-authorizes -> disburse.
- "No actions" hint now accounts for the two new permissions.

## Pipeline Credit-Assessment stage lock — pages/PipelineDealDetail.tsx
AdvancePanel now LOCKS manual stage advance when the deal is at the
credit-assessment gate (stage matches /credit/i + /(assess|analys)/i) and has not
yet been submitted (no lms_application_id). Instead of the advance dropdown it
shows a locked card directing the user to the existing "Submit to Credit Analysis"
panel — which the backend already blocks until every required document is attached.
Once submitted (the deal gains an lms_application_id), the lock clears. This is a
UX lock over existing backend enforcement — no backend change.

## Verify (Josh's env — canonical gate)
  pushd frontend\web && pnpm tsc --noEmit && popd
Browser: open a credit-admin case with all conditions met as the officer
(Request authorization), then as the CA manager (Authorize), then Disburse. On a
pipeline deal at Credit Assessment, confirm the advance panel is locked until the
document checklist is complete and Submit to Credit Analysis succeeds.

## Notes
- No backend files in this batch — purely frontend over B20/B10 backends.
- esbuild syntax-checked here; pnpm tsc --noEmit in your env is authoritative.

## End-to-end now visible in the UI
pipeline (doc-gated submit, stage-locked) -> LMS (assign, info-request, decision,
offer issue/sign/validate, confirm, committee) -> Credit-Admin (conditions,
two-layer authorize, disburse). The full chain has a UI.
