"""pages/37_approvals.py — Pending Approvals (Maker-Checker).
Checker view: all high-value transactions awaiting dual approval.
CBK requirement for transactions above defined thresholds.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from datetime import date
from pages._shared import load_shared_state, safe_html
from pages._access import require_access
from utils.core_audit import audit_log

require_access("approvals")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()

um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)
sc   = str(ud.get("staff_code","") or "")

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>✅ Pending Approvals</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Maker-checker · Dual control · High-value transactions</span></div>",
    unsafe_allow_html=True)

st.markdown(
    "<div style='background:#EFF6FF;border:1px solid #BFDBFE;border-radius:8px;"
    "padding:8px 14px;font-size:12px;margin-bottom:10px'>"
    "CBK requires dual approval (maker-checker) for transactions above defined thresholds. "
    "This page shows all items submitted by makers awaiting checker review. "
    "Checker must be a different user than the maker and hold an appropriate role.</div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=10, show_spinner=False)
def _load_pending():
    p = DATA / "pending_approvals.json"
    return a2z_db.load_json(p) if p.exists() else []

def _save_pending(items):
    (DATA/"pending_approvals.json").write_text(json.dumps(items, indent=2))
    st.cache_data.clear()

pending = _load_pending()
open_items  = [i for i in pending if i.get("status")=="pending_checker"]
closed_items= [i for i in pending if i.get("status") in ("approved","rejected")]

c1,c2,c3,c4 = st.columns(4)
c1.metric("Pending",  len(open_items))
c2.metric("Approved", sum(1 for i in closed_items if i.get("status")=="approved"))
c3.metric("Rejected", sum(1 for i in closed_items if i.get("status")=="rejected"))
c4.metric("Total",    len(pending))

if open_items:
    st.warning(f"⏳ **{len(open_items)} item(s)** awaiting your review")

st.markdown("---")
tabs = st.tabs(["⏳ Pending Review","✅ Approved","❌ Rejected","📋 All History"])

def render_approval_items(items, show_actions=True):
    if not items:
        st.success("✅ Nothing here.")
        return
    for item in sorted(items, key=lambda x: x.get("submitted_at",""), reverse=True):
        amt = float(item.get("amount",0))
        op  = item.get("operation","")
        maker=item.get("maker_name","")
        aid = item.get("approval_id","")
        
        clr = {"pending_checker":"#D97706","approved":"#16A34A","rejected":"#DC2626"}.get(
               item.get("status",""), "#6B7280")
        
        with st.expander(
            f"{item.get('icon','📋')} {op.replace('_',' ').title()} · "
            f"KES {amt/1e6:.2f}M · {maker} · {aid}"):
            
            d1,d2,d3 = st.columns(3)
            d1.markdown(f"**Operation:** {op}")
            d1.markdown(f"**Amount:** KES {amt:,.0f}")
            d1.markdown(f"**Maker:** {safe_html(maker)}")
            d2.markdown(f"**Submitted:** {item.get('submitted_at','')[:10]}")
            d2.markdown(f"**Threshold:** KES {item.get('limit',0):,.0f}")
            d2.markdown(f"**Module:** {item.get('module','')}")
            d3.markdown(f"**Status:** {item.get('status','')}")
            if item.get("notes"):
                d3.markdown(f"**Notes:** {safe_html(item.get('notes',''))}")
            
            # Show detail
            if item.get("detail"):
                st.json(item["detail"])
            
            # Checker cannot be same as maker
            is_maker = str(item.get("maker_code","")) == sc
            
            if show_actions and item.get("status")=="pending_checker":
                if is_maker:
                    st.warning("⚠️ You cannot approve your own submission (maker-checker rule).")
                elif not (is_admin or any(x in role for x in ("Manager","Director","Chief","Head","Senior"))):
                    st.info("ℹ️ You need manager-level access to approve this item.")
                else:
                    checker_note = st.text_input("Checker note (optional)",
                                                  key=f"cn_{aid}", placeholder="Add any conditions or notes…")
                    col_a, col_r, _ = st.columns([1,1,2])
                    if col_a.button("✅ Approve", key=f"apr_{aid}", type="primary"):
                        all_p = _load_pending()
                        for it in all_p:
                            if it.get("approval_id")==aid:
                                it["status"]   = "approved"
                                it["checker"]  = name
                                it["checker_code"] = sc
                                it["approved_at"] = str(today)
                                it["checker_note"]= checker_note
                        _save_pending(all_p)
                        audit_log("DUAL_APPROVAL_APPROVED", uname, f"{op} {aid} KES {amt:,.0f}")
                        st.success(f"✅ Approved: {aid}")
                        st.rerun()
                    if col_r.button("❌ Reject", key=f"rej_{aid}"):
                        if not checker_note.strip():
                            st.error("A rejection reason is required.")
                        else:
                            all_p = _load_pending()
                            for it in all_p:
                                if it.get("approval_id")==aid:
                                    it["status"]  = "rejected"
                                    it["checker"] = name
                                    it["checker_code"] = sc
                                    it["rejected_at"]  = str(today)
                                    it["checker_note"] = checker_note
                            _save_pending(all_p)
                            audit_log("DUAL_APPROVAL_REJECTED", uname, f"{op} {aid} — {checker_note}")
                            st.success("Rejected.")
                            st.rerun()

with tabs[0]: render_approval_items(open_items, show_actions=True)
with tabs[1]: render_approval_items([i for i in closed_items if i["status"]=="approved"], False)
with tabs[2]: render_approval_items([i for i in closed_items if i["status"]=="rejected"], False)
with tabs[3]:
    if pending:
        rows = [{"ID":i.get("approval_id",""),"Operation":i.get("operation",""),
                  "Amount (M)":round(float(i.get("amount",0))/1e6,2),
                  "Maker":i.get("maker_name",""),"Checker":i.get("checker",""),
                  "Status":i.get("status",""),"Date":i.get("submitted_at","")[:10]}
                 for i in pending]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No approval history yet.")
