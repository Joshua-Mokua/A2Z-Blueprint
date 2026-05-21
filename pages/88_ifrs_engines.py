"""pages/88_ifrs_engines.py — IFRS & Standards Engines Studio (v5.71).

Live interactive surface for the 116 deterministic standards engines built in
v5.53 — v5.70. This first integration page surfaces three production-grade
engines that operations and finance teams can use immediately:

    • #97  Tax & VAT Compliance     (KRA Tax Procedures Act)
    • #98  Procurement Workflow      (5-tier approvals + 3-way match)
    • #99  Financial Close           (T+N milestones + materiality + signoff)

Every computation flows through the audited engines registered against
audit gates G89, G90, G91 (passing in v5.70 as part of 103/103). No
synthetic data — all inputs come from the user. Rule 1 / Rule 6 honesty
discipline is preserved (None when inputs missing; fail-closed when
boundaries violated).
"""
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

from decimal import Decimal, InvalidOperation
from datetime import date
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log
from utils.config import currency_symbol, tax_authority

# Import the 3 standards engines we are surfacing live
from utils.tax_compliance import (
    TaxComplianceEngine,
    VAT_STANDARD_RATE_PCT, WITHHOLDING_TAX_RATES_PCT,
    CORPORATE_TAX_RATES_PCT, FILING_DEADLINE_DAYS,
    LATE_FILING_PENALTY_PCT_PER_MONTH, LATE_FILING_PENALTY_MIN_KES,
)
from utils.procurement_workflow import (
    ProcurementWorkflowEngine,
    APPROVAL_TIERS, BUYER_LIMIT_KES, MANAGER_LIMIT_KES,
    DIRECTOR_LIMIT_KES, MD_LIMIT_KES,
    PROCUREMENT_METHODS, QUOTATIONS_REQUIRED,
    THREE_WAY_MATCH_TOLERANCE_PCT,
)
from utils.financial_close import (
    FinancialCloseEngine,
    CLOSE_STATES, RECONCILIATION_TYPES,
    MATERIALITY_THRESHOLD_PCT, SIGNOFF_LEVELS,
    CLOSE_CALENDAR_MILESTONES,
)

# Access — anyone with finance/compliance/operations exposure
require_access("credit.ifrs_engines")  # Use 'perform' as gating module since this is broadly useful

um, ud, uname, *_ = load_shared_state()[:12]


# ── Header ────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:24px;background:linear-gradient(135deg,#1E40AF 0%,#0EA5E9 100%);"
    "border-radius:16px;color:white;margin-bottom:20px'>"
    "<div style='font-size:13px;letter-spacing:2px;opacity:0.85'>STANDARDS LIBRARY · LIVE</div>"
    "<div style='font-size:28px;font-weight:800;margin-top:6px'>IFRS Engines Studio</div>"
    "<div style='font-size:14px;opacity:0.9;margin-top:8px'>"
    "Interactive surface for the deterministic standards engines. Every computation "
    "below uses the same audited code that passes audit gates G89, G90, G91 in production. "
    "No synthetic data — all inputs are yours.</div></div>",
    unsafe_allow_html=True,
)

# Engine selector
engine_tabs = st.tabs([
    "🧾 Tax & VAT Compliance (#97)",
    "🛒 Procurement Workflow (#98)",
    "📑 Financial Close (#99)",
    "📊 IFRS 7 Disclosures (v7.9)",
    "ℹ️ About",
])


# ============================================================================
# Helper for Decimal input
# ============================================================================
def _to_decimal(val, default=None):
    """Safely convert to Decimal. Returns None if input is empty/invalid."""
    if val is None or val == "" or val == 0:
        return default if default is not None else (None if val == "" else Decimal("0"))
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


