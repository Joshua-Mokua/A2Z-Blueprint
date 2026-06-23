"""utils/api_pipeline_models.py — Pydantic models for the canonical
pipeline domain (Generation B / PipelineManager-produced).

Authored v10.503 Phase 3 Arc α Batch α1 — Pipeline API Consolidation.

Purpose
-------
This module is the **single source of truth for the pipeline data
contract** that the FastAPI surface exposes. The Streamlit pages have
historically rendered `PipelineManager.get_deals()` output directly
(dict-typed, no schema). The API endpoints have historically read a
separate JSON file (`data/pipeline.json`) via `_load_json(...)`.

Batch α1 unifies these surfaces by routing both through PipelineManager.
This module then describes — non-strictly for now — what that shape
looks like to consumers (notably the React frontend being introduced
incrementally per `docs/architecture/REACT_READINESS_AUDIT.md`).

Doctrine context
----------------
**The architecture is "Streamlit stays, React additive, FastAPI
canonical."** Both presentation layers consume the same backend
services. This file is part of that canonical contract.

Strictness
----------
Models declare fields with sensible types but accept extra fields and
do not raise on validation failure during this batch. Strict validation
is a future-arc concern — once the data is verified to parse cleanly
across all deals, validators tighten.

Field shape
-----------
Verified same-turn against `PipelineManager().get_deals()[0]` at
commit `b2cf3a4` — the sandbox query returned 29 fields. Each field
below is documented with its presence basis.

References
----------
- `docs/architecture/PIPELINE_DOMAIN_AUDIT.md` Section 15 (deep
  anatomy) — explains why these are the canonical names.
- `utils/core.py:3896` — `PipelineManager.__init__` reads from
  `data/pipeline_deals.json`. After Batch α1 the API endpoints also
  read through this manager.
- `pages/3_pipeline.py:67` — `pm.get_deals()` is the canonical
  Streamlit consumer.
"""
from __future__ import annotations

from typing import List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict, AliasChoices


# ────────────────────────────────────────────────────────────────────
# PipelineDeal — the canonical deal record shape
# ────────────────────────────────────────────────────────────────────


