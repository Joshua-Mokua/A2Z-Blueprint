"""pages/94_credit_governance_cockpit.py — Credit Governance Cockpit (v10.49).

Locks the v10.46 Lean+Compact protocol amendment: every arc closure
ships an interactive UI cockpit alongside the registry/scenario
ratchet. This page closes the credit_model_risk arc by making the two
v10.47-v10.48 engines operator-driveable from the browser:

    🎯 Alt Credit Scoring  — utils.credit_alt_scoring (ENH-260)
    🏛️ Credit Committee   — utils.credit_committee (ENH-268)

Per Rule 1, every engine result is rendered with full provenance —
inputs, intermediates (per-pillar PD + confidence weights, vote
tallies + quorum status), outputs, framework refs.

Per Rule 7, both engines are diagnostic. Alt scoring never
auto-approves a loan; committee engine never auto-disburses funds
or modifies the charter. Outputs feed underwriting workflow + minute
recording — the cockpit makes that posture visible.
"""
from __future__ import annotations

from decimal import Decimal
from datetime import date

import streamlit as st

from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

from utils.credit_alt_scoring import (
    AlternativeCreditScoringEngine,
    ThinFileApplicant,
    TransactionMetrics,
    BehavioralMetrics,
    PsychometricMetrics,
    AltScoringResult,
    ConfidenceBand,
)
from utils.credit_committee import (
    CreditCommitteeEngine,
    CommitteeCharter,
    CommitteeMember,
    CommitteeRole,
    CreditDecisionRequest,
    Vote,
    VoteValue,
    VotingRule,
    DecisionOutcome,
    QuorumStatus,
)


# ──────────────────────────────────────────────────────────────────────
# Access + setup
# ──────────────────────────────────────────────────────────────────────

require_access("perform")
um, ud, uname, *_ = load_shared_state()[:12]


# ──────────────────────────────────────────────────────────────────────
# Header
# ──────────────────────────────────────────────────────────────────────

st.markdown(
    "<div style='padding:24px;background:linear-gradient(135deg,"
    "#15803D 0%,#65A30D 100%);"
    "border-radius:16px;color:white;margin-bottom:20px'>"
    "<div style='font-size:13px;letter-spacing:2px;opacity:0.85'>"
    "CREDIT GOVERNANCE · LIVE COCKPIT</div>"
    "<div style='font-size:28px;font-weight:800;margin-top:6px'>"
    "Credit Governance Cockpit</div>"
    "<div style='font-size:14px;opacity:0.9;margin-top:8px'>"
    "Two diagnostic engines locked under G131: alternative credit "
    "scoring for thin-file applicants (CGAP + Smart Campaign + IFC) "
    "and credit committee governance (CBK PG/03 §6). Outputs feed "
    "underwriting and minute-recording — these engines surface "
    "exposure, never approve loans or disburse funds.</div></div>",
    unsafe_allow_html=True,
)

cred_tabs = st.tabs([
    "🎯 Alt Credit Scoring (#ENH-260)",
    "🏛️ Credit Committee (#ENH-268)",
    "ℹ️ About",
])


# ════════════════════════════════════════════════════════════════════════
# TAB 1 — Alternative Credit Scoring
# ════════════════════════════════════════════════════════════════════════

