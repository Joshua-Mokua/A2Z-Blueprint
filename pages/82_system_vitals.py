"""pages/82_system_vitals.py — System Vital Signs Dashboard (v10.444).

PER JOSHUA OPERATING MANTRA:
    "Rescue the body 100% and prevent it ever falling apart. Are there
    things we are adding that could affect them again and are we
    mitigating against any deterioration of what we have worked hard
    to rescue?"

Continuous body-wide health monitoring across rescued modules:
  - BSC (v10.424-v10.429 rescue)
  - Cascade-BSC 360 (v10.432-v10.433)
  - HR Section (v10.436-v10.443)
  - Standards Wiring (v10.439)
  - Engine State (G119 baseline)

Plus blood-circulation checks for data flow between organs, regression
sentinels comparing current state to baselines, and end-to-end
information flow tracing for a sample staff.

Department: admin. Access key: "admin.system_vitals".
"""
import json
import time
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available


from pages._access import require_access
from pages._shared import load_shared_state
from utils.core_audit import audit_log

require_access("admin.system_vitals")

DATA = Path(__file__).parent.parent / "data"
TODAY = date.today()

um, ud, uname, *_ = load_shared_state()[:12]
role = str(ud.get("role", "")).lower()
is_admin = ud.get("is_admin", False)

audit_log(
    action="system_vitals.view",
    username=uname,
    detail=f"role={role} is_admin={is_admin}",
    module="system_vitals",
)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🫀 System Vital Signs</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Body-wide health · Blood circulation · Regression sentinels · "
    "Information flow</span></div>",
    unsafe_allow_html=True,
)

st.caption(
    "**Operating mantra (Joshua, v10.444):** *Rescue the body 100% and "
    "prevent it ever falling apart.* This page runs the same checks "
    "the audit gate G330 runs on every batch — surfaces any "
    "deterioration of previously-rescued work before it spreads."
)

# Performance warning
st.info(
    "💡 Full vitals check runs 5 full audits + 6 flow checks + sentinel "
    "comparisons. Expect ~30-60 seconds. Results cached for 5 minutes."
)

try:
    from utils.system_vitals_engine import full_body_vitals
except Exception as exc:  # noqa: BLE001
    st.error(f"System vitals engine unavailable: {exc}")
    st.stop()


@st.cache_data(ttl=300, show_spinner="Running full body vitals (~30-60s)...")
def _run_vitals(sample_staff):
    return full_body_vitals(sample_staff).to_dict()


col_left, col_right = st.columns([3, 1])
sample_code = col_left.text_input(
    "Sample staff code for information flow trace",
    value="300001",
    key="vitals_sample",
)
if col_right.button("🔄 Run vitals", key="run_vitals_btn"):
    _run_vitals.clear()

vitals = _run_vitals(sample_code)

# ────────────────────────────────────────────────────────────────
# Header — overall status
# ────────────────────────────────────────────────────────────────

status_color = {
    "healthy":  "✅",
    "degraded": "🟠",
    "critical": "🔴",
}.get(vitals["overall_status"], "⚪")

st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Body Health",
          f"{vitals['body_health_pct']}%",
          delta=f"{status_color} {vitals['overall_status'].upper()}")
c2.metric("Healthy Organs",
          f"{len([o for o in vitals['organ_vitals']['organs'] if o['healthy']])}/"
          f"{len(vitals['organ_vitals']['organs'])}")
c3.metric("Circulation",
          f"{vitals['circulation']['avg_circulation_pct']}%")
c4.metric("Regressions",
          vitals['regression']['critical_count'] + vitals['regression']['high_count'])

# Actionable alerts
if vitals.get("actionable_alerts"):
    st.markdown("**🚨 Actionable Alerts:**")
    for a in vitals["actionable_alerts"]:
        if "CRITICAL" in a:
            st.error(a)
        elif "🟠" in a:
            st.warning(a)
        else:
            st.info(a)

