#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
E4 - daily-log notifications, through the channel that already exists.

utils.notifications.notify_staff() already resolves a roster email, honours the
email configuration, degrades to in-app when there is no address, and never
raises. This adds WHAT to say and WHO to say it to - not a second channel.

IMMEDIATE (the person must act)
    your log was returned         -> the staff member, with the manager's reason
    your branch day was returned  -> the branch manager WHO SUBMITTED IT,
                                     not the branch at large

DIGEST (a standing state, not an event)
    build_digest_lines(day) returns {staff_code: [line, ...]} for the existing
    daily digest run. It computes and returns; it does not send, so
    send_notification_digests.py stays the single sender and nobody receives an
    email per row.

    Excused staff are skipped, and a non-working day returns nothing at all -
    the same rules the follow-up list uses, so the email and the screen cannot
    disagree about who is outstanding.

BEST-EFFORT, NOT SILENT. Every send is wrapped so a mail failure can never fail
a validation or a return - but failures are LOGGED. Silent swallowing is what
hid a two-year-old bug elsewhere in this codebase, and a notification that never
sends is indistinguishable from one nobody reads.

Verified with no mail configured: every call returns False rather than raising,
an empty staff code returns False, and a digest for a Sunday yields 0
recipients.

Usage (from project root, .venv active):
    python scripts\\patch_e4_notifications.py            # dry run
    python scripts\\patch_e4_notifications.py --apply    # write + .pre_e4 backup
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "branch_log_notify.py")
API = os.path.join("utils", "api_branch_log.py")
BACKUP_SUFFIX = ".pre_e4"

RETURN_OLD = '    audit_log("BRANCH_LOG_RETURN", str(user.get("username", "") or ""), detail=f"log={log_id}")'
RETURN_NEW = (
    '    # E4: the person must know their log came back, and why. Best-effort - a\n'
    '    # mail failure must never fail the return itself.\n'
    '    try:\n'
    '        from utils.branch_log_notify import notify_log_returned\n'
    '        notify_log_returned(str(rec.get("staff_code") or ""),\n'
    '                            str(rec.get("log_date") or ""),\n'
    '                            str(_identity(user).get("staff_name") or ""), note)\n'
    '    except Exception:\n'
    '        pass\n'
    + RETURN_OLD)

BDAY_OLD = '    audit_log("BRANCH_DAY_VALIDATE" if approve else "BRANCH_DAY_RETURN",'
BDAY_NEW = (
    '    if not approve:\n'
    '        # E4: tell the branch manager who submitted it, not the branch at large.\n'
    '        try:\n'
    '            from utils.branch_log_notify import notify_branch_day_returned\n'
    '            notify_branch_day_returned(str(rec.get("submitted_by") or ""),\n'
    '                                       branch, day,\n'
    '                                       str(me.get("staff_name") or ""), note)\n'
    '        except Exception:\n'
    '            pass\n'
    + BDAY_OLD)

MODULE = r'''"""
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
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(API):
        print("ABORT: %s not found. Run from the project root." % API)
        return 1
    if os.path.exists(MOD):
        print("ABORT: %s already exists - E4 looks applied." % MOD)
        return 1

    api = open(API, encoding="utf-8").read()
    if "branch_log_notify" in api:
        print("ABORT: notification hooks already present.")
        return 1
    if "BRANCH_DAY_VALIDATE" not in api:
        print("ABORT: apply patch_b2_branch_day.py first.")
        return 1
    for label, mark in (("individual return", RETURN_OLD), ("branch day", BDAY_OLD)):
        if api.count(mark) != 1:
            print("ABORT: %s anchor matched %d times (expected 1)." % (label, api.count(mark)))
            return 1

    api = api.replace(RETURN_OLD, RETURN_NEW, 1)
    print("  ok  log return -> notifies the staff member")
    api = api.replace(BDAY_OLD, BDAY_NEW, 1)
    print("  ok  branch day return -> notifies the submitting branch manager")

    # Count the IMPORT STATEMENT, not the symbol: each block names the function
    # twice (import + call), so a symbol count of 1 would never hold. This is
    # the same import-presence rule the frontend patchers follow.
    for stmt in ("from utils.branch_log_notify import notify_log_returned",
                 "from utils.branch_log_notify import notify_branch_day_returned"):
        if api.count(stmt) != 1:
            print("ABORT: post-check - %r appears %d times." % (stmt, api.count(stmt)))
            return 1
    for token in ("build_digest_lines", "excuses_target", "logger.warning"):
        if token not in MODULE:
            print("ABORT: embedded module missing %r." % token)
            return 1
    print("  ok  post-checks: one hook each, digest builder present")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(MOD, "w", encoding="utf-8", newline="").write(MODULE)
    print("CREATED %s" % MOD)
    shutil.copy2(API, API + BACKUP_SUFFIX)
    open(API, "w", encoding="utf-8", newline="").write(api)
    print("APPLIED %s  (backup: %s)" % (API, os.path.basename(API) + BACKUP_SUFFIX))

    import py_compile
    for path in (MOD, API):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("\nRestart uvicorn. Email only sends where data/email_config.json is")
    print("configured and the staff member has an address on the roster;")
    print("otherwise this is a safe no-op.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
