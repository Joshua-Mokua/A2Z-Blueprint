"""Integration tests for v10.342 — Data schema lock (Option D).

14 tests across 4 sections:
  Section 1 — Validator engine mechanics (5 tests)
  Section 2 — Protected files validation (3 tests)
  Section 3 — Write-time validation (3 tests)
  Section 4 — Audit gate G230 (3 tests)
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
# Section 1 — Validator engine
# ────────────────────────────────────────────────────────────────────

def test_v10342_validator_type_check():
    """Type primitives — string, number, integer, boolean, null."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_value
    assert validate_value("hi", {"type": "string"})["valid"]
    assert not validate_value(42, {"type": "string"})["valid"]
    assert validate_value(42, {"type": "integer"})["valid"]
    assert not validate_value(True, {"type": "integer"})["valid"]  # bool is not int
    assert validate_value(3.14, {"type": "number"})["valid"]
    assert validate_value(True, {"type": "boolean"})["valid"]
    assert validate_value(None, {"type": "null"})["valid"]


def test_v10342_validator_required_and_properties():
    """Object validation with required + properties."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_value
    schema = {
        "type": "object",
        "required": ["a", "b"],
        "properties": {"a": {"type": "string"}, "b": {"type": "number"}},
    }
    assert validate_value({"a": "x", "b": 1}, schema)["valid"]
    bad = validate_value({"a": "x"}, schema)
    assert not bad["valid"]
    assert any("missing required" in e for e in bad["errors"])


def test_v10342_validator_enum_and_pattern():
    """enum + regex pattern."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_value
    enum_schema = {"type": "string", "enum": ["Green", "Amber", "Red"]}
    assert validate_value("Green", enum_schema)["valid"]
    assert not validate_value("GREEN", enum_schema)["valid"]
    pat_schema = {"type": "string", "pattern": r"^RULE_\w+$"}
    assert validate_value("RULE_001", pat_schema)["valid"]
    assert not validate_value("rule_001", pat_schema)["valid"]


def test_v10342_validator_array_items():
    """Array with item-schema enforcement."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_value
    schema = {"type": "array", "items": {"type": "string"}}
    assert validate_value(["a", "b"], schema)["valid"]
    bad = validate_value(["a", 1], schema)
    assert not bad["valid"]
    assert any("expected type string" in e for e in bad["errors"])


def test_v10342_validator_oneof_branch():
    """oneOf accepts at least one matching branch."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_value
    schema = {"oneOf": [{"type": "string"}, {"type": "null"}]}
    assert validate_value("hi", schema)["valid"]
    assert validate_value(None, schema)["valid"]
    assert not validate_value(42, schema)["valid"]


# ────────────────────────────────────────────────────────────────────
# Section 2 — Protected files
# ────────────────────────────────────────────────────────────────────

def test_v10342_five_schemas_registered():
    """≥5 schemas in data/_schemas/."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import list_protected_files
    files = list_protected_files()
    assert len(files) >= 5
    # All canonical files locked
    assert {"bank_targets.json", "strategic_initiatives.json",
            "execute_initiatives.json", "cost_allocation_rules.json",
            "segment_config.json"} <= set(files)


def test_v10342_all_protected_files_validate():
    """Every protected file is currently valid."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_all_protected
    report = validate_all_protected()
    if report["invalid_count"] > 0:
        details = []
        for f in report["files"]:
            if not f["valid"]:
                details.append(f"{f['file']}: {f['errors'][:2]}")
        assert False, "Invalid files: " + " | ".join(details)
    assert report["protected_count"] == report["valid_count"]


def test_v10342_strategic_initiatives_canonical_shape():
    """strategic_initiatives uses canonical Title-case + int counts."""
    si = json.loads((REPO / "data" / "strategic_initiatives.json").read_text())
    from collections import Counter
    rag = Counter(r.get("rag_status") for r in si)
    # No UPPERCASE leaked through
    for forbidden in ("GREEN", "AMBER", "RED"):
        assert rag.get(forbidden, 0) == 0, (
            f"{forbidden} found in canonical Title-case file"
        )
    # int-count fields are int
    for r in si[:5]:
        assert isinstance(r["linked_projects"], int)
        assert isinstance(r["stakeholders"], int)
        assert isinstance(r["key_milestones"], int)


# ────────────────────────────────────────────────────────────────────
# Section 3 — Write-time validation
# ────────────────────────────────────────────────────────────────────

def test_v10342_validate_before_save_rejects_drift():
    """Writing a scalar bank_targets entry fails validation."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_before_save
    # Scalar value (the v10.337 mistake)
    bad = {"PBT|2026": 999.0}
    res = validate_before_save("bank_targets.json", bad)
    assert not res["valid"]
    assert res["protected"]


def test_v10342_validate_before_save_accepts_canonical():
    """Writing a properly-shaped dict passes validation."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_before_save
    good = {"FOO|2027": {"target": 100.0, "buffer_pct": 5}}
    res = validate_before_save("bank_targets.json", good)
    assert res["valid"], res.get("errors")


def test_v10342_unprotected_files_pass_through():
    """A file with no schema is not flagged."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_before_save
    res = validate_before_save("not_a_real_file.json", {"x": 1})
    assert res["valid"]
    assert not res["protected"]


# ────────────────────────────────────────────────────────────────────
# Section 4 — G230 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10342_g230_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_data_schema_lock
    result = gate_data_schema_lock()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G230"


def test_v10342_g230_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G230", gate_data_schema_lock)' in text


def test_v10342_schemas_dir_documented():
    """data/_schemas/_README.json explains the pattern."""
    readme = REPO / "data" / "_schemas" / "_README.json"
    assert readme.exists()
    data = json.loads(readme.read_text())
    assert "_purpose" in data
    assert "_audit_gate" in data
    assert "G230" in data["_audit_gate"]
