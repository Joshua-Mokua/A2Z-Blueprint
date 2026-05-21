"""utils/environment.py — Canonical environment mode declaration.

Per Joshua Master Prompt (Enterprise Banking Digital Twin) Phase O8:
    'Maintain strict isolation between: Development, Simulation, UAT,
     Staging, Production. No simulation artifacts may contaminate
     production DNA.'

This module is the SINGLE SOURCE OF TRUTH for the current environment.
Every write-side operation in the codebase should consult these helpers
before persisting to `data/`, `cbs_data/`, or any other shared path.

Environment definitions (mirror enterprise SDLC conventions):
  DEV       - Developer machine; anything goes; data is local & disposable
  SIM       - Simulation / Digital Twin mode; outputs go to data/sim/
  UAT       - User Acceptance Testing; outputs go to data/uat/
  STAGING   - Pre-production rehearsal; mirrors PROD layout but isolated
  PROD      - Production; ONLY blessed sources may write here

The mode is resolved (in order of precedence):
  1. Environment variable A2Z_ENV (e.g. "sim", "prod")
  2. data/environment.json {"mode": "..."}
  3. Default fallback "dev"
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

REPO = Path(__file__).parent.parent
ENV_FILE = REPO / "data" / "environment.json"
ENV_VAR = "A2Z_ENV"


class Environment(str, Enum):
    """Canonical environment modes for the A2Z platform."""
    DEV = "dev"
    SIM = "sim"
    UAT = "uat"
    STAGING = "staging"
    PROD = "prod"


# Allowed environment promotion paths. Promotion is one-directional —
# you cannot demote PROD to DEV (that would corrupt production DNA).
ALLOWED_PROMOTIONS = {
    Environment.DEV: {Environment.SIM, Environment.UAT},
    Environment.SIM: {Environment.UAT},
    Environment.UAT: {Environment.STAGING},
    Environment.STAGING: {Environment.PROD},
    Environment.PROD: set(),  # PROD is terminal; no demotions
}


@dataclass
class EnvState:
    mode: Environment
    set_at: str
    set_by: str
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "set_at": self.set_at,
            "set_by": self.set_by,
            "reason": self.reason,
        }


def get_environment() -> Environment:
    """Resolve the active environment.

    Precedence: env var > environment.json > default DEV.
    Unknown values fall back to DEV with a warning.
    """
    raw = os.environ.get(ENV_VAR)
    if raw:
        try:
            return Environment(raw.lower().strip())
        except ValueError:
            pass

    if ENV_FILE.exists():
        try:
            data = json.loads(ENV_FILE.read_text(encoding="utf-8"))
            mode = (data.get("mode") or "").lower().strip()
            return Environment(mode)
        except (ValueError, json.JSONDecodeError, OSError):
            pass

    return Environment.DEV


def set_environment(target: Environment, *, set_by: str,
                    reason: str = "", force: bool = False) -> EnvState:
    """Set the environment to a new mode.

    By default, only ALLOWED_PROMOTIONS transitions are accepted.
    `force=True` bypasses (use only for tests / admin emergency).

    Raises ValueError on disallowed transition.
    """
    current = get_environment()
    if not force and target != current:
        allowed = ALLOWED_PROMOTIONS.get(current, set())
        if target not in allowed:
            raise ValueError(
                f"Environment transition {current.value} -> {target.value} "
                f"not allowed. Permitted from {current.value}: "
                f"{sorted(s.value for s in allowed)}. Use force=True only "
                f"for emergency override."
            )

    state = EnvState(
        mode=target,
        set_at=datetime.now(timezone.utc).isoformat(),
        set_by=set_by,
        reason=reason,
    )
    ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    ENV_FILE.write_text(json.dumps(state.to_dict(), indent=2),
                        encoding="utf-8")

    # Audit log the change
    try:
        from utils.audit_log import audit_log
        audit_log(
            action="environment_changed",
            actor=set_by,
            module="ict",
            entity_id=target.value,
            details={
                "from": current.value, "to": target.value,
                "reason": reason, "forced": force,
            },
            severity="critical" if target == Environment.PROD else "warning",
        )
    except Exception:
        pass

    return state


def is_production() -> bool:
    return get_environment() == Environment.PROD


def is_simulation() -> bool:
    return get_environment() == Environment.SIM


def is_staging() -> bool:
    return get_environment() == Environment.STAGING


def is_uat() -> bool:
    return get_environment() == Environment.UAT


def is_dev() -> bool:
    return get_environment() == Environment.DEV


def environment_paths(mode: Optional[Environment] = None) -> dict:
    """Return the canonical write-root paths for a given environment.

    PROD writes to the bare data/ root (the "production DNA" location).
    Every other environment writes to a namespaced sub-directory so
    simulation artifacts can never touch production paths.
    """
    mode = mode or get_environment()
    data_root = REPO / "data"
    cbs_root = REPO / "cbs_data"
    return {
        Environment.PROD: {
            "data_root": data_root,
            "cbs_root": cbs_root,
            "audit_log": data_root / "audit_log.json",
            "disposable": False,
        },
        Environment.STAGING: {
            "data_root": data_root / "staging",
            "cbs_root": cbs_root / "staging",
            "audit_log": data_root / "staging" / "audit_log.json",
            "disposable": False,
        },
        Environment.UAT: {
            "data_root": data_root / "uat",
            "cbs_root": cbs_root / "uat",
            "audit_log": data_root / "uat" / "audit_log.json",
            "disposable": True,
        },
        Environment.SIM: {
            "data_root": data_root / "sim",
            "cbs_root": cbs_root / "sim",
            "audit_log": data_root / "sim" / "audit_log.json",
            "disposable": True,
        },
        Environment.DEV: {
            # DEV uses the same root as PROD (developer local machine).
            # Disposable=True acknowledges nothing here is sacred.
            "data_root": data_root,
            "cbs_root": cbs_root,
            "audit_log": data_root / "audit_log.json",
            "disposable": True,
        },
    }[mode]


__all__ = [
    "Environment", "ALLOWED_PROMOTIONS", "EnvState",
    "get_environment", "set_environment",
    "is_production", "is_simulation", "is_staging",
    "is_uat", "is_dev", "environment_paths",
    "ENV_VAR", "ENV_FILE",
]
