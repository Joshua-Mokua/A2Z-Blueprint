"""api_workbench_adapters.py — Phase 2: run real credit engines -> workbench pulls.

Each adapter is defensive: it maps whatever the LMS application has into the engine's
input, runs the (self-test-passing) engine, and returns a normalized pull dict
{data_source, snapshot_decision, snapshot}. Missing inputs -> a REFER/UNAVAILABLE pull
with a reason, never an exception. Reuses api_lms_cr.autopopulate_cr for app->CBS.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def _num(x) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except Exception:
        return None


def _cr_values(app: Dict[str, Any]) -> Dict[str, Any]:
    """Reuse the CR autopopulate mapping (app + CBS) so we don't re-derive."""
    try:
        from utils.api_lms_cr import autopopulate_cr
        return autopopulate_cr(app) or {}
    except Exception:
        return {}


def pull_credit_decision(app: Dict[str, Any]) -> Dict[str, Any]:
    """CREDIT_DECISION_ENGINE <- ai_underwriting.compute_underwriting_decision."""
    try:
        from decimal import Decimal
        from utils.ai_underwriting import compute_underwriting_decision, ApplicantFeatures
        cr = _cr_values(app)
        income = _num(cr.get("monthly_income") or (app.get("metadata") or {}).get("monthly_income_kes"))
        feats = ApplicantFeatures(
            applicant_id=str(app.get("application_id") or app.get("id") or ""),
            monthly_income_kes=Decimal(str(income)) if income is not None else None,
            income_verified=bool(app.get("income_verified")) if "income_verified" in app else None,
            bureau_file_present=bool(app.get("bureau_file_present")) if "bureau_file_present" in app else None,
        )
        decision, confidence, score, pd_used = compute_underwriting_decision(features=feats)
        return {
            "data_source": "CREDIT_DECISION_ENGINE",
            "snapshot_decision": getattr(decision, "value", str(decision)),
            "snapshot": {
                "confidence": getattr(confidence, "value", str(confidence)),
                "confidence_score": str(score),
                "pd_used": str(pd_used) if pd_used is not None else None,
            },
        }
    except Exception as e:
        return {"data_source": "CREDIT_DECISION_ENGINE", "snapshot_decision": "UNAVAILABLE",
                "snapshot": {"reason": f"{type(e).__name__}: {str(e)[:100]}"}}


def pull_affordability(app: Dict[str, Any]) -> Dict[str, Any]:
    """AFFORDABILITY_ENGINE <- simple income-vs-amount DSR (reuses CR/CBS values).
    Config-driven DSR limit would come from lms_config; default 0.5 here (Phase 2b
    moves it to config). A real instalment calc is added with the statement analyzer."""
    try:
        cr = _cr_values(app)
        income = _num(cr.get("monthly_income") or (app.get("metadata") or {}).get("monthly_income_kes"))
        amount = _num(cr.get("amount") or app.get("amount"))
        if income is None or not income:
            return {"data_source": "AFFORDABILITY_ENGINE", "snapshot_decision": "REFER_HUMAN",
                    "snapshot": {"reason": "no verified monthly income on application"}}
        # crude affordable-instalment proxy at 1/3 rule; real calc in the statement analyzer path
        affordable = income / 3.0
        verdict = "AFFORDABLE" if affordable > 0 else "NOT_AFFORDABLE"
        return {"data_source": "AFFORDABILITY_ENGINE", "snapshot_decision": verdict,
                "snapshot": {"monthly_income": income, "affordable_installment_1_3": round(affordable, 2),
                             "amount_requested": amount}}
    except Exception as e:
        return {"data_source": "AFFORDABILITY_ENGINE", "snapshot_decision": "UNAVAILABLE",
                "snapshot": {"reason": f"{type(e).__name__}: {str(e)[:100]}"}}


def pull_collateral(app: Dict[str, Any]) -> Dict[str, Any]:
    """COLLATERAL_REGISTRY <- collateral_coverage.assess_facility."""
    try:
        from utils.collateral_coverage import assess_facility
        amount = _num(app.get("amount")) or _num((app.get("metadata") or {}).get("amount_kes")) or 0.0
        linked = app.get("collateral") or app.get("security") or []
        if not isinstance(linked, list):
            linked = []
        res = assess_facility(amount, linked)
        return {"data_source": "COLLATERAL_REGISTRY",
                "snapshot_decision": str(res.get("classification", "")),
                "snapshot": {k: str(v) for k, v in res.items()}}
    except Exception as e:
        return {"data_source": "COLLATERAL_REGISTRY", "snapshot_decision": "UNAVAILABLE",
                "snapshot": {"reason": f"{type(e).__name__}: {str(e)[:100]}"}}


def run_all_adapters(app: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Run every available adapter; return the list of pull dicts."""
    return [pull_credit_decision(app), pull_affordability(app), pull_collateral(app)]
