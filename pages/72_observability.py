"""pages/72_observability.py — System Observability & Monitoring.
Real-time system health, incident management, SLA tracking, alert management.
Configurable: monitored systems, SLA thresholds, escalation paths.
BSC: K066 (uptime), K067 (incident SLA), K068 (MTTR).
Department: IT. Roles: IT Manager, Systems Administrator, Service Desk Manager.
"""
import streamlit as st, pandas as pd, json
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import defaultdict
from decimal import Decimal
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("observability")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_it    = any(x in role for x in ("it","system","infrastructure","devops","service desk","head","director","technology"))

def _bsc_trigger(u,k=""):
    try:
        from utils.core import update_bsc_from_modules as _u; _u(u)
    except: pass

@st.cache_data(ttl=15)
def _load():
    p = DATA/"observability_metrics.json"
    raw = a2z_db.load_json(p) if p.exists() else []
    for r in raw:
        for k,v in r.items():
            if isinstance(v,Decimal): r[k]=float(v)
    return raw

@st.cache_data(ttl=60)
def _cfg():
    p = DATA/"observability_config.json"
    if p.exists(): return a2z_db.load_json(p)
    return {
        "systems":[
            {"id":"CORE_BANKING","name":"Core Banking (FlexCube)","tier":1,"uptime_target":99.9,"active":True},
            {"id":"MOBILE","name":"Mobile Banking App","tier":1,"uptime_target":99.5,"active":True},
            {"id":"INTERNET_BANKING","name":"Internet Banking","tier":1,"uptime_target":99.5,"active":True},
            {"id":"ATM","name":"ATM Network","tier":1,"uptime_target":98.0,"active":True},
            {"id":"PAYMENTS","name":"Payments Gateway (RTGS/EFT)","tier":1,"uptime_target":99.9,"active":True},
            {"id":"API_GATEWAY","name":"API Gateway","tier":2,"uptime_target":99.5,"active":True},
            {"id":"DATA_CENTER","name":"Primary Data Centre","tier":1,"uptime_target":99.99,"active":True},
            {"id":"DR_SITE","name":"DR Site","tier":2,"uptime_target":99.5,"active":True},
            {"id":"EMAIL","name":"Email & Collaboration","tier":3,"uptime_target":99.0,"active":True},
            {"id":"ERP","name":"HR/Finance ERP","tier":3,"uptime_target":98.0,"active":True},
        ],
        "incident_sla_minutes":{"P1":30,"P2":120,"P3":480,"P4":1440},
        "escalation_path":["Service Desk","IT Manager","Head of IT","CTO"],
        "alert_channels":["Email","SMS","WhatsApp","PagerDuty"],
    }

def _save(recs): (DATA/"observability_metrics.json").write_text(json.dumps(recs,indent=2)); st.cache_data.clear()

metrics = _load(); cfg = _cfg()
systems_cfg = {s["id"]:s for s in cfg["systems"]}

incidents = [m for m in metrics if m.get("type")=="Incident"]
active_inc = [i for i in incidents if i.get("status") not in ("Resolved","Closed")]
p1_active  = [i for i in active_inc if i.get("priority")=="P1"]
avg_uptime = sum(float(m.get("uptime_pct",0) or 0) for m in metrics if m.get("type")=="Uptime")/max(sum(1 for m in metrics if m.get("type")=="Uptime"),1)
sla_met    = sum(1 for i in incidents if i.get("sla_met"))
mttr_vals  = [float(i.get("resolution_mins",0) or 0) for i in incidents if i.get("resolution_mins")]
avg_mttr   = round(sum(mttr_vals)/max(len(mttr_vals),1),0)

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>🖥️ System Observability</span><span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>Real-time health · Incidents · SLA · Uptime · MTTR</span></div>",unsafe_allow_html=True)
if p1_active: st.error(f"🔴 {len(p1_active)} P1 INCIDENT(S) ACTIVE — immediate response required")
elif active_inc: st.warning(f"⚠️ {len(active_inc)} active incident(s)")

