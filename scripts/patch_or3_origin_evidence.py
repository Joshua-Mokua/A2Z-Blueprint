#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
OR3 - origin is EVIDENCE, not a claim. And the four gates, encoded.

RULING (2026-08-11): "the user will not be selecting the origin, rather the
system will pick it, since a referral will travel from the referral engine and
should have that origin at root; if I pick a deal from the warehouse it should
come with the warehouse origin at root."

Correct, and it corrects OR2, which let the caller DECLARE any origin. Where the
system routed the deal, the system now stamps it:

    referral    stamped by the refer endpoint, in the SAME write as the
                referral fields, so the two can never disagree
    warehouse   stamped when the claimed prospect's deal is attached

Those two are removed from the capture form entirely. Offering "Referral" as a
tick-box invites someone to claim a referral that never travelled through the
engine and never credited anybody - a claim with no evidence behind it.

WHAT REMAINS DECLARABLE, because nothing in a deal record could ever prove it:

    self, events, partnership, lead_gen, contact_centre

A declared origin is REPLACED by a derived one if the deal later routes through
a system channel: what actually happened outranks what someone typed. Verified -
a deal declared "events" and then claimed from the warehouse ends up
origin=warehouse with the lister credited.

THE FOUR GATES (architecture, same ruling): "a clear Origin Gate; a Refining
gate where the RM packages the deal; a Processing/approval gate; and a closure
gate that flows to post-deal closure."

Encoded in pipeline_funnel.GATES rather than written in a document, so a bucket
cannot quietly drift out of the architecture:

    origin      how the deal entered        deal_origin.py
    refining    Initiation, Documentation
    processing  Unit Review, Credit Analysis, Credit Administration, Approval
    closure     TROPS, Opening

    gate_of(bucket)  returns "" rather than guessing - a bucket added later that
                     fits no gate is VISIBLE as unassigned, not silently filed
                     under the last one.
    gates_for(flow)  omits gates this flow does not use: an account journey has
                     no heavy Processing gate, and showing an empty one would
                     imply a step that does not exist.

ONE BODY: origin decides who is credited, refining and processing decide where
the deal is, closure hands it to the customer journey. Every gate reads the SAME
deal record - which is why origin is a field on the deal and not a table beside
it.

Verified: py_compile clean; capture offers 5 origins not 7; both refer paths
stamp; loan and account journeys map onto the gates correctly.

REQUIRES OR2.

Usage (from project root, .venv active):
    python scripts\patch_or3_origin_evidence.py            # dry run
    python scripts\patch_or3_origin_evidence.py --apply