class PipelineDeal(BaseModel):
    """A single pipeline deal as produced by PipelineManager.

    Field naming follows Generation B (the polished shape that
    PipelineManager.add_deal() produces). Generation A field names
    (amount/product/staff_name only) are explicitly NOT canonical
    here — they are legacy from `data/pipeline.json` which Batch α1
    eliminates from the API path.
    """

    model_config = ConfigDict(
        # Allow extra fields. PipelineManager records may carry
        # additional metadata (e.g. seed flags, audit breadcrumbs)
        # that we don't want to reject during this batch.
        extra="allow",
        # Use the field name (not alias) when serializing.
        populate_by_name=True,
    )

    # ── Identity ───────────────────────────────────────────────────
    id: str = Field(
        description="PipelineManager-assigned deal ID, format 'D####'"
    )
    client_name: str = Field(
        description="Customer display name"
    )
    client_cif: Optional[str] = Field(
        default=None,
        description="CBS customer identifier (CIF) if the deal client is matched in CBS",
    )

    # ── Money ──────────────────────────────────────────────────────
    # Canonical amount field is `deal_value` (NOT `amount`).
    # The 8 PipelineManager records sandbox-verified to have
    # deal_value populated and amount=None.
    deal_value: Optional[float] = Field(
        default=None,
        description="Deal amount in canonical currency (typically KES)"
    )
    currency: Optional[str] = Field(
        default=None,
        description="ISO currency code, typically KES"
    )

    # ── Product / categorisation ───────────────────────────────────
    # Canonical product field is `product_type` (NOT `product`).
    product_type: Optional[str] = Field(
        default=None,
        description="e.g. 'Business Loan', 'Personal Loan', 'CASA'"
    )
    pipeline_category: Optional[str] = Field(
        default=None,
        description=(
            "One of: 'Loan', 'Deposit', 'Account', 'Other'. "
            "Derived from product_type via get_pipeline_category()."
        )
    )

    # ── Stage / lifecycle ──────────────────────────────────────────
    stage: str = Field(
        description=(
            "Current pipeline stage. Should be one of "
            "PIPELINE_STAGES_LOAN/ACCOUNT/DEPOSIT/GENERIC depending on "
            "pipeline_category. Strict validation deferred."
        )
    )
    probability: Optional[float] = Field(
        default=None,
        description="Win probability 0-1 (or 0-100 historical)"
    )

    # ── Ownership ──────────────────────────────────────────────────
    # Canonical staff fields are staff_code + staff_name (NOT rm/rm_name).
    staff_code: Optional[str] = Field(
        default=None,
        description="Owning RM staff code (numeric string)"
    )
    staff_name: Optional[str] = Field(
        default=None,
        description="Owning RM display name"
    )
    unit: Optional[str] = Field(
        default=None,
        description="Branch / unit name"
    )

    # ── Customer relationship ──────────────────────────────────────
    client_type: Optional[str] = Field(
        default=None,
        description="'Individual' or 'Business'"
    )
    is_ntb: Optional[bool] = Field(
        default=None,
        description="True if New To Bank (no existing CBS relationship)"
    )
    account_number: Optional[str] = Field(
        default=None,
        description="CBS account number (for Existing customers only)"
    )

    # ── Portfolio conflict (3-path resolution per audit S15.4) ─────
    portfolio_owner_code: Optional[str] = Field(
        default=None,
        description="CBS-assigned RM code when conflict exists"
    )
    portfolio_owner_name: Optional[str] = Field(
        default=None,
        description="CBS-assigned RM name when conflict exists"
    )
    bsc_credit_to: Optional[str] = Field(
        default=None,
        description="Staff name receiving BSC credit on close (may be owner)"
    )

    # ── Action tracking ────────────────────────────────────────────
    next_action: Optional[str] = Field(default=None)
    next_action_date: Optional[str] = Field(
        default=None,
        description="ISO date string YYYY-MM-DD"
    )

    # ── Timestamps ─────────────────────────────────────────────────
    created_at: Optional[str] = Field(default=None)
    updated_at: Optional[str] = Field(default=None)
    updated_by: Optional[str] = Field(
        default=None,
        description="Username of last mutator"
    )
    expected_close: Optional[str] = Field(default=None)
    closed_date: Optional[str] = Field(default=None)

    # ── Notes / freeform ───────────────────────────────────────────
    notes: Optional[str] = Field(default=None)
    loss_reason: Optional[str] = Field(default=None)

    # ── Contact ────────────────────────────────────────────────────
    email: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    id_number: Optional[str] = Field(default=None)
    id_type: Optional[str] = Field(default=None)

    # ── Source / pipeline metadata ─────────────────────────────────
    source: Optional[str] = Field(
        default=None,
        description="'Referral' | 'Existing relationship' | 'Walk-in' | etc."
    )
    competitors: Optional[Any] = Field(default=None)

    # ── Manager validation gate (per audit S15.5) ──────────────────
    manager_validated: Optional[bool] = Field(default=None)


# ────────────────────────────────────────────────────────────────────
# Summary response — for /api/pipeline/summary
# ────────────────────────────────────────────────────────────────────


class PipelineByStage(BaseModel):
    """Per-stage aggregation row."""
    model_config = ConfigDict(extra="allow")

    stage: str
    deal_count: int
    total_value: float


class PipelineTotals(BaseModel):
    """Top-level pipeline totals."""
    model_config = ConfigDict(extra="allow")

    total_deals: int
    pipeline_value: float
    won_value: float
    lost_count: int


class PipelineSummaryResponse(BaseModel):
    """Response shape for GET /api/pipeline/summary."""
    model_config = ConfigDict(extra="allow")

    by_stage: List[PipelineByStage]
    totals: PipelineTotals
    source: str = Field(
        description="'postgresql' or 'pipeline_manager' "
                    "(formerly 'json')"
    )


# ────────────────────────────────────────────────────────────────────
# List response — for /api/pipeline/deals
# ────────────────────────────────────────────────────────────────────


class PipelineDealsResponse(BaseModel):
    """Response shape for GET /api/pipeline/deals."""
    model_config = ConfigDict(extra="allow")

    deals: List[PipelineDeal]
    count: int
    source: str


# ────────────────────────────────────────────────────────────────────
# Mutation request / response models (v10.505 Phase 3 Arc α Batch α3)
# ────────────────────────────────────────────────────────────────────
#
# POST/PUT/advance endpoints. Strictness profile:
# - PipelineDealCreate — required fields enforced by validator
# - PipelineDealUpdate — all optional (partial update semantics)
# - PipelineDealAdvance — new_stage required; note optional
#
# All accept extra=allow so callers can include the richer field set
# Streamlit collects (id_type, id_number, sector, etc.) without
# forcing the API to mirror every UI affordance.


