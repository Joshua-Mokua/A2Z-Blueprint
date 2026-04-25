"""pages/22_credit_analysis.py — Credit Analysis System with swim lanes."""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from pages._shared import load_shared_state, get_user_proposition
from pages._access import require_access
from utils.core import LoanApplicationManager, audit_log

require_access("credit_analysis")

DATA = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()
lam = LoanApplicationManager()

@st.cache_data(ttl=60, show_spinner=False)
def _load():
    f = DATA / "loan_applications.json"
    return json.loads(f.read_text()) if f.exists() else []

apps  = _load()
role  = ud.get("role",""); sc = str(ud.get("staff_code","") or "")
is_admin  = ud.get("is_admin",False)
is_credit = any(x in role for x in ("Credit","Risk","Chief Credit","Chief Risk"))
is_mgr    = any(x in role for x in ("Director","Chief","Head","Manager"))

# Credit team sees all in-flight; others see their own submitted
credit_apps = [a for a in apps
               if a["status"] in ("assigned","analysis","committee",
                                   "approved","declined","returned",
                                   "credit_admin","disbursed","submitted","completeness")]

# ── Proposition head filter ─────────────────────────────
_prop_tag_pg = get_user_proposition()
if _prop_tag_pg:
    credit_apps = [x for x in credit_apps if x.get("proposition_tag") == _prop_tag_pg]
    try:
        import json as _pfj; from pathlib import Path as _pfp
        _pc2 = _pfj.loads((_pfp(__file__).parent.parent / "data" / "proposition_config.json").read_text())
        _pn  = _pc2.get("propositions",{}).get(_prop_tag_pg,{}).get("name",_prop_tag_pg)
        _pi  = _pc2.get("propositions",{}).get(_prop_tag_pg,{}).get("icon","🎯")
        st.info(_pi + " **" + _pn + " view** — " + str(len(credit_apps)) + " tagged records")
    except Exception: pass

if not (is_admin or is_credit or is_mgr):
    credit_apps = [a for a in credit_apps if str(a.get("rm_code","")) == sc]

# ── Header ─────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>🏦 Credit Analysis</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Appraisal · Swim lane processing · Decisions · Committee</span></div>",
    unsafe_allow_html=True)

# ── Stage pipeline visual ──────────────────────────────────────────
STAGES = [
    ("Submitted",   "submitted","#6B7280"),
    ("Completeness","completeness","#D97706"),
    ("Assigned",    "assigned","#7C3AED"),
    ("Analysis",    "analysis","#0891B2"),
    ("Committee",   "committee","#6D28D9"),
    ("Decided",     "approved|declined|returned","#16A34A"),
]
stage_html = "<div style='display:flex;gap:4px;margin-bottom:18px;flex-wrap:wrap'>"
for label, key, color in STAGES:
    cnt = sum(1 for a in credit_apps
              if a["status"] in key.split("|"))
    stage_html += (
        f"<div style='background:{color}15;border:1px solid {color}40;"
        f"border-radius:20px;padding:6px 14px;font-size:12px;display:flex;gap:8px'>"
        f"<span style='color:{color};font-weight:700'>{cnt}</span>"
        f"<span style='color:var(--color-text-secondary)'>{label}</span></div>")
stage_html += "</div>"
st.markdown(stage_html, unsafe_allow_html=True)

tabs = st.tabs(["📥 Queue","🔍 Appraisal","🗳️ Decisions","📊 Analytics","⚙️ Assign"])

