"""pages/0_home.py — A2Z Blueprint Welcome & Landing Page."""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
from datetime import datetime
from utils.core_audit import check_access, get_visible_staff
from utils.core import MODULE_ACCESS
from pages._shared import load_shared_state, safe_html, get_user_proposition
from pages._access import require_access

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()


require_access("perform")

um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()

staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
# V-004 mitigation — these values flow into st.markdown(unsafe_allow_html=True)
# blocks throughout this file. An admin who sets a user's full_name to
# <script>...</script> would XSS every viewer of the home page. Escape once
# at the source so every downstream interpolation is safe by default.
_raw_name = ud.get("full_name", uname) or uname
_raw_role = ud.get("role", "")
_raw_unit = ud.get("unit", "")
name    = safe_html(_raw_name)
role    = safe_html(_raw_role)
unit    = safe_html(_raw_unit)
hour    = datetime.now().hour
greet   = ("Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening")

# ── Hero section ──────────────────────────────────────────────────────
# ── Hero — two-column layout: tagline left, stats/info right ────────
_h_left = (
    # Left column — logo text + tagline
    "<div style='flex:1;min-width:0;padding-right:32px'>"
    f"<div style='font-size:10px;color:rgba(255,255,255,0.45);letter-spacing:2px;"
    f"text-transform:uppercase;font-weight:600;margin-bottom:4px'>"
    f"{greet}</div>"
    f"<div style='font-size:22px;font-weight:900;color:var(--color-background-primary);line-height:1.2;"
    f"letter-spacing:-0.3px;margin-bottom:2px'>"
    f"Welcome back, <span style='color:#F5A623'>{name.split()[0]}</span></div>"
    "<div style='font-size:13px;color:rgba(255,255,255,0.55);margin-bottom:10px;font-weight:400'>"
    "A2Z Blueprint — Perform · Execute · Integrate</div>"
    "<div style='font-size:11px;color:rgba(255,255,255,0.65);line-height:1.65;"
    "font-style:italic;max-width:480px'>"
    "A wholesome performance and strategy execution platform where precision "
    "integrates with market intelligence — offering A-to-Z depth of knowledge, "
    "convergence, analytics and insights for objective decisioning."
    "</div>"
    # Role + unit pills
    f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin-top:14px'>"
    f"<span style='background:rgba(255,255,255,0.12);border-radius:12px;"
    f"padding:3px 12px;font-size:10px;color:rgba(255,255,255,0.85);font-weight:600'>"
    f"{role}</span>"
    f"<span style='background:rgba(245,166,35,0.2);border:1px solid rgba(245,166,35,0.35);"
    f"border-radius:12px;padding:3px 12px;font-size:10px;color:#F5A623;font-weight:600'>"
    f"{unit or 'Group'}</span>"
    f"<span style='background:rgba(255,255,255,0.08);border-radius:12px;"
    f"padding:3px 12px;font-size:10px;color:rgba(255,255,255,0.6)'>"
    f"{datetime.now().strftime('%d %b %Y  ·  %H:%M')}</span>"
    "</div>"
    "</div>"  # end left
)

_h_right = (
    # Right column — three pillar cards
    "<div style='display:flex;flex-direction:column;gap:6px;min-width:200px;width:220px'>"
    "<div style='background:rgba(255,255,255,0.08);border-radius:8px;"
    "padding:8px 12px;border-left:3px solid var(--brand-primary,#006B3F)'>"
    "<div style='font-size:9px;color:rgba(255,255,255,0.45);text-transform:uppercase;"
    "letter-spacing:1px;font-weight:600'>A2Z Perform</div>"
    "<div style='font-size:10px;color:rgba(255,255,255,0.75);margin-top:2px'>"
    "BSC tracking · Cascade · Rankings</div>"
    "</div>"
    "<div style='background:rgba(255,255,255,0.08);border-radius:8px;"
    "padding:8px 12px;border-left:3px solid #185FA5'>"
    "<div style='font-size:9px;color:rgba(255,255,255,0.45);text-transform:uppercase;"
    "letter-spacing:1px;font-weight:600'>A2Z Execute</div>"
    "<div style='font-size:10px;color:rgba(255,255,255,0.75);margin-top:2px'>"
    "Pipeline · SLA · CIMS · Campaigns</div>"
    "</div>"
    "<div style='background:rgba(255,255,255,0.08);border-radius:8px;"
    "padding:8px 12px;border-left:3px solid #6B21A8'>"
    "<div style='font-size:9px;color:rgba(255,255,255,0.45);text-transform:uppercase;"
    "letter-spacing:1px;font-weight:600'>A2Z Integrate</div>"
    "<div style='font-size:10px;color:rgba(255,255,255,0.75);margin-top:2px'>"
    "Intel · SBU · Leverage · People</div>"
    "</div>"
    "</div>"  # end right
)

