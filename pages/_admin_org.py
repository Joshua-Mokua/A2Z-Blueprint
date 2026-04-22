"""pages/_admin_org.py — Admin: Organisation Management.
Departments, clusters, branches, units, roles, module assignments, thresholds, nav labels.
All changes write to org_config.json — zero code changes needed.
"""
import streamlit as st
import json
import re
from pathlib import Path
from utils.config import load_org_config, save_org_config
from utils.core   import audit_log

DATA = Path(__file__).parent.parent / "data"


def _nid(items, prefix):
    nums = [int(re.sub(r"\D","",str(i.get("id","0"))) or "0") for i in items]
    return f"{prefix}{max(nums,default=0)+1:04d}"


def render_dept_manager(tab, uname):
    with tab:
        org   = load_org_config()
        depts = org.get("departments", [])
        clusters = org.get("clusters", [])
        cluster_names = [c["name"] for c in clusters]
        import pandas as pd

        st.markdown("**Departments — add, edit, reorder, change cluster. Changes take effect immediately.**")

        d_rows = [{"#":d.get("order",99),"Icon":d.get("icon",""),
                   "Name":d["name"],"Cluster":d.get("cluster",""),
                   "Active":"✅" if d.get("active",True) else "❌"}
                  for d in sorted(depts, key=lambda x:x.get("order",99))]
        st.dataframe(pd.DataFrame(d_rows), use_container_width=True, hide_index=True)
        st.markdown("---")

        ec1, ec2 = st.columns(2)
        with ec1.expander("➕ Add department"):
            nd_name = st.text_input("Name", key="nd_nm")
            nd_clust= st.selectbox("Cluster", cluster_names, key="nd_cl")
            nd_icon = st.text_input("Icon (emoji)", value="🏢", key="nd_ic")
            nd_col  = st.color_picker("Colour", value="#185FA5", key="nd_co")
            if st.button("✅ Add", key="nd_add", type="primary"):
                if nd_name.strip():
                    nid = re.sub(r"[^a-z0-9]","_",nd_name.lower().strip())[:14]
                    if any(d["id"]==nid for d in depts):
                        st.error("Already exists.")
                    else:
                        org["departments"].append({"id":nid,"name":nd_name.strip(),
                            "cluster":nd_clust,"active":True,"color":nd_col,
                            "icon":nd_icon,"order":max((d.get("order",0) for d in depts),default=0)+1})
                        org.setdefault("dept_module_assignments",{})[nid] = ["perform"]
                        save_org_config(org); audit_log("DEPT_ADDED",uname,nd_name)
                        st.cache_data.clear(); st.success(f"✅ {nd_name} added."); st.rerun()
                else:
                    st.error("Name required.")

        with ec2.expander("✏️ Edit department"):
            dnames = [d["name"] for d in depts]
            esel   = st.selectbox("Select",dnames,key="ed_s")
            edept  = next((d for d in depts if d["name"]==esel),{})
            if edept:
                en2 = st.text_input("Name",  value=edept["name"],               key="ed_n2")
                ec2v= st.selectbox("Cluster",cluster_names,
                                    index=cluster_names.index(edept.get("cluster","Executive"))
                                    if edept.get("cluster","") in cluster_names else 0, key="ed_c2")
                ei2 = st.text_input("Icon",  value=edept.get("icon","🏢"),       key="ed_i2")
                eo2 = st.number_input("Order",value=int(edept.get("order",99)),  key="ed_o2")
                ea2 = st.checkbox("Active",  value=edept.get("active",True),     key="ed_a2")
                if st.button("💾 Save",key="ed_sv",type="primary"):
                    for d in org["departments"]:
                        if d["id"]==edept["id"]:
                            d.update({"name":en2.strip(),"cluster":ec2v,"icon":ei2,
                                      "order":int(eo2),"active":ea2})
                    save_org_config(org); audit_log("DEPT_EDITED",uname,en2)
                    st.cache_data.clear(); st.success("✅ Saved."); st.rerun()

        st.markdown("---")
        st.markdown("**Move a unit/team to a different department:**")
        st.caption("Updates all staff in that unit to the new department navigation without changing roles.")
        users_d = json.loads((DATA/"users.json").read_text())
        all_units= sorted(set(u.get("unit","") for u in users_d.values()
                              if u.get("unit","") not in ("","None",None)))
        mu1,mu2,mu3 = st.columns(3)
        mv_unit = mu1.selectbox("Unit to move",all_units,key="mv_u")
        mv_from = mu2.text_input("Current dept",
                                  value=next((u["department"] for u in users_d.values()
                                             if u.get("unit")==mv_unit),""),
                                  key="mv_f",disabled=True)
        mv_to   = mu3.selectbox("Move to", [d["name"] for d in depts], key="mv_t")
        mv_n    = sum(1 for u in users_d.values() if u.get("unit")==mv_unit)
        st.caption(f"Will update {mv_n} staff member(s).")
        if st.button(f"🔄 Move {mv_unit} → {mv_to}",key="mv_exec",type="primary"):
            for u in users_d.values():
                if u.get("unit")==mv_unit: u["department"]=mv_to
            (DATA/"users.json").write_text(json.dumps(users_d,indent=2))
            audit_log("UNIT_MOVED",uname,f"{mv_unit} → {mv_to} ({mv_n} staff)")
            st.cache_data.clear(); st.success(f"✅ {mv_n} staff moved."); st.rerun()


