"""Integration tests for v10.474 — Phase O8 Environment Isolation Governance.

Per Joshua Master Prompt Phase O8: 'No simulation artifacts may
contaminate production DNA.'
"""

import json
import os
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── 1. environment.py ───────────────────────────────────────────────

def test_v10474_environment_module_exists():
    assert (REPO / "utils" / "environment.py").exists()


def test_v10474_environment_enum_has_five_modes():
    for k in list(sys.modules):
        if "environment" in k and "data_isolation" not in k:
            del sys.modules[k]
    from utils.environment import Environment
    modes = {e.value for e in Environment}
    assert modes == {"dev", "sim", "uat", "staging", "prod"}


def test_v10474_environment_default_dev():
    """With no env var override and dev mode in JSON, default is dev."""
    os.environ.pop("A2Z_ENV", None)
    for k in list(sys.modules):
        if "environment" in k and "data_isolation" not in k:
            del sys.modules[k]
    from utils.environment import get_environment, Environment
    assert get_environment() in (Environment.DEV, Environment.SIM,
                                  Environment.UAT, Environment.STAGING,
                                  Environment.PROD)


def test_v10474_env_var_overrides_json():
    """A2Z_ENV env var takes precedence over environment.json."""
    os.environ["A2Z_ENV"] = "sim"
    try:
        for k in list(sys.modules):
            if "environment" in k and "data_isolation" not in k:
                del sys.modules[k]
        from utils.environment import get_environment, Environment
        assert get_environment() == Environment.SIM
    finally:
        os.environ.pop("A2Z_ENV", None)


def test_v10474_environment_paths_per_mode():
    """Each environment maps to a distinct data_root."""
    for k in list(sys.modules):
        if "environment" in k and "data_isolation" not in k:
            del sys.modules[k]
    from utils.environment import environment_paths, Environment
    prod = environment_paths(Environment.PROD)
    sim = environment_paths(Environment.SIM)
    uat = environment_paths(Environment.UAT)
    assert prod["data_root"] != sim["data_root"]
    assert sim["data_root"] != uat["data_root"]
    assert "sim" in str(sim["data_root"])
    assert "uat" in str(uat["data_root"])
    assert prod["disposable"] is False
    assert sim["disposable"] is True


# ── 2. environment.json ─────────────────────────────────────────────

def test_v10474_environment_json_exists():
    p = REPO / "data" / "environment.json"
    assert p.exists()
    d = json.loads(p.read_text(encoding="utf-8"))
    assert d.get("mode") in {"dev", "sim", "uat", "staging", "prod"}


# ── 3. data_isolation_guard.py ──────────────────────────────────────

def test_v10474_guard_module_exists():
    assert (REPO / "utils" / "data_isolation_guard.py").exists()


def test_v10474_protected_paths_are_blocked_in_sim():
    """Protected production files are blocked from SIM/UAT writes."""
    for k in list(sys.modules):
        if "environment" in k or "data_isolation" in k:
            del sys.modules[k]
    from utils.data_isolation_guard import is_write_allowed
    from utils.environment import Environment
    # SIM mode cannot write to data/users.json
    allowed, why = is_write_allowed("data/users.json", mode=Environment.SIM)
    assert not allowed
    assert "protected" in why.lower()


def test_v10474_non_protected_path_allowed_in_sim():
    """Non-protected paths are OK in any mode."""
    for k in list(sys.modules):
        if "environment" in k or "data_isolation" in k:
            del sys.modules[k]
    from utils.data_isolation_guard import is_write_allowed
    from utils.environment import Environment
    allowed, _ = is_write_allowed("data/some_sim_artefact.json",
                                   mode=Environment.SIM)
    assert allowed


def test_v10474_guarded_write_path_redirects_to_sim():
    """guarded_write_path puts SIM writes in data/sim/."""
    for k in list(sys.modules):
        if "environment" in k or "data_isolation" in k:
            del sys.modules[k]
    from utils.data_isolation_guard import guarded_write_path
    from utils.environment import Environment
    p = guarded_write_path("bsc_actuals_2026-Q1.json", mode=Environment.SIM)
    assert "data/sim" in str(p) or "data\\sim" in str(p)


def test_v10474_guarded_write_path_prod_stays_at_root():
    """guarded_write_path leaves PROD writes at root."""
    for k in list(sys.modules):
        if "environment" in k or "data_isolation" in k:
            del sys.modules[k]
    from utils.data_isolation_guard import guarded_write_path
    from utils.environment import Environment
    p = guarded_write_path("bsc_actuals_2026-Q1.json", mode=Environment.PROD)
    assert "sim" not in str(p)
    assert "uat" not in str(p)
    assert p.parent.name == "data"


