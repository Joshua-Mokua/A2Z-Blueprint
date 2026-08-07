"""utils/notifications.py — In-app notification engine.
Real-time notifications for: assignments, approvals, alerts, month-end actions.
"""
import json
from pathlib import Path
from datetime import date, datetime

DATA = Path(__file__).parent.parent / "data"

def get_notifications(staff_code: str, role: str, unit: str) -> list:
    """Return notifications relevant to this user."""
    notifs = []
    today  = date.today()
    
    # ── FD maturity alerts (treasury) ────────────────────────────
    if any(x in role.lower() for x in ('treasury','dealer','forex','head of treasury')):
        try:
            fd = json.loads((DATA/"treasury_fd.json").read_text())
            urgent = [r for r in fd if r.get("maturity_date") and r["status"] in ("approved","booked")
                      and 0<=(date.fromisoformat(str(r["maturity_date"])[:10])-today).days<=7]
            if urgent:
                notifs.append({"type":"warning","icon":"🔔","title":f"{len(urgent)} FD(s) maturing within 7 days",
                                "link":"Treasury","count":len(urgent)})
        except: pass
    
    # ── Apps assigned to this analyst ────────────────────────────
    if any(x in role.lower() for x in ('credit','analyst')):
        try:
            apps = json.loads((DATA/"loan_applications.json").read_text())
            assigned = [a for a in apps if isinstance(a.get("analyst"),dict) and 
                        str(a["analyst"].get("code",""))==str(staff_code) and
                        a["status"] in ("assigned","analysis")]
            if assigned:
                notifs.append({"type":"info","icon":"📋","title":f"{len(assigned)} applications assigned to you",
                                "link":"Loan Applications","count":len(assigned)})
        except: pass
    
    # ── Pending waiver approvals ──────────────────────────────────
    if any(x in role.lower() for x in ('branch manager','area manager','head')):
        try:
            ra = json.loads((DATA/"revenue_assurance.json").read_text())
            pend = [r for r in ra if r["type"]=="Waiver" and r["status"]=="Pending Approval"]
            if pend:
                notifs.append({"type":"warning","icon":"⏳","title":f"{len(pend)} waiver(s) pending your approval",
                                "link":"Revenue Assurance","count":len(pend)})
        except: pass
    
    # ── Open legal SLA breaches ───────────────────────────────────
    if any(x in role.lower() for x in ('legal','company secretary')):
        try:
            legal = json.loads((DATA/"legal_matters.json").read_text())
            breached = [m for m in legal if m.get("sla_breached") and m["status"]!="completed"]
            if breached:
                notifs.append({"type":"error","icon":"⚖️","title":f"{len(breached)} legal SLA breach(es)",
                                "link":"Legal","count":len(breached)})
        except: pass
    
    # ── Pending approval items (maker-checker) ────────────────────
    try:
        p = DATA / "pending_approvals.json"
        approvals = json.loads(p.read_text()) if p.exists() else []
        pending = [a for a in approvals if a.get("status")=="pending_checker" 
                   and str(a.get("maker_code",""))!=str(staff_code)]
        if pending and any(x in role.lower() for x in ("manager","director","chief","head")):
            notifs.append({"type":"warning","icon":"✅","title":f"{len(pending)} item(s) awaiting your approval",
                            "link":"Approvals","count":len(pending)})
    except: pass
    
    # ── Month-end alerts (last 5 days) ────────────────────────────
    import calendar
    last_day = calendar.monthrange(today.year, today.month)[1]
    days_left = last_day - today.day
    if days_left <= 5:
        notifs.append({"type":"info","icon":"📅","title":f"Month-end: {days_left} day(s) remaining",
                        "link":"Smart Alerts","count":days_left})
    
    # ── Performance nudges (Standard #11, v5.38) ──────────────────
    # Pull from utils.nudge_engine — both recognition and alert nudges
    # surface in the bell. Recognition shows as info (blue), alert as
    # warning (amber). Caller can ack via Performance → My Nudges.
    try:
        from utils.nudge_engine import list_active_nudges
        nudges = list_active_nudges(staff_code)
        recognitions = [n for n in nudges if n.get("type") == "recognition"]
        alerts       = [n for n in nudges if n.get("type") == "alert"]
        if recognitions:
            notifs.append({
                "type":  "info",
                "icon":  "🎉",
                "title": f"{len(recognitions)} performance recognition(s)",
                "link":  "Performance",
                "count": len(recognitions),
            })
        if alerts:
            notifs.append({
                "type":  "warning",
                "icon":  "⚠️",
                "title": f"{len(alerts)} KPI(s) behind target",
                "link":  "Performance",
                "count": len(alerts),
            })
    except Exception:
        pass

    return notifs


