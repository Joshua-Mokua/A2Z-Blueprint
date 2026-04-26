"""pages/28_ra.py — Reporting & Analytics (RA) Module."""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date
from pages._shared import load_shared_state
from pages._access import require_access

require_access("ra")
_ = audit_log("RA_PAGE_VIEWED", uname, "RA dashboard viewed") if "uname" in dir() else None

def _bsc_trigger(username: str, kpi: str = ""):
    """Non-blocking BSC update."""
    try:
        from utils.core import update_bsc_from_modules as _ubm, audit_log
        _ubm(username)
    except Exception:
        pass

DATA  = Path(__file__).parent.parent / "data"

um, ud, uname, *_rest = load_shared_state()[:12]
sc = str(ud.get("staff_code","") or "")
role = ud.get("role","")
name = ud.get("full_name","")
is_admin = ud.get("is_admin", False)
is_exec = any(x in role for x in (
    "Chief","Director","Managing","Head","Manager","Senior Manager","Financial Controller",
    "General Manager","Area Manager","Branch Manager","Senior Branch"))
# Allow all — RA shows relevant data for the user's scope
# Branch manager sees their branch; MD sees everything

@st.cache_data(ttl=60, show_spinner=False)
def load_all():
    def jl(f):
        p = DATA / f; return a2z_db.load_json(p) if p.exists() else {}
    def ja(f):
        p = DATA / f; return a2z_db.load_json(p) if p.exists() else []
    return {
        "scores":    jl("feb_2026_staff_scores.json"),
        "pipeline":  ja("pipeline.json"),
        "apps":      ja("loan_applications.json"),
        "legal":     ja("legal_matters.json"),
        "comp":      ja("compliance_cases.json"),
        "treasury":  ja("treasury_fd.json"),
        "ei":        ja("execute_initiatives.json"),
        "pperf":     jl("proposition_performance.json"),
        "pcfg":      jl("proposition_config.json"),
        "campaigns": ja("campaigns.json"),
        "commission":ja("commission_records.json"),
        "products":  ja("products.json"),
    }

d       = load_all()
scores  = d["scores"];    pipeline = d["pipeline"]; apps = d["apps"]
legal   = d["legal"];     comp     = d["comp"];     treasury = d["treasury"]
ei      = d["ei"];        pperf    = d["pperf"];    pcfg = d["pcfg"]
campaigns = d["campaigns"]; commission = d["commission"]; products = d["products"]

st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>📊 Reporting & Analytics</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Cross-module executive intelligence · Live data</span></div>",
    unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# Restructured: 2-level navigation for clarity
# ─────────────────────────────────────────────────────────────────
sections = st.tabs([
    "🏛️ Executive",
    "📊 Performance",
    "⚙️ Operational",
    "💸 Sales",
])

