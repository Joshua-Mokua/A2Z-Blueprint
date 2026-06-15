# CHANGELOG v10.557 — Hardening H6: Pipeline->LMS handoff surfacing

## Context
Advancing a pipeline deal to an LMS-handoff stage (Compliance) auto-creates a
LoanApplication (handle_lms_handoff -> create_from_pipeline_deal) and the
advance RESPONSE already returns lms_application_id. The frontend already shows
a toast and a cross-link button — but the button is gated on
deal.lms_application_id, which was NEVER written onto the deal. So the link
never appeared and did not survive reload: the handoff was an invisible
side-effect.

## Fix (utils/api.py only)
1. Advance route: after a successful handoff, persist the id onto the deal
   (pm.update_deal {lms_application_id}), re-fetch, and _db_sync to Postgres.
2. _db_sync_pipeline_deal: carry lms_application_id in the deal's metadata
   (no schema change — pipeline_deals has no such column).
3. _normalize_db_deal_row: surface lms_application_id from metadata on DB reads.
The PipelineDeal model has extra="allow", so the id flows through responses.

## Verified
- py_compile OK; metadata round-trip returns the id; extra="allow" model_dump
  carries it; update_deal merges arbitrary keys (no whitelist drop); frontend
  reloadDeal() after advance re-fetches detail (JSON) which now carries the id.

## Result
Advance a deal to Compliance -> toast "Loan application created" -> the deal
now shows a working "Open loan application" cross-link to /lms/{id}, on the
spot and after reload. The credit chain is legible end-to-end.
