"""Regression tests for G393 (gate_organs_registry_coverage).

Authored v10.502 Stage C Arc D2 Batch 5e.

G393 enforces ORGANS_REGISTRY O5 doctrine ("every utils/.py file MUST
be claimable by exactly one organ"). It runs in TRANSITIONAL mode
with a snapshot ceiling on unclaimed modules. Stale references
(modules cited in registry but not on disk) always fail; only
coverage gaps are softened by the ceiling.

Post-correction state at Batch 5e: 527 actual modules, 369 claimed,
0 stale, 158 unclaimed (under ceiling 175).
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _fresh_audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit_script_under_test", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _has_info_prefix(v: str) -> bool:
    return v.startswith("INFO:") or v.startswith("INFO ")


def test_g393_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G393" in gate_ids


def test_g393_function_exists():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_organs_registry_coverage")
    assert callable(audit.gate_organs_registry_coverage)


def test_g393_passes_against_current_registry():
    """Post-Batch-5e: 158 unclaimed (under ceiling 175), 0 stale → PASS."""
    audit = _fresh_audit_module()
    result = audit.gate_organs_registry_coverage()
    assert result["id"] == "G393"
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert len(real_violations) == 0, (
        f"G393 violations against current state: {real_violations}"
    )
    assert result["passed"] is True


def test_g393_summary_reports_counts_and_coverage():
    audit = _fresh_audit_module()
    result = audit.gate_organs_registry_coverage()
    s = result["summary"]
    assert "actual=" in s
    assert "claimed=" in s
    assert "unclaimed=" in s
    assert "coverage=" in s
    assert "TRANSITIONAL ceiling" in s


def test_g393_catches_stale_reference(tmp_path, monkeypatch):
    """A registry citing a module that doesn't exist on disk must FAIL."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "docs" / "architecture").mkdir(parents=True)

    # One real module
    (fake_repo / "utils" / "real_module.py").write_text("# real\n", encoding="utf-8")
    # Registry cites BOTH real_module AND ghost_module
    (fake_repo / "docs" / "architecture" / "ORGANS_REGISTRY.md").write_text(
        "# Stub\n| Module | Resp |\n|---|---|\n"
        "| `utils/real_module.py` | a |\n"
        "| `utils/ghost_module.py` | b |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_organs_registry_coverage()
    assert result["passed"] is False
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert any(
        "ghost_module" in v and "stale" in v for v in real_violations
    ), f"Expected stale-reference violation, got: {real_violations}"


def test_g393_catches_unclaimed_ceiling_violation(tmp_path, monkeypatch):
    """A repo with 200 unclaimed modules exceeds ceiling 175 → FAIL."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "docs" / "architecture").mkdir(parents=True)

    # 200 utils modules, NONE referenced in registry
    for i in range(200):
        (fake_repo / "utils" / f"mod_{i:03d}.py").write_text(
            "# stub\n", encoding="utf-8"
        )
    (fake_repo / "docs" / "architecture" / "ORGANS_REGISTRY.md").write_text(
        "# empty\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_organs_registry_coverage()
    assert result["passed"] is False
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert any(
        "exceeds TRANSITIONAL ceiling" in v for v in real_violations
    ), f"Expected ceiling violation, got: {real_violations}"


def test_g393_passes_when_all_modules_claimed(tmp_path, monkeypatch):
    """A small repo with full coverage and 0 stale must PASS."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "docs" / "architecture").mkdir(parents=True)

    (fake_repo / "utils" / "alpha.py").write_text("# a\n", encoding="utf-8")
    (fake_repo / "utils" / "beta.py").write_text("# b\n", encoding="utf-8")
    (fake_repo / "utils" / "__init__.py").write_text("", encoding="utf-8")
    (fake_repo / "docs" / "architecture" / "ORGANS_REGISTRY.md").write_text(
        "| Mod | Resp |\n|---|---|\n"
        "| `utils/alpha.py` | a |\n"
        "| `utils/beta.py` | b |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_organs_registry_coverage()
    assert result["passed"] is True, (
        f"violations: {result['violations']}"
    )
    # __init__.py should be excluded from the actual count
    m = re.search(r"actual=(\d+)", result["summary"])
    assert m and int(m.group(1)) == 2


def test_g393_handles_missing_utils_dir(tmp_path, monkeypatch):
    audit = _fresh_audit_module()
    empty = tmp_path / "no_utils"
    empty.mkdir()
    (empty / "scripts").mkdir()
    monkeypatch.setattr(
        audit, "__file__", str(empty / "scripts" / "audit.py")
    )
    result = audit.gate_organs_registry_coverage()
    assert result["passed"] is False
    assert any(
        "utils/ directory not found" in v for v in result["violations"]
    )


def test_g393_handles_missing_registry(tmp_path, monkeypatch):
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "no_registry"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "utils" / "x.py").write_text("", encoding="utf-8")

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_organs_registry_coverage()
    assert result["passed"] is False
    assert any(
        "ORGANS_REGISTRY.md not found" in v for v in result["violations"]
    )
