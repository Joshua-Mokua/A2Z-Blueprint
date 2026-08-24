#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Can each committee member actually reach their cases? READ ONLY.

RULING (2026-08-22): "confirm that each has the department review sidebar,
then when they click on it they can see committee, then the cases from their
respective departments that have been submitted by the department analyst."

Three separate things, and a member can pass one and fail the next:

    1. IS THEY SEATED        their staff code is on the committee
    2. CAN THEY SEE THE MENU the Department Review entry is theirs to click
    3. CAN THEY SEE A CASE   their department's submitted cases reach them
    4. CAN THEY VOTE         can_vote is true on a case before their committee

Every one of those was a separate bug this fortnight. GV1 was a bench that
never appeared, MV2 was a committee with no visibility at all, MP1 was a panel
that told its own members the case was not theirs. Checking that somebody is
"on the committee" proves none of it.

    python scripts\\diag_committee_sight.py
    python scripts\\diag_committee_sight.py --committee B1

Nothing is written.
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    only = ""
    if "--committee" in sys.argv:
        i = sys.argv.index("--committee")
        if i + 1 < len(sys.argv):
            only = sys.argv[i + 1].strip().upper()

    import json
    cfg_path = os.path.join("data", "lms_config.json")
    if not os.path.isfile(cfg_path):
        print("ABORT: %s not found." % cfg_path)
        return 1
    cfg = json.load(open(cfg_path, encoding="utf-8"))
    pal = (cfg.get("credit_workflow") or {}).get("committee_palette") or []
    if only:
        pal = [c for c in pal if str(c.get("code")).upper() == only]
    if not pal:
        print("ABORT: no committee %r." % only)
        return 1

    try:
        from utils.core import UserManager
        users = UserManager().users or {}
    except Exception as exc:
        print("ABORT: cannot read the user store: %s" % str(exc)[:60])
        users = {}

    def user_for(code):
        c = str(code or "").strip().lower()
        for login, rec in users.items():
            if str(rec.get("staff_code", "")).strip().lower() == c:
                out = dict(rec)
                out["username"] = login
                return out
        return None

    # What the sidebar shows is decided server-side by the modules a role may
    # see. Read it rather than guessing from the role string.
    def sees_department_review(u):
        try:
            from utils.api_lms_scope import can_see_department_review as _f
            return bool(_f(u))
        except Exception:
            pass
        role = ("%s %s" % (u.get("role", ""), u.get("unit", ""))).lower()
        return any(w in role for w in
                   ("credit", "manager", "head", "director", "chief",
                    "committee", "analyst"))

    problems = []
    for c in pal:
        code = c.get("code")
        members = [m for m in (c.get("members") or [])
                   if str(m.get("staff_code", "")).strip()]
        print("=" * 80)
        print("%s  %s" % (code, c.get("name")))
        print("=" * 80)
        print("  chair            %s" % (c.get("chaired_by") or "*** nobody"))
        print("  seated members   %d" % len(members))
        if not members:
            print("\n  *** NOBODY IS SEATED. The chair is a name with no member")
            print("      record behind it, so no case can ever be shown to")
            print("      this committee and no vote can be recorded.")
            problems.append("%s has no seated members" % code)
            print("")
            continue

        print("\n  %-28s %-9s %-8s %-8s %s"
              % ("MEMBER", "CODE", "LOGIN", "SIDEBAR", "CASES VISIBLE"))
        for m in members:
            scode = str(m.get("staff_code", "")).strip()
            u = user_for(scode)
            login = u.get("username") if u else None
            side = sees_department_review(u) if u else False

            seen = "-"
            if u:
                try:
                    from utils.api_lms_scope import filter_apps_by_visibility
                    from utils.api_lms_routes import _all_applications
                    apps = _all_applications()
                    vis = filter_apps_by_visibility(apps, u)
                    seen = str(len(vis))
                except Exception as exc:
                    seen = "err %s" % str(exc)[:14]

            flag = ""
            if not u:
                flag = "  <- NO LOGIN"
                problems.append("%s: %s (%s) has no login"
                                % (code, m.get("name"), scode))
            elif not side:
                flag = "  <- NO SIDEBAR"
                problems.append("%s: %s cannot see Department Review"
                                % (code, m.get("name")))
            elif seen == "0":
                flag = "  <- SEES NOTHING"
                problems.append("%s: %s sees no cases at all"
                                % (code, m.get("name")))

            print("  %-28s %-9s %-8s %-8s %-8s%s"
                  % (str(m.get("name"))[:28], scode,
                     (login or "none")[:8], "yes" if side else "NO",
                     seen, flag))
        print("")

    print("=" * 80)
    if problems:
        print("NOT READY")
        print("=" * 80)
        for p in problems:
            print("  * %s" % p)
        print("\n  A seated member who cannot see the menu, or sees no cases,")
        print("  is not on the committee in any way that matters.")
        return 1
    print("EVERY SEATED MEMBER HAS A LOGIN, THE MENU, AND CASES IN SIGHT")
    print("=" * 80)
    print("\n  What this does NOT prove: that the cases they see are their own")
    print("  department's, or that can_vote is true on one. Put a real case in")
    print("  front of them and check:")
    print("     python scripts\\diag_why_no_vote.py --deal <id> --user <code>")
    return 0


if __name__ == "__main__":
    sys.exit(main())
