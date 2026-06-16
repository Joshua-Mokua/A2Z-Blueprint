# CHANGELOG v10.577 — Batch B13: Postgres-first reads + atomic create

## Why
Standing rule: all data lives in PostgreSQL. B12's JSON-first read was an
emergency patch made while the sync was best-effort. This reverses it the
RIGHT way — Postgres-first reads, made safe by a reliable write path.

## Changes (utils/api.py)
1. _PIPELINE_READ_DB_FIRST = True
   List, summary, and analytics read PostgreSQL first again.
2. _db_sync_pipeline_deal no longer swallows errors.
   DB-unavailable still no-ops (early return); but if Postgres is UP and the
   write errors, it now RAISES. Silent swallowing was what let JSON and the DB
   drift (deals invisible to DB-first reads).
3. pipeline_deal_create is now ATOMIC.
   After add_deal it syncs to Postgres and verifies the row is present. If the
   sync fails OR the row isn't found, it rolls back the JSON add
   (PipelineManager.delete_deal) and returns 500 — so a deal is in BOTH stores
   or NEITHER. No more JSON-only deals.

## Net effect
Every created deal is guaranteed in Postgres; Postgres-first reads therefore see
every deal. JSON stays a lockstep mirror, so the validation queue (JSON) still
agrees. The divergence class is closed at the create boundary.

## Apply note
This obsoletes the B12 guard test (it asserted JSON-first). Remove it:
    git rm tests\\test_batchB12_json_first.py

## Test
tests/test_batchB13_postgres_first.py  (asserts Postgres-first default)
tests/test_batchB11_analytics.py        (analytics math, unchanged)

## Live verification (clean slate, DB up)
1. Create a deal as Frank (300731) in the UI -> it is D0001 and visible
   immediately in Frank's list; Immaculate (immaculate0716) sees it too.
2. scripts\\diag_pipeline_store.py shows the SAME deal in BOTH JSON and Postgres
   (no divergence).
