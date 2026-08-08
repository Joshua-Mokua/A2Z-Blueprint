"""
A2Z Daily Log — lifecycle state machine (additive, new module).

Enforces the entry lifecycle (see DAILY_LOG_LIFECYCLE.md):

  draft --submit--> submitted ----------------\\
        \\--deadline miss--> auto_submitted -----> manager queue
                                                     |            |
                                             return (<=3d)    validate
                                                     v            v
                                                  returned     validated
                                                     |
                                              resubmit -> submitted
                                                     |
                                    (3d no action) -> locked --admin unlock--> returned

Rules implemented:
  * Deadline: a fixed clock time (default 09:00) on day D+1. Any un-submitted day-D log whose author
    started it (draft exists) or that is missing entirely for a working day is AUTO-SUBMITTED at the
    deadline. Auto-submit is PARTIAL: whatever was autosaved (draft hourly/metrics) is kept; the rest
    is blank. auto_submitted=True and a deficit is inherent in the (lower) index.
  * Return window: a manager may RETURN a submitted/auto_submitted log within 3 calendar days of its
    submit/auto-submit time. Returned logs are editable and re-enter 'submitted' on resubmit.
  * Lock: after 3 days with no validation or return action, a log LOCKS. Only an admin unlocks it.
  * Healing: handled by the read-time carried-forward engine (a corrected+validated day raises the
    running variance automatically) — nothing to do here.

All functions operate on a BranchLogManager-like object exposing `.logs` (list) and `._save()`.
They are safe to call repeatedly (idempotent) and never touch already-terminal records incorrectly.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from utils.branch_log_analytics import deadline_time

RETURN_WINDOW_DAYS = 3


# ── time helpers ──────────────────────────────────────────────────────────
def _parse_dt(s: str) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s))
    except Exception:
        return None


def _deadline_for(log_date_str: str) -> datetime:
    """The auto-submit cutoff for a given log date = (log_date + 1 day) at deadline_time."""
    d = date.fromisoformat(str(log_date_str))
    hh, mm = deadline_time().split(":")
    return datetime.combine(d + timedelta(days=1), datetime.min.time()).replace(
        hour=int(hh), minute=int(mm)
    )


# ── deadline sweep: auto-submit overdue drafts/unsubmitted days ───────────
def sweep_deadlines(blm, now: Optional[datetime] = None) -> list:
    """Auto-submit any day-log still in 'draft' whose deadline has passed.

    PARTIAL auto-submit: the draft's autosaved hourly/metrics are already on the record, so we
    simply flip status to 'auto_submitted', stamp submitted_at, mark auto_submitted=True, and
    leave the (deficit-bearing, partial) index as-is. Effort is preserved; the un-keyed remainder
    stays blank and the low index carries the deficit.

    Returns the list of records that were auto-submitted this sweep (may be empty).
    Idempotent: only 'draft' records past their deadline are affected.
    """
    now = now or datetime.now()
    changed = []
    for l in blm.logs:
        if l.get("status") != "draft":
            continue
        ld = str(l.get("log_date", ""))
        if not ld:
            continue
        try:
            due = _deadline_for(ld)
        except Exception:
            continue
        if now >= due:
            l["status"] = "auto_submitted"
            l["auto_submitted"] = True
            l["submitted_at"] = l.get("submitted_at") or now.isoformat()
            l["auto_submitted_at"] = now.isoformat()
            l["validated"] = False
            l["rejected"] = False
            changed.append(l)
    if changed:
        blm._save()
    return changed


# ── manager return (within the 3-day window) ─────────────────────────────
def return_log(blm, log_id: str, manager: str, note: str,
               now: Optional[datetime] = None) -> dict:
    """Manager returns a submitted/auto_submitted log for fill/resubmission.

    Allowed only within RETURN_WINDOW_DAYS of the log's submit/auto-submit time and only when the
    log is not already validated or locked. Sets status 'returned' (editable by the author).
    Raises ValueError with a clear reason when not allowed.
    """
    now = now or datetime.now()
    log = next((l for l in blm.logs if l.get("id") == log_id), None)
    if not log:
        raise ValueError(f"Log {log_id} not found")
    if log.get("status") not in ("submitted", "auto_submitted"):
        raise ValueError(f"Only submitted logs can be returned (status={log.get('status')})")
    if log.get("locked"):
        raise ValueError("Log is locked — only an admin can unlock it")
    stamped = _parse_dt(log.get("auto_submitted_at") or log.get("submitted_at"))
    if stamped and (now - stamped) > timedelta(days=RETURN_WINDOW_DAYS):
        raise ValueError(f"Return window ({RETURN_WINDOW_DAYS} days) has elapsed — admin unlock required")
    log["status"] = "returned"
    log["returned_at"] = now.isoformat()
    log["returned_by"] = str(manager)
    log["manager_note"] = str(note or "")
    log["validated"] = False
    log["rejected"] = False
    blm._save()
    return log


# ── lock sweep: lock logs whose return window elapsed with no action ──────
def sweep_locks(blm, now: Optional[datetime] = None) -> list:
    """Lock any submitted/auto_submitted log that has sat unvalidated/unreturned past the 3-day
    window. Locked logs can only be reopened by an admin. Returns the newly-locked records.

    Idempotent: already-locked/validated/returned records are skipped.
    """
    now = now or datetime.now()
    changed = []
    for l in blm.logs:
        if l.get("locked") or l.get("validated"):
            continue
        if l.get("status") not in ("submitted", "auto_submitted"):
            continue
        stamped = _parse_dt(l.get("auto_submitted_at") or l.get("submitted_at"))
        if stamped and (now - stamped) > timedelta(days=RETURN_WINDOW_DAYS):
            l["locked"] = True
            l["locked_at"] = now.isoformat()
            changed.append(l)
    if changed:
        blm._save()
    return changed


# ── admin unlock ──────────────────────────────────────────────────────────
def admin_unlock(blm, log_id: str, admin: str, now: Optional[datetime] = None) -> dict:
    """Admin reopens a locked log to 'returned' (editable by the author for refill/resubmit).

    Only admins should call this (enforced at the endpoint). Raises ValueError if not locked.
    """
    now = now or datetime.now()
    log = next((l for l in blm.logs if l.get("id") == log_id), None)
    if not log:
        raise ValueError(f"Log {log_id} not found")
    if not log.get("locked"):
        raise ValueError("Log is not locked")
    log["locked"] = False
    log["status"] = "returned"
    log["unlocked_at"] = now.isoformat()
    log["unlocked_by"] = str(admin)
    log["returned_at"] = now.isoformat()
    blm._save()
    return log


# ── convenience: run both sweeps (call on read of manager queue / grid) ───
def run_maintenance(blm, now: Optional[datetime] = None) -> dict:
    """Run the deadline + lock sweeps together. Safe to call on any read that should reflect the
    current lifecycle state (e.g. before serving the manager queue or the history grid).
    Returns a small summary of what changed."""
    now = now or datetime.now()
    auto = sweep_deadlines(blm, now)
    locked = sweep_locks(blm, now)
    return {
        "auto_submitted": [l.get("id") for l in auto],
        "locked": [l.get("id") for l in locked],
    }
