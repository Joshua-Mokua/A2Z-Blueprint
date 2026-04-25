"""pages/15_cbs.py — CBS Explorer."""
import streamlit as st
import pandas as pd
import json
import random
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils import flexcube_adapter as fcx

require_access("cbs")

# ── FLEXCUBE Integration Status ──────────────────────────────────
_fcx_mode = fcx.get_mode()
_fcx_badge = fcx.get_status_badge()
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏦 CBS Explorer</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Account lookup · Customer view · Transaction history · CIF</span></div>",
    unsafe_allow_html=True)

st.info("CBS Explorer provides read-only access to core banking data. "
        "Modifications must be done through the Core Banking System (Temenos T24).")

@st.cache_data(ttl=60, show_spinner=False)
def _load_base():
    cm = json.loads((DATA/"credit_monitoring.json").read_text()) if (DATA/"credit_monitoring.json").exists() else {}
    watchlist = cm.get("watchlist",[]) if isinstance(cm,dict) else cm
    ci = {}
    if (DATA/"customer_intelligence.json").exists():
        ci = json.loads((DATA/"customer_intelligence.json").read_text())
    apps = json.loads((DATA/"loan_applications.json").read_text()) if (DATA/"loan_applications.json").exists() else []
    pipe = json.loads((DATA/"pipeline.json").read_text()) if (DATA/"pipeline.json").exists() else []
    acct_idx = {r.get("account_number",""): r for r in watchlist if r.get("account_number")}
    cif_idx  = defaultdict(list)
    for r in watchlist:
        if r.get("cif"): cif_idx[str(r["cif"])].append(r)
    return acct_idx, cif_idx, ci, apps, pipe

acct_idx, cif_idx, cust_intel, apps, pipeline = _load_base()


st.caption(f"📡 Data source: {_fcx_badge} | Mode: **{_fcx_mode.upper()}**")
tabs = st.tabs(["🔍 Account Lookup","👤 CIF / Customer View","📊 Portfolio Summary","📋 Batch Search"])

with tabs[0]:
    c1,c2 = st.columns([2,1])
    acct_input = c1.text_input("Account number / CIF", key="cbs_acct",
                                placeholder="e.g. ECO1000000001 or CIF 100000001")
    search_type = c2.radio("Search by", ["Account Number","CIF"], horizontal=True, key="cbs_stype")
    if acct_input.strip():
        q = acct_input.strip().upper()
        if search_type == "Account Number":
            results = [(a, r) for a, r in acct_idx.items() if q in a.upper()][:10]
        else:
            accts = cif_idx.get(str(acct_input.strip()), [])
            results = [(r.get("account_number",""), r) for r in accts[:10]]
        st.markdown(f"**{len(results)} account(s) found:**")
        if results:
            sel_labels = [f"{a} — {r.get('branch_name','')} — {r.get('classification','')} — KES {r.get('outstanding',0)/1e3:.0f}K"
                          for a, r in results]
            sel_acct = st.selectbox("Select account", sel_labels, key="cbs_sel")
            acct_no, rec = results[sel_labels.index(sel_acct)]
            cls   = rec.get("classification","Watch")
            cls_c = {"NPL":"#DC2626","Stage 3":"#DC2626","Watch":"#D97706",
                     "Stage 2":"#D97706","Stage 1":"#16A34A","Normal":"#16A34A"}.get(cls,"#6B7280")
            st.markdown(
                f"<div style='background:var(--color-background-secondary);"
                f"border:1px solid var(--color-border);border-radius:10px;padding:14px 18px;margin:8px 0'>"
                f"<b>{acct_no}</b> &nbsp; "
                f"<span style='background:{cls_c}18;color:{cls_c};border-radius:10px;padding:2px 8px'>{cls}</span>"
                f" &nbsp; CIF: {rec.get('cif','—')} · Branch: {rec.get('branch_name','—')}</div>",
                unsafe_allow_html=True)
            d1,d2,d3,d4 = st.columns(4)
            d1.metric("Loan Amount",   f"KES {rec.get('loan_amount',0)/1e6:.2f}M")
            d2.metric("Outstanding",   f"KES {rec.get('outstanding',0)/1e6:.2f}M")
            d3.metric("Collateral",    f"KES {rec.get('collateral_value',0)/1e6:.2f}M")
            d4.metric("NPL Days",      f"{rec.get('npl_days',0)}")
            st.markdown(f"**Collateral:** {rec.get('collateral_type','—')} | "
                        f"**RM:** {rec.get('rm_name', rec.get('account_officer','—'))} | "
                        f"**Region:** {rec.get('region','—')}")
            covenants = rec.get("covenants",[])
            if covenants:
                st.markdown("**Covenants:**")
                for cv in covenants:
                    icon = "✅" if cv.get("status")=="Compliant" else "⚠️"
                    st.markdown(f"  {icon} {cv.get('type','')} — {cv.get('status','')} · Review: {cv.get('next_review','')[:10]}")
            st.markdown("**Recent transactions (simulated CBS feed):**")
            random.seed(int("".join(filter(str.isdigit, acct_no)) or "0") % 9999)
            txns = []
            bal = float(rec.get("outstanding",0))
            tx_descs = ["MPESA RECEIPT","LOAN INSTALMENT","INT CHARGE","TRANSFER IN","TRANSFER OUT","SALARY CREDIT","DD PAYMENT","ATM WITHDRAWAL"]
            for i in range(10):
                t_date = today - timedelta(days=i*3+random.randint(0,5))
                amt    = random.uniform(-50000, 80000)
                if bal + amt < 0: amt = abs(amt)
                bal   += amt
                txns.append({"Date":t_date.isoformat()[:10],
                              "Description":random.choice(tx_descs),
                              "Amount":round(amt,2),"Balance":round(abs(bal),2)})
            st.dataframe(pd.DataFrame(sorted(txns, key=lambda x:x["Date"],reverse=True)),
                         use_container_width=True, hide_index=True)
        else:
            st.warning(f"No accounts found matching '{acct_input}'")
    else:
        st.markdown("Enter an account number or CIF to search.")

