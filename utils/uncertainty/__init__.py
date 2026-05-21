"""utils.uncertainty — Elite Uncertainty Exposure campaign (COMPLETE).

15-category pre-React final gauntlet:

  v10.489 (Phase 1): Black Swans + Irrationality + Time Corruption    (33)
  v10.490 (Phase 2): Data Poisoning + AI Adversarial                  (18)
  v10.491 (Phase 3): Long-term Drift + Multi-Organ Cascade            (15)
  v10.492 (Phase 4): Observability Blind Spots + Regulator Shock      (15)
  v10.493 (Phase 5): Frontend Pressure + Cognitive Load + React Impact (20)
  v10.494 (Phase 6): Total Collapse + 72hr War Game + Hidden Tech Debt (20)  <- FINAL

Each scenario is a Drill (DrillRunner-runnable) or a state-level check
function. Trajectory digest mechanism enables reproducibility checks.
Track-C deferred items honestly documented for UI-requiring tests.

After v10.494, the React championship transformation begins.
"""

from utils.uncertainty.blackswan import (
    list_blackswan_drills, get_blackswan_drill,
    extreme_chaos_templates_added,
)
from utils.uncertainty.irrational import (
    list_irrational_drills, get_irrational_drill,
    get_irrational_policy_factory, run_irrational_drill,
)
from utils.uncertainty.time_corruption import (
    list_time_corruption_drills, get_time_corruption_drill,
)
from utils.uncertainty.poisoning import (
    list_poisoning_drills, get_poisoning_drill,
    get_poisoning_policy_factory, run_poisoning_drill,
)
from utils.uncertainty.adversarial import (
    list_adversarial_drills, get_adversarial_drill,
    get_adversarial_policy_factory, run_adversarial_drill,
)
from utils.uncertainty.drift import (
    list_drift_drills, get_drift_drill, run_drift_check,
)
from utils.uncertainty.cascade import (
    list_cascade_drills, get_cascade_drill, measure_blast_radius,
)
from utils.uncertainty.observability import (
    list_observability_drills, run_observability_check,
)
from utils.uncertainty.regulator import (
    list_regulator_drills, get_regulator_drill,
    get_regulator_policy_factory, run_regulator_drill,
)
from utils.uncertainty.frontend import (
    list_frontend_drills, run_frontend_check,
)
from utils.uncertainty.cognitive import (
    list_cognitive_drills, run_cognitive_check,
    cognitive_track_c_deferred,
)
from utils.uncertainty.react_impact import (
    list_react_impact_drills, run_react_impact_check,
)
from utils.uncertainty.collapse import (
    list_collapse_drills, run_collapse_check,
)
from utils.uncertainty.war_game import (
    list_war_game_drills, run_war_game_check, run_72hr_war_game,
    WAR_GAME_CRISIS_SCHEDULE,
)
from utils.uncertainty.tech_debt import (
    list_tech_debt_drills, run_tech_debt_check,
)


def list_all_uncertainty_drills():
    """All drill names across v10.489 -> v10.494 (sorted)."""
    return sorted(
        list_blackswan_drills()
        + list_irrational_drills()
        + list_time_corruption_drills()
        + list_poisoning_drills()
        + list_adversarial_drills()
        + list_drift_drills()
        + list_cascade_drills()
        + list_observability_drills()
        + list_regulator_drills()
        + list_frontend_drills()
        + list_cognitive_drills()
        + list_react_impact_drills()
        + list_collapse_drills()
        + list_war_game_drills()
        + list_tech_debt_drills()
    )


__all__ = [
    # v10.489
    "list_blackswan_drills", "get_blackswan_drill",
    "extreme_chaos_templates_added",
    "list_irrational_drills", "get_irrational_drill",
    "get_irrational_policy_factory", "run_irrational_drill",
    "list_time_corruption_drills", "get_time_corruption_drill",
    # v10.490
    "list_poisoning_drills", "get_poisoning_drill",
    "get_poisoning_policy_factory", "run_poisoning_drill",
    "list_adversarial_drills", "get_adversarial_drill",
    "get_adversarial_policy_factory", "run_adversarial_drill",
    # v10.491
    "list_drift_drills", "get_drift_drill", "run_drift_check",
    "list_cascade_drills", "get_cascade_drill", "measure_blast_radius",
    # v10.492
    "list_observability_drills", "run_observability_check",
    "list_regulator_drills", "get_regulator_drill",
    "get_regulator_policy_factory", "run_regulator_drill",
    # v10.493
    "list_frontend_drills", "run_frontend_check",
    "list_cognitive_drills", "run_cognitive_check",
    "cognitive_track_c_deferred",
    "list_react_impact_drills", "run_react_impact_check",
    # v10.494
    "list_collapse_drills", "run_collapse_check",
    "list_war_game_drills", "run_war_game_check",
    "run_72hr_war_game", "WAR_GAME_CRISIS_SCHEDULE",
    "list_tech_debt_drills", "run_tech_debt_check",
    # umbrella
    "list_all_uncertainty_drills",
]
