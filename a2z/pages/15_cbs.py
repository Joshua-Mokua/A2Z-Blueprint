"""
pages/15_cbs.py — Core Banking Simulation (CBS) Data Explorer
700,000 customers | 1.2M accounts | 35 branches | 232 RMs
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import csv, json, os
from pathlib import Path
from utils.core import fmt_num
from pages._shared import load_shared_state
from pages._access import require_access

require_access("perform")  # same as performance — all logged-in users

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

my_code  = str(ud.get("staff_code","") or uname)
my_unit  = ud.get("unit","")
role_l   = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_mgr   = is_admin or any(k in role_l for k in (
    "managing","director","head","regional","branch manager","chief","manager"))

# ── CBS data path ─────────────────────────────────────────────────────
# cbs_data — search multiple locations to handle different working directories
def _find_cbs() -> "Path":
    _here = Path(__file__).parent        # pages/
    _app  = _here.parent                 # a2z/
    _proj = _app.parent                  # project root
    for _p in [_proj/"cbs_data", _app/"cbs_data", Path("cbs_data")]:
        if _p.exists(): return _p
    return _proj / "cbs_data"            # default (may not exist yet)
CBS = _find_cbs()
DATA_READY = CBS.exists() and (CBS/"customers.csv").exists()

# ── CSS ───────────────────────────────────────────────────────────────
st.markdown("""<style>
.cbs-hdr{background:linear-gradient(135deg,#0F172A 0%,#1E3A5F 60%,#0EA5E9 100%);
  border-radius:14px;padding:20px 26px;margin-bottom:16px;
  box-shadow:0 8px 32px rgba(14,165,233,0.20)}
.stat-card{background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);border-radius:12px;
  padding:14px 16px;text-align:center}
.stat-lbl{font-size:9px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:.7px}
.stat-val{font-size:18px;font-weight:800;color:var(--color-text-primary);margin:4px 0 2px}
.stat-sub{font-size:10px;color:var(--color-text-secondary)}
</style>""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────
st.markdown("""<div class='cbs-hdr'>
<div style='color:var(--color-background-primary);font-size:17px;font-weight:800'>🏦 Core Banking Simulation</div>
<div style='color:rgba(255,255,255,.6);font-size:11px;margin-top:3px'>
700,000 customers · 1.2M accounts · 35 branches · 232 relationship managers
· Simulated core banking data</div>
</div>""", unsafe_allow_html=True)

if not DATA_READY:
    st.warning("⚙️ CBS data not found. Run `python3 generate_cbs.py` to generate the simulation dataset.")
    st.stop()

# ── Load index files (fast) ───────────────────────────────────────────
@st.cache_data(ttl=3600)
def load_branch_summary():
    with open(CBS/"branch_summary.json") as f:
        return json.load(f)

@st.cache_data(ttl=3600)
def load_rm_summary():
    with open(CBS/"rm_portfolio_summary.json") as f:
        return json.load(f)

@st.cache_data(ttl=3600)
def load_branches():
    with open(CBS/"branches.json") as f:
        return pd.DataFrame(json.load(f))

@st.cache_data(ttl=600, show_spinner="Loading customers...")
def load_customers_sample(n=50000):
    rows = []
    with open(CBS/"customers.csv", encoding="utf-8") as f:
        for i,row in enumerate(csv.DictReader(f)):
            if i >= n: break
            rows.append(row)
    return pd.DataFrame(rows)

@st.cache_data(ttl=600, show_spinner="Loading accounts...")
def load_accounts_sample(n=100000):
    rows = []
    with open(CBS/"accounts.csv", encoding="utf-8") as f:
        for i,row in enumerate(csv.DictReader(f)):
            if i >= n: break
            rows.append(row)
    df = pd.DataFrame(rows)
    for c in ["current_balance","loan_outstanding","interest_income_ytd","fee_income_ytd"]:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df

@st.cache_data(ttl=600)
def load_transactions():
    df = pd.read_csv(CBS/"transactions_sample.csv")
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0)
    df["txn_date"] = pd.to_datetime(df["txn_date"])
    return df

br_sum  = load_branch_summary()
rm_sum  = load_rm_summary()
br_df   = load_branches()

# ── Bank-wide totals ──────────────────────────────────────────────────
total_dep   = sum(v["deposit_bal"] for v in br_sum.values())
total_loan  = sum(v["loan_bal"]    for v in br_sum.values())
total_npl   = sum(v["npl_bal"]     for v in br_sum.values())
total_accts = sum(v["acct_count"]  for v in br_sum.values())
total_active= sum(v["active_count"] for v in br_sum.values())
npl_ratio   = total_npl/max(total_loan,1)*100

