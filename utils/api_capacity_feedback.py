"""FastAPI Router — Capacity Feedback (v10.412, E6).

Exposes utils/capacity_feedback_engine.py over HTTP for React SPA consumption.

Endpoints (all JWT-protected per existing api.py middleware):

  GET    /api/cascade/capacity-feedback                  → list all
  GET    /api/cascade/capacity-feedback?period=2026      → filtered
  GET    /api/cascade/capacity-feedback?manager_code=X   → for one manager
  GET    /api/cascade/capacity-feedback/kpi/{kpi}/{manager_code}/{period}
                                                          → inline warnings
  POST   /api/cascade/capacity-feedback                  → submit new
  PATCH  /api/cascade/capacity-feedback/{id}/status      → manager resolves
  DELETE /api/cascade/capacity-feedback/{id}             → staff withdraws

This router is DEFINED here but mounted into the main FastAPI app in
v10.413 (E7 Cascade API & Exports) batch — keeping v10.412 single-
concern. The router can be imported and used standalone for testing.

Pydantic models match the dataclass shape in capacity_feedback_engine.

Shipped: v10.412 (definition); mounting in v10.413.
"""
from __future__ import annotations

from typing import List, Optional

try:
    from fastapi import APIRouter, HTTPException, Query
    from pydantic import BaseModel
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False
    APIRouter = None
    HTTPException = None
    Query = None
    BaseModel = object  # type: ignore

from utils.capacity_feedback_engine import (
    CONSTRAINT_TYPES,
    FEEDBACK_STATUSES,
    submit_feedback,
    list_feedback,
    feedback_for_kpi,
    update_status,
    delete_feedback,
)


# ════════════════════════════════════════════════════════════════════
# Pydantic models (request/response shapes)
# ════════════════════════════════════════════════════════════════════

if _FASTAPI_AVAILABLE:

    class CapacityFeedbackOut(BaseModel):
        """Response shape — mirrors CapacityFeedback dataclass."""
        id: str
        staff_code: str
        staff_name: str
        manager_code: str
        manager_name: str
        period: str
        kpi: str
        constraint_type: str
        constraint_value: str
        suggested_target_max: Optional[float] = None
        rationale: str
        status: str
        raised_at: str
        resolved_at: Optional[str] = None
        resolved_by: Optional[str] = None
        response: Optional[str] = None
        history: List[dict] = []

    class CapacityFeedbackSubmit(BaseModel):
        """POST request body for new feedback."""
        staff_code: str
        period: str
        kpi: str
        constraint_type: str
        constraint_value: str
        rationale: str
        suggested_target_max: Optional[float] = None

    class StatusUpdate(BaseModel):
        """PATCH request body for status change."""
        status: str
        response: str
        resolved_by: str


    # ════════════════════════════════════════════════════════════════════
    # Router
    # ════════════════════════════════════════════════════════════════════

    router = APIRouter(
        prefix="/api/cascade/capacity-feedback",
        tags=["cascade", "capacity-feedback"],
    )


    @router.get("", response_model=List[CapacityFeedbackOut])
    def list_capacity_feedback(
        period: Optional[str] = Query(None, description="Filter by period e.g. '2026'"),
        manager_code: Optional[str] = Query(None, description="Filter by recipient manager"),
        staff_code: Optional[str] = Query(None, description="Filter by raiser staff"),
        kpi: Optional[str] = Query(None, description="Filter by KPI id"),
        status: Optional[str] = Query(None, description="Filter by status"),
    ):
        """List capacity feedback with optional filters.

        Returns ALL feedback by default. Filter via query params.
        """
        rows = list_feedback(
            period=period, manager_code=manager_code,
            staff_code=staff_code, kpi=kpi, status=status,
        )
        return [r.to_json() for r in rows]


    @router.get(
        "/kpi/{kpi}/{manager_code}/{period}",
        response_model=List[CapacityFeedbackOut],
    )
    def inline_warnings(kpi: str, manager_code: str, period: str):
        """Inline warnings for Set team targets — open feedback only.

        Used by the manager UI when allocating a target for KPI X to
        their team: surfaces any open constraints raised by team
        members about that KPI.
        """
        rows = feedback_for_kpi(manager_code, kpi, period, open_only=True)
        return [r.to_json() for r in rows]


    @router.post("", response_model=CapacityFeedbackOut, status_code=201)
    def submit_capacity_feedback(body: CapacityFeedbackSubmit):
        """Staff raises a new capacity feedback.

        Validates constraint_type against CONSTRAINT_TYPES.
        """
        if body.constraint_type not in CONSTRAINT_TYPES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"constraint_type must be one of {list(CONSTRAINT_TYPES)}; "
                    f"got {body.constraint_type!r}"
                ),
            )
        try:
            fb = submit_feedback(
                staff_code=body.staff_code,
                period=body.period,
                kpi=body.kpi,
                constraint_type=body.constraint_type,
                constraint_value=body.constraint_value,
                rationale=body.rationale,
                suggested_target_max=body.suggested_target_max,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return fb.to_json()


    @router.patch(
        "/{feedback_id}/status",
        response_model=CapacityFeedbackOut,
    )
    def patch_status(feedback_id: str, body: StatusUpdate):
        """Manager updates the status of a feedback.

        Valid statuses: Open / Acknowledged / Accepted / Rejected / Resolved.
        """
        if body.status not in FEEDBACK_STATUSES:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"status must be one of {list(FEEDBACK_STATUSES)}; "
                    f"got {body.status!r}"
                ),
            )
        try:
            updated = update_status(
                feedback_id=feedback_id,
                status=body.status,
                response=body.response,
                resolved_by=body.resolved_by,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if not updated:
            raise HTTPException(status_code=404,
                                detail=f"Feedback {feedback_id} not found")
        return updated.to_json()


    @router.delete("/{feedback_id}", status_code=204)
    def delete_capacity_feedback(feedback_id: str, by: str = "system"):
        """Staff withdraws their own feedback (or admin deletes)."""
        ok = delete_feedback(feedback_id, by)
        if not ok:
            raise HTTPException(status_code=404,
                                detail=f"Feedback {feedback_id} not found")
        return None

else:
    # FastAPI not installed — router unavailable but module loads
    router = None
