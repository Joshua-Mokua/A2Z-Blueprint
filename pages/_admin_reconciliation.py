"""pages/_admin_reconciliation.py — Reconciliation Centre.

Admin tab showing the daily A2Z vs FLEXCUBE reconciliation framework.

Tabs within this section:
  • Dashboard — summary metrics, recent runs, open breaks
  • Run checks — manual trigger
  • Open breaks — investigate/resolve
  • Schema — table definitions for reference

Per master prompt: "Ensure data integrity, validation, and reconciliation."
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import datetime, timedelta
from utils.core_audit import audit_log
from utils.db import db
from utils import reconciliation as recon

DATA = Path(__file__).parent.parent / "data"


def render_recon_centre(tab, uname: str, is_admin: bool):
    """Render the Reconciliation Centre tab."""
    with tab:
        if not is_admin:
            st.warning("🔒 Reconciliation Centre is admin-only.")
            return

        st.markdown(
            "<div style='padding:16px 0 4px'>"
            "<span style='font-size:22px;font-weight:800'>🔍 Reconciliation Centre</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Daily A2Z ↔ FLEXCUBE checks · Per master prompt requirement</span></div>",
            unsafe_allow_html=True,
        )

        # ── Summary metrics ──────────────────────────────────────
        try:
            summary = recon.get_summary()
        except Exception as e:
            st.error(f"Reconciliation engine error: {e}")
            return

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Checks registered", summary.get("checks_registered", 0))
        m2.metric("Runs in last 7d",   summary.get("total_runs_7d", 0))
        m3.metric("Match rate",        f"{summary.get('match_rate_pct', 0)}%",
                  delta_color="off" if summary.get("match_rate_pct", 0) >= 95 else "inverse")
        m4.metric("Breaks in 30d",     summary.get("breaks_30d", 0))
        m5.metric("OPEN critical",     summary.get("critical_open_breaks", 0),
                  delta_color="inverse" if summary.get("critical_open_breaks", 0) > 0 else "off")

        if summary.get("critical_open_breaks", 0) > 0:
            st.error(f"🔴 {summary['critical_open_breaks']} CRITICAL break(s) open — escalate to CFO/CRO immediately")

        st.markdown("---")

        sub_tabs = st.tabs([
            "📊 Dashboard",
            "▶️ Run Checks",
            "🔴 Open Breaks",
            "📜 Schema",
        ])

        # ── Tab 0: Dashboard ─────────────────────────────────────
        with sub_tabs[0]:
            st.markdown("**Recent reconciliation runs:**")
            runs = recon.list_recent_runs(days=7, limit=50)
            if not runs:
                st.info("No recent runs. Click '▶️ Run Checks' to trigger reconciliation.")
            else:
                rows = []
                for r in runs:
                    ts = r.get("run_ts", "")[:19] if r.get("run_ts") else "—"
                    status = r.get("status", "")
                    icon = {"MATCH":"🟢", "WARN":"🟡", "BREAK":"🔴"}.get(status, "")
                    rows.append({
                        "When":      ts,
                        "Check":     r.get("check_name", ""),
                        "Category":  r.get("check_category", ""),
                        "A2Z":       f"{r.get('a2z_value', 0):,.2f}",
                        "FLEXCUBE":  f"{r.get('flexcube_value', 0):,.2f}",
                        "Variance":  f"{r.get('variance_pct', 0):.2f}%",
                        "Status":    f"{icon} {status}",
                        "Duration":  f"{r.get('duration_ms', 0)}ms",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # Quick history chart by status
            if runs:
                from collections import Counter
                status_counts = Counter(r.get("status", "") for r in runs)
                st.markdown("**Status distribution (last 7 days):**")
                st.bar_chart(pd.DataFrame({"Count": dict(status_counts)}))

        # ── Tab 1: Run Checks ────────────────────────────────────
        with sub_tabs[1]:
            st.markdown("**Available reconciliation checks:**")
            check_meta = [
                ("total_deposits",    "DEPOSITS", "A2Z BSC sum vs FLEXCUBE GL deposit accounts"),
                ("total_loans",       "LOANS",    "A2Z credit_monitoring vs FLEXCUBE loan portfolio"),
                ("npl_ratio",         "NPL",      "A2Z NPL% vs FLEXCUBE classification roll-up"),
                ("lcr_ratio",         "CAPITAL",  "A2Z LCR snapshot vs CBK 100% minimum"),
                ("capital_adequacy",  "CAPITAL",  "A2Z CAR vs CBK 14.5% minimum"),
            ]
            for name, cat, desc in check_meta:
                st.markdown(f"  • **{name}** ({cat}) — {desc}")

            st.markdown("---")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("▶️ Run all checks now", key="recon_run_all", type="primary"):
                    with st.spinner("Running reconciliation checks..."):
                        results = recon.run_all_checks(triggered_by=uname)
                    audit_log("RECON_RUN_ALL", uname, f"{len(results)} checks executed")
                    breaks   = sum(1 for r in results if r.status == "BREAK")
                    matches  = sum(1 for r in results if r.status == "MATCH")
                    if breaks > 0:
                        st.error(f"⚠️ {breaks} break(s) detected, {matches} matched")
                    else:
                        st.success(f"✅ All {len(results)} checks passed")
                    st.rerun()
            with c2:
                st.caption("Reconciliation runs append-only to `audit.recon_runs`.")
                st.caption("Breaks (variance > tolerance) are logged to `audit.recon_breaks` for follow-up.")

        # ── Tab 2: Open Breaks ───────────────────────────────────
        with sub_tabs[2]:
            breaks = recon.list_recent_breaks(days=30, status="OPEN")
            if not breaks:
                st.success("✅ No open reconciliation breaks. Last 30 days clean.")
            else:
                st.warning(f"⚠️ {len(breaks)} open break(s) need investigation")
                for i, b in enumerate(breaks[:25]):
                    sev = b.get("severity", "MEDIUM")
                    sev_icon = {"CRITICAL":"🔴", "HIGH":"🟠", "MEDIUM":"🟡", "LOW":"🟢"}.get(sev, "")
                    with st.expander(f"{sev_icon} {b.get('check_name', '?')} — {sev} — {b.get('break_ts', '')[:10]}"):
                        cc1, cc2, cc3 = st.columns(3)
                        cc1.metric("A2Z value",      f"{b.get('a2z_value', 0):,.2f}")
                        cc2.metric("FLEXCUBE value", f"{b.get('flexcube_value', 0):,.2f}")
                        cc3.metric("Variance",       f"{b.get('variance_pct', 0):.2f}%",
                                   delta_color="inverse")
                        st.caption(f"Category: {b.get('check_category', '')} | Status: {b.get('status', 'OPEN')}")

        # ── Tab 3: Schema ────────────────────────────────────────
        with sub_tabs[3]:
            st.markdown("**Reconciliation tables (in `audit` schema):**")
            st.code("""-- audit.recon_runs : every check execution (append-only)
-- audit.recon_breaks : breaks where variance > tolerance

SELECT * FROM audit.recon_runs
WHERE run_ts >= now() - interval '7 days'
ORDER BY run_ts DESC;

SELECT * FROM audit.recon_breaks WHERE status = 'OPEN';""", language="sql")

            st.markdown("**Tolerance strategy:**")
            st.markdown("""
            - **Absolute:** KES 1,000 default for sums (rounding noise)
            - **Relative:** 0.1pp default for ratios (NPL, LCR)
            - **Tighter:** 0.05pp for capital ratios (CAR, NSFR)
            - **MATCH:** within tolerance → no break logged
            - **WARN:** exceeds tolerance but ≤ 2× → logged, no break
            - **BREAK:** > 2× tolerance → break logged, severity computed by % variance
            """)

            st.caption("Override per check: edit `tolerance_kes` and `tolerance_pct` in `utils/reconciliation.py` CHECK_REGISTRY.")