# ── KPI strip ─────────────────────────────────────────────────────────
kc = st.columns(6)
_kpis = [
    ("#2563EB","Customers","700,000","35 branches"),
    ("#059669","Total Accounts",f"{total_accts:,}",f"{total_active:,} active"),
    ("#10B981","Deposit Book",f"KES {total_dep/1e9:.1f}B","CASA + Term"),
    ("#F59E0B","Loan Book",f"KES {total_loan/1e9:.1f}B","Performing + NPL"),
    ("#EF4444","NPL",f"KES {total_npl/1e9:.1f}B",f"{npl_ratio:.1f}% ratio"),
    ("#7C3AED","RMs",f"232","Across 35 branches"),
]
for i,(clr,lbl,val,sub) in enumerate(_kpis):
    kc[i].markdown(
        f"<div class='stat-card' style='border-top:3px solid {clr}'>"
        f"<div class='stat-lbl'>{lbl}</div>"
        f"<div class='stat-val' style='color:{clr}'>{val}</div>"
        f"<div class='stat-sub'>{sub}</div></div>", unsafe_allow_html=True)

st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ── Sub-navigation ────────────────────────────────────────────────────
view = st.radio("View",
    ["🏢 Branch Portfolio","👤 Customer Explorer","📊 Segment Analysis",
     "💳 Account Analysis","📈 Transaction Activity","🔍 CIF Lookup"],
    horizontal=True, key="cbs_view")

