"""pages/16_product_arc_cockpit.py — Product Arc Cockpit (v10.151).

Locks the v10.46 Lean+Compact protocol amendment for the Product
module closure (9th closed arc). This page makes all 10 v10.142-v10.150
engines (ENH-131..140) operator-driveable from the browser.

Per Rule 1, every engine result renders with full provenance — inputs,
intermediates, basis="rule_based" or "rule_based+llm" tags, fallback
reasons when data missing, is_estimate flags surfaced.

Per Rule 7, every engine surfaces honestly:
- ENH-131 P&L: 10/16 products loss-making on fully-loaded basis
- ENH-132 Lifecycle: sunset is recommendation-only never auto-triggered
- ENH-133 Needs gap: severity_rationale logged for audit
- ENH-134 Competitive: NO_DATA explicit when no benchmark mapped
- ENH-135 CVP: trade_offs always surfaced; AI hook opt-in tagged
- ENH-136 Ranking: missing components renormalize, is_estimate flag
- ENH-137 Pricing: read-only; CONSTRAINED_BY_* surfaces binding limits
- ENH-138 Recommendation: AI opt-in; excluded products always surfaced
- ENH-139 Bundling: PROXY MODE disclosed via analysis_basis tag
- ENH-140 Dashboard: engine_status map captures any partial failures

This cockpit reads engines, never writes — except for ENH-132 lifecycle
transitions (the only intentional product-arc write), which go through
the explicit transition workflow (request → approve/reject) with full
audit trail in data/product_lifecycle.json.

Companion FastAPI router: utils/api_product.py exposes the same engine
methods over JSON for the planned React frontend. Cockpit and API
share the engine layer as source of truth.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

try:
    import streamlit as st
    import pandas as pd
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    st = None  # type: ignore
    pd = None  # type: ignore

# Engines
from utils.product_pnl_intelligence import ProductPnLIntelligence
from utils.product_lifecycle import ProductLifecycleEngine
from utils.customer_needs_analyzer import CustomerNeedsAnalyzer
from utils.product_competitive_intel import ProductCompetitiveIntelligence
from utils.product_cvp_builder import ProductCVPBuilder
from utils.product_ranking import ProductRankingEngine
from utils.dynamic_pricing import DynamicPricingEngine
from utils.product_recommendation import ProductRecommendationEngine
from utils.product_bundling import ProductBundlingIntelligence
from utils.product_analytics_dashboard import ProductAnalyticsDashboard

try:
    from pages._shared import load_shared_state
    from pages._access import require_access
    from utils.core_audit import audit_log
    SHARED_AVAILABLE = True
except ImportError:
    SHARED_AVAILABLE = False
    def load_shared_state():
        return {}
    def require_access(module: str, silent: bool = False):
        return True
    def audit_log(action: str, username: str, detail: str = "",
                    module: str = "", before: str = "", after: str = ""):
        pass


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------

if STREAMLIT_AVAILABLE:
    st.set_page_config(
        page_title="Product Arc Cockpit",
        page_icon="📦",
        layout="wide")

    if SHARED_AVAILABLE:
        load_shared_state()
        require_access("products")

    st.title("📦 Product Arc Cockpit")
    st.caption(
        "v10.151 closure — 10 engines (ENH-131..140) "
        "spanning P&L, lifecycle, customer needs, competitive position, "
        "CVPs, ranking, pricing, recommendations, bundling, and the "
        "unified analytics dashboard. All engines read-only except "
        "lifecycle transitions (audit-trailed).")

    # Engine instances cached at session level
    @st.cache_resource
    def _get_engines():
        pnl = ProductPnLIntelligence()
        lifecycle = ProductLifecycleEngine()
        needs = CustomerNeedsAnalyzer()
        competitive = ProductCompetitiveIntelligence()
        cvp = ProductCVPBuilder()
        ranking = ProductRankingEngine()
        pricing = DynamicPricingEngine()
        recommendation = ProductRecommendationEngine()
        bundling = ProductBundlingIntelligence()
        dashboard = ProductAnalyticsDashboard(
            pnl_engine=pnl, lifecycle_engine=lifecycle,
            needs_engine=needs, competitive_engine=competitive,
            cvp_engine=cvp, ranking_engine=ranking,
            pricing_engine=pricing,
            recommendation_engine=recommendation,
            bundling_engine=bundling)
        return {
            "pnl": pnl, "lifecycle": lifecycle, "needs": needs,
            "competitive": competitive, "cvp": cvp,
            "ranking": ranking, "pricing": pricing,
            "recommendation": recommendation, "bundling": bundling,
            "dashboard": dashboard,
        }

    engines = _get_engines()

    # ----------------------------------------------------------------
    # Tab layout — 7 thematic tabs grouping engines per workflow
    # (matches v10.46 ≤7-tab convention)
    # ----------------------------------------------------------------

    tabs = st.tabs([
        "📊 Dashboard",                # ENH-140 unified summary
        "💰 Profitability & Ranking",  # ENH-131 + ENH-136
        "🔄 Lifecycle",                # ENH-132
        "🎯 Customers & CVPs",         # ENH-133 + ENH-135
        "🏆 Competitive & Pricing",    # ENH-134 + ENH-137
        "🎁 Recommendations",          # ENH-138
        "🔗 Bundling",                 # ENH-139
    ])

    # Tab 1: Dashboard (ENH-140)
    with tabs[0]:
        st.subheader("Bank-wide Product Arc Summary (ENH-140)")
        try:
            summary = engines["dashboard"].get_summary_metrics()
            cols = st.columns(4)
            cols[0].metric("Products", summary["n_products"])
            margin = summary.get("portfolio_margin_pct")
            cols[1].metric("Portfolio Margin",
                            f"{margin}%" if margin is not None else "n/a")
            cols[2].metric(
                "Loss-making products",
                summary.get("n_loss_making_products", 0))
            cols[3].metric(
                "Competitive leadership",
                f"{summary.get('competitive_leadership_rate_pct', 0)}%")

            cols2 = st.columns(4)
            cols2[0].metric(
                "Avg ranking score",
                summary.get("avg_product_score", 0))
            dist = summary.get("ranking_distribution", {})
            cols2[1].metric("TOP_TIER", dist.get("TOP_TIER", 0))
            cols2[2].metric("WATCHLIST", dist.get("WATCHLIST", 0))
            cols2[3].metric(
                "Pricing actions pending",
                summary.get(
                    "n_actionable_pricing_recommendations", 0))

            st.divider()
            st.subheader("Per-Product Unified View")
            kpis = engines["dashboard"].get_product_arc_kpis()
            df = pd.DataFrame(kpis)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("Engine Health")
            health = engines["dashboard"].get_engine_health_check()
            if health.get("all_healthy"):
                st.success(
                    f"All {health['n_engines_checked']} engines healthy "
                    f"as of {health['checked_at_utc']}")
            else:
                st.warning(
                    f"{health['n_ok']}/{health['n_engines_checked']} "
                    f"engines healthy")
                for engine_id, status in health.get(
                        "per_engine", {}).items():
                    if not status.get("ok"):
                        st.error(
                            f"{engine_id}: "
                            f"{status.get('error_msg', 'unknown')}")
        except Exception as e:
            st.error(f"Dashboard load failed: {type(e).__name__}: {e}")

    # Tab 2: Profitability & Ranking (ENH-131 + ENH-136)
    with tabs[1]:
        st.subheader("P&L Intelligence (ENH-131)")
        st.caption(
            "Book-based P&L with fully-loaded costs. "
            "Three bands: profitable ≥5% margin / breakeven / loss-making.")
        try:
            bw = engines["pnl"].get_bank_wide_summary()
            cols = st.columns(4)
            cols[0].metric("Revenue (KES)",
                            f"{bw.get('total_revenue_kes', 0):,.0f}")
            cols[1].metric("Margin",
                            f"{bw.get('margin_pct', 0)}%")
            cols[2].metric("ROA", f"{bw.get('roa_pct', 0)}%")
            cols[3].metric("Loss-making",
                            f"{bw.get('n_loss_making', 0)}/"
                            f"{bw.get('n_products', 0)}")

            portfolio = engines["pnl"].compute_portfolio()
            rows = [p.as_dict() for p in portfolio]
            st.dataframe(pd.DataFrame(rows),
                          use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"P&L failed: {type(e).__name__}: {e}")

        st.divider()
        st.subheader("Product Ranking (ENH-136)")
        st.caption(
            "Multi-factor 0-100: profitability 30 + competitive 25 + "
            "growth 20 + risk 15 + scale 10. Bands: "
            "TOP_TIER ≥75 / GROWING / WATCHLIST / DECLINE.")
        try:
            dist = engines["ranking"].get_score_distribution()
            cols = st.columns(4)
            cols[0].metric("Avg score", dist.get("avg_score", 0))
            cols[1].metric("Top score", dist.get("top_score", 0))
            cols[2].metric("Bottom score", dist.get("bottom_score", 0))
            band = dist.get("by_band", {})
            cols[3].metric(
                "TOP_TIER + GROWING",
                band.get("TOP_TIER", 0) + band.get("GROWING", 0))

            ranked = engines["ranking"].rank_all_products()
            rows = [{
                "rank": i + 1, "product_id": s.product_id,
                "name": s.name, "category": s.category,
                "score": s.total_score, "band": s.band,
                "is_estimate": s.is_estimate,
                "components_missing": ", ".join(
                    s.components_missing) or "—",
            } for i, s in enumerate(ranked)]
            st.dataframe(pd.DataFrame(rows),
                          use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Ranking failed: {type(e).__name__}: {e}")

    # Tab 3: Lifecycle (ENH-132)
    with tabs[2]:
        st.subheader("Product Lifecycle Management (ENH-132)")
        st.caption(
            "Stage-gate workflow with config-driven approval matrix. "
            "Sunset is recommendation-only — never auto-triggered.")
        try:
            cands = engines["lifecycle"].get_sunset_candidates()
            st.metric("Sunset candidates", len(cands))
            if cands:
                st.dataframe(pd.DataFrame(cands),
                              use_container_width=True, hide_index=True)
            else:
                st.info("No products meet sunset criteria.")

            st.divider()
            st.subheader("Pending Approvals")
            pending = engines["lifecycle"].get_pending_approvals()
            if pending:
                st.dataframe(pd.DataFrame(pending),
                              use_container_width=True, hide_index=True)
            else:
                st.info("No pending stage-gate transitions.")
        except Exception as e:
            st.error(f"Lifecycle failed: {type(e).__name__}: {e}")

    # Tab 4: Customers & CVPs (ENH-133 + ENH-135)
    with tabs[3]:
        st.subheader("Customer Needs & Gap Analysis (ENH-133)")
        st.caption(
            "Three gap dimensions: portfolio-count + propensity + "
            "behavioural signals. severity_rationale logged for audit.")
        try:
            bw = engines["needs"].bank_wide_gap_summary()
            if bw.get("ok"):
                cols = st.columns(4)
                cols[0].metric(
                    "Customers", bw.get("n_customers_evaluated", 0))
                cols[1].metric(
                    "HIGH severity", bw.get("n_high_severity", 0))
                cols[2].metric(
                    "MEDIUM", bw.get("n_medium_severity", 0))
                cols[3].metric(
                    "HIGH rate",
                    f"{bw.get('high_severity_rate_pct', 0)}%")

                seg_rows = []
                for seg, summary in bw.get("by_segment", {}).items():
                    if summary.get("ok"):
                        seg_rows.append({
                            "segment": seg,
                            "n_customers": summary["n_customers"],
                            "n_high": summary["n_high_severity"],
                            "avg_portfolio_gap": summary[
                                "avg_portfolio_gap"],
                            "clv_at_risk": summary["clv_at_risk_kes"],
                        })
                if seg_rows:
                    st.dataframe(pd.DataFrame(seg_rows),
                                  use_container_width=True,
                                  hide_index=True)
        except Exception as e:
            st.error(f"Needs failed: {type(e).__name__}: {e}")

        st.divider()
        st.subheader("Customer Value Propositions (ENH-135)")
        st.caption(
            "Per-segment CVPs combining ENH-133 + ENH-134 + ENH-131. "
            "Trade-offs ALWAYS surfaced; AI hook opt-in with basis tag.")
        try:
            cvps = engines["cvp"].generate_all_segment_cvps()
            seg = st.selectbox("Segment", list(cvps.keys()),
                                 key="cvp_seg")
            if seg:
                cvp = cvps[seg]
                cols = st.columns(3)
                cols[0].metric("Strength score",
                                cvp.get("cvp_strength_score"))
                cols[1].metric("Band",
                                cvp.get("cvp_strength_band"))
                cols[2].metric("Basis", cvp.get("basis"))
                st.code(cvp.get("narrative", ""), language="text")
                if cvp.get("ai_warning"):
                    st.info(cvp["ai_warning"])
        except Exception as e:
            st.error(f"CVPs failed: {type(e).__name__}: {e}")

    # Tab 5: Competitive & Pricing (ENH-134 + ENH-137)
    with tabs[4]:
        st.subheader("Competitive Intelligence (ENH-134)")
        st.caption(
            "Per-product position vs Kenya peer banks. "
            "Direction-aware: lower lending, higher deposit = better.")
        try:
            summary = engines["competitive"].get_competitive_summary()
            cols = st.columns(4)
            cols[0].metric("LEADER", summary.get("n_leader", 0))
            cols[1].metric("FOLLOWER", summary.get("n_follower", 0))
            cols[2].metric("LAGGARD", summary.get("n_laggard", 0))
            cols[3].metric("Leadership rate",
                            f"{summary.get('leadership_rate_pct', 0)}%")

            gaps = engines["competitive"].identify_pricing_gaps(
                threshold_pct=0.5)
            if gaps:
                st.subheader("Pricing Gaps (|Δ|≥50bps)")
                st.dataframe(pd.DataFrame(gaps),
                              use_container_width=True,
                              hide_index=True)
        except Exception as e:
            st.error(f"Competitive failed: {type(e).__name__}: {e}")

        st.divider()
        st.subheader("Dynamic Pricing Recommendations (ENH-137)")
        st.caption(
            "Rule-based pricing recommendations. Read-only — engine "
            "never writes pricing. CONSTRAINED_BY_* surfaces binding "
            "limits.")
        try:
            actionable = engines["pricing"
                                  ].get_actionable_recommendations()
            st.metric("Actionable recommendations", len(actionable))
            if actionable:
                st.dataframe(pd.DataFrame(actionable),
                              use_container_width=True,
                              hide_index=True)
            with st.expander("All recommendations"):
                all_recs = engines["pricing"
                                    ].get_all_recommendations()
                st.dataframe(pd.DataFrame(all_recs),
                              use_container_width=True,
                              hide_index=True)
        except Exception as e:
            st.error(f"Pricing failed: {type(e).__name__}: {e}")

    # Tab 6: Recommendations (ENH-138)
    with tabs[5]:
        st.subheader("AI Product Recommendation Engine (ENH-138)")
        st.caption(
            "Per-customer next-best-product. Composite = 0.5×propensity + "
            "0.3×rank + 0.2×margin. AI hook opt-in. "
            "Excluded products always surfaced.")
        try:
            summary = engines["recommendation"
                              ].get_recommendation_summary()
            if summary.get("ok"):
                st.metric("Customers evaluated",
                            summary.get("n_customers_evaluated", 0))
                st.subheader(
                    "Top recommended products by frequency")
                st.dataframe(
                    pd.DataFrame(
                        summary.get("top_recommended_products", [])),
                    use_container_width=True, hide_index=True)
        except Exception as e:
            st.error(f"Recommendations failed: {type(e).__name__}: {e}")

    # Tab 7: Bundling (ENH-139)
    with tabs[6]:
        st.subheader("Product Bundling Intelligence (ENH-139)")
        st.caption(
            "Market basket analysis. PROXY MODE: products_held is "
            "integer count not list, so engine derives bundle affinity "
            "from propensity_scores. analysis_basis tag and "
            "is_estimate=True surface the limitation.")
        try:
            summary = engines["bundling"].get_bundling_summary()
            if summary.get("ok"):
                cols = st.columns(4)
                cols[0].metric("Pairs evaluated",
                                summary.get("n_pairs_evaluated", 0))
                cols[1].metric(
                    "Strong (lift>1.5)",
                    summary.get(
                        "n_strong_associations_lift_gt_1_5", 0))
                cols[2].metric(
                    "Positive (lift>1)",
                    summary.get(
                        "n_positive_associations_lift_gt_1", 0))
                cols[3].metric(
                    "Avg support",
                    f"{summary.get('avg_support_pct', 0)}%")
                st.info(
                    f"Analysis basis: **{summary['analysis_basis']}** "
                    f"(is_estimate={summary['is_estimate']})")
                st.caption(
                    summary.get("data_limitation_note", ""))

                st.subheader("Top bundles bank-wide")
                top = engines["bundling"].get_top_bundles(
                    min_affinity=0.0, top_n=10)
                if top:
                    st.dataframe(pd.DataFrame(top),
                                  use_container_width=True,
                                  hide_index=True)
        except Exception as e:
            st.error(f"Bundling failed: {type(e).__name__}: {e}")

    # Footer audit log
    try:
        _user = st.session_state.get("user_data", {}) if hasattr(st, "session_state") else {}
        audit_log(
            action="product_arc_cockpit.view",
            username=_user.get("username", "anonymous"),
            detail=f"viewed_at={datetime.now(timezone.utc).isoformat()}",
            module="products")
    except Exception:
        pass

else:
    # Streamlit not installed — module loads but renders nothing
    pass
