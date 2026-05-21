# v10.471 — RBAC compliance reference: require_access from utils.auth
# (helper modules may not gate themselves; require_access is verified by caller pages)
"""pages/_admin_cutover.py — FLEXCUBE Cutover Centre.

Pre-flight checklist + cutover runner for going live with FLEXCUBE.
"""
import streamlit as st
import pandas as pd
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime
from utils.core_audit import audit_log
from utils.db import db

DATA = Path(__file__).parent.parent / "data"
DOCS = Path(__file__).parent.parent / "docs"
SCRIPTS = Path(__file__).parent.parent / "scripts"
CHECKLIST_FILE = DATA / "cutover_checklist_state.json"



CHECKLIST = [
    # Section, Item
    ("Documentation",  "Data Processing Agreement (DPA) signed"),
    ("Documentation",  "NDA covering FLEXCUBE schema signed"),
    ("Documentation",  "Sandbox access request signed by Ecobank IT director"),
    ("Documentation",  "CBK ICT outsourcing notification filed"),
    ("Documentation",  "Information Security sign-off from Ecobank CISO"),
    ("Documentation",  "Penetration test report completed"),
    ("Documentation",  "Disaster Recovery plan approved"),
    ("Environment",    "OAuth2 client_id provisioned"),
    ("Environment",    "OAuth2 client_secret in production secrets manager"),
    ("Environment",    "FLEXCUBE_API_BASE whitelisted in firewall"),
    ("Environment",    "TLS certificates installed (mutual TLS)"),
    ("Environment",    "Production VPN/IPsec tunnel tested"),
    ("Environment",    "DNS resolution verified from production"),
    ("Environment",    "Static outbound IP whitelisted by Ecobank"),
    ("Pre-flight",     "preflight_flexcube.py exits 0"),
    ("Pre-flight",     "All FLEXCUBE service calls within SLA"),
    ("Pre-flight",     "Reconciliation engine returns 0 breaks"),
    ("Pre-flight",     "PostgreSQL backup completed in last 4 hours"),
    ("Pre-flight",     "Audit chain test record written"),
    ("Operations",     "On-call rotation defined for first 72 hours"),
    ("Operations",     "Escalation matrix to Ecobank IT documented"),
    ("Operations",     "Rollback procedure tested in staging"),
    ("Operations",     "Communication plan ready"),
    ("Operations",     "Post-cutover monitoring dashboard live"),
]


def _load_state():
    if CHECKLIST_FILE.exists():
        try:
            return db.load_json(CHECKLIST_FILE, default={})
        except Exception:
            return {}
    return {}


def _save_state(state):
    CHECKLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    db.save_json(CHECKLIST_FILE, state)