# ────────────────────────────────────────────────────────────────────
# TAB 1: QUEUE
# ────────────────────────────────────────────────────────────────────
with tabs[0]:
    LANE_COLOR = {"Express":"#16A34A","Standard":"#2563EB","Complex":"#7C3AED"}
    STATUS_LABEL = {
        "submitted":"Submitted","completeness":"Checking Docs","assigned":"Assigned",
        "analysis":"In Analysis","committee":"At Committee","approved":"Approved",
        "declined":"Declined","returned":"Returned","credit_admin":"Credit Admin","disbursed":"Disbursed",
    }
    queue = [a for a in credit_apps
             if a["status"] in ("submitted","completeness","assigned","analysis","committee")]

    lf1,lf2 = st.columns(2)
    filt_lane = lf1.selectbox("Lane",["All","Express","Standard","Complex"], key="ca_lane")
    filt_st   = lf2.selectbox("Status",["All"]+list(STATUS_LABEL.values()), key="ca_st")

    if filt_lane != "All":
        queue = [a for a in queue if a.get("swim_lane", "") == filt_lane]
    if filt_st != "All":
        rev   = {v:k for k,v in STATUS_LABEL.items()}
        queue = [a for a in queue if a["status"] == rev.get(filt_st,"")]

    st.markdown(f"**{len(queue)} applications in queue**")
    for app in sorted(queue, key=lambda x: x.get("tat_days",0), reverse=True):
        sla = app.get("sla_target_days",10); tat = app.get("tat_days",0)
        sla_icon = "🔴" if tat > sla else "🟡" if tat > sla*0.8 else "🟢"
        lc = LANE_COLOR.get(app["swim_lane"],"#6B7280")
        amt = app["amount"]
        amt_s = f"KES {amt/1e9:.2f}B" if amt>=1e9 else f"KES {amt/1e6:.1f}M"
        flag = "🚩 " if app.get("compliance_flag") else ""
        with st.expander(
            f"{sla_icon} {flag}{app['client_name']}  ·  "
            f"<span style='color:{lc}'>{app['swim_lane']}</span>  ·  "
            f"{amt_s}  ·  {STATUS_LABEL.get(app['status'],app['status'])}  ·  TAT {tat}d",
            expanded=False):
            c1,c2,c3,c4 = st.columns(4)
            c1.markdown(f"**ID:** `{app['id']}`")
            c2.markdown(f"**Product:** {app['product']}")
            c3.markdown(f"**RM:** {app['rm_name']}")
            c4.markdown(f"**Applied:** {app['application_date']}")
            if app.get("analyst"):
                st.markdown(f"**Assigned to:** {app['analyst']['name']}")
            if app.get("compliance_flag"):
                st.error(f"⚠️ Compliance flag: {app.get('compliance_type','')} — must be cleared before approval")
            # Quick action buttons (credit team only)
            if is_credit or is_admin:
                b1,b2,b3 = st.columns(3)
                if b1.button("✅ Approve", key=f"apr_{app['id']}", type="primary"):
                    lam.record_decision(app['id'], "approved", role)
                    audit_log("LMS_APPROVED", uname, f"{app['id']}|{app['client_name']}")
                    st.cache_data.clear(); st.success(f"Approved: {app['id']}"); st.rerun()
                if b2.button("↩️ Return for rework", key=f"ret_{app['id']}"):
                    lam.record_decision(app['id'], "returned", role)
                    audit_log("LMS_RETURNED", uname, f"{app['id']}|{app['client_name']}")
                    st.cache_data.clear(); st.warning(f"Returned: {app['id']}"); st.rerun()
                if b3.button("❌ Decline", key=f"dec_{app['id']}"):
                    lam.record_decision(app['id'], "declined", role)
                    audit_log("LMS_DECLINED", uname, f"{app['id']}|{app['client_name']}")
                    st.cache_data.clear(); st.error(f"Declined: {app['id']}"); st.rerun()

# ────────────────────────────────────────────────────────────────────
# TAB 2: APPRAISAL CHECKLIST
# ────────────────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown("**Structured appraisal checklist** — complete all sections before decision.")
    analysis_apps = [a for a in credit_apps if a["status"] in ("assigned","analysis")]
    if not analysis_apps:
        st.info("No applications currently in analysis stage.")
    else:
        sel = st.selectbox("Select application",
                           [f"{a['id']} — {a['client_name']} ({a['swim_lane']})"
                            for a in analysis_apps], key="appr_sel")
        if sel:
            app_id = sel.split(" — ")[0]
            app    = next((a for a in analysis_apps if a["id"]==app_id), None)
            if app:
                st.markdown(f"**{app['client_name']}** · {app['product']} · "
                            f"KES {app['amount']/1e6:.1f}M · {app['swim_lane']} lane")

                ar1, ar2, ar3 = st.columns(3)
                _risk_key = f"risk_rating_{app_id}"
                if _risk_key not in st.session_state:
                    st.session_state[_risk_key] = "B — Standard"
                _risk_rating = ar1.selectbox(
                    "Internal Risk Rating",
                    ["A — Low Risk","B — Standard","C — Watch List","D — Substandard","E — Loss"],
                    key=_risk_key)
                _crb_key = f"crb_{app_id}"
                _crb = ar2.selectbox(
                    "CRB Status",
                    ["Not Done","✅ Done — Clean","⚠️ Done — Adverse"],
                    key=_crb_key)
                ar3.markdown(f"**SLA target:** {app.get('sla_target_days',10)} days · "
                              f"**Elapsed:** {app.get('tat_days',0)} days")

                APPRAISAL_SECTIONS = {
                    "Financial Analysis": [
                        "Revenue trend (3 years)","Cash flow adequacy",
                        "Debt service coverage ratio","Profitability ratios",
                        "Balance sheet strength",
                    ],
                    "Business Assessment": [
                        "Industry/sector analysis","Management quality",
                        "Business model viability","Market position",
                        "Environmental & Social risks",
                    ],
                    "Security & Collateral": [
                        "Collateral valuation verified","Legal charge confirmed",
                        "Insurance coverage adequate","LTV ratio acceptable",
                        "Force sale value assessed",
                    ],
                    "Compliance & KYC": [
                        "KYC documentation complete","CRB check done",
                        "PEP/Sanctions screening done","Source of funds verified",
                        "AML risk rating assigned",
                    ],
                }
                if app["swim_lane"] == "Complex":
                    APPRAISAL_SECTIONS["Credit Committee Pack"] = [
                        "Executive summary prepared","Risk mitigants documented",
                        "Sensitivity analysis done","Recommendation stated",
                        "Committee voting recorded",
                    ]

                for section, items in APPRAISAL_SECTIONS.items():
                    st.markdown(f"**{section}**")
                    cols = st.columns(len(items))
                    for col, item in zip(cols, items):
                        col.checkbox(item, key=f"apr_{app_id}_{item[:10]}")

                st.markdown("---")
                a1,a2,a3 = st.columns(3)
                rec = a1.selectbox("Recommendation",
                                   ["Select","Approve","Decline","Return for rework"],
                                   key=f"rec_{app_id}")
                cond = a2.text_area("Conditions precedent", height=80, key=f"cond_{app_id}")
                comm = a3.text_area("Analyst comments",     height=80, key=f"comm_{app_id}")
                if st.button("💾 Save & submit decision", type="primary",
                             key=f"save_apr_{app_id}", disabled=(rec=="Select")):
                    verdict_map = {"Approve":"approved","Decline":"declined","Return for rework":"returned"}
                    lam.record_decision(app_id, verdict_map.get(rec, rec), role,
                                        conditions=[c.strip() for c in cond.split(",") if c.strip()],
                                        comments=comm)
                    audit_log("LMS_DECISION", uname,
                              f"{app_id}|{rec}|{app['client_name']}")
                    st.cache_data.clear()
                    st.success(f"✅ Decision recorded: {rec} for {app_id}")
                    st.rerun()

