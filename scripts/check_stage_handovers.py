#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Check that someone can act at every stage of the credit chain.

Runs before users find the gap. For each stage, works out who is supposed to
pick a case up there, then checks whether those people can actually see one.

    python scripts/check_stage_handovers.py

Read only. Nothing is written.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())

# stage -> the roles expected to act there
HANDOVERS = [
    ("Branch Credit Committee Review", ("branch manager", "operations manager",
                                        "customer service manager",
                                        "relationship manager")),
    ("Department Credit Analysis", ("credit analyst",)),
    ("Department Credit Committee Review", ("head", "director", "chief")),
    ("Credit Analysis", ("credit risk", "credit analyst")),
    ("Credit Administration", ("credit administration", "credit admin")),
    ("Offer Letter", ("credit administration", "credit admin", "legal")),
    ("Trops", ("trops", "treasury", "disbursement", "operations")),
]


def main():
    from utils.core import UserManager, PipelineManager
    users = [dict(v, username=k) for k, v in (UserManager().users or {}).items()
             if v.get("active")]
    deals = PipelineManager().deals or []

    try:
        from utils.api_lms_routes import _lam
        apps = getattr(_lam(), "apps", []) or []
    except Exception as exc:
        print("Could not read the applications: %s" % str(exc)[:60])
        apps = []

    by_stage = Counter(str(d.get("stage") or "(none)") for d in deals)

    print("=" * 84)
    print("WHO CAN ACT AT EACH STAGE")
    print("=" * 84)
    print("  active staff  %d" % len(users))
    print("  deals         %d" % len(deals))
    print("  credit cases  %d\n" % len(apps))

    problems = []
    print("  %-36s %-7s %-9s %s" % ("STAGE", "DEALS", "STAFF", "STATUS"))
    for stage, roles in HANDOVERS:
        n = by_stage.get(stage, 0)
        who = [u for u in users
               if any(r in str(u.get("role", "")).lower() for r in roles)]
        if not who:
            state = "NOBODY HAS A MATCHING ROLE"
            problems.append((stage, n, "no active staff hold any of: %s"
                             % ", ".join(roles)))
        elif n and not apps:
            state = "deals here but no cases at all"
            problems.append((stage, n, "deals are standing here and there are "
                                       "no credit cases in the system"))
        else:
            state = "ok"
        print("  %-36s %-7d %-9d %s" % (stage[:36], n, len(who), state))

    # A deal standing at a credit stage with no case behind it is invisible to
    # every credit screen, whatever the stage says.
    credit_stages = {s for s, _r in HANDOVERS if s != "Branch Credit Committee Review"}
    orphans = [d for d in deals
               if str(d.get("stage") or "") in credit_stages
               and not str(d.get("lms_application_id") or "").strip()]
    if orphans:
        print("\n  Deals at a credit stage with no case behind them: %d"
              % len(orphans))
        for d in orphans[:10]:
            print("     %-9s %-28s %s" % (str(d.get("id"))[:9],
                                          str(d.get("client_name"))[:28],
                                          d.get("stage")))
        problems.append(("(any)", len(orphans),
                         "these are invisible to every credit screen"))

    # Cases sitting unassigned - waiting for a person, not for a fix.
    pool = [a for a in apps
            if not str(((a.get("analyst") or {}) if isinstance(a.get("analyst"), dict)
                        else {}).get("code", "") or "").strip()]
    if pool:
        print("\n  Cases in the pool, assigned to nobody: %d" % len(pool))
        for a in pool[:10]:
            print("     %-12s %-28s status=%s"
                  % (str(a.get("id"))[:12], str(a.get("client_name"))[:28],
                     a.get("status")))
        print("     These are waiting for an analyst to pick them up.")

    print("\n" + "=" * 84)
    if not problems:
        print("Every stage has someone who could act there.")
        print("=" * 84)
        return 0
    print("Worth looking at")
    print("=" * 84)
    for stage, n, why in problems:
        print("  %-36s %s" % (stage[:36], why))
    print("\n  A stage with deals but nobody able to act is where the next")
    print("  report comes from. Better found here than by a user.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
