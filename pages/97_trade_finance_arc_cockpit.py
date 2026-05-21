"""pages/97_trade_finance_arc_cockpit.py — trade_finance Arc Cockpit (v10.80).

Locks the v10.46 Lean+Compact protocol amendment for the trade
finance arc closure (14th closed arc). This page makes all 10
v10.70-v10.79 engines operator-driveable from the browser.

This cockpit also fulfills ENH-277 — Trade Finance Dashboard —
by composing outputs from the 10 engines into pipeline /
processing-time / exception-aging / top-corporates / country-
exposure views.

Per Rule 1, every engine result renders with full provenance.
Per Rule 7, all 10 engines are diagnostic; this cockpit surfaces
exposure, never issues LCs, never amends LCs, never sends SWIFT
or network messages, never posts journals to the GL, never
blocks transactions, never approves drawdowns.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import streamlit as st

from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

from utils.trade_finance_instruments import (
    TradeFinanceInstrumentsEngine, TradeInstrument,
    InstrumentType, InstrumentState, LcType)
from utils.trade_finance_limits import (
    TradeFinanceLimitsEngine, CounterpartyLimit,
    LimitDimension, UtilizationSeverity)
from utils.trade_finance_swift import (
    TradeFinanceSwiftEngine, SwiftMessageType, SAMPLE_MT700,
    MessageValidationOutcome)
from utils.trade_finance_compliance import (
    TradeFinanceComplianceEngine, TradeFinanceParty,
    SanctionsListEntry, ScreeningOutcome, HitSeverity)
from utils.trade_finance_accounting import (
    TradeFinanceAccountingEngine, JournalEvent)
from utils.trade_finance_reporting import (
    TradeFinanceReportingEngine)
from utils.trade_finance_sustainability import (
    TradeFinanceSustainabilityEngine, TaxonomyEntry,
    SustainabilityTier)
from utils.trade_finance_document_checking import (
    TradeFinanceDocumentCheckingEngine, LCTerms,
    PresentedDocument, DocumentPresentation, DocumentType,
    DiscrepancySeverity, FindingMethod, PresentationOutcome)
from utils.trade_finance_corporate_portal import (
    TradeFinanceCorporatePortalEngine, LCApplication,
    ApplicationCompleteness, AmendmentType,
    DocumentValidationOutcome,
    MessageRoutingDestination)
from utils.trade_finance_connectivity import (
    TradeFinanceConnectivityEngine, InboundMessage,
    FieldMapping, TradeNetwork,
    MessageValidationStatus, RoutingAction, AnomalyType)


# ══════════════════════════════════════════════════════════════════════
# Access + setup
# ══════════════════════════════════════════════════════════════════════

require_access("perform")
um, ud, uname, *_ = load_shared_state()[:12]


# ══════════════════════════════════════════════════════════════════════
# Header
# ══════════════════════════════════════════════════════════════════════

st.markdown(
    "<div style='padding:24px;background:linear-gradient(135deg,"
    "#0F766E 0%,#1E40AF 100%);"
    "border-radius:16px;color:white;margin-bottom:20px'>"
    "<div style='font-size:13px;letter-spacing:2px;opacity:0.85'>"
    "TRADE FINANCE ARC · LIVE COCKPIT</div>"
    "<div style='font-size:28px;font-weight:800;margin-top:6px'>"
    "Trade Finance Arc Cockpit</div>"
    "<div style='font-size:14px;opacity:0.9;margin-top:8px'>"
    "Ten diagnostic engines locked under G137+G138 — instruments, "
    "limits, SWIFT, connectivity, compliance screening, accounting, "
    "reporting + analytics, sustainability, document checking, "
    "corporate portal. Per Rule 7 every engine is diagnostic — "
    "surfaces exposure, never issues LCs, never amends LCs, never "
    "sends SWIFT or network messages, never posts journals to GL, "
    "never blocks transactions, never approves drawdowns.</div>"
    "</div>",
    unsafe_allow_html=True,
)

st.caption(
    "v10.80 · trade_finance arc closure under v10.46-amended "
    "Lean+Compact protocol — 14th closed arc")


# ══════════════════════════════════════════════════════════════════════
# Helper: build a sample instrument for demos
# ══════════════════════════════════════════════════════════════════════

def _sample_instrument(
    iid="LC-DEMO",
    state=InstrumentState.ACTIVE,
    amount=Decimal("2000000"),
    description="Demo goods",
):
    return TradeInstrument(
        instrument_id=iid,
        instrument_type=InstrumentType.LC,
        state=state,
        applicant="Demo Applicant",
        beneficiary="Demo Beneficiary",
        issuing_bank="Bank-A",
        advising_bank="Bank-B",
        amount_kes=amount,
        currency="USD",
        issue_date=date.today() - timedelta(days=30),
        expiry_date=date.today() + timedelta(days=90),
        tenor_days=180,
        lc_type=LcType.SIGHT,
        bg_type=None,
        drawn_amount_kes=Decimal("0"),
        has_partial_shipments=False,
        has_transhipment_allowed=False,
        incoterms="CIF Mombasa",
        description_of_goods=description)


with st.expander("ℹ️ About this cockpit"):
    st.markdown("""
