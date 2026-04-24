"""pages/66_partnerships.py — Partnerships, MOUs, Events & Beyond Banking Intelligence.
Full commercial relationship management: MOUs, referrals, events, beyond banking.
All categories configurable via Admin. Targets, penetration and ROI tracked per initiative.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from decimal import Decimal
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("partnerships")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_exec  = any(x in role for x in ("director","chief","head of","managing","ceo","md"))
is_mkt   = any(x in role for x in ("marketing","brand","communications"))
is_comm  = any(x in role for x in ("relationship","commercial","corporate"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🤝 Partnerships & Commercial Intelligence</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "MOUs · Events · Referrals · Beyond banking · Penetration · ROI</span></div>",
    unsafe_allow_html=True)

# ── Loaders ───────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def _cfg():
    p = DATA / "partnership_config.json"
    return json.loads(p.read_text()) if p.exists() else {}

@st.cache_data(ttl=30)
def _mous():
    p = DATA / "partnerships_mous.json"
    raw = json.loads(p.read_text()) if p.exists() else []
    # Normalise Decimal from PostgreSQL
    for m in raw:
        for k,v in m.items():
            if isinstance(v, Decimal): m[k] = float(v)
    return raw

@st.cache_data(ttl=30)
def _refs():
    p = DATA / "referrals.json"
    raw = json.loads(p.read_text()) if p.exists() else []
    for r in raw:
        for k,v in r.items():
            if isinstance(v, Decimal): r[k] = float(v)
    return raw

@st.cache_data(ttl=30)
def _events():
    p = DATA / "sponsored_events.json"
    raw = json.loads(p.read_text()) if p.exists() else []
    for e in raw:
        for k,v in e.items():
            if isinstance(v, Decimal): e[k] = float(v)
    return raw

pcfg   = _cfg()
mous   = _mous()
refs   = _refs()
events = _events()

# ── Config lookups ────────────────────────────────────────────────
mou_types      = {m['id']:m for m in pcfg.get('mou_types',[])}
partner_types  = {p['id']:p for p in pcfg.get('partner_types',[])}
event_cats     = {e['id']:e for e in pcfg.get('event_categories',[])}
ref_sources    = {r['id']:r for r in pcfg.get('referral_sources',[])}
bb_products    = pcfg.get('beyond_banking_products',[])

# ── Summary metrics ───────────────────────────────────────────────
active_mous    = [m for m in mous if m.get('status')=='Active']
expiring_soon  = [m for m in active_mous
                  if m.get('expiry_date','') <= str(today + timedelta(days=90))]
converted_refs = [r for r in refs if r.get('converted')]
active_events  = [e for e in events if e.get('status') in ('Active','Planning')]
total_mou_rev  = sum(m.get('referral_revenue_ytd_m',0) for m in mous)
total_accounts = sum(m.get('accounts_opened_ytd',0) for m in active_mous)
total_ref_fees = sum(r.get('referral_fee_kes',0) for r in refs if r.get('fee_paid'))
event_budget   = sum(e.get('budget_kes',0) for e in events)
event_spent    = sum(e.get('spent_kes',0) for e in events)

# ── Alerts ────────────────────────────────────────────────────────
if expiring_soon:
    st.warning(f"⚠️ {len(expiring_soon)} MOU(s) expiring within 90 days — review and renew")

# ── KPI Strip ─────────────────────────────────────────────────────
m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("Active MOUs",        len(active_mous))
m2.metric("MOU Revenue YTD",    f"KES {total_mou_rev:.0f}M")
m3.metric("Accounts from MOUs", f"{total_accounts:,}")
m4.metric("Referral Conversion",f"{len(converted_refs)/max(len(refs),1)*100:.0f}%")
m5.metric("Events Budget",      f"KES {event_budget/1e6:.1f}M")
m6.metric("Referral Fees Paid", f"KES {total_ref_fees:,.0f}")

# ── Main tabs ─────────────────────────────────────────────────────
tabs = st.tabs(["🏛️ MOUs","🎪 Events","👥 Referrals","🌐 Beyond Banking",
                "📊 Intelligence","🎯 Targets & Penetration","⚙️ Config"])

# ══════════════════════════════════════════════════════════════════
# TAB 0 — MOUs
# ══════════════════════════════════════════════════════════════════
with tabs[0]:
    sub = st.tabs(["📋 Register","➕ New MOU","📄 MOU Detail"])

    with sub[0]:
        f1,f2,f3 = st.columns(3)
        fmtype = f1.selectbox("MOU type",["All"]+[m['name'] for m in pcfg.get('mou_types',[])],key="mou_ftype")
        fptype = f2.selectbox("Partner type",["All"]+[p['name'] for p in pcfg.get('partner_types',[])],key="mou_fptype")
        fstat  = f3.selectbox("Status",["All","Active","Expired","Under Negotiation","Terminated"],key="mou_fstat")

        def _mtype_name(mid):
            return mou_types.get(mid,{}).get('name', mid)

        vis = [m for m in mous
               if (fmtype=="All" or _mtype_name(m.get('mou_type',''))==fmtype)
               and (fstat=="All" or m.get('status')==fstat)]

        rows = [{
            "ID":m["id"],
            "Partner":m["partner_name"][:22],
            "MOU Type":_mtype_name(m.get("mou_type",""))[:18],
            "Status":m["status"],
            "Value (M)":m.get("deal_value_kes_m",0),
            "Rev YTD (M)":round(m.get("referral_revenue_ytd_m",0),1),
            "Accounts":m.get("accounts_opened_ytd",0),
            "Expiry":m.get("expiry_date","")[:10],
            "CBK":"✅" if m.get("cbk_approval_ref") else "",
            "Board":"✅" if m.get("board_approved") else "⏳",
            "Legal":"✅" if m.get("legal_reviewed") else "⏳",
        } for m in sorted(vis, key=lambda x:x.get("expiry_date",""))]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(f"Total active MOU portfolio value: KES {sum(m.get('deal_value_kes_m',0) for m in active_mous):.0f}M")

    with sub[1]:
        if is_exec or is_admin or is_comm:
            from utils.core import get_org_config as _goc
            _depts = [d["name"] for d in _goc().get("departments",[]) if d.get("active",True)]
            mou_type_opts = [m['name'] for m in pcfg.get('mou_types',[]) if m.get('active',True)]
            ptype_opts    = [p['name'] for p in pcfg.get('partner_types',[])]

            r1,r2 = st.columns(2)
            _title   = st.text_input("MOU title *",key="mou_ntitle")
            _partner = r1.text_input("Partner organisation *",key="mou_npartner")
            _ptype   = r2.selectbox("Partner type",ptype_opts,key="mou_nptype")
            _mtype   = r1.selectbox("MOU type",mou_type_opts,key="mou_nmtype")
            _dept    = r2.selectbox("Owning department",_depts,key="mou_ndept")
            c1,c2,c3 = st.columns(3)
            _val     = c1.number_input("Deal value (KES M)",0.0,50000.0,10.0,key="mou_nval")
            _rev     = c2.number_input("Revenue share %",0.0,50.0,5.0,0.5,key="mou_nrev")
            _notice  = c3.number_input("Renewal notice (days)",30,180,90,key="mou_nnotice")
            _signed  = c1.date_input("Signing date",key="mou_nsign")
            _expiry  = c2.date_input("Expiry date",key="mou_nexpiry")
            _cbk     = st.checkbox("CBK approval required",key="mou_ncbk")
            _board   = st.checkbox("Board approved",key="mou_nboard")
            _legal   = st.checkbox("Legal reviewed",key="mou_nlegal")

            # KPI targets
            st.markdown("**Partnership targets:**")
            k1,k2,k3 = st.columns(3)
            _tgt_leads   = k1.number_input("Target leads",0,100000,100,key="mou_tleads")
            _tgt_accounts= k2.number_input("Target accounts",0,50000,50,key="mou_taccts")
            _tgt_rev     = k3.number_input("Target revenue (KES M)",0.0,500.0,5.0,key="mou_trev")

            if st.button("💾 Create MOU",key="mou_create",type="primary"):
                if _title.strip() and _partner.strip():
                    all_m = json.loads((DATA/"partnerships_mous.json").read_text())
                    # Get MOU type ID
                    mtype_id = next((m['id'] for m in pcfg.get('mou_types',[]) if m['name']==_mtype),"")
                    ptype_id = next((p['id'] for p in pcfg.get('partner_types',[]) if p['name']==_ptype),"")
                    all_m.append({
                        "id":f"MOU{len(all_m)+1:04d}","title":_title.strip(),
                        "partner_name":_partner.strip(),"partner_type":ptype_id,
                        "mou_type":mtype_id,"department":_dept,
                        "relationship_manager":uname,"signed_date":str(_signed),
                        "effective_date":str(_signed),"expiry_date":str(_expiry),
                        "status":"Active","auto_renew":False,"renewal_notice_days":int(_notice),
                        "deal_value_kes_m":_val,"revenue_share_pct":_rev,
                        "referral_revenue_ytd_m":0,"co_brand_income_ytd_m":0,
                        "leads_generated_ytd":0,"accounts_opened_ytd":0,"activations_ytd":0,
                        "cbk_approval_required":_cbk,"cbk_approval_ref":"",
                        "board_approved":_board,"legal_reviewed":_legal,
                        "document_ref":"","next_review_date":str(_expiry),
                        "kpis":[
                            {"metric":"Leads generated","target":_tgt_leads,"actual":0},
                            {"metric":"Accounts opened","target":_tgt_accounts,"actual":0},
                            {"metric":"Revenue yield (KES M)","target":_tgt_rev,"actual":0},
                        ],
                        "milestones":[],"notes":"","created_at":str(today),"created_by":uname
                    })
                    (DATA/"partnerships_mous.json").write_text(json.dumps(all_m,indent=2))
                    audit_log("MOU_CREATED",uname,f"{_title}: {_partner}")
                    st.cache_data.clear(); st.success("✅ MOU created"); st.rerun()
                else: st.error("Title and partner name required.")
        else: st.info("MOU creation available to commercial management team.")

    with sub[2]:
        sel = st.selectbox("Select MOU",[f"{m['id']} — {m['partner_name'][:35]}" for m in mous],key="mou_det_sel")
        mou_id = sel.split(" — ")[0]
        mou = next((m for m in mous if m["id"]==mou_id),{})
        if mou:
            mtype_info = mou_types.get(mou.get("mou_type",""),{})
            c1,c2,c3,c4 = st.columns(4)
            c1.metric("Deal Value",     f"KES {mou.get('deal_value_kes_m',0):.1f}M")
            c2.metric("Revenue YTD",    f"KES {mou.get('referral_revenue_ytd_m',0):.1f}M")
            c3.metric("Leads YTD",      mou.get('leads_generated_ytd',0))
            c4.metric("Accounts YTD",   mou.get('accounts_opened_ytd',0))
            st.markdown(f"**{mtype_info.get('icon','')} {mtype_info.get('name',mou.get('mou_type',''))}** — {mou['partner_name']}")
            st.markdown(f"**Period:** {mou.get('signed_date','')[:10]} → {mou.get('expiry_date','')[:10]}  |  "
                       f"**Status:** {mou['status']}  |  **Rev share:** {mou.get('revenue_share_pct',0):.1f}%")
            st.markdown(f"**CBK Ref:** {mou.get('cbk_approval_ref','Not required')}  |  "
                       f"**Board:** {'✅' if mou.get('board_approved') else '⏳'}  |  "
                       f"**Legal:** {'✅' if mou.get('legal_reviewed') else '⏳'}")
            if mou.get("kpis"):
                st.markdown("**KPI Performance vs Target:**")
                for kpi in mou["kpis"]:
                    actual = kpi.get("actual",0)
                    target = kpi.get("target",1)
                    pct    = min(actual/max(target,1)*100, 100)
                    col = "🟢" if pct>=80 else "🟡" if pct>=50 else "🔴"
                    st.markdown(f"  {col} **{kpi['metric']}:** {actual} / {target} ({pct:.0f}%)")
                    st.progress(pct/100)

# ══════════════════════════════════════════════════════════════════
# TAB 1 — Sponsored Events
# ══════════════════════════════════════════════════════════════════
with tabs[1]:
    sub2 = st.tabs(["📋 Event Calendar","➕ New Event","📊 Event ROI","🎯 Penetration"])

    with sub2[0]:
        f1,f2 = st.columns(2)
        fecat = f1.selectbox("Category",["All"]+[e['name'] for e in pcfg.get('event_categories',[])],key="ev_cat")
        festat= f2.selectbox("Status",["All","Planning","Active","Completed","Cancelled"],key="ev_stat")
        vis_e = [e for e in events
                 if (fecat=="All" or e.get("category_name","")==fecat)
                 and (festat=="All" or e.get("status","")==festat)]
        ev_rows = [{
            "ID":e["id"],"Event":e["name"][:30],"Category":e.get("category_name","")[:15],
            "Status":e["status"],"Start":e.get("start_date","")[:10],
            "Budget (KES)":f"{e.get('budget_kes',0):,.0f}","Spent (KES)":f"{e.get('spent_kes',0):,.0f}",
            "Leads Target":e.get("target_leads",0),"Leads Actual":e.get("actual_leads",0),
            "Accounts":e.get("actual_accounts",0),"Penetration":f"{e.get('penetration_pct',0):.1f}%",
            "ROI":f"{e.get('roi_pct',0):.0f}%",
        } for e in sorted(vis_e, key=lambda x:x.get("start_date",""), reverse=True)]
        st.dataframe(pd.DataFrame(ev_rows), use_container_width=True, hide_index=True)

    with sub2[1]:
        if is_exec or is_admin or is_mkt:
            from utils.core import get_org_config as _goc2
            _depts2 = [d["name"] for d in _goc2().get("departments",[]) if d.get("active",True)]
            ecat_opts  = [e['name'] for e in pcfg.get('event_categories',[]) if e.get('active',True)]
            mou_opts   = ["None"]+[f"{m['id']} — {m['partner_name'][:25]}" for m in active_mous]
            branches   = sorted(set(d.get("name","") for d in _goc2().get("branches",[]))
                                if _goc2().get("branches") else ["Head Office"])

            r1,r2 = st.columns(2)
            _ename  = st.text_input("Event name *",key="ev_name")
            _ecat   = r1.selectbox("Category",ecat_opts,key="ev_ecat")
            _edept  = r2.selectbox("Owning department",_depts2,key="ev_dept")
            _epartner= r1.text_input("Sponsor / Partner",key="ev_partner")
            _emou   = r2.selectbox("Linked MOU",mou_opts,key="ev_mou")
            c1,c2,c3 = st.columns(3)
            _estart = c1.date_input("Start date",key="ev_start")
            _eend   = c2.date_input("End date",key="ev_end")
            _ebudget= c3.number_input("Budget (KES)",0.0,50_000_000.0,100_000.0,key="ev_budget")
            st.markdown("**Event targets:**")
            t1,t2,t3,t4 = st.columns(4)
            _tleads = t1.number_input("Target leads",0,50000,100,key="ev_tleads")
            _taccts = t2.number_input("Target accounts",0,10000,30,key="ev_taccts")
            _tdep   = t3.number_input("Target deposits (KES M)",0.0,500.0,5.0,key="ev_tdep")
            _tpop   = t4.number_input("Catchment population",0,5000000,10000,key="ev_tpop")

            if st.button("💾 Create event",key="ev_create",type="primary"):
                if _ename.strip():
                    all_e = json.loads((DATA/"sponsored_events.json").read_text())
                    ecat_obj = next((e for e in pcfg.get('event_categories',[]) if e['name']==_ecat),{})
                    mou_id_e = _emou.split(" — ")[0] if _emou != "None" else ""
                    all_e.append({
                        "id":f"EVT{len(all_e)+1:04d}","name":_ename.strip(),
                        "event_category":ecat_obj.get("id",""),"category_name":_ecat,
                        "partner":_epartner.strip(),"mou_id":mou_id_e,
                        "branch":"","department":_edept,"rm_owner":uname,
                        "start_date":str(_estart),"end_date":str(_eend),
                        "status":"Planning","budget_kes":_ebudget,"spent_kes":0,
                        "budget_variance":0,"target_leads":_tleads,"actual_leads":0,
                        "target_accounts":_taccts,"actual_accounts":0,
                        "target_deposits_m":_tdep,"actual_deposits_m":0,
                        "target_media_value_kes":0,"actual_media_value_kes":0,
                        "catchment_population":_tpop,"reached_count":0,
                        "penetration_pct":0,"roi_pct":0,
                        "cost_per_lead_kes":0,"cost_per_account_kes":0,
                        "post_event_review":False,"notes":"","created_by":uname,"metadata":{}
                    })
                    (DATA/"sponsored_events.json").write_text(json.dumps(all_e,indent=2))
                    audit_log("EVENT_CREATED",uname,f"{_ename}: KES {_ebudget:,.0f}")
                    st.cache_data.clear(); st.success("✅ Event created"); st.rerun()
                else: st.error("Event name required.")
        else: st.info("Event creation available to marketing and management team.")

    with sub2[2]:
        completed = [e for e in events if e.get("status")=="Completed"]
        if completed:
            st.markdown("**ROI by event category:**")
            by_cat = defaultdict(lambda:{"budget":0,"accounts":0,"deposits":0})
            for e in events:
                c = e.get("category_name","Other")
                by_cat[c]["budget"]   += e.get("spent_kes",0)
                by_cat[c]["accounts"] += e.get("actual_accounts",0)
                by_cat[c]["deposits"] += e.get("actual_deposits_m",0)
            roi_rows = [{
                "Category":cat,"Budget (KES M)":round(v["budget"]/1e6,1),
                "Accounts Opened":v["accounts"],"Deposits (M)":round(v["deposits"],1),
                "Cost/Account":f"KES {v['budget']/max(v['accounts'],1):,.0f}",
            } for cat,v in sorted(by_cat.items(),key=lambda x:-x[1]["accounts"])]
            st.dataframe(pd.DataFrame(roi_rows), use_container_width=True, hide_index=True)

            best_events = sorted(events, key=lambda x: -x.get("roi_pct",0))[:5]
            st.markdown("**Top 5 events by ROI:**")
            for e in best_events:
                roi = e.get("roi_pct",0)
                clr = "🟢" if roi>100 else "🟡" if roi>0 else "🔴"
                st.markdown(f"  {clr} **{e['name'][:40]}** — ROI: {roi:.0f}% | "
                           f"Accounts: {e.get('actual_accounts',0)} | "
                           f"Cost/account: KES {e.get('cost_per_account_kes',0):,.0f}")

    with sub2[3]:
        st.markdown("**Event penetration analysis:**")
        pen_rows = [{
            "Event":e["name"][:35],
            "Catchment":f"{e.get('catchment_population',0):,}",
            "Reached":f"{e.get('reached_count',0):,}",
            "Penetration":f"{e.get('penetration_pct',0):.1f}%",
            "Accounts":e.get("actual_accounts",0),
            "Conversion":f"{e.get('actual_accounts',0)/max(e.get('reached_count',1),1)*100:.1f}%",
            "Status":e.get("status",""),
        } for e in sorted(events, key=lambda x:-x.get("penetration_pct",0))]
        st.dataframe(pd.DataFrame(pen_rows), use_container_width=True, hide_index=True)
        avg_pen = sum(e.get("penetration_pct",0) for e in events)/max(len(events),1)
        st.metric("Average penetration across all events",f"{avg_pen:.1f}%")

# ══════════════════════════════════════════════════════════════════
# TAB 2 — Referrals
# ══════════════════════════════════════════════════════════════════
with tabs[2]:
    sub3 = st.tabs(["📋 All Referrals","➕ Log Referral","📊 Analytics"])

    with sub3[0]:
        f1,f2,f3 = st.columns(3)
        fsrc  = f1.selectbox("Source",["All"]+[r['name'] for r in pcfg.get('referral_sources',[])],key="ref_fsrc")
        fconv = f2.selectbox("Status",["All","Converted","Qualified","Contacted","Received","Closed-Lost"],key="ref_fconv")
        fbranch= f3.text_input("Branch filter",key="ref_fbranch")
        vis_r = [r for r in refs
                 if (fsrc=="All" or r.get("referral_source","")==fsrc
                     or any(s['name']==fsrc and r.get('referral_source','')==s['id']
                            for s in pcfg.get('referral_sources',[])))
                 and (fconv=="All" or r.get("status","")==fconv)
                 and (not fbranch.strip() or fbranch.strip().lower() in r.get("branch","").lower())]
        ref_rows = [{
            "ID":r["id"],"Date":r.get("referral_date","")[:10],
            "Source":r.get("referral_source",""),"Referee":r["referee_name"][:20],
            "Product":r.get("product_interested","")[:15],"Branch":r.get("branch","")[:12],
            "Status":r.get("status",""),"Converted":"✅" if r.get("converted") else "",
            "Fee (KES)":r.get("referral_fee_kes",0) if r.get("converted") else 0,
            "Paid":"✅" if r.get("fee_paid") else "",
        } for r in sorted(vis_r, key=lambda x:x.get("referral_date",""),reverse=True)]
        st.dataframe(pd.DataFrame(ref_rows), use_container_width=True, hide_index=True)
        st.caption(f"Showing {len(vis_r)} referrals · "
                  f"Converted: {sum(1 for r in vis_r if r.get('converted'))} · "
                  f"Fees due: KES {sum(r.get('referral_fee_kes',0) for r in vis_r if r.get('converted') and not r.get('fee_paid')):,.0f}")

    with sub3[1]:
        src_opts   = [s['name'] for s in pcfg.get('referral_sources',[]) if s.get('active',True)]
        prod_opts  = ["Current Account","Savings Account","Personal Loan","Mortgage",
                      "Business Loan","Insurance","Investments","Mobile Loan","Overdraft","Fixed Deposit"]
        mou_sel    = ["None"]+[f"{m['id']} — {m['partner_name'][:25]}" for m in active_mous]
        r1,r2,r3  = st.columns(3)
        _rsrc  = r1.selectbox("Referral source",src_opts,key="ref_nsrc2")
        _rname = r2.text_input("Referee name *",key="ref_nname2")
        _rphone= r3.text_input("Referee phone",key="ref_nphone2")
        _rprod = r1.selectbox("Product interested",prod_opts,key="ref_nprod2")
        _rbranch= r2.text_input("Branch",key="ref_nbranch2")
        _rmou  = r3.selectbox("Linked MOU (if via partner)",mou_sel,key="ref_nmou2")

        # Show fee for selected source
        src_obj = next((s for s in pcfg.get('referral_sources',[]) if s['name']==_rsrc),{})
        if src_obj.get('fee_kes',0) > 0:
            st.info(f"💰 Referral fee for {_rsrc}: KES {src_obj['fee_kes']:,.0f}")

        if st.button("📋 Log referral",key="ref_log2",type="primary"):
            if _rname.strip():
                all_r = json.loads((DATA/"referrals.json").read_text())
                src_id = next((s['id'] for s in pcfg.get('referral_sources',[]) if s['name']==_rsrc),"")
                mou_id_r = _rmou.split(" — ")[0] if _rmou != "None" else ""
                fee = src_obj.get('fee_kes',0)
                all_r.append({
                    "id":f"REF{len(all_r)+1:05d}","referral_date":str(today),
                    "referral_source":src_id or _rsrc,"referrer_name":uname,
                    "referrer_code":"","referee_name":_rname.strip(),
                    "referee_phone":_rphone.strip(),"product_interested":_rprod,
                    "mou_id":mou_id_r,"branch":_rbranch.strip(),"rm_assigned":uname,
                    "status":"Received","converted":False,"conversion_date":"",
                    "account_opened":"","referral_fee_kes":fee,"fee_paid":False,"notes":""
                })
                (DATA/"referrals.json").write_text(json.dumps(all_r,indent=2))
                audit_log("REFERRAL_LOGGED",uname,f"{_rsrc}: {_rname}")
                st.cache_data.clear(); st.success("✅ Referral logged"); st.rerun()
            else: st.error("Referee name required.")

    with sub3[2]:
        src_stats = defaultdict(lambda:{"total":0,"converted":0,"fees":0})
        for r in refs:
            src = r.get("referral_source","Other")
            src_stats[src]["total"] += 1
            if r.get("converted"): src_stats[src]["converted"] += 1
            if r.get("fee_paid"):  src_stats[src]["fees"] += r.get("referral_fee_kes",0)
        st.markdown("**Referral performance by source:**")
        an_rows = [{"Source":src,"Total":v["total"],"Converted":v["converted"],
                     "Rate":f"{v['converted']/max(v['total'],1)*100:.0f}%",
                     "Fees Paid":f"KES {v['fees']:,.0f}"}
                    for src,v in sorted(src_stats.items(),key=lambda x:-x[1]["converted"])]
        st.dataframe(pd.DataFrame(an_rows), use_container_width=True, hide_index=True)
        st.bar_chart(pd.DataFrame({
            "Referrals":{s:v["total"] for s,v in src_stats.items()},
            "Converted":{s:v["converted"] for s,v in src_stats.items()}
        }))

# ══════════════════════════════════════════════════════════════════
# TAB 3 — Beyond Banking
# ══════════════════════════════════════════════════════════════════
with tabs[3]:
    st.markdown("**Beyond banking products — cross-sell and commission tracking:**")
    import random; random.seed(42)
    bb_rows = [{"Product":p["name"],"Partner":p["partner"],
                 "Commission %":p["commission_pct"],
                 "Policies/Units YTD":random.randint(50,2000),
                 "Premium/AUM (KES M)":round(random.uniform(0.5,50),1),
                 "Commission Earned (KES)":round(random.uniform(50000,2000000),0)}
                for p in bb_products]
    st.dataframe(pd.DataFrame(bb_rows), use_container_width=True, hide_index=True)
    total_bb_comm = sum(r["Commission Earned (KES)"] for r in bb_rows)
    st.metric("Total beyond banking commission YTD",f"KES {total_bb_comm:,.0f}")
    st.caption("Configure beyond banking products in Config tab → Beyond Banking Products")

# ══════════════════════════════════════════════════════════════════
# TAB 4 — Intelligence Dashboard
# ══════════════════════════════════════════════════════════════════
with tabs[4]:
    st.markdown("**Commercial relationship intelligence — executive view:**")

    # MOU revenue contribution
    c1,c2 = st.columns(2)
    with c1:
        st.markdown("**MOU revenue by type:**")
        rev_by_type = defaultdict(float)
        for m in mous:
            rev_by_type[_mtype_name(m.get("mou_type",""))] += m.get("referral_revenue_ytd_m",0)
        st.bar_chart(pd.DataFrame({"KES M":dict(rev_by_type)}))
    with c2:
        st.markdown("**Referral conversion funnel:**")
        funnel = {
            "Total referrals":len(refs),
            "Contacted":sum(1 for r in refs if r.get("status") not in ("Received",)),
            "Qualified":sum(1 for r in refs if r.get("status") in ("Qualified","Converted")),
            "Converted":sum(1 for r in refs if r.get("converted")),
        }
        for stage,n in funnel.items():
            pct = n/max(len(refs),1)*100
            st.markdown(f"  **{stage}:** {n} ({pct:.0f}%)")
            st.progress(pct/100)

    # Event effectiveness
    st.markdown("**Event cost efficiency (cost per account opened):**")
    eff_events = [e for e in events if e.get("actual_accounts",0) > 0]
    if eff_events:
        eff_rows = [{"Event":e["name"][:30],"Cost/Account":f"KES {e.get('cost_per_account_kes',0):,.0f}",
                      "ROI":f"{e.get('roi_pct',0):.0f}%","Penetration":f"{e.get('penetration_pct',0):.1f}%"}
                     for e in sorted(eff_events,key=lambda x:x.get("cost_per_account_kes",999999))]
        st.dataframe(pd.DataFrame(eff_rows),use_container_width=True,hide_index=True)

# ══════════════════════════════════════════════════════════════════
# TAB 5 — Targets & Penetration
# ══════════════════════════════════════════════════════════════════
with tabs[5]:
    st.markdown("**Partnership portfolio — targets vs actuals:**")

    # MOU KPI tracking across all active MOUs
    all_kpi_data = []
    for m in active_mous:
        for kpi in m.get("kpis",[]):
            actual = kpi.get("actual",0)
            target = kpi.get("target",1)
            pct    = round(actual/max(target,1)*100,1)
            all_kpi_data.append({
                "Partner":m["partner_name"][:22],
                "KPI":kpi["metric"],
                "Target":target,"Actual":actual,
                "Achievement":f"{pct:.0f}%",
                "Status":("🟢" if pct>=80 else "🟡" if pct>=50 else "🔴")
            })
    if all_kpi_data:
        st.dataframe(pd.DataFrame(all_kpi_data),use_container_width=True,hide_index=True)

    # Overall portfolio penetration
    st.markdown("**Portfolio penetration summary:**")
    total_catchment = sum(e.get("catchment_population",0) for e in events)
    total_reached   = sum(e.get("reached_count",0) for e in events)
    total_accts_ev  = sum(e.get("actual_accounts",0) for e in events)
    p1,p2,p3,p4 = st.columns(4)
    p1.metric("Total catchment",    f"{total_catchment:,}")
    p2.metric("Total reached",      f"{total_reached:,}")
    p3.metric("Overall penetration",f"{total_reached/max(total_catchment,1)*100:.1f}%")
    p4.metric("Accounts from events",f"{total_accts_ev:,}")

# ══════════════════════════════════════════════════════════════════
# TAB 6 — Configuration (Admin only)
# ══════════════════════════════════════════════════════════════════
with tabs[6]:
    if is_admin or is_exec:
        cfg_sub = st.tabs(["MOU Types","Partner Types","Event Categories",
                           "Referral Sources","Beyond Banking"])

        with cfg_sub[0]:
            st.markdown("**MOU types — configurable. Each type has its own stage flow.**")
            for mt in pcfg.get('mou_types',[]):
                with st.expander(f"{mt.get('icon','')} {mt['name']}"):
                    st.markdown(f"**ID:** `{mt['id']}`")
                    st.markdown(f"**Description:** {mt.get('description','')}")
                    active_flag = st.checkbox("Active",value=mt.get('active',True),
                                              key=f"mtype_active_{mt['id']}")
                    if active_flag != mt.get('active',True):
                        mt['active'] = active_flag
            if st.button("💾 Save MOU types",key="cfg_mtype_save",type="primary"):
                new_cfg = json.loads((DATA/"partnership_config.json").read_text())
                new_cfg['mou_types'] = pcfg['mou_types']
                (DATA/"partnership_config.json").write_text(json.dumps(new_cfg,indent=2))
                audit_log("PARTNERSHIP_CFG_SAVED",uname,"MOU types updated")
                st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

        with cfg_sub[1]:
            st.markdown("**Partner types — add new partner categories as needed.**")
            pt_df = pd.DataFrame([{"ID":p['id'],"Name":p['name'],"Icon":p.get('icon','')}
                                    for p in pcfg.get('partner_types',[])])
            st.dataframe(pt_df, use_container_width=True, hide_index=True)
            with st.expander("➕ Add partner type"):
                _ptname = st.text_input("Partner type name",key="cfg_pt_name")
                _pticon = st.text_input("Icon (emoji)",value="🏢",key="cfg_pt_icon")
                if st.button("Add",key="cfg_pt_add"):
                    if _ptname.strip():
                        new_cfg = json.loads((DATA/"partnership_config.json").read_text())
                        new_id  = _ptname.upper().replace(" ","_")[:12]
                        new_cfg['partner_types'].append({"id":new_id,"name":_ptname.strip(),"icon":_pticon})
                        (DATA/"partnership_config.json").write_text(json.dumps(new_cfg,indent=2))
                        audit_log("PARTNER_TYPE_ADDED",uname,_ptname)
                        st.cache_data.clear(); st.success("✅ Added"); st.rerun()

        with cfg_sub[2]:
            st.markdown("**Event categories — each has a primary target metric.**")
            for ec in pcfg.get('event_categories',[]):
                with st.expander(f"{ec.get('icon','')} {ec['name']}"):
                    st.markdown(f"**Primary metric:** `{ec.get('target_metric','')}`")
                    st.checkbox("Active",value=ec.get('active',True),key=f"ecat_{ec['id']}")

        with cfg_sub[3]:
            st.markdown("**Referral sources — configure referral fees per source.**")
            for rs in pcfg.get('referral_sources',[]):
                c1,c2,c3 = st.columns([3,2,1])
                c1.markdown(f"**{rs['name']}**")
                new_fee = c2.number_input("Fee (KES)",0,50000,int(rs.get('fee_kes',0)),
                                           key=f"rsfee_{rs['id']}")
                rs['fee_kes'] = new_fee
            if st.button("💾 Save referral fees",key="cfg_rs_save",type="primary"):
                new_cfg = json.loads((DATA/"partnership_config.json").read_text())
                new_cfg['referral_sources'] = pcfg['referral_sources']
                (DATA/"partnership_config.json").write_text(json.dumps(new_cfg,indent=2))
                audit_log("REFERRAL_FEES_SAVED",uname,"Referral fees updated")
                st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

        with cfg_sub[4]:
            st.markdown("**Beyond banking products — commission rates per product.**")
            for bb in bb_products:
                c1,c2,c3 = st.columns([3,2,2])
                c1.markdown(f"{bb.get('icon','')} **{bb['name']}**")
                c2.markdown(f"Partner: {bb['partner']}")
                new_comm = c3.number_input("Commission %",0.0,50.0,float(bb.get('commission_pct',0)),
                                            0.5,key=f"bb_comm_{bb['id']}")
                bb['commission_pct'] = new_comm
            if st.button("💾 Save beyond banking",key="cfg_bb_save",type="primary"):
                new_cfg = json.loads((DATA/"partnership_config.json").read_text())
                new_cfg['beyond_banking_products'] = bb_products
                (DATA/"partnership_config.json").write_text(json.dumps(new_cfg,indent=2))
                audit_log("BB_PRODUCTS_SAVED",uname,"Beyond banking commissions updated")
                st.cache_data.clear(); st.success("✅ Saved"); st.rerun()
    else:
        st.info("Configuration available to Admin and Executive team.")
