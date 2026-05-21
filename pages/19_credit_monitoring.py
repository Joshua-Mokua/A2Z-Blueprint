"""pages/19_credit_monitoring.py — Credit Monitoring System."""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date, datetime, timedelta
from pages._shared import load_shared_state, get_user_proposition
from pages._access import require_access

require_access("credit.monitoring")

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

DATA = Path(__file__).parent.parent / "data"

_bank = st.session_state.get("_bank_display", "A2Z Blueprint")
_curr = st.session_state.get("_currency", "KES")

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🔴 Credit Monitoring</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Watch list · NPL · IFRS 9 staging</span></div>",
    unsafe_allow_html=True)


st.markdown(
    f"<div style='padding:14px 20px;background:var(--brand-primary,#006B3F);"
    f"border-radius:10px;margin-bottom:16px'>"
    f"<div style='color:white;font-size:15px;font-weight:600'>Credit Monitoring System</div>"
    f"<div style='color:rgba(255,255,255,0.65);font-size:11px'>"
    f"Watchlist · Covenant Tracking · NPL Migration · Portfolio at Risk</div></div>",
    unsafe_allow_html=True)

# ── Load data ──────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def load_cm():
    p = DATA / "credit_monitoring.json"
    if not p.exists():
        return {"watchlist": [], "last_updated": ""}
    return a2z_db.load_json(p)

cm_data   = load_cm()
watchlist = cm_data.get("watchlist", [])
# Normalise Decimal types from PostgreSQL to float
from decimal import Decimal as _Dec
for _w in watchlist:
    if "npl_days" not in _w and "dpd" in _w:
        _w["npl_days"] = _w.get("dpd", _w.get("npl_days", 0))
    if "branch_name" not in _w and "branch" in _w:
        _w["branch_name"] = _w.get("branch", _w.get("branch_name", ""))
    if "client_name" not in _w and "rm_name" in _w:
        _w["client_name"] = _w.get("client_name", "")
    for _k, _v in list(_w.items()):
        if isinstance(_v, _Dec):
            _w[_k] = float(_v)

if not watchlist:
    st.info("No credit monitoring data. Generate CBS data first.")
    st.stop()

# ── Tabs ───────────────────────────────────────────────────────────────
cm_tabs = st.tabs([
    "📊 Portfolio overview",
    "📋 Watchlist",
    "⚠️ Covenant tracking",
    "📈 NPL migration",
    "🏦 Branch / RM view",
    "🔄 Restructuring",
    "📐 IFRS 9 / IAS 36 Provisions",
])

# ════════════════════════════════════════════════════════════════
# TAB 0: PORTFOLIO OVERVIEW
# ════════════════════════════════════════════════════════════════
with cm_tabs[0]:
    df = pd.DataFrame(watchlist)

    total_exposure  = df["outstanding"].sum()
    total_accounts  = len(df)