def render_branch_manager(tab, uname):
    with tab:
        org  = load_org_config()
        brs  = org.get("branches",[])
        depts= org.get("departments",[])
        import pandas as pd

        regions = sorted(set(b.get("region","Other") for b in brs))
        br_reg  = st.selectbox("Filter region",["All"]+regions,key="br_rg")
        vis     = [b for b in brs if br_reg=="All" or b.get("region")==br_reg]
        b_rows  = [{"Branch":b["name"],"Region":b.get("region",""),
                    "Code":b.get("branch_code",""),
                    "Active":"✅" if b.get("active",True) else "❌"}
                   for b in sorted(vis, key=lambda x:x["name"])]
        st.dataframe(pd.DataFrame(b_rows),use_container_width=True,hide_index=True)
        st.caption(f"{len(vis)} shown | {sum(1 for b in brs if b.get('active',True))} active total")

        st.markdown("---")
        bc1,bc2 = st.columns(2)
        with bc1.expander("➕ Add branch"):
            nb_nm = st.text_input("Branch name", key="nb_nm")
            nb_rg = st.selectbox("Region", regions+["Other"], key="nb_rg")
            nb_cd = st.text_input("Branch code", key="nb_cd")
            nb_dt = st.date_input("Opened date",  key="nb_dt")
            if st.button("✅ Add branch",key="nb_add",type="primary"):
                if nb_nm.strip():
                    org["branches"].append({"id":_nid(brs,"BRN"),"name":nb_nm.strip(),
                        "region":nb_rg,"branch_code":nb_cd.strip() or _nid(brs,"B"),
                        "active":True,"dept_id":"retail","opened_date":str(nb_dt),
                        "region_group":nb_rg})
                    save_org_config(org); audit_log("BRANCH_ADDED",uname,nb_nm)
                    st.cache_data.clear(); st.success(f"✅ {nb_nm} added."); st.rerun()
                else: st.error("Name required.")

        with bc2.expander("✏️ Edit / deactivate branch"):
            bnames = sorted(b["name"] for b in brs)
            ebsel  = st.selectbox("Select",bnames,key="eb_s")
            ebbr   = next((b for b in brs if b["name"]==ebsel),{})
            if ebbr:
                ebn2 = st.text_input("Name",  value=ebbr["name"],                key="eb_n2")
                ebr2 = st.selectbox("Region", regions+["Other"],
                                     index=regions.index(ebbr.get("region","Other"))
                                     if ebbr.get("region","Other") in regions else 0, key="eb_r2")
                ebc2 = st.text_input("Code",  value=ebbr.get("branch_code",""),  key="eb_c2")
                eba2 = st.checkbox("Active",  value=ebbr.get("active",True),      key="eb_a2")
                if st.button("💾 Save",key="eb_sv",type="primary"):
                    for b in org["branches"]:
                        if b["id"]==ebbr["id"]:
                            b.update({"name":ebn2.strip(),"region":ebr2,
                                      "branch_code":ebc2.strip(),"active":eba2})
                    save_org_config(org); audit_log("BRANCH_EDITED",uname,ebn2)
                    st.cache_data.clear(); st.success("✅ Saved."); st.rerun()

        st.markdown("---")
        st.markdown("**Add a new HO unit (team/division):**")
        nu_nm = st.text_input("Unit name",  key="nu_nm",
                               placeholder="e.g. Management Reporting, Data Science")
        nu_dp = st.selectbox("Department", [d["name"] for d in depts if d.get("active",True)], key="nu_dp")
        if st.button("➕ Add unit",key="nu_add"):
            if nu_nm.strip():
                org.setdefault("ho_units",[]).append(
                    {"id":_nid(org.get("ho_units",[]),"HOU"),"name":nu_nm.strip(),
                     "dept_id":nu_dp,"active":True})
                save_org_config(org); audit_log("UNIT_ADDED",uname,nu_nm)
                st.cache_data.clear(); st.success(f"✅ {nu_nm} added."); st.rerun()
            else: st.error("Name required.")


