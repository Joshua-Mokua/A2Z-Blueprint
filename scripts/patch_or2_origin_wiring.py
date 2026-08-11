#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
OR2 - the ranking, analytics and deal creation read ORIGIN from config.

OR1 built the model. OR2 replaces the hard-coded REFERRED-versus-DIRECT pair
that was baked into the pipeline leaderboard and the analytics split - it worked
for two origins and breaks at seven.

WHAT CHANGES
  GET /api/pipeline/origins        the configured list, for filters and forms

  /api/pipeline/leaderboard        origin= accepts ANY configured key. When a
      CREDITABLE origin is selected, rows attribute to the party that origin
      credits - the referrer, the warehouse lister, the lead generator, the
      contact-centre agent - instead of the deal owner. Mixing the two in one
      table is what would double-count. "referred" and "direct" are still
      accepted so a stale bookmark does not silently return everything.

  /api/pipeline/analytics/summary  the split now comes from deal_origin
      .summarise(), which reports EVERY configured origin including the empty
      ones. An origin producing no deals is a finding; hiding it is how a
      channel dies quietly. The dead _is_ref helper is removed rather than left
      looking meaningful.

  POST /api/pipeline/deals         records the origin, VALIDATED against config.
      An unrecognised value falls back to the default rather than being stored -
      a typo'd origin would sit outside every bucket and appear in analytics as
      an orphan nobody can filter for.

      origin_party_code / origin_party_name are added to the PRIVILEGED-AT-CREATE
      strip list, alongside the referral fields and for the same reason: a
      caller may declare WHERE a deal came from, but not WHO gets credited for
      it. That is set by the workflow that routed the deal.

  FRONTEND: the ranking's origin filter and the analytics panel are built from
      what the server reports, so an EIGHTH ORIGIN NEEDS NO FRONTEND CHANGE. The
      filter caption names the credited party for creditable origins. "Referred
      vs direct" becomes "Where deals came from", with a colour per origin.

Verified: py_compile clean, tsc --noEmit clean, vite build clean; an
unrecognised origin stores as "self".

REQUIRES OR1.

Usage (from project root, .venv active):
    python scripts\patch_or2_origin_wiring.py            # dry run
    python scripts\patch_or2_origin_wiring.py --apply
