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
