#!/usr/bin/env python3
"""Push the real intermediate managers in, so the tree reads true instead of flat.

Kennedy (Head of Operations) had 43 direct reports and Jane (Head of Consumer) 24 —
because staff were pointed straight at the head. But the managers between them already
exist in the establishment. This routes staff through them:

  Head of Operations
    |- Head Information & Technology  -> IT / developers / service officers
    |- Head, EBS                      -> EBS officers
    |- Operations Manager-Cards       -> Team Leader-Cards -> Cards Operations Officers
    |- Operations Manager-Payments    -> Team Leader-Payments -> Payments officers
    |- Operations Manager-Treasury    -> Team Leader-Trade & Trops -> TROPS officers
    +- Operations Manager-Branch Ops  -> Operations Officers / Assistants / Cheque Validation

  Head of Consumer
    |- Head, Consumer Products        -> Card Officer, Asset Product Manager
    |- Head, Digital Channels         -> Agency Manager, Payments & Digital Channels
    +- Manager, Bancassurance         -> Bancassurance (dotted; solid stays the BM in branches)

Solid lines = reporting + BSC rollup. Dotted = visibility only.
Dry-run unless --apply; org_config.json backed up first; all admin-editable after.
"""
import json, os, shutil, sys
from datetime import datetime

OCP = "data/org_config.json"

OPS_MGR_BRANCH = "Operations Manager-Branch Operations & Retail Support"
OPS_MGR_PAY = "Operations Manager-Payments, RPC & Remittances"
OPS_MGR_TT = "Operations Manager- Treasury & Trade Operations"
OPS_MGR_CARDS = "Operations Manager-Cards, Mobile & Digital Products"
HEAD_OPS = "Head of Operations"
HEAD_IT = "Head Information & Techonolgy"      # catalog spelling
HEAD_EBS = "Head, EBS"

SOLID = {
    # --- Technology under the Head of IT
    "Senior Service Officer, Technology (Applications)": [HEAD_IT],
    "Senior Service Officer, Technology (Networks & Telcoms)": [HEAD_IT],
    "Software Developer": [HEAD_IT],
    "IT Officer": [HEAD_IT],
    "Service Availability Officer": [HEAD_IT],
    # --- EBS
    "EBS Officer": [HEAD_EBS],
    # --- Cards
    "Team Leader-Cards, Mobile and Digital Products": [OPS_MGR_CARDS],
    "Cards Operations Officer": ["Team Leader-Cards, Mobile and Digital Products", OPS_MGR_CARDS],
    # --- Payments  (two Team Leaders hold Payments, so officers go to the single manager)
    "Team Leader-Payments RPC & Remittances": [OPS_MGR_PAY],
    "Payments Operations Officer": [OPS_MGR_PAY],
    "Service Officer- Payments": [OPS_MGR_PAY],
    # --- Treasury & Trade
    "Team Leader-Trade & Trops": [OPS_MGR_TT],
    "Service Officer, TROPS": ["Team Leader-Trade & Trops", OPS_MGR_TT],
    # --- Branch operations & retail support
    "Operations Officer": [OPS_MGR_BRANCH],
    "Operations Assistant Officer": [OPS_MGR_BRANCH],
    "Officer Operations": [OPS_MGR_BRANCH],
    "Cheque Validation Officer": [OPS_MGR_BRANCH],
    "Service Assistant, Operations Officer": [OPS_MGR_BRANCH],
    "Operations Controls Officer": [OPS_MGR_BRANCH],
    # --- Consumer
    "Card Officer": ["Head, Consumer Products"],
    "Asset Product Manager": ["Head, Consumer Products"],
    "Agency Manager": ["Head, Digital Channels & Agency Network"],
    "Senior Officer, Payments & Digital Channels": ["Head, Digital Channels & Agency Network"],
    "Business Development Officer, Bancassurance": ["Manager, Bancassurance"],
    "Scheme Administrator Officer": ["Relationship Manager, Employee Schemes"],
    # Bancassurance officers sit in branches and are SALES -> solid line to the BM,
    # falling back to the Bancassurance manager for the head-office one.
    "Bancassurance Officer": ["Branch Manager", "Manager, Bancassurance"],
}

# dotted = view only, no BSC rollup
DOTTED = {
    "Bancassurance Officer": ["Manager, Bancassurance"],
    "Business Development Officer, Bancassurance": ["Manager, Bancassurance"],
}

def main():
    apply = "--apply" in sys.argv
    oc = json.load(open(OCP, encoding="utf-8"))
    hier = oc.get("hierarchy", {}) or {}
    func = oc.get("functional_hierarchy", {}) or {}
    roles = set(oc.get("roles", []) or [])

    print("SOLID lines (reporting + BSC rollup):\n")
    changes = []
    for role, parents in SOLID.items():
        if role not in roles and role not in hier:
            print(f"   !! {role:52} not a catalog role — SKIPPED"); continue
        bad = [p for p in parents if p not in roles and p not in hier]
        if bad:
            print(f"   !! {role:52} parent missing: {bad} — SKIPPED"); continue
        if (hier.get(role) or []) == parents:
            continue
        print(f"   ~  {role:52} {hier.get(role)}\n        -> {parents}")
        changes.append((role, parents))

    print("\nDOTTED lines (view only):\n")
    dchanges = []
    for role, parents in DOTTED.items():
        if (func.get(role) or []) == parents:
            continue
        print(f"   ~  {role:52} -> {parents}")
        dchanges.append((role, parents))

    if not changes and not dchanges:
        print("\nnothing to change."); return
    for role, parents in changes:
        if role in parents:
            print(f"\nABORT: {role} would report to itself."); sys.exit(1)

    if not apply:
        print(f"\n[DRY-RUN] {len(changes)} solid + {len(dchanges)} dotted would change.")
        return
    shutil.copyfile(OCP, OCP + f".pre_layers_{datetime.now():%Y%m%d-%H%M%S}")
    for role, parents in changes:
        hier[role] = parents
    for role, parents in dchanges:
        func[role] = parents
    oc["hierarchy"] = hier
    oc["functional_hierarchy"] = func
    json.dump(oc, open(OCP, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote {OCP}  ({len(changes)} solid, {len(dchanges)} dotted)")
    print("Restart uvicorn, then: python build_upload_template.py && python test_hierarchy.py")

if __name__ == "__main__":
    main()
