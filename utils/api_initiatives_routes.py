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
    """
    Full status detail for a single initiative — milestones, RAG,
    dependencies, KPI linkage. 404 if not found.
    """
    status = _safe_call("initiative_status", initiative_id, default=None)
    if status is None:
        raise HTTPException(
            status_code=404,
            detail=f"No initiative found with id={initiative_id}",
        )
    return {
        "status":     "ok",
        "initiative": status,
        "source":     "command_centre",
    }
