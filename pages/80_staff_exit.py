"""pages/80_staff_exit.py — Staff Exit Risk & Succession Planning.

Wires `staff_exit_engine` (v10.435) into a user-facing page.
Per HR Rescue Arc v10.441.

Four tabs:
  🎯 Per-Staff Exit Risk    — 5-dimension risk score for any staff
  🚨 Top Key-Person Risks   — highest exit-impact staff bank-wide
  🔄 Redistribution Plan    — simulate 3 strategies (peer_split, manager_absorb, hold_open)
  📊 Bank-Wide Exit Readiness — risk distribution + drivers
"""
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

import pandas as pd
from pathlib import Path
from pages._shared import load_shared_state
from pages._access import require_access

require_access("people_hr.exit")

DATA = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role", "")
sc = str(ud.get("staff_code", ""))
is_admin = ud.get("is_admin", False)
is_hr = any(x in role.lower() for x in (
    "human resource", "hr", "chief human", "manager", "head of"
))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚪 Staff Exit & Succession</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Key-person risk · Target gap detection · Redistribution planning</span></div>",
    unsafe_allow_html=True,
)
st.caption(
    "5-dimension risk scoring: outgoing cascade size, target value flow, "
    "role uniqueness, pillar criticality, incoming reliance. Std v10.435."
)

try:
    from utils.staff_exit_engine import (
        audit_exit_risk,
        audit_all_exit_risks,
        simulate_exit,
        simulate_redistribution,
    )
except Exception as exc:  # noqa: BLE001
    st.error(f"Exit risk engine unavailable: {exc}")
    st.stop()


# Quick metrics header
try:
    quick = audit_all_exit_risks()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Critical risk (75+)", quick.critical_risk_count)
    m2.metric("High risk (50-74)", quick.high_risk_count)
    m3.metric("Medium risk (25-49)", quick.medium_risk_count)
    m4.metric("Avg risk score", f"{quick.avg_risk_score:.1f}")
except Exception:  # noqa: BLE001
    pass

tabs = st.tabs([
    "🎯 Per-Staff Exit Risk",
    "🚨 Top Key-Person Risks",
    "🔄 Redistribution Plan",
    "📊 Bank-Wide Exit Readiness",
])

# ── Tab 0: Per-Staff Exit Risk ──────────────────────────────────
with tabs[0]:
    st.markdown("**Assess exit impact for any staff.**")
    st.caption(
        "Computes 5-dimensional risk score (0-100). Categorical bands: "
        "Critical (75+), High (50-74), Medium (25-49), Low (<25)."
    )
    sel_code = st.text_input("Staff code to assess",
                              value=sc or "300001",
                              key="exit_per_code",
                              help="Defaults to your own code")
    if st.button("Assess exit risk", key="btn_exit_assess"):
        try:
            r = audit_exit_risk(sel_code)

            level_emoji = {
                "Critical": "🔴", "High": "🟠",
                "Medium": "🟡", "Low": "🟢",
            }.get(r.risk_band, "⚪")

            c1, c2 = st.columns([1, 3])
            c1.metric("Risk score", f"{r.risk_score:.1f}",
                      delta=f"{level_emoji} {r.risk_band}")
            c2.write(f"**Staff:** {r.staff_name}")
            c2.write(f"**Role:** {r.role}")
            c2.write(f"**Unit:** {r.unit}")

            st.markdown("**Risk dimensions:**")
            d1, d2, d3, d4, d5 = st.columns(5)
            d1.metric("Outgoing cascade",
                      r.outgoing_cascade_count,
                      help="How many children depend on them")
            d2.metric("Outgoing value (KES)",
                      f"{r.outgoing_value/1e6:.0f}M",
                      help="$ flowing through their delegated targets")
            d3.metric("Role peers",
                      r.role_peer_count,
                      help="Same-role siblings in unit — fewer = more critical")
            d4.metric("Pillars at risk",
                      r.pillars_lost_count,
                      help="Pillar gaps in unit if they leave")
            d5.metric("Incoming reliance",
                      r.incoming_reliance_count,
                      help="Parents/peers pointing at them")

            if r.risk_drivers:
                st.write(f"**Drivers:** {', '.join(r.risk_drivers)}")

            if r.risk_band in ("Critical", "High"):
                st.warning(
                    f"⚠️ {r.risk_band} risk — succession plan recommended. "
                    "Use the Redistribution Plan tab to model gap-fill strategies."
                )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Assessment failed: {exc}")


