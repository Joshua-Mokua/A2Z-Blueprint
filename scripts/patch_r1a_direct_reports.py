#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
R1a - a unit is its DIRECT REPORTS, not its subtree.

MY ERROR, CORRECTED. I had the index MOVING upward - a branch RM's points
leaving Fortis and banking to Consumer. That is not the model.

THE MODEL (ruling 2026-08-08, confirmed):

    A person's index belongs to the unit that EMPLOYS them. Joyce's Fortis
    index includes every Fortis staff member - Consumer RMs, SME RMs, DSAs,
    tellers - because they are her direct reports. Nothing is carved out.

    Higher levels ADD, they do not re-sum. Head of Consumer does not re-count
    those branch RMs. They SEE them through the dotted line, and their own
    index is what THEY add: their Head Office team plus their own contribution,
    referrals included - the same way a Branch Manager adds a branch line on
    top of their staff.

    So the bank total is every person counted once at their employing unit,
    plus each node's own increments. No double counting, because nothing is
    added twice; no subtraction, because nothing is removed from the branch.

    The dotted line is therefore PURELY VISIBILITY - Head of Consumer sees the
    Consumer book across every branch, exactly as the pipeline does - and never
    moves anybody's index.

WHAT CHANGES
  utils/org_validator.direct_reports_of_role(role)
      Staff codes reporting DIRECTLY to the holder(s) of a role, resolved from
      the register's Reports To column - the same column the rest of the
      hierarchy uses. Vectorised, one pass.

  /unit-days
      A unit's members were get_visible_staff_codes (the whole subtree). Taking
      the subtree pulled every branch staff member back into CCB and counted
      them twice. Members are now direct reports.

PROVEN on a fixture mirroring the real chain
  (MD -> Director CCB -> Head of Commercial Banking -> Head of Branches ->
   Branch Manager -> RO -> DSA):

      Director CCB          -> Head Commercial, CCB Analyst     (its own only)
      Head of Commercial    -> Head of Branches
      Head of Branches      -> Branch Manager
      Branch Manager        -> Relationship Officer

  Fortis staff stay in Fortis. CCB does not re-absorb the branch.

Usage (from project root, .venv active):
    python scripts\\patch_r1a_direct_reports.py            # dry run
    python scripts\\patch_r1a_direct_reports.py --apply    # write + .pre_r1a backups
"""
import os
import shutil
import sys

OV = os.path.join("utils", "org_validator.py")
API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_r1a"

OV_ANCHOR = "def units_validated_by(validator_code: str) -> dict:"

FN_NEW = r'''def direct_reports_of_role(role: str) -> list:
    """Staff codes of the people who report DIRECTLY to the holder(s) of a role.

    Ruling 2026-08-08: a person's index belongs to the unit that employs them,
    and a higher level ADDS its own increment rather than re-summing what is
    already counted below. A unit is therefore its direct reports — not its
    subtree. Taking the subtree would pull every branch staff member back into
    CCB and count them twice.

    Resolved from the register's Reports To (the live "Reports To Code"), so it
    follows the same column the rest of the hierarchy uses.
    """
    df = _register()
    r = _s(role)
    if df.empty or not r or "Staff Code" not in df.columns:
        return []
    if "Role" not in df.columns or "Reports To" not in df.columns:
        return []

    roles = df["Role"].astype(str).str.strip()
    holders = [c for c in df["Staff Code"][roles.str.lower() == r.lower()].tolist()
               if _s(c)]
    if not holders:
        return []
    hold = {_s(h) for h in holders}
    reports = df["Reports To"].astype(str).str.strip()
    codes = df["Staff Code"].astype(str).str.strip()
    mask = reports.isin(hold) & (~codes.isin(hold))
    return [c for c in codes[mask].tolist() if c]


'''

BLOCK_NEW = r'''    # RULING 2026-08-08: a person's index belongs to the unit that EMPLOYS them.
    # Higher levels do not re-sum what is already counted below — they ADD their
    # own increment. So a unit's members are its DIRECT REPORTS, never its whole
    # subtree; taking the subtree would re-absorb the branches under CCB and
    # double every branch staff member.
    #
    # The dotted line therefore grants VISIBILITY (Head of Consumer sees the
    # Consumer book across every branch, exactly as the pipeline does) without
    # moving anybody's index out of their branch.
    try:
        from utils.org_validator import direct_reports_of_role
    except Exception:
        direct_reports_of_role = None

    urows = []
    for unit in uscope.get("units", []):
        codes = set()
        if direct_reports_of_role:
            try:
                codes = {_canon_u(c) for c in direct_reports_of_role(unit)}
            except Exception:
                codes = set()
        members = [(d.get("code") or ck, d) for ck, d in dims.items()
                   if _canon_u(d.get("code") or ck) in codes]
'''


API_OLD = """    urows = []
    for unit in uscope.get("units", []):
        try:
            from utils.api_pipeline_scope import get_visible_staff_codes
            codes = {_canon_u(c) for c in get_visible_staff_codes(
                {"staff_code": "", "role": unit, "is_admin": False})}
        except Exception:
            codes = set()
        # Non-branch members only: branch days terminate at the Head of Branches,
        # so counting them inside a unit would double them.
        members = [(d.get("code") or ck, d) for ck, d in dims.items()
                   if _canon_u(d.get("code") or ck) in codes
                   and str((d or {}).get("branch") or "").strip().lower() == "head office"]"""


def main():
    apply = "--apply" in sys.argv
    for p in (OV, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    ov = open(OV, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "direct_reports_of_role" in ov:
        print("ABORT: org_validator already has direct_reports_of_role - R1a looks applied.")
        return 1
    if "units_validated_by" not in ov:
        print("ABORT: apply patch_r1_units.py first.")
        return 1
    if ov.count(OV_ANCHOR) != 1:
        print("ABORT: org_validator anchor matched %d times." % ov.count(OV_ANCHOR))
        return 1
    if api.count(API_OLD) != 1:
        print("ABORT: unit-member block matched %d times (expected 1)." % api.count(API_OLD))
        return 1

    ov = ov.replace(OV_ANCHOR, FN_NEW + OV_ANCHOR, 1)
    print("  ok  org_validator - direct_reports_of_role")

    api = api.replace(API_OLD, BLOCK_NEW, 1)
    print("  ok  /unit-days - members are direct reports, not the subtree")

    if "get_visible_staff_codes" in api[api.index("def branch_log_unit_days("):
                                        api.index("@router.get(\"/branch-days\")")]:
        print("ABORT: post-check - /unit-days still resolves members by subtree.")
        return 1
    if "direct_reports_of_role" not in api:
        print("ABORT: post-check - direct-report resolution not wired.")
        return 1
    print("  ok  post-checks: subtree resolution gone from /unit-days")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((OV, ov), (API, api)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (OV, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1
    print("\nRestart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
