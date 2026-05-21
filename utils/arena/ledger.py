"""utils/arena/ledger.py — persistent ledger of drill runs.

Records every drill run as an append-only JSONL line keyed by:
  run_id            (uuid4 hex)
  drill_name
  run_at            (sim time at start)
  policy_name       (whichever AgentPolicy was used)
  passed
  agent_steps
  successful_agent_steps
  environment_fired
  failure_reasons
  tool_call_summary
  duration_ms       (wall clock for the run)
  trajectory_digest (sha256 of canonicalised step sequence)

The trajectory_digest is the key reproducibility signal: identical
drill + identical policy + identical seed → identical digest.

Ledger storage:
  data/drill_ledger/runs.jsonl                  (append-only)
  data/drill_ledger/<run_id>.trajectory.json    (full trajectory)

Lookup APIs:
  DrillLedger.record(drill, policy_name, result)
  DrillLedger.list_runs(drill_name=None, limit=20)
  DrillLedger.get_run(run_id)
  DrillLedger.summarise(drill_name=None)
  DrillLedger.compare_runs(run_id_a, run_id_b)
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


_LEDGER_DIR = Path("data/drill_ledger")
_LEDGER_FILE = "runs.jsonl"


@dataclass
class DrillRunRecord:
    """A single ledger entry."""
    run_id: str
    drill_name: str
    run_at: str
    policy_name: str
    passed: bool
    agent_steps: int
    successful_agent_steps: int
    environment_fired: List[str] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)
    tool_call_summary: Dict[str, int] = field(default_factory=dict)
    duration_ms: float = 0.0
    trajectory_digest: str = ""
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DrillSummary:
    """Aggregated stats across many runs of a drill (or all drills)."""
    drill_name: Optional[str]
    total_runs: int = 0
    passed_runs: int = 0
    pass_rate: float = 0.0
    avg_agent_steps: float = 0.0
    distinct_digests: int = 0
    most_common_failure: str = ""
    last_run_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DrillComparison:
    """Trajectory comparison between two runs."""
    run_id_a: str
    run_id_b: str
    same_drill: bool
    same_digest: bool
    step_count_a: int
    step_count_b: int
    tool_call_diff: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DrillLedger:
    """Append-only ledger of drill runs. Thread-safe."""

    def __init__(self, *, ledger_dir: Optional[Path] = None):
        self.ledger_dir = Path(ledger_dir or _LEDGER_DIR)
        try:
            self.ledger_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self._lock = threading.Lock()

    # ── record ───────────────────────────────────────────────────

    def record(self, *, drill, result,
                  policy_name: str = "DeterministicPolicy",
                  duration_ms: float = 0.0,
                  notes: str = "") -> DrillRunRecord:
        """Append a run to the ledger.

        ``drill``  is a Drill (we only need .name)
        ``result`` is a DrillResult (we use everything)
        Returns the DrillRunRecord (also written to disk).
        """
        try:
            from utils.simulation_clock import sim_now
            run_at = sim_now().isoformat()
        except Exception:
            run_at = datetime.now(timezone.utc).isoformat()

        record = DrillRunRecord(
            run_id=uuid.uuid4().hex[:16],
            drill_name=drill.name,
            run_at=run_at,
            policy_name=policy_name,
            passed=result.passed,
            agent_steps=result.agent_steps,
            successful_agent_steps=result.successful_agent_steps,
            environment_fired=list(result.environment_fired),
            failure_reasons=list(result.failure_reasons),
            tool_call_summary=(
                result.trajectory.tool_call_summary()
                if result.trajectory is not None else {}
            ),
            duration_ms=duration_ms,
            trajectory_digest=self._digest_trajectory(result.trajectory),
            notes=notes,
        )

        with self._lock:
            try:
                # Append to JSONL
                with open(self.ledger_dir / _LEDGER_FILE, "a",
                            encoding="utf-8") as f:
                    f.write(json.dumps(record.to_dict()) + "\n")
                # Write full trajectory beside
                if result.trajectory is not None:
                    traj_path = (self.ledger_dir
                                  / f"{record.run_id}.trajectory.json")
                    with open(traj_path, "w", encoding="utf-8") as f:
                        try:
                            json.dump(result.trajectory.to_dict(),
                                       f, indent=2, default=str)
                        except Exception:
                            json.dump({"note": "trajectory not serialisable"},
                                       f)
            except Exception:
                pass

        return record

    # ── lookups ──────────────────────────────────────────────────

    def list_runs(self, *, drill_name: Optional[str] = None,
                    limit: int = 50,
                    passed: Optional[bool] = None
                    ) -> List[DrillRunRecord]:
        records = self._read_all()
        if drill_name:
            records = [r for r in records if r.drill_name == drill_name]
        if passed is not None:
            records = [r for r in records if r.passed == passed]
        return records[-limit:]

    def get_run(self, run_id: str) -> Optional[DrillRunRecord]:
        for r in self._read_all():
            if r.run_id == run_id:
                return r
        return None

    def get_trajectory(self, run_id: str) -> Optional[Dict[str, Any]]:
        path = self.ledger_dir / f"{run_id}.trajectory.json"
        if not path.exists():
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def total(self) -> int:
        return len(self._read_all())

    # ── aggregation ──────────────────────────────────────────────

    def summarise(self, drill_name: Optional[str] = None) -> DrillSummary:
        records = self._read_all()
        if drill_name:
            records = [r for r in records if r.drill_name == drill_name]
        if not records:
            return DrillSummary(drill_name=drill_name)
        total = len(records)
        passed = sum(1 for r in records if r.passed)
        avg_steps = sum(r.agent_steps for r in records) / total
        digests = {r.trajectory_digest for r in records
                    if r.trajectory_digest}
        # Most common failure reason
        failure_counts: Dict[str, int] = {}
        for r in records:
            for reason in r.failure_reasons:
                failure_counts[reason] = failure_counts.get(reason, 0) + 1
        if failure_counts:
            most_common = max(failure_counts.items(),
                                key=lambda kv: kv[1])[0]
        else:
            most_common = ""
        last_run_at = records[-1].run_at
        return DrillSummary(
            drill_name=drill_name,
            total_runs=total,
            passed_runs=passed,
            pass_rate=passed / total,
            avg_agent_steps=avg_steps,
            distinct_digests=len(digests),
            most_common_failure=most_common,
            last_run_at=last_run_at,
        )

    def summarise_by_drill(self) -> Dict[str, DrillSummary]:
        out: Dict[str, DrillSummary] = {}
        records = self._read_all()
        names = sorted({r.drill_name for r in records})
        for n in names:
            out[n] = self.summarise(n)
        return out

    # ── comparison ───────────────────────────────────────────────

    def compare_runs(self, run_id_a: str,
                       run_id_b: str) -> DrillComparison:
        a = self.get_run(run_id_a)
        b = self.get_run(run_id_b)
        if a is None or b is None:
            return DrillComparison(
                run_id_a=run_id_a, run_id_b=run_id_b,
                same_drill=False, same_digest=False,
                step_count_a=0, step_count_b=0,
                notes="one or both run_ids not found",
            )
        same_drill = a.drill_name == b.drill_name
        same_digest = (
            a.trajectory_digest and
            a.trajectory_digest == b.trajectory_digest
        )
        # Tool-call diff (set difference)
        tools_a = set(a.tool_call_summary.keys())
        tools_b = set(b.tool_call_summary.keys())
        diff: Dict[str, Any] = {
            "only_in_a": sorted(tools_a - tools_b),
            "only_in_b": sorted(tools_b - tools_a),
            "in_both_count_changed": {
                t: (a.tool_call_summary[t], b.tool_call_summary[t])
                for t in (tools_a & tools_b)
                if a.tool_call_summary[t] != b.tool_call_summary[t]
            },
        }
        return DrillComparison(
            run_id_a=run_id_a, run_id_b=run_id_b,
            same_drill=same_drill, same_digest=bool(same_digest),
            step_count_a=a.agent_steps,
            step_count_b=b.agent_steps,
            tool_call_diff=diff,
        )

    # ── maintenance ──────────────────────────────────────────────

    def clear(self) -> int:
        """Drop the entire ledger from disk. Returns runs removed."""
        with self._lock:
            count = 0
            try:
                ledger_path = self.ledger_dir / _LEDGER_FILE
                if ledger_path.exists():
                    with open(ledger_path, "r",
                                encoding="utf-8") as f:
                        count = sum(1 for _ in f)
                    ledger_path.unlink()
                for p in self.ledger_dir.glob("*.trajectory.json"):
                    try:
                        p.unlink()
                    except Exception:
                        pass
            except Exception:
                pass
            return count

    # ── internals ────────────────────────────────────────────────

    def _read_all(self) -> List[DrillRunRecord]:
        out: List[DrillRunRecord] = []
        path = self.ledger_dir / _LEDGER_FILE
        if not path.exists():
            return out
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                        out.append(DrillRunRecord(**d))
                    except Exception:
                        continue
        except Exception:
            pass
        return out

    @staticmethod
    def _digest_trajectory(trajectory) -> str:
        """SHA-256 digest over canonicalised step sequence."""
        if trajectory is None:
            return ""
        h = hashlib.sha256()
        try:
            for step in getattr(trajectory, "steps", []) or []:
                # Use (tool_name, args_keys_sorted, success) for digest
                args_keys = sorted((step.args or {}).keys())
                payload = {
                    "tool": step.tool_name,
                    "keys": args_keys,
                    "ok": step.result.success,
                }
                h.update(json.dumps(payload, sort_keys=True).encode("utf-8"))
            return h.hexdigest()[:16]
        except Exception:
            return ""


# ── module singleton ────────────────────────────────────────────────

_GLOBAL_LEDGER: Optional[DrillLedger] = None
_LEDGER_LOCK = threading.Lock()


def get_drill_ledger() -> DrillLedger:
    global _GLOBAL_LEDGER
    with _LEDGER_LOCK:
        if _GLOBAL_LEDGER is None:
            _GLOBAL_LEDGER = DrillLedger()
        return _GLOBAL_LEDGER


def reset_drill_ledger() -> None:
    """For test isolation. Does NOT touch disk."""
    global _GLOBAL_LEDGER
    with _LEDGER_LOCK:
        _GLOBAL_LEDGER = None


__all__ = [
    "DrillRunRecord", "DrillSummary", "DrillComparison",
    "DrillLedger", "get_drill_ledger", "reset_drill_ledger",
]
