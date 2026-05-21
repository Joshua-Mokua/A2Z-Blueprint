"""pages/47_digital_channels.py — Digital Channel Dashboard.
Mobile, USSD, internet banking, agency banking, ATM — live KPIs.
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

require_access("sales_customer.digital_channels")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📱 Digital Channels</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Mobile · USSD · Internet Banking · Agency · ATM · Real-time KPIs</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"digital_channels.json"
    return a2z_db.load_json(p) if p.exists() else {}

data = _load()
if not data: st.info("Digital channel data not available."); st.stop()

mob  = data.get("mobile_app",{})
ussd = data.get("ussd",{})
inet = data.get("internet_banking",{})
agn  = data.get("agency_banking",{})
atm  = data.get("atm",{})

# Top-line digital health
mig  = data.get("digital_migration_rate_pct",0)
cost_d = data.get("cost_per_digital_txn_kes",0)
cost_b = data.get("cost_per_branch_txn_kes",0)

st.markdown(
    f"<div style='display:flex;gap:20px;flex-wrap:wrap;background:var(--color-background-secondary);"
    f"border-radius:10px;padding:12px 20px;margin-bottom:10px'>"
    f"<div><div style='font-size:11px;color:var(--color-text-tertiary)'>Digital Migration Rate</div>"
    f"<div style='font-size:22px;font-weight:700'>{mig:.1f}%</div></div>"
    f"<div><div style='font-size:11px;color:var(--color-text-tertiary)'>Cost / Digital Txn</div>"
    f"<div style='font-size:22px;font-weight:700'>KES {cost_d:.0f}</div></div>"
    f"<div><div style='font-size:11px;color:var(--color-text-tertiary)'>Cost / Branch Txn</div>"
    f"<div style='font-size:22px;font-weight:700'>KES {cost_b:.0f}</div></div>"
    f"<div><div style='font-size:11px;color:var(--color-text-tertiary)'>Cost Saving per Digital Txn</div>"
    f"<div style='font-size:22px;font-weight:700;color:#16A34A'>KES {cost_b-cost_d:.0f}</div></div>"
    f"</div>", unsafe_allow_html=True)

tabs = st.tabs(["📱 Mobile App","📲 USSD","💻 Internet Banking","🏪 Agency Banking","🏧 ATM","📈 Trend"])

with tabs[0]:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("MAU",             f"{mob.get('mau',0):,}")
    c2.metric("DAU",             f"{mob.get('dau',0):,}")
    c3.metric("Txns Today",      f"{mob.get('txn_count_today',0):,}")
    c4.metric("Uptime (30d)",    f"{mob.get('uptime_30d_pct',0):.1f}%",
              delta_color="normal" if mob.get('uptime_30d_pct',0)>=cfg('digital_uptime_target',99) else "inverse")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Avg Session",     f"{mob.get('avg_session_min',0):.1f} min")
    c2.metric("Crash Rate",      f"{mob.get('crash_rate_pct',0):.1f}%",
              delta_color="normal" if mob.get('crash_rate_pct',0)<cfg('app_crash_rate_target',1) else "inverse")
    c3.metric("App Rating",      f"{mob.get('app_rating',0):.1f}/5.0")
    c4.metric("Errors Today",    mob.get('errors_today',0),
              delta_color="normal" if mob.get('errors_today',0)<cfg('app_errors_target',50) else "inverse")
    if mob.get('features'):
        st.markdown("**Feature usage (% of sessions):**")
        feats = mob['features']
        st.bar_chart(pd.DataFrame({"% sessions":feats}))

with tabs[1]:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("MAU",              f"{ussd.get('mau',0):,}")
    c2.metric("Txns Today",       f"{ussd.get('txn_count_today',0):,}")
    c3.metric("Completion Rate",  f"{ussd.get('completion_rate_pct',0):.1f}%",
              delta_color="normal" if ussd.get('completion_rate_pct',0)>=cfg('ussd_completion_target',80) else "inverse")
    c4.metric("Uptime (30d)",     f"{ussd.get('uptime_30d_pct',0):.1f}%")
    st.caption(f"Average USSD session: {ussd.get('avg_steps',0):.1f} steps")

with tabs[2]:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("MAU",             f"{inet.get('mau',0):,}")
    c2.metric("Txns Today",      f"{inet.get('txn_count_today',0):,}")
    c3.metric("Value Today (B)", f"KES {inet.get('txn_value_today_kes_b',0):.1f}B")
    c4.metric("Avg Session",     f"{inet.get('avg_session_min',0):.1f} min")

with tabs[3]:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Active Agents",   f"{agn.get('active_agents',0):,}")
    c2.metric("Active Today",    f"{agn.get('agents_active_today',0):,}")
    c3.metric("Txns Today",      f"{agn.get('txn_count_today',0):,}")
    c4.metric("Float Util%",     f"{agn.get('float_utilisation_pct',0):.0f}%",
              delta_color="normal" if agn.get('float_utilisation_pct',0)<90 else "inverse")
    if agn.get('downtime_agents_today',0):
        st.warning(f"⚠️ {agn['downtime_agents_today']} agents with downtime today")

with tabs[4]:
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Total ATMs",      atm.get("total_atms",0))
    c2.metric("Operational",     atm.get("operational",0))
    c3.metric("Uptime",          f"{atm.get('uptime_pct',0):.1f}%",
              delta_color="normal" if atm.get('uptime_pct',0)>=cfg('atm_uptime_target',97) else "inverse")
    c4.metric("Txns Today",      f"{atm.get('txn_count_today',0):,}")
    if atm.get("down",0):
        st.error(f"🔴 {atm['down']} ATM(s) currently out of service")

with tabs[5]:
    trend = data.get("monthly_trend",[])
    if trend:
        st.line_chart(pd.DataFrame({"Mobile MAU":[t["mau"] for t in trend]},
                                    index=[t["month"] for t in trend]))

# v10.465 — Phase 4 WF4 operational output
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()

