#!/usr/bin/env python3
"""Re-point the hierarchy at the CURRENT establishment.

The catalog was built on an older structure: combined "Ag." roles that have since
split, and directorships nobody holds. That stranded 84 people whose manager's role
was vacant. Confirmed by the business:

  * Director Operations & Technology            -> Head of Operations (Kennedy), who reports to the MD
  * Head Information & Technology (Jeff)        -> Head of Operations
  * Ag. Head CX & Head Contact Centre           -> Head Contact Centre & Complaints Management
                                                   (Rosemary retired; contact-centre head holds CX), -> MD
  * Ag. Head Commercial Banking & Head EFS      -> Head EFS (Victor, acting Head of Commercial) -> MD
  * Head of Branches                            -> Head EFS (Victor) for now
  * Head of Consumer                            -> MD  (placeholder: Director CCB not yet appointed)

Dry-run by default; --apply writes data/org_config.json (backed up first).
All admin-editable afterwards in Admin -> Hierarchy.
"""
import json, os, shutil, sys
from datetime import datetime

MD = "Managing Director"

# dead role -> the live role that replaces it as a manager
REPLACE_PARENT = {
    "Director Operations & Technology": "Head of Operations",
    "Ag. Head Customer Experience & Head Contact Centre & Complaints Management":
        "Head Contact Centre & Complaints Management",
    "Ag. Head Commercial Banking & Head EFS": "Head EFS",
}

# explicit lines at the top of the tree
TOP = {
    "Head of Operations": [MD],
    "Head of Consumer": [MD],            # placeholder until Director CCB is appointed
    "Head Contact Centre & Complaints Management": [MD],
    "Head EFS": [MD],                    # Victor, acting Head of Commercial
    "Head of Branches": ["Head EFS"],    # Joshua Muthama -> Victor, currently
    "Head Information & Techonolgy": ["Head of Operations"],   # catalog spelling (Jeff)
    "Head Information & Technology": ["Head of Operations"],   # in case the clean name exists
}

def main():
    apply = "--apply" in sys.argv
    p = "data/org_config.json" if os.path.exists("data/org_config.json") else "a2z/data/org_config.json"
    oc = json.load(open(p, encoding="utf-8"))
    hier = oc.get("hierarchy", {}) or {}
    roles = set(oc.get("roles", []) or [])

    # Build the FINAL hierarchy first, then diff — so a role can never be left
    # reporting to itself (Head of Operations' old parent is what now replaces it).
    final = {r: list(v or []) for r, v in hier.items()}

    # 1) swap dead parents for live ones, everywhere they appear
    for role in list(final):
        new = [REPLACE_PARENT.get(x, x) for x in final[role]]
        final[role] = list(dict.fromkeys(new))     # de-dup, keep order

    # 2) explicit top-of-tree lines WIN over the generic swap
    for role, parents in TOP.items():
        if role in roles or role in final:
            final[role] = list(parents)

    # 3) a role must never report to itself
    for role in list(final):
        if role in final[role]:
            final[role] = [x for x in final[role] if x != role]

    changes = [(r, hier.get(r), final[r]) for r in final if (hier.get(r) or []) != final[r]]

    if not changes:
        print("nothing to change."); return

    print("hierarchy re-points:\n")
    for role, old, new in changes:
        print(f"  ~ {role:52} {old if old else 'NONE'}\n      -> {new}")

    # safety: no parent that isn't a known role
    for role, _, new in changes:
        for x in new:
            if x not in roles and x not in hier:
                print(f"\nABORT: parent role '{x}' is not in the catalog."); sys.exit(1)

    # the dead roles should no longer manage anyone
    still = {r: v for r, v in hier.items() if any(x in REPLACE_PARENT for x in (v or []))}
    if not apply:
        print(f"\n[DRY-RUN] {len(changes)} line(s) would change. Re-run with --apply.")
        print("\nAFTER THIS, the person-level work is admin-side:")
        print("  * add Joshua Muthama  -> Head of Branches (no staff no. yet)")
        print("  * Jane Jelagat KE1158 -> role 'Head of Consumer' (interim; remap when filled)")
        print("  * Rosemary Gitonga KE594 -> deactivate (retired)")
        print("  * Victor KE959 keeps role 'Head EFS' + acting Head of Commercial")
        return

    shutil.copyfile(p, p + f".pre_orgwire_{datetime.now():%Y%m%d-%H%M%S}")
    oc["hierarchy"] = final
    json.dump(oc, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote {p}  ({len(changes)} line(s) changed)")
    print("Restart uvicorn, then: python build_upload_template.py")

if __name__ == "__main__":
    main()
