"""pages/17_campaigns.py — Campaign Management Module."""
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

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()


require_access("campaigns")


um, ud, uname, em, ri_pm, prod_m, pm, lm, hr_m, casc, vm, rlm = load_shared_state()
staff_scores = st.session_state.get("staff_scores", pd.DataFrame())
df_proc      = st.session_state.get("df_processed", pd.DataFrame())

CAMPAIGN_TYPES = [
    "Deposit Mobilisation","Loan Push","Account Opening Drive","DFS Activation",
    "Dormancy Reactivation","Bancassurance Drive","Digital Onboarding",
    "Customer Retention","Trade Finance Push","Cross-sell Campaign","NPS Drive",
]
CAMPAIGN_STATUS = ["Planning","Active","Paused","Completed","Cancelled"]
CAMPAIGN_TARGETS = ["All Branches","Selected Branches","Head Office Teams",
                    "DSO Network Only","Branch Managers","All Staff"]
KPI_MAP = {
    "Deposit Mobilisation":   "Deposit Growth",
    "Loan Push":              "Loans Disbursement",
    "Account Opening Drive":  "New Customer Acquisition",
    "DFS Activation":         "DFS Revenue",
    "Dormancy Reactivation":  "Dormancy Reactivation",
    "Bancassurance Drive":    "Bancassurance",
    "Digital Onboarding":     "Digital Acquiring",
    "Customer Retention":     "CX Score",
    "Trade Finance Push":     "Trade Finance",
    "Cross-sell Campaign":    "Fees and Commission",
    "NPS Drive":              "NPS Score",
}

class CampaignManager:
    def __init__(self):
        self.file      = DATA_DIR / "campaigns.json"
        self.campaigns = self._load()

    def _load(self):
        if not self.file.exists(): self.file.write_text("[]")
        try:
            raw = self.file.read_text()
            d = json.loads(raw) if raw.strip() else []
            return d if isinstance(d, list) else []
        except: return []

    def _save(self):
        self.a2z_db.save_json(file, self.campaigns)

    def create(self, data: dict) -> dict:
        camp_id = f"CAMP{len(self.campaigns)+1:04d}"
        rec = {
            "id":              camp_id,
            "name":            data.get("name",""),
            "type":            data.get("type",""),
            "description":     data.get("description",""),
            "kpi_linked":      KPI_MAP.get(data.get("type",""),""),
            "target_audience": data.get("target_audience",""),
            "target_branches": data.get("target_branches",[]),
            "start_date":      str(data.get("start_date", date.today())),
            "end_date":        str(data.get("end_date", date.today()+timedelta(days=30))),
            "financial_target":data.get("financial_target", 0),
            "unit_target":     data.get("unit_target", 0),
            "incentive":       data.get("incentive",""),
            "incentive_amount":data.get("incentive_amount", 0),
            "status":          "Planning",
            "milestones":      [],
            "progress_logs":   [],
            "created_by":      data.get("created_by",""),
            "created_at":      datetime.now().isoformat(),
        }
        self.campaigns.append(rec)
        self._save()
        return rec

    def update_status(self, camp_id: str, status: str, note: str, by: str):
        for c in self.campaigns:
            if c["id"] == camp_id:
                c["status"] = status
                c.get('milestones', []).append({
                    "status": status, "note": note,
                    "by": by, "at": datetime.now().isoformat()})
                self._save()
                return c
        return None

    def log_progress(self, camp_id: str, unit: str, actual: float,
                     note: str, logged_by: str):
        for c in self.campaigns:
            if c["id"] == camp_id:
                c.get('progress_logs', []).append({
                    "unit": unit, "actual": actual,
                    "note": note, "logged_by": logged_by,
                    "logged_at": datetime.now().isoformat(),
                    "date": str(date.today()),
                })
                self._save()
                return c
        return None

    def get_active(self):
        today = str(date.today())
        return [c for c in self.campaigns
                if c["status"]=="Active"
                and c.get("start_date","")<=today<=c.get("end_date","9999-12-31")]

    def campaign_progress(self, camp_id: str):
        c = next((x for x in self.campaigns if x["id"]==camp_id), None)
        if not c: return 0, 0, 0
        logs  = c.get("progress_logs",[])
        total = sum(float(l.get("actual",0)) for l in logs)
        target= float(c.get("financial_target",0) or c.get("unit_target",0))
        pct   = round(total/target*100,1) if target else 0
        return total, target, pct

