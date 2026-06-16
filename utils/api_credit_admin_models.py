"""utils/api_credit_admin_models.py — Pydantic models for the Credit
Admin (CALMS) domain.

Authored v10.518 Phase 3 Arc α Batch α9 — Credit Admin API.

Domain note
-----------
The Credit Admin domain holds APPROVED loan applications that are
now in the disbursement pipeline. A case (CALMS####) has a list of
disbursement conditions (board resolutions, debentures, KYC docs,
etc.) that must all be fulfilled before funds can be disbursed.

Lifecycle:
  approved (LMS) → handed off to credit-admin → conditions fulfilled
  one by one → all_conditions_met flips True → manager clears for
  disbursement → eventually disbursed=True + disbursement_date set

α9 surfaces this for React:
- List/detail (read)
- Condition fulfillment (anyone in scope can mark a condition met)
- Disburse (manager-tier; calls clear_for_disbursement under the hood)

Field shape verified against data/credit_admin.json record 0 at
commit `c246f0c`.
"""
from __future__ import annotations

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


# ─────────────────────────────────────────────────────────────────────
# Condition — a single disbursement requirement
# ─────────────────────────────────────────────────────────────────────


class CreditAdminCondition(BaseModel):
    """One disbursement condition on a credit-admin case.

    Examples: 'Board resolution', 'Debenture', 'KYC documentation',
    'Insurance certificate'. Set by approval authority; fulfilled by
    operations officers as documents are collected.
    """
    model_config = ConfigDict(extra="allow")

    type: str = Field(description="Human-readable condition name")
    required: bool = Field(
        default=True,
        description="True if condition is mandatory for disbursement"
    )
    fulfilled: bool = Field(
        default=False,
        description="True once the officer marks it complete"
    )
    date_set: Optional[str] = Field(
        default=None,
        description="ISO date the condition was added (typically the approval date)"
    )
    date_met: Optional[str] = Field(
        default=None,
        description="ISO date the condition was fulfilled; null until then"
    )
    officer: Optional[str] = Field(
        default=None,
        description="Name of the officer who fulfilled the condition (audit trail)"
    )
    notes: Optional[str] = Field(
        default="",
        description="Free-text notes about fulfillment"
    )


# ─────────────────────────────────────────────────────────────────────
# CreditAdminCase — the case record shape
# ─────────────────────────────────────────────────────────────────────


