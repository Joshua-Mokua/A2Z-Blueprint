"""pages/94_campaigns_management.py — Campaigns Management Workbench.

User-facing page exposing the v10.279 Campaigns Management cluster
end-to-end. Following v10.276/v10.277/v10.278 pattern — UI ships
alongside engines.

Engines consumed (8 modules, 10 standards):
    - CampaignsCatalogEngine             (#389 + #395)
    - CampaignsOrchestrationEngine       (#390 + #396)
    - CampaignsTriggersEngine            (#391)
    - CampaignsPersonalizationEngine     (#392)
    - CampaignsPerformanceEngine         (#393)
    - CampaignsABTestingEngine           (#394)
    - CampaignsAttributionEngine         (#397)
    - CampaignsJourneyIntegrationEngine  (#398)
"""

from __future__ import annotations

import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

import pandas as pd
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

from utils.campaigns_catalog import (
    CampaignsCatalogEngine, CAMPAIGN_STATES, CAMPAIGN_TYPES,
    CAMPAIGN_APPROVAL_LEVELS, CAMPAIGN_APPROVAL_DECISIONS,
)
from utils.campaigns_orchestration import (
    CampaignsOrchestrationEngine, CHANNEL_DISPATCHERS,
    DISPATCH_MODES, RUN_STATES, RESPONSE_TYPES,
)
from utils.campaigns_triggers import (
    CampaignsTriggersEngine, TRIGGER_EVENT_TYPES, TRIGGER_STATES,
)
from utils.campaigns_personalization import (
    CampaignsPersonalizationEngine, PERSONALIZATION_DIMENSIONS,
    VARIANT_STATES,
)
from utils.campaigns_performance import (
    CampaignsPerformanceEngine, CAMPAIGN_KPIS,
)
from utils.campaigns_ab_testing import (
    CampaignsABTestingEngine, EXPERIMENT_STATES, EXPERIMENT_OUTCOMES,
    DEFAULT_ALPHA, MIN_SAMPLE_SIZE_PER_VARIANT,
)
from utils.campaigns_attribution import (
    CampaignsAttributionEngine, ATTRIBUTION_MODELS,
)
from utils.campaigns_journey_integration import (
    CampaignsJourneyIntegrationEngine, DEFAULT_QUOTAS_PER_DAY,
    JOURNEY_EVENT_TYPES, SUPPRESSION_REASONS,
)

require_access("shared.customer_360")

# ── State ────────────────────────────────────────────────
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role", "")
is_admin = ud.get("is_admin", False)
is_marketing = any(x in role.lower() for x in ("marketing", "head", "campaign"))


@st.cache_resource(show_spinner=False)
def _bootstrap_engines():
    catalog = CampaignsCatalogEngine()
    orch = CampaignsOrchestrationEngine(catalog=catalog)
    triggers = CampaignsTriggersEngine()
    personalization = CampaignsPersonalizationEngine()
    performance = CampaignsPerformanceEngine(catalog=catalog, orchestration=orch)
    ab = CampaignsABTestingEngine()
    attribution = CampaignsAttributionEngine()
    journey = CampaignsJourneyIntegrationEngine()
    return {
        "catalog": catalog, "orch": orch, "triggers": triggers,
        "personalization": personalization, "performance": performance,
        "ab": ab, "attribution": attribution, "journey": journey,
    }


engines = _bootstrap_engines()


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📣 Campaigns Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Catalog · Orchestration · Triggers · Personalization · Performance · A/B · Attribution · Journey"
    "</span></div>",
    unsafe_allow_html=True,
)
st.caption(
    "Powered by v10.279 Campaigns cluster (8 engines, 10 standards). "
    "CBK PG/09 consumer protection via 4-level approval workflow + "
    "over-messaging quotas + suppression list."
)


TABS = ["📋 Catalog & Approval", "📤 Orchestration",
        "⚡ Triggers", "🎨 Personalization",
        "📊 Performance KPIs", "🧪 A/B Experiments",
        "🎯 ROI Attribution", "🛡️ Journey + Quotas"]
tabs = st.tabs(TABS)


