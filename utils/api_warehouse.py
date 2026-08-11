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
    return {"prospect": rec,
            "referrer_code": rec.get("created_by_code"),
            "referrer_name": rec.get("created_by_name")}


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
    out = attach_deal(prospect_id, str(payload.get("deal_id", "") or ""))
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
