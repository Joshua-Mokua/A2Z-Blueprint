#!/usr/bin/env python3
"""CONFIRM the root cause: _enrich_identity_from_store fails to fill staff_code
under concurrency because UserManager() reads users.json per call and races writes.

Drives _enrich_identity_from_store directly with a thin JWT dict (username only,
like a real decoded token) under a thread pool, recording whether staff_code got
filled. Also stresses a concurrent UserManager() load to surface read failures.
"""
import sys, threading
sys.path.insert(0, ".")
from concurrent.futures import ThreadPoolExecutor

from utils.auth_jwt import _enrich_identity_from_store

USERNAME = "frank0731"   # -> should enrich to staff_code 300731
EXPECT = "300731"

results = []
lock = threading.Lock()

def probe(i):
    user = {"username": USERNAME, "role": "Relationship Manager", "scope": "full"}
    try:
        _enrich_identity_from_store(user)
        sc = str(user.get("staff_code", "") or "")
        ok = (sc == EXPECT)
    except Exception as e:
        sc = f"ERR:{type(e).__name__}"; ok = False
    with lock:
        results.append((i, sc, ok))

# serial baseline
probe("serial")
print(f"SERIAL: staff_code={results[-1][1]} ok={results[-1][2]}")

# concurrent burst — also spin a few UserManager loads in parallel to mimic
# the mixed read/write pressure of real traffic
def churn():
    from utils.core import UserManager
    for _ in range(30):
        try: UserManager()
        except Exception: pass

results.clear()
churn_threads = [threading.Thread(target=churn) for _ in range(4)]
for t in churn_threads: t.start()
with ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(probe, range(10)))
for t in churn_threads: t.join()

print(f"\n{'run':10} {'staff_code':>14} {'ok':>6}")
empty=0
for i, sc, ok in sorted(results, key=lambda x:str(x[0])):
    if not ok: empty+=1
    print(f"{str(i):10} {str(sc):>14} {str(ok):>6}")
print(f"\nenrichment FAILED (staff_code not filled): {empty}/10")
print("If empty>0 -> CONFIRMED: _enrich_identity_from_store races users.json ->")
print("blank staff_code -> empty visible set -> 403. B4 = retry/cache the user read.")
