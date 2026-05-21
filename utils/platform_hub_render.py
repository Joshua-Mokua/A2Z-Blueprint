"""
utils/platform_hub_render.py — v10.349 (Option E, sub-batch 5).

Single source of truth for the 4 Platform/IT render functions.
Extracted from pages/91_systems_view, 96_it_digital_pt1,
97_it_digital_pt2, 98_platform_health. The original 4 pages now
import their render function from here; pages/119_platform_hub.py
is the consolidated entry with area selector.
"""

from __future__ import annotations

from __future__ import annotations
from datetime import datetime
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json
import pandas as pd
import streamlit as st
import subprocess
import sys

from utils.core_audit import audit_log
from utils.it_api_gateway import APIGatewayEngine, API_VERSION_STATES, RATE_LIMIT_WINDOWS, AUTH_SCHEMES, API_KEY_STATES
from utils.it_cbk_compliance import CBKComplianceEngine, COMPLIANCE_FRAMEWORKS, PROGRAM_STATES, CONTROL_CATEGORIES, FINDING_SEVERITIES, FINDING_STATES, CERTIFICATION_STATES, CBK_REGULATORY_REFERENCE, DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY
from utils.it_cicd import CICDEngine, PIPELINE_TYPES, PIPELINE_STAGES, PIPELINE_STATES, RUN_STATES, ENVIRONMENT_TYPES, DEFAULT_BUILD_TIMEOUT_MINUTES, DEFAULT_DEPLOY_TIMEOUT_MINUTES
from utils.it_cloud_architecture import CloudArchitectureEngine, CLOUD_PROVIDERS, CONTAINER_RUNTIMES, DEPLOYMENT_STRATEGIES, DEPLOYMENT_STATES, TWELVE_FACTOR_CRITERIA
from utils.it_data_encryption import DataEncryptionEngine, ENCRYPTION_ALGORITHMS, KEY_STATES, KEY_USAGE_PURPOSES, SECRET_TYPES, SECURITY_EVENT_TYPES, PII_SENSITIVITY_LEVELS, DEFAULT_KEY_ROTATION_DAYS, DEFAULT_SECRET_ROTATION_DAYS, DPA_KENYA_REGULATORY_REFERENCE
from utils.it_digital_banking import DigitalBankingEngine, APP_PLATFORMS, APP_VERSION_STATES, SESSION_STATES, NOTIFICATION_TYPES, NOTIFICATION_STATES, BIOMETRIC_TYPES, DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES, DEFAULT_SESSION_HARD_TIMEOUT_MINUTES
from utils.it_disaster_recovery import DisasterRecoveryEngine, DR_PLAN_TIERS, DR_PLAN_STATES, DRILL_TYPES, DRILL_STATES, DEFAULT_RTO_TARGET_HOURS, DEFAULT_RPO_TARGET_MINUTES, CBK_DR_REGULATORY_REFERENCE
from utils.it_itsm import ITSMFrameworkEngine, ITSM_INCIDENT_PRIORITIES, ITSM_INCIDENT_STATES, CHANGE_TYPES, CHANGE_STATES, ASSET_TYPES, ASSET_STATES, KNOWLEDGE_ARTICLE_STATES
from utils.it_multi_tenancy import MultiTenancyEngine, TENANT_STATES, ISOLATION_MODELS, BRANDING_ELEMENTS, FLAG_TYPES, FEATURE_FLAG_STATES
from utils.it_observability import ObservabilityEngine, SLI_TYPES, SLO_TIME_WINDOWS, SLO_STATES, ERROR_BUDGET_POLICIES, DEFAULT_BUDGET_BURN_THRESHOLD_PCT
from utils.page_access import require_access
from utils.page_shared import load_shared_state
from utils.system_flows import FEEDBACK_LOOPS, list_loops, loops_by_status, loop_count_by_status, wired_pct, learning_loops, LOOP_WIRED, LOOP_DESIGNED_NOT_WIRED, LOOP_PARTIAL
from utils.system_invariants import SYSTEM_INVARIANTS, list_invariants, invariant_count_by_severity
from utils.system_stocks import SYSTEM_STOCKS, list_stocks, stock_count_by_status, get_stock_snapshot, STOCK_WIRED, STOCK_NOT_WIRED, STOCK_PARTIAL


# ════════════════════════════════════════════════════════════════
# SYSTEMS_VIEW — render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/91_systems_view.py — A2Z Systems Layer dashboard (v7.0).

THE FOOTBALL TEAM PAGE.

This page makes the systems layer (Charter v7.0) visible. It's not a
new domain page — it's a **meta-page** that surfaces how A2Z works as
a system, not as a library.

Sections:
  1️⃣ The One Question — single tile: is the bank on track?
  2️⃣ System Stocks — 6 accumulators with status
  3️⃣ Feedback Loops — 15 designed loops with wired status
  4️⃣ Hard Invariants — 8 non-linear constraints
  5️⃣ Boundary Awareness — what A2Z is and is not
  6️⃣ Bounded Contexts — the 13 sub-domains

This page is the v7.0 systems-view materialised. Future v7.x batches
deepen each section.

References:
  Donella Meadows, *Thinking in Systems* (2008)
  A2Z Systems Charter, all sections
  Eric Evans, *Domain-Driven Design* (2003)
  Stafford Beer, *The Heart of Enterprise* (1979)
