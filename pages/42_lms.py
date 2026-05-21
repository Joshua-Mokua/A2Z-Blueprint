"""pages/42_lms.py — Learning Management System.
CBK mandatory training, CPD tracking, completion reports, compliance.
"""
import streamlit as st
# v10.470 — Phase 3 Recovery & Modernization: PostgreSQL backing declaration
# Per Joshua doctrine: every page is PG-ready via the utils.db abstraction layer.
try:
    from utils import db as _v470_pg_db  # noqa: F401 — psycopg-backed repository
except ImportError:
    _v470_pg_db = None  # graceful when utils.db not yet available

import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter, defaultdict
from pages._shared import load_shared_state
from pages._access import require_access

require_access("people_hr.learning_mgmt")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role = ud.get("role",""); name = ud.get("full_name","")
sc   = str(ud.get("staff_code",""))
is_admin = ud.get("is_admin",False)
is_hr    = any(x in role.lower() for x in ("human resource","hr","training","chief human"))

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🎓 Learning Management</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "CBK mandatory training · CPD hours · Completion tracking · Compliance</span></div>",
    unsafe_allow_html=True)

@st.cache_data(ttl=60)
def _load():
    c = json.loads((DATA/"lms_courses.json").read_text()) if (DATA/"lms_courses.json").exists() else []
    e = json.loads((DATA/"lms_enrollments.json").read_text()) if (DATA/"lms_enrollments.json").exists() else []
    return c, e

courses, enrollments = _load()

cbk_courses = [c for c in courses if c["cbk_mandatory"]]
completed   = [e for e in enrollments if e["status"]=="Completed"]
overdue     = [e for e in enrollments if e["status"]=="Overdue"]
cbk_done    = [e for e in completed   if e.get("cbk_mandatory")]

m1,m2,m3,m4 = st.columns(4)
m1.metric("Total Courses",      len(courses))
m2.metric("CBK Mandatory",      len(cbk_courses))
m3.metric("Completed (all)",    len(completed))
m4.metric("Overdue",            len(overdue), delta_color="normal" if not overdue else "inverse")

tabs = st.tabs(["📚 Course Catalogue","👤 My Training","📊 Compliance Report","⚠️ Overdue","🏆 Leaderboard","🤝 Peer Learning Cards","🎯 Skill Matching"])

with tabs[0]:
    st.markdown("**Course catalogue:**")
    c_rows=[{"ID":c["id"],"Title":c["title"][:40],"Category":c["category"],
              "CBK Mandatory":("✅" if c["cbk_mandatory"] else ""),
              "Duration (hrs)":c["duration_hours"],"Frequency":c["frequency"]}
             for c in sorted(courses,key=lambda x:(-x["cbk_mandatory"],x["title"]))]
    st.dataframe(pd.DataFrame(c_rows),use_container_width=True,hide_index=True)

with tabs[1]:
    my_enrollments = [e for e in enrollments if str(e.get("staff_code",""))==sc]
    if my_enrollments:
        st.markdown(f"**My training record ({len(my_enrollments)} courses):**")
        my_rows=[{"Course":e["course_title"][:35],"CBK Mandatory":("✅" if e.get("cbk_mandatory") else ""),
                   "Status":e["status"],"Completion":e.get("completion_date","")[:10],
                   "Score":e.get("score",""),"Due":e.get("due_date","")[:10]}
                  for e in sorted(my_enrollments,key=lambda x:(x["status"]=="Completed",x["course_title"]))]
        st.dataframe(pd.DataFrame(my_rows),use_container_width=True,hide_index=True)
        my_completed = sum(1 for e in my_enrollments if e["status"]=="Completed")
        my_cbk_done  = sum(1 for e in my_enrollments if e["status"]=="Completed" and e.get("cbk_mandatory"))
        my_cbk_total = sum(1 for e in my_enrollments if e.get("cbk_mandatory"))
        st.metric("CBK mandatory completion",f"{my_cbk_done}/{my_cbk_total}",
                   "✅ All done" if my_cbk_done==my_cbk_total and my_cbk_total>0 else "⚠️ Incomplete",
                   delta_color="normal" if my_cbk_done==my_cbk_total else "inverse")
    else:
        st.info("No training records found for your staff code.")

with tabs[2]:
    if is_hr or is_admin:
        st.markdown("**CBK mandatory training compliance by department:**")
        dept_cbk = defaultdict(lambda:{"total":0,"done":0})
        for e in enrollments:
            if e.get("cbk_mandatory"):
                dept_cbk[e["dept"]]["total"]+=1
                if e["status"]=="Completed": dept_cbk[e["dept"]]["done"]+=1
        comp_rows=[{"Department":d,"Enrolled":v["total"],"Completed":v["done"],
                     "Compliance%":round(v["done"]/max(v["total"],1)*100,1),
                     "Status":("✅" if v["done"]/max(v["total"],1)>=0.9 else "⚠️" if v["done"]/max(v["total"],1)>=0.7 else "🔴")}
                    for d,v in sorted(dept_cbk.items(),key=lambda x:-x[1]["done"]/max(x[1]["total"],1))]
        st.dataframe(pd.DataFrame(comp_rows),use_container_width=True,hide_index=True)
    else:
        st.info("Compliance report available to HR and Admin.")

