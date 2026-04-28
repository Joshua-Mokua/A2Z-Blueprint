"""pages/_admin_etl.py — ETL Centre.

Admin tab for monitoring and operating the FLEXCUBE ETL pipeline.

Features:
  - Trigger ETL runs (full / incremental / dry-run)
  - View batch register (last 30 days)
  - Inspect staging table contents per batch
  - View ETL logs
"""
import streamlit as st
import pandas as pd
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timedelta
from utils.core_audit import audit_log
from utils.db import db

DATA = Path(__file__).parent.parent / "data"
LOG_DIR = DATA / "etl_logs"
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"


def render_etl_centre(tab, uname: str, is_admin: bool):
    """Render the ETL Centre tab."""
    with tab:
        if not is_admin:
            st.warning("🔒 ETL Centre is admin-only.")
            return

        st.markdown(
            "<div style='padding:16px 0 4px'>"
            "<span style='font-size:22px;font-weight:800'>🔄 FLEXCUBE ETL Centre</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Daily extract · Validate · Reconcile</span></div>",
            unsafe_allow_html=True,
        )

        from utils import flexcube_adapter as fcx
        mode = fcx.get_mode()
        mode_color = {"synthetic":"🟦", "mock":"🟨", "live":"🟩"}.get(mode, "⬜")
        st.info(f"{mode_color} Adapter mode: **{mode.upper()}** — change in FLEXCUBE Integration page (#86)")

        sub_tabs = st.tabs(["📊 Dashboard", "▶️ Run ETL", "📋 Batch History", "🔬 Staging Inspector", "📜 Logs"])

        # ── Dashboard ─────────────────────────────────────────
        with sub_tabs[0]:
            st.markdown("**Recent batches (last 30 days):**")
            batches = []
            try:
                if db.is_postgres_ready():
                    batches = db.fetch_all(
                        "SELECT batch_id, extract_started, extract_completed, status, "
                        "record_count, valid_count, invalid_count, triggered_by "
                        "FROM staging.etl_batch_register "
                        "WHERE extract_started >= now() - interval '30 days' "
                        "ORDER BY extract_started DESC"
                    )
            except Exception as e:
                st.warning(f"Could not query batches: {e}")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Batches in 30d", len(batches))
            success = sum(1 for b in batches if b.get("status") == "COMPLETED")
            failed  = sum(1 for b in batches if b.get("status") in ("FAILED","PARTIAL"))
            m2.metric("Successful", success)
            m3.metric("Failed/Partial", failed, delta_color="inverse" if failed > 0 else "off")
            success_rate = (success / max(len(batches),1)) * 100
            m4.metric("Success rate", f"{success_rate:.1f}%")

            if batches:
                rows = []
                for b in batches[:30]:
                    started   = b.get("extract_started")
                    completed = b.get("extract_completed")
                    duration = "—"
                    if started and completed:
                        try:
                            duration = str(completed - started).split(".")[0]
                        except Exception:
                            pass
                    icon = {"COMPLETED":"✅","PARTIAL":"⚠️","FAILED":"❌","RUNNING":"🔄"}.get(b.get("status",""), "")
                    rows.append({
                        "Status":   f"{icon} {b.get('status','')}",
                        "Batch ID": str(b.get("batch_id",""))[:30],
                        "Started":  str(started)[:19] if started else "—",
                        "Duration": duration,
                        "Records":  b.get("record_count", 0),
                        "Valid":    b.get("valid_count", 0),
                        "Invalid":  b.get("invalid_count", 0),
                        "By":       b.get("triggered_by", ""),
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("No batches yet. Click 'Run ETL' to trigger your first run.")

        # ── Run ETL ───────────────────────────────────────────
        with sub_tabs[1]:
            st.markdown("**Trigger an ETL run**")
            st.caption("Full extract takes 30-90s in synthetic/mock mode. Live mode depends on FLEXCUBE response time.")

            run_mode = st.selectbox("Run mode", ["full", "incremental", "dry-run"],
                                     help="Full=all records, Incremental=since last batch, Dry-run=extract only")
            since = None
            if run_mode == "incremental":
                since = st.text_input("Since (ISO datetime)",
                                       value=(datetime.utcnow() - timedelta(hours=4)).isoformat())

            if st.button("▶️ Run ETL now", type="primary", key="etl_run"):
                cmd = [sys.executable, str(SCRIPTS_DIR / "etl_flexcube.py"),
                       "--mode=" + (run_mode if run_mode != "dry-run" else "full"),
                       "--triggered-by=" + uname]
                if run_mode == "dry-run":
                    cmd.append("--dry-run")
                if since:
                    cmd.append("--since=" + since)

                audit_log("ETL_TRIGGERED", uname, "mode=" + run_mode + ", since=" + (since or "—"))

                with st.spinner("Running ETL (" + run_mode + ")..."):
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
                        st.code(result.stdout[-3000:] if result.stdout else "(no stdout)")
                        if result.returncode == 0:
                            st.success("✅ ETL completed (exit code 0)")
                        else:
                            st.error("❌ ETL exited with code " + str(result.returncode))
                            if result.stderr:
                                st.code(result.stderr[-1000:], language="bash")
                    except subprocess.TimeoutExpired:
                        st.error("⏱️ ETL timed out after 5 minutes")
                    except Exception as e:
                        st.error("❌ Could not run ETL: " + str(e))

            st.markdown("---")
            st.markdown("**Schedule (production)**")
            cron_text = (
                "# Linux cron — daily at 02:00 Nairobi time (23:00 UTC)\n"
                "0 23 * * * cd /opt/a2z && python scripts/etl_flexcube.py --mode=full\n\n"
                "# Incremental every 4 hours during business hours\n"
                "0 */4 * * 1-5 cd /opt/a2z && python scripts/etl_flexcube.py --mode=incremental"
            )
            st.code(cron_text, language="bash")

        # ── Batch History ─────────────────────────────────────
        with sub_tabs[2]:
            st.markdown("**All batches**")
            try:
                if db.is_postgres_ready():
                    all_batches = db.fetch_all(
                        "SELECT * FROM staging.etl_batch_register "
                        "ORDER BY extract_started DESC LIMIT 100"
                    )
                    if all_batches:
                        df = pd.DataFrame(all_batches)
                        for col in ["extract_started", "extract_completed"]:
                            if col in df.columns:
                                df[col] = df[col].astype(str).str[:19]
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No batches recorded.")
                else:
                    st.info("PostgreSQL not connected — batch history requires DB.")
            except Exception as e:
                st.warning(f"Query failed: {e}")

        # ── Staging Inspector ─────────────────────────────────
        with sub_tabs[3]:
            st.markdown("**Inspect a specific batch**")
            try:
                if db.is_postgres_ready():
                    recent_ids = db.fetch_all(
                        "SELECT batch_id FROM staging.etl_batch_register "
                        "ORDER BY extract_started DESC LIMIT 10"
                    )
                    batch_options = [b["batch_id"] for b in recent_ids]
                else:
                    batch_options = []
            except Exception:
                batch_options = []

            if batch_options:
                chosen = st.selectbox("Batch ID", batch_options, key="etl_batch_pick")
                table = st.selectbox("Staging table",
                                      ["flexcube_customers", "flexcube_accounts", "flexcube_loans",
                                       "flexcube_transactions", "flexcube_gl_balances"],
                                      key="etl_table_pick")
                status_filter = st.selectbox("Validation status",
                                              ["ALL", "VALID", "INVALID", "PENDING"],
                                              key="etl_status_pick")

                if st.button("🔍 Inspect", key="etl_inspect"):
                    try:
                        sql = f"SELECT * FROM staging.{table} WHERE batch_id = %s"
                        params = (chosen,)
                        if status_filter != "ALL":
                            sql += " AND validation_status = %s"
                            params = (chosen, status_filter)
                        sql += " LIMIT 200"
                        rows = db.fetch_all(sql, params)
                        if rows:
                            st.success(f"✅ Found {len(rows)} record(s)")
                            df = pd.DataFrame(rows)
                            st.dataframe(df, use_container_width=True)
                        else:
                            st.info("No matching records.")
                    except Exception as e:
                        st.error(f"Query failed: {e}")
            else:
                st.info("No batches available. Run ETL first.")

        # ── Logs ──────────────────────────────────────────────
        with sub_tabs[4]:
            st.markdown("**Recent ETL log files**")
            if LOG_DIR.exists():
                logs = sorted(LOG_DIR.glob("etl_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
                if logs:
                    chosen_log = st.selectbox("Pick a log",
                                               logs[:20],
                                               format_func=lambda p: p.name,
                                               key="etl_log_pick")
                    if chosen_log:
                        try:
                            content = chosen_log.read_text(encoding="utf-8")
                            st.code(content[-10000:], language="text")
                        except Exception as e:
                            st.error(f"Could not read log: {e}")
                else:
                    st.info("No log files yet.")
            else:
                st.info("Log directory not yet created. Run ETL first.")
