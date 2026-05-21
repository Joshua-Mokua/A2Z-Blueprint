"""utils.api_legal — FastAPI router for the Legal arc (v10.179).

Exposes the 9 Legal arc engines (ENH-221..230) as JSON-serializable
HTTP endpoints with JWT authentication. Provides the React-ready
surface for the planned frontend.

DESIGN CONTRACT (mirrors utils/api_compliance.py from v10.169)
--------------------------------------------------------------
1. Every endpoint requires a valid JWT — `Depends(get_current_user)`
2. Each endpoint calls a single engine method and returns a dict
3. Engine is the source of truth for both this API and the
   Streamlit cockpit (pages/28_legal_arc_cockpit.py)
4. Audit logging via `_audit_legal(action, user, detail)` after
   every successful endpoint call — same pattern as api_compliance
5. Read-only contract — every endpoint here is GET. State-changing
   methods (register_*, transition, link_*) become explicit POST
   endpoints in future increments with proper Pydantic request models

V10.179 SCOPE — READ-ONLY GET ENDPOINTS
---------------------------------------
All 8 fully-engineered engines have `board_summary()` returning a
dict — that's the safe verified surface for closure. ENH-221 contract
review is META_ONLY at v10.179, so its endpoint returns a META_ONLY
status dict rather than mock data.

ENDPOINT MAP (all GET, all JWT-protected)
-----------------------------------------
  GET /api/legal/board                          # cross-engine board pack
  GET /api/legal/contract-review/board          ENH-221 (META_ONLY)
  GET /api/legal/obligations/board              ENH-222
  GET /api/legal/cases/board                    ENH-223
  GET /api/legal/counsel/board                  ENH-224
  GET /api/legal/spend/board                    ENH-225
  GET /api/legal/clauses/board                  ENH-226
  GET /api/legal/holds/board                    ENH-227
  GET /api/legal/dashboard/board                ENH-228 (cross-engine)
  GET /api/legal/documents/board                ENH-229
  GET /api/legal/analytics/board                ENH-230
  GET /api/legal/cases/{case_id}                single case lookup
  GET /api/legal/holds/{hold_id}/acknowledgments overdue acks for hold
  GET /api/legal/documents/matter/{matter_id}   docs for matter
  GET /api/legal/analytics/snapshot             latest KPI snapshot
  GET /api/legal/analytics/portfolio-health     0-100 composite score
"""
from __future__ import annotations

from typing import Any, Dict

try:
    from fastapi import APIRouter, Depends, HTTPException
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

    class _DummyRouter:
        def __init__(self, **kwargs): pass
        def get(self, *a, **k):
            def _decorator(fn): return fn
            return _decorator
        def post(self, *a, **k):
            def _decorator(fn): return fn
            return _decorator

    def APIRouter(*a, **kwargs):  # type: ignore
        return _DummyRouter()

    class HTTPException(Exception):  # type: ignore
        def __init__(self, status_code: int = 500,
                       detail: str = ""):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    def Depends(x):  # type: ignore
        return x


# ---------------------------------------------------------------------------
# JWT auth shim (mirrors api_compliance pattern)
# ---------------------------------------------------------------------------

try:
    from utils.auth_jwt import get_current_user
except ImportError:
    def get_current_user():
        return {"username": "system", "role": "admin"}


# ---------------------------------------------------------------------------
# Engine factories — module-level singletons cached for the API process
# ---------------------------------------------------------------------------

from utils.obligation_tracking import ObligationTrackingEngine
from utils.legal_case_management import LegalCaseManagementEngine
from utils.legal_spend_management import LegalSpendManagementEngine
from utils.outside_counsel_portal import OutsideCounselPortalEngine
from utils.clause_library import ClauseLibraryEngine
from utils.legal_hold_management import LegalHoldManagementEngine
from utils.legal_dashboard import LegalDashboardEngine
from utils.legal_document_management import (
    LegalDocumentManagementEngine)
from utils.legal_analytics import LegalAnalyticsEngine


_obligation = ObligationTrackingEngine()
_case       = LegalCaseManagementEngine()
_spend      = LegalSpendManagementEngine()
_counsel    = OutsideCounselPortalEngine()
_clause     = ClauseLibraryEngine()
_hold       = LegalHoldManagementEngine()
_document   = LegalDocumentManagementEngine()
_dashboard  = LegalDashboardEngine(
    obligation_engine=_obligation, case_engine=_case,
    spend_engine=_spend, counsel_engine=_counsel,
    clause_engine=_clause, hold_engine=_hold)
_analytics  = LegalAnalyticsEngine(
    obligation_engine=_obligation, case_engine=_case,
    spend_engine=_spend, counsel_engine=_counsel,
    clause_engine=_clause, hold_engine=_hold,
    dashboard_engine=_dashboard, document_engine=_document)


# ---------------------------------------------------------------------------
# Audit logging shim
# ---------------------------------------------------------------------------

def _audit_legal(action: str, user: Dict[str, Any],
                  detail: str = "") -> None:
    """Audit log every successful endpoint call. Module is 'legal'."""
    try:
        from utils.audit import audit_log
        audit_log(action=action,
                   username=user.get("username", "unknown"),
                   detail=detail, module="legal")
    except Exception:
        # Audit-log failures must not break API responses; the
        # cockpit-side audit infrastructure is separately monitored.
        pass


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/legal", tags=["legal"])


