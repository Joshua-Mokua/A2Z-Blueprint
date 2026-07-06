"""utils/api_lms_journey.py — Case Journey merge (Phase C part 1).

The Case Journey is the through-line of a loan case treated as a
*document that travels across roles and accumulates history*. The
application record carries its own `history` (LMS-side events), but the
richer early story — deal creation, branch/department committee votes,
appeals, stage changes — lives on the linked **pipeline deal**, NOT on
the application.

This module fetches the linked deal (a `PipelineManager` deal, id form
`D####`, file `pipeline_deals.json`) and normalises its journey-bearing
fields into the same shape the `Timeline` component renders:

    {event, by, at, note, by_name?, by_role?}

then merges them chronologically with the application's own history.

IMPORTANT shape note (corrected 2026-07-06): the linked deal is a
`PipelineManager` deal. Those deals do **not** carry a `{stage,date,note}`
history array — that shape belongs to the unrelated `RIPipelineManager`.
The real journey material on a `PipelineManager` deal is:

  - `created_at`                → deal_created
  - `committee_records{code}`   → committee_<outcome> (branch/dept votes)
  - `appeals[]`                 → committee_appeal
  - stage-change *activities*   → deal_stage_change
    (a separate list in pipeline_activities.json, read via
     PipelineManager.get_activities(deal_id=...))

The merge is computed at read-time and attached to the response as a
non-persisted `journey` field (mirrors how the detail endpoint attaches
`sla`). The stored application record is never mutated here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional


# ── timestamp parsing ────────────────────────────────────────────────

def _parse_ts(value: Any) -> datetime:
    """Best-effort parse of the many timestamp forms in this codebase.

    Accepts ISO datetimes ('2026-07-04T11:49:03'), ISO dates
    ('2026-07-04'), and space-separated forms. Unparseable / missing
    values sort to the very start (datetime.min) so a real event with a
    good timestamp always renders after an undated one, deterministically.
    """
    if not value:
        return datetime.min
    s = str(value).strip()
    if not s:
        return datetime.min
    # Normalise a trailing 'Z' and a space-separated date/time.
    s = s.replace("Z", "").replace(" ", "T", 1)
    for fmt in (None, "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            if fmt is None:
                return datetime.fromisoformat(s)
            return datetime.strptime(s, fmt)
        except (ValueError, TypeError):
            continue
    return datetime.min


def _iso(value: Any) -> str:
    """Return a string timestamp suitable for the `at` field.

    Passes through a usable string as-is; falls back to '' when missing.
    """
    if not value:
        return ""
    return str(value)


# ── committee vote summarising ───────────────────────────────────────

def _summarise_votes(votes: List[Dict[str, Any]]) -> str:
    """Human-readable tally, e.g. '3 yes / 1 no' plus dissenting names."""
    if not votes:
        return ""
    tally: Dict[str, int] = {}
    names_by_vote: Dict[str, List[str]] = {}
    for v in votes:
        if not isinstance(v, dict):
            continue
        vote = str(v.get("vote", "")).upper()
        if not vote:
            continue
        tally[vote] = tally.get(vote, 0) + 1
        nm = str(v.get("name", "") or "").strip()
        if nm:
            names_by_vote.setdefault(vote, []).append(nm)
    order = ["YES", "NO", "ABSTAIN", "RECUSED"]
    parts = [f"{tally[k]} {k.lower()}" for k in order if k in tally]
    for k in tally:
        if k not in order:
            parts.append(f"{tally[k]} {k.lower()}")
    summary = " / ".join(parts)
    # Surface dissent (NO) names, which matter most to the next reader.
    dissent = names_by_vote.get("NO") or []
    if dissent:
        summary += f" · against: {', '.join(dissent)}"
    return summary


# ── deal → journey normalisation ─────────────────────────────────────

def _events_from_deal(deal: Dict[str, Any],
                      activities: Optional[List[Dict[str, Any]]] = None
                      ) -> List[Dict[str, Any]]:
    """Normalise a PipelineManager deal's journey fields to Timeline shape."""
    events: List[Dict[str, Any]] = []
    if not isinstance(deal, dict):
        return events

    deal_id = str(deal.get("id", "") or "")

    # 1) Deal creation — the start of the travelling document.
    created = deal.get("created_at") or deal.get("open_date")
    if created:
        owner = str(deal.get("staff_name", "") or deal.get("staff_code", "") or "")
        product = str(deal.get("product_type") or deal.get("product") or "").strip()
        client = str(deal.get("client_name", "") or "").strip()
        note_bits = [b for b in (client, product) if b]
        events.append({
            "event": "deal_created",
            "by": str(deal.get("staff_code", "") or ""),
            "by_name": owner or None,
            "at": _iso(created),
            "note": (" · ".join(note_bits) + (f" (deal {deal_id})" if deal_id else "")).strip(" ·"),
        })

    # 2) Committee decisions — the branch/department votes (dict by code).
    records = deal.get("committee_records")
    if isinstance(records, dict):
        for code, rec in records.items():
            if not isinstance(rec, dict):
                continue
            outcome = str(rec.get("outcome", "") or "").lower() or "recorded"
            votes = rec.get("votes") or []
            tally = _summarise_votes(votes if isinstance(votes, list) else [])
            note_bits = [str(code)]
            if tally:
                note_bits.append(tally)
            if rec.get("note"):
                note_bits.append(str(rec.get("note")))
            events.append({
                "event": f"committee_{outcome}",
                "by": str(rec.get("recorded_by", "") or ""),
                "at": _iso(rec.get("recorded_at")),
                "note": " · ".join(note_bits),
            })

    # 3) Appeals against a rejected committee gate.
    appeals = deal.get("appeals")
    if isinstance(appeals, list):
        for ap in appeals:
            if not isinstance(ap, dict):
                continue
            code = str(ap.get("code", "") or "")
            reason = str(ap.get("reason", "") or "")
            outcome = str(ap.get("outcome", "") or "").upper()
            note_bits = [b for b in (code, (f"outcome: {outcome}" if outcome else ""), reason) if b]
            events.append({
                "event": "committee_appeal",
                "by": str(ap.get("by", "") or ""),
                "at": _iso(ap.get("at")),
                "note": " · ".join(note_bits),
            })

    # 4) Stage-change activities (separate pipeline_activities.json list).
    if isinstance(activities, list):
        for a in activities:
            if not isinstance(a, dict):
                continue
            if str(a.get("activity_type", "")).lower() != "stage change":
                continue
            events.append({
                "event": "deal_stage_change",
                "by": str(a.get("staff_code", "") or ""),
                "by_name": str(a.get("staff_name", "") or "") or None,
                "at": _iso(a.get("recorded_at")),
                "note": str(a.get("note", "") or ""),
            })

    # 5) Affordability appraisal completed by the deal owner (RM). Surfaced so
    #    the journey shows the RM's appraisal alongside the analyst's concurrence
    #    (logged app-side as `affordability_concurred`).
    appr = deal.get("appraisal")
    if isinstance(appr, dict) and (appr.get("updated_at") or appr.get("sources")):
        _by = str(appr.get("updated_by", "") or "")
        _byname = None
        if _by and _by == str(deal.get("staff_code", "") or ""):
            _byname = str(deal.get("staff_name", "") or "") or None
        events.append({
            "event": "affordability_completed",
            "by": _by,
            "by_name": _byname,
            "at": _iso(appr.get("updated_at")),
            "note": "Affordability appraisal completed by deal owner",
        })

    return events