if "campaign_manager" not in st.session_state:
    st.session_state["campaign_manager"] = CampaignManager()
cpm = st.session_state.get("campaign_manager")
if cpm is None: st.info("Campaign data loading..."); st.stop()



st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚀 Campaigns</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Marketing drives · Conversion · ROI</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚀 Campaigns</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Marketing · Conversion tracking</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚀 Campaigns</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Marketing drives · Conversion · ROI</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚀 Campaigns</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Marketing drives · Conversion tracking · ROI</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🚀 Campaigns</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Marketing drives · Conversion · ROI</span></div>",
    unsafe_allow_html=True)


st.markdown(
    "<div style=\'padding:16px 22px;background:#D35400;border-radius:12px;margin-bottom:20px;box-shadow:0 2px 12px rgba(0,0,0,0.15)\'><div style=\'display:flex;align-items:center;justify-content:space-between\'><div><div style=\'color:var(--color-background-primary);font-size:16px;font-weight:700;letter-spacing:-0.2px\'>Campaign Management</div><div style=\'color:rgba(255,255,255,0.65);font-size:11px;margin-top:3px;font-weight:400\'>Design · Launch · Track · Measure · Close campaigns that drive KPI uplift</div></div><div style=\'opacity:0.12;font-size:36px;line-height:1;color:white\'>◆</div></div></div>",
    unsafe_allow_html=True)

tabs = st.tabs([
    "📊 Dashboard",
    "➕ Create campaign",
    "📈 Track progress",
    "🏆 Campaign leaderboard",
    "📋 All campaigns",
])