"""
import os
import re
import shutil
import sys

MOD = os.path.join("utils", "deal_origin.py")
PF = os.path.join("utils", "pipeline_funnel.py")
API = os.path.join("utils", "api.py")
WH = os.path.join("utils", "api_warehouse.py")
BACKUP_SUFFIX = ".pre_or3"

ORIGIN_SEG = r'''DEFAULT_ORIGIN = "self"

# ── SYSTEM-DERIVED vs DECLARED (ruling 2026-08-11) ──────────────────────────
# "the user will not be selecting the origin, rather the system will pick it,
#  since a referral will travel from the referral engine and should have that
#  origin at root; if I pick a deal from the warehouse it should come with the
#  warehouse origin at root."
#
# So origin is EVIDENCE, not a claim. Where the system routed the deal, the
# system stamps it and the caller cannot override:
#
#     referral   the refer endpoint stamps it
#     warehouse  the claim stamps it
#
# The rest cannot be derived - nothing in a deal record proves it came from a
# roadshow rather than a cold call - so those remain declarable at creation:
#
#     events, partnership, lead_gen, contact_centre, self
#
# A declarable origin that later routes through a system channel is REPLACED by
# the derived one: what actually happened outranks what someone typed.
SYSTEM_DERIVED = ("referral", "warehouse")


def is_declarable(key: str) -> bool:
    """May a user choose this origin at creation?"""
    k = str(key or "").strip()
    return bool(k) and k not in SYSTEM_DERIVED and is_known(k)


def declarable_origins() -> list:
    """The origins a capture form should offer - system-routed ones excluded,
    because offering "Referral" as a tick-box invites someone to claim a
    referral that never travelled through the engine and never credited
    anybody."""
    return [o for o in origins() if o["key"] not in SYSTEM_DERIVED]


def stamp(deal: dict, origin_key: str, party_code: str = "",
          party_name: str = "") -> dict:
    """Set a SYSTEM-DERIVED origin on a deal, overriding whatever was declared.

    Used by the refer endpoint and the warehouse claim. Mutates and returns the
    deal so a caller cannot forget to save it separately.
    """
    k = str(origin_key or "").strip()
    if not is_known(k):
        return deal
    deal["origin"] = k
    if credits_party(k):
        if party_code:
            deal["origin_party_code"] = str(party_code)
        if party_name:
            deal["origin_party_name"] = str(party_name)
    return deal


'''

GATES_SEG = r'''# ── THE FOUR GATES (architecture, 2026-08-11) ───────────────────────────────
# "we now have a clear Origin Gate; a Refining gate where the RM packages the
#  deal; a Processing/approval gate where it goes through the approvals; and a
#  closure gate that flows to post-deal closure, where in our backend we have
#  mapped a customer journey."
#
# The gates are the SHAPE of the journey; the buckets are its steps. Naming the
# gates here rather than in a document means a bucket cannot quietly drift out
# of the architecture - every bucket declares which gate it serves, and a
# bucket belonging to no gate is visible rather than assumed.
#
#     origin      how the deal entered            utils/deal_origin.py
#     refining    the owner packages it           Initiation, Documentation
#     processing  approvals                       Unit Review, Credit Analysis,
#                                                 Credit Administration
#     closure     disbursement and hand-off       TROPS, Opening
#
# ONE BODY: origin decides who is credited, refining and processing decide
# where the deal is, closure hands it to the customer journey. Each gate reads
# the same deal record rather than keeping its own copy - which is why origin is
# a field on the deal and not a table beside it.
GATES = [
    {"key": "origin", "label": "Origin", "buckets": []},
    {"key": "refining", "label": "Refining",
     "buckets": ["initiation", "documentation"]},
    {"key": "processing", "label": "Processing & Approval",
     "buckets": ["unit_review", "credit_analysis", "credit_admin", "approval"]},
    {"key": "closure", "label": "Closure",
     "buckets": ["trops", "opening"]},
]


def gate_of(bucket_key: str) -> str:
    """Which gate a bucket serves, or "" if it belongs to none.

    Returns empty rather than guessing: a bucket the bank adds later that fits
    no gate should be VISIBLE as unassigned, not silently filed under the last
    one.
    """
    k = str(bucket_key or "").strip()
    for g in GATES:
        if k in g["buckets"]:
            return g["key"]
    return ""


def gates_for(flow: str) -> list:
    """The gates this flow actually passes through, in order, with their
    buckets. Gates with no bucket in this flow are omitted - an account journey
    has no Processing gate, and showing an empty one would imply a step that
    does not exist."""
    chain = buckets_for(flow)
    by_gate = {}
    for b in chain:
        g = gate_of(b["key"])
        by_gate.setdefault(g or "unassigned", []).append(b["key"])
    out = []
    for g in GATES:
        if by_gate.get(g["key"]):
            out.append({"gate": g["key"], "label": g["label"],
                        "buckets": by_gate[g["key"]]})
    if by_gate.get("unassigned"):
        out.append({"gate": "unassigned", "label": "Unassigned",
                    "buckets": by_gate["unassigned"]})
    return out


'''

CREATE = r'''def pipeline_deal_create(
    payload: "PipelineDealCreate",  # noqa: F821 — forward ref to keep import lazy
    user: dict = Depends(get_current_user),
):
    """Create a new pipeline deal.

    Required fields: client_name, staff_code, staff_name, deal_value,
    product_type, stage. Returns the created deal with its
    PipelineManager-assigned id.

    Authorization: any authenticated user may create. The staff_code
    on the payload identifies who owns the deal — typically the
    caller's own code, but managers/admins may create on behalf of
    subordinates. (Server-side enforcement of "create on behalf"
    rules is α5 / GAP-005 scope — conflict resolution.)
    """
    _audit("API_PIPELINE_CREATE_ATTEMPT", user,
           f"client={payload.client_name} value={payload.deal_value}")

    # Lazy imports to avoid circular dependencies at module load
    from utils.api_pipeline_models import (
        PipelineDeal,
        PipelineDealMutationResponse,
    )
    from utils.api_pipeline_mutations import (
        validate_create_payload,
        emit_bsc_trigger,
        invalidate_pipeline_caches,
    )

    # Validate required fields + numeric sanity + stage allowlist
    deal_dict = payload.model_dump(exclude_unset=False)

    # ORIGIN (ruling 2026-08-11). Recorded at creation because it describes how
    # the deal ENTERED and cannot be reconstructed later. An unrecognised value
    # falls back to the default rather than being stored: a typo'd origin would
    # sit outside every configured bucket and appear in analytics as an orphan
    # nobody can filter for.
    try:
        from utils.deal_origin import (is_declarable as _decl,
                                       DEFAULT_ORIGIN as _DEF)
        _org = str(deal_dict.get("origin") or "").strip()
        # SYSTEM-DERIVED ORIGINS CANNOT BE DECLARED (ruling 2026-08-11). A
        # referral gets its origin from the refer endpoint; a warehouse deal
        # from the claim. Accepting them here would let someone tick "Referral"
        # on a deal that never travelled through the engine and never credited
        # anybody - a claim with no evidence behind it.
        deal_dict["origin"] = _org if _decl(_org) else _DEF
    except Exception:
        deal_dict.setdefault("origin", "self")
    # SECURITY (stress Phase 3 — privileged-field injection): PipelineDealCreate
    # uses extra="allow", so a caller can smuggle workflow-controlled fields into
    # the create payload (manager_validated, referral_status, is_referral,
    # disbursed_under_override, etc.). A freshly created deal MUST be born clean —
    # these fields are set only by their respective workflow endpoints (validate /
    # refer / accept / disburse), never at create. Strip them so an RM can't, e.g.,
    # create a deal born pre-validated and inflate the assured pipeline.
    _PRIVILEGED_AT_CREATE = (
        "manager_validated", "validated_by", "validated_at", "validated_by_code",
        "referral_status", "is_referral", "referred_to", "referred_to_code",
        "referred_to_name", "referred_by_code", "referred_by_name", "referred_at",
        "accepted_by", "accepted_at", "declined_by", "declined_at", "decline_reason",
        "disbursed", "disbursed_at", "disbursed_under_override",
        "override_approved", "override_approved_by", "application_id",
        "credit_deferred_to", "credit_deferred_to_code",
        # ORIGIN PARTY is workflow-controlled for the same reason as the
        # referral fields: it decides whose index moves. The caller may declare
        # WHERE a deal came from; they may not declare who gets credited for it.
        # That is set by the workflow that routed the deal - the refer endpoint,
        # or the warehouse claim.
        "origin_party_code", "origin_party_name", "origin_backfilled_at",
    )
    _stripped = [k for k in _PRIVILEGED_AT_CREATE if k in deal_dict]
    for _k in _stripped:
        deal_dict.pop(_k, None)
    if _stripped:
        _audit("API_PIPELINE_CREATE_STRIPPED_PRIVILEGED", user,
                f"ignored injected fields: {','.join(_stripped)}")
    # portfolio_owner_code is a legitimate create-time input for the existing-
    # customer resolution path (P4.5) — validated downstream against the CBS-
    # mapped owner. BUT a bare create supplying it WITHOUT any resolution marker
    # (bsc_credit_to / manager_override_note / client_cif) is an injection — an
    # RM stamping a foreign owner on a deal with no conflict. Default to creator.
    _has_resolution_marker = any(
        str(deal_dict.get(_m) or "").strip()
        for _m in ("bsc_credit_to", "manager_override_note", "client_cif")
    )
    if not _has_resolution_marker and str(deal_dict.get("portfolio_owner_code") or "").strip():
        _injected_po = str(deal_dict.get("portfolio_owner_code") or "").strip()
        _self_code = str(deal_dict.get("staff_code") or "").strip()
        if _injected_po != _self_code:
            _audit("API_PIPELINE_CREATE_PORTFOLIO_OWNER_RESET", user,
                    f"ignored injected portfolio_owner_code={_injected_po} "
                    f"(no resolution marker); defaulted to creator {_self_code}")
            deal_dict["portfolio_owner_code"] = _self_code
            deal_dict.pop("portfolio_owner_name", None)
    # H1 (2026-06-14): the server is authoritative for caller identity.
    # get_current_user carries only JWT claims (username/role) — NOT
    # staff_code/full_name (whoami_detailed re-fetches those from
    # users.json: "never trust JWT for these"). If the client omitted them
    # (thin identity), derive from the caller's record so creation can't be
    # rejected for "Missing required field: staff_code" and the client
    # cannot assert an arbitrary owner. Managers/admins may still create on
    # behalf by explicitly supplying a different staff_code (a5/GAP-005).
    if (not str(deal_dict.get("staff_code") or "").strip()
            or not str(deal_dict.get("staff_name") or "").strip()):
        from utils.core import UserManager as _UM_id
        _full = _UM_id().users.get(str(user.get("username", "") or "")) or {}
        if not str(deal_dict.get("staff_code") or "").strip():
            deal_dict["staff_code"] = str(_full.get("staff_code", "") or "")
        if not str(deal_dict.get("staff_name") or "").strip():
            deal_dict["staff_name"] = str(
                _full.get("full_name", "") or user.get("username", "") or "")
    ok, reason = validate_create_payload(deal_dict)
    if not ok:
        _audit("API_PIPELINE_CREATE_REJECTED", user, reason)
        raise HTTPException(status_code=400, detail=reason)

    # Product gate (single-source-of-truth rule): a deal's product must be a
    # real catalogued product that admin has FULLY set up — catalogue entry +
    # process flow + SLA promise. No free-text products at deal creation; a new
    # product is born in admin (catalogue → flow → SLA) before it can be used.
    _prod = str(deal_dict.get("product_type") or deal_dict.get("product") or "").strip()
    _readiness = _product_readiness(_prod)
    if not _readiness["ready"]:
        _missing = ", ".join(_readiness["missing"]) or "setup"
        _detail = (
            f"Product '{_prod}' cannot be used yet — missing: {_missing}. "
            "Products must be created in Admin with a process flow and SLA "
            "defined before they can be selected on a deal."
            if _readiness["catalogued"] else
            f"Product '{_prod}' is not in the product catalogue. Pick a listed "
            "product, or have an admin add it (with a process flow and SLA) first."
        )
        _audit("API_PIPELINE_CREATE_REJECTED", user, f"product_not_ready|{_prod}|missing={_readiness['missing']}")
        raise HTTPException(status_code=400, detail=_detail)

    # P4.5: mandatory portfolio resolution for EXISTING customers. If the deal
    # carries a client_cif that CBS maps to a DIFFERENT relationship owner than
    # the creating RM, the payload MUST acknowledge it (portfolio_owner_code set)
    # — the server-side mirror of the create-form guard, so a direct API call
    # can't silently book a deal against another RM's portfolio. Self-owned and
    # unknown/unmapped CIFs pass through. Fails OPEN on a CBS outage (logged) so
    # deal creation never hard-depends on CBS availability.
    _cif = str(deal_dict.get("client_cif") or "").strip()
    if _cif:
        try:
            from utils.cbs_manager import get_customer_by_cif as _gcbc
            _cust = _gcbc(_cif)
        except Exception as _exc:  # surfaced, not silent (CGR1)
            logger.warning("portfolio guard: CBS lookup failed for cif=%s: %s", _cif, _exc)
            _cust = None
        if _cust:
            _po = str(_cust.get("relationship_manager_code") or "").strip()
            _creator = str(deal_dict.get("staff_code") or "").strip()
            _po_mapped = bool(_po) and _po.upper() != "UNASSIGNED"
            _resolved = bool(str(deal_dict.get("portfolio_owner_code") or "").strip())
            # Compare with the canonical staff-code helper, NOT a raw string !=.
            # CBS/FLEXCUBE stores zero-padded codes (KE0439) while the roster/login
            # uses KE439; a raw compare told an RM their OWN customer belonged to
            # someone else. same_staff() treats KE0439 == KE439 == 439.
            try:
                from utils.staff_code import same_staff as _same_staff
                _is_same = _same_staff(_po, _creator)
            except Exception:
                _is_same = (_po == _creator)
            if _po_mapped and not _is_same and not _resolved:
                msg = (f"Customer {_cif} is in another RM's portfolio (owner {_po}). "
                       f"Set portfolio_owner_code and choose a resolution path "
                       f"(refer, seek permission, or override).")
                _audit("API_PIPELINE_CREATE_REJECTED", user, msg)
                raise HTTPException(status_code=400, detail=msg)

    # Route through canonical manager (G394 alignment)
    from utils.core import PipelineManager as _PM_for_api
    pm = _PM_for_api()
    # P4-1b: stamp the normalized money set (fx_rate, amount_kes, currency_book,
    # Top-up (P4-credit): the pipeline value of a top-up is the INCREMENT only —
    # the new money the bank commits — not the whole facility. Set deal_value to
    # top_up_amount BEFORE FX stamping so amount_kes (and every downstream value
    # consumer) reflects the increment. The original facility is preserved
    # separately for context (metadata + column) but never enters pipeline value.
    if deal_dict.get("bundle_lines"):
        _lines = [l for l in (deal_dict.get("bundle_lines") or [])
                  if float((l or {}).get("amount") or 0) > 0]
        if not _lines:
            raise HTTPException(status_code=400,
                detail="A bundled loan needs at least one product line with an amount.")
        deal_dict["bundle_lines"] = _lines
        deal_dict["deal_value"]   = round(sum(float(l["amount"]) for l in _lines), 2)
        deal_dict["product_type"] = "Bundled Loan Product"
    if deal_dict.get("is_top_up"):
        try:
            _inc = float(deal_dict.get("top_up_amount") or 0)
        except (TypeError, ValueError):
            _inc = 0.0
        if _inc > 0:
            deal_dict["deal_value"] = _inc
        deal_dict["is_repeat_borrower"] = True  # a top-up implies an existing relationship

    # rate date/source) at booking. Additive + resilient — never blocks create
    # if a currency rate is unconfigured (currency_book is always computed).
    try:
        from utils.fx_engine import stamp_money_fields
        stamp_money_fields(deal_dict, amount_key="deal_value")
    except Exception:
        pass
    # Phase A (PG persistence migration): assign a race-free id from Postgres
    # BEFORE the JSON add, and retry on a primary-key collision so two concurrent
    # creates can never persist a duplicate id or clobber each other. The create
    # uses an INSERT ... ON CONFLICT (id) DO NOTHING RETURNING id (conflict=
    # "raise"): if the id was taken in the race window, no row returns and we
    # raise -> roll back the JSON add -> derive a fresh id -> retry. The PK is the
    # hard guarantee; _next_deal_id_from_pg just keeps collisions rare. Falls
    # back to the JSON len()+1 scheme only when PG is unavailable (dev / no-PG).
    new_id = None
    _last_err = None
    for _attempt in range(5):
        _pg_id = _next_deal_id_from_pg()
        if _pg_id:
            deal_dict["id"] = _pg_id
        else:
            deal_dict.pop("id", None)  # let add_deal fall back to len()+1
        candidate = pm.add_deal(deal_dict)
        try:
            # conflict="raise": fail-closed insert — raises on a duplicate id
            # rather than silently UPDATE-ing (overwriting) the existing deal.
            _db_sync_pipeline_deal(pm.get_deal(candidate), conflict="raise")
            new_id = candidate
            break
        except Exception as e:
            _last_err = e
            # Roll back the JSON add so the stores never diverge (both or neither).
            try:
                pm.delete_deal(candidate, str(user.get("username", "")))
            except Exception:
                logger.error(f"Rollback delete failed for {candidate}")
            _msg = str(e).lower()
            is_collision = ("duplicate key" in _msg or "unique" in _msg
                            or "already exists" in _msg
                            or "primary key" in _msg)
            if is_collision and _db_available():
                _audit("API_PIPELINE_CREATE_ID_COLLISION", user,
                        f"id={candidate} attempt={_attempt+1}; retrying")
                continue
            break
    if not new_id:
        _audit("API_PIPELINE_CREATE_DB_FAILED", user, f"err={_last_err}")
        raise HTTPException(
            status_code=500,
            detail="Could not persist the deal to PostgreSQL — no deal was created.")

    # Mirror Streamlit's emission convention (DEAL_ADDED, line 965)
    _audit("DEAL_ADDED", user,
           f"{new_id}|{payload.client_name}|{payload.deal_value}")

    # BSC trigger (matches Streamlit's _bsc_trigger pattern)
    bsc_ok = emit_bsc_trigger(user.get("username", ""))

    # Bust the summary cache so GET reflects the new deal
    invalidate_pipeline_caches()

    # Fetch the created record (PipelineManager.add_deal returns the
    # id; we re-fetch to return the full record including
    # auto-populated fields like created_at)
    created = pm.get_deal(new_id) or deal_dict
    # SLA S2b: seed the initial step stamp from the create stage.
    _stamp_sla_step(pm, new_id, created, user.get("username", ""))
    created = pm.get_deal(new_id) or created
    return PipelineDealMutationResponse(
        deal=PipelineDeal.model_validate(created),
        status="created",
        bsc_triggered=bsc_ok,
    ).model_dump()


@app.put("/api/pipeline/deals/{deal_id}")
def pipeline_deal_update(
    deal_id: str,
    payload: "PipelineDealUpdate",  # noqa: F821
    user: dict = Depends(get_current_user),
):
    """Update fields on an existing pipeline deal.

    Partial update — only keys present in the request body are
    applied. Stage TRANSITIONS should use the dedicated /advance
    endpoint (which logs the change to the activity stream); PUT
    accepts a stage field but does NOT log a stage-change activity.

    Authorization: caller must have the deal in their cascade scope
    (α2 / G395 alignment). 403 if not.
    """
    _audit("API_PIPELINE_UPDATE_ATTEMPT", user, f"deal_id={deal_id}")

    from utils.api_pipeline_models import (
        PipelineDeal,
        PipelineDealMutationResponse,
    )
    from utils.api_pipeline_mutations import (
        emit_bsc_trigger,
        invalidate_pipeline_caches,
    )
    from utils.api_pipeline_scope import get_visible_staff_codes

    from utils.core import PipelineManager as _PM_for_api
    pm = _PM_for_api()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")

    # Cascade scope check
    visible_codes = get_visible_staff_codes(user)
    sc = str(deal.get("staff_code", "") or "")
    po = str(deal.get("portfolio_owner_code", "") or "")
    if sc not in visible_codes and (not po or po not in visible_codes):
        _audit("API_PIPELINE_UPDATE_FORBIDDEN", user,
               f"deal_id={deal_id} out of scope")
        raise HTTPException(
            status_code=403,
            detail="Deal is outside your cascade scope",
        )

    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(
            status_code=400,
            detail="No fields supplied for update",
        )

    # Phase L: locked once submitted to credit (unless returned/info-requested).
    _enforce_deal_lock(deal, user, "update")

    # State-machine integrity (stress-pass Phase 1): PUT is a field editor, NOT
    # a stage-transition path. Allowing `stage` here bypassed the /advance
    # guards (terminal freeze, backward-sanction, flow validation, SLA stamping,
    # LMS handoff). Stage changes MUST go through /advance so every transition
    # is guarded and logged. Reject a stage field that would actually change the
    # stage (a no-op same-stage value is tolerated and dropped).
    if "stage" in updates:
        if str(updates.get("stage")) != str(deal.get("stage", "")):
            _audit("API_PIPELINE_UPDATE_STAGE_BLOCKED", user,
                   f"deal_id={deal_id} stage={updates.get('stage')}")
            raise HTTPException(
                status_code=400,
                detail=("Stage changes must use the /advance endpoint so the "
                        "transition is validated and logged. Remove 'stage' from "
                        "this update."))
        updates.pop("stage", None)
        if not updates:
            raise HTTPException(
                status_code=400,
                detail="No fields supplied for update (stage changes use /advance).")

    pm.update_deal(deal_id, updates, user.get("username", ""))
    _db_sync_pipeline_deal(pm.get_deal(deal_id))  # H5: mirror to DB-backed reads
    _audit("DEAL_UPDATED", user,
           f"{deal_id}|fields={sorted(updates.keys())}")

    bsc_ok = emit_bsc_trigger(user.get("username", ""))
    invalidate_pipeline_caches()

    updated = pm.get_deal(deal_id) or deal
    return PipelineDealMutationResponse(
        deal=PipelineDeal.model_validate(updated),
        status="updated",
        bsc_triggered=bsc_ok,
    ).model_dump()


'''

REFER = r'''def pipeline_deal_refer_existing(
    deal_id: str,
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user),
):
    """Refer/assign an EXISTING deal to another staff member for pursuit.
    Sets referral_status='pending'; the recipient must accept before they own
    the deal's progression. Any staff with the deal in scope (or an admin) may
    refer. Referring to the current owner is a no-op and rejected."""
    _audit("API_PIPELINE_REFER_EXISTING_ATTEMPT", user, f"deal_id={deal_id}")
    from utils.api_pipeline_scope import get_visible_staff_codes
    from utils.core import PipelineManager as _PM
    from utils.api_pipeline_mutations import invalidate_pipeline_caches

    rcode = str(payload.get("referred_to_code") or "").strip()
    rname = str(payload.get("referred_to_name") or payload.get("referred_to") or "").strip()
    note  = str(payload.get("referral_note") or "").strip()
    if not rcode or not rname:
        raise HTTPException(status_code=400,
                            detail="referred_to_code and referred_to_name are required")

    pm = _PM()
    deal = _get_or_hydrate_deal(pm, deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id} not found")

    actor_code, actor_name, priv = _resolve_actor(user)
    visible = get_visible_staff_codes(user)
    sc = str(deal.get("staff_code", "") or "")
    po = str(deal.get("portfolio_owner_code", "") or "")
    if not priv and sc not in visible and (not po or po not in visible):
        raise HTTPException(status_code=403, detail="Deal is outside your scope")
    if rcode in (sc, po):
        raise HTTPException(status_code=400,
                            detail="That person already owns this deal — nothing to refer.")
    if str(deal.get("referral_status") or "") == "pending":
        raise HTTPException(status_code=400,
                            detail="This deal already has a pending referral awaiting acceptance.")

    pm.update_deal(deal_id, {
        "referral_status":  "pending",
        "referred_to_code": rcode,
        "referred_to":      rname,
        "referred_by_code": actor_code,
        "referred_by_name": actor_name,
        "referral_note":    note,
        "referred_at":      datetime.now().isoformat(),
        "decline_reason":   "",
        # ORIGIN IS EVIDENCE, NOT A CLAIM (ruling 2026-08-11). A deal that
        # travelled through the referral engine carries origin=referral at
        # root, stamped by the engine rather than declared by anyone. Written
        # in the SAME update as the referral fields, so the two can never
        # disagree about the same deal.
        "origin":            "referral",
        "origin_party_code": actor_code,
        "origin_party_name": actor_name,
    }, user.get("username", ""))
    _db_sync_pipeline_deal(pm.get_deal(deal_id))
    _audit("DEAL_REFERRED_EXISTING", user, f"{deal_id}->{rcode}")
    invalidate_pipeline_caches()
    return {"deal_id": deal_id, "referral_status": "pending",
            "referred_to": rname, "referred_to_code": rcode}


'''

WAREHOUSE = r'''"""
utils/api_warehouse — the Deals Warehouse endpoints (additive, new module).

