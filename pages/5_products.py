"""pages/5_products.py — Products module."""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
try:
    from utils.core import get_fiscal_year as _gfy
except: _gfy = lambda: _gfy()


from pages._shared import load_shared_state
from pages._access import require_access, get_my_scope
require_access("products_pricing.catalogue")

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update — called after every save action."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

@st.cache_data(ttl=60, show_spinner=False)
def _load_products():
    p = Path(__file__).parent.parent / "data" / "products.json"
    return a2z_db.load_json(p) if p.exists() else []

products = _load_products()



# Load session state
um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

st.markdown(
    "<div style=\'padding:16px 22px;background:#D35400;border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)\'><div style=\'display:flex;align-items:center;justify-content:space-between\'><div><div style=\'color:var(--color-background-primary);font-size:16px;font-weight:700;letter-spacing:-0.2px\'>Products</div><div style=\'color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px;font-weight:400\'>Product lifecycle registry · Performance tracking</div></div><div style=\'opacity:0.12;font-size:36px;line-height:1;color:white\'>◆</div></div></div>",
    unsafe_allow_html=True)


# Shared data
uploaded_file = st.session_state.get("uploaded_file")
staff_scores  = st.session_state.get("staff_scores", pd.DataFrame())
df_proc       = st.session_state.get("df_processed", pd.DataFrame())
filtered      = st.session_state.get("filtered_staff", pd.DataFrame())
all_months    = st.session_state.get("all_months", [])

st.subheader("Product registry")
st.caption("Track every banking product across its lifecycle — Assets, Liabilities, NFI, and Channels.")

# ── Category overview cards ───────────────────────────────────
cat_summary = prod_m.category_summary()
all_products = prod_m.get_products()

oc1,oc2,oc3,oc4 = st.columns(4)
for col, (cat, s) in zip([oc1,oc2,oc3,oc4], cat_summary.items()):
    cfg = PRODUCT_CATEGORIES[cat]
    col.markdown(
        f"<div style='padding:12px 14px;background:{cfg['bg']};"
        f"border-left:3px solid {cfg['color']};border-radius:0 8px 8px 0;height:100%'>"
        f"<div style='font-size:11px;color:{cfg['color']};font-weight:500'>{cfg['icon']} {cat}</div>"
        f"<div style='font-size:22px;font-weight:500;margin:4px 0'>{s['count']}</div>"
        f"<div style='font-size:11px;color:var(--color-text-secondary)'>"
        f"{s['active']} active · {s['in_pilot']} pilot · {s['at_risk']} at risk"
        f"</div></div>", unsafe_allow_html=True)

st.markdown("---")

pt1, pt2, pt3, pt4, pt5 = st.tabs(["📋 Registry", "➕ Add product", "📊 Lifecycle view", "📈 Performance", "🤖 Arc Engines"])

