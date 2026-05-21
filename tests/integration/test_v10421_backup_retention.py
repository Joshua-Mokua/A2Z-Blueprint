"""Integration tests for v10.421 — backup retention cleanup."""

import sys
import tempfile
import shutil
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10421_engine_exists():
    path = REPO / "utils" / "backup_retention_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_backup_retention",
        "def apply_retention_policy",
        "class BackupDirInfo",
        "class BackupRetentionAudit",
        "class RetentionApplyResult",
        "BACKUP_DIR_PATTERN",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10421_zero_streamlit():
    text = (REPO / "utils" / "backup_retention_engine.py").read_text()
    import re
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10421_safety_dry_run_is_default():
    """Critical: apply_retention_policy must default to dry_run=True."""
    text = (REPO / "utils" / "backup_retention_engine.py").read_text()
    assert "dry_run: bool = True" in text


def _make_tmp_dir():
    return Path(tempfile.mkdtemp())


def test_v10421_audit_synthetic():
    for k in list(sys.modules):
        if "backup_retention" in k:
            del sys.modules[k]
    from utils.backup_retention_engine import audit_backup_retention

    tmp = _make_tmp_dir()
    try:
        # 3 backup dirs of varying sizes
        (tmp / "_v10010_backups").mkdir()
        (tmp / "_v10010_backups" / "f.txt").write_text("x" * 100)
        (tmp / "_v10020_backups").mkdir()
        (tmp / "_v10020_backups" / "f.txt").write_text("x" * (2 * 1024 * 1024))
        (tmp / "_v10030_backups").mkdir()
        (tmp / "_v10030_backups" / "f.txt").write_text("x" * (2 * 1024 * 1024))

        audit = audit_backup_retention(
            keep_recent_n=1, size_threshold_bytes=1024 * 1024,
            data_dir=tmp,
        )
        assert audit.total_dirs == 3
        assert audit.will_keep == 2  # tiny + recent
        assert audit.will_delete == 1  # mid-range non-recent
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10421_apply_dry_run_default():
    from utils.backup_retention_engine import apply_retention_policy
    tmp = _make_tmp_dir()
    try:
        (tmp / "_v10010_backups").mkdir()
        (tmp / "_v10010_backups" / "f.txt").write_text("x" * (2 * 1024 * 1024))
        (tmp / "_v10020_backups").mkdir()
        (tmp / "_v10020_backups" / "f.txt").write_text("x" * (2 * 1024 * 1024))

        # Default: dry-run, nothing deleted
        result = apply_retention_policy(
            keep_recent_n=1, size_threshold_bytes=1024 * 1024,
            data_dir=tmp,  # dry_run defaults to True
        )
        assert result.dry_run is True
        # Directory still exists
        assert (tmp / "_v10010_backups").exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10421_apply_explicit_delete():
    from utils.backup_retention_engine import apply_retention_policy
    tmp = _make_tmp_dir()
    try:
        (tmp / "_v10010_backups").mkdir()
        (tmp / "_v10010_backups" / "f.txt").write_text("x" * (2 * 1024 * 1024))
        (tmp / "_v10020_backups").mkdir()
        (tmp / "_v10020_backups" / "f.txt").write_text("x" * (2 * 1024 * 1024))

        result = apply_retention_policy(
            keep_recent_n=1, size_threshold_bytes=1024 * 1024,
            dry_run=False, data_dir=tmp,
        )
        assert result.dry_run is False
        assert result.dirs_deleted == 1
        assert not (tmp / "_v10010_backups").exists()  # old: deleted
        assert (tmp / "_v10020_backups").exists()      # recent: kept
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10421_canonical_backups_untouched():
    """Engine NEVER touches data/_canonical_backups."""
    from utils.backup_retention_engine import audit_backup_retention
    tmp = _make_tmp_dir()
    try:
        (tmp / "_canonical_backups").mkdir()
        (tmp / "_canonical_backups" / "x.json").write_text("x" * (10 * 1024 * 1024))
        (tmp / "_v10010_backups").mkdir()
        (tmp / "_v10010_backups" / "f.txt").write_text("x" * 100)

        audit = audit_backup_retention(data_dir=tmp)
        # Only _v10010_backups counted
        dir_names = {d.name for d in audit.dirs}
        assert "_canonical_backups" not in dir_names
        assert "_v10010_backups" in dir_names
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10421_missing_data_dir_graceful():
    from utils.backup_retention_engine import audit_backup_retention
    audit = audit_backup_retention(data_dir=Path("/nonexistent/path"))
    assert audit.total_dirs == 0
    assert audit.will_delete == 0


def test_v10421_size_threshold_preserves_small():
    from utils.backup_retention_engine import audit_backup_retention
    tmp = _make_tmp_dir()
    try:
        # Tiny - below threshold
        (tmp / "_v10010_backups").mkdir()
        (tmp / "_v10010_backups" / "tiny.txt").write_text("x" * 50)
        # Large - above threshold
        (tmp / "_v10020_backups").mkdir()
        (tmp / "_v10020_backups" / "big.txt").write_text("x" * (5 * 1024 * 1024))

        audit = audit_backup_retention(
            keep_recent_n=0,  # No "recent" preservation
            size_threshold_bytes=1024 * 1024,
            data_dir=tmp,
        )
        v10010 = next(d for d in audit.dirs if d.version == 10010)
        v10020 = next(d for d in audit.dirs if d.version == 10020)
        assert v10010.will_delete is False  # tiny preserved
        assert v10020.will_delete is True   # large + not recent
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10421_idempotent():
    """Re-running apply on cleaned state = no changes."""
    from utils.backup_retention_engine import apply_retention_policy, audit_backup_retention
    tmp = _make_tmp_dir()
    try:
        (tmp / "_v10010_backups").mkdir()
        (tmp / "_v10010_backups" / "f.txt").write_text("x" * (2 * 1024 * 1024))
        (tmp / "_v10020_backups").mkdir()
        (tmp / "_v10020_backups" / "f.txt").write_text("x" * (2 * 1024 * 1024))

        apply_retention_policy(
            keep_recent_n=1, size_threshold_bytes=1024 * 1024,
            dry_run=False, data_dir=tmp,
        )
        # Re-audit
        a = audit_backup_retention(
            keep_recent_n=1, size_threshold_bytes=1024 * 1024,
            data_dir=tmp,
        )
        assert a.will_delete == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10421_dataclasses_json_serializable():
    from utils.backup_retention_engine import audit_backup_retention, apply_retention_policy
    tmp = _make_tmp_dir()
    try:
        a = audit_backup_retention(data_dir=tmp)
        r = apply_retention_policy(data_dir=tmp, dry_run=True)
        import json
        json.dumps(a.to_dict())
        json.dumps(r.to_dict())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10421_runner_script_exists():
    path = REPO / "scripts" / "cleanup_backups.py"
    assert path.exists()
    text = path.read_text()
    assert "--confirm" in text


def test_v10421_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    for endpoint in (
        "/api/v1/backup-retention/audit",
        "/api/v1/backup-retention/apply",
    ):
        assert endpoint in text, f"Missing: {endpoint}"


def test_v10421_g307_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10421_backup_retention_cleanup
    r = gate_v10421_backup_retention_cleanup()
    assert r["passed"], r.get("violations")
