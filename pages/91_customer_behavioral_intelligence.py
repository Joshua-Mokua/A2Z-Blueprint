"""pages/91_customer_behavioral_intelligence.py — Customer Behavioral Intelligence.

User-facing page exposing the v10.275 + v10.276 Customer Behavioral cluster
to RMs, Branch Managers, and Customer Service leads. This is the first page
that consumes the new behavioral cluster engines end-to-end:

    Engines (v10.275 — interaction event capture + journey foundations):
        - InteractionCaptureEngine          (#337)
        - MobileAppTrackingEngine           (#338)
        - BranchInteractionEngine           (#339)
        - JourneyAndWidgetEngine            (#342 + #343)
        - OnboardingOptimizationEngine      (#346)

    Engines (v10.276 — behavioral profile + ML hooks):
        - BehavioralProfileEngine           (#340)
        - AnomalyDetectionEngine            (#341)
        - DeclinePredictionEngine           (#344)
        - JourneyOptimizationEngine         (#345)
        - SegmentBehavioralInsightsEngine   (#347)
        - RmBehaviorIntelligenceEngine      (#348)

Honest scope: this page is a STARTING POINT demonstrating cluster
visibility. UI integration backfill for prior 4 closed clusters
(Bancassurance v10.274, Partnerships v10.273, Specialized Segments
v10.272, SLA Tracker v10.271) is deferred to a dedicated UI sprint —
proposed as v10.275.1 / v10.276.1 patch batches OR consolidated into
v10.285 retrospective work.

The page wires the v10.276 ml_nba_fn into journey_and_widget so RMs
see ML-augmented next-best-action when decline risk is HIGH/MEDIUM.
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

# v10.275 engines
from utils.interaction_capture import InteractionCaptureEngine
from utils.branch_interaction import BranchInteractionEngine
from utils.mobile_app_tracking import MobileAppTrackingEngine
from utils.journey_and_widget import (
    JourneyAndWidgetEngine, JOURNEY_STAGES, FRICTION_INDICATORS, NBA_RULES,
)
from utils.onboarding_optimization import OnboardingOptimizationEngine

# v10.276 engines
from utils.customer_behavioral_profile import (
    BehavioralProfileEngine, SPENDING_TIERS, RISK_APPETITE_LEVELS, LIFE_STAGES,
)
from utils.behavioral_anomaly_detection import (
    AnomalyDetectionEngine, ANOMALY_TYPES, ANOMALY_SEVERITIES,
)
from utils.decline_prediction import (
    DeclinePredictionEngine, DECLINE_RISK_LEVELS, INTERVENTION_TYPES,
    PREDICTION_HORIZON_DAYS,
)
from utils.journey_optimization import (
    JourneyOptimizationEngine, VARIANT_STATES,
)
from utils.segment_behavioral_insights import (
    SegmentBehavioralInsightsEngine, BEHAVIORAL_INSIGHT_DIMENSIONS,
)
from utils.rm_behavior_intelligence import (
    RmBehaviorIntelligenceEngine, TALKING_POINT_TYPES, TALKING_POINT_PRIORITIES,
)

require_access("shared.customer_360")

# ── State + roles ────────────────────────────────────────────────
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role", "")
name = ud.get("full_name", "")
is_admin = ud.get("is_admin", False)
is_rm = any(x in role.lower() for x in
              ("relationship", "rm", "branch manager", "general manager",
                "customer service"))


# ── Engine bootstrap (composed with ML hooks wired) ─────────────
@st.cache_resource(show_spinner=False)
def _bootstrap_engines():
    """Initialize all cluster engines + wire v10.276 Rule 7 hooks."""
    capture = InteractionCaptureEngine()
    branch = BranchInteractionEngine(capture=capture)
    app_tracking = MobileAppTrackingEngine(capture=capture)
    onboarding = OnboardingOptimizationEngine()

    profile = BehavioralProfileEngine(capture=capture)
    anomaly = AnomalyDetectionEngine(capture=capture)

    # First create journey WITHOUT hook for decline engine to compose
    journey_base = JourneyAndWidgetEngine(
        capture=capture, app_tracking=app_tracking, branch=branch,
    )
    decline = DeclinePredictionEngine(capture=capture, journey=journey_base)

    # Now wire ml_nba_fn into journey for ML-augmented NBA
    ml_nba_fn = decline.make_ml_nba_fn()
    journey = JourneyAndWidgetEngine(
        capture=capture, app_tracking=app_tracking, branch=branch,
        ml_nba_fn=ml_nba_fn,
    )

    j_optim = JourneyOptimizationEngine(capture=capture, journey=journey)
    seg_insights = SegmentBehavioralInsightsEngine(
        capture=capture, profile=profile, decline=decline, journey=journey,
    )
    rm_intel = RmBehaviorIntelligenceEngine(
        capture=capture, profile=profile, anomaly=anomaly,
        decline=decline, journey=journey,
    )

    return {
        "capture": capture,
        "branch": branch,
        "app_tracking": app_tracking,
        "onboarding": onboarding,
        "profile": profile,
        "anomaly": anomaly,
        "journey": journey,
        "decline": decline,
        "j_optim": j_optim,
        "seg_insights": seg_insights,
        "rm_intel": rm_intel,
    }


engines = _bootstrap_engines()


# ── Header ────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🧠 Customer Behavioral Intelligence</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Profile · Decline risk · Anomalies · NBA · RM talking points · Segment insights"
    "</span></div>",
    unsafe_allow_html=True,
)
st.caption(
    "Powered by v10.275 + v10.276 Customer Behavioral cluster — "
    "11 engines composed end-to-end. ML-augmented NBA wired via Rule 7 hook."
)


# ── Tabs ──────────────────────────────────────────────────────────
TABS = ["📋 Single Customer", "🔥 RM Book", "📊 Segment Insights",
        "🧪 Journey Variants", "🔌 Cluster Status"]
tabs = st.tabs(TABS)


# ─────────────────────────────────────────────────────────────────
# TAB 1 — Single Customer
# ─────────────────────────────────────────────────────────────────
with tabs[0]:
    st.markdown("##### Customer behavioral profile + decline risk + talking points")

    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    cust_id = c1.text_input("Customer ID", value="CUST-DEMO-001",
                                key="cbi_cust_id")
    age = c2.number_input("Age", min_value=18, max_value=120, value=35,
                              key="cbi_age")
    product_count = c3.number_input("Active products", min_value=0,
                                          max_value=20, value=2,
                                          key="cbi_products")
    life_event = c4.selectbox(
        "Life event",
        ["", "MARRIAGE", "NEW_CHILD", "HOUSE_PURCHASE",
         "INCOME_INCREASE", "JOB_CHANGE", "NEAR_RETIREMENT"],
        key="cbi_life",
    )

    if cust_id:
        life_events = [life_event] if life_event else []
        profile = engines["profile"].build_profile(
            cust_id, age=age, life_events=life_events,
        )
        decline = engines["decline"].predict_decline(
            cust_id, product_count=product_count,
        )
        widget = engines["journey"].behavioral_widget_payload(
            cust_id, product_count=product_count,
        )
        anomalies = engines["anomaly"].detect_anomalies(
            cust_id,
            period_start=(date.today() - timedelta(days=14)).isoformat(),
            period_end=date.today().isoformat() + "T23:59:59",
        )
        talking_points = engines["rm_intel"].generate_talking_points(
            cust_id, age=age, life_events=life_events,
            product_count=product_count,
        )

        # KPI strip
        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Stage", widget.get("stage") or "—")
        k2.metric(
            "Spending tier", profile["spending"]["tier"],
            help=(f"Monthly avg KES "
                  f"{profile['spending'].get('monthly_avg_kes', '—')}"),
        )
        k3.metric(
            "Risk appetite", profile["risk_appetite"]["level"],
        )
        k4.metric(
            "Decline risk", decline.get("risk_level", "—"),
            help=f"Score {decline.get('risk_score', '—')} / 100",
        )
        k5.metric(
            "Anomalies (14d)", anomalies.get("anomaly_count", 0),
        )

        # Talking points (urgent first)
        st.markdown("##### 🗣️ RM Talking Points")
        if not talking_points:
            st.info("No urgent signals detected. Customer is engaged "
                       "and stable. Consider routine check-in.")
        else:
            for tp in talking_points:
                priority = tp.get("priority", "LOW")
                emoji = {
                    "URGENT": "🚨", "HIGH": "⚠️",
                    "MEDIUM": "ℹ️", "LOW": "💡",
                }.get(priority, "·")
                st.markdown(
                    f"**{emoji} {priority} — {tp['type']}**  \n"
                    f"{tp['headline']}  \n"
                    f"<span style='font-size:12px;color:var(--color-text-secondary)'>"
                    f"Suggested action: {tp.get('suggested_action', '—')} · "
                    f"Signals: {', '.join(tp.get('supporting_factors', []))}"
                    f"</span>",
                    unsafe_allow_html=True,
                )

        # Next Best Action with ML attribution
        st.markdown("##### 🎯 Next Best Action")
        nba = engines["journey"].next_best_action(
            cust_id, product_count=product_count,
        )
        nba_action = nba.get("action") or "—"
        ml_driven = nba.get("ml_driven", False)
        nba_emoji = "🤖" if ml_driven else "📋"
        nba_label = "ML-augmented" if ml_driven else "Rule-based"
        st.markdown(
            f"**{nba_emoji} Action:** `{nba_action}`  \n"
            f"**Source:** {nba_label}  \n"
            f"**Reason:** {nba.get('reason', '—')}"
        )
        if ml_driven and nba.get("underlying_risk_score"):
            st.caption(
                f"ML override active: decline risk score "
                f"{nba['underlying_risk_score']} elevated this above "
                f"the rule-based stage→action mapping."
            )

        # Decline risk detail
        with st.expander("🔍 Decline risk breakdown (90-day horizon)"):
            cf = decline.get("contributing_factors", {})
            if cf:
                df = pd.DataFrame([
                    {"Factor": k, "Weight": v.get("weight"),
                     "Detail": ", ".join(f"{kk}={vv}" for kk, vv in v.items()
                                            if kk != "weight")}
                    for k, v in cf.items()
                ])
                st.dataframe(df, hide_index=True, use_container_width=True)
                st.caption(f"Composite score: {decline.get('risk_score')} / 100. "
                              f"Prediction horizon: {PREDICTION_HORIZON_DAYS} days.")
            else:
                st.info("No risk factors triggered. Customer is in healthy "
                          "engagement pattern.")

        # Profile detail
        with st.expander("👤 Full behavioral profile"):
            st.json(profile, expanded=False)

        # Recent anomalies detail
        if anomalies.get("anomaly_count", 0) > 0:
            with st.expander(f"⚡ {anomalies['anomaly_count']} anomalies in last 14 days"):
                anom_df = pd.DataFrame(anomalies["anomalies"])
                st.dataframe(anom_df, hide_index=True,
                                use_container_width=True)


# ─────────────────────────────────────────────────────────────────
# TAB 2 — RM Book
# ─────────────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown("##### RM portfolio — book-level decline risk + urgent signals")
    c1, c2 = st.columns([1, 3])
    rm_id = c1.text_input("RM ID", value="RM-101", key="cbi_rm_id")
    book_text = c2.text_area(
        "Customer IDs (comma-separated)",
        value="CUST-DEMO-001, CUST-DEMO-002, CUST-DEMO-003",
        key="cbi_book",
        help="In production, this would auto-populate from the RM's "
              "assigned customer book.",
    )
    cust_ids = [c.strip() for c in book_text.split(",") if c.strip()]

    if rm_id and cust_ids:
        summary = engines["rm_intel"].rm_book_summary(rm_id, cust_ids)

        if summary.get("reason") == "empty_book":
            st.info("Empty book.")
        else:
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Book size", summary["book_size"])
            k2.metric("HIGH risk",
                         summary["decline_risk_buckets"].get("HIGH", 0),
                         delta_color="inverse")
            k3.metric("Urgent talking points",
                         summary["urgent_talking_points"],
                         delta_color="inverse")
            k4.metric("Customers with signals",
                         summary["customers_with_signals"])

            # Risk bucket breakdown
            st.markdown("##### Decline risk distribution")
            buckets_df = pd.DataFrame([
                {"Risk level": k, "Customers": v}
                for k, v in summary["decline_risk_buckets"].items()
            ])
            st.dataframe(buckets_df, hide_index=True, use_container_width=True)

            # Per-customer summary table
            st.markdown("##### Per-customer detail")
            rows = []
            for cid in cust_ids:
                d = engines["decline"].predict_decline(cid)
                tp = engines["rm_intel"].generate_talking_points(cid)
                urgent = sum(1 for t in tp if t.get("priority") == "URGENT")
                high = sum(1 for t in tp if t.get("priority") == "HIGH")
                rows.append({
                    "Customer": cid,
                    "Risk": d.get("risk_level", "—"),
                    "Score": d.get("risk_score", "—"),
                    "URGENT pts": urgent,
                    "HIGH pts": high,
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)


# ─────────────────────────────────────────────────────────────────
# TAB 3 — Segment Insights
# ─────────────────────────────────────────────────────────────────
with tabs[2]:
    st.markdown("##### Segment-level behavioral aggregates (#347)")

    seg_input = st.text_area(
        "Segment → customer assignments (one per line, format: SEGMENT_CODE: cust1, cust2)",
        value=("WOMEN: CUST-DEMO-001, CUST-DEMO-002\n"
                  "DIASPORA: CUST-DEMO-003\n"
                  "SME: CUST-DEMO-004, CUST-DEMO-005"),
        key="cbi_seg_input",
        height=140,
    )

    seg_map = {}
    for line in seg_input.splitlines():
        if ":" not in line:
            continue
        sc, custs = line.split(":", 1)
        seg_map[sc.strip()] = [c.strip() for c in custs.split(",") if c.strip()]

    if seg_map:
        dashboard = engines["seg_insights"].insight_dashboard(seg_map)
        for sc, data in dashboard["segments"].items():
            if data.get("reason") == "empty_segment_population":
                continue
            with st.expander(f"📊 {sc} — {data['scanned_count']} customers"):
                # Show 3 of 6 dimensions for brevity
                for dim in ("SPENDING_TIER_DISTRIBUTION",
                                "DECLINE_RISK_DISTRIBUTION",
                                "NBA_DISTRIBUTION"):
                    st.markdown(f"**{dim}**")
                    counts = data.get(dim, {}).get("counts", {})
                    pct = data.get(dim, {}).get("share_pct", {})
                    df = pd.DataFrame([
                        {"Bucket": k, "Count": counts[k],
                         "Share %": pct.get(k, "—")}
                        for k in counts
                    ])
                    if not df.empty:
                        st.dataframe(df, hide_index=True,
                                        use_container_width=True)


# ─────────────────────────────────────────────────────────────────
# TAB 4 — Journey Variants (#345)
# ─────────────────────────────────────────────────────────────────
with tabs[3]:
    st.markdown("##### Journey Optimization — A/B variants + population friction")

    # Variant registry display
    variants = engines["j_optim"]._load(
        engines["j_optim"].variants_path,
        "journey_variants",
        ("variant_id",),
    )

    if not variants:
        st.info(
            "No variants registered yet. Use the form below to create one. "
            "In production, variant designs come from the Customer Experience team."
        )
    else:
        st.markdown(f"##### {len(variants)} registered variant(s)")
        rows = []
        for v in variants:
            perf = engines["j_optim"].variant_performance(v["variant_id"])
            rows.append({
                "Variant": v.get("variant_name", "—"),
                "ID": v["variant_id"],
                "State": v.get("state", "—"),
                "Assigned": perf.get("assigned", 0),
                "Completed": perf.get("completed", 0),
                "Conversion %": perf.get("conversion_pct", "—"),
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True,
                        use_container_width=True)

    # Quick-create form (for demo; production would be richer)
    if is_admin or is_rm:
        with st.expander("➕ Register new variant"):
            with st.form("new_variant_form"):
                vid = st.text_input("Variant ID")
                vname = st.text_input("Variant name")
                steps = st.text_input("Steps (comma-separated)",
                                          value="welcome, kyc, first_funding")
                split = st.slider("Traffic split %", 5, 95, 50)
                reason = st.text_input("Registration reason",
                                            value="A/B test")
                if st.form_submit_button("Register"):
                    r = engines["j_optim"].register_variant(
                        {"variant_id": vid, "variant_name": vname,
                         "journey_steps": [s.strip() for s in steps.split(",")],
                         "traffic_split_pct": split},
                        actor=uname or "user", reason=reason,
                    )
                    if r["registered"]:
                        st.success(f"Registered {vid}")
                        audit_log(uname or "user",
                                     "register_journey_variant", vid)
                        st.rerun()
                    else:
                        st.error(f"Failed: {r['error']}")


# ─────────────────────────────────────────────────────────────────
# TAB 5 — Cluster Status (transparency for the audit-conscious)
# ─────────────────────────────────────────────────────────────────
with tabs[4]:
    st.markdown("##### Customer Behavioral cluster status")
    st.caption(
        "Transparency view: which engines power this page, "
        "which catalogs are byte-for-byte locked under audit gates G168 + G169."
    )

    cluster_status = [
        ("v10.275 G168", "interaction_capture", "InteractionCaptureEngine",
         "#337 · Foundational event store · 10 channels · 10 event types · 5 outcomes"),
        ("v10.275 G168", "mobile_app_tracking", "MobileAppTrackingEngine",
         "#338 · 6 app event types · funnel + cohort retention"),
        ("v10.275 G168", "branch_interaction", "BranchInteractionEngine",
         "#339 · 10 visit purposes · 5 visit states (Rule 4 with terminals)"),
        ("v10.275 G168", "journey_and_widget", "JourneyAndWidgetEngine",
         "#342+#343 · 8 journey stages · 5 friction indicators · 6 NBA rules · "
         "v10.276 ml_nba_fn hook ACTIVE"),
        ("v10.275 G168", "onboarding_optimization", "OnboardingOptimizationEngine",
         "#346 · 7 onboarding steps (Rule 4 in order) · 30-day target · 90-day revenue"),
        ("v10.276 G169", "customer_behavioral_profile", "BehavioralProfileEngine",
         "#340 · spending tiers · risk appetite · life stages · loyalty score · "
         "make_propensity_score_fn → v10.274 insurance_recommendation"),
        ("v10.276 G169", "behavioral_anomaly_detection", "AnomalyDetectionEngine",
         "#341 · 6 anomaly types · 4 severities · 30d statistical baseline · "
         "make_fraud_score_fn → v10.274 insurance_claims"),
        ("v10.276 G169", "decline_prediction", "DeclinePredictionEngine",
         "#344 · 6 risk factors (sum=100) · 90-day horizon · 6 intervention types · "
         "make_ml_nba_fn → v10.275 journey_and_widget"),
        ("v10.276 G169", "journey_optimization", "JourneyOptimizationEngine",
         "#345 · A/B variant registry · 5 variant states (Rule 4) · friction aggregation"),
        ("v10.276 G169", "segment_behavioral_insights", "SegmentBehavioralInsightsEngine",
         "#347 · 6 insight dimensions · per-segment aggregation across 6 segments"),
        ("v10.276 G169", "rm_behavior_intelligence", "RmBehaviorIntelligenceEngine",
         "#348 · 6 talking-point types · 4 priorities · RM workspace composition"),
    ]
    df = pd.DataFrame(cluster_status,
                          columns=["Locked under", "Module", "Class", "Description"])
    st.dataframe(df, hide_index=True, use_container_width=True)

    st.caption(
        "All 11 engines are imported and instantiated at page load. "
        "Engine catalogs are locked byte-for-byte under audit gates G168 (v10.275) "
        "and G169 (v10.276). Run `python scripts/audit.py` to verify."
    )

    st.markdown("---")
    st.markdown(
        "**Honest scope note:** This page demonstrates v10.275 + v10.276 "
        "cluster integration. UI integration backfill for prior 4 closed "
        "clusters (Bancassurance v10.274 executive dashboard, Partnerships "
        "v10.273 dashboard, Specialized Segments v10.272 segment views, "
        "SLA Tracker v10.271 user view) is deferred to a dedicated UI "
        "sprint within Phase 2A — proposed as v10.275.1 / v10.276.1 patch "
        "batches OR consolidated into v10.285 retrospective."
    )
