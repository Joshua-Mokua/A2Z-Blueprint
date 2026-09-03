#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Exactly who did HD2 make a manager, and what did that give them? READ ONLY.

FROM THE BANK (2026-09-03): "I am being careful not to bring up something that
can distort what we have working ... we are now dealing with a live system and
any touch is with military precision."

HD2 CHANGED ONE KEYWORD - "head of" became "head" - so that "Head, SME" and
"Head EFS" would be recognised the way "Head of Sales" already was. It was
written to give four seated committee members their Manager Queues.

is_manager() DOES MORE THAN DRAW A MENU. It also gates:

    clearing a case for disbursement      api_credit_admin_routes.py:707
    authorising a disbursement            api_credit_admin_routes.py:1124
    resolving a committee referral        api_lms_permissions.py:272
    manager-tier reads across the branch log and the pipeline

So anybody HD2 newly counts as a manager gained those too. That may be right -
a Head of SME is senior, and the equally senior "Head of Sales" already had
them - but it must be SEEN and DECIDED, not discovered in production.

    python scripts\diag_hd2_blast_radius.py

Prints every active staff member whose manager status CHANGED, and what each
gained. Nothing is written.
"""
import os
import re
import sys

sys.path.insert(0, os.getcwd())

OLD_KEYWORDS = ("managing", "director", "head of", "regional", "branch manager",
                "chief", "manager", "supervisor", "credit manager",
                "operations manager")

GAINED = [
    "Manager Queues in the sidebar",
    "clear a case for disbursement",
    "authorise a disbursement",
    "resolve a committee referral (in scope)",
    "manager-tier reads across the branch log",
]


def main():
    from utils.core import UserManager
    try:
        from utils.api_pipeline_manager_actions import is_manager
    except Exception as exc:
        print("ABORT: cannot import is_manager: %s" % str(exc)[:56])
        return 1

    users = UserManager().users or {}
    changed, already = [], 0
    for login, rec in users.items():
        if not rec.get("active"):
            continue
        role = str(rec.get("role", "") or "")
        was = bool(rec.get("is_admin")) or any(k in role.lower()
                                               for k in OLD_KEYWORDS)
        now = bool(is_manager(rec))
        if now and was:
            already += 1
        elif now and not was:
            changed.append((rec.get("full_name"), rec.get("staff_code"), role,
                            rec.get("unit") or rec.get("department") or ""))

    print("=" * 92)
    print("WHO HD2 NEWLY COUNTS AS A MANAGER")
    print("=" * 92)
    print("  active staff                %d" % sum(
        1 for r in users.values() if r.get("active")))
    print("  managers before HD2         %d" % already)
    print("  NEWLY managers              %d" % len(changed))

    if not changed:
        print("\n  Nobody. HD2 changed no permissions - every person it now")
        print("  matches was already a manager by another keyword.")
        return 0

    print("\n  %-28s %-9s %-34s %s" % ("PERSON", "CODE", "ROLE", "UNIT"))
    for name, code, role, unit in sorted(changed, key=lambda x: str(x[2])):
        print("  %-28s %-9s %-34s %s"
              % (str(name)[:28], code, role[:34], str(unit)[:20]))

    print("\n" + "-" * 92)
    print("WHAT EACH OF THEM GAINED")
    print("-" * 92)
    for g in GAINED:
        print("     %s" % g)

    print("\n" + "=" * 92)
    print("IS THAT RIGHT?")
    print("=" * 92)
    print("  HD2 did not invent the category. Before it, 'Head of Sales' and")
    print("  'Head of Branches' were already managers and already had all of")
    print("  the above - the only difference was a comma. So the question is")
    print("  not whether a Head should be a manager, but whether the people")
    print("  listed above should be, and they are the same seniority as those")
    print("  who already were.")
    print("\n  IF ANY OF THEM SHOULD NOT AUTHORISE A DISBURSEMENT, the fix is")
    print("  NOT to narrow is_manager again - that would take Manager Queues")
    print("  from the committee members who need it. It is to give the")
    print("  disbursement endpoints their own gate, which is a smaller and")
    print("  more honest change than making one function mean two things.")
    return 1 if changed else 0


if __name__ == "__main__":
    sys.exit(main())
