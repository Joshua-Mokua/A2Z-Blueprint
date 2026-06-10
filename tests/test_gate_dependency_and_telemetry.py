"""Regression tests for G391 (canonical_dependency_map_sync) and G392
(telemetry_event_naming).

Authored v10.502 Stage C Arc D2 Batch 5d.

Both gates close stated-vs-enforced gaps named directly in their
artifacts' doctrine:

- CANONICAL_DEPENDENCY_MAP D4 cited `gate_canonical_dependency_map_sync`
  by name; the gate did not exist before Batch 5d.
- TELEMETRY_MAP's "Stage C gates planned" section listed
  `gate_telemetry_event_naming`; the gate did not exist before
  Batch 5d.

Both now exist. Both pass against the post-correction state.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _fresh_audit_module():
    """Load scripts/audit.py by explicit file path."""
    spec = importlib.util.spec_from_file_location(
        "audit_script_under_test", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _has_info_prefix(v: str) -> bool:
    return v.startswith("INFO:") or v.startswith("INFO ")


# ────────────────────────────────────────────────────────────────────
# G391 — canonical_dependency_map_sync
# ────────────────────────────────────────────────────────────────────

def test_g391_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G391" in gate_ids


def test_g391_function_exists():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_canonical_dependency_map_sync")
    assert callable(audit.gate_canonical_dependency_map_sync)


def test_g391_passes_against_current_utils_tree():
    """Current state: 2 known SCCs + 32 self-loops; allowlist matches.
    Gate must PASS."""
    audit = _fresh_audit_module()
    result = audit.gate_canonical_dependency_map_sync()
    assert result["id"] == "G391"
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert len(real_violations) == 0, (
        f"G391 violations against current state: {real_violations}"
    )
    assert result["passed"] is True


def test_g391_summary_reports_counts():
    audit = _fresh_audit_module()
    result = audit.gate_canonical_dependency_map_sync()
    s = result["summary"]
    assert "modules=" in s
    assert "multi_module_cycles=" in s
    assert "self_loops=" in s


def test_g391_surfaces_self_loops_as_info():
    """Self-loops should surface as INFO with doctrine exemption note."""
    audit = _fresh_audit_module()
    result = audit.gate_canonical_dependency_map_sync()
    info_lines = [v for v in result["violations"] if _has_info_prefix(v)]
    assert any("self-loop" in v.lower() for v in info_lines), (
        f"Expected self-loop INFO line, got: {info_lines}"
    )


def test_g391_catches_new_multi_module_cycle(tmp_path, monkeypatch):
    """If a NEW multi-module cycle appears outside the allowlist, gate FAILS."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()

    # Create a NEW 3-module cycle: alpha -> beta -> gamma -> alpha
    (fake_repo / "utils" / "alpha.py").write_text(
        "from utils.beta import x\n", encoding="utf-8"
    )
    (fake_repo / "utils" / "beta.py").write_text(
        "from utils.gamma import y\n", encoding="utf-8"
    )
    (fake_repo / "utils" / "gamma.py").write_text(
        "from utils.alpha import z\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_canonical_dependency_map_sync()
    assert result["passed"] is False
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert any(
        "NEW multi-module cycle" in v for v in real_violations
    ), f"Expected NEW cycle violation, got: {real_violations}"
    assert any(
        "alpha" in v and "beta" in v and "gamma" in v
        for v in real_violations
    )


def test_g391_allows_known_cycles(tmp_path, monkeypatch):
    """A repo where the only multi-module cycles match the allowlist must PASS."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()

    # Recreate the credit doctrine cycle from KNOWN_CYCLES
    (fake_repo / "utils" / "credit_doctrine_audit.py").write_text(
        "from utils.credit_section_audit_engine import x\n", encoding="utf-8"
    )
    (fake_repo / "utils" / "credit_section_audit_engine.py").write_text(
        "from utils.credit_doctrine_audit import y\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_canonical_dependency_map_sync()
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert len(real_violations) == 0, (
        f"Allowlisted cycle should not violate, got: {real_violations}"
    )


def test_g391_handles_self_loops_as_info_not_violation(tmp_path, monkeypatch):
    """Self-import in a single module surfaces as INFO, not violation."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()

    (fake_repo / "utils" / "selfref.py").write_text(
        "from utils.selfref import _internal\n", encoding="utf-8"
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_canonical_dependency_map_sync()
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert len(real_violations) == 0
    info_lines = [v for v in result["violations"] if _has_info_prefix(v)]
    assert any("self-loop" in v.lower() for v in info_lines)


def test_g391_handles_missing_utils_dir(tmp_path, monkeypatch):
    audit = _fresh_audit_module()
    empty = tmp_path / "no_utils"
    empty.mkdir()
    (empty / "scripts").mkdir()
    monkeypatch.setattr(
        audit, "__file__", str(empty / "scripts" / "audit.py")
    )
    result = audit.gate_canonical_dependency_map_sync()
    assert result["passed"] is False
    assert any("utils/ directory not found" in v for v in result["violations"])


# ────────────────────────────────────────────────────────────────────
# G392 — telemetry_event_naming
# ────────────────────────────────────────────────────────────────────

def test_g392_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G392" in gate_ids


def test_g392_function_exists():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_telemetry_event_naming")
    assert callable(audit.gate_telemetry_event_naming)


def test_g392_passes_against_current_telemetry_map():
    """After Batch 5d added 4 missing events, gate must PASS."""
    audit = _fresh_audit_module()
    result = audit.gate_telemetry_event_naming()
    assert result["id"] == "G392"
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert len(real_violations) == 0, (
        f"G392 violations against current state: {real_violations}"
    )
    assert result["passed"] is True


def test_g392_summary_reports_counts():
    audit = _fresh_audit_module()
    result = audit.gate_telemetry_event_naming()
    s = result["summary"]
    assert "documented=" in s
    assert "actual=" in s
    assert "undeclared=" in s


def test_g392_catches_undeclared_event(tmp_path, monkeypatch):
    """A literal _audit() event not in TELEMETRY_MAP must be flagged."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "docs" / "architecture").mkdir(parents=True)

    # TELEMETRY_MAP documents only API_FOO
    (fake_repo / "docs" / "architecture" / "TELEMETRY_MAP.md").write_text(
        "# Stub\n| Event |\n|---|\n| `API_FOO` | trigger |\n",
        encoding="utf-8",
    )
    # Code emits BOTH API_FOO (documented) AND API_BAR (undeclared)
    (fake_repo / "utils" / "api_test.py").write_text(
        textwrap.dedent("""
            def _audit(action, user, detail=""): pass

            def handler():
                _audit("API_FOO", {})
                _audit("API_BAR", {})  # undeclared
        """),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_telemetry_event_naming()
    assert result["passed"] is False
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert len(real_violations) == 1
    assert "API_BAR" in real_violations[0]
    assert "T1 + T2" in real_violations[0]


def test_g392_accepts_documented_events(tmp_path, monkeypatch):
    """All events documented → gate PASSES."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "docs" / "architecture").mkdir(parents=True)

    (fake_repo / "docs" / "architecture" / "TELEMETRY_MAP.md").write_text(
        "| `API_X` | a |\n| `API_Y` | b |\n", encoding="utf-8",
    )
    (fake_repo / "utils" / "api_test.py").write_text(
        textwrap.dedent("""
            def _audit(a, u, d=""): pass
            def h():
                _audit("API_X", {})
                _audit("API_Y", {})
        """),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_telemetry_event_naming()
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert len(real_violations) == 0
    assert result["passed"] is True


def test_g392_ignores_dynamically_constructed_event_names(tmp_path, monkeypatch):
    """Events constructed via f-strings can't be checked; gate skips silently."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "docs" / "architecture").mkdir(parents=True)

    # Empty telemetry map
    (fake_repo / "docs" / "architecture" / "TELEMETRY_MAP.md").write_text(
        "# Stub\n", encoding="utf-8",
    )
    (fake_repo / "utils" / "api_dyn.py").write_text(
        textwrap.dedent("""
            def _audit(a, u, d=""): pass
            def h(action):
                _audit(f"API_{action}", {})
                event = "API_DYNAMIC"
                _audit(event, {})
        """),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_telemetry_event_naming()
    # Both audit calls have non-Constant first arg → skipped
    real_violations = [
        v for v in result["violations"] if not _has_info_prefix(v)
    ]
    assert len(real_violations) == 0


def test_g392_handles_missing_telemetry_map(tmp_path, monkeypatch):
    audit = _fresh_audit_module()
    empty = tmp_path / "no_tm"
    empty.mkdir()
    (empty / "scripts").mkdir()
    monkeypatch.setattr(
        audit, "__file__", str(empty / "scripts" / "audit.py")
    )
    result = audit.gate_telemetry_event_naming()
    assert result["passed"] is False
    assert any(
        "TELEMETRY_MAP.md not found" in v for v in result["violations"]
    )
