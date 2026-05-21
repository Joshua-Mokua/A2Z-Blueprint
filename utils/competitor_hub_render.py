"""
utils/competitor_hub_render.py — v10.348 (Option E sub-batch 4).

Single source of truth for the 2 Competitor render functions.
Extracted from pages/11_competitor (Market Overview) and pages/
93_competitor_intelligence (Workbench).

Helper functions like _load() that collided across pages have been
renamed with a domain prefix.
"""

from __future__ import annotations

from __future__ import annotations
from datetime import date
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import json
import pandas as pd
import re
import requests
import streamlit as st

from utils.competitive_alerts import CompetitiveAlertsEngine, ALERT_TYPES, ALERT_PRIORITIES, ALERT_RULE_STATES, EXECUTIVE_ROLES_ROUTING
from utils.competitive_gap_analysis import CompetitiveGapAnalysisEngine, RAG_STATUSES, FEATURE_CATEGORIES, PARITY_THRESHOLD_PCT
from utils.competitive_intel_api import CompetitiveIntelAPI, WIN_LOSS_REASONS
from utils.competitive_radar import ExecutiveCompetitiveRadarEngine, THREAT_OPPORTUNITY_DIMENSIONS
from utils.competitor_data_collection import CompetitorDataCollectionEngine, DATA_TYPES, DATA_SOURCE_TYPES, COMPETITOR_TIERS
from utils.competitor_digital_intel import CompetitorDigitalIntelEngine, POSITIONING_DIMENSIONS
from utils.competitor_rates import CompetitorRatesEngine, RATE_TYPES, TREND_DIRECTIONS, DEFAULT_TREND_EPSILON_PP, DEFAULT_ANOMALY_THRESHOLD_PP
from utils.core_audit import audit_log
from utils.db import db as a2z_db
from utils.page_access import require_access
from utils.page_shared import load_shared_state
from utils.strategic_response import StrategicResponseEngine, RESPONSE_STATES, SLA_TARGETS_HOURS, APPROVAL_DECISIONS



