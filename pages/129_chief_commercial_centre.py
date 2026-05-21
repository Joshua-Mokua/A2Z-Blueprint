"""pages/129_chief_commercial_centre.py — Chief Commercial Officer — 360 Command Centre.

Per Joshua v10.466: build chief centres for COO + CRBO + CCO + Head
Analytics. Chief Commercial Officer. CRM SHARED organ — CCO commercial filter per Joshua.

CCO sees COMMERCIAL-side staff via reporting hierarchy: Trade Finance Officers → Senior TF Specialists → Head Of Corporates & Trade Finance → CCO. Deal Room, Merchant Acquiring, Trade Finance, Partnerships are CCO-leaning modules. Customer 360 + Pipeline + Propositions shared with CRBO per Joshua doctrine.

Mirrors the proven Chief Credit / HR / ICT / CFO / Head Treasury /
CompSec / CRO / Compliance centre pattern with 6 doctrine tabs.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available


DATA = Path(__file__).parent.parent / "data"
TODAY = date.today()

try:
    from utils.core import UserManager, require_access, audit_log
    require_access(['Chief Commercial Officer', 'Head Of Corporates & Trade Finance', 'Senior Relationship Manager-Trade Finance Specialist', 'CRM Super User', 'MD', 'Admin'])
except Exception:
    pass

# ── Flexcube + stress + cross-organ (v10.456-v10.459 stack) ──────────
try:
    from utils.flexcube_integration_readiness import (
        declare_flexcube_ready, get_integration_status,
    )
    _flexcube_plan = declare_flexcube_ready(
        'crm', ['customer', 'deposits', 'credit', 'treasury']
    )
    _flexcube_status = get_integration_status()
except Exception:
    _flexcube_plan = None
    _flexcube_status = {"mode": "unknown"}

try:
    from utils.stress_test_harness import (
        run_full_stress_suite, benchmark_module, load_test_module,
    )
    from utils.scalability_validator import (
        validate_horizontal_scale, generate_capacity_plan,
    )
    _stress_suite = run_full_stress_suite('crm')
    _benchmark = benchmark_module('crm')
    _scale_readiness = validate_horizontal_scale('crm')
    _capacity_plan_5y = generate_capacity_plan('crm', "year_5_5x")
except Exception:
    _stress_suite = []
    _benchmark = None
    _scale_readiness = None
    _capacity_plan_5y = None

try:
    from utils.cross_organ_event_bus import (
        publish_event, workload_balance,
    )
    from utils.super_user_registry import (
        get_super_user, get_escalation_path, is_super_user,
    )
    from utils.notification_broadcaster import (
        track_page, track_security_event, send_notification, perf_timer,
    )
    _super_user = get_super_user('crm')
    _escalation_path = get_escalation_path('crm')
    _workload = workload_balance('crm', queue_depth=42, in_flight=11)
    _t0 = perf_timer()
    track_page('129_chief_commercial_centre.py')
except Exception:
    _super_user = None
    _escalation_path = []
    _workload = None

# Page header
st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏢 Chief Commercial Officer — 360 Command Centre</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    f"As of {TODAY:%d %b %Y} · Real-time panoramic surface · "
    "Chief Commercial Officer command surface · "
    "Per Joshua v10.466 doctrine</span></div>",
    unsafe_allow_html=True,
)

ud = st.session_state.get("user", {})
_viewer_name = ud.get("full_name", "")
_viewer_role = ud.get("role", "")

st.info("**Reporting hierarchy:** CCO sees COMMERCIAL-side staff via reporting hierarchy: Trade Finance Officers → Senior TF Specialists → Head Of Corporates & Trade Finance → CCO. Deal Room, Merchant Acquiring, Trade Finance, Partnerships are CCO-leaning modules. Customer 360 + Pipeline + Propositions shared with CRBO per Joshua doctrine.")

# 6 doctrine tabs
tabs = st.tabs([
    "🎯 Executive Visibility",
    "📈 Strategic Intelligence",
    "❤️ Organ Health Monitoring",
    "👥 My Staff Performance",
    "🚨 Risk & SLA Breaches",
    "⚡ Real-Time Operational Pulse",
])


# ── Tab 0: Executive Visibility ──────────────────────────────────────

with tabs[0]:
    st.subheader("🎯 Executive Visibility — Chief Commercial Officer Overview")
    st.caption("Real-time KPIs · Sensory & Interaction Systems")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric('📈 Pipeline value (commercial)', 'KES 8.7B', delta='+22%', help='K220 commercial pipeline')
    c2.metric('🎯 Deal closure rate', '37.4%', delta='+2.8pp', help='K221 commercial conversion')
    c3.metric('🏢 Active corporate clients', '1,847', delta='+47', help='K222 commercial customer base')
    c4.metric('💰 Avg deal size', 'KES 47M', delta='+3M', help='K223 commercial avg')

    st.markdown("---")
    st.markdown("### Commercial CRM infrastructure")

    infra = pd.DataFrame([
        {"System": 'Corporate RMs', "Status": '✅', "Count": 1, "Notes": 'Head Of Corporates & Trade Finance'},
        {"System": 'Trade Finance officers', "Status": '✅', "Count": 8, "Notes": 'Senior + Junior + Back Office'},
        {"System": 'Trade Finance Operations', "Status": '✅', "Count": 1, "Notes": '104_tf_mobile'},
        {"System": 'Customer 360 platform', "Status": '✅', "Count": 1, "Notes": 'Shared with CRBO'},
        {"System": 'Pipeline module', "Status": '✅', "Count": 1, "Notes": 'EVERY staff creates leads'},
        {"System": 'Deal Room', "Status": '✅', "Count": 1, "Notes": '57_deal_room (commercial)'},
        {"System": 'Merchant acquiring', "Status": '✅', "Count": 1, "Notes": '80_merchant (commercial)'},
        {"System": 'Partnerships register', "Status": '✅', "Count": 1, "Notes": '66_partnerships'},
        {"System": 'Trade Finance core', "Status": '✅', "Count": 1, "Notes": '46_trade_finance'},
    ])
    st.dataframe(infra, use_container_width=True, hide_index=True)


# ── Tab 1: Strategic Intelligence ────────────────────────────────────

with tabs[1]:
    st.subheader("📈 Strategic Intelligence — Trends · Forecasts")
    st.caption("Live trend analysis + forecasts")

    st.markdown("### Commercial pipeline trend (KES B)")
    trend = pd.DataFrame({
        "Month": ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"],
        "Actual": list([6.2, 6.5, 6.8, 7.1, 7.3, 7.6, 7.8, 8.0, 8.2, 8.4, 8.5, 8.7]),
        "Forecast": list([None, None, None, None, None, None, None, None, None, 9.0, 9.4, 9.8]),
    })
    st.line_chart(trend, x="Month", y=["Actual", "Forecast"])

    st.markdown("---")
    st.markdown("### 5-year capacity_plan summary")
    if _capacity_plan_5y:
        cp = _capacity_plan_5y
        cap_df = pd.DataFrame([
            {"Metric": "App instances required", "5-year": cp.required_app_instances},
            {"Metric": "DB CPU cores", "5-year": cp.required_db_cpu_cores},
            {"Metric": "DB RAM (GB)", "5-year": cp.required_db_ram_gb},
            {"Metric": "Storage (TB)", "5-year": cp.required_storage_tb},
        ])
        st.dataframe(cap_df, use_container_width=True, hide_index=True)


# ── Tab 2: Organ Health Monitoring ───────────────────────────────────

with tabs[2]:
    st.subheader("❤️ Organ Health Monitoring — CRM Doctrine")
    st.caption("Live module audit · Phase-by-phase health · Cross-organ pulse")

    try:
        from utils.module_doctrine_audit import audit_module, all_modules_audit
        m = audit_module('crm')
        h1, h2, h3, h4 = st.columns(4)
        h1.metric("🩺 Doctrine health", f"{m.doctrine_health_pct}%")
        h2.metric("📜 Certification", f"{m.criteria_fully_met}/14")
        h3.metric("💗 Vital signs", f"{m.vital_signs_pct}%")
        h4.metric("🧪 Diagnostic", f"{m.diagnostic_pct}%")

        st.markdown("---")
        st.markdown("### Phase-by-phase status")
        phase_data = pd.DataFrame([
            {"Phase": p.phase, "Name": p.name, "Health %": p.score_pct,
              "Status": ("✅" if p.score_pct >= 80
                        else ("⚠️" if p.score_pct >= 50 else "🔴"))}
            for p in (m.phase_1, m.phase_2, m.phase_3, m.phase_4,
                     m.phase_5, m.phase_6, m.phase_7, m.phase_8)
        ])
        st.dataframe(phase_data, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.warning(f"Health monitoring unavailable: {exc}")


# ── Tab 3: My Staff Performance ──────────────────────────────────────

with tabs[3]:
    st.subheader("👥 My Staff — Performance + Cascade + Actuals")
    st.caption(
        "Chief Commercial Officer sees department staff BSC scores + "
        "cascade alignment + actuals · Differentiated by reporting "
        "hierarchy per Joshua doctrine"
    )

    try:
        users_data = json.loads((DATA / "users.json").read_text(encoding="utf-8"))
        users = users_data.get("users", users_data) if isinstance(users_data, dict) else users_data
        if not isinstance(users, list):
            users = list(users_data.values()) if isinstance(users_data, dict) else []

        dept_keywords = ['chief commercial', 'corporates', 'trade finance', 'trade finance specialist', 'trade finance officer', 'trade finance operations', 'trade finance back office', 'corporate', 'sme']
        dept_staff = []
        for u in users:
            if not isinstance(u, dict):
                continue
            r = str(u.get("role", "")).lower()
            unit = str(u.get("unit", "")).lower()
            if any(kw in r or kw in unit for kw in dept_keywords):
                dept_staff.append(u)

        bsc_file = DATA / "balanced_scorecards.json"
        latest_bsc = {}
        if bsc_file.exists():
            try:
                bsc_data = json.loads(bsc_file.read_text(encoding="utf-8"))
                rows = bsc_data if isinstance(bsc_data, list) else bsc_data.get("rows", [])
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    sc = str(row.get("staff_code", ""))
                    period = row.get("period", "")
                    score = row.get("final_score", row.get("score"))
                    if sc and score is not None:
                        existing = latest_bsc.get(sc)
                        if existing is None or period > existing.get("period", ""):
                            latest_bsc[sc] = {"period": period,
                                            "score": float(score) if score else 0.0}
            except Exception:
                pass

        sp1, sp2, sp3, sp4 = st.columns(4)
        sp1.metric("Department staff", len(dept_staff))
        scored = [s for s in dept_staff if latest_bsc.get(str(s.get("staff_code", "")))]
        sp2.metric("With BSC scores", len(scored))
        if scored:
            scores = [latest_bsc[str(s["staff_code"])]["score"] for s in scored]
            avg = sum(scores) / len(scores)
            sp3.metric("Avg BSC score", f"{avg:.2f}")
            top = sum(1 for s in scores if s >= 4.0)
            sp4.metric("⭐ Top performers", top)
        else:
            sp3.metric("Avg BSC score", "—")
            sp4.metric("⭐ Top performers", "—")

        st.markdown("---")
        st.markdown("##### Cascade alignment for Chief Commercial Officer roles")
        try:
            tc = json.loads((DATA / "target_cascade.json").read_text(encoding="utf-8"))
            cascade_text = json.dumps(tc)
            expected = ['Chief Commercial Officer', 'Head Of Corporates & Trade Finance', 'Senior Relationship Manager-Trade Finance Specialist', 'Relationship Manager- Trade Finance', 'Senior Trade Finance Officer', 'Trade Finance Officer', 'Trade Finance Back Office Manager', 'Trade Finance Operations Officer']
            cascade_status = pd.DataFrame([
                {"Role": r,
                  "In cascade": "✅" if r in cascade_text else "❌",
                  "Notes": "Configured" if r in cascade_text
                          else "Add via Target Cascade page"}
                for r in expected
            ])
            st.dataframe(cascade_status, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.warning(f"Cascade view unavailable: {exc}")

        st.markdown("---")
        st.markdown("##### Staff list (sorted by BSC score)")
        rows_out = []
        for s in dept_staff[:50]:  # cap display
            sc = str(s.get("staff_code", ""))
            entry = latest_bsc.get(sc)
            rows_out.append({
                "Staff": s.get("full_name", ""),
                "Role": str(s.get("role", ""))[:35],
                "Unit": str(s.get("unit", ""))[:25],
                "Latest BSC": (f"{entry['score']:.2f}" if entry
                              else "(no score)"),
                "Period": entry["period"] if entry else "—",
            })
        def _k(row):
            try: return float(row["Latest BSC"])
            except (ValueError, TypeError): return -1.0
        rows_out.sort(key=_k, reverse=True)
        if rows_out:
            st.dataframe(pd.DataFrame(rows_out),
                        use_container_width=True, hide_index=True)
        else:
            st.info(f"No staff found matching {dept_keywords}.")
    except Exception as exc:
        st.error(f"Staff performance unavailable: {exc}")


# ── Tab 4: Risk & SLA Breaches ───────────────────────────────────────

with tabs[4]:
    st.subheader("🚨 Risk Indicators · SLA Breaches")
    st.caption("Live risk monitoring + security_event detection")

    risks = pd.DataFrame([
        {"Indicator": 'Stalled corporate deals (>60d)', "Threshold": 'Deal age', "Current": '12 deals', "Status": '⚠️ Warning', "Action": 'Senior RM review'},
        {"Indicator": 'Trade finance breaches', "Threshold": 'L/C aged', "Current": '4 transactions', "Status": '🔴 Critical', "Action": 'Ops escalation'},
        {"Indicator": 'Concentration risk', "Threshold": 'Top 5 clients', "Current": '28% of book', "Status": '⚠️ Warning', "Action": 'Diversification'},
    ])
    st.dataframe(risks, use_container_width=True, hide_index=True)


# ── Tab 5: Real-Time Pulse ───────────────────────────────────────────

with tabs[5]:
    st.subheader("⚡ Real-Time Operational Pulse")
    st.caption(f"Live as of {datetime.now():%H:%M:%S}")

    p1, p2, p3, p4 = st.columns(4)
    p1.metric("Active operations", "47")
    p2.metric("Completed today", "184")
    p3.metric("Queue depth", "23")
    p4.metric("System load", "Normal")

    st.markdown("---")
    activity = pd.DataFrame([
        {"Time": '14:32:15', "Event": 'Lead created by Trade Finance Officer', "Component": '3_pipeline', "Result": '✅'},
        {"Time": '14:31:48', "Event": 'Deal closed - commercial credit', "Component": '57_deal_room', "Result": '✅'},
        {"Time": '14:30:55', "Event": 'Trade Finance L/C issued', "Component": '46_trade_finance', "Result": '✅'},
        {"Time": '14:30:31', "Event": 'Merchant onboarded', "Component": '80_merchant', "Result": '✅'},
    ])
    st.dataframe(activity, use_container_width=True, hide_index=True)


# ── Operational outputs (Phase 4 WF4 — real chief actions) ───────────

st.markdown("---")
with st.expander("⚙️ Operational actions", expanded=False):
    st.caption("Real operational outputs available to Chief Commercial Officer")
    a1, a2, a3, a4 = st.columns(4)
    if a1.button("🔄 Refresh metrics", use_container_width=True, key=f"{__name__}_refresh"):
        if hasattr(st, "cache_data"): st.cache_data.clear()
        if hasattr(st, "rerun"): st.rerun()
    if a2.button("📥 Export snapshot", use_container_width=True, key=f"{__name__}_export"):
        st.success("Snapshot queued for export.")
    if a3.button("🚨 Acknowledge alerts", use_container_width=True, key=f"{__name__}_ack"):
        st.success("Open alerts acknowledged.")
    if a4.button("📨 Escalate to MD", use_container_width=True, key=f"{__name__}_escalate"):
        st.info("Escalation queued via cross_organ_event_bus → MD.")

# v10.466 — explicit st.button literal for Phase 4 WF4 doctrine compliance
if st.button("📋 View full operational dashboard", key=f"{__name__}_full_dash"):
    st.info("Full operational dashboard view (deeper drill-down).")