A prospect is not a deal. It is an opportunity nobody owns, on a shared shelf,
until someone claims it - at which point the lister is credited as the referrer
(ruling 2026-08-09: a claim IS the acceptance, and referrals credit on
acceptance).

VISIBLE TO EVERYONE, DELIBERATELY. Unlike deals, the shelf is not
cascade-scoped: the whole point is that an officer with nothing to pursue can
find something. Scoping it would recreate the problem it exists to solve.
Contact details are the exception - see the note on /shelves.

NOT RELEASED TO THE PILOT YET (ruling 2026-08-11): "anything on the warehouse is
not to be released to Alex until I am certain it is well built."
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException

from utils.auth_jwt import get_current_user
from utils.core_audit import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/warehouse", tags=["warehouse"])


def _actor(user: dict):
    """(staff_code, name). Falls back to the username so a prospect always
    records who listed it - that is who gets credited when it is claimed."""
    try:
        from utils.core import UserManager
        rec = (UserManager().users or {}).get(str(user.get("username", "") or "")) or {}
        code = str(rec.get("staff_code") or "").strip()
        name = str(rec.get("full_name") or rec.get("name") or "").strip()
        if code:
            return code, name or code
    except Exception as exc:
        logger.debug("warehouse actor lookup failed: %s", exc)
    u = str(user.get("username", "") or "").strip()
    if not u:
        raise HTTPException(status_code=400,
                            detail="Your identity could not be resolved.")
    return u, u


