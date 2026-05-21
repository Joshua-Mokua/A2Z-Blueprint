"""pages/46_trade_finance.py — Trade Finance Tracker.
LC issuance, documentary collections, acceptance tracking, utilisation.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter, defaultdict
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("trade_finance.dashboard")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚢 Trade Finance</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "LC issuance · Documentary collections · Acceptance · Utilisation</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"trade_finance.json"
    return a2z_db.load_json(p) if p.exists() else []

lcs = _load()
active   = [l for l in lcs if l["status"] not in ("Settled","Expired","Cancelled")]
expiring = [l for l in active if l.get("expiry_date") and
            0<=(date.fromisoformat(l["expiry_date"][:10])-today).days<=cfg("lc_expiry_warning_days",14)]
total_usd = sum(l["amount"] for l in active)/1e6
discrepancies = sum(l.get("discrepancies",0) for l in lcs)

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Active LCs",         len(active))
m2.metric("Total Value (USD M)", f"{total_usd:.1f}")
m3.metric("Expiring in 14d",    len(expiring), delta_color="normal" if not expiring else "inverse")
m4.metric("Discrepancies",      discrepancies, delta_color="normal" if not discrepancies else "inverse")
m5.metric("Commission (KES M)",  f"{sum(l['commission_earned'] for l in lcs)/1e6:.2f}")

if expiring:
    st.warning(f"⚠️ {len(expiring)} LC(s) expiring within 14 days — check with client on shipment")

tabs = st.tabs(["📋 LC Register","⏰ Expiring Soon","⚠️ Discrepancies","📊 Analytics","🏦 Correspondent Banks","🤖 Arc Engines"])

def _render_lcs(lc_list, title=""):
    if not lc_list: st.success("None in this view."); return
    rows=[{"ID":l["id"],"Type":l["lc_type"],"Ccy":l["currency"],
            "Amount":f"{l['amount']:,.0f}","Equivalent (KES M)":round(l["kes_equivalent"]/1e6,2),
            "Status":l["status"],"Applicant":l["applicant"][:20],
            "Beneficiary":l["beneficiary"][:20],"Correspondent":l["correspondent"][:20],
            "Expiry":l["expiry_date"][:10],"Disc.":l.get("discrepancies",0),
            "Util%":l["utilised_pct"]}
           for l in sorted(lc_list,key=lambda x:x["expiry_date"])]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[0]:
    f1,f2 = st.columns(2)
    ftype = f1.multiselect("LC Type",["Import LC","Export LC","Standby LC","Transferable LC"],
                            default=["Import LC","Export LC"], key="tf_type")
    fstat = f2.multiselect("Status",list(set(l["status"] for l in lcs)),
                            default=["Issued","Advised","Negotiated","Accepted"], key="tf_stat")
    vis = [l for l in lcs if l["lc_type"] in ftype and l["status"] in fstat]
    st.markdown(f"**{len(vis)} LCs** · USD {sum(l['amount'] for l in vis)/1e6:.1f}M")
    _render_lcs(vis)

with tabs[1]:
    _render_lcs(expiring)
    if expiring:
        st.markdown("**Action:** Contact each applicant to confirm shipment/utilisation status or request extension.")

with tabs[2]:
    disc_lcs = [l for l in lcs if l.get("discrepancies",0)>0]
    if disc_lcs:
        st.warning(f"⚠️ {len(disc_lcs)} LCs with document discrepancies")
        _render_lcs(disc_lcs)
    else:
        st.success("✅ No document discrepancies outstanding.")

with tabs[3]:
    type_ct = Counter(l["lc_type"] for l in lcs)
    st.markdown("**LC volume by type:**")
    st.bar_chart(pd.DataFrame({"Count":dict(type_ct.most_common())}).T.T)
    st.markdown("**Top currencies:**")
    ccy_val = defaultdict(float)
    for l in lcs: ccy_val[l["currency"]] += l["amount"]
    for ccy,val in sorted(ccy_val.items(),key=lambda x:-x[1]):
        st.markdown(f"  {ccy}: {val/1e6:.1f}M")

with tabs[4]:
    corr_ct = Counter(l["correspondent"] for l in lcs)
    st.markdown("**Correspondent banks — LC volumes:**")
    cb_rows=[{"Correspondent":cb,"LC Count":n,"USD Value (M)":round(sum(l["amount"] for l in lcs if l["correspondent"]==cb)/1e6,1)}
              for cb,n in corr_ct.most_common()]
    st.dataframe(pd.DataFrame(cb_rows),use_container_width=True,hide_index=True)


# ──────────────────────────────────────────────────────────────────────
# Section 5: 🤖 Arc Engines (absorbed from 97_trade_finance_arc_cockpit.py
# in v10.211 per the architectural reorganization sub-campaign.
# 10 Trade Finance engines (ENH-269..278, 280) presented as nested
# sub-tabs spanning the trade finance arc: Instruments, Limits, SWIFT,
# Compliance, Accounting, Reporting, Sustainability, Document Checking,
# Corporate Portal, Connectivity. All engines diagnostic — outputs feed
# LC issuance, BG enforcement, and SWIFT message routing workflows.
# Mirrors v10.202..v10.210 absorption patterns.
# ──────────────────────────────────────────────────────────────────────
with tabs[5]:
    from datetime import datetime as _dt_tf, timezone as _tz_tf

    try:
        from utils.trade_finance_instruments import (
            TradeFinanceInstrumentsEngine)
        from utils.trade_finance_limits import TradeFinanceLimitsEngine
        from utils.trade_finance_swift import TradeFinanceSwiftEngine
        from utils.trade_finance_compliance import (
            TradeFinanceComplianceEngine)
        from utils.trade_finance_accounting import (
            TradeFinanceAccountingEngine)
        from utils.trade_finance_reporting import (
            TradeFinanceReportingEngine)
        from utils.trade_finance_sustainability import (
            TradeFinanceSustainabilityEngine)
        from utils.trade_finance_document_checking import (
            TradeFinanceDocumentCheckingEngine)
        from utils.trade_finance_corporate_portal import (
            TradeFinanceCorporatePortalEngine)
        from utils.trade_finance_connectivity import (
            TradeFinanceConnectivityEngine)
        _ARC_TF_AVAILABLE = True
    except ImportError as _ie:
        st.error(f"Trade Finance arc engines unavailable: {_ie}")
        _ARC_TF_AVAILABLE = False

    if _ARC_TF_AVAILABLE:
        st.caption(
            "v10.211 absorbed from 97_trade_finance_arc_cockpit.py — "
            "10 engines spanning trade finance instruments, limits, SWIFT "
            "messaging, compliance/sanctions screening, accounting "
            "templates, reporting, sustainability classification, document "
            "checking, corporate portal, and external connectivity. All "
            "engines diagnostic — outputs feed LC issuance, BG enforcement, "
            "and SWIFT routing.")

        arc_tabs = st.tabs([
            "📋 Instruments + 🛡️ Limits",
            "🔧 SWIFT + 🌐 Connectivity",
            "✅ Compliance",
            "💰 Accounting + 📊 Reporting",
            "🌱 Sustainability + 📑 Documents",
            "🏢 Corporate Portal + Dashboard",
            "ℹ️ About",
        ])

        with arc_tabs[0]:
            st.subheader("📋 Trade Instruments (ENH-269)")
            st.markdown(
                "Diagnostic engine for LC / guarantee / collection "
                "instrument lifecycle tracking. Per Rule 7, never "
                "issues instruments — only validates state "
                "transitions.")

            inst_engine = TradeFinanceInstrumentsEngine()

            col_a, col_b = st.columns(2)
            with col_a:
                from_state = st.selectbox(
                    "FROM state",
                    [s.value for s in InstrumentState],
                    key="inst_from")
            with col_b:
                to_state = st.selectbox(
                    "TO state",
                    [s.value for s in InstrumentState],
                    index=2, key="inst_to")

            if st.button(
                "Run validate_state_transition", key="inst_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.instruments",
                    who=uname,
                    details={"from": from_state, "to": to_state})
                result = inst_engine.validate_state_transition(
                    instrument_id="LC-DEMO",
                    from_state=InstrumentState(from_state),
                    to_state=InstrumentState(to_state),
                    instrument_type=InstrumentType.LC)
                st.success(
                    f"Outcome: **{result.outcome.value}**")
                st.write({
                    "from_state": result.from_state.value,
                    "to_state": result.to_state.value,
                    "rationale": result.rationale,
                    "framework_refs": result.framework_refs})

            st.divider()
            st.subheader("🛡️ Trade Limits (ENH-273)")
            st.markdown(
                "Diagnostic limit-utilization engine. Per Rule 7, "
                "never blocks transactions — surfaces breach severity "
                "for human approval workflow.")

            limits_engine = TradeFinanceLimitsEngine()

            if st.button(
                "Run compute_counterparty_utilization (sample)",
                key="lim_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.limits",
                    who=uname, details={})
                instruments = (
                    _sample_instrument(
                        iid="LC-001", amount=Decimal("3000000")),
                    _sample_instrument(
                        iid="LC-002", amount=Decimal("4500000")),
                )
                cp_limits = (
                    CounterpartyLimit(
                        counterparty_id="CP-DEMO",
                        counterparty_name="Demo Applicant",
                        limit_kes=Decimal("10000000")),)
                results = (
                    limits_engine.compute_counterparty_utilization(
                        instruments, cp_limits))
                for u in results:
                    col1, col2, col3 = st.columns(3)
                    col1.metric(
                        "Counterparty",
                        u.dimension_value)
                    col2.metric(
                        "Utilization",
                        f"{u.utilization_pct:.1%}")
                    col3.metric(
                        "Severity", u.severity.value)
                    st.caption(f"Rationale: {u.rationale}")

        with arc_tabs[1]:
            st.subheader("🔧 SWIFT MT Messages (ENH-272)")
            st.markdown(
                "Diagnostic SWIFT MT700/707/760/103 validator. Per "
                "Rule 7, never sends messages over SWIFTNet.")

            swift_engine = TradeFinanceSwiftEngine()

            if st.button(
                "Run parse_message + validate_mt700_structure",
                key="swift_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.swift",
                    who=uname, details={})
                parsed = swift_engine.parse_message(
                    SwiftMessageType.MT700, SAMPLE_MT700)
                validation = swift_engine.validate_mt700_structure(
                    parsed)
                st.success(f"Outcome: **{validation.outcome.value}**")
                st.write({
                    "field_count": len(parsed.fields),
                    "violation_count": len(validation.findings),
                    "violations": [
                        {"field": f.field_tag,
                         "status": f.status.value,
                         "description": f.description}
                        for f in validation.findings[:5]],
                    "framework_refs": validation.framework_refs})

            st.divider()
            st.subheader("🌐 Multi-Bank Connectivity (ENH-276)")
            st.markdown(
                "Diagnostic adapter surface for inbound network "
                "messages — we.trade / Marco Polo / Contour / Bolero "
                "/ SWIFT GPI / SWIFT FIN. Per Rule 7, never sends "
                "outbound, never connects to networks.")

            conn_engine = TradeFinanceConnectivityEngine()

            if st.button(
                "Run validate_inbound_message_structure + "
                "classify_routing_action (sample we.trade)",
                key="conn_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.connectivity",
                    who=uname, details={})
                msg = InboundMessage(
                    message_id="WT-COCKPIT",
                    network=TradeNetwork.WE_TRADE,
                    received_at=date.today(),
                    body={
                        "message_id": "WT-COCKPIT",
                        "message_type": "ISSUE_LC",
                        "sender_bin": "BIN-A",
                        "receiver_bin": "BIN-B",
                        "lc_reference": "LC-COCK",
                        "amount": "1500000",
                        "currency": "USD",
                        "version": "2.0"})
                v = conn_engine.validate_inbound_message_structure(
                    msg)
                a = conn_engine.classify_routing_action(
                    msg, "message_type",
                    {"ISSUE_LC": RoutingAction.NEW_LC_ISSUANCE})
                col_x, col_y = st.columns(2)
                col_x.metric("Validation status", v.status.value)
                col_y.metric("Routing action", a.action.value)
                st.write({
                    "missing_fields": list(v.missing_fields),
                    "matched_message_type": a.matched_message_type,
                    "framework_refs": v.framework_refs})

        with arc_tabs[2]:
            st.subheader("✅ Compliance Screening (ENH-274)")
            st.markdown(
                "Diagnostic sanctions / restricted-country / dual-use "
                "goods screening. Per Rule 7, never blocks "
                "transactions — compliance officer reviews findings + "
                "decides.")

            comp_engine = TradeFinanceComplianceEngine()

            party_name = st.text_input(
                "Party name to screen", value="Demo Trading Co",
                key="comp_party")

            if st.button("Run screen_party", key="comp_btn"):
                audit_log(
                    event_type="cockpit.tf.compliance",
                    who=uname, details={"party": party_name})
                sample_lists = (
                    SanctionsListEntry(
                        list_id="OFAC_SDN",
                        list_authority="US OFAC",
                        entry_id="DEMO-001",
                        entity_type="ENTITY",
                        name="Sanctioned Entity Demo",
                        aliases=("Sanctioned Entity",),
                        country="XX",
                        severity=HitSeverity.CRITICAL),)
                party = TradeFinanceParty(
                    party_id="P-COCK",
                    party_role="APPLICANT",
                    name=party_name,
                    country="KE",
                    aliases=())
                hits = comp_engine.screen_party(party, sample_lists)
                if not hits:
                    st.success("✅ No sanctions hits")
                else:
                    st.warning(f"⚠️ {len(hits)} hit(s) found")
                    for h in hits:
                        st.write(
                            f"- **{h.severity.value}** "
                            f"{h.match_type.value}: {h.matched_name}")

        with arc_tabs[3]:
            st.subheader("💰 Trade Finance Accounting (ENH-275)")
            st.markdown(
                "Diagnostic accounting hook generator. Per Rule 7, "
                "never posts journals to GL — emits proposed entries "
                "for human review.")

            acc_engine = TradeFinanceAccountingEngine()

            event_choice = st.selectbox(
                "Event",
                [e.value for e in JournalEvent],
                key="acc_event")

            if st.button(
                "Run generate_journal_template", key="acc_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.accounting",
                    who=uname, details={"event": event_choice})
                inst = _sample_instrument()
                result = acc_engine.generate_journal_template(
                    instrument=inst,
                    event=JournalEvent(event_choice),
                    posting_date_iso=date.today().isoformat())
                st.success(
                    f"Lines generated: {len(result.lines)}")
                for line in result.lines:
                    st.write(
                        f"- **{line.side.value}** "
                        f"acct={line.account_class.value} "
                        f"{line.amount_kes:,.2f} — {line.narrative}")
                st.caption(
                    f"Per Rule 7: {result.framework_refs[-1]}")

            st.divider()
            st.subheader("📊 Trade Finance Reporting (ENH-280)")
            st.markdown(
                "Diagnostic reporting + analytics with optional ML "
                "hook for forecast refinement (v10.76 contract). When "
                "no hook injected, statistical fallback runs.")

            rep_engine = TradeFinanceReportingEngine()

            if st.button(
                "Run compute_trade_volumes (sample)", key="rep_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.reporting",
                    who=uname, details={})
                instruments = (
                    _sample_instrument(
                        iid="LC-1", amount=Decimal("1500000")),
                    _sample_instrument(
                        iid="LC-2", amount=Decimal("3000000")),
                    _sample_instrument(
                        iid="GTE-1",
                        state=InstrumentState.EXPIRED,
                        amount=Decimal("500000")),
                )
                vol = rep_engine.compute_trade_volumes(
                    instruments, period_label="2026-Q2")
                col1, col2, col3 = st.columns(3)
                col1.metric(
                    "Total volume (USD)",
                    f"{vol.total_volume_kes:,.0f}")
                col2.metric(
                    "Instrument count", str(vol.instrument_count))
                col3.metric(
                    "Avg ticket size",
                    f"{vol.avg_ticket_size_kes:,.0f}")
                st.caption(
                    f"Method: {vol.method.value} · "
                    f"period: {vol.period_label}")

        with arc_tabs[4]:
            st.subheader("🌱 Sustainable Trade Finance (ENH-278)")
            st.markdown(
                "Diagnostic ESG / climate screening for trade finance "
                "instruments. Per Rule 7, never blocks transactions, "
                "never derates internal ratings.")

            sus_engine = TradeFinanceSustainabilityEngine()

            if st.button(
                "Run classify_instrument_sustainability (sample)",
                key="sus_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.sustainability",
                    who=uname, details={})
                taxonomy = (
                    TaxonomyEntry(
                        keyword="solar",
                        tier=SustainabilityTier.GREEN,
                        source="EU Taxonomy 2023",
                        justification=(
                            "Renewable energy infrastructure")),
                    TaxonomyEntry(
                        keyword="rice",
                        tier=SustainabilityTier.UNCLASSIFIED,
                        source="Internal review pending",
                        justification=(
                            "Agricultural commodity — sustainability "
                            "depends on farming practices")),)
                green_inst = _sample_instrument(
                    description="solar panel components")
                result = (
                    sus_engine.classify_instrument_sustainability(
                        green_inst, taxonomy))
                tier_emoji = {
                    SustainabilityTier.GREEN: "🟢",
                    SustainabilityTier.TRANSITION: "🟡",
                    SustainabilityTier.UNCLASSIFIED: "⚪",
                    SustainabilityTier.BROWN: "🟤",
                }.get(result.tier, "?")
                st.write(
                    f"### {tier_emoji} Tier: {result.tier.value}")
                st.write({
                    "matched_keywords": [
                        m.keyword for m in result.matches],
                    "framework_refs": result.framework_refs})

            st.divider()
            st.subheader(
                "📑 Document Checking (ENH-270, ML-extensible)")
            st.markdown(
                "Diagnostic UCP 600 document examination with "
                "optional ML refinement hook. Per Rule 7, never "
                "approves drawdowns.")

            doc_engine = TradeFinanceDocumentCheckingEngine()

            if st.button(
                "Run assess_presentation (sample late presentation)",
                key="doc_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.docs",
                    who=uname, details={})
                lc = LCTerms(
                    lc_reference="LC-COCK-DOC",
                    amount_kes=Decimal("1000000"),
                    currency="USD",
                    expiry_date=date.today() - timedelta(days=5),
                    latest_shipment_date=(
                        date.today() - timedelta(days=20)),
                    description_of_goods=(
                        "50 metric tons milled rice"),
                    required_documents=(
                        DocumentType.COMMERCIAL_INVOICE,
                        DocumentType.BILL_OF_LADING))
                invoice = PresentedDocument(
                    document_type=DocumentType.COMMERCIAL_INVOICE,
                    issuer="Demo",
                    amount_kes=Decimal("1000000"),
                    currency="USD",
                    issue_date=date.today() - timedelta(days=10),
                    description_of_goods=(
                        "50 metric tons milled rice"))
                bl = PresentedDocument(
                    document_type=DocumentType.BILL_OF_LADING,
                    issuer="Maersk",
                    shipment_date=(
                        date.today() - timedelta(days=15)))
                pres = DocumentPresentation(
                    presentation_id="PR-COCK",
                    lc_reference="LC-COCK-DOC",
                    presentation_date=date.today(),
                    documents=(invoice, bl))
                a = doc_engine.assess_presentation(lc, pres)
                outcome_emoji = {
                    PresentationOutcome.CONFORMING: "✅",
                    PresentationOutcome.DISCREPANT_WAIVABLE: "⚠️",
                    PresentationOutcome
                    .DISCREPANT_REFUSAL_LIKELY: "🚫",
                    PresentationOutcome.REFUSED: "❌",
                    PresentationOutcome.INSUFFICIENT_DATA: "❓",
                }.get(a.outcome, "?")
                st.write(
                    f"### {outcome_emoji} Outcome: "
                    f"{a.outcome.value}")
                st.caption(
                    f"ml_disabled={a.overall_ml_disabled} · "
                    f"findings={len(a.findings)}")
                for f in a.findings:
                    st.write(
                        f"- **{f.severity.value}** "
                        f"{f.category.value}: {f.description}")

        with arc_tabs[5]:
            st.subheader("🏢 Corporate Trade Portal (ENH-271)")
            st.markdown(
                "Front-office data-validation engine. Per Rule 7, "
                "never issues LCs, never amends LCs.")

            portal_engine = TradeFinanceCorporatePortalEngine()

            col_a, col_b = st.columns(2)
            with col_a:
                applicant = st.text_input(
                    "Applicant", value="Acme Imports",
                    key="prt_appl")
                beneficiary = st.text_input(
                    "Beneficiary", value="Demo Supplier",
                    key="prt_bene")
            with col_b:
                amount = st.number_input(
                    "Amount (USD)", value=2_000_000,
                    step=100_000, key="prt_amount")
                currency = st.text_input(
                    "Currency", value="USD", key="prt_curr")

            if st.button(
                "Run validate_lc_application", key="prt_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.portal",
                    who=uname,
                    details={
                        "applicant": applicant,
                        "amount": amount})
                app = LCApplication(
                    application_id="APP-COCK",
                    applicant=applicant,
                    beneficiary=beneficiary,
                    requested_amount_kes=Decimal(str(amount)),
                    currency=currency,
                    requested_expiry_date=(
                        date.today() + timedelta(days=90)),
                    requested_latest_shipment_date=(
                        date.today() + timedelta(days=60)),
                    description_of_goods=(
                        "Sample goods for cockpit demo"),
                    incoterms="CIF",
                    submission_date=date.today())
                v = portal_engine.validate_lc_application(app)
                completeness_emoji = {
                    ApplicationCompleteness.COMPLETE: "✅",
                    ApplicationCompleteness.INCOMPLETE: "⚠️",
                    ApplicationCompleteness.INVALID: "❌",
                }.get(v.completeness, "?")
                st.write(
                    f"### {completeness_emoji} "
                    f"{v.completeness.value}")
                if v.estimated_fees_kes is not None:
                    st.metric(
                        "Estimated fees (preliminary)",
                        f"{v.estimated_fees_kes:,.2f}")
                for f in v.findings:
                    st.write(
                        f"- **{f.severity.value}** "
                        f"{f.field_name}: {f.description}")

            st.divider()

            # ── ENH-277 Dashboard fulfillment ────────────────────────
            st.subheader(
                "📊 Trade Finance Portfolio Dashboard (ENH-277)")
            st.markdown(
                "Composes outputs from the 10 trade finance engines "
                "into operational dashboard views. Per Rule 7, "
                "presentation only — operator interprets, no auto-"
                "action.")

            if st.button(
                "Refresh dashboard (sample portfolio)",
                key="dash_btn"
            ):
                audit_log(
                    event_type="cockpit.tf.dashboard",
                    who=uname, details={})

                positions = (
                    _sample_instrument(
                        iid="LC-001", amount=Decimal("2500000")),
                    _sample_instrument(
                        iid="LC-002", amount=Decimal("4500000")),
                    _sample_instrument(
                        iid="LC-003", state=InstrumentState.DRAWN,
                        amount=Decimal("1500000")),
                    _sample_instrument(
                        iid="GTE-001", amount=Decimal("750000")),
                )
                rep = TradeFinanceReportingEngine()
                vol = rep.compute_trade_volumes(
                    positions, period_label="2026-Q2")

                st.markdown("**📋 Pipeline View**")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric(
                    "Total instruments",
                    str(vol.instrument_count))
                col2.metric(
                    "Total volume (USD)",
                    f"{vol.total_volume_kes:,.0f}")
                col3.metric(
                    "Avg ticket",
                    f"{vol.avg_ticket_size_kes:,.0f}")
                col4.metric(
                    "Period", vol.period_label)

                st.markdown("**🏢 Top Applicants by Exposure**")
                from collections import Counter
                by_applicant: Counter = Counter()
                for p in positions:
                    by_applicant[p.applicant] += float(p.amount_kes)
                for corp, exp in by_applicant.most_common(5):
                    st.write(f"- **{corp}**: USD {exp:,.0f}")

                st.caption(
                    "Per Rule 7 — dashboard composition is "
                    "presentational; operator interprets the views, "
                    "no auto-action.")

        with arc_tabs[6]:
            st.markdown("""
