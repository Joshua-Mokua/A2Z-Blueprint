"""Integration tests for v10.343 — Schema Lock sub-batch 2 (Option D).

12 tests across 4 sections:
  Section 1 — Three new schemas registered (3 tests)
  Section 2 — All 8 protected files validate (3 tests)
  Section 3 — Real drift findings captured (3 tests)
  Section 4 — Producer hooks wired (3 tests)
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(modname):
    for k in list(sys.modules):
        if k.startswith(modname):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Three new schemas registered
# ────────────────────────────────────────────────────────────────────

def test_v10343_kpi_library_schema_present():
    """data/_schemas/kpi_library.schema.json exists + locks v10.343."""
    p = REPO / "data" / "_schemas" / "kpi_library.schema.json"
    assert p.exists()
    schema = json.loads(p.read_text())
    assert schema.get("_lock_version") == "v10.343"
    assert "pillars" in schema.get("required", [])
    assert "role_kpis" in schema.get("required", [])


def test_v10343_org_hierarchy_schema_present():
    """data/_schemas/org_hierarchy_config.schema.json exists."""
    p = REPO / "data" / "_schemas" / "org_hierarchy_config.schema.json"
    assert p.exists()
    schema = json.loads(p.read_text())
    assert schema.get("_lock_version") == "v10.343"
    assert "synthetic_top" in schema.get("required", [])


def test_v10343_pipeline_schema_present():
    """data/_schemas/pipeline.schema.json exists + scaled to 0-100."""
    p = REPO / "data" / "_schemas" / "pipeline.schema.json"
    assert p.exists()
    schema = json.loads(p.read_text())
    assert schema.get("_lock_version") == "v10.343"
    # probability must be 0-100 scale to match canonical data
    prob_schema = schema["items"]["properties"]["probability"]
    assert prob_schema.get("maximum") == 100


# ────────────────────────────────────────────────────────────────────
# Section 2 — All 8 protected files validate
# ────────────────────────────────────────────────────────────────────

def test_v10343_eight_protected_files_after_arc():
    """≥8 protected files after v10.343 (5 from v10.342 + 3 new)."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import list_protected_files
    files = list_protected_files()
    assert len(files) >= 8, files
    new_files = {"kpi_library.json", "org_hierarchy_config.json", "pipeline.json"}
    assert new_files <= set(files), f"Missing: {new_files - set(files)}"


def test_v10343_all_protected_validate_clean():
    """All 8 protected files pass their schemas."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_all_protected
    report = validate_all_protected()
    if report["invalid_count"] > 0:
        details = []
        for f in report["files"]:
            if not f["valid"]:
                details.append(f"{f['file']}: {f['errors'][:2]}")
        assert False, "Invalid files: " + " | ".join(details)
    assert report["protected_count"] == 8


def test_v10343_g230_still_green():
    """G230 audit gate continues to pass with 8 schemas."""
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_data_schema_lock
    result = gate_data_schema_lock()
    assert result["passed"], result.get("violations")


# ────────────────────────────────────────────────────────────────────
# Section 3 — Drift findings captured in schemas
# ────────────────────────────────────────────────────────────────────

def test_v10343_kpi_direction_drift_documented():
    """4 KPI direction conventions all accepted (drift flagged for E)."""
    schema = json.loads(
        (REPO / "data" / "_schemas" / "kpi_library.schema.json").read_text()
    )
    direction_enum = (
        schema["properties"]["kpis"]["items"]["properties"]["direction"]["enum"]
    )
    # All four conventions in current data must be accepted
    for d in ("higher", "lower", "higher_better", "lower_better"):
        assert d in direction_enum


def test_v10343_pipeline_optional_fields_allowed():
    """pipeline schema does NOT require the 34 optional fields."""
    schema = json.loads(
        (REPO / "data" / "_schemas" / "pipeline.schema.json").read_text()
    )
    required = set(schema["items"]["required"])
    # Universal-10 are required
    assert "id" in required and "client_name" in required
    # Optional fields are NOT in required
    for opt in ("notes", "expected_close", "unit", "currency"):
        assert opt not in required, f"{opt} should be optional"


def test_v10343_org_hierarchy_polymorphic_allowed():
    """org_hierarchy schema tolerates _note documentation keys."""
    schema = json.loads(
        (REPO / "data" / "_schemas" / "org_hierarchy_config.schema.json").read_text()
    )
    # role_tiers must allow polymorphic values (int OR string _note)
    rt = schema["properties"]["role_tiers"]
    assert rt.get("additionalProperties") is True


# ────────────────────────────────────────────────────────────────────
# Section 4 — Producer hooks wired
# ────────────────────────────────────────────────────────────────────

def test_v10343_set_bank_target_schema_gated():
    """CascadeManager.set_bank_target now checks the schema (v10.343)."""
    text = (REPO / "utils" / "core.py").read_text()
    # The set_bank_target block has a v10.343 schema-lock check
    assert "v10.343" in text
    # And imports validator
    sb_idx = text.find("def set_bank_target")
    next_def_idx = text.find("def get_bank_target", sb_idx)
    method_body = text[sb_idx:next_def_idx]
    assert "validate_value" in method_body or "schema_validator" in method_body


def test_v10343_strategy_save_schema_gated():
    """pages/83_strategy.py _save calls validate_before_save (v10.343)."""
    text = (REPO / "pages" / "83_strategy.py").read_text()
    assert "validate_before_save" in text
    # _save returns False on rejection (boolean contract)
    save_idx = text.find("def _save(data):")
    next_def_idx = text.find("\ndef ", save_idx + 10)
    save_body = text[save_idx:next_def_idx]
    assert "return False" in save_body
    assert "return True" in save_body


def test_v10343_verifier_covers_new_checks():
    """verify_local_state.py covers v10.343 surface."""
    text = (REPO / "scripts" / "verify_local_state.py").read_text()
    assert "v10.343" in text
    # Verifier iterates schema names — check the names are referenced
    for name in ("kpi_library", "org_hierarchy_config", "pipeline"):
        assert name in text
    # Producer-hook checks present
    assert "set_bank_target" in text
    assert "83_strategy.py" in text
