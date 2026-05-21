"""pages/79_staff_onboarding.py — Staff Onboarding fit-in & validation.

Wires `staff_onboarding_engine` (v10.434) into a user-facing page.
Per HR Rescue Arc v10.441.

Four tabs:
  🆕 Simulate Onboarding — preview what a hypothetical hire's BSC will look like
  🔍 Validate Record    — pre-add field/role/duplicate checks
  👤 Per-Staff Audit    — verify any existing staff's full canonical fit
  📊 Bank-Wide Audit    — 81.8% fully-fit rollup across all 1437 staff
"""
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

import pandas as pd
import json
from pathlib import Path
from collections import Counter
from pages._shared import load_shared_state
from pages._access import require_access

require_access("people_hr.onboarding")

DATA = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role", "")
sc = str(ud.get("staff_code", ""))
is_admin = ud.get("is_admin", False)
is_hr = any(x in role.lower() for x in (
    "human resource", "hr", "chief human", "training", "manager", "head of"
))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🆕 Staff Onboarding</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Validate · Simulate · Audit · Fit-in monitoring</span></div>",
    unsafe_allow_html=True,
)
st.caption(
    "Verifies every staff's canonical fit: register → role_kpis → BSC "
    "rows → weight sum 1.0 → all 4 pillars → score computable. Std v10.434."
)

try:
    from utils.staff_onboarding_engine import (
        validate_new_staff,
        simulate_onboarding,
        audit_staff_completeness,
        audit_all_staff_completeness,
    )
except Exception as exc:  # noqa: BLE001
    st.error(f"Onboarding engine unavailable: {exc}")
    st.stop()


# Quick metrics header
try:
    quick = audit_all_staff_completeness()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total staff", quick.total_staff)
    m2.metric("Fully fit", quick.fully_fit,
              delta=f"{quick.fully_fit/max(quick.total_staff,1)*100:.1f}%")
    m3.metric("Partial fit", quick.partial_fit)
    m4.metric("Weight invariant", f"{quick.weight_sum_invariant_pct}%")
except Exception:  # noqa: BLE001
    pass

tabs = st.tabs([
    "🆕 Simulate Onboarding",
    "🔍 Validate Record",
    "👤 Per-Staff Audit",
    "📊 Bank-Wide Audit",
])

# ── Tab 0: Simulate Onboarding ─────────────────────────────────
with tabs[0]:
    st.markdown("**Project what a new hire's BSC would look like — before adding them.**")
    st.caption(
        "No data writes. Catches roles missing from role_kpis (would get 0 KPIs)."
    )
    try:
        lib_path = DATA / "kpi_library.json"
        lib = json.loads(lib_path.read_text(encoding="utf-8"))
        roles = sorted(lib.get("role_kpis", {}).keys())
    except Exception:  # noqa: BLE001
        roles = []

    col1, col2 = st.columns(2)
    sim_code = col1.text_input("Staff Code (hypothetical)",
                                value="TST_SIM_001", key="sim_code")
    sim_name = col2.text_input("Staff Name (hypothetical)",
                                value="Hypothetical New Hire", key="sim_name")
    if roles:
        col3, col4 = st.columns(2)
        sim_role = col3.selectbox("Role", roles, key="sim_role")
        sim_unit = col4.text_input("Unit / Branch",
                                    value="Test Unit", key="sim_unit")
    else:
        st.warning("Could not load role list from kpi_library.json")
        sim_role = st.text_input("Role", key="sim_role_text")
        sim_unit = st.text_input("Unit", value="Test Unit", key="sim_unit_text")

    if st.button("Simulate onboarding", key="btn_sim_onboard"):
        try:
            result = simulate_onboarding({
                "Staff Code": sim_code,
                "Staff Name": sim_name,
                "Role": sim_role,
                "Unit": sim_unit,
            })

            if not result.valid:
                st.error(f"Validation failed: {len(result.validation.errors)} error(s)")
                for e in result.validation.errors:
                    st.write(f"  • **{e.field}**: {e.message}")
            else:
                s1, s2, s3, s4 = st.columns(4)
                s1.metric("BSC rows added", result.bsc_rows_added)
                s2.metric("Weight sum", f"{result.weight_sum_post:.2f}")
                s3.metric("Cascade allocations",
                          result.cascade_allocations_received)
                s4.metric("Score computable",
                          "✓" if result.score_computable else "✗")

                pc = result.pillar_coverage
                st.write(
                    f"**Pillar coverage:** "
                    f"Financial: {pc.get('Financial', 0)} · "
                    f"Customer Focus: {pc.get('Customer Focus', 0)} · "
                    f"OpEx: {pc.get('Operational Excellence', 0)} · "
                    f"P&L: {pc.get('People & Learning', 0)}"
                )

                if result.bsc_rows_added == 0:
                    st.warning(
                        f"⚠️ Role '{sim_role}' has no KPIs in role_kpis. "
                        f"A real hire into this role would get an empty BSC. "
                        f"Admin should add KPIs to role_kpis['{sim_role}']."
                    )

                if result.role_kpis_resolved:
                    with st.expander(
                        f"KPIs that would be assigned ({len(result.role_kpis_resolved)})",
                    ):
                        for k in result.role_kpis_resolved:
                            st.write(f"  • {k}")

                if result.validation.warnings:
                    with st.expander(
                        f"Warnings ({len(result.validation.warnings)})",
                    ):
                        for w in result.validation.warnings:
                            st.write(f"  • **{w.field}**: {w.message}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Simulation failed: {exc}")


