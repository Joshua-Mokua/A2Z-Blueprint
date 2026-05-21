"""
utils/propositions_hub_render.py — v10.347 (Option E, sub-batch 3).

Single source of truth for the 2 Propositions render functions.
Extracted from pages/27_propositions and pages/92_propositions_workbench.
The original 2 pages now import their render function from here;
pages/117_propositions_hub.py is the consolidated entry point with
an area selector at top.

Helper functions like _load_props() that needed namespacing have been
renamed with a domain prefix to avoid cache key collisions.
"""

from __future__ import annotations

from __future__ import annotations
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import json
import pandas as pd
import streamlit as st

from utils.core_audit import audit_log
from utils.customer_behavioral_profile import BehavioralProfileEngine
from utils.db import db as a2z_db
from utils.dynamic_cohorts import DynamicCohortsEngine, COHORT_STATES, AUTO_UPDATE_TRIGGERS
from utils.page_access import require_access
from utils.page_shared import load_shared_state
from utils.propositions_ab_testing import PropositionABTestingEngine, EXPERIMENT_STATES, EXPERIMENT_OUTCOMES, DEFAULT_ALPHA, MIN_SAMPLE_SIZE_PER_VARIANT
from utils.propositions_analytics import PropositionAnalyticsEngine, PROPOSITION_KPIS, ATTRITION_REASONS
from utils.propositions_catalog import PropositionsCatalogEngine, PROPOSITION_STATES, APPROVAL_LEVELS, APPROVAL_DECISIONS
from utils.propositions_eligibility import PropositionsEligibilityEngine, ELIGIBILITY_GATES, ELIGIBILITY_OUTCOMES
from utils.propositions_orchestration import PropositionOrchestrationEngine, CHANNEL_PRIORITIES
from utils.propositions_presentation import PropositionsPresentationEngine, PRESENTATION_CHANNELS
from utils.propositions_pricing import PropositionPricingEngine, PRICING_STRATEGIES, PRICING_STATES, DEFAULT_FLOOR_PCT, DEFAULT_CEILING_PCT


