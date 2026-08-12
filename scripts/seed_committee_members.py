#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Give each branch credit committee a chair and members. DRY RUN by default.

WHY THIS AND NOT SIXTEEN TRIPS THROUGH ADMIN. The committee audit found every
branch committee empty, and a VOTING committee with no members cannot decide -
the endpoint refuses an empty votes[], so a case reaching that gate stops there
with nothing in the interface to free it. Sixteen of those is a lot of typing
to get wrong once.

The membership is not a judgement: it follows the branch hierarchy already in
the register.

    CHAIR     Branch Manager
    MEMBERS   Branch Credit Manager, Branch Operations Manager

Matched on the register's Region column, which carries the branch name - the
same field the committee generator used to create them.

IT SHOWS YOU THE PLAN FIRST, and names every branch where it could not find
somebody, rather than quietly leaving a committee short. A committee with one
member is below the default quorum of 2 and would defer every decision, so
knowing which are short matters more than the count that worked.

NOTHING IS OVERWRITTEN. A committee that already has members is left exactly as
it is - if somebody has set one up by hand, that is the deliberate version.

    python scripts\\seed_committee_members.py
    python scripts\\seed_committee_members.py --apply

Roles can be overridden per deployment in lms_config.credit_workflow:
    "branch_committee_roles": {"chair": "...", "members": ["...", "..."]}