# ══════════════════════════════════════════════════════════════════════
if "Branch Portfolio" in view:
# ══════════════════════════════════════════════════════════════════════
    st.markdown("### 🏢 Branch portfolio — deposits, loans, NPL")
    br_rows = []
    for b in br_df.itertuples():
        s = br_sum.get(b.branch_code, {})
        dep = s.get("deposit_bal",0)
        loan= s.get("loan_bal",0)
        npl = s.get("npl_bal",0)
        br_rows.append({
            "Branch":b.branch_name,"Region":b.region,"County":b.county,
            "Tier":b.tier,"Accounts":s.get("acct_count",0),
            "Active":s.get("active_count",0),
            "Deposits (KES M)":round(dep/1e6,1),
            "Loans (KES M)":round(loan/1e6,1),
            "NPL (KES M)":round(npl/1e6,1),
            "NPL %":round(npl/max(loan,1)*100,1),
        })
    br_tbl = pd.DataFrame(br_rows).sort_values("Deposits (KES M)",ascending=False)

    def _npl_clr(v):
        try:
            v = float(v)
            if v > 15: return "color:#EF4444;font-weight:700"
            if v > 10: return "color:#F59E0B;font-weight:600"
            return "color:#10B981"
        except: return ""

    st.dataframe(
        br_tbl.style.map(_npl_clr, subset=["NPL %"]),
        use_container_width=True, hide_index=True, height=420)

    # Charts
    c1,c2 = st.columns(2)
    fig1 = px.bar(br_tbl.head(15), x="Branch", y="Deposits (KES M)",
        color="Region", title="Top 15 branches by deposit book",
        color_discrete_sequence=px.colors.qualitative.Bold)
    fig1.update_layout(height=320,margin=dict(l=10,r=10,t=40,b=80),xaxis_tickangle=-30)
    c1.plotly_chart(fig1, use_container_width=True)

    fig2 = px.scatter(br_tbl, x="Loans (KES M)", y="NPL %",
        size="Deposits (KES M)", color="Region",
        hover_name="Branch", title="Loan book vs NPL ratio by branch",
        color_discrete_sequence=px.colors.qualitative.Safe)
    fig2.add_hline(y=10, line_dash="dash", line_color="#EF4444",
        annotation_text="10% NPL threshold")
    fig2.update_layout(height=320,margin=dict(l=10,r=10,t=40,b=40))
    c2.plotly_chart(fig2, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════
elif "Customer Explorer" in view:
# ══════════════════════════════════════════════════════════════════════
    st.markdown("### 👤 Customer explorer (first 50,000 sample)")
    cust_df = load_customers_sample(50000)
    fc1,fc2,fc3 = st.columns(3)
    _seg_opts = ["All"] + sorted(cust_df["sub_segment"].dropna().unique().tolist())
    _br_opts  = ["All"] + sorted(cust_df["branch_name"].dropna().unique().tolist())
    _kyc_opts = ["All","Verified","Pending","Expired"]
    _fseg = fc1.selectbox("Segment",_seg_opts)
    _fbr  = fc2.selectbox("Branch",_br_opts)
    _fkyc = fc3.selectbox("KYC status",_kyc_opts)
    _srch = st.text_input("🔍 Search name / CIF / phone")

    mask = pd.Series([True]*len(cust_df))
    if _fseg!="All": mask &= cust_df["sub_segment"]==_fseg
    if _fbr !="All": mask &= cust_df["branch_name"]==_fbr
    if _fkyc!="All": mask &= cust_df["kyc_status"]==_fkyc
    if _srch:
        _srch_l = _srch.lower()
        mask &= (cust_df["full_name"].str.lower().str.contains(_srch_l,na=False) |
                 cust_df["cif"].str.contains(_srch,na=False) |
                 cust_df["phone"].str.contains(_srch,na=False))

    filt = cust_df[mask]
    st.caption(f"{len(filt):,} customers match")
    cols_show = ["cif","full_name","sub_segment","sector","branch_name",
                 "kyc_status","risk_rating","is_dormant_customer","last_activity_date",
                 "relationship_manager_code"]
    cols_show = [c for c in cols_show if c in filt.columns]
    def _risk_clr(v):
        return {"High":"color:#F59E0B","Very High":"color:#EF4444;font-weight:700"}.get(str(v),"")
    st.dataframe(
        filt[cols_show].head(500).style.map(_risk_clr, subset=["risk_rating"] if "risk_rating" in cols_show else []),
        use_container_width=True, hide_index=True, height=380)

# ══════════════════════════════════════════════════════════════════════
elif "Segment Analysis" in view:
# ══════════════════════════════════════════════════════════════════════
    st.markdown("### 📊 Customer segment analysis")
    cust_df = load_customers_sample(200000)

    c1,c2 = st.columns(2)
    _seg_cnt = cust_df["sub_segment"].value_counts().reset_index()
    _seg_cnt.columns = ["Segment","Count"]
    fig_seg = px.pie(_seg_cnt, names="Segment", values="Count",
        title="Customer distribution by segment",
        color_discrete_sequence=px.colors.qualitative.Bold, hole=0.35)
    fig_seg.update_layout(height=340,margin=dict(l=0,r=0,t=40,b=0))
    c1.plotly_chart(fig_seg, use_container_width=True)

    _kyc_cnt = cust_df["kyc_status"].value_counts().reset_index()
    _kyc_cnt.columns = ["KYC Status","Count"]
    fig_kyc = px.bar(_kyc_cnt, x="KYC Status", y="Count",
        title="KYC compliance status",
        color="KYC Status",
        color_discrete_map={"Verified":"#10B981","Pending":"#F59E0B","Expired":"#EF4444"})
    fig_kyc.update_layout(height=340,margin=dict(l=10,r=10,t=40,b=20),showlegend=False)
    c2.plotly_chart(fig_kyc, use_container_width=True)

    c3,c4 = st.columns(2)
    _risk_cnt = cust_df["risk_rating"].value_counts().reset_index()
    _risk_cnt.columns = ["Risk","Count"]
    fig_risk = px.bar(_risk_cnt, x="Risk", y="Count",
        title="Customer risk rating distribution",
        color="Risk",
        color_discrete_map={"Low":"#10B981","Medium":"#F59E0B","High":"#F97316","Very High":"#EF4444"})
    fig_risk.update_layout(height=300,margin=dict(l=10,r=10,t=40,b=20),showlegend=False)
    c3.plotly_chart(fig_risk, use_container_width=True)

    _dom_cnt = cust_df["is_dormant_customer"].astype(str).map({"0":"Active","1":"Dormant"}).value_counts().reset_index()
    _dom_cnt.columns = ["Status","Count"]
    fig_dom = px.pie(_dom_cnt, names="Status", values="Count",
        title="Active vs dormant customers",
        color="Status",
        color_discrete_map={"Active":"#10B981","Dormant":"#EF4444"}, hole=0.4)
    fig_dom.update_layout(height=300,margin=dict(l=0,r=0,t=40,b=0))
    c4.plotly_chart(fig_dom, use_container_width=True)

    # Sector breakdown
    st.markdown("**Sector distribution**")
    _sec_cnt = cust_df["sector"].value_counts().head(15).reset_index()
    _sec_cnt.columns = ["Sector","Count"]
    fig_sec = px.bar(_sec_cnt, x="Count", y="Sector", orientation="h",
        title="Top 15 sectors / occupations",
        color="Count", color_continuous_scale="Blues")
    fig_sec.update_layout(height=420,margin=dict(l=200,r=20,t=40,b=20))
    st.plotly_chart(fig_sec, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════
elif "Account Analysis" in view:
# ══════════════════════════════════════════════════════════════════════
    st.markdown("### 💳 Account analysis (100K sample)")
    acct_df = load_accounts_sample(100000)

    c1,c2 = st.columns(2)
    _cat_bal = acct_df.groupby("category")["current_balance"].sum().reset_index()
    _cat_bal.columns = ["Category","Balance"]
    fig_cat = px.pie(_cat_bal, names="Category", values="Balance",
        title="Balance distribution by account category",
        color_discrete_sequence=px.colors.qualitative.Set2, hole=0.3)
    fig_cat.update_layout(height=320,margin=dict(l=0,r=0,t=40,b=0))
    c1.plotly_chart(fig_cat, use_container_width=True)

    _npl_br = acct_df[acct_df["npl_status"]=="NPL"].groupby("branch_code")["loan_outstanding"].sum().reset_index().head(10)
    _npl_br.columns = ["Branch","NPL (KES)"]
    fig_npl = px.bar(_npl_br, x="Branch", y="NPL (KES)",
        title="NPL by branch (top 10 sample)",
        color="NPL (KES)", color_continuous_scale="Reds")
    fig_npl.update_layout(height=320,margin=dict(l=10,r=10,t=40,b=40))
    c2.plotly_chart(fig_npl, use_container_width=True)

    # Dormancy
    _dorm = acct_df.groupby(["category","dormancy_status"]).size().reset_index(name="Count")
    fig_dorm = px.bar(_dorm, x="category", y="Count", color="dormancy_status",
        title="Active vs Dormant accounts by category",
        color_discrete_map={"Active":"#10B981","Dormant":"#EF4444"},
        barmode="group")
    fig_dorm.update_layout(height=300,margin=dict(l=10,r=10,t=40,b=40))
    st.plotly_chart(fig_dorm, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════
elif "Transaction Activity" in view:
# ══════════════════════════════════════════════════════════════════════
    st.markdown("### 📈 Transaction activity — last 90 days (50,000 sample)")
    txn_df = load_transactions()

    c1,c2 = st.columns(2)
    _daily = txn_df.groupby(txn_df["txn_date"].dt.date).agg(
        Count=("txn_id","count"), Volume=("amount","sum")).reset_index()
    fig_daily = px.line(_daily, x="txn_date", y="Volume",
        title="Daily transaction volume (KES)",
        color_discrete_sequence=["#2563EB"])
    fig_daily.update_layout(height=300,margin=dict(l=10,r=10,t=40,b=30))
    c1.plotly_chart(fig_daily, use_container_width=True)

    _ch = txn_df.groupby("txn_channel")["amount"].sum().reset_index()
    fig_ch = px.pie(_ch, names="txn_channel", values="amount",
        title="Volume by channel",
        color_discrete_sequence=px.colors.qualitative.Pastel, hole=0.35)
    fig_ch.update_layout(height=300,margin=dict(l=0,r=0,t=40,b=0))
    c2.plotly_chart(fig_ch, use_container_width=True)

    _tt = txn_df.groupby("txn_type")["amount"].sum().nlargest(10).reset_index()
    fig_tt = px.bar(_tt, x="txn_type", y="amount",
        title="Top 10 transaction types by volume",
        color="amount", color_continuous_scale="Teal")
    fig_tt.update_layout(height=300,margin=dict(l=10,r=10,t=40,b=80),xaxis_tickangle=-30)
    st.plotly_chart(fig_tt, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════
elif "CIF Lookup" in view:
# ══════════════════════════════════════════════════════════════════════
    st.markdown("### 🔍 Customer 360° — CIF lookup")
    _cif_input = st.text_input("Enter CIF number", placeholder="e.g. 100023456")
    if _cif_input.strip():
        _found_cust = None
        with open(CBS/"customers.csv", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["cif"] == _cif_input.strip():
                    _found_cust = row
                    break
        if _found_cust:
            st.markdown("#### Customer profile")
            _cc = st.columns(4)
            _cc[0].metric("CIF", _found_cust["cif"])
            _cc[1].metric("Name", _found_cust["full_name"][:20])
            _cc[2].metric("Segment", _found_cust["sub_segment"])
            _cc[3].metric("KYC", _found_cust["kyc_status"])
            _cd = st.columns(4)
            _cd[0].metric("Branch", _found_cust["branch_name"][:18])
            _cd[1].metric("Risk", _found_cust["risk_rating"])
            _cd[2].metric("Onboarded", _found_cust["date_onboarded"])
            _cd[3].metric("Last Activity", _found_cust["last_activity_date"])
            st.markdown("#### Accounts")
            _accts = []
            with open(CBS/"accounts.csv", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    if row["cif"] == _cif_input.strip():
                        _accts.append(row)
            if _accts:
                _adf = pd.DataFrame(_accts)
                _disp_cols = [c for c in [
                    "account_number","account_type_name","category","currency",
                    "current_balance","account_status","dormancy_status",
                    "npl_status","date_opened"] if c in _adf.columns]
                for c in ["current_balance"]:
                    if c in _adf.columns:
                        _adf[c] = pd.to_numeric(_adf[c],errors="coerce").apply(
                            lambda x: f"KES {x:,.0f}" if x else "—")
                st.dataframe(_adf[_disp_cols], use_container_width=True, hide_index=True)
            else:
                st.info("No accounts found for this CIF.")
        else:
            st.warning("CIF not found. Try a number between 100000001 and 100700000.")
