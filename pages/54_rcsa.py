"""pages/54_rcsa.py — Risk Register & RCSA.
Operational risk events, KRIs, control effectiveness. Thresholds via Admin.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter
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


require_access("rcsa")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin",False)
is_risk  = any(x in role for x in ("risk","compliance","chief risk","operational risk"))

st.markdown("<div style='padding:16px 0 4px'><span style='font-size:22px;font-weight:800'>🛡️ Risk Register (RCSA)</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Operational risk · Controls · KRIs · Residual risk · Action plans</span></div>",
            unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA/"rcsa_register.json"
    return a2z_db.load_json(p) if p.exists() else []

risks = _load()
HIGH_THR = cfg("rcsa_high_residual", 12)
MED_THR  = cfg("rcsa_medium_residual", 6)

high = [r for r in risks if r.get("residual_score",0) >= HIGH_THR]
med  = [r for r in risks if MED_THR <= r.get("residual_score",0) < HIGH_THR]
kri_breached = [r for r in risks if r.get("kri_breached")]
action_due   = [r for r in risks if r.get("action_required")]

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Risks",  len(risks))
m2.metric("High Residual",len(high), delta_color="normal" if not high else "inverse")
m3.metric("KRI Breached", len(kri_breached), delta_color="normal" if not kri_breached else "inverse")
m4.metric("Action Required",len(action_due))

if high:
    st.error(f"🔴 {len(high)} high-residual risks require immediate management attention")

tabs = st.tabs(["🔴 High Risk","📋 All Risks","📊 Heat Map","🔔 KRIs","➕ Add Risk"])

def _render_risks(risk_list):
    if not risk_list: st.success("None in this view."); return
    rows=[{"ID":r["id"],"Category":r["category"][:20],"Dept":r["department"][:18],
            "Inherent":r["inherent_score"],"Control":r["control_effectiveness"][:12],
            "Residual":r["residual_score"],"Rating":r["residual_rating"],
            "Owner":r["risk_owner"][:20],"Next Review":r["next_review"][:10],
            "Action":("⚠️" if r.get("action_required") else "")}
           for r in sorted(risk_list, key=lambda x:-x.get("residual_score",0))]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[0]: _render_risks(high)
with tabs[1]:
    f1,f2 = st.columns(2)
    fcat = f1.selectbox("Category",["All"]+sorted(set(r["category"] for r in risks)),key="rcsa_cat")
    frat = f2.selectbox("Rating",["All","High","Medium","Low"],key="rcsa_rat")
    vis  = [r for r in risks
            if (fcat=="All" or r["category"]==fcat)
            and (frat=="All" or r["residual_rating"]==frat)]
    _render_risks(vis)

with tabs[2]:
    st.markdown("**Risk heat map — inherent score distribution:**")
    cat_ct = Counter(r["category"] for r in risks)
    st.bar_chart(pd.DataFrame({"Risks":dict(cat_ct.most_common())}).T.T)
    rating_ct = Counter(r["residual_rating"] for r in risks)
    st.markdown("**Residual risk distribution:**")
    for rat,n in [("High",rating_ct.get("High",0)),("Medium",rating_ct.get("Medium",0)),("Low",rating_ct.get("Low",0))]:
        clr={"High":"#DC2626","Medium":"#D97706","Low":"#16A34A"}.get(rat,"#6B7280")
        pct=n/max(len(risks),1)*100
        st.markdown(f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
                    f"<div style='width:60px'>{rat}</div>"
                    f"<div style='background:{clr};height:16px;width:{pct:.0f}%;border-radius:3px'></div>"
                    f"<div style='font-size:12px'>{n} ({pct:.0f}%)</div></div>",unsafe_allow_html=True)

with tabs[3]:
    st.markdown("**KRI Dashboard — breached indicators:**")
    if kri_breached:
        kri_rows=[{"ID":r["id"],"KRI":r["kri"],"Value":r["kri_value"],"Threshold":r["kri_threshold"],
                    "Category":r["category"][:20],"Owner":r["risk_owner"][:20]}
                   for r in kri_breached]
        st.dataframe(pd.DataFrame(kri_rows),use_container_width=True,hide_index=True)
    else:
        st.success("✅ No KRI breaches currently.")

with tabs[4]:
    if is_risk or is_admin:
        st.markdown("**Add new risk to register:**")
        from utils.core import get_org_config as _goc
        _depts = [d["name"] for d in _goc().get("departments",[]) if d.get("active",True)]
        r1,r2,r3 = st.columns(3)
        _cat = r1.selectbox("Category",["Credit Risk","Market Risk","Liquidity Risk","Operational Risk",
                             "Compliance/Legal","Reputational Risk","Strategic Risk","IT/Cyber Risk"],key="rcsa_ncat")
        _dept= r2.selectbox("Department",_depts,key="rcsa_ndept")
        _inh = r3.slider("Inherent score (1-25)",1,25,9,key="rcsa_ninh")
        _desc= st.text_area("Risk description",height=80,key="rcsa_ndesc")
        _ctrl= st.selectbox("Control",["Manual control","Automated control","Dual control",
                             "Segregation of duties","Policy & procedure","None"],key="rcsa_nctrl")
        _eff = st.selectbox("Control effectiveness",["Adequate","Partially adequate","Inadequate"],key="rcsa_neff")
        if st.button("➕ Add risk",key="rcsa_add",type="primary"):
            if _desc.strip():
                all_r = json.loads((DATA/"rcsa_register.json").read_text())
                resid = _inh*(0.4 if _eff=="Adequate" else 0.6 if _eff=="Partially adequate" else 0.85)
                all_r.append({"id":f"RSK{len(all_r)+1:04d}","category":_cat,"description":_desc.strip(),
                               "department":_dept,"inherent_score":_inh,"control_description":_ctrl,
                               "control_effectiveness":_eff,"residual_score":round(resid,1),
                               "residual_rating":("High" if resid>=HIGH_THR else "Medium" if resid>=MED_THR else "Low"),
                               "risk_owner":uname,"last_reviewed":str(today),"next_review":"",
                               "action_required":_eff!="Adequate","kri":"","kri_value":0,"kri_threshold":0,"kri_breached":False,"notes":""})
                (DATA/"rcsa_register.json").write_text(json.dumps(all_r,indent=2))
                audit_log("RCSA_RISK_ADDED",uname,f"{_cat}: {_desc[:60]}")
                _bsc_trigger(uname, "K014")
                st.cache_data.clear(); st.success("✅ Risk added"); st.rerun()
            else: st.error("Description required.")
    else: st.info("Risk Register editing available to Risk & Compliance team.")