### About the trade_finance arc

The trade_finance arc is the **14th closed arc** on the
A2Z MIS 360 platform, locked at v10.80 under audit gates G137
(arc closure — registry + scenarios + modules + Rule 7 + Rule
1) and G138 (UI integration ratchet — this cockpit page).

**Arc duration:** v10.70 → v10.80 (10 dual-batch drops + 1
single-batch + 1 ops-hygiene drop + 1 closure batch).

**Engines (10):**

| Engine | Standard | Drop |
|---|---|---|
| trade_finance_instruments | ENH-269 | v10.70 |
| trade_finance_limits | ENH-273 | v10.71 |
| trade_finance_swift | ENH-272 | v10.72 |
| trade_finance_compliance | ENH-274 | v10.73 |
| trade_finance_accounting | ENH-275 | v10.75 |
| trade_finance_reporting | ENH-280 | v10.76 |
| trade_finance_sustainability | ENH-278 | v10.77 |
| trade_finance_document_checking | ENH-270 | v10.78 |
| trade_finance_corporate_portal | ENH-271 | v10.79 |
| trade_finance_connectivity | ENH-276 | v10.79 |

**Standards (11 of 12 active):**

ENH-269, ENH-270, ENH-271, ENH-272, ENH-273, ENH-274, ENH-275,
ENH-276, ENH-277 (this cockpit), ENH-278, ENH-280.