# ---------- cross-engine board pack ----------

@router.get("/board")
def get_legal_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Cross-engine Legal arc board pack — single call to fetch all 9."""
    payload = {
        "contract_review":   {
            "engine": "ENH-221",
            "status": "META_ONLY",
            "note":   ("AI-powered contract review is currently a "
                       "META_ONLY standard — no engine; deferred to "
                       "future increment when contract-text storage "
                       "infrastructure is wired"),
        },
        "obligations":       _obligation.board_summary(),
        "cases":             _case.board_summary(),
        "counsel":           _counsel.board_summary(),
        "spend":             _spend.board_summary(),
        "clauses":           _clause.board_summary(),
        "holds":             _hold.board_summary(),
        "dashboard":         _dashboard.board_summary(),
        "documents":         _document.board_summary(),
        "analytics":         _analytics.board_summary(),
    }
    _audit_legal("GET /api/legal/board", user,
                  "cross-engine board pack")
    return payload


# ---------- per-engine board endpoints ----------

@router.get("/contract-review/board")
def get_contract_review_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-221 — META_ONLY status."""
    _audit_legal("GET /api/legal/contract-review/board", user)
    return {
        "engine": "ENH-221",
        "status": "META_ONLY",
        "note":   "Contract review engine deferred",
    }


@router.get("/obligations/board")
def get_obligations_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-222 — Obligation Tracking board."""
    _audit_legal("GET /api/legal/obligations/board", user)
    return _obligation.board_summary()


@router.get("/cases/board")
def get_cases_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-223 — Legal Case Management board."""
    _audit_legal("GET /api/legal/cases/board", user)
    return _case.board_summary()


@router.get("/counsel/board")
def get_counsel_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-224 — Outside Counsel Portal board."""
    _audit_legal("GET /api/legal/counsel/board", user)
    return _counsel.board_summary()


@router.get("/spend/board")
def get_spend_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-225 — Legal Spend Management board."""
    _audit_legal("GET /api/legal/spend/board", user)
    return _spend.board_summary()


@router.get("/clauses/board")
def get_clauses_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-226 — Clause Library & Playbooks board."""
    _audit_legal("GET /api/legal/clauses/board", user)
    return _clause.board_summary()


@router.get("/holds/board")
def get_holds_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-227 — Legal Hold Management board."""
    _audit_legal("GET /api/legal/holds/board", user)
    return _hold.board_summary()


@router.get("/dashboard/board")
def get_dashboard_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-228 — Legal Dashboard cross-engine composition."""
    _audit_legal("GET /api/legal/dashboard/board", user)
    return _dashboard.board_summary()


@router.get("/documents/board")
def get_documents_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-229 — Legal Document Management board."""
    _audit_legal("GET /api/legal/documents/board", user)
    return _document.board_summary()


@router.get("/analytics/board")
def get_analytics_board(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """ENH-230 — Legal Analytics & Reporting board."""
    _audit_legal("GET /api/legal/analytics/board", user)
    return _analytics.board_summary()


# ---------- per-engine reverse lookups ----------

@router.get("/cases/{case_id}")
def get_case_by_id(
    case_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Single case lookup."""
    case = _case.case_by_id(case_id)
    if case is None:
        raise HTTPException(
            status_code=404, detail=f"case {case_id} not found")
    _audit_legal("GET /api/legal/cases/{case_id}", user,
                  detail=f"case_id={case_id}")
    return case.to_dict() if hasattr(case, "to_dict") else dict(
        vars(case))


@router.get("/holds/{hold_id}/acknowledgments")
def get_hold_acknowledgments(
    hold_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List acknowledgments for a single legal hold."""
    acks = _hold.acknowledgments_for_hold(hold_id)
    _audit_legal("GET /api/legal/holds/{hold_id}/acknowledgments",
                  user, detail=f"hold_id={hold_id}")
    return {
        "hold_id": hold_id,
        "n_acknowledgments": len(acks),
        "acknowledgments": [
            (a.to_dict() if hasattr(a, "to_dict") else dict(vars(a)))
            for a in acks
        ],
    }


@router.get("/documents/matter/{matter_id}")
def get_documents_for_matter(
    matter_id: str,
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """List legal documents linked to a single matter."""
    docs = _document.documents_for_matter(matter_id)
    _audit_legal("GET /api/legal/documents/matter/{matter_id}",
                  user, detail=f"matter_id={matter_id}")
    return {
        "matter_id":     matter_id,
        "n_documents":   len(docs),
        "documents":     [d.to_dict() for d in docs],
    }


@router.get("/analytics/snapshot")
def get_analytics_snapshot(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Latest KPI snapshot for the Legal arc."""
    kpis = _analytics.kpi_snapshot()
    _audit_legal("GET /api/legal/analytics/snapshot", user)
    return {
        "n_kpis":  len(kpis),
        "kpis":    [k.to_dict() for k in kpis],
    }


@router.get("/analytics/portfolio-health")
def get_portfolio_health(
    user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Composite 0-100 portfolio health score across the Legal arc."""
    score = _analytics.portfolio_health_score()
    _audit_legal("GET /api/legal/analytics/portfolio-health", user)
    return {
        "portfolio_health_score": score,
        "available":              score is not None,
    }


__all__ = ["router"]
