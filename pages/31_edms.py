"""pages/31_edms.py — Electronic Document Management System (EDMS).
KYC documents, loan files, legal docs, board papers, policies, audit reports.
Upload, search, version control, expiry alerts, access management.
"""
import streamlit as st
from utils.db import db as a2z_db
import pandas as pd
import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import date, timedelta
from pages._shared import load_shared_state
from utils.core import audit_log
from pages._access import require_access

def _safe_date(s, fallback=None):
    """Safe date parsing — returns fallback on invalid/None input."""
    try:
        from datetime import date as _d
        return _d.fromisoformat(str(s)) if s else (fallback or _d.today())
    except Exception:
        from datetime import date as _d
        return fallback or _d.today()



require_access("edms")
DATA = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
sc = str(ud.get("staff_code","") or ""); role = ud.get("role",""); name = ud.get("full_name","")
is_admin = ud.get("is_admin",False)
is_mgr   = any(x in role for x in ("Manager","Director","Chief","Head","Legal","Compliance"))

@st.cache_data(ttl=60, show_spinner=False)
def _load_edms():
    p = DATA / "edms_documents.json"
    return a2z_db.load_json(p) if p.exists() else []

docs = _load_edms()

st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>📁 EDMS</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Electronic Document Management · KYC · Legal · Compliance · Board</span></div>",
    unsafe_allow_html=True)

# ── Summary KPIs ─────────────────────────────────────────────────────
active_d    = [d for d in docs if d["status"]=="Active"]
expired_d   = [d for d in docs if d["is_expired"]]
expiring_30 = [d for d in docs if not d["is_expired"]
               and (_safe_date(d["expiry_date"])-today).days <= 30]
needs_review= [d for d in docs if d.get("requires_review") and not d.get("review_date")]
total_mb    = sum(d["file_size_kb"] for d in docs)/1024

c1,c2,c3,c4,c5 = st.columns(5)
c1.metric("Total Documents",   f"{len(docs):,}")
c2.metric("Active",            f"{len(active_d):,}")
c3.metric("Expired",           f"{len(expired_d):,}")
c4.metric("Expiring in 30d",   f"{len(expiring_30):,}")
c5.metric("Pending Review",    f"{len(needs_review):,}")

if expired_d:
    st.error(f"🔴 {len(expired_d)} document(s) have expired — renew immediately")
if expiring_30:
    st.warning(f"⚠️ {len(expiring_30)} document(s) expire within 30 days")
if needs_review:
    st.info(f"ℹ️ {len(needs_review)} document(s) are due for review")

st.markdown("---")
tabs = st.tabs(["🔍 Search & Browse","📂 By Category","⚠️ Alerts","🔗 Linked Records","📤 Upload","⚙️ EDMS Config"])

# ── TAB 1: Search & Browse ───────────────────────────────────────────
with tabs[0]:
    s1,s2,s3,s4 = st.columns(4)
    srch    = s1.text_input("Search", placeholder="client, CIF, title, type…", key="edms_srch")
    sel_cat = s2.selectbox("Category", ["All"]+sorted(set(d["category"] for d in docs)), key="edms_cat")
    sel_acc = s3.selectbox("Access Level", ["All","Public","Internal","Confidential","Restricted","Top Secret"], key="edms_acc")
    sel_st  = s4.selectbox("Status", ["All","Active","Expired","Archived","Pending Review","Draft"], key="edms_st")

    visible = docs
    if srch:
        q = srch.lower()
        visible = [d for d in visible if
                   q in d.get("title","").lower() or q in d.get("client_name","").lower()
                   or q in d.get("client_cif","").lower() or q in d.get("document_type","").lower()
                   or q in d.get("tags",[]) ]
    if sel_cat != "All": visible = [d for d in visible if d["category"]==sel_cat]
    if sel_acc != "All": visible = [d for d in visible if d["access_level"]==sel_acc]
    if sel_st  != "All": visible = [d for d in visible if d["status"]==sel_st]

    st.markdown(f"**{len(visible)} documents**")
    rows = [{"ID":d["id"],"Title":d["title"][:40],"Category":d["category"],
              "Type":d["document_type"][:25],"Client":d.get("client_name","")[:25],
              "Branch":d.get("branch","")[:15],"Status":d["status"],
              "Access":d["access_level"],"Expires":d["expiry_date"][:10],
              "Version":d.get("version","v1.0"),"Size":f"{d.get('file_size_kb',0)}KB"}
             for d in sorted(visible, key=lambda x:x["uploaded_date"], reverse=True)[:100]]
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No documents match your search.")

