# -*- coding: utf-8 -*-
"""Decide a credit case by email, from anywhere, and have it land in the system.

WHY
---
The app is on a LAN address. A recommender on the road, a director at a
branch, a committee member off-site cannot reach it. Email already crosses
that boundary in both directions - so the person never needs the app. The
app reaches the mailbox.

HOW
---
    1. The case is SENT: summary, the analyst's note, the journey so far, the
       documents attached, and a token in the subject.
    2. The person REPLIES from anywhere. First line: APPROVE, DECLINE or
       RETURN. Everything after it goes on the record as their reason.
    3. The server, on the LAN, READS the mailbox, matches the token to one
       case and one person, and records the decision through the SAME route
       function the screen uses - so the case moves, the credit admin case is
       opened, the journey is written and the next person is emailed exactly
       as if it had been done on screen.

WHAT KEEPS IT SAFE
------------------
    the token is single-use, tied to one case and one person, and expires
    a reply from a different address than the one it was sent to is refused
    a reply that does not start with a verdict word is recorded and NOT acted on
    every accepted and refused reply is on the journey and the audit trail

WHAT THE BANK HAS TO PROVIDE
----------------------------
A mailbox the system can read. noreply@ecobank.com cannot receive replies.
data/email_config.json needs:

    "imap_host":     "...",
    "imap_port":     993,
    "imap_user":     "a2z-credit@ecobank.com",
    "imap_password": "...",
    "reply_to":      "a2z-credit@ecobank.com"
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import os
import re
import secrets
from typing import Any, Dict, List, Optional, Tuple

TOKEN_TTL_HOURS = 72
VERDICTS = {
    "APPROVE": "approved", "APPROVED": "approved", "RECOMMEND": "approved",
    "RECOMMENDED": "approved", "YES": "approved",
    "DECLINE": "declined", "DECLINED": "declined", "REJECT": "declined",
    "NO": "declined",
    "RETURN": "returned", "RETURNED": "returned", "REWORK": "returned",
}
_TOKEN_RE = re.compile(r"\[A2Z-([A-Z0-9]+)-([a-z0-9]{10})\]")


# ── CONFIG ────────────────────────────────────────────────────────────────────

def _cfg() -> Dict[str, Any]:
    p = os.path.join("data", "email_config.json")
    try:
        return json.load(open(p, encoding="utf-8")) or {}
    except Exception:
        return {}


def _secret() -> bytes:
    cfg = _cfg()
    s = str(cfg.get("decision_secret") or cfg.get("sender_password") or "a2z")
    return s.encode("utf-8")


def _tokens_path() -> str:
    return os.path.join("data", "email_decision_tokens.json")


def _load_tokens() -> Dict[str, Dict[str, Any]]:
    try:
        return json.load(open(_tokens_path(), encoding="utf-8")) or {}
    except Exception:
        return {}


def _save_tokens(t: Dict[str, Dict[str, Any]]) -> None:
    json.dump(t, open(_tokens_path(), "w", encoding="utf-8"), indent=2)


def _audit(action: str, detail: str) -> None:
    try:
        from utils.core_audit import audit_log
        audit_log(action, "email", detail)
    except Exception:
        pass


# ── SENDING ───────────────────────────────────────────────────────────────────

def issue_token(app_id: str, staff_code: str, email: str) -> str:
    """One token: one case, one person, one use, expiring."""
    nonce = secrets.token_hex(5)
    sig = hmac.new(_secret(), ("%s|%s|%s" % (app_id, staff_code, nonce)).encode(),
                   hashlib.sha256).hexdigest()[:10]
    t = _load_tokens()
    t[sig] = {
        "app_id": app_id, "staff_code": staff_code, "email": email.lower(),
        "issued": _dt.datetime.now().isoformat(timespec="seconds"),
        "expires": (_dt.datetime.now() + _dt.timedelta(hours=TOKEN_TTL_HOURS)
                    ).isoformat(timespec="seconds"),
        "used": False,
    }
    _save_tokens(t)
    return sig


def _journey_text(app: Dict[str, Any]) -> str:
    try:
        from utils.api_lms_journey import build_case_journey
        events = build_case_journey(app) or []
    except Exception:
        events = list(app.get("history") or [])
    lines = []
    for e in events[-25:]:
        at = str(e.get("at") or "")[:16].replace("T", " ")
        who = str(e.get("by_name") or e.get("by") or "")
        what = str(e.get("event") or "").replace("_", " ")
        note = str(e.get("note") or e.get("text") or "")
        lines.append("  %s  %-24s %s%s" % (at, who[:24], what,
                                            (" - " + note) if note else ""))
    return "\n".join(lines) or "  (no events yet)"


def _document_paths(app: Dict[str, Any]) -> List[str]:
    """Absolute paths of the documents attached to the case's deal."""
    out = []
    deal_id = str(app.get("pipeline_deal_id") or "").strip()
    if not deal_id:
        return out
    base = os.path.join("data", "documents", deal_id)
    if os.path.isdir(base):
        for fn in sorted(os.listdir(base)):
            p = os.path.join(base, fn)
            if os.path.isfile(p) and os.path.getsize(p) < 8 * 1024 * 1024:
                out.append(p)
    return out