"""

# Systems layer imports


# ──────────────────────────────────────────────────────────────────────
# Page setup + access control
# ──────────────────────────────────────────────────────────────────────


def render_systems_view(actor: str) -> None:
    """Render the systems_view view. Body extracted from
    the original page."""
    um, ud, uname, *_ = load_shared_state()[:12]

    st.title("🏛️ A2Z Systems View")
    st.caption(
        "**The football team page (v7.0).** Most A2Z pages surface a "
        "domain (HR, AML, Treasury). This page surfaces *the system* — "
        "the layer above all 116 engines that defines purpose, stocks, "
        "feedback loops, invariants, and boundaries. "
        "Reference: `docs/A2Z_SYSTEMS_CHARTER.md`."
    )

    audit_log("SYSTEMS_VIEW_OPENED", uname,
               "User opened v7.0 systems view dashboard")

    tabs = st.tabs([
        "1️⃣ The One Question",
        "2️⃣ System Stocks",
        "3️⃣ Feedback Loops",
        "4️⃣ Hard Invariants",
        "5️⃣ Boundary Awareness",
        "6️⃣ Bounded Contexts",
        "7️⃣ Health Composites",
    ])


    # ════════════════════════════════════════════════════════════════
    # TAB 1 — The One Question
    # ════════════════════════════════════════════════════════════════
    with tabs[0]:
        st.markdown("### The One Question")
        st.markdown(
            "> **\"Is the bank on track to achieve its strategic goals, "
            "and if not, what should I do about it?\"**"
        )
        st.caption(
            "Charter Section 1. Every module, every standard, every feature "
            "must serve this question. Features that do only the first half "
            "(measurement) without enabling the second half (action) are "
            "incomplete by design."
        )

        st.markdown("### Football team test")
        st.markdown(
            "> **\"Can the Managing Director see, in real-time, the impact "
            "of a teller's action on the bank's ROE — and trace the chain "
            "of cause-and-effect across every layer in between?\"**"
        )
        st.caption(
            "Charter Section 2. This is the long-term acceptance criterion. "
            "As of v7.0 we cannot pass this test fully. Each subsequent "
            "batch should advance the test, not regress it."
        )

        # System health summary — composes stocks + loops + invariants
        st.markdown("### System health summary (v7.0)")

        stock_counts = stock_count_by_status()
        loop_counts = loop_count_by_status()
        inv_counts = invariant_count_by_severity()
        wired = wired_pct()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("System stocks defined",
                    len(SYSTEM_STOCKS),
                    help="Charter §5 — Customer base, loan portfolio, "
                         "deposit base, NPL inventory, dormant accounts, "
                         "capital base.")
        c2.metric("Feedback loops",
                    f"{loop_counts.get(LOOP_WIRED, 0)}/{len(FEEDBACK_LOOPS)} wired",
                    f"{wired:.0f}%",
                    help="Charter §8 — 15 designed loops; future batches "
                         "close gaps.")
        c3.metric("Hard invariants",
                    len(SYSTEM_INVARIANTS),
                    help="Charter §6 — non-linear constraints from CBK, "
                         "Basel III, IFRS 9, bank policy.")
        c4.metric("Bounded contexts",
                    "13",
                    help="Charter §3 — DDD sub-domains.")

        st.markdown("### How to read this page")
        st.markdown(
            "- **Tab 2** shows the 6 stocks (Meadows' *system memory*). "
            "Today all 6 are **NOT_WIRED** in A2Z's snapshot accessor — "
            "they exist in CBS but aren't first-class A2Z citizens yet. "
            "v7.x batches will wire them.\n"
            "- **Tab 3** shows the 15 feedback loops. **5 are WIRED** "
            "(L02, L03, L08, L12, L15). **10 remain designed-not-wired** "
            "— closing them is the work of v7.x.\n"
            "- **Tab 4** shows the 8 invariants. As of v7.0 only "
            "stress_testing reads from this registry; other engines "
            "still hard-code thresholds. Migration is incremental.\n"
            "- **Tabs 5 + 6** are reference — boundaries and contexts "
            "the system honours."
        )

        st.info(
            "💡 **Honesty discipline (Rule 6):** Where data is not yet "
            "wired, this page surfaces NOT_WIRED rather than fabricating "
            "zero. Every gap visible here is documented in "
            "`docs/A2Z_SYSTEMS_CHARTER.md` Section 14."
        )


    # ════════════════════════════════════════════════════════════════
    # TAB 2 — System Stocks
    # ════════════════════════════════════════════════════════════════
    with tabs[1]:
        st.markdown("### System Stocks (Meadows' accumulators)")
        st.caption(
            "Donella Meadows: *stocks are the memory of the system*. They "
            "change slowly even when flows are fast, and the system's "
            "behaviour comes from how stocks evolve. A2Z explicitly tracks "
            "6 stocks (Charter §5)."
        )

        # v7.10/v7.11/v8.1/v8.2: FLEXCUBE mode banner — explicit data-source provenance
        try:
            from utils.flexcube_adapter import (get_mode as _fc_mode,
                                                  get_circuit_state as _fc_circuit,
                                                  get_latency_state as _fc_latency,
                                                  get_retry_telemetry as _fc_retry,
                                                  get_config as _fc_config)
            _mode = _fc_mode()
            _mode_label = {
                "live": "🟢 LIVE — pulling from FLEXCUBE Apigee",
                "mock": "🟡 MOCK — synthetic data, simulated API path",
                "synthetic": "⚪ SYNTHETIC — demo defaults / CBS files",
            }.get(_mode, f"❓ {_mode}")
            st.info(
                f"**FLEXCUBE mode:** {_mode_label}. "
                f"v7.10 wired loan_portfolio + deposit_base + npl_inventory; "
                f"v7.11 extended to customer_base + dormant_accounts. "
                f"**5 of 6 stocks now flow through `flexcube_aggregator` ACL** "
                f"(capital_base remains engine-derived from CapitalAdequacyEngine). "
                f"When the bank flips mode to `live`, no caller code change needed."
            )

            # v8.1 circuit breaker status — operator visibility into resilience layer
            _cs = _fc_circuit()
            if _cs["is_open"]:
                st.error(
                    f"🚨 **FLEXCUBE circuit breaker OPEN** — "
                    f"{_cs['consecutive_failures']} consecutive failures detected; "
                    f"live calls are fast-failing for {_cs['seconds_until_close']:.0f} more seconds. "
                    f"ACL is falling through to demo defaults. "
                    f"(Per CBK Operations Resilience Guidelines: trip threshold "
                    f"= {_cs['threshold']} failures, open duration = "
                    f"{_cs['open_duration_seconds']:.0f}s, retries = "
                    f"{_cs['retry_attempts']} with backoff "
                    f"{_cs['retry_backoff_seconds']}s.)"
                )
            elif _cs["consecutive_failures"] > 0:
                st.warning(
                    f"⚠ **FLEXCUBE intermittent failures** — "
                    f"{_cs['consecutive_failures']} of {_cs['threshold']} "
                    f"consecutive failure(s) recorded. Circuit will trip if "
                    f"{_cs['threshold'] - _cs['consecutive_failures']} more "
                    f"consecutive call(s) fail."
                )
            # else: silent (healthy state)

            # v8.9 admin: reset_circuit button (visible when circuit has any
            # accumulated failures, including OPEN state). Restart-free recovery.
            if _cs["is_open"] or _cs["consecutive_failures"] > 0:
                try:
                    from utils.flexcube_adapter import reset_circuit as _fc_reset
                    if st.button(
                        "🔄 Reset circuit breaker",
                        key="systems_view_circuit_reset",
                        help=("Manually clear consecutive_failures + tripped_until "
                              "without restarting. Use after FLEXCUBE outage is "
                              "resolved or when re-probing."),
                    ):
                        reset_result = _fc_reset()
                        st.success(
                            f"✓ Circuit reset at {reset_result['reset_at_iso'][:19]} "
                            f"— prior_consecutive_failures="
                            f"{reset_result['prior_consecutive_failures']}, "
                            f"prior_was_open={reset_result['prior_was_open']}, "
                            f"current_state={reset_result['current_state']}."
                        )
                except Exception:
                    pass

            # v8.18 — per-endpoint circuit detail (closes v8.17's UI surface).
            # Renders a small table when 1+ endpoints are tracked, with per-endpoint
            # selective reset buttons.
            _per_ep = _cs.get("per_endpoint", {})
            if _per_ep:
                with st.expander(
                    f"🎯 Per-endpoint circuit state (v8.17) — "
                    f"{_cs.get('endpoints_tracked', len(_per_ep))} endpoint(s) tracked",
                    expanded=_cs["is_open"],  # auto-expand when something is open
                ):
                    st.caption(
                        "Per v8.17 refactor (closes v8.6 retrospective ack #6): "
                        "each FLEXCUBE endpoint has its own circuit state — a "
                        "tripped NPL endpoint does NOT block Loans/Deposits/etc. "
                        "Aligns A2Z with Newman 2015 + Nygard 2007 canonical pattern."
                    )
                    # Render table
                    import pandas as _pd
                    rows = []
                    for ek, st_dict in sorted(_per_ep.items()):
                        rows.append({
                            "Endpoint": ek,
                            "Consecutive failures": st_dict["consecutive_failures"],
                            "Status": "🚨 OPEN" if st_dict["is_open"] else "✅ Closed",
                            "Reopens in (s)": f"{st_dict['seconds_until_close']:.0f}"
                                              if st_dict["is_open"] else "—",
                        })
                    if rows:
                        _df = _pd.DataFrame(rows)
                        st.dataframe(_df, use_container_width=True, hide_index=True)

                    # Per-endpoint selective reset (only show buttons for non-clean states)
                    troubled = [ek for ek, s in _per_ep.items()
                                 if s["is_open"] or s["consecutive_failures"] > 0]
                    if troubled:
                        st.markdown("**Selective reset** (clears one endpoint without affecting others):")
                        cols = st.columns(min(len(troubled), 3))
                        for idx, ek in enumerate(troubled):
                            col = cols[idx % len(cols)]
                            with col:
                                if st.button(
                                    f"🔄 {ek}",
                                    key=f"systems_view_circuit_reset_{ek.replace('/', '_')}",
                                    use_container_width=True,
                                    help=f"Reset only the {ek} circuit; other endpoints unaffected.",
                                ):
                                    try:
                                        from utils.flexcube_adapter import reset_circuit as _fc_reset_ep
                                        r = _fc_reset_ep(endpoint_key=ek)
                                        st.success(
                                            f"✓ {ek} reset — "
                                            f"prior_failures={r['prior_consecutive_failures']}, "
                                            f"prior_was_open={r['prior_was_open']}"
                                        )
                                    except Exception as ex:
                                        st.error(f"Reset failed: {type(ex).__name__}: {ex}")

            # v8.2 latency telemetry — per-endpoint p50/p95/p99 (only render if any
            # samples have been collected; silent in synthetic mode where no live
            # calls occur)
            _ls = _fc_latency()
            if _ls["summary"]["total_calls"] > 0:
                with st.expander(
                    f"📊 FLEXCUBE latency telemetry (v8.2) — "
                    f"{_ls['summary']['total_calls']} calls observed, "
                    f"{_ls['summary']['overall_success_rate_pct']}% success rate",
                    expanded=False,
                ):
                    st.caption(
                        f"Rolling window of last {_ls['summary']['window_size']} samples "
                        f"per endpoint. Latencies cover full request including retry "
                        f"backoff on failures. Circuit-open fast-fail responses are "
                        f"suppressed from telemetry (they're not real round-trips)."
                    )
                    ep_rows = []
                    for ep, stats in sorted(_ls["endpoints"].items()):
                        ep_rows.append({
                            "Endpoint": ep,
                            "Calls": stats["count"],
                            "Success %": stats["success_rate_pct"],
                            "p50 (ms)": stats["p50_ms"],
                            "p95 (ms)": stats["p95_ms"],
                            "p99 (ms)": stats["p99_ms"],
                            "Last": stats["latest_outcome"],
                        })
                    if ep_rows:
                        st.dataframe(pd.DataFrame(ep_rows),
                                     use_container_width=True, hide_index=True)

            # v8.21 — retry telemetry expander (closes UI surface for v8.19).
            # Renders only if any requests have been observed.
            _rt = _fc_retry()
            if _rt["summary"]["requests_total"] > 0:
                recovery = _rt["summary"]["retry_recovery_rate_pct"]
                recovery_str = f"{recovery}%" if recovery is not None else "—"
                with st.expander(
                    f"🔁 FLEXCUBE retry telemetry (v8.19) — "
                    f"{_rt['summary']['requests_total']} requests, "
                    f"{_rt['summary']['retries_triggered']} retries, "
                    f"recovery rate {recovery_str}",
                    expanded=False,
                ):
                    st.caption(
                        "Per v8.19 + v8.6 retrospective ack #9: each FLEXCUBE "
                        "endpoint tracks how often the retry pattern "
                        "successfully recovered transient failures. High recovery "
                        "rate = retries are doing their job. Low rate = root cause "
                        "needs investigation (FLEXCUBE-side, network, or auth)."
                    )
                    rt_rows = []
                    for ek, s in sorted(_rt["per_endpoint"].items()):
                        rec_pct = s["retry_recovery_rate_pct"]
                        rt_rows.append({
                            "Endpoint": ek,
                            "Requests": s["requests_total"],
                            "Retries": s["retries_triggered"],
                            "Avg retries": s["avg_retries_per_request"],
                            "1st-try OK": s["succeeded_no_retry"],
                            "Recovered": s["succeeded_after_retry"],
                            "Failed": s["failed_after_retries"],
                            "Recovery %": f"{rec_pct}%" if rec_pct is not None else "—",
                        })
                    if rt_rows:
                        st.dataframe(pd.DataFrame(rt_rows),
                                     use_container_width=True, hide_index=True)

            # v8.21 — per-endpoint timeout config display (closes UI surface for v8.20).
            # Always rendered (config is static, not derived from runtime samples).
            try:
                _cfg = _fc_config()
                _ep_timeouts = _cfg.get("endpoint_timeouts", {})
                if _ep_timeouts:
                    with st.expander(
                        f"⏱️ FLEXCUBE per-endpoint timeouts (v8.20) — "
                        f"{len(_ep_timeouts)} endpoint(s) with overrides",
                        expanded=False,
                    ):
                        st.caption(
                            "Per v8.20 + v8.6 retrospective ack #7: each "
                            "FLEXCUBE endpoint can have its own timeout. "
                            "Endpoints not listed below fall through to the "
                            "default `batch_seconds` ({}s) or `rest_seconds` ({}s).".format(
                                _cfg.get("timeouts", {}).get("batch_seconds", "?"),
                                _cfg.get("timeouts", {}).get("rest_seconds", "?"))
                        )
                        to_rows = [
                            {"Endpoint": ek, "Timeout (s)": secs}
                            for ek, secs in sorted(_ep_timeouts.items())
                        ]
                        st.dataframe(pd.DataFrame(to_rows),
                                     use_container_width=True, hide_index=True)
                        st.caption(
                            "To override: edit `endpoint_timeouts` in "
                            "`utils/flexcube_adapter.py`'s `_default_config()` "
                            "or save a custom config. Per-endpoint overrides "
                            "supersede the default `batch_seconds`."
                        )
            except Exception:
                pass
        except Exception:
            pass

        stocks_df = pd.DataFrame(list_stocks())
        st.dataframe(stocks_df, use_container_width=True, hide_index=True)

        st.markdown("### Stock detail")
        selected_stock_id = st.selectbox(
            "Inspect a stock",
            options=list(SYSTEM_STOCKS.keys()),
            format_func=lambda sid: f"{sid} — {SYSTEM_STOCKS[sid].name}",
            key="systems_view_stock_select",
        )

        if selected_stock_id:
            stock = SYSTEM_STOCKS[selected_stock_id]
            snapshot = get_stock_snapshot(selected_stock_id)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**{stock.name}**")
                st.markdown(f"- **Unit**: {stock.unit}")
                st.markdown(f"- **Owner context**: {stock.owner_context}")
                st.markdown(f"- **Status**: `{stock.status}`")
                st.markdown(f"- **Why first-class**: {stock.why_first_class}")
            with c2:
                st.markdown("**Accumulation rule:**")
                st.code(stock.accumulation_rule, language="text")

            st.markdown("**Contributors (engines that add):**")
            for c in stock.contributors:
                st.markdown(f"- `{c}`")
            st.markdown("**Drainers (engines that remove):**")
            for d in stock.drainers:
                st.markdown(f"- `{d}`")

            if stock.notes:
                st.info(f"**Notes:** {stock.notes}")

            st.markdown("**Live snapshot:**")
            if snapshot["status"] == STOCK_NOT_WIRED:
                st.warning(
                    f"⚠ Stock not yet wired to live data. Reason: "
                    f"_{snapshot.get('reason', 'unknown')}_"
                )
            elif snapshot["status"] == STOCK_WIRED:
                st.success(f"✅ Live value: {snapshot.get('value')} {snapshot.get('unit')}")
            else:
                st.info(f"Status: {snapshot['status']}")


    # ════════════════════════════════════════════════════════════════
    # TAB 3 — Feedback Loops
    # ════════════════════════════════════════════════════════════════
    with tabs[2]:
        st.markdown("### Feedback Loops (Meadows' system structure)")
        st.caption(
            "*A system is its feedback loops.* A2Z has 15 designed loops "
            "(Charter §8). The registry in `utils/system_flows.py` tracks "
            "wiring status — future batches close the gaps."
        )

        counts = loop_count_by_status()
        wired_n = counts.get(LOOP_WIRED, 0)
        designed_n = counts.get(LOOP_DESIGNED_NOT_WIRED, 0)
        partial_n = counts.get(LOOP_PARTIAL, 0)
        total = wired_n + designed_n + partial_n

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total loops", total)
        c2.metric("Wired ✅", wired_n,
                    help="Live in code today.")
        c3.metric("Designed not wired ⚠", designed_n,
                    delta_color="inverse" if designed_n > 0 else "normal",
                    help="Documented but not yet wired. Future batch work.")
        c4.metric("Wired %", f"{wired_pct():.0f}%")

        # Learning loops callout
        ll = learning_loops()
        ll_wired = sum(1 for l in ll if l.status == LOOP_WIRED)
        if ll:
            st.info(
                f"💡 **{len(ll)} learning loops** (Meadows' highest-value "
                f"type — outcomes recalibrate behaviour): "
                f"{ll_wired} wired, {len(ll) - ll_wired} pending. "
                "Learning loops are what make a system *adaptive* rather "
                "than just reactive."
            )

        st.markdown("### All 15 designed loops")
        loop_rows = []
        for loop in list_loops():
            status_emoji = {
                LOOP_WIRED: "✅",
                LOOP_DESIGNED_NOT_WIRED: "⚠",
                LOOP_PARTIAL: "🟡",
            }.get(loop.status, "❓")
            loop_rows.append({
                "ID": loop.loop_id,
                "Loop": loop.name,
                "From": loop.from_context,
                "To": loop.to_context,
                "Pattern": loop.pattern.replace("_", " ").title(),
                "Status": f"{status_emoji} {loop.status}",
                "Learning?": "🧠" if loop.learning_loop else "—",
            })
        st.dataframe(pd.DataFrame(loop_rows),
                      use_container_width=True, hide_index=True)

        st.markdown("### Loop detail")
        selected_loop_id = st.selectbox(
            "Inspect a loop",
            options=list(FEEDBACK_LOOPS.keys()),
            format_func=lambda lid: f"{lid} — {FEEDBACK_LOOPS[lid].name}",
            key="systems_view_loop_select",
        )

        if selected_loop_id:
            loop = FEEDBACK_LOOPS[selected_loop_id]
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**{loop.name}**")
                st.markdown(f"- **From**: `{loop.from_engine}`")
                st.markdown(f"- **To**: `{loop.to_engine}`")
                st.markdown(f"- **Pattern**: {loop.pattern}")
                st.markdown(f"- **Status**: `{loop.status}`")
                if loop.learning_loop:
                    st.markdown("- 🧠 **Learning loop** (outcomes recalibrate behaviour)")
            with c2:
                st.markdown("**Payload:**")
                st.code(loop.payload, language="text")
                st.markdown(f"- **Detection delay**: {loop.detection_delay}")
                st.markdown(f"- **Response delay**: {loop.response_delay}")

            st.markdown("**Purpose:**")
            st.write(loop.purpose)

            if loop.notes:
                st.info(f"**Notes:** {loop.notes}")

        # ─────────────────────────────────────────────────────────────
        # v8.5: L14 Channel Reliability → Smart Alerts — interactive surface
        # Completes the 'engine + loop + UI' canonical sequence (matches
        # v7.12/v7.13 pattern that closed L05 cards).
        # ─────────────────────────────────────────────────────────────
        with st.expander(
            "📡 L14 Channel Reliability → Smart Alerts (v8.4 engine / v8.5 surfaced)",
            expanded=False,
        ):
            try:
                from utils.channels_reliability import (
                    ChannelReliabilityProducer,
                    CHANNEL_TYPES,
                    SEVERITY_OUTAGE, SEVERITY_DEGRADATION, SEVERITY_SLA_BREACH,
                    CHANNEL_RELIABILITY_TOPIC,
                )
                from utils.smart_alerts import SmartAlertsConsumer
                from utils.event_bus import get_topic_stats, clear_topic
            except Exception as _e:
                st.error(f"L14 modules not importable: {_e}")
            else:
                st.caption(
                    "v8.4 closed L14 — the campaign's last unwired loop — via "
                    "`utils/event_bus.py` (file-backed JSON-lines bus) + "
                    "`utils/channels_reliability.py` PRODUCER + "
                    "`utils/smart_alerts.py` CONSUMER. v8.5 surfaces the chain "
                    "here so operators can see channel-reliability events flow "
                    "end-to-end into customer alerts. Production deployment can "
                    "swap event_bus for Kafka without changing producer/consumer."
                )

                # Topic stats (live snapshot)
                stats = get_topic_stats(CHANNEL_RELIABILITY_TOPIC)
                sc1, sc2, sc3 = st.columns(3)
                sc1.metric("Events on bus", stats.get("count", 0))
                sc2.metric("Next event_id", stats.get("next_event_id", 1))
                if stats.get("newest_ts"):
                    sc3.metric("Latest event", stats["newest_ts"][:19])
                else:
                    sc3.metric("Latest event", "—")

                st.markdown("---")
                st.markdown("**▶ Emit a test event (PRODUCER side):**")
                col_a, col_b = st.columns(2)
                with col_a:
                    _ch = st.selectbox(
                        "Channel",
                        options=list(CHANNEL_TYPES),
                        key="l14_emit_channel",
                    )
                    _sev = st.selectbox(
                        "Severity",
                        options=[SEVERITY_OUTAGE, SEVERITY_DEGRADATION,
                                  SEVERITY_SLA_BREACH],
                        key="l14_emit_severity",
                    )
                with col_b:
                    _loc = st.text_input(
                        "Location (branch code or 'BANK_WIDE')",
                        value="BANK_WIDE",
                        key="l14_emit_location",
                    )
                    _affected = st.number_input(
                        "Estimated affected customers",
                        min_value=0, max_value=1_000_000, value=500, step=100,
                        key="l14_emit_affected",
                    )

                _desc = st.text_input(
                    "Description",
                    value=f"Test event from page 91 — {_ch}/{_sev}",
                    key="l14_emit_description",
                )

                ec1, ec2 = st.columns([1, 3])
                if ec1.button("📤 Emit event", key="l14_emit_button"):
                    result = ChannelReliabilityProducer.report_event(
                        channel_type=_ch, severity=_sev, location=_loc,
                        description=_desc,
                        estimated_affected_customers=int(_affected),
                    )
                    if result["status"] == "PUBLISHED":
                        ec2.success(
                            f"✓ Published event_id={result['event_id']} at "
                            f"{result['timestamp_iso'][:19]}"
                        )
                    else:
                        ec2.error(
                            f"✗ {result['status']}: {result.get('reason', 'unknown')}"
                        )

                if ec1.button("🗑️ Clear bus", key="l14_clear_button",
                                help="Clear all events for this topic (admin/test)"):
                    cleared = clear_topic(CHANNEL_RELIABILITY_TOPIC)
                    ec2.info(f"Cleared {cleared} events from "
                              f"`{CHANNEL_RELIABILITY_TOPIC}` topic")

                # v8.9 admin: replay_events button — operator debugging/audit
                if ec1.button("🔁 Replay events (audit snapshot)",
                                key="l14_replay_button",
                                help=("Generate a JSON-style audit snapshot of "
                                      "recent events with full metadata for "
                                      "operator debugging or regulatory review.")):
                    try:
                        from utils.event_bus import replay_events as _bus_replay
                        snap = _bus_replay(CHANNEL_RELIABILITY_TOPIC,
                                            since_event_id=0, limit=10)
                        ec2.success(
                            f"✓ Replay snapshot at {snap['replay_at_iso'][:19]} — "
                            f"{snap['count']} event(s) "
                            f"(showing first 10; oldest_ts="
                            f"{(snap['oldest_ts'] or '—')[:19]}, "
                            f"newest_ts={(snap['newest_ts'] or '—')[:19]})."
                        )
                        if snap['events']:
                            with st.expander("📋 Replay snapshot (10 most recent)",
                                              expanded=True):
                                st.json(snap)
                    except Exception as _e:
                        ec2.error(f"Replay failed: {_e}")

                st.markdown("---")
                st.markdown("**▶ Consume events → derive alerts (CONSUMER side):**")

                consume_result = SmartAlertsConsumer.consume(since_event_id=0)
                if consume_result["status"] != "OK":
                    st.error(f"Consumer failed: {consume_result.get('reason')}")
                elif consume_result["consumed_count"] == 0:
                    st.caption(
                        "No events on bus yet. Emit a test event above to see "
                        "the consumer derive a customer alert."
                    )
                else:
                    st.caption(
                        f"Consumed {consume_result['consumed_count']} event(s). "
                        f"Pattern: `{consume_result['pattern']}`, "
                        f"payload_version: `{consume_result['payload_version']}`. "
                        f"Newest event_id: {consume_result['new_max_event_id']}."
                    )

                    tier_emoji = {
                        "URGENT": "🚨",
                        "HIGH": "⚠️",
                        "INFO": "ℹ️",
                    }
                    # Show newest first (reverse chronological)
                    for alert in reversed(consume_result["alerts"]):
                        emoji = tier_emoji.get(alert["tier"], "•")
                        st.markdown(
                            f"**{emoji} [{alert['tier']}] {alert['headline']}** "
                            f"(event {alert['source_event_id']})"
                        )
                        st.caption(
                            f"*Delivery:* {' + '.join(alert['delivery_channels'])} "
                            f"· *Recipients:* {alert['estimated_recipients']:,} "
                            f"· *Affected:* {alert['affected_channel']} @ "
                            f"{alert['affected_location']}"
                        )
                        st.write(alert["body"])
                        st.markdown("")  # spacer

                st.info(
                    "💡 **L14 chain visible end-to-end.** v8.4 built the "
                    "engine + closed the loop; v8.5 surfaces producer + "
                    "consumer here. Loops are now **15/15 = 100%** — "
                    "every designed feedback loop is functional."
                )

            # ── v8.26 surfaces (closes UI for v8.23 dedup + v8.25 alert history) ──
            st.markdown("---")
            st.markdown("##### v8.23 + v8.25 observability — event-bus dedup & alert history")
            st.caption(
                "Per v8.23 + v8.25 + v8.6 retrospective acks #8 + #11: "
                "event-bus dedup prevents duplicate publishes; alert history "
                "persists customer-facing alerts across restarts."
            )

            # v8.23 dedup stats
            try:
                from utils.event_bus import get_dedup_stats as _bus_dedup_stats
                ds = _bus_dedup_stats()
                if ds["total_publish_calls"] > 0:
                    with st.expander(
                        f"🔂 Event-bus dedup stats (v8.23) — "
                        f"{ds['total_publish_calls']} publishes, "
                        f"{ds['dedup_hits']} dedup hits "
                        f"({ds.get('dedup_hit_rate_pct', '—')}%)",
                        expanded=False,
                    ):
                        st.caption(
                            "Per v8.23 + v8.6 ack #8: producers can pass "
                            "`dedup_key` to publish() for idempotent event "
                            "publishing. High dedup hit rate = retries / "
                            "page reloads being correctly de-duplicated."
                        )
                        if ds.get("per_topic"):
                            ds_rows = [
                                {
                                    "Topic": tp,
                                    "Publishes": s["total_publish_calls"],
                                    "Dedup hits": s["dedup_hits"],
                                    "Unique": s["unique_published"],
                                    "Hit rate %": (f"{s['dedup_hit_rate_pct']}%"
                                                   if s["dedup_hit_rate_pct"] is not None
                                                   else "—"),
                                }
                                for tp, s in sorted(ds["per_topic"].items())
                            ]
                            st.dataframe(pd.DataFrame(ds_rows),
                                         use_container_width=True,
                                         hide_index=True)
            except Exception:
                pass

            # v8.25 alert history
            try:
                from utils.smart_alerts import (
                    get_alert_history as _alert_hist,
                    get_alert_history_stats as _alert_stats,
                    acknowledge_alert as _alert_ack,
                )
                ah_stats = _alert_stats()
                if ah_stats["total"] > 0:
                    with st.expander(
                        f"🔔 Customer alert history (v8.25) — "
                        f"{ah_stats['total']} alerts "
                        f"({ah_stats['unacknowledged']} unacked, "
                        f"ack rate {ah_stats.get('acknowledgement_rate_pct') or 0}%)",
                        expanded=ah_stats["unacknowledged"] > 0,
                    ):
                        st.caption(
                            "Per v8.25 + v8.6 ack #11: customer-facing alerts "
                            "(URGENT/HIGH/INFO tiers) are persisted with "
                            "acknowledgement tracking. Survives process restart."
                        )
                        by_tier = ah_stats["by_tier"]
                        sc_a, sc_b, sc_c = st.columns(3)
                        sc_a.metric("URGENT", by_tier.get("URGENT", 0))
                        sc_b.metric("HIGH", by_tier.get("HIGH", 0))
                        sc_c.metric("INFO", by_tier.get("INFO", 0))

                        # Show unacked first (most actionable)
                        unacked = _alert_hist(limit=10, only_unacknowledged=True)
                        if unacked:
                            st.markdown("**Unacknowledged alerts (most recent first):**")
                            for a in unacked:
                                tier_emoji = {"URGENT": "🚨",
                                               "HIGH": "⚠️",
                                               "INFO": "ℹ️"}.get(a.get("tier"), "•")
                                cols = st.columns([4, 1])
                                with cols[0]:
                                    st.markdown(
                                        f"{tier_emoji} **{a.get('headline', '?')}** "
                                        f"`{a.get('alert_id', '?')}` · "
                                        f"created {a.get('created_at_iso', '')[:19]}"
                                    )
                                with cols[1]:
                                    if st.button(
                                        "✓ Ack",
                                        key=f"ack_{a.get('alert_id', '?')}",
                                        use_container_width=True,
                                    ):
                                        if _alert_ack(
                                            a.get("alert_id", ""),
                                            acked_by="systems_view_operator",
                                        ):
                                            st.success(
                                                f"Acknowledged {a.get('alert_id')}")
                                            st.rerun()
                        else:
                            st.success("✓ All alerts acknowledged.")
            except Exception:
                pass

            # v8.26 i18n scaffold — partial close of v8.6 ack #12
            with st.expander(
                "🌐 i18n scaffolding (v8.26 — partial close of ack #12)",
                expanded=False,
            ):
                st.caption(
                    "Per v8.6 retrospective ack #12: alert messages should "
                    "support multiple languages for a multilingual deployment "
                    "(English / French / Swahili are common in East Africa). "
                    "v8.26 ships the SCAFFOLD (translation-string loading + "
                    "language-detection helpers); full translations themselves "
                    "are operational work that lives outside the codebase."
                )
                try:
                    from utils.smart_alerts_i18n import (
                        get_supported_locales,
                        get_translation_keys,
                    )
                    locales = get_supported_locales()
                    keys = get_translation_keys()
                    cs1, cs2 = st.columns(2)
                    cs1.metric("Supported locales", len(locales))
                    cs2.metric("Translation keys", len(keys))
                    st.markdown(
                        f"**Locales scaffolded**: {', '.join(locales)}"
                    )
                    st.markdown(
                        f"**Keys scaffolded** ({len(keys)}): "
                        f"`{'`, `'.join(keys[:5])}`"
                        + (f" + {len(keys)-5} more"
                           if len(keys) > 5 else "")
                    )
                    st.info(
                        "**Honest scope**: only English currently has "
                        "complete translations. French + Swahili are "
                        "scaffolded with English fallback strings; full "
                        "translations require a native-speaker review pass "
                        "(operational work, not code work)."
                    )
                except Exception as _e:
                    st.warning(f"i18n module not available: {type(_e).__name__}")


    # ════════════════════════════════════════════════════════════════
    # TAB 4 — Hard Invariants
    # ════════════════════════════════════════════════════════════════
    with tabs[3]:
        st.markdown("### Hard Non-Linear Constraints")
        st.caption(
            "Meadows' *leverage point #5: rules of the system*. Banking "
            "has hard constraints that cannot be violated. The registry in "
            "`utils/system_invariants.py` is the single source of truth — "
            "engines should read from here rather than hard-code values "
            "(migration is incremental)."
        )

        # Severity counts
        sev_counts = invariant_count_by_severity()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total invariants", len(SYSTEM_INVARIANTS))
        c2.metric("CRITICAL severity", sev_counts.get("CRITICAL", 0),
                    delta_color="inverse")
        c3.metric("HIGH severity", sev_counts.get("HIGH", 0),
                    delta_color="inverse")
        c4.metric("MEDIUM severity", sev_counts.get("MEDIUM", 0))

        st.markdown("### All 8 registered invariants")
        inv_rows = []
        for inv in list_invariants():
            sev_emoji = {
                "CRITICAL": "🚨",
                "HIGH": "⚠",
                "MEDIUM": "🟡",
                "LOW": "🟢",
            }.get(inv.breach_severity, "❓")
            inv_rows.append({
                "ID": inv.invariant_id,
                "Name": inv.name,
                "Threshold": f"{inv.threshold}{inv.threshold_unit[0] if inv.threshold_unit == 'percent' else (' ' + inv.threshold_unit)}".replace(
                    "p", "%") if inv.threshold_unit == "percent" else f"{inv.threshold} {inv.threshold_unit}",
                "Direction": inv.direction,
                "Source": inv.source,
                "Severity": f"{sev_emoji} {inv.breach_severity}",
            })
        st.dataframe(pd.DataFrame(inv_rows),
                      use_container_width=True, hide_index=True)

        st.markdown("### Invariant detail")
        selected_inv_id = st.selectbox(
            "Inspect an invariant",
            options=list(SYSTEM_INVARIANTS.keys()),
            format_func=lambda iid: (f"{iid} — {SYSTEM_INVARIANTS[iid].name}"),
            key="systems_view_invariant_select",
        )

        if selected_inv_id:
            inv = SYSTEM_INVARIANTS[selected_inv_id]
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**{inv.name}**")
                st.markdown(f"- **Threshold**: `{inv.threshold} {inv.threshold_unit}`")
                st.markdown(f"- **Direction**: must be `{inv.direction}` than threshold")
                st.markdown(f"- **Source**: {inv.source}")
                st.markdown(f"- **Citation**: _{inv.citation}_")
                st.markdown(f"- **Severity if breached**: `{inv.breach_severity}`")
            with c2:
                st.markdown("**Affected contexts:**")
                for ctx in inv.affected_contexts:
                    st.markdown(f"- {ctx}")
                if inv.affected_engines:
                    st.markdown("**Affected engines:**")
                    for eng in inv.affected_engines:
                        st.markdown(f"- `{eng}`")

            st.markdown("**Action if breached:**")
            st.warning(inv.breach_action)

            if inv.notes:
                st.info(f"**Notes:** {inv.notes}")

        st.markdown("### Migration progress (engines reading from registry)")
        st.markdown(
            "v7.0 is the first batch with this registry. Engine migration "
            "is incremental — engines that hard-code thresholds today "
            "continue to work; future batches replace the hard-coded "
            "value with `get_threshold(invariant_id)`. **Migrated as of "
            "v7.0:**\n"
            "- ✅ `utils.stress_testing` — `CBK_TOTAL_CAR_MIN_PCT_LOCAL` "
            "now sourced from `system_invariants.get_threshold('CBK_TOTAL_CAR_MIN')` "
            "(falls back to hard-coded 14.5 if registry import fails — "
            "defensive)\n\n"
            "**Pending migration in v7.x:**\n"
            "- `utils.capital_adequacy` — same CAR floor in 3 places\n"
            "- `utils.liquidity_lcr_nsfr` — LCR + NSFR thresholds\n"
            "- `utils.credit_monitoring` — single obligor limit"
        )


    # ════════════════════════════════════════════════════════════════
    # TAB 5 — Boundary Awareness
    # ════════════════════════════════════════════════════════════════
    with tabs[4]:
        st.markdown("### A2Z System Boundaries")
        st.caption(
            "Meadows: *the first step to understanding a system is to "
            "decide what to include and what to exclude*. A2Z is the "
            "**system of intelligence** between systems of record (FLEXCUBE) "
            "and systems of engagement (mobile/agent banking)."
        )

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### ✅ A2Z IS responsible for")
            st.markdown(
                "- ✅ **Strategy cascade** (board → teller, with feedback)\n"
                "- ✅ **Performance measurement** (BSC, KPIs, calibrated ratings)\n"
                "- ✅ **Profitability intelligence** (customer / RM / branch P&L)\n"
                "- ✅ **Risk aggregation** (credit, market, operational, "
                "liquidity, compliance, COSO)\n"
                "- ✅ **Compliance tracking** (regulatory obligations, "
                "audit trail, CBK returns)\n"
                "- ✅ **Decision support** (what-if, recommendations, "
                "alerts, nudges)\n"
                "- ✅ **Process orchestration** (cross-departmental workflows)\n"
                "- ✅ **Strategic intelligence** (environment scanning, "
                "peer comparison, scenarios)"
            )

        with c2:
            st.markdown("### ❌ A2Z is NOT responsible for")
            st.markdown(
                "- ❌ **Core banking transactions** — Oracle FLEXCUBE 12 "
                "is system of record\n"
                "- ❌ **General ledger postings** — bank's ERP is system "
                "of record (A2Z calculates; ERP posts)\n"
                "- ❌ **Customer-facing mobile/agent banking** — separate "
                "channels are systems of engagement\n"
                "- ❌ **Real-time payment switching** — KEPSS, RTGS, SWIFT "
                "are systems of execution\n"
                "- ❌ **Physical document storage** — bank's DMS is system "
                "of record (A2Z indexes; DMS stores)\n"
                "- ❌ **Identity & access management** — corporate IDP "
                "(Active Directory / Okta) is authoritative"
            )

        st.warning(
            "⚠ **Charter §4 enforcement**: any feature that expands these "
            "boundaries requires explicit charter amendment, not a batch-"
            "level decision. If a batch proposal looks like it crosses "
            "the line into FLEXCUBE / channels / IDP / DMS / GL territory, "
            "stop and amend the charter first."
        )


    # ════════════════════════════════════════════════════════════════
    # TAB 6 — Bounded Contexts
    # ════════════════════════════════════════════════════════════════
    with tabs[5]:
        st.markdown("### The 13 Bounded Contexts")
        st.caption(
            "Following Eric Evans' *Domain-Driven Design*: each context "
            "owns its data model, vocabulary, and invariants. Cross-context "
            "integration uses the explicit patterns in Charter §7."
        )

        contexts_df = pd.DataFrame([
            {"#": 1, "Context": "Strategy & Cascade",
                "Engines (representative)":
                    "bsc_engine, target_cascade, kpi_library",
                "Owns": "Goals, weights, calibration"},
            {"#": 2, "Context": "Performance Measurement",
                "Engines (representative)":
                    "actuals_engine, predictive_performance, calibration",
                "Owns": "Scores, ratings, distribution"},
            {"#": 3, "Context": "HR Intelligence",
                "Engines (representative)":
                    "compensation_equity, employee_engagement, "
                    "workforce_planning, coaching",
                "Owns": "Pay equity, engagement, flight risk"},
            {"#": 4, "Context": "Customer Intelligence",
                "Engines (representative)":
                    "customer_segmentation, customer_lifetime_value, "
                    "customer_value, churn_prediction",
                "Owns": "RFM, CLV, segments, churn"},
            {"#": 5, "Context": "Profitability",
                "Engines (representative)":
                    "customer_profitability, rm_profitability, "
                    "profitability_hierarchy",
                "Owns": "Customer / RM / segment P&L"},
            {"#": 6, "Context": "Credit Risk",
                "Engines (representative)":
                    "credit_monitoring, ifrs9_staging, behavioral_pd, "
                    "expected_credit_loss",
                "Owns": "PD, LGD, EAD, ECL, staging"},
            {"#": 7, "Context": "Operational Risk",
                "Engines (representative)":
                    "operational_risk, internal_controls, rcsa",
                "Owns": "Risk events, COSO, deficiencies"},
            {"#": 8, "Context": "Compliance / AML",
                "Engines (representative)":
                    "kyc_aml_risk, transaction_monitoring, cbk_returns",
                "Owns": "KYC bands, alerts, regulatory filings"},
            {"#": 9, "Context": "Daily-Risk Trifecta",
                "Engines (representative)":
                    "irrbb, liquidity_lcr_nsfr, stress_testing",
                "Owns": "Rate risk, liquidity ratios, scenario impact"},
            {"#": 10, "Context": "Treasury & ALM",
                "Engines (representative)":
                    "treasury, alm, capital_adequacy",
                "Owns": "Asset-liability gaps, capital ratios"},
            {"#": 11, "Context": "Branch & Channels",
                "Engines (representative)":
                    "branch_log, channels_cost, channels_reliability, "
                    "channels_income",
                "Owns": "Branch performance, channel economics"},
            {"#": 12, "Context": "Cross-sell & NBA",
                "Engines (representative)":
                    "cross_sell, allocation_optimizer",
                "Owns": "Next-best-action, RM-customer assignments"},
            {"#": 13, "Context": "Smart Alerts & Nudges",
                "Engines (representative)":
                    "smart_alerts, notifications, nudge_engine",
                "Owns": "Proactive workflows"},
        ])
        st.dataframe(contexts_df, use_container_width=True, hide_index=True)

        st.markdown("### Integration patterns (Charter §7)")
        st.markdown(
            "Cross-context integration uses one of six explicit patterns:\n\n"
            "- **Published Language** (preferred) — context exposes a "
            "stable structure (e.g. `KycRiskAssessment`); consumers depend "
            "on the public interface, not internals\n"
            "- **Customer/Supplier** — downstream and upstream negotiate "
            "the contract together (BSC needs profitability data shaped "
            "a particular way)\n"
            "- **Anti-Corruption Layer** — explicit translation layer "
            "between incompatible models (used at A2Z ↔ FLEXCUBE boundary)\n"
            "- **Open Host Service** — context exposes a public API for "
            "many consumers (`bsc_engine.submit()`)\n"
            "- **Conformist** — downstream uses upstream model as-is "
            "(low-stakes only; risky for core integrations)\n"
            "- **Shared Kernel** — two contexts share a small core "
            "(`core.py` audit logging); use sparingly"
        )

        st.info(
            "💡 **Convention from v7.0**: every cross-context import "
            "should declare its pattern in a comment. Existing imports "
            "are documented retroactively in `utils/system_flows.py`."
        )


    # ════════════════════════════════════════════════════════════════
    # TAB 7 — Health Composites (v7.6)
    # ════════════════════════════════════════════════════════════════
    with tabs[6]:
        st.markdown("### Health Composites — single-score health views")
        st.caption(
            "v7.6 surfacing of `composite_scores` module. Each composite "
            "combines multiple signals into one 0-100 score with HEALTHY / "
            "MODERATE / LOW severity bands. Composites are caller-driven — "
            "this view shows them computed against currently-wired stocks "
            "where possible, or honestly as 'needs caller input' otherwise."
        )

        from utils.composite_scores import (workforce_health_composite,
            customer_value_composite, rcsa_health_composite,
            aml_health_composite, ALL_COMPOSITES)
        # v10.351 — removed `from utils.system_stocks import get_stock_snapshot`
        # here. The same import exists at module top (line 40); the local
        # version shadowed it and made `get_stock_snapshot` a local variable
        # in the entire 2,300-line render_systems_view function, which
        # triggered UnboundLocalError on line 444 where the function uses it
        # BEFORE this local-import line was reached.

        # Counts header
        c1, c2, c3 = st.columns(3)
        c1.metric("Composite functions", len(ALL_COMPOSITES),
                  help="Available composites in `utils.composite_scores`. "
                       "Added in v6.0 (3) and v7.5 (1).")
        c2.metric("Wired stocks consumed", "1 of 4 composites",
                  help="aml_health composes the customer_base.by_kyc_risk_band_count "
                       "stock directly. Other composites take caller-supplied inputs.")
        c3.metric("Coverage status", "Surfaced ⭐",
                  help="v7.6 brings composites into the systems-view page. "
                       "Production deployment will wire each composite to "
                       "specific engines on per-domain pages.")

        st.markdown("### Composite computations (live where stocks support it)")

        composite_tabs = st.tabs([
            "🧠 AML Health",
            "🏢 RCSA Health",
            "👥 Workforce Health",
            "🎯 Customer Value",
            "🤖 ML Models",
            "🔌 Integration",
        ])

        # ────────── AML Health (composes customer_base + sample alert summary) ──────────
        with composite_tabs[0]:
            st.markdown("**AML Health (v7.5)** — composes 4 signals from "
                        "Customer Intelligence + Compliance/AML contexts.")
            st.caption(
                "Reads `customer_base.by_kyc_risk_band_count` directly from "
                "the systems layer. Other inputs (alert summary, SAR rate, "
                "velocity) are illustrative — production deployment will pull "
                "from `transaction_monitoring.alert_summary()` and bank metrics."
            )

            cb_snap = get_stock_snapshot("customer_base")
            kyc_dist = cb_snap.get("by_kyc_risk_band_count", {})

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Inputs:**")
                st.markdown(f"- KYC distribution: {kyc_dist} (live from `customer_base`)")
                st.markdown("- Alert disposition: illustrative healthy book")
                st.markdown("- SAR conversion: 10% (ideal)")
                st.markdown("- Txn velocity change: ±2% (stable)")

            with c2:
                r = aml_health_composite(
                    kyc_band_distribution=kyc_dist,
                    alert_summary={"total_alerts": 100,
                                   "by_status": {"OPEN": 8, "INVESTIGATING": 5,
                                                 "SAR_FILED": 10, "DISMISSED": 77}},
                    sar_conversion_pct=10.0,
                    txn_velocity_change_pct=2.0,
                )
                score = r.get("score")
                severity = r.get("severity")
                st.metric("AML Health score", f"{score:.1f}/100" if score else "—",
                          severity)
                sev_color = {"HEALTHY": "✅", "MODERATE": "🟡",
                             "LOW": "🚨", "UNKNOWN": "⚠"}.get(severity, "")
                st.markdown(f"**{sev_color} {severity}**")

            if r.get("components"):
                st.markdown("**Component scores:**")
                for k, v in r["components"].items():
                    st.markdown(f"- `{k}`: {v:.1f}")

            with st.expander("Weights used (caller can override)"):
                for k, v in r.get("weights_used", {}).items():
                    st.markdown(f"- `{k}`: {v}")

            audit_log("SYSTEMS_VIEW_OPENED", uname,
                      f"v7.6 composite surfacing: AML health = {score} ({severity})")

        # ────────── RCSA Health ──────────
        with composite_tabs[1]:
            st.markdown("**RCSA Health (v6.0)** — COSO + control effectiveness "
                        "+ deficiency severity.")
            st.caption(
                "Production deployment surfaces this from the RCSA page "
                "(`pages/54_rcsa.py`). Below illustrates a healthy bank profile."
            )

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Inputs (illustrative healthy):**")
                st.markdown("- COSO overall score: 4.2 / 5.0")
                st.markdown("- Control effectiveness: 88%")
                st.markdown("- Material weaknesses: 0")
                st.markdown("- Significant deficiencies: 2")
                st.markdown("- Other deficiencies: 8")

            with c2:
                r = rcsa_health_composite(
                    coso_overall_score=4.2,
                    control_effectiveness_pct=88.0,
                    material_weakness_count=0,
                    significant_deficiency_count=2,
                    deficiency_count=8,
                )
                score = r.get("score")
                severity = r.get("severity")
                st.metric("RCSA Health score", f"{score:.1f}/100" if score else "—",
                          severity)
                sev_color = {"HEALTHY": "✅", "MODERATE": "🟡",
                             "LOW": "🚨", "UNKNOWN": "⚠"}.get(severity, "")
                st.markdown(f"**{sev_color} {severity}**")

            if r.get("components"):
                st.markdown("**Component scores:**")
                for k, v in r["components"].items():
                    st.markdown(f"- `{k}`: {v:.1f}")

        # ────────── Workforce Health ──────────
        with composite_tabs[2]:
            st.markdown("**Workforce Health (v6.0)** — engagement + eNPS + "
                        "weakest driver + flight risk.")
            st.caption(
                "Production deployment surfaces this from the People page "
                "(`pages/2_people.py`). Below illustrates a healthy bank profile."
            )

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Inputs (illustrative healthy):**")
                st.markdown("- Engagement score: 78 / 100")
                st.markdown("- eNPS: 35")
                st.markdown("- Weakest driver score: 65")
                st.markdown("- Flight risk HIGH %: 8%")

            with c2:
                r = workforce_health_composite(
                    engagement_score=78.0,
                    enps=35.0,
                    weakest_driver_score=65.0,
                    flight_risk_high_pct=8.0,
                )
                score = r.get("score")
                severity = r.get("severity")
                st.metric("Workforce Health score",
                          f"{score:.1f}/100" if score else "—",
                          severity)
                sev_color = {"HEALTHY": "✅", "MODERATE": "🟡",
                             "LOW": "🚨", "UNKNOWN": "⚠"}.get(severity, "")
                st.markdown(f"**{sev_color} {severity}**")

            if r.get("components"):
                st.markdown("**Component scores:**")
                for k, v in r["components"].items():
                    st.markdown(f"- `{k}`: {v:.1f}")

        # ────────── Customer Value ──────────
        with composite_tabs[3]:
            st.markdown("**Customer Value (v6.0)** — RFM segment + CLV + "
                        "Customer Value tier.")
            st.caption(
                "Production deployment surfaces this from the Customer 360 "
                "page (`pages/34_customer360.py`). Below illustrates a high-value "
                "customer profile."
            )

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Inputs (illustrative high-value customer):**")
                st.markdown("- RFM segment: CHAMPIONS")
                st.markdown("- CLV (KES): 850,000")
                st.markdown("- Value tier: PLATINUM")

            with c2:
                r = customer_value_composite(
                    rfm_segment="CHAMPIONS",
                    clv_kes=850000.0,
                    customer_value_tier="PLATINUM",
                )
                score = r.get("score")
                severity = r.get("severity")
                st.metric("Customer Value score",
                          f"{score:.1f}/100" if score else "—",
                          severity)
                sev_color = {"HEALTHY": "✅", "MODERATE": "🟡",
                             "LOW": "🚨", "UNKNOWN": "⚠"}.get(severity, "")
                st.markdown(f"**{sev_color} {severity}**")

            if r.get("components"):
                st.markdown("**Component scores:**")
                for k, v in r["components"].items():
                    st.markdown(f"- `{k}`: {v:.1f}")

        st.divider()
        st.info(
            "💡 **Charter §13 alignment**: composites are caller-driven by "
            "design. They give a single-score view of multi-signal domains "
            "without prescribing how to compute them. Each batch that surfaces "
            "a composite on a per-domain page (page 2 People for workforce, "
            "page 54 RCSA for control health, etc.) is a Charter §13 "
            "advancement — even though composites themselves don't read from "
            "the invariants registry or affect stock wiring."
        )



        # ──────────────────────────────────────────────────────────────────
        # composite_tabs[4] — 🤖 ML Models (absorbed from
        # 98_ml_governance_arc_cockpit.py in v10.212).
        # 5 mlops engines (ENH-281..285) + integration registry (G141)
        # presented as 6 nested sub-sub-tabs. Engines diagnostic — surface
        # deltas, never auto-promote/deprecate/retrain/publish.
        # ──────────────────────────────────────────────────────────────────
        with composite_tabs[4]:
            from datetime import datetime as _dt_ml, timezone as _tz_ml
            from decimal import Decimal as _D_ml

            try:
                from utils.mlops_model_registry import (
                    MLOpsModelRegistryEngine, ModelRegistryEntry,
                    ModelStatus, PromotionGate, GateType, GateComparison,
                    PromotionReadinessOutcome)
                from utils.mlops_adjudication_log import (
                    MLOpsAdjudicationLogEngine, AdjudicationRecord,
                    AgreementStatus, OverrideReason, TimeWindow,
                    TimeWindowUnit, RecommendationClassTaxonomy)
                from utils.mlops_retraining_scheduler import (
                    MLOpsRetrainingSchedulerEngine, FreshnessPolicy,
                    OverrideThresholds, DriftThresholds,
                    RetrainingPolicy, RetrainingOutcome)
                from utils.mlops_ab_harness import (
                    MLOpsABHarnessEngine, PredictionEvent, PredictionRole,
                    ABThresholds, ABReportSeverity)
                from utils.mlops_model_card_composer import (
                    MLOpsModelCardComposerEngine, ModelCardNarrative,
                    ProductionPerformanceSnapshot,
                    CardCompletenessRequirements)
                from utils.standards_registry import (
                    MLOPS_INTEGRATION_REGISTRY)
                _ARC_ML_AVAILABLE = True
            except ImportError as _ie:
                st.error(f"ML Governance arc engines unavailable: {_ie}")
                _ARC_ML_AVAILABLE = False

            if _ARC_ML_AVAILABLE:
                st.caption(
                    "v10.212 absorbed from 98_ml_governance_arc_cockpit.py. "
                    "Operational deployment lifecycle for ML models on the "
                    "platform. All 5 engines diagnostic; operator decides "
                    "every transition.")

                arc_tabs = st.tabs([
                    "🗂️ Registry (ENH-281)",
                    "✋ Adjudication (ENH-282)",
                    "🔄 Retraining (ENH-283)",
                    "🆎 A/B Harness (ENH-284)",
                    "📋 Model Cards (ENH-285)",
                    "🔌 Cross-Platform Wiring (G141)",
                ])

                with arc_tabs[0]:
                    st.markdown("### Model Registry (ENH-281)")
                    st.caption(
                        "Operational deployment lifecycle tracking. Engine "
                        "DIAGNOSTIC ONLY — never persists, never promotes, "
                        "never deploys.")
                    registry_engine = MLOpsModelRegistryEngine()

                    st.markdown(
                        "**Demo: validate promotion readiness with three "
                        "gate types**")
                    active_entry = ModelRegistryEntry(
                        model_id="doc_classifier", version="1.0.0",
                        artifact_hash="a" * 64,
                        training_data_hash="b" * 64,
                        framework="sklearn", framework_version="1.5.1",
                        metrics={"accuracy": Decimal("0.85")},
                        owner="ml-team@bank",
                        status=ModelStatus.ACTIVE,
                        created_by="trainer", created_at_iso="2026-04-01T00:00:00Z")
                    candidate = ModelRegistryEntry(
                        model_id="doc_classifier", version="2.0.0",
                        artifact_hash="c" * 64,
                        training_data_hash="d" * 64,
                        framework="sklearn", framework_version="1.5.1",
                        metrics={"accuracy": Decimal("0.91")},
                        owner="ml-team@bank",
                        status=ModelStatus.PROPOSED,
                        created_by="trainer", created_at_iso="2026-05-01T00:00:00Z")
                    gates = (
                        PromotionGate(
                            gate_id="MIN", gate_type=GateType.MINIMUM_METRIC,
                            description="Accuracy ≥ 0.80",
                            metric_name="accuracy",
                            threshold=Decimal("0.80"),
                            comparison=GateComparison.GTE),
                        PromotionGate(
                            gate_id="REG", gate_type=GateType.NON_REGRESSION,
                            description="No regression vs active",
                            metric_name="accuracy",
                            regression_tolerance=Decimal("0.01"),
                            comparison=GateComparison.GTE),
                        PromotionGate(
                            gate_id="META",
                            gate_type=GateType.METADATA_REQUIRED,
                            description="Owner present",
                            required_field="owner"),
                    )
                    if st.button("Run promotion readiness check",
                                 key="reg_check"):
                        assessment = (
                            registry_engine.validate_promotion_readiness(
                                candidate, active_entry, gates))
                        if assessment.outcome == PromotionReadinessOutcome.READY:
                            st.success(
                                f"✓ Outcome: {assessment.outcome.value}")
                        elif assessment.outcome == (
                            PromotionReadinessOutcome.BLOCKED
                        ):
                            st.error(
                                f"✗ Outcome: {assessment.outcome.value}")
                        else:
                            st.warning(
                                f"⚠ Outcome: {assessment.outcome.value}")

                        for f in assessment.findings:
                            st.markdown(
                                f"- **{f.gate_id}** ({f.gate_type.value}) "
                                f"— {f.severity.value}: {f.description}  \n"
                                f"  *expected:* {f.expected}  \n"
                                f"  *observed:* {f.observed}")
                        audit_log(
                        "ml_governance_promotion_check",
                        uname,
                        "target=" + str(f"{candidate.model_id}@{candidate.version}") + " " + "meta=" + str({"outcome": assessment.outcome.value}))

                with arc_tabs[1]:
                    st.markdown("### Adjudication Log (ENH-282)")
                    st.caption(
                        "Operator-override capture. Engine surfaces signals; "
                        "bias DECISION belongs to model_governance arc at G124.")
                    adj_engine = MLOpsAdjudicationLogEngine()

                    st.markdown(
                        "**Demo: compute override rate over a 24-hour window**")
                    sample_records = (
                        AdjudicationRecord(
                            event_id="E1", model_id="doc_classifier",
                            model_version="1.0", recommendation="APPROVE",
                            recommendation_class="APPROVE",
                            operator_decision="APPROVE",
                            agreement_status=AgreementStatus.ACCEPTED,
                            operator_id="alice",
                            decision_at_iso="2026-05-01T10:00:00Z",
                            override_reason=None,
                            override_reason_text="",
                            input_features_hash=None,
                            retraining_eligible=False, notes=""),
                        AdjudicationRecord(
                            event_id="E2", model_id="doc_classifier",
                            model_version="1.0", recommendation="APPROVE",
                            recommendation_class="APPROVE",
                            operator_decision="REJECT",
                            agreement_status=AgreementStatus.OVERRIDDEN,
                            operator_id="alice",
                            decision_at_iso="2026-05-01T11:00:00Z",
                            override_reason=OverrideReason.DOMAIN_KNOWLEDGE,
                            override_reason_text="watchlist match",
                            input_features_hash="a" * 64,
                            retraining_eligible=True, notes=""),
                        AdjudicationRecord(
                            event_id="E3", model_id="doc_classifier",
                            model_version="1.0", recommendation="APPROVE",
                            recommendation_class="APPROVE",
                            operator_decision="REJECT",
                            agreement_status=AgreementStatus.OVERRIDDEN,
                            operator_id="bob",
                            decision_at_iso="2026-05-01T12:00:00Z",
                            override_reason=OverrideReason.POLICY_OVERRIDE,
                            override_reason_text="",
                            input_features_hash="b" * 64,
                            retraining_eligible=True, notes=""),
                    )
                    window = TimeWindow(
                        duration=24, unit=TimeWindowUnit.HOURS,
                        end_iso="2026-05-02T00:00:00Z")

                    if st.button("Compute override rate",
                                 key="adj_rate"):
                        m = adj_engine.compute_override_rate(
                            sample_records, "doc_classifier", window)
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Total decided",
                                    m.count_accepted + m.count_overridden)
                        col2.metric("Overridden", m.count_overridden)
                        col3.metric(
                            "Override rate",
                            f"{m.override_rate}" if m.override_rate
                            else "N/A")
                        st.caption(
                            "Per Rule 1, rate is None when no decided "
                            "records (PENDING + ESCALATED excluded from "
                            "denominator). Engine never decides 'rate "
                            "too high → trigger retraining' — that's "
                            "ENH-283 territory.")
                        audit_log(
                        "ml_governance_override_rate",
                        uname,
                        "target=" + str("doc_classifier") + " " + "meta=" + str({"rate": str(m.override_rate)}))

                with arc_tabs[2]:
                    st.markdown("### Retraining Scheduler (ENH-283)")
                    st.caption(
                        "Combines freshness + override + drift signals against "
                        "caller policy. Engine never auto-triggers retraining.")
                    retrain_engine = MLOpsRetrainingSchedulerEngine()

                    st.markdown(
                        "**Demo: combined retraining recommendation**")
                    fresh_policy = FreshnessPolicy(
                        warning_age_days=30, stale_age_days=90)
                    override_thresholds = OverrideThresholds(
                        warning_rate=Decimal("0.20"),
                        critical_rate=Decimal("0.40"))
                    drift_thresholds = DriftThresholds(
                        warning_value=Decimal("0.10"),
                        critical_value=Decimal("0.25"),
                        metric_name="PSI")

                    fresh = retrain_engine.evaluate_freshness(
                        model_id="doc_classifier",
                        model_version="1.0.0",
                        training_completed_at_iso="2026-04-15T00:00:00Z",
                        as_of_iso="2026-05-01T00:00:00Z",
                        policy=fresh_policy)
                    override_signal = retrain_engine.evaluate_override_signal(
                        model_id="doc_classifier",
                        current_rate=Decimal("0.08"),
                        thresholds=override_thresholds)
                    drift_signal = retrain_engine.evaluate_drift_signal(
                        model_id="doc_classifier",
                        current_value=Decimal("0.06"),
                        thresholds=drift_thresholds)

                    if st.button("Compute retraining recommendation",
                                 key="retrain_rec"):
                        rec = retrain_engine.compute_retraining_recommendation(
                            model_id="doc_classifier",
                            model_version="1.0.0",
                            freshness=fresh,
                            override_signal=override_signal,
                            drift_signal=drift_signal,
                            policy=RetrainingPolicy(
                                require_freshness=True,
                                require_override_signal=True,
                                require_drift_signal=True))
                        if rec.outcome == RetrainingOutcome.DUE:
                            st.error(f"Outcome: {rec.outcome.value}")
                        elif rec.outcome == RetrainingOutcome.SOON:
                            st.warning(f"Outcome: {rec.outcome.value}")
                        elif rec.outcome == RetrainingOutcome.NOT_YET:
                            st.success(f"Outcome: {rec.outcome.value}")
                        else:
                            st.info(f"Outcome: {rec.outcome.value}")
                        st.markdown(f"**Rationale:** {rec.rationale}")
                        col1, col2, col3 = st.columns(3)
                        col1.metric(
                            "Freshness", rec.freshness.severity.value)
                        col2.metric(
                            "Override",
                            rec.override_signal.severity.value)
                        col3.metric(
                            "Drift",
                            rec.drift_signal.severity.value)
                        audit_log(
                        "ml_governance_retraining_check",
                        uname,
                        "target=" + str("doc_classifier") + " " + "meta=" + str({"outcome": rec.outcome.value}))

                with arc_tabs[3]:
                    st.markdown("### A/B Comparison Harness (ENH-284)")
                    st.caption(
                        "Bridge from candidate registered (SHADOW) to ready for "
                        "promotion (ACTIVE). Engine never auto-promotes — "
                        "ENH-281 validate_promotion_readiness is the gate.")
                    ab_engine = MLOpsABHarnessEngine()

                    st.markdown(
                        "**Demo: 100 paired predictions with 95% agreement**")
                    events = []
                    for i in range(100):
                        events.append(PredictionEvent(
                            event_id=f"A{i}",
                            input_features_hash=f"h{i}",
                            model_id="doc_classifier",
                            model_version="1.0",
                            role=PredictionRole.ACTIVE,
                            predicted_class="APPROVE",
                            predicted_at_iso="2026-05-01T10:00:00Z",
                            latency_ms=Decimal("100")))
                        sclass = "REJECT" if i < 5 else "APPROVE"
                        events.append(PredictionEvent(
                            event_id=f"S{i}",
                            input_features_hash=f"h{i}",
                            model_id="doc_classifier",
                            model_version="2.0",
                            role=PredictionRole.SHADOW,
                            predicted_class=sclass,
                            predicted_at_iso="2026-05-01T10:00:00Z",
                            latency_ms=Decimal("105")))

                    if st.button("Run A/B comparison",
                                 key="ab_compare"):
                        report = ab_engine.build_ab_comparison_report(
                            events, "1.0", "2.0",
                            thresholds=ABThresholds(
                                minimum_paired_sample=50))
                        if report.composite_severity == (
                            ABReportSeverity.READY_TO_PROMOTE
                        ):
                            st.success(
                                f"Composite severity: "
                                f"{report.composite_severity.value}")
                        elif report.composite_severity == (
                            ABReportSeverity.NEEDS_REVIEW
                        ):
                            st.warning(
                                f"Composite severity: "
                                f"{report.composite_severity.value}")
                        elif report.composite_severity == (
                            ABReportSeverity.NOT_READY
                        ):
                            st.error(
                                f"Composite severity: "
                                f"{report.composite_severity.value}")
                        else:
                            st.info(
                                f"Composite severity: "
                                f"{report.composite_severity.value}")
                        st.markdown(f"**Rationale:** {report.rationale}")
                        col1, col2, col3 = st.columns(3)
                        col1.metric(
                            "Agreement rate",
                            f"{report.agreement.agreement_rate}")
                        col2.metric(
                            "Latency Δ (median, ms)",
                            f"{report.latency.median_delta_ms}")
                        col3.metric(
                            "Total paired",
                            report.agreement.total_paired)
                        audit_log(
                        "ml_governance_ab_compare",
                        uname,
                        "target=" + str("doc_classifier") + " " + "meta=" + str({
                                "severity": report.composite_severity.value}))

                with arc_tabs[4]:
                    st.markdown("### Model Card Composer (ENH-285)")
                    st.caption(
                        "Composes per-model documentation surfaces from every "
                        "other arc engine's output + caller-supplied narrative. "
                        "Source of truth: structured ModelCard. Markdown "
                        "rendering for human consumption.")
                    card_engine = MLOpsModelCardComposerEngine()

                    if st.button("Compose sample model card",
                                 key="card_compose"):
                        narrative = ModelCardNarrative(
                            intended_use=(
                                "Classify trade finance documents into "
                                "DISCREPANT vs CLEAN buckets"),
                            out_of_scope_use=(
                                "Not for credit decisions; advisory only"),
                            training_data_description=(
                                "12 months of FLEXCUBE document attachments "
                                "labeled by trade ops"),
                            evaluation_data_description=(
                                "Held-out 20% from same period, stratified"),
                            ethical_considerations=(
                                "Operator-in-the-loop required; "
                                "recommendations advisory"),
                            caveats_and_recommendations=(
                                "Quarterly retraining per ENH-283 freshness "
                                "policy"))
                        snapshot = ProductionPerformanceSnapshot(
                            snapshot_at_iso="2026-05-01T10:00:00Z",
                            override_rate_30d=Decimal("0.08"),
                            override_sample_size_30d=347,
                            drift_metric_name="PSI",
                            drift_metric_value=Decimal("0.06"),
                            last_retraining_outcome="NOT_YET",
                            last_retraining_rationale=(
                                "All signals OK"),
                            last_ab_severity="READY_TO_PROMOTE",
                            last_ab_against_version="2.0.0-shadow")
                        result = card_engine.compose_model_card(
                            model_id="doc_classifier",
                            model_version="1.0.0",
                            framework="sklearn",
                            framework_version="1.5.1",
                            owner="ml-team@bank",
                            artifact_hash="a" * 64,
                            training_data_hash="b" * 64,
                            operational_status="ACTIVE",
                            training_metrics={
                                "accuracy": Decimal("0.87"),
                                "f1": Decimal("0.85")},
                            narrative=narrative,
                            composed_at_iso=(
                                datetime.now(timezone.utc).isoformat()),
                            composed_by=uname,
                            training_completed_at_iso=(
                                "2026-04-15T00:00:00Z"),
                            production_snapshot=snapshot)
                        if result.outcome.value == "COMPOSED":
                            st.success(f"Outcome: {result.outcome.value}")
                            md = card_engine.serialize_card_to_markdown(
                                result.card)
                            with st.expander(
                                "Markdown preview", expanded=True):
                                st.markdown(md)
                        else:
                            st.error(f"Outcome: {result.outcome.value}")
                            for f in result.findings:
                                st.markdown(f"- {f}")
                        audit_log(
                        "ml_governance_card_compose",
                        uname,
                        "target=" + str("doc_classifier") + " " + "meta=" + str({"outcome": result.outcome.value}))

                with arc_tabs[5]:
                    st.markdown(
                        "### Cross-Platform Wiring Catalog (G141)")
                    st.caption(
                        "MLOPS_INTEGRATION_REGISTRY — the audit-side answer to "
                        "'apply this everywhere.' Per Rule 7, this is a "
                        "CATALOG, not coupling. The mlops_* engines never read "
                        "this registry; wiring lives in CALLER code paths.")

                    n_total = len(MLOPS_INTEGRATION_REGISTRY)
                    n_v10_76 = sum(
                        1 for e in MLOPS_INTEGRATION_REGISTRY
                        if e.uses_v10_76_hook_contract)
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Engines catalogued", n_total)
                    col2.metric("Use v10.76 hook", n_v10_76)
                    col3.metric(
                        "Registry-wired (planned)",
                        sum(1 for e in MLOPS_INTEGRATION_REGISTRY
                            if e.registry_wiring_planned))
                    col4.metric(
                        "Adjudication-wired (planned)",
                        sum(1 for e in MLOPS_INTEGRATION_REGISTRY
                            if e.adjudication_wiring_planned))

                    for entry in MLOPS_INTEGRATION_REGISTRY:
                        with st.expander(
                            f"**{entry.engine_module}** "
                            f"({entry.standard_id}) — "
                            f"v10.76={'✓' if entry.uses_v10_76_hook_contract else '—'}",
                            expanded=False):
                            col1, col2, col3 = st.columns(3)
                            col1.metric(
                                "Registry wired",
                                "✓" if entry.registry_wiring_planned else "—")
                            col2.metric(
                                "Adjudication wired",
                                "✓" if entry.adjudication_wiring_planned
                                else "—")
                            col3.metric(
                                "Scheduler wired",
                                "✓" if entry.scheduler_wiring_planned else "—")
                            st.markdown(f"**Notes:** {entry.notes}")

                # ML Gov footer audit
                try:
                    audit_log(
                        action="ml_governance_arc_engines.view",
                        username=ud.get("username", "anonymous"),
                        detail=f"viewed_at={_dt_ml.now(_tz_ml.utc).isoformat()}",
                        module="systems_view")
                except Exception:
                    pass


        # ──────────────────────────────────────────────────────────────────
        # composite_tabs[5] — 🔌 Integration (absorbed from
        # 99_integration_cockpit.py in v10.212).
        # Integration Layer coverage, rules, preview actuals, resolution
        # metrics, period runs, and debug. Surfaces the G143 KPI source →
        # aggregator coverage health composite. Diagnostic — outputs feed
        # the Integration Layer at utils/integration/ but do not commit
        # writes from this UI.
        # ──────────────────────────────────────────────────────────────────
        with composite_tabs[5]:
            from datetime import datetime as _dt_int, timezone as _tz_int

            # The integration cockpit relies on helper functions defined at
            # module level. Re-import them lazily here.
            try:
                from utils.integration import (
                    rules as _int_rules,
                    resolver as _int_resolver,
                    runner as _int_runner,
                )
                _ARC_INT_AVAILABLE = True
            except ImportError as _ie:
                st.error(f"Integration arc components unavailable: {_ie}")
                _ARC_INT_AVAILABLE = False

            if _ARC_INT_AVAILABLE:
                st.caption(
                    "v10.212 absorbed from 99_integration_cockpit.py. "
                    "Integration Layer health view: coverage, rules, "
                    "preview actuals, resolution metrics, period runs, "
                    "debug. Diagnostic only — writes happen via the "
                    "Integration Layer scripts, not from this UI.")

                arc_tabs = st.tabs([
                    "📊 Coverage",
                    "📋 Rules",
                    "🔢 Preview Actuals",
                    "🔎 Resolution Metrics",
                    "▶️ Run Period",
                    "🐛 Debug",
                ])

                with arc_tabs[0]:
                    st.caption(
                        "Equivalent to GET `/api/integration/coverage`. "
                        "Refreshed live each visit.")
                    g143 = _compute_g143_summary()
                    sp = g143.get("strict_preview", {})

                    col1, col2, col3 = st.columns(3)
                    col1.metric(
                        label="Strict-preview tier",
                        value=f"{_tier_emoji(sp.get('tag','—'))} {sp.get('tag','—')}")
                    col2.metric(
                        label="Coverage",
                        value=f"{sp.get('covered', 0)} / {sp.get('total_operational', 0)}",
                        delta=f"{sp.get('coverage_pct', 0.0):.1f}%")
                    col3.metric(
                        label="Audit verdict",
                        value="✅ PASS" if g143.get("passed") else "❌ FAIL")

                    st.divider()

                    # Tier-thresholds reference card
                    st.markdown("**Tier thresholds** (defined in `scripts/audit.py`):")
                    threshold_cols = st.columns(4)
                    threshold_cols[0].markdown(
                        f"🔴 **BELOW STRICT THRESHOLD**\n\n< 50% coverage")
                    threshold_cols[1].markdown(
                        f"🟡 **STRICT-READY (preview)**\n\n[50%, 75%) — v10.119 crossing")
                    threshold_cols[2].markdown(
                        f"🟢 **STRICT-READY (high)**\n\n≥ 75% — v10.125 crossing ✅")
                    threshold_cols[3].markdown(
                        f"⚫ **Strict-flip**\n\n100% — v10.130+ target")

                    st.divider()

                    with st.expander("Full G143 summary text", expanded=False):
                        st.code(g143.get("summary", "—"))

                with arc_tabs[1]:
                    st.caption(
                        "Equivalent to GET `/api/integration/rules`. "
                        "Cached 5 minutes; restart the page to force a refresh.")
                    rules = _load_rule_registry()
                    library = _load_kpi_library()
                    library_by_id = {k.get("id"): k for k in library}

                    st.write(f"**{len(rules)} active aggregation rules** registered.")

                    # Filters
                    fc1, fc2, fc3 = st.columns(3)
                    with fc1:
                        all_patterns = sorted(set(r.get("pattern", "") for r in rules))
                        pattern_filter = st.multiselect(
                            "Filter by pattern", all_patterns, default=[])
                    with fc2:
                        all_tables = sorted(set(r.get("source_table", "") for r in rules))
                        table_filter = st.multiselect(
                            "Filter by source table", all_tables, default=[])
                    with fc3:
                        kpi_search = st.text_input("Search KPI ID / name", "")

                    filtered = rules
                    if pattern_filter:
                        filtered = [r for r in filtered
                                    if r.get("pattern") in pattern_filter]
                    if table_filter:
                        filtered = [r for r in filtered
                                    if r.get("source_table") in table_filter]
                    if kpi_search.strip():
                        q = kpi_search.strip().lower()
                        filtered = [r for r in filtered
                                    if q in (r.get("kpi_id", "") or "").lower()
                                    or q in (library_by_id.get(r.get("kpi_id"), {})
                                             .get("name", "") or "").lower()]

                    if not filtered:
                        st.info("No rules match the current filters.")
                    else:
                        rows = []
                        for r in filtered:
                            kpi = library_by_id.get(r.get("kpi_id"), {})
                            rows.append({
                                "KPI ID": r.get("kpi_id", ""),
                                "KPI Name": kpi.get("name", "—"),
                                "Pattern": r.get("pattern", ""),
                                "Source": r.get("source_table", ""),
                                "Staff field":
                                    r.get("staff_field", "(table default)"),
                                "Period field": r.get("period_field", "—"),
                                "Origin drop": r.get("_origin", "—"),
                            })
                        st.dataframe(rows, use_container_width=True, hide_index=True)

                with arc_tabs[2]:
                    st.markdown(
                        "Pick a period and compute per-staff actuals from the operational "
                        "tables. **Read-only** — no writes happen on this tab. Equivalent "
                        "to GET `/api/integration/actuals/{period}`.")

                    period = st.text_input(
                        "Period (YYYY-MM)", value="2026-04",
                        help="Most rules use last_updated or operational date fields. "
                             "Enter the YYYY-MM you want to filter on.")

                    if st.button("Compute preview actuals", key="preview_actuals_btn"):
                        try:
                            from utils.actuals_engine import (
                                compute_actuals_from_operational_tables)
                            with st.spinner(f"Computing actuals for {period}…"):
                                result = compute_actuals_from_operational_tables(period)
                            st.success(f"Computed {len(result)} KPI groups.")

                            # Summary metrics
                            covered_kpis = sum(1 for kpi_id, by_staff in result.items()
                                               if by_staff)
                            total_staff_actuals = sum(len(by_staff)
                                                       for by_staff in result.values())
                            colA, colB = st.columns(2)
                            colA.metric("KPIs producing actuals", covered_kpis)
                            colB.metric("Total staff-rows emitted", total_staff_actuals)

                            # Per-rule sample
                            with st.expander("Per-rule sample (first 3 staff per KPI)",
                                             expanded=False):
                                preview_rows = []
                                for kpi_id, by_staff in sorted(result.items()):
                                    n = len(by_staff)
                                    sample_items = list(by_staff.items())[:3]
                                    sample_str = ", ".join(
                                        f"{s}: {v:.2f}" if isinstance(v, (int, float))
                                        else f"{s}: {v}"
                                        for s, v in sample_items)
                                    preview_rows.append({
                                        "KPI ID": kpi_id,
                                        "Staff covered": n,
                                        "Sample (first 3)": sample_str or "—",
                                    })
                                st.dataframe(
                                    preview_rows, use_container_width=True, hide_index=True)
                        except ImportError as exc:
                            st.error(
                                f"compute_actuals_from_operational_tables not available: "
                                f"{exc}")
                        except Exception as exc:
                            st.error(f"Compute failed: {exc}")

                with arc_tabs[3]:
                    st.markdown(
                        "Hit rates from the name-resolver and role-resolver caches. "
                        "Equivalent to GET `/api/integration/resolution-metrics`.")

                    try:
                        from utils.staff_name_resolver import (
                            refresh_cache as _refresh_name)
                        from utils.staff_role_resolver import (
                            refresh_cache as _refresh_role)
                        # Try to introspect the resolvers if they expose metric APIs;
                        # otherwise just confirm cache freshness via refresh.
                        from utils.staff_name_resolver import name_to_code as _name_to_code

                        # Refresh caches so the metric snapshot is current
                        _refresh_name()
                        try:
                            _refresh_role()
                        except Exception:
                            pass

                        st.success(
                            "Name + role resolver caches refreshed. Detailed hit-rate "
                            "metrics surface via the API endpoint; this tab confirms the "
                            "resolvers are responsive.")

                        # Show a probe
                        probe = st.text_input(
                            "Probe: full-name → staff_code lookup",
                            value="William Mwanake")
                        if probe.strip():
                            try:
                                code = _name_to_code(probe.strip())
                                if code:
                                    st.metric("Resolved staff_code", code)
                                else:
                                    st.warning(f"No staff_code for '{probe}'.")
                            except Exception as exc:
                                st.error(f"Resolver error: {exc}")

                    except ImportError as exc:
                        st.error(f"Resolvers not available: {exc}")

                with arc_tabs[4]:
                    st.markdown(
                        "Trigger the full integration-layer pipeline for a period. "
                        "Equivalent to POST `/api/integration/run-period`.")

                    sec = _load_security_config()
                    if sec.get("role_gating_enabled"):
                        st.info(
                            f"🔒 **Role-gating ON** (v10.126 hard-flip default). "
                            f"Allowed roles for write: "
                            f"`{', '.join(sec.get('allowed_roles_for_write', []))}`.")
                    else:
                        st.warning(
                            "⚠️ Role-gating DISABLED in config. JWT-only auth is in effect. "
                            "Any logged-in user can trigger writes.")

                    user_role = _user_role()
                    user_can_write = _can_write()
                    st.caption(f"Your role: `{user_role or 'unknown'}` — "
                               f"{'✅ allowed to write' if user_can_write else '⛔ NOT allowed to write'}")

                    period_run = st.text_input(
                        "Period (YYYY-MM)", value="2026-04", key="run_period_input")
                    dry_run = st.checkbox(
                        "Dry run (do NOT write actuals; preview only)",
                        value=True,
                        help="Default ON. Uncheck to actually write actuals to the BSC "
                             "engine. v10.116+ supports both modes.")

                    btn_disabled = not user_can_write
                    btn_label = ("Run period (dry-run)" if dry_run
                                 else "Run period (WRITE)")

                    if st.button(btn_label, key="run_period_btn", disabled=btn_disabled):
                        if not user_can_write:
                            st.error("Role check failed — operation refused.")
                        else:
                            try:
                                from utils.actuals_engine import (
                                    compute_actuals_from_operational_tables)
                                with st.spinner(f"Running pipeline for {period_run}…"):
                                    actuals = compute_actuals_from_operational_tables(
                                        period_run)
                                if dry_run:
                                    st.success(
                                        f"DRY RUN — would have written {len(actuals)} "
                                        f"KPI groups for {period_run}. No writes "
                                        f"performed.")
                                else:
                                    # Writing path is intentionally not implemented in
                                    # this cockpit. Banks should call the API endpoint
                                    # POST /api/integration/run-period with dry_run=false
                                    # for the canonical write path. Surfacing it here
                                    # would duplicate the contract.
                                    st.warning(
                                        "Cockpit only supports DRY RUN. For writes, call "
                                        "POST /api/integration/run-period directly with "
                                        "dry_run=false (uses the same auth + role check).")
                                audit_log(
                                    "integration_cockpit_run_period",
                                    username,
                                    f"username={username} period={period_run} "
                                    f"dry_run={dry_run} kpi_groups={len(actuals)}")
                            except Exception as exc:
                                st.error(f"Pipeline run failed: {exc}")
                                audit_log(
                                    "integration_cockpit_run_period_error",
                                    username,
                                    f"username={username} error={exc}")
                    elif btn_disabled:
                        st.caption(
                            "Button disabled because role-gating excludes your role. "
                            "Contact admin to add your role to "
                            "`_security.allowed_roles_for_write` in "
                            "`integration_layer_config.json`.")

                with arc_tabs[5]:
                    st.caption(
                        "Equivalent to GET `/api/integration/rule-explain/{kpi_id}`. "
                        "For any wired rule + period, shows the rule definition, input "
                        "row counts at each filtering stage, sample matched rows, and "
                        "the per-staff intermediate values that produce the actuals. "
                        "When a number on a dashboard looks wrong, this is where you "
                        "see the working.")

                    try:
                        from utils.kpi_aggregation_rules import (
                            REGISTRY, compute_rule, _row_in_period,
                        )
                        from utils.staff_field_resolver import resolve_staff_field
                    except Exception as e:
                        st.error(f"Integration Layer unavailable: "
                                 f"{type(e).__name__}: {e}")
                    else:
                        # Build picker from REGISTRY (active rules only)
                        active = sorted(
                            [r for r in REGISTRY],
                            key=lambda r: (r.kpi_id, r.source_table))
                        kpi_options = [f"{r.kpi_id} — {r.source_table} ({r.pattern})"
                                       for r in active]

                        col_a, col_b, col_c = st.columns([3, 2, 2])
                        with col_a:
                            picked = st.selectbox(
                                "Rule",
                                options=kpi_options,
                                key="debug_rule_picker",
                                help="All active aggregation rules (KPI — source table — "
                                     "pattern). Library duplicates show the same KPI "
                                     "twice; the first match is explained.")
                        with col_b:
                            period_input = st.text_input(
                                "Period",
                                value="2026-04",
                                max_chars=7,
                                key="debug_period",
                                help="YYYY-MM format")
                        with col_c:
                            staff_filter = st.text_input(
                                "Staff code (optional)",
                                value="",
                                key="debug_staff",
                                help="Narrow the per-staff slice to one staff")
                        sample_size = st.slider(
                            "Sample rows to show", min_value=1, max_value=20, value=5,
                            key="debug_sample_size")

                        # Resolve picked rule
                        idx = kpi_options.index(picked)
                        rule = active[idx]

                        # Validate period
                        import re as _re
                        if not _re.match(r"^\d{4}-(0[1-9]|1[0-2])$", period_input):
                            st.warning(f"Invalid period {period_input!r}; "
                                       f"expected YYYY-MM (e.g. 2026-04)")
                        else:
                            # Stage 1: read table
                            from pathlib import Path as _P
                            data_dir = _P(__file__).resolve().parent.parent / "data"
                            tbl_path = data_dir / f"{rule.source_table}.json"
                            if not tbl_path.exists():
                                st.error(f"Operational table {rule.source_table!r} "
                                         f"not found at {tbl_path}")
                            else:
                                import json as _j
                                with open(tbl_path) as _f:
                                    _d = _j.load(_f)
                                rows = _d if isinstance(_d, list) else list(_d.values())

                                # Stage 2: filter by period
                                rows_in_period = [r for r in rows
                                                  if _row_in_period(r, rule.period_field,
                                                                    period_input)]

                                # Stage 3: filter by primary predicate
                                primary_pred = (rule.predicate
                                                or rule.numerator_pred
                                                or (lambda _r: True))
                                try:
                                    rows_matching = [r for r in rows_in_period
                                                     if primary_pred(r)]
                                except Exception:
                                    rows_matching = rows_in_period

                                # Stage 4: distinct staff
                                sf = resolve_staff_field(rule.source_table,
                                                         rule.staff_field)
                                distinct = set()
                                for r in rows_matching:
                                    if rule.staff_field_extractor is not None:
                                        try:
                                            sc = rule.staff_field_extractor(r)
                                        except Exception:
                                            sc = None
                                    else:
                                        sc = r.get(sf)
                                    if sc:
                                        distinct.add(str(sc))

                                # Stage 5: compute_rule
                                try:
                                    per_staff = compute_rule(rule, rows, period_input, sf)
                                except Exception as _e:
                                    st.error(f"compute_rule failed: "
                                             f"{type(_e).__name__}: {_e}")
                                    per_staff = {}

                                # ── Display ──
                                st.divider()

                                # Row 1: rule definition
                                with st.expander("Rule definition", expanded=False):
                                    st.json({
                                        "kpi_id":            rule.kpi_id,
                                        "source_table":      rule.source_table,
                                        "pattern":           rule.pattern,
                                        "description":       rule.description or "",
                                        "period_field":      rule.period_field,
                                        "staff_field":       rule.staff_field,
                                        "resolved_staff_field": sf,
                                        "value_field":       rule.value_field,
                                        "start_field":       rule.start_field,
                                        "end_field":         rule.end_field,
                                        "numerator_field":   rule.numerator_field,
                                        "denominator_field": rule.denominator_field,
                                        "bool_field":        rule.bool_field,
                                        "decimals":          rule.decimals,
                                        "invert":            rule.invert,
                                        "uses_extractor":
                                            rule.staff_field_extractor is not None,
                                    })

                                # Row 2: pipeline funnel
                                st.subheader("Input funnel")
                                m1, m2, m3, m4 = st.columns(4)
                                m1.metric("Rows in table", len(rows))
                                m2.metric("In period", len(rows_in_period))
                                m3.metric("Matching predicate", len(rows_matching))
                                m4.metric("Distinct staff", len(distinct))

                                # Row 3: sample rows
                                st.subheader(f"Sample matched rows "
                                             f"(top {min(sample_size, len(rows_matching))} "
                                             f"of {len(rows_matching)})")
                                if rows_matching:
                                    import pandas as _pd
                                    sample = []
                                    for r in rows_matching[:sample_size]:
                                        # truncate verbose values for display
                                        display = {}
                                        for k, v in r.items():
                                            if isinstance(v, str) and len(v) > 80:
                                                display[k] = v[:80] + "…"
                                            elif isinstance(v, (list, dict)):
                                                display[k] = _j.dumps(v)[:80] + "…" \
                                                    if len(_j.dumps(v)) > 80 else v
                                            else:
                                                display[k] = v
                                        sample.append(display)
                                    st.dataframe(_pd.DataFrame(sample),
                                                 use_container_width=True)
                                else:
                                    st.info("No rows match the rule's primary predicate "
                                            "for this period. Verify period_field "
                                            f"({rule.period_field!r}) is populated and "
                                            "the predicate logic.")

                                # Row 4: per-staff values
                                st.subheader("Per-staff aggregated values")
                                if not per_staff:
                                    st.info("compute_rule returned no per-staff values.")
                                else:
                                    items = sorted(per_staff.items(),
                                                   key=lambda kv: -float(kv[1])
                                                       if isinstance(kv[1], (int, float))
                                                       else 0)
                                    if staff_filter:
                                        items = [kv for kv in items if kv[0] == staff_filter]
                                    if not items:
                                        st.warning(f"No per-staff entry for "
                                                   f"{staff_filter!r}.")
                                    else:
                                        df_rows = [{"staff_code": sc,
                                                    "value": round(float(v), rule.decimals)
                                                              if isinstance(v, (int, float))
                                                              else v}
                                                   for sc, v in items[:50]]
                                        st.dataframe(_pd.DataFrame(df_rows),
                                                     use_container_width=True)
                                        if len(items) > 50:
                                            st.caption(f"Showing top 50 of {len(items)} "
                                                       f"staff. Filter by staff code to "
                                                       "narrow.")

                # Integration footer audit
                try:
                    audit_log(
                        action="integration_arc_engines.view",
                        username=ud.get("username", "anonymous"),
                        detail=f"viewed_at={_dt_int.now(_tz_int.utc).isoformat()}",
                        module="systems_view")
                except Exception:
                    pass


    # ──────────────────────────────────────────────────────────────────────
    # Footer — link to charter
    # ──────────────────────────────────────────────────────────────────────
    st.divider()
    st.caption(
        "📖 Full charter: `docs/A2Z_SYSTEMS_CHARTER.md` (14 sections, "
        "v1.0). References: Donella Meadows *Thinking in Systems* (2008); "
        "Eric Evans *Domain-Driven Design* (2003); Stafford Beer "
        "*The Heart of Enterprise* (1979); John Gall *Systemantics* "
        "(1977). The systems layer evolves; it is never refactored."
    )


# ════════════════════════════════════════════════════════════════
# IT_DIGITAL_PT1 — render + helpers
# ════════════════════════════════════════════════════════════════

"""
Phase 2A — IT/Digital Foundation pt 1 (pages/96)
=================================================================
v10.281 — covers Standards #291-#295 (5 standards across 5 engines)

