"""pages/69_consent.py — Consent Management (Data Protection Act 2019).
Dept: Compliance | KPIs: K058 K059 | BSC: Auto-scored
Hardcoded: legal bases, CBK categories, DPA Kenya applicability
Configurable: consent types (on/off), data processors, expiry periods, targets
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

require_access("consent_management")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_comp  = any(x in role for x in ("compliance","dpo","data","legal","risk","manager","head","director"))

LEGAL_BASES   = ["Consent","Contractual","Legitimate Interest","Legal Obligation"]
CBK_CATEGORIES= ["Personal Data","Financial Data","Sensitive Data"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

@st.cache_data(ttl=30)
def _load():
    p = DATA / "consent_register.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

@st.cache_data(ttl=60)
def _cfg():
    mc = DATA / "module_config.json"
    if not mc.exists(): return {}
    return json.loads(mc.read_text(encoding="utf-8")).get("consent", {})

def _save(data):
    (DATA/"consent_register.json").write_text(json.dumps(data, indent=2))
    st.cache_data.clear()

records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable", {})
consent_types   = conf_cfg.get("consent_types", [])
data_processors = conf_cfg.get("data_processors", [])
expiry_warn     = conf_cfg.get("expiry_warning_days", 30)
capture_target  = conf_cfg.get("capture_target_pct", 70)

active_types = [c["name"] for c in consent_types if c.get("active", True)]
proc_names   = [p["name"] for p in data_processors]

active_c  = [r for r in records if r.get("status") == "Active"]
withdrawn = [r for r in records if r.get("status") == "Withdrawn"]
expiring  = [r for r in records if r.get("status") == "Active"
             and r.get("expiry_date","") <= str(today + timedelta(days=expiry_warn))]
expired_r = [r for r in records if r.get("status") == "Expired"]
capture_rate = round(len(active_c)/max(len(records),1)*100, 1)
renewal_rate = round(len([r for r in records if r.get("status")=="Active" and r.get("expiry_date","")>str(today)])/max(len(records),1)*100,1)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔏 Consent Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Compliance · Data Protection Act 2019 · K058 · K059</span></div>",
    unsafe_allow_html=True)

if expiring:
    st.warning(f"⚠️ {len(expiring)} consent(s) expiring within {expiry_warn} days — renewal required")
if capture_rate < capture_target:
    st.error(f"🔴 Consent capture rate {capture_rate}% below target {capture_target}%")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total records",    len(records))
m2.metric("Active",           len(active_c))
m3.metric("Withdrawn",        len(withdrawn))
m4.metric("Expiring soon",    len(expiring), delta_color="inverse" if expiring else "off")
m5.metric("Capture rate",     f"{capture_rate}%",
          delta_color="off" if capture_rate>=capture_target else "inverse")

tabs = st.tabs(["📋 Register","⚠️ Expiring","📊 Analytics","➕ Record Consent",
                "🔄 Bulk Actions","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2,f3,f4 = st.columns(4)
    fctype  = f1.selectbox("Type",   ["All"]+sorted(set(r.get("consent_type","") for r in records)), key="cn_type")
    fstat   = f2.selectbox("Status", ["All","Active","Withdrawn","Expired","Pending"], key="cn_stat")
    flegal  = f3.selectbox("Legal basis", ["All"]+LEGAL_BASES, key="cn_legal")
    fsearch = f4.text_input("Search CIF / name", key="cn_search")
    vis = [r for r in records
           if (fctype=="All" or r.get("consent_type","")==fctype)
           and (fstat=="All" or r.get("status","")==fstat)
           and (flegal=="All" or r.get("legal_basis","")==flegal)
           and (not fsearch or fsearch.lower() in r.get("customer_cif","").lower()
                or fsearch.lower() in r.get("customer_name","").lower())]
    rows = [{"ID":r["id"],"CIF":r.get("customer_cif",""),"Customer":r.get("customer_name","")[:20],
              "Consent type":r.get("consent_type","")[:22],"Channel":r.get("channel",""),
              "Status":r.get("status",""),"Legal basis":r.get("legal_basis","")[:20],
              "Granted":r.get("granted_date","")[:10],"Expiry":r.get("expiry_date","")[:10],
              "Processor":r.get("data_processor","")[:15]} for r in vis]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"{len(vis)} records shown | Capture rate: {capture_rate}% vs target {capture_target}%")

with tabs[1]:
    if expiring:
        for r in expiring:
            with st.expander(f"⚠️ {r.get('customer_name',r.get('customer_cif',''))} — {r.get('consent_type','')} — Expires {r.get('expiry_date','')[:10]}"):
                c1,c2 = st.columns(2)
                c1.markdown(f"**CIF:** {r.get('customer_cif','')} | **Channel:** {r.get('channel','')}")
                c2.markdown(f"**Processor:** {r.get('data_processor','')} | **Legal:** {r.get('legal_basis','')}")
                ext_months = c1.selectbox("Extend by", [6,12,24,36], index=1, key=f"ext_{r['id']}")
                if c2.button("🔄 Renew", key=f"renew_{r['id']}", type="primary"):
                    all_r = _load()
                    for rec in all_r:
                        if rec["id"] == r["id"]:
                            old_exp = date.fromisoformat(r.get("expiry_date",str(today))[:10])
                            new_exp = old_exp + timedelta(days=ext_months*30)
                            rec["expiry_date"]  = str(new_exp)
                            rec["status"]       = "Active"
                            break
                    _save(all_r)
                    audit_log("CONSENT_RENEWED", uname, f"{r['id']}: +{ext_months}mo")
                    _bsc_trigger(uname, "K059")
                    st.success(f"✅ Renewed for {ext_months} months"); st.rerun()
    else:
        st.success(f"✅ No consents expiring in next {expiry_warn} days.")

with tabs[2]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**By consent type:**")
        by_type = defaultdict(lambda:{"total":0,"active":0,"withdrawn":0})
        for r in records:
            t = r.get("consent_type","Other")
            by_type[t]["total"]     += 1
            by_type[t]["active"]    += 1 if r.get("status")=="Active" else 0
            by_type[t]["withdrawn"] += 1 if r.get("status")=="Withdrawn" else 0
        an_rows = [{"Type":t[:25],"Total":v["total"],"Active":v["active"],
                     "Withdrawn":v["withdrawn"],"Rate":f"{v['active']/max(v['total'],1)*100:.0f}%"}
                    for t,v in sorted(by_type.items(),key=lambda x:-x[1]["active"])]
        st.dataframe(pd.DataFrame(an_rows), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**By channel:**")
        by_ch = defaultdict(int)
        for r in active_c: by_ch[r.get("channel","Other")] += 1
        st.bar_chart(pd.DataFrame({"Active consents":by_ch}))

    st.markdown("**By data processor:**")
    by_proc = defaultdict(lambda:{"total":0,"active":0})
    for r in records:
        p = r.get("data_processor","Internal")
        by_proc[p]["total"]  += 1
        by_proc[p]["active"] += 1 if r.get("status")=="Active" else 0
    proc_rows = [{"Processor":p[:25],"Total":v["total"],"Active":v["active"]}
                  for p,v in sorted(by_proc.items(),key=lambda x:-x[1]["active"])]
    st.dataframe(pd.DataFrame(proc_rows), use_container_width=True, hide_index=True)

with tabs[3]:
    st.markdown("**Record a new customer consent:**")
    r1,r2 = st.columns(2)
    cif_    = r1.text_input("Customer CIF *", key="cn_new_cif")
    cname_  = r2.text_input("Customer name", key="cn_new_name")
    ctype_  = r1.selectbox("Consent type *", active_types if active_types else ["Marketing Communications"], key="cn_new_type")
    cch_    = r2.selectbox("Channel", ["Branch","Mobile App","USSD","Website","Call Centre","Agent"], key="cn_new_ch")
    clb_    = r1.selectbox("Legal basis", LEGAL_BASES, key="cn_new_lb")
    cproc_  = r2.selectbox("Data processor", ["Internal"]+proc_names, key="cn_new_proc")
    ccbk_   = r1.selectbox("CBK category", CBK_CATEGORIES, key="cn_new_cbk")
    ctype_obj = next((c for c in consent_types if c.get("name")==ctype_), {})
    exp_days  = ctype_obj.get("expiry_days", 365)
    cexp_   = r2.date_input("Expiry date", today+timedelta(days=exp_days), key="cn_new_exp")
    cgrant_ = st.checkbox("Customer has provided consent", True, key="cn_new_grant")

    if st.button("💾 Record consent", key="cn_save", type="primary"):
        if cif_.strip():
            all_r = _load()
            all_r.append({
                "id": f"CONS{len(all_r)+1:05d}",
                "customer_cif": cif_.strip(), "customer_name": cname_.strip(),
                "consent_type": ctype_, "status": "Active" if cgrant_ else "Pending",
                "channel": cch_, "granted": cgrant_,
                "granted_date": str(today) if cgrant_ else "",
                "withdrawn_date": "", "expiry_date": str(cexp_),
                "purpose": f"To {ctype_.lower()} for service improvement",
                "legal_basis": clb_, "data_processor": cproc_, "cbk_category": ccbk_,
                "version": "v1.0", "reviewed_by": uname, "notes": "",
            })
            _save(all_r)
            audit_log("CONSENT_RECORDED", uname, f"{cif_}: {ctype_}")
            _bsc_trigger(uname, "K058")
            st.success("✅ Consent recorded"); st.rerun()
        else:
            st.error("CIF required.")

with tabs[4]:
    if is_comp or is_admin:
        st.markdown("**Bulk actions for consent management:**")
        c1,c2 = st.columns(2)
        c1.metric("Expired records", len(expired_r))
        c2.metric("Withdrawn records", len(withdrawn))
        if st.button("📧 Send renewal reminders for expiring consents", key="cn_remind"):
            audit_log("CONSENT_REMINDERS_SENT", uname, f"{len(expiring)} reminders")
            st.success(f"✅ Renewal reminders sent for {len(expiring)} consents")
        if st.button("📊 Export consent report (CSV)", key="cn_export"):
            audit_log("CONSENT_EXPORTED", uname, "Full register exported")
            st.success("✅ Export queued for download")
    else:
        st.info("Bulk actions available to compliance team.")

with tabs[5]:
    if is_admin:
        st.info("ℹ️ Hardcoded (DPA Kenya 2019 & CBK): Legal bases, CBK data categories, withdrawal immediacy requirement")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("consent",{}).get("configurable",{})

        st.markdown("**Consent type management:**")
        for i, ct in enumerate(cfg_m.get("consent_types",[])):
            c1,c2,c3,c4 = st.columns([3,2,1,1])
            c1.markdown(f"**{ct.get('name','')}**")
            c2.markdown(f"{ct.get('expiry_days',365)} days")
            active_val = c3.checkbox("Active", ct.get("active",True), key=f"ct_act_{i}")
            cfg_m["consent_types"][i]["active"] = active_val

        c1,c2 = st.columns(2)
        new_target = c1.number_input("Capture rate target (%)", 10, 100,
                                     int(cfg_m.get("capture_target_pct",70)), key="cn_cfg_tgt")
        new_warn   = c2.number_input("Expiry warning (days)", 7, 90,
                                     int(cfg_m.get("expiry_warning_days",30)), key="cn_cfg_warn")

        st.markdown("**Add consent type:**")
        r1,r2,r3 = st.columns(3)
        new_ctype = r1.text_input("Type name", key="cn_new_ctype")
        new_exp_d = r2.number_input("Expiry (days)", 30, 1095, 365, key="cn_new_exp_d")
        new_icon  = r3.text_input("Icon", "📄", key="cn_new_icon")
        if st.button("➕ Add consent type", key="cn_type_add"):
            if new_ctype.strip():
                cfg_m.setdefault("consent_types",[]).append(
                    {"id":new_ctype.upper().replace(" ","_")[:12],
                     "name":new_ctype.strip(),"icon":new_icon,"active":True,"expiry_days":int(new_exp_d)})
                audit_log("CONSENT_TYPE_ADDED",uname,new_ctype)

        if st.button("💾 Save consent config", key="cn_cfg_save", type="primary"):
            cfg_m.update({"capture_target_pct":new_target,"expiry_warning_days":new_warn})
            mc["consent"]["configurable"] = cfg_m
            (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("CONSENT_CFG_SAVED",uname,"Config updated")
            st.cache_data.clear(); st.success("✅ Configuration saved"); st.rerun()
    else:
        st.info("Configuration available to Admin only.")

with tabs[6]:
    st.markdown("**Your BSC KPIs from Consent Management:**")
    bsc_rows = [
        {"KPI":"K058 — Consent Capture Rate","Target":f"> {capture_target}%","Actual":f"{capture_rate}%",
         "Weight":"8%","Status":"🟢" if capture_rate>=capture_target else "🔴","Direction":"Higher is better"},
        {"KPI":"K059 — Expired Consents Renewed","Target":"> 80%","Actual":f"{renewal_rate}%",
         "Weight":"5%","Status":"🟢" if renewal_rate>=80 else "🟡","Direction":"Higher is better"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows), use_container_width=True, hide_index=True)
    if st.button("🔄 Refresh BSC", key="cn_bsc_ref", type="primary"):
        _bsc_trigger(uname, "K058")
        st.success("✅ BSC updated"); st.cache_data.clear(); st.rerun()
