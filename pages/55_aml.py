"""pages/55_aml.py — AML Transaction Monitoring.
Alert management, STR filing, risk scoring. Thresholds via Admin.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("aml_monitoring")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_aml   = any(x in role for x in ("compliance","aml","mlro","risk","chief compliance","money laundering"))

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>🔍 AML Transaction Monitoring</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Alerts · STR filing · Risk scoring · Case management</span></div>", unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"aml_alerts.json"
    return json.loads(p.read_text()) if p.exists() else []

alerts    = _load()
HIGH_THR  = cfg("aml_high_risk_score", 70)
CASH_THR  = cfg("aml_cash_threshold_m", 1.0)

high_risk = [a for a in alerts if a.get("risk_score",0) >= HIGH_THR]
open_alts = [a for a in alerts if a.get("status","") in ("Open","Under Review","Escalated to STR")]
strs      = [a for a in alerts if a.get("str_filed")]

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Alerts",  len(alerts))
m2.metric("Open / Active", len(open_alts), delta_color="normal" if not open_alts else "inverse")
m3.metric("High Risk (≥"+str(HIGH_THR)+")", len(high_risk), delta_color="normal" if not high_risk else "inverse")
m4.metric("STRs Filed",    len(strs))

if [a for a in high_risk if a.get("status")=="Open"]:
    st.error(f"🔴 {sum(1 for a in high_risk if a['status']=='Open')} high-risk alerts unassigned — assign immediately")

tabs = st.tabs(["🔴 High Risk","📋 All Alerts","📊 Analytics","📝 New Alert","📄 STR Log"])

_aml_render_count = [0]  # unique key counter

def _render(alert_list, show_update=True):
    if not alert_list: st.success("None here."); return
    rows=[{"ID":a["id"],"Account":a["account_number"][:18],"Rule":a["rule_triggered"][:35],
            "Amount (M)":round(a["amount"]/1e6,2),"Risk Score":a["risk_score"],
            "Level":a["risk_level"],"Status":a["status"][:20],
            "Assigned":a.get("assigned_to","")[:20],"Date":a["transaction_date"][:10],
            "STR":("✅" if a.get("str_filed") else "")}
           for a in sorted(alert_list,key=lambda x:-x.get("risk_score",0))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    if show_update and (is_aml or is_admin) and alert_list:
        _aml_render_count[0] += 1
        _uid = _aml_render_count[0]
        st.markdown("**Update alert:**")
        sel = st.selectbox("Select alert", [a["id"] for a in alert_list],
                           key=f"aml_sel_{_uid}")
        new_status = st.selectbox("New status",
                                   ["Open","Under Review","Cleared","Escalated to STR","Closed-No Action"],
                                   key=f"aml_stat_{_uid}")
        str_filed  = st.checkbox("File STR", key=f"aml_str_{_uid}")
        notes      = st.text_input("Notes",  key=f"aml_note_{_uid}")
        if st.button("💾 Save", key=f"aml_save_{_uid}", type="primary"):
            all_a = json.loads((DATA/"aml_alerts.json").read_text())
            for a in all_a:
                if a["id"]==sel:
                    a["status"]=new_status; a["str_filed"]=str_filed
                    if notes: a["notes"]=notes; a["updated_at"]=str(today)
            (DATA/"aml_alerts.json").write_text(json.dumps(all_a,indent=2))
            audit_log("AML_ALERT_UPDATED",uname,f"{sel}: {new_status}")
            st.cache_data.clear(); st.success("✅ Updated"); st.rerun()

with tabs[0]: _render(high_risk)
with tabs[1]:
    f1,f2 = st.columns(2)
    flevel = f1.selectbox("Risk Level",["All","High","Medium","Low"],key="aml_lev")
    fstat  = f2.selectbox("Status",["All","Open","Under Review","Cleared","Escalated to STR","Closed-No Action"],key="aml_st")
    vis = [a for a in alerts if (flevel=="All" or a["risk_level"]==flevel) and (fstat=="All" or a["status"]==fstat)]
    _render(vis)

with tabs[2]:
    rule_ct = Counter(a["rule_triggered"] for a in alerts)
    st.markdown("**Top triggered rules:**")
    st.bar_chart(pd.DataFrame({"Alerts":dict(rule_ct.most_common(8))}).T.T)
    st.markdown("**Risk level distribution:**")
    lev_ct = Counter(a["risk_level"] for a in alerts)
    for lev,n in lev_ct.most_common():
        st.markdown(f"  {lev}: {n}")

with tabs[3]:
    if is_aml or is_admin:
        r1,r2,r3 = st.columns(3)
        _acct = r1.text_input("Account number",key="aml_nacct")
        _rule = r2.selectbox("Rule triggered",
            ["Cash transaction >KES 1M","Rapid movement of funds","Structuring","Cross-border transfer",
             "PEP transaction","Dormant account","Round-sum","High-risk jurisdiction","Other"],key="aml_nrule")
        _amt  = r3.number_input("Amount (KES M)",0.1,500.0,1.0,key="aml_namt")
        _score= st.slider("Risk score",1,100,65,key="aml_nscore")
        _notes= st.text_area("Description",height=60,key="aml_ndesc")
        if st.button("⚠️ Raise alert",key="aml_raise",type="primary"):
            if _acct.strip():
                all_a = json.loads((DATA/"aml_alerts.json").read_text())
                all_a.append({"id":f"AML{len(all_a)+1:05d}","account_number":_acct.strip(),
                               "customer_name":"","transaction_date":str(today),
                               "amount":_amt*1e6,"transaction_type":"Manual","rule_triggered":_rule,
                               "risk_score":_score,"risk_level":("High" if _score>=HIGH_THR else "Medium" if _score>=50 else "Low"),
                               "status":"Open","assigned_to":uname,"str_filed":False,"str_reference":"",
                               "notes":_notes,"created_at":str(today),"updated_at":str(today)})
                (DATA/"aml_alerts.json").write_text(json.dumps(all_a,indent=2))
                audit_log("AML_ALERT_RAISED",uname,f"Rule: {_rule}")
                st.cache_data.clear(); st.success("✅ Alert raised"); st.rerun()
            else: st.error("Account number required.")
    else: st.info("Alert creation available to Compliance team.")

with tabs[4]:
    st.markdown("**Suspicious Transaction Reports (STR) filed:**")
    if strs:
        str_rows=[{"ID":a["id"],"STR Reference":a.get("str_reference",""),"Account":a["account_number"][:18],
                    "Amount (M)":round(a["amount"]/1e6,2),"Rule":a["rule_triggered"][:30],"Date":a["transaction_date"][:10]}
                   for a in strs]
        st.dataframe(pd.DataFrame(str_rows),use_container_width=True,hide_index=True)
        st.caption("STRs must be filed with the Financial Reporting Centre (FRC) within 3 days of suspicion.")
    else: st.info("No STRs filed.")
