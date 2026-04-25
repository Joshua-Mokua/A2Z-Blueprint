"""pages/21_loan_applications.py — Loan Application & Completeness Engine."""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from pages._shared import load_shared_state, get_user_proposition
from pages._access import require_access
from utils.core import LoanApplicationManager, audit_log, requires_dual_approval, submit_for_approval

require_access("loan_applications")

DATA = Path(__file__).parent.parent / "data"
um, ud, uname, *_ = load_shared_state()

# ── Load data ──────────────────────────────────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _load():
    f = DATA / "loan_applications.json"
    return json.loads(f.read_text()) if f.exists() else []

apps = _load()
lam = LoanApplicationManager()
role = ud.get("role",""); sc = str(ud.get("staff_code","") or "")
is_admin   = ud.get("is_admin", False)
is_credit  = any(x in role for x in ("Credit","Risk","Admin"))
is_manager = any(x in role for x in ("Manager","Director","Chief","Head","Regional"))

# Scope: RM sees own; credit/managers see all
def _visible(apps):
    if is_admin or is_credit or is_manager: return apps
    return [a for a in apps if str(a.get("rm_code","")) == sc]

visible = _visible(apps)
_prop_tag_pg = get_user_proposition()
if _prop_tag_pg:
    visible = [x for x in visible if x.get("proposition_tag") == _prop_tag_pg]
    try:
        import json as _pfj; from pathlib import Path as _pfp
        _pc2 = _pfj.loads((_pfp(__file__).parent.parent/"data"/"proposition_config.json").read_text())
        _pn  = _pc2.get("propositions", {}).get(_prop_tag_pg,{}).get("name",_prop_tag_pg)
        _pi  = _pc2.get("propositions", {}).get(_prop_tag_pg,{}).get("icon","🎯")
        st.info(f"{_pi} **{_pn} view** — {len(visible)} tagged records")
    except Exception: pass


# ── Header ─────────────────────────────────────────────────────────
st.markdown(
    "<div style='padding:16px 0 8px'>"
    "<span style='font-size:22px;font-weight:800'>📋 Loan Applications</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Application journey · Completeness engine · Credit handoff</span></div>",
    unsafe_allow_html=True)

# ── KPI strip ──────────────────────────────────────────────────────
total   = len(visible)
pending = sum(1 for a in visible if a["status"] in ("submitted","completeness","assigned"))
in_anal = sum(1 for a in visible if a["status"] in ("analysis","committee"))
approved= sum(1 for a in visible if a["status"] in ("approved","credit_admin","disbursed"))
declined= sum(1 for a in visible if a["status"] == "declined")
vol     = sum(a["amount"] for a in visible) / 1e9

