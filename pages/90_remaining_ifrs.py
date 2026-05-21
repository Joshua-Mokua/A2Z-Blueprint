"""pages/90_remaining_ifrs.py — Remaining IFRS Engines Studio (v5.77).

Third dedicated integration page wiring 7 IFRS standards in one batch:

    • IFRS 9  Classification (SPPI test, business model, debt/equity classification)
    • IAS 8   Accounting Policies, Changes in Estimates, Errors
    • IFRS 16 Lease Accounting (classification, ROU asset, liability amortization)
    • IAS 12  Income Taxes (deferred tax, DTA recoverability, total tax expense)
    • IFRS 10 Group Consolidation (subsidiary classification, NCI, currency translation)
    • IAS 37  Provisions, Contingent Liabilities and Contingent Assets
    • IFRS 15 Revenue from Contracts with Customers (5-step model)

Companion to:
    • 88_ifrs_engines.py  (Tax #97 / Procurement #98 / Financial Close #99)
    • 89_capital_risk_engines.py (IRRBB #74 / Investment #76 / Capital Adequacy #77 / Credit Risk #53)

Together the 3 dedicated pages cover **17 standards** library-to-UI; an additional
9 are surfaced via in-flow tab injection on existing pages, bringing the cumulative
integration tally to **23 of 116** after v5.77.
"""
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

from decimal import Decimal, InvalidOperation
import pandas as pd
from pages._shared import load_shared_state
from pages._access import require_access
from utils.config import currency_symbol
from utils.core_audit import audit_log

# Engine imports
from utils.ifrs9_classification import (
    IFRS9ClassificationEngine,
    BUSINESS_MODELS, INSTRUMENT_TYPES, MEASUREMENT_CATEGORIES,
)
from utils.ias8_policies import (
    IAS8PoliciesEngine,
    CHANGE_TYPES, POLICY_CHANGE_TRIGGERS, ESTIMATE_CHANGE_REASONS,
    APPLICATION_METHODS, ERROR_PRESENTATION_OUTCOMES,
    PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY,
    PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT,
)
from utils.lease_accounting import (
    LeaseAccountingEngine,
    LEASE_CLASSIFICATIONS, MODIFICATION_TYPES,
    ROU_DEPRECIATION_METHODS,
    SHORT_TERM_MAX_MONTHS, LOW_VALUE_THRESHOLD_USD,
)
from utils.deferred_tax import (
    DeferredTaxEngine,
    TEMPORARY_DIFFERENCE_TYPES,
    DEFERRED_TAX_RECOGNITION_OUTCOMES,
    PROFIT_OR_LOSS_ALLOCATION_BUCKETS,
)
from utils.group_consolidation import (
    GroupConsolidationEngine,
    CONSOLIDATION_METHODS, CURRENCY_TRANSLATION_METHODS,
    ELIMINATION_TYPES, SUBSIDIARY_TYPES,
    CONTROL_THRESHOLD_PCT, SIGNIFICANT_INFLUENCE_THRESHOLD_PCT,
    WHOLLY_OWNED_THRESHOLD_PCT,
)
from utils.provisions import (
    ProvisionsEngine,
    PROBABILITY_LEVELS, PROVISION_TYPES, EXPECTED_VALUE_METHODS,
    POSSIBLE_PCT_MIN, PROBABLE_PCT_MIN, VIRTUALLY_CERTAIN_PCT_MIN,
)
from utils.revenue_recognition import (
    RevenueRecognitionEngine,
    CONTRACT_CRITERIA, OVER_TIME_CRITERIA,
    RECOGNITION_PATTERNS, IFRS_15_STEPS,
    INDICATORS_OF_CONTROL_TRANSFER,
    VARIABLE_CONSIDERATION_TYPES,
)

require_access("credit.ifrs_extended")

um, ud, uname, *_ = load_shared_state()[:12]


# ── Header ────────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:24px;background:linear-gradient(135deg,#1E40AF 0%,#3B82F6 100%);"
    "border-radius:16px;color:white;margin-bottom:20px'>"
    "<div style='font-size:13px;letter-spacing:2px;opacity:0.85'>STANDARDS LIBRARY · LIVE</div>"
    "<div style='font-size:28px;font-weight:800;margin-top:6px'>Remaining IFRS Engines Studio</div>"
    "<div style='font-size:14px;opacity:0.9;margin-top:8px'>"
    "Seven IFRS standards covering classification, leases, taxes, consolidation, "
    "provisions, revenue recognition, and accounting policy changes. "
    "Each tab is a deterministic engine bound byte-for-byte to its standard.</div></div>",
    unsafe_allow_html=True,
)

engine_tabs = st.tabs([
    "📐 IFRS 9 Classify",
    "📋 IAS 8 Policies",
    "🏢 IFRS 16 Leases",
    "💸 IAS 12 Deferred Tax",
    "🏛️ IFRS 10 Consolidation",
    "🛡️ IAS 37 Provisions",
    "💰 IFRS 15 Revenue",
])


def _to_decimal(val, default=None):
    """Safely coerce to Decimal."""
    if val is None or val == "":
        return default
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


