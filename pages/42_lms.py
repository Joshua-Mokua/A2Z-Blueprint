"""pages/42_lms.py — Learning Management System.
CBK mandatory training, CPD tracking, completion reports, compliance.
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date
from collections import Counter, defaultdict
from pages._shared import load_shared_state
from pages._access import require_access

require_access("lms")
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

tabs = st.tabs(["📚 Course Catalogue","👤 My Training","📊 Compliance Report","⚠️ Overdue","🏆 Leaderboard"])

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
