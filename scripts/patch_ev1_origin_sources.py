#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
EV1 - events and partnerships become pickable, and deals point at them.

RULING (2026-08-11): "one creates an event first, then from the event one can
directly create a deal or refer a deal ... the actuals are of course
quantifiable after the closure."

WHAT WE FOUND BEFORE BUILDING, and why this is smaller than expected. The event
object ALREADY EXISTS and is richer than the one described:
data/sponsored_events.json holds 12 events with name, partner, branch,
department, dates, budget, spend, targets for leads / accounts / deposits /
media value, and ROI. data/partnerships.json holds 50.

They had NO API, NO frontend, and no way for a deal to reference one. The object
was never the gap - REACHABILITY was. So this exposes what exists rather than
building a second event table beside it.

ADDS
  utils/origin_sources.py       events, partnerships, options(), attribution()
  GET /api/pipeline/origin-sources?origin=   what to pick for this origin
  GET /api/pipeline/events/{id}/attribution  what the DEALS say it produced

  The capture form gains a second dropdown - "Which one?" - that appears ONLY
  for origins with something to pick. Changing the origin clears the previous
  choice, and the SERVER clears a source id that does not belong to the chosen
  origin, so a stale event_id left on a form cannot silently attribute a
  walk-in deal to a roadshow.

