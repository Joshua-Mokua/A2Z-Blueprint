"""pages/14_branch_log.py — Daily Branch Log: staff reporting + manager validation."""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state
from pages._access import require_access, get_my_scope
require_access("sales_customer.branch_log")





um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
role     = str(ud.get("role", "")).lower()
name     = ud.get("full_name", uname)
is_admin = ud.get("is_admin", False)
sc       = str(ud.get("staff_code", ""))

# ── Area Manager: branch submission tracker ─────────────────────
_is_area_mgr = any(x in role.lower() for x in ("area manager","regional","head of branches","head of retail"))
if _is_area_mgr or is_admin:
    st.markdown("**Branch log submission tracker:**")
    import json as _jbl
    from pathlib import Path as _pbl
    _logs = _jbl.loads((_pbl(__file__).parent.parent/"data"/"branch_actuals.json").read_text()) if (_pbl(__file__).parent.parent/"data"/"branch_actuals.json").exists() else {}
    _branches_all = list(set(u.get("unit","") for u in json.loads((_pbl(__file__).parent.parent/"data"/"users.json").read_text()).values()
                             if u.get("unit","") not in ("Head Office","HO","")))
    _today_bl = date.today()
    _month_logs = {k:v for k,v in _logs.items() if isinstance(v,dict) and str(_today_bl)[:7] in k}
    _submitted   = len(_month_logs)
    _pending_sub = len(_branches_all) - _submitted
    _bs1,_bs2,_bs3 = st.columns(3)
    _bs1.metric("Submitted this month", _submitted)
    _bs2.metric("Pending submission",   max(_pending_sub,0))
    _bs3.metric("Total branches",       len(_branches_all))
    if _pending_sub > 0:
        st.warning(f"⚠️ {_pending_sub} branch(es) have not submitted their monthly log")
    st.markdown("---")
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())

# ── LOG FIELDS ───────────────────────────────────────────────────────
LOG_FIELDS = [
    # (key, label, type, unit, bsc_kpi_link)
    ("accounts_opened",       "Accounts Opened",              "int",   "accounts", "New Customer Acquisition"),
    ("accounts_activated",    "Dormant Accounts Reactivated", "int",   "accounts", "Dormancy Reactivation"),
    ("transactions_count",    "Transactions Processed",       "int",   "count",    "Transactions"),
    ("cards_issued",          "Cards Issued/Renewed",         "int",   "cards",    None),
    ("dfs_registrations",     "DFS / Mobile Money Registrations","int","count",    "Digital Acquiring"),
    ("loans_referred",        "Loans Referred",               "int",   "count",    "Loans Disbursement"),
    ("loans_disbursed",       "Loans Disbursed (KES)",        "amount","KES",      "Loan Book Growth"),
    ("deposits_mobilised",    "Deposits Mobilised (KES)",     "amount","KES",      "Deposit Growth"),
    ("bancassurance_sold",    "Bancassurance Policies Sold",  "int",   "policies", "Bancassurance"),
    ("complaints_received",   "Customer Complaints Received", "int",   "count",    None),
    ("complaints_resolved",   "Complaints Resolved Same Day", "int",   "count",    "Complaint Resolution Rate"),
    ("digital_txns",          "Digital Transactions Assisted","int",   "count",    "Digital Transaction Migration"),
    ("new_leads",             "New Sales Leads Generated",    "int",   "leads",    None),
    ("cross_sell_success",    "Cross-sell Successes",         "int",   "count",    None),
    ("teller_errors",         "Teller Errors / Differences",  "int",   "count",    "Timely Reconciliations"),
    ("customer_visits",       "Customers Served",             "int",   "count",    "CX Score"),
    ("nps_collected",         "NPS Survey Responses Collected","int",  "count",    "NPS Score"),
    ("remarks",               "Remarks / Challenges",         "text",  "",         None),
]

class BranchLogManager:
    def __init__(self):
        self.file = DATA_DIR / "branch_logs.json"
        self.logs = self._load()

    def _load(self):
        if not self.file.exists(): self.file.write_text("[]")
        try:
            raw = self.file.read_text()
            d = json.loads(raw) if raw.strip() else []
            return d if isinstance(d, list) else []
        except: return []

    def _save(self):
        self.a2z_db.save_json(file, self.logs)

    def submit(self, data: dict) -> dict:
        today = str(date.today())
        # Check if already submitted today
        existing = next((l for l in self.logs
                         if l["staff_code"]==str(data.get("staff_code",""))
                         and l["log_date"]==today), None)
        if existing:
            # Update
            existing.update(data)
            existing["updated_at"] = datetime.now().isoformat()
            existing["validated"]  = False  # re-validation needed
            self._save()
            return existing

        rec = {
            "id":          f"LOG{len(self.logs)+1:06d}",
            "log_date":    today,
            "staff_code":  str(data.get("staff_code","")),
            "staff_name":  data.get("staff_name",""),
            "unit":        data.get("unit",""),
            "role":        data.get("role",""),
            "submitted_at":datetime.now().isoformat(),
            "validated":   False,
            "validated_by":"",
            "validated_at":"",
            "manager_note":"",
            **{k: data.get(k, 0) for k,_,t,_,_ in LOG_FIELDS if t != "text"},
            "remarks":     data.get("remarks",""),
        }
        self.logs.append(rec)
        self._save()
        return rec

    def validate(self, log_id: str, manager: str, note: str, approved: bool):
        for l in self.logs:
            if l["id"] == log_id:
                l["validated"]    = approved
                l["validated_by"] = manager
                l["validated_at"] = datetime.now().isoformat()
                l["manager_note"] = note
                l["rejected"]     = not approved
                self._save()
                return l
        return None

    def get_today(self, unit=None):
        today = str(date.today())
        logs  = [l for l in self.logs if l["log_date"]==today]
        if unit and unit!="All":
            logs = [l for l in logs if l["unit"]==unit]
        return logs

    def get_pending_validation(self, unit=None):
        today = str(date.today())
        logs  = [l for l in self.logs
                 if not l.get("validated") and not l.get("rejected",False)]
        if unit and unit!="All":
            logs = [l for l in logs if l["unit"]==unit]
        return logs

    def get_history(self, staff_code=None, unit=None, days=7):
        cutoff = str(date.today() - timedelta(days=days))
        logs   = [l for l in self.logs if l["log_date"]>=cutoff]
        if staff_code: logs = [l for l in logs if l["staff_code"]==str(staff_code)]
        if unit and unit!="All": logs = [l for l in logs if l["unit"]==unit]
        return logs

    def submission_rate(self, unit, days=7):
        """% of eligible staff who submitted logs in the period."""
        logs = self.get_history(unit=unit, days=days)
        dates_covered = len(set(l["log_date"] for l in logs))
        submitters    = len(set(l["staff_code"] for l in logs))
        return submitters, dates_covered

    def unit_totals(self, unit, days=7):
        logs = self.get_history(unit=unit, days=days)
        validated = [l for l in logs if l.get("validated")]
        if not validated:
            return {}
        totals = {}
        for k,_,t,_,_ in LOG_FIELDS:
            if t != "text":
                totals[k] = sum(float(l.get(k,0) or 0) for l in validated)
        return totals

    def get_all(self):
        """Return all branch log entries."""
        return list(self.logs)