# ── TAB 2: By Category ───────────────────────────────────────────────
with tabs[1]:
    st.markdown("**Document inventory by category:**")
    cat_stats = defaultdict(lambda:{"total":0,"active":0,"expired":0,"size_kb":0})
    for d in docs:
        c = d["category"]
        cat_stats[c]["total"]  += 1
        cat_stats[c]["size_kb"]+= d.get("file_size_kb",0)
        if d["status"]=="Active":  cat_stats[c]["active"]  += 1
        if d["is_expired"]:        cat_stats[c]["expired"] += 1
    df_cat = pd.DataFrame([{"Category":c,"Total":v["total"],"Active":v["active"],
                              "Expired":v["expired"],"Size (MB)":round(v["size_kb"]/1024,1)}
                             for c,v in sorted(cat_stats.items(),key=lambda x:-x[1]["total"])])
    st.dataframe(df_cat, use_container_width=True, hide_index=True)

    # Drill into category
    sel_drill = st.selectbox("Drill into category:", list(cat_stats.keys()), key="edms_drill")
    drill_docs = [d for d in docs if d["category"]==sel_drill]
    st.markdown(f"**{len(drill_docs)} {sel_drill} documents:**")
    drill_rows=[{"ID":d["id"],"Title":d["title"][:40],"Type":d["document_type"],
                  "Client":d.get("client_name","")[:25],"Status":d["status"],
                  "Expires":d["expiry_date"][:10]}
                 for d in sorted(drill_docs,key=lambda x:x["uploaded_date"],reverse=True)[:50]]
    if drill_rows: st.dataframe(pd.DataFrame(drill_rows),use_container_width=True,hide_index=True)

# ── TAB 3: Alerts ────────────────────────────────────────────────────
with tabs[2]:
    st.markdown("**Document alerts — action required:**")
    if expired_d:
        st.error(f"🔴 **EXPIRED ({len(expired_d)}):** These documents have passed their expiry date")
        exp_rows=[{"ID":d["id"],"Title":d["title"][:40],"Category":d["category"],
                    "Client":d.get("client_name","")[:25],"Expired":d["expiry_date"][:10]}
                   for d in sorted(expired_d,key=lambda x:x["expiry_date"])]
        st.dataframe(pd.DataFrame(exp_rows),use_container_width=True,hide_index=True)
    if expiring_30:
        st.warning(f"⚠️ **EXPIRING SOON ({len(expiring_30)}):**")
        exp30_rows=[{"ID":d["id"],"Title":d["title"][:40],"Category":d["category"],
                      "Client":d.get("client_name","")[:25],"Expires":d["expiry_date"][:10],
                      "Days Left":(_safe_date(d["expiry_date"])-today).days}
                     for d in sorted(expiring_30,key=lambda x:x["expiry_date"])]
        st.dataframe(pd.DataFrame(exp30_rows),use_container_width=True,hide_index=True)
    if needs_review:
        st.info(f"ℹ️ **PENDING REVIEW ({len(needs_review)}):**")
        rev_rows=[{"ID":d["id"],"Title":d["title"][:40],"Category":d["category"],
                    "Client":d.get("client_name","")[:25],"Uploaded":d["uploaded_date"][:10]}
                   for d in needs_review[:30]]
        st.dataframe(pd.DataFrame(rev_rows),use_container_width=True,hide_index=True)
    if not (expired_d or expiring_30 or needs_review):
        st.success("✅ No document alerts. All documents are current.")

# ── TAB 4: Linked Records ─────────────────────────────────────────────
with tabs[3]:
    st.markdown("**Documents linked to loan applications and legal matters:**")
    linked = [d for d in docs if d.get("linked_id")]
    if not linked:
        st.info("No linked documents yet.")
    else:
        lnk_rows=[{"ID":d["id"],"Title":d["title"][:35],"Linked To":d.get("linked_type",""),
                    "Record ID":d.get("linked_id",""),"Category":d["category"],
                    "Status":d["status"],"Access":d["access_level"]}
                   for d in linked[:50]]
        st.dataframe(pd.DataFrame(lnk_rows),use_container_width=True,hide_index=True)
        st.caption(f"{len(linked)} documents linked to existing records. Link more when uploading.")

