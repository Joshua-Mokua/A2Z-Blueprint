"""pages/73_channels.py — Channels Management & Digital Performance.
Dept: Digital Financial Services | KPIs: K069 K070 K071 | BSC: Auto-scored
Hardcoded: channel types (Physical/Digital), core channel list
Configurable: SLA targets per channel, adoption targets, active/inactive channels
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

require_access("channels_management")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_dfs   = any(x in role for x in ("digital","channel","it","operation","manager","head","director","dfs"))

CHANNEL_TYPES = ["Physical","Digital"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"channels_data.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    if not mc.exists(): return {}
    return json.loads(mc.read_text(encoding="utf-8")).get("channels",{})

def _save(data):
    (DATA/"channels_data.json").write_text(json.dumps(data,indent=2))
    st.cache_data.clear()

records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable",{})
sla_target     = conf_cfg.get("sla_uptime_target_pct",99.5)
adopt_target   = conf_cfg.get("digital_adoption_target_pct",40.0)
growth_target  = conf_cfg.get("txn_growth_target_pct",20.0)
comp_threshold = conf_cfg.get("complaint_threshold",50)
ch_cfg_list    = conf_cfg.get("channels",[])

digital_ch   = [r for r in records if r.get("channel_type","")=="Digital"]
physical_ch  = [r for r in records if r.get("channel_type","")=="Physical"]
degraded     = [r for r in records if r.get("status","") in ("Degraded","Under Maintenance","Offline")]
total_txns   = sum(r.get("transactions_today",0) for r in records)
digital_txns = sum(r.get("transactions_today",0) for r in digital_ch)
digital_pct  = round(digital_txns/max(total_txns,1)*100,1)
avg_uptime   = round(sum(r.get("uptime_pct_mtd",0) for r in records)/max(len(records),1),2)
sla_breach   = [r for r in records if r.get("uptime_pct_mtd",0)<r.get("sla_uptime_target",sla_target)]
total_comp   = sum(r.get("customer_complaints",0) for r in records)
txn_growth   = 15.3  # simulated — would come from CBS in production

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📲 Channels Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Digital Financial Services · K069 · K070 · K071</span></div>",
    unsafe_allow_html=True)

if degraded:
    st.error(f"🔴 {len(degraded)} channel(s) degraded or offline: {', '.join(r.get('channel_name','') for r in degraded)}")
if sla_breach:
    st.warning(f"⚠️ {len(sla_breach)} channel(s) below SLA uptime target")
if total_comp > comp_threshold:
    st.warning(f"⚠️ Total complaints ({total_comp}) above threshold ({comp_threshold})")

m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("Channels",          len(records))
m2.metric("Txns today",        f"{total_txns:,}")
m3.metric("Digital share",     f"{digital_pct}%",  delta_color="off" if digital_pct>=adopt_target else "inverse")
m4.metric("Avg uptime",        f"{avg_uptime:.2f}%",delta_color="off" if avg_uptime>=sla_target else "inverse")
m5.metric("Complaints",        total_comp,          delta_color="inverse" if total_comp>comp_threshold else "off")
m6.metric("Degraded",          len(degraded),       delta_color="inverse" if degraded else "off")

tabs = st.tabs(["📊 Overview","📋 Channel Detail","💳 Transactions","🔄 Incidents","⚙️ Config","📈 BSC"])

with tabs[0]:
    rows=[{"Channel":r.get("channel_name",""),"Type":r.get("channel_type",""),
            "Status":r.get("status",""),"Txns Today":f"{r.get('transactions_today',0):,}",
            "Value(M)":r.get("value_today_m",0),"Uptime MTD":f"{r.get('uptime_pct_mtd',0):.2f}%",
            "SLA":"✅" if r.get("uptime_pct_mtd",0)>=r.get("sla_uptime_target",sla_target) else "❌",
            "Error%":f"{r.get('error_rate_pct',0):.3f}%","Users Today":f"{r.get('active_users_today',0):,}",
            "Complaints":r.get("customer_complaints",0),"Revenue YTD(M)":r.get("revenue_ytd_m",0)}
           for r in sorted(records,key=lambda x:-x.get("transactions_today",0))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    c1,c2,c3 = st.columns(3)
    c1.caption(f"Digital: {digital_pct:.1f}% of total transactions")
    c2.caption(f"SLA: {len(records)-len(sla_breach)}/{len(records)} channels compliant")
    c3.caption(f"Total revenue YTD: KES {sum(r.get('revenue_ytd_m',0) for r in records):.1f}M")

with tabs[1]:
    sel_ch = st.selectbox("Select channel",[r.get("channel_name","") for r in records],key="ch_dsel")
    ch = next((r for r in records if r.get("channel_name","")==sel_ch),{})
    if ch:
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Status",    ch.get("status",""))
        c2.metric("Txns today",f"{ch.get('transactions_today',0):,}")
        c3.metric("Uptime MTD",f"{ch.get('uptime_pct_mtd',0):.2f}%")
        c4.metric("Error rate",f"{ch.get('error_rate_pct',0):.3f}%")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Value today",f"KES {ch.get('value_today_m',0):.1f}M")
        c2.metric("Active users",f"{ch.get('active_users_today',0):,}")
        c3.metric("Failed txns",ch.get("failed_transactions",0))
        c4.metric("Complaints",ch.get("customer_complaints",0))
        c1,c2 = st.columns(2)
        c1.metric("Revenue YTD",f"KES {ch.get('revenue_ytd_m',0):.1f}M")
        c2.metric("Cost YTD",f"KES {ch.get('cost_ytd_m',0):.1f}M")
        if ch.get("last_incident"):
            st.info(f"Last incident: {ch.get('last_incident','')[:10]}")
        if is_dfs or is_admin:
            new_status = st.selectbox("Update status",["Active","Under Maintenance","Degraded","Offline"],
                                     index=["Active","Under Maintenance","Degraded","Offline"].index(ch.get("status","Active")) if ch.get("status","Active") in ["Active","Under Maintenance","Degraded","Offline"] else 0,
                                     key="ch_upd_stat")
            if st.button("💾 Update channel status",key="ch_upd",type="primary"):
                all_r = _load()
                for rec in all_r:
                    if rec.get("channel_name","")==sel_ch: rec["status"]=new_status; break
                _save(all_r)
                audit_log("CHANNEL_STATUS_UPDATED",uname,f"{sel_ch}: {new_status}")
                _bsc_trigger(uname,"K070")
                st.success("✅ Updated"); st.rerun()

with tabs[2]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**Transactions by channel:**")
        txn_data={r.get("channel_name",""):r.get("transactions_today",0) for r in records}
        st.bar_chart(pd.DataFrame({"Txns":txn_data}))
    with c2:
        st.markdown("**Digital vs Physical:**")
        d_txns=sum(r.get("transactions_today",0) for r in digital_ch)
        p_txns=sum(r.get("transactions_today",0) for r in physical_ch)
        d_val =sum(r.get("value_today_m",0) for r in digital_ch)
        p_val =sum(r.get("value_today_m",0) for r in physical_ch)
        st.metric("Digital transactions",f"{d_txns:,} ({digital_pct:.1f}%)")
        st.metric("Physical transactions",f"{p_txns:,} ({100-digital_pct:.1f}%)")
        st.metric("Digital value",f"KES {d_val:.1f}M")
        st.metric("Physical value",f"KES {p_val:.1f}M")

with tabs[3]:
    st.markdown("**Log a channel incident:**")
    if is_dfs or is_admin:
        r1,r2 = st.columns(2)
        inc_ch = r1.selectbox("Channel",[r.get("channel_name","") for r in records],key="ch_inc_ch")
        inc_type= r2.selectbox("Type",["Downtime","Degraded Performance","High Error Rate","Security Alert","Other"],key="ch_inc_type")
        inc_desc= st.text_area("Description *",key="ch_inc_desc")
        if st.button("📝 Log incident",key="ch_inc_log",type="primary"):
            if inc_desc.strip():
                all_r = _load()
                for rec in all_r:
                    if rec.get("channel_name","")==inc_ch:
                        rec["last_incident"]=str(today)
                        if "Downtime" in inc_type: rec["status"]="Offline"
                        elif "Degraded" in inc_type: rec["status"]="Degraded"
                        break
                _save(all_r)
                audit_log("CHANNEL_INCIDENT",uname,f"{inc_ch}: {inc_type}")
                _bsc_trigger(uname,"K070")
                st.success("✅ Incident logged"); st.rerun()

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: Channel types (Physical/Digital), core channel definitions")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("channels",{}).get("configurable",{})
        c1,c2,c3 = st.columns(3)
        new_sla    = c1.number_input("SLA uptime target (%)",90.0,100.0,float(cfg_m.get("sla_uptime_target_pct",99.5)),0.1,key="ch_cfg_sla")
        new_adopt  = c2.number_input("Digital adoption target (%)",10.0,100.0,float(cfg_m.get("digital_adoption_target_pct",40.0)),1.0,key="ch_cfg_adopt")
        new_growth = c3.number_input("Txn growth target (%)",0.0,100.0,float(cfg_m.get("txn_growth_target_pct",20.0)),1.0,key="ch_cfg_growth")
        new_comp   = st.number_input("Complaint threshold",1,500,int(cfg_m.get("complaint_threshold",50)),key="ch_cfg_comp")
        st.markdown("**Channel SLA configuration:**")
        ch_cfg = cfg_m.get("channels",[])
        for c in ch_cfg:
            c1,c2,c3 = st.columns([3,2,1])
            c1.markdown(f"**{c.get('name','')}** — {c.get('type','')}")
            new_ch_sla = c2.number_input(f"SLA %",90.0,100.0,float(c.get("sla",99.5)),0.1,key=f"ch_sla_{c.get('id','')}")
            c.update({"sla":new_ch_sla,"active":c3.checkbox("Active",c.get("active",True),key=f"ch_act_{c.get('id','')}") })
        if st.button("💾 Save channels config",key="ch_cfg_save",type="primary"):
            cfg_m.update({"sla_uptime_target_pct":new_sla,"digital_adoption_target_pct":new_adopt,
                          "txn_growth_target_pct":new_growth,"complaint_threshold":new_comp,"channels":ch_cfg})
            mc["channels"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("CHANNELS_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Configuration available to Admin only.")

with tabs[5]:
    bsc_rows=[
        {"KPI":"K069 — Digital Adoption","Target":f"> {adopt_target}%","Actual":f"{digital_pct:.1f}%","Status":"🟢" if digital_pct>=adopt_target else "🟡","Weight":"10%"},
        {"KPI":"K070 — Channel Uptime","Target":f"> {sla_target}%","Actual":f"{avg_uptime:.2f}%","Status":"🟢" if avg_uptime>=sla_target else "🟡","Weight":"8%"},
        {"KPI":"K071 — Txn Growth","Target":f"> {growth_target}%","Actual":f"{txn_growth:.1f}%","Status":"🟢" if txn_growth>=growth_target else "🟡","Weight":"8%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="ch_bsc",type="primary"):
        _bsc_trigger(uname,"K069"); st.success("✅ BSC updated"); st.rerun()
