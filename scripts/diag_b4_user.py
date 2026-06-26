#!/usr/bin/env python3
"""Test the new hypothesis: under concurrency, the USER's own staff_code
(user_data['staff_code']) and/or get_staff_roster() come back empty, collapsing
get_visible_staff_codes to an empty set -> 403 on every deal.

Drives get_visible_staff_codes directly under a thread pool with a fixed,
known-good user dict, and separately stresses get_staff_roster(), recording:
  - my_code seen
  - roster size
  - size of returned visible set
  - whether the known owner code 300731 is in it
"""
import sys, threading
sys.path.insert(0, ".")
from concurrent.futures import ThreadPoolExecutor

from utils.api_pipeline_scope import get_visible_staff_codes, get_staff_roster

# the OWNER persona used by the diag (frank0731 -> staff_code 300731)
USER = {"username": "frank0731", "staff_code": "300731", "role": "Relationship Manager"}
OWNER = "300731"

results = []
lock = threading.Lock()

def probe(i):
    # 1) roster health
    try:
        r = get_staff_roster()
        rsize = 0 if r is None else len(r)
    except Exception as e:
        rsize = f"ERR:{type(e).__name__}"
    # 2) visible codes for the known-good user
    try:
        vis = get_visible_staff_codes(dict(USER))   # copy, like a fresh request
        vsize = len(vis)
        has_owner = OWNER in vis
    except Exception as e:
        vsize = f"ERR:{type(e).__name__}"; has_owner = False
    with lock:
        results.append((i, rsize, vsize, has_owner))

# serial baseline
probe("serial-0")
base = results[-1]
print(f"SERIAL baseline: roster={base[1]} visible_set={base[2]} has_300731={base[3]}")

# concurrent burst (like 10 simultaneous PUT scope checks)
results.clear()
with ThreadPoolExecutor(max_workers=10) as ex:
    list(ex.map(probe, range(10)))

print(f"\n{'run':10} {'roster':>10} {'visible':>10} {'has_owner':>10}")
miss=0
for i, rsize, vsize, has in sorted(results, key=lambda x:str(x[0])):
    if not has: miss+=1
    print(f"{str(i):10} {str(rsize):>10} {str(vsize):>10} {str(has):>10}")
print(f"\nruns MISSING owner 300731 from visible set: {miss}/10")
print("If miss>0 -> get_visible_staff_codes races (roster empty or my_code lost) ->")
print("THAT is the 403 root cause, and B4 makes the roster/visible computation race-free.")
