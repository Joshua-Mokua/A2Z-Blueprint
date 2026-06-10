"""Regression tests for G389 (api_contract_inventory) and G390
(data_dictionary_tracking_claims).

Authored v10.502 Stage C Arc D2 Batch 5c.

Both gates make doctrine debt VISIBLE rather than instantly closing it:

- G389 runs in TRANSITIONAL mode — accepts the current 81-vs-276
  documented/actual gap by setting a ceiling at 300, but FAILS if the
  actual surface grows beyond that ceiling without a corresponding
  doctrine update.
- G390 enforces git-tracked / gitignored claims in DATA_DICTIONARY by
  cross-checking each row against `git check-ignore` + `git ls-files`.
  After Batch 5c's 4 surgical corrections, the current state passes.

These tests verify the contracts won't regress.
"""
from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
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


# ────────────────────────────────────────────────────────────────────
# G389 — api_contract_inventory
# ────────────────────────────────────────────────────────────────────

def test_g389_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G389" in gate_ids


def test_g389_function_exists():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_api_contract_inventory")
    assert callable(audit.gate_api_contract_inventory)


def test_g389_passes_against_current_artifacts():
    """Current state: actual <= TRANSITIONAL_CEILING. Gate must PASS."""
    audit = _fresh_audit_module()
    result = audit.gate_api_contract_inventory()
    assert result["id"] == "G389"
    real_violations = [
        v for v in result["violations"] if not (v.startswith("INFO:") or v.startswith("INFO "))
    ]
    assert len(real_violations) == 0, (
        f"G389 violations against current state: {real_violations}"
    )
    assert result["passed"] is True


def test_g389_summary_reports_counts():
    """Summary must include documented/actual/undocumented counts."""
    audit = _fresh_audit_module()
    result = audit.gate_api_contract_inventory()
    s = result["summary"]
    assert "documented=" in s
    assert "actual=" in s
    assert "undocumented=" in s
    assert "TRANSITIONAL ceiling" in s


def test_g389_reports_undocumented_endpoints_as_info():
    """Drift surfaces as INFO violations, not real ones, in TRANSITIONAL mode."""
    audit = _fresh_audit_module()
    result = audit.gate_api_contract_inventory()
    info_lines = [v for v in result["violations"] if v.startswith("INFO:") or v.startswith("INFO ")]
    # Expect at least one INFO line with counts
    assert any("documented=" in v and "actual=" in v for v in info_lines), (
        "Expected INFO line with counts"
    )


