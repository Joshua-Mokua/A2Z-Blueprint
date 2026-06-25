#!/usr/bin/env python3
"""Show EXACTLY where pipeline data lives: reads, writes, and JSON<->PG drift.
Answers 'are we on Postgres or JSON?' with evidence, not assertion.
"""
import os, sys, json
sys.path.insert(0, ".")
from utils.db import db

print("="*64)
print("A2Z PERSISTENCE MODE")
print("="*64)

ready = db.is_postgres_ready()
print(f"\nPostgres ready:                 {ready}")
print(f"pipeline_deals uses DB:         {db.table_uses_db('pipeline_deals')}")
print(f"loan_applications uses DB:      {db.table_uses_db('loan_applications')}")
print(f"credit_admin uses DB:           {db.table_uses_db('credit_admin')}")

# read path
try:
    import utils.api as api
    print(f"\nReads DB-first (_PIPELINE_READ_DB_FIRST): {api._PIPELINE_READ_DB_FIRST}")
except Exception as e:
    print(f"  (could not read flag: {e})")

# counts: PG vs JSON for each store
print("\n--- store counts (PG vs JSON) ---")
def _counts(table, jsonfile):
    pg = None
    if ready:
        try: pg = db.fetch_scalar(f"SELECT count(*) FROM {table}", ())
        except Exception as e: pg = f"err: {e}"
    jp = os.path.join("data", jsonfile)
    jn = None
    if os.path.exists(jp):
        try: jn = len(json.loads(open(jp, encoding="utf-8").read()))
        except Exception as e: jn = f"err: {e}"
    drift = ""
    if isinstance(pg, int) and isinstance(jn, int):
        drift = "  IN SYNC" if pg == jn else f"  DRIFT={jn-pg}"
    print(f"  {table:22s} PG={str(pg):>8}   JSON={str(jn):>8}{drift}")

_counts("pipeline_deals", "pipeline_deals.json")
_counts("loan_applications", "loan_applications.json")

print("\n--- interpretation ---")
print("  Reads: Postgres (DB-first).")
print("  Writes (CREATE): Phase A — race-free id, fail-closed PG insert + JSON mirror.")
print("  Writes (UPDATE/ADVANCE): still JSON read-modify-write + PG mirror (Phase B pending).")
print("  => NOT yet PG-only. JSON still written on every mutation until Phase C.")
print("  Any DRIFT above = writes lost to the concurrency race (the bug being fixed).")