with tabs[1]:
    cif_input = st.text_input("CIF number", key="cbs_cif", placeholder="e.g. 100000001")
    if cif_input.strip():
        cif = str(cif_input.strip())
        accts_for_cif = cif_idx.get(cif, [])
        intel = cust_intel.get(cif,{}) if cust_intel else {}
        if accts_for_cif or intel:
            st.markdown(f"**CIF {cif} — {len(accts_for_cif)} account(s):**")
            if intel:
                ci1,ci2,ci3,ci4 = st.columns(4)
                ci1.metric("Segment",         intel.get("segment","—"))
                ci2.metric("Churn Risk",       f"{intel.get('churn_risk',0)*100:.0f}%")
                ci3.metric("Next Best Action", intel.get("nba","—"))
                ci4.metric("CLV (est.)",       f"KES {intel.get('clv_estimate',0)/1e3:.0f}K")
            for acct in accts_for_cif:
                st.markdown(
                    f"• **{acct.get('account_number','')}** — {acct.get('classification','')} — "
                    f"KES {acct.get('outstanding',0)/1e6:.2f}M — {acct.get('branch_name','')}")
            cif_apps = [a for a in apps if str(a.get("client_cif",""))==cif]
            cif_pipe = [d for d in pipeline if str(d.get("client_cif",""))==cif]
            if cif_apps:
                st.markdown(f"**{len(cif_apps)} loan application(s):**")
                for a in cif_apps:
                    st.markdown(f"  • {a['id']} — {a['product']} — KES {a.get('amount',0)/1e6:.1f}M — {a['status']}")
            if cif_pipe:
                st.markdown(f"**{len(cif_pipe)} pipeline deal(s):**")
                for d in cif_pipe:
                    st.markdown(f"  • {d.get('product','')} — KES {float(d.get('amount',0))/1e6:.1f}M — {d.get('stage','')}")
        else:
            st.warning(f"CIF {cif} not found in CBS data.")

with tabs[2]:
    st.markdown("**CBS portfolio overview:**")
    total_accts = len(acct_idx)
    total_out   = sum(r.get("outstanding",0) for r in acct_idx.values())/1e9
    npl_accts   = sum(1 for r in acct_idx.values() if r.get("npl_days",0)>90)
    by_class    = defaultdict(int)
    for r in acct_idx.values(): by_class[r.get("classification","Normal")]+=1
    pm1,pm2,pm3,pm4 = st.columns(4)
    pm1.metric("Total Accounts",    f"{total_accts:,}")
    pm2.metric("Total Outstanding", f"KES {total_out:.1f}B")
    pm3.metric("NPL Accounts",      f"{npl_accts:,}", f"{npl_accts/max(total_accts,1)*100:.1f}%")
    pm4.metric("Unique CIFs",       f"{len(cif_idx):,}")
    df_cls = pd.DataFrame([{"Classification":k,"Accounts":v}
                             for k,v in sorted(by_class.items(),key=lambda x:-x[1])])
    st.dataframe(df_cls, use_container_width=True, hide_index=True)

with tabs[3]:
    st.markdown("**Batch account search — paste account numbers (one per line):**")
    bulk_input = st.text_area("Account numbers", height=150, key="cbs_bulk",
                               placeholder="ECO1000000001\nECO1000000002\n...")
    if bulk_input.strip() and st.button("🔍 Search batch", key="cbs_batch"):
        queries = [q.strip().upper() for q in bulk_input.strip().split("\n") if q.strip()]
        found = []; missing = []
        for q in queries:
            if q in acct_idx:
                r = acct_idx[q]
                found.append({"Account":q,"CIF":r.get("cif",""),"Branch":r.get("branch_name",""),
                               "Outstanding (M)":round(r.get("outstanding",0)/1e6,2),
                               "Classification":r.get("classification",""),
                               "NPL Days":r.get("npl_days",0)})
            else:
                missing.append(q)
        st.markdown(f"**Found: {len(found)} · Not found: {len(missing)}**")
        if found:
            st.dataframe(pd.DataFrame(found), use_container_width=True, hide_index=True)
        if missing:
            st.warning(f"Not found: {missing[:10]}")
