#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
R1 - Head Office units and the consolidated roll-up (backend).

RULINGS (2026-08-08)
    Validation TERMINATES. A branch day is countersigned by the Head of
    Branches; a Head Office unit day by its Director. Nobody re-validates above
    that - re-validating the same object at three levels would make "validated"
    mean nothing in particular.

    The Business Manager is the last gate to the MD and carries the MD's profile
    plus admin. Both OBSERVE every level and may RETURN a day for amendment;
    neither countersigns.

UNITS ARE NOT INVENTED. md_reporting_roles() reads the roles that report to the
Managing Director in org_config.hierarchy - 16 today: CCB, Corporate Banking,
Operations & Technology, Credit Risk, Internal Audit, Internal Control, Legal,
Treasury, Compliance, Finance, HR, Country Risk, Corporate Communications, Head
of Consumer, Business Manager, PA. Not derived from the roster's Department
string, not listed in code. Change a reporting line in org_config and this
follows on the next read.

A unit's members come from get_visible_staff_codes - the SAME call the deal and
referral analytics use. There is one tree.

THE CCB OVERLAP, RESOLVED WITHOUT A CONVENTION. Head of Branches sits inside
CCB's subtree, and CCB also reports to the MD. Because branch days terminate at
the Head of Branches, a unit row counts only its HEAD OFFICE members - so CCB
covers Commercial Banking, SME, Local Corporates, Bancassurance and so on, while
branches roll up separately under a collapsed Branches node. Nothing is counted
twice.

ADDS
  utils/org_validator.md_reporting_roles()  - the units, from org_config
  utils/org_validator.units_validated_by()  - {units seen, units owned,
                                               top_of_house}
  GET /api/branch-log/unit-days?date=
      One collapsed BRANCHES node (a roll-up, not an owner) carrying every
      branch as children, plus one row per Head Office unit. Each row shows
      expected / filed / validated / not filed, submission status, index and
      owner. can_countersign is true only for the unit's own Director.

branch_day.py needs no change: it already keys on an arbitrary string, so a unit
day is stored exactly like a branch day, and the gate, exceptions and
notifications carry over unchanged.

FRONTEND IS R2: the three-level tree (Branches -> branch -> staff, plus unit
rows). R3 is the bank-wide follow-up list.

Verified: py_compile clean on both modules; md_reporting_roles() returns the 16
roles from org_config.

Usage (from project root, .venv active):
    python scripts\\patch_r1_units.py            # dry run
    python scripts\\patch_r1_units.py --apply    # write + .pre_r1 backups