Audience: CTO, CIO, IT ops, SRE, security, compliance.

Tab map (7 tabs covering 5 standards + 2 supplementary):
  1. ITSM Incidents              — #291
  2. ITSM Changes & Assets       — #291
  3. Cloud Architecture          — #292
  4. Observability (SLI/SLO)     — #293
  5. Disaster Recovery           — #294
  6. API Gateway                 — #295
  7. Knowledge Base              — #291 (KB articles)
"""





try:
    from utils.page_access import require_access
except Exception:
    pass


@st.cache_resource
def _engines_pt1():
    return {
        "itsm": ITSMFrameworkEngine(),
        "cloud": CloudArchitectureEngine(),
        "obs": ObservabilityEngine(),
        "dr": DisasterRecoveryEngine(),
        "api": APIGatewayEngine(),
    }


def render_it_digital_pt1(actor: str) -> None:
    """Render the it_digital_pt1 view. Body extracted from
    the original page."""

    st.title("⚙️ IT/Digital Foundation — pt 1")
    st.caption(
        "v10.281 · Standards #291-#295 · ITSM · Cloud-Native · "
        "Observability · DR/BCP · API Gateway"
    )
    eng = _engines_pt1()

    tabs = st.tabs([
        "🎫 ITSM Incidents",
        "🔧 Changes & Assets",
        "☁️ Cloud Architecture",
        "📡 Observability",
        "🔥 Disaster Recovery",
        "🔌 API Gateway",
        "📖 Knowledge Base",
    ])

    # Tab 1: ITSM Incidents (#291)
    with tabs[0]:
        st.subheader("🎫 ITSM Incident Management — #291")
        st.caption(
            "ITIL v4 incident lifecycle: OPEN → IN_PROGRESS → RESOLVED → "
            "CLOSED with re-open path."
        )
        col1, col2 = st.columns([2, 1])
        with col1:
            opens = eng["itsm"].open_incidents()
            st.metric("Open incidents", len(opens))
            for i in opens[:20]:
                st.markdown(
                    f"**[{i['priority']}]** {i['title']} "
                    f"_state: {i['state']}_ "
                    f"<small>assigned: {i.get('assigned_to', '-')}</small>",
                    unsafe_allow_html=True,
                )
        with col2:
            with st.expander("➕ Raise incident", expanded=False):
                with st.form("raise_inc"):
                    iid = st.text_input("Incident ID")
                    title = st.text_input("Title")
                    priority = st.selectbox(
                        "Priority", ITSM_INCIDENT_PRIORITIES,
                    )
                    affected = st.text_input("Affected service")
                    assigned = st.text_input("Assigned to")
                    if st.form_submit_button("Raise"):
                        if iid and title:
                            r = eng["itsm"].raise_incident(
                                {"incident_id": iid, "title": title,
                                  "priority": priority,
                                  "affected_service": affected,
                                  "assigned_to": assigned},
                                actor="ops",
                            )
                            if r["raised"]:
                                audit_log(
                                    action="raise_incident",
                                    username="ops",
                                    module="it_digital_pt1",
                                )
                                st.success(f"Raised {iid}.")
                                st.rerun()
                            else:
                                st.error(f"Failed: {r.get('error', '?')}")

    # Tab 2: Changes + Assets (#291)
    with tabs[1]:
        st.subheader("🔧 ITSM Changes & Assets — #291")
        sub_chg, sub_ast = st.tabs(["Changes", "Assets"])
        with sub_chg:
            with st.expander("➕ Raise change request", expanded=False):
                with st.form("raise_chg"):
                    cid = st.text_input("Change ID")
                    ctitle = st.text_input("Title")
                    ctype = st.selectbox("Change type", CHANGE_TYPES)
                    cplan = st.text_area("Implementation plan")
                    cback = st.text_area("Rollback plan")
                    csched = st.text_input("Scheduled for", value="2026-06-01")
                    if st.form_submit_button("Raise"):
                        if cid and ctitle:
                            r = eng["itsm"].raise_change_request(
                                {"change_id": cid, "title": ctitle,
                                  "change_type": ctype,
                                  "implementation_plan": cplan,
                                  "rollback_plan": cback,
                                  "scheduled_for": csched},
                                actor="cto",
                            )
                            if r["raised"]:
                                audit_log(
                                    action="raise_change_request",
                                    username="cto",
                                    module="it_digital_pt1",
                                )
                                st.success(f"Raised {cid}.")
                                st.rerun()
                            else:
                                st.error(f"Failed: {r.get('error', '?')}")

        with sub_ast:
            with st.expander("➕ Register asset", expanded=False):
                with st.form("reg_asset"):
                    aid = st.text_input("Asset ID")
                    aname = st.text_input("Asset name")
                    atype = st.selectbox("Asset type", ASSET_TYPES)
                    aown = st.text_input("Owner team")
                    aloc = st.text_input("Location")
                    areason = st.text_input("Reason")
                    if st.form_submit_button("Register"):
                        if aid and aname and areason:
                            r = eng["itsm"].register_asset(
                                {"asset_id": aid, "asset_name": aname,
                                  "asset_type": atype, "owner_team": aown,
                                  "location": aloc},
                                actor="ops", reason=areason,
                            )
                            if r["registered"]:
                                audit_log(
                                    action="register_asset",
                                    username="ops",
                                    module="it_digital_pt1",
                                )
                                st.success(f"Registered {aid}.")
                                st.rerun()
                            else:
                                st.error(f"Failed: {r.get('error', '?')}")

    # Tab 3: Cloud Architecture (#292)
    with tabs[2]:
        st.subheader("☁️ Cloud-Native & Container Architecture — #292")
        st.caption(
            "Microservices, Kubernetes-native, multi-cloud (AWS/Azure/GCP) "
            "portability, 12-factor compliance."
        )
        services = eng["cloud"].list_active_services()
        st.metric("Registered services", len(services))
        with st.expander("➕ Register microservice", expanded=False):
            with st.form("reg_svc"):
                sid = st.text_input("Service ID")
                sname = st.text_input("Service name")
                sown = st.text_input("Owner team")
                sruntime = st.selectbox("Runtime", CONTAINER_RUNTIMES)
                sprimary = st.selectbox("Primary provider", CLOUD_PROVIDERS)
                ssecondary = st.multiselect(
                    "Secondary providers", CLOUD_PROVIDERS,
                )
                sreason = st.text_input("Reason")
                if st.form_submit_button("Register"):
                    if sid and sname and sown and sreason:
                        r = eng["cloud"].register_microservice(
                            {"service_id": sid, "service_name": sname,
                              "owner_team": sown,
                              "container_runtime": sruntime,
                              "primary_provider": sprimary,
                              "secondary_providers": ssecondary,
                              "twelve_factor_compliance": {}},
                            actor="cto", reason=sreason,
                        )
                        if r["registered"]:
                            audit_log(
                                action="register_microservice",
                                username="cto",
                                module="it_digital_pt1",
                            )
                            st.success(f"Registered {sid}.")
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error', '?')}")
        with st.expander("📊 Portability assessment", expanded=False):
            check_id = st.text_input("Service ID to assess",
                                          value="SVC-AUTH")
            if st.button("Assess") and check_id:
                a = eng["cloud"].portability_assessment(check_id)
                if a.get("found"):
                    st.metric(
                        "Portability score",
                        f"{a['portability_score']}",
                        delta=f"Grade {a['portability_grade']}",
                    )
                    st.write(
                        f"12-factor: {a['twelve_factor_passed']}/"
                        f"{a['twelve_factor_total']} = "
                        f"{a['compliance_pct']}%"
                    )
                    st.write(
                        f"Primary: **{a['primary_provider']}** · "
                        f"Secondary: {', '.join(a['secondary_providers']) or 'none'}"
                    )

    # Tab 4: Observability (#293)
    with tabs[3]:
        st.subheader("📡 Observability — SLI/SLO/Error Budget — #293")
        st.caption(
            "Prometheus + Grafana + Loki + Jaeger. Error budget burns at "
            f"≥{DEFAULT_BUDGET_BURN_THRESHOLD_PCT}% trigger oversight."
        )
        with st.expander("➕ Register SLI", expanded=False):
            with st.form("reg_sli"):
                lid = st.text_input("SLI ID")
                lname = st.text_input("SLI name")
                ltype = st.selectbox("SLI type", SLI_TYPES)
                lsvc = st.text_input("Service ID")
                lunit = st.text_input("Unit", value="%")
                lreason = st.text_input("Reason")
                if st.form_submit_button("Register"):
                    if lid and lname and lsvc and lreason:
                        r = eng["obs"].register_sli(
                            {"sli_id": lid, "sli_name": lname,
                              "sli_type": ltype, "service_id": lsvc,
                              "unit": lunit},
                            actor="sre", reason=lreason,
                        )
                        if r["registered"]:
                            audit_log(
                                action="register_sli",
                                username="sre",
                                module="it_digital_pt1",
                            )
                            st.success(f"Registered {lid}.")
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error', '?')}")

        with st.expander("➕ Register SLO", expanded=False):
            with st.form("reg_slo"):
                oid = st.text_input("SLO ID")
                oname = st.text_input("SLO name")
                osli = st.text_input("Linked SLI ID")
                otarget = st.text_input("Target %", value="99.9")
                owindow = st.selectbox("Time window", SLO_TIME_WINDOWS)
                opolicy = st.selectbox("Budget policy",
                                              ERROR_BUDGET_POLICIES, index=1)
                oreason = st.text_input("Reason", key="slo_reason")
                if st.form_submit_button("Register"):
                    if oid and oname and osli and oreason:
                        r = eng["obs"].register_slo(
                            {"slo_id": oid, "slo_name": oname,
                              "sli_id": osli, "target_pct": otarget,
                              "time_window": owindow,
                              "budget_policy": opolicy},
                            actor="sre", reason=oreason,
                        )
                        if r["registered"]:
                            audit_log(
                                action="register_slo",
                                username="sre",
                                module="it_digital_pt1",
                            )
                            st.success(f"Registered {oid}.")
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error', '?')}")

    # Tab 5: DR/BCP (#294)
    with tabs[4]:
        st.subheader("🔥 Disaster Recovery & Business Continuity — #294")
        st.caption(
            f"CBK target: RTO ≤ {DEFAULT_RTO_TARGET_HOURS}h, "
            f"RPO ≤ {DEFAULT_RPO_TARGET_MINUTES}min. "
            f"Reference: {CBK_DR_REGULATORY_REFERENCE}."
        )
        with st.expander("➕ Register DR plan", expanded=False):
            with st.form("reg_dr"):
                pid = st.text_input("Plan ID")
                pname = st.text_input("Plan name")
                psvc = st.text_input("Service ID")
                ptier = st.selectbox("Tier", DR_PLAN_TIERS)
                prto = st.text_input("RTO target hours", value="4")
                prpo = st.text_input("RPO target minutes", value="15")
                pprim = st.text_input("Primary region", value="af-south-1")
                pdr = st.text_input("DR region", value="eu-west-2")
                preason = st.text_input("Reason")
                if st.form_submit_button("Register"):
                    if pid and pname and psvc and preason:
                        r = eng["dr"].register_dr_plan(
                            {"plan_id": pid, "plan_name": pname,
                              "service_id": psvc, "tier": ptier,
                              "rto_target_hours": prto,
                              "rpo_target_minutes": prpo,
                              "primary_region": pprim,
                              "dr_region": pdr},
                            actor="cto", reason=preason,
                        )
                        if r["registered"]:
                            audit_log(
                                action="register_dr_plan",
                                username="cto",
                                module="it_digital_pt1",
                            )
                            st.success(f"Registered {pid}.")
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error', '?')}")
        with st.expander("📊 RTO/RPO Compliance Check", expanded=False):
            chk = st.text_input("Plan ID to check", value="DR-CORE")
            if st.button("Check") and chk:
                c = eng["dr"].rto_rpo_compliance(chk)
                if c.get("found"):
                    if c.get("no_data"):
                        st.warning("No measurements yet.")
                    else:
                        compliant_label = (
                            "✅ COMPLIANT" if c["cbk_compliant"]
                            else "❌ NON-COMPLIANT"
                        )
                        st.metric("CBK status", compliant_label)
                        st.write(
                            f"Target RTO: {c['target_rto_hours']}h · "
                            f"Target RPO: {c['target_rpo_minutes']}min"
                        )
                        st.write(
                            f"RTO breaches: {c['rto_breach_count']} · "
                            f"RPO breaches: {c['rpo_breach_count']}"
                        )

    # Tab 6: API Gateway (#295)
    with tabs[5]:
        st.subheader("🔌 API Gateway & Developer Portal — #295")
        st.caption(
            "Kong/Tyk gateway, OAuth2/OIDC, rate limiting, OpenAPI docs, "
            "developer onboarding."
        )
        with st.expander("➕ Register API", expanded=False):
            with st.form("reg_api"):
                aid = st.text_input("API ID")
                aname = st.text_input("API name")
                avers = st.text_input("Version", value="v1")
                aauth = st.selectbox("Auth scheme", AUTH_SCHEMES)
                abase = st.text_input("Base path", value="/api/v1")
                aown = st.text_input("Owner team")
                arate = st.text_input("Rate limit policy ID")
                areason = st.text_input("Reason", key="api_reason")
                if st.form_submit_button("Register"):
                    if aid and aname and abase and areason:
                        r = eng["api"].register_api(
                            {"api_id": aid, "api_name": aname,
                              "version": avers, "auth_scheme": aauth,
                              "base_path": abase, "owner_team": aown,
                              "rate_limit_policy_id": arate},
                            actor="cto", reason=areason,
                        )
                        if r["registered"]:
                            audit_log(
                                action="register_api",
                                username="cto",
                                module="it_digital_pt1",
                            )
                            st.success(f"Registered {aid}.")
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error', '?')}")
        with st.expander("📊 Rate-limit check", expanded=False):
            rai = st.text_input("API ID")
            rkey = st.text_input("Key ID")
            if st.button("Check") and rai and rkey:
                c = eng["api"].rate_limit_check(rai, rkey)
                if c.get("checked"):
                    st.metric("Remaining", c["remaining"])
                    st.write(
                        f"Limit: {c['limit']} per {c['window']} · "
                        f"Burst: {c['burst_limit']} · "
                        f"Current: {c['current_count']}"
                    )
                    if not c["within_limit"]:
                        st.error("Rate limit exceeded.")

    # Tab 7: KB Articles (#291)
    with tabs[6]:
        st.subheader("📖 Knowledge Base — #291")
        st.caption("ITIL knowledge management — runbooks, FAQs, postmortems.")
        with st.expander("➕ Publish article", expanded=False):
            with st.form("pub_kb"):
                kid = st.text_input("Article ID")
                ktitle = st.text_input("Title")
                kcat = st.text_input("Category")
                kcontent = st.text_area("Content", height=200)
                kreason = st.text_input("Publication reason")
                if st.form_submit_button("Publish"):
                    if kid and ktitle and kcontent and kreason:
                        r = eng["itsm"].publish_knowledge_article(
                            {"article_id": kid, "title": ktitle,
                              "content": kcontent, "category": kcat,
                              "tags": []},
                            actor="ops", reason=kreason,
                        )
                        if r["published"]:
                            audit_log(
                                action="publish_kb_article",
                                username="ops",
                                module="it_digital_pt1",
                            )
                            st.success(f"Published {kid}.")
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.get('error', '?')}")


# ════════════════════════════════════════════════════════════════
# IT_DIGITAL_PT2 — render + helpers
# ════════════════════════════════════════════════════════════════

"""
Phase 2A — IT/Digital Foundation pt 2 (pages/97)
=================================================================
v10.282 — covers Standards #296-#300 (5 standards across 5 engines)

