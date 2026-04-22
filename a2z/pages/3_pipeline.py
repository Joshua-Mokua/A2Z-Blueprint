"""pages/3_pipeline.py — Pipeline & Revenue Intelligence (CRM-grade)."""
import streamlit as st
from pathlib import Path
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from utils.core import get_pipeline_stages as _gps, get_product_types as _gpt, get_fiscal_year, get_currency
from pages._shared import load_shared_state
from pages._access import require_access, get_visible_staff
require_access("pipeline")

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
df_proc      = st.session_state.get("df_processed", pd.DataFrame())

# ── Identity ──────────────────────────────────────────────────────────
role_l   = str(ud.get("role","")).lower()
my_code  = str(ud.get("staff_code","") or uname)
my_name  = ud.get("full_name","")
my_unit  = ud.get("unit","")
is_admin = ud.get("is_admin", False)
is_mgr   = is_admin or any(k in role_l for k in (
    "managing","director","head of","regional","branch manager","chief",
    "manager","supervisor","credit manager","operations manager"))
is_md    = is_admin or "managing" in role_l

# ── Visible staff — cascade HIERARCHY drives who you see ───────────────
# This is the SAME hierarchy used by cascade — same tree, bottom-up pipeline
vis_staff = get_visible_staff(ud, staff_scores)

# Build vis_names and vis_codes — always include the user themselves
vis_names = set(vis_staff["Staff Name"].tolist()) if len(vis_staff) else set()
vis_codes = set(vis_staff["Staff Code"].astype(str).tolist()) if len(vis_staff) else set()
vis_names.add(my_name)
vis_codes.add(my_code)

# Debug info stored for team view (admin can see why team is empty)
_vis_debug = {
    "role": ud.get("role",""), "unit": my_unit,
    "vis_count": len(vis_names), "vis_names": sorted(vis_names)[:10],
}

# ── Deal scope ────────────────────────────────────────────────────────
pm = st.session_state.get("pipeline_manager")
if pm is None:
    from utils.core import PipelineManager
    pm = PipelineManager()
    st.session_state["pipeline_manager"] = pm

all_deals   = pm.get_deals()
# Deals where I am a named backup (regardless of hierarchy)
_backup_deals = [d for d in all_deals
                 if my_code in [str(b) for b in d.get("backup_staff_codes", [])]]

if is_md:
    # MD and admins see ALL deals in the system — no filter
    view_deals = list(all_deals)
elif is_mgr:
    # Managers see their visible staff's deals
    # If vis_names is empty (no staff data loaded), fall back to unit scope
    if vis_names:
        view_deals = [d for d in all_deals
                      if d.get("staff_name","") in vis_names
                      or str(d.get("staff_code","")) in vis_codes
                      or (my_unit and d.get("unit","") == my_unit)]
    else:
        # No staff data — scope by unit only
        view_deals = [d for d in all_deals
                      if (my_unit and d.get("unit","") == my_unit)
                      or str(d.get("staff_code","")) == my_code
                      or d.get("staff_name","") == my_name]
else:
    view_deals = [d for d in all_deals
                  if str(d.get("staff_code","")) == my_code
                  or d.get("staff_name","") == my_name]

# Always add backup deals (may be outside normal visibility)
_backup_deal_ids = {d["id"] for d in view_deals}
for _bd in _backup_deals:
    if _bd["id"] not in _backup_deal_ids:
        view_deals.append(_bd)

# Exclude drafts from main view; show separately
drafts     = [d for d in view_deals if d.get("draft")]
live_deals = [d for d in view_deals if not d.get("draft")]
active     = [d for d in live_deals if d["stage"] in ACTIVE_STAGES]
won        = [d for d in live_deals if d["stage"] == "Closed Won"]
lost       = [d for d in live_deals if d["stage"] == "Closed Lost"]
pip_val    = pm.pipeline_value(active)
wt_val     = pm.weighted_pipeline(active)
won_val    = sum(float(d.get("deal_value",0)) for d in won)
conv_r     = round(len(won)/(len(won)+len(lost))*100,1) if (won or lost) else 0

# Assets (money lent out) vs Liabilities (deposits taken in)
_ASSET_PRODUCTS = {
    "Business Loan","Personal Loan","Mortgage / Home Loan","Overdraft",
    "Trade Finance","Asset Finance","Invoice Discounting","LPO Finance",
    "Agricultural Loan","Staff Loan","Credit Card","Other Loan",
}
_LIAB_PRODUCTS = {
    "Current Account (CASA)","Savings Account (CASA)","Fixed Deposit",
    "Call Deposit","Notice Deposit","Junior Account",
    "Business Current Account","Business Savings","Other Deposit",
}
asset_pip  = sum(float(d.get("deal_value",0)) for d in active if d.get("product_type","") in _ASSET_PRODUCTS)
liab_pip   = sum(float(d.get("deal_value",0)) for d in active if d.get("product_type","") in _LIAB_PRODUCTS)
asset_won  = sum(float(d.get("deal_value",0)) for d in won if d.get("product_type","") in _ASSET_PRODUCTS)
liab_won   = sum(float(d.get("deal_value",0)) for d in won if d.get("product_type","") in _LIAB_PRODUCTS)
today_s    = str(date.today())
overdue    = [d for d in active if d.get("next_action_date","") < today_s
              and d.get("next_action_date","")]
due_today  = [d for d in active if d.get("next_action_date","") == today_s]

STAGE_CLR  = {
    "Lead":"#3B82F6","Contacted":"#8B5CF6","Qualified":"#F59E0B",
    "Proposal":"#EF4444","Negotiation":"#F97316","Compliance":"#06B6D4",
    "Closed Won":"#10B981","Closed Lost":"#6B7280",
}
STAGE_BG   = {
    "Lead":"#EFF6FF","Contacted":"#F5F3FF","Qualified":"#FFFBEB",
    "Proposal":"#FEF2F2","Negotiation":"#FFF7ED","Compliance":"#ECFEFF",
    "Closed Won":"#ECFDF5","Closed Lost":"#F9FAFB",
}

