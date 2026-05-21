"""pages/54_rcsa.py — Risk Register & RCSA.
Operational risk events, KRIs, control effectiveness. Thresholds via Admin.
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


require_access("compliance_regulatory.rcsa")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_risk  = any(x in role for x in ("risk","compliance","chief risk","operational risk"))

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>🛡️ Risk Register (RCSA)</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Operational risk · Controls · KRIs · Residual risk · Action plans</span></div>",
            unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"rcsa_register.json"
    return a2z_db.load_json(p) if p.exists() else []

risks = _load()
HIGH_THR = cfg("rcsa_high_residual", 12)
MED_THR  = cfg("rcsa_medium_residual", 6)

high = [r for r in risks if r.get("residual_score",0) >= HIGH_THR]
med  = [r for r in risks if MED_THR <= r.get("residual_score",0) < HIGH_THR]
kri_breached = [r for r in risks if r.get("kri_breached")]
action_due   = [r for r in risks if r.get("action_required")]

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Risks",  len(risks))
m2.metric("High Residual",len(high), delta_color="normal" if not high else "inverse")
m3.metric("KRI Breached", len(kri_breached), delta_color="normal" if not kri_breached else "inverse")
m4.metric("Action Required",len(action_due))

if high:
    st.error(f"🔴 {len(high)} high-residual risks require immediate management attention")

# ─────────────────────────────────────────────────────────────────
# v7.8: RCSA Health Composite (composite_scores.py surfacing)
# ─────────────────────────────────────────────────────────────────
with st.expander("📊 RCSA Health Composite (v6.0 / v7.8 surfaced)", expanded=False):
    from utils.composite_scores import rcsa_health_composite

    st.caption(
        "v7.8 surfacing of `composite_scores.rcsa_health_composite()` on this "
        "domain page (per Charter §13). Composes COSO overall + control "
        "effectiveness + deficiency severity into a single 0-100 score with "
        "HEALTHY / MODERATE / LOW severity bands. Production deployment "
        "reads live values from internal_controls engine + RCSA workflow."
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Inputs (illustrative healthy bank):**")
        rcsa_coso = st.slider("COSO overall score (0-5)", 0.0, 5.0, 4.2, 0.1,
                               key="rcsa_health_coso")
        rcsa_eff = st.slider("Control effectiveness %", 0, 100, 88,
                              key="rcsa_health_eff")
        rcsa_mw = st.number_input("Material weaknesses (count)", 0, 20, 0,
                                    key="rcsa_health_mw")
        rcsa_sd = st.number_input("Significant deficiencies (count)", 0, 50, 2,
                                    key="rcsa_health_sd")
        rcsa_def = st.number_input("Other deficiencies (count)", 0, 100, 8,
                                     key="rcsa_health_def")

    with c2:
        rcsa_result = rcsa_health_composite(
            coso_overall_score=float(rcsa_coso),
            control_effectiveness_pct=float(rcsa_eff),
            material_weakness_count=int(rcsa_mw),
            significant_deficiency_count=int(rcsa_sd),
            deficiency_count=int(rcsa_def),
        )
        rcsa_score = rcsa_result.get("score")
        rcsa_severity = rcsa_result.get("severity")
        sev_color = {"HEALTHY": "✅", "MODERATE": "🟡",
                     "LOW": "🚨", "UNKNOWN": "⚠"}.get(rcsa_severity, "")
        st.metric("RCSA Health score",
                  f"{rcsa_score:.1f}/100" if rcsa_score is not None else "—",
                  rcsa_severity)
        st.markdown(f"**{sev_color} {rcsa_severity}**")

        if rcsa_result.get("components"):
            st.markdown("**Component scores:**")
            for k, v in rcsa_result["components"].items():
                st.markdown(f"- `{k}`: {v:.1f}")

tabs = st.tabs([
    "🔴 High Risk",
    "📋 All Risks",
    "📊 Heat Map",
    "🔔 KRIs",
    "➕ Add Risk",
    "🛡️ Internal Controls (Standard #44)",
    "⚠️ Operational Risk Engine (Standard #43)",
])

def _render_risks(risk_list):
    if not risk_list: st.success("None in this view."); return
    rows=[{"ID":r["id"],"Category":r["category"][:20],"Dept":r["department"][:18],
            "Inherent":r["inherent_score"],"Control":r["control_effectiveness"][:12],
            "Residual":r["residual_score"],"Rating":r["residual_rating"],
            "Owner":r["risk_owner"][:20],"Next Review":r["next_review"][:10],
            "Action":("⚠️" if r.get("action_required") else "")}
           for r in sorted(risk_list, key=lambda x:-x.get("residual_score",0))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[0]: _render_risks(high)
with tabs[1]:
    f1,f2 = st.columns(2)
    fcat = f1.selectbox("Category",["All"]+sorted(set(r["category"] for r in risks)),key="rcsa_cat")
    frat = f2.selectbox("Rating",["All","High","Medium","Low"],key="rcsa_rat")
    vis  = [r for r in risks
            if (fcat=="All" or r["category"]==fcat)
            and (frat=="All" or r["residual_rating"]==frat)]
    _render_risks(vis)

with tabs[2]:
    st.markdown("**Risk heat map — inherent score distribution:**")
    cat_ct = Counter(r["category"] for r in risks)
    st.bar_chart(pd.DataFrame({"Risks":dict(cat_ct.most_common())}).T.T)
    rating_ct = Counter(r["residual_rating"] for r in risks)
    st.markdown("**Residual risk distribution:**")
    for rat,n in [("High",rating_ct.get("High",0)),("Medium",rating_ct.get("Medium",0)),("Low",rating_ct.get("Low",0))]:
        clr={"High":"#DC2626","Medium":"#D97706","Low":"#16A34A"}.get(rat,"#6B7280")
        pct=n/max(len(risks),1)*100
        st.markdown(f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
                    f"<div style='width:60px'>{rat}</div>"
                    f"<div style='background:{clr};height:16px;width:{pct:.0f}%;border-radius:3px'></div>"
                    f"<div style='font-size:12px'>{n} ({pct:.0f}%)</div></div>",unsafe_allow_html=True)

with tabs[3]:
    st.markdown("**KRI Dashboard — breached indicators:**")
    if kri_breached:
        kri_rows=[{"ID":r["id"],"KRI":r["kri"],"Value":r["kri_value"],"Threshold":r["kri_threshold"],
                    "Category":r["category"][:20],"Owner":r["risk_owner"][:20]}
                   for r in kri_breached]
        st.dataframe(pd.DataFrame(kri_rows),use_container_width=True,hide_index=True)
    else:
        st.success("✅ No KRI breaches currently.")

with tabs[4]:
    if is_risk or is_admin:
        st.markdown("**Add new risk to register:**")
        from utils.core import get_org_config as _goc
        _depts = [d["name"] for d in _goc().get("departments",[]) if d.get("active",True)]
        r1,r2,r3 = st.columns(3)
        _cat = r1.selectbox("Category",["Credit Risk","Market Risk","Liquidity Risk","Operational Risk",
                             "Compliance/Legal","Reputational Risk","Strategic Risk","IT/Cyber Risk"],key="rcsa_ncat")
        _dept= r2.selectbox("Department",_depts,key="rcsa_ndept")
        _inh = r3.slider("Inherent score (1-25)",1,25,9,key="rcsa_ninh")
        _desc= st.text_area("Risk description",height=80,key="rcsa_ndesc")
        _ctrl= st.selectbox("Control",["Manual control","Automated control","Dual control",
                             "Segregation of duties","Policy & procedure","None"],key="rcsa_nctrl")
        _eff = st.selectbox("Control effectiveness",["Adequate","Partially adequate","Inadequate"],key="rcsa_neff")
        if st.button("➕ Add risk",key="rcsa_add",type="primary"):
            if _desc.strip():
                all_r = json.loads((DATA/"rcsa_register.json").read_text())
                resid = _inh*(0.4 if _eff=="Adequate" else 0.6 if _eff=="Partially adequate" else 0.85)
                all_r.append({"id":f"RSK{len(all_r)+1:04d}","category":_cat,"description":_desc.strip(),
                               "department":_dept,"inherent_score":_inh,"control_description":_ctrl,
                               "control_effectiveness":_eff,"residual_score":round(resid,1),
                               "residual_rating":("High" if resid>=HIGH_THR else "Medium" if resid>=MED_THR else "Low"),
                               "risk_owner":uname,"last_reviewed":str(today),"next_review":"",
                               "action_required":_eff!="Adequate","kri":"","kri_value":0,"kri_threshold":0,"kri_breached":False,"notes":""})
                (DATA/"rcsa_register.json").write_text(json.dumps(all_r,indent=2))
                audit_log("RCSA_RISK_ADDED",uname,f"{_cat}: {_desc[:60]}")
                _bsc_trigger(uname, "K014")
                st.cache_data.clear(); st.success("✅ Risk added"); st.rerun()
            else: st.error("Description required.")
    else: st.info("Risk Register editing available to Risk & Compliance team.")


# ════════════════════════════════════════════════════════════════
# TAB 6 — INTERNAL CONTROLS (Standard #44, integrated v5.85)
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    from utils.internal_controls import (
        InternalControlsEngine, ControlDeficiency, ControlTest,
        COSO_COMPONENTS, COSO_PRINCIPLES, DEFICIENCY_SEVERITIES,
        SAMPLE_SIZES_BY_RISK, TOLERABLE_EXCEPTION_RATE_PCT,
        TEST_OUTCOMES, MATERIAL_WEAKNESS_THRESHOLD_PCT,
        SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT, TOTAL_COSO_PRINCIPLES,
    )
    from decimal import Decimal as _D_ic

    st.markdown(
        f"**Standard #44 — Internal Controls Engine (COSO Framework)**. "
        f"{TOTAL_COSO_PRINCIPLES} COSO principles across "
        f"{len(COSO_COMPONENTS)} components. "
        f"Sample sizes by risk: LOW=25 / MEDIUM=40 / HIGH=60 / KEY=90. "
        f"Material Weakness threshold ≥{MATERIAL_WEAKNESS_THRESHOLD_PCT}% of assets, "
        f"Significant Deficiency ≥{SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT}%."
    )

    ic_sub_tabs = st.tabs([
        "📐 Sample Size Calculator",
        "✅ Control Test",
        "⚠️ Classify Deficiency",
        "🏛️ COSO Component Score",
        "📊 Effectiveness Summary",
        "🌳 Engine Reference",
        "📦 RCSA Depth (#44, v5.99)",
    ])

    # ──────── Sample Size Calculator ────────
    with ic_sub_tabs[0]:
        st.markdown(
            "**Sample Size by Risk Level** — bound byte-for-byte from "
            "`SAMPLE_SIZES_BY_RISK` and `TOLERABLE_EXCEPTION_RATE_PCT`.")
        ss_risk = st.selectbox("Control risk level",
                                 list(SAMPLE_SIZES_BY_RISK.keys()),
                                 key="ic_ss_risk",
                                 help="LOW=routine, MEDIUM=ordinary business, "
                                       "HIGH=sensitive, KEY=critical to financial reporting.")
        if st.button("Compute sample size",
                       key="ic_ss_btn", type="primary"):
            r = InternalControlsEngine.sample_size(ss_risk)
            if "error" in r:
                st.error(f"⛔ {r['error']}")
            else:
                k1, k2, k3 = st.columns(3)
                k1.metric("Risk level", r["risk_level"])
                k2.metric("Required sample", r["sample_size"])
                k3.metric("Tolerable exception rate",
                           f"{r['tolerable_exception_rate_pct']}%")
                if ss_risk == "KEY":
                    st.error(
                        "🔴 **KEY controls have ZERO tolerance** — any exception "
                        "found in the sample fails the test.")
                else:
                    st.info(
                        f"ℹ Tester needs to test {r['sample_size']} instances. "
                        f"Up to {r['tolerable_exception_rate_pct']}% can fail "
                        "before the control is deemed not effective.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Controls #44: sample_size {ss_risk} → "
                           f"{r['sample_size']}")

    # ──────── Control Test ────────
    with ic_sub_tabs[1]:
        st.markdown(
            "**Run Control Test** — engine grades effectiveness against tolerance band.")
        st.caption(
            "Outcomes: EFFECTIVE (zero exceptions for KEY, within tolerance otherwise) · "
            "PARTIALLY_EFFECTIVE (above zero but within tolerance) · INEFFECTIVE (above tolerance).")

        c1, c2 = st.columns(2)
        with c1:
            ct_id = st.text_input("Test ID", value="T_2026Q2_001", key="ic_ct_id")
            ct_ctrl = st.text_input("Control ID", value="C_INV_001", key="ic_ct_ctrl")
            ct_coso = st.selectbox("COSO component",
                                      list(COSO_COMPONENTS),
                                      index=2, key="ic_ct_coso")
        with c2:
            ct_risk = st.selectbox("Risk level",
                                      list(SAMPLE_SIZES_BY_RISK.keys()),
                                      index=2, key="ic_ct_risk")
            ct_sample = st.number_input("Sample size tested",
                                          min_value=0, value=60, step=5,
                                          key="ic_ct_sample")
            ct_excs = st.number_input("Exceptions found",
                                         min_value=0, value=1, step=1,
                                         key="ic_ct_excs")

        if st.button("Test control",
                       key="ic_ct_btn", type="primary"):
            test = ControlTest(
                test_id=ct_id, control_id=ct_ctrl,
                coso_component=ct_coso, risk_level=ct_risk,
                sample_size=int(ct_sample),
                exceptions_found=int(ct_excs))
            r = InternalControlsEngine.test_control(test)
            if r.get("outcome") is None:
                st.error(
                    f"⛔ Could not test (Rule 1): {r.get('reason', 'missing data')}")
            else:
                outcome = r["outcome"]
                colors = {"EFFECTIVE": "#10B981",
                          "PARTIALLY_EFFECTIVE": "#F59E0B",
                          "INEFFECTIVE": "#DC2626"}
                color = colors.get(outcome, "#6B7280")

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Sample tested", r["sample_size"])
                k2.metric("Sample adequate?",
                           "✅ YES" if r["sample_adequate"] else "🔴 NO",
                           help=f"Min required: {r['min_required_sample']}")
                k3.metric("Exception rate",
                           f"{r['exception_rate_pct']}%",
                           delta=f"tolerance {r['tolerance_pct']}%")
                k4.metric("Effectiveness",
                           f"{r['effectiveness_pct']}%")

                st.markdown(
                    f"<div style='padding:14px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:10px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"OUTCOME</div>"
                    f"<div style='font-size:24px;font-weight:800;color:{color}'>"
                    f"{outcome}</div></div>",
                    unsafe_allow_html=True)

                if not r["sample_adequate"]:
                    st.warning(
                        f"⚠ Sample under-tested — {r['sample_size']} below minimum "
                        f"{r['min_required_sample']} for {ct_risk} risk. "
                        "Result not statistically reliable.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Controls #44: test {ct_id} {outcome} "
                           f"({r['exception_rate_pct']}% vs {r['tolerance_pct']}%)")

    # ──────── Classify Deficiency ────────
    with ic_sub_tabs[2]:
        st.markdown(
            f"**Classify Control Deficiency** — engine applies SEC guidance: "
            f"DEFICIENCY · SIGNIFICANT_DEFICIENCY (≥{SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT}% "
            f"of assets) · MATERIAL_WEAKNESS (≥{MATERIAL_WEAKNESS_THRESHOLD_PCT}% of assets).")
        st.caption(
            "Severity escalates if deficiency affects financial reporting AND "
            "no compensating controls exist.")

        c1, c2 = st.columns(2)
        with c1:
            df_id = st.text_input("Deficiency ID",
                                    value="D_2026Q2_001", key="ic_df_id")
            df_ctrl = st.text_input("Control ID",
                                      value="C_REV_002", key="ic_df_ctrl")
            df_desc = st.text_area("Description",
                                     value="Manual journal entry approval not documented",
                                     height=70, key="ic_df_desc")
        with c2:
            df_impact = st.number_input("Estimated financial impact (KES M)",
                                           min_value=0.0, value=2.0, step=0.5,
                                           key="ic_df_impact")
            df_assets = st.number_input("Total assets (KES B)",
                                           min_value=0.1, value=190.0, step=10.0,
                                           key="ic_df_assets")
            df_fr = st.checkbox("Affects financial reporting",
                                  value=True, key="ic_df_fr")
            df_comp = st.checkbox("Compensating controls exist",
                                    value=False, key="ic_df_comp")

        if st.button("Classify deficiency",
                       key="ic_df_btn", type="primary"):
            d = ControlDeficiency(
                deficiency_id=df_id,
                control_id=df_ctrl,
                description=df_desc,
                estimated_financial_impact_kes=_D_ic(str(df_impact)) * _D_ic("1000000"),
                affects_financial_reporting=df_fr,
                compensating_controls_exist=df_comp,
                total_assets_kes=_D_ic(str(df_assets)) * _D_ic("1000000000"))
            r = InternalControlsEngine.classify_deficiency(d)
            severity = r["severity"]
            colors = {"DEFICIENCY": "#3B82F6",
                      "SIGNIFICANT_DEFICIENCY": "#F59E0B",
                      "MATERIAL_WEAKNESS": "#DC2626"}
            color = colors.get(severity, "#6B7280")

            k1, k2, k3 = st.columns(3)
            k1.metric("Impact",
                       f"KES {_D_ic(str(r['estimated_financial_impact_kes']))/_D_ic('1000000'):,.2f}M")
            k2.metric("Impact % of assets",
                       f"{r['impact_pct']}%",
                       delta=f"≥{MATERIAL_WEAKNESS_THRESHOLD_PCT}% = MW")
            with k3:
                st.markdown(
                    f"<div style='padding:8px 12px;background:{color}22;"
                    f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"SEVERITY</div>"
                    f"<div style='font-size:18px;font-weight:800;color:{color}'>"
                    f"{severity}</div></div>",
                    unsafe_allow_html=True)

            if severity == "MATERIAL_WEAKNESS":
                st.error(
                    "⛔ **MATERIAL WEAKNESS** — must be disclosed in audit report. "
                    "External audit may issue adverse opinion on internal controls. "
                    "Remediation plan required immediately.")
            elif severity == "SIGNIFICANT_DEFICIENCY":
                st.warning(
                    "⚠ **SIGNIFICANT DEFICIENCY** — must be communicated to "
                    "Audit Committee in writing.")
            else:
                st.info(
                    "ℹ **DEFICIENCY** — log in deficiency register, monitor for "
                    "aggregation with similar items.")
            audit_log("IFRS_ENGINE_USED", uname,
                       f"Controls #44: classify {df_id} → {severity} "
                       f"({r['impact_pct']}% of assets)")

    # ──────── COSO Component Score ────────
    with ic_sub_tabs[3]:
        st.markdown(
            f"**COSO Component Score** — rate {TOTAL_COSO_PRINCIPLES} principles "
            f"across {len(COSO_COMPONENTS)} components on a 1-5 scale.")
        st.caption(
            "Engine surfaces missing_principles list (Rule 6 transparency) "
            "and only computes scores for components with at least one rated principle.")

        comp_choice = st.selectbox(
            "Component to score",
            list(COSO_COMPONENTS),
            key="ic_coso_comp",
            help="Choose a component to focus on; engine computes overall score across all rated principles.")

        principles = COSO_PRINCIPLES.get(comp_choice, [])
        st.markdown(f"**Rate the {len(principles)} principles for {comp_choice}** (1=lowest, 5=highest):")

        ratings = {}
        for p in principles:
            short_name = p.split("_", 1)[0]  # e.g. P1
            full_name = p.replace("_", " ").title()
            r_val = st.slider(f"{short_name}: {full_name}",
                                1, 5, 4, key=f"ic_p_{p}")
            ratings[p] = _D_ic(str(r_val))

        if st.button("Compute COSO score",
                       key="ic_coso_btn", type="primary"):
            r = InternalControlsEngine.coso_component_score(ratings)
            scored = r["scored_components"]
            total = r["total_components"]
            missing = r["missing_count"]

            k1, k2, k3 = st.columns(3)
            k1.metric("Components scored",
                       f"{scored} / {total}")
            k2.metric("Overall score",
                       r["overall_score"] or "—",
                       help="Average across rated principles, 1-5 scale.")
            k3.metric("Missing principles",
                       missing,
                       help="Principles not yet rated (Rule 6 transparency)")

            # Per-component breakdown
            comp_rows = []
            for c, score in r["component_scores"].items():
                comp_rows.append({
                    "Component": c,
                    "Score (1-5)": score if score else "—",
                    "Status": "✅" if score else "—",
                })
            st.dataframe(pd.DataFrame(comp_rows),
                         use_container_width=True, hide_index=True)

            if missing > 0:
                st.warning(
                    f"⚠ {missing} principle(s) not yet rated across other components. "
                    "For full COSO assessment, all 17 principles must be rated.")
            audit_log("IFRS_ENGINE_USED", uname,
                       f"Controls #44: COSO {comp_choice} score={r['overall_score']} "
                       f"missing={missing}")

    # ──────── Effectiveness Summary ────────
    with ic_sub_tabs[4]:
        st.markdown(
            "**Control Effectiveness Summary** — aggregate across multiple test results")
        st.caption(
            "Demo dataset: 12 control tests across all 5 COSO components. "
            "Production deployment would feed via `control_test_results.json`.")

        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_test_results():
            return [
                {"control_id": "C001", "outcome": "EFFECTIVE",
                  "coso_component": "CONTROL_ENVIRONMENT"},
                {"control_id": "C002", "outcome": "EFFECTIVE",
                  "coso_component": "CONTROL_ENVIRONMENT"},
                {"control_id": "C003", "outcome": "PARTIALLY_EFFECTIVE",
                  "coso_component": "CONTROL_ENVIRONMENT"},
                {"control_id": "C004", "outcome": "EFFECTIVE",
                  "coso_component": "RISK_ASSESSMENT"},
                {"control_id": "C005", "outcome": "INEFFECTIVE",
                  "coso_component": "RISK_ASSESSMENT"},
                {"control_id": "C006", "outcome": "EFFECTIVE",
                  "coso_component": "CONTROL_ACTIVITIES"},
                {"control_id": "C007", "outcome": "EFFECTIVE",
                  "coso_component": "CONTROL_ACTIVITIES"},
                {"control_id": "C008", "outcome": "PARTIALLY_EFFECTIVE",
                  "coso_component": "CONTROL_ACTIVITIES"},
                {"control_id": "C009", "outcome": "EFFECTIVE",
                  "coso_component": "INFORMATION_COMMUNICATION"},
                {"control_id": "C010", "outcome": "EFFECTIVE",
                  "coso_component": "INFORMATION_COMMUNICATION"},
                {"control_id": "C011", "outcome": "INEFFECTIVE",
                  "coso_component": "MONITORING_ACTIVITIES"},
                {"control_id": "C012", "outcome": "PARTIALLY_EFFECTIVE",
                  "coso_component": "MONITORING_ACTIVITIES"},
            ]

        if st.button("Compute effectiveness summary",
                       key="ic_eff_btn", type="primary"):
            test_results = _demo_test_results()
            r = InternalControlsEngine.control_effectiveness_summary(test_results)
            overall_pct = float(_D_ic(r.get("overall_effectiveness_pct", "0")))
            color = ("#10B981" if overall_pct >= 90
                      else "#F59E0B" if overall_pct >= 70
                      else "#DC2626")

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total tests", r["total_tests"])
            k2.metric("Effective", r["total_effective"])
            k3.metric("Excluded (Rule 6)", r.get("excluded_count", 0))
            with k4:
                st.markdown(
                    f"<div style='padding:8px 12px;background:{color}22;"
                    f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"OVERALL</div>"
                    f"<div style='font-size:18px;font-weight:800;color:{color}'>"
                    f"{overall_pct:.1f}%</div></div>",
                    unsafe_allow_html=True)

            # Per-component breakdown
            rows = []
            for comp, counts in r["by_component"].items():
                total_in_comp = (counts["effective"] +
                                  counts["partially_effective"] +
                                  counts["ineffective"])
                eff_pct = ((counts["effective"] / total_in_comp * 100)
                            if total_in_comp else 0)
                rows.append({
                    "COSO Component": comp,
                    "Effective": counts["effective"],
                    "Partial": counts["partially_effective"],
                    "Ineffective": counts["ineffective"],
                    "Effective %": f"{eff_pct:.1f}%",
                })
            st.dataframe(pd.DataFrame(rows),
                         use_container_width=True, hide_index=True)

            if overall_pct >= 90:
                st.success(
                    f"✅ Strong control environment — {overall_pct:.1f}% effective.")
            elif overall_pct >= 70:
                st.warning(
                    f"⚠ Moderate control environment — {overall_pct:.1f}% effective. "
                    "Remediation needed in weaker components.")
            else:
                st.error(
                    f"⛔ Weak control environment — only {overall_pct:.1f}% effective. "
                    "Audit Committee escalation appropriate.")
            audit_log("IFRS_ENGINE_USED", uname,
                       f"Controls #44: effectiveness {overall_pct:.1f}% "
                       f"across {r['total_tests']} tests")

    # ──────── Engine Reference ────────
    with ic_sub_tabs[5]:
        st.markdown("**Engine Constants Reference** (single source of truth)")

        st.markdown(f"**Sample sizes & tolerance** (byte-for-byte from engine):")
        ss_rows = [
            {"Risk level": k,
              "Sample size": SAMPLE_SIZES_BY_RISK[k],
              "Tolerable exception %": float(TOLERABLE_EXCEPTION_RATE_PCT[k])}
            for k in SAMPLE_SIZES_BY_RISK
        ]
        st.dataframe(pd.DataFrame(ss_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Deficiency severity thresholds:**")
        df_rows = [
            {"Severity": "DEFICIENCY",
              "Trigger": f"< {SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT}% impact"},
            {"Severity": "SIGNIFICANT_DEFICIENCY",
              "Trigger": f"≥{SIGNIFICANT_DEFICIENCY_THRESHOLD_PCT}% impact OR "
                          "affects FR + no compensating control"},
            {"Severity": "MATERIAL_WEAKNESS",
              "Trigger": f"≥{MATERIAL_WEAKNESS_THRESHOLD_PCT}% impact"},
        ]
        st.dataframe(pd.DataFrame(df_rows),
                     use_container_width=True, hide_index=True)

        st.markdown(f"**COSO framework — {len(COSO_COMPONENTS)} components, "
                    f"{TOTAL_COSO_PRINCIPLES} principles:**")
        for comp in COSO_COMPONENTS:
            principles_in_comp = COSO_PRINCIPLES.get(comp, [])
            st.markdown(f"**{comp}** ({len(principles_in_comp)} principles)")
            for p in principles_in_comp:
                st.caption(f"  • {p.replace('_', ' ').title()}")

    # ════════════════════════════════════════════════════════════════
    # IC_SUB_TABS[6]: RCSA Depth (Standard #44, integrated v5.99)
    # ════════════════════════════════════════════════════════════════
    with ic_sub_tabs[6]:
        st.markdown(
            "**RCSA Depth analysis** — extends v5.85 with 4 inner views following "
            "the proven depth-batch template: executive scorecard composing 3 engine "
            "paths, control test batch (single-control → portfolio), aggregate "
            "deficiency analysis, and COSO component investment map.")
        st.caption(
            "💡 v5.85 surfaces each engine path independently. v5.99 composes them "
            "into board-pack-ready views. Same template as v5.97 Compensation depth "
            "+ v5.98 Engagement depth — fourth application of mature pattern.")

        _rcsa_depth_inner = st.tabs([
            "📋 RCSA Executive Scorecard",
            "🎯 Control Test Batch",
            "🌐 Aggregate Deficiency Analysis",
            "🎚️ COSO Investment Map",
        ])

        # ────────── Inner[0]: RCSA Executive Scorecard ──────────
        with _rcsa_depth_inner[0]:
            from decimal import Decimal as _D_rs
            st.markdown(
                "**RCSA Executive Scorecard** — single-screen summary "
                "combining COSO component scoring + control effectiveness + "
                "deficiency severity into GREEN/AMBER/RED verdict for board "
                "audit committee reporting.")
            st.caption(
                "Mirrors v5.97 Compensation Scorecard + v5.98 Engagement "
                "Scorecard pattern. Click compute to refresh all 3 engine paths "
                "in one shot using deterministic synthetic baselines.")

            if st.button("📋 Compute RCSA scorecard",
                           key="rcsa_es_btn", type="primary"):
                # Deterministic baseline ratings (most healthy, 1 weak component)
                rs_ratings = {p: _D_rs("4")
                                for principles in COSO_PRINCIPLES.values()
                                for p in principles}
                # Deliberately weaken Control Environment to demo AMBER
                rs_ratings["P1_INTEGRITY_AND_ETHICAL_VALUES"] = _D_rs("2")
                rs_ratings["P2_BOARD_OVERSIGHT"] = _D_rs("3")

                # Synthetic test results
                rs_test_results = [
                    {"control_id": "C1", "outcome": "EFFECTIVE",
                      "coso_component": "CONTROL_ACTIVITIES"},
                    {"control_id": "C2", "outcome": "EFFECTIVE",
                      "coso_component": "CONTROL_ACTIVITIES"},
                    {"control_id": "C3", "outcome": "EFFECTIVE",
                      "coso_component": "RISK_ASSESSMENT"},
                    {"control_id": "C4", "outcome": "PARTIALLY_EFFECTIVE",
                      "coso_component": "RISK_ASSESSMENT"},
                    {"control_id": "C5", "outcome": "INEFFECTIVE",
                      "coso_component": "MONITORING_ACTIVITIES"},
                    {"control_id": "C6", "outcome": "EFFECTIVE",
                      "coso_component": "INFORMATION_COMMUNICATION"},
                    {"control_id": "C7", "outcome": "EFFECTIVE",
                      "coso_component": "CONTROL_ENVIRONMENT"},
                    {"control_id": "C8", "outcome": "PARTIALLY_EFFECTIVE",
                      "coso_component": "CONTROL_ACTIVITIES"},
                ]

                # Synthetic deficiencies for severity distribution
                rs_deficiencies = [
                    ControlDeficiency("D1", "C5", "monitoring gap",
                                        estimated_financial_impact_kes=_D_rs("8000000"),
                                        affects_financial_reporting=True,
                                        compensating_controls_exist=False,
                                        total_assets_kes=_D_rs("100000000")),
                    ControlDeficiency("D2", "C4", "risk assessment lag",
                                        estimated_financial_impact_kes=_D_rs("500000"),
                                        affects_financial_reporting=True,
                                        compensating_controls_exist=False,
                                        total_assets_kes=_D_rs("100000000")),
                    ControlDeficiency("D3", "C8", "minor process gap",
                                        estimated_financial_impact_kes=_D_rs("50000"),
                                        affects_financial_reporting=False,
                                        compensating_controls_exist=True,
                                        total_assets_kes=_D_rs("100000000")),
                ]

                coso_r = InternalControlsEngine.coso_component_score(rs_ratings)
                eff_r = InternalControlsEngine.control_effectiveness_summary(rs_test_results)
                def_severities = [InternalControlsEngine.classify_deficiency(d).get("severity")
                                    for d in rs_deficiencies]

                overall_score = float(_D_rs(str(coso_r["overall_score"])))
                eff_pct = float(_D_rs(str(eff_r["overall_effectiveness_pct"])))
                total_tests = int(eff_r["total_tests"])
                effective = int(eff_r["total_effective"])
                material_count = sum(1 for s in def_severities
                                       if s == "MATERIAL_WEAKNESS")
                significant_count = sum(1 for s in def_severities
                                          if s == "SIGNIFICANT_DEFICIENCY")
                deficiency_count = sum(1 for s in def_severities
                                         if s == "DEFICIENCY")

                st.markdown("### 1️⃣ COSO component score")
                cs1, cs2, cs3 = st.columns(3)
                cs1.metric("Overall score (1-5)",
                            f"{overall_score:.2f}",
                            help="Average across 5 COSO components.")
                cs2.metric("Components scored",
                            f"{coso_r['scored_components']}/{coso_r['total_components']}")
                cs3.metric("Missing principles",
                            coso_r['missing_count'],
                            help="Per Rule 6 — engine surfaces incomplete data.")

                # Per-component bars (lowest first)
                comp_scores = {comp: float(_D_rs(str(score)))
                                 for comp, score
                                 in coso_r["component_scores"].items()}
                comp_pairs = sorted(comp_scores.items(), key=lambda p: p[1])
                weakest_comp = comp_pairs[0]
                strongest_comp = comp_pairs[-1]

                wc1, wc2 = st.columns(2)
                wc1.markdown(
                    f"<div style='padding:8px;background:#DC262622;"
                    f"border-left:4px solid #DC2626;border-radius:6px'>"
                    f"<div style='font-size:10px;opacity:0.7'>WEAKEST COMPONENT</div>"
                    f"<div style='font-size:14px;font-weight:700;color:#DC2626'>"
                    f"{weakest_comp[0]} ({weakest_comp[1]:.2f})</div></div>",
                    unsafe_allow_html=True)
                wc2.markdown(
                    f"<div style='padding:8px;background:#10B98122;"
                    f"border-left:4px solid #10B981;border-radius:6px'>"
                    f"<div style='font-size:10px;opacity:0.7'>STRONGEST COMPONENT</div>"
                    f"<div style='font-size:14px;font-weight:700;color:#10B981'>"
                    f"{strongest_comp[0]} ({strongest_comp[1]:.2f})</div></div>",
                    unsafe_allow_html=True)

                st.markdown("### 2️⃣ Control effectiveness")
                eff_color = ("#10B981" if eff_pct >= 90
                              else "#F59E0B" if eff_pct >= 70
                              else "#DC2626")
                e1, e2, e3 = st.columns(3)
                e1.metric("Total tests", total_tests)
                e2.metric("Effective", effective)
                with e3:
                    st.markdown(
                        f"<div style='padding:8px;background:{eff_color}22;"
                        f"border-left:4px solid {eff_color};border-radius:6px'>"
                        f"<div style='font-size:10px;opacity:0.7'>EFFECTIVENESS %</div>"
                        f"<div style='font-size:18px;font-weight:700;color:{eff_color}'>"
                        f"{eff_pct:.1f}%</div></div>",
                        unsafe_allow_html=True)

                st.markdown("### 3️⃣ Deficiency severity distribution")
                d1, d2, d3 = st.columns(3)
                d1.metric("Deficiencies (minor)", deficiency_count)
                d2.metric("Significant deficiencies",
                            significant_count,
                            delta_color="inverse" if significant_count > 0 else "normal")
                d3.metric("Material weaknesses",
                            material_count,
                            delta_color="inverse" if material_count > 0 else "normal",
                            help="Material weakness = SOX/CBK-reportable; major audit issue.")

                st.markdown("### 4️⃣ Overall RCSA verdict")
                issues = []
                if overall_score < 3.5:
                    issues.append(
                        f"COSO overall score is low ({overall_score:.2f})")
                if eff_pct < 70:
                    issues.append(f"control effectiveness is low ({eff_pct:.0f}%)")
                if material_count > 0:
                    issues.append(
                        f"{material_count} material weakness(es) — "
                        "audit committee escalation required")
                if significant_count > 0:
                    issues.append(
                        f"{significant_count} significant deficiency(ies)")
                if weakest_comp[1] < 3.0:
                    issues.append(
                        f"{weakest_comp[0]} component critically weak "
                        f"({weakest_comp[1]:.2f})")

                if not issues:
                    st.success(
                        "✅ **RCSA health: GREEN.** All metrics in healthy ranges. "
                        "Maintain via annual self-assessment cycle.")
                elif len(issues) <= 1:
                    st.warning(
                        f"⚠ **RCSA health: AMBER.** Issue: {issues[0]}. "
                        "Targeted remediation recommended.")
                else:
                    st.error(
                        f"🚨 **RCSA health: RED.** Multiple issues: "
                        f"{'; '.join(issues)}. Comprehensive control review + "
                        "audit committee escalation required.")

                audit_log("IFRS_ENGINE_USED", uname,
                            f"Controls #44 (depth): scorecard issues={len(issues)} "
                            f"score={overall_score:.2f} eff={eff_pct:.0f}% "
                            f"material={material_count} significant={significant_count}")

        # ────────── Inner[1]: Control Test Batch ──────────
        with _rcsa_depth_inner[1]:
            from decimal import Decimal as _D_ctb
            st.markdown(
                "**Control Test Batch Analysis** — runs test_control across a "
                "portfolio of controls in one shot. v5.85 surfaces single-control "
                "test; this batch view enables full quarterly test-cycle reporting.")
            st.caption(
                "Synthetic 10-control portfolio with varied risk levels and "
                "exception rates. Useful for: quarterly internal audit cycles, "
                "test-coverage reporting to audit committee, identifying control "
                "areas with concentrated test failures.")

            if st.button("🎯 Run control test batch",
                           key="rcsa_ctb_btn", type="primary"):
                ctb_tests = [
                    ControlTest("T001", "C001", "CONTROL_ACTIVITIES",
                                 "MEDIUM", sample_size=40, exceptions_found=0),
                    ControlTest("T002", "C002", "CONTROL_ACTIVITIES",
                                 "HIGH", sample_size=60, exceptions_found=1),
                    ControlTest("T003", "C003", "RISK_ASSESSMENT",
                                 "KEY", sample_size=90, exceptions_found=0),
                    ControlTest("T004", "C004", "RISK_ASSESSMENT",
                                 "HIGH", sample_size=60, exceptions_found=3),
                    ControlTest("T005", "C005", "MONITORING_ACTIVITIES",
                                 "MEDIUM", sample_size=40, exceptions_found=5),
                    ControlTest("T006", "C006", "CONTROL_ENVIRONMENT",
                                 "LOW", sample_size=25, exceptions_found=2),
                    ControlTest("T007", "C007", "INFORMATION_COMMUNICATION",
                                 "MEDIUM", sample_size=40, exceptions_found=0),
                    ControlTest("T008", "C008", "CONTROL_ACTIVITIES",
                                 "KEY", sample_size=90, exceptions_found=1),
                    ControlTest("T009", "C009", "CONTROL_ACTIVITIES",
                                 "MEDIUM", sample_size=30, exceptions_found=1),
                    ControlTest("T010", "C010", "MONITORING_ACTIVITIES",
                                 "HIGH", sample_size=60, exceptions_found=2),
                ]

                batch_results = []
                for t in ctb_tests:
                    r = InternalControlsEngine.test_control(t)
                    batch_results.append({
                        "Test ID": t.test_id,
                        "Control": t.control_id,
                        "COSO": t.coso_component[:20],
                        "Risk": t.risk_level,
                        "Sample": int(r["sample_size"]),
                        "Exceptions": int(r["exceptions_found"]),
                        "Effectiveness %":
                            float(_D_ctb(str(r["effectiveness_pct"]))),
                        "Outcome": r["outcome"],
                        "Sample adequate":
                            "✅" if str(r["sample_adequate"]).lower() == "true"
                            else "⚠",
                    })

                # Outcome distribution
                effective_n = sum(1 for r in batch_results
                                    if r["Outcome"] == "EFFECTIVE")
                partial_n = sum(1 for r in batch_results
                                  if r["Outcome"] == "PARTIALLY_EFFECTIVE")
                ineffective_n = sum(1 for r in batch_results
                                      if r["Outcome"] == "INEFFECTIVE")
                inadequate_samples = sum(1 for r in batch_results
                                            if r["Sample adequate"] == "⚠")

                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("Total tests", len(batch_results))
                k2.metric("Effective ✅", effective_n)
                k3.metric("Partially eff ⚠", partial_n)
                k4.metric("Ineffective 🚨", ineffective_n,
                            delta_color="inverse" if ineffective_n > 0 else "normal")
                k5.metric("Sample inadequate ⚠", inadequate_samples,
                            delta_color="inverse" if inadequate_samples > 0 else "normal")

                # Sort by effectiveness asc (worst first)
                batch_results.sort(key=lambda r: r["Effectiveness %"])

                # Display table — format effectiveness column
                display_rows = []
                outcome_emoji = {"EFFECTIVE": "✅", "PARTIALLY_EFFECTIVE": "⚠",
                                   "INEFFECTIVE": "🚨"}
                for r in batch_results:
                    display_rows.append({
                        **{k: v for k, v in r.items() if k != "Effectiveness %"},
                        "Effectiveness %": f"{r['Effectiveness %']:.2f}%",
                        "Status": outcome_emoji.get(r["Outcome"], "⚪"),
                    })
                st.dataframe(pd.DataFrame(display_rows),
                             use_container_width=True, hide_index=True)

                # Concentration insight
                if ineffective_n > 0:
                    # Which COSO components have ineffective controls?
                    ineff_components = [r["COSO"] for r in batch_results
                                          if r["Outcome"] == "INEFFECTIVE"]
                    from collections import Counter as _C_ctb
                    comp_concentration = _C_ctb(ineff_components).most_common(3)
                    st.error(
                        f"🚨 **{ineffective_n} ineffective control(s)** — "
                        f"{', '.join(f'{c[0]} ({c[1]})' for c in comp_concentration)}. "
                        "Immediate remediation required + escalation to audit committee.")

                if inadequate_samples > 0:
                    st.warning(
                        f"⚠ **{inadequate_samples} test(s) used inadequate sample "
                        "size** — engine flags but does not block. Production "
                        "deployment should require minimum sample compliance "
                        "before promoting test outcome to formal audit record.")

                audit_log("IFRS_ENGINE_USED", uname,
                            f"Controls #44 (depth): batch tests={len(batch_results)} "
                            f"effective={effective_n} partial={partial_n} "
                            f"ineffective={ineffective_n} inadequate={inadequate_samples}")

        # ────────── Inner[2]: Aggregate Deficiency Analysis ──────────
        with _rcsa_depth_inner[2]:
            from decimal import Decimal as _D_ad
            st.markdown(
                "**Aggregate Deficiency Analysis** — runs classify_deficiency "
                "across all open deficiencies + aggregates by severity, "
                "by COSO component, and by financial impact tier.")
            st.caption(
                "Useful for: audit committee quarterly reports, identifying "
                "concentration of deficiencies in specific COSO components or "
                "control areas, prioritizing remediation budget. v5.85 "
                "surfaces single-deficiency classification; this aggregates.")

            if st.button("🌐 Run aggregate deficiency analysis",
                           key="rcsa_ad_btn", type="primary"):
                # Synthetic 10-deficiency portfolio
                ad_deficiencies = [
                    ControlDeficiency("D001", "C001", "monitoring gap",
                                        estimated_financial_impact_kes=_D_ad("8000000"),
                                        affects_financial_reporting=True,
                                        compensating_controls_exist=False,
                                        total_assets_kes=_D_ad("100000000")),
                    ControlDeficiency("D002", "C002", "approval workflow lag",
                                        estimated_financial_impact_kes=_D_ad("1500000"),
                                        affects_financial_reporting=True,
                                        compensating_controls_exist=False,
                                        total_assets_kes=_D_ad("100000000")),
                    ControlDeficiency("D003", "C003", "segregation of duties",
                                        estimated_financial_impact_kes=_D_ad("3000000"),
                                        affects_financial_reporting=True,
                                        compensating_controls_exist=False,
                                        total_assets_kes=_D_ad("100000000")),
                    ControlDeficiency("D004", "C004", "documentation gap",
                                        estimated_financial_impact_kes=_D_ad("200000"),
                                        affects_financial_reporting=False,
                                        compensating_controls_exist=True,
                                        total_assets_kes=_D_ad("100000000")),
                    ControlDeficiency("D005", "C005", "user access review delay",
                                        estimated_financial_impact_kes=_D_ad("400000"),
                                        affects_financial_reporting=True,
                                        compensating_controls_exist=True,
                                        total_assets_kes=_D_ad("100000000")),
                    ControlDeficiency("D006", "C006", "vendor risk monitoring",
                                        estimated_financial_impact_kes=_D_ad("700000"),
                                        affects_financial_reporting=False,
                                        compensating_controls_exist=False,
                                        total_assets_kes=_D_ad("100000000")),
                    ControlDeficiency("D007", "C007", "training compliance",
                                        estimated_financial_impact_kes=_D_ad("100000"),
                                        affects_financial_reporting=False,
                                        compensating_controls_exist=True,
                                        total_assets_kes=_D_ad("100000000")),
                    ControlDeficiency("D008", "C008", "data quality monitoring",
                                        estimated_financial_impact_kes=_D_ad("6000000"),
                                        affects_financial_reporting=True,
                                        compensating_controls_exist=False,
                                        total_assets_kes=_D_ad("100000000")),
                    ControlDeficiency("D009", "C009", "policy review overdue",
                                        estimated_financial_impact_kes=_D_ad("80000"),
                                        affects_financial_reporting=False,
                                        compensating_controls_exist=True,
                                        total_assets_kes=_D_ad("100000000")),
                    ControlDeficiency("D010", "C010", "incident response gap",
                                        estimated_financial_impact_kes=_D_ad("2500000"),
                                        affects_financial_reporting=True,
                                        compensating_controls_exist=False,
                                        total_assets_kes=_D_ad("100000000")),
                ]

                ad_results = []
                total_impact = 0.0
                for d in ad_deficiencies:
                    r = InternalControlsEngine.classify_deficiency(d)
                    impact = (float(d.estimated_financial_impact_kes)
                                if d.estimated_financial_impact_kes else 0)
                    total_impact += impact
                    ad_results.append({
                        "Deficiency": d.deficiency_id,
                        "Control": d.control_id,
                        "Description": d.description[:30],
                        "Impact (KES)": impact,
                        "Affects FR": "✅" if d.affects_financial_reporting else "—",
                        "Comp controls": "✅" if d.compensating_controls_exist else "—",
                        "Severity": r.get("severity"),
                    })

                # Severity distribution
                material = sum(1 for r in ad_results
                                 if r["Severity"] == "MATERIAL_WEAKNESS")
                significant = sum(1 for r in ad_results
                                    if r["Severity"] == "SIGNIFICANT_DEFICIENCY")
                deficiency = sum(1 for r in ad_results
                                   if r["Severity"] == "DEFICIENCY")

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total deficiencies", len(ad_results))
                k2.metric("Material weakness 🚨", material,
                            delta_color="inverse" if material > 0 else "normal")
                k3.metric("Significant ⚠", significant,
                            delta_color="inverse" if significant > 0 else "normal")
                k4.metric("Total est. impact (KES)",
                            f"{total_impact:,.0f}")

                # Sort by impact desc
                ad_results.sort(key=lambda r: -r["Impact (KES)"])

                display_rows = [
                    {**{k: v for k, v in r.items() if k != "Impact (KES)"},
                      "Impact (KES)": f"{r['Impact (KES)']:,.0f}"}
                    for r in ad_results
                ]
                st.dataframe(pd.DataFrame(display_rows),
                             use_container_width=True, hide_index=True)

                # Material weakness escalation warning
                if material > 0:
                    material_deficiencies = [r for r in ad_results
                                                if r["Severity"] == "MATERIAL_WEAKNESS"]
                    material_impact = sum(r["Impact (KES)"]
                                            for r in material_deficiencies)
                    st.error(
                        f"🚨 **{material} material weakness(es)** with combined "
                        f"impact KES {material_impact:,.0f} "
                        f"({material_impact/total_impact*100:.0f}% of total). "
                        "Audit committee escalation required + management "
                        "remediation plan with target dates per CBK PG/02 "
                        "internal audit guidelines.")
                if significant > 0:
                    st.warning(
                        f"⚠ **{significant} significant deficiency(ies)** — "
                        "include in next quarterly audit committee report "
                        "with action plan + ownership.")

                audit_log("IFRS_ENGINE_USED", uname,
                            f"Controls #44 (depth): aggregate def total={len(ad_results)} "
                            f"material={material} significant={significant} "
                            f"impact={total_impact:.0f}")

        # ────────── Inner[3]: COSO Investment Map ──────────
        with _rcsa_depth_inner[3]:
            from decimal import Decimal as _D_im
            st.markdown(
                "**COSO Component Investment Map** — coso_component_score "
                "ranked ascending with investment priority bands. v5.85 "
                "surfaces COSO scoring; this view ranks components and "
                "surfaces actionable investment priorities.")
            st.caption(
                f"5 COSO components evaluated. Investment priority bands: "
                f"🔴 CRITICAL <2.5 / 🟡 IMPORTANT <3.5 / 🟢 MONITOR <4.5 / "
                f"✅ STRONG ≥4.5. Scoring is on 1-5 likert.")

            if st.button("🎚️ Compute COSO investment map",
                           key="rcsa_im_btn", type="primary"):
                # Synthetic ratings — Control Environment weakest, Risk Assessment medium
                im_ratings = {p: _D_im("4")
                                for principles in COSO_PRINCIPLES.values()
                                for p in principles}
                # Weaken Control Environment
                im_ratings["P1_INTEGRITY_AND_ETHICAL_VALUES"] = _D_im("2")
                im_ratings["P2_BOARD_OVERSIGHT"] = _D_im("3")
                # Medium Risk Assessment
                im_ratings["P7_RISK_IDENTIFICATION_AND_ANALYSIS"] = _D_im("3")
                # Strong Monitoring
                im_ratings["P16_ONGOING_AND_SEPARATE_EVALUATIONS"] = _D_im("5")

                im_r = InternalControlsEngine.coso_component_score(im_ratings)

                # Build ranked list
                comp_pairs = [(c, float(_D_im(str(s))),
                                len(COSO_PRINCIPLES.get(c, [])))
                               for c, s in im_r["component_scores"].items()]
                comp_pairs.sort(key=lambda p: p[1])  # ascending

                priority_rows = []
                for rank, (comp, score, n_principles) in enumerate(comp_pairs, 1):
                    if score < 2.5:
                        priority = "🔴 CRITICAL — invest immediately"
                    elif score < 3.5:
                        priority = "🟡 IMPORTANT — invest within 6 months"
                    elif score < 4.5:
                        priority = "🟢 MONITOR — annual review"
                    else:
                        priority = "✅ STRONG — maintain current programs"
                    priority_rows.append({
                        "Rank": rank,
                        "COSO Component": comp,
                        "Score (1-5)": f"{score:.2f}",
                        "# Principles": n_principles,
                        "Investment priority": priority,
                    })

                st.dataframe(pd.DataFrame(priority_rows),
                             use_container_width=True, hide_index=True)

                # Bar chart
                chart_data = pd.DataFrame({
                    "Score": [p[1] for p in comp_pairs]
                }, index=[p[0][:24] for p in comp_pairs])
                st.markdown("**COSO component scores (ascending — weakest first):**")
                st.bar_chart(chart_data)

                # Critical/Important callouts
                critical = [r for r in priority_rows
                              if "CRITICAL" in r["Investment priority"]]
                important = [r for r in priority_rows
                               if "IMPORTANT" in r["Investment priority"]]
                if critical:
                    st.error(
                        f"🔴 **{len(critical)} component(s) at CRITICAL level**: "
                        f"{', '.join(r['COSO Component'] for r in critical)}. "
                        "Immediate board-level investment required — these "
                        "are foundational COSO weaknesses.")
                if important:
                    st.warning(
                        f"🟡 **{len(important)} component(s) at IMPORTANT level**: "
                        f"{', '.join(r['COSO Component'] for r in important)}. "
                        "Plan investment within 6-month cycle.")
                if not critical and not important:
                    st.success(
                        "✅ All components at MONITOR or STRONG levels. "
                        "Maintain current internal control programs.")

                # Concentration insight
                weakest_score = comp_pairs[0][1]
                strongest_score = comp_pairs[-1][1]
                spread = strongest_score - weakest_score
                if spread > 1.5:
                    st.info(
                        f"💡 **Wide COSO spread ({spread:.2f} points)** — "
                        "internal controls are uneven. Investing in weakest "
                        "components (especially CONTROL_ENVIRONMENT if weak) "
                        "lifts overall framework most efficiently because "
                        "all other components depend on it.")

                # Missing principles surface
                missing_count = int(im_r.get("missing_count", 0))
                if missing_count > 0:
                    st.warning(
                        f"⚠ **{missing_count} principle(s) missing ratings** "
                        "(Rule 6 transparency). Engine excluded these from "
                        "scoring. Production deployment should ensure all "
                        f"{TOTAL_COSO_PRINCIPLES} COSO principles are rated "
                        "before audit committee submission.")

                audit_log("IFRS_ENGINE_USED", uname,
                            f"Controls #44 (depth): investment map "
                            f"weakest={comp_pairs[0][0]}={comp_pairs[0][1]:.2f} "
                            f"critical={len(critical)} important={len(important)}")


# ════════════════════════════════════════════════════════════════
# TAB 7 — OPERATIONAL RISK ENGINE (Standard #43, integrated v5.85)
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    from utils.operational_risk import (
        OperationalRiskEngine, ORM_CATEGORIES, SEVERITY_LEVELS,
        SEVERITY_THRESHOLDS, EVENT_STATUSES,
    )
    from decimal import Decimal as _D_or

    st.markdown(
        f"**Standard #43 — Operational Risk Loss Events Engine** (Basel III ORM)."
        f" {len(ORM_CATEGORIES)} ORM categories, "
        f"{len(SEVERITY_LEVELS)} severity tiers based on financial impact."
    )
    st.caption(
        f"Severity bands (auto-assigned by impact): "
        f"LOW < KES 100K · MEDIUM < KES 1M · HIGH < KES 10M · SEVERE ≥ KES 10M. "
        f"Categories byte-for-byte from Basel II Op Risk taxonomy."
    )

    # Persistent engine instance via session_state
    if "_orm_engine" not in st.session_state:
        st.session_state._orm_engine = OperationalRiskEngine()
    ore = st.session_state._orm_engine

    or_sub_tabs = st.tabs([
        "📝 Log Loss Event",
        "📊 Aggregate by Category",
        "📈 KRI Metrics",
        "🌳 Engine Reference",
    ])

    # ──────── Log loss event ────────
    with or_sub_tabs[0]:
        st.markdown(
            "**Log a loss event** — engine assigns severity automatically based "
            "on financial impact and validates category against Basel taxonomy.")

        c1, c2 = st.columns(2)
        with c1:
            le_cat = st.selectbox("Basel ORM category",
                                     list(ORM_CATEGORIES),
                                     index=1, key="or_le_cat",
                                     help="Standard Basel II Op Risk taxonomy.")
            le_date = st.date_input("Event date",
                                       value=today, key="or_le_date")
        with c2:
            le_branch = st.text_input("Branch code",
                                         value="BR_100", key="or_le_branch")
            le_impact = st.number_input("Financial impact (KES M)",
                                           min_value=0.0, value=2.5, step=0.5,
                                           key="or_le_impact",
                                           help="Leave at 0 for events with no quantified impact yet.")

        le_desc = st.text_area("Event description",
                                 value="Card skimming detected at ATM; "
                                       "5 cards compromised, customers reimbursed",
                                 height=80, key="or_le_desc")

        if st.button("Log loss event",
                       key="or_le_btn", type="primary"):
            r = ore.log_loss_event(
                category=le_cat,
                event_date=str(le_date),
                description=le_desc,
                financial_impact_kes=(float(le_impact) * 1_000_000) if le_impact > 0 else None,
                branch_code=le_branch,
                reported_by=uname,
            )
            if r.get("success"):
                severity = r["severity"]
                colors = {"LOW": "#10B981", "MEDIUM": "#3B82F6",
                          "HIGH": "#F59E0B", "SEVERE": "#DC2626"}
                color = colors.get(severity, "#6B7280")

                k1, k2, k3 = st.columns(3)
                k1.metric("Event ID",
                           r["event_id"][-8:],
                           help=f"Full ID: {r['event_id']}")
                k2.metric("Category", r["category"])
                with k3:
                    st.markdown(
                        f"<div style='padding:8px 12px;background:{color}22;"
                        f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"SEVERITY (auto)</div>"
                        f"<div style='font-size:18px;font-weight:800;color:{color}'>"
                        f"{severity}</div></div>",
                        unsafe_allow_html=True)

                if severity == "SEVERE":
                    st.error(
                        "🔴 **SEVERE event** — material loss event. "
                        "Notify CRO + Audit Committee. "
                        "May require external disclosure under CBK PG/06.")
                elif severity == "HIGH":
                    st.warning(
                        "⚠ **HIGH severity** — escalate to risk committee. "
                        "Root cause analysis required within 30 days.")
                else:
                    st.success(
                        f"✅ Event logged — {severity} severity. "
                        "Aggregate analysis available in next tab.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"OpRisk #43: log {r['event_id']} {le_cat} {severity}")
            else:
                st.error(f"⛔ {r.get('error', 'log failed')}")

        # Show count in current session
        n_events = len(ore._events)
        st.caption(
            f"📊 Session events logged: **{n_events}** "
            f"(stored in-memory for this Streamlit session; "
            "production deployment would feed via `event_store_fn` to persistent DB).")

    # ──────── Aggregate by category ────────
    with or_sub_tabs[1]:
        st.markdown(
            "**Aggregate Losses by Category** — total impact, average loss, "
            "and severity distribution across the 7 Basel ORM categories.")

        c1, c2 = st.columns(2)
        with c1:
            agg_start = st.date_input("Period start",
                                         value=today.replace(day=1), key="or_agg_start")
        with c2:
            agg_end = st.date_input("Period end",
                                       value=today, key="or_agg_end")

        if st.button("Compute aggregate",
                       key="or_agg_btn", type="primary"):
            r = ore.aggregate_losses_by_category(
                str(agg_start), str(agg_end))
            total = _D_or(str(r["total_impact"]))
            event_ct = int(r["total_event_count"])

            k1, k2 = st.columns(2)
            k1.metric("Total events", event_ct)
            k2.metric("Total impact",
                       f"KES {total/_D_or('1000000'):,.2f}M")

            if event_ct == 0:
                st.info(
                    "ℹ No events logged in this period. "
                    "Use the Log Loss Event tab to add some, then re-run.")
            else:
                rows = []
                for cat, info in r["by_category"].items():
                    cat_count = int(info["event_count"])
                    if cat_count == 0:
                        continue  # skip empty categories
                    cat_total = _D_or(str(info["total_impact"]))
                    avg = info.get("average_loss")
                    sev_dist = info["by_severity"]
                    rows.append({
                        "Category": cat,
                        "Events": cat_count,
                        "Total (KES M)":
                            float(cat_total / _D_or("1000000")),
                        "Avg loss (KES M)":
                            float(_D_or(str(avg)) / _D_or("1000000"))
                            if avg and avg != "None" else None,
                        "L/M/H/S":
                            f"{sev_dist['LOW']}/{sev_dist['MEDIUM']}/"
                            f"{sev_dist['HIGH']}/{sev_dist['SEVERE']}",
                    })
                if rows:
                    st.dataframe(pd.DataFrame(rows),
                                 use_container_width=True, hide_index=True)

                # Bar chart by category
                chart_data = pd.DataFrame({
                    "Total (KES M)": [r["Total (KES M)"] for r in rows]
                }, index=[r["Category"] for r in rows])
                st.bar_chart(chart_data)
                audit_log("IFRS_ENGINE_USED", uname,
                           f"OpRisk #43: aggregate {agg_start}→{agg_end} "
                           f"events={event_ct} total={total}")

    # ──────── KRI Metrics ────────
    with or_sub_tabs[2]:
        st.markdown(
            "**Key Risk Indicators** — frequency, severity distribution, "
            "and severe-event count for the period.")

        c1, c2 = st.columns(2)
        with c1:
            kri_start = st.date_input("Period start",
                                         value=today.replace(day=1), key="or_kri_start")
        with c2:
            kri_end = st.date_input("Period end",
                                       value=today, key="or_kri_end")

        if st.button("Compute KRIs",
                       key="or_kri_btn", type="primary"):
            r = ore.compute_kri_metrics(
                str(kri_start), str(kri_end))
            event_freq = int(r["event_frequency"])
            severe = int(r["severe_events"])
            days = int(r["period_days"])
            per_day = float(_D_or(str(r["events_per_day"])))

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Event frequency", event_freq)
            k2.metric("Period (days)", days)
            k3.metric("Events / day",
                       f"{per_day:.3f}")
            severe_color = ("#DC2626" if severe > 0 else "#10B981")
            with k4:
                st.markdown(
                    f"<div style='padding:8px 12px;background:{severe_color}22;"
                    f"border-left:4px solid {severe_color};border-radius:8px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"SEVERE EVENTS</div>"
                    f"<div style='font-size:18px;font-weight:800;color:{severe_color}'>"
                    f"{severe}</div></div>",
                    unsafe_allow_html=True)

            if event_freq == 0:
                st.info(
                    "ℹ No events logged in this period.")
            else:
                # Severity distribution chart
                sev_dist = r["severity_distribution"]
                sev_rows = [
                    {"Severity": s,
                      "Count": int(sev_dist.get(s, 0))}
                    for s in SEVERITY_LEVELS
                ]
                st.dataframe(pd.DataFrame(sev_rows),
                             use_container_width=True, hide_index=True)

                if severe > 0:
                    st.error(
                        f"🔴 **{severe} SEVERE event(s)** in period — "
                        "executive escalation appropriate; "
                        "Audit Committee briefing required per CBK PG/06.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"OpRisk #43: KRI freq={event_freq} severe={severe} "
                           f"days={days}")

    # ──────── Engine reference ────────
    with or_sub_tabs[3]:
        st.markdown("**Engine Constants Reference** (Basel II ORM taxonomy)")

        st.markdown(f"**{len(ORM_CATEGORIES)} ORM categories** "
                    "(byte-for-byte from `ORM_CATEGORIES` constant):")
        cat_descriptions = {
            "INTERNAL_FRAUD": "Embezzlement, unauthorized trading, theft by employees",
            "EXTERNAL_FRAUD": "Card fraud, robbery, hacking, identity theft",
            "EMPLOYMENT_PRACTICES": "Discrimination, workplace safety, employment violations",
            "CLIENTS_PRODUCTS_BUSINESS": "Mis-selling, account churning, fiduciary breaches",
            "DAMAGE_PHYSICAL_ASSETS": "Natural disasters, terrorism, vandalism",
            "BUSINESS_DISRUPTION": "System failures, datacenter outages, network issues",
            "EXECUTION_DELIVERY": "Settlement errors, missed deadlines, processing mistakes",
        }
        cat_rows = [
            {"Category": c,
              "Description": cat_descriptions.get(c, "")}
            for c in ORM_CATEGORIES
        ]
        st.dataframe(pd.DataFrame(cat_rows),
                     use_container_width=True, hide_index=True)

        st.markdown(f"**Severity thresholds** "
                    "(byte-for-byte from `SEVERITY_THRESHOLDS`):")
        sev_rows = [
            {"Severity": s,
              "Threshold (KES)":
                  f"< {_D_or(str(SEVERITY_THRESHOLDS[s])):,.0f}"
                  if SEVERITY_THRESHOLDS[s] is not None
                  else "≥ 10,000,000 (SEVERE has no upper bound)"}
            for s in SEVERITY_LEVELS
        ]
        st.dataframe(pd.DataFrame(sev_rows),
                     use_container_width=True, hide_index=True)

        st.markdown(f"**Event statuses** ({EVENT_STATUSES}):")
        st.caption(
            "Status field exists on the engine event store but is not exposed "
            "in the simplified UI integration; event lifecycle (OPEN → "
            "INVESTIGATING → RESOLVED → CLOSED) would be modelled in a "
            "production deployment with its own management UI.")