class PipelineDealCreate(BaseModel):
    """Request body for POST /api/pipeline/deals.

    Required fields match REQUIRED_CREATE_FIELDS in
    utils/api_pipeline_mutations.py — kept in sync deliberately so
    the validation gate and the schema gate report the same surface.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # Required (validated at endpoint via validate_create_payload)
    client_name: str = Field(description="Customer display name")
    client_cif: Optional[str] = Field(
        default=None,
        description="CBS customer identifier (CIF) when the client is matched in CBS",
    )
    staff_code: Optional[str] = Field(
        default=None,
        description="Owning RM staff code. Optional on the wire: when omitted "
                    "the server derives it from the authenticated caller "
                    "(H1, 2026-06-14). Required value still enforced by "
                    "validate_create_payload after server-side injection.",
    )
    staff_name: Optional[str] = Field(
        default=None,
        description="Owning RM display name. Server-derived when omitted (H1).",
    )
    deal_value: float = Field(
        description="Deal amount in canonical currency (typically KES). "
                    "Must be non-negative."
    )
    product_type: str = Field(
        description="e.g. 'Business Loan', 'Personal Loan', 'CASA'"
    )
    stage: str = Field(
        description="Initial stage. Must be in ALLOWED_ADVANCE_STAGES "
                    "(LMS-handoff stages rejected in α3 — see α4)."
    )

    # Optional but commonly supplied
    client_type: Optional[str] = Field(
        default=None, description="'Individual' or 'Business'"
    )
    segment: Optional[str] = Field(
        default=None,
        description="Customer segment within the client type — e.g. "
                    "Affluent / Core Middle / Mass-Retail (Individual) or "
                    "Large Corporate / Corporate / SME / Micro (Business). "
                    "Options come from core.CUSTOMER_SEGMENTS (admin config).",
    )
    sector: Optional[str] = Field(
        default=None,
        description="Economic sector — for BUSINESS clients, the CBK "
                    "classification from pipeline_settings.business_sectors. "
                    "Empty for Individual clients (see mou_id).",
    )
    mou_id: Optional[str] = Field(
        default=None,
        description="For INDIVIDUAL clients: the partnership/MOU id from the "
                    "active register (data/partnerships_mous.json).",
    )
    mou_title: Optional[str] = Field(
        default=None,
        description="Display title of the selected MOU (or free-text partner "
                    "name when 'Other' is chosen).",
    )
    is_ntb: Optional[bool] = Field(
        default=None, description="True if New To Bank"
    )
    # Top-up (P4-credit): an increase on an EXISTING facility. When is_top_up is
    # true, the deal's pipeline value reflects ONLY the increment (top_up_amount)
    # — the original facility is recorded for context but excluded from pipeline
    # value (the bank's new commitment is just the top-up). Enforced in
    # validate_create_payload + applied at create (deal_value := top_up_amount).
    is_top_up: Optional[bool] = Field(
        default=None, description="True if this deal tops up an existing facility."
    )
    top_up_amount: Optional[float] = Field(
        default=None,
        description="The increment being added (becomes the deal's pipeline "
                    "value when is_top_up). Must be > 0 for a top-up.",
    )
    original_facility_amount: Optional[float] = Field(
        default=None,
        description="The existing facility's size (context only — NOT counted in "
                    "pipeline value). Should be >= top_up_amount.",
    )
    existing_facility_id: Optional[str] = Field(
        default=None,
        description="Identifier of the facility being topped up (optional).",
    )
    pipeline_category: Optional[str] = Field(default=None)
    probability: Optional[float] = Field(default=None)
    next_action: Optional[str] = Field(default=None)
    next_action_date: Optional[str] = Field(default=None)
    expected_close: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)
    source: Optional[str] = Field(default=None)
    unit: Optional[str] = Field(default=None)

    # Portfolio conflict resolution (audit Section 15.4 — partial
    # coverage here; full conflict-resolution flow is α5 scope)
    portfolio_owner_code: Optional[str] = Field(default=None)
    portfolio_owner_name: Optional[str] = Field(default=None)
    bsc_credit_to: Optional[str] = Field(default=None)
    manager_override_note: Optional[str] = Field(
        default=None,
        description="Required when override semantics detected — see "
                    "validate_create_payload in api_pipeline_mutations.py. "
                    "Minimum 10 characters when required. Added v10.507 α5."
    )


class PipelineDealRefer(BaseModel):
    """Request body for POST /api/pipeline/deals/refer.

    Creates a referral-only deal record where the current RM defers
    pursuit to the portfolio owner. Auto-sets:
    - is_referral = True
    - is_ntb = False
    - product_type = "Referral"
    - stage = "Lead"
    - deal_value = 0
    - probability = 0.05

    Required fields enforced at validation by REQUIRED_REFER_FIELDS
    in api_pipeline_mutations.py. The referring RM (staff_code) must
    differ from the portfolio owner (portfolio_owner_code) — referring
    to oneself is a no-op and rejected.

    Audit Section 15.4 (Phase 3 Arc α Batch α5).
    """
    model_config = ConfigDict(extra="allow")

    client_name: str = Field(description="Customer display name")
    staff_code: Optional[str] = Field(
        default=None,
        description="Referring RM staff code. Server-derived when omitted (H1).",
    )
    staff_name: Optional[str] = Field(
        default=None,
        description="Referring RM display name. Server-derived when omitted (H1).",
    )

    # Portfolio owner — who the deal is being referred TO
    portfolio_owner_code: str = Field(
        description="Staff code of the portfolio owner per CBS"
    )
    portfolio_owner_name: str = Field(
        description="Display name of the portfolio owner"
    )
    referred_to: str = Field(
        description="Named recipient — typically equals portfolio_owner_name "
                    "but may be a different person in the same team"
    )

    # Optional context fields
    referral_note: Optional[str] = Field(
        default="",
        description="Free-text note about the referral — context for the "
                    "portfolio owner about what the customer needs"
    )
    account_number: Optional[str] = Field(
        default=None,
        description="CBS account number if the customer is existing"
    )
    unit: Optional[str] = Field(default=None)


class PipelineDealUpdate(BaseModel):
    """Request body for PUT /api/pipeline/deals/{deal_id}.

    All fields optional — partial update. The endpoint applies only
    the keys present in the request; absent keys are not touched.
    `stage` updates via PUT are intentionally allowed for fields
    PipelineManager.update_deal handles (e.g. correcting an
    accidentally-wrong stage during creation). Stage TRANSITIONS
    (with activity log entry, audit trail, BSC trigger) should use
    the dedicated advance endpoint.
    """
    model_config = ConfigDict(extra="allow")

    client_name: Optional[str] = Field(default=None)
    deal_value: Optional[float] = Field(default=None)
    product_type: Optional[str] = Field(default=None)
    stage: Optional[str] = Field(default=None)
    probability: Optional[float] = Field(default=None)
    next_action: Optional[str] = Field(default=None)
    next_action_date: Optional[str] = Field(default=None)
    expected_close: Optional[str] = Field(default=None)
    notes: Optional[str] = Field(default=None)
    source: Optional[str] = Field(default=None)
    competitors: Optional[Any] = Field(default=None)
    loss_reason: Optional[str] = Field(default=None)
    portfolio_owner_code: Optional[str] = Field(default=None)
    portfolio_owner_name: Optional[str] = Field(default=None)
    bsc_credit_to: Optional[str] = Field(default=None)


class PipelineDealAdvance(BaseModel):
    """Request body for POST /api/pipeline/deals/{deal_id}/advance."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    new_stage: str = Field(
        # B16: the React frontend sends `target_stage`; accept both names so
        # the existing UI works without a rebuild. The endpoint still reads
        # `payload.new_stage`, which is populated from either key.
        validation_alias=AliasChoices("new_stage", "target_stage"),
        description="Target stage. Must be in ALLOWED_ADVANCE_STAGES "
                    "from utils/api_pipeline_mutations.py. Sent as "
                    "`target_stage` by the React client (alias)."
    )
    note: Optional[str] = Field(
        default="",
        description="Free-text note about the transition. Recorded in "
                    "activity log."
    )