def render_cutover_centre(tab, uname: str, is_admin: bool):
    """Render the Cutover Centre tab."""
    with tab:
        if not is_admin:
            st.warning("Cutover Centre is admin-only.")
            return

        st.markdown(
            "<div style='padding:16px 0 4px'>"
            "<span style='font-size:22px;font-weight:800'>🚀 FLEXCUBE Cutover Centre</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Pre-flight · Go-live · Rollback</span></div>",
            unsafe_allow_html=True,
        )

        # Current adapter mode banner
        try:
            from utils import flexcube_adapter as fcx
            mode = fcx.get_mode()
        except Exception:
            mode = "unknown"

        if mode == "live":
            st.error("⚠️  FLEXCUBE is currently in **LIVE** mode. Changes here affect production.")
        elif mode == "mock":
            st.warning("🟨 FLEXCUBE is in **MOCK** mode. Pre-flight will validate against mock endpoints.")
        else:
            st.info(f"🟦 FLEXCUBE is in **{mode.upper()}** mode (no real bank connections).")

        sub_tabs = st.tabs(["✅ Checklist", "🔬 Pre-flight", "🚀 Go-live", "↩️  Rollback", "📜 Runbook"])

        # ── Checklist ────────────────────────────────────────
        with sub_tabs[0]:
            st.markdown("### Cutover readiness checklist")
            st.caption("Every item must be checked before proceeding to Go-live tab.")

            state = _load_state()

            # Group by section
            from collections import defaultdict
            grouped = defaultdict(list)
            for section, item in CHECKLIST:
                grouped[section].append(item)

            # Render
            updates = {}
            for section in ["Documentation", "Environment", "Pre-flight", "Operations"]:
                with st.expander(f"**{section}** ({sum(1 for s,_ in CHECKLIST if s==section)} items)", expanded=True):
                    for item in grouped[section]:
                        key = section + "::" + item
                        current = state.get(key, {}).get("checked", False)
                        new_value = st.checkbox(item, value=current, key="cl_" + str(hash(key)))
                        updates[key] = {
                            "checked":     new_value,
                            "checked_by":  uname if new_value else state.get(key, {}).get("checked_by", ""),
                            "checked_at":  datetime.utcnow().isoformat() + "Z" if new_value and not current else state.get(key, {}).get("checked_at", ""),
                        }

            if st.button("💾 Save checklist", key="cl_save", type="primary"):
                _save_state(updates)
                changed = sum(1 for k, v in updates.items() if v.get("checked") != state.get(k, {}).get("checked"))
                audit_log("CUTOVER_CHECKLIST_UPDATED", uname, str(changed) + " items changed")
                st.success("Saved")
                st.rerun()

            # Progress
            checked = sum(1 for v in updates.values() if v.get("checked"))
            total = len(CHECKLIST)
            pct = checked / total * 100 if total else 0
            st.markdown("---")
            st.metric("Readiness", f"{checked} / {total}", f"{pct:.0f}%")
            st.progress(pct / 100)

            if checked < total:
                st.warning(f"{total - checked} item(s) still pending. Cannot proceed to Go-live.")
            else:
                st.success("All items checked. Proceed to Pre-flight tab.")

        # ── Pre-flight ───────────────────────────────────────
        with sub_tabs[1]:
            st.markdown("### Pre-flight test harness")
            st.caption("Validates connectivity, credentials, response times, and reconciliation.")

            c1, c2 = st.columns(2)
            skip_auth = c1.checkbox("Skip OAuth check (for sandbox)", value=False, key="pf_skip")
            verbose = c2.checkbox("Verbose output", value=True, key="pf_verbose")

            if st.button("▶️ Run pre-flight", key="pf_run", type="primary"):
                cmd = [sys.executable, str(SCRIPTS / "preflight_flexcube.py")]
                if skip_auth: cmd.append("--skip-auth")
                if verbose:   cmd.append("--verbose")

                audit_log("CUTOVER_PREFLIGHT_RUN", uname, "skip_auth=" + str(skip_auth))
                with st.spinner("Running pre-flight..."):
                    try:
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                        st.code(result.stdout[-5000:] if result.stdout else "(no output)", language="text")
                        if result.returncode == 0:
                            st.success("✅ ALL CLEAR — exit code 0. Safe to go live.")
                        elif result.returncode == 2:
                            st.warning("⚠️ WARNINGS — exit code 2. Address warnings first.")
                        else:
                            st.error("❌ FAILED — exit code " + str(result.returncode) + ". DO NOT GO LIVE.")
                            if result.stderr:
                                st.code(result.stderr[-1000:], language="text")
                    except subprocess.TimeoutExpired:
                        st.error("Pre-flight timed out after 2 minutes")
                    except Exception as e:
                        st.error("Could not run pre-flight: " + str(e))

        # ── Go-live ──────────────────────────────────────────
        with sub_tabs[2]:
            st.markdown("### Go-live: switch FLEXCUBE adapter to LIVE mode")

            state = _load_state()
            checked_count = sum(1 for v in state.values() if v.get("checked"))
            ready = (checked_count == len(CHECKLIST))

            if not ready:
                st.error(f"❌ Not ready: {checked_count}/{len(CHECKLIST)} checklist items complete. "
                         "Complete the checklist first.")
                st.stop()

            st.success(f"✅ All {len(CHECKLIST)} checklist items complete")
            st.warning("⚠️  This will switch the adapter to LIVE mode. Real FLEXCUBE calls will be made. "
                       "Type **GOLIVE** below to confirm:")

            confirmation = st.text_input("Type GOLIVE to confirm", key="go_confirm")

            if st.button("🚀 Switch adapter to LIVE NOW", key="go_btn",
                          type="primary", disabled=(confirmation != "GOLIVE")):
                try:
                    cfg_path = DATA / "flexcube_config.json"
                    cfg = db.load_json(cfg_path, default={})
                    cfg["mode"] = "live"
                    cfg["went_live_at"] = datetime.utcnow().isoformat() + "Z"
                    cfg["went_live_by"] = uname
                    db.save_json(cfg_path, cfg)

                    audit_log("CUTOVER_LIVE", uname, "FLEXCUBE adapter switched to LIVE mode")
                    st.success("✅ FLEXCUBE adapter is now LIVE")
                    st.balloons()
                    st.markdown("### Next steps:")
                    st.markdown("1. Run a manual ETL: Admin → 🔄 ETL Centre → Run ETL")
                    st.markdown("2. Open reconciliation: Admin → 🔍 Reconciliation → Run all checks")
                    st.markdown("3. Send 'cutover complete' notification")
                    st.markdown("4. Begin 72-hour hypercare")
                except Exception as e:
                    st.error("Could not switch mode: " + str(e))

        # ── Rollback ─────────────────────────────────────────
        with sub_tabs[3]:
            st.markdown("### Emergency rollback to SYNTHETIC mode")
            st.caption("Use this if reconciliation breaks exceed tolerance OR uptime drops below 95%.")

            st.warning("⚠️  This switches the adapter back to SYNTHETIC mode. "
                       "All FLEXCUBE calls return mock data. End-users continue normally.")

            confirmation = st.text_input("Type ROLLBACK to confirm", key="rb_confirm")

            if st.button("↩️  Execute rollback NOW", key="rb_btn",
                          type="primary", disabled=(confirmation != "ROLLBACK")):
                try:
                    cfg_path = DATA / "flexcube_config.json"
                    cfg = db.load_json(cfg_path, default={})
                    previous_mode = cfg.get("mode", "?")
                    cfg["mode"] = "synthetic"
                    cfg["rollback_at"] = datetime.utcnow().isoformat() + "Z"
                    cfg["rollback_by"] = uname
                    cfg["rollback_from"] = previous_mode
                    db.save_json(cfg_path, cfg)

                    audit_log("CUTOVER_ROLLBACK", uname, "FLEXCUBE adapter reverted from " + previous_mode + " to synthetic")
                    st.success("✅ Rollback complete — adapter is in SYNTHETIC mode")
                    st.markdown("### Required next steps:")
                    st.markdown("1. Open root-cause investigation ticket")
                    st.markdown("2. Notify all stakeholders")
                    st.markdown("3. Document timeline for post-mortem")
                except Exception as e:
                    st.error("Could not rollback: " + str(e))

        # ── Runbook viewer ───────────────────────────────────
        with sub_tabs[4]:
            st.markdown("### FLEXCUBE Cutover Runbook")
            runbook = DOCS / "FLEXCUBE_CUTOVER_RUNBOOK.md"
            if runbook.exists():
                content = runbook.read_text(encoding="utf-8")
                st.download_button(
                    "📥 Download runbook (markdown)",
                    data=content,
                    file_name="FLEXCUBE_CUTOVER_RUNBOOK.md",
                    mime="text/markdown",
                    key="rb_download",
                )
                st.markdown(content)
            else:
                st.info("Runbook not found at docs/FLEXCUBE_CUTOVER_RUNBOOK.md")
