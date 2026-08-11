"""
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