# ── Registry ─────────────────────────────────────────────────
with pt1:
    fc1,fc2,fc3,fc4 = st.columns(4)
    with fc1:
        cat_f = st.selectbox("Category", ["All"] + list(PRODUCT_CATEGORIES.keys()), key="pf_cat")
    with fc2:
        all_stages = list(PRODUCT_LIFECYCLE_STAGES.keys())
        stage_f = st.selectbox("Stage", ["All"] + all_stages, key="pf_stage")
    with fc3:
        health_f = st.selectbox("Health", ["All"] + PRODUCT_HEALTH_SIGNALS, key="pf_health")
    with fc4:
        search_p = st.text_input("Search", placeholder="Product name...", key="pf_search")

    prods_view = prod_m.get_products(
        category=None if cat_f=="All" else cat_f,
        stage=None if stage_f=="All" else stage_f,
        health=None if health_f=="All" else health_f)
    if search_p.strip():
        prods_view = [p for p in prods_view
                      if search_p.lower() in p.get("name","").lower()]

    if not prods_view:
        st.info("No products yet. Add your first product in 'Add product'.")
    else:
        for prod in prods_view:
            stage_cfg  = PRODUCT_LIFECYCLE_STAGES.get(prod.get("lifecycle_stage","Active"), {})
            cat_cfg    = PRODUCT_CATEGORIES.get(prod.get("category",""), {})
            health     = prod.get("health","On track")
            h_clr      = {"On track":"var(--brand-mid,#1D9E75)","Needs review":"#BA7517",
                           "At risk":"#E24B4A","Suspended":"#5F5E5A"}.get(health,"#888780")

            with st.expander(
                f"{cat_cfg.get('icon','')} {prod['name']}  ·  "
                f"{prod.get('category','')} / {prod.get('sub_category','')}  ·  "
                f"{prod.get('lifecycle_stage','')}"):

                pc1,pc2,pc3,pc4 = st.columns(4)
                pc1.markdown(
                    f"<span style='background:{stage_cfg.get('bg','#eee')};"
                    f"color:{stage_cfg.get('color','#333')};padding:3px 10px;"
                    f"border-radius:4px;font-size:12px;font-weight:500'>"
                    f"{prod.get('lifecycle_stage','')}</span>", unsafe_allow_html=True)
                pc2.markdown(
                    f"<span style='color:{h_clr};font-size:12px;font-weight:500'>"
                    f"● {health}</span>", unsafe_allow_html=True)
                pc3.markdown(f"**Owner:** {prod.get('owner','—')}")
                pc4.markdown(f"**Sponsor:** {prod.get('sponsor','—')}")

                if prod.get("description"):
                    st.caption(prod["description"])

                d1,d2,d3 = st.columns(3)
                d1.metric("Annual target", fmt_num(prod.get("annual_target",0), short=True))
                d2.metric("YTD actual",    fmt_num(prod.get("ytd_actual",0), short=True))
                d3.metric("Customers",     f"{prod.get('customer_count',0):,}")

                if prod.get("linked_kpis"):
                    st.caption(f"Linked KPIs: {', '.join(prod['linked_kpis'])}")
                if prod.get("linked_initiatives"):
                    init_names = []
                    for iid in prod["linked_initiatives"]:
                        init_obj = em.get_initiative(iid)
                        if init_obj: init_names.append(f"{iid} — {init_obj['name'][:30]}")
                    if init_names:
                        st.caption(f"Linked initiatives: {' | '.join(init_names)}")

                # Stage update
                cat_stages = PRODUCT_CATEGORIES.get(prod.get("category",""),{}).get("lifecycle",[])
                if cat_stages:
                    up1,up2,up3 = st.columns([2,2,1])
                    cur_i    = cat_stages.index(prod["lifecycle_stage"]) if prod.get("lifecycle_stage") in cat_stages else 0
                    new_st_p = up1.selectbox("Move to stage", cat_stages,
                                 index=cur_i, key=f"pst_{prod['id']}")
                    new_hlth = up2.selectbox("Health", PRODUCT_HEALTH_SIGNALS,
                                 index=PRODUCT_HEALTH_SIGNALS.index(health) if health in PRODUCT_HEALTH_SIGNALS else 0,
                                 key=f"phl_{prod['id']}")
                    if up3.button("Save", key=f"psv_{prod['id']}"):
                        prod_m.update_product(prod["id"],
                            {"lifecycle_stage": new_st_p, "health": new_hlth}, uname)
                        audit_log("PRODUCT_UPDATED", uname, f"{prod['id']}:{new_st_p}")
                        _bsc_trigger(uname, "K009")
                        st.rerun()

                # Notes
                note_txt = st.text_input("Add note", key=f"pnt_{prod['id']}")
                if st.button("Add note", key=f"pnb_{prod['id']}"):
                    if note_txt:
                        prod_m.add_note(prod["id"], note_txt, uname)
                        st.rerun()
                if prod.get("notes"):
                    for n in reversed(prod["notes"][-3:]):
                        st.caption(f"{n['date']} ({n['by']}): {n['note']}")

