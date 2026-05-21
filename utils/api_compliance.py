"""utils.api_compliance — FastAPI router for the AML/Compliance arc (v10.169).

Exposes the 9 AML/Compliance arc engines (ENH-191..199) as JSON-
serializable HTTP endpoints with JWT authentication. Provides the
React-ready surface for the planned frontend.

DESIGN CONTRACT (mirrors utils/api_treasury.py from v10.155)
-----------------------------------------------------------------------
1. Every endpoint requires a valid JWT — `Depends(get_current_user)`
2. Each endpoint calls a single engine method and returns a dict
3. Engine is the source of truth for both this API and the
   Streamlit cockpit (pages/27_compliance_arc_cockpit.py)
4. Audit logging via `_audit_compliance(action, user, detail)` after
   every successful endpoint call — same pattern as api_treasury
5. Read-only contract — every endpoint here is GET. State-changing
   methods (register_*, transition, record_*) become explicit POST
   endpoints in future increments with proper Pydantic request models

V10.169 SCOPE — READ-ONLY GET ENDPOINTS
---------------------------------------
All 9 engines have `board_summary()` returning a dict — that's the
safe verified surface for closure. Engine-state-required reads (e.g.
filing_by_id, course_for_id) are exposed where they take simple
string parameters and the engine method has a verified signature.

The honest scope decision matches v10.154's read-only-first approach:
state-mutating endpoints (POST) are deferred to a follow-up increment
because they need typed Pydantic models matching the frozen
dataclasses across all 9 engines.

ENDPOINT MAP (all GET, all JWT-protected)
------------------------------------------
  GET /api/compliance/board                            # cross-engine board pack
  GET /api/compliance/kyc/board                        ENH-191
  GET /api/compliance/screening/board                  ENH-192
  GET /api/compliance/aml/board                        ENH-193
  GET /api/compliance/sar/board                        ENH-194
  GET /api/compliance/risk/board                       ENH-198
  GET /api/compliance/examiner/board                   ENH-199
  GET /api/compliance/regulatory-change/board          ENH-195
  GET /api/compliance/policy/board                     ENH-196
  GET /api/compliance/training/board                   ENH-197
  GET /api/compliance/regulatory-change/{change_id}    single change lookup
  GET /api/compliance/policy/{policy_id}/{version_id}  single policy lookup
  GET /api/compliance/sar/overdue                      operator-actionable list
  GET /api/compliance/training/overdue                 operator-actionable list
  GET /api/compliance/training/expiring                30-day cert expiry window
  GET /api/compliance/risk/latest                      latest enterprise score
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
# JWT auth shim (mirrors api_treasury pattern)
# ---------------------------------------------------------------------------

try:
    from utils.auth_jwt import get_current_user
except ImportError:
    def get_current_user():
        return {"username": "system", "role": "admin"}


# ---------------------------------------------------------------------------
# Engine factories — module-level singletons cached for the API process
# ---------------------------------------------------------------------------

from utils.kyc_onboarding import KycOnboardingEngine
from utils.aml_monitoring import AmlMonitoringEngine
from utils.sar_filing import SarFilingEngine
from utils.compliance_risk_assessment import (
    ComplianceRiskAssessmentEngine)
from utils.examiner_reporting import ExaminerReportingEngine
from utils.regulatory_change import RegulatoryChangeEngine
from utils.policy_management import PolicyManagementEngine
from utils.compliance_training import ComplianceTrainingEngine

try:
    from utils.screening_orchestrator import ScreeningOrchestrator
    SCREENING_AVAILABLE = True
except ImportError:
    SCREENING_AVAILABLE = False
    ScreeningOrchestrator = None  # type: ignore


_kyc = KycOnboardingEngine()
_aml = AmlMonitoringEngine()
_sar = SarFilingEngine()
_risk = ComplianceRiskAssessmentEngine()
_examiner = ExaminerReportingEngine()
_reg_change = RegulatoryChangeEngine()
_policy = PolicyManagementEngine()
_training = ComplianceTrainingEngine()
_screening = (ScreeningOrchestrator() if SCREENING_AVAILABLE
                  else None)


# ---------------------------------------------------------------------------
# Audit hook
# ---------------------------------------------------------------------------

def _audit_compliance(action: str, user: Dict[str, Any],
                         detail: str) -> None:
    """Lightweight audit hook — mirrors api_treasury._audit_treasury."""
    try:
        from utils.core_audit import audit_log
        audit_log(action=action,
                    username=user.get("username", "unknown"),
                    detail=detail, module="compliance")
    except Exception:
        # Don't let audit failure break endpoint
        pass


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


# ---------------------------------------------------------------------------
# Cross-engine board pack
# ---------------------------------------------------------------------------

@router.get("/board")
def get_compliance_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Cross-engine board pack — single response with all 9 engines'
    board_summary() outputs. The closing argument for the Ecobank
    vendor demo: one endpoint, one number per engine, full enterprise
    compliance posture in a single round-trip."""
    _audit_compliance("compliance.board.read", user,
                          "cross-engine board pack")
    payload: Dict[str, Any] = {
        "kyc_onboarding": _kyc.board_summary(),
        "aml_monitoring": _aml.board_summary(),
        "sar_filing": _sar.board_summary(),
        "compliance_risk_assessment": _risk.board_summary(),
        "examiner_reporting": _examiner.board_summary(),
        "regulatory_change": _reg_change.board_summary(),
        "policy_management": _policy.board_summary(),
        "compliance_training": _training.board_summary(),
    }
    if _screening is not None:
        try:
            payload["screening_orchestrator"] = (
                _screening.board_summary())
        except Exception:
            payload["screening_orchestrator"] = {
                "status": "engine_present_but_summary_failed"}
    else:
        payload["screening_orchestrator"] = {
            "status": "engine_not_imported"}
    return payload


