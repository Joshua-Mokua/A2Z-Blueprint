"""pages/30_rms.py — Reconciliation Management System (RMS).
CBS-to-GL reconciliation, nostro accounts, suspense clearing, inter-branch.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date
from pages._shared import load_shared_state
from utils.core_audit import audit_log
from pages._access import require_access

require_access("compliance_regulatory.rms")

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update — called after every save action."""
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass
DATA = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin   = ud.get("is_admin",False)
is_finance = any(x in role for x in ("Financial","Finance","CFO","Treasury","Ops","Operations","Clearing"))
is_mgr     = any(x in role for x in ("Manager","Director","Chief","Head"))

@st.cache_data(ttl=60, show_spinner=False)
def _load_rms():
    p = DATA / "rms_reconciliations.json"
    return a2z_db.load_json(p) if p.exists() else []

records = _load_rms()

st.markdown("<div style='padding:16px 0 8px'><span style='font-size:22px;font-weight:800'>🔄 Reconciliation Management</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "CBS · GL · Nostro · Suspense · Inter-branch</span></div>", unsafe_allow_html=True)

matched   = [r for r in records if r["status"]=="Matched"]
unmatched = [r for r in records if r["status"]!="Matched"]
total_var = sum(r["abs_variance"] for r in unmatched)/1e6
escalated = [r for r in unmatched if r["status"]=="Escalated"]

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Total Reconciliations", len(records))
c2.metric("Matched",   f"{len(matched)}",   f"{len(matched)/len(records)*100:.0f}%")
c3.metric("Unreconciled", f"{len(unmatched)}", f"KES {total_var:.1f}M variance")
c4.metric("Escalated",  len(escalated))
oldest = max((r.get("ageing_days",0) for r in unmatched), default=0)
c5.metric("Oldest Break (days)", oldest)

if unmatched:
    st.error(f"🔴 {len(unmatched)} unreconciled items — KES {total_var:.1f}M total variance")

st.markdown("---")
tabs = st.tabs(["📋 All Items","🔴 Breaks","🔍 By Account","📊 Ageing","➕ New Recon","📅 Month-end Close"])

with tabs[0]:
    f1,f2,f3 = st.columns(3)
    sel_s = f1.selectbox("Status",["All","Matched","Unreconciled","Under Investigation","Escalated","Partially Matched"],key="rms_s")
    sel_t = f2.selectbox("Type",  ["All"]+sorted(set(r["recon_type"] for r in records)),key="rms_t")
    sel_p = f3.selectbox("Period",["All"]+sorted(set(r["period"] for r in records),reverse=True)[:6],key="rms_p")
    vis=[r for r in records
         if (sel_s=="All" or r["status"]==sel_s)
         and (sel_t=="All" or r["recon_type"]==sel_t)
         and (sel_p=="All" or r["period"]==sel_p)]
    st.markdown(f"**{len(vis)} items**")
    df_r=pd.DataFrame([{"ID":r["id"],"Type":r["recon_type"][:25],"Account":f"{r['account_code']} {r['account_name'][:20]}",
                         "Period":r["period"],"CBS Bal":f"{r['cbs_balance']/1e6:.2f}M","GL Bal":f"{r['gl_balance']/1e6:.2f}M",
                         "Variance":f"{r['variance']/1e3:.1f}K","Status":r["status"],
                         "Breaker":r.get("breaker_type",""),"Ageing":r.get("ageing_days",0)}
                        for r in sorted(vis,key=lambda x:-x["abs_variance"])])
    st.dataframe(df_r,use_container_width=True,hide_index=True)

with tabs[1]:
    breaks=[r for r in records if r["status"]!="Matched"]
    if not breaks: st.success("✅ All reconciliations matched.")
    else:
        st.markdown(f"**{len(breaks)} breaks** — KES {sum(r['abs_variance'] for r in breaks)/1e6:.1f}M")
        for r in sorted(breaks,key=lambda x:-x["abs_variance"])[:15]:
            clr="🔴" if r["status"]=="Escalated" else "🟡" if r["abs_variance"]>50000 else "🟠"
            with st.expander(f"{clr} {r['recon_type']} · {r['account_name']} · {r['period']} · Var: KES {r['abs_variance']/1e3:.1f}K"):
                bc1,bc2,bc3=st.columns(3)
                bc1.markdown(f"**CBS:** KES {r['cbs_balance']/1e6:.2f}M  \n**GL:** KES {r['gl_balance']/1e6:.2f}M")
                bc2.markdown(f"**Variance:** KES {r['variance']/1e3:.1f}K  \n**Breaker:** {r.get('breaker_type','')}")
                bc3.markdown(f"**Status:** {r['status']}  \n**Ageing:** {r.get('ageing_days',0)} days")
                if (is_finance or is_admin) and r["status"] in ("Unreconciled","Partially Matched"):
                    act1,act2=st.columns(2)
                    if act1.button("🔍 Investigate",key=f"ri_{r['id']}"):
                        recs=json.loads((DATA/"rms_reconciliations.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Under Investigation"; rec["assigned_to"]=name
                        (DATA/"rms_reconciliations.json").write_text(json.dumps(recs,indent=2))
                        audit_log("RMS_UPDATE", name, "Reconciliation updated")
                        _bsc_trigger(uname, "K057")
                        st.cache_data.clear(); st.success("Marked Under Investigation"); st.rerun()
                    if act2.button("✅ Mark Matched",key=f"rm_{r['id']}"):
                        recs=json.loads((DATA/"rms_reconciliations.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Matched"; rec["variance"]=0; rec["abs_variance"]=0; rec["resolved_date"]=str(today)
                        (DATA/"rms_reconciliations.json").write_text(json.dumps(recs,indent=2))
                        st.cache_data.clear(); st.success("✅ Matched"); st.rerun()

with tabs[2]:
    st.markdown("**Reconciliation rate by account:**")
    acc_stats=defaultdict(lambda:{"total":0,"matched":0,"variance":0.0})
    for r in records:
        k=f"{r['account_code']} {r['account_name']}"
        acc_stats[k]["total"]+=1
        if r["status"]=="Matched": acc_stats[k]["matched"]+=1
        else: acc_stats[k]["variance"]+=r["abs_variance"]
    df_a=pd.DataFrame([{"Account":k,"Total":v["total"],"Matched":v["matched"],
                         "Rate":f"{v['matched']/v['total']*100:.0f}%",
                         "Variance (KES K)":round(v["variance"]/1e3,1)}
                        for k,v in sorted(acc_stats.items(),key=lambda x:-x[1]["variance"])])
    st.dataframe(df_a,use_container_width=True,hide_index=True)

with tabs[3]:
    st.markdown("**Ageing analysis of unreconciled breaks:**")
    age_buckets={"0-7d":0,"8-30d":0,"31-60d":0,"60+d":0}
    for r in records:
        if r["status"]=="Matched": continue
        d=r.get("ageing_days",0)
        if d<=7: age_buckets["0-7d"]+=1
        elif d<=30: age_buckets["8-30d"]+=1
        elif d<=60: age_buckets["31-60d"]+=1
        else: age_buckets["60+d"]+=1
    df_age=pd.DataFrame({"Band":list(age_buckets.keys()),"Count":list(age_buckets.values())})
    st.bar_chart(df_age.set_index("Band"))
    st.caption("Breaks older than 30 days should be escalated to Finance Manager.")

with tabs[4]:
    if not (is_finance or is_admin):
        st.info("Creating reconciliation records requires Finance team access.")
    else:
        st.markdown("**Raise a new reconciliation item:**")
        with st.form("new_rms"):
            nc1,nc2=st.columns(2)
            n_type=nc1.selectbox("Recon Type",["CBS to GL","Nostro Account","Suspense Account","Inter-branch","ATM Settlement","Card Settlement","Mobile Money"],key="rms_ntype")
            n_acc =nc2.text_input("Account code + name",key="rms_nacc",placeholder="e.g. 7001 Suspense Debtors")
            nc3,nc4=st.columns(2)
            n_cbs=nc3.number_input("CBS Balance (KES)",step=1000.0,key="rms_ncbs")
            n_gl =nc4.number_input("GL Balance (KES)",step=1000.0,key="rms_ngl")
            n_period=st.text_input("Period (YYYY-MM)",value=str(today)[:7],key="rms_nperiod")
            n_notes =st.text_area("Notes / breaker reason",height=60,key="rms_nnotes")
            if st.form_submit_button("📥 Submit",type="primary"):
                recs=json.loads((DATA/"rms_reconciliations.json").read_text())
                var=round(n_gl-n_cbs,2)
                recs.append({"id":f"REC{str(len(recs)+1).zfill(5)}","recon_type":n_type,
                    "account_code":"","account_name":n_acc,"account_type":"Manual",
                    "period":n_period,"cbs_balance":float(n_cbs),"gl_balance":float(n_gl),
                    "variance":var,"abs_variance":abs(var),"currency":"KES",
                    "status":"Matched" if abs(var)<1000 else "Unreconciled",
                    "breaker_type":"","assigned_to":"","raised_date":str(today),
                    "due_date":str(today),"resolved_date":None,"ageing_days":0,
                    "notes":n_notes,"last_updated":str(today)})
                (DATA/"rms_reconciliations.json").write_text(json.dumps(recs,indent=2))
                st.cache_data.clear(); st.success("✅ Reconciliation logged"); st.rerun()

with tabs[5]:
    st.markdown("**Month-end reconciliation closure checklist:**")
    _today_me = date.today()
    import calendar as _cal_rms
    _last_day = _cal_rms.monthrange(_today_me.year, _today_me.month)[1]
    _days_rem = _last_day - _today_me.day
    
    if _days_rem <= 5:
        st.warning(f"⚠️ **{_days_rem} days to month end** — all breaks must be resolved or escalated")
    
    # Checklist items
    _matched = [r for r in records if r["status"]=="Matched"]
    _unmatched = [r for r in records if r["status"]!="Matched"]
    _old_breaks = [r for r in _unmatched if r.get("ageing_days",0)>30]
    _nostro_ok = all(r["status"]=="Matched" for r in records if "Nostro" in r.get("recon_type",""))
    _suspense_bal = sum(r.get("gl_balance",0) for r in records if "Suspense" in r.get("recon_type",""))
    
    checklist = [
        ("All CBS-GL reconciliations matched", len(_unmatched)==0),
        (f"Nostro accounts balanced ({sum(1 for r in records if 'Nostro' in r.get('recon_type',''))} accounts)", _nostro_ok),
        (f"No breaks aged >30 days ({len(_old_breaks)} found)", len(_old_breaks)==0),
        (f"Suspense balance zero (KES {_suspense_bal/1e6:.1f}M)", abs(_suspense_bal)<10000),
        (f"Reconciliation rate ≥90% (current: {len(_matched)/max(len(records),1)*100:.0f}%)", len(_matched)/max(len(records),1)>=0.90),
    ]
    all_clear = all(ok for _,ok in checklist)
    
    for item, ok in checklist:
        st.markdown(f"  {'✅' if ok else '❌'} {item}")
    
    st.markdown("---")
    if all_clear:
        st.success("✅ All month-end reconciliation checks passed — ready to close.")
    else:
        remaining_items = [item for item,ok in checklist if not ok]
        st.error(f"❌ {len(remaining_items)} item(s) incomplete. Cannot close until resolved.")
    
    # CBK Format 14 download template
    st.markdown("**CBK Regulatory Returns:**")
    if st.button("📥 Download CBK Format 14 (Reconciliation Statement)", key="cbk14"):
        import io, pandas as _pd_rms
        _buf14 = io.BytesIO()
        _rows14 = [{"Account Code":r["account_code"],"Account Name":r["account_name"][:30],
                     "CBS Balance":r["cbs_balance"],"GL Balance":r["gl_balance"],
                     "Variance":r["variance"],"Status":r["status"],
                     "Ageing Days":r.get("ageing_days",0),"Breaker":r.get("breaker_type","")}
                    for r in records]
        _pd_rms.DataFrame(_rows14).to_excel(_buf14, index=False, sheet_name="CBK Format 14", engine="openpyxl")
        _buf14.seek(0)
        st.download_button("📥 Download", data=_buf14.getvalue(),
                            file_name=f"CBK_Format14_{date.today()}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="cbk14_dl")
