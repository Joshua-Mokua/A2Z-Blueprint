"""pages/29_revenue_assurance.py — Revenue Assurance Module.
Tracks fee waivers, income leakages, and CBS-to-GL income variances.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date, timedelta
from pages._shared import load_shared_state
from utils.core import audit_log, requires_dual_approval, submit_for_approval
from pages._access import require_access

require_access("revenue_assurance")

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
sc = str(ud.get("staff_code","") or ""); role = ud.get("role",""); name = ud.get("full_name","")
is_admin   = ud.get("is_admin",False)
is_finance = any(x in role for x in ("Chief Financial","Financial Controller","Finance Manager","CFO","Tax"))
is_mgr     = any(x in role for x in ("Manager","Director","Chief","Head"))

@st.cache_data(ttl=60, show_spinner=False)
def _load_ra():
    p = DATA / "revenue_assurance.json"
    return a2z_db.load_json(p) if p.exists() else []

records = _load_ra()

st.markdown("<div style='padding:16px 0 8px'><span style='font-size:22px;font-weight:800'>💰 Revenue Assurance</span>"
            "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
            "Fee waivers · Income leakages · Recovery tracking</span></div>", unsafe_allow_html=True)

f1,f2,f3,f4 = st.columns(4)
sel_type   = f1.selectbox("Type",   ["All","Waiver","Leakage"], key="ra_type")
sel_status = f2.selectbox("Status", ["All","Open","Pending Approval","Approved","Investigated","Recovered","Written Off","Rejected","Escalated"], key="ra_status")
sel_period = f3.selectbox("Period", ["All"]+sorted(set(r["period"] for r in records),reverse=True)[:6], key="ra_period")
sel_branch = f4.selectbox("Branch", ["All"]+sorted(set(r["branch"] for r in records)), key="ra_branch")

visible = [r for r in records
           if (sel_type=="All" or r["type"]==sel_type)
           and (sel_status=="All" or r["status"]==sel_status)
           and (sel_period=="All" or r["period"]==sel_period)
           and (sel_branch=="All" or r["branch"]==sel_branch)]

waivers  = [r for r in records if r["type"]=="Waiver"]
leakages = [r for r in records if r["type"]=="Leakage"]
recovered= [r for r in leakages if r["status"]=="Recovered"]
pending  = [r for r in waivers  if r["status"]=="Pending Approval"]

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Total Waivers",    f"{len(waivers)}",  f"KES {sum(r['amount'] for r in waivers)/1e6:.1f}M")
c2.metric("Pending Approval", f"{len(pending)}",  f"KES {sum(r['amount'] for r in pending)/1e6:.1f}M")
c3.metric("Income Leakages",  f"{len(leakages)}", f"KES {sum(r['amount'] for r in leakages)/1e6:.1f}M")
c4.metric("Recovered",        f"{len(recovered)}",f"KES {sum(r['amount'] for r in recovered)/1e6:.1f}M")
c5.metric("Recovery Rate",    f"{len(recovered)/max(len(leakages),1)*100:.0f}%")

if pending and (is_finance or is_admin or is_mgr):
    st.warning(f"\u26a0\ufe0f {len(pending)} waiver(s) pending approval — KES {sum(r['amount'] for r in pending)/1e6:.1f}M")

st.markdown("---")
tabs = st.tabs(["📋 All Records","🔴 Leakages","⏳ Pending Waivers","📊 Analytics","➕ Log Record"])

with tabs[0]:
    st.markdown(f"**{len(visible)} records** — KES {sum(r['amount'] for r in visible)/1e6:.1f}M")
    rows=[{"ID":r["id"],"Type":r["type"],"Fee Type":r["fee_type"][:30],"Branch":r["branch"][:20],
           "Amount":f"{r['amount']:,.0f}","Period":r["period"],"Status":r["status"],
           "Reason":r.get("reason","")[:30],"Raised By":r.get("raised_by","")[:20]}
          for r in sorted(visible,key=lambda x:x["date_raised"],reverse=True)]
    if rows: st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:    st.info("No records match the current filters.")

with tabs[1]:
    open_l=[r for r in visible if r["type"]=="Leakage" and r["status"] not in ("Recovered","Written Off")]
    if not open_l: st.success("✅ No open leakages.")
    else:
        st.error(f"🔴 {len(open_l)} open leakages — KES {sum(r['amount'] for r in open_l)/1e6:.1f}M unrecovered")
        for r in sorted(open_l,key=lambda x:-x["amount"])[:20]:
            with st.expander(f"🔴 {r['fee_type']} · {r['branch']} · KES {r['amount']:,.0f} · {r['status']}"):
                ec1,ec2,ec3=st.columns(3)
                ec1.markdown(f"**Type:** {r['reason']}"); ec2.markdown(f"**Client:** {r['client_name']}"); ec3.markdown(f"**Date:** {r['date_raised']}")
                if (is_finance or is_admin) and r["status"]=="Open":
                    a1,a2=st.columns(2)
                    if a1.button("🔍 Investigate",key=f"inv_{r['id']}"):
                        recs=json.loads((DATA/"revenue_assurance.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Under Investigation"
                        (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                        audit_log("RA_UPDATE", name, "Revenue assurance updated")
                        _bsc_trigger(uname, "K003")
                        st.cache_data.clear(); st.success("Marked Under Investigation"); st.rerun()
                    if a2.button("✅ Mark Recovered",key=f"rec_{r['id']}"):
                        recs=json.loads((DATA/"revenue_assurance.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Recovered"; rec["recovered"]=True; rec["recovered_amount"]=rec["amount"]
                        (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                        audit_log("RA_UPDATE", name, "Revenue assurance updated")
                        _bsc_trigger(uname, "K003")
                        st.cache_data.clear(); st.success("✅ Recovered"); st.rerun()

with tabs[2]:
    pend_w=[r for r in visible if r["type"]=="Waiver" and r["status"]=="Pending Approval"]
    
    # ── Batch approval at month end ──────────────────────────────
    _today_d = date.today()
    _month_end = (_today_d.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    _days_left = (_month_end - _today_d).days
    if pend_w and (is_mgr or is_admin or is_finance) and _days_left <= 5:
        st.warning(f"⚠️ **Month-end: {_days_left}d remaining** — {len(pend_w)} waivers pending")
        if st.button(f"✅ Batch Approve ALL {len(pend_w)} pending waivers (month-end close)", 
                     key="ra_batch_approve", type="primary"):
            recs=json.loads((DATA/"revenue_assurance.json").read_text())
            n=0
            for rec in recs:
                if rec["type"]=="Waiver" and rec["status"]=="Pending Approval":
                    rec["status"]="Approved"; rec["authorised_by"]=name; n+=1
            (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
            audit_log("RA_BATCH_APPROVE",uname,f"Month-end batch approve {n} waivers")
            _bsc_trigger(uname, "K003")
            st.cache_data.clear(); st.success(f"✅ {n} waivers approved (month-end batch)"); st.rerun()
    if not pend_w: st.success("✅ No waivers pending approval.")
    else:
        st.markdown(f"**{len(pend_w)} waivers** — KES {sum(r['amount'] for r in pend_w)/1e6:.1f}M")
        for r in sorted(pend_w,key=lambda x:-x["amount"]):
            with st.expander(f"⏳ {r['fee_type']} · {r['branch']} · KES {r['amount']:,.0f}"):
                wc1,wc2=st.columns(2)
                wc1.markdown(f"**Reason:** {r['reason']}  \n**Client:** {r['client_name']}")
                wc2.markdown(f"**Raised by:** {r.get('raised_by','')}  \n**Date:** {r['date_raised']}")
                if is_mgr or is_admin or is_finance:
                    wa1,wa2=st.columns(2)
                    if wa1.button("✅ Approve",key=f"wapp_{r['id']}",type="primary"):
                        recs=json.loads((DATA/"revenue_assurance.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Approved"; rec["authorised_by"]=name
                        (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                        audit_log("RA_UPDATE", name, "Revenue assurance updated")
                        _bsc_trigger(uname, "K003")
                        st.cache_data.clear(); st.success("✅ Approved"); st.rerun()
                    if wa2.button("❌ Reject",key=f"wrej_{r['id']}"):
                        recs=json.loads((DATA/"revenue_assurance.json").read_text())
                        for rec in recs:
                            if rec["id"]==r["id"]: rec["status"]="Rejected"
                        (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                        audit_log("RA_UPDATE", name, "Revenue assurance updated")
                        _bsc_trigger(uname, "K003")
                        st.cache_data.clear(); st.success("Rejected"); st.rerun()

with tabs[3]:
    st.markdown("**By branch:**")
    bw=defaultdict(lambda:{"w":0,"l":0,"wv":0,"lv":0})
    for r in records:
        b=r["branch"]
        if r["type"]=="Waiver": bw[b]["w"]+=1; bw[b]["wv"]+=r["amount"]
        else:                   bw[b]["l"]+=1; bw[b]["lv"]+=r["amount"]
    df_b=pd.DataFrame([{"Branch":b,"Waivers":v["w"],"Leakages":v["l"],
                         "Waiver (M)":round(v["wv"]/1e6,1),"Leakage (M)":round(v["lv"]/1e6,1),
                         "Total Risk (M)":round((v["wv"]+v["lv"])/1e6,1)} for b,v in bw.items()])
    st.dataframe(df_b.sort_values("Total Risk (M)",ascending=False),use_container_width=True,hide_index=True)
    st.markdown("**By fee type (top 10):**")
    fv=defaultdict(float)
    for r in records: fv[r["fee_type"]]+=r["amount"]
    df_f=pd.DataFrame([{"Fee Type":k,"Total (KES M)":round(v/1e6,1)} for k,v in sorted(fv.items(),key=lambda x:-x[1])[:10]])
    st.dataframe(df_f,use_container_width=True,hide_index=True)

with tabs[4]:
    st.markdown("**Log a new waiver or leakage:**")
    with st.form("log_ra"):
        l1,l2=st.columns(2)
        l_type=l1.selectbox("Type",["Waiver","Leakage"],key="log_type")
        l_fee =l2.selectbox("Fee Type",["Account Maintenance Fee","Ledger Fee","Loan Processing Fee","Card Maintenance Fee","Wire Transfer Fee","RTGS Fee","EFT Fee","Bancassurance Commission","Trade Finance Fee","Other"],key="log_fee")
        l3,l4=st.columns(2)
        l_amount=l3.number_input("Amount (KES)",min_value=0.0,step=1000.0,key="log_amt")
        l_branch=l4.selectbox("Branch",sorted(set(r["branch"] for r in records)),key="log_branch")
        l_client=st.text_input("Client name",key="log_client")
        l_reason=st.text_area("Reason",height=68,key="log_reason")
        if st.form_submit_button("📥 Log record",type="primary"):
            if not l_client.strip(): st.error("Enter client name")
            elif l_amount<=0:        st.error("Amount must be > 0")
            else:
                recs=json.loads((DATA/"revenue_assurance.json").read_text())
                recs.append({"id":f"RA{str(len(recs)+1).zfill(5)}","type":l_type,"fee_type":l_fee,
                    "branch":l_branch,"amount":float(l_amount),"currency":"KES",
                    "date_raised":str(today),"period":str(today)[:7],"reason":l_reason,
                    "client_name":l_client.strip(),"client_cif":"","raised_by":name,"raised_code":sc,
                    "status":"Pending Approval" if l_type=="Waiver" else "Open",
                    "recovered":False,"recovered_amount":0,"authorised_by":"","notes":"","last_updated":str(today)})
                (DATA/"revenue_assurance.json").write_text(json.dumps(recs,indent=2))
                audit_log("RA_UPDATE", name, "Revenue assurance updated")
                _bsc_trigger(uname, "K003")
                st.cache_data.clear(); st.success("✅ Logged"); st.rerun()
