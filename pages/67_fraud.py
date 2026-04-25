"""pages/67_fraud.py — Agent Fraud Detection & Transaction Monitoring.
Detects transaction splitting (structuring), velocity anomalies, commission inflation.
CBK alignment: POCAMLA 2009, CBK Prudential Guidelines on Agents.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import defaultdict, Counter
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
        audit_log("BSC_AUTO_UPDATE", username, f"Module action: {kpi}")
    except Exception:
        pass


require_access("fraud_detection")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_risk  = any(x in role for x in ("risk","compliance","fraud","chief risk","agency","operations"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔎 Agent Fraud Detection</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Transaction splitting · Velocity alerts · Commission anomalies · Agent monitoring</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load_alerts():
    p = DATA / "agent_fraud_alerts.json"
    return json.loads(p.read_text()) if p.exists() else []

@st.cache_data(ttl=60)
def _load_txns():
    p = DATA / "agent_transactions.json"
    return json.loads(p.read_text()) if p.exists() else []

alerts = _load_alerts()
txns   = _load_txns()

# Config thresholds
STRUCT_THRESHOLD = cfg("agent_structuring_threshold_kes", 10_000)
VELOCITY_LIMIT   = cfg("agent_velocity_daily_limit", 20)
COMM_THRESHOLD   = cfg("agent_commission_threshold_kes", 100)

high_alerts = [a for a in alerts if a.get("severity") == "High"]
open_alerts = [a for a in alerts if a.get("status") in ("Open","Under Review")]
struct_alerts = [a for a in alerts if "Structuring" in a.get("alert_type","")]

if high_alerts:
    st.error(f"🔴 {len(high_alerts)} HIGH severity alert(s) — immediate investigation required")
if open_alerts:
    st.warning(f"⚠️ {len(open_alerts)} open alert(s) awaiting action")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total Alerts",        len(alerts))
m2.metric("High Severity",       len(high_alerts),  delta_color="normal" if not high_alerts else "inverse")
m3.metric("Structuring Cases",   len(struct_alerts), delta_color="normal" if not struct_alerts else "inverse")
m4.metric("Open / Active",       len(open_alerts))
m5.metric("Transactions Scanned",len(txns))

tabs = st.tabs(["🔴 High Alerts","📋 All Alerts","🔬 Structuring Detail",
                "📊 Agent Analytics","⚙️ Detection Rules","🔄 Re-run Detection"])

def _sev_badge(sev):
    return "🔴" if sev=="High" else "🟡" if sev=="Medium" else "🟢"

# ── TAB 0: High Alerts ────────────────────────────────────────────
with tabs[0]:
    if high_alerts:
        for a in sorted(high_alerts, key=lambda x: x.get("txn_date",""), reverse=True):
            with st.expander(f"{_sev_badge(a['severity'])} {a['id']} — {a['agent_name']} | {a['alert_type']}"):
                c1,c2,c3,c4 = st.columns(4)
                c1.metric("Transactions",   a.get("txn_count",0))
                c2.metric("Total Amount",   f"KES {a.get('total_amount_kes',0):,.0f}")
                c3.metric("Commission",     f"KES {a.get('commission_earned',0):,.2f}")
                c4.metric("Excess Comm.",   f"KES {a.get('excess_commission',0):,.2f}")
                st.markdown(f"**Agent:** {a['agent_name']} ({a['agent_id']}) | **Branch:** {a.get('branch','')}")
                st.markdown(f"**Customer:** {a['customer_ref']} | **Date:** {a.get('txn_date','')[:10]}")
                st.markdown(f"**Transaction amounts:** {a.get('amounts',[])}")
                st.markdown(f"**Threshold:** KES {a.get('threshold_kes',STRUCT_THRESHOLD):,.0f}")

                if is_risk or is_admin:
                    new_status = st.selectbox("Update status",
                                              ["Open","Under Review","Cleared","Confirmed Fraud","Referred to FRC"],
                                              key=f"fraud_stat_{a['id']}")
                    action     = st.text_input("Action taken", key=f"fraud_act_{a['id']}")
                    if st.button("💾 Save", key=f"fraud_save_{a['id']}", type="primary"):
                        all_a = json.loads((DATA/"agent_fraud_alerts.json").read_text())
                        for al in all_a:
                            if al["id"]==a["id"]:
                                al["status"]=new_status; al["action_taken"]=action
                        (DATA/"agent_fraud_alerts.json").write_text(json.dumps(all_a, indent=2))
                        audit_log("FRAUD_ALERT_UPDATED", uname, f"{a['id']}: {new_status}")
                        _bsc_trigger(uname, "K054")
                        st.cache_data.clear(); st.success("✅ Updated"); st.rerun()
    else:
        st.success("✅ No high severity alerts.")

# ── TAB 1: All Alerts ─────────────────────────────────────────────
with tabs[1]:
    f1,f2 = st.columns(2)
    ftype = f1.selectbox("Alert type",["All","Structuring (Transaction Splitting)","Transaction Velocity"],key="fr_type")
    fstat = f2.selectbox("Status",["All","Open","Under Review","Cleared","Confirmed Fraud"],key="fr_stat")
    vis   = [a for a in alerts
             if (ftype=="All" or a.get("alert_type")==ftype)
             and (fstat=="All" or a.get("status")==fstat)]
    rows  = [{
        "Sev":_sev_badge(a.get("severity","")),
        "ID":a["id"],"Type":a.get("alert_type","")[:28],
        "Agent":a.get("agent_name","")[:18],"Branch":a.get("branch","")[:12],
        "Date":a.get("txn_date","")[:10],"Txns":a.get("txn_count",0),
        "Amount":f"KES {a.get('total_amount_kes',0):,.0f}",
        "Excess Comm":f"KES {a.get('excess_commission',0):,.2f}",
        "Status":a.get("status",""),
    } for a in sorted(vis, key=lambda x: x.get("txn_date",""), reverse=True)]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── TAB 2: Structuring Detail ─────────────────────────────────────
with tabs[2]:
    st.markdown("**What is transaction splitting / structuring?**")
    st.info(
        "An agent deliberately splits one large transaction (e.g. KES 30,000) into multiple "
        "smaller transactions each just below the commission threshold (e.g. 3 × KES 9,999) "
        "to earn 3 separate commissions instead of one. Under POCAMLA 2009, structuring is a "
        "criminal offence. Under CBK Agent Banking guidelines, it warrants immediate suspension."
    )
    if struct_alerts:
        st.markdown(f"**{len(struct_alerts)} structuring case(s) detected:**")
        for a in struct_alerts[:10]:
            with st.expander(f"🔴 {a['id']}: {a['agent_name']} — KES {a.get('total_amount_kes',0):,.0f} split into {a.get('txn_count',0)} transactions"):
                amounts = a.get("amounts",[])
                st.markdown(f"**Transaction amounts:** {[f'KES {x:,.0f}' for x in amounts]}")
                st.markdown(f"**Combined total:** KES {a.get('total_amount_kes',0):,.0f}")
                st.markdown(f"**Threshold:** KES {STRUCT_THRESHOLD:,.0f}")
                st.markdown(f"**Commission earned:** KES {a.get('commission_earned',0):,.2f}")
                actual_comm = a.get('total_amount_kes',0) * 0.01
                st.markdown(f"**Commission if single txn:** KES {actual_comm:,.2f}")
                st.markdown(f"**Excess commission gained:** KES {a.get('excess_commission',0):,.2f}")
    else:
        st.success("✅ No structuring cases detected in current dataset.")

# ── TAB 3: Agent Analytics ────────────────────────────────────────
with tabs[3]:
    if txns:
        agent_stats = defaultdict(lambda: {"txns":0,"total":0,"commission":0,"flags":0})
        for t in txns:
            aid = t.get("agent_id","?")
            agent_stats[aid]["txns"]       += 1
            agent_stats[aid]["total"]      += t.get("amount_kes",0)
            agent_stats[aid]["commission"] += t.get("commission_kes",0)
            if t.get("fraud_flag"):
                agent_stats[aid]["flags"]  += 1

        st.markdown("**Agent transaction summary — flagged agents highlighted:**")
        stat_rows = [{"Agent ID":aid,"Transactions":v["txns"],
                       "Total (KES)":f"{v['total']:,.0f}",
                       "Commission (KES)":f"{v['commission']:,.2f}",
                       "Flagged Txns":v["flags"],
                       "Flag Rate":f"{v['flags']/max(v['txns'],1)*100:.0f}%",
                       "Risk":("🔴 High" if v["flags"]>=3 else "🟡 Medium" if v["flags"]>=1 else "🟢 Clean")}
                      for aid,v in sorted(agent_stats.items(), key=lambda x:-x[1]["flags"])]
        st.dataframe(pd.DataFrame(stat_rows), use_container_width=True, hide_index=True)

# ── TAB 4: Detection Rules ────────────────────────────────────────
with tabs[4]:
    st.markdown("**Active detection rules (configurable via Admin → Thresholds):**")
    rules = [
        {"Rule":"Structuring / Transaction Splitting",
         "Logic":f"Same agent + same customer + same day + 2+ transactions each < KES {STRUCT_THRESHOLD:,.0f} + combined > threshold",
         "Severity":"High","CBK Reference":"POCAMLA 2009 S.7 — Structuring is a criminal offence"},
        {"Rule":"Transaction Velocity",
         "Logic":f"Agent processes > {VELOCITY_LIMIT} transactions in a single day",
         "Severity":"Medium","CBK Reference":"CBK Agent Banking Guidelines — daily transaction limits"},
        {"Rule":"Commission Inflation",
         "Logic":f"Agent earns >KES {COMM_THRESHOLD} commission from a single customer in one day",
         "Severity":"Medium","CBK Reference":"CBK Agent Banking Guidelines — commission caps"},
        {"Rule":"Round-trip Transaction",
         "Logic":"Agent deposits and withdraws same amount for same customer within 60 minutes",
         "Severity":"High","CBK Reference":"AML Guidelines — layering detection"},
        {"Rule":"Off-hours Transaction",
         "Logic":"Transactions processed outside agent operating hours (before 7am or after 8pm)",
         "Severity":"Low","CBK Reference":"CBK Agent Banking Guidelines — operating hours"},
    ]
    st.dataframe(pd.DataFrame(rules), use_container_width=True, hide_index=True)

    st.markdown("**Configurable thresholds:**")
    c1,c2,c3 = st.columns(3)
    c1.metric("Structuring threshold", f"KES {STRUCT_THRESHOLD:,.0f}")
    c2.metric("Velocity daily limit",  f"{VELOCITY_LIMIT} txns/day")
    c3.metric("Commission alert",      f"KES {COMM_THRESHOLD:,.0f}")
    st.caption("Adjust in Admin → Thresholds → Agency Banking")

# ── TAB 5: Re-run Detection ───────────────────────────────────────
with tabs[5]:
    if is_risk or is_admin:
        st.markdown("**Re-run fraud detection engine on latest transactions:**")
        st.info("This scans all agent transactions in `agent_transactions.json` and regenerates "
                "fraud alerts using the current threshold settings. Run after uploading new transaction data.")
        if st.button("🔄 Run detection engine", key="fraud_rerun", type="primary"):
            with st.spinner("Scanning transactions..."):
                all_txns = json.loads((DATA/"agent_transactions.json").read_text())
                new_alerts = []
                alert_num  = 1

                # Structuring detection
                by_key = defaultdict(list)
                for t in all_txns:
                    key = f"{t.get('agent_id','?')}|{t.get('customer_ref','?')}|{t.get('txn_date','?')[:10]}"
                    by_key[key].append(t)

                for key, t_list in by_key.items():
                    below = [t for t in t_list if t.get("amount_kes",0) < STRUCT_THRESHOLD]
                    if len(below) >= 2:
                        total = sum(t.get("amount_kes",0) for t in below)
                        if total >= STRUCT_THRESHOLD:
                            agent_id, cust_ref, txn_date = key.split('|')
                            comm = sum(t.get("commission_kes",0) for t in below)
                            new_alerts.append({
                                "id": f"FRDA{alert_num:05d}",
                                "alert_type": "Structuring (Transaction Splitting)",
                                "severity": "High",
                                "agent_id": agent_id,
                                "agent_name": t_list[0].get("agent_name","Unknown"),
                                "branch": t_list[0].get("branch",""),
                                "customer_ref": cust_ref,
                                "txn_date": txn_date,
                                "txn_count": len(below),
                                "total_amount_kes": round(total,0),
                                "threshold_kes": STRUCT_THRESHOLD,
                                "commission_earned": round(comm,2),
                                "excess_commission": round(max(0, comm - total*0.01),2),
                                "txn_ids": [t["id"] for t in below],
                                "amounts": [t.get("amount_kes",0) for t in below],
                                "status": "Open",
                                "assigned_to": "Agency Banking Manager",
                                "detected_at": str(today),
                                "action_taken": "", "notes": ""
                            })
                            alert_num += 1

                (DATA/"agent_fraud_alerts.json").write_text(json.dumps(new_alerts, indent=2))
                audit_log("FRAUD_DETECTION_RUN", uname, f"{len(new_alerts)} alerts generated")
                st.cache_data.clear()
                st.success(f"✅ Detection complete — {len(new_alerts)} alerts generated")
                st.rerun()
    else:
        st.info("Detection engine available to Risk & Compliance team.")