**Deferred:** ENH-279 Trade Finance Mobile App.

**Scenario library coverage:** 40 trade finance scenarios.

**v10.76 ML hook contract** — ENH-280 + ENH-270 accept optional
Callable hooks for ML refinement. When no hook, deterministic
rules + statistical fallback run. Every output carries
`ml_disabled` + `method` enum.

**Per Rule 7, every engine is diagnostic only** — never issues
LCs, never amends instruments, never sends SWIFT or network
messages, never connects to external networks (we.trade /
Marco Polo / Contour / Bolero), never posts journals to the
GL, never blocks transactions, never approves drawdowns, never
derates internal credit ratings, never auto-decisions ML
predictions.

The cockpit makes this posture visible — every engine
invocation surfaces inputs, intermediates, outputs, and
framework refs. Operator decides; engine surfaces.

**Master Prompt v10.80** — trade_finance arc moves from
"in flight" to "closed arcs" section. Next focus:
ML governance arc post-closure (drift monitoring + model
registry + adjudication feedback loop + scheduled retraining
+ A/B comparison + per-model model cards).
""")

        # Footer audit log
        try:
            audit_log(
                action="trade_finance_arc_engines.view",
                username=ud.get("username", "anonymous"),
                detail=f"viewed_at={_dt_tf.now(_tz_tf.utc).isoformat()}",
                module="trade_finance")
        except Exception:
            pass