"""
import os
import re
import shutil
import sys

API = os.path.join("utils", "api.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
PL = os.path.join("frontend", "web", "src", "components", "PipelineLeaderboard.tsx")
PA = os.path.join("frontend", "web", "src", "components", "PipelineAnalytics.tsx")
BACKUP_SUFFIX = ".pre_or2"

TS_ANCHOR = "export interface PipelineOriginSplit {"

# The leaderboard interface lives elsewhere in api.ts, so it needs its own edit.
# Without it the component compiles against a type that has no `origins`, and
# tsc fails with "Property 'origins' does not exist".
LB_IFACE_OLD = """  total_deals: number; total_value: number; total_weighted: number;
  branches: string[];
}"""
LB_IFACE_NEW = """  total_deals: number; total_value: number; total_weighted: number;
  branches: string[];
  // Built from config, so a new origin appears without a frontend change.
  origins?: { key: string; label: string; credits_party: boolean }[];
}"""

ORIGINS_EP = r'''@app.get("/api/pipeline/origins")
def pipeline_origins(user: dict = Depends(get_current_user)):
    """The configured deal origins, for filters and the create form.

    Config-driven (ruling 2026-08-11: "in future I should be able to add more"),
    so an eighth origin appears in every dropdown without a frontend change.
    """
    from utils.deal_origin import origins, DEFAULT_ORIGIN
    return {"origins": origins(), "default": DEFAULT_ORIGIN}


'''

LEADERBOARD = r'''@app.get("/api/pipeline/leaderboard")
def pipeline_leaderboard(days: int = 30, start: str = "", end: str = "",
                         level: str = "staff", origin: str = "all",
                         branch: str = "", unit: str = "",
                         user: dict = Depends(get_current_user)):
    """Pipeline ranking, in TWO LEVELS: referral and direct.

    Ruling 2026-08-09: "on the pipeline ranking we will also have it in two
    levels, the referral and the direct pipeline from the sales team."

    A deal's VALUE counts once, for whoever owns it. The REFERRER is credited
    separately, under origin=referred, so a referred deal never inflates both
    the owner's and the referrer's totals as though the bank booked it twice.

    A referral counts only once ACCEPTED, matching the daily-log credit rule -
    a pending referral is an intention, not an outcome.

    level:  staff | role | branch | unit
    origin: all | referred | direct
    """
    from datetime import date as _date, timedelta as _td
    from utils.staff_code import canon as _canon_p

    deals = _acquire_scoped_deals(user)

    if start or end:
        lo = str(start or "0000-01-01")[:10]
        hi = str(end or "9999-12-31")[:10]
    else:
        hi = _date.today().isoformat()
        lo = (_date.today() - _td(days=max(int(days or 30), 1))).isoformat()

    def _when(d):
        return str(d.get("created_at") or d.get("open_date") or "")[:10]

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _accepted_referral(d):
        return bool(d.get("is_referral")) and str(d.get("referral_status") or "") == "accepted"

    live = [d for d in deals if not d.get("draft") and lo <= (_when(d) or lo) <= hi]

    # ORIGIN IS CONFIG, NOT A PAIR (ruling 2026-08-11). This filtered on
    # referred-versus-direct, which works for two origins and breaks at seven.
    # "referred" and "direct" are still accepted so an old bookmark or a stale
    # client does not silently return everything.
    from utils.deal_origin import origin_of as _origin_of, credits_party as _credits
    org = str(origin or "all").strip()
    if org == "referred":
        org = "referral"
    elif org == "direct":
        org = "self"
    if org and org != "all":
        live = [d for d in live if _origin_of(d) == org]

    # The roster dimensions the daily log already builds - cached, canonical,
    # and the same source the rankings and grids use. Inventing a second reader
    # here is how this codebase grew two of everything.
    from utils.api_branch_log import _roster_dims
    dims = _roster_dims()
    try:
        from utils.org_validator import unit_for_role, segment_for_role
    except Exception:
        unit_for_role = segment_for_role = lambda _r: ""

    # Attribute to the OWNER. For origin=referred we attribute to the REFERRER
    # instead - that is the whole point of the second level.
    rows_by_key: dict = {}
    for d in live:
        # When a single CREDITABLE origin is selected, attribute to the party
        # that origin credits - the referrer, the warehouse lister, the lead
        # generator, the contact-centre agent. Otherwise attribute to the owner.
        # Mixing the two in one table is what would double-count.
        if org and org != "all" and _credits(org):
            from utils.deal_origin import party_of as _party_of
            pcode, _pname = _party_of(d)
            code = _canon_p(pcode or "")
        else:
            code = _canon_p(d.get("staff_code") or "")
        if not code:
            continue
        dd = dims.get(code) or {}
        role = str(dd.get("role") or "")
        b = str(dd.get("branch") or "")
        u = unit_for_role(role) or ""
        try:
            from utils.org_validator import unit_label as _ul
            ulab = _ul(u) if u else ""
        except Exception:
            ulab = u
        if branch and b != branch:
            continue
        if unit and u != unit:
            continue
        # The executive office is not ranked (ruling 2026-08-11) - same rule as
        # the index ranking, so the two cannot disagree about who is in a table.
        try:
            from utils.org_validator import is_ranked as _ranked
            if not _ranked(u):
                continue
        except Exception:
            pass
        key = {"staff": code, "role": role, "branch": b, "unit": u}.get(level, code)
        if not key:
            key = "(unassigned)"
        e = rows_by_key.setdefault(key, {
            "key": key,
            "staff_code": code if level == "staff" else "",
            "name": (dd.get("full_name") or code) if level == "staff" else key,
            "role": role if level == "staff" else "",
            "branch": b if level == "staff" else "",
            "deals": 0, "value": 0.0, "weighted": 0.0, "won": 0, "lost": 0,
            "referred": 0,
            # Readable department name; the key still groups and filters.
            "label": ulab if level == "unit" else "",
        })
        e["deals"] += 1
        e["value"] += _val(d)
        e["weighted"] += _val(d) * _deal_probability(d)
        st = str(d.get("stage") or "")
        if st == "Closed Won":
            e["won"] += 1
        elif st == "Closed Lost":
            e["lost"] += 1
        if _accepted_referral(d):
            e["referred"] += 1

    rows = []
    for e in rows_by_key.values():
        closed = e["won"] + e["lost"]
        e["value"] = round(e["value"], 2)
        e["weighted"] = round(e["weighted"], 2)
        e["win_rate"] = round(e["won"] / closed * 100, 1) if closed else 0.0
        rows.append(e)
    rows.sort(key=lambda r: -r["value"])
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    from utils.deal_origin import origins as _origins
    return {
        "level": level, "origin": org, "start": lo, "end": hi,
        # The UI builds its filter from this, so a new origin appears without
        # a frontend change.
        "origins": [{"key": "all", "label": "All origins", "credits_party": False}]
                   + [{"key": o["key"], "label": o["label"],
                       "credits_party": o["credits_party"]} for o in _origins()],
        "rows": rows,
        "total_deals": len(live),
        "total_value": round(sum(r["value"] for r in rows), 2),
        "total_weighted": round(sum(r["weighted"] for r in rows), 2),
        "branches": sorted({r["branch"] for r in rows if r.get("branch")}),
    }


'''

ANALYTICS = r'''@app.get("/api/pipeline/analytics/summary")
def pipeline_analytics_summary(days: int = 30, start: str = "", end: str = "",
                               user: dict = Depends(get_current_user)):
    """Pipeline analytics over a reporting period, mirroring the index analytics.

    Same period model (rolling days, or an explicit calendar window for a
    quarter / year-to-date) and the same scope read, so the two analytics pages
    cannot disagree about the same population.

    Returns the journey conversion by bucket, the referred-vs-direct split, and
    the win/loss picture.
    """
    from datetime import date as _date, timedelta as _td
    from utils.pipeline_funnel import (
        stage_flows, flow_for_deal, bucket_view, micro_steps,
    )

    deals = _acquire_scoped_deals(user)

    if start or end:
        lo = str(start or "0000-01-01")[:10]
        hi = str(end or "9999-12-31")[:10]
    else:
        hi = _date.today().isoformat()
        lo = (_date.today() - _td(days=max(int(days or 30), 1))).isoformat()

    def _when(d):
        return str(d.get("created_at") or d.get("open_date") or "")[:10]

    live = [d for d in deals
            if not d.get("draft") and lo <= (_when(d) or lo) <= hi]

    won = [d for d in live if str(d.get("stage")) == "Closed Won"]
    lost = [d for d in live if str(d.get("stage")) == "Closed Lost"]
    open_deals = [d for d in live if str(d.get("stage")) not in ("Closed Won", "Closed Lost")]

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    # Journey conversion, per flow, using the SAME bucket view the funnel draws
    # so the two can never show different counts for the same stage.
    journey = []
    for flow in (stage_flows() or {}):
        mine = [d for d in open_deals if flow_for_deal(d) == flow]
        if not mine:
            continue
        journey.append({"flow": flow, "buckets": bucket_view(mine, flow),
                        "deals": len(mine)})
    journey.sort(key=lambda f: -f["deals"])

    # EVERY CONFIGURED ORIGIN, including the empty ones - an origin producing
    # no deals is a finding, and hiding it is how a channel dies quietly.
    from utils.deal_origin import summarise as _summarise
    origin = _summarise(live)

    closed = len(won) + len(lost)
    return {
        "start": lo, "end": hi, "days": days,
        "totals": {
            "deals": len(live),
            "open": len(open_deals),
            "won": len(won),
            "lost": len(lost),
            "open_value": round(sum(_val(d) for d in open_deals), 2),
            "won_value": round(sum(_val(d) for d in won), 2),
            "weighted": round(sum(_val(d) * _deal_probability(d) for d in open_deals), 2),
            "win_rate": round(len(won) / closed * 100, 1) if closed else 0.0,
        },
        "journey": journey,
        "origin": origin,
    }


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
        from utils.deal_origin import is_known as _known, DEFAULT_ORIGIN as _DEF
        _org = str(deal_dict.get("origin") or "").strip()
        deal_dict["origin"] = _org if _known(_org) else _DEF
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

TS_NEW = r'''export interface DealOrigin {
  key: string; label: string; credits_party: boolean;
  party_label?: string; active?: boolean; note?: string;
}
export interface PipelineOriginSplit {
  origin: string; label?: string; credits_party?: boolean;
  count: number; value: number; won: number;
}
export async function fetchDealOrigins(): Promise<{ origins: DealOrigin[]; default: string }> {
  return getJson<{ origins: DealOrigin[]; default: string }>('/pipeline/origins');
}
'''

PLEAD = r'''// PipelineLeaderboard — pipeline ranking in two levels: referral and direct.
//
// A deal's value counts once, for whoever owns it. Under "Referred" the same
// deals are attributed to the REFERRER instead, so a referred deal is never
// counted twice as though the bank booked it twice — the two views answer
// different questions about the same book.

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineLeaderboard, type PipelineLeaderboard as Board,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

type Level = 'unit' | 'branch' | 'role' | 'staff';
// Origin keys come from the server (ruling 2026-08-11: seven now, more later),
// so this is a plain string rather than a union that would need editing every
// time the bank adds a channel.
type Origin = string;

const LEVELS: { key: Level; label: string }[] = [
  { key: 'unit', label: 'Units' },
  { key: 'branch', label: 'Branches' },
  { key: 'role', label: 'Roles' },
  { key: 'staff', label: 'Individuals' },
];



const MEDAL = ['bg-[#BED600] text-[#3B6D11]', 'bg-[#E6F1FB] text-[#0C447C]', 'bg-[#FAEEDA] text-[#854F0B]'];

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export default function PipelineLeaderboard() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [level, setLevel] = useState<Level>('branch');
  const [origin, setOrigin] = useState<Origin>('all');
  const [data, setData] = useState<Board | null>(null);
  const [loading, setLoading] = useState(false);
  // Drill: clicking a unit / branch / role opens the INDIVIDUALS INSIDE IT,
  // ranked against each other. Ruling 2026-08-09: an individual is ranked
  // within their unit, not against the whole bank — a teller in Fortis and an
  // RM in Corporate are not competing, and a flat bank-wide list of 363 people
  // says nothing a manager can act on. The consolidated view stays available
  // to the MD's office through the tree itself.
  const [openRow, setOpenRow] = useState('');
  const [drill, setDrill] = useState<Board['rows'] | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      setData(await fetchPipelineLeaderboard({ ...a, level, origin }));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the pipeline ranking.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, level, origin, toast]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setOpenRow(''); setDrill(null); }, [level, origin, periodKey]);

  async function expand(key: string) {
    if (openRow === key) { setOpenRow(''); setDrill(null); return; }
    setOpenRow(key);
    setDrill(null);
    setDrillLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      // Narrow by whichever dimension this row is, then ask for the people.
      const extra = level === 'unit' ? { unit: key }
        : level === 'branch' ? { branch: key }
        : {};
      const r = await fetchPipelineLeaderboard({
        ...a, level: 'staff', origin, ...extra,
      });
      setDrill(r.rows);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open that row.' });
      setOpenRow('');
    } finally {
      setDrillLoading(false);
    }
  }

  // Filters are built from what the server reports, so an eighth origin needs
  // no frontend change. Declared after `data` exists.
  const origins = data?.origins
    ?? [{ key: 'all', label: 'All origins', credits_party: false }];
  const rows = data?.rows ?? [];
  const isStaff = level === 'staff';
  const max = Math.max(1, ...rows.map((r) => r.value));

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-900">Pipeline ranking</h2>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {LEVELS.map((l) => (
              <button key={l.key} type="button" onClick={() => setLevel(l.key)}
                className={'rounded-full px-3 py-1 font-medium '
                  + (level === l.key ? 'bg-[#0082BB] text-white'
                                     : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                {l.label}
              </button>
            ))}
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="ml-2 rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex overflow-hidden rounded-lg border border-gray-200">
            {origins.map((o) => (
              <button key={o.key} type="button" onClick={() => setOrigin(o.key)}
                className={'px-3 py-1 font-medium '
                  + (origin === o.key ? 'bg-[#005B82] text-white'
                                      : 'bg-white text-gray-600 hover:bg-gray-50')}>
                {o.label}
              </button>
            ))}
          </span>
          {(() => {
            const o = origins.find((x) => x.key === origin);
            return o?.credits_party ? (
              <span className="text-[11px] text-gray-500">
                credited to the {o.label.toLowerCase()} party, not the deal owner
              </span>
            ) : null;
          })()}
          {data && (
            <span className="ml-auto text-gray-500">
              {data.total_deals} deals · KES{' '}
              <span className="font-semibold text-gray-800">{kes(data.total_value)}</span>
              {' · '}KES {kes(data.total_weighted)} weighted
            </span>
          )}
        </div>

        {loading && <p className="py-8 text-center text-sm text-gray-400">Ranking…</p>}

        {!loading && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            {origin !== 'all'
              ? `No ${(origins.find((x) => x.key === origin)?.label ?? origin).toLowerCase()} deals in this period.`
              : 'Nothing to rank for this period.'}
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full table-fixed border-separate" style={{ borderSpacing: 0 }}>
              <colgroup>
                <col style={{ width: 44 }} />
                <col />
                {isStaff && <col style={{ width: '20%' }} />}
                {isStaff && <col style={{ width: '14%' }} />}
                <col style={{ width: 70 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 70 }} />
              </colgroup>
              <thead>
                <tr>
                  {['#', isStaff ? 'Staff' : LEVELS.find((l) => l.key === level)?.label,
                    ...(isStaff ? ['Role', 'Branch'] : []),
                    'Deals', 'Value (KES)', 'Weighted (KES)', 'Share', 'Win %'].map((h, i) => (
                    <th key={i}
                        className={'px-2 py-2 text-[11px] font-semibold uppercase '
                          + (i >= 4 ? 'text-right ' : 'text-left ')
                          + (h === 'Value (KES)' ? 'bg-[#0082BB] text-white' : 'bg-gray-100 text-gray-600')}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  const expanded = !isStaff && openRow === r.key;
                  return (
                    <>
                    <tr key={r.key}>
                      <td className={`${bg} px-2 py-1.5 text-xs`}>
                        <span className={'inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold '
                          + (r.rank <= 3 ? MEDAL[r.rank - 1] : 'text-gray-400')}>
                          {r.rank}
                        </span>
                      </td>
                      <td className={`${bg} truncate px-2 py-1.5 text-xs font-medium text-gray-900`}
                          title={r.label || r.name}>
                        {isStaff ? r.name : (
                          <button type="button" onClick={() => void expand(r.key)}
                                  className="flex items-center gap-1.5 text-left hover:text-brand-primary">
                            <span className="text-gray-400">{openRow === r.key ? '▾' : '▸'}</span>
                            {r.label || r.name}
                          </button>
                        )}
                      </td>
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.role}>
                          {r.role}
                        </td>
                      )}
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.branch}>
                          {r.branch}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-700`}>
                        {r.deals}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs font-semibold tabular-nums text-gray-900`}>
                        {kes(r.value)}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-600`}>
                        {kes(r.weighted)}
                      </td>
                      <td className={`${bg} px-2 py-1.5`}>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                          <div className="h-full rounded-full bg-[#0082BB]"
                               style={{ width: `${(r.value / max) * 100}%` }} />
                        </div>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums`}>
                        <span className={r.win_rate >= 50 ? 'text-[#3B6D11]' : 'text-gray-500'}>
                          {r.win_rate}%
                        </span>
                      </td>
                    </tr>
                    {expanded && (
                      <tr key={`${r.key}-drill`}>
                        <td colSpan={9} className="bg-[#F7FBFD] px-6 py-3">
                          {drillLoading && (
                            <p className="text-xs text-gray-400">Opening {r.key}…</p>
                          )}
                          {!drillLoading && drill && drill.length === 0 && (
                            <p className="text-xs text-gray-400">Nobody to show here.</p>
                          )}
                          {!drillLoading && drill && drill.length > 0 && (
                            <table className="w-full">
                              <thead>
                                <tr className="border-b border-gray-200">
                                  {['#', 'Staff', 'Name', 'Role', 'Deals',
                                    'Value (KES)', 'Weighted (KES)', 'Win %'].map((h, k) => (
                                    <th key={k}
                                        className={'py-1 pr-3 text-[10px] font-semibold uppercase tracking-wide text-gray-500 '
                                          + (k >= 4 ? 'text-right' : 'text-left')}>
                                      {h}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {drill.slice(0, 40).map((m) => (
                                  <tr key={m.key} className="border-b border-gray-100 last:border-0">
                                    <td className="w-8 py-1 pr-2 text-[11px] tabular-nums text-gray-400">{m.rank}</td>
                                    <td className="py-1 pr-3 text-xs tabular-nums text-gray-500" style={{ width: 80 }}>
                                      {m.staff_code}
                                    </td>
                                    <td className="py-1 pr-3 text-xs text-gray-800">{m.name}</td>
                                    <td className="truncate py-1 pr-3 text-xs text-gray-500" title={m.role}>
                                      {m.role}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-700" style={{ width: 60 }}>
                                      {m.deals}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs font-semibold tabular-nums text-gray-900" style={{ width: 120 }}>
                                      {kes(m.value)}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-600" style={{ width: 120 }}>
                                      {kes(m.weighted)}
                                    </td>
                                    <td className="py-1 text-right text-xs tabular-nums" style={{ width: 60 }}>
                                      <span className={m.win_rate >= 50 ? 'text-[#3B6D11]' : 'text-gray-500'}>
                                        {m.win_rate}%
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {!drillLoading && (drill?.length ?? 0) > 40 && (
                            <p className="mt-1 text-[11px] text-gray-400">
                              showing the top 40 of {drill?.length}
                            </p>
                          )}
                        </td>
                      </tr>
                    )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
'''

PANAL = r'''// PipelineAnalytics — the pipeline counterpart to the index analytics.
//
// Same period model, same scope read, so the two pages cannot disagree about
// the same population. Three questions, in the order management asks them:
//
//   Where is the money        open / weighted / won, and the win rate
//   Where does it stall       conversion through the journey, RAG per bucket
//   Where does it come from   referred versus direct

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineAnalyticsSummary, type PipelineAnalyticsSummary,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

// One colour per origin, in configured order - seven now, more later.
const ORIGIN_COLOURS = ['#0082BB', '#669438', '#E0A02B', '#9455B0',
                        '#C4536F', '#005B82', '#979797', '#3F6FC4'];

const RAG: Record<string, string> = {
  green: '#669438', amber: '#E0A02B', red: '#C4536F', idle: '#D8DBDF',
};

export default function PipelineAnalytics() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [data, setData] = useState<PipelineAnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      setData(await fetchPipelineAnalyticsSummary(a.days ?? 0, a.start ?? '', a.end ?? ''));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load pipeline analytics.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, toast]);

  useEffect(() => { void load(); }, [load]);

  const t = data?.totals;
  const originTotal = (data?.origin ?? []).reduce((a, o) => a + o.count, 0);

  return (
    <div className="space-y-4">
      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-gray-900">Pipeline analytics</h2>
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </Card.Header>
        <Card.Body>
          {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

          {!loading && !t && (
            <p className="py-8 text-center text-sm text-gray-400">No pipeline data for this period.</p>
          )}

          {!loading && t && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                { label: 'Open deals', value: t.open.toLocaleString(), tone: 'text-gray-900' },
                { label: 'Open value (KES)', value: kes(t.open_value), tone: 'text-[#0082BB]' },
                { label: 'Weighted (KES)', value: kes(t.weighted), tone: 'text-[#005B82]' },
                { label: 'Won (KES)', value: kes(t.won_value), tone: 'text-[#3B6D11]' },
                { label: 'Won', value: t.won.toLocaleString(), tone: 'text-[#3B6D11]' },
                { label: 'Lost', value: t.lost.toLocaleString(), tone: 'text-rose-600' },
                { label: 'Win rate', value: `${t.win_rate}%`, tone: 'text-gray-900' },
                { label: 'Deals in period', value: t.deals.toLocaleString(), tone: 'text-gray-900' },
              ].map((s) => (
                <div key={s.label} className="rounded-lg border border-gray-200 p-3">
                  <div className={`text-xl font-semibold tabular-nums ${s.tone}`}>{s.value}</div>
                  <div className="mt-0.5 text-[11px] text-gray-500">{s.label}</div>
                </div>
              ))}
            </div>
          )}
        </Card.Body>
      </Card>

      {!loading && (data?.journey ?? []).length > 0 && (
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Conversion through the journey</h2>
          </Card.Header>
          <Card.Body>
            <div className="space-y-5">
              {(data?.journey ?? []).map((f) => {
                const max = Math.max(1, ...f.buckets.map((b) => b.count));
                return (
                  <div key={f.flow}>
                    <div className="mb-1.5 flex items-baseline gap-2">
                      <span className="text-xs font-semibold capitalize text-gray-800">{f.flow}</span>
                      <span className="text-[11px] text-gray-400">{f.deals} open</span>
                    </div>
                    <div className="space-y-1">
                      {f.buckets.map((b) => (
                        <div key={b.key} className="flex items-center gap-2">
                          <span className="w-44 shrink-0 truncate text-[11px] text-gray-600"
                                title={b.label}>{b.label}</span>
                          <div className="h-4 flex-1 overflow-hidden rounded bg-gray-100">
                            <div className="h-full rounded"
                                 style={{ width: `${(b.count / max) * 100}%`,
                                          background: RAG[b.health.status] || RAG.idle }} />
                          </div>
                          <span className="w-10 shrink-0 text-right text-[11px] tabular-nums text-gray-700">
                            {b.count || '—'}
                          </span>
                          <span className="w-28 shrink-0 text-right text-[11px] tabular-nums text-gray-500">
                            {kes(b.value)}
                          </span>
                          <span className="w-24 shrink-0 text-right text-[10px] tabular-nums"
                                style={{ color: RAG[b.health.status] || RAG.idle }}>
                            {b.health.status === 'idle'
                              ? '—'
                              : `${b.health.avg_days}d / ${b.health.target_days}d`}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card.Body>
        </Card>
      )}

      {!loading && (data?.origin ?? []).length > 0 && (
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Where deals came from</h2>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(data?.origin ?? []).map((o, i) => (
                <div key={o.origin} className="rounded-lg border border-gray-200 p-3">
                  <div className="flex items-baseline justify-between">
                    <span className="text-sm font-semibold text-gray-800">
                      {o.label || o.origin}
                    </span>
                    <span className="text-xs tabular-nums text-gray-500">
                      {originTotal ? Math.round((o.count / originTotal) * 100) : 0}%
                    </span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-100">
                    <div className="h-full rounded-full"
                         style={{ width: `${originTotal ? (o.count / originTotal) * 100 : 0}%`,
                                  background: ORIGIN_COLOURS[i % ORIGIN_COLOURS.length] }} />
                  </div>
                  <div className="mt-2 flex gap-4 text-[11px] tabular-nums text-gray-600">
                    <span>{o.count} deals</span>
                    <span>KES {kes(o.value)}</span>
                    <span className="text-[#3B6D11]">{o.won} won</span>
                  </div>
                </div>
              ))}
            </div>
          </Card.Body>
        </Card>
      )}
    </div>
  );
}
'''


def _replace_block(src, start_marker, not_prefix, new):
    i = src.index(start_marker)
    m = re.search(r'\n@app\.(get|post)\("/api/(?!%s)' % not_prefix, src[i + 40:])
    j = i + 40 + m.start() + 1
    return src[:i] + new + src[j:]


def main():
    apply = "--apply" in sys.argv
    for p in (API, APITS, PL, PA):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1
    if not os.path.isfile(os.path.join("utils", "deal_origin.py")):
        print("ABORT: apply patch_or1_deal_origin.py first.")
        return 1

    api = open(API, encoding="utf-8").read()
    ts = open(APITS, encoding="utf-8").read()

    if '@app.get("/api/pipeline/origins")' in api:
        print("ABORT: the origins endpoint is already registered - OR2 looks applied.")
        return 1

    api = _replace_block(api, '@app.get("/api/pipeline/leaderboard")',
                         "pipeline/leaderboard", LEADERBOARD)
    api = _replace_block(api, '@app.get("/api/pipeline/analytics/summary")',
                         "pipeline/analytics", ANALYTICS)
    i = api.index("def pipeline_deal_create(")
    m = re.search(r'\n@app\.(get|post)\("/api/', api[i + 40:])
    api = api[:i] + CREATE + api[i + 40 + m.start() + 1:]
    api = api.replace('@app.get("/api/pipeline/leaderboard")',
                      ORIGINS_EP + '@app.get("/api/pipeline/leaderboard")', 1)
    print("  ok  api.py - origins endpoint, leaderboard, analytics, create")

    i = ts.index(TS_ANCHOR)
    ts = ts[:i] + TS_NEW + ts[i:]
    # The old split interface is replaced by the one inside TS_NEW.
    ts = ts.replace(TS_NEW + TS_ANCHOR + """
  origin: string; count: number; value: number; won: number;
}""", TS_NEW.rstrip(), 1)
    if ts.count(LB_IFACE_OLD) != 1:
        print("ABORT: leaderboard interface matched %d times." % ts.count(LB_IFACE_OLD))
        return 1
    ts = ts.replace(LB_IFACE_OLD, LB_IFACE_NEW, 1)
    print("  ok  api.ts - origin types and the leaderboard origins field")

    # A caller must not be able to name who gets credited.
    if "origin_party_code" not in CREATE:
        print("ABORT: origin_party_code is not privileged-at-create - a caller")
        print("       could declare who gets credited for their own deal.")
        return 1
    if "_known(_org)" not in CREATE:
        print("ABORT: create does not validate the origin against config.")
        return 1
    if "summarise" not in ANALYTICS:
        print("ABORT: analytics is not using the config-driven summary.")
        return 1
    if "_is_ref(" in ANALYTICS:
        print("ABORT: the dead referred/direct helper survives in analytics.")
        return 1
    for name, blob in (("leaderboard", PLEAD), ("analytics", PANAL)):
        if "ORIGINS: {" in blob or "'referred'" in blob.replace("'referred' are", ""):
            pass
        for op, cl in (("{", "}"), ("(", ")")):
            if blob.count(op) != blob.count(cl):
                print("ABORT: %s component unbalanced %s%s." % (name, op, cl))
                return 1
    if "data?.origins" not in PLEAD:
        print("ABORT: the ranking filter is not built from the server list.")
        return 1
    print("  ok  post-checks: party privileged, origin validated, filters dynamic")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((API, api), (APITS, ts), (PL, PLEAD), (PA, PANAL)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    try:
        py_compile.compile(API, doraise=True)
        print("  ok  api.py compiles")
    except Exception as exc:
        print("  FAIL %s" % exc)
        return 1

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd, restart uvicorn.")
    print("Then backfill so the analytics have origins to report:")
    print("  python scripts\\backfill_deal_origins.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