# ============================================================================
# TAB 0 — IFRS 9 Classification
# ============================================================================
with engine_tabs[0]:
    st.markdown("#### IFRS 9 Financial Instruments — Classification Engine")
    st.caption(
        "Classification of financial assets per IFRS 9.4.1: SPPI test "
        "(Solely Payments of Principal and Interest) + business model assessment. "
        "Outputs one of 5 measurement categories: AMORTIZED_COST, FVTOCI_DEBT, "
        "FVTPL, FVTOCI_EQUITY, FVTPL_EQUITY."
    )

    sub_tabs = st.tabs([
        "🔬 SPPI Test",
        "🎯 Debt Classification",
        "📈 Equity Classification",
        "🔄 Reclassification",
    ])

    with sub_tabs[0]:
        st.markdown("**SPPI Test** (Solely Payments of Principal and Interest)")
        st.caption(
            "A debt instrument passes SPPI if its contractual cash flows are "
            "solely payments of principal and interest on the principal outstanding. "
            "Leverage, equity-linked features, and certain options FAIL SPPI."
        )
        passed = st.radio("SPPI test outcome",
                           ["Pass", "Fail"], horizontal=True, key="ifrs9_sppi")
        if st.button("Record SPPI result", key="ifrs9_sppi_btn", type="primary"):
            r = IFRS9ClassificationEngine.sppi_test(
                passed=(passed == "Pass"))
            if r.get("computed"):
                if r.get("sppi_passed"):
                    st.success("✅ SPPI passed — debt instrument may qualify "
                                "for AMORTIZED_COST or FVTOCI_DEBT.")
                else:
                    st.error("⛔ SPPI failed — instrument MUST be measured at FVTPL "
                              "(IFRS 9.4.1.4 default).")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS9 Classify: SPPI {passed}")

    with sub_tabs[1]:
        st.markdown("**Debt Instrument Classification** (combines SPPI + business model)")
        c1, c2 = st.columns(2)
        with c1:
            bm = st.selectbox("Business model",
                                list(BUSINESS_MODELS), key="ifrs9_bm")
        with c2:
            sppi = st.radio("SPPI test", ["Pass", "Fail"],
                              horizontal=True, key="ifrs9_dc_sppi")
        if st.button("Classify debt instrument",
                       key="ifrs9_dc_btn", type="primary"):
            r = IFRS9ClassificationEngine.classify_debt_instrument(
                business_model=bm, sppi_passed=(sppi == "Pass"))
            if r.get("computed"):
                cat = r.get("category")
                colors = {
                    "AMORTIZED_COST": "#10B981",
                    "FVTOCI_DEBT": "#3B82F6",
                    "FVTPL": "#F59E0B",
                }
                color = colors.get(cat, "#6B7280")
                st.markdown(
                    f"<div style='padding:18px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"MEASUREMENT CATEGORY</div>"
                    f"<div style='font-size:28px;font-weight:800;color:{color}'>{cat}</div>"
                    f"<div style='font-size:13px;margin-top:6px'>"
                    f"{r.get('rationale', '').replace('_', ' ')}</div></div>",
                    unsafe_allow_html=True)
                method = IFRS9ClassificationEngine.measurement_method(cat)
                if method:
                    st.caption(f"Subsequent measurement: **{method.replace('_', ' ')}**")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS9 Classify: debt bm={bm}, sppi={sppi} → {cat}")

    with sub_tabs[2]:
        st.markdown("**Equity Instrument Classification**")
        st.caption(
            "Equity instruments default to FVTPL_EQUITY. An entity may make an "
            "**irrevocable election** at initial recognition to present subsequent "
            "fair value changes in OCI (FVTOCI_EQUITY). NOT available for held-for-trading."
        )
        c1, c2 = st.columns(2)
        with c1:
            elect = st.checkbox("FVTOCI election (irrevocable per IFRS 9.4.1.4)",
                                  key="ifrs9_eq_elect")
        with c2:
            hft = st.checkbox("Held for trading", key="ifrs9_eq_hft")
        if st.button("Classify equity instrument",
                       key="ifrs9_eq_btn", type="primary"):
            r = IFRS9ClassificationEngine.classify_equity_instrument(
                fvtoci_election=elect, held_for_trading=hft)
            if r.get("computed"):
                cat = r.get("category")
                color = "#3B82F6" if cat == "FVTOCI_EQUITY" else "#F59E0B"
                st.markdown(
                    f"<div style='padding:18px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"MEASUREMENT CATEGORY</div>"
                    f"<div style='font-size:28px;font-weight:800;color:{color}'>{cat}</div>"
                    f"<div style='font-size:13px;margin-top:6px'>"
                    f"{r.get('rationale', '').replace('_', ' ')}</div></div>",
                    unsafe_allow_html=True)
                if cat == "FVTOCI_EQUITY":
                    st.warning(
                        "ℹ Reminder: FVTOCI_EQUITY changes are **NEVER recycled** "
                        "to P&L (per IFRS 9.5.7.5 — different from FVTOCI_DEBT).")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS9 Classify: equity FVTOCI={elect} HFT={hft} → {cat}")

    with sub_tabs[3]:
        st.markdown("**Reclassification Eligibility** (IFRS 9.4.4)")
        st.caption(
            "Reclassification of debt instruments is allowed ONLY when the entity "
            "changes its business model. Reclassification of equity instruments "
            "is NEVER permitted."
        )
        c1, c2 = st.columns(2)
        with c1:
            old_bm = st.selectbox("Old business model",
                                    list(BUSINESS_MODELS), key="ifrs9_rc_old")
        with c2:
            new_bm = st.selectbox("New business model",
                                    list(BUSINESS_MODELS), key="ifrs9_rc_new",
                                    index=1)
        if st.button("Check reclassification",
                       key="ifrs9_rc_btn", type="primary"):
            r = IFRS9ClassificationEngine.reclassification_allowed(
                old_business_model=old_bm, new_business_model=new_bm)
            if r.get("computed"):
                if r.get("allowed"):
                    st.success(
                        f"✅ Reclassification ALLOWED from {old_bm} to {new_bm}. "
                        "Apply prospectively from reclassification date.")
                else:
                    st.warning(
                        f"⚠ Reclassification not applicable — same business model.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS9 Classify: reclass {old_bm}→{new_bm} "
                           f"allowed={r.get('allowed')}")


