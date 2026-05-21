"""Integration tests for v10.343 — Schema lock extension (Option D, sub-batch 2).

7 tests across 3 sections:
  Section 1 — Three new schemas registered + valid (3 tests)
  Section 2 — Field/value invariants for each newly locked file (3 tests)
  Section 3 — G230 strengthened threshold (1 test)
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
# Section 1 — Three new schemas registered + valid
# ────────────────────────────────────────────────────────────────────

def test_v10343_three_new_schemas_registered():
    """kpi_library, org_hierarchy_config, pipeline now protected."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import list_protected_files
    files = set(list_protected_files())
    assert {
        "kpi_library.json",
        "org_hierarchy_config.json",
        "pipeline.json",
    } <= files, f"Missing v10.343 schemas: {files}"
    # Total should now be ≥8
    assert len(files) >= 8


def test_v10343_all_eight_protected_files_validate():
    """All 8 protected files (5 from v10.342 + 3 new) validate clean."""
    _reimport("utils.schema_validator")
    from utils.schema_validator import validate_all_protected
    report = validate_all_protected()
    if report["invalid_count"] > 0:
        details = []
        for f in report["files"]:
            if not f["valid"]:
                details.append(f"{f['file']}: {f['errors'][:2]}")
        assert False, "Invalid: " + " | ".join(details)
    assert report["valid_count"] >= 8


def test_v10343_known_divergence_documented():
    """kpi_library schema documents the direction-naming divergence."""
    schema_path = REPO / "data" / "_schemas" / "kpi_library.schema.json"
    schema = json.loads(schema_path.read_text())
    assert "_known_divergence" in schema
    div = schema["_known_divergence"]
    assert div["field"] == "direction"
    # Both naming conventions surfaced
    assert "consumers_using_short_form" in div
    assert "consumers_using_long_form" in div


# ────────────────────────────────────────────────────────────────────
# Section 2 — Field/value invariants
# ────────────────────────────────────────────────────────────────────

def test_v10343_pipeline_probability_is_percent_not_fraction():
    """Pipeline probability values are 0-100 (canonical), not 0-1."""
    pipeline = json.loads((REPO / "data" / "pipeline.json").read_text())
    above_one = sum(1 for r in pipeline if isinstance(r.get("probability"), (int, float)) and r["probability"] > 1)
    assert above_one > 0, "Pipeline data should use 0-100 probability (canonical)"


def test_v10343_kpi_library_direction_uses_active_enum():
    """All kpi.direction values fall in the locked enum set."""
    kpi_lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    valid_directions = {"higher", "lower", "higher_better", "lower_better"}
    bad = []
    for k in kpi_lib.get("kpis", []):
        d = k.get("direction")
        if d is not None and d not in valid_directions:
            bad.append((k.get("id"), d))
    assert not bad, f"kpi.direction drift: {bad[:5]}"


def test_v10343_org_hierarchy_synthetic_top_is_object():
    """synthetic_top must be a dict per canonical shape (not legacy string)."""
    org = json.loads((REPO / "data" / "org_hierarchy_config.json").read_text())
    assert isinstance(org["synthetic_top"], dict)
    assert "enabled" in org["synthetic_top"]


# ────────────────────────────────────────────────────────────────────
# Section 3 — G230 threshold
# ────────────────────────────────────────────────────────────────────

def test_v10343_g230_requires_eight_schemas_minimum():
    """G230 violation if schemas drop below 8 (v10.343 baseline)."""
    text = (REPO / "scripts" / "audit.py").read_text()
    # Look for the v10.343-strengthened threshold
    assert "len(schemas) < 8" in text or "expected ≥8" in text
