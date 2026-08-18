#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
LG1 - the legal-assignment dropdown works, and credit admin can use it.

TWO FAULTS IN ONE ENDPOINT, found while walking the credit administrator's
page. Neither had ever surfaced, because nothing had asked for the list until
credit admin needed it to assign a case for charging.

1. IT RAISED FOR EVERY USER. `is_manager` is not defined at module level in
   api.py - every other caller imports it locally, and this one did not. So
   /api/credit-admin/my-legal-officers threw a NameError for everybody and the
   dropdown was empty for all users, always.

   A NameError on a path nobody exercises is invisible until somebody
   exercises it. That is the third one of these this fortnight.

2. THE ONE PERSON WHO NEEDS IT COULD NOT SEE THE POOL. The full legal list was
   restricted to legal chiefs, legal managers and general managers. Assigning a
   case for charging IS the credit administrator's job - and a Credit
   Administration Officer is none of those three, so even once the endpoint
   stopped raising they would have received an empty list and no explanation.

Verified: py_compile clean, and the endpoint returns without raising for a
credit administrator and for a legal director.

Usage (from project root, .venv active):
    python scripts\\patch_lg1_legal_officers.py            # dry run
    python scripts\\patch_lg1_legal_officers.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_lg1"

OLD = '''    full = bool(user.get("is_admin")) or ("legal" in role_l and (
        "chief" in role_l or "head" in role_l or "manager" in role_l)) or is_manager(user)'''

BLOCK = r'''    # `is_manager` is not defined at module level here - every other caller in
    # this file imports it locally, and this one did not. So the endpoint
    # raised a NameError for EVERY user, and the legal-assignment dropdown was
    # empty for everybody, always.
    #
    # It never surfaced because nothing had asked for the list until credit
    # admin needed it to assign a case for charging.
    try:
        from utils.api_pipeline_manager_actions import is_manager as _is_mgr
        _mgr = bool(_is_mgr(user))
    except Exception:
        _mgr = False
    # CREDIT ADMIN SEES THE LEGAL POOL. Assigning a case for charging IS the
    # credit administrator's job, and the list was restricted to legal chiefs
    # and managers - so the one person who needs the dropdown got an empty one.
    _credit_admin = any(w in role_l for w in
                        ("credit administration", "credit admin", "cad"))
    full = (bool(user.get("is_admin")) or _credit_admin
            or ("legal" in role_l and ("chief" in role_l or "head" in role_l
                                       or "manager" in role_l))
            or _mgr)'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "CREDIT ADMIN SEES THE LEGAL POOL" in s:
        print("ABORT: LG1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the legal gate matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, BLOCK.rstrip(), 1)
    print("  ok  the dropdown no longer raises, and credit admin can use it")

    if "is_manager(user)" in BLOCK:
        print("ABORT: the undefined name survives - it would still raise.")
        return 1
    if "_credit_admin" not in BLOCK:
        print("ABORT: credit admin would still get an empty list, which is the")
        print("       half that matters to the person doing the assigning.")
        return 1
    if "try:" not in BLOCK:
        print("ABORT: the local import is unguarded - if it ever moves, this")
        print("       raises again.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: no NameError, credit admin included, guarded")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % API)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. Credit admin can assign a case to a legal officer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
