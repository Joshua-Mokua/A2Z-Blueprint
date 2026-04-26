"""pages/20_debt_recovery.py — Debt Recovery System."""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()



require_access("debt_recovery")

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass


um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

DATA  = Path(__file__).parent.parent / "data"
_bank = st.session_state.get("_bank_display", "A2Z Blueprint")
_curr = st.session_state.get("_currency", "KES")

is_admin       = ud.get("is_admin", False)
my_role        = ud.get("role", "")
my_name        = ud.get("full_name", uname)
is_recovery_mgr= any(x in my_role.lower() for x in ["recovery","collection","senior manager","manager","director","md","chief"])

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>💰 Debt Recovery</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "DRS · Collections · Legal escalation</span></div>",
    unsafe_allow_html=True)


st.markdown(
    f"<div style='padding:14px 20px;background:#A32D2D;"
    f"border-radius:10px;margin-bottom:16px'>"
    f"<div style='color:white;font-size:15px;font-weight:600'>Debt Recovery System</div>"
    f"<div style='color:rgba(255,255,255,0.65);font-size:11px'>"
    f"Recovery pipeline · Promise-to-pay · Agent performance · BSC auto-feed</div></div>",
    unsafe_allow_html=True)

# ── Load data ──────────────────────────────────────────────────────────
@st.cache_data(ttl=60)
def load_drs():
    p = DATA / "debt_recovery.json"
    if not p.exists():
        return []
    raw = a2z_db.load_json(p)
    # Handle both plain list and {"cases": [...]} dict formats
    if isinstance(raw, list):
        return raw
    return raw.get("cases", [])

def save_drs(data):
    # Always save as plain list
    if isinstance(data, dict):
        data = data.get("cases", [])
    (DATA / "debt_recovery.json").write_text(json.dumps(data, indent=2))
    load_drs.clear()

cases = load_drs()

if not cases:
    st.info("No recovery cases. Generate CBS data first.")
    st.stop()

RECOVERY_STAGES = [
    "Demand Letter 1","Demand Letter 2","Final Demand",
    "Legal - Filed","Legal - Judgment","Attachment",
    "Settlement Negotiation","Restructured","Written Off","Recovered"
]
STRATEGIES = ["Voluntary Payment","Restructuring","Legal Action",
              "Asset Sale","Guarantor Call","Settlement Discount"]

# ── Tabs ───────────────────────────────────────────────────────────────
drs_tabs = st.tabs([
    "📊 Dashboard",
    "📋 Case pipeline",
    "🤝 Promise-to-pay",
    "👤 Agent tracker",
    "📈 BSC auto-feed",
    "📅 Monthly Report",
])