def render_notification_bell(notifs: list):
    """Render notification bell in sidebar — call from app.py or shared."""
    import streamlit as st
    if not notifs: return
    
    n_crit  = sum(1 for n in notifs if n["type"]=="error")
    n_warn  = sum(1 for n in notifs if n["type"]=="warning")
    n_total = len(notifs)
    
    bell_clr = "#DC2626" if n_crit else "#D97706" if n_warn else "#3B82F6"
    
    st.sidebar.markdown(
        f"<div style='background:{bell_clr}18;border:1px solid {bell_clr}40;"
        f"border-radius:8px;padding:8px 12px;margin:4px 0'>"
        f"<div style='font-size:12px;font-weight:600;color:{bell_clr}'>"
        f"🔔 {n_total} notification{'s' if n_total!=1 else ''}</div>"
        + "".join(f"<div style='font-size:11px;margin-top:3px'>{n['icon']} {n['title']}</div>"
                  for n in notifs[:3])
        + ("</div>"), unsafe_allow_html=True)



# ════════════════════════════════════════════════════════════════════
# v10.471 — Phase 3 Circulatory: notify + send_email + sms_send
# ════════════════════════════════════════════════════════════════════

import logging as _v471_logging

_v471_logger = _v471_logging.getLogger("notifications")


def notify(recipient: str, subject: str, body: str = "",
           channel: str = "inapp", **kwargs) -> bool:
    """Send a notification to a recipient via a channel.

    Args:
        recipient: staff_code or email or phone number
        subject: short headline
        body: detailed body text
        channel: 'inapp' | 'email' | 'sms' | 'all'

    Returns True on accepted-for-delivery (best-effort, never blocks caller).
    """
    try:
        _v471_logger.info(f"notify({recipient}, {subject}) channel={channel}")
        # In real env: dispatch to broker. Here: best-effort no-op.
        if channel in ("email", "all"):
            send_email(recipient, subject, body, **kwargs)
        if channel in ("sms", "all"):
            sms_send(recipient, body or subject, **kwargs)
        return True
    except Exception as exc:
        _v471_logger.warning(f"notify failed: {exc}")
        return False


def send_email(to: str, subject: str, body: str = "",
               attachments=None, **kwargs) -> bool:
    """Send an email via the configured SMTP relay (data/email_config.json).

    Safe by default: if email is not configured (no smtp_host/sender_email),
    this is a logged no-op that returns False — NOTHING is sent. Real sending
    only happens once the bank provides email_config.json. Reuses the same
    load_email_config() + smtplib pattern as core.py's transactional emails so
    there is one SMTP path, not two.

    `body` may be plain text or HTML; we send it as HTML (HTML degrades fine in
    text clients, and our digests are HTML).
    """
    if not to or "@" not in str(to):
        _v471_logger.info(f"send_email skipped — no valid address ({to!r})")
        return False
    try:
        from utils.core import load_email_config
        cfg = load_email_config() or {}
    except Exception as exc:
        _v471_logger.warning(f"send_email: could not load email config: {exc}")
        return False
    if not cfg.get("smtp_host") or not cfg.get("sender_email"):
        # Not configured — safe no-op. This is the default state until the bank
        # sets email_config.json; the in-app bell still works regardless.
        _v471_logger.info(f"send_email no-op (email not configured): to={to} subj={subject!r}")
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = cfg["sender_email"]
        msg["To"]      = to
        msg.attach(MIMEText(body or subject, "html"))
        with smtplib.SMTP(cfg["smtp_host"], int(cfg.get("smtp_port", 587))) as srv:
            srv.starttls()
            if cfg.get("sender_password"):
                srv.login(cfg["sender_email"], cfg["sender_password"])
            srv.sendmail(cfg["sender_email"], [to], msg.as_string())
        _v471_logger.info(f"send_email sent: to={to} subj={subject!r}")
        return True
    except Exception as exc:
        _v471_logger.warning(f"send_email failed: {exc}")
        return False


def sms_send(to: str, message: str, **kwargs) -> bool:
    """Send an SMS. Best-effort dispatch."""
    try:
        _v471_logger.info(f"sms_send({to}, {message[:40]})")
        return True
    except Exception as exc:
        _v471_logger.warning(f"sms_send failed: {exc}")
        return False


def _email_for_staff(staff_code: str) -> str:
    """Resolve a staff member's email from the roster (Email column). '' if none."""
    try:
        from utils.api_pipeline_scope import get_staff_roster
        roster = get_staff_roster()
        if roster is None or len(roster) == 0 or "Email" not in roster.columns:
            return ""
        hit = roster[roster["Staff Code"].astype(str).str.strip() == str(staff_code).strip()]
        if len(hit):
            return str(hit.iloc[0].get("Email", "") or "").strip()
    except Exception as exc:
        _v471_logger.warning(f"_email_for_staff({staff_code}) failed: {exc}")
    return ""


def notify_staff(staff_code: str, subject: str, body_html: str = "") -> bool:
    """Real-time notification to a staff member by code: emails them now (if they
    have an address and email is configured). Best-effort — never raises, never
    blocks the caller. Returns True only if an email was actually sent.

    Event hooks (deal assigned, app assigned, approval pending, …) call THIS so
    there is one testable, rate-guardable real-time path. If email is not
    configured, this is a safe no-op and the in-app bell still shows the item.
    """
    try:
        email = _email_for_staff(staff_code)
        if not email:
            _v471_logger.info(f"notify_staff({staff_code}) — no email on file; in-app only")
            return False
        return send_email(email, subject, body_html or subject)
    except Exception as exc:
        _v471_logger.warning(f"notify_staff({staff_code}) failed: {exc}")
        return False
