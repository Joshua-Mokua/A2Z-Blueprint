"""
utils/deal_origin — where a deal came from, and who deserves credit for it.

VISION (2026-08-11): "The first layer of this is the Deal Origin. I have
identified seven origins - Self/Direct, the Referral engine, the Warehouse,
Events, Partnerships, Lead Generators, Contact Centre. These seven are my base
but in future I should be able to add more."

SO IT IS CONFIG, NOT AN ENUM. The pipeline leaderboard and analytics were built
around a hard-coded PAIR - referred versus direct - which works for two and
breaks at seven. Adding an eighth origin must be an admin edit, not a release,
the same way stages became buckets.

CREDITABLE vs NOT (ruling 2026-08-11). Some origins bring a second party who
deserves credit; some are simply a tag describing how the deal arrived:

    self          no second party
    referral      the referrer          credited
    warehouse     the lister            credited
    lead_gen      the generator         credited
    contact_centre the agent            credited
    events        a tag - nobody to credit beyond the owner
    partnership   the partner ORGANISATION, not a person

The distinction matters because credit is what moves someone's index. An origin
marked creditable with no party recorded is a data problem worth surfacing, not
something to silently score as zero.

ONE ORIGIN PER DEAL (ruling 2026-08-11: "I would prefer a single origin but
branch as it progresses"). The origin records how the deal ENTERED. What happens
afterwards - a re-referral to another department, a hand-off - belongs in the
referral_chain, which already exists and already preserves every hop. Letting a
deal carry several origins would make "how many deals came from the warehouse"
unanswerable without deciding what fraction to attribute, which is exactly the
double-counting the ranking rules avoid.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Seeded defaults. Config wins - see origins(). `credits_party` decides whether
# a second person's index moves; `party_label` is what the UI should ask for.
DEFAULT_ORIGINS = [
    {"key": "self", "label": "Self / Direct", "credits_party": False,
     "party_label": "", "active": True,
     "note": "Created directly by the officer who will pursue it."},
    {"key": "referral", "label": "Referral", "credits_party": True,
     "party_label": "Referrer", "active": True,
     "note": "Sent to a named person; credited on acceptance."},
    {"key": "warehouse", "label": "Deals Warehouse", "credits_party": True,
     "party_label": "Listed by", "active": True,
     "note": "Claimed from the shared shelf; the claim IS the acceptance."},
    {"key": "events", "label": "Events", "credits_party": False,
     "party_label": "", "active": True,
     "note": "Gathered at an activation, forum or roadshow."},
    {"key": "partnership", "label": "Partnerships", "credits_party": False,
     "party_label": "Partner", "active": True,
     "note": "Introduced under a partnership or MOU. The party is an "
             "organisation, not a person, so nobody's index moves."},
    {"key": "lead_gen", "label": "Lead Generators", "credits_party": True,
     "party_label": "Generator", "active": True,
     "note": "Sourced by a lead generator who is credited."},
    {"key": "contact_centre", "label": "Contact Centre", "credits_party": True,
     "party_label": "Agent", "active": True,
     "note": "Raised by an agent and handed to an officer - a referral in "
             "everything but name."},
]

DEFAULT_ORIGIN = "self"


def origins(include_inactive: bool = False) -> list:
    """The configured origins. Config first, defaults second."""
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("deal_origins")
        if isinstance(v, list) and v:
            out = []
            for o in v:
                if not isinstance(o, dict) or not str(o.get("key") or "").strip():
                    continue
                out.append({
                    "key": str(o["key"]).strip(),
                    "label": str(o.get("label") or o["key"]),
                    "credits_party": bool(o.get("credits_party")),
                    "party_label": str(o.get("party_label") or ""),
                    "active": bool(o.get("active", True)),
                    "note": str(o.get("note") or ""),
                })
            if out:
                return [o for o in out if include_inactive or o["active"]]
    except Exception as exc:
        logger.debug("deal origins: falling back to defaults (%s)", exc)
    return [dict(o) for o in DEFAULT_ORIGINS
            if include_inactive or o.get("active", True)]


def origin_map() -> dict:
    return {o["key"]: o for o in origins(include_inactive=True)}


def label_for(key: str) -> str:
    """Never blank: an unrecognised origin shows its own key rather than an
    empty cell, so a bad value is visible instead of looking like no data."""
    k = str(key or "").strip()
    if not k:
        return "Unclassified"
    return (origin_map().get(k) or {}).get("label") or k


def credits_party(key: str) -> bool:
    return bool((origin_map().get(str(key or "").strip()) or {}).get("credits_party"))


def is_known(key: str) -> bool:
    return str(key or "").strip() in origin_map()


def origin_of(deal: dict) -> str:
    """The deal's origin, inferred where it has not been set.

    Inference exists for deals created before the origin field did. It is
    deliberately conservative - it reads what the deal already records rather
    than guessing - and anything it cannot place returns DEFAULT_ORIGIN so the
    figure is never blank in a ranking.
    """
    raw = str(deal.get("origin") or "").strip()
    if raw:
        return raw
    if deal.get("warehouse_prospect_id"):
        return "warehouse"
    if deal.get("is_referral") or (deal.get("referral_chain") or []):
        return "referral"
    return DEFAULT_ORIGIN


def party_of(deal: dict) -> tuple:
    """(code, name) of the party credited for this deal, or ("", "").

    Only returns someone when the ORIGIN says there is someone to credit -
    otherwise a deal carrying a stale referrer field would quietly move an index
    it should not.
    """
    o = origin_of(deal)
    if not credits_party(o):
        return "", ""
    code = str(deal.get("origin_party_code") or "").strip()
    name = str(deal.get("origin_party_name") or "").strip()
    if code or name:
        return code, name
    # Fall back to the referral chain for deals that predate the field.
    chain = deal.get("referral_chain") or []
    if chain and isinstance(chain[-1], dict):
        hop = chain[-1]
        return (str(hop.get("referred_by_code") or "").strip(),
                str(hop.get("referred_by") or hop.get("referred_by_name") or "").strip())
    return (str(deal.get("referred_by_code") or "").strip(),
            str(deal.get("referred_by") or "").strip())


def summarise(deals: list) -> list:
    """Count, value and won per origin - for the analytics split.

    Every CONFIGURED origin appears, including those with nothing in them: an
    origin producing no deals is a finding, and hiding it is how a channel
    quietly dies without anyone noticing.
    """
    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    buckets = {o["key"]: {"origin": o["key"], "label": o["label"],
                          "credits_party": o["credits_party"],
                          "count": 0, "value": 0.0, "won": 0}
               for o in origins()}
    unknown = {}
    for d in deals or []:
        k = origin_of(d)
        b = buckets.get(k)
        if b is None:
            b = unknown.setdefault(k, {"origin": k, "label": label_for(k),
                                       "credits_party": False,
                                       "count": 0, "value": 0.0, "won": 0})
        b["count"] += 1
        b["value"] += _val(d)
        if str(d.get("stage") or "") == "Closed Won":
            b["won"] += 1
    out = list(buckets.values()) + list(unknown.values())
    for b in out:
        b["value"] = round(b["value"], 2)
    return out
