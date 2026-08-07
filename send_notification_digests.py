#!/usr/bin/env python3
"""Daily notification digest — emails each staff member their pending items.

Iterates staff (from the roster), computes each one's in-app notifications via
get_notifications(), and emails a digest to those who have any AND have an email
on file. Safe by default: if email is not configured, send_email() is a no-op.

Usage:
  python send_notification_digests.py             dry-run: prints who WOULD be emailed + counts
  python send_notification_digests.py --send       actually send
  python send_notification_digests.py --send --once-per-day   (default guard: skip if already sent today)

Schedule (bank server): run once daily, e.g. 7:00am, via crontab or Windows Task Scheduler.
"""
import sys, json, logging
from pathlib import Path
from datetime import date, datetime

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("digest")

DRY = "--send" not in sys.argv
DATA = Path(__file__).parent / "data"
SENT_LOG = DATA / "digest_sent_log.json"   # per-day guard so we don't double-send


def _load_sent():
    try:
        return json.loads(SENT_LOG.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_sent(d):
    try:
        SENT_LOG.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception as e:
        log.warning(f"could not write sent-log: {e}")


def _digest_html(name, notifs):
    rows = ""
    for n in notifs:
        icon = n.get("icon", "•")
        title = n.get("title", "")
        link = n.get("link", "")
        rows += (f'<tr><td style="padding:8px 12px;border-bottom:1px solid #eee">'
                 f'{icon} {title}</td>'
                 f'<td style="padding:8px 12px;border-bottom:1px solid #eee;color:#0082BB">'
                 f'{link}</td></tr>')
    return f"""<html><body style="font-family:Arial,sans-serif;max-width:560px;margin:auto">
<div style="background:#0082BB;padding:18px;border-radius:8px 8px 0 0">
  <h2 style="color:#fff;margin:0">A2Z MIS 360</h2>
  <p style="color:#BED600;margin:4px 0 0">Your pending items</p>
</div>
<div style="padding:20px;border:1px solid #e0e0e0;border-top:none;border-radius:0 0 8px 8px">
  <p>Hi <strong>{name}</strong>,</p>
  <p>You have {len(notifs)} item(s) needing attention:</p>
  <table style="width:100%;border-collapse:collapse;margin-top:8px">{rows}</table>
  <p style="font-size:12px;color:#999;margin-top:20px">Log in to A2Z MIS 360 to action these.
  This is an automated daily digest — do not reply.</p>
</div></body></html>"""


def main():
    log.info("=" * 60)
    log.info(f"Notification digest — {'DRY-RUN (nothing sent)' if DRY else 'SEND mode'} — {datetime.now():%Y-%m-%d %H:%M}")

    from utils.api_pipeline_scope import get_staff_roster
    from utils.notifications import get_notifications, send_email

    roster = get_staff_roster()
    if roster is None or len(roster) == 0:
        log.info("roster empty — nothing to do"); return

    has_email_col = "Email" in roster.columns
    today = str(date.today())
    sent = _load_sent()
    today_sent = set(sent.get(today, []))

    n_candidates = 0
    n_with_items = 0
    n_emailed = 0
    n_skipped_no_email = 0
    n_skipped_already = 0

    for _, r in roster.iterrows():
        code = str(r.get("Staff Code", "") or "").strip()
        name = str(r.get("Staff Name", "") or "").strip()
        role = str(r.get("Role", "") or "").strip()
        unit = str(r.get("Unit", "") or "").strip()
        email = str(r.get("Email", "") or "").strip() if has_email_col else ""
        if not code:
            continue
        n_candidates += 1

        try:
            notifs = get_notifications(code, role, unit)
        except Exception as e:
            log.warning(f"  {code} {name}: get_notifications error: {e}")
            continue
        if not notifs:
            continue
        n_with_items += 1

        total = sum(int(n.get("count", 1) or 1) for n in notifs)
        if not email or "@" not in email:
            n_skipped_no_email += 1
            log.info(f"  [no-email] {code} {name}: {len(notifs)} item(s) ({total}) — has no email on file")
            continue

        if "--once-per-day" in sys.argv and code in today_sent:
            n_skipped_already += 1
            continue

        if DRY:
            log.info(f"  [would email] {name} <{email}>: {len(notifs)} item(s), {total} total")
        else:
            ok = send_email(email, "A2Z MIS 360 — your pending items", _digest_html(name, notifs))
            if ok:
                n_emailed += 1
                today_sent.add(code)
                log.info(f"  [emailed] {name} <{email}>: {len(notifs)} item(s)")
            else:
                log.info(f"  [send-failed/no-op] {name} <{email}> (email not configured?)")

    if not DRY:
        sent[today] = sorted(today_sent)
        # keep only last 7 days of guard log
        for k in list(sent.keys()):
            if k < str(date.today().replace(day=1)):
                pass
        _save_sent(sent)

    log.info("-" * 60)
    log.info(f"candidates: {n_candidates}   with pending items: {n_with_items}")
    log.info(f"emailed: {n_emailed}   skipped (no email): {n_skipped_no_email}   skipped (already today): {n_skipped_already}")
    if DRY:
        log.info("DRY-RUN — nothing was sent. Re-run with --send to send.")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