m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("Avg uptime",f"{avg_uptime:.2f}%",delta_color="normal" if avg_uptime>=99.5 else "inverse")
m2.metric("Active incidents",len(active_inc),delta_color="inverse" if active_inc else "normal")
m3.metric("P1 incidents",len(p1_active),delta_color="inverse" if p1_active else "normal")
m4.metric("Incident SLA met",f"{sla_met/max(len(incidents),1)*100:.0f}%")
m5.metric("MTTR",f"{avg_mttr:.0f} mins")
m6.metric("Total incidents",len(incidents))

tabs = st.tabs(["🖥️ System Health","🚨 Active Incidents","📊 Analytics","📝 Log Incident","⚙️ Config","🎯 BSC"])

with tabs[0]:
    st.markdown("**Live system status — all monitored systems:**")
    sys_data = {}
    for m in metrics:
        if m.get("type")=="Uptime": sys_data[m.get("system_id","")] = m
    rows=[]
    for s in cfg["systems"]:
        m = sys_data.get(s["id"],{})
        uptime = float(m.get("uptime_pct",100) or 100)
        target = s.get("uptime_target",99.5)
        ok = uptime >= target
        rows.append({"Tier":s["tier"],"System":s["name"],"Uptime":f"{uptime:.2f}%","Target":f"{target:.1f}%","Status":"🟢 Healthy" if ok else "🔴 Below SLA","Last updated":m.get("recorded_at","—")[:16] if m else "—"})
    st.dataframe(pd.DataFrame(sorted(rows,key=lambda x:x["Tier"])),use_container_width=True,hide_index=True)
    st.caption(f"Monitoring {len(cfg['systems'])} systems | Updated every 15 seconds")

with tabs[1]:
    if active_inc:
        for inc in sorted(active_inc,key=lambda x:x.get("priority","P4")):
            p=inc.get("priority","P4"); col={"P1":"🔴","P2":"🟠","P3":"🟡","P4":"⚪"}.get(p,"⚪")
            with st.expander(f"{col} {inc.get('id','')} — {inc.get('title','')[:40]} [{p}]"):
                c1,c2,c3 = st.columns(3)
                c1.markdown(f"**System:** {inc.get('system_id','')}")
                c2.markdown(f"**Opened:** {inc.get('opened_at','')[:16]}")
                c3.markdown(f"**Assigned:** {inc.get('assigned_to','—')}")
                st.markdown(f"**Description:** {inc.get('description','')}")
                sla_mins = cfg["incident_sla_minutes"].get(p,480)
                st.info(f"SLA: {sla_mins} mins | Escalation: {' → '.join(cfg['escalation_path'])}")
                update = st.text_area("Status update",key=f"inc_upd_{inc['id']}")
                status_new = st.selectbox("Update status",["Active","Investigating","Resolved","Closed"],key=f"inc_stat_{inc['id']}")
                if st.button("💾 Update",key=f"inc_save_{inc['id']}",type="primary"):
                    all_m = _load()
                    for m2 in all_m:
                        if m2.get("id")==inc["id"]:
                            m2["status"]=status_new; m2["last_update"]=update; m2["updated_by"]=uname
                            if status_new in ("Resolved","Closed"):
                                m2["resolved_at"]=str(datetime.now())[:16]
                                try:
                                    opened = datetime.fromisoformat(m2.get("opened_at",""))
                                    resolved = datetime.now()
                                    m2["resolution_mins"]=int((resolved-opened).total_seconds()/60)
                                    m2["sla_met"]=m2["resolution_mins"]<=sla_mins
                                except: pass
                            break
                    _save(all_m); audit_log("INCIDENT_UPDATED",uname,f"{inc['id']}: {status_new}")
                    if status_new in ("Resolved","Closed"): _bsc_trigger(uname,"K067")
                    st.success("✅ Updated"); st.rerun()
    else: st.success("✅ No active incidents")

