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
from utils.core_audit import audit_log
from utils.db import db as a2z_db

require_access("treasury_alm.alm")
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

tabs = st.tabs(["📊 Gap Analysis & Liquidity","💰 Funding","🏛️ ALCO","🚨 Contingency","➕ New Snapshot","⚙️ Config","📈 BSC"])

with tabs[0]:
    _liq_sub_tabs = st.tabs([
        "📊 Gap Analysis",
        "💧 LCR / NSFR (Standard #71, integrated v5.76)",
    ])

    with _liq_sub_tabs[0]:
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

    with _liq_sub_tabs[1]:
        # ── LCR / NSFR (Standard #71 Liquidity Risk, integrated v5.76) ──
        from utils.liquidity_risk import (
            LiquidityRiskEngine, HqlaHolding, CashFlowItem,
            FundingItem, AssetItem,
            HQLA_LEVELS, HQLA_HAIRCUT_PCT, INFLOW_CAP_PCT_OF_OUTFLOWS,
            LCR_MIN_PCT, NSFR_MIN_PCT, LCR_GREEN_MIN, NSFR_GREEN_MIN,
            OUTFLOW_RATES_PCT, INFLOW_RATES_PCT,
            ASF_FACTORS_PCT, RSF_FACTORS_PCT, LEVEL_2_TOTAL_CAP_PCT, LEVEL_2B_CAP_PCT,
        )
        from decimal import Decimal as _D_liq
        from utils.core_audit import audit_log

        st.markdown(
            f"**Standard #71 — Basel III Liquidity Coverage Ratio + Net Stable Funding Ratio**. "
            f"LCR ≥ {LCR_MIN_PCT}% (HQLA / 30-day net cash outflows). "
            f"NSFR ≥ {NSFR_MIN_PCT}% (Available Stable Funding / Required Stable Funding). "
            f"Inflows capped at {INFLOW_CAP_PCT_OF_OUTFLOWS}% of outflows per Basel III."
        )

        _lcr_nsfr_tabs = st.tabs(["💧 LCR (30-day stress)", "🏗️ NSFR (12-month stable funding)"])

        # ───── LCR ─────
        with _lcr_nsfr_tabs[0]:
            st.markdown("**Liquidity Coverage Ratio** = HQLA / Net Cash Outflows over 30-day stress.")

            with st.expander("HQLA holdings", expanded=True):
                hqla_c1, hqla_c2, hqla_c3 = st.columns(3)
                with hqla_c1:
                    lvl1 = st.number_input("Level 1 (KES B)",
                                            min_value=0.0, value=15.0, step=1.0,
                                            key="lcr_l1",
                                            help=f"Sovereign / cash / CB reserves. Haircut: {HQLA_HAIRCUT_PCT['LEVEL_1']}%")
                with hqla_c2:
                    lvl2a = st.number_input("Level 2A (KES B)",
                                             min_value=0.0, value=4.0, step=0.5,
                                             key="lcr_l2a",
                                             help=f"Sovereign 20% RW. Haircut: {HQLA_HAIRCUT_PCT['LEVEL_2A']}%")
                with hqla_c3:
                    lvl2b = st.number_input("Level 2B (KES B)",
                                             min_value=0.0, value=1.0, step=0.5,
                                             key="lcr_l2b",
                                             help=f"Corp BBB+. Haircut: {HQLA_HAIRCUT_PCT['LEVEL_2B']}%; cap {LEVEL_2B_CAP_PCT}%")

            with st.expander("Outflows (30-day stress)", expanded=True):
                ofl_c1, ofl_c2 = st.columns(2)
                with ofl_c1:
                    out_retail_stable = st.number_input(
                        f"Retail deposits stable @ {OUTFLOW_RATES_PCT['RETAIL_DEPOSITS_STABLE']}% (KES B)",
                        min_value=0.0, value=80.0, step=5.0, key="lcr_out_rs")
                    out_retail_less = st.number_input(
                        f"Retail less-stable @ {OUTFLOW_RATES_PCT['RETAIL_DEPOSITS_LESS_STABLE']}% (KES B)",
                        min_value=0.0, value=20.0, step=2.0, key="lcr_out_rls")
                    out_sme = st.number_input(
                        f"SME operational @ {OUTFLOW_RATES_PCT['SME_OPERATIONAL']}% (KES B)",
                        min_value=0.0, value=10.0, step=1.0, key="lcr_out_sme")
                with ofl_c2:
                    out_corp = st.number_input(
                        f"Corporate non-financial @ {OUTFLOW_RATES_PCT['CORPORATE_NON_FINANCIAL']}% (KES B)",
                        min_value=0.0, value=15.0, step=1.0, key="lcr_out_cn")
                    out_fin = st.number_input(
                        f"Financial counterparty @ {OUTFLOW_RATES_PCT['FINANCIAL_COUNTERPARTY']}% (KES B)",
                        min_value=0.0, value=5.0, step=1.0, key="lcr_out_fc")
                    out_undrawn = st.number_input(
                        f"Undrawn credit facilities @ {OUTFLOW_RATES_PCT['UNDRAWN_CREDIT_FACILITIES']}% (KES B)",
                        min_value=0.0, value=8.0, step=1.0, key="lcr_out_uc")

            with st.expander("Inflows (capped at 75% of outflows)"):
                inf_c1, inf_c2 = st.columns(2)
                with inf_c1:
                    in_retail = st.number_input(
                        f"Retail loan inflows @ {INFLOW_RATES_PCT['RETAIL_LOAN_INFLOWS']}% (KES B)",
                        min_value=0.0, value=2.0, step=0.5, key="lcr_in_r")
                    in_wholesale = st.number_input(
                        f"Wholesale loan inflows @ {INFLOW_RATES_PCT['WHOLESALE_LOAN_INFLOWS']}% (KES B)",
                        min_value=0.0, value=3.0, step=0.5, key="lcr_in_w")
                with inf_c2:
                    in_secured = st.number_input(
                        f"Secured lending @ {INFLOW_RATES_PCT['SECURED_LENDING']}% (KES B)",
                        min_value=0.0, value=1.0, step=0.5, key="lcr_in_s")

            if st.button("Compute LCR", key="lcr_btn", type="primary"):
                hqla_list = [
                    HqlaHolding("L1", "LEVEL_1", _D_liq(str(lvl1)) * _D_liq("1000000000")),
                    HqlaHolding("L2A", "LEVEL_2A", _D_liq(str(lvl2a)) * _D_liq("1000000000")),
                    HqlaHolding("L2B", "LEVEL_2B", _D_liq(str(lvl2b)) * _D_liq("1000000000")),
                ]
                flows = [
                    CashFlowItem("O1", "RETAIL_DEPOSITS_STABLE", "OUTFLOW",
                                  _D_liq(str(out_retail_stable)) * _D_liq("1000000000")),
                    CashFlowItem("O2", "RETAIL_DEPOSITS_LESS_STABLE", "OUTFLOW",
                                  _D_liq(str(out_retail_less)) * _D_liq("1000000000")),
                    CashFlowItem("O3", "SME_OPERATIONAL", "OUTFLOW",
                                  _D_liq(str(out_sme)) * _D_liq("1000000000")),
                    CashFlowItem("O4", "CORPORATE_NON_FINANCIAL", "OUTFLOW",
                                  _D_liq(str(out_corp)) * _D_liq("1000000000")),
                    CashFlowItem("O5", "FINANCIAL_COUNTERPARTY", "OUTFLOW",
                                  _D_liq(str(out_fin)) * _D_liq("1000000000")),
                    CashFlowItem("O6", "UNDRAWN_CREDIT_FACILITIES", "OUTFLOW",
                                  _D_liq(str(out_undrawn)) * _D_liq("1000000000")),
                    CashFlowItem("I1", "RETAIL_LOAN_INFLOWS", "INFLOW",
                                  _D_liq(str(in_retail)) * _D_liq("1000000000")),
                    CashFlowItem("I2", "WHOLESALE_LOAN_INFLOWS", "INFLOW",
                                  _D_liq(str(in_wholesale)) * _D_liq("1000000000")),
                    CashFlowItem("I3", "SECURED_LENDING", "INFLOW",
                                  _D_liq(str(in_secured)) * _D_liq("1000000000")),
                ]
                r = LiquidityRiskEngine.lcr(hqla_list, flows)
                lcr_pct = r.get("lcr_pct")
                status = r.get("status")
                compliant = r.get("compliant")
                color = {"GREEN":"#10B981","AMBER":"#F59E0B","RED":"#DC2626"}.get(status, "#6B7280")

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("LCR", f"{_D_liq(str(lcr_pct)):.2f}%",
                           delta=f"vs {LCR_MIN_PCT}% min")
                k2.metric("HQLA total", f"KES {_D_liq(str(r['hqla_total_kes']))/_D_liq('1000000000'):.2f}B")
                k3.metric("Net outflows (30d)",
                           f"KES {_D_liq(str(r['net_outflows_kes']))/_D_liq('1000000000'):.2f}B")
                with k4:
                    st.markdown(
                        f"<div style='padding:12px;background:{color}22;"
                        f"border-left:6px solid {color};border-radius:10px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>STATUS</div>"
                        f"<div style='font-size:24px;font-weight:800;color:{color}'>{status}</div></div>",
                        unsafe_allow_html=True)

                if compliant:
                    st.success(
                        f"✅ LCR {_D_liq(str(lcr_pct)):.2f}% meets the {LCR_MIN_PCT}% minimum.")
                else:
                    st.error(
                        f"⛔ LCR {_D_liq(str(lcr_pct)):.2f}% BREACHES the {LCR_MIN_PCT}% minimum. "
                        f"CBK supervisory action required per Basel III.")

                with st.expander("Per-bucket detail"):
                    nco = r.get("nco_breakdown", {})
                    st.write(f"- Total outflows: KES {_D_liq(str(nco.get('total_outflows_kes', 0)))/_D_liq('1000000000'):.2f}B")
                    st.write(f"- Total inflows: KES {_D_liq(str(nco.get('total_inflows_kes', 0)))/_D_liq('1000000000'):.2f}B")
                    st.write(f"- Capped inflows ({INFLOW_CAP_PCT_OF_OUTFLOWS}% of outflows): KES {_D_liq(str(nco.get('capped_inflows_kes', 0)))/_D_liq('1000000000'):.2f}B")
                    hb = r.get("hqla_breakdown", {})
                    if hb.get("cap_applied"):
                        st.warning("ℹ Level 2 cap applied (Level 2 ≤ 40% of total HQLA, Level 2B ≤ 15%).")

                audit_log("IFRS_ENGINE_USED", uname,
                           f"Liquidity #71: LCR {lcr_pct}%, status={status}, compliant={compliant}")

        # ───── NSFR ─────
        with _lcr_nsfr_tabs[1]:
            st.markdown("**Net Stable Funding Ratio** = Available Stable Funding / Required Stable Funding (12-month).")
            with st.expander("Available Stable Funding (liabilities)", expanded=True):
                asf_c1, asf_c2 = st.columns(2)
                with asf_c1:
                    asf_t1 = st.number_input(
                        f"Tier 1 capital @ {ASF_FACTORS_PCT['TIER_1_CAPITAL']}% (KES B)",
                        min_value=0.0, value=15.0, step=1.0, key="nsfr_t1")
                    asf_t2 = st.number_input(
                        f"Tier 2 capital @ {ASF_FACTORS_PCT['TIER_2_CAPITAL']}% (KES B)",
                        min_value=0.0, value=3.0, step=0.5, key="nsfr_t2")
                    asf_retail = st.number_input(
                        f"Retail deposits < 1Y @ {ASF_FACTORS_PCT['RETAIL_DEPOSITS_LT_1Y']}% (KES B)",
                        min_value=0.0, value=80.0, step=5.0, key="nsfr_retail")
                with asf_c2:
                    asf_wholesale = st.number_input(
                        f"Wholesale funding < 1Y @ {ASF_FACTORS_PCT['WHOLESALE_FUNDING_LT_1Y']}% (KES B)",
                        min_value=0.0, value=20.0, step=2.0, key="nsfr_whole")
                    asf_op = st.number_input(
                        f"Operational deposits @ {ASF_FACTORS_PCT['OPERATIONAL_DEPOSITS']}% (KES B)",
                        min_value=0.0, value=15.0, step=1.0, key="nsfr_op")

            with st.expander("Required Stable Funding (assets)", expanded=True):
                rsf_c1, rsf_c2 = st.columns(2)
                with rsf_c1:
                    rsf_cash = st.number_input(
                        f"Cash @ {RSF_FACTORS_PCT['CASH']}% (KES B)",
                        min_value=0.0, value=5.0, step=0.5, key="nsfr_cash")
                    rsf_l1 = st.number_input(
                        f"Level 1 HQLA @ {RSF_FACTORS_PCT['LEVEL_1_HQLA']}% (KES B)",
                        min_value=0.0, value=15.0, step=1.0, key="nsfr_l1")
                    rsf_retail_short = st.number_input(
                        f"Retail loans < 1Y @ {RSF_FACTORS_PCT['RETAIL_LOANS_LT_1Y']}% (KES B)",
                        min_value=0.0, value=10.0, step=1.0, key="nsfr_rl_lt1y")
                with rsf_c2:
                    rsf_corp_long = st.number_input(
                        f"Corporate loans ≥ 1Y @ {RSF_FACTORS_PCT['CORPORATE_LOANS_GTE_1Y']}% (KES B)",
                        min_value=0.0, value=40.0, step=2.0, key="nsfr_corp_gte1y")
                    rsf_mortgage = st.number_input(
                        f"Mortgage loans @ {RSF_FACTORS_PCT['MORTGAGE_LOANS']}% (KES B)",
                        min_value=0.0, value=25.0, step=2.0, key="nsfr_mortgage")

            if st.button("Compute NSFR", key="nsfr_btn", type="primary"):
                funding_list = [
                    FundingItem("F_T1", "TIER_1_CAPITAL",
                                 _D_liq(str(asf_t1)) * _D_liq("1000000000")),
                    FundingItem("F_T2", "TIER_2_CAPITAL",
                                 _D_liq(str(asf_t2)) * _D_liq("1000000000")),
                    FundingItem("F_R", "RETAIL_DEPOSITS_LT_1Y",
                                 _D_liq(str(asf_retail)) * _D_liq("1000000000")),
                    FundingItem("F_W", "WHOLESALE_FUNDING_LT_1Y",
                                 _D_liq(str(asf_wholesale)) * _D_liq("1000000000")),
                    FundingItem("F_O", "OPERATIONAL_DEPOSITS",
                                 _D_liq(str(asf_op)) * _D_liq("1000000000")),
                ]
                assets_list = [
                    AssetItem("A_C", "CASH",
                               _D_liq(str(rsf_cash)) * _D_liq("1000000000")),
                    AssetItem("A_L1", "LEVEL_1_HQLA",
                               _D_liq(str(rsf_l1)) * _D_liq("1000000000")),
                    AssetItem("A_RS", "RETAIL_LOANS_LT_1Y",
                               _D_liq(str(rsf_retail_short)) * _D_liq("1000000000")),
                    AssetItem("A_CL", "CORPORATE_LOANS_GTE_1Y",
                               _D_liq(str(rsf_corp_long)) * _D_liq("1000000000")),
                    AssetItem("A_M", "MORTGAGE_LOANS",
                               _D_liq(str(rsf_mortgage)) * _D_liq("1000000000")),
                ]
                r = LiquidityRiskEngine.nsfr(funding_list, assets_list)
                nsfr_pct = r.get("nsfr_pct")
                status = r.get("status")
                compliant = r.get("compliant")
                color = {"GREEN":"#10B981","AMBER":"#F59E0B","RED":"#DC2626"}.get(status, "#6B7280")

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("NSFR", f"{_D_liq(str(nsfr_pct)):.2f}%",
                           delta=f"vs {NSFR_MIN_PCT}% min")
                k2.metric("ASF total", f"KES {_D_liq(str(r['asf_kes']))/_D_liq('1000000000'):.2f}B")
                k3.metric("RSF total", f"KES {_D_liq(str(r['rsf_kes']))/_D_liq('1000000000'):.2f}B")
                with k4:
                    st.markdown(
                        f"<div style='padding:12px;background:{color}22;"
                        f"border-left:6px solid {color};border-radius:10px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>STATUS</div>"
                        f"<div style='font-size:24px;font-weight:800;color:{color}'>{status}</div></div>",
                        unsafe_allow_html=True)

                if compliant:
                    st.success(
                        f"✅ NSFR {_D_liq(str(nsfr_pct)):.2f}% meets the {NSFR_MIN_PCT}% minimum.")
                else:
                    st.error(
                        f"⛔ NSFR {_D_liq(str(nsfr_pct)):.2f}% BREACHES the {NSFR_MIN_PCT}% minimum. "
                        f"Mismatch between long-term assets and stable funding.")

                with st.expander("Per-category breakdown"):
                    asf_b = r.get("asf_breakdown", {}).get("by_category", {})
                    rsf_b = r.get("rsf_breakdown", {}).get("by_category", {})
                    if asf_b:
                        st.markdown("**Available Stable Funding (post-factor):**")
                        st.dataframe(pd.DataFrame([
                            {"Category": k, "Amount (KES B)": float(_D_liq(str(v))/_D_liq('1000000000'))}
                            for k, v in asf_b.items()
                        ]), hide_index=True, use_container_width=True)
                    if rsf_b:
                        st.markdown("**Required Stable Funding (post-factor):**")
                        st.dataframe(pd.DataFrame([
                            {"Category": k, "Amount (KES B)": float(_D_liq(str(v))/_D_liq('1000000000'))}
                            for k, v in rsf_b.items()
                        ]), hide_index=True, use_container_width=True)

                audit_log("IFRS_ENGINE_USED", uname,
                           f"Liquidity #71: NSFR {nsfr_pct}%, status={status}, compliant={compliant}")

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
