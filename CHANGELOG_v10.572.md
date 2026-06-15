# CHANGELOG v10.572 — Batch B8: Postgres pipeline list enforces scope + permissions

## Problem (security + visibility)
The pipeline list has two read paths. The Postgres branch returned
`SELECT * FROM pipeline_deals` with NO cascade-scope filter and NO per-deal
permission enrichment; only the JSON fallback applied them. Effects when
Postgres is active:
  - cascade scope NOT enforced on the list -> every user could see every deal,
  - per-deal "YOU CAN" permissions empty (no can_edit/can_advance/etc.).
A scoped manager (immaculate) saw 0 only because the DB table is currently
empty while her deal lives in the JSON store — exposing a second issue (below).

## Fix
utils/api.py — the Postgres branch now applies get_visible_staff_codes +
filter_deals_by_visible_codes and enrich_deal_with_permissions, matching the
JSON branch. (Removed the SQL LIMIT/OFFSET so scope is applied before paging,
then slices after — same as the JSON branch.)

## Verified
- _normalize_db_deal_row keeps staff_code (+ maps amount->deal_value).
- filter_deals_by_visible_codes drops out-of-scope DB rows.

## Known divergence (recorded in PENDING_ITEMS.md)
The list reads Postgres; the validation queue + get_pending_validations read the
JSON store (PipelineManager). They can disagree (a deal in JSON but not the DB,
or vice versa). The clean path for testing is a full reset so both start empty,
then create fresh (writes to both via H5). The durable fix is to unify reads on
Postgres (the architectural aim).

## Test
tests/test_batchB8_db_list_scope.py (run in the project venv).
