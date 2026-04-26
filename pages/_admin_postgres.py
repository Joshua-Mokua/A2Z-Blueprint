"""pages/_admin_postgres.py — PostgreSQL Migration Centre.

Admin tab that shows:
  • PostgreSQL connection health
  • Per-table migration status (JSON vs PG)
  • Row counts for each table (in current backend)
  • One-click migration trigger per table
  • Schema export / health reports
"""
import streamlit as st
import pandas as pd
import json
import os
from pathlib import Path
from datetime import datetime
from utils.core import audit_log
from utils.db import db, TABLE_USE_DB, get_schema_sql

DATA = Path(__file__).parent.parent / "data"

# Map: PG table → (JSON file, friendly name, module category)
TABLE_MAP = {
    # Tier 1 — Auth & Audit
    "users":                     ("users.json",                     "Users (auth)",                 "🔐 Tier 1 — Auth"),
    "audit_trail":               ("audit.json",                     "Audit Trail",                  "🔐 Tier 1 — Auth"),
    "sessions":                  (None,                              "Sessions",                     "🔐 Tier 1 — Auth"),
    # Tier 2 — Core
    "bsc_scores":                ("feb_2026_staff_scores.json",     "BSC Scores",                   "📊 Tier 2 — Core"),
    "pipeline_deals":            ("pipeline.json",                   "Pipeline Deals",               "📊 Tier 2 — Core"),
    "loan_applications":         ("loan_applications.json",          "Loan Applications",            "📊 Tier 2 — Core"),
    "aml_alerts":                ("aml_alerts.json",                 "AML Alerts",                   "📊 Tier 2 — Core"),
    "disciplinary":              ("disciplinary.json",               "Disciplinary",                 "📊 Tier 2 — Core"),
    # v5.8 — Phase 1 Critical Regulatory
    "cbk_returns":               ("cbk_returns.json",                "CBK Returns Centre",           "🚨 Phase 1 — Regulatory"),
    "dpo_register":              ("dpo_register.json",               "Data Protection Office",       "🚨 Phase 1 — Regulatory"),
    "sanctions_register":        ("sanctions_register.json",         "Sanctions Screening",          "🚨 Phase 1 — Regulatory"),
    "capital_liquidity_metrics": ("capital_liquidity_metrics.json",  "Capital & Liquidity",          "🚨 Phase 1 — Regulatory"),
    # v5.8 — Phase 2 Business
    "customer_onboarding":       ("customer_onboarding.json",        "Customer Onboarding",          "💼 Phase 2 — Business"),
    "card_management":           ("card_management.json",            "Card Management",              "💼 Phase 2 — Business"),
    "merchant_acquiring":        ("merchant_acquiring.json",         "Merchant Acquiring",           "💼 Phase 2 — Business"),
    "alm_gap_analysis":          ("alm_liquidity.json",              "ALM Gap Analysis",             "💼 Phase 2 — Business"),
    "alm_funding_sources":       ("alm_liquidity.json",              "ALM Funding Sources",          "💼 Phase 2 — Business"),
    "alm_alco_meetings":         ("alm_liquidity.json",              "ALM ALCO Meetings",            "💼 Phase 2 — Business"),
    "alm_contingency_plans":     ("alm_liquidity.json",              "ALM Contingency Plans",        "💼 Phase 2 — Business"),
    "op_risk_losses":            ("op_risk_losses.json",             "Operational Risk Losses",      "💼 Phase 2 — Business"),
    # v5.8 — Phase 3 Strategic
    "strategic_initiatives":     ("strategic_initiatives.json",      "Strategic Initiatives",        "🎯 Phase 3 — Strategic"),
    "board_papers":              ("board_papers.json",               "Board Pack & Papers",          "🎯 Phase 3 — Strategic"),
    "esg_green_loans":           ("esg_climate.json",                "ESG Green Loans",              "🎯 Phase 3 — Strategic"),
    "esg_initiatives":           ("esg_climate.json",                "ESG Initiatives",              "🎯 Phase 3 — Strategic"),
    "esg_climate_assessments":   ("esg_climate.json",                "ESG Climate Assessments",      "🎯 Phase 3 — Strategic"),
    "esg_score_snapshot":        ("esg_climate.json",                "ESG Score Snapshot",           "🎯 Phase 3 — Strategic"),
    # v5.8 — FLEXCUBE
    "flexcube_events":           ("flexcube_events.json",            "FLEXCUBE Events",              "🔌 FLEXCUBE"),
    "flexcube_config":           ("flexcube_config.json",            "FLEXCUBE Config",              "🔌 FLEXCUBE"),
    "module_config":             ("module_config.json",              "Module Config Centre",         "🔧 Configuration"),
}


def _count_json(json_path):
    """Count records in a JSON file."""
    if not json_path:
        return None
    p = DATA / json_path
    if not p.exists():
        return 0
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(d, list): return len(d)
        if isinstance(d, dict):
            # Sum sub-list lengths
            return sum(len(v) if isinstance(v, list) else 1 for v in d.values())
        return 1
    except Exception:
        return None


def _count_pg(table):
    """Count rows in a PG table."""
    if not db.is_postgres_ready():
        return None
    try:
        return db.fetch_scalar(f"SELECT count(*) FROM {table}")
    except Exception:
        return None


