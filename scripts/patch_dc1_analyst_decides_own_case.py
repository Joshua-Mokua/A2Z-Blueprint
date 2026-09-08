#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""The analyst assigned to a case can record its verdict.

The permission engine grants can_record_decision to the assigned analyst, and
the screen shows the Approve / Decline / Return panel on that basis. The
endpoint then requires manager authority and refuses with a 403.

So an analyst sees the buttons and cannot use them. Brian hit this on
LMS00017.

The permission is the one that matches how the bank works: an analyst picks a
case and acts on it - there is no manager step in that flow, for commercial or
consumer. The endpoint is brought into line with it.

Manager and admin keep the authority they had. What changes is that the person
the case is assigned to can decide their own case.

    python scripts/patch_dc1_analyst_decides_own_case.py            # dry run
    python scripts/patch_dc1_analyst_decides_own_case.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_routes.py")

OLD = '''    # Tier check FIRST
    if not is_manager(user):
        raise HTTPException(
            status_code=403,
            detail="Manager authority required to record decisions",
        )

    lam = _lam()'''

NEW = '''    # The assigned analyst, a manager, or an admin.
    #
    # This required manager authority while the permission engine granted
    # can_record_decision to the ASSIGNED ANALYST - so the screen showed the
    # Approve / Decline / Return panel and the endpoint refused it. An analyst
    # picks a case and acts on it; there is no manager step in that flow.
    #
    # The scope check below still applies, so this does not let anybody decide
    # a case that is not theirs.
    lam = _lam()
    _app_early = lam.get(app_id)
    _mine = False
    if _app_early:
        _an = _app_early.get("analyst") or {}
        if isinstance(_an, dict):
            _mine = (str(_an.get("code", "") or "").strip()
                     == str(user.get("staff_code", "") or "").strip()
                     and bool(str(_an.get("code", "") or "").strip()))
    if not (is_manager(user) or user.get("is_admin") or _mine):
        raise HTTPException(
            status_code=403,
            detail=("This case is not assigned to you. Claim it from the pool "
                    "first, or ask the analyst who has it."),
        )
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "there is no manager step in that flow" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The decision guard matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    # An empty analyst code must never match an empty caller code.
    if "and bool(str(_an.get" not in NEW:
        print("An unassigned case would match a caller with no staff code.")
        return 1
    if "is_manager(user)" not in NEW:
        print("Managers would lose the authority they had.")
        return 1
    # The scope check that follows must still run.
    i = s.index("there is no manager step in that flow")
    if "is_app_in_scope" not in s[i:i + 2500]:
        print("The scope check no longer follows this. Anybody could decide")
        print("a case outside their cascade.")
        return 1
    # lam must not be defined twice in the route.
    j = s.index("/decision\"")
    k = s.index("\n@router.", j)
    if s[j:k].count("lam = _lam()") != 1:
        print("lam is now assigned %d times in this route."
              % s[j:k].count("lam = _lam()"))
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("The assigned analyst can decide their own case; scope still applies.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_dc1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nRestart uvicorn. Brian claims LMS00017 from the pool, then")
    print("Approve, Decline and Return all work on it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