_h = (
    "<div style='background:linear-gradient(135deg,#004A2B 0%,var(--brand-primary,#006B3F) 55%,#185FA5 100%);"
    "border-radius:14px;padding:28px 32px;margin-bottom:20px;"
    "box-shadow:0 4px 20px rgba(0,0,0,0.15);position:relative;overflow:hidden'>"
    # Decorative
    "<div style='position:absolute;top:-30px;right:240px;width:160px;height:160px;"
    "border-radius:50%;background:rgba(255,255,255,0.03)'></div>"
    # Two-column flex
    "<div style='display:flex;align-items:center;gap:0'>"
    + _h_left + _h_right +
    "</div>"
    "</div>"
)
st.markdown(_h, unsafe_allow_html=True)

# ── Quick stats (if data loaded) ──────────────────────────────────────
if len(staff_scores):
    vis    = get_visible_staff(ud, staff_scores)
    my_row = staff_scores[staff_scores["Staff Name"]==_raw_name]

    # Build stat cards as styled HTML
    _stats = []
    if len(my_row):
        r    = my_row.iloc[0]
        _bsc = float(r.get("Final_BSC_Score", 0) or 0)
        _rem = r.get("Performance_Remark","—")
        _rnk = r.get("Overall_Rank","—")
        _clr = {"Exceeded By Far":"var(--brand-primary,#006B3F)","Exceeded":"var(--brand-mid,#1D9E75)","Met":"#F5A623",
                "Partially Met":"#E67E22","Unmet":"#E24B4A"}.get(_rem,"#9CA3AF")
        _stats.append(("My BSC score",    f"{_bsc:.2f} / 5.0", _clr, "⭐"))
        _stats.append(("Performance",     _rem,                 _clr, "🏅"))
        _stats.append(("Overall rank",    f"#{_rnk}",           "#185FA5","🏆"))
    else:
        _avg_bsc = vis["Final_BSC_Score"].mean() if "Final_BSC_Score" in vis.columns else 0
        _stats.append(("Staff in view",   str(len(vis)),            "var(--brand-primary,#006B3F)","👥"))
        _stats.append(("Team avg BSC",    f"{_avg_bsc:.2f}",        "#185FA5","📊"))
        _stats.append(("Exceeded",
            str(int((vis["Final_BSC_Score"]>=3.1).sum())) if "Final_BSC_Score" in vis.columns else "—",
            "var(--brand-primary,#006B3F)","🟢"))

    if casc:
        try:
            _my_sc2 = str(ud.get("staff_code","") or uname)
            _locked  = casc.targets_locked(_my_sc2,_gfy())
            _given   = casc.get_what_i_was_given(_my_sc2,_gfy(),_raw_name)
            _clbl    = "🔒 Locked" if _locked else ("⏳ Received" if _given else "⚠️ Not set")
            _cclr    = "var(--brand-primary,#006B3F)" if _locked else ("#F5A623" if _given else "#E24B4A")
            _stats.append(("My cascade",  _clbl, _cclr, "🎯"))
        except: pass

    try:
        _my_deals = pm.get_deals(staff_code=str(ud.get("staff_code","") or uname))
        _active_d = [d for d in _my_deals if d["stage"] not in ("Closed Won","Closed Lost")]
        _pipe_val = sum(float(d.get("deal_value",0))*float(d.get("probability",0.5)) for d in _active_d)
        _stats.append(("Pipeline deals",  f"{len(_active_d)} · KES {_pipe_val/1e6:.1f}M", "#185FA5","💼"))
    except: pass

    # Render stat cards
    _n_stats = len(_stats)
    _s_cols  = st.columns(_n_stats)
    for _ci, (_lbl, _val, _clr, _icon) in enumerate(_stats):
        _s_cols[_ci].markdown(
            f"<div style='padding:12px 14px;background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);"
            f"border-radius:10px;border-top:3px solid {_clr};'>"
            f"<div style='font-size:16px;margin-bottom:4px'>{_icon}</div>"
            f"<div style='font-size:18px;font-weight:700;color:{_clr}'>{_val}</div>"
            f"<div style='font-size:10px;color:var(--color-text-tertiary);margin-top:3px'>{_lbl}</div>"
            f"</div>",
            unsafe_allow_html=True)

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # ── Notification panel ────────────────────────────────────────────
    # Notifications are pre-computed in app.py and stored in session state
    _notifs = st.session_state.get("notifications", [])
    if _notifs:
        for _nf in _notifs:
            _nl  = _nf.get("level","info")
            _bg  = {"urgent":"#FEF2F2","warning":"#FFF7ED","info":"#EFF6FF"}.get(_nl,"#F9FAFB")
            _brd = {"urgent":"#FCA5A5","warning":"#FED7AA","info":"#BFDBFE"}.get(_nl,"#E5E7EB")
            _fc  = {"urgent":"#991B1B","warning":"#92400E","info":"#1E40AF"}.get(_nl,"#374151")
            st.markdown(
                f"<div style='padding:8px 14px;background:{_bg};border:1px solid {_brd};"
                f"border-radius:8px;font-size:12px;color:{_fc};margin-bottom:6px;'>"
                f"{_nf['icon']} {_nf['msg']}</div>",
                unsafe_allow_html=True)

    st.markdown("---")

