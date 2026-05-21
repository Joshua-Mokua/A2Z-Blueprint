"""pages/93_risk_arc_cockpit.py — Risk Arc Engines Cockpit (v10.46).

UI integration backfill closing the protocol gap between v10.39-v10.44
(engines + audit + scenarios shipped) and v10.45 (G129 closure ratchet).
This page makes the four Risk-arc engines operator-driveable from the
browser instead of reachable only via Python imports + scripted scenarios:

    📈 Market Risk VaR   — utils.market_risk_var.VaREngine        (ENH-MR-001)
    🏛️ IRB Capital       — utils.credit_risk_irb.IRBCapitalEngine (ENH-CR-001)
    ⚙️ Op Risk SMA       — utils.op_risk.OperationalRiskSMA       (ENH-OR-001)
    💧 Stressed LCR      — utils.liquidity_stress.LiquidityStressEngine (ENH-LR-001)

Per Rule 1, every engine result is rendered with full provenance — inputs,
intermediates, outputs, framework refs — not just the headline number.

Per Rule 7, every tab makes it visually explicit that the engines are
diagnostic-only — no "execute remediation" buttons; outputs feed
governance discussions, never auto-act.

Decimal-internal monetary precision preserved end-to-end.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date

import streamlit as st

from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

from utils.market_risk_var import (
    VaREngine, VaRMethodology, VaRResult,
)
from utils.credit_risk_irb import (
    IRBCapitalEngine, IRBExposure, ExposureClass, CapitalResult,
)
from utils.op_risk import (
    OperationalRiskSMA, BusinessIndicatorInputs,
    OperationalLossEvent, SMAInputs, SMAResult,
    Bucket, ILMSource, SEVERITY_MULTIPLIERS as _OR_NOOP,  # import safety
)
from utils.liquidity_stress import (
    LiquidityStressEngine, HQLAHolding, HQLALevel,
    OutflowCategory, InflowCategory, StressSeverity,
    BreachSeverity, StressedLCRResult,
)


# ──────────────────────────────────────────────────────────────────────
# Access + setup
# ──────────────────────────────────────────────────────────────────────

require_access("perform")
um, ud, uname, *_ = load_shared_state()[:12]


# ──────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────

st.markdown(
    "<div style='padding:24px;background:linear-gradient(135deg,#1E3A8A 0%,#0EA5E9 100%);"
    "border-radius:16px;color:white;margin-bottom:20px'>"
    "<div style='font-size:13px;letter-spacing:2px;opacity:0.85'>RISK ARC · LIVE COCKPIT</div>"
    "<div style='font-size:28px;font-weight:800;margin-top:6px'>"
    "Risk Arc Engines Cockpit</div>"
    "<div style='font-size:14px;opacity:0.9;margin-top:8px'>"
    "Four Basel III regulatory engines locked under G129: VaR (BCBS d352), "
    "IRB capital (BCBS d424), SMA op-risk (BCBS d457), stressed LCR "
    "(BCBS d295). Every output is diagnostic — these engines surface "
    "exposure, never execute remediation. All approvals flow through "
    "ALCO, Capital Management Committee, and the Risk Committee.</div>"
    "</div>",
    unsafe_allow_html=True,
)

risk_tabs = st.tabs([
    "📈 Market Risk VaR (#ENH-MR-001)",
    "🏛️ IRB Capital (#ENH-CR-001)",
    "⚙️ Op Risk SMA (#ENH-OR-001)",
    "💧 Stressed LCR (#ENH-LR-001)",
    "ℹ️ About",
])


# ════════════════════════════════════════════════════════════════════════
# TAB 1 — Market Risk VaR (ENH-MR-001)
# ════════════════════════════════════════════════════════════════════════

with risk_tabs[0]:
    st.markdown("### 📈 Parametric / Historical VaR + Expected Shortfall")
    st.caption(
        "BCBS d352 §K. Returns provided by caller (no auto-fetch per "
        "Rule 7). 1-day horizon and 99% confidence are the regulatory "
        "default; both are tunable for stress-testing.")

    col_l, col_r = st.columns([2, 1])
    with col_l:
        method_label = st.selectbox(
            "Methodology",
            ["Parametric (Normal)", "Historical"],
            help=(
                "Parametric assumes Normal returns; closed-form. "
                "Historical uses the empirical distribution; no "
                "distribution assumption."))
        portfolio_value = st.number_input(
            "Portfolio value (KES)",
            min_value=1_000_000.0, value=100_000_000.0,
            step=1_000_000.0, format="%.2f")
        confidence_pct = st.slider(
            "Confidence level (%)", 90.0, 99.9, 99.0, 0.1)
        horizon_days = st.number_input(
            "Horizon (days)", min_value=1, max_value=30, value=1)

        returns_csv = st.text_area(
            "Daily returns (comma-separated decimals, e.g. -0.012,0.008,...)",
            value=(
                "-0.012, 0.008, 0.005, -0.020, 0.011, 0.003, "
                "-0.008, 0.015, -0.025, 0.007, 0.002, -0.014, "
                "0.009, -0.011, 0.006, 0.001, -0.018, 0.013, "
                "-0.004, 0.010, -0.022, 0.005, 0.012, -0.009, "
                "0.004, -0.016, 0.008, -0.013, 0.011, -0.006"),
            height=80,
            help="≥ 30 observations recommended for stable VaR.")

    with col_r:
        st.markdown("##### How to read")
        st.caption(
            "**VaR** is the loss at the chosen confidence — \"on the "
            "worst day in 100 we expect to lose at least KES X\". "
            "**Expected Shortfall (ES)** is the average loss in "
            "those tail days — ES ≥ VaR by construction.")

    if st.button("Compute VaR", type="primary", key="var_compute"):
        try:
            returns = [
                float(x.strip()) for x in returns_csv.split(",")
                if x.strip()]
        except ValueError as e:
            st.error(f"Could not parse returns: {e}")
            returns = []

        if len(returns) < 5:
            st.warning(
                f"Only {len(returns)} return observations supplied; "
                f"VaR estimates need ≥ 5 (≥ 30 strongly recommended).")
        elif len(returns) >= 1:
            engine = VaREngine()
            conf = Decimal(str(confidence_pct / 100))
            pv = Decimal(str(portfolio_value))
            if method_label.startswith("Parametric"):
                result: VaRResult = engine.parametric_var(
                    returns=returns,
                    portfolio_value_kes=pv,
                    confidence=conf,
                    horizon_days=int(horizon_days))
            else:
                result = engine.historical_var(
                    returns=returns,
                    portfolio_value_kes=pv,
                    confidence=conf,
                    horizon_days=int(horizon_days))

            audit_log("RISK_ENGINE_USED", uname, {
                "engine": "market_risk_var",
                "method": result.methodology.value,
                "var_kes": str(result.var_kes),
                "es_kes": str(result.expected_shortfall_kes),
                "n_obs": len(returns),
            })

            st.success(
                f"✅ {result.methodology.value} VaR computed on "
                f"{len(returns)} returns")
            m_a, m_b, m_c = st.columns(3)
            m_a.metric(
                "VaR (KES)",
                f"{float(result.var_kes):,.0f}",
                help="Loss at the chosen confidence")
            m_b.metric(
                "Expected Shortfall (KES)",
                f"{float(result.expected_shortfall_kes):,.0f}",
                help="Avg loss in the tail beyond VaR")
            m_c.metric(
                "VaR / Portfolio %",
                f"{float(result.var_kes) / float(pv) * 100:.2f}%")

            with st.expander("Return distribution + provenance"):
                rd = result.return_distribution
                st.json({
                    "methodology": result.methodology.value,
                    "confidence": str(result.confidence),
                    "horizon_days": result.horizon_days,
                    "portfolio_value_kes": str(result.portfolio_value_kes),
                    "var_kes": str(result.var_kes),
                    "expected_shortfall_kes": str(
                        result.expected_shortfall_kes),
                    "return_distribution": {
                        "n": rd.n_observations,
                        "mean": str(rd.mean),
                        "stdev": str(rd.stdev),
                        "min": str(rd.min_return),
                        "max": str(rd.max_return),
                    },
                    "framework_refs": list(result.framework_refs),
                })


# ════════════════════════════════════════════════════════════════════════
# TAB 2 — IRB Capital (ENH-CR-001)
# ════════════════════════════════════════════════════════════════════════

with risk_tabs[1]:
    st.markdown("### 🏛️ IRB Capital — Single Exposure")
    st.caption(
        "BCBS d424 §RBC25 corporate exposure formula. Per Rule 7, "
        "engine never moves loans between exposure classes and "
        "never auto-approves capital allocations — outputs feed "
        "ALCO + Capital Management Committee.")

    col_l, col_r = st.columns([3, 2])
    with col_l:
        exp_id = st.text_input("Exposure ID", value="LARGE-CORP-001")
        exp_class = st.selectbox(
            "Exposure class",
            [ExposureClass.LARGE_CORPORATE.value,
             ExposureClass.SME_CORPORATE.value],
            help="Sovereign / Bank classes reserved for future scope.")
        pd = st.slider(
            "PD — probability of default (1y)", 0.0003, 1.0, 0.01, 0.001,
            format="%.4f",
            help="Floored at 3 bp per BCBS d424 §RBC25.6")
        lgd = st.slider(
            "LGD — loss given default", 0.0, 1.0, 0.45, 0.01)
        ead_kes = st.number_input(
            "EAD — exposure at default (KES)",
            min_value=1_000_000.0, value=10_000_000.0,
            step=1_000_000.0, format="%.2f")
        m_years = st.slider(
            "M — effective maturity (years)", 1.0, 5.0, 2.5, 0.1,
            help="Bounded [1, 5] per BCBS d424 §RBC25.13")

    with col_r:
        st.markdown("##### Defaulted exposures")
        st.caption(
            "Set PD = 1.0 to model a defaulted exposure: per "
            "§RBC25.16 the IRB capital requirement above EL falls "
            "to zero; expected loss is fully realised.")

    if st.button("Compute IRB Capital", type="primary", key="irb_compute"):
        try:
            exposure = IRBExposure(
                exposure_id=exp_id,
                exposure_class=ExposureClass(exp_class),
                pd=float(pd), lgd=float(lgd),
                ead_kes=Decimal(str(ead_kes)),
                maturity_years=float(m_years))
            engine = IRBCapitalEngine()
            result: CapitalResult = engine.compute(exposure)

            audit_log("RISK_ENGINE_USED", uname, {
                "engine": "credit_risk_irb",
                "exposure_id": exp_id,
                "rwa_kes": str(result.rwa_kes),
                "k_pct": str(result.capital_requirement_pct),
            })

            st.success(f"✅ IRB capital computed for {exp_id}")
            m_a, m_b, m_c, m_d = st.columns(4)
            m_a.metric(
                "K (capital requirement %)",
                f"{float(result.capital_requirement_pct) * 100:.4f}%")
            m_b.metric(
                "RWA (KES)",
                f"{float(result.rwa_kes):,.0f}",
                help="K × 12.5 × EAD")
            m_c.metric(
                "Expected Loss (KES)",
                f"{float(result.expected_loss_kes):,.0f}",
                help="PD × LGD × EAD")
            m_d.metric(
                "Capital ratio (RWA / EAD)",
                f"{float(result.rwa_kes) / float(ead_kes) * 100:.2f}%")

            with st.expander("Intermediates + provenance (Rule 1)"):
                st.json({
                    "exposure_id": result.exposure_id,
                    "exposure_class": result.exposure_class.value,
                    "pd": result.pd,
                    "lgd": result.lgd,
                    "ead_kes": str(result.ead_kes),
                    "maturity_years": result.maturity_years,
                    "correlation_R": result.correlation_R,
                    "maturity_adj_b": result.maturity_adj_b,
                    "capital_requirement_pct": str(
                        result.capital_requirement_pct),
                    "rwa_kes": str(result.rwa_kes),
                    "expected_loss_kes": str(
                        result.expected_loss_kes),
                    "framework_refs": list(result.framework_refs),
                })
        except ValueError as e:
            st.error(f"Validation error: {e}")


# ════════════════════════════════════════════════════════════════════════
# TAB 3 — Op Risk SMA (ENH-OR-001)
# ════════════════════════════════════════════════════════════════════════

with risk_tabs[2]:
    st.markdown("### ⚙️ SMA Operational Risk Capital")
    st.caption(
        "BCBS d457 §RBC30. Bucket-1 banks (BI ≤ EUR 1bn) typically "
        "elect ILM = 1.0 under §RBC30.41 national discretion. "
        "Larger banks compute ILM via "
        "ln(e − 1 + (LC / BIC)^0.8) when ≥ 5 years of loss data "
        "are available. Per Rule 7, engine never records loss "
        "events and never approves capital allocations.")

    st.markdown("#### Business Indicator (one fiscal year — replicated 3x)")
    bi_cols = st.columns(3)
    with bi_cols[0]:
        ii = st.number_input(
            "Interest income (KES)",
            min_value=0.0, value=12_000_000_000.0,
            step=100_000_000.0)
        ie = st.number_input(
            "Interest expense (KES)",
            min_value=0.0, value=6_000_000_000.0,
            step=100_000_000.0)
        iea = st.number_input(
            "Interest-earning assets (KES)",
            min_value=0.0, value=400_000_000_000.0,
            step=1_000_000_000.0)
        di = st.number_input(
            "Dividend income (KES)",
            min_value=0.0, value=100_000_000.0,
            step=10_000_000.0)
    with bi_cols[1]:
        oi = st.number_input(
            "Other operating income (KES)",
            min_value=0.0, value=500_000_000.0,
            step=10_000_000.0)
        oe = st.number_input(
            "Other operating expense (KES)",
            min_value=0.0, value=400_000_000.0,
            step=10_000_000.0)
        fi = st.number_input(
            "Fee income (KES)",
            min_value=0.0, value=3_000_000_000.0,
            step=100_000_000.0)
        fe = st.number_input(
            "Fee expense (KES)",
            min_value=0.0, value=500_000_000.0,
            step=10_000_000.0)
    with bi_cols[2]:
        net_tb = st.number_input(
            "Net P&L Trading Book (KES, signed)",
            value=200_000_000.0, step=10_000_000.0)
        net_bb = st.number_input(
            "Net P&L Banking Book (KES, signed)",
            value=100_000_000.0, step=10_000_000.0)
        eur_kes = st.number_input(
            "EUR / KES rate", min_value=1.0, value=145.0, step=1.0)
        bucket1_disc = st.checkbox(
            "Apply Bucket-1 discretion (ILM = 1)", value=True,
            help="§RBC30.41 — most Tier-2 Kenya banks elect this.")

    st.markdown("#### Loss history (annual aggregate, 10y window)")
    loss_per_year = st.number_input(
        "Average annual operational loss (KES)",
        min_value=0.0, value=500_000_000.0, step=50_000_000.0,
        help=(
            "Use the bank's loss-event database aggregated annually. "
            "Engine accepts per-event records too — UI simplifies "
            "to a single annual figure replicated across the 10y "
            "window for the cockpit view."))
    n_loss_years = st.slider(
        "Years of loss history available", 0, 10, 10,
        help=(
            "When < 5, ILM is forced to 1.0 — INSUFFICIENT_HISTORY "
            "source surfaced in result."))

    if st.button("Compute SMA capital", type="primary", key="or_compute"):
        try:
            kw = dict(
                interest_income_kes=Decimal(str(ii)),
                interest_expense_kes=Decimal(str(ie)),
                interest_earning_assets_kes=Decimal(str(iea)),
                dividend_income_kes=Decimal(str(di)),
                other_operating_income_kes=Decimal(str(oi)),
                other_operating_expense_kes=Decimal(str(oe)),
                fee_income_kes=Decimal(str(fi)),
                fee_expense_kes=Decimal(str(fe)),
                net_pnl_trading_book_kes=Decimal(str(net_tb)),
                net_pnl_banking_book_kes=Decimal(str(net_bb)))
            bi_inputs = tuple(
                BusinessIndicatorInputs(fiscal_year=y, **kw)
                for y in (2023, 2024, 2025))
            current_yr = date.today().year
            loss_events = tuple(
                OperationalLossEvent(
                    fiscal_year=y,
                    gross_loss_kes=Decimal(str(loss_per_year)))
                for y in range(
                    current_yr - n_loss_years, current_yr))
            inputs = SMAInputs(
                bi_inputs=bi_inputs, loss_events=loss_events,
                eur_to_kes_rate=Decimal(str(eur_kes)),
                apply_bucket_1_discretion=bool(bucket1_disc))
            result: SMAResult = OperationalRiskSMA().compute(inputs)

            audit_log("RISK_ENGINE_USED", uname, {
                "engine": "op_risk",
                "bucket": result.bucket.value,
                "ilm_source": result.ilm_source.value,
                "rwa_op_kes": str(result.rwa_op_kes),
            })

            st.success(
                f"✅ SMA computed — bucket {result.bucket.value}, "
                f"ILM source: {result.ilm_source.value}")
            m_a, m_b, m_c, m_d = st.columns(4)
            m_a.metric(
                "BI 3y avg (EUR)",
                f"{float(result.bi_three_year_avg_eur):,.0f}")
            m_b.metric(
                "BIC (KES)",
                f"{float(result.bic_kes):,.0f}")
            m_c.metric(
                "ILM",
                f"{float(result.ilm):.4f}",
                help=f"Source: {result.ilm_source.value}")
            m_d.metric(
                "RWA op (KES)",
                f"{float(result.rwa_op_kes):,.0f}",
                help="ORC × 12.5")

            with st.expander("Intermediates + provenance (Rule 1)"):
                st.json({
                    "bi_per_year_kes": [
                        {"year": y, "bi_kes": str(v)}
                        for y, v in result.bi_per_year_kes],
                    "bi_three_year_avg_kes": str(
                        result.bi_three_year_avg_kes),
                    "bi_three_year_avg_eur": str(
                        result.bi_three_year_avg_eur),
                    "bucket": result.bucket.value,
                    "bic_kes": str(result.bic_kes),
                    "annual_avg_loss_kes": str(
                        result.annual_avg_loss_kes),
                    "lc_kes": str(result.lc_kes),
                    "ilm": str(result.ilm),
                    "ilm_source": result.ilm_source.value,
                    "orc_kes": str(result.orc_kes),
                    "rwa_op_kes": str(result.rwa_op_kes),
                    "framework_refs": list(result.framework_refs),
                })
        except ValueError as e:
            st.error(f"Validation error: {e}")


# ════════════════════════════════════════════════════════════════════════
# TAB 4 — Stressed LCR (ENH-LR-001)
# ════════════════════════════════════════════════════════════════════════

with risk_tabs[3]:
    st.markdown("### 💧 Stressed LCR — BCBS d295 calibration")
    st.caption(
        "Distinct from baseline LCR (utils.liquidity_risk, Standard "
        "#73). This page applies severity-tiered run-off "
        "multipliers and surfaces survival horizon when breaching. "
        "Per Rule 7, engine never auto-liquidates HQLA and never "
        "executes funding draws.")

    sev_label = st.radio(
        "Stress severity",
        [s.value for s in StressSeverity],
        index=2, horizontal=True,
        help=(
            "BASELINE 1.0× / MODERATE 1.5× / SEVERE 2.0× / "
            "BANK_RUN 3.0× outflow multipliers. Inflows reduce "
            "in mirror tiers."))

    st.markdown("#### HQLA composition")
    h_a, h_b, h_c = st.columns(3)
    with h_a:
        l1 = st.number_input(
            "Level 1 HQLA (KES) — cash, CB reserves, sovereign 0% RW",
            min_value=0.0, value=80_000_000_000.0,
            step=1_000_000_000.0,
            help="0% haircut")
    with h_b:
        l2a = st.number_input(
            "Level 2A HQLA (KES) — sovereign 20% RW, AA- corp",
            min_value=0.0, value=20_000_000_000.0,
            step=1_000_000_000.0,
            help="15% haircut, capped at 40% of total HQLA")
    with h_c:
        l2b = st.number_input(
            "Level 2B HQLA (KES) — lower-rated corp, equities",
            min_value=0.0, value=5_000_000_000.0,
            step=500_000_000.0,
            help="50% haircut, capped at 15% of total HQLA")

    st.markdown("#### Outflows (30-day, baseline run-off rates)")
    o_a, o_b = st.columns(2)
    with o_a:
        retail_bal = st.number_input(
            "Retail stable deposits (KES)",
            min_value=0.0, value=100_000_000_000.0,
            step=1_000_000_000.0)
        retail_rate = st.slider(
            "Retail base run-off rate", 0.0, 1.0, 0.05, 0.01,
            help="Basel III default for stable retail = 5%")
    with o_b:
        whole_bal = st.number_input(
            "Unsecured wholesale (non-financial, KES)",
            min_value=0.0, value=30_000_000_000.0,
            step=1_000_000_000.0)
        whole_rate = st.slider(
            "Wholesale base run-off rate", 0.0, 1.0, 0.40, 0.01,
            help="Basel III default for non-fin wholesale = 40%")

    st.markdown("#### Inflows (30-day)")
    in_a, in_b = st.columns(2)
    with in_a:
        loans_bal = st.number_input(
            "Performing loans receipts (KES)",
            min_value=0.0, value=8_000_000_000.0,
            step=500_000_000.0)
    with in_b:
        loans_rate = st.slider(
            "Performing loans run-in rate", 0.0, 1.0, 0.50, 0.01,
            help="Basel III default for performing retail/SME = 50%")

    if st.button("Compute stressed LCR", type="primary", key="lr_compute"):
        try:
            holdings = (
                HQLAHolding(
                    holding_id="cb_reserves_l1",
                    level=HQLALevel.LEVEL_1,
                    market_value_kes=Decimal(str(l1))),
                HQLAHolding(
                    holding_id="govt_l2a", level=HQLALevel.LEVEL_2A,
                    market_value_kes=Decimal(str(l2a))),
                HQLAHolding(
                    holding_id="corp_l2b", level=HQLALevel.LEVEL_2B,
                    market_value_kes=Decimal(str(l2b))),
            )
            outflows = (
                OutflowCategory(
                    category_id="retail_stable",
                    label="Retail stable",
                    balance_kes=Decimal(str(retail_bal)),
                    base_run_off_rate=Decimal(str(retail_rate))),
                OutflowCategory(
                    category_id="wholesale_unsec",
                    label="Wholesale unsecured (non-fin)",
                    balance_kes=Decimal(str(whole_bal)),
                    base_run_off_rate=Decimal(str(whole_rate))),
            )
            inflows = (
                InflowCategory(
                    category_id="performing_loans",
                    label="Performing loans",
                    balance_kes=Decimal(str(loans_bal)),
                    base_run_in_rate=Decimal(str(loans_rate))),
            )
            sev = StressSeverity(sev_label)
            result: StressedLCRResult = LiquidityStressEngine().compute(
                holdings=holdings, outflows=outflows,
                inflows=inflows, severity=sev,
                notes=f"cockpit_run_{date.today().isoformat()}")

            audit_log("RISK_ENGINE_USED", uname, {
                "engine": "liquidity_stress",
                "severity": result.severity.value,
                "lcr_ratio": str(result.lcr_ratio),
                "breach_severity": result.breach_severity.value,
            })

            # Breach traffic light
            colour = {
                BreachSeverity.COMPLIANT: "#10B981",
                BreachSeverity.AMBER: "#F59E0B",
                BreachSeverity.RED: "#EF4444",
                BreachSeverity.CRITICAL: "#7F1D1D",
            }[result.breach_severity]
            lcr_pct = (
                f"{float(result.lcr_ratio) * 100:.2f}%"
                if result.lcr_ratio is not None else "n/a (NCO ≤ 0)")
            st.markdown(
                f"<div style='padding:16px;background:{colour};"
                f"border-radius:12px;color:white;margin:12px 0'>"
                f"<div style='font-size:12px;opacity:0.85'>BREACH SEVERITY</div>"
                f"<div style='font-size:24px;font-weight:700'>"
                f"{result.breach_severity.value} · LCR = {lcr_pct}</div>"
                f"</div>",
                unsafe_allow_html=True)

            m_a, m_b, m_c, m_d = st.columns(4)
            m_a.metric(
                "HQLA after caps (KES)",
                f"{float(result.hqla_total_after_caps_kes):,.0f}")
            m_b.metric(
                "Stressed outflows (KES)",
                f"{float(result.total_outflows_kes):,.0f}")
            m_c.metric(
                "NCO 30d (KES)",
                f"{float(result.nco_30d_kes):,.0f}")
            survival_str = (
                f"{float(result.survival_days):.1f} days"
                if result.survival_days is not None
                else "compliant — no horizon")
            m_d.metric("Survival horizon", survival_str)

            with st.expander(
                    "Per-category outflows + provenance (Rule 1)"):
                st.json({
                    "severity": result.severity.value,
                    "hqla_pre_cap_kes": str(
                        result.hqla_total_pre_cap_kes),
                    "hqla_after_caps_kes": str(
                        result.hqla_total_after_caps_kes),
                    "hqla_breakdown": [
                        {
                            "level": b.level.value,
                            "gross_kes": str(b.gross_kes),
                            "haircut_pct": str(b.haircut_pct),
                            "after_haircut_kes": str(
                                b.after_haircut_kes),
                        }
                        for b in result.hqla_breakdown],
                    "outflows": [
                        {
                            "category_id": f.category_id,
                            "balance_kes": str(f.balance_kes),
                            "base_rate": str(f.base_rate),
                            "stress_multiplier": str(
                                f.stress_multiplier),
                            "stressed_rate": str(f.stressed_rate),
                            "stressed_kes": str(f.stressed_kes),
                        }
                        for f in result.outflows],
                    "inflows_capped_kes": str(
                        result.inflows_capped_kes),
                    "nco_30d_kes": str(result.nco_30d_kes),
                    "lcr_ratio": (
                        str(result.lcr_ratio)
                        if result.lcr_ratio is not None else None),
                    "breach_severity": result.breach_severity.value,
                    "survival_days": (
                        str(result.survival_days)
                        if result.survival_days is not None
                        else None),
                    "framework_refs": list(result.framework_refs),
                })
        except ValueError as e:
            st.error(f"Validation error: {e}")


# ════════════════════════════════════════════════════════════════════════
# TAB 5 — About
# ════════════════════════════════════════════════════════════════════════

with risk_tabs[4]:
    st.markdown("### ℹ️ Risk Arc — About this Cockpit")
    st.markdown(
        """
        The Risk arc was built across batches **v10.39 → v10.45**:

        | Batch    | Module                          | Standards            |
        | -------- | ------------------------------- | -------------------- |
        | v10.39   | market_risk_factors / sens / var | ENH-MR-001..005     |
        | v10.40   | market_risk_limits              | ENH-MR-006/007       |
        | v10.41   | trading_book_boundary           | ENH-MR-008/009/010   |
        | v10.42   | credit_risk_irb                 | ENH-CR-001           |
        | v10.43   | op_risk                         | ENH-OR-001           |
        | v10.44   | liquidity_stress                | ENH-LR-001           |
        | v10.45   | G129 + Tier 24 + Master Prompt  | closure ratchet      |
        | **v10.46** | **this cockpit + G130 ratchet** | **UI integration backfill** |

        **Frameworks referenced:**

        - BCBS d352 (FRTB) — Market Risk VaR + Trading Book Boundary
        - BCBS d424 — IRB Approach (Credit Risk Capital)
        - BCBS d457 — Standardised Approach for Operational Risk
        - BCBS d295 — Liquidity Coverage Ratio
        - CBK PG/12 — Liquidity Risk Management
        - CBK PG/15 — Risk Classification & Provisioning

        **Diagnostic-only posture (Rule 7).** None of the four engines
        on this page execute remediation. They surface exposure,
        capital requirement, breach severity, or VaR — and the
        operator carries those numbers to ALCO, the Capital
        Management Committee, or the Risk Committee. No "auto-rebalance",
        "auto-hedge", or "auto-liquidate" affordances exist.

        **Provenance discipline (Rule 1).** Every result rendered above
        also exposes its full intermediate state under the
        "Intermediates + provenance" expander — inputs, computed
        intermediates (correlation R, maturity adjustment b, ILM
        source, HQLA caps applied), outputs, framework refs.
        Decimal-internal monetary precision preserved end-to-end.

        Locked under **G129 risk_arc_closed** (registry/scenario
        ratchet) and **G130 risk_arc_ui_integrated** (this page's
        ratchet — see CHANGELOG_v10.46).
        """)

    audit_log("RISK_COCKPIT_ABOUT_VIEWED", uname, {
        "page": "93_risk_arc_cockpit"})
