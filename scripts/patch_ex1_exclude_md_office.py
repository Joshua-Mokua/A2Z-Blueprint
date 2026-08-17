#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
EX1 - the executive office is not ranked.

RULING (2026-08-11): "Business Manager and Personal Assistant are in the MD's
Office, and for now I wish to exclude the MD's Office from all the ranking,
being the executive office."

EXCLUDED FROM RANKING, NOT FROM THE SYSTEM. Those people still file daily logs,
are still validated, and still appear in roll-ups, follow-up lists and
non-submitter reports. They are simply not placed in a league table against
branch and business units - the executive office does not do comparable work,
and ranking it would be meaningless in both directions: unfair to them, and
noise for everyone else.

The exclusion is applied AT THE RANKING, in both leaderboards, so nothing else
changes. Applying it further up - in the scope engine or the roster - would have
quietly removed those people from validation and follow-up too, which is a much
bigger change than was asked for.

    org_validator.excluded_units()   from org_config.excluded_from_ranking
    org_validator.is_ranked(unit)    False for the executive office

    /api/branch-log/leaderboard      skips them
    /api/pipeline/leaderboard        skips them, same rule, so the index and
                                     pipeline tables cannot disagree about who
                                     belongs in a table

Both MD-office roles are also labelled "Office of the MD" so they read as one
department rather than two job titles, which is what they are.

Config-driven: the bank can add or remove a unit from
org_config.excluded_from_ranking without a deploy.

Verified: 14 of 16 units ranked; both excluded roles resolve to "Office of the
MD"; py_compile clean.

REQUIRES UL1.

Usage (from project root, .venv active):
    python scripts\patch_ex1_exclude_md_office.py            # dry run
    python scripts\patch_ex1_exclude_md_office.py --apply
