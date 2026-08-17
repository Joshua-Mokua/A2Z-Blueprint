#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
UL1 - a unit is a department, not a job title.

PILOT OBSERVATION (2026-08-10): "instead of selecting the unit, e.g Internal
Audit, it instead selects Director, Internal Audit which is the title of the
Unit Director. I saw this also in the ranking and another place."

Correct, and it was in FOUR places, not two. The root is that unit_for_role()
returns the MD-reporting ROLE TITLE, and we used that as the unit's name
everywhere:

    Daily Log Admin       the unit picker
    Ranking               the Units level and the unit filter
    Index analytics       the by-unit chart - which had a local regex stripping
                          "Director," off the front, a hack that was the symptom
    Pipeline ranking      the Units level

THE KEY DOES NOT CHANGE. The role title is how the hierarchy identifies a unit
and it is already stored that way in activity_sets and unit_activity_weights on
the live pilot. Migrating keys would mean rewriting saved config for no gain.
So: KEY unchanged, LABEL derived and displayed.

    org_validator.unit_label(unit)   strips title prefixes and suffixes
    org_config.unit_display_names    explicit overrides where stripping is wrong

DERIVATION IS NOT ENOUGH ON ITS OWN, which is why the override map exists and is
seeded. Stripping alone produced:

    Business Manager             -> "Business"        (should be Business Management)
    Country Risk Manager, K&EAC  -> "Risk Manager..."  (suffix missed)
    Personal Assistant           -> unchanged          (not a department at all)
    Ag. Head HR & Senior HR BP   -> kept the whole tail

Nine overrides are seeded in org_config; the bank can correct any of them
without a deploy. unit_label NEVER returns empty - if stripping leaves nothing
the original stands, because a row with no name is unreadable.

WHAT TRAVELS. Rows and aggregates now carry BOTH: `name`/`unit` remains the key
so every filter that round-trips a value to the server still works, and `label`
is what a person reads. Sending only the label would have broken filtering
silently.

Verified: all 16 units read as departments; py_compile clean; tsc --noEmit
clean; vite build clean; no title-stripping hacks remain in the frontend.

Usage (from project root, .venv active):
    python scripts\patch_ul1_unit_labels.py            # dry run
    python scripts\patch_ul1_unit_labels.py --apply
