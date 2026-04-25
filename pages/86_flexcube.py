"""pages/86_flexcube.py — FLEXCUBE Integration Health.
Connection status, API health, JMS topics, sample queries.
Dept: IT & Digital | KPIs: K109 K110 K111
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log
from utils import flexcube_adapter as fcx

require_access("flexcube_integration")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_it    = any(x in role for x in ("it","tech","digital","system","integration","manager","head","director","chief","cto","cio"))

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

@st.cache_data(ttl=10)
def _events():
    log = DATA / "flexcube_events.json"
    return json.loads(log.read_text(encoding="utf-8")) if log.exists() else []

cfg     = fcx.get_config()
mode    = fcx.get_mode()
events  = _events()

# Health metrics
health = fcx.health_check()
services = health.get("services", {})
n_services    = len(services)
n_up          = sum(1 for s in services.values() if "Up" in str(s.get("status","")) or "Mocked" in str(s.get("status","")))
uptime_pct    = round(n_up/max(n_services,1)*100, 1)
critical_down = [s for s in services.values() if "Down" in str(s.get("status",""))]
err_count_24h = sum(1 for e in events if "error" in (e.get("payload",{}) or {}))
last_event_age_min = 0
if events:
    try:
        from datetime import datetime as _dt
        last_t = _dt.fromisoformat(events[0]["timestamp"].replace("Z",""))
        last_event_age_min = round((_dt.utcnow() - last_t).total_seconds()/60, 1)
    except Exception: pass

st.markdown(
    f"<div style='padding:16px 0 4px'>"
    f"<span style='font-size:22px;font-weight:800'>🔌 FLEXCUBE Integration Health</span>"
    f"<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    f"IT & Digital · {fcx.get_status_badge()} · K109-K111</span></div>",
    unsafe_allow_html=True)

# Mode banner
if mode == "synthetic":
    st.info("🔵 **Synthetic mode active** — All data is generated locally. No connection to real FLEXCUBE. Switch to Mock for integration testing or Live for production.")
elif mode == "mock":
    st.warning("🟡 **Mock mode** — Pretending to call FLEXCUBE APIs but returning synthetic data. Use for integration testing without real credentials.")
else:
    if critical_down:
        st.error(f"🔴 **{len(critical_down)} FLEXCUBE service(s) DOWN** — escalate to Oracle support and Apigee admin")
    else:
        st.success("🟢 **Live mode active** — All FLEXCUBE services healthy")

# KPI strip
m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Mode",            mode.upper())
m2.metric("Services",        f"{n_up}/{n_services}")
m3.metric("Uptime",          f"{uptime_pct}%", delta_color="off" if uptime_pct>=99 else "inverse")
m4.metric("Errors 24h",      err_count_24h, delta_color="inverse" if err_count_24h>5 else "off")
m5.metric("Last event",      f"{last_event_age_min}m ago" if last_event_age_min else "—")

tabs = st.tabs(["🩺 Health","🌐 API Test","📨 JMS Events","🗺️ Architecture","📋 Discovery","⚙️ Config","📈 BSC"])

# ── TAB 0 — Health Dashboard ─────────────────────────────────────
with tabs[0]:
    st.markdown(f"**FLEXCUBE Integration Status — checked {health.get('checked_at','')[:19]}**")
    rows = []
    for name, svc in services.items():
        rows.append({
            "Service":    name,
            "Endpoint":   svc.get("endpoint","")[:50],
            "Status":     svc.get("status",""),
            "Latency":    f"{svc.get('latency_ms',0)}ms" if svc.get('latency_ms') else "—",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if (is_it or is_admin) and st.button("🔄 Run health check now", key="fcx_recheck", type="primary"):
        st.cache_data.clear()
        audit_log("FLEXCUBE_HEALTH_CHECK", uname, f"mode={mode}")
        _bsc_trigger(uname, "K109")
        st.success("✅ Re-check complete"); st.rerun()

    st.markdown("**Compliance Status:**")
    comp = cfg.get("compliance",{})
    cols = st.columns(5)
    for i, (key, val) in enumerate(comp.items()):
        cols[i % 5].metric(key.upper().replace("_"," "), "✅ Yes" if val else "❌ No")

# ── TAB 1 — API Test Console ─────────────────────────────────────
with tabs[1]:
    st.markdown("**Test FLEXCUBE API endpoints** (uses current mode: " + mode.upper() + ")")
    test_type = st.radio("API to test", ["Account Balance","Customer Lookup","Loan Status","RM Portfolio"], horizontal=True, key="fcx_test_type")

    if test_type == "Account Balance":
        c1,c2 = st.columns(2)
        acct = c1.text_input("Account number", "ECO1000000001", key="fcx_acct")
        brh  = c2.text_input("Branch code", "001", key="fcx_brh")
        if st.button("🔎 Query balance", key="fcx_q_bal", type="primary"):
            with st.spinner("Calling FLEXCUBE..."):
                result = fcx.fetch_account_balance(acct, brh)
            st.json(result)
            audit_log("FLEXCUBE_QUERY", uname, f"AccountBalance: {acct}")
            _bsc_trigger(uname, "K110")

    elif test_type == "Customer Lookup":
        cif = st.text_input("Customer CIF", "100000001", key="fcx_cif")
        if st.button("🔎 Query customer", key="fcx_q_cust", type="primary"):
            with st.spinner("Calling FLEXCUBE..."):
                result = fcx.fetch_customer(cif)
            st.json(result)
            audit_log("FLEXCUBE_QUERY", uname, f"Customer: {cif}")
            _bsc_trigger(uname, "K110")

    elif test_type == "Loan Status":
        loan_id = st.text_input("Loan ID", "L0001", key="fcx_loan")
        if st.button("🔎 Query loan", key="fcx_q_loan", type="primary"):
            with st.spinner("Calling FLEXCUBE..."):
                result = fcx.fetch_loan_status(loan_id)
            st.json(result)
            audit_log("FLEXCUBE_QUERY", uname, f"Loan: {loan_id}")
            _bsc_trigger(uname, "K110")

    else:
        rm = st.text_input("RM code", "rm100", key="fcx_rm")
        if st.button("🔎 Query portfolio", key="fcx_q_port", type="primary"):
            with st.spinner("Aggregating portfolio..."):
                result = fcx.fetch_rm_portfolio(rm)
            st.json(result)
            audit_log("FLEXCUBE_QUERY", uname, f"RMPortfolio: {rm}")
            _bsc_trigger(uname, "K110")

    st.caption("These calls go through `utils/flexcube_adapter.py`. In live mode they call real FLEXCUBE REST. In synthetic/mock they read local data.")

# ── TAB 2 — JMS Events ───────────────────────────────────────────
with tabs[2]:
    st.markdown("**Recent integration events** (JMS topics + adapter activity)")
    if events:
        evt_rows = [{
            "Timestamp": e.get("timestamp","")[:19],
            "Topic":     e.get("topic",""),
            "Mode":      e.get("mode","synthetic"),
            "Payload":   str(e.get("payload",""))[:60],
        } for e in events[:50]]
        st.dataframe(pd.DataFrame(evt_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No events captured yet.")

    st.markdown("**Configured JMS topics:**")
    topics = cfg.get("jms_topics",{})
    topic_rows = [{"Event":k.replace("_"," ").title(),"Topic":v} for k,v in topics.items()]
    st.dataframe(pd.DataFrame(topic_rows), use_container_width=True, hide_index=True)

    if (is_it or is_admin):
        st.markdown("**Publish a test event:**")
        c1,c2 = st.columns(2)
        sel_topic = c1.selectbox("Topic", list(topics.values()), key="fcx_pub_topic")
        msg       = c2.text_input("Payload (JSON)", '{"test":"event","ref":"TEST123"}', key="fcx_pub_msg")
        if st.button("📨 Publish event", key="fcx_pub_btn"):
            try:
                payload = json.loads(msg)
            except Exception:
                payload = {"raw": msg}
            ok = fcx.publish_event(sel_topic, payload)
            audit_log("FLEXCUBE_EVENT_PUBLISHED", uname, sel_topic)
            _bsc_trigger(uname, "K111")
            st.success(f"✅ Event {'published' if ok else 'logged'} to {sel_topic}"); st.rerun()

# ── TAB 3 — Architecture Reference ───────────────────────────────
with tabs[3]:
    st.markdown("""