# ============================================================================
# TAB 1 — Tax & VAT Compliance (Standard #97)
# ============================================================================
with engine_tabs[0]:
    st.markdown("#### Tax & VAT Compliance — Standard #97 (Cat B)")
    st.caption(
        f"{tax_authority()} Tax Procedures Act + VAT Act + Income Tax Act. Engine `TaxComplianceEngine`. "
        f"VAT standard rate: **{VAT_STANDARD_RATE_PCT}%**, "
        f"corporate tax (resident): **30%**, late filing penalty: "
        f"**{LATE_FILING_PENALTY_PCT_PER_MONTH}%/month** or "
        f"**{currency_symbol()} {int(LATE_FILING_PENALTY_MIN_KES):,} min**."
    )

    sub_tabs = st.tabs(["VAT Payable", "Corporate Tax", "Withholding Tax",
                         "Filing Deadlines", "Late Penalty"])

    # --- VAT payable ---
    with sub_tabs[0]:
        st.markdown("**Net VAT Payable** (output VAT − input VAT)")
        c1, c2 = st.columns(2)
        with c1:
            sales = st.number_input(f"Sales ({currency_symbol()}, exclusive of VAT)",
                                     min_value=0.0, value=1_000_000.0, step=10_000.0,
                                     key="tax_vat_sales")
        with c2:
            input_vat = st.number_input(f"Input VAT ({currency_symbol()}, claimable)",
                                         min_value=0.0, value=80_000.0, step=1_000.0,
                                         key="tax_vat_input")
        if st.button("Compute VAT", key="tax_vat_btn", type="primary"):
            output_vat_r = TaxComplianceEngine.vat_output(
                _to_decimal(sales), "STANDARD")
            output_vat = _to_decimal(output_vat_r.get("vat")) if output_vat_r else None
            if output_vat is None:
                st.error("Could not compute output VAT.")
            else:
                payable = TaxComplianceEngine.vat_payable(output_vat, _to_decimal(input_vat))
                k1, k2, k3 = st.columns(3)
                k1.metric("Output VAT (16% × sales)", f"{currency_symbol()} {output_vat:,.2f}")
                k2.metric("Input VAT (claimable)", f"{currency_symbol()} {Decimal(str(input_vat)):,.2f}")
                if payable is not None:
                    if payable >= 0:
                        k3.metric(f"VAT Payable to {tax_authority()}", f"{currency_symbol()} {payable:,.2f}")
                    else:
                        k3.metric("Refund Position", f"{currency_symbol()} {abs(payable):,.2f}",
                                   delta="Refund due", delta_color="off")
                else:
                    k3.metric("VAT Payable", "—")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Tax #97: VAT payable computed (sales={sales}, input={input_vat})")

    # --- Corporate tax ---
    with sub_tabs[1]:
        st.markdown("**Corporate Tax**")
        c1, c2 = st.columns(2)
        with c1:
            taxable = st.number_input(f"Taxable income ({currency_symbol()})",
                                       min_value=0.0, value=10_000_000.0, step=100_000.0,
                                       key="tax_corp_inc")
        with c2:
            entity_type = st.selectbox("Entity type",
                                        list(CORPORATE_TAX_RATES_PCT.keys()),
                                        key="tax_corp_entity")
        rate = CORPORATE_TAX_RATES_PCT[entity_type]
        st.caption(f"Rate for **{entity_type}**: {rate}%")
        if st.button("Compute corporate tax", key="tax_corp_btn", type="primary"):
            r = TaxComplianceEngine.corporate_tax(_to_decimal(taxable), entity_type)
            if r.get("computed"):
                st.success(f"Tax = {currency_symbol()} **{Decimal(r['tax']):,.2f}** "
                            f"(at {r['rate_pct']}% rate)")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Tax #97: Corp tax {entity_type} on {taxable}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")

    # --- Withholding tax ---
    with sub_tabs[2]:
        st.markdown(f"**Withholding Tax** ({tax_authority()} WHT schedule)")
        c1, c2 = st.columns(2)
        with c1:
            gross = st.number_input(f"Gross payment ({currency_symbol()})",
                                     min_value=0.0, value=100_000.0, step=1_000.0,
                                     key="tax_wht_gross")
        with c2:
            cat = st.selectbox("Income category",
                                list(WITHHOLDING_TAX_RATES_PCT.keys()),
                                key="tax_wht_cat")
        rate = WITHHOLDING_TAX_RATES_PCT[cat]
        st.caption(f"WHT rate for **{cat}**: {rate}%")
        if st.button("Compute WHT", key="tax_wht_btn", type="primary"):
            r = TaxComplianceEngine.withholding_tax(_to_decimal(gross), cat)
            if r.get("computed"):
                k1, k2, k3 = st.columns(3)
                k1.metric("Gross", f"{currency_symbol()} {Decimal(r['gross_payment']):,.2f}")
                k2.metric(f"WHT ({r['rate_pct']}%)", f"{currency_symbol()} {Decimal(r['wht']):,.2f}")
                k3.metric("Net to recipient", f"{currency_symbol()} {Decimal(r['net_payment']):,.2f}")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Tax #97: WHT {cat} on {gross}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")

    # --- Filing deadlines ---
    with sub_tabs[3]:
        st.markdown(f"**Filing Deadlines** ({tax_authority()} — days after period end)")
        c1, c2 = st.columns(2)
        with c1:
            tax_type = st.selectbox("Tax type",
                                     list(FILING_DEADLINE_DAYS.keys()),
                                     key="tax_deadline_type")
        with c2:
            period_end = st.date_input("Period end", value=date.today(),
                                        key="tax_deadline_period")
        days = FILING_DEADLINE_DAYS[tax_type]
        st.caption(f"Filing deadline for **{tax_type}**: {days} days after period end")
        if st.button("Compute deadline", key="tax_deadline_btn", type="primary"):
            r = TaxComplianceEngine.filing_deadline(tax_type, period_end)
            if r.get("computed"):
                k1, k2, k3 = st.columns(3)
                k1.metric("Period end", r["period_end"])
                k2.metric("Days", str(r["filing_deadline_days"]))
                k3.metric("Deadline", r["deadline_date"])
                # Status
                status_r = TaxComplianceEngine.filing_status(
                    tax_type, period_end, filed=False)
                if status_r.get("computed"):
                    status = status_r.get("status", "—")
                    color = ("#DC2626" if status == "OVERDUE"
                             else "#F59E0B" if status == "DUE"
                             else "#10B981")
                    st.markdown(
                        f"<div style='padding:12px;background:{color}22;"
                        f"border-left:4px solid {color};border-radius:8px'>"
                        f"<b>Current filing status:</b> {status}</div>",
                        unsafe_allow_html=True)
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Tax #97: Deadline {tax_type} period_end={period_end}")

    # --- Late penalty ---
    with sub_tabs[4]:
        st.markdown("**Late Filing Penalty** (5%/month or KES 10K min)")
        c1, c2 = st.columns(2)
        with c1:
            tax_due = st.number_input("Tax due (KES)",
                                       min_value=0.0, value=100_000.0, step=10_000.0,
                                       key="tax_pen_due")
        with c2:
            months = st.number_input("Months late", min_value=0, value=2, step=1,
                                      key="tax_pen_months")
        if st.button("Compute penalty", key="tax_pen_btn", type="primary"):
            penalty = TaxComplianceEngine.late_filing_penalty(
                _to_decimal(tax_due), int(months))
            if penalty is None:
                st.error("Invalid input — penalty cannot be computed.")
            else:
                pct_part = (Decimal(str(tax_due)) * LATE_FILING_PENALTY_PCT_PER_MONTH
                            * Decimal(months)) / Decimal("100")
                k1, k2, k3 = st.columns(3)
                k1.metric("Pct penalty (5%/mo)", f"{currency_symbol()} {pct_part:,.2f}")
                k2.metric("Min floor", f"KES {LATE_FILING_PENALTY_MIN_KES:,.2f}")
                k3.metric("**Penalty (greater of)**", f"{currency_symbol()} {penalty:,.2f}")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Tax #97: Late penalty {tax_due} for {months}mo")