k1,k2,k3,k4,k5,k6 = st.columns(6)
for col, lbl, val, color in [
    (k1,"Total",     f"{total}",      "#1E40AF"),
    (k2,"Pending",   f"{pending}",    "#92400E"),
    (k3,"In Analysis",f"{in_anal}",   "#6D28D9"),
    (k4,"Approved",  f"{approved}",   "#166534"),
    (k5,"Declined",  f"{declined}",   "#991B1B"),
    (k6,"Volume",    f"KES {vol:.1f}B","#0369A1"),
]:
    col.markdown(
        f"<div style='background:var(--color-background-secondary);border:0.5px solid "
        f"var(--color-border-tertiary);border-radius:10px;padding:12px 14px;text-align:center'>"
        f"<div style='font-size:11px;color:var(--color-text-secondary);font-weight:600;"
        f"text-transform:uppercase;letter-spacing:0.5px'>{lbl}</div>"
        f"<div style='font-size:22px;font-weight:800;color:{color};margin-top:2px'>{val}</div>"
        f"</div>", unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ── Tabs ───────────────────────────────────────────────────────────
tab_labels = ["📥 All Applications","✅ Completeness Check","🏊 Swim Lanes","📤 Submit to Credit"]
if is_credit or is_admin:
    tab_labels.append("📊 Analytics")
# ── SLA breach banner ────────────────────────────────────────────
from datetime import date as _dt_la
_today_la = _dt_la.today()
_breached_la = [a for a in visible
                if a.get("status") not in ("approved","credit_admin","disbursed","declined","draft")
                and a.get("tat_days",0) > a.get("sla_target_days",10)]
_near_breach  = [a for a in visible
                 if a.get("status") not in ("approved","credit_admin","disbursed","declined","draft")
                 and a.get("sla_target_days",10) * 0.8 <= a.get("tat_days",0) <= a.get("sla_target_days",10)]
if _breached_la:
    st.error(f"🔴 **{len(_breached_la)} application(s)** have breached their SLA target — immediate attention required")
elif _near_breach:
    st.warning(f"⚠️ **{len(_near_breach)} application(s)** are approaching their SLA deadline")

tabs = st.tabs(tab_labels)

# ────────────────────────────────────────────────────────────────────
# TAB 1 — ALL APPLICATIONS
# ────────────────────────────────────────────────────────────────────
with tabs[0]:
    c1, c2, c3 = st.columns(3)
    status_opts = ["All statuses"] + sorted(set(a["status"] for a in visible))
    lane_opts   = ["All lanes","Express","Standard","Complex"]
    filt_status = c1.selectbox("Status",  status_opts, key="app_st")
    filt_lane   = c2.selectbox("Swim lane", lane_opts,  key="app_ln")
    filt_search = c3.text_input("Search client / RM", key="app_srch")

    filtered = visible
    if filt_status != "All statuses":
        filtered = [a for a in filtered if a["status"] == filt_status]
    if filt_lane != "All lanes":
        filtered = [a for a in filtered if a["swim_lane"] == filt_lane]
    if filt_search:
        q = filt_search.lower()
        filtered = [a for a in filtered
                    if q in a["client_name"].lower() or q in str(a["rm_name"]).lower()]

    STATUS_COLOR = {
        "draft":"#6B7280","submitted":"#2563EB","completeness":"#D97706",
        "assigned":"#7C3AED","analysis":"#0891B2","committee":"#6D28D9",
        "approved":"#16A34A","declined":"#DC2626","returned":"#EA580C",
        "credit_admin":"#0F766E","disbursed":"#166534",
    }
    LANE_COLOR = {"Express":"#16A34A","Standard":"#2563EB","Complex":"#7C3AED"}

    st.markdown(f"**{len(filtered)} applications**")
    for app in sorted(filtered, key=lambda x: x["application_date"], reverse=True)[:50]:
        sc_col = STATUS_COLOR.get(app["status"],"#6B7280")
        lc_col = LANE_COLOR.get(app["swim_lane"],"#6B7280")
        amt    = app["amount"]
        amt_s  = f"KES {amt/1e9:.2f}B" if amt>=1e9 else f"KES {amt/1e6:.1f}M"
        comp   = app.get("completeness_score",100)
        comp_c = "#16A34A" if comp==100 else "#D97706" if comp>=70 else "#DC2626"
        flag   = "🚩 " if app.get("compliance_flag") else ""

        with st.expander(
            f"{flag}{app['client_name']}  ·  {app['product']}  ·  {amt_s}  "
            f"|  {app['swim_lane']}  |  {app['status'].upper().replace('_',' ')}",
            expanded=False):

            cx1,cx2,cx3,cx4 = st.columns(4)
            cx1.markdown(f"**Application ID**  \n`{app['id']}`")
            cx2.markdown(f"**RM**  \n{app['rm_name']} · {app['rm_unit']}")
            cx3.markdown(f"**Applied**  \n{app['application_date']}")
            cx4.markdown(
                f"**Completeness**  \n"
                f"<span style='color:{comp_c};font-weight:700'>{comp}%</span>",
                unsafe_allow_html=True)

            if app.get("compliance_flag"):
                st.warning(f"⚠️ Compliance flag: **{app.get('compliance_type','Unknown')}** — refer to Compliance module")

            missing = [d for d in app.get("docs_required",[])
                       if d not in app.get("docs_submitted",[])]
            if missing:
                st.error(f"**Missing documents:** {', '.join(missing)}")

            # ── Business location map ─────────────────────────────────
            _loc = app.get("business_location", {})
            _lat = _loc.get("lat"); _lng = _loc.get("lng")
            _loc_name = _loc.get("name", "")
            if _lat and _lng:
                st.markdown(
                    f"📍 **Business location:** {_loc_name or f'{_lat:.4f}, {_lng:.4f}'}",
                    unsafe_allow_html=True)
                _map_html = f"""
<div style="border-radius:8px;overflow:hidden;border:1px solid #ddd;height:200px">
<iframe
  width="100%" height="200" frameborder="0" scrolling="no"
  style="border:0"
  src="https://www.openstreetmap.org/export/embed.html?bbox={_lng-0.01}%2C{_lat-0.008}%2C{_lng+0.01}%2C{_lat+0.008}&layer=mapnik&marker={_lat}%2C{_lng}"
  allowfullscreen>
</iframe>
</div>
<div style="font-size:10px;color:#888;margin-top:2px">
  📌 <a href="https://www.openstreetmap.org/?mlat={_lat}&mlon={_lng}#map=16/{_lat}/{_lng}"
     target="_blank" style="color:#2563EB">View on OpenStreetMap</a>
</div>"""
                st.markdown(_map_html, unsafe_allow_html=True)
            elif str(app.get("rm_code","")) == sc or is_credit or is_admin:
                with st.expander("📍 Pin business location", expanded=False):
                    st.caption("Enter coordinates to pin the business on a map. "
                                "You can find coordinates by right-clicking any location "
                                "on Google Maps or OpenStreetMap.")
                    _mc1, _mc2, _mc3 = st.columns(3)
                    _map_lat  = _mc1.number_input("Latitude",  value=-1.2921, step=0.0001,
                                                   format="%.4f", key=f"mlat_{app['id']}")
                    _map_lng  = _mc2.number_input("Longitude", value=36.8219, step=0.0001,
                                                   format="%.4f", key=f"mlng_{app['id']}")
                    _map_name = _mc3.text_input("Business name / area",
                                                 key=f"mname_{app['id']}",
                                                 placeholder="e.g. Westlands, Nairobi")
                    if st.button("📍 Save location", key=f"mpin_{app['id']}",
                                  type="primary"):
                        _apps_all2 = lam.apps
                        for _ai, _ap in enumerate(_apps_all2):
                            if _ap["id"] == app["id"]:
                                _apps_all2[_ai]["business_location"] = {
                                    "lat": _map_lat, "lng": _map_lng,
                                    "name": _map_name.strip()
                                }
                                break
                        lam.save()
                        audit_log("LMS_LOCATION_PINNED", uname,
                                  f"{app['id']}|{_map_lat},{_map_lng}")
                        st.cache_data.clear()
                        st.success(f"✅ Location saved")
                        st.rerun()

            if app.get("decision"):
                dec = app["decision"]
                verdict_color = "#16A34A" if dec["verdict"]=="approved" else "#DC2626" if dec["verdict"]=="declined" else "#EA580C"
                st.markdown(
                    f"**Decision:** <span style='color:{verdict_color};font-weight:700'>"
                    f"{dec['verdict'].upper()}</span>  ·  {dec.get('authority','')}  ·  {dec.get('date','')}",
                    unsafe_allow_html=True)
                if dec.get("reason"):
                    st.markdown(f"**Reason:** {dec['reason']}")

            # Credit memo
            if (is_credit or is_admin) and app.get("status") in ("analysis","committee","approved","credit_admin","disbursed"):
                if st.button(f"📄 Credit Memo", key=f"memo_{app['id']}", help="Generate printable credit appraisal memo"):
                    _memo_html = f"""
<html><head><style>
body{{font-family:Arial,sans-serif;font-size:12px;margin:24px}}
h2{{color:#004d2e;border-bottom:2px solid #004d2e;padding-bottom:4px}}
table{{width:100%;border-collapse:collapse;margin:10px 0}}
td,th{{border:1px solid #ddd;padding:6px 10px}}th{{background:#f5f5f5;font-weight:600}}
</style></head><body>
<h2>CREDIT APPRAISAL MEMORANDUM</h2>
<table>
<tr><th>Application ID</th><td>{app['id']}</td><th>Date</th><td>{app['application_date']}</td></tr>
<tr><th>Client</th><td>{app['client_name']}</td><th>CIF</th><td>{app.get('client_cif','')}</td></tr>
<tr><th>Product</th><td>{app['product']}</td><th>Amount</th><td>KES {app['amount']:,.0f}</td></tr>
<tr><th>Swim Lane</th><td>{app['swim_lane']}</td><th>RM</th><td>{app['rm_name']} — {app['rm_unit']}</td></tr>
<tr><th>Analyst</th><td>{app.get('analyst',{{}}).get('name','') if app.get('analyst') else 'Not assigned'}</td>
    <th>Decision</th><td>{(app.get('decision') or {{}}).get('verdict','Pending').upper()}</td></tr>
</table>
<h2>Conditions Precedent</h2>
<ul>{"".join(f"<li>{c}</li>" for c in (app.get('decision') or {{}}).get('conditions',[]))}</ul>
<p style='margin-top:32px;border-top:1px solid #ccc;padding-top:8px;font-size:10px'>
Generated by A2Z Blueprint · {_dt_la.today().isoformat()}</p>
</body></html>"""
                    st.download_button(
                        "📥 Download Credit Memo",
                        data=_memo_html.encode(),
                        file_name=f"CreditMemo_{app['id']}.html",
                        mime="text/html",
                        key=f"dl_memo_{app['id']}")

# ────────────────────────────────────────────────────────────────────
# TAB 2 — COMPLETENESS CHECK ENGINE
# ────────────────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown("**Application completeness engine** — only complete files proceed to credit analysis.")
    incomplete = [a for a in visible
                  if a["status"] in ("draft","submitted","completeness")
                  and a.get("completeness_score",100) < 100]

    if not incomplete:
        st.success("✅ All applications in your queue are complete.")
    else:
        st.warning(f"⚠️ **{len(incomplete)} applications** have incomplete documents")
        for app in sorted(incomplete, key=lambda x: x.get("completeness_score",0)):
            comp  = app.get("completeness_score",0)
            missing = [d for d in app.get("docs_required",[])
                       if d not in app.get("docs_submitted",[])]
            with st.expander(
                f"{'🔴' if comp<70 else '🟡'} {app['client_name']} — "
                f"{app['product']} — {comp}% complete — {len(missing)} docs missing"):
                st.markdown(f"**Application:** `{app['id']}` · **RM:** {app['rm_name']}")
                for doc in app.get("docs_required",[]):
                    submitted = doc in app.get("docs_submitted",[])
                    st.markdown(
                        f"{'✅' if submitted else '❌'} {doc}",
                        unsafe_allow_html=True)
                if str(app.get("rm_code","")) == sc or is_credit or is_admin:
                    if st.button(f"Mark complete & submit to credit — {app['id']}",
                                 key=f"submit_{app['id']}",
                                 disabled=len(missing) > 0):
                        st.info("Would submit to credit team (demo)")

# ────────────────────────────────────────────────────────────────────
# TAB 3 — SWIM LANES
# ────────────────────────────────────────────────────────────────────
with tabs[2]:
    st.markdown(
        "<div style='padding:8px 0 16px'>"
        "<b>Swim Lane Model</b> — applications routed by risk profile for efficient processing</div>",
        unsafe_allow_html=True)

    lanes = {
        "Express":  {"color":"#16A34A","bg":"#F0FDF4","icon":"⚡",
                     "desc":"Repeat borrowers · Clean history · ≤KES 5M · Auto-score · SLA 3 days"},
        "Standard": {"color":"#2563EB","bg":"#EFF6FF","icon":"📋",
                     "desc":"New borrowers · KES 5M–100M · Full appraisal · SLA 10 days"},
        "Complex":  {"color":"#7C3AED","bg":"#F5F3FF","icon":"🏛️",
                     "desc":"KES 100M+ · Corporate · Trade Finance · Committee required · SLA 21 days"},
    }
    lc1, lc2, lc3 = st.columns(3)
    for col, (lane, cfg) in zip([lc1,lc2,lc3], lanes.items()):
        lane_apps = [a for a in visible if a["swim_lane"] == lane]
        approved  = sum(1 for a in lane_apps if a["status"] in ("approved","credit_admin","disbursed"))
        declined  = sum(1 for a in lane_apps if a["status"] == "declined")
        in_flight = sum(1 for a in lane_apps if a["status"] in ("analysis","committee","assigned"))
        total_l   = len(lane_apps)
        app_rate  = round(approved/(approved+declined)*100) if (approved+declined) > 0 else 0
        avg_tat   = (sum(a.get("tat_days",0) for a in lane_apps) / total_l) if total_l else 0

        col.markdown(
            f"<div style='background:{cfg['bg']};border:1.5px solid {cfg['color']}20;"
            f"border-radius:12px;padding:18px'>"
            f"<div style='font-size:18px'>{cfg['icon']} <b style='color:{cfg['color']}'>{lane}</b></div>"
            f"<div style='font-size:11px;color:#6B7280;margin:6px 0 12px'>{cfg['desc']}</div>"
            f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'>"
            f"<div><div style='font-size:10px;color:#6B7280'>TOTAL</div>"
            f"<div style='font-size:20px;font-weight:800;color:{cfg['color']}'>{total_l}</div></div>"
            f"<div><div style='font-size:10px;color:#6B7280'>IN FLIGHT</div>"
            f"<div style='font-size:20px;font-weight:800'>{in_flight}</div></div>"
            f"<div><div style='font-size:10px;color:#6B7280'>APPROVAL RATE</div>"
            f"<div style='font-size:20px;font-weight:800;color:#16A34A'>{app_rate}%</div></div>"
            f"<div><div style='font-size:10px;color:#6B7280'>AVG TAT</div>"
            f"<div style='font-size:20px;font-weight:800'>{avg_tat:.0f}d</div></div>"
            f"</div></div>",
            unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown("**Applications in flight by lane:**")
    in_flight_apps = [a for a in visible
                      if a["status"] in ("submitted","completeness","assigned",
                                          "analysis","committee")]
    if in_flight_apps:
        rows = []
        for a in sorted(in_flight_apps, key=lambda x: x.get("tat_days",0), reverse=True):
            sla = a.get("sla_target_days",10)
            tat = a.get("tat_days",0)
            rows.append({
                "ID": a["id"], "Client": a["client_name"][:30],
                "Product": a["product"][:20], "Lane": a["swim_lane"],
                "Amount (KES M)": round(a["amount"]/1e6,1),
                "Status": a["status"].replace("_"," ").title(),
                "TAT (days)": tat,
                "SLA (days)": sla,
                "SLA Status": "🔴 Breached" if tat > sla else "🟡 At risk" if tat > sla*0.8 else "✅ On track",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ────────────────────────────────────────────────────────────────────
# (Bulk assign block — available in Analytics tab for credit managers)
# ────────────────────────────────────────────────────────────────────

# ────────────────────────────────────────────────────────────────────
# TAB 4 — SUBMIT TO CREDIT
# ────────────────────────────────────────────────────────────────────
with tabs[3]:
    st.markdown("**Submit complete applications to Credit Analysis.**")
    ready = [a for a in visible
             if a["status"] == "submitted"
             and a.get("completeness_score",0) == 100
             and not a.get("compliance_flag")]
    if not ready:
        st.info("No applications are ready for credit submission right now. "
                "All complete applications have either been submitted or are pending documents.")
    else:
        st.success(f"✅ **{len(ready)} applications** are complete and ready to send to credit")
        for app in ready:
            with st.expander(f"{app['client_name']} · {app['product']} · KES {app['amount']/1e6:.1f}M"):
                c1,c2 = st.columns(2)
                c1.markdown(f"**Swim Lane:** {app['swim_lane']}")
                c2.markdown(f"**RM:** {app['rm_name']}")
                if st.button(f"📤 Submit {app['id']} to Credit Analysis",
                             key=f"to_credit_{app['id']}",
                             type="primary"):
                    lam.submit_to_credit(app['id'])
                    audit_log("LMS_SUBMITTED_TO_CREDIT", uname, f"{app['id']}|{app['client_name']}")
                    st.cache_data.clear()
                    st.success(f"✅ {app['id']} submitted to Credit Analysis queue")
                    st.rerun()

# ────────────────────────────────────────────────────────────────────
# TAB 5 — ANALYTICS (credit/admin only)
# ────────────────────────────────────────────────────────────────────
if len(tabs) > 4:
    with tabs[4]:
        st.markdown("**Decision analytics** — approval rates, rework reasons, TAT by lane")

        # ── Bulk analyst assignment (credit managers only) ────────────
        if is_credit or is_admin:
            _unassigned_q = [a for a in visible
                             if a["status"] in ("submitted","completeness","assigned")
                             and not a.get("analyst")]
            if _unassigned_q:
                st.markdown(f"**🎯 Bulk analyst assignment — {len(_unassigned_q)} unassigned applications:**")
                _analysts_list = [d.get("full_name","") for u,d in um.users.items()
                                   if any(x in d.get("role","") for x in
                                          ("Credit Analyst","Credit Analysis"))]
                _ba1, _ba2 = st.columns([2,1])
                _sel_analyst_bulk = _ba1.selectbox(
                    "Assign all to analyst",
                    ["Select analyst"] + _analysts_list,
                    key="bulk_analyst_sel")
                # Workload indicator
                if _sel_analyst_bulk != "Select analyst":
                    _cur_load = sum(1 for a in apps if
                                    a.get("analyst",{}).get("name","") == _sel_analyst_bulk
                                    and a["status"] in ("assigned","analysis","committee"))
                    _ba1.caption(f"Current workload: {_cur_load} active applications")
                if _ba2.button(f"Assign {len(_unassigned_q)}",
                               key="bulk_assign_btn", type="primary",
                               disabled=(_sel_analyst_bulk == "Select analyst")):
                    _all_apps = lam.apps
                    _assigned_n = 0
                    for _ba_app in _all_apps:
                        if (_ba_app["status"] in ("submitted","completeness")
                                and not _ba_app.get("analyst")
                                and _ba_app.get("completeness_score",0) > 0):
                            _ba_app["analyst"] = {"code": "", "name": _sel_analyst_bulk}
                            _ba_app["status"]  = "assigned"
                            _assigned_n += 1
                    lam.save()
                    audit_log("LMS_BULK_ASSIGNED", uname,
                              f"{_assigned_n} apps → {_sel_analyst_bulk}")
                    st.cache_data.clear()
                    st.success(f"✅ {_assigned_n} applications assigned to {_sel_analyst_bulk}")
                    st.rerun()
                st.markdown("---")
        decided = [a for a in visible if a["status"] in ("approved","declined","returned",
                                                           "credit_admin","disbursed")]
        if decided:
            approved_n = sum(1 for a in decided if a["status"] in ("approved","credit_admin","disbursed"))
            declined_n = sum(1 for a in decided if a["status"] == "declined")
            returned_n = sum(1 for a in decided if a["status"] == "returned")
            total_d    = len(decided)
            an1,an2,an3,an4 = st.columns(4)
            an1.metric("Approval Rate",  f"{approved_n/total_d*100:.1f}%")
            an2.metric("Decline Rate",   f"{declined_n/total_d*100:.1f}%")
            an3.metric("Rework Rate",    f"{returned_n/total_d*100:.1f}%")
            an4.metric("Total Decided",  total_d)

            # Decline reasons
            dec_reasons = [a["decision"]["reason"] for a in decided
                           if a["status"]=="declined" and a.get("decision",{}).get("reason")]
            if dec_reasons:
                from collections import Counter
                reasons = Counter(dec_reasons).most_common(8)
                st.markdown("**Top decline reasons:**")
                for reason, cnt in reasons:
                    pct = cnt / len(dec_reasons) * 100
                    st.markdown(
                        f"<div style='display:flex;align-items:center;gap:10px;margin:4px 0'>"
                        f"<div style='width:160px;font-size:12px'>{reason}</div>"
                        f"<div style='flex:1;background:#F3F4F6;border-radius:4px;height:16px'>"
                        f"<div style='width:{pct:.0f}%;background:#DC2626;height:100%;border-radius:4px'></div>"
                        f"</div><div style='font-size:12px;width:40px;text-align:right'>{cnt}</div>"
                        f"</div>", unsafe_allow_html=True)

# ── Credit Team Capacity Dashboard ─────────────────────────────────
with tabs[-1]:
    import pandas as _pd_cap
    _apps_all_cap = json.loads((DATA/"loan_applications.json").read_text()) if (DATA/"loan_applications.json").exists() else []
    _pending_cap  = [a for a in _apps_all_cap if a["status"] in ("submitted","assigned","analysis","completeness")]
    _approved_cap = [a for a in _apps_all_cap if a["status"] in ("approved","credit_admin")]
    
    st.markdown("**End-of-month credit queue — analyst workload:**")
    _cc1,_cc2,_cc3,_cc4 = st.columns(4)
    _cc1.metric("Pending Decision",  len(_pending_cap))
    _cc2.metric("Approved ∕ Not Disbursed", len(_approved_cap))
    _cc3.metric("Express Queue",     sum(1 for a in _pending_cap if a.get("swim_lane")=="Express"))
    _cc4.metric("Complex Queue",     sum(1 for a in _pending_cap if a.get("swim_lane")=="Complex"))
    
    # SLA countdown
    _month_end = date.today().replace(day=1) + __import__("datetime").timedelta(days=32)
    _month_end = _month_end.replace(day=1) - __import__("datetime").timedelta(days=1)
    _days_left = (_month_end - date.today()).days
    if _days_left <= 5:
        st.error(f"🔴 **{_days_left} days to month end** — {len(_pending_cap)} apps pending. "
                 f"Target: clear queue before {_month_end.strftime('%d %b')}.")
    elif _days_left <= 10:
        st.warning(f"⚠️ {_days_left} days to month end — {len(_pending_cap)} apps in queue.")
    
    # By analyst
    _by_analyst = _pd_cap.DataFrame(
        [{"Analyst": a.get("analyst",{}).get("name","Unassigned") if isinstance(a.get("analyst"),dict) else (a.get("analyst") or "Unassigned"),
          "Apps":1,"Lane":a.get("swim_lane","Standard"),"Status":a["status"]}
         for a in _pending_cap]
    )
    if not _by_analyst.empty:
        _analyst_summary = _by_analyst.groupby("Analyst").agg(Apps=("Apps","sum")).reset_index()
        _analyst_summary = _analyst_summary.sort_values("Apps",ascending=False)
        st.markdown("**Queue by analyst:**")
        st.dataframe(_analyst_summary, use_container_width=True, hide_index=True)
    else:
        st.success("✅ No pending applications in queue.")
    
    # Disbursement alerts
    if _approved_cap:
        st.markdown("**Approved but not disbursed — need Operations action:**")
        _disb_rows = [{"ID":a["id"],"Client":a["client_name"][:25],"Product":a["product"][:25],
                        "Amount (M)":round(a.get("amount",0)/1e6,2),"RM":a.get("rm_name","")[:20],
                        "Approved":str(a.get("decision",{}).get("date",""))[:10] if isinstance(a.get("decision"),dict) else ""}
                       for a in sorted(_approved_cap,key=lambda x:x.get("amount",0),reverse=True)[:20]]
        st.dataframe(_pd_cap.DataFrame(_disb_rows), use_container_width=True, hide_index=True)