# ── CSS ───────────────────────────────────────────────────────────────
st.markdown("""<style>
.pip-hdr{background:linear-gradient(135deg,#1E3A5F 0%,#1D4ED8 60%,#0EA5E9 100%);
  border-radius:14px;padding:20px 26px;margin-bottom:18px;
  box-shadow:0 8px 32px rgba(29,78,216,0.25)}
.kpi-strip{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;margin-bottom:16px}
.kpi-c{background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);border-radius:12px;
  padding:14px 12px;text-align:center;position:relative;overflow:hidden}
.kpi-c::before{content:'';position:absolute;top:0;left:0;right:0;height:3px}
.kpi-lbl{font-size:9px;color:var(--color-text-tertiary);text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}
.kpi-val{font-size:20px;font-weight:800;color:var(--color-text-primary);line-height:1;margin-bottom:3px}
.kpi-sub{font-size:10px;color:var(--color-text-secondary)}
.deal-card{background:var(--color-background-primary);border-radius:12px;padding:16px;margin-bottom:10px;
  border:0.5px solid var(--color-border-tertiary);border-left:5px solid #3B82F6;
  box-shadow:0 2px 8px rgba(0,0,0,0.04);transition:all .2s;position:relative}
.deal-card:hover{box-shadow:0 6px 20px rgba(0,0,0,0.10);transform:translateY(-1px)}
.deal-card.overdue{border-left-color:#EF4444;background:linear-gradient(to right,#FEF2F2,white)}
.deal-card.validated{border-left-color:#10B981}
.deal-card.draft{border-left-color:var(--color-text-tertiary);background:#FAFAFA;opacity:.85}
.badge{display:inline-block;padding:2px 8px;border-radius:20px;font-size:9px;font-weight:700}
.badge-ntb{background:#ECFDF5;color:#065F46;border:1px solid #A7F3D0}
.badge-ex{background:#EFF6FF;color:#1E40AF;border:1px solid #BFDBFE}
.badge-val{background:#ECFDF5;color:#065F46;border:1px solid #6EE7B7}
.badge-pend{background:#FEF3C7;color:#92400E;border:1px solid #FDE68A}
.badge-draft{background:var(--color-background-secondary);color:var(--color-text-secondary);border:1px solid #D1D5DB}
.stage-bar{display:flex;gap:4px;margin:12px 0}
.stage-seg{height:6px;border-radius:3px;flex:1;background:#F3F4F6}
.section-ttl{font-size:11px;font-weight:700;color:var(--color-text-secondary);text-transform:uppercase;
  letter-spacing:.8px;margin:18px 0 8px;padding-bottom:6px;
  border-bottom:0.5px solid var(--color-border-tertiary);display:flex;align-items:center;gap:6px}
.alert-banner{padding:12px 16px;border-radius:10px;font-size:12px;
  display:flex;align-items:center;gap:10px;margin-bottom:12px}
.alert-red{background:#FEF2F2;border:1px solid #FECACA;color:#991B1B}
.alert-amber{background:#FFFBEB;border:1px solid #FDE68A;color:#92400E}
.alert-green{background:#ECFDF5;border:1px solid #A7F3D0;color:#065F46}
.form-card{background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);border-radius:14px;
  padding:24px;box-shadow:0 2px 12px rgba(0,0,0,0.04)}
/* Coloured input field borders */
.form-card input[type="text"], .form-card input[type="number"],
.form-card textarea, .form-card select,
div[data-testid="stTextInput"] input,
div[data-testid="stNumberInput"] input,
div[data-testid="stTextArea"] textarea,
div[data-testid="stSelectbox"] > div > div {
  border-color: #7C3AED !important;
  border-width: 1px !important;
  border-radius: 6px !important;
}
div[data-testid="stTextInput"] input:focus,
div[data-testid="stNumberInput"] input:focus,
div[data-testid="stTextArea"] textarea:focus {
  border-color: #2563EB !important;
  box-shadow: 0 0 0 2px rgba(37,99,235,0.15) !important;
}
/* Compact selector row */
.sel-row { display:flex; gap:6px; margin-bottom:8px; }
</style>""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────
_my_drafts = [d for d in drafts if str(d.get("staff_code",""))==my_code or d.get("staff_name","")==my_name]
st.markdown(f"""<div class='pip-hdr'>
<div style='display:flex;align-items:center;justify-content:space-between'>
<div>
  <div style='color:var(--color-background-primary);font-size:17px;font-weight:800;letter-spacing:-.3px'>
    💼 Pipeline & Revenue Intelligence</div>
  <div style='color:rgba(255,255,255,.6);font-size:11px;margin-top:3px'>
    Deal tracking · Portfolio management · Revenue forecast · Team analytics</div>
</div>
<div style='display:flex;gap:8px;align-items:center'>
  {"<div style='background:rgba(239,68,68,.2);border:1px solid rgba(239,68,68,.4);color:#FEE2E2;font-size:10px;font-weight:700;padding:4px 10px;border-radius:20px'>⚠️ "+str(len(overdue))+" overdue</div>" if overdue else ""}
  {"<div style='background:rgba(156,163,175,.2);border:1px solid rgba(156,163,175,.4);color:#F3F4F6;font-size:10px;font-weight:700;padding:4px 10px;border-radius:20px'>📝 "+str(len(_my_drafts))+" draft(s)</div>" if _my_drafts else ""}
  <div style='background:rgba(255,255,255,.15);color:rgba(255,255,255,.8);font-size:10px;padding:4px 10px;border-radius:20px'>
    {'Team view' if is_mgr else 'My pipeline'}</div>
</div>
</div></div>""", unsafe_allow_html=True)

# ── KPI cards ─────────────────────────────────────────────────────────
# Row 1: Total summary + Assets + Liabilities
_r1 = st.columns(4)
_r1_cards = [
    ("#1E40AF","🏦 Total Active Deals", str(len(active)),
     f"Pipeline: KES {fmt_num(pip_val,short=True)}",
     f"Wtd forecast: KES {fmt_num(wt_val,short=True)}"),
    ("#2563EB","📈 Loan Pipeline (Assets)",
     f"KES {fmt_num(asset_pip,short=True)}",
     f"Won: KES {fmt_num(asset_won,short=True)}",
     "Loans, ODs, Trade Finance, Mortgages"),
    ("#059669","💰 Deposit Pipeline (Liabilities)",
     f"KES {fmt_num(liab_pip,short=True)}",
     f"Won: KES {fmt_num(liab_won,short=True)}",
     "CASA, Fixed, Call, Notice Deposits"),
    ("#EF4444" if overdue else "#10B981",
     "⚠️ Actions Overdue" if overdue else "✅ Actions",
     str(len(overdue)) if overdue else "On track",
     f"{len(due_today)} due today · {len(active)} active",
     f"Win rate: {conv_r:.0f}% ({len(won)} won)"),
]
for i,(clr,lbl,val,sub1,sub2) in enumerate(_r1_cards):
    _r1[i].markdown(
        f"<div class='kpi-c' style='border-top:4px solid {clr};padding:16px 14px'>"
        f"<div class='kpi-lbl' style='color:{clr}'>{lbl}</div>"
        f"<div class='kpi-val' style='color:{clr};font-size:18px'>{val}</div>"
        f"<div class='kpi-sub' style='margin-top:4px'>{sub1}</div>"
        f"<div style='font-size:9px;color:var(--color-text-tertiary);margin-top:2px'>{sub2}</div>"
        f"</div>", unsafe_allow_html=True)

# Stage progress bar
if active:
    _stage_counts = {s["stage"]: sum(1 for d in active if d["stage"]==s["stage"]) for s in PIPELINE_STAGES}
    _bar_html = "<div class='stage-bar'>"
    for s in PIPELINE_STAGES:
        if s["stage"] in ("Closed Won","Closed Lost"): continue
        _cnt = _stage_counts.get(s["stage"],0)
        _clr = STAGE_CLR.get(s["stage"],"#D1D5DB")
        _op  = 0.3 + 0.7*(_cnt/max(_stage_counts.values(),default=1)) if _cnt else 0.15
        _sname2 = s["stage"]
        _bar_html += f"<div class='stage-seg' style='background:{_clr};opacity:{_op}' title='{_sname2}: {_cnt}'></div>"
    _bar_html += "</div>"
    st.markdown(_bar_html, unsafe_allow_html=True)

# Draft notification banner
if _my_drafts:
    st.markdown(
        f"<div class='alert-banner alert-amber'>"
        f"📝 <b>You have {len(_my_drafts)} saved draft(s)</b> — leads saved for later completion. "
        f"Complete them in the <b>My Actions</b> tab.</div>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────
_tab_labels = ["➕ Add Deal","📋 Deal Board","⚡ My Actions",
               "📈 Analytics","👥 Team View","📅 Activity Log"]
if not is_mgr:
    _tab_labels = [t for t in _tab_labels if "Team" not in t]

tabs = st.tabs(_tab_labels)
def _tab(n):
    try:    return tabs[_tab_labels.index(n)]
    except: return None

# ══════════════════════════════════════════════════════════════════════
# TAB 1 — ADD DEAL
# ══════════════════════════════════════════════════════════════════════
with tabs[0]:
    # Success banner (shown after form clears)
    if st.session_state.get("_last_deal"):
        _ld = st.session_state.pop("_last_deal")
        _saved = _ld.get("draft")
        st.markdown(
            f"<div class='alert-banner {'alert-amber' if _saved else 'alert-green'}'>"
            f"{'📝' if _saved else '✅'} <b>{'Draft saved' if _saved else 'Deal added'}</b> — "
            f"{_ld['client']} · KES {fmt_num(_ld['value'],short=True)} · {_ld['stage']}<br>"
            f"{'<span style=\"font-size:11px\">Complete this draft in My Actions tab.</span>' if _saved else ''}"
            f"</div>", unsafe_allow_html=True)

    # ── Pipeline category definitions ────────────────────────────────
    _pip_cats_def = {
        "📈 Loan / Asset":  {"cat":"Loan",   "clr":"#2563EB","bg":"#EFF6FF","desc":"Loans, Overdrafts, Trade Finance, Mortgages"},
        "💰 Deposit":       {"cat":"Deposit", "clr":"#059669","bg":"#ECFDF5","desc":"CASA, Fixed Deposit, Call & Notice"},
        "🏦 Account":       {"cat":"Account", "clr":"#7C3AED","bg":"#F5F3FF","desc":"Account opening — count not KES"},
        "⚙️ Other":         {"cat":"Other",   "clr":"#6B7280","bg":"#F9FAFB","desc":"Insurance, DFS, Treasury"},
    }

    # ── ROW A: Who is the customer? (2 choices: NTB/Existing + Ind/Biz) ──
    # Both chosen in one compact row — no separate steps
    _ntb_sel   = st.session_state.get("pl_ntb_sel","Existing")
    _tier1_sel = st.session_state.get("pl_tier1_sel","Individual")
    is_ntb     = _ntb_sel == "NTB"

    # 6 clickable dot-style boxes in one row: Existing·Ind, Existing·Biz, NTB·Ind, NTB·Biz, [spacer], Loan, Deposit, Account, Other
    st.markdown(
        "<div style='display:flex;align-items:center;gap:6px;margin-bottom:6px'>"
        "<span style='font-size:10px;font-weight:700;color:var(--color-text-tertiary);text-transform:uppercase;"
        "letter-spacing:.5px;white-space:nowrap'>Customer</span>"
        "<div style='flex:1;height:1px;background:#F3F4F6'></div>"
        "</div>", unsafe_allow_html=True)

    _cust_opts = [
        ("Existing","Individual","🏦","👤","#059669","#ECFDF5"),
        ("Existing","Business",  "🏦","🏢","#0284C7","#EFF6FF"),
        ("NTB",     "Individual","✨","👤","#7C3AED","#F5F3FF"),
        ("NTB",     "Business",  "✨","🏢","#DC2626","#FEF2F2"),
    ]
    _ca, _cb, _cc, _cd, _spc, _ce, _cf, _cg, _ch = st.columns([1,1,1,1,.15,1,1,1,1])
    _cust_cols = [_ca,_cb,_cc,_cd]

    for _ci, (_cn, _ct, _ico1, _ico2, _clr, _bg) in enumerate(_cust_opts):
        _active = (_ntb_sel==_cn and _tier1_sel==_ct)
        _box_bg  = _bg    if _active else "var(--color-background-primary)"
        _box_brd = _clr   if _active else "#E5E7EB"
        _box_tc  = _clr   if _active else "#9CA3AF"
        # Single-line compact tile: click the tile markdown = button below it
        _cust_cols[_ci].markdown(
            f"<div style='padding:5px 3px;background:{_box_bg};"
            f"border:2px solid {_box_brd};border-radius:8px;text-align:center'>"
            f"<span style='font-size:13px'>{_ico1}{_ico2}</span>"
            f"<div style='font-size:8px;font-weight:700;color:{_box_tc};line-height:1.2'>"
            f"{_cn}<br>{_ct}</div>"
            f"</div>", unsafe_allow_html=True)
        if _cust_cols[_ci].button("✓" if _active else " ",
                                   key=f"pl_cust_{_ci}",
                                   use_container_width=True,
                                   type="primary" if _active else "secondary"):
            st.session_state["pl_ntb_sel"]   = _cn
            st.session_state["pl_tier1_sel"] = _ct
            st.rerun()

    # ── ROW A continued: Pipeline category ───────────────────────────
    _spc.markdown("<div style='border-left:0.5px solid var(--color-border-tertiary);height:70px;margin:6px auto'></div>",
                  unsafe_allow_html=True)
    st.markdown(
        "<div style='position:relative;top:-62px;left:0;display:inline-block;"  # hidden label
        "font-size:9px;color:var(--color-text-tertiary)'></div>", unsafe_allow_html=True)

    _pip_cat_sel = st.session_state.get("pl_pip_cat_sel","📈 Loan / Asset")
    _pipe_cols   = [_ce, _cf, _cg, _ch]
    for _pci2, (_pck2, _pcv2) in enumerate(_pip_cats_def.items()):
        _psel2  = _pip_cat_sel == _pck2
        _p_bg2  = _pcv2["bg"]  if _psel2 else "var(--color-background-primary)"
        _p_brd2 = _pcv2["clr"] if _psel2 else "#E5E7EB"
        _p_tc2  = _pcv2["clr"] if _psel2 else "#9CA3AF"
        _p_ico2 = _pck2.split()[0]
        _p_lbl2 = _pck2.split(" ",1)[1]
        _pipe_cols[_pci2].markdown(
            f"<div style='padding:5px 3px;background:{_p_bg2};"
            f"border:2px solid {_p_brd2};border-radius:8px;text-align:center'>"
            f"<span style='font-size:13px'>{_p_ico2}</span>"
            f"<div style='font-size:8px;font-weight:700;color:{_p_tc2};line-height:1.2'>{_p_lbl2}</div>"
            f"</div>", unsafe_allow_html=True)
        if _pipe_cols[_pci2].button("✓" if _psel2 else " ",
                                     key=f"pl_pip_{_pci2}",
                                     use_container_width=True,
                                     type="primary" if _psel2 else "secondary"):
            st.session_state["pl_pip_cat_sel"] = _pck2; st.rerun()

    _tier1_val = st.session_state.get("pl_tier1_sel","Individual")
    _pip_cat   = _pip_cats_def.get(_pip_cat_sel,{}).get("cat","Loan")
    _is_account_pip = _pip_cat == "Account"

    # ── Existing: account lookup + portfolio check ─────────────────────
    acc_num = ""
    portfolio_owner_code = my_code
    portfolio_owner_name = my_name
    refer_action = "Mine"

    if not is_ntb:
        st.markdown("<div class='section-ttl'>🔍 Account lookup</div>",
                    unsafe_allow_html=True)
        _lk1, _lk2 = st.columns(2)
        acc_num  = _lk1.text_input("Account number / CIF",
                                    placeholder="e.g. 0123456789", key="pl_acc")
        acc_name = _lk2.text_input("Customer name (confirm)",
                                    placeholder="Confirm spelling", key="pl_accname")

        if acc_num:
            # ── Look up in CBS — search multiple path locations ────────
            _cbs_customer = None
            _cbs_account  = None
            import csv as _csv

            # cbs_data can sit at: project root, one or two levels up from pages/
            _here = Path(__file__).parent          # pages/
            _app_root = _here.parent               # a2z/
            _proj_root = _app_root.parent          # project root (where generate_cbs.py lives)
            _search_paths = [
                _proj_root / "cbs_data",
                _app_root  / "cbs_data",
                _here      / "cbs_data",
                Path("cbs_data"),                  # relative to CWD
            ]
            _cust_csv = None
            _acct_csv = None
            for _sp in _search_paths:
                if (_sp / "customers.csv").exists():
                    _cust_csv = _sp / "customers.csv"
                    _acct_csv = _sp / "accounts.csv"
                    break

            if _cust_csv and _cust_csv.exists():
                _acc_strip = acc_num.strip().upper()

                # Determine what was entered: ECO... = account number, numeric = CIF
                _is_account_num = _acc_strip.startswith("ECO")

                if _is_account_num:
                    # Search accounts.csv first, then get CIF → customer
                    if _acct_csv and _acct_csv.exists():
                        with open(_acct_csv, encoding="utf-8") as _af:
                            for _arow in _csv.DictReader(_af):
                                if _arow.get("account_number","").upper() == _acc_strip:
                                    _cbs_account = _arow
                                    _cif = _arow.get("cif","")
                                    with open(_cust_csv, encoding="utf-8") as _cf2:
                                        for _crow2 in _csv.DictReader(_cf2):
                                            if _crow2.get("cif","") == _cif:
                                                _cbs_customer = _crow2; break
                                    break
                else:
                    # Numeric CIF — search customers.csv directly
                    with open(_cust_csv, encoding="utf-8") as _cf:
                        for _crow in _csv.DictReader(_cf):
                            if _crow.get("cif","") == _acc_strip:
                                _cbs_customer = _crow; break
                    # Still not found? Try as account number anyway
                    if not _cbs_customer and _acct_csv and _acct_csv.exists():
                        with open(_acct_csv, encoding="utf-8") as _af:
                            for _arow in _csv.DictReader(_af):
                                if _arow.get("account_number","") == _acc_strip:
                                    _cbs_account = _arow
                                    _cif = _arow.get("cif","")
                                    with open(_cust_csv, encoding="utf-8") as _cf2:
                                        for _crow2 in _csv.DictReader(_cf2):
                                            if _crow2.get("cif","") == _cif:
                                                _cbs_customer = _crow2; break
                                    break

            # ── Auto-populate fields from CBS ─────────────────────────
            if _cbs_customer:
                _cbs_name    = _cbs_customer.get("full_name","")
                _cbs_segment = _cbs_customer.get("sub_segment","")
                _cbs_sector  = _cbs_customer.get("sector","")
                _cbs_rm_code = _cbs_customer.get("relationship_manager_code","")
                _cbs_kyc     = _cbs_customer.get("kyc_status","")
                _cbs_risk    = _cbs_customer.get("risk_rating","")
                _cbs_type    = _cbs_customer.get("customer_type","Individual")
                _cbs_branch  = _cbs_customer.get("branch_name","")

                st.markdown(
                    f"<div style='padding:10px 14px;background:#F0FDF4;"
                    f"border:1px solid #A7F3D0;border-radius:10px;margin:6px 0'>"
                    f"<div style='font-size:11px;font-weight:700;color:#065F46;margin-bottom:6px'>"
                    f"✅ Customer found in CBS</div>"
                    f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;font-size:11px'>"
                    f"<div><span style='color:var(--color-text-tertiary)'>Name</span><br><b>{_cbs_name}</b></div>"
                    f"<div><span style='color:var(--color-text-tertiary)'>Segment</span><br><b>{_cbs_segment}</b></div>"
                    f"<div><span style='color:var(--color-text-tertiary)'>Sector</span><br><b>{_cbs_sector[:28] if _cbs_sector else '—'}</b></div>"
                    f"<div><span style='color:var(--color-text-tertiary)'>Branch</span><br><b>{_cbs_branch}</b></div>"
                    f"<div><span style='color:var(--color-text-tertiary)'>KYC</span><br><b style='color:{'#10B981' if _cbs_kyc=='Verified' else '#F59E0B'}'>{_cbs_kyc}</b></div>"
                    f"<div><span style='color:var(--color-text-tertiary)'>Risk</span><br><b style='color:{'#EF4444' if _cbs_risk in ('High','Very High') else '#10B981'}'>{_cbs_risk}</b></div>"
                    f"</div></div>",
                    unsafe_allow_html=True)

                # Store in session for form pre-fill
                st.session_state["_pf_cbs_name"]    = _cbs_name
                st.session_state["_pf_cbs_segment"]  = _cbs_segment
                st.session_state["_pf_cbs_sector"]   = _cbs_sector
                st.session_state["_pf_cbs_type"]     = _cbs_type

                # Portfolio ownership from CBS RM code
                if _cbs_rm_code and _cbs_rm_code != my_code:
                    # Find RM name from staff_scores
                    _rm_name = ""
                    if len(staff_scores):
                        _rm_row = staff_scores[staff_scores["Staff Code"].astype(str)==_cbs_rm_code]
                        if len(_rm_row): _rm_name = _rm_row["Staff Name"].iloc[0]
                    _rm_name = _rm_name or f"RM {_cbs_rm_code}"
                    portfolio_owner_code = _cbs_rm_code
                    portfolio_owner_name = _rm_name
                    st.markdown(
                        f"<div class='alert-banner alert-amber'>"
                        f"⚠️ <b>Portfolio conflict</b> — This customer's RM is "
                        f"<b>{_rm_name}</b> (per CBS). BSC credit on closure goes to them."
                        f"</div>", unsafe_allow_html=True)
                    refer_action = st.radio("How to proceed?",
                        ["Seek permission — I will get approval from the portfolio owner",
                         "Refer to portfolio owner",
                         "Pursue and credit to my BSC (requires manager override note)"],
                        key="pl_refer")
                    if "Refer" in refer_action:
                        _ref_to  = st.text_input("Refer to (staff name)", key="pl_refto")
                        _ref_note= st.text_area("Referral note", height=60, key="pl_refnote")
                        if st.button("📨 Send referral", type="primary"):
                            if _ref_to:
                                pm.add_deal({
                                    "staff_code":my_code,"staff_name":my_name,"unit":my_unit,
                                    "client_name":_cbs_name,"account_number":acc_num,
                                    "client_type":"Existing","product_type":"Referral",
                                    "deal_value":0,"stage":"Lead","probability":0.05,
                                    "next_action":f"Referred to {_ref_to}: {_ref_note}",
                                    "next_action_date":str(date.today()),
                                    "source":"Referral",
                                    "portfolio_owner_code":_cbs_rm_code,
                                    "portfolio_owner_name":_rm_name,
                                    "is_referral":True,"referred_to":_ref_to,
                                    "referral_note":_ref_note,"is_ntb":False,
                                })
                                audit_log("DEAL_REFERRED", uname, f"{acc_num}→{_ref_to}")
                                st.success(f"✅ Referred to {_ref_to}")
                                st.rerun()
                        st.stop()
                else:
                    st.markdown(
                        "<div class='alert-banner alert-green'>"
                        "✅ <b>Your portfolio</b> — This customer is assigned to you in CBS."
                        "</div>", unsafe_allow_html=True)
            else:
                # Not in CBS — check existing pipeline deals
                _existing_deal = next((d for d in all_deals
                                       if d.get("account_number","") == acc_num.strip()
                                       and not d.get("draft")), None)
                if _existing_deal:
                    _po_code = str(_existing_deal.get("portfolio_owner_code","") or
                                   _existing_deal.get("staff_code",""))
                    _po_name = _existing_deal.get("portfolio_owner_name","") or _existing_deal.get("staff_name","")
                    if _po_code and _po_code != my_code:
                        portfolio_owner_code = _po_code
                        portfolio_owner_name = _po_name
                        st.markdown(
                            f"<div class='alert-banner alert-amber'>"
                            f"⚠️ <b>Account found in pipeline</b> — owned by {_po_name}.</div>",
                            unsafe_allow_html=True)
                    else:
                        st.markdown("<div class='alert-banner alert-green'>✅ Account found in pipeline.</div>",
                                    unsafe_allow_html=True)
                else:
                    st.caption("⚠️ Account/CIF not found in CBS. Proceed with manual entry.")



    # ── Main form ─────────────────────────────────────────────────────
    st.markdown("<div class='section-ttl' style='margin-top:14px'>📝 Deal details</div>",
                unsafe_allow_html=True)

    # ── Individual or Business tiles (Step 3 — inside form section) ─
    # Moved below pipeline category selection

    st.markdown("<div class='form-card'>", unsafe_allow_html=True)

    # clear_on_submit=False so validation errors don't wipe the form
    # On SUCCESS we increment _form_n to render a fresh form
    _fk = f"deal_form_{st.session_state.get('_form_n',0)}"
    with st.form(_fk, clear_on_submit=False):
        # ══ COMPACT 3-COLUMN LAYOUT — designed to fit one screen ════════
        # Row 1: Customer identity (3 cols)
        _tier1     = st.session_state.get("pl_tier1_sel","Individual")
        _is_biz    = _tier1 == "Business"
        r1a, r1b, r1c = st.columns(3)

        if is_ntb:
            client_name = r1a.text_input("Full name *", placeholder="e.g. John Otieno Kamau")
        else:
            # Pre-fill from CBS lookup if available
            _cbs_prefill = st.session_state.get("_pf_cbs_name","") or st.session_state.get("pl_accname","")
            client_name = r1a.text_input("Customer name *",
                value=_cbs_prefill,
                placeholder="Auto-filled from CBS")

        client_type = r1b.selectbox("Sub-segment *",
            CUSTOMER_SEGMENTS.get(_tier1,[]), key="pl_tier2")
        full_segment = f"{_tier1} — {client_type}"

        # Sector (col 3 row 1)
        if _is_biz:
            sector = r1c.selectbox("Industry / CBK sector",
                ["— Select —"]+CBK_SECTORS, key="pl_sector")
        else:
            sector = r1c.selectbox("Occupation / profile",
                ["— Select —"]+INDIVIDUAL_SECTOR_LIST, key="pl_sector")

        # Row 2: NTB fields OR Business fields (3 cols)
        if is_ntb and not _is_biz:
            r2a,r2b,r2c = st.columns(3)
            id_type   = r2a.selectbox("ID type",
                ["National ID","Passport","Alien ID","Company Reg No","Other"])
            id_number = r2b.text_input("ID number *", placeholder="e.g. 12345678",
                value=st.session_state.get("_pf_idnum",""))
            phone     = r2c.text_input("Phone", placeholder="+254 7XX XXX XXX",
                value=st.session_state.get("_pf_phone",""))
        elif is_ntb and _is_biz:
            r2a,r2b,r2c = st.columns(3)
            id_type   = "Company Reg No"
            id_number = r2a.text_input("Company Reg No *", placeholder="e.g. PVT-123456",
                value=st.session_state.get("_pf_idnum",""))
            phone     = r2b.text_input("Business phone", placeholder="+254 2XX XXX XXX",
                value=st.session_state.get("_pf_phone",""))
            biz_name  = r2c.text_input("Business / company name *",
                placeholder="e.g. Kamau & Sons Limited",
                value=st.session_state.get("_pf_biz_name",""))
        else:
            id_type = ""; id_number = ""; phone = ""

        if _is_biz and not is_ntb:
            r2a,r2b,r2c = st.columns(3)
            biz_name = r2a.text_input("Business / company name *",
                placeholder="e.g. Kamau & Sons Limited",
                value=st.session_state.get("_pf_biz_name",""))
            contact_person = r2b.text_input("Contact person *",
                placeholder="e.g. James Mwangi",
                value=st.session_state.get("_pf_contact",""))
            _pos_sel = r2c.selectbox("Contact title", CONTACT_POSITIONS, key="pl_pos_sel")
            if _pos_sel == "Other (specify below)":
                contact_position = r2c.text_input("Specify title",
                    value=st.session_state.get("_pf_position",""), key="pl_pos_other")
            else:
                contact_position = _pos_sel if _pos_sel != "— Select position —" else ""
        elif _is_biz and is_ntb:
            # biz_name already captured above; add contact fields
            r3a,r3b,r3c = st.columns(3)
            contact_person = r3a.text_input("Contact person *",
                placeholder="e.g. James Mwangi",
                value=st.session_state.get("_pf_contact",""))
            _pos_sel = r3b.selectbox("Contact title", CONTACT_POSITIONS, key="pl_pos_sel")
            contact_position = _pos_sel if _pos_sel not in ("— Select position —","Other (specify below)") else ""
            decision_level = r3c.selectbox("Decision level", DECISION_LEVELS, key="pl_decision_level")
        else:
            biz_name=""; contact_person=""; contact_position=""

        if _is_biz and not is_ntb:
            decision_level = r2a.selectbox("Decision level", DECISION_LEVELS, key="pl_decision_level")
        elif not _is_biz:
            decision_level = ""

        # ── Row 3: Product + Deal value + Stage (3 cols) ────────────────
        st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
        _all_prods = get_custom_product_types()
        _cat_prod_filter = {
            "Loan":    [p for p in _all_prods if get_pipeline_category(p)=="Loan"],
            "Deposit": [p for p in _all_prods if get_pipeline_category(p) in ("Deposit","Account")],
            "Account": [p for p in _all_prods if get_pipeline_category(p)=="Account"],
            "Other":   [p for p in _all_prods if get_pipeline_category(p)=="Other"],
        }
        _filtered_prods = _cat_prod_filter.get(_pip_cat, _all_prods) or _all_prods
        _cat_stages  = get_stages_for_category(_pip_cat)
        _cat_active  = [s["stage"] for s in _cat_stages
                        if s["stage"] not in ("Closed Won","Closed Lost")]
        _pip_cat_from_prod = _pip_cat

        r3a,r3b,r3c = st.columns(3)
        product_type = r3a.selectbox("Product / facility *",
            ["— Select product —"]+_filtered_prods)
        if product_type != "— Select product —":
            _pip_cat_from_prod = get_pipeline_category(product_type)

        _is_account_pip = _pip_cat_from_prod == "Account" or _pip_cat == "Account"
        _prob_defaults  = {
            "Lead":5,"Contacted":15,"Qualified":25,"Application":35,
            "Credit Assessment":50,"Offer / Proposal":65,"KYC / Documentation":40,
            "Account Opening":70,"Compliance Review":80,"Compliance":80,
            "Documentation":50,"Negotiation":70,"Proposal":50,
        }
        stage = r3b.selectbox("Stage *", _cat_active, key="pl_stage")
        probability = r3c.slider("Probability %", 0, 100,
            _prob_defaults.get(stage, 10))

        # ── Row 4: Value (or account count) + Next action + Date ────────
        r4a,r4b,r4c = st.columns(3)
        _today = date.today()

        if _is_account_pip:
            deal_value = 0.0
            _acct_count = r4a.number_input("Number of accounts *",
                min_value=0, step=1, value=0)
            _acct_count_val = int(_acct_count)
        else:
            _acct_count_val = 0
            _dv_txt = r4a.text_input("Deal value (KES) *",
                placeholder="e.g. 5,000,000",
                value=st.session_state.get("_pf_deal_value",""),
                help="Tab to next field — don't press Enter")
            try:    deal_value = float(str(_dv_txt).replace(",","").replace(" ","") or 0)
            except: deal_value = 0.0
            if deal_value > 0: r4a.caption(f"✓ KES {deal_value:,.0f}")
            elif _dv_txt.strip(): r4a.caption("⚠️ Invalid amount")

        next_action = r4b.text_input("Next action *",
            placeholder="e.g. Send KYC checklist")
        next_date   = r4c.date_input("Next action date",
            value=_today+timedelta(days=3),
            min_value=_today-timedelta(days=1),
            max_value=_today+timedelta(days=365), key="pl_nd")

        # ── Row 5: Source + Close date + Backup ─────────────────────────
        r5a,r5b,r5c = st.columns(3)
        source = r5a.selectbox("Lead source",
            ["Referral","Existing relationship","Walk-in","Cold call",
             "Branch campaign","Digital / online","Partner / broker","Other"])
        exp_close = r5b.date_input("Expected close date",
            value=_today+timedelta(days=60),
            min_value=_today, max_value=_today+timedelta(days=730), key="pl_ec")

        # Backup staff — cascade HIERARCHY: reportees + line manager
        _HIER = {
            "Managing Director":["Director Retail Banking","Director Commercial Banking","Chief Finance Officer","Chief Risk Officer","Chief Operations Officer","Chief Compliance Officer","Chief Human Resources Officer","Head Of Strategy","Head Of Internal Audit","Head Of Marketing","Head Of Digital Innovation","Debt Recovery Unit Manager"],
            "Director Retail Banking":["Head Of Retail","Regional Head"],
            "Director Commercial Banking":["Head Of SME","Head Of Corporate"],
            "Head Of Retail":["Regional Head"],
            "Regional Head":["Branch Manager"],
            "Branch Manager":["Branch Operations Manager","Branch Credit Manager"],
            "Branch Operations Manager":["Teller","Customer Service Officer","Branch Operations Supervisor"],
            "Branch Credit Manager":["Relationship Officer Personal Banking","Relationship Officer Business Banking","Direct Sales Officer"],
            "IT Manager":["IT Support Officer"],
            "Operations Manager":["Branch Operations Manager"],
        }
        my_role_clean  = str(ud.get("role","")).strip()
        _reportee_roles= _HIER.get(my_role_clean,[])
        _mgr_role      = next((r for r,subs in _HIER.items() if my_role_clean in subs),None)
        _backup_pool   = set()
        if len(staff_scores):
            _ss2 = staff_scores.copy()
            _ss2["_uc"] = _ss2["Unit"].astype(str).str.strip()
            if _reportee_roles:
                _rdf = _ss2[(_ss2["Role"].isin(_reportee_roles)) &
                             (_ss2["_uc"]==my_unit.strip()) &
                             (_ss2["Staff Name"]!=my_name)]
                _backup_pool.update(_rdf["Staff Name"].tolist())
            if _mgr_role:
                _ldf = _ss2[(_ss2["Role"]==_mgr_role) & (_ss2["Staff Name"]!=my_name)]
                _ldf2 = _ldf[_ldf["_uc"]==my_unit.strip()]
                _backup_pool.update((_ldf2 if len(_ldf2) else _ldf)["Staff Name"].tolist())
            if not _backup_pool and my_unit:
                _udf = _ss2[(_ss2["_uc"]==my_unit.strip()) & (_ss2["Staff Name"]!=my_name)]
                _backup_pool.update(_udf["Staff Name"].tolist())
        _unit_staff = sorted(_backup_pool)
        if _unit_staff:
            _backup_sel = r5c.multiselect("🤝 Backup (max 2)",
                _unit_staff, max_selections=2, key="pl_backups",
                help="Reportees & line manager. Can move stage only.")
        else:
            _backup_sel = []
            r5c.caption("—")

        # Assign to (manager only)
        if is_mgr and len(vis_staff) > 1:
            assignee = r5a.selectbox("Assign to",
                ["Myself"]+sorted(vis_names-{my_name}), key="pl_assign")
        else:
            assignee = "Myself"

        # ── Row 6: Account interest / Competitors / Notes (full width) ──
        if _is_account_pip:
            _non_account = [p for p in _all_prods if p not in {
                "Current Account (CASA)","Savings Account (CASA)","Salary Account",
                "Business Current Account","Business Savings","Junior Account","Other Deposit"}]
            _interest_prods = st.multiselect(
                "💡 Products of interest (optional — creates linked deals)",
                _non_account, key="pl_interest_prods")
            _interest_values = {}
            if _interest_prods:
                _iv_cols = st.columns(min(4,len(_interest_prods)))
                for _ipi,_ipr in enumerate(_interest_prods):
                    _iv_txt = _iv_cols[_ipi%4].text_input(
                        f"{_ipr[:18]}", placeholder="KES", key=f"pl_iv_{_ipi}")
                    try: _interest_values[_ipr] = float(str(_iv_txt).replace(",","") or 0)
                    except: _interest_values[_ipr] = 0.0
        else:
            _interest_prods=[]; _interest_values={}

        r6a,r6b = st.columns([1,2])
        comp_sel = r6a.multiselect("Competing banks",
            KENYA_BANKS, key="pl_comp")
        notes = r6b.text_area("Notes", height=56,
            placeholder="Relationship history, key triggers, urgency...")

        # ── Duplicate check ───────────────────────────────────────────
        _dup_err = []; _dup_warn = []
        if client_name.strip():
            _cn = client_name.strip().lower()
            _exact = [d for d in all_deals if d["stage"] in ACTIVE_STAGES
                      and d.get("client_name","").lower()==_cn
                      and d.get("product_type","")==product_type
                      and not d.get("draft")]
            if _exact:
                _dup_err.append(f"🚫 Duplicate — {_exact[0].get('client_name','')} already "
                                 f"has an active {product_type} deal "
                                 f"({_exact[0]['id']}, owner: {_exact[0].get('staff_name','')})")
            _other_rm = [d for d in all_deals if d["stage"] in ACTIVE_STAGES
                         and d.get("client_name","").lower()==_cn
                         and str(d.get("staff_code",""))!=my_code
                         and not d.get("draft") and not _exact]
            if _other_rm:
                _dup_warn.append(f"⚠️ {_other_rm[0].get('client_name','')} is being pursued by "
                                  f"{_other_rm[0].get('staff_name','')} "
                                  f"({_other_rm[0].get('product_type','')}). "
                                  "One primary RM per customer is best practice.")

        for _de in _dup_err:  st.error(_de)
        for _dw in _dup_warn: st.warning(_dw)

        _override = st.checkbox("I acknowledge the conflict above",
                                 key="pl_override") if _dup_warn and not _dup_err else False

        # ── Buttons ───────────────────────────────────────────────────
        sb1, sb2 = st.columns(2)
        _add     = sb1.form_submit_button("✅ Add to Pipeline",
                                           type="primary", use_container_width=True)
        _draft   = sb2.form_submit_button("📝 Save as draft (complete later)",
                                           use_container_width=True)

        if _add or _draft:
            _errs = []
            if not client_name.strip() and not (_is_biz and biz_name.strip()):
                _errs.append("Customer name required")
            if _is_biz and not biz_name.strip():
                _errs.append("Business / company name required")
            if product_type=="— Select product —": _errs.append("Select a product")
            if deal_value <= 0 and _add and not _is_account_pip:
                _errs.append("Deal value required")
            if _is_account_pip and _acct_count_val <= 0 and _add:
                _errs.append("Number of accounts required")
            if not next_action.strip() and _add: _errs.append("Next action required")
            if is_ntb and not id_number.strip() and _add: _errs.append("ID number required for NTB")
            if _dup_err:                        _errs.append("Resolve duplicates first")
            if _dup_warn and not _override and _add: _errs.append("Acknowledge conflict above")

            if _errs:
                for _e in _errs: st.error(f"❌ {_e}")
            else:
                if assignee == "Myself":
                    owner_code = my_code; owner_name = my_name
                else:
                    _or = staff_scores[staff_scores["Staff Name"]==assignee]
                    owner_code = str(_or["Staff Code"].iloc[0]) if len(_or) else my_code
                    owner_name = assignee

                _bsc_credit = (portfolio_owner_name
                               if not is_ntb and portfolio_owner_code != my_code
                               and "seek permission" not in refer_action.lower()
                               and "refer" not in refer_action.lower()
                               else owner_name)

                # Persist values to session_state for form prefill
                st.session_state["_pf_biz_name"]    = biz_name
                st.session_state["_pf_contact"]     = contact_person
                st.session_state["_pf_position"]    = contact_position
                st.session_state["_pf_idnum"]       = id_number
                st.session_state["_pf_phone"]       = phone
                st.session_state["_pf_deal_value"]  = _dv_txt if not _is_account_pip else ""

                # Resolve backup staff codes
                _backup_codes = []
                _backup_names = st.session_state.get("pl_backups", [])
                for _bn in _backup_names:
                    _br = staff_scores[staff_scores["Staff Name"]==_bn]
                    if len(_br):
                        _backup_codes.append(str(_br["Staff Code"].iloc[0]))

                _data = {
                    "staff_code":          owner_code,
                    "staff_name":          owner_name,
                    "backup_staff_codes":  _backup_codes,
                    "backup_staff_names":  _backup_names,
                    "unit":                my_unit,
                    "client_name":         (biz_name.strip() if _is_biz and biz_name.strip()
                                            else client_name.strip()),
                    "client_type":         full_segment,
                    "business_name":       biz_name.strip() if _is_biz else "",
                    "contact_person":      contact_person.strip(),
                    "contact_position":    contact_position.strip(),
                    "decision_level":      (decision_level
                                            if decision_level != "— Select —" else ""),
                    "account_number":      acc_num if not is_ntb else "",
                    "is_ntb":              is_ntb,
                    "id_type":             id_type,
                    "id_number":           id_number,
                    "phone":               phone,
                    "product_type":        (product_type if product_type!="— Select product —" else "Other"),
                    "sector":              sector if sector != "— Select —" else "",
                    "deal_value":          deal_value,
                    "account_count":       _acct_count_val,
                    "pipeline_category":   _pip_cat,
                    "interest_products":   _interest_prods,
                    "stage":               stage if _add else "Lead",
                    "probability":         probability/100 if _add else 0.05,
                    "next_action":         next_action.strip() if _add else "— To be completed —",
                    "next_action_date":    str(next_date) if _add else str(_today + timedelta(days=7)),
                    "expected_close":      str(exp_close),
                    "source":              source,
                    "notes":               notes,
                    "competitors":         ", ".join(comp_sel),
                    "portfolio_owner_code": portfolio_owner_code,
                    "portfolio_owner_name": portfolio_owner_name,
                    "bsc_credit_to":       _bsc_credit,
                    "draft":               bool(_draft),
                }
                did = pm.add_deal(_data)
                audit_log("DEAL_ADDED" if _add else "DEAL_DRAFTED", uname,
                          f"{did}|{client_name}|{deal_value}")

                # Create linked pipeline deals for products of interest (account pipeline only)
                if _add and _is_account_pip and _interest_prods:
                    for _ip in _interest_prods:
                        _ip_cat  = get_pipeline_category(_ip)
                        _ip_stgs = get_stages_for_category(_ip_cat)
                        _ip_stg  = next((s["stage"] for s in _ip_stgs
                                         if s["stage"] not in ("Closed Won","Closed Lost")), "Lead")
                        _ip_val  = _interest_values.get(_ip, 0.0)
                        _ip_did  = pm.add_deal({
                            **_data,
                            "product_type":     _ip,
                            "deal_value":       _ip_val,
                            "pipeline_category":_ip_cat,
                            "stage":            _ip_stg,
                            "probability":      0.10,
                            "linked_account_deal": did,
                            "notes": f"Interest expressed during account opening for {client_name}. Linked to {did}.",
                            "draft": False,
                        })
                        audit_log("LINKED_DEAL_CREATED", uname, f"{_ip_did}|{_ip}|linked:{did}")
                st.session_state["_deal_form_n"] = st.session_state.get("_deal_form_n",0)+1
                st.session_state["_form_n"]      = st.session_state.get("_form_n",0)+1
                # Clear persisted form values on success
                for _pk in ["_pf_biz_name","_pf_contact","_pf_position","_pf_idnum","_pf_phone"]:
                    st.session_state.pop(_pk, None)
                st.session_state["_last_deal"]   = {
                    "id":did,"client":client_name.strip(),
                    "value":deal_value,"stage":stage,"draft":bool(_draft),
                }
                st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════
# TAB 2 — DEAL BOARD
# ══════════════════════════════════════════════════════════════════════
with tabs[1]:
    _fc = st.columns([2,1,1,2])
    _sf  = _fc[0].multiselect("Stage", STAGE_NAMES, default=ACTIVE_STAGES, key="pl_sf")
    _pf  = _fc[1].multiselect("Product", get_custom_product_types()[:10], key="pl_pf")
    _of  = _fc[2].multiselect("Owner", sorted({d.get("staff_name","") for d in live_deals}),
               key="pl_of") if is_mgr else []
    _sch = _fc[3].text_input("🔍 Search client / account / ID", key="pl_sch")

    bd = [d for d in live_deals
          if (not _sf  or d["stage"] in _sf)
          and (not _pf  or d.get("product_type","") in _pf)
          and (not _of  or d.get("staff_name","") in _of)
          and (not _sch or _sch.lower() in
               (d.get("client_name","")+" "+d.get("id","")+" "+
                d.get("account_number","")).lower())]

    _vm = st.radio("View", ["🃏 Cards","📊 Table"], horizontal=True, key="pl_vm")

    if not bd:
        st.info("No deals match your filters.")
    elif "Cards" in _vm:
        # ── World-class horizontal Kanban board ──────────────────────
        # Show only stages that have deals — max 5 columns visible
        _active_stages = [_si for _si in PIPELINE_STAGES
                          if any(d["stage"] == _si["stage"] for d in bd)]
        _total_pipeline = sum(float(d.get("deal_value",0))*float(d.get("probability",0))
                              for d in bd if d["stage"] in ACTIVE_STAGES)

        # Pipeline summary strip
        _p_metrics = st.columns(5)
        _p_metrics[0].metric("Total deals", len(bd))
        _p_metrics[1].metric("Active", sum(1 for d in bd if d["stage"] in ACTIVE_STAGES))
        _p_metrics[2].metric("Weighted pipeline", f"KES {fmt_num(_total_pipeline,short=True)}")
        _p_metrics[3].metric("Disbursed", sum(1 for d in bd if d["stage"] in ("Disbursed","Closed Won")))
        _p_metrics[4].metric("Overdue actions", sum(1 for d in bd
                             if d.get("next_action_date","") and d["next_action_date"] < today_s))

        # Build full Kanban HTML — horizontal scrollable columns
        _cols_html = ""
        for _si in _active_stages:
            _sn  = _si["stage"]
            _sds = [d for d in bd if d["stage"] == _sn]
            _sv  = sum(float(d.get("deal_value",0)) for d in _sds)
            _clr_map = {
                "Prospecting":"#6366F1","Needs Analysis":"#8B5CF6",
                "Proposal":"#3B82F6","Documentation":"#0EA5E9",
                "Negotiation":"#06B6D4","Credit Review":"#F59E0B",
                "Credit Committee":"#F97316","Approval":"#10B981",
                "Bank Approval":"#059669","Disbursed":"var(--brand-mid,#1D9E75)",
                "Closed Won":"#166534","Closed Lost":"#6B7280",
                "Issued":"var(--brand-mid,#1D9E75)","Signed":"#166534",
            }
            _clr = _clr_map.get(_sn, "#6B7280")
            _bg  = "var(--color-background-secondary)"

            # Column header
            _cards_html = ""
            for _d in _sds:
                _ov  = _d.get("next_action_date","") < today_s if _d.get("next_action_date") else False
                _v   = float(_d.get("deal_value",0))
                _p   = float(_d.get("probability",0))
                _age = 0
                try:
                    from datetime import date as _dt
                    _age = (_dt.today() - _dt.fromisoformat(_d.get("open_date",today_s))).days
                except: pass

                # Probability arc (SVG semicircle indicator)
                _arc_pct = int(_p * 100)
                _arc_clr = "var(--brand-mid,#1D9E75)" if _arc_pct >= 70 else ("#F59E0B" if _arc_pct >= 40 else "#E24B4A")
                # SVG arc: 62.8 = full circumference of r=10 circle
                _dash_val = round(_arc_pct * 62.8 / 100, 1)

                _border_clr = "#EF4444" if _ov else "var(--color-border-tertiary)"
                _cards_html += f"""
<div style="background:var(--color-background-primary);border:0.5px solid {_border_clr};
border-radius:10px;padding:12px;margin-bottom:8px;cursor:pointer;
transition:box-shadow .15s;border-top:3px solid {_clr};"
onmouseover="this.style.boxShadow='0 2px 12px rgba(0,0,0,0.08)'"
onmouseout="this.style.boxShadow='none'">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px">
    <span style="font-size:10px;color:var(--color-text-secondary);font-weight:500">{_d['id']}</span>
    <svg width="28" height="28" viewBox="0 0 28 28">
      <circle cx="14" cy="14" r="10" fill="none" stroke="var(--color-border-tertiary)" stroke-width="2.5"/>
      <circle cx="14" cy="14" r="10" fill="none" stroke="{_arc_clr}" stroke-width="2.5"
        stroke-dasharray="{_dash_val} 62.8" stroke-dashoffset="15.7"
        stroke-linecap="round" transform="rotate(-90 14 14)"/>
      <text x="14" y="18" text-anchor="middle" font-size="7"
        fill="{_arc_clr}" font-weight="600">{_arc_pct}%</text>
    </svg>
  </div>
  <div style="font-weight:500;font-size:13px;color:var(--color-text-primary);
    margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
    {_d.get('client_name','')[:24]}
  </div>
  <div style="font-size:11px;color:var(--color-text-secondary);margin-bottom:8px">
    {(_d.get('product') or _d.get('product_type','—'))[:28]}
  </div>
  <div style="display:flex;justify-content:space-between;align-items:center">
    <div style="font-size:15px;font-weight:500;color:var(--color-text-primary)">
      KES {fmt_num(_v,short=True)}
    </div>
    <div style="font-size:10px;color:var(--color-text-secondary)">
      Wtd {fmt_num(_v*_p,short=True)}
    </div>
  </div>
  <div style="margin-top:8px;padding-top:8px;
    border-top:0.5px solid var(--color-border-tertiary);
    display:flex;justify-content:space-between;align-items:center">
    <div style="font-size:10px;color:{'#EF4444' if _ov else 'var(--color-text-secondary)'};
      font-weight:{'600' if _ov else '400'}">
      {'⚠ ' if _ov else ''}{_d.get('expected_close','—')}
    </div>
    <div style="font-size:10px;color:var(--color-text-secondary)">
      {_age}d in stage
    </div>
  </div>
  {f'<div style="font-size:10px;color:var(--color-text-secondary);margin-top:4px">👤 {_d.get(chr(115)+chr(116)+chr(97)+chr(102)+chr(102)+chr(95)+chr(110)+chr(97)+chr(109)+chr(101),"")}</div>' if is_mgr else ''}
</div>"""

            _cols_html += f"""
<div style="min-width:220px;max-width:240px;flex-shrink:0">
  <div style="padding:8px 4px 10px;border-bottom:2px solid {_clr};margin-bottom:10px">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <span style="font-size:12px;font-weight:500;color:var(--color-text-primary)">{_sn}</span>
      <span style="background:{_clr}22;color:{_clr};font-size:10px;font-weight:600;
        padding:2px 8px;border-radius:10px">{len(_sds)}</span>
    </div>
    <div style="font-size:10px;color:var(--color-text-secondary);margin-top:2px">
      KES {fmt_num(_sv,short=True)}
    </div>
  </div>
  <div style="max-height:520px;overflow-y:auto;padding-right:4px">{_cards_html}</div>
</div>"""

        # Render the full horizontal scrollable board
        st.markdown(
            f"<div style='display:flex;gap:14px;overflow-x:auto;padding:4px 0 12px;"
            f"scrollbar-width:thin'>{_cols_html}</div>",
            unsafe_allow_html=True)
        _bd_df = pd.DataFrame(bd)
        _show  = [c for c in ["id","client_name","is_ntb","pipeline_category","product_type",
                               "account_count","deal_value","stage","probability",
                               "next_action_date","manager_validated","staff_name"]
                  if c in _bd_df.columns]
        _disp  = _bd_df[_show].copy()
        if "deal_value"  in _disp.columns: _disp["deal_value"] = _disp["deal_value"].apply(lambda x: fmt_num(float(x or 0),short=True))
        if "probability" in _disp.columns: _disp["probability"] = _disp["probability"].apply(lambda x: f"{float(x or 0)*100:.0f}%")
        if "is_ntb"      in _disp.columns: _disp["is_ntb"] = _disp["is_ntb"].apply(lambda x: "NTB" if x else "Existing")
        if "manager_validated" in _disp.columns: _disp["manager_validated"] = _disp["manager_validated"].apply(lambda x: "✔" if x else "⏳")
        if "next_action_date"  in _disp.columns: _disp["next_action_date"] = _disp["next_action_date"].apply(lambda x: f"⚠️ {x}" if str(x) < today_s else str(x))
        _disp.columns = [c.replace("_"," ").title() for c in _disp.columns]
        def _hl_st(v): return f"background:{STAGE_BG.get(v,'')};color:{STAGE_CLR.get(v,'')};font-weight:700"
        def _hl_dt(v): return "color:#EF4444;font-weight:700" if str(v).startswith("⚠️") else ""
        st.dataframe(_disp.style
            .map(_hl_st, subset=["Stage"] if "Stage" in _disp.columns else [])
            .map(_hl_dt, subset=["Next Action Date"] if "Next Action Date" in _disp.columns else []),
            use_container_width=True, hide_index=True, height=420)

    # ── Quick update — ownership-aware ───────────────────────────────
    if bd:
        with st.expander("⚡ Quick update deal"):
            _do = {f"{d['id']} · {d.get('client_name','')} [{d['stage']}]": d["id"] for d in bd}
            _qs1,_qs2 = st.columns([3,1])
            _sel = _qs1.selectbox("Deal", list(_do.keys()), key="pl_qsel")
            if _sel:
                _sd = next((d for d in bd if d["id"]==_do[_sel]),None)
                if _sd:
                    # ── Ownership & backup check ──────────────────────
                    _sd_owner    = str(_sd.get("staff_code",""))
                    _sd_backups  = _sd.get("backup_staff_codes", [])  # list of backup codes
                    _is_owner    = (_sd_owner == my_code or _sd.get("staff_name","") == my_name)
                    _is_backup   = my_code in [str(b) for b in _sd_backups]
                    _can_update  = _is_owner or _is_backup
                    _can_edit    = _is_owner   # only owner can edit value/prob/next action

                    if not _can_update:
                        st.markdown(
                            f"<div class='alert-banner alert-red'>"
                            f"🔒 <b>Deal owned by {_sd.get('staff_name','another RM')}</b> — "
                            f"only the deal owner or their named backup can update this deal. "
                            f"If you need to make changes, ask the owner to add you as backup."
                            f"</div>", unsafe_allow_html=True)
                    elif _is_backup and not _is_owner:
                        st.markdown(
                            f"<div class='alert-banner alert-amber'>"
                            f"🤝 <b>You are a backup for this deal</b> (owned by "
                            f"{_sd.get('staff_name','')}) — you can move the stage "
                            f"but cannot edit deal details."
                            f"</div>", unsafe_allow_html=True)

                    _ci  = ALL_STAGE_NAMES.index(_sd["stage"]) if _sd["stage"] in ALL_STAGE_NAMES else 0
                    _all_remaining = ALL_STAGE_NAMES[_ci:]
                    _nst = _qs2.selectbox("Move to stage", _all_remaining, key="pl_nst",
                                          disabled=not _can_update)

                    if _can_edit:
                        _e1,_e2,_e3 = st.columns(3)
                        _nv_raw = _e1.text_input("Value (KES)",
                            value=f"{float(_sd.get('deal_value',0)):,.0f}", key="pl_qv")
                        try:    _nv = float(str(_nv_raw).replace(",","") or 0)
                        except: _nv = float(_sd.get("deal_value",0))
                        if _nv > 0: _e1.caption(f"✓ KES {_nv:,.0f}")
                        _np  = _e2.slider("Prob %",0,100,int(float(_sd.get("probability",0.3))*100),key="pl_qp")
                        _nna = _e3.text_input("Next action",value=_sd.get("next_action",""),key="pl_qna")
                        _nnd = _e1.date_input("Next action date",
                            value=date.fromisoformat(_sd["next_action_date"]) if _sd.get("next_action_date") else date.today(),
                            key="pl_qnd")
                    else:
                        # Manager sees read-only deal details
                        st.markdown(
                            f"**Value:** KES {fmt_num(float(_sd.get('deal_value',0)),short=True)} · "
                            f"**Prob:** {int(float(_sd.get('probability',0))*100)}% · "
                            f"**Next action:** {_sd.get('next_action','—')}")
                        _nv = float(_sd.get("deal_value",0))
                        _np = int(float(_sd.get("probability",0.3))*100)
                        _nna= _sd.get("next_action",""); _nnd=date.today()

                    _note = st.text_input("Update note *", placeholder="What happened? What's the next step?", key="pl_qnote")
                    _lr   = st.selectbox("Loss reason", LOSS_REASONS, key="pl_qlr") if _nst=="Closed Lost" else ""
                    _ub1,_ub2 = st.columns(2)
                    if _ub1.button("💾 Save changes", type="primary", key="pl_qsave",
                                   disabled=not _can_update):
                        if _note.strip() or _nst!=_sd["stage"]:
                            if _nst!=_sd["stage"]:
                                pm.update_stage(_sd["id"],_nst,
                                    f"{'Loss: '+_lr+'. ' if _lr else ''}{_note}",uname)
                            if _can_edit:
                                pm.update_deal(_sd["id"],{"deal_value":_nv,"probability":_np/100,
                                    "next_action":_nna,"next_action_date":str(_nnd)},uname)
                            _who = "owner" if _is_owner else "backup"
                            audit_log("DEAL_UPDATED",uname,f"{_sd['id']}|{_who}")
                            st.toast("✅ Updated"); st.rerun()
                        else: st.error("Add a note.")

    # ── Manager queues ─────────────────────────────────────────────────
    if is_mgr:
        _cancel_q = [d for d in view_deals if d.get("cancel_requested") and not d.get("cancel_approved")]
        _val_q    = [d for d in view_deals if d["stage"] in STAGE_NAMES[1:]
                     and not d.get("manager_validated") and not d.get("cancel_requested") and not d.get("draft")]
        if _cancel_q:
            st.markdown("---")
            st.markdown(f"<div class='section-ttl'>🗑️ Cancellation requests ({len(_cancel_q)})</div>",
                        unsafe_allow_html=True)
            for _cr in _cancel_q:
                with st.expander(f"🗑️ {_cr.get('client_name','')} — {_cr['id']} [{_cr.get('stage','')}]", expanded=True):
                    _ci_md = (f"**Requested by:** {_cr.get('cancel_requested_by','')}  \n"
                              f"**Reason:** {_cr.get('cancel_reason','—')}  \n"
                              f"**Value:** KES {fmt_num(float(_cr.get('deal_value',0)),short=True)}")
                    st.markdown(_ci_md)
                    _cn  = st.text_input("Manager note", key=f"cn_{_cr['id']}")
                    _ca1,_ca2 = st.columns(2)
                    if _ca1.button("✅ Approve cancel", key=f"cap_{_cr['id']}", type="primary"):
                        pm.approve_cancel(_cr["id"],uname,True,_cn)
                        audit_log("CANCEL_APPROVED",uname,_cr["id"]); st.toast("Cancelled"); st.rerun()
                    if _ca2.button("❌ Reject", key=f"crj_{_cr['id']}"):
                        pm.approve_cancel(_cr["id"],uname,False,_cn)
                        audit_log("CANCEL_REJECTED",uname,_cr["id"]); st.toast("Rejected"); st.rerun()

        if _val_q:
            st.markdown("---")
            st.markdown(f"<div class='section-ttl'>✔️ Deals awaiting validation ({len(_val_q)})</div>",
                        unsafe_allow_html=True)
            for _vd in _val_q[:8]:
                with st.expander(f"{_vd.get('client_name','')} — {_vd['id']} [{_vd.get('stage','')}]"):
                    _vd_p = int(float(_vd.get("probability",0))*100)
                    st.markdown(
                        f"**{_vd.get('staff_name','')}** · {_vd.get('product_type','')} · "
                        f"KES {fmt_num(float(_vd.get('deal_value',0)),short=True)} · {_vd_p}%")
                    st.caption(f"Next: {_vd.get('next_action','—')} | Close: {_vd.get('expected_close','—')}")
                    _vn  = st.text_input("Validation note", key=f"vn_{_vd['id']}")
                    _vb1,_vb2 = st.columns(2)
                    if _vb1.button("✅ Validate — include in forecast", key=f"vok_{_vd['id']}", type="primary"):
                        pm.validate_deal(_vd["id"],uname,True,_vn)
                        audit_log("DEAL_VALIDATED",uname,_vd["id"]); st.toast("✅ Validated"); st.rerun()
                    if _vb2.button("⚠️ Query — return to owner", key=f"vqy_{_vd['id']}"):
                        pm.validate_deal(_vd["id"],uname,False,_vn)
                        audit_log("DEAL_QUERIED",uname,_vd["id"]); st.toast("Queried"); st.rerun()

# ══════════════════════════════════════════════════════════════════════
# TAB 3 — MY ACTIONS
# ══════════════════════════════════════════════════════════════════════
with tabs[2]:
    # ── Drafts pending completion ─────────────────────────────────────
    if _my_drafts:
        st.markdown(f"<div class='section-ttl'>📝 Drafts — complete later ({len(_my_drafts)})</div>",
                    unsafe_allow_html=True)
        for _dr in _my_drafts:
            with st.expander(f"📝 {_dr.get('client_name','—')} — {_dr.get('product_type','—')} (draft)"):
                _dr_c = st.columns(3)
                _dr_c[0].markdown(f"**Client:** {_dr.get('client_name','—')}")
                _dr_c[1].markdown(f"**Product:** {_dr.get('product_type','—')}")
                _dr_c[2].markdown(f"**Created:** {str(_dr.get('created_at',''))[:10]}")
                _dv_edit = st.text_input("Deal value (KES) *",
                    value=f"{float(_dr.get('deal_value',0)):,.0f}" if float(_dr.get('deal_value',0)) else "",
                    key=f"dre_v_{_dr['id']}", placeholder="e.g. 5,000,000")
                _dna_edit = st.text_input("Next action *", value=_dr.get("next_action","").replace("— To be completed —",""),
                    key=f"dre_na_{_dr['id']}")
                _dnd_edit = st.date_input("Next action date",
                    value=date.fromisoformat(_dr["next_action_date"]) if _dr.get("next_action_date") and _dr["next_action_date"] != str(date.today()+timedelta(days=7)) else date.today()+timedelta(days=3),
                    key=f"dre_nd_{_dr['id']}")
                _d1,_d2 = st.columns(2)
                if _d1.button("✅ Complete & publish deal", key=f"drc_{_dr['id']}", type="primary"):
                    try:
                        _dv_f = float(str(_dv_edit).replace(",","") or 0)
                    except: _dv_f = 0
                    if _dna_edit.strip() and _dv_f > 0:
                        pm.update_deal(_dr["id"],{
                            "deal_value":_dv_f,"next_action":_dna_edit,
                            "next_action_date":str(_dnd_edit),"draft":False
                        }, uname)
                        audit_log("DRAFT_COMPLETED",uname,_dr["id"])
                        st.toast("✅ Deal published!"); st.rerun()
                    else:
                        st.error("Value and next action are required to publish.")
                if _d2.button("🗑️ Discard draft", key=f"drd_{_dr['id']}"):
                    pm.delete_deal(_dr["id"], uname)
                    audit_log("DRAFT_DISCARDED",uname,_dr["id"]); st.rerun()

    # ── Deals I'm backing up ─────────────────────────────────────────
    _my_backup_deals = [d for d in all_deals
                        if my_code in [str(b) for b in d.get("backup_staff_codes", [])]
                        and d["stage"] in ACTIVE_STAGES]
    if _my_backup_deals:
        st.markdown(f"<div class='section-ttl'>🤝 Deals I'm backing up ({len(_my_backup_deals)})</div>",
                    unsafe_allow_html=True)
        st.caption("You have been named backup on these deals. You can move the stage but not edit details.")
        for _bu in _my_backup_deals:
            _bu_ov = _bu.get("next_action_date","") < today_s
            st.markdown(
                f"<div style='padding:10px 14px;background:#F5F3FF;"
                f"border:1px solid #DDD6FE;border-left:4px solid #7C3AED;"
                f"border-radius:0 8px 8px 0;margin:4px 0;font-size:11px'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<b>{_bu.get('client_name','—')}</b> "
                f"<span style='color:#7C3AED;font-weight:700'>{_bu['id']} [{_bu['stage']}]</span></div>"
                f"<div style='color:var(--color-text-secondary);margin-top:2px'>"
                f"Owner: {_bu.get('staff_name','—')} · {_bu.get('product_type','—')} · "
                f"KES {fmt_num(float(_bu.get('deal_value',0)),short=True)}</div>"
                f"<div style='color:{'#EF4444' if _bu_ov else '#6B7280'};margin-top:2px'>"
                f"{'⚠️ OVERDUE' if _bu_ov else '📅'} {_bu.get('next_action_date','—')} — "
                f"{_bu.get('next_action','—')[:50]}</div>"
                f"</div>", unsafe_allow_html=True)

    # ── Overdue ───────────────────────────────────────────────────────
    st.markdown(f"<div class='section-ttl'>🔴 Overdue actions ({len(overdue)})</div>",
                unsafe_allow_html=True)
    if overdue:
        for _d in sorted(overdue, key=lambda x: x.get("next_action_date","")):
            _dl = (date.today()-date.fromisoformat(_d["next_action_date"])).days
            st.markdown(
                f"<div class='alert-banner alert-red'>"
                f"<div style='flex:1'>"
                f"<b>{_d.get('client_name','—')}</b> · {_d['id']} · "
                f"{_d.get('product_type','—')} · KES {fmt_num(float(_d.get('deal_value',0)),short=True)}"
                f"<span style='float:right;color:#EF4444;font-weight:800'>{_dl}d late</span><br>"
                f"<span style='font-size:10px;color:#991B1B'>{_d.get('next_action','—')}</span>"
                f"</div></div>", unsafe_allow_html=True)
    else:
        st.markdown("<div class='alert-banner alert-green'>✅ No overdue actions — pipeline on track!</div>",
                    unsafe_allow_html=True)

    # ── Due today ─────────────────────────────────────────────────────
    st.markdown(f"<div class='section-ttl'>🟡 Due today ({len(due_today)})</div>",
                unsafe_allow_html=True)
    if due_today:
        for _d in due_today:
            st.markdown(
                f"<div class='alert-banner alert-amber'>"
                f"<b>{_d.get('client_name','—')}</b> · {_d['id']} · {_d.get('product_type','—')}<br>"
                f"<span style='font-size:10px'>{_d.get('next_action','—')}</span>"
                f"</div>", unsafe_allow_html=True)
    else:
        st.info("Nothing scheduled for today.")

    # ── Cancel / delete ───────────────────────────────────────────────
    st.markdown("<div class='section-ttl'>🗑️ Cancel or delete a deal</div>",
                unsafe_allow_html=True)
    _cancellable = [d for d in view_deals if d["stage"] in ACTIVE_STAGES
                    and not d.get("cancel_requested") and not d.get("draft")]
    if _cancellable:
        _co = {f"{d['id']} · {d.get('client_name','')} [{d['stage']}]": d for d in _cancellable}
        _csel = st.selectbox("Select deal", list(_co.keys()), key="pl_csel")
        if _csel:
            _cd = _co[_csel]
            _creason = st.text_input("Reason *", key="pl_creason",
                placeholder="e.g. Duplicate entry / customer no longer interested")
            _is_lead = _cd.get("stage") == "Lead"
            if _is_lead:
                st.caption("💡 At Lead stage you can delete immediately — no approval needed.")
                if st.button("🗑️ Delete lead", type="primary", key="pl_del"):
                    if _creason.strip():
                        pm.delete_deal(_cd["id"], uname)
                        audit_log("DEAL_DELETED",uname,f"{_cd['id']}|{_creason}"); st.toast("Deleted"); st.rerun()
                    else: st.error("Reason required.")
            else:
                st.warning(f"Deal is at **{_cd['stage']}** — manager approval needed to cancel.")
                if st.button("📨 Request manager approval to cancel", key="pl_reqcan"):
                    if _creason.strip():
                        pm.request_cancel(_cd["id"], uname, _creason)
                        audit_log("CANCEL_REQUESTED",uname,f"{_cd['id']}|{_creason}"); st.success("Request sent."); st.rerun()
                    else: st.error("Reason required.")

    # ── Log activity ──────────────────────────────────────────────────
    st.markdown("<div class='section-ttl'>📝 Log an activity</div>",
                unsafe_allow_html=True)
    _my_active = [d for d in active if str(d.get("staff_code",""))==my_code or d.get("staff_name","")==my_name]
    if _my_active:
        _ao = {f"{d['id']} · {d.get('client_name','')} [{d['stage']}]": d["id"] for d in _my_active}
        with st.form("activity_form"):
            _a1,_a2 = st.columns(2)
            _asel = _a1.selectbox("Deal", list(_ao.keys()), key="pl_asel")
            _atype= _a2.selectbox("Activity type", ACTIVITY_TYPES)
            _aout = _a1.selectbox("Outcome",["Positive — progressing","Neutral — needs follow-up",
                "Negative — at risk","No response","Completed"])
            _anote= _a2.text_area("Notes *", height=80)
            _anxt = _a1.text_input("Next step")
            _anxtdt=_a2.date_input("Next step date",
                value=date.today()+timedelta(days=2), key="pl_adt")
            if st.form_submit_button("📝 Log activity", type="primary", use_container_width=True):
                if not _anote.strip(): st.error("Notes required.")
                else:
                    _did = _ao[_asel]
                    pm.add_activity({"deal_id":_did,"staff_code":my_code,"staff_name":my_name,
                        "activity_type":_atype,"outcome":_aout,"note":_anote,
                        "next_action":_anxt,"next_action_date":str(_anxtdt)})
                    pm.update_deal(_did,{"next_action":_anxt,"next_action_date":str(_anxtdt)},uname)
                    audit_log("ACTIVITY_LOGGED",uname,f"{_did}|{_atype}"); st.success("✅ Logged"); st.rerun()

# ══════════════════════════════════════════════════════════════════════
# TAB 4 — ANALYTICS
# ══════════════════════════════════════════════════════════════════════
with tabs[3]:
    if not live_deals:
        st.info("No live deals yet.")
    else:
        _cat_map = {p:cat for cat,prods in PRODUCT_CATALOGUE.items() for p in prods}

        # ── Analytics sub-navigation ───────────────────────────────────
        _an_view = st.radio("Dashboard view",
            ["📊 Overview","🎯 Targets vs Pipeline","🌍 Sectors & Segments",
             "📈 Conversion & Velocity","👥 Relationship Quality"],
            horizontal=True, key="pl_an_view")

        # ── Shared helpers ─────────────────────────────────────────────
        def _pip_chart_clr(pct):
            return "#10B981" if pct>=100 else "#F59E0B" if pct>=60 else "#EF4444"

        _PROD_KPI_MAP = {
            "Business Loan":"Loan Book Growth","Personal Loan":"Disbursements Retail Loans",
            "Mortgage / Home Loan":"Loan Book Growth","Overdraft":"Loan Book Growth",
            "Asset Finance":"Disbursements Retail Loans","LPO Finance":"Disbursements Retail Loans",
            "Trade Finance":"Disbursements Retail Loans","Bancassurance":"Bancassurance",
            "DFS Onboarding":"Collection Throughput","Current Account (CASA)":"Retail & MSME Deposit Growth",
            "Savings Account (CASA)":"Retail & MSME Deposit Growth","Fixed Deposit":"Retail & MSME Deposit Growth",
            "Call Deposit":"Retail & MSME Deposit Growth","Business Current Account":"Retail & MSME Deposit Growth",
        }

        # ══════════════════════════════════════════════════════════════
        if "Overview" in _an_view:
        # ══════════════════════════════════════════════════════════════
            st.markdown("### 📊 Pipeline overview")

            # Row 1: Pipeline by category
            _hl = [("Loans & Credit","#2563EB","📈"),
                   ("Deposits & CASA","#059669","💰"),
                   ("Insurance & Bancassurance","#F59E0B","🛡️"),
                   ("Digital & Transactional","#7C3AED","📱"),
                   ("Treasury & Investments","#DC2626","🏛️")]
            _cats_act={}; _cats_won={}; _cats_cnt={}
            for d in active:
                _c = _cat_map.get(d.get("product_type",""),"Other Facilities")
                _cats_act[_c] = _cats_act.get(_c,0)+float(d.get("deal_value",0))*float(d.get("probability",0.5))
                _cats_cnt[_c] = _cats_cnt.get(_c,0)+1
            for d in won:
                _c = _cat_map.get(d.get("product_type",""),"Other Facilities")
                _cats_won[_c] = _cats_won.get(_c,0)+float(d.get("deal_value",0))

            _oc = st.columns(5)
            for _i,(_cat,_clr,_ico) in enumerate(_hl):
                _av=_cats_act.get(_cat,0); _wv=_cats_won.get(_cat,0); _cn=_cats_cnt.get(_cat,0)
                _oc[_i].markdown(
                    f"<div class='kpi-c' style='border-top:4px solid {_clr};padding:12px'>"
                    f"<div style='font-size:20px;margin-bottom:4px'>{_ico}</div>"
                    f"<div class='kpi-lbl' style='color:{_clr};font-size:9px'>{_cat[:16]}</div>"
                    f"<div style='font-size:16px;font-weight:800;color:{_clr}'>{fmt_num(_av,short=True)}</div>"
                    f"<div class='kpi-sub'>{_cn} active deals</div>"
                    f"<div style='font-size:10px;color:#10B981;font-weight:700;margin-top:3px'>"
                    f"Won: {fmt_num(_wv,short=True)}</div>"
                    f"<div style='height:3px;background:var(--color-background-secondary);border-radius:2px;margin-top:6px'>"
                    f"<div style='height:100%;width:{min(100,_wv/max(_av,1)*100):.0f}%;"
                    f"background:{_clr};border-radius:2px'></div></div>"
                    f"</div>", unsafe_allow_html=True)

            st.markdown("<div style='height:8px'></div>",unsafe_allow_html=True)

            # Row 2: NTB vs Existing + Pipeline by stage
            _r2a, _r2b = st.columns(2)
            _ntb_deals  = [d for d in active if d.get("is_ntb")]
            _ex_deals   = [d for d in active if not d.get("is_ntb")]
            _ntb_v = sum(float(d.get("deal_value",0)) for d in _ntb_deals)
            _ex_v  = sum(float(d.get("deal_value",0)) for d in _ex_deals)
            _ntb_cnt = len(_ntb_deals); _ex_cnt = len(_ex_deals)
            with _r2a:
                fig_ntb = go.Figure(data=[go.Bar(
                    x=["NTB","Existing"],
                    y=[_ntb_v, _ex_v],
                    marker_color=["#10B981","#3B82F6"],
                    text=[f"KES {fmt_num(_ntb_v,short=True)}<br>{_ntb_cnt} deals",
                          f"KES {fmt_num(_ex_v,short=True)}<br>{_ex_cnt} deals"],
                    textposition="outside")])
                fig_ntb.update_layout(title="NTB vs Existing Customer (pipeline value)",
                    height=280,margin=dict(l=10,r=10,t=40,b=10),
                    plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                    showlegend=False)
                st.plotly_chart(fig_ntb, use_container_width=True)

            with _r2b:
                _stg_v = {}; _stg_cnt = {}
                for d in active:
                    sn = d["stage"]
                    _stg_v[sn] = _stg_v.get(sn,0)+float(d.get("deal_value",0))
                    _stg_cnt[sn] = _stg_cnt.get(sn,0)+1
                fig_stg = go.Figure(data=[go.Bar(
                    x=list(_stg_v.keys()), y=list(_stg_v.values()),
                    marker_color=[STAGE_CLR.get(s,"#6B7280") for s in _stg_v],
                    text=[fmt_num(v,short=True) for v in _stg_v.values()],
                    textposition="outside")])
                fig_stg.update_layout(title="Pipeline value by stage",
                    height=280,margin=dict(l=10,r=10,t=40,b=10),
                    plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
                    showlegend=False)
                st.plotly_chart(fig_stg, use_container_width=True)

            # Row 3: Lead source + Win/Loss trend
            _r3a, _r3b = st.columns(2)
            _src = {}
            for d in live_deals: _src[d.get("source","Other")] = _src.get(d.get("source","Other"),0)+1
            with _r3a:
                if _src:
                    fig_src = px.pie(names=list(_src.keys()),values=list(_src.values()),
                        title="Deals by lead source",
                        color_discrete_sequence=px.colors.qualitative.Pastel)
                    fig_src.update_layout(height=280,margin=dict(l=0,r=0,t=40,b=0))
                    st.plotly_chart(fig_src,use_container_width=True)
            with _r3b:
                _wl_months = {}
                for d in live_deals:
                    if d["stage"] in ("Closed Won","Closed Lost"):
                        mo = str(d.get("updated_at",""))[:7]
                        if mo:
                            _wl_months.setdefault(mo,{"Won":0,"Lost":0})
                            _wl_months[mo][d["stage"].replace("Closed ","")] += 1
                if _wl_months:
                    _wl_df = pd.DataFrame([{"Month":m,**v} for m,v in sorted(_wl_months.items())])
                    fig_wl = px.bar(_wl_df,x="Month",y=["Won","Lost"],
                        title="Monthly win / loss trend",barmode="group",
                        color_discrete_map={"Won":"#10B981","Lost":"#EF4444"})
                    fig_wl.update_layout(height=280,margin=dict(l=10,r=10,t=40,b=40))
                    st.plotly_chart(fig_wl,use_container_width=True)

        # ══════════════════════════════════════════════════════════════
        elif "Targets" in _an_view:
        # ══════════════════════════════════════════════════════════════
            st.markdown("### 🎯 Pipeline vs cascade targets")
            _casc2 = st.session_state.get("cascade_manager")
            _kpi_tgts = {}
            if _casc2:
                _gv = _casc2.get_what_i_was_given(my_code,_gfy(),my_name) if not is_md else []
                for _kp in ["Disbursements Retail Loans","Loan Book Growth","Total NFI",
                            "Retail & MSME Deposit Growth","Collection Throughput","Bancassurance","New Accounts"]:
                    _m = next((g for g in _gv if g.get("kpi")==_kp),None)
                    if _m: _kpi_tgts[_kp] = float(_m["amount"])
                    elif is_md:
                        _bt = _casc2.get_bank_target(_kp,_gfy())
                        if _bt: _kpi_tgts[_kp] = float(_bt.get("target",0))

            if not _kpi_tgts:
                st.info("No cascade targets set yet. Ask your manager to cascade targets first.")
            else:
                _pbk = {}
                for d in active:
                    for _pk2,_kk in _PROD_KPI_MAP.items():
                        if _pk2.lower() in str(d.get("product_type","")).lower():
                            _pbk[_kk] = _pbk.get(_kk,0)+float(d.get("deal_value",0))*float(d.get("probability",0.5))
                            break

                # Gauge-style progress bars for each KPI
                for _kp,_tgt in _kpi_tgts.items():
                    _won_v = sum(float(d.get("deal_value",0)) for d in won
                                 if any(_pk2.lower() in str(d.get("product_type","")).lower()
                                        for _pk2,_kk in _PROD_KPI_MAP.items() if _kk==_kp))
                    _pipe_v= _pbk.get(_kp,0)
                    _total = _won_v + _pipe_v
                    _pct   = min(200,_total/_tgt*100) if _tgt else 0
                    _won_pct = min(100,_won_v/_tgt*100) if _tgt else 0
                    _pip_pct = min(100-_won_pct,_pipe_v/_tgt*100) if _tgt else 0
                    _clr2  = _pip_chart_clr(_pct)
                    _gap   = max(0,_tgt-_total)
                    st.markdown(
                        f"<div style='padding:14px 16px;background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);"
                        f"border-radius:12px;margin-bottom:8px'>"
                        f"<div style='display:flex;justify-content:space-between;margin-bottom:8px'>"
                        f"<span style='font-weight:700;font-size:12px;color:var(--color-text-primary)'>{_kp}</span>"
                        f"<span style='font-size:12px;font-weight:800;color:{_clr2}'>{_pct:.0f}% covered</span>"
                        f"</div>"
                        f"<div style='height:12px;background:var(--color-background-secondary);border-radius:6px;overflow:hidden;margin-bottom:6px'>"
                        f"<div style='display:flex;height:100%'>"
                        f"<div style='width:{_won_pct:.1f}%;background:#10B981;border-radius:6px 0 0 6px' title='Won'></div>"
                        f"<div style='width:{_pip_pct:.1f}%;background:#3B82F6;opacity:.7' title='In pipeline'></div>"
                        f"</div></div>"
                        f"<div style='display:flex;gap:16px;font-size:10px;color:var(--color-text-secondary)'>"
                        f"<span>🏆 Won: <b style='color:#10B981'>{fmt_num(_won_v,short=True)}</b></span>"
                        f"<span>📈 Pipeline: <b style='color:#3B82F6'>{fmt_num(_pipe_v,short=True)}</b></span>"
                        f"<span>🎯 Target: <b>{fmt_num(_tgt,short=True)}</b></span>"
                        f"<span style='color:#EF4444'>Gap: <b>{fmt_num(_gap,short=True)}</b></span>"
                        f"</div></div>",
                        unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════
        elif "Sectors" in _an_view:
        # ══════════════════════════════════════════════════════════════
            st.markdown("### 🌍 Sectors & Customer Segments")
            _r1, _r2 = st.columns(2)

            # Sector breakdown
            _sec = {}
            for d in live_deals:
                _s = d.get("sector","Unknown") or "Not specified"
                if _s in ("— Select —",""): _s = "Not specified"
                _sec[_s] = _sec.get(_s,0)+float(d.get("deal_value",0))
            _sec_cnt = {}
            for d in live_deals:
                _s = d.get("sector","") or "Not specified"
                if _s in ("— Select —",""): _s = "Not specified"
                _sec_cnt[_s] = _sec_cnt.get(_s,0)+1

            with _r1:
                if _sec:
                    fig_sec = px.treemap(
                        names=list(_sec.keys()),
                        values=list(_sec.values()),
                        parents=[""]*len(_sec),
                        title="Pipeline by CBK Economic Sector (KES)",
                        color=list(_sec.values()),
                        color_continuous_scale="Blues")
                    fig_sec.update_layout(height=380,margin=dict(l=10,r=10,t=40,b=10))
                    st.plotly_chart(fig_sec,use_container_width=True)

            with _r2:
                if _sec_cnt:
                    fig_scc = px.bar(
                        x=list(_sec_cnt.keys()),y=list(_sec_cnt.values()),
                        title="Number of deals by sector",
                        color=list(_sec_cnt.values()),
                        color_continuous_scale="Teal")
                    fig_scc.update_layout(height=380,margin=dict(l=10,r=10,t=40,b=60),
                        xaxis_tickangle=-30,plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_scc,use_container_width=True)

            # Segment breakdown
            st.markdown("#### Customer segment analysis")
            _seg_data = {}
            for d in live_deals:
                _sg = d.get("client_type","") or "Unknown"
                _sg_parts = _sg.split(" — ")
                _tier1_s = _sg_parts[0] if _sg_parts else "Unknown"
                _tier2_s = _sg_parts[1] if len(_sg_parts)>1 else "—"
                _seg_data.setdefault(_tier1_s,{})
                _seg_data[_tier1_s][_tier2_s] = (
                    _seg_data[_tier1_s].get(_tier2_s,0)+float(d.get("deal_value",0)))

            _sga, _sgb, _sgc = st.columns(3)
            _seg_cols_map = [_sga, _sgb, _sgc]
            for _sgi, (_tier1_k, _tier2_v) in enumerate(_seg_data.items()):
                _sgcol = _seg_cols_map[_sgi % 3]
                _clr_t = "#2563EB" if _tier1_k=="Individual" else "#7C3AED"
                _sgcol.markdown(
                    f"<div style='background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);"
                    f"border-radius:10px;padding:12px;margin-bottom:8px'>"
                    f"<div style='font-weight:700;font-size:11px;color:{_clr_t};"
                    f"margin-bottom:8px'>{'👤' if _tier1_k=='Individual' else '🏢'} {_tier1_k}</div>"
                    + "".join(
                        f"<div style='display:flex;justify-content:space-between;"
                        f"font-size:11px;padding:3px 0;border-bottom:1px solid var(--color-background-secondary)'>"
                        f"<span style='color:var(--color-text-primary)'>{sub}</span>"
                        f"<span style='font-weight:700;color:{_clr_t}'>{fmt_num(v,short=True)}</span></div>"
                        for sub,v in sorted(_tier2_v.items(), key=lambda x:-x[1]))
                    + "</div>", unsafe_allow_html=True)

        # ══════════════════════════════════════════════════════════════
        elif "Conversion" in _an_view:
        # ══════════════════════════════════════════════════════════════
            st.markdown("### 📈 Conversion & Velocity")
            _ca, _cb = st.columns(2)

            # Funnel by category
            _funnel_cats = ["Account","Loan","Deposit"]
            for _fcat in _funnel_cats:
                _fcat_deals = [d for d in live_deals
                               if d.get("pipeline_category",get_pipeline_category(d.get("product_type",""))) == _fcat]
                if not _fcat_deals: continue
                _fstages = get_stages_for_category(_fcat)
                _fstg_cnt = {s["stage"]:0 for s in _fstages}
                for d in _fcat_deals: _fstg_cnt[d["stage"]] = _fstg_cnt.get(d["stage"],0)+1
                _funnel_df = pd.DataFrame([
                    {"Stage":s["stage"],"Count":_fstg_cnt.get(s["stage"],0)}
                    for s in _fstages if s["stage"] not in ("Closed Lost",)])
                _clr_f = {"Account":"#059669","Loan":"#2563EB","Deposit":"#7C3AED"}.get(_fcat,"#6B7280")
                fig_f = px.funnel(_funnel_df,x="Count",y="Stage",
                    title=f"{_fcat} pipeline funnel",
                    color_discrete_sequence=[_clr_f])
                fig_f.update_layout(height=300,margin=dict(l=10,r=10,t=40,b=10))
                _ca.plotly_chart(fig_f,use_container_width=True)

            # Avg days in stage (velocity)
            _stg_ages = {}
            for d in active:
                try:
                    _days = (datetime.now()-datetime.fromisoformat(
                        d.get("updated_at",datetime.now().isoformat()))).days
                    _stg_ages.setdefault(d["stage"],[]).append(_days)
                except: pass
            if _stg_ages:
                _vel_df = pd.DataFrame([
                    {"Stage":s,"Avg days stale":round(sum(v)/len(v),1),
                     "Deals":len(v)} for s,v in _stg_ages.items()])
                fig_vel = px.bar(_vel_df,x="Stage",y="Avg days stale",
                    title="Average days since last update per stage",
                    color="Avg days stale",color_continuous_scale="RdYlGn_r",
                    text="Deals")
                fig_vel.add_hline(y=14,line_dash="dash",line_color="#EF4444",
                    annotation_text="14d stale threshold")
                fig_vel.update_layout(height=300,margin=dict(l=10,r=10,t=40,b=40),
                    plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)")
                _cb.plotly_chart(fig_vel,use_container_width=True)

        # ══════════════════════════════════════════════════════════════
        elif "Relationship" in _an_view:
        # ══════════════════════════════════════════════════════════════
            st.markdown("### 👥 Relationship Quality")
            _rqa, _rqb = st.columns(2)

            # Decision level of contacts
            _dlev = {}
            for d in live_deals:
                _dl = d.get("decision_level","") or "Not captured"
                if _dl in ("— Select —",""): _dl = "Not captured"
                _dlev[_dl] = _dlev.get(_dl,0)+1
            if _dlev:
                _dl_order = ["Ultimate decision maker — signs off","Key influencer — recommends to board",
                             "Evaluator — reviews options","Gatekeeper — controls access",
                             "End user — no signing authority","Not captured"]
                _dl_vals  = [_dlev.get(d,0) for d in _dl_order if d in _dlev]
                _dl_keys  = [d.split(" —")[0][:20] for d in _dl_order if d in _dlev]
                fig_dl = go.Figure(go.Bar(
                    x=_dl_vals,y=_dl_keys,orientation="h",
                    marker_color=["#10B981","#3B82F6","#F59E0B","#F97316","#EF4444","#9CA3AF"][:len(_dl_keys)],
                    text=_dl_vals,textposition="outside"))
                fig_dl.update_layout(title="Contact decision-making level",
                    height=300,margin=dict(l=160,r=40,t=40,b=10),
                    plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)")
                _rqa.plotly_chart(fig_dl,use_container_width=True)

            # Portfolio: own vs cross
            _own   = sum(1 for d in live_deals if not d.get("portfolio_owner_code","")
                         or d.get("portfolio_owner_code","")==my_code)
            _cross = sum(1 for d in live_deals if d.get("portfolio_owner_code","")
                         and d.get("portfolio_owner_code","")!=my_code)
            if _own or _cross:
                fig_port = go.Figure(go.Pie(
                    labels=["Own portfolio","Cross-portfolio"],
                    values=[_own,_cross],
                    marker_colors=["#10B981","#F59E0B"],
                    hole=.4))
                fig_port.update_layout(title="Portfolio ownership split",
                    height=300,margin=dict(l=0,r=0,t=40,b=0))
                _rqb.plotly_chart(fig_port,use_container_width=True)

            # NTB conversion rate by segment
            _seg_ntb = {}; _seg_tot = {}
            for d in live_deals:
                _sg = (d.get("client_type","") or "Unknown").split(" — ")[-1]
                _seg_tot[_sg] = _seg_tot.get(_sg,0)+1
                if d.get("is_ntb"): _seg_ntb[_sg] = _seg_ntb.get(_sg,0)+1
            if _seg_ntb:
                _ntb_df = pd.DataFrame([
                    {"Segment":sg,"NTB deals":_seg_ntb.get(sg,0),
                     "Total":_seg_tot.get(sg,1),
                     "NTB %":round(_seg_ntb.get(sg,0)/_seg_tot.get(sg,1)*100,0)}
                    for sg in _seg_tot if sg in _seg_ntb or _seg_tot.get(sg,0)>0])
                if len(_ntb_df):
                    fig_ntb2 = px.bar(_ntb_df,x="Segment",y="NTB %",
                        title="NTB deal proportion by customer segment (%)",
                        color="NTB %",color_continuous_scale="Greens",
                        text="NTB %")
                    fig_ntb2.update_layout(height=280,margin=dict(l=10,r=10,t=40,b=60),
                        xaxis_tickangle=-30,plot_bgcolor="rgba(0,0,0,0)",
                        paper_bgcolor="rgba(0,0,0,0)")
                    st.plotly_chart(fig_ntb2,use_container_width=True)

# ══════════════════════════════════════════════════════════════════════
# TAB 5 — TEAM VIEW
# ══════════════════════════════════════════════════════════════════════
if "👥 Team View" in _tab_labels:
    with _tab("👥 Team View"):
        if not vis_staff.empty:
            st.caption(f"Your team: {len(vis_names)} staff · unit: {my_unit}")
        if not live_deals:
            st.info("No team deals found.")
            with st.expander("🔧 Debug — why am I not seeing team deals?"):
                st.markdown(f"""
**Your role:** {ud.get('role','')}  
**Your unit:** {my_unit}  
**Staff visible to you ({len(vis_names)}):** {', '.join(sorted(vis_names)) or '(none)'}  
**Total deals in system:** {len(all_deals)}  
**Deals in your unit:** {sum(1 for d in all_deals if d.get('unit','') == my_unit)}  

**Possible causes:**
- Staff haven't added any pipeline deals yet
- Deals were created with a different unit name — check that staff unit matches "{my_unit}"
- If unit is blank in BSC data, deals won't be matched by unit
                """)
        else:
            # ── Category filter icons ─────────────────────────────────
            _tv_cat = st.radio(
                "View by",
                ["📊 All","📈 Loans (Assets)","💰 Deposits (Liabilities)","🆕 New Accounts"],
                horizontal=True, key="pl_tv_cat")

            _ASSET_P  = _ASSET_PRODUCTS  # defined at top of page
            _LIAB_P   = _LIAB_PRODUCTS
            _ACCT_P   = {"Current Account (CASA)","Savings Account (CASA)",
                         "Junior Account","Business Current Account","Business Savings"}

            def _cat_filter(d):
                pt = d.get("product_type","")
                if "Assets" in _tv_cat:   return pt in _ASSET_P
                if "Liabilities" in _tv_cat: return pt in _LIAB_P
                if "Accounts" in _tv_cat: return pt in _ACCT_P
                return True  # All

            _tv_deals = [d for d in live_deals if _cat_filter(d)]

            if not _tv_deals:
                st.info(f"No deals in this category yet for your team.")
            else:
                # Per-staff summary
                _ss = {}
                for d in _tv_deals:
                    sn  = d.get("staff_name","Unknown")
                    val = float(d.get("deal_value",0))
                    s   = _ss.setdefault(sn,{
                        "active":0,"loans":0,"deposits":0,"accounts":0,
                        "pipeline":0,"won":0,"won_val":0,"lost":0,
                        "overdue":0,"unvalidated":0})
                    pt = d.get("product_type","")
                    if d["stage"] in ACTIVE_STAGES:
                        s["active"]  += 1
                        s["pipeline"]+= val
                        if pt in _ASSET_P: s["loans"]    += val
                        if pt in _LIAB_P:  s["deposits"] += val
                        if pt in _ACCT_P:  s["accounts"] += 1
                        if d.get("next_action_date","") < today_s: s["overdue"]+=1
                        if not d.get("manager_validated") and d["stage"] in STAGE_NAMES[1:]: s["unvalidated"]+=1
                    elif d["stage"]=="Closed Won":  s["won"]+=1; s["won_val"]+=val
                    elif d["stage"]=="Closed Lost": s["lost"]+=1

                # Render per-staff scorecards
                for _sn, _sv in sorted(_ss.items(), key=lambda x: -x[1]["pipeline"]):
                    _wr   = round(_sv["won"]/max(_sv["won"]+_sv["lost"],1)*100,0)
                    _ov_c = "#EF4444" if _sv["overdue"] else "#10B981"
                    _uv_c = "#F59E0B" if _sv["unvalidated"] else "#6B7280"
                    st.markdown(
                        f"<div style='background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);"
                        f"border-radius:12px;padding:14px 16px;margin-bottom:8px;"
                        f"box-shadow:0 1px 4px rgba(0,0,0,0.04)'>"
                        f"<div style='display:flex;align-items:center;justify-content:space-between;"
                        f"margin-bottom:10px'>"
                        f"<span style='font-weight:700;font-size:13px;color:var(--color-text-primary)'>👤 {_sn}</span>"
                        f"<div style='display:flex;gap:12px;font-size:10px'>"
                        f"<span style='color:var(--color-text-secondary)'>{_sv['active']} active · {_sv['won']}W · {_sv['lost']}L</span>"
                        f"<span style='color:{_ov_c};font-weight:700'>⚠️ {_sv['overdue']} overdue</span>"
                        f"<span style='color:{_uv_c};font-weight:600'>⏳ {_sv['unvalidated']} unvalidated</span>"
                        f"</div></div>"
                        f"<div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px'>"
                        f"<div style='background:#EFF6FF;border-radius:8px;padding:8px 10px'>"
                        f"<div style='font-size:9px;color:#3B82F6;font-weight:700;text-transform:uppercase'>📊 Total Pipeline</div>"
                        f"<div style='font-size:14px;font-weight:800;color:#1E40AF'>KES {fmt_num(_sv['pipeline'],short=True)}</div>"
                        f"<div style='font-size:10px;color:var(--color-text-secondary)'>Won: {fmt_num(_sv['won_val'],short=True)}</div>"
                        f"</div>"
                        f"<div style='background:#EFF6FF;border-radius:8px;padding:8px 10px'>"
                        f"<div style='font-size:9px;color:#2563EB;font-weight:700;text-transform:uppercase'>📈 Loans</div>"
                        f"<div style='font-size:14px;font-weight:800;color:#1E40AF'>KES {fmt_num(_sv['loans'],short=True)}</div>"
                        f"<div style='font-size:10px;color:var(--color-text-secondary)'>Assets pipeline</div>"
                        f"</div>"
                        f"<div style='background:#ECFDF5;border-radius:8px;padding:8px 10px'>"
                        f"<div style='font-size:9px;color:#059669;font-weight:700;text-transform:uppercase'>💰 Deposits</div>"
                        f"<div style='font-size:14px;font-weight:800;color:#065F46'>KES {fmt_num(_sv['deposits'],short=True)}</div>"
                        f"<div style='font-size:10px;color:var(--color-text-secondary)'>Liabilities pipeline</div>"
                        f"</div>"
                        f"<div style='background:#F5F3FF;border-radius:8px;padding:8px 10px'>"
                        f"<div style='font-size:9px;color:#7C3AED;font-weight:700;text-transform:uppercase'>🆕 Accounts</div>"
                        f"<div style='font-size:14px;font-weight:800;color:#5B21B6'>{_sv['accounts']} deals</div>"
                        f"<div style='font-size:10px;color:var(--color-text-secondary)'>CASA / New accts</div>"
                        f"</div></div>"
                        f"<div style='margin-top:8px;height:4px;background:var(--color-background-secondary);border-radius:2px'>"
                        f"<div style='height:100%;width:{min(100,_wr):.0f}%;background:#10B981;border-radius:2px' title='Win rate {_wr:.0f}%'></div>"
                        f"</div>"
                        f"<div style='font-size:9px;color:var(--color-text-secondary);margin-top:2px'>Win rate: {_wr:.0f}%</div>"
                        f"</div>", unsafe_allow_html=True)

                # Stacked bar by stage
                _sb = {}
                for d in _tv_deals:
                    sn = d.get("staff_name","")
                    _sb.setdefault(sn,{s["stage"]:0 for s in PIPELINE_STAGES})
                    _sb[sn][d["stage"]] = _sb[sn].get(d["stage"],0)+1
                _sb_df = pd.DataFrame(_sb).T.reset_index().rename(columns={"index":"Staff"})
                if len(_sb_df):
                    _melt = _sb_df.melt("Staff",var_name="Stage",value_name="Count")
                    _fig  = px.bar(_melt[_melt["Count"]>0],x="Staff",y="Count",
                        color="Stage",title="Deals by stage per staff member",
                        color_discrete_map=STAGE_CLR)
                    _fig.update_layout(height=300,margin=dict(l=10,r=10,t=40,b=60),xaxis_tickangle=-30)
                    st.plotly_chart(_fig,use_container_width=True)

# ══════════════════════════════════════════════════════════════════════
# TAB 6 — ACTIVITY LOG
# ══════════════════════════════════════════════════════════════════════
with tabs[-1]:
    _asc  = my_code if not is_mgr else None
    _acts = pm.get_activities(staff_code=_asc,limit=150)
    if not _acts:
        st.info("No activities yet.")
    else:
        _adf  = pd.DataFrame(_acts)
        _show = [c for c in ["recorded_at","deal_id","staff_name","activity_type",
                              "outcome","note","next_action","next_action_date"] if c in _adf.columns]
        _disp = _adf[_show].copy()
        if "recorded_at" in _disp.columns:
            _disp["recorded_at"] = _disp["recorded_at"].str[:16].str.replace("T"," ")
        _disp.columns = [c.replace("_"," ").title() for c in _disp.columns]
        def _hl_o(v):
            if "Positive" in str(v): return "color:#10B981;font-weight:700"
            if "Negative" in str(v): return "color:#EF4444;font-weight:700"
            return ""
        st.dataframe(
            _disp.style.map(_hl_o, subset=["Outcome"] if "Outcome" in _disp.columns else []),
            use_container_width=True,hide_index=True,height=450)