# ============================================================================
# TAB 2 — Procurement Workflow (Standard #98)
# ============================================================================
with engine_tabs[1]:
    st.markdown("#### Procurement Workflow — Standard #98 (Cat B)")
    st.caption(
        "Approval matrix + procurement method + 3-way match. Engine `ProcurementWorkflowEngine`. "
        f"Tiers: BUYER ≤ KES {int(BUYER_LIMIT_KES):,}, "
        f"MANAGER ≤ {int(MANAGER_LIMIT_KES):,}, "
        f"DIRECTOR ≤ {int(DIRECTOR_LIMIT_KES):,}, "
        f"MD ≤ {int(MD_LIMIT_KES):,}, BOARD > MD limit. "
        f"3-way match tolerance: ±{THREE_WAY_MATCH_TOLERANCE_PCT}%."
    )

    sub_tabs = st.tabs(["Approval Authority", "Procurement Method", "3-Way Match"])

    # --- Approval authority ---
    with sub_tabs[0]:
        st.markdown("**Who must approve this procurement?**")
        amount = st.number_input("Procurement amount (KES)",
                                  min_value=0.0, value=500_000.0, step=10_000.0,
                                  key="proc_app_amount")
        if st.button("Determine approval tier", key="proc_app_btn", type="primary"):
            r = ProcurementWorkflowEngine.approval_authority(_to_decimal(amount))
            if r.get("computed"):
                tier = r["tier"]
                tier_color = {"BUYER":"#10B981","MANAGER":"#3B82F6","DIRECTOR":"#8B5CF6",
                              "MD":"#F59E0B","BOARD":"#DC2626"}.get(tier, "#6B7280")
                st.markdown(
                    f"<div style='padding:20px;background:{tier_color}22;"
                    f"border-left:6px solid {tier_color};border-radius:12px'>"
                    f"<div style='font-size:13px;letter-spacing:1.5px;opacity:0.7'>"
                    f"REQUIRED APPROVAL TIER</div>"
                    f"<div style='font-size:32px;font-weight:800;color:{tier_color};"
                    f"margin-top:6px'>{tier}</div>"
                    f"<div style='font-size:13px;margin-top:8px'>Amount: "
                    f"KES {Decimal(r['amount_kes']):,.2f}</div></div>",
                    unsafe_allow_html=True)
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Procurement #98: Approval tier for {amount}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")

        with st.expander("All approval tiers"):
            tier_rows = [
                ("BUYER", f"≤ KES {int(BUYER_LIMIT_KES):,}"),
                ("MANAGER", f"KES {int(BUYER_LIMIT_KES)+1:,} – {int(MANAGER_LIMIT_KES):,}"),
                ("DIRECTOR", f"KES {int(MANAGER_LIMIT_KES)+1:,} – {int(DIRECTOR_LIMIT_KES):,}"),
                ("MD", f"KES {int(DIRECTOR_LIMIT_KES)+1:,} – {int(MD_LIMIT_KES):,}"),
                ("BOARD", f"> KES {int(MD_LIMIT_KES):,}"),
            ]
            for tier, rng in tier_rows:
                st.write(f"- **{tier}** — {rng}")

    # --- Procurement method ---
    with sub_tabs[1]:
        st.markdown("**Which procurement method applies?**")
        amount2 = st.number_input("Procurement amount (KES)",
                                   min_value=0.0, value=500_000.0, step=10_000.0,
                                   key="proc_method_amount")
        if st.button("Determine method", key="proc_method_btn", type="primary"):
            r = ProcurementWorkflowEngine.procurement_method(_to_decimal(amount2))
            if r.get("computed"):
                method = r["method"]
                quotes = r.get("quotations_required", "—")
                k1, k2 = st.columns(2)
                k1.metric("Method", method)
                k2.metric("Quotations required", str(quotes))
                method_descriptions = {
                    "DIRECT_PURCHASE": "Single quotation, low value",
                    "REQUEST_FOR_QUOTATION": "3 quotations, mid value",
                    "OPEN_TENDER": "Public tender — any number of bidders",
                    "RESTRICTED_TENDER": "Pre-qualified vendor list (5 bidders)",
                    "FRAMEWORK_AGREEMENT": "Recurring panel arrangement",
                }
                st.info(method_descriptions.get(method, "—"))
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Procurement #98: Method for {amount2}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")

    # --- 3-way match ---
    with sub_tabs[2]:
        st.markdown("**3-Way Match** (PO ↔ GRN ↔ Invoice; tolerance ±2%)")
        c1, c2, c3 = st.columns(3)
        with c1:
            po_amt = st.number_input("PO amount", min_value=0.0,
                                      value=100_000.0, step=1_000.0, key="proc_3w_po")
        with c2:
            grn_amt = st.number_input("GRN amount", min_value=0.0,
                                       value=102_000.0, step=1_000.0, key="proc_3w_grn")
        with c3:
            inv_amt = st.number_input("Invoice amount", min_value=0.0,
                                       value=100_000.0, step=1_000.0, key="proc_3w_inv")
        if st.button("Run 3-way match", key="proc_3w_btn", type="primary"):
            r = ProcurementWorkflowEngine.three_way_match(
                _to_decimal(po_amt), _to_decimal(grn_amt), _to_decimal(inv_amt))
            if r.get("computed"):
                matched = r.get("matched")
                eligible = r.get("eligible_for_payment")
                if matched and eligible:
                    color = "#10B981"; verdict = "✅ MATCHED — eligible for payment"
                else:
                    color = "#DC2626"; verdict = "❌ MISMATCH — payment blocked"
                st.markdown(
                    f"<div style='padding:18px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px'>"
                    f"<div style='font-size:18px;font-weight:700;color:{color}'>"
                    f"{verdict}</div></div>", unsafe_allow_html=True)
                k1, k2 = st.columns(2)
                k1.metric("GRN deviation vs PO",
                           f"{Decimal(r['grn_deviation_pct']):.2f}%")
                k2.metric("Invoice deviation vs PO",
                           f"{Decimal(r['invoice_deviation_pct']):.2f}%")
                st.caption(f"Tolerance: ±{r['tolerance_pct']}%")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Procurement #98: 3WM PO={po_amt} GRN={grn_amt} INV={inv_amt}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")