if "branch_log_manager" not in st.session_state:
    st.session_state["branch_log_manager"] = BranchLogManager()
blm = st.session_state.get("branch_log_manager")
if blm is None: st.info("Branch log loading..."); st.stop()

role_low  = str(ud.get("role","")).lower()
my_unit   = ud.get("unit","")
my_sc     = str(ud.get("staff_code",""))
is_mgr    = any(k in role_low for k in ("manager","director","head","regional","admin"))
is_admin  = "admin" in role_low or ud.get("can_view_all", False)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📝 Branch Daily Log</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Daily reporting · Handover</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📝 Branch Daily Log</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Daily reporting · Handover · Manager view</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📝 Branch Daily Log</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Daily reporting · Handover · Manager view</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📝 Branch Daily Log</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Daily reporting · Manager view · Handover</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📝 Branch Daily Log</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Daily reporting · Manager view</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:14px 20px;background:#2C3E50;border-radius:10px;margin-bottom:16px'>"
    "<div style='color:var(--color-background-primary);font-size:16px;font-weight:500'>Daily Branch Activity Log</div>"
    "<div style='color:#BDC3C7;font-size:11px;margin-top:2px'>"
    f"Submit · Validate · Track · Analyse | Today: {date.today().strftime('%A, %d %B %Y')}"
    "</div></div>", unsafe_allow_html=True)

