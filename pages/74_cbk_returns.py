"""pages/74_cbk_returns.py — CBK Returns Centre.
All 47 prudential returns in one place. Submit, track, audit.
Dept: Compliance | KPIs: K072 K073 K074
"""
import streamlit as st
from utils.config import currency_symbol, regulator
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log
from utils.db import db as a2z_db

require_access("compliance_regulatory.cbk_returns")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_comp  = any(x in role for x in ("compliance","finance","treasury","risk","manager","head","director","chief","md","ceo"))

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"cbk_returns.json", table="cbk_returns")

def _save(data):
    a2z_db.dual_save(DATA/"cbk_returns.json", data, table="cbk_returns", flat_cols=('id', 'return_code', 'return_name', 'frequency', 'period', 'due_date', 'submitted', 'on_time', 'status', 'department'))
    st.cache_data.clear()


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("cbk_returns",{}) if mc.exists() else {}


records  = _load()
cfg_c    = _cfg()
conf_cfg = cfg_c.get("configurable", {})
warn_days= conf_cfg.get("early_warning_days", 7)
min_acc  = conf_cfg.get("minimum_accuracy_pct", 95)

submitted_r = [r for r in records if r.get("submitted")]
on_time_r   = [r for r in submitted_r if r.get("on_time")]
overdue_r   = [r for r in records if r.get("status")=="Overdue"]
upcoming_r  = [r for r in records if r.get("status")=="Pending" and r.get("due_date","")<=str(today+timedelta(days=warn_days))]
findings    = sum(r.get("regulatory_findings",0) for r in submitted_r)
findings_cl = sum(r.get("findings_closed",0) for r in submitted_r)
on_time_pct = round(len(on_time_r)/max(len(submitted_r),1)*100,1)
acc_avg     = round(sum(r.get("accuracy_score",0) for r in submitted_r)/max(len(submitted_r),1),1)
findings_pct= round(findings_cl/max(findings,1)*100,1)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    f"<span style='font-size:22px;font-weight:800'>📊 {regulator()} Returns Centre</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Compliance · 47 returns · K072 · K073 · K074</span></div>",
    unsafe_allow_html=True)

if overdue_r:
    st.error(f"🔴 {len(overdue_r)} return(s) OVERDUE — late filing penalty {currency_symbol()} 50K each")
if upcoming_r:
    st.warning(f"⚠️ {len(upcoming_r)} return(s) due within {warn_days} days")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Total returns",  len(records))
m2.metric("On-time filed",  f"{on_time_pct}%", delta_color="off" if on_time_pct>=95 else "inverse")
m3.metric("Accuracy",       f"{acc_avg}%",     delta_color="off" if acc_avg>=min_acc else "inverse")
m4.metric("Overdue",        len(overdue_r),    delta_color="inverse" if overdue_r else "off")
m5.metric("Findings closed", f"{findings_cl}/{findings}")

