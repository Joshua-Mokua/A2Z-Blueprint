"""pages/12_cascade.py — Target Cascade with BSC scorecard format."""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import numpy as np
import plotly.express as px
import datetime as _dt
from utils.core import *
from utils.core import get_fiscal_year as _gfy_casc
from pages._shared import load_shared_state, safe_html
from pages._access import require_access, get_my_scope, tab_visible

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d, timedelta
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()


require_access("cascade")

def _bsc_trigger(username: str, kpi: str = ""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass


try:
    from utils.core import suggest_target, get_bank_growth_trajectory
except ImportError:
    suggest_target = None
    get_bank_growth_trajectory = None


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🎯 Target Cascade</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Bank → SBU → Branch → Individual target setting</span></div>",
    unsafe_allow_html=True)

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
df_proc      = st.session_state.get("df_processed", pd.DataFrame())

role_l  = str(ud.get("role","")).lower()
my_name_l = ud.get("full_name","")
_raw_code  = str(ud.get("staff_code","") or "").strip()

# Always try to resolve the numeric staff code from the BSC data by name
# This handles: (a) account has no staff code, (b) wrong code, (c) username stored
_resolved_code = _raw_code
if not df_proc.empty and "Staff Name" in df_proc.columns and my_name_l:
    # Exact name match first
    name_rows = df_proc[df_proc["Staff Name"] == my_name_l]
    if name_rows.empty:
        # Partial match — try surname
        surname = my_name_l.strip().split()[-1] if my_name_l.strip() else ""
        if surname:
            name_rows = df_proc[df_proc["Staff Name"].str.contains(surname, case=False, na=False)]
    if not name_rows.empty and "Staff Code" in name_rows.columns:
        bsc_code = str(name_rows["Staff Code"].iloc[0]).strip()
        if bsc_code and bsc_code != "nan":
            _resolved_code = bsc_code

my_code = _resolved_code or _raw_code or uname
my_unit = ud.get("unit","")
# Strictly role-based — "director" does NOT grant MD-level access
_is_admin = ud.get("is_admin", False)
is_md   = (_is_admin
           or any(k in role_l for k in ("managing director","md","ceo"))
           or role_l in ("admin","managing director"))
can_all = is_md   # only MD/Admin see everything
is_mgr  = is_md or any(k in role_l for k in (
    "director","head of","head_of","regional head",
    "branch manager","chief","manager"))

if len(staff_scores)==0:
    st.markdown(
        "<div style='padding:48px;text-align:center;background:#F0FDF4;"
        "border-radius:16px;border:2px dashed var(--brand-primary,#006B3F)44;margin:20px 0'>"
        "<div style='font-size:48px'>🎯</div>"
        "<div style='font-size:20px;font-weight:700;color:var(--brand-primary,#006B3F);margin-top:12px'>Target Cascade</div>"
        "<div style='color:var(--color-text-secondary);font-size:14px;margin-top:8px'>Upload BSC data to begin</div></div>",
        unsafe_allow_html=True)
    st.stop()

try:
    from utils.core import CascadeManager
    needs_refresh = (casc is None or
        not all(hasattr(casc,m) for m in
                ["get_fixed_kpis","get_bank_target","is_fixed",
                 "set_cascade_deadline","set_global_timeline","request_review","lock_targets"]))
    if needs_refresh:
        casc = CascadeManager()
        st.session_state["cascade_manager"] = casc
except Exception as ex:
    st.error(f"CascadeManager error: {ex}")
    st.stop()

# Safety patch — if casc is stale and missing methods, add safe no-op versions
# This handles browser sessions that survived before __getattr__ was added
if not callable(getattr(casc, "get_fixed_kpis", None)):
    casc.get_fixed_kpis   = lambda period="": []
if not callable(getattr(casc, "get_fixed_value", None)):
    casc.get_fixed_value  = lambda kpi="", period="": 0.0
if not callable(getattr(casc, "get_bank_target", None)):
    casc.get_bank_target  = lambda kpi="", period="": None
if not callable(getattr(casc, "is_fixed", None)):
    casc.is_fixed         = lambda kpi="", period="": False
if not callable(getattr(casc, "targets_locked", None)):
    casc.targets_locked   = lambda *a, **k: False
if not hasattr(casc, "bank_targets"):
    casc.bank_targets     = {}
if not hasattr(casc, "fixed_kpis"):
    casc.fixed_kpis       = {}
if not hasattr(casc, "cascade"):
    casc.cascade          = {}

# ── CONSTANTS ─────────────────────────────────────────────────────────
# ── Org hierarchy — exact role strings from BSC data ─────────────────
# MD → Directors/Chiefs (direct reports)
# Director Retail Banking → Head Of Retail → Regional Head → Branch Manager
# Branch Manager → Branch Operations Manager + Branch Credit Manager
# Branch Operations Manager → Teller + Customer Service Officer
# Branch Credit Manager → Relationship Officer Personal Banking + Direct Sales Officer
# Load hierarchy from org config (admin-configurable), fall back to hardcoded
try:
    from utils.core import get_org_config as _get_org
    _org_hier = _get_org().get("hierarchy", {})
    # Convert {role: [parents]} → {role: [children]} for cascade use
    _HIER_CHILDREN = {}
    for _role, _parents in _org_hier.items():
        if _role not in _HIER_CHILDREN:
            _HIER_CHILDREN[_role] = []
        for _parent in _parents:
            _HIER_CHILDREN.setdefault(_parent, [])
            if _role not in _HIER_CHILDREN[_parent]:
                _HIER_CHILDREN[_parent].append(_role)
    if _HIER_CHILDREN:
        HIERARCHY = _HIER_CHILDREN
    else:
        raise ValueError("Empty hierarchy")
except Exception:
    HIERARCHY = {
    "Managing Director": [
        "Director Retail Banking", "Director Commercial Banking",
        "Chief Finance Officer", "Chief Risk Officer", "Chief Operations Officer",
        "Chief Compliance Officer", "Chief Human Resources Officer",
        "Head Of Strategy", "Head Of Internal Audit", "Head Of Marketing",
        "Head Of Digital Innovation", "Debt Recovery Unit Manager",
    ],
    "Director Retail Banking": ["Head Of Retail", "Regional Head"],
    "Director Commercial Banking": ["Head Of SME", "Head Of Corporate"],
    "Head Of Retail": ["Regional Head"],
    "Head Of Corporate": ["Relationship Manager Corporate"],
    "Head Of SME": ["Relationship Manager SME"],
    "Head Of Digital Innovation": ["IT Manager"],
    "Head Of Strategy": ["Strategy Analyst"],
    "Head Of Internal Audit": ["Internal Auditor"],
    "Head Of Marketing": ["Marketing Officer"],
    "Chief Finance Officer": ["Financial Controller", "Treasury Manager"],
    "Chief Risk Officer": ["Risk Manager"],
    "Chief Operations Officer": ["Operations Manager"],
    "Chief Compliance Officer": ["Compliance Officer"],
    "Chief Human Resources Officer": ["HR Business Partner", "HR Officer"],
    "Chief Credit Officer": ["Credit Analyst", "Credit Administrator"],
    "Debt Recovery Unit Manager": ["Recovery Officer"],
    "Procurement Manager": ["Procurement Officer"],
    "Regional Head": ["Branch Manager"],
    "Branch Manager": ["Branch Operations Manager", "Branch Credit Manager"],
    "Branch Operations Manager": [
        "Teller", "Customer Service Officer",
        "Branch Operations Supervisor",
    ],
    "Branch Credit Manager": [
        "Relationship Officer Personal Banking",
        "Relationship Officer Business Banking",
        "Direct Sales Officer",
    ],
    "IT Manager": ["IT Support Officer"],
    "Operations Manager": ["Branch Operations Manager"],
}  # end fallback HIERARCHY

# Role → exact data role name mapping (for my_role_level lookup)
ROLE_MAP = {
    "managing director":          "Managing Director",
    "director retail banking":    "Director Retail Banking",
    "director commercial banking":"Director Commercial Banking",
    "head of retail":             "Head Of Retail",
    "head of corporate":          "Head Of Corporate",
    "head of sme":                "Head Of SME",
    "head of digital innovation": "Head Of Digital Innovation",
    "head of strategy":           "Head Of Strategy",
    "head of internal audit":     "Head Of Internal Audit",
    "head of marketing":          "Head Of Marketing",
    "chief finance officer":      "Chief Finance Officer",
    "chief risk officer":         "Chief Risk Officer",
    "chief operations officer":   "Chief Operations Officer",
    "chief compliance officer":   "Chief Compliance Officer",
    "chief human resources officer": "Chief Human Resources Officer",
    "chief credit officer":       "Chief Credit Officer",
    "debt recovery unit manager": "Debt Recovery Unit Manager",
    "procurement manager":        "Procurement Manager",
    "regional head":              "Regional Head",
    "branch manager":             "Branch Manager",
    "branch operations manager":  "Branch Operations Manager",
    "branch credit manager":      "Branch Credit Manager",
    "it manager":                 "IT Manager",
    "operations manager":         "Operations Manager",
    "branch operations supervisor": "Branch Operations Supervisor",
    "relationship officer business banking": "Relationship Officer Business Banking",
    "relationship officer personal banking": "Relationship Officer Personal Banking",
    "direct sales officer":       "Direct Sales Officer",
    "customer service officer":   "Customer Service Officer",
    "teller":                     "Teller",
    # Bank-specific roles (configurable via Admin)
    "chief executive & managing director": "Chief Executive & Managing Director",
    "chief retail banking officer":        "Chief Retail Banking Officer",
    "chief commercial officer":            "Chief Commercial Officer",
    "chief financial officer":             "Chief Financial Officer",
    "chief credit officer":                "Chief Credit Officer",
    "chief risk officer":                  "Chief Risk Officer",
    "chief information officer":           "Chief Information Officer",
    "chief operating officer":             "Chief Operating Officer",
    "chief human resource officer":        "Chief Human Resource Officer",
    "company secretary and chief legal officer": "Company Secretary and Chief Legal Officer",
    "area manager":                        "Area Manager",
    "head of branches":                    "Head of Branches",
    "branch senior relationship officer":  "Branch Senior Relationship Officer",
    "senior digital channels officer":     "Senior Digital Channels Officer",
    "branch relationship manager":         "Branch Relationship Manager",
    "relationship officer-business banker":"Relationship Officer-Business Banker",
    "relationship officer-personal banker":"Relationship Officer-Personal Banker",
    "direct sales representative - assets & liabilities": "Direct Sales Representative - Assets & Liabilities",
    "relationship officer bancassurance":  "Relationship Officer Bancassurance",
    "general manager - bancassurance":     "General Manager - Bancassurance",
    "head of msme":                        "Head of MSME",
    "head of digital financial services":  "Head of Digital Financial Services",
}

LEVEL_ORDER = [
    "Managing Director",
    "Director Retail Banking", "Director Commercial Banking",
    "Head Of Retail", "Head Of Corporate", "Head Of SME",
    "Head Of Digital Innovation", "Chief Finance Officer", "Chief Risk Officer",
    "Chief Operations Officer", "Chief Compliance Officer", "Chief Human Resources Officer",
    "Regional Head", "Branch Manager",
    "Branch Operations Manager", "Branch Credit Manager",
    "Branch Operations Supervisor",
    "Teller", "Customer Service Officer",
    "Relationship Officer Personal Banking",
    "Relationship Officer Business Banking",
    "Direct Sales Officer",
]
PILLARS = ["Financial","Customer Focus","Operational Excellence","People & Learning"]
PC  = {"Financial":"var(--brand-primary,#006B3F)","Customer Focus":"#185FA5",
       "Operational Excellence":"#8E44AD","People & Learning":"#D97706"}
PI  = {"Financial":"💰","Customer Focus":"🤝",
       "Operational Excellence":"⚙️","People & Learning":"🎓"}
# Pillar weights — configurable via Admin → KPI Library
PILLAR_WEIGHTS = {
    "Financial":0.66,"Customer Focus":0.22,
    "Operational Excellence":0.07,"People & Learning":0.05,
}
PCT_KPIS = {
    "CIR","NPL Ratio","PAR","Capital Adequacy Ratio","Liquidity Ratio","ROE","NIM","LDR",
    "Diligence Score","NPS Score","SLA Adherence Score","CX Score","Compliance",
    "AML SAR Filing Rate","Audit Coverage Rate","Audit Closure","Branch Optimization Score",
    "Regulatory Compliance Score","Regulatory Reporting Timeliness","Training Completion Rate",
    "Staff Retention Rate","Strategic Initiative Completion Rate","Complaint Resolution Rate",
    "System Uptime","Recovery Rate","Case Resolution Rate","Timely Reconciliations",
    "Incident Resolution Rate","Procurement TAT","Credit TAT Score","Digital Transaction Migration",
    "Campaign Conversion Rate","Credit Approval TAT","Staff Productivity","Diligence Score","CASA Ratio","CX Score","PAR","Account Dormancy","Channel Dormancy",
}

# KPIs that are always financial amounts (KES) — never treat as percentage
KES_KPIS = {
    "Disbursements Corporate Loans","Disbursements Retail Loans","Disbursements MSME Loans",
    "Loans Disbursement","Loan Book Growth","Retail & MSME Deposit Growth",
    "Commercial Deposit Growth","Deposit Growth","Total NFI","Fees and Commission","PBT",
    "Top 100 Customers Deposit","Collection Throughput","Trade Finance",
    "Treasury Revenue","Bancassurance","DFS Revenue",
}

def is_pct(k):
    if k in KES_KPIS: return False   # always KES — never %
    return k in PCT_KPIS or any(x in k.lower() for x in ("ratio"," rate","score","margin","uptime","tat","%"))

# KPIs where LOWER is better — buffer REDUCES the target (tightens it)
REDUCE_KPIS = {
    "CIR","NPL Ratio","PAR","Account Dormancy","Channel Dormancy","Regression to NPL",
    "Complaint Resolution Rate","AML SAR Filing Rate",
}
def is_reduce(k):
    """True if lower value = better performance (buffer tightens the target)."""
    return (k in REDUCE_KPIS or
            any(x in k.lower() for x in ("npl","par","cir","cost","complaint","aml","overdue")))

# Average-type KPIs — the bank target is a rate/ratio, NOT a sum to distribute.
# Each person gets their OWN individual target. Allocation = setting per-person target.
# The bank total = average of individual targets, not their sum.
AVG_KPIS = {
    "NPL Ratio","CIR","PAR","ROE","ROA","NPS Score","CX Score",
    "SLA Adherence Score","Credit TAT Score","Complaint Resolution Rate",
    "Digital Transaction Migration","Staff Retention Rate","Training Completion Rate",
    "Audit Closure","Regulatory Compliance Score","AML SAR Filing Rate",
    "Diligence Score","Initiative Score","Ideation Score",
    "Strategic Initiative Completion Rate","Branch Optimization Score",
    "Campaign Conversion Rate","Credit Approval TAT","Incident Resolution Rate",
    "Recovery Rate","System Uptime","Procurement TAT","Regulatory Reporting Timeliness",
    "Employee Satisfaction Score","Audit Coverage Rate","Case Resolution Rate","Staff Productivity","CX Score",
    "Capital Adequacy Ratio","Liquidity Ratio","Timely Reconciliations",
    "Compliance","Digital Active Customers",
}
def is_avg_kpi(k):
    """True if KPI is a rate/ratio — each person gets individual target (no pooled sum)."""
    return (k in AVG_KPIS or
            any(x in k.lower() for x in
                ("ratio","rate","score","margin","uptime","tat","closure",
                 "completion","retention","resolution","migration","coverage")))

# Count-type KPIs — measured as whole numbers (units, accounts, transactions)
# NOT in KES — format as plain integers
COUNT_KPIS = {
    "Transactions", "New Customer Acquisition", "Dormancy Reactivation",
    "Cards Issued", "Bancassurance", "Loans Referred",
    "New Accounts", "Number of Business Borrowers",
    "Active Initiatives Count", "Number of New Customers",
}
def is_count_kpi(k):
    """True if KPI is a count/volume — display as integer, not KES."""
    return (k in COUNT_KPIS or
            any(x in k.lower() for x in
                ("accounts opened","transactions processed","cards issued",
                 "registrations","referred","reactivat","acquisition",
                 "number of","borrower","initiatives count","new accounts")))

def fmt_v(v, kpi=""):
    """Format value with proper commas and units based on KPI type."""
    if v is None or (isinstance(v,float) and (np.isnan(v) or v==0)): return "—"
    if is_pct(kpi):
        display = v * 100 if abs(v) <= 1.5 else v
        return f"{display:,.2f}%"
    # Count KPIs — whole number, no KES prefix
    if is_count_kpi(kpi):
        return f"{int(round(v)):,}"
    # Financial values — KES prefix with scale
    if abs(v) >= 1_000_000_000: return f"KES {v/1e9:,.3f}B"
    if abs(v) >= 1_000_000:     return f"KES {v/1e6:,.2f}M"
    if abs(v) >= 1_000:         return f"KES {v:,.0f}"
    return f"{v:,.4f}"

def fmt_input_hint(kpi):
    """Show format hint below number inputs."""
    if is_pct(kpi):     return "Enter as decimal (e.g. 0.06 for 6%)"
    if is_count_kpi(kpi): return "Enter as count (e.g. 250 transactions)"
    return "Enter in KES (e.g. 50000000 for KES 50M)"

def kpi_step(k):
    if is_pct(k): return 0.005
    if is_count_kpi(k): return 1.0        # count KPIs: step by 1
    if any(x in k.lower() for x in ("growth","disburs","deposit","loan","asset",
                                     "income","pbt","revenue","treasury","trade","fee",
                                     "commission","acquiring")): return 1_000_000.0
    if any(x in k.lower() for x in ("transactions","customer","complaints")): return 100.0
    return 500_000.0

def get_pillar(k):
    if df_proc.empty or "Pillar" not in df_proc.columns: return "Financial"
    r = df_proc[df_proc["KPI"]==k]["Pillar"]
    return r.iloc[0] if len(r) else "Financial"

def score_color(pct):
    if pct>=100: return "var(--brand-primary,#006B3F)"
    if pct>=90:  return "var(--brand-mid,#1D9E75)"
    if pct>=70:  return "#F5A623"
    if pct>=50:  return "#E67E22"
    return "#E24B4A"

def get_reports(role, unit=None):
    # Try exact role key, then case-insensitive match
    sub = HIERARCHY.get(role,[])
    if not sub:
        for k,v in HIERARCHY.items():
            if k.lower() == str(role).lower():
                sub = v; break
    if not sub or len(staff_scores)==0: return pd.DataFrame()
    mask = staff_scores["Role"].isin(sub)
    if unit: mask = mask & (staff_scores["Unit"]==unit)
    result = staff_scores[mask].copy()
    # For top-level roles: deduplicate — keep one row per Staff Name
    _top_roles = {"Managing Director","Chief Executive & Managing Director"}
    if role in _top_roles and len(result):
        result = result.drop_duplicates(subset=["Staff Name","Role"]).copy()
    return result

