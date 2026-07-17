#!/usr/bin/env python3
"""Wire the branch reporting line as confirmed by the business:

    Branch Manager
    |-- Assistant Branch Service & Operations Manager      (the branch operations manager)
    |     |-- Teller
    |     |-- Customer Service Manager
    |     +-- Branch Operations Officer
    +-- Sales (Relationship Officer / Manager, DSA Team Lead, DSA)  -> direct to the BM

Validation follows this line: branch operations staff are validated by the ops
manager; sales are validated by the Branch Manager.

Dry-run by default; --apply writes data/org_config.json (backed up first).
Everything here is admin-editable afterwards in Admin -> Hierarchy.
"""
import json, os, shutil, sys
from datetime import datetime

OPS = "Assistant Branch Service & Operations Manager"

# role -> parents.  Only these lines change; sales are already direct to the BM.
WIRE = {
    "Teller": [OPS],
    "Customer Service Manager": [OPS],
    "Branch Operations Officer": [OPS],
    OPS: ["Branch Manager"],
    # sales: mirrors Relationship Officer, which is already direct to the BM
    "Relationship Manager": ["Branch Manager"],
}

def main():
    apply = "--apply" in sys.argv
    p = "data/org_config.json" if os.path.exists("data/org_config.json") else "a2z/data/org_config.json"
    oc = json.load(open(p, encoding="utf-8"))
    hier = oc.get("hierarchy", {}) or {}
    roles = set(oc.get("roles", []) or [])

    if OPS not in roles:
        print(f"ABORT: '{OPS}' is not a catalog role — nothing to wire to."); sys.exit(1)

    print("branch line to wire:\n")
    changes, adds = [], []
    for role, parents in WIRE.items():
        cur = hier.get(role)
        if cur == parents:
            print(f"  =  {role:46} already -> {parents}")
            continue
        if role not in roles:
            adds.append(role)
        print(f"  ~  {role:46} {cur if cur is not None else 'NOT IN HIERARCHY'}  ->  {parents}")
        changes.append((role, parents))

    if adds:
        print(f"\n  (roles added to the catalog: {adds})")

    # safety: a role must never end up reporting to itself
    for role, parents in changes:
        if role in parents:
            print(f"\nABORT: {role} would report to itself."); sys.exit(1)

    if not changes:
        print("\nnothing to change."); return
    if not apply:
        print("\n[DRY-RUN] re-run with --apply to write org_config.json")
        return

    shutil.copyfile(p, p + f".pre_branchwire_{datetime.now():%Y%m%d-%H%M%S}")
    for role, parents in changes:
        hier[role] = parents
        roles.add(role)
    oc["hierarchy"] = hier
    oc["roles"] = sorted(roles)
    json.dump(oc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote {p}  ({len(changes)} line(s) changed)")
    print("Restart uvicorn, then re-run:  python build_upload_template.py")

if __name__ == "__main__":
    main()
