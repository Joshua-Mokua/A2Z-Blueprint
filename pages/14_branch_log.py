"""pages/14_branch_log.py — Daily Branch Log: staff reporting + manager validation."""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
from utils.core import *
from pages._shared import load_shared_state
from pages._access import require_access, get_my_scope
require_access("branch_log")





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
        self.file.write_text(json.dumps(self.logs, indent=2, default=str))

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