DERIVED ACTUALS COUNT ONLY CLOSED-WON DEALS (ruling: "quantifiable after the
closure"). A lead that never converted did not produce an account, and counting
it would flatter every event's return:

    derived.leads      every deal pointing at the event
    derived.accounts   those that closed won
    derived.value      the value of those that closed won

BOTH figures are returned - `derived` and `stored`. The stored actuals are
generated test data (confirmed), but replacing them silently would leave nobody
able to tell which number they were reading, and the two disagreeing is itself
information.

MEASURED against the real files: 12 events (3 active), 50 partnerships (49
active); an event with 3 attributed deals of which 1 closed won reports 3 leads
and 1 account.

NEXT: an events page showing derived against target, and the same treatment for
Lead Generators - which has no object yet and will need one.

Usage (from project root, .venv active):
    python scripts\patch_ev1_origin_sources.py            # dry run
    python scripts\patch_ev1_origin_sources.py --apply
"""
import os
import re
import shutil
import sys

MOD = os.path.join("utils", "origin_sources.py")
API = os.path.join("utils", "api.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
PAGE = os.path.join("frontend", "web", "src", "pages", "PipelineCreate.tsx")
TYPES = os.path.join("frontend", "web", "src", "types", "pipeline.ts")
BACKUP_SUFFIX = ".pre_ev1"

MODULE = r'''"""
utils/origin_sources — the events and partnerships a deal can point at.

RULING (2026-08-11): "for events, partnerships and lead generators we will build
it so one creates an event first, then from the event one can directly create a
deal or refer a deal ... the actuals are of course quantifiable after the
closure."

WHAT WAS ALREADY HERE, and why this module is small. data/sponsored_events.json
already holds 12 events carrying name, partner, branch, department, start and
end dates, budget, spend, targets for leads / accounts / deposits / media value,
and ROI. data/partnerships.json holds 50 with partner type, sector, RM owner and
expected volume.

They had NO API, NO frontend, and no way for a deal to reference one. The object
was never the gap - reachability was. So this exposes what exists rather than
building a second event table beside it.

DERIVED ACTUALS, AFTER CLOSURE. The actual_* fields on an event are generated
test figures (confirmed 2026-08-11). Once deals carry an event_id, the honest
figures come from the deals themselves - and only from deals that CLOSED WON,
because a lead that never converted did not produce an account and counting it
would flatter every event's return.

Both are reported: `stored` (what the file says) and `derived` (what the deals
say). Replacing the stored figure silently would leave nobody able to tell which
number they were looking at, and the two disagreeing is itself information.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_EVENTS = os.path.join("data", "sponsored_events.json")
_PARTNERSHIPS = os.path.join("data", "partnerships.json")

CLOSED_WON = "Closed Won"


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        # Read-only source: an unreadable file means no options to offer, which
        # is visible in the UI. It must not raise into a deal-capture request.
        logger.warning("origin source %s unreadable: %s", path, exc)
        return []
    if isinstance(data, dict):
        data = list(data.values())
    return [d for d in data if isinstance(d, dict)]


def events(active_only: bool = False) -> list:
    """Sponsored events, newest first.

    `active_only` filters to events still running - useful for a capture form,
    where offering an event that ended eight months ago invites a mis-tag.
    """
    out = _load(_EVENTS)
    if active_only:
        out = [e for e in out
               if str(e.get("status") or "").strip().lower() in ("active", "planned")]
    return sorted(out, key=lambda e: str(e.get("start_date") or ""), reverse=True)


def partnerships(active_only: bool = False) -> list:
    out = _load(_PARTNERSHIPS)
    if active_only:
        out = [p for p in out if p.get("activated")
               or str(p.get("status") or "").strip().lower() == "active"]
    return sorted(out, key=lambda p: str(p.get("partner_name") or ""))


def get_event(event_id: str) -> Optional[dict]:
    eid = str(event_id or "").strip()
    return next((e for e in _load(_EVENTS) if str(e.get("id") or "") == eid), None)


def get_partnership(partner_id: str) -> Optional[dict]:
    pid = str(partner_id or "").strip()
    return next((p for p in _load(_PARTNERSHIPS) if str(p.get("id") or "") == pid), None)


def options(origin_key: str, active_only: bool = True) -> list:
    """The pickable sources for an origin: [{id, label, sub}].

    Returns [] for origins with nothing to pick - self, referral, warehouse -
    so a capture form can simply not render a second dropdown rather than
    special-casing each origin.
    """
    k = str(origin_key or "").strip()
    if k == "events":
        return [{"id": str(e.get("id") or ""),
                 "label": str(e.get("name") or e.get("id") or ""),
                 "sub": " · ".join(x for x in (
                     str(e.get("branch") or ""),
                     str(e.get("start_date") or "")[:10],
                     str(e.get("event_category") or "")) if x)}
                for e in events(active_only) if e.get("id")]
    if k == "partnership":
        return [{"id": str(p.get("id") or ""),
                 "label": str(p.get("partner_name") or p.get("id") or ""),
                 "sub": " · ".join(x for x in (
                     str(p.get("partner_type") or ""),
                     str(p.get("sector") or "")) if x)}
                for p in partnerships(active_only) if p.get("id")]
    return []


def source_field(origin_key: str) -> str:
    """Which field on the deal holds the chosen source for this origin."""
    return {"events": "event_id", "partnership": "mou_id"}.get(
        str(origin_key or "").strip(), "")


def attribution(event_id: str, deals: list) -> dict:
    """What the DEALS say this event produced, against what the file says.

    Only CLOSED WON deals count toward accounts and value (ruling 2026-08-11:
    "the actuals are of course quantifiable after the closure"). A lead that
    never converted did not produce an account, and counting it would flatter
    every event's return.

    Both figures are returned. Silently replacing the stored number would leave
    nobody able to tell which they were looking at - and the two disagreeing is
    itself worth seeing.
    """
    eid = str(event_id or "").strip()
    mine = [d for d in (deals or [])
            if str(d.get("event_id") or "").strip() == eid]
    won = [d for d in mine if str(d.get("stage") or "") == CLOSED_WON]

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    ev = get_event(eid) or {}
    spent = float(ev.get("spent_kes") or ev.get("budget_kes") or 0)
    won_value = round(sum(_val(d) for d in won), 2)
    return {
        "event_id": eid,
        "derived": {
            "leads": len(mine),
            "accounts": len(won),
            "value": won_value,
            "cost_per_lead": round(spent / len(mine), 2) if mine else 0.0,
            "cost_per_account": round(spent / len(won), 2) if won else 0.0,
        },
        "stored": {
            "leads": ev.get("actual_leads"),
            "accounts": ev.get("actual_accounts"),
            "cost_per_lead": ev.get("cost_per_lead_kes"),
            "cost_per_account": ev.get("cost_per_account_kes"),
        },
        "target": {
            "leads": ev.get("target_leads"),
            "accounts": ev.get("target_accounts"),
        },
        "spent_kes": spent,
    }
'''

ENDPOINTS = r'''@app.get("/api/pipeline/origin-sources")
def pipeline_origin_sources(origin: str = "", active_only: bool = True,
                            user: dict = Depends(get_current_user)):
    """What a deal can point at for this origin.

    Ruling 2026-08-11: "one creates an event first, then from the event one can
    directly create a deal or refer a deal." So events and partnerships are
    PICKED, not typed - which is what makes "what did that roadshow produce"
    answerable later.

    Returns [] for origins with nothing to pick, so the capture form can simply
    not render a second dropdown rather than special-casing each origin.
    """
    from utils.origin_sources import options, source_field
    o = str(origin or "").strip()
    return {"origin": o, "field": source_field(o),
            "options": options(o, bool(active_only))}


@app.get("/api/pipeline/events/{event_id}/attribution")
def pipeline_event_attribution(event_id: str,
                               user: dict = Depends(get_current_user)):
    """What the DEALS say this event produced, against what the file says.

    Only closed-won deals count toward accounts and value (ruling 2026-08-11:
    "the actuals are quantifiable after the closure"). Both figures are
    returned - replacing the stored one silently would leave nobody able to
    tell which number they were reading.
    """
    from utils.origin_sources import attribution, get_event
    if not get_event(event_id):
        raise HTTPException(status_code=404, detail="No such event.")
    return attribution(event_id, _acquire_scoped_deals(user))


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
        # The chosen SOURCE for that origin - which event, which partnership.
        # A source id that does not belong to the chosen origin is CLEARED, so
        # a stale event_id left on a form cannot silently attribute a walk-in
        # deal to a roadshow.
        from utils.origin_sources import source_field as _sfield
        _field = _sfield(deal_dict["origin"])
        for _f in ("event_id", "mou_id"):
            if _f != _field:
                deal_dict.pop(_f, None)
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

TS_NEW = r'''export interface OriginSourceOption { id: string; label: string; sub: string }
export async function fetchOriginSources(
  origin: string, activeOnly = true,
): Promise<{ origin: string; field: string; options: OriginSourceOption[] }> {
  const q = new URLSearchParams({ origin, active_only: String(activeOnly) });
  return getJson<{ origin: string; field: string; options: OriginSourceOption[] }>(
    `/pipeline/origin-sources?${q.toString()}`);
}
'''

IFACE = r'''export interface CreateDealRequest {
  // Required
  client_name:           string;
  staff_code:            string;
  staff_name:            string;
  deal_value:            number;
  product_type:          string;
  stage:                 string;

  // Optional but commonly supplied
  client_type?:          string;     // 'Individual' or 'Business'
  currency?:             string;     // ISO code; defaults KES (admin FX table)
  segment?:              string;     // segment within client type (cascade)
  sector?:               string;     // CBK economic sector (Business clients)
  mou_id?:               string;     // partnership/MOU id (Individual clients)
  /** How the deal entered - one of the DECLARABLE origins. The server
   *  validates it and replaces any system-routed value (referral, warehouse),
   *  which are stamped by the workflow that actually routed the deal. */
  origin?:               string;
  /** The chosen source for that origin - a sponsored event. Cleared server-side
   *  if it does not belong to the origin. */
  event_id?:             string;
  mou_title?:            string;     // MOU title or free-text partner ("Other")
  client_cif?:           string;     // δ2: CBS CIF when client matched in CBS lookup
  is_ntb?:               boolean;
  pipeline_category?:    string;
  is_top_up?:            boolean;   // true if topping up an existing facility
  top_up_amount?:        number;    // the increment (becomes pipeline value)
  bundle_lines?:         { product_type: string; amount: number }[]; // Bundled Loan Product lines
  original_facility_amount?: number; // existing facility size (context only)
  probability?:          number;     // 0..1 (NOT 0..100)
  next_action?:          string;
  next_action_date?:     string;     // YYYY-MM-DD
  expected_close?:       string;     // YYYY-MM-DD
  notes?:                string;
  source?:               string;
  unit?:                 string;
  account_number?:       string;
  phone?:                string;
  email?:                string;

  // Conflict resolution fields (β3)
  portfolio_owner_code?:    string;
  portfolio_owner_name?:    string;
  bsc_credit_to?:           string;
  manager_override_note?:   string;
}'''

PAGE_NEW = r'''// v10.512 Phase 4 Batch β3 — PipelineCreate page.
//
// Form at /pipeline/new for creating a new pipeline deal. Covers the
// happy path AND the α5 portfolio-conflict resolution (Refer / Seek
// permission / Override-with-note).
//
// Architecture note — Streamlit/backend semantic inversion:
//   Streamlit's `_bsc_credit` calculation in pages/3_pipeline.py inverts
//   the bsc_credit_to value relative to what the backend rules in
//   utils/api_pipeline_mutations.py::is_override_semantics expect:
//
//   Streamlit "Seek permission"  → bsc_credit_to = creator      (me)
//   Streamlit "Pursue (override)" → bsc_credit_to = portfolio_owner
//
//   Backend rules:
//   bsc_credit_to == portfolio_owner_name → seek-permission (no note)
//   bsc_credit_to == anything else          → override (note required)
//
//   So Streamlit's "Seek permission" payload triggers the backend's
//   OVERRIDE rule and fails validation (no note collected). This is
//   the α5 doctrine note's "latent UX bug surfaced in α5 inspection."
//
//   This page implements the BACKEND's semantics — internally
//   consistent, server-validated. A future batch should fix Streamlit
//   to match (not β3 scope). Documenting the divergence in REVIVAL_LEDGER
//   is part of β3's deliverable.
//
// Deliberately NOT in β3 (deferred to later batches):
//   - CBS auto-lookup (needs new GET /api/cbs/customer/{cif} endpoint)
//   - Product dropdown driven by GET /api/pipeline/products
//   - Duplicate detection across deals (client-side scan or server endpoint)
//   - Backup staff selector
//   - Save-as-draft path
//   - Sector / decision-level / ID type / phone fields
//   - Competitors multiselect
//   - Linked deals for accounts pipeline
//   - Manager "assign to" override

import { useEffect, useMemo, useState } from 'react';
import { BundleLinesEditor, type BundleLine } from '@/components/BundleLinesEditor';
import { useNavigate } from 'react-router-dom';
import { useBranding } from '@/hooks/useBranding';
import { useRole } from '@/hooks/useRole';
import { useToast } from '@/components/Toast';
import { fetchDealOrigins, fetchOriginSources,
         type DealOrigin, type OriginSourceOption } from '@/lib/api';
import { usePipelineDealMutations } from '@/hooks/usePipelineDealMutations';
import { useFxRates } from '@/hooks/useFxRates';
import { Card } from '@/components/Card';
import { StaffPicker } from '@/components/StaffPicker';
import { PageHeader } from '@/components/PageHeader';
import { Button } from '@/components/Button';
import { Badge } from '@/components/Badge';
import { Input } from '@/components/Input';
import { CustomerSearchInput } from '@/components/CustomerSearchInput';
import { fetchCbsCustomer, fetchPipelineConfig, fetchCustomerPortfolioOwner, ApiValidationError, type CustomerPortfolioOwner, type StaffMember } from '@/lib/api';
import {
  PIPELINE_CATEGORIES, INITIAL_STAGES_BY_CATEGORY,
  SOURCE_OPTIONS,
  MIN_OVERRIDE_NOTE_LEN,
  type CreateDealRequest, type ReferDealRequest,
  type PipelineConfig,
} from '@/types/pipeline';
import { segmentToCustomerType, type CbsCustomer } from '@/types/cbs';
import { getAdminBranches, type AdminBranch } from '@/lib/api';


// ── Conflict resolution path discriminator ──────────────────────────────

type ConflictPath = 'refer' | 'seek_permission' | 'override';


// ── Page component ──────────────────────────────────────────────────────

// Map a product to its class (asset/liability/insurance/other) using the
// admin product_catalogue, mirroring the backend _classify_product: exact
// match first, then containment. Drives which stage_flow the create form's
// Initial-stage dropdown follows. Returns null when no catalogue is loaded so
// the caller can fall back to the legacy category map.
type ProductClass = 'asset' | 'liability' | 'insurance' | 'other';
const PRODUCT_CLASS_MAP: Record<string, ProductClass> = {
  Assets: 'asset',
  Liabilities: 'liability',
  Insurance: 'insurance',
  Transactional: 'other',
  Investments: 'other',
};
function classifyProduct(
  productType: string,
  catalogue?: Record<string, string[]>,
): ProductClass | null {
  if (!catalogue) return null;
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
  const n = norm(productType);
  if (!n) return null;
  for (const [cls, prods] of Object.entries(catalogue)) {
    if (prods.some((p) => norm(p) === n)) return PRODUCT_CLASS_MAP[cls] ?? 'other';
  }
  for (const [cls, prods] of Object.entries(catalogue)) {
    if (prods.some((p) => {
      const pn = norm(p);
      return pn !== '' && (pn.includes(n) || n.includes(pn));
    })) return PRODUCT_CLASS_MAP[cls] ?? 'other';
  }
  return 'other';
}

export function PipelineCreate() {
  const navigate = useNavigate();
  const { branding } = useBranding();
  const { user } = useRole();
  const { toast } = useToast();
  const mutations = usePipelineDealMutations();

  // ── Core form state ──────────────────────────────────────────────────

  const [clientName,  setClientName]  = useState('');
  const [config,      setConfig]      = useState<PipelineConfig | null>(null);
  const [clientType,  setClientType]  = useState<string>('');
  const [segment,     setSegment]     = useState<string>('');
  const [sector,      setSector]      = useState<string>('');
  const [currency,    setCurrency]    = useState<string>('KES');
  // Item 1: originating branch. Auto-derived from the creator's own branch for
  // branch staff; Head-Office RMs pick one here (their own unit is 'Head Office').
  const [branches,          setBranches]          = useState<AdminBranch[]>([]);
  const [originatingBranch, setOriginatingBranch] = useState<string>('');
  const creatorIsHeadOffice = ((user?.unit || '').trim().toLowerCase() === 'head office')
                              || !((user?.unit || '').trim());
  const [mouId,       setMouId]       = useState<string>('');     // Individual: selected MOU id
  const [mouQuery,    setMouQuery]    = useState<string>('');     // MOU picker search filter
  const [mouOpen,     setMouOpen]     = useState<boolean>(false); // MOU dropdown open
  const [otherText,   setOtherText]   = useState<string>('');     // free text when 'Other' chosen
  const SENTINEL_OTHER = '__OTHER__';
  const [isNtb,       setIsNtb]       = useState(false);
  // ORIGIN (ruling 2026-08-11). Only DECLARABLE origins are offered - referral
  // and warehouse are stamped by the workflow that routed the deal, so
  // offering them here would invite a claim with no evidence behind it.
  const [origin, setOrigin] = useState('self');
  const [originOpts, setOriginOpts] = useState<DealOrigin[]>([]);
  // The SOURCE for that origin - which event, which partnership. Empty for
  // origins with nothing to pick, so no second dropdown renders.
  const [sourceOpts, setSourceOpts] = useState<OriginSourceOption[]>([]);
  const [sourceId, setSourceId] = useState('');
  const [accountNumber, setAccountNumber] = useState('');

  // γ2: Tracks the CBS customer picked via the autofill dropdown.
  // null means no autofill match (free-text fallback). The picked
  // customer drives the "✓ matched in CBS" badge under the input
  // and lets us derive isNtb=false automatically.
  const [pickedCustomer, setPickedCustomer] = useState<CbsCustomer | null>(null);

  // δ2: Direct CIF entry. Separate from pickedCustomer so users who
  // KNOW the CIF can type it without name-searching first. Auto-populated
  // when user picks a customer via the name dropdown. The "Fetch" button
  // does a GET /api/cbs/customers/{cif} lookup and autofills the form
  // from the returned customer record.
  const [clientCif,     setClientCif]     = useState<string>('');
  const [cifLookupLoading, setCifLookupLoading] = useState<boolean>(false);
  const [cifLookupError,   setCifLookupError]   = useState<string | null>(null);

  const [category,    setCategory]    = useState<string>('Loan');
  const [isTopUp,     setIsTopUp]     = useState<boolean>(false);
  const [existingAmt, setExistingAmt] = useState<string>('');
  const [topUpAmt,    setTopUpAmt]    = useState<string>('');
  const [productType, setProductType] = useState('');
  const [dealValue,   setDealValue]   = useState<string>('');     // string so input keeps cursor position
  const [bundleLines, setBundleLines] = useState<BundleLine[]>([]);
  const [bundleTotal, setBundleTotal] = useState<number>(0);
  const isBundle = productType.trim() === 'Bundled Loan Product';
  const [stage,       setStage]       = useState<string>('Lead');
  // (Manual probability slider removed — win probability is now DERIVED from the
  //  selected product flow's stage; see derivedWinProbability below.)

  const [nextAction,     setNextAction]     = useState('');
  const [nextActionDate, setNextActionDate] = useState('');
  const [expectedClose,  setExpectedClose]  = useState('');
  const [source,         setSource]         = useState<string>('Existing relationship');
  const [notes,          setNotes]          = useState('');
  const [contactPhone,   setContactPhone]   = useState('');
  const [contactEmail,   setContactEmail]   = useState('');

  // ── Conflict resolution state ────────────────────────────────────────

  const [hasConflict, setHasConflict] = useState(false);
  const [portfolioOwnerCode, setPortfolioOwnerCode] = useState('');
  const [portfolioOwnerName, setPortfolioOwnerName] = useState('');
  const [conflictPath,       setConflictPath]       = useState<ConflictPath>('seek_permission');

  // P2: CBS portfolio-owner auto-detection (existing customers). detectedOwner
  // holds the last lookup; the effect below auto-fills the conflict fields.
  const [detectedOwner, setDetectedOwner] = useState<CustomerPortfolioOwner | null>(null);
  const [ownerDetecting, setOwnerDetecting] = useState(false);
  const [referredTo,         setReferredTo]         = useState('');     // refer path only
  const [referralNote,       setReferralNote]       = useState('');     // refer path only

  // First-class "refer to a colleague" mode on the create page. When on, the
  // form collapses to client + recipient + note; deal-detail fields are hidden
  // and not required (the recipient completes the deal once they accept).
  const [referMode,      setReferMode]      = useState(() => {
    try { return new URLSearchParams(window.location.search).get('refer') === '1'; }
    catch { return false; }
  });
  const [referRecipient, setReferRecipient] = useState<StaffMember | null>(null);
  const [overrideNote,       setOverrideNote]       = useState('');     // override path only

  // ── Submit state ─────────────────────────────────────────────────────
  //
  // β5.0 polish: replaced single submitError with two state slices so we
  // can render field-level errors inline AND a banner for non-field
  // errors (network/server failures). Pattern:
  //   fieldErrors[fieldName] = "human readable message"  → inline + red border
  //   formError              = "human readable message"  → banner at top
  //
  // The banner sits at the TOP of the form (not bottom) so users can
  // see it without scrolling — the bug β5.0 fixes is that the old
  // banner was at the bottom and users missed it entirely.

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError,   setFormError]   = useState<string | null>(null);

  // ── Derived values ───────────────────────────────────────────────────

  // Admin config drives the segment cascade, sectors, and per-class stage
  // flows. Best-effort — the form falls back to legacy defaults if it can't
  // load.
  // The declarable origins, from config - so an eighth channel appears here
  // without a frontend change.
  useEffect(() => {
    let alive = true;
    void (async () => {
      try {
        const r = await fetchDealOrigins();
        if (!alive) return;
        const declarable = r.origins.filter(
          (o) => o.key !== 'referral' && o.key !== 'warehouse');
        setOriginOpts(declarable);
        setOrigin((cur) => (declarable.some((o) => o.key === cur)
          ? cur : (r.default || 'self')));
      } catch {
        // A failed lookup must not block deal capture - the server defaults
        // the origin anyway, so the form stays usable.
        if (alive) setOriginOpts([]);
      }
    })();
    return () => { alive = false; };
  }, []);

  // Reload the source list whenever the origin changes, and clear any previous
  // choice - a stale event_id left behind would attribute this deal to the
  // wrong roadshow. The server clears it too; doing it here keeps the form
  // honest about what it is about to send.
  useEffect(() => {
    let alive = true;
    setSourceId('');
    void (async () => {
      try {
        const r = await fetchOriginSources(origin);
        if (alive) setSourceOpts(r.options ?? []);
      } catch {
        if (alive) setSourceOpts([]);
      }
    })();
    return () => { alive = false; };
  }, [origin]);
  useEffect(() => {
    let active = true;
    fetchPipelineConfig()
      .then((c) => { if (active) setConfig(c); })
      .catch(() => { /* fall back to category-based stages, empty segments */ });
    // Item 1: load branches for the Head-Office RM originating-branch picker.
    getAdminBranches()
      .then((r) => setBranches((r.branches || []).filter((b) => b.active !== false)))
      .catch(() => { /* picker will be empty; validation still guards HO RMs */ });
    return () => { active = false; };
  }, []);

  // Product class drives the stage flow (admin config) — loan vs deposit etc.
  const productClass = useMemo(
    () => classifyProduct(productType, config?.product_catalogue),
    [productType, config],
  );
  // Config-driven categories (admin-authored via deal_categories), with the
  // built-in PIPELINE_CATEGORIES as the pre-config fallback.
  const categories = useMemo<string[]>(
    () => {
      const cfg = config?.deal_categories ?? [];
      // A2a: show only pipeline-surfaced categories (balance-sheet class);
      // dormant deal-types are kept in config but hidden from the dropdown.
      const surfaced = cfg.filter((c) => (c.surface ?? 'pipeline') !== 'dormant');
      const list = surfaced.length ? surfaced : cfg;
      return list.length ? list.map((c) => c.category) : [...PIPELINE_CATEGORIES];
    },
    [config],
  );
  // Initial stages for a category: admin-config flow first, then the legacy
  // per-category map, then a minimal default — never throws for a new category.
  const stagesForCategory = (cat: string): string[] => {
    const fromCfg = config?.deal_categories?.find((c) => c.category === cat)?.stages;
    if (fromCfg && fromCfg.length) return [...fromCfg];
    const legacy = (INITIAL_STAGES_BY_CATEGORY as Record<string, readonly string[]>)[cat];
    return legacy ? [...legacy] : ['Lead'];
  };
  const stageOptions = useMemo(() => {
    // Resolution precedence mirrors the server's _stage_flow_for:
    //   1. product_flows[productType] — the product's OWN flow (each product
    //      can diverge, with its own stages + per-stage target_days + win %).
    //   2. stage_flows[productClass]  — the per-class flow.
    //   3. built-in per-category list — pre-config fallback.
    // "Initial stage" excludes terminal stages.
    const isTerminal = (s: string) => s === 'Closed Won' || s === 'Closed Lost';
    const pflow = config?.product_flows?.[productType];
    if (pflow && Array.isArray(pflow.stages) && pflow.stages.length) {
      const names = pflow.stages
        .map((s) => String(s.stage ?? '').trim())
        .filter((s) => s && !isTerminal(s));
      if (names.length) return names;
    }
    const flows = config?.stage_flows;
    if (flows && productClass && flows[productClass]?.length) {
      return flows[productClass].filter((s) => !isTerminal(s));
    }
    return stagesForCategory(category);   // config-driven, with legacy fallback
  }, [config, productType, productClass, category]);

  // The per-stage SLA target (days) for the currently selected stage, from the
  // product's flow — so create-time shows the stage's promise alongside its win
  // probability. Null when the product has no flow or the stage carries none.
  const selectedStageTargetDays = useMemo<number | null>(() => {
    const pflow = config?.product_flows?.[productType];
    if (!pflow || !Array.isArray(pflow.stages)) return null;
    const target = stage.trim().toLowerCase();
    for (const s of pflow.stages) {
      if (String(s.stage ?? '').trim().toLowerCase() === target) {
        const t = Number(s.target_days);
        return Number.isFinite(t) && t > 0 ? t : null;
      }
    }
    return null;
  }, [config, productType, stage]);

  // Win probability is DERIVED from the chosen product's flow at the selected
  // stage (admin-authored), exactly as the server derives it on read — never a
  // manual figure. Null when the product has no flow or the stage carries no
  // win_probability. Mirrors _flow_stage_win_probability server-side.
  const derivedWinProbability = useMemo<number | null>(() => {
    const flow = config?.product_flows?.[productType];
    if (!flow || !Array.isArray(flow.stages)) return null;
    const target = stage.trim().toLowerCase();
    for (const s of flow.stages) {
      if (String(s.stage ?? '').trim().toLowerCase() === target) {
        const wp = s.win_probability;
        if (wp === null || wp === undefined) return null;
        const v = Number(wp);
        return Number.isFinite(v) && v >= 0 && v <= 100 ? v : null;
      }
    }
    return null;
  }, [config, productType, stage]);

  // Client business lines (Consumer / Commercial / CIB) — admin-configurable.
  // The selected type's `field` (mou|sector) drives the third selector.
  const clientTypes = useMemo(
    () => config?.client_types ?? [
      { key: 'Consumer',   label: 'Consumer',                       field: 'mou' as const },
      { key: 'Commercial', label: 'Commercial',                     field: 'sector' as const },
      { key: 'CIB',        label: 'Corporate & Investment Banking', field: 'sector' as const },
    ],
    [config],
  );
  const clientField = useMemo(
    () => clientTypes.find((t) => t.key === clientType)?.field ?? 'sector',
    [clientTypes, clientType],
  );
  const usesSector = clientField === 'sector';

  // Segment cascade off client type; sectors from config.
  const segmentOptions = useMemo(
    () => config?.customer_segments?.[clientType] ?? [],
    [config, clientType],
  );
  // Client-type-aware third field: sector-line -> CBK sectors; mou-line -> MOUs.
  // Both admin-config-driven with an optional "Other…" free-text fallback.
  const businessSectors = useMemo(
    () => config?.business_sectors ?? config?.sectors ?? [],
    [config],
  );
  const individualMous = useMemo(() => config?.individual_mous ?? [], [config]);
  // Searchable picker: filter the (119+) MOU list by the typed query.
  const filteredMous = useMemo(() => {
    const q = mouQuery.trim().toLowerCase();
    if (!q) return individualMous;
    return individualMous.filter((m) =>
      (m.title ?? '').toLowerCase().includes(q) ||
      (m.partner_name ?? '').toLowerCase().includes(q));
  }, [individualMous, mouQuery]);
  const selectedMouTitle = useMemo(
    () => individualMous.find((m) => m.id === mouId)?.title ?? '',
    [individualMous, mouId],
  );

  // Admin-configured mandatory fields (Admin → Configuration). Drives the red
  // asterisks + the extra validation for the optional selection fields (segment
  // / sector / MOU). The four core fields the backend always demands (name /
  // product / value / stage) stay required client-side regardless, so the form
  // can't submit a deal the API would reject.
  const requiredFields = useMemo(
    () => config?.required_fields ?? ['client_name', 'product_type', 'deal_value', 'stage'],
    [config],
  );
  const isReq = (key: string): boolean => requiredFields.includes(key);
  const reqStar = (key: string) => (isReq(key) ? <RedStar /> : null);
  const allowOther = usesSector
    ? (config?.allow_other_sector ?? true)
    : false;  // consumer MOU: no "Other" escape — must pick a listed MOU partner

  // Once config loads, default the client type to the first configured line.
  useEffect(() => {
    if (!clientType && clientTypes.length) setClientType(clientTypes[0].key);
  }, [clientTypes, clientType]);

  // Map the CBS-derived legacy customer type to a configured client-type key.
  const legacyToTypeKey = (legacy: 'Individual' | 'Business'): string => {
    const wantField = legacy === 'Individual' ? 'mou' : 'sector';
    return clientTypes.find((t) => t.field === wantField)?.key
      ?? clientTypes[0]?.key ?? '';
  };

  // Reset the third-field selections when the client type flips, so a stale
  // sector doesn't ride along on a consumer deal (or a stale MOU on a business one).
  useEffect(() => {
    setSector('');
    setMouId('');
    setOtherText('');
  }, [clientType]);

  // Resolve what the client-type-aware third field contributes to the payload.
  const thirdField = useMemo(() => {
    if (usesSector) {
      const s = sector === SENTINEL_OTHER ? otherText.trim() : sector;
      return { sector: s || undefined, mou_id: undefined as string | undefined,
               mou_title: undefined as string | undefined };
    }
    const isOther = mouId === SENTINEL_OTHER;
    return {
      sector: undefined as string | undefined,
      mou_id: isOther || !mouId ? undefined : mouId,
      mou_title: isOther
        ? (otherText.trim() || undefined)
        : individualMous.find((m) => m.id === mouId)?.title,
    };
  }, [usesSector, sector, mouId, otherText, individualMous]);

  // Currency options come from the admin-maintained FX table (active rates),
  // not a hardcoded list — so extending to other Ecobank affiliates or
  // cross-border customers is an admin action, never a code change. KES (base)
  // is always offered even before any FX rate is configured.
  const { rates: fxRates } = useFxRates(true);
  const currencyOptions = useMemo(() => {
    const set = new Set<string>(['KES']);
    for (const r of fxRates) if (r.currency) set.add(r.currency.toUpperCase());
    // KES (local), then the priority trade currencies USD + CNY, then the rest
    // (EcoBank's African footprint) alphabetically.
    const PRIORITY = ['KES', 'USD', 'CNY'];
    return Array.from(set).sort((a, b) => {
      const ia = PRIORITY.indexOf(a);
      const ib = PRIORITY.indexOf(b);
      if (ia !== -1 || ib !== -1) return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
      return a.localeCompare(b);
    });
  }, [fxRates]);
  const selectedRate = useMemo(
    () => (currency === 'KES' ? 1 : fxRates.find((r) => r.currency?.toUpperCase() === currency)?.rate_to_kes),
    [currency, fxRates],
  );

  const productOptions = useMemo(() => {
    const cat = config?.product_catalogue;
    // A2a: the category carries its own product_class (balance-sheet class);
    // fall back to the legacy name map, then to all classes.
    const catCfg = config?.deal_categories?.find((c) => c.category === category);
    const legacyWant: Record<string, ProductClass[]> = {
      Loan: ['asset'], Deposit: ['liability'], Account: ['liability', 'other'],
    };
    const buckets: ProductClass[] = (catCfg?.product_class?.length
      ? (catCfg.product_class as ProductClass[])
      : (legacyWant[category] ?? ['asset', 'liability', 'insurance', 'other']));
    const flows = config?.product_flows ?? {};
    // P4a: a product whose flow declares client_types is offered ONLY to those
    // client types; an empty (or absent) client_types means offered to all.
    const offeredToClient = (product: string): boolean => {
      const cts = flows[product]?.client_types;
      if (!cts || cts.length === 0) return true;       // all client types
      return !clientType || cts.includes(clientType);
    };
    // Product gate (matches the server): a product is selectable only once it's
    // set up — it must have its OWN process flow (whose stage day-sum is the
    // SLA). Products without a flow can't be used on a deal, so they aren't
    // offered. Admin sets up the flow + SLA before a product appears here.
    const isReady = (product: string): boolean => {
      const entry = flows[product];
      return !!(entry && Array.isArray(entry.stages) && entry.stages.length > 0);
    };
    if (cat) {
      const out: string[] = [];
      for (const [cls, prods] of Object.entries(cat)) {
        if (buckets.includes(PRODUCT_CLASS_MAP[cls] ?? 'other')) {
          out.push(...prods.filter((p) => offeredToClient(p) && isReady(p)));
        }
      }
      if (out.length) return Array.from(new Set(out));
    }
    // No fallback to free-text suggestions: an empty list means no ready product
    // for this category/client type — the user must pick a different category or
    // an admin must set one up.
    return [];
  }, [config, category, clientType]);
  const dealValueNum       = useMemo(() => {
    const n = Number(String(dealValue).replace(/[,\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [dealValue]);
  const existingAmtNum = useMemo(() => {
    const n = Number(String(existingAmt).replace(/[,\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [existingAmt]);
  const topUpAmtNum = useMemo(() => {
    const n = Number(String(topUpAmt).replace(/[,\s]/g, ''));
    return Number.isFinite(n) ? n : NaN;
  }, [topUpAmt]);

  // Override note is required when conflictPath === 'override' AND user has conflict
  const overrideNoteTooShort = hasConflict && conflictPath === 'override'
    && overrideNote.trim().length < MIN_OVERRIDE_NOTE_LEN;

  // A2a: default category to first pipeline category once config loads (so the
  // create form opens on a balance-sheet class, not the hardcoded 'Loan').
  useEffect(() => {
    if (categories.length && !categories.includes(category)) {
      setCategory(categories[0]);
      const initStages = stagesForCategory(categories[0]);
      setStage((cur) => (initStages.includes(cur) ? cur : (initStages[0] ?? 'Lead')));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categories]);

  // When category changes, ensure stage is valid for the new category.
  // β5.1: AUTO-UPDATE stage to the first option for the new category.
  // β3 originally chose NOT to auto-update ("let user see change explicitly")
  // but that creates a confusing failure mode where the dropdown LOOKS
  // filled with a valid-seeming value (e.g. "Lead") but is invalid for
  // the current category, and submit fails with a "Stage X not valid for
  // Y pipeline" error that users find confusing because the field appears
  // filled. Auto-update eliminates that failure entirely.
  const stageIsValidForCategory = stageOptions.includes(stage);

  useEffect(() => {
    if (!stageOptions.includes(stage)) {
      setStage(stageOptions[0] ?? 'Lead');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [category, productClass, stageOptions]);

  // Clear segment when it no longer fits the selected client type.
  useEffect(() => {
    if (segment && !segmentOptions.includes(segment)) setSegment('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientType, segmentOptions]);

  // Clear a selected product when narrowing (by client type or category)
  // removes it from the offered set, so a product not offered to the chosen
  // client type / category can't be silently submitted. Products are now
  // selection-only from the catalogue (no free-text), so any selected product
  // must always be in the offered list.
  useEffect(() => {
    if (productType && !productOptions.includes(productType)) {
      setProductType('');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clientType, category, productOptions]);

  // P2: when an existing customer is picked, look up their mapped portfolio
  // owner from CBS. If the customer belongs to a DIFFERENT RM, auto-flag the
  // conflict and pre-fill the owner so the deal can be referred for a nod.
  // If the current user owns the portfolio (or it's unmapped), no conflict.
  useEffect(() => {
    const cif = pickedCustomer?.cif?.trim();
    if (!cif) { setDetectedOwner(null); return; }
    let cancelled = false;
    setOwnerDetecting(true);
    fetchCustomerPortfolioOwner(cif)
      .then((po) => {
        if (cancelled) return;
        setDetectedOwner(po);
        const me = (user?.staff_code || '').trim();
        if (po.is_mapped && po.portfolio_owner_code && po.portfolio_owner_code !== me) {
          setHasConflict(true);
          setPortfolioOwnerCode(po.portfolio_owner_code);
          setPortfolioOwnerName(po.portfolio_owner_name || '');
          setConflictPath('refer');
        } else {
          setHasConflict(false);
          setPortfolioOwnerCode('');
          setPortfolioOwnerName('');
        }
      })
      .catch(() => { if (!cancelled) setDetectedOwner(null); })
      .finally(() => { if (!cancelled) setOwnerDetecting(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickedCustomer?.cif, user?.staff_code]);

  // ── Live field error clearing (β5.1) ─────────────────────────────────
  //
  // When a user starts typing in a field that's currently flagged red,
  // clear that field's error immediately — don't wait for re-submit.
  // Without this, users see a red field, fix it, and the red persists
  // until they hit Submit again, which feels broken.
  const clearFieldError = (key: string) => {
    setFieldErrors((prev) => {
      if (!prev[key]) return prev;
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  // δ2 (2026-06-12): direct CIF lookup. User types a CIF in the
  // "Client CIF" input and clicks "Fetch from CBS" (or presses Enter).
  // We GET /api/cbs/customers/{cif}; on success we autofill clientName,
  // clientType, pickedCustomer, isNtb (same shape as picking from the
  // name dropdown). 404 surfaces as an error message under the input.
  const onFetchCif = async () => {
    const cif = clientCif.trim();
    if (!cif) {
      setCifLookupError('Enter a CIF to fetch.');
      return;
    }
    setCifLookupLoading(true);
    setCifLookupError(null);
    try {
      const resp = await fetchCbsCustomer(cif);
      const customer = resp.customer;
      // Mirror the onCustomerPicked branch from the name-search dropdown
      setPickedCustomer(customer);
      setClientName(customer.full_name);
      setClientType(legacyToTypeKey(segmentToCustomerType(customer.segment)));
      setIsNtb(false);
      setClientCif(customer.cif);
      clearFieldError('clientName');
      toast({
        tone: 'success',
        message: `✓ Customer found: ${customer.full_name}`,
      });
    } catch (e) {
      if (e instanceof ApiValidationError) {
        setCifLookupError(e.detail || 'CIF lookup failed.');
      } else {
        const msg = e instanceof Error ? e.message : 'CIF lookup failed.';
        setCifLookupError(msg);
      }
    } finally {
      setCifLookupLoading(false);
    }
  };

  // ── Validation ───────────────────────────────────────────────────────
  //
  // β5.0 polish: returns Record<field-name, message> instead of single
  // string. Collects ALL errors so the user can see every missing field
  // at once rather than fixing them one at a time.
  //
  // Field names match the state variable names (clientName,
  // portfolioOwnerCode, etc.) — the form's per-field rendering uses
  // these as keys when looking up errors.

  const isReferPath = hasConflict && conflictPath === 'refer';

  const validate = (): Record<string, string> => {
    const errors: Record<string, string> = {};

    if (!clientName.trim()) errors.clientName = 'Client name is required.';
    if (creatorIsHeadOffice && !originatingBranch.trim()) errors.originatingBranch = 'Please select the originating branch.';

    // Refer mode: only the client and the recipient are required; everything
    // else is optional (the recipient completes the deal after accepting).
    if (referMode) {
      if (!referRecipient) errors.referRecipient = 'Choose a colleague to refer this to.';
      return errors;
    }

    if (isReferPath) {
      // Refer path has different required fields
      if (!portfolioOwnerCode.trim()) errors.portfolioOwnerCode = 'Portfolio owner staff code is required for referral.';
      if (!portfolioOwnerName.trim()) errors.portfolioOwnerName = 'Portfolio owner name is required for referral.';
      if (!referredTo.trim())         errors.referredTo         = 'Referred-to name is required.';
      if (user?.staff_code && portfolioOwnerCode.trim() === user.staff_code) {
        errors.portfolioOwnerCode = "You can't refer a deal to yourself.";
      }
      return errors;
    }

    // Standard create path
    // P4: portfolio assignment is mandatory for an EXISTING customer whose CBS
    // portfolio owner is someone else. P2 auto-flags the conflict; if the user
    // has cleared it, they must address it (refer / seek permission / override)
    // rather than silently book a deal against another RM's portfolio.
    const me = (user?.staff_code || '').trim();
    const detectedConflict = !isNtb && !!detectedOwner?.is_mapped
      && !!detectedOwner.portfolio_owner_code
      && detectedOwner.portfolio_owner_code !== me;
    if (detectedConflict && !hasConflict) {
      errors.hasConflict = `This customer is in ${detectedOwner?.portfolio_owner_name || 'another RM'}\u2019s portfolio — choose how to proceed (refer, seek permission, or override).`;
    }

    if (!productType.trim())        errors.productType = 'Product type is required.';
    if (!stage.trim())              errors.stage       = 'Stage is required.';
    if (stage.trim() && !stageIsValidForCategory) {
      errors.stage = `Stage "${stage}" is not valid for ${category} pipeline.`;
    }
    if (isTopUp) {
      if (!Number.isFinite(topUpAmtNum) || topUpAmtNum <= 0) {
        errors.dealValue = 'Top-up amount must be greater than zero.';
      } else if (Number.isFinite(existingAmtNum) && existingAmtNum > 0 && existingAmtNum < topUpAmtNum) {
        errors.dealValue = 'Existing facility amount should be at least the top-up amount.';
      }
    } else if (!Number.isFinite(dealValueNum) || dealValueNum < 0) {
      errors.dealValue = 'Deal value must be a non-negative number.';
    }

    // Admin-configured mandatory selection fields (layered on the always-on
    // core fields above). Segment / sector / MOU are otherwise optional.
    if (isReq('segment') && segmentOptions.length > 0 && !segment.trim()) {
      errors.segment = 'Segment is required.';
    }
    if (usesSector && isReq('sector') && !sector.trim()) {
      errors.sectorMou = 'CBK sector is required.';
    }
    // Ecobank rule: Consumer deals lend ONLY through an MOU partner, so the
    // MOU is ALWAYS required for a consumer (mou-field) deal — not contingent on
    // admin required_fields config — and the "Other" escape is not permitted.
    if (!usesSector) {
      if (!mouId.trim()) {
        errors.sectorMou = 'An MOU partner is required for consumer deals.';
      } else if (mouId === SENTINEL_OTHER) {
        errors.sectorMou = 'Consumer deals must use a listed MOU partner (no "Other").';
      }
    }

    if (hasConflict) {
      if (!portfolioOwnerCode.trim()) errors.portfolioOwnerCode = 'Portfolio owner staff code is required.';
      if (!portfolioOwnerName.trim()) errors.portfolioOwnerName = 'Portfolio owner name is required.';
      if (user?.staff_code && portfolioOwnerCode.trim() === user.staff_code) {
        errors.portfolioOwnerCode = 'Portfolio owner cannot be yourself — uncheck conflict if you own this portfolio.';
      }
      if (conflictPath === 'override' && overrideNote.trim().length < MIN_OVERRIDE_NOTE_LEN) {
        errors.overrideNote = `Manager override note must be at least ${MIN_OVERRIDE_NOTE_LEN} characters (current: ${overrideNote.trim().length}).`;
      }
    }
    return errors;
  };

  // ── Server error → field mapping ────────────────────────────────────
  //
  // β5.0 polish: try to map server detail strings back to specific
  // fields. Backend validators in utils/api_pipeline_mutations.py
  // emit messages like "Missing required field: client_name". When
  // we recognise the snake_case field, map it to the camelCase state
  // variable and set a fieldError. Otherwise fall back to the banner.

  const SERVER_FIELD_MAP: Record<string, string> = {
    client_name:          'clientName',
    staff_code:           'clientName',   // shouldn't happen — we set this
    staff_name:           'clientName',   // shouldn't happen — we set this
    deal_value:           'dealValue',
    product_type:         'productType',
    stage:                'stage',
    portfolio_owner_code: 'portfolioOwnerCode',
    portfolio_owner_name: 'portfolioOwnerName',
    referred_to:          'referredTo',
    manager_override_note: 'overrideNote',
  };

  const parseServerError = (serverDetail: string): { fieldKey: string | null; message: string } => {
    if (!serverDetail) return { fieldKey: null, message: 'Submission failed.' };
    // Match "Missing required field: X" pattern
    const m1 = serverDetail.match(/Missing required field:\s*(\w+)/i);
    if (m1 && SERVER_FIELD_MAP[m1[1].toLowerCase()]) {
      return { fieldKey: SERVER_FIELD_MAP[m1[1].toLowerCase()], message: serverDetail };
    }
    // Match "manager_override_note required" pattern (α5 override semantics)
    if (/manager_override_note/i.test(serverDetail)) {
      return { fieldKey: 'overrideNote', message: serverDetail };
    }
    // Match "portfolio_owner_code" mentions
    if (/portfolio_owner_code/i.test(serverDetail)) {
      return { fieldKey: 'portfolioOwnerCode', message: serverDetail };
    }
    return { fieldKey: null, message: serverDetail };
  };

  // ── Scroll-to-error helper ──────────────────────────────────────────
  //
  // β5.0 polish: after submit fails, scroll the first errored field
  // into view and focus it. Uses the data-field attr added to each
  // input wrapper. If the field can't be found, scroll to the form
  // top so the banner is visible.

  const scrollToFirstError = (errors: Record<string, string>) => {
    const firstField = Object.keys(errors)[0];
    if (!firstField) return;
    setTimeout(() => {
      const el = document.querySelector<HTMLElement>(`[data-field="${firstField}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        // Try to focus the first focusable descendant
        const focusable = el.querySelector<HTMLElement>('input, textarea, select');
        if (focusable) focusable.focus({ preventScroll: true });
      } else {
        // Fall back: scroll to top so banner is visible
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    }, 50);
  };

  // ── Submit ───────────────────────────────────────────────────────────

  const onSubmit = async () => {
    // Reset any previous error state
    setFormError(null);
    setFieldErrors({});

    // Client-side validation: collect all errors
    const localErrors = validate();
    if (Object.keys(localErrors).length > 0) {
      setFieldErrors(localErrors);
      // Toast in case user scrolled past the banner
      toast({
        tone: 'danger',
        message: `Please fix ${Object.keys(localErrors).length} issue${Object.keys(localErrors).length > 1 ? 's' : ''} in the form.`,
      });
      scrollToFirstError(localErrors);
      return;
    }

    // Guard against missing user identity (shouldn't happen given the
    // route is ProtectedRoute requireAuth, but type system needs it)
    if (!user?.staff_code || !user?.full_name) {
      setFormError('Your user identity is not loaded. Try refreshing the page.');
      toast({ tone: 'danger', message: 'User identity not loaded — please refresh.' });
      window.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }

    // ── Refer mode: first-class "refer to a colleague" from create ──────
    if (referMode && referRecipient) {
      const body: ReferDealRequest = {
        client_name:           clientName.trim(),
        staff_code:            user.staff_code,
        staff_name:            user.full_name,
        portfolio_owner_code:  referRecipient.staff_code,
        portfolio_owner_name:  referRecipient.name,
        referred_to:           referRecipient.name,
        referral_note:         referralNote.trim() || undefined,
      };
      const result = await mutations.refer(body);
      if (result.ok) {
        toast({
          tone: 'success',
          message: `Deal referred to ${referRecipient.name} for their acceptance — it stays pending until they accept the nod.`,
        });
        navigate(`/pipeline/${encodeURIComponent(result.data.deal.id)}`);
      } else {
        const parsed = parseServerError(result.error);
        if (parsed.fieldKey) {
          setFieldErrors({ [parsed.fieldKey]: parsed.message });
          scrollToFirstError({ [parsed.fieldKey]: parsed.message });
        } else {
          setFormError(parsed.message);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        toast({ tone: 'danger', message: parsed.message });
      }
      return;
    }

    // ── Refer path: separate endpoint ──────────────────────────────────
    if (isReferPath) {
      const body: ReferDealRequest = {
        client_name:           clientName.trim(),
        staff_code:            user.staff_code,
        staff_name:            user.full_name,
        portfolio_owner_code:  portfolioOwnerCode.trim(),
        portfolio_owner_name:  portfolioOwnerName.trim(),
        referred_to:           referredTo.trim(),
        referral_note:         referralNote.trim() || undefined,
        account_number:        accountNumber.trim() || undefined,
        // Note: unit not sent from client — UserIdentity surfaces
        // department, not unit. Server can resolve unit from staff_code
        // if needed (the create endpoint already does this for other
        // ownership fields).
      };
      const result = await mutations.refer(body);
      if (result.ok) {
        toast({
          tone: 'success',
          message: `Deal referred to ${referredTo.trim()} for their acceptance — it stays pending until they accept the nod.`,
        });
        navigate(`/pipeline/${encodeURIComponent(result.data.deal.id)}`);
      } else {
        // Server validation failure — try to map to a field
        const parsed = parseServerError(result.error);
        if (parsed.fieldKey) {
          setFieldErrors({ [parsed.fieldKey]: parsed.message });
          scrollToFirstError({ [parsed.fieldKey]: parsed.message });
        } else {
          setFormError(parsed.message);
          window.scrollTo({ top: 0, behavior: 'smooth' });
        }
        toast({ tone: 'danger', message: parsed.message });
      }
      return;
    }

    // ── Standard create path (with optional conflict fields) ───────────
    const body: CreateDealRequest = {
      client_name:  clientName.trim(),
      // Declared origin. The server validates it and silently replaces a
      // system-routed value, so a stale client cannot claim a referral.
      origin,
      ...(sourceId ? { event_id: sourceId } : {}),
      staff_code:   user.staff_code,
      staff_name:   user.full_name,
      deal_value:   isBundle ? bundleTotal : (isTopUp ? topUpAmtNum : dealValueNum),
        bundle_lines: isBundle && bundleLines.length
          ? bundleLines.map((l) => ({ product_type: l.product_type, amount: Number(String(l.amount).replace(/[,\s]/g, '')) }))
          : undefined,
      product_type: productType.trim(),
      stage:        stage,

      // Optional
      client_type:        clientType,
      currency:           currency || 'KES',
      segment:            segment || undefined,
      sector:             thirdField.sector,
      mou_id:             thirdField.mou_id,
      mou_title:          thirdField.mou_title,
      client_cif:         clientCif.trim() || undefined,  // δ2: persist CIF when known
      is_ntb:             isNtb,
      pipeline_category:  category,
      is_top_up:          isTopUp || undefined,
      top_up_amount:      isTopUp && Number.isFinite(topUpAmtNum) ? topUpAmtNum : undefined,
      original_facility_amount: isTopUp && Number.isFinite(existingAmtNum) ? existingAmtNum : undefined,
      // Legacy `probability` (0..1) now reflects the DERIVED stage win
      // probability rather than a manual slider; omitted when the stage has
      // none authored (server derives win_probability on read regardless).
      probability:        derivedWinProbability !== null ? derivedWinProbability / 100 : undefined,
      next_action:        nextAction.trim() || undefined,
      next_action_date:   nextActionDate || undefined,
      expected_close:     expectedClose  || undefined,
      notes:              notes.trim() || undefined,
      source:             source,
      // Item 1: Head-Office RMs pick an originating branch; send it as unit.
      // Branch staff omit it and the backend auto-derives from their own branch.
      unit:               creatorIsHeadOffice && originatingBranch ? originatingBranch : undefined,
      // Server resolves unit from staff_code if needed.
      account_number:     accountNumber.trim() || undefined,
      phone:              contactPhone.trim() || undefined,
      email:              contactEmail.trim() || undefined,
    };

    // ── Apply conflict resolution to body ─────────────────────────────
    if (hasConflict) {
      body.portfolio_owner_code = portfolioOwnerCode.trim();
      body.portfolio_owner_name = portfolioOwnerName.trim();

      if (conflictPath === 'seek_permission') {
        // BSC credit goes to portfolio owner. Backend sees this as
        // seek-permission semantics — NO override note required.
        body.bsc_credit_to = portfolioOwnerName.trim();
      } else if (conflictPath === 'override') {
        // BSC credit goes to caller. Backend detects override semantics
        // and REQUIRES manager_override_note (≥10 chars).
        body.bsc_credit_to          = user.full_name;
        body.manager_override_note  = overrideNote.trim();
      }
    }

    const result = await mutations.create(body);
    if (result.ok) {
      toast({ tone: 'success', message: 'Deal created.' });
      navigate(`/pipeline/${encodeURIComponent(result.data.deal.id)}`);
    } else {
      // Server validation failure — try to map to a field
      const parsed = parseServerError(result.error);
      if (parsed.fieldKey) {
        setFieldErrors({ [parsed.fieldKey]: parsed.message });
        scrollToFirstError({ [parsed.fieldKey]: parsed.message });
      } else {
        setFormError(parsed.message);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
      toast({ tone: 'danger', message: parsed.message });
    }
  };

  // ── Render ────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50">
      <PageHeader
        title="New Deal"
        breadcrumbs={[
          { label: 'EKE Sales Pro', to: '/pipeline' },
          { label: 'New deal' },
        ]}
        subtitle="Capture a lead — customer, classification, value, and ownership."
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate('/pipeline')}>
            ← Back to pipeline
          </Button>
        }
      />

      <main className="max-w-6xl mx-auto px-6 pt-4 pb-8">
        {/* Mode toggle: build a full deal, or refer a lead to a colleague. */}
        <div className="mb-4 inline-flex rounded-lg border border-gray-200 bg-white p-1 text-sm">
          <button
            type="button"
            onClick={() => setReferMode(false)}
            className={`px-4 py-1.5 rounded-md transition ${!referMode ? 'bg-brand-primary text-white' : 'text-gray-600 hover:text-gray-900'}`}
          >
            Create a deal
          </button>
          <button
            type="button"
            onClick={() => setReferMode(true)}
            className={`px-4 py-1.5 rounded-md transition ${referMode ? 'bg-brand-primary text-white' : 'text-gray-600 hover:text-gray-900'}`}
          >
            Refer to a colleague
          </button>
        </div>

        {/* ─────────── Error summary banner (β5.0 polish) ───────────
            Renders at the top so users see it without scrolling.
            Shows either:
              - formError (banner-level: network/server/identity errors), OR
              - a summary count of fieldErrors with a "review fields"
                hint, since each field also shows its own inline message
        */}
        {(formError || Object.keys(fieldErrors).length > 0) && (
          <div
            role="alert"
            aria-live="assertive"
            className="mb-4 px-4 py-3 rounded-md bg-red-50 border-l-4 border-red-500 text-sm text-red-900 shadow-sm"
          >
            {formError ? (
              <div>
                <div className="font-semibold mb-0.5">Submission failed</div>
                <div>{formError}</div>
              </div>
            ) : (
              <div>
                <div className="font-semibold mb-0.5">
                  Please fix {Object.keys(fieldErrors).length} field
                  {Object.keys(fieldErrors).length > 1 ? 's' : ''} below
                </div>
                <div className="text-xs">
                  Each problem is highlighted in red next to the relevant input.
                </div>
              </div>
            )}
          </div>
        )}

        {/* ─────────── Form sections (2-up on wide screens) ─────────── */}
        <div className="grid lg:grid-cols-2 gap-5 items-start">
        {/* ─────────── Customer section ─────────── */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Customer</h2>
            <span className="text-xs text-gray-400">Who is this deal for?</span>
          </Card.Header>
          <Card.Body>
            {/* ORIGIN — the first gate. Where did this deal come from? Only
                the origins a person can legitimately declare appear here;
                referral and warehouse are stamped by the system when the deal
                actually travels that route. */}
            {originOpts.length > 0 && (
              <div className="mb-4">
                <label className="text-sm font-medium text-gray-700">
                  Deal origin
                </label>
                <select
                  value={origin}
                  onChange={(e) => setOrigin(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {originOpts.map((o) => (
                    <option key={o.key} value={o.key}>{o.label}</option>
                  ))}
                </select>
                {(() => {
                  const o = originOpts.find((x) => x.key === origin);
                  return o?.note ? (
                    <p className="mt-1 text-xs text-gray-500">{o.note}</p>
                  ) : null;
                })()}

                {sourceOpts.length > 0 && (
                  <div className="mt-3">
                    <label className="text-sm font-medium text-gray-700">
                      Which one?
                    </label>
                    <select
                      value={sourceId}
                      onChange={(e) => setSourceId(e.target.value)}
                      disabled={mutations.loading}
                      className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                    >
                      <option value="">Not specified</option>
                      {sourceOpts.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.label}{o.sub ? ` — ${o.sub}` : ''}
                        </option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            )}

            {/* Relationship status — drives whether a CBS CIF lookup is
                offered (existing customer) or the form is filled fresh (NTB). */}
            <div className="mb-4">
              <label className="text-sm font-medium text-gray-700">
                Relationship status{reqStar('relationship_status')}
              </label>
              <select
                value={isNtb ? 'ntb' : 'existing'}
                onChange={(e) => setIsNtb(e.target.value === 'ntb')}
                disabled={mutations.loading}
                className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
              >
                <option value="existing">Existing customer</option>
                <option value="ntb">New to Bank</option>
              </select>
            </div>

            {/* CIF lookup — only meaningful for an existing (in-CBS) customer. */}
            {!isNtb && (
            <div className="mb-4" data-field="clientCif">
              <label className="text-sm font-medium text-gray-700">
                Client CIF (to fetch from CBS)
              </label>
              <div className="flex gap-2 mt-1">
                <input
                  type="text"
                  value={clientCif}
                  onChange={(e) => {
                    setClientCif(e.target.value);
                    if (cifLookupError) setCifLookupError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && clientCif.trim() && !cifLookupLoading) {
                      e.preventDefault();
                      void onFetchCif();
                    }
                  }}
                  placeholder="e.g. 100123456"
                  disabled={mutations.loading || cifLookupLoading}
                  autoComplete="off"
                  className="flex-1 h-10 px-3 rounded-md border border-gray-300 bg-white text-sm font-mono focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                />
                <Button
                  variant="secondary"
                  size="md"
                  onClick={() => void onFetchCif()}
                  disabled={!clientCif.trim() || mutations.loading || cifLookupLoading}
                >
                  {cifLookupLoading ? 'Fetching…' : 'Fetch from CBS'}
                </Button>
              </div>
              {cifLookupError && (
                <div className="mt-1 text-xs text-red-700">{cifLookupError}</div>
              )}
              {!cifLookupError && pickedCustomer && clientCif === pickedCustomer.cif && (
                <div className="mt-1 text-xs text-green-700">
                  ✓ CIF matches picked customer
                </div>
              )}
            </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div data-field="clientName">
                <CustomerSearchInput
                  label={<>Client name <RedStar /></>}
                  placeholder="Type a name (min 3 chars) to search CBS, or enter free text"
                  value={clientName}
                  onChange={(v) => { setClientName(v); clearFieldError('clientName'); }}
                  onCustomerPicked={(c) => {
                    // γ2 autofill — when user picks from CBS dropdown,
                    // populate related fields automatically.
                    setPickedCustomer(c);
                    setClientType(legacyToTypeKey(segmentToCustomerType(c.segment)));
                    // Customer is in CBS, so by definition not New-To-Bank.
                    setIsNtb(false);
                    // δ2: also capture the CIF so it persists on the deal.
                    setClientCif(c.cif);
                    setCifLookupError(null);
                    clearFieldError('clientName');
                  }}
                  onCustomerCleared={() => setPickedCustomer(null)}
                  pickedCustomer={pickedCustomer}
                  disabled={mutations.loading}
                  error={fieldErrors.clientName}
                />
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Customer type{reqStar('client_type')}
                </label>
                <select
                  value={clientType}
                  onChange={(e) => setClientType(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {clientTypes.map((t) => (
                    <option key={t.key} value={t.key}>{t.label}</option>
                  ))}
                </select>
              </div>
              <div data-field="segment">
                <label className="text-sm font-medium text-gray-700">
                  Segment{reqStar('segment')}
                </label>
                <select
                  value={segment}
                  onChange={(e) => { setSegment(e.target.value); clearFieldError('segment'); }}
                  disabled={mutations.loading || segmentOptions.length === 0}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  <option value="">
                    {segmentOptions.length === 0 ? '—' : `Select ${clientType.toLowerCase()} segment`}
                  </option>
                  {segmentOptions.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                {fieldErrors.segment && (
                  <p className="text-xs text-red-700 mt-1">{fieldErrors.segment}</p>
                )}
              </div>
              {creatorIsHeadOffice && (
                <div data-field="originatingBranch">
                  <label className="text-sm font-medium text-gray-700">
                    Originating branch<RedStar />
                  </label>
                  <select
                    value={originatingBranch}
                    onChange={(e) => setOriginatingBranch(e.target.value)}
                    disabled={mutations.loading}
                    className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                  >
                    <option value="">Select branch…</option>
                    {branches.map((b) => (
                      <option key={b.id || b.name} value={b.name}>{b.name}</option>
                    ))}
                  </select>
                  {fieldErrors.originatingBranch && (
                    <p className="text-xs text-red-700 mt-1">{fieldErrors.originatingBranch}</p>
                  )}
                </div>
              )}
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Currency{reqStar('currency')}
                </label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                >
                  {currencyOptions.map((c) => (
                    <option key={c} value={c}>{c}{c === 'KES' ? ' (local)' : ''}</option>
                  ))}
                </select>
                {currency !== 'KES' && (
                  <p className="text-xs text-gray-500 mt-1">
                    {selectedRate
                      ? `FCY · ≈ KES ${(dealValueNum * selectedRate).toLocaleString(undefined, { maximumFractionDigits: 0 })} at ${selectedRate}/${currency}`
                      : `FCY · no admin FX rate set for ${currency} yet`}
                  </p>
                )}
              </div>
              <div data-field="sectorMou">
                <label className="text-sm font-medium text-gray-700">
                  {usesSector
                    ? <>Sector (CBK){reqStar('sector')}</>
                    : <>Partnership / MOU<RedStar /></>}
                </label>
                {usesSector ? (
                  <select
                    value={sector}
                    onChange={(e) => setSector(e.target.value)}
                    disabled={mutations.loading}
                    className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                  >
                    <option value="">Select CBK sector (optional)</option>
                    {businessSectors.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                    {allowOther && <option value={SENTINEL_OTHER}>Other…</option>}
                  </select>
                ) : (
                  <div className="relative">
                    <input
                      type="text"
                      value={mouOpen ? mouQuery : selectedMouTitle}
                      placeholder="Search and select an MOU partner (required)"
                      disabled={mutations.loading}
                      autoComplete="off"
                      onFocus={() => { setMouOpen(true); setMouQuery(''); }}
                      onChange={(e) => { setMouQuery(e.target.value); setMouOpen(true); }}
                      onBlur={() => { window.setTimeout(() => setMouOpen(false), 120); }}
                      className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                    />
                    {mouOpen && (
                      <ul className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded-md border border-gray-200 bg-white shadow-lg">
                        {filteredMous.length === 0 ? (
                          <li className="px-3 py-2 text-sm text-gray-500">
                            No partner matches “{mouQuery}”.
                          </li>
                        ) : (
                          filteredMous.map((m) => (
                            <li key={m.id}>
                              <button
                                type="button"
                                onMouseDown={(e) => {
                                  e.preventDefault();
                                  setMouId(m.id);
                                  setMouQuery('');
                                  setMouOpen(false);
                                }}
                                className={`w-full text-left px-3 py-2 text-sm hover:bg-brand-primary/10 ${m.id === mouId ? 'bg-brand-primary/5 font-medium' : ''}`}
                              >
                                {m.title}
                              </button>
                            </li>
                          ))
                        )}
                      </ul>
                    )}
                  </div>
                )}
                {(sector === SENTINEL_OTHER || mouId === SENTINEL_OTHER) && (
                  <input
                    type="text"
                    value={otherText}
                    onChange={(e) => setOtherText(e.target.value)}
                    disabled={mutations.loading}
                    placeholder={usesSector ? 'Specify sector' : 'Specify partner / MOU'}
                    className="mt-2 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
                  />
                )}
                {fieldErrors.sectorMou && (
                  <p className="text-xs text-red-700 mt-1">{fieldErrors.sectorMou}</p>
                )}
              </div>
              <Input
                label={isNtb ? 'New account number (once opened)' : 'Account number / CIF (optional)'}
                placeholder={isNtb ? "Enter once the customer's account is opened" : 'e.g. ECO0123456789 or 100456789'}
                value={accountNumber}
                onChange={(e) => setAccountNumber(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Customer phone (optional)"
                placeholder="e.g. 0712 345 678"
                value={contactPhone}
                onChange={(e) => setContactPhone(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Customer email (optional)"
                placeholder="e.g. name@example.com"
                value={contactEmail}
                onChange={(e) => setContactEmail(e.target.value)}
                disabled={mutations.loading}
              />
            </div>
          </Card.Body>
        </Card>

        {referMode && (
          <Card stripe="accent">
            <Card.Header>
              <h2 className="text-base font-semibold text-gray-900">Refer to a colleague</h2>
              <span className="text-xs text-gray-400">Recipient + note</span>
            </Card.Header>
            <Card.Body>
              <p className="text-sm text-gray-600 mb-3">
                Hand this lead to a colleague — pick their segment, then the person.
                Only the client name and recipient are required; they complete the
                deal once they accept it.
              </p>
              <StaffPicker value={referRecipient} onChange={setReferRecipient} />
              {fieldErrors.referRecipient && (
                <p className="text-xs text-red-600 mt-2">{fieldErrors.referRecipient}</p>
              )}
              <div className="mt-3">
                <Input
                  label="Note (optional)"
                  placeholder="Why you're referring this"
                  value={referralNote}
                  onChange={(e) => setReferralNote(e.target.value)}
                  disabled={mutations.loading}
                />
              </div>
            </Card.Body>
          </Card>
        )}

        {!referMode && (<>
        {/* ─────────── Deal classification + value ─────────── */}
        <Card stripe="primary">
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Deal details</h2>
            <span className="text-xs text-gray-400">Classification + value</span>
          </Card.Header>
          <Card.Body>
            <div>
              <label className="text-sm font-medium text-gray-700">Pipeline category <RedStar /></label>
              <select
                value={category}
                onChange={(e) => {
                  const c = e.target.value;
                  setCategory(c);
                  const initStages = stagesForCategory(c);
                  if (!initStages.includes(stage)) {
                    setStage(initStages[0] ?? 'Lead');
                  }
                  setProductType('');
                }}
                disabled={mutations.loading}
                className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 disabled:bg-gray-50 disabled:text-gray-400"
              >
                {categories.map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </div>

            <div className="mt-4" data-field="productType">
              <label className="text-sm font-medium text-gray-700">Product type <RedStar /></label>
              <select
                value={productOptions.includes(productType) ? productType : ''}
                onChange={(e) => {
                  setProductType(e.target.value);
                  clearFieldError('productType');
                }}
                disabled={mutations.loading || productOptions.length === 0}
                aria-invalid={!!fieldErrors.productType}
                className={`mt-1 w-full h-10 px-3 rounded-md border bg-white text-sm text-gray-900 focus:outline-none focus:ring-2 ${
                  fieldErrors.productType
                    ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                    : 'border-gray-300 focus:border-brand-primary focus:ring-brand-primary/20'
                }`}
              >
                <option value="">Select a product…</option>
                {productOptions.map((p) => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              {productOptions.length === 0 && (
                <p className="mt-1 text-xs text-gray-500">
                  No products are set up for this category{clientType ? ` and client type` : ''} yet.
                  Products must be created in Admin with a process flow and SLA before they can be used.
                </p>
              )}
              {fieldErrors.productType && (
                <p className="mt-1 text-xs text-red-700">{fieldErrors.productType}</p>
              )}
            </div>

            <div className="mt-4">
              <label className="text-sm font-medium text-gray-700">Facility type</label>
              <div className="mt-1 inline-flex rounded-md border border-gray-300 overflow-hidden">
                <button type="button"
                  className={`px-4 py-1.5 text-sm ${!isTopUp ? 'bg-brand-primary text-white' : 'bg-white text-gray-700'}`}
                  onClick={() => { setIsTopUp(false); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}>New facility</button>
                <button type="button"
                  className={`px-4 py-1.5 text-sm ${isTopUp ? 'bg-brand-primary text-white' : 'bg-white text-gray-700'}`}
                  onClick={() => { setIsTopUp(true); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}>Top-up</button>
              </div>
              {isBundle && (
                <BundleLinesEditor
                  value={bundleLines}
                  onChange={(lines, total) => { setBundleLines(lines); setBundleTotal(total); }}
                  currencySymbol={branding?.currency_symbol ?? 'KES'}
                />
              )}

              {!isBundle && isTopUp && (
                <p className="mt-1 text-xs text-gray-500">
                  A top-up adds to an existing facility. The pipeline value reflects only the increment (the new money), not the whole facility.
                </p>
              )}
            </div>

            {!isBundle && isTopUp && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                <div>
                  <Input
                    label={<>Existing facility amount (KES) <RedStar /></>}
                    placeholder="e.g. 20000000" type="number"
                    value={existingAmt}
                    onChange={(e) => setExistingAmt(e.target.value)}
                    disabled={mutations.loading}
                    helper={Number.isFinite(existingAmtNum) && existingAmtNum > 0
                      ? `${branding?.currency_symbol ?? 'KES'} ${existingAmtNum.toLocaleString()} (context only)`
                      : 'Context only — not counted in pipeline value'}
                  />
                </div>
                <div data-field="dealValue">
                  <Input
                    label={<>Top-up amount (KES) <RedStar /></>}
                    placeholder="e.g. 5000000" type="number"
                    value={topUpAmt}
                    onChange={(e) => { setTopUpAmt(e.target.value); clearFieldError('dealValue'); }}
                    disabled={mutations.loading}
                    helper={Number.isFinite(topUpAmtNum) && topUpAmtNum > 0
                      ? `${branding?.currency_symbol ?? 'KES'} ${topUpAmtNum.toLocaleString()} — this IS the pipeline value`
                      : undefined}
                    error={fieldErrors.dealValue}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              {!isBundle && !isTopUp && (
              <div data-field="dealValue">
                <Input
                  label={category === 'Account'
                    ? <>Number of accounts <RedStar /></>
                    : <>Deal value (KES) <RedStar /></>}
                  placeholder={category === 'Account' ? 'e.g. 1' : 'e.g. 5000000'}
                  type="number"
                  value={dealValue}
                  onChange={(e) => { setDealValue(e.target.value); clearFieldError('dealValue'); }}
                  disabled={mutations.loading}
                  helper={Number.isFinite(dealValueNum) && dealValueNum > 0
                    ? `${branding?.currency_symbol ?? 'KES'} ${dealValueNum.toLocaleString()}`
                    : undefined}
                  error={fieldErrors.dealValue}
                />
              </div>
              )}
              {!isBundle && isTopUp && (
              <div>
                <label className="text-sm font-medium text-gray-700">Pipeline value</label>
                <div className="mt-2 flex items-center gap-2">
                  <Badge tone="info" size="sm">
                    {Number.isFinite(topUpAmtNum) && topUpAmtNum > 0
                      ? `${branding?.currency_symbol ?? 'KES'} ${topUpAmtNum.toLocaleString()}`
                      : '—'}
                  </Badge>
                  <span className="text-xs text-gray-400">top-up increment</span>
                </div>
              </div>
              )}
              <div data-field="stage">
                <label className="text-sm font-medium text-gray-700">
                  Initial stage <RedStar />
                </label>
                <select
                  value={stage}
                  onChange={(e) => { setStage(e.target.value); clearFieldError('stage'); }}
                  disabled={mutations.loading}
                  aria-invalid={!!fieldErrors.stage}
                  className={`mt-1 w-full h-10 px-3 rounded-md border bg-white text-sm text-gray-900 focus:outline-none focus:ring-2 ${
                    fieldErrors.stage
                      ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                      : 'border-gray-300 focus:border-brand-primary focus:ring-brand-primary/20'
                  }`}
                >
                  {stageOptions.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                {fieldErrors.stage && (
                  <p className="mt-1 text-xs text-red-700">{fieldErrors.stage}</p>
                )}
              </div>
              <div>
                <label className="text-sm font-medium text-gray-700">
                  Win probability
                </label>
                {derivedWinProbability === null ? (
                  <div className="mt-2 flex items-center gap-2">
                    <Badge tone="neutral" size="sm">—</Badge>
                    <span className="text-xs text-gray-400">
                      Set per stage in the product flow (Admin → Product flows).
                    </span>
                  </div>
                ) : (
                  <div className="mt-2 flex items-center gap-2">
                    <Badge
                      tone={derivedWinProbability >= 75 ? 'success'
                        : derivedWinProbability >= 40 ? 'info' : 'neutral'}
                      size="sm"
                    >
                      {Math.round(derivedWinProbability)}%
                    </Badge>
                    <span className="text-xs text-gray-400">
                      auto from “{stage}” — updates as the deal advances
                    </span>
                  </div>
                )}
                {selectedStageTargetDays !== null && (
                  <p className="mt-1 text-[11px] text-gray-400">
                    Stage SLA: {selectedStageTargetDays} business day{selectedStageTargetDays === 1 ? '' : 's'} (from product flow)
                  </p>
                )}
              </div>
            </div>
          </Card.Body>
        </Card>

        {/* ─────────── Workflow ─────────── */}
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Workflow</h2>
            <span className="text-xs text-gray-400">Next steps + source</span>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <Input
                label="Next action"
                placeholder="e.g. Send KYC checklist"
                value={nextAction}
                onChange={(e) => setNextAction(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Next action date"
                type="date"
                value={nextActionDate}
                onChange={(e) => setNextActionDate(e.target.value)}
                disabled={mutations.loading}
              />
              <Input
                label="Expected close date"
                type="date"
                value={expectedClose}
                onChange={(e) => setExpectedClose(e.target.value)}
                disabled={mutations.loading}
              />
              <div className="md:col-span-2">
                <label className="text-sm font-medium text-gray-700">Lead source</label>
                <select
                  value={source}
                  onChange={(e) => setSource(e.target.value)}
                  disabled={mutations.loading}
                  className="mt-1 w-full h-10 px-3 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20"
                >
                  {SOURCE_OPTIONS.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="mt-4">
              <label className="text-sm font-medium text-gray-700">
                Notes
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                disabled={mutations.loading}
                placeholder="Relationship history, key triggers, urgency..."
                rows={2}
                className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
              />
            </div>
          </Card.Body>
        </Card>

        {/* ─────────── Portfolio conflict resolution ─────────── */}
        <Card stripe={hasConflict ? 'accent' : undefined}>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">
              Portfolio assignment
            </h2>
            <span className="text-xs text-gray-400">
              {hasConflict ? 'α5 conflict resolution' : 'Is this customer already in another RM\u2019s portfolio?'}
            </span>
          </Card.Header>
          <Card.Body>
            <label className="flex items-center gap-3 cursor-pointer" data-field="hasConflict">
              <input
                type="checkbox"
                checked={hasConflict}
                onChange={(e) => { setHasConflict(e.target.checked); if (e.target.checked) clearFieldError('hasConflict'); }}
                disabled={mutations.loading}
                className="h-4 w-4 rounded border-gray-300 text-brand-primary focus:ring-brand-primary"
              />
              <span className="text-sm text-gray-800">
                This customer is in another RM&rsquo;s portfolio
              </span>
            </label>
            {ownerDetecting && (
              <p className="text-xs text-gray-500 mt-2">Checking portfolio ownership in CBS…</p>
            )}
            {!ownerDetecting && detectedOwner?.is_mapped
              && detectedOwner.portfolio_owner_code
              && detectedOwner.portfolio_owner_code !== (user?.staff_code || '').trim() && (
              <div className="mt-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                Auto-detected from CBS: this customer is in{' '}
                <span className="font-semibold">
                  {detectedOwner.portfolio_owner_name || `RM ${detectedOwner.portfolio_owner_code}`}
                </span>
                &rsquo;s portfolio. The deal will be referred to them for a nod.
                {!detectedOwner.owner_in_roster && (
                  <span className="block mt-1 text-amber-700">
                    Note: this owner isn&rsquo;t a recognised system user — confirm the recipient manually.
                  </span>
                )}
              </div>
            )}
            {!ownerDetecting && detectedOwner?.is_mapped
              && detectedOwner.portfolio_owner_code === (user?.staff_code || '').trim() && (
              <div className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800">
                You are this customer&rsquo;s portfolio owner — no conflict.
              </div>
            )}
            {!ownerDetecting && detectedOwner && !detectedOwner.is_mapped && (
              <p className="text-xs text-gray-500 mt-2">
                No portfolio owner on record for this customer in CBS — mark a conflict manually if needed.
              </p>
            )}
            {!detectedOwner && !ownerDetecting && (
              <p className="text-xs text-gray-500 mt-2">
                Check this if CBS already assigns the customer to a different RM.
                For an existing customer, ownership is detected automatically.
              </p>
            )}
            {fieldErrors.hasConflict && (
              <p className="text-xs text-red-600 mt-2">{fieldErrors.hasConflict}</p>
            )}

            {hasConflict && (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div data-field="portfolioOwnerCode">
                  <Input
                    label={<>Portfolio owner staff code <RedStar /></>}
                    placeholder="e.g. 0123"
                    value={portfolioOwnerCode}
                    onChange={(e) => { setPortfolioOwnerCode(e.target.value); clearFieldError('portfolioOwnerCode'); }}
                    disabled={mutations.loading}
                    error={fieldErrors.portfolioOwnerCode}
                  />
                </div>
                <div data-field="portfolioOwnerName">
                  <Input
                    label={<>Portfolio owner name <RedStar /></>}
                    placeholder="e.g. Jane Mwangi"
                    value={portfolioOwnerName}
                    onChange={(e) => { setPortfolioOwnerName(e.target.value); clearFieldError('portfolioOwnerName'); }}
                    disabled={mutations.loading}
                    error={fieldErrors.portfolioOwnerName}
                  />
                </div>
              </div>
            )}

            {hasConflict && (
              <div className="mt-6">
                <label className="text-sm font-medium text-gray-700">
                  How do you want to proceed?
                </label>
                <div className="mt-2 space-y-2">
                  <PathRadio
                    active={conflictPath === 'refer'}
                    onClick={() => setConflictPath('refer')}
                    disabled={mutations.loading}
                    label="Refer to portfolio owner"
                    sub={`Sends the lead to ${portfolioOwnerName || 'the owner'}. They take it from here.`}
                  />
                  <PathRadio
                    active={conflictPath === 'seek_permission'}
                    onClick={() => setConflictPath('seek_permission')}
                    disabled={mutations.loading}
                    label="Seek permission, defer BSC credit"
                    sub={`You'll work the deal; BSC credit on close goes to ${portfolioOwnerName || 'the owner'}. No manager approval required server-side.`}
                  />
                  <PathRadio
                    active={conflictPath === 'override'}
                    onClick={() => setConflictPath('override')}
                    disabled={mutations.loading}
                    label="Override portfolio assignment, take BSC credit"
                    sub={`BSC credit goes to ${user?.full_name ?? 'you'}. Requires manager override note (\u2265 ${MIN_OVERRIDE_NOTE_LEN} chars).`}
                  />
                </div>
              </div>
            )}

            {hasConflict && conflictPath === 'refer' && (
              <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4">
                <div data-field="referredTo">
                  <Input
                    label={<>Referred to (named recipient) <RedStar /></>}
                    placeholder="Usually the portfolio owner"
                    value={referredTo}
                    onChange={(e) => { setReferredTo(e.target.value); clearFieldError('referredTo'); }}
                    disabled={mutations.loading}
                    error={fieldErrors.referredTo}
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="text-sm font-medium text-gray-700">
                    Referral note (optional)
                  </label>
                  <textarea
                    value={referralNote}
                    onChange={(e) => setReferralNote(e.target.value)}
                    disabled={mutations.loading}
                    placeholder="Context for the recipient — what does this customer need?"
                    rows={2}
                    className="mt-1 w-full px-3 py-2 rounded-md border border-gray-300 bg-white text-sm text-gray-900 focus:outline-none focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/20 resize-y"
                  />
                </div>
              </div>
            )}

            {hasConflict && conflictPath === 'override' && (
              <div className="mt-4" data-field="overrideNote">
                <label className="text-sm font-medium text-gray-700">
                  Manager override note <RedStar /> (min {MIN_OVERRIDE_NOTE_LEN} chars)
                </label>
                <textarea
                  value={overrideNote}
                  onChange={(e) => { setOverrideNote(e.target.value); clearFieldError('overrideNote'); }}
                  disabled={mutations.loading}
                  placeholder="Why is the override appropriate? This is reviewed by management."
                  rows={3}
                  aria-invalid={!!fieldErrors.overrideNote}
                  className={`mt-1 w-full px-3 py-2 rounded-md border bg-white text-sm text-gray-900 focus:outline-none focus:ring-2 resize-y ${
                    fieldErrors.overrideNote
                      ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20'
                      : 'border-gray-300 focus:border-brand-primary focus:ring-brand-primary/20'
                  }`}
                />
                {fieldErrors.overrideNote ? (
                  <p className="mt-1 text-xs text-red-700">{fieldErrors.overrideNote}</p>
                ) : overrideNote.length > 0 && overrideNoteTooShort ? (
                  <p className="text-xs text-amber-600 mt-1">
                    {overrideNote.trim().length} / {MIN_OVERRIDE_NOTE_LEN} characters.
                  </p>
                ) : null}
              </div>
            )}
          </Card.Body>
        </Card>
        </>)}
        </div>

        {/* (β5.0 polish: bottom error banner removed.
             Errors now shown at the TOP of the form for visibility
             plus inline next to each errored field.) */}


        <div className="mt-6 flex items-center justify-between gap-4">
          <Button
            variant="ghost"
            size="md"
            onClick={() => navigate('/pipeline')}
            disabled={mutations.loading}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            size="md"
            onClick={() => void onSubmit()}
            loading={mutations.loading}
          >
            {(referMode || isReferPath) ? 'Send referral' : 'Create deal'}
          </Button>
        </div>

        {/* Footer */}
        <footer className="mt-12 pb-6 text-center text-[11px] text-gray-400 leading-relaxed">
          {branding?.ip_notice}
        </footer>
      </main>
    </div>
  );
}


// ── Helper components ───────────────────────────────────────────────────

/** Red required-field marker. */
function RedStar() {
  return <span className="text-red-600"> *</span>;
}

interface PathRadioProps {
  active:    boolean;
  onClick:   () => void;
  disabled?: boolean;
  label:     string;
  sub:       React.ReactNode;
}

function PathRadio({ active, onClick, disabled, label, sub }: PathRadioProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`w-full text-left px-4 py-3 rounded-md border transition-colors ${
        active
          ? 'bg-blue-50 border-brand-primary'
          : 'bg-white border-gray-200 hover:border-gray-400'
      } ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <div className="flex items-start gap-3">
        <div className={`mt-0.5 h-4 w-4 rounded-full border-2 flex-shrink-0 ${
          active ? 'border-brand-primary bg-brand-primary' : 'border-gray-400'
        }`}>
          {active && <div className="h-1.5 w-1.5 rounded-full bg-white m-auto mt-[3px]" />}
        </div>
        <div className="flex-1">
          <div className="text-sm font-medium text-gray-900">{label}</div>
          <div className="text-xs text-gray-600 mt-0.5">{sub}</div>
        </div>
      </div>
    </button>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, PAGE, TYPES):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - EV1 looks applied." % MOD)
        return 1
    if not os.path.isfile(os.path.join("data", "sponsored_events.json")):
        print("ABORT: data/sponsored_events.json not found - nothing to expose.")
        return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()
    tp = open(TYPES, encoding="utf-8").read()

    if "/api/pipeline/origin-sources" in api:
        print("ABORT: the origin-sources endpoint already exists.")
        return 1
    if '@app.get("/api/pipeline/origins")' not in api:
        print("ABORT: apply patch_or2_origin_wiring.py first.")
        return 1
    if "_decl(_org)" not in api:
        print("ABORT: apply patch_or3_origin_evidence.py first.")
        return 1

    api = api.replace('@app.get("/api/pipeline/origins")',
                      ENDPOINTS + '@app.get("/api/pipeline/origins")', 1)
    c = api.index("def pipeline_deal_create(")
    m = re.search(r'\n@app\.(get|post)\("/api/', api[c + 40:])
    api = api[:c] + CREATE + api[c + 40 + m.start() + 1:]
    print("  ok  api.py - source endpoints and create clearing")

    anchor = "export async function fetchDealOrigins()"
    if ts.count(anchor) != 1:
        print("ABORT: api.ts anchor matched %d times." % ts.count(anchor))
        return 1
    ts = ts.replace(anchor, TS_NEW + anchor, 1)
    i = tp.index("export interface CreateDealRequest {")
    j = tp.index("\n}", i) + 2
    tp = tp[:i] + IFACE + tp[j:]
    print("  ok  api.ts and types")

    # A source id belonging to another origin must be cleared, or a walk-in
    # deal silently credits a roadshow.
    if 'deal_dict.pop(_f, None)' not in CREATE:
        print("ABORT: create does not clear a mismatched source id.")
        return 1
    if "CLOSED_WON" not in MODULE or "== CLOSED_WON" not in MODULE:
        print("ABORT: attribution does not restrict accounts to closed-won.")
        return 1
    if '"stored"' not in MODULE or '"derived"' not in MODULE:
        print("ABORT: attribution must report BOTH figures - replacing the")
        print("       stored one silently would hide which is being read.")
        return 1
    if "event_id?:" not in IFACE:
        print("ABORT: CreateDealRequest does not carry event_id.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if PAGE_NEW.count(op) != PAGE_NEW.count(cl):
            print("ABORT: page unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  post-checks: closure-only actuals, both figures, id cleared")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("CREATED %s" % MOD)
    for path, content in ((API, api), (APITS, ts), (TYPES, tp), (PAGE, PAGE_NEW)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (MOD, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd, restart uvicorn.")
    print("Choosing Events on the create form should now offer 3 active events.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