def render_postgres_centre(tab, uname: str, is_admin: bool):
    """Render the PostgreSQL Migration Centre tab."""
    with tab:
        if not is_admin:
            st.warning("🔒 PostgreSQL Migration Centre is admin-only.")
            return

        st.markdown(
            "<div style='padding:16px 0 4px'>"
            "<span style='font-size:22px;font-weight:800'>🗄️ PostgreSQL Migration Centre</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Govern the JSON → PostgreSQL transition</span></div>",
            unsafe_allow_html=True,
        )

        # ── Connection health ─────────────────────────────────────
        health = db.health_check()
        is_ready = db.is_postgres_ready()

        status_color = "🟢" if is_ready else "🔴"
        if is_ready:
            st.success(f"{status_color} PostgreSQL connected: {health.get('host','?')} / {health.get('database','?')}")
        else:
            st.error(f"{status_color} PostgreSQL is OFFLINE — system is using JSON file backend (synthetic mode).")
            st.caption("To enable PostgreSQL, set environment variables and restart Streamlit:")
            st.code(
                "A2Z_USE_DB=true\n"
                "A2Z_DB_HOST=<host>\n"
                "A2Z_DB_NAME=a2z_mis360\n"
                "A2Z_DB_USER=a2z_app\n"
                "A2Z_DB_PASSWORD=<password>\n"
                "A2Z_DB_SSLMODE=require",
                language="bash",
            )

        # ── KPI strip ─────────────────────────────────────────────
        n_total       = len(TABLE_USE_DB)
        n_pg_active   = sum(1 for v in TABLE_USE_DB.values() if v)
        n_json_only   = n_total - n_pg_active

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Backend",          "PostgreSQL" if is_ready else "JSON files")
        m2.metric("Tables defined",   n_total)
        m3.metric("Migrated to PG",   n_pg_active, delta_color="off")
        m4.metric("On JSON",          n_json_only)

        if is_ready:
            st.metric("Database size", health.get("db_size","?"))

        # ── Migration status table ────────────────────────────────
        st.markdown("### Migration Status by Table")

        # Group tables by category
        from collections import defaultdict
        by_cat = defaultdict(list)
        for table, flag in TABLE_USE_DB.items():
            meta = TABLE_MAP.get(table, (None, table, "❓ Other"))
            by_cat[meta[2]].append((table, flag, meta[0], meta[1]))

        for category, items in sorted(by_cat.items()):
            with st.expander(f"{category} ({len(items)} tables)", expanded="Phase 1" in category or "FLEXCUBE" in category):
                rows = []
                for table, flag, json_file, friendly in sorted(items):
                    json_count = _count_json(json_file)
                    pg_count   = _count_pg(table) if is_ready else None

                    if flag and is_ready and pg_count is not None and pg_count > 0:
                        status = "🟢 Live (PG)"
                    elif flag and is_ready:
                        status = "🟡 Empty (PG, no data)"
                    elif json_count and json_count > 0:
                        status = "📁 JSON only"
                    else:
                        status = "⚪ No data"

                    rows.append({
                        "Status":     status,
                        "Table":      table,
                        "Module":     friendly,
                        "JSON file":  json_file or "—",
                        "JSON rows":  f"{json_count:,}" if json_count is not None else "—",
                        "PG rows":    f"{pg_count:,}"   if pg_count   is not None else "—",
                        "Backend":    "PG" if flag else "JSON",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        st.markdown("---")

        # ── Bulk migration tools ──────────────────────────────────
        st.markdown("### 🚀 Migration Tools")

        tool_col1, tool_col2 = st.columns(2)

        with tool_col1:
            st.markdown("**Step 1 — Apply schema**")
            st.caption("Creates all tables (CREATE TABLE IF NOT EXISTS — safe to run multiple times)")
            if not is_ready:
                st.button("🚫 Apply schema", disabled=True, key="pg_apply_disabled",
                         help="Connect to PostgreSQL first")
            elif st.button("📋 Apply schema now", key="pg_apply", type="primary"):
                schema = get_schema_sql()
                try:
                    with db.transaction() as conn:
                        with conn.cursor() as cur:
                            cur.execute(schema)
                    audit_log("PG_SCHEMA_APPLIED", uname, "Schema CREATE TABLE IF NOT EXISTS executed")
                    st.success("✅ Schema applied — all 29 tables ready")
                except Exception as e:
                    st.error(f"❌ Schema apply failed: {e}")

        with tool_col2:
            st.markdown("**Step 2 — Run migration script**")
            st.caption("Loads all JSON data into PG. Run from terminal:")
            st.code("python scripts/migrate_to_postgres.py", language="bash")
            st.caption("This script is idempotent — safe to re-run. It DELETEs and re-INSERTs each table.")

        st.markdown("---")

        # ── SQL inspector ────────────────────────────────────────
        st.markdown("### 🔍 SQL Console (read-only)")
        st.caption("Run SELECT queries against PostgreSQL. Audit-logged.")
        sql = st.text_area("SQL query", "SELECT count(*) FROM cbk_returns;", key="pg_sql", height=80)
        if st.button("▶️ Execute", key="pg_exec"):
            if not is_ready:
                st.error("PostgreSQL not connected.")
            elif not sql.strip().upper().startswith("SELECT"):
                st.error("Only SELECT queries are permitted from this console.")
            else:
                try:
                    rows = db.fetch_all(sql)
                    audit_log("PG_QUERY", uname, sql[:200])
                    st.success(f"✅ {len(rows)} row(s) returned")
                    if rows:
                        st.dataframe(pd.DataFrame(rows), use_container_width=True)
                except Exception as e:
                    st.error(f"❌ Query failed: {e}")

        # ── Schema preview ────────────────────────────────────────
        with st.expander("📜 View full schema DDL"):
            st.code(get_schema_sql(), language="sql")

        # ── Footer ────────────────────────────────────────────────
        st.markdown("---")
        st.caption(
            "💡 **Migration approach:** dual-mode (default).\n"
            "Pages always write to JSON (cheap insurance) and additionally to PostgreSQL when "
            "the table flag is True. Pages always read from PostgreSQL when the flag is True, "
            "falling back to JSON if PG fails. This keeps the system online during migration "
            "and during PG outages."
        )
