"""pages/62_p2p.py — Procure-to-Pay (P2P).
Purchase requests → POs → Goods receipt → Invoices → Payment.
Co-owned: Procurement raises PRs/POs; Finance approves invoices for payment.
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
from utils.core import audit_log

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
        audit_log("BSC_AUTO_UPDATE", username, f"Module action: {kpi}")
    except Exception:
        pass


require_access("p2p")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
dept     = ud.get("department","")
is_admin = ud.get("is_admin",False)
is_proc  = any(x in role for x in ("procurement","head of procurement","facilities"))
is_fin   = any(x in role for x in ("financial","cfo","finance","controller","accounts"))
is_req   = True  # any staff can raise a PR

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🛒 Procure-to-Pay (P2P)</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Purchase Requests · Purchase Orders · Goods Receipt · Invoices · Payment</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load_prs():
    p = DATA / "purchase_requests.json"
    return a2z_db.load_json(p) if p.exists() else []

@st.cache_data(ttl=30)
def _load_pos():
    p = DATA / "purchase_orders.json"
    return a2z_db.load_json(p) if p.exists() else []

@st.cache_data(ttl=30)
def _load_invs():
    p = DATA / "invoices.json"
    return a2z_db.load_json(p) if p.exists() else []

prs  = _load_prs()
pos  = _load_pos()
invs = _load_invs()

pending_pr  = [p for p in prs  if p.get("status") in ("Submitted",)]
overdue_inv = [i for i in invs if i.get("status") == "Overdue"]
mismatch    = [i for i in invs if i.get("match_status") == "Mismatch" and i.get("status") not in ("Paid",)]
pending_pay = [i for i in invs if i.get("status") == "Approved for Payment"]

# Alert strip
if overdue_inv:
    st.error(f"🔴 {len(overdue_inv)} invoice(s) OVERDUE — immediate payment action required")
if mismatch:
    st.warning(f"⚠️ {len(mismatch)} invoice(s) with 3-way match mismatch — review before payment")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Open PRs",        sum(1 for p in prs if p.get("status") not in ("Rejected","Closed")))
m2.metric("Pending Approval",len(pending_pr), delta_color="normal" if not pending_pr else "inverse")
m3.metric("Active POs",      sum(1 for p in pos if p.get("status") not in ("Fully Received","Cancelled")))
m4.metric("Overdue Invoices",len(overdue_inv),delta_color="normal" if not overdue_inv else "inverse")
m5.metric("Pending Payment", len(pending_pay))

tabs = st.tabs(["📋 Purchase Requests","📦 Purchase Orders","🧾 Invoices",
                "💳 Payment Queue","➕ Raise PR","📊 Analytics"])

# ── TAB 0: Purchase Requests ──────────────────────────────────────
with tabs[0]:
    f1,f2 = st.columns(2)
    f_stat = f1.selectbox("Status",["All","Draft","Submitted","Approved","Rejected","On Hold"],key="p2p_prst")
    f_dept = f2.selectbox("Department",["All"]+sorted(set(p.get("department","") for p in prs)),key="p2p_dept")
    vis_pr = [p for p in prs
              if (f_stat=="All" or p.get("status")==f_stat)
              and (f_dept=="All" or p.get("department")==f_dept)]
    # Non-procurement staff see only their dept
    if not (is_proc or is_admin or is_fin):
        vis_pr = [p for p in vis_pr if p.get("department")==dept or p.get("requested_by")==uname]
    rows = [{"ID":p["id"],"Title":p["title"][:35],"Dept":p["department"][:18],
              "Category":p["category"][:20],"Amount (KES)":f"{p['amount_kes']:,.0f}",
              "Status":p["status"],"Urgent":"🔴" if p.get("urgent") else "",
              "Requested":p["request_date"][:10]}
             for p in sorted(vis_pr, key=lambda x: x.get("request_date",""), reverse=True)]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if is_proc or is_admin:
        st.markdown("**Approve / Reject a PR:**")
        sub_prs = [p for p in prs if p["status"]=="Submitted"]
        if sub_prs:
            sel_pr = st.selectbox("Select PR", [p["id"] for p in sub_prs], key="p2p_apr_sel")
            c1,c2  = st.columns(2)
            if c1.button("✅ Approve", key="p2p_apr", type="primary"):
                all_p = json.loads((DATA/"purchase_requests.json").read_text())
                for p in all_p:
                    if p["id"]==sel_pr:
                        p["status"]="Approved"; p["approved_by"]=uname; p["approval_date"]=str(today)
                (DATA/"purchase_requests.json").write_text(json.dumps(all_p,indent=2))
                audit_log("PR_APPROVED", uname, sel_pr)
                _bsc_trigger(uname, "K051")
                st.cache_data.clear(); st.success("✅ PR Approved"); st.rerun()
            if c2.button("❌ Reject", key="p2p_rej"):
                all_p = json.loads((DATA/"purchase_requests.json").read_text())
                for p in all_p:
                    if p["id"]==sel_pr: p["status"]="Rejected"
                (DATA/"purchase_requests.json").write_text(json.dumps(all_p,indent=2))
                audit_log("PR_REJECTED", uname, sel_pr)
                _bsc_trigger(uname, "K051")
                st.cache_data.clear(); st.success("PR rejected"); st.rerun()
        else:
            st.success("✅ No PRs pending approval")

# ── TAB 1: Purchase Orders ─────────────────────────────────────────
with tabs[1]:
    po_rows = [{"PO":p["id"],"PR":p["pr_id"],"Vendor":p["vendor"][:20],
                 "Dept":p["department"][:18],"Amount (KES)":f"{p['amount_kes']:,.0f}",
                 "Status":p["status"],"Issue Date":p.get("issue_date","")[:10],
                 "Delivery":p.get("delivery_date","")[:10],
                 "3-Way Match":"✅" if p.get("3way_match") else "⏳"}
                for p in sorted(pos, key=lambda x: x.get("issue_date",""), reverse=True)]
    st.dataframe(pd.DataFrame(po_rows), use_container_width=True, hide_index=True)
    total_po = sum(p["amount_kes"] for p in pos)
    st.caption(f"Total PO commitment: KES {total_po/1e6:.1f}M")

# ── TAB 2: Invoices ────────────────────────────────────────────────
with tabs[2]:
    f3,f4 = st.columns(2)
    f_ist = f3.selectbox("Status",["All","Received","Under Review","Approved for Payment",
                                    "Paid","Disputed","Overdue"], key="p2p_ist")
    f_imt = f4.selectbox("Match Status",["All","Matched","Mismatch","Pending"],key="p2p_imt")
    vis_inv = [i for i in invs
               if (f_ist=="All" or i.get("status")==f_ist)
               and (f_imt=="All" or i.get("match_status")==f_imt)]
    inv_rows = [{"ID":i["id"],"Vendor":i["vendor"][:20],"Dept":i["department"][:15],
                  "Amount (KES)":f"{i['amount_kes']:,.0f}","Due Date":i.get("due_date","")[:10],
                  "Status":i["status"],"Match":i.get("match_status",""),
                  "Finance":("✅" if i.get("finance_approved") else "")}
                 for i in sorted(vis_inv, key=lambda x: x.get("due_date",""))]
    st.dataframe(pd.DataFrame(inv_rows), use_container_width=True, hide_index=True)

    if is_fin or is_admin:
        st.markdown("**Approve invoice for payment:**")
        approvable = [i for i in invs if i.get("status")=="Under Review" and i.get("3way_match")]
        if approvable:
            sel_inv = st.selectbox("Select invoice",[i["id"] for i in approvable],key="p2p_fin_sel")
            if st.button("✅ Approve for payment",key="p2p_fin_apr",type="primary"):
                all_i = json.loads((DATA/"invoices.json").read_text())
                for i in all_i:
                    if i["id"]==sel_inv: i["status"]="Approved for Payment"; i["finance_approved"]=True
                (DATA/"invoices.json").write_text(json.dumps(all_i,indent=2))
                audit_log("INVOICE_APPROVED",uname,sel_inv)
                st.cache_data.clear(); st.success("✅ Approved for payment"); st.rerun()
        else:
            st.info("No invoices awaiting finance approval (requires 3-way match ✅)")

# ── TAB 3: Payment Queue ──────────────────────────────────────────
with tabs[3]:
    st.markdown("**Invoices approved for payment — payment queue:**")
    total_queue = sum(i["amount_kes"] for i in pending_pay)
    st.metric("Total in queue", f"KES {total_queue:,.0f}")
    if pending_pay:
        q_rows = [{"ID":i["id"],"Vendor":i["vendor"][:20],"Amount (KES)":f"{i['amount_kes']:,.0f}",
                    "Due":i.get("due_date","")[:10],"Department":i["department"][:18]}
                   for i in sorted(pending_pay, key=lambda x: x.get("due_date",""))]
        st.dataframe(pd.DataFrame(q_rows), use_container_width=True, hide_index=True)
        if is_fin or is_admin:
            pay_sel = st.selectbox("Mark as paid",[i["id"] for i in pending_pay],key="p2p_pay_sel")
            pay_ref = st.text_input("Payment reference (EFT/RTGS/Cheque no.)",key="p2p_pay_ref")
            if st.button("💳 Record payment",key="p2p_pay_btn",type="primary"):
                if pay_ref.strip():
                    all_i = json.loads((DATA/"invoices.json").read_text())
                    for i in all_i:
                        if i["id"]==pay_sel:
                            i["status"]="Paid"; i["payment_date"]=str(today); i["payment_ref"]=pay_ref.strip()
                    (DATA/"invoices.json").write_text(json.dumps(all_i,indent=2))
                    audit_log("INVOICE_PAID",uname,f"{pay_sel}: {pay_ref}")
                    st.cache_data.clear(); st.success("✅ Payment recorded"); st.rerun()
                else: st.error("Payment reference required")
    else:
        st.success("✅ Payment queue is clear")

# ── TAB 4: Raise PR ────────────────────────────────────────────────
with tabs[4]:
    st.markdown("**Raise a new Purchase Request:**")
    from utils.core import get_org_config as _goc
    _depts = [d["name"] for d in _goc().get("departments",[]) if d.get("active",True)]
    CATEGORIES = ["IT Equipment","Office Supplies","Cleaning & Sanitation","Furniture & Fittings",
                   "Security Services","Utilities","Professional Services","Travel & Accommodation",
                   "Printing & Stationery","Vehicle Fleet","Maintenance & Repairs","Marketing Materials","Other"]
    r1,r2,r3 = st.columns(3)
    _title  = st.text_input("Title / Description *",key="p2p_ntitle")
    _cat    = r1.selectbox("Category",CATEGORIES,key="p2p_ncat")
    _dept_r = r2.selectbox("Requesting department",_depts,
                            index=_depts.index(dept) if dept in _depts else 0, key="p2p_ndept")
    _amt    = r3.number_input("Estimated amount (KES)",100.0,50_000_000.0,10_000.0,key="p2p_namt")
    _vendor = st.text_input("Preferred vendor (optional)",key="p2p_nvend")
    _urgent = st.checkbox("Mark as urgent",key="p2p_urg")
    _just   = st.text_area("Business justification *",height=70,key="p2p_njust")
    if st.button("📤 Submit PR",key="p2p_submit",type="primary"):
        if _title.strip() and _just.strip():
            all_p = json.loads((DATA/"purchase_requests.json").read_text())
            new_id = f"PR{len(all_p)+1:05d}"
            all_p.append({
                "id":new_id,"title":_title.strip(),"category":_cat,
                "requested_by":uname,"department":_dept_r,"amount_kes":_amt,
                "currency":"KES","vendor_preferred":_vendor.strip(),"justification":_just.strip(),
                "status":"Submitted","request_date":str(today),"approved_by":"","approval_date":"",
                "po_id":"","budget_line":_cat,"urgent":_urgent,"notes":""
            })
            (DATA/"purchase_requests.json").write_text(json.dumps(all_p,indent=2))
            audit_log("PR_RAISED",uname,f"{new_id}: {_title[:60]}")
            _bsc_trigger(uname, "K051")
            st.cache_data.clear(); st.success(f"✅ PR {new_id} submitted for approval"); st.rerun()
        else: st.error("Title and justification required")

# ── TAB 5: Analytics ──────────────────────────────────────────────
with tabs[5]:
    spend_by_cat = {}
    for p in prs:
        if p.get("status") in ("Approved",):
            spend_by_cat[p["category"]] = spend_by_cat.get(p["category"],0) + p["amount_kes"]
    st.markdown("**Approved spend by category (KES):**")
    if spend_by_cat:
        st.bar_chart(pd.DataFrame({"KES":spend_by_cat}))
    total_committed = sum(p["amount_kes"] for p in pos)
    total_invoiced  = sum(i["amount_kes"] for i in invs)
    total_paid      = sum(i["amount_kes"] for i in invs if i["status"]=="Paid")
    c1,c2,c3 = st.columns(3)
    c1.metric("Total PO Commitment",f"KES {total_committed/1e6:.1f}M")
    c2.metric("Total Invoiced",     f"KES {total_invoiced/1e6:.1f}M")
    c3.metric("Total Paid YTD",     f"KES {total_paid/1e6:.1f}M")
