"""utils/cert/championship.py — Championship Readiness Certification.

Per the Enterprise Revival Integrity Validation, Olympic Rehabilitation
& Championship Readiness Framework, this module exists to confirm that
ALL 33 mandatory items across 8 categories tick before React
transformation may begin.

Building blocks:
  - ChampionshipItem: one mandatory checklist item, mapped to one or
    more CertCheck names that prove it
  - CHAMPIONSHIP_CHECKLIST: ordered list of all 33 mandatory items
  - build_championship_full(): a CertProtocol containing every check
    (Olympic full 22 + Championship extras)
  - ChampionshipReport: extends CertReport with explicit checklist_verdicts

Run via:
    from utils.cert.championship import (
        build_championship_full, run_championship_cert)
    report = run_championship_cert()
    print(report.summary_line())
    print(report.checklist_markdown())
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.cert.base import CertCheck, CertProtocol, CertReport
from utils.cert.certifier import Certifier
from utils.cert import checks as olympic
from utils.cert import championship_checks as champ


@dataclass(frozen=True)
class ChampionshipItem:
    """One row of the mandatory Olympic Readiness Checklist."""
    item_id: str                # e.g. "REV-01"
    category: str               # "Revival Integrity", etc.
    label: str                  # short description
    rationale: str              # why this item matters
    check_names: List[str]      # CertCheck names that prove it
    notes: str = ""             # additional context (mapping rationale)


# ─── The 33 mandatory checklist items ───────────────────────────────


CHAMPIONSHIP_CHECKLIST: List[ChampionshipItem] = [
    # ═══ Revival Integrity (4) ═══
    ChampionshipItem(
        item_id="REV-01",
        category="Revival Integrity",
        label="All revived modules remain healthy",
        rationale=(
            "Every previously-built organ must still pass its audit "
            "gate. Locked behind 404 gates in scripts/audit.py."
        ),
        check_names=["championship.all_audit_gates_pass"],
    ),
    ChampionshipItem(
        item_id="REV-02",
        category="Revival Integrity",
        label="No regression detected",
        rationale=(
            "G162 baseline (4022 expected violations) must hold "
            "exactly — any drift means new regression."
        ),
        check_names=["championship.g162_baseline_zero_drift"],
    ),
    ChampionshipItem(
        item_id="REV-03",
        category="Revival Integrity",
        label="No silent failures exist",
        rationale=(
            "G330 silent-degradation guard catches degradations that "
            "would otherwise pass other gates."
        ),
        check_names=["championship.no_silent_degradation"],
    ),
    ChampionshipItem(
        item_id="REV-04",
        category="Revival Integrity",
        label="No cross-organ deterioration",
        rationale=(
            "Cascade BSC 360 harmony must remain 100% with zero "
            "critical issues across 13 organs."
        ),
        check_names=["championship.cascade_360_harmony_100pct"],
    ),

    # ═══ Digital Twin Integrity (4) ═══
    ChampionshipItem(
        item_id="DT-01",
        category="Digital Twin Integrity",
        label="Virtual Bank fully operational",
        rationale=(
            "All 8 simulator organs (channels/scenarios/chaos/macro/"
            "simclock/ml/agents/arena) present and operational."
        ),
        check_names=["championship.virtual_bank_fully_operational",
                     "channels.seven_registered"],
    ),
    ChampionshipItem(
        item_id="DT-02",
        category="Digital Twin Integrity",
        label="Simulation realism validated",
        rationale=(
            "Kenya 2026 baseline values within realistic ranges + "
            "OU evolution deterministic + shock preserves spreads."
        ),
        check_names=["macro.kenya_baseline_realistic",
                     "macro.evolution_seed_deterministic",
                     "macro.shock_preserves_spreads"],
    ),
    ChampionshipItem(
        item_id="DT-03",
        category="Digital Twin Integrity",
        label="Scenario engines stable",
        rationale=(
            "100 scenarios registered + sample scenario runs without "
            "crashing."
        ),
        check_names=["scenarios.one_hundred_registered",
                     "scenarios.run_sample"],
    ),
    ChampionshipItem(
        item_id="DT-04",
        category="Digital Twin Integrity",
        label="Synthetic data isolation preserved",
        rationale=(
            "All simulator outputs land under data/ subdirectories, "
            "never contaminating other repos or /home."
        ),
        check_names=["championship.synthetic_data_isolation"],
    ),

    # ═══ Enterprise Harmony (4) ═══
    ChampionshipItem(
        item_id="HARM-01",
        category="Enterprise Harmony",
        label="Cross-module synchronization operational",
        rationale=(
            "Cascade BSC 360 audit confirms all stages pass with "
            "perfect harmony — same metric as REV-04 but framed for "
            "cross-module sync."
        ),
        check_names=["championship.integration_ecosystem_harmonized"],
    ),
    ChampionshipItem(
        item_id="HARM-02",
        category="Enterprise Harmony",
        label="KPI intelligence flow validated",
        rationale=(
            "KPI library has the canonical 35 KPIs across 4 pillars "
            "(Financial/Customer/Operational/People&Learning)."
        ),
        check_names=["championship.kpi_library_structure"],
    ),
    ChampionshipItem(
        item_id="HARM-03",
        category="Enterprise Harmony",
        label="Workflow circulation healthy",
        rationale=(
            "Workflow engine + 4 named workflows (credit, "
            "reconciliation, disciplinary, procurement) importable."
        ),
        check_names=["championship.workflow_engine_present"],
    ),
    ChampionshipItem(
        item_id="HARM-04",
        category="Enterprise Harmony",
        label="Enterprise observability active",
        rationale=(
            "Event bus carries telemetry from chaos + macro + agent "
            "organs simultaneously."
        ),
        check_names=["eventbus.emit_and_query",
                     "championship.event_bus_cross_organ_lineage"],
    ),

    # ═══ Financial & Regulatory Integrity (5) ═══
    ChampionshipItem(
        item_id="REG-01",
        category="Financial & Regulatory Integrity",
        label="IFRS compliant",
        rationale=(
            "IFRS 7 disclosures + IFRS 9 classification + provisions "
            "+ asset impairment + accruals synthesizer all importable."
        ),
        check_names=["championship.ifrs_modules_present"],
    ),
    ChampionshipItem(
        item_id="REG-02",
        category="Financial & Regulatory Integrity",
        label="CBK compliant",
        rationale=(
            "CBK regulatory reporting + compliance actuals engine + "
            "AML monitoring all importable."
        ),
        check_names=["championship.cbk_compliance_modules_present"],
    ),
    ChampionshipItem(
        item_id="REG-03",
        category="Financial & Regulatory Integrity",
        label="KRA compliant",
        rationale="KRA tax compliance modules importable.",
        check_names=["championship.kra_tax_compliance_present"],
    ),
    ChampionshipItem(
        item_id="REG-04",
        category="Financial & Regulatory Integrity",
        label="Labour law compliant",
        rationale=(
            "HR engine + leave management + staff exit + onboarding "
            "modules all importable (constitutional employment rights)."
        ),
        check_names=["championship.labour_law_hr_modules_present"],
    ),
    ChampionshipItem(
        item_id="REG-05",
        category="Financial & Regulatory Integrity",
        label="Financial calculations validated",
        rationale=(
            "Treasury spreads preserved under shocks + ML regressor "
            "recovers known coefficients (proxy for numeric correctness)."
        ),
        check_names=["championship.financial_calculations_validated"],
    ),

    # ═══ Resilience & Conditioning (4) ═══
    ChampionshipItem(
        item_id="RES-01",
        category="Resilience & Conditioning",
        label="Chaos testing passed",
        rationale=(
            "Chaos library activates AND blocks 10/10 transactions "
            "during outage window."
        ),
        check_names=["championship.chaos_testing_passed",
                     "channels.chaos_outage_blocks"],
    ),
    ChampionshipItem(
        item_id="RES-02",
        category="Resilience & Conditioning",
        label="Stress testing passed",
        rationale=(
            "Three simultaneous chaos events + macro shock all "
            "co-exist and propagate correctly."
        ),
        check_names=["championship.stress_multi_chaos_concurrent"],
    ),
    ChampionshipItem(
        item_id="RES-03",
        category="Resilience & Conditioning",
        label="Recovery mechanisms validated",
        rationale=(
            "Channels recover automatically after chaos windows expire."
        ),
        check_names=["championship.recovery_mechanisms_validated",
                     "chaos.window_expires"],
    ),
    ChampionshipItem(
        item_id="RES-04",
        category="Resilience & Conditioning",
        label="Long-duration endurance validated",
        rationale=(
            "30-day clock advance with calendar events firing + "
            "all 12 drills × 3 repeats (36 runs) pass with stable "
            "trajectory digests."
        ),
        check_names=["championship.long_duration_30_days",
                     "championship.endurance_drill_batch_three_repeats"],
    ),

    # ═══ AI & Intelligence Readiness (4) ═══
    ChampionshipItem(
        item_id="AI-01",
        category="AI & Intelligence Readiness",
        label="ML systems stable",
        rationale=(
            "SimpleClassifier converges on linearly-separable + "
            "SimpleRegressor recovers known coefficients + seed-"
            "deterministic training."
        ),
        check_names=["ml.classifier_learns", "ml.regressor_recovers",
                     "ml.classifier_seed_deterministic"],
    ),
    ChampionshipItem(
        item_id="AI-02",
        category="AI & Intelligence Readiness",
        label="LLM systems validated",
        rationale=(
            "Agent framework is LLM-agnostic via AgentPolicy interface. "
            "15 tools across 6 categories + 3 reference policies "
            "validated. LLM-backed policies plug in via subclass with "
            "no other changes — same trajectory schema, same budget, "
            "same event emission."
        ),
        check_names=["championship.llm_agent_infrastructure_validated",
                     "agents.registry_15_tools"],
    ),
    ChampionshipItem(
        item_id="AI-03",
        category="AI & Intelligence Readiness",
        label="Drift detection operational",
        rationale=(
            "trajectory_digest is SHA-256 over canonical step sequence; "
            "same drill twice -> same digest. Any drift in behaviour "
            "surfaces as digest mismatch via DrillLedger.compare_runs."
        ),
        check_names=["championship.drift_detection_operational",
                     "arena.trajectory_digest_deterministic"],
    ),
    ChampionshipItem(
        item_id="AI-04",
        category="AI & Intelligence Readiness",
        label="Explainability validated",
        rationale=(
            "SimpleClassifier weights inspectable. ModelMetrics "
            "provides accuracy/precision/recall/f1 attribution. ML "
            "model registry stores dataset_fingerprint provenance."
        ),
        check_names=["championship.explainability_validated"],
    ),

    # ═══ Training Arena Readiness (4) ═══
    ChampionshipItem(
        item_id="TRAIN-01",
        category="Training Arena Readiness",
        label="Training simulations operational",
        rationale=(
            "DrillRunner + 12-drill library + DrillLedger end-to-end "
            "in one batch."
        ),
        check_names=["championship.training_simulations_operational",
                     "arena.twelve_drills_pass"],
    ),
    ChampionshipItem(
        item_id="TRAIN-02",
        category="Training Arena Readiness",
        label="Scenario replay functional",
        rationale=(
            "Drill trajectories persisted to disk and replay "
            "deterministically — same drill + same policy -> identical "
            "trajectory digest."
        ),
        check_names=["championship.scenario_replay_functional"],
    ),
    ChampionshipItem(
        item_id="TRAIN-03",
        category="Training Arena Readiness",
        label="Coaching systems active",
        rationale=(
            "DrillOracle.failure_reasons returns structured coaching "
            "messages naming exactly which conditions were missed "
            "(min_steps, required_tool_calls, must_observe_chaos, etc)."
        ),
        check_names=["championship.coaching_systems_active"],
    ),
    ChampionshipItem(
        item_id="TRAIN-04",
        category="Training Arena Readiness",
        label="Role-based simulation validated",
        rationale=(
            "12 drills span 5 operational role contexts: channel "
            "operations, macro/treasury observation, EOM branch ops, "
            "credit/ML, and executive cascade response."
        ),
        check_names=["championship.role_based_simulation_validated"],
    ),

    # ═══ React Readiness (4) ═══
    ChampionshipItem(
        item_id="UI-01",
        category="React Readiness",
        label="Backend elite-grade stable",
        rationale=(
            "olympic_full battery (22 checks across 10 organs) all "
            "pass simultaneously."
        ),
        check_names=["championship.backend_elite_grade_stable"],
    ),
    ChampionshipItem(
        item_id="UI-02",
        category="React Readiness",
        label="APIs production-ready",
        rationale=(
            "utils.api module importable with FastAPI app/router or "
            "endpoint callables exposed."
        ),
        check_names=["championship.apis_production_ready"],
    ),
    ChampionshipItem(
        item_id="UI-03",
        category="React Readiness",
        label="FastAPI architecture validated",
        rationale=(
            "14+ api_*.py modules importable and parseable. Verified "
            "by importing each utils/api*.py file."
        ),
        check_names=["championship.fastapi_architecture_validated"],
    ),
    ChampionshipItem(
        item_id="UI-04",
        category="React Readiness",
        label="Integration ecosystem harmonized",
        rationale=(
            "No circular imports across simulator + cert + arena + "
            "agents + ml + cascade engines. Cascade 360 harmony at "
            "100% confirms cross-organ wiring sound."
        ),
        check_names=["championship.no_circular_imports",
                     "championship.integration_ecosystem_harmonized"],
    ),
]


@dataclass
class ChampionshipReport:
    """Wraps a CertReport with explicit per-item verdicts."""
    cert_report: CertReport
    checklist_verdicts: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Championship passes iff every mandatory item ticks."""
        return all(v.get("passed", False)
                   for v in self.checklist_verdicts.values())

    @property
    def items_passed(self) -> int:
        return sum(1 for v in self.checklist_verdicts.values()
                   if v.get("passed", False))

    @property
    def items_total(self) -> int:
        return len(self.checklist_verdicts)

    def summary_line(self) -> str:
        flag = "🏆 CHAMPIONSHIP READY" if self.passed else "✗ NOT READY"
        return (
            f"{flag} - "
            f"{self.items_passed}/{self.items_total} mandatory items "
            f"ticked; {self.cert_report.passed_checks}/"
            f"{self.cert_report.total_checks} underlying checks pass; "
            f"duration={self.cert_report.duration_seconds:.1f}s"
        )

    def checklist_markdown(self) -> str:
        """Generate the comprehensive markdown report grouped by category."""
        lines: List[str] = []
        lines.append("# Championship Readiness Report")
        lines.append("")
        lines.append(self.summary_line())
        lines.append("")
        lines.append(
            f"- Started: {self.cert_report.started_at}"
        )
        lines.append(
            f"- Finished: {self.cert_report.finished_at}"
        )
        lines.append(
            f"- Underlying check pass rate: "
            f"{self.cert_report.passed_checks}/"
            f"{self.cert_report.total_checks} "
            f"({self.cert_report.pass_rate*100:.1f}%)"
        )
        lines.append(
            f"- Critical failures: {self.cert_report.critical_failures}"
        )
        lines.append("")
        # Category groupings
        cats_seen: List[str] = []
        for item in CHAMPIONSHIP_CHECKLIST:
            if item.category not in cats_seen:
                cats_seen.append(item.category)
        for cat in cats_seen:
            items_in_cat = [it for it in CHAMPIONSHIP_CHECKLIST
                             if it.category == cat]
            passed_in_cat = sum(
                1 for it in items_in_cat
                if self.checklist_verdicts.get(it.item_id, {})
                  .get("passed", False)
            )
            lines.append(
                f"## {cat} "
                f"({passed_in_cat}/{len(items_in_cat)})"
            )
            lines.append("")
            for item in items_in_cat:
                verdict = self.checklist_verdicts.get(item.item_id, {})
                tick = "✅" if verdict.get("passed", False) else "❌"
                lines.append(
                    f"- {tick} **{item.item_id} — {item.label}**"
                )
                lines.append(f"   - {item.rationale}")
                lines.append(
                    f"   - Backed by: "
                    f"`{', '.join(item.check_names)}`"
                )
                evidence = verdict.get("evidence", "")
                if evidence:
                    lines.append(f"   - Evidence: {evidence}")
                if not verdict.get("passed", False):
                    why = verdict.get("why_failed", "")
                    if why:
                        lines.append(f"   - Why failed: {why}")
            lines.append("")
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "items_passed": self.items_passed,
            "items_total": self.items_total,
            "summary": self.summary_line(),
            "checklist_verdicts": self.checklist_verdicts,
            "cert_report": self.cert_report.to_dict(),
        }


