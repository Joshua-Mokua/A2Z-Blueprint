#!/usr/bin/env python3
"""scripts/time_export.py — verify the _load_json cache fixed the analytics
bottleneck. Call 1 populates the cache; call 2+ should be near-instant.
"""
from __future__ import annotations
import sys, time
sys.path.insert(0, ".")
import utils.api as api
from utils.core import UserManager
um = UserManager()
md = um.users.get("william0001") or um.users.get("william001")
user = dict(md); user.setdefault("username", "william0001")
deals = api._acquire_scoped_deals(user)
print(f"{len(deals)} deals in scope\n")
def _t(label, fn):
    t0 = time.perf_counter(); fn(); dt=(time.perf_counter()-t0)*1000
    print(f"  {label:42s} {dt:9.1f} ms")
_t("analytics call 1 (populates _load_json cache)", lambda: api._compute_pipeline_analytics(deals))
_t("analytics call 2 (cached config)", lambda: api._compute_pipeline_analytics(deals))
_t("analytics call 3 (cached config)", lambda: api._compute_pipeline_analytics(deals))
print("\nExpect call 1 already fast (cache fills mid-call), calls 2/3 fast too.")
print("Was ~5500 ms before the fix.")