# ── Proposition head summary ─────────────────────────────────────────
_prop_tag_home = get_user_proposition()
if _prop_tag_home:
    try:
        import json as _phj; from pathlib import Path as _php
        _pcfg_h = _phj.loads((_php(__file__).parent.parent/"data"/"proposition_config.json").read_text())
        _pperf_h= _phj.loads((_php(__file__).parent.parent/"data"/"proposition_performance.json").read_text())
        _ph_prop = _pperf_h.get(_prop_tag_home,{})
        _ph_cfg  = _pcfg_h.get("propositions", {}).get(_prop_tag_home,{})
        _ph_score= _ph_prop.get("proposition_score",0)
        _ph_color= _ph_cfg.get("color","#006B3F")
        _ph_icon = _ph_cfg.get("icon","🎯")
        _ph_name = _ph_cfg.get("name","")
        _ph_cust = _ph_prop.get("total_tagged_customers",0)
        _ph_kpis = _ph_prop.get("kpis",[])
        _ph_score_lbl = ("Outstanding" if _ph_score>=4.5 else "Exceeds" if _ph_score>=3.5
                          else "Meets" if _ph_score>=2.5 else "Needs Improvement")
        st.markdown(
            f"<div style='background:{_ph_color}08;border:1.5px solid {_ph_color}30;"
            f"border-radius:12px;padding:16px;margin-bottom:16px'>"
            f"<div style='display:flex;align-items:center;gap:12px;margin-bottom:10px'>"
            f"<div style='font-size:28px'>{_ph_icon}</div>"
            f"<div><div style='font-size:14px;font-weight:700;color:{_ph_color}'>"
            f"{_ph_name}</div>"
            f"<div style='font-size:11px;color:var(--color-text-tertiary)'>"
            f"{_ph_cust:,} tagged customers · Proposition score: "
            f"<b style='color:{_ph_color}'>{_ph_score:.2f}</b> ({_ph_score_lbl})</div>"
            f"</div></div>"
            f"<div style='display:flex;gap:8px;flex-wrap:wrap'>",
            unsafe_allow_html=True)
        # Show top 3 KPIs
        for _k in sorted(_ph_kpis, key=lambda x:-x.get("achievement",0))[:3]:
            _k_ach = _k.get("achievement",0)
            _k_clr = "#16A34A" if _k_ach>=100 else "#D97706" if _k_ach>=80 else "#DC2626"
            st.markdown(
                f"<div style='background:{_k_clr}10;border:1px solid {_k_clr}30;"
                f"border-radius:8px;padding:6px 12px;font-size:11px'>"
                f"<b style='color:{_k_clr}'>{_k_ach:.0f}%</b> {_k['name']}</div>",
                unsafe_allow_html=True)
        st.markdown("</div></div>", unsafe_allow_html=True)
    except Exception: pass

# ── Smart Alerts widget on home ──────────────────────────────────
try:
    _sa_alerts = []
    _fd_h = [r for r in json.loads((Path(__file__).parent.parent/"data"/"treasury_fd.json").read_text())
              if r.get("maturity_date") and r["status"] in ("approved","booked")
              and 0<=(_safe_date(r["maturity_date"])-date.today()).days<=7]
    _bsc_low = [s for s in json.loads((Path(__file__).parent.parent/"data"/"feb_2026_staff_scores.json").read_text()).values()
                if s["final_score"]<2.5]
    n_crit = len(_fd_h) + len(_bsc_low)
    if n_crit > 0:
        st.markdown(
            f"<a href='/Smart_Alerts' style='text-decoration:none'>"
            f"<div style='background:#FEF2F2;border:1.5px solid #FECACA;border-radius:8px;"
            f"padding:8px 14px;margin-bottom:8px;display:flex;align-items:center;gap:10px'>"
            f"<span style='font-size:18px'>🔔</span>"
            f"<span style='font-size:13px;color:#991B1B;font-weight:600'>"
            f"{n_crit} critical alerts need attention — FD maturities, BSC drops</span>"
            f"<span style='margin-left:auto;font-size:11px;color:#DC2626'>View alerts →</span>"
            f"</div></a>", unsafe_allow_html=True)
