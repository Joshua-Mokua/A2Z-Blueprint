"""pages/53_irrbb.py — IRRBB Dashboard.
EaR, EVE, repricing gap. CBK limits configurable via Admin.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access

require_access("irrbb")
DATA  = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>📉 IRRBB Dashboard</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Interest Rate Risk · EaR · EVE · Repricing Gap · CBK Limits</span></div>",
            unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA/"irrbb.json"
    return json.loads(p.read_text()) if p.exists() else {}

data = _load()
if not data: st.info("IRRBB data not available."); st.stop()

ear_lim = cfg("irrbb_ear_limit_pct",  20.0)
ear_wrn = cfg("irrbb_ear_warning_pct",15.0)
eve_lim = cfg("irrbb_eve_limit_pct",  20.0)

scenarios = data.get("scenarios",[])
gaps      = data.get("repricing_gap",[])
nim       = data.get("nim_current_pct",0)

# Alerts for limit breaches
for s in scenarios:
    if s.get("ear_pct",0) >= ear_lim:
        st.error(f"🔴 EaR LIMIT BREACH: Scenario {s['name']} — EaR {s['ear_pct']:.1f}% ≥ CBK limit {ear_lim}%")
    elif s.get("ear_pct",0) >= ear_wrn:
        st.warning(f"⚠️ EaR warning: Scenario {s['name']} — EaR {s['ear_pct']:.1f}% approaching limit {ear_lim}%")

m1,m2,m3 = st.columns(3)
m1.metric("Current NIM",          f"{nim:.2f}%")
m2.metric("EaR Limit (CBK)",      f"{ear_lim:.0f}%")
m3.metric("EVE Limit (CBK)",      f"{eve_lim:.0f}%")

tabs = st.tabs(["📊 Stress Scenarios","📐 Repricing Gap","⚙️ Limits","ℹ️ Methodology"])

with tabs[0]:
    st.markdown("**EaR and EVE impact under CBK-prescribed rate scenarios:**")
    s_rows=[{"Scenario":s["name"],
              "EaR Impact (KES M)":s["ear_impact_m"],"EaR %":f"{s['ear_pct']:.1f}%",
              "EVE Impact (KES M)":s["eve_impact_m"],"EVE %":f"{s['eve_pct']:.1f}%",
              "EaR Status":("🔴 BREACH" if s['ear_pct']>=ear_lim else "🟡 Watch" if s['ear_pct']>=ear_wrn else "🟢 OK"),
              "EVE Status":("🔴 BREACH" if s['eve_pct']>=eve_lim else "🟢 OK")}
             for s in scenarios]
    st.dataframe(pd.DataFrame(s_rows),use_container_width=True,hide_index=True)
    st.caption(f"EaR = Earnings at Risk (impact on NII over 12 months). EVE = Economic Value of Equity. "
               f"CBK limits: EaR ≤ {ear_lim:.0f}% of projected NII, EVE ≤ {eve_lim:.0f}% of equity.")

with tabs[1]:
    st.markdown("**Repricing gap by bucket (KES B):**")
    g_rows=[{"Bucket":g["bucket"],"Assets (B)":g["assets_b"],"Liabilities (B)":g["liabilities_b"],
              "Gap (B)":g["gap_b"],"Cumulative (B)":g["cumulative_b"],
              "Position":("Asset-sensitive" if g["gap_b"]>0 else "Liability-sensitive")}
             for g in gaps]
    st.dataframe(pd.DataFrame(g_rows),use_container_width=True,hide_index=True)
    st.line_chart(pd.DataFrame({"Cumulative Gap (B)":[g["cumulative_b"] for g in gaps]},
                                index=[g["bucket"] for g in gaps]))

with tabs[2]:
    st.markdown("**CBK IRRBB Limits (configurable via Admin → Thresholds):**")
    st.info(f"EaR warning: {ear_wrn:.0f}% · EaR limit: {ear_lim:.0f}% · EVE limit: {eve_lim:.0f}%")
    st.caption("Adjust in Admin → Thresholds → Treasury. Changes apply immediately.")

with tabs[3]:
    st.markdown("**Methodology:**")
    st.markdown("""
    **Earnings at Risk (EaR):** Impact on Net Interest Income over the next 12 months under a rate shock.
    Formula: EaR = Repricing Gap × Rate Shock × Time Factor.

    **Economic Value of Equity (EVE):** Present value of all asset cash flows minus present value of
    all liability cash flows. Measures long-term interest rate sensitivity.

    **CBK Reference:** Prudential Guideline on Interest Rate Risk in the Banking Book (IRRBB), 2021.
    Banks must report EaR and EVE under at least 6 rate scenarios including +/-100bps, +/-200bps,
    and parallel shocks. Breaches must be reported to CBK within 5 business days.
    """)
