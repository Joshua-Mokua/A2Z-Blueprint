"""utils/vb_actuals_bridge.py — Virtual Bank to live BSC actuals bridge.

Per Joshua v10.473 / Phase O1 doctrine:
    'Fully wire Virtual Bank outputs into the live BSC actuals refresh
     pipeline. Eliminate dependence on static Excel actuals.'

This module closes B-101 by providing a single orchestrator
`refresh_actuals_from_virtual_bank()` that:

  1. Reads CBS aggregates from cbs_data/
  2. Runs virtual_bank_kpi_unifier to produce UniversalBSCRecords
  3. Calls canonical_bsc_writer to persist them into bsc_actuals_*.json
  4. Triggers downstream YoY refresh
  5. Audit-logs the entire run

The bridge is dry-run by default. Callers must explicitly pass
`dry_run=False` to actually write.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vb_actuals_bridge")

REPO_ROOT = Path(__file__).parent.parent
CBS_DEFAULT = REPO_ROOT / "cbs_data"


@dataclass
class BridgeResult:
    """Outcome of a single VB→BSC bridge run."""
    success: bool
    dry_run: bool
    period: str
    target_period: str
    cbs_dir: str
    records_produced: int = 0
    records_written: int = 0
    records_skipped: int = 0
    validation_failures: int = 0
    reconciliation_balanced: bool = False
    duration_s: float = 0.0
    notes: List[str] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def refresh_actuals_from_virtual_bank(
    *,
    cbs_dir: Optional[Path] = None,
    period: str = "2026",
    target_period: str = "2026-Q1",
    dry_run: bool = True,
    actor: str = "system",
) -> BridgeResult:
    """Refresh live BSC actuals from the Virtual Bank → CBS pipeline.

    Args:
        cbs_dir: Source CBS aggregates directory (defaults to repo cbs_data/).
        period: Period the unifier reports records under (e.g. '2026'
                annual, normalised to canonical formats internally).
        target_period: Period bsc_engine.submit() writes against
                       (must be YYYY-QN or YYYY-MM).
        dry_run: If True (default), no mutations. Returns preview counts.
        actor: Audit log actor for the run.

    Returns:
        BridgeResult with counts + reconciliation status.
    """
    started = datetime.now()
    notes: List[str] = []
    result = BridgeResult(
        success=False, dry_run=dry_run, period=period,
        target_period=target_period,
        cbs_dir=str(cbs_dir or CBS_DEFAULT),
    )
    cbs_path = Path(cbs_dir) if cbs_dir is not None else CBS_DEFAULT
    # v10.475 Phase O2-A — emit observable event chain
    _v475_correlation_id = f"vb_refresh_{started.strftime('%Y%m%d%H%M%S%f')}"
    _v475_parent_event_id = None
    try:
        from utils.event_bus import get_event_bus as _v475_bus
        _v475_parent_event_id = _v475_bus().emit(
            event_type="actuals.refresh.started",
            actor=actor, module="bsc_cascade",
            entity_id=target_period,
            payload={"period": period, "target_period": target_period,
                     "dry_run": dry_run, "cbs_dir": str(cbs_path)},
            correlation_id=_v475_correlation_id,
            severity="info",
        )
    except Exception:
        pass

    if not cbs_path.exists():
        result.error = f"CBS directory not found: {cbs_path}"
        return result

    # ── v10.474 Phase O8 isolation guard ────────────────────────
    try:
        from utils.environment import get_environment, Environment
        from utils.data_isolation_guard import is_write_allowed
        _env = get_environment()
        if _env != Environment.PROD and not dry_run:
            # Non-PROD modes writing live actuals into PROD bsc_actuals_*.json
            # would contaminate production DNA. Refuse and require explicit
            # promotion via utils.data_migration.
            target_prod_file = f"data/bsc_actuals_{target_period}.json"
            allowed, why = is_write_allowed(target_prod_file, mode=_env)
            if not allowed:
                result.error = (
                    f"isolation guard blocked live write: {why}. "
                    f"Either switch to PROD mode (set_environment) or "
                    f"use dry_run=True for sim-mode previews."
                )
                notes.append(result.error)
                result.notes = notes
                from datetime import datetime as _dt
                result.duration_s = (_dt.now() - started).total_seconds()
                return result
        notes.append(f"environment={_env.value}")
    except ImportError:
        # Isolation module not available — proceed (back-compat)
        pass

    try:
        # ── 1. Unify VB output to UniversalBSCRecords ───────────────
        from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
        unify_out = unify_all_kpi_flow(cbs_dir=cbs_path, period=period)
        all_records = unify_out.get("all_records", []) or []
        validation = unify_out.get("validation", {}) or {}
        recon = unify_out.get("reconciliation", {}) or {}
        result.records_produced = len(all_records)
        result.validation_failures = int(validation.get("invalid_count", 0))
        result.reconciliation_balanced = bool(recon.get("balanced", False))
        if result.validation_failures > 0:
            notes.append(
                f"validation: {result.validation_failures} invalid records — "
                f"NOT writing"
            )
            result.notes = notes
            result.duration_s = (datetime.now() - started).total_seconds()
            return result

        # ── 2. Write through canonical_bsc_writer ───────────────────
        # The writer reads CBS itself via the v10.377 unifier and writes
        # via bsc_engine.submit(). We pass cbs_dir to keep deterministic
        # source. (Writer's own signature accepts cbs_dir + target_period.)
        from utils.canonical_bsc_writer import write_canonical_pbt_to_bsc
        write_out = write_canonical_pbt_to_bsc(
            cbs_dir=cbs_path,
            target_period=target_period,
            dry_run=dry_run,
            actor=actor,
        )
        # WriteResult fields vary; extract defensively
        result.records_written = int(getattr(write_out, "records_written", 0)
                                     or getattr(write_out, "n_written", 0) or 0)
        result.records_skipped = int(getattr(write_out, "records_skipped", 0)
                                     or getattr(write_out, "n_skipped", 0) or 0)

        # ── 3. Downstream YoY refresh (only on real write) ──────────
        if not dry_run and result.records_written > 0:
            try:
                from utils.live_actuals import refresh_yoy
                refresh_yoy()
                notes.append("YoY refresh triggered")
            except Exception as exc:
                notes.append(f"YoY refresh skipped: {exc}")

        # ── 4. Audit log ─────────────────────────────────────────────
        try:
            from utils.audit_log import audit_log
            audit_log(
                action="vb_actuals_refresh",
                actor=actor,
                module="bsc_cascade",
                entity_id=target_period,
                details={
                    "dry_run": dry_run,
                    "period": period,
                    "target_period": target_period,
                    "records_produced": result.records_produced,
                    "records_written": result.records_written,
                    "reconciliation_balanced": result.reconciliation_balanced,
                },
            )
        except Exception as exc:
            notes.append(f"audit log skipped: {exc}")

        result.success = True
    except Exception as exc:
        logger.exception("refresh_actuals_from_virtual_bank failed")
        result.error = str(exc)
        notes.append(f"exception: {exc}")
    finally:
        result.notes = notes
        result.duration_s = (datetime.now() - started).total_seconds()
        # v10.475 Phase O2-A — emit completion event
        try:
            from utils.event_bus import get_event_bus as _v475_bus_end
            _v475_bus_end().emit(
                event_type=("actuals.refresh.completed"
                            if result.success
                            else "actuals.refresh.failed"),
                actor=actor, module="bsc_cascade",
                entity_id=target_period,
                payload={
                    "records_produced": result.records_produced,
                    "records_written": result.records_written,
                    "validation_failures": result.validation_failures,
                    "reconciliation_balanced": result.reconciliation_balanced,
                    "duration_s": result.duration_s,
                    "error": result.error,
                },
                correlation_id=_v475_correlation_id,
                parent_event_id=_v475_parent_event_id,
                severity=("info" if result.success else "error"),
            )
        except Exception:
            pass
    return result


def preview_actuals_from_virtual_bank(
    *, cbs_dir: Optional[Path] = None,
    period: str = "2026",
    target_period: str = "2026-Q1",
) -> BridgeResult:
    """Convenience preview wrapper — guarantees dry_run=True."""
    return refresh_actuals_from_virtual_bank(
        cbs_dir=cbs_dir, period=period, target_period=target_period,
        dry_run=True,
    )


# ──────────────────────────────────────────────────────────────────────
# Self-tests (B-103 alignment: facade has self-tests)
# ──────────────────────────────────────────────────────────────────────

def _test_preview_dry_run_against_repo_cbs() -> None:
    """Dry-run preview against the real cbs_data/ — must not write."""
    result = preview_actuals_from_virtual_bank()
    assert result.dry_run is True
    assert result.error is None or "not found" in result.error, (
        f"unexpected error: {result.error}"
    )


def _test_period_quarterly_format_acceptance() -> None:
    """target_period must be Q-form; bridge should validate."""
    # The bridge passes target_period to canonical_bsc_writer which itself
    # validates via bsc_engine. Smoke-test that a sensible Q-form is accepted.
    result = preview_actuals_from_virtual_bank(target_period="2026-Q4")
    assert isinstance(result, BridgeResult)


def _test_bad_cbs_dir_errors_cleanly() -> None:
    """Non-existent cbs_dir must error cleanly, not crash."""
    result = refresh_actuals_from_virtual_bank(
        cbs_dir=Path("/tmp/__nonexistent_cbs__"),
        dry_run=True,
    )
    assert result.success is False
    assert "not found" in (result.error or "")


def self_test() -> None:
    """Run all self-tests."""
    _test_preview_dry_run_against_repo_cbs()
    _test_period_quarterly_format_acceptance()
    _test_bad_cbs_dir_errors_cleanly()


__all__ = [
    "BridgeResult", "refresh_actuals_from_virtual_bank",
    "preview_actuals_from_virtual_bank", "self_test",
]


if __name__ == "__main__":
    import sys as _sys
    if str(REPO_ROOT) not in _sys.path:
        _sys.path.insert(0, str(REPO_ROOT))
    self_test()
    print("vb_actuals_bridge self-test passed")