tabs = st.tabs([
    "📝 My daily log",
    "✅ Validate (managers)",
    "📊 Unit summary",
    "📈 Trends",
    "🏆 Leaderboard",
    "🏛️ Branch Performance (Standard #90)",
    "🛠️ Branch Ops Excellence (Standard #92)",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — MY DAILY LOG
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    st.subheader(f"Daily log — {date.today().strftime('%d %b %Y')}")

    # Check if already submitted today
    today_logs = blm.get_today()
    my_today   = next((l for l in today_logs if l["staff_code"]==my_sc), None)

    if my_today:
        status = "✅ Validated" if my_today.get("validated") else ("❌ Rejected" if my_today.get("rejected") else "⏳ Awaiting validation")
        st.markdown(
            f"<div style='padding:10px 14px;background:var(--brand-light,#E8F5EE);"
            f"border-left:4px solid var(--brand-primary,#006B3F);border-radius:0 6px 6px 0;margin-bottom:12px'>"
            f"<b>Already submitted today</b> · Status: {status}"
            f"{'<br>Manager note: ' + my_today['manager_note'] if my_today.get('manager_note') else ''}"
            f"</div>", unsafe_allow_html=True)

        if my_today.get("rejected"):
            st.warning("Your log was rejected. Please correct and resubmit.")
        elif not my_today.get("validated"):
            st.info("Awaiting manager validation.")
            st.stop()

    with st.form("daily_log_form"):
        st.markdown("#### Enter today's activity numbers")
        st.caption("Enter actual counts for each activity. Leave 0 if not applicable to your role.")

        # Grid of fields
        field_values = {}
        # Group fields into pairs
        field_list = [(k,l,t,u,kpi) for k,l,t,u,kpi in LOG_FIELDS if t != "text"]
        for i in range(0, len(field_list), 2):
            cols = st.columns(2)
            for j, (k,l,t,u,kpi) in enumerate(field_list[i:i+2]):
                with cols[j]:
                    default = float(my_today.get(k,0)) if my_today else 0.0
                    if t == "amount":
                        field_values[k] = st.number_input(
                            f"{l} ({u})", min_value=0.0, value=default,
                            step=10000.0, format="%.0f", key=f"log_{k}")
                    else:
                        field_values[k] = st.number_input(
                            f"{l}", min_value=0, value=int(default),
                            step=1, key=f"log_{k}")

        remarks = st.text_area("Remarks / challenges / highlights",
                               value=my_today.get("remarks","") if my_today else "",
                               height=70, key="log_remarks")

        col_s, col_r = st.columns([3,1])
        submitted = col_s.form_submit_button("📤 Submit daily log", type="primary")
        if submitted:
            # Get staff info
            my_row = staff_scores[staff_scores["Staff Code"].astype(str)==my_sc] if len(staff_scores) else pd.DataFrame()
            my_name = my_row["Staff Name"].values[0] if len(my_row) else ud.get("full_name", uname)
            my_role = my_row["Role"].values[0] if len(my_row) else ud.get("role","")
            my_unit_val = my_row["Unit"].values[0] if len(my_row) else my_unit

            log_data = {
                "staff_code": my_sc,
                "staff_name": my_name,
                "unit":       my_unit_val,
                "role":       my_role,
                "remarks":    remarks,
                **field_values,
            }
            rec = blm.submit(log_data)
            audit_log("BRANCH_LOG_SUBMITTED", uname, f"{my_unit_val}:{date.today()}")
            st.success(f"✅ Daily log submitted. Awaiting manager validation.")
            st.cache_data.clear()
            st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 2 — VALIDATE (MANAGERS)
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    if not is_mgr:
        st.info("Validation is available to branch managers and above.")
        st.stop()

    st.subheader("Validate staff daily logs")
    st.caption("Review and approve or reject staff submissions. Only validated logs count in analytics.")

    # Unit filter for admin/director
    if is_admin:
        all_units = sorted(set(l["unit"] for l in blm.logs if l["unit"]))
        val_unit  = st.selectbox("Unit", ["All"] + all_units, key="val_unit_f")
    else:
        val_unit = my_unit

    pending = blm.get_pending_validation(val_unit)

    if not pending:
        st.success("No logs pending validation.")
    else:
        st.markdown(f"**{len(pending)} log(s) awaiting your validation:**")
        for log in pending:
            with st.expander(
                f"📋 {log['staff_name']} · {log['role']} · {log['unit']} · {log['log_date']}",
                expanded=True):

                # Show all fields
                col_a, col_b = st.columns(2)
                field_pairs = [(k,l,t,u,kpi) for k,l,t,u,kpi in LOG_FIELDS if t!="text"]
                for i, (k,l,t,u,kpi) in enumerate(field_pairs):
                    v = log.get(k, 0)
                    col = col_a if i%2==0 else col_b
                    display = f"{v:,.0f}" if t=="amount" else str(int(v or 0))
                    kpi_tag = f" → {kpi}" if kpi else ""
                    col.markdown(
                        f"<div style='font-size:11px;padding:2px 0'>"
                        f"<span style='color:#888'>{l}:</span> "
                        f"<b>{display}</b>"
                        f"<span style='color:var(--brand-primary,#006B3F);font-size:10px'>{kpi_tag}</span>"
                        f"</div>", unsafe_allow_html=True)

                if log.get("remarks"):
                    st.markdown(f"**Remarks:** {log['remarks']}")

                with st.form(f"val_form_{log['id']}"):
                    vf1, vf2 = st.columns(2)
                    approve = vf1.radio("Decision", ["✅ Approve","❌ Reject"],
                                        horizontal=True, key=f"vd_{log['id']}")
                    mgr_note = vf2.text_input("Note (optional)", key=f"vn_{log['id']}")
                    if st.form_submit_button("Submit decision", type="primary"):
                        approved = "Approve" in approve
                        blm.validate(log["id"], uname, mgr_note, approved)
                        audit_log("BRANCH_LOG_VALIDATED", uname,
                                  f"{log['id']}:{'approved' if approved else 'rejected'}")
                        st.success("Decision recorded.")
                        st.cache_data.clear()
                        st.rerun()

# ════════════════════════════════════════════════════════════════
# TAB 3 — UNIT SUMMARY
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Unit daily summary")

    su_unit = st.selectbox("Select unit",
        ["All"] + sorted(set(l["unit"] for l in blm.logs)) if blm.logs else ["All"],
        key="su_unit")
    su_days = st.slider("Period (days)", 1, 30, 7, key="su_days")

    today_by_unit = blm.get_today(su_unit if su_unit!="All" else None)
    submitted_today = len(today_by_unit)
    validated_today = len([l for l in today_by_unit if l.get("validated")])
    pending_today   = len([l for l in today_by_unit if not l.get("validated") and not l.get("rejected")])

    tc1, tc2, tc3 = st.columns(3)
    tc1.metric("Submitted today",  submitted_today)
    tc2.metric("Validated today",  validated_today)
    tc3.metric("Pending today",    pending_today,
               delta=f"-{pending_today}" if pending_today else "0", delta_color="inverse")

    totals = blm.unit_totals(su_unit, su_days) if su_unit!="All" else {}

    if totals:
        st.markdown(f"#### Validated activity totals — last {su_days} days")
        t_rows = []
        for k,label,t,unit,kpi in LOG_FIELDS:
            if t!="text" and k in totals and totals[k]>0:
                display = f"{totals[k]:,.0f}" if t=="amount" else f"{int(totals[k]):,}"
                t_rows.append({"Activity": label, "Total": display,
                                "Unit": unit, "KPI": kpi or "—"})
        if t_rows:
            st.dataframe(pd.DataFrame(t_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No validated logs for this unit yet.")

    # Today's submissions table
    if today_by_unit:
        st.markdown("#### Today's submissions")
        sub_rows = [{
            "Staff":     l["staff_name"],
            "Role":      l["role"],
            "Accounts":  int(l.get("accounts_opened",0)),
            "Reactivated":int(l.get("accounts_activated",0)),
            "Txns":      int(l.get("transactions_count",0)),
            "DFS":       int(l.get("dfs_registrations",0)),
            "Deposits":  f"KES {float(l.get('deposits_mobilised',0)):,.0f}",
            "Status":    "✅ Validated" if l.get("validated") else
                         ("❌ Rejected" if l.get("rejected") else "⏳ Pending"),
        } for l in today_by_unit]
        st.dataframe(pd.DataFrame(sub_rows), use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 4 — TRENDS
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Activity trends")

    # Submission heatmap — days x weeks
    _all_logs = blm.get_all() if blm else []
    if _all_logs:
        from collections import defaultdict
        import calendar as _cal
        _sub_days = defaultdict(int)
        _today_bl = date.today()
        _start_bl = _today_bl.replace(day=1)
        for _lg in _all_logs:
            _ld = str(_lg.get("date",""))[:10]
            if _ld >= str(_start_bl):
                _sub_days[_ld] += 1

        # Calendar heatmap for current month
        _mo_days  = _cal.monthrange(_today_bl.year, _today_bl.month)[1]
        _first_wd = date(_today_bl.year, _today_bl.month, 1).weekday()
        _cells_html = (
            "<div style='background:var(--color-background-primary);border:0.5px solid var(--color-border-tertiary);border-radius:8px;"
            "padding:12px;margin-bottom:12px'>"
            "<div style='font-size:11px;font-weight:700;color:var(--color-text-primary);margin-bottom:8px'>"
            f"📅 Submission heatmap — {_cal.month_name[_today_bl.month]} {_today_bl.year}</div>"
            "<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:3px;max-width:420px'>"
        )
        for _dn in ["Mo","Tu","We","Th","Fr","Sa","Su"]:
            _cells_html += f"<div style='font-size:9px;color:var(--color-text-tertiary);text-align:center;font-weight:600'>{_dn}</div>"
        for _ in range(_first_wd):
            _cells_html += "<div></div>"
        for _d in range(1, _mo_days+1):
            _dt_str = f"{_today_bl.year}-{_today_bl.month:02d}-{_d:02d}"
            _cnt    = _sub_days.get(_dt_str, 0)
            _is_td  = (_d == _today_bl.day)
            _bg     = ("var(--brand-primary,#006B3F)" if _cnt>=5 else "#4ADE80" if _cnt>=3 else "#BBF7D0" if _cnt>=1 else "#F3F4F6")
            _fg     = "var(--color-background-primary)" if _cnt>=3 else ("#111827" if _cnt==0 else "#166534")
            _brd    = "2px solid #F5A623" if _is_td else "none"
            _cells_html += (
                f"<div style='background:{_bg};color:{_fg};border:{_brd};"
                f"border-radius:4px;padding:4px 2px;text-align:center;"
                f"font-size:10px;font-weight:{'700' if _is_td else '500'}'>"
                f"<div>{_d}</div>"
                f"{'<div style="font-size:8px">' + str(_cnt) + '</div>' if _cnt else ''}"
                f"</div>"
            )
        _cells_html += "</div></div>"
        st.markdown(_cells_html, unsafe_allow_html=True)
    tr_unit = st.selectbox("Unit", ["All"] + sorted(set(l["unit"] for l in blm.logs)),
                            key="tr_unit_f")
    tr_metric = st.selectbox("Metric", [l for _,l,t,_,_ in LOG_FIELDS if t!="text"],
                              key="tr_metric_f")
    tr_key = next((k for k,l,_,_,_ in LOG_FIELDS if l==tr_metric), None)
    tr_days= st.slider("Days", 7, 60, 30, key="tr_days")

    hist = blm.get_history(unit=tr_unit if tr_unit!="All" else None, days=tr_days)
    validated_hist = [l for l in hist if l.get("validated")]

    if validated_hist and tr_key:
        tr_df = pd.DataFrame([{
            "Date":   l["log_date"],
            "Value":  float(l.get(tr_key, 0) or 0),
            "Staff":  l["staff_name"],
            "Unit":   l["unit"],
        } for l in validated_hist])

        daily = tr_df.groupby("Date")["Value"].sum().reset_index()
        fig_tr = px.line(daily, x="Date", y="Value",
                         title=f"{tr_metric} — daily trend ({tr_unit})",
                         markers=True, line_shape="spline")
        fig_tr.update_traces(line_color="var(--brand-primary,#006B3F)", line_width=2)
        fig_tr.update_layout(height=320,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_tr, use_container_width=True)

        # Staff breakdown
        staff_daily = tr_df.groupby("Staff")["Value"].sum().reset_index().sort_values("Value",ascending=False)
        fig_sb = px.bar(staff_daily.head(15), x="Staff", y="Value",
                        title=f"{tr_metric} by staff",
                        color="Value", color_continuous_scale=["#E8F5EE","var(--brand-primary,#006B3F)"])
        fig_sb.update_layout(height=280, xaxis_tickangle=-30,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_sb, use_container_width=True)
    else:
        st.info("No validated data available. Logs must be submitted and validated by a manager first.")

# ════════════════════════════════════════════════════════════════
# TAB 5 — LEADERBOARD
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("Branch activity leaderboard")
    st.caption("Rankings based on validated daily log submissions — last 30 days.")

    hist30 = blm.get_history(days=30)
    val30  = [l for l in hist30 if l.get("validated")]

    if not val30:
        st.info("No validated logs yet. Once managers validate submissions, the leaderboard will populate.")
    else:
        leader_rows = {}
        for l in val30:
            sc = l["staff_code"]
            if sc not in leader_rows:
                leader_rows[sc] = {
                    "Staff Code": sc,
                    "Staff Name": l["staff_name"],
                    "Unit":       l["unit"],
                    "Role":       l["role"],
                    "Days submitted": 0,
                    "Accounts opened": 0,
                    "Reactivations": 0,
                    "DFS regs": 0,
                    "Deposits (KES)": 0,
                    "Transactions": 0,
                    "Cross-sells": 0,
                }
            leader_rows[sc]["Days submitted"] += 1
            leader_rows[sc]["Accounts opened"]  += int(l.get("accounts_opened",0) or 0)
            leader_rows[sc]["Reactivations"]    += int(l.get("accounts_activated",0) or 0)
            leader_rows[sc]["DFS regs"]         += int(l.get("dfs_registrations",0) or 0)
            leader_rows[sc]["Deposits (KES)"]   += float(l.get("deposits_mobilised",0) or 0)
            leader_rows[sc]["Transactions"]     += int(l.get("transactions_count",0) or 0)
            leader_rows[sc]["Cross-sells"]      += int(l.get("cross_sell_success",0) or 0)

        lb_df = pd.DataFrame(list(leader_rows.values()))
        # Composite score: normalise each metric and sum
        metrics = ["Accounts opened","Reactivations","DFS regs","Transactions","Cross-sells"]
        for m in metrics:
            mx = lb_df[m].max()
            lb_df[f"_{m}_n"] = lb_df[m]/mx if mx>0 else 0
        lb_df["Score"] = lb_df[[f"_{m}_n" for m in metrics]].mean(axis=1).round(3)
        lb_df = lb_df.sort_values("Score", ascending=False).reset_index(drop=True)
        lb_df.index = lb_df.index + 1
        lb_df["Rank"] = lb_df.index
        lb_df["Deposits (KES)"] = lb_df["Deposits (KES)"].apply(lambda x: f"{x:,.0f}")

        display_cols = ["Rank","Staff Name","Unit","Days submitted",
                        "Accounts opened","Reactivations","DFS regs",
                        "Transactions","Deposits (KES)","Score"]
        drop_cols = [c for c in lb_df.columns if c.startswith('_')]
        lb_df = lb_df.drop(columns=drop_cols)

        def hl_rank(v):
            if v == 1: return 'background-color:#FFD700;font-weight:bold'
            if v == 2: return 'background-color:#C0C0C0;font-weight:bold'
            if v == 3: return 'background-color:#CD7F32;font-weight:bold'
            return ''

        st.dataframe(
            lb_df[display_cols].style.map(hl_rank, subset=['Rank']),
            use_container_width=True, height=400)

        # Submission compliance
        st.markdown("---")
        st.markdown("#### Submission compliance — who is logging consistently?")
        compliance_df = lb_df[["Staff Name","Unit","Days submitted"]].copy()
        working_days = min(30, (date.today() - date(date.today().year, date.today().month, 1)).days + 1)
        compliance_df["Compliance %"] = (compliance_df["Days submitted"] / working_days * 100).clip(0,100).round(1)
        compliance_df = compliance_df.sort_values("Compliance %", ascending=False)
        fig_c = px.bar(compliance_df.head(20), x="Staff Name", y="Compliance %",
                       color="Compliance %",
                       color_continuous_scale=["#E24B4A","#F5A623","var(--brand-primary,#006B3F)"],
                       range_color=[0,100], title="Log submission compliance (%)")
        fig_c.add_hline(y=80, line_dash="dash", line_color="var(--brand-primary,#006B3F)",
                         annotation_text="80% target")
        fig_c.update_layout(height=300, xaxis_tickangle=-30,
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig_c, use_container_width=True)


# ════════════════════════════════════════════════════════════════
# TAB 6 — BRANCH PERFORMANCE (Standard #90, integrated v5.80)
# ════════════════════════════════════════════════════════════════
with tabs[5]:
    from utils.branch_performance import (
        BranchPerformanceEngine, BranchPnlInputs,
        BRANCH_LIFECYCLE_STAGES, LIFECYCLE_BANDS_YEARS,
        PERFORMANCE_TIERS, PEER_GROUP_LOCATIONS, PEER_GROUP_SIZES,
        TIER_1_THRESHOLD_PCT, BRANCH_PNL_LINES,
    )
    from utils.core_audit import audit_log
    from decimal import Decimal as _D_bp

    st.markdown(
        f"**Standard #90 — Branch Performance Engine**. "
        f"P&L computation, cost-income ratio, Return on Average Assets, "
        f"lifecycle classification, peer benchmarking, quartile ranking."
    )
    st.caption(
        f"Performance tiers: {' / '.join(PERFORMANCE_TIERS)} "
        f"(TIER_1 ≥ {TIER_1_THRESHOLD_PCT}th percentile). "
        f"Lifecycle bands: NEW (0-2y) / GROWTH (2-5y) / MATURE (5+y)."
    )

    bp_sub_tabs = st.tabs([
        "📊 Branch P&L",
        "🌳 Lifecycle Classifier",
        "📐 Cost-Income & RoAA",
        "🏅 Peer Benchmarking",
    ])

    # ──────── Branch P&L ────────
    with bp_sub_tabs[0]:
        st.markdown(
            "**Branch P&L computation** — deterministic income/expense aggregation.")
        st.caption(
            "Engine returns 6 BRANCH_PNL_LINES: NII / NON_INTEREST_INCOME / "
            "OPEX_DIRECT / OPEX_ALLOCATED / IMPAIRMENT / NPBT plus total_income, total_opex.")
        c1, c2 = st.columns(2)
        with c1:
            bp_id = st.text_input("Branch ID", value="BR_100", key="bp_id")
            bp_nii = st.number_input("NII (KES M)",
                                       min_value=0.0, value=50.0, step=5.0,
                                       key="bp_nii",
                                       help="Net interest income for the period.")
            bp_nfi = st.number_input("Non-interest income (KES M)",
                                       min_value=0.0, value=15.0, step=2.0,
                                       key="bp_nfi")
            bp_imp = st.number_input("Impairment (KES M)",
                                       min_value=0.0, value=3.0, step=0.5,
                                       key="bp_imp")
        with c2:
            bp_opex_dir = st.number_input("Direct opex (KES M)",
                                            min_value=0.0, value=20.0, step=2.0,
                                            key="bp_opex_dir",
                                            help="Salaries, rent, utilities at branch.")
            bp_opex_alloc = st.number_input("Allocated opex (KES M)",
                                              min_value=0.0, value=8.0, step=1.0,
                                              key="bp_opex_alloc",
                                              help="Headquarters cost allocation.")
            bp_assets = st.number_input("Average assets (KES M)",
                                          min_value=0.0, value=800.0, step=50.0,
                                          key="bp_assets")

        if st.button("Compute branch P&L",
                       key="bp_pnl_btn", type="primary"):
            inputs = BranchPnlInputs(
                branch_id=bp_id,
                nii=_D_bp(str(bp_nii)) * _D_bp("1000000"),
                non_interest_income=_D_bp(str(bp_nfi)) * _D_bp("1000000"),
                opex_direct=_D_bp(str(bp_opex_dir)) * _D_bp("1000000"),
                opex_allocated=_D_bp(str(bp_opex_alloc)) * _D_bp("1000000"),
                impairment=_D_bp(str(bp_imp)) * _D_bp("1000000"),
                avg_assets=_D_bp(str(bp_assets)) * _D_bp("1000000"),
            )
            r = BranchPerformanceEngine.branch_pnl(inputs)
            if r.get("computed"):
                k1, k2, k3, k4 = st.columns(4)
                ti = _D_bp(str(r["total_income"]))
                tox = _D_bp(str(r["total_opex"]))
                imp = _D_bp(str(r["impairment"]))
                npbt = _D_bp(str(r["npbt"]))
                k1.metric("Total income",
                           f"KES {ti/_D_bp('1000000'):,.2f}M")
                k2.metric("Total opex",
                           f"KES {tox/_D_bp('1000000'):,.2f}M")
                k3.metric("Impairment",
                           f"KES {imp/_D_bp('1000000'):,.2f}M")
                k4.metric("**NPBT**",
                           f"KES {npbt/_D_bp('1000000'):,.2f}M",
                           delta=f"{(npbt/ti*100 if ti else 0):.1f}% margin"
                                  if ti else None)

                # Cost-income ratio derived from this same data
                cir = BranchPerformanceEngine.cost_income_ratio(tox, ti)
                roaa = BranchPerformanceEngine.return_on_avg_assets(
                    npbt, _D_bp(str(bp_assets)) * _D_bp("1000000"))
                col1, col2 = st.columns(2)
                if cir is not None:
                    cir_color = "#10B981" if cir < 50 else "#F59E0B" if cir < 70 else "#DC2626"
                    col1.markdown(
                        f"<div style='padding:12px;background:{cir_color}22;"
                        f"border-left:4px solid {cir_color};border-radius:8px'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"COST-INCOME RATIO</div>"
                        f"<div style='font-size:24px;font-weight:800;color:{cir_color}'>"
                        f"{cir:.2f}%</div>"
                        f"<div style='font-size:11px;opacity:0.85'>Lower = more efficient</div>"
                        f"</div>", unsafe_allow_html=True)
                if roaa is not None:
                    col2.metric("Return on Avg Assets", f"{roaa:.2f}%",
                                 help="NPBT / average assets — measures profitability.")

                audit_log("IFRS_ENGINE_USED", uname,
                           f"Branch #90: P&L {bp_id} NPBT={npbt} CIR={cir}")
            else:
                st.error("Could not compute (Rule 1 — missing inputs).")

    # ──────── Lifecycle classifier ────────
    with bp_sub_tabs[1]:
        st.markdown(
            "**Branch Lifecycle Stage** — classification by years open.")
        st.caption(
            f"NEW: 0-2 years (still ramping) · GROWTH: 2-5 years (scaling) · "
            f"MATURE: 5+ years (steady-state). Different KPI expectations apply per stage.")
        years = st.number_input("Years open",
                                  min_value=0, max_value=50, value=3, step=1,
                                  key="bp_years")
        if st.button("Classify lifecycle",
                       key="bp_lc_btn", type="primary"):
            stage = BranchPerformanceEngine.lifecycle_stage(int(years))
            if stage:
                colors = {"NEW": "#3B82F6", "GROWTH": "#10B981", "MATURE": "#8B5CF6"}
                color = colors.get(stage, "#6B7280")
                st.markdown(
                    f"<div style='padding:18px;background:{color}22;"
                    f"border-left:6px solid {color};border-radius:12px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"LIFECYCLE STAGE</div>"
                    f"<div style='font-size:28px;font-weight:800;color:{color}'>"
                    f"{stage}</div></div>",
                    unsafe_allow_html=True)
                stage_guidance = {
                    "NEW": "🌱 Focus: customer acquisition, brand awareness, breakeven trajectory. Lower P&L expectations.",
                    "GROWTH": "🚀 Focus: deposit/loan growth, cross-sell, profitability. Standard KPI targets.",
                    "MATURE": "🏛️ Focus: efficiency, retention, market share defence. Higher cost-income discipline.",
                }
                st.info(stage_guidance.get(stage, ""))
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Branch #90: lifecycle {years}y → {stage}")

    # ──────── Cost-income + RoAA ────────
    with bp_sub_tabs[2]:
        st.markdown(
            "**Cost-Income Ratio & Return on Average Assets** "
            "(standalone calculators)")
        st.caption(
            "Use these for cross-branch comparison or for testing scenarios "
            "without going through full P&L computation.")

        cir_tab, roaa_tab = st.tabs([
            "📐 Cost-Income Ratio",
            "💎 Return on Avg Assets",
        ])

        with cir_tab:
            st.markdown("**Cost-Income Ratio** = Total opex / Total income")
            c1, c2 = st.columns(2)
            with c1:
                opex_v = st.number_input("Total opex (KES M)",
                                           min_value=0.0, value=28.0, step=2.0,
                                           key="bp_cir_opex")
            with c2:
                inc_v = st.number_input("Total income (KES M)",
                                          min_value=0.0, value=65.0, step=5.0,
                                          key="bp_cir_inc")
            if st.button("Compute CIR", key="bp_cir_btn", type="primary"):
                cir = BranchPerformanceEngine.cost_income_ratio(
                    _D_bp(str(opex_v)) * _D_bp("1000000"),
                    _D_bp(str(inc_v)) * _D_bp("1000000"))
                if cir is None:
                    st.error("Could not compute (income must be > 0).")
                else:
                    color = "#10B981" if cir < 50 else "#F59E0B" if cir < 70 else "#DC2626"
                    label = "EFFICIENT" if cir < 50 else "ACCEPTABLE" if cir < 70 else "INEFFICIENT"
                    st.markdown(
                        f"<div style='padding:14px;background:{color}22;"
                        f"border-left:6px solid {color};border-radius:10px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"COST-INCOME RATIO</div>"
                        f"<div style='font-size:28px;font-weight:800;color:{color}'>"
                        f"{cir:.2f}% — {label}</div></div>",
                        unsafe_allow_html=True)
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"Branch #90: CIR opex={opex_v}M inc={inc_v}M → {cir}%")

        with roaa_tab:
            st.markdown("**Return on Average Assets** = NPBT / Avg assets × 100")
            c1, c2 = st.columns(2)
            with c1:
                npbt_v = st.number_input("NPBT (KES M)",
                                           value=30.0, step=2.0, key="bp_roaa_npbt")
            with c2:
                aa_v = st.number_input("Average assets (KES M)",
                                         min_value=0.0, value=800.0, step=50.0,
                                         key="bp_roaa_aa")
            if st.button("Compute RoAA", key="bp_roaa_btn", type="primary"):
                roaa = BranchPerformanceEngine.return_on_avg_assets(
                    _D_bp(str(npbt_v)) * _D_bp("1000000"),
                    _D_bp(str(aa_v)) * _D_bp("1000000"))
                if roaa is None:
                    st.error("Could not compute (avg assets must be > 0).")
                else:
                    color = "#10B981" if roaa > 2 else "#F59E0B" if roaa > 0 else "#DC2626"
                    st.markdown(
                        f"<div style='padding:14px;background:{color}22;"
                        f"border-left:6px solid {color};border-radius:10px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"RoAA</div>"
                        f"<div style='font-size:28px;font-weight:800;color:{color}'>"
                        f"{roaa:.2f}%</div></div>",
                        unsafe_allow_html=True)
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"Branch #90: RoAA NPBT={npbt_v}M / AA={aa_v}M → {roaa}%")

    # ──────── Peer benchmarking ────────
    with bp_sub_tabs[3]:
        st.markdown(
            "**Peer Benchmarking** — compare branch performance against peer group")
        st.caption(
            f"Engine returns P25 / median / P75 for the peer set, plus quartile rank "
            f"for the target branch. TIER_1 ≥ {TIER_1_THRESHOLD_PCT}th percentile.")

        st.markdown("**Peer values** (e.g. NPBT or RoAA across peer branches):")
        peer_input = st.text_area(
            "Enter peer values (one per line, KES M)",
            value="20.0\n25.0\n28.0\n32.0\n35.0\n40.0\n42.0\n48.0\n50.0",
            height=100, key="bp_peer_input",
            help="Peers should be of similar lifecycle / location / size for valid comparison.")

        target_v = st.number_input("Target branch value (KES M)",
                                      value=48.0, step=1.0, key="bp_peer_target")

        if st.button("Run benchmarking",
                       key="bp_bench_btn", type="primary"):
            try:
                peers = [_D_bp(line.strip()) * _D_bp("1000000")
                          for line in peer_input.split("\n") if line.strip()]
            except Exception:
                st.error("Could not parse peer values — use one number per line.")
                peers = []

            if not peers:
                st.warning("Add at least one peer value.")
            else:
                bm = BranchPerformanceEngine.peer_benchmark_metrics(peers)
                qr = BranchPerformanceEngine.quartile_rank(
                    _D_bp(str(target_v)) * _D_bp("1000000"), peers)

                k1, k2, k3 = st.columns(3)
                k1.metric("Peer count", bm.get("n"))
                k2.metric("P25",
                           f"KES {_D_bp(str(bm['percentile_25']))/_D_bp('1000000'):.1f}M")
                k3.metric("Median",
                           f"KES {_D_bp(str(bm['median']))/_D_bp('1000000'):.1f}M")

                k1, k2 = st.columns(2)
                k1.metric("P75",
                           f"KES {_D_bp(str(bm['percentile_75']))/_D_bp('1000000'):.1f}M")
                tier = qr.get("tier")
                pct = qr.get("percentile")
                tier_colors = {"TIER_1": "#059669", "TIER_2": "#10B981",
                                "TIER_3": "#F59E0B", "TIER_4": "#DC2626"}
                color = tier_colors.get(tier, "#6B7280")
                with k2:
                    st.markdown(
                        f"<div style='padding:12px;background:{color}22;"
                        f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                        f"BRANCH RANK</div>"
                        f"<div style='font-size:22px;font-weight:800;color:{color}'>"
                        f"{tier} @ {pct}%ile</div></div>",
                        unsafe_allow_html=True)

                if tier == "TIER_1":
                    st.success(
                        f"🏅 **Top tier branch** — at or above {TIER_1_THRESHOLD_PCT}th "
                        "percentile vs peers. Strong performer.")
                elif tier == "TIER_4":
                    st.error(
                        "⚠ **Bottom tier** — branch in lowest quartile vs peers. "
                        "Performance review recommended.")
                audit_log("IFRS_ENGINE_USED", uname,
                           f"Branch #90: peer bench {target_v}M → {tier} @ {pct}%ile")


# ════════════════════════════════════════════════════════════════
# TAB 7 — BRANCH OPS EXCELLENCE (Standard #92, integrated v5.82)
# ════════════════════════════════════════════════════════════════
with tabs[6]:
    from utils.branch_ops_excellence import (
        BranchOpsExcellenceEngine, WaitTimeObservation,
        TransactionRecord, OpsIncident,
        TAT_TARGETS, ALLOWED_INCIDENT_TRANSITIONS, SCORE_WEIGHTS,
        CUSTOMER_WAIT_P50_TARGET_MIN, CUSTOMER_WAIT_P90_TARGET_MIN,
        CUSTOMER_WAIT_AMBER_P90_MIN,
        ERROR_RATE_GREEN_MAX, ERROR_RATE_AMBER_MAX,
        INCIDENT_SEVERITY_LEVELS, VALID_INCIDENT_STATUSES,
    )
    from datetime import datetime, timedelta
    from decimal import Decimal as _D_be

    st.markdown(
        f"**Standard #92 — Branch Operational Excellence Engine**. "
        f"Customer wait time, error rate, turnaround time per transaction type, "
        f"and incident transition state machine."
    )
    st.caption(
        f"Wait time targets: P50 ≤ {CUSTOMER_WAIT_P50_TARGET_MIN}min, "
        f"P90 ≤ {CUSTOMER_WAIT_P90_TARGET_MIN}min (RED above {CUSTOMER_WAIT_AMBER_P90_MIN}min P90). "
        f"Error rate bands: GREEN ≤ {ERROR_RATE_GREEN_MAX}% / AMBER ≤ {ERROR_RATE_AMBER_MAX}% / RED above. "
        f"TAT targets defined per-transaction-type ({len(TAT_TARGETS)} types)."
    )

    boe_sub_tabs = st.tabs([
        "⏱️ Customer Wait Time",
        "❌ Error Rate",
        "📅 Turnaround Time (TAT)",
        "🚨 Incident Workflow",
        "🌳 Engine Reference",
    ])

    # ──────── Customer Wait Time ────────
    with boe_sub_tabs[0]:
        st.markdown(
            f"**Customer Wait Time Analysis** (P50/P90 vs CBK retail SLA targets)")
        st.caption(
            f"Demo dataset — 30 observations across BR_100 (faster) and BR_200 (slower) "
            "to demonstrate severity bands. Production deployment would feed via "
            "`branch_wait_observations.json`.")

        # Demo dataset
        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_wait_obs():
            base = datetime(2026, 4, 30, 9, 0)
            obs = []
            for i in range(15):
                join = base + timedelta(minutes=i*3)
                start = join + timedelta(minutes=2 + i % 8)  # 2-9 min wait
                end = start + timedelta(minutes=5)
                obs.append(WaitTimeObservation(f"O{i}", "BR_100", f"C{i}",
                                                 join, start, end))
            for i in range(15):
                join = base + timedelta(minutes=i*3)
                start = join + timedelta(minutes=8 + i % 12)  # 8-19 min wait
                end = start + timedelta(minutes=5)
                obs.append(WaitTimeObservation(f"OB{i}", "BR_200", f"CB{i}",
                                                 join, start, end))
            return obs

        observations = _demo_wait_obs()

        if st.button("Compute wait time stats",
                       key="boe_wait_btn", type="primary"):
            r = BranchOpsExcellenceEngine.customer_wait_time(observations)
            severity = r.get("severity")
            colors = {"GREEN": "#10B981", "AMBER": "#F59E0B",
                      "RED": "#DC2626", None: "#6B7280"}
            color = colors.get(severity, "#6B7280")

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Observations", r.get("observations_count"))
            k2.metric("P50 (median)",
                       f"{r.get('p50_minutes')} min",
                       delta=f"target ≤ {CUSTOMER_WAIT_P50_TARGET_MIN} min")
            k3.metric("P90", f"{r.get('p90_minutes')} min",
                       delta=f"target ≤ {CUSTOMER_WAIT_P90_TARGET_MIN} min")
            with k4:
                st.markdown(
                    f"<div style='padding:8px 12px;background:{color}22;"
                    f"border-left:4px solid {color};border-radius:8px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"SEVERITY</div>"
                    f"<div style='font-size:20px;font-weight:800;color:{color}'>"
                    f"{severity}</div></div>", unsafe_allow_html=True)

            st.metric("Max wait observed",
                       f"{r.get('max_minutes')} min")
            excluded = r.get("observations_excluded", 0)
            if excluded > 0:
                st.warning(
                    f"⚠ {excluded} observation(s) excluded — missing service times "
                    "(Rule 6 transparency).")

            if severity == "RED":
                st.error(
                    f"⛔ Wait times exceed CBK retail SLA. Branch managers should "
                    "review queue management — staffing levels, peak-hour routing, "
                    "self-service options.")
            elif severity == "AMBER":
                st.warning(
                    "⚠ Wait times approach SLA limits. Monitor closely.")
            else:
                st.success("✅ Wait times within target.")
            audit_log("IFRS_ENGINE_USED", uname,
                       f"BranchOps #92: wait_time count={r['observations_count']} "
                       f"P50={r.get('p50_minutes')} P90={r.get('p90_minutes')} "
                       f"severity={severity}")

    # ──────── Error Rate ────────
    with boe_sub_tabs[1]:
        st.markdown(
            f"**Error Rate by Branch** — % of transactions flagged with errors")
        st.caption(
            f"Severity bands: GREEN ≤ {ERROR_RATE_GREEN_MAX}% · "
            f"AMBER ≤ {ERROR_RATE_AMBER_MAX}% · RED above {ERROR_RATE_AMBER_MAX}%. "
            "Demo dataset includes deliberately injected errors.")

        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_txns():
            base = datetime(2026, 4, 1)
            txns = []
            # BR_100 — 30 txns, 3 errors (10% — RED)
            for i in range(30):
                init = base + timedelta(days=i % 25)
                comp = init + timedelta(days=1)
                txns.append(TransactionRecord(
                    f"T_100_{i}", "BR_100", "ACCOUNT_OPENING",
                    init, comp,
                    has_error=(i % 10 < 3),  # 30% errors
                    business_days_elapsed=1 + (i % 4)))
            # BR_200 — 50 txns, 1 error (2% — AMBER)
            for i in range(50):
                init = base + timedelta(days=i % 25)
                comp = init + timedelta(days=1 + i % 3)
                txns.append(TransactionRecord(
                    f"T_200_{i}", "BR_200", "ACCOUNT_OPENING",
                    init, comp,
                    has_error=(i == 5),
                    business_days_elapsed=1 + i % 3))
            # BR_300 — 100 txns, 0 errors (GREEN)
            for i in range(100):
                init = base + timedelta(days=i % 25)
                comp = init + timedelta(days=1)
                txns.append(TransactionRecord(
                    f"T_300_{i}", "BR_300", "ACCOUNT_OPENING",
                    init, comp,
                    has_error=False,
                    business_days_elapsed=1))
            return txns

        all_txns = _demo_txns()

        if st.button("Compute error rates",
                       key="boe_err_btn", type="primary"):
            r = BranchOpsExcellenceEngine.error_rate_by_branch(all_txns)
            branches = r.get("branches", [])
            if branches:
                rows = []
                for br in branches:
                    sev = br.get("severity", "—")
                    sev_emoji = {"GREEN": "🟢", "AMBER": "🟡", "RED": "🔴"}.get(sev, "—")
                    rows.append({
                        "Branch": br.get("branch_id"),
                        "Transactions": br.get("transaction_count"),
                        "Errors": br.get("error_count"),
                        "Error rate %": br.get("error_rate_pct"),
                        "Severity": f"{sev_emoji} {sev}",
                    })
                st.dataframe(pd.DataFrame(rows),
                             use_container_width=True, hide_index=True)

                # Bar chart
                chart_data = pd.DataFrame({
                    "Error rate %": [b.get("error_rate_pct", 0) for b in branches]
                }, index=[b.get("branch_id") for b in branches])
                st.bar_chart(chart_data)
                audit_log("IFRS_ENGINE_USED", uname,
                           f"BranchOps #92: error rate {len(branches)} branches scanned")

    # ──────── Turnaround Time ────────
    with boe_sub_tabs[2]:
        st.markdown(
            f"**Turnaround Time (TAT)** per transaction type")
        st.caption(
            f"Engine binds {len(TAT_TARGETS)} TAT targets byte-for-byte: "
            "ACCOUNT_OPENING=1 day, LOAN_DISBURSEMENT=5 days, CARD_ISSUANCE=7 days, etc.")

        ttype = st.selectbox(
            "Transaction type",
            list(TAT_TARGETS.keys()),
            key="boe_tat_type")
        target_days = TAT_TARGETS[ttype]
        st.caption(f"**Target**: ≤ {target_days} business day{'s' if target_days != 1 else ''}")

        @st.cache_data(ttl=300, show_spinner=False)
        def _demo_tat_txns():
            base = datetime(2026, 4, 1)
            txns = []
            for ttype_x, target in TAT_TARGETS.items():
                for i in range(15):
                    init = base + timedelta(days=i)
                    # 60% within target, 40% slow
                    days_taken = (target if i < 9 else target * (2 + i % 3))
                    comp = init + timedelta(days=days_taken)
                    txns.append(TransactionRecord(
                        f"TAT_{ttype_x}_{i}", "BR_100", ttype_x,
                        init, comp,
                        business_days_elapsed=days_taken))
            return txns

        tat_txns = _demo_tat_txns()

        if st.button("Compute TAT stats",
                       key="boe_tat_btn", type="primary"):
            r = BranchOpsExcellenceEngine.turnaround_time(tat_txns, ttype)
            sla_pct = r.get("sla_compliant_pct", 0)
            sla_color = "#10B981" if sla_pct >= 90 else "#F59E0B" if sla_pct >= 70 else "#DC2626"

            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Completed", r.get("completed_count"))
            k2.metric("Median days", r.get("median_days"),
                       delta=f"target ≤ {target_days}")
            k3.metric("P90 days", r.get("p90_days"))
            with k4:
                st.markdown(
                    f"<div style='padding:8px 12px;background:{sla_color}22;"
                    f"border-left:4px solid {sla_color};border-radius:8px;text-align:center'>"
                    f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>"
                    f"SLA COMPLIANT</div>"
                    f"<div style='font-size:20px;font-weight:800;color:{sla_color}'>"
                    f"{sla_pct}%</div></div>", unsafe_allow_html=True)

            incomplete = r.get("incomplete_count", 0)
            if incomplete > 0:
                st.warning(
                    f"⚠ {incomplete} transaction(s) incomplete — excluded from TAT "
                    "(Rule 6 transparency).")

            sla_count = r.get("sla_compliant_count", 0)
            total = r.get("completed_count", 0)
            if sla_pct >= 90:
                st.success(
                    f"✅ Strong TAT compliance — {sla_count}/{total} within target.")
            elif sla_pct >= 70:
                st.warning(
                    f"⚠ Moderate TAT compliance — {sla_count}/{total} within target. "
                    "Process review recommended.")
            else:
                st.error(
                    f"⛔ Poor TAT compliance — only {sla_count}/{total} within target. "
                    "Operational improvement plan required.")
            audit_log("IFRS_ENGINE_USED", uname,
                       f"BranchOps #92: TAT {ttype} median={r.get('median_days')} "
                       f"sla_pct={sla_pct}")

    # ──────── Incident Workflow ────────
    with boe_sub_tabs[3]:
        st.markdown(
            f"**Incident Transition State Machine** — enforces valid status flow.")
        st.caption(
            f"States: {' / '.join(VALID_INCIDENT_STATUSES)}. "
            f"Severity levels: {' / '.join(INCIDENT_SEVERITY_LEVELS)}. "
            "RESOLVED is terminal — no transitions out. RESOLVED requires resolution_reason.")

        st.markdown("**Valid transitions:**")
        trans_rows = [
            {"From state": k,
              "Allowed to": ", ".join(v) if v else "(terminal)"}
            for k, v in ALLOWED_INCIDENT_TRANSITIONS.items()
        ]
        st.dataframe(pd.DataFrame(trans_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Test a transition:**")
        c1, c2, c3 = st.columns(3)
        with c1:
            inc_id = st.text_input("Incident ID", value="I_TEST", key="boe_inc_id")
            inc_branch = st.text_input("Branch ID", value="BR_100", key="boe_inc_br")
        with c2:
            inc_severity = st.selectbox("Severity",
                                          list(INCIDENT_SEVERITY_LEVELS),
                                          index=2, key="boe_inc_sev")
            inc_current = st.selectbox("Current status",
                                         list(VALID_INCIDENT_STATUSES),
                                         key="boe_inc_curr")
        with c3:
            inc_target = st.selectbox("Target status",
                                        list(VALID_INCIDENT_STATUSES),
                                        index=1, key="boe_inc_tgt")
            inc_reviewer = st.text_input("Reviewer ID",
                                            value=uname, key="boe_inc_rev")

        inc_reason = st.text_input(
            "Resolution reason (required for → RESOLVED)",
            value="" if inc_target != "RESOLVED" else "Cash variance reconciled",
            key="boe_inc_reason")

        if st.button("Test transition",
                       key="boe_inc_btn", type="primary"):
            inc = OpsIncident(
                incident_id=inc_id,
                branch_id=inc_branch,
                severity=inc_severity,
                description="Test incident",
                status=inc_current,
            )
            ok, msg = BranchOpsExcellenceEngine.transition_incident(
                inc, inc_target, inc_reviewer,
                resolution_reason=inc_reason if inc_reason.strip() else None)
            if ok:
                st.success(
                    f"✅ Transition allowed: **{inc_current} → {inc_target}**. "
                    f"Final status: `{inc.status}`. Engine confirmed: `{msg}`.")
                if inc.reviewer_id:
                    st.caption(f"Reviewer recorded: {inc.reviewer_id}")
            else:
                st.error(
                    f"⛔ Transition rejected: **{inc_current} → {inc_target}**. "
                    f"Reason: `{msg}`. Status unchanged.")
            audit_log("IFRS_ENGINE_USED", uname,
                       f"BranchOps #92: incident {inc_current}→{inc_target} "
                       f"ok={ok}")

    # ──────── Engine Reference ────────
    with boe_sub_tabs[4]:
        st.markdown("**Engine Constants Reference** (single source of truth)")

        st.markdown("**Wait time targets:**")
        wait_rows = [
            {"Metric": "P50 (median wait)", "Target": f"≤ {CUSTOMER_WAIT_P50_TARGET_MIN} min", "Source": "CUSTOMER_WAIT_P50_TARGET_MIN"},
            {"Metric": "P90 (95% of customers)", "Target": f"≤ {CUSTOMER_WAIT_P90_TARGET_MIN} min", "Source": "CUSTOMER_WAIT_P90_TARGET_MIN"},
            {"Metric": "P90 AMBER threshold", "Target": f"≤ {CUSTOMER_WAIT_AMBER_P90_MIN} min", "Source": "CUSTOMER_WAIT_AMBER_P90_MIN"},
        ]
        st.dataframe(pd.DataFrame(wait_rows),
                     use_container_width=True, hide_index=True)

        st.markdown("**Error rate severity bands:**")
        err_rows = [
            {"Band": "🟢 GREEN", "Range": f"≤ {ERROR_RATE_GREEN_MAX}%"},
            {"Band": "🟡 AMBER", "Range": f"≤ {ERROR_RATE_AMBER_MAX}%"},
            {"Band": "🔴 RED", "Range": f"> {ERROR_RATE_AMBER_MAX}%"},
        ]
        st.dataframe(pd.DataFrame(err_rows),
                     use_container_width=True, hide_index=True)

        st.markdown(f"**TAT targets** ({len(TAT_TARGETS)} transaction types):")
        tat_rows = [
            {"Transaction type": t, "Target (business days)": d}
            for t, d in TAT_TARGETS.items()
        ]
        st.dataframe(pd.DataFrame(tat_rows),
                     use_container_width=True, hide_index=True)

        st.markdown(f"**Score weights** (composite operational score):")
        sw_rows = [
            {"Component": k, "Weight (%)": v}
            for k, v in SCORE_WEIGHTS.items()
        ]
        st.dataframe(pd.DataFrame(sw_rows),
                     use_container_width=True, hide_index=True)
        st.caption(
            f"Note: composite score weights sum to {sum(SCORE_WEIGHTS.values())} — "
            "engine constant. The composite score itself is computed by the higher-level "
            "BSC engine, not exposed in this tab.")
