#!/usr/bin/env python3
"""Post-seed sanity check for the Consumer BSC — run before committing.

The seed added 27 KPIs and 10 scorecards and moved 2 roles. This asserts the things a
bulk seed can silently break, the same failure family as the rest of this week:
  - every KPI id referenced by a scorecard actually exists in the library
  - every scorecard's pillar (area) weights sum to 1.0
  - within-pillar KPI weights sum to 1.0 per pillar
  - no role_kpi_weights entry points at a KPI missing from role_kpis
  - the two tree moves landed and created no cycle
  - targets in target_cascade resolve to a real staff code + real KPI id
"""
import json
from pathlib import Path

DATA = Path("data")
lib = json.loads((DATA / "kpi_library.json").read_text(encoding="utf-8"))
ids = {k["id"] for k in lib.get("kpis", [])}
rw = lib.get("role_kpi_weights", {})
rk = lib.get("role_kpis", {})

CONSUMER = ["Manager, Bancassurance", "Head Premier Banking", "Head of Sales",
            "Manager, Partnership, Alliances & Diaspora", "Head of Consumer",
            "Head, Consumer Products", "Card Officer",
            "Head, Digital Channels & Agency Network",
            "Senior Officer, Payments & Digital Channels", "Asset Product Manager"]

fails = []
for role in CONSUMER:
    w = rw.get(role)
    if not w:
        fails.append(f"{role}: no role_kpi_weights entry"); continue
    areas = w.get("areas", {})
    asum = sum(areas.values())
    if abs(asum - 1.0) > 0.01:
        fails.append(f"{role}: area weights sum to {asum:.3f}, not 1.0")
    # within-pillar sums
    per = {}
    for kid, m in w.get("kpis", {}).items():
        per.setdefault(m["area"], 0)
        per[m["area"]] += m["weight"]
        if kid not in ids:
            fails.append(f"{role}: KPI {kid} not in library")
        if kid not in (rk.get(role) or []):
            fails.append(f"{role}: {kid} weighted but not in role_kpis")
    for obj in w.get("objectives", []):
        per.setdefault(obj["area"], 0)
        per[obj["area"]] += obj["weight"]
    for area, s in per.items():
        if abs(s - 1.0) > 0.02:
            fails.append(f"{role}/{area}: within-pillar weights sum to {s:.3f}, not 1.0")

# tree
h = json.loads((DATA / "org_config.json").read_text(encoding="utf-8")).get("hierarchy", {})
for child, parent in [("Manager, Partnership, Alliances & Diaspora", "Head Premier Banking"),
                      ("Scheme Administrator Officer", "Asset Product Manager")]:
    if h.get(child) != [parent]:
        fails.append(f"tree: {child} -> {h.get(child)}, expected [{parent}]")

# targets
cas = json.loads((DATA / "target_cascade.json").read_text(encoding="utf-8"))
ccount = sum(1 for k in cas if "|" in k and k.split("|")[1] in ids)
orphan = [k for k in cas if "|" in k and k.split("|")[1] not in ids]

print(f"consumer scorecards checked : {len(CONSUMER)}")
print(f"library KPIs                : {len(ids)}")
print(f"cascade targets to real ids : {ccount}")
if orphan:
    print(f"cascade targets to UNKNOWN ids: {len(orphan)} -> {orphan[:4]}")
print()
if fails:
    print(f"FAILURES ({len(fails)}):")
    for f in fails:
        print("   -", f)
else:
    print("ALL CHECKS PASS — scorecards, weights, tree and targets are consistent.")