def my_role_level():
    """Return the exact HIERARCHY key matching the logged-in user's role."""
    # 1. Exact match via ROLE_MAP
    exact = ROLE_MAP.get(role_l.strip())
    if exact and exact in HIERARCHY:
        return exact
    # 2. Exact match directly in HIERARCHY keys
    for lvl in HIERARCHY:
        if lvl.lower() == role_l.strip():
            return lvl
    # 3. Partial fallbacks
    # MD/CEO — find the actual key in HIERARCHY (may be "Chief Executive & Managing Director")
    if "managing" in role_l or "chief executive" in role_l or role_l in ("md","ceo","admin"):
        # Find the top-level key dynamically — no hardcoded name
        roots = [k for k, v in HIERARCHY.items() if not v]
        if roots: return roots[0]
        for k in HIERARCHY:
            if "managing" in k.lower() or "chief executive" in k.lower(): return k
    # Fuzzy match against actual HIERARCHY keys — never hardcode role names
    for k in HIERARCHY:
        kl = k.lower()
        # Match on significant words (4+ chars) to avoid false positives
        words = [w for w in role_l.split() if len(w) >= 4]
        if words and all(w in kl for w in words[:2]):
            return k
    # Admin sees the root role
    if can_all:
        roots = [k for k, v in HIERARCHY.items() if not v]
        return roots[0] if roots else None
    return None

def is_new_hire(name):
    reg = st.session_state.get("staff_registry",{})
    if isinstance(reg,dict):
        for _,info in reg.items():
            if info.get("Staff Name","")==name:
                return str(info.get("Staff Status","")).lower()=="new"
    return False

def get_prior(name, kpi):
    if df_proc.empty: return 0.0, 0.0
    rows = df_proc[(df_proc["Staff Name"]==name)&(df_proc["KPI"]==kpi)]
    if rows.empty: return 0.0, 0.0
    r   = rows.iloc[0]
    tgt = float(pd.to_numeric(r.get("Annual Target",0),errors="coerce") or 0)
    fy25= 0.0
    for col in ["FY-25 Actual","FY25 Actual","Annual Actual"]:
        if col in r.index:
            fy25 = float(pd.to_numeric(r.get(col,0),errors="coerce") or 0)
            if fy25>0: break
    return fy25, tgt

def pct_change_label(new_val, old_val):
    """Return formatted % change from prior year target."""
    if not old_val or not new_val: return "—"
    chg = (new_val - old_val) / abs(old_val) * 100
    clr = "var(--brand-primary,#006B3F)" if chg>=0 else "#E24B4A"
    arrow = "▲" if chg>=0 else "▼"
    return f"<span style='color:{clr};font-size:11px;font-weight:600'>{arrow} {abs(chg):.1f}%</span>"

# Build from loaded data; always ensure real bank BSC KPIs are present
all_kpis = sorted(df_proc["KPI"].unique().tolist()) if not df_proc.empty and "KPI" in df_proc.columns else []
kpis_by_pillar: dict = {}
for k in all_kpis:
    kpis_by_pillar.setdefault(get_pillar(k),[]).append(k)
# Ensure all 18 real BSC KPIs appear in cascade even before data loads
_REAL_KPIS = {
    "Financial": ["PBT","Deposit Growth","CASA Ratio","Loans Disbursement","Loan Book Growth",
                  "NPL Ratio","Fees and Commission","DFS Revenue","Trade Finance",
                  "Treasury Revenue","Bancassurance"],
    "Customer Focus": ["New Customer Acquisition","CX Score","Digital Active Customers",
                       "Ecosystem Banking"],
    "Operational Excellence": ["Compliance Score","Audit Score"],
    "People & Learning": ["Diligence Score"],
}
for _rp, _rks in _REAL_KPIS.items():
    for _rk in _rks:
        if _rk not in kpis_by_pillar.get(_rp,[]):
            kpis_by_pillar.setdefault(_rp,[]).append(_rk)
period=_gfy_casc()
fixed_kpis = casc.get_fixed_kpis(period)

# ── PAGE HEADER ───────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 22px;background:var(--brand-primary,#006B3F);border-radius:12px;"
    "margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)'>"
    "<div style='display:flex;align-items:center;justify-content:space-between'>"
    "<div><div style='color:var(--color-background-primary);font-size:16px;font-weight:700'>🎯 Target Cascade</div>"
    "<div style='color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px'>"
    "Set bank targets → Lock fixed KPIs → Allocate to team → Staff accept & track"
    "</div></div>"
    "<div style='opacity:0.12;font-size:36px;color:var(--color-background-primary)'>◆</div>"
    "</div></div>", unsafe_allow_html=True)

# Global timeline status bar
tl = casc.get_global_timeline(period)
if tl:
    ta = casc.time_remaining_analysis(period)
    days_rem = ta.get("days_remaining", 0)
    clr = "var(--brand-primary,#006B3F)" if days_rem and days_rem>14 else ("#F5A623" if days_rem and days_rem>0 else "#E24B4A")
    msg = (f"⏰ Cascade end: {tl['cascade_end_date']} · "
           f"{'🔴 Overdue' if ta['is_overdue'] else f'{days_rem}d remaining'}")
    st.markdown(
        f"<div style='padding:7px 14px;background:{clr}18;border:1px solid {clr}44;"
        f"border-radius:8px;margin-bottom:12px;font-size:12px;font-weight:600;color:{clr}'>"
        f"{msg}</div>", unsafe_allow_html=True)

# Build tab list based on role — hide tabs the user can't use
_tab_defs = [
    ("🏦 Bank targets & timeline", "bank_targets"),
    ("🔒 Fixed KPIs",              "fixed_kpis"),
    ("🎯 Set team targets",        "set_targets"),
    ("📊 My targets",              "my_targets"),
    ("🌳 Cascade tree",            "cascade_tree"),
    ("✅ Coverage & deadlines",    "coverage"),
    ("🔍 Review requests",         "review_requests"),
]
_visible_tabs = [(label, key) for label, key in _tab_defs if tab_visible(ud, key)]
_tab_labels   = [label for label, _ in _visible_tabs]
_tab_keys     = [key   for _, key   in _visible_tabs]
tabs = st.tabs(_tab_labels)

# Tab content guards — only render if tab is in visible set
def _in_tab(key):
    """Returns (visible: bool, tab_index: int)."""
    return key in _tab_keys, (_tab_keys.index(key) if key in _tab_keys else -1)

# ══════════════════════════════════════════════════════════════════
# TAB 1 — BANK TARGETS + MASTER TIMELINE
# ══════════════════════════════════════════════════════════════════
_tab_visible_bank_targets, _tab_idx_bank_targets = _in_tab("bank_targets")
if _tab_visible_bank_targets:
  with tabs[_tab_idx_bank_targets]:
    if not tab_visible(ud,"bank_targets") or not is_md:
        st.info("Bank-level targets and timeline are set by the MD / Admin only.")

    # ── MASTER CASCADE TIMELINE ──────────────────────────────────
    st.markdown(
        "<div style='padding:12px 16px;background:#FEF3C7;border:1px solid #FDE68A;"
        "border-radius:10px;margin-bottom:16px'>"
        "<b style='color:#92400E'>⏰ Step 0 — Set the master cascade timeline</b><br>"
        "<span style='font-size:12px;color:#78350F'>"
        "Define the end date by which the entire cascade must reach every staff member. "
        "Set expected windows per level. The system will reject any deadline set outside these windows."
        "</span></div>", unsafe_allow_html=True)

    existing_tl = casc.get_global_timeline(period)
    today = _dt.date.today()

    with st.expander("⏰ Configure master cascade timeline", expanded=not bool(existing_tl)):
        tl_c1, tl_c2 = st.columns(2)
        cascade_end = tl_c1.date_input(
            "🏁 Full bank cascade must complete by",
            value=(_safe_date(existing_tl["cascade_end_date"])
                   if existing_tl else today + _dt.timedelta(days=30)),
            min_value=today,
            key="tl_end",
            help="No individual deadline can be set beyond this date")

        tl_c2.markdown(
            "<div style='padding:10px;background:var(--color-background-secondary);border-radius:8px;font-size:11px;color:var(--color-text-secondary)'>"
            f"Today: <b>{today}</b><br>"
            f"Days to cascade end: <b>{(cascade_end-today).days}</b><br>"
            f"Levels to cascade through: <b>{len(LEVEL_ORDER)}</b><br>"
            f"Avg days per level: <b>{(cascade_end-today).days//max(len(LEVEL_ORDER),1):.1f}</b>"
            "</div>", unsafe_allow_html=True)

        st.markdown("**Expected window per management level:**")
        levels_cfg = []
        existing_levels = {l["role"]:l for l in (existing_tl.get("levels",[]) if existing_tl else [])}
        mgr_levels = [l for l in LEVEL_ORDER if l in HIERARCHY]

        for lvl in mgr_levels:
            ex = existing_levels.get(lvl,{})
            default_conf = (_safe_date(ex.get("confirm_by", ""))
                            if ex.get("confirm_by") else today+_dt.timedelta(days=5))
            default_casc = (_safe_date(ex.get("cascade_by", ""))
                            if ex.get("cascade_by") else today+_dt.timedelta(days=12))
            lc1,lc2,lc3 = st.columns([2,1,1])
            lc1.markdown(f"<div style='padding:8px 0;font-size:12px;font-weight:600'>{lvl}</div>",
                         unsafe_allow_html=True)
            c_by = lc2.date_input("Confirm by", value=default_conf,
                                   min_value=today, max_value=cascade_end,
                                   key=f"tl_conf_{lvl}", label_visibility="collapsed")
            k_by = lc3.date_input("Cascade by", value=default_casc,
                                   min_value=today, max_value=cascade_end,
                                   key=f"tl_casc_{lvl}", label_visibility="collapsed")
            levels_cfg.append({"role":lvl,"confirm_by":str(c_by),"cascade_by":str(k_by)})

        if st.button("💾 Save master cascade timeline", type="primary"):
            casc.set_global_timeline(period, str(cascade_end), levels_cfg, uname)
            audit_log("CASCADE_TIMELINE", uname, f"{period}|end:{cascade_end}")
            _bsc_trigger(uname, "K017")
            st.toast(f"✅ Master timeline set — cascade ends {cascade_end}", icon="⏰")
            st.cache_data.clear()
            st.rerun()

    if existing_tl:
        st.markdown(
            f"<div style='padding:10px 14px;background:#F0FDF4;border:1px solid #BBF7D0;"
            f"border-radius:8px;font-size:12px'>"
            f"✅ Timeline set: cascade must complete by <b>{existing_tl['cascade_end_date']}</b> "
            f"· {len(existing_tl.get('levels',[]))} levels configured"
            f"</div>", unsafe_allow_html=True)

    st.markdown("---")

    # ── BANK KPI TARGETS ─────────────────────────────────────────
    st.markdown(
        "<div style='padding:10px 14px;background:#F0FDF4;border:1px solid #BBF7D0;"
        "border-radius:8px;margin-bottom:12px;font-size:12px;color:#166534'>"
        "<b>Step 1 — Set bank targets.</b> "
        "Enter target for each KPI. Add a buffer % — directors receive the stretch figure. "
        "FY-25 achievement is shown to anchor each target in evidence."
        "</div>", unsafe_allow_html=True)

    _, hc2 = st.columns([5,1])
    t_period = hc2.selectbox("Period",[_gfy_casc(),"2025"],key="bank_period")

    for pillar in PILLARS:
        kpis_p = kpis_by_pillar.get(pillar,[])
        if not kpis_p: continue
        pclr = PC[pillar]; picon = PI[pillar]

        st.markdown(
            f"<div style='display:flex;align-items:center;gap:10px;padding:10px 16px;"
            f"background:{pclr};border-radius:10px;margin:18px 0 4px'>"
            f"<span style='font-size:16px'>{picon}</span>"
            f"<span style='color:var(--color-background-primary);font-weight:700;font-size:13px'>{pillar}</span>"
            f"<span style='color:rgba(255,255,255,0.55);font-size:11px'>"
            f"— {len(kpis_p)} KPIs</span></div>", unsafe_allow_html=True)

        # Column headers
        st.markdown(
            "<div style='display:grid;"
            "grid-template-columns:2.2fr 1fr 0.8fr 0.5fr 1.4fr 0.9fr 1.2fr 0.8fr;gap:6px;"
            "padding:5px 14px;background:var(--color-background-secondary);border-radius:6px;"
            "font-size:10px;font-weight:700;color:var(--color-text-secondary);"
            "text-transform:uppercase;letter-spacing:0.4px;margin-bottom:2px'>"
            "<span>KPI</span><span>FY-25 Actual</span><span>FY-25 %</span>"
            "<span>Wt</span><span>2026 Target</span><span>Buffer %</span>"
            "<span>Stretch</span><span></span></div>", unsafe_allow_html=True)

        for kpi in kpis_p:
            existing = casc.get_bank_target(kpi, t_period)
            cur_tgt  = existing.get("target", 0.0)  if existing else 0.0
            cur_buf  = existing.get("buffer_pct", 0.0) if existing else 0.0
            is_fix   = kpi in fixed_kpis; pct_kpi = is_pct(kpi)

            kpi_rows = df_proc[df_proc["KPI"]==kpi] if not df_proc.empty else pd.DataFrame()
            fy25_total=0.0; tgt26_total=0.0; wt_avg=0.0
            if not kpi_rows.empty:
                for col in ["FY-25 Actual","FY25 Actual","Annual Actual"]:
                    if col in kpi_rows.columns:
                        fy25_total=float(pd.to_numeric(kpi_rows[col],errors="coerce").sum() or 0)
                        if fy25_total>0: break
                tgt26_total=float(pd.to_numeric(kpi_rows["Annual Target"],errors="coerce").sum() or 0)
                wt_avg=float(pd.to_numeric(kpi_rows["Weight"],errors="coerce").mean() or 0)
            fy25_pct = round(fy25_total/tgt26_total*100,1) if tgt26_total else 0
            pct_clr  = score_color(fy25_pct) if fy25_pct else "#9CA3AF"
            _direction  = -1 if is_reduce(kpi) else 1
            cur_stretch = round(cur_tgt*(1+_direction*cur_buf/100),2) if (cur_tgt and cur_buf) else cur_tgt
            row_bg = "#FFFBEB" if is_fix else "var(--color-background-primary)"

            st.markdown(
                f"<div style='display:grid;"
                f"grid-template-columns:2.2fr 1fr 0.8fr 0.5fr 1.4fr 0.9fr 1.2fr 0.8fr;"
                f"gap:6px;padding:6px 14px;background:{row_bg};"
                f"border:1px solid #F0F0F0;border-radius:8px;margin:2px 0;"
                f"align-items:center;font-size:12px'>"
                f"<span style='font-weight:600;color:var(--color-text-primary)'>{kpi}{'&nbsp;🔒' if is_fix else ''}</span>"
                f"<span style='color:var(--color-text-primary)'>{fmt_v(fy25_total,kpi) if fy25_total else '—'}</span>"
                f"<span style='color:{pct_clr};font-weight:700'>{'—' if not fy25_pct else f'{fy25_pct:.1f}%'}</span>"
                f"<span style='color:var(--color-text-tertiary)'>{wt_avg*100:.0f}%</span>"
                f"<span></span><span></span>"
                f"<span style='color:#F5A623;font-weight:600'>{fmt_v(cur_stretch,kpi) if cur_stretch else '—'}</span>"
                f"<span></span></div>", unsafe_allow_html=True)

            ic = st.columns([2.2,1,0.8,0.5,1.4,0.9,1.2,0.8])

            # ── Target input — text for comma-formatted large numbers ─
            # Use text_input for ALL targets — supports commas, no max_value issues
            _tgt_raw_key = f"btraw_{kpi}_{t_period}"
            # Pre-fill from saved value ONLY on first render (not on every rerender)
            if _tgt_raw_key not in st.session_state:
                if pct_kpi:
                    st.session_state[_tgt_raw_key] = f"{cur_tgt:.2f}" if cur_tgt else ""
                else:
                    st.session_state[_tgt_raw_key] = f"{cur_tgt:,.0f}" if cur_tgt else ""
            _placeholder = "e.g. 78.50%" if pct_kpi else "e.g. 2,000,000,000"
            _tgt_typed = ic[4].text_input(
                "Target", key=_tgt_raw_key,
                label_visibility="collapsed", placeholder=_placeholder)
            try:
                new_tgt = float(str(_tgt_typed).replace(",","").replace(" ","") or 0)
            except (ValueError, TypeError):
                new_tgt = cur_tgt

            # ── Buffer — with direction indicator ─────────────────────
            _reduce = is_reduce(kpi)
            _buf_help = ("Buffer REDUCES target (lower=better KPI)" if _reduce
                         else "Buffer ADDS to target as stretch")
            new_buf = ic[5].number_input(
                "Buf%", value=float(cur_buf), min_value=0.0, max_value=50.0,
                step=0.5, format="%.1f", key=f"bb_{kpi}_{t_period}",
                label_visibility="collapsed", help=_buf_help)
            # Show direction indicator
            if new_buf > 0:
                _arrow = "↓" if _reduce else "↑"
                _col   = "#185FA5" if _reduce else "var(--brand-primary,#006B3F)"
                ic[5].markdown(
                    f"<div style='font-size:9px;color:{_col};text-align:center;"
                    f"margin-top:-8px'>{_arrow} tightens</div>" if _reduce else
                    f"<div style='font-size:9px;color:{_col};text-align:center;"
                    f"margin-top:-8px'>{_arrow} stretches</div>",
                    unsafe_allow_html=True)

            if ic[7].button("💾", key=f"sv_{kpi}_{t_period}", help="Save target"):
                casc.set_bank_target(kpi, t_period, float(new_tgt), float(new_buf))
                audit_log("BANK_TARGET", uname, f"{kpi}|{t_period}|{new_tgt}")
                _bsc_trigger(uname, "K017")
                st.toast(f"✅ {kpi}: {fmt_v(new_tgt,kpi)}", icon="✅")
                st.cache_data.clear()
                st.rerun()

    saved_all = {k:v for k,v in (getattr(casc,"bank_targets",{}) or {}).items() if k.endswith(f"|{t_period}")}
    if saved_all:
        st.markdown("---")
        sv1,sv2,sv3,sv4 = st.columns(4)
        sv1.metric("KPIs set", len(saved_all))
        sv2.metric("With buffer", sum(1 for v in saved_all.values() if v.get("buffer_pct",0)>0))
        sv3.metric("Fixed KPIs", len(fixed_kpis))
        sv4.metric("Timeline set", "✅" if existing_tl else "❌ Not set")

    # ── KPI Weight Editor (MD only) ────────────────────────────────
    with st.expander("⚖️ Adjust KPI weights for Financial KPIs", expanded=False):
        st.caption(
            "Fine-tune the weight each Financial KPI carries in the MD BSC. "
            "Weights across ALL pillars must total 100%. "
            "Changes are saved to the KPI library and apply to all roles.")
        try:
            from utils.core_kpi import get_kpi_library, save_kpi_library
            _wlib = get_kpi_library()
            _wkpi_weights = _wlib.get("kpi_weights", {})
            _wpillars     = _wlib.get("pillars", {})
            _wpillar_wts  = _wlib.get("pillar_weights", {
                "Financial":0.40,"Customer Focus":0.25,
                "Operational Excellence":0.25,"People & Learning":0.10})

            with st.form("kpi_weight_editor_form"):
                st.markdown("**Pillar weights (must total 100%)**")
                _pwc = st.columns(4)
                _new_pw = {}
                _pw_tot = 0
                for _pi2, (_pn2, _pw2) in enumerate(_wpillar_wts.items()):
                    _pv2 = int(_pw2*100) if _pw2<=1.0 else int(_pw2)
                    _nv2 = _pwc[_pi2].number_input(_pn2, 0, 100, _pv2,
                        key=f"wpil_{_pn2}")
                    _new_pw[_pn2] = _nv2/100; _pw_tot += _nv2
                _ptclr = "#10B981" if _pw_tot==100 else "#EF4444"
                st.markdown(
                    f"<div style='color:{_ptclr};font-weight:700;font-size:12px'>"
                    f"Pillar total: {_pw_tot}% {'✅' if _pw_tot==100 else '❌'}</div>",
                    unsafe_allow_html=True)

                st.markdown("**Financial KPI weights** (within Financial pillar)")
                _fin_kpis = _wpillars.get("Financial",[])
                _new_kw   = dict(_wkpi_weights)
                _fin_cols = st.columns(3)
                _fin_tot  = 0
                for _fi, _fk in enumerate(_fin_kpis):
                    _fw_cur = _wkpi_weights.get(_fk["id"], _fk.get("default_weight",0.10))
                    _fw_pct = int(_fw_cur*100) if _fw_cur<=1.0 else int(_fw_cur)
                    _fw_new = _fin_cols[_fi%3].number_input(
                        _fk["name"][:20], 0, 100, _fw_pct, key=f"wkpi_{_fk['id']}")
                    _new_kw[_fk["id"]] = _fw_new/100
                    _fin_tot += _fw_new
                _ftclr = "#10B981" if _fin_tot==100 else "#F59E0B"
                st.markdown(
                    f"<div style='color:{_ftclr};font-size:11px;margin-top:4px'>"
                    f"Financial KPI total: {_fin_tot}% (should = 100% within Financial pillar)</div>",
                    unsafe_allow_html=True)

                if st.form_submit_button("💾 Save weights", type="primary"):
                    if _pw_tot == 100:
                        _wlib["pillar_weights"] = _new_pw
                        _wlib["kpi_weights"]    = _new_kw
                        save_kpi_library(_wlib)
                        st.success("✅ KPI weights saved — BSC will reflect on next load.")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Pillar weights must total 100% before saving.")
        except Exception as _we:
            st.warning(f"Could not load KPI library: {_we}")

    # ── Monthly Target Distribution ────────────────────────────────
    with st.expander("📅 Monthly target distribution", expanded=False):
        st.caption(
            "Choose how annual targets are divided into monthly targets per KPI. "
            "Equal = divide by 12. Seasonal = apply a pattern that reflects business cycles.")

        _dist_kpis = [k.split("|")[0] for k in saved_all.keys()] if saved_all else []
        if not _dist_kpis:
            st.info("Set and save bank targets above first.")
        else:
            # Load existing distribution settings
            _dist_file = DATA_DIR / "target_distribution.json"
            _dist_cfg  = {}
            try:
                if _dist_file.exists():
                    _dist_cfg = a2z_db.load_json(_dist_file)
            except: pass

            # Month labels
            _months = ["Jan","Feb","Mar","Apr","May","Jun",
                       "Jul","Aug","Sep","Oct","Nov","Dec"]

            # Seasonal patterns
            _patterns = {
                "Equal (÷12)":    [1/12]*12,
                "Q4 heavy":       [0.05,0.06,0.07,0.08,0.08,0.08,0.08,0.08,0.09,0.10,0.12,0.11],
                "Q1 heavy":       [0.12,0.11,0.10,0.09,0.08,0.08,0.07,0.07,0.08,0.08,0.07,0.05],
                "Mid-year surge": [0.06,0.07,0.08,0.09,0.10,0.12,0.12,0.10,0.09,0.08,0.05,0.04],
                "Custom":         None,
            }

            _sel_kpi_d = st.selectbox("Select KPI to configure", _dist_kpis, key="dist_kpi_sel")
            _cur_dist  = _dist_cfg.get(_sel_kpi_d, {"pattern":"Equal (÷12)","weights":[1/12]*12})
            _sel_pat   = st.radio("Distribution pattern",
                list(_patterns.keys()),
                index=list(_patterns.keys()).index(_cur_dist.get("pattern","Equal (÷12)"))
                if _cur_dist.get("pattern") in _patterns else 0,
                horizontal=True, key="dist_pat")

            if _sel_pat == "Custom":
                st.markdown("**Enter % per month (must total 100%)**")
                _cust_cols = st.columns(6)
                _cust_wts  = []
                _cur_cust  = _cur_dist.get("weights",[1/12]*12)
                for _mi, _mn in enumerate(_months):
                    _cv = round((_cur_cust[_mi] if _mi < len(_cur_cust) else 1/12)*100, 1)
                    _nv = _cust_cols[_mi%6].number_input(
                        _mn, 0.0, 100.0, _cv, 0.1, key=f"dist_{_mi}", format="%.1f")
                    _cust_wts.append(_nv/100)
                _cust_tot = sum(_cust_wts)*100
                _ctclr = "#10B981" if abs(_cust_tot-100)<0.2 else "#EF4444"
                st.markdown(
                    f"<div style='color:{_ctclr};font-weight:700;font-size:12px'>"
                    f"Total: {_cust_tot:.1f}% {'✅' if abs(_cust_tot-100)<0.2 else '❌ must = 100%'}</div>",
                    unsafe_allow_html=True)
                _final_wts = _cust_wts
            else:
                _final_wts = _patterns[_sel_pat]
                # Show preview bar chart
                _prev_bt   = saved_all.get(f"{_sel_kpi_d}|{t_period}",{})
                _prev_ann  = float(_prev_bt.get("target",0)) if _prev_bt else 0
                if _prev_ann and _final_wts:
                    _prev_monthly = [round(_prev_ann*w) for w in _final_wts]
                    import plotly.graph_objects as _go
                    _fig_d = _go.Figure(_go.Bar(
                        x=_months, y=_prev_monthly,
                        marker_color="#2563EB",
                        text=[f"{v/1e6:.1f}M" if v>=1e6 else str(int(v)) for v in _prev_monthly],
                        textposition="outside"))
                    _fig_d.update_layout(height=220,margin=dict(l=10,r=10,t=20,b=20),
                        showlegend=False, yaxis_title="Target")
                    st.plotly_chart(_fig_d, use_container_width=True)

            if st.button("💾 Save distribution", type="primary", key="save_dist"):
                _dist_cfg[_sel_kpi_d] = {
                    "pattern": _sel_pat,
                    "weights": [round(w,4) for w in _final_wts] if _final_wts else [1/12]*12,
                }
                a2z_db.save_json(_dist_file, _dist_cfg)
                st.success(f"✅ Distribution saved for {_sel_kpi_d}.")
                st.cache_data.clear()
                st.rerun()