st.divider()

tabs = st.tabs([
    "🫀 Organ Vitals",
    "🩸 Blood Circulation",
    "🚨 Regression Sentinels",
    "🔄 Information Flow",
    "📊 History",
])


# ────────────────────────────────────────────────────────────────
# Tab 0: Organ Vitals
# ────────────────────────────────────────────────────────────────
with tabs[0]:
    st.subheader("🫀 Per-Module Health Metrics")
    st.caption("Each rescued module's current health vs the baseline we worked to achieve.")

    organs = vitals["organ_vitals"]["organs"]
    rows = []
    for o in organs:
        icon = "✅" if o["healthy"] else "🔴"
        delta = o["delta_from_baseline"]
        rows.append({
            "Status": icon,
            "Organ": o["organ"],
            "Metric": o["metric_name"],
            "Current": f"{o['current_value']:.2f}",
            "Baseline": f"{o['baseline_value']:.2f}",
            "Δ Baseline": f"{delta:+.2f}",
            "Notes": o["notes"],
        })
    st.dataframe(pd.DataFrame(rows),
                use_container_width=True, hide_index=True)


# ────────────────────────────────────────────────────────────────
# Tab 1: Blood Circulation
# ────────────────────────────────────────────────────────────────
with tabs[1]:
    st.subheader("🩸 Data Flow Between Organs")
    st.caption(
        "Linear flows = direct downstream (KPI Library → BSC). "
        "Non-linear = engine integration (HR Auto-Actuals → BSC submit)."
    )

    checks = vitals["circulation"]["checks"]
    rows = []
    for c in checks:
        icon = "✅" if c["passed"] else "🔴"
        rows.append({
            "Status": icon,
            "Flow": c["flow_name"],
            "Direction": c["direction"],
            "Coverage %": f"{c['coverage_pct']:.1f}",
            "Notes": c["notes"],
        })
    st.dataframe(pd.DataFrame(rows),
                use_container_width=True, hide_index=True)

    # Show sample failures for any failing check
    for c in checks:
        if not c["passed"] and c.get("sample_failures"):
            with st.expander(f"🔴 Sample failures: {c['flow_name']}"):
                for f in c["sample_failures"]:
                    st.code(f)


# ────────────────────────────────────────────────────────────────
# Tab 2: Regression Sentinels
# ────────────────────────────────────────────────────────────────
with tabs[2]:
    st.subheader("🚨 Regression Sentinels")
    st.caption(
        "**The mantra in action.** Each previously-rescued module has "
        "a baseline value. Any drop = regression alert. v10.444 onwards, "
        "G330 enforces these on every batch."
    )

    if vitals["regression"]["has_regression"]:
        st.error(
            f"🔴 {vitals['regression']['critical_count']} critical + "
            f"{vitals['regression']['high_count']} high regression(s) "
            f"detected. FIX before next batch."
        )
        for a in vitals["regression"]["alerts"]:
            severity_icon = {
                "critical": "🔴", "high": "🟠",
                "medium": "🟡", "low": "🟢",
            }.get(a["severity"], "⚪")
            st.warning(
                f"{severity_icon} **{a['organ']}** ({a['metric']}): "
                f"baseline {a['baseline']} → current {a['current']} "
                f"(drop {a['drop']:.2f})"
            )
            st.caption(a["message"])
    else:
        st.success(
            "✅ **No regressions detected.** All previously-rescued "
            "modules are operating at or above their post-rescue baselines."
        )
        st.markdown("**Baselines being protected:**")
        st.markdown(
            "- BSC rescue: ≥ 100% (v10.424-v10.429)\n"
            "- Cascade-BSC 360: ≥ 100% (v10.432-v10.433)\n"
            "- HR Section health: ≥ 88.7% (v10.443)\n"
            "- HR Engine wiring: 100% (v10.441)\n"
            "- HR API coverage: 100% (v10.442)\n"
            "- Standards wiring: ≥ 78.8% (v10.439)\n"
            "- Engine state critical count: 0 (G119)"
        )