# ════════════════════════════════════════════════════════════════
# COMPETITOR — OVERVIEW render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/11_competitor.py — Competitor Intelligence.
Kenya banking market: rates, market share, KPIs vs peers. CBK data.
"""


def render_competitor_overview(actor: str) -> None:
    """Render the competitor overview view. Body extracted from
    the original page."""
    DATA  = Path(__file__).parent.parent / "data"
    today = date.today()
    um, ud, uname, *_ = load_shared_state()[:12]
    role = ud.get("role",""); name = ud.get("full_name","")

    st.markdown(
        "<div style='padding:16px 0 4px'>"
        "<span style='font-size:22px;font-weight:800'>🔍 Competitor Intelligence</span>"
        "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
        "Kenya banking market · Peer rates · Market share · KPI benchmarking</span></div>",
        unsafe_allow_html=True)

    @st.cache_data(ttl=300, show_spinner=False)
    def _overview_load():
        p = DATA / "competitor_data.json"
        return a2z_db.load_json(p) if p.exists() else {}

    data = _overview_load()
    if not data:
        st.info("Competitor data not available."); st.stop()

    banks = data.get("banks",{}); rates_dep = data.get("deposit_rates",{})
    rates_lend = data.get("lending_rates",{}); mkt_share = data.get("market_share",{})
    OUR_BANK = "Ecobank"

    tabs = st.tabs(["📊 Market Overview","💱 Rate Comparison","🏆 KPI Benchmarking","📈 Market Share","🤖 AI Market Brief"])

    # ── TAB 1: Market Overview ─────────────────────────────────────────
    with tabs[0]:
        st.markdown(f"**Kenya banking sector — {data.get('as_at',str(today))}**")
        st.markdown(f"CBK Rate: **{data.get('cbk_rate',13)}%**")

        bank_rows = [{"Bank":bdata.get("full_name", "")[:28],"Tier":bdata.get("tier", ""),
                       "Assets (B)":bdata.get("assets_kes_b", 0),"Loans (B)":bdata.get("loans_kes_b", 0),
                       "Deposits (B)":bdata.get("deposits_kes_b", 0),"NPL%":bdata.get("npl_pct", 0),
                       "CAR%":bdata["car_pct"],"NIM%":bdata.get("nim_pct", 0),"ROE%":bdata.get("roe_pct", 0),
                       "Branches":bdata["branches"]}
                      for bank, bdata in sorted(banks.items(), key=lambda x:-x[1]["assets_kes_b"])]
        df_banks = pd.DataFrame(bank_rows)

        # Highlight our bank
        def _highlight_ours(row):
            is_ours = OUR_BANK.lower() in row["Bank"].lower()
            return ["background-color: #E8F5EE; font-weight:bold" if is_ours else "" for _ in row]

        st.dataframe(df_banks.style.apply(_highlight_ours, axis=1), use_container_width=True, hide_index=True)

        our = banks.get(OUR_BANK,{})
        if our:
            st.markdown("---")
            st.markdown("**Our position vs Tier 1 average:**")
            t1_banks = [v for v in banks.values() if v["tier"]==1]
            t1_avg = lambda key: sum(b.get(key,0) for b in t1_banks)/max(len(t1_banks),1)
            comps = [("NPL%",our.get("npl_pct",0),t1_avg("npl_pct"),True),
                     ("NIM%",our.get("nim_pct",0),t1_avg("nim_pct"),False),
                     ("ROE%",our.get("roe_pct",0),t1_avg("roe_pct"),False),
                     ("CAR%",our.get("car_pct",0),t1_avg("car_pct"),False)]
            _oc = st.columns(4)
            for col,(metric,ours_v,t1_v,lower_better) in zip(_oc,comps):
                is_better = (ours_v < t1_v) if lower_better else (ours_v > t1_v)
                col.metric(f"Our {metric}", f"{ours_v}%", f"Peer avg: {t1_v:.1f}%",
                           delta_color="normal" if is_better else "inverse")

    # ── TAB 2: Rate Comparison ─────────────────────────────────────────
    with tabs[1]:
        r1,r2 = st.tabs(["📥 Deposit Rates","📤 Lending Rates"])
        with r1:
            st.markdown("**Deposit rates comparison (% p.a.):**")
            for tenor, rate_map in rates_dep.items():
                _dep_rows = [{"Bank":b,"Rate%":r,"vs Ours":f"{r-rate_map.get(OUR_BANK,0):+.2f}pp"}
                              for b,r in sorted(rate_map.items(), key=lambda x:-x[1])]
                our_rate = rate_map.get(OUR_BANK,0)
                better = sum(1 for b,r in rate_map.items() if b!=OUR_BANK and r<our_rate)
                icon = "🟢" if better >= len(rate_map)//2 else "🔴"
                st.markdown(f"**{tenor}:** {icon} We offer {our_rate}% — better than {better}/{len(rate_map)-1} peers")

            df_dep = pd.DataFrame({tenor: rate_map for tenor,rate_map in rates_dep.items()}).T
            st.dataframe(df_dep, use_container_width=True)

        with r2:
            st.markdown("**Lending rates comparison (% p.a.):**")
            df_lend = pd.DataFrame({prod: rate_map for prod,rate_map in rates_lend.items()}).T
            st.dataframe(df_lend, use_container_width=True)
            for prod, rate_map in rates_lend.items():
                our_r = rate_map.get(OUR_BANK,0)
                cheaper_than_us = [b for b,r in rate_map.items() if b!=OUR_BANK and r<our_r]
                if cheaper_than_us:
                    st.warning(f"⚠️ **{prod}**: {cheaper_than_us} offer lower rates — review pricing")

    # ── TAB 3: KPI Benchmarking ─────────────────────────────────────────
    with tabs[2]:
        st.markdown("**KPI benchmarking vs peer group:**")
        our = banks.get(OUR_BANK,{})
        if our:
            kpi_rows = []
            for metric, label, lower_better in [
                ("npl_pct","NPL Ratio (%)",True), ("car_pct","Capital Adequacy (%)",False),
                ("nim_pct","Net Interest Margin (%)",False), ("roe_pct","Return on Equity (%)",False),
            ]:
                vals = {b:v.get(metric,0) for b,v in banks.items()}
                our_v = vals.get(OUR_BANK,0)
                rank  = sorted(vals.values(), reverse=not lower_better).index(our_v)+1
                best  = min(vals.values()) if lower_better else max(vals.values())
                worst = max(vals.values()) if lower_better else min(vals.values())
                status= "🟢 Top" if rank<=3 else "🟡 Mid" if rank<=6 else "🔴 Bottom"
                kpi_rows.append({"KPI":label,"Ecobank":our_v,"Industry Best":best,
                                   "Industry Worst":worst,"Rank":f"#{rank} of {len(vals)}","Status":status})
            st.dataframe(pd.DataFrame(kpi_rows), use_container_width=True, hide_index=True)

    # ── TAB 4: Market Share ─────────────────────────────────────────────
    with tabs[3]:
        st.markdown("**Market share analysis:**")
        for mtype, label in [("total_assets_pct","Total Assets"),
                              ("total_deposits_pct","Total Deposits"),
                              ("digital_customers_pct","Digital Customers")]:
            share = mkt_share.get(mtype,{})
            our_s = share.get(OUR_BANK,0)
            st.markdown(f"**{label}:** Ecobank {our_s:.1f}% market share")

        share_data = mkt_share.get("total_assets_pct",{})
        df_share   = pd.DataFrame({"Bank":list(share_data.keys()),
                                     "Share%":list(share_data.values())}).sort_values("Share%",ascending=False)
        st.bar_chart(df_share.set_index("Bank")["Share%"])

    # ── TAB 5: AI Market Brief ──────────────────────────────────────────
    with tabs[4]:
        st.markdown("**AI-generated competitive intelligence brief:**")
        st.caption("Claude analyses our position vs peers and generates a strategic brief.")
        our = banks.get(OUR_BANK,{})
        if st.button("🤖 Generate competitive brief", key="ci_ai", type="primary"):
            audit_log("COMPETITOR_BRIEF_GENERATED", uname, "AI competitive brief")
            with st.spinner("Analysing competitive landscape…"):
                try:
                    _context = (f"Ecobank Kenya: Assets KES {our.get('assets_kes_b',0)}B, "
                                f"NPL {our.get('npl_pct',0)}%, NIM {our.get('nim_pct',0)}%, "
                                f"ROE {our.get('roe_pct',0)}%, {our.get('branches',0)} branches. "
                                f"Market share assets: {mkt_share.get('total_assets_pct',{}).get(OUR_BANK,0):.1f}%. "
                                f"KCB leads with 23.1%, Equity 20.4%. "
                                f"Our 12M FD rate {rates_dep.get('12M Fixed',{}).get(OUR_BANK,0)}% — "
                                f"highest among peers.")
                    resp = requests.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"Content-Type":"application/json"},
                        json={"model":"claude-sonnet-4-20250514","max_tokens":600,
                              "system":"You are a banking strategy analyst covering Kenya. Write a concise, actionable competitive intelligence brief.",
                              "messages":[{"role":"user","content":
                                  f"Write a 4-bullet competitive intelligence brief for Ecobank Kenya management: {_context}. "
                                  "Focus on: 1) Key vulnerability, 2) Key opportunity, 3) Rate positioning, 4) Digital gap."}]},
                        timeout=30)
                    resp.raise_for_status()
                    st.markdown(resp.json()["content"][0]["text"])
                except Exception as e:
                    st.error(f"Brief unavailable: {str(e)[:80]}")


# ════════════════════════════════════════════════════════════════
# COMPETITOR — WORKBENCH render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/93_competitor_intelligence.py — Competitor Intelligence Workbench.

User-facing page exposing the v10.278 Competitor Intelligence cluster
end-to-end. Following the v10.276/v10.277 pattern: every cluster batch
ships a UI page alongside its engines.

Engines consumed (8 modules, 10 standards):
    - CompetitorDataCollectionEngine     (#327)
    - CompetitorRatesEngine              (#328)
    - CompetitorDigitalIntelEngine       (#329 + #333)
    - CompetitiveGapAnalysisEngine       (#332)
    - CompetitiveAlertsEngine            (#331)
    - StrategicResponseEngine            (#334)
    - ExecutiveCompetitiveRadarEngine    (#330)
    - CompetitiveIntelAPI                (#335 + #336, with v10.272 hook)

v10.272 hook wiring is honored: tab 8 shows the make_competitor_data_fn
factory wired into v10.272 SegmentDashboardEngine and the resulting
basis="competitor_intel_v10.278".
"""


