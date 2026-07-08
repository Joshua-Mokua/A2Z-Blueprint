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
    # NOTE: "Compliance" was removed (v10.574 B10). Credit submission is now an
    # explicit, document-gated action (POST /submit-to-credit), not a silent
    # side-effect of advancing a stage. These config credit stages remain for
    # config-flow deals that advance through them directly.
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


# ────────────────────────────────────────────────────────────────────
# Conflict resolution helpers (v10.507 Phase 3 Arc α Batch α5)
# ────────────────────────────────────────────────────────────────────
#
# Per audit Section 15.4, conflict resolution has three distinct
# paths when a deal's portfolio owner is someone other than the
# creating RM:
#
# 1. REFER (separate endpoint POST /api/pipeline/deals/refer):
#    RM defers to portfolio owner. Creates a referral-only deal
#    record with is_referral=True. BSC credit (when the referred
#    deal closes) goes to whoever ultimately closes it.
#
# 2. SEEK PERMISSION (implicit creation-time semantics):
#    RM pursues with external/verbal permission from portfolio
#    owner. The deal has portfolio_owner_code != staff_code AND
#    bsc_credit_to set to the assignee/staff_name. No new endpoint
#    needed — it's a field-value combination at deal creation.
#
# 3. OVERRIDE (extended validation on POST /api/pipeline/deals):
#    RM pursues WITHOUT portfolio owner's permission. Requires
#    manager_override_note (>= MIN_OVERRIDE_NOTE_LEN chars). The
#    deal has portfolio_owner_code != staff_code AND bsc_credit_to
#    routed to the portfolio_owner_name (default) for audit trail.


# Minimum characters for a manager override note. Long enough to be
# meaningful (rule out "ok" / "yes" / "approved"), short enough to
# not friction-burn the user. Matches the Streamlit page's implicit
# expectation that the note explain why an override is appropriate.
MIN_OVERRIDE_NOTE_LEN: int = 10


# Required fields on the referral endpoint. The endpoint creates a
# deal record with is_referral=True; these are the minimum fields
# needed to make the referral actionable for the portfolio owner.
REQUIRED_REFER_FIELDS: Tuple[str, ...] = (
    "client_name",
    "staff_code",          # the referring RM
    "staff_name",
    "portfolio_owner_code", # who they're referring TO (owner per CBS)
    "portfolio_owner_name",
    "referred_to",         # the named recipient (often == portfolio_owner_name)
)


def is_override_semantics(deal_data: Dict[str, Any]) -> bool:
    """Return True if the deal payload represents an OVERRIDE
    conflict resolution (RM pursuing without portfolio owner's
    permission).

    Detection rule:
    - portfolio_owner_code is set AND non-empty
    - portfolio_owner_code != staff_code (i.e., real conflict exists)
    - bsc_credit_to is NOT the portfolio_owner_name (i.e., the RM is
      claiming the BSC credit, not deferring it to the owner)

    The "seek permission" path is the inverse — when conflict exists
    but bsc_credit_to == portfolio_owner_name. Those payloads pass
    validation without an override note.
    """
    po_code = str(deal_data.get("portfolio_owner_code", "") or "").strip()
    staff_code = str(deal_data.get("staff_code", "") or "").strip()
    if not po_code or po_code == staff_code:
        # No conflict — not override semantics
        return False

    po_name = str(deal_data.get("portfolio_owner_name", "") or "").strip()
    bsc_credit_to = str(deal_data.get("bsc_credit_to", "") or "").strip()

    # If bsc_credit_to is unset or equals portfolio owner → seek-permission
    # path (the RM is deferring BSC credit). NOT override.
    if not bsc_credit_to:
        return False
    if bsc_credit_to == po_name:
        return False

    # Conflict exists AND RM is claiming the BSC credit → override semantics
    return True


