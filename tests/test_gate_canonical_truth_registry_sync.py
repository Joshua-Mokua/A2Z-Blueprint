"""Regression tests for G388 — gate_canonical_truth_registry_sync.

Authored in v10.502 Stage C Arc D2 Batch 5b to close the
stated-vs-enforced gap on `CANONICAL_TRUTH_REGISTRY.md` D4 doctrine.

The gate parses `Authoritative source` and `Canonical interface` rows
from the registry, extracts backticked path-shaped values, and verifies
each resolves on disk. Two safety lists (RUNTIME_GITIGNORED,
SHADCN_ASPIRATIONAL) prevent false positives for legitimately-absent
paths.

These tests verify:
1. The gate is registered in scripts/audit.py GATES dispatch table.
2. The gate passes against the current real registry (the registry was
   reality-corrected in Batch 5b; all pointers should resolve).
3. The gate catches a synthetic missing pointer when the registry is
   mutated in a temp file.
4. The gate handles glob patterns correctly.
5. The gate respects the RUNTIME_GITIGNORED allowlist.
6. The gate respects the SHADCN_ASPIRATIONAL allowlist.
7. The gate doesn't crash if the registry file is missing — returns
   a failure result with a clear violation.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _fresh_audit_module():
    """Load scripts/audit.py by explicit file path.

    Avoid bare `import audit` because the repo also contains
    `./audit.py` at the root, which would shadow `scripts/audit.py`
    on sys.path. Explicit loader path eliminates the ambiguity.
    Each call returns a freshly-executed module so monkeypatch
    state never leaks between tests.
    """
    spec = importlib.util.spec_from_file_location(
        "audit_script_under_test", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_g388_is_registered_in_gates_table():
    """The gate must appear in the GATES dispatch list."""
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G388" in gate_ids, (
        "G388 missing from GATES registry — gate authored but not wired"
    )


def test_g388_function_exists_with_expected_signature():
    """Function must be importable and callable with no arguments."""
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_canonical_truth_registry_sync"), (
        "gate_canonical_truth_registry_sync function not defined"
    )
    fn = audit.gate_canonical_truth_registry_sync
    assert callable(fn)


def test_g388_passes_against_current_registry():
    """After Batch 5b corrections, the real registry should pass cleanly."""
    audit = _fresh_audit_module()
    result = audit.gate_canonical_truth_registry_sync()
    assert result["id"] == "G388"
    assert result["name"] == "canonical_truth_registry_sync"
    # Filter INFO notes out of violations to check real failures
    real_violations = [
        v for v in result["violations"]
        if not v.startswith("INFO ")
    ]
    assert len(real_violations) == 0, (
        f"G388 has unexpected violations against the corrected registry: "
        f"{real_violations}"
    )
    assert result["passed"] is True


def test_g388_returns_expected_summary_shape():
    """Summary must report checked/resolved/violations counts."""
    audit = _fresh_audit_module()
    result = audit.gate_canonical_truth_registry_sync()
    s = result["summary"]
    assert "checked=" in s
    assert "resolved=" in s
    assert "violations=" in s
    assert "runtime_gitignored=" in s
    assert "shadcn_aspirational=" in s


def test_g388_catches_synthetic_missing_pointer(tmp_path, monkeypatch):
    """If the registry is mutated to cite a non-existent path, gate must fail."""
    audit = _fresh_audit_module()

    # Stage a tampered registry in a temp tree
    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    (fake_repo / "docs" / "architecture").mkdir(parents=True)
    bad_registry = fake_repo / "docs" / "architecture" / "CANONICAL_TRUTH_REGISTRY.md"
    bad_registry.write_text(
        "# Test registry\n\n"
        "### Domain: Synthetic\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Authoritative source | `definitely/does/not/exist.json` |\n"
        "| Canonical interface | `also/missing.py` |\n",
        encoding="utf-8",
    )

    # Re-point the gate's repo root to the fake tree
    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    # Need a scripts dir for the Path(__file__).resolve().parent.parent walk
    (fake_repo / "scripts").mkdir()
    (fake_repo / "scripts" / "audit.py").write_text("# stub")

    result = audit.gate_canonical_truth_registry_sync()
    assert result["passed"] is False
    real_violations = [
        v for v in result["violations"] if not v.startswith("INFO ")
    ]
    assert len(real_violations) == 2, (
        f"Expected 2 missing-pointer violations, got: {real_violations}"
    )
    assert any("definitely/does/not/exist.json" in v for v in real_violations)
    assert any("also/missing.py" in v for v in real_violations)


def test_g388_handles_glob_with_matches(tmp_path, monkeypatch):
    """A glob pattern with at least one filesystem match should resolve."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "docs" / "architecture").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "utils" / "thing_alpha.py").write_text("")
    (fake_repo / "utils" / "thing_beta.py").write_text("")

    registry = fake_repo / "docs" / "architecture" / "CANONICAL_TRUTH_REGISTRY.md"
    registry.write_text(
        "### Domain: Glob test\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Authoritative source | `utils/thing_*.py` |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    (fake_repo / "scripts").mkdir()

    result = audit.gate_canonical_truth_registry_sync()
    real_violations = [
        v for v in result["violations"] if not v.startswith("INFO ")
    ]
    assert len(real_violations) == 0, (
        f"Glob with matches should resolve, got: {real_violations}"
    )


def test_g388_catches_glob_with_no_matches(tmp_path, monkeypatch):
    """A glob pattern with zero matches must be flagged."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "docs" / "architecture").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    # No files matching the glob

    registry = fake_repo / "docs" / "architecture" / "CANONICAL_TRUTH_REGISTRY.md"
    registry.write_text(
        "### Domain: Glob test\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Authoritative source | `utils/missing_*.py` |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    (fake_repo / "scripts").mkdir()

    result = audit.gate_canonical_truth_registry_sync()
    real_violations = [
        v for v in result["violations"] if not v.startswith("INFO ")
    ]
    assert len(real_violations) == 1
    assert "missing_*.py" in real_violations[0]
    assert "zero matches" in real_violations[0]


def test_g388_skips_runtime_gitignored_paths(tmp_path, monkeypatch):
    """data/users.json is gitignored runtime data — must be skipped."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "docs" / "architecture").mkdir(parents=True)
    # data/users.json deliberately not created

    registry = fake_repo / "docs" / "architecture" / "CANONICAL_TRUTH_REGISTRY.md"
    registry.write_text(
        "### Domain: Test\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Authoritative source | `data/users.json` |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    (fake_repo / "scripts").mkdir()

    result = audit.gate_canonical_truth_registry_sync()
    real_violations = [
        v for v in result["violations"] if not v.startswith("INFO ")
    ]
    assert len(real_violations) == 0
    # The INFO note should be present
    info_notes = [v for v in result["violations"] if v.startswith("INFO ")]
    assert any("data/users.json" in v for v in info_notes)
    assert result["passed"] is True


def test_g388_skips_shadcn_aspirational_paths(tmp_path, monkeypatch):
    """shadcn paths are ASPIRATIONAL post-rollback — must be skipped."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "docs" / "architecture").mkdir(parents=True)
    # frontend/web/components.json deliberately not created

    registry = fake_repo / "docs" / "architecture" / "CANONICAL_TRUTH_REGISTRY.md"
    registry.write_text(
        "### Domain: Test\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Authoritative source | `frontend/web/components.json` |\n"
        "| Canonical interface | `lib/cn` |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    (fake_repo / "scripts").mkdir()

    result = audit.gate_canonical_truth_registry_sync()
    real_violations = [
        v for v in result["violations"] if not v.startswith("INFO ")
    ]
    assert len(real_violations) == 0
    info_notes = [v for v in result["violations"] if v.startswith("INFO ")]
    assert any("components.json" in v for v in info_notes)
    assert any("lib/cn" in v for v in info_notes)


def test_g388_handles_missing_registry_file(tmp_path, monkeypatch):
    """If the registry artifact itself is missing, gate must fail cleanly."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "empty_repo"
    fake_repo.mkdir()
    (fake_repo / "scripts").mkdir()

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )

    result = audit.gate_canonical_truth_registry_sync()
    assert result["passed"] is False
    assert len(result["violations"]) >= 1
    assert any(
        "CANONICAL_TRUTH_REGISTRY.md not found" in v
        for v in result["violations"]
    )


def test_g388_skips_non_path_bare_names(tmp_path, monkeypatch):
    """Backticked values like function names with no `/` must not be flagged."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "docs" / "architecture").mkdir(parents=True)

    registry = fake_repo / "docs" / "architecture" / "CANONICAL_TRUTH_REGISTRY.md"
    registry.write_text(
        "### Domain: Test\n\n"
        "| Field | Value |\n"
        "|---|---|\n"
        "| Canonical interface | `someFunction`, `AnotherIdentifier`, `module::method` |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    (fake_repo / "scripts").mkdir()

    result = audit.gate_canonical_truth_registry_sync()
    real_violations = [
        v for v in result["violations"] if not v.startswith("INFO ")
    ]
    assert len(real_violations) == 0, (
        f"Bare identifiers should be skipped, got: {real_violations}"
    )
