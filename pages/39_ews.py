"""pages/39_ews.py — Early Warning System.
Rule-based credit deterioration triggers: missed payments, covenant breach,
sector stress. Red/Amber/Yellow staging. RM action tracking.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter, defaultdict
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
        audit_log("BSC_AUTO_UPDATE", username, f"Module action: {kpi}")
    except Exception:
        pass


require_access("credit.ews")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)
sc = str(ud.get("staff_code",""))
is_credit = any(x in role.lower() for x in ("credit","chief","analyst","risk","head"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>⚠️ Early Warning System</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Credit deterioration signals · Trigger-based staging · RM action tracking</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"ews_cases.json"
    return a2z_db.load_json(p) if p.exists() else []

cases = _load()
stage_ct = Counter(c["stage"] for c in cases)

m1,m2,m3,m4 = st.columns(4)
m1.metric("🔴 Red (DPD>60)",   stage_ct.get("Red",0),   "Immediate action")
m2.metric("🟡 Amber (DPD>30)", stage_ct.get("Amber",0), "Monitor closely")
m3.metric("🟡 Yellow",         stage_ct.get("Yellow",0),"Watch list")
m4.metric("Total EWS Cases",   len(cases))

tabs = st.tabs(["🔴 Red Alerts","🟡 Amber","🟢 All Cases","➕ New Alert","📊 Analytics"])

def _stage_color(stage):
    return {"Red":"#DC2626","Amber":"#D97706","Yellow":"#16A34A"}.get(stage,"#6B7280")

_ews_render_count = [0]  # mutable counter for unique keys

def _render_cases(case_list, show_action=True):
    if not case_list:
        st.success("No cases in this category."); return
    _ews_render_count[0] += 1
    _uid = _ews_render_count[0]   # unique per render call
    rows = [{"ID":c["id"],"Account":c["account_number"][:18],
              "Outstanding (M)":round(c["outstanding"]/1e6,2),
              "DPD":c["dpd"],"Stage":c["stage"],
              "Triggers":", ".join(c["triggers"][:2]),
              "RM":c["rm"][:18],"Branch":c["branch"][:20],
              "Next Action":c["next_action"][:10],
              "Recommended":c["recommended_action"][:30]}
             for c in sorted(case_list,key=lambda x:-x["dpd"])]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

    if show_action and (is_credit or is_admin):
        st.markdown("**Update case:**")
        _sel_id = st.selectbox("Select case", [c["id"] for c in case_list],
                                key=f"ews_sel_{_uid}")
        _new_action = st.text_input("Action taken / notes", key=f"ews_action_{_uid}")
        if st.button("💾 Save update", key=f"ews_save_{_uid}", type="primary"):
            if _new_action:
                all_c = json.loads((DATA/"ews_cases.json").read_text())
                for c in all_c:
                    if c["id"]==_sel_id: c["notes"]=_new_action; c["last_reviewed"]=str(today)
                (DATA/"ews_cases.json").write_text(json.dumps(all_c,indent=2))
                audit_log("EWS_UPDATED",uname,f"{_sel_id}: {_new_action[:60]}")
                _bsc_trigger(uname, "K047")
                st.cache_data.clear(); st.success("✅ Updated"); st.rerun()

with tabs[0]: _render_cases([c for c in cases if c["stage"]=="Red"])
with tabs[1]: _render_cases([c for c in cases if c["stage"]=="Amber"])
with tabs[2]: _render_cases(cases)

with tabs[3]:
    st.markdown("**Raise a new early warning alert:**")
    e1,e2,e3 = st.columns(3)
    _acct  = e1.text_input("Account number",key="ews_acct")
    _stage = e2.selectbox("Stage",["Yellow","Amber","Red"],key="ews_stg")
    _trig  = e3.multiselect("Triggers",["Missed 1 payment","Missed 2 payments","DPD > "+str(cfg("ews_amber_dpd",30)),
                             "Covenant breach","Collateral drop","Sector stress","Rating downgrade"],key="ews_trg")
    _notes = st.text_area("Description / observations",height=80,key="ews_desc")
    if st.button("⚠️ Raise alert",key="ews_raise",type="primary"):
        if _acct and _trig:
            all_c = json.loads((DATA/"ews_cases.json").read_text())
            new_id= f"EWS{len(all_c)+1:05d}"
            all_c.append({"id":new_id,"account_number":_acct,"client_cif":"","outstanding":0,
                           "branch":"","rm":"","risk_score":50,"triggers":_trig,"dpd":0,
                           "stage":_stage,"last_reviewed":str(today),"next_action":str(today),
                           "recommended_action":"Investigate","raised_date":str(today),
                           "status":"Active","notes":_notes})
            (DATA/"ews_cases.json").write_text(json.dumps(all_c,indent=2))
            audit_log("EWS_RAISED",uname,f"{new_id} stage={_stage}")
            _bsc_trigger(uname, "K047")
            st.cache_data.clear(); st.success(f"✅ Alert {new_id} raised"); st.rerun()
        else: st.error("Account number and at least one trigger are required")

with tabs[4]:
    from collections import Counter as _C
    trig_all = [t for c in cases for t in c.get("triggers",[])]
    trig_ct  = _C(trig_all)
    st.markdown("**Most common triggers:**")
    st.bar_chart(pd.DataFrame({"Count":dict(trig_ct.most_common(8))}).T.T)
    st.markdown("**Outstanding (KES M) by stage:**")
    stage_out = defaultdict(float)
    for c in cases: stage_out[c["stage"]] += c["outstanding"]
    for s,v in stage_out.items():
        clr = _stage_color(s)
        st.markdown(f"  {s}: KES {v/1e6:.1f}M",)
