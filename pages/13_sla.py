"""pages/13_sla.py — SLA Tracker: scoring CX based on SLA adherence."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state, get_user_proposition
from pages._access import require_access, get_my_scope
require_access("sla")


um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
registry     = st.session_state.get("staff_registry", pd.DataFrame())

# ── SLA DEFINITIONS ──────────────────────────────────────────────────
SLA_CATEGORIES = {
    "Account Opening": {
        "sla_hours": 24, "priority": "High",
        "description": "New account fully opened and customer notified",
        "owner_roles": ["Customer Service Officer","Branch Operations Manager","Branch Manager"],
        "color": "var(--brand-primary,#006B3F)",
    },
    "Loan Processing": {
        "sla_hours": 72, "priority": "Critical",
        "description": "Loan application reviewed and decision communicated",
        "owner_roles": ["Branch Credit Manager","Credit Analyst","Chief Credit Officer"],
        "color": "#E24B4A",
    },
    "Credit Approval TAT": {
        "sla_hours": 48, "priority": "Critical",
        "description": "Credit approved or declined from submission",
        "owner_roles": ["Credit Analyst","Branch Credit Manager","Chief Credit Officer"],
        "color": "#C0392B",
    },
    "Cheque Clearance": {
        "sla_hours": 48, "priority": "High",
        "description": "Cheque cleared and funds available to customer",
        "owner_roles": ["Teller","Branch Operations Manager"],
        "color": "#185FA5",
    },
    "Card Issuance": {
        "sla_hours": 72, "priority": "Medium",
        "description": "Debit/credit card issued and activated",
        "owner_roles": ["Customer Service Officer","Branch Operations Manager"],
        "color": "#8E44AD",
    },
    "Complaint Resolution": {
        "sla_hours": 24, "priority": "Critical",
        "description": "Customer complaint acknowledged and resolution communicated",
        "owner_roles": ["Customer Service Officer","Branch Manager","Branch Operations Manager"],
        "color": "#E67E22",
    },
    "Statement Request": {
        "sla_hours": 4, "priority": "Low",
        "description": "Account statement generated and sent",
        "owner_roles": ["Customer Service Officer","Teller"],
        "color": "#27AE60",
    },
    "Fund Transfer": {
        "sla_hours": 2, "priority": "High",
        "description": "Internal/RTGS/EFT transfer executed",
        "owner_roles": ["Teller","Branch Operations Manager"],
        "color": "#2980B9",
    },
    "DFS Registration": {
        "sla_hours": 1, "priority": "Medium",
        "description": "Mobile money / DFS account registered and activated",
        "owner_roles": ["Customer Service Officer","Direct Sales Officer","Teller"],
        "color": "#16A085",
    },
    "Dormancy Reactivation": {
        "sla_hours": 48, "priority": "Medium",
        "description": "Dormant account reactivated and customer notified",
        "owner_roles": ["Customer Service Officer","Relationship Officer Personal Banking"],
        "color": "#F39C12",
    },
    "Audit Query Response": {
        "sla_hours": 24, "priority": "Critical",
        "description": "Audit query responded to with evidence",
        "owner_roles": ["Branch Manager","Branch Operations Manager","All"],
        "color": "#7F8C8D",
    },
    "IT Incident Resolution": {
        "sla_hours": 4, "priority": "Critical",
        "description": "System incident resolved or escalated with workaround",
        "owner_roles": ["IT Support Officer","IT Manager"],
        "color": "#C0392B",
    },
    "HR Request Processing": {
        "sla_hours": 48, "priority": "Medium",
        "description": "Leave, payroll, or HR query processed",
        "owner_roles": ["HR Officer","HR Business Partner"],
        "color": "#9B59B6",
    },
    "Procurement Request": {
        "sla_hours": 72, "priority": "Medium",
        "description": "Purchase request processed and supplier engaged",
        "owner_roles": ["Procurement Officer","Procurement Manager"],
        "color": "#D35400",
    },
}

PRIORITY_COLORS = {"Critical":"#E24B4A","High":"#F5A623","Medium":"#185FA5","Low":"#7F8C8D"}

# ── MANAGER ───────────────────────────────────────────────────────────
class SLAManager:
    def __init__(self):
        self.file    = DATA_DIR / "sla_tickets.json"
        self.tickets = self._load()

    def _load(self):
        if not self.file.exists(): self.file.write_text("[]")
        try:
            raw = self.file.read_text()
            d = json.loads(raw) if raw.strip() else []
            return d if isinstance(d, list) else []
        except: return []

    def _save(self):
        self.file.write_text(json.dumps(self.tickets, indent=2, default=str))

    def log_ticket(self, data: dict) -> dict:
        ticket_id = f"SLA{len(self.tickets)+1:05d}"
        opened_dt = datetime.now()
        sla_cfg   = SLA_CATEGORIES.get(data.get("category",""), {})
        sla_hrs   = sla_cfg.get("sla_hours", 24)
        due_dt    = opened_dt + timedelta(hours=sla_hrs)
        rec = {
            "id":           ticket_id,
            "category":     data.get("category",""),
            "customer_name":data.get("customer_name",""),
            "account_no":   data.get("account_no",""),
            "unit":         data.get("unit",""),
            "staff_code":   str(data.get("staff_code","")),
            "staff_name":   data.get("staff_name",""),
            "description":  data.get("description",""),
            "priority":     sla_cfg.get("priority","Medium"),
            "sla_hours":    sla_hrs,
            "opened_at":    str(opened_dt),
            "due_at":       str(due_dt),
            "resolved_at":  None,
            "status":       "Open",
            "resolution":   "",
            "breached":     False,
            "logged_by":    data.get("logged_by",""),
        }
        self.tickets.append(rec)
        self._save()
        return rec

    def resolve(self, ticket_id: str, resolution: str, resolved_by: str):
        for t in self.tickets:
            if t["id"] == ticket_id:
                now = datetime.now()
                t["resolved_at"] = str(now)
                t["resolution"]  = resolution
                t["status"]      = "Resolved"
                try:
                    due = datetime.fromisoformat(t["due_at"])
                    t["breached"] = now > due
                except: t["breached"] = False
                t["resolved_by"] = resolved_by
                self._save()
                return t
        return None

    def get_open(self, unit=None):
        now = datetime.now()
        open_t = [t for t in self.tickets if t["status"]=="Open"]
        for t in open_t:
            try:
                due = datetime.fromisoformat(t["due_at"])
                t["_overdue"] = now > due
                t["_hours_remaining"] = round((due-now).total_seconds()/3600, 1)
            except:
                t["_overdue"] = False
                t["_hours_remaining"] = 0
        if unit and unit != "All":
            open_t = [t for t in open_t if t["unit"]==unit]
        return open_t

    def sla_score(self, unit=None, staff_code=None, days_back=30):
        cutoff = datetime.now() - timedelta(days=days_back)
        resolved = [t for t in self.tickets
                    if t["status"]=="Resolved" and t.get("resolved_at")]
        resolved = [t for t in resolved
                    if datetime.fromisoformat(t["resolved_at"][:19]) >= cutoff]
        if unit and unit!="All":
            resolved = [t for t in resolved if t["unit"]==unit]
        if staff_code:
            resolved = [t for t in resolved if t["staff_code"]==str(staff_code)]
        if not resolved:
            return 1.0, 0, 0
        total    = len(resolved)
        breached = sum(1 for t in resolved if t.get("breached"))
        score    = round((total-breached)/total, 4)
        return score, total, breached

    def get_all(self):
        return self.tickets

    def analytics(self):
        total     = len(self.tickets)
        resolved  = [t for t in self.tickets if t["status"]=="Resolved"]
        open_t    = [t for t in self.tickets if t["status"]=="Open"]
        breached  = [t for t in resolved if t.get("breached")]
        by_cat    = {}
        for t in self.tickets:
            c = t.get("category","Unknown")
            if c not in by_cat:
                by_cat[c] = {"total":0,"resolved":0,"breached":0}
            by_cat[c]["total"] += 1
            if t["status"]=="Resolved": by_cat[c]["resolved"] += 1
            if t.get("breached"):       by_cat[c]["breached"] += 1
        # Average resolution time
        res_times = []
        for t in resolved:
            try:
                o = datetime.fromisoformat(t["opened_at"][:19])
                r = datetime.fromisoformat(t["resolved_at"][:19])
                res_times.append((r-o).total_seconds()/3600)
            except: pass
        avg_res = round(sum(res_times)/len(res_times),1) if res_times else 0
        return {
            "total": total, "open": len(open_t),
            "resolved": len(resolved), "breached": len(breached),
            "sla_score": round((len(resolved)-len(breached))/max(len(resolved),1),4),
            "avg_resolution_hours": avg_res,
            "by_category": by_cat,
        }

# Initialise
if "sla_manager" not in st.session_state:
    st.session_state["sla_manager"] = SLAManager()
slm = st.session_state["sla_manager"]

# ── HEADER ───────────────────────────────────────────────────────────


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📋 SLA Tracker</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Service levels · TAT · Escalations</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📋 SLA Tracker</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Service levels · TAT · Escalations</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📋 SLA Tracker</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Customer service levels · TAT · Escalations</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📋 SLA Tracker</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Customer service levels · TAT · Escalations</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📋 SLA Tracker</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Customer service levels · TAT · Escalations</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📋 SLA Tracker</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Customer service levels · TAT · Escalations</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style=\'padding:16px 22px;background:#185FA5;border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)\'><div style=\'display:flex;align-items:center;justify-content:space-between\'><div><div style=\'color:var(--color-background-primary);font-size:16px;font-weight:700;letter-spacing:-0.2px\'>SLA Tracker</div><div style=\'color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px;font-weight:400\'>Service Level Agreement tracking · CX scoring · Breach alerts · Staff accountability</div></div><div style=\'opacity:0.12;font-size:36px;line-height:1;color:white\'>◆</div></div></div>",
    unsafe_allow_html=True)

tabs = st.tabs([
    "📊 Dashboard",
    "🎫 Log ticket",
    "✅ Resolve tickets",
    "👤 Staff SLA scores",
    "📈 Analytics",
    "⚙️ SLA definitions",
    "⚖️ LMS / Legal / Compliance",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    anl = slm.analytics()
    overall_score = anl["sla_score"]
    score_clr = 'var(--brand-primary,#006B3F)' if overall_score>=0.90 else ('#F5A623' if overall_score>=0.75 else '#E24B4A')

    c1,c2,c3,c4,c5,c6 = st.columns(6)
    c1.metric("Overall SLA score",  f"{overall_score:.1%}",
              help="Tickets resolved within SLA / total resolved")
    c2.metric("Total tickets",      anl["total"])
    c3.metric("Open",               anl["open"],
              delta=f"-{anl['open']}" if anl['open'] else "0", delta_color="inverse")
    c4.metric("Resolved",           anl["resolved"])
    c5.metric("Breached",           anl["breached"],
              delta=f"-{anl['breached']}" if anl['breached'] else "0", delta_color="inverse")
    c6.metric("Avg resolution",     f"{anl['avg_resolution_hours']}h")

    # SLA score gauge
    ga1, ga2 = st.columns(2)
    with ga1:
        fig_g = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=overall_score*100,
            delta={"reference":90,"suffix":"%"},
            title={"text":"SLA Adherence Score (%)"},
            gauge={
                "axis":{"range":[0,100]},
                "bar":{"color":score_clr},
                "steps":[
                    {"range":[0,75],"color":"#FDEDEC"},
                    {"range":[75,90],"color":"#FEF6E4"},
                    {"range":[90,100],"color":"var(--brand-light,#E8F5EE)"},
                ],
                "threshold":{"line":{"color":"var(--brand-primary,#006B3F)","width":3},"value":90},
            }
        ))
        fig_g.update_layout(height=240,
            paper_bgcolor='rgba(0,0,0,0)', margin=dict(l=20,r=20,t=40,b=20))
        st.plotly_chart(fig_g, use_container_width=True)

    with ga2:
        if anl["by_category"]:
            cat_rows = [{"Category":c[:20], "Total":v["total"],
                         "Breached":v["breached"],
                         "Score":f"{(v['resolved']-v['breached'])/max(v['resolved'],1):.0%}"}
                        for c,v in anl["by_category"].items()]
            cat_df = pd.DataFrame(cat_rows).sort_values("Breached", ascending=False)
            def hl_score(v):
                try:
                    p = float(str(v).replace('%',''))
                    if p >= 90: return 'color:var(--brand-primary,#006B3F);font-weight:500'
                    if p >= 75: return 'color:#F5A623'
                    return 'color:#E24B4A;font-weight:500'
                except: return ''
            st.markdown("**SLA by category**")
            st.dataframe(cat_df.style.map(hl_score, subset=['Score']),
                         use_container_width=True, hide_index=True, height=220)

    # Open tickets — overdue highlighted
    st.markdown("---")
    st.markdown("#### Open tickets")
    unit_filter = st.selectbox(
        "Filter by unit", ["All"] + sorted(set(t["unit"] for t in slm.tickets if t["unit"])),
        key="sla_unit_f")
    open_tickets = slm.get_open(unit_filter)

    if not open_tickets:
        st.success("No open SLA tickets.")
    else:
        overdue = [t for t in open_tickets if t.get("_overdue")]
        if overdue:
            st.error(f"⚠️ {len(overdue)} ticket(s) OVERDUE — immediate action required")

        for t in sorted(open_tickets, key=lambda x: x.get("_overdue",False), reverse=True)[:20]:
            overdue_flag = t.get("_overdue", False)
            hrs_rem      = t.get("_hours_remaining", 0)
            pri_clr      = PRIORITY_COLORS.get(t["priority"],"#888")
            border_clr   = "#E24B4A" if overdue_flag else pri_clr
            status_txt   = f"🔴 OVERDUE by {abs(hrs_rem):.1f}h" if overdue_flag else f"⏱ {hrs_rem:.1f}h remaining"

            st.markdown(
                f"<div style='padding:8px 12px;background:var(--color-background-secondary);"
                f"border-left:4px solid {border_clr};"
                f"border-radius:0 6px 6px 0;margin:3px 0;font-size:12px'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<span><b>{t['id']}</b> · {t['category']} "
                f"<span style='background:{pri_clr};color:var(--color-background-primary);padding:1px 5px;"
                f"border-radius:8px;font-size:10px'>{t['priority']}</span></span>"
                f"<span style='color:{border_clr};font-weight:500'>{status_txt}</span></div>"
                f"<div style='color:#666;margin-top:2px'>"
                f"{t['customer_name']} · {t['unit']} · {t['staff_name']} · "
                f"Opened: {t['opened_at'][:16]}</div>"
                f"<div style='color:#888;font-size:11px'>{t['description'][:80]}</div>"
                f"</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TAB 2 — LOG TICKET
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Log new SLA ticket")

    all_units = sorted(set(
        staff_scores["Unit"].tolist() if len(staff_scores) else []
    ) or ["Head Office"])

    with st.form("sla_log_form"):
        lc1, lc2 = st.columns(2)
        sla_cat   = lc1.selectbox("Service category *", list(SLA_CATEGORIES.keys()))
        sla_unit  = lc2.selectbox("Branch / unit *", all_units)

        cfg = SLA_CATEGORIES[sla_cat]
        st.markdown(
            f"<div style='padding:6px 10px;background:#EBF0F7;"
            f"border-left:3px solid #185FA5;font-size:11px'>"
            f"SLA: <b>{cfg['sla_hours']} hours</b> · Priority: <b>{cfg['priority']}</b> · "
            f"{cfg['description']}</div>", unsafe_allow_html=True)

        lc3, lc4 = st.columns(2)
        cust_name = lc3.text_input("Customer name")
        acct_no   = lc4.text_input("Account number")

        # Staff selector
        unit_staff = staff_scores[staff_scores["Unit"]==sla_unit] if len(staff_scores) else pd.DataFrame()
        staff_opts = {f"{r['Staff Name']} ({r['Role']})": str(r["Staff Code"])
                      for _, r in unit_staff.iterrows()} if len(unit_staff) else {"Manual entry": ""}
        sla_staff_lbl = st.selectbox("Assigned to *", list(staff_opts.keys()))
        sla_staff_code= staff_opts[sla_staff_lbl]
        sla_desc      = st.text_area("Description / details *", height=70)

        if st.form_submit_button("Log ticket", type="primary"):
            if sla_cat and sla_unit and sla_desc:
                t = slm.log_ticket({
                    "category":     sla_cat,
                    "unit":         sla_unit,
                    "staff_code":   sla_staff_code,
                    "staff_name":   sla_staff_lbl.split('(')[0].strip(),
                    "customer_name":cust_name,
                    "account_no":   acct_no,
                    "description":  sla_desc,
                    "logged_by":    uname,
                })
                audit_log("SLA_TICKET_LOGGED", uname, f"{t['id']}:{sla_cat}:{sla_unit}")
                due_str = datetime.fromisoformat(t["due_at"][:19]).strftime("%d %b %Y %H:%M")
                st.success(f"✅ Ticket **{t['id']}** logged. Due by: **{due_str}**")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Category, unit and description are required.")

# ════════════════════════════════════════════════════════════════
# TAB 3 — RESOLVE
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Resolve open tickets")
    open_t = slm.get_open()

    if not open_t:
        st.success("No open tickets to resolve.")
    else:
        def _ticket_label(t):
            rem = t.get('_hours_remaining', 0)
            status = '🔴 OVERDUE' if t.get('_overdue') else f'{rem:.1f}h left'
            return f"{t['id']} — {t['category']} | {t['unit']} | {status}"
        ticket_opts = {_ticket_label(t): t['id'] for t in open_t}
        sel_ticket_lbl = st.selectbox("Select ticket to resolve", list(ticket_opts.keys()))
        sel_id         = ticket_opts[sel_ticket_lbl]
        sel_t          = next((t for t in open_t if t["id"]==sel_id), None)

        if sel_t:
            st.markdown(
                f"<div style='padding:10px 14px;background:var(--color-background-secondary);"
                f"border-radius:6px;font-size:12px;margin:8px 0'>"
                f"<b>{sel_t['id']}</b> · <b>{sel_t['category']}</b> · "
                f"Priority: {sel_t['priority']}<br>"
                f"Customer: {sel_t['customer_name']} · Account: {sel_t['account_no']}<br>"
                f"Assigned: {sel_t['staff_name']} · Unit: {sel_t['unit']}<br>"
                f"Opened: {sel_t['opened_at'][:16]} · "
                f"Due: {sel_t['due_at'][:16]} · "
                f"{'🔴 OVERDUE' if sel_t.get('_overdue') else '🟢 Within SLA'}"
                f"</div>", unsafe_allow_html=True)

            with st.form("resolve_form"):
                resolution = st.text_area("Resolution notes *", height=80,
                    placeholder="Describe how the issue was resolved and outcome for the customer.")
                if st.form_submit_button("✅ Mark as resolved", type="primary"):
                    if resolution:
                        resolved_t = slm.resolve(sel_id, resolution, uname)
                        breached_msg = "⚠️ SLA was breached" if resolved_t.get("breached") else "✅ Resolved within SLA"
                        audit_log("SLA_RESOLVED", uname, f"{sel_id}:{breached_msg}")
                        st.success(f"Ticket {sel_id} resolved. {breached_msg}")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("Resolution notes are required.")

# ════════════════════════════════════════════════════════════════
# TAB 4 — STAFF SLA SCORES
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Staff SLA adherence scores")
    st.caption("SLA score = tickets resolved within SLA ÷ total resolved tickets. "
               "This feeds directly into the CX Score KPI in the BSC.")

    days_back = st.slider("Period (days)", 7, 90, 30, key="sla_days")

    if len(staff_scores):
        score_rows = []
        for _, sr in staff_scores.iterrows():
            sc   = str(sr["Staff Code"])
            score, total, breached = slm.sla_score(staff_code=sc, days_back=days_back)
            if total > 0:
                score_rows.append({
                    "Staff":    sr["Staff Name"],
                    "Unit":     sr["Unit"],
                    "Role":     sr["Role"],
                    "Tickets":  total,
                    "Breached": breached,
                    "SLA Score":score,
                })

        if score_rows:
            sc_df = pd.DataFrame(score_rows).sort_values("SLA Score")
            sc_df["Rating"] = sc_df["SLA Score"].apply(
                lambda x: "🟢 Excellent" if x>=0.95 else
                          ("🟡 Good" if x>=0.85 else
                           ("🟠 At risk" if x>=0.70 else "🔴 Critical")))

            # Chart
            fig_s = px.bar(sc_df, x="Staff", y="SLA Score", color="SLA Score",
                           color_continuous_scale=["#E24B4A","#F5A623","var(--brand-primary,#006B3F)"],
                           title=f"Staff SLA scores — last {days_back} days",
                           range_color=[0,1])
            fig_s.add_hline(y=0.90, line_dash="dash", line_color="var(--brand-primary,#006B3F)",
                             annotation_text="90% target")
            fig_s.update_layout(height=320, xaxis_tickangle=-35,
                yaxis_tickformat=".0%",
                plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
            st.plotly_chart(fig_s, use_container_width=True)

            def hl_sla(v):
                try:
                    if isinstance(v, float):
                        if v>=0.95: return 'color:var(--brand-primary,#006B3F);font-weight:500'
                        if v>=0.85: return 'color:#F5A623'
                        return 'color:#E24B4A;font-weight:500'
                except: pass
                return ''

            sc_df["SLA Score"] = sc_df["SLA Score"].apply(lambda x: f"{x:.1%}")
            st.dataframe(sc_df.style.map(hl_sla, subset=['SLA Score']),
                         use_container_width=True, hide_index=True)
        else:
            st.info(f"No resolved tickets in the last {days_back} days.")
    else:
        st.info("Upload BSC data to see staff-level SLA scores.")

# ════════════════════════════════════════════════════════════════
# TAB 5 — ANALYTICS
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("SLA analytics")

    _sla_all = slm.get_all() if slm else []
    if not _sla_all:
        st.info("No SLA tickets yet.")
    else:
        _sl_df = pd.DataFrame(_sla_all)

        # Summary metrics
        _sa1,_sa2,_sa3,_sa4 = st.columns(4)
        _total_sl   = len(_sla_all)
        _breached_sl= sum(1 for t in _sla_all if t.get("breached"))
        _open_sl    = sum(1 for t in _sla_all if t.get("status") not in ("Resolved","Closed"))
        _tat_score  = (_total_sl - _breached_sl)/_total_sl*100 if _total_sl else 0
        _sa1.metric("Total tickets",    _total_sl)
        _sa2.metric("Open",             _open_sl)
        _sa3.metric("Breached",         _breached_sl,
                    delta=f"-{_breached_sl}" if _breached_sl else None, delta_color="inverse")
        _sa4.metric("TAT score",        f"{_tat_score:.1f}%",
                    delta="Target: 90%",
                    delta_color="normal" if _tat_score>=90 else "inverse")

        _sl_c1, _sl_c2 = st.columns(2)

        # Breach by unit heatmap
        with _sl_c1:
            if "unit" in _sl_df.columns:
                _unit_breach = (_sl_df.groupby("unit")
                                .apply(lambda g: pd.Series({
                                    "Total":   len(g),
                                    "Breached":g["breached"].sum() if "breached" in g else 0
                                })).reset_index())
                _unit_breach["Breach Rate"] = (_unit_breach["Breached"] /
                                               _unit_breach["Total"] * 100).round(1)
                _unit_breach = _unit_breach.sort_values("Breach Rate", ascending=False)
                fig_ub = px.bar(_unit_breach, x="Breach Rate", y="unit",
                                orientation="h",
                                title="Breach rate by unit (%)",
                                color="Breach Rate",
                                color_continuous_scale=["var(--brand-primary,#006B3F)","#F5A623","#E24B4A"],
                                range_color=[0,50],
                                labels={"unit":"Unit","Breach Rate":"Breach %"})
                fig_ub.add_vline(x=10, line_dash="dash", line_color="#374151")
                fig_ub.update_layout(height=max(280,len(_unit_breach)*28),
                                     coloraxis_showscale=False,
                                     plot_bgcolor="rgba(0,0,0,0)",
                                     paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_ub, use_container_width=True)

        # Ticket type breakdown
        with _sl_c2:
            if "ticket_type" in _sl_df.columns:
                _type_cnt = _sl_df["ticket_type"].value_counts().reset_index()
                _type_cnt.columns = ["Type","Count"]
                fig_tp = px.pie(_type_cnt, names="Type", values="Count",
                                title="Tickets by type",
                                color_discrete_sequence=px.colors.qualitative.Set2)
                fig_tp.update_layout(height=280, margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_tp, use_container_width=True)

        # Trend — tickets per week
        if "created_at" in _sl_df.columns:
            try:
                _sl_df["week"] = pd.to_datetime(
                    _sl_df["created_at"].str[:10]).dt.to_period("W").astype(str)
                _wk = _sl_df.groupby("week").agg(
                    Total=("id","count"),
                    Breached=("breached","sum")).reset_index()
                _wk.columns = ["Week","Total","Breached"]
                fig_wk = px.bar(_wk, x="Week", y=["Total","Breached"],
                                title="Weekly ticket volume",
                                barmode="overlay",
                                color_discrete_map={"Total":"#185FA5","Breached":"#E24B4A"})
                fig_wk.update_layout(height=240, plot_bgcolor="rgba(0,0,0,0)",
                                     paper_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_wk, use_container_width=True)
            except: pass
    anl = slm.analytics()

    if anl["total"] == 0:
        st.info("No tickets logged yet. Log tickets in the 'Log ticket' tab.")
    else:
        ac1, ac2 = st.columns(2)
        with ac1:
            # Breach rate by category
            if anl["by_category"]:
                cat_data = [{"Category": c[:22],
                              "Breach rate": round(v["breached"]/max(v["total"],1)*100,1),
                              "Total": v["total"]}
                             for c,v in anl["by_category"].items() if v["total"]>0]
                cat_df = pd.DataFrame(cat_data).sort_values("Breach rate", ascending=False)
                fig_br = px.bar(cat_df, x="Breach rate", y="Category",
                                orientation='h', color="Breach rate",
                                color_continuous_scale=["var(--brand-primary,#006B3F)","#F5A623","#E24B4A"],
                                title="Breach rate % by category",
                                range_color=[0,50])
                fig_br.update_layout(height=320,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                    margin=dict(l=0,r=0,t=40,b=0))
                st.plotly_chart(fig_br, use_container_width=True)

        with ac2:
            # Priority distribution
            prio_counts = {}
            for t in slm.tickets:
                p = t.get("priority","Medium")
                prio_counts[p] = prio_counts.get(p,0)+1
            prio_df = pd.DataFrame(list(prio_counts.items()), columns=["Priority","Count"])
            fig_p = px.pie(prio_df, names="Priority", values="Count",
                           title="Tickets by priority",
                           color="Priority",
                           color_discrete_map=PRIORITY_COLORS)
            fig_p.update_layout(height=320, margin=dict(l=0,r=0,t=40,b=0))
            st.plotly_chart(fig_p, use_container_width=True)

        # Unit performance table
        unit_scores = {}
        for t in slm.tickets:
            u = t.get("unit","Unknown")
            if u not in unit_scores:
                unit_scores[u] = {"total":0,"resolved":0,"breached":0}
            unit_scores[u]["total"] += 1
            if t["status"]=="Resolved":
                unit_scores[u]["resolved"] += 1
                if t.get("breached"): unit_scores[u]["breached"] += 1

        if unit_scores:
            unit_rows = [{"Unit": u,
                           "Total": v["total"],
                           "Resolved": v["resolved"],
                           "Breached": v["breached"],
                           "SLA Score": f"{(v['resolved']-v['breached'])/max(v['resolved'],1):.1%}"}
                          for u,v in unit_scores.items()]
            unit_df = pd.DataFrame(unit_rows).sort_values("SLA Score")
            st.markdown("**SLA performance by unit**")
            st.dataframe(unit_df, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 6 — SLA DEFINITIONS
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    st.subheader("SLA definitions & standards")
    st.caption("These are the service standards against which all tickets are measured.")

    for cat, cfg in SLA_CATEGORIES.items():
        clr = PRIORITY_COLORS.get(cfg["priority"], "#888")
        st.markdown(
            f"<div style='padding:8px 14px;background:var(--color-background-secondary);"
            f"border-left:4px solid {clr};"
            f"border-radius:0 6px 6px 0;margin:3px 0;font-size:12px'>"
            f"<div style='display:flex;justify-content:space-between'>"
            f"<b>{cat}</b>"
            f"<span style='background:{clr};color:var(--color-background-primary);padding:1px 6px;"
            f"border-radius:8px;font-size:10px'>{cfg['priority']} · {cfg['sla_hours']}h SLA</span>"
            f"</div>"
            f"<div style='color:#666;margin-top:2px'>{cfg['description']}</div>"
            f"<div style='color:#888;font-size:11px;margin-top:2px'>"
            f"Owner roles: {', '.join(cfg['owner_roles'][:3])}</div>"
            f"</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════
# TAB 7 — LMS / LEGAL / COMPLIANCE SLA TRACKER
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    st.markdown("**Cross-module SLA tracking** — Legal matters, Credit TAT, and Compliance case resolution.")
    from pathlib import Path as _Path
    import json as _json
    from datetime import date as _dt_lms
    from collections import defaultdict as _dd_lms

    _DATA = _Path(__file__).parent.parent / "data"

    _lt1, _lt2, _lt3 = st.tabs(["⚖️ Legal Matters", "🏦 Credit TAT", "🛡️ Compliance"])

    # ── Legal SLA ─────────────────────────────────────────────────
    with _lt1:
        try:
            _legal = _json.loads((_DATA/"legal_matters.json").read_text())
            _open_legal = [m for m in _legal if m["status"] not in ("completed","on_hold")]
            _overdue_l  = [m for m in _open_legal if m.get("sla_breached")]
            _lm1,_lm2,_lm3,_lm4 = st.columns(4)
            _lm1.metric("Open Matters",    len(_open_legal))
            _lm2.metric("Overdue",         len(_overdue_l), delta_color="inverse")
            _lm3.metric("On Track",        len(_open_legal)-len(_overdue_l))
            _sla_r = round(sum(1 for m in _legal if m["status"]=="completed" and not m.get("sla_breached"))/
                           max(sum(1 for m in _legal if m["status"]=="completed"),1)*100,1)
            _lm4.metric("SLA Rate",        f"{_sla_r}%")
            if _overdue_l:
                st.error(f"🔴 {len(_overdue_l)} legal matters past SLA")
            _by_type = _dd_lms(lambda:{"open":0,"overdue":0,"completed":0,"on_time":0})
            for _m in _legal:
                _bt = _by_type[_m["matter_type"]]
                if _m["status"] == "completed":
                    _bt["completed"] += 1
                    if not _m.get("sla_breached"): _bt["on_time"] += 1
                elif _m["status"] not in ("on_hold",):
                    _bt["open"] += 1
                    if _m.get("sla_breached"): _bt["overdue"] += 1
            _rows_l = [{"Type": mt,"Open": d["open"],"Overdue": d["overdue"],
                         "Completed": d["completed"],
                         "SLA Rate": f"{round(d['on_time']/max(d['completed'],1)*100,1)}%"}
                        for mt,d in sorted(_by_type.items())]
            st.dataframe(st.data_editor(None) if False else __import__("pandas").DataFrame(_rows_l),
                         use_container_width=True, hide_index=True)
        except Exception as _e:
            st.info(f"Legal data not available: {_e}")

    # ── Credit TAT ────────────────────────────────────────────────
    with _lt2:
        try:
            _apps = _json.loads((_DATA/"loan_applications.json").read_text())
            _decided = [a for a in _apps if a["status"] in
                        ("approved","declined","returned","credit_admin","disbursed")]
            _breached = [a for a in _decided if a.get("tat_days",0) > a.get("sla_target_days",10)]
            _am1,_am2,_am3,_am4 = st.columns(4)
            _am1.metric("Decided",        len(_decided))
            _am2.metric("SLA Breached",   len(_breached), delta_color="inverse")
            _am3.metric("SLA Rate", f"{round((len(_decided)-len(_breached))/max(len(_decided),1)*100,1)}%")
            _avg_tat = round(sum(a.get("tat_days",0) for a in _decided)/max(len(_decided),1),1)
            _am4.metric("Avg TAT (days)", str(_avg_tat))
            # By swim lane
            for _lane in ("Express","Standard","Complex"):
                _lane_apps = [a for a in _decided if a.get("swim_lane")==_lane]
                if not _lane_apps: continue
                _l_tat    = round(sum(a.get("tat_days",0) for a in _lane_apps)/len(_lane_apps),1)
                _l_sla    = {"Express":3,"Standard":10,"Complex":21}.get(_lane,10)
                _l_breach = sum(1 for a in _lane_apps if a.get("tat_days",0) > _l_sla)
                _l_rate   = round((len(_lane_apps)-_l_breach)/len(_lane_apps)*100,1)
                _icon = "✅" if _l_rate >= 80 else "🟡" if _l_rate >= 60 else "🔴"
                st.markdown(f"  {_icon} **{_lane}**: {len(_lane_apps)} decided · "
                             f"Avg TAT {_l_tat}d (SLA {_l_sla}d) · SLA Rate {_l_rate}%")
        except Exception as _e:
            st.info(f"Credit data not available: {_e}")

    # ── Compliance SLA ────────────────────────────────────────────
    with _lt3:
        try:
            _comp  = _json.loads((_DATA/"compliance_cases.json").read_text())
            _lms_c = _json.loads((_DATA/"lms_config.json").read_text())
            _sla_d = _lms_c.get("compliance_sla_days", {"Critical":1,"High":3,"Medium":7,"Low":14})
            _open_c = [c for c in _comp if c["status"] in ("open","under_review")]
            _today_c = _dt_lms.today()
            _breach_c = 0
            for _c in _open_c:
                _rl = _c.get("risk_level","Low")
                _sla = _sla_d.get(_rl, 7)
                try:
                    _raised = _dt_lms.fromisoformat(_c.get("raised_date",str(_today_c)))
                    if (_today_c - _raised).days > _sla: _breach_c += 1
                except: pass
            _cleared = sum(1 for c in _comp if c["status"]=="cleared")
            _cm1,_cm2,_cm3,_cm4 = st.columns(4)
            _cm1.metric("Total Cases",   len(_comp))
            _cm2.metric("Open",          len(_open_c))
            _cm3.metric("SLA Breached",  _breach_c, delta_color="inverse")
            _cm4.metric("Cleared",       _cleared)
            # By risk level
            for _rl in ("Critical","High","Medium","Low"):
                _rl_c = [c for c in _open_c if c.get("risk_level")==_rl]
                if not _rl_c: continue
                _rl_sla = _sla_d.get(_rl, 7)
                _rl_br  = sum(1 for c in _rl_c
                               if (_today_c - _dt_lms.fromisoformat(c.get("raised_date",str(_today_c)))).days > _rl_sla
                               if c.get("raised_date"))
                _icon = "🔴" if _rl=="Critical" and _rl_br > 0 else "🟡" if _rl_br > 0 else "✅"
                st.markdown(f"  {_icon} **{_rl}** (SLA {_rl_sla}d): "
                             f"{len(_rl_c)} open · {_rl_br} breached")
        except Exception as _e:
            st.info(f"Compliance data not available: {_e}")
