"""Integration tests for v10.420 — KPI library dedup."""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10420_engine_exists():
    path = REPO / "utils" / "kpi_dedup_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_kpi_dedup",
        "def migrate_dedup_kpi_library",
        "class AliasPairAudit",
        "class DedupAudit",
        "class DedupMigrationResult",
        "KPI_ALIAS_PAIRS",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10420_zero_streamlit():
    text = (REPO / "utils" / "kpi_dedup_engine.py").read_text()
    import re
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10420_alias_pairs_constant():
    for k in list(sys.modules):
        if "kpi_dedup" in k:
            del sys.modules[k]
    from utils.kpi_dedup_engine import KPI_ALIAS_PAIRS
    assert KPI_ALIAS_PAIRS == {
        "NEW_ACCOUNTS": "K006",
        "K069": "K024",
        "K048": "K028",
        "NIM": "NET_INTEREST_MARGIN",
    }


def test_v10420_audit_synthetic():
    from utils.kpi_dedup_engine import audit_kpi_dedup
    lib = {
        "kpis": [{"id": "NEW_ACCOUNTS", "name": "x"}, {"id": "K006", "name": "x"}],
        "role_kpis": {"R": ["NEW_ACCOUNTS"]},
        "kpi_weights": {"NEW_ACCOUNTS": 0.5},
    }
    a = audit_kpi_dedup(lib, {})
    assert a.total_pairs == 4
    new_accounts = next(p for p in a.pair_audits if p.duplicate_id == "NEW_ACCOUNTS")
    assert new_accounts.duplicate_in_kpis is True
    assert new_accounts.duplicate_role_refs == 1
    assert new_accounts.duplicate_in_kpi_weights is True


def test_v10420_migration_consolidates_references():
    from utils.kpi_dedup_engine import migrate_dedup_kpi_library
    lib = {
        "kpis": [
            {"id": "NEW_ACCOUNTS", "name": "x"},
            {"id": "K006", "name": "x"},
            {"id": "OTHER", "name": "y"},
        ],
        "role_kpis": {"R": ["NEW_ACCOUNTS", "OTHER"]},
        "kpi_weights": {"NEW_ACCOUNTS": 0.5, "OTHER": 0.5},
    }
    bt = {}
    result = migrate_dedup_kpi_library(
        lib, bt, write_back=False, rebuild_normalized_weights=False,
    )
    assert result.pairs_migrated == 4
    # NEW_ACCOUNTS replaced with K006 in role list
    assert set(lib["role_kpis"]["R"]) == {"K006", "OTHER"}
    # NEW_ACCOUNTS removed from kpis list
    assert {k["id"] for k in lib["kpis"]} == {"K006", "OTHER"}
    # kpi_weights cleaned
    assert "NEW_ACCOUNTS" not in lib["kpi_weights"]


def test_v10420_migration_dedupes_overlap():
    """When a role has BOTH duplicate and canonical, dedupe to one entry."""
    from utils.kpi_dedup_engine import migrate_dedup_kpi_library
    lib = {
        "kpis": [{"id": "K069", "name": "x"}, {"id": "K024", "name": "x"}],
        "role_kpis": {"R": ["K069", "K024"]},
        "kpi_weights": {},
    }
    migrate_dedup_kpi_library(
        lib, {}, write_back=False, rebuild_normalized_weights=False,
    )
    assert lib["role_kpis"]["R"] == ["K024"]  # deduped


def test_v10420_migration_bank_targets_inheritance():
    """If duplicate has bank_target but canonical doesn't, canonical inherits."""
    from utils.kpi_dedup_engine import migrate_dedup_kpi_library
    lib = {
        "kpis": [], "role_kpis": {}, "kpi_weights": {},
    }
    bt = {"2026": {"NEW_ACCOUNTS": {"target": 100, "period": "2026"}}}
    migrate_dedup_kpi_library(
        lib, bt, write_back=False, rebuild_normalized_weights=False,
    )
    assert "NEW_ACCOUNTS" not in bt["2026"]
    assert "K006" in bt["2026"]
    assert bt["2026"]["K006"]["target"] == 100


def test_v10420_migration_idempotent():
    from utils.kpi_dedup_engine import migrate_dedup_kpi_library
    lib = {
        "kpis": [{"id": "NEW_ACCOUNTS", "name": "x"}, {"id": "K006", "name": "x"}],
        "role_kpis": {"R": ["NEW_ACCOUNTS"]},
        "kpi_weights": {"NEW_ACCOUNTS": 0.5},
    }
    r1 = migrate_dedup_kpi_library(lib, {}, write_back=False, rebuild_normalized_weights=False)
    r2 = migrate_dedup_kpi_library(lib, {}, write_back=False, rebuild_normalized_weights=False)
    # Second run should have no role updates
    assert r2.role_kpis_updated == 0


def test_v10420_metadata_stamp():
    from utils.kpi_dedup_engine import migrate_dedup_kpi_library
    lib = {"kpis": [], "role_kpis": {}, "kpi_weights": {}}
    migrate_dedup_kpi_library(lib, {}, write_back=False, rebuild_normalized_weights=False)
    assert "_v10420_dedup_complete" in lib
    assert lib["_v10420_dedup_complete"]["shipped"] == "v10.420"


def test_v10420_dataclasses_json_serializable():
    from utils.kpi_dedup_engine import audit_kpi_dedup, migrate_dedup_kpi_library
    a = audit_kpi_dedup({"kpis": [], "role_kpis": {}, "kpi_weights": {}}, {})
    r = migrate_dedup_kpi_library(
        {"kpis": [], "role_kpis": {}, "kpi_weights": {}}, {},
        write_back=False, rebuild_normalized_weights=False,
    )
    import json
    json.dumps(a.to_dict())
    json.dumps(r.to_dict())


def test_v10420_migration_script_exists():
    path = REPO / "scripts" / "dedup_kpi_library.py"
    assert path.exists()


def test_v10420_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    for endpoint in (
        "/api/v1/kpi-dedup/audit",
        "/api/v1/kpi-dedup/migrate",
    ):
        assert endpoint in text, f"Missing: {endpoint}"


def test_v10420_real_library_already_deduped():
    """After running the migration in this sandbox, audit shows 0 pending."""
    for k in list(sys.modules):
        if "kpi_dedup" in k:
            del sys.modules[k]
    from utils.kpi_dedup_engine import audit_kpi_dedup
    audit = audit_kpi_dedup()
    assert audit.pending == 0, f"{audit.pending} pairs still pending"
    assert audit.already_migrated == 4


def test_v10420_g306_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10420_kpi_library_dedup
    r = gate_v10420_kpi_library_dedup()
    assert r["passed"], r.get("violations")
