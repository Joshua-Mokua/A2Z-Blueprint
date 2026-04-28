"""pages/50_cybersecurity.py — Cybersecurity Dashboard.
Threat alerts, patch compliance, phishing tests, vulnerability tracker.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("cybersecurity")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)
is_cyber = any(x in role.lower() for x in ("cyber","security","ict","information","soc"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔐 Cybersecurity</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Threat posture · Patch compliance · Phishing · Vulnerability tracker</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"cybersecurity.json"
    return a2z_db.load_json(p) if p.exists() else {}

data = _load()
if not data: st.info("Cybersecurity data not available."); st.stop()

patch  = data.get("patch_compliance_pct",0)
target = data.get("target_patch_pct",95)
phish  = data.get("phishing_test",{})
vulns  = data.get("vulnerabilities",[])
priv   = data.get("privileged_accounts",{})
crit_unpatched = data.get("critical_unpatched",0)
cbk_pending    = data.get("cbk_reportable_pending",0)

# Threat posture banner
posture_clr = "#16A34A" if patch>=target and crit_unpatched==0 else "#D97706" if patch>=cfg("cyber_patch_warn",80) else "#DC2626"
posture_txt = "SECURE" if patch>=target and crit_unpatched==0 else "MODERATE RISK" if patch>=cfg("cyber_patch_warn",80) else "HIGH RISK"

st.markdown(
    f"<div style='background:{posture_clr}12;border:2px solid {posture_clr}40;border-radius:10px;"
    f"padding:10px 18px;margin-bottom:10px;display:flex;align-items:center;gap:16px'>"
    f"<div style='font-size:22px;font-weight:800;color:{posture_clr}'>🔒 {posture_txt}</div>"
    f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
    f"Patch compliance: {patch:.0f}% · Critical unpatched: {crit_unpatched} · "
    f"SIEM alerts today: {data.get('siem_alerts_today',0)} · "
    f"{'⚠️ CBK reportable pending' if cbk_pending else 'No CBK pending'}</div></div>",
    unsafe_allow_html=True)

tabs = st.tabs(["🩹 Patch Compliance","🎣 Phishing Tests","🐛 Vulnerabilities","🔑 Privileged Access","⚠️ Incidents"])

with tabs[0]:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Patch Compliance",   f"{patch:.1f}%",
              f"Target {target:.0f}%", delta_color="normal" if patch>=target else "inverse")
    c2.metric("Critical Unpatched", crit_unpatched, delta_color="normal" if crit_unpatched==0 else "inverse")
    c3.metric("High Unpatched",     data.get("high_unpatched",0))
    c4.metric("Target",             f"{target:.0f}%")
    gap = target - patch
    if gap > 0:
        st.error(f"🔴 Patch compliance is {gap:.1f}pp below target — {crit_unpatched} critical patches outstanding")
    st.markdown("**Patch compliance by priority:**")
    for v in vulns:
        sev = v["severity"]
        clr = {"Critical":"#DC2626","High":"#D97706","Medium":"#3B82F6","Low":"#6B7280"}.get(sev,"#6B7280")
        st.markdown(
            f"<div style='border-left:3px solid {clr};padding:5px 12px;margin:3px;background:{clr}08'>"
            f"<b style='color:{clr}'>{sev}</b>: {v['count']} vulnerabilities · oldest: {v['oldest_days']} days</div>",
            unsafe_allow_html=True)

with tabs[1]:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Emails Sent",    phish.get("sent",0))
    c2.metric("Clicked",        phish.get("clicked",0))
    c3.metric("Click Rate",     f"{phish.get('click_rate_pct',0):.1f}%",
              delta_color="normal" if phish.get("click_rate_pct",0)<cfg("phishing_click_target",5) else "inverse")
    c4.metric("Reported",       phish.get("reported",0))
    target_click = cfg('phishing_click_target', 5.0)
    if phish.get("click_rate_pct",0) > target_click:
        st.warning(f"⚠️ Click rate {phish['click_rate_pct']:.1f}% exceeds 5% target — additional training required")
    st.caption(f"Phishing simulation tests staff awareness. Best-in-class banks achieve <{cfg('phishing_click_target',5)//2}% click rate.")

with tabs[2]:
    if vulns:
        v_rows=[{"Severity":v["severity"],"Open Count":v["count"],"Oldest (days)":v["oldest_days"],
                  "Risk":("🔴 Critical" if v["severity"]=="Critical" else "🟠 High" if v["severity"]=="High" else "🟡 Medium")}
                 for v in vulns]
        st.dataframe(pd.DataFrame(v_rows),use_container_width=True,hide_index=True)
        if crit_unpatched:
            st.error(f"🔴 {crit_unpatched} CRITICAL vulnerabilities unpatched — patch within 24 hours per CBK guidelines")

with tabs[3]:
    c1,c2,c3 = st.columns(3)
    c1.metric("Total Privileged Accounts", priv.get("total",0))
    c2.metric("Reviewed this quarter",     priv.get("reviewed_this_quarter",0))
    c3.metric("Overdue review",            priv.get("overdue_review",0),
              delta_color="normal" if priv.get("overdue_review",0)==0 else "inverse")
    if priv.get("overdue_review",0):
        st.warning(f"⚠️ {priv['overdue_review']} privileged accounts overdue for quarterly access review")
    st.caption("CBK requires quarterly review of all privileged access. Overdue reviews must be escalated to CISO.")

with tabs[4]:
    st.metric("CBK Reportable Incidents Pending", cbk_pending,
               delta_color="normal" if cbk_pending==0 else "inverse")
    st.metric("Total Incidents (30d)", data.get("incidents_30d",0))
    if cbk_pending:
        st.error(f"🔴 {cbk_pending} CBK-reportable incident(s) pending notification — file within 24 hours")
    st.caption("Per CBK Prudential Guideline on Cybersecurity: major incidents must be reported within 24 hours.")