# ── public entry point ───────────────────────────────────────────────

def build_case_journey(app: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return the merged, chronologically-ordered Case Journey.

    Ascending by timestamp (oldest first); the frontend reverses for
    newest-first display. Never raises — any failure fetching or
    normalising the linked deal falls back to the application's own
    history so the endpoint stays resilient (mirrors the sla try/except).
    """
    own = list(app.get("history") or [])
    # Defensive copy; ensure each own-history entry has the core keys.
    merged: List[Dict[str, Any]] = []
    for e in own:
        if isinstance(e, dict):
            merged.append(dict(e))

    deal_id = str(app.get("pipeline_deal_id", "") or "").strip()
    if deal_id:
        try:
            from utils.core import PipelineManager
            pm = PipelineManager()
            deal = pm.get_deal(deal_id)
            if deal:
                try:
                    activities = pm.get_activities(deal_id=deal_id, limit=200)
                except Exception:
                    activities = []
                merged.extend(_events_from_deal(deal, activities))
        except Exception:
            # Fall back to app history alone — never fail the detail read.
            pass

    # Backfill milestone facts from the current app record for cases whose
    # events pre-date event-logging (Phase C part 2). Only synthesised when
    # the event isn't already present, so new logged cases never double up.
    # Nothing is fabricated: each entry reflects a fact already on the record.
    present = {str(e.get("event", "")) for e in merged}
    analyst = app.get("analyst") or {}
    if analyst.get("code") and "assigned_to_analyst" not in present:
        merged.append({
            "event": "assigned_to_analyst",
            "by": "",
            "at": _iso(app.get("assigned_at") or app.get("last_updated")),
            "note": f"Assigned to {analyst.get('name') or analyst.get('code')}",
        })
    decision = app.get("decision") or {}
    _verdict = str(decision.get("verdict", "") or "").lower()
    if _verdict:
        _status = {
            "approved": "approved", "decline": "declined", "declined": "declined",
            "return": "returned", "returned": "returned",
        }.get(_verdict, _verdict)
        if f"decision_{_status}" not in present:
            merged.append({
                "event": f"decision_{_status}",
                "by": str(decision.get("authority", "") or ""),
                "at": _iso(decision.get("date") or app.get("last_updated")),
                "note": str(decision.get("reason") or decision.get("comments") or ""),
            })

    merged.sort(key=lambda e: _parse_ts(e.get("at")))
    return merged
