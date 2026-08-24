#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
Why can this person not attach a document? READ ONLY.

FROM THE PILOT (2026-08-24): Catherine Muasya, the consumer credit analyst,
tries to attach the CRB report and the call memo and gets 403 Forbidden.

    python scripts\diag_attach_403.py --app <app id> --user KE1234
    python scripts\diag_attach_403.py --user KE1234        (all her cases)

THE GATE is in api_lms_routes.py:

    can_edit or can_submit_to_dcc or can_decide or is_assigned_analyst

and is_assigned_analyst is an EXACT STRING COMPARISON of the caller's staff
code against app["analyst"]["code"]. So there are only a few ways to fail it,
and they look identical from the browser:

    1. she is not the assigned analyst      - a scope question
    2. she IS, but the codes are punctuated differently - KE0539 vs KE539,
       the same fault that stopped a portfolio owner being recognised
    3. the case has no analyst at all       - nobody can attach
    4. her user record has no staff_code    - nothing can ever match

This prints which one, per case, with both codes side by side.
"""
import os
import re
import sys

sys.path.insert(0, os.getcwd())


def _digits(v):
    m = re.match(r"^([A-Za-z]*)0*(\d+)$", str(v or "").strip())
    return ("%s%s" % (m.group(1).upper(), m.group(2))) if m else ""


def main():
    who = app_id = ""
    for flag in ("--user", "--app"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--user":
                    who = sys.argv[i + 1].strip()
                else:
                    app_id = sys.argv[i + 1].strip()
    if not who:
        print("ABORT: --user <staff code or login> is required.")
        return 1

    from utils.core import UserManager
    users = UserManager().users or {}
    u = None
    for login, rec in users.items():
        if (login.lower() == who.lower()
                or str(rec.get("staff_code", "")).strip().lower() == who.lower()
                or _digits(rec.get("staff_code")) == _digits(who)):
            u = dict(rec, username=login)
            break
    if not u:
        print("ABORT: nobody matches %r." % who)
        return 1

    caller = str(u.get("staff_code", "") or "").strip()
    print("=" * 84)
    print("WHY THE 403 ON ATTACHING A DOCUMENT")
    print("=" * 84)
    print("  person        %s" % (u.get("full_name") or u.get("username")))
    print("  login         %s" % u.get("username"))
    print("  staff code    %s" % (caller or "*** NONE - nothing can ever match"))
    print("  role          %s" % u.get("role"))
    if not caller:
        print("\n  A user record with no staff code fails every ownership test")
        print("  in the system, not only this one.")
        return 1

    try:
        from utils.api_lms_models import load_applications as _load
        apps = _load()
    except Exception:
        try:
            from utils.api_lms_routes import _lam
            apps = list((_lam().all() or {}).values())
        except Exception as exc:
            print("ABORT: cannot read the applications: %s" % str(exc)[:60])
            return 1
    if isinstance(apps, dict):
        apps = list(apps.values())
    if app_id:
        apps = [a for a in apps if str(a.get("id")) == app_id]
        if not apps:
            print("ABORT: no application %r." % app_id)
            return 1

    from utils.api_lms_permissions import resolve_application_permissions

    print("\n  %-12s %-24s %-12s %-12s %s"
          % ("CASE", "SEGMENT", "ANALYST", "MATCHES?", "MAY ATTACH"))
    blocked, padding = 0, 0
    for a in apps[:40]:
        an = a.get("analyst") or {}
        acode = str(an.get("code", "") or "").strip() if isinstance(an, dict) else ""
        exact = bool(acode) and acode == caller
        loose = bool(acode) and _digits(acode) == _digits(caller)
        try:
            p = resolve_application_permissions(u, a) or {}
        except Exception:
            p = {}
        may = bool(p.get("can_edit") or p.get("can_submit_to_dcc")
                   or p.get("can_decide") or p.get("is_assigned_analyst"))

        note = ""
        if not acode:
            note = "  <- case has NO analyst"
        elif exact:
            note = ""
        elif loose:
            note = "  <- SAME PERSON, different padding"
            padding += 1
        else:
            note = "  <- assigned to somebody else"
        if not may:
            blocked += 1

        print("  %-12s %-24s %-12s %-12s %-10s%s"
              % (str(a.get("id"))[:12],
                 str(a.get("segment") or a.get("department") or "")[:24],
                 acode or "none",
                 "yes" if exact else ("padding" if loose else "no"),
                 "yes" if may else "403", note))

    print("\n" + "=" * 84)
    if padding:
        print("THE CODES DIFFER ONLY BY PADDING")
        print("=" * 84)
        print("  %d case(s) are assigned to this person under a differently" % padding)
        print("  punctuated staff code - KE0539 against KE539. That is the same")
        print("  fault that stopped a portfolio owner being recognised, and the")
        print("  fix is the same: compare the digits.")
        return 1
    if blocked == len(apps[:40]) and apps:
        print("SHE IS NOT THE ASSIGNED ANALYST ON ANY OF THESE")
        print("=" * 84)
        print("  The gate asks whether she is working THIS case, not whether")
        print("  she is an analyst for the segment.")
        print("\n  If a segment analyst is meant to attach papers to any case in")
        print("  her segment - which is what 'the analysts should be allowed to")
        print("  introduce and upload documents along the journey' means - then")
        print("  the gate is asking the wrong question and needs widening to")
        print("  the segment, deliberately, not by accident.")
        return 1
    print("SHE MAY ATTACH TO %d OF %d" % (len(apps[:40]) - blocked, len(apps[:40])))
    print("=" * 84)
    print("\n  If the 403 was on a specific case, name it with --app and this")
    print("  will say which test that one failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
