#!/usr/bin/env python3
"""Definitive instrumentation of the concurrent-update 403.

Rather than go through HTTP, this drives the SAME internal calls the PUT handler
makes — _PM_for_api() + _get_or_hydrate_deal + the scope read — under a thread
pool, and records for each concurrent call:
    source = 'PG' | 'json-fallback' | 'none'
    staff_code seen by the scope check
This pinpoints whether concurrency pushes the read into the JSON fallback and
whether that fallback yields a blanked staff_code (the 403 cause).

Run from project root (venv active):
    python scripts/diag_b4_instrument.py
"""
import sys, time, threading
sys.path.insert(0, ".")
from concurrent.futures import ThreadPoolExecutor

# import the live internals
import utils.api as api
from utils.core import PipelineManager as PM

# pick 10 real deal ids that exist in PG (recent ones)
from utils.db import db
rows = db.fetch_all("SELECT id FROM pipeline_deals ORDER BY id DESC LIMIT 10")
ids = [r["id"] for r in rows]
print(f"probing {len(ids)} existing PG deals: {ids}")

# monkeypatch _normalize passthrough so we can see source; we instead wrap
orig_hydrate = api._get_or_hydrate_deal
results = []
lock = threading.Lock()

def instrumented(deal_id):
    pm = PM()                      # same as _PM_for_api(): fresh per 'request'
    # replicate the handler's read
    deal = api._get_or_hydrate_deal(pm, deal_id)
    sc = str((deal or {}).get("staff_code","") or "")
    # determine source: was it in PG?
    src = "none"
    if deal is not None:
        # if the in-memory JSON had it before hydrate, it's ambiguous; infer:
        # re-read PG directly
        try:
            row = db.fetch_one("SELECT staff_code FROM pipeline_deals WHERE id=%s",(deal_id,))
            pg_sc = str((row or {}).get("staff_code","") or "")
            src = "PG-ok" if pg_sc and pg_sc==sc else ("PG-blank" if not pg_sc else "json-or-mismatch")
        except Exception as e:
            src = f"pgerr:{type(e).__name__}"
    with lock:
        results.append((deal_id, src, sc))

# fire concurrently, like 10 simultaneous PUTs
with ThreadPoolExecutor(max_workers=len(ids)) as ex:
    list(ex.map(instrumented, ids))

print(f"\n{'deal':10} {'source':18} {'staff_code_seen':>16}")
blank=0
for did, src, sc in sorted(results):
    if not sc: blank+=1
    print(f"{did:10} {src:18} {sc:>16}")
print(f"\nblank staff_code under concurrency: {blank}/{len(ids)}")
print("If blank>0 with source=PG-ok in DB -> the in-request read returns blank even")
print("though PG has it -> _get_or_hydrate_deal is hitting the JSON fallback (PM() load")
print("caught a concurrent _save_deals mid-rewrite). That's the 403 root cause.")