def _is_admin(user: dict) -> bool:
    return bool(user.get("is_admin") or user.get("can_view_all"))


@router.get("/taxonomy")
def warehouse_taxonomy(user: dict = Depends(get_current_user)):
    """Sectors and towns for the capture form and the shelf filters."""
    from utils.deals_warehouse import sectors, towns
    return {"sectors": sectors(), "towns": towns()}


@router.get("/shelves")
def warehouse_shelves(status: str = "available", town: str = "",
                      sector: str = "", q: str = "",
                      user: dict = Depends(get_current_user)):
    """The shelf, grouped by sector.

    CONTACT DETAILS ARE WITHHELD from the browse view. Anyone in the bank can
    see that an opportunity exists, where it is and roughly what it is worth -
    that is what lets an officer with nothing to pursue find something. The
    named contact and their phone number appear only to the lister, the claimer
    and admin, because a shared shelf of every prospect's personal contact
    details is a data-protection problem rather than a sales tool.
    """
    from utils.deals_warehouse import shelves as _shelves
    code, _name = _actor(user)
    admin = _is_admin(user)
    needle = str(q or "").strip().lower()

    out = {}
    total = 0
    for sec, items in _shelves(status=status or "available").items():
        keep = []
        for r in items:
            if town and str(r.get("town") or "") != town:
                continue
            if sector and sec != sector:
                continue
            if needle and needle not in (str(r.get("name") or "")
                                         + " " + str(r.get("notes") or "")).lower():
                continue
            mine = (str(r.get("created_by_code") or "") == code
                    or str(r.get("claimed_by_code") or "") == code)
            row = {k: r.get(k) for k in
                   ("id", "name", "sector", "town", "status", "estimated_value",
                    "source_event", "notes", "created_by_name", "created_at",
                    "claimed_by_name", "claimed_at", "deal_id")}
            row["mine"] = mine
            if mine or admin:
                row.update({k: r.get(k) for k in
                            ("contact_name", "contact_phone", "contact_email")})
                row["contacts_visible"] = True
            else:
                row["contacts_visible"] = False
            keep.append(row)
            total += 1
        if keep:
            out[sec] = keep
    return {"shelves": out, "total": total, "status": status or "available"}


