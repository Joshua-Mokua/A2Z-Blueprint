"""utils/api_pipeline_mutations.py — Helpers for pipeline mutation
endpoints (POST/PUT/advance).

Authored v10.505 Phase 3 Arc α Batch α3 — Pipeline CRUD + Advance.

Purpose
-------
Centralizes the constants, validation, and side-effect helpers used
by `/api/pipeline/deals` (POST), `/api/pipeline/deals/{id}` (PUT),
and `/api/pipeline/deals/{id}/advance` (POST). Keeping these in a
sibling module rather than inline keeps `utils/api.py` readable and
makes the mutation contract auditable.

Doctrine context
----------------
**"Streamlit stays, React additive, FastAPI canonical."** The
Streamlit page `pages/3_pipeline.py` has its own implementation of
the create/update/advance flows (around lines 940-988 for add,
560-590 for advance). α3 brings the API surface up to parity for
the basic CRUD operations, but **deliberately stops short of LMS
handoff** (Section 15.7) — that's α4's scope.

Per the audit's `_LMS_STAGES` finding, when a deal advances to one
of {Credit Review, Approval, Bank Approval, Credit Committee,
Documentation, Vetting, Disbursed}, Streamlit auto-creates a
LoanApplication record via `LoanApplicationManager.create_from_pipeline_deal`.
α3 cannot replicate this because it would leave deals at LMS stages
without linked applications — an inconsistent state.

α3's resolution (Option C): the advance endpoint maintains an
**explicit allowlist** of safe stages. Requests to advance to any
LMS-deferred stage are rejected with HTTP 400 + an explanatory
message pointing the caller at Streamlit until α4 lands. A new
audit gate (G396) verifies this allowlist is enforced.

References
----------
- `docs/architecture/PIPELINE_DOMAIN_AUDIT.md` Section 15.7 (LMS
  handoff anatomy) and Section 16.3 (Arc α scope).
- `utils/core.py:932` — `PIPELINE_STAGES_LOAN` (the 10 doctrine
  stages).
- `pages/3_pipeline.py:21-26` — `_bsc_trigger()`, the BSC recompute
  pattern α3 mirrors server-side.
- `utils/core.py:6483` — `update_bsc_from_modules(username)`, the
  canonical BSC recompute function.
"""
from __future__ import annotations

from typing import Any, Dict, Set, Tuple


# ────────────────────────────────────────────────────────────────────
# Stage allowlist (Option C — explicit guard against LMS handoff drift)
# ────────────────────────────────────────────────────────────────────


# Stages from the canonical PIPELINE_STAGES_LOAN that DO NOT require
# LMS handoff. α3's advance endpoint permits transitions to these
# stages only. The full vocabulary lives in `utils/core.py:932` and
# `utils/core.py:944` (Loan + Deposit stage lists); we maintain a
# string set here for fast O(1) membership tests and to keep the
# gate's enforcement target unambiguous.
ALLOWED_ADVANCE_STAGES: Set[str] = {
    # Loan pipeline pre-LMS stages
    "Lead",
    "Contacted",
    "Qualified",
    "Proposal",
    "Negotiation",
    "Compliance",
    "Closed Won",
    "Closed Lost",
    # Account pipeline stages (no LMS handoff applies)
    "Information Gathered",
    "Documentation Complete",
    "Account Opened",
    # Deposit pipeline stages
    "Pitched",
    "Negotiating",
    "Funded",
    # Generic
    "Open",
}


# Stages that require LMS handoff per audit Section 15.7. Advance
# endpoint rejects these in α3 with HTTP 400 + pointer to α4. This
# set is the explicit COMPLEMENT to ALLOWED_ADVANCE_STAGES for the
# loan workflow; G396 verifies neither set is silently widened.
LMS_DEFERRED_STAGES: Set[str] = {
    "Credit Review",
    "Approval",
    "Bank Approval",
    "Credit Committee",
    "Documentation",
    "Vetting",
    "Disbursed",
}