"""
import os
import re
import shutil
import sys

OV = os.path.join("utils", "org_validator.py")
ABL = os.path.join("utils", "api_branch_log.py")
API = os.path.join("utils", "api.py")
LEAD = os.path.join("frontend", "web", "src", "components", "Leaderboard.tsx")
PLEAD = os.path.join("frontend", "web", "src", "components", "PipelineLeaderboard.tsx")
ANAL = os.path.join("frontend", "web", "src", "components", "DailyLogAnalytics.tsx")
ADMIN = os.path.join("frontend", "web", "src", "pages", "DailyLogAdmin.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
BACKUP_SUFFIX = ".pre_ul1"

TS_EDITS = [
    ("  segment?: string;\n  avg_index?: number; avg_target?: number;   // per ON-DUTY day",
     "  segment?: string;\n  label?: string;            // readable department name; `name` stays the key\n  avg_index?: number; avg_target?: number;   // per ON-DUTY day"),
    ("  roles: string[]; branches: string[]; units: string[]; segments?: string[];",
     "  roles: string[]; branches: string[]; units: string[]; segments?: string[];\n  unit_labels?: Record<string, string>;"),
    ("  units?: string[];\n}",
     "  units?: string[];\n  unit_labels?: Record<string, string>;\n}"),
    ("  deals: number; value: number; weighted: number;\n  won: number; lost: number; referred: number; win_rate: number;",
     "  deals: number; value: number; weighted: number;\n  won: number; lost: number; referred: number; win_rate: number;\n  label?: string;"),
]

SEGMENT = r'''# ── UNIT DISPLAY NAMES (2026-08-11) ─────────────────────────────────────────
# A unit's KEY is the MD-reporting ROLE TITLE - that is how the hierarchy
# identifies it, and it is already stored that way in activity_sets,
# unit_activity_weights and every saved config. Changing the key would mean
# migrating live pilot config, so the key stays.
#
# But a title is not a department. "Director, Internal Audit" is a person's
# designation; the unit is "Internal Audit". Showing the title made the admin
# picker, the ranking and the analytics all read as though you were selecting a
# person rather than a department.
#
# So: KEY unchanged, LABEL derived. Config-driven via org_config.unit_display_names
# so the bank can correct any of the sixteen without a deploy.
_TITLE_PREFIXES = (
    "ag. head of ", "ag. head ", "acting head of ", "acting head ",
    "chief ", "director of ", "director, ", "director ",
    "head of ", "head ", "country ", "general manager, ", "general manager ",
)
_TITLE_SUFFIXES = (
    " officer", " manager", " & company secretary",
)


def unit_display_names() -> dict:
    """Explicit overrides from org_config. Anything absent is derived."""
    try:
        from utils.config import load_org_config
        v = (load_org_config() or {}).get("unit_display_names")
        if isinstance(v, dict):
            return {str(k): str(x) for k, x in v.items() if str(x).strip()}
    except Exception:
        pass
    return {}


def unit_label(unit: str) -> str:
    """What a human should read for this unit.

    Never returns empty: if stripping leaves nothing - "Business Manager",
    "Personal Assistant" - the original stands. A blank unit label would be
    worse than a slightly odd one, because a row with no name is unreadable.
    """
    raw = _s(unit)
    if not raw:
        return ""
    over = unit_display_names()
    if raw in over:
        return over[raw]

    low = raw.lower()
    out = raw
    for pre in _TITLE_PREFIXES:
        if low.startswith(pre):
            out = raw[len(pre):]
            break
    low2 = out.lower()
    for suf in _TITLE_SUFFIXES:
        if low2.endswith(suf) and len(out) > len(suf) + 2:
            out = out[: -len(suf)]
            break
    out = out.strip(" ,-")
    return out or raw


'''

CFG = r'''@router.get("/config")
def branch_log_config_get(user: dict = Depends(get_current_user)):
    """Per-activity weights + daily index target (admin-configured), with fields."""
    from utils.branch_log import load_log_config
    cfg = load_log_config()
    # UNITS the admin can configure: every MD-reporting unit, so the panel can
    # offer a list rather than expecting someone to type a unit name exactly.
    try:
        from utils.org_validator import md_reporting_roles
        # The KEY stays the role title (it is what every stored config uses);
        # the panel shows a readable department name alongside it.
        from utils.org_validator import unit_label
        units = sorted(md_reporting_roles() or [])
        unit_labels = {u: unit_label(u) for u in units}
    except Exception:
        units = sorted((cfg.get("activity_sets") or {}).keys())
    return {"activity_weights": cfg.get("activity_weights", {}) or {},
            "daily_index_target": cfg.get("daily_index_target", 0) or 0,
            "fields": fields_schema(),
            "activity_sets": cfg.get("activity_sets", {}) or {},
            "unit_activity_weights": cfg.get("unit_activity_weights", {}) or {},
            "units": units,
            "unit_labels": unit_labels}


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

LEADER = r'''// A2 — cumulative ranking, drillable: unit → branch → role → individual.
//
// Every person is counted exactly once at each level, so switching level never
// changes the bank total — only how it is partitioned. That is the property
// that makes a leaderboard trustworthy: if the totals moved when you changed
// the lens, nobody could tell which number was real.
//
// Filters compose downward. Pick a unit and the branch list narrows to that
// unit; pick a branch and the role list narrows to that branch. So "rank the
// tellers in Fortis" is two clicks, and "rank branches inside CCB" is one.
//
// Per-staff totals come from carried_forward() server-side — the same engine
// the history grid uses — so this can never disagree with the history.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import { fetchBranchLogLeaderboard, type Leaderboard, type LeaderboardRow } from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

type Level = 'unit' | 'segment' | 'branch' | 'role' | 'staff';

const LEVELS: { key: Level; label: string }[] = [
  { key: 'unit',    label: 'Units' },
  { key: 'segment', label: 'Segments' },
  { key: 'branch',  label: 'Branches' },
  { key: 'role',    label: 'Roles' },
  { key: 'staff',   label: 'Individuals' },
];

// Medal tint for the top three, brand palette only.
const MEDAL = ['bg-[#BED600] text-[#3B6D11]', 'bg-[#E6F1FB] text-[#0C447C]', 'bg-[#FAEEDA] text-[#854F0B]'];

function bar(pct: number): string {
  if (pct >= 100) return 'bg-[#669438]';
  if (pct >= 75) return 'bg-[#BED600]';
  if (pct >= 50) return 'bg-[#E0A02B]';
  return 'bg-[#C4536F]';
}

export default function Leaderboard() {
  const { toast } = useToast();
  const [level, setLevel] = useState<Level>('branch');
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [unit, setUnit] = useState('');
  const [branch, setBranch] = useState('');
  const [role, setRole] = useState('');
  const [data, setData] = useState<Leaderboard | null>(null);
  const [loading, setLoading] = useState(false);
  // Row expansion: clicking a unit/branch/role shows the individuals inside it,
  // fetched with that row as a filter — the same drill the daily log uses.
  const [openRow, setOpenRow] = useState('');
  const [drill, setDrill] = useState<LeaderboardRow[] | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);
  // Three met/not-met gauges: the selected period, the year so far, and
  // today. A single window answers 'how did we do'; the three together
  // answer 'and is it getting better', which is the question a manager
  // actually acts on.
  const [ytd, setYtd] = useState<Leaderboard | null>(null);
  const [today, setToday] = useState<Leaderboard | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchBranchLogLeaderboard({
        ...periodArgs(findPeriod(periodKey)), level, unit, branch, role,
      }));
      const now = new Date();
      const iso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
      try {
        setYtd(await fetchBranchLogLeaderboard({
          start: `${now.getFullYear()}-01-01`, end: iso, level, unit, branch, role,
        }));
      } catch { setYtd(null); }
      try {
        setToday(await fetchBranchLogLeaderboard({
          start: iso, end: iso, level, unit, branch, role,
        }));
      } catch { setToday(null); }
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the ranking.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, level, unit, branch, role, toast]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setOpenRow(''); setDrill(null); }, [level, periodKey, unit, branch, role]);

  async function expand(r: LeaderboardRow) {
    const key = String(r.name || r.staff_code || '');
    if (openRow === key) { setOpenRow(''); setDrill(null); return; }
    setOpenRow(key);
    setDrill(null);
    setDrillLoading(true);
    try {
      // Narrow by whichever dimension this row represents, then ask for people.
      const extra = level === 'unit' ? { unit: key }
        : level === 'branch' ? { branch: key }
        : { role: key };
      const r2 = await fetchBranchLogLeaderboard({
        ...periodArgs(findPeriod(periodKey)), level: 'staff', unit, branch, role, ...extra,
      });
      setDrill(r2.rows);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open that row.' });
      setOpenRow('');
    } finally {
      setDrillLoading(false);
    }
  }

  const rows = data?.rows ?? [];
  const max = useMemo(
    () => Math.max(1, ...rows.map((r) => Number(r.index) || 0)), [rows]);

  const isStaff = level === 'staff';
  // A unit's KEY is the MD-reporting role title, because that is what every
  // stored config uses; `label` is the department name a person should read.
  // Falls back to the key so a row is never blank.
  const nameOf = (r: LeaderboardRow) =>
    isStaff ? String(r.staff_name || r.staff_code || '')
            : String(r.label || r.name || '');

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Cumulative ranking</h2>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {LEVELS.map((l) => (
              <button key={l.key} type="button" onClick={() => setLevel(l.key)}
                className={'rounded-full px-3 py-1 font-medium transition-colors '
                  + (level === l.key ? 'bg-[#0082BB] text-white'
                                     : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                {l.label}
              </button>
            ))}
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="ml-2 rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {/* Filters compose downward: unit narrows branches, branch narrows roles. */}
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <select value={unit} onChange={(e) => { setUnit(e.target.value); setBranch(''); setRole(''); }}
                  className="max-w-[240px] rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="">All units</option>
            {(data?.units ?? []).map((u) => (
              <option key={u} value={u}>{data?.unit_labels?.[u] ?? u}</option>
            ))}
          </select>
          <select value={branch} onChange={(e) => { setBranch(e.target.value); setRole(''); }}
                  className="max-w-[180px] rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="">All branches</option>
            {(data?.branches ?? []).map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
          <select value={role} onChange={(e) => setRole(e.target.value)}
                  className="max-w-[240px] rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="">All roles</option>
            {(data?.roles ?? []).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          {(unit || branch || role) && (
            <button type="button"
                    onClick={() => { setUnit(''); setBranch(''); setRole(''); }}
                    className="rounded px-1.5 py-0.5 text-[11px] text-brand-primary hover:bg-[#0082BB]/10">
              Clear
            </button>
          )}
          {data && (
            <span className="ml-auto text-gray-500">
              {data.total_headcount} staff · total index{' '}
              <span className="font-semibold text-gray-800">{data.total_index.toLocaleString()}</span>
            </span>
          )}
        </div>

        {/* Met vs not met on the same scope as the table, across three windows.
            A person-day counts only if it carried a target, so rest days and
            excused days neither flatter nor punish. */}
        {!loading && (
          <div className="mb-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
            {([
              { key: 'sel', label: findPeriod(periodKey).label, d: data },
              { key: 'ytd', label: `Year to date`, d: ytd },
              { key: 'day', label: 'Today', d: today },
            ] as const).map(({ key, label, d }) => {
              const scored = d?.scored_days ?? 0;
              const met = d?.met_days ?? 0;
              return (
                <div key={key}
                     className="flex items-center gap-3 rounded-lg border border-gray-200 bg-gray-50/50 p-3">
                  <ResponsiveContainer width={78} height={78}>
                    <PieChart>
                      <Pie dataKey="value" innerRadius={22} outerRadius={36} paddingAngle={2}
                           data={scored
                             ? [{ name: 'Met', value: met },
                                { name: 'Not met', value: scored - met }]
                             : [{ name: 'No data', value: 1 }]}>
                        {scored
                          ? [<Cell key="m" fill="#669438" />, <Cell key="n" fill="#C4536F" />]
                          : [<Cell key="e" fill="#EDEDED" />]}
                      </Pie>
                      {scored ? <Tooltip formatter={(v: number) => [`${v} person-days`, '']} /> : null}
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="min-w-0 text-xs">
                    <div className="truncate text-[11px] font-medium text-gray-500" title={label}>
                      {label}
                    </div>
                    <div className="text-xl font-semibold text-[#3B6D11]">
                      {scored ? `${d?.met_rate ?? 0}%` : '—'}
                    </div>
                    <div className="text-[10px] text-gray-400">
                      {scored
                        ? `${met.toLocaleString()} met · ${(scored - met).toLocaleString()} missed`
                        : 'nothing carried a target'}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {loading && <p className="py-8 text-center text-sm text-gray-400">Ranking…</p>}

        {!loading && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            Nothing to rank for this period and filter.
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full table-fixed border-separate" style={{ borderSpacing: 0 }}>
              <colgroup>
                <col style={{ width: 44 }} />
                <col />
                {isStaff && <col style={{ width: '18%' }} />}
                {isStaff && <col style={{ width: '14%' }} />}
                {!isStaff && <col style={{ width: 72 }} />}
                <col style={{ width: 104 }} />
                <col style={{ width: 96 }} />
                <col style={{ width: 76 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 76 }} />
                {!isStaff && <col style={{ width: 84 }} />}
                <col style={{ width: 68 }} />
              </colgroup>
              <thead>
                <tr>
                  <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">#</th>
                  <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">
                    {isStaff ? 'Staff' : LEVELS.find((l) => l.key === level)?.label}
                  </th>
                  {isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Role</th>
                  )}
                  {isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Branch</th>
                  )}
                  {!isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Staff</th>
                  )}
                  <th className="bg-[#0082BB] px-2 py-2 text-right text-[11px] font-semibold uppercase text-white">Avg/day</th>
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Total index</th>
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">On duty</th>
                  <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Achievement</th>
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Met %</th>
                  {!isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Per head</th>
                  )}
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Filed</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const pct = Number(r.achievement) || 0;
                  const idx = Number(r.index) || 0;
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  const rowKey = String(r.name || r.staff_code || i);
                  const expanded = !isStaff && openRow === rowKey;
                  return (
                    <>
                    <tr key={rowKey}>
                      <td className={`${bg} px-2 py-1.5 text-xs`}>
                        <span className={'inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold '
                          + (r.rank && r.rank <= 3 ? MEDAL[r.rank - 1] : 'text-gray-400')}>
                          {r.rank}
                        </span>
                      </td>
                      <td className={`${bg} truncate px-2 py-1.5 text-xs font-medium text-gray-900`}
                          title={nameOf(r)}>
                        {isStaff ? nameOf(r) : (
                          <button type="button" onClick={() => void expand(r)}
                                  className="flex items-center gap-1.5 text-left hover:text-brand-primary">
                            <span className="text-gray-400">
                              {openRow === String(r.name || '') ? '▾' : '▸'}
                            </span>
                            {nameOf(r)}
                          </button>
                        )}
                      </td>
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.role}>
                          {r.role}
                        </td>
                      )}
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.branch}>
                          {r.branch}
                        </td>
                      )}
                      {!isStaff && (
                        <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                          {r.headcount}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs font-semibold tabular-nums`}>
                        <span className={(r.avg_index ?? 0) >= (r.avg_target ?? 0) && (r.avg_target ?? 0) > 0
                          ? 'text-[#3B6D11]' : 'text-gray-900'}>
                          {(r.avg_index ?? 0).toFixed(1)}
                        </span>
                        <span className="ml-1 text-[10px] font-normal text-gray-400">
                          {' / '}{(r.avg_target ?? 0).toFixed(0)}
                        </span>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-600`}>
                        {idx.toLocaleString()}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                        {r.scored_days ?? 0}
                      </td>
                      <td className={`${bg} px-2 py-1.5`}>
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-24 overflow-hidden rounded-full bg-gray-100">
                            <div className={`h-full ${bar(pct)}`}
                                 style={{ width: `${Math.min(Math.max(idx / max, 0), 1) * 100}%` }} />
                          </div>
                          <span className={'text-[11px] tabular-nums '
                            + (pct >= 100 ? 'text-[#3B6D11]' : pct >= 50 ? 'text-gray-600' : 'text-rose-600')}>
                            {pct}%
                          </span>
                        </div>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums`}>
                        <span className={(r.met_rate ?? 0) >= 60 ? 'text-[#3B6D11]'
                          : (r.met_rate ?? 0) >= 30 ? 'text-amber-600' : 'text-rose-600'}>
                          {r.met_rate ?? 0}%
                        </span>
                      </td>
                      {!isStaff && (
                        <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-700`}>
                          {r.index_per_head}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                        {r.days_filed}
                      </td>
                    </tr>
                    {expanded && (
                      <tr key={`${rowKey}-drill`}>
                        <td colSpan={10} className="bg-[#F7FBFD] px-6 py-3">
                          {drillLoading && (
                            <p className="text-xs text-gray-400">Opening {rowKey}…</p>
                          )}
                          {!drillLoading && drill && drill.length === 0 && (
                            <p className="text-xs text-gray-400">Nobody to show here.</p>
                          )}
                          {!drillLoading && drill && drill.length > 0 && (
                            <table className="w-full">
                              <thead>
                                <tr className="border-b border-gray-200">
                                  <th className="w-8 py-1 pr-2 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500">#</th>
                                  <th className="py-1 pr-3 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 80 }}>Staff</th>
                                  <th className="py-1 pr-3 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500">Name</th>
                                  <th className="py-1 pr-3 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500">Role</th>
                                  <th className="py-1 pr-3 text-left text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 110 }}>Segment</th>
                                  <th className="py-1 pr-3 text-right text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 90 }}>Avg/day</th>
                                  <th className="py-1 pr-3 text-right text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 90 }}>Total index</th>
                                  <th className="py-1 pr-3 text-right text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 70 }}>On duty</th>
                                  <th className="py-1 text-right text-[10px] font-semibold uppercase tracking-wide text-gray-500" style={{ width: 60 }}>Met %</th>
                                </tr>
                              </thead>
                              <tbody>
                                {drill.slice(0, 40).map((m) => (
                                  <tr key={m.staff_code} className="border-b border-gray-100 last:border-0">
                                    <td className="w-8 py-1 pr-2 text-[11px] tabular-nums text-gray-400">
                                      {m.rank}
                                    </td>
                                    <td className="py-1 pr-3 text-xs tabular-nums text-gray-500" style={{ width: 80 }}>
                                      {m.staff_code}
                                    </td>
                                    <td className="py-1 pr-3 text-xs text-gray-800">{m.staff_name}</td>
                                    <td className="truncate py-1 pr-3 text-xs text-gray-500" title={m.role}>
                                      {m.role}
                                    </td>
                                    <td className="py-1 pr-3 text-xs text-gray-500">
                                      {/* A branch manager bears the branch rather than sitting
                                          in a segment (ruling 2026-08-09), so they read as
                                          "Branch" instead of showing an empty cell. */}
                                      {m.segment
                                        ? m.segment
                                        : <span className="rounded bg-[#E6F1FB] px-1.5 py-0.5 text-[10px] text-[#0C447C]">Branch</span>}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs font-semibold tabular-nums"
                                        style={{ width: 90 }}>
                                      <span className={(m.avg_index ?? 0) >= (m.avg_target ?? 0) && (m.avg_target ?? 0) > 0
                                        ? 'text-[#3B6D11]' : 'text-gray-900'}>
                                        {(m.avg_index ?? 0).toFixed(1)}
                                      </span>
                                      <span className="ml-1 text-[10px] font-normal text-gray-400">
                                        / {(m.avg_target ?? 0).toFixed(0)}
                                      </span>
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-600"
                                        style={{ width: 90 }}>
                                      {Math.round(Number(m.index) || 0).toLocaleString()}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-500"
                                        style={{ width: 70 }}>
                                      {m.scored_days ?? 0}
                                    </td>
                                    <td className="py-1 text-right text-xs tabular-nums" style={{ width: 60 }}>
                                      <span className={(m.met_rate ?? 0) >= 60 ? 'text-[#3B6D11]'
                                        : (m.met_rate ?? 0) >= 30 ? 'text-amber-600' : 'text-rose-600'}>
                                        {m.met_rate ?? 0}%
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {!drillLoading && (drill?.length ?? 0) > 40 && (
                            <p className="mt-1 text-[11px] text-gray-400">
                              showing the top 40 of {drill?.length}
                            </p>
                          )}
                        </td>
                      </tr>
                    )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
'''

PLEADER = r'''// PipelineLeaderboard — pipeline ranking in two levels: referral and direct.
//
// A deal's value counts once, for whoever owns it. Under "Referred" the same
// deals are attributed to the REFERRER instead, so a referred deal is never
// counted twice as though the bank booked it twice — the two views answer
// different questions about the same book.

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineLeaderboard, type PipelineLeaderboard as Board,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

type Level = 'unit' | 'branch' | 'role' | 'staff';
type Origin = 'all' | 'direct' | 'referred';

const LEVELS: { key: Level; label: string }[] = [
  { key: 'unit', label: 'Units' },
  { key: 'branch', label: 'Branches' },
  { key: 'role', label: 'Roles' },
  { key: 'staff', label: 'Individuals' },
];

const ORIGINS: { key: Origin; label: string }[] = [
  { key: 'all', label: 'All deals' },
  { key: 'direct', label: 'Direct' },
  { key: 'referred', label: 'Referred' },
];

const MEDAL = ['bg-[#BED600] text-[#3B6D11]', 'bg-[#E6F1FB] text-[#0C447C]', 'bg-[#FAEEDA] text-[#854F0B]'];

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export default function PipelineLeaderboard() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [level, setLevel] = useState<Level>('branch');
  const [origin, setOrigin] = useState<Origin>('all');
  const [data, setData] = useState<Board | null>(null);
  const [loading, setLoading] = useState(false);
  // Drill: clicking a unit / branch / role opens the INDIVIDUALS INSIDE IT,
  // ranked against each other. Ruling 2026-08-09: an individual is ranked
  // within their unit, not against the whole bank — a teller in Fortis and an
  // RM in Corporate are not competing, and a flat bank-wide list of 363 people
  // says nothing a manager can act on. The consolidated view stays available
  // to the MD's office through the tree itself.
  const [openRow, setOpenRow] = useState('');
  const [drill, setDrill] = useState<Board['rows'] | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      setData(await fetchPipelineLeaderboard({ ...a, level, origin }));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the pipeline ranking.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, level, origin, toast]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setOpenRow(''); setDrill(null); }, [level, origin, periodKey]);

  async function expand(key: string) {
    if (openRow === key) { setOpenRow(''); setDrill(null); return; }
    setOpenRow(key);
    setDrill(null);
    setDrillLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      // Narrow by whichever dimension this row is, then ask for the people.
      const extra = level === 'unit' ? { unit: key }
        : level === 'branch' ? { branch: key }
        : {};
      const r = await fetchPipelineLeaderboard({
        ...a, level: 'staff', origin, ...extra,
      });
      setDrill(r.rows);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open that row.' });
      setOpenRow('');
    } finally {
      setDrillLoading(false);
    }
  }

  const rows = data?.rows ?? [];
  const isStaff = level === 'staff';
  const max = Math.max(1, ...rows.map((r) => r.value));

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-900">Pipeline ranking</h2>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {LEVELS.map((l) => (
              <button key={l.key} type="button" onClick={() => setLevel(l.key)}
                className={'rounded-full px-3 py-1 font-medium '
                  + (level === l.key ? 'bg-[#0082BB] text-white'
                                     : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                {l.label}
              </button>
            ))}
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="ml-2 rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex overflow-hidden rounded-lg border border-gray-200">
            {ORIGINS.map((o) => (
              <button key={o.key} type="button" onClick={() => setOrigin(o.key)}
                className={'px-3 py-1 font-medium '
                  + (origin === o.key ? 'bg-[#005B82] text-white'
                                      : 'bg-white text-gray-600 hover:bg-gray-50')}>
                {o.label}
              </button>
            ))}
          </span>
          {origin === 'referred' && (
            <span className="text-[11px] text-gray-500">credited to the referrer</span>
          )}
          {data && (
            <span className="ml-auto text-gray-500">
              {data.total_deals} deals · KES{' '}
              <span className="font-semibold text-gray-800">{kes(data.total_value)}</span>
              {' · '}KES {kes(data.total_weighted)} weighted
            </span>
          )}
        </div>

        {loading && <p className="py-8 text-center text-sm text-gray-400">Ranking…</p>}

        {!loading && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            {origin === 'referred'
              ? 'No accepted referrals in this period.'
              : 'Nothing to rank for this period.'}
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full table-fixed border-separate" style={{ borderSpacing: 0 }}>
              <colgroup>
                <col style={{ width: 44 }} />
                <col />
                {isStaff && <col style={{ width: '20%' }} />}
                {isStaff && <col style={{ width: '14%' }} />}
                <col style={{ width: 70 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 70 }} />
              </colgroup>
              <thead>
                <tr>
                  {['#', isStaff ? 'Staff' : LEVELS.find((l) => l.key === level)?.label,
                    ...(isStaff ? ['Role', 'Branch'] : []),
                    'Deals', 'Value (KES)', 'Weighted (KES)', 'Share', 'Win %'].map((h, i) => (
                    <th key={i}
                        className={'px-2 py-2 text-[11px] font-semibold uppercase '
                          + (i >= 4 ? 'text-right ' : 'text-left ')
                          + (h === 'Value (KES)' ? 'bg-[#0082BB] text-white' : 'bg-gray-100 text-gray-600')}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  const expanded = !isStaff && openRow === r.key;
                  return (
                    <>
                    <tr key={r.key}>
                      <td className={`${bg} px-2 py-1.5 text-xs`}>
                        <span className={'inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold '
                          + (r.rank <= 3 ? MEDAL[r.rank - 1] : 'text-gray-400')}>
                          {r.rank}
                        </span>
                      </td>
                      <td className={`${bg} truncate px-2 py-1.5 text-xs font-medium text-gray-900`}
                          title={r.label || r.name}>
                        {isStaff ? r.name : (
                          <button type="button" onClick={() => void expand(r.key)}
                                  className="flex items-center gap-1.5 text-left hover:text-brand-primary">
                            <span className="text-gray-400">{openRow === r.key ? '▾' : '▸'}</span>
                            {r.label || r.name}
                          </button>
                        )}
                      </td>
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.role}>
                          {r.role}
                        </td>
                      )}
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.branch}>
                          {r.branch}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-700`}>
                        {r.deals}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs font-semibold tabular-nums text-gray-900`}>
                        {kes(r.value)}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-600`}>
                        {kes(r.weighted)}
                      </td>
                      <td className={`${bg} px-2 py-1.5`}>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                          <div className="h-full rounded-full bg-[#0082BB]"
                               style={{ width: `${(r.value / max) * 100}%` }} />
                        </div>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums`}>
                        <span className={r.win_rate >= 50 ? 'text-[#3B6D11]' : 'text-gray-500'}>
                          {r.win_rate}%
                        </span>
                      </td>
                    </tr>
                    {expanded && (
                      <tr key={`${r.key}-drill`}>
                        <td colSpan={9} className="bg-[#F7FBFD] px-6 py-3">
                          {drillLoading && (
                            <p className="text-xs text-gray-400">Opening {r.key}…</p>
                          )}
                          {!drillLoading && drill && drill.length === 0 && (
                            <p className="text-xs text-gray-400">Nobody to show here.</p>
                          )}
                          {!drillLoading && drill && drill.length > 0 && (
                            <table className="w-full">
                              <thead>
                                <tr className="border-b border-gray-200">
                                  {['#', 'Staff', 'Name', 'Role', 'Deals',
                                    'Value (KES)', 'Weighted (KES)', 'Win %'].map((h, k) => (
                                    <th key={k}
                                        className={'py-1 pr-3 text-[10px] font-semibold uppercase tracking-wide text-gray-500 '
                                          + (k >= 4 ? 'text-right' : 'text-left')}>
                                      {h}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {drill.slice(0, 40).map((m) => (
                                  <tr key={m.key} className="border-b border-gray-100 last:border-0">
                                    <td className="w-8 py-1 pr-2 text-[11px] tabular-nums text-gray-400">{m.rank}</td>
                                    <td className="py-1 pr-3 text-xs tabular-nums text-gray-500" style={{ width: 80 }}>
                                      {m.staff_code}
                                    </td>
                                    <td className="py-1 pr-3 text-xs text-gray-800">{m.name}</td>
                                    <td className="truncate py-1 pr-3 text-xs text-gray-500" title={m.role}>
                                      {m.role}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-700" style={{ width: 60 }}>
                                      {m.deals}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs font-semibold tabular-nums text-gray-900" style={{ width: 120 }}>
                                      {kes(m.value)}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-600" style={{ width: 120 }}>
                                      {kes(m.weighted)}
                                    </td>
                                    <td className="py-1 text-right text-xs tabular-nums" style={{ width: 60 }}>
                                      <span className={m.win_rate >= 50 ? 'text-[#3B6D11]' : 'text-gray-500'}>
                                        {m.win_rate}%
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {!drillLoading && (drill?.length ?? 0) > 40 && (
                            <p className="mt-1 text-[11px] text-gray-400">
                              showing the top 40 of {drill?.length}
                            </p>
                          )}
                        </td>
                      </tr>
                    )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
'''

ANALYTICS = r'''// A3 — daily-log analytics. The 80/20 view first, because that is the question
// management actually asks: which few activities are producing the output.
//
// Three panels:
//   IMPACT     tier split (high/medium/low) plus the per-activity contribution
//              that produced it, so the pie is never a black box — you can see
//              which activity put each slice there.
//   VALIDATION where the logs stand: validated, pending, returned, auto-swept.
//   TREND      index per day across the window, so a dip has a date.
//
// Scope comes from the server (get_visible_staff_codes), so a branch manager
// sees their branch and the MD sees the bank without this component deciding
// anything.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchBranchLogAnalytics, fetchBranchLogLeaderboard,
  type BranchLogAnalytics, type Leaderboard,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

// Brand palette. High is primary blue, medium the deep blue, low grey — so the
// eye reads importance by saturation rather than by hue alone.
const TIER_COLOUR: Record<string, string> = {
  high: '#0082BB', medium: '#005B82', low: '#979797',
};
const TIER_LABEL: Record<string, string> = {
  high: 'High impact', medium: 'Medium', low: 'Low',
};
const VALID_COLOUR = ['#669438', '#E0A02B', '#C4536F', '#979797'];

function pct(n: number, total: number): string {
  if (!total) return '0%';
  return `${Math.round((n / total) * 1000) / 10}%`;
}

export default function DailyLogAnalytics() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [data, setData] = useState<BranchLogAnalytics | null>(null);
  // Met vs not met per unit, cumulative over the window. Sourced from the
  // leaderboard so the analytics and the ranking cannot report different
  // achievement for the same population.
  const [byUnit, setByUnit] = useState<Leaderboard | null>(null);
  // At a branch the MD-reporting unit is the wrong label — a teller does not
  // think of themselves as under 'Director Consumer & Commercial Banking'.
  // Default to segments when the caller's population sits in one branch.
  const [dim, setDim] = useState<'unit' | 'segment'>('segment');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = findPeriod(periodKey);
      const a = periodArgs(p);
      setData(await fetchBranchLogAnalytics(a.days ?? 0, '', a.start ?? '', a.end ?? ''));
      try {
        const lb = await fetchBranchLogLeaderboard({ ...a, level: dim });
        setByUnit(lb);
      } catch { setByUnit(null); }
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load analytics.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, dim, toast]);

  useEffect(() => { void load(); }, [load]);

  const impact = data?.impact;
  const totals = data?.totals;

  const tierData = useMemo(() => {
    if (!impact) return [];
    return (['high', 'medium', 'low'] as const)
      .map((t) => ({ name: TIER_LABEL[t], key: t, value: Math.max(Number(impact[t]) || 0, 0) }))
      .filter((d) => d.value > 0);
  }, [impact]);

  const activityData = useMemo(() => {
    const by = impact?.by_activity ?? {};
    return Object.entries(by)
      .map(([k, v]) => ({
        key: k,
        name: k.replace(/_/g, ' '),
        index: Math.round(Number((v as { index: number }).index) || 0),
        tier: String((v as { tier: string }).tier || 'medium'),
      }))
      .filter((d) => d.index > 0)
      .sort((a, b) => b.index - a.index)
      .slice(0, 12);
  }, [impact]);

  const validationData = useMemo(() => {
    if (!totals) return [];
    return [
      { name: 'Validated', value: totals.validated || 0 },
      { name: 'Pending', value: totals.pending || 0 },
      { name: 'Returned', value: totals.returned || 0 },
      { name: 'Auto-submitted', value: totals.auto_submitted || 0 },
    ].filter((d) => d.value > 0);
  }, [totals]);

  const totalIndex = Number(impact?.total) || 0;
  const highPct = Number(impact?.high_pct) || 0;

  return (
    <div className="mt-4 space-y-4">
      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900">
                Index analytics — where the output comes from
              </h2>
            </div>
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </Card.Header>
        <Card.Body>
          {loading && <p className="py-10 text-center text-sm text-gray-400">Loading analytics…</p>}

          {!loading && !data && (
            <p className="py-10 text-center text-sm text-gray-400">No analytics available.</p>
          )}

          {!loading && data && totalIndex === 0 && (
            <p className="py-10 text-center text-sm text-gray-400">
              No index produced in this period.
            </p>
          )}

          {!loading && data && totalIndex > 0 && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
              <div>
                <ResponsiveContainer width="100%" height={230}>
                  <PieChart>
                    <Pie data={tierData} dataKey="value" nameKey="name"
                         innerRadius={55} outerRadius={90} paddingAngle={2}>
                      {tierData.map((d) => (
                        <Cell key={d.key} fill={TIER_COLOUR[d.key]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => [`${Math.round(v)} index`, '']} />
                    <Legend verticalAlign="bottom" height={24}
                            wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="mt-1 text-center">
                  <div className="text-2xl font-semibold text-[#0082BB]">
                    {Math.round(highPct)}%
                  </div>
                </div>
              </div>

              {/* The pie is never a black box: this is what put each slice there. */}
              <div>
                <div className="mb-1 text-xs font-semibold text-gray-600">
                  Contribution by activity
                </div>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={activityData} layout="vertical"
                            margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#EDEDED" />
                    <XAxis type="number" tick={{ fontSize: 10, fill: '#979797' }} />
                    <YAxis type="category" dataKey="name" width={150}
                           tick={{ fontSize: 10, fill: '#464646' }} />
                    <Tooltip formatter={(v: number) => [`${v} index`, '']} />
                    <Bar dataKey="index" radius={[0, 3, 3, 0]}>
                      {activityData.map((d) => (
                        <Cell key={d.key} fill={TIER_COLOUR[d.tier] || '#979797'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </Card.Body>
      </Card>

      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-base font-semibold text-gray-900">
              Daily target — met vs not met
            </h2>
          </div>
        </Card.Header>
        <Card.Body>
          {!byUnit || (byUnit.scored_days ?? 0) === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              No scored days in this period.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
              <div className="text-center">
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie dataKey="value" innerRadius={48} outerRadius={78} paddingAngle={2}
                         data={[{ name: 'Met', value: byUnit.met_days ?? 0 },
                                { name: 'Not met',
                                  value: (byUnit.scored_days ?? 0) - (byUnit.met_days ?? 0) }]}>
                      <Cell fill="#669438" />
                      <Cell fill="#C4536F" />
                    </Pie>
                    <Tooltip formatter={(v: number) => [`${v} person-days`, '']} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="text-2xl font-semibold text-[#3B6D11]">
                  {byUnit.met_rate ?? 0}%
                </div>
                <div className="text-xs text-gray-500">
                  of person-days met the target, bank-wide
                </div>
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-gray-600">
                    By {dim === 'segment' ? 'segment' : 'unit'} — cumulative over{' '}
                    {findPeriod(periodKey).label.toLowerCase()}
                  </span>
                  <span className="flex gap-1 text-[11px]">
                    {(['segment', 'unit'] as const).map((d) => (
                      <button key={d} type="button" onClick={() => setDim(d)}
                        className={'rounded-full px-2 py-0.5 '
                          + (dim === d ? 'bg-[#0082BB] text-white'
                                       : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                        {d === 'segment' ? 'Consumer / Commercial / Operations' : 'Units'}
                      </button>
                    ))}
                  </span>
                </div>
                <ResponsiveContainer width="100%" height={Math.max(180, (byUnit.rows.length || 1) * 26)}>
                  <BarChart
                    data={byUnit.rows.map((r) => ({
                      // Was a local regex stripping "Director," - a symptom of
                      // the unit key being a job title. The server now sends a
                      // proper department label, so the hack goes.
                      name: String(r.label || r.name || '').slice(0, 26),
                      met: r.met_days ?? 0,
                      missed: (r.scored_days ?? 0) - (r.met_days ?? 0),
                      rate: r.met_rate ?? 0,
                    }))}
                    layout="vertical" stackOffset="expand"
                    margin={{ left: 8, right: 16, top: 4, bottom: 4 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#EDEDED" />
                    <XAxis type="number" tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                           tick={{ fontSize: 10, fill: '#979797' }} />
                    <YAxis type="category" dataKey="name" width={170}
                           tick={{ fontSize: 10, fill: '#464646' }} />
                    <Tooltip formatter={(v: number, n: string) => [`${v} days`, n]} />
                    <Bar dataKey="met" stackId="a" fill="#669438" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="missed" stackId="a" fill="#C4536F" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </Card.Body>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Validation state</h2>
          </Card.Header>
          <Card.Body>
            {validationData.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-400">No logs in this period.</p>
            ) : (
              <div className="grid grid-cols-[180px_minmax(0,1fr)] items-center gap-4">
                <ResponsiveContainer width="100%" height={170}>
                  <PieChart>
                    <Pie data={validationData} dataKey="value" nameKey="name"
                         innerRadius={42} outerRadius={70} paddingAngle={2}>
                      {validationData.map((d, i) => (
                        <Cell key={d.name} fill={VALID_COLOUR[i % VALID_COLOUR.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-1 text-xs">
                  {validationData.map((d, i) => (
                    <div key={d.name} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-gray-600">
                        <span className="inline-block h-2 w-2 rounded-full"
                              style={{ background: VALID_COLOUR[i % VALID_COLOUR.length] }} />
                        {d.name}
                      </span>
                      <span className="tabular-nums text-gray-800">
                        {d.value}
                        <span className="ml-1 text-gray-400">
                          {pct(d.value, totals?.logs || 0)}
                        </span>
                      </span>
                    </div>
                  ))}
                  <div className="mt-2 border-t border-gray-100 pt-2 text-gray-500">
                    Validation rate{' '}
                    <span className="font-semibold text-gray-800">
                      {totals?.validation_rate ?? 0}%
                    </span>
                  </div>
                </div>
              </div>
            )}
          </Card.Body>
        </Card>

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Participation</h2>
          </Card.Header>
          <Card.Body>
            {!totals ? (
              <p className="py-8 text-center text-sm text-gray-400">No data.</p>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Logs submitted', value: totals.logs, tone: 'text-gray-900' },
                  { label: 'People filing', value: totals.submitters, tone: 'text-gray-900' },
                  { label: 'Awaiting validation', value: totals.pending, tone: 'text-amber-600' },
                  { label: 'Auto-submitted at deadline', value: totals.auto_submitted, tone: 'text-amber-700' },
                  { label: 'Returned for amendment', value: totals.returned, tone: 'text-rose-600' },
                  { label: 'Total index', value: Math.round(totalIndex), tone: 'text-[#0082BB]' },
                ].map((s) => (
                  <div key={s.label} className="rounded-lg border border-gray-200 p-3">
                    <div className={`text-xl font-semibold tabular-nums ${s.tone}`}>
                      {Number(s.value || 0).toLocaleString()}
                    </div>
                    <div className="mt-0.5 text-[11px] text-gray-500">{s.label}</div>
                  </div>
                ))}
              </div>
            )}
          </Card.Body>
        </Card>
      </div>
    </div>
  );
}
'''

ADMINPAGE = r'''// ──────────────────────────────────────────────────────────────────────────
// Admin > Daily Log — productivity index configuration, consolidated into the
// Administration area (previously only reachable as an "Index Setup" tab on the
// Daily Log page itself).
//
// Three sections, all against existing endpoints:
//   1. Daily index target        POST /branch-log/config
//   2. Points per activity       POST /branch-log/config  (activity_weights)
//   3. Extra activities          POST /branch-log/activities  (role-tagged)
//
// AMOUNT-FIELD SCALING: compute_index is sum(count x weight), so an amount field
// (deposits in KES) with weight 1 would score 500,000 for a KES 500k deposit and
// drown out every count-based activity. For amount fields this panel takes
// "points per KES 100,000" and stores weight = entered / 100000.
// ──────────────────────────────────────────────────────────────────────────
import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { AdminTabs } from '@/components/AdminTabs';
import {
  fetchBranchLogFields,
  fetchBranchLogConfig,
  saveBranchLogConfig,
  saveBranchLogUnitConfig,
  fetchBranchLogActivities,
  saveBranchLogActivities,
  type BranchLogField,
  type ExtraActivity,
} from '@/lib/api';

const AMOUNT_SCALE = 100000; // amount weights are entered per KES 100,000

const inputCls =
  'w-full rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:outline-none ' +
  'focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20';

const btn =
  'rounded-md px-3 py-1.5 text-sm font-medium text-white bg-[#0082BB] ' +
  'hover:opacity-90 disabled:opacity-40';
const btnGhost =
  'rounded-md px-3 py-1.5 text-sm font-medium text-gray-600 border border-gray-300 hover:bg-gray-50';

function isAmount(f: BranchLogField): boolean {
  return String(f.type || '').toLowerCase() === 'amount';
}

export function DailyLogAdmin() {
  const [fields, setFields] = useState<BranchLogField[]>([]);
  const [weights, setWeights] = useState<Record<string, string>>({});
  const [target, setTarget] = useState('');
  // Per-unit sets and weights (AS1-AS3). A unit with NO set keeps the branch
  // base, so "not configured" is the normal state, not an error.
  const [units, setUnits] = useState<string[]>([]);
  const [unitLabels, setUnitLabels] = useState<Record<string, string>>({});
  const [sets, setSets] = useState<Record<string, string[]>>({});
  const [unitW, setUnitW] = useState<Record<string, Record<string, number>>>({});
  const [unit, setUnit] = useState('');
  const [savingUnit, setSavingUnit] = useState(false);

  const unitKeys = unit ? (sets[unit] ?? []) : [];
  const unitConfigured = unit ? Boolean(sets[unit]?.length) : false;

  function toggleKey(k: string) {
    if (!unit) return;
    const cur = sets[unit] ?? [];
    const next = cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k];
    setSets({ ...sets, [unit]: next });
  }

  function setUnitWeight(k: string, v: string) {
    if (!unit) return;
    const cur = { ...(unitW[unit] ?? {}) };
    if (v.trim() === '') delete cur[k];
    else cur[k] = Number(v) || 0;
    setUnitW({ ...unitW, [unit]: cur });
  }

  async function saveUnit() {
    if (!unit) return;
    setSavingUnit(true);
    try {
      // Sent as its own payload. An empty set REMOVES the unit server-side,
      // returning its people to the branch base rather than leaving them with
      // no activities at all.
      await saveBranchLogUnitConfig({
        activity_sets: { [unit]: sets[unit] ?? [] },
        unit_activity_weights: { [unit]: unitW[unit] ?? {} },
      });
      // This page reports through setMsg, not a toast - matching the two save
      // handlers already here rather than introducing a second convention.
      setMsg({
        tone: 'ok',
        text: (sets[unit] ?? []).length
          ? `${unit} saved.`
          : `${unit} returned to the branch activity set.`,
      });
    } catch (e) {
      setMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Could not save.' });
    } finally {
      setSavingUnit(false);
    }
  }
  const [extras, setExtras] = useState<ExtraActivity[]>([]);
  const [newAct, setNewAct] = useState({ key: '', label: '', unit: '', weight: '', roles: '' });
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const [f, cfg, acts] = await Promise.all([
        fetchBranchLogFields(),
        fetchBranchLogConfig(),
        fetchBranchLogActivities(),
      ]);
      setFields(f.fields ?? []);
      const w: Record<string, string> = {};
      for (const fl of f.fields ?? []) {
        const raw = Number(cfg.activity_weights?.[fl.key] ?? 0);
        w[fl.key] = String(isAmount(fl) ? raw * AMOUNT_SCALE : raw);
      }
      setWeights(w);
      setTarget(String(cfg.daily_index_target ?? 0));
      setUnits(cfg.units ?? []);
      setUnitLabels(cfg.unit_labels ?? {});
      setSets(cfg.activity_sets ?? {});
      setUnitW(cfg.unit_activity_weights ?? {});
      setExtras(acts.extra ?? []);
    } catch (e) {
      setMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Could not load config' });
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const saveWeights = async () => {
    setBusy(true); setMsg(null);
    try {
      const out: Record<string, number> = {};
      for (const f of fields) {
        const entered = Number(weights[f.key] ?? 0) || 0;
        out[f.key] = isAmount(f) ? entered / AMOUNT_SCALE : entered;
      }
      await saveBranchLogConfig(out, Number(target) || 0);
      setMsg({ tone: 'ok', text: 'Points and target saved.' });
      await load();
    } catch (e) {
      setMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Save failed' });
    } finally { setBusy(false); }
  };

  const addExtra = () => {
    const k = newAct.key.trim();
    if (!k || !newAct.label.trim()) {
      setMsg({ tone: 'err', text: 'Key and label are required.' }); return;
    }
    setExtras((p) => [
      ...p.filter((x) => x.key !== k),
      {
        key: k,
        label: newAct.label.trim(),
        type: 'int',
        unit: newAct.unit.trim(),
        weight: Number(newAct.weight) || 0,
        roles: newAct.roles.split(',').map((r) => r.trim()).filter(Boolean),
      },
    ]);
    setNewAct({ key: '', label: '', unit: '', weight: '', roles: '' });
  };

  const saveExtras = async () => {
    setBusy(true); setMsg(null);
    try {
      await saveBranchLogActivities(extras);
      setMsg({ tone: 'ok', text: 'Extra activities saved.' });
      await load();
    } catch (e) {
      setMsg({ tone: 'err', text: e instanceof Error ? e.message : 'Save failed' });
    } finally { setBusy(false); }
  };

  return (
    <>
      <AdminTabs subtitle="Daily Log productivity index — activity points, target, and role-specific activities." />
      <div className="mx-auto max-w-7xl space-y-4 px-6 py-5 2xl:max-w-[1680px]">
        {msg && (
          <div className={`rounded-md px-3 py-2 text-sm ${
            msg.tone === 'ok' ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-700'}`}>
            {msg.text}
          </div>
        )}

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Activity points &amp; daily target</h2>
          </Card.Header>
          <Card.Body>
            <label className="mb-4 block text-sm">
              <span className="mb-1 block text-gray-700">Daily index target</span>
              <input type="number" min={0} className={`${inputCls} w-40`}
                value={target} onChange={(e) => setTarget(e.target.value)} />
              <span className="mt-1 block text-xs text-gray-400">
                The index a productive day should reach. Ranking shows each person against this.
              </span>
            </label>

            <p className="mb-1 text-sm font-medium text-gray-700">Points per activity</p>
            <p className="mb-3 text-xs text-gray-400">
              Count activities score points x quantity. Amount activities (KES) are entered as
              points per KES {AMOUNT_SCALE.toLocaleString()} so they stay comparable with counts.
            </p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {fields.map((f) => (
                <label key={f.key} className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-gray-700">
                    {f.label}
                    <span className="ml-1 text-xs text-gray-400">
                      {isAmount(f) ? `(per KES ${AMOUNT_SCALE.toLocaleString()})` : `(${f.unit || 'count'})`}
                    </span>
                  </span>
                  <input type="number" step="any" className={`${inputCls} w-24`}
                    value={weights[f.key] ?? ''}
                    onChange={(e) => setWeights((p) => ({ ...p, [f.key]: e.target.value }))} />
                </label>
              ))}
            </div>
            <div className="mt-4 flex justify-end">
              <button type="button" className={btn} disabled={busy} onClick={() => void saveWeights()}>
                {busy ? 'Saving…' : 'Save points & target'}
              </button>
            </div>
          </Card.Body>
        </Card>

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Role-specific activities</h2>
          </Card.Header>
          <Card.Body>
            <p className="mb-3 text-xs text-gray-400">
              Activities beyond the common base. Leave roles blank to show for everyone; list roles
              (comma-separated) to show only for those roles — anything logged outside a person's
              own role counts as over-and-above.
            </p>

            {extras.length > 0 && (
              <div className="mb-3 space-y-1">
                {extras.map((a, i) => (
                  <div key={a.key}
                    className="flex items-center justify-between rounded border border-gray-100 px-3 py-2">
                    <div className="min-w-0">
                      <span className="font-medium text-gray-800">{a.label}</span>
                      <span className="ml-2 text-xs text-gray-500">
                        {a.unit || 'count'} · {a.weight} pts
                        {a.roles?.length ? ` · ${a.roles.join(', ')}` : ' · all roles'}
                      </span>
                    </div>
                    <button type="button" className="text-xs text-gray-400 hover:text-red-600"
                      onClick={() => setExtras((p) => p.filter((_, j) => j !== i))}>
                      Remove
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-5">
              <input className={inputCls} placeholder="key (e.g. credit_files)"
                value={newAct.key} onChange={(e) => setNewAct((p) => ({ ...p, key: e.target.value }))} />
              <input className={inputCls} placeholder="Label"
                value={newAct.label} onChange={(e) => setNewAct((p) => ({ ...p, label: e.target.value }))} />
              <input className={inputCls} placeholder="unit"
                value={newAct.unit} onChange={(e) => setNewAct((p) => ({ ...p, unit: e.target.value }))} />
              <input className={inputCls} type="number" step="any" placeholder="points"
                value={newAct.weight} onChange={(e) => setNewAct((p) => ({ ...p, weight: e.target.value }))} />
              <input className={inputCls} placeholder="roles (comma-sep)"
                value={newAct.roles} onChange={(e) => setNewAct((p) => ({ ...p, roles: e.target.value }))} />
            </div>

            <div className="mt-3 flex justify-end gap-2">
              <button type="button" className={btnGhost} onClick={addExtra}>Add activity</button>
              <button type="button" className={btn} disabled={busy} onClick={() => void saveExtras()}>
                {busy ? 'Saving…' : 'Save activities'}
              </button>
            </div>
          </Card.Body>
        </Card>

        <Card className="mt-4">
          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="text-base font-semibold text-gray-900">Activities by unit</h2>
              <select value={unit} onChange={(e) => setUnit(e.target.value)}
                      className="rounded border border-gray-200 px-2 py-1 text-xs">
                <option value="">Select a unit…</option>
                {units.map((u) => (
                  <option key={u} value={u}>
                    {unitLabels[u] ?? u}{sets[u]?.length ? ` (${sets[u].length})` : ''}
                  </option>
                ))}
              </select>
            </div>
          </Card.Header>
          <Card.Body>
            {!unit && (
              <p className="py-6 text-center text-sm text-gray-400">
                Pick a unit to give it its own activities.
              </p>
            )}

            {unit && (
              <>
                <p className="mb-3 text-xs text-gray-500">
                  {unitConfigured
                    ? `${unitKeys.length} selected. Clear them all to return this unit to the branch set.`
                    : 'Not configured — this unit currently uses the branch activity set.'}
                </p>

                <div className="overflow-auto rounded-lg border border-gray-200">
                  <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
                    <thead>
                      <tr>
                        <th className="w-10 bg-gray-100 px-2 py-2"></th>
                        <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Activity</th>
                        <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Bank weight</th>
                        <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">This unit</th>
                      </tr>
                    </thead>
                    <tbody>
                      {fields.filter((f) => f.key !== 'remarks').map((f, i) => {
                        const on = unitKeys.includes(f.key);
                        const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                        const ov = unitW[unit]?.[f.key];
                        return (
                          <tr key={f.key}>
                            <td className={`${bg} px-2 py-1.5`}>
                              <input type="checkbox" checked={on}
                                     onChange={() => toggleKey(f.key)} />
                            </td>
                            <td className={`${bg} px-2 py-1.5 text-xs ${on ? 'text-gray-900' : 'text-gray-400'}`}>
                              {f.label}
                              {f.key === 'loans_referred' && (
                                <span className="ml-2 rounded bg-[#E6F1FB] px-1.5 py-0.5 text-[10px] text-[#0C447C]">
                                  always included
                                </span>
                              )}
                            </td>
                            <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                              {weights[f.key] ?? 0}
                            </td>
                            <td className={`${bg} px-2 py-1.5 text-right`}>
                              <input
                                type="number" step="0.1"
                                value={ov === undefined ? '' : String(ov)}
                                placeholder="inherit"
                                onChange={(e) => setUnitWeight(f.key, e.target.value)}
                                className="w-20 rounded border border-gray-200 px-2 py-1 text-right text-xs"
                              />
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="mt-3 flex items-center justify-between gap-2">
                  <span className="text-[11px] text-gray-500">
                    Blank weight inherits the bank figure. Target stays {target} for everyone.
                  </span>
                  <button type="button" className={btn} disabled={savingUnit}
                          onClick={() => void saveUnit()}>
                    {savingUnit ? 'Saving…' : `Save ${(unitLabels[unit] ?? unit).slice(0, 28)}`}
                  </button>
                </div>
              </>
            )}
          </Card.Body>
        </Card>
      </div>
    </>
  );
}

export default DailyLogAdmin;
'''


def main():
    apply = "--apply" in sys.argv
    for p in (OV, ABL, API, LEAD, PLEAD, ANAL, ADMIN, APITS):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            print("       Apply patch_as4_unit_admin_ui.py and its predecessors first.")
            return 1

    ov = open(OV, encoding="utf-8").read()
    abl = open(ABL, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if "def unit_label(" in ov:
        print("ABORT: unit_label already present - UL1 looks applied.")
        return 1
    if "def unit_for_role(" not in ov:
        print("ABORT: apply patch_a1_leaderboard.py first.")
        return 1

    ov = ov.replace("def unit_for_role(role: str) -> str:",
                    SEGMENT + "def unit_for_role(role: str) -> str:", 1)
    print("  ok  org_validator - unit_label")

    i = abl.index('@router.get("/config")')
    m = re.search(r'\n@router\.(get|post)\("/(?!config)', abl[i + 40:])
    abl = abl[:i] + CFG + abl[i + 40 + m.start() + 1:]
    a = abl.index('@router.get("/leaderboard")')
    b = abl.index('@router.get("/analytics")', a)
    abl = abl[:a] + LB + abl[b:]
    print("  ok  api_branch_log - config and leaderboard carry labels")

    e = api.index('@app.get("/api/pipeline/leaderboard")')
    m2 = re.search(r'\n@app\.(get|post)\("/api/(?!pipeline/leaderboard)', api[e + 40:])
    api = api[:e] + PLB + api[e + 40 + m2.start() + 1:]
    print("  ok  api - pipeline leaderboard carries labels")

    for old, new in TS_EDITS:
        if ts.count(old) != 1:
            print("ABORT: api.ts edit matched %d times: %s" % (ts.count(old), old[:44]))
            return 1
        ts = ts.replace(old, new, 1)
    print("  ok  api.ts - label fields")

    # The KEY must survive everywhere, or filters that round-trip break.
    for name, blob in (("Leaderboard", LEADER), ("PipelineLeaderboard", PLEADER)):
        if "r.name" not in blob:
            print("ABORT: %s no longer sends the key - filtering would break." % name)
            return 1
    if "replace(/^Director" in ANALYTICS:
        print("ABORT: the title-stripping hack survives in the analytics chart.")
        return 1
    if "unitLabels" not in ADMINPAGE:
        print("ABORT: the admin picker does not use labels.")
        return 1
    for name, blob in (("Leaderboard", LEADER), ("PipelineLeaderboard", PLEADER),
                       ("DailyLogAnalytics", ANALYTICS), ("DailyLogAdmin", ADMINPAGE)):
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s unbalanced %s%s." % (name, op, cl))
                return 1
    print("  ok  post-checks: keys preserved, hack gone")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((OV, ov), (ABL, abl), (API, api), (APITS, ts),
                          (LEAD, LEADER), (PLEAD, PLEADER),
                          (ANAL, ANALYTICS), (ADMIN, ADMINPAGE)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (OV, ABL, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Seed the display-name overrides (nine units derivation gets wrong):")
    print("  python scripts\\seed_unit_labels.py --apply")
    print("Then: pushd frontend\\web && pnpm tsc --noEmit && popd")
    return 0


if __name__ == "__main__":
    sys.exit(main())