with tabs[3]:
    if overdue:
        od_rows=[{"Staff":e["staff_name"][:25],"Dept":e["dept"][:20],
                   "Course":e["course_title"][:30],"CBK Mandatory":("✅" if e.get("cbk_mandatory") else ""),
                   "Due":e.get("due_date","")[:10]}
                  for e in sorted(overdue,key=lambda x:(not x.get("cbk_mandatory",False),x["staff_name"]))[:30]]
        st.dataframe(pd.DataFrame(od_rows),use_container_width=True,hide_index=True)
        st.caption(f"{len(overdue)} overdue enrollments — CBK mandatory courses should be prioritised")
    else:
        st.success("✅ No overdue training enrollments.")

with tabs[4]:
    staff_pts = Counter(e["staff_name"] for e in completed)
    top10 = staff_pts.most_common(10)
    if top10:
        st.markdown("**Top 10 learners by courses completed:**")
        lb_rows=[{"Rank":i+1,"Name":n[:28],"Courses Completed":cnt} for i,(n,cnt) in enumerate(top10)]
        st.dataframe(pd.DataFrame(lb_rows),use_container_width=True,hide_index=True)


# ════════════════════════════════════════════════════════════════════
# v10.438 — Wire Std #14 PeerLearningNetwork into LMS
# ════════════════════════════════════════════════════════════════════

with tabs[5]:
    st.markdown("**🤝 Peer Learning Cards — Best practice sharing across the bank**")
    st.caption(
        "Top performers' approaches surfaced as weekly learning cards. "
        "Driver: scripts/generate_learning_cards.py · Std #14 (PeerLearningNetwork)."
    )
    try:
        from utils.peer_learning import list_cards_for_staff, PeerLearningNetwork
    except Exception as exc:  # noqa: BLE001
        st.error(f"Peer learning engine unavailable: {exc}")
    else:
        # My cards
        if sc:
            my_cards = list_cards_for_staff(sc, limit=20)
            if my_cards:
                st.markdown(f"**My relevant cards ({len(my_cards)}):**")
                card_rows = [{
                    "KPI/Skill": c.get("kpi_id", c.get("skill", ""))[:30],
                    "Performer": c.get("performer_name", "")[:25],
                    "Insight": (c.get("insight", "") or "")[:80],
                    "Generated": (c.get("generated_at", "") or "")[:10],
                } for c in my_cards]
                st.dataframe(pd.DataFrame(card_rows),
                            use_container_width=True, hide_index=True)
            else:
                st.info("No peer learning cards relevant to you yet. "
                       "Cards generate weekly from top-5 performers per KPI.")

        # Admin: generate cards manually
        if is_hr or is_admin:
            st.divider()
            st.markdown("**Admin: Trigger card generation**")
            from datetime import datetime as _dt
            current_week = _dt.now().strftime("%Y-W%V")
            colA, colB = st.columns([3, 1])
            colA.write(f"Generate weekly learning cards for: **{current_week}**")
            if colB.button("Generate cards", key="lms_gen_cards"):
                try:
                    network = PeerLearningNetwork()
                    cards = network.generate_weekly_cards(week=current_week)
                    st.success(f"✓ Generated {len(cards)} learning cards.")
                except Exception as exc:  # noqa: BLE001
                    st.error(f"Generation failed: {exc}")

with tabs[6]:
    st.markdown("**🎯 Skill Matching — Find peers ahead on a skill**")
    st.caption(
        "Match yourself with peers who rank higher on a skill. Uses "
        "role_skill_matrix.json. Std #14 (PeerLearningNetwork)."
    )
    try:
        from utils.peer_learning import PeerLearningNetwork
        skill_options = [
            "Customer Service Excellence", "Digital Tools Proficiency",
            "Credit Analysis", "Sales Pipeline Management",
            "Risk Assessment", "Compliance Awareness",
            "Coaching & Mentoring", "Data Analysis",
            "Process Improvement", "Communication Skills",
        ]
        sel_skill = st.selectbox("Skill area", skill_options, key="lms_skill")
        sel_level = st.slider("Your current level (1-5)", 1, 5, 3, key="lms_level")
        if st.button("Find peers ahead", key="lms_match_btn"):
            try:
                network = PeerLearningNetwork()
                peers = network.match_for_skill(
                    skill=sel_skill, level=sel_level, top_n=10,
                )
                if peers:
                    st.markdown(f"**{len(peers)} peer(s) ahead of you on {sel_skill}:**")
                    peer_rows = [{
                        "Staff Code": p.get("staff_code", ""),
                        "Name": p.get("name", "")[:30],
                        "Role": p.get("role", "")[:30],
                        "Their level": p.get("level", ""),
                        "Department": p.get("department", "")[:20],
                    } for p in peers]
                    st.dataframe(pd.DataFrame(peer_rows),
                                use_container_width=True, hide_index=True)
                else:
                    st.info(f"No peers found ahead of level {sel_level} on {sel_skill}.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Match failed: {exc}")
    except Exception as exc:  # noqa: BLE001
        st.error(f"Peer learning engine unavailable: {exc}")
