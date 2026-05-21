"""pages/29_revenue_assurance.py — Revenue Assurance Module.
Tracks fee waivers, income leakages, and CBS-to-GL income variances.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date, timedelta
from pages._shared import load_shared_state
from utils.core_audit import audit_log, requires_dual_approval, submit_for_approval
from pages._access import require_access

require_access("finance.revenue_assurance")

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update — called after every save action."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass
DATA = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
sc = str(ud.get("staff_code","") or ""); role = ud.get("role",""); name = ud.get("full_name","")
is_admin   = ud.get("is_admin",False)
is_finance = any(x in role for x in ("Chief Financial","Financial Controller","Finance Manager","CFO","Tax"))
is_mgr     = any(x in role for x in ("Manager","Director","Chief","Head"))

@st.cache_data(ttl=60, show_spinner=False)
def _load_ra():
    p = DATA / "revenue_assurance.json"
    return a2z_db.load_json(p) if p.exists() else []

records = _load_ra()

st.markdown("<div style='padding:16px 0 8px'><span style='font-size:22px;font-weight:800'>💰 Revenue Assurance</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Fee waivers · Income leakages · Recovery tracking</span></div>", unsafe_allow_html=True)

f1,f2,f3,f4 = st.columns(4)
sel_type   = f1.selectbox("Type",   ["All","Waiver","Leakage"], key="ra_type")
sel_status = f2.selectbox("Status", ["All","Open","Pending Approval","Approved","Investigated","Recovered","Written Off","Rejected","Escalated"], key="ra_status")
sel_period = f3.selectbox("Period", ["All"]+sorted(set(r["period"] for r in records),reverse=True)[:6], key="ra_period")
sel_branch = f4.selectbox("Branch", ["All"]+sorted(set(r["branch"] for r in records)), key="ra_branch")

visible = [r for r in records
           if (sel_type=="All" or r["type"]==sel_type)
           and (sel_status=="All" or r["status"]==sel_status)
           and (sel_period=="All" or r["period"]==sel_period)
           and (sel_branch=="All" or r["branch"]==sel_branch)]

waivers  = [r for r in records if r["type"]=="Waiver"]
leakages = [r for r in records if r["type"]=="Leakage"]
recovered= [r for r in leakages if r["status"]=="Recovered"]
pending  = [r for r in waivers  if r["status"]=="Pending Approval"]

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Total Waivers",    f"{len(waivers)}",  f"KES {sum(r['amount'] for r in waivers)/1e6:.1f}M")
c2.metric("Pending Approval", f"{len(pending)}",  f"KES {sum(r['amount'] for r in pending)/1e6:.1f}M")
c3.metric("Income Leakages",  f"{len(leakages)}", f"KES {sum(r['amount'] for r in leakages)/1e6:.1f}M")
c4.metric("Recovered",        f"{len(recovered)}",f"KES {sum(r['amount'] for r in recovered)/1e6:.1f}M")
c5.metric("Recovery Rate",    f"{len(recovered)/max(len(leakages),1)*100:.0f}%")

if pending and (is_finance or is_admin or is_mgr):
    st.warning(f"\u26a0\ufe0f {len(pending)} waiver(s) pending approval — KES {sum(r['amount'] for r in pending)/1e6:.1f}M")

st.markdown("---")
tabs = st.tabs(["📋 All Records","🔴 Leakages","⏳ Pending Waivers","📊 Analytics","➕ Log Record","🤖 Arc Engines"])

with tabs[0]:
    st.markdown(f"**{len(visible)} records** — KES {sum(r['amount'] for r in visible)/1e6:.1f}M")
    rows=[{"ID":r["id"],"Type":r["type"],"Fee Type":r["fee_type"][:30],"Branch":r["branch"][:20],
           "Amount":f"{r['amount']:,.0f}","Period":r["period"],"Status":r["status"],
           "Reason":r.get("reason","")[:30],"Raised By":r.get("raised_by","")[:20]}
          for r in sorted(visible,key=lambda x:x["date_raised"],reverse=True)]
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:    st.info("No records match the current filters.")

with tabs[1]:
    open_l=[r for r in visible if r["type"]=="Leakage" and r["status"] not in ("Recovered","Written Off")]
    if not open_l: st.success("✅ No open leakages.")
    else:
        st.error(f"🔴 {len(open_l)} open leakages — KES {sum(r['amount'] for r in open_l)/1e6:.1f}M unrecovered")
        for r in sorted(open_l,key=lambda x:-x["amount"])[:20]:
            with st.expander(f"🔴 {r['fee_type']} · {r['branch']} · KES {r['amount']:,.0f} · {r['status']}"):
                ec1,ec2,ec3=st.columns(3)
                ec1.markdown(f"**Type:** {r['reason']}"); ec2.markdown(f"**Client:** {r['client_name']}"); ec3.markdown(f"**Date:** {r['date_raised']}")
                if (is_finance or is_admin) and r["status"]=="Open":
                    a1,a2=st.columns(2)
                    if a1.button("🔍 Investigate",key=f"inv_{r['id']}"):
                        recs=json.loads((DATA/"revenue_assurance.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Under Investigation"
                        (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                        audit_log("RA_UPDATE", name, "Revenue assurance updated")
                        _bsc_trigger(uname, "K003")
                        st.cache_data.clear(); st.success("Marked Under Investigation"); st.rerun()
                    if a2.button("✅ Mark Recovered",key=f"rec_{r['id']}"):
                        recs=json.loads((DATA/"revenue_assurance.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Recovered"; rec["recovered"]=True; rec["recovered_amount"]=rec["amount"]
                        (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                        audit_log("RA_UPDATE", name, "Revenue assurance updated")
                        _bsc_trigger(uname, "K003")
                        st.cache_data.clear(); st.success("✅ Recovered"); st.rerun()

with tabs[2]:
    pend_w=[r for r in visible if r["type"]=="Waiver" and r["status"]=="Pending Approval"]
    
    # ── Batch approval at month end ──────────────────────────────
    _today_d = date.today()
    _month_end = (_today_d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    _days_left = (_month_end - _today_d).days
    if pend_w and (is_mgr or is_admin or is_finance) and _days_left <= 5:
        st.warning(f"⚠️ **Month-end: {_days_left}d remaining** — {len(pend_w)} waivers pending")
        if st.button(f"✅ Batch Approve ALL {len(pend_w)} pending waivers (month-end close)", 
                     key="ra_batch_approve", type="primary"):
            recs=json.loads((DATA/"revenue_assurance.json").read_text())
            n=0
            for rec in recs:
                if rec["type"]=="Waiver" and rec["status"]=="Pending Approval":
                    rec["status"]="Approved"; rec["authorised_by"]=name; n+=1
            (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
            audit_log("RA_BATCH_APPROVE",uname,f"Month-end batch approve {n} waivers")
            _bsc_trigger(uname, "K003")
            st.cache_data.clear(); st.success(f"✅ {n} waivers approved (month-end batch)"); st.rerun()
    if not pend_w: st.success("✅ No waivers pending approval.")
    else:
        st.markdown(f"**{len(pend_w)} waivers** — KES {sum(r['amount'] for r in pend_w)/1e6:.1f}M")
        for r in sorted(pend_w,key=lambda x:-x["amount"]):
            with st.expander(f"⏳ {r['fee_type']} · {r['branch']} · KES {r['amount']:,.0f}"):
                wc1,wc2=st.columns(2)
                wc1.markdown(f"**Reason:** {r['reason']}  \n**Client:** {r['client_name']}")
                wc2.markdown(f"**Raised by:** {r.get('raised_by','')}  \n**Date:** {r['date_raised']}")
                if is_mgr or is_admin or is_finance:
                    wa1,wa2=st.columns(2)
                    if wa1.button("✅ Approve",key=f"wapp_{r['id']}",type="primary"):
                        recs=json.loads((DATA/"revenue_assurance.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Approved"; rec["authorised_by"]=name
                        (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                        audit_log("RA_UPDATE", name, "Revenue assurance updated")
                        _bsc_trigger(uname, "K003")
                        st.cache_data.clear(); st.success("✅ Approved"); st.rerun()
                    if wa2.button("❌ Reject",key=f"wrej_{r['id']}"):
                        recs=json.loads((DATA/"revenue_assurance.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Rejected"
                        (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                        audit_log("RA_UPDATE", name, "Revenue assurance updated")
                        _bsc_trigger(uname, "K003")
                        st.cache_data.clear(); st.success("Rejected"); st.rerun()

with tabs[3]:
    st.markdown("**By branch:**")
    bw=defaultdict(lambda:{"w":0,"l":0,"wv":0,"lv":0})
    for r in records:
        b=r["branch"]
        if r["type"]=="Waiver": bw[b]["w"]+=1; bw[b]["wv"]+=r["amount"]
        else:                   bw[b]["l"]+=1; bw[b]["lv"]+=r["amount"]
    df_b=pd.DataFrame([{"Branch":b,"Waivers":v["w"],"Leakages":v["l"],
                         "Waiver (M)":round(v["wv"]/1e6,1),"Leakage (M)":round(v["lv"]/1e6,1),
                         "Total Risk (M)":round((v["wv"]+v["lv"])/1e6,1)} for b,v in bw.items()])
    st.dataframe(df_b.sort_values("Total Risk (M)",ascending=False),use_container_width=True,hide_index=True)
    st.markdown("**By fee type (top 10):**")
    fv=defaultdict(float)
    for r in records: fv[r["fee_type"]]+=r["amount"]
    df_f=pd.DataFrame([{"Fee Type":k,"Total (KES M)":round(v/1e6,1)} for k,v in sorted(fv.items(),key=lambda x:-x[1])[:10]])
    st.dataframe(df_f,use_container_width=True,hide_index=True)

with tabs[4]:
    st.markdown("**Log a new waiver or leakage:**")
    with st.form("log_ra"):
        l1,l2=st.columns(2)
        l_type=l1.selectbox("Type",["Waiver","Leakage"],key="log_type")
        l_fee =l2.selectbox("Fee Type",["Account Maintenance Fee","Ledger Fee","Loan Processing Fee","Card Maintenance Fee","Wire Transfer Fee","RTGS Fee","EFT Fee","Bancassurance Commission","Trade Finance Fee","Other"],key="log_fee")
        l3,l4=st.columns(2)
        l_amount=l3.number_input("Amount (KES)",min_value=0.0,step=1000.0,key="log_amt")
        l_branch=l4.selectbox("Branch",sorted(set(r["branch"] for r in records)),key="log_branch")
        l_client=st.text_input("Client name",key="log_client")
        l_reason=st.text_area("Reason",height=68,key="log_reason")
        if st.form_submit_button("📥 Log record",type="primary"):
            if not l_client.strip(): st.error("Enter client name")
            elif l_amount<=0:        st.error("Amount must be > 0")
            else:
                recs=json.loads((DATA/"revenue_assurance.json").read_text())
                recs.append({"id":f"RA{str(len(recs)+1).zfill(5)}","type":l_type,"fee_type":l_fee,
                    "branch":l_branch,"amount":float(l_amount),"currency":"KES",
                    "date_raised":str(today),"period":str(today)[:7],"reason":l_reason,
                    "client_name":l_client.strip(),"client_cif":"","raised_by":name,"raised_code":sc,
                    "status":"Pending Approval" if l_type=="Waiver" else "Open",
                    "recovered":False,"recovered_amount":0,"authorised_by":"","notes":"","last_updated":str(today)})
                (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                audit_log("RA_UPDATE", name, "Revenue assurance updated")
                _bsc_trigger(uname, "K003")
                st.cache_data.clear(); st.success("✅ Logged"); st.rerun()


# ──────────────────────────────────────────────────────────────────────
# Section 5: 🤖 Arc Engines (absorbed from
# 95_revenue_assurance_cockpit.py in v10.210 per the architectural
# reorganization sub-campaign. 8 engines (ENH-301..308) presented as
# 7 nested sub-tabs spanning the revenue assurance arc.
#
# v10.210 also re-homed this page from operations to finance department
# (along with 9_sbu.py which moved from sales_customer to finance).
# Revenue assurance is conceptually a Finance function: detecting
# revenue leakage, verifying billing accuracy, reconciling
# partner/supplier shares — all CFO-owned activities. SBU profitability
# similarly: P&L by business unit is Finance work, not Sales.
# Operations and sales_customer remain secondary-visible for the staff
# who consume these dashboards from those teams.
#
# All engines diagnostic — no auto-recovery; outputs feed the leakage
# log, waiver workflow, and CBK regulatory submissions. Mirrors
# v10.202..v10.209 absorption patterns.
# ──────────────────────────────────────────────────────────────────────
with tabs[5]:
    from datetime import datetime as _dt_ra, timezone as _tz_ra

    try:
        from utils.revenue_validation import RevenueValidationEngine
        from utils.revenue_anomaly_patterns import (
            RevenueAnomalyPatternEngine)
        from utils.revenue_orchestrator import RevenueOrchestrator
        from utils.partner_supplier_recon import (
            PartnerSupplierReconciliationEngine)
        from utils.revenue_dashboard_metrics import (
            RevenueDashboardMetrics)
        from utils.continuous_billing_verification import (
            ContinuousBillingVerificationEngine)
        from utils.commission_assurance import CommissionAssuranceEngine
        from utils.regulatory_revenue_reporting import (
            RegulatoryRevenueReportingEngine)
        _ARC_RA_AVAILABLE = True
    except ImportError as _ie:
        st.error(f"Revenue Assurance arc engines unavailable: {_ie}")
        _ARC_RA_AVAILABLE = False

    if _ARC_RA_AVAILABLE:
        st.caption(
            "v10.210 absorbed from 95_revenue_assurance_cockpit.py — "
            "8 engines spanning revenue validation, anomaly detection, "
            "orchestration, partner/supplier reconciliation, dashboard "
            "metrics, continuous billing verification, commission "
            "assurance, and regulatory revenue reporting. All engines "
            "diagnostic — outputs feed the leakage log, waiver workflow, "
            "and CBK regulatory submissions.")

        
        arc_tabs = st.tabs([
            "📋 Validation",
            "🔍 Patterns",
            "🧭 Orchestrator + 📊 Metrics",
            "🤝 Partner/Supplier",
            "✅ Pre-issuance",
            "💼 Commission",
            "🏛️ Regulatory",
        ])

        with arc_tabs[0]:
            st.subheader("Revenue Validation (ENH-241)")
            st.caption(
                "Schema · Completeness · Cross-Source recon (CBS↔GL) · "
                "Statistical anomaly")
            seed_records = [
                RevenueRecord(
                    record_id="R-001", source_system="CBS",
                    posting_date=date(2026, 4, 15),
                    amount_kes=Decimal("100000"),
                    revenue_category="INTEREST_INCOME",
                    branch_code="NRB-01"),
                RevenueRecord(
                    record_id="R-002", source_system="CBS",
                    posting_date=date(2026, 4, 16),
                    amount_kes=Decimal("50000"),
                    revenue_category="FEE_INCOME",
                    branch_code="NRB-01"),
            ]
            if st.button("Run validation engine", key="rv_run"):
                eng = RevenueValidationEngine()
                report = eng.validate_all(records=seed_records)
                audit_log(
                    "REVENUE_ENGINE_USED", uname,
                    {"engine": "revenue_validation",
                     "findings": len(report.findings)})
                st.success(
                    f"Validation complete — {len(report.findings)} "
                    "findings")
                with st.expander("Severity breakdown", expanded=True):
                    st.json(report.by_severity)
                with st.expander("Category breakdown"):
                    st.json(report.by_category)
                with st.expander("Findings (Rule 1 — full provenance)"):
                    for f in report.findings:
                        st.write(
                            f"**{f.severity.value}** · "
                            f"{f.category.value} — {f.description}")

        with arc_tabs[1]:
            st.subheader("Revenue Anomaly Patterns (ENH-242)")
            st.caption(
                "6 deterministic detectors over POSTED records; ML hook "
                "injectable per Rule 6 (ml_disabled flag surfaced explicitly "
                "when absent)")
            if st.button("Run pattern detection demo", key="ra_run"):
                eng = RevenueAnomalyPatternEngine()
                # Demo: 2 duplicate billings — same customer, same amount,
                # within 3 days
                records = [
                    RevenueRecord(
                        record_id="R-A", source_system="CBS",
                        posting_date=date(2026, 4, 10),
                        amount_kes=Decimal("5000"),
                        revenue_category="FEE_INCOME",
                        branch_code="NRB-01",
                        customer_id="C-001"),
                    RevenueRecord(
                        record_id="R-B", source_system="CBS",
                        posting_date=date(2026, 4, 11),
                        amount_kes=Decimal("5000"),
                        revenue_category="FEE_INCOME",
                        branch_code="NRB-01",
                        customer_id="C-001"),
                ]
                findings = eng.detect_duplicate_billing(records)
                audit_log(
                    "REVENUE_ENGINE_USED", uname,
                    {"engine": "revenue_anomaly_patterns",
                     "findings": len(findings),
                     "detector": "duplicate_billing"})
                if findings:
                    st.warning(f"{len(findings)} duplicate billing finding(s)")
                    for f in findings:
                        st.write(
                            f"- **{f.severity.value}** · {f.pattern_id.value} "
                            f"· {f.description}")
                        st.caption(
                            f"Records: {f.record_ids} · "
                            f"Framework: {f.framework_refs[0]}")
                else:
                    st.info("No duplicates in demo data")
                st.caption(
                    "ml_disabled=True surfaced — this demo runs deterministic "
                    "detectors only; production injects ML hook via "
                    "engine.attach_ml_anomaly_detector(...)")

        with arc_tabs[2]:
            st.subheader("Revenue Agentic Orchestrator (ENH-243)")
            st.caption(
                "Stateless — caller maintains state externally. "
                "Routes findings to 6 InvestigatorTeam values via "
                "(severity, family) lookup.")
            if st.button("Demo: route a sample finding", key="ro_run"):
                from utils.revenue_orchestrator import (
                    OrchestratorConfig, TriageRule, InvestigatorTeam)
                from utils.revenue_anomaly_patterns import PatternId
                # Minimal triage rule set keyed by family + severity. A real
                # deployment configures these per the bank's investigation
                # team structure. The demo uses sensible defaults.
                rules = (
                    TriageRule(
                        family_or_category="BILLING_ERROR",
                        severity=ValidationSeverity.HIGH,
                        team=InvestigatorTeam.REVENUE_RECOVERY,
                        sla_days=5),
                    TriageRule(
                        family_or_category="LEAKAGE",
                        severity=ValidationSeverity.HIGH,
                        team=InvestigatorTeam.REVENUE_RECOVERY,
                        sla_days=5),
                    TriageRule(
                        family_or_category="COMMISSION_MISCALC",
                        severity=ValidationSeverity.MEDIUM,
                        team=InvestigatorTeam.OPERATIONS,
                        sla_days=10),
                )
                cfg = OrchestratorConfig(triage_rules=rules)
                eng = RevenueOrchestrator(config=cfg)
                finding = PatternFinding(
                    finding_id="F-DEMO-001",
                    pattern_id=PatternId.EXPIRED_CONTRACT_BILLING,
                    family=PatternFamily.BILLING_ERROR,
                    severity=ValidationSeverity.HIGH,
                    record_ids=("R-X",),
                    description="Demo high-severity billing exception",
                    evidence="Contract expired 2025-10-01; charges accrued",
                    confidence=Decimal("0.85"),
                    ml_score=None,
                    framework_refs=("ENH-242",),
                    notes="")
                result = eng.orchestrate(
                    findings=[finding],
                    raised_dates={"F-DEMO-001": date(2026, 4, 20)},
                    as_of=date(2026, 4, 25),
                    monetary_impacts={"F-DEMO-001": Decimal("500000")})
                audit_log(
                    "REVENUE_ENGINE_USED", uname,
                    f"engine=revenue_orchestrator items={len(result.work_items)}")
                wi = result.work_items[0]
                st.metric("Priority score", f"{float(wi.priority_score):.1f}")
                st.metric("Routed to", wi.assigned_team.value)
                st.metric("Past SLA?", "Yes" if wi.past_sla else "No")
                with st.expander("priority_components (Rule 1)"):
                    st.json({k: str(v)
                             for k, v in wi.priority_components.items()})

            st.divider()
            st.subheader("Revenue Dashboard Metrics (ENH-245)")
            st.caption(
                "Read-only aggregation. 6 metric families consumed by this "
                "cockpit — leakage trend, top categories (count + impact), "
                "recovery, team activity, cycle times, summary.")
            if st.button("Demo: compute metrics", key="rdm_run"):
                from utils.revenue_orchestrator import WorkItem
                eng = RevenueDashboardMetrics()
                items = [
                    WorkItem(
                        work_item_id="W1",
                        source_finding_id="F1",
                        source_finding_type=FindingType.PATTERN,
                        severity=ValidationSeverity.HIGH,
                        family_or_category="BILLING",
                        description="demo",
                        affected_record_ids=("R1",),
                        raised_date=date(2026, 4, 1),
                        age_days=15, sla_deadline=date(2026, 4, 8),
                        past_sla=True,
                        assigned_team=InvestigatorTeam.BILLING_OPS,
                        priority_score=Decimal("75"),
                        priority_components={},
                        monetary_impact_kes=Decimal("50000"),
                        current_state=WorkItemState.IN_PROGRESS,
                        framework_refs=("ENH-243",)),
                ]
                window = DashboardWindow(
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 12, 31))
                metrics = eng.compute_all(items, window, ())
                audit_log(
                    "REVENUE_ENGINE_USED", uname,
                    {"engine": "revenue_dashboard_metrics",
                     "items": metrics.total_work_items})
                st.metric("Total work items", metrics.total_work_items)
                st.metric("Recovery KES", str(metrics.recovery.recovered_kes))
                st.metric(
                    "Open count", metrics.recovery.open_count)
                with st.expander("Team activity"):
                    for t in metrics.team_activities:
                        st.write(
                            f"**{t.team.value}** — total {t.total_count}, "
                            f"past_sla {t.past_sla_count}")

        with arc_tabs[3]:
            st.subheader("Partner & Supplier Reconciliation (ENH-244)")
            st.caption(
                "Multi-party recon — partner share validation + supplier "
                "3-way match (PO → GRN → Invoice → Payment)")
            if st.button("Demo: partner share recon", key="ps_run"):
                eng = PartnerSupplierReconciliationEngine()
                agreement = PartnerAgreement(
                    agreement_id="DEMO-AGT", partner_id="MTN",
                    revenue_category="COMMISSION_INCOME",
                    share_pct=Decimal("0.30"),
                    effective_from=date(2026, 1, 1),
                    effective_to=date(2026, 12, 31))
                revenues = [
                    PartnerRevenueRecord(
                        record_id="r1", partner_id="MTN",
                        agreement_id="DEMO-AGT",
                        revenue_category="COMMISSION_INCOME",
                        gross_revenue_kes=Decimal("3000000"),
                        posting_date=date(2026, 4, 10)),
                ]
                settlements = [
                    PartnerSettlement(
                        settlement_id="ST-001", partner_id="MTN",
                        agreement_id="DEMO-AGT", period="2026-04",
                        settled_kes=Decimal("800000"),
                        settlement_date=date(2026, 5, 5)),
                ]
                findings = eng.validate_partner_share(
                    (agreement,), revenues, settlements)
                audit_log(
                    "REVENUE_ENGINE_USED", uname,
                    {"engine": "partner_supplier_recon",
                     "findings": len(findings)})
                if findings:
                    f = findings[0]
                    st.error(
                        f"**{f.discrepancy_type.value}** — "
                        f"{f.party_id} variance KES "
                        f"{f.variance_kes:,}")
                    st.caption(f"Expected: {f.expected}")
                    st.caption(f"Observed: {f.observed}")

        with arc_tabs[4]:
            st.subheader("Continuous Billing Verification (ENH-246)")
            st.caption(
                "PRE-issuance verification (vs ENH-242 which screens POSTED "
                "records). 5 checks → 3 Verdicts (PASS / HOLD / REJECT). "
                "Engine recommends; caller's billing pipeline decides.")
            if st.button("Demo: verify a draft", key="cbv_run"):
                eng = ContinuousBillingVerificationEngine()
                contract = ContractRate(
                    contract_id="DEMO-C", customer_id="cust-A",
                    product_code="LOAN", floor_rate_pct=Decimal("3.0"),
                    ceiling_rate_pct=Decimal("8.0"),
                    effective_from=date(2026, 1, 1),
                    effective_to=date(2026, 12, 31))
                # Below-floor rate → HOLD
                draft = BillingDraft(
                    draft_id="D-DEMO", customer_id="cust-A",
                    product_code="LOAN", contract_id="DEMO-C",
                    proposed_amount_kes=Decimal("100000"),
                    draft_date=date(2026, 4, 15),
                    applied_rate_pct=Decimal("2.5"))
                result = eng.verify(draft, contracts=(contract,))
                audit_log(
                    "REVENUE_ENGINE_USED", uname,
                    {"engine": "continuous_billing_verification",
                     "verdict": result.verdict.value})
                verdict_colour = {
                    Verdict.PASS: "✅", Verdict.HOLD_PENDING_REVIEW: "⚠️",
                    Verdict.REJECT_RECOMMENDED: "🚫",
                }
                st.metric(
                    "Verdict",
                    f"{verdict_colour[result.verdict]} "
                    f"{result.verdict.value}")
                st.write(
                    f"FAIL: {result.fail_count} · WARN: {result.warn_count} "
                    f"· SKIPPED: {result.skipped_count}")
                with st.expander("All 5 check results (Rule 1)"):
                    for r in result.check_results:
                        icon = {
                            CheckStatus.PASS: "✅",
                            CheckStatus.WARN: "⚠️",
                            CheckStatus.FAIL: "🚫",
                            CheckStatus.SKIPPED: "⏭️",
                        }[r.status]
                        st.write(
                            f"{icon} **{r.check_name.value}** ({r.status.value}) "
                            f"— {r.description}")

        with arc_tabs[5]:
            st.subheader("Commission & Incentive Assurance (ENH-247)")
            st.caption(
                "Plan-based recomputation. Closes the loop with ENH-242 — "
                "where ENH-242 took expected as input, ENH-247 COMPUTES it "
                "from a tiered IncentivePlan.")
            if st.button("Demo: tier walk", key="cma_run"):
                eng = CommissionAssuranceEngine()
                plan = IncentivePlan(
                    plan_id="DEMO-PLAN", rm_role="RM-Tier-1",
                    tiers=(
                        CommissionTier(
                            tier_min_kes=Decimal("0"),
                            tier_max_kes=Decimal("100000"),
                            rate_pct=Decimal("0.02")),
                        CommissionTier(
                            tier_min_kes=Decimal("100000"),
                            tier_max_kes=Decimal("500000"),
                            rate_pct=Decimal("0.03")),
                        CommissionTier(
                            tier_min_kes=Decimal("500000"),
                            tier_max_kes=None,
                            rate_pct=Decimal("0.05")),
                    ),
                    basis=TierBasis.MARGINAL)
                calc = eng.compute_expected_commission(
                    plan, "rm-DEMO", "2026-04", Decimal("1000000"))
                audit_log(
                    "REVENUE_ENGINE_USED", uname,
                    {"engine": "commission_assurance",
                     "rm": "rm-DEMO",
                     "expected": str(calc.expected_commission_kes)})
                st.metric(
                    "Expected commission KES",
                    f"{calc.expected_commission_kes:,}")
                st.caption(
                    f"Underlying revenue: KES "
                    f"{calc.underlying_revenue_kes:,} · "
                    f"Basis: {calc.basis.value}")
                with st.expander(
                        "Per-tier contribution breakdown (Rule 1)",
                        expanded=True):
                    for c in calc.contributions:
                        top = (
                            str(c.tier_max_kes)
                            if c.tier_max_kes is not None else "∞")
                        st.write(
                            f"**[{c.tier_min_kes:,} → {top}]** @ "
                            f"{c.rate_pct * 100:.1f}% · "
                            f"amount in tier: KES {c.amount_in_tier_kes:,} "
                            f"· contribution: KES {c.contribution_kes:,}")

        with arc_tabs[6]:
            st.subheader("Regulatory Revenue Reporting (ENH-248)")
            st.caption(
                "Engine produces ReportPackage data; serialization (XBRL/"
                "XML/CSV) and submission rails (CBK BSD portal, KRA iTax) "
                "are caller's workflow.")
            if st.button("Demo: generate CBK Q1 report", key="orr_run"):
                eng = RegulatoryRevenueReportingEngine()
                template = ReportTemplate(
                    template_id="DEMO-CBK-Q1",
                    regulator=Regulator.CBK,
                    period_label="2026-Q1",
                    period_start=date(2026, 1, 1),
                    period_end=date(2026, 3, 31),
                    line_specs=(
                        ReportLineSpec(
                            line_code="L-INT", line_name="Interest income",
                            revenue_categories=frozenset(
                                {"INTEREST_INCOME"}),
                            required=True),
                        ReportLineSpec(
                            line_code="L-FEE", line_name="Fee income",
                            revenue_categories=frozenset(
                                {"FEE_INCOME", "COMMISSION_INCOME"}),
                            required=True),
                    ))
                records = [
                    RevenueRecord(
                        record_id="R1", source_system="CBS",
                        posting_date=date(2026, 2, 5),
                        amount_kes=Decimal("500000"),
                        revenue_category="INTEREST_INCOME",
                        branch_code="NRB-01"),
                    RevenueRecord(
                        record_id="R2", source_system="CBS",
                        posting_date=date(2026, 2, 20),
                        amount_kes=Decimal("100000"),
                        revenue_category="FEE_INCOME",
                        branch_code="NRB-01"),
                ]
                pkg = eng.generate_report(template, records)
                audit_log(
                    "REVENUE_ENGINE_USED", uname,
                    {"engine": "regulatory_revenue_reporting",
                     "template": pkg.template_id,
                     "total_kes": str(pkg.total_kes)})
                st.metric("Total KES", f"{pkg.total_kes:,}")
                st.metric("Regulator", pkg.regulator.value)
                with st.expander("Line items (Rule 1 provenance)",
                                 expanded=True):
                    for li in pkg.line_items:
                        st.write(
                            f"**{li.line_code} — {li.line_name}** · "
                            f"KES {li.amount_kes:,} · "
                            f"{li.record_count} record(s)")
                        st.caption(
                            f"Records: {list(li.contributing_record_ids)}")
                if pkg.unmapped_categories:
                    st.warning(
                        f"Unmapped categories: "
                        f"{list(pkg.unmapped_categories)} — "
                        f"{pkg.unmapped_record_count} record(s)")


        # Footer audit log
        try:
            audit_log(
                action="revenue_assurance_arc_engines.view",
                username=ud.get("username", "anonymous"),
                detail=f"viewed_at={_dt_ra.now(_tz_ra.utc).isoformat()}",
                module="revenue_assurance")
        except Exception:
            pass
