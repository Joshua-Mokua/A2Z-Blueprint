"""pages/24_compliance.py — Compliance Management: PEP, AML, KYC, sanctions."""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from pages._shared import load_shared_state, get_user_proposition
from pages._access import require_access
from utils.core import ComplianceManager, audit_log

require_access("compliance")

DATA = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()

@st.cache_data(ttl=60, show_spinner=False)
def _load():
    f = DATA / "compliance_cases.json"
    return json.loads(f.read_text()) if f.exists() else []

cases = _load()
role = ud.get("role",""); sc = str(ud.get("staff_code","") or "")
is_admin   = ud.get("is_admin",False)
is_comp    = any(x in role for x in ("Compliance","AML","Legal","Risk","Chief"))
is_mgr     = any(x in role for x in ("Manager","Director","Head"))
cmgr = ComplianceManager()

visible = cases if (is_admin or is_comp or is_mgr) else [
    c for c in cases if str(c.get("raised_by","")) == ud.get("full_name","")]

# ── Proposition head filter ─────────────────────────────
_prop_tag_pg = get_user_proposition()
if _prop_tag_pg:
    visible = [x for x in visible if x.get("proposition_tag") == _prop_tag_pg]
    try:
        import json as _pfj; from pathlib import Path as _pfp
        _pc2 = _pfj.loads((_pfp(__file__).parent.parent / "data" / "proposition_config.json").read_text())
        _pn  = _pc2.get("propositions",{}).get(_prop_tag_pg,{}).get("name",_prop_tag_pg)
        _pi  = _pc2.get("propositions",{}).get(_prop_tag_pg,{}).get("icon","🎯")
        st.info(_pi + " **" + _pn + " view** — " + str(len(visible)) + " tagged records")
    except Exception: pass


# ── Header ─────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>🛡️ Compliance</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "PEP screening · AML/KYC · Sanctions · Regulatory approvals</span></div>",
    unsafe_allow_html=True)

# ── KPI strip ──────────────────────────────────────────────────────
total    = len(visible)
open_n   = sum(1 for c in visible if c["status"] == "open")
review_n = sum(1 for c in visible if c["status"] == "under_review")
cleared  = sum(1 for c in visible if c["status"] == "cleared")
escalated= sum(1 for c in visible if c["status"] == "escalated")
critical = sum(1 for c in visible if c.get("risk_level") == "Critical")

