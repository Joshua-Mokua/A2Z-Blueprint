"""pages/_admin_sprint.py — Sprint Modules Admin Config (Tab 25).
All configurable settings for the 10 sprint modules, grouped by department.
Hard-coded items are clearly labelled as such.
"""
import streamlit as st
import json
from pathlib import Path
from utils.core_audit import audit_log
from utils.core import get_org_config, save_org_config
from utils.db import db as a2z_db

DATA = Path(__file__).parent.parent / "data"


def _section(icon, title, dept_colour="#006B3F"):
    st.markdown(
        f"<div style='background:{dept_colour}12;border-left:4px solid {dept_colour};"
        f"padding:10px 16px;border-radius:0 8px 8px 0;margin:18px 0 10px'>"
        f"<span style='font-weight:700;font-size:14px'>{icon} {title}</span></div>",
        unsafe_allow_html=True)


def render_sprint_config(tab, uname):
    with tab:
        st.subheader("🚀 Sprint Modules Configuration")
        st.caption(
            "Settings for the 10 new modules added in Sprint 10. "
            "Each section shows what is configurable (saved to org_config.json) "
            "and what is hard-coded (built into the module logic and requires a code change).")

        org = get_org_config()
        thr = org.setdefault("thresholds", {})
        changed = {}

        sp_tabs = st.tabs([
            "📑 Finance","📉 Treasury","🛡️ Risk & Compliance",
            "🤝 Commercial","👥 HR","🔄 IT & Digital","🗂️ Projects"
        ])

        # ── FINANCE: Mgmt Accounts + Transfer Pricing ──────────────
        with sp_tabs[0]:
            _section("📑","Management Accounts Pack","#185FA5")
            st.markdown("**Configurable:**")
            c1,c2,c3 = st.columns(3)
            cir_v = c1.number_input("CIR target (%)", 30.0, 80.0,
                                     float(thr.get("cir_target_pct",55)), key="sp_cir")
            npl_v = c2.number_input("NPL warning (%)", 1.0, 20.0,
                                     float(thr.get("npl_warning_pct",5.0)), 0.5, key="sp_npl")
            roe_v = c3.number_input("ROE target (%)", 5.0, 40.0,
                                     float(thr.get("roe_target_pct",15.0)), key="sp_roe")
            if abs(cir_v - thr.get("cir_target_pct",55)) > 0.01: changed["cir_target_pct"] = cir_v
            if abs(npl_v - thr.get("npl_warning_pct",5.0)) > 0.01: changed["npl_warning_pct"] = npl_v
            if abs(roe_v - thr.get("roe_target_pct",15.0)) > 0.01: changed["roe_target_pct"] = roe_v
            st.markdown("**Hard-coded (requires code change):**")
            st.info("📌 P&L line items, balance sheet structure, ratio formulas (NIM/CIR/ROA/ROE/CAR).\n"
                    "📌 Prior month comparison always uses the preceding calendar month.\n"
                    "📌 Data source: `data/mgmt_accounts.json` auto-populated from CBS actuals engine.")

            _section("💱","Transfer Pricing (FTP)","#185FA5")
            st.markdown("**Configurable:**")
            d1,d2 = st.columns(2)
            ftp_w = d1.number_input("NIM spread warning below (%)", 0.1, 3.0,
                                     float(thr.get("ftp_spread_warning_pct",0.5)), 0.1, key="sp_ftpw")
            ftp_f = d2.number_input("Mortgage FTP floor (%)", 10.0, 20.0,
                                     float(thr.get("ftp_mortgage_floor_pct",13.5)), 0.5, key="sp_ftpf")
            if abs(ftp_w - thr.get("ftp_spread_warning_pct",0.5)) > 0.001: changed["ftp_spread_warning_pct"] = ftp_w
            if abs(ftp_f - thr.get("ftp_mortgage_floor_pct",13.5)) > 0.001: changed["ftp_mortgage_floor_pct"] = ftp_f
            st.markdown("**FTP curve (configurable via Treasury Config tab):**")
            ftp_data_p = DATA / "transfer_pricing.json"
            if ftp_data_p.exists():
                ftp_data = a2z_db.load_json(ftp_data_p, default={})
                ftp_rates = ftp_data.get("ftp_rates", {})
                fcols = st.columns(len(ftp_rates) if ftp_rates else 1)
                new_ftp = {}
                for col, (tenor, rate) in zip(fcols, ftp_rates.items()):
                    new_ftp[tenor] = col.number_input(f"FTP {tenor} (%)", 8.0, 25.0,
                                                       float(rate), 0.1, key=f"sp_ftp_{tenor}")
                if st.button("💾 Save FTP curve", key="sp_ftp_save"):
                    ftp_data["ftp_rates"] = new_ftp
                    a2z_db.save_json(ftp_data_p, ftp_data)
                    audit_log("FTP_CURVE_UPDATED", uname, f"{len(new_ftp)} tenors saved")
                    st.success("✅ FTP curve saved")
            st.markdown("**Hard-coded:**")
            st.info("📌 Product list for NIM attribution: defined in `transfer_pricing.json`.\n"
                    "📌 FTP methodology: pool-based matched maturity. Formula is fixed.\n"
                    "📌 Base rate always reads from `org_config.json['base_cbr_pct']`.")

        # ── TREASURY: IRRBB ────────────────────────────────────────
        with sp_tabs[1]:
            _section("📉","IRRBB Dashboard","#854F0B")
            st.markdown("**Configurable (CBK IRRBB Guideline 2021):**")
            i1,i2,i3,i4 = st.columns(4)
            ear_w = i1.number_input("EaR warning (%)", 5.0, 19.0,
                                     float(thr.get("irrbb_ear_warning_pct",15.0)), key="sp_earw")
            ear_l = i2.number_input("EaR CBK limit (%)", 10.0, 25.0,
                                     float(thr.get("irrbb_ear_limit_pct",20.0)), key="sp_earl")
            eve_w = i3.number_input("EVE warning (%)", 5.0, 19.0,
                                     float(thr.get("irrbb_eve_warning_pct",15.0)), key="sp_evew")
            eve_l = i4.number_input("EVE CBK limit (%)", 10.0, 25.0,
                                     float(thr.get("irrbb_eve_limit_pct",20.0)), key="sp_evel")
            for k,v in [("irrbb_ear_warning_pct",ear_w),("irrbb_ear_limit_pct",ear_l),
                        ("irrbb_eve_warning_pct",eve_w),("irrbb_eve_limit_pct",eve_l)]:
                if abs(v - thr.get(k,20.0)) > 0.01: changed[k] = v
            st.caption("CBK default limits: EaR ≤ 20% of projected NII, EVE ≤ 20% of Tier 1 Capital. "
                       "Warning triggers at 15% to allow corrective action before breach.")
            st.markdown("**Hard-coded:**")
            st.info("📌 Rate shock scenarios: +200bps, +100bps, -100bps, -200bps, Parallel+200 "
                    "(CBK-prescribed — cannot be removed, only data values change).\n"
                    "📌 Repricing bucket definitions: 0-1M, 1-3M, 3-6M, 6-12M, 1-3Y, >3Y.\n"
                    "📌 EaR formula: repricing_gap × rate_shock × time_factor.\n"
                    "📌 Data source: `data/irrbb.json` updated by ALM team or CBS feed.")

        # ── RISK & COMPLIANCE: RCSA + AML ─────────────────────────
        with sp_tabs[2]:
            _section("🛡️","Operational Risk Register (RCSA)","#A32D2D")
            st.markdown("**Configurable:**")
            r1,r2,r3 = st.columns(3)
            rh = r1.number_input("High residual score ≥", 8, 25,
                                  int(thr.get("rcsa_high_residual",12)), key="sp_rh")
            rm = r2.number_input("Medium residual score ≥", 3, 12,
                                  int(thr.get("rcsa_medium_residual",6)), key="sp_rm")
            rd = r3.number_input("Review frequency (days)", 30, 365,
                                  int(thr.get("rcsa_review_frequency_days",90)), key="sp_rd")
            for k,v in [("rcsa_high_residual",rh),("rcsa_medium_residual",rm),("rcsa_review_frequency_days",rd)]:
                if v != thr.get(k): changed[k] = v
            st.markdown("**Risk categories (configurable via module):**")
            rcsa_p = DATA / "rcsa_register.json"
            if rcsa_p.exists():
                risks = a2z_db.load_json(rcsa_p, default=[])
                cats = sorted(set(r.get("category","") for r in risks))
                st.caption(f"Current categories: {', '.join(cats)}")
            st.markdown("**Hard-coded:**")
            st.info("📌 Residual score = inherent_score × control_factor "
                    "(0.4=Adequate, 0.6=Partial, 0.85=Inadequate).\n"
                    "📌 KRI breach logic: value > threshold.\n"
                    "📌 RCSA methodology follows Basel II/III operational risk framework.")

            _section("🔍","AML Transaction Monitoring","#A32D2D")
            st.markdown("**Configurable:**")
            a1,a2,a3 = st.columns(3)
            ah = a1.number_input("High-risk score threshold", 50, 100,
                                  int(thr.get("aml_high_risk_score",70)), key="sp_amlh")
            as_ = a2.number_input("STR flag threshold (KES M)", 0.5, 50.0,
                                   float(thr.get("aml_str_threshold_m",5.0)), 0.5, key="sp_amls")
            ac = a3.number_input("Cash reporting threshold (KES M)", 0.1, 5.0,
                                  float(thr.get("aml_cash_threshold_m",1.0)), 0.1, key="sp_amlc")
            for k,v in [("aml_high_risk_score",ah),("aml_str_threshold_m",as_),("aml_cash_threshold_m",ac)]:
                if abs(float(v) - float(thr.get(k,70))) > 0.001: changed[k] = v
            st.markdown("**AML monitoring rules (hard-coded, regulatory):**")
            st.info("📌 Transaction monitoring rules are hard-coded to POCAMLA 2009 and CBK "
                    "AML/CFT Guideline requirements (cash, structuring, PEP, cross-border, dormant).\n"
                    "📌 STR filing requirement: within 3 days of suspicion (Section 44, POCAMLA).\n"
                    "📌 Risk scoring model: rule-based (not ML) with configurable thresholds above.\n"
                    "📌 FRC reporting: manual — compliance officer files STR via FRC portal.")

        # ── COMMERCIAL: Deal Room ─────────────────────────────────
        with sp_tabs[3]:
            _section("🤝","Deal Room & Term Sheet Engine","#0F6E56")
            st.markdown("**Configurable:**")
            dr1,dr2 = st.columns(2)
            dr_sla  = dr1.number_input("CP satisfaction SLA (days after signing)", 7, 90,
                                        int(thr.get("deal_room_cp_sla_days",14)), key="sp_drsla")
            dr_dscr = dr2.number_input("Minimum DSCR covenant default", 1.0, 3.0,
                                        float(thr.get("deal_room_min_dscr",1.2)), 0.1, key="sp_drdscr")
            for k,v in [("deal_room_cp_sla_days",dr_sla),("deal_room_min_dscr",dr_dscr)]:
                if abs(float(v) - float(thr.get(k,14))) > 0.001: changed[k] = v

            st.markdown("**Deal types and standard covenants (configurable):**")
            pc_p = DATA / "pipeline_settings.json"
            if pc_p.exists():
                ps_d = a2z_db.load_json(pc_p, default={})
                deal_types = ps_d.get("deal_types", [])
                dt_text = st.text_area("Deal types (one per line)",
                                       value="\n".join(deal_types),
                                       height=100, key="sp_dt")
                if st.button("💾 Save deal types", key="sp_dt_save"):
                    ps_d["deal_types"] = [x.strip() for x in dt_text.splitlines() if x.strip()]
                    a2z_db.save_json(pc_p, ps_d)
                    audit_log("DEAL_TYPES_UPDATED", uname, f"{len(ps_d['deal_types'])} types")
                    st.success("✅ Deal types saved")
            st.markdown("**Hard-coded:**")
            st.info("📌 Term sheet PDF template: uses bank letterhead + standard legal boilerplate.\n"
                    "📌 Fee calculations: arrangement fee on facility amount, commitment fee on undrawn.\n"
                    "📌 Deal stages flow: links directly from Pipeline module stages.")

        # ── HR: Workforce + Disciplinary ─────────────────────────
        with sp_tabs[4]:
            _section("📋","Workforce Planning","#3C3489")
            st.markdown("**Configurable:**")
            hr1,hr2 = st.columns(2)
            wf_a = hr1.number_input("Attrition warning (%)", 5.0, 30.0,
                                     float(thr.get("workforce_attrition_warn_pct",12.0)), key="sp_wfa")
            wf_s = hr2.number_input("Min succession candidates (critical roles)", 1, 5,
                                     int(thr.get("workforce_succession_min",1)), key="sp_wfs")
            for k,v in [("workforce_attrition_warn_pct",wf_a),("workforce_succession_min",wf_s)]:
                if abs(float(v) - float(thr.get(k,12.0))) > 0.001: changed[k] = v
            st.markdown("**Hard-coded:**")
            st.info("📌 Headcount data sourced from `data/workforce_planning.json` — "
                    "updated from HR system or manual upload.\n"
                    "📌 Succession depth ratings: Strong/Adequate/Thin/Critical are fixed labels.\n"
                    "📌 Gender ratio calculation: always Female % of total.")

            _section("⚖️","Disciplinary Register","#3C3489")
            st.markdown("**Access control (configurable):**")
            st.info("Access is restricted to HR team and Global Admins. "
                    "This is enforced by `require_access('disciplinary')` + role check in the page. "
                    "To grant a non-HR user access, add `disciplinary` to their accessible_modules "
                    "in Admin → Permissions.")
            st.markdown("**Hard-coded:**")
            st.info("📌 Offence categories: fixed to standard HR disciplinary framework.\n"
                    "📌 Outcome options: Warning/Final Warning/Suspension/Dismissal/Cleared.\n"
                    "📌 All records marked `confidential: true` — visible only to HR/Admin.\n"
                    "📌 No email notifications built in (by design — handle outside the system).")

        # ── IT & DIGITAL: CAB ─────────────────────────────────────
        with sp_tabs[5]:
            _section("🔄","Change Management Register (CAB)","#533AB7")
            st.markdown("**Configurable systems list:**")
            cab_p = DATA / "cab_register.json"
            if cab_p.exists():
                cab_d = a2z_db.load_json(cab_p, default={})
                curr_systems = sorted(set(c.get("system","") for c in cab_d))
                st.caption(f"Systems currently in register: {', '.join(curr_systems)}")
            st.markdown("**CBK notification flag:**")
            st.info("The CBK ICT notification requirement (CBK ICT/08/2019 Guideline) is flagged "
                    "automatically on Emergency changes and any change where `cbk_notification_required` "
                    "is checked. The actual notification to CBK is done outside the system.")
            st.markdown("**Hard-coded:**")
            st.info("📌 Change types: Standard, Normal, Emergency, Pre-approved — fixed per ITIL.\n"
                    "📌 Risk levels: Low/Medium/High — fixed.\n"
                    "📌 PIR requirement: mandatory for Emergency changes (auto-flagged).\n"
                    "📌 Status flow: Draft → Pending CAB → CAB Approved → Implementing → Completed.")

        # ── PROJECTS ─────────────────────────────────────────────
        with sp_tabs[6]:
            _section("🗂️","Project Management","#185FA5")
            st.markdown("**Configurable:**")
            p1,p2,p3 = st.columns(3)
            pb_a = p1.number_input("Budget Amber trigger (%)", 60, 100,
                                    int(thr.get("project_budget_amber_pct",85)), key="sp_pba")
            pc_a = p2.number_input("Completion Amber below (%)", 30, 90,
                                    int(thr.get("project_completion_amber_pct",70)), key="sp_pca")
            pd_r = p3.number_input("Milestone overdue Red (days)", 1, 30,
                                    int(thr.get("project_overdue_days_red",7)), key="sp_pdr")
            for k,v in [("project_budget_amber_pct",pb_a),("project_completion_amber_pct",pc_a),("project_overdue_days_red",pd_r)]:
                if v != thr.get(k): changed[k] = v
            st.markdown("**Link from Execute module:**")
            st.info("When an initiative in the Execute module is approved through Gate G4 (Implementation), "
                    "a project record is created in Projects with `initiative_id` linking back. "
                    "The Projects module shows the initiative ID and links back to Execute.\n"
                    "To convert an initiative manually: create a project in Projects → New Project "
                    "and enter the initiative ID.")
            st.markdown("**Hard-coded:**")
            st.info("📌 RAG logic: Green/Amber/Red set by PM. Auto-flags based on budget/overdue thresholds above.\n"
                    "📌 Project categories: Technology/Operations/Business/Compliance/People/Infrastructure.\n"
                    "📌 Status flow: Initiation → Planning → Executing → Monitoring → Completed.\n"
                    "📌 All departments can view their own projects. Global admins see all.")

        # ── SAVE BUTTON ───────────────────────────────────────────
        st.markdown("---")
        if st.button("💾 Save all sprint threshold changes", key="sp_save_all", type="primary"):
            if changed:
                for k,v in changed.items():
                    org["thresholds"][k] = v
                save_org_config(org)
                audit_log("SPRINT_THRESHOLDS_SAVED", uname, f"{len(changed)} thresholds updated: {list(changed.keys())}")
                st.success(f"✅ {len(changed)} threshold(s) saved: {', '.join(changed.keys())}")
                st.cache_data.clear()
                st.rerun()
            else:
                st.info("No changes to save.")
