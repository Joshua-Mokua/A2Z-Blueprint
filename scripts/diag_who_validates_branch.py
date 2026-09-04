#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Who can validate whose deals at a branch? READ ONLY.

FROM THE BANK (2026-09-04): "we had clearly defined that not only the branch
manager can validate a deal - we said at least the Operations Manager, Customer
Service Manager, Assistant Branch Service & Operations Manager, or essentially
anyone in management at the branch, since we are having trouble with many
managers out."

    python scripts\diag_who_validates_branch.py --branch Kisumu

VALIDATING A DEAL NEEDS TWO THINGS:

    1. is_manager(user)          the role contains manager / head / director...
    2. the deal's OWNER is in    get_visible_staff_codes(user) - which follows
       the caller's cascade      the reporting line, not the branch

The second is the real constraint. A Branch Operations Manager passes the first
test easily, but tellers, CSOs and BOS report to them while the ROs report to
the Branch Credit Manager - so an Operations Manager covering for an absent
Branch Manager can validate some of the branch's deals and not others, with no
message explaining why.

This prints, for every manager at a branch, exactly whose deals they can
validate. That is the picture to decide from before widening anything.
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    branch = ""
    if "--branch" in sys.argv:
        i = sys.argv.index("--branch")
        if i + 1 < len(sys.argv):
            branch = sys.argv[i + 1].strip()
    if not branch:
        print("ABORT: --branch <name> is required.")
        return 1

    from utils.core import UserManager
    from utils.api_pipeline_scope import get_staff_roster, get_visible_staff_codes
    from utils.api_pipeline_manager_actions import is_manager

    roster = get_staff_roster()
    users = UserManager().users or {}
    by_code = {}
    for login, rec in users.items():
        c = str(rec.get("staff_code", "")).strip()
        if c:
            by_code[c] = dict(rec, username=login)

    people = []
    for _i, r in roster.iterrows():
        b = str(r.get("Branch") or r.get("Unit") or "").strip()
        if branch.lower() not in b.lower():
            continue
        people.append({
            "code": str(r.get("Staff Code") or "").strip(),
            "name": str(r.get("Staff Name") or "").strip(),
            "role": str(r.get("Role") or "").strip(),
            "reports_to": str(r.get("Reports To") or "").strip(),
        })
    if not people:
        print("ABORT: nobody at a branch matching %r." % branch)
        return 1

    print("=" * 92)
    print("WHO CAN VALIDATE WHOSE DEALS AT %s" % branch.upper())
    print("=" * 92)
    print("  staff at this branch  %d\n" % len(people))

    codes = {p["code"] for p in people}
    managers, gaps = [], []
    for p in people:
        u = by_code.get(p["code"])
        if not u:
            continue
        if not is_manager(u):
            continue
        try:
            vis = set(get_visible_staff_codes(u) or [])
        except Exception as exc:
            print("  %-26s could not read scope: %s" % (p["name"][:26], str(exc)[:40]))
            continue
        mine = codes & vis
        managers.append((p, mine))

    if not managers:
        print("  NOBODY at this branch is a manager. Every deal here must be")
        print("  validated from above.")
        return 1

    print("  %-26s %-34s %s" % ("MANAGER", "ROLE", "CAN VALIDATE"))
    for p, mine in sorted(managers, key=lambda x: -len(x[1])):
        print("  %-26s %-34s %d of %d at this branch"
              % (p["name"][:26], p["role"][:34], len(mine), len(codes)))

    # Who is covered by nobody?
    covered = set()
    for _p, mine in managers:
        covered |= mine
    orphans = [p for p in people if p["code"] not in covered and p["code"]]
    if orphans:
        print("\n  NOBODY AT THIS BRANCH CAN VALIDATE THESE PEOPLE'S DEALS:")
        for p in orphans[:10]:
            print("     %-26s %-30s reports to %s"
                  % (p["name"][:26], p["role"][:30], p["reports_to"] or "-"))
        if len(orphans) > 10:
            print("     ... and %d more" % (len(orphans) - 10))

    print("\n" + "=" * 92)
    print("WHAT THIS MEANS")
    print("=" * 92)
    print("  A manager validates the people in THEIR CASCADE, not the people at")
    print("  their branch. Where a branch splits under two managers - operations")
    print("  one side, credit the other - covering for one of them does not")
    print("  reach the other's staff.")
    print("\n  IF THE BANK WANTS ANY BRANCH MANAGER-TIER PERSON TO VALIDATE ANY")
    print("  DEAL AT THAT BRANCH, that is a widening of scope, not a role list,")
    print("  and it should be a deliberate decision: it lets an Operations")
    print("  Manager validate a relationship officer's credit deal.")
    print("\n  The narrower alternative is the delegation already built for the")
    print("  daily log - a named person, a named branch, an end date and a")
    print("  reason - which covers absence without changing the rule for")
    print("  everybody permanently.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