def render_competitor_workbench(actor: str) -> None:
    """Render the competitor workbench view. Body extracted from
    the original page."""

    # ── State + roles ────────────────────────────────────────────────
    um, ud, uname, *_ = load_shared_state()[:12]
    role = ud.get("role", "")
    name = ud.get("full_name", "")
    is_admin = ud.get("is_admin", False)
    is_strategy = any(x in role.lower() for x in
                           ("strategy", "head", "general manager", "ceo",
                            "cfo", "coo", "cmo"))


    # ── Engine bootstrap ──────────────────────────────────────────────
    @st.cache_resource(show_spinner=False)
    def _workbench_bootstrap_engines():
        dc = CompetitorDataCollectionEngine()
        rates = CompetitorRatesEngine(data_collection=dc)
        digital = CompetitorDigitalIntelEngine(data_collection=dc)
        gaps = CompetitiveGapAnalysisEngine(data_collection=dc)
        alerts = CompetitiveAlertsEngine(data_collection=dc, rates_engine=rates)
        radar = ExecutiveCompetitiveRadarEngine(
            data_collection=dc, rates=rates, digital=digital,
            alerts=alerts, gaps=gaps,
        )
        response = StrategicResponseEngine()
        api = CompetitiveIntelAPI(
            data_collection=dc, rates=rates, digital=digital,
            alerts=alerts, gaps=gaps, radar=radar,
        )
        return {
            "dc": dc, "rates": rates, "digital": digital, "gaps": gaps,
            "alerts": alerts, "radar": radar, "response": response, "api": api,
        }


    engines = _workbench_bootstrap_engines()


    # ── Header ────────────────────────────────────────────────────────
    st.markdown(
        "<div style='padding:16px 0 4px'>"
        "<span style='font-size:22px;font-weight:800'>🎯 Competitor Intelligence</span>"
        "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
        "Data · Rates · Digital · Gaps · Alerts · Strategic Response · Radar · SBU View"
        "</span></div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "Powered by v10.278 Competitor Intelligence cluster (8 engines, 10 "
        "standards). v10.272 SegmentDashboard hook now wired (basis="
        "\"competitor_intel_v10.278\")."
    )


    # ── Tabs ──────────────────────────────────────────────────────────
    TABS = ["📊 Competitors & Data Points", "💰 Rate Comparison",
            "📱 Digital Intel & Positioning", "🚦 Feature Gaps RAG",
            "🚨 Alerts", "🔁 Strategic Response",
            "🎯 Executive Radar", "🏢 SBU View + v10.272 Hook"]
    tabs = st.tabs(TABS)


    # ─────────────────────────────────────────────────────────────────
    # TAB 1 — Competitors & Data Points (#327)
    # ─────────────────────────────────────────────────────────────────
    with tabs[0]:
        st.markdown("##### Tracked competitors with data ingestion store")

        competitors = engines["dc"].list_competitors()
        if not competitors:
            st.info(
                "No competitors registered yet. Use the Quick Register form "
                "below to add tier-1, tier-2, or tier-3 competitors. "
                "v10.278 ships the structured store; production-grade NLP "
                "scraping is deferred per SPEC_DEVIATION_NOTE."
            )
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Tracked competitors", len(competitors))
            tier_counts = {}
            for c in competitors:
                tier_counts[c.get("tier", "?")] = tier_counts.get(c.get("tier", "?"), 0) + 1
            c2.metric("TIER_1", tier_counts.get("TIER_1", 0))
            c3.metric("TIER_2 + TIER_3",
                         tier_counts.get("TIER_2", 0) + tier_counts.get("TIER_3", 0))

            rows = []
            for c in competitors:
                data_points = engines["dc"].list_data_points(
                    competitor_id=c["competitor_id"],
                )
                rows.append({
                    "ID": c["competitor_id"],
                    "Name": c.get("name", "—"),
                    "Tier": c.get("tier", "—"),
                    "Website": c.get("website", "—"),
                    "Data points": len(data_points),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)

            # Recent data points
            with st.expander("📌 Recent data points (last 50)"):
                all_dps = engines["dc"].list_data_points()
                all_dps.sort(key=lambda r: r.get("recorded_at", ""), reverse=True)
                dp_rows = []
                for dp in all_dps[:50]:
                    dp_rows.append({
                        "Competitor": dp["competitor_id"],
                        "Type": dp["data_type"],
                        "Value": dp.get("value", "—"),
                        "Source": dp["data_source"],
                        "As of": dp.get("as_of", "—"),
                    })
                if dp_rows:
                    st.dataframe(pd.DataFrame(dp_rows), hide_index=True,
                                    use_container_width=True)
                else:
                    st.info("No data points yet.")

        if is_admin or is_strategy:
            with st.expander("➕ Register competitor"):
                with st.form("new_comp"):
                    cid = st.text_input("Competitor ID")
                    cname = st.text_input("Name")
                    ctier = st.selectbox("Tier", list(COMPETITOR_TIERS))
                    cwebsite = st.text_input("Website (optional)")
                    if st.form_submit_button("Register"):
                        r = engines["dc"].register_competitor(
                            {"competitor_id": cid, "name": cname,
                             "tier": ctier, "website": cwebsite},
                            actor=uname or "user",
                        )
                        if r["registered"]:
                            st.success(f"Registered {cid}")
                            audit_log(uname or "user",
                                         "register_competitor", cid)
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error')}")


    # ─────────────────────────────────────────────────────────────────
    # TAB 2 — Rate Comparison (#328)
    # ─────────────────────────────────────────────────────────────────
    with tabs[1]:
        st.markdown("##### Daily competitor rate tracking + trend + anomaly")
        st.caption(
            f"Trend epsilon: {DEFAULT_TREND_EPSILON_PP}pp · "
            f"Anomaly threshold: {DEFAULT_ANOMALY_THRESHOLD_PP}pp"
        )

        rate_type = st.selectbox("Rate type", list(RATE_TYPES), key="rate_type")
        as_of = st.date_input(
            "As of date",
            value=date.today(), key="rate_asof",
        )
        table = engines["rates"].rate_comparison_table(
            rate_type, as_of_date=as_of.isoformat(),
        )
        if "error" in table:
            st.error(table["error"])
        elif not table.get("rows"):
            st.info("No competitor rate data yet.")
        else:
            rows = []
            for r in table["rows"]:
                rows.append({
                    "Competitor": r["competitor_name"] or r["competitor_id"],
                    "Tier": r.get("tier", "—"),
                    "Rate": r["value"] or "—",
                    "Unit": r.get("unit", "—"),
                    "As of": r.get("as_of", "—"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)

        with st.expander("📈 Anomaly detection"):
            threshold = st.number_input(
                "Threshold (pp)", min_value=0.1, max_value=10.0,
                value=float(DEFAULT_ANOMALY_THRESHOLD_PP), step=0.1,
                key="anom_thresh",
            )
            days = st.number_input("Window days", 7, 365, 30, key="anom_days")
            if st.button("Detect anomalies"):
                a = engines["rates"].detect_anomalies(
                    rate_type,
                    threshold_pp=Decimal(str(threshold)), days=int(days),
                )
                st.metric("Anomalies", a["anomaly_count"])
                if a["anomalies"]:
                    st.dataframe(
                        pd.DataFrame(a["anomalies"]),
                        hide_index=True, use_container_width=True,
                    )


    # ─────────────────────────────────────────────────────────────────
    # TAB 3 — Digital Intel & Positioning Map (#329 + #333)
    # ─────────────────────────────────────────────────────────────────
    with tabs[2]:
        st.markdown("##### Digital strategy timeline + dimensional positioning")

        competitors = engines["dc"].list_competitors()
        if not competitors:
            st.info("No competitors registered yet.")
        else:
            c1, c2 = st.columns(2)
            comp_choice = c1.selectbox(
                "Competitor",
                [c["competitor_id"] for c in competitors],
                format_func=lambda x: next(
                    (c["name"] for c in competitors if c["competitor_id"] == x), x),
            )
            days = c2.number_input("Window days", 30, 720, 180, key="dig_days")

            timeline = engines["digital"].digital_event_timeline(
                comp_choice, days=int(days),
            )
            c1, c2, c3 = st.columns(3)
            c1.metric("Total events", timeline["event_count"])
            c2.metric("Launches", timeline["by_type"].get("DIGITAL_LAUNCH", 0))
            c3.metric("Features",
                         timeline["by_type"].get("PRODUCT_FEATURE", 0))

            velocity = engines["digital"].digital_velocity_score(
                comp_choice, period_days=int(days),
            )
            if velocity.get("events_per_month") is not None:
                st.metric("Velocity (events/month)", velocity["events_per_month"])

            st.markdown("##### Dimensional positioning map")
            positioning = engines["digital"].positioning_map()
            if positioning["competitor_count"] == 0:
                st.info("No positioning data yet.")
            else:
                rows = []
                for r in positioning["rows"]:
                    row = {
                        "Competitor": r["competitor_name"] or r["competitor_id"],
                        "Tier": r.get("tier", "—"),
                    }
                    for dim in POSITIONING_DIMENSIONS:
                        val = r.get(dim)
                        row[dim] = val if val is not None else "—"
                    rows.append(row)
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                                use_container_width=True)


    # ─────────────────────────────────────────────────────────────────
    # TAB 4 — Feature Gaps RAG (#332)
    # ─────────────────────────────────────────────────────────────────
    with tabs[3]:
        st.markdown("##### Feature-by-feature gap analysis with RAG status")
        st.caption(
            f"Parity threshold: {PARITY_THRESHOLD_PCT}% — features above this "
            "competitor presence drive RED status when we lack them, "
            "AMBER when we have parity but no leadership."
        )

        cat = st.selectbox(
            "Category filter",
            [""] + list(FEATURE_CATEGORIES),
            key="gap_cat",
        )
        table = engines["gaps"].feature_gap_table(
            feature_category=cat or None,
        )
        if "error" in table:
            st.error(table["error"])
        elif table.get("reason"):
            st.info(f"No data: {table['reason']}")
        else:
            summary = engines["gaps"].rag_status_summary()
            c1, c2, c3 = st.columns(3)
            c1.metric("🔴 RED", summary.get("RED", 0))
            c2.metric("🟡 AMBER", summary.get("AMBER", 0))
            c3.metric("🟢 GREEN", summary.get("GREEN", 0))

            rows = []
            for r in table["rows"]:
                emoji = {"RED": "🔴", "AMBER": "🟡", "GREEN": "🟢"}[r["rag_status"]]
                rows.append({
                    "Feature": r["name"],
                    "Category": r["category"],
                    "Internal": "✅" if r["internal_present"] else "❌",
                    "Competitors": (
                        f"{r['competitor_presence_count']}/{r['competitor_total']} "
                        f"({r['competitor_presence_pct']}%)"
                    ),
                    "RAG": f"{emoji} {r['rag_status']}",
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)


    # ─────────────────────────────────────────────────────────────────
    # TAB 5 — Alerts (#331)
    # ─────────────────────────────────────────────────────────────────
    with tabs[4]:
        st.markdown("##### Real-time competitive alerts with executive routing")

        rules = engines["alerts"]._load(
            engines["alerts"].rules_path,
            "competitive_alert_rules", ("rule_id",),
        )
        if rules:
            st.caption(f"{len(rules)} alert rule(s) registered")
            rows = []
            for r in rules:
                rows.append({
                    "ID": r["rule_id"],
                    "Type": r["alert_type"],
                    "Priority": r["priority"],
                    "Tier filter": r.get("competitor_filter_tier") or "any",
                    "State": r.get("state", "—"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)
        else:
            st.info("No alert rules registered yet.")

        st.markdown("##### Recent published alerts (last 30 days)")
        role_filter = st.selectbox(
            "Filter by executive role",
            [""] + sorted(set(
                r for prio in EXECUTIVE_ROLES_ROUTING.values() for r in prio
            )),
            key="alerts_role",
        )
        published = engines["alerts"].list_published_alerts(
            executive_role=role_filter or None, days=30,
        )
        if published:
            rows = []
            for a in published:
                rows.append({
                    "Priority": a.get("priority"),
                    "Type": a.get("alert_type"),
                    "Headline": a.get("headline", "—"),
                    "Recipients": ", ".join(a.get("recipients", [])),
                    "Published": a.get("published_at", "—"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)
        else:
            st.info("No published alerts in window.")


    # ─────────────────────────────────────────────────────────────────
    # TAB 6 — Strategic Response (#334)
    # ─────────────────────────────────────────────────────────────────
    with tabs[5]:
        st.markdown("##### Strategic response workflow: detect → measure")
        st.caption(
            f"States: {len(RESPONSE_STATES)} · "
            f"SLA stages defined: {len(SLA_TARGETS_HOURS)}"
        )

        # SLA reference table
        with st.expander("📋 SLA reference"):
            sla_rows = []
            for k, v in SLA_TARGETS_HOURS.items():
                sla_rows.append({
                    "Stage": k.replace("__", " → "),
                    "Target hours": v,
                })
            st.dataframe(pd.DataFrame(sla_rows), hide_index=True,
                            use_container_width=True)

        responses = engines["response"].list_responses()
        if not responses:
            st.info(
                "No strategic responses initiated yet. Responses are "
                "initiated from alerts in Tab 5."
            )
        else:
            rows = []
            for r in responses:
                status = engines["response"].response_status(r["response_id"])
                rows.append({
                    "ID": r["response_id"][:30] + "…",
                    "State": r.get("state", "—"),
                    "Owner": r.get("owner", "—"),
                    "Alert": r.get("alert_id", "—"),
                    "Competitor": r.get("related_competitor_id") or "—",
                    "SLA breaches": status.get("sla_breach_count", 0),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)


    # ─────────────────────────────────────────────────────────────────
    # TAB 7 — Executive Radar (#330)
    # ─────────────────────────────────────────────────────────────────
    with tabs[6]:
        st.markdown("##### Executive radar: market share + NPS + heatmap")

        period = st.text_input("Period", "2026-Q1", key="radar_period")

        # Market share
        ms = engines["radar"].market_share_snapshot(period)
        if ms.get("reason") == "no_market_share_data":
            st.info("No market share data registered yet.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Tracked %", ms.get("tracked_pct", "0"))
            c2.metric("Untracked %", ms.get("untracked_pct", "—"))
            c3.metric("Competitors with data",
                         ms.get("competitor_count_with_data", 0))

            st.markdown("##### Top competitors by market share")
            rows = []
            for r in ms.get("top_competitors", []):
                rows.append({
                    "Competitor": r["name"] or r["competitor_id"],
                    "Tier": r.get("tier", "—"),
                    "Share %": r["share_pct"],
                    "As of": r.get("as_of", "—"),
                })
            if rows:
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                                use_container_width=True)

        # Threat / opportunity heatmap
        st.markdown("##### Threats + opportunities (last 30 days)")
        h = engines["radar"].threats_opportunities_heatmap(
            period_start=(date.today() - timedelta(days=30)).isoformat(),
            period_end=date.today().isoformat() + "Z",
        )
        c1, c2 = st.columns(2)
        c1.metric("⚠️ Threats", h["threat_count"])
        c2.metric("🌟 Opportunities", h["opportunity_count"])

        if h["threats"]:
            st.markdown("**Threats**")
            rows = []
            for t in h["threats"][:15]:
                rows.append({
                    "Severity": t.get("severity", "—"),
                    "Dimension": t["dimension"],
                    "Competitor": t.get("competitor_name") or "—",
                    "Headline": t.get("headline", "—"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)

        if h["opportunities"]:
            st.markdown("**Opportunities**")
            rows = []
            for o in h["opportunities"][:15]:
                rows.append({
                    "Severity": o.get("severity", "—"),
                    "Dimension": o["dimension"],
                    "Competitor": o.get("competitor_name") or "—",
                    "Headline": o.get("headline", "—"),
                })
            st.dataframe(pd.DataFrame(rows), hide_index=True,
                            use_container_width=True)


    # ─────────────────────────────────────────────────────────────────
    # TAB 8 — SBU View + v10.272 Hook Status (#335 + #336)
    # ─────────────────────────────────────────────────────────────────
    with tabs[7]:
        st.markdown("##### SBU competitive view + v10.272 hook status")
        st.caption(
            "v10.278 honors the v10.272 deferred wiring: "
            "make_competitor_data_fn() returns a Callable matching "
            "segment_dashboards.competitor_data_fn signature."
        )

        # SBU view
        from utils.specialized_segments_tagging import SEGMENT_CODES
        sbu_choice = st.selectbox(
            "SBU segment",
            list(SEGMENT_CODES),
            key="sbu_choice",
        )
        period = st.text_input("Period", "2026-Q1", key="sbu_period")

        sv = engines["api"].sbu_competitive_view(sbu_choice, period)
        if "error" in sv:
            st.error(sv["error"])
        else:
            c1, c2, c3 = st.columns(3)
            ms = sv.get("market_share", {})
            c1.metric(
                "Market share data",
                len(ms.get("market_share_by_segment", []))
                if isinstance(ms.get("market_share_by_segment"), list) else 0,
            )
            c2.metric("Pricing pressure alerts",
                         sv.get("pricing_pressure_count", 0))
            gap_summary = sv.get("feature_gap_summary", {})
            c3.metric("RED feature gaps", gap_summary.get("RED", 0)
                           if isinstance(gap_summary, dict) else 0)

            # v10.272 hook status
            st.markdown("---")
            st.markdown("##### v10.272 segment_dashboards hook status")
            try:
                from utils.segment_dashboards import SegmentDashboardEngine
                engine_with_hook = SegmentDashboardEngine(
                    competitor_data_fn=engines["api"].make_competitor_data_fn(),
                )
                dash = engine_with_hook.build_segment_dashboard(sbu_choice, period)
                benchmark = dash.get("competitor_benchmark", {})
                basis = benchmark.get("basis", "—")
                data_source = benchmark.get("data_source", "—")
                if basis == "competitor_intel_v10.278":
                    st.success(
                        f"✅ v10.272 hook WIRED — basis={basis}, "
                        f"data_source={data_source}"
                    )
                else:
                    st.warning(
                        f"⚠️ v10.272 hook present but unexpected basis: {basis}"
                    )
                with st.expander("🔍 Wired benchmark payload"):
                    st.json(benchmark)
            except ImportError:
                st.error("v10.272 segment_dashboards module not found")

            # Win/loss
            st.markdown("---")
            st.markdown("##### Win/loss records")
            wl = engines["api"].list_win_loss_records(
                sbu_segment_code=sbu_choice, days=90,
            )
            if not wl:
                st.info(f"No win/loss records for {sbu_choice} in last 90 days.")
            else:
                rows = []
                for w in wl[:30]:
                    rows.append({
                        "Outcome": w["outcome"],
                        "Reason": w["reason"],
                        "Competitor": w.get("competitor_id") or "—",
                        "Deal value KES": w.get("deal_value_kes") or "—",
                        "Recorded": w.get("recorded_at", "—"),
                    })
                st.dataframe(pd.DataFrame(rows), hide_index=True,
                                use_container_width=True)

        st.markdown("---")
        st.markdown(
            "**Cluster status (v10.278, G171 locked):** 8 engines covering "
            "10 standards. v10.272 deferred wiring honored. Following the "
            "v10.276/v10.277 pattern, this page ships alongside engine code."
        )

