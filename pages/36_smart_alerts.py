"""pages/36_smart_alerts.py — Smart Alerts Engine.
Proactive alerts: maturing FDs, BSC drops, SLA breaches,
deal staleness, compliance deadlines. AI-prioritised.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import Counter
from pages._shared import load_shared_state
from pages._access import require_access

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()



require_access("smart_alerts")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

@st.cache_data(ttl=30, show_spinner=False)
def _build_alerts():
    alerts = []
    aid = 1

    def add(atype, icon, sev, title, msg, module):
        nonlocal aid
        alerts.append({"id":f"ALT{aid:05d}","type":atype,"icon":icon,"severity":sev,
                        "title":title,"message":msg,"module":module,
                        "created":str(today),"read":False})
        aid+=1

    # FD maturing
    try:
        fd = json.loads((DATA/"treasury_fd.json").read_text())
        for r in fd:
            if r.get("maturity_date") and r["status"] in ("approved","booked"):
                try:
                    days=(_safe_date(r["maturity_date"])-today).days
                    if 0<=days<=7:
                        add("FD_MATURING","🔔","critical",
                            f"FD maturing in {days}d",
                            f"{r['client_name'][:25]} · {r['currency']} {r['amount']/1e6:.1f}M · {r['maturity_date']}",
                            "Treasury")
                    elif 8<=days<=30:
                        add("FD_MATURING","🔔","warning",
                            f"FD maturing in {days}d",
                            f"{r['client_name'][:25]} · {r['currency']} {r['amount']/1e6:.1f}M",
                            "Treasury")
                except: pass
    except: pass

    # Legal SLA breaches
    try:
        legal=json.loads((DATA/"legal_matters.json").read_text())
        for m in legal:
            if m.get("sla_breached") and m["status"] not in ("completed","on_hold"):
                add("LEGAL_OVERDUE","⚖️","critical",
                    f"Legal SLA breached",
                    f"{m.get('matter_type','')} · {m.get('client_name','')[:20]} · {m['status']}",
                    "Legal")
    except: pass

    # BSC below threshold
    try:
        scores=json.loads((DATA/"feb_2026_staff_scores.json").read_text())
        low = [(k,v) for k,v in scores.items() if v["final_score"]<2.5]
        for sc_v,s in low[:10]:
            add("BSC_LOW","📉","warning",
                f"BSC below 2.5: {s['name'][:20]}",
                f"Score {s['final_score']:.2f} · {s['role'][:30]} · {s['unit']}",
                "Performance")
    except: pass

    # Pipeline stale deals
    try:
        pipeline=json.loads((DATA/"pipeline.json").read_text())
        active=[d for d in pipeline if d.get("stage") not in ("Closed Won","Closed Lost")]
        for d in active:
            try:
                last=_safe_date(d.get("last_updated",str(today)))
                days=(today-last).days
                if days>=14:
                    add("DEAL_STALE","💼","info",
                        f"Deal stale {days}d: {d.get('client_name','')[:20]}",
                        f"{d.get('product','')[:25]} · {d.get('stage','')} · KES {d.get('amount',0)/1e6:.0f}M",
                        "Pipeline")
            except: pass
    except: pass

    # Compliance overdue
    try:
        comp=json.loads((DATA/"compliance_cases.json").read_text())
        for c in comp:
            if c["status"] in ("open","under_review"):
                try:
                    raised=_safe_date(c.get("raised_date",str(today)))
                    days=(today-raised).days
                    sla={"Critical":1,"High":3,"Medium":7,"Low":14}.get(c.get("risk_level","Low"),7)
                    if days>sla:
                        add("COMPLIANCE_DUE","🛡️","critical",
                            f"Compliance case overdue: {c.get('risk_level','')}",
                            f"{c.get('case_type','')[:30]} · {days}d open (SLA {sla}d)",
                            "Compliance")
                except: pass
    except: pass

    # RMS old breaks
    try:
        rms=json.loads((DATA/"rms_reconciliations.json").read_text())
        old_breaks=[r for r in rms if r["status"]!="Matched" and r.get("ageing_days",0)>30]
        if old_breaks:
            add("RECON_OLD","🔄","warning",
                f"{len(old_breaks)} reconciliation breaks aged >30d",
                f"Total variance: KES {sum(r['abs_variance'] for r in old_breaks)/1e6:.1f}M",
                "Reconciliation")
    except: pass

    # EDMS expiring docs
    try:
        edms=json.loads((DATA/"edms_documents.json").read_text())
        expiring=[d for d in edms if not d["is_expired"] and
                  0<=(_safe_date(d["expiry_date"])-today).days<=30]
        if expiring:
            add("DOCS_EXPIRING","📁","warning",
                f"{len(expiring)} documents expiring within 30 days",
                "Review and renew in EDMS","EDMS")
    except: pass

    return sorted(alerts, key=lambda x:{"critical":0,"warning":1,"info":2}.get(x["severity"],3))

alerts = _build_alerts()


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔔 Smart Alerts</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Proactive · Real-time · AI-prioritised</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔔 Smart Alerts</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Proactive · Real-time · AI-prioritised</span></div>",
    unsafe_allow_html=True)

# Summary
crits  = [a for a in alerts if a["severity"]=="critical"]
warns  = [a for a in alerts if a["severity"]=="warning"]
infos  = [a for a in alerts if a["severity"]=="info"]

c1,c2,c3,c4 = st.columns(4)
c1.metric("🔴 Critical",  len(crits))
c2.metric("🟡 Warning",   len(warns))
c3.metric("ℹ️ Info",      len(infos))
c4.metric("Total Alerts", len(alerts))

if crits:
    st.error(f"🔴 **{len(crits)} critical alerts** require immediate attention")

st.markdown("---")
tabs = st.tabs(["🔴 Critical","🟡 Warnings","ℹ️ All Alerts","⚙️ Alert Config"])

def render_alerts(alert_list):
    if not alert_list:
        st.success("✅ No alerts in this category.")
        return
    for a in alert_list:
        clr={"critical":"#DC2626","warning":"#D97706","info":"#3B82F6"}.get(a["severity"],"#6B7280")
        with st.container():
            col1,col2,col3 = st.columns([1,8,2])
            col1.markdown(f"<div style='font-size:24px'>{a['icon']}</div>",unsafe_allow_html=True)
            col2.markdown(
                f"<div style='padding:6px 0'>"
                f"<div style='font-size:13px;font-weight:700;color:{clr}'>{a['title']}</div>"
                f"<div style='font-size:11px;color:var(--color-text-secondary)'>{a['message']}</div>"
                f"<div style='font-size:10px;color:var(--color-text-tertiary)'>Module: {a['module']} · {a['created']}</div>"
                f"</div>", unsafe_allow_html=True)
            col3.markdown(f"<span style='background:{clr}20;color:{clr};border-radius:10px;"
                          f"padding:2px 8px;font-size:10px;font-weight:600'>{a['severity'].upper()}</span>",
                          unsafe_allow_html=True)
            st.markdown("<hr style='margin:2px 0;opacity:0.2'>",unsafe_allow_html=True)

with tabs[0]: render_alerts(crits)
with tabs[1]: render_alerts(warns)
with tabs[2]: render_alerts(alerts)
with tabs[3]:
    st.markdown("**Alert configuration (what triggers alerts):**")
    st.json({
        "FD_MATURING":      "7 days (critical), 30 days (warning)",
        "LEGAL_OVERDUE":    "Any SLA breach",
        "BSC_LOW":          "Score below 2.5",
        "DEAL_STALE":       "14 days without update",
        "COMPLIANCE_DUE":   "Beyond SLA days for risk level",
        "RECON_OLD":        "Reconciliation break aged 30+ days",
        "DOCS_EXPIRING":    "30 days before expiry",
    })
    st.caption("Alert thresholds are configurable via Admin. Alert routing to specific roles is configurable.")