# ════════════════════════════════════════════════════════════════
# PROPOSITIONS_PERFORMANCE — render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/27_propositions.py — Proposition / Segment Overlay Performance.
Horizontal units (Women Banking, Diaspora, SME, Agri, Trade Finance, etc.)
track INFLUENCE KPIs, not portfolio volumes — zero double-counting.
"""


def render_propositions_performance(actor: str) -> None:
    """Render the propositions_performance view. Body extracted from
    pages/<original>.py."""

    DATA = Path(__file__).parent.parent / "data"
    um, ud, uname, *_ = load_shared_state()

    @st.cache_data(ttl=60, show_spinner=False)
    def _propositions_performance_load_props():
        f = DATA / "proposition_performance.json"
        return a2z_db.load_json(f) if f.exists() else {}

    @st.cache_data(ttl=60, show_spinner=False)
    def _propositions_performance_load_tags():
        f = DATA / "segment_tags.json"
        return a2z_db.load_json(f) if f.exists() else {}

    @st.cache_data(ttl=30, show_spinner=False)
    def _load_cfg():
        f = DATA / "proposition_config.json"
        return a2z_db.load_json(f) if f.exists() else {"propositions": {}}

    props   = _propositions_performance_load_props()
    tags    = _propositions_performance_load_tags()
    pcfg    = _load_cfg()
    # Merge live config into performance data so page always reflects current targets/names
    for _tag, _pcfg_prop in pcfg.get("propositions", {}).items():
        if _tag in props:
            # Update name, icon, color, kpi targets from config (config is source of truth)
            props[_tag]["name"]        = _pcfg_prop.get("name",  props[_tag].get("name",""))
            props[_tag]["icon"]        = _pcfg_prop.get("icon",  props[_tag].get("icon",""))
            props[_tag]["color"]       = _pcfg_prop.get("color", props[_tag].get("color",""))
            props[_tag]["description"] = _pcfg_prop.get("description", props[_tag].get("description",""))
            props[_tag]["head_name"]   = ""
            # Update KPI targets from config
            cfg_kpi_tgts = {k["id"]: k["target"] for k in _pcfg_prop.get("kpis", [])}
            for kpi in props[_tag].get("kpis", []):
                if kpi["id"] in cfg_kpi_tgts:
                    kpi["target"] = cfg_kpi_tgts[kpi["id"]]
    # Filter to active only
    props = {t: p for t, p in props.items()
             if pcfg.get("propositions", {}).get(t, {}).get("active", True)}
    role  = ud.get("role",""); sc = str(ud.get("staff_code","") or "")
    is_admin   = ud.get("is_admin",False)
    is_exec    = any(x in role for x in ("Chief","Director","Head","Managing"))

    # ── Header ─────────────────────────────────────────────────────────
    st.markdown(
        "<div style='padding:16px 0 8px'>"
        "<span style='font-size:22px;font-weight:800'>🎯 Propositions</span>"
        "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
        "Segment overlay scorecard · No double-counting · Influence metrics</span></div>",
        unsafe_allow_html=True)

    # Explain the model
    with st.expander("ℹ️ How proposition tracking works — no double-counting", expanded=False):
        st.markdown("""
    **Two layers, different KPIs:**

    | Layer | Who owns it | What is measured | Source |
    |-------|-------------|-----------------|--------|
    | **Primary Portfolio** | Branch RM / Corporate RM | Deposits, Loans, NFI, NPL, New Accounts | CBS (direct) |
    | **Proposition Overlay** | Proposition Head / Specialist RM | Acquired customers, Penetration %, Wallet share, Events, NPS | Tagged customers |

    **The key distinction:** A woman-owned business in Hassan's portfolio contributes to his
    deposit and loan targets. The **Women Banking unit does NOT claim those deposits** —
    instead they track *how many* women customers the bank has, *what share* of their wallet
    is with us, and *how deeply* they are penetrated with products. These are **influence metrics**,
    not volume metrics, so there is no double-counting.

    **Segment tags** are applied to CIF records. A customer can carry multiple tags
    (e.g. WB + SME). The proposition scorecard aggregates across all branches — it is a
    **bank-wide cross-cutting view**, not a branch P&L view.
    """)

    if is_admin:
        st.markdown(
            "⚙️ [Configure propositions in Admin → Propositions tab](/Admin) — "
            "add/remove propositions, edit KPIs and targets, toggle active/inactive.",
            unsafe_allow_html=False)

    if not props:
        st.info("No proposition data found. Run generate_propositions.py to initialise.")
        st.stop()

    # ── Overview scorecard ─────────────────────────────────────────────
    st.markdown("### Bank-wide proposition performance")
    prop_list = list(props.values())
    cols = st.columns(min(4, len(prop_list)))
    for i, prop in enumerate(sorted(prop_list, key=lambda x:-x["proposition_score"])):
        col = cols[i % len(cols)]
        score = prop["proposition_score"]
        color = prop["color"]
        clr_score = "#16A34A" if score >= 3.5 else "#D97706" if score >= 2.5 else "#DC2626"
        col.markdown(
            f"<div style='background:{color}10;border:1.5px solid {color}40;"
            f"border-radius:12px;padding:14px;text-align:center;margin-bottom:10px'>"
            f"<div style='font-size:22px'>{prop['icon']}</div>"
            f"<div style='font-size:12px;font-weight:700;color:{color};margin:4px 0'>"
            f"{prop['name']}</div>"
            f"<div style='font-size:28px;font-weight:800;color:{clr_score}'>"
            f"{score:.2f}</div>"
            f"<div style='font-size:10px;color:var(--color-text-tertiary)'>"
            f"{prop['total_tagged_customers']:,} tagged customers</div>"
            f"</div>",
            unsafe_allow_html=True)
        if (i+1) % 4 == 0 and i+1 < len(prop_list):
            cols = st.columns(min(4, len(prop_list)-(i+1)))

    st.markdown("---")

    # ── Proposition detail tabs ────────────────────────────────────────
    prop_names = [f"{p['icon']} {p['name']}" for p in prop_list]
    sel_tab = st.selectbox("Select proposition to view:", prop_names, key="prop_sel")
    # v10.353 — defensive: fall back to first prop if selection doesn't match
    # any registered proposition (avoid StopIteration in edge cases).
    sel_tag = next(
        (t for t, p in props.items() if f"{p['icon']} {p['name']}" == sel_tab),
        next(iter(props), None),
    )
    if sel_tag is None:
        st.warning("No propositions are currently registered.")
        return
    prop = props[sel_tag]

    color = prop["color"]
    st.markdown(
        f"<div style='background:{color}08;border:1px solid {color}30;"
        f"border-radius:12px;padding:16px;margin:8px 0'>"
        f"<span style='font-size:20px'>{prop['icon']}</span> "
        f"<b style='font-size:18px;color:{color}'>{prop['name']}</b> "
        f"<span style='color:var(--color-text-secondary);font-size:13px'>· {prop['description']}</span><br>"
        f"<span style='font-size:12px;color:var(--color-text-tertiary)'>"
        f"Head: {prop['head_name'] or 'Not assigned'} · "
        f"Tagged customers: {prop['total_tagged_customers']:,} · "
        f"Period: {prop['period']}</span>"
        f"</div>",
        unsafe_allow_html=True)

    tabs = st.tabs(["📊 KPI Scorecard","📈 Trend","🌿 Branch Contribution","👥 RM Champions","📋 About"])

    # ── TAB 1: KPI Scorecard ───────────────────────────────────────────
    with tabs[0]:
        kpis = prop["kpis"]
        overall = prop["proposition_score"]
        score_color = "#16A34A" if overall>=3.5 else "#D97706" if overall>=2.5 else "#DC2626"
        score_label = ("Outstanding" if overall>=4.5 else "Exceeds Expectations" if overall>=3.5
                       else "Meets Expectations" if overall>=2.5 else "Needs Improvement" if overall>=2.0
                       else "Below Expectations")
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:20px;margin-bottom:16px'>"
            f"<div style='text-align:center'>"
            f"<div style='font-size:42px;font-weight:800;color:{score_color}'>{overall:.2f}</div>"
            f"<div style='font-size:12px;color:{score_color};font-weight:600'>{score_label}</div>"
            f"<div style='font-size:10px;color:var(--color-text-tertiary)'>/ 5.0</div>"
            f"</div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
            f"Proposition BSC score based on {len(kpis)} influence KPIs.<br>"
            f"<b>These metrics do not overlap with portfolio BSC KPIs</b> — "
            f"no deposit or loan volumes are counted here unless explicitly proposition-specific."
            f"</div></div>",
            unsafe_allow_html=True)

        # KPI rows
        from utils.core import fmt_kpi_value
        for kpi in sorted(kpis, key=lambda x: -x["score"]):
            tgt = kpi["target"]; act = kpi["actual"]; ach = kpi["achievement"]
            score = kpi["score"]; wt = kpi["weight"]
            is_rev = kpi["direction"] == "lower"
            score_clr = "#16A34A" if score>=3.5 else "#D97706" if score>=2.5 else "#DC2626"
            ach_clr   = "#16A34A" if (ach>=100 and not is_rev) or (ach>=100 and is_rev) else "#DC2626"
            ach_lbl   = f"{ach:.1f}%"
            tgt_disp  = fmt_kpi_value(tgt, kpi["name"], short=True)
            act_disp  = fmt_kpi_value(act, kpi["name"], short=True)

            # Progress bar (capped at 130%)
            bar_pct = min(ach / 130 * 100, 100)
            bar_clr = "#16A34A" if ach >= 100 else "#D97706" if ach >= 80 else "#DC2626"

            st.markdown(
                f"<div style='background:var(--color-background-secondary);"
                f"border-radius:8px;padding:10px 14px;margin-bottom:6px'>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:6px'>"
                f"<div style='font-size:13px;font-weight:600'>{kpi['name']}</div>"
                f"<div style='display:flex;gap:12px;font-size:12px'>"
                f"<span style='color:var(--color-text-tertiary)'>Tgt: {tgt_disp}</span>"
                f"<span style='color:var(--color-text-secondary)'>Act: {act_disp}</span>"
                f"<span style='color:{ach_clr};font-weight:700'>{ach_lbl}</span>"
                f"<span style='background:{score_clr};color:white;border-radius:10px;"
                f"padding:1px 8px;font-weight:700'>{score:.1f}</span>"
                f"<span style='color:var(--color-text-tertiary)'>wt {wt:.0%}</span>"
                f"</div></div>"
                f"<div style='background:#F3F4F6;border-radius:3px;height:5px'>"
                f"<div style='width:{bar_pct:.0f}%;background:{bar_clr};"
                f"height:100%;border-radius:3px'></div>"
                f"</div></div>",
                unsafe_allow_html=True)

    # ── TAB 2: Trend ──────────────────────────────────────────────────
    with tabs[1]:
        st.markdown("**12-month trend** for each KPI")
        # Show trend for first 3 KPIs
        for kpi in kpis[:4]:
            trend = kpi.get("monthly_trend",[])
            if not trend: continue
            months = [t["month"] for t in trend]
            values = [t["value"] for t in trend]
            df_t = pd.DataFrame({"Month":months, kpi["name"]:values})
            st.markdown(f"**{kpi['name']}** (target: {fmt_kpi_value(kpi['target'],kpi['name'],True)})")
            st.line_chart(df_t.set_index("Month"))

    # ── TAB 3: Branch Contribution ────────────────────────────────────
    with tabs[2]:
        st.markdown(
            "**Branch contribution** — which branches have the most tagged customers "
            "for this proposition. Branches are ranked by tagged customer count.")
        bc = sorted(prop.get("branch_contributions",[]), key=lambda x:-x.get("tagged_customers",0))
        if bc:
            rows = [{
                "Branch": b["branch"][:30],
                "Tagged Customers": b["tagged_customers"],
                "Proposition Score": b["proposition_score"],
                "Champion RM": b.get("champion_rm","—"),
            } for b in bc]
            df_bc = pd.DataFrame(rows)
            st.dataframe(df_bc, use_container_width=True, hide_index=True)
            total_tagged = sum(b["tagged_customers"] for b in bc)
            st.caption(
                f"Total tagged customers across {len(bc)} branches: **{total_tagged:,}**. "
                f"Note: These customers also appear in branch RM portfolios — no double-counting "
                f"because proposition uses influence KPIs, not portfolio volumes.")
        else:
            st.info("No branch contribution data available.")

    # ── TAB 4: RM Champions ───────────────────────────────────────────
    with tabs[3]:
        st.markdown(
            "**Contributing RMs** — relationship managers whose portfolios include "
            "tagged customers for this proposition.")
        rm_codes = prop.get("contributing_rms",[])
        if rm_codes:
            rm_rows = []
            for rm_sc in rm_codes[:20]:
                rm_user = next(((u,d) for u,d in um.users.items()
                                if str(d.get("staff_code","")) == rm_sc), (None,{}))
                if rm_user[0]:
                    rm_rows.append({
                        "Staff Code": rm_sc,
                        "Name": rm_user[1].get("full_name","")[:30],
                        "Role": rm_user[1].get("role","")[:35],
                        "Unit": rm_user[1].get("unit","")[:25],
                    })
            if rm_rows:
                st.dataframe(pd.DataFrame(rm_rows), use_container_width=True, hide_index=True)
            st.info(
                f"💡 These RMs' portfolio customers are **tagged** with the "
                f"{prop['icon']} {prop['name']} segment code. Their portfolio BSC is unchanged "
                f"— only the proposition overlay benefits from the tagging.")
        else:
            st.info("No RM data for this proposition.")

    # ── TAB 5: About ──────────────────────────────────────────────────
    with tabs[4]:
        st.markdown(f"### {prop['icon']} {prop['name']} — Proposition Overview")
        st.markdown(f"**What this measures:** {prop['description']}")
        st.markdown("""
    **Why it's different from the branch BSC:**
    The branch BSC measures portfolio ownership — every deposit, loan and fee income
    attributed to a relationship manager's CBS portfolio. That's the P&L view.

    The proposition scorecard measures **market development** — how effectively the
    bank is building this customer segment, regardless of which branch or RM holds
    the customer. A Women Banking customer managed by Hassan in Thika branch still
    contributes to the Women Banking proposition score, but Hassan's portfolio BSC
    is not affected by the WB scoring.
    """)
        st.markdown(f"**KPIs in this scorecard:** {len(prop['kpis'])}")
        _kpi_rows = ["| KPI | Target | Actual | Achievement | Weight |",
                     "|-----|--------|--------|-------------|--------|"]
        for k in prop['kpis']:
            _kpi_rows.append(
                f"| {k['name']} | {fmt_kpi_value(k['target'],k['name'],True)} | "
                f"{fmt_kpi_value(k['actual'],k['name'],True)} | "
                f"{k['achievement']:.1f}% | {k['weight']:.0%} |")
        st.markdown("\n".join(_kpi_rows))
        st.markdown(
            f"**Tagged customers:** {prop['total_tagged_customers']:,} CIFs carry the "
            f"`{sel_tag}` segment tag.  **Period:** {prop['period']} (Jan–Dec)")


# ════════════════════════════════════════════════════════════════
# PROPOSITIONS_WORKBENCH — render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/92_propositions_workbench.py — Propositions Workbench.

User-facing page exposing the v10.277 Propositions cluster end-to-end.
Following the v10.276 pattern: every cluster batch ships a UI page
alongside its engines.

Engines consumed (8 modules, 10 standards):
    - PropositionsCatalogEngine          (#349 + #350)
    - PropositionsEligibilityEngine      (#351)
    - PropositionPricingEngine           (#352, with Rule 7 hook)
    - PropositionOrchestrationEngine     (#353)
    - PropositionAnalyticsEngine         (#354)
    - PropositionABTestingEngine         (#355)
    - DynamicCohortsEngine               (#356)
    - PropositionsPresentationEngine     (#357 + #358)

CBK Product Governance compliance is surfaced in Tab 1 (Catalog) via
the multi-level approval status panel.
"""


