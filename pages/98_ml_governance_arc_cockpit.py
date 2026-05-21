"""pages/98_ml_governance_arc_cockpit.py — ml_governance Arc Cockpit (v10.86).

Locks the v10.46 Lean+Compact protocol amendment for the ml_governance
arc closure (15th closed arc). This page makes all 5 v10.81-v10.85
mlops_* engines operator-driveable from the browser.

The cockpit also surfaces the MLOPS_INTEGRATION_REGISTRY catalog
(the audit-side answer to "apply this everywhere" — codified by
G141). Operations sees which platform engines are wired through
the arc.

Per Rule 1, every engine result renders with full provenance.
Per Rule 7, all 5 engines are diagnostic; this cockpit surfaces
deltas, never auto-promotes models, never auto-deprecates,
never auto-triggers retraining, never publishes externally.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import streamlit as st

from pages._shared import load_shared_state
from pages._access import require_access
from utils.core_audit import audit_log

from utils.mlops_model_registry import (
    MLOpsModelRegistryEngine, ModelRegistryEntry,
    ModelStatus, PromotionGate, GateType, GateComparison,
    PromotionReadinessOutcome)
from utils.mlops_adjudication_log import (
    MLOpsAdjudicationLogEngine, AdjudicationRecord,
    AgreementStatus, OverrideReason, TimeWindow,
    TimeWindowUnit, RecommendationClassTaxonomy)
from utils.mlops_retraining_scheduler import (
    MLOpsRetrainingSchedulerEngine, FreshnessPolicy,
    OverrideThresholds, DriftThresholds,
    RetrainingPolicy, RetrainingOutcome)
from utils.mlops_ab_harness import (
    MLOpsABHarnessEngine, PredictionEvent, PredictionRole,
    ABThresholds, ABReportSeverity)
from utils.mlops_model_card_composer import (
    MLOpsModelCardComposerEngine, ModelCardNarrative,
    ProductionPerformanceSnapshot,
    CardCompletenessRequirements)
from utils.standards_registry import (
    MLOPS_INTEGRATION_REGISTRY)


# ══════════════════════════════════════════════════════════════════════
# Access + setup
# ══════════════════════════════════════════════════════════════════════

require_access("perform")
um, ud, uname, *_ = load_shared_state()[:12]

audit_log(
        "ml_governance_cockpit_view",
        uname,
        "target=" + str("ml_governance_arc") + " " + "meta=" + str({"page": "98_ml_governance_arc_cockpit"}))


# ══════════════════════════════════════════════════════════════════════
# Header
# ══════════════════════════════════════════════════════════════════════

st.markdown(
    "<div style='padding:24px;background:linear-gradient(135deg,"
    "#7C3AED 0%,#1E40AF 100%);"
    "border-radius:16px;color:white;margin-bottom:20px'>"
    "<div style='font-size:13px;letter-spacing:2px;opacity:0.85'>"
    "ML GOVERNANCE ARC · CLOSURE COCKPIT (v10.86)</div>"
    "<div style='font-size:28px;font-weight:600;margin-top:6px'>"
    "🧠 ml_governance Arc — Single Pane of Glass</div>"
    "<div style='font-size:14px;opacity:0.9;margin-top:8px;"
    "max-width:780px'>"
    "Operational deployment lifecycle tracking for ML models on the "
    "platform. Distinct from the closed model_governance arc at "
    "G124 (which handles model risk + validation + drift detection "
    "+ bias monitoring). This arc handles "
    "<strong>WHICH version is deployed</strong>, "
    "<strong>WHAT operators decide</strong>, "
    "<strong>WHEN to retrain</strong>, "
    "<strong>HOW shadow compares to active</strong>, "
    "and <strong>composes per-model cards</strong> from all of the "
    "above. All 5 engines diagnostic; operator decides every "
    "transition.</div>"
    "</div>",
    unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
# Tabs (one per engine + one for the integration catalog)
# ══════════════════════════════════════════════════════════════════════

tab_registry, tab_adj, tab_retrain, tab_ab, tab_cards, tab_wiring = (
    st.tabs([
        "🗂️ Registry (ENH-281)",
        "✋ Adjudication (ENH-282)",
        "🔄 Retraining (ENH-283)",
        "🆎 A/B Harness (ENH-284)",
        "📋 Model Cards (ENH-285)",
        "🔌 Cross-Platform Wiring (G141)",
    ]))


# ──────────────────────────────────────────────────────────────────────
# Tab 1: Registry
# ──────────────────────────────────────────────────────────────────────
with tab_registry:
    st.markdown("### Model Registry (ENH-281)")
    st.caption(
        "Operational deployment lifecycle tracking. Engine "
        "DIAGNOSTIC ONLY — never persists, never promotes, "
        "never deploys.")
    registry_engine = MLOpsModelRegistryEngine()

    st.markdown(
        "**Demo: validate promotion readiness with three "
        "gate types**")
    active_entry = ModelRegistryEntry(
        model_id="doc_classifier", version="1.0.0",
        artifact_hash="a" * 64,
        training_data_hash="b" * 64,
        framework="sklearn", framework_version="1.5.1",
        metrics={"accuracy": Decimal("0.85")},
        owner="ml-team@bank",
        status=ModelStatus.ACTIVE,
        created_by="trainer", created_at_iso="2026-04-01T00:00:00Z")
    candidate = ModelRegistryEntry(
        model_id="doc_classifier", version="2.0.0",
        artifact_hash="c" * 64,
        training_data_hash="d" * 64,
        framework="sklearn", framework_version="1.5.1",
        metrics={"accuracy": Decimal("0.91")},
        owner="ml-team@bank",
        status=ModelStatus.PROPOSED,
        created_by="trainer", created_at_iso="2026-05-01T00:00:00Z")
    gates = (
        PromotionGate(
            gate_id="MIN", gate_type=GateType.MINIMUM_METRIC,
            description="Accuracy ≥ 0.80",
            metric_name="accuracy",
            threshold=Decimal("0.80"),
            comparison=GateComparison.GTE),
        PromotionGate(
            gate_id="REG", gate_type=GateType.NON_REGRESSION,
            description="No regression vs active",
            metric_name="accuracy",
            regression_tolerance=Decimal("0.01"),
            comparison=GateComparison.GTE),
        PromotionGate(
            gate_id="META",
            gate_type=GateType.METADATA_REQUIRED,
            description="Owner present",
            required_field="owner"),
    )
    if st.button("Run promotion readiness check",
                 key="reg_check"):
        assessment = (
            registry_engine.validate_promotion_readiness(
                candidate, active_entry, gates))
        if assessment.outcome == PromotionReadinessOutcome.READY:
            st.success(
                f"✓ Outcome: {assessment.outcome.value}")
        elif assessment.outcome == (
            PromotionReadinessOutcome.BLOCKED
        ):
            st.error(
                f"✗ Outcome: {assessment.outcome.value}")
        else:
            st.warning(
                f"⚠ Outcome: {assessment.outcome.value}")

        for f in assessment.findings:
            st.markdown(
                f"- **{f.gate_id}** ({f.gate_type.value}) "
                f"— {f.severity.value}: {f.description}  \n"
                f"  *expected:* {f.expected}  \n"
                f"  *observed:* {f.observed}")
        audit_log(
        "ml_governance_promotion_check",
        uname,
        "target=" + str(f"{candidate.model_id}@{candidate.version}") + " " + "meta=" + str({"outcome": assessment.outcome.value}))


# ──────────────────────────────────────────────────────────────────────
# Tab 2: Adjudication
# ──────────────────────────────────────────────────────────────────────
with tab_adj:
    st.markdown("### Adjudication Log (ENH-282)")
    st.caption(
        "Operator-override capture. Engine surfaces signals; "
        "bias DECISION belongs to model_governance arc at G124.")
    adj_engine = MLOpsAdjudicationLogEngine()

    st.markdown(
        "**Demo: compute override rate over a 24-hour window**")
    sample_records = (
        AdjudicationRecord(
            event_id="E1", model_id="doc_classifier",
            model_version="1.0", recommendation="APPROVE",
            recommendation_class="APPROVE",
            operator_decision="APPROVE",
            agreement_status=AgreementStatus.ACCEPTED,
            operator_id="alice",
            decision_at_iso="2026-05-01T10:00:00Z",
            override_reason=None,
            override_reason_text="",
            input_features_hash=None,
            retraining_eligible=False, notes=""),
        AdjudicationRecord(
            event_id="E2", model_id="doc_classifier",
            model_version="1.0", recommendation="APPROVE",
            recommendation_class="APPROVE",
            operator_decision="REJECT",
            agreement_status=AgreementStatus.OVERRIDDEN,
            operator_id="alice",
            decision_at_iso="2026-05-01T11:00:00Z",
            override_reason=OverrideReason.DOMAIN_KNOWLEDGE,
            override_reason_text="watchlist match",
            input_features_hash="a" * 64,
            retraining_eligible=True, notes=""),
        AdjudicationRecord(
            event_id="E3", model_id="doc_classifier",
            model_version="1.0", recommendation="APPROVE",
            recommendation_class="APPROVE",
            operator_decision="REJECT",
            agreement_status=AgreementStatus.OVERRIDDEN,
            operator_id="bob",
            decision_at_iso="2026-05-01T12:00:00Z",
            override_reason=OverrideReason.POLICY_OVERRIDE,
            override_reason_text="",
            input_features_hash="b" * 64,
            retraining_eligible=True, notes=""),
    )
    window = TimeWindow(
        duration=24, unit=TimeWindowUnit.HOURS,
        end_iso="2026-05-02T00:00:00Z")

    if st.button("Compute override rate",
                 key="adj_rate"):
        m = adj_engine.compute_override_rate(
            sample_records, "doc_classifier", window)
        col1, col2, col3 = st.columns(3)
        col1.metric("Total decided",
                    m.count_accepted + m.count_overridden)
        col2.metric("Overridden", m.count_overridden)
        col3.metric(
            "Override rate",
            f"{m.override_rate}" if m.override_rate
            else "N/A")
        st.caption(
            "Per Rule 1, rate is None when no decided "
            "records (PENDING + ESCALATED excluded from "
            "denominator). Engine never decides 'rate "
            "too high → trigger retraining' — that's "
            "ENH-283 territory.")
        audit_log(
        "ml_governance_override_rate",
        uname,
        "target=" + str("doc_classifier") + " " + "meta=" + str({"rate": str(m.override_rate)}))


# ──────────────────────────────────────────────────────────────────────
# Tab 3: Retraining Scheduler
# ──────────────────────────────────────────────────────────────────────
with tab_retrain:
    st.markdown("### Retraining Scheduler (ENH-283)")
    st.caption(
        "Combines freshness + override + drift signals against "
        "caller policy. Engine never auto-triggers retraining.")
    retrain_engine = MLOpsRetrainingSchedulerEngine()

    st.markdown(
        "**Demo: combined retraining recommendation**")
    fresh_policy = FreshnessPolicy(
        warning_age_days=30, stale_age_days=90)
    override_thresholds = OverrideThresholds(
        warning_rate=Decimal("0.20"),
        critical_rate=Decimal("0.40"))
    drift_thresholds = DriftThresholds(
        warning_value=Decimal("0.10"),
        critical_value=Decimal("0.25"),
        metric_name="PSI")

    fresh = retrain_engine.evaluate_freshness(
        model_id="doc_classifier",
        model_version="1.0.0",
        training_completed_at_iso="2026-04-15T00:00:00Z",
        as_of_iso="2026-05-01T00:00:00Z",
        policy=fresh_policy)
    override_signal = retrain_engine.evaluate_override_signal(
        model_id="doc_classifier",
        current_rate=Decimal("0.08"),
        thresholds=override_thresholds)
    drift_signal = retrain_engine.evaluate_drift_signal(
        model_id="doc_classifier",
        current_value=Decimal("0.06"),
        thresholds=drift_thresholds)

    if st.button("Compute retraining recommendation",
                 key="retrain_rec"):
        rec = retrain_engine.compute_retraining_recommendation(
            model_id="doc_classifier",
            model_version="1.0.0",
            freshness=fresh,
            override_signal=override_signal,
            drift_signal=drift_signal,
            policy=RetrainingPolicy(
                require_freshness=True,
                require_override_signal=True,
                require_drift_signal=True))
        if rec.outcome == RetrainingOutcome.DUE:
            st.error(f"Outcome: {rec.outcome.value}")
        elif rec.outcome == RetrainingOutcome.SOON:
            st.warning(f"Outcome: {rec.outcome.value}")
        elif rec.outcome == RetrainingOutcome.NOT_YET:
            st.success(f"Outcome: {rec.outcome.value}")
        else:
            st.info(f"Outcome: {rec.outcome.value}")
        st.markdown(f"**Rationale:** {rec.rationale}")
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Freshness", rec.freshness.severity.value)
        col2.metric(
            "Override",
            rec.override_signal.severity.value)
        col3.metric(
            "Drift",
            rec.drift_signal.severity.value)
        audit_log(
        "ml_governance_retraining_check",
        uname,
        "target=" + str("doc_classifier") + " " + "meta=" + str({"outcome": rec.outcome.value}))


# ──────────────────────────────────────────────────────────────────────
# Tab 4: A/B Harness
# ──────────────────────────────────────────────────────────────────────
with tab_ab:
    st.markdown("### A/B Comparison Harness (ENH-284)")
    st.caption(
        "Bridge from candidate registered (SHADOW) to ready for "
        "promotion (ACTIVE). Engine never auto-promotes — "
        "ENH-281 validate_promotion_readiness is the gate.")
    ab_engine = MLOpsABHarnessEngine()

    st.markdown(
        "**Demo: 100 paired predictions with 95% agreement**")
    events = []
    for i in range(100):
        events.append(PredictionEvent(
            event_id=f"A{i}",
            input_features_hash=f"h{i}",
            model_id="doc_classifier",
            model_version="1.0",
            role=PredictionRole.ACTIVE,
            predicted_class="APPROVE",
            predicted_at_iso="2026-05-01T10:00:00Z",
            latency_ms=Decimal("100")))
        sclass = "REJECT" if i < 5 else "APPROVE"
        events.append(PredictionEvent(
            event_id=f"S{i}",
            input_features_hash=f"h{i}",
            model_id="doc_classifier",
            model_version="2.0",
            role=PredictionRole.SHADOW,
            predicted_class=sclass,
            predicted_at_iso="2026-05-01T10:00:00Z",
            latency_ms=Decimal("105")))

    if st.button("Run A/B comparison",
                 key="ab_compare"):
        report = ab_engine.build_ab_comparison_report(
            events, "1.0", "2.0",
            thresholds=ABThresholds(
                minimum_paired_sample=50))
        if report.composite_severity == (
            ABReportSeverity.READY_TO_PROMOTE
        ):
            st.success(
                f"Composite severity: "
                f"{report.composite_severity.value}")
        elif report.composite_severity == (
            ABReportSeverity.NEEDS_REVIEW
        ):
            st.warning(
                f"Composite severity: "
                f"{report.composite_severity.value}")
        elif report.composite_severity == (
            ABReportSeverity.NOT_READY
        ):
            st.error(
                f"Composite severity: "
                f"{report.composite_severity.value}")
        else:
            st.info(
                f"Composite severity: "
                f"{report.composite_severity.value}")
        st.markdown(f"**Rationale:** {report.rationale}")
        col1, col2, col3 = st.columns(3)
        col1.metric(
            "Agreement rate",
            f"{report.agreement.agreement_rate}")
        col2.metric(
            "Latency Δ (median, ms)",
            f"{report.latency.median_delta_ms}")
        col3.metric(
            "Total paired",
            report.agreement.total_paired)
        audit_log(
        "ml_governance_ab_compare",
        uname,
        "target=" + str("doc_classifier") + " " + "meta=" + str({
                "severity": report.composite_severity.value}))


# ──────────────────────────────────────────────────────────────────────
# Tab 5: Model Cards
# ──────────────────────────────────────────────────────────────────────
with tab_cards:
    st.markdown("### Model Card Composer (ENH-285)")
    st.caption(
        "Composes per-model documentation surfaces from every "
        "other arc engine's output + caller-supplied narrative. "
        "Source of truth: structured ModelCard. Markdown "
        "rendering for human consumption.")
    card_engine = MLOpsModelCardComposerEngine()

    if st.button("Compose sample model card",
                 key="card_compose"):
        narrative = ModelCardNarrative(
            intended_use=(
                "Classify trade finance documents into "
                "DISCREPANT vs CLEAN buckets"),
            out_of_scope_use=(
                "Not for credit decisions; advisory only"),
            training_data_description=(
                "12 months of FLEXCUBE document attachments "
                "labeled by trade ops"),
            evaluation_data_description=(
                "Held-out 20% from same period, stratified"),
            ethical_considerations=(
                "Operator-in-the-loop required; "
                "recommendations advisory"),
            caveats_and_recommendations=(
                "Quarterly retraining per ENH-283 freshness "
                "policy"))
        snapshot = ProductionPerformanceSnapshot(
            snapshot_at_iso="2026-05-01T10:00:00Z",
            override_rate_30d=Decimal("0.08"),
            override_sample_size_30d=347,
            drift_metric_name="PSI",
            drift_metric_value=Decimal("0.06"),
            last_retraining_outcome="NOT_YET",
            last_retraining_rationale=(
                "All signals OK"),
            last_ab_severity="READY_TO_PROMOTE",
            last_ab_against_version="2.0.0-shadow")
        result = card_engine.compose_model_card(
            model_id="doc_classifier",
            model_version="1.0.0",
            framework="sklearn",
            framework_version="1.5.1",
            owner="ml-team@bank",
            artifact_hash="a" * 64,
            training_data_hash="b" * 64,
            operational_status="ACTIVE",
            training_metrics={
                "accuracy": Decimal("0.87"),
                "f1": Decimal("0.85")},
            narrative=narrative,
            composed_at_iso=(
                datetime.now(timezone.utc).isoformat()),
            composed_by=uname,
            training_completed_at_iso=(
                "2026-04-15T00:00:00Z"),
            production_snapshot=snapshot)
        if result.outcome.value == "COMPOSED":
            st.success(f"Outcome: {result.outcome.value}")
            md = card_engine.serialize_card_to_markdown(
                result.card)
            with st.expander(
                "Markdown preview", expanded=True):
                st.markdown(md)
        else:
            st.error(f"Outcome: {result.outcome.value}")
            for f in result.findings:
                st.markdown(f"- {f}")
        audit_log(
        "ml_governance_card_compose",
        uname,
        "target=" + str("doc_classifier") + " " + "meta=" + str({"outcome": result.outcome.value}))


# ──────────────────────────────────────────────────────────────────────
# Tab 6: Cross-platform wiring catalog
# ──────────────────────────────────────────────────────────────────────
with tab_wiring:
    st.markdown(
        "### Cross-Platform Wiring Catalog (G141)")
    st.caption(
        "MLOPS_INTEGRATION_REGISTRY — the audit-side answer to "
        "'apply this everywhere.' Per Rule 7, this is a "
        "CATALOG, not coupling. The mlops_* engines never read "
        "this registry; wiring lives in CALLER code paths.")

    n_total = len(MLOPS_INTEGRATION_REGISTRY)
    n_v10_76 = sum(
        1 for e in MLOPS_INTEGRATION_REGISTRY
        if e.uses_v10_76_hook_contract)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Engines catalogued", n_total)
    col2.metric("Use v10.76 hook", n_v10_76)
    col3.metric(
        "Registry-wired (planned)",
        sum(1 for e in MLOPS_INTEGRATION_REGISTRY
            if e.registry_wiring_planned))
    col4.metric(
        "Adjudication-wired (planned)",
        sum(1 for e in MLOPS_INTEGRATION_REGISTRY
            if e.adjudication_wiring_planned))

    for entry in MLOPS_INTEGRATION_REGISTRY:
        with st.expander(
            f"**{entry.engine_module}** "
            f"({entry.standard_id}) — "
            f"v10.76={'✓' if entry.uses_v10_76_hook_contract else '—'}",
            expanded=False):
            col1, col2, col3 = st.columns(3)
            col1.metric(
                "Registry wired",
                "✓" if entry.registry_wiring_planned else "—")
            col2.metric(
                "Adjudication wired",
                "✓" if entry.adjudication_wiring_planned
                else "—")
            col3.metric(
                "Scheduler wired",
                "✓" if entry.scheduler_wiring_planned else "—")
            st.markdown(f"**Notes:** {entry.notes}")


# ══════════════════════════════════════════════════════════════════════
# Footer
# ══════════════════════════════════════════════════════════════════════

st.markdown("---")
st.caption(
    "ml_governance arc cockpit — v10.86 closure batch. 5 engines + "
    "MLOPS_INTEGRATION_REGISTRY catalog + G139/G140/G141 audit gates. "
    "15th closed arc on the platform. Per Rule 7, every interaction "
    "above is diagnostic — engines never auto-promote, never auto-"
    "deprecate, never auto-trigger retraining, never publish "
    "externally. Per Rule 1, every output preserves provenance + "
    "framework_refs. Caller-supplied data discipline matches the "
    "arc pattern through ENH-281/282/283/284/285.")
