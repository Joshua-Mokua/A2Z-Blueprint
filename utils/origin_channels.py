"""
utils/origin_channels — one model over every channel the bank invests in.

RULING (2026-08-11): "since the process should almost be similar with
partnerships and lead generators, we can have them as one ... build with a
future in mind, we should not only limit to features existing."

WHY ONE MODEL RATHER THAN THREE PAGES. Events, Partnerships and Lead Generators
ask the SAME question - what did we spend, what did it produce, was it worth it.
Three implementations would be three places to change when the fourth channel
arrives, and they would drift: one would count leads before closure, another
after, and nobody would know which number they were reading.

So a CHANNEL is declared in config, exactly as origins are, and every channel
normalises to one record shape. Adding "Trade Shows" or "Diaspora Agents" later
is a config entry plus a store, not a new page.

    channel      the origin key it feeds        store
    events       events                         data/sponsored_events.json
    partnership  partnership                    data/partnerships.json
    lead_gen     lead_gen                       data/lead_generators.json

WHAT ALREADY EXISTED, checked before building (standing instruction): the events
and partnership stores are real and populated - 12 and 50 records. utils/
partner_leads_commissions.py already holds a LeadTrackingEngine and a
CommissionEngine, 668 lines, Streamlit-only. This module does NOT reimplement
them; lead_gen records here describe the GENERATOR (who they are, what they
cost), and the existing engine remains the place lead lifecycle lives.

OWNERSHIP IS A UNIT *OR* A BRANCH (ruling 2026-08-11: "could belong to a unit,
although at times branches can hold events like customer dinners so we need to
be specific"). Both are stored explicitly rather than inferred from a single
free-text field, because "Nakuru" could be either and a report that cannot tell
them apart cannot answer "what did Retail Banking spend" or "what did this
branch run".

NOT EVERY CHANNEL HAS A BUDGET, and pretending otherwise would invent numbers.
Partnerships carry expected_volume_kes_m but no spend, so `supports_roi` is False
for them: the analytics show volume against expectation rather than a return
percentage that would be division by a budget nobody set.
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

_lock = threading.Lock()

CLOSED_WON = "Closed Won"

# Channel declarations. Config wins - see channels(). `supports_roi` records
# whether a return figure is meaningful, so a channel with no budget is never
# shown a percentage computed from zero.
DEFAULT_CHANNELS = [
    {"key": "events", "label": "Events", "origin": "events",
     "store": "sponsored_events.json", "supports_roi": True,
     "party_label": "Partner",
     "note": "Sponsorships, roadshows, activations - anything with a budget and "
             "a date."},
    {"key": "partnership", "label": "Partnerships", "origin": "partnership",
     "store": "partnerships.json", "supports_roi": False,
     "party_label": "Partner",
     "note": "MOUs and agreements. Measured on volume against expectation, not "
             "on spend."},
    {"key": "lead_gen", "label": "Lead Generators", "origin": "lead_gen",
     "store": "lead_generators.json", "supports_roi": True,
     "party_label": "Generator",
     "note": "Individuals or firms sourcing leads, usually on commission."},
]


def channels(include_inactive: bool = False) -> list:
    try:
        from utils.core import get_pipeline_settings
        v = (get_pipeline_settings() or {}).get("origin_channels")
        if isinstance(v, list) and v:
            out = [c for c in v if isinstance(c, dict) and c.get("key")]
            if out:
                return [c for c in out
                        if include_inactive or c.get("active", True)]
    except Exception as exc:
        logger.debug("origin channels: using defaults (%s)", exc)
    return [dict(c) for c in DEFAULT_CHANNELS]


def channel(key: str) -> Optional[dict]:
    k = str(key or "").strip()
    return next((c for c in channels(True) if c["key"] == k), None)


def _path(key: str) -> str:
    c = channel(key) or {}
    return os.path.join("data", str(c.get("store") or ""))


def _read(key: str) -> list:
    p = _path(key)
    if not p or not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as exc:
        # A store we cannot read means no channels to show, which is visible.
        # It must not raise into a page render or a deal-capture request.
        logger.warning("channel store %s unreadable: %s", p, exc)
        return []
    if isinstance(data, dict):
        data = list(data.values())
    return [d for d in data if isinstance(d, dict)]


def _write(key: str, records: list) -> None:
    p = _path(key)
    if not p:
        raise ValueError("Unknown channel: %r" % key)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p) or ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(records, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def normalise(rec: dict, key: str) -> dict:
    """One shape for every channel, whatever its store looks like.

    Missing values stay NULL rather than becoming zero. A target nobody set and
    a target of zero mean different things, and rendering both as 0 would let a
    channel look like it missed a goal it never had.
    """
    def _num(*names):
        for n in names:
            v = rec.get(n)
            if v not in (None, ""):
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
        return None

    owner_type = str(rec.get("owner_type") or "").strip()
    owner = str(rec.get("owner") or "").strip()
    if not owner_type:
        # Records that predate owner_type: department is a unit, branch is a
        # branch. Inferred, not guessed - both fields already exist.
        if rec.get("department"):
            owner_type, owner = "unit", str(rec["department"])
        elif rec.get("branch"):
            owner_type, owner = "branch", str(rec["branch"])
        elif rec.get("rm_code") or rec.get("rm_owner"):
            # Partnerships carry only an RM. Their unit is the RM's unit -
            # derived from the hierarchy rather than left blank, because an
            # unowned partnership cannot be scoped to anybody and would vanish
            # from every unit's view.
            try:
                from utils.org_validator import unit_for_role
                from utils.api_pipeline_scope import get_staff_roster
                code = str(rec.get("rm_code") or rec.get("rm_owner") or "")
                df = get_staff_roster()
                hit = df[df["Staff Code"].astype(str) == code]
                if len(hit):
                    u = unit_for_role(str(hit.iloc[0].get("Role") or ""))
                    if u:
                        owner_type, owner = "unit", u
            except Exception as exc:
                logger.debug("could not derive partnership owner: %s", exc)

    return {
        "id": str(rec.get("id") or ""),
        "channel": key,
        "name": str(rec.get("name") or rec.get("partner_name")
                    or rec.get("generator_name") or rec.get("id") or ""),
        "party": str(rec.get("partner") or rec.get("partner_name") or ""),
        "owner_type": owner_type,
        "owner": owner,
        "branch": str(rec.get("branch") or ""),
        "category": str(rec.get("category_name") or rec.get("event_category")
                        or rec.get("partner_type") or ""),
        "sector": str(rec.get("sector") or ""),
        "start_date": str(rec.get("start_date") or rec.get("signed_date") or ""),
        "end_date": str(rec.get("end_date") or ""),
        "status": str(rec.get("status") or ""),
        "budget_kes": _num("budget_kes"),
        "spent_kes": _num("spent_kes"),
        "target_leads": _num("target_leads"),
        "target_accounts": _num("target_accounts"),
        "target_value_kes": _num("target_value_kes", "expected_volume_kes")
                            or ((_num("expected_volume_kes_m") or 0) * 1_000_000
                                if _num("expected_volume_kes_m") else None),
        "owner_code": str(rec.get("rm_owner") or rec.get("rm_code") or ""),
        "created_by": str(rec.get("created_by") or ""),
    }


def listing(key: str, active_only: bool = False) -> list:
    out = [normalise(r, key) for r in _read(key)]
    if active_only:
        out = [r for r in out if r["status"].lower() in
               ("active", "planning", "planned", "")]
    return sorted(out, key=lambda r: r["start_date"], reverse=True)


def get(key: str, rec_id: str) -> Optional[dict]:
    rid = str(rec_id or "").strip()
    return next((normalise(r, key) for r in _read(key)
                 if str(r.get("id") or "") == rid), None)


def create(key: str, *, name: str, owner_type: str, owner: str,
           created_by: str, party: str = "", branch: str = "",
           category: str = "", start_date: str = "", end_date: str = "",
           budget_kes: float = 0, target_leads: float = 0,
           target_accounts: float = 0, target_value_kes: float = 0,
           notes: str = "") -> dict:
    """Add a channel record.

    OWNER IS REQUIRED and must say WHICH KIND. A unit-owned event and a
    branch-owned customer dinner answer different questions, and a single
    free-text owner field could not tell "Nakuru the branch" from "Nakuru the
    region" later.
    """
    c = channel(key)
    if not c:
        raise ValueError("Unknown channel: %r" % key)
    nm = str(name or "").strip()
    if not nm:
        raise ValueError("A %s needs a name." % c["label"].rstrip("s").lower())
    ot = str(owner_type or "").strip().lower()
    if ot not in ("unit", "branch"):
        raise ValueError("Say whether this belongs to a unit or a branch.")
    if not str(owner or "").strip():
        raise ValueError("Which %s owns it?" % ot)

    prefix = {"events": "EVT", "partnership": "PRT", "lead_gen": "LGN"}.get(key, "CHN")
    rec = {
        "id": prefix + uuid.uuid4().hex[:6].upper(),
        "name": nm,
        "partner": str(party or "").strip(),
        "owner_type": ot,
        "owner": str(owner).strip(),
        # department/branch kept in sync so the existing Streamlit pages and
        # the generated records keep reading the same fields.
        "department": str(owner).strip() if ot == "unit" else "",
        "branch": str(branch or (owner if ot == "branch" else "")).strip(),
        "category_name": str(category or "").strip(),
        "start_date": str(start_date or "").strip(),
        "end_date": str(end_date or "").strip(),
        "status": "Planning",
        "budget_kes": float(budget_kes or 0),
        "spent_kes": 0.0,
        "target_leads": float(target_leads or 0),
        "target_accounts": float(target_accounts or 0),
        "target_value_kes": float(target_value_kes or 0),
        "notes": str(notes or "").strip(),
        "created_by": str(created_by or "").strip(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _lock:
        records = _read(key)
        records.append(rec)
        _write(key, records)
    return normalise(rec, key)


def attribution(key: str, rec_id: str, deals: list) -> dict:
    """What the DEALS say this channel record produced.

    Accounts and value count only CLOSED WON deals (ruling 2026-08-11: "the
    actuals are quantifiable after the closure"). Return is reported only when
    the channel `supports_roi` AND something was actually spent - a percentage
    computed against a budget nobody set is a fabricated number.
    """
    c = channel(key) or {}
    rid = str(rec_id or "").strip()
    field = {"events": "event_id", "partnership": "mou_id"}.get(key, "channel_id")
    mine = [d for d in (deals or []) if str(d.get(field) or "").strip() == rid]
    won = [d for d in mine if str(d.get("stage") or "") == CLOSED_WON]

    def _val(d):
        try:
            return float(d.get("amount_kes") or d.get("deal_value") or 0)
        except (TypeError, ValueError):
            return 0.0

    rec = get(key, rid) or {}
    spent = rec.get("spent_kes") or rec.get("budget_kes") or 0
    won_value = round(sum(_val(d) for d in won), 2)
    roi = None
    if c.get("supports_roi") and spent:
        roi = round((won_value - spent) / spent * 100, 1)
    return {
        "id": rid, "channel": key,
        "leads": len(mine), "accounts": len(won), "value": won_value,
        "spent_kes": spent, "roi_pct": roi,
        "supports_roi": bool(c.get("supports_roi")),
        "target_leads": rec.get("target_leads"),
        "target_accounts": rec.get("target_accounts"),
        "target_value_kes": rec.get("target_value_kes"),
    }