def send_for_decision(app_id: str, staff_code: str, asked_by: Dict[str, Any],
                      dry_run: bool = False) -> Dict[str, Any]:
    """Email the case to somebody for their decision."""
    from utils.api_lms_routes import _lam
    from utils.core import UserManager

    app = _lam().get(app_id)
    if not app:
        raise LookupError("Application '%s' not found" % app_id)

    users = UserManager().users or {}
    person = next((r for r in users.values()
                   if str(r.get("staff_code", "")).strip() == staff_code), None)
    if not person:
        raise LookupError("Nobody has staff code %r" % staff_code)
    email = str(person.get("email") or "").strip()
    if not email:
        raise ValueError("%s has no email address on their account"
                         % (person.get("full_name") or staff_code))

    cfg = _cfg()
    reply_to = str(cfg.get("reply_to") or cfg.get("imap_user") or "").strip()
    if not reply_to:
        raise RuntimeError("No reply_to mailbox in data/email_config.json - "
                           "replies would go to noreply and never be read.")

    token = issue_token(app_id, staff_code, email) if not dry_run else "DRYRUN0000"
    subject = "[A2Z-%s-%s] Your decision is needed: %s" % (
        app_id, token, str(app.get("client_name") or ""))

    amount = app.get("amount") or 0
    try:
        amount_s = "KES %s" % format(int(float(amount)), ",")
    except (TypeError, ValueError):
        amount_s = str(amount)
    an = app.get("analyst_before_recommendation") or app.get("analyst") or {}
    analyst = str((an or {}).get("name") or "") if isinstance(an, dict) else ""
    readiness = app.get("committee_readiness") or {}
    analyst_note = str((readiness or {}).get("opinion") or "")

    body = """%s,

%s has asked for your decision on this case. Reply to this email from
your phone or anywhere else. You do not need to reach the system.

REPLY WITH ONE OF THESE AS THE FIRST LINE, then your reasons:

    APPROVE
    DECLINE
    RETURN

Everything after that line goes on the case record as your reason.

------------------------------------------------------------
CASE           %s
CLIENT         %s
PRODUCT        %s
AMOUNT         %s
STATUS         %s
RECOMMENDED BY %s
ANALYST        %s
------------------------------------------------------------

ANALYST'S NOTE
%s

CASE JOURNEY SO FAR
%s

The documents are attached.

This request expires in %d hours. It is for you alone - a reply from another
address will be refused.
""" % (
        person.get("full_name") or staff_code,
        asked_by.get("full_name") or "The system",
        app_id, app.get("client_name"), app.get("product") or "-", amount_s,
        app.get("status"), app.get("committee_recommended_by") or "-",
        analyst or "-",
        analyst_note or "  (none recorded)",
        _journey_text(app),
        TOKEN_TTL_HOURS,
    )

    docs = _document_paths(app)
    if dry_run:
        return {"to": email, "subject": subject, "documents": len(docs),
                "reply_to": reply_to, "body": body}

    from utils.notifications import send_email
    ok = send_email(email, subject, body, attachments=docs or None,
                    reply_to=reply_to)
    _audit("EMAIL_DECISION_SENT" if ok else "EMAIL_DECISION_NOT_SENT",
           "%s|to=%s|%s|docs=%d" % (app_id, staff_code, email, len(docs)))
    try:
        from utils.handover import journey
        journey(app_id, "sent_for_email_decision", asked_by,
                "Emailed to %s for their decision (%d document%s attached)"
                % (person.get("full_name") or staff_code, len(docs),
                   "" if len(docs) == 1 else "s"),
                to=staff_code, token=token)
    except Exception:
        pass
    return {"to": email, "subject": subject, "documents": len(docs),
            "sent": ok, "token": token}


# ── READING REPLIES ───────────────────────────────────────────────────────────

def parse_reply(subject: str, body: str) -> Tuple[Optional[str], Optional[str],
                                                  str, str]:
    """(app_id, token, verdict, reason) from a reply. verdict '' if none."""
    m = _TOKEN_RE.search(subject or "")
    if not m:
        m = _TOKEN_RE.search(body or "")
    if not m:
        return None, None, "", ""
    app_id, token = m.group(1), m.group(2)

    # First non-empty line that is not quoted, not a greeting artefact.
    verdict, reason_lines = "", []
    for raw in (body or "").splitlines():
        line = raw.strip()
        if not line or line.startswith(">"):
            continue
        if re.match(r"^(On .* wrote:|From:|Sent:|To:|Subject:|-----)", line):
            break
        if not verdict:
            word = re.sub(r"[^A-Za-z]", "", line.split()[0]).upper() if line.split() else ""
            if word in VERDICTS:
                verdict = VERDICTS[word]
                rest = line[len(line.split()[0]):].strip(" :-")
                if rest:
                    reason_lines.append(rest)
                continue
            # No verdict on the first line: whatever they wrote is a comment.
            reason_lines.append(line)
            continue
        reason_lines.append(line)
    return app_id, token, verdict, " ".join(reason_lines).strip()


