"""pages/57_deal_room.py — Deal Room and Term Sheet Engine."""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from utils.config import cfg
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core import audit_log

require_access("deal_room")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
is_admin = ud.get("is_admin", False)

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🤝 Deal Room</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Term sheet engine · Deal structuring · Conditions precedent · Covenants"
    "</span></div>", unsafe_allow_html=True)

@st.cache_data(ttl=30)
def _load():
    p = DATA / "deal_rooms.json"
    return json.loads(p.read_text()) if p.exists() else []

deals  = _load()
active = [d for d in deals if d.get("term_sheet_status") != "Signed"]
signed = [d for d in deals if d.get("term_sheet_status") == "Signed"]
total_val = sum(d.get("amount_m", 0) for d in deals)

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Deals", len(deals))
m2.metric("Active",      len(active))
m3.metric("Signed",      len(signed))
m4.metric("Total Value", f"KES {total_val/1000:.1f}B")

tabs = st.tabs(["📋 All Deals", "📄 Term Sheet", "✅ Checklist", "📊 Portfolio"])

with tabs[0]:
    f1, f2 = st.columns(2)
    ftype = f1.selectbox("Type",
                          ["All"] + sorted(set(d.get("deal_type","") for d in deals)),
                          key="dr_tp")
    fstat = f2.selectbox("TS Status",
                          ["All","Draft","Sent to client","Client comments received","Agreed","Signed"],
                          key="dr_st")
    vis = [d for d in deals
           if (ftype == "All" or d.get("deal_type") == ftype)
           and (fstat == "All" or d.get("term_sheet_status") == fstat)]
    rows = [{"ID": d["id"], "Deal": d["deal_name"][:25],
              "Type": d.get("deal_type","")[:18],
              "Amount (M)": d.get("amount_m",0),
              "Rate %": d.get("rate_pct",0),
              "Status": d.get("term_sheet_status","")[:20],
              "RM": d.get("rm","")[:18],
              "CPs": "✅" if d.get("checklist_complete") else "❌"}
             for d in sorted(vis, key=lambda x: -x.get("amount_m", 0))]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

with tabs[1]:
    deal_names = [d["deal_name"] for d in deals]
    sel_name   = st.selectbox("Select deal", deal_names, key="dr_sel")
    deal       = next((d for d in deals if d["deal_name"] == sel_name), {})
    if deal:
        c1, c2  = st.columns(2)
        ts_amt  = c1.number_input("Amount (KES M)", 0.0, 10000.0,
                                   float(deal.get("amount_m", 100)), key="dr_amt")
        ts_rate = c2.number_input("Rate (%)", 8.0, 30.0,
                                   float(deal.get("rate_pct", 14)), key="dr_rate")
        ts_ten  = c1.number_input("Tenor (months)", 1, 360,
                                   int(deal.get("tenor_months", 36)), key="dr_ten")
        ts_sec  = c2.text_input("Security", value=deal.get("security",""), key="dr_sec")
        cp_def  = chr(10).join(deal.get("conditions_precedent", []))
        cov_def = chr(10).join(deal.get("covenants", []))
        cp_text  = st.text_area("Conditions Precedent (one per line)",
                                 value=cp_def, height=80, key="dr_cp")
        cov_text = st.text_area("Covenants (one per line)",
                                 value=cov_def, height=80, key="dr_cov")
        ts_stat  = st.selectbox("Term Sheet Status",
                                 ["Draft","Sent to client","Client comments received","Agreed","Signed"],
                                 key="dr_ts_stat")
        arr_fee  = deal.get("fees", {}).get("arrangement_pct", 1.0)
        st.caption(f"Arrangement fee {arr_fee:.2f}% = KES {ts_amt * arr_fee / 100:.1f}M")
        if st.button("💾 Save term sheet", key="dr_save", type="primary"):
            all_d = json.loads((DATA / "deal_rooms.json").read_text())
            for d2 in all_d:
                if d2["deal_name"] == sel_name:
                    d2["amount_m"]             = ts_amt
                    d2["rate_pct"]             = ts_rate
                    d2["tenor_months"]         = int(ts_ten)
                    d2["security"]             = ts_sec
                    d2["term_sheet_status"]    = ts_stat
                    d2["last_updated"]         = str(today)
                    d2["conditions_precedent"] = [c.strip() for c in cp_text.splitlines() if c.strip()]
                    d2["covenants"]            = [c.strip() for c in cov_text.splitlines() if c.strip()]
            (DATA / "deal_rooms.json").write_text(json.dumps(all_d, indent=2))
            audit_log("TERM_SHEET_SAVED", uname, f"{sel_name}: KES {ts_amt}M @ {ts_rate}%")
            st.cache_data.clear()
            st.success("✅ Term sheet saved")
            st.rerun()

with tabs[2]:
    for d in sorted(active, key=lambda x: -x.get("amount_m", 0))[:8]:
        done  = d.get("checklist_complete", False)
        icon  = "✅" if done else "⚠️"
        label = f"{icon} {d['deal_name'][:35]} — KES {d.get('amount_m',0):.0f}M"
        with st.expander(label):
            st.markdown("**Conditions Precedent:**")
            for cp in d.get("conditions_precedent", []):
                st.markdown(f"  ☐ {cp}")
            st.markdown("**Covenants:**")
            for cov in d.get("covenants", []):
                st.markdown(f"  📋 {cov}")

with tabs[3]:
    by_type = {}
    for d in deals:
        t = d.get("deal_type", "Other")
        by_type[t] = by_type.get(t, 0) + d.get("amount_m", 0)
    st.bar_chart(pd.DataFrame({"KES M": by_type}))
