#!/usr/bin/env python3
"""Verify B0: create a deal with portfolio fields, confirm they're in PG metadata
(not just JSON). Proves the write-completeness fix actually persists to Postgres.
"""
import sys, json, time
import urllib.request, urllib.error
sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8502"
def _req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE+path, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode(); return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        return e.code, {"detail": e.read().decode()[:120]}

st, body = _req("POST","/api/auth/login",body={"username":"frank0731","password":"EcoStaff0731"})
tok = body.get("access_token") or body.get("token")
print(f"login: {st}")

# create a deal with a manager override note (a B0 field)
st, r = _req("POST","/api/pipeline/deals",tok,{
    "client_name":f"B0 VERIFY {time.time()}","product_type":"Term Loan",
    "deal_value":1000000,"stage":"Lead","segment":"SME",
    "bsc_credit_to":"Immaculate Wue","manager_override_note":"B0 roundtrip test note",
    "portfolio_owner_code":"300716"})
did = (r.get("deal") or {}).get("id") if isinstance(r,dict) else None
print(f"created: {st} id={did}")

time.sleep(0.5)
# read directly from PG metadata
from utils.db import db
row = db.fetch_one("SELECT metadata FROM pipeline_deals WHERE id=%s", (did,))
if row and row.get("metadata"):
    md = row["metadata"] if isinstance(row["metadata"],dict) else json.loads(row["metadata"])
    print(f"\nPG metadata round-trip for {did}:")
    for f in ("bsc_credit_to","manager_override_note","portfolio_owner_code"):
        v = md.get(f)
        print(f"  {f:24} = {v!r}  {'OK' if v else 'MISSING'}")
else:
    print("no PG row/metadata found")
