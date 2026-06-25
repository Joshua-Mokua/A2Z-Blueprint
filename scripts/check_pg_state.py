#!/usr/bin/env python3
"""Is Postgres actually enabled + reachable, and does pipeline_deals have rows?
This decides whether the migration is 'flip write-primacy' (PG live) or
'PG isn't even on' (system is JSON-only and the mirror is a no-op).
"""
import os, sys
sys.path.insert(0, ".")
print("=== environment ===")
for k in ("A2Z_USE_DB","A2Z_DB_HOST","A2Z_DB_PORT","A2Z_DB_NAME","A2Z_DB_USER","A2Z_DB_SSLMODE"):
    v = os.getenv(k)
    print(f"  {k} = {v if v else '(unset)'}")
print(f"  A2Z_DB_PASSWORD = {'(set)' if os.getenv('A2Z_DB_PASSWORD') else '(unset)'}")

from utils.db import db
print("\n=== runtime ===")
ready = db.is_postgres_ready()
print(f"  is_postgres_ready(): {ready}")
print(f"  table_uses_db('pipeline_deals'): {db.table_uses_db('pipeline_deals')}")
if ready:
    try:
        n = db.fetch_scalar("SELECT count(*) FROM pipeline_deals", ())
        print(f"  pipeline_deals row count (PG): {n}")
        mx = db.fetch_scalar("SELECT max(id) FROM pipeline_deals", ())
        print(f"  max id (PG): {mx}")
    except Exception as e:
        print(f"  PG query failed: {e}")
else:
    print("  -> PG NOT live. System is JSON-only. The concurrency race is on JSON,")
    print("     and the 'DB-first' reads + _db_sync mirror are currently no-ops.")
    print("     Migration step 0 = stand up Postgres + enable A2Z_USE_DB=true.")

# compare to JSON
import json as _j
p = os.path.join("data","pipeline_deals.json")
if os.path.exists(p):
    jn = len(_j.loads(open(p,encoding="utf-8").read()))
    print(f"\n  pipeline_deals.json row count: {jn}")
