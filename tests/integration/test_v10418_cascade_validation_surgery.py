"""Integration tests for v10.418 — cascade-validation surgery.

14 tests across 4 sections.
"""

import sys
import tempfile
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Engine
# ────────────────────────────────────────────────────────────────────

def test_v10418_engine_has_compliance():
    text = (REPO / "utils" / "cascade_retain_engine.py").read_text()
    for needed in (
        "def compute_allocation_compliance",
        "class AllocationCompliance",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10418_engine_still_zero_streamlit():
    text = (REPO / "utils" / "cascade_retain_engine.py").read_text()
    import re
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


# ────────────────────────────────────────────────────────────────────
# Section 2 — compliance behavior
# ────────────────────────────────────────────────────────────────────

def _isolated_engine():
    for k in list(sys.modules):
        if "cascade_retain" in k:
            del sys.modules[k]
    import importlib
    mod = importlib.import_module("utils.cascade_retain_engine")
    tmp_dir = Path(tempfile.mkdtemp())
    mod.AUTH_FILE = tmp_dir / "test.json"
    return mod


def test_v10418_fully_cascaded():
    mod = _isolated_engine()
    c = mod.compute_allocation_compliance("MGR", "PBT", "2026", 100.0, 100.0)
    assert c.status == "fully_cascaded"
    assert c.compliance_ok is True
    assert c.retained_amount == 0.0


def test_v10418_fully_cascaded_within_tolerance():
    """0.1% rounding tolerance: 100.05 ~= 100."""
    mod = _isolated_engine()
    c = mod.compute_allocation_compliance("MGR", "PBT", "2026", 100.0, 100.05)
    assert c.status == "fully_cascaded"
    assert c.compliance_ok is True


def test_v10418_retained_authorized():
    mod = _isolated_engine()
    mod.set_retain_authorization("AUTHORIZED", "BOSS", "2026", can_retain=True)
    c = mod.compute_allocation_compliance("AUTHORIZED", "PBT", "2026", 100.0, 70.0)
    assert c.status == "retained_authorized"
    assert c.compliance_ok is True
    assert abs(c.retained_amount - 30.0) < 1e-6
    assert abs(c.retained_pct - 0.30) < 1e-6
    assert c.has_retain_auth is True


def test_v10418_under_no_auth():
    mod = _isolated_engine()
    c = mod.compute_allocation_compliance("UNAUTH", "PBT", "2026", 100.0, 70.0)
    assert c.status == "under_no_auth"
    assert c.compliance_ok is False
    assert c.retained_amount == 0.0  # not legitimate retention
    assert c.has_retain_auth is False


def test_v10418_over_allocated_ignores_auth():
    """Over-allocation is always a violation, regardless of auth."""
    mod = _isolated_engine()
    mod.set_retain_authorization("AUTHORIZED", "BOSS", "2026", can_retain=True)
    c = mod.compute_allocation_compliance("AUTHORIZED", "PBT", "2026", 100.0, 110.0)
    assert c.status == "over_allocated"
    assert c.compliance_ok is False


def test_v10418_no_target():
    mod = _isolated_engine()
    c = mod.compute_allocation_compliance("ANY", "ANY_KPI", "2026", 0.0, 50.0)
    assert c.status == "no_target"
    assert c.compliance_ok is False


def test_v10418_revoked_auth_doesnt_help():
    """can_retain=False (explicit revoke) means under-allocation IS a violation."""
    mod = _isolated_engine()
    mod.set_retain_authorization("REVOKED", "BOSS", "2026", can_retain=False)
    c = mod.compute_allocation_compliance("REVOKED", "PBT", "2026", 100.0, 70.0)
    assert c.status == "under_no_auth"  # explicit revoke = same as no auth
    assert c.compliance_ok is False


def test_v10418_compliance_dataclass_json():
    mod = _isolated_engine()
    c = mod.compute_allocation_compliance("X", "Y", "2026", 100.0, 100.0)
    import json
    json.dumps(c.to_dict())


# ────────────────────────────────────────────────────────────────────
# Section 3 — UI wiring
# ────────────────────────────────────────────────────────────────────

def test_v10418_cascade_imports_compliance():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "compute_allocation_compliance" in text


def test_v10418_coverage_display_uses_compliance():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "_row_status" in text
    assert '"Retained' in text  # Retained status label
    assert "Fully cascaded" in text or "fully_cascaded" in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — FastAPI + Gate
# ────────────────────────────────────────────────────────────────────

def test_v10418_compliance_endpoint_registered():
    for k in list(sys.modules):
        if "api_cascade" in k:
            del sys.modules[k]
    from utils.api_cascade import router
    compliance_routes = [r for r in router.routes if "/retain/compliance" in r.path]
    assert len(compliance_routes) == 1
    assert "POST" in compliance_routes[0].methods


def test_v10418_compliance_pydantic_models():
    text = (REPO / "utils" / "api_cascade.py").read_text()
    assert "class ComplianceCheckRequest" in text
    assert "class ComplianceCheckResponse" in text


def test_v10418_g304_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10418_cascade_validation_surgery
    r = gate_v10418_cascade_validation_surgery()
    assert r["passed"], r.get("violations")
