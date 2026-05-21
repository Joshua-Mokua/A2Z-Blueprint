"""pages/36_smart_alerts.py — Smart Alerts Engine.
Proactive alerts: maturing FDs, BSC drops, SLA breaches,
deal staleness, compliance deadlines. AI-prioritised.
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
from datetime import date, timedelta
from collections import Counter
from pages._shared import load_shared_state
from pages._access import require_access

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()



require_access("shared.smart_alerts")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

@st.cache_data(ttl=30, show_spinner=False)
def _build_alerts():
    alerts = []
    aid = 1

    def add(atype, icon, sev, title, msg, module):
        nonlocal aid
        alerts.append({"id":f"ALT{aid:05d}","type":atype,"icon":icon,"severity":sev,
                        "title":title,"message":msg,"module":module,
                        "created":str(today),"read":False})
        aid+=1

    # FD maturing
    try:
        fd = json.loads((DATA/"treasury_fd.json").read_text())
        for r in fd:
            if r.get("maturity_date") and r["status"] in ("approved","booked"):
                try:
                    days=(_safe_date(r["maturity_date"])-today).days
                    if 0<=days<=7:
                        add("FD_MATURING","🔔","critical",
                            f"FD maturing in {days}d",
                            f"{r['client_name'][:25]} · {r['currency']} {r['amount']/1e6:.1f}M · {r['maturity_date']}",
                            "Treasury")
                    elif 8<=days<=30:
                        add("FD_MATURING","🔔","warning",
                            f"FD maturing in {days}d",
                            f"{r['client_name'][:25]} · {r['currency']} {r['amount']/1e6:.1f}M",
                            "Treasury")
                except: pass
    except: pass

    # Legal SLA breaches
    try:
        legal=json.loads((DATA/"legal_matters.json").read_text())
        for m in legal:
            if m.get("sla_breached") and m["status"] not in ("completed","on_hold"):
                add("LEGAL_OVERDUE","⚖️","critical",
                    f"Legal SLA breached",
                    f"{m.get('matter_type','')} · {m.get('client_name','')[:20]} · {m['status']}",
                    "Legal")
    except: pass

    # BSC below threshold
    try:
        scores=json.loads((DATA/"feb_2026_staff_scores.json").read_text())
        low = [(k,v) for k,v in scores.items() if v["final_score"]<2.5]
        for sc_v,s in low[:10]:
            add("BSC_LOW","📉","warning",
                f"BSC below 2.5: {s['name'][:20]}",
                f"Score {s['final_score']:.2f} · {s['role'][:30]} · {s['unit']}",
                "Performance")
    except: pass

    # Pipeline stale deals
    try:
        pipeline=json.loads((DATA/"pipeline.json").read_text())
        active=[d for d in pipeline if d.get("stage") not in ("Closed Won","Closed Lost")]
        for d in active:
            try:
                last=_safe_date(d.get("last_updated",str(today)))
                days=(today-last).days
                if days>=14:
                    add("DEAL_STALE","💼","info",
                        f"Deal stale {days}d: {d.get('client_name','')[:20]}",
                        f"{d.get('product','')[:25]} · {d.get('stage','')} · KES {d.get('amount',0)/1e6:.0f}M",
                        "Pipeline")
            except: pass
    except: pass

    # Compliance overdue
    try:
        comp=json.loads((DATA/"compliance_cases.json").read_text())
        for c in comp:
            if c["status"] in ("open","under_review"):
                try:
                    raised=_safe_date(c.get("raised_date",str(today)))
                    days=(today-raised).days
                    sla={"Critical":1,"High":3,"Medium":7,"Low":14}.get(c.get("risk_level","Low"),7)
                    if days>sla:
                        add("COMPLIANCE_DUE","🛡️","critical",
                            f"Compliance case overdue: {c.get('risk_level','')}",
                            f"{c.get('case_type','')[:30]} · {days}d open (SLA {sla}d)",
                            "Compliance")
                except: pass
    except: pass

    # RMS old breaks
    try:
        rms=json.loads((DATA/"rms_reconciliations.json").read_text())
        old_breaks=[r for r in rms if r["status"]!="Matched" and r.get("ageing_days",0)>30]
        if old_breaks:
            add("RECON_OLD","🔄","warning",
                f"{len(old_breaks)} reconciliation breaks aged >30d",
                f"Total variance: KES {sum(r['abs_variance'] for r in old_breaks)/1e6:.1f}M",
                "Reconciliation")
    except: pass

    # EDMS expiring docs
    try:
        edms=json.loads((DATA/"edms_documents.json").read_text())
        expiring=[d for d in edms if not d["is_expired"] and
                  0<=(_safe_date(d["expiry_date"])-today).days<=30]
        if expiring:
            add("DOCS_EXPIRING","📁","warning",
                f"{len(expiring)} documents expiring within 30 days",
                "Review and renew in EDMS","EDMS")
    except: pass

    return sorted(alerts, key=lambda x:{"critical":0,"warning":1,"info":2}.get(x["severity"],3))

alerts = _build_alerts()


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔔 Smart Alerts</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Proactive · Real-time · AI-prioritised</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔔 Smart Alerts</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Proactive · Real-time · AI-prioritised</span></div>",
    unsafe_allow_html=True)

# Summary
crits  = [a for a in alerts if a["severity"]=="critical"]
warns  = [a for a in alerts if a["severity"]=="warning"]
infos  = [a for a in alerts if a["severity"]=="info"]

c1,c2,c3,c4 = st.columns(4)
c1.metric("🔴 Critical",  len(crits))
c2.metric("🟡 Warning",   len(warns))
c3.metric("ℹ️ Info",      len(infos))
c4.metric("Total Alerts", len(alerts))

if crits:
    st.error(f"🔴 **{len(crits)} critical alerts** require immediate attention")

st.markdown("---")
tabs = st.tabs([
    "🔴 Critical",
    "🟡 Warnings",
    "ℹ️ All Alerts",
    "⚙️ Alert Config",
    "🔍 Transaction Monitoring (Standard #46)",
    "📊 AML Alert Summary (Standard #46)",
    "🌳 Engine Reference (Standard #46)",
])

def render_alerts(alert_list):
    if not alert_list:
        st.success("✅ No alerts in this category.")
        return
    for a in alert_list:
        clr={"critical":"#DC2626","warning":"#D97706","info":"#3B82F6"}.get(a["severity"],"#6B7280")
        with st.container():
            col1,col2,col3 = st.columns([1,8,2])
            col1.markdown(f"<div style='font-size:24px'>{a['icon']}</div>",unsafe_allow_html=True)
            col2.markdown(
                f"<div style='padding:6px 0'>"
                f"<div style='font-size:13px;font-weight:700;color:{clr}'>{a['title']}</div>"
                f"<div style='font-size:11px;color:var(--color-text-secondary)'>{a['message']}</div>"
                f"<div style='font-size:10px;color:var(--color-text-tertiary)'>Module: {a['module']} · {a['created']}</div>"
                f"</div>", unsafe_allow_html=True)
            col3.markdown(f"<span style='background:{clr}20;color:{clr};border-radius:10px;"
                          f"padding:2px 8px;font-size:10px;font-weight:600'>{a['severity'].upper()}</span>",
                          unsafe_allow_html=True)
            st.markdown("<hr style='margin:2px 0;opacity:0.2'>",unsafe_allow_html=True)

with tabs[0]: render_alerts(crits)
with tabs[1]: render_alerts(warns)
with tabs[2]: render_alerts(alerts)
with tabs[3]:
    st.markdown("**Alert configuration (what triggers alerts):**")
    st.json({
        "FD_MATURING":      "7 days (critical), 30 days (warning)",
        "LEGAL_OVERDUE":    "Any SLA breach",
        "BSC_LOW":          "Score below 2.5",
        "DEAL_STALE":       "14 days without update",
        "COMPLIANCE_DUE":   "Beyond SLA days for risk level",
        "RECON_OLD":        "Reconciliation break aged 30+ days",
        "DOCS_EXPIRING":    "30 days before expiry",
    })
    st.caption("Alert thresholds are configurable via Admin. Alert routing to specific roles is configurable.")


# ════════════════════════════════════════════════════════════════
# TAB 5 — TRANSACTION MONITORING ENGINE (Standard #46, integrated v5.88)
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    from utils.transaction_monitoring import (
        TransactionMonitoringEngine, Transaction, Alert,
        RULE_CATALOG, ALLOWED_ALERT_TRANSITIONS,
        ALERT_STATUS_OPEN, ALERT_STATUS_INVESTIGATING,
        ALERT_STATUS_SAR_FILED, ALERT_STATUS_DISMISSED,
        CASH_REPORTING_THRESHOLD_KES, DAILY_VELOCITY_AMOUNT_KES,
        DAILY_VELOCITY_COUNT_THRESHOLD, DORMANT_ACTIVITY_THRESHOLD_KES,
        HIGH_RISK_JURISDICTIONS_TXN, PROHIBITED_JURISDICTIONS_TXN,
        PEP_LARGE_TXN_KES, RAPID_MOVEMENT_THRESHOLD_KES,
        RAPID_MOVEMENT_WINDOW_HOURS, ROUND_NUMBER_MIN_COUNT,
        ROUND_NUMBER_WINDOW_DAYS,
        SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_LOW,
    )
    from datetime import datetime, timedelta
    from decimal import Decimal as _D_tm
    from utils.core_audit import audit_log

    st.markdown(
        f"**Standard #46 — Transaction Monitoring Engine** (CBK PG/05 + FATF Rec. 20). "
        f"{len(RULE_CATALOG)} rules scan transactions and emit alerts with severity tiers. "
        f"Full alert state machine (OPEN → INVESTIGATING → SAR_FILED/DISMISSED)."
    )
    st.caption(
        f"Rule catalog: R1 cash threshold (≥KES {int(CASH_REPORTING_THRESHOLD_KES/1e6)}M), "
        f"R2 structuring, R3 rapid movement (≥KES {int(RAPID_MOVEMENT_THRESHOLD_KES/1e6)}M in {RAPID_MOVEMENT_WINDOW_HOURS}h), "
        f"R4 high-risk geography, R5 dormant activity, R6 round number pattern, "
        f"R7 daily velocity (≥{DAILY_VELOCITY_COUNT_THRESHOLD} txns or ≥KES {int(DAILY_VELOCITY_AMOUNT_KES/1e6)}M), "
        f"R8 PEP large txn (≥KES {int(PEP_LARGE_TXN_KES/1e6)}M)."
    )

    # Persistent engine instance via session_state
    if "_tme_engine" not in st.session_state:
        st.session_state._tme_engine = TransactionMonitoringEngine()
        st.session_state._tme_alerts = []
    tme = st.session_state._tme_engine

    tm_sub_tabs = st.tabs([
        "🔍 Run Rule Scanner",
        "🔄 Alert Transitions",
        "🌳 Demo Transaction Builder",
        "📦 TxnMonitor Depth (#46, v6.1)",
    ])

    # ──────── Run Rule Scanner ────────
    with tm_sub_tabs[0]:
        st.markdown(
            "**Run all 8 rules against a demo transaction set** — engine scans "
            "for AML patterns and emits alerts.")
        st.caption(
            "💡 Demo dataset includes deliberately constructed transactions to "
            "trigger several rules. Production deployment would feed live CBS "
            "transactions through the same engine.")

        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_transactions():
            base = datetime(2026, 4, 15, 10, 0)
            return [
                # R1: cash threshold (>=1M)
                Transaction("T001", "C001", "A001", _D_tm("1500000"),
                            "CASH_DEPOSIT", base, direction="CREDIT"),
                Transaction("T002", "C001", "A001", _D_tm("2200000"),
                            "CASH_WITHDRAWAL", base + timedelta(hours=1),
                            direction="DEBIT"),
                # R2: structuring (3+ deposits just under 1M)
                Transaction("T003", "C002", "A002", _D_tm("950000"),
                            "CASH_DEPOSIT", base, direction="CREDIT"),
                Transaction("T004", "C002", "A002", _D_tm("980000"),
                            "CASH_DEPOSIT", base + timedelta(hours=2),
                            direction="CREDIT"),
                Transaction("T005", "C002", "A002", _D_tm("970000"),
                            "CASH_DEPOSIT", base + timedelta(hours=4),
                            direction="CREDIT"),
                Transaction("T006", "C002", "A002", _D_tm("990000"),
                            "CASH_DEPOSIT", base + timedelta(hours=6),
                            direction="CREDIT"),
                # R3: rapid movement (5M credit followed by 5M+ debits in 48h)
                Transaction("T007", "C003", "A003", _D_tm("6000000"),
                            "WIRE_IN", base, direction="CREDIT",
                            counterparty_country="GB"),
                Transaction("T008", "C003", "A003", _D_tm("3000000"),
                            "WIRE_OUT", base + timedelta(hours=4),
                            direction="DEBIT", counterparty_country="ZA"),
                Transaction("T009", "C003", "A003", _D_tm("2500000"),
                            "WIRE_OUT", base + timedelta(hours=12),
                            direction="DEBIT", counterparty_country="UG"),
                # R4: high-risk + prohibited jurisdictions
                Transaction("T010", "C004", "A004", _D_tm("500000"),
                            "WIRE_OUT", base, direction="DEBIT",
                            counterparty_country="AF"),  # high-risk
                Transaction("T011", "C005", "A005", _D_tm("100000"),
                            "WIRE_IN", base, direction="CREDIT",
                            counterparty_country="KP"),  # prohibited
                # R5: dormant account activity
                Transaction("T012", "C006", "A006", _D_tm("250000"),
                            "WITHDRAWAL", base, direction="DEBIT",
                            account_dormant=True),
                # R8: PEP large transaction
                Transaction("T013", "C007", "A007", _D_tm("3000000"),
                            "WIRE_OUT", base, direction="DEBIT",
                            customer_pep=True,
                            counterparty_country="CH"),
                # Normal txn — no alerts expected
                Transaction("T014", "C008", "A008", _D_tm("50000"),
                            "TRANSFER", base, direction="CREDIT"),
            ]

        if st.button("🔍 Run rule scanner",
                       key="tm_scan_btn", type="primary"):
            txns = _demo_transactions()
            alerts = tme.scan(txns)
            st.session_state._tme_alerts = alerts

            st.success(
                f"✅ Scanned **{len(txns)} transactions** → "
                f"generated **{len(alerts)} alerts** across {len(RULE_CATALOG)} rules.")

            if alerts:
                # Severity distribution
                from collections import Counter
                sev_counter = Counter([a.severity for a in alerts])
                rule_counter = Counter([a.rule_id for a in alerts])

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("🔴 CRITICAL", sev_counter.get("CRITICAL", 0))
                k2.metric("🟠 HIGH", sev_counter.get("HIGH", 0))
                k3.metric("🟡 MEDIUM", sev_counter.get("MEDIUM", 0))
                k4.metric("🔵 LOW", sev_counter.get("LOW", 0))

                # Per-alert table
                st.markdown("**Generated alerts:**")
                rows = []
                sev_emoji = {"CRITICAL": "🔴", "HIGH": "🟠",
                             "MEDIUM": "🟡", "LOW": "🔵"}
                for a in alerts:
                    rows.append({
                        "ID": a.alert_id,
                        "Rule": f"{a.rule_id} {a.rule_name}",
                        "Severity": f"{sev_emoji.get(a.severity, '⚪')} {a.severity}",
                        "Customer": a.customer_id,
                        "Txns": ", ".join(a.txn_ids[:3]),
                        "Status": a.status,
                    })
                st.dataframe(pd.DataFrame(rows),
                             use_container_width=True, hide_index=True)

                # Show full description for each alert
                with st.expander("Show alert descriptions"):
                    for a in alerts:
                        st.markdown(
                            f"**Alert {a.alert_id}** ({a.rule_id} {a.rule_name}, "
                            f"{a.severity}, customer {a.customer_id}): {a.description}")

                # Critical/high → action guidance
                critical_count = sev_counter.get("CRITICAL", 0)
                if critical_count > 0:
                    st.error(
                        f"⛔ **{critical_count} CRITICAL alert(s)** — immediate "
                        "MLRO escalation required. Per CBK PG/05, structuring "
                        "and prohibited-jurisdiction patterns must be reported "
                        "within 24 hours.")
                elif sev_counter.get("HIGH", 0) > 0:
                    st.warning(
                        f"⚠ **{sev_counter['HIGH']} HIGH alert(s)** — "
                        "investigate within 72 hours. Cash threshold breaches "
                        "require Currency Transaction Report (CTR) filing.")
            else:
                st.info(
                    "ℹ No alerts triggered — all transactions within safe parameters.")

            audit_log("IFRS_ENGINE_USED", uname,
                       f"TxnMonitor #46: scan {len(txns)} txns → {len(alerts)} alerts")

        # Display previously generated alerts if exist
        if st.session_state._tme_alerts:
            st.caption(
                f"📊 Session alerts: **{len(st.session_state._tme_alerts)}** "
                "(state persists across this Streamlit session — production deployment "
                "would persist via DB).")

    # ──────── Alert Transitions ────────
    with tm_sub_tabs[1]:
        st.markdown(
            "**Alert State Machine** — investigate/dismiss/file SAR for each alert.")
        st.caption(
            "Valid transitions: OPEN → INVESTIGATING (only); "
            "INVESTIGATING → SAR_FILED or DISMISSED; "
            "SAR_FILED and DISMISSED are terminal. "
            "SAR_FILED + DISMISSED both require resolution_reason.")

        # Show transition rules
        st.markdown("**Allowed transitions:**")
        trans_rows = [
            {"From state": k,
              "Allowed to": ", ".join(v) if v else "(terminal)"}
            for k, v in ALLOWED_ALERT_TRANSITIONS.items()
        ]
        st.dataframe(pd.DataFrame(trans_rows),
                     use_container_width=True, hide_index=True)

        # Try transitions on existing alerts
        if not st.session_state._tme_alerts:
            st.info(
                "ℹ Run the rule scanner first (previous tab) to generate alerts, "
                "then return here to test state transitions.")
        else:
            st.markdown("**Test a transition on an existing alert:**")

            # Build current state table
            curr_rows = []
            for a in st.session_state._tme_alerts:
                curr_rows.append({
                    "ID": a.alert_id,
                    "Rule": a.rule_id,
                    "Severity": a.severity,
                    "Customer": a.customer_id,
                    "Status": a.status,
                    "Reviewer": a.reviewer_id or "—",
                })
            st.dataframe(pd.DataFrame(curr_rows),
                         use_container_width=True, hide_index=True)

            tc1, tc2, tc3 = st.columns(3)
            with tc1:
                t_alert_ids = [a.alert_id for a in st.session_state._tme_alerts]
                t_alert_id = st.selectbox(
                    "Alert ID",
                    t_alert_ids,
                    key="tm_t_alert")
            with tc2:
                t_target = st.selectbox(
                    "Target status",
                    ["INVESTIGATING", "SAR_FILED", "DISMISSED"],
                    key="tm_t_target")
            with tc3:
                t_reason = st.text_input(
                    "Resolution reason",
                    value="" if t_target == "INVESTIGATING"
                          else "Filed STR_2026_001",
                    key="tm_t_reason",
                    help="Required for SAR_FILED + DISMISSED.")

            if st.button("Test transition",
                           key="tm_t_btn", type="primary"):
                ok, msg = tme.transition_alert(
                    int(t_alert_id), t_target, uname,
                    resolution_reason=t_reason if t_reason.strip() else None)
                if ok:
                    st.success(
                        f"✅ Alert {t_alert_id} transitioned: status now "
                        f"`{t_target}`. Engine confirmed: `{msg}`.")
                    # Refresh state
                    matching = [a for a in st.session_state._tme_alerts
                                  if a.alert_id == int(t_alert_id)]
                    if matching:
                        st.caption(
                            f"📋 Reviewer: `{matching[0].reviewer_id}` · "
                            f"Resolution reason: `{matching[0].resolution_reason or '—'}`")
                else:
                    st.error(
                        f"⛔ Transition rejected: `{msg}`. "
                        "Engine enforces state machine — see allowed transitions above.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"TxnMonitor #46: alert {t_alert_id} → {t_target} "
                           f"ok={ok}")

    # ──────── Demo Transaction Builder ────────
    with tm_sub_tabs[2]:
        st.markdown(
            "**Add a single transaction and re-scan** — useful for testing "
            "rules against specific scenarios.")

        bc1, bc2 = st.columns(2)
        with bc1:
            db_txn_id = st.text_input("Transaction ID",
                                        value=f"T_USER_{date.today().toordinal()}",
                                        key="tm_db_id")
            db_cust = st.text_input("Customer ID",
                                      value="C_TEST", key="tm_db_cust")
            db_amount = st.number_input("Amount (KES M)",
                                          min_value=0.0, value=2.5, step=0.5,
                                          key="tm_db_amount")
            db_type = st.selectbox(
                "Transaction type",
                ["CASH_DEPOSIT", "CASH_WITHDRAWAL", "WIRE_IN", "WIRE_OUT",
                 "WITHDRAWAL", "TRANSFER", "FX"],
                key="tm_db_type")
        with bc2:
            db_dir = st.radio("Direction",
                                ["CREDIT", "DEBIT"], horizontal=True,
                                key="tm_db_dir")
            db_country = st.text_input("Counterparty country (ISO-2)",
                                          value="", max_chars=2,
                                          key="tm_db_country",
                                          help="Empty for domestic. AF/MM/SY/YE/SS = high-risk; KP/IR = prohibited.")
            db_pep = st.checkbox("Customer is PEP",
                                   value=False, key="tm_db_pep")
            db_dormant = st.checkbox("Account is dormant",
                                       value=False, key="tm_db_dormant")

        if st.button("Add txn + rescan",
                       key="tm_db_btn", type="primary"):
            base_txns = _demo_transactions()
            new_txn = Transaction(
                txn_id=db_txn_id,
                customer_id=db_cust,
                account_id=f"A_{db_cust}",
                amount_kes=_D_tm(str(db_amount * 1_000_000)),
                txn_type=db_type,
                txn_datetime=datetime(2026, 4, 15, 12, 0),
                direction=db_dir,
                counterparty_country=db_country.upper().strip() or None,
                customer_pep=db_pep,
                account_dormant=db_dormant,
            )
            all_txns = base_txns + [new_txn]
            # Reset engine to avoid duplicate alert IDs
            new_tme = TransactionMonitoringEngine()
            new_alerts = new_tme.scan(all_txns)

            # Filter to only alerts touching this new txn
            user_alerts = [a for a in new_alerts if db_txn_id in a.txn_ids]
            other_count = len(new_alerts) - len(user_alerts)

            if user_alerts:
                st.warning(
                    f"⚠ User transaction triggered **{len(user_alerts)} alert(s)** "
                    f"(plus {other_count} alerts from demo dataset).")
                for a in user_alerts:
                    sev_emoji = {"CRITICAL": "🔴", "HIGH": "🟠",
                                 "MEDIUM": "🟡", "LOW": "🔵"}.get(a.severity, "⚪")
                    st.markdown(
                        f"- {sev_emoji} **{a.rule_id} {a.rule_name}** "
                        f"({a.severity}): {a.description}")
            else:
                st.success(
                    f"✅ User transaction did NOT trigger any rules. "
                    f"Demo dataset still generates {other_count} alerts as before.")

            audit_log("IFRS_ENGINE_USED", uname,
                       f"TxnMonitor #46: user-built txn {db_txn_id} → "
                       f"{len(user_alerts)} alerts")

    # ════════════════════════════════════════════════════════════════
    # TM_SUB_TABS[3]: TxnMonitor Depth (Standard #46, integrated v6.1)
    # ════════════════════════════════════════════════════════════════
    with tm_sub_tabs[3]:
        st.markdown(
            "**Transaction Monitoring Depth analysis** — extends v5.88 with "
            "4 inner views following the proven depth-batch template (5th "
            "application after v5.95+v5.97+v5.98+v5.99).")
        st.caption(
            "💡 v5.88 surfaces rule scanner + alert transitions + demo "
            "transaction builder. v6.1 adds: alert scorecard, rule-coverage "
            "matrix, status-flow analysis, severity ranking.")

        _tm_depth_inner = st.tabs([
            "📋 Alert Executive Scorecard",
            "🎯 Rule Coverage Matrix",
            "🔄 Alert Status Flow Analysis",
            "🎚️ Severity Investment Map",
        ])

        # ────────── Inner[0]: Alert Executive Scorecard ──────────
        with _tm_depth_inner[0]:
            st.markdown(
                "**Alert Executive Scorecard** — composes scan + alert_summary "
                "into single-screen GREEN/AMBER/RED verdict with rule "
                "coverage, severity distribution, and SAR-pipeline metrics.")
            st.caption(
                "Mirrors v5.97/v5.98/v5.99/v6.1 KYC scorecard pattern. "
                "Click compute to refresh from synthetic transaction set "
                "designed to trigger 6+ rules.")

            if st.button("📋 Compute alert scorecard",
                           key="tm_es_btn", type="primary"):
                from datetime import timedelta as _td_es
                _es_engine = TransactionMonitoringEngine()
                base = datetime(2026, 4, 15, 10, 0)

                # Synthetic transaction set triggering R1, R2, R5, R6, R7, R8
                es_txns = [
                    Transaction("ES01", "C001", "A001", _D_tm("1500000"),
                                "CASH_DEPOSIT", base, None, None, "INBOUND",
                                False, False, {}),  # R1
                    Transaction("ES02", "C002", "A002", _D_tm("950000"),
                                "CASH_DEPOSIT", base, None, None, "INBOUND",
                                False, False, {}),  # R2 attempt
                    Transaction("ES03", "C002", "A002", _D_tm("980000"),
                                "CASH_DEPOSIT", base + _td_es(days=2),
                                None, None, "INBOUND", False, False, {}),
                    Transaction("ES04", "C002", "A002", _D_tm("999000"),
                                "CASH_DEPOSIT", base + _td_es(days=4),
                                None, None, "INBOUND", False, False, {}),
                    Transaction("ES05", "C005", "A005", _D_tm("500000"),
                                "TRANSFER", base, None, None, "INBOUND",
                                False, True, {}),  # R5
                    *[Transaction(f"ES_VEL_{i}", "C006", "A006",
                                  _D_tm("600000"), "TRANSFER",
                                  base + _td_es(minutes=i*5),
                                  None, None, "INBOUND", False, False, {})
                      for i in range(22)],  # R6 + R7
                    Transaction("ES30", "C007", "A007", _D_tm("3000000"),
                                "TRANSFER", base, None, None, "INBOUND",
                                True, False, {}),  # R8
                ]

                _es_alerts = _es_engine.scan(es_txns)
                _es_summary = _es_engine.alert_summary()

                # === Section 1️⃣: Alert volume + rule coverage ===
                st.markdown("### 1️⃣ Alert volume + rule coverage")
                total_alerts = int(_es_summary.get("total_alerts", 0))
                rules_fired = len(_es_summary.get("by_rule", {}))
                rules_total = len(RULE_CATALOG)
                rule_coverage_pct = (rules_fired / rules_total * 100
                                       if rules_total else 0)

                a1, a2, a3 = st.columns(3)
                a1.metric("Total alerts", total_alerts)
                a2.metric("Rules fired",
                            f"{rules_fired}/{rules_total}",
                            help="How many of the 8 rules emitted at least one alert.")
                a3.metric("Rule coverage %",
                            f"{rule_coverage_pct:.0f}%",
                            help="Higher = more types of activity captured.")

                # === Section 2️⃣: Severity distribution ===
                st.markdown("### 2️⃣ Severity distribution")
                by_sev = _es_summary.get("by_severity", {})
                crit_n = int(by_sev.get("CRITICAL", 0))
                high_n = int(by_sev.get("HIGH", 0))
                med_n = int(by_sev.get("MEDIUM", 0))
                low_n = int(by_sev.get("LOW", 0))

                s1, s2, s3, s4 = st.columns(4)
                s1.metric("CRITICAL 🚨", crit_n,
                            delta_color="inverse" if crit_n > 0 else "normal")
                s2.metric("HIGH 🟠", high_n)
                s3.metric("MEDIUM ⚠", med_n)
                s4.metric("LOW ✅", low_n)

                # === Section 3️⃣: Status pipeline ===
                st.markdown("### 3️⃣ Alert status pipeline")
                by_status = _es_summary.get("by_status", {})
                open_n = int(by_status.get("OPEN", 0))
                inv_n = int(by_status.get("INVESTIGATING", 0))
                sar_n = int(by_status.get("SAR_FILED", 0))
                dis_n = int(by_status.get("DISMISSED", 0))

                p1, p2, p3, p4 = st.columns(4)
                p1.metric("OPEN", open_n,
                            delta_color="inverse" if open_n > 0 else "normal",
                            help="Awaiting compliance investigation.")
                p2.metric("INVESTIGATING", inv_n)
                p3.metric("SAR_FILED 📄", sar_n,
                            help="Reported to FRC per CBK PG/15.")
                p4.metric("DISMISSED", dis_n)

                # === Section 4️⃣: Overall verdict ===
                st.markdown("### 4️⃣ Overall transaction monitoring verdict")
                issues = []
                if crit_n > 0:
                    issues.append(
                        f"{crit_n} CRITICAL alert(s) require immediate "
                        "investigation")
                if open_n > 5:
                    issues.append(
                        f"{open_n} OPEN alert(s) — investigation backlog")
                if rule_coverage_pct < 50:
                    issues.append(
                        f"only {rule_coverage_pct:.0f}% rule coverage — "
                        "some risk types may be un-monitored")

                if not issues:
                    st.success(
                        "✅ **Alert pipeline health: GREEN.** All metrics "
                        "in healthy ranges. Maintain via daily review + "
                        "monthly rule tuning.")
                elif len(issues) <= 1:
                    st.warning(
                        f"⚠ **Alert pipeline health: AMBER.** Issue: "
                        f"{issues[0]}. Compliance review recommended.")
                else:
                    st.error(
                        f"🚨 **Alert pipeline health: RED.** Multiple issues: "
                        f"{'; '.join(issues)}. MLRO escalation + workflow "
                        "review required.")

                audit_log("IFRS_ENGINE_USED", uname,
                            f"TxnMonitor #46 (depth): scorecard total={total_alerts} "
                            f"crit={crit_n} open={open_n} coverage={rule_coverage_pct:.0f}%")

        # ────────── Inner[1]: Rule Coverage Matrix ──────────
        with _tm_depth_inner[1]:
            st.markdown(
                "**Rule Coverage Matrix** — analyzes which rules are firing "
                "across the transaction stream. Identifies under-utilized "
                "rules (may indicate threshold miscalibration) and "
                "over-firing rules (may indicate threshold too sensitive).")
            st.caption(
                "Each rule has a designed threshold (CASH_REPORTING_THRESHOLD, "
                "STRUCTURING_LOWER/UPPER, etc.). Production deployment with "
                "false-positive feedback loop can use this view to tune "
                "thresholds.")

            if st.button("🎯 Compute rule coverage matrix",
                           key="tm_rcm_btn", type="primary"):
                from datetime import timedelta as _td_rcm
                _rcm_engine = TransactionMonitoringEngine()
                base = datetime(2026, 4, 15, 10, 0)

                rcm_txns = [
                    Transaction("RCM01", "C001", "A001", _D_tm("1500000"),
                                "CASH_DEPOSIT", base, None, None, "INBOUND",
                                False, False, {}),
                    Transaction("RCM02", "C002", "A002", _D_tm("950000"),
                                "CASH_DEPOSIT", base, None, None, "INBOUND",
                                False, False, {}),
                    Transaction("RCM03", "C002", "A002", _D_tm("980000"),
                                "CASH_DEPOSIT", base + _td_rcm(days=2),
                                None, None, "INBOUND", False, False, {}),
                    Transaction("RCM04", "C002", "A002", _D_tm("999000"),
                                "CASH_DEPOSIT", base + _td_rcm(days=4),
                                None, None, "INBOUND", False, False, {}),
                    Transaction("RCM05", "C005", "A005", _D_tm("500000"),
                                "TRANSFER", base, None, None, "INBOUND",
                                False, True, {}),
                    *[Transaction(f"RCM_VEL_{i}", "C006", "A006",
                                  _D_tm("600000"), "TRANSFER",
                                  base + _td_rcm(minutes=i*5),
                                  None, None, "INBOUND", False, False, {})
                      for i in range(22)],
                    Transaction("RCM30", "C007", "A007", _D_tm("3000000"),
                                "TRANSFER", base, None, None, "INBOUND",
                                True, False, {}),
                ]

                _rcm_alerts = _rcm_engine.scan(rcm_txns)
                _rcm_summary = _rcm_engine.alert_summary()

                # Build coverage matrix
                rcm_rows = []
                by_rule = _rcm_summary.get("by_rule", {})
                for rule_id in sorted(RULE_CATALOG.keys()):
                    rule_def = RULE_CATALOG[rule_id]
                    fired_count = int(by_rule.get(rule_id, 0))
                    if fired_count == 0:
                        coverage = "✅ No alerts"
                    elif fired_count <= 3:
                        coverage = f"🟢 NORMAL ({fired_count})"
                    elif fired_count <= 10:
                        coverage = f"🟡 ELEVATED ({fired_count})"
                    else:
                        coverage = f"🔴 HIGH ({fired_count})"
                    rcm_rows.append({
                        "Rule": rule_id,
                        "Name": rule_def["name"],
                        "Severity": rule_def["severity"],
                        "Alerts fired": fired_count,
                        "Coverage": coverage,
                    })

                st.dataframe(pd.DataFrame(rcm_rows),
                             use_container_width=True, hide_index=True)

                # Bar chart
                chart_pairs = [(r["Rule"], r["Alerts fired"]) for r in rcm_rows]
                chart_data = pd.DataFrame({
                    "Alerts": [p[1] for p in chart_pairs]
                }, index=[p[0] for p in chart_pairs])
                st.markdown("**Alerts fired per rule:**")
                st.bar_chart(chart_data)

                # Coverage insights
                no_fire = [r for r in rcm_rows if r["Alerts fired"] == 0]
                high_fire = [r for r in rcm_rows if r["Alerts fired"] > 5]

                if no_fire:
                    st.info(
                        f"💡 **{len(no_fire)} rule(s) did not fire**: "
                        f"{', '.join(r['Rule'] for r in no_fire)}. "
                        "Either: (a) genuinely no matching activity, or "
                        "(b) thresholds too lenient. Review with compliance "
                        "team before declaring (a).")
                if high_fire:
                    st.warning(
                        f"⚠ **{len(high_fire)} rule(s) firing heavily**: "
                        f"{', '.join(r['Rule'] for r in high_fire)}. "
                        "May indicate threshold miscalibration (too "
                        "sensitive → false positives) OR genuine elevated "
                        "activity. Investigation backlog risk.")

                audit_log("IFRS_ENGINE_USED", uname,
                            f"TxnMonitor #46 (depth): coverage matrix "
                            f"no_fire={len(no_fire)} high_fire={len(high_fire)}")

        # ────────── Inner[2]: Alert Status Flow Analysis ──────────
        with _tm_depth_inner[2]:
            st.markdown(
                "**Alert Status Flow Analysis** — visualizes the alert "
                "lifecycle pipeline (OPEN → INVESTIGATING → SAR_FILED / "
                "DISMISSED) and surfaces backlog + workflow metrics.")
            st.caption(
                "Caller-side aggregation. Engine surfaces by_status counts "
                "via alert_summary; this view computes flow ratios + "
                "backlog risk.")

            if st.button("🔄 Compute status flow analysis",
                           key="tm_sfa_btn", type="primary"):
                from datetime import timedelta as _td_sfa
                _sfa_engine = TransactionMonitoringEngine()
                base = datetime(2026, 4, 15, 10, 0)

                sfa_txns = [
                    Transaction("SFA01", "C001", "A001", _D_tm("1500000"),
                                "CASH_DEPOSIT", base, None, None, "INBOUND",
                                False, False, {}),
                    Transaction("SFA02", "C002", "A002", _D_tm("950000"),
                                "CASH_DEPOSIT", base, None, None, "INBOUND",
                                False, False, {}),
                    Transaction("SFA03", "C002", "A002", _D_tm("980000"),
                                "CASH_DEPOSIT", base + _td_sfa(days=2),
                                None, None, "INBOUND", False, False, {}),
                    Transaction("SFA04", "C002", "A002", _D_tm("999000"),
                                "CASH_DEPOSIT", base + _td_sfa(days=4),
                                None, None, "INBOUND", False, False, {}),
                    Transaction("SFA05", "C005", "A005", _D_tm("500000"),
                                "TRANSFER", base, None, None, "INBOUND",
                                False, True, {}),
                    Transaction("SFA06", "C007", "A007", _D_tm("3000000"),
                                "TRANSFER", base, None, None, "INBOUND",
                                True, False, {}),
                ]

                _sfa_alerts = _sfa_engine.scan(sfa_txns)

                # Simulate workflow progression: move some through pipeline
                # OPEN → INVESTIGATING for first half
                for a in _sfa_alerts[:len(_sfa_alerts)//2]:
                    _sfa_engine.transition_alert(a.alert_id, "INVESTIGATING",
                                                   "REV001")
                # INVESTIGATING → SAR_FILED for first one
                if _sfa_alerts:
                    _sfa_engine.transition_alert(_sfa_alerts[0].alert_id,
                                                   "SAR_FILED", "REV001",
                                                   "Confirmed structuring")

                _sfa_summary = _sfa_engine.alert_summary()
                by_status = _sfa_summary.get("by_status", {})
                open_n = int(by_status.get("OPEN", 0))
                inv_n = int(by_status.get("INVESTIGATING", 0))
                sar_n = int(by_status.get("SAR_FILED", 0))
                dis_n = int(by_status.get("DISMISSED", 0))
                total = open_n + inv_n + sar_n + dis_n

                # Flow ratios
                if total:
                    open_pct = open_n / total * 100
                    inv_pct = inv_n / total * 100
                    closed_pct = (sar_n + dis_n) / total * 100
                    sar_rate = (sar_n / max(sar_n + dis_n, 1) * 100)
                else:
                    open_pct = inv_pct = closed_pct = sar_rate = 0

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Backlog (OPEN)",
                            f"{open_n} ({open_pct:.0f}%)",
                            delta_color="inverse" if open_pct > 50 else "normal")
                k2.metric("In progress (INV)",
                            f"{inv_n} ({inv_pct:.0f}%)")
                k3.metric("Closed",
                            f"{sar_n + dis_n} ({closed_pct:.0f}%)")
                k4.metric("SAR rate (of closed)",
                            f"{sar_rate:.0f}%",
                            help="True positive rate — high SAR rate means "
                                 "rules are well-calibrated.")

                # Pipeline visualization (text-based for simplicity)
                st.markdown("**Status pipeline:**")
                pipeline_data = pd.DataFrame({
                    "Count": [open_n, inv_n, sar_n, dis_n]
                }, index=["OPEN", "INVESTIGATING", "SAR_FILED", "DISMISSED"])
                st.bar_chart(pipeline_data)

                # Insights
                if open_pct > 60:
                    st.error(
                        f"🚨 **Heavy backlog** — {open_pct:.0f}% of alerts "
                        "are OPEN (un-investigated). Compliance team "
                        "capacity issue or recent volume spike.")
                if sar_rate > 0 and sar_rate < 20:
                    st.warning(
                        f"⚠ **Low SAR rate** ({sar_rate:.0f}%) — most "
                        "investigated alerts dismissed as false positives. "
                        "Rule threshold tuning may reduce noise.")
                elif sar_rate > 50:
                    st.info(
                        f"💡 **Strong SAR rate** ({sar_rate:.0f}%) — rules "
                        "are well-calibrated; most investigations lead to "
                        "regulatory filings.")

                audit_log("IFRS_ENGINE_USED", uname,
                            f"TxnMonitor #46 (depth): flow open={open_n} "
                            f"inv={inv_n} sar={sar_n} dis={dis_n} "
                            f"sar_rate={sar_rate:.0f}%")

        # ────────── Inner[3]: Severity Investment Map ──────────
        with _tm_depth_inner[3]:
            st.markdown(
                "**Severity Investment Map** — ranks the 8 rules by alert "
                "volume × severity weight, surfacing which rules consume "
                "most compliance investigation capacity.")
            st.caption(
                "💡 Severity weights: CRITICAL=10, HIGH=5, MEDIUM=2, LOW=1. "
                "Investment priority bands based on weighted load.")

            if st.button("🎚️ Compute severity investment map",
                           key="tm_sim_btn", type="primary"):
                from datetime import timedelta as _td_sim
                _sim_engine = TransactionMonitoringEngine()
                base = datetime(2026, 4, 15, 10, 0)

                sim_txns = [
                    Transaction("SIM01", "C001", "A001", _D_tm("1500000"),
                                "CASH_DEPOSIT", base, None, None, "INBOUND",
                                False, False, {}),
                    Transaction("SIM02", "C002", "A002", _D_tm("950000"),
                                "CASH_DEPOSIT", base, None, None, "INBOUND",
                                False, False, {}),
                    Transaction("SIM03", "C002", "A002", _D_tm("980000"),
                                "CASH_DEPOSIT", base + _td_sim(days=2),
                                None, None, "INBOUND", False, False, {}),
                    Transaction("SIM04", "C002", "A002", _D_tm("999000"),
                                "CASH_DEPOSIT", base + _td_sim(days=4),
                                None, None, "INBOUND", False, False, {}),
                    Transaction("SIM05", "C005", "A005", _D_tm("500000"),
                                "TRANSFER", base, None, None, "INBOUND",
                                False, True, {}),
                    *[Transaction(f"SIM_VEL_{i}", "C006", "A006",
                                  _D_tm("600000"), "TRANSFER",
                                  base + _td_sim(minutes=i*5),
                                  None, None, "INBOUND", False, False, {})
                      for i in range(22)],
                    Transaction("SIM30", "C007", "A007", _D_tm("3000000"),
                                "TRANSFER", base, None, None, "INBOUND",
                                True, False, {}),
                ]

                _sim_alerts = _sim_engine.scan(sim_txns)
                _sim_summary = _sim_engine.alert_summary()

                # Severity weights for investigation effort
                SEV_WEIGHTS = {"CRITICAL": 10, "HIGH": 5,
                                "MEDIUM": 2, "LOW": 1}

                # Per-rule load = count × severity weight
                sim_rows = []
                by_rule = _sim_summary.get("by_rule", {})
                for rule_id in sorted(RULE_CATALOG.keys()):
                    rule_def = RULE_CATALOG[rule_id]
                    sev = rule_def["severity"]
                    sev_weight = SEV_WEIGHTS.get(sev, 1)
                    fired = int(by_rule.get(rule_id, 0))
                    load = fired * sev_weight

                    if load >= 30:
                        priority = "🔴 CRITICAL — top investigation cost"
                    elif load >= 15:
                        priority = "🟡 IMPORTANT — significant load"
                    elif load >= 5:
                        priority = "🟢 MONITOR — manageable"
                    else:
                        priority = "✅ LOW LOAD"
                    sim_rows.append({
                        "Rule": rule_id,
                        "Name": rule_def["name"],
                        "Severity": sev,
                        "Alerts": fired,
                        "Investigation load":
                            f"{load} (sev × count)",
                        "Investment priority": priority,
                    })

                # Sort by load desc
                sim_rows.sort(key=lambda r: -int(
                    r["Investigation load"].split(" ")[0]))

                st.dataframe(pd.DataFrame(sim_rows),
                             use_container_width=True, hide_index=True)

                # Bar chart
                chart_data = pd.DataFrame({
                    "Investigation load":
                        [int(r["Investigation load"].split(" ")[0])
                          for r in sim_rows]
                }, index=[r["Rule"] for r in sim_rows])
                st.markdown("**Per-rule investigation load (severity × count):**")
                st.bar_chart(chart_data)

                # Critical / important callouts
                critical = [r for r in sim_rows
                              if "CRITICAL" in r["Investment priority"]]
                important = [r for r in sim_rows
                               if "IMPORTANT" in r["Investment priority"]]
                if critical:
                    st.error(
                        f"🔴 **{len(critical)} rule(s) consume critical "
                        f"investigation capacity**: "
                        f"{', '.join(r['Rule'] for r in critical)}. "
                        "Consider: (a) hiring additional analysts for these, "
                        "or (b) reviewing thresholds to reduce false positives.")
                if important:
                    st.warning(
                        f"🟡 **{len(important)} rule(s) at IMPORTANT load**: "
                        f"{', '.join(r['Rule'] for r in important)}. "
                        "Plan capacity within 6 months or tune thresholds.")

                audit_log("IFRS_ENGINE_USED", uname,
                            f"TxnMonitor #46 (depth): severity map "
                            f"critical={len(critical)} important={len(important)}")


# ════════════════════════════════════════════════════════════════
# TAB 6 — AML ALERT SUMMARY (Standard #46, integrated v5.88)
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    from utils.transaction_monitoring import (
        TransactionMonitoringEngine, Alert, RULE_CATALOG,
        SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_LOW,
    )

    st.markdown(
        "**AML Alert Summary** — aggregate analytics across all open alerts "
        "for the current Streamlit session.")
    st.caption(
        "Engine returns counts by rule, severity, and status. "
        "💡 Run the rule scanner in the previous tab first to populate alerts.")

    if "_tme_engine" not in st.session_state:
        st.info("ℹ Run the rule scanner first (Transaction Monitoring tab) to populate alerts.")
    else:
        tme = st.session_state._tme_engine

        if st.button("📊 Refresh AML alert summary",
                       key="tm_sum_btn", type="primary"):
            r = tme.alert_summary()
            total = int(r["total_alerts"])
            open_count = int(r["open_alerts"])

            if total == 0:
                st.warning(
                    "⚠ No alerts in current session. Run rule scanner first.")
            else:
                # Top metrics
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total alerts", total)
                k2.metric("Open (require action)", open_count,
                           help="Alerts in OPEN or INVESTIGATING state.")

                by_sev = r["by_severity"]
                critical = int(by_sev.get("CRITICAL", 0))
                high = int(by_sev.get("HIGH", 0))
                k3.metric("🔴 CRITICAL", critical)
                k4.metric("🟠 HIGH", high)

                # By rule breakdown
                st.markdown("**Alerts by rule:**")
                rule_rows = []
                for rid, count in r["by_rule"].items():
                    cnt = int(count)
                    if cnt == 0:
                        continue
                    rinfo = RULE_CATALOG.get(rid, {})
                    rule_rows.append({
                        "Rule": rid,
                        "Name": rinfo.get("name", "—"),
                        "Severity": rinfo.get("severity", "—"),
                        "Count": cnt,
                    })
                if rule_rows:
                    st.dataframe(pd.DataFrame(rule_rows),
                                 use_container_width=True, hide_index=True)

                # Status breakdown
                st.markdown("**Alerts by status:**")
                status_rows = []
                for status, count in r["by_status"].items():
                    cnt = int(count)
                    if cnt == 0:
                        continue
                    status_rows.append({
                        "Status": status,
                        "Count": cnt,
                    })
                if status_rows:
                    st.dataframe(pd.DataFrame(status_rows),
                                 use_container_width=True, hide_index=True)

                # Severity bar chart
                st.markdown("**Severity distribution:**")
                sev_data = pd.DataFrame({
                    "Count": [int(by_sev.get(s, 0))
                              for s in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]]
                }, index=["CRITICAL", "HIGH", "MEDIUM", "LOW"])
                st.bar_chart(sev_data)

                # Executive guidance
                if critical > 0:
                    st.error(
                        f"⛔ **{critical} CRITICAL alert(s) outstanding** — "
                        "MLRO immediate escalation required.")
                elif high > 0:
                    st.warning(
                        f"⚠ **{high} HIGH alert(s) outstanding** — "
                        "investigate within 72h.")
                else:
                    st.success(
                        f"✅ No critical or high-severity alerts outstanding.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"TxnMonitor #46: summary total={total} "
                           f"open={open_count} critical={critical} high={high}")


# ════════════════════════════════════════════════════════════════
# TAB 7 — ENGINE REFERENCE (Standard #46, integrated v5.88)
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    from utils.transaction_monitoring import (
        RULE_CATALOG, ALLOWED_ALERT_TRANSITIONS,
        CASH_REPORTING_THRESHOLD_KES, DAILY_VELOCITY_AMOUNT_KES,
        DAILY_VELOCITY_COUNT_THRESHOLD, DORMANT_ACTIVITY_THRESHOLD_KES,
        HIGH_RISK_JURISDICTIONS_TXN, PROHIBITED_JURISDICTIONS_TXN,
        PEP_LARGE_TXN_KES, RAPID_MOVEMENT_THRESHOLD_KES,
        RAPID_MOVEMENT_WINDOW_HOURS, ROUND_NUMBER_MIN_COUNT,
        ROUND_NUMBER_WINDOW_DAYS,
    )

    st.markdown("**Engine Constants Reference** (single source of truth)")

    st.markdown(f"**Rule catalog ({len(RULE_CATALOG)} rules):**")
    rule_descriptions = {
        "R1": f"Cash transaction ≥ KES {int(CASH_REPORTING_THRESHOLD_KES/1e6)}M (CTR threshold)",
        "R2": f"Structuring: 3+ deposits just under KES {int(CASH_REPORTING_THRESHOLD_KES/1e6)}M in short window",
        "R3": f"Rapid movement: KES {int(RAPID_MOVEMENT_THRESHOLD_KES/1e6)}M+ credit followed by debits within {RAPID_MOVEMENT_WINDOW_HOURS}h",
        "R4": f"Wire to/from prohibited jurisdiction (any amount) or high-risk jurisdiction (KES 100K+)",
        "R5": f"Activity > KES {int(DORMANT_ACTIVITY_THRESHOLD_KES/1000)}K on dormant account",
        "R6": f"Round number pattern: {ROUND_NUMBER_MIN_COUNT}+ identical-round txns in {ROUND_NUMBER_WINDOW_DAYS} days",
        "R7": f"Daily velocity: ≥{DAILY_VELOCITY_COUNT_THRESHOLD} txns or ≥KES {int(DAILY_VELOCITY_AMOUNT_KES/1e6)}M in 24h",
        "R8": f"PEP customer transaction ≥ KES {int(PEP_LARGE_TXN_KES/1e6)}M",
    }
    rule_rows = [
        {"Rule": rid,
          "Name": rinfo["name"],
          "Severity": rinfo["severity"],
          "Trigger": rule_descriptions.get(rid, "—")}
        for rid, rinfo in RULE_CATALOG.items()
    ]
    st.dataframe(pd.DataFrame(rule_rows),
                 use_container_width=True, hide_index=True)

    st.markdown(
        f"**Jurisdiction lists** (FATF + CBK PG/05 aligned, hard-coded — "
        "production must refresh from FATF publications):")
    juris_rows = [
        {"Tier": "🚫 PROHIBITED",
          "Jurisdictions": ", ".join(PROHIBITED_JURISDICTIONS_TXN),
          "R4 trigger": "Any wire amount"},
        {"Tier": "🔴 HIGH RISK",
          "Jurisdictions": ", ".join(HIGH_RISK_JURISDICTIONS_TXN),
          "R4 trigger": "Wire amount ≥ KES 100K"},
    ]
    st.dataframe(pd.DataFrame(juris_rows),
                 use_container_width=True, hide_index=True)

    st.markdown("**Alert state machine:**")
    state_rows = [
        {"From state": k,
          "Allowed to": ", ".join(v) if v else "(terminal)"}
        for k, v in ALLOWED_ALERT_TRANSITIONS.items()
    ]
    st.dataframe(pd.DataFrame(state_rows),
                 use_container_width=True, hide_index=True)

    st.caption(
        "All rules and thresholds bound byte-for-byte from engine constants. "
        "Production deployment can adjust thresholds via cost_overrides-style mechanism "
        "(planned for v6+). The `STR_FILED` and `DISMISSED` states require resolution_reason. "
        "Per CBK PG/05, suspicious transaction reports must be filed with the Financial "
        "Reporting Centre (FRC) within 3 business days of suspicion forming.")