def build_championship_full() -> CertProtocol:
    """Bundle Olympic full + all Championship-specific checks."""
    p = CertProtocol(
        name="championship_full",
        description=(
            "Full Championship Readiness battery covering all 33 "
            "mandatory items across 8 phases. Must be 33/33 passing "
            "before React transformation may begin."
        ),
    )

    # ─── Olympic baseline (22 checks from olympic_full) ─────────────
    # channels
    p.add(CertCheck(name="channels.seven_registered", organ="channels",
                      fn=olympic.check_channels_seven_registered))
    p.add(CertCheck(name="channels.seed_deterministic", organ="channels",
                      fn=olympic.check_channels_seed_deterministic))
    p.add(CertCheck(name="channels.chaos_outage_blocks", organ="channels",
                      fn=olympic.check_channels_chaos_outage_blocks))
    # scenarios
    p.add(CertCheck(name="scenarios.one_hundred_registered",
                      organ="scenarios",
                      fn=olympic.check_scenarios_one_hundred_registered))
    p.add(CertCheck(name="scenarios.run_sample", organ="scenarios",
                      fn=olympic.check_scenarios_run_a_sample,
                      critical=False))
    # chaos
    p.add(CertCheck(name="chaos.library_size_25", organ="chaos",
                      fn=olympic.check_chaos_library_size))
    p.add(CertCheck(name="chaos.window_expires", organ="chaos",
                      fn=olympic.check_chaos_window_expires))
    # macro
    p.add(CertCheck(name="macro.kenya_baseline_realistic",
                      organ="macro",
                      fn=olympic.check_macro_kenya_baseline_realistic))
    p.add(CertCheck(name="macro.evolution_seed_deterministic",
                      organ="macro",
                      fn=olympic.check_macro_evolution_seed_deterministic))
    p.add(CertCheck(name="macro.shock_preserves_spreads",
                      organ="macro",
                      fn=olympic.check_macro_shock_preserves_spreads))
    # simclock
    p.add(CertCheck(name="simclock.set_and_advance", organ="simclock",
                      fn=olympic.check_simclock_set_and_advance))
    p.add(CertCheck(name="simclock.tick_scheduler_fires",
                      organ="simclock",
                      fn=olympic.check_tick_scheduler_fires_callbacks))
    # ml
    p.add(CertCheck(name="ml.classifier_learns",
                      organ="ml",
                      fn=olympic.check_ml_classifier_learns_synthetic))
    p.add(CertCheck(name="ml.regressor_recovers", organ="ml",
                      fn=olympic.check_ml_regressor_recovers_linear))
    p.add(CertCheck(name="ml.classifier_seed_deterministic", organ="ml",
                      fn=olympic.check_ml_classifier_seed_deterministic))
    # agents
    p.add(CertCheck(name="agents.registry_15_tools", organ="agents",
                      fn=olympic.check_agents_default_registry_15_tools))
    p.add(CertCheck(name="agents.random_seed_deterministic", organ="agents",
                      fn=olympic.check_agents_random_policy_deterministic))
    p.add(CertCheck(name="agents.budget_enforced", organ="agents",
                      fn=olympic.check_agents_budget_enforced))
    # arena
    p.add(CertCheck(name="arena.twelve_drills_pass", organ="arena",
                      fn=olympic.check_arena_twelve_drills_pass))
    p.add(CertCheck(name="arena.trajectory_digest_deterministic",
                      organ="arena",
                      fn=olympic.check_arena_trajectory_digest_deterministic))
    # event bus
    p.add(CertCheck(name="eventbus.emit_and_query", organ="eventbus",
                      fn=olympic.check_event_bus_emits_and_queries))
    # cascade 360
    p.add(CertCheck(name="cascade_360.harmony_preserved",
                      organ="cascade_360",
                      fn=olympic.check_360_harmony))

    # ─── Championship-specific checks (29 extras) ───────────────────
    # C1 Revival Integrity
    p.add(CertCheck(name="championship.all_audit_gates_pass",
                      organ="revival",
                      fn=champ.check_all_audit_gates_pass,
                      timeout_seconds=600))
    p.add(CertCheck(name="championship.g162_baseline_zero_drift",
                      organ="revival",
                      fn=champ.check_g162_baseline_zero_drift))
    p.add(CertCheck(name="championship.no_silent_degradation",
                      organ="revival",
                      fn=champ.check_no_silent_degradation))
    p.add(CertCheck(name="championship.cascade_360_harmony_100pct",
                      organ="revival",
                      fn=champ.check_cascade_360_harmony_100pct))
    # C2 Digital Twin
    p.add(CertCheck(name="championship.virtual_bank_fully_operational",
                      organ="digital_twin",
                      fn=champ.check_virtual_bank_fully_operational))
    p.add(CertCheck(name="championship.synthetic_data_isolation",
                      organ="digital_twin",
                      fn=champ.check_synthetic_data_isolation))
    # C3 Harmony
    p.add(CertCheck(name="championship.kpi_library_structure",
                      organ="harmony",
                      fn=champ.check_kpi_library_structure))
    p.add(CertCheck(name="championship.workflow_engine_present",
                      organ="harmony",
                      fn=champ.check_workflow_engine_present))
    p.add(CertCheck(name="championship.event_bus_cross_organ_lineage",
                      organ="harmony",
                      fn=champ.check_event_bus_cross_organ_lineage))
    # C4 Regulatory
    p.add(CertCheck(name="championship.ifrs_modules_present",
                      organ="regulatory",
                      fn=champ.check_ifrs_modules_present))
    p.add(CertCheck(name="championship.cbk_compliance_modules_present",
                      organ="regulatory",
                      fn=champ.check_cbk_compliance_modules_present))
    p.add(CertCheck(name="championship.kra_tax_compliance_present",
                      organ="regulatory",
                      fn=champ.check_kra_tax_compliance_present))
    p.add(CertCheck(name="championship.labour_law_hr_modules_present",
                      organ="regulatory",
                      fn=champ.check_labour_law_hr_modules_present))
    p.add(CertCheck(name="championship.financial_calculations_validated",
                      organ="regulatory",
                      fn=champ.check_financial_calculations_validated))
    # C5 Resilience
    p.add(CertCheck(name="championship.chaos_testing_passed",
                      organ="resilience",
                      fn=champ.check_chaos_testing_passed))
    p.add(CertCheck(name="championship.stress_multi_chaos_concurrent",
                      organ="resilience",
                      fn=champ.check_stress_multi_chaos_concurrent))
    p.add(CertCheck(name="championship.recovery_mechanisms_validated",
                      organ="resilience",
                      fn=champ.check_recovery_mechanisms_validated))
    p.add(CertCheck(name="championship.endurance_drill_batch_three_repeats",
                      organ="resilience",
                      fn=champ.check_endurance_drill_batch_three_repeats,
                      timeout_seconds=300))
    p.add(CertCheck(name="championship.long_duration_30_days",
                      organ="resilience",
                      fn=champ.check_long_duration_30_days))
    # C6 AI
    p.add(CertCheck(name="championship.drift_detection_operational",
                      organ="ai",
                      fn=champ.check_drift_detection_operational))
    p.add(CertCheck(name="championship.explainability_validated",
                      organ="ai",
                      fn=champ.check_explainability_validated))
    p.add(CertCheck(name="championship.agent_can_use_ml_model",
                      organ="ai",
                      fn=champ.check_agent_can_use_ml_model))
    p.add(CertCheck(name="championship.llm_agent_infrastructure_validated",
                      organ="ai",
                      fn=champ.check_llm_agent_infrastructure_validated))
    # C7 Training
    p.add(CertCheck(name="championship.training_simulations_operational",
                      organ="training",
                      fn=champ.check_training_simulations_operational,
                      timeout_seconds=120))
    p.add(CertCheck(name="championship.scenario_replay_functional",
                      organ="training",
                      fn=champ.check_scenario_replay_functional))
    p.add(CertCheck(name="championship.coaching_systems_active",
                      organ="training",
                      fn=champ.check_coaching_systems_active))
    p.add(CertCheck(name="championship.role_based_simulation_validated",
                      organ="training",
                      fn=champ.check_role_based_simulation_validated))
    # C8 React readiness
    p.add(CertCheck(name="championship.fastapi_architecture_validated",
                      organ="react_readiness",
                      fn=champ.check_fastapi_architecture_validated))
    p.add(CertCheck(name="championship.apis_production_ready",
                      organ="react_readiness",
                      fn=champ.check_apis_production_ready))
    p.add(CertCheck(name="championship.no_circular_imports",
                      organ="react_readiness",
                      fn=champ.check_no_circular_imports))
    p.add(CertCheck(name="championship.backend_elite_grade_stable",
                      organ="react_readiness",
                      fn=champ.check_backend_elite_grade_stable,
                      timeout_seconds=180))
    p.add(CertCheck(name="championship.integration_ecosystem_harmonized",
                      organ="react_readiness",
                      fn=champ.check_integration_ecosystem_harmonized))
    return p


