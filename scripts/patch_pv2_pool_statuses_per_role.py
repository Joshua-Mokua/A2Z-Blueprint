#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Let each pool role see only the statuses that are its work.

The pool has one status list shared by every role in it. Adding Credit Risk to
the roles gave Korir everything on that list - including cases still with the
department analysts, which are not his to review and only make it harder to
find the ones that are.

Adds an optional per-role override. A role with an entry sees only those
statuses; a role without one keeps the shared list exactly as now.

    pool_visibility: {
      roles:    [ ... ],
      statuses: [ ... ],              the default, unchanged
      role_statuses: {
        "credit risk": ["approved"]   only what a committee has approved
      }
    }

    python scripts/patch_pv2_pool_statuses_per_role.py            # dry run
    python scripts/patch_pv2_pool_statuses_per_role.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_lms_scope.py")

OLD = '''    pool_ok = _role_sees_pool(caller_role, pool_cfg["roles"])
    pool_statuses = {s.strip().lower() for s in pool_cfg["statuses"]}'''

NEW = '''    pool_ok = _role_sees_pool(caller_role, pool_cfg["roles"])
    pool_statuses = {s.strip().lower() for s in pool_cfg["statuses"]}

    # ── SOME ROLES ONLY WANT PART OF THE POOL ────────────────────────────────
    # One status list served every pool role. Adding Credit Risk gave that role
    # everything on it, including cases still with the department analysts -
    # not theirs to review, and enough of them to bury the ones that are.
    #
    # A role listed here sees only its own statuses. A role that is not listed
    # keeps the shared list exactly as before.
    _per_role = pool_cfg.get("role_statuses") or {}
    if isinstance(_per_role, dict) and caller_role:
        _cr = str(caller_role).strip().lower()
        for _rk, _sts in _per_role.items():
            if str(_rk).strip().lower() in _cr and isinstance(_sts, (list, tuple)):
                pool_statuses = {str(x).strip().lower() for x in _sts if str(x).strip()}
                break'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "SOME ROLES ONLY WANT PART OF THE POOL" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The pool config block matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    # A role with no entry must be unaffected.
    if "if isinstance(_per_role, dict)" not in NEW:
        print("A missing or malformed role_statuses would break every role.")
        return 1
    # An empty override must not silently open the whole pool.
    if 'if str(x).strip()' not in NEW:
        print("An empty entry would leave the status set empty or unfiltered.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("A pool role can now be given its own status list.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("Nothing changes until a role_statuses entry is configured.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_pv2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nNothing has changed yet. Set the narrowed list:")
    print('   python scripts/set_pool_statuses_for_role.py --role "credit risk" \\')
    print('       --statuses approved --apply')
    return 0


if __name__ == "__main__":
    sys.exit(main())