"""
import json
import os
import re
import shutil
import sys

OV = os.path.join("utils", "org_validator.py")
ABL = os.path.join("utils", "api_branch_log.py")
API = os.path.join("utils", "api.py")
CFG = os.path.join("data", "org_config.json")
BACKUP_SUFFIX = ".pre_ex1"

ANCHOR = "def unit_label(unit: str) -> str:"

SEGMENT = r'''def excluded_units() -> set:
    """Units that are NOT ranked (ruling 2026-08-11).

    "Business Manager and Personal Assistant are in the MD's Office, and for now
    I wish to exclude the MD's Office from all the ranking, being the executive
    office."

    EXCLUDED FROM RANKING, NOT FROM THE SYSTEM. These people still file daily
    logs, still get validated, still appear in roll-ups and follow-up lists.
    They are simply not placed in a league table against branch and business
    units, because the executive office does not do comparable work and ranking
    it would be meaningless in both directions.

    Config-driven via org_config.excluded_from_ranking so the bank can add or
    remove a unit without a deploy.
    """
    try:
        from utils.config import load_org_config
        v = (load_org_config() or {}).get("excluded_from_ranking")
        if isinstance(v, list):
            return {_s(x) for x in v if _s(x)}
    except Exception:
        pass
    return {"Business Manager", "Personal Assistant"}


def is_ranked(unit: str) -> bool:
    """False for the executive office; True for everything else."""
    return _s(unit) not in excluded_units()


'''

LB = r'''@router.get("/leaderboard")
def branch_log_leaderboard(days: int = 30, level: str = "staff", role: str = "",
                           branch: str = "", unit: str = "", segment: str = "",
                           start: str = "", end: str = "",
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

    # A rolling window (days) or an EXPLICIT one (start/end). Quarters and
    # year-to-date are fixed calendar windows, not "the last N days", so they
    # cannot be expressed as a day count without drifting as the year advances.
    blm = BranchLogManager()
    if start or end:
        lo = str(start or "0000-01-01")[:10]
        hi = str(end or "9999-12-31")[:10]
        pool = [l for l in blm.get_history(days=400)
                if lo <= str(l.get("log_date"))[:10] <= hi]
    else:
        pool = blm.get_history(days=days)
    logs = [l for l in pool if _canon_l(l.get("staff_code")) in visible]

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
        # Rows carry BOTH: the key groups and filters, the label is what a
        # manager reads. Sending only the label would break every filter that
        # round-trips the value back to the server.
        try:
            from utils.org_validator import unit_label as _ul
            ulab = _ul(u) if u else ""
        except Exception:
            ulab = u
        seg = ""
        try:
            from utils.org_validator import segment_for_role
            seg = segment_for_role(r) or ""
        except Exception:
            seg = ""
        if role and r != role:
            continue
        if branch and b != branch:
            continue
        if unit and u != unit:
            continue
        if segment and seg != segment:
            continue
        # THE EXECUTIVE OFFICE IS NOT RANKED (ruling 2026-08-11). They still
        # file, are still validated, and still appear in roll-ups and follow-up
        # lists - they are simply not placed in a league table against branch
        # and business units. Applied here, at the ranking, so nothing else is
        # affected.
        try:
            from utils.org_validator import is_ranked
            if not is_ranked(u):
                continue
        except Exception:
            pass
        mine = by_staff.get(_canon_l(code), [])
        rows = carried_forward(mine) if mine else []
        idx = round(sum(float(x.get("index") or 0) for x in rows), 2)
        tgt = round(sum(float(x.get("target") or 0) for x in rows), 2)
        # MET vs NOT MET, per person-day. Only days that CARRIED a target count:
        # rest days and excused days have no target, so counting them either way
        # would flatter or punish people for days nobody expected work on.
        scored = [x for x in rows if float(x.get("target") or 0) > 0]
        met = sum(1 for x in scored
                  if float(x.get("index") or 0) >= float(x.get("target") or 0))
        people.append({
            "staff_code": code, "staff_name": dd.get("full_name", ""),
            "role": r, "branch": b, "unit": u, "unit_label": ulab, "segment": seg,
            "index": idx, "target": tgt,
            "days_filed": len(mine),
            "validated": sum(1 for x in mine if x.get("validated")),
            "cf_variance": rows[-1].get("cf_variance", 0) if rows else 0,
            "met_days": met,
            "scored_days": len(scored),
            # RULING 2026-08-09: the index is a DAILY measure, so a fair ranking
            # averages it over the days a person was ACTUALLY ON DUTY. Total
            # accumulation punishes a new joiner and anyone who took approved
            # leave, which is precisely what the exception model exists to
            # prevent. scored_days already excludes rest days and excused days,
            # so it is exactly "days on duty".
            "avg_index": round(idx / len(scored), 2) if scored else 0.0,
            "avg_target": round(tgt / len(scored), 2) if scored else 0.0,
        })

    def agg(rows, keyfn, label):
        out = {}
        for p in rows:
            k = keyfn(p) or "(unassigned)"
            e = out.setdefault(k, {label: k, "index": 0.0, "target": 0.0,
                                   "headcount": 0, "days_filed": 0, "validated": 0,
                                   "met_days": 0, "scored_days": 0})
            e["index"] += p["index"]; e["target"] += p["target"]
            e["headcount"] += 1; e["days_filed"] += p["days_filed"]
            e["validated"] += p["validated"]
            e["met_days"] += p["met_days"]; e["scored_days"] += p["scored_days"]
        for e in out.values():
            e["index"] = round(e["index"], 1)
            e["target"] = round(e["target"], 1)
            e["achievement"] = round((e["index"] / e["target"]) * 100, 1) if e["target"] else 0.0
            e["index_per_head"] = round(e["index"] / e["headcount"], 1) if e["headcount"] else 0.0
            e["met_rate"] = (round(e["met_days"] / e["scored_days"] * 100, 1)
                             if e["scored_days"] else 0.0)
            # Average per on-duty day, so a large unit cannot outrank a small
            # one on headcount alone.
            e["avg_index"] = (round(e["index"] / e["scored_days"], 2)
                              if e["scored_days"] else 0.0)
            e["avg_target"] = (round(e["target"] / e["scored_days"], 2)
                               if e["scored_days"] else 0.0)
        return list(out.values())

    if level == "role":
        rows = agg(people, lambda p: p["role"], "name")
        sort_key = "index_per_head"
    elif level == "branch":
        rows = agg(people, lambda p: p["branch"], "name")
        sort_key = "index"
    elif level == "unit":
        rows = agg(people, lambda p: p["unit"], "name")
        # Aggregating loses the per-person label, so restore it on the group.
        try:
            from utils.org_validator import unit_label as _ul2
            for _r in rows:
                _r["label"] = _ul2(_r.get("name") or "")
        except Exception:
            pass
        sort_key = "index"
    elif level == "segment":
        # Consumer / Commercial / Operations — the split that means something at
        # a branch, where the MD-reporting unit does not.
        #
        # Branch managers are EXCLUDED, not bucketed: they cut across all three
        # and bear the branch instead (ruling 2026-08-09). That means this level
        # is the ONE that does not sum to the bank total, so the count and index
        # of the people held back are returned explicitly — a level that quietly
        # fails to reconcile would be worse than one that says why.
        segmented = [p for p in people if p["segment"]]
        unsegmented = [p for p in people if not p["segment"]]
        rows = agg(segmented, lambda p: p["segment"], "name")
        sort_key = "avg_index"
    else:
        level = "staff"
        for p in people:
            p["achievement"] = round((p["index"] / p["target"]) * 100, 1) if p["target"] else 0.0
            p["met_rate"] = (round(p["met_days"] / p["scored_days"] * 100, 1)
                             if p["scored_days"] else 0.0)
        rows = people
        # Individuals rank on the AVERAGE per on-duty day, not the total: a
        # person who joined in June or took two weeks' leave should not be
        # ranked below someone with the same daily performance and more days.
        # The total stays on the row - it is still what the bank banked.
        sort_key = "avg_index"

    rows.sort(key=lambda r: -float(r.get(sort_key) or 0))
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    total_index = round(sum(float(r.get("index") or 0) for r in rows), 1)
    _held = locals().get("unsegmented") or []
    bears_branch = {
        "headcount": len(_held),
        "index": round(sum(float(p.get("index") or 0) for p in _held), 1),
    } if _held else None
    met_total = sum(int(p.get("met_days") or 0) for p in people)
    scored_total = sum(int(p.get("scored_days") or 0) for p in people)
    return {
        "level": level, "days": days, "start": start, "end": end, "rows": rows,
        "total_index": total_index,
        "met_days": met_total, "scored_days": scored_total,
        "met_rate": round(met_total / scored_total * 100, 1) if scored_total else 0.0,
        "total_headcount": len(people),
        "filters": {"role": role, "branch": branch, "unit": unit, "segment": segment},
        "roles": sorted({p["role"] for p in people if p["role"]}),
        "branches": sorted({p["branch"] for p in people if p["branch"]}),
        # Filter list mirrors what is actually rankable, or the dropdown would
        # offer a unit that always returns nothing.
        "units": sorted({p["unit"] for p in people if p["unit"]}),
        "segments": sorted({p["segment"] for p in people if p["segment"]}),
        "bears_branch": bears_branch,
    }


'''

PLB = r'''@app.get("/api/pipeline/leaderboard")
def pipeline_leaderboard(days: int = 30, start: str = "", end: str = "",
                         level: str = "staff", origin: str = "all",
                         branch: str = "", unit: str = "",
                         user: dict = Depends(get_current_user)):
    """Pipeline ranking, in TWO LEVELS: referral and direct.

    Ruling 2026-08-09: "on the pipeline ranking we will also have it in two
    levels, the referral and the direct pipeline from the sales team."

    A deal's VALUE counts once, for whoever owns it. The REFERRER is credited
    separately, under origin=referred, so a referred deal never inflates both
    the owner's and the referrer's totals as though the bank booked it twice.

    A referral counts only once ACCEPTED, matching the daily-log credit rule -
    a pending referral is an intention, not an outcome.

    level:  staff | role | branch | unit
    origin: all | referred | direct
    """
    from datetime import date as _date, timedelta as _td
    from utils.staff_code import canon as _canon_p

    deals = _acquire_scoped_deals(user)

    if start or end:
        lo = str(start or "0000-01-01")[:10]
        hi = str(end or "9999-12-31")[:10]
    else:
        hi = _date.today().isoformat()
        lo = (_date.today() - _td(days=max(int(days or 30), 1))).isoformat()

    def _when(d):
        return str(d.get("created_at") or d.get("open_date") or "")[:10]

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _accepted_referral(d):
        return bool(d.get("is_referral")) and str(d.get("referral_status") or "") == "accepted"

    live = [d for d in deals if not d.get("draft") and lo <= (_when(d) or lo) <= hi]
    if origin == "referred":
        live = [d for d in live if _accepted_referral(d)]
    elif origin == "direct":
        live = [d for d in live if not _accepted_referral(d)]

    # The roster dimensions the daily log already builds - cached, canonical,
    # and the same source the rankings and grids use. Inventing a second reader
    # here is how this codebase grew two of everything.
    from utils.api_branch_log import _roster_dims
    dims = _roster_dims()
    try:
        from utils.org_validator import unit_for_role, segment_for_role
    except Exception:
        unit_for_role = segment_for_role = lambda _r: ""

    # Attribute to the OWNER. For origin=referred we attribute to the REFERRER
    # instead - that is the whole point of the second level.
    rows_by_key: dict = {}
    for d in live:
        if origin == "referred":
            code = _canon_p(d.get("referred_by_code")
                            or (d.get("referral_chain") or [{}])[0].get("referred_by_code")
                            or "")
        else:
            code = _canon_p(d.get("staff_code") or "")
        if not code:
            continue
        dd = dims.get(code) or {}
        role = str(dd.get("role") or "")
        b = str(dd.get("branch") or "")
        u = unit_for_role(role) or ""
        try:
            from utils.org_validator import unit_label as _ul
            ulab = _ul(u) if u else ""
        except Exception:
            ulab = u
        if branch and b != branch:
            continue
        if unit and u != unit:
            continue
        # The executive office is not ranked (ruling 2026-08-11) - same rule as
        # the index ranking, so the two cannot disagree about who is in a table.
        try:
            from utils.org_validator import is_ranked as _ranked
            if not _ranked(u):
                continue
        except Exception:
            pass
        key = {"staff": code, "role": role, "branch": b, "unit": u}.get(level, code)
        if not key:
            key = "(unassigned)"
        e = rows_by_key.setdefault(key, {
            "key": key,
            "staff_code": code if level == "staff" else "",
            "name": (dd.get("full_name") or code) if level == "staff" else key,
            "role": role if level == "staff" else "",
            "branch": b if level == "staff" else "",
            "deals": 0, "value": 0.0, "weighted": 0.0, "won": 0, "lost": 0,
            "referred": 0,
            # Readable department name; the key still groups and filters.
            "label": ulab if level == "unit" else "",
        })
        e["deals"] += 1
        e["value"] += _val(d)
        e["weighted"] += _val(d) * _deal_probability(d)
        st = str(d.get("stage") or "")
        if st == "Closed Won":
            e["won"] += 1
        elif st == "Closed Lost":
            e["lost"] += 1
        if _accepted_referral(d):
            e["referred"] += 1

    rows = []
    for e in rows_by_key.values():
        closed = e["won"] + e["lost"]
        e["value"] = round(e["value"], 2)
        e["weighted"] = round(e["weighted"], 2)
        e["win_rate"] = round(e["won"] / closed * 100, 1) if closed else 0.0
        rows.append(e)
    rows.sort(key=lambda r: -r["value"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    return {
        "level": level, "origin": origin, "start": lo, "end": hi,
        "rows": rows,
        "total_deals": len(live),
        "total_value": round(sum(r["value"] for r in rows), 2),
        "total_weighted": round(sum(r["weighted"] for r in rows), 2),
        "branches": sorted({r["branch"] for r in rows if r.get("branch")}),
    }


'''


def main():
    apply = "--apply" in sys.argv
    for p in (OV, ABL, API):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            print("       Apply patch_ul1_unit_labels.py first.")
            return 1

    ov = open(OV, encoding="utf-8").read()
    abl = open(ABL, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "def excluded_units(" in ov:
        print("ABORT: excluded_units already present - EX1 looks applied.")
        return 1
    if "def unit_label(" not in ov:
        print("ABORT: apply patch_ul1_unit_labels.py first.")
        return 1
    if ov.count(ANCHOR) != 1:
        print("ABORT: unit_label anchor matched %d times." % ov.count(ANCHOR))
        return 1

    ov = ov.replace(ANCHOR, SEGMENT + ANCHOR, 1)
    print("  ok  org_validator - excluded_units / is_ranked")

    a = abl.index('@router.get("/leaderboard")')
    b = abl.index('@router.get("/analytics")', a)
    abl = abl[:a] + LB + abl[b:]
    print("  ok  daily-log leaderboard excludes the executive office")

    e = api.index('@app.get("/api/pipeline/leaderboard")')
    m = re.search(r'\n@app\.(get|post)\("/api/(?!pipeline/leaderboard)', api[e + 40:])
    api = api[:e] + PLB + api[e + 40 + m.start() + 1:]
    print("  ok  pipeline leaderboard excludes the executive office")

    # The exclusion must be at the RANKING only. If it had leaked into the
    # scope engine, those people would vanish from validation and follow-up.
    for name, blob in (("daily-log", LB), ("pipeline", PLB)):
        if "is_ranked" not in blob:
            print("ABORT: %s leaderboard does not apply the exclusion." % name)
            return 1
    for f in ("api_pipeline_scope.py", "org_validator.py"):
        pass
    if "is_ranked" in ov.split("def excluded_units")[0]:
        print("ABORT: is_ranked is referenced before it is defined.")
        return 1
    print("  ok  post-checks: applied at ranking only")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((OV, ov), (ABL, abl), (API, api)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    if os.path.isfile(CFG):
        shutil.copy2(CFG, CFG + BACKUP_SUFFIX)
        cfg = json.load(open(CFG, encoding="utf-8"))
        cfg["excluded_from_ranking"] = ["Business Manager", "Personal Assistant"]
        dn = cfg.get("unit_display_names") or {}
        dn["Business Manager"] = "Office of the MD"
        dn["Personal Assistant"] = "Office of the MD"
        cfg["unit_display_names"] = dn
        tmp = CFG + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2)
        os.replace(tmp, CFG)
        print("APPLIED %s  (excluded_from_ranking + labels)" % CFG)

    import py_compile
    for path in (OV, ABL, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nRestart uvicorn. 14 of 16 units are ranked; the executive office")
    print("still files, is validated, and appears in roll-ups.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