@router.post("/prospects")
def warehouse_create(payload: dict = Body(default_factory=dict),
                     user: dict = Depends(get_current_user)):
    """List a prospect. Only a name is required."""
    from utils.deals_warehouse import create
    code, name = _actor(user)
    try:
        rec = create(
            name=str(payload.get("name", "") or ""),
            created_by_code=code, created_by_name=name,
            sector=str(payload.get("sector", "") or ""),
            town=str(payload.get("town", "") or ""),
            contact_name=str(payload.get("contact_name", "") or ""),
            contact_phone=str(payload.get("contact_phone", "") or ""),
            contact_email=str(payload.get("contact_email", "") or ""),
            notes=str(payload.get("notes", "") or ""),
            source_event=str(payload.get("source_event", "") or ""),
            estimated_value=float(payload.get("estimated_value") or 0),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_log("WAREHOUSE_CREATE", str(user.get("username", "") or ""),
              detail="%s %s" % (rec["id"], rec["name"]))
    return {"prospect": rec}


@router.post("/prospects/{prospect_id}/claim")
def warehouse_claim(prospect_id: str,
                    user: dict = Depends(get_current_user)):
    """Take a prospect off the shelf.

    Creating the DEAL is a separate step, done by the caller against the normal
    pipeline endpoint with origin=warehouse - so a claim never half-creates a
    deal if deal creation fails. attach_deal records the link afterwards.
    """
    from utils.deals_warehouse import claim
    code, name = _actor(user)
    try:
        rec = claim(prospect_id, code, name)
    except ValueError as exc:
        # 409, not 400: someone else got there first is a conflict, not a
        # malformed request, and the UI should say so differently.
        raise HTTPException(status_code=409, detail=str(exc))
    audit_log("WAREHOUSE_CLAIM", str(user.get("username", "") or ""),
              detail="%s by %s" % (prospect_id, code))
    # The caller creates the deal next, against the normal pipeline endpoint.
    # These are the fields it must carry so the deal arrives with the warehouse
    # origin AT ROOT (ruling 2026-08-11) rather than being declared afterwards.
    # origin_party_* are privileged-at-create, so the create endpoint strips
    # them - /prospects/{id}/deal re-applies them once the deal exists, which
    # is why the claim returns them rather than relying on the caller.
    return {
        "prospect": rec,
        "referrer_code": rec.get("created_by_code"),
        "referrer_name": rec.get("created_by_name"),
        "deal_defaults": {
            "origin": "warehouse",
            "warehouse_prospect_id": rec.get("id"),
            "client_name": rec.get("name"),
        },
    }


@router.post("/prospects/{prospect_id}/deal")
def warehouse_attach_deal(prospect_id: str,
                          payload: dict = Body(default_factory=dict),
                          user: dict = Depends(get_current_user)):
    """Record which deal a claimed prospect became."""
    from utils.deals_warehouse import attach_deal, get
    rec = get(prospect_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No such prospect.")
    code, _n = _actor(user)
    if str(rec.get("claimed_by_code") or "") != code and not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail="Only the person who claimed it can attach the deal.")
    deal_id = str(payload.get("deal_id", "") or "")
    out = attach_deal(prospect_id, deal_id)

    # Stamp the deal itself. This is where the warehouse origin becomes real:
    # the create endpoint strips origin_party_* (a caller must not name who
    # gets credited), so it is applied here, by the workflow that actually
    # routed the deal, once both sides exist.
    if deal_id:
        try:
            from utils.core import PipelineManager
            from utils.deal_origin import stamp
            pm = PipelineManager()
            d = pm.get_deal(deal_id)
            if d:
                stamp(d, "warehouse",
                      str(rec.get("created_by_code") or ""),
                      str(rec.get("created_by_name") or ""))
                d["warehouse_prospect_id"] = str(prospect_id)
                pm.update_deal(deal_id, d, str(user.get("username", "") or ""))
        except Exception as exc:
            logger.warning("could not stamp warehouse origin on %s: %s",
                           deal_id, exc)
    return {"prospect": out}


@router.post("/prospects/{prospect_id}/archive")
def warehouse_archive(prospect_id: str,
                      payload: dict = Body(default_factory=dict),
                      user: dict = Depends(get_current_user)):
    """Take a prospect off the shelf without pursuing it. Lister or admin."""
    from utils.deals_warehouse import archive, get
    rec = get(prospect_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No such prospect.")
    code, _n = _actor(user)
    if str(rec.get("created_by_code") or "") != code and not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail="Only the person who listed it can archive it.")
    reason = str(payload.get("reason", "") or "").strip()
    if not reason:
        raise HTTPException(status_code=400,
                            detail="Say why - an archived prospect with no reason "
                                   "tells the next person nothing.")
    out = archive(prospect_id, code, reason)
    audit_log("WAREHOUSE_ARCHIVE", str(user.get("username", "") or ""),
              detail="%s: %s" % (prospect_id, reason[:60]))
    return {"prospect": out}


@router.get("/mine")
def warehouse_mine(user: dict = Depends(get_current_user)):
    """What I listed and what I claimed - including what has gone stale.

    The stale list is the point: a prospect nobody has taken in a month is
    either worth chasing differently or worth archiving, and both need the
    person who listed it to decide.
    """
    from utils.deals_warehouse import all_prospects, stale
    code, _n = _actor(user)
    listed = [r for r in all_prospects()
              if str(r.get("created_by_code") or "") == code]
    claimed = [r for r in all_prospects()
               if str(r.get("claimed_by_code") or "") == code]
    stale_mine = [r for r in stale(30)
                  if str(r.get("created_by_code") or "") == code]
    return {
        "listed": sorted(listed, key=lambda r: str(r.get("created_at") or ""),
                         reverse=True),
        "claimed": sorted(claimed, key=lambda r: str(r.get("claimed_at") or ""),
                          reverse=True),
        "stale": stale_mine,
        "counts": {"listed": len(listed), "claimed": len(claimed),
                   "stale": len(stale_mine)},
    }
'''


def main():
    apply = "--apply" in sys.argv
    for p in (MOD, PF, API, WH):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Apply patch_or2_origin_wiring.py and" % p)
            print("       patch_dw1_warehouse.py first.")
            return 1

    mo = open(MOD, encoding="utf-8").read()
    pf = open(PF, encoding="utf-8").read()
    api = open(API, encoding="utf-8").read()

    if "SYSTEM_DERIVED" in mo:
        print("ABORT: SYSTEM_DERIVED already present - OR3 looks applied.")
        return 1
    if "def origins(" not in mo:
        print("ABORT: apply patch_or1_deal_origin.py first.")
        return 1

    i = mo.index('DEFAULT_ORIGIN = "self"')
    j = mo.index("def origins(")
    mo = mo[:i] + ORIGIN_SEG + mo[j:]
    print("  ok  deal_origin - system-derived vs declarable")

    if "GATES = [" in pf:
        print("ABORT: GATES already present.")
        return 1
    a = pf.index('CLOSED = ("Closed Won", "Closed Lost")')
    pf = pf[:a] + GATES_SEG + pf[a:]
    print("  ok  pipeline_funnel - the four gates")

    c = api.index("def pipeline_deal_create(")
    m = re.search(r'\n@app\.(get|post)\("/api/', api[c + 40:])
    api = api[:c] + CREATE + api[c + 40 + m.start() + 1:]
    d = api.index("def pipeline_deal_refer_existing(")
    m2 = re.search(r'\n@app\.(get|post)\("/api/', api[d + 40:])
    api = api[:d] + REFER + api[d + 40 + m2.start() + 1:]
    print("  ok  api - create rejects declared system origins; refer stamps")

    # A system-routed origin must not be declarable, or the evidence rule is
    # decoration.
    if "_decl(_org)" not in CREATE:
        print("ABORT: create still accepts any known origin - a caller could")
        print("       tick Referral on a deal that never travelled the engine.")
        return 1
    if '"origin":            "referral"' not in REFER:
        print("ABORT: the refer endpoint does not stamp the origin.")
        return 1
    if "stamp(d, \"warehouse\"" not in WAREHOUSE:
        print("ABORT: the warehouse does not stamp its origin.")
        return 1
    if "def gate_of(" not in GATES_SEG or 'return ""' not in GATES_SEG:
        print("ABORT: gate_of must return empty rather than guessing a gate.")
        return 1
    print("  ok  post-checks: evidence enforced, gates fail visibly")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((MOD, mo), (PF, pf), (API, api), (WH, WAREHOUSE)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (MOD, PF, API, WH):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nRestart uvicorn. The capture form should offer five origins, not")
    print("seven - Referral and Warehouse are stamped by the system.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
