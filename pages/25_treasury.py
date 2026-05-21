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
from utils.config import currency_symbol, regulator, currency, country, core_banking_system

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()



require_access("treasury_alm.dashboard")
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
    f"<span>🏦 <b>{regulator()} Rate:</b> {cbk_rate:.2f}%</span>"
    + "".join(f"<span>💱 <b>{ccy}/{currency()}:</b> {rate:.2f}</span>" for ccy,rate in fx_rates.items())
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
    "🤖 Arc Engines",
])

# ── Section 0: 📊 Overview ─────────────────────────────
with sections[0]:
    st.markdown("**Treasury at a glance:**")
    fd_book = sum(r["amount"] for r in fd if r["currency"] == currency() and r["status"] in ("approved","booked"))/1e9
    fx_vol  = sum(d["kes_amount"] for d in fx_deals if d["status"] in ("Confirmed","Settled"))/1e9
    mm_book = sum(r["principal"] for r in mm if r["status"]=="Active")/1e9
    gs_face = sum(s["face_value"] for s in gs if not s["is_matured"])/1e9
    gs_mkt  = sum(s["market_value"] for s in gs if not s["is_matured"])/1e9
    unreal_gl= sum(s["unrealised_gl"] for s in gs if not s["is_matured"])/1e6

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("FD Book",          f"{currency_symbol()} {fd_book:.1f}B")
    c2.metric("FX Dealt (YTD)",   f"{currency_symbol()} {fx_vol:.1f}B")
    c3.metric("MM Placements",    f"{currency_symbol()} {mm_book:.1f}B")
    c4.metric("Gov Securities",   f"{currency_symbol()} {gs_face:.1f}B face")
    c5.metric("Unrealised G/L",   f"{currency_symbol()} {unreal_gl:.0f}M",
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
            st.markdown(f"  • FD `{r['id']}` {r['client_name'][:25]} · {currency_symbol()} {r['amount']/1e6:.1f}M · Matures {r['maturity_date']}")
        for r in mm_mat7:
            st.markdown(f"  • MM `{r['id']}` {r['counterparty'][:25]} · {currency_symbol()} {r['principal']/1e6:.1f}M · Matures {r['maturity_date']}")

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
            sel_c = f2.selectbox("Currency",["All", currency(), "USD", "EUR"],key="fd_c")
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
                st.warning(f"⏳ {len(pending_fd)} FD requests pending — KES {sum(r['amount'] for r in pending_fd if r['currency'] == currency())/1e9:.2f}B")
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
            c2.metric("Total KES",f"{currency_symbol()} {sum(r['amount'] for r in booked if r['currency'] == currency())/1e9:.2f}B")
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
        c2.metric("Buy Vol",  f"{currency_symbol()} {sum(d['kes_amount'] for d in fx_deals if d['direction']=='Buy')/1e9:.1f}B")
        c3.metric("Sell Vol", f"{currency_symbol()} {sum(d['kes_amount'] for d in fx_deals if d['direction']=='Sell')/1e9:.1f}B")
        c4.metric("Total Margin",f"{currency_symbol()} {sum(d.get('margin_kes',0) for d in fx_deals)/1e6:.1f}M")
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
                   "FCY Amt":f"{d['fcy_amount']:,.0f}","Rate":d["rate"],f"{currency()} Amt (M)":round(d["kes_amount"]/1e6,1),
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
                       "Net FCY":f"{v['buy']-v['sell']:,.0f}",f"Net {currency()} (M)":round((v["buy"]-v["sell"])*fx_rates.get(ccy,1)/1e6,1),
                       f"Limit {currency()} (M)":round(tcfg.get("counterparty_limits",{}).get("net_open",500e6)/1e6,0)}
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
        c2.metric("Total Outstanding",f"{currency_symbol()} {sum(r['principal'] for r in active_mm)/1e9:.1f}B")
        c3.metric("Avg Rate",f"{sum(r['rate'] for r in active_mm)/max(len(active_mm),1):.2f}%")
        c4.metric("Interest Earned (Total)",f"{currency_symbol()} {sum(r['interest_earned'] for r in mm)/1e6:.0f}M")

        rows=[{"ID":r["id"],"Type":r["type"],"Counterparty":r["counterparty"][:25],
               "Principal (M)":round(r["principal"]/1e6,1),"Rate%":r["rate"],
               "Tenor":r["tenor_days"],"Matures":r["maturity_date"][:10],
               f"Interest ({currency()} K)":round(r["interest_earned"]/1e3,0),"Status":r["status"]}
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
        c1.metric("Total Portfolio",f"{currency_symbol()} {total_face:.1f}B face")
        c2.metric("Market Value",   f"{currency_symbol()} {total_mkt:.1f}B")
        c3.metric("Unrealised G/L", f"{currency_symbol()} {total_gl:.0f}M",delta_color="normal" if total_gl>=0 else "inverse")
        c4.metric("Accrued Interest",f"{currency_symbol()} {accrued:.0f}M")
        c5.metric("Holdings",       len(active_gs))

        st.markdown("**By IFRS 9 classification:**")
        for clf, items, desc in [("HTM",htm,"Held to Maturity — at amortised cost"),
                                   ("AFS",afs,"Available for Sale — FV through OCI"),
                                   ("FVTPL",fvtpl,"Fair Value through P&L — trading book")]:
            if not items: continue
            val=sum(s["face_value"] for s in items)/1e9
            mkt=sum(s["market_value"] for s in items)/1e9
            gl =sum(s["unrealised_gl"] for s in items)/1e6
            st.markdown(f"  **{clf}** ({desc}): {len(items)} securities · {currency_symbol()} {val:.1f}B face · "
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
        "💱 FX Position Monitoring",
    ])
    with sub[0]:
        if not alm:
            st.info("ALM data not available.")
        else:
            st.markdown(f"**Asset-Liability Management — as at {alm.get('as_at_date',str(today))}**")
            st.markdown(f"{regulator()} Rate: **{alm.get('cbk_rate',13.00):.2f}%**  |  Interbank: **{alm.get('interbank_rate',12.5):.2f}%**")

            st.markdown("---")
            st.markdown(f"**Liquidity ratios ({regulator()} Prudential Guidelines):**")
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
                ch1.metric("Level 1 HQLA",f"{currency_symbol()} {hqla.get('level_1',0)/1e9:.1f}B",f"Gov securities, {regulator()} cash")
                ch2.metric("Level 2A",     f"{currency_symbol()} {hqla.get('level_2a',0)/1e9:.1f}B","AAA-rated securities")
                ch3.metric("Level 2B",     f"{currency_symbol()} {hqla.get('level_2b',0)/1e9:.1f}B","Listed equities, etc")

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
        - regulatory IFRS 9 reporting format

        **What is configurable via Admin:**
        - ECL rates per stage (default 1% / 15% / 50%)
        - IFRS 9 classification per instrument type
        - SICR threshold (days past due for Stage 2 transfer)
        - Probability of Default curves
            """)


    # ── FX Position Monitoring (Standard #75, integrated v5.76) ──
    with sub[3]:
        from utils.fx_position import (
            FxPositionMonitoringEngine, FxPosition,
            SUPPORTED_CURRENCIES, AGGREGATE_FX_LIMIT_PCT,
            SINGLE_CURRENCY_LIMIT_PCT, AGGREGATION_METHODS,
        )
        from decimal import Decimal as _D_fx

        st.markdown(
            f"**Standard #75 — FX Position Monitoring** ({regulator()} PG/03). "
            f"Single-currency limit: ≤ **{SINGLE_CURRENCY_LIMIT_PCT}% of core capital**. "
            f"Aggregate limit: ≤ **{AGGREGATE_FX_LIMIT_PCT}% of core capital**."
        )
        st.caption(
            f"Engine `FxPositionMonitoringEngine`. "
            f"{len(SUPPORTED_CURRENCIES)} supported currencies. "
            f"2 aggregation methods (SHORTHAND vs SUM_ABSOLUTE)."
        )

        fx_sub_tabs = st.tabs([
            "📊 Net Open Position",
            "🚧 Limit Compliance Check",
            "🔍 Aggregation Method Comparison",
        ])

        # ---- Net Open Position per currency ----
        with fx_sub_tabs[0]:
            st.markdown("**Net Open Position per Currency** = FX assets − FX liabilities (KES-equivalent)")
            st.caption(
                "Uses the page's `treasury_fx.json` deal data if available; "
                "falls back to default 3-currency demo (USD / EUR / GBP).")

            # Aggregate FX deals by currency to derive positions
            fx_aggregated = {}
            for d in fx_deals:
                ccy = d.get("currency", "USD") or "USD"
                if ccy == "KES":
                    continue
                amt = float(d.get("kes_amount", 0) or 0)
                side = (d.get("side", "") or "").upper()
                if ccy not in fx_aggregated:
                    fx_aggregated[ccy] = {"assets": 0, "liabilities": 0,
                                            "spot": float(d.get("spot_rate",
                                                                  fx_rates.get(ccy, 0)) or 0)}
                # Buy → asset; Sell → liability (simplified)
                if "BUY" in side:
                    fx_aggregated[ccy]["assets"] += amt
                elif "SELL" in side:
                    fx_aggregated[ccy]["liabilities"] += amt
                else:
                    # Unspecified side → split 50/50 as net-zero contribution proxy
                    fx_aggregated[ccy]["assets"] += amt / 2
                    fx_aggregated[ccy]["liabilities"] += amt / 2

            # Allow the user to override / add positions
            st.markdown("**Position inputs** (KES-equivalent, in KES B):")
            position_rows = []
            default_positions = [
                ("USD", 10.0, 8.0, 130.0),
                ("EUR", 5.0, 5.5, 141.0),
                ("GBP", 3.0, 2.5, 165.0),
            ]
            for i, (default_ccy, default_a, default_l, default_spot) in enumerate(default_positions):
                # If we have aggregated data for this ccy, prefer it
                agg = fx_aggregated.get(default_ccy, {})
                a_val = agg.get("assets", 0) / 1e9 if agg.get("assets") else default_a
                l_val = agg.get("liabilities", 0) / 1e9 if agg.get("liabilities") else default_l
                s_val = agg.get("spot", default_spot) or default_spot
                fx_c1, fx_c2, fx_c3, fx_c4 = st.columns([1, 1.5, 1.5, 1])
                with fx_c1:
                    ccy = st.selectbox(f"Currency {i+1}",
                                         list(SUPPORTED_CURRENCIES),
                                         index=list(SUPPORTED_CURRENCIES).index(default_ccy),
                                         key=f"fx_pos_ccy_{i}")
                with fx_c2:
                    a = st.number_input("FX assets (KES B)",
                                          min_value=0.0, value=float(a_val),
                                          step=0.5, key=f"fx_pos_a_{i}")
                with fx_c3:
                    l = st.number_input("FX liabilities (KES B)",
                                          min_value=0.0, value=float(l_val),
                                          step=0.5, key=f"fx_pos_l_{i}")
                with fx_c4:
                    sp = st.number_input("Spot",
                                           min_value=0.0, value=float(s_val),
                                           step=1.0, key=f"fx_pos_sp_{i}")
                position_rows.append({"ccy": ccy, "a": a, "l": l, "sp": sp})

            if st.button("Compute net open positions", key="fx_pos_btn",
                          type="primary"):
                positions = [
                    FxPosition(
                        position_id=f"P{i+1}",
                        currency=row["ccy"],
                        fx_assets_kes_equivalent=_D_fx(str(row["a"])) * _D_fx("1000000000"),
                        fx_liabilities_kes_equivalent=_D_fx(str(row["l"])) * _D_fx("1000000000"),
                        spot_rate_to_kes=_D_fx(str(row["sp"])))
                    for i, row in enumerate(position_rows)
                ]
                r = FxPositionMonitoringEngine.net_open_position_per_currency(positions)
                if r.get("currency_count", 0) > 0:
                    rows_disp = []
                    for p in r.get("positions", []):
                        nop = _D_fx(str(p.get("net_open_position_kes", 0)))
                        rows_disp.append({
                            "Currency": p.get("currency"),
                            "Assets (KES B)": float(_D_fx(str(p.get("fx_assets_kes", 0)))/_D_fx("1000000000")),
                            "Liabilities (KES B)": float(_D_fx(str(p.get("fx_liabilities_kes", 0)))/_D_fx("1000000000")),
                            "Net Open Position (KES B)": float(nop / _D_fx("1000000000")),
                            "Type": p.get("position_type"),
                        })
                    st.dataframe(pd.DataFrame(rows_disp),
                                 use_container_width=True, hide_index=True)
                    if r.get("unknown_currencies"):
                        st.warning(
                            f"⚠ Unknown currencies excluded (Rule 6): "
                            f"{', '.join(r['unknown_currencies'])}")
                    audit_log("IFRS_ENGINE_USED", uname,
                               f"FX #75: NOP per ccy, count={r['currency_count']}")
                else:
                    st.error("No valid currencies in input.")

        # ---- Limit compliance check ----
        with fx_sub_tabs[1]:
            st.markdown(
                f"**Limit Compliance Check** ({regulator()} PG/03). "
                f"Single ≤ {SINGLE_CURRENCY_LIMIT_PCT}% / aggregate ≤ {AGGREGATE_FX_LIMIT_PCT}% of core capital.")
            core_cap = st.number_input("Core capital (KES B)",
                                         min_value=0.0, value=15.0, step=1.0,
                                         key="fx_core_cap",
                                         help="Tier 1 capital.")
            st.caption("Uses the same position inputs as the Net Open Position tab.")

            if st.button("Check compliance", key="fx_limit_btn",
                          type="primary"):
                positions = []
                for i in range(3):
                    ccy = st.session_state.get(f"fx_pos_ccy_{i}", "USD")
                    a = st.session_state.get(f"fx_pos_a_{i}", 1.0)
                    l = st.session_state.get(f"fx_pos_l_{i}", 1.0)
                    sp = st.session_state.get(f"fx_pos_sp_{i}", 130.0)
                    positions.append(FxPosition(
                        position_id=f"P{i+1}", currency=ccy,
                        fx_assets_kes_equivalent=_D_fx(str(a)) * _D_fx("1000000000"),
                        fx_liabilities_kes_equivalent=_D_fx(str(l)) * _D_fx("1000000000"),
                        spot_rate_to_kes=_D_fx(str(sp))))
                r = FxPositionMonitoringEngine.fx_exposure_limit_check(
                    positions,
                    _D_fx(str(core_cap)) * _D_fx("1000000000"))
                status = r.get("status")
                agg_pct = r.get("aggregate_pct")
                agg_breach = r.get("aggregate_breach")
                single_breaches = r.get("single_currency_breaches", [])
                color = {"GREEN":"#10B981","AMBER":"#F59E0B","RED":"#DC2626"}.get(status, "#6B7280")

                k1, k2, k3 = st.columns(3)
                k1.metric("Aggregate FX %", f"{agg_pct}%",
                           delta=f"vs {AGGREGATE_FX_LIMIT_PCT}% limit")
                k2.metric("Single-currency breaches",
                           str(len(single_breaches)))
                with k3:
                    st.markdown(
                        f"<div style='padding:12px;background:{color}22;"
                        f"border-left:6px solid {color};border-radius:10px;text-align:center'>"
                        f"<div style='font-size:11px;letter-spacing:1.5px;opacity:0.7'>STATUS</div>"
                        f"<div style='font-size:24px;font-weight:800;color:{color}'>{status}</div></div>",
                        unsafe_allow_html=True)

                if not agg_breach and not single_breaches:
                    st.success(
                        f"✅ All FX limits within {regulator()} PG/03 thresholds.")
                else:
                    if agg_breach:
                        st.error(
                            f"⛔ **Aggregate FX limit BREACHED** at {agg_pct}% "
                            f"(limit {AGGREGATE_FX_LIMIT_PCT}%).")
                    if single_breaches:
                        st.error(
                            f"⛔ **{len(single_breaches)} single-currency breach(es):**")
                        for b in single_breaches:
                            st.write(
                                f"- **{b['currency']}** at {b['limit_pct']}% "
                                f"(limit {SINGLE_CURRENCY_LIMIT_PCT}%)")

                # Per-currency table
                per = r.get("per_currency", [])
                if per:
                    with st.expander("Per-currency limit detail"):
                        st.dataframe(pd.DataFrame([
                            {"Currency": p["currency"],
                             "NOP (KES B)": float(_D_fx(str(p["net_open_position_kes"]))/_D_fx("1000000000")),
                             "Type": p["position_type"],
                             "Limit %": p["limit_pct"],
                             "Breach": "🔴" if p["breach"] else "✅"}
                            for p in per]),
                            use_container_width=True, hide_index=True)

                audit_log("IFRS_ENGINE_USED", uname,
                           f"FX #75: Limit check core_cap={core_cap}B, "
                           f"agg_pct={agg_pct}%, status={status}, "
                           f"single_breaches={len(single_breaches)}")

        # ---- Aggregation method comparison ----
        with fx_sub_tabs[2]:
            st.markdown(
                "**Aggregation Method Comparison**: SHORTHAND vs SUM_ABSOLUTE")
            st.caption(
                "**SHORTHAND** = max(|sum of long positions|, |sum of short positions|) — Basel default. "
                "**SUM_ABSOLUTE** = sum of absolute NOPs across all currencies — more conservative. "
                "Banks may use either; SHORTHAND is more permissive.")

            if st.button("Compare methods", key="fx_agg_btn",
                          type="primary"):
                positions = []
                for i in range(3):
                    ccy = st.session_state.get(f"fx_pos_ccy_{i}", "USD")
                    a = st.session_state.get(f"fx_pos_a_{i}", 1.0)
                    l = st.session_state.get(f"fx_pos_l_{i}", 1.0)
                    sp = st.session_state.get(f"fx_pos_sp_{i}", 130.0)
                    positions.append(FxPosition(
                        position_id=f"P{i+1}", currency=ccy,
                        fx_assets_kes_equivalent=_D_fx(str(a)) * _D_fx("1000000000"),
                        fx_liabilities_kes_equivalent=_D_fx(str(l)) * _D_fx("1000000000"),
                        spot_rate_to_kes=_D_fx(str(sp))))
                r_short = FxPositionMonitoringEngine.aggregate_net_open_position(
                    positions, "SHORTHAND_METHOD")
                r_abs = FxPositionMonitoringEngine.aggregate_net_open_position(
                    positions, "SUM_ABSOLUTE")

                k1, k2 = st.columns(2)
                with k1:
                    st.metric("SHORTHAND aggregate (KES B)",
                               f"{_D_fx(str(r_short['aggregate_net_open_position_kes']))/_D_fx('1000000000'):.2f}")
                    st.caption(
                        f"Long: {_D_fx(str(r_short['sum_long_kes']))/_D_fx('1000000000'):.2f}B / "
                        f"Short: {_D_fx(str(r_short['sum_short_kes']))/_D_fx('1000000000'):.2f}B")
                with k2:
                    st.metric("SUM_ABSOLUTE aggregate (KES B)",
                               f"{_D_fx(str(r_abs['aggregate_net_open_position_kes']))/_D_fx('1000000000'):.2f}")
                    st.caption(
                        f"Sum of absolute NOPs across "
                        f"{r_abs['currency_count']} currencies")

                short_v = float(_D_fx(str(r_short['aggregate_net_open_position_kes'])))
                abs_v = float(_D_fx(str(r_abs['aggregate_net_open_position_kes'])))
                if short_v < abs_v:
                    st.info(
                        f"ℹ SHORTHAND ({short_v/1e9:.2f}B) is lower than "
                        f"SUM_ABSOLUTE ({abs_v/1e9:.2f}B) — long and short positions "
                        f"partially offset. SHORTHAND gives a more permissive view.")
                else:
                    st.info(
                        "ℹ Both methods produce the same aggregate (no offsetting between long and short).")

                audit_log("IFRS_ENGINE_USED", uname,
                           f"FX #75: Method compare SHORT={short_v}, ABS={abs_v}")


# ──────────────────────────────────────────────────────────────────────
# Section 3: 🤖 Arc Engines (absorbed from 26_treasury_arc_cockpit.py
# in v10.202 per the architectural reorganization sub-campaign.
# 12 Treasury-arc engines (ENH-231..240, ENH-LR-001, ENH-TRS-R1..R6,
# regulatory LCR — see ENH-LR-001) presented as 7 thematic sub-tabs grouping engines
# per workflow logic. Read-only display except for state-mutating
# buttons that go through utils/api_treasury.py FastAPI endpoints.
# ──────────────────────────────────────────────────────────────────────
with sections[3]:
    from datetime import datetime, timezone

    # Lazy-import engines so the rest of the page renders even if any
    # engine module fails to import. Match the cockpit's defensive style.
    try:
        from utils.treasury_intelligence import TreasuryIntelligenceEngine
        from utils.treasury_alm import TreasuryALMEngine
        from utils.treasury_dashboard import TreasuryDashboardEngine
        from utils.treasury_products import TreasuryProductsEngine
        from utils.treasury_agents import AgentOrchestrator
        from utils.treasury_connectivity import TreasuryConnectivityEngine
        from utils.treasury_digital_assets import DigitalAssetTreasuryEngine
        from utils.treasury_unified_platform import UnifiedTreasuryPlatform
        from utils.liquidity_risk import LiquidityRiskEngine
        from utils.liquidity_stress import LiquidityStressEngine
        from utils.islamic_treasury import IslamicTreasuryEngine
        from utils.climate_treasury_limits import ClimateTreasuryLimitsEngine
        _ARC_ENGINES_AVAILABLE = True
    except ImportError as _ie:
        st.error(f"Arc engines unavailable: {_ie}")
        _ARC_ENGINES_AVAILABLE = False

    try:
        from pages._cockpit_render import render_summary as _render_summary
    except ImportError:
        def _render_summary(summary, *, exclude=()):
            st.json(summary if summary else {})

    if _ARC_ENGINES_AVAILABLE:
        st.caption(
            "v10.202 absorbed from 26_treasury_arc_cockpit.py — 12 engines "
            f"(ENH-231..240, ENH-LR-001, ENH-TRS-R1..R6, {regulator()}-PG-05-LCR) "
            "spanning intelligence, ALM, products, agents, connectivity, "
            "digital assets, climate, Islamic, and unified cross-asset "
            "rollup. All engines read-only here; state-mutating workflows "
            "go through the FastAPI POST endpoints in utils/api_treasury.py.")

        # Engine instances cached at session level
        @st.cache_resource
        def _get_arc_engines():
            return {
                "intel":            TreasuryIntelligenceEngine(),
                "alm":              TreasuryALMEngine(),
                "dashboard":        TreasuryDashboardEngine(),
                "products":         TreasuryProductsEngine(),
                "agents":           AgentOrchestrator(),
                "connectivity":     TreasuryConnectivityEngine(),
                "digital_assets":   DigitalAssetTreasuryEngine(),
                "unified":          UnifiedTreasuryPlatform(),
                "liquidity_stress": LiquidityStressEngine(),
                "islamic":          IslamicTreasuryEngine(),
                "climate":          ClimateTreasuryLimitsEngine(),
            }

        engines = _get_arc_engines()

        # 7 thematic nested sub-tabs grouping the 12 engines per workflow.
        # G4 7-tab limit respected: top-level rows have 4 tabs, this nested
        # row has 7 — both within the cap.
        arc_tabs = st.tabs([
            "📊 Dashboard",
            "💧 Liquidity & ALM",
            "💰 Products",
            "🤖 Agents",
            "🔌 Connectivity",
            "🌐 Digital & Climate",
            "🕌 Islamic & Unified",
        ])

        # Sub-tab 1: Dashboard (intelligence + dashboard board pack)
        with arc_tabs[0]:
            st.subheader("Treasury Intelligence (ENH-231..234, 236)")
            st.caption(
                "Yield curves, liquidity metrics, income by instrument, "
                "ALM dashboard data — read directly from FLEXCUBE-shaped "
                "feeds via TreasuryIntelligenceEngine.")
            try:
                _today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                _cur_period = datetime.now(timezone.utc).strftime("%Y-%m")

                with st.expander("Yield curve (KES, today)", expanded=True):
                    yc = engines["intel"].yield_curve(
                        as_of_date=_today, currency="KES")
                    _render_summary(yc)

                with st.expander("Liquidity metrics (today)"):
                    lm = engines["intel"].liquidity_metrics(as_of_date=_today)
                    _render_summary(lm)

                with st.expander(f"Income by instrument ({_cur_period})"):
                    inc = engines["intel"].income_by_instrument(period=_cur_period)
                    _render_summary(inc)
            except Exception as e:
                st.error(f"Intelligence load failed: {type(e).__name__}: {e}")

            st.divider()
            st.subheader("Dashboard board pack (ENH-238)")
            try:
                bp = engines["dashboard"].board_summary()
                _render_summary(bp)
            except Exception as e:
                st.error(f"Dashboard board pack failed: {type(e).__name__}: {e}")

        # Sub-tab 2: Liquidity & ALM (ENH-233 + ENH-LR-001 + ENH-232)
        with arc_tabs[1]:
            st.subheader(f"Liquidity Risk Engine ({regulator()}-PG-05-LCR)")
            st.caption(
                "LCR/NSFR computations require posted state (HQLA holdings, "
                "cash flow items, funding components). Use the explicit POST "
                "endpoints in /api/treasury/* with typed Pydantic models. "
                "This tab shows ALM board summary + outlier scenarios.")
            try:
                ab = engines["alm"].board_summary()
                st.subheader("ALM board summary (ENH-233)")
                _render_summary(ab)
            except Exception as e:
                st.error(f"ALM board summary failed: {type(e).__name__}: {e}")

            st.divider()
            try:
                outliers = engines["alm"].outlier_scenarios()
                if outliers:
                    st.subheader(f"Outlier IRRBB scenarios (n={len(outliers)})")
                    rows = []
                    for o in outliers:
                        if hasattr(o, "__dataclass_fields__"):
                            rows.append({k: getattr(o, k)
                                          for k in o.__dataclass_fields__.keys()})
                        else:
                            rows.append({"value": str(o)})
                    if rows:
                        st.dataframe(pd.DataFrame(rows),
                                      use_container_width=True, hide_index=True)
                else:
                    st.info("No outlier scenarios — engine reports all "
                              "IRRBB scenarios within tolerance.")
            except Exception as e:
                st.error(f"Outlier scenarios failed: {type(e).__name__}: {e}")

        # Sub-tab 3: Products (ENH-234)
        with arc_tabs[2]:
            st.subheader("Treasury Products (ENH-234)")
            st.caption(
                "FD, FX, MM, Bonds with MTM and yield curves. Position "
                "registration goes through POST endpoints; this tab shows "
                "the board summary which rolls up positions already in "
                "the engine state.")
            try:
                pb = engines["products"].board_summary()
                _render_summary(pb)
            except Exception as e:
                st.error(f"Products board summary failed: {type(e).__name__}: {e}")

        # Sub-tab 4: Agents (ENH-240)
        with arc_tabs[3]:
            st.subheader("Treasury Agents Orchestration (ENH-240)")
            st.caption(
                "AgentOrchestrator + 5 agents (Cash, FX, MM, Risk, "
                "Compliance). Recommendations lifecycle: pending → "
                "approve/reject. This tab shows the current board summary.")
            try:
                ab = engines["agents"].board_summary()
                _render_summary(ab)
            except Exception as e:
                st.error(f"Agents board summary failed: {type(e).__name__}: {e}")

        # Sub-tab 5: Connectivity (ENH-TRS-R1, R3, R5)
        with arc_tabs[4]:
            st.subheader("Treasury Connectivity (ENH-TRS-R1, R3, R5)")
            st.caption(
                "9900+ bank connections + MMF direct access + ERP-to-Bank "
                "payment journeys. Currently shows board summary of "
                "registered connectors and counterparties.")
            try:
                cb = engines["connectivity"].board_summary()
                _render_summary(cb)
            except Exception as e:
                st.error(f"Connectivity board summary failed: "
                          f"{type(e).__name__}: {e}")

        # Sub-tab 6: Digital & Climate (ENH-TRS-R2 + ENH-TRS-R6)
        with arc_tabs[5]:
            st.subheader("Digital Asset Treasury (ENH-TRS-R2)")
            st.caption(
                "Stablecoin and digital asset treasury integration. "
                "Wallet whitelisting + holdings + spot rates.")
            try:
                if hasattr(engines["digital_assets"], "board_summary"):
                    db_ = engines["digital_assets"].board_summary()
                    _render_summary(db_)
                else:
                    st.info("DigitalAssetTreasuryEngine has no board_summary "
                              "method. Engine present and instantiable; "
                              "integration is by direct method calls only.")
            except Exception as e:
                st.error(f"Digital Assets failed: {type(e).__name__}: {e}")

            st.divider()
            st.subheader("Climate-Adjusted Treasury Limits (ENH-TRS-R6)")
            st.caption(
                "Climate-overlay adjustments to treasury exposure limits "
                "by asset class. Read-only — limits are computed from the "
                "configured climate engine at request time.")
            try:
                cb_ = engines["climate"].board_summary()
                _render_summary(cb_)

                st.subheader("All adjusted limits")
                _arc_limits = engines["climate"].compute_all_limits()
                if _arc_limits:
                    rows = []
                    for li in _arc_limits:
                        if hasattr(li, "__dataclass_fields__"):
                            rows.append({k: getattr(li, k)
                                          for k in li.__dataclass_fields__.keys()})
                    if rows:
                        st.dataframe(pd.DataFrame(rows),
                                      use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Climate limits failed: {type(e).__name__}: {e}")

        # Sub-tab 7: Islamic & Unified (ENH-239 + ENH-TRS-R4)
        with arc_tabs[6]:
            st.subheader("Islamic Treasury (ENH-239)")
            st.caption(
                "Sharia-compliant treasury products. board_summary + "
                "non-compliant products surfaced for review.")
            try:
                ib = engines["islamic"].board_summary()
                _render_summary(ib)

                non_compliant = engines["islamic"].non_compliant_products()
                if non_compliant:
                    st.subheader(f"⚠️ Non-compliant products (n={len(non_compliant)})")
                    rows = []
                    for p in non_compliant:
                        if hasattr(p, "__dataclass_fields__"):
                            rows.append({k: getattr(p, k)
                                          for k in p.__dataclass_fields__.keys()})
                    if rows:
                        st.dataframe(pd.DataFrame(rows),
                                      use_container_width=True, hide_index=True)
                else:
                    st.success("All Islamic products Sharia-compliant.")
            except Exception as e:
                st.error(f"Islamic Treasury failed: {type(e).__name__}: {e}")

            st.divider()
            st.subheader("Unified Treasury Platform (ENH-TRS-R4)")
            st.caption(
                "MX.3-class cross-asset rollup combining FX, MM, Bonds, "
                "Liquidity. Single source of truth for board reporting.")
            try:
                ub = engines["unified"].board_summary()
                _render_summary(ub)

                positions = engines["unified"].positions()
                if positions:
                    st.subheader(f"Positions (n={len(positions)})")
                    rows = []
                    for p in positions:
                        if hasattr(p, "__dataclass_fields__"):
                            rows.append({k: getattr(p, k)
                                          for k in p.__dataclass_fields__.keys()})
                    if rows:
                        st.dataframe(pd.DataFrame(rows),
                                      use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Unified Platform failed: {type(e).__name__}: {e}")

        # Footer audit log
        try:
            audit_log(
                action="treasury_arc_engines.view",
                username=ud.get("username", "anonymous"),
                detail=f"viewed_at={datetime.now(timezone.utc).isoformat()}",
                module="alm_liquidity")
        except Exception:
            pass