# ════════════════════════════════════════════════════════════════
# TAB 0: DASHBOARD
# ════════════════════════════════════════════════════════════════
with drs_tabs[0]:
    df = pd.DataFrame(cases)
    # Alias for convenience
    df["stage"]         = df["recovery_stage"]
    df["strategy"]      = df["recovery_stage"].apply(
        lambda s: ("Legal" if "Legal" in str(s)
                   else "Negotiation" if "Settlement" in str(s) or "Negotiation" in str(s)
                   else "Collection"))
    df["recovery_rate"] = df["amount_recovered"] / df["outstanding"].replace(0, 1) * 100
    df["agent_name"]    = df["recovery_officer"]
    df["region"]        = df["branch"].apply(lambda b: "Nairobi" if b else "Other")

    active_df  = df[df["status"]=="Active"]
    closed_df  = df[df["status"]=="Closed"]
    total_out  = df["outstanding"].sum()
    total_coll = df["amount_recovered"].sum()
    recovery_rate = total_coll / total_out * 100 if total_out else 0
    active_cases  = len(active_df)
    recovered_cases = len(df[df["stage"]=="Recovered"])

    # Today's actions
    today_str = str(date.today())
    due_today = df[df["next_action"]==today_str]
    overdue   = df[(df["next_action"] < today_str) & (df["status"]=="Active")]

    # Metrics
    m1,m2,m3,m4,m5,m6 = st.columns(6)
    m1.metric("Active cases",       f"{active_cases:,}")
    m2.metric("Total outstanding",  f"{_curr} {total_out/1e9:.2f}B")
    m3.metric("Total collected",    f"{_curr} {total_coll/1e9:.2f}B")
    m4.metric("Recovery rate",      f"{recovery_rate:.1f}%",
              delta=f"{recovery_rate-33:.1f}% vs 33% base")
    m5.metric("Actions due today",  f"{len(due_today):,}")
    m6.metric("Overdue actions",    f"{len(overdue):,}",
              delta=f"-{len(overdue)}" if len(overdue) else None, delta_color="inverse")

    st.markdown("---")
    dc1, dc2 = st.columns(2)

    # Stage funnel
    with dc1:
        st.markdown("#### Recovery pipeline")
        stage_df = df[df["status"]=="Active"].groupby("stage").agg(
            Cases=("id","count"),
            Outstanding=("outstanding","sum"),
            Collected=("amount_recovered","sum"),
        ).reset_index()

        # Order by stage
        stage_order = {s:i for i,s in enumerate(RECOVERY_STAGES)}
        stage_df["order"] = stage_df["stage"].map(stage_order)
        stage_df = stage_df.sort_values("order")

        def stage_clr(v):
            if "Legal" in str(v) or "Attachment" in str(v): return "color:#A32D2D;font-weight:500"
            if "Demand" in str(v): return "color:#BA7517"
            if "Settlement" in str(v) or "Restructure" in str(v): return "color:#185FA5"
            if "Recovered" in str(v): return "color:#3B6D11;font-weight:500"
            return ""

        stage_df["Outstanding"] = stage_df["Outstanding"].apply(lambda x: f"{x/1e6:.1f}M")
        stage_df["Collected"]   = stage_df["Collected"].apply(lambda x: f"{x/1e6:.1f}M")
        stage_df = stage_df.drop(columns="order")
        st.dataframe(
            stage_df.style.map(stage_clr, subset=["stage"]),
            hide_index=True, use_container_width=True)

    # Strategy breakdown
    with dc2:
        st.markdown("#### By strategy")
        strat_df = df.groupby("strategy").agg(
            Cases=("id","count"),
            Outstanding=("outstanding","sum"),
            Rate=("recovery_rate","mean"),
        ).reset_index()
        strat_df["Outstanding"] = strat_df["Outstanding"].apply(lambda x: f"{x/1e6:.1f}M")
        strat_df["Rate"] = strat_df["Rate"].apply(lambda x: f"{x:.1f}%")
        strat_df = strat_df.sort_values("Cases", ascending=False)
        st.dataframe(strat_df, hide_index=True, use_container_width=True)

    # Overdue actions alert
    if len(overdue) > 0:
        st.markdown("---")
        st.error(f"🚨 {len(overdue)} cases have overdue actions")
        ov_show = overdue[["id","account_number","outstanding","stage",
                            "agent_name","next_action"]].head(10).copy()
        ov_show["outstanding"] = ov_show["outstanding"].apply(lambda x: f"{x/1e6:.1f}M")
        ov_show = ov_show.rename(columns={"next_action":"Action Was Due"})
        st.dataframe(ov_show, hide_index=True, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 1: CASE PIPELINE
# ════════════════════════════════════════════════════════════════
with drs_tabs[1]:
    df = pd.DataFrame(cases)
    df["stage"]         = df["recovery_stage"]
    df["strategy"]      = df["recovery_stage"].apply(
        lambda s: ("Legal" if "Legal" in str(s)
                   else "Negotiation" if "Settlement" in str(s) or "Negotiation" in str(s)
                   else "Collection"))
    df["recovery_rate"] = df["amount_recovered"] / df["outstanding"].replace(0, 1) * 100
    df["agent_name"]    = df["recovery_officer"]
    df["region"]        = df["branch"].apply(lambda b: "Nairobi" if b else "Other")

    # Filters
    fc1,fc2,fc3 = st.columns(3)
    stage_filt  = fc1.selectbox("Stage", ["All"]+RECOVERY_STAGES, key="drs_stage")
    agent_filt  = fc2.selectbox("Agent",
        ["All","Mine"]+sorted(df["agent_name"].dropna().unique().tolist()),
        key="drs_agent")
    status_filt = fc3.selectbox("Status", ["All","Active","Closed"], key="drs_status")

    mask = pd.Series([True]*len(df))
    if stage_filt  != "All": mask &= df["stage"]==stage_filt
    if agent_filt  == "Mine": mask &= df["agent_name"]==my_name
    elif agent_filt!= "All": mask &= df["agent_name"]==agent_filt
    if status_filt != "All": mask &= df["status"]==status_filt

    fdf = df[mask].copy()
    st.caption(f"{len(fdf):,} cases · Outstanding: {_curr} {fdf['outstanding'].sum()/1e9:.2f}B")

    show = fdf[["id","account_number","branch","outstanding","amount_recovered",
                "recovery_rate","stage","strategy","agent_name","next_action","status"]].copy()
    show["outstanding"]     = show["outstanding"].apply(lambda x: f"{x/1e6:.1f}M")
    show["amount_recovered"]= show["amount_recovered"].apply(lambda x: f"{x/1e6:.1f}M")
    show["recovery_rate"]   = show["recovery_rate"].apply(lambda x: f"{x:.1f}%")

    def rate_clr(v):
        try:
            n = float(str(v).replace("%",""))
            if n >= 60: return "color:#3B6D11;font-weight:500"
            if n >= 30: return "color:#BA7517"
            return "color:#A32D2D"
        except: return ""

    st.dataframe(
        show.style.map(rate_clr, subset=["recovery_rate"]),
        hide_index=True, use_container_width=True, height=380)

    # ── Case detail + update ───────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Update case")
    case_opts = ["— Select case —"] + fdf["id"].tolist()[:100]
    sel_case  = st.selectbox("Case", case_opts, key="drs_case_sel")

    if sel_case != "— Select case —":
        rec = next((c for c in cases if c["id"]==sel_case), None)
        if rec:
            ci1,ci2,ci3 = st.columns(3)
            ci1.markdown(f"**Account:** {rec['account_number']}")
            ci1.markdown(f"**Branch:** {rec['branch']}")
            ci1.markdown(f"**Region:** {rec['region']}")
            ci2.markdown(f"**Outstanding:** {_curr} {rec['outstanding']/1e6:.2f}M")
            ci2.markdown(f"**Collected:** {_curr} {rec['amount_recovered']/1e6:.2f}M")
            ci2.markdown(f"**Rate:** {rec['recovery_rate']:.1f}%")
            ci3.markdown(f"**Stage:** {rec['stage']}")
            ci3.markdown(f"**Agent:** {rec['agent_name']}")
            ci3.markdown(f"**Days in recovery:** {rec['dpd']}")

            if rec.get("legal_firm"):
                st.caption(f"Legal ref: {rec['legal_firm']}")

            # ── Demand Letter generator ──────────────────────────
            _dl1, _dl2 = st.columns(2)
            if _dl1.button("📄 Generate Demand Letter", key=f"dl_{sel_case}",
                           help="Generate a formal demand letter for this account"):
                _today_dl = date.today()
                _deadline = _today_dl + timedelta(days=14)
                _dl_html = f"""<!DOCTYPE html>
<html><head><style>
body{{font-family:Arial,sans-serif;font-size:12px;margin:40px;color:#333}}
.header{{text-align:center;border-bottom:2px solid #004d2e;padding-bottom:16px;margin-bottom:24px}}
.bank{{font-size:20px;font-weight:700;color:#004d2e}}
.ref{{float:right;font-size:11px;color:#666}}
p{{margin:8px 0;line-height:1.6}}
.amount{{font-size:14px;font-weight:700;color:#A32D2D}}
.footer{{margin-top:40px;font-size:10px;color:#666;border-top:1px solid #ccc;padding-top:8px}}
</style></head><body>
<div class="header">
  <div class="bank">A2Z BLUEPRINT BANK</div>
  <div style="font-size:11px;color:#666">Head Office, Nairobi · Tel: +254 20 000 0000</div>
</div>
<p class="ref">Ref: {rec['id']}/{_today_dl.strftime('%Y%m%d')}</p>
<p><b>Date:</b> {_today_dl.strftime('%d %B %Y')}</p>
<p><b>The Borrower/Guarantor</b><br>
Account: <b>{rec['account_number']}</b><br>
Branch: {rec['branch']}</p>
<br>
<p><b>FORMAL DEMAND FOR REPAYMENT OF OUTSTANDING LOAN FACILITY</b></p>
<p>Dear Sir/Madam,</p>
<p>We refer to the above-mentioned loan facility and wish to bring to your attention that
your account is <b>{rec['npl_days']} days in arrears</b>.</p>
<p>As at {_today_dl.strftime('%d %B %Y')}, the total outstanding amount is:</p>
<p class="amount">KES {rec['outstanding']:,.2f}</p>
<p>You are hereby formally demanded to settle the full outstanding amount 
<b>within 14 days</b> of this notice, i.e., by <b>{_deadline.strftime('%d %B %Y')}</b>.</p>
<p>Failure to settle this amount by the stipulated date will compel the Bank to
institute legal proceedings to recover the outstanding debt, including all
associated costs, without further notice to you.</p>
<p>Please contact your relationship manager on <b>+254 20 000 0000</b> to discuss
repayment arrangements.</p>
<br>
<p>Yours faithfully,</p>
<p><b>Head, Credit Recovery</b><br>A2Z Blueprint Bank</p>
<div class="footer">This is a system-generated demand letter · A2Z Blueprint v2.0</div>
</body></html>"""
                st.download_button(
                    "📥 Download Demand Letter",
                    data=_dl_html.encode(),
                    file_name=f"DemandLetter_{rec['account_number']}_{_today_dl}.html",
                    mime="text/html",
                    key=f"dl_download_{sel_case}")
                audit_log("DEMAND_LETTER_GENERATED", uname,
                          f"{sel_case}|{rec['account_number']}|KES{rec['outstanding']:,.0f}",
                          module="debt_recovery")

            # ── Settlement offer ──────────────────────────────────
            if _dl2.button("🤝 Record Settlement Offer", key=f"sett_{sel_case}"):
                st.session_state[f"show_settlement_{sel_case}"] = True

            if st.session_state.get(f"show_settlement_{sel_case}"):
                with st.form(f"settlement_{sel_case}"):
                    _sf1, _sf2, _sf3 = st.columns(3)
                    _sett_amt = _sf1.number_input(
                        "Settlement amount (KES)", min_value=0.0,
                        value=float(rec['outstanding']) * 0.7, step=50_000.0)
                    _sett_disc = _sf2.number_input(
                        "Discount granted (%)", min_value=0.0, max_value=100.0,
                        value=round((1 - _sett_amt/max(rec['outstanding'],1))*100, 1))
                    _sett_valid = _sf3.date_input(
                        "Offer valid until", value=date.today() + timedelta(days=30))
                    _sett_approver = st.selectbox("Approved by",
                        ["Branch Manager","Regional Head","Chief Credit Officer","MD"])
                    _sett_note = st.text_area("Settlement terms / conditions", height=60)
                    if st.form_submit_button("💾 Save settlement offer", type="primary"):
                        for c in cases:
                            if c["id"] == sel_case:
                                c.setdefault("settlement_offers", []).append({
                                    "amount":    _sett_amt,
                                    "discount":  _sett_disc,
                                    "valid_until": str(_sett_valid),
                                    "approver":  _sett_approver,
                                    "note":      _sett_note,
                                    "date":      str(date.today()),
                                    "status":    "Pending",
                                })
                                c["stage"] = "Settlement Negotiation"
                        save_drs(drs_data)
                        audit_log("SETTLEMENT_OFFER_RECORDED", uname,
                                  f"{sel_case}|KES{_sett_amt:,.0f}|disc{_sett_disc:.1f}%",
                                  module="debt_recovery")
                        st.session_state.pop(f"show_settlement_{sel_case}", None)
                        st.cache_data.clear()
                        st.success(f"✅ Settlement offer saved for {sel_case}")
                        st.rerun()

            with st.form(f"drs_upd_{sel_case}"):
                uf1,uf2,uf3 = st.columns(3)
                new_stage  = uf1.selectbox("Update stage", RECOVERY_STAGES,
                    index=RECOVERY_STAGES.index(rec["stage"]) if rec["stage"] in RECOVERY_STAGES else 0)
                new_strategy= uf2.selectbox("Strategy", STRATEGIES,
                    index=STRATEGIES.index(rec["strategy"]) if rec["strategy"] in STRATEGIES else 0)
                new_next   = uf3.date_input("Next action date",
                    value=_safe_date(rec["next_action"])
                    if rec.get("next_action") else date.today()+timedelta(days=7))
                new_coll   = st.number_input("Additional amount collected (KES)",
                    min_value=0.0, step=100000.0, value=0.0)
                new_note   = st.text_area("Action note", height=70,
                    value=rec.get("notes",""))

                if st.form_submit_button("💾 Update case", type="primary"):
                    for c in cases:
                        if c["id"] == sel_case:
                            prev_stage = c["stage"]
                            c["stage"]          = new_stage
                            c["strategy"]       = new_strategy
                            c["next_action"]= str(new_next)
                            c["last_updated"]= str(date.today())
                            c["amount_recovered"]+= new_coll
                            c["recovery_rate"]  = (c["amount_recovered"] /
                                                   c["outstanding"] * 100
                                                   if c["outstanding"] else 0)
                            c["notes"]          = new_note
                            if new_stage == "Recovered":
                                c["status"] = "Closed"
                    save_drs(drs_data)
                    audit_log("RECOVERY_CASE_UPDATED", uname,
                              f"{sel_case}:{prev_stage}→{new_stage}", module="debt_recovery")
                    st.success(f"✅ Case {sel_case} updated.")
                    st.cache_data.clear()
                    st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 2: PROMISE-TO-PAY
# ════════════════════════════════════════════════════════════════
with drs_tabs[2]:
    # Flatten all PTPs
    ptp_rows = []
    for c in cases:
        for p in c.get("promise_to_pay", []):
            ptp_rows.append({
                "Case ID":     c["id"],
                "Account":     c["account_number"],
                "Agent":       c["agent_name"],
                "PTP Date":    p["date"],
                "PTP Amount":  p["amount"],
                "Kept":        "✅ Yes" if p["kept"] else "❌ No",
                "Paid":        p.get("actual_paid", 0),
                "Outstanding": c["outstanding"],
            })

    ptp_df = pd.DataFrame(ptp_rows) if ptp_rows else pd.DataFrame()

    if ptp_df.empty:
        st.info("No promise-to-pay records yet.")
    else:
        total_ptp     = len(ptp_df)
        kept_ptp      = len(ptp_df[ptp_df["Kept"]=="✅ Yes"])
        keep_rate     = kept_ptp / total_ptp * 100 if total_ptp else 0
        total_promised= ptp_df["PTP Amount"].sum()
        total_paid    = ptp_df["Paid"].sum()

        pm1,pm2,pm3,pm4 = st.columns(4)
        pm1.metric("Total PTPs",     f"{total_ptp:,}")
        pm2.metric("Kept",           f"{kept_ptp:,}")
        pm3.metric("Keep rate",      f"{keep_rate:.1f}%")
        pm4.metric("Amount promised",f"{_curr} {total_promised/1e6:.1f}M")

        st.markdown("---")

        # Filter
        pf1,pf2 = st.columns(2)
        kept_filt = pf1.radio("Filter", ["All","Kept","Broken"], horizontal=True, key="ptp_filt")
        agent_ptp = pf2.selectbox("Agent", ["All"]+sorted(ptp_df["Agent"].unique().tolist()),
                                   key="ptp_agent")

        pmask = pd.Series([True]*len(ptp_df))
        if kept_filt == "Kept":   pmask &= ptp_df["Kept"]=="✅ Yes"
        if kept_filt == "Broken": pmask &= ptp_df["Kept"]=="❌ No"
        if agent_ptp != "All":    pmask &= ptp_df["Agent"]==agent_ptp

        disp_ptp = ptp_df[pmask].copy()
        disp_ptp["PTP Amount"] = disp_ptp["PTP Amount"].apply(lambda x: f"{x/1e6:.2f}M")
        disp_ptp["Paid"]       = disp_ptp["Paid"].apply(lambda x: f"{x/1e6:.2f}M")

        def kept_clr(v):
            if "Yes" in str(v): return "color:#3B6D11;font-weight:500"
            return "color:#A32D2D"

        st.dataframe(
            disp_ptp.style.map(kept_clr, subset=["Kept"]),
            hide_index=True, use_container_width=True, height=360)

        # Add new PTP
        st.markdown("---")
        st.markdown("#### Record new promise-to-pay")
        with st.form("new_ptp"):
            np1,np2,np3 = st.columns(3)
            ptp_case   = np1.selectbox("Case",
                [c["id"] for c in cases if c["status"]=="Active"][:100],
                key="ptp_case_sel")
            ptp_amount = np2.number_input("Amount promised (KES)",
                min_value=0.0, step=50000.0)
            ptp_date   = np3.date_input("Commitment date",
                value=date.today()+timedelta(days=7))
            if st.form_submit_button("➕ Record PTP", type="primary"):
                for c in cases:
                    if c["id"] == ptp_case:
                        c.setdefault("promise_to_pay",[]).append({
                            "date": str(ptp_date),
                            "amount": ptp_amount,
                            "kept": False,
                            "actual_paid": 0,
                        })
                save_drs(drs_data)
                audit_log("PTP_RECORDED", uname,
                          f"{ptp_case}:KES{ptp_amount:,.0f}", module="debt_recovery")
                st.success(f"PTP recorded for {ptp_case}.")
                st.cache_data.clear()
                st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 3: AGENT TRACKER
# ════════════════════════════════════════════════════════════════
with drs_tabs[3]:
    df = pd.DataFrame(cases)
    df["stage"]         = df["recovery_stage"]
    df["strategy"]      = df["recovery_stage"].apply(
        lambda s: ("Legal" if "Legal" in str(s)
                   else "Negotiation" if "Settlement" in str(s) or "Negotiation" in str(s)
                   else "Collection"))
    df["recovery_rate"] = df["amount_recovered"] / df["outstanding"].replace(0, 1) * 100
    df["agent_name"]    = df["recovery_officer"]
    df["region"]        = df["branch"].apply(lambda b: "Nairobi" if b else "Other")

    agent_perf = df.groupby("agent_name").agg(
        Cases=("id","count"),
        Active=("status", lambda x: (x=="Active").sum()),
        Outstanding=("outstanding","sum"),
        Collected=("amount_recovered","sum"),
        Avg_Rate=("recovery_rate","mean"),
        Overdue=("next_action",
                 lambda x: (x < str(date.today())).sum()),
    ).reset_index()
    agent_perf["Avg Rate"] = agent_perf["Avg_Rate"].apply(lambda x: f"{x:.1f}%")
    agent_perf["Outstanding"]= agent_perf["Outstanding"].apply(lambda x: f"{x/1e6:.1f}M")
    agent_perf["Collected"]  = agent_perf["Collected"].apply(lambda x: f"{x/1e6:.1f}M")
    agent_perf = agent_perf.drop(columns="Avg_Rate")
    agent_perf = agent_perf.sort_values("Collected", ascending=False)

    # Summary
    best_agent = agent_perf.iloc[0]["agent_name"] if len(agent_perf) else "—"
    st.info(f"👑 Top agent this period: **{best_agent}**")

    def agent_rate_clr(v):
        try:
            n = float(str(v).replace("%",""))
            if n >= 50: return "color:#3B6D11;font-weight:500"
            if n >= 30: return "color:#BA7517"
            return "color:#A32D2D"
        except: return ""

    def overdue_clr(v):
        try:
            if int(v) > 5: return "color:#A32D2D;font-weight:500"
            if int(v) > 0: return "color:#BA7517"
        except: pass
        return "color:#3B6D11"

    st.dataframe(
        agent_perf.style
            .map(agent_rate_clr, subset=["Avg Rate"])
            .map(overdue_clr,    subset=["Overdue"]),
        hide_index=True, use_container_width=True, height=400)

    st.download_button("📥 Export agent report",
        data=agent_perf.to_csv(index=False).encode(),
        file_name="agent_performance.csv", mime="text/csv",
        key="agent_export")

# ════════════════════════════════════════════════════════════════
# TAB 4: BSC AUTO-FEED
# ════════════════════════════════════════════════════════════════
with drs_tabs[4]:
    st.caption(
        "Recovery data automatically updates the Collection Throughput KPI "
        "on each agent's and manager's BSC scorecard — no manual entry.")

    df = pd.DataFrame(cases)
    df["stage"]         = df["recovery_stage"]
    df["strategy"]      = df["recovery_stage"].apply(
        lambda s: ("Legal" if "Legal" in str(s)
                   else "Negotiation" if "Settlement" in str(s) or "Negotiation" in str(s)
                   else "Collection"))
    df["recovery_rate"] = df["amount_recovered"] / df["outstanding"].replace(0, 1) * 100
    df["agent_name"]    = df["recovery_officer"]
    df["region"]        = df["branch"].apply(lambda b: "Nairobi" if b else "Other")

    # Compute collection throughput per agent
    agent_kpis = df.groupby("agent_name").agg(
        Outstanding=("outstanding","sum"),
        Collected=("amount_recovered","sum"),
        Rate=("recovery_rate","mean"),
    ).reset_index()
    agent_kpis["COLLECTION_THROUGHPUT"] = agent_kpis["Rate"].round(1)
    agent_kpis["BSC_Score"] = agent_kpis["COLLECTION_THROUGHPUT"].apply(
        lambda r: 5.0 if r>130 else 4.5 if r>120 else 4.0 if r>110 else
                  3.5 if r>100 else 3.0 if r>=91 else 2.5 if r>=61 else
                  2.0 if r>=51 else 1.5 if r>=31 else 1.0)

    st.markdown("#### Collection throughput → BSC score mapping")
    bsc1,bsc2 = st.columns(2)
    with bsc1:
        disp = agent_kpis[["agent_name","Collected","COLLECTION_THROUGHPUT","BSC_Score"]].copy()
        disp["Collected"] = disp["Collected"].apply(lambda x: f"{x/1e6:.1f}M")
        disp["COLLECTION_THROUGHPUT"] = disp["COLLECTION_THROUGHPUT"].apply(lambda x: f"{x:.1f}%")

        def bsc_clr(v):
            try:
                n = float(v)
                if n >= 4.0: return "color:#3B6D11;font-weight:500"
                if n >= 3.0: return "color:#BA7517"
                return "color:#A32D2D"
            except: return ""

        st.dataframe(
            disp.style.map(bsc_clr, subset=["BSC_Score"]),
            hide_index=True, use_container_width=True, height=300)

    with bsc2:
        # Bank-level NPL KPI
        total_out_all   = df["outstanding"].sum()
        total_coll_all  = df["amount_recovered"].sum()
        npl_rate_act    = df[df["stage"]=="Stage 3"]["outstanding"].sum()
        bank_rate        = total_coll_all / total_out_all * 100 if total_out_all else 0

        st.markdown("**Bank-level KPI actuals (auto-computed)**")
        kpi_rows = [
            {"KPI":"Collection Throughput","Actual":f"{bank_rate:.1f}%","Target":"35%",
             "Status":"✅ Met" if bank_rate>=35 else "❌ Below"},
            {"KPI":"NPL Ratio","Actual":f"{npl_rate_act/1e9:.2f}B",
             "Target":"< 9% portfolio","Status":"⚠️ Monitor"},
            {"KPI":"Recovery Rate","Actual":f"{bank_rate:.1f}%","Target":"33%",
             "Status":"✅ Met" if bank_rate>=33 else "❌ Below"},
        ]
        st.dataframe(pd.DataFrame(kpi_rows), hide_index=True, use_container_width=True)

    st.markdown("---")
    if st.button("🔄 Push actuals to BSC now", type="primary", key="drs_push_bsc"):
        # Write a recovery_actuals.json that the actuals engine picks up
        recovery_actuals = {}
        for _, row in agent_kpis.iterrows():
            recovery_actuals[row["agent_name"]] = {
                "COLLECTION_THROUGHPUT": float(row["COLLECTION_THROUGHPUT"]),
                "updated_at": str(date.today()),
            }
        (DATA/"recovery_actuals.json").write_text(json.dumps(recovery_actuals, indent=2))
        audit_log("DRS_BSC_PUSH", uname,
                  f"{len(recovery_actuals)} agents updated", module="debt_recovery")
        st.success(f"✅ Collection Throughput actuals pushed for {len(recovery_actuals)} agents. "
                   f"Scores will update on next BSC refresh.")
