"""Integration tests for v10.431 — admin validation engine + UI wiring."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10431_engine_exists():
    path = REPO / "utils" / "admin_validation_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def validate_kpi_change",
        "def validate_pillar_weights",
        "def validate_role_kpis_change",
        "def validate_target_override",
        "def validate_full_library",
        "def apply_legacy_code_aliases",
        "class ValidationIssue",
        "class ValidationResult",
        "class LegacyAliasResult",
        "LEGACY_CODE_ALIAS_MAP",
        "CANONICAL_PILLARS",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10431_zero_streamlit():
    text = (REPO / "utils" / "admin_validation_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10431_safety_dry_run_default():
    text = (REPO / "utils" / "admin_validation_engine.py").read_text()
    assert "dry_run: bool = True" in text


def test_v10431_legacy_alias_map_22_entries():
    for k in list(sys.modules):
        if "admin_validation_engine" in k:
            del sys.modules[k]
    from utils.admin_validation_engine import LEGACY_CODE_ALIAS_MAP
    assert len(LEGACY_CODE_ALIAS_MAP) == 22
    # Spot checks
    assert LEGACY_CODE_ALIAS_MAP["FEES_COMM"] == "Fee Income (KES M)"
    assert LEGACY_CODE_ALIAS_MAP["NPS"] == "WB NPS Score"
    assert LEGACY_CODE_ALIAS_MAP["TOTAL_NFI"] == "Total NFI"
    assert LEGACY_CODE_ALIAS_MAP["LOAN_DISB"] == "Loans Disbursed (KES M)"


def test_v10431_validate_kpi_change_canonical_pillar():
    from utils.admin_validation_engine import validate_kpi_change
    # Good case
    r = validate_kpi_change(
        {"id": "TEST", "name": "Test", "pillar": "Financial"},
        existing_lib={"kpis": []},
    )
    assert r.valid
    # Bad pillar
    r = validate_kpi_change(
        {"id": "BAD", "name": "Bad", "pillar": "Risk"},  # non-canonical
        existing_lib={"kpis": []},
    )
    assert not r.valid
    assert any("non-canonical" in e.message for e in r.errors)


def test_v10431_validate_pillar_weights_sum():
    from utils.admin_validation_engine import validate_pillar_weights
    # Good (Kaplan-Norton)
    r = validate_pillar_weights({
        "Financial": 0.40, "Customer Focus": 0.25,
        "Operational Excellence": 0.25, "People & Learning": 0.10,
    })
    assert r.valid
    # Bad sum
    r = validate_pillar_weights({
        "Financial": 0.50, "Customer Focus": 0.30,
        "Operational Excellence": 0.30, "People & Learning": 0.10,
    })
    assert not r.valid


def test_v10431_validate_role_kpis_orphan_detection():
    from utils.admin_validation_engine import validate_role_kpis_change
    lib = {"kpis": [{"id": "K001", "name": "Loans", "pillar": "Financial"}]}
    # Good
    r = validate_role_kpis_change("MD", ["K001"], existing_lib=lib)
    assert r.valid
    # Orphan
    r = validate_role_kpis_change("MD", ["K001", "GHOST"], existing_lib=lib)
    assert not r.valid


def test_v10431_validate_target_override_large_swing_warning():
    from utils.admin_validation_engine import validate_target_override
    r = validate_target_override("Alice", "Loans", 200.0, current_target=90.0)
    assert r.valid  # warning, not error
    assert any("changes by" in w.message for w in r.warnings)


def test_v10431_library_register_extended_with_risk():
    """v10.426 LIBRARY_PILLAR_FIX_MAP now includes Risk -> Financial."""
    for k in list(sys.modules):
        if "bsc_library_register_engine" in k:
            del sys.modules[k]
    from utils.bsc_library_register_engine import LIBRARY_PILLAR_FIX_MAP
    assert LIBRARY_PILLAR_FIX_MAP.get("Risk") == "Financial"


def test_v10431_full_library_validates_clean():
    """After v10.431 fixes, validate_full_library returns valid=True."""
    for k in list(sys.modules):
        if "admin_validation_engine" in k:
            del sys.modules[k]
    from utils.admin_validation_engine import validate_full_library
    r = validate_full_library()
    assert r.valid, [e.to_dict() for e in r.errors]
    assert len(r.errors) == 0


def test_v10431_legacy_aliases_applied_to_library():
    """The 22 legacy SNAKE_CASE codes should now appear as aliases."""
    import json
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    all_aliases = set()
    for k in lib.get("kpis", []):
        if isinstance(k, dict):
            for a in k.get("aliases", []) or []:
                all_aliases.add(str(a))
    for k in list(sys.modules):
        if "admin_validation_engine" in k:
            del sys.modules[k]
    from utils.admin_validation_engine import LEGACY_CODE_ALIAS_MAP
    for code in LEGACY_CODE_ALIAS_MAP:
        assert code in all_aliases, f"Library missing legacy alias: {code}"


def test_v10431_admin_panel_has_library_validation():
    text = (REPO / "utils" / "bsc_admin_panel.py").read_text()
    assert "def render_library_validation_panel" in text


def test_v10431_admin_page_wires_validation_panel():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "render_library_validation_panel" in text


def test_v10431_admin_page_syntax_valid():
    import ast
    text = (REPO / "pages" / "7_admin.py").read_text()
    ast.parse(text)


def test_v10431_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/admin-validation/library" in text
    assert "/api/v1/admin-validation/legacy-aliases" in text


def test_v10431_bsc_health_still_100():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10431_idempotent_legacy_aliases():
    """Running apply_legacy_code_aliases on a clean state yields 0 changes."""
    from utils.admin_validation_engine import apply_legacy_code_aliases
    r = apply_legacy_code_aliases(dry_run=True)
    assert r.aliases_added == 0


def test_v10431_dataclasses_json_serializable():
    import json
    from utils.admin_validation_engine import (
        validate_kpi_change, validate_full_library, apply_legacy_code_aliases,
    )
    json.dumps(validate_kpi_change(
        {"id": "X", "name": "X", "pillar": "Financial"},
        existing_lib={"kpis": []},
    ).to_dict())
    json.dumps(validate_full_library().to_dict())
    json.dumps(apply_legacy_code_aliases(dry_run=True).to_dict())


def test_v10431_g317_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10431_admin_validation
    r = gate_v10431_admin_validation()
    assert r["passed"], r.get("violations")
