#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Can the credit admin team see and act on the cases that reach them?

Credit admin is scoped differently from credit analysis. The LMS pool lets a
role see work by STATUS regardless of who owns the deal. Credit admin has no
pool: a case is visible only if the deal's RM is in the caller's cascade.

That matters because credit admin sits at head office and the RMs are in
branches. If they are not in the cascade, the case arrives and nobody can see
it.

    python scripts/check_credit_admin_reach.py --user <staff code>
    python scripts/check_credit_admin_reach.py            (whole team)

Read only.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

CA_ROLES = ("credit admin", "credit administration", "credit administrator")


def main():
    who = ""
    if "--user" in sys.argv:
        i = sys.argv.index("--user")
        if i + 1 < len(sys.argv):
            who = sys.argv[i + 1].strip()

    from utils.core import UserManager
    from utils.api_pipeline_scope import get_visible_staff_codes
    try:
        from utils.core import CreditAdminManager
        cases = getattr(CreditAdminManager(), "cases", []) or []
    except Exception as exc:
        print("Could not read the credit admin cases: %s" % str(exc)[:60])
        cases = []

    users = [dict(v, username=k) for k, v in (UserManager().users or {}).items()
             if v.get("active")]
    if who:
        team = [u for u in users
                if str(u.get("staff_code", "")).strip().lower() == who.lower()]
        if not team:
            print("Nobody has staff code %r." % who)
            return 1
    else:
        team = [u for u in users
                if any(r in str(u.get("role", "")).lower() for r in CA_ROLES)]

    print("=" * 88)
    print("CREDIT ADMIN REACH")
    print("=" * 88)
    print("  credit admin cases in the system  %d" % len(cases))
    print("  people checked                    %d\n" % len(team))
    if not team:
        print("  Nobody active holds a credit admin role. Check the role")
        print("  spelling in the register against: %s" % ", ".join(CA_ROLES))
        return 1

    try:
        from utils.api_credit_admin_routes import filter_cases_by_visible_codes
    except Exception:
        filter_cases_by_visible_codes = None

    problems = []
    for u in team:
        code = str(u.get("staff_code", "") or "")
        try:
            vis = set(get_visible_staff_codes(u) or [])
        except Exception as exc:
            print("  %-26s could not read scope: %s"
                  % (str(u.get("full_name"))[:26], str(exc)[:40]))
            continue
        seen = []
        if filter_cases_by_visible_codes:
            try:
                seen = filter_cases_by_visible_codes(cases, vis, u) or []
            except Exception as exc:
                print("  filter raised: %s" % str(exc)[:60])
        print("  %-26s %-30s cascade=%-5d sees=%d"
              % (str(u.get("full_name"))[:26], str(u.get("role"))[:30],
                 len(vis), len(seen)))
        if cases and not seen:
            problems.append((u, len(vis)))

    if cases and problems:
        print("\n  THESE SEE NOTHING, AND THERE ARE CASES TO SEE")
        for u, n in problems:
            print("     %-26s cascade covers %d staff"
                  % (str(u.get("full_name"))[:26], n))
        print("\n  A credit admin case is visible only when the deal's RM is in")
        print("  the caller's cascade. Credit admin sits at head office and the")
        print("  RMs are in branches, so unless the department rule puts them")
        print("  in scope, the case arrives and nobody can see it.")
        print("")
        print("  Credit analysis solved this with a POOL - a role sees work by")
        print("  STATUS, whoever owns the deal. Credit admin has no equivalent.")
        print("  That is the gap, and it is a build rather than a config.")

    if cases and not problems:
        print("\n  Everyone checked can see cases. Acting uses the same scope,")
        print("  so if they can see it they can work it.")
    if not cases:
        print("\n  No credit admin cases exist yet, so this proves nothing.")
        print("  Re-run once a case has been approved through to credit admin.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
