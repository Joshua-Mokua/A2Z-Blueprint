# CHANGELOG v10.556 — Hardening H5: pipeline DB read/write consistency

## Defect (D-02)
Pipeline LIST/detail reads are DB-first (Postgres holds the 294 seeded deals),
but every runtime mutation (create/refer/advance/update/cancel) wrote ONLY the
JSON store via PipelineManager. Result: created/changed deals never appeared
in the DB-backed list (count stuck at 294; new deal got JSON id "D0010"
because the JSON store had only 9 rows — proving the 294 live only in DB).
Also: the list returned raw DB columns (amount/product), but the frontend
reads deal_value/product_type, so the VALUE column rendered "—".

## Fix (utils/api.py)
- _db_sync_pipeline_deal(deal): UPSERT (INSERT ... ON CONFLICT (id) DO UPDATE)
  the deal's current JSON state into pipeline_deals when Postgres is available.
  Field map: deal_value->amount, product_type->product, pipeline_category->
  metadata. Best-effort; never breaks the (already-succeeded) JSON write.
  Wired after all 6 mutations (create, refer, update, advance, cancel
  request, cancel approve).
- _normalize_db_deal_row(row): maps DB columns back to frontend field names
  (amount->deal_value, product->product_type, metadata->pipeline_category);
  applied to the list response so values/products display.

## Verified
- py_compile OK; UPSERT SQL builds (18 cols/placeholders); field mapping
  correct; empty dates -> NULL (no DATE insert error).
- Behaviour to confirm in-app: create a deal -> it appears in the list with
  its value, and opens in detail.

## Known follow-ons (separate)
- The 294 PRE-SEEDED deals are DB-only; the detail route reads JSON, so
  opening one of those still 404s. New deals (synced to both) work in both.
  A DB-first detail branch would close that — next batch.