tabs = st.tabs(["📋 Returns Calendar","🔴 Overdue & Upcoming","➕ Submit Return","🔍 Findings","📊 Analytics","⚙️ Config","📈 BSC"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    ffreq = f1.selectbox("Frequency",["All","Daily","Monthly","Quarterly","Annual"],key="cbk_freq")
    fstat = f2.selectbox("Status",["All","Submitted","Pending","Overdue"],key="cbk_stat")
    fdept = f3.selectbox("Department",["All"]+sorted(set(r.get("department","") for r in records)),key="cbk_dept")
    vis = [r for r in records
           if (ffreq=="All" or r.get("frequency","")==ffreq)
           and (fstat=="All" or r.get("status","")==fstat)
           and (fdept=="All" or r.get("department","")==fdept)]
    rows = [{"Code":r.get("return_code",""),"Return":r.get("return_name","")[:35],
              "Freq":r.get("frequency",""),"Period":r.get("period",""),
              "Due":r.get("due_date","")[:10],"Status":r.get("status",""),
              "On Time":"✅" if r.get("on_time") else "❌" if r.get("submitted") else "⏳",
              "Accuracy":f"{r.get('accuracy_score',0)}%" if r.get("submitted") else "—",
              "Findings":r.get("regulatory_findings",0),"Dept":r.get("department","")[:12]}
             for r in sorted(vis,key=lambda x:x.get("due_date",""))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

    # ──────────────────────────────────────────────────────────────────
    # Recent Generations enrichment (v10.267)
    # Reads cbk_returns_generated.json (populated by v10.266 wiring) and
    # surfaces the most recent CbkReturnPackages alongside the periodic
    # registry. Joins by return_code (CAR/LIQ/SBL/LXP/FXE/NPL/IRR/OPR
    # plus future BSD-1/2/3/17 from v10.268). Uses db.dual_load to
    # respect G2 direct_io gate — reads from PG when migrated, JSON
    # otherwise.
    # ──────────────────────────────────────────────────────────────────
    try:
        from utils.db import db as _gen_db
        _gen_rows = _gen_db.dual_load(
            DATA / "cbk_returns_generated.json",
            table="cbk_returns_generated",
            index_cols=("id",))
        if not isinstance(_gen_rows, list):
            _gen_rows = []
    except Exception:
        _gen_rows = []

    if _gen_rows:
        # Build a per-code latest-row index for the summary
        _latest_by_code = {}
        for _r in _gen_rows:
            _code = _r.get("return_code", "")
            _gen_at = _r.get("generated_at", "")
            if _code and _gen_at:
                _existing = _latest_by_code.get(_code)
                if _existing is None or _gen_at > _existing.get("generated_at", ""):
                    _latest_by_code[_code] = _r

        st.markdown("---")
        with st.expander(
            f"📈 Recent Generations from Auto-Generators "
            f"({len(_gen_rows)} total · "
            f"{len(_latest_by_code)} unique return codes)",
            expanded=False,
        ):
            # Severity emoji map (mirrors the badge colors in Risk-Based tabs)
            _sev_emoji = {
                "NONE": "🟢",
                "MARGINAL": "🟡",
                "BREACH": "🔴",
                "SEVERE_BREACH": "⛔",
            }

            # Per-code latest summary table — one row per unique return_code
            _summary_rows = []
            for _code, _r in sorted(_latest_by_code.items()):
                _sev = _r.get("breach_severity", "NONE")
                _summary_rows.append({
                    "Code": _code,
                    "Latest period": _r.get("period", ""),
                    "Last generated":
                        _r.get("generated_at", "")[:19].replace("T", " "),
                    "By": _r.get("generated_by", ""),
                    "Severity": f"{_sev_emoji.get(_sev, '⚪')} {_sev}",
                    "Description":
                        (_r.get("breach_description", "") or "")[:60],
                })
            st.markdown(
                f"**Latest generation per return code** "
                f"(joins to periodic registry above by code matching):")
            st.dataframe(pd.DataFrame(_summary_rows),
                          use_container_width=True, hide_index=True)

            # History — last 10 generations across all codes
            st.markdown("**Last 10 generations (chronological):**")
            _recent = sorted(_gen_rows,
                              key=lambda x: x.get("generated_at", ""),
                              reverse=True)[:10]
            _hist_rows = [{
                "Generated at":
                    _r.get("generated_at", "")[:19].replace("T", " "),
                "Code": _r.get("return_code", ""),
                "Period": _r.get("period", ""),
                "By": _r.get("generated_by", ""),
                "Severity": f"{_sev_emoji.get(_r.get('breach_severity', 'NONE'), '⚪')} "
                              f"{_r.get('breach_severity', 'NONE')}",
            } for _r in _recent]
            st.dataframe(pd.DataFrame(_hist_rows),
                          use_container_width=True, hide_index=True)
    else:
        st.caption(
            "💾 No generations persisted yet. Generate a return via "
            "Submit Return → BSD or Risk-Based Auto-Generators to "
            "populate this section.")

with tabs[1]:
    if overdue_r:
        st.markdown("**🔴 OVERDUE — file immediately:**")
        for r in overdue_r[:20]:
            with st.expander(f"🔴 {r.get('return_code','')} — {r.get('return_name','')} ({r.get('period','')})"):
                c1,c2,c3 = st.columns(3)
                c1.metric("Due date",r.get("due_date","")[:10])
                days_late = (today - date.fromisoformat(r.get("due_date","")[:10])).days
                c2.metric("Days late",days_late,delta_color="inverse")
                c3.metric("Penalty",f"{currency_symbol()} {50000*days_late:,}")
                if is_comp and st.button("Submit now",key=f"cbk_sub_{r['id']}",type="primary"):
                    all_r = _load()
                    for rec in all_r:
                        if rec["id"]==r["id"]:
                            rec["submitted"]=True; rec["submitted_date"]=str(today); rec["on_time"]=False
                            rec["submitted_by"]=uname; rec["status"]="Submitted"; rec["accuracy_score"]=90
                            break
                    _save(all_r); audit_log("CBK_RETURN_SUBMITTED",uname,r["return_code"])
                    _bsc_trigger(uname,"K072")
                    st.success("✅ Submitted (late)"); st.rerun()
    if upcoming_r:
        st.markdown(f"**⚠️ Upcoming within {warn_days} days:**")
        upc_rows = [{"Code":r.get("return_code",""),"Name":r.get("return_name","")[:30],
                      "Due":r.get("due_date","")[:10],"Days left":(date.fromisoformat(r.get("due_date","")[:10])-today).days,
                      "Department":r.get("department","")} for r in upcoming_r]
        st.dataframe(pd.DataFrame(upc_rows),use_container_width=True,hide_index=True)
    if not overdue_r and not upcoming_r:
        st.success("✅ No overdue or upcoming returns.")

with tabs[2]:
    _cbk_sub_tabs = st.tabs([
        "📝 Manual Submission",
        "🤖 BSD Auto-Generators (Standard #80, integrated v5.81)",
        f"🛡️ Risk-Based Auto-Generators (5 of 8 {regulator()} packages, integrated v10.262)",
    ])
    with _cbk_sub_tabs[0]:
        if is_comp or is_admin:
            pending_subs = [r for r in records if r.get("status") in ("Pending","Overdue")]
            if pending_subs:
                sel = st.selectbox("Select return to submit",
                                  [f"{r.get('return_code','')} — {r.get('return_name','')[:30]} ({r.get('period','')})" for r in pending_subs[:30]],
                                  key="cbk_sub_sel")
                sel_id = sel.split(" — ")[0]
                r = next((x for x in pending_subs if x.get("return_code","")==sel_id),{})
                if r:
                    st.markdown(f"**Period:** {r.get('period','')} | **Due:** {r.get('due_date','')[:10]} | **Frequency:** {r.get('frequency','')}")
                    acc_score = st.slider("Accuracy score (%)", 50, 100, 95, key="cbk_sub_acc")
                    queries  = st.number_input("Anticipated queries", 0, 10, 0, key="cbk_sub_q")
                    preparer = st.text_input("Preparer", uname, key="cbk_sub_prep")
                    reviewer = st.text_input("Reviewer", key="cbk_sub_rev")
                    approver = st.text_input("Approver", key="cbk_sub_app")
                    if st.button(f"📤 Submit to {regulator()}",key="cbk_sub_btn",type="primary"):
                        all_r = _load()
                        on_time = today <= date.fromisoformat(r.get("due_date","")[:10])
                        for rec in all_r:
                            if rec["id"]==r["id"]:
                                rec["submitted"]=True; rec["submitted_date"]=str(today)
                                rec["on_time"]=on_time; rec["submitted_by"]=uname
                                rec["status"]="Submitted"; rec["accuracy_score"]=acc_score
                                rec["queries_raised"]=queries; rec["preparer"]=preparer
                                rec["reviewer"]=reviewer; rec["approver"]=approver
                                break
                        _save(all_r); audit_log("CBK_RETURN_SUBMITTED",uname,r.get("return_code",""))
                        _bsc_trigger(uname,"K072")
                        st.success(f"✅ {sel_id} submitted ({'on time' if on_time else 'late'})"); st.rerun()
            else:
                st.success("✅ No pending returns to submit.")

    with _cbk_sub_tabs[1]:
        # ── BSD Auto-Generators (Standard #80, integrated v5.81) ──
        from utils.regulatory_returns import (
            RegulatoryReturnsEngine, Bsd1Inputs, Bsd2Inputs, Bsd3Inputs,
            LoanForClassification, BSD_RETURN_TYPES, RETURN_FREQUENCIES,
            LOAN_CLASSIFICATIONS, LOAN_CLASSIFICATION_DAYS, LOAN_PROVISION_PCT,
            STATUTORY_LIQUIDITY_RATIO_MIN_PCT,
        )
        from decimal import Decimal as _D_cbk
        from utils.cbk_regulatory_reporting import (
            save_bsd_result as _save_bsd,
        )

        st.markdown(
            f"**Standard #80 — {regulator()} Returns Auto-Generators**. "
            f"Four BSD return formats: BSD-1 (DAILY liquidity), "
            f"BSD-2 (WEEKLY balance sheet), BSD-3 (MONTHLY capital adequacy), "
            f"BSD-17 (MONTHLY credit quality)."
        )
        st.caption(
            f"Engine binds {regulator()} statutory thresholds byte-for-byte: "
            f"liquidity ratio ≥ {STATUTORY_LIQUIDITY_RATIO_MIN_PCT}% (BSD-1); "
            f"loan classifications NORMAL/WATCH/SUBSTANDARD/DOUBTFUL/LOSS by DPD "
            f"per LOAN_CLASSIFICATION_DAYS dict; provisions 1%/3%/20%/50%/100% per "
            f"LOAN_PROVISION_PCT dict (BSD-17)."
        )

        bsd_tabs = st.tabs([
            "💧 BSD-1 (Daily Liquidity)",
            "📊 BSD-2 (Weekly Balance Sheet)",
            "💰 BSD-3 (Monthly Capital Adequacy)",
            "🏦 BSD-17 (Monthly Credit Quality)",
        ])

        # ──────── BSD-1 ────────
        with bsd_tabs[0]:
            st.markdown(
                f"**BSD-1 Daily Liquidity Return** — frequency: "
                f"{RETURN_FREQUENCIES['BSD_1']}. "
                f"Statutory liquidity ratio = (cash + CB balances + T-bills + "
                f"other liquid assets) / total deposits ≥ "
                f"{STATUTORY_LIQUIDITY_RATIO_MIN_PCT}%."
            )
            c1, c2 = st.columns(2)
            with c1:
                b1_cash = st.number_input(f"Cash ({currency_symbol()} B)",
                                            min_value=0.0, value=3.0, step=0.5,
                                            key="bsd1_cash")
                b1_cb = st.number_input(f"Central Bank balances ({currency_symbol()} B)",
                                          min_value=0.0, value=12.0, step=1.0,
                                          key="bsd1_cb",
                                          help=f"Statutory + free reserves at {regulator()}.")
                b1_tb = st.number_input(f"Treasury bills ({currency_symbol()} B)",
                                          min_value=0.0, value=8.0, step=1.0,
                                          key="bsd1_tb")
            with c2:
                b1_other = st.number_input(f"Other liquid assets ({currency_symbol()} B)",
                                             min_value=0.0, value=2.0, step=0.5,
                                             key="bsd1_other")
                b1_dep = st.number_input(f"Total deposits ({currency_symbol()} B)",
                                           min_value=0.0, value=100.0, step=5.0,
                                           key="bsd1_dep")

            if st.button("Generate BSD-1", key="bsd1_btn", type="primary"):
                inp = Bsd1Inputs(
                    reporting_date=today,
                    cash_kes=_D_cbk(str(b1_cash)) * _D_cbk("1000000000"),
                    central_bank_balances_kes=_D_cbk(str(b1_cb)) * _D_cbk("1000000000"),
                    treasury_bills_kes=_D_cbk(str(b1_tb)) * _D_cbk("1000000000"),
                    other_liquid_assets_kes=_D_cbk(str(b1_other)) * _D_cbk("1000000000"),
                    total_deposits_kes=_D_cbk(str(b1_dep)) * _D_cbk("1000000000"),
                )
                r = RegulatoryReturnsEngine.generate_bsd1_daily_liquidity(inp)
                if r.get("generated"):
                    ratio = _D_cbk(str(r["liquidity_ratio_pct"]))
                    compliant = r.get("compliant")
                    color = "#10B981" if compliant else "#DC2626"

                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("Liquid assets",
                               f"{currency_symbol()} {_D_cbk(str(r['liquid_assets_kes']))/_D_cbk('1000000000'):,.2f}B")
                    k2.metric("Total deposits",
                               f"{currency_symbol()} {_D_cbk(str(r['total_deposits_kes']))/_D_cbk('1000000000'):,.2f}B")
                    k3.metric("Liquidity ratio",
                               f"{ratio}%",
                               delta=f"vs {STATUTORY_LIQUIDITY_RATIO_MIN_PCT}% min")
                    with k4:
                        st.markdown(
                            f"<div style='padding:8px 12px;background:{color}22;"
                            f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                            f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                            f"BSD-1 STATUS</div>"
                            f"<div style='font-size:20px;font-weight:800;color:{color}'>"
                            f"{'COMPLIANT' if compliant else 'BREACH'}</div></div>",
                            unsafe_allow_html=True)

                    if compliant:
                        st.success(
                            f"✅ Liquidity ratio {ratio}% meets {regulator()} minimum "
                            f"of {STATUTORY_LIQUIDITY_RATIO_MIN_PCT}%.")
                    else:
                        st.error(
                            f"⛔ Liquidity ratio {ratio}% **BELOW** {regulator()} minimum. "
                            f"Daily breach must be reported and remediated.")
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"CBK Returns #80: BSD-1 ratio={ratio}% "
                               f"compliant={compliant}")
                    _persist = _save_bsd(
                        r, "BSD-1", str(today), uname, DATA)
                    if _persist.get("persisted"):
                        st.caption(
                            f"💾 Persisted (id={_persist['data']['id']}, "
                            f"PG={'✅' if _persist.get('pg_persisted') else '—'})")

        # ──────── BSD-2 ────────
        with bsd_tabs[1]:
            st.markdown(
                f"**BSD-2 Weekly Balance Sheet Return** — frequency: "
                f"{RETURN_FREQUENCIES['BSD_2']}. "
                "Engine validates the accounting equation Assets = Liabilities + Equity "
                "and flags any imbalance for review.")
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Assets:**")
                b2_cash = st.number_input(f"Cash & equivalents ({currency_symbol()} B)",
                                            min_value=0.0, value=15.0, step=1.0,
                                            key="bsd2_cash")
                b2_loans = st.number_input("Loans & advances (KES B)",
                                             min_value=0.0, value=120.0, step=5.0,
                                             key="bsd2_loans")
                b2_inv = st.number_input("Investments (KES B)",
                                           min_value=0.0, value=50.0, step=2.0,
                                           key="bsd2_inv")
                b2_other_a = st.number_input("Other assets (KES B)",
                                                min_value=0.0, value=5.0, step=0.5,
                                                key="bsd2_other_a")
            with c2:
                st.markdown("**Liabilities & Equity:**")
                b2_dep = st.number_input("Deposits (KES B)",
                                           min_value=0.0, value=130.0, step=5.0,
                                           key="bsd2_dep")
                b2_borr = st.number_input("Borrowings (KES B)",
                                            min_value=0.0, value=30.0, step=2.0,
                                            key="bsd2_borr")
                b2_other_l = st.number_input("Other liabilities (KES B)",
                                                min_value=0.0, value=8.0, step=0.5,
                                                key="bsd2_other_l")
                b2_eq = st.number_input("Shareholders' equity (KES B)",
                                          min_value=0.0, value=22.0, step=1.0,
                                          key="bsd2_eq")

            if st.button("Generate BSD-2", key="bsd2_btn", type="primary"):
                inp = Bsd2Inputs(
                    reporting_date=today,
                    cash_and_equivalents_kes=_D_cbk(str(b2_cash)) * _D_cbk("1000000000"),
                    loans_and_advances_kes=_D_cbk(str(b2_loans)) * _D_cbk("1000000000"),
                    investments_kes=_D_cbk(str(b2_inv)) * _D_cbk("1000000000"),
                    other_assets_kes=_D_cbk(str(b2_other_a)) * _D_cbk("1000000000"),
                    deposits_kes=_D_cbk(str(b2_dep)) * _D_cbk("1000000000"),
                    borrowings_kes=_D_cbk(str(b2_borr)) * _D_cbk("1000000000"),
                    other_liabilities_kes=_D_cbk(str(b2_other_l)) * _D_cbk("1000000000"),
                    shareholders_equity_kes=_D_cbk(str(b2_eq)) * _D_cbk("1000000000"),
                )
                r = RegulatoryReturnsEngine.generate_bsd2_balance_sheet(inp)
                if r.get("generated"):
                    bal_ok = r.get("balance_check_passed")
                    diff = _D_cbk(str(r["balance_check_diff_kes"]))
                    color = "#10B981" if bal_ok else "#DC2626"

                    k1, k2, k3 = st.columns(3)
                    k1.metric("Total assets",
                               f"{currency_symbol()} {_D_cbk(str(r['total_assets_kes']))/_D_cbk('1000000000'):,.2f}B")
                    k2.metric("Total liab. + equity",
                               f"{currency_symbol()} {_D_cbk(str(r['total_liabilities_plus_equity_kes']))/_D_cbk('1000000000'):,.2f}B")
                    with k3:
                        st.markdown(
                            f"<div style='padding:8px 12px;background:{color}22;"
                            f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                            f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                            f"BALANCE CHECK</div>"
                            f"<div style='font-size:20px;font-weight:800;color:{color}'>"
                            f"{'BALANCED' if bal_ok else 'IMBALANCE'}</div></div>",
                            unsafe_allow_html=True)

                    if bal_ok:
                        st.success("✅ Balance sheet balances exactly.")
                    else:
                        st.error(
                            f"⛔ Imbalance of KES {abs(diff)/_D_cbk('1000000000'):,.4f}B. "
                            f"Investigate before submission to CBK.")
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"CBK Returns #80: BSD-2 balance check={bal_ok} "
                               f"diff={diff}")
                    _persist = _save_bsd(
                        r, "BSD-2", str(today)[:7], uname, DATA)
                    if _persist.get("persisted"):
                        st.caption(
                            f"💾 Persisted (id={_persist['data']['id']}, "
                            f"PG={'✅' if _persist.get('pg_persisted') else '—'})")

        # ──────── BSD-3 ────────
        with bsd_tabs[2]:
            st.markdown(
                f"**BSD-3 Monthly Capital Adequacy Return** — frequency: "
                f"{RETURN_FREQUENCIES['BSD_3']}. "
                "Computes CET1 ratio, Tier 1 ratio, total CAR. "
                "Engine flags compliance against CBK total CAR floor."
            )
            c1, c2 = st.columns(2)
            with c1:
                b3_cet1 = st.number_input("CET1 (KES B)",
                                            min_value=0.0, value=18.0, step=0.5,
                                            key="bsd3_cet1",
                                            help="Common Equity Tier 1 capital.")
                b3_t1 = st.number_input("Tier 1 (KES B)",
                                          min_value=0.0, value=20.0, step=0.5,
                                          key="bsd3_t1",
                                          help="Tier 1 = CET1 + Additional Tier 1.")
            with c2:
                b3_tc = st.number_input("Total capital (KES B)",
                                          min_value=0.0, value=25.0, step=0.5,
                                          key="bsd3_tc",
                                          help="Tier 1 + Tier 2.")
                b3_rwa = st.number_input("Total RWA (KES B)",
                                           min_value=0.0, value=150.0, step=5.0,
                                           key="bsd3_rwa")

            if st.button("Generate BSD-3", key="bsd3_btn", type="primary"):
                inp = Bsd3Inputs(
                    reporting_date=today,
                    cet1_kes=_D_cbk(str(b3_cet1)) * _D_cbk("1000000000"),
                    tier1_kes=_D_cbk(str(b3_t1)) * _D_cbk("1000000000"),
                    total_capital_kes=_D_cbk(str(b3_tc)) * _D_cbk("1000000000"),
                    total_rwa_kes=_D_cbk(str(b3_rwa)) * _D_cbk("1000000000"),
                )
                r = RegulatoryReturnsEngine.generate_bsd3_capital_adequacy(inp)
                if r.get("generated"):
                    cet1_pct = _D_cbk(str(r["cet1_ratio_pct"]))
                    t1_pct = _D_cbk(str(r["tier1_ratio_pct"]))
                    car = _D_cbk(str(r["total_car_pct"]))
                    compliant = r.get("compliant_cbk")
                    color = "#10B981" if compliant else "#DC2626"

                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric("CET1 ratio", f"{cet1_pct}%")
                    k2.metric("Tier 1 ratio", f"{t1_pct}%")
                    k3.metric("Total CAR", f"{car}%")
                    with k4:
                        st.markdown(
                            f"<div style='padding:8px 12px;background:{color}22;"
                            f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                            f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                            f"CBK COMPLIANT</div>"
                            f"<div style='font-size:20px;font-weight:800;color:{color}'>"
                            f"{'YES' if compliant else 'NO'}</div></div>",
                            unsafe_allow_html=True)

                    if not compliant:
                        st.error(
                            "⛔ CAR ratios BELOW CBK prudential minimum. "
                            "Capital plan required per CBK PG/02.")
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"CBK Returns #80: BSD-3 CET1={cet1_pct}% T1={t1_pct}% "
                               f"CAR={car}% compliant={compliant}")
                    _persist = _save_bsd(
                        r, "BSD-3", str(today)[:7], uname, DATA)
                    if _persist.get("persisted"):
                        st.caption(
                            f"💾 Persisted (id={_persist['data']['id']}, "
                            f"PG={'✅' if _persist.get('pg_persisted') else '—'})")

        # ──────── BSD-17 ────────
        with bsd_tabs[3]:
            st.markdown(
                f"**BSD-17 Monthly Credit Quality Return** — frequency: "
                f"{RETURN_FREQUENCIES['BSD_17']}. "
                "Classifies loans by days past due into 5 CBK categories with "
                "engine-bound provisioning percentages."
            )

            with st.expander("Loan classification reference (engine constants)"):
                ref_rows = [
                    {"Class": cls,
                      "DPD range":
                          f"{LOAN_CLASSIFICATION_DAYS[cls][0]}-{LOAN_CLASSIFICATION_DAYS[cls][1]} days"
                          if LOAN_CLASSIFICATION_DAYS[cls][1] < 99999
                          else f"≥{LOAN_CLASSIFICATION_DAYS[cls][0]} days",
                      "Provision %": f"{LOAN_PROVISION_PCT[cls]}%"}
                    for cls in LOAN_CLASSIFICATIONS
                ]
                st.dataframe(pd.DataFrame(ref_rows),
                             use_container_width=True, hide_index=True)

            st.markdown("**Sample loans for classification** (edit to test scenarios):")
            loan_data = []
            default_loans = [
                ("L001", 5.0, 10),    # NORMAL
                ("L002", 3.0, 45),    # WATCH
                ("L003", 2.0, 75),    # SUBSTANDARD
                ("L004", 4.0, 120),   # DOUBTFUL
                ("L005", 1.5, 250),   # LOSS
                ("L006", 2.5, 5),     # NORMAL
                ("L007", 3.5, 25),    # NORMAL
            ]
            for i, (lid, lout, ldpd) in enumerate(default_loans):
                lc1, lc2, lc3 = st.columns([1, 1.5, 1])
                with lc1:
                    loan_id = st.text_input(f"Loan {i+1} ID",
                                               value=lid, key=f"bsd17_id_{i}")
                with lc2:
                    out_v = st.number_input(f"Outstanding (KES M)",
                                              min_value=0.0, value=lout, step=0.1,
                                              key=f"bsd17_out_{i}")
                with lc3:
                    dpd_v = st.number_input(f"DPD",
                                              min_value=0, value=ldpd, step=1,
                                              key=f"bsd17_dpd_{i}")
                if loan_id.strip() and out_v > 0:
                    loan_data.append((loan_id.strip(), out_v, dpd_v))

            if st.button("Generate BSD-17", key="bsd17_btn", type="primary"):
                if not loan_data:
                    st.warning("Add at least one loan with outstanding > 0.")
                else:
                    loans = [
                        LoanForClassification(
                            loan_id=lid,
                            outstanding_kes=_D_cbk(str(out_v)) * _D_cbk("1000000"),
                            days_past_due=int(dpd_v))
                        for lid, out_v, dpd_v in loan_data
                    ]
                    r = RegulatoryReturnsEngine.generate_bsd17_credit_quality(loans)
                    if r.get("generated"):
                        npl_ratio = _D_cbk(str(r["npl_ratio_pct"]))
                        npl_color = ("#10B981" if npl_ratio < _D_cbk("5")
                                       else "#F59E0B" if npl_ratio < _D_cbk("10")
                                       else "#DC2626")
                        prov_total = _D_cbk(str(r["total_provisions_kes"]))
                        book_total = _D_cbk(str(r["total_loan_book_kes"]))

                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("Loan count", r.get("loan_count"))
                        k2.metric("Total book",
                                   f"KES {book_total/_D_cbk('1000000'):,.2f}M")
                        k3.metric("NPL ratio",
                                   f"{npl_ratio}%")
                        k4.metric("Provisions",
                                   f"KES {prov_total/_D_cbk('1000000'):,.2f}M",
                                   delta=f"{(prov_total/book_total*100 if book_total else 0):.1f}% of book"
                                          if book_total else None)

                        # Per-classification breakdown
                        by_cls = r.get("by_classification_kes", {})
                        cls_rows = [
                            {"Classification": cls,
                              "DPD range":
                                  f"{LOAN_CLASSIFICATION_DAYS[cls][0]}-{LOAN_CLASSIFICATION_DAYS[cls][1]}"
                                  if LOAN_CLASSIFICATION_DAYS[cls][1] < 99999
                                  else f"≥{LOAN_CLASSIFICATION_DAYS[cls][0]}",
                              "Outstanding (KES M)":
                                  float(_D_cbk(str(by_cls.get(cls, "0"))) / _D_cbk("1000000")),
                              "Provision rate":
                                  f"{LOAN_PROVISION_PCT[cls]}%",
                              "Implied provision (KES M)":
                                  float(_D_cbk(str(by_cls.get(cls, "0"))) *
                                          LOAN_PROVISION_PCT[cls] /
                                          _D_cbk("100") / _D_cbk("1000000"))}
                            for cls in LOAN_CLASSIFICATIONS
                        ]
                        st.dataframe(pd.DataFrame(cls_rows),
                                     use_container_width=True, hide_index=True)

                        if r.get("excluded_count", 0) > 0:
                            st.warning(
                                f"⚠ {r['excluded_count']} loan(s) excluded — "
                                "missing outstanding or DPD (Rule 6 transparency).")

                        audit_log("IFRS_ENGINE_USED", uname,
                                   f"CBK Returns #80: BSD-17 {r['loan_count']} loans, "
                                   f"NPL={npl_ratio}%, provisions={prov_total}")
                        _persist = _save_bsd(
                            r, "BSD-17", str(today)[:7], uname, DATA)
                        if _persist.get("persisted"):
                            st.caption(
                                f"💾 Persisted (id={_persist['data']['id']}, "
                                f"PG={'✅' if _persist.get('pg_persisted') else '—'})")

    # ──────────────────────────────────────────────────────────────────
    # Risk-Based Auto-Generators (v10.262 + v10.263 + v10.264)
    # 5 of the 8 risk-based regulatory packages NOT covered by
    # BSD-1/2/3/17 above. Engine code in utils/cbk_regulatory_reporting.py;
    # this UI surfaces inputs + computes + displays breach severity.
    # ──────────────────────────────────────────────────────────────────
    with _cbk_sub_tabs[2]:
        from utils.cbk_regulatory_reporting import (
            CBKRegulatoryReportingEngine as _RbEngine,
            BorrowerExposure, CurrencyPosition, NplStaging,
            IrrComponents, OperationalRiskComponents, BreachSeverity,
            save_cbk_package as _save_pkg,
        )
        _engine_rb = _RbEngine()
        _D_rb = _D_cbk  # reuse Decimal helper from BSD section

        st.markdown(
            f"**Risk-Based Auto-Generators** — 5 {regulator()} return packages "
            f"computed from the engine's typed inputs, with statutory "
            f"thresholds binding byte-for-byte. Output is a "
            f"`CbkReturnPackage` with computed metrics + breach severity "
            f"+ framework refs ({regulator()} PG/04, PG/05, BCBS SRP31)."
        )
        st.caption(
            f"Statutory thresholds (per {regulator()} prudential guidelines): "
            f"SBL ≤ {_engine_rb.SBL_MAXIMUM_PCT * 100:.0f}% of core capital · "
            f"LXP ≤ {_engine_rb.LXP_AGGREGATE_MAX_MULTIPLE}× core capital · "
            f"FXE per-currency ≤ {_engine_rb.FXE_PER_CURRENCY_LIMIT_PCT * 100:.0f}% · "
            f"IRRBB Δ EVE ≤ {_engine_rb.IRRBB_DELTA_EVE_MAX_PCT_OF_TIER1 * 100:.0f}% of Tier 1 · "
            f"OPR α = {_engine_rb.OPR_ALPHA * 100:.0f}% (Basel II SA)."
        )

        rb_tabs = st.tabs([
            "🎯 SBL (Single Borrower Limit)",
            "📊 LXP (Large Exposures)",
            "💱 FXE (Forex Exposure)",
            "📈 IRR (Interest Rate Risk)",
            "⚠️ OPR (Operational Risk)",
        ])

        # Helper — render the breach severity badge consistently across all 5
        def _render_severity_badge(sev_label: str, status_label: str = "STATUS"):
            color_map = {
                "NONE": "#10B981",
                "MARGINAL": "#F59E0B",
                "BREACH": "#DC2626",
                "SEVERE_BREACH": "#7F1D1D",
            }
            c = color_map.get(sev_label, "#6B7280")
            label_text = {
                "NONE": "COMPLIANT",
                "MARGINAL": "MARGINAL",
                "BREACH": "BREACH",
                "SEVERE_BREACH": "SEVERE BREACH",
            }.get(sev_label, sev_label)
            st.markdown(
                f"<div style='padding:8px 12px;background:{c}22;"
                f"border-left:4px solid {c};border-radius:8px;text-align:center'>"
                f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                f"{status_label}</div>"
                f"<div style='font-size:20px;font-weight:800;color:{c}'>"
                f"{label_text}</div></div>",
                unsafe_allow_html=True)

        # ──────── SBL — Single Borrower Limit ────────
        with rb_tabs[0]:
            st.markdown(
                f"**SBL — Single Borrower Limit**. Per {regulator()} PG/05, "
                f"no single borrower's total exposure (funded + unfunded) may "
                f"exceed **25% of core capital**. Insider/related-party "
                f"borrowers carry stricter sub-limits (managed separately)."
            )
            sbl_c1, sbl_c2 = st.columns([1, 2])
            with sbl_c1:
                sbl_core = st.number_input(
                    f"Core capital ({currency_symbol()} B)",
                    min_value=0.1, value=15.0, step=1.0,
                    key="rb_sbl_core",
                    help="Tier 1 + permitted Tier 2 instruments")
                sbl_period = st.text_input(
                    "Period", value=str(today)[:7],
                    key="rb_sbl_period")
            with sbl_c2:
                st.caption(
                    f"Enter top borrowers by total exposure. The engine "
                    f"computes each as % of core capital and identifies "
                    f"any that exceed {_engine_rb.SBL_MAXIMUM_PCT * 100:.0f}%.")
                sbl_n = st.number_input("Number of borrowers", 1, 20, 5,
                                          key="rb_sbl_n")

            sbl_borrowers = []
            for i in range(int(sbl_n)):
                sbc1, sbc2, sbc3, sbc4 = st.columns([1.5, 2, 1, 1])
                with sbc1:
                    bid = st.text_input(f"ID #{i+1}",
                                         value=f"B{i+1:03d}",
                                         key=f"rb_sbl_id_{i}")
                with sbc2:
                    bname = st.text_input(f"Name #{i+1}",
                                            value=f"Borrower {i+1}",
                                            key=f"rb_sbl_name_{i}")
                with sbc3:
                    bfund = st.number_input(
                        f"Funded ({currency_symbol()} M)",
                        min_value=0.0, value=float(500.0 - i * 50),
                        step=10.0, key=f"rb_sbl_f_{i}")
                with sbc4:
                    bunf = st.number_input(
                        f"Unfunded ({currency_symbol()} M)",
                        min_value=0.0, value=float(100.0 - i * 10),
                        step=10.0, key=f"rb_sbl_u_{i}")
                if bid.strip():
                    sbl_borrowers.append((bid.strip(), bname,
                                            bfund, bunf))

            if st.button("Generate SBL", key="rb_sbl_btn", type="primary"):
                if not sbl_borrowers:
                    st.warning("Add at least one borrower with non-empty ID.")
                else:
                    try:
                        exposures = [
                            BorrowerExposure(
                                borrower_id=bid,
                                borrower_name=bname,
                                funded_kes=_D_rb(str(bf)) * _D_rb("1000000"),
                                unfunded_kes=_D_rb(str(bu)) * _D_rb("1000000"))
                            for bid, bname, bf, bu in sbl_borrowers
                        ]
                        pkg = _engine_rb.generate_sbl(
                            period=sbl_period,
                            core_capital_kes=_D_rb(str(sbl_core))
                                * _D_rb("1000000000"),
                            exposures=exposures)

                        m = pkg.computed_metrics
                        top_pct = m.get("top_borrower_pct_of_core",
                                         _D_rb("0"))
                        breach_count = int(m.get("borrowers_in_breach", 0))

                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("Top borrower %",
                                   f"{top_pct * 100:.2f}%",
                                   delta=f"vs {_engine_rb.SBL_MAXIMUM_PCT * 100:.0f}% max")
                        k2.metric("Top exposure",
                                   f"{currency_symbol()} {m['top_borrower_exposure_kes']/_D_rb('1000000'):.1f}M")
                        k3.metric("Borrowers in breach", breach_count)
                        with k4:
                            _render_severity_badge(
                                pkg.breach_severity.value,
                                "SBL STATUS")

                        st.info(pkg.breach_description)
                        with st.expander("Framework refs + raw output"):
                            st.code("\n".join(pkg.framework_refs))
                            st.json({k: str(v) for k, v in m.items()})

                        audit_log("CBK_RETURN_GENERATED", uname,
                                   f"SBL period={sbl_period} top%={top_pct} "
                                   f"breaches={breach_count}")
                        _persist = _save_pkg(pkg, uname, DATA)
                        if _persist.get("persisted"):
                            st.caption(
                                f"💾 Persisted (id={_persist['data']['id']}, "
                                f"PG={'✅' if _persist.get('pg_persisted') else '—'})")
                        else:
                            st.caption(
                                f"⚠ Could not persist: "
                                f"{_persist.get('error', 'unknown error')}")
                    except ValueError as e:
                        st.error(f"⛔ Validation: {e}")

        # ──────── LXP — Large Exposures ────────
        with rb_tabs[1]:
            st.markdown(
                f"**LXP — Large Exposures**. Per {regulator()} PG/05, the "
                f"sum of all *large* exposures (each ≥10% of core capital) "
                f"may not exceed **8× core capital** in aggregate. Large-"
                f"exposure registers track these separately for granular "
                f"supervisory reporting."
            )
            lxp_c1, lxp_c2 = st.columns([1, 2])
            with lxp_c1:
                lxp_core = st.number_input(
                    f"Core capital ({currency_symbol()} B)",
                    min_value=0.1, value=15.0, step=1.0,
                    key="rb_lxp_core")
                lxp_period = st.text_input(
                    "Period", value=str(today)[:7],
                    key="rb_lxp_period")
            with lxp_c2:
                st.caption(
                    f"Enter exposures of size ≥{_engine_rb.LXP_LARGE_EXPOSURE_THRESHOLD_PCT * 100:.0f}% "
                    f"of core capital. The engine sums them and reports the "
                    f"aggregate as a multiple of core capital. Threshold: "
                    f"{_engine_rb.LXP_AGGREGATE_MAX_MULTIPLE}× max.")
                lxp_n = st.number_input("Number of large exposures", 1, 30, 8,
                                          key="rb_lxp_n")

            lxp_exposures = []
            for i in range(int(lxp_n)):
                lxc1, lxc2, lxc3, lxc4 = st.columns([1.5, 2, 1, 1])
                with lxc1:
                    bid = st.text_input(f"ID #{i+1}",
                                         value=f"L{i+1:03d}",
                                         key=f"rb_lxp_id_{i}")
                with lxc2:
                    bname = st.text_input(f"Name #{i+1}",
                                            value=f"Large Counterparty {i+1}",
                                            key=f"rb_lxp_name_{i}")
                with lxc3:
                    bfund = st.number_input(
                        f"Funded ({currency_symbol()} M)",
                        min_value=0.0, value=float(2000.0 - i * 100),
                        step=50.0, key=f"rb_lxp_f_{i}")
                with lxc4:
                    bunf = st.number_input(
                        f"Unfunded ({currency_symbol()} M)",
                        min_value=0.0, value=float(500.0 - i * 25),
                        step=25.0, key=f"rb_lxp_u_{i}")
                if bid.strip():
                    lxp_exposures.append((bid.strip(), bname,
                                            bfund, bunf))

            if st.button("Generate LXP", key="rb_lxp_btn", type="primary"):
                if not lxp_exposures:
                    st.warning("Add at least one exposure with non-empty ID.")
                else:
                    try:
                        exposures = [
                            BorrowerExposure(
                                borrower_id=bid,
                                borrower_name=bname,
                                funded_kes=_D_rb(str(bf)) * _D_rb("1000000"),
                                unfunded_kes=_D_rb(str(bu)) * _D_rb("1000000"))
                            for bid, bname, bf, bu in lxp_exposures
                        ]
                        pkg = _engine_rb.generate_lxp(
                            period=lxp_period,
                            core_capital_kes=_D_rb(str(lxp_core))
                                * _D_rb("1000000000"),
                            exposures=exposures)

                        m = pkg.computed_metrics
                        large_count = int(m.get("large_exposure_count", 0))
                        agg_mult = m.get("aggregate_multiple_of_core",
                                          _D_rb("0"))
                        agg_kes = m.get("aggregate_kes", _D_rb("0"))

                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("Large exposures", large_count)
                        k2.metric("Aggregate",
                                   f"{currency_symbol()} {agg_kes/_D_rb('1000000000'):.2f}B")
                        k3.metric("× core capital",
                                   f"{agg_mult}×",
                                   delta=f"vs {_engine_rb.LXP_AGGREGATE_MAX_MULTIPLE}× max")
                        with k4:
                            _render_severity_badge(
                                pkg.breach_severity.value,
                                "LXP STATUS")

                        st.info(pkg.breach_description)
                        with st.expander("Framework refs + raw output"):
                            st.code("\n".join(pkg.framework_refs))
                            st.json({k: str(v) for k, v in m.items()})

                        audit_log("CBK_RETURN_GENERATED", uname,
                                   f"LXP period={lxp_period} agg={agg_mult}× "
                                   f"large={large_count}")
                        _persist = _save_pkg(pkg, uname, DATA)
                        if _persist.get("persisted"):
                            st.caption(
                                f"💾 Persisted (id={_persist['data']['id']}, "
                                f"PG={'✅' if _persist.get('pg_persisted') else '—'})")
                        else:
                            st.caption(
                                f"⚠ Could not persist: "
                                f"{_persist.get('error', 'unknown error')}")
                    except ValueError as e:
                        st.error(f"⛔ Validation: {e}")

        # ──────── FXE — Forex Exposure ────────
        with rb_tabs[2]:
            st.markdown(
                f"**FXE — Forex Exposure**. Per {regulator()} PG/06, the "
                f"net open position in any single non-{currency_symbol()} "
                f"currency may not exceed **±10% of core capital**. "
                f"Aggregate net open position is limited separately. The "
                f"engine computes per-currency net = |long − short| and "
                f"flags any currency above the threshold."
            )
            fxe_c1, fxe_c2 = st.columns([1, 2])
            with fxe_c1:
                fxe_core = st.number_input(
                    f"Core capital ({currency_symbol()} B)",
                    min_value=0.1, value=15.0, step=1.0,
                    key="rb_fxe_core")
                fxe_period = st.text_input(
                    "Period", value=str(today)[:7],
                    key="rb_fxe_period")
            with fxe_c2:
                st.caption(
                    f"Enter open positions per currency. The engine "
                    f"computes net = |long − short| in {currency_symbol()} "
                    f"equivalent and reports each as % of core capital. "
                    f"Threshold: {_engine_rb.FXE_PER_CURRENCY_LIMIT_PCT * 100:.0f}% "
                    f"per currency (BCBS standard).")
                fxe_default_curs = ["USD", "EUR", "GBP", "ZAR", "UGX"]
                fxe_curs_input = st.text_input(
                    "Currencies (comma-separated, no " + currency_symbol() + ")",
                    value=", ".join(fxe_default_curs),
                    key="rb_fxe_curs",
                    help=f"List of foreign currencies to report. "
                         f"{currency_symbol()} (home) is excluded by the engine.")
                fxe_curs = [c.strip().upper() for c in fxe_curs_input.split(",")
                             if c.strip()]

            # Per-currency long/short input rows
            fxe_positions = []
            default_longs = [800, 400, 200, 100, 50]   # in M
            default_shorts = [600, 350, 180, 80, 40]
            for i, cur in enumerate(fxe_curs):
                fxc1, fxc2, fxc3 = st.columns([1, 1, 1])
                with fxc1:
                    st.text_input(f"Currency #{i+1}", value=cur,
                                   disabled=True, key=f"rb_fxe_cur_{i}")
                with fxc2:
                    long_v = st.number_input(
                        f"Long ({currency_symbol()} M)",
                        min_value=0.0,
                        value=float(default_longs[i] if i < len(default_longs)
                                     else 100),
                        step=10.0, key=f"rb_fxe_long_{i}")
                with fxc3:
                    short_v = st.number_input(
                        f"Short ({currency_symbol()} M)",
                        min_value=0.0,
                        value=float(default_shorts[i] if i < len(default_shorts)
                                     else 80),
                        step=10.0, key=f"rb_fxe_short_{i}")
                if cur:
                    fxe_positions.append((cur, long_v, short_v))

            if st.button("Generate FXE", key="rb_fxe_btn", type="primary"):
                if not fxe_positions:
                    st.warning("Add at least one currency.")
                else:
                    try:
                        positions = [
                            CurrencyPosition(
                                currency=cur,
                                long_kes_equivalent=_D_rb(str(long_v))
                                    * _D_rb("1000000"),
                                short_kes_equivalent=_D_rb(str(short_v))
                                    * _D_rb("1000000"))
                            for cur, long_v, short_v in fxe_positions
                        ]
                        pkg = _engine_rb.generate_fxe(
                            period=fxe_period,
                            core_capital_kes=_D_rb(str(fxe_core))
                                * _D_rb("1000000000"),
                            positions=positions)

                        m = pkg.computed_metrics
                        worst_pct = m.get("worst_pct_of_core", _D_rb("0"))
                        breach_count = int(m.get("currencies_in_breach", 0))

                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("Currencies", int(m.get("currency_count", 0)))
                        k2.metric("Worst position",
                                   f"{worst_pct * 100:.2f}%",
                                   delta=f"vs {_engine_rb.FXE_PER_CURRENCY_LIMIT_PCT * 100:.0f}% max")
                        k3.metric("In breach", breach_count)
                        with k4:
                            _render_severity_badge(
                                pkg.breach_severity.value,
                                "FXE STATUS")

                        st.info(pkg.breach_description)

                        # Per-currency breakdown
                        per_cur_pcts = {
                            k.replace("pct_", ""): float(v) * 100
                            for k, v in pkg.inputs_used.items()
                            if k.startswith("pct_")
                        }
                        if per_cur_pcts:
                            cur_df = pd.DataFrame([
                                {"Currency": cur,
                                 "Net % of core": f"{pct:.2f}%",
                                 "Status": ("⛔ BREACH"
                                              if pct > float(_engine_rb.FXE_PER_CURRENCY_LIMIT_PCT) * 100
                                              else "✅ OK")}
                                for cur, pct in per_cur_pcts.items()
                            ])
                            st.dataframe(cur_df,
                                         use_container_width=True,
                                         hide_index=True)

                        with st.expander("Framework refs + raw output"):
                            st.code("\n".join(pkg.framework_refs))
                            st.json({k: str(v) for k, v in m.items()})

                        audit_log("CBK_RETURN_GENERATED", uname,
                                   f"FXE period={fxe_period} worst%={worst_pct} "
                                   f"breaches={breach_count}")
                        _persist = _save_pkg(pkg, uname, DATA)
                        if _persist.get("persisted"):
                            st.caption(
                                f"💾 Persisted (id={_persist['data']['id']}, "
                                f"PG={'✅' if _persist.get('pg_persisted') else '—'})")
                        else:
                            st.caption(
                                f"⚠ Could not persist: "
                                f"{_persist.get('error', 'unknown error')}")
                    except ValueError as e:
                        st.error(f"⛔ Validation: {e}")

        # ──────── IRR — Interest Rate Risk in Banking Book ────────
        with rb_tabs[3]:
            st.markdown(
                f"**IRR — Interest Rate Risk in Banking Book**. Per "
                f"{regulator()} PG/03 §5 + BCBS SRP31, banks must report "
                f"the change in Economic Value of Equity (Δ EVE) under "
                f"a parallel ±200bps rate shock. Banks above **15% of "
                f"Tier 1 capital** are classified as outliers requiring "
                f"supervisory review."
            )
            st.caption(
                f"Caller supplies the worst-case Δ EVE (typically the "
                f"larger absolute value of +200bps and -200bps shock "
                f"results from your ALM model). Sign convention: positive = "
                f"loss in EVE. Engine returns the % of Tier 1 + outlier "
                f"classification.")

            irr_c1, irr_c2 = st.columns(2)
            with irr_c1:
                irr_period = st.text_input(
                    "Period", value=str(today)[:7],
                    key="rb_irr_period")
                irr_tier1 = st.number_input(
                    f"Tier 1 capital ({currency_symbol()} B)",
                    min_value=0.1, value=12.0, step=1.0,
                    key="rb_irr_tier1",
                    help="Tier 1 capital from the most recent CAR "
                         "computation.")
            with irr_c2:
                irr_delta = st.number_input(
                    f"Δ EVE worst-case ({currency_symbol()} B)",
                    min_value=0.0, value=1.5, step=0.1,
                    key="rb_irr_delta",
                    help="Absolute worst-case change in EVE under "
                         "±200bps parallel shock. From your ALM model.")
                irr_shock = st.selectbox(
                    "Shock scenario",
                    ["PARALLEL_PLUS_MINUS_200BPS",
                     "PARALLEL_PLUS_200BPS",
                     "PARALLEL_MINUS_200BPS",
                     "STEEPENER", "FLATTENER",
                     "SHORT_RATE_UP", "SHORT_RATE_DOWN"],
                    index=0, key="rb_irr_shock",
                    help="Standardised BCBS shock scenarios. Default "
                         "is the parallel ±200bps test required by "
                         f"{regulator()} PG/03.")

            if st.button("Generate IRR", key="rb_irr_btn", type="primary"):
                try:
                    components = IrrComponents(
                        period=irr_period,
                        delta_eve_kes=_D_rb(str(irr_delta))
                            * _D_rb("1000000000"),
                        tier1_capital_kes=_D_rb(str(irr_tier1))
                            * _D_rb("1000000000"),
                        shock_scenario=irr_shock,
                    )
                    pkg = _engine_rb.generate_irr(components)

                    m = pkg.computed_metrics
                    eve_share = m.get("delta_eve_share_of_tier1",
                                        _D_rb("0"))
                    eve_pct = m.get("delta_eve_pct_of_tier1",
                                      _D_rb("0"))

                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric(
                        "Δ EVE",
                        f"{currency_symbol()} {_D_rb(str(m['delta_eve_kes']))/_D_rb('1000000000'):.2f}B")
                    k2.metric(
                        "Tier 1",
                        f"{currency_symbol()} {_D_rb(str(m['tier1_capital_kes']))/_D_rb('1000000000'):.2f}B")
                    k3.metric(
                        "Δ EVE / Tier 1",
                        f"{eve_pct}%",
                        delta=f"vs {_engine_rb.IRRBB_DELTA_EVE_MAX_PCT_OF_TIER1 * 100:.0f}% outlier line")
                    with k4:
                        _render_severity_badge(
                            pkg.breach_severity.value,
                            "IRR STATUS")

                    st.info(pkg.breach_description)

                    if pkg.breach_severity == BreachSeverity.NONE:
                        st.success(
                            f"✅ Bank is INSIDE the BCBS outlier line "
                            f"({eve_pct}% < {_engine_rb.IRRBB_DELTA_EVE_MAX_PCT_OF_TIER1 * 100:.0f}%). "
                            f"No supervisory review required for this metric.")
                    else:
                        st.error(
                            f"⛔ Bank is an OUTLIER under BCBS SRP31 "
                            f"({eve_pct}% ≥ {_engine_rb.IRRBB_DELTA_EVE_MAX_PCT_OF_TIER1 * 100:.0f}%). "
                            f"Supervisory review + remediation plan required. "
                            f"Consider duration mismatch reduction, "
                            f"hedging, or balance-sheet restructuring.")

                    with st.expander("Framework refs + raw output"):
                        st.code("\n".join(pkg.framework_refs))
                        st.json({k: str(v) for k, v in m.items()})

                    audit_log("CBK_RETURN_GENERATED", uname,
                               f"IRR period={irr_period} eve_pct={eve_pct}% "
                               f"shock={irr_shock}")
                    _persist = _save_pkg(pkg, uname, DATA)
                    if _persist.get("persisted"):
                        st.caption(
                            f"💾 Persisted (id={_persist['data']['id']}, "
                            f"PG={'✅' if _persist.get('pg_persisted') else '—'})")
                    else:
                        st.caption(
                            f"⚠ Could not persist: "
                            f"{_persist.get('error', 'unknown error')}")
                except ValueError as e:
                    st.error(f"⛔ Validation: {e}")

        # ──────── OPR — Operational Risk Capital Charge ────────
        with rb_tabs[4]:
            st.markdown(
                f"**OPR — Operational Risk Capital Charge** "
                f"(Basel II Standardised Approach). Per "
                f"{regulator()} PG/03 §6 + BCBS Basel II §649, the "
                f"capital requirement is **α × 3-year average gross "
                f"income**, where α = {_engine_rb.OPR_ALPHA * 100:.0f}%. "
                f"The implied OPR-RWA is the capital charge × 12.5 "
                f"(inverse of 8% minimum capital ratio). Reasonableness "
                f"check: OPR-RWA share of total RWA ≤ "
                f"{_engine_rb.OPR_RWA_SHARE_MAX_PCT * 100:.0f}% — above "
                f"that flags an unusually high op-risk profile."
            )
            st.caption(
                f"Negative-income years are excluded from the average "
                f"per Basel II §651. Pass 0 for any year with negative "
                f"gross income; the engine handles the exclusion.")

            opr_period = st.text_input(
                "Period", value=str(today)[:7],
                key="rb_opr_period")

            opr_c1, opr_c2, opr_c3 = st.columns(3)
            with opr_c1:
                opr_y_minus2 = st.number_input(
                    f"Gross income Y-2 ({currency_symbol()} B)",
                    min_value=0.0, value=8.5, step=0.5,
                    key="rb_opr_ym2",
                    help="Gross income from 2 years ago. Pass 0 if "
                         "that year had negative income.")
            with opr_c2:
                opr_y_minus1 = st.number_input(
                    f"Gross income Y-1 ({currency_symbol()} B)",
                    min_value=0.0, value=9.2, step=0.5,
                    key="rb_opr_ym1",
                    help="Gross income from 1 year ago.")
            with opr_c3:
                opr_y_current = st.number_input(
                    f"Gross income current Y ({currency_symbol()} B)",
                    min_value=0.0, value=10.0, step=0.5,
                    key="rb_opr_yc",
                    help="Gross income for the current year (annualised).")

            opr_total_rwa = st.number_input(
                f"Total RWA ({currency_symbol()} B)",
                min_value=0.1, value=80.0, step=5.0,
                key="rb_opr_rwa",
                help="Total risk-weighted assets across credit, market, "
                     "and operational risk. From your CAR computation.")

            if st.button("Generate OPR", key="rb_opr_btn", type="primary"):
                try:
                    components = OperationalRiskComponents(
                        period=opr_period,
                        gross_income_year_minus_2_kes=_D_rb(str(opr_y_minus2))
                            * _D_rb("1000000000"),
                        gross_income_year_minus_1_kes=_D_rb(str(opr_y_minus1))
                            * _D_rb("1000000000"),
                        gross_income_current_year_kes=_D_rb(str(opr_y_current))
                            * _D_rb("1000000000"),
                        total_rwa_kes=_D_rb(str(opr_total_rwa))
                            * _D_rb("1000000000"),
                    )
                    pkg = _engine_rb.generate_opr(components)

                    m = pkg.computed_metrics
                    avg_gi = m.get("avg_gross_income_kes", _D_rb("0"))
                    cap_charge = m.get("capital_charge_kes", _D_rb("0"))
                    opr_rwa = m.get("implied_opr_rwa_kes", _D_rb("0"))
                    share_pct = m.get("opr_rwa_share_pct", _D_rb("0"))
                    pos_years = int(m.get("positive_years_count", 0))

                    k1, k2, k3, k4 = st.columns(4)
                    k1.metric(
                        "3-yr avg gross income",
                        f"{currency_symbol()} {_D_rb(str(avg_gi))/_D_rb('1000000000'):.2f}B",
                        delta=f"{pos_years} positive year(s)")
                    k2.metric(
                        "Capital charge",
                        f"{currency_symbol()} {_D_rb(str(cap_charge))/_D_rb('1000000000'):.3f}B",
                        delta=f"α={_engine_rb.OPR_ALPHA * 100:.0f}%")
                    k3.metric(
                        "OPR-RWA share",
                        f"{share_pct}%",
                        delta=f"vs {_engine_rb.OPR_RWA_SHARE_MAX_PCT * 100:.0f}% max")
                    with k4:
                        _render_severity_badge(
                            pkg.breach_severity.value,
                            "OPR STATUS")

                    st.info(pkg.breach_description)

                    # Component breakdown table
                    breakdown_rows = [
                        {"Metric": "Year-2 gross income",
                         "Value":
                             f"{currency_symbol()} {opr_y_minus2:.2f}B"},
                        {"Metric": "Year-1 gross income",
                         "Value":
                             f"{currency_symbol()} {opr_y_minus1:.2f}B"},
                        {"Metric": "Current Y gross income",
                         "Value":
                             f"{currency_symbol()} {opr_y_current:.2f}B"},
                        {"Metric": "Positive years included",
                         "Value": f"{pos_years} of 3"},
                        {"Metric":
                             f"3-yr avg gross income (positive years)",
                         "Value":
                             f"{currency_symbol()} {_D_rb(str(avg_gi))/_D_rb('1000000000'):.3f}B"},
                        {"Metric":
                             f"Capital charge (α × avg = "
                             f"{_engine_rb.OPR_ALPHA * 100:.0f}% × avg)",
                         "Value":
                             f"{currency_symbol()} {_D_rb(str(cap_charge))/_D_rb('1000000000'):.3f}B"},
                        {"Metric":
                             "Implied OPR-RWA (capital × 12.5)",
                         "Value":
                             f"{currency_symbol()} {_D_rb(str(opr_rwa))/_D_rb('1000000000'):.3f}B"},
                        {"Metric": "Total RWA",
                         "Value":
                             f"{currency_symbol()} {opr_total_rwa:.2f}B"},
                        {"Metric": "OPR-RWA share of total RWA",
                         "Value": f"{share_pct}%"},
                    ]
                    st.dataframe(pd.DataFrame(breakdown_rows),
                                 use_container_width=True,
                                 hide_index=True)

                    if pkg.breach_severity == BreachSeverity.NONE:
                        st.success(
                            f"✅ OPR-RWA share ({share_pct}%) is within "
                            f"the {_engine_rb.OPR_RWA_SHARE_MAX_PCT * 100:.0f}% "
                            f"reasonableness threshold. Capital charge "
                            f"of {currency_symbol()} {_D_rb(str(cap_charge))/_D_rb('1000000000'):.3f}B "
                            f"appears proportionate to gross income.")
                    else:
                        st.warning(
                            f"⚠ OPR-RWA share ({share_pct}%) is "
                            f"unusually high vs the "
                            f"{_engine_rb.OPR_RWA_SHARE_MAX_PCT * 100:.0f}% reasonableness "
                            f"threshold. Review whether: (a) gross "
                            f"income is unusually high (recent M&A?), "
                            f"(b) total RWA is unusually low (capital "
                            f"adequacy concern?), or (c) op-risk "
                            f"profile genuinely warrants a higher "
                            f"capital charge. Consider Advanced "
                            f"Measurement Approach (AMA) or TSA.")

                    with st.expander("Framework refs + raw output"):
                        st.code("\n".join(pkg.framework_refs))
                        st.json({k: str(v) for k, v in m.items()})

                    audit_log("CBK_RETURN_GENERATED", uname,
                               f"OPR period={opr_period} "
                               f"share%={share_pct}% "
                               f"capital_charge={cap_charge}")
                    _persist = _save_pkg(pkg, uname, DATA)
                    if _persist.get("persisted"):
                        st.caption(
                            f"💾 Persisted (id={_persist['data']['id']}, "
                            f"PG={'✅' if _persist.get('pg_persisted') else '—'})")
                    else:
                        st.caption(
                            f"⚠ Could not persist: "
                            f"{_persist.get('error', 'unknown error')}")
                except ValueError as e:
                    st.error(f"⛔ Validation: {e}")