# ══════════════════════════════════════════════════════════════════
# TAB 2 — FIXED KPIs
# ══════════════════════════════════════════════════════════════════
_tab_visible_fixed_kpis, _tab_idx_fixed_kpis = _in_tab("fixed_kpis")
if _tab_visible_fixed_kpis:
  with tabs[_tab_idx_fixed_kpis]:
    if not is_md:
        st.info("Fixed KPI management is MD / Admin only.")
    else:
        st.markdown(
            "<div style='padding:10px 16px;background:#FEF3C7;border:1px solid #FDE68A;"
            "border-radius:8px;margin-bottom:12px'>"
            "<b style='color:#92400E'>🔒 Fixed KPIs — bank-wide, auto-cascade to all staff</b><br>"
            "<span style='font-size:12px;color:#78350F'>"
            "Tick a KPI and enter its value. It will appear on every role's BSC that "
            "carries it — showing the fixed target and live achievement immediately, "
            "with no manual cascade needed.</span></div>",
            unsafe_allow_html=True)

        fp1, fp2 = st.columns([4,1])
        fix_period = fp2.selectbox("Period", [_gfy_casc(),"2025"], key="fix_period")
        cur_fixed  = casc.get_fixed_kpis(fix_period)
        new_fixed  = []
        fix_values = {}

        for pillar in PILLARS:
            kpis_p = sorted(kpis_by_pillar.get(pillar, []))
            if not kpis_p: continue
            pclr = PC[pillar]; picon = PI[pillar]
            st.markdown(
                f"<div style='padding:6px 12px;background:{pclr};color:var(--color-background-primary);"
                f"font-weight:700;font-size:11px;border-radius:6px;margin:10px 0 4px'>"
                f"{picon} {pillar}</div>", unsafe_allow_html=True)

            for kpi in kpis_p:
                is_cur_fixed = kpi in cur_fixed
                bt     = casc.get_bank_target(kpi, fix_period)
                bt_val = float(bt["target"]) if bt and bt.get("target") else 0.0
                pct_k  = is_pct(kpi)
                # Roles carrying this KPI
                roles_with_kpi = []
                if not df_proc.empty and "KPI" in df_proc.columns:
                    roles_with_kpi = df_proc[df_proc["KPI"]==kpi]["Role"].dropna().unique().tolist()

                tick_key = f"fix_{kpi}_{fix_period}"
                val_key  = f"fixval_{kpi}_{fix_period}"
                if tick_key not in st.session_state:
                    st.session_state[tick_key] = is_cur_fixed
                if val_key not in st.session_state:
                    st.session_state[val_key] = bt_val

                row_bg = "#FFFBEB" if is_cur_fixed else "var(--color-background-primary)"
                c1, c2, c3, c4 = st.columns([0.4, 2, 2, 3])

                ticked = c1.checkbox("", key=tick_key, label_visibility="collapsed")

                c2.markdown(
                    f"<div style='padding:6px 0;font-size:11px;"
                    f"font-weight:{'700' if is_cur_fixed else '400'};color:var(--color-text-primary)'>"
                    f"{'🔒 ' if is_cur_fixed else ''}{kpi}</div>",
                    unsafe_allow_html=True)

                if ticked:
                    new_fixed.append(kpi)
                    if pct_k:
                        fix_val = c3.number_input(
                            f"Val {kpi}", value=st.session_state.get(val_key, bt_val or 0.0),
                            min_value=0.0, max_value=100.0, step=0.01,
                            format="%.2f", key=val_key, label_visibility="collapsed",
                            help="Enter percentage e.g. 80 for 80%")
                    else:
                        _raw_key = f"fixraw_{kpi}_{fix_period}"
                        _disp = f"{st.session_state.get(val_key, bt_val):,.0f}" if st.session_state.get(val_key, bt_val) else ""
                        raw_input = c3.text_input(
                            f"Val {kpi}", value=_disp,
                            key=_raw_key, label_visibility="collapsed",
                            placeholder="e.g. 5,000,000")
                        try:
                            fix_val = float(str(raw_input).replace(",","").replace(" ","") or 0)
                        except (ValueError, TypeError):
                            fix_val = bt_val
                        st.session_state[val_key] = fix_val
                    fix_values[kpi] = fix_val
                    disp = (f"{fix_val:.2f}%" if pct_k else fmt_v(fix_val, kpi)) if fix_val else "—"
                    n_roles = len(roles_with_kpi)
                    c4.markdown(
                        f"<div style='padding:5px 0;font-size:11px;color:var(--brand-primary,#006B3F)'>"
                        f"✓ <b>{disp}</b> locked across {n_roles} role(s)</div>",
                        unsafe_allow_html=True)
                else:
                    c3.markdown(
                        f"<div style='padding:5px 0;font-size:10px;color:var(--color-text-tertiary)'>"
                        f"{fmt_v(bt_val,kpi) if bt_val else 'not set'}</div>",
                        unsafe_allow_html=True)
                    if roles_with_kpi:
                        c4.markdown(
                            f"<div style='font-size:10px;color:var(--color-text-tertiary);padding:5px 0'>"
                            f"Applies to: {', '.join(roles_with_kpi[:3])}"
                            f"{f' +{len(roles_with_kpi)-3} more' if len(roles_with_kpi)>3 else ''}"
                            f"</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
        if new_fixed:
            st.markdown(
                f"<div style='padding:8px 14px;background:#F0FDF4;border:1px solid #BBF7D0;"
                f"border-radius:8px;font-size:12px;margin-bottom:8px'>"
                f"🔒 <b>{len(new_fixed)}</b> KPI(s) will be fixed: "
                f"{', '.join(new_fixed)}</div>",
                unsafe_allow_html=True)

        if st.button("🔒 Save & auto-cascade fixed KPIs", type="primary",
                      use_container_width=True, key="save_fixed"):
            # Store values both in fixed_kpis.json AND bank_targets.json
            casc.set_fixed_kpis(fix_period, new_fixed, fix_values)
            saved_vals = 0
            for kpi_s, val_s in fix_values.items():
                if val_s and val_s > 0:
                    casc.set_bank_target(kpi_s, fix_period, float(val_s), 0.0)
                    saved_vals += 1
            audit_log("FIXED_KPIS", uname,
                      f"{fix_period}:{len(new_fixed)} fixed, {saved_vals} values")
            _bsc_trigger(uname, "K017")
            # Reload cascade manager so new values are visible immediately
            try:
                from utils.core import CascadeManager as _CM
                st.session_state["cascade_manager"] = _CM()
            except: pass
            st.toast(f"🔒 {len(new_fixed)} KPIs fixed · {saved_vals} values saved",
                     icon="🔒")
            st.cache_data.clear()
            st.rerun()

        if cur_fixed:
            st.info(
                f"Currently fixed ({fix_period}): "
                + " · ".join(f"🔒 {k}" for k in cur_fixed))


# ══════════════════════════════════════════════════════════════════
# TAB 3 — SET TEAM TARGETS (BSC scorecard per reportee)
# ══════════════════════════════════════════════════════════════════
_tab_visible_set_targets, _tab_idx_set_targets = _in_tab("set_targets")
if _tab_visible_set_targets:
  with tabs[_tab_idx_set_targets]:
    if not tab_visible(ud,"set_targets") or not is_mgr:
        st.info("Target allocation is available to managers and above.")
    else:
      # ── Direct reports ────────────────────────────────────────
      my_rl = my_role_level()
      # Branch-scoped roles: load from org_config (not hardcoded)
      try:
          from utils.core import get_org_roles as _gor
          _branch_scoped = set(get_org_roles("branch_staff"))
          if not _branch_scoped:
              raise ValueError("empty")
      except:
          _branch_scoped = set(ROLE_MAP.values())  # fallback: all known roles
      _use_unit = my_unit if (my_rl in _branch_scoped) else None
      d_reports = get_reports(my_rl or "", _use_unit)

      if my_rl == "Regional Head":
          my_region_raw = (ud.get("region","") or
                           my_unit.lower().replace(" region","").strip())
          my_rh_sc      = my_code  # Regional Head's staff code

          if my_region_raw and len(d_reports) and "Region" in d_reports.columns:
              rgn = str(my_region_raw).lower().replace(" region","").strip()
              _region_filtered = d_reports[d_reports["Region"].apply(
                  lambda r: str(r).lower().replace(" region","").strip()==rgn)]
              if len(_region_filtered) > 0:
                  d_reports = _region_filtered
              else:
                  # Fallback: filter by Reports To Code from Staff Register
                  # Load staff register to find branches reporting to this RH
                  try:
                      _sr = pm.get_staff_register() if hasattr(pm,'get_staff_register') else None
                      if _sr is None and not staff_scores.empty:
                          # Use uploaded data to find by Reports To Code
                          _sr_data = st.session_state.get("staff_register_df")
                          if _sr_data is not None:
                              _my_branches = _sr_data[
                                  _sr_data["Reports To Code"].astype(str).str.strip() == str(my_rh_sc).strip()
                              ]["Staff Name"].tolist()
                              if _my_branches:
                                  d_reports = d_reports[d_reports["Staff Name"].isin(_my_branches)]
                  except: pass

          if len(d_reports) == 0:
              # Last resort: show ALL branch managers and let manager filter
              if not d_reports.empty:
                  pass  # keep empty result
              else:
                  # Check if this is a data/config issue
                  _debug = (f"Region in account: '{ud.get('region','')}' | "
                            f"Unit: '{my_unit}' | "
                            f"Staff code: '{my_code}'")
                  st.warning(f"⚠️ No branch managers found for your region. "
                             f"Please ask Admin to verify your account has the correct "
                             f"Region field set (North / Central / South). {_debug}")

      if len(d_reports) == 0 and my_rl != "Regional Head":
          st.info(f"No direct reports found for **{my_rl}**. "
                  "Contact Admin to configure reporting lines.")

      else:
        # ── Controls ──────────────────────────────────────────
        h1, h2, h3 = st.columns([3, 1, 1])
        h1.markdown(
            f"<div style='padding:8px 0;font-size:14px;font-weight:700;color:var(--color-text-primary)'>"
            f"🎯 Set targets — {my_rl} · {len(d_reports)} direct report(s)</div>",
            unsafe_allow_html=True)
        alloc_year = st.selectbox("Period", [_gfy_casc(), str(int(_gfy_casc())-1)] if _gfy_casc() else [_gfy_casc(),"2025"], key="alloc_yr")

        # ── GUARD: non-MD cannot cascade until own targets received ───
        if not is_md and casc:
            _my_given_check = casc.get_what_i_was_given(my_code, alloc_year, my_name_l)
            _fixed_exist    = bool(casc.get_fixed_kpis(alloc_year))
            if not _my_given_check and not _fixed_exist:
                st.warning(
                    "⏳ You cannot cascade targets until your own targets have been set. "
                    "Your line manager has not yet cascaded targets to you. "
                    "Once you receive and confirm your targets, you can cascade to your team.")
                st.stop()
        act_pillar_sel = h3.selectbox(
            "Pillar",
            ["All pillars"] + [f"{PI.get(p,'')} {p}" for p in PILLARS],
            key="alloc_pillar")
        act_pillar = next((p for p in PILLARS if p in act_pillar_sel), None)

        # ── Bulk lock all direct reports ─────────────────────────────
        _locked_count  = sum(1 for _, _dr in d_reports.iterrows()
                              if casc.targets_locked(str(_dr.get("Staff Code","")), alloc_year))
        _total_dr      = len(d_reports)
        _unlocked_dr   = _total_dr - _locked_count
        if _unlocked_dr > 0:
            _bl1, _bl2 = st.columns([3, 1])
            _bl1.caption(f"**{_locked_count}/{_total_dr}** direct reports have locked targets")
            if _bl2.button(f"🔒 Lock all {_unlocked_dr} remaining",
                           key="bulk_lock_all_dr", type="primary",
                           use_container_width=True):
                _bulk_locked = 0
                for _, _dr_bl in d_reports.iterrows():
                    _dr_sc_bl = str(_dr_bl.get("Staff Code",""))
                    if _dr_sc_bl and not casc.targets_locked(_dr_sc_bl, alloc_year):
                        casc.lock_targets(_dr_sc_bl, alloc_year)
                        _bulk_locked += 1
                audit_log("BULK_LOCK_TARGETS", uname, alloc_year,
                           module="cascade",
                           detail=f"{my_code}|bulk_locked {_bulk_locked} direct reports")
                _bsc_trigger(uname, "K017")
                st.cache_data.clear()
                st.success(f"✅ Locked targets for {_bulk_locked} direct report(s)")
                st.rerun()
        else:
            st.success(f"✅ All {_total_dr} direct reports have locked targets")

        # Sort direct reports
        d_sorted = (d_reports.sort_values(["Unit","Staff Name"])
                    if "Unit" in d_reports.columns
                    else d_reports.sort_values("Staff Name")).reset_index(drop=True)

        # ── Existing allocations ──────────────────────────────
        existing_allocs = {}
        for k_key, entry in casc.cascade.items():
            if k_key.startswith("deadline|") or k_key.startswith("global_"): continue
            if entry.get("period","") != alloc_year: continue
            if entry.get("from_code","") not in (
                    my_code, uname, str(ud.get("staff_code",""))): continue
            for a in entry.get("allocations",[]):
                existing_allocs[(str(a.get("to_code","")), entry["kpi"])] = a.get("amount",0)

        # ── Role → KPI map from uploaded data ────────────────
        # Build which KPIs each person in d_sorted actually carries
        def _person_kpis(name, pillar_filter=None, exclude_fixed=False):
            """Return KPIs for a person.
            exclude_fixed=False → all KPIs including fixed (for full BSC table view)
            exclude_fixed=True  → non-fixed only (for editable input section)
            """
            if df_proc.empty: return []
            rows = df_proc[df_proc["Staff Name"]==name]
            if pillar_filter:
                rows = rows[rows["Pillar"]==pillar_filter]
            result = (rows[["Pillar","KPI","Weight","Annual Target"]]
                      .drop_duplicates(subset=["KPI"])
                      .sort_values(["Pillar","KPI"])
                      .to_dict("records"))
            if exclude_fixed:
                return [r for r in result
                        if not casc.is_fixed(r["KPI"], alloc_year)]
            return result

        # ── Group reportees for MD (by role cluster) ──────────
        MD_CLUSTERS = [
            ("💼 Business Directors", [
                "Director Retail Banking","Director Commercial Banking","Director Retail"]),
            ("📊 Finance & Risk", [
                "Chief Finance Officer","Chief Risk Officer","Chief Credit Officer"]),
            ("⚙️ Operations & Compliance", [
                "Chief Operations Officer","Chief Compliance Officer"]),
            ("👥 People & Support", [
                "Chief Human Resources Officer","Head Of Strategy",
                "Head Of Internal Audit","Head Of Digital Innovation",
                "Head Of Marketing","Debt Recovery Unit Manager"]),
        ]
        IS_MD = my_rl in ("Managing Director",)

        def _get_groups(d_sorted):
            if not IS_MD:
                return [("", d_sorted)]
            groups, placed = [], set()
            for grp_name, roles in MD_CLUSTERS:
                g = d_sorted[d_sorted["Role"].isin(roles)]
                if len(g):
                    groups.append((grp_name, g.reset_index(drop=True)))
                    placed.update(g.index.tolist())
            rest = d_sorted[~d_sorted.index.isin(placed)]
            if len(rest): groups.append(("📋 Other", rest.reset_index(drop=True)))
            return groups or [("", d_sorted)]

        rep_groups = _get_groups(d_sorted)

        # ── BRANCH BULK ALLOCATE — BM sets branch totals, split to BOM+BCM ──
        # Available only for Branch Manager level
        if my_rl == "Branch Manager" and not is_md:
            with st.expander("🏢 Allocate whole-branch targets (auto-split to BOM & BCM trees)",
                             expanded=False):
                st.caption(
                    "Set the total branch target per KPI. "
                    "The system will proportionally split to BOM tree and BCM tree "
                    "based on each tree's share of that KPI. "
                    "You can still override individual amounts in the tables below.")

                # Identify BOM and BCM groups
                _bom_group = next((df2 for gn, df2 in rep_groups
                                   if "Operations" in str(gn)), None)
                _bcm_group = next((df2 for gn, df2 in rep_groups
                                   if "Credit" in str(gn)), None)

                if _bom_group is None and _bcm_group is None:
                    st.info("No BOM/BCM groups found. Ensure reporting lines are configured.")
                else:
                    _bom_names = _bom_group["Staff Name"].tolist() if _bom_group is not None else []
                    _bcm_names = _bcm_group["Staff Name"].tolist() if _bcm_group is not None else []
                    _bom_codes = [str(_bom_group[_bom_group["Staff Name"]==n]["Staff Code"].values[0])
                                  for n in _bom_names if n in _bom_group["Staff Name"].values] if _bom_group is not None else []
                    _bcm_codes = [str(_bcm_group[_bcm_group["Staff Name"]==n]["Staff Code"].values[0])
                                  for n in _bcm_names if n in _bcm_group["Staff Name"].values] if _bcm_group is not None else []

                    st.markdown(
                        f"<div style='font-size:11px;color:var(--color-text-secondary);margin-bottom:8px'>"
                        f"BOM tree: {len(_bom_names)} person(s) | "
                        f"BCM tree: {len(_bcm_names)} person(s)</div>",
                        unsafe_allow_html=True)

                    # Get all KPIs that exist in BOTH trees
                    _bom_kpis = set()
                    _bcm_kpis = set()
                    if not df_proc.empty:
                        for _nm in _bom_names:
                            _bom_kpis.update(df_proc[df_proc["Staff Name"]==_nm]["KPI"].tolist())
                        for _nm in _bcm_names:
                            _bcm_kpis.update(df_proc[df_proc["Staff Name"]==_nm]["KPI"].tolist())

                    # Financial KPIs that span both (branch-owned targets)
                    _branch_kpis = sorted((_bom_kpis | _bcm_kpis) & {
                        "Deposit Growth","Loan Book Growth","Fees and Commission",
                        "DFS Revenue","Bancassurance","Digital Acquiring",
                        "Transactions","New Customer Acquisition","Dormancy Reactivation",
                        "PBT","NPL Ratio","PAR","Loans Disbursement",
                    })

                    if not _branch_kpis:
                        st.info("Upload v6 BSC data to enable branch bulk allocation.")
                    else:
                        _ba_c1, _ba_c2 = st.columns(2)
                        _ba_c1.markdown("**KPI**")
                        _ba_c2.markdown("**Branch total target**")

                        _bulk_entries = {}
                        for _bkpi in _branch_kpis:
                            _is_cnt = is_count_kpi(_bkpi)
                            _is_pct_b = is_pct(_bkpi)
                            _bk1, _bk2 = st.columns([2, 3])
                            _bk1.markdown(
                                f"<div style='padding:7px 0;font-size:11px;"
                                f"color:var(--color-text-primary);font-weight:600'>{_bkpi}"
                                f"{'  <span style="font-size:9px;color:var(--color-text-tertiary)">count</span>' if _is_cnt else ''}"
                                f"</div>", unsafe_allow_html=True)

                            _bkey = f"bulk_{alloc_year}_{_bkpi}"
                            if _is_pct_b:
                                _bulk_entries[_bkpi] = _bk2.number_input(
                                    _bkpi, min_value=0.0, max_value=1.0, step=0.005,
                                    format="%.3f", key=_bkey, label_visibility="collapsed")
                            elif _is_cnt:
                                _bulk_entries[_bkpi] = float(_bk2.number_input(
                                    _bkpi, min_value=0, step=1,
                                    key=_bkey, label_visibility="collapsed"))
                            else:
                                _raw = _bk2.text_input(_bkpi, key=_bkey + "_raw",
                                    placeholder="e.g. 150,000,000",
                                    label_visibility="collapsed")
                                try: _bulk_entries[_bkpi] = float(str(_raw).replace(",","") or 0)
                                except: _bulk_entries[_bkpi] = 0.0

                        # Split ratio: based on FY-25 actual share or equal if no data
                        st.markdown("**Split method**")
                        _split_mode = st.radio(
                            "Split", ["50/50 equal", "By FY-25 actual share",
                                      "By KPI ownership (BOM ops / BCM credit)"],
                            horizontal=True, key=f"bulk_split_{alloc_year}")

                        if st.button("⚡ Apply branch targets → split to both trees",
                                     type="primary", key=f"bulk_apply_{alloc_year}"):
                            _applied = 0
                            for _bkpi, _branch_tgt in _bulk_entries.items():
                                if not _branch_tgt: continue
                                _is_avg = is_avg_kpi(_bkpi)

                                # Determine which groups get this KPI
                                _in_bom = _bkpi in _bom_kpis
                                _in_bcm = _bkpi in _bcm_kpis

                                if _is_avg:
                                    # Individual rate — each person gets branch target
                                    for _gname, _gcodes in [("BOM",_bom_codes),("BCM",_bcm_codes)]:
                                        _eligible_g = _gcodes if (_in_bom if _gname=="BOM" else _in_bcm) else []
                                        for _gc in _eligible_g:
                                            st.session_state[f"ni_raw_{_gc}_{_bkpi}_{alloc_year}"] = str(_branch_tgt)
                                            st.session_state[f"v_{_gc}_{_bkpi}_{alloc_year}"] = _branch_tgt
                                            _applied += 1
                                else:
                                    # Additive — split between BOM and BCM
                                    _bom_eligible = _bom_codes if _in_bom else []
                                    _bcm_eligible = _bcm_codes if _in_bcm else []
                                    _total_eligible = len(_bom_eligible) + len(_bcm_eligible)
                                    if not _total_eligible: continue

                                    if _split_mode == "50/50 equal" or not (_in_bom and _in_bcm):
                                        # Equal per person
                                        _per = _branch_tgt / _total_eligible if _total_eligible else 0
                                        for _gc in _bom_eligible + _bcm_eligible:
                                            st.session_state[f"ni_raw_{_gc}_{_bkpi}_{alloc_year}"] = (
                                                str(int(_per)) if is_count_kpi(_bkpi) else f"{_per:,.0f}")
                                            st.session_state[f"v_{_gc}_{_bkpi}_{alloc_year}"] = _per
                                            _applied += 1
                                    elif _split_mode == "By KPI ownership (BOM ops / BCM credit)":
                                        # KPI ownership: credit KPIs 100% to BCM, ops KPIs to BOM
                                        _credit_kpis = {"Loans Disbursement","Loan Book Growth","NPL Ratio","PAR","Bancassurance"}
                                        _ops_kpis    = {"Transactions","Digital Acquiring","Dormancy Reactivation"}
                                        if _bkpi in _credit_kpis:
                                            _eligible_s = _bcm_eligible or _bom_eligible
                                        elif _bkpi in _ops_kpis:
                                            _eligible_s = _bom_eligible or _bcm_eligible
                                        else:
                                            _eligible_s = _bom_eligible + _bcm_eligible
                                        _per = _branch_tgt / len(_eligible_s) if _eligible_s else 0
                                        for _gc in _eligible_s:
                                            st.session_state[f"ni_raw_{_gc}_{_bkpi}_{alloc_year}"] = (
                                                str(int(_per)) if is_count_kpi(_bkpi) else f"{_per:,.0f}")
                                            st.session_state[f"v_{_gc}_{_bkpi}_{alloc_year}"] = _per
                                            _applied += 1
                                    else:
                                        # By FY-25 actual share
                                        _fy25s = {}
                                        for _gc in _bom_eligible + _bcm_eligible:
                                            _gr = df_proc[(df_proc["Staff Code"].astype(str)==_gc) &
                                                          (df_proc["KPI"]==_bkpi)] if not df_proc.empty else pd.DataFrame()
                                            if len(_gr):
                                                for _col in ["FY-25 Actual","Annual Actual"]:
                                                    if _col in _gr.columns:
                                                        _fy25s[_gc] = float(pd.to_numeric(_gr[_col].iloc[0],errors="coerce") or 0)
                                                        break
                                        _fy_total = sum(_fy25s.values())
                                        for _gc in _bom_eligible + _bcm_eligible:
                                            _wt = (_fy25s.get(_gc,0)/_fy_total) if _fy_total else (1/(_total_eligible or 1))
                                            _val = _branch_tgt * _wt
                                            st.session_state[f"ni_raw_{_gc}_{_bkpi}_{alloc_year}"] = (
                                                str(int(_val)) if is_count_kpi(_bkpi) else f"{_val:,.0f}")
                                            st.session_state[f"v_{_gc}_{_bkpi}_{alloc_year}"] = _val
                                            _applied += 1

                            st.toast(f"✅ Applied {len([v for v in _bulk_entries.values() if v])} branch targets → {_applied} allocations set", icon="🏢")
                            st.cache_data.clear()
                            st.rerun()

        # ── Render one BSC table per group ────────────────────
        for grp_name, grp_df in rep_groups:
            n = len(grp_df)
            if not n: continue

            # Group header
            if grp_name:
                st.markdown(
                    f"<div style='padding:10px 16px;background:linear-gradient("
                    f"135deg,#1A252F,#2C3E50);border-radius:10px;margin:18px 0 8px;"
                    f"display:flex;align-items:center;gap:10px'>"
                    f"<span style='color:var(--color-background-primary);font-weight:700;font-size:13px'>"
                    f"{grp_name}</span>"
                    f"<span style='color:rgba(255,255,255,0.4);font-size:11px'>"
                    f"· {n} person(s)</span></div>",
                    unsafe_allow_html=True)

            # All KPIs for this group — union of every member's KPIs (incl fixed)
            # Used for the full BSC overview table
            group_kpi_set_all  = {}  # {(pillar, kpi): weight} — ALL including fixed
            group_kpi_set_edit = {}  # {(pillar, kpi): weight} — non-fixed only (inputs)
            for _, dr_row in grp_df.iterrows():
                for k in _person_kpis(dr_row["Staff Name"], act_pillar, exclude_fixed=False):
                    key = (k["Pillar"], k["KPI"])
                    if key not in group_kpi_set_all:
                        group_kpi_set_all[key] = k.get("Weight",0) or 0
                for k in _person_kpis(dr_row["Staff Name"], act_pillar, exclude_fixed=True):
                    key = (k["Pillar"], k["KPI"])
                    if key not in group_kpi_set_edit:
                        group_kpi_set_edit[key] = k.get("Weight",0) or 0

            # group_kpi_set stays as "all" for the totals weight row
            group_kpi_set = group_kpi_set_all

            def _sort_kpis(kpi_dict):
                return sorted(kpi_dict.keys(),
                               key=lambda x: (PILLARS.index(x[0]) if x[0] in PILLARS else 99, x[1]))

            kpis_for_group  = _sort_kpis(group_kpi_set_all)   # table: ALL KPIs
            kpis_for_inputs = _sort_kpis(group_kpi_set_edit)   # inputs: non-fixed only

            if not kpis_for_group:
                for pillar in (PILLARS if not act_pillar else [act_pillar]):
                    for kpi in kpis_by_pillar.get(pillar,[]):
                        kpis_for_group.append((pillar, kpi))
                kpis_for_inputs = [(p,k) for p,k in kpis_for_group
                                   if not casc.is_fixed(k, alloc_year)]

            if not kpis_for_group:
                st.info("No KPI data for this group."); continue

            # ── Build person info list ────────────────────────
            rep_list = []
            for _, dr_row in grp_df.iterrows():
                nm  = dr_row["Staff Name"]
                sc  = str(dr_row.get("Staff Code",""))
                unt = str(dr_row.get("Unit","")).replace(" Branch","").replace(" Region","")
                rl  = str(dr_row.get("Role",""))
                lkd = casc.targets_locked(sc, alloc_year)
                nh  = is_new_hire(nm)
                sn  = nm.split()[0]+" "+(nm.split()[-1][0] if len(nm.split())>1 else "")
                try:
                    from utils.core import photo_avatar_html as _ph
                    av = _ph(sc, nm, size=30)
                except:
                    ini = (nm[0]+nm.split()[-1][0]).upper() if nm.split() else "?"
                    av  = (f"<div style='width:30px;height:30px;border-radius:50%;"
                           f"background:linear-gradient(135deg,var(--brand-primary,#006B3F),var(--brand-mid,#1D9E75);"
                           f"display:flex;align-items:center;justify-content:center;"
                           f"color:var(--color-background-primary);font-size:10px;font-weight:800'>{ini}</div>")
                rep_list.append({"nm":nm,"sc":sc,"unit":unt,"role":rl,
                                  "lkd":lkd,"nh":nh,"short":sn,"av":av})

            # ── HTML TABLE — BSC scorecard style ─────────────
            # Column: Pillar | KPI | Wt | Bank Target | FY-25 | [person cols] | Total | Buffer
            person_ths = "".join(
                f"<th style='padding:8px 6px;text-align:center;min-width:100px;"
                f"background:#185FA5;color:var(--color-background-primary);border:1px solid #1a4a8a'>"
                f"<div style='display:flex;flex-direction:column;align-items:center;gap:2px'>"
                f"{r['av']}"
                f"<span style='font-size:9px;font-weight:700;margin-top:2px'>"
                f"{r['short']}{'🔒' if r['lkd'] else ''}{'🆕' if r['nh'] else ''}</span>"
                f"<span style='font-size:8px;opacity:0.65'>{r['unit']}</span>"
                f"</div></th>"
                for r in rep_list)

            tbl = (
                "<div style='overflow-x:auto;border-radius:10px;"
                "border:1px solid var(--color-border-secondary);box-shadow:0 2px 8px rgba(0,0,0,0.07);"
                "margin-bottom:10px;position:relative'>"
                "<table style='border-collapse:collapse;font-size:11px;table-layout:auto'>"
                "<thead>"
                "<tr style='background:var(--brand-primary,#006B3F)'>"
                "<th style='padding:9px 6px;min-width:66px;text-align:center;"
                "color:var(--color-background-primary);border:1px solid #004a2b;"
                "position:sticky;left:0;z-index:3;background:var(--brand-primary,#006B3F)'>Pillar</th>"
                "<th style='padding:9px 10px;text-align:left;min-width:150px;"
                "color:var(--color-background-primary);border:1px solid #004a2b;"
                "position:sticky;left:66px;z-index:3;background:var(--brand-primary,#006B3F)'>KPI</th>"
                "<th style='padding:9px 5px;text-align:center;min-width:36px;"
                "color:var(--color-background-primary);border:1px solid #004a2b'>Wt</th>"
                "<th style='padding:9px 8px;text-align:right;min-width:88px;"
                "color:var(--color-background-primary);border:1px solid #004a2b'>Your Target</th>"
                "<th style='padding:9px 8px;text-align:right;min-width:80px;"
                "background:#374151;color:var(--color-background-primary);border:1px solid #2d3748'>FY-25</th>"
                + person_ths +
                "<th style='padding:9px 6px;text-align:right;min-width:80px;"
                "background:#166534;color:var(--color-background-primary);border:1px solid #14532d'>Total/Avg</th>"
                "<th style='padding:9px 6px;text-align:center;min-width:70px;"
                "background:#166534;color:var(--color-background-primary);border:1px solid #14532d'>vs Target</th>"
                "</tr></thead><tbody>"
            )

            # Pillar rowspan counts (for THIS group's KPIs)
            pillar_counts = {}
            for pillar, kpi in kpis_for_group:
                pillar_counts[pillar] = pillar_counts.get(pillar,0)+1

            PILLAR_BG  = {"Financial":"var(--brand-light,#E8F5EE)","Customer Focus":"#EFF6FF",
                           "Operational Excellence":"#F3E8FF"}
            PILLAR_CLR = {"Financial":"var(--brand-primary,#006B3F)","Customer Focus":"#185FA5",
                           "Operational Excellence":"#6B21A8"}

            prev_pil   = None
            input_rows = []  # (pillar,kpi,sc,ss_key,cur_v,step,pct_kpi,lkd,is_fix,nm)
            row_idx    = 0

            for pillar, kpi in kpis_for_group:
                is_fix  = casc.is_fixed(kpi, alloc_year)
                pct_kpi = is_pct(kpi)
                step    = kpi_step(kpi)
                # Try alloc_year first, then common periods as fallback
                bt = casc.get_bank_target(kpi, alloc_year)
                if not bt:
                    for _p in (_gfy_casc(),"2025"):
                        bt = casc.get_bank_target(kpi, _p)
                        if bt: break
                bank_tgt = float(bt["target"]) if bt and bt.get("target") else 0.0
                # Compute stretch_tgt here so table column can show it
                if bt and bt.get("buffer_pct") and bank_tgt:
                    _tbl_buf = float(bt["buffer_pct"])
                    _tbl_dir = -1 if is_reduce(kpi) else 1
                    stretch_tgt = round(bank_tgt*(1+_tbl_dir*_tbl_buf/100), 2)
                else:
                    stretch_tgt = bank_tgt
                p_bg    = PILLAR_BG.get(pillar,"#F9FAFB")
                p_clr   = PILLAR_CLR.get(pillar,"#374151")
                row_bg  = "#FFFBEB" if is_fix else ("var(--color-background-primary)" if row_idx%2==0 else "#FAFAFA")
                row_idx += 1

                # Pillar cell (rowspan)
                if pillar != prev_pil:
                    cnt = pillar_counts[pillar]
                    pil_td = (
                        f"<td rowspan='{cnt}' style='background:{p_bg};"
                        f"color:{p_clr};font-weight:700;font-size:9px;"
                        f"text-align:center;vertical-align:middle;"
                        f"padding:6px 3px;border:0.5px solid var(--color-border-tertiary);"
                        f"white-space:nowrap;"
                        f"position:sticky;left:0;z-index:2'>"
                        f"{PI.get(pillar,'')}<br>"
                        f"<span style='font-size:8px'>"
                        f"{pillar.replace(' ','<br>')}</span></td>")
                    prev_pil = pillar
                else:
                    pil_td = ""

                # Wt and FY-25 (avg across members who have this KPI)
                wt_vals, fy_vals = [], []
                for r in rep_list:
                    rows_r = (df_proc[(df_proc["Staff Name"]==r["nm"])
                                      &(df_proc["KPI"]==kpi)]
                              if not df_proc.empty else pd.DataFrame())
                    if len(rows_r):
                        wt_vals.append(float(pd.to_numeric(
                            rows_r["Weight"].iloc[0], errors="coerce") or 0))
                        fy_vals.append(float(pd.to_numeric(
                            rows_r.get("FY-25 Actual", rows_r.iloc[:,0]).iloc[0]
                            if "FY-25 Actual" in rows_r.columns
                            else 0, errors="coerce") or 0))
                wt_avg  = sum(wt_vals)/len(wt_vals) if wt_vals else 0
                fy25_avg= sum(fy_vals)/len(fy_vals) if fy_vals else 0

                fix_badge = (
                    "<span style='background:#FDE68A;color:#92400E;font-size:8px;"
                    "font-weight:700;padding:1px 4px;border-radius:3px;margin-left:4px;"
                    "vertical-align:middle'>AUTO</span>"
                    if is_fix else "")
                tbl += (
                    f"<tr style='background:{row_bg}'>"
                    + pil_td
                    + f"<td style='font-size:11px;padding:5px 10px;"
                    f"border:0.5px solid var(--color-border-tertiary);background:{row_bg};"
                    f"position:sticky;left:66px;z-index:2;"
                    f"font-weight:{'600' if is_fix else '400'}'>"
                    f"{'🔒 ' if is_fix else ''}{kpi}{fix_badge}</td>"
                    + f"<td style='text-align:center;font-size:10px;color:var(--color-text-tertiary);"
                    f"border:0.5px solid var(--color-border-tertiary)'>"
                    f"{f'{wt_avg*100:.0f}%' if wt_avg else '—'}</td>"
                    + f"<td style='text-align:right;font-size:11px;padding:4px 8px;"
                    f"border:0.5px solid var(--color-border-tertiary);font-weight:600'>"
                    f"{fmt_v(stretch_tgt,kpi) if stretch_tgt else ('—' if not bank_tgt else fmt_v(bank_tgt,kpi))}</td>"
                    + f"<td style='text-align:right;font-size:11px;padding:4px 8px;"
                    f"color:var(--color-text-secondary);border:0.5px solid var(--color-border-tertiary)'>"
                    f"{fmt_v(fy25_avg,kpi) if fy25_avg else '—'}</td>"
                )

                # Per-person value cells
                row_vals = []
                for r in rep_list:
                    sc     = r["sc"]
                    # Check if this KPI is in this person's scorecard
                    person_has_kpi = not df_proc.empty and len(
                        df_proc[(df_proc["Staff Name"]==r["nm"])
                                &(df_proc["KPI"]==kpi)]) > 0
                    if not person_has_kpi:
                        tbl += ("<td style='background:var(--color-background-secondary);border:0.5px solid var(--color-border-tertiary);"
                                "text-align:center;color:#D1D5DB;font-size:10px'>—</td>")
                        row_vals.append(0)
                        continue

                    if is_fix:
                        # Fixed KPI — use dedicated get_fixed_value() which checks
                        # both fixed_kpis.json values and bank_targets.json
                        fix_val = casc.get_fixed_value(kpi, alloc_year)
                        if not fix_val:
                            for _try_per in [_gfy_casc(), "2025"]:
                                fix_val = casc.get_fixed_value(kpi, _try_per)
                                if fix_val: break
                        row_vals.append(fix_val)
                        if fix_val:
                            disp = fmt_v(fix_val, kpi)
                            cell_content = (
                                f"<div style='display:flex;flex-direction:column;"
                                f"align-items:flex-end;gap:1px'>"
                                f"<span style='font-weight:700;color:#92400E'>"
                                f"🔒 {disp}</span>"
                                f"<span style='font-size:8px;color:#B45309;"
                                f"background:#FDE68A;padding:0 3px;border-radius:2px'>"
                                f"auto-cascade</span>"
                                f"</div>")
                        else:
                            # Fixed but no value stored yet — show the row but note value pending
                            cell_content = (
                                "<div style='text-align:center'>"
                                "<span style='background:#FDE68A;color:#92400E;font-size:9px;"
                                "padding:1px 5px;border-radius:3px;font-weight:700'>🔒 auto</span>"
                                "</div>")
                        tbl += (f"<td style='text-align:right;font-size:11px;padding:4px 6px;"
                                f"background:#FFFBEB;border:1px solid #FDE68A'>"
                                f"{cell_content}</td>")
                    else:
                        ss_key = f"v_{sc}_{kpi}_{alloc_year}"
                        ex_val = existing_allocs.get((sc,kpi), 0.0)
                        cur_v  = float(st.session_state.get(ss_key, ex_val or 0.0))
                        row_vals.append(cur_v)
                        disp    = fmt_v(cur_v,kpi) if cur_v else "—"
                        cel_bg  = "#F0FDF4" if r["lkd"] else "#EFF6FF"
                        cel_clr = "var(--brand-primary,#006B3F)" if cur_v else "#9CA3AF"
                        tbl += (f"<td style='text-align:right;font-size:11px;padding:4px 6px;"
                                f"background:{cel_bg};border:0.5px solid var(--color-border-tertiary);"
                                f"font-weight:600;color:{cel_clr}'>{disp}</td>")

                # Total/Average + buffer
                _n_vals   = [v for v in row_vals if v > 0]
                _is_avg_k = is_avg_kpi(kpi)
                if _is_avg_k:
                    # Average-type KPI — show avg of entered values
                    row_summary = sum(_n_vals)/len(_n_vals) if _n_vals else 0
                    _sum_lbl = fmt_v(row_summary,kpi) if row_summary else "—"
                    _buf_col = "#9CA3AF"
                    # Compare avg entered to bank target
                    if bank_tgt and row_summary:
                        _diff = row_summary - bank_tgt
                        _buf_col = "var(--brand-primary,#006B3F)" if (is_reduce(kpi) and _diff<=0) or (not is_reduce(kpi) and _diff>=0) else "#E24B4A"
                        buf_str = f"avg {fmt_v(row_summary,kpi)}"
                    else:
                        buf_str = "avg"
                else:
                    row_summary = sum(row_vals)
                    _sum_lbl = fmt_v(row_summary,kpi) if row_summary else "—"
                    if bank_tgt and row_summary:
                        buf_pct = (row_summary-bank_tgt)/abs(bank_tgt)*100
                        buf_str = f"{buf_pct:+.1f}%"
                        buf_clr = "var(--brand-primary,#006B3F)" if buf_pct>=0 else "#E24B4A"
                        _buf_col = buf_clr
                    else:
                        buf_str,_buf_col = "—","#9CA3AF"

                tbl += (
                    f"<td style='text-align:right;font-size:11px;padding:4px 6px;"
                    f"background:#F0FDF4;font-weight:700;color:var(--brand-primary,#006B3F);"
                    f"border:1px solid #BBF7D0'>"
                    f"{_sum_lbl}</td>"
                    f"<td style='text-align:center;font-size:10px;font-weight:700;"
                    f"color:{_buf_col};border:0.5px solid var(--color-border-tertiary)'>{buf_str}</td>"
                    "</tr>"
                )

            # Weighted totals row — one cell per person showing their total weight
            # Each person's weights should sum to 100%
            person_wt_totals = {}
            for r in rep_list:
                wt_sum = 0.0
                for p2, k2 in kpis_for_group:
                    rows_wt = (df_proc[(df_proc["Staff Name"]==r["nm"])
                                       &(df_proc["KPI"]==k2)]
                               if not df_proc.empty else pd.DataFrame())
                    if len(rows_wt):
                        wt_sum += float(pd.to_numeric(
                            rows_wt["Weight"].iloc[0], errors="coerce") or 0)
                person_wt_totals[r["sc"]] = wt_sum * 100

            def _wt_cell(sc_r):
                w = person_wt_totals.get(sc_r, 0)
                clr = "var(--brand-primary,#006B3F)" if abs(w-100)<0.5 else "#E24B4A"
                return (f"<td style='text-align:center;font-weight:700;font-size:10px;"
                        f"color:{clr};background:var(--brand-light,#E8F5EE);border:1px solid #BBF7D0'>"
                        f"{w:.0f}%</td>")

            # Only show weight-total row if any person is NOT at 100% (validation alert)
            _bad_wts = [r for r in rep_list
                        if abs(person_wt_totals.get(r["sc"],0)-100) > 0.5]
            if _bad_wts:
                tbl += (
                    "<tr style='background:#FEF2F2;border-top:2px solid #E24B4A'>"
                    "<td colspan='2' style='padding:8px 10px;font-size:11px;"
                    "font-weight:700;color:#E24B4A'>⚠️ KPI weight check</td>"
                    "<td style='text-align:center;font-size:10px;color:var(--color-text-tertiary);"
                    "border:0.5px solid var(--color-border-tertiary)'>Σ wt</td>"
                    "<td colspan='2'></td>"
                    + "".join(_wt_cell(r["sc"]) for r in rep_list)
                    + "<td></td><td></td></tr>"
                )
            tbl += "</tbody></table></div>"
            st.markdown(tbl, unsafe_allow_html=True)

            # ── INLINE INPUTS — non-fixed KPIs only, grouped by KPI ─
            has_any_editable = any(
                not rep_list_r["lkd"]
                for rep_list_r in rep_list
            ) and kpis_for_inputs

            if has_any_editable:
                # ── Adopt whole target as-is (BCM / BOM only) ─────────
                # BCM/BOM received a target from BM — they can pass it
                # straight to each of their reportees unchanged.
                _mid_manager_roles = {
                    "Branch Credit Manager", "Branch Operations Manager",
                }
                if my_rl in _mid_manager_roles and not is_md:
                    _grp_uid_adopt = (grp_name.replace(" ","_").replace("/","_")[:14]
                                      if grp_name else "all")
                    _adopt_key = f"adopt_asis_{_grp_uid_adopt}_{alloc_year}"

                    if st.button(
                            f"📥 Adopt received target as-is → distribute equally to {len(rep_list)} reportee(s)",
                            key=_adopt_key,
                            help="Passes your received target unchanged to every member of this group. "
                                 "You can still adjust individual amounts below.",
                            use_container_width=True):
                        _adopted = 0
                        for _ap, _ak in kpis_for_inputs:
                            if is_avg_kpi(_ak): continue  # individual rates set separately
                            # Get what this manager received for this KPI
                            _am_rcv = next(
                                (g["amount"] for g in
                                 (casc.get_what_i_was_given(my_code, alloc_year, my_name_l) or [])
                                 if g.get("kpi") == _ak), 0.0)
                            if casc.is_fixed(_ak, alloc_year):
                                _am_rcv = casc.get_fixed_value(_ak, alloc_year) or 0.0
                            if not _am_rcv: continue
                            # Distribute equally
                            _n_rep = len([r for r in rep_list
                                          if not casc.is_fixed(_ak, alloc_year)])
                            if not _n_rep: continue
                            _per_person = _am_rcv / _n_rep
                            for _rp in rep_list:
                                _rsc = _rp["sc"]
                                if is_count_kpi(_ak):
                                    _rv = str(int(round(_per_person)))
                                else:
                                    _rv = f"{_per_person:,.0f}"
                                st.session_state[f"ni_raw_{_rsc}_{_ak}_{alloc_year}"] = _rv
                                st.session_state[f"v_{_rsc}_{_ak}_{alloc_year}"] = _per_person
                                _adopted += 1
                        if _adopted:
                            st.toast(f"✅ Adopted {_adopted} target values → {len(rep_list)} reportee(s)", icon="📥")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.warning("No received targets found. Ensure your line manager has cascaded to you first.")

                st.markdown(
                    "<div style='padding:10px 14px;background:var(--color-background-secondary);"
                    "border:0.5px solid var(--color-border-tertiary);border-radius:8px;"
                    "font-size:11px;font-weight:700;color:var(--color-text-primary);"
                    "margin:10px 0 8px'>↓ Enter allocation amounts — "
                    "<span style='color:var(--color-text-tertiary);font-weight:400'>fixed KPIs auto-apply</span>"
                    "</div>",
                    unsafe_allow_html=True)

                for pillar, kpi in kpis_for_inputs:
                    pclr    = PILLAR_CLR.get(pillar,"#374151")
                    pct_kpi = is_pct(kpi)
                    step    = kpi_step(kpi)
                    bt      = casc.get_bank_target(kpi, alloc_year)
                    bank_tgt= bt["target"] if bt else 0.0

                    # What was cascaded TO this manager for this KPI?
                    # This is the manager's OWN target received from their line manager
                    _my_given_kpi = next(
                        (g for g in (casc.get_what_i_was_given(my_code, alloc_year, my_name_l) or [])
                         if g.get("kpi") == kpi), None)
                    _my_received = float(_my_given_kpi["amount"]) if _my_given_kpi else 0.0

                    # For fixed KPIs, use the fixed value
                    if casc.is_fixed(kpi, alloc_year):
                        _my_received = casc.get_fixed_value(kpi, alloc_year) or bank_tgt

                    # Manager's pool to distribute = what they received (not bank total)
                    # If MD (no one cascades to them), use bank target with buffer
                    if _my_received:
                        stretch_tgt = _my_received  # their received amount IS their target
                    elif is_md:
                        # MD uses bank target + buffer as their pool
                        bt_obj = casc.get_bank_target(kpi, alloc_year)
                        stretch_tgt = bank_tgt
                        if bt_obj and bt_obj.get("buffer_pct",0):
                            _buf = float(bt_obj.get("buffer_pct",0))
                            _dir = -1 if is_reduce(kpi) else 1
                            stretch_tgt = round(bank_tgt*(1+_dir*_buf/100),2)
                    else:
                        stretch_tgt = bank_tgt  # fallback

                    # Sum already-allocated amounts — read from the text input state
                    def _get_alloc_val(sc_r, kpi_r):
                        """Get current allocation value from text input or saved."""
                        raw_key = f"ni_raw_{sc_r}_{kpi_r}_{alloc_year}"
                        v_key   = f"v_{sc_r}_{kpi_r}_{alloc_year}"
                        # Try text input first (live typed value)
                        raw = st.session_state.get(raw_key, "")
                        if raw:
                            try: return float(str(raw).replace(",","").replace(" ","") or 0)
                            except: pass
                        # Fall back to parsed session state or saved allocation
                        return float(st.session_state.get(v_key,
                               existing_allocs.get((sc_r, kpi_r), 0.0)))

                    _allocated_so_far = sum(
                        _get_alloc_val(r2["sc"], kpi)
                        for r2 in rep_list
                        if not casc.is_fixed(kpi, alloc_year))
                    _remaining = stretch_tgt - _allocated_so_far if stretch_tgt else None
                    _rem_clr   = ("var(--brand-primary,#006B3F)" if _remaining and _remaining >= 0 else "#E24B4A") if _remaining is not None else "#9CA3AF"

                    _hdr_right = ""
                    if stretch_tgt:
                        if _my_received and not is_md:
                            # Show what this manager received as their target
                            _hdr_right += f"Your target: <b>{fmt_v(_my_received,kpi)}</b>"
                        else:
                            _hdr_right += f"Bank: <b>{fmt_v(bank_tgt,kpi)}</b>"
                        if stretch_tgt != bank_tgt and stretch_tgt != _my_received:
                            _hdr_right += f" → With buffer: <b>{fmt_v(stretch_tgt,kpi)}</b>"
                        if _remaining is not None:
                            _rem_str = fmt_v(abs(_remaining),kpi)
                            _over    = "over" if _remaining < 0 else "remaining"
                            _hdr_right += (f" · <span style='color:{_rem_clr};font-weight:700'>"
                                           f"{_rem_str} {_over}</span>")
                    else:
                        _hdr_right = "No bank target set"

                    st.markdown(
                        f"<div style='padding:5px 10px;background:{pclr}10;"
                        f"border-left:3px solid {pclr};border-radius:0 6px 6px 0;"
                        f"font-size:11px;font-weight:700;color:{pclr};"
                        f"margin:10px 0 4px;display:flex;justify-content:space-between;"
                        f"align-items:center'>"
                        f"<span>{kpi}</span>"
                        f"<span style='font-weight:400;color:var(--color-text-secondary);font-size:10px'>"
                        f"{_hdr_right}</span>"
                        f"</div>", unsafe_allow_html=True)

                    # ── Build eligible list for this KPI ──────────────
                    _eligible = []
                    for r in rep_list:
                        if r["lkd"]: continue
                        if not df_proc.empty:
                            if len(df_proc[(df_proc["Staff Name"]==r["nm"])
                                          &(df_proc["KPI"]==kpi)]) == 0:
                                continue
                        _eligible.append(r)

                    if not _eligible:
                        continue

                    # ── Helper: get current typed/saved value for a person ──
                    def _cur_alloc(sc_r):
                        raw = st.session_state.get(f"ni_raw_{sc_r}_{kpi}_{alloc_year}", "")
                        if raw:
                            try: return float(str(raw).replace(",","").replace(" ","") or 0)
                            except: pass
                        pct_k2 = f"ni_{sc_r}_{kpi}_{alloc_year}"
                        if pct_k2 in st.session_state:
                            return float(st.session_state[pct_k2] or 0)
                        return float(existing_allocs.get((sc_r, kpi), 0.0))

                    # ── Allocation mode: additive vs average ──────────────
                    _grp_uid   = (grp_name.replace(" ","_").replace("/","_")[:12]
                                  if grp_name else "all")
                    _dir_buf_key = f"dirbuf_{_grp_uid}_{kpi}_{alloc_year}"
                    _n_el      = len(_eligible)
                    _is_avg    = is_avg_kpi(kpi)
                    _allocated = sum(_cur_alloc(r2["sc"]) for r2 in _eligible)
                    _fmt_v     = (lambda v: f"{v:.2f}%") if pct_kpi else (lambda v: fmt_v(v, kpi))

                    # Apply director's buffer FIRST, then compute remaining
                    if not _is_avg and stretch_tgt:
                        _dir_buf_now = float(st.session_state.get(_dir_buf_key, 0.0))
                        if _dir_buf_now:
                            _dir_dir = -1 if is_reduce(kpi) else 1
                            stretch_tgt = round(stretch_tgt * (1 + _dir_dir * _dir_buf_now / 100), 2)

                    _remaining = (stretch_tgt - _allocated) if (stretch_tgt and not _is_avg) else 0.0
                    _remaining = 0.0 if abs(_remaining) < 0.01 else _remaining
                    _rem_clr   = "var(--brand-primary,#006B3F)" if _remaining >= 0 else "#E24B4A"

                    # ── KPI mode badge ─────────────────────────────────────
                    if _is_avg:
                        # For avg KPIs: show bank target as context, no pool tracking
                        _avg_bank = fmt_v(bank_tgt,kpi) if bank_tgt else "—"
                        # Compute average of entered targets so far
                        _entered = [_cur_alloc(r2["sc"]) for r2 in _eligible if _cur_alloc(r2["sc"])>0]
                        _avg_entered = sum(_entered)/len(_entered) if _entered else 0
                        _avg_disp = fmt_v(_avg_entered,kpi) if _avg_entered else "—"
                        st.markdown(
                            f"<div style='font-size:10px;color:var(--color-text-secondary);padding:1px 0 4px;"
                            f"display:flex;gap:12px;flex-wrap:wrap;align-items:center'>"
                            f"<span style='background:#EFF6FF;border:1px solid #BFDBFE;"
                            f"border-radius:6px;padding:1px 6px;font-size:9px;"
                            f"font-weight:700;color:#185FA5'>📊 Individual rate</span>"
                            f"<span>Bank target: <b>{_avg_bank}</b></span>"
                            f"{'<span>Avg entered: <b>' + _avg_disp + '</b></span>' if _avg_entered else ''}"
                            f"</div>",
                            unsafe_allow_html=True)
                    elif stretch_tgt:
                        _rem_disp = _fmt_v(abs(_remaining))
                        _alloc_disp = _fmt_v(_allocated)
                        _bal_clr = _rem_clr
                        st.markdown(
                            f"<div style='font-size:10px;color:var(--color-text-secondary);padding:1px 0 4px;"
                            f"display:flex;gap:12px;flex-wrap:wrap'>"
                            f"<span>Pool: <b style='color:var(--color-text-primary)'>{_fmt_v(stretch_tgt)}</b></span>"
                            f"<span>Allocated: <b style='color:var(--color-text-primary)'>{_alloc_disp}</b></span>"
                            f"<span style='color:{_bal_clr};font-weight:700'>"
                            f"{'🔴' if _remaining < -0.01 else '🟢'} "
                            f"{_rem_disp} {'over' if _remaining < -0.01 else 'remaining'}</span>"
                            f"</div>",
                            unsafe_allow_html=True)

                    # ── Action buttons ─────────────────────────────────────
                    if not _is_avg and stretch_tgt:
                        if _dir_buf_key not in st.session_state:
                            st.session_state[_dir_buf_key] = 0.0
                        _buf_c, _ac1, _ac2 = st.columns([1, 2, 2])
                        # Buffer already applied above — just show the input field
                        _dir_buf = _buf_c.number_input(
                            "My buffer %", min_value=0.0, max_value=20.0,
                            step=0.5, format="%.1f",
                            key=_dir_buf_key, label_visibility="visible",
                            help="Buffer added to your received target before distributing")

                        if _n_el == 1:
                            # Single eligible — "Allocate all"
                            _sole = _eligible[0]
                            if _ac1.button(
                                    f"⚡ All to {_sole['short']} ({_fmt_v(stretch_tgt)})",
                                    key=f"alloc_all_{_grp_uid}_{kpi}_{alloc_year}",
                                    use_container_width=True, type="primary"):
                                _rk = f"ni_raw_{_sole['sc']}_{kpi}_{alloc_year}"
                                _vk = f"v_{_sole['sc']}_{kpi}_{alloc_year}"
                                st.session_state[_rk] = f"{stretch_tgt:,.0f}" if not pct_kpi else f"{stretch_tgt:.2f}"
                                st.session_state[_vk] = stretch_tgt
                                st.cache_data.clear()
                                st.rerun()
                            if _remaining > 0.01 and _allocated > 0:
                                if _ac2.button(f"↔ Top up {_fmt_v(_remaining)}",
                                               key=f"alloc_rem_{_grp_uid}_{kpi}_{alloc_year}",
                                               use_container_width=True):
                                    _new = _allocated + _remaining
                                    st.session_state[f"ni_raw_{_sole['sc']}_{kpi}_{alloc_year}"] = f"{_new:,.0f}" if not pct_kpi else f"{_new:.2f}"
                                    st.session_state[f"v_{_sole['sc']}_{kpi}_{alloc_year}"] = _new
                                    st.cache_data.clear()
                                    st.rerun()

                        elif _n_el > 1 and _remaining > 0.01:
                            # Multiple eligible — ratio allocation
                            _ratio_key = f"ratio_mode_{_grp_uid}_{kpi}_{alloc_year}"
                            if _ratio_key not in st.session_state:
                                st.session_state[_ratio_key] = "equal"
                            _mode = _ac1.selectbox(
                                "Split method",
                                ["equal", "custom ratio", "by FY-25 actual"],
                                index=["equal","custom ratio","by FY-25 actual"].index(
                                    st.session_state[_ratio_key]),
                                key=f"ratiosel_{_grp_uid}_{kpi}_{alloc_year}",
                                label_visibility="collapsed")
                            st.session_state[_ratio_key] = _mode

                            if _ac2.button(f"↔ Distribute {_fmt_v(_remaining)}",
                                           key=f"alloc_split_{_grp_uid}_{kpi}_{alloc_year}",
                                           use_container_width=True, type="primary"):
                                if _mode == "equal":
                                    _per = _remaining / _n_el
                                    for _er in _eligible:
                                        _new = _cur_alloc(_er["sc"]) + _per
                                        st.session_state[f"ni_raw_{_er['sc']}_{kpi}_{alloc_year}"] = f"{_new:,.0f}" if not pct_kpi else f"{_new:.2f}"
                                        st.session_state[f"v_{_er['sc']}_{kpi}_{alloc_year}"] = _new
                                elif _mode == "by FY-25 actual":
                                    # Weight by each person's FY-25 actual for this KPI
                                    _fy25s = {}
                                    for _er in _eligible:
                                        _rows = df_proc[(df_proc["Staff Name"]==_er["nm"])&(df_proc["KPI"]==kpi)] if not df_proc.empty else pd.DataFrame()
                                        for _col in ["FY-25 Actual","Annual Actual","YTD_Actual"]:
                                            if _col in _rows.columns and len(_rows):
                                                _fy25s[_er["sc"]] = float(pd.to_numeric(_rows[_col].iloc[0],errors="coerce") or 0)
                                                break
                                    _fy_total = sum(_fy25s.values())
                                    for _er in _eligible:
                                        _wt   = (_fy25s.get(_er["sc"],0) / _fy_total) if _fy_total else (1/_n_el)
                                        _new  = _cur_alloc(_er["sc"]) + _remaining * _wt
                                        st.session_state[f"ni_raw_{_er['sc']}_{kpi}_{alloc_year}"] = f"{_new:,.0f}" if not pct_kpi else f"{_new:.2f}"
                                        st.session_state[f"v_{_er['sc']}_{kpi}_{alloc_year}"] = _new
                                else:
                                    # Custom ratio — read from ratio inputs below
                                    _ratios = {_er["sc"]: float(st.session_state.get(
                                        f"cratio_{_er['sc']}_{kpi}_{alloc_year}", 1.0))
                                        for _er in _eligible}
                                    _rat_sum = sum(_ratios.values()) or 1
                                    for _er in _eligible:
                                        _new = _cur_alloc(_er["sc"]) + _remaining * (_ratios[_er["sc"]] / _rat_sum)
                                        st.session_state[f"ni_raw_{_er['sc']}_{kpi}_{alloc_year}"] = f"{_new:,.0f}" if not pct_kpi else f"{_new:.2f}"
                                        st.session_state[f"v_{_er['sc']}_{kpi}_{alloc_year}"] = _new
                                st.cache_data.clear()
                                st.rerun()

                    # ── Compact input rows per eligible person ─────────────
                    # Show custom ratio inputs if that mode is selected
                    _show_cratio = (not _is_avg and _n_el > 1 and
                                    st.session_state.get(f"ratio_mode_{_grp_uid}_{kpi}_{alloc_year}","equal") == "custom ratio")
                    if _show_cratio:
                        _cr_cols = st.columns([2]+[1]*_n_el)
                        _cr_cols[0].markdown(
                            "<div style='font-size:10px;color:var(--color-text-tertiary);padding:4px 0'>Ratio</div>",
                            unsafe_allow_html=True)
                        for _cri, _er in enumerate(_eligible):
                            _cr_key = f"cratio_{_er['sc']}_{kpi}_{alloc_year}"
                            if _cr_key not in st.session_state:
                                st.session_state[_cr_key] = 1.0
                            _cr_cols[_cri+1].number_input(
                                _er["short"], min_value=0.1, max_value=99.0,
                                step=0.5, format="%.1f", key=_cr_key,
                                label_visibility="collapsed")

                    for r in _eligible:
                        sc_r   = r["sc"]
                        ss_key = f"v_{sc_r}_{kpi}_{alloc_year}"
                        cur_v  = _cur_alloc(sc_r)

                        # Compact 4-column layout: name | input | formatted | share%
                        ic1, ic2, ic3, ic4 = st.columns([1.8, 3, 1.5, 1])

                        ic1.markdown(
                            f"<div style='padding:6px 0;font-size:11px;"
                            f"color:var(--color-text-primary);font-weight:600;white-space:nowrap'>"
                            f"{r['short']}</div>", unsafe_allow_html=True)

                        if pct_kpi:
                            _pct_key = f"ni_{sc_r}_{kpi}_{alloc_year}"
                            if _pct_key not in st.session_state:
                                st.session_state[_pct_key] = float(cur_v)
                            new_v = ic2.number_input(
                                f"{kpi} {sc_r}", min_value=0.0,
                                max_value=100.0, step=0.01, format="%.2f",
                                key=_pct_key, label_visibility="collapsed")
                        elif is_count_kpi(kpi):
                            # Count KPIs — integer input
                            _cnt_key = f"ni_cnt_{sc_r}_{kpi}_{alloc_year}"
                            if _cnt_key not in st.session_state:
                                st.session_state[_cnt_key] = int(cur_v) if cur_v else 0
                            new_v = float(ic2.number_input(
                                f"{kpi} {sc_r}", min_value=0, step=1,
                                key=_cnt_key, label_visibility="collapsed",
                                help=f"Enter count (e.g. 250 for 250 transactions)"))
                            # Also store in raw key for save compatibility
                            st.session_state[f"ni_raw_{sc_r}_{kpi}_{alloc_year}"] = str(int(new_v))
                        else:
                            _raw_key = f"ni_raw_{sc_r}_{kpi}_{alloc_year}"
                            if _raw_key not in st.session_state:
                                st.session_state[_raw_key] = f"{cur_v:,.0f}" if cur_v else ""
                            raw_input = ic2.text_input(
                                f"{kpi} {sc_r}", key=_raw_key,
                                placeholder="e.g. 2,000,000,000",
                                label_visibility="collapsed")
                            try:
                                new_v = float(str(raw_input).replace(",","").replace(" ","") or 0)
                            except (ValueError, TypeError):
                                new_v = cur_v

                        st.session_state[ss_key] = new_v
                        _disp = (f"{int(round(new_v)):,}" if is_count_kpi(kpi) and not pct_kpi
                                 else fmt_v(new_v, kpi) if not pct_kpi else f"{new_v:.2f}%")
                        ic3.markdown(
                            f"<div style='padding:6px 2px;font-size:11px;"
                            f"font-weight:700;color:var(--brand-primary,#006B3F);text-align:right'>"
                            f"{_disp if new_v else '—'}</div>", unsafe_allow_html=True)
                        # Share of pool (additive KPIs only)
                        if not _is_avg and stretch_tgt and new_v:
                            _share = new_v / stretch_tgt * 100
                            ic4.markdown(
                                f"<div style='padding:6px 2px;font-size:10px;"
                                f"color:var(--color-text-tertiary);text-align:right'>"
                                f"{_share:.0f}%</div>", unsafe_allow_html=True)

        # ── PER-GROUP SAVE — rendered after all group tables/inputs ─
        today_d = _dt.date.today()
        tl_now  = casc.get_global_timeline(alloc_year)
        max_d   = (_safe_date(tl_now["cascade_end_date"])
                   if tl_now else today_d+_dt.timedelta(days=90))

        for grp_name_sv, grp_df_sv in rep_groups:
            _uid_sv = grp_name_sv.replace(" ","_").replace("/","_")[:12] if grp_name_sv else "all"
            _n_sv   = len(grp_df_sv)
            _lbl_sv = grp_name_sv if grp_name_sv else "All reportees"

            # Show save section immediately after each group
            st.markdown(
                f"<div style='background:#F0FDF4;border:1px solid #BBF7D0;"
                f"border-radius:8px;padding:10px 14px;margin:8px 0'>"
                f"<span style='font-size:12px;font-weight:700;color:#166534'>"
                f"💾 Save & cascade → {_lbl_sv} ({_n_sv} person(s))</span></div>",
                unsafe_allow_html=True)

            sv1, sv2, sv3 = st.columns(3)
            _conf_k = f"conf_{_uid_sv}_{alloc_year}"
            _casc_k = f"casc_{_uid_sv}_{alloc_year}"
            sv_conf = sv1.date_input("Confirm by", key=_conf_k,
                value=today_d+_dt.timedelta(days=5),
                min_value=today_d, max_value=max_d)
            sv_casc = sv2.date_input("Cascade by", key=_casc_k,
                value=today_d+_dt.timedelta(days=14),
                min_value=today_d, max_value=max_d)

            if sv3.button(f"💾 Cascade → {_lbl_sv}",
                          key=f"save_grp_{_uid_sv}_{alloc_year}",
                          type="primary", use_container_width=True):
                _vld, _vmsg = casc.validate_deadline_against_global(
                    alloc_year, my_rl, str(sv_conf), str(sv_casc))
                if not _vld:
                    st.error(f"❌ {_vmsg}")
                else:
                    _saved_sv = 0
                    for _, _dr_sv in grp_df_sv.iterrows():
                        _dr_nm_sv = _dr_sv["Staff Name"]
                        _dr_sc_sv = str(_dr_sv.get("Staff Code",""))
                        _dr_rl_sv = _dr_sv.get("Role","")
                        _dr_un_sv = _dr_sv.get("Unit","")
                        if casc.targets_locked(_dr_sc_sv, alloc_year): continue
                        _kpi_keys = set()
                        for _sk in st.session_state:
                            if _sk.startswith(f"v_{_dr_sc_sv}_") and _sk.endswith(f"_{alloc_year}"):
                                _kpi_keys.add(_sk[len(f"v_{_dr_sc_sv}_"):-len(f"_{alloc_year}")])
                            if _sk.startswith(f"ni_raw_{_dr_sc_sv}_") and _sk.endswith(f"_{alloc_year}"):
                                _kpi_keys.add(_sk[len(f"ni_raw_{_dr_sc_sv}_"):-len(f"_{alloc_year}")])
                            if _sk.startswith(f"ni_{_dr_sc_sv}_") and _sk.endswith(f"_{alloc_year}"):
                                _kpi_keys.add(_sk[len(f"ni_{_dr_sc_sv}_"):-len(f"_{alloc_year}")])
                        for _kp in _kpi_keys:
                            _raw = st.session_state.get(f"ni_raw_{_dr_sc_sv}_{_kp}_{alloc_year}","")
                            if _raw:
                                try: _amt = float(str(_raw).replace(",","").replace(" ","") or 0)
                                except: _amt = 0.0
                            else:
                                _amt = float(st.session_state.get(f"v_{_dr_sc_sv}_{_kp}_{alloc_year}", 0.0))
                                if not _amt:
                                    _amt = float(st.session_state.get(f"ni_{_dr_sc_sv}_{_kp}_{alloc_year}", 0.0))
                            if _amt == 0: continue
                            _ex = casc.get_allocation(my_code, _kp, alloc_year)
                            _cl = [a for a in (_ex["allocations"] if _ex else [])
                                   if a.get("to_code") != _dr_sc_sv]
                            _cl.append({"to_code":_dr_sc_sv,"to_name":_dr_nm_sv,
                                        "to_role":_dr_rl_sv,"to_unit":_dr_un_sv,"amount":_amt})
                            casc.set_allocation(my_code, _kp, alloc_year, _cl, _amt)
                            _saved_sv += 1
                        casc.set_cascade_deadline(_dr_sc_sv, alloc_year,
                            str(sv_conf), str(sv_casc), uname)
                        audit_log("CASCADE_ALLOC", uname, f"{_dr_nm_sv}|{alloc_year}")
                        _bsc_trigger(uname, "K017")
                    st.toast(f"✅ Cascaded to {_n_sv} in {_lbl_sv}", icon="✅")
                    st.cache_data.clear()
                    st.rerun()
        st.markdown("---")
        st.caption("💡 Use the expandable save sections above to cascade by group with individual timelines.")

        # ── GLOBAL SAVE (all at once) ─────────────────────────────────
        with st.expander("💾 Save & cascade ALL groups at once", expanded=False):
          dl_c1,dl_c2 = st.columns(2)
          bulk_conf = dl_c1.date_input(
              "Confirm-by date (all)",
              value=today_d+_dt.timedelta(days=5),
              min_value=today_d, max_value=max_d, key="bulk_conf")
          bulk_casc = dl_c2.date_input(
              "Cascade-by date (all)",
              value=today_d+_dt.timedelta(days=14),
              min_value=today_d, max_value=max_d, key="bulk_casc")

          if st.button(
                f"💾 Save & cascade to all {len(d_sorted)} direct report(s)",
                type="primary", use_container_width=True, key="save_all"):
            valid, msg = casc.validate_deadline_against_global(
                alloc_year, my_rl, str(bulk_conf), str(bulk_casc))
            if not valid:
                st.error(f"❌ {msg}")
            else:
                saved_people = 0
                for _, dr_row in d_sorted.iterrows():
                    dr_nm = dr_row["Staff Name"]
                    dr_sc = str(dr_row.get("Staff Code",""))
                    dr_rl = dr_row.get("Role","")
                    dr_un = dr_row.get("Unit","")
                    if casc.targets_locked(dr_sc, alloc_year): continue
                    saved_kpis = 0
                    for grp_name, grp_df in rep_groups:
                        if dr_nm not in grp_df["Staff Name"].values: continue
                        for kpi_set_key in group_kpi_set if grp_name else {}:
                            pass  # rebuilt below
                    # Use all ss_keys for this person
                    _g_kpi_keys = set()
                    for _gk in st.session_state:
                        if _gk.startswith(f"v_{dr_sc}_") and _gk.endswith(f"_{alloc_year}"):
                            _g_kpi_keys.add(_gk[len(f"v_{dr_sc}_"):-len(f"_{alloc_year}")])
                        if _gk.startswith(f"ni_raw_{dr_sc}_") and _gk.endswith(f"_{alloc_year}"):
                            _g_kpi_keys.add(_gk[len(f"ni_raw_{dr_sc}_"):-len(f"_{alloc_year}")])
                        if _gk.startswith(f"ni_{dr_sc}_") and _gk.endswith(f"_{alloc_year}"):
                            _g_kpi_keys.add(_gk[len(f"ni_{dr_sc}_"):-len(f"_{alloc_year}")])
                    for kpi_part in _g_kpi_keys:
                        _raw_g = st.session_state.get(f"ni_raw_{dr_sc}_{kpi_part}_{alloc_year}","")
                        if _raw_g:
                            try: amt = float(str(_raw_g).replace(",","").replace(" ","") or 0)
                            except: amt = 0.0
                        else:
                            amt = float(st.session_state.get(f"v_{dr_sc}_{kpi_part}_{alloc_year}", 0.0))
                            if not amt:
                                amt = float(st.session_state.get(f"ni_{dr_sc}_{kpi_part}_{alloc_year}", 0.0))
                        if amt == 0: continue
                        my_kpi_r = (df_proc[(df_proc["Staff Name"]==ud.get("full_name",""))
                                            &(df_proc["KPI"]==kpi_part)]
                                    if not df_proc.empty else pd.DataFrame())
                        my_pool = float(pd.to_numeric(
                            my_kpi_r["Annual Target"].values[0],
                            errors="coerce") or 0) if len(my_kpi_r) else 0
                        cur_alloc = casc.get_allocation(my_code, kpi_part, alloc_year)
                        cur_list  = [a for a in (cur_alloc["allocations"] if cur_alloc else [])
                                     if a.get("to_code") != dr_sc]
                        cur_list.append({"to_code":dr_sc,"to_name":dr_nm,
                                          "to_role":dr_rl,"to_unit":dr_un,"amount":amt})
                        casc.set_allocation(my_code, kpi_part, alloc_year,
                                            cur_list, my_pool or amt)
                        saved_kpis += 1
                    casc.set_cascade_deadline(
                        dr_sc, alloc_year, str(bulk_conf), str(bulk_casc), uname)
                    saved_people += 1
                    audit_log("CASCADE_ALLOC", uname,
                              f"{dr_nm}|{alloc_year}|{saved_kpis}KPIs")
                    _bsc_trigger(uname, "K017")
                # Clear inputs
                for k in list(st.session_state.keys()):
                    if k.startswith("v_") and k.endswith(f"_{alloc_year}"):
                        del st.session_state[k]
                st.toast(f"✅ Targets cascaded to {saved_people} people", icon="✅")
                st.cache_data.clear()
                st.rerun()


# TAB 4 — MY TARGETS (accept, request review, lock)
# ══════════════════════════════════════════════════════════════════
_tab_visible_my_targets, _tab_idx_my_targets = _in_tab("my_targets")
if _tab_visible_my_targets:
  with tabs[_tab_idx_my_targets]:
    my_name  = ud.get("full_name","")
    # Try primary code lookup, then fallback to username, then to full name search
    my_given = casc.get_what_i_was_given(my_code, period, my_name_l) if casc else []
    if not my_given and uname != my_code and casc:
        my_given = casc.get_what_i_was_given(uname, period, my_name_l)
    _raw_sc = str(ud.get("staff_code","")).strip()
    if not my_given and _raw_sc and _raw_sc != my_code and casc:
        my_given = casc.get_what_i_was_given(_raw_sc, period, my_name_l)

    # Fixed KPIs — always present regardless of cascade status
    _my_fixed_kpis = {}   # {kpi: target_value}
    if casc:
        for kpi_fp in casc.get_fixed_kpis(period):
            bt = casc.get_bank_target(kpi_fp, period)
            if bt and bt.get("target"):
                _my_fixed_kpis[kpi_fp] = bt["target"]
    given_map= {g["kpi"]: g["amount"] for g in my_given}
    locked_me= casc.targets_locked(my_code, period, my_name_l)

    # ── Debug panel — admin only ─────────────────────────────────────
    if ud.get("is_admin"):
        with st.expander("🔧 Debug — cascade lookup (admin only)", expanded=not bool(my_given)):
            st.markdown(f"""
**Logged-in user:** `{my_name_l}` · username: `{uname}`  
**Stored staff_code in account:** `{ud.get('staff_code','')}` | **Resolved from BSC:** `{_resolved_code}` | **Final my_code:** `{my_code}`  
**Period:** `{period}` | **my_given entries:** `{len(my_given)}`  

👉 **To fix permanently:** go to Admin → Users → Edit this user → set Staff Code to `{_resolved_code}`
            """)
            if casc and casc.cascade:
                alloc_entries = {k:v for k,v in casc.cascade.items()
                                 if not k.startswith("deadline|") and not k.startswith("global_")}
                st.markdown(f"**Total allocation entries in cascade store:** `{len(alloc_entries)}`")
                if alloc_entries:
                    st.markdown("**All `to_code` / `to_name` values stored:**")
                    seen = set()
                    for k,e in alloc_entries.items():
                        for a in e.get("allocations",[]):
                            key_pair = (str(a.get("to_code","")), str(a.get("to_name","")))
                            if key_pair not in seen:
                                seen.add(key_pair)
                                match = (str(a.get("to_code",""))==my_code or
                                         my_name_l.lower() in str(a.get("to_name","")).lower())
                                st.markdown(f"  - code: `{a.get('to_code','')}` · name: `{a.get('to_name','')}` {'✅ **MATCH**' if match else ''}")
            else:
                st.warning("⚠️ casc.cascade is empty — no allocations have been saved yet. "
                           "The MD needs to save targets in the 'Set team targets' tab first.")

    # Deadline + action cards
    my_dl = casc.get_cascade_deadline(my_code, period, my_name_l)
    if my_dl:
        today_d  = _dt.date.today()
        conf_due = _safe_date(my_dl.get("confirm_by") or my_dl.get("locked_at",""))
        casc_due = _safe_date(my_dl.get("cascade_by") or my_dl.get("locked_at",""))
        confirmed= my_dl.get("confirmed",False)
        cascaded = my_dl.get("cascaded",False)
        dl_score = casc.deadline_compliance_score(my_code, period)

        dc1,dc2,dc3 = st.columns(3)
        def status_card(done, due, icon_done, icon_pend, label_done, label_pend, col):
            overdue = not done and due < today_d
            bg  = "#F0FDF4" if done else ("#FEF2F2" if overdue else "#FFF7ED")
            brd = "#BBF7D0" if done else ("#FCA5A5" if overdue else "#FED7AA")
            clr = "#166534" if done else ("#991B1B" if overdue else "#92400E")
            col.markdown(
                f"<div style='padding:12px;background:{bg};border:1px solid {brd};"
                f"border-radius:8px;text-align:center'>"
                f"<div style='font-size:22px'>{'✅' if done else ('🔴' if overdue else icon_pend)}</div>"
                f"<div style='font-size:11px;font-weight:600;color:{clr};margin-top:4px'>"
                f"{'⚡ ' if overdue else ''}{label_done if done else label_pend}</div>"
                f"<div style='font-size:10px;color:{clr};margin-top:2px'>by {due}</div>"
                f"</div>", unsafe_allow_html=True)
        status_card(confirmed, conf_due, "⏰","⏰","Targets confirmed","Confirm by",dc1)
        status_card(cascaded,  casc_due, "🔽","🔽","Cascade complete","Cascade by",dc2)
        dc3.metric("Cascade diligence", f"{dl_score:.0f}/100",
                   delta_color="normal" if dl_score>=90 else "inverse")
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    if locked_me:
        st.success("🔒 Your targets are locked and tracking is live. BSC actuals are being measured against your agreed targets.")
    
    # For MD: load bank targets as own targets
    if is_md and casc:
        # MD always sees bank targets as own targets — refresh from bank_targets
        _bt_map = {}
        for kpi_bt, bt_entry in (getattr(casc,"bank_targets",{}) or {}).items():
            if str(bt_entry.get("period","")) == period:
                kpi_nm = bt_entry.get("kpi","")
                if kpi_nm and bt_entry.get("target"):
                    _bt_map[kpi_nm] = float(bt_entry["target"])
        if _bt_map:
            # Merge bank targets into given_map (bank target is MD's target)
            for _kn, _kv in _bt_map.items():
                given_map.setdefault(_kn, _kv)
            if not my_given:
                my_given = [{"kpi":k,"amount":v,"period":period,
                             "from_code":"bank","my_share":100}
                            for k,v in given_map.items()]
            st.markdown(
                "<div style='padding:10px 14px;background:var(--brand-light,#E8F5EE);"
                "border:1px solid #BBF7D0;border-radius:8px;font-size:12px;"
                "color:#166534;margin-bottom:10px'>"
                "🏦 <b>MD targets</b> — Your targets are the bank-level targets. "
                "Fixed KPIs apply bank-wide. Stretch targets computed with your buffer.</div>",
                unsafe_allow_html=True)

    if not my_given and not locked_me and not is_md:
        st.markdown(
            "<div style='padding:12px 16px;background:#FEF3C7;border:1px solid #FDE68A;"
            "border-radius:8px;margin-bottom:12px;font-size:12px;color:#92400E'>"
            "<b>⏳ No cascaded targets found for your profile yet.</b><br>"
            "Your manager needs to set and cascade targets to you. "
            "Contact them or check the Bank Targets timeline."
            "</div>", unsafe_allow_html=True)

    if my_given or locked_me:
        # Pending review requests
        my_rrs = [r for r in casc.get_review_requests(period, my_code)
                  if r["status"]=="Pending"]
        if my_rrs:
            st.warning(f"⏳ You have {len(my_rrs)} pending review request(s). Awaiting manager response.")

        act1, act2, act3 = st.columns(3)
        if not my_dl or not my_dl.get("confirmed"):
            if act1.button("✅ I accept my targets — lock & begin tracking",
                           type="primary", use_container_width=True):
                casc.mark_confirmed(my_code, period)
                casc.lock_targets(my_code, period)
                audit_log("TARGET_ACCEPTED_LOCKED", uname, period,
                          module="cascade",
                          detail=f"{my_code}|{period}|accepted+locked")
                _bsc_trigger(uname, "K017")
                # Clear BSC cache so scorecard reloads with new targets
                for _ck in ["df_processed","staff_scores","filtered_staff",
                             "_cbs_loaded_file","_cbs_mtime"]:
                    st.session_state.pop(_ck, None)
                st.toast("🔒 Targets accepted and locked. Tracking begins now!", icon="🔒")
                st.cache_data.clear()
                st.rerun()
        elif not locked_me:
            if act1.button("🔒 Lock targets & start tracking", type="primary",
                           use_container_width=True):
                casc.lock_targets(my_code, period)
                # lock_targets() now handles: locked_targets.json + xlsx injection
                audit_log("TARGETS_LOCKED", uname, period,
                          module="cascade",
                          detail=f"{my_code}|{period}|locked")
                _bsc_trigger(uname, "K017")
                # Clear BSC cache so scorecard reloads with updated targets immediately
                for _ck in ["df_processed","staff_scores","filtered_staff",
                             "_cbs_loaded_file","_cbs_mtime"]:
                    st.session_state.pop(_ck, None)
                st.success("🔒 Targets locked — scorecard updating now.")
                st.cache_data.clear()
                st.rerun()

        if not locked_me and is_mgr:
            if act2.button("🔽 Mark cascade complete", use_container_width=True):
                casc.mark_cascaded(my_code, period)
                # Inject targets to all allocatees when manager completes cascade
                try:
                    _act_cascade = sorted(
                        [f for f in (Path(__file__).parent.parent/"data").glob("actuals_*.xlsx")
                         if "backup" not in f.name], reverse=True)
                    if _act_cascade:
                        from utils.actuals_engine import inject_cascade_targets
                        inject_cascade_targets(_act_cascade[0])
                except Exception:
                    pass
                audit_log("CASCADE_DONE", uname, period,
                          module="cascade", detail=f"{my_code}|{period}")
                _bsc_trigger(uname, "K017")
                for _ck in ["df_processed","staff_scores","filtered_staff",
                             "_cbs_loaded_file"]:
                    st.session_state.pop(_ck, None)
                st.toast("✅ Cascade marked complete — allocatees' targets updated", icon="✅")
                st.cache_data.clear()
                st.rerun()

        # Review request
        with act3.expander("🔍 Request target review"):
            rr_kpi = st.selectbox("KPI to review", list(given_map.keys()) or all_kpis,
                                   key="rr_kpi")
            rr_given   = float(given_map.get(rr_kpi, 0))
            rr_pct_kpi = is_pct(rr_kpi)

            # Compute allowed review range:
            # MD:      can propose ≥ bank target (cannot go below their own bank target)
            # Others:  can only adjust within the buffer applied by their line manager
            #          i.e. proposed must be between bank_target and received_cascade_target
            _rr_bt  = casc.get_bank_target(rr_kpi, period)
            _rr_bv  = float(_rr_bt["target"]) if _rr_bt else 0.0
            _rr_buf = float(_rr_bt.get("buffer_pct",0)) if _rr_bt else 0.0
            _rr_dir = -1 if is_reduce(rr_kpi) else 1
            _rr_stretch = round(_rr_bv * (1 + _rr_dir * _rr_buf / 100), 4) if _rr_bv and _rr_buf else _rr_bv

            if is_md:
                # MD can request below bank target (asking board to lower it)
                # but not below 50% of bank target as a sanity check
                _rr_min = _rr_bv * 0.5
                _rr_max = _rr_stretch * 1.2
                _rr_hint = (f"Allowed range: {fmt_v(_rr_min,rr_kpi)} – {fmt_v(_rr_max,rr_kpi)}. "
                            f"Must not go below 50% of bank target without board approval.")
            else:
                # Line manager: can propose between bank target and received cascade amount
                # Buffer is the negotiation space — cannot go lower than bank target
                if _rr_dir == 1:  # growth KPI — lower=less stretch
                    _rr_min = _rr_bv        # bank target floor
                    _rr_max = rr_given * 1.0  # received amount ceiling
                else:  # reduce KPI — higher=less stretch
                    _rr_min = rr_given * 1.0  # received amount floor
                    _rr_max = _rr_bv          # bank target ceiling
                _rr_hint = (f"Review range: {fmt_v(_rr_min,rr_kpi)} – {fmt_v(_rr_max,rr_kpi)}. "
                            f"Cannot go beyond your received target. Buffer is the negotiation space.")

            st.caption(_rr_hint)
            rr_reason = st.text_area("Reason for review request", height=60, key="rr_reason",
                placeholder="e.g. Market conditions indicate target needs adjustment...")

            rr_target = st.number_input(
                "My proposed target",
                value=rr_given,
                min_value=0.0,
                step=kpi_step(rr_kpi),
                key="rr_proposed")

            # Validate within allowed range
            _rr_valid = True
            if not is_md:
                _lo = min(_rr_min, _rr_max)
                _hi = max(_rr_min, _rr_max)
                if rr_target < _lo * 0.999 or rr_target > _hi * 1.001:
                    st.error(f"❌ Proposed target {fmt_v(rr_target,rr_kpi)} is outside the "
                             f"allowed review range ({fmt_v(_lo,rr_kpi)} – {fmt_v(_hi,rr_kpi)}). "
                             f"You can only negotiate within the buffer applied by your manager.")
                    _rr_valid = False

            if st.button("Send review request", type="secondary") and _rr_valid:
                if rr_reason.strip():
                    casc.request_review(my_code, my_name, period, rr_kpi,
                                        rr_reason, rr_target)
                    audit_log("REVIEW_REQUEST", uname,
                              f"{period}|{rr_kpi}|proposed:{rr_target}")
                    _bsc_trigger(uname, "K017")
                    st.toast("✅ Review request sent to your manager", icon="📨")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("Please provide a reason.")

    # ── Target summary cards ─────────────────────────────────────────
    if given_map:
        _kpi_cats = {"Financial":[],"Customer Focus":[],"Operational Excellence":[]}
        _df_kpi   = df_proc[df_proc["Staff Name"]==my_name_l] if not df_proc.empty else pd.DataFrame()
        for _gkpi, _gamt in given_map.items():
            _pillar = "Financial"
            if not _df_kpi.empty:
                _pr = _df_kpi[_df_kpi["KPI"]==_gkpi]
                if len(_pr): _pillar = str(_pr["Pillar"].iloc[0])
            _kpi_cats.get(_pillar,[]).append((_gkpi, float(_gamt)))

        _pclrs = {"Financial":"var(--brand-primary,#006B3F)","Customer Focus":"#185FA5",
                  "Operational Excellence":"#6B21A8"}
        _pbgs  = {"Financial":"var(--brand-light,#E8F5EE)","Customer Focus":"#EFF6FF",
                  "Operational Excellence":"#F3E8FF"}
        for _pil, _kpis in _kpi_cats.items():
            if not _kpis: continue
            _pc = _pclrs.get(_pil,"#374151"); _pb = _pbgs.get(_pil,"#F9FAFB")
            st.markdown(
                f"<div style='background:{_pb};border-left:3px solid {_pc};"
                f"border-radius:0 6px 6px 0;padding:6px 12px;font-size:10px;"
                f"font-weight:700;color:{_pc};text-transform:uppercase;"
                f"letter-spacing:0.5px;margin:10px 0 4px'>{_pil}</div>",
                unsafe_allow_html=True)
            _card_cols = st.columns(min(4, len(_kpis)))
            for _ci, (_kn, _kv) in enumerate(_kpis):
                _is_fix = _kn in _my_fixed_kpis
                _cc = _card_cols[_ci % len(_card_cols)]
                _cc.markdown(
                    f"<div style='padding:10px 12px;background:var(--color-background-primary);"
                    f"border:1px solid {'#FDE68A' if _is_fix else '#E5E7EB'};"
                    f"border-radius:8px;margin-bottom:6px'>"
                    f"<div style='font-size:10px;color:var(--color-text-tertiary);margin-bottom:4px'>"
                    f"{'🔒 FIXED — ' if _is_fix else ''}{_kn}</div>"
                    f"<div style='font-size:16px;font-weight:700;color:{_pc}'>"
                    f"{fmt_v(_kv,_kn)}</div>"
                    f"</div>", unsafe_allow_html=True)

    st.markdown("---")

    # BSC scorecard table
    if my_name and not df_proc.empty:
        my_kpis = df_proc[df_proc["Staff Name"]==my_name].copy()
        if not my_kpis.empty:
            my_bsc = staff_scores[staff_scores["Staff Name"]==my_name]
            if len(my_bsc):
                m=my_bsc.iloc[0]
                mc1,mc2,mc3,mc4=st.columns(4)
                mc1.metric("BSC Score",f"{m['Final_BSC_Score']:.2f}/5.0")
                mc2.metric("Rank",f"#{m['Overall_Rank']}")
                mc3.metric("Performance",m["Performance_Remark"])
                mc4.metric("Percentile",f"{m.get('Percentile',0):.0f}th")
            st.markdown("---")

            for pillar in PILLARS:
                pk = my_kpis[my_kpis["Pillar"]==pillar] if "Pillar" in my_kpis.columns else pd.DataFrame()
                if pk.empty: continue
                pclr=PC[pillar]; picon=PI[pillar]
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:8px;padding:9px 14px;"
                    f"background:{pclr};border-radius:8px;margin:16px 0 4px'>"
                    f"<span>{picon}</span>"
                    f"<span style='color:var(--color-background-primary);font-weight:700;font-size:13px'>{pillar}</span>"
                    f"</div>", unsafe_allow_html=True)
                st.markdown(
                    "<div style='display:grid;"
                    "grid-template-columns:2fr 0.5fr 1fr 0.8fr 1.2fr 1fr 1fr 0.7fr;"
                    "gap:6px;padding:5px 12px;background:var(--color-background-secondary);border-radius:6px;"
                    "font-size:10px;font-weight:700;color:var(--color-text-secondary);"
                    "text-transform:uppercase;letter-spacing:0.4px;margin-bottom:2px'>"
                    "<span>KPI</span><span>Wt</span>"
                    "<span>FY-25</span><span>FY-25 %</span>"
                    "<span>2026 Target</span><span>Cascaded</span>"
                    "<span>YTD Actual</span><span>Score</span></div>",
                    unsafe_allow_html=True)
                for _,r in pk.iterrows():
                    kpi      = r.get("KPI","")
                    wt       = float(pd.to_numeric(r.get("Weight",0),errors="coerce") or 0)
                    act      = float(pd.to_numeric(r.get("YTD_Actual",r.get("Annual Actual",0)),errors="coerce") or 0)
                    ct       = given_map.get(kpi)  # cascaded target from line manager
                    is_fixed = kpi in _my_fixed_kpis

                    # Target resolution — cascade is single source of truth
                    # Fixed KPIs: use bank-level fixed target always
                    # Cascaded KPIs: use amount given by line manager
                    # Otherwise: blank (—)
                    if is_fixed:
                        tgt = _my_fixed_kpis[kpi]
                    elif ct:
                        tgt = float(ct)
                    else:
                        tgt = None   # not yet set

                    # Score and achievement
                    # Fixed KPIs: always compute (non-negotiable targets)
                    # Others: only when locked
                    if is_fixed and tgt:
                        sc  = float(pd.to_numeric(r.get("Score",0),errors="coerce") or 0)
                        pct = round(act/tgt*100,1) if tgt else 0.0
                    elif locked_me and tgt:
                        sc  = float(pd.to_numeric(r.get("Score",0),errors="coerce") or 0)
                        pct = round(act/tgt*100,1) if tgt else 0.0 if tgt else None
                    else:
                        sc  = None
                        pct = None

                    fy25,_    = get_prior(my_name,kpi)
                    fy25_pct  = round(fy25/tgt*100,1) if tgt and fy25 else 0
                    pct_clr   = score_color(pct) if pct is not None else "#D1D5DB"
                    fy_clr    = score_color(fy25_pct) if fy25_pct else "#9CA3AF"
                    sc_clr    = score_color(sc/5*100) if sc is not None else "#D1D5DB"

                    # Visual states
                    if is_fixed:
                        row_bg   = "#FFFBEB"   # amber — fixed
                        row_bord = "#FDE68A"
                        kpi_pfx  = ("🔒 <span style='background:#FDE68A;color:#92400E;"
                                    "font-size:8px;font-weight:700;padding:1px 4px;"
                                    "border-radius:3px;margin-right:3px'>FIXED</span>")
                        tgt_cell = (f"<span style='color:#92400E;font-weight:700'>"
                                    f"🔒 {fmt_v(tgt,kpi)}</span>")
                    elif locked_me:
                        row_bg   = "#F0FDF4"
                        row_bord = "#BBF7D0"
                        kpi_pfx  = ""
                        tgt_cell = (f"<span style='font-weight:700'>"
                                    f"{fmt_v(tgt,kpi) if tgt else '—'}</span>")
                    elif tgt:
                        row_bg   = "#EFF6FF"   # blue — cascaded, not yet locked
                        row_bord = "#BFDBFE"
                        kpi_pfx  = ""
                        tgt_cell = (f"<span style='color:#185FA5;font-weight:700'>"
                                    f"{fmt_v(tgt,kpi)}</span>")
                    else:
                        row_bg   = "var(--color-background-primary)"
                        row_bord = "#F0F0F0"
                        kpi_pfx  = ""
                        tgt_cell = "<span style='color:#D1D5DB'>—</span>"

                    sc_cell = (f"<span style='color:{sc_clr};font-weight:800'>{sc:.2f}</span>"
                               if sc is not None else
                               ("<span style='color:#F59E0B;font-size:10px'>⏳ live</span>"
                                if is_fixed else
                                "<span style='color:#D1D5DB;font-size:10px'>⏳</span>"))
                    pct_cell = (f"<span style='color:{pct_clr};font-weight:700'>{fmt_v(act,kpi)}</span>"
                                if pct is not None else
                                f"<span style='color:var(--color-text-secondary);font-weight:600'>{fmt_v(act,kpi)}</span>")

                    st.markdown(
                        f"<div style='display:grid;"
                        f"grid-template-columns:2fr 0.5fr 1fr 0.8fr 1.2fr 1fr 1fr 0.7fr;"
                        f"gap:6px;padding:7px 12px;background:{row_bg};"
                        f"border:1px solid {row_bord};"
                        f"border-radius:8px;margin:2px 0;font-size:12px;align-items:center'>"
                        f"<span style='font-weight:600;color:var(--color-text-primary)'>{kpi_pfx}{kpi}</span>"
                        f"<span style='color:var(--color-text-secondary)'>{wt*100:.0f}%</span>"
                        f"<span>{fmt_v(fy25,kpi) if fy25 else '—'}</span>"
                        f"<span style='color:{fy_clr};font-weight:700'>"
                        f"{'—' if not fy25_pct else f'{fy25_pct:.1f}%'}</span>"
                        f"{tgt_cell}"
                        f"<span style='color:#185FA5;font-weight:700'>"
                        f"{fmt_v(ct,kpi) if ct else '—'}</span>"
                        f"{pct_cell}"
                        f"{sc_cell}"
                        f"</div>", unsafe_allow_html=True)
    else:
        st.info("No BSC data found for your profile.")

