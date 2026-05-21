"""utils.chaos — Phase O5 chaos engineering.

Inject failures into the 7 channels at specific sim moments. Models:
  - Channel-wide outages (Safaricom M-Pesa down, SWIFT correspondent unreachable)
  - Elevated failure rates (degraded card scheme, KEPSS latency spike)
  - Single transaction failures (specific reference triggers a specific failure)
  - Macro shocks (FX devaluation, credit shock) — coordinates with v10.481

Chaos is scheduled via the tick scheduler so it fires at deterministic
sim moments, can be replayed reproducibly, and is observable via the
event bus.
"""

from utils.chaos.base import (
    ChaosEvent, ChaosKind, ChaosSeverity,
)
from utils.chaos.injector import (
    ChaosInjector, get_chaos_injector, reset_chaos_injector,
)
from utils.chaos.library import (
    CHAOS_LIBRARY, get_chaos_event, list_chaos_events,
    chaos_events_by_kind, chaos_events_by_severity,
)
from utils.chaos.scheduler import ChaosScheduler

__all__ = [
    "ChaosScheduler",
    "ChaosEvent", "ChaosKind", "ChaosSeverity",
    "ChaosInjector", "get_chaos_injector", "reset_chaos_injector",
    "CHAOS_LIBRARY", "get_chaos_event", "list_chaos_events",
    "chaos_events_by_kind", "chaos_events_by_severity",
]