# ── Tab 1: Validate Record ──────────────────────────────────────
with tabs[1]:
    st.markdown("**Pre-add validation — required fields, format, duplicates, role configured.**")
    st.caption("Run this before any HR system inserts a new staff record.")

    with st.form("validate_form"):
        col1, col2 = st.columns(2)
        v_code = col1.text_input("Staff Code *", value="", key="v_code")
        v_name = col2.text_input("Staff Name *", value="", key="v_name")
        col3, col4 = st.columns(2)
        v_role = col3.text_input("Role *", value="", key="v_role")
        v_unit = col4.text_input("Unit *", value="", key="v_unit")
        col5, col6 = st.columns(2)
        v_reports_to = col5.text_input("Reports To (manager code)", value="",
                                        key="v_reports_to")
        v_band = col6.text_input("Band", value="", key="v_band")
        v_submit = st.form_submit_button("Validate")

    if v_submit:
        payload = {
            "Staff Code": v_code,
            "Staff Name": v_name,
            "Role": v_role,
            "Unit": v_unit,
        }
        if v_reports_to.strip():
            payload["Reports To"] = v_reports_to.strip()
        if v_band.strip():
            payload["Band"] = v_band.strip()

        try:
            r = validate_new_staff(payload)
            if r.valid:
                st.success(f"✅ Validation passed. {len(r.warnings)} warning(s).")
            else:
                st.error(f"❌ Validation failed. {len(r.errors)} error(s).")

            if r.errors:
                st.markdown("**Errors:**")
                for e in r.errors:
                    st.write(f"  🔴 **{e.field}**: {e.message}")
            if r.warnings:
                st.markdown("**Warnings:**")
                for w in r.warnings:
                    st.write(f"  🟡 **{w.field}**: {w.message}")
            if r.info:
                st.markdown("**Info:**")
                for i in r.info:
                    st.write(f"  ℹ️ **{i.field}**: {i.message}")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Validation failed: {exc}")


# ── Tab 2: Per-Staff Audit ──────────────────────────────────────
with tabs[2]:
    st.markdown("**Audit any existing staff's full canonical fit across 6 dimensions.**")
    st.caption(
        "Register · role_kpis · BSC rows · weight sum · pillars · score · cascade."
    )
    audit_code = st.text_input("Staff code to audit",
                                value=sc or "300001",
                                key="audit_code")
    if st.button("Run audit", key="btn_audit_staff"):
        try:
            a = audit_staff_completeness(audit_code)

            if not a.register_present:
                st.error(f"Staff code {audit_code} not in register.")
            else:
                c1, c2 = st.columns(2)
                c1.write(f"**Name:** {a.staff_name}")
                c1.write(f"**Role:** {a.role}")
                c2.write(f"**Unit:** {a.unit}")
                c2.write(
                    f"**Overall fit:** "
                    f"{'✅ Yes' if a.overall_fit else '⚠️ No'}"
                )

                m1, m2, m3, m4 = st.columns(4)
                m1.metric("BSC rows", a.bsc_row_count)
                m2.metric("BSC ∩ role_kpis", a.bsc_kpis_matching_role_kpis)
                m3.metric("Weight sum", f"{a.weight_sum:.4f}",
                          delta="✓" if a.weight_sum_valid else "⚠️")
                m4.metric("Cascade alloc", a.cascade_allocations_received)

                st.write(
                    f"**Pillar coverage:** "
                    f"Financial: {a.pillar_coverage.get('Financial', 0)} · "
                    f"Customer: {a.pillar_coverage.get('Customer Focus', 0)} · "
                    f"OpEx: {a.pillar_coverage.get('Operational Excellence', 0)} · "
                    f"P&L: {a.pillar_coverage.get('People & Learning', 0)}"
                )

                if a.bsc_kpis_missing:
                    with st.expander(
                        f"⚠️ Missing role_kpis from BSC ({len(a.bsc_kpis_missing)})",
                    ):
                        for k in a.bsc_kpis_missing:
                            st.write(f"  • {k}")

                if a.issues:
                    st.warning("**Issues:**")
                    for issue in a.issues:
                        st.write(f"  • {issue}")
                else:
                    st.success("✅ No issues detected.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Audit failed: {exc}")


# ── Tab 3: Bank-Wide Audit ──────────────────────────────────────
with tabs[3]:
    st.markdown("**Bank-wide fit-in audit across all 1,437 staff.**")
    st.caption(
        "Read-only diagnostic. Surfaces staff with gaps that admin should "
        "fix via the KPI Library editor (role_kpis configuration)."
    )

    try:
        full = audit_all_staff_completeness()

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total", full.total_staff)
        c2.metric("Fully fit", full.fully_fit,
                  delta=f"{full.fully_fit/max(full.total_staff,1)*100:.1f}%")
        c3.metric("Partial fit", full.partial_fit)
        c4.metric("Failing", full.failing)

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Avg role_kpi coverage", f"{full.avg_role_kpi_coverage_pct}%")
        c6.metric("Weight invariant", f"{full.weight_sum_invariant_pct}%")
        c7.metric("Score computable", f"{full.score_computable_pct}%")
        c8.metric("All 4 pillars", f"{full.pillar_coverage_pct}%")

        if full.failing_samples:
            with st.expander(
                f"🔴 Failing staff samples ({len(full.failing_samples)})",
                expanded=False,
            ):
                for s in full.failing_samples:
                    st.error(
                        f"**{s.get('code')} {s.get('name')}** "
                        f"({s.get('role')}): {', '.join(s.get('issues', []))}"
                    )

        st.divider()
        st.caption(f"Audit timestamp: {full.timestamp}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Bank-wide audit failed: {exc}")
