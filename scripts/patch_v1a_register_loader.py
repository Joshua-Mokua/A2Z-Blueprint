#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
V1a - CRITICAL: the staff register was never loading in org_validator.

utils/org_validator._register() read `sheet_name="Staff Register"`. The live
data/staff_register.xlsx exports as `Sheet1`. pandas raised, the bare `except`
swallowed it, and the function returned an EMPTY DataFrame.

Consequence: EVERY validator lookup in this module returned _admin_fallback -
for daily logs AND for pipeline deals. Nothing errored, nothing logged; the
system just quietly routed all validation to admin.

Proven on the live file:
    SHEETS: ['Sheet1']
    _register() rows: 0

TWO MORE MISMATCHES, found once the sheet loaded:

  * The register carries `Reports To Code` - an actual STAFF CODE - where the
    older export carried `Reports To` as a ROLE NAME. line_manager_of() was
    feeding a code into _resolve_role_in_unit() and finding nothing. It now
    resolves a direct code lookup first and keeps role-resolution as fallback.

  * The register carries BOTH `Branch` and `Unit`. Branch is the physical site
    the management triad belongs to; Unit holds a department on some rows. The
    triad now resolves on Branch, falling back to Unit.

VERIFIED against a fixture matching the live schema exactly:

    Fortis staff        -> mode=triad, 3 validators (BM, ABSOM, CSM)
    Head Office staff   -> mode=line_manager, correct reports-to person
    Eldoret (no BM)     -> triad of the roles that DO exist
    BM validates own branch staff                     True
    CSM of another branch validates Fortis staff      False
    a teller validates a peer                         False

Usage (from project root, .venv active):
    python scripts\\patch_v1a_register_loader.py            # dry run
    python scripts\\patch_v1a_register_loader.py --apply    # write + .pre_v1a backup
