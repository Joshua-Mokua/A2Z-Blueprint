"""Backup Retention Engine — v10.421 (Phase 2d).

Per Joshua's locked backlog: 122 MB of stale .before snapshots
accumulated across the v10.345-v10.404 arc. Current sandbox state:
~173 MB across 17 _v10*_backups directories.

SAFETY-FIRST design:
  - All deletions are OPT-IN (default = dry-run)
  - Retention policy is configurable; defaults are conservative
  - Audit returns rich detail per directory before any deletion
  - Tiny backups (<1 MB) preserved by default - cheap historical reference
  - N most recent batch backups always preserved
  - Engine never deletes the data/_canonical_backups directory (different
    purpose - those are point-in-time snapshots of canonical configs,
    not batch-migration before-snapshots)

Default policy:
  - Preserve all backups < 1 MB
  - Preserve the 3 most recent _v10*_backups dirs
  - Delete everything else under data/_v10*_backups/

This is a one-shot housekeeping operation. After running, the engine's
audit shows reclaimed space and what remains.

ARCHITECTURAL NOTE: API-first per v10.412. ZERO streamlit imports.
File-system operations are explicit and gated behind apply_retention_policy
(not done in audit).

Shipped: v10.421.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"

# Defaults
DEFAULT_KEEP_RECENT_N = 3
DEFAULT_PRESERVE_SIZE_THRESHOLD_BYTES = 1 * 1024 * 1024  # 1 MB

# Pattern: _v10XXX_backups where XXX is digits
BACKUP_DIR_PATTERN = re.compile(r"^_v(\d+)_backups$")


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class BackupDirInfo:
    """Info about one backup directory."""
    name: str                    # e.g. _v10398_backups
    version: int                 # e.g. 10398
    path: str                    # absolute path
    file_count: int
    total_bytes: int             # sum of all files
    total_mb: float              # convenience
    is_below_threshold: bool     # < size_threshold_bytes
    is_recent: bool              # in top-N most recent
    will_delete: bool            # under current retention policy
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BackupRetentionAudit:
    """Bank-wide backup audit."""
    total_dirs: int
    total_bytes: int
    total_mb: float
    will_keep: int               # under retention policy
    will_delete: int             # under retention policy
    bytes_to_reclaim: int        # sum of will_delete sizes
    mb_to_reclaim: float
    keep_recent_n: int
    size_threshold_mb: float
    dirs: List[BackupDirInfo] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetentionApplyResult:
    """Result of running the retention policy."""
    dry_run: bool
    dirs_deleted: int
    bytes_reclaimed: int
    mb_reclaimed: float
    deleted_dirs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════

def _dir_size_bytes(path: Path) -> int:
    """Sum of all file sizes under path (recursive)."""
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _dir_file_count(path: Path) -> int:
    """Count of regular files under path (recursive)."""
    try:
        return sum(1 for f in path.rglob("*") if f.is_file())
    except OSError:
        return 0


def _list_backup_dirs(data_dir: Optional[Path] = None) -> List[Path]:
    """Find all _v10X_backups directories under data/."""
    if data_dir is None:
        data_dir = DATA_DIR
    if not data_dir.exists():
        return []
    dirs = []
    for entry in data_dir.iterdir():
        if entry.is_dir() and BACKUP_DIR_PATTERN.match(entry.name):
            dirs.append(entry)
    return dirs


# ════════════════════════════════════════════════════════════════════
# Public API — Audit
# ════════════════════════════════════════════════════════════════════

def audit_backup_retention(
    keep_recent_n: int = DEFAULT_KEEP_RECENT_N,
    size_threshold_bytes: int = DEFAULT_PRESERVE_SIZE_THRESHOLD_BYTES,
    data_dir: Optional[Path] = None,
) -> BackupRetentionAudit:
    """Audit backup directories against a retention policy.

    Policy:
      - Preserve backups below `size_threshold_bytes` (cheap historical refs)
      - Preserve the top-N most recent _v10*_backups by version number
      - Mark the rest as `will_delete=True` in the result

    No files are modified. Returns the audit only.
    """
    dirs = _list_backup_dirs(data_dir)
    # Parse versions, sort by version desc (most recent first)
    parsed: List[tuple] = []
    for d in dirs:
        m = BACKUP_DIR_PATTERN.match(d.name)
        if m:
            parsed.append((int(m.group(1)), d))
    parsed.sort(key=lambda x: x[0], reverse=True)

    # Top-N recent versions
    recent_versions = {v for v, _ in parsed[:keep_recent_n]}

    infos: List[BackupDirInfo] = []
    total_bytes = 0
    bytes_to_reclaim = 0
    will_keep = 0
    will_delete = 0

    for version, path in parsed:
        size = _dir_size_bytes(path)
        files = _dir_file_count(path)
        below_threshold = size < size_threshold_bytes
        is_recent = version in recent_versions

        will_del = not (below_threshold or is_recent)

        # Reason note
        if is_recent and below_threshold:
            note = "preserved: recent + below threshold"
        elif is_recent:
            note = "preserved: recent"
        elif below_threshold:
            note = "preserved: below threshold"
        else:
            note = "marked for deletion: stale + above threshold"

        info = BackupDirInfo(
            name=path.name,
            version=version,
            path=str(path),
            file_count=files,
            total_bytes=size,
            total_mb=round(size / (1024 * 1024), 2),
            is_below_threshold=below_threshold,
            is_recent=is_recent,
            will_delete=will_del,
            note=note,
        )
        infos.append(info)
        total_bytes += size
        if will_del:
            bytes_to_reclaim += size
            will_delete += 1
        else:
            will_keep += 1

    return BackupRetentionAudit(
        total_dirs=len(infos),
        total_bytes=total_bytes,
        total_mb=round(total_bytes / (1024 * 1024), 2),
        will_keep=will_keep,
        will_delete=will_delete,
        bytes_to_reclaim=bytes_to_reclaim,
        mb_to_reclaim=round(bytes_to_reclaim / (1024 * 1024), 2),
        keep_recent_n=keep_recent_n,
        size_threshold_mb=size_threshold_bytes / (1024 * 1024),
        dirs=infos,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Apply (destructive — explicit opt-in)
# ════════════════════════════════════════════════════════════════════

def apply_retention_policy(
    keep_recent_n: int = DEFAULT_KEEP_RECENT_N,
    size_threshold_bytes: int = DEFAULT_PRESERVE_SIZE_THRESHOLD_BYTES,
    dry_run: bool = True,
    data_dir: Optional[Path] = None,
) -> RetentionApplyResult:
    """Apply the retention policy.

    dry_run=True (default): reports what would be deleted, no FS changes
    dry_run=False: actually deletes the directories

    The destructive path requires an explicit dry_run=False.
    """
    audit = audit_backup_retention(
        keep_recent_n=keep_recent_n,
        size_threshold_bytes=size_threshold_bytes,
        data_dir=data_dir,
    )

    to_delete = [info for info in audit.dirs if info.will_delete]
    deleted_names: List[str] = []
    errors: List[str] = []
    bytes_freed = 0

    for info in to_delete:
        if dry_run:
            deleted_names.append(info.name)
            bytes_freed += info.total_bytes
            continue
        try:
            shutil.rmtree(info.path)
            deleted_names.append(info.name)
            bytes_freed += info.total_bytes
        except OSError as exc:
            errors.append(f"{info.name}: {exc}")

    return RetentionApplyResult(
        dry_run=dry_run,
        dirs_deleted=len(deleted_names),
        bytes_reclaimed=bytes_freed,
        mb_reclaimed=round(bytes_freed / (1024 * 1024), 2),
        deleted_dirs=deleted_names,
        errors=errors,
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ backup_retention_engine self-test ─")
    import tempfile

    # Set up a synthetic data dir with backup dirs of various sizes
    tmp = Path(tempfile.mkdtemp())
    try:
        # Tiny backup (50 bytes) — should be preserved
        (tmp / "_v10100_backups").mkdir()
        (tmp / "_v10100_backups" / "small.json").write_text("x" * 50)

        # Medium backup (1.5 MB) — eligible for deletion
        (tmp / "_v10200_backups").mkdir()
        (tmp / "_v10200_backups" / "medium.json").write_text("x" * (1_500_000))

        # Large backup (2 MB) — eligible for deletion
        (tmp / "_v10300_backups").mkdir()
        (tmp / "_v10300_backups" / "large.json").write_text("x" * (2_000_000))

        # Largest backup (3 MB) — recent, so preserved
        (tmp / "_v10400_backups").mkdir()
        (tmp / "_v10400_backups" / "largest.json").write_text("x" * (3_000_000))

        # Non-backup directory — should be ignored
        (tmp / "_canonical_backups").mkdir()
        (tmp / "_canonical_backups" / "ignored.json").write_text("x" * 5_000_000)

        # Audit with keep_recent_n=1 (only v10400 should be recent)
        audit = audit_backup_retention(
            keep_recent_n=1,
            size_threshold_bytes=1024 * 1024,  # 1 MB threshold
            data_dir=tmp,
        )
        assert audit.total_dirs == 4
        assert audit.will_keep == 2   # v10100 (tiny) + v10400 (recent)
        assert audit.will_delete == 2  # v10200 + v10300
        print(f"  ✓ Audit: {audit.will_keep} keep, {audit.will_delete} delete")

        v10100 = next(d for d in audit.dirs if d.version == 10100)
        v10200 = next(d for d in audit.dirs if d.version == 10200)
        v10300 = next(d for d in audit.dirs if d.version == 10300)
        v10400 = next(d for d in audit.dirs if d.version == 10400)

        assert v10100.is_below_threshold is True
        assert v10100.will_delete is False
        assert v10200.will_delete is True
        assert v10300.will_delete is True
        assert v10400.is_recent is True
        assert v10400.will_delete is False
        print(f"  ✓ Policy applied correctly per directory")

        # Dry-run apply
        result_dry = apply_retention_policy(
            keep_recent_n=1,
            size_threshold_bytes=1024 * 1024,
            dry_run=True,
            data_dir=tmp,
        )
        assert result_dry.dry_run is True
        assert result_dry.dirs_deleted == 2
        # Verify no actual deletion
        assert (tmp / "_v10200_backups").exists()
        assert (tmp / "_v10300_backups").exists()
        print(f"  ✓ Dry-run: would delete {result_dry.dirs_deleted} dirs, "
              f"freeing {result_dry.mb_reclaimed:.2f} MB (no FS change)")

        # Real apply
        result = apply_retention_policy(
            keep_recent_n=1,
            size_threshold_bytes=1024 * 1024,
            dry_run=False,
            data_dir=tmp,
        )
        assert result.dry_run is False
        assert result.dirs_deleted == 2
        # Verify actual deletion
        assert not (tmp / "_v10200_backups").exists()
        assert not (tmp / "_v10300_backups").exists()
        assert (tmp / "_v10100_backups").exists()  # tiny preserved
        assert (tmp / "_v10400_backups").exists()  # recent preserved
        assert (tmp / "_canonical_backups").exists()  # ignored entirely
        print(f"  ✓ Apply: deleted {result.dirs_deleted} dirs, "
              f"freed {result.mb_reclaimed:.2f} MB")

        # Idempotency: re-run shouldn't do anything
        audit2 = audit_backup_retention(
            keep_recent_n=1,
            size_threshold_bytes=1024 * 1024,
            data_dir=tmp,
        )
        assert audit2.will_delete == 0
        print(f"  ✓ Idempotent: re-audit shows 0 to delete")

        # Edge: missing data dir
        missing = Path(tempfile.mkdtemp()) / "nonexistent"
        a3 = audit_backup_retention(data_dir=missing)
        assert a3.total_dirs == 0
        print("  ✓ Missing data dir handled gracefully")

        # Zero streamlit imports
        text = Path(__file__).read_text()
        streamlit_imports = re.findall(
            r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
            text, re.MULTILINE,
        )
        assert len(streamlit_imports) == 0
        print("  ✓ Zero streamlit imports (React-ready)")

        print("✓ self_test passed")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    self_test()