with cred_tabs[0]:
    st.markdown("### 🎯 Thin-File PD via 3 Alternative Pillars")
    st.caption(
        "CGAP + Smart Campaign + IFC. Each pillar produces a "
        "sub-PD AND a confidence weight (0 when unusable). "
        "Composite = confidence-weighted across usable pillars. "
        "Below LOW confidence → recommend_bureau_check=True so "
        "underwriting escalates rather than acting on a thin "
        "estimate.")

    applicant_id = st.text_input(
        "Applicant ID", value="APP-001", key="alt_applicant_id")

    pillar_cols = st.columns(3)

    # ── Transaction pillar inputs ─────────────────────────────────────
    with pillar_cols[0]:
        st.markdown("##### 1️⃣ TRANSACTION (50% weight)")
        txn_enabled = st.checkbox(
            "Include transaction data", value=True, key="txn_on")
        if txn_enabled:
            months = st.number_input(
                "Months observed", min_value=0, max_value=60, value=12,
                key="txn_months",
                help="Min 3 months for pillar to be usable.")
            cv = st.slider(
                "Monthly deposit CV", 0.0, 2.0, 0.20, 0.05,
                key="txn_cv",
                help="Coefficient of variation. Lower = more stable.")
            salary = st.checkbox(
                "Salary cycle signal present", value=True,
                key="txn_salary")
            ed_ratio = st.slider(
                "Expense / deposit ratio", 0.0, 1.5, 0.65, 0.05,
                key="txn_ed",
                help="High ≈ thin liquidity.")
            bills = st.slider(
                "Bills on time %", 0.0, 1.0, 0.90, 0.05,
                key="txn_bills")

    # ── Behavioral pillar inputs ──────────────────────────────────────
    with pillar_cols[1]:
        st.markdown("##### 2️⃣ BEHAVIORAL (30% weight)")
        beh_enabled = st.checkbox(
            "Include behavioral data", value=True, key="beh_on")
        if beh_enabled:
            tenure = st.number_input(
                "Tenure with bank (months)",
                min_value=0, max_value=120, value=18,
                key="beh_tenure",
                help="Min 1 month for pillar to be usable.")
            mobile = st.slider(
                "Mobile-active days / month", 0, 31, 18, 1,
                key="beh_mobile")
            delinq = st.number_input(
                "Current facility delinquency days",
                min_value=0, max_value=180, value=0,
                key="beh_delinq",
                help="Strongest single behavioral signal.")

    # ── Psychometric pillar inputs ────────────────────────────────────
    with pillar_cols[2]:
        st.markdown("##### 3️⃣ PSYCHOMETRIC (20% weight)")
        psy_enabled = st.checkbox(
            "Include psychometric data", value=False, key="psy_on")
        if psy_enabled:
            risk_tol = st.slider(
                "Risk tolerance score", 0.0, 1.0, 0.30, 0.05,
                key="psy_risk",
                help="Higher = more risk-taking ≈ riskier.")
            time_horizon = st.slider(
                "Time horizon score", 0.0, 1.0, 0.70, 0.05,
                key="psy_horizon",
                help="Higher = longer-term thinking ≈ lower risk.")

    if st.button(
            "Compute alt-PD", type="primary", key="alt_compute"):
        try:
            txn = (TransactionMetrics(
                months_observed=int(months),
                monthly_deposit_cv=float(cv),
                salary_cycle_signal=bool(salary),
                expense_to_deposit_ratio=float(ed_ratio),
                bills_on_time_pct=float(bills),
            ) if txn_enabled else None)
            beh = (BehavioralMetrics(
                tenure_months=int(tenure),
                mobile_active_days_per_month=float(mobile),
                current_facility_delinquency_days=int(delinq),
            ) if beh_enabled else None)
            psy = (PsychometricMetrics(
                risk_tolerance_score=float(risk_tol),
                time_horizon_score=float(time_horizon),
            ) if psy_enabled else None)

            applicant = ThinFileApplicant(
                applicant_id=applicant_id,
                transaction=txn, behavioral=beh, psychometric=psy)
            engine = AlternativeCreditScoringEngine()
            result: AltScoringResult = engine.compute(applicant)

            audit_log("CREDIT_ENGINE_USED", uname, {
                "engine": "credit_alt_scoring",
                "applicant_id": applicant_id,
                "composite_pd": (
                    str(result.composite_pd)
                    if result.composite_pd is not None else None),
                "confidence_band": result.confidence_band.value,
                "missing_pillars": list(result.missing_pillars),
            })

            # Confidence band traffic light
            band_colour = {
                ConfidenceBand.HIGH: "#10B981",
                ConfidenceBand.MEDIUM: "#F59E0B",
                ConfidenceBand.LOW: "#EF4444",
            }[result.confidence_band]
            pd_str = (
                f"{result.composite_pd * 100:.3f}%"
                if result.composite_pd is not None
                else "n/a (no usable pillars)")
            grade_str = result.grade if result.grade else "n/a"
            st.markdown(
                f"<div style='padding:16px;background:{band_colour};"
                f"border-radius:12px;color:white;margin:12px 0'>"
                f"<div style='font-size:12px;opacity:0.85'>"
                f"CONFIDENCE BAND</div>"
                f"<div style='font-size:24px;font-weight:700'>"
                f"{result.confidence_band.value} · "
                f"composite alt-PD = {pd_str} · grade = "
                f"{grade_str}</div></div>",
                unsafe_allow_html=True)

            if result.recommend_bureau_check:
                st.warning(
                    "🔍 **Bureau check recommended.** Confidence "
                    "below threshold — escalate to traditional "
                    "bureau scoring before underwriting decision.")

            m_a, m_b, m_c, m_d = st.columns(4)
            m_a.metric(
                "Composite PD",
                pd_str)
            m_b.metric(
                "Overall confidence",
                f"{float(result.overall_confidence) * 100:.1f}%")
            m_c.metric(
                "Grade",
                grade_str)
            m_d.metric(
                "Missing pillars",
                str(len(result.missing_pillars)),
                help=(", ".join(result.missing_pillars)
                      if result.missing_pillars else "none"))

            # Per-pillar breakdown
            st.markdown("##### Per-pillar breakdown")
            for ps in result.pillar_scores:
                with st.expander(
                        f"{ps.pillar_name} · "
                        f"PD = {ps.pillar_pd if ps.pillar_pd else 'n/a'} "
                        f"· confidence = {ps.confidence_weight}"):
                    if ps.pillar_pd is not None:
                        st.write(
                            f"**Sub-PD:** "
                            f"{ps.pillar_pd * 100:.3f}%")
                        st.write(
                            f"**Confidence weight:** "
                            f"{ps.confidence_weight}")
                        st.write(
                            f"**Features used:** "
                            f"{', '.join(ps.features_used)}")
                    else:
                        st.write(f"**Skipped:** {ps.skip_reason}")

            with st.expander("Full result + framework refs (Rule 1)"):
                st.json({
                    "applicant_id": result.applicant_id,
                    "composite_pd": (
                        str(result.composite_pd)
                        if result.composite_pd is not None
                        else None),
                    "grade": result.grade,
                    "confidence_band": result.confidence_band.value,
                    "overall_confidence": str(
                        result.overall_confidence),
                    "missing_pillars": list(result.missing_pillars),
                    "recommend_bureau_check":
                        result.recommend_bureau_check,
                    "pillar_scores": [
                        {
                            "pillar_name": ps.pillar_name,
                            "pillar_pd": ps.pillar_pd,
                            "confidence_weight": str(
                                ps.confidence_weight),
                            "features_used": list(ps.features_used),
                            "skip_reason": ps.skip_reason,
                        }
                        for ps in result.pillar_scores],
                    "framework_refs": list(result.framework_refs),
                })
        except ValueError as e:
            st.error(f"Validation error: {e}")


