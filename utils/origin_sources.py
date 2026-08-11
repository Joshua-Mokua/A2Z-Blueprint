"""
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
    if k == "lead_gen":
        from utils.origin_channels import listing as _listing
        return [{"id": r["id"], "label": r["name"],
                 "sub": " · ".join(x for x in (r.get("category") or "",
                                               r.get("owner") or "") if x)}
                for r in _listing("lead_gen", active_only) if r.get("id")]
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
    return {"events": "event_id", "partnership": "mou_id",
            "lead_gen": "channel_id"}.get(str(origin_key or "").strip(), "")


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
