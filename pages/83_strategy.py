"""pages/83_strategy.py — Strategic Initiatives.
Strategy execution dashboard. Links strategy to projects to BSC.
Dept: Executive | KPIs: K101 K102 K103
"""
import streamlit as st
import pandas as pd
import json
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict
from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log
from utils.db import db as a2z_db

require_access("strategy_performance.strategic_initiatives")
DATA  = Path(__file__).parent.parent / "data"
today = date.today()
um, ud, uname, *_ = load_shared_state()[:12]
role     = str(ud.get("role","")).lower()
is_admin = ud.get("is_admin", False)
is_exec  = any(x in role for x in ("md","ceo","director","chief","head","strategy","manager"))

PILLARS = ["Customer Experience","Operational Excellence","Financial Performance",
           "People & Culture","Digital Transformation","Risk & Compliance"]

def _bsc_trigger(username, kpi=""):
    try:
        from utils.core import update_bsc_from_modules as _ubm
        _ubm(username)
    except Exception: pass

@st.cache_data(ttl=30)
def _load():
    return a2z_db.dual_load(DATA/"strategic_initiatives.json", table="strategic_initiatives")

def _save(data):
    # v10.343 — schema-lock gate: refuse a write that would break the
    # locked strategic_initiatives shape. Returns the validation result
    # so the caller can decide whether to surface an error toast.
    try:
        from utils.schema_validator import validate_before_save
        check = validate_before_save("strategic_initiatives.json", data)
        if not check.get("valid", True):
            st.error(
                "Save blocked by schema lock (v10.342). "
                f"First issue: {check.get('errors', ['?'])[0]}. "
                "Fix the data shape and retry."
            )
            return False
    except Exception:
        pass  # validator unavailable — fall through
    a2z_db.dual_save(DATA/"strategic_initiatives.json", data, table="strategic_initiatives", flat_cols=('id', 'name', 'pillar', 'sponsor', 'owner', 'owner_username', 'start_date', 'target_end_date', 'actual_end_date', 'completion_pct', 'status', 'rag_status', 'budget_kes_m', 'spent_kes_m', 'department'))
    st.cache_data.clear()
    return True


@st.cache_data(ttl=60)
def _cfg():
    mc = DATA/"module_config.json"
    return (a2z_db.load_json(mc, default={}) or {}).get("strategic_initiatives",{}) if mc.exists() else {}


records = _load()
cfg_c = _cfg()
conf_cfg = cfg_c.get("configurable",{})
amber_threshold = conf_cfg.get("amber_threshold_completion_pct",70)
red_threshold   = conf_cfg.get("red_threshold_completion_pct",40)

on_track  = [r for r in records if r.get("status") in ("On Track","Completed")]
at_risk   = [r for r in records if r.get("status")=="At Risk"]
behind    = [r for r in records if r.get("status")=="Behind"]
completed = [r for r in records if r.get("status")=="Completed"]
on_track_pct = round(len(on_track)/max(len(records),1)*100,1)
exec_score   = round(sum(r.get("completion_pct",0) for r in records)/max(len(records),1),1)

# ROI vs plan
roi_data = [(r.get("expected_roi_pct",0), r.get("actual_roi_pct",0)) for r in completed]
avg_expected = sum(e for e,_ in roi_data)/max(len(roi_data),1)
avg_actual   = sum(a for _,a in roi_data)/max(len(roi_data),1)
roi_pct = round((avg_actual/max(avg_expected,1))*100,1) if avg_expected else 100

st.markdown(
    "<div style='padding:16px 0 4px'>"
    "<span style='font-size:22px;font-weight:800'>🎯 Strategic Initiatives</span>"
    "<span style='font-size:13px;color:var(--color-text-secondary);margin-left:12px'>"
    "Executive · K101-K103</span></div>",
    unsafe_allow_html=True)

if behind: st.error(f"🔴 {len(behind)} initiative(s) BEHIND — escalate to ExCo")
if at_risk: st.warning(f"⚠️ {len(at_risk)} initiative(s) AT RISK")

m1,m2,m3,m4,m5 = st.columns(5)
m1.metric("Initiatives",     len(records))
m2.metric("On track",        len(on_track), delta_color="off" if on_track_pct>=70 else "inverse")
m3.metric("Completed",       len(completed))
m4.metric("Execution score", f"{exec_score}/100")
m5.metric("ROI vs plan",     f"{roi_pct}%")

tabs = st.tabs(["📊 Portfolio","📋 Initiatives","➕ New","📈 Pillars","⚙️ Config","📈 BSC","🤖 Arc Engines"])

with tabs[0]:
    rag_counts = {"Green":0,"Amber":0,"Red":0}
    for r in records: rag_counts[r.get("rag_status","Amber")] = rag_counts.get(r.get("rag_status","Amber"),0)+1
    c1,c2,c3 = st.columns(3)
    c1.metric("🟢 Green", rag_counts.get("Green",0))
    c2.metric("🟡 Amber", rag_counts.get("Amber",0))
    c3.metric("🔴 Red",   rag_counts.get("Red",0))
    st.bar_chart(pd.DataFrame({"Initiatives":rag_counts}))