# ════════════════════════════════════════════════════════════════════════
# TAB 2 — Credit Committee Governance
# ════════════════════════════════════════════════════════════════════════

with cred_tabs[1]:
    st.markdown("### 🏛️ Credit Committee Decision")
    st.caption(
        "CBK PG/03 §6. Engine validates quorum (headcount + "
        "required roles + independence min), applies the charter's "
        "voting rule, supersedes voting with authority-limit check, "
        "and surfaces escalation requirements for policy overrides "
        "per §6.7. Per Rule 7, engine never auto-approves or "
        "auto-disburses — output feeds minute recording.")

    # Default charter (5 members, simple majority, KES 100m authority)
    DEFAULT_MEMBERS = (
        ("m1", "Alice (Chair)", CommitteeRole.CHAIR, False),
        ("m2", "Bob (CRO)", CommitteeRole.CRO, False),
        ("m3", "Carol (CCO)", CommitteeRole.CCO, False),
        ("m4", "Dave (Independent)",
         CommitteeRole.INDEPENDENT_MEMBER, True),
        ("m5", "Eve (Independent)",
         CommitteeRole.INDEPENDENT_MEMBER, True),
    )

    st.markdown("#### Committee charter")
    charter_cols = st.columns(2)
    with charter_cols[0]:
        voting_rule_label = st.selectbox(
            "Voting rule",
            [vr.value for vr in VotingRule],
            help=(
                "SIMPLE_MAJORITY ties → REJECT defensively. Use "
                "CHAIR_TIEBREAKER if ties should pass."))
        min_quorum = st.number_input(
            "Min quorum count", min_value=1, max_value=5, value=3)
    with charter_cols[1]:
        authority_kes = st.number_input(
            "Authority limit (KES)",
            min_value=1_000_000.0, value=100_000_000.0,
            step=10_000_000.0, format="%.2f",
            help="Facilities above → ESCALATED without vote.")
        indep_min = st.number_input(
            "Min independent members", min_value=0, max_value=5,
            value=1)

    st.markdown("#### Decision request")
    req_cols = st.columns([2, 2, 1])
    with req_cols[0]:
        req_id = st.text_input(
            "Request ID", value="REQ-001", key="com_req_id")
        borrower_id = st.text_input(
            "Borrower ID", value="BORR-123", key="com_borr_id")
    with req_cols[1]:
        facility_kes = st.number_input(
            "Facility (KES)",
            min_value=1_000_000.0, value=50_000_000.0,
            step=1_000_000.0, format="%.2f",
            key="com_facility")
        proposed_rationale = st.text_input(
            "Proposed rationale",
            value="Working capital line for established trader",
            key="com_rationale")
    with req_cols[2]:
        is_override = st.checkbox(
            "Policy override?", value=False, key="com_override")
        override_rationale = ""
        if is_override:
            override_rationale = st.text_area(
                "Override rationale (mandatory per §6.7)",
                value="LTV 92% vs policy max 80%",
                height=70, key="com_override_rat")

    st.markdown("#### Attendance + voting")
    st.caption(
        "Tick attendance. For each attending member, select their "
        "vote. Absent-member votes are silently ignored. Duplicate "
        "votes from one member: first-vote-wins.")
    attending_ids = []
    votes_collected = []
    for mid, mname, mrole, mindep in DEFAULT_MEMBERS:
        att_col, vote_col = st.columns([3, 2])
        with att_col:
            indep_marker = " ⭐" if mindep else ""
            attending = st.checkbox(
                f"{mname} ({mrole.value}){indep_marker}",
                value=True, key=f"att_{mid}")
        with vote_col:
            vote_label = st.selectbox(
                f"Vote — {mid}",
                [vv.value for vv in VoteValue],
                index=0, key=f"vote_{mid}",
                disabled=not attending,
                label_visibility="collapsed")
        if attending:
            attending_ids.append(mid)
            votes_collected.append(
                Vote(member_id=mid,
                     vote=VoteValue(vote_label)))

    conditions_text = st.text_area(
        "Conditions (one per line, optional — drives "
        "APPROVED_WITH_CONDITIONS outcome)",
        value="", height=80, key="com_conditions")

    if st.button(
            "Evaluate decision", type="primary", key="com_compute"):
        try:
            members = tuple(
                CommitteeMember(
                    member_id=mid, name=mname, role=mrole,
                    is_independent=mindep)
                for mid, mname, mrole, mindep in DEFAULT_MEMBERS)
            charter = CommitteeCharter(
                committee_id="MCC",
                name="Management Credit Committee",
                members=members,
                voting_rule=VotingRule(voting_rule_label),
                min_quorum_count=int(min_quorum),
                required_roles=frozenset({CommitteeRole.CRO}),
                authority_limit_kes=Decimal(str(authority_kes)),
                independent_member_min=int(indep_min))
            request = CreditDecisionRequest(
                request_id=req_id, borrower_id=borrower_id,
                facility_kes=Decimal(str(facility_kes)),
                proposed_rationale=proposed_rationale,
                is_policy_override=is_override,
                override_rationale=override_rationale)
            applied_conditions = tuple(
                line.strip() for line in conditions_text.splitlines()
                if line.strip())

            engine = CreditCommitteeEngine(charter)
            result = engine.evaluate(
                request=request,
                attending_member_ids=tuple(attending_ids),
                votes=tuple(votes_collected),
                applied_conditions=applied_conditions,
                notes=f"cockpit_run_{date.today().isoformat()}")

            audit_log("CREDIT_ENGINE_USED", uname, {
                "engine": "credit_committee",
                "request_id": req_id,
                "outcome": result.outcome.value,
                "quorum_status": result.quorum_status.value,
                "escalation_required": result.escalation_required,
            })

            # Outcome banner
            outcome_colour = {
                DecisionOutcome.APPROVED: "#10B981",
                DecisionOutcome.APPROVED_WITH_CONDITIONS: "#10B981",
                DecisionOutcome.REJECTED: "#EF4444",
                DecisionOutcome.DEFERRED: "#F59E0B",
                DecisionOutcome.ESCALATED: "#3B82F6",
                DecisionOutcome.QUORUM_FAILED: "#7F1D1D",
            }[result.outcome]
            st.markdown(
                f"<div style='padding:16px;background:{outcome_colour};"
                f"border-radius:12px;color:white;margin:12px 0'>"
                f"<div style='font-size:12px;opacity:0.85'>OUTCOME</div>"
                f"<div style='font-size:24px;font-weight:700'>"
                f"{result.outcome.value}</div>"
                f"<div style='font-size:13px;opacity:0.9;"
                f"margin-top:6px'>{result.rationale}</div>"
                f"</div>",
                unsafe_allow_html=True)

            if result.escalation_required:
                st.info(
                    f"📤 **Escalation required** to "
                    f"{result.escalation_target}. "
                    f"{'Policy override approval — ' if result.is_policy_override else ''}"
                    f"per CBK PG/03 §6.7.")

            m_a, m_b, m_c, m_d = st.columns(4)
            m_a.metric(
                "Quorum",
                result.quorum_status.value,
                help=result.quorum_reason)
            m_b.metric(
                "YES votes",
                str(result.vote_tally.yes_count))
            m_c.metric(
                "NO votes",
                str(result.vote_tally.no_count))
            m_d.metric(
                "Total present",
                str(result.vote_tally.total_present),
                help=(f"abstain={result.vote_tally.abstain_count}, "
                      f"recused={result.vote_tally.recused_count}"))

            with st.expander(
                    "Full DecisionResult + framework refs (Rule 1)"):
                st.json({
                    "request_id": result.request_id,
                    "committee_id": result.committee_id,
                    "members_present_ids": list(
                        result.members_present_ids),
                    "members_present_roles": [
                        r.value for r in result.members_present_roles],
                    "quorum_status": result.quorum_status.value,
                    "quorum_reason": result.quorum_reason,
                    "vote_tally": {
                        "yes_count": result.vote_tally.yes_count,
                        "no_count": result.vote_tally.no_count,
                        "abstain_count":
                            result.vote_tally.abstain_count,
                        "recused_count":
                            result.vote_tally.recused_count,
                        "total_voting":
                            result.vote_tally.total_voting,
                        "total_present":
                            result.vote_tally.total_present,
                    },
                    "voting_rule": result.voting_rule.value,
                    "outcome": result.outcome.value,
                    "rationale": result.rationale,
                    "conditions": list(result.conditions),
                    "is_policy_override": result.is_policy_override,
                    "escalation_required":
                        result.escalation_required,
                    "escalation_target": result.escalation_target,
                    "framework_refs": list(result.framework_refs),
                    "notes": result.notes,
                })
        except ValueError as e:
            st.error(f"Validation error: {e}")