# ── Add product ───────────────────────────────────────────────
with pt2:
    st.subheader("Add new product")
    with st.form("add_product"):
        ac1,ac2 = st.columns(2)
        with ac1:
            p_name   = st.text_input("Product name *")
            p_cat    = st.selectbox("Category *", list(PRODUCT_CATEGORIES.keys()))
            sub_cats = list(PRODUCT_CATEGORIES[p_cat]["sub_categories"].keys()) if p_cat else []
            p_sub    = st.selectbox("Sub-category", sub_cats) if sub_cats else st.text_input("Sub-category")
            prod_types = PRODUCT_CATEGORIES[p_cat]["sub_categories"].get(p_sub, []) if p_cat and p_sub else []
            p_type   = st.selectbox("Product type", ["Custom..."] + prod_types) if prod_types else st.text_input("Product type")
            p_stage  = st.selectbox("Lifecycle stage",
                PRODUCT_CATEGORIES[p_cat]["lifecycle"] if p_cat else list(PRODUCT_LIFECYCLE_STAGES.keys()))
        with ac2:
            p_owner   = st.text_input("Product owner (username)")
            p_sponsor = st.text_input("Sponsor (Director name)")
            p_segment = st.selectbox("Target segment",
                ["Retail","SME","Corporate","All segments","Institutional"])
            p_launch  = st.date_input("Launch date")
            p_review  = st.date_input("Next review date")

        p_desc     = st.text_area("Description", height=70)
        p_kpis     = st.multiselect("Linked KPIs",
            PRODUCT_CATEGORIES[p_cat]["kpi_links"] + ["Other"] if p_cat else [],
            help="Which BSC KPIs does this product contribute to?")
        ac3,ac4 = st.columns(2)
        p_target = ac3.number_input("Annual target (KES or units)", min_value=0.0, step=1000000.0)
        p_cust   = ac4.number_input("Current customer count", min_value=0, step=100)

        # Link to initiative
        init_opts = ["None"] + [f"{i['id']} — {i['name'][:40]}" for i in em.get_initiatives(status='All')]
        p_init = st.selectbox("Link to initiative (optional)", init_opts)

        if st.form_submit_button("✅ Register product", type="primary"):
            if not p_name:
                st.error("Product name required.")
            else:
                linked_init = []
                if p_init != "None":
                    linked_init = [p_init.split(" — ")[0]]
                new_prod_id = prod_m.add_product({
                    "name": p_name, "category": p_cat,
                    "sub_category": p_sub, "product_type": p_type if p_type != "Custom..." else "",
                    "lifecycle_stage": p_stage, "health": "On track",
                    "owner": p_owner, "sponsor": p_sponsor,
                    "description": p_desc, "target_segment": p_segment,
                    "launch_date": str(p_launch), "review_date": str(p_review),
                    "linked_kpis": p_kpis, "linked_initiatives": linked_init,
                    "annual_target": p_target, "customer_count": p_cust,
                    "created_by": uname,
                })
                # Auto-link initiative back
                if linked_init:
                    prod_m.link_to_initiative(new_prod_id, linked_init[0])
                audit_log("PRODUCT_CREATED", uname, f"{new_prod_id}:{p_name}")
                _bsc_trigger(uname, "K009")
                st.success(f"Product {new_prod_id} registered!")
                st.rerun()