def render_module_assignment(tab, uname):
    with tab:
        org   = load_org_config()
        depts = [d for d in org.get("departments",[]) if d.get("active",True)]
        mods  = org.get("modules",[])
        assign= org.get("dept_module_assignments",{})

        st.markdown("**Assign modules to departments. Tick = visible in that department navigation.**")
        st.caption("Universal modules (Home, Smart Alerts, Approvals, Customer 360) are always shown.")

        sel_nm  = st.selectbox("Department",[d["name"] for d in depts],key="ma_d")
        sel_dep = next((d for d in depts if d["name"]==sel_nm),{})
        sel_id  = sel_dep.get("id","")
        if not sel_id: return

        current = set(assign.get(sel_id,[]))
        univ    = {m["key"] for m in mods if m.get("universal")}
        non_u   = [m for m in sorted(mods,key=lambda x:x.get("name",""))
                   if not m.get("universal") and m.get("active",True)]

        CAT = {
            "📊 Performance & BSC":    ["perform","cascade","commission","nps","crosssell","branch_log","optimize","products","sla"],
            "💼 Sales & CRM":          ["pipeline","loan_applications","cims","campaigns","propositions","trade_finance","bancassurance_mgmt"],
            "📋 Credit & Risk":        ["credit_analysis","credit_admin","credit_monitoring","debt_recovery","ews","collateral","ifrs9","compliance","legal"],
            "💰 Finance & Treasury":   ["treasury","stress_testing","sbu","opex","revenue_assurance","rms","ra","budget"],
            "⚙️ Operations & IT":      ["ops","edms","cbs","incidents","digital_channels","contact_centre","agency_banking","cybersecurity","export"],
            "👥 People":               ["people","lms","pip"],
            "🔗 Executive":            ["integrate","competitor"],
        }

        new_assign = list(current)
        for cat_nm, keys in CAT.items():
            cat_m = [m for m in non_u if m["key"] in keys]
            if not cat_m: continue
            st.markdown(f"**{cat_nm}**")
            cols = st.columns(4)
            for j,m in enumerate(cat_m):
                chk = cols[j%4].checkbox(
                    f"{m['icon']} {m['name']}",
                    value=(m["key"] in current),
                    key=f"ma_{sel_id}_{m['key']}",
                    help=m.get("description",""))
                if chk and m["key"] not in new_assign: new_assign.append(m["key"])
                elif not chk and m["key"] in new_assign: new_assign.remove(m["key"])

        if st.button("💾 Save assignments",key="ma_sv",type="primary"):
            org["dept_module_assignments"][sel_id] = new_assign
            save_org_config(org)
            audit_log("MODULES_ASSIGNED",uname,f"{sel_nm}: {len(new_assign)} modules")
            st.cache_data.clear(); st.success(f"✅ {len(new_assign)} modules saved for {sel_nm}."); st.rerun()