def render_propositions_workbench(actor: str) -> None:
    """Render the propositions_workbench view. Body extracted from
    pages/<original>.py."""

    # ── State + roles ────────────────────────────────────────────────
    um, ud, uname, *_ = load_shared_state()[:12]
    role = ud.get("role", "")
    name = ud.get("full_name", "")
    is_admin = ud.get("is_admin", False)
    is_pm = any(x in role.lower() for x in
                  ("product", "marketing", "head", "general manager"))


    # ── Engine bootstrap ──────────────────────────────────────────────
    @st.cache_resource(show_spinner=False)
    def _bootstrap_engines():
        catalog = PropositionsCatalogEngine()
        eligibility = PropositionsEligibilityEngine(catalog=catalog)
        pricing = PropositionPricingEngine(catalog=catalog)
        orchestration = PropositionOrchestrationEngine(
            catalog=catalog, eligibility=eligibility, pricing=pricing,
        )
        analytics = PropositionAnalyticsEngine(
            catalog=catalog, orchestration=orchestration,
        )
        ab = PropositionABTestingEngine(catalog=catalog)
        profile = BehavioralProfileEngine()
        cohorts = DynamicCohortsEngine(profile=profile)
        presentation = PropositionsPresentationEngine(
            catalog=catalog, eligibility=eligibility,
            pricing=pricing, orchestration=orchestration,
        )
        return {
            "catalog": catalog, "eligibility": eligibility, "pricing": pricing,
            "orchestration": orchestration, "analytics": analytics,
            "ab": ab, "cohorts": cohorts, "presentation": presentation,
        }


    engines = _bootstrap_engines()


    # ── Header ────────────────────────────────────────────────────────
    st.markdown(
        "<div style='padding:16px 0 4px'>"
        "<span style='font-size:22px;font-weight:800'>🎁 Propositions Workbench</span>"
        "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
        "Catalog · Eligibility · Pricing · NBA · Analytics · A/B · Cohorts · Channels"
        "</span></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Powered by v10.277 Propositions cluster (8 engines, 10 standards). "
        "CBK Product Governance compliance via 5-level approval workflow."
    )


    # ── Tabs ──────────────────────────────────────────────────────────
    TABS = ["📋 Catalog & Approval", "🚪 Eligibility Check",
            "🎯 NBA Preview", "💰 Pricing & Fairness",
            "📊 Performance KPIs", "🧪 A/B Experiments",
            "🧭 Dynamic Cohorts", "📺 Channel Presentation"]
    tabs = st.tabs(TABS)


    # ─────────────────────────────────────────────────────────────────
    # TAB 1 — Catalog & Approval (#349 + #350)
    # ─────────────────────────────────────────────────────────────────
    with tabs[0]:
        st.markdown("##### Proposition catalog with multi-level approval workflow")

        propositions = engines["catalog"].list_propositions()
        if not propositions:
            st.info(
                "No propositions registered yet. Use the Quick Register form "
                "below to create one. CBK PG requires multi-level approval before "
                "activation: PRODUCT_HEAD → RISK_OFFICER → COMPLIANCE_OFFICER → "
                "FINANCE_OFFICER → MD."
            )
        else:
            # Summary KPIs
            by_state = {}
            for p in propositions:
                by_state[p.get("state", "?")] = by_state.get(p.get("state", "?"), 0) + 1
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total propositions", len(propositions))
            c2.metric("LIVE", by_state.get("LIVE", 0))
            c3.metric("In approval", by_state.get("IN_APPROVAL", 0))
            c4.metric("Drafts", by_state.get("DRAFT", 0))

            # Catalog table
            rows = []
            for p in propositions:
                rows.append({
                    "ID": p["proposition_id"],
                    "Name": p.get("name", "—"),
                    "Version": p.get("version", 1),
                    "State": p.get("state", "—"),
                    "Owner": p.get("owner_role", "—"),
                    "Segments": ", ".join(p.get("target_segments", [])) or "any",
                    "Channels": ", ".join(p.get("channels", [])) or "—",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)

            # Approval status drill-down
            st.markdown("##### Approval status (CBK PG audit trail)")
            prop_choice = st.selectbox(
                "Inspect approval status",
                [p["proposition_id"] for p in propositions],
                key="prop_inspect",
            )
            if prop_choice:
                status = engines["catalog"].approval_status(prop_choice)
                if status.get("reason") == "no_approval_records":
                    st.info(
                        "No approval records yet. Submit for approval to start "
                        "the 5-level review chain."
                    )
                else:
                    rows = []
                    for level in APPROVAL_LEVELS:
                        info = status["per_level"].get(level, {})
                        rows.append({
                            "Level": level,
                            "Decision": info.get("decision", "PENDING"),
                            "Approver": info.get("actor") or "—",
                            "Decided at": info.get("decided_at") or "—",
                            "Notes": info.get("notes", "") or "—",
                        })
                    st.dataframe(pd.DataFrame(rows), hide_index=True,
                                    use_container_width=True)
                    if status["all_levels_decided"]:
                        st.success("All 5 approval levels decided.")
                    else:
                        pending = sum(
                            1 for level in APPROVAL_LEVELS
                            if status["per_level"].get(level, {}).get("decision") == "PENDING"
                        )
                        st.warning(f"{pending} level(s) still PENDING.")

        # Quick register
        if is_admin or is_pm:
            with st.expander("➕ Register new proposition (DRAFT)"):
                with st.form("new_prop_form"):
                    pid = st.text_input("Proposition ID")
                    pname = st.text_input("Name")
                    pdesc = st.text_area("Description", height=68)
                    segs = st.multiselect(
                        "Target segments",
                        ["WOMEN", "DIASPORA", "ASSET_FINANCE",
                         "AGRI", "YOUTH", "SME"],
                    )
                    chans = st.multiselect(
                        "Channels",
                        list(CHANNEL_PRIORITIES),
                        default=["MOBILE_APP", "BRANCH"],
                    )
                    if st.form_submit_button("Register"):
                        r = engines["catalog"].register_proposition(
                            {"proposition_id": pid, "name": pname,
                             "owner_role": role or "product",
                             "description": pdesc,
                             "target_segments": segs, "channels": chans},
                            actor=uname or "user",
                        )
                        if r["registered"]:
                            st.success(f"Registered {pid} in DRAFT")
                            audit_log(uname or "user",
                                         "register_proposition", pid)
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error')}")


    # ─────────────────────────────────────────────────────────────────
    # TAB 2 — Eligibility Check (#351)
    # ─────────────────────────────────────────────────────────────────
    with tabs[1]:
        st.markdown("##### Real-time eligibility evaluation across 7 gates")
        st.caption(
            "Gates: " + " · ".join(ELIGIBILITY_GATES)
        )

        propositions = engines["catalog"].list_propositions(state="LIVE")
        if not propositions:
            st.info("No LIVE propositions yet. Approve and activate one first.")
        else:
            prop_choice = st.selectbox(
                "Proposition",
                [p["proposition_id"] for p in propositions],
                format_func=lambda x: next(
                    (p["name"] for p in propositions
                      if p["proposition_id"] == x), x),
                key="elig_prop",
            )

            c1, c2, c3 = st.columns(3)
            cust_id = c1.text_input("Customer ID", value="CUST-DEMO-001",
                                        key="elig_cust")
            age = c2.number_input("Age", 18, 120, 35, key="elig_age")
            balance_kes = c3.number_input(
                "Balance KES", 0, 10**8, 200_000, key="elig_balance",
            )
            c4, c5, c6 = st.columns(3)
            kyc = c4.selectbox(
                "KYC", ["COMPLETE", "PENDING", "EXPIRED", "NONE"],
                key="elig_kyc",
            )
            seg = c5.selectbox(
                "Segment",
                ["", "WOMEN", "DIASPORA", "ASSET_FINANCE", "AGRI", "YOUTH", "SME"],
                key="elig_seg",
            )
            risk = c6.selectbox(
                "Risk appetite",
                ["", "CONSERVATIVE", "MODERATE", "ADVENTUROUS"],
                key="elig_risk",
            )
            c7, c8, c9 = st.columns(3)
            aml = c7.selectbox(
                "AML status",
                ["CLEARED", "FLAGGED", "UNDER_REVIEW"], key="elig_aml",
            )
            pep = c8.checkbox("PEP", key="elig_pep")
            sanctions = c9.checkbox("Sanctions listed", key="elig_sanc")

            if cust_id and prop_choice:
                attrs = {
                    "customer_id": cust_id,
                    "kyc_status": kyc,
                    "segment": seg or None,
                    "age": age,
                    "aml_status": aml,
                    "pep_status": pep,
                    "sanctions_listed": sanctions,
                    "risk_appetite": risk or None,
                    "balance_kes": str(balance_kes),
                    "preferred_channel": "MOBILE_APP",
                }
                result = engines["eligibility"].check_eligibility(
                    prop_choice, attrs,
                )

                if result["eligible"]:
                    if result["outcome"] == "ELIGIBLE":
                        st.success(f"✅ ELIGIBLE — all gates pass")
                    else:
                        st.warning(
                            f"⚠️ {result['outcome']} — eligible with conditions"
                        )
                else:
                    st.error(
                        f"❌ {result['outcome']} — {len(result['reasons'])} "
                        "reason(s)"
                    )

                # Per-gate breakdown
                rows = []
                for gate in ELIGIBILITY_GATES:
                    g = result["gate_results"].get(gate, {})
                    passed = g.get("passed")
                    emoji = (
                        "✅" if passed is True
                        else ("⚠️" if passed is None else "❌")
                    )
                    rows.append({
                        "Gate": gate,
                        "Status": f"{emoji} {passed}",
                        "Detail": (g.get("reason")
                                      or ("; ".join(g.get("reasons", []))
                                           if g.get("reasons") else "—")),
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                                use_container_width=True)


    # ─────────────────────────────────────────────────────────────────
    # TAB 3 — NBA Preview (#353)
    # ─────────────────────────────────────────────────────────────────
    with tabs[2]:
        st.markdown("##### Next Best Proposition — per-customer ranked list")

        c1, c2, c3 = st.columns(3)
        nba_cust = c1.text_input("Customer ID", "CUST-DEMO-001", key="nba_cust")
        nba_top_n = c2.number_input("Top N", 1, 10, 5, key="nba_topn")
        nba_seg = c3.selectbox(
            "Segment",
            ["", "WOMEN", "DIASPORA", "ASSET_FINANCE", "AGRI", "YOUTH", "SME"],
            key="nba_seg",
        )
        c4, c5, c6 = st.columns(3)
        nba_age = c4.number_input("Age", 18, 120, 35, key="nba_age")
        nba_tier = c5.selectbox(
            "Spending tier",
            ["", "HIGH", "MEDIUM", "LOW"], key="nba_tier",
        )
        nba_chan = c6.selectbox(
            "Preferred channel", [""] + list(CHANNEL_PRIORITIES),
            key="nba_chan",
        )

        if nba_cust:
            attrs = {
                "customer_id": nba_cust,
                "kyc_status": "COMPLETE",
                "segment": nba_seg or None,
                "age": nba_age,
                "aml_status": "CLEARED",
                "balance_kes": "200000",
                "preferred_channel": nba_chan or None,
                "risk_appetite": "MODERATE",
                "spending_tier": nba_tier or None,
            }
            nba = engines["orchestration"].next_best_propositions(
                attrs, top_n=int(nba_top_n),
            )

            if nba.get("reason"):
                st.info(f"No NBA: {nba['reason']}")
            else:
                rows = []
                for entry in nba["propositions"]:
                    rows.append({
                        "Rank": rows and len(rows) + 1 or 1,
                        "Proposition": entry["name"],
                        "Score": entry["score"],
                        "Eligibility": entry["eligibility_outcome"],
                        "Channel": entry["preferred_channel_for_customer"],
                        "Factors": ", ".join(entry["factors"][:3]),
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                                use_container_width=True)
                st.caption(
                    "Ranking factors: " +
                    ", ".join(nba.get("ranking_factors", []))
                )


    # ─────────────────────────────────────────────────────────────────
    # TAB 4 — Pricing & Fairness (#352)
    # ─────────────────────────────────────────────────────────────────
    with tabs[3]:
        st.markdown("##### Dynamic pricing strategies + fairness audit")
        st.caption(
            f"Fairness guardrails: floor {DEFAULT_FLOOR_PCT}% / "
            f"ceiling {DEFAULT_CEILING_PCT}% of base price."
        )

        propositions = engines["catalog"].list_propositions()
        if not propositions:
            st.info("Register propositions first.")
        else:
            prop_choice = st.selectbox(
                "Proposition", [p["proposition_id"] for p in propositions],
                key="price_prop",
            )

            # Show active strategy
            active = engines["pricing"].get_active_strategy(prop_choice)
            if active:
                st.success(
                    f"Active strategy: **{active['strategy_id']}** "
                    f"({active['strategy_type']}, base "
                    f"{active['base_price_kes']} KES)"
                )
            else:
                st.warning("No active pricing strategy for this proposition.")

            # Test pricing
            with st.expander("🧪 Test price for a customer"):
                c1, c2, c3 = st.columns(3)
                cust = c1.text_input("Customer ID", "CUST-PRICE-1",
                                          key="price_cust")
                seg = c2.selectbox(
                    "Segment",
                    ["", "WOMEN", "DIASPORA", "ASSET_FINANCE",
                     "AGRI", "YOUTH", "SME"], key="price_seg",
                )
                tier = c3.selectbox(
                    "Spending tier",
                    ["", "HIGH", "MEDIUM", "LOW"], key="price_tier",
                )
                if st.button("Compute price"):
                    attrs = {"customer_id": cust, "segment": seg or None,
                                "spending_tier": tier or None}
                    result = engines["pricing"].compute_price(prop_choice, attrs)
                    if result.get("price_kes"):
                        cc1, cc2, cc3 = st.columns(3)
                        cc1.metric("Final price KES", result["price_kes"])
                        cc2.metric("Base price KES", result["base_price_kes"])
                        cc3.metric("Strategy", result["strategy_type"])
                        st.caption(f"Factors: {', '.join(result['factors'])}")
                        st.caption(f"Fairness: {result['fairness_check']}")
                    else:
                        st.warning(result.get("reason", "no_price"))

            # Fairness audit
            with st.expander("⚖️ Fairness audit"):
                c1, c2 = st.columns(2)
                audit_start = c1.text_input(
                    "Period start", "2026-01-01", key="fa_start",
                )
                audit_end = c2.text_input(
                    "Period end", "2027-12-31", key="fa_end",
                )
                if st.button("Run fairness audit"):
                    a = engines["pricing"].fairness_audit(
                        prop_choice, audit_start, audit_end,
                    )
                    if a.get("decision_count", 0) == 0:
                        st.info("No pricing decisions in window.")
                    else:
                        cc1, cc2, cc3, cc4 = st.columns(4)
                        cc1.metric("Decisions", a["decision_count"])
                        cc2.metric("Min KES", a["min_price_kes"])
                        cc3.metric("Max KES", a["max_price_kes"])
                        cc4.metric("Variance %", a["variance_ratio_pct"] or "—")
                        if a.get("variance_violation"):
                            st.error(
                                f"⚠️ Variance violation — exceeds "
                                f"{a['max_variance_threshold_pct']}% threshold."
                            )
                        else:
                            st.success("Within fairness band.")


    # ─────────────────────────────────────────────────────────────────
    # TAB 5 — Performance KPIs (#354)
    # ─────────────────────────────────────────────────────────────────
    with tabs[4]:
        st.markdown("##### Per-proposition performance KPIs")

        propositions = engines["catalog"].list_propositions()
        if not propositions:
            st.info("Register propositions first.")
        else:
            prop_choice = st.selectbox(
                "Proposition", [p["proposition_id"] for p in propositions],
                key="kpi_prop",
            )
            c1, c2 = st.columns(2)
            kpi_start = c1.text_input(
                "Period start", "2026-01-01", key="kpi_start",
            )
            kpi_end = c2.text_input(
                "Period end", "2027-12-31", key="kpi_end",
            )

            kpis = engines["analytics"].proposition_kpis(
                prop_choice, kpi_start, kpi_end,
            )
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Impressions", kpis["IMPRESSIONS"])
            c2.metric("Take-ups", kpis["TAKE_UPS"])
            c3.metric("Take-up rate %", kpis["TAKE_UP_RATE_PCT"] or "—")
            c4.metric("Revenue KES", kpis["REVENUE_KES"])
            c5, c6, c7 = st.columns(3)
            c5.metric("Avg revenue/take-up",
                         kpis["AVG_REVENUE_PER_TAKE_UP"] or "—")
            c6.metric("Attritions", kpis["ATTRITION_COUNT"])
            c7.metric(
                "NPS",
                kpis["NPS"] if kpis["NPS"] is not None else "—",
                help=f"Based on {kpis['respondent_count']} responses",
            )


    # ─────────────────────────────────────────────────────────────────
    # TAB 6 — A/B Experiments (#355)
    # ─────────────────────────────────────────────────────────────────
    with tabs[5]:
        st.markdown("##### Statistical A/B experiments")
        st.caption(
            f"Default α = {DEFAULT_ALPHA} · min sample size per arm = "
            f"{MIN_SAMPLE_SIZE_PER_VARIANT}"
        )

        experiments = engines["ab"]._load(
            engines["ab"].experiments_path, "ab_experiments",
            ("experiment_id",),
        )

        if not experiments:
            st.info("No experiments registered yet.")
        else:
            rows = []
            for e in experiments:
                sig = engines["ab"].significance_test(e["experiment_id"])
                results = engines["ab"].experiment_results(e["experiment_id"])
                rows.append({
                    "ID": e["experiment_id"],
                    "Name": e.get("experiment_name", "—"),
                    "State": e.get("state", "—"),
                    "A assigned": results["variant_a"]["assigned"],
                    "B assigned": results["variant_b"]["assigned"],
                    "A conv %": results["variant_a"]["conversion_rate_pct"] or "—",
                    "B conv %": results["variant_b"]["conversion_rate_pct"] or "—",
                    "Outcome": sig.get("outcome", "—"),
                    "p-value": sig.get("p_value", "—"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)


    # ─────────────────────────────────────────────────────────────────
    # TAB 7 — Dynamic Cohorts (#356)
    # ─────────────────────────────────────────────────────────────────
    with tabs[6]:
        st.markdown("##### Dynamic customer cohorts with auto-refresh triggers")
        st.caption(
            "Triggers: " + " · ".join(AUTO_UPDATE_TRIGGERS)
        )

        cohorts = engines["cohorts"]._load(
            engines["cohorts"].cohorts_path, "dynamic_cohorts", ("cohort_id",),
        )
        if not cohorts:
            st.info("No cohorts defined yet.")
        else:
            rows = []
            for c in cohorts:
                members = engines["cohorts"].cohort_membership(c["cohort_id"])
                rows.append({
                    "ID": c["cohort_id"],
                    "Name": c.get("cohort_name", "—"),
                    "Rule type": c.get("rule_type"),
                    "State": c.get("state"),
                    "Members": len(members),
                    "Last refresh": c.get("last_refreshed_at") or "—",
                    "Triggers": ", ".join(c.get("triggers", [])),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)


    # ─────────────────────────────────────────────────────────────────
    # TAB 8 — Channel Presentation (#357 + #358)
    # ─────────────────────────────────────────────────────────────────
    with tabs[7]:
        st.markdown("##### Channel-specific rendering preview")

        propositions = engines["catalog"].list_propositions(state="LIVE")
        if not propositions:
            st.info("No LIVE propositions to render.")
        else:
            c1, c2 = st.columns(2)
            prop_choice = c1.selectbox(
                "Proposition",
                [p["proposition_id"] for p in propositions],
                key="render_prop",
            )
            channel = c2.selectbox(
                "Channel", list(PRESENTATION_CHANNELS), key="render_chan",
            )

            c3, c4, c5 = st.columns(3)
            cname = c3.text_input("Customer name", "Jane Mwangi",
                                      key="render_name")
            cust = c4.text_input("Customer ID", "CUST-001", key="render_cust")
            seg = c5.selectbox(
                "Segment",
                ["", "WOMEN", "DIASPORA", "ASSET_FINANCE",
                 "AGRI", "YOUTH", "SME"],
                key="render_seg",
            )

            if st.button("Render"):
                attrs = {
                    "customer_id": cust, "name": cname,
                    "kyc_status": "COMPLETE", "segment": seg or None,
                    "age": 35, "aml_status": "CLEARED",
                    "balance_kes": "200000",
                    "preferred_channel": "MOBILE_APP",
                    "risk_appetite": "MODERATE",
                }
                result = engines["presentation"].render_for_channel(
                    prop_choice, channel, attrs,
                )
                if not result.get("rendered"):
                    st.error(f"Not rendered: {result.get('reason') or result.get('error')}")
                    if result.get("eligibility_reasons"):
                        st.caption(
                            "Reasons: " + ", ".join(result["eligibility_reasons"])
                        )
                else:
                    st.success("Rendered for channel " + channel)
                    st.markdown(f"**Headline:** {result['headline']}")
                    st.markdown(f"**Body:** {result['body']}")
                    st.markdown(f"**CTA:** {result['cta_text']}")
                    st.caption(f"Price: {result['price_kes']} KES")
                    # Channel-specific fields
                    key = {
                        "APP_CARD": "card", "WEB_BANNER": "banner",
                        "RM_SCRIPT": "script", "SMS": "sms", "EMAIL": "email",
                    }[channel]
                    with st.expander(f"📦 {channel} payload"):
                        st.json(result.get(key, {}))

        st.markdown("---")
        st.markdown(
            "**Cluster status (v10.277, G170 locked):** 8 engines covering "
            "10 standards. Following the v10.276 pattern, this page ships "
            "alongside engine code rather than after — closing the visibility "
            "gap before it opens."
        )

