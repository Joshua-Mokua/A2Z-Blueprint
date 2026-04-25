"""pages/60_disciplinary.py — Disciplinary Register."""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("disciplinary")

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
is_admin = ud.get("is_admin", False)
is_hr    = any(x in ud.get("role","").lower() for x in ("human resource","hr","chief human"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>⚖️ Disciplinary Register</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Confidential · Cases · Hearings · Outcomes · Appeals</span></div>",
    unsafe_allow_html=True)

if not (is_hr or is_admin):
    st.error("⛔ Access restricted. This register is confidential — HR team only.")
    st.stop()

st.info("🔒 Confidential — contents of this register must not be shared outside HR and authorised management.")

@st.cache_data(ttl=30)
def _load():
    p = DATA / "disciplinary_register.json"
    return json.loads(p.read_text()) if p.exists() else []

cases = _load()
open_c  = [c for c in cases if c.get("status") == "Open"]
appeals = [c for c in cases if c.get("status") == "On Appeal"]

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Cases",   len(cases))
m2.metric("Open",          len(open_c))
m3.metric("On Appeal",     len(appeals))
m4.metric("Closed",        sum(1 for c in cases if c.get("status")=="Closed"))

tabs = st.tabs(["📋 All Cases","⚠️ Open","📊 Analytics","➕ New Case"])

def _render_cases(case_list):
    if not case_list: st.success("None here."); return
    rows = [{"ID": c["id"], "Dept": c.get("department","")[:18],
              "Offence": c.get("offence_category","")[:25],
              "Offence Date": c.get("offence_date","")[:10],
              "Hearing": c.get("hearing_date","")[:10],
              "Outcome": c.get("outcome","")[:20],
              "Sanction": c.get("sanction","")[:18],
              "Status": c.get("status",""),
              "Appeal": "⚠️" if c.get("appeal_filed") else ""}
             for c in sorted(case_list, key=lambda x: x.get("offence_date",""), reverse=True)]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[0]: _render_cases(cases)
with tabs[1]: _render_cases(open_c)

with tabs[2]:
    off_ct = Counter(c.get("offence_category","") for c in cases)
    st.markdown("**Cases by offence category:**")
    st.bar_chart(pd.DataFrame({"Cases": dict(off_ct.most_common(8))}).T.T)
    outcome_ct = Counter(c.get("outcome","") for c in cases)
    st.markdown("**Outcomes:**")
    for k,n in outcome_ct.most_common():
        st.markdown(f"  {k}: {n}")

with tabs[3]:
    OFFENCES = ["Gross misconduct","Insubordination","Absenteeism","Policy violation",
                "Customer data breach","Financial irregularity","Sexual harassment","Negligence"]
    from utils.core import get_org_config as _goc
    _depts = [d["name"] for d in _goc().get("departments",[]) if d.get("active",True)]
    r1, r2 = st.columns(2)
    _dept   = r1.selectbox("Department", _depts, key="disc_dept")
    _off    = r2.selectbox("Offence category", OFFENCES, key="disc_off")
    _date   = st.date_input("Offence date", key="disc_date")
    _staff  = st.text_input("Staff name (do not enter staff code here)", key="disc_staff")
    _desc   = st.text_area("Brief description of offence", height=60, key="disc_desc")
    if st.button("➕ Open case", key="disc_create", type="primary"):
        if _staff.strip() and _desc.strip():
            all_c = json.loads((DATA/"disciplinary_register.json").read_text())
            all_c.append({
                "id": f"DISC{len(all_c)+1:04d}", "staff_code": "", "staff_name": _staff.strip(),
                "department": _dept, "offence_category": _off, "offence_date": str(_date),
                "hearing_date": "", "outcome": "Under investigation", "sanction": "Pending",
                "appeal_filed": False, "appeal_outcome": "",
                "hr_manager": uname, "status": "Open", "confidential": True,
                "notes": _desc.strip(), "created_date": str(today)
            })
            (DATA/"disciplinary_register.json").write_text(json.dumps(all_c, indent=2))
            audit_log("DISC_CASE_OPENED", uname, f"DISC{len(all_c):04d}: {_off}")
            _bsc_trigger(uname, "K018")
            st.cache_data.clear(); st.success("✅ Case opened"); st.rerun()
        else: st.error("Staff name and description required.")