# ────────────────────────────────────────────────────────────────────
# Required-field validation (POST payload)
# ────────────────────────────────────────────────────────────────────


# Minimum fields a new deal must carry. Streamlit collects MANY more
# (client_type, is_ntb, id_type, id_number, phone, sector, etc.) but
# those are presentation-layer richness. The canonical PipelineManager
# only needs enough to identify the deal + its owner.
REQUIRED_CREATE_FIELDS: Tuple[str, ...] = (
    "client_name",
    "staff_code",
    "staff_name",
    "deal_value",
    "product_type",
    "stage",
)


def validate_create_payload(deal_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (ok, reason) for a deal creation payload.

    Checks:
      - All REQUIRED_CREATE_FIELDS are present AND non-empty
      - `deal_value` is a non-negative number
      - `stage` is in ALLOWED_ADVANCE_STAGES (cannot create directly
        at an LMS stage either — must advance through proper flow)

    `reason` is safe to expose to the API caller; do not include
    sensitive context.
    """
    for field in REQUIRED_CREATE_FIELDS:
        v = deal_data.get(field)
        if v is None or (isinstance(v, str) and not v.strip()):
            return False, f"Missing required field: {field}"

    # Numeric sanity on deal_value
    try:
        val = float(deal_data["deal_value"])
        if val < 0:
            return False, "deal_value must be non-negative"
    except (TypeError, ValueError):
        return False, "deal_value must be a number"

    # Stage must be a known non-LMS stage. Creating a deal directly
    # at an LMS stage would have the same inconsistency problem as
    # advancing into one without the handoff.
    stage = str(deal_data.get("stage", ""))
    if stage in LMS_DEFERRED_STAGES:
        return False, (
            f"Cannot create deal directly at stage '{stage}' "
            "(LMS handoff stage — deferred to Arc α4). "
            "Create at 'Lead' and advance through the workflow."
        )
    if stage not in ALLOWED_ADVANCE_STAGES:
        return False, f"Unknown stage: '{stage}'"

    return True, ""


def validate_advance_target(new_stage: str) -> Tuple[bool, str]:
    """Return (ok, reason) for an advance request.

    Post-α4 doctrine: advance is permitted to any stage in
    ``ALLOWED_ADVANCE_STAGES`` OR ``LMS_DEFERRED_STAGES``. When the
    target is an LMS stage, the caller (endpoint) is expected to
    invoke ``handle_lms_handoff`` to auto-create the linked
    LoanApplication.

    α3 originally rejected LMS stages outright (Option C); α4 lifts
    that restriction by implementing the handoff. The set name
    `LMS_DEFERRED_STAGES` is retained for backward compatibility
    with prior tests/imports — semantically these are now "LMS
    handoff trigger stages" but the constant name documents the
    historical transition.
    """
    if not new_stage or not isinstance(new_stage, str):
        return False, "new_stage must be a non-empty string"

    if new_stage in LMS_DEFERRED_STAGES:
        # α4: permitted, handoff triggered by caller. No longer rejected.
        return True, ""

    if new_stage not in ALLOWED_ADVANCE_STAGES:
        return False, (
            f"Unknown stage: '{new_stage}'. "
            f"Allowed stages: {sorted(ALLOWED_ADVANCE_STAGES | LMS_DEFERRED_STAGES)}"
        )

    return True, ""


def is_lms_handoff_transition(old_stage: str, new_stage: str) -> bool:
    """Return True if (old, new) represents an LMS handoff transition.

    A handoff fires when the deal IS entering an LMS stage AND the
    transition is real (not a no-op). Matches the Streamlit page
    condition at line 1242: ``_nst in _LMS_STAGES and _nst != _sd.get("stage")``.

    Returns False if:
    - ``new_stage`` is not an LMS stage (no handoff needed)
    - ``new_stage == old_stage`` (no-op, no handoff)

    LMS→LMS transitions (Credit Review → Approval, etc.) return True
    here; idempotency in ``LoanApplicationManager.create_from_pipeline_deal``
    handles those safely — returns the existing app id instead of
    creating a duplicate.
    """
    if new_stage not in LMS_DEFERRED_STAGES:
        return False
    if new_stage == old_stage:
        return False
    return True


def handle_lms_handoff(
    deal: Dict[str, Any],
    old_stage: str,
    new_stage: str,
    username: str,
) -> Tuple[bool, Any, Any]:
    """Trigger LMS handoff if applicable.

    Returns
    -------
    (triggered, app_id, error)
        triggered : bool
            True if a new application was created OR an existing one
            was found (deal is now linked to an application).
            False if the transition didn't qualify for handoff at all.
        app_id : Optional[str]
            The application id (new or existing). None on failure or
            on no-handoff case.
        error : Optional[str]
            Error message if handoff was attempted and failed. None
            on success or non-handoff. The endpoint should include
            this in the response so the caller knows.

    Failure semantics: handoff failure does NOT roll back the advance.
    The deal has already transitioned (PipelineManager.update_stage
    is complete by the time this function is called). The endpoint
    returns HTTP 200 with `lms_error` in the response body. An audit
    event `API_PIPELINE_ADVANCE_LMS_FAILED` should be emitted by the
    caller alongside.
    """
    if not is_lms_handoff_transition(old_stage, new_stage):
        return False, None, None

    try:
        # Lazy import — pulls a fair amount of surface area
        from utils.core import LoanApplicationManager
        lam = LoanApplicationManager()
        app_id = lam.create_from_pipeline_deal(deal, username)
        if not app_id:
            return False, None, (
                "create_from_pipeline_deal returned None — deal "
                "lacks required fields for application creation"
            )
        return True, app_id, None
    except Exception as e:
        return False, None, f"LMS handoff failed: {type(e).__name__}: {e}"


# ────────────────────────────────────────────────────────────────────
# BSC trigger (server-side equivalent of pages/3_pipeline.py:21-26)
# ────────────────────────────────────────────────────────────────────


def emit_bsc_trigger(username: str) -> bool:
    """Trigger a BSC recompute for the user. Server-side equivalent
    of the `_bsc_trigger(uname, "K041")` pattern Streamlit uses 16
    times in the pipeline page.

    Returns True on success, False on failure (silently — the K041
    breadcrumb is a side-effect, not a load-bearing op, per the
    audit's Section 15.6 finding that the kpi parameter is decorative).

    The canonical implementation is `update_bsc_from_modules(username)`
    in `utils/core.py:6483`. We mirror Streamlit's "best effort,
    don't crash the request on BSC failure" semantics.
    """
    if not username:
        return False
    try:
        from utils.core import update_bsc_from_modules
        update_bsc_from_modules(username)
        return True
    except Exception:
        # Per the Streamlit page's pattern (line 25: `except
        # Exception: pass`). BSC recompute failing should not roll
        # back a successful deal mutation.
        return False


# ────────────────────────────────────────────────────────────────────
# Cache invalidation
# ────────────────────────────────────────────────────────────────────


def invalidate_pipeline_caches() -> None:
    """Clear the in-memory pipeline_summary cache (and any future
    pipeline-domain caches) so the next GET reflects the mutation.

    `utils/api.py` maintains `_cache` and `_cache_ts` dicts as
    module-level state. We import them lazily because this helper
    may be called from contexts where importing api would create
    cycles or unnecessary side effects.
    """
    try:
        from utils import api as _api_module
        # Pop both maps for the pipeline_summary key. Add more keys
        # here as future pipeline-domain endpoints get caching.
        for key in ("pipeline_summary",):
            _api_module._cache.pop(key, None)
            _api_module._cache_ts.pop(key, None)
    except Exception:
        # If api module can't be imported (test isolation, etc.),
        # invalidation is moot.
        pass
