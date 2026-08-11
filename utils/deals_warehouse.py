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
import re
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


# ── THE DUPLICATE RULE ──────────────────────────────────────────────────────
# RULING (2026-08-11): "what rule can we put in place that ensures the list is
# clean and there are no duplicates - we need to build a formidable database."
#
# Exact-name matching is not enough. These are the SAME business:
#
#     Mwalimu National Sacco Society Ltd
#     MWALIMU NATIONAL SACCO SOCIETY LIMITED
#     Mwalimu National Sacco Society Ltd.
#     Mwalimu  National  Sacco  Society
#
# So every prospect carries a CANONICAL KEY: lowercased, punctuation removed,
# whitespace collapsed, and the legal suffix stripped - because "Ltd" and
# "Limited" are the same company and a register will spell it both ways across
# two documents.
#
# The key is STORED, not recomputed on read. If the normalising rules change
# later, existing records keep the key they were admitted under, so a rule
# change cannot suddenly declare two long-standing prospects to be duplicates.
# WORD BY WORD, not longest-phrase-first. Phrase matching was inconsistent:
# "2NK Sacco Society Ltd" stripped "society ltd" leaving "2nk sacco", while
# "2NK Sacco Society" stripped "sacco society" leaving "2nk" - so the same
# business produced two keys and the duplicate slipped through. Peeling one
# trailing word at a time always converges on the same answer.
_SUFFIX_WORDS = {
    "limited", "ltd", "ltd.", "plc", "company", "co", "society", "sacco",
    "incorporated", "inc", "llp", "llc", "cooperative", "coop",
}


def canonical_key(name: str) -> str:
    """One key per real-world business, whatever the spelling."""
    n = str(name or "").lower()
    n = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in n)
    n = " ".join(n.split())
    words = n.split()
    # Peel trailing suffix words, but NEVER to nothing: a society actually
    # named "Sacco Society Limited" would otherwise canonicalise to an empty
    # key and collide with every other fully-stripped name.
    while len(words) > 1 and words[-1] in _SUFFIX_WORDS:
        words.pop()
    return " ".join(words)