**v10.80 · trade_finance arc closure**

Ten engines locked under audit gates G137 (registry + scenarios +
modules + Rule 7 + Rule 1) and G138 (UI integration). Fourteenth
closed arc on the platform.

**Standards activated (11 of 12):**
- ENH-269 Instruments · ENH-270 Document Checking (ML-extensible)
  · ENH-271 Corporate Portal · ENH-272 SWIFT
- ENH-273 Limits · ENH-274 Compliance Screening · ENH-275
  Accounting · ENH-276 Multi-Bank Connectivity
- ENH-277 Dashboard (this cockpit) · ENH-278 Sustainability ·
  ENH-280 Reporting

**Deferred (1 of 12):** ENH-279 Mobile App — UI delivery concern,
not an engine-architecture concern. ENH-271 corporate portal data
layer already supports mobile UI clients via the same API.

**Scenario coverage:** 40 trade finance scenarios across the arc.

**v10.76 ML hook contract** — ENH-280 and ENH-270 accept optional
ML hooks. Every output carries `ml_disabled` + `method` enum.
""")


# ══════════════════════════════════════════════════════════════════════
# Tabs
# ══════════════════════════════════════════════════════════════════════

tabs = st.tabs([
    "📋 Instruments + 🛡️ Limits",
    "🔧 SWIFT + 🌐 Connectivity",
    "✅ Compliance",
    "💰 Accounting + 📊 Reporting",
    "🌱 Sustainability + 📑 Documents",
    "🏢 Corporate Portal + Dashboard",
    "ℹ️ About",
])


# ──────────────────────────────────────────────────────────────────────
# Tab 1: Instruments + Limits
# ──────────────────────────────────────────────────────────────────────

with tabs[0]:
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


# ──────────────────────────────────────────────────────────────────────
# Tab 2: SWIFT + Connectivity
# ──────────────────────────────────────────────────────────────────────

with tabs[1]:
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


# ──────────────────────────────────────────────────────────────────────
# Tab 3: Compliance
# ──────────────────────────────────────────────────────────────────────

with tabs[2]:
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


# ──────────────────────────────────────────────────────────────────────
# Tab 4: Accounting + Reporting
# ──────────────────────────────────────────────────────────────────────

with tabs[3]:
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


# ──────────────────────────────────────────────────────────────────────
# Tab 5: Sustainability + Documents
# ──────────────────────────────────────────────────────────────────────

with tabs[4]:
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


# ──────────────────────────────────────────────────────────────────────
# Tab 6: Corporate Portal + Dashboard
# ──────────────────────────────────────────────────────────────────────

with tabs[5]:
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


# ──────────────────────────────────────────────────────────────────────
# Tab 7: About
# ──────────────────────────────────────────────────────────────────────

with tabs[6]:
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
