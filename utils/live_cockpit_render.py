"""
utils/live_cockpit_render.py — v10.345 (Option E, sub-batch 1).

Single source of truth for the 4 Live Cockpit render functions.
Extracted from pages/109_cims_live, 110_treasury_live, 111_credit_live,
112_compliance_live. The original 4 pages now import their render
function from here; the consolidated page (115_live_cockpits) imports
all 4 and routes via domain selector.

Cache helpers are namespaced with a domain prefix to avoid Streamlit
cache key collisions between domains.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import streamlit as st

from utils.cash_forecast_wiring import make_primed_forecaster
from utils.cockpit_read import audit_log_records
from utils.cockpit_read import cims_instruction_trace, cims_open_work, load_records, filter_records, sort_records, latest_n
from utils.cockpit_read import compliance_cra_training
from utils.cockpit_read import compliance_open_work, compliance_cases, compliance_aml_alerts, compliance_sanctions_screening, compliance_regulatory_returns, count_by, latest_n
from utils.cockpit_read import count_by
from utils.cockpit_read import credit_open_work, credit_loan_applications, credit_ifrs9_loans, credit_watchlist, load_records, count_by, latest_n
from utils.cockpit_read import credit_portfolio_analytics
from utils.cockpit_read import treasury_cash_forecast
from utils.cockpit_read import treasury_daily_report
from utils.cockpit_read import treasury_open_work, load_records, count_by, treasury_liquidity_metrics, treasury_irrbb, treasury_capital_adequacy
from utils.core_audit import audit_log
from utils.treasury_dashboard_wiring import make_wired_dashboard


# ════════════════════════════════════════════════════════════════
# CIMS — render + cache helpers
# ════════════════════════════════════════════════════════════════

@st.cache_data(ttl=10)
def _cims_cached_open_work():
    return cims_open_work(data_dir="data", limit=50)


@st.cache_data(ttl=10)
def _cims_cached_trace(session_id: str):
    return cims_instruction_trace(session_id, data_dir="data")


@st.cache_data(ttl=10)
def _cims_cached_recent_sessions(n: int = 50):
    sessions = load_records(
        "data/cims_capture_sessions.json",
        "cims_capture_sessions", ("session_id",),
    )
    return latest_n(sessions, n=n)


@st.cache_data(ttl=10)
def _cims_cached_recent_exceptions(n: int = 50):
    exceptions = load_records(
        "data/cims_exceptions.json",
        "cims_exceptions", ("exception_id",),
    )
    return latest_n(exceptions, n=n)


@st.cache_data(ttl=10)
def _cims_cached_recent_history(n: int = 100):
    history = load_records(
        "data/cims_audit_history.json",
        "cims_audit_history", ("record_id",),
    )
    return latest_n(history, n=n)


@st.cache_data(ttl=10)
def _cims_cached_pending_manual_stp():
    stp_requests = load_records(
        "data/cims_stp_requests.json",
        "cims_stp_requests", ("request_id",),
    )
    return filter_records(stp_requests, state="MANUAL_REVIEW")


@st.cache_data(ttl=10)
def _cims_cached_pending_merges():
    merges = load_records(
        "data/cims_identity_merges.json",
        "cims_identity_merges", ("merge_id",),
    )
    return filter_records(
        merges,
        custom_predicate=lambda r: r.get("state") not in (
            "APPROVED", "REJECTED", "REVERSED",
        ),
    )


@st.cache_data(ttl=10)
def _cims_cached_low_confidence_nlp():
    nlp = load_records(
        "data/cims_classification_requests.json",
        "cims_classification_requests", ("request_id",),
    )
    return filter_records(
        nlp,
        custom_predicate=lambda r: (
            r.get("confidence_tier") in ("LOW", "MEDIUM")
            and r.get("state") not in ("OVERRIDDEN", "COMPLETED")
        ),
    )


def render_cims_cockpit(actor: str) -> None:
    """Render the CIMS live cockpit. Body extracted from
    pages/<original>_cims_live.py main()."""
    st.title("🎛️ CIMS Live Cockpit")
    st.caption(
        "v10.295 · Read-side composition of all 15 CIMS engines · "
        "Auto-refreshes every 10s · Real audit-trail integration"
    )

    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    # Manual refresh button to bust the 10s cache
    cols = st.columns([4, 1])
    cols[0].caption(
        f"Loaded at: {datetime.utcnow().isoformat(timespec='seconds')} UTC"
    )
    if cols[1].button("🔄 Refresh now"):
        st.cache_data.clear()
        audit_log(
            action="cockpit_cache_clear",
            username=actor,
            module="cims_live",
        )
        st.rerun()

    tabs = st.tabs([
        "📊 Open work pulse",
        "🔍 Instruction trace",
        "📥 Recent capture",
        "⏰ SLA risk board",
        "🚨 Exception board",
        "👀 Pending reviews",
        "📜 Audit trail",
    ])

    # ---------- Tab 1: Open work pulse ----------
    with tabs[0]:
        st.subheader("Bank-wide CIMS work landscape")
        st.caption(
            "Live counts across all 15 CIMS engines. "
            "Cached 10s for performance — use Refresh now to force."
        )
        snapshot = _cims_cached_open_work()

        # Headline metrics — 7 across so the operator sees the
        # whole landscape on one screen
        cols = st.columns(7)
        cols[0].metric(
            "Open sessions",
            snapshot["open_capture_sessions"],
        )
        cols[1].metric(
            "Pending NLP",
            snapshot["pending_nlp"],
        )
        cols[2].metric(
            "STP manual",
            snapshot["pending_stp_manual"],
        )
        cols[3].metric(
            "Open exceptions",
            snapshot["open_exceptions"],
        )
        cols[4].metric(
            "SLA upcoming",
            snapshot["upcoming_sla"],
        )
        cols[5].metric(
            "SLA breached",
            snapshot["breached_sla"],
            delta=(
                "needs attention" if snapshot["breached_sla"] > 0
                else None
            ),
            delta_color="inverse",
        )
        cols[6].metric(
            "Pending merges",
            snapshot["pending_merges"],
        )

        # Triage hint
        if snapshot["breached_sla"] > 0:
            st.error(
                f"🛑 {snapshot['breached_sla']} SLA obligations "
                f"are breached or past deadline. See the SLA "
                f"risk board for the full list."
            )
        if snapshot["open_exceptions"] > 20:
            st.warning(
                f"⚠ {snapshot['open_exceptions']} open exceptions "
                f"— above advisory threshold. See exception board."
            )

        st.markdown("---")
        st.markdown("**Recent open sessions (top 10):**")
        for r in snapshot["recent_open_sessions"][:10]:
            st.write(
                f"• `{r.get('session_id', '?')}` "
                f"[{r.get('state', '?')}] "
                f"channel={r.get('originating_channel', r.get('channel', '?'))} "
                f"opened={r.get('registered_at', '?')[:19]}"
            )

    # ---------- Tab 2: Instruction trace ----------
    with tabs[1]:
        st.subheader("Full lifecycle trace for one session")
        st.caption(
            "Joins capture (#166) → classification (#167) → "
            "STP (#168) → exceptions (#175) → SLA (#171) → "
            "audit history (#176) for a single linked_session_id."
        )

        sid = st.text_input(
            "Linked session ID",
            placeholder="e.g. CAP-001",
            key="trace_sid",
        )
        if sid:
            trace = _cims_cached_trace(sid)
            audit_log(
                action="instruction_trace_view",
                username=actor,
                module="cims_live",
            )

            # Capture
            if trace["capture"]:
                cap = trace["capture"]
                st.markdown("**📥 Capture (#166):**")
                st.write(
                    f"• state: `{cap.get('state', '?')}` · "
                    f"channel: {cap.get('originating_channel', cap.get('channel', '?'))} · "
                    f"opened: {cap.get('registered_at', '?')[:19]}"
                )
                if cap.get("instruction_type"):
                    st.caption(
                        f"  instruction_type: "
                        f"{cap['instruction_type']}"
                    )
            else:
                st.warning(
                    f"No capture session found for `{sid}`"
                )

            # Classification
            cr = trace["classification_requests"]
            if cr:
                st.markdown(f"**🧠 NLP classification (#167) — "
                                  f"{len(cr)} request(s):**")
                for r in cr[:5]:
                    st.write(
                        f"• `{r.get('request_id', '?')}` "
                        f"intent={r.get('intent_category', '?')} "
                        f"tier={r.get('confidence_tier', '?')} "
                        f"state={r.get('state', '?')}"
                    )

            # STP
            stp = trace["stp_requests"]
            if stp:
                st.markdown(f"**⚡ STP decisions (#168) — "
                                  f"{len(stp)} request(s):**")
                for r in stp[:5]:
                    st.write(
                        f"• `{r.get('request_id', '?')}` "
                        f"decision_state={r.get('state', '?')} "
                        f"risk_tier={r.get('risk_tier', '?')}"
                    )

            # Exceptions
            exc = trace["exceptions"]
            if exc:
                st.markdown(f"**🚨 Exceptions (#175) — "
                                  f"{len(exc)} record(s):**")
                for r in exc[:5]:
                    st.write(
                        f"• `{r.get('exception_id', '?')}` "
                        f"severity={r.get('severity', '?')} "
                        f"state={r.get('state', '?')} "
                        f"category={r.get('category', '?')}"
                    )

            # SLA
            sla = trace["sla_obligations"]
            if sla:
                st.markdown(f"**⏰ SLA obligations (#171) — "
                                  f"{len(sla)} record(s):**")
                for r in sla[:5]:
                    st.write(
                        f"• `{r.get('obligation_id', '?')}` "
                        f"deadline={r.get('deadline_at', '?')[:19]} "
                        f"state={r.get('state', '?')}"
                    )

            # History (full timeline)
            hist = trace["history"]
            if hist:
                st.markdown(f"**📜 Audit history (#176) — "
                                  f"{len(hist)} record(s):**")
                for r in hist[:20]:
                    st.write(
                        f"• {r.get('registered_at', '?')[:19]} "
                        f"`{r.get('kind', '?')}` "
                        f"{r.get('narrative', '')[:100]}"
                    )
                if len(hist) > 20:
                    st.caption(
                        f"  ... and {len(hist) - 20} more"
                    )

    # ---------- Tab 3: Recent capture ----------
    with tabs[2]:
        st.subheader("Most recent capture sessions")
        st.caption(
            "Top 50 most recently registered sessions across "
            "all channels."
        )
        sessions = _cims_cached_recent_sessions(n=50)
        st.metric("Sessions shown", len(sessions))
        if not sessions:
            st.info(
                "No capture sessions yet. Sessions appear here "
                "once `register_capture_session()` is called."
            )
        else:
            # Channel breakdown
            from utils.cockpit_read import count_by
            by_chan = count_by(sessions, "originating_channel")
            by_state = count_by(sessions, "state")
            cols = st.columns(2)
            cols[0].write("**By channel:**")
            for k, v in sorted(by_chan.items(),
                                  key=lambda x: -x[1]):
                cols[0].write(f"  {k}: {v}")
            cols[1].write("**By state:**")
            for k, v in sorted(by_state.items(),
                                  key=lambda x: -x[1]):
                cols[1].write(f"  {k}: {v}")

            st.markdown("---")
            st.markdown("**Recent rows:**")
            for r in sessions[:25]:
                st.write(
                    f"• `{r.get('session_id', '?')}` "
                    f"[{r.get('state', '?')}] "
                    f"channel={r.get('originating_channel', r.get('channel', '?'))} "
                    f"opened={r.get('registered_at', '?')[:19]}"
                )

    # ---------- Tab 4: SLA risk board ----------
    with tabs[3]:
        st.subheader("SLA risk board")
        st.caption(
            "Obligations with upcoming or breached deadlines. "
            "Reg E, Reg Z, CBK Banking Act, DPA Kenya 2019."
        )
        snapshot = _cims_cached_open_work()

        cols = st.columns(2)
        cols[0].metric("Upcoming (within window)",
                          snapshot["upcoming_sla"])
        cols[1].metric("Breached / past deadline",
                          snapshot["breached_sla"],
                          delta_color="inverse")

        if snapshot["recent_breached_sla"]:
            st.error("**Breached obligations (top 50):**")
            for r in snapshot["recent_breached_sla"]:
                st.write(
                    f"• `{r.get('obligation_id', '?')}` "
                    f"deadline={r.get('deadline_at', '?')[:19]} "
                    f"state={r.get('state', '?')} "
                    f"session={r.get('linked_session_id', '?')}"
                )
        else:
            st.success("No breached SLA obligations.")

    # ---------- Tab 5: Exception board ----------
    with tabs[4]:
        st.subheader("Open exceptions")
        exceptions = _cims_cached_recent_exceptions(n=200)
        open_exc = filter_records(
            exceptions,
            custom_predicate=lambda r: r.get("state") not in (
                "RESOLVED", "CANCELLED",
            ),
        )

        from utils.cockpit_read import count_by
        by_sev = count_by(open_exc, "severity")
        by_cat = count_by(open_exc, "category")

        cols = st.columns(4)
        cols[0].metric("Total open", len(open_exc))
        cols[1].metric("Critical",
                          by_sev.get("CRITICAL", 0),
                          delta_color="inverse")
        cols[2].metric("High",
                          by_sev.get("HIGH", 0))
        cols[3].metric("Medium",
                          by_sev.get("MEDIUM", 0))

        if by_cat:
            st.write("**By category:**")
            for k, v in sorted(by_cat.items(),
                                  key=lambda x: -x[1]):
                st.write(f"  {k}: {v}")

        st.markdown("---")
        st.markdown("**Most recent open exceptions (top 25):**")
        for r in open_exc[:25]:
            st.write(
                f"• `{r.get('exception_id', '?')}` "
                f"[{r.get('severity', '?')}/{r.get('state', '?')}] "
                f"{r.get('category', '?')} · "
                f"{r.get('narrative', '')[:80]}"
            )

    # ---------- Tab 6: Pending reviews ----------
    with tabs[5]:
        st.subheader("Pending human reviews across CIMS")

        st.markdown("**STP — Manual review queue (#168):**")
        stp_manual = _cims_cached_pending_manual_stp()
        st.metric("Awaiting STP manual review", len(stp_manual))
        for r in stp_manual[:10]:
            st.write(
                f"• `{r.get('request_id', '?')}` "
                f"risk_tier={r.get('risk_tier', '?')} "
                f"session={r.get('linked_session_id', '?')}"
            )

        st.markdown("---")
        st.markdown("**Identity — Pending merges (#173):**")
        merges = _cims_cached_pending_merges()
        st.metric("Pending merges", len(merges))
        for r in merges[:10]:
            st.write(
                f"• `{r.get('merge_id', '?')}` "
                f"state={r.get('state', '?')} "
                f"source={r.get('source_identity_id', '?')} "
                f"target={r.get('target_identity_id', '?')}"
            )

        st.markdown("---")
        st.markdown("**NLP — Low-confidence classifications (#167):**")
        low_conf = _cims_cached_low_confidence_nlp()
        st.metric("Low/medium confidence pending", len(low_conf))
        for r in low_conf[:10]:
            st.write(
                f"• `{r.get('request_id', '?')}` "
                f"tier={r.get('confidence_tier', '?')} "
                f"intent={r.get('intent_category', '?')}"
            )

    # ---------- Tab 7: Audit trail explorer ----------
    with tabs[6]:
        st.subheader("Recent audit history records (#176)")
        st.caption(
            "Append-only history — corrections supersede but never "
            "replace originals."
        )

        kind_filter = st.selectbox(
            "Filter by kind",
            ["(all)", "INSTRUCTION_LIFECYCLE",
              "CLASSIFICATION_OUTCOME", "STP_DECISION",
              "IDENTITY_LINK_EVENT", "EXCEPTION_LIFECYCLE",
              "SLA_OBLIGATION_EVENT", "NBA_RECOMMENDATION",
              "DROPOUT_INTERVENTION"],
            key="hist_kind",
        )
        records = _cims_cached_recent_history(n=200)
        if kind_filter != "(all)":
            records = [r for r in records
                         if r.get("kind") == kind_filter]

        st.metric("History records shown", len(records))
        if not records:
            st.info("No audit history records match the filter.")
        else:
            for r in records[:50]:
                st.write(
                    f"• {r.get('registered_at', '?')[:19]} "
                    f"`{r.get('kind', '?')}` "
                    f"session={r.get('linked_session_id', '?')} "
                    f"— {r.get('narrative', '')[:100]}"
                )


# ════════════════════════════════════════════════════════════════
# TREASURY — render + cache helpers
# ════════════════════════════════════════════════════════════════

@st.cache_data(ttl=10)
def _treasury_cached_open_work():
    return treasury_open_work(data_dir="data")


@st.cache_data(ttl=10)
def _treasury_cached_liquidity_metrics():
    return treasury_liquidity_metrics(data_dir="data")


@st.cache_data(ttl=10)
def _treasury_cached_irrbb():
    return treasury_irrbb(data_dir="data")


@st.cache_data(ttl=10)
def _treasury_cached_fx_records():
    return load_records(
        "data/treasury_fx.json",
        "treasury_fx", ("id",),
    )


@st.cache_data(ttl=10)
def _treasury_cached_capital_metrics():
    return treasury_capital_adequacy(data_dir="data")


@st.cache_data(ttl=60)  # Dashboard report is heavier — cache 60s
def _treasury_cached_dashboard_report(as_of_date: str):
    """Generate a daily treasury report via a wired
    TreasuryDashboardEngine. v10.302 closes the v10.296
    placeholder — all 5 upstream engines now inject via
    `make_wired_dashboard()`."""
    # Import surfaces the wiring dependency so static checks
    # (G193 + test_page_110_uses_wired_factory) can see it.
    from utils.treasury_dashboard_wiring import (  # noqa: F401
        make_wired_dashboard,
    )
    from utils.cockpit_read import treasury_daily_report
    return treasury_daily_report(as_of_date=as_of_date)


@st.cache_data(ttl=60)  # Forecast computation — cache 60s
def _treasury_cached_cash_forecast(horizon_days: int = 91):
    """13-week cash forecast via a primed
    TreasuryCashForecastingEngine. v10.304 closes the v10.296
    placeholder — engine is primed from any production
    cash_history.json + cash_scheduled_flows.json present.
    Empty production data renders cleanly as status=no_data."""
    from utils.cash_forecast_wiring import (  # noqa: F401
        make_primed_forecaster,
    )
    from utils.cockpit_read import treasury_cash_forecast
    return treasury_cash_forecast(horizon_days=horizon_days)


def render_treasury_cockpit(actor: str) -> None:
    """Render the TREASURY live cockpit. Body extracted from
    pages/<original>_treasury_live.py main()."""
    st.title("🏦 Treasury Live Cockpit")
    st.caption(
        "v10.296 · Read-side composition of Treasury arc engines "
        "(ALM, Products, RWA, FTP, Cash Forecasting, IRRBB) · "
        "Auto-refreshes every 10s"
    )

    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    cols = st.columns([4, 1])
    cols[0].caption(
        f"Loaded at: "
        f"{datetime.utcnow().isoformat(timespec='seconds')} UTC"
    )
    if cols[1].button("🔄 Refresh now"):
        st.cache_data.clear()
        audit_log(
            action="cockpit_cache_clear",
            username=actor,
            module="treasury_live",
        )
        st.rerun()

    tabs = st.tabs([
        "📊 Open work pulse",
        "💧 LCR & NSFR",
        "📈 IRRBB scenarios",
        "💱 FX positions",
        "🏛️ RWA & capital",
        "💰 Cash forecast",
        "📋 Dashboard report",
    ])

    # ---------- Tab 1: Open work pulse ----------
    with tabs[0]:
        st.subheader("Bank-wide Treasury work landscape")
        st.caption(
            "Live counts from liquidity_metrics.json, irrbb.json, "
            "treasury_fx.json. Cached 10s — use Refresh to force."
        )

        snap = _treasury_cached_open_work()

        cols = st.columns(5)
        cols[0].metric(
            "FX positions",
            snap["fx_positions_count"],
        )
        cols[1].metric(
            "Open FX deals",
            snap["open_fx_deals"],
        )
        cols[2].metric(
            "IRRBB breaches",
            snap["irrbb_breaches"],
            delta=(
                "needs attention" if snap["irrbb_breaches"] > 0
                else None
            ),
            delta_color="inverse",
        )

        lcr_display = (
            f"{snap['lcr_pct']:.1f}%" if snap["lcr_pct"] is not None
            else "—"
        )
        cols[3].metric(
            "LCR",
            lcr_display,
            delta=(
                f"min {snap['lcr_min_pct']:.0f}%"
                if snap["lcr_min_pct"] is not None else None
            ),
            delta_color=(
                "inverse" if snap["lcr_breached"] else "normal"
            ),
        )
        cols[4].metric(
            "As at (read)",
            snap["as_at"][11:19] if snap.get("as_at") else "—",
        )

        # Triage banners
        if snap["lcr_breached"]:
            st.error(
                f"🛑 LCR is {snap['lcr_pct']:.1f}%, below the "
                f"{snap['lcr_min_pct']:.0f}% CBK minimum. "
                f"Escalate to Treasury head + Risk."
            )
        if snap["irrbb_breaches"] > 0:
            st.warning(
                f"⚠ {snap['irrbb_breaches']} IRRBB scenarios "
                f"breach CBK limits. See IRRBB tab."
            )

    # ---------- Tab 2: LCR & NSFR ----------
    with tabs[1]:
        st.subheader("Liquidity Coverage & Net Stable Funding")
        liq = _treasury_cached_liquidity_metrics()
        if liq is None:
            st.info(
                "No data in data/liquidity_metrics.json. "
                "Treasury team loads this daily."
            )
        else:
            cols = st.columns(3)
            cols[0].metric(
                "LCR",
                f"{liq.get('lcr', 0):.1f}%",
            )
            cols[1].metric(
                "CBK minimum",
                f"{liq.get('lcr_minimum_pct', 0):.0f}%",
            )
            cols[2].metric(
                "Internal target",
                f"{liq.get('lcr_internal_target_pct', 0):.0f}%",
            )

            st.caption(
                f"As at: {liq.get('as_at', '—')} · "
                f"Currency: {liq.get('currency', '—')}"
            )

            comps = liq.get("lcr_components")
            if isinstance(comps, dict):
                st.markdown("**LCR components:**")
                for k, v in comps.items():
                    st.write(f"  {k}: {v}")

    # ---------- Tab 3: IRRBB scenarios ----------
    with tabs[2]:
        st.subheader(
            "Interest Rate Risk in the Banking Book — Scenarios"
        )
        irrbb = _treasury_cached_irrbb()
        if irrbb is None:
            st.info(
                "No data in data/irrbb.json. ALM team runs this "
                "monthly per CBK Prudential Guidelines."
            )
        else:
            ear_limit = irrbb.get("cbk_limit_ear_pct")
            eve_limit = irrbb.get("cbk_limit_eve_pct")
            cols = st.columns(3)
            cols[0].metric(
                "CBK EAR limit",
                f"{ear_limit}%" if ear_limit else "—",
            )
            cols[1].metric(
                "CBK EVE limit",
                f"{eve_limit}%" if eve_limit else "—",
            )
            cols[2].metric(
                "As at",
                irrbb.get("as_at", "—"),
            )

            scenarios = irrbb.get("scenarios", [])
            if scenarios:
                st.markdown("**Scenarios:**")
                for s in scenarios:
                    if not isinstance(s, dict):
                        continue
                    ear = s.get("ear_pct", 0)
                    eve = s.get("eve_pct", 0)
                    ear_b = (ear_limit is not None
                              and abs(float(ear)) > float(ear_limit))
                    eve_b = (eve_limit is not None
                              and abs(float(eve)) > float(eve_limit))
                    flag = ""
                    if ear_b or eve_b:
                        flag = " 🛑"
                    st.write(
                        f"• `{s.get('scenario', '?')}` "
                        f"EAR={ear}% EVE={eve}%{flag}"
                    )

    # ---------- Tab 4: FX positions ----------
    with tabs[3]:
        st.subheader("FX position book")
        records = _treasury_cached_fx_records()
        st.metric("Total FX records", len(records))
        if not records:
            st.info(
                "No data in data/treasury_fx.json."
            )
        else:
            # By currency
            by_currency = count_by(records, "currency")
            by_deal_type = count_by(records, "deal_type")
            by_status = count_by(records, "status")

            cols = st.columns(3)
            cols[0].write("**By currency:**")
            for k, v in sorted(by_currency.items(),
                                  key=lambda x: -x[1]):
                cols[0].write(f"  {k or '(unset)'}: {v}")
            cols[1].write("**By deal type:**")
            for k, v in sorted(by_deal_type.items(),
                                  key=lambda x: -x[1]):
                cols[1].write(f"  {k or '(unset)'}: {v}")
            cols[2].write("**By status:**")
            for k, v in sorted(by_status.items(),
                                  key=lambda x: -x[1]):
                cols[2].write(f"  {k or '(unset)'}: {v}")

            st.markdown("---")
            st.markdown("**Recent records (top 20):**")
            for r in records[:20]:
                st.write(
                    f"• `{r.get('id', '?')}` "
                    f"{r.get('deal_type', '?')} "
                    f"{r.get('direction', '')} "
                    f"{r.get('currency', '?')} "
                    f"{r.get('fcy_amount', 0):,} → "
                    f"KES {r.get('kes_amount', 0):,}"
                )

    # ---------- Tab 5: RWA & capital ----------
    with tabs[4]:
        st.subheader("Risk-Weighted Assets & Capital Adequacy")
        cap = _treasury_cached_capital_metrics()
        if cap is None:
            st.info(
                "No data in data/capital_adequacy.json."
            )
        else:
            cols = st.columns(3)
            cols[0].metric(
                "CET1 ratio",
                f"{cap.get('cet1_ratio_pct', 0):.2f}%",
            )
            cols[1].metric(
                "Tier 1 ratio",
                f"{cap.get('tier1_ratio_pct', 0):.2f}%",
            )
            cols[2].metric(
                "Total capital ratio",
                f"{cap.get('total_capital_ratio_pct', 0):.2f}%",
            )
            st.caption(
                f"As at: {cap.get('as_at', '—')}"
            )

    # ---------- Tab 6: Cash forecast ----------
    with tabs[5]:
        st.subheader("13-week cash forecast")
        st.caption(
            "Composed via TreasuryCashForecastingEngine "
            "(ENH-237) primed by `make_primed_forecaster()`. "
            "Provide data/cash_history.json + "
            "data/cash_scheduled_flows.json to enable real "
            "projections."
        )

        from utils.cockpit_read import treasury_cash_forecast
        fc = _treasury_cached_cash_forecast()

        # Header row
        kcols = st.columns(4)
        kcols[0].metric("Horizon (days)", fc["horizon_days"])
        kcols[1].metric(
            "History days used", fc["n_history_days_used"],
        )
        kcols[2].metric("Forecast points", fc["n_points"])
        kcols[3].metric("Status", fc["status"])

        if fc["status"] == "no_data":
            st.info(fc["notes"])
        elif fc["status"] == "error":
            st.error(f"Forecast error: {fc['notes']}")
        else:
            if fc["notes"]:
                st.caption(fc["notes"])

            # Render first 20 points compactly
            st.markdown("**First 20 daily points:**")
            for p in fc["points"][:20]:
                st.write(
                    f"• {p['forecast_date']} · "
                    f"total={p['total_kes']} · "
                    f"baseline={p['baseline_kes']} · "
                    f"80% band [{p['band_low_80']}, "
                    f"{p['band_high_80']}]"
                )
            if fc["n_points"] > 20:
                st.caption(
                    f"…and {fc['n_points'] - 20} more points. "
                    f"Fetch /api/cockpit/treasury/cash-forecast "
                    f"for the full series."
                )

    # ---------- Tab 7: Dashboard report ----------
    with tabs[6]:
        st.subheader("Daily Treasury Dashboard Report")
        st.caption(
            "Composed via TreasuryDashboardEngine (wired in "
            "v10.302 with all 5 upstream engines: ALM, "
            "Products, RWA, FTP, Forecast). Refresh cached 60s."
        )

        today = datetime.utcnow().date().isoformat()
        report = _treasury_cached_dashboard_report(today)

        audit_log(
            action="treasury_dashboard_report_view",
            username=actor,
            module="treasury_live",
        )

        # Header row
        kcols = st.columns(3)
        kcols[0].metric("Report ID", report["report_id"])
        kcols[1].metric("As of", report["as_of_date"])
        kcols[2].metric("Sections", report["n_sections"])

        # Engine wiring status row
        st.markdown("**Engine wiring status:**")
        summary = report["board_summary"]
        wcols = st.columns(5)
        wire_flags = [
            ("alm_wired", "ALM", wcols[0]),
            ("products_wired", "Products", wcols[1]),
            ("rwa_wired", "RWA", wcols[2]),
            ("ftp_wired", "FTP", wcols[3]),
            ("forecast_wired", "Forecast", wcols[4]),
        ]
        for flag, label, col in wire_flags:
            icon = "✅" if summary.get(flag) else "⚪"
            col.write(f"{icon} {label}")

        # Section rendering
        st.markdown("---")
        st.markdown("**Sections:**")
        if not report["sections"]:
            st.info(
                "Wired dashboard returned zero sections. This "
                "is unexpected — check upstream engine "
                "instantiation in utils.treasury_dashboard_"
                "wiring."
            )
        for s in report["sections"]:
            status = s.get("status", "?")
            status_icon = {
                "ok": "✅", "OK": "✅",
                "warning": "⚠", "WARNING": "⚠",
                "breach": "🛑", "BREACH": "🛑",
                "no_data": "⚪", "NO_DATA": "⚪",
            }.get(status, "•")
            st.markdown(
                f"**{status_icon} {s['section_title']}** · "
                f"`{s['section_id']}` · status: {status}"
            )
            st.caption(s.get("notes") or "")
            if s.get("metrics"):
                metric_pairs = [
                    f"{k}={v}" for k, v in s["metrics"].items()
                ]
                st.write("  " + " · ".join(metric_pairs))


# ════════════════════════════════════════════════════════════════
# CREDIT — render + cache helpers
# ════════════════════════════════════════════════════════════════

@st.cache_data(ttl=10)
def _credit_cached_open_work():
    return credit_open_work(data_dir="data")


@st.cache_data(ttl=10)
def _credit_cached_loan_apps():
    return credit_loan_applications(data_dir="data")


@st.cache_data(ttl=10)
def _credit_cached_ifrs9():
    return credit_ifrs9_loans(data_dir="data")


@st.cache_data(ttl=10)
def _credit_cached_watchlist():
    return credit_watchlist(data_dir="data")


@st.cache_data(ttl=10)
def _credit_cached_credit_admin():
    return load_records(
        "data/credit_admin.json",
        "credit_admin", ("id",),
    )


@st.cache_data(ttl=60)  # Portfolio analytics is heavier — cache 60s
def _credit_cached_portfolio_analytics():
    """v10.309 Cat A composer — wraps credit_portfolio_analytics
    composing AI underwriting + PD distribution + IRB capital."""
    from utils.cockpit_read import credit_portfolio_analytics
    return credit_portfolio_analytics(data_dir="data")


def render_credit_cockpit(actor: str) -> None:
    """Render the CREDIT live cockpit. Body extracted from
    pages/<original>_credit_live.py main()."""
    st.title("💳 Credit Live Cockpit")
    st.caption(
        "v10.300 · Read-side composition of Credit module "
        "engines (#119-#130 + CRD-R1..R7 + KESONIA) · "
        "Auto-refreshes every 10s · CBK Prudential reporting "
        "context"
    )

    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    cols = st.columns([4, 1])
    cols[0].caption(
        f"Loaded at: "
        f"{datetime.utcnow().isoformat(timespec='seconds')} UTC"
    )
    if cols[1].button("🔄 Refresh now"):
        st.cache_data.clear()
        audit_log(
            action="cockpit_cache_clear",
            username=actor,
            module="credit_live",
        )
        st.rerun()

    tabs = st.tabs([
        "📊 Open work pulse",
        "📥 Loan pipeline",
        "📈 IFRS9 stages",
        "🚨 NPL & watchlist",
        "✅ Credit admin",
        "📋 Portfolio analytics",
        "📜 Audit trail",
    ])

    # ---------- Tab 1: Open work pulse ----------
    with tabs[0]:
        st.subheader("Bank-wide Credit landscape")
        st.caption(
            "Live counts across loan applications, IFRS9 loans, "
            "and the credit monitoring watchlist."
        )

        snap = _credit_cached_open_work()

        cols = st.columns(5)
        cols[0].metric(
            "Applications total",
            snap["applications_total"],
        )
        cols[1].metric(
            "Applications open",
            snap["applications_open"],
        )
        cols[2].metric(
            "IFRS9 records",
            snap["ifrs9_total"],
        )

        npl_display = (
            f"{snap['npl_pct']:.2f}%"
            if snap["npl_pct"] is not None
            else "—"
        )
        cols[3].metric(
            "NPL ratio",
            npl_display,
            delta=(
                "above 5%" if (snap["npl_pct"] or 0) > 5 else None
            ),
            delta_color="inverse",
        )
        cols[4].metric(
            "Watchlist",
            snap["watchlist_count"],
        )

        # IFRS9 stage breakdown row
        st.markdown("---")
        st.markdown("**IFRS9 stage distribution:**")
        scols = st.columns(3)
        scols[0].metric(
            "Stage 1 (performing)",
            snap["ifrs9_stage1"],
        )
        scols[1].metric(
            "Stage 2 (sig. credit increase)",
            snap["ifrs9_stage2"],
            delta_color="inverse",
        )
        scols[2].metric(
            "Stage 3 (NPL)",
            snap["ifrs9_stage3"],
            delta_color="inverse",
        )

        # Triage banners
        if snap["npl_pct"] is not None and snap["npl_pct"] > 5.0:
            st.error(
                f"🛑 NPL ratio is {snap['npl_pct']:.2f}%, above "
                f"the 5% advisory threshold. Escalate to Credit "
                f"Risk + Recovery."
            )
        if snap["ifrs9_stage2"] > 0:
            st.warning(
                f"⚠ {snap['ifrs9_stage2']} loans in Stage 2 "
                f"(significant credit increase). Watch for "
                f"Stage 3 migration."
            )

    # ---------- Tab 2: Loan pipeline ----------
    with tabs[1]:
        st.subheader("Loan application pipeline")
        apps = _credit_cached_loan_apps()
        st.metric("Total applications", len(apps))

        if not apps:
            st.info(
                "No applications in data/loan_applications.json."
            )
        else:
            snap = _credit_cached_open_work()
            st.markdown("**By swim lane:**")
            for lane, n in sorted(
                snap["applications_by_stage"].items(),
                key=lambda x: -x[1],
            ):
                st.write(f"  {lane}: {n}")

            st.markdown("---")
            by_product = count_by(apps, "product")
            by_currency = count_by(apps, "currency")
            pcols = st.columns(2)
            pcols[0].write("**By product:**")
            for k, v in sorted(by_product.items(),
                                  key=lambda x: -x[1])[:10]:
                pcols[0].write(f"  {k or '(unset)'}: {v}")
            pcols[1].write("**By currency:**")
            for k, v in sorted(by_currency.items(),
                                  key=lambda x: -x[1]):
                pcols[1].write(f"  {k or '(unset)'}: {v}")

            st.markdown("---")
            st.markdown("**Recent applications (top 20):**")
            recent = latest_n(apps, n=20,
                                 by_field="application_date")
            for r in recent:
                st.write(
                    f"• `{r.get('id', '?')}` "
                    f"{r.get('client_name', '?')} · "
                    f"{r.get('product', '?')} · "
                    f"{r.get('currency', 'KES')} "
                    f"{r.get('amount', 0):,} · "
                    f"lane={r.get('swim_lane', '?')}"
                )

    # ---------- Tab 3: IFRS9 stages ----------
    with tabs[2]:
        st.subheader("IFRS9 loan staging")
        st.caption(
            "Per IFRS9 / CBK Prudential Guidelines: Stage 1 = "
            "12-month ECL, Stage 2 = lifetime ECL (significant "
            "credit increase), Stage 3 = lifetime ECL (NPL / "
            "credit-impaired)."
        )
        loans = _credit_cached_ifrs9()
        st.metric("Total IFRS9 records", len(loans))

        if not loans:
            st.info("No data in data/ifrs9_loans.json.")
        else:
            snap = _credit_cached_open_work()
            scols = st.columns(3)
            scols[0].metric("Stage 1", snap["ifrs9_stage1"])
            scols[1].metric("Stage 2", snap["ifrs9_stage2"])
            scols[2].metric("Stage 3 (NPL)",
                              snap["ifrs9_stage3"])

            # Aggregate outstanding by stage
            stage_outstanding = {1: 0.0, 2: 0.0, 3: 0.0}
            for r in loans:
                if not isinstance(r, dict):
                    continue
                try:
                    s = int(r.get("stage", 0))
                except (ValueError, TypeError):
                    continue
                if s in stage_outstanding:
                    try:
                        stage_outstanding[s] += float(
                            r.get("outstanding", 0))
                    except (ValueError, TypeError):
                        pass

            st.markdown("---")
            st.markdown("**Outstanding by stage:**")
            for stage, total in stage_outstanding.items():
                st.write(f"  Stage {stage}: {total:,.0f}")

    # ---------- Tab 4: NPL & watchlist ----------
    with tabs[3]:
        st.subheader("Non-Performing Loans & Watchlist")
        loans = _credit_cached_ifrs9()
        npl_records = [
            r for r in loans
            if isinstance(r, dict)
            and r.get("stage") == 3
        ]
        st.metric("Stage 3 (NPL) accounts", len(npl_records))

        if npl_records:
            st.markdown("**Top 20 NPL accounts by outstanding:**")
            try:
                npl_sorted = sorted(
                    npl_records,
                    key=lambda r: float(r.get("outstanding", 0)),
                    reverse=True,
                )
            except Exception:
                npl_sorted = npl_records
            for r in npl_sorted[:20]:
                st.write(
                    f"• `{r.get('account_id', '?')}` "
                    f"{r.get('client_name', '?')} · "
                    f"outstanding={r.get('outstanding', 0):,} · "
                    f"npl_days={r.get('npl_days', '?')} · "
                    f"pd_12m={r.get('pd_12m', '?')}"
                )

        st.markdown("---")
        st.markdown("**Credit monitoring watchlist:**")
        wl = _credit_cached_watchlist()
        st.metric("Watchlist entries", len(wl))
        for entry in wl[:20]:
            st.write(
                f"• {entry.get('client', '?')} — "
                f"{entry.get('reason', 'no reason recorded')}"
            )

    # ---------- Tab 5: Credit admin ----------
    with tabs[4]:
        st.subheader("Approved credit book")
        admin = _credit_cached_credit_admin()
        st.metric("Approved facilities", len(admin))

        if admin:
            by_product = count_by(admin, "product")
            pcols = st.columns(2)
            pcols[0].write("**By product (top 10):**")
            for k, v in sorted(by_product.items(),
                                  key=lambda x: -x[1])[:10]:
                pcols[0].write(f"  {k or '(unset)'}: {v}")

            by_rm = count_by(admin, "rm_code")
            pcols[1].write("**Top 5 RMs by deal count:**")
            for k, v in sorted(by_rm.items(),
                                  key=lambda x: -x[1])[:5]:
                pcols[1].write(f"  {k or '(unset)'}: {v}")

            st.markdown("---")
            st.markdown("**Recent approvals (top 10):**")
            recent = latest_n(admin, n=10,
                                 by_field="approval_date")
            for r in recent:
                st.write(
                    f"• `{r.get('id', '?')}` "
                    f"app={r.get('application_id', '?')} · "
                    f"{r.get('client_name', '?')} · "
                    f"{r.get('product', '?')} · "
                    f"{r.get('amount', 0):,} · "
                    f"RM={r.get('rm_code', '?')}"
                )

    # ---------- Tab 6: Portfolio analytics ----------
    with tabs[5]:
        st.subheader("Portfolio analytics (Cat A composer)")
        st.caption(
            "v10.309 — composes AI underwriting + PD "
            "distribution + IRB capital into a single report. "
            "Refresh cached 60s."
        )

        from utils.cockpit_read import credit_portfolio_analytics
        report = _credit_cached_portfolio_analytics()

        audit_log(
            action="credit_portfolio_analytics_view",
            username=actor,
            module="credit_live",
        )

        # Header row
        kcols = st.columns(3)
        kcols[0].metric("Report ID", report["report_id"])
        kcols[1].metric("Sections", report["n_sections"])
        kcols[2].metric("Status", report["status"])

        # Section rendering
        st.markdown("---")
        st.markdown("**Sections:**")
        for s in report["sections"]:
            status_icon = {
                "ok": "✅", "warning": "⚠", "breach": "🛑",
                "no_data": "⚪", "error": "❌",
            }.get(s["status"], "•")
            st.markdown(
                f"**{status_icon} {s['section_title']}** · "
                f"`{s['section_id']}` · status: {s['status']}"
            )
            if s.get("notes"):
                st.caption(s["notes"])
            if s.get("metrics"):
                # Compact metric display
                metric_pairs = [
                    f"{k}={v}" for k, v in s["metrics"].items()
                ]
                st.write("  " + " · ".join(metric_pairs))

    # ---------- Tab 7: Audit trail ----------
    with tabs[6]:
        st.subheader("Credit decisions audit trail")
        audit_log(
            action="credit_audit_view",
            username=actor,
            module="credit_live",
        )

        # v10.305 — wired to the platform-wide audit_log.json
        # via the audit_log_records composer. Pre-filtered to
        # the credit_live module so operators see decisions
        # from this cockpit (and other credit-tagged actions).
        from utils.cockpit_read import audit_log_records

        # Operator filter UI
        fcols = st.columns(3)
        action_filter = fcols[0].text_input(
            "Filter by action (exact match)",
            value="", key="credit_audit_action_filter",
        ) or None
        user_filter = fcols[1].text_input(
            "Filter by user",
            value="", key="credit_audit_user_filter",
        ) or None
        limit_choice = fcols[2].selectbox(
            "Show last", [25, 50, 100, 250],
            index=1,
            key="credit_audit_limit",
        )

        trail = audit_log_records(
            data_dir="data",
            module="credit_live",
            action=action_filter,
            user=user_filter,
            limit=limit_choice,
        )

        mcols = st.columns(2)
        mcols[0].metric("Filtered records", trail["count"])
        mcols[1].metric(
            "Showing",
            min(trail["count"], limit_choice),
        )

        if not trail["records"]:
            st.info(
                "No audit records match the filter. Note: "
                "only credit_live-tagged actions appear here. "
                "Use the platform audit module page for the "
                "full audit log including SAR filings + BSC "
                "submissions + admin operations."
            )
        else:
            for r in trail["records"]:
                st.write(
                    f"• {r.get('ts', '?')[:19]} · "
                    f"{r.get('user', '?')} · "
                    f"`{r.get('action', '?')}` · "
                    f"{r.get('detail', '')[:80]}"
                )


# ════════════════════════════════════════════════════════════════
# COMPLIANCE — render + cache helpers
# ════════════════════════════════════════════════════════════════

@st.cache_data(ttl=10)
def _compliance_cached_open_work():
    return compliance_open_work(data_dir="data")


@st.cache_data(ttl=10)
def _compliance_cached_cases():
    return compliance_cases(data_dir="data")


@st.cache_data(ttl=10)
def _compliance_cached_alerts():
    return compliance_aml_alerts(data_dir="data")


@st.cache_data(ttl=10)
def _compliance_cached_sanctions():
    return compliance_sanctions_screening(data_dir="data")


@st.cache_data(ttl=10)
def _compliance_cached_returns():
    return compliance_regulatory_returns(data_dir="data")


@st.cache_data(ttl=60)  # Cat A composer is heavier — cache 60s
def _compliance_cached_cra_training():
    """v10.310 Cat A composer — wraps compliance_cra_training
    composing ComplianceRiskAssessmentEngine + ComplianceTrainingEngine."""
    from utils.cockpit_read import compliance_cra_training
    return compliance_cra_training(data_dir="data")


def render_compliance_cockpit(actor: str) -> None:
    """Render the COMPLIANCE live cockpit. Body extracted from
    pages/<original>_compliance_live.py main()."""
    st.title("⚖ Compliance Live Cockpit")
    st.caption(
        "v10.301 · Read-side composition of CMS engines "
        "(#191-#200) · Auto-refreshes every 10s · KYC/AML/"
        "Sanctions/Regulatory-return tracking"
    )

    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    cols = st.columns([4, 1])
    cols[0].caption(
        f"Loaded at: "
        f"{datetime.utcnow().isoformat(timespec='seconds')} UTC"
    )
    if cols[1].button("🔄 Refresh now"):
        st.cache_data.clear()
        audit_log(
            action="cockpit_cache_clear",
            username=actor,
            module="compliance_live",
        )
        st.rerun()

    tabs = st.tabs([
        "📊 Open work pulse",
        "🗂 Compliance cases",
        "🚨 AML alerts",
        "🔍 Sanctions screening",
        "📅 Regulatory returns",
        "🎯 CRA & training",
        "📜 Audit trail",
    ])

    # ---------- Tab 1: Open work pulse ----------
    with tabs[0]:
        st.subheader("Bank-wide Compliance landscape")
        st.caption(
            "Live counts across KYC cases, AML alerts, "
            "sanctions screening hits, and regulatory returns."
        )

        snap = _compliance_cached_open_work()

        cols = st.columns(4)
        cols[0].metric(
            "Cases open",
            snap["compliance_cases_open"],
            delta=(
                f"of {snap['compliance_cases_total']} total"
            ),
            delta_color="off",
        )
        cols[1].metric(
            "AML alerts (high risk)",
            snap["aml_alerts_high_risk"],
            delta=(
                f"{snap['aml_alerts_open']} open"
            ),
            delta_color="off",
        )
        cols[2].metric(
            "Sanctions hits pending",
            snap["sanctions_hits_pending_review"],
            delta=(
                f"of {snap['sanctions_screening_total']} "
                f"screenings"
            ),
            delta_color="off",
        )
        cols[3].metric(
            "Returns overdue",
            snap["regulatory_returns_overdue"],
            delta=(
                f"on-time: "
                f"{snap['regulatory_returns_on_time_pct']:.1f}%"
                if snap['regulatory_returns_on_time_pct']
                is not None
                else "no filed returns yet"
            ),
            delta_color="inverse",
        )

        # Risk distribution row
        st.markdown("---")
        st.markdown("**Compliance cases by risk level:**")
        risks = snap["compliance_cases_by_risk"]
        rcols = st.columns(3)
        rcols[0].metric("High", risks.get("high", 0))
        rcols[1].metric("Medium", risks.get("medium", 0))
        rcols[2].metric("Low", risks.get("low", 0))

        # Triage banners
        if snap["sanctions_hits_pending_review"] > 0:
            st.error(
                f"🛑 {snap['sanctions_hits_pending_review']} "
                f"sanctions match(es) await human review. "
                f"Regulatory SLA: escalate immediately."
            )
        if snap["regulatory_returns_overdue"] > 0:
            st.error(
                f"🛑 {snap['regulatory_returns_overdue']} "
                f"regulatory return(s) overdue. CBK / KRA "
                f"penalties accrue daily."
            )
        if snap["aml_alerts_high_risk"] > 5:
            st.warning(
                f"⚠ {snap['aml_alerts_high_risk']} high-risk "
                f"AML alerts open. Consider escalation to MLRO."
            )

    # ---------- Tab 2: Compliance cases ----------
    with tabs[1]:
        st.subheader("Compliance cases registry")
        cases = _compliance_cached_cases()
        st.metric("Total cases on file", len(cases))

        if not cases:
            st.info(
                "No records in data/compliance_cases.json."
            )
        else:
            by_status = count_by(cases, "status")
            by_flag = count_by(cases, "flag_type")
            by_risk = count_by(cases, "risk_level")

            pcols = st.columns(3)
            pcols[0].write("**By status:**")
            for k, v in sorted(by_status.items(),
                                  key=lambda x: -x[1]):
                pcols[0].write(f"  {k or '(unset)'}: {v}")
            pcols[1].write("**By flag type:**")
            for k, v in sorted(by_flag.items(),
                                  key=lambda x: -x[1])[:10]:
                pcols[1].write(f"  {k or '(unset)'}: {v}")
            pcols[2].write("**By risk:**")
            for k, v in sorted(by_risk.items(),
                                  key=lambda x: -x[1]):
                pcols[2].write(f"  {k or '(unset)'}: {v}")

            st.markdown("---")
            st.markdown(
                "**Recent cases (top 20 by raised_date):**"
            )
            recent = latest_n(cases, n=20,
                                 by_field="raised_date")
            for r in recent:
                st.write(
                    f"• `{r.get('id', '?')}` "
                    f"{r.get('client_name', '?')} · "
                    f"flag={r.get('flag_type', '?')} · "
                    f"risk={r.get('risk_level', '?')} · "
                    f"status={r.get('status', '?')}"
                )

    # ---------- Tab 3: AML alerts ----------
    with tabs[2]:
        st.subheader("AML monitoring alerts")
        st.caption(
            "AML rule-based + risk-scored alerts from "
            "utils.aml_monitoring.AmlMonitoringEngine "
            "(standard #194)."
        )
        alerts = _compliance_cached_alerts()
        st.metric("Total alerts on file", len(alerts))

        if not alerts:
            st.info("No records in data/aml_alerts.json.")
        else:
            by_rule = count_by(alerts, "rule_triggered")
            by_risk = count_by(alerts, "risk_level")

            pcols = st.columns(2)
            pcols[0].write("**By rule triggered (top 10):**")
            for k, v in sorted(by_rule.items(),
                                  key=lambda x: -x[1])[:10]:
                pcols[0].write(f"  {k or '(unset)'}: {v}")
            pcols[1].write("**By risk:**")
            for k, v in sorted(by_risk.items(),
                                  key=lambda x: -x[1]):
                pcols[1].write(f"  {k or '(unset)'}: {v}")

            st.markdown("---")
            st.markdown("**Recent alerts (top 20):**")
            recent = latest_n(alerts, n=20,
                                 by_field="transaction_date")
            for r in recent:
                st.write(
                    f"• `{r.get('id', '?')}` "
                    f"{r.get('customer_name', '?')} · "
                    f"amount={r.get('amount', 0):,} · "
                    f"rule={r.get('rule_triggered', '?')} · "
                    f"risk={r.get('risk_level', '?')} · "
                    f"status={r.get('status', '?')}"
                )

    # ---------- Tab 4: Sanctions screening ----------
    with tabs[3]:
        st.subheader("Sanctions screening queue")
        st.caption(
            "PEP + Sanctions matches from "
            "utils.sanctions_screening.SanctionsScreeningEngine "
            "(standard #192). Cleared/Confirmed/False-positive "
            "are terminal."
        )
        screenings = _compliance_cached_sanctions()
        st.metric("Total screenings on file", len(screenings))

        if not screenings:
            st.info(
                "No records in data/sanctions_register.json."
            )
        else:
            snap = _compliance_cached_open_work()
            st.metric(
                "Pending review (regulatorily critical)",
                snap["sanctions_hits_pending_review"],
            )

            by_source = count_by(screenings, "screening_source")
            by_status = count_by(screenings, "status")
            pcols = st.columns(2)
            pcols[0].write("**By screening source:**")
            for k, v in sorted(by_source.items(),
                                  key=lambda x: -x[1]):
                pcols[0].write(f"  {k or '(unset)'}: {v}")
            pcols[1].write("**By status:**")
            for k, v in sorted(by_status.items(),
                                  key=lambda x: -x[1]):
                pcols[1].write(f"  {k or '(unset)'}: {v}")

            st.markdown("---")
            st.markdown(
                "**Top 20 by match score (descending):**"
            )
            try:
                top_matches = sorted(
                    [s for s in screenings
                     if isinstance(s, dict)],
                    key=lambda r: float(r.get("match_score") or 0),
                    reverse=True,
                )[:20]
            except Exception:
                top_matches = screenings[:20]
            for r in top_matches:
                st.write(
                    f"• `{r.get('id', '?')}` "
                    f"{r.get('customer_name', '?')} · "
                    f"match={r.get('match_score', '?')} · "
                    f"list={r.get('list_matched', '?')} · "
                    f"status={r.get('status', '?')}"
                )

    # ---------- Tab 5: Regulatory returns ----------
    with tabs[4]:
        st.subheader("Regulatory filing calendar")
        st.caption(
            "Returns to CBK, KRA, and other authorities. "
            "Overdue items accrue penalties daily — escalate "
            "to Head of Compliance."
        )
        returns = _compliance_cached_returns()
        st.metric("Total returns tracked", len(returns))

        snap = _compliance_cached_open_work()
        kcols = st.columns(2)
        kcols[0].metric(
            "Overdue",
            snap["regulatory_returns_overdue"],
            delta_color="inverse",
        )
        on_time_display = (
            f"{snap['regulatory_returns_on_time_pct']:.1f}%"
            if snap["regulatory_returns_on_time_pct"] is not None
            else "—"
        )
        kcols[1].metric(
            "On-time filing rate",
            on_time_display,
        )

        if returns:
            by_freq = count_by(returns, "frequency")
            by_status = count_by(returns, "status")
            pcols = st.columns(2)
            pcols[0].write("**By frequency:**")
            for k, v in sorted(by_freq.items(),
                                  key=lambda x: -x[1]):
                pcols[0].write(f"  {k or '(unset)'}: {v}")
            pcols[1].write("**By status:**")
            for k, v in sorted(by_status.items(),
                                  key=lambda x: -x[1]):
                pcols[1].write(f"  {k or '(unset)'}: {v}")

            st.markdown("---")
            st.markdown(
                "**Returns with nearest due date (top 15):**"
            )
            # Sort by due_date ascending so soonest surface
            try:
                upcoming = sorted(
                    [r for r in returns
                     if isinstance(r, dict)
                     and r.get("due_date")],
                    key=lambda r: r.get("due_date", ""),
                )[:15]
            except Exception:
                upcoming = returns[:15]
            for r in upcoming:
                filed = r.get("filed_date") or "—"
                st.write(
                    f"• `{r.get('id', '?')}` "
                    f"{r.get('return_name', '?')} · "
                    f"due={r.get('due_date', '?')} · "
                    f"filed={filed} · "
                    f"on_time={r.get('on_time', '?')}"
                )

    # ---------- Tab 6: CRA & training ----------
    with tabs[5]:
        st.subheader("Compliance Risk Assessment & Training")
        st.caption(
            "v10.310 — Cat A composer. Composes "
            "ComplianceRiskAssessmentEngine (#198) + "
            "ComplianceTrainingEngine (#197). Refresh cached "
            "60s."
        )

        from utils.cockpit_read import compliance_cra_training
        report = _compliance_cached_cra_training()

        audit_log(
            action="compliance_cra_training_view",
            username=actor,
            module="compliance_live",
        )

        # Header row
        kcols = st.columns(3)
        kcols[0].metric("Report ID", report["report_id"])
        kcols[1].metric("Sections", report["n_sections"])
        kcols[2].metric("Status", report["status"])

        # Section rendering
        st.markdown("---")
        st.markdown("**Sections:**")
        for s in report["sections"]:
            status_icon = {
                "ok": "✅", "warning": "⚠", "breach": "🛑",
                "no_data": "⚪", "error": "❌",
            }.get(s["status"], "•")
            st.markdown(
                f"**{status_icon} {s['section_title']}** · "
                f"`{s['section_id']}` · status: {s['status']}"
            )
            if s.get("notes"):
                st.caption(s["notes"])
            if s.get("metrics"):
                metric_pairs = [
                    f"{k}={v}" for k, v in s["metrics"].items()
                ]
                st.write("  " + " · ".join(metric_pairs))

    # ---------- Tab 7: Audit trail ----------
    with tabs[6]:
        st.subheader("Compliance decisions audit trail")
        audit_log(
            action="compliance_audit_view",
            username=actor,
            module="compliance_live",
        )

        # v10.305 — wired to the platform-wide audit_log.json
        # via the audit_log_records composer. Pre-filtered to
        # the compliance_live module so operators see
        # decisions made through this cockpit (sanctions
        # reviews, SAR triage, etc.).
        from utils.cockpit_read import audit_log_records

        fcols = st.columns(3)
        action_filter = fcols[0].text_input(
            "Filter by action (exact match)",
            value="", key="compliance_audit_action_filter",
        ) or None
        user_filter = fcols[1].text_input(
            "Filter by user",
            value="", key="compliance_audit_user_filter",
        ) or None
        limit_choice = fcols[2].selectbox(
            "Show last", [25, 50, 100, 250],
            index=1,
            key="compliance_audit_limit",
        )

        trail = audit_log_records(
            data_dir="data",
            module="compliance_live",
            action=action_filter,
            user=user_filter,
            limit=limit_choice,
        )

        mcols = st.columns(2)
        mcols[0].metric("Filtered records", trail["count"])
        mcols[1].metric(
            "Showing",
            min(trail["count"], limit_choice),
        )

        if not trail["records"]:
            st.info(
                "No audit records match the filter. Note: only "
                "compliance_live-tagged actions appear here. "
                "SAR filing decisions are audit-logged "
                "separately under module=sar_filing via "
                "utils.sar_filing — query without the "
                "compliance_live module filter to see those, "
                "or visit the SAR module page directly."
            )
        else:
            for r in trail["records"]:
                st.write(
                    f"• {r.get('ts', '?')[:19]} · "
                    f"{r.get('user', '?')} · "
                    f"`{r.get('action', '?')}` · "
                    f"{r.get('detail', '')[:80]}"
                )

