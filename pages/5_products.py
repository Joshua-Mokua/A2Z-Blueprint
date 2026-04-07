"""pages/5_products.py — Products module."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *

from pages._shared import load_shared_state

# Load session state
um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

st.markdown(
    "<div style='padding:14px 20px;background:#D35400;border-radius:10px;margin-bottom:16px'>"
    "<div style='color:white;font-size:16px;font-weight:500'>Products</div>"
    "<div style='color:rgba(255,255,255,0.75);font-size:11px;margin-top:2px'>Product lifecycle registry · Performance tracking</div>"
    "</div>", unsafe_allow_html=True)


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

pt1, pt2, pt3 = st.tabs(["📋 Registry", "➕ Add product", "📊 Lifecycle view"])

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
            h_clr      = {"On track":"#1D9E75","Needs review":"#BA7517",
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


# ── TAB 12: INTEGRATE — MD & EXECUTIVE COMMAND CENTRE ─────────────────────