"""
import os
import shutil
import sys

OV = os.path.join("utils", "org_validator.py")
API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_r1"

OV_ANCHOR = "def can_validate_daily_log(validator_code: str, staff_code: str) -> bool:"
API_ANCHOR = '@router.get("/branch-days")'

UNITS_NEW = r'''def md_reporting_roles() -> list:
    """The roles that report to the Managing Director in org_config.hierarchy.

    These ARE the Head Office units — Internal Control, Finance, HR, Treasury,
    CCB, Corporate Banking and the rest. They are not derived from the roster's
    Department string and not listed in code: change a reporting line in
    org_config and this follows on the next read.
    """
    try:
        from utils.config import load_org_config
        hier = (load_org_config() or {}).get("hierarchy") or {}
    except Exception:
        return []
    out = []
    for role, info in hier.items():
        parents = (list(info.get("reports_to", []) or [])
                   if isinstance(info, dict) else list(info or []))
        if any("managing director" in str(p).lower() for p in parents):
            out.append(role)
    return sorted(out)


def _is_top_of_house(role: str) -> bool:
    """MD, Business Manager or an admin — the observation tier.

    Ruling 2026-08-08: the Business Manager is the last gate to the MD and
    carries the MD's profile plus admin.
    """
    r = str(role or "").strip().lower()
    return ("managing director" in r or "chief executive" in r
            or r == "business manager" or "admin" in r)


def units_validated_by(validator_code: str) -> dict:
    """Which HEAD OFFICE UNITS does this person own?

    A unit is an MD-reporting role. Its owner is the holder of that role, and
    that owner's countersignature IS the unit's validation — validation
    TERMINATES there (ruling 2026-08-08). The MD and Business Manager observe
    every unit and may return one for amendment, but never re-validate.

    Returns {"units": [role, ...], "owns": [role, ...], "top_of_house": bool}
        units - what this person can SEE
        owns  - what this person may COUNTERSIGN (empty at the observation tier)
    """
    df = _register()
    vc = _s(validator_code)
    all_units = md_reporting_roles()
    if df.empty or not vc or "Staff Code" not in df.columns:
        return {"units": [], "owns": [], "top_of_house": False}

    me = df[df["Staff Code"] == vc]
    if me.empty:
        return {"units": [], "owns": [], "top_of_house": False}
    my_role = _s(me.iloc[0].get("Role", ""))

    if _is_top_of_house(my_role):
        return {"units": all_units, "owns": [], "top_of_house": True}

    owns = [u for u in all_units if _role_matches(my_role, u) or
            _s(my_role).lower() == _s(u).lower()]
    return {"units": owns, "owns": owns, "top_of_house": False}


'''

ENDPOINT_NEW = r'''@router.get("/unit-days")
def branch_log_unit_days(date: str = "", user: dict = Depends(get_current_user)):
    """The consolidated roll-up for the Business Manager and the MD.

    Ruling 2026-08-08: VALIDATION TERMINATES. A branch day is countersigned by
    the Head of Branches; a Head Office unit day by its Director. Nobody
    re-validates above that. This tier OBSERVES, and may return a day for
    amendment — it never countersigns.

    Shape:
        one collapsed BRANCHES node (a roll-up, not an owner) aggregating every
        branch, plus one row per MD-reporting unit from org_config.hierarchy.

    Because branch days stop at the Head of Branches, the CCB unit here covers
    only its NON-BRANCH staff — Head of Branches sits inside CCB's subtree, so
    counting branches again would double them.
    """
    from datetime import date as _date
    from utils.staff_code import canon as _canon_u

    me = _identity(user)
    my_code = str(me.get("staff_code", "") or "")
    try:
        day = _date.fromisoformat(str(date)[:10]) if date else _date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    iso = day.isoformat()

    try:
        from utils.org_validator import units_validated_by, branches_validated_by
        uscope = units_validated_by(my_code)
        bscope = branches_validated_by(my_code)
    except Exception:
        uscope = {"units": [], "owns": [], "top_of_house": False}
        bscope = {"branches": []}

    if not uscope.get("units") and not bscope.get("branches"):
        return {"branches": None, "units": [], "date": iso, "top_of_house": False}

    try:
        from utils import workcal as _wc
        if not _wc.is_working_day(day):
            return {"branches": None, "units": [], "date": iso,
                    "working_day": False, "label": _wc.holiday_label(day),
                    "top_of_house": bool(uscope.get("top_of_house"))}
    except Exception:
        pass

    dims = _roster_dims()
    blm = BranchLogManager()
    logs = [l for l in blm.get_history(days=45) if str(l.get("log_date"))[:10] == iso]
    filed_by = {}
    for l in logs:
        filed_by[_canon_u(l.get("staff_code"))] = l

    from utils.branch_day import list_branch_days

    # ── the collapsed BRANCHES node ──────────────────────────────────────────
    branch_names = sorted({str((d or {}).get("branch") or "").strip()
                           for d in dims.values()
                           if str((d or {}).get("branch") or "").strip()
                           and str((d or {}).get("branch") or "").strip().lower()
                           != "head office"})
    subs = list_branch_days(iso, branch_names)
    brows, tot = [], {"expected": 0, "filed": 0, "validated": 0, "index": 0.0,
                      "countersigned": 0, "over": 0}
    for b in branch_names:
        members = [(d.get("code") or ck, d) for ck, d in dims.items()
                   if str((d or {}).get("branch") or "").strip() == b]
        filed = sum(1 for c, _d in members if _canon_u(c) in filed_by)
        validated = sum(1 for c, _d in members
                        if (filed_by.get(_canon_u(c)) or {}).get("validated"))
        rec = subs.get(b) or {}
        over = 0
        try:
            from utils.branch_log_reconcile import reconcile_branch_day
            over = int((reconcile_branch_day(logs, b, iso) or {}).get("anomaly_count", 0))
        except Exception:
            over = 0
        row = {"key": b, "name": b, "kind": "branch",
               "expected": len(members), "filed": filed, "validated": validated,
               "not_filed": max(len(members) - filed, 0),
               "status": rec.get("status", "draft"),
               "index": rec.get("branch_index", 0),
               "owner": rec.get("validated_by_name", "") or rec.get("submitted_by_name", ""),
               "over_reported": over}
        brows.append(row)
        tot["expected"] += row["expected"]; tot["filed"] += row["filed"]
        tot["validated"] += row["validated"]; tot["index"] += float(row["index"] or 0)
        tot["over"] += over
        if row["status"] == "validated":
            tot["countersigned"] += 1

    branches_node = {
        "key": "__branches__", "name": "Branches", "kind": "rollup",
        "expected": tot["expected"], "filed": tot["filed"],
        "validated": tot["validated"],
        "not_filed": max(tot["expected"] - tot["filed"], 0),
        "index": round(tot["index"], 1),
        "count": len(brows), "countersigned": tot["countersigned"],
        "over_reported": tot["over"],
        "owner": "Head of Branches",
        "children": brows,
    } if brows else None

    # ── one row per Head Office unit ─────────────────────────────────────────
    urows = []
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
                   and str((d or {}).get("branch") or "").strip().lower() == "head office"]
        if not members:
            continue
        filed = sum(1 for c, _d in members if _canon_u(c) in filed_by)
        validated = sum(1 for c, _d in members
                        if (filed_by.get(_canon_u(c)) or {}).get("validated"))
        rec = list_branch_days(iso, [unit]).get(unit) or {}
        urows.append({
            "key": unit, "name": unit, "kind": "unit",
            "expected": len(members), "filed": filed, "validated": validated,
            "not_filed": max(len(members) - filed, 0),
            "status": rec.get("status", "draft"),
            "index": rec.get("branch_index", 0),
            "owner": rec.get("validated_by_name", "") or rec.get("submitted_by_name", ""),
            "over_reported": 0,
            "can_countersign": unit in (uscope.get("owns") or []),
        })
    urows.sort(key=lambda r: r["name"])

    return {"branches": branches_node, "units": urows, "date": iso,
            "working_day": True,
            "top_of_house": bool(uscope.get("top_of_house")),
            "can_return": bool(uscope.get("top_of_house")) or _is_admin(user)}


'''


def main():
    apply = "--apply" in sys.argv
    for p in (OV, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    ov = open(OV, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "md_reporting_roles" in ov:
        print("ABORT: org_validator already has md_reporting_roles - R1 looks applied.")
        return 1
    if "branches_validated_by" not in ov:
        print("ABORT: apply patch_b2_branch_day.py first.")
        return 1
    if "/unit-days" in api:
        print("ABORT: api_branch_log already has /unit-days.")
        return 1
    if ov.count(OV_ANCHOR) != 1:
        print("ABORT: org_validator anchor matched %d times." % ov.count(OV_ANCHOR))
        return 1
    if api.count(API_ANCHOR) != 1:
        print("ABORT: api anchor matched %d times." % api.count(API_ANCHOR))
        return 1

    ov = ov.replace(OV_ANCHOR, UNITS_NEW + OV_ANCHOR, 1)
    print("  ok  org_validator - md_reporting_roles / units_validated_by")

    api = api.replace(API_ANCHOR, ENDPOINT_NEW + API_ANCHOR, 1)
    print("  ok  api_branch_log - GET /unit-days")

    if api.count('@router.get("/unit-days")') != 1:
        print("ABORT: post-check - unit-days route count is not 1.")
        return 1
    if api.count('@router.get("/branch-days")') != 1:
        print("ABORT: post-check - branch-days route count changed.")
        return 1
    for token in ("md_reporting_roles", "top_of_house", "_is_top_of_house"):
        if token not in UNITS_NEW:
            print("ABORT: embedded block missing %r." % token)
            return 1
    print("  ok  post-checks: both routes present exactly once")

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

    print("")
    print("Check the units resolve from YOUR org_config:")
    print("  python -c \"import sys;sys.path.insert(0,'.');"
          "from utils.org_validator import md_reporting_roles as m;"
          "[print(' ',r) for r in m()]\"")
    print("Then restart uvicorn. R2 is the frontend tree.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