except Exception: pass


# ── Calendar events widget ─────────────────────────────────────────
try:
    _cal_p = Path(__file__).parent.parent / "data" / "calendar_events.json"
    if _cal_p.exists():
        _cal_events = a2z_db.load_json(_cal_p) if hasattr(json,'loads') else []
        _upcoming   = [e for e in _cal_events
                       if e.get("date") and
                       0 <= (date.fromisoformat(e["date"][:10]) - date.today()).days <= 14]
        if _upcoming:
            st.markdown("**📅 Upcoming events (14 days):**")
            for ev in sorted(_upcoming, key=lambda x:x["date"]):
                days = (date.fromisoformat(ev["date"][:10])-date.today()).days
                when = "Today" if days==0 else f"In {days}d ({ev['date'][:10]})"
                _type_c = {"Regulatory":"#DC2626","Performance":"#3B82F6",
                            "Governance":"#7C3AED","Training":"#16A34A"}.get(ev.get("type",""),"#6B7280")
                st.markdown(
                    f"<div style='border-left:3px solid {_type_c};padding:2px 8px;margin:2px;"
                    f"background:{_type_c}08;border-radius:0 4px 4px 0'>"
                    f"<span style='font-size:11px;font-weight:600;color:{_type_c}'>{ev.get('type','')}</span>"
                    f" — {ev['title']} <span style='color:var(--color-text-tertiary);font-size:10px'>({when})</span>"
                    f"</div>", unsafe_allow_html=True)
except Exception: pass

# ── Quick action cards ───────────────────────────────────────────────
_role_l = _raw_role.lower()
_qa_items = []
if any(x in _role_l for x in ('relationship','business banker','rm')):
    _qa_items += [('📊 New Pipeline Deal',     'pipeline',    '#2563EB'),
                  ('📋 New Loan Application',   'loan_applications', '#7C3AED'),
                  ('📥 New FD Request',         'treasury',    '#0891B2')]
elif any(x in _role_l for x in ('branch manager','branch operations')):
    _qa_items += [('📊 Branch Pipeline',        'pipeline',    '#2563EB'),
                  ('👥 Team Scorecard',          'perform',     '#16A34A'),
                  ('📋 Loan Queue',             'loan_applications','#7C3AED'),
                  ('📝 Branch Daily Log',       'branch_log',  '#D97706')]
elif any(x in _role_l for x in ('credit analyst','credit analysis','chief credit')):
    _qa_items += [('🏦 Credit Queue',           'credit_analysis',  '#0891B2'),
                  ('📋 All Applications',       'loan_applications','#7C3AED'),
                  ('📑 Credit Admin',           'credit_admin', '#6D28D9')]
elif any(x in _role_l for x in ('legal','company secretary','paralegal')):
    _qa_items += [('⚖️ Open Matters',           'legal',        '#1D4ED8'),
                  ('🗂️ Custody Register',       'legal',        '#065F46')]
elif any(x in _role_l for x in ('compliance','aml','risk')):
    _qa_items += [('🛡️ Open Cases',             'compliance',   '#DC2626'),
                  ('📊 Risk Dashboard',         'perform',      '#7C3AED')]
elif any(x in _role_l for x in ('treasury','dealer','cfo','chief finance')):
    _qa_items += [('💹 FD Ratification Queue',  'treasury',     '#0891B2'),
                  ('📈 Rate Analytics',         'treasury',     '#16A34A')]
else:
    _qa_items += [('🏆 My Scorecard',           'perform',      '#16A34A'),
                  ('🎯 My Targets',             'cascade',      '#2563EB')]

if _qa_items:
    _qc = st.columns(len(_qa_items))
    for _qcol, (_qlbl, _qmod, _qclr) in zip(_qc, _qa_items):
        _qcol.markdown(
            f"<a href='/{_qmod.replace('_',' ').title()}' style='text-decoration:none'>"
            f"<div style='background:{_qclr}12;border:1.5px solid {_qclr}40;"
            f"border-radius:10px;padding:12px 10px;text-align:center;cursor:pointer'>"
            f"<div style='font-size:20px'>{_qlbl.split(' ')[0]}</div>"
            f"<div style='font-size:11px;font-weight:600;color:{_qclr};margin-top:4px'>"
            f"{' '.join(_qlbl.split(' ')[1:])}</div>"
            f"</div></a>",
            unsafe_allow_html=True)
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