def record_from_reply(app_id: str, token: str, from_addr: str, verdict: str,
                      reason: str) -> Dict[str, Any]:
    """Act on a reply, through the same route the screen uses."""
    t = _load_tokens()
    rec = t.get(token)
    if not rec or rec.get("app_id") != app_id:
        _audit("EMAIL_DECISION_REFUSED", "%s|%s|unknown token" % (app_id, token))
        return {"ok": False, "why": "unknown token"}
    if rec.get("used"):
        _audit("EMAIL_DECISION_REFUSED", "%s|%s|token already used" % (app_id, token))
        return {"ok": False, "why": "already used"}
    if _dt.datetime.now().isoformat() > str(rec.get("expires") or ""):
        _audit("EMAIL_DECISION_REFUSED", "%s|%s|expired" % (app_id, token))
        return {"ok": False, "why": "expired"}
    if str(from_addr or "").strip().lower() != str(rec.get("email") or "").lower():
        _audit("EMAIL_DECISION_REFUSED",
               "%s|%s|from %s, expected %s" % (app_id, token, from_addr,
                                               rec.get("email")))
        return {"ok": False, "why": "wrong sender"}

    from utils.core import UserManager
    users = UserManager().users or {}
    user = next((dict(r, username=l) for l, r in users.items()
                 if str(r.get("staff_code", "")).strip() == rec["staff_code"]),
                None)
    if not user:
        return {"ok": False, "why": "person no longer exists"}

    if not verdict:
        try:
            from utils.handover import journey
            journey(app_id, "email_reply_no_verdict", user,
                    "Replied by email without a verdict: %s" % (reason or "(empty)"))
        except Exception:
            pass
        _audit("EMAIL_DECISION_NO_VERDICT", "%s|%s" % (app_id, reason[:60]))
        return {"ok": False, "why": "no verdict - recorded as a comment"}

    if len(reason) < 5:
        reason = "Decided by email reply (no reason given)"

    # The SAME function the screen calls. Everything it does - the status,
    # the credit admin case, the journey, the next email - happens here too.
    from utils.api_lms_routes import lms_application_decision
    from utils.api_lms_models import RecordDecisionRequest
    payload = RecordDecisionRequest(verdict=verdict, authority="Credit Risk",
                                    reason=reason)
    try:
        res = lms_application_decision(app_id, payload, user)
    except Exception as exc:
        _audit("EMAIL_DECISION_FAILED", "%s|%s|%s" % (app_id, verdict, str(exc)[:60]))
        return {"ok": False, "why": "the decision was refused: %s" % str(exc)[:80]}

    rec["used"] = True
    rec["used_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    rec["verdict"] = verdict
    _save_tokens(t)
    try:
        from utils.handover import journey
        journey(app_id, "decided_by_email", user,
                "%s by email reply: %s" % (verdict.title(), reason),
                verdict=verdict, from_addr=from_addr)
    except Exception:
        pass
    _audit("EMAIL_DECISION_RECORDED", "%s|%s|%s" % (app_id, verdict, reason[:60]))
    return {"ok": True, "verdict": verdict, "result": res}


def poll_once(dry_run: bool = False) -> Dict[str, int]:
    """Read the mailbox once and act on every decision reply in it."""
    import email as _email
    import imaplib

    cfg = _cfg()
    host = str(cfg.get("imap_host") or "").strip()
    user = str(cfg.get("imap_user") or "").strip()
    pw = str(cfg.get("imap_password") or "")
    port = int(cfg.get("imap_port") or 993)
    if not host or not user:
        raise RuntimeError("imap_host / imap_user not set in data/email_config.json")

    counts = {"seen": 0, "acted": 0, "refused": 0, "ignored": 0}
    box = imaplib.IMAP4_SSL(host, port) if port == 993 else imaplib.IMAP4(host, port)
    box.login(user, pw)
    box.select("INBOX")
    _typ, data = box.search(None, "UNSEEN")
    for num in (data[0] or b"").split():
        counts["seen"] += 1
        _typ, msg_data = box.fetch(num, "(RFC822)")
        msg = _email.message_from_bytes(msg_data[0][1])
        subject = str(msg.get("Subject") or "")
        from_addr = _email.utils.parseaddr(str(msg.get("From") or ""))[1]
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                if part.get_content_type() == "text/plain":
                    body = part.get_payload(decode=True).decode(
                        part.get_content_charset() or "utf-8", "replace")
                    break
        else:
            body = msg.get_payload(decode=True).decode(
                msg.get_content_charset() or "utf-8", "replace")

        app_id, token, verdict, reason = parse_reply(subject, body)
        if not app_id:
            counts["ignored"] += 1
            continue
        if dry_run:
            print("  would act: %s %s from %s -> %s: %s"
                  % (app_id, token, from_addr, verdict or "(no verdict)",
                     reason[:60]))
            continue
        res = record_from_reply(app_id, token, from_addr, verdict, reason)
        if res.get("ok"):
            counts["acted"] += 1
            box.store(num, "+FLAGS", "\\Seen")
        else:
            counts["refused"] += 1
            box.store(num, "+FLAGS", "\\Seen")
    box.logout()
    return counts
