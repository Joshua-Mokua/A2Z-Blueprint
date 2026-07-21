"""
v10.540 Phase 8 Batch γ4a — Strategic Initiatives read-only routes.

Wraps utils.command_centre_strategic_initiatives.CommandCentreStrategicInitiativesEngine
which is the façade composing 4 underlying engines (portfolio, impact,
dependency, resource).

Endpoint inventory (read-only):
  - GET /api/initiatives/portfolio-summary
      Bank-wide RAG distribution + initiatives-at-risk list.
  - GET /api/initiatives/{initiative_id}
      Single initiative detail: milestones + RAG + dependencies + KPI linkage.

Authorization: any authenticated user. Strategic initiatives are
exec-team visibility; if narrower scope is needed later we add a
role-tier gate (Director+ etc.).

Empty-data tolerance: the underlying engine reads from
data/strategic_initiatives.json which may not exist yet (initiatives
register-as-you-go via the Streamlit Command Centre page). Routes
catch FileNotFoundError + similar and return an empty-state response
with status="no_data" so the React UI can render a friendly "No
initiatives registered yet" empty state rather than crashing.

Audit emission: NOT emitted on these read endpoints. Future register/
add-milestone PUT/POST endpoints (γ4c+) will emit.
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException

from utils.auth_jwt import get_current_user


router = APIRouter(prefix="/api/initiatives", tags=["initiatives"])
_log = logging.getLogger("a2z.initiatives")


# Module-level singleton — instantiated lazily so the route module imports
# cleanly even if the engine has init-time dependencies that fail
# (e.g. missing data file).
_engine = None


def _get_engine():
    """
    Lazy singleton for CommandCentreStrategicInitiativesEngine.
    Wraps instantiation in try/except so an init error doesn't 500
    every subsequent request — instead we log once and re-attempt
    on the next call.
    """
    global _engine
    if _engine is not None:
        return _engine
    try:
        from utils.command_centre_strategic_initiatives import (
            CommandCentreStrategicInitiativesEngine,
        )
        _engine = CommandCentreStrategicInitiativesEngine()
        return _engine
    except Exception as e:
        _log.warning(
            "CommandCentreStrategicInitiativesEngine init failed: %s. "
            "Will retry on next request.", e,
        )
        return None


def _safe_call(method_name: str, *args, default=None):
    """
    Call engine.<method_name>(*args). On any exception, return `default`
    and log. Used to keep endpoints empty-state-tolerant when the
    engine is partly initialized or data file missing.
    """
    engine = _get_engine()
    if engine is None:
        return default
    fn = getattr(engine, method_name, None)
    if fn is None:
        _log.warning("Engine has no method %s", method_name)
        return default
    try:
        return fn(*args)
    except FileNotFoundError as e:
        _log.info("Engine.%s missing data file: %s", method_name, e)
        return default
    except Exception as e:
        _log.warning("Engine.%s raised %s: %s", method_name, type(e).__name__, e)
        return default


# ── Endpoints ───────────────────────────────────────────────────────────


@router.get("/portfolio-summary")
def fetch_portfolio_summary(
    user: dict = Depends(get_current_user),
):
    """
    Bank-wide RAG distribution + initiatives-at-risk list.
    Returns empty-state shape when no initiatives are registered yet
    (data/strategic_initiatives.json missing or empty).
    """
    summary = _safe_call("portfolio_summary", default=None)
    if summary is None:
        return {
            "status":  "no_data",
            "summary": {
                "total":         0,
                "rag_distribution": {"GREEN": 0, "AMBER": 0, "RED": 0},
                "at_risk":       [],
            },
            "source":  "command_centre",
            "note":    "No initiatives registered yet; the engine has no data file to read.",
        }
    return {
        "status":  "ok",
        "summary": summary,
        "source":  "command_centre",
    }


@router.get("/{initiative_id}")
def fetch_initiative_detail(
    initiative_id: str,
    user: dict = Depends(get_current_user),
):
    """Single initiative detail with milestones, from the canonical execute store."""
    try:
        mgr = _execute_manager()
        init = mgr.get_initiative(initiative_id)
        if not init:
            return {"status": "not_found", "initiative": None}
        return {"status": "ok", "initiative": _slim_initiative(init)}
    except Exception as e:  # noqa: BLE001
        _log.warning("fetch_initiative_detail failed: %s", e)
        return {"status": "error", "initiative": None, "note": str(e)}


@router.get("")
def list_initiatives(
    status: Optional[str] = "Active",
    workstream: Optional[str] = None,
    user: dict = Depends(get_current_user),
):
    """List canonical execute-initiatives with their milestone plans.

    status defaults to Active; pass status=All to include closed. Empty-state
    tolerant: returns {"status": "no_data", "initiatives": []} if the store is
    empty or unreadable, so the UI renders a friendly empty state.
    """
    try:
        mgr = _execute_manager()
        items = mgr.get_initiatives(status=status or "Active", workstream=workstream)
        slim = [_slim_initiative(i) for i in items]
        return {
            "status": "ok" if slim else "no_data",
            "count": len(slim),
            "initiatives": slim,
        }
    except Exception as e:  # noqa: BLE001
        _log.warning("list_initiatives failed: %s", e)
        return {"status": "no_data", "count": 0, "initiatives": [], "note": str(e)}


# ─── v10.543 Phase 1 — authoring write routes ──────────────────────────
# POST create-initiative + POST add-milestone. Both wrap ExecuteManager
# methods that already exist. created_by / actor is taken from the auth'd
# user, never the client body. Additive: GET routes above are untouched.

from pydantic import BaseModel, Field
from typing import List as _List, Optional as _Optional


class _NewInitiative(BaseModel):
    name:           str
    objective:      str
    category:       str = "Strategic Initiative"
    workstream:     str
    io:             str                      # owner — must be a register Staff Name
    sub_workstream: str = ""
    io_backup:      str = ""
    estimated_impact: float = 0
    tags:           _List[str] = Field(default_factory=list)


class _NewMilestone(BaseModel):
    name:       str
    owner:      str
    due_date:   str
    type:       str = "Delivery"
    start_date: str = ""
    description: str = ""


@router.post("")
def create_initiative_route(
    payload: _NewInitiative,
    user: dict = Depends(get_current_user),
):
    """Create a new initiative (starts at gate G0). created_by = the auth'd user."""
    try:
        mgr = _execute_manager()
        data = payload.model_dump()
        data["created_by"] = (user.get("full_name") or user.get("username") or "unknown")
        init_id = mgr.create_initiative(data)
        if not init_id:
            raise HTTPException(status_code=400, detail="create_initiative returned nothing")
        # create_initiative returns the id string
        iid = init_id if isinstance(init_id, str) else init_id.get("id")
        return {"status": "ok", "id": iid}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        _log.warning("create_initiative failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{initiative_id}/milestones")
def add_milestone_route(
    initiative_id: str,
    payload: _NewMilestone,
    user: dict = Depends(get_current_user),
):
    """Add a milestone to an existing initiative."""
    try:
        mgr = _execute_manager()
        if not mgr.get_initiative(initiative_id):
            raise HTTPException(status_code=404, detail=f"no initiative {initiative_id}")
        ms = mgr.add_milestone(initiative_id, payload.model_dump())
        if ms is None:
            raise HTTPException(status_code=400, detail="add_milestone returned nothing")
        ms_id = ms if isinstance(ms, str) else (ms.get("id") if isinstance(ms, dict) else None)
        return {"status": "ok", "milestone_id": ms_id}
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        _log.warning("add_milestone failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