def render_roles_manager(tab, uname):
    with tab:
        org   = load_org_config()
        roles = org.get("roles",[])
        dnames= [d["name"] for d in org.get("departments",[]) if d.get("active",True)]
        import pandas as pd

        st.markdown("**Role library — add, edit, assign grades and departments.**")
        rf = st.text_input("Filter",key="rl_f",placeholder="Search roles…")
        vis= [r for r in roles if rf.lower() in r["name"].lower()] if rf else roles[:60]
        st.dataframe(pd.DataFrame([{"Role":r["name"][:40],"Grade":r.get("grade","G3"),
            "Dept":r.get("dept_id",""),"Active":"✅" if r.get("active",True) else "❌"}
            for r in sorted(vis,key=lambda x:x["name"])]),
            use_container_width=True, hide_index=True)
        st.caption(f"{len(vis)} of {len(roles)} roles shown")

        rc1,rc2 = st.columns(2)
        with rc1.expander("➕ Add role"):
            rn = st.text_input("Role name",key="nr_n")
            rg = st.selectbox("Grade",["G1","G2","G3","G4","G5","G6","G7","G8"],
                               index=2, key="nr_g")
            rd = st.selectbox("Department", dnames, key="nr_d")
            rb = st.checkbox("Branch role", key="nr_b")
            if st.button("✅ Add",key="nr_add",type="primary"):
                if rn.strip():
                    if any(r["name"]==rn.strip() for r in roles):
                        st.error("Already exists.")
                    else:
                        org["roles"].append({"id":_nid(roles,"ROLE"),"name":rn.strip(),
                            "grade":rg,"dept_id":rd,"active":True,"is_branch_role":rb})
                        save_org_config(org); audit_log("ROLE_ADDED",uname,rn)
                        st.cache_data.clear(); st.success(f"✅ {rn} added."); st.rerun()
                else: st.error("Name required.")

        with rc2.expander("✏️ Edit role"):
            rsel  = st.selectbox("Select",sorted(r["name"] for r in roles),key="er_s")
            eroler= next((r for r in roles if r["name"]==rsel),{})
            if eroler:
                ern2= st.text_input("Name",value=eroler["name"],key="er_n2")
                erg2= st.selectbox("Grade",["G1","G2","G3","G4","G5","G6","G7","G8"],
                                    index=["G1","G2","G3","G4","G5","G6","G7","G8"].index(
                                           eroler.get("grade","G3")),key="er_g2")
                era2= st.checkbox("Active",value=eroler.get("active",True),key="er_a2")
                if st.button("💾 Save",key="er_sv",type="primary"):
                    for r in org["roles"]:
                        if r["id"]==eroler["id"]:
                            r.update({"name":ern2.strip(),"grade":erg2,"active":era2})
                    save_org_config(org); audit_log("ROLE_EDITED",uname,ern2)
                    st.cache_data.clear(); st.success("✅ Saved."); st.rerun()