# ── Lifecycle view ────────────────────────────────────────────
with pt3:
    st.subheader("Lifecycle pipeline")
    st.caption("Products at each stage across all categories.")

    lc_summary = prod_m.lifecycle_summary()

    if not lc_summary:
        st.info("No products registered yet.")
    else:
        # Funnel by stage
        stage_order = ["Concept","Pilot","Planning","Development","Launch",
                       "Active","Growth","Optimising","Mature","Sunset","Decommissioned"]
        funnel_rows = []
        for s in stage_order:
            if s in lc_summary:
                cfg = PRODUCT_LIFECYCLE_STAGES.get(s, {})
                funnel_rows.append({"Stage": s, "Count": lc_summary[s],
                                    "Color": cfg.get("color","#888")})

        if funnel_rows:
            ff_df = pd.DataFrame(funnel_rows)
            fig_funnel = px.bar(ff_df, x="Stage", y="Count",
                                title="Products by lifecycle stage",
                                color="Stage",
                                color_discrete_map={r["Stage"]: r["Color"] for _, r in ff_df.iterrows()})
            fig_funnel.update_layout(showlegend=False, height=280,
                                      margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_funnel, use_container_width=True)

        # Category breakdown
        fig_cat = px.sunburst(
            pd.DataFrame([
                {"Category": p.get("category",""), "Stage": p.get("lifecycle_stage",""),
                 "Name": p.get("name","")}
                for p in prod_m.get_products()]),
            path=["Category","Stage","Name"],
            title="Product portfolio — category → stage → product")
        fig_cat.update_layout(height=500)
        st.plotly_chart(fig_cat, use_container_width=True)

        # Products needing review
        from_date = datetime.now().date()
        review_soon = [p for p in prod_m.get_products()
                       if p.get("review_date") and p["review_date"] >= str(from_date)
                       and p["review_date"] <= str(from_date + timedelta(days=30))]
        at_risk = [p for p in prod_m.get_products() if p.get("health") == "At risk"]

        if review_soon or at_risk:
            st.markdown("---")
            if review_soon:
                st.warning(f"📅 {len(review_soon)} product(s) due for review within 30 days")
                for p in review_soon:
                    st.caption(f"  {p['name']} — review date: {p['review_date']}")
            if at_risk:
                st.error(f"⚠️ {len(at_risk)} product(s) marked At Risk")
                for p in at_risk:
                    st.caption(f"  {p['name']} ({p['category']}) — owner: {p.get('owner','—')}")


with pt4:
    st.subheader("Product performance analytics")
    st.caption("KPI actuals linked to products — BSC data vs product targets.")

    all_prods = prod_m.get_products()
    if not all_prods or df_proc.empty:
        st.info("Upload BSC data and add products to see performance analytics.")
    else:
        # Use cascade targets if available (more accurate than upload targets)
        _casc_prod = st.session_state.get("cascade_manager")
        _bank_tgts = {}
        if _casc_prod:
            for _bk, _bv in (getattr(_casc_prod,"bank_targets",{}) or {}).items():
                if str(_bv.get("period","")) in (_gfy(),"2025"):
                    _kn = _bv.get("kpi","")
                    if _kn: _bank_tgts[_kn] = float(_bv.get("target",0))

        # Map products to their linked KPIs in df_proc
        perf_rows = []
        for prod in all_prods:
            for linked_kpi in (prod.get("linked_kpis") or []):
                kpi_rows = df_proc[df_proc["KPI"] == linked_kpi]
                if kpi_rows.empty: continue
                act_total = float(kpi_rows["YTD_Actual"].sum()) if "YTD_Actual" in kpi_rows.columns else 0
                # Prefer cascade/bank target over uploaded Annual Target
                tgt_total = _bank_tgts.get(linked_kpi) or float(kpi_rows["Annual Target"].sum())
                _tgt_src  = "📊" if linked_kpi in _bank_tgts else "📁"
                pct       = act_total/tgt_total*100 if tgt_total else 0
                perf_rows.append({
                    "Product":    prod["name"],
                    "Category":   prod.get("category",""),
                    "KPI":        linked_kpi,
                    "Target":     f"{_tgt_src} {fmt_num(tgt_total, True)}",
                    "YTD Actual": fmt_num(act_total, True),
                    "Achievement": f"{pct:.1f}%",
                    "_pct":       pct,
                    "Health":     prod.get("health","On track"),
                })

        if perf_rows:
            perf_df = pd.DataFrame(perf_rows)

            # Summary metrics
            pa1,pa2,pa3,pa4 = st.columns(4)
            pa1.metric("Products tracked", len(all_prods))
            pa2.metric("On track (≥90%)", int((perf_df["_pct"]>=90).sum()))
            pa3.metric("Needs review", int(((perf_df["_pct"]>=60)&(perf_df["_pct"]<90)).sum()))
            pa4.metric("At risk (<60%)", int((perf_df["_pct"]<60).sum()))

            # Chart
            fig_pa = px.bar(
                perf_df.sort_values("_pct"),
                x="_pct", y="Product", orientation="h",
                color="_pct",
                color_continuous_scale=["#E24B4A","#F5A623","var(--brand-primary,#006B3F)"],
                range_color=[0,130],
                title="Product KPI achievement (%)",
                labels={"_pct":"Achievement %","Product":"Product"})
            fig_pa.add_vline(x=100, line_dash="dash", line_color="#374151", line_width=1)
            fig_pa.update_layout(height=max(300,len(perf_rows)*32),
                                 coloraxis_showscale=False,
                                 plot_bgcolor="rgba(0,0,0,0)",
                                 paper_bgcolor="rgba(0,0,0,0)",
                                 margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_pa, use_container_width=True)

            # Detail table
            def _pa_hl(v):
                try:
                    p = float(str(v).replace("%",""))
                    if p >= 100: return "color:var(--brand-primary,#006B3F);font-weight:700"
                    if p >= 90:  return "color:var(--brand-mid,#1D9E75);font-weight:600"
                    if p >= 60:  return "color:#F5A623"
                    return "color:#E24B4A;font-weight:700"
                except: return ""
            disp_pa = perf_df.drop(columns=["_pct"])
            st.dataframe(
                disp_pa.style.map(_pa_hl, subset=["Achievement"]),
                use_container_width=True, hide_index=True)
        else:
            st.info("No linked KPI data found. Link KPIs to products in the Registry tab.")

