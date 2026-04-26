"""pages/26_legal.py — Legal Module: matter tracking, SLA, attorney pipeline, BSC."""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict, Counter
from pages._shared import load_shared_state, get_user_proposition
from pages._access import require_access
from utils.core import audit_log, requires_dual_approval, submit_for_approval

require_access("legal")

def _bsc_trigger(username: str, kpi: str = ""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

DATA = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()

@st.cache_data(ttl=60, show_spinner=False)
def _load():
    f = DATA / "legal_matters.json"
    return a2z_db.load_json(f) if f.exists() else []

@st.cache_data(ttl=300, show_spinner=False)
def _cfg():
    f = DATA / "lms_config.json"
    return a2z_db.load_json(f) if f.exists() else {}

matters = _load()
cfg     = _cfg()
role    = ud.get("role","")
sc      = str(ud.get("staff_code","") or "")
is_admin   = ud.get("is_admin",False)
is_legal   = any(x in role for x in ("Legal","Company Secretary","Compliance",
                                       "Attorney","Paralegal","Chief Legal"))
is_mgr     = any(x in role for x in ("Manager","Director","Chief","Head"))

visible = matters if (is_admin or is_legal or is_mgr) else [
    m for m in matters if m.get("legal_officer",{}).get("code","") == sc]

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


today = date.today()

# ── Header ─────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>⚖️ Legal</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Matter tracking · SLA management · Attorney pipeline · BSC feed</span></div>",
    unsafe_allow_html=True)

# ── KPI strip ──────────────────────────────────────────────────────
total    = len(visible)
open_n   = sum(1 for m in visible if m["status"] not in ("completed","on_hold"))
overdue  = sum(1 for m in visible if m["sla_breached"] and m["status"] != "completed")
completed= sum(1 for m in visible if m["status"] == "completed")
on_track = open_n - overdue
attorneys= sum(1 for m in visible if m.get("attorney"))

# SLA compliance rate
decided  = [m for m in visible if m["status"] in ("completed",)]
sla_ok   = sum(1 for m in decided if not m["sla_breached"])
sla_rate = round(sla_ok/len(decided)*100,1) if decided else 0