# ============================================================================
# TAB 1 — IAS 8 Policies
# ============================================================================
with engine_tabs[1]:
    st.markdown("#### IAS 8 — Accounting Policies, Changes in Estimates, and Errors")
    st.caption(
        f"Three change types: {' / '.join(CHANGE_TYPES)}. Materiality thresholds for "
        f"prior-period errors: {PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY}% of equity, "
        f"{PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT}% of profit."
    )

    sub_tabs = st.tabs([
        "🔍 Change Type Classifier",
        "🔬 Error Materiality Test",
        "🛠️ Application Method",
    ])

    with sub_tabs[0]:
        st.markdown("**Classify the change** (per IAS 8.5)")
        change = st.selectbox("Change type", list(CHANGE_TYPES),
                                key="ias8_change")
        if st.button("Validate change type",
                       key="ias8_change_btn", type="primary"):
            r = IAS8PoliciesEngine.classify_change_type(change)
            if r.get("valid"):
                st.success(f"✅ Valid change type: **{change}**")
                # Application method
                am = IAS8PoliciesEngine.required_application_method(change)
                if am.get("computed"):
                    method = am.get("method")
                    method_descriptions = {
                        "RETROSPECTIVE": "Apply as if the new policy had always been applied. Restate comparatives.",
                        "PROSPECTIVE": "Apply only to current and future periods. Comparatives NOT restated.",
                        "RESTATEMENT": "Restate prior period(s) where the error occurred.",
                    }
                    st.info(
                        f"**Required application method:** `{method}` — "
                        f"{method_descriptions.get(method, '')}")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS8: classify {change} → valid")
            else:
                st.error(f"⛔ {r.get('reason')}")

    with sub_tabs[1]:
        st.markdown("**Prior-Period Error Materiality Test** (IAS 8.41)")
        st.caption(
            f"Material if error ≥ {PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_PROFIT}% of "
            f"prior-period profit OR ≥ {PRIOR_PERIOD_ERROR_MATERIALITY_PCT_OF_EQUITY}% "
            "of prior-period equity."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            err_amt = st.number_input(f"Error amount ({currency_symbol()} M)",
                                        min_value=0.0, value=100.0, step=10.0,
                                        key="ias8_err")
        with c2:
            prof = st.number_input(f"Prior-period profit ({currency_symbol()} M)",
                                     min_value=0.0, value=1000.0, step=100.0,
                                     key="ias8_prof")
        with c3:
            eq = st.number_input(f"Prior-period equity ({currency_symbol()} M)",
                                   min_value=0.0, value=10000.0, step=100.0,
                                   key="ias8_eq")
        if st.button("Test materiality",
                       key="ias8_mat_btn", type="primary"):
            r = IAS8PoliciesEngine.error_materiality_test(
                error_amount=_to_decimal(err_amt) * Decimal("1000000"),
                prior_period_profit=_to_decimal(prof) * Decimal("1000000"),
                prior_period_equity=_to_decimal(eq) * Decimal("1000000"))
            if r.get("computed"):
                material = r.get("material")
                outcome = r.get("outcome")
                pct_p = r.get("pct_of_profit")
                pct_e = r.get("pct_of_equity")
                k1, k2, k3 = st.columns(3)
                k1.metric("% of profit", f"{pct_p}%")
                k2.metric("% of equity", f"{pct_e}%")
                with k3:
                    color = "#DC2626" if material else "#10B981"
                    label = "MATERIAL" if material else "NOT MATERIAL"
                    st.markdown(
                        f"<div style='padding:8px 12px;background:{color}22;"
                        f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                        f"<div style='font-size:18px;font-weight:800;color:{color}'>"
                        f"{label}</div></div>", unsafe_allow_html=True)
                if material:
                    st.error(
                        f"⛔ Error is MATERIAL — outcome: **{outcome.replace('_', ' ')}**. "
                        f"Restate comparative amounts in current-period financial statements "
                        "per IAS 8.42.")
                else:
                    st.success(
                        "✅ Error not material — disclosure may not be required, "
                        "but document the assessment.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS8: error 100M test material={material}")

    with sub_tabs[2]:
        st.markdown("**Required Application Method by Change Type**")
        rows = []
        method_details = {
            "RETROSPECTIVE": "Apply as if always-applied; restate comparatives",
            "PROSPECTIVE": "Apply current/future only; no restatement",
            "RESTATEMENT": "Restate prior period(s) where error occurred",
        }
        for ct in CHANGE_TYPES:
            r = IAS8PoliciesEngine.required_application_method(ct)
            method = r.get("method", "—") if r.get("computed") else "—"
            rows.append({
                "Change type": ct.replace("_", " ").title(),
                "Application method": method,
                "Effect": method_details.get(method, "—"),
            })
        st.dataframe(pd.DataFrame(rows),
                     use_container_width=True, hide_index=True)


# ============================================================================
# TAB 2 — IFRS 16 Leases
# ============================================================================
with engine_tabs[2]:
    st.markdown("#### IFRS 16 — Leases")
    st.caption(
        f"Lease classifications: {' / '.join(LEASE_CLASSIFICATIONS)}. "
        f"Short-term threshold: ≤{SHORT_TERM_MAX_MONTHS} months. "
        f"Low-value threshold: ≤USD {LOW_VALUE_THRESHOLD_USD}."
    )

    sub_tabs = st.tabs([
        "🏷️ Classify",
        "📊 Liability Initial PV",
        "🏗️ ROU Asset",
        "📉 Liability Amortization",
    ])

    with sub_tabs[0]:
        st.markdown("**Classify the lease** (per IFRS 16.5-6)")
        c1, c2 = st.columns(2)
        with c1:
            term = st.number_input("Lease term (months)",
                                     min_value=1, value=24, step=1,
                                     key="lease_term")
        with c2:
            asset_usd = st.number_input("Asset value when new (USD)",
                                          min_value=0.0, value=10000.0, step=500.0,
                                          key="lease_asset_usd",
                                          help=f"Threshold: ≤USD {LOW_VALUE_THRESHOLD_USD}.")
        if st.button("Classify lease", key="lease_class_btn", type="primary"):
            cls = LeaseAccountingEngine.lease_classification(
                term_months=int(term),
                asset_value_when_new_usd=_to_decimal(asset_usd))
            if cls:
                colors = {"SHORT_TERM": "#3B82F6", "LOW_VALUE": "#10B981",
                          "STANDARD": "#F59E0B"}
                color = colors.get(cls, "#6B7280")
                st.markdown(
                    f"<div style='padding:18px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"CLASSIFICATION</div>"
                    f"<div style='font-size:28px;font-weight:800;color:{color}'>{cls}</div></div>",
                    unsafe_allow_html=True)
                if cls in ("SHORT_TERM", "LOW_VALUE"):
                    st.success(
                        f"✅ Eligible for **expense-as-incurred recognition** "
                        f"(IFRS 16.5). Lessee may elect not to recognise ROU asset / liability.")
                else:
                    st.info(
                        "ℹ STANDARD lease — ROU asset + lease liability recognition required "
                        "per IFRS 16.22-26.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS16: classify {term}mo USD{asset_usd} → {cls}")

    with sub_tabs[1]:
        st.markdown("**Initial Lease Liability** = Σ PV of lease payments")
        c1, c2, c3 = st.columns(3)
        with c1:
            pmt = st.number_input(f"Monthly payment ({currency_symbol()})",
                                    min_value=0.0, value=100000.0, step=10000.0,
                                    key="lease_pmt")
        with c2:
            term2 = st.number_input("Term (months)",
                                      min_value=1, value=60, step=1,
                                      key="lease_pv_term")
        with c3:
            rate = st.number_input("Annual rate (%)",
                                     min_value=0.0, value=8.0, step=0.5,
                                     key="lease_rate",
                                     help="Implicit rate or incremental borrowing rate.")
        if st.button("Compute initial liability",
                       key="lease_pv_btn", type="primary"):
            r = LeaseAccountingEngine.lease_liability_initial(
                monthly_payment=_to_decimal(pmt),
                term_months=int(term2),
                annual_rate_pct=_to_decimal(rate))
            if r.get("computed"):
                pv = _to_decimal(r["pv"])
                k1, k2 = st.columns(2)
                k1.metric("Initial liability (PV)",
                           f"{currency_symbol()} {pv:,.2f}")
                undiscounted = _to_decimal(pmt) * Decimal(str(term2))
                k2.metric("Undiscounted total",
                           f"{currency_symbol()} {undiscounted:,.2f}",
                           delta=f"-{(undiscounted - pv):,.2f} discount")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS16: liability_pv pmt={pmt} term={term2}mo @ {rate}% → {pv}")

    with sub_tabs[2]:
        st.markdown("**Right-of-Use Asset** = Liability + Initial costs − Incentives")
        c1, c2, c3 = st.columns(3)
        with c1:
            liab = st.number_input(f"Lease liability ({currency_symbol()})",
                                     min_value=0.0, value=4928000.0, step=10000.0,
                                     key="rou_liab")
        with c2:
            idc = st.number_input(f"Initial direct costs ({currency_symbol()})",
                                    min_value=0.0, value=100000.0, step=5000.0,
                                    key="rou_idc",
                                    help="e.g. legal fees, commissions paid to negotiate the lease.")
        with c3:
            incentives = st.number_input(f"Lease incentives received ({currency_symbol()})",
                                           min_value=0.0, value=50000.0, step=5000.0,
                                           key="rou_inc",
                                           help="Cash or in-kind incentives from the lessor.")
        if st.button("Compute ROU asset", key="rou_btn", type="primary"):
            r = LeaseAccountingEngine.rou_asset_initial(
                lease_liability=_to_decimal(liab),
                initial_direct_costs=_to_decimal(idc),
                lease_incentives=_to_decimal(incentives))
            if r.get("computed"):
                rou = _to_decimal(r["rou"])
                st.metric("Initial ROU asset",
                           f"{currency_symbol()} {rou:,.2f}",
                           help="= liability + IDC - incentives")
                st.caption(
                    f"Built from: liability {liab:,.0f} + IDC {idc:,.0f} - "
                    f"incentives {incentives:,.0f}")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS16: ROU = {rou}")

    with sub_tabs[3]:
        st.markdown("**Liability Amortization** (single-period split)")
        st.caption(
            "Each payment splits between interest expense (P&L) and "
            "principal reduction (reduces liability)."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            opening = st.number_input(f"Opening liability ({currency_symbol()})",
                                         min_value=0.0, value=4928000.0,
                                         step=10000.0, key="amort_opening")
        with c2:
            pmt2 = st.number_input(f"Monthly payment ({currency_symbol()})",
                                     min_value=0.0, value=100000.0, step=5000.0,
                                     key="amort_pmt")
        with c3:
            rate2 = st.number_input("Annual rate (%)",
                                      min_value=0.0, value=8.0, step=0.5,
                                      key="amort_rate")
        if st.button("Compute amortization", key="amort_btn", type="primary"):
            r = LeaseAccountingEngine.lease_liability_amortization(
                opening_liability=_to_decimal(opening),
                monthly_payment=_to_decimal(pmt2),
                annual_rate_pct=_to_decimal(rate2))
            if r.get("computed"):
                k1, k2, k3 = st.columns(3)
                k1.metric("Interest portion",
                           f"{currency_symbol()} {_to_decimal(r['interest_portion']):,.2f}")
                k2.metric("Principal portion",
                           f"{currency_symbol()} {_to_decimal(r['principal_portion']):,.2f}")
                k3.metric("Closing liability",
                           f"{currency_symbol()} {_to_decimal(r['closing_liability']):,.2f}")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS16: amort opening={opening} pmt={pmt2}")


# ============================================================================
# TAB 3 — IAS 12 Deferred Tax
# ============================================================================
with engine_tabs[3]:
    st.markdown("#### IAS 12 — Income Taxes (Deferred)")
    st.caption(
        f"Temporary difference types: {' / '.join(TEMPORARY_DIFFERENCE_TYPES)}. "
        f"Deferred tax = TD × enacted rate. DTA recognised only when future taxable "
        "profit is probable per IAS 12.34."
    )

    sub_tabs = st.tabs([
        "📐 Temporary Difference",
        "🧮 Deferred Tax Computation",
        "🔍 DTA Recoverability",
        "💰 Total Tax Expense",
    ])

    with sub_tabs[0]:
        st.markdown("**Temporary Difference** = Carrying amount − Tax base")
        c1, c2 = st.columns(2)
        with c1:
            ca = st.number_input(f"Carrying amount ({currency_symbol()})",
                                   min_value=0.0, value=100000.0, step=1000.0,
                                   key="td_ca")
        with c2:
            tb = st.number_input(f"Tax base ({currency_symbol()})",
                                   min_value=0.0, value=60000.0, step=1000.0,
                                   key="td_tb")
        if st.button("Compute TD", key="td_btn", type="primary"):
            r = DeferredTaxEngine.temporary_difference(
                carrying_amount=_to_decimal(ca), tax_base=_to_decimal(tb))
            if r.get("computed"):
                td = _to_decimal(r["temporary_difference"])
                cls = DeferredTaxEngine.classify_temporary_difference(td)
                color = "#DC2626" if cls == "TAXABLE" else "#10B981"
                k1, k2 = st.columns(2)
                k1.metric("Temporary difference", f"{currency_symbol()} {td:,.2f}")
                with k2:
                    st.markdown(
                        f"<div style='padding:8px 12px;background:{color}22;"
                        f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"CLASSIFICATION</div>"
                        f"<div style='font-size:18px;font-weight:800;color:{color}'>"
                        f"{cls}</div></div>", unsafe_allow_html=True)
                if cls == "TAXABLE":
                    st.info("ℹ TAXABLE TD → gives rise to a **deferred tax LIABILITY**.")
                else:
                    st.info("ℹ DEDUCTIBLE TD → may give rise to a **deferred tax ASSET** "
                              "(subject to recoverability test).")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS12: TD CA={ca} TB={tb} → {td} ({cls})")

    with sub_tabs[1]:
        st.markdown("**Deferred Tax** = TD × enacted rate")
        c1, c2 = st.columns(2)
        with c1:
            td_amt = st.number_input(f"Temporary difference ({currency_symbol()})",
                                       value=40000.0, step=1000.0, key="dt_td")
        with c2:
            rate_dt = st.number_input("Enacted tax rate (%)",
                                        min_value=0.0, value=30.0, step=1.0,
                                        key="dt_rate")
        if st.button("Compute deferred tax", key="dt_btn", type="primary"):
            r = DeferredTaxEngine.deferred_tax(
                temporary_difference=_to_decimal(td_amt),
                enacted_tax_rate_pct=_to_decimal(rate_dt))
            if r.get("computed"):
                dt = _to_decimal(r["deferred_tax"])
                cls = r.get("classification")
                color = "#DC2626" if "LIABILITY" in cls else "#10B981"
                k1, k2 = st.columns(2)
                k1.metric("Deferred tax", f"{currency_symbol()} {dt:,.2f}")
                with k2:
                    st.markdown(
                        f"<div style='padding:8px 12px;background:{color}22;"
                        f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                        f"<div style='font-size:18px;font-weight:800;color:{color}'>"
                        f"{cls.replace('_', ' ')}</div></div>", unsafe_allow_html=True)
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS12: deferred_tax TD={td_amt} @ {rate_dt}% → {dt} ({cls})")

    with sub_tabs[2]:
        st.markdown("**DTA Recoverability** (IAS 12.34)")
        st.caption(
            "DTA is recognised only to the extent that future taxable profits "
            "will be available against which deductible TDs can be utilised. "
            "Engine requires the input TD to be **negative** (deductible)."
        )
        c1, c2 = st.columns(2)
        with c1:
            ded_td = st.number_input("Deductible TD (KES, enter as POSITIVE; engine treats as negative)",
                                       min_value=0.0, value=50000.0, step=1000.0,
                                       key="dta_td")
        with c2:
            future_p = st.number_input(f"Future taxable profit estimate ({currency_symbol()})",
                                          min_value=0.0, value=100000.0, step=1000.0,
                                          key="dta_future")
        if st.button("Test DTA recoverability", key="dta_btn", type="primary"):
            r = DeferredTaxEngine.dta_recoverability(
                deductible_td=-_to_decimal(ded_td),  # engine wants negative
                future_taxable_profit_estimate=_to_decimal(future_p))
            if r.get("computed"):
                outcome = r.get("recognition")
                if outcome == "FULL_RECOGNITION":
                    st.success(
                        f"✅ FULL DTA RECOGNITION — future profit ({future_p:,.0f}) "
                        f"covers the {ded_td:,.0f} deductible TD.")
                elif outcome == "PARTIAL_RECOGNITION":
                    st.warning(
                        f"⚠ PARTIAL recognition — DTA limited to recoverable portion. "
                        f"Surplus written off.")
                elif outcome == "NO_RECOGNITION":
                    st.error(
                        f"⛔ NO RECOGNITION — insufficient future taxable profit. "
                        f"DTA NOT recognised per IAS 12.24-27.")
                with st.expander("Engine output"):
                    st.json(r)
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS12: DTA recov TD={ded_td} future={future_p} → {outcome}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason')}")

    with sub_tabs[3]:
        st.markdown("**Total Tax Expense** = Current + Deferred (P&L portion)")
        c1, c2, c3 = st.columns(3)
        with c1:
            ct = st.number_input(f"Current tax ({currency_symbol()})",
                                   value=300000.0, step=10000.0, key="tt_ct")
        with c2:
            dt_pnl = st.number_input(f"Deferred tax in P&L ({currency_symbol()})",
                                       value=12000.0, step=1000.0, key="tt_dtpnl")
        with c3:
            dt_oci = st.number_input(f"Deferred tax in OCI ({currency_symbol()})",
                                       value=0.0, step=1000.0, key="tt_dtoci")
        if st.button("Compute total tax", key="tt_btn", type="primary"):
            r = DeferredTaxEngine.total_tax_expense(
                current_tax=_to_decimal(ct),
                deferred_tax_pnl=_to_decimal(dt_pnl),
                deferred_tax_oci=_to_decimal(dt_oci))
            if r.get("computed"):
                k1, k2 = st.columns(2)
                k1.metric("Total P&L tax expense",
                           f"{currency_symbol()} {_to_decimal(r['total_tax_expense_pnl']):,.2f}")
                k2.metric("OCI tax (separate)",
                           f"{currency_symbol()} {_to_decimal(r['deferred_tax_oci_separate']):,.2f}",
                           help="Recognised in OCI, not P&L")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS12: total_tax current={ct} dt_pnl={dt_pnl} dt_oci={dt_oci}")


# ============================================================================
# TAB 4 — IFRS 10 Group Consolidation
# ============================================================================
with engine_tabs[4]:
    st.markdown("#### IFRS 10 — Consolidated Financial Statements")
    st.caption(
        f"Control threshold: >{CONTROL_THRESHOLD_PCT}% (full consolidation). "
        f"Significant influence: ≥{SIGNIFICANT_INFLUENCE_THRESHOLD_PCT}% (equity method). "
        f"Wholly owned: ≥{WHOLLY_OWNED_THRESHOLD_PCT}% (no NCI)."
    )

    sub_tabs = st.tabs([
        "🏷️ Subsidiary Classification",
        "👥 Non-Controlling Interest",
        "🔄 Intra-Group Eliminations",
        "💱 Currency Translation",
    ])

    with sub_tabs[0]:
        st.markdown("**Classify investee** by ownership %")
        c1, c2, c3 = st.columns(3)
        with c1:
            own = st.number_input("Ownership % (parent share)",
                                    min_value=0.0, max_value=100.0,
                                    value=75.0, step=1.0, key="cons_own")
        with c2:
            jv = st.checkbox("Joint venture", key="cons_jv")
        with c3:
            br = st.checkbox("Branch", key="cons_br")
        if st.button("Classify investee", key="cons_class_btn", type="primary"):
            cls = GroupConsolidationEngine.subsidiary_classification(
                ownership_pct=_to_decimal(own),
                is_joint_venture=jv, is_branch=br)
            r = GroupConsolidationEngine.consolidation_method(
                ownership_pct=_to_decimal(own), is_joint_venture=jv)
            if cls and r.get("computed"):
                method = r.get("method")
                colors = {
                    "WHOLLY_OWNED": "#059669", "MAJORITY_OWNED": "#10B981",
                    "ASSOCIATE": "#3B82F6", "JOINT_VENTURE": "#F59E0B",
                    "BRANCH": "#8B5CF6",
                }
                color = colors.get(cls, "#6B7280")
                k1, k2 = st.columns(2)
                with k1:
                    st.markdown(
                        f"<div style='padding:14px;background:{color}22;"
                        f"border-left:6px solid {color};border-radius:10px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"CLASSIFICATION</div>"
                        f"<div style='font-size:24px;font-weight:800;color:{color}'>{cls}</div></div>",
                        unsafe_allow_html=True)
                k2.metric("Consolidation method", method.replace("_", " "))
                st.caption(f"Rationale: {r.get('rationale', '').replace('_', ' ')}")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS10: classify {own}% → {cls}, method={method}")

    with sub_tabs[1]:
        st.markdown("**Non-Controlling Interest** = subsidiary equity × NCI %")
        c1, c2 = st.columns(2)
        with c1:
            sub_eq = st.number_input(f"Subsidiary equity ({currency_symbol()} M)",
                                       min_value=0.0, value=10.0, step=1.0,
                                       key="nci_eq")
        with c2:
            par_own = st.number_input("Parent ownership (%)",
                                         min_value=0.0, max_value=100.0,
                                         value=75.0, step=1.0, key="nci_own")
        if st.button("Compute NCI", key="nci_btn", type="primary"):
            r = GroupConsolidationEngine.non_controlling_interest(
                subsidiary_equity=_to_decimal(sub_eq) * Decimal("1000000"),
                parent_ownership_pct=_to_decimal(par_own))
            if r.get("computed"):
                nci = _to_decimal(r["nci"])
                k1, k2, k3 = st.columns(3)
                k1.metric("Parent share", f"{par_own:.1f}%")
                k2.metric("NCI share", f"{r['nci_share_pct']}%")
                k3.metric("NCI value",
                           f"{currency_symbol()} {nci/Decimal('1000000'):,.2f}M")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS10: NCI eq={sub_eq}M, parent={par_own}% → {nci}")

    with sub_tabs[2]:
        st.markdown("**Intra-Group Eliminations** (IFRS 10.B86)")
        st.caption("Eliminate 100% of intra-group balances and transactions during consolidation.")
        c1, c2 = st.columns(2)
        with c1:
            elim_type = st.selectbox("Elimination type",
                                       list(ELIMINATION_TYPES), key="elim_type")
        with c2:
            gross = st.number_input(f"Gross intra-group amount ({currency_symbol()} M)",
                                      min_value=0.0, value=5.0, step=0.5,
                                      key="elim_gross")
        if st.button("Compute elimination", key="elim_btn", type="primary"):
            r = GroupConsolidationEngine.elimination_amount(
                elimination_type=elim_type,
                gross_amount=_to_decimal(gross) * Decimal("1000000"))
            if r.get("computed"):
                elim = _to_decimal(r["elimination"])
                st.success(
                    f"✅ Eliminate **KES {elim/Decimal('1000000'):,.2f}M** "
                    f"of {elim_type.replace('_', ' ').lower()}.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS10: elim {elim_type} {gross}M")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason')}")

    with sub_tabs[3]:
        st.markdown("**Currency Translation** (IAS 21)")
        st.caption(
            f"Methods: {' / '.join(CURRENCY_TRANSLATION_METHODS)}. "
            "TEMPORAL_METHOD uses historical rates for non-monetary items; "
            "CURRENT_RATE_METHOD uses closing rate for all assets/liabilities."
        )
        c1, c2 = st.columns(2)
        with c1:
            method = st.selectbox("Method",
                                    list(CURRENCY_TRANSLATION_METHODS),
                                    key="ct_method")
            amount_local = st.number_input("Amount (local currency)",
                                              min_value=0.0, value=1.0,
                                              step=0.1, key="ct_amt",
                                              help="In millions of local currency.")
        with c2:
            closing = st.number_input("Closing rate (KES/local)",
                                         min_value=0.0, value=130.0, step=1.0,
                                         key="ct_closing")
            historical = st.number_input("Historical rate (KES/local)",
                                            min_value=0.0, value=125.0, step=1.0,
                                            key="ct_hist")
            is_mon = st.checkbox("Monetary item", value=True, key="ct_mon")
        if st.button("Translate", key="ct_btn", type="primary"):
            r = GroupConsolidationEngine.currency_translation(
                amount_local=_to_decimal(amount_local) * Decimal("1000000"),
                method=method,
                closing_rate=_to_decimal(closing),
                historical_rate=_to_decimal(historical),
                is_monetary=is_mon)
            if r.get("computed"):
                trans = _to_decimal(r["translated"])
                k1, k2 = st.columns(2)
                k1.metric("Translated amount",
                           f"{currency_symbol()} {trans/Decimal('1000000'):,.2f}M")
                k2.metric("Rate used",
                           f"{currency_symbol()} {_to_decimal(r.get('rate_used', '0')):.2f}")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS10/IAS21: translate {amount_local}M {method} → {trans}")
            else:
                st.error(f"Could not compute. Reason: {r.get('reason')}")


# ============================================================================
# TAB 5 — IAS 37 Provisions
# ============================================================================
with engine_tabs[5]:
    st.markdown("#### IAS 37 — Provisions, Contingent Liabilities, Contingent Assets")
    st.caption(
        f"Probability bands: PROBABLE ≥{PROBABLE_PCT_MIN}%, "
        f"POSSIBLE ≥{POSSIBLE_PCT_MIN}%, REMOTE <{POSSIBLE_PCT_MIN}%, "
        f"VIRTUALLY_CERTAIN ≥{VIRTUALLY_CERTAIN_PCT_MIN}%."
    )

    sub_tabs = st.tabs([
        "🎯 Liability Treatment",
        "💎 Asset Treatment",
        "📊 Provision Measurement",
        "🔥 Onerous Contract Test",
        "💵 Reimbursement",
    ])

    with sub_tabs[0]:
        st.markdown("**Liability Treatment by Probability** (IAS 37.14)")
        c1, c2 = st.columns(2)
        with c1:
            prob = st.number_input("Probability of outflow (%)",
                                     min_value=0.0, max_value=100.0,
                                     value=75.0, step=5.0, key="liab_prob")
        with c2:
            reliable = st.checkbox("Reliable estimate available",
                                     value=True, key="liab_reliable")
        if st.button("Determine treatment",
                       key="liab_btn", type="primary"):
            r = ProvisionsEngine.liability_treatment(
                probability_pct=_to_decimal(prob),
                reliable_estimate=reliable)
            if r.get("computed"):
                treatment = r.get("treatment")
                cls = r.get("probability_classification")
                colors = {"RECOGNISE": "#DC2626",
                          "DISCLOSE": "#F59E0B",
                          "NEITHER": "#10B981"}
                color = colors.get(treatment, "#6B7280")
                k1, k2 = st.columns(2)
                k1.metric("Probability class", cls)
                with k2:
                    st.markdown(
                        f"<div style='padding:8px 12px;background:{color}22;"
                        f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                        f"<div style='font-size:18px;font-weight:800;color:{color}'>"
                        f"{treatment}</div></div>", unsafe_allow_html=True)
                if treatment == "RECOGNISE":
                    st.error(
                        "⛔ **PROVISION RECOGNITION REQUIRED** — recognise on balance "
                        "sheet at best estimate per IAS 37.36.")
                elif treatment == "DISCLOSE":
                    st.warning(
                        "⚠ **CONTINGENT LIABILITY DISCLOSURE** — disclose in notes "
                        "per IAS 37.86. Do NOT recognise on balance sheet.")
                else:
                    st.success("✅ No recognition or disclosure required.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS37: liability prob={prob}% → {cls} / {treatment}")

    with sub_tabs[1]:
        st.markdown("**Asset Treatment by Probability** (IAS 37.31-35)")
        st.caption(
            "Contingent assets are recognised ONLY when virtually certain "
            f"(≥{VIRTUALLY_CERTAIN_PCT_MIN}%). Probable assets are disclosed only.")
        prob_a = st.number_input("Probability of inflow (%)",
                                    min_value=0.0, max_value=100.0,
                                    value=99.0, step=5.0, key="asset_prob")
        if st.button("Determine asset treatment",
                       key="asset_btn", type="primary"):
            r = ProvisionsEngine.asset_treatment(
                probability_pct=_to_decimal(prob_a))
            if r.get("computed"):
                treatment = r.get("treatment")
                if treatment == "RECOGNISE":
                    st.success(
                        f"✅ **VIRTUALLY CERTAIN** — recognise contingent asset "
                        f"per IAS 37.33.")
                elif treatment == "DISCLOSE":
                    st.warning(
                        f"⚠ **PROBABLE** — disclose only, do not recognise.")
                else:
                    st.info("ℹ No recognition or disclosure required.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS37: asset prob={prob_a}% → {treatment}")

    with sub_tabs[2]:
        st.markdown("**Provision Measurement** (IAS 37.36-41)")
        method = st.radio(
            "Measurement method",
            list(EXPECTED_VALUE_METHODS),
            key="prov_method",
            help="SINGLE_OBLIGATION = best estimate of single outflow. "
                 "LARGE_POPULATION = expected value (probability-weighted). "
                 "CONTINUOUS_RANGE = midpoint of equally-likely range.")
        if method == "SINGLE_OBLIGATION":
            amt = st.number_input(f"Best estimate ({currency_symbol()})",
                                    min_value=0.0, value=200000.0, step=10000.0,
                                    key="prov_single")
            if st.button("Measure", key="prov_meas_btn", type="primary"):
                r = ProvisionsEngine.provision_measurement(
                    method=method, amount=_to_decimal(amt))
                if r.get("computed"):
                    st.metric("Provision measurement", f"{currency_symbol()} {amt:,.2f}")
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"IAS37: provision SINGLE {amt}")
        elif method == "LARGE_POPULATION":
            st.caption(
                "Enter probability-weighted outcomes (probabilities should sum to 100%).")
            outcomes = []
            for i in range(3):
                c1, c2 = st.columns(2)
                with c1:
                    p = st.number_input(f"Outcome {i+1} probability (%)",
                                          min_value=0.0, max_value=100.0,
                                          value=[50.0, 30.0, 20.0][i], step=5.0,
                                          key=f"prov_p_{i}")
                with c2:
                    a = st.number_input(f"Outcome {i+1} amount (KES)",
                                          min_value=0.0,
                                          value=[100000.0, 200000.0, 500000.0][i],
                                          step=10000.0, key=f"prov_a_{i}")
                if p > 0 and a >= 0:
                    outcomes.append((_to_decimal(p), _to_decimal(a)))
            if st.button("Measure expected value",
                           key="prov_ev_btn", type="primary"):
                r = ProvisionsEngine.provision_measurement(
                    method=method,
                    probability_weighted_outcomes=outcomes)
                if r.get("computed"):
                    meas = _to_decimal(r["measurement"])
                    st.metric("Expected value provision", f"{currency_symbol()} {meas:,.2f}")
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"IAS37: provision EV {meas}")
                else:
                    st.error(r.get("reason", "Could not compute"))
        else:  # CONTINUOUS_RANGE
            c1, c2 = st.columns(2)
            with c1:
                lo = st.number_input(f"Range low ({currency_symbol()})",
                                       min_value=0.0, value=100000.0,
                                       step=10000.0, key="prov_lo")
            with c2:
                hi = st.number_input(f"Range high ({currency_symbol()})",
                                       min_value=0.0, value=500000.0,
                                       step=10000.0, key="prov_hi")
            if st.button("Measure midpoint",
                           key="prov_range_btn", type="primary"):
                r = ProvisionsEngine.provision_measurement(
                    method=method,
                    range_low=_to_decimal(lo),
                    range_high=_to_decimal(hi))
                if r.get("computed"):
                    meas = _to_decimal(r["measurement"])
                    st.metric("Midpoint provision", f"{currency_symbol()} {meas:,.2f}")
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"IAS37: provision RANGE {meas}")
                else:
                    st.error(r.get("reason", "Could not compute"))

    with sub_tabs[3]:
        st.markdown("**Onerous Contract Test** (IAS 37.66-69)")
        st.caption(
            "A contract is onerous when unavoidable costs exceed expected economic "
            "benefits. The provision = excess of unavoidable costs over benefits."
        )
        c1, c2 = st.columns(2)
        with c1:
            costs = st.number_input(f"Unavoidable costs ({currency_symbol()})",
                                      min_value=0.0, value=500000.0, step=10000.0,
                                      key="oc_costs")
        with c2:
            benefits = st.number_input(f"Expected economic benefits ({currency_symbol()})",
                                          min_value=0.0, value=300000.0, step=10000.0,
                                          key="oc_benefits")
        if st.button("Test onerous contract", key="oc_btn", type="primary"):
            r = ProvisionsEngine.onerous_contract_test(
                unavoidable_costs=_to_decimal(costs),
                expected_economic_benefits=_to_decimal(benefits))
            if r.get("computed"):
                onerous = r.get("onerous")
                if onerous:
                    prov = _to_decimal(r["provision"])
                    st.error(
                        f"⛔ **ONEROUS CONTRACT** — recognise provision "
                        f"of **KES {prov:,.2f}** "
                        f"(costs {costs:,.0f} − benefits {benefits:,.0f}).")
                else:
                    st.success("✅ Not onerous — benefits cover unavoidable costs.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS37: onerous test costs={costs} ben={benefits} "
                           f"→ onerous={onerous}")

    with sub_tabs[4]:
        st.markdown("**Reimbursement Treatment** (IAS 37.53-58)")
        st.caption(
            "When part or all of the expenditure required to settle a provision "
            "is expected to be reimbursed, the reimbursement should be recognised "
            "as a SEPARATE asset only when it is virtually certain to be received."
        )
        c1, c2 = st.columns(2)
        with c1:
            virt = st.checkbox("Virtually certain to receive",
                                 value=True, key="reim_virt")
        with c2:
            reim_amt = st.number_input(f"Expected reimbursement ({currency_symbol()})",
                                          min_value=0.0, value=50000.0, step=5000.0,
                                          key="reim_amt")
        if st.button("Test reimbursement", key="reim_btn", type="primary"):
            r = ProvisionsEngine.reimbursement_treatment(
                reimbursement_virtually_certain=virt,
                reimbursement_amount=_to_decimal(reim_amt))
            if r.get("computed"):
                if r.get("recognise_asset"):
                    st.success(
                        f"✅ **RECOGNISE separate asset** of KES {reim_amt:,.0f}. "
                        f"NOT netted against provision per IAS 37.54.")
                else:
                    st.warning(
                        "⚠ NOT virtually certain — DO NOT recognise asset. "
                        "Disclose existence in notes only.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IAS37: reimbursement virt={virt} amt={reim_amt}")