# ════════════════════════════════════════════════════════════════
# TAB 1 — DASHBOARD
# ════════════════════════════════════════════════════════════════
with tabs[0]:
    active = cpm.get_active()
    all_c  = cpm.campaigns
    completed = [c for c in all_c if c["status"]=="Completed"]

    dc1,dc2,dc3,dc4 = st.columns(4)
    dc1.metric("Total campaigns", len(all_c))
    dc2.metric("Active now",      len(active),
               delta=f"{len(active)}" if active else "0")
    dc3.metric("Completed",       len(completed))
    dc4.metric("Planning",        len([c for c in all_c if c["status"]=="Planning"]))

    if active:
        st.markdown("### 🟢 Active campaigns")
        for c in active:
            total, target, pct = cpm.campaign_progress(c["id"])
            days_left = (_safe_date(c["end_date"]) - date.today()).days
            clr = 'var(--brand-primary,#006B3F)' if pct>=80 else ('#F5A623' if pct>=50 else '#E24B4A')

            st.markdown(
                f"<div style='padding:12px 16px;background:var(--color-background-secondary);"
                f"border-left:5px solid {clr};"
                f"border-radius:0 8px 8px 0;margin:6px 0'>"
                f"<div style='display:flex;justify-content:space-between'>"
                f"<div><b style='font-size:14px'>{c['name']}</b> "
                f"<span style='background:#D35400;color:var(--color-background-primary);padding:1px 6px;"
                f"border-radius:8px;font-size:10px'>{c['type']}</span></div>"
                f"<span style='color:{clr};font-weight:600'>{pct:.0f}% of target</span></div>"
                f"<div style='margin:6px 0 4px 0;height:6px;background:#EEE;border-radius:3px'>"
                f"<div style='width:{min(pct,100):.0f}%;height:100%;background:{clr};border-radius:3px'></div></div>"
                f"<div style='display:flex;gap:20px;font-size:11px;color:#666'>"
                f"<span>KPI: <b>{c.get('kpi_linked', "")}</b></span>"
                f"<span>Actual: <b>{fmt_num(total,True)}</b></span>"
                f"<span>Target: <b>{fmt_num(target,True)}</b></span>"
                f"<span>Days left: <b>{days_left}</b></span>"
                f"<span>Audience: <b>{c.get('target_audience', "")}</b></span>"
                f"</div></div>", unsafe_allow_html=True)
    else:
        st.info("No active campaigns. Create one in the 'Create campaign' tab.")

    if completed:
        st.markdown("### Campaign outcomes")
        outcome_rows = []
        for c in completed:
            total, target, pct = cpm.campaign_progress(c["id"])
            outcome_rows.append({
                "Campaign": c["name"], "Type": c["type"],
                "Target": fmt_num(target, True),
                "Achieved": fmt_num(total, True),
                "Achievement": f"{pct:.1f}%",
                "Result": "✅ Hit" if pct>=90 else ("⚠️ Partial" if pct>=60 else "❌ Missed"),
            })
        if outcome_rows:
            out_df = pd.DataFrame(outcome_rows)
            def hl_result(v):
                if '✅' in str(v): return 'color:var(--brand-primary,#006B3F);font-weight:500'
                if '⚠️' in str(v): return 'color:#F5A623'
                return 'color:#E24B4A'
            st.dataframe(out_df.style.map(hl_result, subset=['Result']),
                         use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════════════
# TAB 2 — CREATE CAMPAIGN
# ════════════════════════════════════════════════════════════════
with tabs[1]:
    st.subheader("Create new campaign")

    all_units_c = sorted(staff_scores["Unit"].unique().tolist()) if len(staff_scores) else []

    with st.form("create_camp_form"):
        cc1, cc2 = st.columns(2)
        camp_name = cc1.text_input("Campaign name *",
            placeholder="e.g. Q2 Deposit Drive 2026")
        camp_type = cc2.selectbox("Campaign type *", CAMPAIGN_TYPES)

        linked_kpi = KPI_MAP.get(camp_type,"")
        if linked_kpi:
            st.markdown(
                f"<div style='padding:5px 10px;background:#FEF6E4;"
                f"border-left:3px solid #D35400;font-size:11px'>"
                f"Linked KPI: <b>{linked_kpi}</b> — performance on this campaign "
                f"feeds into each participant's Campaign Conversion Rate KPI</div>",
                unsafe_allow_html=True)

        camp_desc = st.text_area("Campaign description / objectives", height=60)

        cc3, cc4 = st.columns(2)
        start_dt = cc3.date_input("Start date", value=date.today())
        end_dt   = cc4.date_input("End date",   value=date.today()+timedelta(days=30))

        cc5, cc6 = st.columns(2)
        audience  = cc5.selectbox("Target audience", CAMPAIGN_TARGETS)
        fin_target= cc6.number_input("Financial target (KES)", min_value=0.0,
                                      value=0.0, step=1_000_000.0, format="%.0f")

        cc7, cc8 = st.columns(2)
        unit_target = cc7.number_input("Unit target (customers/accounts/units)",
                                        min_value=0, value=0, step=10)
        incentive_amt = cc8.number_input("Incentive amount per staff (KES)",
                                          min_value=0, value=0, step=500)

        target_branches = st.multiselect("Target branches (leave blank for all)",
                                          all_units_c, key="camp_branches")
        incentive_desc  = st.text_input("Incentive description",
            placeholder="e.g. Top performer wins KES 5,000 airtime voucher")

        if st.form_submit_button("🚀 Create campaign", type="primary"):
            if camp_name and camp_type and end_dt > start_dt:
                c = cpm.create({
                    "name": camp_name, "type": camp_type,
                    "description": camp_desc,
                    "target_audience": audience,
                    "target_branches": target_branches or all_units_c,
                    "start_date": start_dt, "end_date": end_dt,
                    "financial_target": fin_target,
                    "unit_target": unit_target,
                    "incentive": incentive_desc,
                    "incentive_amount": incentive_amt,
                    "created_by": uname,
                })
                audit_log("CAMPAIGN_CREATED", uname, f"{c['id']}:{camp_name}")
                st.success(f"✅ Campaign **{c['id']}** created: {camp_name}")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("Name, type and valid date range are required.")

# ════════════════════════════════════════════════════════════════
# TAB 3 — TRACK PROGRESS
# ════════════════════════════════════════════════════════════════
with tabs[2]:
    st.subheader("Track campaign progress")

    if not cpm.campaigns:
        st.info("No campaigns yet.")
    else:
        camp_opts = {f"{c['id']} — {c['name']} [{c['status']}]": c["id"]
                     for c in cpm.campaigns}
        sel_camp_lbl = st.selectbox("Select campaign", list(camp_opts.keys()), key="tc_camp")
        sel_camp_id  = camp_opts[sel_camp_lbl]
        camp = next((c for c in cpm.campaigns if c["id"]==sel_camp_id), None)

        if camp:
            total, target, pct = cpm.campaign_progress(camp["id"])
            days_rem = (_safe_date(camp["end_date"]) - date.today()).days
            clr = 'var(--brand-primary,#006B3F)' if pct>=80 else ('#F5A623' if pct>=50 else '#E24B4A')

            tc1,tc2,tc3,tc4 = st.columns(4)
            tc1.metric("Status",      camp["status"])
            tc2.metric("Progress",    f"{pct:.1f}%")
            tc3.metric("Achieved",    fmt_num(total, True))
            tc4.metric("Days remaining", days_rem,
                       delta_color="inverse" if days_rem<7 else "normal")

            st.progress(min(pct/100,1.0), text=f"{pct:.0f}% of {fmt_num(target,True)} target")

            # Status controls
            st.markdown("**Update status:**")
            sc1, sc2, sc3 = st.columns(3)
            if camp["status"] == "Planning" and sc1.button("🟢 Launch", type="primary"):
                cpm.update_status(camp["id"], "Active", "Campaign launched", uname)
                st.cache_data.clear()
                st.rerun()
            if camp["status"] == "Active" and sc2.button("⏸ Pause"):
                cpm.update_status(camp["id"], "Paused", "Campaign paused", uname)
                st.cache_data.clear()
                st.rerun()
            if camp["status"] in ("Active","Paused") and sc3.button("✅ Complete"):
                cpm.update_status(camp["id"], "Completed", "Campaign completed", uname)
                st.cache_data.clear()
                st.rerun()

            # Log progress
            st.markdown("---")
            st.markdown("**Log branch progress:**")
            unit_list = camp.get("target_branches",[]) or all_units_c
            with st.form(f"log_prog_{camp['id']}"):
                lp1, lp2 = st.columns(2)
                log_unit   = lp1.selectbox("Branch/unit", unit_list or ["All"])
                log_actual = lp2.number_input("Actual achieved", min_value=0.0,
                                               step=100000.0, format="%.0f")
                log_note   = st.text_input("Note")
                if st.form_submit_button("Log progress", type="primary"):
                    cpm.log_progress(camp["id"], log_unit, log_actual, log_note, uname)
                    st.success("Progress logged.")
                    st.cache_data.clear()
                    st.rerun()

            # Progress by branch
            if camp.get("progress_logs", []):
                st.markdown("**Progress by branch:**")
                by_unit = {}
                for l in camp.get("progress_logs", []):
                    u = l["unit"]
                    by_unit[u] = by_unit.get(u,0) + float(l.get("actual",0))
                unit_prog = pd.DataFrame(
                    [{"Branch":u,"Actual":v} for u,v in by_unit.items()]
                ).sort_values("Actual", ascending=False)
                fig_up = px.bar(unit_prog, x="Branch", y="Actual",
                                 color="Actual",
                                 color_continuous_scale=["#FEF6E4","#D35400"],
                                 title="Progress by branch")
                fig_up.update_layout(height=280, xaxis_tickangle=-30,
                    plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig_up, use_container_width=True)

# ════════════════════════════════════════════════════════════════
# TAB 4 — CAMPAIGN LEADERBOARD
# ════════════════════════════════════════════════════════════════
with tabs[3]:
    st.subheader("Campaign leaderboard")
    active_c = cpm.get_active()

    if not active_c:
        st.info("No active campaigns. Launch a campaign to see the leaderboard.")
    else:
        sel_active_lbl = st.selectbox("Campaign",
            [f"{c['id']} — {c['name']}" for c in active_c], key="lb_camp")
        sel_active_id  = sel_active_lbl.split(" — ")[0]
        camp = next((c for c in active_c if c["id"]==sel_active_id), None)

        if camp and camp.get("progress_logs", []):
            by_unit = {}
            for l in camp.get("progress_logs", []):
                u = l["unit"]
                by_unit[u] = by_unit.get(u,0) + float(l.get("actual",0))

            lb = pd.DataFrame([{"Branch":u,"Total":v}
                                for u,v in by_unit.items()]).sort_values("Total",ascending=False)
            lb["Rank"] = range(1, len(lb)+1)
            target = float(camp.get("financial_target",0) or camp.get("unit_target",0))
            lb["%  of target"] = lb["Total"].apply(
                lambda x: f"{x/target*100:.1f}%" if target else "—")

            # Visual
            for _, row in lb.iterrows():
                pct_v = float(row["% of target"].replace('%','')) if '%' in str(row.get("% of target","")) else 0
                bar_w = min(int(lb["Total"].max() and row["Total"]/lb["Total"].max()*100), 100)
                medal = "🥇" if row["Rank"]==1 else ("🥈" if row["Rank"]==2 else ("🥉" if row["Rank"]==3 else f"#{row['Rank']}"))
                clr   = "#FFD700" if row["Rank"]==1 else ("#C0C0C0" if row["Rank"]==2 else ("#CD7F32" if row["Rank"]==3 else "#D35400"))

                st.markdown(
                    f"<div style='padding:8px 14px;background:var(--color-background-secondary);"
                    f"border-left:4px solid {clr};border-radius:0 6px 6px 0;margin:3px 0'>"
                    f"<div style='display:flex;justify-content:space-between'>"
                    f"<span><b>{medal} {row['Branch']}</b></span>"
                    f"<span style='color:{clr};font-weight:600'>{fmt_num(row['Total'],True)}</span></div>"
                    f"<div style='margin-top:4px;height:4px;background:#EEE;border-radius:2px'>"
                    f"<div style='width:{bar_w}%;height:100%;background:{clr};border-radius:2px'></div>"
                    f"</div></div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════
# TAB 5 — ALL CAMPAIGNS
# ════════════════════════════════════════════════════════════════
with tabs[4]:
    st.subheader("All campaigns")
    if not cpm.campaigns:
        st.info("No campaigns created yet.")
    else:
        status_filter = st.multiselect("Filter by status", CAMPAIGN_STATUS,
                                        default=CAMPAIGN_STATUS, key="ac_status")
        filtered_camps = [c for c in cpm.campaigns if c["status"] in status_filter]

        all_rows = []
        for c in filtered_camps:
            total, target, pct = cpm.campaign_progress(c["id"])
            all_rows.append({
                "ID":          c["id"],
                "Name":        c["name"],
                "Type":        c["type"],
                "Status":      c["status"],
                "Start":       c["start_date"],
                "End":         c["end_date"],
                "Target":      fmt_num(target, True),
                "Achieved":    fmt_num(total, True),
                "Progress":    f"{pct:.1f}%",
                "KPI":         c.get("kpi_linked",""),
                "Created by":  c.get("created_by",""),
            })

        if all_rows:
            all_df = pd.DataFrame(all_rows)
            def hl_status(v):
                if v=="Active":    return 'color:var(--brand-primary,#006B3F);font-weight:500'
                if v=="Completed": return 'color:#185FA5'
                if v=="Cancelled": return 'color:#E24B4A'
                return ''
            st.dataframe(all_df.style.map(hl_status, subset=['Status']),
                         use_container_width=True, hide_index=True)
