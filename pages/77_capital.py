"""pages/77_capital.py — Capital Adequacy & Liquidity (Basel III).
CAR, LCR, NSFR, Tier 1 — daily monitoring.
Dept: Treasury | KPIs: K080 K081 K082 K083
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log
from utils.db import db as a2z_db

require_access("regulatory_capital")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_treas = any(x in role for x in ("treasury","finance","risk","cfo","alco","manager","head","director","chief"))

# CBK MINIMUMS — HARDCODED
TIER1_MIN  = 10.5
TOTAL_MIN  = 14.5
LCR_MIN    = 100
NSFR_MIN   = 100
LEVERAGE_MIN = 4.5

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"capital_liquidity_metrics.json", table="capital_liquidity_metrics")

def _save(data):
    a2z_db.dual_save(DATA/"capital_liquidity_metrics.json", data, table="capital_liquidity_metrics", flat_cols=('id', 'metric_date', 'tier1_ratio_pct', 'total_capital_ratio_pct', 'leverage_ratio_pct', 'lcr_pct', 'nsfr_pct', 'all_compliant'))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("regulatory_capital",{}) if mc.exists() else {}


records = sorted(_load(), key=lambda x:x.get("metric_date",""), reverse=True)
cfg_c = _cfg()
conf_cfg = cfg_c.get("configurable",{})
tier1_warn = conf_cfg.get("tier1_warning_pct",12.0)
total_warn = conf_cfg.get("total_capital_warning_pct",16.0)
lcr_warn   = conf_cfg.get("lcr_warning_pct",110)
nsfr_warn  = conf_cfg.get("nsfr_warning_pct",110)

latest = records[0] if records else {}
prev_30= records[30] if len(records)>30 else (records[-1] if records else {})

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏛️ Capital Adequacy & Liquidity</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    f"Basel III + CBK Prudential · As of {latest.get('metric_date','—')}</span></div>",
    unsafe_allow_html=True)

# Latest position
tier1     = latest.get("tier1_ratio_pct", 0)
total_cap = latest.get("total_capital_ratio_pct", 0)
lev       = latest.get("leverage_ratio_pct", 0)
lcr       = latest.get("lcr_pct", 0)
nsfr      = latest.get("nsfr_pct", 0)

# Alerts
alerts = []
if tier1 < TIER1_MIN: alerts.append(f"🔴 BREACH: Tier 1 {tier1:.2f}% below CBK minimum {TIER1_MIN}%")
elif tier1 < tier1_warn: alerts.append(f"⚠️ Tier 1 {tier1:.2f}% below warning level {tier1_warn}%")
if total_cap < TOTAL_MIN: alerts.append(f"🔴 BREACH: Total Capital {total_cap:.2f}% below CBK minimum {TOTAL_MIN}%")
elif total_cap < total_warn: alerts.append(f"⚠️ Total Capital {total_cap:.2f}% below warning level {total_warn}%")
if lcr < LCR_MIN: alerts.append(f"🔴 BREACH: LCR {lcr:.1f}% below CBK minimum {LCR_MIN}%")
elif lcr < lcr_warn: alerts.append(f"⚠️ LCR {lcr:.1f}% below warning level {lcr_warn}%")
if nsfr < NSFR_MIN: alerts.append(f"🔴 BREACH: NSFR {nsfr:.1f}% below CBK minimum {NSFR_MIN}%")

for a in alerts:
    if "🔴" in a: st.error(a)
    else: st.warning(a)
if not alerts: st.success("✅ All capital and liquidity ratios above CBK minimums and warning levels.")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Tier 1 Capital",   f"{tier1:.2f}%",
          delta=f"Min: {TIER1_MIN}%",
          delta_color="off" if tier1>=tier1_warn else "inverse")
m2.metric("Total Capital",    f"{total_cap:.2f}%",
          delta=f"Min: {TOTAL_MIN}%",
          delta_color="off" if total_cap>=total_warn else "inverse")
m3.metric("Leverage",         f"{lev:.2f}%",
          delta=f"Min: {LEVERAGE_MIN}%",
          delta_color="off" if lev>=LEVERAGE_MIN else "inverse")
m4.metric("LCR",              f"{lcr:.1f}%",
          delta=f"Min: {LCR_MIN}%",
          delta_color="off" if lcr>=lcr_warn else "inverse")
m5.metric("NSFR",             f"{nsfr:.1f}%",
          delta=f"Min: {NSFR_MIN}%",
          delta_color="off" if nsfr>=nsfr_warn else "inverse")

tabs = st.tabs(["📊 Dashboard","📈 Trend (60 days)","💰 Capital Composition","💧 Liquidity Detail","➕ New Snapshot","⚙️ Config","📈 BSC"])

with tabs[0]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**Capital — KES Billions:**")
        st.metric("Tier 1 Capital",   f"KES {latest.get('tier1_capital_kes_b',0):.2f}B")
        st.metric("Tier 2 Capital",   f"KES {latest.get('tier2_capital_kes_b',0):.2f}B")
        st.metric("Total Capital",    f"KES {latest.get('total_capital_kes_b',0):.2f}B")
        st.metric("Risk Weighted Assets", f"KES {latest.get('rwa_kes_b',0):.2f}B")
    with c2:
        st.markdown("**Liquidity — KES Billions:**")
        st.metric("Liquid Assets",    f"KES {latest.get('liquid_assets_kes_b',0):.2f}B")
        st.metric("Net Outflows",     f"KES {latest.get('net_outflows_kes_b',0):.2f}B")
        st.metric("Available Funding",f"KES {latest.get('available_funding_kes_b',0):.2f}B")
        st.metric("Required Funding", f"KES {latest.get('required_funding_kes_b',0):.2f}B")

with tabs[1]:
    if records:
        df = pd.DataFrame(records[:60])
        df["metric_date"] = pd.to_datetime(df["metric_date"])
        df = df.sort_values("metric_date")
        st.markdown("**Capital ratios (last 60 days):**")
        st.line_chart(df.set_index("metric_date")[["tier1_ratio_pct","total_capital_ratio_pct"]])
        st.markdown("**Liquidity ratios (last 60 days):**")
        st.line_chart(df.set_index("metric_date")[["lcr_pct","nsfr_pct"]])

with tabs[2]:
    st.markdown("**Capital composition:**")
    df = pd.DataFrame({
        "Component":["Tier 1","Tier 2","RWA"],
        "KES (B)":[latest.get("tier1_capital_kes_b",0),
                    latest.get("tier2_capital_kes_b",0),
                    latest.get("rwa_kes_b",0)]
    })
    st.dataframe(df, use_container_width=True, hide_index=True)
    delta_t1 = tier1 - prev_30.get("tier1_ratio_pct",tier1)
    st.caption(f"30-day change: Tier 1 {'+' if delta_t1>=0 else ''}{delta_t1:.2f}pp | Total Capital {'+' if (total_cap-prev_30.get('total_capital_ratio_pct',total_cap))>=0 else ''}{total_cap-prev_30.get('total_capital_ratio_pct',total_cap):.2f}pp")

with tabs[3]:
    st.markdown("**LCR detail:**")
    if lcr >= LCR_MIN:
        st.success(f"LCR {lcr:.1f}% — surplus over minimum: {lcr-LCR_MIN:.1f}pp")
    st.metric("HQLA",          f"KES {latest.get('liquid_assets_kes_b',0):.2f}B")
    st.metric("Net Outflows",  f"KES {latest.get('net_outflows_kes_b',0):.2f}B")
    st.markdown("**NSFR detail:**")
    if nsfr >= NSFR_MIN:
        st.success(f"NSFR {nsfr:.1f}% — surplus over minimum: {nsfr-NSFR_MIN:.1f}pp")
    st.metric("Available Stable Funding",f"KES {latest.get('available_funding_kes_b',0):.2f}B")
    st.metric("Required Stable Funding", f"KES {latest.get('required_funding_kes_b',0):.2f}B")

with tabs[4]:
    if is_treas or is_admin:
        st.markdown("**Daily snapshot (Treasury team only):**")
        c1,c2,c3 = st.columns(3)
        m_date = c1.date_input("Snapshot date",today,key="cap_new_date")
        new_t1c= c2.number_input("Tier 1 Capital (KES B)",0.0,200.0,float(latest.get("tier1_capital_kes_b",40.0)),0.1,key="cap_new_t1c")
        new_t2c= c3.number_input("Tier 2 Capital (KES B)",0.0,100.0,float(latest.get("tier2_capital_kes_b",10.0)),0.1,key="cap_new_t2c")
        new_rwa= c1.number_input("Risk Weighted Assets (KES B)",0.0,1000.0,float(latest.get("rwa_kes_b",290.0)),0.1,key="cap_new_rwa")
        new_la = c2.number_input("Liquid Assets (KES B)",0.0,500.0,float(latest.get("liquid_assets_kes_b",95.0)),0.1,key="cap_new_la")
        new_no = c3.number_input("Net Outflows (KES B)",0.0,500.0,float(latest.get("net_outflows_kes_b",75.0)),0.1,key="cap_new_no")
        new_af = c1.number_input("Available Funding (KES B)",0.0,1000.0,float(latest.get("available_funding_kes_b",240.0)),0.1,key="cap_new_af")
        new_rf = c2.number_input("Required Funding (KES B)",0.0,1000.0,float(latest.get("required_funding_kes_b",210.0)),0.1,key="cap_new_rf")
        if st.button("💾 Save snapshot",key="cap_save_snap",type="primary"):
            new_total_cap = new_t1c + new_t2c
            new_t1_ratio  = round(new_t1c/max(new_rwa,0.001)*100, 2)
            new_total_r   = round(new_total_cap/max(new_rwa,0.001)*100, 2)
            new_lcr       = round(new_la/max(new_no,0.001)*100, 1)
            new_nsfr      = round(new_af/max(new_rf,0.001)*100, 1)
            all_r = _load()
            all_r.insert(0, {
                "id":              f"CAP{len(all_r)+1:04d}",
                "metric_date":     str(m_date),
                "tier1_capital_kes_b":     new_t1c,
                "tier2_capital_kes_b":     new_t2c,
                "total_capital_kes_b":     new_total_cap,
                "rwa_kes_b":               new_rwa,
                "tier1_ratio_pct":         new_t1_ratio,
                "total_capital_ratio_pct": new_total_r,
                "leverage_ratio_pct":      round(new_t1c/max(new_rwa*0.5,0.001)*100,2),
                "cbk_tier1_minimum_pct":   TIER1_MIN,
                "cbk_total_minimum_pct":   TOTAL_MIN,
                "lcr_pct":                 new_lcr,
                "lcr_minimum_pct":         LCR_MIN,
                "nsfr_pct":                new_nsfr,
                "nsfr_minimum_pct":        NSFR_MIN,
                "liquid_assets_kes_b":     new_la,
                "net_outflows_kes_b":      new_no,
                "available_funding_kes_b": new_af,
                "required_funding_kes_b":  new_rf,
                "all_compliant":           all([new_t1_ratio>=TIER1_MIN,new_total_r>=TOTAL_MIN,new_lcr>=LCR_MIN,new_nsfr>=NSFR_MIN]),
                "alco_meeting_held":       False,
                "reported_to_cbk":         False,
                "exceptions":              0,
                "calculated_by":           uname,
                "approved_by":             "",
                "notes":                   "",
            })
            _save(all_r); audit_log("CAPITAL_SNAPSHOT",uname,f"{m_date}: T1={new_t1_ratio}% LCR={new_lcr}%")
            _bsc_trigger(uname,"K080")
            st.success(f"✅ Snapshot saved — T1: {new_t1_ratio}% | LCR: {new_lcr}%"); st.rerun()
    else:
        st.info("Treasury team only.")

with tabs[5]:
    if is_admin:
        st.info("ℹ️ Hardcoded (CBK Prudential): Tier 1 min 10.5%, Total Capital min 14.5%, LCR 100%, NSFR 100%, daily calculation")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("regulatory_capital",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_t1w = c1.number_input("Tier 1 warning (%)",10.5,20.0,float(cfg_m.get("tier1_warning_pct",12.0)),0.5,key="cap_cfg_t1w")
        new_tcw = c2.number_input("Total Capital warning (%)",14.5,25.0,float(cfg_m.get("total_capital_warning_pct",16.0)),0.5,key="cap_cfg_tcw")
        new_lw  = c1.number_input("LCR warning (%)",100,200,int(cfg_m.get("lcr_warning_pct",110)),5,key="cap_cfg_lw")
        new_nw  = c2.number_input("NSFR warning (%)",100,200,int(cfg_m.get("nsfr_warning_pct",110)),5,key="cap_cfg_nw")
        if st.button("💾 Save",key="cap_cfg_save",type="primary"):
            cfg_m.update({"tier1_warning_pct":new_t1w,"total_capital_warning_pct":new_tcw,"lcr_warning_pct":new_lw,"nsfr_warning_pct":new_nw})
            mc["regulatory_capital"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("CAPITAL_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Admin only.")

with tabs[6]:
    bsc_rows=[
        {"KPI":"K080 — Capital Adequacy Ratio","Target":f"> {TOTAL_MIN}%","Actual":f"{total_cap:.2f}%","Status":"🟢" if total_cap>=total_warn else "🟡","Weight":"12%"},
        {"KPI":"K081 — Liquidity Coverage Ratio","Target":f"> {LCR_MIN}%","Actual":f"{lcr:.1f}%","Status":"🟢" if lcr>=lcr_warn else "🟡","Weight":"10%"},
        {"KPI":"K082 — Net Stable Funding Ratio","Target":f"> {NSFR_MIN}%","Actual":f"{nsfr:.1f}%","Status":"🟢" if nsfr>=nsfr_warn else "🟡","Weight":"8%"},
        {"KPI":"K083 — Tier 1 Capital Ratio","Target":f"> {TIER1_MIN}%","Actual":f"{tier1:.2f}%","Status":"🟢" if tier1>=tier1_warn else "🟡","Weight":"10%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="cap_bsc",type="primary"):
        _bsc_trigger(uname,"K080"); st.success("✅ BSC updated"); st.rerun()
