"""utils.arena — Phase O7-A training arena + O7-B ledger.

Named drills where the digital twin is subjected to a pre-scripted set
of environmental events (chaos activations, macro shocks, scenarios)
and an agent must demonstrate survival or learning behaviour.

Each Drill packages:
  - setup        : an initial sim state (sim_time + macro baseline)
  - environment  : timed list of chaos/macro/scenario events
  - agent_goal   : what the agent is asked to do
  - oracle       : pass/fail criterion over the resulting trajectory

The library ships 12 prebuilt Kenya-realistic drills. v10.486 (O7-B) adds:
  - DrillLedger  : persistent append-only record of every drill run
  - DrillBatch   : run many drills in sequence, aggregate statistics
  - Trajectory comparison via SHA-256 digest of canonical step sequence

Drills run via DrillRunner, which composes a TickScheduler +
ChaosScheduler + AgentRunner and verifies the oracle when the run
completes.
"""

from utils.arena.base import (
    Drill, DrillEnvironmentEvent, DrillResult, DrillOracle,
)
from utils.arena.library import (
    DRILL_LIBRARY, get_drill, list_drills, drills_by_category,
)
from utils.arena.runner import DrillRunner
from utils.arena.ledger import (
    DrillRunRecord, DrillSummary, DrillComparison,
    DrillLedger, get_drill_ledger, reset_drill_ledger,
)
from utils.arena.batch import DrillBatch, BatchResult

__all__ = [
    # O7-A
    "Drill", "DrillEnvironmentEvent", "DrillResult", "DrillOracle",
    "DRILL_LIBRARY", "get_drill", "list_drills", "drills_by_category",
    "DrillRunner",
    # O7-B
    "DrillRunRecord", "DrillSummary", "DrillComparison",
    "DrillLedger", "get_drill_ledger", "reset_drill_ledger",
    "DrillBatch", "BatchResult",
]