with tabs[3]:
    with_findings = [r for r in records if r.get("regulatory_findings",0)>0]
    if with_findings:
        st.markdown(f"**Returns with regulatory findings ({len(with_findings)}):**")
        for r in with_findings[:20]:
            ratio = f"{r.get('findings_closed',0)}/{r.get('regulatory_findings',0)}"
            with st.expander(f"📌 {r.get('return_code','')} — {r.get('return_name','')[:30]} | Findings: {ratio}"):
                if r.get("findings_closed",0) < r.get("regulatory_findings",0):
                    if st.button("Close finding",key=f"cbk_fc_{r['id']}"):
                        all_r = _load()
                        for rec in all_r:
                            if rec["id"]==r["id"]:
                                rec["findings_closed"] = min(rec.get("findings_closed",0)+1,rec.get("regulatory_findings",0))
                                break
                        _save(all_r); audit_log("CBK_FINDING_CLOSED",uname,r.get("return_code",""))
                        _bsc_trigger(uname,"K074")
                        st.success("✅ Finding closed"); st.rerun()
    else:
        st.success("✅ No outstanding regulatory findings.")

with tabs[4]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**By department:**")
        by_dept = defaultdict(lambda:{"total":0,"on_time":0})
        for r in submitted_r:
            d = r.get("department","Other")
            by_dept[d]["total"] += 1
            if r.get("on_time"): by_dept[d]["on_time"] += 1
        rows = [{"Department":d,"Submitted":v["total"],"On Time":v["on_time"],
                  "Rate":f"{v['on_time']/max(v['total'],1)*100:.0f}%"}
                for d,v in sorted(by_dept.items())]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
    with c2:
        st.markdown("**By frequency:**")
        by_freq = defaultdict(lambda:{"total":0,"on_time":0})
        for r in submitted_r:
            f = r.get("frequency","Other")
            by_freq[f]["total"] += 1
            if r.get("on_time"): by_freq[f]["on_time"] += 1
        rows = [{"Frequency":f,"Submitted":v["total"],"On Time":v["on_time"],
                  "Rate":f"{v['on_time']/max(v['total'],1)*100:.0f}%"}
                for f,v in by_freq.items()]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[5]:
    if is_admin:
        st.info("ℹ️ Hardcoded: 47 CBK returns, frequencies, late filing penalty KES 50K, regulator details")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("cbk_returns",{}).get("configurable",{})
        c1,c2,c3 = st.columns(3)
        new_warn = c1.number_input("Early warning days",1,30,int(cfg_m.get("early_warning_days",7)),key="cbk_cfg_warn")
        new_acc  = c2.number_input("Min accuracy (%)",50,100,int(cfg_m.get("minimum_accuracy_pct",95)),key="cbk_cfg_acc")
        new_email= c3.text_input("Escalation email",cfg_m.get("escalation_email",""),key="cbk_cfg_email")
        if st.button("💾 Save config",key="cbk_cfg_save",type="primary"):
            cfg_m.update({"early_warning_days":new_warn,"minimum_accuracy_pct":new_acc,"escalation_email":new_email})
            mc["cbk_returns"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("CBK_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Admin only.")

with tabs[6]:
    bsc_rows=[
        {"KPI":"K072 — On-time filing","Target":"> 95%","Actual":f"{on_time_pct}%","Status":"🟢" if on_time_pct>=95 else "🔴","Weight":"10%"},
        {"KPI":"K073 — Accuracy","Target":f"> {min_acc}%","Actual":f"{acc_avg}%","Status":"🟢" if acc_avg>=min_acc else "🟡","Weight":"8%"},
        {"KPI":"K074 — Findings closed","Target":"> 90%","Actual":f"{findings_pct}%","Status":"🟢" if findings_pct>=90 else "🟡","Weight":"5%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="cbk_bsc",type="primary"):
        _bsc_trigger(uname,"K072"); st.success("✅ BSC updated"); st.rerun()