with tabs[1]:
    f1,f2 = st.columns(2)
    fpil = f1.selectbox("Pillar",["All"]+PILLARS,key="st_fpil")
    frag = f2.selectbox("RAG",["All","Green","Amber","Red"],key="st_frag")
    vis = [r for r in records
           if (fpil=="All" or r.get("pillar","")==fpil)
           and (frag=="All" or r.get("rag_status","")==frag)]
    rows=[{"ID":r["id"],"Name":r.get("name","")[:25],"Pillar":r.get("pillar","")[:20],
            "Sponsor":r.get("sponsor","")[:15],"Status":r.get("status",""),
            "RAG":r.get("rag_status",""),"Progress":f"{r.get('completion_pct',0)}%",
            "Budget(M)":r.get("budget_kes_m",0),"Spent(M)":r.get("spent_kes_m",0),
            "Target":r.get("target_end_date","")[:10]} for r in vis]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[2]:
    if is_exec or is_admin:
        r1,r2 = st.columns(2)
        nm    = r1.text_input("Name *",key="st_n_nm")
        pil   = r2.selectbox("Pillar",PILLARS,key="st_n_pil")
        sp    = r1.selectbox("Sponsor",["MD","Director Retail","Director Commercial","Director Risk","Director IT","CFO","CRO"],key="st_n_sp")
        bud   = r2.number_input("Budget (KES M)",0.1,1000.0,10.0,key="st_n_bud")
        td    = r1.date_input("Target end date",today+timedelta(days=365),key="st_n_td")
        roi   = r2.number_input("Expected ROI %",0.0,200.0,30.0,key="st_n_roi")
        if st.button("💾 Create",key="st_n_save",type="primary"):
            if nm.strip():
                all_r = _load()
                all_r.append({"id":f"INIT{len(all_r)+1:04d}","name":nm,
                              "description":f"{pil} initiative","pillar":pil,
                              "sponsor":sp,"owner":uname,"owner_username":uname,
                              "start_date":str(today),"target_end_date":str(td),
                              "actual_end_date":"","completion_pct":0,
                              "status":"On Track","rag_status":"Green","budget_kes_m":bud,
                              "spent_kes_m":0,"expected_roi_pct":roi,"actual_roi_pct":0,
                              "linked_projects":0,"linked_kpis":[],"linked_bsc_kpis":[],
                              "key_milestones":0,"milestones_met":0,
                              "department":ud.get("department",""),
                              "stakeholders":1,"risks_identified":0,"risks_mitigated":0,
                              "last_updated":str(today),"next_review":str(today+timedelta(days=30)),
                              "executive_summary":"","notes":""})
                _save(all_r); audit_log("INITIATIVE_CREATED",uname,nm); _bsc_trigger(uname,"K101")
                st.success("✅ Initiative created"); st.rerun()

with tabs[3]:
    by_pillar = defaultdict(lambda:{"count":0,"avg_compl":0,"on_track":0})
    for r in records:
        p = r.get("pillar","Other")
        by_pillar[p]["count"] += 1
        by_pillar[p]["avg_compl"] += r.get("completion_pct",0)
        if r.get("status") in ("On Track","Completed"): by_pillar[p]["on_track"] += 1
    rows = [{"Pillar":p,"Count":v["count"],
              "Avg progress":f"{v['avg_compl']/max(v['count'],1):.0f}%",
              "On track":f"{v['on_track']}/{v['count']}"}
             for p,v in by_pillar.items()]
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

with tabs[4]:
    if is_admin:
        st.info("ℹ️ Hardcoded: RAG levels (Green/Amber/Red), 30-day review frequency")
        mc = json.loads((DATA/"module_config.json").read_text())
        cfg_m = mc.get("strategic_initiatives",{}).get("configurable",{})
        c1,c2 = st.columns(2)
        new_a = c1.number_input("Amber threshold (%)",30,90,int(cfg_m.get("amber_threshold_completion_pct",70)),key="st_c_a")
        new_r = c2.number_input("Red threshold (%)",10,60,int(cfg_m.get("red_threshold_completion_pct",40)),key="st_c_r")
        if st.button("💾 Save",key="st_cfg_save",type="primary"):
            cfg_m.update({"amber_threshold_completion_pct":new_a,"red_threshold_completion_pct":new_r})
            mc["strategic_initiatives"]["configurable"]=cfg_m; (DATA/"module_config.json").write_text(json.dumps(mc,indent=2))
            audit_log("STRATEGY_CFG_SAVED",uname,"Config updated"); st.cache_data.clear(); st.success("✅ Saved"); st.rerun()

with tabs[5]:
    bsc_rows=[
        {"KPI":"K101 — Initiatives On Track","Target":"> 80%","Actual":f"{on_track_pct}%","Status":"🟢" if on_track_pct>=80 else "🟡","Weight":"10%"},
        {"KPI":"K102 — Execution Score","Target":"> 70","Actual":f"{exec_score}","Status":"🟢" if exec_score>=70 else "🟡","Weight":"8%"},
        {"KPI":"K103 — Initiative ROI","Target":"> 100%","Actual":f"{roi_pct}%","Status":"🟢" if roi_pct>=100 else "🟡","Weight":"8%"},
    ]
    st.dataframe(pd.DataFrame(bsc_rows),use_container_width=True,hide_index=True)
    if st.button("🔄 Refresh BSC",key="st_bsc",type="primary"):
        _bsc_trigger(uname,"K101"); st.success("✅ BSC updated"); st.rerun()


