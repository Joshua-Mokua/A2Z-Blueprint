"""utils/api_lms_models.py — Pydantic models for the Loan Application
(LMS) domain.

Authored v10.515 Phase 3 Arc α Batch α8 — LMS API.

Purpose
-------
Defines the data contract for the FastAPI surface that exposes
LoanApplicationManager (in utils/core.py:5267) to consumers (notably
the React frontend). Mirrors the shape of api_pipeline_models.py for
the pipeline domain.

Doctrine context
----------------
"Streamlit stays, React additive, FastAPI canonical." Both presentation
layers consume the same LoanApplicationManager. This module just
documents the contract that the new API endpoints expose.

Strictness
----------
Models declare fields with sensible types but accept extra fields
(`extra="allow"`) so future additions to the underlying JSON shape
don't break the response serialization.

Field shape
-----------
Verified same-turn against data/loan_applications.json record 0 at
commit `ac260b5` plus the LoanApplicationManager method set
(create_from_pipeline_deal, update, submit_to_credit, record_decision)
at utils/core.py:5267-5485.
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# ─────────────────────────────────────────────────────────────────────
# LoanApplication — the canonical application record shape
# ─────────────────────────────────────────────────────────────────────


class LoanApplication(BaseModel):
    """A single loan application as produced/maintained by
    LoanApplicationManager.

    Field naming follows the data file (data/loan_applications.json)
    — the LoanApplicationManager IS the canonical writer, so the file
    shape and the API shape are identical by construction.
    """

    model_config = ConfigDict(
        extra="allow",
        populate_by_name=True,
    )

    # ── Identity ──
    id: str = Field(description="LMS-assigned ID, format 'LMS#####'")
    pipeline_deal_id: Optional[str] = Field(
        default=None,
        description="Source pipeline deal id if created via α4 handoff. "
                    "Null for applications created outside the pipeline flow."
    )

    # ── Customer ──
    client_name: str = Field(description="Customer display name")
    client_cif: Optional[str] = Field(
        default=None,
        description="CBS customer identifier"
    )

    # ── Money ──
    amount: Optional[float] = Field(
        default=None,
        description="Application amount in canonical currency"
    )
    currency: Optional[str] = Field(default=None, description="ISO currency code")

    # ── Product ──
    product: Optional[str] = Field(
        default=None,
        description="Loan product name (e.g. 'Personal Loan', "
                    "'Business Loan', 'Mortgage')"
    )
    swim_lane: Optional[str] = Field(
        default=None,
        description="Express | Standard | Complex — set by α4 handoff "
                    "based on amount bands (≤5M Express, ≥100M Complex, "
                    "Standard between)"
    )

    # ── Status / lifecycle ──
    status: str = Field(
        description="Current lifecycle status. Lowercase string. "
                    "Common values: submitted | assigned | approved | "
                    "declined | returned | credit_admin | disbursed. "
                    "Strict enum validation deferred — see "
                    "PIPELINE_DOMAIN_AUDIT Section 18.5."
    )
    application_date: Optional[str] = Field(
        default=None,
        description="ISO date YYYY-MM-DD"
    )
    last_updated: Optional[str] = Field(
        default=None,
        description="ISO date YYYY-MM-DD"
    )

    # ── Ownership (RM-side) ──
    rm_code: Optional[str] = Field(
        default=None,
        description="Originating RM staff code"
    )
    rm_name: Optional[str] = Field(default=None)
    rm_unit: Optional[str] = Field(default=None)

    # ── Ownership (Analyst-side) ──
    # The analyst is a nested dict {code, name} when assigned, None otherwise.
    # Modelled as Dict[str, Any] for forward-compatibility (the underlying
    # data may add fields like assigned_date in future).
    analyst: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Assigned credit analyst: {code, name} when assigned; "
                    "null when application is still 'submitted'."
    )

    # ── Decision (post-review) ──
    # Set by LoanApplicationManager.record_decision. Nested dict shape:
    # {verdict, date, authority, reason, conditions, comments}
    decision: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Decision record set by record_decision endpoint. "
                    "Null until a manager records approve/decline/return."
    )

    # ── Underwriting flags ──
    is_repeat_borrower: Optional[bool] = Field(default=None)
    clean_repayment_history: Optional[bool] = Field(default=None)

    # ── Documentation ──
    docs_required: Optional[List[str]] = Field(
        default=None,
        description="List of document types required for this app"
    )
    docs_submitted: Optional[List[str]] = Field(
        default=None,
        description="List of document types received"
    )
    completeness_score: Optional[float] = Field(
        default=None,
        description="0-100 percentage of docs submitted vs required"
    )

    # ── Compliance ──
    compliance_flag: Optional[bool] = Field(
        default=None,
        description="True if compliance review flagged this application"
    )
    compliance_type: Optional[str] = Field(default=None)

    # ── SLA tracking ──
    tat_days: Optional[int] = Field(
        default=None,
        description="Turnaround days elapsed since submission"
    )
    sla_target_days: Optional[int] = Field(
        default=None,
        description="Days target before SLA breach"
    )

    # ── Categorization ──
    proposition_tag: Optional[str] = Field(
        default=None,
        description="Customer/product proposition tag (e.g. 'SME', 'Premium')"
    )
    deal_category: Optional[str] = Field(
        default=None,
        description="e.g. 'New Facility', 'Top-up', 'Renewal'"
    )

    # ── Provenance (α4 added) ──
    created_by: Optional[str] = Field(
        default=None,
        description="Username of the creator if created via the API "
                    "handoff (α4). Empty for legacy records."
    )
    created_via: Optional[str] = Field(
        default=None,
        description="e.g. 'api_pipeline_advance' for α4-handoff-created records"
    )

    # ── Free text ──
    appraisal_notes: Optional[str] = Field(default=None)


# ─────────────────────────────────────────────────────────────────────
# List response (GET /api/lms/applications)
# ─────────────────────────────────────────────────────────────────────


class LoanApplicationsResponse(BaseModel):
    """Response shape for GET /api/lms/applications."""
    model_config = ConfigDict(extra="allow")

    applications: List[LoanApplication]
    count: int
    source: str = Field(
        description="'loan_application_manager' (canonical) or "
                    "future PG-backed source"
    )


# ─────────────────────────────────────────────────────────────────────
# Per-application permissions object (mirrors pipeline pattern)
# ─────────────────────────────────────────────────────────────────────


class LoanApplicationPermissions(BaseModel):
    """Caller-vs-application permission flags.

    Drives React UI control visibility. The server enforces these
    on every mutation endpoint regardless of what the UI displays.
    """
    model_config = ConfigDict(extra="allow")

    can_view: bool = Field(description="Caller can fetch detail")
    can_update: bool = Field(
        description="Caller can PUT field updates (subject to status "
                    "guardrail: status must be submitted|assigned)"
    )
    can_assign: bool = Field(
        description="Caller can POST to /assign (manager-tier only)"
    )
    can_record_decision: bool = Field(
        description="Caller can POST to /decision (manager-tier only)"
    )


# ─────────────────────────────────────────────────────────────────────
# Detail response (GET /api/lms/applications/{id})
# ─────────────────────────────────────────────────────────────────────


class LoanApplicationDetailResponse(BaseModel):
    """Response shape for GET /api/lms/applications/{app_id}."""
    model_config = ConfigDict(extra="allow")

    application: LoanApplication
    permissions: LoanApplicationPermissions
    source: str


# ─────────────────────────────────────────────────────────────────────
# Mutation request models
# ─────────────────────────────────────────────────────────────────────


class AssignAnalystRequest(BaseModel):
    """Request body for POST /api/lms/applications/{id}/assign.

    Manager-tier authorization required at endpoint. Status must be
    'submitted' (no re-assignment of already-assigned applications).
    """
    model_config = ConfigDict(extra="allow")

    analyst_code: str = Field(
        min_length=1,
        description="Staff code of the analyst being assigned"
    )
    analyst_name: str = Field(
        min_length=1,
        description="Display name of the analyst"
    )


class LoanAppUpdateRequest(BaseModel):
    """Request body for PUT /api/lms/applications/{id}.

    Partial update — all fields optional, absent keys not touched.
    Status guardrail: application status must be 'submitted' or
    'assigned' for update to be permitted (enforced at endpoint).

    Deliberately omitted from this model (NOT updatable via PUT):
    id, pipeline_deal_id, amount, product, currency, application_date,
    rm_code, rm_name, rm_unit, status, analyst, decision, swim_lane,
    last_updated. Those are either immutable identity fields, set at
    creation only, or maintained via dedicated endpoints (assign,
    decision).
    """
    model_config = ConfigDict(extra="allow")

    docs_submitted: Optional[List[str]] = Field(
        default=None,
        description="Replace docs_submitted list (full replacement, not merge)"
    )
    docs_required: Optional[List[str]] = Field(
        default=None,
        description="Replace docs_required list"
    )
    completeness_score: Optional[float] = Field(
        default=None,
        description="0-100 percentage"
    )
    compliance_flag: Optional[bool] = Field(default=None)
    compliance_type: Optional[str] = Field(default=None)
    appraisal_notes: Optional[str] = Field(default=None)
    is_repeat_borrower: Optional[bool] = Field(default=None)
    clean_repayment_history: Optional[bool] = Field(default=None)


class RecordDecisionRequest(BaseModel):
    """Request body for POST /api/lms/applications/{id}/decision.

    Manager-tier authorization required at endpoint. Status must be
    'submitted' or 'assigned' for decision recording to be permitted.

    Verdict is case-insensitive — 'approve', 'approved', 'decline',
    'declined', 'return', 'returned' all accepted. Normalized at
    endpoint to canonical {'approved', 'declined', 'returned'}.
    """
    model_config = ConfigDict(extra="allow")

    verdict: str = Field(
        description="approve|approved | decline|declined | return|returned "
                    "(case-insensitive)"
    )
    authority: str = Field(
        min_length=1,
        description="Decision-maker role/title (e.g. 'Branch Manager', "
                    "'Credit Manager', 'Managing Director'). Recorded "
                    "on the decision block for audit trail."
    )
    reason: Optional[str] = Field(
        default="",
        description="Free-text reason. Especially useful for declined "
                    "and returned verdicts."
    )
    conditions: Optional[List[str]] = Field(
        default=None,
        description="List of conditions attached to the decision. "
                    "Typically used with approved verdict for "
                    "conditional approvals."
    )
    comments: Optional[str] = Field(
        default="",
        description="Manager comments visible to RM/analyst on returns "
                    "or queries."
    )


# ─────────────────────────────────────────────────────────────────────
# Mutation response (used by all 3 mutation endpoints)
# ─────────────────────────────────────────────────────────────────────


class LoanAppMutationResponse(BaseModel):
    """Response shape for POST /assign, PUT, POST /decision.

    Returns the full updated application record plus a status string
    indicating the operation type. Frontend uses status to dispatch
    UI feedback (e.g. toast message variant).
    """
    model_config = ConfigDict(extra="allow")

    application: LoanApplication
    status: str = Field(
        description="'assigned' | 'updated' | 'decision_approved' | "
                    "'decision_declined' | 'decision_returned'"
    )


# ─────────────────────────────────────────────────────────────────────
# Credit workflow request bodies (v10.584)
# ─────────────────────────────────────────────────────────────────────

class RequestInfoRequest(BaseModel):
    """POST /api/lms/applications/{id}/request-info — analyst asks the deal
    owner for more documentation (pre-decision)."""
    reasons: List[str] = Field(
        default_factory=list,
        description="Reason codes (typically from lms_config rework_reasons).")
    documents: List[str] = Field(
        default_factory=list,
        description="Specific documents requested.")
    note: str = Field(default="", description="Free-text context.")


class ProvideInfoRequest(BaseModel):
    """POST /api/lms/applications/{id}/provide-info — deal owner supplies the
    requested documentation; case returns to assigned."""
    documents: List[str] = Field(default_factory=list)
    note: str = Field(default="")


class SignOfferRequest(BaseModel):
    """POST /api/lms/applications/{id}/sign-offer — deal owner marks the
    letter of offer signed and attaches the signed copy."""
    note: str = Field(default="")
    attachment_filename: Optional[str] = Field(
        default=None, description="Signed-copy filename (reference mode).")
    attachment_ref: Optional[str] = Field(
        default=None, description="Storage ref/URL (file_upload mode).")


class ValidateOfferRequest(BaseModel):
    """POST /api/lms/applications/{id}/validate-offer — line manager
    validates the signed offer (checks & balances)."""
    approve: bool = Field(default=True,
                          description="False sends it back for re-handling.")
    note: str = Field(default="")


class ConfirmToCreditAdminRequest(BaseModel):
    """POST /api/lms/applications/{id}/confirm-to-credit-admin — analyst
    confirms to credit admin to proceed; creates the CALMS case."""
    note: str = Field(default="")


# ─────────────────────────────────────────────────────────────────────
# Committee voting request bodies (v10.586)
# ─────────────────────────────────────────────────────────────────────

class CommitteeVoteRequest(BaseModel):
    """POST /api/lms/applications/{id}/committee/vote — one member's vote."""
    member_id: str = Field(min_length=1, description="Charter member id (e.g. 'm1').")
    vote: str = Field(description="YES | NO | ABSTAIN | RECUSED")
    rationale: str = Field(default="")


class ResolveCommitteeRequest(BaseModel):
    """POST /api/lms/applications/{id}/committee/resolve — run the engine over
    the recorded votes and apply the outcome."""
    attending_member_ids: List[str] = Field(
        default_factory=list,
        description="Members present; defaults to everyone who voted.")
    note: str = Field(default="")