# ── TAB 12: INTEGRATE — MD & EXECUTIVE COMMAND CENTRE ─────────────────────


# ──────────────────────────────────────────────────────────────────────
# Section 5: 🤖 Arc Engines (absorbed from 16_product_arc_cockpit.py
# in v10.204 per the architectural reorganization sub-campaign.
# 10 Product engines (ENH-131..140) presented as 7 nested sub-tabs
# spanning the product lifecycle: Dashboard, Profitability & Ranking,
# Lifecycle, Customers & CVPs, Competitive & Pricing, Recommendations,
# Bundling. Read-only display except for ENH-132 lifecycle transitions
# (request → approve/reject) with full audit trail. Mirrors the v10.202
# Treasury and v10.203 Strategy absorption patterns.
# ──────────────────────────────────────────────────────────────────────
with pt5:
    from datetime import datetime as _dt_pa, timezone as _tz_pa

    try:
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
        _ARC_PRODUCT_AVAILABLE = True
    except ImportError as _ie:
        st.error(f"Product arc engines unavailable: {_ie}")
        _ARC_PRODUCT_AVAILABLE = False

    if _ARC_PRODUCT_AVAILABLE:
        st.caption(
            "v10.204 absorbed from 16_product_arc_cockpit.py — 10 engines "
            "(ENH-131..140) spanning product P&L, lifecycle, customer needs, "
            "competitive intelligence, CVP, ranking, pricing, "
            "recommendations, bundling, and unified dashboard. Read-only "
            "except ENH-132 lifecycle transitions which go through "
            "request → approve/reject with full audit trail.")

        # Engine dependencies: dashboard takes the other 9 as constructor args.
        # Cache at session level for performance.
        @st.cache_resource
        def _get_arc_product_engines():
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

        engines = _get_arc_product_engines()

        arc_tabs = st.tabs([
            "📊 Dashboard",
            "💰 Profitability & Ranking",
            "🔄 Lifecycle",
            "🎯 Customers & CVPs",
            "🏆 Competitive & Pricing",
            "🎁 Recommendations",
            "🔗 Bundling",
        ])

        with arc_tabs[0]:
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

        with arc_tabs[1]:
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

        with arc_tabs[2]:
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

        with arc_tabs[3]:
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

        with arc_tabs[4]:
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

        with arc_tabs[5]:
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

        with arc_tabs[6]:
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
            audit_log(
                action="product_arc_engines.view",
                username=ud.get("username", "anonymous"),
                detail=f"viewed_at={_dt_pa.now(_tz_pa.utc).isoformat()}",
                module="products")
        except Exception:
            pass