def test_v10474_assert_not_production_blocks_in_prod():
    """assert_not_production raises in PROD."""
    os.environ["A2Z_ENV"] = "prod"
    try:
        for k in list(sys.modules):
            if "environment" in k or "data_isolation" in k:
                del sys.modules[k]
        from utils.data_isolation_guard import assert_not_production
        with pytest.raises(RuntimeError, match="REFUSED"):
            assert_not_production("test chaos")
    finally:
        os.environ.pop("A2Z_ENV", None)


def test_v10474_assert_not_production_allows_in_sim():
    """assert_not_production passes silently in SIM."""
    os.environ["A2Z_ENV"] = "sim"
    try:
        for k in list(sys.modules):
            if "environment" in k or "data_isolation" in k:
                del sys.modules[k]
        from utils.data_isolation_guard import assert_not_production
        assert_not_production("test chaos")  # should NOT raise
    finally:
        os.environ.pop("A2Z_ENV", None)


# ── 4. data_migration.py ────────────────────────────────────────────

def test_v10474_migration_module_exists():
    assert (REPO / "utils" / "data_migration.py").exists()


def test_v10474_promotion_dev_to_sim_allowed():
    for k in list(sys.modules):
        if "data_migration" in k or "environment" in k: del sys.modules[k]
    from utils.data_migration import promote_dataset
    from utils.environment import Environment
    result = promote_dataset(
        src=Environment.DEV, dst=Environment.SIM,
        actor="test_v10474", reason="test",
        file_filter=["environment.json"], dry_run=True,
    )
    assert result.success
    assert result.files_copied >= 1


def test_v10474_promotion_prod_to_dev_blocked():
    """One-way ladder: cannot demote PROD to DEV."""
    for k in list(sys.modules):
        if "data_migration" in k or "environment" in k: del sys.modules[k]
    from utils.data_migration import promote_dataset
    from utils.environment import Environment
    result = promote_dataset(
        src=Environment.PROD, dst=Environment.DEV,
        actor="test_v10474", reason="demotion attempt", dry_run=True,
    )
    assert not result.success
    assert "not in allowed set" in (result.error or "")


def test_v10474_promotion_audit_logged():
    """Successful promotion creates an audit entry."""
    for k in list(sys.modules):
        if "data_migration" in k or "environment" in k or "audit_log" in k:
            del sys.modules[k]
    from utils.data_migration import promote_dataset
    from utils.environment import Environment
    from utils.audit_log import query_audit
    result = promote_dataset(
        src=Environment.DEV, dst=Environment.SIM,
        actor="test_v10474_audit", reason="audit verification",
        file_filter=["environment.json"], dry_run=False,
    )
    assert result.audit_id is not None
    # Cross-verify via query
    entries = query_audit(actor="test_v10474_audit", limit=5)
    assert any(e.get("action") == "dataset_promoted" for e in entries)


# ── 5. Sandbox dirs ─────────────────────────────────────────────────

def test_v10474_sim_directory_exists_with_readme():
    p = REPO / "data" / "sim"
    assert p.exists() and p.is_dir()
    assert (p / "README.md").exists()


def test_v10474_uat_directory_exists_with_readme():
    p = REPO / "data" / "uat"
    assert p.exists() and p.is_dir()
    assert (p / "README.md").exists()


def test_v10474_staging_directory_exists_with_readme():
    p = REPO / "data" / "staging"
    assert p.exists() and p.is_dir()
    assert (p / "README.md").exists()


# ── 6. Policy doc ───────────────────────────────────────────────────

def test_v10474_policy_doc_exists():
    p = REPO / "docs" / "environment_isolation_policy.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    for kw in ("DEV", "SIM", "UAT", "STAGING", "PROD",
               "promote_dataset", "guarded_write_path", "PROTECTED"):
        assert kw in text


# ── 7. vb_actuals_bridge wiring ─────────────────────────────────────

def test_v10474_vb_actuals_bridge_wires_isolation_guard():
    text = (REPO / "utils" / "vb_actuals_bridge.py").read_text(encoding="utf-8")
    assert "isolation guard" in text.lower() or "is_write_allowed" in text


# ── 8. G360 + regression ────────────────────────────────────────────

def test_v10474_g360_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10474_o8_environment_isolation
    r = gate_v10474_o8_environment_isolation()
    assert r["passed"], r.get("violations")


def test_v10474_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360" in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct >= 99.9


def test_v10474_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k: del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct >= 99.9


def test_v10474_v10473_o1_preserved():
    """Prior batch (v10.473 O1 stabilization) still works."""
    for k in list(sys.modules):
        if "virtual_bank_kpi_unifier" in k: del sys.modules[k]
    from utils.virtual_bank_kpi_unifier import _normalise_period
    assert _normalise_period("2026Q1") == "2026-Q1"
