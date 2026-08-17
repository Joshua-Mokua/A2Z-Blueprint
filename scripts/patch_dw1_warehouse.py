#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DW1 - the Deals Warehouse. Backend: prospects, shelves, claiming.

RULING (2026-08-09): "a referral is direct to a person, the warehouse is a
prospect ... anyone can log in and create a potential deal worth pursuing. If
one has no deal at all to pursue they can get into the warehouse to look for
potential deals. Once they identify, they can pick to pursue, then that deal
also roots back to the person who created it as a referral."

A PROSPECT IS NOT A DEAL. It is an opportunity nobody owns, sitting on a shared
shelf, until someone claims it - at which point it becomes a real deal owned by
the claimer and the lister is credited as the referrer.

WHY A CLAIM IS A REFERRAL ACCEPTANCE. The credit rule is already settled:
referrals credit on ACCEPTANCE. A claim IS the acceptance - someone has taken
the work on - so the lister is credited on the day they listed it, derived at
read time, exactly like a direct referral. One rule, two routes in, no second
arithmetic to keep in step.

FIRST CLAIM WINS (ruling 2026-08-09), checked INSIDE the lock. Checking outside
would let two officers who each loaded the shelf a second apart both believe
they had it, and both call the customer.

SHELVES are SECTOR (16) and TOWN (Kenya's 47 counties), both config-overridable
via warehouse_sectors / warehouse_towns. Towns are NOT derived from the branch
network: org_config.branches carries `region` values that are ORG ROLE NAMES
("Head of Branches"), not geography, and `county` is empty - the first draft
derived from it and silently produced one nonsense entry.

Only a NAME is required to list a prospect. One jotted down at an event with a
name and a phone number is still worth having; demanding a full taxonomy at
capture is how a shelf ends up empty. Unsectored records go to an "Unsorted"
shelf rather than being hidden.

CONTACT DETAILS ARE WITHHELD from the browse view. Anyone can see that an
opportunity exists, where it is and roughly what it is worth - that is what lets
an officer with nothing to pursue find something. The named contact and their
phone number appear only to the lister, the claimer and admin, because a shared
shelf of every prospect's personal contact details is a data-protection problem
rather than a sales tool.

ARCHIVED, NEVER DELETED, and a reason is required - a prospect somebody judged
not worth pursuing is itself worth knowing next time the name comes up.

ENDPOINTS
    GET  /api/warehouse/taxonomy
    GET  /api/warehouse/shelves?status=&town=&sector=&q=
    POST /api/warehouse/prospects
    POST /api/warehouse/prospects/{id}/claim      409 if already taken
    POST /api/warehouse/prospects/{id}/deal
    POST /api/warehouse/prospects/{id}/archive
    GET  /api/warehouse/mine                      listed / claimed / stale

MEASURED: shelves group by sector with Unsorted for the rest; a second claim is
refused naming who has it; claiming your own listing is refused rather than
producing a self-referral.

NOT FOR THE PILOT YET (ruling 2026-08-11): "anything on the warehouse is not to
be released to Alex until I am certain it is well built." Add
patch_dw1_warehouse to NOT_FOR_RELEASE in build_alex_release.py before the next
release.

FRONTEND IS DW2.

Usage (from project root, .venv active):
    python scripts\patch_dw1_warehouse.py            # dry run
    python scripts\patch_dw1_warehouse.py --apply
"""
import os
import shutil
import sys

STORE = os.path.join("utils", "deals_warehouse.py")
APIW = os.path.join("utils", "api_warehouse.py")
API = os.path.join("utils", "api.py")
BACKUP_SUFFIX = ".pre_dw1"

ANCHOR = """from utils.api_branch_log import router as branch_log_router
app.include_router(branch_log_router)"""

WIRE = """from utils.api_branch_log import router as branch_log_router
app.include_router(branch_log_router)

# Deals Warehouse - the shared shelf of prospects. NOT released to the pilot
# until the build is settled (ruling 2026-08-11).
from utils.api_warehouse import router as warehouse_router
app.include_router(warehouse_router)"""

STORE_SRC = r'''"""
utils/deals_warehouse — the shared shelf of prospects.

RULING (2026-08-09): "a referral is direct to a person, the warehouse is a
prospect ... anyone can log in and create a potential deal worth pursuing with
more details, maybe on contacts, location noted. If one has no deal at all to
pursue they can get into the warehouse to look for potential deals. Once they
identify, they can pick to pursue, then that deal also roots back to the person
who created it as a referral."

So a prospect is NOT a deal. It is an opportunity nobody owns yet, sitting on a
shelf, until someone claims it - at which point it becomes a real deal owned by
the claimer, and the person who put it there is credited as the referrer.

WHY CLAIMING IS A REFERRAL ACCEPTANCE. The credit rule is already settled:
referrals credit on ACCEPTANCE (ruling 2026-08-09). A claim IS the acceptance -
someone has taken the work on - so the lister is credited on the day they listed
it, derived at read time, exactly like a direct referral. One rule, two routes
in, no second arithmetic to keep in step.

FIRST CLAIM WINS (ruling 2026-08-09). A claimed prospect leaves the shelf and
the lister sees who took it. Allowing several officers to pursue one prospect
would put several people from the same bank in front of one customer, which is
worse than an idle prospect.

SHELVES are SECTOR and TOWN. Both come from config so the bank can reshape them
without a deploy, and both are optional on a record: a prospect somebody jotted
down at an event with only a name and a phone number is still worth having, and
demanding a full taxonomy at capture is how a shelf ends up empty.

Store: data/deals_warehouse.json, written atomically (mkstemp/fsync/os.replace)
so a crash mid-write cannot truncate the file - the same pattern as branch_day.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import uuid
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

_PATH = os.path.join("data", "deals_warehouse.json")
_lock = threading.Lock()

STATUS_AVAILABLE = "available"
STATUS_CLAIMED = "claimed"
STATUS_CONVERTED = "converted"
STATUS_ARCHIVED = "archived"

# Fallback taxonomy. Config wins - see sectors()/towns(). These exist so a fresh
# install has usable shelves rather than a free-text field that fragments into
# forty spellings of the same sector.
DEFAULT_TOWNS = [
    "Nairobi", "Mombasa", "Kisumu", "Nakuru", "Uasin Gishu (Eldoret)",
    "Kiambu", "Machakos", "Kajiado", "Nyeri", "Meru", "Kakamega", "Bungoma",
    "Kilifi", "Kericho", "Trans Nzoia (Kitale)", "Nyandarua", "Muranga",
    "Embu", "Kirinyaga", "Laikipia", "Narok", "Bomet", "Kisii", "Nyamira",
    "Migori", "Homa Bay", "Siaya", "Busia", "Vihiga", "Baringo", "Nandi",
    "Elgeyo Marakwet", "West Pokot", "Turkana", "Samburu", "Isiolo",
    "Marsabit", "Mandera", "Wajir", "Garissa", "Tana River", "Lamu",
    "Taita Taveta", "Kwale", "Makueni", "Kitui", "Tharaka Nithi",
]

DEFAULT_SECTORS = [
    "Agriculture & Agribusiness", "Manufacturing", "Wholesale & Retail Trade",
    "Transport & Logistics", "Construction & Real Estate", "Hospitality & Tourism",
    "Education", "Health & Pharmaceuticals", "Financial Services",
    "ICT & Telecommunications", "Energy & Extractives", "Professional Services",
    "Media & Creative", "NGO & Development", "Public Sector", "Other",
]


def _read() -> dict:
    if not os.path.exists(_PATH):
        return {}
    try:
        with open(_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as exc:
        # RAISE, never return {} silently. An empty read here would look like
        # an empty warehouse, and the next write would erase every prospect in
        # it - the same destructive read-modify-write that cost us
        # pipeline_settings.json.
        raise RuntimeError("deals_warehouse.json unreadable: %s" % exc) from exc


def _write(data: dict) -> None:
    os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(_PATH) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, _PATH)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def sectors() -> list:
    """Shelf categories. Config first, defaults second."""
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_sectors")
        if isinstance(v, list) and v:
            return [str(x) for x in v if str(x).strip()]
    except Exception:
        pass
    return list(DEFAULT_SECTORS)


def towns() -> list:
    """Towns of operation. Config first; otherwise derived from the branch
    network, because the bank already knows where it operates and a hand-typed
    town list would drift from it immediately."""
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_towns")
        if isinstance(v, list) and v:
            return [str(x) for x in v if str(x).strip()]
    except Exception:
        pass
    # NOT derived from the branch network: org_config.branches carries `region`
    # values that are ORG ROLE NAMES ("Head of Branches"), not geography, and
    # `county` is empty. A town list built from that would have looked
    # deliberate and been nonsense.
    #
    # Kenya's counties are stable public reference data and are what an RM
    # actually means by "town of operation" at this granularity. The bank can
    # replace the list wholesale via warehouse_towns.
    return list(DEFAULT_TOWNS)
    return []


def all_prospects() -> list:
    return list((_read() or {}).values())


def get(prospect_id: str) -> Optional[dict]:
    return (_read() or {}).get(str(prospect_id))


def create(*, name: str, created_by_code: str, created_by_name: str,
           sector: str = "", town: str = "", contact_name: str = "",
           contact_phone: str = "", contact_email: str = "",
           notes: str = "", source_event: str = "",
           estimated_value: float = 0.0) -> dict:
    """List a prospect on the shelf.

    Only the NAME is required. A prospect jotted down at an event with a name
    and a phone number is still worth having; demanding a full taxonomy at
    capture is how a shelf ends up empty.
    """
    nm = str(name or "").strip()
    if not nm:
        raise ValueError("A prospect needs a name.")
    if not str(created_by_code or "").strip():
        raise ValueError("A prospect must record who listed it - that is who "
                         "gets the referral credit when it is claimed.")

    now = datetime.now().isoformat(timespec="seconds")
    pid = "WH" + uuid.uuid4().hex[:10].upper()
    rec = {
        "id": pid,
        "name": nm,
        "sector": str(sector or "").strip(),
        "town": str(town or "").strip(),
        "contact_name": str(contact_name or "").strip(),
        "contact_phone": str(contact_phone or "").strip(),
        "contact_email": str(contact_email or "").strip(),
        "notes": str(notes or "").strip(),
        "source_event": str(source_event or "").strip(),
        "estimated_value": float(estimated_value or 0),
        "status": STATUS_AVAILABLE,
        "created_by_code": str(created_by_code).strip(),
        "created_by_name": str(created_by_name or "").strip(),
        "created_at": now,
        "claimed_by_code": "",
        "claimed_by_name": "",
        "claimed_at": "",
        "deal_id": "",
    }
    with _lock:
        data = _read()
        data[pid] = rec
        _write(data)
    return rec


def claim(prospect_id: str, by_code: str, by_name: str) -> dict:
    """Take a prospect off the shelf.

    FIRST CLAIM WINS, checked INSIDE the lock. Checking outside would let two
    officers who both loaded the shelf a second apart each believe they had it,
    and both call the customer.
    """
    pid = str(prospect_id)
    code = str(by_code or "").strip()
    if not code:
        raise ValueError("Cannot claim without a staff code.")
    with _lock:
        data = _read()
        rec = data.get(pid)
        if not rec:
            raise ValueError("That prospect no longer exists.")
        if rec.get("status") != STATUS_AVAILABLE:
            who = rec.get("claimed_by_name") or "someone else"
            raise ValueError("Already taken by %s." % who)
        if str(rec.get("created_by_code") or "") == code:
            # Not forbidden by any ruling, but pointless: it would credit the
            # lister with referring to themselves. Say so rather than silently
            # produce a self-referral.
            raise ValueError("You listed this prospect - pursue it directly "
                             "rather than claiming your own referral.")
        rec["status"] = STATUS_CLAIMED
        rec["claimed_by_code"] = code
        rec["claimed_by_name"] = str(by_name or "").strip()
        rec["claimed_at"] = datetime.now().isoformat(timespec="seconds")
        data[pid] = rec
        _write(data)
    return rec


def attach_deal(prospect_id: str, deal_id: str) -> Optional[dict]:
    """Record which deal a claimed prospect became."""
    with _lock:
        data = _read()
        rec = data.get(str(prospect_id))
        if not rec:
            return None
        rec["deal_id"] = str(deal_id or "")
        rec["status"] = STATUS_CONVERTED if deal_id else rec.get("status")
        data[str(prospect_id)] = rec
        _write(data)
    return rec


def archive(prospect_id: str, by_code: str, reason: str = "") -> dict:
    """Take a prospect off the shelf without pursuing it.

    Only the lister or an admin should reach this - the endpoint enforces that.
    Archived, never deleted: a prospect somebody judged not worth pursuing is
    itself worth knowing next time the same name comes up.
    """
    with _lock:
        data = _read()
        rec = data.get(str(prospect_id))
        if not rec:
            raise ValueError("That prospect no longer exists.")
        rec["status"] = STATUS_ARCHIVED
        rec["archived_by_code"] = str(by_code or "")
        rec["archived_reason"] = str(reason or "")
        rec["archived_at"] = datetime.now().isoformat(timespec="seconds")
        data[str(prospect_id)] = rec
        _write(data)
    return rec


def shelves(status: str = STATUS_AVAILABLE) -> dict:
    """{sector: [prospect, ...]} for browsing, newest first within a shelf.

    Prospects with no sector go to "Unsorted" rather than being hidden - a
    record captured in a hurry is exactly the one somebody should be able to
    find and tidy.
    """
    out: dict = {}
    for rec in all_prospects():
        if status and rec.get("status") != status:
            continue
        key = str(rec.get("sector") or "").strip() or "Unsorted"
        out.setdefault(key, []).append(rec)
    for k in out:
        out[k].sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return out


def stale(days: int = 30, status: str = STATUS_AVAILABLE) -> list:
    """Prospects nobody has claimed in N days.

    Surfaced to the LISTER, not buried: an idle prospect is either worth
    chasing differently or worth archiving, and both need a person to decide.
    """
    from datetime import date, timedelta
    cutoff = (date.today() - timedelta(days=max(int(days or 0), 0))).isoformat()
    return [r for r in all_prospects()
            if r.get("status") == status
            and str(r.get("created_at") or "")[:10] <= cutoff]
'''

API_SRC = r'''"""
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
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1
    for p in (STORE, APIW):
        if os.path.exists(p):
            print("ABORT: %s already exists - DW1 looks applied." % p)
            return 1

    api = open(API, encoding="utf-8").read()
    if "api_warehouse" in api:
        print("ABORT: the warehouse router is already registered.")
        return 1
    if api.count(ANCHOR) != 1:
        print("ABORT: router anchor matched %d times." % api.count(ANCHOR))
        return 1

    for token in ("def claim(", "FIRST CLAIM WINS", "_write", "DEFAULT_TOWNS",
                  "DEFAULT_SECTORS"):
        if token not in STORE_SRC:
            print("ABORT: embedded store missing %r." % token)
            return 1
    # A silent empty read here would look like an empty warehouse, and the next
    # write would erase every prospect in it.
    # An absent file IS an empty warehouse - returning {} there is correct.
    # What must never happen is returning {} on a READ ERROR: the next write
    # would then erase every prospect. Check the except branch RAISES.
    _read_src = STORE_SRC.split("def _read")[1].split("def _write")[0]
    if "raise RuntimeError" not in _read_src:
        print("ABORT: _read does not raise on a failed read. Returning {} there")
        print("       would erase the shelf on the next write - the same")
        print("       destructive read-modify-write that cost pipeline_settings.")
        return 1
    for token in ("contacts_visible", "409", "def warehouse_claim"):
        if token not in API_SRC:
            print("ABORT: embedded endpoints missing %r." % token)
            return 1

    api = api.replace(ANCHOR, WIRE, 1)
    if api.count("include_router(warehouse_router)") != 1:
        print("ABORT: post-check - router registered %d times."
              % api.count("include_router(warehouse_router)"))
        return 1
    if api.count("include_router(branch_log_router)") != 1:
        print("ABORT: post-check - the branch-log router registration changed.")
        return 1
    print("  ok  store and endpoints validated; router registered once")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(STORE, "w", encoding="utf-8", newline="").write(STORE_SRC)
    print("CREATED %s" % STORE)
    open(APIW, "w", encoding="utf-8", newline="").write(API_SRC)
    print("CREATED %s" % APIW)
    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s" % API)

    import py_compile
    for path in (STORE, APIW, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("Restart uvicorn. The shelf is empty until someone lists a prospect.")
    print("REMINDER: add patch_dw1_warehouse to NOT_FOR_RELEASE in")
    print("scripts/build_alex_release.py before the next pilot release.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
