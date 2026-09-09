#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Let the bank add a role to the full-visibility list without a code change.

Nine roles see every deal, hardcoded: MD, CEO, admin, Head of Branches. A role
that is not in the list falls back to its department or its cascade, and
nothing on screen explains why.

Credit Risk Manager oversees the whole book and sees nothing. That is the
fourth hardcoded role list to cost a day - Credit Risk Manager against the
pool, Credit Administration Officer, Head CAD, and now this.

org_config.json -> all_view_roles is added to the built-in set, never replaces
it, so nothing that works today stops.

    python scripts/patch_av1_all_view_roles_configurable.py            # dry run
    python scripts/patch_av1_all_view_roles_configurable.py --apply

Then:
    python scripts/set_all_view_roles.py --add "credit risk manager" --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "core_audit.py")

OLD = '''    if (is_admin or "admin" in role_l
            or role_l in _ALL_VIEW_ROLES'''

NEW = '''    # The bank can add a role without a code change. Added to the built-in
    # set, never replacing it, so nothing that works today stops working.
    _extra_all_view = set()
    try:
        from utils.config import load_org_config as _loc
        _extra_all_view = {str(r).strip().lower()
                           for r in ((_loc() or {}).get("all_view_roles") or [])
                           if str(r).strip()}
    except Exception:
        pass
    if (is_admin or "admin" in role_l
            or role_l in _extra_all_view
            or role_l in _ALL_VIEW_ROLES'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("%s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "_extra_all_view" in s:
        print("Already applied.")
        return 1
    if s.count(OLD) != 1:
        print("The all-view check matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)

    if "_ALL_VIEW_ROLES" not in NEW:
        print("The built-in roles would be replaced rather than added to.")
        return 1
    if "except Exception" not in NEW:
        print("A missing or malformed config would break every scope check.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("Would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("all_view_roles in org_config is honoured, on top of the built-ins.")

    if not apply:
        print("\nDry run. Re-run with --apply.")
        print("Nothing changes until a role is configured.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_av1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("Applied %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("Compiles.")
    except Exception as exc:
        print("Failed: %s" % exc)
        return 1
    print("\nNothing has changed yet:")
    print('   python scripts/set_all_view_roles.py --add "credit risk manager" --apply')
    return 0


if __name__ == "__main__":
    sys.exit(main())