# ── Module tiles — only show accessible modules ───────────────────────
# Module tiles: (module_key, icon, title, tagline, unlock_description, colour)
# Module groupings for home page
MODULE_GROUPS = {
    "🏆 A2Z Perform": ["perform","cascade","products","optimize","branch_log"],
    "⚡ A2Z Execute": ["execute","pipeline","sla","campaigns","cims","commission"],
    "🔗 A2Z Integrate": ["integrate","competitor","sbu","opex","people","export"],
    "⚙️ Admin": ["admin"],
}

MODULE_TILES = [
    ("perform", "🏆", "Perform",
     "Your BSC scorecard — live, ranked, actionable",
     "Unlocks your personal KPI scorecard with target vs actual tracking across "
     "Financial, Customer and Operational pillars. View rankings across your team, "
     "drill into individual performance, validate scores, and track monthly trends. "
     "Scores only activate after targets are confirmed via cascade.",
     "var(--brand-primary,#006B3F)"),

    ("cascade", "🎯", "Target Cascade",
     "Where targets flow — from bank to individual",
     "The MD sets bank-level targets. Directors, Heads and Managers cascade them "
     "downward through the organisation. Each person reviews, requests changes if "
     "needed, then accepts and locks their targets — activating their BSC tracking. "
     "Deadlines and coverage are monitored at every level.",
     "#185FA5"),

    ("pipeline", "💼", "Pipeline",
     "Your revenue engine — deals from lead to close",
     "A full CRM deal board tracking every opportunity through Lead → Qualified → "
     "Proposal → Negotiation → Closed Won. Log activities, set next actions, "
     "forecast revenue with probability weighting, and view your team's conversion "
     "rates and at-risk deals. Managers see consolidated team analytics.",
     "var(--brand-mid,#1D9E75)"),

    ("people", "👥", "People",
     "Staff lifecycle — from onboarding to exit",
     "Manage leave requests and approvals, disciplinary cases, PIPs, transfers and "
     "separations. HR and line managers can track leave balances, record conduct "
     "matters with full audit trails, and monitor staff welfare indicators. "
     "Leave entitlements are configured by Admin to match company policy.",
     "#8E44AD"),

    ("execute", "⚡", "Execute",
     "Strategic initiatives — milestones, gates, accountability",
     "Tracks every strategic project from initiation to delivery. Workstream leads "
     "update milestones, Finance approvers sign off on budgets, and Sponsors review "
     "gate progression. Links directly to Diligence and Initiative KPI scores in "
     "the BSC — execution drives performance measurement.",
     "#E67E22"),

    ("cims", "📨", "CIMS",
     "Compliance instructions — tracked, actioned, closed",
     "Raise and receive compliance instructions, regulatory notices and internal "
     "directives. Auto-assignment routes tickets to the right team. Staff action "
     "instructions within SLA, upload supporting documents, and escalate where "
     "needed. Full audit trail for regulatory examination.",
     "#E24B4A"),

    ("sla", "📋", "SLA Tracker",
     "Service levels — measured, monitored, enforced",
     "Tracks adherence to internal SLAs across branches and departments. View "
     "violation heatmaps, identify repeat offenders, and monitor improvement trends. "
     "SLA scores feed directly into the Operational Excellence pillar of each "
     "staff member's BSC scorecard.",
     "#F5A623"),

    ("branch_log", "📝", "Branch Daily Log",
     "Daily branch operations — capture, verify, track",
     "Branch staff log daily transactions, digital migration numbers, acquiring "
     "volumes and cash reconciliations. Supervisors review and validate entries. "
     "Logged data auto-populates Transactions, Digital Acquiring and CX KPIs "
     "in the BSC — eliminating manual spreadsheet reporting.",
     "#2980B9"),

    ("commission", "💰", "Commission",
     "Incentive earnings — transparent, real-time, fair",
     "Calculates commission and incentive earnings based on actual sales performance "
     "against targets. Staff see their running total; managers see team payout "
     "projections by product line. Connects to pipeline closure data for accuracy.",
     "#27AE60"),

    ("campaigns", "🚀", "Campaigns",
     "Sales campaigns — planned, tracked, measured",
     "Create and track branch and product campaigns. Monitor conversion rates, "
     "customer acquisition per campaign, and ROI. Campaign performance feeds into "
     "the Campaign Conversion Rate KPI in staff scorecards.",
     "#C0392B"),

    ("sbu", "🏦", "SBU Performance",
     "Business unit intelligence — contribution and growth",
     "Deep-dive into business unit performance: deposit growth, loan book, "
     "fee income and PBT contribution. Compare branches, regions and segments. "
     "Directors and Heads use this to identify outliers and benchmark performance "
     "across the retail and commercial networks.",
     "#6C3483"),

    ("opex", "📉", "Operating Leverage",
     "Cost efficiency — where every shilling goes",
     "Tracks the Cost-to-Income Ratio and operating leverage across units. "
     "Identifies cost centres, flags budget overruns and highlights efficiency "
     "gains. Finance and Directors use this alongside PBT data to manage "
     "the bank's cost discipline.",
     "#1A252F"),

    ("integrate", "🔗", "Integrate",
     "The executive view — performance meets strategy meets market",
     "Synthesises data across Perform, Execute, Pipeline and external market "
     "intelligence into a single executive dashboard. Identifies convergence "
     "patterns, strategic gaps and competitive positioning. The MD and Directors "
     "use this for objective, data-driven decisioning.",
     "var(--brand-primary,#006B3F)"),

    ("admin", "⚙️", "Admin",
     "System control — users, access, structure, audit",
     "Create and manage user accounts with role-based access. Configure which "
     "modules and pages each person can access. Set up reporting lines, remap "
     "managers, configure leave entitlements and review the full system audit log. "
     "All access changes take effect immediately.",
     "#374151"),

    ("export", "📥", "Export",
     "Data out — reports, summaries, raw downloads",
     "Export BSC scorecards, KPI data, pipeline reports and HR records to Excel. "
     "Schedule periodic exports for board packs or regulatory submissions. "
     "All exports respect your access permissions — you only download data "
     "within your authorised scope.",
     "#4B5563"),
]