# ─────────────────────────────────────────────────────────────────
# TAB 1 — Catalog & Approval (#389 + #395)
# ─────────────────────────────────────────────────────────────────
with tabs[0]:
    st.markdown("##### Campaign catalog with CBK PG/09 4-level approval")

    raw_campaigns = engines["catalog"].list_campaigns()
    # Filter to engine-shaped records only. Pre-platform data files
    # (e.g. legacy data/campaigns.json with 'id'/'type'/'status' keys
    # rather than 'campaign_id'/'campaign_type'/'state') would crash
    # the cockpit. Surface a banner so the operator knows migration
    # is pending without losing the rest of the page.
    campaigns = [c for c in raw_campaigns if "campaign_id" in c]
    legacy_count = len(raw_campaigns) - len(campaigns)
    if legacy_count > 0:
        st.warning(
            f"{legacy_count} legacy campaign record(s) ignored — "
            f"they predate the v10.279 catalog schema and need "
            f"migration to the campaign_id/state shape before "
            f"they appear here.",
        )

    if not campaigns:
        st.info(
            "No campaigns yet. Use the form below to register one. CBK "
            "PG/09 requires multi-level approval before activation: "
            "MARKETING_HEAD → COMPLIANCE_OFFICER → PRODUCT_HEAD → MD."
        )
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", len(campaigns))
        states = [c.get("state") for c in campaigns]
        c2.metric("RUNNING", states.count("RUNNING"))
        c3.metric("In approval", states.count("IN_APPROVAL"))
        c4.metric("Drafts", states.count("DRAFT"))

        rows = []
        for c in campaigns:
            rows.append({
                "ID": c["campaign_id"],
                "Name": c.get("name", "—"),
                "Type": c.get("campaign_type", "—"),
                "State": c.get("state", "—"),
                "Channels": ", ".join(c.get("channels", [])) or "—",
                "Segments": ", ".join(c.get("target_segments", [])) or "any",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                        use_container_width=True)

        st.markdown("##### Approval status drill-down")
        camp_choice = st.selectbox(
            "Inspect approval status",
            [c["campaign_id"] for c in campaigns], key="camp_inspect",
        )
        if camp_choice:
            status = engines["catalog"].approval_status(camp_choice)
            if status.get("reason") == "no_approval_records":
                st.info("No approval records yet. Submit for approval to start the chain.")
            else:
                rows = []
                for level in CAMPAIGN_APPROVAL_LEVELS:
                    info = status["per_level"].get(level, {})
                    rows.append({
                        "Level": level,
                        "Decision": info.get("decision", "PENDING"),
                        "Approver": info.get("actor") or "—",
                        "Decided at": info.get("decided_at") or "—",
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                                use_container_width=True)
                if status["all_levels_decided"]:
                    st.success("All 4 approval levels decided.")

    if is_admin or is_marketing:
        with st.expander("➕ Register new campaign (DRAFT)"):
            with st.form("new_camp"):
                cid = st.text_input("Campaign ID")
                cname = st.text_input("Name")
                ctype = st.selectbox("Type", list(CAMPAIGN_TYPES))
                csegs = st.multiselect(
                    "Target segments",
                    ["WOMEN", "DIASPORA", "ASSET_FINANCE",
                     "AGRI", "YOUTH", "SME"],
                )
                cchans = st.multiselect(
                    "Channels", list(CHANNEL_DISPATCHERS),
                    default=["EMAIL", "SMS"],
                )
                cmsg = st.text_area("Message template", height=80)
                cbudget = st.number_input("Budget KES", 0, 10**9, 100_000)
                if st.form_submit_button("Register"):
                    r = engines["catalog"].register_campaign(
                        {"campaign_id": cid, "name": cname,
                         "campaign_type": ctype,
                         "owner_role": role or "marketing",
                         "target_segments": csegs, "channels": cchans,
                         "message_template": cmsg,
                         "budget_kes": str(cbudget)},
                        actor=uname or "user",
                    )
                    if r["registered"]:
                        st.success(f"Registered {cid}")
                        audit_log(uname or "user",
                                     "register_campaign", cid)
                        st.rerun()
                    else:
                        st.error(f"Failed: {r.get('error')}")


# ─────────────────────────────────────────────────────────────────
# TAB 2 — Orchestration (#390 + #396)
# ─────────────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown("##### Multi-channel orchestration + automated execution")
    st.caption(f"Channels: {', '.join(CHANNEL_DISPATCHERS)} · "
                  f"Modes: {', '.join(DISPATCH_MODES)}")

    runs = engines["orch"].list_runs()
    if not runs:
        st.info("No campaign runs yet. Approved + RUNNING campaigns can be dispatched.")
    else:
        rows = []
        for r in runs[:30]:
            rows.append({
                "Run ID": r["run_id"][:30] + "…",
                "Campaign": r["campaign_id"],
                "Mode": r["dispatch_mode"],
                "Audience": r["audience_size"],
                "Successes": r["successes"],
                "Failures": r["failures"],
                "State": r["state"],
                "Dispatched": r.get("dispatched_at", "—")[:19],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                        use_container_width=True)


# ─────────────────────────────────────────────────────────────────
# TAB 3 — Triggers (#391)
# ─────────────────────────────────────────────────────────────────
with tabs[2]:
    st.markdown("##### Behavioral triggers — event-based campaign activation")
    st.caption(f"Event types: {', '.join(TRIGGER_EVENT_TYPES)}")

    triggers_list = engines["triggers"].list_triggers()
    if not triggers_list:
        st.info("No triggers registered yet.")
    else:
        rows = []
        for t in triggers_list:
            rows.append({
                "ID": t["trigger_id"],
                "Campaign": t["campaign_id"],
                "Event": t["event_type"],
                "State": t.get("state", "—"),
                "Predicate": str(t.get("predicate", {}))[:60],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                        use_container_width=True)


# ─────────────────────────────────────────────────────────────────
# TAB 4 — Personalization (#392)
# ─────────────────────────────────────────────────────────────────
with tabs[3]:
    st.markdown("##### AI-powered personalization variants")
    st.caption(f"Dimensions: {', '.join(PERSONALIZATION_DIMENSIONS)}")
    st.info(
        "v10.279 ships deterministic variant selection with Rule 7 "
        "ML hook factory. Production ML personalization deferred per "
        "SPEC_DEVIATION_NOTE."
    )

    campaigns = engines["catalog"].list_campaigns()
    if campaigns:
        camp_choice = st.selectbox(
            "Campaign", [c.get("campaign_id", "unknown") for c in campaigns if c.get("campaign_id")],
            key="pers_camp",
        )
        variants = engines["personalization"].list_variants(camp_choice)
        if not variants:
            st.info(f"No variants registered for {camp_choice}.")
        else:
            rows = []
            for v in variants:
                rows.append({
                    "ID": v["variant_id"],
                    "Dimension": v["dimension"],
                    "Content": v["content"][:60],
                    "Target segment": v.get("target_segment") or "any",
                    "Target tier": v.get("target_spending_tier") or "any",
                    "State": v.get("state", "—"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)


# ─────────────────────────────────────────────────────────────────
# TAB 5 — Performance KPIs (#393)
# ─────────────────────────────────────────────────────────────────
with tabs[4]:
    st.markdown("##### Real-time campaign performance KPIs")
    st.caption(f"KPIs: {', '.join(CAMPAIGN_KPIS)}")

    campaigns = engines["catalog"].list_campaigns()
    if not campaigns:
        st.info("No campaigns to evaluate.")
    else:
        camp_choice = st.selectbox(
            "Campaign", [c.get("campaign_id", "unknown") for c in campaigns if c.get("campaign_id")], key="perf_camp",
        )
        kpis = engines["performance"].campaign_kpis(camp_choice)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Reach", kpis["REACH"])
        c2.metric("Delivered rate %", kpis["DELIVERED_RATE"] or "—")
        c3.metric("Conversion rate %", kpis["CONVERSION_RATE"] or "—")
        c4.metric("ROI %", kpis["ROI_PCT"] or "—")
        c5, c6, c7 = st.columns(3)
        c5.metric("Revenue KES", kpis["REVENUE_KES"])
        c6.metric("Cost KES", kpis["COST_KES"] or "—")
        c7.metric("Conversions", kpis.get("converted_count", 0))


# ─────────────────────────────────────────────────────────────────
# TAB 6 — A/B Experiments (#394)
# ─────────────────────────────────────────────────────────────────
with tabs[5]:
    st.markdown("##### Statistical A/B experiments")
    st.caption(
        f"Default α = {DEFAULT_ALPHA} · "
        f"Min sample/variant = {MIN_SAMPLE_SIZE_PER_VARIANT}"
    )

    experiments = engines["ab"]._load(
        engines["ab"].experiments_path,
        "campaign_ab_experiments", ("experiment_id",),
    )
    if not experiments:
        st.info("No A/B experiments yet.")
    else:
        rows = []
        for e in experiments:
            sig = engines["ab"].significance_test(e["experiment_id"])
            rows.append({
                "ID": e["experiment_id"],
                "Campaign": e["campaign_id"],
                "Dimension": e.get("dimension", "—"),
                "State": e.get("state", "—"),
                "n_a": sig.get("n_a", "—"),
                "n_b": sig.get("n_b", "—"),
                "Outcome": sig.get("outcome", "—"),
                "p-value": sig.get("p_value", "—"),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                        use_container_width=True)


# ─────────────────────────────────────────────────────────────────
# TAB 7 — ROI Attribution (#397)
# ─────────────────────────────────────────────────────────────────
with tabs[6]:
    st.markdown("##### Multi-touch ROI attribution")
    st.caption(f"Models: {', '.join(ATTRIBUTION_MODELS)}")

    campaigns = engines["catalog"].list_campaigns()
    if not campaigns:
        st.info("No campaigns.")
    else:
        c1, c2 = st.columns(2)
        camp_choice = c1.selectbox(
            "Campaign", [c.get("campaign_id", "unknown") for c in campaigns if c.get("campaign_id")], key="attr_camp",
        )
        model = c2.selectbox(
            "Model", list(ATTRIBUTION_MODELS), key="attr_model",
        )
        s = engines["attribution"].campaign_attribution_summary(
            camp_choice, model=model,
        )
        c1, c2 = st.columns(2)
        c1.metric("Attributed revenue KES",
                     s.get("attributed_revenue_kes", "0"))
        c2.metric("Attributed conversions",
                     s.get("attributed_conversion_count", 0))


# ─────────────────────────────────────────────────────────────────
# TAB 8 — Journey + Quotas (#398)
# ─────────────────────────────────────────────────────────────────
with tabs[7]:
    st.markdown("##### Journey integration + over-messaging prevention")
    st.caption(
        f"Default daily quotas: {DEFAULT_QUOTAS_PER_DAY}"
    )

    st.markdown("##### Quota check")
    c1, c2 = st.columns(2)
    cust_id = c1.text_input("Customer ID", "C-DEMO-1", key="quota_cust")
    chan = c2.selectbox("Channel", list(CHANNEL_DISPATCHERS), key="quota_chan")
    if cust_id and chan:
        q = engines["journey"].check_messaging_quota(cust_id, chan)
        c1, c2, c3 = st.columns(3)
        c1.metric("Sent today", q.get("current", 0))
        c2.metric("Limit", q.get("limit", 0))
        c3.metric("Remaining", q.get("remaining", 0))
        if q.get("within_quota"):
            st.success("✅ Within quota")
        else:
            st.warning("⚠️ Quota exceeded")
        if engines["journey"].is_suppressed(cust_id):
            st.error("🛡️ Customer is SUPPRESSED — no messages will be sent")

    # Suppression list
    sups = engines["journey"]._load(
        engines["journey"].suppressions_path,
        "customer_suppressions", ("suppression_id",),
    )
    active_sups = [s for s in sups if s.get("active")]
    if active_sups:
        st.markdown(f"##### Active suppressions ({len(active_sups)})")
        rows = []
        for s in active_sups[:20]:
            rows.append({
                "Customer": s["customer_id"],
                "Reason": s["reason"],
                "Applied": s.get("applied_at", "—")[:19],
                "Notes": s.get("notes", "")[:60],
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                        use_container_width=True)

    st.markdown("---")
    st.markdown(
        "**Cluster status (v10.279, G172 locked):** 8 engines covering "
        "10 standards. CBK PG/09 consumer protection enforced via "
        "4-level approval + per-channel daily quotas + suppression list."
    )
