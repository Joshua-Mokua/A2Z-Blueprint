#!/usr/bin/env python3
"""Profile _compute_pipeline_analytics with cProfile to find the hot function."""
import sys, cProfile, pstats, io
sys.path.insert(0, ".")
import utils.api as api
from utils.core import UserManager
um = UserManager()
md = um.users.get("william0001") or um.users.get("william001")
user = dict(md); user.setdefault("username", "william0001")
deals = api._acquire_scoped_deals(user)
print(f"{len(deals)} deals; profiling analytics...\n")

pr = cProfile.Profile()
pr.enable()
api._compute_pipeline_analytics(deals)
pr.disable()

s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
ps.print_stats(20)
# print the top hot lines
out = s.getvalue()
print("\n".join(out.splitlines()[:35]))