with tabs[2]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**Incidents by priority:**")
        by_p = defaultdict(lambda:{"count":0,"resolved":0,"sla_met":0,"total_mins":0})
        for i in incidents:
            p=i.get("priority","P4"); by_p[p]["count"]+=1
            if i.get("status") in ("Resolved","Closed"): by_p[p]["resolved"]+=1
            if i.get("sla_met"): by_p[p]["sla_met"]+=1
            by_p[p]["total_mins"]+=float(i.get("resolution_mins",0) or 0)
        p_rows=[{"Priority":p,"Total":v["count"],"Resolved":v["resolved"],"SLA Met":v["sla_met"],"Avg MTTR":f"{v['total_mins']/max(v['resolved'],1):.0f}m"}for p,v in sorted(by_p.items())]
        st.dataframe(pd.DataFrame(p_rows),use_container_width=True,hide_index=True)
    with c2:
        st.markdown("**Uptime by system tier:**")
        tier_uptime = defaultdict(list)
        for m in metrics:
            if m.get("type")=="Uptime":
                sys = systems_cfg.get(m.get("system_id",""),{})
                tier_uptime[sys.get("tier",3)].append(float(m.get("uptime_pct",0) or 0))
        tier_rows=[{"Tier":f"Tier {t}","Systems":len(vals),"Avg Uptime":f"{sum(vals)/len(vals):.2f}%","Min":f"{min(vals):.2f}%"}for t,vals in sorted(tier_uptime.items())]
        st.dataframe(pd.DataFrame(tier_rows),use_container_width=True,hide_index=True)

with tabs[3]:
    if is_it or is_admin:
        sys_opts = [s["id"] for s in cfg["systems"] if s.get("active")]
        c1,c2 = st.columns(2)
        _title = st.text_input("Incident title *",key="obs_ntitle")
        _sys   = c1.selectbox("Affected system",sys_opts,key="obs_nsys")
        _prio  = c2.selectbox("Priority",["P1","P2","P3","P4"],key="obs_nprio")
        _desc  = st.text_area("Description",key="obs_ndesc")
        _assign= st.text_input("Assign to (username)",value=uname,key="obs_nassign")
        if st.button("🚨 Log incident",key="obs_nlog",type="primary"):
            if _title.strip():
                all_m = _load()
                all_m.append({"id":f"INC{len(all_m)+1:05d}","type":"Incident","title":_title.strip(),"system_id":_sys,"priority":_prio,"description":_desc,"status":"Active","opened_at":datetime.now().isoformat()[:16],"assigned_to":_assign,"resolved_at":"","resolution_mins":0,"sla_met":False,"last_update":"","updated_by":"","logged_by":uname,"created_at":str(today)})
                _save(all_m); audit_log("INCIDENT_LOGGED",uname,f"{_prio}: {_title[:40]}")
                st.success("✅ Incident logged"); st.rerun()
            else: st.error("Title required")
    else: st.info("Incident logging for IT team.")

with tabs[4]:
    if is_admin or is_it:
        st.markdown("**Monitored systems — SLA targets configurable:**")
        for s in cfg["systems"]:
            c1,c2,c3,c4 = st.columns([4,2,1,1])
            c1.markdown(f"**{s['name']}** (Tier {s['tier']})")
            new_target = c2.number_input("Uptime target %",90.0,100.0,float(s.get("uptime_target",99.5)),0.1,key=f"obs_tgt_{s['id']}")
            s["uptime_target"]=new_target
            s["active"]=c4.checkbox("Active",value=s.get("active",True),key=f"obs_act_{s['id']}")
        if st.button("💾 Save config",key="obs_cfg_save",type="primary"):
            (DATA/"observability_config.json").write_text(json.dumps(cfg,indent=2))
            st.cache_data.clear(); audit_log("OBS_CFG_SAVED",uname,""); st.success("✅"); st.rerun()
    else: st.info("Config for IT management.")

with tabs[5]:
    st.markdown("**System Observability BSC KPIs:**")
    st.metric("K066 — System Uptime",f"{avg_uptime:.2f}%","Target 99.5%",delta_color="normal" if avg_uptime>=99.5 else "inverse")
    sla_pct = round(sla_met/max(len(incidents),1)*100,1)
    st.metric("K067 — Incident SLA Met",f"{sla_pct:.0f}%","Target 90%",delta_color="normal" if sla_pct>=90 else "inverse")
    st.metric("K068 — MTTR",f"{avg_mttr:.0f} mins","Target ≤60 mins",delta_color="normal" if avg_mttr<=60 else "inverse")
    if st.button("🔄 Refresh BSC",key="obs_bsc_ref"): _bsc_trigger(uname,"observability"); st.success("✅"); st.rerun()