k1,k2,k3,k4,k5,k6 = st.columns(6)
for col,lbl,val,color in [
    (k1,"Open",       str(open_n),   "#1E40AF"),
    (k2,"Overdue",    str(overdue),  "#DC2626"),
    (k3,"On Track",   str(on_track), "#16A34A"),
    (k4,"Completed",  str(completed),"#6B7280"),
    (k5,"External Att.",str(attorneys),"#7C3AED"),
    (k6,"SLA Rate",   f"{sla_rate}%","#0369A1"),
]:
    col.markdown(
        f"<div style='background:var(--color-background-secondary);border:0.5px solid "
        f"var(--color-border-tertiary);border-radius:10px;padding:12px;text-align:center'>"
        f"<div style='font-size:11px;color:var(--color-text-secondary);font-weight:600;"
        f"text-transform:uppercase'>{lbl}</div>"
        f"<div style='font-size:22px;font-weight:800;color:{color}'>{val}</div>"
        f"</div>", unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ── SLA heat bar ──────────────────────────────────────────────────
mt_sla_stats = defaultdict(lambda: {"total":0,"on_time":0,"overdue":0,"in_flight":0})
for m in visible:
    mt = m["matter_type"]
    mt_sla_stats[mt]["total"] += 1
    if m["status"] == "completed":
        if not m["sla_breached"]: mt_sla_stats[mt]["on_time"] += 1
        else: mt_sla_stats[mt]["overdue"] += 1
    elif m["status"] not in ("on_hold",):
        mt_sla_stats[mt]["in_flight"] += 1

bar_html = "<div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:16px'>"
for mt,s in mt_sla_stats.items():
    done = s["on_time"] + s["overdue"]
    rate = round(s["on_time"]/done*100) if done else 0
    clr  = "#16A34A" if rate>=85 else "#D97706" if rate>=60 else "#DC2626"
    bar_html += (
        f"<div style='background:{clr}15;border:1px solid {clr}40;border-radius:20px;"
        f"padding:5px 12px;font-size:12px;display:flex;gap:8px;align-items:center'>"
        f"<span style='color:{clr};font-weight:700'>{rate}%</span>"
        f"<span style='color:var(--color-text-secondary)'>{mt} ({s['in_flight']} open)</span></div>")
bar_html += "</div>"
st.markdown(bar_html, unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────
tabs = st.tabs([
    "📋 Active Matters",
    "⚖️ By Type",
    "🔴 Overdue",
    "📊 SLA Analytics",
    "🏛️ Attorney Pipeline",
    "🔐 BSC Feed",
    "🗂️ Custody Register",
    "➕ New Matter",
])

STATUS_COLOR = {
    "open":"#6B7280","in_progress":"#2563EB","pending_client":"#D97706",
    "pending_registry":"#9333EA","pending_attorney":"#0891B2",
    "completed":"#16A34A","overdue":"#DC2626","on_hold":"#6B7280",
}
PRIORITY_COLOR = {"Normal":"#6B7280","Urgent":"#D97706","Critical":"#DC2626"}

def _render_step_bar(matter):
    n     = matter["steps_total"]
    done  = matter["steps_completed"]
    pct   = int(done/n*100)
    color = "#16A34A" if pct==100 else "#2563EB" if pct>=50 else "#D97706"
    bar   = (
        f"<div style='margin:8px 0'>"
        f"<div style='display:flex;justify-content:space-between;font-size:11px;"
        f"color:var(--color-text-secondary);margin-bottom:4px'>"
        f"<span>Step {done}/{n}: <b>{matter['current_step']}</b></span>"
        f"<span>{pct}%</span></div>"
        f"<div style='background:#F3F4F6;border-radius:4px;height:8px'>"
        f"<div style='width:{pct}%;background:{color};height:100%;"
        f"border-radius:4px;transition:width 0.3s'></div>"
        f"</div>"
        f"</div>")
    st.markdown(bar, unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────
# TAB 1: ACTIVE MATTERS
# ────────────────────────────────────────────────────────────────────
with tabs[0]:
    f1,f2,f3 = st.columns(3)
    filt_type = f1.selectbox("Matter type",
                              ["All"]+sorted(set(m["matter_type"] for m in visible)),
                              key="lg_type")
    filt_st   = f2.selectbox("Status",
                              ["Active (excl. completed)","All"]+
                              sorted(set(m["status"] for m in visible)),
                              key="lg_st")
    filt_srch = f3.text_input("Search client", key="lg_srch")

    filtered = visible
    if filt_type != "All":
        filtered = [m for m in filtered if m["matter_type"] == filt_type]
    if filt_st == "Active (excl. completed)":
        filtered = [m for m in filtered if m["status"] not in ("completed","on_hold")]
    elif filt_st != "All":
        filtered = [m for m in filtered if m["status"] == filt_st]
    if filt_srch:
        q = filt_srch.lower()
        filtered = [m for m in filtered if q in m["client_name"].lower()]

    filtered = sorted(filtered,
                       key=lambda x: (x["status"]!="overdue", x["days_to_sla"]))
    st.markdown(f"**{len(filtered)} matters**")

    for m in filtered[:60]:
        sc2  = STATUS_COLOR.get(m["status"],"#6B7280")
        pc2  = PRIORITY_COLOR.get(m["priority"],"#6B7280")
        dtsl = m["days_to_sla"]
        sla_label = (f"🔴 {-dtsl}d overdue" if dtsl < 0
                     else f"🟡 {dtsl}d left"  if dtsl <= 3
                     else f"🟢 {dtsl}d left")
        amt_s = f"KES {m['amount']/1e6:.1f}M" if m.get("amount") else ""
        with st.expander(
            f"{m['matter_type']} · {m['client_name']} · "
            f"{m['status'].replace('_',' ').title()} · {sla_label}",
            expanded=(m["status"]=="overdue" and m["priority"]=="Critical")):

            c1,c2,c3,c4 = st.columns(4)
            c1.markdown(f"**ID:** `{m['id']}`")
            c2.markdown(f"**Officer:** {m.get('legal_officer',{}).get('name','Unassigned')}")
            c3.markdown(f"**Opened:** {m['opened_date']}")
            c4.markdown(f"**SLA due:** {m['sla_due_date']} ({m['sla_days']}d SLA)")
            if amt_s:
                st.markdown(f"**Facility:** {m['product']} · {amt_s}")
            if m.get("attorney"):
                st.markdown(f"**External attorney:** {m['attorney']} · Ref: `{m.get('attorney_ref','')}`")

            _render_step_bar(m)

            # Step advancement (legal team)
            if (is_legal or is_admin) and m["next_step"] and m["status"] not in ("completed","on_hold"):
                b1,b2 = st.columns(2)
                note  = b1.text_input("Step note", key=f"snote_{m['id']}", label_visibility="collapsed",
                                       placeholder="Action taken…")
                if b2.button(f"✅ Advance to: {m['next_step'][:35]}",
                              key=f"adv_{m['id']}"):
                    # Persist step advancement
                    all_matters = json.loads((DATA/"legal_matters.json").read_text())  # bypass cache
                    for idx, mm in enumerate(all_matters):
                        if mm["id"] == m["id"]:
                            new_done = mm["steps_completed"] + 1
                            mm["steps_completed"] = new_done
                            mm["current_step"] = mm["step_history"][new_done-1]["step"] if new_done <= mm["steps_total"] else mm["current_step"]
                            if new_done >= mm["steps_total"]:
                                mm["status"] = "completed"
                                mm["completed_date"] = str(today)
                            mm["step_history"].append({
                                "step": m["next_step"],"status":"completed",
                                "date": str(today),
                                "officer": ud.get("full_name",""),
                                "notes": note,
                            })
                            mm["next_step"] = (mm["step_history"][new_done]["step"]
                                               if new_done < mm["steps_total"] else None)
                            mm["last_updated"] = str(today)
                            break
                    (DATA/"legal_matters.json").write_text(
                        json.dumps(all_matters, indent=2))
                    audit_log("LEGAL_STEP_ADVANCED", uname,
                              f"{m['id']}|{m['next_step']}|{m['client_name']}")
                    _bsc_trigger(uname, "K039")
                    st.cache_data.clear()
                    st.success(f"✅ Advanced: {m['next_step']}")
                    st.rerun()

            # Attorney fees (for Attorney Instruction matters)
            if m.get("attorney"):
                _fee_key = f"fee_{m['id']}"
                _cur_fee = m.get("attorney_fee", 0)
                _fa1, _fa2, _fa3 = st.columns(3)
                _fa1.markdown(f"**Attorney:** {m['attorney']}")
                _fa1.markdown(f"**Ref:** `{m.get('attorney_ref','—')}`")
                if _cur_fee:
                    _fa2.markdown(f"**Fees to date:** KES {_cur_fee:,.0f}")
                if (is_legal or is_admin):
                    _new_fee = _fa3.number_input(
                        "Log fee payment (KES)", min_value=0.0,
                        step=10_000.0, key=f"fee_input_{m['id']}")
                    if _fa3.button("💳 Record fee", key=f"fee_btn_{m['id']}",
                                   disabled=_new_fee == 0):
                        _all_m = json.loads((DATA/"legal_matters.json").read_text())
                        for _mi, _mm in enumerate(_all_m):
                            if _mm["id"] == m["id"]:
                                _all_m[_mi]["attorney_fee"] = (
                                    float(_mm.get("attorney_fee",0)) + _new_fee)
                                _all_m[_mi]["last_updated"] = str(today)
                                break
                        (DATA/"legal_matters.json").write_text(
                            __import__("json").dumps(_all_m, indent=2))
                        audit_log("LEGAL_FEE_RECORDED", uname,
                                  f"{m['id']}|KES {_new_fee:,.0f}")
                        _bsc_trigger(uname, "K039")
                        st.cache_data.clear()
                        st.success(f"✅ Fee KES {_new_fee:,.0f} recorded")
                        st.rerun()

            # Escalate to CCO button
            if (is_legal or is_admin) and m["status"] not in ("completed","on_hold"):
                if st.button(f"🔺 Escalate to CCO", key=f"esc_cco_{m['id']}",
                             help="Escalate to Chief Credit Officer when security cannot be perfected"):
                    _all_m = json.loads((DATA/"legal_matters.json").read_text())
                    for _mi, _mm in enumerate(_all_m):
                        if _mm["id"] == m["id"]:
                            _all_m[_mi]["status"]       = "on_hold"
                            _all_m[_mi]["notes"]        = f"Escalated to CCO: {str(today)}"
                            _all_m[_mi]["last_updated"] = str(today)
                            break
                    (DATA/"legal_matters.json").write_text(
                        __import__("json").dumps(_all_m, indent=2))
                    audit_log("LEGAL_ESCALATED_CCO", uname,
                              f"{m['id']}|{m['client_name']}|escalated to CCO")
                    _bsc_trigger(uname, "K039")
                    st.cache_data.clear()
                    st.warning(f"⚠️ {m['id']} escalated to CCO — matter put on hold")
                    st.rerun()

            # Documents
            docs = m.get("documents",[])
            if docs:
                received = sum(1 for d in docs if d.get("received"))
                st.markdown(f"**Documents:** {received}/{len(docs)} received")
                doc_html = "<div style='display:flex;gap:8px;flex-wrap:wrap;margin-top:4px'>"
                for doc in docs:
                    c = "#16A34A" if doc.get("received") else "#DC2626"
                    doc_html += (f"<span style='background:{c}15;border:1px solid {c}40;"
                                 f"border-radius:12px;padding:3px 10px;font-size:11px;"
                                 f"color:{c}'>{"✅" if doc.get("received") else "⏳"} "
                                 f"{doc['type']}</span>")
                doc_html += "</div>"
                st.markdown(doc_html, unsafe_allow_html=True)

# ────────────────────────────────────────────────────────────────────
# TAB 2: BY TYPE
# ────────────────────────────────────────────────────────────────────
with tabs[1]:
    for mt_name, mt_data in sorted(mt_sla_stats.items()):
        total_mt  = mt_data["total"]
        done_mt   = mt_data["on_time"] + mt_data["overdue"]
        rate_mt   = round(mt_data["on_time"]/done_mt*100) if done_mt else 0
        clr       = "#16A34A" if rate_mt>=85 else "#D97706" if rate_mt>=60 else "#DC2626"
        with st.expander(
            f"{mt_name}  ·  {mt_data['in_flight']} open  ·  SLA rate {rate_mt}%",
            expanded=False):
            m1,m2,m3,m4 = st.columns(4)
            m1.metric("Total",    total_mt)
            m2.metric("Completed",done_mt)
            m3.metric("On Time",  mt_data["on_time"])
            m4.metric("Overdue",  mt_data["overdue"])
            # Matters in this type
            type_matters = [m for m in visible if m["matter_type"]==mt_name
                            and m["status"] not in ("completed","on_hold")]
            if type_matters:
                rows = [{"ID":m["id"],"Client":m["client_name"][:25],
                         "Status":m["status"].replace("_"," ").title(),
                         "Days to SLA":m["days_to_sla"],
                         "Step":m["current_step"][:35],
                         "Officer":m.get("legal_officer",{}).get("name","")[:20]}
                        for m in sorted(type_matters, key=lambda x:x["days_to_sla"])]
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────
# TAB 3: OVERDUE
# ────────────────────────────────────────────────────────────────────
with tabs[2]:
    ov = sorted([m for m in visible if m["sla_breached"] and m["status"]!="completed"],
                key=lambda x: x["days_to_sla"])
    if not ov:
        st.success("✅ No overdue matters.")
    else:
        st.error(f"🔴 {len(ov)} matters past SLA deadline")
        rows = []
        for m in ov:
            rows.append({
                "ID": m["id"],"Type": m["matter_type"],
                "Client": m["client_name"][:25],
                "Days Overdue": abs(m["days_to_sla"]),
                "SLA (days)": m["sla_days"],
                "Status": m["status"].replace("_"," ").title(),
                "Step": m["current_step"][:35],
                "Priority": m["priority"],
                "Officer": m.get("legal_officer",{}).get("name","")[:20],
            })
        df = pd.DataFrame(rows)
        st.dataframe(df.style.map(
            lambda v: "color:#DC2626;font-weight:700" if isinstance(v,int) and v > 14 else "",
            subset=["Days Overdue"]),
            use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────
# TAB 4: SLA ANALYTICS
# ────────────────────────────────────────────────────────────────────
with tabs[3]:
    completed_matters = [m for m in visible if m["status"] == "completed"]
    if not completed_matters:
        st.info("No completed matters yet.")
    else:
        total_c   = len(completed_matters)
        on_time   = sum(1 for m in completed_matters if not m["sla_breached"])
        sla_pct   = round(on_time/total_c*100,1)
        avg_days  = sum(m["days_elapsed"] for m in completed_matters) / total_c

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Completed",   total_c)
        m2.metric("SLA Rate",    f"{sla_pct}%", f"{on_time}/{total_c}")
        m3.metric("Avg TAT",     f"{avg_days:.1f}d")
        m4.metric("Open Overdue",str(overdue))

        # SLA by matter type
        st.markdown("**SLA compliance by matter type:**")
        type_stats = defaultdict(lambda:{"on_time":0,"total":0,"avg_tat":[]})
        for m in completed_matters:
            tp = m["matter_type"]
            type_stats[tp]["total"] += 1
            if not m["sla_breached"]: type_stats[tp]["on_time"] += 1
            type_stats[tp]["avg_tat"].append(m["days_elapsed"])

        rows = []
        for tp, s in sorted(type_stats.items()):
            rate  = round(s["on_time"]/s["total"]*100,1) if s["total"] else 0
            avg_t = round(sum(s["avg_tat"])/len(s["avg_tat"]),1) if s["avg_tat"] else 0
            sla_d = next((MATTER_TYPES[tp]["sla_days"] for MATTER_TYPES in
                          [{"Security Perfection":{"sla_days":14},
                            "Loan Documentation":{"sla_days":5},
                            "Attorney Instruction":{"sla_days":21},
                            "Property Valuation Oversight":{"sla_days":10},
                            "Title Deed Custody":{"sla_days":3},
                            "Litigation":{"sla_days":90},
                            "Legal Opinion":{"sla_days":7}}]
                          if tp in MATTER_TYPES), 0)
            rows.append({"Matter Type":tp,"SLA (days)":sla_d,
                         "Avg TAT (days)":avg_t,"SLA Rate (%)":rate,
                         "Completed":s["total"]})
        st.dataframe(pd.DataFrame(rows).sort_values("SLA Rate (%)"),
                     use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────
# TAB 5: ATTORNEY PIPELINE
# ────────────────────────────────────────────────────────────────────
with tabs[4]:
    att_matters = [m for m in visible if m.get("attorney")]
    if not att_matters:
        st.info("No matters with external attorneys.")
    else:
        att_stats = Counter(m["attorney"] for m in att_matters)
        st.markdown(f"**{len(att_matters)} matters with {len(att_stats)} attorneys**")

        for attorney, cnt in att_stats.most_common():
            att_ms = [m for m in att_matters if m["attorney"]==attorney]
            open_a = sum(1 for m in att_ms if m["status"]!="completed")
            ovd_a  = sum(1 for m in att_ms if m["sla_breached"])
            with st.expander(f"🏛️ {attorney}  ·  {cnt} matters  ·  {open_a} open  ·  {ovd_a} overdue"):
                for m in att_ms:
                    dtsl = m["days_to_sla"]
                    sla_s = f"🔴 {-dtsl}d over" if dtsl<0 else f"🟡 {dtsl}d" if dtsl<=5 else f"🟢 {dtsl}d"
                    st.markdown(
                        f"• `{m['id']}` {m['client_name'][:25]} · "
                        f"Ref: `{m.get('attorney_ref','—')}` · "
                        f"{m['current_step'][:35]} · {sla_s}")

# ────────────────────────────────────────────────────────────────────
# TAB 6: BSC FEED
# ────────────────────────────────────────────────────────────────────
with tabs[5]:
    st.markdown("**Legal KPI actuals for BSC scorecard** — computed from matter TAT data.")
    sla_kpis = defaultdict(lambda:{"total":0,"on_time":0,"sla_days":0})
    for m in visible:
        kpi = m.get("sla_kpi","")
        if kpi:
            sla_kpis[kpi]["total"]    += 1
            sla_kpis[kpi]["sla_days"]  = m.get("sla_days",7)
            if m["status"]=="completed" and not m["sla_breached"]:
                sla_kpis[kpi]["on_time"] += 1

    rows = []
    for kpi, s in sorted(sla_kpis.items()):
        done  = s["on_time"] + sum(1 for m in visible
                                    if m.get("sla_kpi")==kpi and m["status"]=="completed"
                                    and m["sla_breached"])
        rate  = round(s["on_time"]/done*100,1) if done else 0
        rows.append({
            "KPI (BSC)":       kpi,
            "SLA Target (days)":s["sla_days"],
            "Total Matters":   s["total"],
            "Completed":       done,
            "On Time":         s["on_time"],
            "SLA Rate (%)":    rate,
            "BSC Actual":      rate,
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.info("💡 These rates feed directly into the SLA module and BSC scorecard "
                "for legal team members. Admin → Refresh Actuals to push to BSC.")
    else:
        st.info("No completed matters to compute BSC actuals from.")

# ────────────────────────────────────────────────────────────────────
# TAB 7: NEW MATTER
# ────────────────────────────────────────────────────────────────────
with tabs[6]:
    st.markdown("**Title Deed Custody Register** — searchable log of all deeds held by the bank.")
    _custody_matters = [m for m in matters if m.get("matter_type") == "Title Deed Custody"]
    _c_search = st.text_input("Search by client, CIF, or deed ID", key="cust_srch",
                               placeholder="e.g. Wanjiku, CIF123456, LGL00045")
    if _c_search:
        _q = _c_search.lower()
        _custody_matters = [m for m in _custody_matters
                             if _q in m.get("client_name","").lower()
                             or _q in m.get("client_cif","").lower()
                             or _q in m.get("id","").lower()
                             or _q in m.get("application_id","").lower()]
    _received = [m for m in _custody_matters if m.get("steps_completed",0) >= 3]
    _pending  = [m for m in _custody_matters if m.get("steps_completed",0) < 3]
    _cr1, _cr2, _cr3 = st.columns(3)
    _cr1.metric("Total Deeds", len(_custody_matters))
    _cr2.metric("In Strong Room", len(_received))
    _cr3.metric("Pending Processing", len(_pending))
    st.markdown(f"**{len(_custody_matters)} deeds**")
    _custody_rows = []
    for m in sorted(_custody_matters, key=lambda x: x["opened_date"], reverse=True):
        _step_done = m.get("current_step","—")
        _in_sr     = "✅ Yes" if "Strong room" in _step_done or m.get("steps_completed",0) >= len(m.get("step_history",[])) else "⏳ No"
        _custody_rows.append({
            "Matter ID":     m["id"],
            "Client":        m["client_name"][:30],
            "CIF":           m.get("client_cif",""),
            "Product":       m.get("product","")[:20],
            "Received":      m["opened_date"],
            "Status":        m["status"].replace("_"," ").title(),
            "Current Step":  _step_done[:35],
            "In Strong Room": _in_sr,
            "Officer":       m.get("legal_officer",{}).get("name","")[:20] if m.get("legal_officer") else "",
        })
    if _custody_rows:
        import pandas as _pd_cust
        st.dataframe(_pd_cust.DataFrame(_custody_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No title deed custody records match your search.")

with tabs[7]:
    if not (is_legal or is_admin or is_mgr):
        st.info("Matter creation is managed by the legal team.")
    else:
        st.markdown("**Open a new legal matter**")
        MATTER_TYPES_LIST = [
            "Security Perfection","Loan Documentation","Attorney Instruction",
            "Property Valuation Oversight","Title Deed Custody",
            "Litigation","Legal Opinion",
        ]
        SLA_BY_TYPE = {
            "Security Perfection":14,"Loan Documentation":5,"Attorney Instruction":21,
            "Property Valuation Oversight":10,"Title Deed Custody":3,
            "Litigation":90,"Legal Opinion":7,
        }

        n1,n2 = st.columns(2)
        mt_sel    = n1.selectbox("Matter type",  MATTER_TYPES_LIST, key="new_mt")
        priority  = n2.selectbox("Priority",     ["Normal","Urgent","Critical"], key="new_pri")
        client    = n1.text_input("Client name", key="new_client")
        cif       = n2.text_input("Client CIF",  key="new_cif")
        n3,n4     = st.columns(2)
        product   = n3.text_input("Facility/Product", key="new_prod")
        amount    = n4.number_input("Amount (KES)", min_value=0.0, step=1_000_000.0, key="new_amt")
        attorney  = st.text_input("External attorney (if applicable)", key="new_att")
        notes     = st.text_area("Opening notes", key="new_notes", height=80)

        if st.button("📂 Open matter", type="primary", key="new_matter_btn",
                     disabled=not client.strip()):
            import random as _rnd
            all_m = json.loads((DATA/"legal_matters.json").read_text())
            new_id = f"LGL{str(len(all_m)+1).zfill(5)}"
            sla_d  = SLA_BY_TYPE.get(mt_sel, 10)
            from datetime import date as _dt2
            today2 = _dt2.today()
            sla_due= (today2 + timedelta(days=sla_d)).isoformat()
            STEPS_BY_TYPE = {
                "Security Perfection":  ["Instruction received","Title search ordered",
                                          "Charge instrument drafted","Client signed",
                                          "Witness/notarisation","Land registry lodged",
                                          "Registration confirmed","Title returned to bank"],
                "Loan Documentation":   ["Instruction received","Facility letter drafted",
                                          "Credit approved","Client signed",
                                          "Bank countersigned","Documents filed"],
                "Attorney Instruction": ["Brief sent to attorney","Attorney acknowledges",
                                          "Search undertaken","Opinion issued",
                                          "Conditions addressed","File returned"],
                "Property Valuation Oversight":["Instruction to valuer","Site visit scheduled",
                                          "Draft valuation received","Valuation reviewed",
                                          "Valuation approved","Report filed"],
                "Title Deed Custody":   ["Deed received from client","Deed verified",
                                          "Entered in custody register",
                                          "Charge noted on deed","Stored in strong room"],
                "Litigation":           ["Demand letter issued","Response / default",
                                          "Advocate instructed","Pleadings filed",
                                          "Case management","Hearing","Judgment","Execution"],
                "Legal Opinion":        ["Query received","Research undertaken",
                                          "Opinion drafted","Reviewed by Head of Legal",
                                          "Opinion issued"],
            }
            steps = STEPS_BY_TYPE.get(mt_sel, ["Opened","In progress","Closed"])
            new_matter = {
                "id": new_id,"matter_type": mt_sel,"status": "open",
                "priority": priority,"opened_date": str(today2),
                "sla_due_date": sla_due,"completed_date": None,
                "days_elapsed": 0,"days_to_sla": sla_d,"sla_days": sla_d,
                "sla_breached": False,
                "sla_kpi": f"{mt_sel} TAT",
                "client_name": client,"client_cif": cif,
                "application_id": None,"product": product,"amount": float(amount),
                "legal_officer": {"code": sc, "name": ud.get("full_name","")},
                "attorney": attorney or None,"attorney_ref": None,
                "steps_total": len(steps),"steps_completed": 1,
                "current_step": steps[0],"next_step": steps[1] if len(steps)>1 else None,
                "step_history": [{"step":steps[0],"status":"completed",
                                   "date":str(today2),"officer":ud.get("full_name",""),
                                   "notes":notes}],
                "documents": [],"notes": notes,"last_updated": str(today2),
            }
            all_m.append(new_matter)
            (DATA/"legal_matters.json").write_text(json.dumps(all_m, indent=2))
            audit_log("LEGAL_MATTER_OPENED", uname,
                      f"{new_id}|{mt_sel}|{client}")
            _bsc_trigger(uname, "K039")
            st.cache_data.clear()
            st.success(f"✅ Matter {new_id} opened — SLA: {sla_d} days")
            st.rerun()