**Reference Integration Architecture** (Ecobank Kenya × Oracle FLEXCUBE):

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Customer         │     │ Apigee Gateway   │     │  FLEXCUBE UBS    │
│ Channels         │────►│ (Google Cloud)   │────►│  Application     │
│ (App, Web,       │     │ OAuth2 + mTLS    │     │  Server          │
│  USSD, ATM)      │     │ Rate limiting    │     │  WebLogic        │
└──────────────────┘     └────────┬─────────┘     └────────┬─────────┘
                                  │                        │
                                  │                        ▼
┌──────────────────┐              │              ┌──────────────────┐
│ A2Z Blueprint    │              │              │ FLEXCUBE Oracle  │
│ MIS 360          │◄─────────────┘              │ Database (TDE)   │
│ (this system)    │                             │ + Read-only DR   │
└────────┬─────────┘                             └──────────────────┘
         │
         │ JMS subscriptions
         ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Oracle Mantas    │     │ KETS / KEPSS     │     │ SWIFT Alliance   │
│ AML Engine       │     │ PesaLink (ISO    │     │ (MT/MX)          │
│                  │     │ 20022) Card      │     │                  │
│                  │     │ Switch (8583)    │     │                  │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

**Standards in use:**
- ISO 20022 — domestic clearing (PesaLink, RTGS via KEPSS)
- ISO 8583  — card/ATM/POS switch
- SWIFT MT/MX — cross-border correspondent
- REST/JSON — Apigee-fronted modern channels
- SOAP/WSDL — legacy integrations
- JMS — async events between FLEXCUBE and dependents