accessible = [(m,i,t,tl,ul,c) for m,i,t,tl,ul,c in MODULE_TILES
              if check_access(ud, m)[0]]

if accessible:
    st.markdown(
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"margin-bottom:12px'>"
        f"<div style='font-size:13px;font-weight:700;color:var(--color-text-primary)'>"
        f"Your modules</div>"
        f"<div style='font-size:11px;color:var(--color-text-tertiary)'>"
        f"{len(accessible)} module(s) accessible</div>"
        f"</div>",
        unsafe_allow_html=True)

    _PAGE_FILES = {
        "perform":"pages/1_perform.py","people":"pages/2_people.py",
        "pipeline":"pages/3_pipeline.py","execute":"pages/4_execute.py",
        "products":"pages/5_products.py","integrate":"pages/6_integrate.py",
        "admin":"pages/7_admin.py","export":"pages/8_export.py",
        "sbu":"pages/9_sbu.py","opex":"pages/10_opex.py",
        "competitor":"pages/11_competitor.py","cascade":"pages/12_cascade.py",
        "sla":"pages/13_sla.py","branch_log":"pages/14_branch_log.py",
        "optimize":"pages/15_optimize.py","commission":"pages/16_commission.py",
        "campaigns":"pages/17_campaigns.py","cims":"pages/18_cims.py",
    }

    # Render tiles grouped by module category
    for group_name, group_mods in MODULE_GROUPS.items():
        group_tiles = [(m,i,t,tl,ul,c) for m,i,t,tl,ul,c in accessible
                       if m in group_mods]
        if not group_tiles: continue
        _gh_clr = {"🏆 A2Z Perform":"var(--brand-primary,#006B3F)","⚡ A2Z Execute":"#185FA5",
                    "🔗 A2Z Integrate":"#6B21A8","⚙️ Admin":"#374151"}.get(group_name,"#374151")
        st.markdown(
            f"<div style='display:flex;align-items:center;gap:8px;"
            f"margin:20px 0 8px;padding-bottom:6px;"
            f"border-bottom:2px solid {_gh_clr}20'>"
            f"<div style='width:3px;height:16px;background:{_gh_clr};border-radius:2px'></div>"
            f"<div style='font-size:12px;font-weight:700;color:{_gh_clr};"
            f"text-transform:uppercase;letter-spacing:0.8px'>{group_name}</div>"
            f"</div>",
            unsafe_allow_html=True)
        rows = [group_tiles[i:i+3] for i in range(0, len(group_tiles), 3)]
        for row in rows:
            cols = st.columns(3)
            for col, (mod, icon, title, tagline, unlock, colour) in zip(cols, row):
                with col:
                    # Live stat for this tile
                    _stat = ""
                    try:
                        if mod == "cascade" and casc:
                            _my_sc2 = str(ud.get("staff_code","") or uname)
                            _given2 = casc.get_what_i_was_given(_my_sc2,_gfy(),_raw_name)
                            _locked2 = casc.targets_locked(_my_sc2,_gfy())
                            _stat = "🔒 Locked" if _locked2 else (f"⏳ {len(_given2)} KPI(s) pending" if _given2 else "⚠️ Not cascaded")
                        elif mod == "pipeline" and pm:
                            _my_deals2 = pm.get_deals(staff_code=str(ud.get("staff_code","") or uname))
                            _active2 = [d for d in _my_deals2 if d["stage"] not in ("Closed Won","Closed Lost")]
                            _stat = f"{len(_active2)} active deal(s)"
                        elif mod == "people" and lm:
                            _pending_lv = [l for l in lm.get_all_leaves()
                                           if l.get("approved") is None]
                            _stat = f"{len(_pending_lv)} leave request(s) pending" if _pending_lv else ""
                        elif mod == "perform" and len(staff_scores):
                            _my_row2 = staff_scores[staff_scores["Staff Name"]==_raw_name]
                            if len(_my_row2):
                                _sc2 = float(_my_row2.iloc[0].get("Final_BSC_Score",0))
                                _stat = f"BSC: {_sc2:.2f} / 5.0"
                    except: pass

                    _stat_html = (f"<div style='margin-top:8px;padding:3px 8px;"
                                  f"background:{colour}15;border-radius:10px;"
                                  f"font-size:10px;font-weight:600;color:{colour};"
                                  f"display:inline-block'>{_stat}</div>"
                                  if _stat else "")
                    st.markdown(
                        f"<div style='padding:14px 16px;background:var(--color-background-primary);"
                        f"border:0.5px solid var(--color-border-tertiary);border-left:4px solid {colour};"
                        f"border-radius:10px;margin-bottom:4px;"
                        f"transition:box-shadow 0.15s'>"
                        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px'>"
                        f"<span style='font-size:20px'>{icon}</span>"
                        f"<div>"
                        f"<div style='font-weight:700;color:var(--color-text-primary);font-size:13px'>{title}</div>"
                        f"<div style='color:{colour};font-size:10px;font-weight:600'>{tagline}</div>"
                        f"</div></div>"
                        f"<div style='color:var(--color-text-secondary);font-size:10px;line-height:1.5'>{unlock[:120]}...</div>"
                        f"{_stat_html}"
                        f"</div>",
                        unsafe_allow_html=True)
                    pf = _PAGE_FILES.get(mod)
                    if pf:
                        try:
                            st.page_link(pf, label=f"Open {title} →",
                                         use_container_width=True)
                        except Exception:
                            pass

