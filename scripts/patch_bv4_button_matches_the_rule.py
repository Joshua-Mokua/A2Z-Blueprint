#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BV4 - the Validate button works where the endpoint would accept it.

FROM THE BANK (2026-09-04): Osoro Hilda at Kisumu, and the same at Nyeri - the
deals are in the Pipeline validation tab and cannot be validated. The
diagnostic says nothing blocks her. Both are true, because THREE places decide
this and only two were widened.

    BV2 (09-03)  the VALIDATE ENDPOINT      cascade OR the caller's branch
    BV3 (09-04)  the QUEUE LISTING          cascade OR the caller's branch
    here         the PER-DEAL PERMISSION    cascade ONLY

    is_manager_in_scope = bool(deal_staff) and deal_staff in visible_staff_codes

can_validate is built from that flag, and the UI reads it to decide whether the
Validate button does anything. So the deal is listed, the endpoint would accept
it, and the button is dead - which is exactly the state this module already
warns about in its own docstring:

    "A Mortgage deal at 'Initiation' ... showed in the queue with can_validate
     False: the manager saw it and the button did nothing."

That was a fix half made on the stage rule. This is the same shape on the
branch rule.

WHAT THIS CHANGES: the permission uses the same test as the endpoint - the
cascade, OR the deal is at the caller's own branch.

BOTH SIDES MUST HAVE A BRANCH, as in BV2 and BV3. A blank matches nothing: a
wildcard would hand every unassigned deal to every manager.

NOTHING ELSE IN THE PERMISSION SET MOVES. can_validate still requires a
validation stage, an unvalidated deal, no pending cancellation and no draft.
This widens WHO, not WHAT.

Usage (from project root, .venv active):
    python scripts\patch_bv4_button_matches_the_rule.py            # dry run
    python scripts\patch_bv4_button_matches_the_rule.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api_pipeline_permissions.py")

OLD = '''    elif caller_is_manager:
        is_manager_in_scope = (
            bool(deal_staff) and deal_staff in visible_staff_codes
        )'''

NEW = '''    elif caller_is_manager:
        # ── THE CASCADE, OR THE CALLER'S OWN BRANCH ─────────────────────────
        # BV2 widened the validate endpoint and BV3 widened the queue. This
        # flag decides whether the BUTTON does anything, and it still asked
        # only the cascade - so a branch manager-tier person saw the deals,
        # the endpoint would have accepted them, and nothing happened when
        # they clicked.
        #
        # This module's own docstring warns about exactly this shape: "the
        # manager saw it and the button did nothing."
        #
        # BOTH SIDES MUST HAVE A BRANCH. A blank matches nothing - a wildcard
        # would hand every unassigned deal to every manager.
        _in_cascade = bool(deal_staff) and deal_staff in visible_staff_codes
        _same_branch = False
        if not _in_cascade:
            try:
                _mine = str(user.get("branch", "") or "").strip()
                _theirs = str(deal.get("branch", "") or "").strip()
                if not (_mine and _theirs):
                    from utils.api_pipeline_scope import get_staff_roster as _gsr
                    _r = _gsr()
                    _col = "Branch" if "Branch" in _r.columns else "Unit"
                    if not _mine and my_code:
                        _me = _r[_r["Staff Code"].astype(str).str.strip() == my_code]
                        if not _me.empty:
                            _mine = str(_me.iloc[0].get(_col) or "").strip()
                    if not _theirs and deal_staff:
                        _ow = _r[_r["Staff Code"].astype(str).str.strip() == deal_staff]
                        if not _ow.empty:
                            _theirs = str(_ow.iloc[0].get(_col) or "").strip()
                _same_branch = (bool(_mine) and bool(_theirs)
                                and _mine.lower() == _theirs.lower())
            except Exception:
                # Never widen on an error - a failed lookup must leave the
                # caller with exactly the cascade they had.
                _same_branch = False
        is_manager_in_scope = _in_cascade or _same_branch'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "THE CASCADE, OR THE CALLER'S OWN BRANCH" in s:
        print("ABORT: BV4 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the manager-in-scope block matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  the permission uses the same test as the endpoint")

    if "bool(_mine) and bool(_theirs)" not in NEW:
        print("ABORT: an unknown branch would match, handing every unassigned")
        print("       deal to every manager.")
        return 1
    if "_same_branch = False" not in NEW.split("except Exception")[1]:
        print("ABORT: an error would widen rather than narrow. A failed lookup")
        print("       must leave the caller with the cascade they had.")
        return 1
    if "_in_cascade or _same_branch" not in NEW:
        print("ABORT: the cascade is no longer honoured on its own.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: cascade kept, blank never matches, fails closed")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_bv4")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN. The Validate button should now work on the deals")
    print("that were listed but dead.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
