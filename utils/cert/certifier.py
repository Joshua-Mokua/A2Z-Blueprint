"""utils/cert/certifier.py — run a CertProtocol, produce a CertReport.

Includes the standard prebuilt protocols:
  - olympic_full   : all checks across all organs (~30s)
  - olympic_quick  : light sampling of each organ (~5s)
"""

from __future__ import annotations

import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from utils.cert.base import (
    CertCheck, CertProtocol, CertReport, CheckOutcome,
)
from utils.cert import checks as ck


_CERT_DIR = Path("data/cert_reports")


def _reset_singletons() -> None:
    """Reset all simulator singletons for reproducible cert runs."""
    try:
        from utils.simulation_clock import reset_simulation_clock
        reset_simulation_clock()
    except Exception:
        pass
    try:
        from utils.chaos import reset_chaos_injector
        reset_chaos_injector()
    except Exception:
        pass
    try:
        from utils.macro_state import reset_macro_state
        reset_macro_state()
    except Exception:
        pass
    try:
        from utils.ml import reset_model_registry
        reset_model_registry()
    except Exception:
        pass
    try:
        from utils.agents import reset_default_tool_registry
        reset_default_tool_registry()
    except Exception:
        pass


def _normalise_check_result(raw):
    """Normalise check function return value to a dict."""
    if isinstance(raw, dict):
        return {
            "passed": bool(raw.get("passed", False)),
            "note": str(raw.get("note", "")),
            "metrics": dict(raw.get("metrics", {})),
        }
    if isinstance(raw, tuple) and len(raw) == 2:
        passed, note = raw
        return {
            "passed": bool(passed),
            "note": str(note),
            "metrics": {},
        }
    if isinstance(raw, bool):
        return {"passed": raw, "note": "", "metrics": {}}
    # Unknown shape — treat as failure
    return {
        "passed": False,
        "note": f"unexpected check return: {type(raw).__name__}",
        "metrics": {},
    }


class Certifier:
    """Execute a CertProtocol and produce a CertReport."""

    def __init__(self, *, reports_dir: Optional[Path] = None,
                  reset_between_checks: bool = True):
        self.reports_dir = Path(reports_dir or _CERT_DIR)
        try:
            self.reports_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.reset_between_checks = reset_between_checks

    def run(self, protocol: CertProtocol,
              *, persist: bool = True) -> CertReport:
        """Execute every check in the protocol in declaration order."""
        started_at = datetime.now(timezone.utc).isoformat()
        report = CertReport(
            protocol_name=protocol.name,
            started_at=started_at,
        )
        start = time.time()

        for check in protocol.checks:
            if self.reset_between_checks:
                _reset_singletons()
            outcome = self._run_one_check(check)
            report.outcomes.append(outcome)
            # Aggregate
            bucket = report.by_organ.setdefault(
                check.organ, {"total": 0, "passed": 0})
            bucket["total"] += 1
            report.total_checks += 1
            if outcome.passed:
                bucket["passed"] += 1
                report.passed_checks += 1
            else:
                report.failed_checks += 1
                if outcome.critical:
                    report.critical_failures += 1

        report.duration_seconds = time.time() - start
        report.finished_at = datetime.now(timezone.utc).isoformat()

        if persist:
            self._persist(report)

        # Final reset for clean slate after cert run
        if self.reset_between_checks:
            _reset_singletons()
        return report

    # ── internals ────────────────────────────────────────────────

    def _run_one_check(self, check: CertCheck) -> CheckOutcome:
        start = time.time()
        try:
            raw = check.fn()
            normalised = _normalise_check_result(raw)
            duration_ms = (time.time() - start) * 1000.0
            return CheckOutcome(
                name=check.name,
                organ=check.organ,
                passed=normalised["passed"],
                duration_ms=duration_ms,
                note=normalised["note"],
                metrics=normalised["metrics"],
                critical=check.critical,
            )
        except Exception as exc:
            duration_ms = (time.time() - start) * 1000.0
            return CheckOutcome(
                name=check.name,
                organ=check.organ,
                passed=False,
                duration_ms=duration_ms,
                error=(
                    f"{type(exc).__name__}: {exc}\n"
                    f"{traceback.format_exc()[:500]}"
                ),
                critical=check.critical,
            )

    def _persist(self, report: CertReport) -> Optional[Path]:
        try:
            stamp = report.started_at.replace(":", "-").replace(".", "-")
            fname = f"{report.protocol_name}_{stamp}.json"
            path = self.reports_dir / fname
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report.to_dict(), f, indent=2)
            return path
        except Exception:
            return None


# ─── Prebuilt protocols ─────────────────────────────────────────────


