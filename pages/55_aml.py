"""pages/55_aml.py — AML Transaction Monitoring.
Alert management, STR filing, risk scoring. Thresholds via Admin.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
        audit_log("BSC_AUTO_UPDATE", username, f"Module action: {kpi}")
    except Exception:
        pass


require_access("compliance_regulatory.aml")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_aml   = any(x in role for x in ("compliance","aml","mlro","risk","chief compliance","money laundering"))

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>🔍 AML Transaction Monitoring</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Alerts · STR filing · Risk scoring · Case management</span></div>", unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"aml_alerts.json"
    return a2z_db.load_json(p) if p.exists() else []

_raw_alerts = _load()
# Normalise Decimal types from PostgreSQL
from decimal import Decimal as _D
alerts = []
for _a in _raw_alerts:
    _a2 = {k: float(v) if isinstance(v, _D) else v for k, v in _a.items()}
    alerts.append(_a2)
HIGH_THR  = cfg("aml_high_risk_score", 70)
CASH_THR  = cfg("aml_cash_threshold_m", 1.0)

high_risk = [a for a in alerts if a.get("risk_score",0) >= HIGH_THR]
open_alts = [a for a in alerts if a.get("status","") in ("Open","Under Review","Escalated to STR")]
strs      = [a for a in alerts if a.get("str_filed")]

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Alerts",  len(alerts))
m2.metric("Open / Active", len(open_alts), delta_color="normal" if not open_alts else "inverse")
m3.metric("High Risk (≥"+str(HIGH_THR)+")", len(high_risk), delta_color="normal" if not high_risk else "inverse")
m4.metric("STRs Filed",    len(strs))

if [a for a in high_risk if a.get("status")=="Open"]:
    st.error(f"🔴 {sum(1 for a in high_risk if a['status']=='Open')} high-risk alerts unassigned — assign immediately")

# ─────────────────────────────────────────────────────────────────
# v7.8: AML Health Composite (composite_scores.py surfacing)
# ─────────────────────────────────────────────────────────────────
with st.expander("📊 AML Health Composite (v7.5 / v7.8 surfaced)", expanded=False):
    from utils.composite_scores import aml_health_composite
    from utils.system_stocks import get_stock_snapshot

    st.caption(
        "v7.8 surfacing of `composite_scores.aml_health_composite()` on this "
        "domain page (per Charter §13). Composes 4 signals — KYC band stability "
        "(LIVE from `customer_base` stock) + alert disposition + SAR conversion "
        "rate + transaction velocity stability — into a single 0-100 score with "
        "HEALTHY / MODERATE / LOW severity bands."
    )

    cb_snap = get_stock_snapshot("customer_base")
    kyc_dist = cb_snap.get("by_kyc_risk_band_count", {})

    # Compute alert disposition LIVE from page's alerts state
    alert_total = len(alerts)
    alert_open = sum(1 for a in alerts if a.get("status") in ("Open", "Active"))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Inputs:**")
        st.markdown(f"- KYC distribution: {kyc_dist} *(LIVE from `customer_base` stock)*")
        st.markdown(f"- Total alerts on this page: **{alert_total}**, "
                    f"open: **{alert_open}** *(LIVE from page state)*")
        aml_sar = st.slider("SAR conversion rate %", 0.0, 30.0, 10.0, 0.5,
                             key="aml_health_sar")
        aml_velocity = st.slider("Txn velocity change %", -50.0, 50.0, 2.0, 1.0,
                                  key="aml_health_velocity")

    with c2:
        # Build alert_summary in the shape the composite expects
        alert_summary = {
            "total_alerts": alert_total,
            "by_status": {"OPEN": alert_open,
                          "DISMISSED": max(0, alert_total - alert_open)},
        }

        aml_result = aml_health_composite(
            kyc_band_distribution=kyc_dist,
            alert_summary=alert_summary,
            sar_conversion_pct=float(aml_sar),
            txn_velocity_change_pct=float(aml_velocity),
        )
        aml_score = aml_result.get("score")
        aml_severity = aml_result.get("severity")
        sev_color = {"HEALTHY": "✅", "MODERATE": "🟡",
                     "LOW": "🚨", "UNKNOWN": "⚠"}.get(aml_severity, "")
        st.metric("AML Health score",
                  f"{aml_score:.1f}/100" if aml_score is not None else "—",
                  aml_severity)
        st.markdown(f"**{sev_color} {aml_severity}**")

        if aml_result.get("components"):
            st.markdown("**Component scores:**")
            for k, v in aml_result["components"].items():
                st.markdown(f"- `{k}`: {v:.1f}")

tabs = st.tabs([
    "🔴 High Risk",
    "📋 All Alerts",
    "📊 Analytics",
    "📝 New Alert",
    "📄 STR Log",
    "🛡️ Customer KYC Risk (Standard #36)",
    "📊 Portfolio Risk Summary (Standard #36)",
])

_aml_render_count = [0]  # unique key counter

def _render(alert_list, show_update=True):
    if not alert_list: st.success("None here."); return
    rows=[{"ID":a["id"],"Account":a["account_number"][:18],"Rule":a["rule_triggered"][:35],
            "Amount (M)":round(a["amount"]/1e6,2),"Risk Score":a["risk_score"],
            "Level":a["risk_level"],"Status":a["status"][:20],
            "Assigned":a.get("assigned_to","")[:20],"Date":a["transaction_date"][:10],
            "STR":("✅" if a.get("str_filed") else "")}
           for a in sorted(alert_list,key=lambda x:-x.get("risk_score",0))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    if show_update and (is_aml or is_admin) and alert_list:
        _aml_render_count[0] += 1
        _uid = _aml_render_count[0]
        st.markdown("**Update alert:**")
        sel = st.selectbox("Select alert", [a["id"] for a in alert_list],
                           key=f"aml_sel_{_uid}")
        new_status = st.selectbox("New status",
                                   ["Open","Under Review","Cleared","Escalated to STR","Closed-No Action"],
                                   key=f"aml_stat_{_uid}")
        str_filed  = st.checkbox("File STR", key=f"aml_str_{_uid}")
        notes      = st.text_input("Notes",  key=f"aml_note_{_uid}")
        if st.button("💾 Save", key=f"aml_save_{_uid}", type="primary"):
            all_a = json.loads((DATA/"aml_alerts.json").read_text())
            for a in all_a:
                if a["id"]==sel:
                    a["status"]=new_status; a["str_filed"]=str_filed
                    if notes: a["notes"]=notes; a["updated_at"]=str(today)
            (DATA/"aml_alerts.json").write_text(json.dumps(all_a,indent=2))
            audit_log("AML_ALERT_UPDATED",uname,f"{sel}: {new_status}")
            _bsc_trigger(uname, "K049")
            st.cache_data.clear(); st.success("✅ Updated"); st.rerun()

with tabs[0]: _render(high_risk)
with tabs[1]:
    f1,f2 = st.columns(2)
    flevel = f1.selectbox("Risk Level",["All","High","Medium","Low"],key="aml_lev")
    fstat  = f2.selectbox("Status",["All","Open","Under Review","Cleared","Escalated to STR","Closed-No Action"],key="aml_st")
    vis = [a for a in alerts if (flevel=="All" or a["risk_level"]==flevel) and (fstat=="All" or a["status"]==fstat)]
    _render(vis)

with tabs[2]:
    rule_ct = Counter(a["rule_triggered"] for a in alerts)
    st.markdown("**Top triggered rules:**")
    st.bar_chart(pd.DataFrame({"Alerts":dict(rule_ct.most_common(8))}).T.T)
    st.markdown("**Risk level distribution:**")
    lev_ct = Counter(a["risk_level"] for a in alerts)
    for lev,n in lev_ct.most_common():
        st.markdown(f"  {lev}: {n}")

with tabs[3]:
    if is_aml or is_admin:
        r1,r2,r3 = st.columns(3)
        _acct = r1.text_input("Account number",key="aml_nacct")
        _rule = r2.selectbox("Rule triggered",
            ["Cash transaction >KES 1M","Rapid movement of funds","Structuring","Cross-border transfer",
             "PEP transaction","Dormant account","Round-sum","High-risk jurisdiction","Other"],key="aml_nrule")
        _amt  = r3.number_input("Amount (KES M)",0.1,500.0,1.0,key="aml_namt")
        _score= st.slider("Risk score",1,100,65,key="aml_nscore")
        _notes= st.text_area("Description",height=60,key="aml_ndesc")
        if st.button("⚠️ Raise alert",key="aml_raise",type="primary"):
            if _acct.strip():
                all_a = json.loads((DATA/"aml_alerts.json").read_text())
                all_a.append({"id":f"AML{len(all_a)+1:05d}","account_number":_acct.strip(),
                               "customer_name":"","transaction_date":str(today),
                               "amount":_amt*1e6,"transaction_type":"Manual","rule_triggered":_rule,
                               "risk_score":_score,"risk_level":("High" if _score>=HIGH_THR else "Medium" if _score>=50 else "Low"),
                               "status":"Open","assigned_to":uname,"str_filed":False,"str_reference":"",
                               "notes":_notes,"created_at":str(today),"updated_at":str(today)})
                (DATA/"aml_alerts.json").write_text(json.dumps(all_a,indent=2))
                audit_log("AML_ALERT_RAISED",uname,f"Rule: {_rule}")
                st.cache_data.clear(); st.success("✅ Alert raised"); st.rerun()
            else: st.error("Account number required.")
    else: st.info("Alert creation available to Compliance team.")

with tabs[4]:
    st.markdown("**Suspicious Transaction Reports (STR) filed:**")
    if strs:
        str_rows=[{"ID":a["id"],"STR Reference":a.get("str_reference",""),"Account":a["account_number"][:18],
                    "Amount (M)":round(a["amount"]/1e6,2),"Rule":a["rule_triggered"][:30],"Date":a["transaction_date"][:10]}
                   for a in strs]
        st.dataframe(pd.DataFrame(str_rows),use_container_width=True,hide_index=True)
        st.caption("STRs must be filed with the Financial Reporting Centre (FRC) within 3 days of suspicion.")
    else: st.info("No STRs filed.")


# ════════════════════════════════════════════════════════════════
# TAB 6 — CUSTOMER KYC RISK ASSESSMENT (Standard #36, integrated v5.86)
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    from utils.kyc_aml_risk import (
        KycAmlRiskEngine, KycRiskAssessment,
        CDD_LEVEL_BY_BAND, CHANNEL_PTS, CUSTOMER_TYPE_PTS,
        GEOGRAPHY_HIGH_PTS, GEOGRAPHY_LOW_PTS, GEOGRAPHY_MEDIUM_PTS,
        GEOGRAPHY_PROHIBITED_PTS, HIGH_RISK_JURISDICTIONS,
        HIGH_VELOCITY_AMOUNT_KES_30D, HIGH_VELOCITY_TXN_COUNT_30D,
        MEDIUM_RISK_JURISDICTIONS, PRODUCT_PTS, PROHIBITED_JURISDICTIONS,
        RISK_BAND_HIGH_MAX, RISK_BAND_LOW_MAX, RISK_BAND_MEDIUM_MAX,
        RISK_BAND_PROHIBITED_MIN, STRUCTURING_THRESHOLD_KES,
    )

    st.markdown(
        f"**Standard #36 — KYC/AML Risk Engine** (FATF + CBK PG/05 aligned). "
        f"5-component customer risk scoring → 4 risk bands "
        f"(LOW≤{RISK_BAND_LOW_MAX} · MEDIUM≤{RISK_BAND_MEDIUM_MAX} · "
        f"HIGH≤{RISK_BAND_HIGH_MAX} · PROHIBITED≥{RISK_BAND_PROHIBITED_MIN})."
    )
    st.caption(
        f"Auto-prohibition triggers: sanctions list hit, jurisdiction in "
        f"{PROHIBITED_JURISDICTIONS}, or composite score ≥{RISK_BAND_PROHIBITED_MIN}. "
        f"CDD escalates with band: SIMPLIFIED → STANDARD → ENHANCED → ONBOARDING_REJECTED."
    )

    kyc_sub_tabs = st.tabs([
        "🔍 Single Customer Assessment",
        "🌍 Geography Reference",
        "📦 Product Risk Reference",
        "👤 Customer Type Reference",
        "🌳 Engine Reference",
        "📦 KYC Depth (#36, v6.1)",
    ])

    # ──────── Single customer assessment ────────
    with kyc_sub_tabs[0]:
        st.markdown(
            "**Assess one customer profile** — engine evaluates 5 components "
            "(geography, product, customer type, channel, behavior) and assigns "
            "risk band + CDD level.")
        st.caption(
            "💡 Tip: provide BOTH `country_code` (residence) AND `citizenship_code` "
            "for accurate geography scoring — engine takes MAX of the two.")

        c1, c2 = st.columns(2)
        with c1:
            kyc_id = st.text_input("Customer ID",
                                     value="CUST_2026_001", key="kyc_id")
            kyc_country = st.text_input("Country of residence (ISO-2)",
                                          value="KE", max_chars=2,
                                          key="kyc_country",
                                          help="ISO-2 country code, e.g. KE, GB, US.")
            kyc_citizen = st.text_input("Citizenship (ISO-2)",
                                          value="KE", max_chars=2,
                                          key="kyc_citizen",
                                          help="Leave equal to country if same; "
                                                "engine takes MAX of the two scores.")
            kyc_type = st.selectbox("Customer type",
                                       ["INDIVIDUAL_RESIDENT",
                                        "PEP_FOREIGN", "PEP_DOMESTIC", "NGO_NPO",
                                        "HIGH_NET_WORTH", "BEARER_SHARE_ENTITY",
                                        "INDIVIDUAL_NON_RESIDENT", "SME_RESIDENT",
                                        "CORPORATE_RESIDENT", "TRUST"],
                                       key="kyc_type",
                                       help="Engine recognizes 10 standard types; "
                                            "unknown types default to medium risk.")

        with c2:
            kyc_channel = st.selectbox("Onboarding channel",
                                          list(CHANNEL_PTS.keys()),
                                          index=0, key="kyc_channel")
            kyc_pep = st.checkbox("PEP flag",
                                    value=False, key="kyc_pep",
                                    help="Politically Exposed Person — heightens scrutiny.")
            kyc_sanc = st.checkbox("Sanctions list hit",
                                     value=False, key="kyc_sanc",
                                     help="⛔ Auto-prohibits onboarding.")

        st.markdown("**Products** (select all that apply):")
        product_options = list(PRODUCT_PTS.keys()) + ["SAVINGS", "CURRENT", "FX", "CARDS"]
        kyc_products = st.multiselect("Products held",
                                         product_options,
                                         default=["SAVINGS"],
                                         key="kyc_products",
                                         help="Engine takes MAX risk product (not sum).")

        with st.expander("Optional: 30-day behavior data"):
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                kyc_txn_count = st.number_input(
                    "Transaction count (30d)",
                    min_value=0, value=0, step=1, key="kyc_txn_count",
                    help=f"≥{HIGH_VELOCITY_TXN_COUNT_30D} flags high velocity")
            with bc2:
                kyc_txn_amt = st.number_input(
                    "Transaction amount (KES M, 30d)",
                    min_value=0.0, value=0.0, step=1.0, key="kyc_txn_amt",
                    help=f"≥KES {HIGH_VELOCITY_AMOUNT_KES_30D/1e6:.0f}M flags high velocity")
            with bc3:
                kyc_struct = st.number_input(
                    "Structured deposits count (30d)",
                    min_value=0, value=0, step=1, key="kyc_struct",
                    help=f"≥3 just-under-{STRUCTURING_THRESHOLD_KES/1e6:.0f}M deposits = structuring flag")

        if st.button("🛡️ Assess KYC risk",
                       key="kyc_assess_btn", type="primary"):
            customer = {
                "customer_id": kyc_id,
                "country_code": kyc_country.upper().strip() if kyc_country.strip() else None,
                "citizenship_code": kyc_citizen.upper().strip() if kyc_citizen.strip() else None,
                "customer_type": kyc_type,
                "products": kyc_products if kyc_products else None,
                "onboarding_channel": kyc_channel,
                "pep_flag": kyc_pep,
                "sanctions_hit": kyc_sanc,
            }
            # Behavior block only if user provided data
            if (kyc_txn_count > 0 or kyc_txn_amt > 0 or kyc_struct > 0):
                customer["behavior"] = {
                    "txn_count_30d": int(kyc_txn_count),
                    "txn_amount_kes_30d": int(kyc_txn_amt * 1_000_000),
                    "structured_deposits_count_30d": int(kyc_struct),
                }

            r = KycAmlRiskEngine.assess_customer(customer)

            # Verdict banner
            band_colors = {
                "LOW": "#10B981",
                "MEDIUM": "#3B82F6",
                "HIGH": "#F59E0B",
                "PROHIBITED": "#DC2626",
            }
            color = band_colors.get(r.risk_band, "#6B7280")

            st.markdown(
                f"<div style='padding:18px;background:{color}22;"
                f"border-left:6px solid {color};border-radius:12px'>"
                f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                f"OVERALL ASSESSMENT</div>"
                f"<div style='font-size:32px;font-weight:800;color:{color};margin-top:6px'>"
                f"{r.risk_band} (score {r.risk_score})</div>"
                f"<div style='font-size:14px;margin-top:6px'>"
                f"CDD Level: <b>{r.cdd_level}</b></div></div>",
                unsafe_allow_html=True)

            # Auto-prohibit banner
            if r.auto_prohibited:
                st.error(
                    f"⛔ **AUTO-PROHIBITED** — reason: `{r.auto_prohibited_reason}`. "
                    "Onboarding rejected per CBK PG/05. Escalate to MLRO.")

            # Component scores breakdown
            comp_rows = []
            for comp, pts in r.component_scores.items():
                reason = r.component_reasons.get(comp, "—")
                comp_rows.append({
                    "Component": comp.replace("_", " ").title(),
                    "Points": pts,
                    "Reason": reason,
                })
            st.markdown("**Component breakdown:**")
            st.dataframe(pd.DataFrame(comp_rows),
                         use_container_width=True, hide_index=True)

            # Flags
            if r.pep_flag or r.sanctions_flag:
                st.markdown("**Flags:**")
                if r.pep_flag:
                    st.warning(
                        "🚨 **PEP flag** — Politically Exposed Person. "
                        "Senior management approval required for onboarding "
                        "(Enhanced Due Diligence + ongoing monitoring per FATF Rec. 12).")
                if r.sanctions_flag:
                    st.error(
                        "⛔ **Sanctions list hit** — onboarding prohibited. "
                        "File Suspicious Transaction Report (STR) with FRC within 3 days.")

            # Guidance based on band
            if r.risk_band == "LOW":
                st.success(
                    "✅ **Low risk** — Simplified Due Diligence acceptable. "
                    "Standard ID verification + monitoring.")
            elif r.risk_band == "MEDIUM":
                st.info(
                    "ℹ **Medium risk** — Standard Due Diligence required. "
                    "Verify identity, source of funds, ongoing transaction monitoring.")
            elif r.risk_band == "HIGH":
                st.warning(
                    "⚠ **High risk** — Enhanced Due Diligence required. "
                    "Senior approval before onboarding, source-of-wealth verification, "
                    "more frequent reviews (annually or sooner).")

            audit_log("IFRS_ENGINE_USED", uname,
                       f"KYC #36: {kyc_id} score={r.risk_score} band={r.risk_band} "
                       f"cdd={r.cdd_level} auto_prohibited={r.auto_prohibited}")

    # ──────── Geography reference ────────
    with kyc_sub_tabs[1]:
        st.markdown(
            "**Geography Risk Reference** (FATF + CBK PG/05 aligned)")
        st.caption(
            "Engine takes MAX of country_code + citizenship_code. "
            "Missing geography defaults to MEDIUM (15 pts) — Rule 6: "
            "absent data is NOT zero-risk.")

        geo_rows = []
        for cc in PROHIBITED_JURISDICTIONS:
            geo_rows.append({"ISO-2": cc, "Risk tier": "🚫 PROHIBITED",
                              "Points": GEOGRAPHY_PROHIBITED_PTS,
                              "Action": "Onboarding rejected"})
        for cc in HIGH_RISK_JURISDICTIONS:
            geo_rows.append({"ISO-2": cc, "Risk tier": "🔴 HIGH RISK",
                              "Points": GEOGRAPHY_HIGH_PTS,
                              "Action": "Enhanced Due Diligence"})
        for cc in MEDIUM_RISK_JURISDICTIONS:
            geo_rows.append({"ISO-2": cc, "Risk tier": "🟡 MEDIUM RISK",
                              "Points": GEOGRAPHY_MEDIUM_PTS,
                              "Action": "Standard Due Diligence"})
        geo_rows.append({"ISO-2": "(missing)", "Risk tier": "🟡 PENDING KYC",
                          "Points": GEOGRAPHY_MEDIUM_PTS,
                          "Action": "Complete KYC first"})
        geo_rows.append({"ISO-2": "(any other)", "Risk tier": "🟢 LOW RISK",
                          "Points": GEOGRAPHY_LOW_PTS,
                          "Action": "Simplified Due Diligence"})
        st.dataframe(pd.DataFrame(geo_rows),
                     use_container_width=True, hide_index=True)

        st.caption(
            f"Bound byte-for-byte: GEOGRAPHY_PROHIBITED_PTS={GEOGRAPHY_PROHIBITED_PTS}, "
            f"GEOGRAPHY_HIGH_PTS={GEOGRAPHY_HIGH_PTS}, "
            f"GEOGRAPHY_MEDIUM_PTS={GEOGRAPHY_MEDIUM_PTS}, "
            f"GEOGRAPHY_LOW_PTS={GEOGRAPHY_LOW_PTS}.")

    # ──────── Product risk reference ────────
    with kyc_sub_tabs[2]:
        st.markdown("**Product Risk Reference** (engine takes MAX risk product, not sum)")

        prod_rows = []
        for prod, pts in sorted(PRODUCT_PTS.items(), key=lambda x: -x[1]):
            tier = ("🔴 HIGH" if pts >= 20 else
                    "🟡 MEDIUM" if pts >= 10 else
                    "🟢 LOW")
            prod_rows.append({"Product": prod, "Tier": tier, "Points": pts})
        st.dataframe(pd.DataFrame(prod_rows),
                     use_container_width=True, hide_index=True)

        st.caption(
            "Products NOT in this list (e.g. SAVINGS, CURRENT) score 0. "
            "Unknown products score 5 (pending review per Rule 6).")

    # ──────── Customer type reference ────────
    with kyc_sub_tabs[3]:
        st.markdown(
            "**Customer Type Reference** (PEP_FOREIGN, PEP_DOMESTIC, NGO_NPO etc.)")

        type_rows = []
        for ct, pts in sorted(CUSTOMER_TYPE_PTS.items(), key=lambda x: -x[1]):
            tier = ("🔴 HIGH" if pts >= 15 else
                    "🟡 MEDIUM" if pts >= 10 else
                    "🟢 LOW")
            type_rows.append({"Customer Type": ct, "Tier": tier, "Points": pts})
        st.dataframe(pd.DataFrame(type_rows),
                     use_container_width=True, hide_index=True)

        st.caption(
            "Unknown customer_type defaults to 10 pts (medium-risk pending KYC, Rule 6). "
            "Unrecognized strings (e.g. 'INDIVIDUAL_RESIDENT' if not in dict) "
            "also score 10 with reason 'customer_type_unrecognized'.")

    # ──────── Engine reference ────────
    with kyc_sub_tabs[4]:
        st.markdown("**Engine Constants Reference** (single source of truth)")

        st.markdown("**Risk band thresholds:**")
        band_rows = [
            {"Band": "🟢 LOW", "Score range": f"0-{RISK_BAND_LOW_MAX}",
              "CDD Level": CDD_LEVEL_BY_BAND["LOW"]},
            {"Band": "🔵 MEDIUM",
              "Score range": f"{RISK_BAND_LOW_MAX+1}-{RISK_BAND_MEDIUM_MAX}",
              "CDD Level": CDD_LEVEL_BY_BAND["MEDIUM"]},
            {"Band": "🟡 HIGH",
              "Score range": f"{RISK_BAND_MEDIUM_MAX+1}-{RISK_BAND_HIGH_MAX}",
              "CDD Level": CDD_LEVEL_BY_BAND["HIGH"]},
            {"Band": "🔴 PROHIBITED",
              "Score range": f"≥{RISK_BAND_PROHIBITED_MIN}",
              "CDD Level": CDD_LEVEL_BY_BAND["PROHIBITED"]},
        ]
        st.dataframe(pd.DataFrame(band_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Channel risk:**")
        chan_rows = [
            {"Channel": ch, "Points": pts}
            for ch, pts in CHANNEL_PTS.items()
        ]
        st.dataframe(pd.DataFrame(chan_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Behavior thresholds:**")
        beh_rows = [
            {"Trigger": f"Structured deposits ≥3 (just under KES {STRUCTURING_THRESHOLD_KES/1e6:.0f}M)",
              "Points": 5},
            {"Trigger": f"High velocity count ≥{HIGH_VELOCITY_TXN_COUNT_30D} txns/30d",
              "Points": 3},
            {"Trigger": f"High velocity amount ≥KES {HIGH_VELOCITY_AMOUNT_KES_30D/1e6:.0f}M/30d",
              "Points": 2},
        ]
        st.dataframe(pd.DataFrame(beh_rows),
                     use_container_width=True, hide_index=True)
        st.caption(
            "Behavior score is capped at 10 even if all 3 flags trigger "
            "(5+3+2=10 hit cap).")

    # ════════════════════════════════════════════════════════════════
    # KYC_SUB_TABS[5]: KYC Depth (Standard #36, integrated v6.1)
    # ════════════════════════════════════════════════════════════════
    with kyc_sub_tabs[5]:
        st.markdown(
            "**KYC Depth analysis** — extends v5.86 with 4 inner views "
            "following the proven depth-batch template (5th application after "
            "v5.95 CLV + v5.97 Compensation + v5.98 Engagement + v5.99 RCSA).")
        st.caption(
            "💡 v5.86 surfaces single-customer assessment + reference tabs. "
            "v6.1 adds: portfolio scorecard, batch assessment, jurisdiction "
            "concentration map, and risk-band investment ranking.")

        _kyc_depth_inner = st.tabs([
            "📋 KYC Executive Scorecard",
            "🎯 Customer Assessment Batch",
            "🌐 Jurisdiction Concentration Map",
            "🎚️ Risk Component Investment Map",
        ])

        # ────────── Inner[0]: KYC Executive Scorecard ──────────
        with _kyc_depth_inner[0]:
            st.markdown(
                "**KYC Executive Scorecard** — composes assess_customer + "
                "portfolio_risk_summary into single-screen GREEN/AMBER/RED "
                "verdict for board compliance committee reporting.")
            st.caption(
                "Mirrors v5.97/v5.98/v5.99 scorecard pattern. Click compute "
                "to refresh from synthetic 12-customer book.")

            if st.button("📋 Compute KYC scorecard",
                           key="kyc_es_btn", type="primary"):
                # Synthetic 12-customer book
                kyc_es_book = [
                    {"customer_id": "C001", "customer_type": "INDIVIDUAL",
                      "country_code": "KE", "products": ["RETAIL"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 800000, "txn_count_30d": 8},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C002", "customer_type": "PEP_DOMESTIC",
                      "country_code": "KE", "products": ["PRIVATE_BANKING"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 30000000, "txn_count_30d": 25},
                      "pep_flag": True, "sanctions_hit": False},
                    {"customer_id": "C003", "customer_type": "HIGH_NET_WORTH",
                      "country_code": "KE", "products": ["WEALTH_MANAGEMENT"],
                      "onboarding_channel": "MOBILE_APP_VIDEO_KYC",
                      "behavior": {"txn_amount_kes_30d": 60000000, "txn_count_30d": 60},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C004", "customer_type": "PEP_FOREIGN",
                      "country_code": "AF", "products": ["CORRESPONDENT_BANKING"],
                      "onboarding_channel": "NON_FACE_TO_FACE",
                      "behavior": {"txn_amount_kes_30d": 80000000, "txn_count_30d": 70},
                      "pep_flag": True, "sanctions_hit": False},
                    {"customer_id": "C005", "customer_type": "INDIVIDUAL",
                      "country_code": "PK", "products": ["RETAIL"],
                      "onboarding_channel": "AGENT_BANKING",
                      "behavior": {"txn_amount_kes_30d": 500000, "txn_count_30d": 5},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C006", "customer_type": "NGO_NPO",
                      "country_code": "KE", "products": ["CASH_INTENSIVE"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 20000000, "txn_count_30d": 30},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C007", "customer_type": "INDIVIDUAL",
                      "country_code": "KP", "products": ["RETAIL"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 100000, "txn_count_30d": 1},
                      "pep_flag": False, "sanctions_hit": False},  # PROHIBITED
                    {"customer_id": "C008",
                      "customer_type": "BEARER_SHARE_ENTITY",
                      "country_code": "TR", "products": ["TRADE_FINANCE"],
                      "onboarding_channel": "INTRODUCED_THIRD_PARTY",
                      "behavior": {"txn_amount_kes_30d": 25000000, "txn_count_30d": 20},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C009", "customer_type": "INDIVIDUAL",
                      "country_code": "KE", "products": ["RETAIL"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 200000, "txn_count_30d": 3},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C010", "customer_type": "INDIVIDUAL",
                      "country_code": "KE", "products": ["RETAIL"],
                      "onboarding_channel": "MOBILE_APP_VIDEO_KYC",
                      "behavior": {"txn_amount_kes_30d": 1500000, "txn_count_30d": 12},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C011", "customer_type": "INDIVIDUAL",
                      "country_code": "KE", "products": ["RETAIL"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 0, "txn_count_30d": 0},
                      "pep_flag": False, "sanctions_hit": True},  # SANCTIONS
                    {"customer_id": "C012", "customer_type": "PEP_DOMESTIC",
                      "country_code": "KE", "products": ["PRIVATE_BANKING"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 5000000, "txn_count_30d": 15},
                      "pep_flag": True, "sanctions_hit": False},
                ]

                kyc_es_assessments = [KycAmlRiskEngine.assess_customer(c)
                                        for c in kyc_es_book]
                kyc_es_summary = KycAmlRiskEngine.portfolio_risk_summary(
                    kyc_es_assessments)

                # === Section 1️⃣: Risk Band Distribution ===
                st.markdown("### 1️⃣ Risk band distribution")
                by_band = kyc_es_summary.get("by_band", {})
                low = int(by_band.get("LOW", 0))
                med = int(by_band.get("MEDIUM", 0))
                high = int(by_band.get("HIGH", 0))
                proh = int(by_band.get("PROHIBITED", 0))
                total = int(kyc_es_summary.get("total_customers", 0))

                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("Total", total)
                k2.metric("LOW ✅", low)
                k3.metric("MEDIUM ⚠", med)
                k4.metric("HIGH 🟠", high,
                            delta_color="inverse" if high > 0 else "normal")
                k5.metric("PROHIBITED 🚨", proh,
                            delta_color="inverse" if proh > 0 else "normal")

                # === Section 2️⃣: Special Flags ===
                st.markdown("### 2️⃣ PEP / Sanctions / Auto-prohibited flags")
                pep_n = int(kyc_es_summary.get("pep_count", 0))
                sanc_n = int(kyc_es_summary.get("sanctions_count", 0))
                auto_proh = int(kyc_es_summary.get("auto_prohibited_count", 0))
                f1, f2, f3 = st.columns(3)
                f1.metric("PEP customers", pep_n,
                            help="Politically exposed persons require EDD.")
                f2.metric("Sanctions hits", sanc_n,
                            delta_color="inverse" if sanc_n > 0 else "normal",
                            help="Auto-prohibited per AML/CFT regulations.")
                f3.metric("Auto-prohibited", auto_proh,
                            delta_color="inverse" if auto_proh > 0 else "normal",
                            help="Cannot be onboarded — engine surfaces reason.")

                # === Section 3️⃣: CDD Workload ===
                st.markdown("### 3️⃣ CDD workload distribution")
                edd_required = high  # HIGH band → EDD
                sdd_eligible = low   # LOW band → SDD (simplified)
                std_required = med   # MEDIUM band → standard
                rejected = proh

                w1, w2, w3, w4 = st.columns(4)
                w1.metric("SDD (simplified)", sdd_eligible,
                            help="Streamlined onboarding — basic ID + address.")
                w2.metric("Standard CDD", std_required)
                w3.metric("Enhanced CDD", edd_required,
                            help="Full source-of-funds verification + senior approval.")
                w4.metric("Rejected (PROHIBITED)", rejected,
                            delta_color="inverse" if rejected > 0 else "normal")

                # === Section 4️⃣: Overall scorecard verdict ===
                st.markdown("### 4️⃣ Overall KYC verdict")
                issues = []
                if proh > 0:
                    issues.append(
                        f"{proh} prohibited customer(s) — cannot be onboarded")
                if sanc_n > 0:
                    issues.append(f"{sanc_n} sanctions hit(s)")
                pep_pct = (pep_n / total * 100) if total else 0
                if pep_pct > 10:
                    issues.append(
                        f"PEP concentration high ({pep_pct:.0f}% of book)")
                high_pct = (high / total * 100) if total else 0
                if high_pct > 25:
                    issues.append(
                        f"HIGH-risk concentration excessive ({high_pct:.0f}%)")

                if not issues:
                    st.success(
                        "✅ **KYC health: GREEN.** All metrics in healthy "
                        "ranges. Maintain via annual re-KYC + transaction "
                        "monitoring.")
                elif len(issues) <= 1:
                    st.warning(
                        f"⚠ **KYC health: AMBER.** Issue: {issues[0]}. "
                        "Compliance review recommended.")
                else:
                    st.error(
                        f"🚨 **KYC health: RED.** Multiple issues: "
                        f"{'; '.join(issues)}. Compliance committee "
                        "escalation + onboarding policy review required.")

                audit_log("AML_ENGINE_USED", uname,
                            f"KYC #36 (depth): scorecard total={total} "
                            f"high={high} prohibited={proh} pep={pep_n} "
                            f"sanctions={sanc_n} issues={len(issues)}")

        # ────────── Inner[1]: Customer Assessment Batch ──────────
        with _kyc_depth_inner[1]:
            st.markdown(
                "**Customer Assessment Batch** — runs assess_customer across "
                "a 12-customer synthetic book, sorted by risk score desc. "
                "v5.86 surfaces single-customer assessment; this batch view "
                "enables onboarding-pipeline + annual re-KYC review.")
            st.caption(
                "Useful for: monthly compliance committee onboarding review, "
                "annual re-KYC cycles, identifying which customers need "
                "Enhanced Due Diligence vs streamlined.")

            if st.button("🎯 Run customer assessment batch",
                           key="kyc_cab_btn", type="primary"):
                # Reuse the same synthetic book
                kyc_cab_book = [
                    {"customer_id": "C001", "customer_type": "INDIVIDUAL",
                      "country_code": "KE", "products": ["RETAIL"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 800000, "txn_count_30d": 8},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C002", "customer_type": "PEP_DOMESTIC",
                      "country_code": "KE", "products": ["PRIVATE_BANKING"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 30000000, "txn_count_30d": 25},
                      "pep_flag": True, "sanctions_hit": False},
                    {"customer_id": "C003", "customer_type": "HIGH_NET_WORTH",
                      "country_code": "KE", "products": ["WEALTH_MANAGEMENT"],
                      "onboarding_channel": "MOBILE_APP_VIDEO_KYC",
                      "behavior": {"txn_amount_kes_30d": 60000000, "txn_count_30d": 60},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C004", "customer_type": "PEP_FOREIGN",
                      "country_code": "AF", "products": ["CORRESPONDENT_BANKING"],
                      "onboarding_channel": "NON_FACE_TO_FACE",
                      "behavior": {"txn_amount_kes_30d": 80000000, "txn_count_30d": 70},
                      "pep_flag": True, "sanctions_hit": False},
                    {"customer_id": "C005", "customer_type": "INDIVIDUAL",
                      "country_code": "PK", "products": ["RETAIL"],
                      "onboarding_channel": "AGENT_BANKING",
                      "behavior": {"txn_amount_kes_30d": 500000, "txn_count_30d": 5},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C006", "customer_type": "NGO_NPO",
                      "country_code": "KE", "products": ["CASH_INTENSIVE"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 20000000, "txn_count_30d": 30},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C007", "customer_type": "INDIVIDUAL",
                      "country_code": "KP", "products": ["RETAIL"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 100000, "txn_count_30d": 1},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C008",
                      "customer_type": "BEARER_SHARE_ENTITY",
                      "country_code": "TR", "products": ["TRADE_FINANCE"],
                      "onboarding_channel": "INTRODUCED_THIRD_PARTY",
                      "behavior": {"txn_amount_kes_30d": 25000000, "txn_count_30d": 20},
                      "pep_flag": False, "sanctions_hit": False},
                ]

                cab_results = []
                for c in kyc_cab_book:
                    r = KycAmlRiskEngine.assess_customer(c)
                    cab_results.append({
                        "Customer": r.customer_id,
                        "Type": c["customer_type"][:20],
                        "Country": c["country_code"],
                        "Score": r.risk_score,
                        "Band": r.risk_band,
                        "CDD": r.cdd_level[:20],
                        "PEP": "✅" if r.pep_flag else "—",
                        "Sanctions": "🚨" if r.sanctions_flag else "—",
                        "Auto-proh": ("🚨" if r.auto_prohibited else "—"),
                    })
                # Sort by score desc (highest risk first)
                cab_results.sort(key=lambda r: -r["Score"])

                # Distribution
                proh_n = sum(1 for r in cab_results if r["Band"] == "PROHIBITED")
                high_n = sum(1 for r in cab_results if r["Band"] == "HIGH")
                med_n = sum(1 for r in cab_results if r["Band"] == "MEDIUM")
                low_n = sum(1 for r in cab_results if r["Band"] == "LOW")

                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("Total assessed", len(cab_results))
                k2.metric("PROHIBITED 🚨", proh_n,
                            delta_color="inverse" if proh_n > 0 else "normal")
                k3.metric("HIGH 🟠", high_n,
                            delta_color="inverse" if high_n > 0 else "normal")
                k4.metric("MEDIUM ⚠", med_n)
                k5.metric("LOW ✅", low_n)

                # Status emoji column
                band_emoji = {"PROHIBITED": "🚨", "HIGH": "🟠",
                                "MEDIUM": "⚠", "LOW": "✅"}
                display_rows = [
                    {**{k: v for k, v in r.items()},
                      "Status": band_emoji.get(r["Band"], "⚪")}
                    for r in cab_results
                ]
                st.dataframe(pd.DataFrame(display_rows),
                             use_container_width=True, hide_index=True)

                # Recommendations
                if proh_n > 0:
                    st.error(
                        f"🚨 **{proh_n} prohibited customer(s)** — cannot be "
                        "onboarded. Engine surfaces reason via "
                        "`auto_prohibited_reason` field. Onboarding pipeline "
                        "must reject + log per AML/CFT regulations.")
                if high_n > 0:
                    st.warning(
                        f"🟠 **{high_n} HIGH-risk customer(s)** — require "
                        "Enhanced Due Diligence: source of funds, beneficial "
                        "owner, ongoing transaction monitoring intensified.")

                audit_log("AML_ENGINE_USED", uname,
                            f"KYC #36 (depth): batch n={len(cab_results)} "
                            f"prohibited={proh_n} high={high_n} med={med_n} low={low_n}")

        # ────────── Inner[2]: Jurisdiction Concentration Map ──────────
        with _kyc_depth_inner[2]:
            st.markdown(
                "**Jurisdiction Concentration Map** — analyzes geographic "
                "distribution of customer book + flags concentration in "
                "high-risk or prohibited jurisdictions.")
            st.caption(
                "Caller-side aggregation over assess_customer outputs. "
                "Engine doesn't have built-in geographic summary method. "
                "Useful for AML committee jurisdiction-exposure dashboards.")

            from utils.kyc_aml_risk import (HIGH_RISK_JURISDICTIONS,
                MEDIUM_RISK_JURISDICTIONS, PROHIBITED_JURISDICTIONS)

            if st.button("🌐 Compute jurisdiction map",
                           key="kyc_jm_btn", type="primary"):
                # Use same book
                jm_book = [
                    ("C001", "KE"), ("C002", "KE"), ("C003", "KE"),
                    ("C004", "AF"), ("C005", "PK"), ("C006", "KE"),
                    ("C007", "KP"), ("C008", "TR"), ("C009", "KE"),
                    ("C010", "KE"), ("C011", "KE"), ("C012", "KE"),
                    ("C013", "MM"), ("C014", "JO"), ("C015", "SY"),
                ]

                from collections import Counter as _C_jm
                country_counts = _C_jm(c[1] for c in jm_book)

                # Categorize each country
                jm_rows = []
                for country, count in sorted(country_counts.items(),
                                                key=lambda x: -x[1]):
                    if country in PROHIBITED_JURISDICTIONS:
                        cat = "🚨 PROHIBITED"
                        cat_color = "#7C2D12"
                    elif country in HIGH_RISK_JURISDICTIONS:
                        cat = "🟠 HIGH RISK"
                        cat_color = "#DC2626"
                    elif country in MEDIUM_RISK_JURISDICTIONS:
                        cat = "⚠ MEDIUM RISK"
                        cat_color = "#F59E0B"
                    else:
                        cat = "✅ LOW RISK"
                        cat_color = "#10B981"
                    jm_rows.append({
                        "Country": country,
                        "Customers": count,
                        "% of book": f"{count/len(jm_book)*100:.1f}%",
                        "Category": cat,
                    })

                # Aggregate severity counts
                proh_count = sum(r["Customers"] for r in jm_rows
                                   if "PROHIBITED" in r["Category"])
                high_count = sum(r["Customers"] for r in jm_rows
                                   if "HIGH RISK" in r["Category"])
                med_count = sum(r["Customers"] for r in jm_rows
                                  if "MEDIUM RISK" in r["Category"])
                low_count = sum(r["Customers"] for r in jm_rows
                                  if "LOW RISK" in r["Category"])

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Prohibited countries 🚨", proh_count,
                            delta_color="inverse" if proh_count > 0 else "normal")
                k2.metric("High-risk countries 🟠", high_count,
                            delta_color="inverse" if high_count > 0 else "normal")
                k3.metric("Medium-risk countries ⚠", med_count)
                k4.metric("Low-risk countries ✅", low_count)

                st.dataframe(pd.DataFrame(jm_rows),
                             use_container_width=True, hide_index=True)

                # Bar chart
                chart_data = pd.DataFrame({
                    "Customers": [r["Customers"] for r in jm_rows]
                }, index=[r["Country"] for r in jm_rows])
                st.markdown("**Customer concentration by country:**")
                st.bar_chart(chart_data)

                if proh_count > 0:
                    st.error(
                        f"🚨 **{proh_count} customer(s) from prohibited "
                        "jurisdictions** (KP/IR). Engine auto-prohibits these. "
                        "Confirm onboarding has been rejected + escalate to "
                        "compliance committee.")
                if high_count >= 3:
                    st.warning(
                        f"🟠 **High-risk jurisdiction concentration** — "
                        f"{high_count} customer(s) from FATF high-risk list. "
                        "Apply EDD + ongoing monitoring + senior approval.")

                audit_log("AML_ENGINE_USED", uname,
                            f"KYC #36 (depth): jurisdiction map "
                            f"prohibited={proh_count} high={high_count} "
                            f"medium={med_count} low={low_count}")

        # ────────── Inner[3]: Risk Component Investment Map ──────────
        with _kyc_depth_inner[3]:
            st.markdown(
                "**Risk Component Investment Map** — analyzes the 5 risk "
                "components (geography, product, customer_type, channel, "
                "behavior) and ranks where the bank's risk concentration "
                "lies. Helps compliance teams prioritize control investment.")
            st.caption(
                "💡 Investment priority bands: 🔴 CRITICAL >50% of book has "
                "high score / 🟡 IMPORTANT >25% / 🟢 MONITOR <25% / "
                "✅ STRONG <10%.")

            if st.button("🎚️ Compute component investment map",
                           key="kyc_cim_btn", type="primary"):
                # Reuse same book
                cim_book = [
                    {"customer_id": "C001", "customer_type": "INDIVIDUAL",
                      "country_code": "KE", "products": ["RETAIL"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 800000, "txn_count_30d": 8},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C002", "customer_type": "PEP_DOMESTIC",
                      "country_code": "KE", "products": ["PRIVATE_BANKING"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 30000000, "txn_count_30d": 25},
                      "pep_flag": True, "sanctions_hit": False},
                    {"customer_id": "C003", "customer_type": "HIGH_NET_WORTH",
                      "country_code": "KE", "products": ["WEALTH_MANAGEMENT"],
                      "onboarding_channel": "MOBILE_APP_VIDEO_KYC",
                      "behavior": {"txn_amount_kes_30d": 60000000, "txn_count_30d": 60},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C004", "customer_type": "PEP_FOREIGN",
                      "country_code": "AF", "products": ["CORRESPONDENT_BANKING"],
                      "onboarding_channel": "NON_FACE_TO_FACE",
                      "behavior": {"txn_amount_kes_30d": 80000000, "txn_count_30d": 70},
                      "pep_flag": True, "sanctions_hit": False},
                    {"customer_id": "C005", "customer_type": "INDIVIDUAL",
                      "country_code": "PK", "products": ["RETAIL"],
                      "onboarding_channel": "AGENT_BANKING",
                      "behavior": {"txn_amount_kes_30d": 500000, "txn_count_30d": 5},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C006", "customer_type": "NGO_NPO",
                      "country_code": "KE", "products": ["CASH_INTENSIVE"],
                      "onboarding_channel": "FACE_TO_FACE_BRANCH",
                      "behavior": {"txn_amount_kes_30d": 20000000, "txn_count_30d": 30},
                      "pep_flag": False, "sanctions_hit": False},
                    {"customer_id": "C008",
                      "customer_type": "BEARER_SHARE_ENTITY",
                      "country_code": "TR", "products": ["TRADE_FINANCE"],
                      "onboarding_channel": "INTRODUCED_THIRD_PARTY",
                      "behavior": {"txn_amount_kes_30d": 25000000, "txn_count_30d": 20},
                      "pep_flag": False, "sanctions_hit": False},
                ]

                # Aggregate component scores
                component_totals = {"geography": 0, "product": 0,
                                      "customer_type": 0, "channel": 0,
                                      "behavior": 0}
                component_high_count = {"geography": 0, "product": 0,
                                          "customer_type": 0, "channel": 0,
                                          "behavior": 0}
                # Threshold for "high" component score (>=15 means contributes
                # significantly to overall risk band)
                HIGH_COMPONENT_THRESHOLD = 15

                for c in cim_book:
                    r = KycAmlRiskEngine.assess_customer(c)
                    for comp_name, comp_score in r.component_scores.items():
                        component_totals[comp_name] += comp_score
                        if comp_score >= HIGH_COMPONENT_THRESHOLD:
                            component_high_count[comp_name] += 1

                # Rank components by % of customers with high score
                total_customers = len(cim_book)
                cim_rows = []
                for comp_name, high_count in component_high_count.items():
                    pct = (high_count / total_customers * 100
                            if total_customers else 0)
                    avg_score = (component_totals[comp_name] / total_customers
                                  if total_customers else 0)
                    if pct > 50:
                        priority = "🔴 CRITICAL — major risk concentration"
                    elif pct > 25:
                        priority = "🟡 IMPORTANT — invest in controls"
                    elif pct >= 10:
                        priority = "🟢 MONITOR — manageable exposure"
                    else:
                        priority = "✅ STRONG — well-controlled"
                    cim_rows.append({
                        "Component": comp_name.replace("_", " ").title(),
                        "Avg score": f"{avg_score:.1f}",
                        "% of book with high score":
                            f"{pct:.0f}% ({high_count}/{total_customers})",
                        "Investment priority": priority,
                    })

                # Sort by avg score desc
                cim_rows.sort(key=lambda r: -float(r["Avg score"]))

                st.dataframe(pd.DataFrame(cim_rows),
                             use_container_width=True, hide_index=True)

                # Bar chart of avg component scores
                chart_pairs = [(r["Component"], float(r["Avg score"]))
                                 for r in cim_rows]
                chart_data = pd.DataFrame({
                    "Avg score": [p[1] for p in chart_pairs]
                }, index=[p[0] for p in chart_pairs])
                st.markdown("**Average component risk score across book:**")
                st.bar_chart(chart_data)

                # Critical / important callouts
                critical = [r for r in cim_rows
                              if "CRITICAL" in r["Investment priority"]]
                important = [r for r in cim_rows
                               if "IMPORTANT" in r["Investment priority"]]
                if critical:
                    st.error(
                        f"🔴 **{len(critical)} component(s) at CRITICAL** — "
                        f"{', '.join(r['Component'] for r in critical)}. "
                        "Major risk concentration. Invest in controls + "
                        "EDD intensification.")
                if important:
                    st.warning(
                        f"🟡 **{len(important)} component(s) at IMPORTANT** — "
                        f"{', '.join(r['Component'] for r in important)}. "
                        "Plan compliance investment within 6-month cycle.")
                if not critical and not important:
                    st.success(
                        "✅ All components at MONITOR or STRONG levels. "
                        "Maintain current AML/CFT control framework.")

                audit_log("AML_ENGINE_USED", uname,
                            f"KYC #36 (depth): component map "
                            f"critical={len(critical)} important={len(important)}")


# ════════════════════════════════════════════════════════════════
# TAB 7 — PORTFOLIO RISK SUMMARY (Standard #36, integrated v5.86)
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    from utils.kyc_aml_risk import (
        KycAmlRiskEngine, KycRiskAssessment,
        RISK_BAND_LOW_MAX, RISK_BAND_MEDIUM_MAX, RISK_BAND_HIGH_MAX,
        RISK_BAND_PROHIBITED_MIN,
    )

    st.markdown(
        f"**Standard #36 — Portfolio Risk Summary**. "
        "Aggregate KYC risk distribution across customer portfolio.")
    st.caption(
        "Demo dataset: 8 customer profiles representing typical Tier-2 bank mix. "
        "Production deployment would feed via `customers_register.json` "
        "passed through `assess_customer` to build the assessments list.")

    # Demo dataset — representative customer mix
    @st.cache_data(ttl=300, show_spinner=False)
    def _demo_portfolio():
        customers = [
            # Low risk retail
            {"customer_id": "RET_001", "country_code": "KE",
              "citizenship_code": "KE",
              "customer_type": "INDIVIDUAL_RESIDENT",
              "products": ["SAVINGS"],
              "onboarding_channel": "FACE_TO_FACE_BRANCH",
              "pep_flag": False, "sanctions_hit": False},
            {"customer_id": "RET_002", "country_code": "KE",
              "citizenship_code": "KE",
              "customer_type": "INDIVIDUAL_RESIDENT",
              "products": ["SAVINGS", "CURRENT"],
              "onboarding_channel": "MOBILE_APP_VIDEO_KYC",
              "pep_flag": False, "sanctions_hit": False},
            # Medium SME
            {"customer_id": "SME_001", "country_code": "KE",
              "citizenship_code": "KE",
              "customer_type": "SME_RESIDENT",
              "products": ["TRADE_FINANCE", "FX"],
              "onboarding_channel": "FACE_TO_FACE_BRANCH",
              "pep_flag": False, "sanctions_hit": False},
            # NGO/NPO — flagged
            {"customer_id": "NGO_001", "country_code": "KE",
              "citizenship_code": "KE",
              "customer_type": "NGO_NPO",
              "products": ["CURRENT"],
              "onboarding_channel": "FACE_TO_FACE_BRANCH",
              "pep_flag": False, "sanctions_hit": False},
            # HNW domestic PEP
            {"customer_id": "HNW_001", "country_code": "KE",
              "citizenship_code": "KE",
              "customer_type": "PEP_DOMESTIC",
              "products": ["PRIVATE_BANKING", "WEALTH_MANAGEMENT"],
              "onboarding_channel": "FACE_TO_FACE_BRANCH",
              "pep_flag": True, "sanctions_hit": False},
            # Foreign PEP — high risk
            {"customer_id": "PEP_F_001", "country_code": "PK",  # medium jurisdiction
              "citizenship_code": "PK",
              "customer_type": "PEP_FOREIGN",
              "products": ["PRIVATE_BANKING"],
              "onboarding_channel": "INTRODUCED_THIRD_PARTY",
              "pep_flag": True, "sanctions_hit": False},
            # Sanctions hit — auto-prohibited
            {"customer_id": "SANC_001", "country_code": "KE",
              "citizenship_code": "KE",
              "customer_type": "INDIVIDUAL_RESIDENT",
              "products": ["SAVINGS"],
              "onboarding_channel": "FACE_TO_FACE_BRANCH",
              "pep_flag": False, "sanctions_hit": True},
            # Prohibited jurisdiction — auto-prohibited
            {"customer_id": "PROH_001", "country_code": "IR",
              "citizenship_code": "IR",
              "customer_type": "INDIVIDUAL_NON_RESIDENT",
              "products": ["CURRENT"],
              "onboarding_channel": "NON_FACE_TO_FACE",
              "pep_flag": False, "sanctions_hit": False},
        ]
        return [KycAmlRiskEngine.assess_customer(c) for c in customers]

    if st.button("📊 Compute portfolio risk summary",
                   key="kyc_portfolio_btn", type="primary"):
        assessments = _demo_portfolio()
        r = KycAmlRiskEngine.portfolio_risk_summary(assessments)

        total = int(r["total_customers"])
        by_band = r["by_band"]
        pep_count = int(r["pep_count"])
        sanc_count = int(r["sanctions_count"])
        ap_count = int(r["auto_prohibited_count"])

        # Top metrics
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total customers", total)
        k2.metric("PEP count", pep_count,
                   help="Politically Exposed Persons.")
        k3.metric("Sanctions hits", sanc_count,
                   help="⛔ Auto-prohibited.")
        k4.metric("Auto-prohibited", ap_count,
                   help="Sanctions hits + prohibited jurisdictions.")

        # By-band breakdown
        st.markdown("**Risk band distribution:**")
        band_rows = []
        band_colors = {"LOW": "🟢", "MEDIUM": "🔵",
                        "HIGH": "🟡", "PROHIBITED": "🔴"}
        for band in ["LOW", "MEDIUM", "HIGH", "PROHIBITED"]:
            count = int(by_band.get(band, 0))
            pct = (count / total * 100) if total else 0
            band_rows.append({
                "Band": f"{band_colors.get(band, '⚪')} {band}",
                "Count": count,
                "% of portfolio": f"{pct:.1f}%",
            })
        st.dataframe(pd.DataFrame(band_rows),
                     use_container_width=True, hide_index=True)

        # Bar chart
        chart_data = pd.DataFrame({
            "Customers": [int(by_band.get(b, 0))
                            for b in ["LOW", "MEDIUM", "HIGH", "PROHIBITED"]]
        }, index=["LOW", "MEDIUM", "HIGH", "PROHIBITED"])
        st.bar_chart(chart_data)

        # Per-customer breakdown
        st.markdown("**Per-customer assessments:**")
        cust_rows = []
        for a in assessments:
            band_emoji = band_colors.get(a.risk_band, "⚪")
            cust_rows.append({
                "Customer ID": a.customer_id,
                "Score": a.risk_score,
                "Band": f"{band_emoji} {a.risk_band}",
                "CDD": a.cdd_level.replace("_", " ").title(),
                "PEP": "🚨" if a.pep_flag else "",
                "Sanctions": "⛔" if a.sanctions_flag else "",
                "Auto-prohibited": "🚫" if a.auto_prohibited else "",
            })
        st.dataframe(pd.DataFrame(cust_rows),
                     use_container_width=True, hide_index=True)

        # Executive guidance
        prohibited_pct = (int(by_band.get("PROHIBITED", 0)) / total * 100) if total else 0
        high_pct = (int(by_band.get("HIGH", 0)) / total * 100) if total else 0
        if prohibited_pct > 5:
            st.error(
                f"⛔ **{prohibited_pct:.1f}% of portfolio at PROHIBITED band** — "
                "review onboarding controls. CBK PG/05 expects auto-prohibition "
                "to filter prohibited customers before onboarding, so a high count "
                "in this category suggests filters need tuning.")
        elif high_pct > 20:
            st.warning(
                f"⚠ **{high_pct:.1f}% of portfolio at HIGH band** — "
                "Enhanced Due Diligence resourcing should match volume. "
                "Quarterly EDD reviews recommended.")
        else:
            st.success(
                f"✅ Portfolio risk distribution within healthy bounds. "
                f"PROHIBITED={prohibited_pct:.1f}%, HIGH={high_pct:.1f}%.")

        audit_log("IFRS_ENGINE_USED", uname,
                   f"KYC #36: portfolio summary total={total} "
                   f"PEP={pep_count} sanctions={sanc_count} prohibited={ap_count}")