# ============================================================================
# TAB 3 — Financial Close (Standard #99)
# ============================================================================
with engine_tabs[2]:
    st.markdown("#### Financial Close & Reconciliation Discipline — Standard #99 (Cat B)")
    st.caption(
        "Materiality + signoff + recon variance + close calendar. "
        "Engine `FinancialCloseEngine`. "
        f"Materiality threshold: **{MATERIALITY_THRESHOLD_PCT}%** (strict >); "
        f"suspense: **zero tolerance**; "
        f"signoff levels: **{' → '.join(SIGNOFF_LEVELS)}** (all 3 required)."
    )

    sub_tabs = st.tabs(["Recon Variance", "Materiality Check",
                         "Close Calendar", "Signoff Compliance"])

    # --- Recon variance ---
    with sub_tabs[0]:
        st.markdown("**Reconciliation Variance** (subledger − GL)")
        c1, c2 = st.columns(2)
        with c1:
            gl = st.number_input("GL balance (KES)",
                                  value=1_000_000.0, step=10_000.0, key="close_var_gl")
        with c2:
            subledger = st.number_input("Subledger balance (KES)",
                                         value=1_001_000.0, step=10_000.0,
                                         key="close_var_sub")
        if st.button("Compute variance", key="close_var_btn", type="primary"):
            r = FinancialCloseEngine.reconciliation_variance(
                _to_decimal(gl), _to_decimal(subledger))
            if r.get("computed"):
                k1, k2 = st.columns(2)
                k1.metric("Variance (KES)", f"{Decimal(r['variance']):,.2f}")
                pct = r.get("variance_pct")
                k2.metric("Variance %",
                           f"{Decimal(pct):.4f}%" if pct is not None else "—")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Close #99: Recon variance GL={gl} Sub={subledger}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")

    # --- Materiality ---
    with sub_tabs[1]:
        st.markdown("**Materiality Check** (0.1% threshold, strict >)")
        c1, c2 = st.columns(2)
        with c1:
            var_pct = st.number_input("Variance %",
                                       value=0.05, step=0.01, format="%.4f",
                                       key="close_mat_pct")
        with c2:
            recon_type = st.selectbox("Reconciliation type", RECONCILIATION_TYPES,
                                       key="close_mat_type")
        if st.button("Check materiality", key="close_mat_btn", type="primary"):
            r = FinancialCloseEngine.materiality_check(
                _to_decimal(var_pct), recon_type)
            if r.get("computed"):
                material = r.get("material")
                if material:
                    color = "#DC2626"; verdict = "❌ MATERIAL — needs investigation"
                else:
                    color = "#10B981"; verdict = "✅ NOT MATERIAL — within threshold"
                st.markdown(
                    f"<div style='padding:16px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px'>"
                    f"<div style='font-size:16px;font-weight:700;color:{color}'>"
                    f"{verdict}</div>"
                    f"<div style='font-size:13px;margin-top:6px'>"
                    f"{r.get('rationale','')}</div></div>",
                    unsafe_allow_html=True)
                if recon_type == "SUSPENSE_ACCOUNT":
                    st.warning("⚠ SUSPENSE accounts have **zero tolerance** — "
                                "any non-zero variance is material.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Close #99: Materiality {var_pct}% on {recon_type}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")

    # --- Close calendar ---
    with sub_tabs[2]:
        st.markdown("**Close Calendar Milestones** (T+N days from period end)")
        c1, c2 = st.columns(2)
        with c1:
            period_end_close = st.date_input("Period end",
                                              value=date.today(),
                                              key="close_cal_period")
        with c2:
            milestone = st.selectbox("Milestone",
                                      list(CLOSE_CALENDAR_MILESTONES.keys()),
                                      key="close_cal_milestone")
        days = CLOSE_CALENDAR_MILESTONES[milestone]
        st.caption(f"**{milestone}** = T+{days} days after period end")
        if st.button("Compute milestone date", key="close_cal_btn", type="primary"):
            r = FinancialCloseEngine.close_calendar_milestone(period_end_close, milestone)
            if r.get("computed"):
                k1, k2, k3 = st.columns(3)
                k1.metric("Period end", r["period_end"])
                k2.metric("T+N", f"+{r['days_offset']}")
                k3.metric("Target date", r["deadline_date"])
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Close #99: Milestone {milestone}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")

        with st.expander("Full close calendar"):
            for m, d in CLOSE_CALENDAR_MILESTONES.items():
                st.write(f"- **{m}** — T+{d} days")

    # --- Signoff completeness ---
    with sub_tabs[3]:
        st.markdown(f"**Signoff Compliance** (all 3 levels required: "
                     f"{' → '.join(SIGNOFF_LEVELS)})")
        cols = st.columns(len(SIGNOFF_LEVELS))
        provided = {}
        for col, lvl in zip(cols, SIGNOFF_LEVELS):
            with col:
                provided[lvl] = st.checkbox(lvl, value=True, key=f"close_so_{lvl}")
        if st.button("Check signoff", key="close_so_btn", type="primary"):
            r = FinancialCloseEngine.signoff_complete(provided)
            if r.get("computed"):
                ok = r.get("eligible_for_close")
                if ok:
                    color = "#10B981"; verdict = "✅ COMPLETE — eligible for close"
                else:
                    color = "#DC2626"; verdict = "❌ INCOMPLETE — close blocked"
                st.markdown(
                    f"<div style='padding:16px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px'>"
                    f"<div style='font-size:16px;font-weight:700;color:{color}'>"
                    f"{verdict}</div></div>", unsafe_allow_html=True)
                missing = r.get("missing_levels", [])
                if missing:
                    st.warning(f"Missing signoffs: {', '.join(missing)}")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Close #99: Signoff check missing={missing}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason','unknown')}")


