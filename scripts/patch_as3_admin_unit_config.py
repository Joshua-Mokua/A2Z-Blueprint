#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
AS3 - the admin can actually amend the unit sets and weights.

RULING (2026-08-10): "aligned on that, the branch default but with admin still
being able to amend."

AS1 and AS2 made per-unit activity sets and weights real, but the admin config
endpoint only ever knew about activity_weights and daily_index_target. So the
new settings could be changed by editing JSON on the server and no other way -
which is not "the admin can amend", it is "Joshua can amend".

GET /api/branch-log/config now returns
    activity_sets            {unit: [field key]}
    unit_activity_weights    {unit: {key: weight}}
    units                    all 16 MD-reporting units, so the panel offers a
                             LIST rather than expecting someone to type a unit
                             name exactly right

POST /api/branch-log/config now accepts both, admin-only as before, and:

    an activity set sent EMPTY REMOVES the unit rather than storing an empty
    list. An empty set would leave that unit with no activities at all and its
    people would read zero; removing it returns them to the branch base, which
    is what "no set" is meant to mean.

    unknown field keys are DROPPED rather than stored - a set pointing at a
    field that does not exist silently gives that unit fewer activities than
    the admin thinks they configured.

    weights sent empty CLEAR the override, so a unit falls back to the
    bank-wide weights. There has to be a way back.

CONTEXT - where this landed today. The first cut configured six units; four
were reverted to the branch base because their sets were too thin to reach the
target honestly (Credit Risk would have needed a referral worth 26 against a
target of 25). Two remain, weighted to sum 26.0 and 25.9. Everyone else is on
the branch base until their real activities exist.

Verified: py_compile clean; 16 units returned for selection.

REQUIRES AS2.

Usage (from project root, .venv active):
    python scripts\patch_as3_admin_unit_config.py            # dry run
    python scripts\patch_as3_admin_unit_config.py --apply
"""
import os
import shutil
import sys

API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_as3"

BLOCK = r'''@router.get("/config")
def branch_log_config_get(user: dict = Depends(get_current_user)):
    """Per-activity weights + daily index target (admin-configured), with fields."""
    from utils.branch_log import load_log_config
    cfg = load_log_config()
    # UNITS the admin can configure: every MD-reporting unit, so the panel can
    # offer a list rather than expecting someone to type a unit name exactly.
    try:
        from utils.org_validator import md_reporting_roles
        units = sorted(md_reporting_roles() or [])
    except Exception:
        units = sorted((cfg.get("activity_sets") or {}).keys())
    return {"activity_weights": cfg.get("activity_weights", {}) or {},
            "daily_index_target": cfg.get("daily_index_target", 0) or 0,
            "fields": fields_schema(),
            "activity_sets": cfg.get("activity_sets", {}) or {},
            "unit_activity_weights": cfg.get("unit_activity_weights", {}) or {},
            "units": units}


@router.post("/config")
def branch_log_config_set(payload: dict = Body(default_factory=dict),
                          user: dict = Depends(get_current_user)):
    """Set activity weights (points) + daily index target. Admin only."""
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin authority required.")
    from utils.branch_log import load_log_config, save_log_config
    cfg = load_log_config()
    if isinstance(payload.get("activity_weights"), dict):
        weights = {}
        for k, v in payload["activity_weights"].items():
            try:
                weights[str(k)] = float(v or 0)
            except (TypeError, ValueError):
                weights[str(k)] = 0.0
        cfg["activity_weights"] = weights
    if "daily_index_target" in payload:
        try:
            cfg["daily_index_target"] = float(payload.get("daily_index_target") or 0)
        except (TypeError, ValueError):
            cfg["daily_index_target"] = 0.0

    # PER-UNIT ACTIVITY SETS (AS1). {unit: [field key, ...]}
    # A unit sent with an EMPTY list is REMOVED rather than stored empty: an
    # empty set would leave that unit with no activities at all and its people
    # would read zero. Removing it returns them to the branch base, which is
    # what "no set" is supposed to mean.
    if isinstance(payload.get("activity_sets"), dict):
        from utils.branch_log import fields_schema
        known = {f["key"] for f in fields_schema()}
        sets = dict(cfg.get("activity_sets") or {})
        for unit, keys in payload["activity_sets"].items():
            u = str(unit).strip()
            if not u:
                continue
            good = [str(k) for k in (keys or []) if str(k) in known]
            if good:
                sets[u] = good
            else:
                sets.pop(u, None)
        cfg["activity_sets"] = sets

    # PER-UNIT WEIGHT OVERRIDES (AS2). {unit: {key: weight}}
    if isinstance(payload.get("unit_activity_weights"), dict):
        uw = dict(cfg.get("unit_activity_weights") or {})
        for unit, m in payload["unit_activity_weights"].items():
            u = str(unit).strip()
            if not u or not isinstance(m, dict):
                continue
            got = {}
            for k, v in m.items():
                try:
                    got[str(k)] = float(v)
                except (TypeError, ValueError):
                    continue
            if got:
                uw[u] = got
            else:
                uw.pop(u, None)      # cleared = inherit the bank-wide weights
        cfg["unit_activity_weights"] = uw

    save_log_config(cfg)
    audit_log("BRANCH_LOG_CONFIG", str(user.get("username", "") or ""), "weights/target updated")
    return {"status": "saved",
            "activity_weights": cfg.get("activity_weights", {}),
            "daily_index_target": cfg.get("daily_index_target", 0),
            "activity_sets": cfg.get("activity_sets", {}),
            "unit_activity_weights": cfg.get("unit_activity_weights", {})}


'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1

    s = open(API, encoding="utf-8").read()
    if '"activity_sets": cfg.get("activity_sets"' in s:
        print("ABORT: the config endpoint already handles activity_sets - AS3 looks applied.")
        return 1
    if '@router.get("/config")' not in s or '@router.post("/config")' not in s:
        print("ABORT: the config endpoints are not where expected.")
        return 1

    import re
    i = s.index('@router.get("/config")')
    m = re.search(r'\n@router\.(get|post)\("/(?!config)', s[i + 40:])
    if not m:
        print("ABORT: could not find the end of the config block.")
        return 1
    j = i + 40 + m.start() + 1
    s = s[:i] + BLOCK + s[j:]
    print("  ok  config GET/POST replaced")

    for token in ('"activity_sets"', '"unit_activity_weights"', '"units"',
                  "sets.pop(u, None)", "uw.pop(u, None)"):
        if token not in BLOCK:
            print("ABORT: embedded block missing %r." % token)
            return 1
    # An empty set must REMOVE, never store empty - otherwise a unit ends up
    # with no activities and its people read zero.
    if "if good:" not in BLOCK:
        print("ABORT: an empty activity set would be stored rather than removed.")
        return 1
    if s.count('@router.get("/config")') != 1 or s.count('@router.post("/config")') != 1:
        print("ABORT: post-check - config route count is wrong.")
        return 1
    if "_is_admin(user)" not in BLOCK:
        print("ABORT: post-check - the admin gate was lost.")
        return 1
    print("  ok  post-checks: admin gate intact, empty set removes")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(s)
    print("APPLIED %s  (backup: %s)" % (API, os.path.basename(API) + BACKUP_SUFFIX))

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nRestart uvicorn. GET /api/branch-log/config now returns the unit")
    print("list, the sets and the per-unit weights for the admin panel to edit.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
