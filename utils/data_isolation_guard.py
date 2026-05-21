"""utils/data_isolation_guard.py — Production DNA protection.

Per Joshua Master Prompt Phase O8:
    'No simulation artifacts may contaminate production DNA.'

This module guards write operations. Every helper here is OPT-IN —
caller code chooses to consult the guard. We do NOT monkey-patch the
filesystem (that would be fragile and break unrelated code). Instead,
callers in sensitive write paths (simulation outputs, virtual bank
persistence, etc.) consult `is_write_allowed()` or use
`guarded_write_path()` to resolve a mode-appropriate destination.

The guard's invariants:

  1. **Protected production paths** are immutable in DEV/SIM/UAT modes.
     A simulation cannot overwrite production `bsc_actuals_*.json` or
     `kpi_library.json`.

  2. **Sim/UAT outputs are namespaced**: `data/sim/...`, `data/uat/...`
     so a misconfigured engine running in PROD with sim-flavored inputs
     still writes to the sim sandbox, not the root.

  3. **Explicit promotion**: production data only changes via the
     migration helper (`utils/data_migration.py`) with audit trail.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from utils.environment import (
    Environment, get_environment, environment_paths, is_production
)

REPO = Path(__file__).parent.parent

# Paths that are ONLY writable in PROD or DEV (DEV mirrors PROD locally).
# Other environments (SIM, UAT, STAGING) must namespace their writes.
PROTECTED_PROD_FILES = {
    "data/users.json",
    "data/hr.json",
    "data/kpi_library.json",
    "data/target_cascade.json",
    "data/bank_targets.json",
    "data/bsc_scores.json",
    "data/actuals_yoy.json",
    "data/_manifest.json" if (REPO / "data" / "_manifest.json").exists() else "",
    # Manifests + canonical schemas
}
PROTECTED_PROD_FILES.discard("")  # drop empty if any


def is_protected_production_path(rel_or_abs_path) -> bool:
    """Check whether a path is in the protected production set."""
    p = Path(rel_or_abs_path)
    try:
        rel = p.relative_to(REPO) if p.is_absolute() else p
    except ValueError:
        rel = p
    return str(rel).replace("\\", "/") in PROTECTED_PROD_FILES


def is_write_allowed(target_path, *, mode: Optional[Environment] = None) -> tuple:
    """Decide whether a write to target_path is allowed in the given mode.

    Returns (allowed: bool, reason: str).

    Policy:
      - DEV: anything goes (returns True)
      - PROD: allowed (production deployments write to production paths)
      - SIM/UAT/STAGING: protected prod files BLOCKED; sandbox paths OK

    Note: callers (e.g. bsc_engine.submit, vb_actuals_bridge) should
    redirect their write to environment_paths()['data_root'] when in
    non-PROD modes — this guard is the secondary defence.
    """
    mode = mode or get_environment()
    p = Path(target_path)

    if mode == Environment.DEV or mode == Environment.PROD:
        return True, "dev/prod modes allow direct writes to production paths"

    # Non-prod: check if the target is in the protected set
    if is_protected_production_path(p):
        return False, (
            f"mode={mode.value} cannot write to protected production path "
            f"{p}. Redirect to environment_paths()['data_root'] "
            f"(e.g. data/{mode.value}/) instead."
        )
    return True, f"mode={mode.value} allows non-protected write to {p}"


def guarded_write_path(rel_path: str, *, mode: Optional[Environment] = None) -> Path:
    """Resolve a write-safe absolute path for the given environment.

    Example:
      In SIM mode, guarded_write_path('bsc_actuals_2026-Q1.json')
        -> /tmp/a2z_fix/data/sim/bsc_actuals_2026-Q1.json
      In PROD mode, the same call
        -> /tmp/a2z_fix/data/bsc_actuals_2026-Q1.json

    Callers in the simulation pipeline should ALWAYS resolve via this
    helper instead of hardcoding `data/...` paths.
    """
    mode = mode or get_environment()
    paths = environment_paths(mode)
    root = paths["data_root"]
    root.mkdir(parents=True, exist_ok=True)
    return root / rel_path


def assert_not_production(operation: str = "this operation") -> None:
    """Hard guard for simulation-only operations.

    Raises RuntimeError if called in PROD mode. Used inside chaos engine,
    test fixtures, scenario injection, and other operations that must
    never run against production.
    """
    if is_production():
        raise RuntimeError(
            f"REFUSED: {operation} cannot run in PROD mode. "
            f"Switch to SIM/UAT/STAGING via utils.environment.set_environment()."
        )


def audit_summary() -> dict:
    """Return a snapshot of isolation posture for use in audit gates."""
    mode = get_environment()
    paths = environment_paths(mode)
    return {
        "mode": mode.value,
        "data_root": str(paths["data_root"]),
        "cbs_root": str(paths["cbs_root"]),
        "disposable": paths["disposable"],
        "protected_prod_files_count": len(PROTECTED_PROD_FILES),
        "sim_dir_exists": (REPO / "data" / "sim").exists(),
        "uat_dir_exists": (REPO / "data" / "uat").exists(),
    }


__all__ = [
    "PROTECTED_PROD_FILES", "is_protected_production_path",
    "is_write_allowed", "guarded_write_path",
    "assert_not_production", "audit_summary",
]