# ══════════════════════════════════════════════════════════════════
# TAB 5 — CASCADE TREE
# ══════════════════════════════════════════════════════════════════
_tab_visible_cascade_tree, _tab_idx_cascade_tree = _in_tab("cascade_tree")
if _tab_visible_cascade_tree:
  with tabs[_tab_idx_cascade_tree]:
    st.subheader("Cascade tree")
    if not all_kpis: st.info("No KPI data."); st.stop()
    t1,t2 = st.columns(2)
    kpi_opts = [f"{PI.get(get_pillar(k),'')} {k}" for k in all_kpis]
    sd = t1.selectbox("KPI",kpi_opts,key="tree_kpi")
    sel_kpi = sd.split(" ",1)[1] if " " in sd else sd
    t_per   = t2.selectbox("Period",[_gfy_casc(),"2025"],key="tree_per")

    bt = casc.get_bank_target(sel_kpi,t_per)
    if bt:
        st.markdown(
            f"<div style='padding:10px 16px;background:#F0FDF4;border:1px solid #BBF7D0;"
            f"border-radius:8px;margin:8px 0;font-size:12px'>"
            f"🏦 Bank: <b>{fmt_v(bt['target'],sel_kpi)}</b>"
            +(f"&nbsp;+&nbsp;{bt['buffer_pct']}% → stretch <b>{fmt_v(bt['stretch_target'],sel_kpi)}</b>"
              if bt['buffer_pct'] else "")
            +(f"&nbsp;·&nbsp;🔒 Fixed" if casc.is_fixed(sel_kpi,t_per) else "")+"</div>",
            unsafe_allow_html=True)

    def build_tree(role,depth=0,unit=None):
        items=[]
        subs=HIERARCHY.get(role,[])
        ls=staff_scores[staff_scores["Role"]==role] if len(staff_scores) else pd.DataFrame()
        # Only apply unit filter for truly unit-scoped roles
        _tree_unit_scoped = {
            "Regional Head","Branch Manager","Branch Operations Manager",
            "Branch Credit Manager","IT Manager","Operations Manager",
        }
        if unit and role in _tree_unit_scoped: ls=ls[ls["Unit"]==unit]
        for _,p in ls.iterrows():
            sc=str(p.get("Staff Code","")); nm=p.get("Staff Name","")
            up=p.get("Unit",""); bsc=p.get("Final_BSC_Score",0)
            kr=df_proc[(df_proc["Staff Name"]==nm)&(df_proc["KPI"]==sel_kpi)] if not df_proc.empty else pd.DataFrame()
            tgt=float(kr["Annual Target"].values[0]) if len(kr) else 0
            act=float(pd.to_numeric(kr["YTD_Actual"].values[0],errors="coerce") or 0) if len(kr) and "YTD_Actual" in kr.columns else 0
            fy25=0.0
            if len(kr):
                for col in ["FY-25 Actual","Annual Actual"]:
                    if col in kr.columns:
                        fy25=float(pd.to_numeric(kr[col].values[0],errors="coerce") or 0)
                        if fy25>0: break
            _,_,cov,_=casc.cascade_coverage(sc,sel_kpi,t_per)
            lk=casc.targets_locked(sc,t_per)
            items.append({"d":depth,"n":nm,"r":role,"u":up,"tgt":tgt,"act":act,
                           "fy25_pct":round(fy25/tgt*100,1) if tgt and fy25 else 0,
                           "ach":round(act/tgt*100,1) if tgt else 0,"bsc":bsc,
                           "cov":cov,"nh":is_new_hire(nm),"locked":lk})
            for s in subs: items.extend(build_tree(s,depth+1,up))
        return items

    tree=build_tree("MD / CEO")[:50]
    if tree:
        # Summary counts
        _tr_total   = len(tree)
        _tr_locked  = sum(1 for t in tree if t["locked"])
        _tr_cov_ok  = sum(1 for t in tree if t["cov"]>=90)
        _tr_no_tgt  = sum(1 for t in tree if not t["tgt"])
        _ts1,_ts2,_ts3,_ts4 = st.columns(4)
        _ts1.metric("In cascade", _tr_total)
        _ts2.metric("🔒 Targets locked", _tr_locked)
        _ts3.metric("✅ Coverage ≥90%", _tr_cov_ok)
        _ts4.metric("⚠️ No target set", _tr_no_tgt)

        st.markdown(
            "<div style='display:grid;grid-template-columns:2.5fr 0.8fr 1fr 1fr 1.2fr;"
            "gap:6px;padding:6px 12px;background:var(--color-background-secondary);border-radius:6px;"
            "font-size:10px;font-weight:700;color:var(--color-text-secondary);"
            "text-transform:uppercase;letter-spacing:0.4px;margin-bottom:4px'>"
            "<span>Name / Role</span><span>FY-25 %</span>"
            "<span>2026 Target</span><span>YTD</span><span>Cascade</span></div>",
            unsafe_allow_html=True)
        for item in tree:
            ind="&nbsp;"*(item["d"]*6)
            ac_c=score_color(item["ach"])
            fy_c=score_color(item["fy25_pct"]) if item["fy25_pct"] else "#9CA3AF"
            cov=item["cov"]
            bc="var(--brand-primary,#006B3F)" if cov>=95 else "#F5A623" if cov>0 else "#E24B4A"
            cb=(f"<span style='background:{bc};color:var(--color-background-primary);padding:1px 6px;"
                f"border-radius:8px;font-size:10px'>"
                f"{'✓' if cov>=95 else '⚠' if cov>0 else '✗'} {cov:.0f}%</span>")
            lk_b=(" <span style='background:var(--brand-primary,#006B3F);color:var(--color-background-primary);font-size:9px;"
                  "padding:0 4px;border-radius:3px'>🔒</span>" if item["locked"] else "")
            nh_b=(" <span style='background:#185FA5;color:var(--color-background-primary);font-size:9px;"
                  "padding:0 4px;border-radius:3px'>NEW</span>" if item["nh"] else "")
            dc=["var(--brand-primary,#006B3F)","#F5A623","#185FA5","#8E44AD","#9CA3AF"][min(item["d"],4)]
            fy_str = "New" if item["nh"] else (f"{item['fy25_pct']:.0f}%" if item["fy25_pct"] else "—")
            st.markdown(
                f"<div style='display:grid;grid-template-columns:2.5fr 0.8fr 1fr 1fr 1.2fr;"
                f"gap:6px;padding:6px 12px;background:var(--color-background-secondary);"
                f"border-left:{3+item['d']}px solid {dc};"
                f"margin:2px 0;border-radius:0 6px 6px 0;font-size:11px;align-items:center'>"
                f"<div>{ind}<b>{item['n']}</b>{nh_b}{lk_b}<br>"
                f"<span style='color:var(--color-text-tertiary);font-size:10px'>{item['r']}&nbsp;·&nbsp;{item['u']}</span></div>"
                f"<span style='color:{fy_c};font-weight:700'>{fy_str}</span>"
                f"<span style='font-weight:600'>{fmt_v(item['tgt'],sel_kpi)}</span>"
                f"<span style='color:{ac_c}'>{fmt_v(item['act'],sel_kpi)}</span>"
                f"{cb}</div>", unsafe_allow_html=True)
    else:
        st.info("No hierarchy data found.")

