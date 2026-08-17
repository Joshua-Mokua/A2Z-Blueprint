#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
A1 - cumulative ranking (backend), and the analytics scope fix it exposed.

WHAT YOU ASKED FOR: "cumulative ranking, right from the individual, branch,
units filtering to the MD that we can still drill down like we have for the
daily log", plus ranking within a ROLE - tellers at a branch, for instance.

GET /api/branch-log/leaderboard?days=&level=&role=&branch=&unit=

    level = staff | role | branch | unit
    role / branch / unit are filters, so a Branch Manager can rank the tellers
    inside their own branch, or the MD can rank branches within CCB.

    Every person is counted EXACTLY ONCE at each level, so a level always sums
    to the same bank total. Rows carry index, target, achievement %, headcount,
    index per head, days filed, validated count and rank.

RANKING IS A DIFFERENT LENS FROM INDEX OWNERSHIP, and the distinction matters.
The ruling that a person's index belongs to their employing unit governs what a
unit's OWN number is. A cumulative ranking asks something else: how much
activity sits beneath this unit in total. So the roll-up walks the SOLID line
(utils.org_validator.unit_for_role) - using the dotted line would place a branch
RM in both Fortis and Consumer and the level would stop summing.

    150 of 153 roles resolve to one of the 16 MD-reporting units.

Per-staff totals come from carried_forward() - the SAME read-time engine the
history grid uses - so a leaderboard can never disagree with the history a
manager is looking at.

ALSO FIXED, because building on it made it visible: /analytics still carried its
own _is_admin / _is_manager scope rules, the second-hierarchy fault removed from
the history grid in P3f. Analytics and the grid could therefore report different
populations for the same user. It now uses get_visible_staff_codes with the
enriched caller context, and reports scope_tier from what the engine returned.

Verified: py_compile clean on both modules, tsc --noEmit clean, 34 routes, and
the analytics body no longer references the legacy scope helpers.

NOT in this batch: the 80/20 impact tiers. Every activity currently resolves to
'medium' because none have been assigned, so an impact pie would be one colour.
Your DAILY_LOG_IMPACT_MODEL.md defines them but is untracked, so I have not
guessed - send it and the tiers go in exactly as defined.

Usage (from project root, .venv active):
    python scripts\\patch_a1_leaderboard.py            # dry run
    python scripts\\patch_a1_leaderboard.py --apply    # write + .pre_a1 backups