def build_olympic_full() -> CertProtocol:
    """The full Olympic-grade certification battery."""
    p = CertProtocol(
        name="olympic_full",
        description=(
            "Full Olympic certification: every organ tested for "
            "reproducibility, soundness, and integration. ~30s wall time."
        ),
    )
    # channels (3 checks)
    p.add(CertCheck(name="channels.seven_registered", organ="channels",
                      fn=ck.check_channels_seven_registered,
                      description="all 7 channels discoverable"))
    p.add(CertCheck(name="channels.seed_deterministic", organ="channels",
                      fn=ck.check_channels_seed_deterministic,
                      description="same seed -> same outcome"))
    p.add(CertCheck(name="channels.chaos_outage_blocks", organ="channels",
                      fn=ck.check_channels_chaos_outage_blocks,
                      description="outage blocks all submissions"))
    # scenarios (2)
    p.add(CertCheck(name="scenarios.one_hundred_registered",
                      organ="scenarios",
                      fn=ck.check_scenarios_one_hundred_registered,
                      description="100 scenarios in library"))
    p.add(CertCheck(name="scenarios.run_sample",
                      organ="scenarios",
                      fn=ck.check_scenarios_run_a_sample,
                      description="sample scenario runs",
                      critical=False))
    # chaos (2)
    p.add(CertCheck(name="chaos.library_size_25", organ="chaos",
                      fn=ck.check_chaos_library_size,
                      description="25 chaos templates"))
    p.add(CertCheck(name="chaos.window_expires", organ="chaos",
                      fn=ck.check_chaos_window_expires,
                      description="chaos auto-expires after window"))
    # macro (3)
    p.add(CertCheck(name="macro.kenya_baseline_realistic",
                      organ="macro",
                      fn=ck.check_macro_kenya_baseline_realistic,
                      description="Kenya 2026 baseline realistic"))
    p.add(CertCheck(name="macro.evolution_seed_deterministic",
                      organ="macro",
                      fn=ck.check_macro_evolution_seed_deterministic,
                      description="OU evolution deterministic"))
    p.add(CertCheck(name="macro.shock_preserves_spreads",
                      organ="macro",
                      fn=ck.check_macro_shock_preserves_spreads,
                      description="cbr_change preserves T-bill spreads"))
    # sim clock (2)
    p.add(CertCheck(name="simclock.set_and_advance", organ="simclock",
                      fn=ck.check_simclock_set_and_advance,
                      description="set + advance precise"))
    p.add(CertCheck(name="simclock.tick_scheduler_fires",
                      organ="simclock",
                      fn=ck.check_tick_scheduler_fires_callbacks,
                      description="scheduler fires callbacks at sim time"))
    # ml (3)
    p.add(CertCheck(name="ml.classifier_learns",
                      organ="ml",
                      fn=ck.check_ml_classifier_learns_synthetic,
                      description="classifier learns linearly separable"))
    p.add(CertCheck(name="ml.regressor_recovers",
                      organ="ml",
                      fn=ck.check_ml_regressor_recovers_linear,
                      description="regressor recovers coefficients"))
    p.add(CertCheck(name="ml.classifier_seed_deterministic",
                      organ="ml",
                      fn=ck.check_ml_classifier_seed_deterministic,
                      description="classifier seed deterministic"))
    # agents (3)
    p.add(CertCheck(name="agents.registry_15_tools",
                      organ="agents",
                      fn=ck.check_agents_default_registry_15_tools,
                      description="15 tools across 6 categories"))
    p.add(CertCheck(name="agents.random_seed_deterministic",
                      organ="agents",
                      fn=ck.check_agents_random_policy_deterministic,
                      description="random policy deterministic"))
    p.add(CertCheck(name="agents.budget_enforced",
                      organ="agents",
                      fn=ck.check_agents_budget_enforced,
                      description="max_steps budget enforced"))
    # arena (2)
    p.add(CertCheck(name="arena.twelve_drills_pass",
                      organ="arena",
                      fn=ck.check_arena_twelve_drills_pass,
                      description="all 12 prebuilt drills pass"))
    p.add(CertCheck(name="arena.trajectory_digest_deterministic",
                      organ="arena",
                      fn=ck.check_arena_trajectory_digest_deterministic,
                      description="trajectory digest deterministic"))
    # event bus (1)
    p.add(CertCheck(name="eventbus.emit_and_query",
                      organ="eventbus",
                      fn=ck.check_event_bus_emits_and_queries,
                      description="event bus round-trip"))
    # 360 (1)
    p.add(CertCheck(name="cascade_360.harmony_preserved",
                      organ="cascade_360",
                      fn=ck.check_360_harmony,
                      description="cascade BSC 360 harmony >= 99.9%"))
    return p


def build_olympic_quick() -> CertProtocol:
    """Quick sanity sweep — one critical check per organ."""
    p = CertProtocol(
        name="olympic_quick",
        description=(
            "Quick sanity sweep - one critical check per organ. ~5s."
        ),
    )
    p.add(CertCheck(name="channels.seven_registered", organ="channels",
                      fn=ck.check_channels_seven_registered))
    p.add(CertCheck(name="scenarios.one_hundred_registered",
                      organ="scenarios",
                      fn=ck.check_scenarios_one_hundred_registered))
    p.add(CertCheck(name="chaos.library_size_25", organ="chaos",
                      fn=ck.check_chaos_library_size))
    p.add(CertCheck(name="macro.kenya_baseline_realistic",
                      organ="macro",
                      fn=ck.check_macro_kenya_baseline_realistic))
    p.add(CertCheck(name="simclock.set_and_advance", organ="simclock",
                      fn=ck.check_simclock_set_and_advance))
    p.add(CertCheck(name="ml.classifier_seed_deterministic",
                      organ="ml",
                      fn=ck.check_ml_classifier_seed_deterministic))
    p.add(CertCheck(name="agents.registry_15_tools",
                      organ="agents",
                      fn=ck.check_agents_default_registry_15_tools))
    p.add(CertCheck(name="arena.trajectory_digest_deterministic",
                      organ="arena",
                      fn=ck.check_arena_trajectory_digest_deterministic))
    p.add(CertCheck(name="cascade_360.harmony_preserved",
                      organ="cascade_360",
                      fn=ck.check_360_harmony))
    return p


__all__ = ["Certifier", "build_olympic_full", "build_olympic_quick"]