def render_thresholds(tab, uname):
    with tab:
        org  = load_org_config()
        thr  = org.get("thresholds",{})
        st.markdown("**System-wide thresholds — all modules read from here.**")
        st.caption("Save applies immediately. No restart required.")

        GROUPS = {
            "📊 BSC & Performance":{
                "bsc_exceeds":("BSC Exceeds (≥)",0.5,5.0,0.1),
                "bsc_at_risk":("BSC At-Risk (<)",0.5,4.0,0.1),
                "pip_trigger_bsc":("PIP trigger BSC <",0.5,4.0,0.1),
            },
            "⭐ NPS":{
                "nps_good":("NPS Good (≥)",0,100,1),
                "nps_poor":("NPS Poor (<)",0,100,1),
            },
            "📋 Credit":{
                "ews_red_dpd":("EWS Red DPD >",1,180,1),
                "ews_amber_dpd":("EWS Amber DPD >",1,90,1),
                "collateral_ltv_alert":("LTV alert (%)",50,200,5),
                "collateral_valuation_warning_days":("Valuation warning (days)",7,90,1),
            },
            "💰 Finance":{
                "cir_target_pct":("CIR target (%)",30,80,1),
                "budget_achv_good":("Budget good (%)",80,120,1),
                "budget_achv_warn":("Budget warn (%)",60,100,1),
            },
            "💹 Treasury":{
                "fd_maturity_warning_days":("FD maturity alert (days)",1,30,1),
                "lc_expiry_warning_days":("LC expiry alert (days)",1,30,1),
            },
            "📞 Contact Centre":{
                "contact_centre_sla_pct":("SLA ≤30s target (%)",50,100,1),
                "contact_centre_fcr_pct":("FCR target (%)",40,100,1),
                "cc_csat_target":("CSAT target (1-5)",1.0,5.0,0.1),
                "cc_queue_alert_high":("Queue high alert",1,50,1),
            },
            "📱 Digital":{
                "digital_uptime_target":("Uptime target (%)",90,100,0.1),
                "app_crash_rate_target":("Crash rate target (%)",0,5,0.1),
                "ussd_completion_target":("USSD completion (%)",50,100,1),
                "atm_uptime_target":("ATM uptime target (%)",80,100,0.1),
            },
            "🔐 Cyber":{
                "patch_compliance_target":("Patch target (%)",70,100,1),
                "phishing_click_target":("Phishing click target (%)",1,20,1),
            },
            "🏪 Agency & BNC":{
                "agent_float_alert_pct":("Float alert (%)",50,150,5),
                "bnc_claims_ratio_target":("Claims ratio target (%)",20,120,5),
            },
            "📉 IRRBB (CBK Limits)":{
                "irrbb_ear_warning_pct":("EaR warning (%)",5,20,1),
                "irrbb_ear_limit_pct":  ("EaR CBK limit (%)",10,25,1),
                "irrbb_eve_warning_pct":("EVE warning (%)",5,20,1),
                "irrbb_eve_limit_pct":  ("EVE CBK limit (%)",10,25,1),
            },
            "🔍 AML Monitoring":{
                "aml_high_risk_score":   ("High-risk score threshold",50,100,5),
                "aml_str_threshold_m":   ("STR flag threshold (KES M)",0.5,50.0,0.5),
                "aml_cash_threshold_m":  ("Cash reporting threshold (KES M)",0.1,5.0,0.1),
            },
            "🛡️ Risk Register (RCSA)":{
                "rcsa_high_residual":          ("High residual score ≥",8,25,1),
                "rcsa_medium_residual":        ("Medium residual score ≥",3,12,1),
                "rcsa_review_frequency_days":  ("Review frequency (days)",30,180,10),
            },
            "💱 Transfer Pricing":{
                "ftp_spread_warning_pct":  ("NIM spread warning < (%)",0.1,2.0,0.1),
                "ftp_mortgage_floor_pct":  ("Mortgage FTP floor (%)",10.0,18.0,0.5),
            },
            "🗂️ Projects":{
                "project_budget_amber_pct":     ("Budget Amber trigger (%)",70,100,5),
                "project_completion_amber_pct": ("Completion Amber below (%)",40,90,5),
                "project_overdue_days_red":     ("Milestone overdue Red (days)",1,14,1),
            },
            "👥 Workforce":{
                "workforce_attrition_warn_pct": ("Attrition warning (%)",5,25,1),
                "workforce_succession_min":     ("Min succession depth",1,5,1),
            },
            "🤝 Deal Room":{
                "deal_room_cp_sla_days":  ("CP satisfaction SLA (days)",7,60,1),
                "deal_room_min_dscr":     ("Min DSCR covenant",1.0,2.5,0.1),
            },
        }
        changed = {}
        for gname, items in GROUPS.items():
            st.markdown(f"**{gname}**")
            cols = st.columns(3)
            for j,(key,(label,mn,mx,step)) in enumerate(items.items()):
                cur = float(thr.get(key,(float(mn)+float(mx))/2))
                nv  = cols[j%3].number_input(label,min_value=float(mn),max_value=float(mx),
                                               value=cur,step=float(step),key=f"thr_{key}")
                if abs(nv-cur)>0.001: changed[key]=nv

        if st.button("💾 Save thresholds",key="thr_sv",type="primary"):
            if changed:
                for k,v in changed.items(): org["thresholds"][k]=v
                save_org_config(org)
                audit_log("THRESHOLDS_UPDATED",uname,f"{len(changed)} changed")
                st.cache_data.clear(); st.success(f"✅ {len(changed)} threshold(s) saved."); st.rerun()
            else: st.info("No changes.")


def render_nav_labels(tab, uname):
    with tab:
        org   = load_org_config()
        mods  = org.get("modules",[])
        labels= org.get("nav_labels",{})
        st.markdown("**Rename sidebar navigation entries — no code required.**")
        st.caption("Leave blank to use the default label.")
        new_l = {}
        active_mods = sorted([m for m in mods if m.get("active",True)], key=lambda x:x["name"])
        cols = st.columns(2)
        for j,m in enumerate(active_mods):
            cur = labels.get(m["key"],"")
            nv  = cols[j%2].text_input(
                f"{m['icon']} {m['name']}",value=cur,
                placeholder=m["name"],key=f"nl_{m['key']}",
                label_visibility="visible")
            if nv.strip(): new_l[m["key"]]=nv.strip()

        if st.button("💾 Save labels",key="nl_sv",type="primary"):
            org["nav_labels"] = new_l
            save_org_config(org)
            audit_log("NAV_LABELS_SAVED",uname,f"{len(new_l)} custom labels")
            st.cache_data.clear(); st.success(f"✅ {len(new_l)} labels saved."); st.rerun()
