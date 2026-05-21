"""Integration tests for v10.434 — staff onboarding fit-in test."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10434_engine_exists():
    path = REPO / "utils" / "staff_onboarding_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def validate_new_staff",
        "def simulate_onboarding",
        "def audit_staff_completeness",
        "def audit_all_staff_completeness",
        "class ValidationResult",
        "class OnboardingResult",
        "class CompletenessAudit",
        "class FullCompletenessAudit",
        "CANONICAL_PILLARS",
        "WEIGHT_TOLERANCE",
        "_resolve_canonical_names",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10434_zero_streamlit():
    text = (REPO / "utils" / "staff_onboarding_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10434_validate_new_staff_required_fields():
    for k in list(sys.modules):
        if "staff_onboarding_engine" in k:
            del sys.modules[k]
    from utils.staff_onboarding_engine import validate_new_staff
    # Missing fields
    r = validate_new_staff({"Staff Code": "X"})
    assert not r.valid
    assert any("required" in e.message for e in r.errors)


def test_v10434_validate_new_staff_duplicate_code():
    from utils.staff_onboarding_engine import validate_new_staff
    # 300001 is MD — already exists
    r = validate_new_staff({
        "Staff Code": "300001",
        "Staff Name": "Test", "Role": "Teller", "Unit": "Test",
    })
    assert not r.valid
    assert any("already exists" in e.message for e in r.errors)


def test_v10434_validate_new_staff_good_case():
    from utils.staff_onboarding_engine import validate_new_staff
    r = validate_new_staff({
        "Staff Code": "TST99001",
        "Staff Name": "Test New",
        "Role": "Branch Operations Manager",
        "Unit": "Test Branch",
    })
    assert r.valid


def test_v10434_simulate_onboarding_existing_role():
    from utils.staff_onboarding_engine import simulate_onboarding
    r = simulate_onboarding({
        "Staff Code": "TST_SIM_001",
        "Staff Name": "Test Sim",
        "Role": "Teller",
        "Unit": "Test Branch",
    })
    assert r.valid
    assert r.bsc_rows_added > 0
    assert r.weight_sum_post > 0
    assert r.score_computable


def test_v10434_simulate_onboarding_unconfigured_role():
    """A role with no role_kpis returns 0 BSC rows + warning."""
    from utils.staff_onboarding_engine import simulate_onboarding
    r = simulate_onboarding({
        "Staff Code": "TST_HYP_001",
        "Staff Name": "Hypothetical Role Test",
        "Role": "Some Brand New Role Not In Lib",
        "Unit": "Test",
    })
    # Should validate but warn
    assert r.valid
    assert r.bsc_rows_added == 0
    assert not r.score_computable


def test_v10434_audit_staff_completeness_md():
    from utils.staff_onboarding_engine import audit_staff_completeness
    md = audit_staff_completeness("300001")
    assert md.register_present
    assert md.bsc_row_count > 0
    # Weight should be 1.0 after v10.433 renormalize
    assert md.weight_sum_valid
    assert md.score_computable


def test_v10434_audit_all_staff_completeness():
    from utils.staff_onboarding_engine import audit_all_staff_completeness
    a = audit_all_staff_completeness()
    assert a.total_staff > 1000
    # Post-v10.433: 100% weight + score invariants
    assert a.weight_sum_invariant_pct == 100.0
    assert a.score_computable_pct == 100.0
    # Pillar coverage near-full
    assert a.pillar_coverage_pct >= 95.0
    # Avg role_kpi coverage healthy
    assert a.avg_role_kpi_coverage_pct >= 75.0


def test_v10434_canonical_name_resolver():
    import json
    from utils.staff_onboarding_engine import _resolve_canonical_names
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    # PRODUCT_BOOK_ACHIEVEMENT should resolve to "Product Book Achievement"
    canonical = _resolve_canonical_names(lib, ["PRODUCT_BOOK_ACHIEVEMENT"])
    assert canonical == ["Product Book Achievement"]
    # Direct name passes through
    canonical = _resolve_canonical_names(lib, ["PBT"])
    assert "PBT" in canonical


def test_v10434_admin_panel_has_onboarding():
    text = (REPO / "utils" / "bsc_admin_panel.py").read_text()
    assert "def render_onboarding_fit_panel" in text


def test_v10434_admin_page_wires_onboarding():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "render_onboarding_fit_panel" in text


def test_v10434_admin_page_syntax_valid():
    import ast
    text = (REPO / "pages" / "7_admin.py").read_text()
    ast.parse(text)


def test_v10434_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/onboarding/audit" in text
    assert "/api/v1/onboarding/simulate" in text
    assert "Body" in text  # POST needs Body


def test_v10434_dataclasses_json_serializable():
    import json
    from utils.staff_onboarding_engine import (
        validate_new_staff, simulate_onboarding,
        audit_staff_completeness, audit_all_staff_completeness,
    )
    json.dumps(validate_new_staff({
        "Staff Code": "TST_JSON",
        "Staff Name": "T", "Role": "Teller", "Unit": "T",
    }).to_dict())
    json.dumps(simulate_onboarding({
        "Staff Code": "TST_JSON_SIM",
        "Staff Name": "T", "Role": "Teller", "Unit": "T",
    }).to_dict())
    json.dumps(audit_staff_completeness("300001").to_dict())
    json.dumps(audit_all_staff_completeness().to_dict())


def test_v10434_360_harmony_preserved():
    """v10.434 is audit-only; 360 harmony must stay 100%."""
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10434_bsc_rescue_health_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10434_g320_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10434_staff_onboarding
    r = gate_v10434_staff_onboarding()
    assert r["passed"], r.get("violations")