# ── Tab 1: Top Key-Person Risks ─────────────────────────────────
with tabs[1]:
    st.markdown("**Bank-wide ranking — who creates the biggest gap if they exit?**")
    st.caption(
        "Sorted by composite risk score across all 5 dimensions. "
        "Top of list = priority succession planning candidates."
    )
    top_n = st.slider("How many to show", 5, 50, 20, key="exit_top_n")
    if st.button("Refresh ranking", key="btn_exit_rank"):
        try:
            full = audit_all_exit_risks()

            # Combine critical + high samples + sort by score
            samples = list(full.critical_staff) + list(full.high_staff)
            samples.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
            samples = samples[:top_n]

            if samples:
                rows = [{
                    "Code": s.get("staff_code", ""),
                    "Name": s.get("name", "")[:30],
                    "Role": s.get("role", "")[:30],
                    "Score": round(s.get("risk_score", 0), 1),
                    "Band": s.get("risk_band", ""),
                    "Outgoing cascade": s.get("outgoing_cascade_count", 0),
                    "Role peers": s.get("role_peer_count", 0),
                    "Drivers": ", ".join(s.get("risk_drivers", []))[:60],
                } for s in samples]
                st.dataframe(pd.DataFrame(rows),
                            use_container_width=True, hide_index=True)
            else:
                st.success("✅ No critical or high-risk staff identified.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Ranking failed: {exc}")


# ── Tab 2: Redistribution Plan ──────────────────────────────────
with tabs[2]:
    st.markdown("**Simulate gap-fill if a staff exits — 3 strategies.**")
    st.caption(
        "**peer_split**: split among same-role peers in unit · "
        "**manager_absorb**: push up to their manager · "
        "**hold_open**: document gap unassigned."
    )

    redist_code = st.text_input("Exiting staff code",
                                 value="300277",
                                 key="redist_code",
                                 help="Try 300277 (Branch Manager, ~50 score)")
    if st.button("Run all 3 redistribution simulations", key="btn_redist"):
        try:
            full_sim = simulate_exit(redist_code)

            r = full_sim.risk
            level_emoji = {
                "Critical": "🔴", "High": "🟠",
                "Medium": "🟡", "Low": "🟢",
            }.get(r.risk_band, "⚪")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Staff", full_sim.staff_name[:20])
            c2.metric("Risk score", f"{r.risk_score:.0f}",
                      delta=f"{level_emoji} {r.risk_band}")
            c3.metric("Recommended", full_sim.recommended_strategy)
            c4.metric("Options tested", len(full_sim.redistribution_options))

            if full_sim.redistribution_options:
                rows = [{
                    "Strategy": opt.strategy,
                    "Valid": "✓" if opt.valid else "✗",
                    "Receivers": len(opt.receivers),
                    "Feasibility %": round(opt.feasibility_pct, 1),
                    "Unassigned value (KES)": f"{opt.unassigned_value/1e6:.1f}M",
                    "Warnings": "; ".join(opt.warnings)[:60] if opt.warnings else "—",
                } for opt in full_sim.redistribution_options]
                st.dataframe(pd.DataFrame(rows),
                            use_container_width=True, hide_index=True)

                # Show receivers detail for recommended strategy
                recommended = next(
                    (o for o in full_sim.redistribution_options
                     if o.strategy == full_sim.recommended_strategy),
                    None,
                )
                if recommended and recommended.receivers:
                    with st.expander(
                        f"Receivers for recommended '{recommended.strategy}' "
                        f"({len(recommended.receivers)})",
                    ):
                        rec_rows = [{
                            "Code": r.get("code", ""),
                            "Name": r.get("name", "")[:30],
                            "Added target (KES)": f"{r.get('added_target', 0)/1e6:.1f}M",
                        } for r in recommended.receivers]
                        st.dataframe(pd.DataFrame(rec_rows),
                                    use_container_width=True, hide_index=True)
        except Exception as exc:  # noqa: BLE001
            st.error(f"Simulation failed: {exc}")


# ── Tab 3: Bank-Wide Exit Readiness ─────────────────────────────
with tabs[3]:
    st.markdown("**Bank-wide exit risk distribution + global drivers.**")
    st.caption("Read-only diagnostic. Refresh to recompute.")

    try:
        full = audit_all_exit_risks()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🔴 Critical (75+)", full.critical_risk_count)
        c2.metric("🟠 High (50-74)", full.high_risk_count)
        c3.metric("🟡 Medium (25-49)", full.medium_risk_count)
        c4.metric("🟢 Low (<25)", full.low_risk_count)

        c5, c6 = st.columns(2)
        c5.metric("Total staff", full.total_staff)
        c6.metric("Avg risk score", f"{full.avg_risk_score:.2f}")

        if full.critical_risk_count == 0:
            st.success(
                f"✅ No critical-risk staff. "
                f"{full.high_risk_count} high-risk warrant succession plans."
            )
        else:
            st.error(
                f"🔴 {full.critical_risk_count} critical-risk staff need "
                f"immediate succession planning."
            )

        if full.top_risk_drivers_global:
            st.markdown("**Top risk drivers across the bank:**")
            for driver, count in full.top_risk_drivers_global.items():
                st.write(f"  • **{driver}**: {count} staff affected")

        if full.critical_staff:
            with st.expander(
                f"🔴 Critical-risk staff ({len(full.critical_staff)})",
                expanded=True,
            ):
                st.dataframe(pd.DataFrame(full.critical_staff),
                            use_container_width=True, hide_index=True)

        st.divider()
        st.caption(f"Audit timestamp: {full.timestamp}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Bank-wide audit failed: {exc}")
