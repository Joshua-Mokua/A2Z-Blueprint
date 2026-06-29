#!/usr/bin/env python3
"""scripts/verify_auth_cache.py — in-process proof the cached user store works
on the REAL UserManager (no server, no mutation to users.json).

    python scripts\\verify_auth_cache.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.core import UserManager

a = UserManager()
b = UserManager()
assert a.users is b.users, "FAIL: instances do not share the cached store"
n = len(a.users)
for _ in range(200):
    UserManager()                     # must be cheap; must not reload/re-heal
assert len(a.users) == n, "FAIL: store size changed under repeated construction"
# read a known scoped login (non-mutating)
present = "frank0731" in a.users
print(f"shared cache: OK (a.users is b.users); users={n}; frank0731 present={present}")
print("200 constructions did not change the store -> ensure_* did not re-fire")
print("AUTH-CACHE VERIFY PASSED")
