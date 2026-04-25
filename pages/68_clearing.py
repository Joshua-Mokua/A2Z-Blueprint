"""pages/68_clearing.py — Clearing & Settlement Management.
RTGS, KEPSS, EFT, cheque clearing, nostro reconciliation, exceptions.
Configurable: clearing windows, nostro accounts, exception thresholds.
BSC auto-scores: K055 (exception rate), K056 (nostro recon), K057 (settlement TAT).
Department: Operations. Roles: Clearing Officer, Settlement Officer, Head of Ops.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, datetime, timedelta
from collections import defaultdict
from decimal import Decimal
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("clearing")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()

um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_ops   = any(x in role for x in ("operations","clearing","settlement","nostro","head"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏦 Clearing & Settlement</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "RTGS · KEPSS · EFT · Cheque · Nostro reconciliation · Exceptions</span></div>",
    unsafe_allow_html=True)

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    p = DATA/"clearing_records.json"
    raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    for r in raw:
        for k,v in r.items():
            if isinstance(v,Decimal): r[k]=float(v)
    return raw

@st.cache_data(ttl=60)
def _cfg():
    p = DATA/"clearing_config.json"
    if p.exists(): return json.loads(p.read_text(encoding="utf-8"))
    return {
        "clearing_windows":[
            {"id":"RTGS","name":"RTGS","open":"08:00","close":"15:30","currency":"KES","active":True},
            {"id":"KEPSS","name":"KEPSS","open":"08:00","close":"17:00","currency":"KES","active":True},
            {"id":"EFT","name":"EFT","open":"00:00","close":"23:59","currency":"KES","active":True},
            {"id":"CHQKE","name":"Cheque Clearing","open":"08:00","close":"12:00","currency":"KES","active":True},
            {"id":"SWIFT","name":"SWIFT","open":"08:00","close":"16:00","currency":"USD/EUR/GBP","active":True},
        ],
        "nostro_accounts":[
            {"id":"USD001","bank":"Correspondent A","currency":"USD","threshold_m":5.0,"active":True},
            {"id":"EUR001","bank":"Correspondent B","currency":"EUR","threshold_m":2.0,"active":True},
            {"id":"GBP001","bank":"Correspondent C","currency":"GBP","threshold_m":1.0,"active":True},
        ],
        "exception_threshold_pct":2.0,
        "settlement_tat_minutes":{"RTGS":30,"KEPSS":60,"EFT":240,"CHQKE":1440,"SWIFT":480},
    }

def _save_cfg(cfg): (DATA/"clearing_config.json").write_text(json.dumps(cfg,indent=2))
def _save_records(recs): (DATA/"clearing_records.json").write_text(json.dumps(recs,indent=2)); st.cache_data.clear()

records = _load()
cfg     = _cfg()

# ── Summary metrics ───────────────────────────────────────────────
total     = len(records)
today_recs= [r for r in records if r.get("clearing_date","")[:10]==str(today)]
exceptions= [r for r in records if r.get("status") in ("Failed","Rejected","Exception")]
reconciled= [r for r in records if r.get("reconciled")]
pending_recon = [r for r in records if not r.get("reconciled") and r.get("status")=="Settled"]
total_value = sum(float(r.get("amount_kes",0) or 0) for r in records)/1e9

exc_rate = round(len(exceptions)/max(total,1)*100,1)
recon_rate= round(len(reconciled)/max(total,1)*100,1)

if exceptions: st.error(f"🔴 {len(exceptions)} clearing exceptions require action")
if pending_recon: st.warning(f"⚠️ {len(pending_recon)} items pending nostro reconciliation")

m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("Total items",       f"{total:,}")
m2.metric("Today's items",     f"{len(today_recs):,}")
m3.metric("Total value (KES B)",f"{total_value:.1f}")
m4.metric("Exceptions",        len(exceptions),
          delta_color="inverse" if exceptions else "normal")
m5.metric("Exception rate",    f"{exc_rate:.1f}%",
          delta=f"Target ≤{cfg.get('exception_threshold_pct',2.0):.1f}%",
          delta_color="normal" if exc_rate<=cfg.get('exception_threshold_pct',2.0) else "inverse")
m6.metric("Nostro recon rate", f"{recon_rate:.1f}%")

tabs = st.tabs(["📋 Register","🚨 Exceptions","🔗 Nostro Recon","➕ New Item",
                "📊 Analytics","⚙️ Config","🎯 BSC Impact"])

# ── TAB 0: Register ───────────────────────────────────────────────
with tabs[0]:
    f1,f2,f3,f4 = st.columns(4)
    f_sys  = f1.selectbox("System",["All"]+[c["id"] for c in cfg["clearing_windows"]],key="cl_fsys")
    f_stat = f2.selectbox("Status",["All","Submitted","Processing","Settled","Failed","Rejected","Exception"],key="cl_fstat")
    f_date = f3.date_input("From date",today-timedelta(days=7),key="cl_fdate")
    f_ccy  = f4.selectbox("Currency",["All","KES","USD","EUR","GBP"],key="cl_fccy")

    vis = [r for r in records
           if (f_sys=="All" or r.get("system","")==f_sys)
           and (f_stat=="All" or r.get("status","")==f_stat)
           and r.get("clearing_date","")[:10]>=str(f_date)
           and (f_ccy=="All" or r.get("currency","")==f_ccy)]

    rows = [{"ID":r["id"],"System":r.get("system",""),"Date":r.get("clearing_date","")[:10],
             "Currency":r.get("currency","KES"),
             "Amount":f"{float(r.get('amount_kes',0) or 0)/1e6:.2f}M",
             "Status":r.get("status",""),"Reconciled":"✅" if r.get("reconciled") else "⏳",
             "TAT Met":"✅" if r.get("settlement_tat_met") else "❌" if r.get("status")=="Settled" else "—",
             "Exception":"🔴" if r.get("status") in ("Failed","Rejected","Exception") else ""}
            for r in sorted(vis, key=lambda x:x.get("clearing_date",""),reverse=True)]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    
    v_val = sum(float(r.get("amount_kes",0) or 0) for r in vis)/1e9
    st.caption(f"Showing {len(vis)} items | Total value: KES {v_val:.2f}B")

# ── TAB 1: Exceptions ─────────────────────────────────────────────
with tabs[1]:
    st.markdown("**Items requiring action — failures, rejections and exceptions:**")
    if exceptions:
        for exc in sorted(exceptions, key=lambda x:x.get("clearing_date",""),reverse=True)[:20]:
            with st.expander(f"🔴 {exc['id']} — {exc.get('system','')} — KES {float(exc.get('amount_kes',0) or 0)/1e6:.2f}M"):
                c1,c2,c3 = st.columns(3)
                c1.markdown(f"**Status:** {exc.get('status','')}")
                c2.markdown(f"**Date:** {exc.get('clearing_date','')[:10]}")
                c3.markdown(f"**Reason:** {exc.get('exception_reason','—')}")
                action = st.selectbox("Action",["Select","Resubmit","Reject","Escalate","Resolved"],
                                      key=f"exc_act_{exc['id']}")
                note   = st.text_input("Note", key=f"exc_note_{exc['id']}")
                if st.button("💾 Apply action", key=f"exc_save_{exc['id']}", type="primary"):
                    if action != "Select":
                        all_r = _load()
                        for r2 in all_r:
                            if r2["id"]==exc["id"]:
                                r2["status"]       = "Resolved" if action=="Resolved" else r2["status"]
                                r2["action_taken"] = action
                                r2["action_note"]  = note
                                r2["actioned_by"]  = uname
                                r2["actioned_at"]  = str(today)
                                break
                        _save_records(all_r)
                        audit_log("CLEARING_EXCEPTION_ACTIONED",uname,f"{exc['id']}: {action}")
                        _bsc_trigger(uname,"K055")
                        st.success("✅ Action applied"); st.rerun()
    else:
        st.success("✅ No exceptions — all items processing normally")

# ── TAB 2: Nostro Reconciliation ──────────────────────────────────
with tabs[2]:
    st.markdown("**Nostro account reconciliation status:**")
    for nostro in cfg.get("nostro_accounts",[]):
        with st.expander(f"🏦 {nostro['bank']} — {nostro['currency']}"):
            nrecs = [r for r in records if r.get("currency")==nostro["currency"]]
            recon_c = sum(1 for r in nrecs if r.get("reconciled"))
            unrecon = [r for r in nrecs if not r.get("reconciled") and r.get("status")=="Settled"]
            c1,c2,c3 = st.columns(3)
            c1.metric("Items",len(nrecs))
            c2.metric("Reconciled",recon_c)
            c3.metric("Pending",len(unrecon))
            if unrecon:
                st.markdown("**Unreconciled items:**")
                un_rows = [{"ID":r["id"],"Date":r.get("clearing_date","")[:10],
                            "Amount":f"{float(r.get('amount_kes',0) or 0)/1e6:.2f}M"}
                           for r in unrecon[:10]]
                st.dataframe(pd.DataFrame(un_rows),use_container_width=True,hide_index=True)
                if st.button(f"✅ Mark all reconciled — {nostro['currency']}", key=f"recon_{nostro['id']}"):
                    all_r = _load()
                    cnt = 0
                    for r2 in all_r:
                        if r2.get("currency")==nostro["currency"] and not r2.get("reconciled") and r2.get("status")=="Settled":
                            r2["reconciled"]=True; r2["reconciled_by"]=uname; r2["reconciled_at"]=str(today); cnt+=1
                    _save_records(all_r)
                    audit_log("NOSTRO_RECONCILED",uname,f"{nostro['currency']}: {cnt} items")
                    _bsc_trigger(uname,"K056")
                    st.success(f"✅ {cnt} items marked reconciled"); st.rerun()

# ── TAB 3: New Item ───────────────────────────────────────────────
with tabs[3]:
    if is_ops or is_admin:
        sys_opts  = [c["id"] for c in cfg["clearing_windows"] if c.get("active")]
        ccy_opts  = ["KES","USD","EUR","GBP"]
        stat_opts = ["Submitted","Processing","Settled","Failed"]
        c1,c2,c3 = st.columns(3)
        _sys  = c1.selectbox("Clearing system",sys_opts,key="cl_new_sys")
        _ccy  = c2.selectbox("Currency",ccy_opts,key="cl_new_ccy")
        _stat = c3.selectbox("Status",stat_opts,key="cl_new_stat")
        _amt  = st.number_input("Amount",0.0,10_000_000_000.0,1_000_000.0,key="cl_new_amt")
        _ref  = st.text_input("Reference",key="cl_new_ref")
        _cdate= st.date_input("Clearing date",today,key="cl_new_date")
        _recon= st.checkbox("Already reconciled",key="cl_new_recon")
        _tat  = st.checkbox("Settlement TAT met",value=True,key="cl_new_tat")

        if st.button("💾 Submit clearing item",key="cl_new_submit",type="primary"):
            if _ref.strip():
                all_r = _load()
                all_r.append({
                    "id":f"CLR{len(all_r)+1:06d}","system":_sys,"currency":_ccy,
                    "amount_kes":_amt,"reference":_ref.strip(),"status":_stat,
                    "clearing_date":str(_cdate),"reconciled":_recon,
                    "reconciled_by":uname if _recon else "","reconciled_at":str(today) if _recon else "",
                    "settlement_tat_met":_tat,"exception_reason":"",
                    "officer_username":uname,"created_by":uname,"created_at":str(today)
                })
                _save_records(all_r)
                audit_log("CLEARING_SUBMITTED",uname,f"{_sys}: {_ref} KES {_amt:,.0f}")
                _bsc_trigger(uname,"K057")
                st.success("✅ Clearing item submitted"); st.rerun()
            else: st.error("Reference required")
    else: st.info("Clearing submission available to Operations staff.")

# ── TAB 4: Analytics ──────────────────────────────────────────────
with tabs[4]:
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**Volume by system:**")
        sys_vol = defaultdict(lambda:{"count":0,"value":0,"exceptions":0})
        for r in records:
            s = r.get("system","Other")
            sys_vol[s]["count"]  += 1
            sys_vol[s]["value"]  += float(r.get("amount_kes",0) or 0)/1e9
            if r.get("status") in ("Failed","Rejected","Exception"):
                sys_vol[s]["exceptions"] += 1
        vol_rows = [{"System":s,"Items":v["count"],"Value (KES B)":round(v["value"],2),
                     "Exceptions":v["exceptions"],"Exc Rate":f"{v['exceptions']/max(v['count'],1)*100:.1f}%"}
                    for s,v in sorted(sys_vol.items(),key=lambda x:-x[1]["count"])]
        st.dataframe(pd.DataFrame(vol_rows),use_container_width=True,hide_index=True)
    with c2:
        st.markdown("**Settlement TAT performance:**")
        tat_data = {}
        for c_def in cfg["clearing_windows"]:
            sid  = c_def["id"]
            recs = [r for r in records if r.get("system")==sid and r.get("status")=="Settled"]
            met  = sum(1 for r in recs if r.get("settlement_tat_met"))
            target_mins = cfg.get("settlement_tat_minutes",{}).get(sid,60)
            tat_data[sid] = {"items":len(recs),"met":met,
                             "rate":f"{met/max(len(recs),1)*100:.0f}%",
                             "target":f"{target_mins} mins"}
        tat_rows = [{"System":s,"Items":v["items"],"TAT Met":v["met"],
                     "Rate":v["rate"],"Target":v["target"]} for s,v in tat_data.items()]
        st.dataframe(pd.DataFrame(tat_rows),use_container_width=True,hide_index=True)

# ── TAB 5: Config ─────────────────────────────────────────────────
with tabs[5]:
    if is_admin or is_ops:
        cfg2 = _cfg()
        st.markdown("**Clearing windows:**")
        for win in cfg2["clearing_windows"]:
            c1,c2,c3,c4 = st.columns([3,2,2,1])
            c1.markdown(f"**{win['name']}** ({win['currency']})")
            c2.markdown(f"{win['open']} – {win['close']}")
            c3.markdown(f"TAT target: {cfg2['settlement_tat_minutes'].get(win['id'],60)} mins")
            active = c4.checkbox("Active",value=win.get("active",True),key=f"win_{win['id']}")
            win["active"] = active
        st.markdown("**Exception threshold:**")
        new_thr = st.number_input("Exception rate alert threshold (%)",0.0,10.0,
                                   cfg2.get("exception_threshold_pct",2.0),0.1,key="cl_thr")
        if st.button("💾 Save config",key="cl_cfg_save",type="primary"):
            cfg2["exception_threshold_pct"] = new_thr
            _save_cfg(cfg2); st.cache_data.clear()
            audit_log("CLEARING_CFG_SAVED",uname,"Clearing config updated")
            st.success("✅ Saved"); st.rerun()
    else: st.info("Configuration available to Operations management.")

# ── TAB 6: BSC Impact ─────────────────────────────────────────────
with tabs[6]:
    st.markdown("**Clearing & Settlement KPIs on your BSC:**")
    kpi_info = {"K055":("Exception Rate","lower_better","≤2%"),
                "K056":("Nostro Recon Rate","higher_better","≥98%"),
                "K057":("Settlement TAT","higher_better","≥95%")}
    actuals = {"K055":exc_rate,"K056":recon_rate,
               "K057":round(sum(1 for r in records if r.get("settlement_tat_met"))/max(total,1)*100,1)}
    for kid,(name,direction,target) in kpi_info.items():
        actual = actuals[kid]
        good = (actual<=2.0 if direction=="lower_better" else actual>=90.0)
        st.markdown(f"{'🟢' if good else '🔴'} **{kid} — {name}:** {actual:.1f}% | Target: {target}")
        st.progress(min(actual/100,1.0) if direction=="higher_better" else min((100-actual)/100,1.0))
    if st.button("🔄 Refresh BSC",key="cl_bsc_refresh"):
        _bsc_trigger(uname,"clearing"); st.success("✅ BSC updated"); st.cache_data.clear(); st.rerun()