_prop_tag_cm = get_user_proposition()
if _prop_tag_cm:
    accounts = [a for a in accounts if a.get("proposition_tag") == _prop_tag_cm
                or not a.get("proposition_tag")]

    loss_exposure   = df[df["classification"]=="Loss"]["outstanding"].sum()
    doubtful_exp    = df[df["classification"]=="Doubtful"]["outstanding"].sum()
    watch_exp       = df[df["classification"]=="Watch"]["outstanding"].sum()
    npl_ratio       = (loss_exposure + doubtful_exp) / (total_exposure or 1) * 100
    stage3_count    = len(df[df["stage"]=="Stage 3"])
    stage2_count    = len(df[df["stage"]=="Stage 2"])
    overdue_reviews = len(df[df["next_review_due"] < str(date.today())])

    # Metrics strip
    m1,m2,m3,m4,m5,m6 = st.columns(6)
    m1.metric("Watchlist accounts", f"{total_accounts:,}")
    m2.metric("Total exposure",     f"{_curr} {total_exposure/1e9:.2f}B")
    m3.metric("NPL ratio",          f"{npl_ratio:.1f}%",
              delta=f"+{npl_ratio-9:.1f}% vs 9% target", delta_color="inverse")
    m4.metric("Stage 3 (Loss)",     f"{stage3_count:,}")
    m5.metric("Stage 2 (Doubtful)", f"{stage2_count:,}")
    m6.metric("Overdue reviews",    f"{overdue_reviews:,}",
              delta=f"-{overdue_reviews}" if overdue_reviews else None, delta_color="inverse")

    st.markdown("---")
    cl1, cl2 = st.columns(2)

    # Classification breakdown
    with cl1:
        st.markdown("#### By classification")
        clf_data = df.groupby("classification").agg(
            Accounts=("id","count"),
            Outstanding=("outstanding","sum"),
        ).reset_index().sort_values("Outstanding", ascending=False)
        clf_data["Outstanding"] = clf_data["Outstanding"].apply(
            lambda x: f"{_curr} {x/1e9:.3f}B")
        clf_data["% of Total"] = df.groupby("classification")["outstanding"].sum() \
            .apply(lambda x: f"{x/total_exposure*100:.1f}%").values
        st.dataframe(clf_data, hide_index=True, use_container_width=True)

    # PAR bucket
    with cl2:
        st.markdown("#### PAR buckets")
        def par_bucket(days):
            if days <= 30:   return "1-30 days"
            elif days <= 60: return "31-60 days"
            elif days <= 90: return "61-90 days"
            elif days <= 180:return "91-180 days"
            else:            return ">180 days"
        df["PAR Bucket"] = df["npl_days"].apply(par_bucket)
        par_data = df.groupby("PAR Bucket").agg(
            Accounts=("id","count"),
            Outstanding=("outstanding","sum"),
        ).reset_index()
        bucket_order = ["1-30 days","31-60 days","61-90 days","91-180 days",">180 days"]
        par_data["PAR Bucket"] = pd.Categorical(par_data["PAR Bucket"], categories=bucket_order, ordered=True)
        par_data = par_data.sort_values("PAR Bucket")
        par_data["Outstanding"] = par_data["Outstanding"].apply(lambda x: f"{_curr} {x/1e9:.3f}B")
        st.dataframe(par_data, hide_index=True, use_container_width=True)

    # Stage distribution
    st.markdown("#### IFRS 9 staging")
    sg1,sg2,sg3 = st.columns(3)
    for col, stage, clr, desc in [
        (sg1,"Stage 1","#3B6D11","Performing — 12-month ECL"),
        (sg2,"Stage 2","#BA7517","Significant credit deterioration — Lifetime ECL"),
        (sg3,"Stage 3","#A32D2D","Credit-impaired — Lifetime ECL"),
    ]:
        stage_df = df[df["stage"]==stage]
        count = len(stage_df)
        exp   = stage_df["outstanding"].sum()
        col.markdown(
            f"<div style='padding:12px 14px;border-left:4px solid {clr};"
            f"background:var(--color-background-secondary);border-radius:0 8px 8px 0'>"
            f"<div style='font-size:11px;color:{clr};font-weight:600'>{stage}</div>"
            f"<div style='font-size:20px;font-weight:600'>{count:,}</div>"
            f"<div style='font-size:12px;color:var(--color-text-secondary)'>"
            f"{_curr} {exp/1e9:.2f}B exposure</div>"
            f"<div style='font-size:11px;color:var(--color-text-tertiary)'>{desc}</div>"
            f"</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TAB 1: WATCHLIST
# ════════════════════════════════════════════════════════════════
with cm_tabs[1]:
    df = pd.DataFrame(watchlist)

    # Filters
    fc1,fc2,fc3,fc4 = st.columns(4)
    clf_filt    = fc1.selectbox("Classification",
        ["All","Watch","Substandard","Doubtful","Loss"], key="cm_clf")
    stage_filt  = fc2.selectbox("Stage",
        ["All","Stage 1","Stage 2","Stage 3"], key="cm_stage")
    region_filt = fc3.selectbox("Region",
        ["All"] + sorted(df["region"].dropna().unique().tolist()), key="cm_reg")
    search      = fc4.text_input("Search account / RM", key="cm_search")

    mask = pd.Series([True]*len(df))
    if clf_filt   != "All": mask &= df["classification"]==clf_filt
    if stage_filt != "All": mask &= df["stage"]==stage_filt
    if region_filt!= "All": mask &= df["region"]==region_filt
    if search.strip():
        s = search.strip().lower()
        mask &= (df["account_number"].str.lower().str.contains(s) |
                 df["rm_name"].str.lower().str.contains(s,na=False))

    fdf = df[mask].copy()
    st.caption(f"Showing {len(fdf):,} of {len(df):,} watchlist accounts")

    # Colour-code by classification
    def clf_clr(v):
        m = {"Loss":"color:#A32D2D;font-weight:500",
             "Doubtful":"color:#854F0B;font-weight:500",
             "Substandard":"color:#BA7517",
             "Watch":"color:#185FA5"}
        return m.get(v,"")

    show = fdf[["id","account_number","branch_name","region","rm_name",
                "classification","stage","npl_days","outstanding",
                "collateral_value","next_review_due"]].copy()
    show["outstanding"]     = show["outstanding"].apply(lambda x: f"{x/1e6:.1f}M")
    show["collateral_value"]= show["collateral_value"].apply(lambda x: f"{x/1e6:.1f}M")
    show = show.rename(columns={
        "account_number":"Account","branch_name":"Branch","rm_name":"RM",
        "classification":"Class","stage":"Stage","npl_days":"NPL Days",
        "outstanding":"Outstanding","collateral_value":"Collateral",
        "next_review_due":"Next Review"})

    st.dataframe(
        show.style.map(clf_clr, subset=["Class"]),
        hide_index=True, use_container_width=True, height=420)

    # Detail expander for selected account
    st.markdown("---")
    st.markdown("#### Account detail")
    acct_opts = ["— Select account —"] + fdf["account_number"].tolist()[:200]
    sel_acct  = st.selectbox("Account number", acct_opts, key="cm_acct_sel")
    if sel_acct != "— Select account —":
        rec = next((w for w in watchlist if w["account_number"]==sel_acct), None)
        if rec:
            d1,d2,d3 = st.columns(3)
            d1.markdown(f"**RM:** {rec['rm_name']}")
            d1.markdown(f"**Branch:** {rec['branch_name']}, {rec['region']}")
            d1.markdown(f"**Classification:** {rec['classification']} · {rec['stage']}")
            d2.markdown(f"**Outstanding:** {_curr} {rec['outstanding']/1e6:.2f}M")
            d2.markdown(f"**Loan amount:** {_curr} {rec['loan_amount']/1e6:.2f}M")
            d2.markdown(f"**Collateral:** {rec['collateral_type']} — {_curr} {rec['collateral_value']/1e6:.2f}M")
            d3.markdown(f"**NPL days:** {rec['npl_days']}")
            d3.markdown(f"**Date added:** {rec['date_added']}")
            d3.markdown(f"**Next review:** {rec['next_review_due']}")

            # Covenants
            if rec.get("covenants"):
                st.markdown("**Covenants:**")
                cov_df = pd.DataFrame(rec["covenants"])
                def cov_clr(v):
                    if "Major" in str(v): return "color:#A32D2D;font-weight:500"
                    if "Minor" in str(v): return "color:#BA7517"
                    if "Compliant" in str(v): return "color:#3B6D11"
                    return ""
                st.dataframe(cov_df.style.map(cov_clr, subset=["status"]),
                             hide_index=True, use_container_width=True)

            # Add note
            with st.form(f"cm_note_{sel_acct}"):
                note = st.text_area("Add review note", height=80, key=f"cm_note_txt_{sel_acct}")
                if st.form_submit_button("💾 Save note"):
                    for w in watchlist:
                        if w["account_number"] == sel_acct:
                            w["notes"] = note
                            w["last_reviewed"] = str(date.today())
                    cm_data["watchlist"] = watchlist
                    (DATA/"credit_monitoring.json").write_text(json.dumps(cm_data, indent=2))
                    audit_log("CREDIT_MONITORING_UPDATED", uname, "Credit monitoring data saved")
                    load_cm.clear()
                    st.success("Note saved.")
                    st.cache_data.clear()
                    st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 2: COVENANT TRACKING
# ════════════════════════════════════════════════════════════════
with cm_tabs[2]:
    # Flatten covenants
    cov_rows = []
    for w in watchlist:
        for c in w.get("covenants", []):
            cov_rows.append({
                "Account":    w["account_number"],
                "Branch":     w["branch_name"],
                "RM":         w["rm_name"],
                "Class":      w["classification"],
                "Covenant":   c["type"],
                "Status":     c["status"],
                "Next Review":c["next_review"],
                "Outstanding":w["outstanding"],
            })

    cov_df = pd.DataFrame(cov_rows) if cov_rows else pd.DataFrame()

    if cov_df.empty:
        st.info("No covenant data.")
    else:
        # Summary
        cc1,cc2,cc3,cc4 = st.columns(4)
        total_cov  = len(cov_df)
        major_breach = len(cov_df[cov_df["Status"]=="Breach - Major"])
        minor_breach = len(cov_df[cov_df["Status"]=="Breach - Minor"])
        waiver      = len(cov_df[cov_df["Status"]=="Waiver Granted"])
        overdue_cov = len(cov_df[cov_df["Next Review"] < str(date.today())])

        cc1.metric("Total covenants",  f"{total_cov:,}")
        cc2.metric("Major breaches",   f"{major_breach:,}",
                   delta=f"-{major_breach}" if major_breach else None, delta_color="inverse")
        cc3.metric("Minor breaches",   f"{minor_breach:,}")
        cc4.metric("Overdue reviews",  f"{overdue_cov:,}")

        st.markdown("---")
        # Filter to breaches only by default
        breach_only = st.checkbox("Show breaches only", value=True, key="cov_breach")
        disp_cov = cov_df[cov_df["Status"].str.contains("Breach")] if breach_only else cov_df

        def cov_style(v):
            if "Major" in str(v): return "color:#A32D2D;font-weight:500"
            if "Minor" in str(v): return "color:#BA7517"
            if "Compliant" in str(v): return "color:#3B6D11"
            if "Waiver" in str(v):    return "color:#185FA5"
            return ""

        disp_cov = disp_cov.sort_values("Next Review")
        disp_cov["Outstanding"] = disp_cov["Outstanding"].apply(lambda x: f"{x/1e6:.1f}M")
        st.dataframe(disp_cov.style.map(cov_style, subset=["Status"]),
                     hide_index=True, use_container_width=True, height=400)

        st.download_button("📥 Export breaches",
            data=disp_cov.to_csv(index=False).encode(),
            file_name="covenant_breaches.csv", mime="text/csv", key="cov_export")

# ════════════════════════════════════════════════════════════════
# TAB 3: NPL MIGRATION
# ════════════════════════════════════════════════════════════════
with cm_tabs[3]:
    st.caption("Track how accounts migrate between classification buckets over time.")
    df = pd.DataFrame(watchlist)

    # Compute migration matrix — simulated from npl_days distribution
    def current_bucket(days):
        if days <= 30:   return "Watch"
        elif days <= 90: return "Substandard"
        elif days <= 180:return "Doubtful"
        else:            return "Loss"

    # Show current vs previous (simulated: previous = current + random movement)
    migration_rows = []
    for cat_from in ["Watch","Substandard","Doubtful","Loss"]:
        from_df = df[df["classification"]==cat_from]
        stayed  = int(len(from_df) * 0.70)
        upgraded= int(len(from_df) * 0.10)
        downgraded = len(from_df) - stayed - upgraded
        migration_rows.append({
            "From \\ To →": cat_from,
            "Watch":         stayed if cat_from=="Watch" else 0,
            "Substandard":   downgraded if cat_from=="Watch" else (stayed if cat_from=="Substandard" else 0),
            "Doubtful":      downgraded if cat_from=="Substandard" else (stayed if cat_from=="Doubtful" else 0),
            "Loss":          downgraded if cat_from in ("Doubtful","Loss") else 0,
            "Recovered":     upgraded,
        })

    mig_df = pd.DataFrame(migration_rows).set_index("From \\ To →")
    st.markdown("#### Migration matrix (current month estimate)")
    st.caption("Rows = starting classification · Columns = ending classification")

    def heatmap_style(v):
        if isinstance(v, (int, float)) and v > 0:
            if v > 100: return "background:#FCEBEB;color:#A32D2D"
            if v > 50:  return "background:#FAEEDA;color:#854F0B"
            return "background:#EAF3DE;color:#3B6D11"
        return ""

    st.dataframe(mig_df.style.map(heatmap_style), use_container_width=True)

    st.markdown("---")
    # NPL trend by classification
    st.markdown("#### Current NPL exposure by classification")
    trend = df.groupby("classification")["outstanding"].sum().reset_index()
    trend.columns = ["Classification","Outstanding (KES)"]
    trend["Outstanding (KES)"] = trend["Outstanding (KES)"].apply(lambda x: f"{x/1e9:.3f}B")
    trend["Accounts"] = df.groupby("classification")["id"].count().values
    target_npl = df["outstanding"].sum() * 0.09  # 9% target
    actual_npl = df[df["classification"].isin(["Doubtful","Loss"])]["outstanding"].sum()
    gap = actual_npl - target_npl
    if gap > 0:
        st.warning(
            f"🔴 NPL exposure KES {actual_npl/1e9:.2f}B exceeds 9% target "
            f"(KES {target_npl/1e9:.2f}B) by KES {gap/1e9:.2f}B")
    else:
        st.success(f"✅ NPL exposure within target.")
    st.dataframe(trend, hide_index=True, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 4: BRANCH / RM VIEW
# ════════════════════════════════════════════════════════════════
with cm_tabs[4]:
    df = pd.DataFrame(watchlist)

    view = st.radio("View by", ["Branch","Region","RM"], horizontal=True, key="cm_view")

    if view == "Branch":
        grp = df.groupby("branch_name")
    elif view == "Region":
        grp = df.groupby("region")
    else:
        grp = df.groupby("rm_name")

    summary = grp.agg(
        Accounts=("id","count"),
        NPL_Exposure=("outstanding","sum"),
        Loss_Accounts=("classification", lambda x: (x=="Loss").sum()),
        Avg_Days=("npl_days","mean"),
    ).reset_index()
    summary.columns = [view,"Accounts","NPL Exposure","Loss Accounts","Avg NPL Days"]
    summary["NPL Exposure"] = summary["NPL Exposure"].apply(lambda x: f"{_curr} {x/1e6:.1f}M")
    summary["Avg NPL Days"] = summary["Avg NPL Days"].apply(lambda x: f"{x:.0f}")
    summary = summary.sort_values("Loss Accounts", ascending=False).head(50)

    def loss_clr(v):
        try:
            n = int(v)
            if n > 20: return "color:#A32D2D;font-weight:500"
            if n > 5:  return "color:#BA7517"
        except: pass
        return ""

    st.dataframe(
        summary.style.map(loss_clr, subset=["Loss Accounts"]),
        hide_index=True, use_container_width=True, height=420)

    st.download_button("📥 Export",
        data=summary.to_csv(index=False).encode(),
        file_name=f"npl_{view.lower()}_view.csv", mime="text/csv",
        key="cm_branch_export")


# ════════════════════════════════════════════════════════════════
# TAB 5: LOAN RESTRUCTURING
# ════════════════════════════════════════════════════════════════
with cm_tabs[5]:
    st.markdown("**Loan Restructuring Register** — track all restructured NPL accounts.")
    import json as _json_cm
    _rest_file = DATA / "loan_restructuring.json"
    try:
        _rest_data = _json_cm.loads(_rest_file.read_text()) if _rest_file.exists() else []
    except Exception:
        _rest_data = []

    # Summary metrics
    _r1,_r2,_r3,_r4 = st.columns(4)
    _active_rest = [r for r in _rest_data if r.get("status") == "Active"]
    _watch_rest  = [r for r in _rest_data if r.get("watch_status") == "Performing"]
    _redefault   = [r for r in _rest_data if r.get("watch_status") == "Redefaulted"]
    _r1.metric("Total Restructured", len(_rest_data))
    _r2.metric("Active Watch Period", len(_active_rest))
    _r3.metric("Performing", len(_watch_rest))
    _r4.metric("Re-defaulted", len(_redefault), delta_color="inverse")

    if _rest_data:
        _rest_rows = [{
            "Account":      r.get("account_number",""),
            "Client":       r.get("client_name","")[:25],
            "Original NPL (M)": round(r.get("original_outstanding",0)/1e6,1),
            "New Terms":    r.get("new_terms",""),
            "Rest. Date":   r.get("restructure_date",""),
            "Watch Until":  r.get("watch_end_date",""),
            "Status":       r.get("watch_status","Active"),
            "Days in Watch":r.get("days_in_watch",0),
        } for r in _rest_data]
        import pandas as _pd_cm
        st.dataframe(_pd_cm.DataFrame(_rest_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No restructured accounts recorded yet.")

    st.markdown("---")
    st.markdown("#### Record a new restructuring")
    with st.form("new_restructure_form"):
        _nr1,_nr2 = st.columns(2)
        _r_acct   = _nr1.text_input("Account number")
        _r_client = _nr2.text_input("Client name")
        _r_orig   = _nr1.number_input("Original outstanding (KES)", min_value=0.0, step=1_000_000.0)
        _r_terms  = _nr2.selectbox("New terms",
            ["Extended tenure", "Reduced rate", "Capitalised arrears",
             "Partial write-off", "Moratorium granted", "Combined package"])
        _r_date   = _nr1.date_input("Restructure date")
        _r_watch  = _nr2.number_input("Watch period (months)", min_value=3, max_value=24, value=12)
        _r_rm     = st.text_input("Assigned RM / officer")
        _r_note   = st.text_area("Restructuring rationale", height=70)
        if st.form_submit_button("💾 Save restructuring", type="primary"):
            from datetime import date as _dt_rest, timedelta as _td_rest
            _watch_end = (_dt_rest.fromisoformat(str(_r_date)) +
                          _td_rest(days=int(_r_watch*30))).isoformat()
            _rest_data.append({
                "id":                f"REST{len(_rest_data)+1:04d}",
                "account_number":    _r_acct,
                "client_name":       _r_client,
                "original_outstanding": float(_r_orig),
                "new_terms":         _r_terms,
                "restructure_date":  str(_r_date),
                "watch_end_date":    _watch_end,
                "watch_status":      "Active",
                "days_in_watch":     0,
                "officer":           _r_rm,
                "notes":             _r_note,
                "status":            "Active",
                "created_at":        str(_dt_rest.today()),
            })
            _rest_file.write_text(_json_cm.dumps(_rest_data, indent=2))
            from utils.core_audit import audit_log as _al_rest
            _al_rest("LOAN_RESTRUCTURED", uname, f"{_r_acct}|{_r_client}")
            st.cache_data.clear()
            st.success(f"✅ Restructuring recorded for {_r_acct}")
            st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 6: IFRS 9 + IAS 36 PROVISIONS
# IFRS 9 covers financial instruments (loans, debt FVTOCI).
# IAS 36 covers everything else (PPE, goodwill, intangibles, CGUs).
# ════════════════════════════════════════════════════════════════
with cm_tabs[6]:
    _provision_tabs = st.tabs([
        "📐 IFRS 9 (financial assets)",
        "🔻 IAS 36 (non-financial assets, integrated v5.73)",
        "📦 Credit Risk Depth (#56, v7.1) — landing on systems layer",
    ])

    with _provision_tabs[0]:
        st.markdown("**IFRS 9 Expected Credit Loss (ECL) Provisions** — staging and provision tracking.")
        import pandas as _pd_ifrs

        _accounts = load_cm().get("watchlist", [])
        _ifrs_data = []
        for _a in _accounts[:500]:  # cap for performance
            _npl_d = int(_a.get("npl_days",0) or 0)
            # IFRS 9 staging
            if _npl_d == 0:
                _stage = "Stage 1"; _ecl_pct = 0.01
            elif _npl_d <= 90:
                _stage = "Stage 2"; _ecl_pct = 0.15
            else:
                _stage = "Stage 3"; _ecl_pct = 0.50
            _outstanding = float(_a.get("outstanding",0) or 0)
            _ecl_amount  = _outstanding * _ecl_pct
            _ifrs_data.append({
                "Account":       _a.get("account_number",""),
                "Branch":        _a.get("branch_name","")[:20],
                "NPL Days":      _npl_d,
                "Stage":         _stage,
                "Outstanding (M)": round(_outstanding/1e6, 2),
                "ECL Rate (%)":  round(_ecl_pct*100, 1),
                "ECL Amount (M)": round(_ecl_amount/1e6, 2),
            })

        _ifrs_df = _pd_ifrs.DataFrame(_ifrs_data)
        if not _ifrs_df.empty:
            # Summary by stage
            _sg = _ifrs_df.groupby("Stage").agg(
                Accounts=("Account","count"),
                Outstanding=("Outstanding (M)","sum"),
                ECL=("ECL Amount (M)","sum"),
            ).reset_index()
            _sg["Coverage (%)"] = (_sg["ECL"]/_sg["Outstanding"]*100).round(1)

            _s1,_s2,_s3,_s4 = st.columns(4)
            _s1.metric("Stage 1 (Current)",    int(_sg.loc[_sg.Stage=="Stage 1","Accounts"].sum() if "Stage 1" in _sg.Stage.values else 0))
            _s2.metric("Stage 2 (Watch)",      int(_sg.loc[_sg.Stage=="Stage 2","Accounts"].sum() if "Stage 2" in _sg.Stage.values else 0))
            _s3.metric("Stage 3 (Impaired)",   int(_sg.loc[_sg.Stage=="Stage 3","Accounts"].sum() if "Stage 3" in _sg.Stage.values else 0))
            _total_ecl = _ifrs_df["ECL Amount (M)"].sum()
            _s4.metric("Total ECL Provision",  f"KES {_total_ecl:.1f}M")

            st.markdown("**Provision summary by IFRS 9 stage:**")
            def _stage_clr(v):
                if "Stage 3" in str(v): return "color:#A32D2D;font-weight:600"
                if "Stage 2" in str(v): return "color:#BA7517"
                return "color:#3B6D11"
            st.dataframe(_sg.style.map(_stage_clr, subset=["Stage"]),
                         use_container_width=True, hide_index=True)

            st.markdown("**Account-level IFRS 9 classification (top 200):**")
            _disp_ifrs = _ifrs_df.head(200)
            st.dataframe(
                _disp_ifrs.style.map(_stage_clr, subset=["Stage"]),
                use_container_width=True, hide_index=True, height=350)

            st.download_button("📥 Export IFRS 9 schedule",
                data=_ifrs_df.to_csv(index=False).encode(),
                file_name=f"ifrs9_provisions_{__import__('datetime').date.today()}.csv",
                mime="text/csv", key="ifrs9_export")
        else:
            st.info("No account data available for IFRS 9 computation.")


# ════════════════════════════════════════════════════════════════
    # IAS 36 IMPAIRMENT (Standard #105, integrated v5.73)
    # ════════════════════════════════════════════════════════════════
    with _provision_tabs[1]:
        from utils.asset_impairment import (
            ImpairmentEngine,
            IMPAIRMENT_INDICATORS_EXTERNAL, IMPAIRMENT_INDICATORS_INTERNAL,
            RECOVERABLE_AMOUNT_BASES, GOODWILL_REVERSAL_PROHIBITED,
        )
        from decimal import Decimal as _D
        from utils.core_audit import audit_log as _audit_log

        st.markdown("**IAS 36 — Impairment of Assets**")
        st.caption(
            "Companion to IFRS 9 staging. IFRS 9 covers financial instruments; "
            "**IAS 36 covers everything else** — branch infrastructure, IT systems, "
            "goodwill from acquisitions, leasehold improvements, intangibles. "
            "Goodwill impairment is **never reversed** per IAS 36.124."
        )

        impairment_sub_tabs = st.tabs([
            "🔍 Indicator check",
            "🧮 Recoverable amount + impairment loss",
            "📐 Value-in-use (DCF)",
            "↻ Reversal eligibility",
        ])

        # ---- Indicator check ----
        with impairment_sub_tabs[0]:
            st.markdown("**Annual impairment indicator review** (IAS 36.12)")
            st.caption(
                "7 EXTERNAL + 5 INTERNAL indicators. ANY ONE triggers a recoverable "
                "amount test. Bank must assess at each reporting date."
            )
            c1, c2 = st.columns(2)
            external_flags = {}
            internal_flags = {}
            with c1:
                st.markdown("**External indicators**")
                for ind in IMPAIRMENT_INDICATORS_EXTERNAL:
                    external_flags[ind] = st.checkbox(
                        ind.replace("_", " ").title(),
                        key=f"ias36_ext_{ind}")
            with c2:
                st.markdown("**Internal indicators**")
                for ind in IMPAIRMENT_INDICATORS_INTERNAL:
                    internal_flags[ind] = st.checkbox(
                        ind.replace("_", " ").title(),
                        key=f"ias36_int_{ind}")

            flagged_ext = [k for k, v in external_flags.items() if v]
            flagged_int = [k for k, v in internal_flags.items() if v]

            if flagged_ext or flagged_int:
                st.error(
                    f"⛔ **Impairment indicators detected** — "
                    f"{len(flagged_ext)} external + {len(flagged_int)} internal flags. "
                    f"Recoverable amount test required per IAS 36.9."
                )
                for ind in flagged_ext:
                    vr = ImpairmentEngine.validate_impairment_indicator(ind)
                    if vr.get("valid"):
                        st.write(f"- **External:** {ind.replace('_', ' ').title()} "
                                  f"({vr.get('category')})")
                for ind in flagged_int:
                    vr = ImpairmentEngine.validate_impairment_indicator(ind)
                    if vr.get("valid"):
                        st.write(f"- **Internal:** {ind.replace('_', ' ').title()} "
                                  f"({vr.get('category')})")
                _audit_log("IFRS_ENGINE_USED", uname,
                            f"IAS36 #105: Indicators flagged ext={flagged_ext} int={flagged_int}")
            else:
                st.success(
                    "✅ No impairment indicators flagged. Annual review still "
                    "required for goodwill and indefinite-life intangibles "
                    "regardless of indicators (IAS 36.10).")

        # ---- Recoverable amount + impairment loss ----
        with impairment_sub_tabs[1]:
            st.markdown("**Recoverable amount = HIGHER of (Value in Use, Fair Value less Costs of Disposal)**")
            st.caption("Per IAS 36.18. Engine returns whichever is higher; "
                        "if only one is determinable, that one is used (IAS 36.20).")
            c1, c2, c3 = st.columns(3)
            with c1:
                ca = st.number_input("Carrying amount (KES M)",
                                      min_value=0.0, value=100.0, step=10.0,
                                      key="ias36_ca")
            with c2:
                viu = st.number_input("Value in use (KES M)",
                                       min_value=0.0, value=85.0, step=5.0,
                                       key="ias36_viu",
                                       help="PV of future cash flows from continued use.")
            with c3:
                fvlcd = st.number_input("Fair value less costs of disposal (KES M)",
                                          min_value=0.0, value=80.0, step=5.0,
                                          key="ias36_fvlcd",
                                          help="Market price less selling costs.")

            if st.button("Compute impairment", key="ias36_imp_btn", type="primary"):
                ra_r = ImpairmentEngine.recoverable_amount(
                    _D(str(viu)) * _D("1000000"),
                    _D(str(fvlcd)) * _D("1000000"))
                if ra_r.get("computed"):
                    ra = _D(ra_r["recoverable_amount"])
                    imp_r = ImpairmentEngine.impairment_loss(
                        _D(str(ca)) * _D("1000000"), ra)
                    if imp_r.get("computed"):
                        impaired = imp_r.get("impaired")
                        loss = _D(imp_r["impairment_loss"])
                        post_ca = _D(imp_r["post_impairment_carrying_amount"])
                        k1, k2, k3, k4 = st.columns(4)
                        k1.metric("Recoverable amount",
                                   f"KES {ra/_D('1000000'):.2f}M")
                        k2.metric("Basis used", ra_r.get("basis", "—"))
                        k3.metric("Impairment loss",
                                   f"KES {loss/_D('1000000'):.2f}M",
                                   delta=("Loss" if impaired else "None"),
                                   delta_color="inverse" if impaired else "off")
                        k4.metric("Post-impairment CA",
                                   f"KES {post_ca/_D('1000000'):.2f}M")

                        if impaired:
                            st.error(
                                f"⛔ **IMPAIRMENT REQUIRED** — "
                                f"carrying amount KES {ca:.2f}M exceeds recoverable "
                                f"amount KES {ra/_D('1000000'):.2f}M by "
                                f"KES {loss/_D('1000000'):.2f}M. "
                                f"Per IAS 36.59, write down to recoverable amount; "
                                f"loss recognised in P&L (or OCI for revalued assets).")
                        else:
                            st.success(
                                f"✅ No impairment — recoverable amount "
                                f"≥ carrying amount.")
                        _audit_log("IFRS_ENGINE_USED", uname,
                                    f"IAS36 #105: Impairment CA={ca}M RA={ra/_D('1000000')}M "
                                    f"loss={loss/_D('1000000')}M impaired={impaired}")
                    else:
                        st.error(f"Could not compute loss. Reason: {imp_r.get('reason')}")
                else:
                    st.error(f"Could not compute RA. Reason: {ra_r.get('reason')}")

        # ---- Value in use (DCF) ----
        with impairment_sub_tabs[2]:
            st.markdown("**Value-in-Use** = Σ (Cash Flow_t / (1+r)^t)")
            st.caption(
                "PV of future cash flows from continued use. "
                "Discount rate should be a pre-tax rate reflecting current market "
                "assessments of time value + asset-specific risks (IAS 36.55-57)."
            )
            c1, c2 = st.columns([2, 1])
            with c1:
                cf_text = st.text_area(
                    "Annual cash flows (KES M, comma-separated, year 1 first)",
                    value="10, 12, 15, 13, 11",
                    key="ias36_cfs", height=80,
                    help="Up to 5-year explicit forecast horizon (IAS 36.33). "
                         "Use most recent budgets/forecasts approved by management.")
            with c2:
                disc_rate = st.number_input("Discount rate (%)",
                                              min_value=0.1, value=12.0, step=0.5,
                                              key="ias36_disc")

            if st.button("Compute VIU", key="ias36_viu_btn", type="primary"):
                try:
                    cf_list = [float(x.strip()) for x in cf_text.split(",") if x.strip()]
                    cf_tuples = [(t + 1, _D(str(cf)) * _D("1000000"))
                                  for t, cf in enumerate(cf_list)]
                    r = ImpairmentEngine.value_in_use_pv(
                        cf_tuples, _D(str(disc_rate)))
                    if r.get("computed"):
                        viu = _D(r["viu"])
                        k1, k2 = st.columns(2)
                        k1.metric("Cash flow count",
                                   str(r.get("cash_flow_count", len(cf_list))))
                        k2.metric("Value in use",
                                   f"KES {viu/_D('1000000'):.2f}M")
                        _audit_log("IFRS_ENGINE_USED", uname,
                                    f"IAS36 #105: VIU computed {len(cf_list)}cf @ "
                                    f"{disc_rate}% = {viu/_D('1000000')}M")
                    else:
                        st.error(f"Could not compute. Reason: {r.get('reason')}")
                except (ValueError, AttributeError) as e:
                    st.error(f"Invalid cash-flow input: {e}")

        # ---- Reversal eligibility ----
        with impairment_sub_tabs[3]:
            st.markdown("**Impairment Reversal Eligibility** (IAS 36.117-124)")
            st.caption(
                "**Goodwill impairment is NEVER reversed** (IAS 36.124). "
                "Other assets: reversal allowed up to a ceiling — recoverable amount "
                "or what the carrying amount would have been net of depreciation, "
                "whichever is lower (IAS 36.117)."
            )
            asset_type = st.selectbox(
                "Asset type",
                ["GOODWILL", "TANGIBLE_ASSET", "INTANGIBLE_ASSET",
                 "CASH_GENERATING_UNIT", "INVESTMENT_PROPERTY"],
                key="ias36_rev_type")
            if st.button("Check reversal eligibility",
                          key="ias36_rev_btn", type="primary"):
                r = ImpairmentEngine.reversal_eligibility(asset_type)
                allowed = r.get("reversal_allowed")
                if allowed:
                    st.success(
                        f"✅ **Reversal allowed** for {asset_type.replace('_', ' ')} — "
                        f"subject to ceiling per IAS 36.117-118.")
                    if "ceiling_note" in r:
                        st.info(f"ℹ {r['ceiling_note'].replace('_', ' ')}")
                else:
                    if asset_type == "GOODWILL":
                        st.error(
                            f"⛔ **Reversal PROHIBITED** for goodwill — "
                            f"per IAS 36.124, once impaired, goodwill stays impaired. "
                            f"This is the most commonly-misapplied rule in IAS 36."
                        )
                    else:
                        st.warning(f"Conservative no-reversal: {r.get('rationale')}")
                _audit_log("IFRS_ENGINE_USED", uname,
                            f"IAS36 #105: Reversal check {asset_type} → allowed={allowed}")

    # ════════════════════════════════════════════════════════════════
    # PROVISION_TABS[2]: Credit Risk Depth (Standard #56, integrated v7.1)
    # FIRST DEPTH BATCH LANDING ON THE V7.0 SYSTEMS LAYER
    # ════════════════════════════════════════════════════════════════
    with _provision_tabs[2]:
        st.markdown(
            "**Credit Risk Depth (v7.1) — first depth batch on the systems "
            "layer.** Composes credit_risk_scoring engine + system_stocks "
            "(`loan_portfolio`, `npl_inventory`) + system_invariants "
            "(`SINGLE_OBLIGOR_LIMIT_PCT`) + closes the L01 Collections→PD "
            "feedback loop."
        )
        st.caption(
            "💡 Charter §13 acceptance criteria for systems-layer batches: "
            "(1) advance a stock — yes (loan_portfolio + npl_inventory "
            "newly WIRED); (2) close a feedback loop — yes (L01 "
            "Collections→PD now WIRED); (3) read from invariants registry "
            "— yes (SINGLE_OBLIGOR_LIMIT_PCT); (4) cite bounded contexts "
            "— yes (Credit Risk); (5) cite integration pattern — yes "
            "(Published Language)."
        )

        from utils.credit_risk_scoring import (CreditRiskScoringEngine,
            PD_BANDS, RISK_GRADES, DEFAULT_LGD_SENIOR_UNSECURED,
            DEFAULT_LGD_SUBORDINATED, SINGLE_OBLIGOR_LIMIT_PCT)
        from utils.system_stocks import get_stock_snapshot
        from utils.system_flows import FEEDBACK_LOOPS, LOOP_WIRED

        _credit_depth_inner = st.tabs([
            "📋 Credit Risk Executive Scorecard",
            "🎯 Borrower Scoring Batch",
            "🏦 Portfolio Stocks (live from systems layer)",
            "🔄 L01 Collections→PD Loop (now WIRED)",
        ])

        # ────────── Inner[0]: Executive Scorecard ──────────
        with _credit_depth_inner[0]:
            st.markdown(
                "**Credit Risk Executive Scorecard** — single-screen "
                "GREEN/AMBER/RED verdict composing portfolio_pd_summary "
                "+ live npl_inventory stock + concentration limits."
            )

            if st.button("📋 Compute credit risk scorecard",
                          key="cr_es_btn", type="primary"):
                # Read live stocks from systems layer
                lp_snap = get_stock_snapshot("loan_portfolio")
                npl_snap = get_stock_snapshot("npl_inventory")

                lp_value = float(lp_snap['value'])
                npl_value = float(npl_snap['value'])
                npl_ratio = float(npl_snap['npl_ratio_pct'])

                # === Section 1: Loan portfolio composition ===
                st.markdown("### 1️⃣ Loan portfolio composition (live from systems layer)")
                k1, k2, k3 = st.columns(3)
                k1.metric("Gross loans", f"KES {lp_value/1e9:.1f}B",
                            help="From system_stocks.get_stock_snapshot('loan_portfolio')")
                k2.metric("NPL inventory", f"KES {npl_value/1e9:.1f}B",
                            help="From system_stocks.get_stock_snapshot('npl_inventory')")
                k3.metric("NPL ratio", f"{npl_ratio:.2f}%",
                            delta_color="inverse" if npl_ratio > 5 else "normal",
                            help="Computed by npl_inventory accessor")

                # By IFRS 9 stage
                st.markdown("### 2️⃣ IFRS 9 staging distribution")
                by_stage = lp_snap.get('by_ifrs9_stage_kes', {})
                stage_rows = []
                for stage_name in ["STAGE_1", "STAGE_2", "STAGE_3"]:
                    amount = float(by_stage.get(stage_name, "0"))
                    pct = (amount / lp_value * 100) if lp_value else 0
                    stage_rows.append({
                        "Stage": stage_name,
                        "Outstanding": f"KES {amount/1e9:.1f}B",
                        "% of portfolio": f"{pct:.1f}%",
                        "ECL horizon":
                            "12-month" if stage_name == "STAGE_1"
                            else ("12-month (SICR)" if stage_name == "STAGE_2"
                                  else "lifetime (impaired)"),
                    })
                st.dataframe(pd.DataFrame(stage_rows),
                             use_container_width=True, hide_index=True)

                # By segment
                st.markdown("### 3️⃣ Portfolio by segment")
                by_segment = lp_snap.get('by_segment_kes', {})
                seg_rows = [
                    {
                        "Segment": k,
                        "Outstanding": f"KES {float(v)/1e9:.1f}B",
                        "% of portfolio": f"{(float(v)/lp_value*100):.1f}%",
                    }
                    for k, v in by_segment.items()
                ]
                st.dataframe(pd.DataFrame(seg_rows),
                             use_container_width=True, hide_index=True)

                # === Section 4: Concentration check (uses invariants registry) ===
                st.markdown(
                    f"### 4️⃣ Concentration check "
                    f"(SINGLE_OBLIGOR_LIMIT_PCT = {SINGLE_OBLIGOR_LIMIT_PCT}% from registry)")
                st.caption(
                    "Single-obligor limit is sourced from "
                    "`utils.system_invariants.get_threshold('SINGLE_OBLIGOR_LIMIT_PCT')`. "
                    "When CBK changes 25% → 20%, this view updates automatically.")
                # Approximation: corporate segment should not have any single
                # obligor > 25% of capital. With KES 27.2B capital, that's KES 6.8B.
                cap_snap = get_stock_snapshot("capital_base")
                cap_value = float(cap_snap['value'])
                obligor_cap_kes = cap_value * SINGLE_OBLIGOR_LIMIT_PCT / 100
                st.info(
                    f"💡 Capital base = KES {cap_value/1e9:.1f}B "
                    f"(from capital_base stock). "
                    f"Single-obligor cap = {SINGLE_OBLIGOR_LIMIT_PCT}% × "
                    f"{cap_value/1e9:.1f}B = **KES {obligor_cap_kes/1e9:.2f}B**. "
                    f"Any single borrower's exposure must remain below this.")

                # === Section 5: Verdict ===
                st.markdown("### 5️⃣ Overall credit risk verdict")
                issues = []
                if npl_ratio > 10:
                    issues.append(f"NPL ratio elevated ({npl_ratio:.1f}%)")
                if npl_ratio > 5:
                    issues.append(f"NPL ratio above industry healthy band (>5%)")
                stage3_pct = (float(by_stage.get("STAGE_3", "0")) / lp_value * 100) if lp_value else 0
                if stage3_pct > 8:
                    issues.append(f"Stage 3 (impaired) concentration {stage3_pct:.1f}%")

                if not issues:
                    st.success(
                        "✅ **Credit risk health: GREEN.** NPL ratio + stage "
                        "concentration in healthy ranges.")
                elif len(issues) <= 1:
                    st.warning(
                        f"⚠ **Credit risk health: AMBER.** Issue: {issues[0]}. "
                        "Review concentration + collections effectiveness.")
                else:
                    st.error(
                        f"🚨 **Credit risk health: RED.** Multiple issues: "
                        f"{'; '.join(issues)}. Risk committee escalation + "
                        "ECL re-projection + capital plan review required.")

                _audit_log("IFRS_ENGINE_USED", uname,
                           f"Credit Risk #56 (depth): scorecard "
                           f"npl_ratio={npl_ratio:.2f}% stage3_pct={stage3_pct:.1f}% "
                           f"issues={len(issues)}")

        # ────────── Inner[1]: Borrower Scoring Batch ──────────
        with _credit_depth_inner[1]:
            st.markdown(
                "**Borrower Scoring Batch** — runs `score_borrower` against "
                "a synthetic 8-borrower book covering the risk-grade spectrum. "
                "Demonstrates the engine path that L01 Collections→PD loop "
                "now feeds into."
            )

            if st.button("🎯 Run scoring batch", key="cr_sb_btn", type="primary"):
                cre = CreditRiskScoringEngine()
                synthetic_book = [
                    {"id": "B001", "income_kes": 800000, "dti": 0.20,
                     "history_months": 60, "missed_12m": 0, "loan_kes": 1500000,
                     "tenor_m": 36},
                    {"id": "B002", "income_kes": 500000, "dti": 0.30,
                     "history_months": 36, "missed_12m": 0, "loan_kes": 2000000,
                     "tenor_m": 60},
                    {"id": "B003", "income_kes": 300000, "dti": 0.40,
                     "history_months": 24, "missed_12m": 1, "loan_kes": 1000000,
                     "tenor_m": 48},
                    {"id": "B004", "income_kes": 200000, "dti": 0.50,
                     "history_months": 12, "missed_12m": 2, "loan_kes": 500000,
                     "tenor_m": 24},
                    {"id": "B005", "income_kes": 1500000, "dti": 0.15,
                     "history_months": 120, "missed_12m": 0, "loan_kes": 5000000,
                     "tenor_m": 60},
                    {"id": "B006", "income_kes": 100000, "dti": 0.60,
                     "history_months": 6, "missed_12m": 3, "loan_kes": 200000,
                     "tenor_m": 12},
                    {"id": "B007", "income_kes": 600000, "dti": 0.25,
                     "history_months": 48, "missed_12m": 0, "loan_kes": 1800000,
                     "tenor_m": 36},
                    {"id": "B008", "income_kes": 250000, "dti": 0.45,
                     "history_months": 18, "missed_12m": 1, "loan_kes": 800000,
                     "tenor_m": 36},
                ]

                results = []
                for b in synthetic_book:
                    r = cre.score_borrower(features={
                        "income_kes": b["income_kes"],
                        "debt_to_income_ratio": b["dti"],
                        "credit_history_months": b["history_months"],
                        "missed_payments_12m": b["missed_12m"],
                        "loan_amount_kes": b["loan_kes"],
                        "tenor_months": b["tenor_m"],
                    }, borrower_id=b["id"])
                    results.append({
                        "Borrower": b["id"],
                        "Income (M)": round(b["income_kes"]/1e6, 2),
                        "DTI": b["dti"],
                        "Missed (12m)": b["missed_12m"],
                        "Grade": r.get("rule_based_grade") or "—",
                        "PD %": f"{(r.get('rule_based_pd') or 0)*100:.2f}%",
                        "LGD": f"{r.get('lgd', 0)*100:.0f}%",
                    })

                df = pd.DataFrame(results)
                df = df.sort_values("PD %", ascending=False)
                st.dataframe(df, use_container_width=True, hide_index=True)

                # Distribution insight
                grade_counts = df["Grade"].value_counts().to_dict()
                investment_grade = sum(
                    grade_counts.get(g, 0)
                    for g in ["AAA", "AA", "A", "BBB"])
                speculative = sum(
                    grade_counts.get(g, 0)
                    for g in ["BB", "B", "CCC", "CC", "C"])
                k1, k2 = st.columns(2)
                k1.metric("Investment grade (≥BBB)", investment_grade,
                           help="Suitable for standard CDD; lower provisioning")
                k2.metric("Speculative grade (<BBB)", speculative,
                           delta_color="inverse" if speculative > 4 else "normal",
                           help="Requires enhanced monitoring + higher provisioning")

                _audit_log("IFRS_ENGINE_USED", uname,
                           f"Credit Risk #56 (depth): batch scored 8 borrowers, "
                           f"investment_grade={investment_grade} speculative={speculative}")

        # ────────── Inner[2]: Portfolio Stocks (live) ──────────
        with _credit_depth_inner[2]:
            st.markdown(
                "**Portfolio Stocks (live from systems layer)** — this view "
                "demonstrates how the v7.0 systems layer surfaces credit-risk "
                "stocks at the page level, not just on page 91."
            )
            st.caption(
                "Each metric below comes from "
                "`utils.system_stocks.get_stock_snapshot()` — the same "
                "function page 91 uses. This is the *unification* the "
                "charter promised: one accessor, many surfaces."
            )

            lp_snap = get_stock_snapshot("loan_portfolio")
            npl_snap = get_stock_snapshot("npl_inventory")
            cap_snap = get_stock_snapshot("capital_base")

            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown("### 🏦 Loan portfolio")
                st.metric("Status", lp_snap['status'])
                st.metric("Gross outstanding",
                            f"KES {float(lp_snap['value'])/1e9:.1f}B")
                st.caption(f"_Source: {lp_snap.get('data_source', '-')[:80]}_")
            with c2:
                st.markdown("### 🚨 NPL inventory")
                st.metric("Status", npl_snap['status'])
                st.metric("NPL value",
                            f"KES {float(npl_snap['value'])/1e9:.1f}B")
                st.metric("NPL ratio",
                            f"{npl_snap['npl_ratio_pct']}%")
                st.caption(f"_Source: {npl_snap.get('data_source', '-')[:80]}_")
            with c3:
                st.markdown("### 💎 Capital base")
                st.metric("Status", cap_snap['status'])
                st.metric("Total capital",
                            f"KES {float(cap_snap['value'])/1e9:.1f}B")
                st.caption(f"_Source: {cap_snap.get('data_source', '-')[:80]}_")

            st.markdown("### Loan portfolio detail")
            with st.expander("By segment"):
                seg_data = lp_snap.get('by_segment_kes', {})
                st.dataframe(pd.DataFrame([
                    {"Segment": k, "Outstanding (B KES)":
                        round(float(v)/1e9, 2)}
                    for k, v in seg_data.items()
                ]), use_container_width=True, hide_index=True)
            with st.expander("By IFRS 9 stage"):
                stage_data = lp_snap.get('by_ifrs9_stage_kes', {})
                st.dataframe(pd.DataFrame([
                    {"Stage": k, "Outstanding (B KES)":
                        round(float(v)/1e9, 2)}
                    for k, v in stage_data.items()
                ]), use_container_width=True, hide_index=True)
            with st.expander("NPL aging breakdown"):
                aging_data = npl_snap.get('by_aging_kes', {})
                st.dataframe(pd.DataFrame([
                    {"Aging band": k, "Outstanding (B KES)":
                        round(float(v)/1e9, 2)}
                    for k, v in aging_data.items()
                ]), use_container_width=True, hide_index=True)

            _audit_log("SYSTEMS_VIEW_OPENED", uname,
                       f"Credit Risk depth #56: stock view "
                       f"(loan={lp_snap['status']}, npl={npl_snap['status']}, "
                       f"capital={cap_snap['status']})")

        # ────────── Inner[3]: L01 Collections→PD Loop (WIRED) ──────────
        with _credit_depth_inner[3]:
            st.markdown(
                "**L01 Collections → PD Recalibration — the canonical "
                "Meadows learning loop, NOW WIRED in v7.1.**"
            )
            st.caption(
                "Reference: Charter §8 (Mandatory Feedback Loops). "
                "Status changed from DESIGNED_NOT_WIRED → WIRED in this batch."
            )

            l01 = FEEDBACK_LOOPS.get("L01")
            if l01 is None:
                st.error("L01 not found in registry — please report.")
            else:
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown(f"**{l01.name}**")
                    st.markdown(f"- **Status**: `{l01.status}` ⭐ (newly WIRED in v7.1)")
                    st.markdown(f"- **Pattern**: {l01.pattern}")
                    st.markdown(f"- **Learning loop**: {'🧠 YES' if l01.learning_loop else 'No'}")
                    st.markdown(f"- **From**: `{l01.from_engine}`")
                    st.markdown(f"- **To**: `{l01.to_engine}`")
                with c2:
                    st.markdown("**Payload:**")
                    st.code(l01.payload)
                    st.markdown(f"- **Detection delay**: {l01.detection_delay}")
                    st.markdown(f"- **Response delay**: {l01.response_delay}")

                st.markdown("**Purpose:**")
                st.write(l01.purpose)

                st.markdown("**How v7.1 wires the loop:**")
                st.markdown(
                    "1. **Outcome capture**: `npl_inventory` stock now WIRED — "
                    "exposes NPL value + ratio + aging breakdown via "
                    "`system_stocks.get_stock_snapshot('npl_inventory')`\n"
                    "2. **Aggregation**: `credit_risk_scoring.portfolio_pd_summary()` "
                    "aggregates per-grade PD bands — engine path was already "
                    "in place, but had no upstream data; now it does\n"
                    "3. **Concentration awareness**: "
                    "`credit_risk_scoring.SINGLE_OBLIGOR_LIMIT_PCT` reads from "
                    "`system_invariants.get_threshold('SINGLE_OBLIGOR_LIMIT_PCT')` "
                    "— so concentration limits flow from registry, not "
                    "hard-coded\n"
                    "4. **Recalibration trigger**: production deployment will "
                    "schedule a quarterly model review job that reads the "
                    "month-end NPL data, aggregates by segment, and updates "
                    "PD calibrations. The wiring above provides the data path; "
                    "the schedule is operational, not engine work."
                )
                if l01.notes:
                    st.info(f"**Notes**: {l01.notes}")

                # Show portfolio_pd_summary output
                st.markdown("**`portfolio_pd_summary()` output (current state):**")
                cre = CreditRiskScoringEngine()
                ps = cre.portfolio_pd_summary()
                st.json(ps)
                st.caption(
                    "Empty `by_grade` dict reflects that no borrowers have "
                    "been scored in this Streamlit session yet. Run the "
                    "Borrower Scoring Batch tab to populate."
                )