def validate_refer_payload(deal_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (ok, reason) for a referral creation payload.

    Differs from validate_create_payload in REQUIRED_FIELDS set
    (no deal_value/product_type/stage — these are auto-set by the
    endpoint). Referrals don't have a meaningful deal_value at
    creation time; the portfolio owner sets it when they pick up
    the referred deal.
    """
    for field in REQUIRED_REFER_FIELDS:
        v = deal_data.get(field)
        if v is None or (isinstance(v, str) and not v.strip()):
            return False, f"Missing required field for referral: {field}"

    # The referring RM cannot refer to themselves — that's a no-op
    staff_code = str(deal_data.get("staff_code", "") or "").strip()
    po_code = str(deal_data.get("portfolio_owner_code", "") or "").strip()
    if staff_code == po_code:
        return False, (
            "Cannot refer to yourself — portfolio_owner_code "
            "must differ from staff_code"
        )

    return True, ""




# FP1 (2026-07-02): create-cutoff derived from the PRODUCT'S OWN flow, not a frozen set.
# The credit-analysis handoff stage is where the deal leaves pipeline ORIGINATION and
# becomes an LMS matter. It may be named per product ("Credit Analysis",
# "Credit Assessment", ...); detect it flexibly.
_CREDIT_ANALYSIS_FAMILY = {"credit analysis", "credit assessment"}

def _product_flow_stage_names(product_type: str) -> list:
    """Ordered stage names for a product's flow (product_flows)."""
    try:
        from utils.api import _load_json, _norm_product
        cfg = _load_json("pipeline_settings.json") or {}
        pf = cfg.get("product_flows", {}) or {}
        want = _norm_product(product_type) if product_type else ""
        for name, entry in pf.items():
            if _norm_product(name) == want and isinstance(entry, dict):
                out = []
                for st in entry.get("stages", []):
                    nm = st.get("stage") if isinstance(st, dict) else st
                    if nm:
                        out.append(str(nm))
                return out
    except Exception:
        pass
    return []

def _credit_handoff_cutoff(product_type: str):
    """Return (handoff_stage, handoff_index, flow_stages). handoff_index is None if
    the product's flow has no credit-analysis handoff stage."""
    stages = _product_flow_stage_names(product_type)
    # P2: Department Analyst layer. When enabled, the credit factory engages
    # EARLIER — at the configured department handoff stage (e.g. "Department
    # Credit Committee Review") rather than at Credit Analysis. Both the RM edit
    # lock and the LMS-application creation key off this cutoff, so both shift
    # earlier automatically. Gated: when disabled (default) this block is a
    # no-op and the legacy Credit-Analysis cutoff below applies unchanged.
    try:
        from utils.api_lms_mutations import get_credit_workflow_config
        da = (get_credit_workflow_config() or {}).get("department_analyst") or {}
        if da.get("enabled"):
            hs = str(da.get("handoff_stage", "") or "").strip().lower()
            if hs:
                for i, nm in enumerate(stages):
                    if str(nm).strip().lower() == hs:
                        return nm, i, stages
    except Exception:
        pass
    # explicit config override
    explicit = None
    try:
        from utils.api import _load_json, _norm_product
        cfg = _load_json("pipeline_settings.json") or {}
        pf = cfg.get("product_flows", {}) or {}
        want = _norm_product(product_type) if product_type else ""
        for name, entry in pf.items():
            if _norm_product(name) == want and isinstance(entry, dict):
                explicit = entry.get("credit_handoff_stage")
                break
    except Exception:
        pass
    if explicit and explicit in stages:
        return explicit, stages.index(explicit), stages
    # family match (first stage whose name is in the credit-analysis family)
    for i, nm in enumerate(stages):
        if str(nm).strip().lower() in _CREDIT_ANALYSIS_FAMILY:
            return nm, i, stages
    return None, None, stages


def is_credit_handoff_for_deal(deal: Dict[str, Any], old_stage: str, new_stage: str) -> bool:
    """Per-product credit handoff gate.

    A deal hands off to Credit (creating the LMS application and locking the deal)
    when it ENTERS its product's designated credit-analysis stage — "Credit
    Analysis" / "Credit Assessment", or an explicit ``credit_handoff_stage``.
    Origination stages that come BEFORE it in the product's own flow
    (e.g. Documentation, Branch/Department Credit Committee Review) do NOT hand
    off and do NOT lock — the RM keeps building the case there.

    Each product's journey (and therefore its credit gate) varies, so this keys
    off the product's own flow rather than a global stage-name set. Falls back to
    the static ``LMS_DEFERRED_STAGES`` test only when the product's flow has no
    credit-analysis stage (e.g. deposit/account products), preserving legacy
    behaviour for those.
    """
    if new_stage == old_stage:
        return False
    product_type = str(deal.get("product_type", "") or "")
    handoff_stage, handoff_idx, flow_stages = _credit_handoff_cutoff(product_type)
    if handoff_stage is None or handoff_idx is None:
        # No credit-analysis stage in this product's flow — legacy behaviour.
        return is_lms_handoff_transition(old_stage, new_stage)
    new_idx = flow_stages.index(new_stage) if new_stage in flow_stages else -1
    if new_idx < 0:
        # Target stage isn't in this product's flow — fall back to the static set.
        return is_lms_handoff_transition(old_stage, new_stage)
    # Fire once the deal reaches (enters or is past) the credit-analysis cutoff.
    # create_from_pipeline_deal is idempotent, so LMS->LMS moves past the cutoff
    # return the existing application id rather than creating a duplicate.
    return new_idx >= handoff_idx


def validate_create_payload(deal_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (ok, reason) for a deal creation payload.

    Checks:
      - All REQUIRED_CREATE_FIELDS are present AND non-empty
      - `deal_value` is a non-negative number
      - `stage` is in ALLOWED_ADVANCE_STAGES (cannot create directly
        at an LMS stage either — must advance through proper flow)
      - **Override semantics detected → manager_override_note required**
        (v10.507 Phase 3 Arc α Batch α5). When the payload indicates
        the RM is claiming BSC credit despite a portfolio conflict
        existing, a manager_override_note of at least
        MIN_OVERRIDE_NOTE_LEN characters must be present.

    `reason` is safe to expose to the API caller; do not include
    sensitive context.
    """
    for field in REQUIRED_CREATE_FIELDS:
        v = deal_data.get(field)
        if v is None or (isinstance(v, str) and not v.strip()):
            return False, f"Missing required field: {field}"

    # Numeric sanity on deal_value. float() accepts NaN/Infinity and absurd
    # magnitudes, which then crash the persistence layer (a 500 / DoS surface
    # found in stress Phase 3). Reject non-finite and out-of-range values here.
    import math as _math
    try:
        val = float(deal_data["deal_value"])
    except (TypeError, ValueError):
        return False, "deal_value must be a number"
    if not _math.isfinite(val):
        return False, "deal_value must be a finite number"
    if val < 0:
        return False, "deal_value must be non-negative"
    # Upper bound: 1 quadrillion KES is already absurd for a single facility;
    # anything beyond is malformed input, not a real deal. Prevents overflow /
    # persistence crashes from values like 1e308.
    if val > 1_000_000_000_000_000:
        return False, "deal_value exceeds the maximum allowed magnitude"

    # String sanity on free-text fields (stress Phase 3): cap length to prevent
    # oversized-payload persistence crashes (a 1 MB name 500'd the DB layer),
    # and reject control characters / NUL. Control chars (\x00-\x08, \x0b-\x0c,
    # \x0e-\x1f, \x7f) cannot be written into an Excel cell (openpyxl raises
    # IllegalCharacterError), so a single poisoned name would break the xlsx
    # export for the whole scoped pipeline; reject them at the door.
    def _has_control_chars(s: str) -> bool:
        return any((ord(ch) < 0x20 and ch not in "\t\n\r") or ord(ch) == 0x7f
                   for ch in s)
    for _fld in ("client_name", "product_type"):
        _v = deal_data.get(_fld)
        if isinstance(_v, str) and _v:
            if "\x00" in _v:
                return False, f"{_fld} contains an invalid null character"
            if _has_control_chars(_v):
                return False, f"{_fld} contains invalid control characters"
            if len(_v) > 512:
                return False, f"{_fld} is too long (max 512 characters)"

    # FP1 (2026-07-02): create policy derived from the PRODUCT'S OWN flow, replacing
    # the stale hardcoded LMS_DEFERRED create-block. The pipeline tracks a deal
    # start->disbursement (the lead never drops), but a deal may only be CREATED
    # before the credit-analysis handoff; past there the case lives in the modules.
    stage = str(deal_data.get("stage", ""))
    product_type = str(deal_data.get("product_type", "") or "")

    if stage not in ALLOWED_ADVANCE_STAGES and stage not in _configured_stage_names():
        return False, f"Unknown stage: '{stage}'"

    if stage in {"Closed Won", "Closed Lost"}:
        return False, (
            f"Cannot create a deal directly at a terminal stage ('{stage}'). "
            "Terminal outcomes are reached by progressing a deal, not by creating one there."
        )

    handoff_stage, handoff_idx, flow_stages = _credit_handoff_cutoff(product_type)
    if flow_stages:
        if stage not in flow_stages:
            return False, (
                f"Stage '{stage}' is not part of the '{product_type}' product flow. "
                f"Configured stages: {', '.join(flow_stages)}."
            )
        stage_idx = flow_stages.index(stage)
        if handoff_idx is not None and stage_idx >= handoff_idx:
            return False, (
                f"Cannot create a deal at stage '{stage}'. Creation is allowed only "
                f"before the credit-analysis handoff ('{handoff_stage}'); at or beyond "
                "that point the deal is tracked automatically as it moves through credit "
                "analysis, credit administration and disbursement."
            )
        if stage_idx > 0 and not bool(deal_data.get("manager_validated")):
            return False, (
                f"A deal created already at stage '{stage}' must be manager-validated "
                "at creation (manager_validated) to record an in-progress deal entering "
                "above the first stage."
            )
    else:
        if stage not in {"Lead", "Open", "Prospecting", "Pitched", "Initiation"} and not bool(deal_data.get("manager_validated")):
            return False, (
                f"A deal created at stage '{stage}' (above the first stage) must be "
                "manager-validated at creation."
            )

    # Override semantics check (v10.507 α5). If the RM is claiming
    # BSC credit despite a portfolio conflict, require a manager
    # override note. This is the API enforcement for what Streamlit
    # promises ("requires manager override note") but never actually
    # collects — a latent UX bug surfaced in α5 inspection.
    if is_override_semantics(deal_data):
        note = str(deal_data.get("manager_override_note", "") or "").strip()
        if not note:
            return False, (
                "Override semantics detected (portfolio conflict + "
                "RM claiming BSC credit) but no manager_override_note "
                "provided. This combination requires a written "
                "rationale for manager review per audit Section 15.4."
            )
        if len(note) < MIN_OVERRIDE_NOTE_LEN:
            return False, (
                f"manager_override_note too short ({len(note)} chars); "
                f"minimum {MIN_OVERRIDE_NOTE_LEN} characters required "
                "to be meaningful for manager review."
            )

    # Consumer deals lend ONLY through an MOU partnership (Ecobank rule):
    # a deal whose client_type resolves to the 'mou' business line MUST carry a
    # non-empty mou_id. This is the server-side mirror of the create-form's
    # required MOU picker — a direct API call can't book a consumer deal with no
    # MOU. Commercial/CIB (sector-field) deals are unaffected.
    if _is_consumer_mou_deal(deal_data):
        mou_id = str(deal_data.get("mou_id", "") or "").strip()
        if not mou_id:
            return False, (
                "Consumer deals must be booked against an MOU partner "
                "(Ecobank consumer lending flows only through MOUs). "
                "Select an MOU before creating the deal."
            )

    # Top-up: an increase on an existing facility. The pipeline value reflects
    # only the increment, so a top-up MUST carry a positive top_up_amount, and
    # the original facility (if given) must be at least the increment.
    if deal_data.get("is_top_up"):
        try:
            inc = float(deal_data.get("top_up_amount") or 0)
        except (TypeError, ValueError):
            inc = 0.0
        if inc <= 0:
            return False, (
                "A top-up requires a positive top-up amount (the increment "
                "being added to the existing facility)."
            )
        orig_raw = deal_data.get("original_facility_amount")
        if orig_raw not in (None, ""):
            try:
                orig = float(orig_raw)
            except (TypeError, ValueError):
                return False, "Original facility amount must be a number."
            if orig < inc:
                return False, (
                    "Original facility amount must be at least the top-up "
                    "amount (you're adding to an existing facility)."
                )

    return True, ""


def _is_consumer_mou_deal(deal_data: Dict[str, Any]) -> bool:
    """True when the deal's client_type resolves to the 'mou' business line
    (Consumer). Mirrors api._client_type_field locally to avoid a circular
    import; falls back to keyword detection for legacy 'Individual' aliases."""
    ct = str(deal_data.get("client_type", "") or "").strip().lower()
    if not ct:
        return False
    # explicit config-key resolution (best-effort; tolerant of absence)
    try:
        from utils.core import get_pipeline_settings as _lps  # type: ignore
        cfg = _lps() or {}
        for e in (cfg.get("client_types") or []):
            if isinstance(e, dict) and str(e.get("key", "")).lower() == ct:
                return str(e.get("field", "")).lower() == "mou"
    except Exception:
        pass
    # legacy aliases + keyword fallback (Consumer / Individual -> mou)
    return ct.startswith("consumer") or ct.startswith("individual")


def _configured_stage_names() -> Set[str]:
    """Stage names from the admin-configured pipeline (org_config), so
    per-bank custom/configured stages advance without code changes.
    Batch A (2026-06-15). Lazy import to avoid a cycle; best-effort.
    """
    try:
        from utils.core import get_all_pipeline_stage_names
        return get_all_pipeline_stage_names()
    except Exception:
        return set()


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

    if (new_stage not in ALLOWED_ADVANCE_STAGES
            and new_stage not in _configured_stage_names()):
        return False, (
            f"Unknown stage: '{new_stage}'. "
            f"Allowed stages: "
            f"{sorted(ALLOWED_ADVANCE_STAGES | LMS_DEFERRED_STAGES | _configured_stage_names())}"
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
    if not is_credit_handoff_for_deal(deal, old_stage, new_stage):
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
        # Pop both maps for the pipeline-domain cache keys. The MD dashboard
        # (key 'md_dashboard') derives pipeline_value + the FCY/LCY split from
        # the same deals, so a deal mutation must refresh it too — otherwise it
        # serves a stale total for up to its TTL (caused an analytics-vs-dashboard
        # FCY drift on warm re-runs). Add more keys here as future
        # pipeline-domain endpoints get caching.
        for key in ("pipeline_summary", "md_dashboard"):
            _api_module._cache.pop(key, None)
            _api_module._cache_ts.pop(key, None)
    except Exception:
        # If api module can't be imported (test isolation, etc.),
        # invalidation is moot.
        pass