def test_g389_handles_missing_contract_file(tmp_path, monkeypatch):
    """Missing artifact triggers clean failure, not crash."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "empty_repo"
    fake_repo.mkdir()
    (fake_repo / "scripts").mkdir()
    (fake_repo / "utils").mkdir()
    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_api_contract_inventory()
    assert result["passed"] is False
    assert any("API_CONTRACTS.md not found" in v for v in result["violations"])


def test_g389_ceiling_enforcement_via_synthetic_router(tmp_path, monkeypatch):
    """If actual surface exceeds the transitional ceiling, gate FAILS."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "docs" / "architecture").mkdir(parents=True)

    # Documented: zero endpoints in the contract
    (fake_repo / "docs" / "architecture" / "API_CONTRACTS.md").write_text(
        "# Stub contract\n\n(no endpoints documented)\n",
        encoding="utf-8",
    )

    # Actual: synthesize 301 endpoints across one big router file
    router_src = ["from fastapi import APIRouter", "router = APIRouter()"]
    for i in range(301):
        router_src.append(f'@router.get("/api/synthetic/endpoint_{i}")')
        router_src.append(f"def handler_{i}(): return {{}}")
        router_src.append("")
    (fake_repo / "utils" / "api_synthetic.py").write_text(
        "\n".join(router_src), encoding="utf-8"
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_api_contract_inventory()
    assert result["passed"] is False
    real_violations = [
        v for v in result["violations"] if not (v.startswith("INFO:") or v.startswith("INFO "))
    ]
    assert any(
        "exceeds transitional ceiling" in v for v in real_violations
    ), f"Expected ceiling violation, got: {real_violations}"


def test_g389_ast_walk_finds_all_decorator_types(tmp_path, monkeypatch):
    """Gate must recognize @app.get, @router.post, @<name>_router.put forms."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "utils").mkdir()
    (fake_repo / "docs" / "architecture").mkdir(parents=True)

    (fake_repo / "docs" / "architecture" / "API_CONTRACTS.md").write_text(
        "# Stub\n", encoding="utf-8"
    )
    (fake_repo / "utils" / "api_mixed.py").write_text(
        "from fastapi import FastAPI, APIRouter\n"
        "app = FastAPI()\n"
        "router = APIRouter()\n"
        "custom_router = APIRouter()\n"
        "\n"
        '@app.get("/api/a")\n'
        "def a(): pass\n"
        "\n"
        '@router.post("/api/b")\n'
        "def b(): pass\n"
        "\n"
        '@custom_router.put("/api/c")\n'
        "def c(): pass\n"
        "\n"
        '@app.delete("/api/d")\n'
        "async def d(): pass\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_api_contract_inventory()
    # Expect 4 actual endpoints discovered
    s = result["summary"]
    m = re.search(r"actual=(\d+)", s)
    assert m and int(m.group(1)) == 4, f"Expected actual=4, got summary: {s}"


# ────────────────────────────────────────────────────────────────────
# G390 — data_dictionary_tracking_claims
# ────────────────────────────────────────────────────────────────────

def test_g390_is_registered_in_gates_table():
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G390" in gate_ids


def test_g390_function_exists():
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_data_dictionary_tracking_claims")
    assert callable(audit.gate_data_dictionary_tracking_claims)


def test_g390_passes_against_current_dictionary():
    """After Batch 5c corrections, every claim should resolve cleanly."""
    audit = _fresh_audit_module()
    result = audit.gate_data_dictionary_tracking_claims()
    assert result["id"] == "G390"
    real_violations = [
        v for v in result["violations"] if not (v.startswith("INFO:") or v.startswith("INFO "))
    ]
    assert len(real_violations) == 0, (
        f"G390 violations against current state: {real_violations}"
    )
    assert result["passed"] is True


def test_g390_summary_reports_counts():
    audit = _fresh_audit_module()
    result = audit.gate_data_dictionary_tracking_claims()
    s = result["summary"]
    assert "rows_checked=" in s
    assert "rows_ok=" in s
    assert "violations=" in s


def test_g390_handles_missing_dictionary(tmp_path, monkeypatch):
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "empty_repo"
    fake_repo.mkdir()
    (fake_repo / "scripts").mkdir()
    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_data_dictionary_tracking_claims()
    assert result["passed"] is False
    assert any(
        "DATA_DICTIONARY.md not found" in v for v in result["violations"]
    )


def test_g390_catches_wrong_git_tracked_claim(tmp_path, monkeypatch):
    """A row claiming git-tracked for a gitignored file must fail."""
    audit = _fresh_audit_module()
    # Set up minimal git repo with a gitignored file
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "docs" / "architecture").mkdir(parents=True)
    (fake_repo / "data").mkdir()

    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.local"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=fake_repo, check=True
    )
    (fake_repo / ".gitignore").write_text("data/secret.json\n", encoding="utf-8")
    (fake_repo / "data" / "secret.json").write_text("{}", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=fake_repo, check=True
    )

    # Dictionary claims data/secret.json is git-tracked — it's actually ignored
    (fake_repo / "docs" / "architecture" / "DATA_DICTIONARY.md").write_text(
        "| File | Owner | Retention |\n"
        "|---|---|---|\n"
        "| `data/secret.json` | someone | git-tracked |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_data_dictionary_tracking_claims()
    assert result["passed"] is False
    real_violations = [
        v for v in result["violations"] if not (v.startswith("INFO:") or v.startswith("INFO "))
    ]
    assert len(real_violations) == 1
    assert "data/secret.json" in real_violations[0]
    assert "claimed git-tracked" in real_violations[0]


def test_g390_accepts_correct_claims(tmp_path, monkeypatch):
    """Mix of correct git-tracked and gitignored claims must all pass."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "docs" / "architecture").mkdir(parents=True)
    (fake_repo / "data").mkdir()

    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.local"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=fake_repo, check=True
    )
    (fake_repo / ".gitignore").write_text("data/runtime.json\n", encoding="utf-8")
    (fake_repo / "data" / "real.json").write_text("{}", encoding="utf-8")
    (fake_repo / "data" / "runtime.json").write_text("{}", encoding="utf-8")
    subprocess.run(
        ["git", "add", ".gitignore", "data/real.json"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=fake_repo, check=True
    )

    (fake_repo / "docs" / "architecture" / "DATA_DICTIONARY.md").write_text(
        "| File | Owner | Retention |\n"
        "|---|---|---|\n"
        "| `data/real.json` | a | git-tracked |\n"
        "| `data/runtime.json` | b | gitignored |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_data_dictionary_tracking_claims()
    assert result["passed"] is True, f"violations: {result['violations']}"
    s = result["summary"]
    m = re.search(r"rows_ok=(\d+)", s)
    assert m and int(m.group(1)) == 2


def test_g390_catches_wrong_gitignored_claim(tmp_path, monkeypatch):
    """A row claiming gitignored for a tracked file must fail."""
    audit = _fresh_audit_module()
    fake_repo = tmp_path / "fake_repo"
    (fake_repo / "scripts").mkdir(parents=True)
    (fake_repo / "docs" / "architecture").mkdir(parents=True)
    (fake_repo / "data").mkdir()

    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.local"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "config", "user.name", "test"], cwd=fake_repo, check=True
    )
    (fake_repo / "data" / "tracked.json").write_text("{}", encoding="utf-8")
    subprocess.run(
        ["git", "add", "data/tracked.json"], cwd=fake_repo, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"], cwd=fake_repo, check=True
    )

    (fake_repo / "docs" / "architecture" / "DATA_DICTIONARY.md").write_text(
        "| File | Owner | Retention |\n"
        "|---|---|---|\n"
        "| `data/tracked.json` | a | gitignored |\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        audit, "__file__", str(fake_repo / "scripts" / "audit.py")
    )
    result = audit.gate_data_dictionary_tracking_claims()
    assert result["passed"] is False
    real_violations = [
        v for v in result["violations"] if not (v.startswith("INFO:") or v.startswith("INFO "))
    ]
    assert len(real_violations) == 1
    assert "data/tracked.json" in real_violations[0]
    assert "claimed gitignored" in real_violations[0]
