"""pages/43_pip.py — Performance Improvement Plan (PIP).
Structured workflow for staff with BSC below 2.5.
Targets, check-ins, HR tracking, outcome recording.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import Counter
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

require_access("people_hr.pip")

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update — called after every save action."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
sc   = str(ud.get("staff_code",""))
is_admin = ud.get("is_admin",False)
is_hr    = any(x in role.lower() for x in ("human resource","hr","training","chief human","manager"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>📈 Performance Improvement Plans</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "BSC below 2.5 · Structured support · HR tracking · Outcomes</span></div>",
    unsafe_allow_html=True)

st.info("PIP is a structured performance support programme. It is not punitive — it provides a defined plan with targets, support resources, and regular check-ins to help staff improve.")

@st.cache_data(ttl=30)
def _load():
    p = DATA/"pip_cases.json"
    return a2z_db.load_json(p) if p.exists() else []

pips = _load()
status_ct = Counter(p["status"] for p in pips)

m1,m2,m3,m4 = st.columns(4)
m1.metric("Active PIPs",      status_ct.get("Active",0))
m2.metric("Completed - Improved",status_ct.get("Completed - Improved",0))
m3.metric("Extended",         status_ct.get("Extended",0))
m4.metric("Total PIPs",       len(pips))

tabs = st.tabs(["📋 Active PIPs","✅ Completed","➕ Initiate PIP","📊 Analytics","⚡ Efficiency Insights"])

def _render_pips(pip_list):
    if not pip_list:
        st.success("No PIPs in this category."); return
    for p in sorted(pip_list, key=lambda x:x["bsc_score"]):
        days_remaining = (date.fromisoformat(p["end_date"][:10])-today).days if p.get("end_date") else 0
        clr = "#DC2626" if p["bsc_score"]<2.0 else "#D97706"
        with st.expander(f"📋 {p['id']} — {p['staff_name']} · BSC {p['bsc_score']:.2f} · {p['status']}"):
            c1,c2 = st.columns(2)
            c1.markdown(f"**Role:** {p['role'][:35]}")
            c1.markdown(f"**Unit:** {p.get('unit','')[:25]}")
            c1.markdown(f"**BSC Score:** {p['bsc_score']:.2f}/5.0")
            c1.markdown(f"**Start:** {p['start_date'][:10]} · **End:** {p['end_date'][:10]}")
            c1.markdown(f"**HR Manager:** {p.get('hr_manager','')[:25]}")
            c2.markdown("**Improvement targets:**")
            for t in p.get("improvement_targets",[]): c2.markdown(f"  • {t}")
            c2.markdown(f"**Next review:** {p.get('review_date','')[:10]}")
            if days_remaining > 0:
                c2.metric("Days remaining", days_remaining,
                           delta_color="normal" if days_remaining>14 else "inverse")
            if (is_hr or is_admin) and p["status"]=="Active":
                new_notes = st.text_input("Check-in notes",key=f"pip_note_{p['id']}")
                new_status= st.selectbox("Update status",
                    ["Active","Completed - Improved","Extended","Terminated"],
                    index=["Active","Completed - Improved","Extended","Terminated"].index(p["status"]),
                    key=f"pip_stat_{p['id']}")
                if st.button("💾 Save",key=f"pip_save_{p['id']}",type="primary"):
                    all_p = json.loads((DATA/"pip_cases.json").read_text())
                    for pip in all_p:
                        if pip["id"]==p["id"]:
                            pip["status"]=new_status
                            if new_notes: pip["notes"]=new_notes
                    (DATA/"pip_cases.json").write_text(json.dumps(all_p,indent=2))
                    audit_log("PIP_UPDATED",uname,f"{p['id']} → {new_status}")
                    _bsc_trigger(uname, "K016")
                    st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

with tabs[0]: _render_pips([p for p in pips if p["status"]=="Active"])
with tabs[1]: _render_pips([p for p in pips if "Completed" in p["status"]])
with tabs[2]:
    if is_hr or is_admin:
        st.markdown("**Initiate a PIP for a staff member with BSC below 2.5:**")
        scores = json.loads((DATA/"feb_2026_staff_scores.json").read_text()) if (DATA/"feb_2026_staff_scores.json").exists() else {}
        eligible = [(sc_v,v) for sc_v,v in scores.items() if v["final_score"]<2.5]
        if eligible:
            sel_staff = st.selectbox("Select staff member",
                [f"{v['name']} — {v['role'][:25]} — BSC {v['final_score']:.2f}" for _,v in eligible],
                key="pip_init_sel")
            idx = [f"{v['name']} — {v['role'][:25]} — BSC {v['final_score']:.2f}" for _,v in eligible].index(sel_staff)
            sel_sc, sel_v = eligible[idx]
            targets = st.text_area("Improvement targets (one per line)",
                value="Achieve BSC score ≥ 3.0 within 90 days\nComplete all mandatory CBK training\nZero unresolved customer complaints",
                height=100, key="pip_targets")
            review_date = st.date_input("First review date", value=today+__import__("datetime").timedelta(days=30), key="pip_rev")
            end_date    = st.date_input("PIP end date", value=today+__import__("datetime").timedelta(days=90), key="pip_end")
            if st.button("📋 Initiate PIP",key="pip_create",type="primary"):
                all_p = json.loads((DATA/"pip_cases.json").read_text())
                new_id= f"PIP{len(all_p)+1:04d}"
                all_p.append({"id":new_id,"staff_code":sel_sc,"staff_name":sel_v["name"],
                    "role":sel_v["role"],"unit":sel_v.get("unit",""),
                    "bsc_score":sel_v["final_score"],"start_date":str(today),
                    "review_date":str(review_date),"end_date":str(end_date),
                    "status":"Active","improvement_targets":[t.strip() for t in targets.split("\n") if t.strip()],
                    "hr_manager":name,"supervisor_name":"","notes":"",
                    "check_in_dates":[str(review_date),str(end_date)]})
                (DATA/"pip_cases.json").write_text(json.dumps(all_p,indent=2))
                audit_log("PIP_INITIATED",uname,f"{new_id} for {sel_v['name']}")
                _bsc_trigger(uname, "K016")
                st.cache_data.clear(); st.success(f"✅ PIP {new_id} initiated"); st.rerun()
        else:
            st.success("✅ No staff currently with BSC below 2.5.")
    else:
        st.info("PIP initiation available to HR and Admin.")
with tabs[3]:
    if pips:
        outcome_ct = Counter(p["status"] for p in pips)
        st.markdown("**PIP outcomes:**")
        for s,n in outcome_ct.most_common():
            st.markdown(f"  {s}: {n}")


# ════════════════════════════════════════════════════════════════════
# v10.440 — Wire Std #18 EfficiencyEngine into PIP
# ════════════════════════════════════════════════════════════════════

with tabs[4]:
    st.markdown("**⚡ Efficiency Insights — Per-KPI efficiency vs peer average**")
    st.caption(
        "Efficiency = KPI achievement per minute of micro-task time. "
        "Higher = more output per unit of effort. Std #18 "
        "(EfficiencyEngine). Used to inform PIP improvement targets."
    )
    try:
        from utils.efficiency import EfficiencyEngine
    except Exception as exc:  # noqa: BLE001
        st.error(f"Efficiency engine unavailable: {exc}")
    else:
        # Period selector
        from datetime import datetime as _dt
        now = _dt.now()
        period_options = [
            now.strftime("%Y-%m"),                           # current month
            (now.replace(day=1) - timedelta(days=1)).strftime("%Y-%m"),  # last month
            f"{now.year}-Q{(now.month - 1) // 3 + 1}",       # current quarter
        ]
        col1, col2 = st.columns([2, 3])
        sel_period = col1.selectbox(
            "Period", period_options, key="pip_eff_period",
        )

        # Staff selector: HR/Admin pick any; staff sees self
        if is_hr or is_admin:
            # List PIP staff for convenience
            active_pip_codes = [
                p.get("staff_code", "") for p in pips
                if p.get("status") == "Active"
            ]
            options = [sc] + sorted(set(active_pip_codes) - {sc})
            sel_staff = col2.selectbox(
                "Staff code", options, key="pip_eff_staff",
                help="Defaults to you; HR can review PIP staff",
            )
        else:
            sel_staff = sc
            col2.write(f"Showing your scores: **{sc}**")

        if st.button("Calculate efficiency", key="pip_eff_calc"):
            try:
                engine = EfficiencyEngine()
                scores = engine.calculate_efficiency_scores(
                    staff_code=str(sel_staff), period=sel_period,
                )
                if not scores:
                    st.info(
                        f"No efficiency data for {sel_staff} in {sel_period}. "
                        "Need both BSC outputs and completed micro-tasks "
                        "for that period."
                    )
                else:
                    personal = scores.get("personal_efficiency", {}) or {}
                    vs_peer = scores.get("vs_peer_average", {}) or {}
                    meta = scores.get("meta", {}) or {}

                    # Summary
                    if personal:
                        n_kpis = len(personal)
                        st.metric("KPIs measured", n_kpis)

                        rows = []
                        for kpi_id, eff_per_min in personal.items():
                            ratio = vs_peer.get(kpi_id)
                            ratio_str = (
                                f"{ratio:.2f}x" if ratio is not None
                                else "no peers"
                            )
                            status = (
                                "🟢 Above peers" if ratio and ratio > 1.0
                                else "🟡 Near peers" if ratio and ratio > 0.8
                                else "🔴 Below peers" if ratio is not None
                                else "—"
                            )
                            rows.append({
                                "KPI": kpi_id,
                                "Efficiency (per min)": round(eff_per_min, 4),
                                "vs Peer Average": ratio_str,
                                "Status": status,
                            })
                        st.dataframe(pd.DataFrame(rows),
                                    use_container_width=True, hide_index=True)

                        # Below-peer flag for PIP improvement
                        below_peer = [
                            r for r in rows
                            if "Below" in r["Status"]
                        ]
                        if below_peer:
                            st.warning(
                                f"⚠️ {len(below_peer)} KPI(s) below peer average — "
                                f"candidates for PIP improvement targets."
                            )
                    else:
                        st.info("No personal_efficiency computed for this period.")

                    if meta:
                        with st.expander("Method & traceability"):
                            st.json(meta)
            except Exception as exc:  # noqa: BLE001
                st.error(f"Calculation failed: {exc}")
