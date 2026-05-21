"""pages/73_channels.py — Channels Management & Digital Performance.
Dept: Digital Financial Services | KPIs: K069 K070 K071 | BSC: Auto-scored
Hardcoded: channel types (Physical/Digital), core channel list
Configurable: SLA targets per channel, adoption targets, active/inactive channels
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log
from utils.config import currency_symbol, regulator

require_access("sales_customer.channels")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_dfs   = any(x in role for x in ("digital","channel","it","operation","manager","head","director","dfs"))

CHANNEL_TYPES = ["Physical","Digital"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"channels_data.json"
    return a2z_db.load_json(p) if p.exists() else []

@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    if not mc.exists(): return {}
    return a2z_db.load_json(mc).get("channels",{})

def _save(data):
    (DATA/"channels_data.json").write_text(json.dumps(data,indent=2))
    st.cache_data.clear()

records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable",{})
sla_target     = conf_cfg.get("sla_uptime_target_pct",99.5)
adopt_target   = conf_cfg.get("digital_adoption_target_pct",40.0)
growth_target  = conf_cfg.get("txn_growth_target_pct",20.0)
comp_threshold = conf_cfg.get("complaint_threshold",50)
ch_cfg_list    = conf_cfg.get("channels",[])

digital_ch   = [r for r in records if r.get("channel_type","")=="Digital"]
physical_ch  = [r for r in records if r.get("channel_type","")=="Physical"]
degraded     = [r for r in records if r.get("status","") in ("Degraded","Under Maintenance","Offline")]
total_txns   = sum(r.get("transactions_today",0) for r in records)
digital_txns = sum(r.get("transactions_today",0) for r in digital_ch)
digital_pct  = round(digital_txns/max(total_txns,1)*100,1)
avg_uptime   = round(sum(r.get("uptime_pct_mtd",0) for r in records)/max(len(records),1),2)
sla_breach   = [r for r in records if r.get("uptime_pct_mtd",0)<r.get("sla_uptime_target",sla_target)]
total_comp   = sum(r.get("customer_complaints",0) for r in records)
txn_growth   = 15.3  # simulated — would come from CBS in production

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📲 Channels Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Digital Financial Services · K069 · K070 · K071</span></div>",
    unsafe_allow_html=True)

if degraded:
    st.error(f"🔴 {len(degraded)} channel(s) degraded or offline: {', '.join(r.get('channel_name','') for r in degraded)}")
if sla_breach:
    st.warning(f"⚠️ {len(sla_breach)} channel(s) below SLA uptime target")
if total_comp > comp_threshold:
    st.warning(f"⚠️ Total complaints ({total_comp}) above threshold ({comp_threshold})")

m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("Channels",          len(records))
m2.metric("Txns today",        f"{total_txns:,}")
m3.metric("Digital share",     f"{digital_pct}%",  delta_color="off" if digital_pct>=adopt_target else "inverse")
m4.metric("Avg uptime",        f"{avg_uptime:.2f}%",delta_color="off" if avg_uptime>=sla_target else "inverse")
m5.metric("Complaints",        total_comp,          delta_color="inverse" if total_comp>comp_threshold else "off")
m6.metric("Degraded",          len(degraded),       delta_color="inverse" if degraded else "off")

tabs = st.tabs(["📊 Overview","📋 Channel Detail","💳 Transactions","🔄 Incidents","⚙️ Config","📈 BSC","🚀 Channel Performance (Standard #91)"])

with tabs[0]:
    rows=[{"Channel":r.get("channel_name",""),"Type":r.get("channel_type",""),
            "Status":r.get("status",""),"Txns Today":f"{r.get('transactions_today',0):,}",
            "Value(M)":r.get("value_today_m",0),"Uptime MTD":f"{r.get('uptime_pct_mtd',0):.2f}%",
            "SLA":"✅" if r.get("uptime_pct_mtd",0)>=r.get("sla_uptime_target",sla_target) else "❌",
            "Error%":f"{r.get('error_rate_pct',0):.3f}%","Users Today":f"{r.get('active_users_today',0):,}",
            "Complaints":r.get("customer_complaints",0),"Revenue YTD(M)":r.get("revenue_ytd_m",0)}
           for r in sorted(records,key=lambda x:-x.get("transactions_today",0))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    c1,c2,c3 = st.columns(3)
    c1.caption(f"Digital: {digital_pct:.1f}% of total transactions")
    c2.caption(f"SLA: {len(records)-len(sla_breach)}/{len(records)} channels compliant")
    c3.caption(f"Total revenue YTD: {currency_symbol()} {sum(r.get('revenue_ytd_m',0) for r in records):.1f}M")

with tabs[1]:
    sel_ch = st.selectbox("Select channel",[r.get("channel_name","") for r in records],key="ch_dsel")
    ch = next((r for r in records if r.get("channel_name","")==sel_ch),{})
    if ch:
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Status",    ch.get("status",""))
        c2.metric("Txns today",f"{ch.get('transactions_today',0):,}")
        c3.metric("Uptime MTD",f"{ch.get('uptime_pct_mtd',0):.2f}%")
        c4.metric("Error rate",f"{ch.get('error_rate_pct',0):.3f}%")
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Value today",f"{currency_symbol()} {ch.get('value_today_m',0):.1f}M")
        c2.metric("Active users",f"{ch.get('active_users_today',0):,}")
        c3.metric("Failed txns",ch.get("failed_transactions",0))
        c4.metric("Complaints",ch.get("customer_complaints",0))
        c1,c2 = st.columns(2)
        c1.metric("Revenue YTD",f"{currency_symbol()} {ch.get('revenue_ytd_m',0):.1f}M")
        c2.metric("Cost YTD",f"{currency_symbol()} {ch.get('cost_ytd_m',0):.1f}M")
        if ch.get("last_incident"):
            st.info(f"Last incident: {ch.get('last_incident','')[:10]}")
        if is_dfs or is_admin:
            new_status = st.selectbox("Update status",["Active","Under Maintenance","Degraded","Offline"],
                                     index=["Active","Under Maintenance","Degraded","Offline"].index(ch.get("status","Active")) if ch.get("status","Active") in ["Active","Under Maintenance","Degraded","Offline"] else 0,
                                     key="ch_upd_stat")
            if st.button("💾 Update channel status",key="ch_upd",type="primary"):
                all_r = _load()
                for rec in all_r:
                    if rec.get("channel_name","")==sel_ch: rec["status"]=new_status; break
                _save(all_r)
                audit_log("CHANNEL_STATUS_UPDATED",uname,f"{sel_ch}: {new_status}")
                _bsc_trigger(uname,"K070")
                st.success("✅ Updated"); st.rerun()

with tabs[2]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**Transactions by channel:**")
        txn_data={r.get("channel_name",""):r.get("transactions_today",0) for r in records}
        st.bar_chart(pd.DataFrame({"Txns":txn_data}))
    with c2:
        st.markdown("**Digital vs Physical:**")
        d_txns=sum(r.get("transactions_today",0) for r in digital_ch)
        p_txns=sum(r.get("transactions_today",0) for r in physical_ch)
        d_val =sum(r.get("value_today_m",0) for r in digital_ch)
        p_val =sum(r.get("value_today_m",0) for r in physical_ch)
        st.metric("Digital transactions",f"{d_txns:,} ({digital_pct:.1f}%)")
        st.metric("Physical transactions",f"{p_txns:,} ({100-digital_pct:.1f}%)")
        st.metric("Digital value",f"{currency_symbol()} {d_val:.1f}M")
        st.metric("Physical value",f"{currency_symbol()} {p_val:.1f}M")

with tabs[3]:
    _ch_inc_sub_tabs = st.tabs([
        "📝 Manual Incident Log",
        "📡 Channel SLA Monitoring (Standard #91 SLA, integrated v5.83)",
    ])
    with _ch_inc_sub_tabs[0]:
        st.markdown("**Log a channel incident:**")
        if is_dfs or is_admin:
            r1,r2 = st.columns(2)
            inc_ch = r1.selectbox("Channel",[r.get("channel_name","") for r in records],key="ch_inc_ch")
            inc_type= r2.selectbox("Type",["Downtime","Degraded Performance","High Error Rate","Security Alert","Other"],key="ch_inc_type")
            inc_desc= st.text_area("Description *",key="ch_inc_desc")
            if st.button("📝 Log incident",key="ch_inc_log",type="primary"):
                if inc_desc.strip():
                    all_r = _load()
                    for rec in all_r:
                        if rec.get("channel_name","")==inc_ch:
                            rec["last_incident"]=str(today)
                            if "Downtime" in inc_type: rec["status"]="Offline"
                            elif "Degraded" in inc_type: rec["status"]="Degraded"
                            break
                    _save(all_r)
                    audit_log("CHANNEL_INCIDENT",uname,f"{inc_ch}: {inc_type}")
                    _bsc_trigger(uname,"K070")
                    st.success("✅ Incident logged"); st.rerun()

    with _ch_inc_sub_tabs[1]:
        # ── Channel SLA Monitoring (Standard #91 SLA, integrated v5.83) ──
        from utils.channel_sla import (
            ChannelSlaMonitoringEngine, ChannelOutage, LatencyObservation,
            CHANNELS as SLA_CHANNELS,
            CHANNEL_UPTIME_TARGET_PCT, CHANNEL_LATENCY_TARGET_P99_MS,
            UPTIME_GREEN_GAP_MAX_PP, UPTIME_AMBER_GAP_MAX_PP,
        )
        from datetime import datetime, timedelta
        from decimal import Decimal as _D_sla

        st.markdown(
            f"**Standard #91 SLA — Channel SLA Monitoring Engine**. "
            f"Tracks outages and latency observations across "
            f"{len(SLA_CHANNELS)} channels. Computes uptime%, MTBF, MTTR, "
            "latency distribution, and combined per-channel severity."
        )
        st.caption(
            f"Uptime targets: MOBILE/INTERNET/API ≥ 99.9% · "
            f"ATM/USSD/AGENT/POS ≥ 99.5% · BRANCH ≥ 99.0% (byte-for-byte from "
            f"CHANNEL_UPTIME_TARGET_PCT). "
            f"Latency P99 targets: digital channels 2000ms, ATM/AGENT 5000ms, "
            f"USSD 8000ms, POS 3000ms, BRANCH 30000ms."
        )

        sla_sub_tabs = st.tabs([
            "🟢 Uptime % (per channel)",
            "📈 MTBF & MTTR",
            "⚡ Response Time Distribution",
            "📊 Multi-Channel SLA Summary",
            "🌳 Engine Reference",
        ])

        # Demo dataset — outages and latency observations for last 30 days
        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_outages_and_latency():
            base = datetime(2026, 4, 1)
            outages = [
                # MOBILE — 1 short outage
                ChannelOutage("OUT_M01", "MOBILE",
                                base + timedelta(days=4, hours=10),
                                base + timedelta(days=4, hours=10, minutes=30),
                                severity="PARTIAL"),
                # ATM — 2 outages
                ChannelOutage("OUT_A01", "ATM",
                                base + timedelta(days=9, hours=14),
                                base + timedelta(days=9, hours=18),
                                severity="FULL"),
                ChannelOutage("OUT_A02", "ATM",
                                base + timedelta(days=21, hours=9),
                                base + timedelta(days=21, hours=11),
                                severity="PARTIAL"),
                # USSD — 1 outage
                ChannelOutage("OUT_U01", "USSD",
                                base + timedelta(days=15, hours=12),
                                base + timedelta(days=15, hours=12, minutes=15),
                                severity="PARTIAL"),
                # AGENT — 1 longer outage
                ChannelOutage("OUT_AG01", "AGENT",
                                base + timedelta(days=18, hours=8),
                                base + timedelta(days=18, hours=14),
                                severity="FULL"),
            ]

            # Latency observations — simulate distributions with seed
            import random
            random.seed(42)
            obs = []
            # MOBILE — fast (most under 2s, occasional slower)
            for i in range(150):
                obs.append(LatencyObservation(
                    f"L_M_{i}", "MOBILE",
                    random.randint(800, 2500),  # slightly above target
                    base + timedelta(hours=i*4)))
            # ATM — slower
            for i in range(80):
                obs.append(LatencyObservation(
                    f"L_A_{i}", "ATM",
                    random.randint(2000, 6000),
                    base + timedelta(hours=i*8)))
            # USSD — wide spread
            for i in range(60):
                obs.append(LatencyObservation(
                    f"L_U_{i}", "USSD",
                    random.randint(2000, 9000),
                    base + timedelta(hours=i*10)))
            # API — fast
            for i in range(200):
                obs.append(LatencyObservation(
                    f"L_API_{i}", "API",
                    random.randint(500, 1800),  # mostly within target
                    base + timedelta(hours=i*3)))
            return outages, obs

        outages, observations = _demo_outages_and_latency()
        period_start = datetime(2026, 4, 1)
        period_end = datetime(2026, 4, 30, 23, 59, 59)
        st.caption(
            f"📊 Demo dataset: **{len(outages)} outages** + "
            f"**{len(observations)} latency observations** "
            f"across {period_start.date()} → {period_end.date()}. "
            "Production deployment would feed via "
            "`channel_outages.json` + `channel_latency.json`.")

        # ──────── Uptime ────────
        with sla_sub_tabs[0]:
            st.markdown(f"**Uptime % per channel** (vs {regulator()} PG/04 + DFS targets)")
            st.caption(
                f"GREEN: at-or-above target. "
                f"AMBER: within {UPTIME_AMBER_GAP_MAX_PP} pp below target. "
                f"RED: more than {UPTIME_AMBER_GAP_MAX_PP} pp gap.")

            uptime_ch = st.selectbox(
                "Channel",
                list(SLA_CHANNELS),
                key="sla_up_ch")

            if st.button("Compute uptime %",
                           key="sla_up_btn", type="primary"):
                r = ChannelSlaMonitoringEngine.uptime_pct(
                    outages, uptime_ch, period_start, period_end)
                up_pct = r.get("uptime_pct")
                target = r.get("target_pct")
                severity = r.get("severity")
                downtime_sec = r.get("downtime_seconds", 0)
                downtime_min = downtime_sec / 60
                colors = {"GREEN": "#10B981", "AMBER": "#F59E0B",
                          "RED": "#DC2626", None: "#6B7280"}
                color = colors.get(severity, "#6B7280")

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Uptime %", f"{up_pct}%",
                           delta=f"target ≥ {target}%")
                k2.metric("Downtime",
                           f"{downtime_min:,.1f} min" if downtime_min < 1440
                           else f"{downtime_min/60:,.2f} hr")
                k3.metric("Outages logged", r.get("outage_count"))
                with k4:
                    st.markdown(
                        f"<div style='padding:8px 12px;background:{color}22;"
                        f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"SEVERITY</div>"
                        f"<div style='font-size:20px;font-weight:800;color:{color}'>"
                        f"{severity}</div></div>", unsafe_allow_html=True)

                ongoing = r.get("ongoing_outages_count", 0)
                if ongoing > 0:
                    st.warning(
                        f"⚠ {ongoing} ongoing outage(s) — uptime calc treats these "
                        "as continuing through period_end.")

                if severity == "RED":
                    st.error(
                        f"⛔ {uptime_ch} uptime {up_pct}% **MORE than "
                        f"{UPTIME_AMBER_GAP_MAX_PP}pp below** target {target}%. "
                        f"{regulator()} PG/04 incident reporting may be required.")
                elif severity == "AMBER":
                    st.warning(
                        f"⚠ {uptime_ch} uptime {up_pct}% within "
                        f"{UPTIME_AMBER_GAP_MAX_PP}pp of target — close monitoring needed.")
                else:
                    st.success(f"✅ {uptime_ch} uptime {up_pct}% meets {target}% target.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"ChannelSLA #91-SLA: uptime {uptime_ch} "
                           f"{up_pct}% target={target}% severity={severity}")

        # ──────── MTBF / MTTR ────────
        with sla_sub_tabs[1]:
            st.markdown("**Mean Time Between Failures (MTBF) & Mean Time To Repair (MTTR)**")
            st.caption(
                "MTBF measures reliability — higher = more reliable. "
                "MTTR measures incident response speed — lower = faster recovery. "
                "Both require completed (ended) outages.")

            mtbf_ch = st.selectbox(
                "Channel",
                list(SLA_CHANNELS),
                key="sla_mtbf_ch",
                index=list(SLA_CHANNELS).index("ATM"))

            if st.button("Compute MTBF/MTTR",
                           key="sla_mtbf_btn", type="primary"):
                r = ChannelSlaMonitoringEngine.incident_mtbf_mttr(
                    outages, mtbf_ch, period_start, period_end)
                mttr = r.get("mttr_minutes")
                mtbf = r.get("mtbf_hours")
                outage_ct = r.get("outage_count", 0)
                completed = r.get("completed_outages", 0)

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Outages", outage_ct)
                k2.metric("Completed", completed)
                k3.metric("MTTR (avg)",
                           f"{mttr:,.1f} min" if mttr is not None else "—",
                           help="Mean Time To Repair — lower is better.")
                k4.metric("MTBF",
                           f"{mtbf:,.1f} hr" if mtbf is not None else "—",
                           help="Mean Time Between Failures — higher is better.")

                if outage_ct == 0:
                    st.success(
                        f"✅ {mtbf_ch} had **zero outages** in this period — "
                        "perfect reliability.")
                elif outage_ct == 1:
                    st.info(
                        f"ℹ Only 1 outage logged for {mtbf_ch} — MTBF cannot be "
                        "computed (need at least 2 to measure intervals).")

                audit_log("IFRS_ENGINE_USED", uname,
                           f"ChannelSLA #91-SLA: MTBF/MTTR {mtbf_ch} "
                           f"outages={outage_ct} mttr={mttr} mtbf={mtbf}")

        # ──────── Response time distribution ────────
        with sla_sub_tabs[2]:
            st.markdown(
                "**Response Time Distribution** (P50 / P90 / P99 vs target)")
            st.caption(
                "Engine binds CHANNEL_LATENCY_TARGET_P99_MS dict byte-for-byte. "
                "Severity computed from P99 vs target.")

            lat_ch = st.selectbox(
                "Channel",
                list(SLA_CHANNELS),
                key="sla_lat_ch",
                index=list(SLA_CHANNELS).index("MOBILE"))

            if st.button("Compute latency distribution",
                           key="sla_lat_btn", type="primary"):
                r = ChannelSlaMonitoringEngine.response_time_distribution(
                    observations, lat_ch)
                count = r.get("observations_count", 0)
                excluded = r.get("observations_excluded", 0)
                if count == 0:
                    st.warning(
                        f"No latency observations for {lat_ch} in dataset.")
                else:
                    p50 = r.get("p50_ms")
                    p90 = r.get("p90_ms")
                    p99 = r.get("p99_ms")
                    max_ms = r.get("max_ms")
                    target = r.get("p99_target_ms")
                    severity = r.get("severity")
                    colors = {"GREEN": "#10B981", "AMBER": "#F59E0B",
                              "RED": "#DC2626", None: "#6B7280"}
                    color = colors.get(severity, "#6B7280")

                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Observations", count)
                    k2.metric("P50 (median)", f"{p50:,.0f} ms")
                    k3.metric("P90", f"{p90:,.0f} ms")
                    k4.metric("P99", f"{p99:,.0f} ms",
                               delta=f"target ≤ {target} ms")

                    k1, k2 = st.columns(2)
                    k1.metric("Max observed", f"{max_ms:,.0f} ms")
                    with k2:
                        st.markdown(
                            f"<div style='padding:8px 12px;background:{color}22;"
                            f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                            f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                            f"P99 SEVERITY</div>"
                            f"<div style='font-size:20px;font-weight:800;color:{color}'>"
                            f"{severity}</div></div>", unsafe_allow_html=True)

                    if excluded > 0:
                        st.warning(
                            f"⚠ {excluded} observation(s) excluded — invalid response times "
                            "(Rule 6 transparency).")

                    if severity == "RED":
                        st.error(
                            f"⛔ P99 latency {p99:,.0f}ms significantly above "
                            f"{target}ms target — performance optimization needed.")
                    elif severity == "AMBER":
                        st.warning(
                            f"⚠ P99 latency {p99:,.0f}ms approaching/above target — monitor closely.")
                    else:
                        st.success(
                            f"✅ {lat_ch} P99 latency {p99:,.0f}ms within {target}ms target.")
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"ChannelSLA #91-SLA: latency {lat_ch} "
                               f"P50={p50}ms P99={p99}ms severity={severity}")

        # ──────── Multi-channel summary ────────
        with sla_sub_tabs[3]:
            st.markdown(
                "**Multi-Channel SLA Summary** — uptime + latency per channel "
                "with combined severity.")
            st.caption(
                "Combined severity = worst of (uptime severity, latency severity). "
                "Used for executive dashboards.")

            if st.button("Compute SLA summary",
                           key="sla_sum_btn", type="primary"):
                r = ChannelSlaMonitoringEngine.channel_sla_summary(
                    outages, observations, period_start, period_end)
                channels_data = r.get("channels", [])

                if channels_data:
                    rows = []
                    for ch in channels_data:
                        sev = ch.get("combined_severity", "—")
                        sev_emoji = {"GREEN": "🟢", "AMBER": "🟡",
                                       "RED": "🔴"}.get(sev, "⚪")
                        p99_ms = ch.get("p99_ms")
                        p99_display = (f"{float(_D_sla(str(p99_ms))):,.0f}"
                                          if p99_ms not in (None, "None") else "—")
                        rows.append({
                            "Channel": ch.get("channel"),
                            "Uptime %": ch.get("uptime_pct"),
                            "Uptime sev.": ch.get("uptime_severity") or "—",
                            "P99 (ms)": p99_display,
                            "Latency sev.": ch.get("latency_severity") or "—",
                            "Combined": f"{sev_emoji} {sev}",
                        })
                    st.dataframe(pd.DataFrame(rows),
                                 use_container_width=True, hide_index=True)

                    # Count of severity buckets
                    sev_counts = {"GREEN": 0, "AMBER": 0, "RED": 0}
                    for ch in channels_data:
                        s = ch.get("combined_severity")
                        if s in sev_counts:
                            sev_counts[s] += 1

                    k1, k2, k3 = st.columns(3)
                    k1.metric("🟢 GREEN channels", sev_counts["GREEN"])
                    k2.metric("🟡 AMBER channels", sev_counts["AMBER"])
                    k3.metric("🔴 RED channels", sev_counts["RED"])

                    if sev_counts["RED"] > 0:
                        st.error(
                            f"⛔ {sev_counts['RED']} channel(s) at RED — "
                            "executive escalation appropriate.")
                    elif sev_counts["AMBER"] > 0:
                        st.warning(
                            f"⚠ {sev_counts['AMBER']} channel(s) at AMBER — "
                            "operational monitoring required.")
                    else:
                        st.success(
                            "✅ All channels at GREEN — full SLA compliance.")
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"ChannelSLA #91-SLA: summary "
                               f"G={sev_counts['GREEN']} A={sev_counts['AMBER']} R={sev_counts['RED']}")

        # ──────── Engine reference ────────
        with sla_sub_tabs[4]:
            st.markdown("**Engine Constants Reference** (single source of truth)")

            st.markdown(f"**Uptime targets per channel:**")
            up_rows = [
                {"Channel": ch,
                  "Uptime target %": float(CHANNEL_UPTIME_TARGET_PCT.get(ch, 0)),
                  "Latency P99 target (ms)": CHANNEL_LATENCY_TARGET_P99_MS.get(ch, 0)}
                for ch in SLA_CHANNELS
            ]
            st.dataframe(pd.DataFrame(up_rows),
                         use_container_width=True, hide_index=True)

            st.markdown("**Severity gap thresholds:**")
            gap_rows = [
                {"Band": "🟢 GREEN", "Gap to target":
                    f"≤ {UPTIME_GREEN_GAP_MAX_PP} pp (at or above target)"},
                {"Band": "🟡 AMBER", "Gap to target":
                    f"≤ {UPTIME_AMBER_GAP_MAX_PP} pp below target"},
                {"Band": "🔴 RED", "Gap to target":
                    f"> {UPTIME_AMBER_GAP_MAX_PP} pp below target"},
            ]
            st.dataframe(pd.DataFrame(gap_rows),
                         use_container_width=True, hide_index=True)

            st.caption(
                f"Uptime targets reflect {regulator()} PG/04 (channel availability) and bank's "
                "internal Service Level Agreements. Latency targets reflect customer "
                "experience research — mobile/internet customers expect responses "
                "within 2 seconds, ATM users tolerate 5 seconds, branch operations "
                "tolerate 30 seconds for transaction processing.")

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: Channel types (Physical/Digital), core channel definitions")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("channels",{}).get("configurable",{})
        c1,c2,c3 = st.columns(3)
        new_sla    = c1.number_input("SLA uptime target (%)",90.0,100.0,float(cfg_m.get("sla_uptime_target_pct",99.5)),0.1,key="ch_cfg_sla")
        new_adopt  = c2.number_input("Digital adoption target (%)",10.0,100.0,float(cfg_m.get("digital_adoption_target_pct",40.0)),1.0,key="ch_cfg_adopt")
        new_growth = c3.number_input("Txn growth target (%)",0.0,100.0,float(cfg_m.get("txn_growth_target_pct",20.0)),1.0,key="ch_cfg_growth")
        new_comp   = st.number_input("Complaint threshold",1,500,int(cfg_m.get("complaint_threshold",50)),key="ch_cfg_comp")
        st.markdown("**Channel SLA configuration:**")
        ch_cfg = cfg_m.get("channels",[])
        for c in ch_cfg:
            c1,c2,c3 = st.columns([3,2,1])
            c1.markdown(f"**{c.get('name','')}** — {c.get('type','')}")
            new_ch_sla = c2.number_input(f"SLA %",90.0,100.0,float(c.get("sla",99.5)),0.1,key=f"ch_sla_{c.get('id','')}")
            c.update({"sla":new_ch_sla,"active":c3.checkbox("Active",c.get("active",True),key=f"ch_act_{c.get('id','')}") })
        if st.button("💾 Save channels config",key="ch_cfg_save",type="primary"):
            cfg_m.update({"sla_uptime_target_pct":new_sla,"digital_adoption_target_pct":new_adopt,
                          "txn_growth_target_pct":new_growth,"complaint_threshold":new_comp,"channels":ch_cfg})
            mc["channels"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("CHANNELS_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Configuration available to Admin only.")

with tabs[5]:
    bsc_rows=[
        {"KPI":"K069 — Digital Adoption","Target":f"> {adopt_target}%","Actual":f"{digital_pct:.1f}%","Status":"🟢" if digital_pct>=adopt_target else "🟡","Weight":"10%"},
        {"KPI":"K070 — Channel Uptime","Target":f"> {sla_target}%","Actual":f"{avg_uptime:.2f}%","Status":"🟢" if avg_uptime>=sla_target else "🟡","Weight":"8%"},
        {"KPI":"K071 — Txn Growth","Target":f"> {growth_target}%","Actual":f"{txn_growth:.1f}%","Status":"🟢" if txn_growth>=growth_target else "🟡","Weight":"8%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="ch_bsc",type="primary"):
        _bsc_trigger(uname,"K069"); st.success("✅ BSC updated"); st.rerun()


# ════════════════════════════════════════════════════════════════
# TAB 6 — CHANNEL PERFORMANCE (Standard #91, integrated v5.80)
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    from utils.channel_performance import (
        ChannelPerformanceEngine, ChannelMetrics,
        CHANNELS, CHANNEL_TIER_MAP, CHANNEL_TIERS,
        CHANNEL_COST_PER_TXN_KES, CHANNEL_AVAILABILITY_TARGET_PCT,
        SELF_SERVICE_CHANNELS,
    )
    from decimal import Decimal as _D_cp

    st.markdown(
        f"**Standard #91 — Channel Performance Engine**. "
        f"Cost per transaction, blended cost, channel mix, self-service ratio, "
        f"availability compliance. {len(CHANNELS)} channels across "
        f"{len(CHANNEL_TIERS)} tiers ({' / '.join(CHANNEL_TIERS)})."
    )
    st.caption(
        f"Availability target: {CHANNEL_AVAILABILITY_TARGET_PCT}% per {regulator()} PG/04. "
        f"Self-service channels: {' / '.join(SELF_SERVICE_CHANNELS)}."
    )

    cp_sub_tabs = st.tabs([
        "💰 Cost per Transaction",
        "📊 Channel Mix",
        "🤳 Self-Service Ratio",
        "🟢 Availability Compliance",
        "🌳 Channel Cost Reference",
        "💵 Channel Income (v5.87)",
        "🎯 Optimization Recommendations (v5.87)",
    ])

    # ──────── Cost per transaction ────────
    with cp_sub_tabs[0]:
        st.markdown(
            "**Cost per Transaction** for a single channel + **Blended Cost** across channel mix")

        single_tab, blended_tab = st.tabs(["📍 Single channel", "🔀 Blended (multi-channel)"])

        with single_tab:
            st.markdown("**Per-channel cost per transaction**")
            c1, c2 = st.columns(2)
            with c1:
                cp_op = st.number_input(f"Operating cost ({currency_symbol()} M)",
                                          min_value=0.0, value=5.0, step=0.5,
                                          key="cp_single_op")
            with c2:
                cp_tx = st.number_input("Transaction count",
                                          min_value=0, value=25000, step=1000,
                                          key="cp_single_tx")
            if st.button("Compute cost per txn",
                           key="cp_single_btn", type="primary"):
                r = ChannelPerformanceEngine.cost_per_transaction(
                    _D_cp(str(cp_op)) * _D_cp("1000000"),
                    int(cp_tx))
                cpt = _D_cp(str(r["cost_per_txn_kes"]))
                st.metric("Cost per transaction", f"{currency_symbol()} {cpt:,.2f}")
                st.caption(
                    f"Based on {cp_tx:,} transactions and {currency_symbol()} {cp_op}M operating cost.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Channel #91: cost_per_txn op={cp_op}M tx={cp_tx} → {cpt}")

        with blended_tab:
            st.markdown("**Blended cost per transaction across channel mix**")
            st.caption(
                "Engine uses CHANNEL_COST_PER_TXN_KES (BRANCH=200 / ATM=50 / "
                "AGENT=30 / MOBILE=2 / INTERNET=5 / USSD=2 etc.) as standard rates.")

            mix_inputs = {}
            cols = st.columns(2)
            for i, ch in enumerate(["BRANCH", "ATM", "AGENT", "MOBILE",
                                      "INTERNET", "USSD", "CALL_CENTER", "POS"]):
                cost = CHANNEL_COST_PER_TXN_KES.get(ch, _D_cp("0"))
                with cols[i % 2]:
                    val = st.number_input(
                        f"{ch} ({currency_symbol()} {cost}/txn)",
                        min_value=0,
                        value={"MOBILE": 100000, "ATM": 30000,
                                "BRANCH": 5000, "INTERNET": 20000,
                                "USSD": 50000, "AGENT": 0,
                                "CALL_CENTER": 0, "POS": 0}.get(ch, 0),
                        step=1000, key=f"cp_mix_{ch}")
                    if val > 0:
                        mix_inputs[ch] = val

            if st.button("Compute blended cost",
                           key="cp_blended_btn", type="primary"):
                if not mix_inputs:
                    st.warning("Add at least one channel with transactions.")
                else:
                    r = ChannelPerformanceEngine.blended_cost_per_transaction(mix_inputs)
                    blended = _D_cp(str(r["blended_cost_per_txn_kes"]))
                    total_tx = r.get("total_txn_count", 0)
                    total_cost = _D_cp(str(r["total_weighted_cost_kes"]))
                    k1, k2, k3 = st.columns(3)
                    k1.metric("Blended cost / txn",
                               f"{currency_symbol()} {blended:,.2f}")
                    k2.metric("Total transactions",
                               f"{total_tx:,}")
                    k3.metric("Total weighted cost",
                               f"{currency_symbol()} {total_cost/_D_cp('1000000'):,.2f}M")

                    # Show contribution
                    contrib_rows = [
                        {"Channel": ch,
                          "Transactions": tx,
                          "Cost/txn (KES)": float(CHANNEL_COST_PER_TXN_KES.get(ch, 0)),
                          "Weighted cost (KES M)":
                              float(_D_cp(str(tx)) * CHANNEL_COST_PER_TXN_KES.get(ch, _D_cp("0")) / _D_cp("1000000"))}
                        for ch, tx in mix_inputs.items()
                    ]
                    st.dataframe(pd.DataFrame(contrib_rows),
                                 use_container_width=True, hide_index=True)
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"Channel #91: blended cost {len(mix_inputs)} channels "
                               f"{total_tx} txn → {blended} per txn")

    # ──────── Channel mix ────────
    with cp_sub_tabs[1]:
        st.markdown("**Channel Mix %** — share of transactions per channel")
        st.caption(
            "Used to track digital migration. Healthy banks see >70% in digital channels "
            "(MOBILE / INTERNET / USSD).")

        st.markdown("**Channel transaction counts:**")
        mix_inputs2 = {}
        cols = st.columns(2)
        for i, ch in enumerate(["BRANCH", "ATM", "AGENT", "MOBILE",
                                  "INTERNET", "USSD", "CALL_CENTER", "POS"]):
            with cols[i % 2]:
                val = st.number_input(
                    f"{ch}",
                    min_value=0,
                    value={"MOBILE": 100000, "ATM": 30000,
                            "BRANCH": 5000, "INTERNET": 20000,
                            "USSD": 50000}.get(ch, 0),
                    step=1000, key=f"cp_mix2_{ch}")
                if val > 0:
                    mix_inputs2[ch] = val

        if st.button("Compute channel mix",
                       key="cp_mixpct_btn", type="primary"):
            r = ChannelPerformanceEngine.channel_mix_pct(mix_inputs2)
            mix_pct = r.get("mix_pct", {})
            total = r.get("total_txn_count", 0)
            unknown = r.get("unknown_channels", [])

            if mix_pct:
                # Sort by tier then alpha
                rows = []
                for ch, pct in sorted(mix_pct.items(),
                                        key=lambda x: (CHANNEL_TIER_MAP.get(x[0], "ZZZ"), x[0])):
                    rows.append({
                        "Channel": ch,
                        "Tier": CHANNEL_TIER_MAP.get(ch, "?"),
                        "Transactions": mix_inputs2.get(ch, 0),
                        "% of total": float(_D_cp(str(pct))),
                    })
                st.dataframe(pd.DataFrame(rows),
                             use_container_width=True, hide_index=True)

                # Bar chart
                chart_data = pd.DataFrame({
                    "% share": [r["% of total"] for r in rows]
                }, index=[r["Channel"] for r in rows])
                st.bar_chart(chart_data)

                st.metric("Total transactions", f"{total:,}")
                if unknown:
                    st.warning(
                        f"⚠ Unknown channels excluded: {', '.join(unknown)}")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Channel #91: mix {len(mix_pct)} channels {total} txn")

    # ──────── Self-service ratio ────────
    with cp_sub_tabs[2]:
        st.markdown(
            f"**Self-Service Ratio** — % of transactions through "
            f"{', '.join(SELF_SERVICE_CHANNELS)}")
        st.caption(
            "Higher = lower service cost + better customer experience. "
            "Industry-leading banks achieve >85% self-service.")

        if st.button("Compute self-service ratio",
                       key="cp_ss_btn", type="primary",
                       help="Uses the same channel mix from the previous tab."):
            r = ChannelPerformanceEngine.self_service_ratio(mix_inputs2 if mix_inputs2 else
                {"MOBILE": 100000, "ATM": 30000, "BRANCH": 5000,
                 "INTERNET": 20000, "USSD": 50000})
            ss_pct = float(_D_cp(str(r["self_service_ratio_pct"])))
            color = "#10B981" if ss_pct >= 85 else "#F59E0B" if ss_pct >= 70 else "#DC2626"
            label = "EXCELLENT" if ss_pct >= 85 else "GOOD" if ss_pct >= 70 else "NEEDS_IMPROVEMENT"

            k1, k2, k3 = st.columns(3)
            k1.metric("Self-service ratio", f"{ss_pct:.2f}%")
            k2.metric("Self-service txns",
                       f"{r.get('self_service_count', 0):,}")
            k3.metric("Total txns",
                       f"{r.get('total_count', 0):,}")

            st.markdown(
                f"<div style='padding:14px;background:{color}22;"
                f"border-left:6px solid {color};border-radius:10px;text-align:center'>"
                f"<div style='font-size:24px;font-weight:800;color:{color}'>"
                f"{label}</div></div>", unsafe_allow_html=True)
            audit_log("IFRS_ENGINE_USED", uname,
                       f"Channel #91: self-service {ss_pct}% ({label})")

    # ──────── Availability compliance ────────
    with cp_sub_tabs[3]:
        st.markdown(
            f"**Channel Availability Compliance** — uptime vs {regulator()} PG/04 target "
            f"{CHANNEL_AVAILABILITY_TARGET_PCT}%")
        c1, c2 = st.columns(2)
        with c1:
            avail_ch = st.selectbox("Channel", list(CHANNELS), key="cp_avail_ch",
                                       index=list(CHANNELS).index("MOBILE"))
        with c2:
            avail_pct = st.number_input("Uptime (%)",
                                          min_value=0.0, max_value=100.0,
                                          value=99.7, step=0.1,
                                          key="cp_avail_pct")
        if st.button("Check availability compliance",
                       key="cp_avail_btn", type="primary"):
            r = ChannelPerformanceEngine.channel_availability_compliance(
                avail_ch, _D_cp(str(avail_pct)))
            compliant = r.get("compliant")
            shortfall = r.get("shortfall_pct")

            if compliant:
                st.success(
                    f"✅ **COMPLIANT** — {avail_ch} uptime "
                    f"{avail_pct}% meets {CHANNEL_AVAILABILITY_TARGET_PCT}% target.")
            else:
                st.error(
                    f"⛔ **NON-COMPLIANT** — {avail_ch} uptime {avail_pct}% "
                    f"BELOW {CHANNEL_AVAILABILITY_TARGET_PCT}% target. "
                    f"Shortfall: {shortfall} pp. {regulator()} PG/04 incident reporting may apply.")
            audit_log("IFRS_ENGINE_USED", uname,
                       f"Channel #91: availability {avail_ch} {avail_pct}% "
                       f"compliant={compliant}")

    # ──────── Cost reference ────────
    with cp_sub_tabs[4]:
        st.markdown(
            "**Channel Cost Reference Table** (engine constant — single source of truth)")
        st.caption(
            "These costs are bound byte-for-byte in `CHANNEL_COST_PER_TXN_KES`. "
            "Changes require engine code review.")

        ref_rows = [
            {"Channel": ch,
              "Tier": CHANNEL_TIER_MAP.get(ch, "?"),
              "Cost/txn (KES)": float(CHANNEL_COST_PER_TXN_KES.get(ch, 0)),
              "Self-service": "✅" if ch in SELF_SERVICE_CHANNELS else "—"}
            for ch in CHANNELS
        ]
        ref_df = pd.DataFrame(ref_rows)
        st.dataframe(ref_df, use_container_width=True, hide_index=True)

        # Cost ratio insight
        branch_cost = float(CHANNEL_COST_PER_TXN_KES.get("BRANCH", 0))
        mobile_cost = float(CHANNEL_COST_PER_TXN_KES.get("MOBILE", 1))
        if mobile_cost > 0:
            ratio = branch_cost / mobile_cost
            st.info(
                f"📊 **Branch vs mobile cost ratio**: BRANCH costs **{ratio:.0f}× more** "
                f"per transaction than MOBILE (KES {branch_cost} vs KES {mobile_cost}). "
                f"This is the core economic argument for digital migration.")

    # ════════════════════════════════════════════════════════════════
    # CP_SUB_TABS[5] — CHANNEL INCOME (Standard #91 Income, integrated v5.87)
    # ════════════════════════════════════════════════════════════════
    with cp_sub_tabs[5]:
        from utils.channel_income import (
            ChannelIncomeEngine, CHANNELS as INCOME_CHANNELS,
            DEFAULT_COST_PER_TXN, HIGH_VOLUME_THRESHOLD,
            LOW_MARGIN_THRESHOLD_PCT,
        )
        from decimal import Decimal as _D_ci

        st.markdown(
            f"**Standard #91 Income — Channel Income & Cost-to-Serve Engine**. "
            f"Computes income aggregation by channel (with optional segment filter), "
            f"cost-to-serve per transaction, and full channel P&L. "
            f"Engine covers {len(INCOME_CHANNELS)} channels: "
            f"{' / '.join(INCOME_CHANNELS)}."
        )
        st.caption(
            f"💡 The engine has independent cost basis from `CHANNEL_COST_PER_TXN_KES` "
            f"(used in tabs above) — `DEFAULT_COST_PER_TXN` provides FTE+infra+processing breakdown. "
            f"Page uses demo income + transaction data; production deployment would feed via "
            f"`channel_income.json` + `channel_transactions.json`."
        )

        # Demo dataset — typical Tier-2 bank monthly channel mix
        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_channel_data():
            """Returns (income_rows, txn_counts) tuple."""
            income_rows = [
                {"channel": "BRANCH", "segment": "RETAIL", "amount": _D_ci("12000000")},
                {"channel": "BRANCH", "segment": "SME", "amount": _D_ci("18000000")},
                {"channel": "BRANCH", "segment": "CORPORATE", "amount": _D_ci("25000000")},
                {"channel": "ATM", "segment": "RETAIL", "amount": _D_ci("8500000")},
                {"channel": "MOBILE", "segment": "RETAIL", "amount": _D_ci("22000000")},
                {"channel": "MOBILE", "segment": "SME", "amount": _D_ci("3500000")},
                {"channel": "INTERNET", "segment": "RETAIL", "amount": _D_ci("4500000")},
                {"channel": "INTERNET", "segment": "SME", "amount": _D_ci("6800000")},
                {"channel": "INTERNET", "segment": "CORPORATE", "amount": _D_ci("15000000")},
                {"channel": "AGENT", "segment": "RETAIL", "amount": _D_ci("9200000")},
                {"channel": "USSD", "segment": "RETAIL", "amount": _D_ci("3100000")},
                {"channel": "POS", "segment": "RETAIL", "amount": _D_ci("5500000")},
                {"channel": "POS", "segment": "SME", "amount": _D_ci("2800000")},
            ]
            txn_counts = {
                "BRANCH": 45000, "ATM": 380000, "MOBILE": 1850000,
                "INTERNET": 220000, "AGENT": 145000,
                "USSD": 890000, "POS": 95000,
            }
            return income_rows, txn_counts

        income_rows, txn_counts = _demo_channel_data()

        # Build engine with closures
        def _income_lookup(period):
            return income_rows

        def _txn_lookup(period, channel):
            return {"count": txn_counts.get(channel, 0)}

        cie = ChannelIncomeEngine(
            income_lookup_fn=_income_lookup,
            transaction_lookup_fn=_txn_lookup,
        )

        ci_inner = st.tabs([
            "💵 Income by Channel",
            "💸 Cost-to-Serve",
            "📊 Channel P&L",
            "🌳 Engine Reference",
        ])

        # ──── Income by channel ────
        with ci_inner[0]:
            st.markdown(
                "**Income by Channel** — fee aggregation across the period, "
                "optionally filtered by customer segment.")

            c1, c2 = st.columns(2)
            with c1:
                inc_period = st.text_input("Period",
                                              value="2026-04", key="ci_inc_period")
            with c2:
                inc_segment = st.selectbox("Segment filter",
                                              ["ALL", "RETAIL", "SME", "CORPORATE"],
                                              key="ci_inc_segment")

            if st.button("💵 Compute income",
                           key="ci_inc_btn", type="primary"):
                seg = None if inc_segment == "ALL" else inc_segment
                r = cie.income_by_channel(inc_period, segment=seg)

                total_income = float(_D_ci(str(r["total_income"])))
                rows_proc = int(r["meta"]["rows_processed"])
                rows_skip = int(r["meta"]["rows_skipped"])
                unknown = r["meta"]["unknown_channels"]

                k1, k2, k3 = st.columns(3)
                k1.metric("Total income",
                           f"{currency_symbol()} {total_income/1e6:,.2f}M")
                k2.metric("Rows processed",
                           rows_proc)
                k3.metric("Rows skipped (Rule 6)",
                           rows_skip,
                           help="Skipped due to missing channel/amount.")

                if unknown:
                    st.warning(
                        f"⚠ Unknown channels in data (excluded): "
                        f"{', '.join(unknown)}")

                # Per-channel breakdown
                inc_rows = []
                for ch in INCOME_CHANNELS:
                    ch_data = r["channels"].get(ch, {})
                    income = float(_D_ci(str(ch_data.get("income", 0))))
                    share_pct = ch_data.get("share_pct")
                    inc_rows.append({
                        "Channel": ch,
                        "Income (KES M)": round(income / 1e6, 2),
                        "Share of total":
                            f"{float(_D_ci(str(share_pct))):.2f}%"
                            if share_pct not in (None, "None") else "—",
                    })
                st.dataframe(pd.DataFrame(inc_rows),
                             use_container_width=True, hide_index=True)

                # Bar chart
                chart_data = pd.DataFrame({
                    "Income (KES M)": [r["Income (KES M)"] for r in inc_rows]
                }, index=[r["Channel"] for r in inc_rows])
                st.bar_chart(chart_data)

                audit_log("IFRS_ENGINE_USED", uname,
                           f"ChannelIncome #91-INC: income {inc_period} "
                           f"segment={inc_segment} total={total_income:.0f}")

        # ──── Cost-to-Serve ────
        with ci_inner[1]:
            st.markdown(
                "**Cost-to-Serve** — unit cost per transaction (FTE allocation + "
                "infrastructure + processing) and total channel cost.")
            st.caption(
                "💡 Engine returns cost components separately so cost-to-serve can be "
                "recomputed from updated FTE/infra/processing assumptions without changing "
                "engine code (use `cost_overrides` constructor parameter).")

            cc1, cc2 = st.columns(2)
            with cc1:
                cs_period = st.text_input("Period",
                                            value="2026-04", key="ci_cs_period")
            with cc2:
                cs_channel = st.selectbox("Channel",
                                             list(INCOME_CHANNELS),
                                             index=2, key="ci_cs_channel")

            if st.button("💸 Compute cost-to-serve",
                           key="ci_cs_btn", type="primary"):
                r = cie.cost_to_serve(cs_period, cs_channel)
                txn_count = int(_D_ci(str(r.get("transaction_count", 0))))
                cost_per = r.get("cost_per_transaction")
                total_cost = float(_D_ci(str(r.get("total_cost", 0))))
                cost_basis = r.get("meta", {}).get("cost_basis", {})

                k1, k2, k3 = st.columns(3)
                k1.metric("Transactions", f"{txn_count:,}")
                k2.metric("Cost / txn (KES)",
                           f"{float(_D_ci(str(cost_per))):.2f}"
                           if cost_per is not None else "—")
                k3.metric("Total cost (KES M)",
                           f"{total_cost/1e6:,.2f}")

                # Cost components breakdown
                if cost_basis:
                    st.markdown("**Cost components breakdown:**")
                    cb_rows = [
                        {"Component": k.replace("_", " ").title(),
                          "KES/txn": float(_D_ci(str(v)))}
                        for k, v in cost_basis.items()
                    ]
                    cb_rows.append({
                        "Component": "TOTAL (sum)",
                        "KES/txn":
                            sum(float(_D_ci(str(v))) for v in cost_basis.values()),
                    })
                    st.dataframe(pd.DataFrame(cb_rows),
                                 use_container_width=True, hide_index=True)

                if txn_count == 0:
                    st.warning(
                        f"⚠ No transactions for {cs_channel} in {cs_period} — "
                        "total_cost is 0 even though unit cost is defined.")

                audit_log("IFRS_ENGINE_USED", uname,
                           f"ChannelIncome #91-INC: cost_to_serve {cs_channel} "
                           f"unit={cost_per} total={total_cost:.0f}")

        # ──── Channel P&L ────
        with ci_inner[2]:
            st.markdown(
                "**Channel P&L** — combine income + cost across all channels for "
                "complete profitability view.")
            st.caption(
                "Margin = (income - cost) / income × 100. "
                "Negative margins indicate channel costs exceed income — "
                "subsidization signal for executive review.")

            pnl_period = st.text_input("Period",
                                          value="2026-04", key="ci_pnl_period")

            if st.button("📊 Compute channel P&L",
                           key="ci_pnl_btn", type="primary"):
                # Use optimization recommendations method to get income+cost+margin per channel
                r = cie.channel_optimization_recommendations(pnl_period)
                recs = r["recommendations"]

                pnl_rows = []
                total_income = 0.0
                total_cost = 0.0
                for rec in recs:
                    income = float(_D_ci(str(rec["income"])))
                    cost = float(_D_ci(str(rec["cost"])))
                    margin = rec.get("margin_pct")
                    margin_pct_str = (
                        f"{float(_D_ci(str(margin))):.2f}%"
                        if margin not in (None, "None") else "—")
                    margin_emoji = "—"
                    if margin not in (None, "None"):
                        m = float(_D_ci(str(margin)))
                        margin_emoji = ("🟢" if m >= 50 else
                                         "🟡" if m >= 20 else
                                         "🔴")
                    pnl_rows.append({
                        "Channel": rec["channel"],
                        "Txns": int(_D_ci(str(rec["txn_count"]))),
                        "Income (KES M)": round(income / 1e6, 2),
                        "Cost (KES M)": round(cost / 1e6, 2),
                        "Margin": f"{margin_emoji} {margin_pct_str}",
                    })
                    total_income += income
                    total_cost += cost

                st.dataframe(pd.DataFrame(pnl_rows),
                             use_container_width=True, hide_index=True)

                # Aggregate metrics
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total income",
                           f"{currency_symbol()} {total_income/1e6:,.2f}M")
                k2.metric("Total cost",
                           f"{currency_symbol()} {total_cost/1e6:,.2f}M")
                net = total_income - total_cost
                k3.metric("Net contribution",
                           f"{currency_symbol()} {net/1e6:,.2f}M",
                           delta=f"{(net/total_income*100 if total_income else 0):.1f}% margin")
                cir = (total_cost / total_income * 100) if total_income else 0
                k4.metric("CIR (channel ops)",
                           f"{cir:.1f}%",
                           help="Cost-to-income ratio across channel operations only.")

                audit_log("IFRS_ENGINE_USED", uname,
                           f"ChannelIncome #91-INC: P&L {pnl_period} "
                           f"income={total_income:.0f} cost={total_cost:.0f} "
                           f"margin={(net/total_income*100 if total_income else 0):.1f}%")

        # ──── Engine reference ────
        with ci_inner[3]:
            st.markdown("**Engine Constants Reference** (single source of truth)")

            st.markdown(
                f"**Default cost components** — {len(DEFAULT_COST_PER_TXN)} channels "
                "with FTE / infrastructure / processing breakdown:")
            cost_rows = []
            for ch in INCOME_CHANNELS:
                comp = DEFAULT_COST_PER_TXN.get(ch, {})
                fte = float(_D_ci(str(comp.get("fte_allocation", 0))))
                infra = float(_D_ci(str(comp.get("infrastructure", 0))))
                proc = float(_D_ci(str(comp.get("processing", 0))))
                cost_rows.append({
                    "Channel": ch,
                    "FTE": fte, "Infra": infra, "Processing": proc,
                    "Total/txn": fte + infra + proc,
                })
            st.dataframe(pd.DataFrame(cost_rows),
                         use_container_width=True, hide_index=True)

            st.markdown("**Optimization thresholds:**")
            opt_rows = [
                {"Constant": "HIGH_VOLUME_THRESHOLD",
                  "Value": HIGH_VOLUME_THRESHOLD,
                  "Meaning": "Min txn count for 'high volume' classification"},
                {"Constant": "LOW_MARGIN_THRESHOLD_PCT",
                  "Value": f"{float(LOW_MARGIN_THRESHOLD_PCT)}%",
                  "Meaning": "Margin% below this triggers 'review' recommendation"},
            ]
            st.dataframe(pd.DataFrame(opt_rows),
                         use_container_width=True, hide_index=True)

            st.caption(
                "💡 Cost basis differs from `CHANNEL_COST_PER_TXN_KES` used in earlier tabs. "
                "Channel Performance engine #91 uses a single cost number per channel; "
                "Channel Income engine #91-INC breaks the same number into FTE/infra/processing "
                "components so cost-to-serve assumptions can be tuned independently.")

    # ════════════════════════════════════════════════════════════════
    # CP_SUB_TABS[6] — OPTIMIZATION RECOMMENDATIONS (Standard #91 Income, v5.87)
    # ════════════════════════════════════════════════════════════════
    with cp_sub_tabs[6]:
        from utils.channel_income import (
            ChannelIncomeEngine, HIGH_VOLUME_THRESHOLD, LOW_MARGIN_THRESHOLD_PCT,
        )
        from decimal import Decimal as _D_or

        st.markdown(
            f"**Channel Optimization Recommendations** — engine evaluates each "
            f"channel's volume + margin and recommends action: promote_channel "
            f"(high margin + high volume), maintain (default), or review "
            f"(margin < {float(LOW_MARGIN_THRESHOLD_PCT)}%).")
        st.caption(
            f"Volume threshold: ≥{HIGH_VOLUME_THRESHOLD:,} txns per period for "
            f"'high volume' classification. Margin threshold: < "
            f"{float(LOW_MARGIN_THRESHOLD_PCT)}% for 'review' classification.")

        # Reuse the demo data from above (same period via cache)
        opt_period = st.text_input("Period",
                                      value="2026-04", key="ci_opt_period")

        if st.button("🎯 Compute recommendations",
                       key="ci_opt_btn", type="primary"):
            # Reuse the cached demo data via separate engine instance
            income_rows, txn_counts = _demo_channel_data()

            def _income_lookup(period):
                return income_rows

            def _txn_lookup(period, channel):
                return {"count": txn_counts.get(channel, 0)}

            cie_opt = ChannelIncomeEngine(
                income_lookup_fn=_income_lookup,
                transaction_lookup_fn=_txn_lookup,
            )
            r = cie_opt.channel_optimization_recommendations(opt_period)

            # Tally recommendations
            from collections import Counter
            rec_counter = Counter([rec["recommendation"] for rec in r["recommendations"]])
            promote_count = rec_counter.get("promote_channel", 0)
            maintain_count = rec_counter.get("maintain", 0)
            review_count = rec_counter.get("review", 0)

            k1, k2, k3 = st.columns(3)
            k1.metric("🟢 Promote", promote_count,
                       help="High margin + high volume.")
            k2.metric("🟡 Maintain", maintain_count,
                       help="Steady-state.")
            k3.metric("🔴 Review", review_count,
                       help=f"Margin < {float(LOW_MARGIN_THRESHOLD_PCT)}%.")

            # Per-channel detail
            opt_rows = []
            rec_emojis = {"promote_channel": "🟢", "maintain": "🟡", "review": "🔴"}
            for rec in r["recommendations"]:
                margin = rec.get("margin_pct")
                margin_str = (f"{float(_D_or(str(margin))):.2f}%"
                                if margin not in (None, "None") else "—")
                rec_label = rec["recommendation"]
                emoji = rec_emojis.get(rec_label, "—")
                opt_rows.append({
                    "Channel": rec["channel"],
                    "Txns": int(_D_or(str(rec["txn_count"]))),
                    "Income (KES M)": round(
                        float(_D_or(str(rec["income"]))) / 1e6, 2),
                    "Cost (KES M)": round(
                        float(_D_or(str(rec["cost"]))) / 1e6, 2),
                    "Margin": margin_str,
                    "Recommendation": f"{emoji} {rec_label.replace('_', ' ')}",
                })
            st.dataframe(pd.DataFrame(opt_rows),
                         use_container_width=True, hide_index=True)

            # Executive guidance
            if review_count > 0:
                st.error(
                    f"⛔ **{review_count} channel(s) under review** — margin below "
                    f"{float(LOW_MARGIN_THRESHOLD_PCT)}% threshold. Investigate cost "
                    "structure: are FTE allocations correct? Is volume too low to amortize "
                    "fixed costs? Channel rationalization candidate.")
            elif promote_count >= 4:
                st.success(
                    f"✅ **{promote_count} of {len(r['recommendations'])} channels** "
                    "flagged for promotion — strong digital channel mix. "
                    "Consider promoting these in customer communications and reducing "
                    "branch traffic toward them.")
            else:
                st.info(
                    f"ℹ {promote_count} promote · {maintain_count} maintain · "
                    f"{review_count} review.")

            audit_log("IFRS_ENGINE_USED", uname,
                       f"ChannelIncome #91-INC: recommendations {opt_period} "
                       f"promote={promote_count} maintain={maintain_count} "
                       f"review={review_count}")