def find_duplicate(name: str, records: Optional[list] = None) -> Optional[dict]:
    """The existing prospect this name would duplicate, or None."""
    key = canonical_key(name)
    if not key:
        return None
    for r in (records if records is not None else all_prospects()):
        if (r.get("canonical_key") or canonical_key(r.get("name", ""))) == key:
            return r
    return None


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
    key = canonical_key(nm)
    rec = {
        "id": pid,
        "name": nm,
        "canonical_key": key,
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
        # Checked INSIDE the lock: two imports running a second apart would
        # otherwise each find nothing and both write the same business.
        dupe = find_duplicate(nm, list(data.values()))
        if dupe:
            raise ValueError(
                "Already on the shelf as %r (listed by %s)."
                % (dupe.get("name"), dupe.get("created_by_name") or "someone"))
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


def delete(prospect_id: str, password: str = "") -> bool:
    """Remove a prospect entirely. ADMIN ONLY - the endpoint enforces that.

    RULING (2026-08-11): "for the admin I need to be able to delete an entry as
    a whole so that items like Mombasa that are not saccos I can delete."

    Distinct from archive() on purpose. ARCHIVE says "we looked at this and
    decided not to pursue it" and is worth keeping. DELETE says "this was never
    a business" - a county name, a street, a fragment of a table. Keeping those
    would leave the audit trail full of noise that teaches nobody anything.
    """
    pid = str(prospect_id or "").strip()
    with _lock:
        data = _read()
        if pid not in data:
            return False
        # A VALIDATED record needs the password even for an admin. Admin rights
        # say who MAY delete; the password says they meant to.
        if data[pid].get("validated") and password != protected_password():
            raise PermissionError(
                "This is a validated record. Deleting it needs the warehouse "
                "password.")
        del data[pid]
        _write(data)
    return True


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


# ── THE COMPLETENESS MATRIX ─────────────────────────────────────────────────
# RULING (2026-08-11): "establish 10 must-have fields as a measure for a
# completeness index, scoring each entry, and once done it is marked complete.
# This ensures we keep backfilling, and sets the rules of what a complete entry
# looks like for anyone keying in data. Then a validation check - once an entry
# is fully complete it can be validated and stored as a record that can be
# used."
#
# THE TEN ARE WHAT SOMEBODY NEEDS TO APPROACH A BUSINESS WITH CONFIDENCE. Not
# ten arbitrary boxes: each answers a question an RM would otherwise have to
# ask, and a prospect missing several is one nobody can act on.
#
#     WHO      legal name · registration number
#     WHAT     sector · what they do
#     WHERE    county · physical address
#     REACH    phone · email
#     WHO TO   decision maker and their role
#     HOW BIG  a size indicator - turnover, members, staff
#
# WEIGHTED, because they are not equal. A name with no phone number is further
# from usable than a phone number with no registration number, and an unweighted
# score would call those the same.
#
# CONFIG-DRIVEN via warehouse_completeness, so the bank can change the standard
# without a release - the same rule as origins, channels and activity sets.
#
# SCORED FROM THE RECORD *AND* ITS CARD. A phone number added as an enrichment
# item counts exactly as much as one typed into the contact field; requiring it
# in a particular place would punish people for using the tool as intended.
DEFAULT_COMPLETENESS = [
    {"key": "name", "label": "Legal name", "weight": 15,
     "why": "Who they are, as registered."},
    # REGISTRATION NUMBER REPLACED (ruling 2026-08-11: "that might be hard to
    # obtain, we can replace it with another piece"). It is real but it is
    # locked behind BRS, so it would sit unanswered on almost every record and
    # drag the score down without anybody being able to fix it. A field nobody
    # can fill is not a standard, it is a permanent deduction.
    #
    # Branches are visible, useful to every purpose, and were on the original
    # wish list for the card.
    {"key": "branches", "label": "Branches or footprint", "weight": 10,
     "why": "Where they actually operate - and how big that makes them."},
    {"key": "sector", "label": "Sector", "weight": 10,
     "why": "Decides which products are even relevant."},
    {"key": "county", "label": "County", "weight": 10,
     "why": "Decides which branch owns the conversation."},
    {"key": "physical_address", "label": "Physical address", "weight": 8,
     "why": "You cannot visit a postal box."},
    {"key": "phone", "label": "Phone", "weight": 12,
     "why": "Without it nobody can start."},
    {"key": "email", "label": "Email", "weight": 8,
     "why": "For anything that needs a paper trail."},
    {"key": "decision_maker", "label": "Decision maker and role", "weight": 15,
     "why": "The single thing that turns a cold call into a meeting."},
    {"key": "size_indicator", "label": "Size - turnover, members or staff", "weight": 7,
     "why": "Tells you which desk should hold it."},
    {"key": "business_activity", "label": "What they actually do", "weight": 5,
     "why": "A sector is a category; this is the business."},
    # FIVE MORE (ruling 2026-08-11: "expand the field to at least 15 so that we
    # stretch our viability and give our models a better accuracy chance").
    # These are the ones that separate a contactable business from a
    # QUALIFIABLE one - they are what a viability score will be built on.
    {"key": "established", "label": "Year established", "weight": 5,
     "why": "Longevity is the cheapest risk signal there is."},
    # SEGMENT REPLACES LEGAL FORM (ruling 2026-08-11: "I don't understand what
    # legal is, but I would instead look for information like Segment"). Legal
    # form is a lawyer's category; segment is the one the bank actually
    # organises itself around, and it decides which desk holds the
    # relationship.
    {"key": "segment", "label": "Segment", "weight": 3,
     "why": "Which desk holds the relationship."},
    {"key": "existing_banker", "label": "Who they bank with now", "weight": 6,
     "why": "Tells you whether this is a switch, a share, or a first account."},
    {"key": "online_presence", "label": "Website or verified listing", "weight": 3,
     "why": "Somewhere to check the story before the meeting."},
    # "IDENTIFIED NEED" WAS PIPELINE LANGUAGE (ruling 2026-08-11: "that would
    # mean this is only for pipeline - we are building a warehouse that can be
    # used across various needs, and pipeline is one of them"). A warehouse
    # should not bake one consumer's vocabulary into its schema.
    {"key": "value_chain", "label": "Value chain and potential needs", "weight": 8,
     "why": "What they buy, sell and depend on - which serves sales, credit "
            "and sector analysis alike, not just a deal."},
]

STATUS_VALIDATED = "validated"

# PICKED, NOT TYPED (ruling 2026-08-11: "for those we have autopopulated we
# need a drop down, e.g. Sector, so that for our analysis we don't have
# mismatches that are a result of mistyping"). Free text here would produce
# "SME", "S.M.E", "Sme" and "Small" as four segments in every report.
DEFAULT_SEGMENTS = [
    "Micro", "Small Enterprise", "Medium Enterprise", "Large Enterprise",
    "Corporate", "Institution", "Public Sector", "NGO / Development",
]


def segments() -> list:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_segments")
        if isinstance(v, list) and v:
            return [str(x) for x in v if str(x).strip()]
    except Exception:
        pass
    return list(DEFAULT_SEGMENTS)

# RULING (2026-08-11): "a threshold for submitting for validation to begin
# should be at least 80% and above, then the additional can be completed from
# validation."
#
# 100% was the wrong bar. It meant a record with fourteen of fifteen fields sat
# unusable beside one with four, and the last field is often the hardest to get
# - so demanding it would leave good records stranded in the working set
# forever. Eighty per cent says "enough to act on"; the remainder is finished
# during validation by the person who is looking anyway.
DEFAULT_VALIDATION_THRESHOLD = 80


def validation_threshold() -> int:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_validation_threshold")
        if isinstance(v, (int, float)) and 0 < float(v) <= 100:
            return int(v)
    except Exception:
        pass
    return DEFAULT_VALIDATION_THRESHOLD

# Legal form can usually be read off the name itself - a register that says
# "Sacco Society Ltd" has already told you what kind of entity this is, and
# asking somebody to retype it would be busywork.
_LEGAL_FORM = re.compile(
    r"\b(ltd|limited|plc|llp|llc|sacco|society|co-?operative|co-?op|trust"
    r"|foundation|association|union|scheme|bank|ngo)\b", re.IGNORECASE)


def completeness_fields() -> list:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_completeness")
        if isinstance(v, list) and v:
            return [f for f in v if isinstance(f, dict) and f.get("key")]
    except Exception:
        pass
    return [dict(f) for f in DEFAULT_COMPLETENESS]


def _has(rec: dict, key: str) -> bool:
    """Is this field answered - anywhere on the record or its card?"""
    def _t(*names):
        return any(str(rec.get(n) or "").strip() for n in names)

    items = rec.get("enrichment") or []

    def _card(*kinds):
        return any(str(i.get("title") or "").strip()
                   for i in items if i.get("kind") in kinds)

    if key == "name":
        return _t("name")
    if key == "branches":
        return _t("branches", "footprint") or _card("association")
    if key == "sector":
        return _t("sector") and str(rec.get("sector")).strip().lower() != "unsorted"
    if key == "county":
        return _t("town")
    if key == "physical_address":
        return _t("physical_address", "address") or _card("contact")
    if key == "phone":
        return _t("contact_phone") or _card("contact")
    if key == "email":
        return _t("contact_email") or _card("contact")
    if key == "decision_maker":
        return _t("contact_name") or _card("relationship")
    if key == "size_indicator":
        return bool(rec.get("estimated_value")) or _card("financial")
    if key == "business_activity":
        return _t("notes") or _card("note", "news")
    if key == "established":
        return _t("established", "year_established") or _card("filing")
    if key == "segment":
        return _t("segment")
    if key == "existing_banker":
        return _t("existing_banker") or _card("relationship")
    if key == "online_presence":
        return _t("website", "url") or any(
            str(i.get("url") or "").strip() for i in items)
    if key == "value_chain":
        return _t("value_chain", "opportunity") or _card("note")
    return _t(key)


def completeness(prospect_id_or_rec) -> dict:
    """Score one prospect against the matrix.

    Returns the score, what is answered, and WHAT IS MISSING with the reason it
    matters - because a score alone tells somebody they are incomplete without
    telling them what to do about it.
    """
    rec = (prospect_id_or_rec if isinstance(prospect_id_or_rec, dict)
           else get(prospect_id_or_rec))
    if not rec:
        return {}
    fields = completeness_fields()
    total = sum(int(f.get("weight") or 0) for f in fields) or 1
    have, missing, got = [], [], 0
    for f in fields:
        if _has(rec, f["key"]):
            have.append(f["key"])
            got += int(f.get("weight") or 0)
        else:
            missing.append({"key": f["key"], "label": f.get("label") or f["key"],
                            "why": f.get("why") or "", "weight": f.get("weight")})
    pct = round(got / total * 100)
    bar = validation_threshold()
    return {
        "prospect_id": rec.get("id"),
        "score": pct,
        # "complete" now means READY TO VALIDATE, not perfect. The two are
        # reported separately so nobody has to guess which one a number means.
        "complete": pct >= bar,
        "fully_complete": pct >= 100,
        "threshold": bar,
        "have": have,
        "missing": missing,
        "answered": len(have),
        "of": len(fields),
        "validated": rec.get("validated") is True,
        "validated_by": rec.get("validated_by") or "",
        "validated_at": rec.get("validated_at") or "",
        # A record edited AFTER validation is no longer the record that was
        # validated. Saying so is more honest than silently keeping the badge.
        "stale_validation": bool(
            rec.get("validated") and rec.get("last_edited_at")
            and str(rec.get("last_edited_at")) > str(rec.get("validated_at") or "")),
    }


# ── HOUSE STYLE ─────────────────────────────────────────────────────────────
# RULING (2026-08-11): "the input format should default to standard - if it is
# upper case, then Proper while saving. Avoid double spacing and no spacing at
# the end. This is to protect the larger data sets."
#
# NORMALISED ON THE WAY IN, NOT ON THE WAY OUT. Cleaning at display time leaves
# the mess in the store, so the next consumer - an export, a match, a dedupe -
# still meets "MWALIMU  NATIONAL SACCO " and treats it as a different business
# from "Mwalimu National Sacco". Doing it once at the door is the only version
# that protects the dataset.
#
# ALL-CAPS AND all-lower BECOME PROPER CASE. Mixed case is LEFT ALONE, because
# somebody who typed "PCEA Kayole" or "e-Mobility Ltd" meant it, and
# title-casing that would be a correction nobody asked for.
# Acronyms that look wrong in Proper Case. "Ltd" is deliberately NOT here -
# Kenyan usage is "Ltd", not "LTD", and forcing the shout would be a change
# nobody asked for.
_KEEP_UPPER = {"plc", "dt", "hq", "ke", "kcb", "nssf", "kra", "usiu", "cbd",
               "ict", "ngo", "pcea", "ack", "kag", "sme", "usa", "uk", "eu",
               # "Sacco" not "SACCO" - the register itself writes it that
               # way, and the source document is the better authority than my
               # guess about acronyms.
               "wdt", "fosa", "bosa", "kebs", "kemri", "helb", "cic",
               "epza", "gdc", "nrs", "amref", "icea", "kasneb", "p.o", "po",
               "ceo", "cfo", "coo", "md", "gm", "hr", "it", "mp", "dt-sacco"}
_LOWER_WORDS = {"and", "of", "the", "for", "in", "on", "at", "to", "a"}


def _cap(word: str) -> str:
    """Capitalise a single word, preserving its internal punctuation.

    Splits on the separators that appear inside real names - hyphens,
    apostrophes and dots - so "trans-nzoia" becomes "Trans-Nzoia" and "p.o"
    becomes "P.O" rather than losing the mark entirely, which is what happened
    when the address separator was treated as a word boundary.
    """
    out = word.lower()
    for sep in ("-", "'", "\u2019", "."):
        parts = []
        for p in out.split(sep):
            if not p:
                parts.append(p)
            elif p.strip(".,").lower() in _KEEP_UPPER:
                # A hyphenated word can contain an acronym: "wdt-sacco" is
                # "WDT-Sacco", not "Wdt-Sacco".
                parts.append(p.upper())
            else:
                parts.append(p[:1].upper() + p[1:])
        out = sep.join(parts)
    return out


def _proper(text: str) -> str:
    out = []
    for i, w in enumerate(text.split(" ")):
        if not w:
            continue
        low = w.lower().strip(".,")
        if not any(ch.isalpha() for ch in w):
            out.append(w)                    # "-", "&", numbers: leave alone
        elif low in _KEEP_UPPER:
            out.append(w.upper())
        elif i and low in _LOWER_WORDS:
            out.append(low)
        else:
            out.append(_cap(w))
    return " ".join(out)


def normalise_value(key: str, value):
    """House style for one field. Applied on every write."""
    if not isinstance(value, str):
        return value
    v = " ".join(value.split())          # collapses doubles AND trims both ends
    if not v:
        return v
    if key in ("contact_email", "website"):
        return v.lower()
    if key == "contact_phone":
        # Keep the digits and the punctuation people actually use.
        return "".join(ch for ch in v if ch.isdigit() or ch in "+-() ").strip()
    if key in ("additional_information", "notes", "business_activity",
               "value_chain"):
        return v                          # prose: cleaned of spacing, not recased
    if v.isupper() or v.islower():
        return _proper(v)
    return v


# ── EDITING, AND WHAT PROTECTS A VALIDATED RECORD ───────────────────────────
# RULING (2026-08-11): "one will only be able to edit items under validation.
# The edit and delete on the validated, let them be restricted with a delete
# password - for now set it as Pendo, but I will control that from admin."
#
# A VALIDATED RECORD IS THE USABLE SET. Somebody staked their name on it, and
# people are being told to prefer it - so changing one should take a deliberate
# act, not a stray click on a page somebody was browsing.
#
# UNDER VALIDATION, editing is open. That is the point of the working set: it
# exists to be filled in, and putting a password in front of backfilling would
# guarantee the backfilling never happens.
#
# THE PASSWORD IS CONFIG, not code. Defaulting to "Pendo" as instructed, and
# admin can change it without a release. It is a SPEED BUMP, not security: it
# stops an accident, and it is not pretending to stop anybody determined.
DEFAULT_PROTECTED_PASSWORD = "Pendo"

EDITABLE_FIELDS = (
    "name", "sector", "town", "physical_address", "contact_name",
    "contact_phone", "contact_email", "notes", "estimated_value",
    "branches", "established", "segment", "existing_banker", "ownership",
    "website", "value_chain", "business_activity", "additional_information",
)


def protected_password() -> str:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("warehouse_protected_password")
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass
    return DEFAULT_PROTECTED_PASSWORD


def update_prospect(prospect_id: str, changes: dict, *, by_name: str = "",
                    password: str = "") -> dict:
    """Edit a prospect. A VALIDATED one needs the password.

    Editing a validated record does NOT silently un-validate it - completeness()
    already flags it stale, which tells the reader the truth (this changed after
    it was checked) without throwing away the fact that somebody once checked
    it. Quietly dropping the badge would lose that history.
    """
    pid = str(prospect_id or "").strip()
    with _lock:
        data = _read()
        rec = data.get(pid)
        if not rec:
            raise ValueError("That prospect no longer exists.")
        if rec.get("validated") and password != protected_password():
            raise PermissionError(
                "This is a validated record. Editing it needs the warehouse "
                "password - somebody vouched for these details.")

        applied = {}
        for k, v in (changes or {}).items():
            if k not in EDITABLE_FIELDS:
                continue
            v = normalise_value(k, v)
            rec[k] = v
            applied[k] = v
        if not applied:
            raise ValueError("Nothing to change.")
        if "name" in applied:
            rec["canonical_key"] = canonical_key(str(applied["name"]))
        rec["last_edited_at"] = datetime.now().isoformat(timespec="seconds")
        rec["last_edited_by"] = str(by_name or "")
        data[pid] = rec
        _write(data)
    return rec


def validate_prospect(prospect_id: str, by_code: str, by_name: str) -> dict:
    """Promote a COMPLETE entry to a validated record.

    Validation is a HUMAN ACT, not a consequence of the score. 100% means every
    field has something in it; validation means somebody looked and believed it.
    A record can be complete and wrong, and the whole point of a usable set is
    that somebody staked their name on it.
    """
    pid = str(prospect_id or "").strip()
    with _lock:
        data = _read()
        rec = data.get(pid)
        if not rec:
            raise ValueError("That prospect no longer exists.")
        c = completeness(rec)
        if not c.get("complete"):
            missing = ", ".join(m["label"] for m in c.get("missing", [])[:4])
            raise ValueError(
                "Not complete yet - %d%%. Still needed: %s."
                % (c.get("score", 0), missing or "unknown"))
        rec["validated"] = True
        rec["validated_by"] = str(by_name or by_code or "")
        rec["validated_at"] = datetime.now().isoformat(timespec="seconds")
        data[pid] = rec
        _write(data)
    return completeness(rec)


def completeness_summary() -> dict:
    """How complete is the warehouse as a whole, and which field is holding it
    back - the question that decides what to backfill next."""
    recs = all_prospects()
    fields = completeness_fields()
    missing_counts = {f["key"]: 0 for f in fields}
    scores, complete, validated = [], 0, 0
    for r in recs:
        c = completeness(r)
        scores.append(c.get("score", 0))
        if c.get("complete"):
            complete += 1
        if c.get("validated"):
            validated += 1
        for m in c.get("missing", []):
            missing_counts[m["key"]] = missing_counts.get(m["key"], 0) + 1
    labels = {f["key"]: f.get("label") or f["key"] for f in fields}
    return {
        "total": len(recs),
        "average_score": round(sum(scores) / len(scores)) if scores else 0,
        "complete": complete,
        "validated": validated,
        "usable": validated,
        "worst_gaps": sorted(
            [{"key": k, "label": labels.get(k, k), "missing": n}
             for k, n in missing_counts.items() if n],
            key=lambda x: -x["missing"])[:5],
    }


# ── THE INFORMATION CARD ────────────────────────────────────────────────────
# RULING (2026-08-11): "on each we have an information card - all available
# public information concerning the company including financials, associations
# etc, arranged in recency with key information and links to detailed
# information."
#
# An enrichment item is a FACT WITH A SOURCE AND A DATE. Never a copied
# article: we store the headline, the date, where it came from and a LINK.
# Storing article bodies would be republishing somebody else's work, and a
# stale copy is worse than a link that stays current.
#
# ORDERED BY RECENCY because that is how this is read - "what has happened to
# this company lately" - and an undated item sorts last rather than first,
# since something with no date is the least trustworthy thing on the card.
#
# HOW IT GETS FILLED, honestly: not by scraping. Either
#   - a licensed provider's API (the same vendors selling BRS records also sell
#     financials and group structure), pushed in through add_enrichment, or
#   - an RM who finds something and records it, which is worth having on its
#     own - a note that a prospect just won a county tender is exactly the kind
#     of thing that dies in one person's inbox.
ENRICHMENT_KINDS = ("financial", "news", "association", "filing", "contact",
                    "relationship", "note")


def add_enrichment(prospect_id: str, *, kind: str, title: str,
                   source: str, url: str = "", occurred_on: str = "",
                   detail: str = "", added_by: str = "") -> dict:
    """Attach one fact to a prospect's information card.

    `title` should be a headline or a figure, not a paragraph - the card is a
    scan-and-click surface, and anything longer belongs behind the link.
    """
    pid = str(prospect_id or "").strip()
    k = str(kind or "note").strip().lower()
    if k not in ENRICHMENT_KINDS:
        k = "note"
    t = str(title or "").strip()
    if not t:
        raise ValueError("An entry needs a title.")
    if not str(source or "").strip():
        # Provenance is the whole point: an unsourced claim on a prospect card
        # is a rumour that looks like research.
        raise ValueError("Say where this came from.")

    item = {
        "id": uuid.uuid4().hex[:8],
        "kind": k,
        "title": t[:200],
        "detail": str(detail or "")[:500],
        "source": str(source).strip()[:120],
        "url": str(url or "").strip()[:500],
        "occurred_on": str(occurred_on or "")[:10],
        "added_by": str(added_by or ""),
        "added_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _lock:
        data = _read()
        rec = data.get(pid)
        if not rec:
            raise ValueError("That prospect no longer exists.")
        rec.setdefault("enrichment", []).append(item)
        data[pid] = rec
        _write(data)
    return item


def information_card(prospect_id: str) -> dict:
    """Everything known about a prospect, newest first.

    Undated items sort LAST, not first: something with no date is the least
    trustworthy entry on the card, and putting it at the top would give it the
    prominence of breaking news.
    """
    rec = get(prospect_id)
    if not rec:
        return {}
    items = list(rec.get("enrichment") or [])
    items.sort(key=lambda i: (i.get("occurred_on") or "0000-00-00",
                              i.get("added_at") or ""), reverse=True)
    by_kind = {}
    for i in items:
        by_kind.setdefault(i["kind"], []).append(i)
    return {
        "prospect_id": rec.get("id"),
        "name": rec.get("name"),
        "items": items,
        "by_kind": by_kind,
        "counts": {k: len(v) for k, v in by_kind.items()},
        "total": len(items),
    }


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
