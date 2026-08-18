#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why does this analyst have no segment? READ ONLY.

A Department Analyst sees ONLY their own segment's cases - but only if the
system can work out what their segment IS. The resolution runs:

    role "Consumer Credit Analyst"   -> consumer, straight away
    role "Credit Analyst"            -> ambiguous, so the STAFF REGISTER's
                                        Department decides
    no staff code, or no department  -> "" , meaning NO RESTRICTION

That last line is the trap: an empty segment is falsy, so every gate reads it
as "this person has no segment constraint" and shows them everything. Catherine
seeing 271 cases instead of her Consumer ones is that, not a filter that was
never written.

    python scripts\\diag_analyst_segment.py --user catherine
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    who = ""
    if "--user" in sys.argv:
        i = sys.argv.index("--user")
        if i + 1 < len(sys.argv):
            who = sys.argv[i + 1].strip()
    if not who:
        print("ABORT: --user <login, staff code or part of a name> is required.")
        return 1

    from utils.core import UserManager
    from utils.api_lms_scope import _analyst_segment, _staff_department

    users = UserManager().users or {}
    rec, uname = None, ""
    w = who.lower()
    for k, v in users.items():
        if k.lower() == w or str(v.get("staff_code", "")).lower() == w:
            rec, uname = v, k
            break
    if not rec:
        hits = [(k, v) for k, v in users.items()
                if w in k.lower()
                or w in str(v.get("full_name") or v.get("name") or "").lower()]
        if len(hits) == 1:
            uname, rec = hits[0]
        elif len(hits) > 1:
            print("Several match %r:" % who)
            for k, v in hits[:10]:
                print("   %-24s %-28s %s" % (k, str(v.get("full_name") or "")[:28],
                                             v.get("staff_code")))
            return 1
    if not rec:
        print("ABORT: nobody matches %r." % who)
        return 1

    code = str(rec.get("staff_code", "") or "").strip()
    role = str(rec.get("role", "") or "")
    print("=" * 74)
    print("ANALYST SEGMENT")
    print("=" * 74)
    print("  login        %s" % uname)
    print("  staff_code   %r" % code)
    print("  role         %r" % role)

    dept = _staff_department(code) if code else ""
    seg = _analyst_segment(role, code)
    print("  department   %r   (from the staff register)" % dept)
    print("  SEGMENT      %r" % seg)

    print("")
    if seg:
        print("  Resolved. This person sees only %s cases." % seg)
        return 0

    print("  *** NO SEGMENT - so every gate treats them as unrestricted and")
    print("      they see EVERY case, not just their own segment's.")
    print("")
    if not code:
        print("      CAUSE: the login carries no staff_code, so the register")
        print("      cannot be consulted at all. Fix: set staff_code on this")
        print("      user in data/users.json.")
    elif not dept:
        print("      CAUSE: staff code %s is not in the register, or its" % code)
        print("      Department column is empty. The role 'Credit Analyst' is")
        print("      ambiguous - it spans Consumer and Commercial - so the")
        print("      department is the only thing that can tell them apart.")
        print("      Fix: set that person's Department to Consumer, Commercial")
        print("      or Corporate in the staff register.")
    else:
        print("      CAUSE: department %r matches none of consumer / commercial" % dept)
        print("      / corporate / investment. Fix: use one of those words, or")
        print("      give the role an explicit prefix such as 'Consumer Credit")
        print("      Analyst', which resolves without the register.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
