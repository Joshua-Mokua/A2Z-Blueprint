#!/usr/bin/env python3
"""Pull the Must Win Battles already seeded onto the consumer scorecards.

'Align with our existing list' — the MWBs live as the MustWin-pillar objectives we seeded
last session into kpi_library role_kpi_weights[role].objectives (area == 'MustWin'). This
lists them per owner so we author them as real initiatives against THIS list, not invent
new ones. Nothing written.
"""
import json
from pathlib import Path

lib = json.loads((Path("data")/"kpi_library.json").read_text(encoding="utf-8"))
rw = lib.get("role_kpi_weights", {})

# map role -> the person who holds it (for the io owner), from the register
from utils.api_pipeline_scope import get_staff_roster
reg = get_staff_roster()
reg["Role"] = reg["Role"].astype(str).str.strip()
reg["Staff Name"] = reg["Staff Name"].astype(str).str.strip()
role_holder = {}
for _, r in reg.iterrows():
    role_holder.setdefault(r["Role"], r["Staff Name"])

CONSUMER_ROLES = ["Head of Consumer", "Manager, Bancassurance", "Head, Consumer Products",
    "Head, Digital Channels & Agency Network", "Head Premier Banking", "Head of Sales",
    "Manager, Partnership, Alliances & Diaspora",
    "Senior Officer, Payments & Digital Channels", "Asset Product Manager", "Card Officer"]

total = 0
print("=== Must Win Battles already on the consumer scorecards ===\n")
for role in CONSUMER_ROLES:
    w = rw.get(role, {})
    objs = w.get("objectives", [])
    mwbs = [o for o in objs if o.get("area") == "MustWin"]
    if not mwbs:
        continue
    owner = role_holder.get(role, "(no holder)")
    print(f"### {role}  — owner: {owner}")
    for o in mwbs:
        due = o.get("due") or "no date"
        print(f"     • {o.get('text','')[:66]:66}  [{due}]  w={o.get('weight')}")
        total += 1
    print()

print(f"total MWBs across consumer scorecards: {total}")
print("\nThese become initiatives: name=text, io=owner, due parsed to a milestone.")
print("Each MWB with a date becomes an initiative with at least one milestone (the")
print("deliverable by that date); multi-part ones can get multiple milestones.")