# ============================================================================
# TAB 4 — IFRS 7 Disclosures Engine (v7.9)
# ============================================================================
with engine_tabs[3]:
    st.markdown("#### IFRS 7 Financial Instruments Disclosures — v7.9 surfacing")
    st.caption(
        "Interactive depth on `utils.ifrs7_disclosures.IFRS7DisclosureEngine`. "
        "Final leg of v7.1's planned triple-page Credit Risk depth campaign "
        "(page 19 PD/LGD/EAD scoring → page 32 IFRS 9 classification → "
        "**page 88 IFRS 7 disclosures**). Per IFRS 7, banks must publicly "
        "disclose information enabling users to evaluate the significance of "
        "financial instruments and the nature/extent of risks they bring."
    )

    from utils.ifrs7_disclosures import IFRS7DisclosureEngine

    ifrs7_sections = st.tabs([
        "📋 Disclosure Class",
        "🎯 Credit Concentration",
        "⏱️ Maturity Buckets",
        "📅 Bucket Classifier",
        "📈 Market Risk Sensitivity",
        "🔗 Hedge Disclosure Pack",
        "✅ Completeness Check",
    ])

    # ────────── 1. Validate Disclosure Class ──────────
    with ifrs7_sections[0]:
        st.markdown("### Validate Disclosure Class")
        st.caption(
            "Per IFRS 7 §6 — entity must disclose financial instruments by "
            "class. Valid categories per IFRS 7 §B1-B3."
        )

        c1, c2 = st.columns(2)
        with c1:
            cat = st.selectbox("Disclosure category:",
                ["SIGNIFICANCE_TO_FINANCIAL_POSITION",
                 "NATURE_AND_EXTENT_OF_RISKS",
                 "QUANTITATIVE_RISK_DATA",
                 "INVALID_CATEGORY"],
                key="ifrs7_validate_cat")
        result = IFRS7DisclosureEngine.validate_disclosure_class(cat)
        with c2:
            st.markdown("**Engine output:**")
            st.json(result)

        st.markdown("**IFRS 7 reference:** §6 — class disclosures must reflect "
                    "the entity's measurement categories.")

    # ────────── 2. Credit Risk Concentration ──────────
    with ifrs7_sections[1]:
        st.markdown("### Credit Risk Concentration")
        st.caption(
            "Per IFRS 7 §B8 — disclosures of credit risk concentration by "
            "single counterparty, geography, sector, etc. Concentration "
            "above 10% (single name) or 25% (sector) typically triggers "
            "explicit disclosure."
        )

        c1, c2 = st.columns(2)
        with c1:
            exposure_kes = st.number_input(
                "Exposure amount (KES)",
                min_value=0, value=15_000_000_000,  # 15B default
                step=1_000_000_000, key="ifrs7_conc_exp")
            total_exp_kes = st.number_input(
                "Total portfolio exposure (KES)",
                min_value=0, value=100_000_000_000,  # 100B default
                step=10_000_000_000, key="ifrs7_conc_total")
            conc_type = st.selectbox(
                "Concentration type:",
                ["SINGLE_COUNTERPARTY", "GEOGRAPHIC", "SECTOR",
                 "PRODUCT_TYPE", "INSTRUMENT_TYPE"],
                key="ifrs7_conc_type")

        result = IFRS7DisclosureEngine.credit_risk_concentration(
            exposure_amount=Decimal(str(exposure_kes)),
            total_exposure=Decimal(str(total_exp_kes)),
            concentration_type=conc_type,
        )

        with c2:
            st.markdown("**Engine output:**")
            st.json(result)

        st.markdown("**IFRS 7 reference:** §B8 — concentrations of credit "
                    "risk must be disclosed when the financial assets share "
                    "common characteristics that would cause their ability "
                    "to meet obligations to be similarly affected.")

    # ────────── 3. Liquidity Maturity Buckets ──────────
    with ifrs7_sections[2]:
        st.markdown("### Liquidity Maturity Buckets")
        st.caption(
            "Per IFRS 7 §39 — bank must disclose remaining contractual "
            "maturity for financial liabilities. 6 standard buckets: "
            "On Demand / 0-30 days / 31-90 days / 91-365 days / 1-5 years "
            "/ Over 5 years."
        )

        st.markdown("**Cash flows by days-to-maturity:**")
        c1, c2 = st.columns(2)
        with c1:
            on_demand_kes = st.number_input(
                "On-demand amount (KES)",
                min_value=0, value=20_000_000_000,
                step=1_000_000_000, key="ifrs7_liq_demand")
            cf_30d_kes = st.number_input(
                "Cash flow 30 days (KES)",
                min_value=0, value=15_000_000_000,
                step=1_000_000_000, key="ifrs7_liq_30")
            cf_60d_kes = st.number_input(
                "Cash flow 60 days (KES)",
                min_value=0, value=10_000_000_000,
                step=1_000_000_000, key="ifrs7_liq_60")
        with c2:
            cf_180d_kes = st.number_input(
                "Cash flow 180 days (KES)",
                min_value=0, value=8_000_000_000,
                step=1_000_000_000, key="ifrs7_liq_180")
            cf_2yr_kes = st.number_input(
                "Cash flow 2 years (KES)",
                min_value=0, value=25_000_000_000,
                step=1_000_000_000, key="ifrs7_liq_2y")
            cf_10yr_kes = st.number_input(
                "Cash flow 10 years (KES)",
                min_value=0, value=12_000_000_000,
                step=1_000_000_000, key="ifrs7_liq_10y")

        cash_flows = [
            (30, Decimal(str(cf_30d_kes))),
            (60, Decimal(str(cf_60d_kes))),
            (180, Decimal(str(cf_180d_kes))),
            (730, Decimal(str(cf_2yr_kes))),  # 2 years
            (3650, Decimal(str(cf_10yr_kes))),  # 10 years
        ]
        result = IFRS7DisclosureEngine.liquidity_maturity_buckets(
            cash_flows=cash_flows,
            on_demand_amount=Decimal(str(on_demand_kes)),
        )

        st.markdown("**Engine output:**")
        st.json(result)

        st.markdown("**IFRS 7 reference:** §39(a) — maturity analysis for "
                    "non-derivative financial liabilities showing remaining "
                    "contractual maturities.")

    # ────────── 4. Maturity Bucket Classifier ──────────
    with ifrs7_sections[3]:
        st.markdown("### Maturity Bucket Classifier (single instrument)")
        st.caption(
            "Helper that classifies a single instrument's days-to-maturity "
            "into one of the 6 IFRS 7 buckets."
        )

        c1, c2 = st.columns(2)
        with c1:
            on_demand = st.checkbox("On-demand instrument?", value=False,
                key="ifrs7_class_demand")
            days_to_mat = st.number_input(
                "Days to maturity:",
                min_value=0, value=120, key="ifrs7_class_days",
                disabled=on_demand)

        bucket = IFRS7DisclosureEngine.classify_maturity_bucket(
            days_to_maturity=None if on_demand else int(days_to_mat),
            on_demand=on_demand)

        with c2:
            st.markdown(f"**Bucket:** `{bucket}`")

        st.markdown("**5 IFRS 7 buckets (engine values):**")
        st.markdown("""
| Bucket | Range |
|---|---|
| ON_DEMAND | callable on demand |
| UP_TO_3_MONTHS | 0-90 days |
| THREE_TO_12_MONTHS | 91-365 days |
| ONE_TO_5_YEARS | 366-1825 days |
| OVER_5_YEARS | >1825 days |

**Note:** engine returns IFRS 7 §39-style band names. The exact strings
above match what `classify_maturity_bucket()` returns; the
`liquidity_maturity_buckets()` aggregator uses the same band names
internally.
        """)

    # ────────── 5. Market Risk Sensitivity ──────────
    with ifrs7_sections[4]:
        st.markdown("### Market Risk Sensitivity Analysis")
        st.caption(
            "Per IFRS 7 §40 — bank must disclose sensitivity of P&L / equity "
            "to reasonably possible changes in each market risk variable "
            "(interest rate, FX rate, equity price, commodity price)."
        )

        c1, c2 = st.columns(2)
        with c1:
            risk_var = st.selectbox(
                "Risk variable:",
                ["INTEREST_RATE", "FX_RATE", "EQUITY_PRICE",
                 "COMMODITY_PRICE", "INVALID"],
                key="ifrs7_market_var")
            exposure_kes = st.number_input(
                "Exposure (KES)",
                min_value=0, value=10_000_000_000,
                step=1_000_000_000, key="ifrs7_market_exp")
            sensitivity_pct = st.number_input(
                "Sensitivity change (%, e.g. 1.0 for 1%)",
                value=1.0, step=0.5, key="ifrs7_market_sens")

        result = IFRS7DisclosureEngine.market_risk_sensitivity(
            risk_variable=risk_var,
            exposure=Decimal(str(exposure_kes)),
            sensitivity_change_pct=Decimal(str(sensitivity_pct)),
        )

        with c2:
            st.markdown("**Engine output:**")
            st.json(result)

        st.markdown("**IFRS 7 reference:** §40 — for each type of market "
                    "risk, sensitivity analysis showing how P&L and equity "
                    "would have been affected by reasonably possible changes "
                    "in the relevant risk variable.")

    # ────────── 6. Hedge Disclosure Pack ──────────
    with ifrs7_sections[5]:
        st.markdown("### Hedge Accounting Disclosure Pack")
        st.caption(
            "Per IFRS 7 §22A-24G — when hedge accounting is applied, the "
            "entity must disclose strategy, the carrying amount of hedging "
            "instruments, hedged items, hedge ineffectiveness, and the "
            "gains/losses recognised in P&L or OCI."
        )

        hedge_type = st.selectbox(
            "Hedge type:",
            ["FAIR_VALUE_HEDGE", "CASH_FLOW_HEDGE",
             "NET_INVESTMENT_HEDGE", "INVALID_HEDGE"],
            key="ifrs7_hedge_type")
        result = IFRS7DisclosureEngine.hedge_disclosure_pack(hedge_type)
        st.markdown("**Engine output (required disclosure items):**")
        st.json(result)

        st.markdown("**IFRS 7 reference:** §22A-24G — hedge accounting "
                    "disclosures vary by hedge type. Fair-value hedges affect "
                    "P&L; cash-flow hedges affect OCI then reclass to P&L; "
                    "net-investment hedges affect translation reserve.")

    # ────────── 7. Disclosure Completeness ──────────
    with ifrs7_sections[6]:
        st.markdown("### Disclosure Completeness Check")
        st.caption(
            "Helper that compares a provided set of disclosures against "
            "the required set. Returns missing items + completeness %. "
            "Useful for IFRS 7 compliance dashboards."
        )

        # Default required set per IFRS 7
        default_required = [
            "credit_risk_concentration",
            "liquidity_maturity_buckets",
            "market_risk_sensitivity",
            "hedge_accounting_pack",
            "fair_value_hierarchy",
            "transferred_assets_pack",
            "offsetting_pack",
        ]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Required (IFRS 7 default):**")
            for item in default_required:
                st.markdown(f"- `{item}`")
            provided_input = st.text_area(
                "Provided disclosures (one per line):",
                value="\n".join(default_required[:5]),  # 5 of 7
                height=180, key="ifrs7_complete_provided")

        provided = [p.strip() for p in provided_input.splitlines() if p.strip()]
        result = IFRS7DisclosureEngine.disclosure_completeness(
            required_set=default_required,
            provided_set=provided,
        )

        with c2:
            st.markdown("**Engine output:**")
            st.json(result)

        st.markdown("**Tip:** clear the text area to see the engine flag all "
                    "items as missing. Caller decides what counts as 'required' "
                    "per their disclosure context.")

    st.divider()
    st.info(
        "💡 **v7.9 alignment with v7.1 plan**: this page completes the "
        "triple-page Credit Risk depth campaign — page 19 surfaced PD/LGD/EAD "
        "scoring, page 32 surfaced IFRS 9 classification, **page 88 here "
        "surfaces IFRS 7 disclosures**. Combined with the existing 4 engine "
        "tabs (Tax #97, Procurement #98, Financial Close #99) this page is "
        "now the platform's Engine Studio — every Cat B engine is "
        "interactively explorable. Next: the L05 Card usage loop closure "
        "would add a `cards` engine + Card surfacing."
    )

    audit_log("IFRS_ENGINE_USED", uname,
              f"v7.9 IFRS 7 Disclosures Engine sub-tab opened")