**Security:**
- TLS 1.2+ in transit, TDE AES-256 at rest, HSM-backed keys
- OAuth2 client credentials (Apigee), mTLS for partner integrations
- Data residency: Kenya primary, Ghana DR
- PCI DSS compliant card paths
- Data Protection Act 2019 compliant

**Why this matters for A2Z:**
This MIS reads from FLEXCUBE through the adapter layer. In synthetic mode it
uses local data for demos. In live mode it calls Apigee-fronted FLEXCUBE REST.
The same module code works in all modes — only the adapter changes behavior.
    """)

# ── TAB 4 — Discovery Questions ──────────────────────────────────
with tabs[4]:
    st.markdown("**Pending discovery questions for Ecobank IT:**")
    questions = cfg.get("discovery_questions_pending",[])
    if questions:
        for i, q in enumerate(questions, 1):
            st.markdown(f"  {i}. {q}")
    else:
        st.success("✅ All discovery items resolved.")

    st.markdown("---")
    st.markdown("**Document references consulted:**")
    refs = [
        "Oracle FLEXCUBE UBS Restful Services Usage Guide (F56608_01)",
        "Oracle Banking APIs Host Integration Guide (F56935_01)",
        "Oracle FLEXCUBE — Mantas Integration (F18207_01)",
        "Oracle FLEXCUBE UBS Database Practices 19c R14.4 (F20443_01)",
        "Ecobank–Google Cloud Partnership press release (Jul 2025)",
        "CBK National Payment Strategy 2021–25",
        "CBK Climate Risk Guidance (2023)",
        "Data Protection Act 2019 (Kenya)",
        "ISO 20022, ISO 8583, SWIFT MT/MX standards",
        "PCI DSS v4.0",
    ]
    for r in refs: st.markdown(f"  • {r}")

# ── TAB 5 — Configuration ────────────────────────────────────────
with tabs[5]:
    if is_admin or is_it:
        st.markdown("**FLEXCUBE Integration Configuration:**")
        st.warning("⚠️ Changing mode to LIVE requires valid OAuth2 credentials in environment variables: FLEXCUBE_CLIENT_ID and FLEXCUBE_CLIENT_SECRET")

        c1,c2,c3 = st.columns(3)
        new_mode = c1.selectbox("Mode",
                               ["synthetic","mock","live"],
                               index=["synthetic","mock","live"].index(cfg.get("mode","synthetic")),
                               key="fcx_cfg_mode",
                               help="synthetic = local data | mock = pretend live | live = real APIs")
        new_env  = c2.selectbox("Environment",
                               cfg.get("environments",["dev","sit","uat","prod"]),
                               index=cfg.get("environments",["dev","sit","uat","prod"]).index(cfg.get("active_environment","dev")) if cfg.get("active_environment") in cfg.get("environments",[]) else 0,
                               key="fcx_cfg_env")
        new_ver  = c3.text_input("FCUBS version", cfg.get("fcubs_version","14.7"), key="fcx_cfg_ver")

        st.markdown("**Endpoints:**")
        new_endpoints = {}
        for k, v in cfg.get("endpoints",{}).items():
            new_endpoints[k] = st.text_input(k, v, key=f"fcx_ep_{k}")

        st.markdown("**Timeouts (seconds):**")
        new_timeouts = {}
        c1,c2,c3 = st.columns(3)
        new_timeouts["rest_seconds"] = c1.number_input("REST", 1, 60, int(cfg.get("timeouts",{}).get("rest_seconds",5)), key="fcx_to_rest")
        new_timeouts["soap_seconds"] = c2.number_input("SOAP", 1, 120, int(cfg.get("timeouts",{}).get("soap_seconds",10)), key="fcx_to_soap")
        new_timeouts["batch_seconds"]= c3.number_input("Batch", 30, 1800, int(cfg.get("timeouts",{}).get("batch_seconds",300)), key="fcx_to_batch")

        if st.button("💾 Save FLEXCUBE configuration", key="fcx_cfg_save", type="primary"):
            cfg["mode"] = new_mode
            cfg["active_environment"] = new_env
            cfg["fcubs_version"] = new_ver
            cfg["endpoints"]     = new_endpoints
            cfg["timeouts"]      = new_timeouts
            fcx.save_config(cfg)
            audit_log("FLEXCUBE_CFG_SAVED", uname, f"mode={new_mode}, env={new_env}")
            _bsc_trigger(uname, "K109")
            st.cache_data.clear()
            st.success(f"✅ Configuration saved — mode is now {new_mode.upper()}")
            st.rerun()
    else:
        st.info("Configuration available to IT and Admin only.")

# ── TAB 6 — BSC ──────────────────────────────────────────────────
with tabs[6]:
    bsc_rows = [
        {"KPI":"K109 — FLEXCUBE Uptime",         "Target":"> 99%", "Actual":f"{uptime_pct}%",
         "Status":"🟢" if uptime_pct>=99 else "🟡" if uptime_pct>=95 else "🔴", "Weight":"8%"},
        {"KPI":"K110 — Integration Errors (24h)","Target":"< 5",   "Actual":str(err_count_24h),
         "Status":"🟢" if err_count_24h<5 else "🔴", "Weight":"5%"},
        {"KPI":"K111 — Event Sync Lag (min)",    "Target":"< 5",   "Actual":f"{last_event_age_min}",
         "Status":"🟢" if last_event_age_min<5 else "🟡", "Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows), use_container_width=True, hide_index=True)
    if st.button("🔄 Refresh BSC", key="fcx_bsc", type="primary"):
        _bsc_trigger(uname, "K109")
        st.success("✅ BSC updated"); st.cache_data.clear(); st.rerun()
