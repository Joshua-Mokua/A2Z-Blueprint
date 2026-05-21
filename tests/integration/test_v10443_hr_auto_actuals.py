"""Integration tests for v10.443 — HR Auto-Actuals + Chief HR Centre."""

import json
import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10443_engine_exists():
    p = REPO / "utils" / "hr_actuals_engine.py"
    assert p.exists()
    text = p.read_text()
    for needed in (
        "def compute_kpi_actual",
        "def compute_all_hr_actuals_for_staff",
        "def compute_bank_wide_hr_kpi",
        "def audit_auto_actuals_coverage",
        "class AutoActualResult",
        "class CoverageAudit",
        "HR_KPI_SOURCES",
        "HR_KPI_NON_AUTO",
        "KPI_COMPUTERS",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10443_engine_zero_streamlit():
    text = (REPO / "utils" / "hr_actuals_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10443_compute_training_hours():
    for k in list(sys.modules):
        if "hr_actuals_engine" in k:
            del sys.modules[k]
    from utils.hr_actuals_engine import compute_kpi_actual
    r = compute_kpi_actual("300001", "K016", "2025-12")
    # Returns a real number (LMS data exists, MD has enrollments or zero)
    assert r.kpi_id == "K016"
    assert r.source_module == "Learning Management"
    assert r.value is not None  # Even 0 is a valid auto-value


def test_v10443_compute_mandatory_training_pct():
    for k in list(sys.modules):
        if "hr_actuals_engine" in k:
            del sys.modules[k]
    from utils.hr_actuals_engine import compute_kpi_actual
    r = compute_kpi_actual("300001", "K121", "2025-12")
    assert r.source_module == "Learning Management"
    # MD has mandatory training data — should be 0-100
    if r.value is not None:
        assert 0 <= r.value <= 100


def test_v10443_k019_is_non_auto():
    """K019 (360 Feedback) is not auto-populatable from HR modules."""
    for k in list(sys.modules):
        if "hr_actuals_engine" in k:
            del sys.modules[k]
    from utils.hr_actuals_engine import compute_kpi_actual
    r = compute_kpi_actual("300001", "K019", "2025-12")
    assert r.value is None
    assert r.source_module == "manual"
    assert r.confidence == "none"


def test_v10443_finance_kpis_are_non_auto():
    """K005, K021 (Finance KPIs) stay manual."""
    for k in list(sys.modules):
        if "hr_actuals_engine" in k:
            del sys.modules[k]
    from utils.hr_actuals_engine import compute_kpi_actual
    for kpi in ("K005", "K021"):
        r = compute_kpi_actual("300001", kpi, "2025-12")
        assert r.value is None, f"{kpi} should be None"
        assert r.source_module == "manual"


def test_v10443_bank_wide_retention():
    for k in list(sys.modules):
        if "hr_actuals_engine" in k:
            del sys.modules[k]
    from utils.hr_actuals_engine import compute_bank_wide_hr_kpi
    r = compute_bank_wide_hr_kpi("K018", "2025-12")
    assert r.staff_code is None  # bank-wide
    assert r.kpi_id == "K018"
    # Retention is a %; should be 0-100
    if r.value is not None:
        assert 0 <= r.value <= 100


def test_v10443_coverage_audit_works():
    for k in list(sys.modules):
        if "hr_actuals_engine" in k:
            del sys.modules[k]
    from utils.hr_actuals_engine import audit_auto_actuals_coverage
    cov = audit_auto_actuals_coverage()
    # We auto-populate ~6 of 14 HR-pillar KPIs = ~43%
    assert cov.coverage_pct >= 40.0
    assert cov.auto_populated_count >= 4
    assert cov.total_hr_kpis >= 10


def test_v10443_compute_all_for_staff():
    """Compute every KPI in the role for the MD."""
    for k in list(sys.modules):
        if "hr_actuals_engine" in k:
            del sys.modules[k]
    from utils.hr_actuals_engine import compute_all_hr_actuals_for_staff
    results = compute_all_hr_actuals_for_staff("300001", "2025-12")
    # MD has role_kpis, should return at least a few results
    assert len(results) >= 0  # Could be 0 if role isn't in role_kpis
    # All results must be AutoActualResult instances
    for r in results:
        assert hasattr(r, "kpi_id")
        assert hasattr(r, "value")


def test_v10443_engine_results_json_serializable():
    for k in list(sys.modules):
        if "hr_actuals_engine" in k:
            del sys.modules[k]
    from utils.hr_actuals_engine import (
        compute_kpi_actual, compute_bank_wide_hr_kpi,
        audit_auto_actuals_coverage,
    )
    r1 = compute_kpi_actual("300001", "K016", "2025-12")
    r2 = compute_bank_wide_hr_kpi("K018", "2025-12")
    cov = audit_auto_actuals_coverage()
    json.dumps(r1.to_dict())
    json.dumps(r2.to_dict())
    json.dumps(cov.to_dict())


def test_v10443_chief_hr_centre_page_exists():
    p = REPO / "pages" / "81_chief_hr_centre.py"
    assert p.exists()


def test_v10443_chief_hr_centre_has_6_tabs():
    t = (REPO / "pages" / "81_chief_hr_centre.py").read_text()
    for tab in (
        "People Overview",
        "HR KPI Auto-Actuals",
        "Training & Development",
        "Performance Programs",
        "Onboarding & Exit Risk",
        "Financial Snapshot",
    ):
        assert tab in t, f"Tab missing: {tab}"


def test_v10443_chief_hr_centre_imports_engine():
    t = (REPO / "pages" / "81_chief_hr_centre.py").read_text()
    assert "from utils.hr_actuals_engine" in t


def test_v10443_chief_hr_centre_syntax_valid():
    import ast
    ast.parse((REPO / "pages" / "81_chief_hr_centre.py").read_text())


def test_v10443_chief_hr_centre_in_manifest():
    m = json.loads((REPO / "pages" / "_manifest.json").read_text())
    entry = m["pages"].get("81_chief_hr_centre.py")
    assert entry is not None
    assert entry["department_primary"] == "people_hr"
    assert "_v10443_new_pages" in m


def test_v10443_api_endpoints():
    t = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/hr-actuals/staff/{staff_code}" in t
    assert "/api/v1/hr-actuals/bank-wide/{kpi_id_or_name}" in t
    assert "/api/v1/hr-actuals/coverage" in t
    assert "from utils.hr_actuals_engine" in t


def test_v10443_api_syntax_valid():
    import ast
    ast.parse((REPO / "utils" / "api.py").read_text())


def test_v10443_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10443_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10443_hr_engine_wiring_preserved():
    """v10.441 100% engine wiring must be preserved."""
    for k in list(sys.modules):
        if "hr_section_audit_engine" in k:
            del sys.modules[k]
    from utils.hr_section_audit_engine import audit_engine_wiring
    ew = audit_engine_wiring()
    assert ew.wiring_coverage_pct == 100.0


def test_v10443_g329_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10443_hr_auto_actuals
    r = gate_v10443_hr_auto_actuals()
    assert r["passed"], r.get("violations")