# ============================================================================
# TAB 5 — About (was tab 4 before v7.9)
# ============================================================================
with engine_tabs[4]:
    st.markdown("#### About this page")
    st.markdown("""
This page is the **first integration** between the A2Z standards library
(116 deterministic engines built in v5.53–v5.70) and the live deployed Streamlit
application. Three engines are surfaced live as interactive tools:

| Standard | Engine | Audit Gate |
|---|---|---|
| #97 Tax & VAT Compliance (Cat B, KRA Tax Procedures Act) | `TaxComplianceEngine` | G89 ✅ |
| #98 Procurement Workflow (Cat B, 5-tier approvals + 3-way match) | `ProcurementWorkflowEngine` | G90 ✅ |
| #99 Financial Close (Cat B, T+N milestones + materiality + signoff) | `FinancialCloseEngine` | G91 ✅ |

Every computation goes through the same audited code that passes audit gates
**G89, G90, G91** in the platform's audit run (currently **103/103 gates passing**
in v5.70). All literal thresholds (VAT 16%, corporate 30%, tier limits in KES,
materiality 0.1%, etc.) are byte-for-byte bound to KRA / IFRS / internal policy.

**Why this page matters:** until v5.71, the 116 standards lived in
`utils/` as an independent library and were tested only by the audit script.
This page demonstrates that the engines are **callable from the live UI**,
that operations and finance teams can use them on real inputs, and that every
use is **audit-logged** (`IFRS_ENGINE_USED` events visible in the audit trail).

**Honesty discipline preserved:** every engine returns `None` when inputs are
missing (Rule 1) and surfaces unknown categories or out-of-range values
(Rule 6) — no silent defaults. Decimal precision is 28 digits throughout.

**What's next** — Volumes 25+ will integrate additional engines into existing
operational pages (e.g. surfacing impairment indicators on the credit
monitoring page, related-party flags on the customer 360 page).
    """)

    st.markdown("---")
    st.caption("v5.71 · IFRS Engines Studio · Standards #97-#99 live")
