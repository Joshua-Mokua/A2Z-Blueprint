"""pages/25_treasury.py — Full Treasury Management System.
FD ratification, FX dealing, Money Market, Government Securities,
Dealing Blotter, Nostro, ALM/Liquidity ratios, Limits & compliance.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date, timedelta
from pages._shared import load_shared_state
from utils.core_audit import audit_log, requires_dual_approval, submit_for_approval
from pages._access import require_access
from utils.core import fmt_kpi_value

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()



require_access("treasury")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()

um, ud, uname, *_ = load_shared_state()[:12]
sc = str(ud.get("staff_code","") or ""); role = ud.get("role",""); name = ud.get("full_name","")
is_admin    = ud.get("is_admin",False)
is_treasury = any(x in role for x in ("Treasury","Dealer","Forex","CFO","Chief Financial"))
is_mgr      = any(x in role for x in ("Manager","Director","Chief","Head"))

@st.cache_data(ttl=60, show_spinner=False)
def _load(fname):
    p = DATA / fname
    return a2z_db.load_json(p) if p.exists() else ([] if "json" in fname else {})

# Load config
@st.cache_data(ttl=30, show_spinner=False)
def _cfg():
    p = DATA / "proposition_config.json"
    if not p.exists(): return {}
    return a2z_db.load_json(p).get("treasury_config", {})

tcfg = _cfg()
cbk_rate   = tcfg.get("cbk_rate", 13.00)
fx_rates   = tcfg.get("fx_reference_rates", {"USD":130.50,"EUR":141.20,"GBP":165.80})
ecl_rates  = tcfg.get("ifrs9_ecl_rates",    {"Stage 1":0.01,"Stage 2":0.15,"Stage 3":0.50})
liq_min    = tcfg.get("liquidity_ratios_minimum", {"LCR":100,"NSFR":100})

# Load all treasury data
fd       = _load("treasury_fd.json")
fx_deals = _load("treasury_fx.json")
mm       = _load("treasury_mm.json")
gs       = _load("treasury_gov_secs.json")
limits   = _load("treasury_limits.json")
alm      = _load("treasury_alm.json")

st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>💹 Treasury</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "FD · FX · Money Market · Government Securities · ALM · Limits</span></div>",
    unsafe_allow_html=True)

# ── Market reference bar ─────────────────────────────────────────────
st.markdown(
    f"<div style='background:var(--color-background-secondary);border-radius:8px;"
    f"padding:8px 16px;font-size:12px;display:flex;gap:24px;flex-wrap:wrap;margin-bottom:8px'>"
    f"<span>🏦 <b>CBK Rate:</b> {cbk_rate:.2f}%</span>"
    + "".join(f"<span>💱 <b>{ccy}/KES:</b> {rate:.2f}</span>" for ccy,rate in fx_rates.items())
    + f"<span style='color:var(--color-text-tertiary)'>Updated: {alm.get('last_updated',str(today))}</span>"
    + "</div>",
    unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────
# Restructured: 2-level navigation for clarity
# ─────────────────────────────────────────────────────────────────
sections = st.tabs([
    "📊 Overview",
    "💼 Products",
    "⚖️ Risk & Control",
])

# ── Section 0: 📊 Overview ─────────────────────────────
with sections[0]:
    st.markdown("**Treasury at a glance:**")
    fd_book = sum(r["amount"] for r in fd if r["currency"]=="KES" and r["status"] in ("approved","booked"))/1e9
    fx_vol  = sum(d["kes_amount"] for d in fx_deals if d["status"] in ("Confirmed","Settled"))/1e9
    mm_book = sum(r["principal"] for r in mm if r["status"]=="Active")/1e9
    gs_face = sum(s["face_value"] for s in gs if not s["is_matured"])/1e9
    gs_mkt  = sum(s["market_value"] for s in gs if not s["is_matured"])/1e9
    unreal_gl= sum(s["unrealised_gl"] for s in gs if not s["is_matured"])/1e6

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("FD Book",          f"KES {fd_book:.1f}B")
    c2.metric("FX Dealt (YTD)",   f"KES {fx_vol:.1f}B")
    c3.metric("MM Placements",    f"KES {mm_book:.1f}B")
    c4.metric("Gov Securities",   f"KES {gs_face:.1f}B face")
    c5.metric("Unrealised G/L",   f"KES {unreal_gl:.0f}M",
              delta_color="normal" if unreal_gl >= 0 else "inverse")

    st.markdown("---")
    liq = alm.get("liquidity_ratios", {}) if alm else {}
    lc1,lc2,lc3,lc4 = st.columns(4)
    for col, key, min_v, label in [
        (lc1,"lcr",100,"LCR"),
        (lc2,"nsfr",100,"NSFR"),
        (lc3,"loan_to_deposit",80,"L/D Ratio"),
        (lc4,"liquid_assets_ratio",20,"Liquid Assets"),
    ]:
        val = liq.get(key,{}).get("value",0) if liq else 0
        tgt = liq.get(key,{}).get("minimum", liq_min.get(key.upper(), min_v)) if liq else min_v
        clr = "normal" if val >= tgt else "inverse"
        col.metric(label, f"{val:.1f}%", f"Min: {tgt}%", delta_color=clr)

    # Maturing soon
    fd_mat7 = [r for r in fd if r.get("maturity_date") and
                0 <= (_safe_date(r["maturity_date"])-today).days <= 7
                and r["status"] in ("approved","booked")]
    mm_mat7 = [r for r in mm if r.get("maturity_date") and
                0 <= (_safe_date(r["maturity_date"])-today).days <= 7
                and r["status"]=="Active"]
    if fd_mat7 or mm_mat7:
        st.markdown("---")
        st.error(f"🔴 **Maturing within 7 days:** {len(fd_mat7)} FDs + {len(mm_mat7)} MM placements — arrange rollover or settlement")
        for r in fd_mat7:
            st.markdown(f"  • FD `{r['id']}` {r['client_name'][:25]} · KES {r['amount']/1e6:.1f}M · Matures {r['maturity_date']}")
        for r in mm_mat7:
            st.markdown(f"  • MM `{r['id']}` {r['counterparty'][:25]} · KES {r['principal']/1e6:.1f}M · Matures {r['maturity_date']}")

    # ════════════════════════════════════════════════════════════════════
    # TAB 2: FIXED DEPOSITS
    # ════════════════════════════════════════════════════════════════════

# ── Section 1: 💼 Products ─────────────────────────────
with sections[1]:
    sub = st.tabs([
        "📋 Fixed Deposits",
        "💱 FX Dealing",
        "💰 Money Market",
        "🏛️ Government Securities",
    ])
    with sub[0]:
        fd_tabs = st.tabs(["📋 Queue","⏳ Pending Ratification","📈 Booked","💹 Rate Analytics"])

        with fd_tabs[0]:
            f1,f2,f3 = st.columns(3)
            sel_s = f1.selectbox("Status",["All","pending","approved","booked","counter_offered","rejected"],key="fd_s")
            sel_c = f2.selectbox("Currency",["All","KES","USD","EUR"],key="fd_c")
            sel_p = f3.selectbox("Product",["All"]+sorted(set(r["product"] for r in fd)),key="fd_p")
            vis=[r for r in fd if (sel_s=="All" or r["status"]==sel_s)
                 and (sel_c=="All" or r["currency"]==sel_c)
                 and (sel_p=="All" or r["product"]==sel_p)]
            rows=[{"ID":r["id"],"Client":r["client_name"][:28],"Product":r["product"][:30],
                   "Ccy":r["currency"],"Amount (M)":round(r["amount"]/1e6,1),
                   "Tenure":r["tenure_days"],"Proposed%":r["proposed_rate"],
                   "Ratified%":r.get("ratified_rate","—"),"Status":r["status"],
                   "Submitted":r["submitted_date"]}
                  for r in sorted(vis,key=lambda x:x["submitted_date"],reverse=True)]
            if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

        with fd_tabs[1]:
            pending_fd=[r for r in fd if r["status"]=="pending"]
            if not pending_fd: st.success("✅ No FDs pending ratification.")
            else:
                st.warning(f"⏳ {len(pending_fd)} FD requests pending — KES {sum(r['amount'] for r in pending_fd if r['currency']=='KES')/1e9:.2f}B")
                # Batch ratify by tenure
                from collections import defaultdict as _dd
                by_tenure=_dd(list)
                for r in pending_fd: by_tenure[r["tenure_days"]].append(r)
                st.markdown("**Batch ratify by tenure:**")
                for tenure, grp in sorted(by_tenure.items()):
                    if len(grp)<2: continue
                    bt1,bt2,bt3=st.columns([2,2,1])
                    bt1.markdown(f"**{tenure}d** — {len(grp)} requests · avg proposed: {sum(r['proposed_rate'] for r in grp)/len(grp):.2f}%")
                    batch_rate=bt2.number_input(f"Rate ({tenure}d)%",min_value=1.0,max_value=25.0,
                        value=round(sum(r["proposed_rate"] for r in grp)/len(grp),2),step=0.25,key=f"br_{tenure}")
                    if bt3.button(f"Apply {len(grp)}",key=f"ba_{tenure}",type="primary"):
                        all_fd=json.loads((DATA/"treasury_fd.json").read_text())
                        n=0
                        for item in all_fd:
                            if item["status"]=="pending" and item["tenure_days"]==tenure:
                                item["ratified_rate"]=batch_rate; item["status"]="approved"
                                item["treasury_officer"]=name; item["ratified_date"]=str(today); n+=1
                        (DATA/"treasury_fd.json").write_text(json.dumps(all_fd,indent=2))
                        audit_log("TREASURY_FD_UPDATE", name, f"FD {r['id']} ratified")
                        st.cache_data.clear(); st.success(f"✅ {n} FDs ratified at {batch_rate}%"); st.rerun()
                # Individual ratification
                st.markdown("---")
                # Sort by urgency: maturing soonest first, then by amount
        from datetime import date as _dt_treas
        def _urgency(r):
            try:
                days=(_safe_date(str(r.get("maturity_date","9999-12-31"))[:10])-_dt_treas.today()).days
                return (days, -r.get("amount",0))
            except: return (9999, 0)
        _urgent_fd = [r for r in pending_fd if r.get("maturity_date") and 
                      (_safe_date(str(r["maturity_date"])[:10])-date.today()).days<=7]
        if _urgent_fd:
            st.error(f"🔴 **{len(_urgent_fd)} FD(s) maturing within 7 days need immediate ratification!**")
        for r in sorted(pending_fd, key=_urgency)[:10]:
                    with st.expander(f"{r['client_name'][:25]} · {r['currency']} {r['amount']/1e6:.1f}M · {r['tenure_days']}d · {r['proposed_rate']}%"):
                        rc1,rc2=st.columns(2)
                        rc1.markdown(f"**RM:** {r['rm_name']}  \n**Submitted:** {r['submitted_date']}")
                        new_rate=rc2.number_input("Ratify at (%)",value=float(r["proposed_rate"]),step=0.25,key=f"rr_{r['id']}")
                        ra1,ra2=st.columns(2)
                        if ra1.button("✅ Ratify",key=f"rat_{r['id']}",type="primary"):
                            all_fd=json.loads((DATA/"treasury_fd.json").read_text())
                            for item in all_fd:
                                if item["id"]==r["id"]: item["ratified_rate"]=new_rate; item["status"]="approved"; item["treasury_officer"]=name; item["ratified_date"]=str(today)
                            (DATA/"treasury_fd.json").write_text(json.dumps(all_fd,indent=2))
                            st.cache_data.clear(); st.success(f"✅ Ratified at {new_rate}%"); st.rerun()
                        if ra2.button("❌ Reject",key=f"rej_{r['id']}"):
                            all_fd=json.loads((DATA/"treasury_fd.json").read_text())
                            for item in all_fd:
                                if item["id"]==r["id"]: item["status"]="rejected"
                            (DATA/"treasury_fd.json").write_text(json.dumps(all_fd,indent=2))
                            st.cache_data.clear(); st.success("Rejected"); st.rerun()

        with fd_tabs[2]:
            booked=[r for r in fd if r["status"] in ("approved","booked")]
            fd_mat7_b=[r for r in booked if r.get("maturity_date") and 0<=(_safe_date(r["maturity_date"])-today).days<=7]
            fd_mat30=[r for r in booked if r.get("maturity_date") and 0<=(_safe_date(r["maturity_date"])-today).days<=30]
            if fd_mat7_b: st.error(f"🔴 {len(fd_mat7_b)} FDs maturing within 7 days")
            elif fd_mat30: st.warning(f"⚠️ {len(fd_mat30)} FDs maturing within 30 days")
            c1,c2,c3,c4=st.columns(4)
            c1.metric("Booked FDs",len(booked))
            c2.metric("Total KES",f"KES {sum(r['amount'] for r in booked if r['currency']=='KES')/1e9:.2f}B")
            avg_r=sum(r.get('ratified_rate',r['proposed_rate']) for r in booked)/max(len(booked),1)
            c3.metric("Avg Rate",f"{avg_r:.2f}%")
            c4.metric("Maturing ≤30d",len(fd_mat30))
            rows=[{"ID":r["id"],"Client":r["client_name"][:25],"Ccy":r["currency"],
                   "Amount (M)":round(r["amount"]/1e6,1),"Rate%":r.get("ratified_rate",r["proposed_rate"]),
                   "Tenure":r["tenure_days"],"Matures":(r.get("maturity_date") or "")[:10]}
                  for r in sorted(booked,key=lambda x:x.get("maturity_date") or "9999")]
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

        with fd_tabs[3]:
            all_ratified=[r for r in fd if r.get("ratified_rate")]
            if all_ratified:
                by_tenure=defaultdict(list)
                for r in all_ratified: by_tenure[r["tenure_days"]].append(r.get("ratified_rate",r["proposed_rate"]))
                df_rt=pd.DataFrame([{"Tenure (days)":t,"Avg Rate%":round(sum(v)/len(v),2),"Count":len(v),"Min%":round(min(v),2),"Max%":round(max(v),2)} for t,v in sorted(by_tenure.items())])
                st.markdown("**Rates by tenure:**"); st.dataframe(df_rt,use_container_width=True,hide_index=True)
                st.bar_chart(df_rt.set_index("Tenure (days)")["Avg Rate%"])

        # ════════════════════════════════════════════════════════════════════
        # TAB 3: FX DEALING
        # ════════════════════════════════════════════════════════════════════
    with sub[1]:
        c1,c2,c3,c4,c5=st.columns(5)
        c1.metric("FX Deals",len(fx_deals))
        c2.metric("Buy Vol",  f"KES {sum(d['kes_amount'] for d in fx_deals if d['direction']=='Buy')/1e9:.1f}B")
        c3.metric("Sell Vol", f"KES {sum(d['kes_amount'] for d in fx_deals if d['direction']=='Sell')/1e9:.1f}B")
        c4.metric("Total Margin",f"KES {sum(d.get('margin_kes',0) for d in fx_deals)/1e6:.1f}M")
        fwd_count=sum(1 for d in fx_deals if d["deal_type"]=="Forward")
        c5.metric("Forwards",fwd_count)

        fx_t1,fx_t2=st.tabs(["📋 Deal Register","📊 Exposure"])
        with fx_t1:
            f1,f2,f3=st.columns(3)
            sel_fc=f1.selectbox("Currency",["All"]+sorted(set(d["currency"] for d in fx_deals)),key="fx_c")
            sel_ft=f2.selectbox("Type",["All","Spot","Forward"],key="fx_t")
            sel_fs=f3.selectbox("Status",["All","Confirmed","Settled","Cancelled"],key="fx_s")
            vis_fx=[d for d in fx_deals
                    if (sel_fc=="All" or d["currency"]==sel_fc)
                    and (sel_ft=="All" or d["deal_type"]==sel_ft)
                    and (sel_fs=="All" or d["status"]==sel_fs)]
            rows=[{"ID":d["id"],"Type":d["deal_type"],"Dir":d["direction"],"CCY":d["currency"],
                   "FCY Amt":f"{d['fcy_amount']:,.0f}","Rate":d["rate"],"KES Amt (M)":round(d["kes_amount"]/1e6,1),
                   "Counterparty":d["counterparty"][:20],"Value Date":d["value_date"][:10],"Status":d["status"]}
                  for d in sorted(vis_fx,key=lambda x:(x.get("trade_date") or "9999"),reverse=True)[:50]]
            if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

        with fx_t2:
            st.markdown("**Net open position by currency:**")
            ccy_exp=defaultdict(lambda:{"buy":0.0,"sell":0.0})
            for d in fx_deals:
                if d["status"]!="Settled":
                    ccy_exp[d["currency"]]["buy" if d["direction"]=="Buy" else "sell"]+=d["fcy_amount"]
            exp_rows=[{"Currency":ccy,"Buy FCY":f"{v['buy']:,.0f}","Sell FCY":f"{v['sell']:,.0f}",
                       "Net FCY":f"{v['buy']-v['sell']:,.0f}","Net KES (M)":round((v["buy"]-v["sell"])*fx_rates.get(ccy,1)/1e6,1),
                       "Limit KES (M)":round(tcfg.get("counterparty_limits",{}).get("net_open",500e6)/1e6,0)}
                      for ccy,v in ccy_exp.items()]
            if exp_rows: st.dataframe(pd.DataFrame(exp_rows),use_container_width=True,hide_index=True)

        # ════════════════════════════════════════════════════════════════════
        # TAB 4: MONEY MARKET
        # ════════════════════════════════════════════════════════════════════
    with sub[2]:
        active_mm=[r for r in mm if r["status"]=="Active"]
        matured_mm=[r for r in mm if r["status"]=="Matured"]
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Active Placements",len(active_mm))
        c2.metric("Total Outstanding",f"KES {sum(r['principal'] for r in active_mm)/1e9:.1f}B")
        c3.metric("Avg Rate",f"{sum(r['rate'] for r in active_mm)/max(len(active_mm),1):.2f}%")
        c4.metric("Interest Earned (Total)",f"KES {sum(r['interest_earned'] for r in mm)/1e6:.0f}M")

        rows=[{"ID":r["id"],"Type":r["type"],"Counterparty":r["counterparty"][:25],
               "Principal (M)":round(r["principal"]/1e6,1),"Rate%":r["rate"],
               "Tenor":r["tenor_days"],"Matures":r["maturity_date"][:10],
               "Interest (KES K)":round(r["interest_earned"]/1e3,0),"Status":r["status"]}
              for r in sorted(mm,key=lambda x:(x.get("maturity_date") or "9999"))]
        if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

        # ════════════════════════════════════════════════════════════════════
        # TAB 5: GOVERNMENT SECURITIES
        # ════════════════════════════════════════════════════════════════════
    with sub[3]:
        active_gs=[s for s in gs if not s["is_matured"]]
        htm=[s for s in active_gs if s["classification"]=="HTM"]
        afs=[s for s in active_gs if s["classification"]=="AFS"]
        fvtpl=[s for s in active_gs if s["classification"]=="FVTPL"]
        total_face=sum(s["face_value"] for s in active_gs)/1e9
        total_mkt =sum(s["market_value"] for s in active_gs)/1e9
        total_gl  =sum(s["unrealised_gl"] for s in active_gs)/1e6
        accrued   =sum(s.get("accrued_interest",0) for s in active_gs)/1e6

        c1,c2,c3,c4,c5=st.columns(5)
        c1.metric("Total Portfolio",f"KES {total_face:.1f}B face")
        c2.metric("Market Value",   f"KES {total_mkt:.1f}B")
        c3.metric("Unrealised G/L", f"KES {total_gl:.0f}M",delta_color="normal" if total_gl>=0 else "inverse")
        c4.metric("Accrued Interest",f"KES {accrued:.0f}M")
        c5.metric("Holdings",       len(active_gs))

        st.markdown("**By IFRS 9 classification:**")
        for clf, items, desc in [("HTM",htm,"Held to Maturity — at amortised cost"),
                                   ("AFS",afs,"Available for Sale — FV through OCI"),
                                   ("FVTPL",fvtpl,"Fair Value through P&L — trading book")]:
            if not items: continue
            val=sum(s["face_value"] for s in items)/1e9
            mkt=sum(s["market_value"] for s in items)/1e9
            gl =sum(s["unrealised_gl"] for s in items)/1e6
            st.markdown(f"  **{clf}** ({desc}): {len(items)} securities · KES {val:.1f}B face · "
                        f"KES {mkt:.1f}B MtM · G/L: KES {gl:.0f}M")

        st.markdown("---")
        rows=[{"ISIN":s["isin"],"Type":s["security_type"][:25],"Face (M)":round(s["face_value"]/1e6,0),
               "Mkt Val (M)":round(s["market_value"]/1e6,0),"G/L (M)":round(s["unrealised_gl"]/1e6,1),
               "YTM%":s["ytm"],"Coupon%":s["coupon_rate"],"Matures":s["maturity_date"][:10],
               "Class":s["classification"],"Portfolio":s["portfolio"]}
              for s in sorted(active_gs,key=lambda x:(x.get("maturity_date") or "9999"))]
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

        # ════════════════════════════════════════════════════════════════════
        # TAB 6: ALM & LIQUIDITY
        # ════════════════════════════════════════════════════════════════════

# ── Section 2: ⚖️ Risk & Control ─────────────────────────────
with sections[2]:
    sub = st.tabs([
        "📊 ALM & Liquidity",
        "🔒 Limits & Blotter",
        "📐 IFRS 9",
    ])
    with sub[0]:
        if not alm:
            st.info("ALM data not available.")
        else:
            st.markdown(f"**Asset-Liability Management — as at {alm.get('as_at_date',str(today))}**")
            st.markdown(f"CBK Rate: **{alm.get('cbk_rate',13.00):.2f}%**  |  Interbank: **{alm.get('interbank_rate',12.5):.2f}%**")

            st.markdown("---")
            st.markdown("**Liquidity ratios (CBK Prudential Guidelines):**")
            liq=alm.get("liquidity_ratios",{})
            for key,info in liq.items():
                val=info.get("value",0); tgt=info.get("minimum",info.get("maximum",100))
                is_max="maximum" in info
                ok=(val<=tgt) if is_max else (val>=tgt)
                icon="✅" if ok else "🔴"
                bar_pct=min(val/tgt*100,150) if tgt>0 else 0
                bar_clr="#16A34A" if ok else "#DC2626"
                st.markdown(
                    f"<div style='margin:4px 0;padding:8px 14px;background:var(--color-background-secondary);border-radius:8px'>"
                    f"<div style='display:flex;justify-content:space-between'><b>{info.get('label',key.upper())}</b>"
                    f"<span style='color:{bar_clr}'>{icon} {val:.1f}% ({"max" if is_max else "min"}: {tgt}%)</span></div>"
                    f"<div style='background:#E5E7EB;height:5px;border-radius:3px;margin-top:6px'>"
                    f"<div style='width:{min(val/max(tgt,1)*100,100):.0f}%;background:{bar_clr};height:100%;border-radius:3px'></div></div>"
                    f"</div>", unsafe_allow_html=True)

            st.markdown("---")
            st.markdown("**Repricing gap analysis (Interest Rate Risk):**")
            gaps=alm.get("repricing_gaps",[])
            if gaps:
                df_gap=pd.DataFrame([{"Bucket":g["bucket"],
                    "Assets (B)":round(g["assets"]/1e9,1),"Liabilities (B)":round(g["liabilities"]/1e9,1),
                    "Gap (B)":round(g["gap"]/1e9,1),"Cumulative Gap (B)":round(g["cumulative_gap"]/1e9,1)}
                    for g in gaps])
                st.dataframe(df_gap,use_container_width=True,hide_index=True)
                st.caption("Positive gap = asset-sensitive (benefits from rate rises). Negative gap = liability-sensitive (benefits from rate falls).")

            hqla=alm.get("hqla",{})
            if hqla:
                st.markdown("**HQLA composition (LCR buffer):**")
                ch1,ch2,ch3=st.columns(3)
                ch1.metric("Level 1 HQLA",f"KES {hqla.get('level_1',0)/1e9:.1f}B","Gov securities, CBK cash")
                ch2.metric("Level 2A",     f"KES {hqla.get('level_2a',0)/1e9:.1f}B","AAA-rated securities")
                ch3.metric("Level 2B",     f"KES {hqla.get('level_2b',0)/1e9:.1f}B","Listed equities, etc")

        # ════════════════════════════════════════════════════════════════════
        # TAB 7: LIMITS & BLOTTER
        # ════════════════════════════════════════════════════════════════════
    with sub[1]:
        if not limits:
            st.info("Limits data not available.")
        else:
            lt1,lt2,lt3=st.tabs(["🏦 Counterparty","👤 Dealer","💱 Currency"])

            with lt1:
                st.markdown("**Counterparty credit limits:**")
                cp_rows=[]
                for cp in limits.get("counterparty_limits",[]):
                    util_pct=cp["utilised"]/max(cp["limit_kes"],1)*100
                    status_icon="🔴" if util_pct>90 else "🟡" if util_pct>70 else "✅"
                    cp_rows.append({"Counterparty":cp["counterparty"][:25],
                        "Limit (M)":round(cp["limit_kes"]/1e6,0),"Utilised (M)":round(cp["utilised"]/1e6,0),
                        "Util%":f"{util_pct:.0f}%","Status":status_icon,"Review":cp.get("review_date","")[:10]})
                st.dataframe(pd.DataFrame(cp_rows),use_container_width=True,hide_index=True)

            with lt2:
                st.markdown("**Dealer trading limits:**")
                d_rows=[{"Dealer":d["dealer"],"Intraday (M)":round(d["intraday_limit"]/1e6,0),
                          "Overnight (M)":round(d["overnight_limit"]/1e6,0),
                          "Stop Loss (M)":round(d["stop_loss_daily"]/1e6,0)}
                         for d in limits.get("dealer_limits",[])]
                st.dataframe(pd.DataFrame(d_rows),use_container_width=True,hide_index=True)

            with lt3:
                st.markdown("**Net open position limits by currency:**")
                c_rows=[{"Currency":c["currency"],
                          "NOP Limit (M)":round(c["net_open_position"]/1e6,0),
                          "Utilised (M)":round(c["utilised"]/1e6,0),
                          "Util%":f"{c['utilised']/max(c['net_open_position'],1)*100:.0f}%"}
                         for c in limits.get("currency_limits",[])]
                st.dataframe(pd.DataFrame(c_rows),use_container_width=True,hide_index=True)

        # ════════════════════════════════════════════════════════════════════
        # TAB 8: IFRS 9 — FINANCIAL INSTRUMENTS
        # ════════════════════════════════════════════════════════════════════
    with sub[2]:
        st.markdown("**IFRS 9 classification and measurement — Treasury portfolio**")
        st.markdown(
            "<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;"
            "padding:10px 16px;font-size:12px;margin-bottom:12px'>"
            "IFRS 9 requires financial assets to be classified based on the business model "
            "for managing the asset and the contractual cash flow characteristics (SPPI test)."
            "</div>", unsafe_allow_html=True)

        active_gs_i=[s for s in gs if not s["is_matured"]]
        i1,i2,i3=st.tabs(["🏛️ Gov Securities Classification","📐 ECL on Investments","⚙️ IFRS 9 Config"])

        with i1:
            clf_summary=Counter(s["classification"] for s in active_gs_i)
            for clf,n in clf_summary.items():
                items=[s for s in active_gs_i if s["classification"]==clf]
                fv=sum(s["face_value"] for s in items)/1e9
                mv=sum(s["market_value"] for s in items)/1e9
                gl=sum(s["unrealised_gl"] for s in items)/1e6
                desc={"HTM":"Amortised cost; held to collect cash flows only",
                      "AFS":"FVOCI; held to collect AND sell",
                      "FVTPL":"Fair value through P&L; trading or residual category"}.get(clf,"")
                icon="🟢" if gl>=0 else "🔴"
                st.markdown(
                    f"<div style='background:var(--color-background-secondary);border-radius:8px;"
                    f"padding:12px;margin-bottom:8px'>"
                    f"<b>{clf}</b> — {n} securities · KES {fv:.1f}B face · KES {mv:.1f}B MtM · "
                    f"{icon} G/L: KES {gl:.0f}M<br>"
                    f"<span style='font-size:11px;color:var(--color-text-secondary)'>{desc}</span>"
                    f"</div>", unsafe_allow_html=True)

            st.dataframe(pd.DataFrame([{"ISIN":s["isin"],"Type":s["security_type"][:25],
                "Class":s["classification"],"Face (M)":round(s["face_value"]/1e6,0),
                "MtM (M)":round(s["market_value"]/1e6,0),"G/L (M)":round(s["unrealised_gl"]/1e6,1),
                "Coupon%":s["coupon_rate"],"Matures":s["maturity_date"][:10]}
                for s in active_gs_i]),use_container_width=True,hide_index=True)

        with i2:
            st.markdown("**ECL provision on investment portfolio (Stage assessment):**")
            ecl_data=[]
            for s in active_gs_i:
                days_to_mat=(_safe_date(s["maturity_date"])-today).days
                stage="Stage 1" if days_to_mat>0 else "Stage 3"
                ecl_pct=ecl_rates.get(stage,0.01)
                ecl_amt=s["face_value"]*ecl_pct
                ecl_data.append({"ISIN":s["isin"],"Type":s["security_type"][:20],
                    "Class":s["classification"],"Stage":stage,
                    "Face (M)":round(s["face_value"]/1e6,0),
                    "ECL Rate%":f"{ecl_pct*100:.2f}%","ECL Amount (KES K)":round(ecl_amt/1e3,0)})
            if ecl_data:
                df_ecl=pd.DataFrame(ecl_data)
                total_ecl=sum(e.get("face_value_raw",0) for e in ecl_data if False)
                st.dataframe(df_ecl,use_container_width=True,hide_index=True)
                st.caption("Government of Kenya securities are generally Stage 1 given sovereign rating. ECL rates are configured in Admin → Treasury Config.")

        with i3:
            st.markdown("**IFRS 9 rates currently configured:**")
            st.json(ecl_rates)
            st.markdown("Update these in **Admin → Treasury Config** tab.")
            st.markdown("""
        **What is hardcoded (cannot change via UI):**
        - IFRS 9 stage transition rules (Stage 1→2: SICR; Stage 2→3: default)
        - SPPI test logic (contractual cash flows = principal + interest only)
        - Amortised cost effective interest rate calculation
        - OCI recycling treatment for AFS instruments
        - CBK IFRS 9 regulatory reporting format

        **What is configurable via Admin:**
        - ECL rates per stage (default 1% / 15% / 50%)
        - IFRS 9 classification per instrument type
        - SICR threshold (days past due for Stage 2 transfer)
        - Probability of Default curves
            """)

