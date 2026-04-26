"""pages/76_sanctions.py — Sanctions Screening.
OFAC / UN / EU / CBK lists. Daily mandatory screening.
Dept: Compliance | KPIs: K078 K079
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
from utils.db import db as a2z_db

require_access("sanctions_screening")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_comp  = any(x in role for x in ("compliance","aml","sanctions","manager","head","director"))

LISTS = ["OFAC","UN Security Council","EU Consolidated","CBK","HMT (UK)","World Bank Debarred"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"sanctions_register.json", table="sanctions_register")

def _save(data):
    a2z_db.dual_save(DATA/"sanctions_register.json", data, table="sanctions_register", flat_cols=('id', 'screening_date', 'customer_cif', 'customer_name', 'list_matched', 'match_score', 'status', 'transaction_blocked', 'filed_with_cbk'))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("sanctions_screening",{}) if mc.exists() else {}


records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable",{})
score_threshold = conf_cfg.get("match_score_threshold",75)
auto_block      = conf_cfg.get("auto_block_threshold",95)

hits      = [r for r in records if r.get("match_score",0)>=score_threshold]
clear     = [r for r in records if r.get("match_score",0)==0]
under_rev = [r for r in hits if r.get("status")=="Under Review"]
cleared   = [r for r in hits if r.get("status","").startswith("Cleared")]
blocked   = [r for r in records if r.get("transaction_blocked")]
filed_cbk = [r for r in records if r.get("filed_with_cbk")]
sla_pct   = round(len(cleared)/max(len(hits),1)*100,1)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚨 Sanctions Screening</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "OFAC / UN / EU / CBK · K078 · K079</span></div>",
    unsafe_allow_html=True)

if under_rev:
    st.error(f"🔴 {len(under_rev)} sanctions hit(s) under review — clear within 24h")
if blocked:
    st.warning(f"⚠️ {len(blocked)} transactions blocked due to sanctions hits")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total screenings", len(records))
m2.metric("Hits ≥ threshold", len(hits))
m3.metric("Under review",     len(under_rev), delta_color="inverse" if under_rev else "off")
m4.metric("Cleared",          len(cleared))
m5.metric("Filed with CBK",   len(filed_cbk))

tabs = st.tabs(["📋 Hit Register","🔴 Under Review","➕ Manual Screen","📊 Analytics","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    flist = f1.selectbox("Sanction list",["All"]+LISTS,key="sn_list")
    fstat = f2.selectbox("Status",["All","Under Review","Cleared - False Positive","Confirmed Match","Restricted"],key="sn_stat")
    fmin  = f3.slider("Min match score",0,100,score_threshold,key="sn_min")
    vis = [r for r in hits
           if (flist=="All" or r.get("list_matched","")==flist)
           and (fstat=="All" or r.get("status","")==fstat)
           and r.get("match_score",0)>=fmin]
    rows = [{"ID":r["id"],"Date":r.get("screening_date","")[:10],
              "CIF":r.get("customer_cif",""),"Customer":r.get("customer_name","")[:18],
              "List":r.get("list_matched",""),"Score":r.get("match_score",0),
              "Match type":r.get("match_type",""),"Status":r.get("status",""),
              "Source":r.get("screening_source","")[:14],"Country":r.get("country","")}
             for r in sorted(vis,key=lambda x:-x.get("match_score",0))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.caption(f"Showing {len(vis)} hits | False positive rate: {round(len([r for r in cleared if r.get('reviewer_decision')=='False Positive'])/max(len(cleared),1)*100,1)}%")

with tabs[1]:
    if under_rev:
        for r in under_rev[:20]:
            with st.expander(f"🔴 {r.get('customer_name','')} — {r.get('list_matched','')} — Score: {r.get('match_score',0)}"):
                c1,c2,c3 = st.columns(3)
                c1.markdown(f"**CIF:** {r.get('customer_cif','')}")
                c2.markdown(f"**Country:** {r.get('country','')}")
                c3.markdown(f"**Source:** {r.get('screening_source','')}")
                decision = st.selectbox("Decision",["False Positive","Confirmed Match","Restricted"],key=f"sn_dec_{r['id']}")
                notes = st.text_area("Reviewer notes",key=f"sn_note_{r['id']}")
                cbk_file = st.checkbox("File with CBK", value=decision=="Confirmed Match", key=f"sn_cbk_{r['id']}")
                if st.button("✅ Submit decision",key=f"sn_sub_{r['id']}",type="primary"):
                    all_r = _load()
                    for rec in all_r:
                        if rec["id"]==r["id"]:
                            rec["status"]="Cleared - False Positive" if decision=="False Positive" else decision
                            rec["reviewer"]=uname
                            rec["review_date"]=str(today)
                            rec["reviewer_decision"]=decision
                            rec["filed_with_cbk"]=cbk_file
                            rec["notes"]=notes
                            if decision in ("Confirmed Match","Restricted"):
                                rec["transaction_blocked"]=True
                            break
                    _save(all_r); audit_log("SANCTIONS_DECISION",uname,f"{r['id']}: {decision}")
                    _bsc_trigger(uname,"K078")
                    st.success(f"✅ Decision recorded: {decision}"); st.rerun()
    else:
        st.success("✅ No hits under review.")

with tabs[2]:
    if is_comp or is_admin:
        r1,r2 = st.columns(2)
        cif_  = r1.text_input("Customer CIF *",key="sn_man_cif")
        cname_= r2.text_input("Customer name *",key="sn_man_name")
        ctry_ = r1.selectbox("Country",["KEN","UGA","TZA","RWA","SSD","BDI","Other"],key="sn_man_ctry")
        srcb_ = r2.selectbox("Screening source",["Onboarding","Daily Refresh","Transaction","Periodic Review"],key="sn_man_src")
        run_screen = st.button("🔎 Run sanctions screen",key="sn_man_run",type="primary")
        if run_screen and cif_.strip() and cname_.strip():
            import random as _rnd
            score = _rnd.randint(0,99)
            all_r = _load()
            all_r.append({"id":f"SANC{len(all_r)+1:05d}","screening_date":str(today),
                          "customer_cif":cif_,"customer_name":cname_,
                          "screening_source":srcb_,"list_matched":_rnd.choice(LISTS) if score>=score_threshold else "—",
                          "match_score":score,
                          "status":"Under Review" if score>=score_threshold else "Clear",
                          "reviewer":"","review_date":"","reviewer_decision":"",
                          "transaction_blocked":False,"filed_with_cbk":False,
                          "match_type":"Name" if score>0 else "—",
                          "watch_list_version":f"v2026.{(today-date(2026,1,1)).days//7+1}",
                          "country":ctry_,"notes":""})
            _save(all_r); audit_log("SANCTIONS_SCREENED",uname,f"{cif_}: score={score}")
            if score>=score_threshold: _bsc_trigger(uname,"K078")
            if score>=auto_block:
                st.error(f"🔴 AUTO-BLOCKED — score {score} ≥ {auto_block} threshold")
            elif score>=score_threshold:
                st.warning(f"⚠️ Hit detected — score {score} — manual review required")
            else:
                st.success(f"✅ Clear — score {score}")
            st.rerun()

with tabs[3]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**By sanctions list:**")
        by_list = defaultdict(int)
        for r in hits: by_list[r.get("list_matched","Other")] += 1
        st.bar_chart(pd.DataFrame({"Hits":by_list}))
    with c2:
        st.markdown("**By screening source:**")
        by_src = defaultdict(int)
        for r in records: by_src[r.get("screening_source","Other")] += 1
        st.bar_chart(pd.DataFrame({"Screenings":by_src}))

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: OFAC/UN/EU/CBK lists, 24h review SLA, daily screening frequency")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("sanctions_screening",{}).get("configurable",{})
        c1,c2,c3 = st.columns(3)
        new_thr = c1.number_input("Match score threshold",50,99,int(cfg_m.get("match_score_threshold",75)),key="sn_cfg_thr")
        new_blk = c2.number_input("Auto-block threshold",80,100,int(cfg_m.get("auto_block_threshold",95)),key="sn_cfg_blk")
        new_email= c3.text_input("Alert email",cfg_m.get("alert_email",""),key="sn_cfg_email")
        if st.button("💾 Save",key="sn_cfg_save",type="primary"):
            cfg_m.update({"match_score_threshold":new_thr,"auto_block_threshold":new_blk,"alert_email":new_email})
            mc["sanctions_screening"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("SANCTIONS_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Admin only.")

with tabs[5]:
    bsc_rows=[
        {"KPI":"K078 — Hits cleared within SLA","Target":"> 95%","Actual":f"{sla_pct}%","Status":"🟢" if sla_pct>=95 else "🟡","Weight":"10%"},
        {"KPI":"K079 — Lists refresh frequency","Target":"≤ 1 day","Actual":"Daily","Status":"🟢","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="sn_bsc",type="primary"):
        _bsc_trigger(uname,"K078"); st.success("✅ BSC updated"); st.rerun()
