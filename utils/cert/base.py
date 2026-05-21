"""utils/cert/base.py — Olympic certification base types.

A CertCheck is one named test with a deterministic verdict. A CertReport
aggregates many CertChecks across organs. A CertProtocol is a named
battery (e.g. "olympic_full", "olympic_quick") that bundles checks for
execution.

The certifier runs each check exactly once, records duration and
outcome, and produces a structured report that can be written to disk
as JSON for downstream review.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional


# A check function returns either:
#   - True  / False                 (binary pass)
#   - (bool, str)                   (pass + note)
#   - {"passed": bool, "note": str, "metrics": {...}}
CheckResult = Any
CheckFn = Callable[..., CheckResult]


@dataclass
class CertCheck:
    """A single certification check."""
    name: str
    organ: str                          # channels / scenarios / chaos / etc
    fn: CheckFn
    description: str = ""
    critical: bool = True               # if True, any failure fails the cert
    timeout_seconds: float = 60.0

    def __post_init__(self):
        if not self.name:
            raise ValueError("CertCheck.name required")
        if not callable(self.fn):
            raise ValueError(
                f"CertCheck {self.name}: fn must be callable"
            )


@dataclass
class CheckOutcome:
    """The verdict of running one CertCheck."""
    name: str
    organ: str
    passed: bool
    duration_ms: float
    note: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    critical: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CertReport:
    """Aggregated certification report."""
    protocol_name: str
    started_at: str
    finished_at: str = ""
    total_checks: int = 0
    passed_checks: int = 0
    failed_checks: int = 0
    critical_failures: int = 0
    duration_seconds: float = 0.0
    outcomes: List[CheckOutcome] = field(default_factory=list)
    by_organ: Dict[str, Dict[str, int]] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Certification passes iff no critical failures."""
        return self.critical_failures == 0 and self.total_checks > 0

    @property
    def pass_rate(self) -> float:
        if self.total_checks == 0:
            return 0.0
        return self.passed_checks / self.total_checks

    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_name": self.protocol_name,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_checks": self.total_checks,
            "passed_checks": self.passed_checks,
            "failed_checks": self.failed_checks,
            "critical_failures": self.critical_failures,
            "duration_seconds": round(self.duration_seconds, 3),
            "pass_rate": round(self.pass_rate, 4),
            "passed": self.passed,
            "by_organ": dict(self.by_organ),
            "outcomes": [o.to_dict() for o in self.outcomes],
        }

    def summary_line(self) -> str:
        flag = "✓ CERTIFIED" if self.passed else "✗ FAILED"
        return (
            f"{flag} - {self.protocol_name}: "
            f"{self.passed_checks}/{self.total_checks} checks pass "
            f"(critical_failures={self.critical_failures}) "
            f"in {self.duration_seconds:.1f}s"
        )


@dataclass
class CertProtocol:
    """A named battery of certification checks."""
    name: str
    description: str = ""
    checks: List[CertCheck] = field(default_factory=list)

    def __post_init__(self):
        if not self.name:
            raise ValueError("CertProtocol.name required")

    def add(self, check: CertCheck) -> "CertProtocol":
        self.checks.append(check)
        return self

    def organs(self) -> List[str]:
        return sorted({c.organ for c in self.checks})

    def check_count(self) -> int:
        return len(self.checks)


__all__ = [
    "CertCheck", "CheckOutcome", "CertReport", "CertProtocol",
    "CheckFn", "CheckResult",
]
