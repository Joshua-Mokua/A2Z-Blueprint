#!/usr/bin/env python3
"""Diagnose why concurrent creates show +0 persisted. Fires N creates, prints
each one's status + returned id, then queries PG directly for those ids.
"""
import sys, json, threading, time
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8502"
def _req(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, {"detail": e.read().decode()[:200]}
    except Exception as e:
        return 0, {"detail": str(e)}

st, body = _req("POST", "/api/auth/login", body={"username":"frank0731","password":"EcoStaff0731"})
tok = body.get("access_token") or body.get("token")
print(f"login: {st}")

from utils.db import db
pg_before = db.fetch_scalar("SELECT count(*) FROM pipeline_deals", ())
print(f"PG count before: {pg_before}")

N = 11
results = []
lock = threading.Lock()
def _create(i):
    st, body = _req("POST", "/api/pipeline/deals", tok, {
        "client_name": f"DIAG {i} {time.time()}", "product_type":"Term Loan",
        "deal_value":1000000, "stage":"Lead", "segment":"SME"})
    did = (body.get("deal") or {}).get("id") if isinstance(body,dict) else None
    with lock:
        results.append((i, st, did, body.get("detail","")[:80] if isinstance(body,dict) else ""))

with ThreadPoolExecutor(max_workers=N) as ex:
    list(ex.map(_create, range(N)))

time.sleep(1.5)
pg_after = db.fetch_scalar("SELECT count(*) FROM pipeline_deals", ())
print(f"PG count after:  {pg_after}  (delta={pg_after-pg_before})\n")

print("per-create results:")
ids = []
for i, st, did, detail in sorted(results):
    print(f"  [{i:2}] status={st} id={did} {detail}")
    if did: ids.append(did)

print(f"\nreturned ids: {sorted(set(ids))} ({len(ids)} total, {len(set(ids))} unique)")
# are those ids actually in PG?
if ids:
    found = db.fetch_all("SELECT id FROM pipeline_deals WHERE id = ANY(%s)", (ids,))
    found_ids = {r["id"] for r in found}
    print(f"of those, IN PG: {sorted(found_ids)} ({len(found_ids)})")
    print(f"NOT in PG: {sorted(set(ids)-found_ids)}")