class PipelineDealMutationResponse(BaseModel):
    """Response shape for POST/PUT/advance success.

    Returns the full updated deal record + a status field for the
    caller's UX. The `bsc_triggered` flag indicates whether the
    side-effect BSC recompute succeeded (failure is non-fatal per
    Section 15.6 — the K041 breadcrumb is best-effort).

    LMS handoff fields (v10.506 Phase 3 Arc α Batch α4) — only
    populated on advance operations. When advancing to a stage in
    LMS_DEFERRED_STAGES, the endpoint attempts to create a linked
    LoanApplication via LoanApplicationManager.create_from_pipeline_deal:
    - lms_triggered=True + lms_application_id set + lms_error=None
      means the application exists (newly created or already linked).
    - lms_triggered=False + lms_error set means the handoff was
      attempted but failed; the advance itself succeeded.
    - All three None means no handoff was applicable (non-LMS stage
      or no transition happened).
    """
    model_config = ConfigDict(extra="allow")

    deal: PipelineDeal
    status: str = Field(description="'created' | 'updated' | 'advanced' | 'referred'")
    bsc_triggered: bool = Field(
        description="True if BSC recompute was invoked successfully"
    )
    lms_triggered: Optional[bool] = Field(
        default=None,
        description="True if LMS handoff completed (new or idempotent). "
                    "Only set on advance operations."
    )
    lms_application_id: Optional[str] = Field(
        default=None,
        description="The LoanApplication id (new or existing) linked to "
                    "this deal. Format 'LMS#####'. Only set when "
                    "lms_triggered is True."
    )
    lms_error: Optional[str] = Field(
        default=None,
        description="Error message if LMS handoff was attempted and "
                    "failed. The advance itself still succeeded; this "
                    "indicates the caller should retry the handoff or "
                    "escalate."
    )


