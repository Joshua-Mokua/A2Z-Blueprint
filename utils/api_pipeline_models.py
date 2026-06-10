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
from pydantic import BaseModel, Field, ConfigDict


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