# ── Recent activity & notices ─────────────────────────────────────────

# ── Branch league ranking ─────────────────────────────────────
try:
    import json as _json_h
    from pathlib import Path as _Path_h
    _scores_file = _Path_h("a2z/data/feb_2026_branch_scores.json")
    _org_cfg     = _Path_h("a2z/data/org_config.json")
    if _scores_file.exists() and _org_cfg.exists():
        _bscores = _json_h.loads(_scores_file.read_text())
        _org_h   = _json_h.loads(_org_cfg.read_text())
        _bname_h = st.session_state.get("_bank_display", "A2Z Blueprint")

        st.markdown("---")
        st.markdown(
            f"<div style='font-size:14px;font-weight:700;color:var(--color-text-primary);margin-bottom:8px'>"
            f"🏆 Branch Peer League — Feb 2026</div>",
            unsafe_allow_html=True)

        # Group by league
        _leagues = {"Premier":[],"Large":[],"Medium":[],"New":[]}
        for _bname_k, _bdata in _bscores.items():
            _lg = _bdata.get("league","Medium")
            _leagues.setdefault(_lg,[]).append({
                "branch": _bname_k.title().replace(" Branch","").replace("Fbt","FBT"),
                "rank": _bdata.get("rank",0),
                "pbt": _bdata.get("pbt_achievement",0),
            })

        _lc = {"Premier":"var(--brand-primary,#006B3F)","Large":"#185FA5","Medium":"#7C3AED","New":"#D97706"}
        _league_cols = st.columns(min(4, len([l for l in _leagues if _leagues[l]])))
        _ci = 0
        for _lg_name, _members in _leagues.items():
            if not _members: continue
            _members_sorted = sorted(_members, key=lambda x: x["rank"] or 999)
            _col = _league_cols[_ci % len(_league_cols)]
            _clr = _lc.get(_lg_name,"#6B7280")
            _html = (
                f"<div style='border:1px solid {_clr}30;border-radius:8px;overflow:hidden'>"
                f"<div style='background:{_clr};color:var(--color-background-primary);padding:6px 10px;"
                f"font-size:11px;font-weight:700'>{_lg_name} League ({len(_members)})</div>"
                f"<div style='padding:6px 8px;max-height:200px;overflow-y:auto'>")
            for _m in _members_sorted[:10]:
                _pbt_pct = _m["pbt"] * 100
                _pbt_c   = "var(--brand-primary,#006B3F)" if _pbt_pct >= 91 else "#F5A623" if _pbt_pct >= 61 else "#E24B4A"
                _html += (
                    f"<div style='display:flex;justify-content:space-between;"
                    f"font-size:10px;padding:2px 0;border-bottom:0.5px solid var(--color-border-tertiary)'>"
                    f"<span style='color:var(--color-text-primary)'>#{_m['rank']} {_m['branch'][:22]}</span>"
                    f"<span style='color:{_pbt_c};font-weight:600'>{_pbt_pct:.0f}%</span>"
                    f"</div>")
            if len(_members) > 10:
                _html += f"<div style='font-size:9px;color:var(--color-text-tertiary);padding:3px'>+{len(_members)-10} more</div>"
            _html += "</div></div>"
            _col.markdown(_html, unsafe_allow_html=True)
            _ci += 1
