"""
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
            # Scored HERE, on the shelf, not only on the detail page - a
            # completeness standard nobody sees while browsing is a standard
            # nobody backfills against.
            try:
                from utils.deals_warehouse import completeness as _cc
                _c = _cc(r)
                row["score"] = _c.get("score", 0)
                row["validated"] = _c.get("validated", False)
                row["missing_count"] = len(_c.get("missing", []))
            except Exception:
                row["score"] = 0
    # INSTITUTIONAL CONTACTS ARE SHOWN (ruling 2026-08-11: "why not
            # just display the contact"). A company switchboard or info@ address
            # published in a regulator's register is not personal data, and
            # hiding it made the shelf less useful for no protection.
            #
            # A NAMED PERSON still waits for a claim: "Jane Wanjiku, 0722..."
            # on an open shelf is exactly the case the Data Protection Act
            # covers, and it is the one field an RM adds by hand.
            row["contact_phone"] = r.get("contact_phone")
            row["contact_email"] = r.get("contact_email")
            if mine or admin:
                row["contact_name"] = r.get("contact_name")
                row["contacts_visible"] = True
            else:
                row["contacts_visible"] = False


    # INSTITUTIONAL CONTACTS ARE SHOWN (ruling 2026-08-11: "why not
            # just display the contact"). A company switchboard or info@ address
            # published in a regulator's register is not personal data, and
            # hiding it made the shelf less useful for no protection.
            #
            # A NAMED PERSON still waits for a claim: "Jane Wanjiku, 0722..."
            # on an open shelf is exactly the case the Data Protection Act
            # covers, and it is the one field an RM adds by hand.
            row["contact_phone"] = r.get("contact_phone")
            row["contact_email"] = r.get("contact_email")
            if mine or admin:
                row["contact_name"] = r.get("contact_name")
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


@router.get("/prospects/{prospect_id}")
def warehouse_detail(prospect_id: str, user: dict = Depends(get_current_user)):
    """Everything about one prospect, before deciding whether to pursue it.

    Ruling 2026-08-11: "an interested person can click to view more details
    before they can decide to pick."

    CONTACT DETAILS FOLLOW THE SAME RULE AS THE SHELF - visible to the lister,
    the claimer and admin only. Opening a detail page is not a claim, and a
    page that revealed contacts on a click would make the shelf's protection
    decorative.
    """
    from utils.deals_warehouse import get, information_card
    from utils.deals_warehouse import completeness
    rec = get(prospect_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No such prospect.")
    code, _n = _actor(user)
    mine = (str(rec.get("created_by_code") or "") == code
            or str(rec.get("claimed_by_code") or "") == code)
    visible = mine or _is_admin(user)

    # Every editable field travels, so the completeness table can be filled in
    # place rather than being a list of things you are told you lack.
    from utils.deals_warehouse import EDITABLE_FIELDS
    out = {k: rec.get(k) for k in
           ("id", "name", "sector", "town", "status", "estimated_value",
            "source_event", "notes", "created_by_name", "created_at",
            "claimed_by_name", "claimed_at", "deal_id")}
    for _f in EDITABLE_FIELDS:
        out.setdefault(_f, rec.get(_f))

    out["mine"] = mine
    out["contacts_visible"] = visible
    if visible:
        out.update({k: rec.get(k) for k in
                    ("contact_name", "contact_phone", "contact_email")})
    return {"prospect": out, "card": information_card(prospect_id),
            "completeness": completeness(rec)}


@router.post("/prospects/{prospect_id}/enrichment")
def warehouse_add_enrichment(prospect_id: str,
                             payload: dict = Body(default_factory=dict),
                             user: dict = Depends(get_current_user)):
    """Add a fact to a prospect's information card.

    ANYONE MAY ADD, deliberately. A note that a prospect just won a county
    tender is exactly the kind of thing that dies in one person's inbox, and
    restricting it to the lister would guarantee that. Every item records who
    added it and where it came from, which is the accountability that matters
    here.
    """
    from utils.deals_warehouse import add_enrichment
    code, name = _actor(user)
    try:
        item = add_enrichment(
            prospect_id,
            kind=str(payload.get("kind", "note") or "note"),
            title=str(payload.get("title", "") or ""),
            source=str(payload.get("source", "") or ""),
            url=str(payload.get("url", "") or ""),
            occurred_on=str(payload.get("occurred_on", "") or ""),
            detail=str(payload.get("detail", "") or ""),
            added_by=name or code,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_log("WAREHOUSE_ENRICH", str(user.get("username", "") or ""),
              detail="%s: %s" % (prospect_id, item["title"][:60]))
    return {"item": item}


@router.delete("/prospects/{prospect_id}")
def warehouse_delete(prospect_id: str, password: str = "",
                     user: dict = Depends(get_current_user)):
    """Delete a prospect outright. ADMIN ONLY.

    Archiving is for a business somebody judged not worth pursuing. Deletion is
    for a row that was never a business - a county name, a street, a fragment of
    a table that survived the import. Those do not belong in an audit trail.
    """
    from utils.deals_warehouse import delete, get
    if not _is_admin(user):
        raise HTTPException(status_code=403,
                            detail="Only an admin can delete a prospect. "
                                   "Archiving is available to whoever listed it.")
    rec = get(prospect_id)
    if not rec:
        raise HTTPException(status_code=404, detail="No such prospect.")
    try:
        # Admin rights say who MAY delete; the password says they meant to.
        delete(prospect_id, password=str(password or ""))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    audit_log("WAREHOUSE_DELETE", str(user.get("username", "") or ""),
              detail="%s %s" % (prospect_id, str(rec.get("name"))[:60]))
    return {"deleted": prospect_id}


@router.patch("/prospects/{prospect_id}")
def warehouse_update(prospect_id: str,
                     payload: dict = Body(default_factory=dict),
                     user: dict = Depends(get_current_user)):
    """Edit a prospect.

    OPEN while the record is under validation - that set exists to be filled
    in, and a password in front of backfilling would guarantee the backfilling
    never happens.

    PASSWORD-PROTECTED once validated. Somebody staked their name on those
    details and people are being told to prefer them, so changing one should be
    a deliberate act rather than a stray click.
    """
    from utils.deals_warehouse import update_prospect
    _code, name = _actor(user)
    changes = dict(payload or {})
    password = str(changes.pop("password", "") or "")
    try:
        rec = update_prospect(prospect_id, changes, by_name=name,
                              password=password)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    audit_log("WAREHOUSE_EDIT", str(user.get("username", "") or ""),
              detail="%s: %s" % (prospect_id, ", ".join(sorted(changes))[:60]))
    return {"prospect": {k: rec.get(k) for k in
                         ("id", "name", "sector", "town", "contact_name",
                          "contact_phone", "contact_email", "notes",
                          "validated", "last_edited_at", "last_edited_by")}}


@router.get("/completeness")
def warehouse_completeness(user: dict = Depends(get_current_user)):
    """The matrix itself, and how the warehouse scores against it.

    The FIELDS are returned alongside the summary so a capture form can show
    the standard while somebody is typing, rather than telling them afterwards
    what they should have entered.
    """
    from utils.deals_warehouse import (completeness_fields, completeness_summary,
                                       segments, sectors, towns)
    # The PICKLISTS travel with the matrix so a form can offer them without a
    # second round trip - and so every client offers the SAME options, which is
    # the whole reason they are lists rather than free text.
    return {"fields": completeness_fields(),
            "summary": completeness_summary(),
            "segments": segments(),
            "sectors": sectors(),
            "counties": towns()}





@router.post("/prospects/{prospect_id}/validate")
def warehouse_validate(prospect_id: str,
                       user: dict = Depends(get_current_user)):
    """Promote a complete entry to a validated, usable record.

    Deliberately NOT automatic at 100%. A record can be complete and wrong; the
    point of a usable set is that somebody looked and staked their name on it.
    The 400 names what is still missing rather than just refusing.
    """
    from utils.deals_warehouse import validate_prospect
    code, name = _actor(user)
    try:
        return {"completeness": validate_prospect(prospect_id, code, name)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


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
