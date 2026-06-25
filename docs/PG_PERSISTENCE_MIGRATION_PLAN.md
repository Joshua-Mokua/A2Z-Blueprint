# Postgres Persistence Migration Plan

**Author:** Claude session, recorded by Joshua Mokua
**Date:** 2026-06-25
**Trigger:** Stress Phase 4 (concurrency/load) confirmed catastrophic data loss
under concurrent writes — 20 parallel creates collapsed to 0 net persisted; 10
concurrent updates to distinct deals lost 9. Root cause: JSON-file
read-modify-write with no locking, `PipelineManager()` re-instantiated per
request. Deployment target is multi-worker/multi-host, where a file lock cannot
coordinate — so Postgres-transactional persistence is the only correct fix.

---

## What already exists (grounded 2026-06-25)

The PG layer is substantially built — this is **flip primacy + close gaps**, not
greenfield:

- `utils/db.py` `Database` class with `transaction()`, atomic `upsert()`
  (`INSERT ... ON CONFLICT DO UPDATE`, psycopg2-composed/safe), `execute`,
  `fetch_one/all/scalar`.
- `pipeline_deals` table exists: `id VARCHAR(50) PRIMARY KEY`, typed columns +
  `metadata JSONB`, indexes on stage/staff/client.
- `loan_applications` and `credit_admin` tables also exist (`TABLE_USE_DB: True`)
  — **they share the same race** and must be migrated too.
- Reads are ALREADY DB-first: `_PIPELINE_READ_DB_FIRST = True` (api.py:2610).
  `_acquire_scoped_deals` selects from `pipeline_deals` (the JSON-first docstring
  is stale).
- A mirror writer exists: `_db_sync_pipeline_deal(deal)` upserts a deal to PG
  after the JSON write. This becomes (part of) the authoritative write path.

## The actual gap

WRITES are JSON-authoritative: endpoints call `PipelineManager.add_deal` /
`update_deal` / `update_stage`, which mutate the in-memory list and rewrite the
whole JSON file (the race), then best-effort mirror to PG. We must invert this:
**PG becomes the write authority via atomic ops; JSON becomes a derived mirror
(or is retired).**

Two distinct races, both confirmed:
1. **ID generation:** `id = f"D{len(self.deals)+1}"` — concurrent creates compute
   the same id. PG `PRIMARY KEY` would reject the dup (one create fails loudly
   instead of silently clobbering), but we want a race-free id source.
2. **Lost update / lost create:** whole-file rewrite from a per-request snapshot
   clobbers concurrent writes to OTHER records.

## Scope (grounded call-site counts, api.py)

- `add_deal`: 2 call-sites
- `update_deal`: 9 call-sites
- `update_stage`: 2 call-sites
- Plus the sibling stores: `loan_applications`, `credit_admin` (similar mutation
  helpers in their managers).

---

## Phased plan (each phase independently shippable + harness-green)

### Phase A — Race-free ID + atomic create (pipeline)
- Replace `D{len+1}` with a race-free id. Options:
  - **PG sequence** `pipeline_deal_seq` → `D{nextval:04d}` (keeps the D#### format
    the UI/tests expect). Preferred — preserves id shape.
  - UUID (simpler, but breaks the human-readable D#### convention the harness and
    UI rely on). Rejected for that reason.
- `add_deal` becomes: `INSERT INTO pipeline_deals (...) VALUES (...) RETURNING id`
  inside a transaction, id from the sequence. No read-modify-write.
- Keep writing the JSON mirror for now (belt-and-suspenders) but PG is authoritative.
- **Gate:** harness 295/295 + re-run stress_concurrency Probe 1 → 0 dup IDs, 0 lost.

### Phase B — Atomic update/advance (pipeline)
- `update_deal` / `update_stage` become `UPDATE pipeline_deals SET ... WHERE id=%s`
  (targeted row update — no whole-list rewrite), or `upsert()` on the full row
  read-modified inside a single `transaction()` with `SELECT ... FOR UPDATE` to
  serialize concurrent mutations of the SAME deal.
- Field-merge semantics: typed columns updated directly; rich/extra fields merged
  into `metadata` JSONB (`metadata = metadata || %s::jsonb`).
- **Gate:** harness 295/295 + stress_concurrency Probe 2 → all concurrent
  distinct-deal updates persist; Probe 3 → same-deal advances serialize cleanly.

### Phase C — Retire / demote the JSON mirror (pipeline)
- Once PG writes are authoritative and proven, the JSON file becomes either
  (a) a read-through cache rebuilt from PG, or (b) retired. Decide based on
  whether any legacy Streamlit page still reads the JSON directly (AUDIT NEEDED:
  grep Streamlit pages for `pipeline_deals.json` reads).
- `PipelineManager` reads become thin wrappers over PG (or are removed from the
  hot path). Fixes the 6s/20-read latency too (no per-request full-file load).
- **Gate:** harness 295/295; read-load probe p95 well down from 5.8s.

### Phase D — Apply the same pattern to loan_applications + credit_admin
- Same race, same fix. Sequenced after pipeline is proven so the pattern is
  established and the blast radius is one store at a time.
- **Gate:** harness 295/295 after each; a concurrency probe extended to LMS +
  credit-admin mutations.

---

## Risks & mitigations
- **Dual-write skew during transition:** while both JSON and PG are written,
  they can diverge. Mitigation: PG authoritative for reads (already true); JSON
  mirror best-effort; a reconciliation script to detect drift.
- **The metadata JSONB merge** must not drop fields. Mitigation: explicit
  `metadata || excluded` merge + a round-trip test per phase.
- **Transaction scope / connection pooling** under multi-worker: confirm
  `_get_pool()` is process-safe (psycopg2 pool per process). AUDIT NEEDED.
- **Harness is sequential** — it will NOT catch a regression in concurrency.
  Each phase must re-run `stress_concurrency.py`, not just the harness.

## Pre-work / audits needed before Phase A
1. Confirm psycopg2 connection pool is per-process and safe under uvicorn workers.
2. Grep all Streamlit pages + scripts for direct `pipeline_deals.json` reads
   (anything reading JSON directly breaks when PG becomes authoritative).
3. Confirm `_db_sync_pipeline_deal` field map covers every column (it notes
   deal_value->amount, product_type->product, category in metadata).
4. Decide id scheme (PG sequence `D{nextval}` recommended).

## Definition of done
- `stress_concurrency.py` at n=20 (and n=50): 0 HOLES across all probes.
- Harness 295/295 throughout.
- Read-load p95 < 1s.
- All three stores (pipeline, loan_applications, credit_admin) PG-authoritative.
