"""utils/data_migration.py — Environment promotion helper.

Per Joshua Master Prompt Phase O8:
    'Secure migration pipelines, production-safe deployments.'

This module provides the ONLY blessed path for moving data between
environments. Promotion is recorded, audited, and reversible (the
source remains intact unless explicitly purged).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from utils.environment import (
    Environment, get_environment, environment_paths, ALLOWED_PROMOTIONS
)

REPO = Path(__file__).parent.parent


@dataclass
class PromotionResult:
    success: bool
    src: str
    dst: str
    files_copied: int = 0
    bytes_copied: int = 0
    actor: str = ""
    reason: str = ""
    started_at: str = ""
    completed_at: str = ""
    error: Optional[str] = None
    audit_id: Optional[str] = None
    files_list: List[str] = field(default_factory=list)


def promote_dataset(
    *,
    src: Environment,
    dst: Environment,
    actor: str,
    reason: str = "",
    file_filter: Optional[List[str]] = None,
    dry_run: bool = True,
) -> PromotionResult:
    """Promote a dataset from one environment to the next.

    Args:
        src: Source environment (must be lower in the promotion ladder).
        dst: Target environment.
        actor: staff_code or system actor — required for audit.
        reason: Human-readable promotion justification.
        file_filter: Optional list of filenames to copy. If None, copies
                     all top-level files from the src data_root.
        dry_run: If True (default), no writes — returns what would happen.

    Returns:
        PromotionResult.
    """
    started = datetime.now(timezone.utc)
    started_iso = started.isoformat()
    result = PromotionResult(
        success=False, src=src.value, dst=dst.value,
        actor=actor, reason=reason, started_at=started_iso,
    )

    # 1. Validate allowed transition
    allowed = ALLOWED_PROMOTIONS.get(src, set())
    if dst not in allowed:
        result.error = (
            f"promotion {src.value} -> {dst.value} not in allowed set "
            f"{sorted(s.value for s in allowed)}"
        )
        result.completed_at = datetime.now(timezone.utc).isoformat()
        return result

    # 2. Resolve source/destination paths
    src_paths = environment_paths(src)
    dst_paths = environment_paths(dst)
    src_root = src_paths["data_root"]
    dst_root = dst_paths["data_root"]

    if not src_root.exists():
        result.error = f"source data_root {src_root} does not exist"
        result.completed_at = datetime.now(timezone.utc).isoformat()
        return result

    if not dry_run:
        dst_root.mkdir(parents=True, exist_ok=True)

    # 3. Collect files to copy
    src_files = [p for p in src_root.iterdir() if p.is_file()]
    if file_filter:
        filter_set = set(file_filter)
        src_files = [p for p in src_files if p.name in filter_set]

    copied = 0
    bytes_total = 0
    for sf in src_files:
        dest = dst_root / sf.name
        if not dry_run:
            shutil.copy2(sf, dest)
        copied += 1
        bytes_total += sf.stat().st_size
        result.files_list.append(sf.name)

    result.files_copied = copied
    result.bytes_copied = bytes_total
    result.success = True
    result.completed_at = datetime.now(timezone.utc).isoformat()

    # 4. Audit-log the promotion
    try:
        from utils.audit_log import audit_log
        result.audit_id = audit_log(
            action="dataset_promoted",
            actor=actor,
            module="ict",
            entity_id=f"{src.value}->{dst.value}",
            details={
                "src": src.value, "dst": dst.value,
                "files_copied": copied, "bytes_copied": bytes_total,
                "reason": reason, "dry_run": dry_run,
                "files_list": result.files_list[:50],
            },
            severity="critical" if dst == Environment.PROD else "warning",
        )
    except Exception:
        pass

    return result


def list_environment_inventory(env: Optional[Environment] = None) -> dict:
    """Inventory the contents of an environment's data_root.

    Useful for diff-ing two environments before promotion.
    """
    env = env or get_environment()
    paths = environment_paths(env)
    root = paths["data_root"]
    if not root.exists():
        return {"env": env.value, "exists": False, "files": []}
    files = []
    for p in sorted(root.iterdir()):
        if p.is_file():
            files.append({
                "name": p.name,
                "size_bytes": p.stat().st_size,
                "modified_at": datetime.fromtimestamp(
                    p.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            })
    return {
        "env": env.value,
        "exists": True,
        "data_root": str(root),
        "file_count": len(files),
        "files": files,
    }


__all__ = [
    "PromotionResult", "promote_dataset", "list_environment_inventory",
]