# ──────────────────────────────────────────────────────────────────────
# Section 6: 🤖 Arc Engines (absorbed from 15_strategy_arc_cockpit.py
# in v10.203 per the architectural reorganization sub-campaign.
# 15 Strategy engines (ENH-141..155) presented as 7 nested sub-tabs
# spanning the strategy lifecycle: Formulation → Cascade → Health →
# Execution → Learning → STO → ROI. Read-only display except for
# state-mutating buttons that go through utils/api_strategy.py FastAPI
# endpoints. Mirrors the v10.202 Treasury Arc absorption pattern.
# ──────────────────────────────────────────────────────────────────────
with tabs[6]:
    try:
        from utils.strategy_formulation import StrategyFormulationEngine
        from utils.strategic_options import StrategicOptionsGenerator
        from utils.strategy_decomposition import StrategyDecompositionEngine
        from utils.initiative_portfolio import StrategicInitiativePortfolio
        from utils.enhanced_cascade import EnhancedCascadeEngine
        from utils.daily_strategy_integration import DailyStrategyIntegration
        from utils.gap_analyzer import StrategyGapAnalyzer
        from utils.corrective_actions import CorrectiveActionGenerator
        from utils.strategy_learning import StrategyLearningLoop
        from utils.stakeholder_engagement import StakeholderEngagementEngine
        from utils.strategy_health import StrategyHealthEngine
        from utils.strategy_simulator import StrategySimulator
        from utils.strategy_communication import StrategyCommunicationEngine
        from utils.sto_toolkit import STOToolkit
        from utils.strategy_roi import StrategyROIAnalytics
        _ARC_STRATEGY_AVAILABLE = True
    except ImportError as _ie:
        st.error(f"Strategy arc engines unavailable: {_ie}")
        _ARC_STRATEGY_AVAILABLE = False

    if _ARC_STRATEGY_AVAILABLE:
        st.caption(
            "v10.203 absorbed from 15_strategy_arc_cockpit.py — 15 engines "
            "(ENH-141..155) spanning the strategy lifecycle: Formulation, "
            "Cascade, Health, Execution, Learning, STO, ROI. All engines "
            "read-only here; state-mutating workflows go through the "
            "FastAPI POST endpoints in utils/api_strategy.py.")

        arc_tabs = st.tabs([
            "🎯 Formulation",
            "📊 Cascade",
            "📈 Health",
            "🔍 Execution",
            "🧠 Learning",
            "🏢 STO",
            "💰 ROI",
        ])

        with arc_tabs[0]:
            st.subheader("Strategy Formulation Flow")
            st.caption("ENH-141 SWOT → ENH-142 Options → ENH-143 Pillars → "
                        "ENH-144 Portfolio. Engines run synchronously with "
                        "deterministic rule-based logic; AI augmentation hooks "
                        "are opt-in (basis tag shows on each output).")

            # === ENH-141 SWOT ===
            with st.expander("🔍 ENH-141 — SWOT Engine", expanded=True):
                st.markdown(
                    "**Generate SWOT analysis from STEEP environmental signals.** "
                    "Inputs: macro context (text); engine produces "
                    "Strengths/Weaknesses/Opportunities/Threats with priority "
                    "scoring. AI augmentation is opt-in — without an AI hook, "
                    "the engine returns rule-based defaults transparently.")
                steep_input = st.text_area(
                    "STEEP context (Social/Tech/Economic/Environmental/Political signals)",
                    value="Rising digital banking adoption in Kenya; mobile "
                          "money penetration above 80%; competitive pressure "
                          "from neobanks; CBK regulatory tightening on credit "
                          "exposures; growth in trade finance corridors.",
                    height=80, key="form_steep")
                if st.button("Generate SWOT", key="form_swot_run"):
                    try:
                        result = StrategyFormulationEngine().generate_swot(
                            steep_input)
                        st.success(f"SWOT generated · basis={result.get('basis', 'rule_based')}")
                        col_s, col_w = st.columns(2)
                        with col_s:
                            st.markdown("**💪 Strengths**")
                            for s in result.get("strengths", [])[:5]:
                                st.markdown(f"- {s}")
                            st.markdown("**📈 Opportunities**")
                            for o in result.get("opportunities", [])[:5]:
                                st.markdown(f"- {o}")
                        with col_w:
                            st.markdown("**⚠️ Weaknesses**")
                            for w in result.get("weaknesses", [])[:5]:
                                st.markdown(f"- {w}")
                            st.markdown("**🚨 Threats**")
                            for t in result.get("threats", [])[:5]:
                                st.markdown(f"- {t}")
                        audit_log(uname, "swot_generated",
                                    f"steep_len={len(steep_input)}")
                    except Exception as e:
                        st.error(f"SWOT generation failed: {e}")

            # === ENH-142 Strategic Options ===
            with st.expander("🎲 ENH-142 — Strategic Options Generator"):
                st.markdown(
                    "**Score and rank strategic options.** Engine evaluates "
                    "candidate options across financial/strategic/risk axes "
                    "with documented weighting. No silent ML — same input "
                    "produces same ranking.")
                if st.button("Generate ranked options", key="form_opts_run"):
                    try:
                        generator = StrategicOptionsGenerator()
                        # Generate from default option universe
                        opts = generator.generate_options(
                            swot=None,
                            market_intel=None,
                            competitor_intel=None)
                        if isinstance(opts, list) and opts:
                            df = pd.DataFrame(opts)
                            st.dataframe(df, use_container_width=True,
                                         hide_index=True)
                        else:
                            st.info("Generator returned empty option set — "
                                     "AI hook not injected and no default "
                                     "universe configured.")
                        audit_log(uname, "options_ranked",
                                    f"n={len(opts) if isinstance(opts, list) else 0}")
                    except Exception as e:
                        st.error(f"Options generation failed: {e}")

            # === ENH-143 Pillars ===
            with st.expander("🏛️ ENH-143 — Strategic Decomposition (Pillars)"):
                pillar_intent = st.text_input(
                    "Strategic intent",
                    value="digital transformation operational excellence "
                          "sustainable growth",
                    key="form_pillar_intent")
                if st.button("Decompose into pillars", key="form_pillars_run"):
                    try:
                        pillars = StrategyDecompositionEngine(
                            ).define_strategic_pillars(pillar_intent)
                        st.success(f"Generated {len(pillars)} pillars")
                        for p in pillars:
                            st.markdown(
                                f"**{p['name']}** — {p.get('description', '')}")
                            if p.get("success_metrics"):
                                st.caption(f"Success metrics: "
                                           f"{', '.join(p['success_metrics'])}")
                        audit_log(uname, "pillars_defined",
                                    f"n={len(pillars)}")
                    except Exception as e:
                        st.error(f"Pillar decomposition failed: {e}")

            # === ENH-144 Initiative Portfolio ===
            with st.expander("📋 ENH-144 — Initiative Portfolio (Knapsack Optimised)"):
                st.markdown(
                    "**Reads existing strategic_initiatives.json seed.** Engine "
                    "computes knapsack-optimal portfolio under budget constraint "
                    "via DP. Read-only — initiatives are managed in "
                    "`83_strategy.py`.")
                budget_m = st.number_input(
                    "Budget cap (KES millions)",
                    min_value=10, max_value=10_000, value=250,
                    key="form_portfolio_budget")
                if st.button("Optimize portfolio", key="form_portfolio_run"):
                    try:
                        portfolio = StrategicInitiativePortfolio()
                        pillars = StrategyDecompositionEngine(
                            ).define_strategic_pillars("digital growth")
                        initiatives = portfolio.get_proposed_initiatives(pillars)
                        if not initiatives:
                            st.info("No initiatives in seed.")
                        else:
                            selected, deferred = portfolio.knapsack_optimize(
                                initiatives,
                                budget=budget_m * 1_000_000)
                            st.success(
                                f"Selected {len(selected)} of "
                                f"{len(initiatives)} initiatives within "
                                f"KES {budget_m}M budget · "
                                f"deferred {len(deferred)}.")
                            if selected:
                                df = pd.DataFrame([{
                                    "id": s.get("id"),
                                    "name": s.get("name"),
                                    "pillar": s.get("pillar"),
                                    "estimated_cost": s.get("estimated_cost"),
                                    "combined_score": s.get("combined_score"),
                                } for s in selected])
                                st.dataframe(df, use_container_width=True,
                                             hide_index=True)
                            audit_log(uname, "portfolio_optimized",
                                      f"selected={len(selected)} "
                                      f"deferred={len(deferred)} "
                                      f"budget_m={budget_m}")
                    except Exception as e:
                        st.error(f"Portfolio optimization failed: {e}")


        # ══════════════════════════════════════════════════════════════════════
        # Tab 2 — Cascade (ENH-145/153)
        # ══════════════════════════════════════════════════════════════════════

        with arc_tabs[1]:
            st.subheader("Strategy Cascade & Daily Integration")
            st.caption("ENH-145 cascades pillar OKRs through E/M/A bands. "
                        "ENH-153 surfaces personal daily strategy contribution "
                        "scorecards (the BSC engine link).")

            # === ENH-145 Enhanced Cascade ===
            with st.expander("🌳 ENH-145 — Enhanced Cascade Engine", expanded=True):
                st.markdown(
                    "**Band-weighted cascade**: pillar OKRs flow E1→E4 (full "
                    "weight), M1→M5 (75%), A1→A4 (50%). Per-band visibility "
                    "rules + skill-gap signals.")
                if st.button("Build cascade", key="cascade_build_run"):
                    try:
                        pillars = StrategyDecompositionEngine(
                            ).define_strategic_pillars("digital growth")
                        # Synthetic pillar OKRs for cascade demo
                        pillar_okrs = [
                            {"objective": f"Advance {p['name']}",
                             "key_results": [
                                 {"id": f"KR-{i}-{j}",
                                  "description": m,
                                  "target": 100, "actual": 60}
                                 for j, m in enumerate(p.get(
                                     "success_metrics", [])[:3])
                             ],
                             "pillar": p["name"]}
                            for i, p in enumerate(pillars)
                        ]
                        # Cascade for one department (demo)
                        dept = "Retail Banking"
                        cascade = EnhancedCascadeEngine().cascade_with_engagement(
                            pillar_okrs=pillar_okrs,
                            department=dept,
                            strategic_pillars=pillars)
                        st.success(
                            f"Cascade for '{dept}': "
                            f"{cascade.get('n_employees_reached', 0)} employees "
                            f"reached · {len(cascade.get('individual_okrs', []))} "
                            f"individual OKRs generated")
                        if cascade.get("coverage_by_band"):
                            st.markdown("**Coverage by band:**")
                            df = pd.DataFrame([
                                {"band": b, "n_employees": n}
                                for b, n in cascade["coverage_by_band"].items()])
                            st.dataframe(df, use_container_width=True,
                                         hide_index=True)
                        audit_log(uname, "cascade_built",
                                  f"dept={dept} "
                                  f"employees={cascade.get('n_employees_reached', 0)}")
                    except Exception as e:
                        st.error(f"Cascade build failed: {e}")

            # === ENH-153 Daily Strategy Integration ===
            with st.expander("📅 ENH-153 — Daily Strategy Integration ⭐",
                               expanded=True):
                st.markdown(
                    f"**Personal scorecard for {uname or 'you'}.** Connects "
                    "daily BSC scores to bank-wide strategic pillars via your "
                    "individual contribution mapping.")
                if st.button("Show my contribution",
                               key="daily_strategy_run"):
                    try:
                        if not uname:
                            st.warning("Login required to view personal scorecard.")
                        else:
                            scorecard = DailyStrategyIntegration(
                                ).create_personal_strategy_scorecard(uname)
                            st.success(
                                f"Bank health: "
                                f"{scorecard.get('bank_strategy_health', 'N/A')} "
                                f"· Your contribution score: "
                                f"{scorecard.get('contribution_score', 'N/A')}")
                            if scorecard.get("my_pillar_contributions"):
                                df = pd.DataFrame(
                                    scorecard["my_pillar_contributions"])
                                st.dataframe(df,
                                             use_container_width=True,
                                             hide_index=True)
                            audit_log(uname, "personal_scorecard_viewed",
                                      "")
                    except Exception as e:
                        st.error(f"Scorecard fetch failed: {e}")


        # ══════════════════════════════════════════════════════════════════════
        # Tab 3 — Health Dashboard (ENH-150)
        # ══════════════════════════════════════════════════════════════════════

        with arc_tabs[2]:
            st.subheader("Strategy Health Dashboard (ENH-150)")
            st.caption("Doc spec page: pages/150_strategy_dashboard.py · "
                        "Health score = 0.5×progress + 0.3×gap_inverse + "
                        "0.2×engagement, weights re-normalize when components "
                        "missing.")

            if st.button("Refresh dashboard", key="health_refresh"):
                st.cache_data.clear()

            try:
                pillars = StrategyDecompositionEngine().define_strategic_pillars(
                    "digital growth")
                # Use existing pulse if any
                pulse = StakeholderEngagementEngine().run_engagement_pulse()
                # Synthetic gap result (caller can override)
                perf = {p["name"]: {"_signals": {}} for p in pillars}
                gap_result = StrategyGapAnalyzer().analyze_gaps(pillars, perf)

                payload = StrategyHealthEngine().build_dashboard_payload(
                    pillars=pillars,
                    gap_result=gap_result,
                    engagement_pulse=pulse if pulse.get("score") else None)

                # Overall metrics
                h1, h2, h3, h4 = st.columns(4)
                score = payload.get("overall_score")
                level = payload.get("level")
                h1.metric("Health score",
                            f"{score}/100" if score is not None else "—",
                            delta=level)
                comps = payload.get("components", {})
                h2.metric("Progress",
                            f"{comps.get('progress', 0)}%"
                            if comps.get('progress') is not None else "—")
                h3.metric("Gap inverse",
                            f"{comps.get('gap_inverse', 0)}/100"
                            if comps.get('gap_inverse') is not None else "—")
                h4.metric("Engagement",
                            f"{comps.get('engagement', 0)}/100"
                            if comps.get('engagement') is not None else "—")

                st.caption(
                    f"Weights used: {payload.get('weights_used', {})} · "
                    f"Next review: {payload.get('next_review_date')}")

                # Per-pillar table
                st.markdown("### Per-pillar progress")
                per_p = payload.get("pillar_progress", [])
                if per_p:
                    df = pd.DataFrame([
                        {
                            "Pillar": p["pillar"],
                            "Progress (%)": p.get("progress"),
                            "Risk": p.get("risk_level"),
                            "Initiatives": p.get("n_initiatives"),
                            "On track": p.get("on_track"),
                            "Delayed": p.get("delayed"),
                            "Blocked": p.get("blocked"),
                            "Expected completion": p.get("expected_completion"),
                        } for p in per_p])
                    st.dataframe(df, use_container_width=True, hide_index=True)

                # Alerts
                alerts = payload.get("alerts", [])
                if alerts:
                    st.markdown("### ⚠️ Alerts")
                    for a in alerts:
                        fn = (st.error if a["severity"] == "HIGH"
                              else st.warning)
                        fn(f"[{a['severity']}] **{a['code']}**: {a['message']}")

                # Insights
                insights = payload.get("insights", [])
                if insights:
                    st.markdown("### 💡 Insights")
                    for ins in insights:
                        st.info(ins)

            except Exception as e:
                st.error(f"Dashboard render failed: {e}")


        # ══════════════════════════════════════════════════════════════════════
        # Tab 4 — Execution (ENH-146/147/151)
        # ══════════════════════════════════════════════════════════════════════

        with arc_tabs[3]:
            st.subheader("Strategy Execution Tools")
            st.caption("Gap analyzer detects underperformance vs targets. "
                        "Corrective actions generates implementation plans. "
                        "Simulator tests reallocations before commitment.")

            # === ENH-146 Gap Analyzer ===
            with st.expander("🔍 ENH-146 — Gap Analyzer", expanded=True):
                st.markdown(
                    "**Decision-tree root-cause classifier:** UNDER_RESOURCED → "
                    "PROCESS_BOTTLENECK → SKILL_GAP → AI_CLASSIFIED → "
                    "UNCLASSIFIED. HIGH severity at < 70%, MEDIUM 70-90%.")
                if st.button("Run gap analysis", key="exec_gap_run"):
                    try:
                        pillars = StrategyDecompositionEngine(
                            ).define_strategic_pillars("digital growth")
                        # Use synthetic perf signals representing real measurement
                        perf = {}
                        for p in pillars:
                            perf[p["name"]] = {
                                "_signals": {"resource_utilization": 1.30}
                            }
                        gap = StrategyGapAnalyzer().analyze_gaps(
                            pillars, perf)
                        st.success(
                            f"Gap analysis: {gap.get('n_high', 0)} HIGH, "
                            f"{gap.get('n_medium', 0)} MEDIUM gaps · "
                            f"total gap value {gap.get('total_gap_value', 0)}")
                        if gap.get("systemic_gaps"):
                            st.warning(
                                f"⚠️ {len(gap['systemic_gaps'])} systemic "
                                f"gap(s): {', '.join(s['category'] for s in gap['systemic_gaps'])}")
                        if gap.get("gaps"):
                            df = pd.DataFrame([
                                {
                                    "Pillar": g.get("pillar"),
                                    "Metric": g.get("metric"),
                                    "Severity": g.get("severity"),
                                    "Gap %": g.get("gap_percentage"),
                                    "Root cause": g.get("root_cause"),
                                } for g in gap["gaps"][:10]])
                            st.dataframe(df, use_container_width=True,
                                         hide_index=True)
                        audit_log(uname, "gap_analyzed",
                                  f"high={gap.get('n_high', 0)}")
                    except Exception as e:
                        st.error(f"Gap analysis failed: {e}")

            # === ENH-147 Corrective Actions ===
            with st.expander("🛠️ ENH-147 — Corrective Action Generator"):
                st.markdown(
                    "**Action templates:** RESOURCE_REALLOCATION (0.5× gap × "
                    "KES 6M/FTE), PROCESS_REDESIGN (0.7× gap × KES 5M), "
                    "TRAINING (0.3× gap × KES 2.5M). Prioritized by "
                    "impact-per-cost ratio.")
                if st.button("Generate corrective actions",
                               key="exec_actions_run"):
                    try:
                        pillars = StrategyDecompositionEngine(
                            ).define_strategic_pillars("digital growth")
                        perf = {p["name"]: {"_signals": {
                            "resource_utilization": 1.30}} for p in pillars}
                        gap = StrategyGapAnalyzer().analyze_gaps(pillars, perf)
                        ca_gen = CorrectiveActionGenerator()
                        results = []
                        for g in (gap.get("gaps", []) or [])[:5]:
                            actions = ca_gen.generate_corrective_actions(g)
                            results.append({
                                "gap_id": actions.get("gap_id"),
                                "n_actions": len(actions.get(
                                    "recommended_actions", [])),
                                "combined_impact": actions.get("combined_impact"),
                                "total_cost_kes": actions.get("total_cost"),
                            })
                        if results:
                            st.dataframe(pd.DataFrame(results),
                                         use_container_width=True,
                                         hide_index=True)
                        else:
                            st.info("No gaps to address.")
                        audit_log(uname, "actions_generated",
                                  f"n={len(results)}")
                    except Exception as e:
                        st.error(f"Action generation failed: {e}")

            # === ENH-151 Simulator ===
            with st.expander("🔮 ENH-151 — Strategy Simulator (What-If)"):
                st.markdown(
                    "**Linear impact model:** 1 FTE (KES 6M) ≈ +5 progress / "
                    "-2 weeks. Saturation above 5 FTE. Estimation uncertainty "
                    "band ±15% (NOT statistical CI).")
                col_s1, col_s2, col_s3 = st.columns(3)
                from_p = col_s1.text_input("From pillar",
                                               value="Operational Excellence",
                                               key="sim_from")
                to_p = col_s2.text_input("To pillar",
                                             value="Digital & Data Transformation",
                                             key="sim_to")
                amt_m = col_s3.number_input("Amount (KES millions)",
                                               min_value=1, max_value=500,
                                               value=12, key="sim_amt")
                if st.button("Simulate reallocation", key="sim_run"):
                    try:
                        result = StrategySimulator(
                            ).simulate_resource_reallocation(
                                from_p, to_p, amt_m * 1_000_000)
                        rec = result.get("recommendation")
                        if rec == "Proceed":
                            st.success(f"✅ {rec} — {result.get('rationale', '')}")
                        elif rec == "Reconsider":
                            st.warning(f"⚠️ {rec} — {result.get('rationale', '')}")
                        else:
                            st.info(f"{rec} — {result.get('rationale', '')}")

                        col_l, col_r = st.columns(2)
                        fp = result.get("from_pillar", {})
                        tp = result.get("to_pillar", {})
                        col_l.markdown(f"**{fp.get('name')}**")
                        col_l.write(
                            f"Current progress: {fp.get('current_progress')}")
                        col_l.write(
                            f"Projected: {fp.get('projected_progress')}")
                        col_r.markdown(f"**{tp.get('name')}**")
                        col_r.write(
                            f"Current progress: {tp.get('current_progress')}")
                        col_r.write(
                            f"Projected: {tp.get('projected_progress')}")
                        st.caption(
                            f"Estimation uncertainty band ±"
                            f"{result.get('estimation_uncertainty_band', 0.15) * 100:.0f}%"
                            " · basis=rule_based linear model")
                        audit_log(uname, "simulation_run",
                                  f"from={from_p} to={to_p} amt_m={amt_m}")
                    except Exception as e:
                        st.error(f"Simulation failed: {e}")


        # ══════════════════════════════════════════════════════════════════════
        # Tab 5 — Learning (ENH-148/149/152)
        # ══════════════════════════════════════════════════════════════════════

        with arc_tabs[4]:
            st.subheader("Learning, Engagement & Communication")
            st.caption("Capture what worked / didn't (148), measure pulse + "
                        "run campaigns (149), distribute strategy updates with "
                        "explicit prepared/sent/failed status (152).")

            # === ENH-148 Learning Loop ===
            with st.expander("🧠 ENH-148 — Strategy Learning Loop", expanded=True):
                st.markdown(
                    "**Classifies prior cycle initiatives** as successful "
                    "(completion ≥ 90, ROI ≥ 80% expected) or failed "
                    "(completion < 60 OR ROI < 50%). Common-factor extraction "
                    "over (department, type, sponsor, pillar) with min "
                    "frequency 2.")
                if st.button("Capture lessons", key="learn_lessons_run"):
                    try:
                        lessons = StrategyLearningLoop(
                            ).capture_lessons_learned("2026_pilot_cycle")
                        st.success(
                            f"Cycle '{lessons.get('strategy_cycle_id')}': "
                            f"{lessons.get('n_successful', 0)} successful, "
                            f"{lessons.get('n_failed', 0)} failed of "
                            f"{lessons.get('n_total', 0)} · stored="
                            f"{lessons.get('stored', False)}")
                        col_w, col_d = st.columns(2)
                        with col_w:
                            st.markdown("**✅ What worked**")
                            for ins in lessons["what_worked"][
                                    "key_insights"][:5]:
                                st.markdown(f"- {ins}")
                        with col_d:
                            st.markdown("**❌ What didn't**")
                            for lrn in lessons["what_didnt_work"][
                                    "key_learnings"][:5]:
                                st.markdown(f"- {lrn}")
                        st.markdown("**📋 Recommendations for next cycle**")
                        for rec in lessons.get(
                                "recommendations_for_next_cycle", [])[:5]:
                            badge = ("🔄" if rec["type"] == "discriminator"
                                     else "✓" if rec["type"] == "replicate"
                                     else "⚠️")
                            st.markdown(
                                f"{badge} **[{rec['type']}]** {rec['title']}")
                        audit_log(uname, "lessons_captured",
                                  f"successful={lessons.get('n_successful', 0)}")
                    except Exception as e:
                        st.error(f"Lessons capture failed: {e}")

            # === ENH-149 Stakeholder Engagement ===
            with st.expander("🗳️ ENH-149 — Engagement Pulse & Campaigns"):
                st.markdown(
                    "**4 canonical pulse questions** (per Continuation.docx "
                    "Standard #149) on 5-point Likert. Score formula: "
                    "((mean - 1) / 4) × 100. Levels HIGH≥75, MEDIUM≥50, LOW<50.")
                col_p1, col_p2 = st.columns(2)
                dept_filter = col_p1.text_input(
                    "Department filter (optional)", value="",
                    key="pulse_dept")
                period_filter = col_p2.text_input(
                    "Period filter (e.g. 2025-Q4, optional)", value="",
                    key="pulse_period")
                if st.button("Run pulse", key="pulse_run"):
                    try:
                        pulse = StakeholderEngagementEngine(
                            ).run_engagement_pulse(
                                department=dept_filter or None,
                                period=period_filter or None)
                        if pulse.get("score") is not None:
                            st.success(
                                f"Pulse score: {pulse['score']}/100 · "
                                f"level={pulse['level']} · "
                                f"n_responses={pulse['n_responses']}")
                        else:
                            st.info(
                                f"No data: {pulse.get('fallback_reason', '')}")
                        if pulse.get("by_question"):
                            st.markdown("**Per-question average (Likert 1-5):**")
                            for q, avg in pulse["by_question"].items():
                                if avg is not None:
                                    st.caption(f"  {q}: {avg}")
                        audit_log(uname, "pulse_run",
                                  f"score={pulse.get('score')}")
                    except Exception as e:
                        st.error(f"Pulse failed: {e}")

                st.divider()
                st.markdown("**Strategy contribution campaigns**")
                campaign_pillar = st.text_input(
                    "Pillar name", value="Digital & Data Transformation",
                    key="campaign_pillar")
                if st.button("Create campaign", key="campaign_run"):
                    try:
                        c = StakeholderEngagementEngine(
                            ).run_strategy_contribution_campaign(
                                {"name": campaign_pillar})
                        st.success(
                            f"Campaign '{c['campaign_id']}' created · "
                            f"rewards: best KES "
                            f"{c['rewards']['best_idea']:,}, feasible KES "
                            f"{c['rewards']['most_feasible']:,}, innovative "
                            f"KES {c['rewards']['most_innovative']:,}")
                        audit_log(uname, "campaign_created",
                                  f"pillar={campaign_pillar}")
                    except Exception as e:
                        st.error(f"Campaign creation failed: {e}")

            # === ENH-152 Strategy Communication ===
            with st.expander("📢 ENH-152 — Strategy Communication"):
                st.markdown(
                    "**Multi-channel strategy distribution.** Audience "
                    "segmentation by users.json band: E1-E4 → executive "
                    "(email), M1-M5 → manager (Slack), A1-A4 → staff "
                    "(app notification). **No adapters injected → "
                    "DELIVERY_PREPARED status (engine does NOT pretend "
                    "messages were sent).** Adapters configured at deployment.")
                col_u1, col_u2 = st.columns(2)
                upd_id = col_u1.text_input("Update ID",
                                               value="UPD-DEMO-001",
                                               key="comm_id")
                upd_title = col_u2.text_input("Title",
                                                  value="Q2 Strategy Progress",
                                                  key="comm_title")
                upd_summary = st.text_area(
                    "Summary text (used for all 3 tiers)",
                    value="Strategy execution checkpoint Q2.",
                    height=70, key="comm_summary")
                if st.button("Distribute (dry-run)", key="comm_run"):
                    try:
                        update_payload = {
                            "id": upd_id,
                            "title": upd_title,
                            "executive_summary": upd_summary,
                            "manager_summary": upd_summary,
                            "staff_summary": upd_summary,
                            "dashboard_link": "/strategy_dashboard",
                        }
                        result = StrategyCommunicationEngine(
                            ).distribute_strategy_update(update_payload)
                        st.success(
                            f"Audience segmentation: "
                            f"{result['audience_segments']['executive']} exec "
                            f"+ {result['audience_segments']['manager']} mgr + "
                            f"{result['audience_segments']['staff']} staff = "
                            f"{result['n_total_recipients']} total")
                        st.warning(
                            f"⚠️ DELIVERY_PREPARED: "
                            f"{result['n_prepared']} recipients (no adapter "
                            f"injected — engine does NOT pretend messages "
                            f"were sent)")
                        with st.expander("Per-tier delivery status"):
                            for tier, d in result["deliveries"].items():
                                st.markdown(
                                    f"**{tier}**: {d['delivery_status']} · "
                                    f"channel={d['channel']} · "
                                    f"recipients={d['n_recipients']}")
                                if d.get("fallback_reason"):
                                    st.caption(d["fallback_reason"])
                        audit_log(uname, "comm_distribution_simulated",
                                  f"id={upd_id} total={result['n_total_recipients']}")
                    except Exception as e:
                        st.error(f"Distribution failed: {e}")


        # ══════════════════════════════════════════════════════════════════════
        # Tab 6 — STO Toolkit (ENH-154)
        # ══════════════════════════════════════════════════════════════════════

        with arc_tabs[5]:
            st.subheader("Strategy Transformation Office Toolkit (ENH-154)")
            st.caption("Doc spec page: pages/151_sto_toolkit.py · "
                        "6 tabs · read-only contract with all engines.")

            sto_tabs = st.tabs([
                "📊 Portfolio", "⚠️ Risks", "📋 Reviews",
                "📈 Analytics", "📝 Minutes", "🎓 Academy",
            ])
            tk = STOToolkit()

            with sto_tabs[0]:
                try:
                    port = tk.get_portfolio()
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Total initiatives", port.get("n_initiatives", 0))
                    c2.metric("Completion rate",
                                f"{port.get('completion_rate', 0)}%")
                    c3.metric("Total budget",
                                f"KES {(port.get('total_budget_kes', 0) / 1e6):,.0f}M")
                    bc = port.get("budget_consumption_pct")
                    c4.metric("Budget consumed",
                                f"{bc}%" if bc is not None else "—")
                    rag = port.get("rag_distribution", {})
                    if rag:
                        st.markdown("### RAG distribution")
                        df = pd.DataFrame([
                            {"RAG": k, "Count": v}
                            for k, v in rag.items() if v > 0])
                        st.dataframe(df, use_container_width=True,
                                     hide_index=True)
                    if port.get("initiatives"):
                        with st.expander("Full initiative table"):
                            st.dataframe(
                                pd.DataFrame(port["initiatives"]),
                                use_container_width=True, hide_index=True)
                except Exception as e:
                    st.error(f"Portfolio fetch failed: {e}")

            with sto_tabs[1]:
                try:
                    risks = tk.get_strategy_risks()
                    if risks.get("fallback_reason"):
                        st.info(risks["fallback_reason"])
                    if risks.get("risks"):
                        bl = risks.get("by_level", {})
                        c1, c2, c3 = st.columns(3)
                        c1.metric("🔴 HIGH", bl.get("HIGH", 0))
                        c2.metric("🟡 MEDIUM", bl.get("MEDIUM", 0))
                        c3.metric("🟢 LOW", bl.get("LOW", 0))
                        for r in risks["risks"]:
                            icon = ("🔴" if r["level"] == "HIGH"
                                    else "🟡" if r["level"] == "MEDIUM"
                                    else "🟢")
                            with st.expander(
                                    f"{icon} **{r.get('name')}** "
                                    f"({r['level']})"):
                                st.markdown(f"**Mitigation:** "
                                            f"{r.get('mitigation', '')}")
                                st.caption(
                                    f"Owner: {r.get('owner', '')} · "
                                    f"Status: {r.get('status', '')} · "
                                    f"Review: {r.get('review_date', '')}")
                except Exception as e:
                    st.error(f"Risks fetch failed: {e}")

            with sto_tabs[2]:
                try:
                    revs = tk.get_upcoming_reviews()
                    if revs.get("fallback_reason"):
                        st.info(revs["fallback_reason"])
                    if revs.get("reviews"):
                        st.metric("Upcoming reviews", revs.get("n_upcoming", 0))
                        df = pd.DataFrame([
                            {
                                "Review ID": r.get("review_id"),
                                "Type": r.get("type"),
                                "Date": r.get("date"),
                                "Owner": r.get("owner"),
                                "Status": r.get("status"),
                            } for r in revs["reviews"]])
                        st.dataframe(df, use_container_width=True,
                                     hide_index=True)
                        if st.button("Generate review pack",
                                     key="sto_pack_run"):
                            pack = tk.generate_review_pack()
                            _render_summary(pack)
                            audit_log(uname, "review_pack_generated",
                                      f"pack_basis={pack.get('basis', '')}")
                except Exception as e:
                    st.error(f"Reviews fetch failed: {e}")

            with sto_tabs[3]:
                try:
                    ana = tk.get_strategy_analytics()
                    c1, c2, c3 = st.columns(3)
                    if ana.get("health"):
                        c1.metric("Health score",
                                    f"{ana['health'].get('overall_score', 0)}/100",
                                    delta=ana['health'].get('level'))
                    if ana.get("engagement"):
                        c2.metric("Engagement",
                                    f"{ana['engagement'].get('score', '—')}/100")
                    if ana.get("lessons"):
                        c3.metric("Lessons cycles",
                                    ana['lessons'].get('latest_cycle', '—'))
                    if ana.get("fallback_reasons"):
                        with st.expander("Fallback reasons"):
                            for r in ana["fallback_reasons"]:
                                st.caption(r)
                except Exception as e:
                    st.error(f"Analytics fetch failed: {e}")

            with sto_tabs[4]:
                try:
                    mins = tk.get_meeting_minutes()
                    if mins.get("fallback_reason"):
                        st.info(mins["fallback_reason"])
                    for m in mins.get("minutes", []):
                        with st.expander(
                                f"📝 **{m.get('minutes_id')}** — "
                                f"{m.get('date')} ({m.get('type')})"):
                            st.markdown("**Key decisions**")
                            for d in m.get("key_decisions", []):
                                st.markdown(f"- {d}")
                            st.markdown("**Action items**")
                            for a in m.get("action_items", []):
                                st.markdown(f"- {a}")
                            st.caption(f"Next review: "
                                       f"{m.get('next_review_date', '')}")
                except Exception as e:
                    st.error(f"Minutes fetch failed: {e}")

            with sto_tabs[5]:
                try:
                    train = tk.get_strategy_training()
                    if train.get("fallback_reason"):
                        st.info(train["fallback_reason"])
                    for s in train.get("sessions", []):
                        with st.expander(
                                f"🎓 **{s.get('name')}** — {s.get('date')}"):
                            st.markdown(s.get("description", ""))
                            st.caption(
                                f"Facilitator: {s.get('facilitator', '')} · "
                                f"Audience: {s.get('audience', '')} · "
                                f"Format: {s.get('format', '')} · "
                                f"Seats: {s.get('seats_left', '')}/"
                                f"{s.get('seats_total', '')}")
                except Exception as e:
                    st.error(f"Training fetch failed: {e}")


        # ══════════════════════════════════════════════════════════════════════
        # Tab 7 — ROI Analytics (ENH-155)
        # ══════════════════════════════════════════════════════════════════════

        with arc_tabs[6]:
            st.subheader("Strategy ROI & Impact Analytics (ENH-155)")
            st.caption("Direct (revenue + cost savings) + indirect (customer "
                        "LTV + employee productivity + risk reduction). All "
                        "monetization constants NAMED + bank-overridable. "
                        "Indirect benefits LABELED is_estimate=True with "
                        "±20% uncertainty band.")

            cycle_id = st.text_input("Strategy cycle ID",
                                         value="2026_pilot_cycle",
                                         key="roi_cycle")
            duration_m = st.number_input("Cycle duration (months)",
                                             min_value=1, max_value=60,
                                             value=12, key="roi_duration")
            if st.button("Calculate ROI", key="roi_run"):
                try:
                    result = StrategyROIAnalytics().calculate_strategy_roi(
                        cycle_id, cycle_duration_months=duration_m)

                    c1, c2, c3, c4 = st.columns(4)
                    tb = result.get("total_benefit_kes")
                    ic = result.get("implementation_cost_kes")
                    roi_pct = result.get("roi_percentage")
                    payback = result.get("payback_period_months")

                    c1.metric("Total benefit",
                                f"KES {tb / 1e6:,.0f}M" if tb is not None else "—")
                    c2.metric("Cost",
                                f"KES {ic / 1e6:,.0f}M" if ic is not None else "—")
                    c3.metric("ROI",
                                f"{roi_pct}%" if roi_pct is not None else "—",
                                delta_color=("normal" if (roi_pct or 0) >= 0
                                             else "inverse"))
                    c4.metric("Payback",
                                f"{payback} months" if payback is not None else "—")

                    st.markdown("### Direct vs Indirect breakdown")
                    d_b = result.get("direct_benefit_kes", 0)
                    i_b = result.get("indirect_benefit_kes", 0)
                    df_split = pd.DataFrame([
                        {"Component": "Direct", "Amount (KES M)": d_b / 1e6},
                        {"Component": "Indirect", "Amount (KES M)": i_b / 1e6},
                    ])
                    st.dataframe(df_split, use_container_width=True,
                                  hide_index=True)

                    st.markdown("### Category breakdown")
                    rows = []
                    for cat, data in result.get("breakdown", {}).items():
                        amt = data.get("amount_kes")
                        if amt is not None:
                            rows.append({
                                "Category": cat,
                                "Amount (KES M)": round(amt / 1e6, 2),
                                "Is estimate": data.get("is_estimate", False),
                                "Note": data.get("fallback_reason") or "",
                            })
                    if rows:
                        st.dataframe(pd.DataFrame(rows),
                                      use_container_width=True,
                                      hide_index=True)

                    st.caption(
                        f"Indirect uncertainty band: ±"
                        f"{result.get('uncertainty_band', 0.20) * 100:.0f}% · "
                        f"basis={result.get('basis', 'rule_based')}")

                    audit_log(uname, "roi_calculated",
                              f"cycle={cycle_id} roi_pct={roi_pct}")

                except Exception as e:
                    st.error(f"ROI calculation failed: {e}")


        # ══════════════════════════════════════════════════════════════════════
        # Footer
        # ══════════════════════════════════════════════════════════════════════

        st.caption(
            "Strategy Arc Cockpit v10.141 · 15/15 standards live · "
            "ENH-141 through ENH-155 · G145 closure gate locked · "
            "G146 UI integration ratchet · "
            "engines exposed via utils/api_strategy.py for React frontend.")


        # Footer audit log
        try:
            audit_log(
                action="strategy_arc_engines.view",
                username=ud.get("username", "anonymous"),
                detail=f"viewed_at={date.today().isoformat()}",
                module="strategic_initiatives")
        except Exception:
            pass