# ────────────────────────────────────────────────────────────────────
# TAB 3: DECISIONS
# ────────────────────────────────────────────────────────────────────
with tabs[2]:
    decided = [a for a in credit_apps
               if a["status"] in ("approved","declined","returned","credit_admin","disbursed")]
    if not decided:
        st.info("No decisions recorded yet.")
    else:
        rows = []
        for a in decided:
            dec = a.get("decision") or {}
            rows.append({
                "ID": a["id"], "Client": a["client_name"][:28],
                "Product": a["product"][:20], "Lane": a.get("swim_lane", ""),
                "Amount (KES M)": round(a["amount"]/1e6,1),
                "Verdict": dec.get("verdict","").upper(),
                "Authority": dec.get("authority",""),
                "Date": dec.get("date",""),
                "Reason": (dec.get("reason","")[:40] if dec.get("reason") else ""),
            })
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────
# TAB 4: ANALYTICS
# ────────────────────────────────────────────────────────────────────
with tabs[3]:
    decided = [a for a in credit_apps
               if a["status"] in ("approved","declined","returned","credit_admin","disbursed")]
    if decided:
        total_d  = len(decided)
        app_n    = sum(1 for a in decided if a["status"] in ("approved","credit_admin","disbursed"))
        dec_n    = sum(1 for a in decided if a["status"] == "declined")
        ret_n    = sum(1 for a in decided if a["status"] == "returned")
        avg_tat  = sum(a.get("tat_days",0) for a in decided) / total_d

        m1,m2,m3,m4 = st.columns(4)
        m1.metric("Approval Rate",  f"{app_n/total_d*100:.1f}%",  f"{app_n}/{total_d}")
        m2.metric("Decline Rate",   f"{dec_n/total_d*100:.1f}%",  f"{dec_n}/{total_d}")
        m3.metric("Rework Rate",    f"{ret_n/total_d*100:.1f}%",  f"{ret_n}/{total_d}")
        m4.metric("Avg TAT (days)", f"{avg_tat:.1f}")

        # By swim lane
        st.markdown("**Performance by swim lane:**")
        for lane in ["Express","Standard","Complex"]:
            lane_d = [a for a in decided if a.get("swim_lane", "")==lane]
            if not lane_d: continue
            ld_app = sum(1 for a in lane_d if a["status"] in ("approved","credit_admin","disbursed"))
            ld_dec = sum(1 for a in lane_d if a["status"]=="declined")
            ld_ret = sum(1 for a in lane_d if a["status"]=="returned")
            ld_tat = sum(a.get("tat_days",0) for a in lane_d) / len(lane_d)
            sla    = 3 if lane=="Express" else 10 if lane=="Standard" else 21
            sla_ok = sum(1 for a in lane_d if a.get("tat_days",0) <= sla)
            st.markdown(
                f"**{lane}** ({len(lane_d)}) — "
                f"Approved {ld_app/max(len(lane_d),1)*100:.0f}% · "
                f"Declined {ld_dec/max(len(lane_d),1)*100:.0f}% · "
                f"Reworked {ld_ret/max(len(lane_d),1)*100:.0f}% · "
                f"Avg TAT {ld_tat:.1f}d (SLA {sla}d) · "
                f"SLA Compliance {sla_ok/max(len(lane_d),1)*100:.0f}%")

        # Decline reasons breakdown
        from collections import Counter
        d_reasons = [a["decision"]["reason"] for a in decided
                     if a["status"]=="declined" and a.get("decision",{}).get("reason")]
        r_reasons = [a["decision"]["reason"] for a in decided
                     if a["status"]=="returned" and a.get("decision",{}).get("reason")]
        if d_reasons or r_reasons:
            dr1,dr2 = st.columns(2)
            if d_reasons:
                dr1.markdown("**Decline reasons:**")
                for reason, cnt in Counter(d_reasons).most_common(5):
                    dr1.markdown(f"• {reason}: **{cnt}**")
            if r_reasons:
                dr2.markdown("**Rework reasons:**")
                for reason, cnt in Counter(r_reasons).most_common(5):
                    dr2.markdown(f"• {reason}: **{cnt}**")

