"""Audit log — append-only audit trail framework.

Per Joshua doctrine Phase 3 EC5 + Phase 7: Audit integration & traceability.
Every state-changing action must call `audit_log(...)` for traceability.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).parent.parent / "data"
LOG_FILE = DATA_DIR / "audit_log.json"


def _load_log() -> List[Dict[str, Any]]:
    if not LOG_FILE.exists():
        return []
    try:
        data = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def audit_log(action: str, actor: str, module: str = "",
              entity_id: str = "", details: Optional[Dict[str, Any]] = None,
              severity: str = "info") -> str:
    """Write an audit log entry. Returns the entry's ID.

    Args:
        action: short label (e.g. "approve_loan", "cascade_update")
        actor: staff_code or system actor name
        module: optional organ/module key
        entity_id: optional ID of the affected entity
        details: optional dict of additional context
        severity: info | warning | error | critical
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    idem_seed = f"{actor}|{action}|{entity_id}|{timestamp}"
    entry_id = hashlib.sha256(idem_seed.encode()).hexdigest()[:16]
    entry = {
        "id": entry_id,
        "timestamp": timestamp,
        "actor": actor,
        "action": action,
        "module": module,
        "entity_id": entity_id,
        "severity": severity,
        "details": details or {},
    }
    try:
        log = _load_log()
        log.append(entry)
        LOG_FILE.write_text(json.dumps(log, indent=2), encoding="utf-8")
    except Exception:
        pass  # never fail caller on logging issues
    return entry_id


def query_audit(actor: Optional[str] = None, module: Optional[str] = None,
                action: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieve audit entries with optional filters (newest first)."""
    log = _load_log()
    result = []
    for entry in reversed(log):
        if actor and entry.get("actor") != actor:
            continue
        if module and entry.get("module") != module:
            continue
        if action and entry.get("action") != action:
            continue
        result.append(entry)
        if len(result) >= limit:
            break
    return result


__all__ = ["audit_log", "query_audit"]