k1,k2,k3,k4,k5 = st.columns(5)
for col, lbl, val, color in [
    (k1,"Open",      str(open_n),   "#DC2626"),
    (k2,"Under Review",str(review_n),"#D97706"),
    (k3,"Cleared",   str(cleared),  "#16A34A"),
    (k4,"Escalated", str(escalated),"#7C3AED"),
    (k5,"Critical",  str(critical), "#991B1B"),
]:
    col.markdown(
        f"<div style='background:var(--color-background-secondary);border:0.5px solid "
        f"var(--color-border-tertiary);border-radius:10px;padding:12px;text-align:center'>"
        f"<div style='font-size:11px;color:var(--color-text-secondary);font-weight:600;"
        f"text-transform:uppercase'>{lbl}</div>"
        f"<div style='font-size:24px;font-weight:800;color:{color}'>{val}</div>"
        f"</div>", unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

RISK_COLOR = {"Low":"#16A34A","Medium":"#D97706","High":"#DC2626","Critical":"#7F1D1D"}
STATUS_COLOR = {
    "open":"#DC2626","under_review":"#D97706","cleared":"#16A34A",
    "escalated":"#7C3AED","rejected":"#6B7280",
}
FLAG_ICON = {
    "PEP":"👤","Sanctioned Entity":"🚫","Adverse Media":"📰",
    "Restricted Sector":"🏭","AML Flag":"💰","Unusual Transaction":"⚠️",
}

tabs = st.tabs(["📋 All Cases","🔴 Open","✅ Cleared","📊 Analytics",
    "📅 Regulatory Calendar"
])

# ────────────────────────────────────────────────────────────────────
# TAB 1: ALL
# ────────────────────────────────────────────────────────────────────
with tabs[0]:
    f1,f2,f3 = st.columns(3)
    filt_st   = f1.selectbox("Status",["All","open","under_review","cleared","escalated","rejected"], key="cs_st")
    filt_risk = f2.selectbox("Risk level",["All","Critical","High","Medium","Low"], key="cs_risk")
    filt_flag = f3.selectbox("Flag type",["All"]+sorted(set(c["flag_type"] for c in visible)), key="cs_flag")

    filt = visible
    if filt_st   != "All": filt = [c for c in filt if c["status"] == filt_st]
    if filt_risk != "All": filt = [c for c in filt if c.get("risk_level") == filt_risk]
    if filt_flag != "All": filt = [c for c in filt if c["flag_type"] == filt_flag]

    for case in sorted(filt, key=lambda x: (x["status"]!="open", x.get("risk_level",""))):
        rc  = RISK_COLOR.get(case.get("risk_level","Low"),"#6B7280")
        sc2 = STATUS_COLOR.get(case["status"],"#6B7280")
        icon= FLAG_ICON.get(case["flag_type"],"⚠️")
        _d2sla = case.get("_days_to_sla", 99)
        _sla_txt = f"🔴 {-_d2sla}d overdue" if _d2sla < 0 else f"🟡 Due in {_d2sla}d" if _d2sla <= 2 else f"🟢 {_d2sla}d"
        with st.expander(
            f"{icon} {case['client_name']} · "
            f"**{case['flag_type']}** · "
            f"{case['status'].replace('_',' ').title()} · "
            f"{case.get('risk_level','')} risk  ·  {_sla_txt}",
            expanded=(case["status"]=="open" and case.get("risk_level")=="Critical")):
            c1,c2,c3,c4 = st.columns(4)
            c1.markdown(f"**Case:** `{case['id']}`")
            c2.markdown(f"**Source:** {case['source'].replace('_',' ').title()}")
            c3.markdown(f"**Raised:** {case['raised_date']}")
            c4.markdown(f"**Officer:** {case.get('assigned_officer','Unassigned')}")
            if case.get("source_ref"):
                st.markdown(f"**Reference:** `{case['source_ref']}`")
            if case.get("escalated_to"):
                st.warning(f"Escalated to: **{case['escalated_to']}**")
            # Documents required
            docs = case.get("documents_required",[])
            if docs:
                st.markdown(f"**Documents required:** {', '.join(docs)}")
            # Action buttons
            if (is_comp or is_admin) and case["status"] in ("open","under_review"):
                b1,b2,b3 = st.columns(3)
                if b1.button("✅ Clear case", key=f"clr_{case['id']}", type="primary"):
                    cmgr.update_status(case['id'], "cleared", ud.get('full_name', uname))
                    audit_log("COMPLIANCE_CLEARED", uname, f"{case['id']}|{case['client_name']}")
                    st.cache_data.clear(); st.success(f"Case {case['id']} cleared"); st.rerun()
                if b2.button("🔺 Escalate",  key=f"esc_{case['id']}"):
                    cmgr.update_status(case['id'], "escalated",
                                       escalate_to="Head of Compliance")
                    audit_log("COMPLIANCE_ESCALATED", uname, f"{case['id']}|{case['client_name']}")
                    st.cache_data.clear(); st.warning(f"Case {case['id']} escalated"); st.rerun()
                if b3.button("📝 Add note",  key=f"note_{case['id']}"):
                    st.info("Note saved")

# ────────────────────────────────────────────────────────────────────
# TAB 2: OPEN
# ────────────────────────────────────────────────────────────────────
with tabs[1]:
    open_cases = sorted(
        [c for c in visible if c["status"] in ("open","under_review")],
        key=lambda x: ["Critical","High","Medium","Low"].index(x.get("risk_level","Low")))
    if not open_cases:
        st.success("✅ No open compliance cases.")
    else:
        st.error(f"⚠️ {len(open_cases)} open cases require action")
        rows = []
        for c in open_cases:
            rows.append({
                "ID": c["id"], "Client": c["client_name"][:28],
                "Flag": c["flag_type"], "Risk": c.get("risk_level",""),
                "Source": c["source"].replace("_"," ").title(),
                "Status": c["status"].replace("_"," ").title(),
                "Raised": c["raised_date"],
                "Officer": c.get("assigned_officer","—"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────
# TAB 3: CLEARED
# ────────────────────────────────────────────────────────────────────
with tabs[2]:
    cleared_cases = [c for c in visible if c["status"] == "cleared"]
    st.markdown(f"**{len(cleared_cases)} cleared cases**")
    if cleared_cases:
        rows = [{"ID": c["id"],"Client": c["client_name"][:28],
                 "Flag": c["flag_type"],"Risk": c.get("risk_level",""),
                 "Cleared Date": c.get("cleared_date","—")}
                for c in cleared_cases]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────
# TAB 4: ANALYTICS
# ────────────────────────────────────────────────────────────────────
with tabs[3]:
    from collections import Counter
    from datetime import date as _dt2, timedelta as _td
    _sla_days_map = {"Critical":1,"High":3,"Medium":7,"Low":14}
    # Mark SLA status on each case
    for _c in visible:
        _rl  = _c.get("risk_level","Low")
        _sla = _sla_days_map.get(_rl, 7)
        try:
            _raised = _dt2.fromisoformat(_c.get("raised_date", str(_dt2.today())))
            _due    = _raised + _td(days=_sla)
            _c["_days_to_sla"] = (_due - _dt2.today()).days
            _c["_sla_breached"] = _c["_days_to_sla"] < 0 and _c["status"] not in ("cleared","rejected")
        except: _c["_days_to_sla"] = 99; _c["_sla_breached"] = False

    _breached = sum(1 for c in visible if c.get("_sla_breached"))
    if _breached:
        st.error(f"🔴 {_breached} compliance case(s) have breached their SLA deadline — immediate action required")

    from collections import Counter
    if visible:
        total = len(visible)
        cleared_pct = (sum(1 for c in visible if c["status"]=="cleared")/total*100) if total else 0.0
        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Total Cases",    total)
        m2.metric("Clearance Rate", f"{cleared_pct:.1f}%")
        m3.metric("Critical Open",
                  sum(1 for c in visible if c["status"]=="open" and c.get("risk_level")=="Critical"))
        m4.metric("SLA Breached", str(_breached), delta_color="inverse")

        # By flag type
        flag_counts = Counter(c["flag_type"] for c in visible)
        st.markdown("**Cases by flag type:**")
        for flag, cnt in flag_counts.most_common():
            pct = cnt/total*100 if total else 0.0
            cleared_flag = sum(1 for c in visible
                               if c["flag_type"]==flag and c["status"]=="cleared")
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
                f"<div style='width:200px;font-size:12px'>{FLAG_ICON.get(flag,'⚠️')} {flag}</div>"
                f"<div style='flex:1;background:#F3F4F6;border-radius:4px;height:14px'>"
                f"<div style='width:{pct:.0f}%;background:#DC2626;height:100%;border-radius:4px'></div>"
                f"</div>"
                f"<div style='font-size:12px;width:50px'>{cnt} ({cleared_flag} cleared)</div>"
                f"</div>", unsafe_allow_html=True)

with tabs[-1]:
    import re as _re_rc, calendar as _cal_rc
    st.markdown("**Monthly CBK Regulatory Returns Calendar:**")
    _today_rc = date.today()
    _last_day  = _cal_rc.monthrange(_today_rc.year, _today_rc.month)[1]
    CBK_RETURNS = [
        {"Return":"CBK Return 1 — Balance Sheet",         "Due":10,"Cat":"Prudential"},
        {"Return":"CBK Return 2 — P&L Statement",         "Due":10,"Cat":"Prudential"},
        {"Return":"CBK Return 3 — Capital Adequacy",      "Due":10,"Cat":"Capital"},
        {"Return":"CBK Return 8 — Asset Quality / NPL",   "Due":10,"Cat":"Credit Risk"},
        {"Return":"CBK Return 14 — Reconciliation",       "Due":15,"Cat":"Operations"},
        {"Return":"IFRS 9 ECL Provision Report",          "Due":20,"Cat":"Accounting"},
        {"Return":"AML/CFT STR Monthly Summary",          "Due":15,"Cat":"Compliance"},
        {"Return":"Liquidity Report LCR/NSFR",            "Due":10,"Cat":"Liquidity"},
        {"Return":"Foreign Exchange Position Return",     "Due":10,"Cat":"Treasury"},
        {"Return":"Credit Reference Bureau Filing",       "Due":5, "Cat":"Credit"},
    ]
    import pandas as _pd_rc
    _rows_rc = []
    for r in CBK_RETURNS:
        due = _today_rc.replace(day=min(r["Due"],_last_day))
        days_rem = (due - _today_rc).days
        if days_rem < 0:   status = "✅ Submitted"
        elif days_rem == 0:status = "🔴 DUE TODAY"
        elif days_rem <= 3:status = f"🟡 Due in {days_rem}d"
        else:              status = f"⬜ {due.strftime('%d %b')}"
        _rows_rc.append({"Return":r["Return"],"Category":r["Cat"],"Due":due.strftime("%d %b"),"Status":status})
    st.dataframe(_pd_rc.DataFrame(_rows_rc),use_container_width=True,hide_index=True)
    urgent_rc=[r for r in _rows_rc if "🔴" in r["Status"] or "🟡" in r["Status"]]
    if urgent_rc: st.error(f"🔴 {len(urgent_rc)} return(s) due within 3 days — action immediately")
    st.caption("Integrate with CBK SDMS for automated submission confirmation in production.")
