# CHANGELOG v10.576 — Batch B12: pipeline reads JSON-first (fix invisible deals)

## Problem (diagnosed via scripts/diag_pipeline_store.py)
JSON store had 17 deals; Postgres had 2. The list, analytics, and summary read
Postgres FIRST, and the create path only mirrors to Postgres best-effort
(_db_sync_pipeline_deal swallows errors), so 15 freshly-created/older deals were
invisible. That is why newly created deals "disappeared" and the count stuck.

## Fix
utils/api.py:
- New module flag `_PIPELINE_READ_DB_FIRST = False`.
- Three pipeline READ paths now read the JSON store (PipelineManager) first,
  which is the synchronous source of truth and already what the validation
  queue reads — so list, analytics, summary, and validation now AGREE:
    * GET /api/pipeline/deals      (list)
    * GET /api/pipeline/summary    (dashboard tiles)
    * GET /api/pipeline/analytics  (funnel; via _acquire_scoped_deals)
- Postgres remains a best-effort mirror for mutations. Flip the flag back to
  True only once the DB sync is guaranteed (PENDING: unify reads on Postgres).
- Scope + enrichment unchanged — still applied on the JSON path.

## Result after applying + restart
The list/analytics/summary show ALL in-scope deals (not just the 2 that
happened to sync). Count reflects reality.

## Note on scope (not a code bug)
Deals owned by non-register codes (0001 / ADMIN001) stay out of scope even for
the MD, because the MD's view is the 1438 *register* staff codes and those test
owners aren't in the register. For the demo, create deals as register staff
(e.g. Frank 300731). This is expected behaviour, not the bug fixed here.

## Tests
tests/test_batchB12_json_first.py (guards the default).
Analytics math still covered by tests/test_batchB11_analytics.py.
