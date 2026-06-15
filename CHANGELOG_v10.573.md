# CHANGELOG v10.573 — Batch B9: Submit-to-Credit gate (backend)

## What
An explicit, document-gated credit submission — the proper flow you described,
replacing the silent stage trigger.

utils/api.py:
- _get_required_documents_for_deal(deal): required docs from lms_config's tiered
  document_checklist — default + above_10m (amount > 10M) + corporate + mortgage.
- GET  /api/pipeline/deals/{id}/credit-checklist
       -> {required, provided, missing, already_submitted, lms_application_id, can_submit}
- POST /api/pipeline/deals/{id}/submit-to-credit  {documents_provided: [...]}
       - owner or admin only; not already submitted; not terminal.
       - missing required docs -> HTTP 400 {message, missing, required}.
       - complete -> create_from_pipeline_deal (canonical handoff) -> records
         lms_application_id + documents_provided + submitted_to_credit on the
         deal, syncs to Postgres (H5), audits.

## How to test now (via /api/docs, before the UI lands in B10)
1. GET  /api/pipeline/deals/{id}/credit-checklist  -> see required + missing.
2. POST /api/pipeline/deals/{id}/submit-to-credit with a PARTIAL list -> 400 +
   the missing documents.
3. POST again with the full required list -> 200 + application_id; the deal now
   carries lms_application_id and appears in Loan Applications.

## Not yet (next, B10)
- Frontend "Submit to Credit Analysis" panel (checklist + button + missing-doc
  error) on the deal detail.
- Remove the silent Compliance auto-trigger (v10.568 stopgap) so this gate is
  the ONLY path to credit. Kept for now so nothing breaks mid-change.

## Verified
- Personal Loan 5M -> 6 default docs; partial provided -> blocked.
- Corporate 50M -> default + above_10m + corporate tiers.

## Test
tests/test_batchB9_credit_gate.py (run in the project venv).
