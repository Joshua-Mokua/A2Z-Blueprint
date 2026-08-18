#!/usr/bin/env python3
"""Diagnose the concurrent-update lost-write: is the loss in PG or JSON?
Creates K deals, concurrently PUTs a unique sentinel to each, then checks BOTH
PG (direct) and the GET endpoint for each sentinel.
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
        return e.code, {"detail": e.read().decode()[:120]}
    except Exception as e:
        return 0, {"detail": str(e)}

st, body = _req("POST","/api/auth/login",body={"username":"frank0731","password":"EcoStaff0731"})
tok = body.get("access_token") or body.get("token")
print(f"login: {st}")

K = 10
made = []
for i in range(K):
    st, body = _req("POST","/api/pipeline/deals",tok,
        {"client_name":f"UPD-DIAG {i} {time.time()}","product_type":"Term Loan",
         "deal_value":1000000,"stage":"Lead","segment":"SME"})
    did = (body.get("deal") or {}).get("id") if isinstance(body,dict) else None
    if did: made.append(did)
print(f"created {len(made)} deals: {made}")

sentinel = f"SENT-{int(time.time())}"
statuses = []
lock = threading.Lock()
def _upd(did):
    st, body = _req("PUT", f"/api/pipeline/deals/{did}", tok, {"next_action": f"{sentinel}-{did}"})
    with lock: statuses.append((did, st, body.get("detail","")[:60] if isinstance(body,dict) else ""))

with ThreadPoolExecutor(max_workers=len(made)) as ex:
    list(ex.map(_upd, made))
time.sleep(1.5)

print("\nPUT statuses:")
for did, st, detail in sorted(statuses):
    print(f"  {did}: {st} {detail}")

# check PG directly vs GET endpoint
from utils.db import db
print(f"\n{'deal':10} {'in_PG':>22} {'via_GET':>22}")
pg_ok = get_ok = 0
for did in made:
    row = db.fetch_one("SELECT metadata FROM pipeline_deals WHERE id=%s", (did,))
    pg_na = ""
    if row and row.get("metadata"):
        md = row["metadata"] if isinstance(row["metadata"], dict) else json.loads(row["metadata"])
        pg_na = str(md.get("next_action") or "")
    # also check the dedicated column? next_action may be in metadata only
    st, body = _req("GET", f"/api/pipeline/deals/{did}", tok)
    deal = (body.get("deal") or {}) if isinstance(body,dict) else {}
    get_na = str(deal.get("next_action") or "")
    pg_hit = pg_na.startswith(sentinel)
    get_hit = get_na.startswith(sentinel)
    pg_ok += pg_hit; get_ok += get_hit
    print(f"  {did:10} {('YES' if pg_hit else 'no'):>22} {('YES' if get_hit else 'no'):>22}")

print(f"\nPG has sentinel:  {pg_ok}/{len(made)}")
print(f"GET has sentinel: {get_ok}/{len(made)}")
print("\nIf PG=high but GET=low -> read path issue. If BOTH low -> the PUT's PG")
print("write itself is being lost (the _db_sync after a clobbered JSON read).")