# ══════════════════════════════════════════════════════════════════
# TAB 6 — COVERAGE & DEADLINES
# ══════════════════════════════════════════════════════════════════
_tab_visible_coverage, _tab_idx_coverage = _in_tab("coverage")
if _tab_visible_coverage:
  with tabs[_tab_idx_coverage]:
    # Build set of staff codes visible to this user — use their REPORTING TREE only
    # staff_scores is the full 380-staff dataset; filtered_staff is the scoped tree
    _filtered_tree = st.session_state.get("filtered_staff", staff_scores)
    _visible_sc = (set(str(r) for r in _filtered_tree["Staff Code"].astype(str).tolist())
                   if len(_filtered_tree) else set())
    # Always include own code
    _visible_sc.add(str(ud.get("staff_code","") or uname))

    cv1, cv2 = st.columns(2)
    with cv1:
        st.subheader("Allocation coverage")
        rows=[]
        for k,e in casc.cascade.items():
            if k.startswith("deadline|") or k.startswith("global_"): continue
            fc=e["from_code"]
            # Only show entries from managers within this user's visible tree
            if not is_md and fc not in _visible_sc:
                continue
            nr=staff_scores[staff_scores["Staff Code"].astype(str)==fc]
            fn=nr["Staff Name"].values[0] if len(nr) else fc
            t=e["total_target"]; a=e["allocated_sum"]
            cov=round(a/t*100,1) if t else 0
            rows.append({"Manager":fn,"KPI":e["kpi"],"Coverage":f"{cov:.0f}%","_cov":cov})
        if rows:
            cdf=pd.DataFrame(rows)
            st.metric("Avg coverage",f"{cdf['_cov'].mean():.0f}%")
            def hc(v):
                try:
                    p=float(str(v).replace("%",""))
                    if p>=95: return "color:var(--brand-primary,#006B3F);font-weight:600"
                    if p>=50: return "color:#F5A623"
                    return "color:#E24B4A;font-weight:600"
                except: return ""
            st.dataframe(cdf.drop(columns=["_cov"]).style.map(hc,subset=["Coverage"]),
                         use_container_width=True,hide_index=True,height=300)
        else:
            st.info("No allocations recorded yet.")
    with cv2:
        st.subheader("Deadline tracker")
        all_dl=casc.all_deadlines_summary(period)
        # Filter to direct reports of the current manager
        # Get direct report codes from the cascade data (from_code matches manager code)
        _my_dr_codes = set()
        for _k, _e in casc.cascade.items():
            if _k.startswith("deadline|"): continue
            if _k.startswith("global_"): continue
            if _e.get("from_code","") in (my_code, uname, str(ud.get("staff_code",""))):
                for _a in _e.get("allocations",[]):
                    _my_dr_codes.add(str(_a.get("to_code","")))
        # For MD: show all; for others: show only their direct reports
        all_dl=[dl for dl in all_dl
                if is_md or dl["staff_code"] in _my_dr_codes or dl["staff_code"] in _visible_sc]
        if not all_dl:
            st.info("No deadlines set yet. Save & cascade to your team to set deadlines.")
            # Show who the direct reports are for context
            d_rpts_dl = get_reports(my_role_level() or "", my_unit)
            if len(d_rpts_dl):
                st.caption(f"Direct reports: {', '.join(d_rpts_dl['Staff Name'].tolist()[:5])}")
        else:
            dl_rows=[]
            for dl in all_dl:
                sc=dl["staff_code"]
                nr=staff_scores[staff_scores["Staff Code"].astype(str)==sc]
                name=nr["Staff Name"].values[0] if len(nr) else sc
                dl_rows.append({
                    "Staff":name,
                    "Confirm by":dl.get("confirm_by", ""),
                    "Confirmed":"✅" if dl["confirmed"] else ("🔴" if dl["conf_overdue"] else "⏳"),
                    "Cascade by":dl.get("cascade_by", ""),
                    "Cascaded":"✅" if dl["cascaded"] else ("🔴" if dl["casc_overdue"] else "⏳"),
                    "Score":f"{dl['score']:.0f}/100",
                    "Locked":"🔒" if casc.targets_locked(dl["staff_code"],period) else "—",
                })
            dl_df=pd.DataFrame(dl_rows)
            def hd(v):
                if "🔴" in str(v): return "color:#E24B4A;font-weight:600"
                if "✅" in str(v): return "color:var(--brand-primary,#006B3F);font-weight:600"
                return "color:#F5A623"
            st.dataframe(dl_df.style.map(hd,subset=["Confirmed","Cascaded"]),
                         use_container_width=True,hide_index=True,height=300)

