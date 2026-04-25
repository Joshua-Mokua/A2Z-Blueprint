"""pages/68_clearing.py — Clearing & Settlement Management.
Dept: Operations | KPIs: K055 K056 K057 | BSC: Auto-scored
Hardcoded: CBK regulatory systems (RTGS, EFT, SWIFT, PESALINK)
Configurable: fail-rate threshold, nostro accounts, batch windows, recon SLA
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
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
is_ops   = any(x in role for x in ("operation","settlement","clearing","treasury","finance","manager","head","director","chief"))

# ── HARDCODED (CBK-mandated, cannot be changed) ───────────────────
CBK_SYSTEMS   = ["RTGS","EFT","SWIFT","PESALINK","CHEQUE","MOBILE MONEY","CARD"]
CBK_CURRENCIES= ["KES","USD","EUR","GBP","UGX","TZS","RWF"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception:
        pass

@st.cache_data(ttl=30)
def _load():
    p = DATA / "clearing_records.json"
    raw = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
    return [{k: float(v) if isinstance(v, Decimal) else v for k,v in r.items()} for r in raw]

@st.cache_data(ttl=60)
def _cfg():
    mc = DATA / "module_config.json"
    if not mc.exists(): return {}
    return json.loads(mc.read_text(encoding="utf-8")).get("clearing", {})

def _save(data):
    (DATA/"clearing_records.json").write_text(json.dumps(data, indent=2))
    st.cache_data.clear()

records = _load()
cfg_c   = _cfg()
configurable = cfg_c.get("configurable", {})
fail_thresh  = configurable.get("fail_rate_threshold_pct", 5.0)
recon_sla    = configurable.get("recon_sla_hours", 24)
nostro_list  = configurable.get("nostro_accounts", [])
batch_windows= configurable.get("batch_windows", ["08:00","11:00","14:00","16:00"])

# ── KPI calculations ─────────────────────────────────────────────
failed    = [r for r in records if r.get("status") in ("Failed","Rejected","Reversed")]
settled   = [r for r in records if r.get("status") == "Settled"]
pending   = [r for r in records if r.get("status") == "Pending"]
recon_ok  = [r for r in records if r.get("reconciled")]
total_val = sum(r.get("amount_kes",0) for r in records)
fail_rate = round(len(failed)/max(len(records),1)*100,1)
recon_pct = round(len(recon_ok)/max(len(records),1)*100,1)
same_day  = sum(1 for r in settled if r.get("value_date","")[:10]==r.get("settlement_date","")[:10])
same_day_pct = round(same_day/max(len(settled),1)*100,1)
discrepancies = [r for r in records if r.get("discrepancy_kes",0) > 0]

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🏦 Clearing & Settlement</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Operations · K055 · K056 · K057</span></div>",
    unsafe_allow_html=True)

# ── Alerts ────────────────────────────────────────────────────────
if fail_rate > fail_thresh:
    st.error(f"🔴 Settlement fail rate {fail_rate}% exceeds {fail_thresh}% threshold — escalate immediately")
if discrepancies:
    st.warning(f"⚠️ {len(discrepancies)} items with reconciliation discrepancies")

# ── KPI strip ─────────────────────────────────────────────────────
m1,m2,m3,m4,m5,m6 = st.columns(6)
m1.metric("Total items",     len(records))
m2.metric("Settled",         len(settled))
m3.metric("Failed",          len(failed),      delta_color="inverse" if failed else "off")
m4.metric("Fail rate",       f"{fail_rate}%",  delta_color="inverse" if fail_rate>fail_thresh else "off")
m5.metric("Same-day %",      f"{same_day_pct}%")
m6.metric("Reconciled %",    f"{recon_pct}%",  delta_color="off")

tabs = st.tabs(["📋 Register","❌ Exceptions","🔍 Reconciliation","➕ New Entry",
                "📊 Analytics","⚙️ Config","📈 BSC"])

# ── TAB 0 — Register ─────────────────────────────────────────────
with tabs[0]:
    f1,f2,f3,f4 = st.columns(4)
    fsys  = f1.selectbox("System",   ["All"]+CBK_SYSTEMS, key="cl_sys")
    fstat = f2.selectbox("Status",   ["All","Pending","Settled","Failed","Queued","Rejected","Reversed"], key="cl_stat")
    fcur  = f3.selectbox("Currency", ["All"]+CBK_CURRENCIES, key="cl_cur")
    fdays = f4.number_input("Last N days", 1, 365, 30, key="cl_days")
    cutoff = str(today - timedelta(days=int(fdays)))
    vis = [r for r in records
           if (fsys=="All" or r.get("system","")==fsys)
           and (fstat=="All" or r.get("status","")==fstat)
           and (fcur=="All" or r.get("currency","")==fcur)
           and r.get("value_date","")>=cutoff]
    rows = [{
        "ID":r["id"],"System":r.get("system",""),"Ref":r.get("transaction_ref","")[:15],
        "Amount":f"KES {r.get('amount_kes',0):,.0f}","Currency":r.get("currency","KES"),
        "Status":r.get("status",""),"Value Date":r.get("value_date","")[:10],
        "Settlement":r.get("settlement_date","")[:10],"Reconciled":"✅" if r.get("reconciled") else "⏳",
        "Discrepancy":f"KES {r.get('discrepancy_kes',0):,.0f}" if r.get("discrepancy_kes",0)>0 else "",
    } for r in sorted(vis, key=lambda x:x.get("value_date",""), reverse=True)]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    c1,c2,c3 = st.columns(3)
    c1.caption(f"Showing {len(vis)} of {len(records)} items")
    c2.caption(f"Total value: KES {sum(r.get('amount_kes',0) for r in vis)/1e9:.2f}B")
    c3.caption(f"Batch windows: {', '.join(batch_windows)}")

# ── TAB 1 — Exceptions ───────────────────────────────────────────
with tabs[1]:
    st.markdown("**Failed, rejected and reversed items requiring action:**")
    if failed:
        for r in failed:
            with st.expander(f"❌ {r['id']} — {r.get('system','')} — KES {r.get('amount_kes',0):,.0f}"):
                c1,c2,c3 = st.columns(3)
                c1.metric("Amount", f"KES {r.get('amount_kes',0):,.0f}")
                c2.metric("Status", r.get("status",""))
                c3.metric("Value Date", r.get("value_date","")[:10])
                st.markdown(f"**Reason:** {r.get('failure_reason','—')} | **Ref:** {r.get('transaction_ref','')}")
                action = st.selectbox("Action", ["Select","Reprocess","Reverse","Escalate","Write off"],
                                     key=f"cl_act_{r['id']}")
                notes  = st.text_input("Notes", key=f"cl_note_{r['id']}")
                if st.button("💾 Apply", key=f"cl_apply_{r['id']}", type="primary"):
                    if action != "Select":
                        all_r = _load()
                        for rec in all_r:
                            if rec["id"] == r["id"]:
                                rec["notes"] = f"{action}: {notes}"
                                if action in ("Reprocess","Reverse"): rec["status"] = "Pending"
                                break
                        _save(all_r)
                        audit_log("CLEARING_EXCEPTION_ACTIONED", uname, f"{r['id']}: {action}")
                        _bsc_trigger(uname, "K055")
                        st.success(f"✅ {action} applied"); st.rerun()
    else:
        st.success("✅ No failed items in current period.")

# ── TAB 2 — Reconciliation ───────────────────────────────────────
with tabs[2]:
    unreconciled = [r for r in records if not r.get("reconciled") and r.get("status")=="Settled"]
    c1,c2,c3 = st.columns(3)
    c1.metric("Unreconciled settled", len(unreconciled))
    c2.metric("Reconciled", len(recon_ok))
    c3.metric("Discrepancies", len(discrepancies))

    if unreconciled:
        st.markdown("**Items pending reconciliation:**")
        for r in unreconciled[:30]:
            c1,c2,c3,c4 = st.columns([3,2,2,1])
            c1.markdown(f"**{r['id']}** — {r.get('system','')} — {r.get('transaction_ref','')[:12]}")
            c2.markdown(f"KES {r.get('amount_kes',0):,.0f}")
            c3.markdown(r.get("value_date","")[:10])
            if c4.button("✅", key=f"recon_{r['id']}", help="Mark reconciled"):
                all_r = _load()
                for rec in all_r:
                    if rec["id"] == r["id"]:
                        rec["reconciled"]    = True
                        rec["reconciled_at"] = str(today)
                        break
                _save(all_r)
                audit_log("CLEARING_RECONCILED", uname, r["id"])
                _bsc_trigger(uname, "K057")
                st.success("✅ Reconciled"); st.rerun()
        if is_ops and st.button("✅ Reconcile all settled items", key="cl_recon_all"):
            all_r = _load()
            count = 0
            for rec in all_r:
                if not rec.get("reconciled") and rec.get("status")=="Settled":
                    rec["reconciled"]    = True
                    rec["reconciled_at"] = str(today)
                    count += 1
            _save(all_r)
            audit_log("CLEARING_BULK_RECON", uname, f"{count} items reconciled")
            _bsc_trigger(uname, "K057")
            st.success(f"✅ {count} items reconciled"); st.rerun()

# ── TAB 3 — New Entry ────────────────────────────────────────────
with tabs[3]:
    if is_ops or is_admin:
        r1,r2 = st.columns(2)
        sys_   = r1.selectbox("Clearing system *", CBK_SYSTEMS, key="cl_new_sys")
        cur_   = r2.selectbox("Currency", CBK_CURRENCIES, key="cl_new_cur")
        ref_   = r1.text_input("Transaction reference *", key="cl_new_ref")
        amt_   = r2.number_input("Amount", 0.0, key="cl_new_amt")
        debit_ = r1.text_input("Debit account", key="cl_new_deb")
        credit_= r2.text_input("Credit account", key="cl_new_cred")
        vdate_ = r1.date_input("Value date", today, key="cl_new_vd")
        nostro_opts = [""] + [n["id"]+" — "+n["name"] for n in nostro_list]
        nostro_= r2.selectbox("Nostro account", nostro_opts, key="cl_new_nostro")
        cbk_   = st.text_input("CBK batch reference", key="cl_new_cbk")
        if st.button("💾 Submit clearing item", key="cl_new_save", type="primary"):
            if ref_.strip() and amt_ > 0:
                all_r = _load()
                all_r.append({
                    "id": f"CLR{len(all_r)+1:05d}", "value_date": str(vdate_),
                    "settlement_date": "", "system": sys_, "transaction_ref": ref_.strip(),
                    "debit_account": debit_.strip(), "credit_account": credit_.strip(),
                    "amount_kes": amt_, "currency": cur_, "status": "Pending",
                    "failure_reason": "", "settled_by": "", "nostro_account": nostro_.split(" — ")[0],
                    "cbk_batch_ref": cbk_.strip(), "reconciled": False, "reconciled_at": "",
                    "discrepancy_kes": 0, "notes": "",
                })
                _save(all_r)
                audit_log("CLEARING_SUBMITTED", uname, f"{ref_}: KES {amt_:,.0f} via {sys_}")
                _bsc_trigger(uname, "K056")
                st.success("✅ Clearing item submitted"); st.rerun()
            else:
                st.error("Reference and amount required.")
    else:
        st.info("Entry available to Operations team.")

# ── TAB 4 — Analytics ────────────────────────────────────────────
with tabs[4]:
    c1,c2 = st.columns(2)
    with c1:
        by_sys = defaultdict(lambda:{"total":0,"failed":0,"value":0})
        for r in records:
            s = r.get("system","Other")
            by_sys[s]["total"]  += 1
            by_sys[s]["value"]  += r.get("amount_kes",0)
            if r.get("status") in ("Failed","Rejected","Reversed"):
                by_sys[s]["failed"] += 1
        st.markdown("**By system:**")
        an_rows = [{"System":s,"Items":v["total"],"Failed":v["failed"],
                     "Fail%":f"{v['failed']/max(v['total'],1)*100:.1f}%",
                     "Value (B)":f"{v['value']/1e9:.2f}"}
                    for s,v in sorted(by_sys.items(),key=lambda x:-x[1]["value"])]
        st.dataframe(pd.DataFrame(an_rows), use_container_width=True, hide_index=True)
    with c2:
        st.markdown("**Status breakdown:**")
        by_stat = defaultdict(int)
        for r in records: by_stat[r.get("status","Unknown")] += 1
        st.bar_chart(pd.DataFrame({"Count":by_stat}))

# ── TAB 5 — Config (Admin) ────────────────────────────────────────
with tabs[5]:
    if is_admin:
        st.markdown("**Configurable settings for Clearing & Settlement:**")
        st.info("ℹ️ Hardcoded (CBK-mandated, cannot change): clearing systems (RTGS, EFT, SWIFT, PESALINK, CHEQUE), accepted currencies, CBK reporting requirement.")

        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("clearing",{}).get("configurable",{})

        c1,c2 = st.columns(2)
        new_fail = c1.number_input("Fail rate alert threshold (%)", 1.0, 20.0,
                                   float(cfg_m.get("fail_rate_threshold_pct",5.0)), 0.5, key="cl_cfg_fail")
        new_recon = c2.number_input("Reconciliation SLA (hours)", 1, 72,
                                    int(cfg_m.get("recon_sla_hours",24)), key="cl_cfg_recon")
        new_email = st.text_input("Escalation email", cfg_m.get("escalation_email",""), key="cl_cfg_email")
        new_disc  = st.number_input("Discrepancy alert threshold (KES)", 0, 100000,
                                    int(cfg_m.get("discrepancy_alert_kes",1000)), key="cl_cfg_disc")
        new_auto  = st.checkbox("Auto-reconcile settled items", cfg_m.get("auto_reconcile",True), key="cl_cfg_auto")

        st.markdown("**Nostro accounts:**")
        nostro_df = pd.DataFrame(cfg_m.get("nostro_accounts",[]))
        if not nostro_df.empty:
            st.dataframe(nostro_df, use_container_width=True, hide_index=True)

        with st.expander("➕ Add nostro account"):
            n1,n2,n3 = st.columns(3)
            n_id  = n1.text_input("Account ID", key="cl_n_id")
            n_name= n2.text_input("Account name", key="cl_n_name")
            n_cur = n3.selectbox("Currency", CBK_CURRENCIES, key="cl_n_cur")
            if st.button("Add nostro", key="cl_n_add"):
                if n_id.strip() and n_name.strip():
                    mc["clearing"]["configurable"].setdefault("nostro_accounts",[]).append(
                        {"id":n_id.strip(),"name":n_name.strip(),"currency":n_cur})
                    (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
                    audit_log("CLEARING_CFG_NOSTRO",uname,n_name)
                    st.cache_data.clear(); st.success("✅ Nostro added"); st.rerun()

        if st.button("💾 Save configuration", key="cl_cfg_save", type="primary"):
            mc["clearing"]["configurable"].update({
                "fail_rate_threshold_pct": new_fail,
                "recon_sla_hours":         new_recon,
                "escalation_email":        new_email,
                "discrepancy_alert_kes":   new_disc,
                "auto_reconcile":          new_auto,
            })
            (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("CLEARING_CFG_SAVED", uname, "Config updated")
            st.cache_data.clear(); st.success("✅ Configuration saved"); st.rerun()
    else:
        st.info("Configuration available to Admin only.")

# ── TAB 6 — BSC ──────────────────────────────────────────────────
with tabs[6]:
    st.markdown("**Your BSC KPIs from Clearing & Settlement:**")
    st.caption("These are auto-scored from your clearing activity — no manual entry needed.")
    bsc_rows = [
        {"KPI":"K055 — Settlement Fail Rate","Target":f"< {fail_thresh}%","Actual":f"{fail_rate}%",
         "Weight":"10%","Status":"🟢" if fail_rate<fail_thresh else "🔴","Direction":"Lower is better"},
        {"KPI":"K056 — Same-day Settlement","Target":"> 90%","Actual":f"{same_day_pct}%",
         "Weight":"8%","Status":"🟢" if same_day_pct>90 else "🟡","Direction":"Higher is better"},
        {"KPI":"K057 — Reconciliation Completion","Target":"> 95%","Actual":f"{recon_pct}%",
         "Weight":"8%","Status":"🟢" if recon_pct>95 else "🟡","Direction":"Higher is better"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows), use_container_width=True, hide_index=True)
    if st.button("🔄 Refresh my BSC from clearing data", key="cl_bsc_ref", type="primary"):
        _bsc_trigger(uname, "K055")
        st.success("✅ BSC updated from clearing module"); st.cache_data.clear(); st.rerun()
