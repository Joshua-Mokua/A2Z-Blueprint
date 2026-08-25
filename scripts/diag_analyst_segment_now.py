#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Does the system know which segment each analyst belongs to? READ ONLY.

Catherine Mwikali Mutisya (KE1300) is the CONSUMER credit analyst, but her role
string is only "Credit Analyst" - the segment is not in it. The code already
knows this: _analyst_segment() says so in its own docstring and falls back to
the DEPARTMENT to tell Consumer from Commercial.

So before widening any permission, the question is whether that fallback
actually resolves for the people in the pilot. A segment gate is worthless if
everybody resolves to "" - it would grant everything or nothing.

    python scripts\diag_analyst_segment_now.py

Prints, for every credit analyst: the role, the department the register gives,
and the segment the code derives. Then the same for a sample of cases, so you
can see whether the two would ever meet.
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    from utils.core import UserManager
    from utils.api_lms_scope import _analyst_segment, _app_segment, _staff_department

    users = UserManager().users or {}
    analysts = [(k, v) for k, v in users.items()
                if "analyst" in str(v.get("role", "")).lower()
                and v.get("active")]

    print("=" * 88)
    print("WHICH SEGMENT DOES EACH ANALYST RESOLVE TO?")
    print("=" * 88)
    print("  %-26s %-9s %-26s %-22s %s"
          % ("ANALYST", "CODE", "ROLE", "DEPARTMENT", "SEGMENT"))
    unresolved = []
    for login, v in analysts:
        code = str(v.get("staff_code", "") or "")
        role = str(v.get("role", "") or "")
        try:
            dept = _staff_department(code) or ""
        except Exception:
            dept = "?"
        seg = _analyst_segment(role, code) or ""
        if not seg:
            unresolved.append((v.get("full_name"), role, dept))
        print("  %-26s %-9s %-26s %-22s %s"
              % (str(v.get("full_name"))[:26], code, role[:26], dept[:22],
                 seg or "*** none"))

    # And the cases.
    try:
        from utils.api_lms_routes import _lam
        apps = getattr(_lam(), "apps", []) or []
    except Exception:
        apps = []
    print("\n" + "-" * 88)
    print("AND WHAT SEGMENT DO THE CASES CARRY?")
    print("-" * 88)
    tally = {}
    for a in apps:
        try:
            s = _app_segment(a) or ""
        except Exception:
            s = "?"
        tally[s or "(none)"] = tally.get(s or "(none)", 0) + 1
    print("  applications  %d" % len(apps))
    for s, n in sorted(tally.items(), key=lambda x: -x[1]):
        print("     %-16s %d" % (s, n))

    print("\n" + "=" * 88)
    if unresolved:
        print("SOME ANALYSTS HAVE NO SEGMENT")
        print("=" * 88)
        for name, role, dept in unresolved:
            print("  * %-28s %-24s dept=%r" % (str(name)[:28], role[:24], dept))
        print("\n  A segment gate cannot be built on this. The department is")
        print("  what disambiguates 'Credit Analyst', and where it is blank or")
        print("  does not contain Consumer / Commercial / Corporate, the code")
        print("  returns '' and the person is treated as having NO segment.")
        print("\n  Fix the register first: that is data, not code.")
        return 1
    if tally.get("(none)", 0) == len(apps) and apps:
        print("EVERY CASE HAS NO SEGMENT")
        print("=" * 88)
        print("  The analysts resolve, but the cases do not - so a segment gate")
        print("  would still match nothing. _app_segment reads metadata.segment")
        print("  and then client_type; neither is set on these applications.")
        return 1
    print("BOTH SIDES RESOLVE - a segment gate would have something to match")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
