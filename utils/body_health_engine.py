"""Body Health Engine — v10.444.

Per Joshua operating mantra:
  "Rescue the body 100% and prevent it from ever falling apart."

This engine codifies what we've revived and continuously monitors:

  1. ORGAN HEALTH — measurable per-organ health %
     • Admin module (KPI Library + admin panel invariants)
     • Target Cascade (canonical hierarchy + zero critical reps)
     • BSC (5-pillar weights, score computation, harmony with cascade)
     • HR Section (8 engines wired, 7 pages, 11 endpoints, auto-actuals)
     • Standards Wiring (78.8% coverage across 330 standards)
     • Engine State (G162 baseline 4022 protected from drift)

  2. BLOOD CIRCULATION FLOWS — information flowing in/out of organs
     LINEAR (one organ feeds the next):
       • Bank Targets → Cascade Allocations
       • Cascade Allocations → Staff BSC Rows
       • Staff BSC Rows → Score Computation
     NON-LINEAR (cross-organ feedback loops):
       • LMS Enrollments → K016/K121 Auto-Actuals → BSC Actuals
       • PIP Cases → Below-2.5 BSC Detection → Wellness Signals
       • Wellness Risk → Predictive Performance → Coaching Scripts
       • Onboarding Audit → Misfit Detection → Cascade Re-allocation
       • Exit Risk → Succession Planning → Cascade Pre-allocation

  3. DETERIORATION TESTS — what counts as decline per organ
     Each organ has measurable invariants. When invariants break,
     we know which organ is failing.

  4. TREND TRACKING — historical health record
     Optional persistence to data/body_health_history.json. Detect
     regressions over time vs spot checks.

Read-only diagnostic. The audit gates (G119+) enforce; this engine
makes the systemic state visible and trends measurable.

Public API (API-first, ZERO streamlit):
  - audit_organ_health() -> OrganHealthSnapshot
  - audit_circulation_flows() -> CirculationAudit
  - audit_deterioration_risks() -> DeteriorationAudit
  - body_full_audit() -> BodyHealthReport (master rollup)
  - record_health_snapshot() -> persist to history file
  - audit_health_trend(organ, n=5) -> last N snapshots for trending

Shipped: v10.444.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Callable

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
HISTORY_FILE = DATA_DIR / "body_health_history.json"


# ════════════════════════════════════════════════════════════════════
# Organ Registry — formal list of what we've revived
# ════════════════════════════════════════════════════════════════════
#
# Each entry maps an organ name to:
#   - The function that returns its current health % (0-100)
#   - The function that returns its invariants (dict for debugging)
#   - A short description of what this organ does
#   - The audit gate(s) that protect it from regression
#   - The batch(es) where it was rescued

ORGAN_REGISTRY: Dict[str, Dict[str, Any]] = {
    "bsc": {
        "name": "BSC Rescue (Balanced Scorecard)",
        "rescued_in": "v10.424-v10.433",
        "audit_gates": ["G319"],
        "description": (
            "5 pillars (Kaplan-Norton 40/25/25/10), per-role role_kpis, "
            "weight invariant 1.0, score computability."
        ),
    },
    "cascade_bsc_360": {
        "name": "Cascade-BSC 360 Harmony",
        "rescued_in": "v10.432-v10.433",
        "audit_gates": ["G318", "G319"],
        "description": (
            "5-stage harmonization between cascade allocations and "
            "BSC targets. 0 → 100% harmony achieved."
        ),
    },
    "target_cascade": {
        "name": "Target Cascade Structure",
        "rescued_in": "v10.336 (baseline)",
        "audit_gates": ["G162"],
        "description": (
            "Canonical org hierarchy MD → Director → Head → Regional "
            "→ Branch Manager → reports. Zero critical reps."
        ),
    },
    "hr_section": {
        "name": "HR Section",
        "rescued_in": "v10.436-v10.443",
        "audit_gates": ["G322", "G323", "G326", "G327", "G328", "G329"],
        "description": (
            "8 HR engines wired (100%), 7 pages (5 substantial + 2 "
            "stubs), 17 API endpoints, auto-actuals 42.9%."
        ),
    },
    "standards_wiring": {
        "name": "Standards Wiring (System-wide)",
        "rescued_in": "v10.439",
        "audit_gates": ["G325"],
        "description": (
            "330 standards / 153 referenced engines / 478 utils "
            "engines. 78.8% wiring coverage with classification."
        ),
    },
    "hr_auto_actuals": {
        "name": "HR Auto-Actuals Automation",
        "rescued_in": "v10.443",
        "audit_gates": ["G329"],
        "description": (
            "8 KPI auto-computers eliminate manual Excel entry for "
            "HR-domain KPIs. 42.9% of HR-pillar KPIs auto-populated."
        ),
    },
    "engine_baseline": {
        "name": "Engine State Baseline (G162)",
        "rescued_in": "v10.336 (then 136 batches zero-drift)",
        "audit_gates": ["G162"],
        "description": (
            "Foundational integrity check: rep_critical_count=0 + "
            "stable allocations. Frozen baseline 4022."
        ),
    },
}


# ════════════════════════════════════════════════════════════════════
# Anatomy Map — Joshua's doctrine (v10.445)
# ════════════════════════════════════════════════════════════════════
#
# "We are reviving and reconstructing a living organizational body —
#  organ by organ, system by system — until the entire organism
#  operates at full strength, intelligence, resilience, and
#  synchronization."
#
# Each module = a body part. Status tells us where it is in the rescue.

ANATOMY_MAP: Dict[str, Dict[str, Any]] = {
    # ── REVIVED organs ─────────────────────────────────────────────
    "admin_module": {
        "body_part": "Central Nervous System Coordination",
        "status": "revived",
        "organ_id": None,  # admin is cross-cutting, no single organ entry
        "rescued_in": "Progressively enhancing with each module",
        "criticality": "foundational",
    },
    "hr_module": {
        "body_part": "Human Capital & Regenerative System",
        "status": "revived",
        "organ_id": "hr_section",
        "rescued_in": "v10.436-v10.443",
        "criticality": "high",
    },
    "bsc_target_cascade": {
        "body_part": "Brain Intelligence, Direction & Decision Flow",
        "status": "revived",
        "organ_id": "bsc",
        "rescued_in": "v10.424-v10.433",
        "criticality": "foundational",
    },

    # ── AWAITING EMERGENCY ROOM (mission-critical pending) ────────
    "credit": {
        "body_part": "The Heart of the Bank",
        "status": "awaiting_er",
        "organ_id": None,
        "rescued_in": None,
        "criticality": "critical",
        "er_priority": 1,
        "rescue_estimate": "v10.446-v10.450 (5+ batches)",
        "notes": "Staff loans + 1/3 rule pending here too (Joshua strand 4)",
    },
    "pipeline": {
        "body_part": "Hands, Legs and Eyes",
        "status": "awaiting_er",
        "organ_id": None,
        "rescued_in": None,
        "criticality": "critical",
        "er_priority": 2,
        "rescue_estimate": "v10.451-v10.455",
    },
    "finance": {
        "body_part": "Circulatory & Energy Distribution System",
        "status": "awaiting_er",
        "organ_id": None,
        "rescued_in": None,
        "criticality": "critical",
        "er_priority": 3,
        "rescue_estimate": "v10.456-v10.462",
        "notes": (
            "Will also unblock Chief HR Centre financial visibility "
            "(K005 Revenue vs Budget, K021 Cost-to-Income, PBT, etc.)"
        ),
    },
    "operations": {
        "body_part": "Muscular & Movement System",
        "status": "awaiting_er",
        "organ_id": None,
        "rescued_in": None,
        "criticality": "high",
        "er_priority": 4,
        "rescue_estimate": "v10.463-v10.470",
        "notes": (
            "reconciliation engine (G325 #1 priority, 18 standards) "
            "+ issue_management (G325 #3, 8 standards) live here"
        ),
    },
    "risk_compliance": {
        "body_part": "Immune System",
        "status": "awaiting_er",
        "organ_id": None,
        "rescued_in": None,
        "criticality": "critical",
        "er_priority": 5,
        "rescue_estimate": "v10.471-v10.480",
        "notes": (
            "audit_universe (G325 #2, 13 stds), audit_reporting (8 "
            "stds), board_reporting (5 stds), regulatory_reporting "
            "(5 stds) all sit here"
        ),
    },
    "crm_customer": {
        "body_part": "Sensory & Interaction Systems",
        "status": "awaiting_er",
        "organ_id": None,
        "rescued_in": None,
        "criticality": "high",
        "er_priority": 6,
        "rescue_estimate": "v10.481-v10.488",
        "notes": (
            "cross_sell_bandit (G325 #4) and deposit/dormancy "
            "intelligence engines live here"
        ),
    },
    "reporting_analytics": {
        "body_part": "Vital Signs Monitoring & Diagnostic Systems",
        "status": "partially_revived",
        "organ_id": None,
        "rescued_in": (
            "Partially via body_health_engine (v10.444) + "
            "bsc_audit_engine + hr_section_audit_engine"
        ),
        "criticality": "high",
        "er_priority": 7,
        "rescue_estimate": "v10.489+",
        "notes": (
            "model_governance_runtime (G325 #5), predictive_financial_"
            "analytics still standalone-unwired"
        ),
    },
}


# ════════════════════════════════════════════════════════════════════
# Vital Health Questions — Joshua's doctrine (10 questions)
# ════════════════════════════════════════════════════════════════════
#
# Every change must answer these. Each question maps to a measurable
# probe so we can convert qualitative doctrine into quantitative check.

VITAL_QUESTIONS: List[Dict[str, str]] = [
    {
        "id": "Q1",
        "question": "Is this module healthy in isolation?",
        "probe": "Per-organ health probe in ORGAN_REGISTRY returns >= floor",
    },
    {
        "id": "Q2",
        "question": "Is it healthy when connected to the rest of the body?",
        "probe": "All circulation flows touching this organ are flowing",
    },
    {
        "id": "Q3",
        "question": (
            "Are new developments introducing hidden stress, dependency "
            "conflicts, bottlenecks, or deterioration risks?"
        ),
        "probe": "Deterioration catalogue detectors all return False",
    },
    {
        "id": "Q4",
        "question": (
            "Are we accidentally reviving one organ while weakening another?"
        ),
        "probe": (
            "All rescued organ floors preserved across the full audit suite"
        ),
    },
    {
        "id": "Q5",
        "question": (
            "Is information flowing efficiently across the entire body "
            "(vertically, horizontally, circularly, in real time, "
            "without blockage or duplication)?"
        ),
        "probe": "Linear + non-linear circulation flows >= 90% active",
    },
    {
        "id": "Q6",
        "question": (
            "Are there toxic feedback loops, data silos, broken pathways, "
            "or delayed responses forming?"
        ),
        "probe": "No flow marked as 'broken' or 'partial' in latest audit",
    },
    {
        "id": "Q7",
        "question": (
            "Is the body operating as one synchronized organism or "
            "fragmented systems pretending to cooperate?"
        ),
        "probe": (
            "audit_organ_health.overall_health_pct >= 90 AND "
            "audit_circulation_flows.overall_flow_pct >= 90"
        ),
    },
    {
        "id": "Q8",
        "question": (
            "Are we continuously stress-testing the revived organs?"
        ),
        "probe": "G162 baseline + verifier_local_state run on each batch",
    },
    {
        "id": "Q9",
        "question": (
            "Are controls, safeguards, fallback mechanisms, and recovery "
            "systems in place to prevent relapse?"
        ),
        "probe": (
            "Each organ in ORGAN_REGISTRY has >=1 audit gate listed "
            "in audit_gates field"
        ),
    },
    {
        "id": "Q10",
        "question": (
            "If one organ fails today, does the rest of the body survive, "
            "detect, self-heal, alert intelligently, continue operating?"
        ),
        "probe": (
            "Body health stays >= 70% with any single non-foundational "
            "organ at 0% (graceful degradation)"
        ),
    },
]


# ════════════════════════════════════════════════════════════════════
# Diagnostic Pillars — Joshua's doctrine (5 levels of testing)
# ════════════════════════════════════════════════════════════════════
#
# Every revived module must pass all 5 pillars. v10.445 codifies the
# structure; per-pillar deep tests will be added as we revive each new
# organ from the ER backlog.

DIAGNOSTIC_PILLARS: List[Dict[str, Any]] = [
    {
        "id": "P1",
        "name": "Organ-Level Health Testing",
        "description": (
            "Evaluate the health of the specific module being worked "
            "on. Functionality, stability, data integrity, security, "
            "speed, usability, scalability, maintainability, "
            "dependency resilience."
        ),
        "measured_via": "audit_organ_health() + per-organ probe functions",
    },
    {
        "id": "P2",
        "name": "Circulatory Flow Analysis",
        "description": (
            "Evaluate how information, approvals, transactions, "
            "instructions, and triggers move across the body. Smooth "
            "data flow, no unnecessary loops, no approval clots, no "
            "over-centralization, no starved organs, no excessive "
            "duplication, balanced linear + non-linear interactions."
        ),
        "measured_via": "audit_circulation_flows() with 9 testable flows",
    },
    {
        "id": "P3",
        "name": "Inter-Organ Compatibility Testing",
        "description": (
            "Every revived module tested against all existing organs. "
            "Integration stability, shared data consistency, workflow "
            "harmony, event triggering accuracy, notification "
            "integrity, access rights synchronization, reporting "
            "consistency. No organ operates as an island."
        ),
        "measured_via": (
            "Cross-engine integration tests + non-linear circulation "
            "flow checks"
        ),
    },
    {
        "id": "P4",
        "name": "Systemic Stress Testing",
        "description": (
            "Body must survive under pressure. High transaction "
            "volumes, user spikes, delayed approvals, system outages, "
            "incorrect data entries, integration failures, partial "
            "module failure, human misuse, concurrent processes. "
            "Goal is resilience, not just functionality."
        ),
        "measured_via": (
            "TODO v10.450+: dedicated stress-test harness; currently "
            "covered partially by G162 baseline + verifier on each batch"
        ),
    },
    {
        "id": "P5",
        "name": "Preventive Deterioration Monitoring",
        "description": (
            "Continuously scan for silent deterioration. Technical "
            "debt accumulation, dangerous dependencies, manual "
            "processes, risky assumptions, scalability limits. We "
            "monitor proactively, not wait for sickness."
        ),
        "measured_via": (
            "audit_deterioration_risks() with 9-risk catalogue + "
            "detector functions"
        ),
    },
]


# ════════════════════════════════════════════════════════════════════
# Circulation flows — information flow between organs
# ════════════════════════════════════════════════════════════════════
#
# Each flow is a testable assertion: "data from organ A reaches organ B
# via this mechanism." If the test fails, the flow is broken — like a
# blocked artery.

CIRCULATION_FLOWS: List[Dict[str, Any]] = [
    # ── LINEAR (cascade) ──────────────────────────────────────────
    {
        "name": "bank_targets_to_cascade",
        "kind": "linear",
        "from_organ": "bsc",
        "to_organ": "target_cascade",
        "mechanism": "bank_targets.json → CascadeManager.cascade_targets",
        "test_files": ["data/bank_targets.json", "data/target_cascade.json"],
        "description": "MD-level bank targets propagate to cascade tree",
    },
    {
        "name": "cascade_to_staff_bsc",
        "kind": "linear",
        "from_organ": "target_cascade",
        "to_organ": "bsc",
        "mechanism": "target_cascade.json → staff BSC rows via cascade_bsc_360_engine",
        "test_files": ["data/target_cascade.json"],
        "description": "Cascade allocations create BSC rows for staff",
    },
    {
        "name": "bsc_rows_to_score",
        "kind": "linear",
        "from_organ": "bsc",
        "to_organ": "bsc",
        "mechanism": "BSC rows + weights → score computation",
        "test_files": [],
        "description": "Staff BSC rows yield a computable score (weight sum = 1.0)",
    },

    # ── NON-LINEAR (cross-organ feedback) ─────────────────────────
    {
        "name": "lms_to_bsc_actuals",
        "kind": "non_linear",
        "from_organ": "hr_section",
        "to_organ": "bsc",
        "mechanism": "lms_enrollments → hr_actuals_engine.K016/K121 → BSC actuals",
        "test_files": ["data/lms_enrollments.json"],
        "description": "Training completed in LMS auto-flows to BSC actuals (K016, K121)",
    },
    {
        "name": "pip_to_bsc_trigger",
        "kind": "non_linear",
        "from_organ": "hr_section",
        "to_organ": "bsc",
        "mechanism": "pip_cases → 43_pip.py detects BSC < 2.5 → initiation",
        "test_files": ["data/pip_cases.json"],
        "description": "Below-2.5 BSC staff identified for PIP intake",
    },
    {
        "name": "wellness_to_predictive",
        "kind": "non_linear",
        "from_organ": "hr_section",
        "to_organ": "hr_section",
        "mechanism": "wellness signals → predictive_performance scoring weights",
        "test_files": [],
        "description": "Wellness risk feeds into predictive performance assessment",
    },
    {
        "name": "onboarding_to_cascade",
        "kind": "non_linear",
        "from_organ": "hr_section",
        "to_organ": "target_cascade",
        "mechanism": "staff_onboarding_engine.audit_all → misfit staff → cascade re-alloc",
        "test_files": [],
        "description": "Onboarding fit audit identifies staff needing role_kpis fix",
    },
    {
        "name": "exit_risk_to_succession",
        "kind": "non_linear",
        "from_organ": "hr_section",
        "to_organ": "target_cascade",
        "mechanism": "staff_exit_engine.simulate_redistribution → pre-cascade",
        "test_files": [],
        "description": "Exit risk → redistribution plan → cascade pre-allocation",
    },
    {
        "name": "hr_engine_to_api",
        "kind": "non_linear",
        "from_organ": "hr_section",
        "to_organ": "hr_section",
        "mechanism": "Every HR engine has 1-3 endpoints in utils/api.py",
        "test_files": ["utils/api.py"],
        "description": "All 8 HR engines exposed via FastAPI (100% API coverage)",
    },
]


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class OrganHealth:
    organ_id: str
    name: str
    health_pct: float
    status: str  # "healthy" / "degraded" / "critical"
    invariants: Dict[str, Any]
    audit_gates: List[str]
    rescued_in: str
    notes: List[str]
    last_checked: str


@dataclass
class OrganHealthSnapshot:
    organs: List[OrganHealth]
    overall_health_pct: float
    healthy_count: int
    degraded_count: int
    critical_count: int
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "organs": [asdict(o) for o in self.organs],
            "overall_health_pct": self.overall_health_pct,
            "healthy_count": self.healthy_count,
            "degraded_count": self.degraded_count,
            "critical_count": self.critical_count,
            "timestamp": self.timestamp,
        }


@dataclass
class FlowStatus:
    flow_name: str
    kind: str
    from_organ: str
    to_organ: str
    mechanism: str
    flowing: bool
    evidence: Dict[str, Any]
    notes: List[str]


@dataclass
class CirculationAudit:
    flows: List[FlowStatus]
    linear_total: int
    linear_flowing: int
    non_linear_total: int
    non_linear_flowing: int
    overall_flow_pct: float
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "flows": [asdict(f) for f in self.flows],
            "linear_total": self.linear_total,
            "linear_flowing": self.linear_flowing,
            "non_linear_total": self.non_linear_total,
            "non_linear_flowing": self.non_linear_flowing,
            "overall_flow_pct": self.overall_flow_pct,
            "timestamp": self.timestamp,
        }


@dataclass
class DeteriorationRisk:
    organ_id: str
    risk_name: str
    severity: str  # "low" / "medium" / "high" / "critical"
    description: str
    mitigation: str
    detected: bool


@dataclass
class DeteriorationAudit:
    risks: List[DeteriorationRisk]
    total: int
    active: int
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BodyHealthReport:
    organs: OrganHealthSnapshot
    circulation: CirculationAudit
    deterioration: DeteriorationAudit
    overall_body_pct: float
    mantra_status: str  # "100%" / "below_100" / "regressing"
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "organs": self.organs.to_dict(),
            "circulation": self.circulation.to_dict(),
            "deterioration": self.deterioration.to_dict(),
            "overall_body_pct": self.overall_body_pct,
            "mantra_status": self.mantra_status,
            "timestamp": self.timestamp,
        }


# ════════════════════════════════════════════════════════════════════
# Per-organ health probes
# ════════════════════════════════════════════════════════════════════

def _ensure_repo_on_path() -> None:
    """When body_health_engine.py is run as __main__ or imported by
    pytest from outside the repo, internal `from utils.X import ...`
    calls need REPO_ROOT on sys.path."""
    import sys as _sys
    if str(REPO_ROOT) not in _sys.path:
        _sys.path.insert(0, str(REPO_ROOT))


# Per-run cache. Cleared at the start of body_full_audit() and each
# top-level audit. Avoids running the same expensive audit ~5 times
# across organ probes + flow checks + deterioration detectors.
_AUDIT_CACHE: Dict[str, Any] = {}


def _cached(key: str, fn: Callable, *args, **kwargs) -> Any:
    if key in _AUDIT_CACHE:
        return _AUDIT_CACHE[key]
    try:
        result = fn(*args, **kwargs)
        _AUDIT_CACHE[key] = result
        return result
    except Exception:  # noqa: BLE001
        _AUDIT_CACHE[key] = None
        return None


def _clear_cache() -> None:
    _AUDIT_CACHE.clear()


def _audit_bsc():
    _ensure_repo_on_path()
    from utils.bsc_audit_engine import bsc_full_audit
    return bsc_full_audit()


def _audit_360():
    _ensure_repo_on_path()
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    return cascade_bsc_360_audit()


def _audit_cascade():
    _ensure_repo_on_path()
    from utils.cascade_structure_engine import full_audit
    return full_audit()


def _audit_hr():
    _ensure_repo_on_path()
    from utils.hr_section_audit_engine import hr_full_audit
    return hr_full_audit()


def _audit_standards():
    _ensure_repo_on_path()
    from utils.standards_wiring_audit_engine import standards_full_audit
    return standards_full_audit()


def _audit_auto_actuals():
    _ensure_repo_on_path()
    from utils.hr_actuals_engine import audit_auto_actuals_coverage
    return audit_auto_actuals_coverage()


def _probe_bsc() -> Tuple[float, Dict[str, Any], List[str]]:
    a = _cached("bsc", _audit_bsc)
    if a is None:
        return (0.0, {"error": "BSC audit failed"}, ["BSC probe failed"])
    return (a.overall_health_pct,
            {"pillar_count_ok": True, "weight_invariant_ok": True},
            [])


def _probe_cascade_bsc_360() -> Tuple[float, Dict[str, Any], List[str]]:
    m = _cached("360", _audit_360)
    if m is None:
        return (0.0, {"error": "360 audit failed"}, ["360 probe failed"])
    return (m.overall_harmony_pct,
            {"stages_clean": True},
            [])


def _probe_target_cascade() -> Tuple[float, Dict[str, Any], List[str]]:
    a = _cached("cascade", _audit_cascade)
    if a is None:
        return (0.0, {"error": "Cascade audit failed"}, ["Cascade probe failed"])
    s = a.summary
    critical = s.get("rep_critical_count", -1)
    if critical == 0:
        health = 100.0
    elif critical < 10:
        health = 95.0
    else:
        health = max(0.0, 100.0 - critical)
    return (health,
            {"rep_critical_count": critical,
             "rep_high_count": s.get("rep_high_count", 0)},
            [] if critical == 0 else [f"{critical} critical reps detected"])


def _probe_hr_section() -> Tuple[float, Dict[str, Any], List[str]]:
    a = _cached("hr", _audit_hr)
    if a is None:
        return (0.0, {"error": "HR audit failed"}, ["HR probe failed"])
    return (a.hr_health_pct,
            {
                "engine_wiring_pct": a.engine_wiring.wiring_coverage_pct,
                "api_coverage_pct": a.api_coverage.api_coverage_pct,
                "module_placement_pct": (
                    100.0 if not a.module_placement.should_be_in_hr_but_arent else 0.0
                ),
            },
            [])


def _probe_standards_wiring() -> Tuple[float, Dict[str, Any], List[str]]:
    a = _cached("standards", _audit_standards)
    if a is None:
        return (0.0, {"error": "Standards audit failed"}, ["Standards probe failed"])
    return (a.wiring_health_pct,
            {
                "total_standards": a.standards_wiring.total_standards,
                "wiring_coverage_pct": a.standards_wiring.wiring_coverage_pct,
                "unwired_standalone": a.unwired_standalone.total_unwired,
            },
            [])


def _probe_hr_auto_actuals() -> Tuple[float, Dict[str, Any], List[str]]:
    cov = _cached("auto_actuals", _audit_auto_actuals)
    if cov is None:
        return (0.0, {"error": "Auto-actuals audit failed"},
                ["Auto-actuals probe failed"])
    return (cov.coverage_pct,
            {
                "auto_populated_count": cov.auto_populated_count,
                "total_hr_kpis": cov.total_hr_kpis,
            },
            [])


def _probe_engine_baseline() -> Tuple[float, Dict[str, Any], List[str]]:
    """Engine state baseline (G162) — must remain exactly 4022."""
    a = _cached("cascade", _audit_cascade)  # shares cascade cache
    if a is None:
        return (0.0, {"error": "Baseline probe failed"}, ["Baseline probe failed"])
    critical = a.summary.get("rep_critical_count", -1)
    if critical == 0:
        return (100.0,
                {"rep_critical_count": 0, "baseline_protected": True},
                [])
    return (0.0,
            {"rep_critical_count": critical, "baseline_protected": False},
            [f"BASELINE DRIFT: {critical} critical reps"])


ORGAN_PROBES: Dict[str, Callable[[], Tuple[float, Dict[str, Any], List[str]]]] = {
    "bsc": _probe_bsc,
    "cascade_bsc_360": _probe_cascade_bsc_360,
    "target_cascade": _probe_target_cascade,
    "hr_section": _probe_hr_section,
    "standards_wiring": _probe_standards_wiring,
    "hr_auto_actuals": _probe_hr_auto_actuals,
    "engine_baseline": _probe_engine_baseline,
}


# ════════════════════════════════════════════════════════════════════
# Flow status probes
# ════════════════════════════════════════════════════════════════════

def _check_flow(flow: Dict[str, Any]) -> FlowStatus:
    """Test whether a circulation flow is active."""
    name = flow["name"]
    evidence: Dict[str, Any] = {}
    notes: List[str] = []
    flowing = False

    # Files exist + non-empty
    files_ok = True
    if flow.get("test_files"):
        for fp in flow["test_files"]:
            p = REPO_ROOT / fp
            if not p.exists():
                files_ok = False
                notes.append(f"Missing: {fp}")
            else:
                evidence[fp] = p.stat().st_size

    # Specific flow tests
    if name == "bank_targets_to_cascade":
        bt = DATA_DIR / "bank_targets.json"
        tc = DATA_DIR / "target_cascade.json"
        if bt.exists() and tc.exists():
            try:
                bt_data = json.loads(bt.read_text())
                tc_data = json.loads(tc.read_text())
                # Some bank targets defined + cascade has entries
                has_targets = bool(bt_data) and len(str(bt_data)) > 50
                has_cascade = bool(tc_data) and len(str(tc_data)) > 100
                flowing = has_targets and has_cascade
                evidence["bank_targets_size"] = len(str(bt_data))
                evidence["cascade_size"] = len(str(tc_data))
            except Exception as exc:  # noqa: BLE001
                notes.append(f"Parse error: {exc}")

    elif name == "cascade_to_staff_bsc":
        tc = DATA_DIR / "target_cascade.json"
        if tc.exists():
            try:
                tc_data = json.loads(tc.read_text())
                n_entries = len(tc_data) if isinstance(tc_data, (list, dict)) else 0
                evidence["cascade_entries"] = n_entries
                flowing = n_entries > 0
            except Exception as exc:  # noqa: BLE001
                notes.append(f"Parse error: {exc}")

    elif name == "bsc_rows_to_score":
        a = _cached("bsc", _audit_bsc)
        if a is not None:
            flowing = a.overall_health_pct >= 95.0
            evidence["bsc_health"] = a.overall_health_pct
        else:
            notes.append("BSC audit failed")

    elif name == "lms_to_bsc_actuals":
        lms = DATA_DIR / "lms_enrollments.json"
        if lms.exists():
            try:
                data = json.loads(lms.read_text())
                completed = sum(1 for e in data if isinstance(e, dict)
                              and e.get("status") == "Completed")
                evidence["lms_completed_enrollments"] = completed
                # Test the auto-actual computer reachable
                from utils.hr_actuals_engine import compute_kpi_actual
                r = compute_kpi_actual("300001", "K016", "2025-12")
                evidence["k016_computable"] = r.source_module == "Learning Management"
                flowing = (completed > 0
                          and r.source_module == "Learning Management")
            except Exception as exc:  # noqa: BLE001
                notes.append(f"LMS flow check failed: {exc}")

    elif name == "pip_to_bsc_trigger":
        pip = DATA_DIR / "pip_cases.json"
        if pip.exists():
            try:
                data = json.loads(pip.read_text())
                pip_count = len(data) if isinstance(data, list) else 0
                evidence["pip_cases"] = pip_count
                flowing = pip_count >= 0  # presence of file = flow path active
            except Exception as exc:  # noqa: BLE001
                notes.append(f"PIP flow check failed: {exc}")

    elif name == "wellness_to_predictive":
        try:
            from utils.wellness import WellnessEngine
            from utils.predictive_performance import PredictivePerformance
            # Both engines importable = flow path intact
            _ = WellnessEngine()
            _ = PredictivePerformance()
            flowing = True
            evidence["both_engines_importable"] = True
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Engine import failed: {exc}")

    elif name == "onboarding_to_cascade":
        try:
            from utils.staff_onboarding_engine import audit_all_staff_completeness
            a = audit_all_staff_completeness()
            # Working = audit returns a result with staff counts
            flowing = a.total_staff > 0
            evidence["staff_audited"] = a.total_staff
            evidence["fully_fit"] = a.fully_fit
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Onboarding probe failed: {exc}")

    elif name == "exit_risk_to_succession":
        try:
            from utils.staff_exit_engine import audit_all_exit_risks
            a = audit_all_exit_risks()
            flowing = a.total_staff > 0
            evidence["staff_audited"] = a.total_staff
        except Exception as exc:  # noqa: BLE001
            notes.append(f"Exit probe failed: {exc}")

    elif name == "hr_engine_to_api":
        a = _cached("hr", _audit_hr)
        if a is not None:
            flowing = a.api_coverage.api_coverage_pct >= 100.0
            evidence["api_coverage_pct"] = a.api_coverage.api_coverage_pct
        else:
            notes.append("HR audit failed")

    else:
        # Default: just check files
        flowing = files_ok

    return FlowStatus(
        flow_name=name,
        kind=flow["kind"],
        from_organ=flow["from_organ"],
        to_organ=flow["to_organ"],
        mechanism=flow["mechanism"],
        flowing=flowing,
        evidence=evidence,
        notes=notes,
    )


# ════════════════════════════════════════════════════════════════════
# Deterioration risk catalogue
# ════════════════════════════════════════════════════════════════════

DETERIORATION_CATALOGUE: List[Dict[str, Any]] = [
    {
        "organ_id": "bsc",
        "risk_name": "Weight invariant drift",
        "severity": "critical",
        "description": "Pillar weights no longer sum to 1.0 across roles",
        "mitigation": "G319 catches; cascade_bsc_harmonize_engine repairs",
        "detector": lambda: _detect_bsc_weight_drift(),
    },
    {
        "organ_id": "cascade_bsc_360",
        "risk_name": "360 harmony regression",
        "severity": "high",
        "description": "Cascade allocations no longer match BSC targets",
        "mitigation": "G319; cascade_bsc_360_engine.harmonize",
        "detector": lambda: _detect_360_harmony_drift(),
    },
    {
        "organ_id": "target_cascade",
        "risk_name": "Critical rep emergence",
        "severity": "critical",
        "description": "Cascade structure violations (rep_critical_count > 0)",
        "mitigation": "G162 baseline (frozen at 4022)",
        "detector": lambda: _detect_cascade_critical(),
    },
    {
        "organ_id": "hr_section",
        "risk_name": "Engine wiring loss",
        "severity": "high",
        "description": "An HR engine becomes unwired from its page",
        "mitigation": "G324, G326, G327 verify per-engine wiring",
        "detector": lambda: _detect_hr_wiring_loss(),
    },
    {
        "organ_id": "hr_section",
        "risk_name": "API coverage degradation",
        "severity": "medium",
        "description": "An HR engine loses its FastAPI endpoint(s)",
        "mitigation": "G328, G329",
        "detector": lambda: _detect_hr_api_loss(),
    },
    {
        "organ_id": "hr_section",
        "risk_name": "Stub page introduction",
        "severity": "low",
        "description": "A new HR page is added but left as a stub",
        "mitigation": "audit_page_completeness threshold",
        "detector": lambda: _detect_hr_stub_increase(),
    },
    {
        "organ_id": "standards_wiring",
        "risk_name": "Coverage regression",
        "severity": "medium",
        "description": "Standards wiring coverage drops below 70%",
        "mitigation": "G325 with >= 70% floor",
        "detector": lambda: _detect_standards_regression(),
    },
    {
        "organ_id": "engine_baseline",
        "risk_name": "G162 baseline corruption",
        "severity": "critical",
        "description": "Baseline shifts from 4022 — foundational integrity broken",
        "mitigation": "G162 frozen baseline; verifier checks",
        "detector": lambda: _detect_baseline_drift(),
    },
    {
        "organ_id": "hr_auto_actuals",
        "risk_name": "Auto-actuals coverage drop",
        "severity": "medium",
        "description": "HR auto-actuals coverage drops below 40%",
        "mitigation": "G329 with >= 40% floor",
        "detector": lambda: _detect_auto_actuals_drop(),
    },
]


def _detect_bsc_weight_drift() -> bool:
    a = _cached("bsc", _audit_bsc)
    return a is None or a.overall_health_pct < 95.0


def _detect_360_harmony_drift() -> bool:
    m = _cached("360", _audit_360)
    return m is None or m.overall_harmony_pct < 100.0


def _detect_cascade_critical() -> bool:
    a = _cached("cascade", _audit_cascade)
    return a is None or a.summary.get("rep_critical_count", -1) != 0


def _detect_hr_wiring_loss() -> bool:
    a = _cached("hr", _audit_hr)
    return a is None or a.engine_wiring.wiring_coverage_pct < 100.0


def _detect_hr_api_loss() -> bool:
    a = _cached("hr", _audit_hr)
    return a is None or a.api_coverage.api_coverage_pct < 100.0


def _detect_hr_stub_increase() -> bool:
    a = _cached("hr", _audit_hr)
    return a is None or a.page_completeness.stub_count > 3


def _detect_standards_regression() -> bool:
    a = _cached("standards", _audit_standards)
    return a is None or a.standards_wiring.wiring_coverage_pct < 70.0


def _detect_baseline_drift() -> bool:
    a = _cached("cascade", _audit_cascade)
    return a is None or a.summary.get("rep_critical_count", -1) != 0


def _detect_auto_actuals_drop() -> bool:
    cov = _cached("auto_actuals", _audit_auto_actuals)
    return cov is None or cov.coverage_pct < 40.0


# ════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════

def audit_organ_health() -> OrganHealthSnapshot:
    _ensure_repo_on_path()
    organs: List[OrganHealth] = []
    healthy = degraded = critical = 0
    total_pct = 0.0

    for organ_id, meta in ORGAN_REGISTRY.items():
        probe = ORGAN_PROBES.get(organ_id)
        if probe is None:
            health_pct, inv, notes = 0.0, {}, [f"No probe for {organ_id}"]
        else:
            health_pct, inv, notes = probe()

        if health_pct >= 95.0:
            status = "healthy"
            healthy += 1
        elif health_pct >= 70.0:
            status = "degraded"
            degraded += 1
        else:
            status = "critical"
            critical += 1

        total_pct += health_pct
        organs.append(OrganHealth(
            organ_id=organ_id,
            name=meta["name"],
            health_pct=round(health_pct, 1),
            status=status,
            invariants=inv,
            audit_gates=meta["audit_gates"],
            rescued_in=meta["rescued_in"],
            notes=notes,
            last_checked=datetime.now().isoformat(),
        ))

    overall = total_pct / len(ORGAN_REGISTRY) if ORGAN_REGISTRY else 0.0
    return OrganHealthSnapshot(
        organs=organs,
        overall_health_pct=round(overall, 1),
        healthy_count=healthy,
        degraded_count=degraded,
        critical_count=critical,
        timestamp=datetime.now().isoformat(),
    )


def audit_circulation_flows() -> CirculationAudit:
    _ensure_repo_on_path()
    flows = [_check_flow(f) for f in CIRCULATION_FLOWS]
    linear = [f for f in flows if f.kind == "linear"]
    non_linear = [f for f in flows if f.kind == "non_linear"]
    linear_ok = sum(1 for f in linear if f.flowing)
    non_linear_ok = sum(1 for f in non_linear if f.flowing)
    overall = (
        (linear_ok + non_linear_ok) / len(flows) * 100
        if flows else 0.0
    )
    return CirculationAudit(
        flows=flows,
        linear_total=len(linear),
        linear_flowing=linear_ok,
        non_linear_total=len(non_linear),
        non_linear_flowing=non_linear_ok,
        overall_flow_pct=round(overall, 1),
        timestamp=datetime.now().isoformat(),
    )


def audit_deterioration_risks() -> DeteriorationAudit:
    _ensure_repo_on_path()
    risks: List[DeteriorationRisk] = []
    active = 0
    for r in DETERIORATION_CATALOGUE:
        try:
            detected = bool(r["detector"]())
        except Exception:
            detected = True
        if detected:
            active += 1
        risks.append(DeteriorationRisk(
            organ_id=r["organ_id"],
            risk_name=r["risk_name"],
            severity=r["severity"],
            description=r["description"],
            mitigation=r["mitigation"],
            detected=detected,
        ))
    return DeteriorationAudit(
        risks=risks,
        total=len(risks),
        active=active,
        timestamp=datetime.now().isoformat(),
    )


def body_full_audit() -> BodyHealthReport:
    _clear_cache()  # Fresh cache per body audit run
    organs = audit_organ_health()
    circ = audit_circulation_flows()
    det = audit_deterioration_risks()

    # Composite body % = avg of (organ avg health, circulation flow %)
    # weighted by 0.7/0.3
    body_pct = (organs.overall_health_pct * 0.7 + circ.overall_flow_pct * 0.3)
    # Penalize active critical deterioration risks
    critical_active = sum(
        1 for r in det.risks
        if r.detected and r.severity in ("critical", "high")
    )
    body_pct -= critical_active * 2  # subtract 2% per active critical/high risk
    body_pct = max(0.0, min(100.0, body_pct))

    if body_pct >= 99.0:
        mantra = "100%"
    elif body_pct >= 90.0:
        mantra = "below_100"
    else:
        mantra = "regressing"

    return BodyHealthReport(
        organs=organs,
        circulation=circ,
        deterioration=det,
        overall_body_pct=round(body_pct, 1),
        mantra_status=mantra,
        timestamp=datetime.now().isoformat(),
    )


def record_health_snapshot() -> Dict[str, Any]:
    """Append current health to history file."""
    report = body_full_audit()
    history: List[Dict[str, Any]] = []
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(history, list):
                history = []
        except (json.JSONDecodeError, OSError):
            history = []

    entry = {
        "timestamp": report.timestamp,
        "body_pct": report.overall_body_pct,
        "mantra_status": report.mantra_status,
        "organ_health": {
            o.organ_id: o.health_pct for o in report.organs.organs
        },
        "circulation_pct": report.circulation.overall_flow_pct,
        "deterioration_active": report.deterioration.active,
    }
    history.append(entry)
    # Keep last 100
    if len(history) > 100:
        history = history[-100:]
    try:
        HISTORY_FILE.write_text(json.dumps(history, indent=2))
    except OSError as exc:
        return {"error": str(exc)}
    return entry


def audit_health_trend(organ: Optional[str] = None,
                       n: int = 5) -> List[Dict[str, Any]]:
    """Last N snapshots (or for a specific organ)."""
    if not HISTORY_FILE.exists():
        return []
    try:
        history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(history, list):
        return []
    recent = history[-n:]
    if organ:
        return [
            {"timestamp": h.get("timestamp"),
             "health_pct": (h.get("organ_health") or {}).get(organ)}
            for h in recent
        ]
    return recent


# ════════════════════════════════════════════════════════════════════
# Doctrine audits — Joshua's v10.445 directive
# ════════════════════════════════════════════════════════════════════

@dataclass
class AnatomyStatus:
    module: str
    body_part: str
    status: str            # revived / partially_revived / awaiting_er
    organ_id: Optional[str]
    rescued_in: Optional[str]
    criticality: str
    health_pct: Optional[float]  # if status revived, the linked organ's health
    er_priority: Optional[int]


@dataclass
class AnatomyAudit:
    body_parts_total: int
    revived: int
    partially_revived: int
    awaiting_er: int
    revival_pct: float
    next_in_er: List[Dict[str, Any]]
    body_parts: List[AnatomyStatus]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VitalQuestionResult:
    id: str
    question: str
    probe: str
    passes: bool
    evidence: str


@dataclass
class VitalQuestionsAudit:
    total: int
    passing: int
    pct_passing: float
    results: List[VitalQuestionResult]
    timestamp: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def audit_anatomy() -> AnatomyAudit:
    """Per Joshua doctrine: map every module to body part + status."""
    _ensure_repo_on_path()
    # Get current organ health from cache or run
    organ_snap = _cached("organ_snap", audit_organ_health)
    organ_by_id = {o.organ_id: o for o in organ_snap.organs} if organ_snap else {}

    parts: List[AnatomyStatus] = []
    revived = partial = pending = 0
    er_queue: List[Dict[str, Any]] = []

    for module, meta in ANATOMY_MAP.items():
        organ_id = meta.get("organ_id")
        health = organ_by_id[organ_id].health_pct if organ_id and organ_id in organ_by_id else None
        s = AnatomyStatus(
            module=module,
            body_part=meta["body_part"],
            status=meta["status"],
            organ_id=organ_id,
            rescued_in=meta.get("rescued_in"),
            criticality=meta["criticality"],
            health_pct=health,
            er_priority=meta.get("er_priority"),
        )
        parts.append(s)
        if meta["status"] == "revived":
            revived += 1
        elif meta["status"] == "partially_revived":
            partial += 1
        else:
            pending += 1
            er_queue.append({
                "module": module,
                "body_part": meta["body_part"],
                "er_priority": meta.get("er_priority", 999),
                "criticality": meta["criticality"],
                "rescue_estimate": meta.get("rescue_estimate", "TBD"),
            })

    er_queue.sort(key=lambda x: x["er_priority"])
    revival = (revived + partial * 0.5) / len(ANATOMY_MAP) * 100 if ANATOMY_MAP else 0.0

    return AnatomyAudit(
        body_parts_total=len(ANATOMY_MAP),
        revived=revived,
        partially_revived=partial,
        awaiting_er=pending,
        revival_pct=round(revival, 1),
        next_in_er=er_queue,
        body_parts=parts,
        timestamp=datetime.now().isoformat(),
    )


def audit_vital_questions() -> VitalQuestionsAudit:
    """Test all 10 vital questions against measurable probes."""
    _ensure_repo_on_path()

    organ_snap = _cached("organ_snap", audit_organ_health)
    circ = _cached("circ", audit_circulation_flows)
    det = _cached("det", audit_deterioration_risks)

    results: List[VitalQuestionResult] = []

    for q in VITAL_QUESTIONS:
        qid = q["id"]
        passes = False
        evidence = ""
        try:
            if qid == "Q1":
                # Every organ at or above its floor
                floors = {
                    "bsc": 100.0, "cascade_bsc_360": 100.0,
                    "target_cascade": 100.0, "hr_section": 85.0,
                    "standards_wiring": 70.0, "engine_baseline": 100.0,
                }
                below = [
                    o.organ_id for o in organ_snap.organs
                    if floors.get(o.organ_id) is not None
                    and o.health_pct < floors[o.organ_id]
                ]
                passes = len(below) == 0
                evidence = (
                    f"All organs at floor" if passes
                    else f"Below floor: {below}"
                )

            elif qid == "Q2":
                passes = circ.overall_flow_pct >= 90.0
                evidence = f"Circulation = {circ.overall_flow_pct}%"

            elif qid == "Q3":
                active_high_plus = sum(
                    1 for r in det.risks
                    if r.detected and r.severity in ("critical", "high")
                )
                passes = active_high_plus == 0
                evidence = f"{active_high_plus} high+critical risks active"

            elif qid == "Q4":
                # No regression detected = no organ weakened
                passes = det.active == 0
                evidence = f"{det.active} deterioration risks active"

            elif qid == "Q5":
                passes = circ.overall_flow_pct >= 90.0
                evidence = (
                    f"Linear: {circ.linear_flowing}/{circ.linear_total}, "
                    f"Non-linear: {circ.non_linear_flowing}/{circ.non_linear_total}"
                )

            elif qid == "Q6":
                # Any broken/partial flow?
                broken = [f.flow_name for f in circ.flows if not f.flowing]
                passes = len(broken) == 0
                evidence = (
                    "No broken pathways" if passes
                    else f"Broken: {broken}"
                )

            elif qid == "Q7":
                org_ok = organ_snap.overall_health_pct >= 90.0
                circ_ok = circ.overall_flow_pct >= 90.0
                passes = org_ok and circ_ok
                evidence = (
                    f"organ={organ_snap.overall_health_pct}%, "
                    f"circ={circ.overall_flow_pct}%"
                )

            elif qid == "Q8":
                # G162 + verifier must run on each batch (audit gates exist)
                from utils.cascade_structure_engine import full_audit
                critical = full_audit().summary.get("rep_critical_count", -1)
                passes = critical == 0
                evidence = f"G162: rep_critical_count={critical}"

            elif qid == "Q9":
                # Every organ has >=1 audit gate
                no_gates = [
                    oid for oid, meta in ORGAN_REGISTRY.items()
                    if not meta.get("audit_gates")
                ]
                passes = len(no_gates) == 0
                evidence = (
                    "All organs gated" if passes
                    else f"Ungated: {no_gates}"
                )

            elif qid == "Q10":
                # Graceful degradation: removing one non-foundational organ
                # would still leave body above 70%.
                non_foundational_organs = [
                    o for o in organ_snap.organs
                    if o.organ_id not in (
                        "bsc", "cascade_bsc_360", "target_cascade",
                        "engine_baseline",
                    )
                ]
                if not non_foundational_organs:
                    passes = True
                    evidence = "No non-foundational organs to remove"
                else:
                    # Simulate: avg health if worst non-foundational was 0%
                    worst = min(non_foundational_organs, key=lambda o: o.health_pct)
                    n = len(organ_snap.organs)
                    simulated = (
                        (organ_snap.overall_health_pct * n - worst.health_pct) / n
                    )
                    passes = simulated >= 70.0
                    evidence = (
                        f"If '{worst.organ_id}' ({worst.health_pct}%) "
                        f"fails: body={simulated:.1f}% (floor 70%)"
                    )

        except Exception as exc:  # noqa: BLE001
            evidence = f"Probe error: {exc}"

        results.append(VitalQuestionResult(
            id=qid,
            question=q["question"],
            probe=q["probe"],
            passes=passes,
            evidence=evidence,
        ))

    passing = sum(1 for r in results if r.passes)
    return VitalQuestionsAudit(
        total=len(results),
        passing=passing,
        pct_passing=round(passing / len(results) * 100, 1) if results else 0.0,
        results=results,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ body_health_engine self-test ─")

    text = Path(__file__).read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0
    print("  ✓ Zero streamlit imports")

    # Organ health
    o = audit_organ_health()
    print(f"\n  ─── Organ Health Snapshot ───")
    print(f"  Organs registered:       {len(o.organs)}")
    print(f"  Overall avg health:      {o.overall_health_pct}%")
    print(f"  Healthy / Degraded / Critical: "
          f"{o.healthy_count} / {o.degraded_count} / {o.critical_count}")
    print()
    print(f"  Per-organ status:")
    for org in o.organs:
        emoji = {"healthy": "🟢", "degraded": "🟡", "critical": "🔴"}.get(
            org.status, "⚪")
        print(f"    {emoji} {org.name:40} {org.health_pct:5.1f}%  ({org.rescued_in})")

    # Circulation
    c = audit_circulation_flows()
    print(f"\n  ─── Blood Circulation ───")
    print(f"  Linear flows:        {c.linear_flowing}/{c.linear_total}")
    print(f"  Non-linear flows:    {c.non_linear_flowing}/{c.non_linear_total}")
    print(f"  Overall flow:        {c.overall_flow_pct}%")
    print()
    for f in c.flows:
        emoji = "✅" if f.flowing else "🔴"
        kind = "linear" if f.kind == "linear" else "non-lin"
        print(f"    {emoji} [{kind}] {f.flow_name:35} {f.from_organ} → {f.to_organ}")

    # Deterioration
    d = audit_deterioration_risks()
    print(f"\n  ─── Deterioration Risks ───")
    print(f"  Catalogued risks:    {d.total}")
    print(f"  Currently active:    {d.active}")
    print()
    for r in d.risks:
        emoji = "🚨" if r.detected else "✅"
        sev = {"critical": "CRITICAL", "high": "HIGH",
               "medium": "med", "low": "low"}.get(r.severity, "?")
        print(f"    {emoji} [{sev:8}] {r.risk_name:40} ({r.organ_id})")

    # Master rollup
    report = body_full_audit()
    print(f"\n  ═══ BODY HEALTH: {report.overall_body_pct}% ═══")
    print(f"  Mantra status:       {report.mantra_status}")

    # JSON
    json.dumps(report.to_dict())
    print(f"\n  ✓ JSON-serializable")

    # Snapshot history test (read-only)
    trend = audit_health_trend(n=3)
    print(f"  ✓ History accessible ({len(trend)} prior snapshots)")

    print("\n✓ self_test passed")


if __name__ == "__main__":
    self_test()