"""
import json
import os
import shutil
import sys

sys.path.insert(0, os.getcwd())

CFG = os.path.join("data", "lms_config.json")

# THESE ARE THE ROLES THE REGISTER ACTUALLY CARRIES, checked against it rather
# than taken from the hierarchy note - which still lists a "Branch Credit
# Manager" the bank removed long ago, and which is why the first run found
# nobody in any branch.
#
# CHAIR IS A FALLBACK CHAIN. Not every branch has a Branch Manager; the ruling
# (2026-08-12) is "for those we get either the service manager or operations,
# but admin can always change". First match wins, and admin can override any of
# it afterwards.
DEFAULT_CHAIR = ["branch manager",
                 "customer service manager",
                 "assistant branch service & operations manager"]

# EVERY RELATIONSHIP MANAGER SITS, EXCEPT DIRECT SALES (ruling 2026-08-12:
# "ensure any Relationship Manager other than the DSA are part of the
# committee"). So this is not "take the first two that match" any more - the
# managers below are taken, and then EVERY RM in the branch joins them.
#
# The committee is as large as the branch's RM bench, which is the point: the
# people who bring the business sit on the committee that reviews it.
DEFAULT_MEMBERS = ["customer service manager",
                   "assistant branch service & operations manager",
                   "branch operations officer"]

# Anyone whose role contains one of these joins as well, however many there are.
ALL_OF_ROLE = ["relationship manager", "relationship officer"]

# DIRECT SALES ARE EXCLUDED. A DSA or a DSA team lead sells; they do not sit in
# review of what was sold. Matched as a substring, because the titles vary -
# "Direct Sales Agent", "Branch DSA Team Lead".
EXCLUDE = ["direct sales", "dsa"]

# The floor, not the target. With every RM included most branches will exceed
# it comfortably; this is what flags the ones that cannot.
WANTED_MEMBERS = 2


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(CFG):
        print("ABORT: %s not found - run from the project root." % CFG)
        return 1

    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
    except Exception as exc:
        print("ABORT: staff register unavailable: %s" % exc)
        return 1
    if len(df) == 0:
        print("ABORT: the staff register is empty - nothing to draw members from.")
        return 1

    cfg = json.load(open(CFG, encoding="utf-8")) or {}
    cw = cfg.get("credit_workflow")
    if not isinstance(cw, dict):
        cw = {}
    palette = cw.get("committee_palette")
    if not isinstance(palette, list):
        palette = []

    roles_cfg = cw.get("branch_committee_roles") or {}
    _c = roles_cfg.get("chair") or DEFAULT_CHAIR
    chair_roles = [str(r).lower() for r in
                   (_c if isinstance(_c, list) else [_c])]
    member_roles = [str(r).lower() for r in
                    (roles_cfg.get("members") or DEFAULT_MEMBERS)]
    wanted = int(roles_cfg.get("wanted_members") or WANTED_MEMBERS)

    # Index the register by branch. Region carries the branch name - the same
    # field the committee generator matched on when it created these.
    by_branch = {}
    for _i, r in df.iterrows():
        branch = str(r.get("Unit") or "").strip()
        if not branch:
            continue
        by_branch.setdefault(branch.lower(), []).append({
            "code": str(r.get("Staff Code") or "").strip(),
            "name": str(r.get("Staff Name") or "").strip(),
            "role": str(r.get("Role") or "").strip(),
        })

    branch_cttees = [c for c in palette
                     if str(c.get("kind", "")).lower() == "branch"]
    print("=" * 74)
    print("BRANCH COMMITTEE MEMBERSHIP")
    print("=" * 74)
    print("  committees      %d" % len(branch_cttees))
    print("  register rows   %d across %d branches" % (len(df), len(by_branch)))
    print("  chair, in order %s" % " -> ".join(chair_roles))
    print("  managers        %s" % ", ".join(member_roles))
    print("  plus ALL        %s" % ", ".join(ALL_OF_ROLE))
    print("  excluding       %s" % ", ".join(EXCLUDE))
    print("  minimum         %d (the default quorum)" % wanted)

    planned, short, untouched = [], [], []
    for c in branch_cttees:
        if c.get("members"):
            untouched.append(c)
            continue
        branch = str(c.get("branch") or "").strip().lower()
        people = by_branch.get(branch, [])

        def _find(role_frag, exclude=()):
            return next((p for p in people
                         if role_frag in p["role"].lower()
                         and p["code"] not in exclude), None)

        # Chair: first role in the chain that this branch actually has.
        chair = None
        for cr in chair_roles:
            chair = _find(cr)
            if chair:
                break

        # The named managers first, one each, then EVERY relationship manager.
        # Never reusing the chair - one person cannot be two members, and a
        # committee of one counted twice is what the quorum exists to stop.
        used = {chair["code"]} if chair else set()
        members = []

        def _excluded(role):
            rl = role.lower()
            return any(x in rl for x in EXCLUDE)

        for mr in member_roles:
            p = _find(mr, exclude=used)
            if p and not _excluded(p["role"]):
                used.add(p["code"])
                members.append({"staff_code": p["code"], "name": p["name"],
                                "role": p["role"]})

        for person in people:
            if person["code"] in used or _excluded(person["role"]):
                continue
            if any(r in person["role"].lower() for r in ALL_OF_ROLE):
                used.add(person["code"])
                members.append({"staff_code": person["code"],
                                "name": person["name"], "role": person["role"]})
        missing = [] if len(members) >= wanted else ["only %d of %d found"
                                                     % (len(members), wanted)]
        planned.append((c, chair, members, missing))
        # Below the default quorum of 2, this committee would DEFER every
        # decision - which is a quieter failure than an empty one, so it is
        # called out rather than counted as done.
        if len(members) < 2:
            short.append((c, len(members), missing))

    if untouched:
        print("\n  %d committee(s) already have members - left untouched."
              % len(untouched))

    print("\n  TO POPULATE  %d" % len(planned))
    for c, chair, members, missing in planned[:8]:
        print("     %-38s chair: %-22s members: %d"
              % (str(c.get("name"))[:38],
                 (chair or {}).get("name", "(none found)")[:22], len(members)))
    if len(planned) > 8:
        print("     ... and %d more" % (len(planned) - 8))

    if short:
        print("\n  *** %d committee(s) would have FEWER THAN 2 members:" % len(short))
        for c, n, missing in short:
            print("     %-38s %d member(s)  %s"
                  % (str(c.get("name"))[:38], n, ", ".join(missing) or ""))
        print("")
        print("  The default quorum is 2, so these would DEFER every decision")
        print("  rather than approving or rejecting. Add people to those")
        print("  branches in the register, or set min_quorum_count on the")
        print("  committee deliberately - do not leave it to be discovered by")
        print("  a case that stalls.")

    if not planned:
        print("\n  Nothing to do.")
        return 0

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(CFG, CFG + ".pre_members")
    for c, chair, members, _missing in planned:
        if chair:
            c["chaired_by"] = chair["name"]
            c["chair_staff_code"] = chair["code"]
        c["members"] = members
    cw["committee_palette"] = palette
    cfg["credit_workflow"] = cw
    tmp = CFG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2)
    os.replace(tmp, CFG)

    print("\npopulated %d committee(s) (backup: %s)"
          % (len(planned), os.path.basename(CFG + ".pre_members")))
    print("Restart uvicorn, then check the path is clear before assigning any")
    print("committee as a gate on a product:")
    print("  python scripts\\audit_committee_path.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