# ============================================================================
# TAB 6 — IFRS 15 Revenue
# ============================================================================
with engine_tabs[6]:
    st.markdown("#### IFRS 15 — Revenue from Contracts with Customers")
    st.caption(
        "5-step model: " + " → ".join(s.replace("_", " ").title()
                                        for s in IFRS_15_STEPS) + "."
    )

    sub_tabs = st.tabs([
        "1️⃣ Identify Contract",
        "3️⃣ Determine Price",
        "4️⃣ Allocate Price",
        "5️⃣ Recognition Pattern",
    ])

    with sub_tabs[0]:
        st.markdown("**Step 1: Identify the Contract** (IFRS 15.9)")
        st.caption(
            f"All {len(CONTRACT_CRITERIA)} criteria must be met for a contract "
            "to exist within the scope of IFRS 15.")
        criteria_met = {}
        for crit in CONTRACT_CRITERIA:
            criteria_met[crit] = st.checkbox(
                crit.replace("_", " ").title(),
                value=True, key=f"rev_crit_{crit}")
        if st.button("Identify contract", key="rev_id_btn", type="primary"):
            r = RevenueRecognitionEngine.identify_contract(criteria_met)
            recognised = r.get("contract_recognised")
            missing = r.get("criteria_missing_or_false", [])
            if recognised:
                st.success(
                    "✅ **CONTRACT EXISTS** — all 5 criteria met. "
                    "Proceed to Step 2 (identify performance obligations).")
            else:
                st.error(
                    f"⛔ **NO CONTRACT** — {len(missing)} criteria not met: "
                    + ", ".join(c.replace("_", " ").title() for c in missing))
            audit_log("IFRS_ENGINE_USED", uname,
                       f"IFRS15: identify contract recognised={recognised}, "
                       f"missing={len(missing)}")

    with sub_tabs[1]:
        st.markdown("**Step 3: Determine Transaction Price** (IFRS 15.47)")
        c1, c2 = st.columns(2)
        with c1:
            fixed = st.number_input(f"Fixed consideration ({currency_symbol()} M)",
                                      min_value=0.0, value=1.0, step=0.1,
                                      key="rev_fixed")
            variable = st.number_input(f"Variable consideration ({currency_symbol()} M)",
                                          value=0.1, step=0.05,
                                          key="rev_variable",
                                          help="Bonuses, rebates, refunds (probability-weighted).")
        with c2:
            non_cash = st.number_input(f"Non-cash consideration ({currency_symbol()} M)",
                                          min_value=0.0, value=0.0, step=0.1,
                                          key="rev_noncash")
            payable = st.number_input(f"Consideration payable to customer ({currency_symbol()} M)",
                                         min_value=0.0, value=0.0, step=0.1,
                                         key="rev_payable",
                                         help="Reduces transaction price.")
        if st.button("Compute transaction price",
                       key="rev_price_btn", type="primary"):
            r = RevenueRecognitionEngine.determine_transaction_price(
                fixed_consideration=_to_decimal(fixed) * Decimal("1000000"),
                variable_consideration=_to_decimal(variable) * Decimal("1000000"),
                non_cash_consideration=_to_decimal(non_cash) * Decimal("1000000"),
                consideration_payable_to_customer=_to_decimal(payable) * Decimal("1000000"))
            if r.get("computed"):
                price = _to_decimal(r["transaction_price"])
                st.metric("Transaction price",
                           f"{currency_symbol()} {price/Decimal('1000000'):,.2f}M")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"IFRS15: tx price → {price}")

    with sub_tabs[2]:
        st.markdown("**Step 4: Allocate Transaction Price** (IFRS 15.74)")
        st.caption(
            "Allocate based on relative standalone selling prices (SSPs) of "
            "each performance obligation.")
        tx_price = st.number_input(f"Transaction price ({currency_symbol()} M)",
                                      min_value=0.0, value=1.0, step=0.1,
                                      key="alloc_tx")
        st.markdown("**Performance obligations + standalone selling prices:**")
        ssps = {}
        for i in range(3):
            c1, c2 = st.columns(2)
            with c1:
                name = st.text_input(f"Obligation {i+1} name",
                                       value=[f"PROD_{c}" for c in "ABC"][i],
                                       key=f"alloc_n_{i}")
            with c2:
                ssp = st.number_input(f"SSP (KES K)",
                                        min_value=0.0,
                                        value=[600.0, 400.0, 0.0][i], step=50.0,
                                        key=f"alloc_s_{i}")
            if name.strip() and ssp > 0:
                ssps[name.strip()] = _to_decimal(ssp) * Decimal("1000")
        if st.button("Allocate price", key="alloc_btn", type="primary"):
            if not ssps:
                st.warning("Add at least one obligation with non-zero SSP.")
            else:
                r = RevenueRecognitionEngine.allocate_transaction_price(
                    transaction_price=_to_decimal(tx_price) * Decimal("1000000"),
                    standalone_selling_prices=ssps)
                if r.get("computed"):
                    rows = [
                        {"Obligation": k,
                          "Standalone SSP (KES K)": float(v / Decimal("1000")),
                          "Allocated price (KES K)": float(_to_decimal(r["allocations"][k]) / Decimal("1000"))}
                        for k, v in ssps.items()
                    ]
                    st.dataframe(pd.DataFrame(rows),
                                 use_container_width=True, hide_index=True)
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"IFRS15: allocate {len(ssps)} obligations")

    with sub_tabs[3]:
        st.markdown("**Step 5: Recognition Pattern** (IFRS 15.32, 35)")
        st.caption(
            "Revenue is recognised OVER TIME if any one of 3 criteria is met "
            "(IFRS 15.35). Otherwise, POINT IN TIME (when control transfers).")
        ot_criteria = {}
        for crit in OVER_TIME_CRITERIA:
            ot_criteria[crit] = st.checkbox(
                crit.replace("_", " ").title(),
                value=False, key=f"rev_ot_{crit}")
        if st.button("Determine pattern", key="rev_pat_btn", type="primary"):
            r = RevenueRecognitionEngine.revenue_recognition_pattern(ot_criteria)
            pattern = r.get("pattern")
            color = "#3B82F6" if pattern == "OVER_TIME" else "#F59E0B"
            st.markdown(
                f"<div style='padding:18px;background:{color}22;"
                f"border-left:6px solid {color};border-radius:12px;text-align:center'>"
                f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                f"RECOGNITION PATTERN</div>"
                f"<div style='font-size:28px;font-weight:800;color:{color}'>{pattern}</div>"
                f"<div style='font-size:13px;margin-top:6px'>"
                f"{r.get('rationale', '').replace('_', ' ')}</div></div>",
                unsafe_allow_html=True)
            criteria_met = r.get("criteria_met", [])
            if criteria_met:
                st.caption(
                    "Over-time criteria met: " + ", ".join(criteria_met))
            audit_log("IFRS_ENGINE_USED", uname,
                       f"IFRS15: recognition → {pattern}")
