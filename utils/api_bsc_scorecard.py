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


def _scorecard_for_role(role: str) -> Dict[str, Any]:
    from utils.bsc_score_computation import resolve_role_kpis

    lib = _library()
    rw = (lib.get("role_kpi_weights") or {}).get(role) or {}
    defs = {k.get("id"): k for k in lib.get("kpis", []) if isinstance(k, dict)}

    kpis: List[Dict[str, Any]] = []
    for r in resolve_role_kpis(role):
        d = defs.get(r.canonical_id) or {}
        meta = (rw.get("kpis") or {}).get(r.canonical_id) or {}
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

    reports = [_row(idx[c], idx[c].get("role") in direct_roles)
               for c in sorted(visible) if c in idx]
    reports.sort(key=lambda p: (not p["is_direct_report"], p["full_name"]))

    return {"me": _row(me, False), "reports": reports,
            "direct_report_count": sum(1 for r in reports if r["is_direct_report"]),
            "total_visible": len(reports)}


@router.get("/scorecard/{staff_code}")
def bsc_scorecard(staff_code: str, user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """The scorecard definition for one person, scoped by the reporting tree."""
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

    card = _scorecard_for_role(person.get("role") or "")
    card["staff"] = {**person, "display_name": _display(person.get("full_name", ""))}
    return card


@router.get("/pillars")
def bsc_pillars(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Performance areas and their default weights, for headers and colours."""
    lib = _library()
    return {"pillars": lib.get("pillars", []),
            "pillar_weights": lib.get("pillar_weights", {})}