# ══════════════════════════════════════════════════════════════════
# TAB 7 — REVIEW REQUESTS
# ══════════════════════════════════════════════════════════════════
_tab_visible_review_requests, _tab_idx_review_requests = _in_tab("review_requests")
if _tab_visible_review_requests:
  with tabs[_tab_idx_review_requests]:
    st.subheader("Target review requests")
    st.caption("Staff who feel their targets need re-evaluation can raise a request here. "
               "Managers review and approve or reject before the staff member accepts.")

    all_rrs = casc.get_review_requests(period)
    if not all_rrs:
        st.info("No review requests raised for this period.")
    else:
        pending = [r for r in all_rrs if r["status"]=="Pending"]
        resolved= [r for r in all_rrs if r["status"]!="Pending"]

        rr1,rr2,rr3 = st.columns(3)
        rr1.metric("Total requests",  len(all_rrs))
        rr2.metric("Pending review",  len(pending),
                   delta_color="inverse" if pending else "off")
        rr3.metric("Resolved",        len(resolved))

        if pending:
            st.markdown(f"#### Pending ({len(pending)})")
            for rr in pending:
                with st.expander(
                    f"⏳ {rr['id']} — {rr['staff_name']} · {rr['kpi']} · raised {rr['raised_at'][:10]}"):
                    rc1,rc2 = st.columns(2)
                    rc1.markdown(
                        f"**Staff:** {rr['staff_name']}  \n"
                        f"**KPI:** {rr['kpi']}  \n"
                        f"**Period:** {rr['period']}  \n"
                        f"**Current cascaded target:** {fmt_v(given_map.get(rr['kpi'],0), rr['kpi'])}  \n"
                        f"**Proposed target:** {fmt_v(rr['requested_target'], rr['kpi'])}")
                    rc2.markdown(f"**Reason:**\n\n{rr['reason']}")

                    if is_mgr:
                        with st.form(f"resolve_{rr['id']}"):
                            rs1,rs2 = st.columns(2)
                            decision = rs1.selectbox("Decision",["Approved","Rejected"],
                                                      key=f"dec_{rr['id']}")
                            response = rs2.text_input("Response to staff",
                                                       key=f"resp_{rr['id']}")
                            if st.form_submit_button("Submit decision", type="primary"):
                                casc.resolve_review(rr["id"], decision, response, uname)
                                audit_log("REVIEW_RESOLVED", uname,
                                          f"{rr['id']}|{decision}")
                                _bsc_trigger(uname, "K017")
                                st.toast(f"✅ Review {decision.lower()} for {rr['staff_name']}", icon="✅")
                                st.cache_data.clear()
                                st.rerun()

        if resolved:
            st.markdown(f"#### Resolved ({len(resolved)})")
            res_df = pd.DataFrame([{
                "ID": r["id"], "Staff": r["staff_name"], "KPI": r["kpi"],
                "Status": r["status"], "Resolved by": r.get("resolved_by","—"),
                "Date": r.get("resolved_at","")[:10] if r.get("resolved_at") else "—",
            } for r in resolved])
            def hl_status(v):
                if v=="Approved": return "color:var(--brand-primary,#006B3F);font-weight:600"
                if v=="Rejected": return "color:#E24B4A;font-weight:600"
                return ""
            st.dataframe(res_df.style.map(hl_status,subset=["Status"]),
                         use_container_width=True,hide_index=True)