# ────────────────────────────────────────────────────────────────────
# TAB 5: ASSIGN (credit managers only)
# ────────────────────────────────────────────────────────────────────
with tabs[4]:
    if not (is_credit or is_admin or is_mgr):
        st.info("Assignment is managed by the credit team.")
    else:
        unassigned = [a for a in credit_apps
                      if a["status"] in ("submitted","completeness")
                      and a.get("completeness_score",0) >= 80
                      and not a.get("compliance_flag")]
        if not unassigned:
            st.success("✅ No unassigned complete applications.")
        else:
            st.markdown(f"**{len(unassigned)} applications ready to assign:**")
            analysts = [d.get("full_name","") for u,d in um.users.items()
                        if any(x in d.get("role","") for x in ("Credit Analyst","Credit Analysis"))]
            for app in unassigned:
                c1,c2,c3 = st.columns([3,2,1])
                c1.markdown(f"**{app['client_name']}** — {app['product']} — "
                            f"KES {app['amount']/1e6:.1f}M — {app['swim_lane']}")
                sel_analyst = c2.selectbox("Assign to", ["Select analyst"]+analysts,
                                           key=f"asgn_{app['id']}", label_visibility="collapsed")
                if c3.button("Assign", key=f"asgn_btn_{app['id']}",
                             disabled=(sel_analyst=="Select analyst")):
                    lam.submit_to_credit(app['id'], analyst_name=sel_analyst)
                    audit_log("LMS_ASSIGNED", uname, f"{app['id']}|{sel_analyst}")
                    st.cache_data.clear()
                    st.success(f"✅ {app['id']} assigned to {sel_analyst}")
                    st.rerun()

# ── AI Credit Memo tab ────────────────────────────────────────────
_last_tab_idx = len(re.findall(r"with tabs\[", code_snippet := """ """)) if False else None
with tabs[-1]:  # AI Credit Memo
    import requests as _req
    st.markdown("**AI Credit Memo Generator** — one-click draft from analysis data")
    st.caption("Based on the selected application's data, Claude generates a professional credit memo draft.")
    if "view_app" in st.session_state and st.session_state.get("view_app"):
        sel_a = st.session_state.get("view_app")
        if st.button("🤖 Generate credit memo draft", key="ca_memo_gen", type="primary"):
            with st.spinner("Drafting credit memo…"):
                try:
                    _app_data = json.dumps(sel_a, indent=2)[:3000]
                    _r = _req.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={"Content-Type":"application/json"},
                        json={
                            "model":"claude-sonnet-4-20250514",
                            "max_tokens":800,
                            "system":"You are a senior credit analyst at Ecobank Kenya. Draft a formal credit memorandum based on the loan application data provided. Use CBK standard credit memo format.",
                            "messages":[{"role":"user","content":f"Draft a credit memo for this application:\n{_app_data}"}]
                        }, timeout=30)
                    _r.raise_for_status()
                    memo_text = _r.json()["content"][0]["text"]
                    st.session_state["ca_memo_text"] = memo_text
                except Exception as _e:
                    st.error(f"Could not generate memo: {str(_e)[:80]}")
        if "ca_memo_text" in st.session_state:
            st.markdown("**Draft Credit Memo:**")
            st.markdown(st.session_state.get("ca_memo_text",""))
            st.download_button("📥 Download memo", data=st.session_state["ca_memo_text"].encode(),
                                file_name="credit_memo_draft.txt", key="ca_memo_dl")
    else:
        st.info("Select a loan application in the queue to generate its credit memo.")