# ════════════════════════════════════════════════════════════════════════
# TAB 3 — About
# ════════════════════════════════════════════════════════════════════════

with cred_tabs[2]:
    st.markdown("### ℹ️ credit_model_risk arc — About this Cockpit")
    st.markdown(
        """
        The credit_model_risk arc was opened at **v10.47** and closed
        at **v10.49** under the v10.46-amended Lean+Compact protocol
        (UI integration is now non-negotiable at arc closure):

        | Batch    | Module                 | Standards | Status |
        | -------- | ---------------------- | --------- | ------ |
        | v10.47   | credit_alt_scoring     | ENH-260   | ✅      |
        | v10.48   | credit_committee       | ENH-268   | ✅      |
        | **v10.49** | **G131 + G132 + Tier 25 + Master Prompt + this cockpit** | **closure** | ✅      |

        **Frameworks referenced:**

        - CGAP Thin-File Lending Guidance
        - Smart Campaign Client Protection Principles
        - IFC Inclusive Finance — Alternative Data
        - CBK PG/03 §6 Credit Risk Governance (§6.4 quorum, §6.6
          voting + decision recording, §6.7 policy override
          documentation)

        **Diagnostic-only posture (Rule 7).** Neither engine acts on
        decisions. `AlternativeCreditScoringEngine.compute(...)` returns
        a PD estimate with confidence band — never approves a loan,
        never writes to the credit bureau. `CreditCommitteeEngine.
        evaluate(...)` returns a DecisionResult with outcome — never
        disburses funds, never modifies the charter at runtime, never
        publishes to downstream systems. Outputs feed underwriting
        workflow + minute recording — caller responsibility.

        **Provenance discipline (Rule 1).** Every result rendered above
        also exposes its full state under the "Full result + framework
        refs" expander. Alt scoring surfaces all 3 PillarScore objects
        with features_used + skip_reason; committee surfaces the full
        VoteTally + members_present + quorum_status + rationale +
        framework refs.

        Locked under **G131 credit_model_risk_arc_closed** (registry
        + scenario ratchet) and **G132
        credit_model_risk_arc_ui_integrated** (this page's UI
        ratchet — see CHANGELOG_v10.49).

        **Arc state:** registry-locked + scenario-locked + UI-locked
        along three axes per the v10.46 amendment.
        """)

    audit_log("CREDIT_COCKPIT_ABOUT_VIEWED", uname, {
        "page": "94_credit_governance_cockpit"})
