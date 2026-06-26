#!/usr/bin/env python3
"""Isolate the 403 cause: is it read-your-writes timing on the CREATE, or the
UPDATE path itself? Creates 10 deals, WAITS for them to settle, verifies each is
readable+owned, THEN fires concurrent updates. If 403s vanish with the wait, the
bug is create-commit timing (not the update path) -> B4 targets create persistence.
"""
import sys, json, time, threading
import urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, ".")

BASE = "http://127.0.0.1:8502"
def _req(method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE+path, data=data, method=method)
    r.add_header("Content-Type","application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode(); return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, {"detail": e.read().decode()[:80]}
    except Exception as e:
        return 0, {"detail": str(e)}

st, b = _req("POST","/api/auth/login",body={"username":"frank0731","password":"EcoStaff0731"})
tok = b.get("access_token") or b.get("token")
print(f"login: {st}")

# create 10
made=[]
for i in range(10):
    st,r=_req("POST","/api/pipeline/deals",tok,
        {"client_name":f"B4-ISO {i} {time.time()}","product_type":"Term Loan",
         "deal_value":1000000,"stage":"Lead","segment":"SME"})
    did=(r.get("deal") or {}).get("id") if isinstance(r,dict) else None
    if did: made.append(did)
print(f"created {len(made)}: {made}")

# WAIT and verify each is readable + correctly owned BEFORE updating
print("\nwaiting 3s for creates to settle, then verifying ownership pre-update...")
time.sleep(3)
pre_ok=0
for did in made:
    st,gb=_req("GET",f"/api/pipeline/deals/{did}",tok)
    deal=(gb.get("deal") or {}) if isinstance(gb,dict) else {}
    sc=str(deal.get("staff_code","") or "")
    if sc: pre_ok+=1
print(f"pre-update: {pre_ok}/{len(made)} deals have a non-empty staff_code on read")

# NOW fire concurrent updates (creates are long settled)
sent=f"ISO-{int(time.time())}"
stats=[]; lock=threading.Lock()
def _upd(did):
    st,bd=_req("PUT",f"/api/pipeline/deals/{did}",tok,{"next_action":f"{sent}-{did}"})
    with lock: stats.append((did,st))
with ThreadPoolExecutor(max_workers=len(made)) as ex:
    list(ex.map(_upd, made))

forbidden=sum(1 for _,s in stats if s==403)
ok=sum(1 for _,s in stats if s==200)
print(f"\nconcurrent updates AFTER settle: {ok} x 200, {forbidden} x 403")
print("\nINTERPRETATION:")
print("  403s ~0 now -> bug was CREATE-commit timing (read-your-writes), not update path.")
print("            -> B4 = make create persist to PG synchronously/atomically before returning.")
print("  403s still high -> the update path's own read races; deeper look needed.")
