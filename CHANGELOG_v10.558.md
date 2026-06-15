# CHANGELOG v10.558 — Hardening H7: DB-first detail + mutation hydration

## Symptom
Clicking a pre-seeded deal (e.g. DEAL01110) returned 404 "out-of-scope".
Reason: the LIST read is DB-first (294 deals in Postgres), but the DETAIL and
MUTATION routes read only the JSON store via pm.get_deal — and those 294 deals
exist only in the DB. So they could neither be opened nor advanced.

## Fix (utils/api.py)
_get_or_hydrate_deal(pm, deal_id): returns the JSON deal if present; otherwise
loads the row from Postgres, normalizes it (amount->deal_value, etc.), and
registers it on the request-scoped PipelineManager (pm.deals.append) so
update_stage/update_deal operate on it. Mutations then re-sync to Postgres via
_db_sync_pipeline_deal (H5), keeping the DB authoritative. Wired into all 6
read sites: detail, update (PUT), advance, validate, cancel/request,
cancel/approve. Returns None (clean 404) if the deal is in neither store.

## Verified
- py_compile OK; helper is non-recursive (calls pm.get_deal internally);
  JSON deals still resolve; a DB-only deal hydrates with correct deal_value/
  product_type and becomes mutatable; missing id -> None.

## Result
Any deal in the list — seeded or created — now opens in detail and can be
advanced (which is what makes the Pipeline->LMS handoff testable on the
seeded portfolio). This advances the JSON->Postgres migration: detail + all
mutations are now Postgres-aware.
