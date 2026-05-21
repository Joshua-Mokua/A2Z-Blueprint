"""system_flows.py — feedback loop registry for A2Z.

v7.0 introduces this module to make Donella Meadows' "feedback loops"
first-class. Until v7.0, cross-engine integration was implicit — some
loops worked (BSC ↔ actuals, profitability cluster), most were absent.

This module is **declarative**. It does not execute or enforce loops.
It enumerates the 15 designed feedback loops (Charter Section 8) with
metadata: source engine, target engine, payload, integration pattern,
delay characteristics, wiring status.

Usage:
  - Pages query this module to surface loop status to operators
  - Audit queries this module to verify "designed" loops are documented
  - Future v7.x batches close DESIGNED_NOT_WIRED loops one at a time

Philosophy:
  - Pure: no I/O, no global state, no side effects
  - Honest: status field surfaces wiring state truthfully
  - Caller-side: engines do not import this module; pages and audit do

References:
  Donella Meadows, *Thinking in Systems* (2008), Ch. 1: "Feedback loops"
  Eric Evans, *Domain-Driven Design* (2003): integration patterns
  A2Z Systems Charter, Sections 7-8
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────
# Status constants — honest wiring state
# ──────────────────────────────────────────────────────────────────────

LOOP_WIRED = "WIRED"                              # Live in code
LOOP_DESIGNED_NOT_WIRED = "DESIGNED_NOT_WIRED"    # Documented, not wired
LOOP_PARTIAL = "PARTIAL"                          # Half-wired (rare)
LOOP_DEPRECATED = "DEPRECATED"                    # Was wired, now retired


# ──────────────────────────────────────────────────────────────────────
# Integration patterns (DDD vocabulary, Charter Section 7)
# ──────────────────────────────────────────────────────────────────────

PATTERN_PUBLISHED_LANGUAGE = "PUBLISHED_LANGUAGE"
PATTERN_CUSTOMER_SUPPLIER = "CUSTOMER_SUPPLIER"
PATTERN_ANTI_CORRUPTION_LAYER = "ANTI_CORRUPTION_LAYER"
PATTERN_CONFORMIST = "CONFORMIST"
PATTERN_OPEN_HOST_SERVICE = "OPEN_HOST_SERVICE"
PATTERN_SHARED_KERNEL = "SHARED_KERNEL"

VALID_PATTERNS = (
    PATTERN_PUBLISHED_LANGUAGE,
    PATTERN_CUSTOMER_SUPPLIER,
    PATTERN_ANTI_CORRUPTION_LAYER,
    PATTERN_CONFORMIST,
    PATTERN_OPEN_HOST_SERVICE,
    PATTERN_SHARED_KERNEL,
)


# ──────────────────────────────────────────────────────────────────────
# FeedbackLoop dataclass
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FeedbackLoop:
    """A single designed feedback loop in A2Z."""
    loop_id: str  # e.g. 'L01_collections_to_pd'
    name: str
    from_context: str  # Bounded context (Charter Section 3)
    to_context: str
    from_engine: str  # utils.<engine>
    to_engine: str
    payload: str  # What data flows
    purpose: str  # Why this loop matters
    pattern: str  # Integration pattern (Charter Section 7)
    detection_delay: str  # When does target know change occurred?
    response_delay: str  # When does target's behaviour change?
    status: str  # Wiring status
    learning_loop: bool = False  # True if outcomes feed back to recalibrate
    notes: str = ""


# ──────────────────────────────────────────────────────────────────────
# The 15 designed feedback loops (Charter Section 8)
# ──────────────────────────────────────────────────────────────────────

FEEDBACK_LOOPS: Dict[str, FeedbackLoop] = {
    "L01": FeedbackLoop(
        loop_id="L01",
        name="Collections → PD recalibration",
        from_context="Credit Risk",
        to_context="Credit Risk",
        from_engine="utils.system_stocks",
        to_engine="utils.credit_risk_scoring",
        payload="actual_repayment_outcomes_by_segment",
        purpose=(
            "Realised default behaviour recalibrates probability-of-default "
            "models. Without this loop, PD models drift from reality."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="month-end batch",
        response_delay="quarterly model review",
        status=LOOP_WIRED,
        learning_loop=True,
        notes=(
            "v7.1: WIRED via npl_inventory stock + portfolio_pd_summary "
            "engine path. credit_risk_scoring engine reads NPL data via "
            "system_stocks.get_stock_snapshot('npl_inventory'); "
            "portfolio_pd_summary aggregates per-grade PD bands. "
            "This is the canonical Meadows learning loop — outcomes "
            "(actual defaults) recalibrate behaviour (next-period PD). "
            "Registry `from_engine` corrected v7.15 from `utils.collections` "
            "(never existed) to `utils.system_stocks` (actual producer "
            "interface — credit_risk_scoring reads via "
            "system_stocks.get_stock_snapshot); discovered by new G106 audit gate."
        ),
    ),

    "L02": FeedbackLoop(
        loop_id="L02",
        name="Customer profitability → Target cascade",
        from_context="Profitability",
        to_context="Strategy & Cascade",
        from_engine="utils.customer_profitability",
        to_engine="utils.profitability_integration",
        payload="customer_pnl_aggregated_by_rm",
        purpose=(
            "Realised RM portfolio profitability adjusts next-period "
            "RM targets. High performers get stretch targets; under-"
            "performers get coaching targets."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="month-end actuals close",
        response_delay="next quarterly target review",
        status=LOOP_WIRED,
        learning_loop=True,
        notes="Wired in v5.92 via `profitability_integration`. Registry `to_engine` corrected v7.15 from `utils.target_cascade` (never existed) to `utils.profitability_integration` (actual consumer); discovered by new G106 audit gate.",
    ),

    "L03": FeedbackLoop(
        loop_id="L03",
        name="Staff campaigns → BSC engine",
        from_context="Smart Alerts & Nudges",
        to_context="Performance Measurement",
        from_engine="utils.nudge_engine",
        to_engine="utils.bsc_engine",
        payload="campaign_completion_signals",
        purpose=(
            "Successful nudges and campaign closures update BSC scores. "
            "A campaign that fires but doesn't complete shouldn't reward "
            "the same as one that completes."
        ),
        pattern=PATTERN_OPEN_HOST_SERVICE,
        detection_delay="real-time",
        response_delay="next BSC compute cycle",
        status=LOOP_WIRED,
        notes="Wired since v5.x via bsc_engine.submit_batch().",
    ),

    "L04": FeedbackLoop(
        loop_id="L04",
        name="Value chain health → Operational risk",
        from_context="Cross-sell & NBA",
        to_context="Operational Risk",
        from_engine="utils.vendor_risk",
        to_engine="utils.operational_risk",
        payload="vendor_concentration_and_dependency_signals",
        purpose=(
            "Vendor / partner health signals (SLA breaches, concentration, "
            "single-source dependencies) feed operational risk scoring. "
            "An overdependence on one vendor is itself an operational risk."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="weekly aggregation",
        response_delay="next monthly RCSA review",
        status=LOOP_WIRED,
        notes=(
            "v7.6: WIRED via OperationalRiskEngine.vendor_health_to_oprisk() "
            "CONSUMER. from_engine corrected from utils.partnerships (which "
            "doesn't exist as a module — fifth such correction in v7.x) to "
            "utils.vendor_risk (the actual engine). Synthesises HIGH/CRITICAL "
            "oprisk events from concentration breaches + SLA breaches "
            "(HIGH/CRITICAL only) + due-diligence gaps (<80% completeness). "
            "Consumes vendor_risk.vendor_concentration_check + sla_breach_severity "
            "+ due_diligence_completeness outputs."
        ),
    ),

    "L05": FeedbackLoop(
        loop_id="L05",
        name="Card usage → Customer 360 enrichment",
        from_context="Branch & Channels",
        to_context="Customer Intelligence",
        from_engine="utils.cards",
        to_engine="utils.customer_segmentation",
        payload="transaction_velocity_merchant_categories_geographic_pattern",
        purpose=(
            "Card usage patterns (where, when, what) enrich RFM segments "
            "and CLV projections. Two customers with identical balances "
            "but different card usage have different lifetime value."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="daily batch",
        response_delay="next monthly segmentation refresh",
        status=LOOP_WIRED,
        notes=(
            "v7.12: WIRED via new `utils/cards.py` module (CardsEngine with "
            "usage_velocity + merchant_category_mix + geographic_pattern + "
            "card_usage_profile aggregator producing PUBLISHED_LANGUAGE "
            "payload_version 1.0) + `customer_segmentation.py` CONSUMER "
            "`enrich_segment_with_card_usage()`. Strategy: HIGH velocity + "
            "diverse MCCs uplift segment 1 step (LOYAL→CHAMPIONS); DORMANT "
            "velocity downgrades 1 step; FOREIGN_HEAVY geo flags "
            "TRAVELER_PROFILE; >70% dominant MCC flags SPECIALIST_PROFILE. "
            "Round-trip verified."
        ),
    ),

    "L06": FeedbackLoop(
        loop_id="L06",
        name="Stress test scenarios → Capital plan",
        from_context="Daily-Risk Trifecta",
        to_context="Treasury & ALM",
        from_engine="utils.stress_testing",
        to_engine="utils.capital_adequacy",
        payload="scenario_capital_shortfall_kes",
        purpose=(
            "Severely-adverse stress test capital shortfall feeds the "
            "capital plan as a buffer-rebuild requirement. ICAAP "
            "submission ties stress results to capital plan directly."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="quarterly stress test",
        response_delay="annual ICAAP cycle",
        status=LOOP_WIRED,
        notes=(
            "v7.2: WIRED via stress_capital_shortfall_summary() PRODUCER "
            "→ capital_plan_from_stress() CONSUMER. Payload version 1.0 "
            "stable contract per Charter §7 Published Language pattern. "
            "Shortfall = required_capital - stressed_capital using CBK CAR "
            "floor from invariants registry. Plan severity bands: GREEN "
            "(no breach), AMBER (≤5B organic retention), RED (≤15B Tier 2 "
            "issuance), CRITICAL (>15B rights issue + CBK notification)."
        ),
    ),

    "L07": FeedbackLoop(
        loop_id="L07",
        name="KYC risk band → Transaction monitoring sensitivity",
        from_context="Compliance / AML",
        to_context="Compliance / AML",
        from_engine="utils.kyc_aml_risk",
        to_engine="utils.transaction_monitoring",
        payload="customer_risk_band_per_customer",
        purpose=(
            "HIGH-risk KYC customers should trigger TxnMonitor alerts at "
            "lower thresholds than LOW-risk customers. Currently all "
            "customers face the same thresholds (false-positive heavy "
            "for low-risk; false-negative-prone for high-risk)."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="onboarding (real-time) + annual re-KYC",
        response_delay="next transaction batch",
        status=LOOP_WIRED,
        notes=(
            "v7.2: WIRED via TransactionMonitoringEngine.scan_with_risk_bands() "
            "CONSUMER. Backward-compatible (calls scan() then post-processes). "
            "HIGH/PROHIBITED bands trigger severity uplift (MEDIUM→HIGH, "
            "HIGH→CRITICAL); LOW band triggers downgrade only for benign "
            "rules (R5 dormant, R6 round-number) — never for CRITICAL "
            "rules (R2 structuring, R4 high-risk geography). Consumed "
            "payload: kyc_aml_risk.KycRiskAssessment.risk_band v1.0."
        ),
    ),

    "L08": FeedbackLoop(
        loop_id="L08",
        name="Engagement scores → Flight risk → Succession",
        from_context="HR Intelligence",
        to_context="HR Intelligence",
        from_engine="utils.employee_engagement",
        to_engine="utils.predictive_performance",
        payload="staff_engagement_score_and_flight_risk_signals",
        purpose=(
            "Low engagement + high flight risk signals trigger succession "
            "planning + retention conversations. Without this loop, "
            "engagement surveys are vanity metrics."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="quarterly survey",
        response_delay="monthly 1:1 cycle",
        status=LOOP_WIRED,
        learning_loop=True,
        notes="Wired in v5.98 engagement depth.",
    ),

    "L09": FeedbackLoop(
        loop_id="L09",
        name="Branch performance → Resource allocation",
        from_context="Branch & Channels",
        to_context="Cross-sell & NBA",
        from_engine="utils.branch_performance",
        to_engine="utils.allocation_optimizer",
        payload="branch_efficiency_metrics_and_capacity_utilisation",
        purpose=(
            "Underperforming branches should get RM reallocation; "
            "overperforming branches should get capacity expansion "
            "(or be the model for replication)."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="monthly branch close",
        response_delay="quarterly RM review",
        status=LOOP_WIRED,
        notes=(
            "v7.4: WIRED via CustomerAllocationOptimizer."
            "reallocation_signals_from_branch_performance() CONSUMER. "
            "from_engine corrected from utils.branch_log (which doesn't "
            "exist as a module — was a registry placeholder error) to "
            "utils.branch_performance (the actual engine). "
            "Quartile-based directives: TOP→EXPAND_CAPACITY, "
            "Q2→MAINTAIN, Q3→COACHING_INVESTMENT, BOTTOM→REALLOCATION_CANDIDATE. "
            "Sorted by priority so HIGH_RISK reallocations surface first. "
            "Consumes branch_performance.peer_benchmark_metrics + quartile_rank "
            "outputs."
        ),
    ),

    "L10": FeedbackLoop(
        loop_id="L10",
        name="Customer churn → Cross-sell prioritisation",
        from_context="Customer Intelligence",
        to_context="Cross-sell & NBA",
        from_engine="utils.churn_prediction",
        to_engine="utils.cross_sell_nba",
        payload="at_risk_customer_list_with_retention_value",
        purpose=(
            "Customers predicted to churn but with high retention value "
            "should jump the cross-sell queue. Saving an existing "
            "customer is cheaper than acquiring a new one."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="weekly churn model run",
        response_delay="next campaign cycle",
        status=LOOP_WIRED,
        notes=(
            "v7.3: WIRED via CrossSellNextBestActionEngine.priorities_from_churn() "
            "CONSUMER. to_engine corrected from utils.cross_sell to "
            "utils.cross_sell_nba (the actual engine). Consumes "
            "churn_prediction.retention_intervention_priority() output. "
            "HIGH-risk customers get full uplift (× factor); MEDIUM-risk "
            "customers get half uplift; LOW-risk untouched. Default "
            "uplift factor = 1.5x. Saves an existing customer rather "
            "than acquiring a new one — Meadows leverage point #4 "
            "(self-organisation through retention prioritisation)."
        ),
    ),

    "L11": FeedbackLoop(
        loop_id="L11",
        name="RCSA deficiencies → Audit findings",
        from_context="Operational Risk",
        to_context="Operational Risk",
        from_engine="utils.internal_controls",
        to_engine="utils.audit_universe",
        payload="material_weakness_and_significant_deficiency_records",
        purpose=(
            "RCSA-identified material weaknesses become audit-tracked "
            "findings with owners, target dates, status. Currently RCSA "
            "and audit workflow live in separate engines."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="annual RCSA cycle",
        response_delay="next audit committee meeting",
        status=LOOP_WIRED,
        notes=(
            "v7.2: WIRED via AuditUniverseEngine.audit_findings_from_rcsa() "
            "CONSUMER. to_engine corrected from utils.audit_workflow (which "
            "doesn't exist) to utils.audit_universe (the actual engine). "
            "Severity mapping per PCAOB AS 2201: MATERIAL_WEAKNESS → "
            "CRITICAL (30-day target, audit committee escalation); "
            "SIGNIFICANT_DEFICIENCY → HIGH (60-day target, management "
            "response); DEFICIENCY → MEDIUM (90-day target, RCSA owner "
            "action). Consumed payload: internal_controls.classify_deficiency v1.0."
        ),
    ),

    "L12": FeedbackLoop(
        loop_id="L12",
        name="Profitability hierarchy → BSC",
        from_context="Profitability",
        to_context="Performance Measurement",
        from_engine="utils.profitability_hierarchy",
        to_engine="utils.bsc_engine",
        payload="rm_pyramid_profitability_aggregates",
        purpose=(
            "RM-level profitability rolls up the management hierarchy "
            "and lands in BSC at branch + region + country tiers. "
            "Hierarchy mirrors the bank's actual reporting lines."
        ),
        pattern=PATTERN_CUSTOMER_SUPPLIER,
        detection_delay="month-end actuals",
        response_delay="next BSC compute",
        status=LOOP_WIRED,
        notes="Wired in v5.92 via profitability_integration.",
    ),

    "L13": FeedbackLoop(
        loop_id="L13",
        name="Compensation equity → Workforce planning",
        from_context="HR Intelligence",
        to_context="HR Intelligence",
        from_engine="utils.compensation_equity",
        to_engine="utils.workforce_analytics",
        payload="below_band_staff_and_uplift_cost_estimate",
        purpose=(
            "Below-compa-ratio staff identified by compensation analysis "
            "feed workforce planning's annual merit budget. Without this "
            "loop, equity remediation is ad-hoc."
        ),
        pattern=PATTERN_PUBLISHED_LANGUAGE,
        detection_delay="annual comp review",
        response_delay="next merit cycle",
        status=LOOP_WIRED,
        notes=(
            "v7.5: WIRED via WorkforceAnalyticsEngine.merit_budget_from_compensation_equity() "
            "CONSUMER. to_engine corrected from utils.workforce_planning "
            "(which doesn't exist as a module — fourth such correction "
            "in v7.x after L11/L10/L09) to utils.workforce_analytics "
            "(the actual engine). Consumer takes per-grade pay distribution "
            "and gender-pay-gap data, produces merit budget recommendation "
            "with priority targeting of below-median + below-pay-gap-line "
            "staff. Per Charter §7 Published Language pattern."
        ),
    ),

    "L14": FeedbackLoop(
        loop_id="L14",
        name="Channel reliability → Customer experience alerts",
        from_context="Branch & Channels",
        to_context="Smart Alerts & Nudges",
        from_engine="utils.channels_reliability",
        to_engine="utils.smart_alerts",
        payload="channel_outage_and_degradation_events",
        purpose=(
            "ATM down, mobile-app slowness, or agent-banking SLA breach "
            "should trigger proactive customer alerts ('your usual ATM "
            "is down; nearest alternative is X')."
        ),
        pattern=PATTERN_OPEN_HOST_SERVICE,
        detection_delay="real-time",
        response_delay="real-time",
        status=LOOP_WIRED,
        notes=(
            "v8.4: WIRED via new `utils/event_bus.py` (file-backed JSON-lines "
            "event bus with in-memory cache + thread-safe locking + rolling "
            "1000-event retention per topic) + `utils/channels_reliability.py` "
            "PRODUCER (ChannelReliabilityProducer.report_event() emits to "
            "`channel_reliability` topic, supports 5 channel types × 3 severity "
            "tiers) + `utils/smart_alerts.py` CONSUMER (SmartAlertsConsumer."
            "consume(since_event_id=N) subscribes, returns customer-targeted "
            "alerts with URGENT/HIGH/INFO tiers + PUSH/SMS/IN_APP_BANNER "
            "delivery channels + alternative-channel guidance). Closes "
            "campaign's last unwired loop — loops now 100%. Production can "
            "swap event_bus storage to Kafka by reimplementing publish() + "
            "subscribe() — producer/consumer API unchanged."
        ),
    ),

    "L15": FeedbackLoop(
        loop_id="L15",
        name="FLEXCUBE actuals → All engines",
        from_context="External (FLEXCUBE)",
        to_context="(many)",
        from_engine="utils.flexcube_etl_dag",
        to_engine="utils.actuals_engine",
        payload="daily_balance_sheet_and_pl_actuals",
        purpose=(
            "Foundational data flow: FLEXCUBE is the system of record; "
            "all A2Z analytics ultimately depend on FLEXCUBE actuals "
            "being current. The Anti-Corruption Layer prevents FLEXCUBE "
            "schema changes from breaking A2Z engines."
        ),
        pattern=PATTERN_ANTI_CORRUPTION_LAYER,
        detection_delay="daily ETL",
        response_delay="immediate (downstream engines re-run)",
        status=LOOP_WIRED,
        notes="Foundational; predates v7.0.",
    ),
}


# ──────────────────────────────────────────────────────────────────────
# Accessor functions
# ──────────────────────────────────────────────────────────────────────

def list_loops() -> List[FeedbackLoop]:
    """Return all 15 designed loops."""
    return list(FEEDBACK_LOOPS.values())


def loops_by_status() -> Dict[str, List[FeedbackLoop]]:
    """Group loops by wiring status."""
    by_status: Dict[str, List[FeedbackLoop]] = {
        LOOP_WIRED: [],
        LOOP_PARTIAL: [],
        LOOP_DESIGNED_NOT_WIRED: [],
        LOOP_DEPRECATED: [],
    }
    for loop in FEEDBACK_LOOPS.values():
        by_status.setdefault(loop.status, []).append(loop)
    return by_status


def loop_count_by_status() -> Dict[str, int]:
    return {k: len(v) for k, v in loops_by_status().items()}


def wired_pct() -> float:
    """Percentage of designed loops currently wired."""
    counts = loop_count_by_status()
    total = counts.get(LOOP_WIRED, 0) + counts.get(
        LOOP_DESIGNED_NOT_WIRED, 0) + counts.get(LOOP_PARTIAL, 0)
    if total == 0:
        return 0.0
    wired = counts.get(LOOP_WIRED, 0) + 0.5 * counts.get(LOOP_PARTIAL, 0)
    return wired / total * 100.0


def loops_for_engine(engine_name: str) -> List[FeedbackLoop]:
    """Return all loops where this engine is source or target.

    Useful for: engine refactoring (which loops will be affected),
    audit gates (which engines participate in feedback structure).
    """
    return [
        loop for loop in FEEDBACK_LOOPS.values()
        if engine_name in (loop.from_engine, loop.to_engine)
    ]


def loops_by_pattern(pattern: str) -> List[FeedbackLoop]:
    """Return all loops using a specific integration pattern."""
    if pattern not in VALID_PATTERNS:
        return []
    return [loop for loop in FEEDBACK_LOOPS.values()
            if loop.pattern == pattern]


def learning_loops() -> List[FeedbackLoop]:
    """Return only the loops that produce learning (outcomes recalibrate behaviour).

    Per Meadows: learning loops are the highest-value feedback loops
    because they enable adaptation. A2Z has 4 learning loops (L01, L02,
    L08, L12); the others are signal-routing or coordination loops.
    """
    return [loop for loop in FEEDBACK_LOOPS.values() if loop.learning_loop]