except Exception as _he:
    pass  # silent fail — data may not be available

st.markdown("---")
n1, n2 = st.columns(2)

with n1:
    st.markdown("#### 📌 Notices")
    notices = []

    # Cascade pending
    if casc:
        try:
            my_sc  = str(ud.get("staff_code","") or uname)
            given  = casc.get_what_i_was_given(my_sc, _gfy(), _raw_name)
            locked = casc.targets_locked(my_sc, _gfy())
            if given and not locked:
                notices.append(("🎯","You have cascaded targets awaiting your acceptance",
                                 "Target Cascade → My targets","#F5A623"))
            elif not given:
                notices.append(("⏳","Your targets have not yet been cascaded to you",
                                 "Follow up with your line manager","#9CA3AF"))
        except: pass

    # At-risk pipeline deals
    try:
        from datetime import timedelta
        my_deals  = pm.get_deals(staff_code=str(ud.get("staff_code","") or uname))
        at_risk   = [d for d in my_deals
                     if d.get("stage","") not in ("Closed Won","Closed Lost")
                     and (datetime.now()-datetime.fromisoformat(
                         d.get("updated_at",datetime.now().isoformat()))).days > 14]
        if at_risk:
            notices.append(("⚠️",f"{len(at_risk)} pipeline deal(s) with no update in 14+ days",
                             "Pipeline → Deal board","#E24B4A"))
    except: pass

    if not notices:
        notices.append(("✅","All clear — no pending actions","","var(--brand-primary,#006B3F)"))

    for icon, msg, link, colour in notices:
        st.markdown(
            f"<div style='padding:10px 14px;background:{colour}12;"
            f"border-left:3px solid {colour};border-radius:0 8px 8px 0;margin-bottom:6px;"
            f"font-size:12px'>"
            f"<b style='color:{colour}'>{icon} {msg}</b>"
            + (f"<br><span style='color:var(--color-text-tertiary)'>{link}</span>" if link else "") +
            f"</div>", unsafe_allow_html=True)

with n2:
    st.markdown("#### 🏦 Platform pillars")
    pillars = [
        ("📊","Perform","BSC-driven performance tracking from individual KPIs to bank-wide scorecard"),
        ("⚡","Execute","Strategic initiative management with milestones, gates and finance controls"),
        ("🔗","Integrate","Cross-functional analytics bridging performance, pipeline and market intelligence"),
    ]
    for icon, title, desc in pillars:
        st.markdown(
            f"<div style='padding:12px 14px;background:var(--color-background-secondary);border-radius:8px;"
            f"margin-bottom:6px;font-size:12px'>"
            f"<b>{icon} {title}</b><br>"
            f"<span style='color:var(--color-text-secondary)'>{desc}</span></div>",
            unsafe_allow_html=True)

    # System tagline
    st.markdown(
        "<div style='padding:12px 14px;background:linear-gradient(135deg,#004A2B,var(--brand-primary,#006B3F);"
        "border-radius:8px;margin-top:8px;font-size:11px;color:rgba(255,255,255,0.7);"
        "font-style:italic;line-height:1.6'>"
        "Convergence · Analytics · Insights · Decisioning<br>"
        "<span style='color:#F5A623;font-weight:700'>A2Z Blueprint</span> — "
        "Perform · Execute · Integrate</div>",
        unsafe_allow_html=True)
