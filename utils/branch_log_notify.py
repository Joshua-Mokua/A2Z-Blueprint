"""
A2Z Daily Log — notification hooks (additive, new module).

Routes daily-log events through the EXISTING notify_staff path rather than
growing a second channel: utils.notifications.notify_staff already resolves the
roster email, honours the email configuration, degrades to in-app when there is
no address, and never raises. This module only decides WHAT to say and WHO to
say it to.

WHAT GETS SENT IMMEDIATELY (the person must act):
    your log was returned          -> the staff member
    your branch day was returned   -> the branch manager who submitted it

WHAT BELONGS IN A DIGEST (a standing state, not an event):
    you have not filed             -> the staff member
    your team has N outstanding    -> the branch manager
    branch days awaiting you       -> the Head of Branches

Nobody should receive an email per row. build_digest_lines() produces the
content for the daily digest run; it does not send anything itself, so the
existing send_notification_digests.py schedule stays the single sender.

EVERY CALL IS BEST-EFFORT AND NEVER FAILS THE ACTION. A validation must not
fail because a mail server is down. But failures are LOGGED, not swallowed
silently — the pattern that hid a two-year-old bug elsewhere in this codebase.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_STYLE = (
    "font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#464646;"
    "line-height:1.5"
)
_BRAND = "#0082BB"


def _shell(title: str, body: str, action: str = "") -> str:
    """One house style for every daily-log email."""
    act = (f'<p style="margin:16px 0 0"><a href="#" '
           f'style="color:{_BRAND};text-decoration:none;font-weight:600">{action}</a></p>'
           if action else "")
    return (
        f'<div style="{_STYLE}">'
        f'<h2 style="color:{_BRAND};font-size:16px;margin:0 0 12px">{title}</h2>'
        f'{body}{act}'
        f'<p style="margin:20px 0 0;font-size:11px;color:#979797">'
        f'A2Z MIS 360 · Daily Log. This message was sent automatically.</p>'
        f'</div>'
    )


def _send(staff_code: str, subject: str, html: str) -> bool:
    if not str(staff_code or "").strip():
        return False
    try:
        from utils.notifications import notify_staff
        return bool(notify_staff(str(staff_code).strip(), subject, html))
    except Exception as exc:
        # Logged, not swallowed: a notification that silently never sends is
        # indistinguishable from one nobody reads.
        logger.warning("daily-log notify failed for %s: %s", staff_code, exc)
        return False


def notify_log_returned(staff_code: str, log_date: str, manager_name: str,
                        note: str) -> bool:
    """A staff member's daily log has been sent back for amendment."""
    body = (
        f"<p>Your daily log for <strong>{log_date}</strong> has been returned by "
        f"<strong>{manager_name or 'your manager'}</strong>.</p>"
        f"<p style='background:#FBEAF0;padding:10px;border-radius:6px;color:#993556'>"
        f"{note or 'No reason was recorded.'}</p>"
        f"<p>Open the Daily Log, correct the entry and submit it again. "
        f"Logs lock three working days after submission.</p>"
    )
    return _send(staff_code, f"Daily log returned — {log_date}",
                 _shell("Your daily log needs amending", body, "Open the Daily Log"))


def notify_branch_day_returned(bm_staff_code: str, branch: str, day: str,
                               by_name: str, note: str) -> bool:
    """A branch day has been sent back to the branch manager."""
    body = (
        f"<p>The <strong>{branch}</strong> branch day for <strong>{day}</strong> "
        f"has been returned by <strong>{by_name or 'the Head of Branches'}</strong>.</p>"
        f"<p style='background:#FBEAF0;padding:10px;border-radius:6px;color:#993556'>"
        f"{note}</p>"
        f"<p>Review the branch line and your team's entries, then submit the day again.</p>"
    )
    return _send(bm_staff_code, f"{branch} branch day returned — {day}",
                 _shell("Branch day returned", body, "Open Manager Queues"))


def build_digest_lines(day: str) -> dict:
    """Content for the daily digest run — computed, not sent.

    Returns {staff_code: [line, ...]} so the existing digest sender can batch
    one message per person instead of one per event.
    """
    out: dict = {}
    try:
        from utils.branch_log import BranchLogManager
        from utils.staff_code import canon
        from utils import workcal
    except Exception as exc:
        logger.warning("digest build failed to import: %s", exc)
        return out

    try:
        if not workcal.is_working_day(day):
            return out
    except Exception:
        pass

    try:
        blm = BranchLogManager()
        filed = {canon(l.get("staff_code")) for l in blm.get_history(days=5)
                 if str(l.get("log_date"))[:10] == str(day)[:10]}
    except Exception as exc:
        logger.warning("digest build could not read logs: %s", exc)
        return out

    try:
        from utils.api_pipeline_scope import get_staff_roster
        df = get_staff_roster()
        if df is None or len(df) == 0:
            return out
    except Exception as exc:
        logger.warning("digest build could not read the roster: %s", exc)
        return out

    try:
        from utils.branch_log_exceptions import exception_for
    except Exception:
        exception_for = lambda *_a, **_k: None   # noqa: E731

    for _, r in df.iterrows():
        code = str(r.get("Staff Code", "") or "").strip()
        if not code or canon(code) in filed:
            continue
        exc = exception_for(code, str(day)[:10]) or {}
        if exc.get("excuses_target"):
            continue                      # excused: nothing to chase
        out.setdefault(code, []).append(
            f"You have not submitted your daily log for {day}.")
    return out