Audience: CISO, CTO, CIO, security engineering, compliance, audit.

Tab map (7 tabs covering 5 standards):
  1. Encryption Keys                  — #296
  2. Secrets & PII                    — #296
  3. CI/CD Pipelines                  — #297
  4. Tenants & Branding               — #298
  5. Feature Flags                    — #298
  6. Digital Channels & Sessions      — #299
  7. Compliance & Certifications      — #300
"""





try:
    from utils.page_access import require_access
except Exception:
    pass


@st.cache_resource
def _engines_pt2():
    return {
        "enc": DataEncryptionEngine(),
        "ci": CICDEngine(),
        "mt": MultiTenancyEngine(),
        "db": DigitalBankingEngine(),
        "cbk": CBKComplianceEngine(),
    }


def render_it_digital_pt2(actor: str) -> None:
    """Render the it_digital_pt2 view. Body extracted from
    the original page."""

    st.title("🛡️ IT/Digital Foundation — pt 2")
    st.caption(
        "v10.282 · Standards #296-#300 · Encryption · CI/CD · "
        "Multi-Tenancy · Digital Channels · CBK Compliance"
    )

    eng = _engines_pt2()
    actor = st.session_state.get("user", {}).get(
        "username", "anonymous",
    )

    tabs = st.tabs([
        "🔐 Encryption Keys",
        "🗝️ Secrets & PII",
        "🚀 CI/CD Pipelines",
        "🏢 Tenants & Branding",
        "🎚️ Feature Flags",
        "📱 Channels & Sessions",
        "📋 Compliance & Certs",
    ])

    # =========================================================
    # Tab 1: Encryption Keys
    # =========================================================
    with tabs[0]:
        st.subheader("Encryption keys (Standard #296)")
        st.caption(
            f"DPA Kenya 2019 + CBK Cybersecurity. Default rotation: "
            f"{DEFAULT_KEY_ROTATION_DAYS} days. Algorithms: "
            f"{', '.join(ENCRYPTION_ALGORITHMS)}."
        )

        sub = st.tabs(["Register key", "Transition state", "Compliance"])

        with sub[0]:
            with st.form("enc_key_form"):
                kid = st.text_input("Key ID")
                kname = st.text_input("Key name")
                algo = st.selectbox("Algorithm", ENCRYPTION_ALGORITHMS)
                purpose = st.selectbox("Purpose", KEY_USAGE_PURPOSES)
                hsm = st.checkbox("HSM-backed", value=True)
                rot = st.number_input(
                    "Rotation days", min_value=30,
                    value=DEFAULT_KEY_ROTATION_DAYS,
                )
                reason = st.text_input("Reason")
                if st.form_submit_button("Register key"):
                    res = eng["enc"].register_encryption_key(
                        {"key_id": kid, "key_name": kname,
                         "algorithm": algo, "purpose": purpose,
                         "hsm_backed": hsm, "rotation_days": int(rot)},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_encryption_key",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(f"Key {kid} registered (PENDING)")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[1]:
            with st.form("enc_key_transition"):
                kid = st.text_input("Key ID to transition")
                new_state = st.selectbox("New state", KEY_STATES)
                reason = st.text_input("Reason")
                if st.form_submit_button("Transition"):
                    res = eng["enc"].transition_key_state(
                        kid, new_state, actor=actor, reason=reason,
                    )
                    audit_log(
                        action="transition_encryption_key_state",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[2]:
            stats = eng["enc"].encryption_compliance_status()
            cols = st.columns(4)
            cols[0].metric("Active keys", stats["active_keys"])
            cols[1].metric(
                "HSM coverage", f"{stats['hsm_coverage_pct']}%",
            )
            cols[2].metric(
                "Critical PII fields", stats["critical_pii_count"],
            )
            cols[3].metric(
                "Critical PII encrypted",
                f"{stats['critical_pii_coverage_pct']}%",
            )
            st.caption(
                f"Regulatory ref: {stats['regulatory_reference']}",
            )

    # =========================================================
    # Tab 2: Secrets & PII
    # =========================================================
    with tabs[1]:
        st.subheader("Secrets vault & PII registry (Standard #296)")

        sub = st.tabs(["Secret", "Rotate", "PII field",
                            "Security event", "Rotation due"])

        with sub[0]:
            with st.form("secret_form"):
                sid = st.text_input("Secret ID")
                sname = st.text_input("Secret name")
                stype = st.selectbox("Type", SECRET_TYPES)
                vpath = st.text_input("Vault path")
                team = st.text_input("Owner team")
                rot = st.number_input(
                    "Rotation days", min_value=15,
                    value=DEFAULT_SECRET_ROTATION_DAYS,
                )
                reason = st.text_input("Reason")
                if st.form_submit_button("Register secret"):
                    res = eng["enc"].register_secret(
                        {"secret_id": sid, "secret_name": sname,
                         "secret_type": stype, "vault_path": vpath,
                         "owner_team": team, "rotation_days": int(rot)},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_secret",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(f"Secret {sid} registered")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[1]:
            with st.form("secret_rotate"):
                sid = st.text_input("Secret ID to rotate")
                reason = st.text_input("Rotation reason")
                if st.form_submit_button("Rotate"):
                    res = eng["enc"].rotate_secret(
                        sid, actor=actor, reason=reason,
                    )
                    audit_log(
                        action="rotate_secret",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("rotated"):
                        st.success(
                            f"Rotated. Count: {res.get('rotation_count')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[2]:
            with st.form("pii_form"):
                fid = st.text_input("Field ID")
                table = st.text_input("Table name")
                col = st.text_input("Column name")
                sens = st.selectbox(
                    "Sensitivity", PII_SENSITIVITY_LEVELS,
                )
                kref = st.text_input("Encryption key ID")
                reason = st.text_input("Reason")
                if st.form_submit_button("Register PII field"):
                    res = eng["enc"].register_pii_field(
                        {"field_id": fid, "table_name": table,
                         "column_name": col,
                         "sensitivity_level": sens,
                         "encryption_key_id": kref},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_pii_field",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(
                            f"PII field {fid} registered "
                            f"({DPA_KENYA_REGULATORY_REFERENCE})",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[3]:
            with st.form("sec_evt_form"):
                eid = st.text_input("Event ID")
                etype = st.selectbox("Type", SECURITY_EVENT_TYPES)
                subject = st.text_input("Subject")
                details = st.text_area("Details")
                severity = st.selectbox(
                    "Severity",
                    ("INFO", "LOW", "MEDIUM", "HIGH", "CRITICAL"),
                )
                if st.form_submit_button("Record event"):
                    res = eng["enc"].record_security_event(
                        {"event_id": eid, "event_type": etype,
                         "subject": subject, "details": details,
                         "severity": severity},
                        actor=actor,
                    )
                    audit_log(
                        action="record_security_event",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("recorded"):
                        st.success("Event recorded")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[4]:
            within = st.number_input(
                "Within next N days", min_value=1, value=30,
            )
            due = eng["enc"].secret_rotation_due(within_days=int(within))
            st.metric("Secrets due", len(due))
            for d in due[:10]:
                st.write(
                    f"• {d.get('secret_id')} — "
                    f"{d.get('next_rotation_at', '')[:10]}",
                )

    # =========================================================
    # Tab 3: CI/CD Pipelines
    # =========================================================
    with tabs[2]:
        st.subheader("CI/CD pipelines (Standard #297)")
        st.caption(
            f"Types: {', '.join(PIPELINE_TYPES)}. Default build timeout: "
            f"{DEFAULT_BUILD_TIMEOUT_MINUTES}m. Default deploy timeout: "
            f"{DEFAULT_DEPLOY_TIMEOUT_MINUTES}m."
        )

        sub = st.tabs([
            "Environment", "Pipeline", "Pipeline state",
            "Run", "Run state", "Metrics",
        ])

        with sub[0]:
            with st.form("env_form"):
                eid = st.text_input("Env ID")
                ename = st.text_input("Env name")
                etype = st.selectbox("Type", ENVIRONMENT_TYPES)
                reason = st.text_input("Reason")
                if st.form_submit_button("Register environment"):
                    res = eng["ci"].register_environment(
                        {"env_id": eid, "env_name": ename,
                         "env_type": etype},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_cicd_environment",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(f"Env {eid} registered")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[1]:
            with st.form("pipe_form"):
                pid = st.text_input("Pipeline ID")
                pname = st.text_input("Pipeline name")
                ptype = st.selectbox("Type", PIPELINE_TYPES)
                svc = st.text_input("Service ID")
                stages = st.multiselect(
                    "Stages", PIPELINE_STAGES,
                    default=list(PIPELINE_STAGES[:5]),
                )
                btim = st.number_input(
                    "Build timeout (min)", min_value=1,
                    value=DEFAULT_BUILD_TIMEOUT_MINUTES,
                )
                reason = st.text_input("Reason")
                if st.form_submit_button("Register pipeline"):
                    res = eng["ci"].register_pipeline(
                        {"pipeline_id": pid, "pipeline_name": pname,
                         "pipeline_type": ptype, "service_id": svc,
                         "stages": stages,
                         "build_timeout_minutes": int(btim)},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_pipeline",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(f"Pipeline {pid} registered (ACTIVE)")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[2]:
            with st.form("pipe_state"):
                pid = st.text_input("Pipeline ID")
                ns = st.selectbox("New state", PIPELINE_STATES)
                reason = st.text_input("Reason")
                if st.form_submit_button("Transition"):
                    res = eng["ci"].transition_pipeline_state(
                        pid, ns, actor=actor, reason=reason,
                    )
                    audit_log(
                        action="transition_pipeline_state",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[3]:
            with st.form("run_form"):
                rid = st.text_input("Run ID")
                pid = st.text_input("Pipeline ID")
                sha = st.text_input("Commit SHA")
                branch = st.text_input("Branch", value="main")
                env = st.text_input("Target environment")
                if st.form_submit_button("Record run"):
                    res = eng["ci"].record_pipeline_run(
                        {"run_id": rid, "pipeline_id": pid,
                         "commit_sha": sha, "branch": branch,
                         "triggered_at": datetime.utcnow().isoformat(),
                         "target_environment": env},
                        actor=actor,
                    )
                    audit_log(
                        action="record_pipeline_run",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("recorded"):
                        st.success(f"Run {rid} queued")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[4]:
            with st.form("run_state"):
                rid = st.text_input("Run ID")
                ns = st.selectbox("New state", RUN_STATES)
                reason = st.text_input("Reason")
                if st.form_submit_button("Transition"):
                    res = eng["ci"].transition_run_state(
                        rid, ns, actor=actor, reason=reason,
                    )
                    audit_log(
                        action="transition_run_state",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[5]:
            cols = st.columns(2)
            with cols[0]:
                pid = st.text_input("Pipeline ID for metrics")
                days = st.number_input(
                    "Window (days)", min_value=1, value=30,
                )
                if st.button("Get metrics"):
                    m = eng["ci"].pipeline_metrics(
                        pid, days=int(days),
                    )
                    st.metric("Total runs", m["total_runs"])
                    st.metric(
                        "Success rate", f"{m['success_rate_pct']}%",
                    )
                    st.metric(
                        "Avg duration (s)",
                        m["average_duration_seconds"],
                    )
            with cols[1]:
                env = st.text_input("Env name for deploy frequency")
                ddays = st.number_input(
                    "Deploy window (days)", min_value=1, value=30,
                    key="ddays",
                )
                if st.button("Get deploy freq"):
                    d = eng["ci"].deployment_frequency(
                        env, days=int(ddays),
                    )
                    st.metric(
                        "Successful deploys", d["successful_deployments"],
                    )
                    st.metric(
                        "Deploys per day", d["deployments_per_day"],
                    )

    # =========================================================
    # Tab 4: Tenants & Branding
    # =========================================================
    with tabs[3]:
        st.subheader("Multi-tenancy (Standard #298)")
        st.caption(
            f"Isolation models: {', '.join(ISOLATION_MODELS)}. "
            f"States: {', '.join(TENANT_STATES)}."
        )

        sub = st.tabs(["Tenant", "Tenant state", "Branding",
                            "Isolation check"])

        with sub[0]:
            with st.form("tenant_form"):
                tid = st.text_input("Tenant ID")
                tname = st.text_input("Tenant name")
                iso = st.selectbox("Isolation model", ISOLATION_MODELS)
                durl = st.text_input("Database URL ref")
                schema = st.text_input("Schema name")
                domain = st.text_input("Domain")
                reason = st.text_input("Reason")
                if st.form_submit_button("Register tenant"):
                    res = eng["mt"].register_tenant(
                        {"tenant_id": tid, "tenant_name": tname,
                         "isolation_model": iso,
                         "database_url_ref": durl,
                         "schema_name": schema, "domain": domain},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_tenant",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(
                            f"Tenant {tid} registered (PROVISIONING)",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[1]:
            with st.form("tenant_state"):
                tid = st.text_input("Tenant ID")
                ns = st.selectbox("New state", TENANT_STATES)
                reason = st.text_input("Reason")
                if st.form_submit_button("Transition"):
                    res = eng["mt"].transition_tenant_state(
                        tid, ns, actor=actor, reason=reason,
                    )
                    audit_log(
                        action="transition_tenant_state",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[2]:
            with st.form("brand_form"):
                pid = st.text_input("Profile ID")
                tid = st.text_input("Tenant ID")
                logo = st.text_input("Logo URL")
                primary = st.text_input("Primary color (hex)")
                secondary = st.text_input("Secondary color (hex)")
                fav = st.text_input("Favicon URL")
                email = st.text_input("Email sender")
                phone = st.text_input("Support phone")
                reason = st.text_input("Reason")
                if st.form_submit_button("Register branding"):
                    elements = {}
                    if logo:
                        elements["LOGO_URL"] = logo
                    if primary:
                        elements["PRIMARY_COLOR"] = primary
                    if secondary:
                        elements["SECONDARY_COLOR"] = secondary
                    if fav:
                        elements["FAVICON_URL"] = fav
                    if email:
                        elements["EMAIL_SENDER"] = email
                    if phone:
                        elements["SUPPORT_PHONE"] = phone
                    res = eng["mt"].register_branding_profile(
                        {"profile_id": pid, "tenant_id": tid,
                         "elements": elements},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_branding_profile",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(f"Branding profile {pid} registered")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[3]:
            tid = st.text_input(
                "Tenant ID for isolation check", key="iso_check_tid",
            )
            if st.button("Run check"):
                r = eng["mt"].tenant_isolation_check(tid)
                if r.get("found"):
                    if r["isolation_valid"]:
                        st.success(
                            f"Valid: {r['isolation_model']} ({r['state']})",
                        )
                    else:
                        st.error(
                            f"Violations: {', '.join(r['violations'])}",
                        )
                else:
                    st.error("Tenant not found")

    # =========================================================
    # Tab 5: Feature Flags
    # =========================================================
    with tabs[4]:
        st.subheader("Feature flags (Standard #298)")
        st.caption(
            f"Types: {', '.join(FLAG_TYPES)}. States: "
            f"{', '.join(FEATURE_FLAG_STATES)}."
        )

        sub = st.tabs(["Register flag", "Set tenant feature",
                            "Tenant features"])

        with sub[0]:
            with st.form("flag_form"):
                fid = st.text_input("Flag ID")
                fname = st.text_input("Flag name")
                ftype = st.selectbox("Type", FLAG_TYPES)
                if ftype == "BOOLEAN":
                    default = st.checkbox("Default value", value=False)
                elif ftype == "PERCENTAGE_ROLLOUT":
                    default = st.number_input(
                        "Default rollout %", min_value=0, max_value=100,
                        value=0,
                    )
                else:
                    default = st.text_area(
                        "Default allowlist (comma-separated)",
                    )
                desc = st.text_area("Description")
                reason = st.text_input("Reason")
                if st.form_submit_button("Register flag"):
                    res = eng["mt"].register_feature_flag(
                        {"flag_id": fid, "flag_name": fname,
                         "flag_type": ftype, "default_value": default,
                         "description": desc},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_feature_flag",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(f"Flag {fid} registered (ACTIVE)")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[1]:
            with st.form("set_feature"):
                tid = st.text_input("Tenant ID", key="tf_tid")
                fid = st.text_input("Feature ID", key="tf_fid")
                en = st.checkbox("Enabled")
                reason = st.text_input("Reason", key="tf_reason")
                if st.form_submit_button("Set"):
                    res = eng["mt"].set_tenant_feature(
                        tid, fid, en, actor=actor, reason=reason,
                    )
                    audit_log(
                        action="set_tenant_feature",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("set"):
                        if res.get("updated"):
                            st.success("Updated existing flag binding")
                        else:
                            st.success("Created flag binding")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[2]:
            tid = st.text_input("Tenant ID to inspect",
                                       key="ef_tid")
            if st.button("List enabled features"):
                feats = eng["mt"].enabled_features_for_tenant(tid)
                st.metric("Enabled features", len(feats))
                for f in feats:
                    st.write(f"• {f.get('feature_id')}")

    # =========================================================
    # Tab 6: Digital Channels & Sessions
    # =========================================================
    with tabs[5]:
        st.subheader("Digital banking suite (Standard #299)")
        st.caption(
            f"Platforms: {', '.join(APP_PLATFORMS)}. Idle timeout: "
            f"{DEFAULT_SESSION_IDLE_TIMEOUT_MINUTES}m. Hard timeout: "
            f"{DEFAULT_SESSION_HARD_TIMEOUT_MINUTES}m."
        )

        sub = st.tabs([
            "App", "Version", "Version state",
            "Session state", "Push notification",
            "Biometric", "Continuity",
        ])

        with sub[0]:
            with st.form("app_form"):
                aid = st.text_input("App ID")
                aname = st.text_input("App name")
                plat = st.selectbox("Platform", APP_PLATFORMS)
                store = st.text_input("Store URL")
                team = st.text_input("Owner team")
                reason = st.text_input("Reason")
                if st.form_submit_button("Register app"):
                    res = eng["db"].register_app(
                        {"app_id": aid, "app_name": aname,
                         "platform": plat, "store_url": store,
                         "owner_team": team},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_digital_app",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(f"App {aid} registered")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[1]:
            with st.form("ver_form"):
                vid = st.text_input("Version ID")
                aid = st.text_input("App ID", key="ver_aid")
                vnum = st.text_input("Version number")
                notes = st.text_area("Release notes")
                osmin = st.text_input("Min OS version")
                reason = st.text_input("Reason", key="ver_reason")
                if st.form_submit_button("Register version"):
                    res = eng["db"].register_app_version(
                        {"version_id": vid, "app_id": aid,
                         "version_number": vnum,
                         "release_notes": notes,
                         "min_os_version": osmin},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_app_version",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(f"Version {vid} registered (ALPHA)")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[2]:
            with st.form("ver_state"):
                vid = st.text_input("Version ID", key="vs_vid")
                ns = st.selectbox("New state", APP_VERSION_STATES)
                reason = st.text_input("Reason", key="vs_reason")
                if st.form_submit_button("Transition"):
                    res = eng["db"].transition_version_state(
                        vid, ns, actor=actor, reason=reason,
                    )
                    audit_log(
                        action="transition_version_state",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[3]:
            with st.form("session_state"):
                sid = st.text_input("Session ID")
                ns = st.selectbox("New state", SESSION_STATES)
                reason = st.text_input("Reason", key="ss_reason")
                if st.form_submit_button("Transition"):
                    res = eng["db"].transition_session_state(
                        sid, ns, actor=actor, reason=reason,
                    )
                    audit_log(
                        action="transition_session_state",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("transitioned"):
                        st.success(
                            f"{res.get('from')} → {res.get('to')}",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[4]:
            with st.form("push_form"):
                nid = st.text_input("Notification ID")
                cid = st.text_input("Customer ID", key="pn_cid")
                ntype = st.selectbox("Type", NOTIFICATION_TYPES)
                title = st.text_input("Title")
                body = st.text_area("Body")
                deep = st.text_input("Deep link")
                if st.form_submit_button("Queue notification"):
                    res = eng["db"].record_push_notification(
                        {"notification_id": nid, "customer_id": cid,
                         "notification_type": ntype,
                         "title": title, "body": body,
                         "deep_link": deep},
                        actor=actor,
                    )
                    audit_log(
                        action="record_push_notification",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("recorded"):
                        st.success(f"Notification {nid} queued")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[5]:
            with st.form("bio_form"):
                eid = st.text_input("Enrollment ID")
                cid = st.text_input("Customer ID", key="bio_cid")
                fp = st.text_input("Device fingerprint")
                btype = st.selectbox("Biometric type", BIOMETRIC_TYPES)
                reason = st.text_input("Reason", key="bio_reason")
                if st.form_submit_button("Enroll"):
                    res = eng["db"].biometric_enrollment(
                        {"enrollment_id": eid, "customer_id": cid,
                         "device_fingerprint": fp,
                         "biometric_type": btype},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="biometric_enrollment",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("enrolled"):
                        st.success(f"Enrollment {eid} active")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[6]:
            cid = st.text_input("Customer ID for continuity",
                                       key="cc_cid")
            if st.button("Check continuity"):
                c = eng["db"].session_continuity_check(cid)
                cols = st.columns(4)
                cols[0].metric("Total sessions", c["total_sessions"])
                cols[1].metric("Active", c["active_sessions"])
                cols[2].metric("Idle", c["idle_sessions"])
                cols[3].metric(
                    "Platforms", c["unique_platforms"],
                )
                if c["omnichannel"]:
                    st.success("Omnichannel: " + ", ".join(c["platforms"]))
                else:
                    st.info("Single-channel only")

            ndays = st.number_input(
                "Notification window (days)", min_value=1, value=7,
            )
            if st.button("Notification metrics"):
                m = eng["db"].notification_metrics(days=int(ndays))
                cols = st.columns(3)
                cols[0].metric("Total", m["total_notifications"])
                cols[1].metric("Delivered", m["delivered"])
                cols[2].metric(
                    "Delivery rate", f"{m['delivery_rate_pct']}%",
                )

    # =========================================================
    # Tab 7: Compliance & Certifications
    # =========================================================
    with tabs[6]:
        st.subheader(
            "CBK IT compliance & certifications (Standard #300)",
        )
        st.caption(
            f"Frameworks: {', '.join(COMPLIANCE_FRAMEWORKS)}. "
            f"Reg ref: {CBK_REGULATORY_REFERENCE}. "
            f"Remediation SLA (CRITICAL): "
            f"{DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY['CRITICAL']}d, "
            f"HIGH: {DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY['HIGH']}d."
        )

        sub = st.tabs([
            "Program", "Control", "Finding",
            "Certification", "Summary", "Expiring",
        ])

        with sub[0]:
            with st.form("prog_form"):
                pid = st.text_input("Program ID")
                pname = st.text_input("Program name")
                fw = st.selectbox("Framework", COMPLIANCE_FRAMEWORKS)
                owner = st.text_input("Owner role")
                scope = st.text_area("Scope")
                reason = st.text_input("Reason")
                if st.form_submit_button("Register program"):
                    res = eng["cbk"].register_compliance_program(
                        {"program_id": pid, "program_name": pname,
                         "framework": fw, "owner_role": owner,
                         "scope": scope},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_compliance_program",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(
                            f"Program {pid} registered (PLANNED)",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

            with st.expander("Transition program state"):
                with st.form("prog_state"):
                    pid_t = st.text_input("Program ID", key="ps_pid")
                    ns = st.selectbox("New state", PROGRAM_STATES)
                    reason_t = st.text_input("Reason", key="ps_reason")
                    if st.form_submit_button("Transition"):
                        res = eng["cbk"].transition_program_state(
                            pid_t, ns, actor=actor, reason=reason_t,
                        )
                        audit_log(
                            action="transition_program_state",
                            username=actor,
                            module="it_digital_pt2",
                        )
                        if res.get("transitioned"):
                            st.success(
                                f"{res.get('from')} → {res.get('to')}",
                            )
                        else:
                            st.error(res.get("error", "Failed"))

        with sub[1]:
            with st.form("ctl_form"):
                cid = st.text_input("Control ID")
                pid = st.text_input("Program ID", key="ctl_pid")
                cname = st.text_input("Control name")
                cat = st.selectbox("Category", CONTROL_CATEGORIES)
                desc = st.text_area("Description")
                owner = st.text_input("Owner role", key="ctl_owner")
                reason = st.text_input("Reason", key="ctl_reason")
                if st.form_submit_button("Register control"):
                    res = eng["cbk"].register_control(
                        {"control_id": cid, "program_id": pid,
                         "control_name": cname, "category": cat,
                         "description": desc, "owner_role": owner},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_compliance_control",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(f"Control {cid} registered")
                    else:
                        st.error(res.get("error", "Failed"))

        with sub[2]:
            with st.form("find_form"):
                fid = st.text_input("Finding ID")
                cid = st.text_input("Control ID", key="find_cid")
                sev = st.selectbox("Severity", FINDING_SEVERITIES)
                desc = st.text_area("Description", key="find_desc")
                src = st.text_input("Audit source")
                if st.form_submit_button("Record finding"):
                    res = eng["cbk"].record_audit_finding(
                        {"finding_id": fid, "control_id": cid,
                         "severity": sev, "description": desc,
                         "audit_source": src},
                        actor=actor,
                    )
                    audit_log(
                        action="record_audit_finding",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("recorded"):
                        st.success(
                            f"Finding {fid} recorded (OPEN, "
                            f"SLA: "
                            f"{DEFAULT_REMEDIATION_SLA_DAYS_BY_SEVERITY[sev]}d)",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

            with st.expander("Transition finding state"):
                with st.form("find_state"):
                    fid_t = st.text_input("Finding ID", key="fs_fid")
                    ns = st.selectbox("New state", FINDING_STATES)
                    reason_t = st.text_input("Reason", key="fs_reason")
                    if st.form_submit_button("Transition"):
                        res = eng["cbk"].transition_finding_state(
                            fid_t, ns, actor=actor, reason=reason_t,
                        )
                        audit_log(
                            action="transition_finding_state",
                            username=actor,
                            module="it_digital_pt2",
                        )
                        if res.get("transitioned"):
                            st.success(
                                f"{res.get('from')} → {res.get('to')}",
                            )
                        else:
                            st.error(res.get("error", "Failed"))

        with sub[3]:
            with st.form("cert_form"):
                cid = st.text_input("Certification ID")
                fw = st.selectbox(
                    "Framework", COMPLIANCE_FRAMEWORKS,
                    key="cert_fw",
                )
                issued = st.text_input("Issued at (ISO)")
                expires = st.text_input("Expires at (ISO)")
                issuer = st.text_input("Issuer")
                scope = st.text_input("Scope")
                evidence = st.text_input("Evidence URL")
                reason = st.text_input("Reason", key="cert_reason")
                if st.form_submit_button("Register certification"):
                    res = eng["cbk"].register_certification(
                        {"certification_id": cid, "framework": fw,
                         "issued_at": issued, "expires_at": expires,
                         "issuer": issuer, "scope": scope,
                         "evidence_url": evidence},
                        actor=actor, reason=reason,
                    )
                    audit_log(
                        action="register_certification",
                        username=actor,
                        module="it_digital_pt2",
                    )
                    if res.get("registered"):
                        st.success(
                            f"Certification {cid} registered (PENDING)",
                        )
                    else:
                        st.error(res.get("error", "Failed"))

            with st.expander("Transition certification state"):
                with st.form("cert_state"):
                    cid_t = st.text_input("Certification ID", key="cs_cid")
                    ns = st.selectbox("New state", CERTIFICATION_STATES)
                    reason_t = st.text_input("Reason", key="cs_reason")
                    if st.form_submit_button("Transition"):
                        res = eng["cbk"].transition_certification_state(
                            cid_t, ns, actor=actor, reason=reason_t,
                        )
                        audit_log(
                            action="transition_certification_state",
                            username=actor,
                            module="it_digital_pt2",
                        )
                        if res.get("transitioned"):
                            st.success(
                                f"{res.get('from')} → {res.get('to')}",
                            )
                        else:
                            st.error(res.get("error", "Failed"))

        with sub[4]:
            fw = st.selectbox(
                "Framework filter (optional)",
                ("ALL",) + COMPLIANCE_FRAMEWORKS,
            )
            fw_arg = None if fw == "ALL" else fw
            s = eng["cbk"].compliance_summary(framework=fw_arg)
            cols = st.columns(4)
            cols[0].metric("Programs", s["total_programs"])
            cols[1].metric("Active", s["active_programs"])
            cols[2].metric("Open findings", s["open_findings"])
            cols[3].metric("Critical open", s["critical_open"])
            st.caption(f"Reg ref: {s['regulatory_reference']}")

        with sub[5]:
            within = st.number_input(
                "Window (days)", min_value=1, value=90,
                key="exp_within",
            )
            exp = eng["cbk"].expiring_certifications(
                within_days=int(within),
            )
            st.metric("Expiring certifications", len(exp))
            for e_ in exp[:10]:
                st.write(
                    f"• {e_.get('certification_id')} "
                    f"({e_.get('framework')}) — expires "
                    f"{e_.get('expires_at', '')[:10]}",
                )


# ════════════════════════════════════════════════════════════════
# PLATFORM_HEALTH — render + helpers
# ════════════════════════════════════════════════════════════════

"""pages/98_platform_health.py — v10.74 platform health dashboard.

