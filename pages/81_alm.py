"""pages/81_alm.py — ALM & Liquidity Management.
Daily liquidity gap, funding concentration, ALCO actions.
Dept: Treasury | KPIs: K094 K095 K096 K097
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

require_access("alm_liquidity")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_treas = any(x in role for x in ("treasury","alm","alco","cfo","risk","finance","manager","head","director","chief"))

TENORS = ["Sight","1-7d","8-30d","1-3m","3-6m","6-12m","1-3y","3-5y","5y+"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load_dict(DATA/"alm_liquidity.json", table_map={'gap_analysis': 'alm_gap_analysis', 'funding_sources': 'alm_funding_sources', 'alco_meetings': 'alm_alco_meetings', 'contingency_plans': 'alm_contingency_plans'})

def _save(data):
    """Save nested-dict module data — JSON only (PG nested writes are explicit per sub-table)."""
    (DATA/"alm_liquidity.json").write_text(json.dumps(data,indent=2,default=str))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("alm_liquidity",{}) if mc.exists() else {}


data = _load()
gaps     = data.get("gap_analysis",[])
funding  = data.get("funding_sources",[])
alco_m   = data.get("alco_meetings",[])
cfp      = data.get("contingency_plans",[])
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable",{})
conc_alert    = conf_cfg.get("concentration_alert_pct",25)
buffer_target = conf_cfg.get("liquidity_buffer_target_kes_b",30)

# Latest gap analysis
latest_date = max((g.get("metric_date","") for g in gaps),default="")
latest_gaps = [g for g in gaps if g.get("metric_date","")==latest_date]
total_gap_b = sum(g.get("gap_kes",0) for g in latest_gaps)/1e9
liq_buffer_b= sum(g.get("gap_kes",0) for g in latest_gaps if g.get("tenor_bucket","") in ("Sight","1-7d","8-30d"))/1e9

# Concentration
top_source = max(funding, key=lambda x:x.get("concentration_pct",0)) if funding else {}
top_conc   = top_source.get("concentration_pct",0)

# ALCO action items
total_actions  = sum(m.get("action_items",0) for m in alco_m)
closed_actions = sum(m.get("actions_closed",0) for m in alco_m)
actions_pct    = round(closed_actions/max(total_actions,1)*100,1)

# Stress test coverage
tested_cfp     = sum(1 for c in cfp if c.get("test_result")=="Pass")
stress_pct     = round(tested_cfp/max(len(cfp),1)*100,1)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>💧 ALM & Liquidity Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Treasury · K094-K097</span></div>",
    unsafe_allow_html=True)

if top_conc > conc_alert:
    st.warning(f"⚠️ Funding concentration: {top_source.get('source','')} at {top_conc}% — above {conc_alert}% threshold")
if liq_buffer_b < buffer_target:
    st.warning(f"⚠️ Short-tenor liquidity buffer KES {liq_buffer_b:.1f}B below target KES {buffer_target}B")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Liquidity buffer", f"KES {liq_buffer_b:.1f}B", delta_color="off" if liq_buffer_b>=buffer_target else "inverse")
m2.metric("Total gap",        f"KES {total_gap_b:.1f}B")
m3.metric("Top source conc.", f"{top_conc}%", delta_color="off" if top_conc<=conc_alert else "inverse")
m4.metric("ALCO actions",     f"{closed_actions}/{total_actions}", delta_color="off" if actions_pct>=80 else "inverse")
m5.metric("Stress coverage",  f"{stress_pct}%")

tabs = st.tabs(["📊 Gap Analysis","💰 Funding","🏛️ ALCO","🚨 Contingency","➕ New Snapshot","⚙️ Config","📈 BSC"])

with tabs[0]:
    if latest_gaps:
        st.markdown(f"**Gap analysis — {latest_date}:**")
        rows = [{"Tenor":g.get("tenor_bucket",""),
                  "Assets (B)":round(g.get("assets_kes",0)/1e9,2),
                  "Liabilities (B)":round(g.get("liabilities_kes",0)/1e9,2),
                  "Gap (B)":round(g.get("gap_kes",0)/1e9,2),
                  "Cumulative (B)":round(g.get("cumulative_gap_kes",0)/1e9,2),
                  "Stress factor":g.get("stress_factor",0)}
                 for g in sorted(latest_gaps,key=lambda x:TENORS.index(x.get("tenor_bucket","Sight")) if x.get("tenor_bucket","") in TENORS else 99)]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.bar_chart(pd.DataFrame({"Gap (KES B)":{r["Tenor"]:r["Gap (B)"] for r in rows}}))

with tabs[1]:
    rows = [{"Source":f.get("source",""),"Amount (B)":f.get("amount_kes_b",0),
              "Concentration":f"{f.get('concentration_pct',0)}%",
              "Avg tenor (d)":f.get("tenor_avg_days",0),
              "Rate":f"{f.get('rate_pct',0)}%"} for f in funding]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    st.bar_chart(pd.DataFrame({"Concentration %":{f.get("source",""):f.get("concentration_pct",0) for f in funding}}))

with tabs[2]:
    if alco_m:
        rows = [{"Date":m.get("meeting_date","")[:10],"Agenda items":m.get("agenda_items",0),
                  "Decisions":m.get("decisions_taken",0),
                  "Actions":f"{m.get('actions_closed',0)}/{m.get('action_items',0)}",
                  "Attendance":f"{m.get('attendance_pct',0)}%",
                  "Papers on time":"✅" if m.get("papers_circulated_on_time") else "❌"}
                 for m in alco_m]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[3]:
    st.markdown("**Contingency Funding Plans:**")
    for c in cfp:
        result = c.get("test_result","Not tested")
        icon   = "✅" if result=="Pass" else "🟡" if result=="In Progress" else "❌"
        with st.expander(f"{icon} {c.get('id','')} — {c.get('trigger','')[:50]}"):
            st.markdown(f"**Action:** {c.get('action','')}")
            st.markdown(f"**Last tested:** {c.get('tested_date','—')}")
            st.markdown(f"**Result:** {result}")
            if (is_treas or is_admin) and result not in ("Pass",):
                if st.button("✅ Mark test passed",key=f"alm_cfp_{c['id']}",type="primary"):
                    all_data = _load()
                    for plan in all_data.get("contingency_plans",[]):
                        if plan["id"]==c["id"]:
                            plan["test_result"]="Pass"
                            plan["tested_date"]=str(today)
                            break
                    _save(all_data); audit_log("CFP_TESTED",uname,c["id"]); _bsc_trigger(uname,"K096")
                    st.success("✅ Test recorded"); st.rerun()

with tabs[4]:
    if is_treas or is_admin:
        st.markdown("**Add gap snapshot for today:**")
        c1,c2,c3 = st.columns(3)
        sel_tenor = c1.selectbox("Tenor",TENORS,key="alm_n_t")
        new_a     = c2.number_input("Assets (KES B)",0.0,1000.0,50.0,0.1,key="alm_n_a")
        new_l     = c3.number_input("Liabilities (KES B)",0.0,1000.0,50.0,0.1,key="alm_n_l")
        if st.button("💾 Save snapshot",key="alm_n_save",type="primary"):
            all_data = _load()
            all_data.setdefault("gap_analysis",[]).insert(0,{
                "id":f"ALM{len(gaps)+1:05d}","metric_date":str(today),
                "tenor_bucket":sel_tenor,
                "assets_kes":new_a*1e9,"liabilities_kes":new_l*1e9,
                "gap_kes":(new_a-new_l)*1e9,"cumulative_gap_kes":(new_a-new_l)*1e9,
                "tenor_days":0,"stress_factor":0.1
            })
            _save(all_data); audit_log("ALM_SNAPSHOT",uname,sel_tenor); _bsc_trigger(uname,"K094")
            st.success("✅ Snapshot saved"); st.rerun()

with tabs[5]:
    if is_admin:
        st.info("ℹ️ Hardcoded: Tenor buckets, ALCO 75% min attendance, Basel III + CBK framework")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("alm_liquidity",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_conc = c1.number_input("Concentration alert (%)",10,50,int(cfg_m.get("concentration_alert_pct",25)),key="alm_c_conc")
        new_buf  = c2.number_input("Buffer target (KES B)",10,200,int(cfg_m.get("liquidity_buffer_target_kes_b",30)),key="alm_c_buf")
        if st.button("💾 Save",key="alm_cfg_save",type="primary"):
            cfg_m.update({"concentration_alert_pct":new_conc,"liquidity_buffer_target_kes_b":new_buf})
            mc["alm_liquidity"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("ALM_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

with tabs[6]:
    bsc_rows=[
        {"KPI":"K094 — Liquidity Buffer","Target":f"KES {buffer_target}B","Actual":f"KES {liq_buffer_b:.1f}B","Status":"🟢" if liq_buffer_b>=buffer_target else "🟡","Weight":"10%"},
        {"KPI":"K095 — Funding Concentration","Target":f"< {conc_alert}%","Actual":f"{top_conc}%","Status":"🟢" if top_conc<=conc_alert else "🟡","Weight":"8%"},
        {"KPI":"K096 — Stress Test Coverage","Target":"> 80%","Actual":f"{stress_pct}%","Status":"🟢" if stress_pct>=80 else "🟡","Weight":"5%"},
        {"KPI":"K097 — ALCO Actions Closed","Target":"> 80%","Actual":f"{actions_pct}%","Status":"🟢" if actions_pct>=80 else "🟡","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="alm_bsc",type="primary"):
        _bsc_trigger(uname,"K094"); st.success("✅ BSC updated"); st.rerun()
