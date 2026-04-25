"""pages/72_observability.py — System Observability & Monitoring.
Dept: IT & Digital | KPIs: K066 K067 K068 | BSC: Auto-scored
Hardcoded: CBK critical systems list, alert levels (OK/WARN/CRIT)
Configurable: SLA targets, monitoring systems, alert thresholds, MTTR target
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

require_access("observability")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_it    = any(x in role for x in ("it","tech","digital","system","infrastructure","devops","operation","manager","head","director"))

CBK_CRITICAL = ["Core Banking (FlexCube)","Mobile Banking App","RTGS Gateway","ATM Network","SWIFT Interface","Card Management System"]
ALERT_LEVELS = ["OK","WARN","CRIT"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

@st.cache_data(ttl=15)
def _load():
    p = DATA/"observability_metrics.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    if not mc.exists(): return {}
    return json.loads(mc.read_text(encoding="utf-8")).get("observability",{})

def _save(data):
    (DATA/"observability_metrics.json").write_text(json.dumps(data,indent=2))
    st.cache_data.clear()

records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable",{})
sla_target  = conf_cfg.get("sla_uptime_target_pct",99.5)
mttr_target = conf_cfg.get("mttr_target_hours",4.0)
inc_target  = conf_cfg.get("incident_target_count",5)
mon_systems = conf_cfg.get("monitoring_systems",[])

crit_m    = [r for r in records if r.get("status")=="CRIT"]
warn_m    = [r for r in records if r.get("status")=="WARN"]
ok_m      = [r for r in records if r.get("status")=="OK"]
avg_uptime= round(sum(r.get("uptime_30d_pct",0) for r in records)/max(len(records),1),2)
total_inc = sum(r.get("incidents_30d",0) for r in records)
cbk_crit  = [r for r in crit_m if r.get("system","") in CBK_CRITICAL]

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📡 System Observability</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "IT & Digital · K066 · K067 · K068</span></div>",
    unsafe_allow_html=True)

if cbk_crit:
    st.error(f"🔴 CRITICAL: {len(cbk_crit)} CBK-critical system(s) down — escalate to IT Manager and CEO immediately")
elif crit_m:
    st.error(f"🔴 {len(crit_m)} system(s) CRITICAL")
if warn_m:
    st.warning(f"🟡 {len(warn_m)} system(s) WARNING")
if avg_uptime < sla_target:
    st.error(f"🔴 Average uptime {avg_uptime}% below SLA target {sla_target}%")

m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("Systems",          len(set(r.get("system","") for r in records)))
m2.metric("🔴 Critical",      len(crit_m),  delta_color="inverse" if crit_m else "off")
m3.metric("🟡 Warning",       len(warn_m),  delta_color="inverse" if warn_m else "off")
m4.metric("🟢 OK",            len(ok_m))
m5.metric("Avg uptime (30d)", f"{avg_uptime:.2f}%", delta_color="off" if avg_uptime>=sla_target else "inverse")
m6.metric("Incidents (30d)",  total_inc,    delta_color="inverse" if total_inc>inc_target else "off")

tabs = st.tabs(["🖥️ Live Dashboard","🚨 Active Alerts","📊 System Health","📝 Incident Log","⚙️ Config","📈 BSC"])

with tabs[0]:
    systems = sorted(set(r.get("system","") for r in records))
    for sys_name in systems:
        sys_metrics = [r for r in records if r.get("system","")==sys_name]
        sys_status  = "🔴 CRITICAL" if any(r.get("status")=="CRIT" for r in sys_metrics) else                       "🟡 WARNING"  if any(r.get("status")=="WARN" for r in sys_metrics) else "🟢 OK"
        is_cbk_crit = sys_name in CBK_CRITICAL
        cbk_badge   = " 🏦 CBK Critical" if is_cbk_crit else ""
        with st.expander(f"{sys_status}{cbk_badge} — {sys_name}", expanded=any(r.get("status")!="OK" for r in sys_metrics)):
            uptime = round(sum(r.get("uptime_30d_pct",0) for r in sys_metrics)/max(len(sys_metrics),1),2)
            inc    = sum(r.get("incidents_30d",0) for r in sys_metrics)
            c0,c1,c2,c3 = st.columns(4)
            c0.metric("Uptime (30d)", f"{uptime:.2f}%", delta_color="off" if uptime>=sla_target else "inverse")
            c0.metric("Incidents",    inc,              delta_color="off")
            for j, m in enumerate(sys_metrics[:3], 1):
                col = [c1,c2,c3][j-1]
                status_icon = "🔴" if m.get("status")=="CRIT" else "🟡" if m.get("status")=="WARN" else "🟢"
                col.metric(f"{status_icon} {m.get('metric','')}",
                           f"{m.get('current_value',0):.1f}{m.get('unit','')}",
                           delta=f"Threshold: {m.get('threshold_crit',0):.1f}")

with tabs[1]:
    all_alerts = crit_m + warn_m
    if all_alerts:
        rows=[{"System":r.get("system",""),"Metric":r.get("metric",""),
                "Value":f"{r.get('current_value',0):.1f}{r.get('unit','')}",
                "WARN threshold":f"{r.get('threshold_warn',0):.1f}",
                "CRIT threshold":f"{r.get('threshold_crit',0):.1f}",
                "Status":r.get("status",""),"Team":r.get("owner_team","")[:20],
                "CBK":"🏦" if r.get("system","") in CBK_CRITICAL else ""} for r in all_alerts]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        if is_it or is_admin:
            c1,c2 = st.columns(2)
            if c1.button("✅ Acknowledge all alerts",key="obs_ack",type="primary"):
                audit_log("OBS_ALERTS_ACK",uname,f"{len(all_alerts)} alerts acknowledged")
                _bsc_trigger(uname,"K067")
                st.success(f"✅ {len(all_alerts)} alerts acknowledged — teams notified")
            if c2.button("📧 Escalate critical to management",key="obs_esc"):
                audit_log("OBS_ESCALATED",uname,f"{len(crit_m)} critical escalated")
                st.success("✅ Escalation sent to IT Manager and Operations Director")
    else:
        st.success("✅ All systems operational — no active alerts.")

with tabs[2]:
    rows=[]
    for sys_name in systems:
        sys_m = [r for r in records if r.get("system","")==sys_name]
        avg_up = round(sum(r.get("uptime_30d_pct",0) for r in sys_m)/max(len(sys_m),1),2)
        inc    = sum(r.get("incidents_30d",0) for r in sys_m)
        status = "🔴 CRIT" if any(r.get("status")=="CRIT" for r in sys_m) else                  "🟡 WARN" if any(r.get("status")=="WARN" for r in sys_m) else "🟢 OK"
        rows.append({"System":sys_name[:30],"Status":status,"Uptime(30d)":f"{avg_up:.2f}%",
                      "SLA Target":f"{sla_target}%","SLA Met":"✅" if avg_up>=sla_target else "❌",
                      "Incidents":inc,"CBK Critical":"🏦" if sys_name in CBK_CRITICAL else ""})
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    sla_met = sum(1 for r in rows if r["SLA Met"]=="✅")
    st.caption(f"SLA compliance: {sla_met}/{len(rows)} systems | Average uptime: {avg_uptime:.2f}%")

with tabs[3]:
    st.markdown("**Log a new incident:**")
    if is_it or is_admin:
        r1,r2 = st.columns(2)
        sys_sel = r1.selectbox("System",systems,key="obs_inc_sys")
        severity= r2.selectbox("Severity",["P1 — Critical","P2 — Major","P3 — Minor"],key="obs_inc_sev")
        desc_   = st.text_area("Description *",key="obs_inc_desc")
        if st.button("📝 Log incident",key="obs_inc_log",type="primary"):
            if desc_.strip():
                all_m = _load()
                for m in all_m:
                    if m.get("system","")==sys_sel:
                        m["incidents_30d"] = m.get("incidents_30d",0)+1
                        if "P1" in severity or "P2" in severity: m["status"]="CRIT"
                        break
                _save(all_m)
                audit_log("OBS_INCIDENT_LOGGED",uname,f"{sys_sel}: {severity}")
                _bsc_trigger(uname,"K067")
                st.success("✅ Incident logged"); st.rerun()

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: CBK critical systems list, alert levels (OK/WARN/CRIT)")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("observability",{}).get("configurable",{})
        c1,c2,c3 = st.columns(3)
        new_sla   = c1.number_input("SLA uptime target (%)",90.0,100.0,float(cfg_m.get("sla_uptime_target_pct",99.5)),0.1,key="obs_cfg_sla")
        new_mttr  = c2.number_input("MTTR target (hrs)",1.0,24.0,float(cfg_m.get("mttr_target_hours",4.0)),0.5,key="obs_cfg_mttr")
        new_inc   = c3.number_input("Incident count target",1,50,int(cfg_m.get("incident_target_count",5)),key="obs_cfg_inc")
        new_email = st.text_input("Alert email",cfg_m.get("alert_email",""),key="obs_cfg_email")
        new_check = st.number_input("Check interval (minutes)",1,60,int(cfg_m.get("check_interval_minutes",5)),key="obs_cfg_check")
        st.markdown("**Monitored systems:**")
        for ms in cfg_m.get("monitoring_systems",[]):
            c1,c2,c3 = st.columns([3,2,1])
            c1.markdown(f"**{ms.get('name','')}**")
            c2.markdown(f"Team: {ms.get('team','')}")
            c3.markdown("🏦 CBK" if ms.get("critical") else "")
        if st.button("💾 Save observability config",key="obs_cfg_save",type="primary"):
            cfg_m.update({"sla_uptime_target_pct":new_sla,"mttr_target_hours":new_mttr,
                          "incident_target_count":new_inc,"alert_email":new_email,"check_interval_minutes":new_check})
            mc["observability"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("OBS_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Configuration available to Admin only.")

with tabs[5]:
    bsc_rows=[
        {"KPI":"K066 — System Uptime","Target":f"> {sla_target}%","Actual":f"{avg_uptime:.2f}%","Status":"🟢" if avg_uptime>=sla_target else "🔴","Weight":"10%"},
        {"KPI":"K067 — Critical Incidents","Target":f"< {inc_target}","Actual":str(len(crit_m)),"Status":"🟢" if len(crit_m)<inc_target else "🔴","Weight":"8%"},
        {"KPI":"K068 — MTTR","Target":f"< {mttr_target}hrs","Actual":"2.5hrs (est)","Status":"🟢","Weight":"8%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="obs_bsc",type="primary"):
        _bsc_trigger(uname,"K066"); st.success("✅ BSC updated"); st.rerun()
