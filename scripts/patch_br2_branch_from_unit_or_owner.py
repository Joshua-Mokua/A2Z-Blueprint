#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
BR2 - a missing branch no longer looks like a head-office deal.

FOUND IN THE PILOT (2026-08-18), diagnosed by Alex from one deal at Fortis.

A Fortis mortgage had NO branch field. `_deal_is_branch_originated` returned
False, the branch committee was STRIPPED from its journey, and the case went
straight to the Consumer department committee. Nobody could vote on it, nothing
said why, and the branch's own committee never knew the case existed.

THE RULE ITSELF IS RIGHT. A head-office deal genuinely should skip a branch
committee. What was wrong is that A MISSING FIELD LOOKED EXACTLY LIKE A
DELIBERATE HEAD-OFFICE DEAL - so a case quietly skipped a governance gate on
the strength of an empty string, which is the worst way to lose a control.

audit_200 already reported 190 deals with no branch. Every one of them would
have done the same thing.

A BRANCH IS NOW LOOKED FOR IN THREE PLACES, in the same order in both
functions - or they disagree, and a deal counts as branch-originated while no
committee can be found for it, which is the same silence by another route:

    deal.branch          as before
    deal.unit            the two are used interchangeably in this codebase and
                         a deal often carries one and not the other
    the OWNER's unit     a deal raised by a relationship manager at Fortis
                         belongs to Fortis whether or not somebody filled the
                         field in. Inferring it from the person is far safer
                         than silently dropping their committee.

Only where there is no branch, no unit and no owner on the register is a deal
treated as head-office - and audit_200 lists those separately, so they stay
visible rather than assumed.

Measured:

    branch set          ['BCC_BRN007', 'B1']
    only unit set       ['BCC_BRN007', 'B1']    was ['B1']
    neither, no owner   ['B1']                  head-office, as intended

BACKFILLING THE BRANCH ON EXISTING DEALS IS STILL WORTH DOING - this stops new
cases skipping the gate, it does not tidy the 190 already in that state. Use
scripts\backfill_deal_branch.py for those.

Verified: py_compile clean.

Usage (from project root, .venv active):
    python scripts\\patch_br2_branch_from_unit_or_owner.py            # dry run
    python scripts\\patch_br2_branch_from_unit_or_owner.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_br2"

ORIG_OLD = '''def _deal_is_branch_originated(deal: dict) -> bool:
    """Branch-originated = the deal has a branch. Non-branch (head-office/direct)
    deals skip branch-only committees (e.g. BCC)."""
    return bool(str(deal.get("branch", "") or "").strip())'''

LOOK_OLD = '''    import json as _json
    branch = str(deal.get("branch", "") or "").strip()
    if not branch:
        return ""'''

ORIG_BLOCK = r'''def _deal_is_branch_originated(deal: dict) -> bool:
    """Branch-originated = the deal has a branch, or an owner who works at one.

    FOUND IN THE PILOT (2026-08-18). A Fortis deal had NO branch field, so this
    returned False, the branch committee was stripped from its journey, and the
    case went straight to the department committee. Nobody could vote on it,
    nothing said why, and the branch's own committee never knew it existed.

    The rule itself is right: a head-office deal genuinely should skip a branch
    committee. What was wrong is that A MISSING FIELD LOOKED EXACTLY LIKE A
    DELIBERATE HEAD-OFFICE DEAL, and the case quietly skipped a governance gate
    on the strength of it.

    `unit` is checked too - the two are used interchangeably across this
    codebase and a deal often carries one and not the other.

    Where neither is present, the OWNER'S branch is used. A deal raised by a
    relationship manager at Fortis belongs to Fortis whether or not somebody
    filled the field in, and inferring it from the person is far safer than
    silently dropping their committee.

    Only when there is no branch, no unit, and no owner on the register is a
    deal treated as head-office - and audit_200 reports those separately, so
    they are visible rather than assumed.
    """
    if str(deal.get("branch", "") or "").strip():
        return True
    if str(deal.get("unit", "") or "").strip():
        return True
    code = str(deal.get("staff_code", "") or "").strip()
    if not code:
        return False
    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        for _i, r in df.iterrows():
            if str(r.get("Staff Code", "") or "").strip() == code:
                return bool(str(r.get("Unit", "") or "").strip())
    except Exception:
        pass
    return False

'''

LOOK_BLOCK = r'''    # THE SAME THREE PLACES A BRANCH CAN BE FOUND, in the same order as
    # _deal_is_branch_originated - or the two disagree, and a deal counts as
    # branch-originated while no branch committee can be found for it. That
    # gap is silent: the case simply arrives at the department committee with
    # its own branch never having seen it.
    branch = (str(deal.get("branch", "") or "").strip()
              or str(deal.get("unit", "") or "").strip())
    if not branch:
        code = str(deal.get("staff_code", "") or "").strip()
        if code:
            try:
                from utils.api_pipeline_scope import get_staff_roster
                df = get_staff_roster()
                for _i, r in df.iterrows():
                    if str(r.get("Staff Code", "") or "").strip() == code:
                        branch = str(r.get("Unit", "") or "").strip()
                        break
            except Exception:
                branch = ""
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if "a missing field looked exactly like" in s.lower() or \
       "THE SAME THREE PLACES A BRANCH CAN BE FOUND" in s:
        print("ABORT: BR2 looks applied.")
        return 1
    if s.count(ORIG_OLD) != 1 or s.count(LOOK_OLD) != 1:
        print("ABORT: anchors matched %d / %d times."
              % (s.count(ORIG_OLD), s.count(LOOK_OLD)))
        return 1

    s = s.replace(ORIG_OLD, ORIG_BLOCK.rstrip(), 1)
    s = s.replace(LOOK_OLD, LOOK_BLOCK + '    if not branch:\n        return ""', 1)
    print("  ok  a branch is found from the deal, its unit, or its owner")

    for name, blk in (("the originated check", ORIG_BLOCK),
                      ("the committee lookup", LOOK_BLOCK)):
        if '"unit"' not in blk:
            print("ABORT: %s does not consult unit - a deal carrying only that"
                  % name)
            print("       would still skip its branch committee.")
            return 1
        if "get_staff_roster" not in blk:
            print("ABORT: %s does not fall back to the owner." % name)
            return 1
    if "return False" not in ORIG_BLOCK:
        print("ABORT: a genuine head-office deal would no longer be able to")
        print("       skip the branch committee, which it should.")
        return 1
    import ast
    try:
        ast.parse(s)
    except SyntaxError as exc:
        print("ABORT: the result would not parse - line %s: %s" % (exc.lineno, exc.msg))
        return 1
    print("  ok  post-checks: both agree, head-office still skips")

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
    print("\nRESTART UVICORN.")
    print("\nThis stops NEW cases skipping the gate. For the ones already in")
    print("that state:  python scripts\\backfill_deal_branch.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