# ────────────────────────────────────────────────────────────────
# Tab 3: Information Flow (end-to-end trace)
# ────────────────────────────────────────────────────────────────
with tabs[3]:
    st.subheader(f"🔄 End-to-End Information Flow")
    st.caption(
        f"Trace sample staff `{sample_code}` through the chain: "
        "register → role_kpis → BSC rows → weight sum → score computable."
    )

    flow = vitals["flow_balance"]
    for s in flow["chain_steps"]:
        icon = "✅" if s.get("passed") else "🔴"
        st.write(f"{icon} **{s.get('step', '?')}**: {s.get('detail', '')}")

    if flow["end_to_end_passed"]:
        st.success(
            f"✅ End-to-end passed for {sample_code}. The body's "
            "information flow is intact for this sample."
        )
    else:
        st.warning(
            f"⚠️ Flow broken at step: **{flow.get('failure_step', '?')}**. "
            "This indicates a specific data integrity issue for this "
            "staff — investigate before next batch."
        )

    st.caption(
        "💡 Try different staff codes — branch managers, RMs, support "
        "staff — to see if the flow holds across the org."
    )


# ────────────────────────────────────────────────────────────────
# Tab 4: History (per-batch vitals)
# ────────────────────────────────────────────────────────────────
with tabs[4]:
    st.subheader("📊 Vital Signs History")
    st.caption(
        "Each batch from v10.444+ writes a snapshot. Detect drift across "
        "batches. (History grows over time.)"
    )

    hist_dir = DATA / "_vital_signs_history"
    hist_dir.mkdir(exist_ok=True)
    history_files = sorted(hist_dir.glob("vitals_*.json"))[-20:]

    if not history_files:
        st.info(
            "No history yet — snapshots write each time vitals are "
            "checked from this page or G330. Run vitals a few times to "
            "build history."
        )
    else:
        snapshots = []
        for f in history_files:
            try:
                snap = json.loads(f.read_text())
                snapshots.append({
                    "Timestamp": snap.get("timestamp", "")[:19],
                    "Status": snap.get("overall_status", ""),
                    "Body health %": snap.get("body_health_pct", 0),
                    "Healthy organs": (
                        len([o for o in snap.get("organ_vitals", {})
                             .get("organs", []) if o.get("healthy")])
                    ),
                    "Regressions": (
                        snap.get("regression", {}).get("critical_count", 0)
                        + snap.get("regression", {}).get("high_count", 0)
                    ),
                })
            except Exception:
                pass
        if snapshots:
            df = pd.DataFrame(snapshots)
            st.dataframe(df, use_container_width=True, hide_index=True)

            # Line chart of body health over time
            if len(snapshots) > 1:
                st.line_chart(df.set_index("Timestamp")["Body health %"])

# Write current vitals as a history snapshot
try:
    hist_dir = DATA / "_vital_signs_history"
    hist_dir.mkdir(exist_ok=True)
    ts = vitals["timestamp"].replace(":", "-").replace(".", "-")[:23]
    (hist_dir / f"vitals_{ts}.json").write_text(json.dumps(vitals, indent=2))
except Exception:
    pass

# ────────────────────────────────────────────────────────────────
# Footer
# ────────────────────────────────────────────────────────────────
st.divider()
st.caption(
    "💡 G330 (audit gate) calls these same checks on every batch — "
    "any regression beyond baselines breaks the build. **This page is "
    "the heart-rate monitor that watches the body 24/7.**"
)

# v10.465 — Phase 4 WF4 operational output (admin re-homed page)
st.markdown("---")
if st.button("🔄 Refresh this view", key=f"{__name__}_refresh_v465"):
    if hasattr(st, "cache_data"):
        st.cache_data.clear()
    if hasattr(st, "rerun"):
        st.rerun()

