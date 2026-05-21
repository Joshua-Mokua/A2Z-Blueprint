"""pages/45_crosssell.py — Cross-sell & Upsell Intelligence.
Products per customer, deepening ratio, NBA conversion, branch ranking.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from utils.config import cfg, currency_symbol
from pages._shared import load_shared_state
from pages._access import require_access

require_access("sales_customer.crosssell")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔁 Cross-sell Intelligence</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Products per customer · Deepening ratio · NBA conversion · Branch ranking</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    p = DATA/"crosssell_data.json"
    return a2z_db.load_json(p) if p.exists() else {}

data = _load()
if not data: st.info("Cross-sell data not available."); st.stop()

avg_prod = data.get("bank_average_products_per_customer",2.4)
tgt_prod = data.get("target_products_per_customer",3.5)
gap      = tgt_prod - avg_prod

m1,m2,m3,m4 = st.columns(4)
m1.metric("Avg Products/Customer", f"{avg_prod:.1f}")
m2.metric("Target",                f"{tgt_prod:.1f}")
m3.metric("Gap to Target",         f"{gap:.1f} products",
          delta_color="normal" if gap<=0 else "inverse")
m4.metric("Deepening Opportunity", f"{gap/tgt_prod*100:.0f}% upside")

tabs = st.tabs([
    "📊 Segment View",
    "🏢 Branch Ranking",
    "💡 NBA Opportunities",
    "📈 Conversion Funnel",
    "🎯 NBA Engine (Standard #59)",
    "📋 Priority List (Standard #59)",
    "🌳 Engine Reference (Standard #59)",
])

with tabs[0]:
    segs = data.get("by_segment",[])
    st.markdown("**Products per customer by segment:**")
    seg_rows=[{"Segment":s["segment"],"Avg Products":s["avg_products"],
                "Customers":f"{s['customers']:,}","NBA Conversion%":s["nba_conversion_pct"]}
               for s in segs]
    st.dataframe(pd.DataFrame(seg_rows),use_container_width=True,hide_index=True)
    st.bar_chart(pd.DataFrame({"Avg Products":[s["avg_products"] for s in segs]},
                               index=[s["segment"] for s in segs]))

with tabs[1]:
    branches = data.get("by_branch",[])
    b_rows=[{"Branch":b["branch"][:28],"Avg Products":b["avg_products"],
              "Deepening Score":b["deepening_score"],
              "Grade":("🟢" if b["deepening_score"]>=cfg("deepening_score_good",70) else "🟡" if b["deepening_score"]>=cfg("deepening_score_warn",50) else "🔴")}
             for b in sorted(branches,key=lambda x:-x["deepening_score"])]
    st.dataframe(pd.DataFrame(b_rows),use_container_width=True,hide_index=True)

with tabs[2]:
    nba = data.get("top_nba_products",[])
    st.markdown("**Top Next Best Action opportunities — eligible customers with propensity:**")
    nba_rows=[{"Product":n["product"],"Eligible Customers":f"{n['eligible_customers']:,}",
                "Avg Propensity":f"{n['propensity_avg']*100:.0f}%",
                "Converted (30d)":n["converted_30d"],
                "Conversion Rate":f"{n['converted_30d']/n['eligible_customers']*100:.1f}%"}
               for n in sorted(nba,key=lambda x:-x["eligible_customers"])]
    st.dataframe(pd.DataFrame(nba_rows),use_container_width=True,hide_index=True)

with tabs[3]:
    st.markdown("**Conversion funnel — from NBA identification to product take-up:**")
    total_eligible = sum(n["eligible_customers"] for n in nba)
    total_converted = sum(n["converted_30d"] for n in nba)
    funnel = [
        ("Eligible customers identified",    total_eligible,  "#3B82F6"),
        ("Contacted / approached",            int(total_eligible*0.45), "#0891B2"),
        ("Expressed interest",               int(total_eligible*0.22), "#0F6E56"),
        ("Application submitted",            int(total_eligible*0.12), "#16A34A"),
        ("Converted (product taken up)",     total_converted, "#15803D"),
    ]
    for label, n, clr in funnel:
        pct = n/max(total_eligible,1)*100
        bar = int(pct/2)
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
            f"<div style='width:260px;font-size:12px'>{label}</div>"
            f"<div style='background:{clr};height:18px;width:{bar}%;border-radius:3px;min-width:4px'></div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>{n:,} ({pct:.1f}%)</div>"
            f"</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# TAB 5 — NBA ENGINE (Standard #59 Cross-sell, integrated v5.89)
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    from utils.cross_sell_nba import (
        CrossSellNextBestActionEngine, CustomerForCrossSell,
        RECOMMENDABLE_PRODUCTS, NBA_RULE_WEIGHTS,
        NBA_HOT_THRESHOLD, NBA_WARM_THRESHOLD,
        PERSONAL_LOAN_MIN_INCOME_KES, MORTGAGE_MIN_INCOME_KES,
        CREDIT_CARD_MIN_INCOME_KES, INVESTMENT_MIN_BALANCE_KES,
        TERM_DEPOSIT_MIN_BALANCE_KES, MIN_TENURE_FOR_UNSECURED_DAYS,
        SPEC_DEVIATION_NOTE,
    )
    from decimal import Decimal as _D_xs
    from utils.core_audit import audit_log as _audit_log

    st.markdown(
        f"**Standard #59 — Cross-sell Next-Best-Action Engine**. "
        f"Deterministic rule-based propensity scoring across "
        f"{len(NBA_RULE_WEIGHTS)} rules → recommendations for "
        f"{len(RECOMMENDABLE_PRODUCTS)} products with HOT/WARM/COLD tiers."
    )
    st.caption(
        f"Tier thresholds: HOT≥{NBA_HOT_THRESHOLD} · WARM≥{NBA_WARM_THRESHOLD} · "
        f"COLD<{NBA_WARM_THRESHOLD}. ML-based recommender deferred per spec deviation #9 — "
        "engine uses deterministic rule-based scoring (Rule 7 — no silent ML fallback)."
    )

    nba_sub_tabs = st.tabs([
        "🔍 Single Customer NBA",
        "✅ Product Eligibility",
        "🌳 Demo Customer Builder",
    ])

    # ──────── Single Customer NBA ────────
    with nba_sub_tabs[0]:
        st.markdown(
            "**Get Next-Best-Action recommendations for a single customer** — "
            "engine evaluates 7 rules and returns ranked product recommendations.")

        c1, c2 = st.columns(2)
        with c1:
            xs_id = st.text_input("Customer ID",
                                    value="CUST_2026_001", key="xs_id")
            xs_cif = st.text_input("CIF ID",
                                     value="CIF_001", key="xs_cif")
            xs_income = st.number_input(f"Monthly income ({currency_symbol()} K)",
                                          min_value=0.0, value=85.0, step=5.0,
                                          key="xs_income",
                                          help=f"Personal loan needs ≥{int(PERSONAL_LOAN_MIN_INCOME_KES)/1000:.0f}K · "
                                                f"Credit card ≥{int(CREDIT_CARD_MIN_INCOME_KES)/1000:.0f}K · "
                                                f"Mortgage ≥{int(MORTGAGE_MIN_INCOME_KES)/1000:.0f}K")
            xs_savings = st.number_input(f"Savings balance ({currency_symbol()} K)",
                                           min_value=0.0, value=600.0, step=50.0,
                                           key="xs_savings",
                                           help=f"Investment needs ≥{int(INVESTMENT_MIN_BALANCE_KES)/1000:.0f}K · "
                                                f"Term deposit ≥{int(TERM_DEPOSIT_MIN_BALANCE_KES)/1000:.0f}K")
            xs_current = st.number_input(f"Current balance ({currency_symbol()} K)",
                                           min_value=0.0, value=120.0, step=20.0,
                                           key="xs_current")

        with c2:
            xs_tenure = st.number_input("Tenure (days)",
                                          min_value=0, value=720, step=30,
                                          key="xs_tenure",
                                          help=f"Unsecured products need ≥{MIN_TENURE_FOR_UNSECURED_DAYS} days.")
            xs_lifecycle = st.selectbox("Lifecycle stage",
                                          ["NEW", "GROWTH", "MATURE", "DECLINING"],
                                          index=2, key="xs_lifecycle")
            xs_complaint = st.checkbox("Has open complaint",
                                         value=False, key="xs_complaint",
                                         help="Customers with open complaints are excluded from NBA.")

            st.markdown("**Products held:**")
            xs_savings_acct = st.checkbox("Savings account",
                                            value=True, key="xs_savings_acct")
            xs_current_acct = st.checkbox("Current account",
                                            value=True, key="xs_current_acct")
            xs_loan = st.checkbox("Personal loan",
                                    value=False, key="xs_loan")
            xs_mortgage = st.checkbox("Mortgage",
                                        value=False, key="xs_mortgage")
            xs_card = st.checkbox("Credit card",
                                    value=True, key="xs_card")
            xs_td = st.checkbox("Term deposit",
                                  value=False, key="xs_td")
            xs_invest = st.checkbox("Investment",
                                      value=False, key="xs_invest")
            xs_insurance = st.checkbox("Insurance",
                                         value=False, key="xs_insurance")

        if st.button("🎯 Compute NBA",
                       key="xs_nba_btn", type="primary"):
            customer = CustomerForCrossSell(
                customer_id=xs_id,
                cif_id=xs_cif,
                monthly_income_kes=_D_xs(str(xs_income * 1000)),
                total_savings_balance_kes=_D_xs(str(xs_savings * 1000)),
                total_current_balance_kes=_D_xs(str(xs_current * 1000)),
                has_savings_account=xs_savings_acct,
                has_current_account=xs_current_acct,
                has_personal_loan=xs_loan,
                has_mortgage=xs_mortgage,
                has_credit_card=xs_card,
                has_term_deposit=xs_td,
                has_investment=xs_invest,
                has_insurance=xs_insurance,
                tenure_days=int(xs_tenure),
                lifecycle_stage=xs_lifecycle,
                last_complaint_open=xs_complaint,
            )
            r = CrossSellNextBestActionEngine.next_best_action_rule_based(customer)

            rec_count = int(r.get("recommendation_count", 0))
            applied = r.get("applied_rules", [])
            recs = r.get("recommendations", [])

            k1, k2, k3 = st.columns(3)
            k1.metric("Recommendations", rec_count)
            k2.metric("Rules applied", len(applied))
            # Tier breakdown
            from collections import Counter
            tier_counter = Counter([rec.get("tier", "—") for rec in recs])
            hot = tier_counter.get("HOT", 0)
            warm = tier_counter.get("WARM", 0)
            cold = tier_counter.get("COLD", 0)
            k3.metric("HOT / WARM / COLD",
                       f"{hot} / {warm} / {cold}")

            if recs:
                st.markdown("**Ranked recommendations:**")
                tier_emoji = {"HOT": "🔥", "WARM": "🌤️", "COLD": "❄️"}
                rec_rows = []
                for rec in recs:
                    tier = rec.get("tier", "—")
                    rec_rows.append({
                        "Product": rec.get("product"),
                        "Score": int(_D_xs(str(rec.get("score", 0)))),
                        "Tier": f"{tier_emoji.get(tier, '⚪')} {tier}",
                        "Rule": rec.get("rule", "—"),
                        "Rationale": rec.get("rationale", "—"),
                    })
                st.dataframe(pd.DataFrame(rec_rows),
                             use_container_width=True, hide_index=True)

                # Top recommendation guidance
                top_rec = recs[0]
                top_tier = top_rec.get("tier", "")
                if top_tier == "HOT":
                    st.success(
                        f"🔥 **HOT lead** — top recommendation: **{top_rec['product']}** "
                        f"(score {top_rec['score']}). "
                        f"Customer relationship manager should follow up within 7 days.")
                elif top_tier == "WARM":
                    st.info(
                        f"🌤️ **WARM lead** — top recommendation: **{top_rec['product']}** "
                        f"(score {top_rec['score']}). "
                        f"Suitable for next routine engagement.")
                else:
                    st.warning(
                        f"❄️ **COLD/none** — no high-priority recommendations.")
            else:
                st.info(
                    "ℹ No recommendations triggered. Customer may already hold all "
                    "eligible products, or thresholds (income/balance/tenure) not met.")

            _audit_log("IFRS_ENGINE_USED", uname,
                        f"CrossSell #59: NBA {xs_id} recs={rec_count} "
                        f"hot={hot} warm={warm} cold={cold}")

    # ──────── Product Eligibility ────────
    with nba_sub_tabs[1]:
        st.markdown(
            "**Check eligibility for a specific product** — engine returns "
            "eligibility decision + reason.")
        st.caption(
            "Engine checks: already-held flag, income thresholds, balance thresholds, "
            "tenure requirements, complaint status. Returns first failure reason "
            "(Rule 6 transparency) or 'passed_all_checks' if eligible.")

        ec1, ec2 = st.columns(2)
        with ec1:
            ep_product = st.selectbox(
                "Product to check",
                list(RECOMMENDABLE_PRODUCTS),
                key="xs_ep_product")
            ep_id = st.text_input("Customer ID",
                                    value="CUST_ELIG_001", key="xs_ep_id")
            ep_income = st.number_input(f"Monthly income ({currency_symbol()} K)",
                                          min_value=0.0, value=50.0, step=5.0,
                                          key="xs_ep_income")
        with ec2:
            ep_savings = st.number_input(f"Savings balance ({currency_symbol()} K)",
                                           min_value=0.0, value=200.0, step=50.0,
                                           key="xs_ep_savings")
            ep_tenure = st.number_input("Tenure (days)",
                                          min_value=0, value=400, step=30,
                                          key="xs_ep_tenure")
            ep_held = st.checkbox(f"Customer already holds {ep_product}",
                                    value=False, key="xs_ep_held")

        if st.button("✅ Check eligibility",
                       key="xs_ep_btn", type="primary"):
            ep_cust = CustomerForCrossSell(
                customer_id=ep_id, cif_id=f"CIF_{ep_id}",
                monthly_income_kes=_D_xs(str(ep_income * 1000)),
                total_savings_balance_kes=_D_xs(str(ep_savings * 1000)),
                tenure_days=int(ep_tenure),
                # Set the "has_X" flag based on product
                has_savings_account=(ep_held and ep_product == "SAVINGS"),
                has_current_account=(ep_held and ep_product == "CURRENT"),
                has_personal_loan=(ep_held and ep_product == "PERSONAL_LOAN"),
                has_mortgage=(ep_held and ep_product == "MORTGAGE"),
                has_credit_card=(ep_held and ep_product == "CREDIT_CARD"),
                has_term_deposit=(ep_held and ep_product == "TERM_DEPOSIT"),
                has_investment=(ep_held and ep_product == "INVESTMENT"),
                has_insurance=(ep_held and ep_product == "INSURANCE"),
            )
            r = CrossSellNextBestActionEngine.product_eligibility(ep_cust, ep_product)
            eligible = r.get("eligible", False)
            reason = r.get("reason", "—")

            if eligible:
                st.success(
                    f"✅ **Eligible for {ep_product}** — `{reason}`")
            else:
                st.error(
                    f"⛔ **NOT eligible for {ep_product}** — reason: `{reason}`")

            # Surface engine response details
            st.markdown("**Engine response:**")
            st.json(r)

            _audit_log("IFRS_ENGINE_USED", uname,
                        f"CrossSell #59: eligibility {ep_product} eligible={eligible} reason={reason}")

    # ──────── Demo Customer Builder ────────
    with nba_sub_tabs[2]:
        st.markdown(
            "**Demo customer scenarios** — pre-configured profiles to demonstrate "
            "different rule combinations.")

        scenario = st.selectbox(
            "Scenario",
            [
                "High savings + no mortgage (mortgage rule)",
                "High income + no credit card (card rule)",
                "Current account only (savings rule)",
                "New customer + no card (lifecycle rule)",
                "Stable mature customer (investment rule)",
                "Low engagement (savings nudge)",
                "Customer with open complaint (excluded)",
            ],
            key="xs_demo_scenario")

        # Build customer based on scenario
        scenarios = {
            "High savings + no mortgage (mortgage rule)": dict(
                customer_id="DEMO_001", cif_id="CIF_001",
                monthly_income_kes=_D_xs("100000"),
                total_savings_balance_kes=_D_xs("800000"),
                has_savings_account=True, has_current_account=True,
                has_credit_card=True, tenure_days=720, lifecycle_stage="MATURE"),
            "High income + no credit card (card rule)": dict(
                customer_id="DEMO_002", cif_id="CIF_002",
                monthly_income_kes=_D_xs("120000"),
                total_savings_balance_kes=_D_xs("50000"),
                has_savings_account=True, tenure_days=600, lifecycle_stage="GROWTH"),
            "Current account only (savings rule)": dict(
                customer_id="DEMO_003", cif_id="CIF_003",
                monthly_income_kes=_D_xs("35000"),
                total_current_balance_kes=_D_xs("80000"),
                has_current_account=True, tenure_days=400),
            "New customer + no card (lifecycle rule)": dict(
                customer_id="DEMO_004", cif_id="CIF_004",
                monthly_income_kes=_D_xs("60000"),
                has_savings_account=True, tenure_days=90, lifecycle_stage="NEW"),
            "Stable mature customer (investment rule)": dict(
                customer_id="DEMO_005", cif_id="CIF_005",
                monthly_income_kes=_D_xs("90000"),
                total_savings_balance_kes=_D_xs("400000"),
                has_savings_account=True, has_current_account=True,
                has_credit_card=True, tenure_days=1500, lifecycle_stage="MATURE"),
            "Low engagement (savings nudge)": dict(
                customer_id="DEMO_006", cif_id="CIF_006",
                monthly_income_kes=_D_xs("25000"),
                total_savings_balance_kes=_D_xs("5000"),
                has_savings_account=True, tenure_days=200, lifecycle_stage="DECLINING"),
            "Customer with open complaint (excluded)": dict(
                customer_id="DEMO_007", cif_id="CIF_007",
                monthly_income_kes=_D_xs("100000"),
                total_savings_balance_kes=_D_xs("800000"),
                has_savings_account=True, tenure_days=720, lifecycle_stage="MATURE",
                last_complaint_open=True),
        }
        cust_cfg = scenarios[scenario]

        st.json({k: str(v) for k, v in cust_cfg.items()})

        if st.button("🎯 Run scenario",
                       key="xs_demo_btn", type="primary"):
            demo_cust = CustomerForCrossSell(**cust_cfg)
            r = CrossSellNextBestActionEngine.next_best_action_rule_based(demo_cust)

            recs = r.get("recommendations", [])
            applied = r.get("applied_rules", [])

            if recs:
                st.success(
                    f"✅ {len(recs)} recommendation(s) generated:")
                tier_emoji = {"HOT": "🔥", "WARM": "🌤️", "COLD": "❄️"}
                for rec in recs:
                    tier = rec.get("tier", "—")
                    st.markdown(
                        f"- {tier_emoji.get(tier, '⚪')} **{rec['product']}** "
                        f"(score {rec['score']}, tier {tier}): "
                        f"`{rec['rule']}` → {rec.get('rationale', '—')}")
            else:
                st.info(
                    "ℹ No recommendations for this scenario.")

            st.caption(f"Rules applied: {applied}")
            _audit_log("IFRS_ENGINE_USED", uname,
                        f"CrossSell #59: scenario {cust_cfg['customer_id']} "
                        f"recs={len(recs)} applied={applied}")


# ════════════════════════════════════════════════════════════════
# TAB 6 — PRIORITY LIST (Standard #59 Cross-sell, integrated v5.89)
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    _pl_sub_tabs = st.tabs([
        "📋 Cross-sell Priority (existing)",
        "🎯 Optimize RM Allocation (#57, v5.94)",
        "🔬 What-If Projection (#57, v5.94)",
        "🌳 Allocation Engine Reference (#57, v5.94)",
    ])

    with _pl_sub_tabs[0]:
        from utils.cross_sell_nba import (
            CrossSellNextBestActionEngine, CustomerForCrossSell,
            NBA_HOT_THRESHOLD, NBA_WARM_THRESHOLD,
        )
        from decimal import Decimal as _D_pl
        from utils.core_audit import audit_log as _audit_log_pl

        st.markdown(
            "**Cross-sell Priority List** — engine ranks top opportunities across "
            "a customer portfolio, sorted by NBA score descending.")
        st.caption(
            f"Demo dataset: 8 customer profiles representing typical Tier-2 bank mix "
            f"(retail/SME/HNW). Engine returns top opportunities with score, tier, "
            f"and rationale for each. Production deployment would feed via "
            f"`customers_register.json` filtered through `next_best_action_rule_based`.")

        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_xs_portfolio():
            return [
                CustomerForCrossSell(
                    customer_id="C_HNW_001", cif_id="CIF_HNW_001",
                    monthly_income_kes=_D_pl("250000"),
                    total_savings_balance_kes=_D_pl("1500000"),
                    has_savings_account=True, has_current_account=True,
                    has_credit_card=True, has_mortgage=False,
                    tenure_days=900, lifecycle_stage="MATURE"),
                CustomerForCrossSell(
                    customer_id="C_RET_001", cif_id="CIF_RET_001",
                    monthly_income_kes=_D_pl("85000"),
                    total_savings_balance_kes=_D_pl("250000"),
                    has_savings_account=True, has_current_account=True,
                    has_credit_card=False,
                    tenure_days=600, lifecycle_stage="GROWTH"),
                CustomerForCrossSell(
                    customer_id="C_RET_002", cif_id="CIF_RET_002",
                    monthly_income_kes=_D_pl("45000"),
                    total_savings_balance_kes=_D_pl("80000"),
                    total_current_balance_kes=_D_pl("60000"),
                    has_current_account=True, has_savings_account=False,
                    tenure_days=300, lifecycle_stage="GROWTH"),
                CustomerForCrossSell(
                    customer_id="C_NEW_001", cif_id="CIF_NEW_001",
                    monthly_income_kes=_D_pl("65000"),
                    total_savings_balance_kes=_D_pl("30000"),
                    has_savings_account=True,
                    tenure_days=80, lifecycle_stage="NEW"),
                CustomerForCrossSell(
                    customer_id="C_SME_001", cif_id="CIF_SME_001",
                    monthly_income_kes=_D_pl("180000"),
                    total_savings_balance_kes=_D_pl("500000"),
                    total_current_balance_kes=_D_pl("400000"),
                    has_savings_account=True, has_current_account=True,
                    has_credit_card=True,
                    tenure_days=1200, lifecycle_stage="MATURE"),
                CustomerForCrossSell(
                    customer_id="C_RET_003", cif_id="CIF_RET_003",
                    monthly_income_kes=_D_pl("32000"),
                    total_savings_balance_kes=_D_pl("8000"),
                    has_savings_account=True,
                    tenure_days=400, lifecycle_stage="DECLINING"),
                CustomerForCrossSell(
                    customer_id="C_FUL_001", cif_id="CIF_FUL_001",
                    monthly_income_kes=_D_pl("110000"),
                    total_savings_balance_kes=_D_pl("300000"),
                    has_savings_account=True, has_current_account=True,
                    has_credit_card=True, has_term_deposit=True,
                    has_investment=True, has_personal_loan=True,
                    has_mortgage=True, has_insurance=True,
                    tenure_days=1500, lifecycle_stage="MATURE"),
                CustomerForCrossSell(
                    customer_id="C_CMP_001", cif_id="CIF_CMP_001",
                    monthly_income_kes=_D_pl("90000"),
                    total_savings_balance_kes=_D_pl("700000"),
                    has_savings_account=True,
                    tenure_days=900, lifecycle_stage="MATURE",
                    last_complaint_open=True),
            ]

        pl_max = st.slider(
            "Max opportunities to return",
            min_value=5, max_value=50, value=20, step=5,
            key="xs_pl_max")

        if st.button("📋 Compute priority list",
                       key="xs_pl_btn", type="primary"):
            portfolio = _demo_xs_portfolio()
            r = CrossSellNextBestActionEngine.cross_sell_priority_list(
                portfolio, max_count=pl_max)

            total = int(r["total_customers"])
            no_recs = int(r["customers_with_no_recs"])
            opps = int(r["total_opportunities"])
            top = r.get("top_opportunities", [])

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Total customers", total)
            k2.metric("With recs", total - no_recs)
            k3.metric("No recs", no_recs,
                       help="Already fully cross-sold OR thresholds not met OR open complaint.")
            k4.metric("Total opportunities", opps,
                       help="One customer can have multiple opportunities.")

            if top:
                st.markdown("**Top opportunities (sorted by score desc):**")
                tier_emoji = {"HOT": "🔥", "WARM": "🌤️", "COLD": "❄️"}
                top_rows = []
                for o in top:
                    tier = o.get("tier", "—")
                    top_rows.append({
                        "Customer": o.get("customer_id"),
                        "Product": o.get("product"),
                        "Score": int(_D_pl(str(o.get("score", 0)))),
                        "Tier": f"{tier_emoji.get(tier, '⚪')} {tier}",
                        "Rule": o.get("rule", "—"),
                        "Rationale": o.get("rationale", "—"),
                    })
                st.dataframe(pd.DataFrame(top_rows),
                             use_container_width=True, hide_index=True)

                # Tier distribution
                from collections import Counter
                tier_counter = Counter([o.get("tier", "—") for o in top])
                hot = tier_counter.get("HOT", 0)
                warm = tier_counter.get("WARM", 0)
                cold = tier_counter.get("COLD", 0)

                sk1, sk2, sk3 = st.columns(3)
                sk1.metric("🔥 HOT", hot)
                sk2.metric("🌤️ WARM", warm)
                sk3.metric("❄️ COLD", cold)

                # Bar chart of products by total score
                from collections import defaultdict
                prod_score = defaultdict(int)
                for o in top:
                    prod_score[o.get("product", "?")] += int(_D_pl(str(o.get("score", 0))))
                chart_data = pd.DataFrame({
                    "Total score": list(prod_score.values())
                }, index=list(prod_score.keys()))
                st.markdown("**Product opportunity strength (sum of scores):**")
                st.bar_chart(chart_data)

                if hot >= 5:
                    st.success(
                        f"✅ Strong pipeline — {hot} HOT lead(s). RM team should "
                        "prioritize these for outreach within 7 days.")
                elif hot >= 2:
                    st.info(
                        f"ℹ {hot} HOT lead(s) for immediate follow-up.")
                else:
                    st.warning(
                        f"⚠ Only {hot} HOT lead(s). Consider widening eligibility "
                        "criteria or expanding portfolio data.")
            else:
                st.info(
                    "ℹ No opportunities found in current portfolio.")

            _audit_log_pl("IFRS_ENGINE_USED", uname,
                           f"CrossSell #59: priority_list total={total} no_recs={no_recs} "
                           f"opps={opps} top_returned={len(top)}")

    # ════════════════════════════════════════════════════════════════
    # SUB-TAB[1]: Optimize RM Allocation (Standard #57, integrated v5.94)
    # ════════════════════════════════════════════════════════════════
    with _pl_sub_tabs[1]:
        from utils.allocation_optimizer import (
            CustomerAllocationOptimizer,
            DEFAULT_RM_CAPACITY, PROVISIONAL_FTP_OFF_THRESHOLD,
        )
        from utils.core_audit import audit_log as _audit_log_alloc

        st.markdown(
            "**Standard #57 — Customer Allocation Optimizer**. "
            "Greedy capacity-constrained algorithm assigns customers to RMs "
            "to maximize total projected PBT, subject to per-RM capacity caps.")
        st.caption(
            f"Default RM capacity: {DEFAULT_RM_CAPACITY} customers. "
            "Algorithm: greedy with marginal-gain ordering. Engine's own caveat: "
            "for >100 customers consider Hungarian / LP solver. "
            f"Provisional flag triggers when ≥{int(PROVISIONAL_FTP_OFF_THRESHOLD*100)}% "
            "of projections use FTP-off mode (data quality signal).")

        st.markdown("**Demo segment** — 5 customers, 3 RMs, varied PBT profitability matrix:")

        # Demo data inputs
        ac1, ac2 = st.columns(2)
        with ac1:
            alloc_segment = st.text_input("Segment", value="HNW",
                                            key="alloc_segment")
            alloc_period = st.text_input("Period", value="2025-12",
                                           key="alloc_period")
        with ac2:
            alloc_n_customers = st.slider("Number of customers",
                                            min_value=3, max_value=10,
                                            value=5, key="alloc_n_customers")
            alloc_capacity_each = st.slider("Capacity per RM (demo)",
                                              min_value=1, max_value=5,
                                              value=2, key="alloc_capacity",
                                              help="Cap on customers each RM can serve in demo.")

        if st.button("🎯 Run RM allocation optimization",
                       key="alloc_run_btn", type="primary"):
            # Build deterministic demo profitability matrix
            n = int(alloc_n_customers)
            cap = int(alloc_capacity_each)
            customer_ids = [f"C{i:03d}" for i in range(n)]
            rm_codes = ["RM001", "RM002", "RM003"]

            # Deterministic synthetic profit matrix — varies by (cust, rm) pair
            def _make_pbt(cid_i, rm_i):
                base = [50000, 30000, 90000, 25000, 35000, 40000, 20000, 15000,
                         70000, 55000][cid_i % 10]
                modifier = [1.0, 1.5, 1.2, 0.8, 1.1, 1.3, 0.9, 0.7, 1.4, 1.0][(cid_i * 3 + rm_i) % 10]
                return float(base * modifier)

            profit_matrix = {(customer_ids[i], rm_codes[j]): _make_pbt(i, j)
                              for i in range(n) for j in range(3)}

            # Current allocation: round-robin assignment for marginal-gain context
            current_alloc = {customer_ids[i]: rm_codes[i % 3] for i in range(n)}

            def _customers_fn(seg):
                return customer_ids

            def _rms_fn(seg):
                return rm_codes

            def _capacity_fn(rm):
                return cap

            def _current_fn(cid):
                return current_alloc.get(cid)

            def _projection_fn(cid, rm, period):
                pbt = profit_matrix.get((cid, rm))
                if pbt is None:
                    return None
                return {"projected_pbt": pbt, "ftp_mode": "on"}

            engine = CustomerAllocationOptimizer(
                customers_in_segment_fn=_customers_fn,
                rms_for_segment_fn=_rms_fn,
                rm_capacity_fn=_capacity_fn,
                current_allocation_fn=_current_fn,
                projection_fn=_projection_fn,
            )
            r = engine.optimize_rm_allocation(alloc_segment, period=alloc_period)

            # Top metrics
            assignments = r.get("assignments", [])
            total_gain = float(_D_pl(str(r.get("total_potential_gain", 0))))
            total_pbt = float(_D_pl(str(r.get("total_projected_pbt", 0))))
            meta = r.get("meta", {})
            unassignable = meta.get("unassignable", [])
            unassignable_count = int(meta.get("unassignable_count", 0))
            provisional = str(r.get("provisional", "False")).lower() == "true"

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Customers in segment", int(meta.get("customers_in_segment", 0)))
            k2.metric("Assignments made", len(assignments))
            k3.metric("Total potential gain", f"{currency_symbol()} {total_gain:,.0f}",
                       help="Sum of marginal_gain across assignments (improvement vs current).")
            k4.metric("Total projected PBT", f"{currency_symbol()} {total_pbt:,.0f}",
                       help="Sum of projected_pbt across all assignments.")

            # Provisional warning
            if provisional:
                st.warning(
                    f"⚠ **Provisional result** — engine flagged this as "
                    f"data-quality-low because ≥{int(PROVISIONAL_FTP_OFF_THRESHOLD*100)}% "
                    f"of projections used FTP-off mode. "
                    "Treat outputs as directional, not authoritative.")

            # Data quality warning
            if r.get("data_quality_warning") and r.get("data_quality_warning") != "None":
                st.info(f"ℹ {r['data_quality_warning']}")

            # Assignments table
            if assignments:
                st.markdown("**Optimal RM-customer assignments:**")
                rows = []
                for a in assignments:
                    pbt = float(_D_pl(str(a["projected_pbt"])))
                    gain = float(_D_pl(str(a["marginal_gain"])))
                    rows.append({
                        "Customer": a["customer_id"],
                        "Current RM": a.get("current_rm", "—"),
                        "→ Recommended RM": a["rm_code"],
                        f"Projected PBT ({currency_symbol()})": f"{pbt:,.0f}",
                        f"Marginal gain ({currency_symbol()})": f"{gain:+,.0f}",
                        "FTP mode": a.get("upstream_ftp_mode", "—"),
                    })
                st.dataframe(pd.DataFrame(rows),
                             use_container_width=True, hide_index=True)

                # RM utilization
                rm_util = meta.get("rm_utilization", {})
                if rm_util:
                    st.markdown("**RM capacity utilization:**")
                    util_cols = st.columns(len(rm_util))
                    for i, (rm, util) in enumerate(rm_util.items()):
                        util_cols[i].metric(rm, str(util),
                                              help="assigned/capacity")

            # Unassignable customers
            if unassignable_count > 0:
                st.warning(
                    f"⚠ **{unassignable_count} customer(s) unassignable** "
                    f"(Rule 6 transparency):")
                un_rows = [{"Customer": u["customer_id"], "Reason": u["reason"]}
                            for u in unassignable]
                st.dataframe(pd.DataFrame(un_rows),
                             use_container_width=True, hide_index=True)

            # Algorithm metadata
            with st.expander("Engine metadata"):
                st.json({
                    "algorithm": meta.get("algorithm"),
                    "algorithm_caveats": meta.get("algorithm_caveats"),
                    "upstream_ftp_modes": dict(meta.get("upstream_ftp_modes", {})),
                    "provisional_threshold_pct": meta.get("provisional_threshold_pct"),
                    "generated_at": meta.get("generated_at"),
                })

            _audit_log_alloc("IFRS_ENGINE_USED", uname,
                              f"AllocOpt #57: segment={alloc_segment} period={alloc_period} "
                              f"customers={n} assignments={len(assignments)} "
                              f"gain={total_gain:.0f} pbt={total_pbt:.0f} "
                              f"provisional={provisional} unassignable={unassignable_count}")

    # ════════════════════════════════════════════════════════════════
    # SUB-TAB[2]: What-If Projection (Standard #57, integrated v5.94)
    # ════════════════════════════════════════════════════════════════
    with _pl_sub_tabs[2]:
        from utils.allocation_optimizer import CustomerAllocationOptimizer
        from utils.core_audit import audit_log as _audit_log_wif

        st.markdown(
            "**What-If Projection** — for a single customer, project profitability "
            "across all eligible RMs in the segment. Helps RM team or relationship "
            "manager identify the best-fit RM before reassignment.")
        st.caption(
            "Engine method: `project_profitability_if_served_by(customer_id, rm_code, period)`. "
            "Returns dict with `projected_pbt` + `ftp_mode`, or `None` if RM is "
            "ineligible for this customer / data missing.")

        wic1, wic2 = st.columns(2)
        with wic1:
            wif_customer = st.text_input("Customer ID",
                                            value="C001",
                                            key="wif_customer")
            wif_period = st.text_input("Period", value="2025-12",
                                          key="wif_period")
        with wic2:
            wif_rms = st.text_input("RMs to compare (comma-separated)",
                                      value="RM001,RM002,RM003",
                                      key="wif_rms")

        if st.button("🔬 Run what-if projection",
                       key="wif_btn", type="primary"):
            # Use same demo profitability matrix as sub-tab[1]
            def _make_pbt(cid_i, rm_i):
                base = [50000, 30000, 90000, 25000, 35000, 40000, 20000, 15000,
                         70000, 55000][cid_i % 10]
                modifier = [1.0, 1.5, 1.2, 0.8, 1.1, 1.3, 0.9, 0.7, 1.4, 1.0][(cid_i * 3 + rm_i) % 10]
                return float(base * modifier)

            # Derive customer index for matrix lookup
            try:
                cid_i = int(wif_customer.lstrip("C").lstrip("0") or "0")
            except ValueError:
                cid_i = 0

            rm_list = [r.strip() for r in wif_rms.split(",") if r.strip()]

            def _projection_fn(cid, rm, period):
                # Map RM to deterministic index
                try:
                    rm_i = int(rm.lstrip("RM").lstrip("0") or "0") - 1
                except ValueError:
                    return None
                if rm_i < 0 or rm_i >= len(rm_list):
                    return None
                pbt = _make_pbt(cid_i, rm_i)
                return {"projected_pbt": pbt, "ftp_mode": "on"}

            engine = CustomerAllocationOptimizer(projection_fn=_projection_fn)

            # Project across all RMs
            results = []
            for rm in rm_list:
                p = engine.project_profitability_if_served_by(
                    wif_customer, rm, wif_period)
                if p is not None:
                    results.append({
                        "RM": rm,
                        f"Projected PBT ({currency_symbol()})": float(p["projected_pbt"]),
                        "FTP mode": p["ftp_mode"],
                    })
                else:
                    results.append({
                        "RM": rm,
                        f"Projected PBT ({currency_symbol()})": None,
                        "FTP mode": "ineligible / data missing",
                    })

            if not results:
                st.warning(f"⚠ No RMs to compare for {wif_customer}.")
            else:
                # Sort by PBT desc (None goes last)
                eligible = [r for r in results if r[f"Projected PBT ({currency_symbol()})"] is not None]
                ineligible = [r for r in results if r[f"Projected PBT ({currency_symbol()})"] is None]
                eligible.sort(key=lambda r: -r[f"Projected PBT ({currency_symbol()})"])

                if eligible:
                    best = eligible[0]
                    st.markdown(
                        f"<div style='padding:14px;background:#10B98122;"
                        f"border-left:6px solid #10B981;border-radius:10px'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"BEST-FIT RM</div>"
                        f"<div style='font-size:24px;font-weight:800;color:#10B981'>"
                        f"✅ {best['RM']} → {currency_symbol()} {best['Projected PBT (KES)']:,.0f}</div></div>",
                        unsafe_allow_html=True)

                rows = []
                for r in eligible + ineligible:
                    rows.append({
                        "RM": r["RM"],
                        f"Projected PBT ({currency_symbol()})": (f"{r['Projected PBT (KES)']:,.0f}"
                                                  if r['Projected PBT (KES)'] is not None
                                                  else "—"),
                        "FTP mode": r["FTP mode"],
                    })
                st.dataframe(pd.DataFrame(rows),
                             use_container_width=True, hide_index=True)

                if ineligible:
                    st.caption(
                        f"💡 {len(ineligible)} RM(s) returned None — engine indicates "
                        "RM ineligible for this customer or data missing (Rule 6).")

                _audit_log_wif("IFRS_ENGINE_USED", uname,
                                f"AllocOpt #57: whatif {wif_customer} "
                                f"rms_compared={len(rm_list)} eligible={len(eligible)} "
                                f"best_rm={eligible[0]['RM'] if eligible else 'none'}")

    # ════════════════════════════════════════════════════════════════
    # SUB-TAB[3]: Allocation Engine Reference (Standard #57, integrated v5.94)
    # ════════════════════════════════════════════════════════════════
    with _pl_sub_tabs[3]:
        from utils.allocation_optimizer import (
            DEFAULT_RM_CAPACITY, PROVISIONAL_FTP_OFF_THRESHOLD,
        )

        st.markdown("**Allocation Engine Reference** (Standard #57)")

        st.markdown("**Engine constants:**")
        const_rows = [
            {"Constant": "DEFAULT_RM_CAPACITY",
              "Value": str(DEFAULT_RM_CAPACITY),
              "Meaning": "Max customers an RM can serve when capacity_fn unspecified"},
            {"Constant": "PROVISIONAL_FTP_OFF_THRESHOLD",
              "Value": f"{PROVISIONAL_FTP_OFF_THRESHOLD} ({int(PROVISIONAL_FTP_OFF_THRESHOLD*100)}%)",
              "Meaning": "Triggers `provisional=True` when this fraction of projections use FTP-off mode"},
        ]
        st.dataframe(pd.DataFrame(const_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**5 DI callbacks:**")
        di_rows = [
            {"Callback": "customers_in_segment_fn(segment)",
              "Returns": "list[customer_id] — customers in this segment"},
            {"Callback": "rms_for_segment_fn(segment)",
              "Returns": "list[rm_code] — RMs eligible to serve this segment"},
            {"Callback": "rm_capacity_fn(rm_code)",
              "Returns": "int — max customers this RM can serve "
                         f"(default {DEFAULT_RM_CAPACITY})"},
            {"Callback": "current_allocation_fn(customer_id)",
              "Returns": "rm_code | None — RM currently serving this customer "
                         "(used for marginal_gain calculation)"},
            {"Callback": "projection_fn(customer_id, rm_code, period)",
              "Returns": "dict | None — {projected_pbt, ftp_mode} "
                         "or None if RM ineligible / data missing"},
        ]
        st.dataframe(pd.DataFrame(di_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Engine output structure:**")
        st.code('''
{
  "segment": "HNW",
  "period": "2025-12",
  "assignments": [
    {"customer_id": "C001", "rm_code": "RM002",
     "projected_pbt": 75000.0, "current_rm": "RM001",
     "marginal_gain": 25000.0, "upstream_ftp_mode": "on"},
    ...
  ],
  "total_potential_gain": 95000.0,    # sum of marginal gains
  "total_projected_pbt": 375000.0,    # sum of projected PBTs
  "provisional": False,                # data quality flag
  "data_quality_warning": None,        # narrative warning
  "meta": {
    "customers_in_segment": 5,
    "rms_in_segment": 3,
    "assignments_made": 5,
    "unassignable": [...],             # customers with no eligible RM
    "unassignable_count": 0,
    "rm_utilization": {"RM001": "1/2", "RM002": "2/3", "RM003": "2/2"},
    "upstream_ftp_modes": {"on": 15},  # count of projection calls
    "provisional_threshold_pct": 50.0,
    "algorithm": "greedy_capacity_constrained_v1",
    "algorithm_caveats": [...],
    "generated_at": "2026-05-01T..."
  }
}
        ''', language="json")

        st.markdown("**Algorithm: greedy_capacity_constrained_v1**")
        st.caption(
            "Engine ranks all (customer, RM) pairs by marginal gain "
            "(projected_pbt with new RM minus projected_pbt with current RM), "
            "then assigns greedily — highest marginal gain first, respecting "
            "RM capacity caps. **Engine's own caveat (surfaced in meta.algorithm_caveats)**: "
            "*\"Greedy with marginal-gain ordering. Hits optimal on labelled small "
            "fixtures; for >100 customers consider Hungarian / LP solver.\"* "
            "Production deployment with large segments should add a Hungarian-algorithm "
            "or Linear-Programming-solver wrapper.")

        st.markdown("**Rule 6 transparency:**")
        st.caption(
            "Customers with no eligible RM (projection returns None for all RMs) "
            "are surfaced in `meta.unassignable` with `reason` field. **Engine "
            "doesn't silently drop them** — caller can decide whether to expand "
            "RM pool, override capacity, or flag for manual handling.")

        st.markdown("**Provisional flag (data quality signal):**")
        st.caption(
            f"When ≥{int(PROVISIONAL_FTP_OFF_THRESHOLD*100)}% of projection calls "
            "return `ftp_mode='off'` (i.e. projected PBT computed without FTP), "
            "engine sets `provisional=True`. **Treat provisional outputs as "
            "directional, not authoritative** — the bank's RM allocation policy "
            "should ideally feed FTP-on projections for accurate marginal-gain "
            "calculations.")

        st.caption(
            "💡 **Strategic context — opens resource allocation axis**: v5.94 is "
            "the first integration on the resource allocation axis (capital/people "
            "deployment optimization), distinct from the customer-centric quartet "
            "(NBA + Segmentation + Churn + Profitability) and HR axis "
            "(retrospective + forward-looking + action-oriented). "
            "Future allocation work could include: branch resource allocation, "
            "marketing spend allocation, capital allocation across business units.")


# ════════════════════════════════════════════════════════════════
# TAB 7 — ENGINE REFERENCE (Standard #59 Cross-sell, integrated v5.89)
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    from utils.cross_sell_nba import (
        RECOMMENDABLE_PRODUCTS, NBA_RULE_WEIGHTS,
        NBA_HOT_THRESHOLD, NBA_WARM_THRESHOLD,
        PERSONAL_LOAN_MIN_INCOME_KES, MORTGAGE_MIN_INCOME_KES,
        CREDIT_CARD_MIN_INCOME_KES, INVESTMENT_MIN_BALANCE_KES,
        TERM_DEPOSIT_MIN_BALANCE_KES, MIN_TENURE_FOR_UNSECURED_DAYS,
        SPEC_DEVIATION_NOTE,
    )

    st.markdown("**Engine Constants Reference** (single source of truth)")

    st.markdown("**NBA rule weights** (sorted descending):")
    rule_descriptions = {
        "high_savings_signals_mortgage": "Savings ≥500K + no existing mortgage → recommend MORTGAGE",
        "high_income_no_credit_card": "Income ≥100K + no credit card → recommend CREDIT_CARD",
        "stable_balance_signals_investment": "Stable savings holder + no investment → recommend INVESTMENT",
        "current_acct_no_savings": "Current account holder + no savings → recommend SAVINGS",
        "lifecycle_new_no_card": "NEW lifecycle + no card + tenure-eligible → recommend CREDIT_CARD",
        "growing_lifecycle_no_term_deposit": "GROWTH + balance ≥50K + no TD → recommend TERM_DEPOSIT",
        "low_engagement_signals_savings": "Low balance + low tenure → recommend basic SAVINGS",
    }
    rule_rows = sorted(
        [{"Rule": rname,
           "Weight": w,
           "Description": rule_descriptions.get(rname, "—")}
         for rname, w in NBA_RULE_WEIGHTS.items()],
        key=lambda r: -r["Weight"])
    st.dataframe(pd.DataFrame(rule_rows),
                 use_container_width=True, hide_index=True)

    st.markdown("**Tier thresholds:**")
    tier_rows = [
        {"Tier": "🔥 HOT", "Score": f"≥{NBA_HOT_THRESHOLD}",
          "Action": "Follow up within 7 days"},
        {"Tier": "🌤️ WARM", "Score": f"{NBA_WARM_THRESHOLD}-{NBA_HOT_THRESHOLD-1}",
          "Action": "Include in routine engagement"},
        {"Tier": "❄️ COLD", "Score": f"<{NBA_WARM_THRESHOLD}",
          "Action": "Low priority"},
    ]
    st.dataframe(pd.DataFrame(tier_rows),
                 use_container_width=True, hide_index=True)

    st.markdown(f"**Recommendable products** ({len(RECOMMENDABLE_PRODUCTS)}):")
    st.caption(", ".join(RECOMMENDABLE_PRODUCTS))

    st.markdown("**Eligibility thresholds** (byte-for-byte from engine constants):")
    _min_inc_col = f"Min income ({currency_symbol()})"
    _min_bal_col = f"Min balance ({currency_symbol()})"
    elig_rows = [
        {"Product": "PERSONAL_LOAN",
          _min_inc_col: f"{int(PERSONAL_LOAN_MIN_INCOME_KES):,}",
          _min_bal_col: "—",
          "Min tenure (days)": MIN_TENURE_FOR_UNSECURED_DAYS},
        {"Product": "CREDIT_CARD",
          _min_inc_col: f"{int(CREDIT_CARD_MIN_INCOME_KES):,}",
          _min_bal_col: "—",
          "Min tenure (days)": MIN_TENURE_FOR_UNSECURED_DAYS},
        {"Product": "MORTGAGE",
          _min_inc_col: f"{int(MORTGAGE_MIN_INCOME_KES):,}",
          _min_bal_col: "—",
          "Min tenure (days)": "—"},
        {"Product": "INVESTMENT",
          _min_inc_col: "—",
          _min_bal_col: f"{int(INVESTMENT_MIN_BALANCE_KES):,}",
          "Min tenure (days)": "—"},
        {"Product": "TERM_DEPOSIT",
          _min_inc_col: "—",
          _min_bal_col: f"{int(TERM_DEPOSIT_MIN_BALANCE_KES):,}",
          "Min tenure (days)": "—"},
        {"Product": "SAVINGS / CURRENT / INSURANCE",
          _min_inc_col: "—",
          _min_bal_col: "—",
          "Min tenure (days)": "—"},
    ]
    st.dataframe(pd.DataFrame(elig_rows),
                 use_container_width=True, hide_index=True)

    st.markdown("**Spec deviation #9 — ML recommender deferred:**")
    st.warning(
        f"ℹ {SPEC_DEVIATION_NOTE}")
    st.caption(
        "Per Rule 7 (no silent ML predictions), the engine does NOT fall back to "
        "ML when no `ml_recommender_fn` is provided to `next_best_action_predict`. "
        "Production deployment can plug in an ML model via the `ml_recommender_fn` "
        "callback when available — until then, deterministic rule-based scoring "
        "is the primary path.")