def run_championship_cert(*, reports_dir: Optional[Path] = None,
                            ) -> ChampionshipReport:
    """Run the full championship battery and produce a ChampionshipReport."""
    protocol = build_championship_full()
    certifier = Certifier(reports_dir=reports_dir)
    cert_report = certifier.run(protocol)

    # Build outcome name -> outcome map for fast lookup
    outcome_by_name: Dict[str, Any] = {
        o.name: o for o in cert_report.outcomes
    }

    # Map each mandatory item to its verdict
    checklist_verdicts: Dict[str, Dict[str, Any]] = {}
    for item in CHAMPIONSHIP_CHECKLIST:
        # Item ticks iff EVERY backing check passes
        backing_outcomes = [outcome_by_name.get(n) for n in item.check_names]
        missing = [n for n, o in zip(item.check_names, backing_outcomes)
                    if o is None]
        if missing:
            checklist_verdicts[item.item_id] = {
                "passed": False,
                "evidence": "",
                "why_failed": f"backing check(s) not in protocol: {missing}",
                "backing_outcomes": [],
            }
            continue
        passed = all(o.passed for o in backing_outcomes if o is not None)
        evidence_parts: List[str] = []
        why_parts: List[str] = []
        for o in backing_outcomes:
            if o is None:
                continue
            if o.passed:
                evidence_parts.append(f"`{o.name}`: {o.note or 'ok'}")
            else:
                why_parts.append(
                    f"`{o.name}` failed: "
                    f"{o.note or o.error[:200] or '(no detail)'}"
                )
        checklist_verdicts[item.item_id] = {
            "passed": passed,
            "evidence": " | ".join(evidence_parts) if passed else "",
            "why_failed": " | ".join(why_parts) if not passed else "",
            "backing_outcomes": [o.to_dict() for o in backing_outcomes
                                  if o is not None],
        }

    report = ChampionshipReport(
        cert_report=cert_report,
        checklist_verdicts=checklist_verdicts,
    )

    # Persist comprehensive championship JSON beside the cert JSON
    try:
        stamp = cert_report.started_at.replace(":", "-").replace(".", "-")
        out_dir = reports_dir or (Path(__file__).resolve().parent.parent.parent
                                    / "data" / "cert_reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"championship_full_{stamp}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
    except Exception:
        pass

    return report


__all__ = [
    "ChampionshipItem", "ChampionshipReport",
    "CHAMPIONSHIP_CHECKLIST",
    "build_championship_full", "run_championship_cert",
]