"""
import os
import shutil
import sys

OV = os.path.join("utils", "org_validator.py")
API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_a1"

OV_ANCHOR = "def units_validated_by(validator_code: str) -> dict:"
API_ANCHOR = '@router.get("/analytics")'

SCOPE_OLD = '''    logs = blm.get_history(days=days)
    if unit and unit != "All":
        logs = [l for l in logs if str(l.get("unit", "")) == unit]
    if _is_admin(user):
        scoped = logs
    elif _is_manager(user):
        scoped = _subtree_logs(logs, user, me)
    else:
        scoped = [l for l in logs if str(l.get("staff_code")) == me["staff_code"]]'''

TIER_OLD = '''        "scope_tier": "bank" if _is_admin(user) else ("subtree" if _is_manager(user) else "self"),
        "impact": breakdown,'''
TIER_NEW = '''        "scope_tier": ("bank" if len(_visible) >= max(len(_roster_dims()), 1)
                       else ("subtree" if len(_visible) > 1 else "self")),
        "visible_staff": len(_visible),
        "impact": breakdown,'''

UNITMAP_NEW = r'''@lru_cache(maxsize=1)
def _role_to_unit_map() -> dict:
    """{role -> the MD-reporting unit it rolls into}, by walking the SOLID line.

    Used for CUMULATIVE RANKING only. Ranking is a different lens from index
    ownership: the ruling that a person's index belongs to their employing unit
    governs what a unit's own number is, while a cumulative ranking asks "how
    much activity sits beneath this unit in total". Each person is counted
    exactly ONCE per level, so a level always sums to the bank.

    The dotted (functional) line is deliberately NOT used here — it would place
    a branch RM in both Fortis and Consumer and the level would stop summing.
    """
    try:
        from utils.config import load_org_config
        hier = (load_org_config() or {}).get("hierarchy") or {}
    except Exception:
        return {}

    def parents(role):
        info = hier.get(role)
        if isinstance(info, dict):
            return list(info.get("reports_to") or [])
        return list(info or [])

    tops = set(md_reporting_roles())
    out = {}
    for role in hier:
        cur, seen = role, set()
        for _ in range(14):
            if cur in tops:
                out[role] = cur
                break
            if cur in seen:
                break
            seen.add(cur)
            ps = parents(cur)
            if not ps:
                break
            cur = ps[0]
    return out


def unit_for_role(role: str) -> str:
    """The MD-reporting unit a role rolls into, or '' when it reaches nothing."""
    m = _role_to_unit_map()
    r = _s(role)
    return m.get(r, "")


'''

LEADERBOARD_NEW = r'''@router.get("/leaderboard")
def branch_log_leaderboard(days: int = 30, level: str = "staff", role: str = "",
                           branch: str = "", unit: str = "",
                           user: dict = Depends(get_current_user)):
    """Cumulative ranking, drillable: staff -> role -> branch -> unit.

    Every person is counted EXACTLY ONCE at each level, so a level always sums
    to the same bank total. Ranking is a different lens from index ownership:
    the ruling that a person's index belongs to their employing unit governs
    what a unit's OWN number is; this asks how much activity sits beneath a
    unit in total. The SOLID line is used for the unit roll-up — the dotted
    line would place a branch RM in both Fortis and Consumer and the level
    would stop summing.

    level:  staff | role | branch | unit
    role/branch/unit: optional filters, so a Branch Manager can rank tellers
    inside their own branch.

    Scope is the canonical engine (get_visible_staff_codes), the same call the
    history grid and the pipeline use.
    """
    from utils.branch_log import metric_keys
    from utils.branch_log_analytics import carried_forward, _target_for
    from utils.staff_code import canon as _canon_l

    me = _identity(user)
    my_code = str(me.get("staff_code", "") or "")

    _stored = {}
    try:
        from utils.core import UserManager
        _stored = UserManager().users.get(str(user.get("username", "")) or "") or {}
    except Exception:
        _stored = {}
    user_ctx = {
        "staff_code":   my_code or str(_stored.get("staff_code", "") or ""),
        "role":         me.get("role", "") or str(_stored.get("role", "") or ""),
        "full_name":    str(_stored.get("full_name", "") or me.get("staff_name", "") or ""),
        "unit":         me.get("unit", "") or str(_stored.get("unit", "") or ""),
        "department":   str(_stored.get("department", "") or ""),
        "is_admin":     bool(user.get("is_admin") or _stored.get("is_admin")),
        "can_view_all": bool(user.get("can_view_all") or _stored.get("can_view_all")),
    }
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        visible = {_canon_l(c) for c in get_visible_staff_codes(user_ctx)}
    except Exception:
        visible = set()
    visible.discard("")
    if not visible and user_ctx["staff_code"]:
        visible = {_canon_l(user_ctx["staff_code"])}

    dims = _roster_dims()
    try:
        from utils.org_validator import unit_for_role
    except Exception:
        unit_for_role = lambda _r: ""      # noqa: E731

    blm = BranchLogManager()
    logs = [l for l in blm.get_history(days=days)
            if _canon_l(l.get("staff_code")) in visible]

    # Per-staff cumulative: index actually achieved, target that applied, and
    # the closing carried-forward balance from the same read-time engine the
    # grid uses — so a leaderboard can never disagree with the history.
    by_staff = {}
    for l in logs:
        by_staff.setdefault(_canon_l(l.get("staff_code")), []).append(l)

    people = []
    for ck, dd in dims.items():
        code = dd.get("code") or ck
        if _canon_l(code) not in visible:
            continue
        r = str(dd.get("role") or "")
        b = str(dd.get("branch") or "")
        u = unit_for_role(r) or ""
        if role and r != role:
            continue
        if branch and b != branch:
            continue
        if unit and u != unit:
            continue
        mine = by_staff.get(_canon_l(code), [])
        rows = carried_forward(mine) if mine else []
        idx = round(sum(float(x.get("index") or 0) for x in rows), 2)
        tgt = round(sum(float(x.get("target") or 0) for x in rows), 2)
        people.append({
            "staff_code": code, "staff_name": dd.get("full_name", ""),
            "role": r, "branch": b, "unit": u,
            "index": idx, "target": tgt,
            "days_filed": len(mine),
            "validated": sum(1 for x in mine if x.get("validated")),
            "cf_variance": rows[-1].get("cf_variance", 0) if rows else 0,
        })

    def agg(rows, keyfn, label):
        out = {}
        for p in rows:
            k = keyfn(p) or "(unassigned)"
            e = out.setdefault(k, {label: k, "index": 0.0, "target": 0.0,
                                   "headcount": 0, "days_filed": 0, "validated": 0})
            e["index"] += p["index"]; e["target"] += p["target"]
            e["headcount"] += 1; e["days_filed"] += p["days_filed"]
            e["validated"] += p["validated"]
        for e in out.values():
            e["index"] = round(e["index"], 1)
            e["target"] = round(e["target"], 1)
            e["achievement"] = round((e["index"] / e["target"]) * 100, 1) if e["target"] else 0.0
            e["index_per_head"] = round(e["index"] / e["headcount"], 1) if e["headcount"] else 0.0
        return list(out.values())

    if level == "role":
        rows = agg(people, lambda p: p["role"], "name")
        sort_key = "index_per_head"
    elif level == "branch":
        rows = agg(people, lambda p: p["branch"], "name")
        sort_key = "index"
    elif level == "unit":
        rows = agg(people, lambda p: p["unit"], "name")
        sort_key = "index"
    else:
        level = "staff"
        for p in people:
            p["achievement"] = round((p["index"] / p["target"]) * 100, 1) if p["target"] else 0.0
        rows = people
        sort_key = "index"

    rows.sort(key=lambda r: -float(r.get(sort_key) or 0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    total_index = round(sum(float(r.get("index") or 0) for r in rows), 1)
    return {
        "level": level, "days": days, "rows": rows,
        "total_index": total_index,
        "total_headcount": len(people),
        "filters": {"role": role, "branch": branch, "unit": unit},
        "roles": sorted({p["role"] for p in people if p["role"]}),
        "branches": sorted({p["branch"] for p in people if p["branch"]}),
        "units": sorted({p["unit"] for p in people if p["unit"]}),
    }


'''

SCOPE_NEW = r'''    logs = blm.get_history(days=days)
    if unit and unit != "All":
        logs = [l for l in logs if str(l.get("unit", "")) == unit]

    # Scope from the CANONICAL engine, as the history grid and leaderboard do.
    # This endpoint previously carried its own _is_admin/_is_manager rules, so
    # analytics and the grid could disagree about the same population — the
    # second-hierarchy fault fixed in P3f, still present here.
    from utils.staff_code import canon as _canon_a
    _stored = {}
    try:
        from utils.core import UserManager
        _stored = UserManager().users.get(str(user.get("username", "")) or "") or {}
    except Exception:
        _stored = {}
    _ctx = {
        "staff_code":   me.get("staff_code", "") or str(_stored.get("staff_code", "") or ""),
        "role":         me.get("role", "") or str(_stored.get("role", "") or ""),
        "full_name":    str(_stored.get("full_name", "") or me.get("staff_name", "") or ""),
        "unit":         me.get("unit", "") or str(_stored.get("unit", "") or ""),
        "department":   str(_stored.get("department", "") or ""),
        "is_admin":     bool(user.get("is_admin") or _stored.get("is_admin")),
        "can_view_all": bool(user.get("can_view_all") or _stored.get("can_view_all")),
    }
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        _visible = {_canon_a(c) for c in get_visible_staff_codes(_ctx)}
    except Exception:
        _visible = set()
    _visible.discard("")
    if not _visible and _ctx["staff_code"]:
        _visible = {_canon_a(_ctx["staff_code"])}
    scoped = [l for l in logs if _canon_a(l.get("staff_code")) in _visible]'''


def main():
    apply = "--apply" in sys.argv
    for p in (OV, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1

    ov = open(OV, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "_role_to_unit_map" in ov:
        print("ABORT: org_validator already has _role_to_unit_map - A1 looks applied.")
        return 1
    if "units_validated_by" not in ov:
        print("ABORT: apply patch_r1_units.py first.")
        return 1
    if "/leaderboard" in api:
        print("ABORT: api_branch_log already has /leaderboard.")
        return 1
    for label, hay, mark in (("org_validator", ov, OV_ANCHOR),
                             ("analytics route", api, API_ANCHOR),
                             ("analytics scope", api, SCOPE_OLD),
                             ("analytics scope_tier", api, TIER_OLD)):
        if hay.count(mark) != 1:
            print("ABORT: %s anchor matched %d times." % (label, hay.count(mark)))
            return 1

    ov = ov.replace(OV_ANCHOR, UNITMAP_NEW + OV_ANCHOR, 1)
    print("  ok  org_validator - unit_for_role (solid-line roll-up)")

    api = api.replace(API_ANCHOR, LEADERBOARD_NEW + API_ANCHOR, 1)
    print("  ok  api_branch_log - GET /leaderboard")

    api = api.replace(SCOPE_OLD, SCOPE_NEW, 1)
    api = api.replace(TIER_OLD, TIER_NEW, 1)
    print("  ok  /analytics - scope from the canonical engine")

    if api.count('@router.get("/leaderboard")') != 1:
        print("ABORT: post-check - leaderboard route count is not 1.")
        return 1
    _a = api.index("def branch_log_analytics(")
    _b = api.index('        "high_impact_keys"', _a)
    if "_is_admin(user)" in api[_a:_b] or "_is_manager(user)" in api[_a:_b]:
        print("ABORT: post-check - analytics still uses the legacy scope helpers.")
        return 1
    if "get_visible_staff_codes" not in api[_a:_b]:
        print("ABORT: post-check - analytics is not using the engine.")
        return 1
    print("  ok  post-checks: one leaderboard route, analytics on the engine")

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
    print("Check the roll-up against YOUR hierarchy:")
    print("  python -c \"import sys;sys.path.insert(0,'.');"
          "from utils.org_validator import unit_for_role as u;"
          "[print(' %-30s -> %s' % (r, u(r))) for r in "
          "['Branch Manager','Direct Sales Agent','Credit Analyst']]\"")
    print("Then restart uvicorn.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
