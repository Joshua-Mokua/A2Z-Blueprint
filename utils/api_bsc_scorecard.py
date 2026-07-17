"""utils/api_bsc_scorecard.py — Balanced Scorecard (BSC) router.

Serves the scorecard *definition* for a person: which KPIs their role is measured on,
which performance area each sits in, what it is worth, and the dated objectives that
sit alongside the measures. The pre-existing ``/api/bsc/staff/{username}`` returns
computed *scores*; nothing exposed the scorecard itself, so the React page had nothing
to render.

Design notes:

* Weights come from ``resolve_role_kpis`` (utils.bsc_score_computation), which already
  reads ``role_kpi_weights[role]`` and returns the effective weight (area share x
  within-area share). This router does not re-implement that maths — one engine.
* Objectives are read straight from ``role_kpi_weights[role]["objectives"]``. They are
  deliberately not library KPIs: they are dated and belong to one person once.
* Scoping reuses ``get_visible_staff_codes`` — the canonical REPORTING_TREE walk that
  Pipeline already uses. The older BSC endpoint gated on ``role in ("admin","director")``,
  which the MD's own role string ("Managing Director") does not satisfy; anything
  hierarchy-shaped belongs to the tree, not to a role-name match.
* ``weights_complete: false`` is passed through untouched so the UI can show a
  scorecard as incomplete rather than implying invented weights are real.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException

from utils.auth_jwt import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/bsc", tags=["bsc"])


def _money_fields(entry, actual, rate: float, show_both: bool) -> Dict[str, Any]:
    """KES/USD equivalents for one KPI row, and the stretch line where allowed."""
    if not isinstance(entry, dict):
        return {"currency": None, "target_money": None, "stretch": None,
                "stretch_money": None, "actual_money": None, "baseline_2025": None}
    cur = entry.get("currency")
    stretch = entry.get("stretch_target")
    out = {
        "currency": cur,
        "target_money": _money(entry.get("target"), cur, rate),
        "actual_money": _money(actual, cur, rate),
        "baseline_2025": entry.get("baseline_2025"),
        "stretch": stretch if show_both else None,
        "stretch_money": _money(stretch, cur, rate) if show_both else None,
    }
    return out


def _library() -> dict:
    from utils.core import get_kpi_library
    return get_kpi_library() or {}


def _staff_index() -> Dict[str, dict]:
    """staff_code -> {name, role, unit}.

    Uses the roster loader that api_pipeline_scope already owns: it is cached with a
    60s TTL and thread-safe, and a second reader of the same spreadsheet would be one
    more copy of the same truth to drift.
    """
    from utils.api_pipeline_scope import get_staff_roster
    out: Dict[str, dict] = {}
    try:
        df = get_staff_roster()
        if df is None or len(df) == 0:
            return out
        for _, r in df.iterrows():
            code = str(r.get("Staff Code") or "").strip()
            if not code:
                continue
            out[code] = {
                "staff_code": code,
                "full_name": str(r.get("Staff Name") or "").strip(),
                "role": str(r.get("Role") or "").strip(),
                "unit": str(r.get("Branch") or r.get("Unit") or "").strip(),
                "department": str(r.get("Department") or "").strip(),
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"staff register unavailable: {exc}")
    return out


def _display(full_name: str, preferred: str = "") -> str:
    try:
        from utils.staff_names import display_name
        return display_name(full_name, preferred) or full_name
    except Exception:  # noqa: BLE001
        return (full_name or "").split(" ")[0] or full_name


def _may_switch_basis(user: dict, person: Optional[dict] = None) -> bool:
    """Only the roles named in bsc_view_config may see both lines and switch basis.

    Everyone else sees a single Target column carrying the stretch — the figure their
    own scorecard gave them. Keyed by role rather than staff code so it survives
    people changing seats.
    """
    from utils.bsc_score_computation import _view_config
    cfg = _view_config() or {}
    roles = {str(r).strip().lower() for r in (cfg.get("basis_switch_roles") or [])}
    codes = {str(s).strip() for s in (cfg.get("basis_switch_staff_codes") or [])}
    my_role = str((person or {}).get("role") or user.get("role") or "").strip().lower()
    my_code = str(user.get("staff_code") or "").strip()
    return my_role in roles or (my_code and my_code in codes)


def _money(value, currency: Optional[str], rate: float) -> Dict[str, Any]:
    """A monetary figure in both currencies. Group reports in USD, the affiliate runs
    in KES, so both are shown rather than one being the truth and the other lost.
    Non-monetary measures (percentages, counts, ratings) convert to nothing and say so.
    """
    if value is None or not currency or not rate:
        return {"kes": None, "usd": None, "scale": None}
    if currency == "USD_MM":
        return {"kes": round(value * rate, 2), "usd": round(value, 2), "scale": "MM"}
    if currency == "USD_K":
        return {"kes": round(value * rate, 2), "usd": round(value, 2), "scale": "K"}
    if currency == "KES_MM":
        return {"kes": round(value, 2), "usd": round(value / rate, 2), "scale": "MM"}
    if currency == "KES_K":
        return {"kes": round(value, 2), "usd": round(value / rate, 2), "scale": "K"}
    # An unrecognised currency returns nothing rather than guessing a scale: a wrong
    # scale is a wrong number by a factor of a thousand, and silently.
    return {"kes": None, "usd": None, "scale": None}


def _scorecard_for_role(role: str, staff_code: str = "", period: str = "2026",
                        basis: str = "", show_both: bool = False) -> Dict[str, Any]:
    from utils.bsc_score_computation import resolve_role_kpis

    lib = _library()
    rw = (lib.get("role_kpi_weights") or {}).get(role) or {}
    defs = {k.get("id"): k for k in lib.get("kpis", []) if isinstance(k, dict)}

    # Actuals, targets, achievement and the 1-5 score all come from
    # compute_staff_scorecard — the engine that already resolves bank_fixed ->
    # cascaded -> role_default targets and reads bsc_actuals. Recomputing any of
    # that here would be a second answer to the same question.
    from utils.bsc_score_computation import (
        compute_staff_scorecard, default_scoring_basis, fx_kes_per_usd, _bank_targets,
    )
    basis = (basis or default_scoring_basis()).lower()
    rate = fx_kes_per_usd()
    bank = _bank_targets() or {}

    scored: Dict[str, Any] = {}
    final_score = None
    if staff_code:
        try:
            sc = compute_staff_scorecard(staff_code, role, period, basis)
            final_score = sc.final_score
            scored = {k.canonical_id: k for k in sc.kpi_scores}
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"scorecard computation failed for {staff_code}: {exc}")

    kpis: List[Dict[str, Any]] = []
    for r in resolve_role_kpis(role):
        d = defs.get(r.canonical_id) or {}
        meta = (rw.get("kpis") or {}).get(r.canonical_id) or {}
        s = scored.get(r.canonical_id)
        kpis.append({
            "id": r.canonical_id,
            "name": d.get("name") or r.canonical_id,
            "area": r.pillar,
            "unit": d.get("unit") or "",
            "direction": r.direction,
            "weight": round(r.weight, 6),           # effective share of the scorecard
            "area_weight": (rw.get("areas") or {}).get(r.pillar),
            "within_area_weight": meta.get("weight"),
            "defined": r.defined,
            "description": d.get("description") or "",
            "actual": getattr(s, "actual", None),
            "target": getattr(s, "target", None),
            "target_source": getattr(s, "target_source", "missing"),
            "achievement_pct": getattr(s, "achievement_pct", None),
            "score": getattr(s, "score", None),
            **_money_fields(bank.get(f"{r.canonical_id}|{period}"),
                            getattr(s, "actual", None), rate, show_both),
        })

    objectives = [
        {"text": o.get("text"), "area": o.get("area"), "due": o.get("due"),
         "within_area_weight": o.get("weight"),
         "weight": (round((rw.get("areas") or {}).get(o.get("area"), 0.0) * o["weight"], 6)
                    if o.get("weight") is not None else None)}
        for o in (rw.get("objectives") or [])
    ]

    total = sum(k["weight"] for k in kpis) + sum(o["weight"] or 0.0 for o in objectives)
    return {
        "role": role,
        "areas": rw.get("areas"),
        "kpis": kpis,
        "objectives": objectives,
        "weights_complete": rw.get("weights_complete", False),
        "weights_pending_reason": rw.get("weights_pending_reason"),
        "source_ambiguous": rw.get("source_ambiguous", False),
        "source": rw.get("source"),
        "total_weight": round(total, 6),
        "has_scorecard": bool(kpis),
        "period": period,
        "final_score": final_score,
        "scored_count": sum(1 for k in kpis if k["score"] is not None),
        "basis": basis,
        "can_switch_basis": show_both,
        "fx_kes_per_usd": rate,
    }


@router.get("/team")
def bsc_team(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """The caller plus everyone whose scorecard the caller may open — the tabs."""
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.core import get_org_config

    idx = _staff_index()
    me_code = str(user.get("staff_code") or "").strip()
    me = idx.get(me_code) or {
        "staff_code": me_code,
        "full_name": user.get("full_name") or user.get("username") or "",
        "role": user.get("role") or "", "unit": "",
    }

    try:
        visible = {str(c) for c in get_visible_staff_codes(user)}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"scope lookup failed, falling back to self: {exc}")
        visible = {me_code}
    visible.discard(me_code)

    # Direct reports first: hierarchy[role] lists the roles a role reports TO, so the
    # roles reporting to me are those whose list contains my role.
    hierarchy = (get_org_config() or {}).get("hierarchy", {}) or {}
    my_role = (me.get("role") or "").strip()
    direct_roles = {
        r for r, parents in hierarchy.items()
        if isinstance(parents, list) and my_role and my_role in parents
    }

    lib_roles = set((_library().get("role_kpi_weights") or {}).keys())

    def _row(p: dict, direct: bool) -> dict:
        return {**p, "display_name": _display(p.get("full_name", "")),
                "is_direct_report": direct,
                "has_scorecard": p.get("role") in lib_roles}

    # Tabs are the people who report DIRECTLY to the caller, not everyone in scope.
    # get_visible_staff_codes returns the whole bank for the MD (364 people), which is
    # a scope for permission checks, not a tab bar. Direct reports are what a manager
    # actually reviews, and the same rule reproduces itself at every level down the
    # tree: a Branch Manager sees their branch team, a leaf sees only themselves.
    reports = [_row(idx[c], True) for c in sorted(visible)
               if c in idx and idx[c].get("role") in direct_roles]
    reports.sort(key=lambda p: (not p["has_scorecard"], p["role"], p["full_name"]))

    return {"me": _row(me, False), "reports": reports,
            "direct_report_count": len(reports),
            "total_visible": len(visible)}


@router.get("/scorecard/{staff_code}")
def bsc_scorecard(staff_code: str, period: str = "2026", basis: str = "",
                  user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """The scorecard for one person, scoped by the reporting tree.

    ``basis`` is honoured only for the roles allowed to switch it; anyone else gets
    the admin default whatever they ask for, so the parameter cannot be used to see
    a view they are not meant to.
    """
    from utils.api_pipeline_scope import get_visible_staff_codes

    staff_code = str(staff_code).strip()
    me_code = str(user.get("staff_code") or "").strip()
    if staff_code != me_code:
        try:
            allowed = {str(c) for c in get_visible_staff_codes(user)}
        except Exception:  # noqa: BLE001
            allowed = {me_code}
        if staff_code not in allowed:
            raise HTTPException(status_code=403,
                                detail="Not permitted to view this scorecard")

    person = _staff_index().get(staff_code)
    if not person:
        raise HTTPException(status_code=404, detail=f"Unknown staff code {staff_code}")

    show_both = _may_switch_basis(user)
    if not show_both:
        basis = ""      # ignore what was asked for; the default governs
    card = _scorecard_for_role(person.get("role") or "", staff_code, period,
                               basis, show_both)
    card["staff"] = {**person, "display_name": _display(person.get("full_name", ""))}
    return card


@router.get("/departments")
def bsc_departments(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """The caller's reports grouped by department — the tab structure.

    A tab per department rather than per person: the MD opens "Commercial" and
    chooses among the people in it, instead of reading fifteen first names. The
    grouping is the register's Department column, so it stays true as the bank
    reorganises. Departments containing a direct report are marked, and everyone in
    scope is listed so a department opens onto its whole team, not just its head.
    """
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.core import get_org_config

    idx = _staff_index()
    me_code = str(user.get("staff_code") or "").strip()
    me = idx.get(me_code) or {
        "staff_code": me_code,
        "full_name": user.get("full_name") or user.get("username") or "",
        "role": user.get("role") or "", "unit": "", "department": "",
    }

    try:
        visible = {str(c) for c in get_visible_staff_codes(user)}
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"scope lookup failed: {exc}")
        visible = {me_code}
    visible.discard(me_code)

    hierarchy = (get_org_config() or {}).get("hierarchy", {}) or {}
    my_role = (me.get("role") or "").strip()
    direct_roles = {
        r for r, parents in hierarchy.items()
        if isinstance(parents, list) and my_role and my_role in parents
    }
    lib_roles = set((_library().get("role_kpi_weights") or {}).keys())

    groups: Dict[str, List[dict]] = {}
    for code in sorted(visible):
        p = idx.get(code)
        if not p:
            continue
        dept = p.get("department") or p.get("unit") or "Unassigned"
        groups.setdefault(dept, []).append({
            **p,
            "display_name": _display(p.get("full_name", "")),
            "is_direct_report": p.get("role") in direct_roles,
            "has_scorecard": p.get("role") in lib_roles,
        })

    departments = []
    for dept, people in groups.items():
        people.sort(key=lambda x: (not x["is_direct_report"],
                                   not x["has_scorecard"], x["full_name"]))
        departments.append({
            "department": dept,
            "people": people,
            "head": next((x for x in people if x["is_direct_report"]), None),
            "direct_report_count": sum(1 for x in people if x["is_direct_report"]),
            "scorecard_count": sum(1 for x in people if x["has_scorecard"]),
            "total": len(people),
        })
    # Departments the caller line-manages first, then the rest alphabetically.
    departments.sort(key=lambda d: (not d["direct_report_count"], d["department"]))

    return {
        "me": {**me, "display_name": _display(me.get("full_name", "")),
               "is_direct_report": False,
               "has_scorecard": me.get("role") in lib_roles},
        "departments": departments,
        "department_count": len(departments),
        "total_visible": len(visible),
    }


@router.get("/pillars")
def bsc_pillars(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Performance areas and their default weights, for headers and colours."""
    lib = _library()
    return {"pillars": lib.get("pillars", []),
            "pillar_weights": lib.get("pillar_weights", {})}
