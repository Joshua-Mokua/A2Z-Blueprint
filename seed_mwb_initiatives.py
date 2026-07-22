#!/usr/bin/env python3
"""Clear the 61 test initiatives and seed the 27 real Must Win Battles as initiatives.

The MWBs already live as MustWin objectives on the 10 consumer scorecards (owner = a real
register Staff Name, so compute_initiative_kpis matches and the BSC feed works). This:
  1. backs up execute_initiatives.json
  2. clears the 61 test records (Veronica Mutai + WS0x placeholders — all discardable)
  3. creates one initiative per MWB via ExecuteManager.create_initiative
  4. adds one delivery milestone per MWB (due date parsed where present)

Each initiative starts at gate G0. Its owner (io) is the scorecard role-holder, so
compute_initiative_kpis(staff_name) feeds the Initiative Implementation Score to their BSC.

    python seed_mwb_initiatives.py            # dry run — prints every create/clear
    python seed_mwb_initiatives.py --apply
"""
import json, re, shutil, sys, time
from datetime import date
from pathlib import Path

DATA = Path("data")

# ── date parsing: catch 'by June', 'end May', 'Apr-26', 'by June 2026' ──
MONTHS = {m: i for i, m in enumerate(
    ["january","february","march","april","may","june","july","august",
     "september","october","november","december"], 1)}
MON3 = {m[:3]: i for m, i in MONTHS.items()}

def parse_due(text):
    t = text.lower()
    # Apr-26 style
    m = re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[-\s]?(\d{2})\b', t)
    if m and m.group(2):
        mo = MON3.get(m.group(1)); yr = 2000 + int(m.group(2))
        if mo: return _eom(yr, mo)
    # 'by June 2026' / 'end May 2025' / 'by May'
    m = re.search(r'\b(?:by|end|end of)\s+([a-z]+)\s*(\d{4})?\b', t)
    if m:
        mo = MONTHS.get(m.group(1)) or MON3.get(m.group(1)[:3])
        if mo:
            yr = int(m.group(2)) if m.group(2) else 2026
            return _eom(yr, mo)
    return None

def _eom(y, m):
    if m == 12: return f"{y}-12-31"
    nxt = date(y, m + 1, 1)
    from datetime import timedelta
    return str(nxt - timedelta(days=1))

# ── owners: role -> holder Staff Name (from register) ──────────────────
from utils.api_pipeline_scope import get_staff_roster
reg = get_staff_roster()
reg["Role"] = reg["Role"].astype(str).str.strip()
reg["Staff Name"] = reg["Staff Name"].astype(str).str.strip()
role_holder = {}
for _, r in reg.iterrows():
    role_holder.setdefault(r["Role"], r["Staff Name"])

# ── the MWBs, per role (from the seeded MustWin objectives) ────────────
lib = json.loads((DATA/"kpi_library.json").read_text(encoding="utf-8"))
rw = lib.get("role_kpi_weights", {})

ROLE_WS = {  # per-owner sub-workstream under Consumer Banking
    "Head of Consumer": "Consumer Leadership",
    "Manager, Bancassurance": "Bancassurance",
    "Head, Consumer Products": "Consumer Products",
    "Head, Digital Channels & Agency Network": "Digital & Agency",
    "Head Premier Banking": "Premier Banking",
    "Head of Sales": "Sales",
    "Manager, Partnership, Alliances & Diaspora": "Partnerships & Diaspora",
    "Senior Officer, Payments & Digital Channels": "Payments & Digital",
    "Asset Product Manager": "Asset Products",
    "Card Officer": "Cards",
}

rows = []
for role, ws in ROLE_WS.items():
    owner = role_holder.get(role)
    for o in rw.get(role, {}).get("objectives", []):
        if o.get("area") != "MustWin":
            continue
        text = o.get("text", "").strip()
        due = o.get("due") or parse_due(text)
        flag = ""
        if due and due.startswith("2025"):
            flag = "  ⚠ 2025 date — verify (likely 2026)"
        rows.append((role, owner, ws, text, due, o.get("weight"), flag))

print(f"=== will CREATE {len(rows)} MWB initiatives (one milestone each) ===\n")
undated = 0
for role, owner, ws, text, due, w, flag in rows:
    if not owner:
        print(f"  !! {role}: NO register holder — skipping"); continue
    d = due or "(no date — open milestone)"
    if not due: undated += 1
    print(f"  {owner[:20]:20} [{ws:22}] {text[:50]:50} due {d}{flag}")
print(f"\n  {undated} have no parseable date (open milestone, date added later)")

# clear count
ei = DATA / "execute_initiatives.json"
existing = json.loads(ei.read_text(encoding="utf-8")) if ei.exists() else []
existing = existing if isinstance(existing, list) else []
print(f"\n=== will CLEAR {len(existing)} existing test initiatives ===")
print(f"   (backup taken first)")

if "--apply" not in sys.argv:
    print("\n[DRY-RUN] re-run with --apply to clear + seed")
    sys.exit(0)

# ── apply ──────────────────────────────────────────────────────────────
shutil.copy2(ei, ei.with_suffix(f".json.pre_mwbseed_{int(time.time())}"))
ei.write_text("[]", encoding="utf-8")   # clear
print("\ncleared. seeding...")

from utils.core import ExecuteManager
mgr = ExecuteManager()
created = 0
for role, owner, ws, text, due, w, flag in rows:
    if not owner:
        continue
    res = mgr.create_initiative({
        "name": text,
        "objective": text,
        "category": "Must Win Battle",
        "workstream": "Consumer Banking",
        "sub_workstream": ws,
        "io": owner,
        "created_by": "BSC Seed 2026",
        "estimated_impact": 0,
    })
    if not res:
        print(f"  !! create failed for {text[:40]}"); continue
    # create_initiative may return the id (str) or the initiative (dict) — handle both.
    init_id = res if isinstance(res, str) else res.get("id")
    if not init_id:
        print(f"  !! no id back for {text[:40]}"); continue
    mgr.add_milestone(init_id, {
        "name": f"Deliver: {text[:60]}",
        "type": "Delivery",
        "owner": owner,
        "due_date": due or "",
    })
    created += 1

print(f"\nseeded {created} MWB initiatives, each with a delivery milestone.")
print("Owner (io) = register Staff Name, so compute_initiative_kpis feeds each")
print("person's Initiative Implementation Score into their BSC.")
print("All start at gate G0 — advance via the gate flow as milestones complete.")
