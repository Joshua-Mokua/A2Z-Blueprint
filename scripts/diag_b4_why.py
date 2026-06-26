#!/usr/bin/env python3
"""Why does enrichment fail even when the read no longer throws?
Instruments UserManager._load under concurrency to record, per call:
  - did read_text throw? (retry exhausted?)
  - did json.loads succeed?
  - how many users in the parsed dict?
  - is frank0731 present?
This distinguishes 'read threw' from 'read got a valid-but-truncated file
missing records' (-> the WRITE is non-atomic, fix belongs on _save).
"""
import sys, threading, json as _json
sys.path.insert(0, ".")
from concurrent.futures import ThreadPoolExecutor

from utils.core import UserManager, DATA_DIR

USERS = DATA_DIR / "users.json"
results = []
lock = threading.Lock()

def probe(i):
    rec = {"i": i}
    # mimic exactly what _load's read does, with the retry
    import time
    raw = ""; threw = False
    for attempt in range(5):
        try:
            raw = USERS.read_text(encoding="utf-8"); break
        except Exception:
            threw = True; time.sleep(0.02*(attempt+1))
    rec["read_threw_then_recovered"] = threw and bool(raw)
    rec["read_failed"] = not bool(raw)
    n = -1; has_frank = False; parse_ok = False
    if raw:
        try:
            d = _json.loads(raw); parse_ok = True
            n = len(d); has_frank = "frank0731" in d
        except Exception:
            parse_ok = False
    rec["parse_ok"] = parse_ok; rec["n_users"] = n; rec["has_frank"] = has_frank
    with lock: results.append(rec)

# baseline
probe("serial")
b = results[-1]
print(f"SERIAL: n_users={b['n_users']} has_frank={b['has_frank']} parse_ok={b['parse_ok']}")

# concurrent: readers + writers (construct UserManager, which WRITES)
results.clear()
def writer():
    for _ in range(20):
        try: UserManager()   # constructs -> _save + ensure_* may write users.json
        except Exception: pass
wt = [threading.Thread(target=writer) for _ in range(4)]
for t in wt: t.start()
with ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(probe, range(10)))
for t in wt: t.join()

print(f"\n{'run':6} {'read_fail':>10} {'parse_ok':>9} {'n_users':>8} {'has_frank':>10}")
bad=0
for r in sorted(results, key=lambda x:str(x['i'])):
    if not r['has_frank']: bad+=1
    print(f"{str(r['i']):6} {str(r['read_failed']):>10} {str(r['parse_ok']):>9} {str(r['n_users']):>8} {str(r['has_frank']):>10}")
print(f"\nruns where frank0731 MISSING from a successfully-read file: {bad}/10")
print("If parse_ok=True but n_users is SMALL / has_frank=False -> the WRITE is non-atomic:")
print("readers get a valid-but-truncated file. Fix = atomic _save/save_users, NOT read retry.")