# ── Section 0: 🏛️ Executive ─────────────────────────────
with sections[0]:
    sub = st.tabs([
        "🏦 Executive Summary",
        "🔍 MD Drill-down",
        "📅 Month-end Pack",
    ])
    with sub[0]:
        total_staff = len(scores)
        avg_bsc     = sum(s["final_score"] for s in scores.values())/max(total_staff,1)
        above_3     = sum(1 for s in scores.values() if s["final_score"]>=3.0)
        below_25    = sum(1 for s in scores.values() if s["final_score"]<2.5)

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Avg BSC Score",    f"{avg_bsc:.2f}/5.0")
        c2.metric("Staff Scored",     f"{total_staff:,}")
        c3.metric("On Track (≥3.0)", f"{above_3:,}",  f"{above_3/total_staff*100:.0f}%")
        c4.metric("At Risk (<2.5)",  f"{below_25:,}")
        c5.metric("Outstanding (≥4)",f"{sum(1 for s in scores.values() if s['final_score']>=4.0):,}")
        st.markdown("---")

        active_deals = [d for d in pipeline if d.get("stage") not in ("Closed Won","Closed Lost")]
        won_deals    = [d for d in pipeline if d.get("stage")=="Closed Won"]
        pending_apps = sum(1 for a in apps if a["status"] in ("submitted","assigned","analysis"))
        disb_vol     = sum(a.get("amount",0) for a in apps if a["status"]=="disbursed")/1e9
        sla_breach   = sum(1 for a in apps if a.get("tat_days",0)>a.get("sla_target_days",10)
                           and a["status"] not in ("approved","credit_admin","disbursed","declined"))

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Active Pipeline",  f"KES {sum(float(d.get('amount',0)) for d in active_deals)/1e9:.1f}B")
        c2.metric("Won This Period",  f"KES {sum(float(d.get('amount',0)) for d in won_deals)/1e9:.1f}B")
        c3.metric("Apps Pending",     f"{pending_apps}")
        c4.metric("Disbursed Vol",    f"KES {disb_vol:.1f}B")
        c5.metric("SLA Breaches",     f"{sla_breach}")
        st.markdown("---")

        open_legal  = sum(1 for m in legal if m["status"] not in ("completed","on_hold"))
        open_comp   = sum(1 for c in comp if c["status"] in ("open","under_review"))
        fd_pend     = sum(1 for r in treasury if r["status"]=="pending")
        init_active = sum(1 for i in ei if i.get("status","Active")=="Active")
        avg_prop    = sum(p["proposition_score"] for p in pperf.values())/max(len(pperf),1)

        c1,c2,c3,c4,c5 = st.columns(5)
        c1.metric("Open Legal",      f"{open_legal}")
        c2.metric("Open Compliance", f"{open_comp}")
        c3.metric("FD Pending",      f"{fd_pend}")
        c4.metric("Initiatives",     f"{init_active} active")
        c5.metric("Avg Prop Score",  f"{avg_prop:.2f}")

        st.markdown("---")
        st.markdown("**BSC score distribution:**")
        buckets = ["1.0-1.9","2.0-2.4","2.5-2.9","3.0-3.4","3.5-3.9","4.0-4.4","4.5-5.0"]
        ranges  = [(1.0,2.0),(2.0,2.5),(2.5,3.0),(3.0,3.5),(3.5,4.0),(4.0,4.5),(4.5,5.01)]
        counts  = [sum(1 for s in scores.values() if lo<=s["final_score"]<hi) for lo,hi in ranges]
        st.bar_chart(pd.DataFrame({"Staff":counts},index=buckets))

        # ── TAB 2: BSC League Table ─────────────────────────────────────────
    with sub[1]:
        units=["All"]+sorted(set(s.get("unit","") for s in scores.values() if s.get("unit","")))
        sel_u=st.selectbox("Select unit",units,key="md_unit")
        us={k:v for k,v in scores.items() if sel_u=="All" or v.get("unit","")==sel_u}
        if us:
            avg_u=sum(s["final_score"] for s in us.values())/max(len(us),1)
            top_s=sorted(us.items(),key=lambda x:-x[1]["final_score"])
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Staff",len(us)); c2.metric("Unit Avg",f"{avg_u:.2f}")
            c3.metric("Top Score",f"{top_s[0][1]['final_score']:.2f}" if top_s else "—")
            c4.metric("Bottom",f"{sorted(us.items(),key=lambda x:x[1]['final_score'])[0][1]['final_score']:.2f}" if us else "—")

            df_u=pd.DataFrame([{"Code":k,"Name":s["name"][:28],"Role":s["role"][:35],
                "BSC":s["final_score"],"KPIs":s["n_kpis"],
                "Band":("🔴" if s["final_score"]<2.5 else "🟡" if s["final_score"]<3.5 else "🟢" if s["final_score"]<4.5 else "⭐")}
                for k,s in sorted(us.items(),key=lambda x:-x[1]["final_score"])])
            st.dataframe(df_u,use_container_width=True,hide_index=True)

            st.markdown("---")
            sel_st=st.selectbox("Drill into staff member",
                ["— select —"]+[f"{k} — {s['name']}" for k,s in sorted(us.items(),key=lambda x:x[1]["name"])],key="md_st")
            if sel_st!="— select —":
                sel_sc=sel_st.split(" — ")[0]; _s=scores.get(sel_sc,{})
                st.markdown(f"#### {_s.get('name','')} · {_s.get('role','')} · {_s.get('unit','')}")
                c1,c2,c3=st.columns(3)
                c1.metric("BSC Score",f"{_s.get('final_score',0):.2f}/5.0")
                c2.metric("Pipeline Deals",sum(1 for d in pipeline if str(d.get("staff_code",""))==sel_sc))
                c3.metric("LMS Apps",sum(1 for a in apps if str(a.get("rm_code",""))==sel_sc))

        # ── TAB 9: Month-end Executive Pack ─────────────────────────────────
    with sub[2]:
        st.markdown("**Month-end executive pack — one-click board summary**")

        _today_d  = date.today()
        _import_calendar = __import__("calendar")
        _last_day = _import_calendar.monthrange(_today_d.year, _today_d.month)[1]
        _period   = _today_d.strftime("%B %Y")
        _days_rem = _last_day - _today_d.day

        if _days_rem <= 5:
            st.success(f"📅 Month-end is {_days_rem} days away — pack is ready to generate")

        # BSC snapshot
        _total_s  = len(scores)
        _avg_bsc  = sum(s["final_score"] for s in scores.values())/_total_s if _total_s else 0
        _above35  = sum(1 for s in scores.values() if s["final_score"]>=3.5)
        _below25  = sum(1 for s in scores.values() if s["final_score"]<2.5)

        # Credit snapshot
        _apps_eom = json.loads((DATA/"loan_applications.json").read_text()) if (DATA/"loan_applications.json").exists() else []
        _decided  = [a for a in _apps_eom if a["status"] in ("approved","declined","disbursed","credit_admin","returned")]
        _approval_rate = sum(1 for a in _decided if a["status"] in ("approved","credit_admin","disbursed"))/max(len(_decided),1)*100
        _disb_vol = sum(a.get("amount",0) for a in _apps_eom if a["status"]=="disbursed")/1e9

        # Treasury snapshot
        _fd_eom   = json.loads((DATA/"treasury_fd.json").read_text()) if (DATA/"treasury_fd.json").exists() else []
        _fd_book  = sum(r["amount"] for r in _fd_eom if r["status"] in ("approved","booked") and r["currency"]=="KES")/1e9

        # Pipeline snapshot
        _pip_active = [d for d in pipeline if d.get("stage") not in ("Closed Won","Closed Lost")]
        _pip_val    = sum(float(d.get("amount",0)) for d in _pip_active)/1e9

        st.markdown("---")
        st.markdown(f"## Ecobank Kenya — {_period} Performance Summary")

        # Row 1: Performance
        pc1,pc2,pc3,pc4 = st.columns(4)
        pc1.metric("Avg BSC Score", f"{_avg_bsc:.2f}/5.0", f"{_total_s:,} staff scored")
        pc2.metric("On Track (≥3.5)", f"{_above35:,}", f"{_above35/_total_s*100:.0f}%")
        pc3.metric("At Risk (<2.5)", f"{_below25:,}")
        pc4.metric("Approval Rate", f"{_approval_rate:.1f}%", f"{len(_decided)} decided")

        # Row 2: Financial
        fc1,fc2,fc3,fc4 = st.columns(4)
        fc1.metric("Disbursed Volume", f"KES {_disb_vol:.1f}B")
        fc2.metric("FD Book", f"KES {_fd_book:.1f}B")
        fc3.metric("Active Pipeline", f"KES {_pip_val:.1f}B")
        fc4.metric("Prop Score (avg)", f"{sum(p['proposition_score'] for p in pperf.values())/max(len(pperf),1):.2f}")

        st.markdown("---")

        # Generate Excel pack
        if st.button("📥 Generate Month-end Executive Pack (Excel)", type="primary", key="eom_pack"):
            try:
                import io as _io
                import pandas as _pd_eom, openpyxl as _oxl

                _buf = _io.BytesIO()
                with _pd_eom.ExcelWriter(_buf, engine="openpyxl") as _writer:
                    # Sheet 1: BSC Summary
                    _bsc_rows = [{"Staff Code":k,"Name":v["name"][:28],"Role":v["role"][:30],
                                   "Unit":v["unit"][:20],"BSC Score":v["final_score"],
                                   "Band":"Exceeds" if v["final_score"]>=3.5 else "Meets" if v["final_score"]>=2.5 else "Below"}
                                  for k,v in sorted(scores.items(),key=lambda x:-x[1]["final_score"])]
                    _pd_eom.DataFrame(_bsc_rows).to_excel(_writer, sheet_name="BSC Scores", index=False)

                    # Sheet 2: Credit Portfolio
                    _cr_rows = [{"ID":a["id"],"Client":a["client_name"][:25],"Product":a["product"],
                                  "Amount (KES M)":round(a.get("amount",0)/1e6,2),"Status":a["status"],
                                  "RM":a.get("rm_name","")[:20]}
                                 for a in _apps_eom[:500]]
                    _pd_eom.DataFrame(_cr_rows).to_excel(_writer, sheet_name="Credit Portfolio", index=False)

                    # Sheet 3: Pipeline
                    _pp_rows = [{"ID":d["id"],"Client":d.get("client_name","")[:25],"Product":d.get("product",""),
                                  "Amount (M)":round(float(d.get("amount",0))/1e6,1),"Stage":d.get("stage",""),
                                  "Prop":d.get("proposition_tag",""),"AI Win%":f"{d.get('win_probability_ai',0)*100:.0f}%"}
                                 for d in sorted(pipeline,key=lambda x:-float(x.get("amount",0)))]
                    _pd_eom.DataFrame(_pp_rows).to_excel(_writer, sheet_name="Pipeline", index=False)

                    # Sheet 4: Propositions
                    _prop_rows = [{"Proposition":pcfg.get("propositions",{}).get(t,{}).get("name",t),
                                    "Score":p["proposition_score"],"Customers":p.get("total_tagged_customers",0)}
                                   for t,p in pperf.items()]
                    _pd_eom.DataFrame(_prop_rows).to_excel(_writer, sheet_name="Propositions", index=False)

                _buf.seek(0)
                st.download_button(
                    f"📥 Download {_period} Executive Pack",
                    data=_buf.getvalue(),
                    file_name=f"EcoBank_{_today_d.strftime('%Y%m')}_ExecutivePack.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="eom_dl")
                st.success("✅ Pack ready — 4 sheets: BSC Scores, Credit Portfolio, Pipeline, Propositions")
            except Exception as _e:
                st.error(f"Could not generate pack: {str(_e)[:100]}")

# ── Section 1: 📊 Performance ─────────────────────────────
with sections[1]:
    sub = st.tabs([
        "🏆 BSC League Table",
        "🎯 Proposition vs Portfolio",
    ])
    with sub[0]:
        _view = st.selectbox("View by", ["All Staff","By Unit (avg)","By Role Group","Top 50","Bottom 50"], key="lt_view")
        rows = []
        for sc_v, s in scores.items():
            rl = s["role"].lower()
            grp = ("Executive" if any(x in rl for x in ("chief","director","managing")) else
                   "Credit"    if any(x in rl for x in ("credit","analyst")) else
                   "Legal"     if "legal" in rl else
                   "Treasury"  if any(x in rl for x in ("treasury","dealer")) else
                   "Compliance"if any(x in rl for x in ("compliance","risk")) else "Retail")
            rows.append({"Code":sc_v,"Name":s["name"][:28],"Role":s["role"][:35],
                         "Unit":s["unit"][:25],"BSC Score":s["final_score"],
                         "KPIs":s["n_kpis"],"Avg Ach":f"{s['avg_ach']:.0f}%",
                         "Band":("🔴 Below" if s["final_score"]<2.5 else
                                 "🟡 Meets" if s["final_score"]<3.5 else
                                 "🟢 Exceeds" if s["final_score"]<4.5 else "⭐ Outstanding"),
                         "_grp":grp})

        df = pd.DataFrame(rows)
        if _view == "Top 50":     df=df.nlargest(50,"BSC Score")
        elif _view == "Bottom 50":df=df.nsmallest(50,"BSC Score")
        elif _view == "By Unit (avg)":
            df2=df.groupby("Unit")["BSC Score"].mean().reset_index().sort_values("BSC Score",ascending=False)
            df2["BSC Score"]=df2["BSC Score"].round(2)
            df2.insert(0,"Rank",range(1,len(df2)+1))
            st.dataframe(df2,use_container_width=True,hide_index=True); st.stop()
        elif _view == "By Role Group":
            df2=df.groupby("_grp")["BSC Score"].agg(["mean","count"]).reset_index()
            df2.columns=["Group","Avg BSC","Staff Count"]
            df2["Avg BSC"]=df2["Avg BSC"].round(2)
            st.dataframe(df2.sort_values("Avg BSC",ascending=False),use_container_width=True,hide_index=True); st.stop()

        df=df.drop(columns=["_grp"]).sort_values("BSC Score",ascending=False).reset_index(drop=True)
        df.index=df.index+1
        st.dataframe(df, use_container_width=True)
        st.caption(f"{len(df):,} staff · avg {df['BSC Score'].mean():.2f}")

        # ── TAB 3: Pipeline Analytics ───────────────────────────────────────
    with sub[1]:
        st.caption("Proposition = influence metrics. Portfolio = primary P&L. No double-counting.")
        prop_rows=[]
        for tag,perf in pperf.items():
            cfg=pcfg.get("propositions",{}).get(tag,{})
            pdp=[d for d in pipeline if d.get("proposition_tag")==tag]
            pap=[a for a in apps if a.get("proposition_tag")==tag]
            pvol=sum(a.get("amount",0) for a in pap if a.get("status")=="disbursed")
            prop_rows.append({"":cfg.get("icon",""),"Proposition":cfg.get("name",tag),
                               "Score":perf.get("proposition_score",0),
                               "Band":("🟢" if perf.get("proposition_score",0)>=3.5 else "🟡" if perf.get("proposition_score",0)>=2.5 else "🔴"),
                               "Tagged Customers":perf.get("total_tagged_customers",0),
                               "Pipeline":len(pdp),"LMS Apps":len(pap),"Disbursed (KES M)":round(pvol/1e6,1)})
        st.dataframe(pd.DataFrame(prop_rows).sort_values("Score",ascending=False),use_container_width=True,hide_index=True)

        sel_p=st.selectbox("Drill into:",
            [f"{pcfg['propositions'][t]['icon']} {pcfg['propositions'][t]['name']}" for t in pperf],key="ra_prop")
        sel_t=next(t for t in pperf if f"{pcfg['propositions'][t]['icon']} {pcfg['propositions'][t]['name']}"==sel_p)
        kpr=[{"KPI":k["name"],"Target":k["target"],"Actual":k.get("actual",0),
              "Ach":f"{k.get('achievement',0):.1f}%","Score":k.get("score",0),"Wt":f"{k['weight']:.0%}"}
             for k in sorted(pperf[sel_t]["kpis"],key=lambda x:-x.get("achievement",0))]
        st.dataframe(pd.DataFrame(kpr),use_container_width=True,hide_index=True)

        # ── TAB 6: Initiative Tracker ───────────────────────────────────────

# ── Section 2: ⚙️ Operational ─────────────────────────────
with sections[2]:
    sub = st.tabs([
        "🏦 Credit Portfolio",
        "💼 Pipeline Analytics",
        "🚀 Initiative Tracker",
    ])
    with sub[0]:
        decided=[a for a in apps if a["status"] in ("approved","declined","returned","credit_admin","disbursed")]
        td=max(len(decided),1)
        c1,c2,c3,c4,c5=st.columns(5)
        c1.metric("Total Apps",      len(apps))
        c2.metric("Approval Rate",   f"{sum(1 for a in decided if a['status'] in ('approved','credit_admin','disbursed'))/td*100:.1f}%")
        c3.metric("Decline Rate",    f"{sum(1 for a in decided if a['status']=='declined')/td*100:.1f}%")
        c4.metric("Rework Rate",     f"{sum(1 for a in decided if a['status']=='returned')/td*100:.1f}%")
        c5.metric("Pending Queue",   sum(1 for a in apps if a["status"] in ("submitted","assigned","analysis")))

        st.markdown("**TAT by swim lane:**")
        for lane,sla in [("Express",3),("Standard",10),("Complex",21)]:
            la=[a for a in decided if a.get("swim_lane")==lane]
            if not la: continue
            avg_t=round(sum(a.get("tat_days",0) for a in la)/len(la),1)
            ot=sum(1 for a in la if a.get("tat_days",0)<=sla)
            icon="✅" if ot/max(len(la),1)>=0.8 else "🟡" if ot/max(len(la),1)>=0.6 else "🔴"
            st.markdown(f"  {icon} **{lane}** SLA {sla}d: avg {avg_t}d · {ot/max(len(la),1)*100:.0f}% on-time ({ot}/{len(la)})")

        # ── TAB 5: Proposition vs Portfolio ────────────────────────────────
    with sub[1]:
        active=[d for d in pipeline if d.get("stage") not in ("Closed Won","Closed Lost")]
        won   =[d for d in pipeline if d.get("stage")=="Closed Won"]
        lost  =[d for d in pipeline if d.get("stage")=="Closed Lost"]
        conv_r=round(len(won)/(len(won)+len(lost))*100,1) if (won or lost) else 0

        c1,c2,c3,c4,c5=st.columns(5)
        c1.metric("Active Deals",    len(active))
        c2.metric("Pipeline Value",  f"KES {sum(float(d.get('amount',0)) for d in active)/1e9:.1f}B")
        c3.metric("Won",             len(won))
        c4.metric("Conversion Rate", f"{conv_r}%")
        c5.metric("Lost",            len(lost))

        st.markdown("**By stage:**")
        STAGES=["Lead","Prospecting","Needs Analysis","Proposal","Negotiation","Credit Review","Credit Approval","Credit Committee","Disbursed"]
        sc2=Counter(d.get("stage","") for d in active)
        df_st=pd.DataFrame([{"Stage":s,"Deals":sc2.get(s,0),"Value (KES M)":round(sum(float(x.get("amount",0)) for x in active if x.get("stage")==s)/1e6,0)} for s in STAGES if sc2.get(s,0)>0])
        st.dataframe(df_st,use_container_width=True,hide_index=True)

        st.markdown("**By proposition:**")
        ptag=Counter(d.get("proposition_tag") for d in active if d.get("proposition_tag"))
        pval=defaultdict(float)
        for d in active:
            if d.get("proposition_tag"): pval[d["proposition_tag"]]+=float(d.get("amount",0))
        df_pp=pd.DataFrame([{"Prop":pcfg.get("propositions",{}).get(t,{}).get("icon","")+" "+pcfg.get("propositions",{}).get(t,{}).get("name",t),"Deals":n,"Value (KES B)":round(pval[t]/1e9,2)} for t,n in ptag.most_common()])
        if not df_pp.empty: st.dataframe(df_pp,use_container_width=True,hide_index=True)

        # ── TAB 4: Credit Portfolio ─────────────────────────────────────────
    with sub[2]:
        gates={};
        for i in ei:
            g=i.get("current_gate") or i.get("gate","G0"); gates[g]=gates.get(g,0)+1
        cols=st.columns(6)
        for col,g in zip(cols,["G0","G1","G2","G3","G4","G5"]): col.metric(g,gates.get(g,0))
        tb=sum(float(i.get("budget",0)) for i in ei)/1e9
        ts=sum(float(i.get("spent",0)) for i in ei)/1e9
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Budget",f"KES {tb:.1f}B"); c2.metric("Spent",f"KES {ts:.1f}B")
        c3.metric("Utilised",f"{ts/max(tb,0.001)*100:.1f}%"); c4.metric("Active",sum(1 for i in ei if i.get("status","Active")=="Active"))
        df_ei=pd.DataFrame([{"Gate":i.get("current_gate") or i.get("gate",""),
            "Name":i.get("name","")[:45],"Status":i.get("status",""),
            "Budget (M)":round(float(i.get("budget",0))/1e6,0),"Spent (M)":round(float(i.get("spent",0))/1e6,0),
            "Owner":(i.get("owner") or i.get("io",""))[:25]}
            for i in sorted(ei,key=lambda x:x.get("current_gate") or x.get("gate","G0"))])
        st.dataframe(df_ei,use_container_width=True,hide_index=True)

        # ── TAB 7: Campaigns & Commission ──────────────────────────────────

# ── Section 3: 💸 Sales ─────────────────────────────
with sections[3]:
    t1,t2=st.tabs(["📣 Campaigns","💰 Commission"])
    with t1:
        if not campaigns: st.info("No campaign data.")
        else:
            ac=[c for c in campaigns if c.get("status")=="Active"]
            co=[c for c in campaigns if c.get("status")=="Completed"]
            avg_cv=round(sum(c.get("conversion_rate",0) for c in co)/max(len(co),1),1)
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Total",len(campaigns)); c2.metric("Active",len(ac))
            c3.metric("Completed",len(co)); c4.metric("Avg Conv",f"{avg_cv}%")
            df_c=pd.DataFrame([{"Name":c["name"][:35],"Type":c["type"],"Branch":c["branch"][:20],
                "Status":c["status"],"Target":c.get("target_accounts",0),
                "Actual":c.get("actual_accounts",0),"Conv %":f"{c.get('conversion_rate',0):.0f}%"}
                for c in sorted(campaigns,key=lambda x:-x.get("conversion_rate",0))])
            st.dataframe(df_c,use_container_width=True,hide_index=True)
    with t2:
        if not commission: st.info("No commission data.")
        else:
            tc=sum(r.get("total_commission",0) for r in commission)/1e6
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Total Payable",f"KES {tc:.1f}M"); c2.metric("Records",len(commission))
            c3.metric("Approved",sum(1 for r in commission if r.get("status")=="Approved"))
            c4.metric("Avg per RM",f"KES {tc/max(len(commission),1)*1e6:,.0f}")
            tiers=Counter(r.get("tier","") for r in commission)
            st.markdown("**Tiers:** "+" | ".join(f"**{t}** {n}" for t,n in sorted(tiers.items())))
            df_cm=pd.DataFrame([{"Name":r["staff_name"][:25],"Tier":r["tier"],
                "BSC":r["bsc_score"],"Perf (KES)":f"{r.get('performance_commission',0):,.0f}",
                "Sales (KES)":f"{r.get('sales_commission',0):,.0f}",
                "Total (KES)":f"{r.get('total_commission',0):,.0f}","Status":r.get("status","")}
                for r in sorted(commission,key=lambda x:-x.get("total_commission",0))[:50]])
            st.dataframe(df_cm,use_container_width=True,hide_index=True)

    # ── TAB 8: MD Drill-down ────────────────────────────────────────────

