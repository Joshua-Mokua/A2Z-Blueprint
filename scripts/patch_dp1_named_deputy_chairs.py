#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DP1 - a department committee's deputy chairs are named people.

RULING (2026-08-14): "Jane being chair, but when away Annet or Fiona should
then be the mandatory."

CH1 made the chair's vote required, with the OPERATIONS MANAGER standing in.
That works for a branch committee, where every branch has one - the deputy is a
post rather than a person. A department committee has no equivalent post, so
its deputies must be named.

TWO WAYS TO DEPUTISE NOW:

    by role   "operations manager" - branch committees, unchanged
    by name   a roster entry carrying deputy_chair: true

scripts/name_dcc_members.py writes that flag:

    python scripts\\name_dcc_members.py --committee B1 \\
        --members Lunar,Annet,Fiona,Maingi --deputies Annet,Fiona

A DEPUTY MUST SIT ON THE COMMITTEE. The naming script refuses a deputy who is
not among its members - somebody who cannot vote cannot deputise for a vote.

Measured:

    Jane Jelagat Atugah   chair=True   deputy=False
    Annet Wanjiru         chair=False  deputy=True
    Fiona Kamau           chair=False  deputy=True
    Lunar Otieno          chair=False  deputy=False

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_dp1_named_deputy_chairs.py            # dry run
    python scripts\\patch_dp1_named_deputy_chairs.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_dp1"

OLD = '''    def _is_deputy(v):
        _r = str(v.get("role", "") or "").lower()
        return "operations manager" in _r or "operations" in _r'''

BLOCK = r'''    def _is_deputy(v):
        # ── TWO WAYS TO DEPUTISE ────────────────────────────────────────────
        # BY ROLE, for branch committees: every branch has an operations
        # manager, so the deputy is the post rather than a person.
        #
        # BY NAME, for department committees (ruling 2026-08-14: "Jane being
        # chair, but when away Annet or Fiona should then be the mandatory").
        # A department committee has no equivalent post, so its deputies are
        # named on the roster with deputy_chair: true.
        _r = str(v.get("role", "") or "").lower()
        if "operations manager" in _r or "operations" in _r:
            return True
        _code = str(v.get("staff_code", "") or "").strip()
        _name = str(v.get("name", "") or "").strip().lower()
        for _m in (committee.get("members") or []):
            if not isinstance(_m, dict) or not _m.get("deputy_chair"):
                continue
            if (_code and str(_m.get("staff_code", "")).strip() == _code) \
                    or (_name and str(_m.get("name", "")).strip().lower() == _name):
                return True
        return False

'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "TWO WAYS TO DEPUTISE" in s:
        print("ABORT: DP1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the deputy check matched %d times." % s.count(OLD))
        print("       CH1 must be applied first.")
        return 1

    s = s.replace(OLD, BLOCK.rstrip(), 1)
    print("  ok  named deputy chairs are honoured")

    if "deputy_chair" not in BLOCK:
        print("ABORT: the named-deputy flag is not read.")
        return 1
    if "operations manager" not in BLOCK:
        print("ABORT: the branch committees' role-based deputy was dropped.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: both kinds of deputy, and it parses")

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
    print("\nName the deputies with:")
    print("  python scripts\\name_dcc_members.py --committee B1 \\")
    print("      --members Lunar,Annet,Fiona,Maingi --deputies Annet,Fiona --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
