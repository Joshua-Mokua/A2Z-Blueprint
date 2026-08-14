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
                # NAME THE PERSON. The record carries recorded_by_name and the
                # journey was reading only the staff code, so a committee
                # decision showed as "KE1218" or blank. The journey exists to
                # answer "who decided this" - a code answers it for nobody
                # reading the file six weeks later.
                "by_name": rec.get("recorded_by_name") or None,
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

    # 6) SLA commitments — when a stage's SLA is at risk/breached, the deal owner
    #    records a reason + a committed date. Surface each in the journey. If the
    #    committed date has passed the commitment is UNFULFILLED — an SLA breach —
    #    tagged `sla_breached` so the UI renders it red; otherwise `sla_commitment`.
    commitments = deal.get("sla_commitments")
    if isinstance(commitments, dict):
        from datetime import date as _date
        for step, c in commitments.items():
            if not isinstance(c, dict):
                continue
            committed = str(c.get("committed_date") or "")
            violated = False
            try:
                violated = bool(committed) and _date.fromisoformat(committed) < _date.today()
            except Exception:
                violated = False
            step_label = str(step).replace("_", " ").strip() or "current stage"
            reason = str(c.get("reason", "") or "").strip()
            note = (f"SLA {'breached' if violated else 'at risk'} at stage '{step_label}'"
                    + (f" — committed by {committed}" if committed else ""))
            if reason:
                note += f" · reason: {reason}"
            events.append({
                "event": "sla_breached" if violated else "sla_commitment",
                "by": str(c.get("recorded_by", "") or ""),
                "by_name": c.get("recorded_by_name") or None,
                "at": _iso(c.get("recorded_at")),
                "note": note,
            })

    # ── TOUCH POINTS THAT WERE NOT BEING RECORDED (pilot, 2026-08-12) ────────
    # "We had defined that any touch point of the case has to be recorded -
    # could it be that the journey is not capturing everything?"
    #
    # It was not. The journey carried creation, stage changes, committee
    # outcomes, appeals, affordability and SLA - but three decisions that
    # CHANGE WHO CONTROLS THE DEAL left no trace at all:
    #
    #     MANAGER VALIDATION - the gate that lets a deal move at all
    #     REFERRAL           - the deal changing hands
    #     CANCELLATION       - a request to stop, and the answer to it
    #
    # A case journey missing those cannot answer "who let this through", which
    # is the first question anybody asks of a credit file after the fact.

    # ── EACH VOTE IS A TOUCH POINT (pilot, 2026-08-14) ──────────────────────
    # "The submission did confirm but it did not record to the case journey ...
    # each vote needs to write to the case journey."
    #
    # The journey read committee_records, which is written only when quorum is
    # reached. So every individual vote - the act of a named person deciding -
    # was invisible until the committee finished, and if it never finished,
    # invisible for ever. A case journey that cannot show who has spoken is not
    # a record of the committee's work.
    #
    # The final decision still appears as its own event, so the journey reads:
    # each member voting, then the committee deciding.
    votes_by_cttee = deal.get("committee_votes")
    if isinstance(votes_by_cttee, dict):
        for _code, _cast in votes_by_cttee.items():
            if not isinstance(_cast, dict):
                continue
            for _who, _v in _cast.items():
                if not isinstance(_v, dict):
                    continue
                _vote = str(_v.get("vote", "") or "").upper()
                _said = {"YES": "recommended", "NO": "did not recommend",
                         "ABSTAIN": "abstained", "RECUSED": "recused themselves"
                         }.get(_vote, _vote.lower())
                _note = "%s %s" % (_v.get("name") or _who, _said)
                if _v.get("role"):
                    _note += " (%s)" % _v.get("role")
                if _v.get("comment"):
                    _note += " — %s" % _v.get("comment")
                events.append({
                    "event": "committee_vote",
                    "by": str(_v.get("staff_code", "") or ""),
                    "by_name": _v.get("name") or None,
                    "at": _iso(_v.get("at")),
                    "note": "%s · %s" % (_code, _note),
                })

    # ── A STAGE THAT MOVED ITSELF SAYS SO ───────────────────────────────────
    # "I do hope every autosubmit records in the case journey as well."
    #
    # It must. A stage that changes with nobody at a keyboard is the one entry
    # a reader is most likely to question later - "who moved this, and why is
    # there no name against it?" - so it names the committee whose decision
    # moved it rather than leaving a silent jump between two stages.
    _auto = str(deal.get("auto_advanced_by", "") or "")
    if _auto:
        _why = _auto.split(":", 1)[1] if ":" in _auto else _auto
        events.append({
            "event": "auto_advanced",
            "by": "", "by_name": None,
            "at": _iso(deal.get("updated_at")),
            "note": ("advanced automatically to %s — %s had recommended it, so "
                     "the case did not wait to be submitted"
                     % (deal.get("stage") or "the next stage", _why)),
        })

    # ── A RETURN FOR REWORK, AND THE WORK COMING BACK ───────────────────────
    # The simulation caught this: every other touch point was recorded and a
    # rework was not. A case sent back to a branch left no trace of who
    # returned it or why - which is the first entry an auditor asks about,
    # because it is the point where a case stopped moving.
    #
    # EVERY return is shown, not just the last. A case returned three times is
    # a different conversation from one returned once, and rework_history keeps
    # them all.
    for _rw in (deal.get("rework_history") or []):
        if not isinstance(_rw, dict):
            continue
        _note = str(_rw.get("reason", "") or "").strip() or "returned for rework"
        _items = [str(x) for x in (_rw.get("items") or []) if str(x).strip()]
        if _items:
            _note += " — " + ", ".join(_items)
        events.append({
            "event": "returned_for_rework",
            "by": str(_rw.get("by", "") or ""),
            "by_name": _rw.get("by_name") or None,
            "at": _iso(_rw.get("at")),
            "note": _note,
        })

    # And the branch sending it back, which closes the loop: without it the
    # journey shows a case leaving and never returning.
    if deal.get("rework_completed_at"):
        events.append({
            "event": "rework_completed",
            "by": "", "by_name": deal.get("rework_completed_by") or None,
            "at": _iso(deal.get("rework_completed_at")),
            "note": ("reworked and sent back to credit"
                     + (" — %s" % deal.get("rework_note")
                        if deal.get("rework_note") else "")),
        })

    # Manager validation. The fields are already written by the validate
    # endpoint (Item 5) - nothing new is recorded, it was simply never read.
    if deal.get("manager_validated"):
        who = str(deal.get("validated_by_name", "") or "")
        role = str(deal.get("validated_by_role", "") or "")
        events.append({
            "event": "manager_validated",
            "by": str(deal.get("validated_by_code", "") or ""),
            "by_name": who or None,
            "at": _iso(deal.get("validated_at")),
            "note": ("Validated by %s%s" % (who or "a manager",
                                            " (%s)" % role if role else ""))
                    + " — the deal may now progress",
        })

    # Referral. Recorded whether or not it was accepted: a declined referral is
    # part of the history, and leaving it out would make a deal look as though
    # it had never moved.
    rstatus = str(deal.get("referral_status", "") or "").strip().lower()
    if rstatus:
        frm = str(deal.get("referred_by_name", "") or "")
        to = str(deal.get("referred_to_name", "") or "")
        events.append({
            "event": "referral_%s" % rstatus,
            "by": str(deal.get("referred_by", "") or ""),
            "by_name": frm or None,
            "at": _iso(deal.get("referred_at")),
            "note": ("Referred%s%s — %s"
                     % (" by %s" % frm if frm else "",
                        " to %s" % to if to else "", rstatus)),
        })

    # Cancellation, requested and answered as separate moments - the gap
    # between them is often the thing somebody is asking about.
    if deal.get("cancel_requested"):
        events.append({
            "event": "cancel_requested",
            "by": str(deal.get("cancel_requested_by", "") or ""),
            "by_name": deal.get("cancel_requested_by_name") or None,
            "at": _iso(deal.get("cancel_requested_at")),
            "note": "Cancellation requested"
                    + (" — %s" % deal.get("cancel_request_reason")
                       if deal.get("cancel_request_reason") else ""),
        })
    if deal.get("cancel_approved"):
        events.append({
            "event": "cancel_approved",
            "by": str(deal.get("cancel_approved_by", "") or ""),
            "by_name": deal.get("cancel_approved_by_name") or None,
            "at": _iso(deal.get("cancel_approved_at")),
            "note": "Cancellation approved",
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


def build_deal_journey(deal: Dict[str, Any],
                       activities: Optional[List[Dict[str, Any]]] = None
                       ) -> List[Dict[str, Any]]:
    """Case Journey for a pipeline deal that is NOT yet linked to a credit
    application (origination stages). Reuses the same deal->journey normalisation
    as the merged application journey, so the two surfaces render identically.
    Oldest-first; never raises.
    """
    try:
        evs = _events_from_deal(deal, activities or [])
        evs.sort(key=lambda e: _parse_ts(e.get("at")))
        return evs
    except Exception:
        return []