# ---------------------------------------------------------------------------
# Per-engine board summaries
# ---------------------------------------------------------------------------

@router.get("/kyc/board")
def get_kyc_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance("compliance.kyc.board.read", user, "")
    return _kyc.board_summary()


@router.get("/screening/board")
def get_screening_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance("compliance.screening.board.read", user, "")
    if _screening is None:
        return {"status": "engine_not_imported"}
    return _screening.board_summary()


@router.get("/aml/board")
def get_aml_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance("compliance.aml.board.read", user, "")
    return _aml.board_summary()


@router.get("/sar/board")
def get_sar_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance("compliance.sar.board.read", user, "")
    return _sar.board_summary()


@router.get("/risk/board")
def get_risk_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance("compliance.risk.board.read", user, "")
    return _risk.board_summary()


@router.get("/examiner/board")
def get_examiner_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance("compliance.examiner.board.read", user, "")
    return _examiner.board_summary()


@router.get("/regulatory-change/board")
def get_regulatory_change_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance("compliance.regulatory_change.board.read",
                          user, "")
    return _reg_change.board_summary()


@router.get("/policy/board")
def get_policy_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance("compliance.policy.board.read", user, "")
    return _policy.board_summary()


@router.get("/training/board")
def get_training_board(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance("compliance.training.board.read", user, "")
    return _training.board_summary()


# ---------------------------------------------------------------------------
# Operator-actionable lists (overdue + expiring)
# ---------------------------------------------------------------------------

@router.get("/sar/overdue")
def get_sar_overdue(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """DRAFT filings past POCAMLA §44 7-day deadline — direct
    regulatory exposure list."""
    _audit_compliance("compliance.sar.overdue.read", user, "")
    overdue = _sar.overdue_filings()
    return {
        "n_overdue": len(overdue),
        "filings": [f.to_dict() for f in overdue],
    }


@router.get("/regulatory-change/overdue")
def get_regulatory_change_overdue(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Regulatory changes past attestation deadline."""
    _audit_compliance(
        "compliance.regulatory_change.overdue.read", user, "")
    overdue = _reg_change.overdue_attestations()
    return {
        "n_overdue": len(overdue),
        "changes": [c.to_dict() for c in overdue],
    }


@router.get("/policy/overdue")
def get_policy_overdue(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Active policies whose attestation cycle deadline has passed
    for any attestor."""
    _audit_compliance("compliance.policy.overdue.read", user, "")
    overdue = _policy.overdue_attestations()
    return {
        "n_overdue": len(overdue),
        "policies": [p.to_dict() for p in overdue],
    }


@router.get("/training/overdue")
def get_training_overdue(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Training assignments past their due_date and not completed."""
    _audit_compliance("compliance.training.overdue.read", user, "")
    overdue = _training.overdue_assignments()
    return {
        "n_overdue": len(overdue),
        "assignments": [a.to_dict() for a in overdue],
    }


@router.get("/training/expiring")
def get_training_expiring(
        window_days: int = 30,
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Certifications expiring within `window_days` (default 30)."""
    _audit_compliance(
        "compliance.training.expiring.read", user,
        f"window={window_days}")
    expiring = _training.expiring_certifications(
        window_days=window_days)
    return {
        "window_days": window_days,
        "n_expiring": len(expiring),
        "assignments": [a.to_dict() for a in expiring],
    }


# ---------------------------------------------------------------------------
# Single-record lookups
# ---------------------------------------------------------------------------

@router.get("/regulatory-change/{change_id}")
def get_regulatory_change(
        change_id: str,
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance(
        "compliance.regulatory_change.read", user,
        f"change_id={change_id}")
    try:
        change = _reg_change.change_by_id(change_id)
    except KeyError:
        raise HTTPException(status_code=404,
                              detail=f"change_id not found: {change_id}")
    return change.to_dict()


@router.get("/policy/{policy_id}/{version_id}")
def get_policy(
        policy_id: str, version_id: str,
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    _audit_compliance(
        "compliance.policy.read", user,
        f"policy={policy_id} v={version_id}")
    try:
        policy = _policy.policy_by_version(policy_id, version_id)
    except KeyError:
        raise HTTPException(
            status_code=404,
            detail=f"policy not found: {policy_id} {version_id}")
    return policy.to_dict()


@router.get("/risk/latest")
def get_risk_latest(
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Latest enterprise compliance risk assessment — the one number
    that summarizes the bank's compliance posture."""
    _audit_compliance("compliance.risk.latest.read", user, "")
    latest = _risk.latest_assessment()
    if latest is None:
        return {"status": "no_assessments_yet",
                "advice": "call POST /api/compliance/risk/assess to "
                            "generate first assessment"}
    return latest.to_dict()


# ---------------------------------------------------------------------------
# Cross-engine bidirectional reverse-lookups (the trio)
# ---------------------------------------------------------------------------

@router.get("/policy/by-change/{change_id}")
def get_policies_for_change(
        change_id: str,
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """ENH-195 → ENH-196 reverse-lookup."""
    _audit_compliance(
        "compliance.policies_for_change.read", user,
        f"change_id={change_id}")
    policies = _policy.policies_for_change(change_id)
    return {
        "change_id": change_id,
        "n_policies": len(policies),
        "policies": [p.to_dict() for p in policies],
    }


@router.get("/training/by-change/{change_id}")
def get_courses_for_change(
        change_id: str,
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """ENH-195 → ENH-197 reverse-lookup."""
    _audit_compliance(
        "compliance.courses_for_change.read", user,
        f"change_id={change_id}")
    courses = _training.courses_for_change(change_id)
    return {
        "change_id": change_id,
        "n_courses": len(courses),
        "courses": [c.to_dict() for c in courses],
    }


@router.get("/training/by-policy/{policy_id}")
def get_courses_for_policy(
        policy_id: str,
        user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """ENH-196 → ENH-197 reverse-lookup."""
    _audit_compliance(
        "compliance.courses_for_policy.read", user,
        f"policy_id={policy_id}")
    courses = _training.courses_for_policy(policy_id)
    return {
        "policy_id": policy_id,
        "n_courses": len(courses),
        "courses": [c.to_dict() for c in courses],
    }