# ────────────────────────────────────────────────────────────────────
# Manager queue models (v10.508 Phase 3 Arc α Batch α6)
# ────────────────────────────────────────────────────────────────────


class PipelineDealValidate(BaseModel):
    """Request body for POST /api/pipeline/deals/{id}/validate.

    Manager either VALIDATES (approved=True → DEAL_VALIDATED audit,
    deal becomes part of forecast) or QUERIES (approved=False →
    DEAL_QUERIED audit, deal returns to owner with the note).

    Mirrors Streamlit pages/3_pipeline.py:1329-1336.
    """
    model_config = ConfigDict(extra="allow")

    approved: bool = Field(
        description="True = validate (include in forecast); "
                    "False = query (return to owner)"
    )
    note: Optional[str] = Field(
        default="",
        description="Manager's note. Permissive — matches Streamlit "
                    "which doesn't enforce a note on query either."
    )


class PipelineDealCancelRequest(BaseModel):
    """Request body for POST /api/pipeline/deals/{id}/cancel/request.

    Any RM can request cancellation of a deal in their cascade scope.
    The request enters the manager's cancellation queue for review.
    Validation requires a non-trivial reason (>= MIN_CANCEL_REASON_LEN
    chars from utils/api_pipeline_manager_actions.py).

    Mirrors Streamlit pages/3_pipeline.py:1460-1463.
    """
    model_config = ConfigDict(extra="allow")

    reason: str = Field(
        min_length=1,
        description="Why the deal should be cancelled. Visible to "
                    "manager in their cancellation queue."
    )


class PipelineDealCancelApprove(BaseModel):
    """Request body for POST /api/pipeline/deals/{id}/cancel/approve.

    Manager either APPROVES the cancellation (approve=True -> deal
    transitions to Closed Lost, CANCEL_APPROVED audit) or REJECTS it
    (approve=False -> deal continues, CANCEL_REJECTED audit).

    Mirrors Streamlit pages/3_pipeline.py:1307-1315.
    """
    model_config = ConfigDict(extra="allow")

    approve: bool = Field(
        description="True = approve cancellation; False = reject "
                    "(deal continues, cancel_requested flag cleared)"
    )
    note: Optional[str] = Field(
        default="",
        description="Manager's decision note. Visible on the deal "
                    "record for audit trail."
    )


class PipelineManagerQueueResponse(BaseModel):
    """Response shape for the two manager-queue GET endpoints.

    Returns the filtered list of deals + count + queue identifier.
    Same general shape as PipelineDealsResponse but with queue
    metadata for the caller to distinguish which queue this came from.
    """
    model_config = ConfigDict(extra="allow")

    deals: List[PipelineDeal]
    count: int
    queue: str = Field(description="'validation' | 'cancellation'")

