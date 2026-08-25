#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Of everyone who should be able to attach a document, who actually can?

FROM THE PILOT (2026-08-25): "hope we resolve for the other analysts as well as
they may be attaching documents as well."

AT1 let a SEGMENT analyst attach to her segment's cases. That covers Consumer,
Commercial and CIB. It does nothing for:

    credit risk         _analyst_segment returns "" for credit risk BY DESIGN -
                        they work across every segment, so they have no
                        segment constraint and AT1's rule cannot match
    credit admin        attaches legal and security paperwork after approval
    the RM who owns it  provides information when the case is returned

Each of those may already be covered by can_edit, can_decide or is_mgr - or
may not. Reasoning about it from the permission code is how the last three
wrong answers happened. This asks the actual function.

    python scripts\diag_who_can_attach.py
    python scripts\diag_who_can_attach.py --app LMS00007

For each credit-side person it prints, against a real case, whether the attach
gate would let them through and WHICH test carried them.
"""
import os
import sys

sys.path.insert(0, os.getcwd())

WANTED = ("credit analyst", "credit risk", "credit admin", "credit administration",
          "remedial", "recover", "director, credit", "chief credit")


def main():
    app_id = ""
    if "--app" in sys.argv:
        i = sys.argv.index("--app")
        if i + 1 < len(sys.argv):
            app_id = sys.argv[i + 1].strip()

    from utils.core import UserManager
    from utils.api_lms_permissions import resolve_application_permissions
    try:
        from utils.api_lms_scope import _analyst_segment, _app_segment
    except Exception:
        _analyst_segment = _app_segment = lambda *a, **k: ""

    users = UserManager().users or {}
    people = [dict(v, username=k) for k, v in users.items()
              if v.get("active")
              and any(w in str(v.get("role", "")).lower() for w in WANTED)]
    if not people:
        print("ABORT: nobody on the credit side is active.")
        return 1

    try:
        from utils.api_lms_routes import _lam
        apps = getattr(_lam(), "apps", []) or []
    except Exception as exc:
        print("ABORT: cannot read the applications: %s" % str(exc)[:60])
        return 1
    if app_id:
        apps = [a for a in apps if str(a.get("id")) == app_id]
        if not apps:
            print("ABORT: no application %r." % app_id)
            return 1
    # Prefer a case that HAS a segment - otherwise the segment rule cannot
    # fire and the answer says nothing about it.
    with_seg = [a for a in apps if (_app_segment(a) or "")]
    sample = (with_seg or apps)[:1]
    if not sample:
        print("ABORT: there are no applications to test against.")
        return 1
    a = sample[0]
    seg = _app_segment(a) or ""

    print("=" * 88)
    print("WHO CAN ATTACH A DOCUMENT TO THIS CASE")
    print("=" * 88)
    print("  case          %s" % a.get("id"))
    print("  client type   %s" % (a.get("client_type") or "(blank)"))
    print("  segment       %s" % (seg or "*** none - the segment rule cannot fire"))
    print("  assigned to   %s"
          % ((a.get("analyst") or {}).get("code") if isinstance(a.get("analyst"), dict)
             else "(nobody)"))
    if not seg:
        print("\n  NOTE: this case has no segment, so AT1's rule is inert here.")
        print("  Name a case that has one with --app to test it properly.")

    print("\n  %-26s %-28s %-10s %s"
          % ("PERSON", "ROLE", "SEGMENT", "MAY ATTACH  (carried by)"))
    blocked = []
    for u in sorted(people, key=lambda x: str(x.get("role"))):
        role = str(u.get("role", "") or "")
        code = str(u.get("staff_code", "") or "")
        mine = _analyst_segment(role, code) or ""
        try:
            p = resolve_application_permissions(u, a) or {}
        except Exception:
            p = {}
        why = []
        if p.get("is_assigned_analyst"):
            why.append("assigned")
        if p.get("can_edit"):
            why.append("can_edit")
        if p.get("can_submit_to_dcc"):
            why.append("submit")
        if p.get("can_decide"):
            why.append("decide")
        if mine and seg and mine == seg:
            why.append("segment")
        may = bool(why)
        if not may:
            blocked.append((u.get("full_name"), role))
        print("  %-26s %-28s %-10s %-6s %s"
              % (str(u.get("full_name"))[:26], role[:28], mine or "-",
                 "yes" if may else "403",
                 ", ".join(why) if why else ""))

    print("\n" + "=" * 88)
    if blocked:
        print("STILL BLOCKED ON THIS CASE")
        print("=" * 88)
        for name, role in blocked:
            print("  * %-28s %s" % (str(name)[:28], role))
        print("\n  Whether that is right depends on the role. Credit risk and")
        print("  credit admin come to a case at a particular STAGE - if this")
        print("  case has not reached theirs, a refusal is correct and not a")
        print("  bug. Test against a case at their stage before widening")
        print("  anything: a permission opened for a stage nobody has reached")
        print("  is a permission opened for every stage.")
        return 1
    print("EVERYONE ON THE CREDIT SIDE CAN ATTACH TO THIS CASE")
    print("=" * 88)
    return 0


if __name__ == "__main__":
    sys.exit(main())