Operator-facing single-page health view of the platform. Runs the
three diagnostic checks that determine whether the platform is in
a known-good state:

  1. Audit gates       — `python scripts/audit.py` (136 ratchet gates)
  2. Structural checks — `python scripts/structure_audit.py` (HARD/SOFT)
  3. Engine self-tests — `python scripts/run_engine_self_tests.py`
                         (140+ diagnostic engines, ~3-4 seconds total)

Plus inventory tabs:
  4. Standards summary  — by status / arc / priority tier
  5. Scenarios summary  — by category / requires_engines

Why a Streamlit page instead of just CLI: operators (business analysts,
auditors, the bank's IT manager) need a 30-second confidence check
they can run without opening a terminal. The CLI scripts always run
the same checks; this page is the one-click surface.

Per Rule 7, the page surfaces results — it never auto-fixes
violations, never restarts services, never modifies the registry,
never gates downstream pages. If something is red, the operator
investigates; the page just makes the red visible.

Caches: subprocess outputs cached for 60 seconds via
@st.cache_data(ttl=60) to avoid re-running on every interaction.
Manual `Run check` button bypasses cache via cache.clear().
"""




# ───── Page setup ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Platform Health",
    page_icon="🩺",
    layout="wide")

# Access guard: aligns with existing pattern. Module name
# 'platform_health' should be added to MODULE_ACCESS in utils.core
# for whoever should see this page (typically Admin + IT Manager).
# Falling back to silent=True when module isn't registered yet so
# the page is still discoverable during initial deployment.


def render_platform_health(actor: str) -> None:
    """Render the platform_health view. Body extracted from
    the original page."""

    ud = st.session_state.get("user_data", {}) or {}
    username = ud.get("username", "anonymous")
    audit_log(
        "PLATFORM_HEALTH_VIEWED",
        username=username,
        detail="opened platform health dashboard")

    REPO_ROOT = Path(__file__).resolve().parent.parent

    # ───── Header ──────────────────────────────────────────────────────────
    st.title("🩺 Platform Health")
    st.caption(
        f"Operator confidence check · v10.74 · "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")

    st.markdown(
        "Each tab runs a real diagnostic against the running platform. "
        "Results are cached for 60 seconds to keep the page snappy. Press "
        "**Refresh all checks** to re-run from scratch.")

    if st.button("🔄 Refresh all checks", help="Bypass 60-second cache"):
        st.cache_data.clear()
        audit_log(
            "PLATFORM_HEALTH_REFRESHED",
            username=username,
            detail="manually cleared health cache")
        st.rerun()


    # ───── Helpers (cached) ────────────────────────────────────────────────
    @st.cache_data(ttl=60)
    def run_audit() -> Dict[str, object]:
        """Run scripts/audit.py and return parsed result."""
        try:
            r = subprocess.run(
                [sys.executable, "scripts/audit.py"],
                cwd=REPO_ROOT, capture_output=True, text=True,
                timeout=180)
        except subprocess.TimeoutExpired:
            return {
                "ok": False, "score": "n/a",
                "passed": 0, "total": 0,
                "raw_output": "TIMEOUT after 180s",
                "ran_at": datetime.now().isoformat()}
        raw = (r.stdout or "") + "\n" + (r.stderr or "")
        score_line = next(
            (line for line in raw.splitlines()
             if "Score:" in line),
            "")
        # Parse "Score: 136/136 gates = 100.0% — PASS"
        passed = total = 0
        ok = False
        if "/" in score_line and "Score:" in score_line:
            try:
                frag = score_line.split("Score:")[1].split("gates")[0]
                passed_str, total_str = frag.strip().split("/")
                passed = int(passed_str.strip())
                total = int(total_str.strip())
                ok = passed == total and "PASS" in score_line
            except (ValueError, IndexError):
                pass
        return {
            "ok": ok and r.returncode == 0,
            "score": f"{passed}/{total}" if total else "n/a",
            "passed": passed, "total": total,
            "raw_output": raw,
            "returncode": r.returncode,
            "ran_at": datetime.now().isoformat()}


    @st.cache_data(ttl=60)
    def run_structure_audit() -> Dict[str, object]:
        """Run scripts/structure_audit.py and parse for STABLE marker."""
        try:
            r = subprocess.run(
                [sys.executable, "scripts/structure_audit.py"],
                cwd=REPO_ROOT, capture_output=True, text=True,
                timeout=60)
        except subprocess.TimeoutExpired:
            return {
                "ok": False, "stable": False,
                "raw_output": "TIMEOUT after 60s",
                "ran_at": datetime.now().isoformat()}
        raw = (r.stdout or "") + "\n" + (r.stderr or "")
        stable = "STABLE" in raw and "match baseline" in raw
        # Parse module/import counts
        modules = imports = hard = 0
        for line in raw.splitlines():
            if "Modules scanned:" in line:
                try:
                    # "Modules scanned: 338 | Imports: 867 | Findings: 68 (HARD=3)"
                    parts = line.split("|")
                    modules = int(
                        parts[0].split(":")[1].strip())
                    imports = int(
                        parts[1].split(":")[1].strip())
                    if "HARD=" in line:
                        hard = int(
                            line.split("HARD=")[1].split(")")[0])
                except (ValueError, IndexError):
                    pass
        return {
            "ok": stable and r.returncode == 0,
            "stable": stable,
            "modules": modules, "imports": imports,
            "hard": hard,
            "raw_output": raw,
            "returncode": r.returncode,
            "ran_at": datetime.now().isoformat()}


    @st.cache_data(ttl=60)
    def run_engine_self_tests() -> Dict[str, object]:
        """Run scripts/run_engine_self_tests.py --json and return summary."""
        try:
            r = subprocess.run(
                [sys.executable,
                 "scripts/run_engine_self_tests.py", "--json"],
                cwd=REPO_ROOT, capture_output=True, text=True,
                timeout=600)
        except subprocess.TimeoutExpired:
            return {
                "ok": False, "total": 0,
                "passed": 0, "failed": 0, "skipped": 0,
                "raw_output": "TIMEOUT after 600s",
                "results": [],
                "ran_at": datetime.now().isoformat()}
        raw = r.stdout or ""
        summary: Dict[str, object] = {
            "ok": False,
            "total": 0, "passed": 0, "failed": 0, "skipped": 0,
            "results": [],
            "raw_output": (r.stdout or "") + "\n" + (r.stderr or ""),
            "returncode": r.returncode,
            "ran_at": datetime.now().isoformat()}
        try:
            data = json.loads(raw)
            summary.update(data)
            summary["ok"] = (
                r.returncode == 0 and data.get("failed", 1) == 0)
        except (json.JSONDecodeError, ValueError):
            pass
        return summary


    def _status_metric(label: str, ok: bool, value: str) -> None:
        """Render a metric with color-coded status emoji."""
        icon = "🟢" if ok else "🔴"
        st.metric(label, f"{icon}  {value}")


    # ───── Tabs ────────────────────────────────────────────────────────────
    tab_overview, tab_audit, tab_structure, tab_engines, \
        tab_standards, tab_scenarios = st.tabs([
            "Overview",
            "Audit gates",
            "Structural integrity",
            "Engine self-tests",
            "Standards inventory",
            "Scenarios inventory",
        ])

    # ───── Overview ────────────────────────────────────────────────────────
    with tab_overview:
        st.subheader("Platform health summary")
        with st.spinner("Running 3 health checks..."):
            audit_r = run_audit()
            structure_r = run_structure_audit()
            engines_r = run_engine_self_tests()

        col1, col2, col3 = st.columns(3)
        with col1:
            _status_metric(
                "Audit gates",
                audit_r["ok"],
                audit_r["score"])
        with col2:
            _status_metric(
                "Structural integrity",
                structure_r["ok"],
                "STABLE" if structure_r["stable"] else "DRIFT")
        with col3:
            _status_metric(
                "Engine self-tests",
                engines_r["ok"],
                f"{engines_r['passed']}/{engines_r['total']}")

        overall_ok = (
            audit_r["ok"]
            and structure_r["ok"]
            and engines_r["ok"])
        st.markdown("---")
        if overall_ok:
            st.success(
                "**All systems green.** Platform is in a known-good "
                "state. Last checked: "
                f"{datetime.now().strftime('%H:%M:%S')}")
        else:
            st.error(
                "**Attention required.** One or more checks failed. "
                "See the per-tab detail below for diagnosis.")

        st.caption(
            "Per Rule 7, this page surfaces health state only — it "
            "never auto-fixes, never restarts services, never modifies "
            "the registry. If a check is red, the operator investigates "
            "via the per-tab raw output and applies a remediation drop.")

    # ───── Audit gates ─────────────────────────────────────────────────────
    with tab_audit:
        st.subheader("🔒 Audit gates (`scripts/audit.py`)")
        audit_r = run_audit()
        col1, col2, col3 = st.columns(3)
        with col1:
            _status_metric(
                "Result",
                audit_r["ok"],
                "PASS" if audit_r["ok"] else "FAIL")
        with col2:
            st.metric("Gates passed", str(audit_r["passed"]))
        with col3:
            st.metric("Gates total", str(audit_r["total"]))

        st.caption(
            f"Last run: {audit_r['ran_at'][:19].replace('T', ' ')} · "
            f"return code {audit_r.get('returncode', 'n/a')}")

        with st.expander(
            "Raw audit output (click to expand)",
            expanded=not audit_r["ok"],
        ):
            st.code(audit_r["raw_output"], language="text")

    # ───── Structural integrity ────────────────────────────────────────────
    with tab_structure:
        st.subheader("🧱 Structural integrity (`scripts/structure_audit.py`)")
        sa = run_structure_audit()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _status_metric(
                "Status",
                sa["ok"],
                "STABLE" if sa["stable"] else "DRIFT")
        with col2:
            st.metric("Modules scanned", str(sa.get("modules", 0)))
        with col3:
            st.metric("Imports analyzed", str(sa.get("imports", 0)))
        with col4:
            st.metric("HARD findings", str(sa.get("hard", 0)))

        st.caption(
            f"Last run: {sa['ran_at'][:19].replace('T', ' ')} · "
            f"return code {sa.get('returncode', 'n/a')}")

        with st.expander(
            "Raw structure audit output (click to expand)",
            expanded=not sa["ok"],
        ):
            st.code(sa["raw_output"], language="text")

    # ───── Engine self-tests ───────────────────────────────────────────────
    with tab_engines:
        st.subheader(
            "⚙️ Engine self-tests "
            "(`scripts/run_engine_self_tests.py`)")
        er = run_engine_self_tests()
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            _status_metric(
                "Status",
                er["ok"],
                "PASS" if er["ok"] else "FAIL")
        with col2:
            st.metric("Engines passed", str(er["passed"]))
        with col3:
            st.metric("Engines failed", str(er["failed"]))
        with col4:
            st.metric("Engines total", str(er["total"]))

        st.caption(
            f"Last run: {er['ran_at'][:19].replace('T', ' ')} · "
            f"return code {er.get('returncode', 'n/a')}")

        if er.get("results"):
            # Sort: failures first, then by name
            results_sorted = sorted(
                er["results"],
                key=lambda r: (r["status"] != "failed", r["engine"]))
            st.markdown("**Per-engine results:**")
            # Render in 2 columns to keep page compact
            col_a, col_b = st.columns(2)
            for i, r in enumerate(results_sorted):
                target = col_a if i % 2 == 0 else col_b
                icon = (
                    "🟢" if r["status"] == "passed"
                    else "🔴" if r["status"] == "failed"
                    else "⚪")
                target.write(
                    f"{icon} `{r['engine']}` "
                    f"({r['duration_seconds']}s)")
                if r["status"] == "failed":
                    target.warning(
                        f"  detail: {r.get('detail', '')}")

        with st.expander(
            "Raw orchestrator output (click to expand)",
            expanded=not er["ok"],
        ):
            st.code(er.get("raw_output", ""), language="text")

    # ───── Standards inventory ─────────────────────────────────────────────
    with tab_standards:
        st.subheader("📋 Standards inventory")
        try:
            from utils.standards_registry import STANDARDS_REGISTRY
            total = len(STANDARDS_REGISTRY)
            active = [
                s for s in STANDARDS_REGISTRY if s.status == "active"]
            planned = [
                s for s in STANDARDS_REGISTRY if s.status == "planned"]

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total standards", str(total))
            with col2:
                st.metric("Active", str(len(active)))
            with col3:
                st.metric("Planned", str(len(planned)))

            # Breakdown by subcategory
            from collections import Counter
            sub_active = Counter(s.subcategory for s in active)
            sub_planned = Counter(s.subcategory for s in planned)
            all_subs = sorted(
                set(sub_active) | set(sub_planned))
            st.markdown("**Per-subcategory breakdown:**")
            rows = []
            for sub in all_subs:
                rows.append({
                    "Subcategory": sub,
                    "Active": sub_active.get(sub, 0),
                    "Planned": sub_planned.get(sub, 0),
                    "Total": (
                        sub_active.get(sub, 0)
                        + sub_planned.get(sub, 0)),
                })
            import pandas as pd
            df = pd.DataFrame(rows).sort_values(
                "Total", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # By priority tier
            tier_counts = Counter(
                s.priority_tier for s in STANDARDS_REGISTRY)
            st.markdown("**By priority tier:**")
            st.write(dict(sorted(tier_counts.items())))
        except ImportError as e:
            st.error(f"Could not load standards_registry: {e}")

    # ───── Scenarios inventory ─────────────────────────────────────────────
    with tab_scenarios:
        st.subheader("🎬 Scenarios inventory")
        try:
            from utils.scenario_simulator import (
                TREASURY_SCENARIO_LIBRARY)
            total = len(TREASURY_SCENARIO_LIBRARY)
            st.metric("Total scenarios", str(total))

            from collections import Counter
            cat_counts = Counter(
                s.category.value for s in TREASURY_SCENARIO_LIBRARY)
            st.markdown("**By category:**")
            st.write(dict(cat_counts))

            # Group by scenario_id prefix to show arc coverage
            prefix_counts = Counter()
            for s in TREASURY_SCENARIO_LIBRARY:
                prefix = s.scenario_id.split("-", 1)[0]
                prefix_counts[prefix] += 1
            st.markdown("**By scenario family (prefix):**")
            rows = [
                {"Prefix": k, "Count": v}
                for k, v in sorted(
                    prefix_counts.items(),
                    key=lambda x: (-x[1], x[0]))]
            import pandas as pd
            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, hide_index=True)
        except ImportError as e:
            st.error(f"Could not load scenario_simulator: {e}")

    # ───── Footer ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.caption(
        "v10.74 ops hygiene drop · health checks per Rule 7 — surfacing "
        "only · audit + structure + engines orthogonal verification "
        "stack · cached 60s for snappy navigation, refresh button "
        "above for fresh runs")

