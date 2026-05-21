"""Integration tests for v10.419 — role weight renormalization."""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Engine
# ────────────────────────────────────────────────────────────────────

def test_v10419_engine_exists():
    path = REPO / "utils" / "role_weight_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_role_weight",
        "def bank_role_weight_audit",
        "def compute_role_normalized_weights",
        "def migrate_normalize_all_roles",
        "def get_role_normalized_weight",
        "class RoleWeightAudit",
        "class BankRoleWeightAudit",
        "NORMALIZATION_TOLERANCE",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10419_zero_streamlit():
    text = (REPO / "utils" / "role_weight_engine.py").read_text()
    import re
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10419_audit_single_role():
    from utils.role_weight_engine import audit_role_weight
    a = audit_role_weight(
        "Test", ["K1", "K2", "K3"],
        {"K1": 0.20, "K2": 0.30, "K3": 0.50},
    )
    assert a.kpi_count == 3
    assert a.kpis_with_weight == 3
    assert a.kpis_missing_weight == 0
    assert abs(a.sum_of_weights - 1.0) < 1e-9
    assert a.is_normalized is True


def test_v10419_audit_under_normalized():
    from utils.role_weight_engine import audit_role_weight
    a = audit_role_weight(
        "Test", ["K1", "K2"],
        {"K1": 0.20, "K2": 0.30},  # sum = 0.50
    )
    assert abs(a.sum_of_weights - 0.50) < 1e-9
    assert a.is_normalized is False
    assert abs(a.normalization_factor - 2.0) < 1e-9


def test_v10419_audit_missing_weights():
    from utils.role_weight_engine import audit_role_weight
    a = audit_role_weight(
        "Test", ["K1", "K2", "K3"],
        {"K1": 0.20},  # K2, K3 missing
    )
    assert a.kpis_with_weight == 1
    assert a.kpis_missing_weight == 2


def test_v10419_audit_handles_empty():
    from utils.role_weight_engine import audit_role_weight
    a = audit_role_weight("Empty", [], {})
    assert a.kpi_count == 0
    assert a.sum_of_weights == 0.0
    assert a.is_normalized is False


def test_v10419_audit_handles_bad_input():
    from utils.role_weight_engine import audit_role_weight
    a = audit_role_weight("Bad", "not a list", {})  # type: ignore
    assert a.kpi_count == 0


def test_v10419_compute_normalized():
    from utils.role_weight_engine import compute_role_normalized_weights
    n = compute_role_normalized_weights(
        "Test", ["K1", "K2"], {"K1": 0.20, "K2": 0.30},
    )
    assert abs(sum(n.values()) - 1.0) < 1e-6
    assert abs(n["K1"] - 0.40) < 1e-9  # 0.20 / 0.50
    assert abs(n["K2"] - 0.60) < 1e-9


def test_v10419_normalize_zero_sum_fallback():
    """When all weights are 0 / missing, fall back to equal weights."""
    from utils.role_weight_engine import compute_role_normalized_weights
    n = compute_role_normalized_weights(
        "Test", ["K1", "K2", "K3", "K4"],
        {},  # all missing, default = 0.05 each → sum = 0.20
    )
    # Actually default is 0.05 so all get equal share — should sum to 1.0
    assert abs(sum(n.values()) - 1.0) < 1e-6
    # Equal split
    expected = 1.0 / 4
    for k in n:
        assert abs(n[k] - expected) < 1e-9


def test_v10419_bank_audit_skips_meta_keys():
    from utils.role_weight_engine import bank_role_weight_audit
    lib = {
        "role_kpis": {
            "RoleA": ["K1"],
            "RoleB": ["K1", "K2"],
            "_meta_key": ["should skip"],
        },
        "kpi_weights": {"K1": 0.50, "K2": 0.50},
    }
    a = bank_role_weight_audit(lib)
    assert a.total_roles == 2  # _meta excluded
    # RoleA: sum 0.50 (broken). RoleB: sum 1.00 (normalized)
    assert a.normalized_count == 1
    assert a.broken_count == 1


def test_v10419_migration_writes_normalized():
    from utils.role_weight_engine import migrate_normalize_all_roles
    lib = {
        "role_kpis": {
            "RoleA": ["K1", "K2"],
            "RoleB": ["K1"],
        },
        "kpi_weights": {"K1": 0.20, "K2": 0.30},
    }
    audit, normalized = migrate_normalize_all_roles(lib, write_back=False)
    assert len(normalized) == 2
    for role, w in normalized.items():
        assert abs(sum(w.values()) - 1.0) < 1e-6


def test_v10419_get_normalized_returns_none_for_missing():
    from utils.role_weight_engine import get_role_normalized_weight
    lib = {"role_normalized_weights": {"RoleA": {"K1": 0.5, "K2": 0.5}}}
    assert get_role_normalized_weight("RoleA", "K1", lib) == 0.5
    assert get_role_normalized_weight("MissingRole", "K1", lib) is None
    assert get_role_normalized_weight("RoleA", "MissingKPI", lib) is None


def test_v10419_dataclasses_json_serializable():
    from utils.role_weight_engine import audit_role_weight, bank_role_weight_audit
    a = audit_role_weight("X", ["K1"], {"K1": 0.5})
    b = bank_role_weight_audit({"role_kpis": {}, "kpi_weights": {}})
    import json
    json.dumps(a.to_dict())
    json.dumps(b.to_dict())


# ────────────────────────────────────────────────────────────────────
# Migration script
# ────────────────────────────────────────────────────────────────────

def test_v10419_migration_script_exists():
    path = REPO / "scripts" / "normalize_role_weights.py"
    assert path.exists()
    text = path.read_text()
    assert "migrate_normalize_all_roles" in text


# ────────────────────────────────────────────────────────────────────
# FastAPI
# ────────────────────────────────────────────────────────────────────

def test_v10419_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    for endpoint in (
        "/api/v1/role-weights/audit",
        "/api/v1/role-weights/{role}/audit",
        "/api/v1/role-weights/{role}/normalized",
        "/api/v1/role-weights/migrate",
    ):
        assert endpoint in text, f"Missing endpoint: {endpoint}"


# ────────────────────────────────────────────────────────────────────
# Gate
# ────────────────────────────────────────────────────────────────────

def test_v10419_g305_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10419_role_weight_renormalization
    r = gate_v10419_role_weight_renormalization()
    assert r["passed"], r.get("violations")
