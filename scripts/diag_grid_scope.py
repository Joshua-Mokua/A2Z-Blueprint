#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why does the history grid return no rows? — READ ONLY.

Walks the exact chain the /history-grid endpoint walks, for one username, and
prints what each step resolves to. Run it for the user who sees an empty grid.

    python scripts\\diag_grid_scope.py KE754

No argument: tries a few likely usernames from users.json.
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())


def rule(t):
    print("\n" + "=" * 66)
    print(t)
    print("=" * 66)


def main():
    who = sys.argv[1] if len(sys.argv) > 1 else ""

    users = {}
    try:
        raw = json.loads(open(os.path.join("data", "users.json"), encoding="utf-8").read())
        users = raw if isinstance(raw, dict) else {
            str(r.get("username")): r for r in raw if isinstance(r, dict)}
    except Exception as exc:
        print("could not read users.json: %s" % exc)
        return 1

    if not who:
        cands = [k for k in users if "josh" in k.lower()] or list(users)[:1]
        who = cands[0] if cands else ""
        print("no username given — using %r" % who)

    rec = users.get(who)
    if not rec:
        print("username %r not in users.json. Candidates containing 'KE7':" % who)
        for k in list(users)[:0] or [k for k in users if k.startswith("KE7")][:10]:
            print("   ", k)
        return 1

    rule("A. THE USER RECORD")
    for k in ("username", "staff_code", "full_name", "role", "department", "unit",
              "is_admin", "can_view_all", "active"):
        print("  %-14s %s" % (k, rec.get(k)))

    # what the token carries -> what _identity resolves
    user_ctx = {
        "username": who,
        "role": rec.get("role", ""),
        "staff_code": rec.get("staff_code", ""),
        "is_admin": bool(rec.get("is_admin")),
    }

    rule("B. SCOPE TIER (which branch of the endpoint runs)")
    try:
        import utils.api_branch_log as m
        me = m._identity(user_ctx)
        print("  _identity -> staff_code=%r role=%r unit=%r"
              % (me.get("staff_code"), me.get("role"), me.get("unit")))
        is_admin = m._is_admin(user_ctx)
        is_mgr = m._is_manager(user_ctx)
        print("  _is_admin   : %s" % is_admin)
        print("  _is_manager : %s" % is_mgr)
        print("  scope_tier  : %s" % ("bank" if is_admin else ("subtree" if is_mgr else "self")))
    except Exception as exc:
        print("  FAILED: %s" % exc)
        return 1

    rule("C. ROSTER MAP (_roster_dims)")
    try:
        dims = m._roster_dims()
        print("  entries: %d" % len(dims))
        if not dims:
            print("  *** EMPTY — get_staff_roster() returned nothing in this process.")
            print("      The grid cannot complete against the roster, so non-filers")
            print("      never appear. Check data/staff_register.xlsx is readable.")
        else:
            mine = m._dims_for(me.get("staff_code"))
            print("  this user in roster: %s" % (mine or "NOT FOUND"))
    except Exception as exc:
        print("  FAILED: %s" % exc)

    rule("D. VISIBLE STAFF (the pipeline hierarchy engine)")
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        thin = get_visible_staff_codes({
            "staff_code": me.get("staff_code", ""),
            "role": me.get("role", ""),
            "is_admin": bool(user_ctx.get("is_admin")),
        })
        print("  with a THIN context (what the grid used to send): %d codes" % len(thin))
        codes = get_visible_staff_codes({
            "staff_code":   me.get("staff_code", ""),
            "role":         rec.get("role", ""),
            "full_name":    rec.get("full_name", ""),
            "unit":         rec.get("unit", ""),
            "department":   rec.get("department", ""),
            "is_admin":     bool(rec.get("is_admin")),
            "can_view_all": bool(rec.get("can_view_all")),
        })
        print("  with the FULL context (what it sends now)        : %d codes" % len(codes))
        print("  get_visible_staff_codes -> %d codes" % len(codes))
        print("  sample: %s" % sorted(str(c) for c in codes)[:12])
        if len(codes) <= 1:
            print("  *** ONLY SELF (or none). This is why the grid is empty:")
            print("      the hierarchy engine does not consider this user a manager")
            print("      of anyone. Compare with what the Pipeline shows for them.")
    except Exception as exc:
        print("  FAILED: %s" % exc)

    rule("E. LOGS PRESENT AT ALL")
    try:
        from utils.branch_log import BranchLogManager
        blm = BranchLogManager()
        logs = blm.get_history(days=7)
        print("  logs in last 7 days: %d" % len(logs))
        codes_in_logs = sorted({str(l.get("staff_code")) for l in logs})[:12]
        print("  staff codes present: %s" % codes_in_logs)
    except Exception as exc:
        print("  FAILED: %s" % exc)

    rule("F. READ THIS")
    print("If C is EMPTY  -> staff_register.xlsx is not loading in the API process.")
    print("If D is 1 or 0 -> the hierarchy engine does not see this user as a")
    print("                  manager; the grid then scopes to self only.")
    print("If E is 0      -> there are no logs at all in the window, and the")
    print("                  roster fill is the only thing that can produce rows.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
