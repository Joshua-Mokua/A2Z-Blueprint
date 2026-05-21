"""utils/chaos/base.py — chaos event types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class ChaosKind(str, Enum):
    """Kinds of chaos events we can inject."""
    CHANNEL_OUTAGE = "channel_outage"        # 100% failure on a channel
    ELEVATED_FAILURE = "elevated_failure"    # bump failure rate for a window
    LATENCY_SPIKE = "latency_spike"          # multiply latency for a window
    MACRO_SHOCK = "macro_shock"              # delegates to macro_evolution
    SCHEME_DEGRADED = "scheme_degraded"      # card scheme partial outage


class ChaosSeverity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ChaosEvent:
    """A scheduled chaos injection.

    Fields:
      name              — unique short label
      kind              — what kind of chaos
      when              — sim moment to inject (tz-aware)
      duration          — how long the effect lasts (timedelta)
      severity          — observational classification
      target            — channel name(s) affected: 'mpesa', '*', etc.
      payload           — kind-specific parameters
      realistic_basis   — why this scenario is realistic
      tags              — searchable labels
    """
    name: str
    kind: ChaosKind
    when: datetime
    duration: timedelta = timedelta(minutes=30)
    severity: ChaosSeverity = ChaosSeverity.MEDIUM
    target: str = "*"
    payload: Dict[str, Any] = field(default_factory=dict)
    realistic_basis: str = ""
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.when.tzinfo is None:
            raise ValueError(f"ChaosEvent {self.name}: when must be tz-aware")
        if not isinstance(self.kind, ChaosKind):
            object.__setattr__(self, "kind", ChaosKind(self.kind))
        if not isinstance(self.severity, ChaosSeverity):
            object.__setattr__(self, "severity", ChaosSeverity(self.severity))

    def ends_at(self) -> datetime:
        return self.when + self.duration


__all__ = ["ChaosEvent", "ChaosKind", "ChaosSeverity"]
