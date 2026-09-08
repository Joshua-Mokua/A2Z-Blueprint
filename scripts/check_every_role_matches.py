#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Which roles in the register match nothing, and so can see nothing.

Four separate lists decide what a person reaches, each written at a different
time against the role spellings that existed then:

    the pool roles              lms_config pool_visibility.roles
    the credit admin department api_credit_admin_scope
    the manager keywords        api_pipeline_manager_actions
    the analyst segments        api_lms_scope

A role string that matches none of them is invisible in that area, and nobody
finds out until a person complains. Three have cost a day each: Credit Risk
Manager, Credit Administration Officer, Head CAD.

    python scripts/check_every_role_matches.py

Read only. Run it after any hire, and before any go-live.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.getcwd())


def main():
    from utils.core import UserManager
    users = [dict(v, username=k) for k, v in (UserManager().users or {}).items()
             if v.get("active")]
    roles = Counter(str(u.get("role", "") or "").strip() for u in users)

    checks = []
    try:
        from utils.api_lms_scope import get_pool_visibility_config, _role_sees_pool
        cfg = get_pool_visibility_config()
        checks.append(("credit work pool",
                       lambda r: _role_sees_pool(r, cfg["roles"])))
    except Exception as exc:
        print("could not load the pool config: %s" % str(exc)[:50])
    try:
        from utils.api_credit_admin_scope import _is_credit_admin_department_role
        checks.append(("credit admin department",
                       lambda r: _is_credit_admin_department_role({"role": r})))
    except Exception as exc:
        print("could not load the credit admin scope: %s" % str(exc)[:50])
    try:
        from utils.api_pipeline_manager_actions import is_manager
        checks.append(("manager", lambda r: is_manager({"role": r})))
    except Exception as exc:
        print("could not load is_manager: %s" % str(exc)[:50])
    try:
        from utils.api_lms_scope import _analyst_segment
        checks.append(("a segment analyst",
                       lambda r: bool(_analyst_segment(r, ""))))
    except Exception as exc:
        print("could not load _analyst_segment: %s" % str(exc)[:50])

    if not checks:
        print("Nothing to check against.")
        return 1

    print("=" * 96)
    print("WHAT EACH ROLE MATCHES")
    print("=" * 96)
    print("  active staff  %d" % len(users))
    print("  distinct roles %d\n" % len(roles))

    hdr = "  %-38s %-6s" % ("ROLE", "PEOPLE")
    for name, _f in checks:
        hdr += " %-24s" % name[:24]
    print(hdr)

    nothing = []
    for role, n in roles.most_common():
        if not role:
            continue
        line = "  %-38s %-6d" % (role[:38], n)
        hits = 0
        for _name, f in checks:
            try:
                ok = bool(f(role))
            except Exception:
                ok = False
            hits += 1 if ok else 0
            line += " %-24s" % ("yes" if ok else "-")
        print(line)
        if hits == 0:
            nothing.append((role, n))

    print("\n" + "=" * 96)
    if not nothing:
        print("Every role matches at least one list.")
        print("=" * 96)
        return 0
    print("MATCH NOTHING: %d role(s), %d person(s)"
          % (len(nothing), sum(n for _r, n in nothing)))
    print("=" * 96)
    for role, n in nothing:
        print("  %-44s %d person(s)" % (role[:44], n))
    print("\n  These people see only their own work and their cascade. If any")
    print("  of them is meant to work a pool - credit, admin, TROPS - they")
    print("  will report seeing nothing, and nothing will explain why.")
    print("\n  Fix by adding the role to the list it belongs in, not by")
    print("  renaming people in the register.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
