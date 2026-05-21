"""pages/64_vendors.py — Vendor Management Register.
Vendor onboarding, KRA compliance, performance ratings, contract linkage.
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
from utils.core_audit import audit_log

require_access("operations.vendor_management")

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update — called after every save action."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_proc  = any(x in role for x in ("procurement","head of procurement","facilities"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🤝 Vendor Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Vendor register · KRA compliance · Performance · Onboarding · Suspension</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA / "vendor_register.json"
    return a2z_db.load_json(p) if p.exists() else []

vendors = _load()
active     = [v for v in vendors if v.get("status")=="Active"]
non_kra    = [v for v in vendors if not v.get("tax_compliance")]
no_insur   = [v for v in vendors if not v.get("insurance_valid")]
suspended  = [v for v in vendors if v.get("status")=="Suspended"]

if non_kra:
    st.error(f"🔴 {len(non_kra)} vendor(s) with invalid KRA compliance — payments should be withheld")
if suspended:
    st.warning(f"⚠️ {len(suspended)} vendor(s) suspended — check before raising POs")

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Vendors",   len(vendors))
m2.metric("Active",          len(active))
m3.metric("KRA Non-Compliant",len(non_kra),delta_color="normal" if not non_kra else "inverse")
m4.metric("Suspended",       len(suspended))

tabs = st.tabs([
    "📋 Vendor List",
    "⚠️ Compliance",
    "📊 Performance",
    "🛡️ Risk Assessment",
    "🛒 Procurement Workflow",
    "➕ Onboard Vendor",
])

with tabs[0]:
    f1,f2 = st.columns(2)
    fstat = f1.selectbox("Status",["All","Active","Suspended","Under Review"],key="vnd_st")
    fcat  = f2.selectbox("Category",["All"]+sorted(set(v.get("category","") for v in vendors)),key="vnd_cat")
    vis   = [v for v in vendors
             if (fstat=="All" or v.get("status")==fstat)
             and (fcat=="All" or v.get("category")==fcat)]
    rows  = [{"ID":v["id"],"Vendor":v["name"][:25],"Category":v["category"][:18],
               "KRA":"✅" if v.get("tax_compliance") else "❌",
               "Insurance":"✅" if v.get("insurance_valid") else "❌",
               "Rating":v.get("rating",0),"Spend YTD (M)":v.get("total_spend_ytd_m",0),
               "Open POs":v.get("open_pos",0),"Status":v.get("status",""),
               "Last Review":v.get("last_reviewed","")[:10]}
              for v in sorted(vis, key=lambda x: -x.get("total_spend_ytd_m",0))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[1]:
    st.markdown("**KRA non-compliant vendors — payments must be withheld:**")
    if non_kra:
        nc_rows = [{"Vendor":v["name"],"Spend YTD (M)":v.get("total_spend_ytd_m",0),
                     "Last Review":v.get("last_reviewed","")[:10],"Status":v.get("status","")}
                    for v in non_kra]
        st.dataframe(pd.DataFrame(nc_rows), use_container_width=True, hide_index=True)
        st.caption("⚠️ Per KRA regulation, withholding tax must be applied and valid compliance certificates required before payment.")
    else:
        st.success("✅ All vendors KRA-compliant")

    st.markdown("**No insurance coverage:**")
    if no_insur:
        ni_rows = [{"Vendor":v["name"],"Category":v["category"],"Status":v.get("status","")}
                    for v in no_insur]
        st.dataframe(pd.DataFrame(ni_rows), use_container_width=True, hide_index=True)

with tabs[2]:
    top = sorted(vendors, key=lambda x: -x.get("total_spend_ytd_m",0))[:10]
    st.markdown("**Top 10 vendors by YTD spend:**")
    st.bar_chart(pd.DataFrame({"Spend YTD (M)":{v["name"]:v["total_spend_ytd_m"] for v in top}}))
    st.markdown("**Vendor performance ratings:**")
    rat_rows = [{"Vendor":v["name"][:25],"Rating":v.get("rating",0),
                  "Spend YTD (M)":v.get("total_spend_ytd_m",0),
                  "Category":v.get("category","")[:18]}
                 for v in sorted(vendors, key=lambda x: -x.get("rating",0))]
    st.dataframe(pd.DataFrame(rat_rows), use_container_width=True, hide_index=True)

with tabs[3]:
    # ── IAS-style Risk Assessment (Standard #96 Vendor Risk, integrated v5.74) ──
    from utils.vendor_risk import (
        VendorRiskEngine, VendorRecord,
        VENDOR_TIERS, VENDOR_CATEGORIES,
        REVIEW_CADENCE_DAYS, SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS,
        VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT,
        DUE_DILIGENCE_CHECKS, CRITICAL_TIER_REQUIRED_CHECKS,
        LOWER_TIER_REQUIRED_CHECKS, CONTRACT_RENEWAL_NOTICE_DAYS,
        SLA_BREACH_SEVERITIES,
    )
    from decimal import Decimal as _D
    from datetime import date as _date, datetime as _dt

    st.markdown(
        "**Standard #96 — Third-Party Risk & Outsourcing Oversight** "
        "(CBK PG/06 + Banking Act). Engine `VendorRiskEngine`.")
    st.caption(
        f"4 vendor tiers ({' / '.join(VENDOR_TIERS)}); review cadence "
        f"TIER_1={REVIEW_CADENCE_DAYS['TIER_1_CRITICAL']}d / "
        f"TIER_2={REVIEW_CADENCE_DAYS['TIER_2_HIGH']}d / "
        f"TIER_3={REVIEW_CADENCE_DAYS['TIER_3_MEDIUM']}d / "
        f"TIER_4={REVIEW_CADENCE_DAYS['TIER_4_LOW']}d. "
        f"Single-vendor concentration alert at "
        f"≥{VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT}% within a category."
    )

    risk_sub_tabs = st.tabs([
        "🔍 Due Diligence Check",
        "📅 Review Schedule",
        "📊 Concentration Risk",
        "⚠️ SLA Breach Severity",
    ])

    # ---- Due diligence check ----
    with risk_sub_tabs[0]:
        st.markdown("**Verify required due-diligence checks for a single vendor**")
        st.caption(
            f"TIER_1_CRITICAL requires ALL 5 checks "
            f"({', '.join(CRITICAL_TIER_REQUIRED_CHECKS)}). "
            f"Lower tiers require minimum 2 ({', '.join(LOWER_TIER_REQUIRED_CHECKS)})."
        )
        c1, c2 = st.columns(2)
        with c1:
            dd_vid = st.text_input("Vendor ID", value="V001", key="dd_vid")
            dd_cat = st.selectbox("Category", list(VENDOR_CATEGORIES), key="dd_cat")
            dd_tier = st.selectbox("Tier", list(VENDOR_TIERS), key="dd_tier")
        with c2:
            dd_spend = st.number_input("Annual spend (KES M)",
                                         min_value=0.0, value=50.0, step=1.0,
                                         key="dd_spend")
            st.markdown("**Completed checks:**")
            dd_checks = []
            for check in DUE_DILIGENCE_CHECKS:
                if st.checkbox(check.replace("_", " ").title(), key=f"dd_chk_{check}"):
                    dd_checks.append(check)

        if st.button("Run DD check", key="dd_btn", type="primary"):
            v = VendorRecord(
                vendor_id=dd_vid, category=dd_cat, tier=dd_tier,
                annual_spend_kes=_D(str(dd_spend)) * _D("1000000"),
                completed_dd_checks=dd_checks)
            r = VendorRiskEngine.due_diligence_completeness(v)
            complete = r.get("complete")
            eligible = r.get("eligible_for_onboarding")
            if complete:
                st.success(
                    f"✅ Due diligence COMPLETE — {dd_vid} eligible for onboarding. "
                    f"All {len(r.get('required_checks', []))} required checks satisfied.")
            else:
                missing = r.get("missing_checks", [])
                st.error(
                    f"⛔ Due diligence INCOMPLETE — {len(missing)} check(s) missing: "
                    f"**{', '.join(missing)}**. "
                    f"Onboarding BLOCKED until checks completed (Rule 6 fail-closed)."
                )
            with st.expander("Engine response detail"):
                st.json(r)
            audit_log("IFRS_ENGINE_USED", uname,
                       f"VendorRisk #96: DD check {dd_vid} tier={dd_tier} "
                       f"complete={complete}")

    # ---- Review schedule ----
    with risk_sub_tabs[1]:
        st.markdown("**Periodic Review Status — All Vendors**")
        st.caption(
            "Per CBK PG/06, vendors must be re-reviewed at tier-specific cadences. "
            "Overdue reviews trigger remediation."
        )

        # Build review table from the loaded vendor register
        if not vendors:
            st.info("No vendors in register — onboard a vendor first.")
        else:
            review_rows = []
            overdue_count = 0
            due_soon_count = 0
            for v in vendors:
                # Map page's vendor record fields to engine VendorRecord fields
                # The page stores last_reviewed as ISO string; map category to a tier heuristically
                cat = v.get("category", "Other") or "Other"
                last_review_str = v.get("last_reviewed", "")[:10]
                # Heuristic tier mapping (page lacks explicit tier; spend-based proxy)
                spend_m = float(v.get("total_spend_ytd_m", 0) or 0)
                if spend_m >= 50:
                    tier = "TIER_1_CRITICAL"
                elif spend_m >= 10:
                    tier = "TIER_2_HIGH"
                elif spend_m >= 1:
                    tier = "TIER_3_MEDIUM"
                else:
                    tier = "TIER_4_LOW"
                # Map page categories to engine categories (rough)
                eng_cat = "PROFESSIONAL_SERVICES"
                if "IT" in cat or "Technology" in cat:
                    eng_cat = "CRITICAL_TECH" if tier == "TIER_1_CRITICAL" else "NON_CRITICAL_TECH"
                elif "Cleaning" in cat or "Security" in cat or "Maintenance" in cat:
                    eng_cat = "FACILITIES"
                elif "Outsourc" in cat:
                    eng_cat = "OUTSOURCED_OPS"
                # Parse last review date
                try:
                    lr_date = _date.fromisoformat(last_review_str) if last_review_str else None
                except (ValueError, TypeError):
                    lr_date = None
                if lr_date is None:
                    review_rows.append({
                        "Vendor": (v.get("name", "") or "")[:25],
                        "Tier": tier, "Category": eng_cat,
                        "Last review": "—",
                        "Days until next review": "—",
                        "Status": "MISSING_DATA",
                    })
                    continue
                vrec = VendorRecord(
                    vendor_id=v.get("id", "—"),
                    category=eng_cat, tier=tier,
                    last_review_date=lr_date)
                rr = VendorRiskEngine.review_due(vrec)
                due_in = rr.get("review_due_in_days")
                overdue = rr.get("is_overdue")
                if overdue:
                    overdue_count += 1
                    status = "OVERDUE"
                elif due_in is not None and due_in <= 30:
                    due_soon_count += 1
                    status = "DUE_SOON"
                else:
                    status = "ON_SCHEDULE"
                review_rows.append({
                    "Vendor": (v.get("name", "") or "")[:25],
                    "Tier": tier, "Category": eng_cat,
                    "Last review": last_review_str,
                    "Days until next review": due_in,
                    "Status": status,
                })

            if overdue_count or due_soon_count:
                st.warning(
                    f"📅 **Review attention required** — "
                    f"{overdue_count} OVERDUE / {due_soon_count} DUE_SOON (within 30d)."
                )
            else:
                st.success("✅ All vendor reviews on schedule.")

            df_review = pd.DataFrame(review_rows)
            # Color code Status
            def _status_clr(v):
                if v == "OVERDUE": return "color:#A32D2D;font-weight:600"
                if v == "DUE_SOON": return "color:#BA7517"
                if v == "MISSING_DATA": return "color:#6B7280"
                return "color:#3B6D11"
            try:
                styled = df_review.style.map(_status_clr, subset=["Status"])
                st.dataframe(styled, use_container_width=True, hide_index=True)
            except Exception:
                # Fallback if pandas styling unavailable
                st.dataframe(df_review, use_container_width=True, hide_index=True)
            audit_log("IFRS_ENGINE_USED", uname,
                       f"VendorRisk #96: Review schedule scanned, "
                       f"overdue={overdue_count}, due_soon={due_soon_count}")

    # ---- Concentration risk ----
    with risk_sub_tabs[2]:
        st.markdown("**Single-Vendor Concentration Risk**")
        st.caption(
            f"Per CBK PG/06, alerts when a single vendor accounts for "
            f"≥{VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT}% of category spend."
        )
        if not vendors:
            st.info("No vendors in register.")
        else:
            cat_options = list(VENDOR_CATEGORIES)
            sel_cat = st.selectbox("Category to analyse", cat_options,
                                     key="conc_cat")
            if st.button("Check concentration", key="conc_btn", type="primary"):
                # Build VendorRecord list for the selected engine category
                # Heuristic mapping page → engine categories
                vrecs = []
                for v in vendors:
                    page_cat = v.get("category", "") or ""
                    spend_m = float(v.get("total_spend_ytd_m", 0) or 0)
                    if spend_m >= 50:
                        tier = "TIER_1_CRITICAL"
                    elif spend_m >= 10:
                        tier = "TIER_2_HIGH"
                    elif spend_m >= 1:
                        tier = "TIER_3_MEDIUM"
                    else:
                        tier = "TIER_4_LOW"
                    if "IT" in page_cat:
                        eng_cat = "CRITICAL_TECH" if tier == "TIER_1_CRITICAL" else "NON_CRITICAL_TECH"
                    elif "Cleaning" in page_cat or "Security" in page_cat or "Maintenance" in page_cat:
                        eng_cat = "FACILITIES"
                    elif "Outsourc" in page_cat:
                        eng_cat = "OUTSOURCED_OPS"
                    else:
                        eng_cat = "PROFESSIONAL_SERVICES"
                    if eng_cat != sel_cat:
                        continue
                    vrecs.append(VendorRecord(
                        vendor_id=v.get("id", ""),
                        category=eng_cat, tier=tier,
                        annual_spend_kes=_D(str(spend_m)) * _D("1000000")))

                if not vrecs:
                    st.info(f"No vendors mapped to category **{sel_cat}**.")
                else:
                    r = VendorRiskEngine.vendor_concentration_check(vrecs, sel_cat)
                    if r.get("computed"):
                        max_v = r.get("max_concentration_vendor_id")
                        max_pct = r.get("max_concentration_pct")
                        alert = r.get("concentration_alert")
                        total = r.get("total_spend_kes")
                        k1, k2, k3 = st.columns(3)
                        k1.metric("Vendors in category",
                                   str(r.get("vendor_count", 0)))
                        k2.metric("Top vendor",
                                   f"{max_v} ({max_pct}%)" if max_v else "—")
                        k3.metric("Total category spend",
                                   f"KES {_D(total)/_D('1000000'):,.2f}M"
                                   if total else "—")
                        if alert:
                            st.error(
                                f"⛔ **Concentration alert** — vendor **{max_v}** "
                                f"accounts for **{max_pct}%** of {sel_cat} spend, "
                                f"exceeding {VENDOR_CONCENTRATION_CRITICAL_THRESHOLD_PCT}% "
                                f"threshold per CBK PG/06."
                            )
                        else:
                            st.success(
                                f"✅ No concentration alert — "
                                f"largest single vendor is {max_pct}% of category."
                            )
                        audit_log("IFRS_ENGINE_USED", uname,
                                   f"VendorRisk #96: Concentration {sel_cat} "
                                   f"max={max_v}@{max_pct}% alert={alert}")
                    else:
                        st.error(f"Could not compute. Reason: {r.get('reason')}")

    # ---- SLA breach severity ----
    with risk_sub_tabs[3]:
        st.markdown("**SLA Breach Severity Classification**")
        st.caption(
            f"Per CBK PG/06 outsourcing oversight: "
            f"CRITICAL ≥{SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS['CRITICAL']}hr · "
            f"HIGH {SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS['HIGH']}–{SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS['CRITICAL']}hr · "
            f"MEDIUM {SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS['MEDIUM']}–{SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS['HIGH']}hr · "
            f"LOW <{SLA_BREACH_DOWNTIME_THRESHOLDS_HOURS['MEDIUM']}hr."
        )
        downtime = st.number_input("Downtime (hours)",
                                     min_value=0.0, value=2.5, step=0.5,
                                     key="sla_downtime",
                                     help="Cumulative service unavailability "
                                          "during the breach window.")
        if st.button("Classify severity", key="sla_btn", type="primary"):
            sev = VendorRiskEngine.sla_breach_severity(_D(str(downtime)))
            if sev is None:
                st.error("Could not classify (downtime missing or negative).")
            else:
                color = {"CRITICAL": "#DC2626", "HIGH": "#F59E0B",
                          "MEDIUM": "#3B82F6", "LOW": "#10B981"}.get(sev, "#6B7280")
                st.markdown(
                    f"<div style='padding:18px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"BREACH SEVERITY</div>"
                    f"<div style='font-size:32px;font-weight:800;color:{color};margin-top:4px'>"
                    f"{sev}</div>"
                    f"<div style='font-size:13px;margin-top:6px'>"
                    f"Downtime: {downtime}hr</div></div>",
                    unsafe_allow_html=True)
                if sev in ("CRITICAL", "HIGH"):
                    st.warning(
                        "ℹ Severity at this level typically triggers contractual "
                        "service credits and may require escalation to the Head of "
                        "Operations or Chief Risk Officer per the vendor's BCP plan.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"VendorRisk #96: SLA severity {downtime}hr → {sev}")


with tabs[4]:
    # ── Procurement Workflow Reference (Standard #98, integrated v5.74) ──
    # Cross-reference to the v5.71 IFRS Engines Studio. This tab provides
    # vendor-context shortcuts to procurement decisions for the selected vendor.
    from utils.procurement_workflow import (
        ProcurementWorkflowEngine,
        APPROVAL_TIERS, BUYER_LIMIT_KES, MANAGER_LIMIT_KES,
        DIRECTOR_LIMIT_KES, MD_LIMIT_KES, PROCUREMENT_METHODS,
        QUOTATIONS_REQUIRED, THREE_WAY_MATCH_TOLERANCE_PCT,
    )
    from decimal import Decimal as _D2

    st.markdown(
        "**Standard #98 — Procurement Workflow Reference** "
        "(approval matrix + procurement method + 3-way match)."
    )
    st.caption(
        f"Approval tiers: BUYER ≤ KES {int(BUYER_LIMIT_KES):,} · "
        f"MANAGER ≤ {int(MANAGER_LIMIT_KES):,} · "
        f"DIRECTOR ≤ {int(DIRECTOR_LIMIT_KES):,} · "
        f"MD ≤ {int(MD_LIMIT_KES):,} · BOARD above. "
        f"For full procurement engine, see *IFRS Engines Studio → Procurement Workflow*."
    )

    proc_sub_tabs = st.tabs([
        "🎯 Vendor Procurement Quick-Check",
        "✅ 3-Way Match Pre-Pay",
    ])

    # ---- Vendor procurement quick-check ----
    with proc_sub_tabs[0]:
        st.markdown(
            "**For a vendor + amount, determine approval tier + procurement method "
            "+ quotations required in one shot.**")
        if vendors:
            vendor_options = ["(select vendor)"] + [
                f"{v['id']} — {v['name'][:30]}" for v in vendors[:50]]
            sel = st.selectbox("Vendor", vendor_options, key="vp_vendor")
            sel_v = None
            if sel != "(select vendor)":
                vid = sel.split(" — ")[0]
                sel_v = next((v for v in vendors if v.get("id") == vid), None)
        else:
            sel = "(select vendor)"
            sel_v = None
            st.info("No vendors in register.")

        amt = st.number_input("Procurement amount (KES)",
                                min_value=0.0, value=500_000.0, step=10_000.0,
                                key="vp_amount")

        if st.button("Determine workflow", key="vp_btn", type="primary"):
            # Approval tier
            r1 = ProcurementWorkflowEngine.approval_authority(_D2(str(amt)))
            r2 = ProcurementWorkflowEngine.procurement_method(_D2(str(amt)))
            if r1.get("computed") and r2.get("computed"):
                tier = r1["tier"]
                method = r2["method"]
                quotes = r2.get("quotations_required", "—")
                tier_color = {"BUYER":"#10B981","MANAGER":"#3B82F6","DIRECTOR":"#8B5CF6",
                               "MD":"#F59E0B","BOARD":"#DC2626"}.get(tier, "#6B7280")
                st.markdown(
                    f"<div style='padding:18px;background:{tier_color}22;"
                    f"border-left:6px solid {tier_color};border-radius:12px'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                    f"<div><div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"APPROVAL TIER</div>"
                    f"<div style='font-size:28px;font-weight:800;color:{tier_color}'>"
                    f"{tier}</div></div>"
                    f"<div style='text-align:right'><div style='font-size:11px;"
                    f"letter-spacing:1.5px;opacity:0.7'>METHOD</div>"
                    f"<div style='font-size:18px;font-weight:700'>{method}</div>"
                    f"<div style='font-size:13px;margin-top:4px'>"
                    f"{quotes} quotations required</div></div></div></div>",
                    unsafe_allow_html=True)

                # Vendor-specific guardrails
                if sel_v:
                    issues = []
                    if not sel_v.get("tax_compliance"):
                        issues.append(
                            "🔴 Vendor is **KRA non-compliant** — payments must be withheld.")
                    if not sel_v.get("insurance_valid"):
                        issues.append(
                            "🟡 Vendor lacks **valid insurance** — risk exposure.")
                    if sel_v.get("status") == "Suspended":
                        issues.append(
                            "🔴 Vendor is **SUSPENDED** — POs cannot be raised.")
                    if issues:
                        st.error("**Vendor compliance issues:**")
                        for i in issues:
                            st.write(f"- {i}")
                    else:
                        st.success("✅ Vendor passes compliance pre-checks.")

                audit_log("IFRS_ENGINE_USED", uname,
                           f"Procurement #98: Workflow check vendor={sel} amt={amt} "
                           f"tier={tier} method={method}")
            else:
                st.error("Could not compute.")

    # ---- 3-way match pre-pay ----
    with proc_sub_tabs[1]:
        st.markdown(
            f"**3-Way Match Pre-Pay Validation** "
            f"(PO ↔ GRN ↔ Invoice; tolerance ±{THREE_WAY_MATCH_TOLERANCE_PCT}%)."
        )
        st.caption(
            "Run before processing payment. Mismatches outside ±2% tolerance "
            "block payment per #98 procurement engine."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            po_amt = st.number_input("PO amount", min_value=0.0,
                                       value=100_000.0, step=1_000.0,
                                       key="vp_3w_po")
        with c2:
            grn_amt = st.number_input("GRN amount", min_value=0.0,
                                        value=102_000.0, step=1_000.0,
                                        key="vp_3w_grn")
        with c3:
            inv_amt = st.number_input("Invoice amount", min_value=0.0,
                                        value=100_000.0, step=1_000.0,
                                        key="vp_3w_inv")
        if st.button("Run 3-way match", key="vp_3w_btn", type="primary"):
            r = ProcurementWorkflowEngine.three_way_match(
                _D2(str(po_amt)), _D2(str(grn_amt)), _D2(str(inv_amt)))
            if r.get("computed"):
                matched = r.get("matched")
                eligible = r.get("eligible_for_payment")
                if matched and eligible:
                    color = "#10B981"
                    verdict = "✅ MATCHED — payment eligible"
                else:
                    color = "#DC2626"
                    verdict = "❌ MISMATCH — payment BLOCKED"
                st.markdown(
                    f"<div style='padding:18px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px'>"
                    f"<div style='font-size:18px;font-weight:700;color:{color}'>"
                    f"{verdict}</div></div>", unsafe_allow_html=True)
                k1, k2 = st.columns(2)
                k1.metric("GRN deviation vs PO",
                           f"{_D2(r['grn_deviation_pct']):.2f}%")
                k2.metric("Invoice deviation vs PO",
                           f"{_D2(r['invoice_deviation_pct']):.2f}%")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Procurement #98: 3WM PO={po_amt}/GRN={grn_amt}/"
                           f"INV={inv_amt} matched={matched}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason')}")


with tabs[5]:
    if is_proc or is_admin:
        CATS = ["IT Equipment","Office Supplies","Cleaning & Sanitation","Furniture & Fittings",
                "Security Services","Utilities","Professional Services","Travel & Accommodation",
                "Printing & Stationery","Vehicle Fleet","Maintenance & Repairs","Other"]
        r1,r2 = st.columns(2)
        _vname = st.text_input("Vendor name *",key="vnd_name")
        _vcat  = r1.selectbox("Category",CATS,key="vnd_vcat")
        _vkra  = st.text_input("KRA PIN *",key="vnd_kra")
        _vreg  = r2.text_input("Business registration no. *",key="vnd_reg")
        _vcp   = st.text_input("Contact person",key="vnd_cp")
        _vph   = r1.text_input("Phone",key="vnd_ph")
        _vem   = r2.text_input("Email",key="vnd_em")
        _vkra_ok = st.checkbox("KRA compliance verified",key="vnd_kra_ok")
        _vins_ok = st.checkbox("Insurance verified",key="vnd_ins_ok")
        if st.button("✅ Onboard vendor",key="vnd_add",type="primary"):
            if _vname.strip() and _vkra.strip():
                all_v = json.loads((DATA/"vendor_register.json").read_text())
                all_v.append({
                    "id":f"VND{len(all_v)+1:04d}","name":_vname.strip(),"category":_vcat,
                    "kra_pin":_vkra.strip(),"registration_no":_vreg.strip(),"contact_person":_vcp,
                    "phone":_vph,"email":_vem,"address":"","status":"Active",
                    "onboarding_date":str(today),"last_reviewed":str(today),
                    "next_review":"","tax_compliance":_vkra_ok,"insurance_valid":_vins_ok,
                    "bank_details":{},"rating":3.0,"total_spend_ytd_m":0,"open_pos":0,"notes":""
                })
                (DATA/"vendor_register.json").write_text(json.dumps(all_v,indent=2))
                audit_log("VENDOR_ONBOARDED",uname,_vname.strip())
                _bsc_trigger(uname, "K052")
                st.cache_data.clear(); st.success(f"✅ {_vname} onboarded"); st.rerun()
            else: st.error("Vendor name and KRA PIN required.")
    else: st.info("Vendor onboarding available to Procurement team.")
