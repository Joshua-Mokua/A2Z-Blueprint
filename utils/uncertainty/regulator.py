"""utils/uncertainty/regulator.py — Phase 9 of Uncertainty Exposure.

Regulator shock drills. Simulate emergency regulator actions and
measure whether the system can adapt + provide audit extraction quickly.

The 7 regulator shock scenarios:
   1. Emergency CBK circular (new reporting requirement overnight)
   2. KRA audit request (transaction history extraction)
   3. AML investigation (suspicious activity report)
   4. Suspicious transaction freeze (specific account/beneficiary)
   5. CBK system inspection (operational integrity audit)
   6. Legal hold order (data preservation across products)
   7. OFAC sanctions update (cross-reference with existing customers)

Each scenario is built as a Drill where the agent must extract the
specific information a regulator would request. The oracle verifies
the required data points are reachable via the existing tool registry.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List

from utils.arena.base import Drill, DrillEnvironmentEvent, DrillOracle
from utils.agents.policies import AgentPolicy


_NAIROBI_TZ = None
def _tz():
    global _NAIROBI_TZ
    if _NAIROBI_TZ is None:
        from utils.simulation_clock import NAIROBI_TZ
        _NAIROBI_TZ = NAIROBI_TZ
    return _NAIROBI_TZ


# ─── Regulator response policies ────────────────────────────────────


class CbkEmergencyCircularPolicy(AgentPolicy):
    """Respond to overnight CBK circular: produce evidence of compliance
    by querying macro context, recent channel activity, and current
    chaos status (all required for the new reporting requirement).
    """
    name = "cbk_circular_response"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("macro:snapshot", {}, "current macro/rate context"),
            ("chaos:active", {}, "operational state right now"),
            ("channel:list", {}, "channel capacity"),
            ("events:query",
              {"event_type": "macro.update", "limit": 10},
              "recent macro audit trail"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "circular response complete")


class KraAuditExtractionPolicy(AgentPolicy):
    """KRA tax audit: extract transaction history with full traceability."""
    name = "kra_audit_extractor"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("events:query",
              {"event_type": "integration.rtgs.success", "limit": 50},
              "RTGS history for KRA"),
            ("events:query",
              {"event_type": "integration.swift.success", "limit": 50},
              "SWIFT history for KRA"),
            ("events:query",
              {"event_type": "integration.mpesa.success", "limit": 50},
              "M-Pesa history"),
            ("time:now", {}, "extraction timestamp for audit"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "KRA extraction complete")


class AmlInvestigationPolicy(AgentPolicy):
    """AML investigator looks at failed + successful transactions to
    identify suspicious patterns.
    """
    name = "aml_investigator"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("events:query",
              {"event_type": "integration.mpesa.success", "limit": 100},
              "all M-Pesa successes"),
            ("events:query",
              {"event_type": "integration.mpesa.failure", "limit": 100},
              "all M-Pesa failures"),
            ("events:query",
              {"event_type": "integration.rtgs.success", "limit": 50},
              "RTGS for cross-border check"),
            ("chaos:active", {},
              "rule out operational anomaly"),
            ("time:now", {},
              "investigation timestamp"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "AML investigation complete")


class SuspiciousFreezePolicy(AgentPolicy):
    """Activate freeze chaos to demonstrate freeze capability."""
    name = "suspicious_freeze"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("chaos:activate",
              {"name": "regulatory_freeze_order_cbk_suspension"},
              "activate regulator-ordered freeze"),
            ("chaos:active", {}, "confirm freeze active"),
            ("events:query",
              {"event_type": "chaos.activated", "limit": 5},
              "audit trail of freeze action"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "freeze demonstration complete")


class CbkInspectionPolicy(AgentPolicy):
    """CBK inspector demands operational + macro + audit data."""
    name = "cbk_inspector"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("macro:snapshot", {},
              "current macro position"),
            ("channel:list", {},
              "all integrated channels"),
            ("chaos:list", {},
              "all known chaos templates (capability list)"),
            ("chaos:active", {}, "current operational state"),
            ("events:query",
              {"event_type": "chaos.activated", "limit": 20},
              "operational history"),
            ("ml:list", {},
              "ML models in production"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "inspection complete")


class LegalHoldPolicy(AgentPolicy):
    """Legal hold: preserve and extract data across multiple channels."""
    name = "legal_hold"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("events:query",
              {"event_type": "integration.rtgs.success", "limit": 50},
              "preserve RTGS data"),
            ("events:query",
              {"event_type": "integration.swift.success", "limit": 50},
              "preserve SWIFT data"),
            ("events:query",
              {"event_type": "integration.cards.success", "limit": 50},
              "preserve cards data"),
            ("events:query",
              {"event_type": "integration.mpesa.success", "limit": 50},
              "preserve M-Pesa data"),
            ("events:query",
              {"event_type": "macro.update", "limit": 30},
              "preserve macro context"),
            ("time:now", {}, "legal hold timestamp"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "legal hold complete")


class OfacSanctionsCheckPolicy(AgentPolicy):
    """OFAC sanctions update: check whether any recent SWIFT/RTGS
    transactions need re-screening.
    """
    name = "ofac_sanctions_check"

    def __init__(self):
        self._step = 0

    def choose(self, observation, available_tools, goal):
        plans = [
            ("events:query",
              {"event_type": "integration.swift.success", "limit": 100},
              "all SWIFT for re-screening"),
            ("events:query",
              {"event_type": "integration.rtgs.success", "limit": 100},
              "all RTGS for re-screening"),
            ("events:query",
              {"event_type": "integration.swift.failure", "limit": 50},
              "any prior failures that might have leaked"),
        ]
        if self._step < len(plans):
            self._step += 1
            return plans[self._step - 1]
        return (None, {}, "OFAC check complete")


# ─── Regulator drill library ────────────────────────────────────────


def _build_regulator_library():
    tz = _tz()
    L: Dict[str, tuple] = {}
    base = datetime(2026, 9, 1, 9, 0, tzinfo=tz)

    L["reg_cbk_emergency_circular"] = (Drill(
        name="reg_cbk_emergency_circular", category="regulator_shock",
        description=(
            "CBK issues an emergency circular at 18:00 requiring "
            "morning-after compliance evidence. Agent extracts macro "
            "+ operational + audit context in 4 tool calls."
        ),
        sim_start=base, environment=[],
        agent_goal="cbk_circular",
        oracle=DrillOracle(
            min_steps=4,
            required_tool_calls=["macro:snapshot", "chaos:active",
                                   "channel:list", "events:query"],
        ),
        tags=["regulator", "cbk", "compliance"],
    ), CbkEmergencyCircularPolicy)

    L["reg_kra_audit_request"] = (Drill(
        name="reg_kra_audit_request", category="regulator_shock",
        description=(
            "KRA tax audit demands extraction of 50-row transaction "
            "history for RTGS + SWIFT + M-Pesa plus extraction "
            "timestamp."
        ),
        sim_start=base + timedelta(hours=1), environment=[],
        agent_goal="kra_audit",
        oracle=DrillOracle(
            min_steps=4,
            required_tool_calls=["events:query", "time:now"],
        ),
        tags=["regulator", "kra", "tax"],
    ), KraAuditExtractionPolicy)

    L["reg_aml_investigation"] = (Drill(
        name="reg_aml_investigation", category="regulator_shock",
        description=(
            "AML investigator examines successes + failures + "
            "operational anomalies + cross-border activity."
        ),
        sim_start=base + timedelta(hours=2), environment=[],
        agent_goal="aml_investigate",
        oracle=DrillOracle(
            min_steps=5,
            required_tool_calls=["events:query", "chaos:active"],
        ),
        tags=["regulator", "aml"],
    ), AmlInvestigationPolicy)

    L["reg_suspicious_freeze"] = (Drill(
        name="reg_suspicious_freeze", category="regulator_shock",
        description=(
            "Activate a regulator-ordered freeze and confirm both the "
            "active state and the audit trail entry."
        ),
        sim_start=base + timedelta(hours=3), environment=[],
        agent_goal="freeze_demo",
        oracle=DrillOracle(
            min_steps=3,
            required_tool_calls=["chaos:activate", "chaos:active",
                                   "events:query"],
        ),
        tags=["regulator", "freeze"],
    ), SuspiciousFreezePolicy)

    L["reg_cbk_inspection"] = (Drill(
        name="reg_cbk_inspection", category="regulator_shock",
        description=(
            "Full CBK on-site inspection: macro + channels + chaos "
            "templates + active state + history + ML models. 6-step "
            "deep extraction."
        ),
        sim_start=base + timedelta(hours=4), environment=[],
        agent_goal="cbk_inspect",
        oracle=DrillOracle(
            min_steps=6,
            required_tool_calls=["macro:snapshot", "channel:list",
                                   "chaos:list", "chaos:active",
                                   "events:query", "ml:list"],
        ),
        tags=["regulator", "cbk", "inspection"],
    ), CbkInspectionPolicy)

    L["reg_legal_hold"] = (Drill(
        name="reg_legal_hold", category="regulator_shock",
        description=(
            "Legal hold order: preserve and extract data across all "
            "4 payment channels + macro context + timestamp."
        ),
        sim_start=base + timedelta(hours=5), environment=[],
        agent_goal="legal_hold",
        oracle=DrillOracle(
            min_steps=6,
            required_tool_calls=["events:query", "time:now"],
        ),
        tags=["regulator", "legal"],
    ), LegalHoldPolicy)

    L["reg_ofac_sanctions_update"] = (Drill(
        name="reg_ofac_sanctions_update", category="regulator_shock",
        description=(
            "OFAC sanctions list updated: re-screen all SWIFT + RTGS "
            "successes and review any prior failures."
        ),
        sim_start=base + timedelta(hours=6), environment=[],
        agent_goal="ofac_check",
        oracle=DrillOracle(
            min_steps=3,
            required_tool_calls=["events:query"],
        ),
        tags=["regulator", "ofac", "sanctions"],
    ), OfacSanctionsCheckPolicy)

    return L


_LIBRARY = None


def _ensure():
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = _build_regulator_library()
    return _LIBRARY


def list_regulator_drills() -> List[str]:
    return sorted(_ensure().keys())


def get_regulator_drill(name: str) -> Drill:
    L = _ensure()
    if name not in L:
        raise KeyError(f"unknown regulator drill: {name!r}")
    return L[name][0]


def get_regulator_policy_factory(name: str):
    L = _ensure()
    if name not in L:
        raise KeyError(f"unknown regulator drill: {name!r}")
    return L[name][1]


def run_regulator_drill(name: str):
    from utils.arena import DrillRunner
    from utils.agents.base import AgentBudget
    drill = get_regulator_drill(name)
    policy_cls = get_regulator_policy_factory(name)
    runner = DrillRunner(
        agent_policy=policy_cls(),
        agent_budget=AgentBudget(max_steps=30, max_seconds=60),
    )
    return runner.run(drill)


__all__ = [
    "CbkEmergencyCircularPolicy", "KraAuditExtractionPolicy",
    "AmlInvestigationPolicy", "SuspiciousFreezePolicy",
    "CbkInspectionPolicy", "LegalHoldPolicy",
    "OfacSanctionsCheckPolicy",
    "list_regulator_drills", "get_regulator_drill",
    "get_regulator_policy_factory", "run_regulator_drill",
]
