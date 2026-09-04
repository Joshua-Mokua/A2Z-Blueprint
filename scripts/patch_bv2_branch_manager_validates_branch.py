#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BV2 - a manager at a branch can validate that branch's deals.

RULING FROM THE BANK (2026-09-04): "not only the branch manager can validate a
deal - the Operations Manager, Customer Service Manager, Assistant Branch
Service & Operations Manager, or essentially anyone in management at the
branch. Just open it up fully, we will tighten as we progress; currently we
don't need to make it hard for them."

WHY IT WAS HARD. Validation followed the CASCADE, not the branch:

    visible_codes = get_visible_staff_codes(user)
    if sc not in visible_codes: 403 "Deal is outside your cascade scope"

A branch splits under two managers - tellers, CSOs and BOS report to
operations; relationship officers report to credit. So a Customer Service
Manager covering for an absent Branch Manager could validate half the branch
and was refused the other half, with a message about a "cascade scope" that
means nothing to somebody standing in a banking hall.

WHAT THIS ADDS: a manager may also validate a deal whose OWNER IS AT THEIR OWN
BRANCH. The cascade rule is untouched and still grants everything it granted
before; this only adds the branch.

    cascade  ->  allowed, exactly as before
    OR
    same branch AND the caller is a manager  ->  allowed

THIS IS DELIBERATELY BROAD, AND THE BANK SAID SO. It lets a Customer Service
Manager validate a relationship officer's credit deal. The alternative was
leaving branches unable to work while managers are away, and the bank chose
this knowingly with the intention of tightening later.

WHAT IT DOES NOT DO: it does not make a non-manager a validator, it does not
cross branches, and it does not touch what anybody can SEE - only who may
validate. Head office callers with no branch match nothing new.

Usage (from project root, .venv active):
    python scripts\patch_bv2_branch_manager_validates_branch.py            # dry run
    python scripts\patch_bv2_branch_manager_validates_branch.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "api.py")

OLD = '''    # Scope check — manager can only validate deals under their cascade
    visible_codes = get_visible_staff_codes(user)
    sc = str(deal.get("staff_code", "") or "")
    if sc not in visible_codes:
        _audit("API_PIPELINE_VALIDATE_FORBIDDEN", user,
               f"deal_id={deal_id} out of scope")
        raise HTTPException(
            status_code=403,
            detail="Deal is outside your cascade scope",
        )'''

NEW = '''    # Scope check — the cascade, OR the caller's own branch.
    visible_codes = get_visible_staff_codes(user)
    sc = str(deal.get("staff_code", "") or "")

    # ── A MANAGER AT A BRANCH MAY VALIDATE THAT BRANCH'S DEALS ──────────────
    # RULING (2026-09-04): "not only the branch manager ... essentially anyone
    # in management at the branch. Just open it up fully, we will tighten as we
    # progress."
    #
    # A branch splits under two managers - tellers, CSOs and BOS report to
    # operations; relationship officers report to credit. Following the cascade
    # alone meant a Customer Service Manager covering for an absent Branch
    # Manager could validate half the branch and was refused the other half,
    # with a message about "cascade scope" that means nothing to somebody
    # standing in a banking hall.
    #
    # THIS IS DELIBERATELY BROAD and the bank asked for it knowing so: it lets
    # a Customer Service Manager validate a relationship officer's credit deal.
    # The alternative was branches unable to work while managers are away.
    #
    # It ADDS to the cascade and never subtracts. It does not make a
    # non-manager a validator, and it does not cross branches: a caller with no
    # branch of their own matches nothing new.
    _same_branch = False
    if sc not in visible_codes:
        try:
            from utils.api_pipeline_scope import get_staff_roster as _gsr
            _r = _gsr()
            _mine = str(user.get("branch", "") or "").strip()
            if not _mine:
                _me = _r[_r["Staff Code"].astype(str).str.strip()
                         == str(user.get("staff_code", "") or "").strip()]
                if not _me.empty:
                    _mine = str(_me.iloc[0].get("Branch")
                                or _me.iloc[0].get("Unit") or "").strip()
            _them = str(deal.get("branch", "") or "").strip()
            if not _them and sc:
                _o = _r[_r["Staff Code"].astype(str).str.strip() == sc]
                if not _o.empty:
                    _them = str(_o.iloc[0].get("Branch")
                                or _o.iloc[0].get("Unit") or "").strip()
            # Both sides must be known. An empty branch is not a wildcard - it
            # would let anybody validate anybody.
            _same_branch = bool(_mine) and bool(_them) and _mine.lower() == _them.lower()
            if _same_branch:
                logger.info(
                    "validate: %s is outside the cascade but at the same "
                    "branch (%s) - allowed per the 2026-09-04 ruling",
                    sc, _mine)
        except Exception as exc:  # surfaced, never silent (CGR1)
            logger.warning("branch check failed validating %s: %s", deal_id, exc)

    if sc not in visible_codes and not _same_branch:
        _audit("API_PIPELINE_VALIDATE_FORBIDDEN", user,
               f"deal_id={deal_id} out of scope")
        raise HTTPException(
            status_code=403,
            detail="This deal belongs to another branch and is not in your team.",
        )'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(MOD):
        print("ABORT: %s not found." % MOD)
        return 1

    s = open(MOD, encoding="utf-8").read()
    if "A MANAGER AT A BRANCH MAY VALIDATE THAT BRANCH'S DEALS" in s:
        print("ABORT: BV2 looks applied.")
        return 1
    if s.count(OLD) != 1:
        print("ABORT: the scope check matched %d times." % s.count(OLD))
        return 1

    s = s.replace(OLD, NEW, 1)
    print("  ok  a manager may validate their own branch's deals")

    # An empty branch must never match, or anybody validates anybody.
    if "bool(_mine) and bool(_them)" not in NEW:
        print("ABORT: an unknown branch would match, which would let anybody")
        print("       validate anybody.")
        return 1
    # The manager test upstream must still be there - this widens the SCOPE,
    # not who counts as a manager.
    i_end = s.index("A MANAGER AT A BRANCH MAY VALIDATE")
    if "is_manager(user)" not in s[max(0, i_end - 3000):i_end]:
        print("ABORT: the manager check no longer runs before this. BV2 widens")
        print("       the scope, it does not make everybody a validator.")
        return 1
    if "logger.warning" not in NEW:
        print("ABORT: a failed branch lookup must say so - silence would refuse")
        print("       a legitimate manager and look like a permission decision.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: manager test intact, empty branch never matches")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(MOD, MOD + ".pre_bv2")
    open(MOD, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s" % MOD)
    import py_compile
    try:
        py_compile.compile(MOD, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1
    print("\nRESTART UVICORN.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
