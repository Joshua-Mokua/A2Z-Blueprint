"""utils/arena/batch.py — batch drill execution.

DrillBatch runs many drills in sequence (optionally with the same policy
seed), records each to the ledger, and returns aggregated statistics.

Use cases:
  - "Run all 12 drills nightly under DeterministicPolicy"
  - "Run every channel_survival drill 3 times to detect flake"
  - "Sweep RandomPolicy seeds 0..4 across the cascade drill"
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Sequence

from utils.arena.base import Drill, DrillResult
from utils.arena.library import get_drill, list_drills
from utils.arena.ledger import (
    DrillLedger, DrillRunRecord, get_drill_ledger,
)
from utils.arena.runner import DrillRunner


@dataclass
class BatchResult:
    """Outcome of a batch run."""
    total: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    drill_names: List[str] = field(default_factory=list)
    failed_drills: List[str] = field(default_factory=list)
    run_ids: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    by_category: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DrillBatch:
    """Run many drills in sequence and aggregate."""

    def __init__(self, *,
                  ledger: Optional[DrillLedger] = None,
                  runner: Optional[DrillRunner] = None,
                  policy_factory=None):
        """policy_factory is a callable returning a fresh AgentPolicy
        for each drill. If None, DeterministicPolicy is used."""
        self.ledger = ledger or get_drill_ledger()
        self._runner_template = runner
        if policy_factory is None:
            from utils.agents import DeterministicPolicy
            self._policy_factory = DeterministicPolicy
        else:
            self._policy_factory = policy_factory

    def run(self, *, drill_names: Optional[Sequence[str]] = None,
              category: Optional[str] = None,
              repeats: int = 1,
              record_to_ledger: bool = True) -> BatchResult:
        """Run a batch.

        If ``drill_names`` is None and ``category`` is None: all 12 drills.
        If ``category`` is set: every drill in that category.
        ``repeats`` runs each drill that many times in sequence.
        """
        if drill_names:
            names = list(drill_names)
        elif category:
            from utils.arena import drills_by_category
            names = drills_by_category(category)
        else:
            names = list_drills()

        run_ids: List[str] = []
        failed_drills: List[str] = []
        passed = 0
        total = 0
        by_category: Dict[str, Dict[str, int]] = {}

        start = time.time()
        for name in names:
            drill = get_drill(name)
            cat_bucket = by_category.setdefault(
                drill.category, {"total": 0, "passed": 0})

            for _ in range(repeats):
                policy = self._policy_factory()
                runner = DrillRunner(agent_policy=policy)
                run_start = time.time()
                result = runner.run(drill)
                duration_ms = (time.time() - run_start) * 1000.0

                if record_to_ledger:
                    record = self.ledger.record(
                        drill=drill, result=result,
                        policy_name=type(policy).__name__,
                        duration_ms=duration_ms,
                    )
                    run_ids.append(record.run_id)

                total += 1
                cat_bucket["total"] += 1
                if result.passed:
                    passed += 1
                    cat_bucket["passed"] += 1
                else:
                    failed_drills.append(name)

        duration = time.time() - start
        return BatchResult(
            total=total,
            passed=passed,
            failed=total - passed,
            pass_rate=(passed / total) if total else 0.0,
            drill_names=names,
            failed_drills=failed_drills,
            run_ids=run_ids,
            duration_seconds=duration,
            by_category=by_category,
        )


__all__ = ["DrillBatch", "BatchResult"]