"""
import os
import shutil
import sys

OV = os.path.join("utils", "org_validator.py")
BACKUP_SUFFIX = ".pre_v1a"

REG_NEW = r'''def _register() -> pd.DataFrame:
    """Load the staff register with its REAL header (row 0). Cached.

    Note: we deliberately read the file directly rather than via
    build_staff_registry(), which reads header=1 and mis-parses this file.
    """
    from utils.core import DATA_DIR
    sr = Path(DATA_DIR) / "staff_register.xlsx"
    if not sr.exists():
        return pd.DataFrame()

    # The sheet was named "Staff Register" historically; the live file exports
    # as "Sheet1". Reading only the named sheet raised, was swallowed, and
    # returned an EMPTY frame — which made every validator lookup in this module
    # (daily logs AND deals) fall through to the admin fallback, silently.
    # Try the named sheet, then the first sheet.
    df = pd.DataFrame()
    for sheet in ("Staff Register", 0):
        try:
            df = pd.read_excel(sr, sheet_name=sheet, header=0)
            if df is not None and len(df):
                break
        except Exception:
            continue
    if df is None or df.empty:
        return pd.DataFrame()

    df.columns = [str(c).strip() for c in df.columns]

    # Column aliases: the live register carries "Reports To Code" (a staff code)
    # and a separate "Branch" alongside "Unit". Normalise without renaming the
    # source file.
    if "Reports To" not in df.columns and "Reports To Code" in df.columns:
        df["Reports To"] = df["Reports To Code"]
    if "Unit" not in df.columns and "Branch" in df.columns:
        df["Unit"] = df["Branch"]

    for col in ("Staff Code", "Staff Name", "Role", "Unit", "Branch",
                "Department", "Region", "Reports To", "Reports To Code"):
        if col in df.columns:
            df[col] = df[col].map(_s)
    return df


'''

LM_NEW = r'''    want = _s(p.get("Reports To", ""))
    if not want or want.lower() == "nan":
        return _admin_fallback("person is top-of-tree (no Reports To)")

    # The live register stores "Reports To Code" — an actual staff code — where
    # older exports stored a ROLE NAME. A direct code lookup is both cheaper and
    # exact, so prefer it and keep the role-resolution path as the fallback.
    direct = df[df["Staff Code"] == want]
    if not direct.empty:
        res = _found(direct.iloc[0])
        res["via"] = "reports-to code"
        return res

'''


OLD_REG_MARK = '        df = pd.read_excel(sr, sheet_name="Staff Register", header=0)'
OLD_LM_MARK = '    row, how = _resolve_role_in_unit(df, want, unit or _HEAD_OFFICE, region)'
OLD_UNIT_MARK = '    unit = _s(p.get("Unit", ""))'
OLD_LOOP_MARK = '        if _s(row.get("Unit", "")).lower() != unit.lower():'


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(OV):
        print("ABORT: %s not found. Run from the project root." % OV)
        return 1
    ov = open(OV, encoding="utf-8").read()

    if "the live file exports as" in ov or "Try the named sheet, then the first sheet" in ov:
        print("ABORT: V1a looks applied already.")
        return 1
    if "daily_log_validators_for" not in ov:
        print("ABORT: apply patch_v1_validation_backend.py first.")
        return 1
    # _resolve_role_in_unit(...) appears in BOTH line_manager_of and
    # resolve_validator, so that anchor is only counted inside line_manager_of.
    lm_start = ov.index("def line_manager_of(staff_code: str) -> dict:")
    lm_end = ov.index("def resolve_validator(owner_code: str) -> dict:", lm_start)
    lm_slice = ov[lm_start:lm_end]
    # The same `unit = _s(p.get("Unit", ""))` line exists in line_manager_of;
    # the triad edits must only touch daily_log_validators_for.
    t_start = ov.index("def daily_log_validators_for(staff_code: str) -> dict:")
    t_end = ov.index("def can_validate_daily_log(", t_start)
    triad_slice = ov[t_start:t_end]
    checks = (("register loader", OLD_REG_MARK, ov),
              ("line_manager_of", OLD_LM_MARK, lm_slice),
              ("triad unit", OLD_UNIT_MARK, triad_slice),
              ("triad loop", OLD_LOOP_MARK, triad_slice))
    for label, mark, hay in checks:
        if hay.count(mark) != 1:
            print("ABORT: %s anchor matched %d times (expected 1)." % (label, hay.count(mark)))
            return 1

    i = ov.index("def _register() -> pd.DataFrame:")
    j = ov.index("def _admin_fallback(reason: str) -> dict:")
    ov = ov[:i] + REG_NEW + ov[j:]
    print("  ok  _register - sheet fallback + Reports To Code / Branch aliases")

    a = ov.index('    want = _s(p.get("Reports To", ""))',
                 ov.index("def line_manager_of(staff_code: str) -> dict:"))
    b = ov.index(OLD_LM_MARK, a)
    ov = ov[:a] + LM_NEW + ov[b:]
    print("  ok  line_manager_of - direct staff-code lookup")

    t_start = ov.index("def daily_log_validators_for(staff_code: str) -> dict:")
    t_end = ov.index("def can_validate_daily_log(", t_start)
    triad = ov[t_start:t_end]
    triad = triad.replace(
        OLD_UNIT_MARK,
        '    # The register carries BOTH Branch and Unit. Branch is the physical site\n'
        '    # the triad belongs to; Unit can hold a department on some rows.\n'
        '    unit = _s(p.get("Branch", "")) or _s(p.get("Unit", ""))', 1)
    triad = triad.replace(
        OLD_LOOP_MARK,
        '        row_branch = _s(row.get("Branch", "")) or _s(row.get("Unit", ""))\n'
        '        if row_branch.lower() != unit.lower():', 1)
    ov = ov[:t_start] + triad + ov[t_end:]
    print("  ok  triad resolves on Branch, falling back to Unit")

    if "Try the named sheet, then the first sheet" not in ov:
        print("ABORT: post-check - register loader was not replaced.")
        return 1
    if "reports-to code" not in ov:
        print("ABORT: post-check - direct code lookup missing.")
        return 1

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(OV, OV + BACKUP_SUFFIX)
    open(OV, "w", encoding="utf-8", newline="").write(ov)
    print("APPLIED %s  (backup: %s)" % (OV, os.path.basename(OV) + BACKUP_SUFFIX))

    import py_compile
    try:
        py_compile.compile(OV, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("")
    print("Verify with:  python scripts\\test_branch_triad.py Fortis")
    print("Expect mode=triad and three named validators. Then restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