# ── TAB 5: Upload ─────────────────────────────────────────────────────
with tabs[4]:
    st.markdown("**Register a new document:**")
    st.caption("In production this would handle actual file uploads. Here we register document metadata.")
    CATS=["KYC Documents","Loan File","Legal Documents","Board Papers","Policy Documents",
          "Credit Files","Security Documents","Compliance Records","HR Documents",
          "Audit Reports","Contract","Correspondence","Treasury Documents"]
    with st.form("edms_upload"):
        uc1,uc2 = st.columns(2)
        u_cat  = uc1.selectbox("Category",CATS,key="edms_ucat")
        u_type = uc2.text_input("Document type",placeholder="e.g. Title Deed",key="edms_utype")
        u_title= st.text_input("Document title *",key="edms_utitle")
        uc3,uc4= st.columns(2)
        u_client=uc3.text_input("Client name",key="edms_uclient")
        u_cif  = uc4.text_input("CIF number",key="edms_ucif")
        uc5,uc6= st.columns(2)
        from datetime import datetime
        u_expiry=(date.today()+timedelta(days=365)).isoformat()
        u_expiry=uc5.text_input("Expiry date (YYYY-MM-DD)",value=u_expiry,key="edms_uexp")
        u_access=uc6.selectbox("Access level",["Internal","Confidential","Public","Restricted","Top Secret"],key="edms_uacc")
        uc7,uc8= st.columns(2)
        u_link_type=uc7.selectbox("Link to",["None","loan_application","legal_matter"],key="edms_ultype")
        u_link_id  =uc8.text_input("Linked record ID",placeholder="e.g. LMS00001",key="edms_ulid")
        u_branch   = st.selectbox("Branch", sorted(set(d.get("branch","") for d in docs))[:30], key="edms_ubranch")
        if st.form_submit_button("📤 Register document",type="primary"):
            if not u_title.strip(): st.error("Title is required")
            else:
                all_docs=json.loads((DATA/"edms_documents.json").read_text())
                new_id=f"DOC{str(len(all_docs)+1).zfill(6)}"
                is_exp=False
                try: is_exp=_safe_date(u_expiry)<today
                except: pass
                all_docs.append({
                    "id":new_id,"category":u_cat,"document_type":u_type or u_cat,
                    "title":u_title.strip(),"client_name":u_client,"client_cif":u_cif,
                    "linked_type":u_link_type if u_link_type!="None" else "",
                    "linked_id":u_link_id if u_link_type!="None" else "",
                    "file_name":f"{new_id}_{u_type.replace(' ','_')}.pdf",
                    "file_size_kb":0,"pages":0,"uploaded_date":str(today),
                    "uploaded_by":name,"branch":u_branch,"access_level":u_access,
                    "status":"Active","expiry_date":u_expiry,"is_expired":is_exp,
                    "requires_review":False,"reviewed_by":"","review_date":"",
                    "tags":[],"version":"v1.0","notes":"","last_updated":str(today)})
                (DATA/"edms_documents.json").write_text(json.dumps(all_docs,indent=2))
                audit_log("EDMS_UPDATE", name, "Data saved")
                st.cache_data.clear(); st.success(f"✅ Document registered: {new_id}"); st.rerun()

# ── TAB 6: Config ────────────────────────────────────────────────────
with tabs[5]:
    if not (is_admin or is_mgr):
        st.info("EDMS configuration requires manager or admin access.")
    else:
        st.markdown("""
### EDMS Configuration Guide

**Configurable via Admin:**
- Document categories and types (add/rename)
- Access level definitions (who can see Restricted/Top Secret)
- Expiry alert thresholds (30d, 60d, 90d)
- Review frequency per document category
- Mandatory documents checklist per loan product
- Branch-level document quotas

**Hardcoded by design:**
- Document versioning scheme (v1.0, v2.0 etc)
- Audit trail of all uploads and access events
- Link structure to CBS records (loan_application, legal_matter)
- Expiry tracking calculation (uses uploaded_date + retention period)
        """)
