"""Integration tests for v10.422 — retired test cleanup."""

import sys
import tempfile
import shutil
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10422_engine_exists():
    path = REPO / "utils" / "test_cleanup_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_retired_tests",
        "def archive_retired_tests",
        "class RetiredTestInfo",
        "class TestCleanupAudit",
        "class ArchiveResult",
        "RETIRED_PATTERN",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10422_zero_streamlit():
    text = (REPO / "utils" / "test_cleanup_engine.py").read_text()
    import re
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10422_audit_real_codebase():
    """The real test suite has 12 retired functions across 4 files."""
    for k in list(sys.modules):
        if "test_cleanup" in k:
            del sys.modules[k]
    from utils.test_cleanup_engine import audit_retired_tests
    audit = audit_retired_tests()
    assert audit.total_retired >= 11, f"Got {audit.total_retired}, expected >= 11"
    assert audit.files_affected >= 3


def test_v10422_retired_pattern_parsing():
    """RETIRED_PATTERN should correctly extract version info."""
    from utils.test_cleanup_engine import RETIRED_PATTERN
    m = RETIRED_PATTERN.match("_retired_v10403_test_v10397_total_unique_codes")
    assert m is not None
    assert m.group(1) == "10403"
    assert m.group(2) == "10397"
    assert "total_unique_codes" in m.group(3)


def test_v10422_audit_synthetic_dir():
    from utils.test_cleanup_engine import audit_retired_tests
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "test_a.py").write_text(
            "def test_normal():\n    pass\n\n"
            "def _retired_v10200_test_v10100_old():\n    '''docstring'''\n    pass\n"
        )
        (tmp / "test_b.py").write_text(
            "def _retired_v10250_test_v10150_obsolete():\n    pass\n"
        )
        audit = audit_retired_tests(tests_dir=tmp)
        assert audit.total_retired == 2
        assert audit.files_affected == 2
        assert audit.by_retired_version == {"v10200": 1, "v10250": 1}
        assert audit.by_original_version == {"v10100": 1, "v10150": 1}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10422_audit_handles_empty_dir():
    from utils.test_cleanup_engine import audit_retired_tests
    tmp = Path(tempfile.mkdtemp())
    try:
        audit = audit_retired_tests(tests_dir=tmp)
        assert audit.total_retired == 0
        assert audit.files_affected == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10422_audit_skips_active_tests():
    from utils.test_cleanup_engine import audit_retired_tests
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "test_x.py").write_text(
            "def test_v10100_active():\n    pass\n"
            "def test_v10200_also_active():\n    pass\n"
            "def helper_function():\n    pass\n"
        )
        audit = audit_retired_tests(tests_dir=tmp)
        assert audit.total_retired == 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10422_archive_dry_run_default():
    from utils.test_cleanup_engine import archive_retired_tests
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "test_x.py").write_text(
            "def _retired_v10200_test_v10100_old():\n    pass\n"
        )
        archive_path = tmp / "out.json"
        result = archive_retired_tests(
            tests_dir=tmp, archive_path=archive_path,
        )
        # dry_run default = True, so file not written
        assert result.dry_run is True
        assert not archive_path.exists()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10422_archive_explicit_write():
    from utils.test_cleanup_engine import archive_retired_tests
    import json
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "test_x.py").write_text(
            "def _retired_v10200_test_v10100_old():\n    '''docstring'''\n    pass\n"
        )
        archive_path = tmp / "out.json"
        result = archive_retired_tests(
            tests_dir=tmp, archive_path=archive_path, dry_run=False,
        )
        assert result.dry_run is False
        assert archive_path.exists()
        archive = json.loads(archive_path.read_text())
        assert archive["total_retired"] == 1
        sample = next(iter(archive["tests"].values()))
        assert "def " in sample["body"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10422_archive_idempotent():
    from utils.test_cleanup_engine import archive_retired_tests
    tmp = Path(tempfile.mkdtemp())
    try:
        (tmp / "test_x.py").write_text(
            "def _retired_v10200_test_v10100_old():\n    pass\n"
        )
        archive_path = tmp / "out.json"
        r1 = archive_retired_tests(tests_dir=tmp, archive_path=archive_path, dry_run=False)
        r2 = archive_retired_tests(tests_dir=tmp, archive_path=archive_path, dry_run=False)
        assert r1.tests_archived == r2.tests_archived
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10422_archive_file_present():
    """After running v10.422 in this sandbox, the archive should exist."""
    archive = REPO / "data" / "_retired_tests_archive.json"
    assert archive.exists()
    import json
    data = json.loads(archive.read_text())
    assert data["total_retired"] >= 11
    assert "shipped" in data
    assert data["shipped"] == "v10.422"


def test_v10422_dataclasses_json_serializable():
    from utils.test_cleanup_engine import (
        audit_retired_tests, archive_retired_tests,
    )
    tmp = Path(tempfile.mkdtemp())
    try:
        a = audit_retired_tests(tests_dir=tmp)
        r = archive_retired_tests(tests_dir=tmp, archive_path=tmp / "x.json")
        import json
        json.dumps(a.to_dict())
        json.dumps(r.to_dict())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10422_runner_script_exists():
    path = REPO / "scripts" / "audit_retired_tests.py"
    assert path.exists()
    text = path.read_text()
    assert "--archive" in text


def test_v10422_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    for endpoint in (
        "/api/v1/test-cleanup/audit",
        "/api/v1/test-cleanup/archive",
    ):
        assert endpoint in text, f"Missing: {endpoint}"


def test_v10422_g308_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10422_retired_test_cleanup
    r = gate_v10422_retired_test_cleanup()
    assert r["passed"], r.get("violations")
