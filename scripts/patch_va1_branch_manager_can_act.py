#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
VA1 - a manager at the branch can act, not only the one line manager.

FROM THE BANK (2026-09-04), Betty Waiguru by email and Osoro Hilda at Kisumu -
three deals listed, each saying:

    not yours to validate

THE DAY VIEW HAS ITS OWN, STRICTER RULE. pipeline_validation_queue does not use
the cascade or the branch. It resolves ONE validator for the deal's owner and
compares:

    v = resolve_validator(deal["staff_code"])
    can_act = str(v.get("validator_code") or "") == my_code

So exactly one person in the bank may act on each deal - that owner's line
manager. If they are away, nobody can, and the day cannot close.

THIS IS THE FOURTH PLACE THIS DECISION IS MADE:

    the validate endpoint      cascade OR the caller's branch     (BV2)
    the queue listing          cascade OR the caller's branch     (BV3)
    the per-deal permission    cascade only                       (BV4, pending)
    THIS day view              one named validator                (here)

Each was widened separately, and this one was never found because it lives in
a different module and answers a different screen.

WHAT THIS CHANGES: can_act is also true for a MANAGER AT THE SAME BRANCH as the
deal's owner - the same rule the validate endpoint uses, so a person who is
shown the button can use it.

    the resolved validator            can act, as now
    an admin                          can act, as now
    a manager at the owner's branch   can act - new
    anybody else                      cannot, as now

BOTH SIDES MUST HAVE A BRANCH. A blank matches nothing, as everywhere else: a
wildcard would let any manager act on any deal in the bank.

READ-ONLY STAYS READ-ONLY. A tier-2 caller inspecting another branch has
can_act forced false before this, and that is untouched.

Usage (from project root, .venv active):
    python scripts\patch_va1_branch_manager_can_act.py            # dry run
    python scripts\patch_va1_branch_manager_can_act.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_pipeline_validation.py")

OLD = '''                try:
                    from utils.org_validator import resolve_validator
                    v = resolve_validator(str(d.get("staff_code") or ""))
                    can_act = str(v.get("validator_code") or "") == my_code
                except Exception:
                    can_act = False'''

NEW = '''                try:
                    from utils.org_validator import resolve_validator
                    v = resolve_validator(str(d.get("staff_code") or ""))
                    can_act = str(v.get("validator_code") or "") == my_code
                except Exception:
                    can_act = False

                # ── OR A MANAGER AT THE OWNER'S BRANCH ──────────────────────
                # RULING (2026-09-04): a branch's work must not stop because
                # one person is away. The validate endpoint already accepts a
                # manager at the deal's branch; this screen did not, so it
                # showed three deals and said "not yours to validate" about
                # every one of them.
                #
                # Exactly one person in the bank could act on each deal - that
                # owner's line manager - and the day could not close without
                # them.
                #
                # BOTH SIDES MUST HAVE A BRANCH. A blank matches nothing, or
                # any manager could act on any deal in the bank.
                if not can_act:
                    try:
                        from utils.api_pipeline_manager_actions import (
                            is_manager as _is_mgr)
                        if _is_mgr(user):
                            from utils.api_pipeline_scope import (
                                get_staff_roster as _gsr)
                            _r = _gsr()
                            _col = "Branch" if "Branch" in _r.columns else "Unit"
                            _mine = str(user.get("branch", "") or "").strip()
                            if not _mine and my_code:
                                _me_row = _r[_r["Staff Code"].astype(str)
                                             .str.strip() == my_code]
                                if not _me_row.empty:
                                    _mine = str(_me_row.iloc[0].get(_col) or "").strip()
                            _theirs = str(d.get("branch", "") or "").strip()
                            if not _theirs:
                                _ow = _r[_r["Staff Code"].astype(str).str.strip()
                                         == str(d.get("staff_code") or "").strip()]
                                if not _ow.empty:
                                    _theirs = str(_ow.iloc[0].get(_col) or "").strip()
                            can_act = (bool(_mine) and bool(_theirs)
                                       and _mine.lower() == _theirs.lower())
                    except Exception:
                        # Never widen on an error - a failed lookup leaves the
                        # caller with exactly what the line-manager test gave.
                        pass'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "OR A MANAGER AT THE OWNER'S BRANCH" in s:
        print("ABORT: VA1 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the can_act block matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  a manager at the owner's branch can act")

    if "bool(_mine) and bool(_theirs)" not in NEW:
        print("ABORT: a blank branch would match, letting any manager act on")
        print("       any deal in the bank.")
        return 1
    if "_is_mgr(user)" not in NEW:
        print("ABORT: a non-manager would be let in.")
        return 1
    if "if not can_act:" not in NEW:
        print("ABORT: this must only ADD - the line-manager test still stands")
        print("       on its own.")
        return 1
    # inspect_only must still force can_act false BEFORE this runs.
    _i = s.index("OR A MANAGER AT THE OWNER'S BRANCH")
    if "inspect_only" not in s[max(0, _i - 1200):_i]:
        print("ABORT: the read-only guard no longer runs first. A tier-2")
        print("       caller inspecting another branch must stay read-only.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: adds only, blank never matches, read-only intact")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_va1")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. Betty and Hilda should be able to validate the")
    print("deals their screens already list.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
