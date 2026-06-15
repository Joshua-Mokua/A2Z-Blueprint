# CHANGELOG v10.574 — Batch B10: Submit-to-Credit gate (frontend) + stopgap removal

## What
Wires the B9 credit gate into the UI and makes the gated button the ONLY
path to credit — the silent "advance to Compliance" trigger is gone.

### Frontend
- types/pipeline.ts: CreditChecklistResponse + SubmitToCreditResponse.
- lib/api.ts: fetchCreditChecklist(dealId) + submitDealToCredit(dealId, docs).
- pages/PipelineDealDetail.tsx:
  - New "Submit to Credit Analysis" panel (accent stripe) below the advance
    panel. Fetches the checklist; renders each required document as a
    checkbox (pre-checked from what's already provided); the Submit button is
    disabled until every required document is checked.
  - On success: success toast with the new application id + reload (the deal
    now shows the "View Loan Application" cross-link).
  - On a server 400 (backstop): shows the missing-document message inline.
  - Already-submitted deals: shows a "Submitted" card with the application
    link instead of the form. Non-owners/non-admins: panel stays hidden.
  - Advance panel no longer claims "Loan application created" on Compliance.

### Backend
- api.py: submit-to-credit 400 now returns a readable string
  ("Cannot submit to credit — missing documents: ...") so the frontend
  surfaces it. (Structured missing list still comes from the checklist GET.)
- api_pipeline_mutations.py: removed "Compliance" from LMS_DEFERRED_STAGES
  (undoes the v10.568 stopgap). "Compliance" remains a valid ADVANCE stage —
  it just no longer silently creates a loan application. Config credit stages
  (Credit Review etc.) remain triggers for config-flow deals.

## End-to-end to test (UI)
1. As the deal OWNER (e.g. frank0731), open a deal → "Submit to Credit
   Analysis" panel lists the required documents.
2. Leave one unchecked → Submit is disabled. Check all → Submit enabled.
3. Submit → success toast + "View Loan Application →" appears; the deal shows
   "Submitted". The application is in Loan Applications.
4. As a manager/non-owner → no submit panel (oversight only).

## TypeScript gate
Run in your env (canonical):  pushd frontend\web && pnpm tsc --noEmit && popd

## Tests
Backend gate logic covered by tests/test_batchB9_credit_gate.py (from B9).