class CreditAdminCase(BaseModel):
    """An approved loan application now in the disbursement pipeline.

    Field naming follows data/credit_admin.json — the
    CreditAdminManager IS the canonical writer.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # ── Identity ──
    id: str = Field(description="Case ID, format 'CALMS#####'")
    application_id: str = Field(
        description="Source LMS application ID (LMS#####)"
    )

    # ── Customer / product (denormalized from LMS for fast access) ──
    client_name: str
    product: Optional[str] = None
    amount: Optional[float] = None

    # ── Ownership ──
    rm_code: Optional[str] = None
    rm_name: Optional[str] = None

    # ── Lifecycle dates ──
    approval_date: Optional[str] = Field(
        default=None,
        description="ISO date when the underlying LMS application was approved"
    )
    last_updated: Optional[str] = None

    # ── Conditions ──
    conditions: List[CreditAdminCondition] = Field(
        default_factory=list,
        description="Disbursement conditions; all must be fulfilled before disburse"
    )

    # ── Computed gates (maintained by CreditAdminManager) ──
    all_conditions_met: bool = Field(
        default=False,
        description="True when every required condition is fulfilled"
    )
    ready_for_disbursement: bool = Field(
        default=False,
        description="True once a manager clears the case for disbursement; "
                    "requires all_conditions_met=True first"
    )

    # ── Two-layer authorization (v10.585) ──
    authorization_requested: bool = Field(
        default=False,
        description="Layer 1: a credit-admin officer has requested authorization")
    authorization_requested_by: Optional[str] = None
    authorization_requested_at: Optional[str] = None
    authorized: bool = Field(
        default=False,
        description="Layer 2: a credit-admin manager has authorized disbursement")
    authorized_by: Optional[str] = None
    authorized_at: Optional[str] = None

    # ── Disbursement ──
    disbursed: bool = Field(default=False)
    disbursement_date: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────
# List response
# ─────────────────────────────────────────────────────────────────────


class CreditAdminCasesResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    cases: List[CreditAdminCase]
    count: int
    source: str


# ─────────────────────────────────────────────────────────────────────
# Per-case permissions
# ─────────────────────────────────────────────────────────────────────


class CreditAdminPermissions(BaseModel):
    """Caller-vs-case permission flags."""
    model_config = ConfigDict(extra="allow")

    can_view: bool = Field(description="Caller can fetch detail")
    can_fulfill_condition: bool = Field(
        description="Caller can POST to /conditions/fulfill "
                    "(anyone in scope, case not disbursed)"
    )
    can_disburse: bool = Field(
        description="Caller can POST to /disburse "
                    "(manager-tier, all_conditions_met=True, not disbursed)"
    )
    can_request_authorization: bool = Field(
        default=False,
        description="Caller can POST to /request-authorization "
                    "(in scope, all_conditions_met, not yet requested, two-layer on)"
    )
    can_authorize: bool = Field(
        default=False,
        description="Caller can POST to /authorize "
                    "(CA manager-tier, authorization_requested, not yet authorized)"
    )


class CreditAdminCaseDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    case: CreditAdminCase
    permissions: CreditAdminPermissions
    source: str


# ─────────────────────────────────────────────────────────────────────
# Mutation requests
# ─────────────────────────────────────────────────────────────────────


class FulfillConditionRequest(BaseModel):
    """Request body for POST /api/credit-admin/cases/{id}/conditions/fulfill.

    Marks a single condition (identified by its 'type' string) as
    fulfilled. The officer_name is recorded on the condition for
    audit trail.

    Scope: anyone in cascade can fulfill conditions (per α9 decision —
    operations officers, RMs, and managers all collaborate on document
    collection).
    """
    model_config = ConfigDict(extra="allow")

    condition_type: str = Field(
        min_length=1,
        description="The 'type' field of the condition to mark fulfilled "
                    "(e.g. 'Board resolution', 'Debenture')"
    )
    officer_name: str = Field(
        min_length=1,
        description="Name of the officer marking the condition fulfilled. "
                    "Recorded on the condition for audit. Typically the "
                    "logged-in user's full_name but allows for delegation "
                    "(officer marks on behalf of someone else)."
    )
    notes: Optional[str] = Field(
        default="",
        description="Optional notes about how the condition was fulfilled"
    )


class DisburseCaseRequest(BaseModel):
    """Request body for POST /api/credit-admin/cases/{id}/disburse.

    Clears the case for disbursement. Calls
    CreditAdminManager.clear_for_disbursement under the hood, which
    sets ready_for_disbursement=True (NOT disbursed=True — that's a
    separate finance-system step outside this API's scope).

    Manager-tier authorization required at endpoint.
    """
    model_config = ConfigDict(extra="allow")

    authority: str = Field(
        min_length=1,
        description="Decision-maker role/title clearing the case "
                    "(e.g. 'Credit Manager', 'Branch Manager', "
                    "'Managing Director'). Recorded for audit."
    )
    comments: Optional[str] = Field(
        default="",
        description="Optional notes about the clearance decision"
    )


# ─────────────────────────────────────────────────────────────────────
# Mutation response
# ─────────────────────────────────────────────────────────────────────


class CreditAdminMutationResponse(BaseModel):
    """Response shape for the 2 mutation endpoints."""
    model_config = ConfigDict(extra="allow")

    case: CreditAdminCase
    status: str = Field(
        description="'condition_fulfilled' | 'cleared_for_disbursement'"
    )


# ─────────────────────────────────────────────────────────────────────
# Two-layer authorization request bodies (v10.585)
# ─────────────────────────────────────────────────────────────────────

class RequestAuthorizationRequest(BaseModel):
    """POST /api/credit-admin/cases/{id}/request-authorization — Layer 1.
    A credit-admin officer confirms the case is ready and requests manager
    authorization. Requires all_conditions_met."""
    model_config = ConfigDict(extra="allow")
    note: str = Field(default="", description="Officer's confirmation note.")


class AuthorizeRequest(BaseModel):
    """POST /api/credit-admin/cases/{id}/authorize — Layer 2.
    A credit-admin MANAGER authorizes disbursement. Requires a pending
    authorization request."""
    model_config = ConfigDict(extra="allow")
    note: str = Field(default="", description="Manager's authorization note.")
