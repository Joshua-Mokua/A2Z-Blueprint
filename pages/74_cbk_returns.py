"""pages/74_cbk_returns.py — CBK Returns Centre.
All 47 prudential returns in one place. Submit, track, audit.
Dept: Compliance | KPIs: K072 K073 K074
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("cbk_returns")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_comp  = any(x in role for x in ("compliance","finance","treasury","risk","manager","head","director","chief","md","ceo"))

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"cbk_returns.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return json.loads(mc.read_text(encoding="utf-8")).get("cbk_returns",{}) if mc.exists() else {}

def _save(data):
    (DATA/"cbk_returns.json").write_text(json.dumps(data, indent=2))
    st.cache_data.clear()

records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable", {})
warn_days= conf_cfg.get("early_warning_days", 7)
min_acc  = conf_cfg.get("minimum_accuracy_pct", 95)

submitted_r = [r for r in records if r.get("submitted")]
on_time_r   = [r for r in submitted_r if r.get("on_time")]
overdue_r   = [r for r in records if r.get("status")=="Overdue"]
upcoming_r  = [r for r in records if r.get("status")=="Pending" and r.get("due_date","")<=str(today+timedelta(days=warn_days))]
findings    = sum(r.get("regulatory_findings",0) for r in submitted_r)
findings_cl = sum(r.get("findings_closed",0) for r in submitted_r)
on_time_pct = round(len(on_time_r)/max(len(submitted_r),1)*100,1)
acc_avg     = round(sum(r.get("accuracy_score",0) for r in submitted_r)/max(len(submitted_r),1),1)
findings_pct= round(findings_cl/max(findings,1)*100,1)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📊 CBK Returns Centre</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Compliance · 47 returns · K072 · K073 · K074</span></div>",
    unsafe_allow_html=True)

if overdue_r:
    st.error(f"🔴 {len(overdue_r)} return(s) OVERDUE — late filing penalty KES 50K each")
if upcoming_r:
    st.warning(f"⚠️ {len(upcoming_r)} return(s) due within {warn_days} days")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total returns",  len(records))
m2.metric("On-time filed",  f"{on_time_pct}%", delta_color="off" if on_time_pct>=95 else "inverse")
m3.metric("Accuracy",       f"{acc_avg}%",     delta_color="off" if acc_avg>=min_acc else "inverse")
m4.metric("Overdue",        len(overdue_r),    delta_color="inverse" if overdue_r else "off")
m5.metric("Findings closed", f"{findings_cl}/{findings}")

tabs = st.tabs(["📋 Returns Calendar","🔴 Overdue & Upcoming","➕ Submit Return","🔍 Findings","📊 Analytics","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    ffreq = f1.selectbox("Frequency",["All","Daily","Monthly","Quarterly","Annual"],key="cbk_freq")
    fstat = f2.selectbox("Status",["All","Submitted","Pending","Overdue"],key="cbk_stat")
    fdept = f3.selectbox("Department",["All"]+sorted(set(r.get("department","") for r in records)),key="cbk_dept")
    vis = [r for r in records
           if (ffreq=="All" or r.get("frequency","")==ffreq)
           and (fstat=="All" or r.get("status","")==fstat)
           and (fdept=="All" or r.get("department","")==fdept)]
    rows = [{"Code":r.get("return_code",""),"Return":r.get("return_name","")[:35],
              "Freq":r.get("frequency",""),"Period":r.get("period",""),
              "Due":r.get("due_date","")[:10],"Status":r.get("status",""),
              "On Time":"✅" if r.get("on_time") else "❌" if r.get("submitted") else "⏳",
              "Accuracy":f"{r.get('accuracy_score',0)}%" if r.get("submitted") else "—",
              "Findings":r.get("regulatory_findings",0),"Dept":r.get("department","")[:12]}
             for r in sorted(vis,key=lambda x:x.get("due_date",""))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[1]:
    if overdue_r:
        st.markdown("**🔴 OVERDUE — file immediately:**")
        for r in overdue_r[:20]:
            with st.expander(f"🔴 {r.get('return_code','')} — {r.get('return_name','')} ({r.get('period','')})"):
                c1,c2,c3 = st.columns(3)
                c1.metric("Due date",r.get("due_date","")[:10])
                days_late = (today - date.fromisoformat(r.get("due_date","")[:10])).days
                c2.metric("Days late",days_late,delta_color="inverse")
                c3.metric("Penalty",f"KES {50000*days_late:,}")
                if is_comp and st.button("Submit now",key=f"cbk_sub_{r['id']}",type="primary"):
                    all_r = _load()
                    for rec in all_r:
                        if rec["id"]==r["id"]:
                            rec["submitted"]=True; rec["submitted_date"]=str(today); rec["on_time"]=False
                            rec["submitted_by"]=uname; rec["status"]="Submitted"; rec["accuracy_score"]=90
                            break
                    _save(all_r); audit_log("CBK_RETURN_SUBMITTED",uname,r["return_code"])
                    _bsc_trigger(uname,"K072")
                    st.success("✅ Submitted (late)"); st.rerun()
    if upcoming_r:
        st.markdown(f"**⚠️ Upcoming within {warn_days} days:**")
        upc_rows = [{"Code":r.get("return_code",""),"Name":r.get("return_name","")[:30],
                      "Due":r.get("due_date","")[:10],"Days left":(date.fromisoformat(r.get("due_date","")[:10])-today).days,
                      "Department":r.get("department","")} for r in upcoming_r]
        st.dataframe(pd.DataFrame(upc_rows),use_container_width=True,hide_index=True)
    if not overdue_r and not upcoming_r:
        st.success("✅ No overdue or upcoming returns.")

with tabs[2]:
    if is_comp or is_admin:
        pending_subs = [r for r in records if r.get("status") in ("Pending","Overdue")]
        if pending_subs:
            sel = st.selectbox("Select return to submit",
                              [f"{r.get('return_code','')} — {r.get('return_name','')[:30]} ({r.get('period','')})" for r in pending_subs[:30]],
                              key="cbk_sub_sel")
            sel_id = sel.split(" — ")[0]
            r = next((x for x in pending_subs if x.get("return_code","")==sel_id),{})
            if r:
                st.markdown(f"**Period:** {r.get('period','')} | **Due:** {r.get('due_date','')[:10]} | **Frequency:** {r.get('frequency','')}")
                acc_score = st.slider("Accuracy score (%)", 50, 100, 95, key="cbk_sub_acc")
                queries  = st.number_input("Anticipated queries", 0, 10, 0, key="cbk_sub_q")
                preparer = st.text_input("Preparer", uname, key="cbk_sub_prep")
                reviewer = st.text_input("Reviewer", key="cbk_sub_rev")
                approver = st.text_input("Approver", key="cbk_sub_app")
                if st.button("📤 Submit to CBK",key="cbk_sub_btn",type="primary"):
                    all_r = _load()
                    on_time = today <= date.fromisoformat(r.get("due_date","")[:10])
                    for rec in all_r:
                        if rec["id"]==r["id"]:
                            rec["submitted"]=True; rec["submitted_date"]=str(today)
                            rec["on_time"]=on_time; rec["submitted_by"]=uname
                            rec["status"]="Submitted"; rec["accuracy_score"]=acc_score
                            rec["queries_raised"]=queries; rec["preparer"]=preparer
                            rec["reviewer"]=reviewer; rec["approver"]=approver
                            break
                    _save(all_r); audit_log("CBK_RETURN_SUBMITTED",uname,r.get("return_code",""))
                    _bsc_trigger(uname,"K072")
                    st.success(f"✅ {sel_id} submitted ({'on time' if on_time else 'late'})"); st.rerun()
        else:
            st.success("✅ No pending returns to submit.")

with tabs[3]:
    with_findings = [r for r in records if r.get("regulatory_findings",0)>0]
    if with_findings:
        st.markdown(f"**Returns with regulatory findings ({len(with_findings)}):**")
        for r in with_findings[:20]:
            ratio = f"{r.get('findings_closed',0)}/{r.get('regulatory_findings',0)}"
            with st.expander(f"📌 {r.get('return_code','')} — {r.get('return_name','')[:30]} | Findings: {ratio}"):
                if r.get("findings_closed",0) < r.get("regulatory_findings",0):
                    if st.button("Close finding",key=f"cbk_fc_{r['id']}"):
                        all_r = _load()
                        for rec in all_r:
                            if rec["id"]==r["id"]:
                                rec["findings_closed"] = min(rec.get("findings_closed",0)+1,rec.get("regulatory_findings",0))
                                break
                        _save(all_r); audit_log("CBK_FINDING_CLOSED",uname,r.get("return_code",""))
                        _bsc_trigger(uname,"K074")
                        st.success("✅ Finding closed"); st.rerun()
    else:
        st.success("✅ No outstanding regulatory findings.")

with tabs[4]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**By department:**")
        by_dept = defaultdict(lambda:{"total":0,"on_time":0})
        for r in submitted_r:
            d = r.get("department","Other")
            by_dept[d]["total"] += 1
            if r.get("on_time"): by_dept[d]["on_time"] += 1
        rows = [{"Department":d,"Submitted":v["total"],"On Time":v["on_time"],
                  "Rate":f"{v['on_time']/max(v['total'],1)*100:.0f}%"}
                for d,v in sorted(by_dept.items())]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with c2:
        st.markdown("**By frequency:**")
        by_freq = defaultdict(lambda:{"total":0,"on_time":0})
        for r in submitted_r:
            f = r.get("frequency","Other")
            by_freq[f]["total"] += 1
            if r.get("on_time"): by_freq[f]["on_time"] += 1
        rows = [{"Frequency":f,"Submitted":v["total"],"On Time":v["on_time"],
                  "Rate":f"{v['on_time']/max(v['total'],1)*100:.0f}%"}
                for f,v in by_freq.items()]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[5]:
    if is_admin:
        st.info("ℹ️ Hardcoded: 47 CBK returns, frequencies, late filing penalty KES 50K, regulator details")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("cbk_returns",{}).get("configurable",{})
        c1,c2,c3 = st.columns(3)
        new_warn = c1.number_input("Early warning days",1,30,int(cfg_m.get("early_warning_days",7)),key="cbk_cfg_warn")
        new_acc  = c2.number_input("Min accuracy (%)",50,100,int(cfg_m.get("minimum_accuracy_pct",95)),key="cbk_cfg_acc")
        new_email= c3.text_input("Escalation email",cfg_m.get("escalation_email",""),key="cbk_cfg_email")
        if st.button("💾 Save config",key="cbk_cfg_save",type="primary"):
            cfg_m.update({"early_warning_days":new_warn,"minimum_accuracy_pct":new_acc,"escalation_email":new_email})
            mc["cbk_returns"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("CBK_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Admin only.")

with tabs[6]:
    bsc_rows=[
        {"KPI":"K072 — On-time filing","Target":"> 95%","Actual":f"{on_time_pct}%","Status":"🟢" if on_time_pct>=95 else "🔴","Weight":"10%"},
        {"KPI":"K073 — Accuracy","Target":f"> {min_acc}%","Actual":f"{acc_avg}%","Status":"🟢" if acc_avg>=min_acc else "🟡","Weight":"8%"},
        {"KPI":"K074 — Findings closed","Target":"> 90%","Actual":f"{findings_pct}%","Status":"🟢" if findings_pct>=90 else "🟡","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="cbk_bsc",type="primary"):
        _bsc_trigger(uname,"K072"); st.success("✅ BSC updated"); st.rerun()
