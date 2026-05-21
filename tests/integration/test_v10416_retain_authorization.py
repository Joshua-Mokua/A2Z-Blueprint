"""Integration tests for v10.416 — F3: per-line-manager retain authorization.

16 tests across 5 sections.
"""

import sys
import tempfile
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Engine module
# ────────────────────────────────────────────────────────────────────

def test_v10416_engine_module_exists():
    path = REPO / "utils" / "cascade_retain_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def is_eligible_for_retention",
        "def set_retain_authorization",
        "def get_retain_authorization",
        "def is_retention_allowed",
        "def get_team_retain_authorizations",
        "def remove_retain_authorization",
        "def retention_audit_summary",
        "class RetainAuthorization",
        "class RetentionAuditSummary",
        "TIER1_ROLE_KEYWORDS",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10416_zero_streamlit_imports():
    text = (REPO / "utils" / "cascade_retain_engine.py").read_text()
    import re
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


# ────────────────────────────────────────────────────────────────────
# Section 2 — Eligibility (tier rule)
# ────────────────────────────────────────────────────────────────────

def test_v10416_tier1_roles_not_eligible():
    from utils.cascade_retain_engine import is_eligible_for_retention
    not_eligible = [
        "Managing Director",
        "Chief Executive & Managing Director",
        "Director Retail Banking",
        "Director Commercial Banking",
        "Head Of Retail",
        "Head of MSME",
        "Head Of Corporates & Trade Finance",
        "Regional Head",
        "Branch Manager",
    ]
    for role in not_eligible:
        assert is_eligible_for_retention(role) is False, f"{role} should NOT be eligible"


def test_v10416_below_bm_eligible():
    from utils.cascade_retain_engine import is_eligible_for_retention
    eligible = [
        "Branch Operations Manager",
        "Senior Relationship Manager - SME",
        "Relationship Manager - SME",
        "Senior Relationship Manager - Corporate Banking",
        "Relationship Manager - Corporate Banking",
        "Assistant Relationship Manager-Corporate",
        "Teller",  # leaf, but eligibility says yes
        "CSO",
    ]
    for role in eligible:
        assert is_eligible_for_retention(role) is True, f"{role} should be eligible"


def test_v10416_empty_role_not_eligible():
    from utils.cascade_retain_engine import is_eligible_for_retention
    assert is_eligible_for_retention("") is False
    assert is_eligible_for_retention(None) is False
    assert is_eligible_for_retention(123) is False  # non-string


# ────────────────────────────────────────────────────────────────────
# Section 3 — Engine CRUD
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


def test_v10416_set_and_get_authorization():
    mod = _isolated_engine()
    auth = mod.set_retain_authorization(
        "BOM001", "BM001", "2026",
        can_retain=True, note="Branch lead — local discretion",
    )
    assert auth is not None
    assert auth.staff_code == "BOM001"
    assert auth.authorized_by == "BM001"
    assert auth.can_retain is True
    assert auth.note == "Branch lead — local discretion"

    got = mod.get_retain_authorization("BOM001", "2026")
    assert got is not None
    assert got.can_retain is True


def test_v10416_is_retention_allowed_convenience():
    mod = _isolated_engine()
    mod.set_retain_authorization("BOM001", "BM001", "2026", can_retain=True)
    assert mod.is_retention_allowed("BOM001", "2026") is True
    assert mod.is_retention_allowed("BOM999", "2026") is False  # not configured


def test_v10416_explicit_revoke():
    mod = _isolated_engine()
    mod.set_retain_authorization("BOM002", "BM001", "2026", can_retain=False)
    auth = mod.get_retain_authorization("BOM002", "2026")
    assert auth is not None
    assert auth.can_retain is False
    # is_retention_allowed returns False for explicit revoke
    assert mod.is_retention_allowed("BOM002", "2026") is False


def test_v10416_validation_rejects_empty():
    mod = _isolated_engine()
    assert mod.set_retain_authorization("", "BM", "2026") is None
    assert mod.set_retain_authorization("X", "", "2026") is None
    assert mod.set_retain_authorization("X", "BM", "") is None


def test_v10416_remove_authorization():
    mod = _isolated_engine()
    mod.set_retain_authorization("BOM001", "BM001", "2026", can_retain=True)
    assert mod.remove_retain_authorization("BOM001", "2026", "BM001") is True
    assert mod.get_retain_authorization("BOM001", "2026") is None
    # Removing nonexistent is False (not exception)
    assert mod.remove_retain_authorization("NOPE", "2026", "BM") is False


def test_v10416_team_authorizations():
    mod = _isolated_engine()
    mod.set_retain_authorization("R1", "BOSS", "2026", can_retain=True)
    mod.set_retain_authorization("R2", "BOSS", "2026", can_retain=False)
    # R3 not configured
    team = mod.get_team_retain_authorizations(["R1", "R2", "R3"], "2026")
    assert len(team) == 2
    granted = [a for a in team if a.can_retain]
    assert len(granted) == 1


def test_v10416_audit_summary():
    mod = _isolated_engine()
    mod.set_retain_authorization("R1", "BOSS1", "2026", can_retain=True)
    mod.set_retain_authorization("R2", "BOSS2", "2026", can_retain=True)
    mod.set_retain_authorization("R3", "BOSS1", "2026", can_retain=False)
    s = mod.retention_audit_summary("2026")
    assert s.total_authorizations == 3
    assert s.granted_count == 2
    assert s.revoked_count == 1
    assert sorted(s.authorizing_managers) == ["BOSS1", "BOSS2"]


def test_v10416_dataclasses_json_serializable():
    mod = _isolated_engine()
    auth = mod.set_retain_authorization("R1", "BOSS", "2026")
    s = mod.retention_audit_summary("2026")

    import json
    json.dumps(auth.to_dict())
    json.dumps(s.to_dict())


# ────────────────────────────────────────────────────────────────────
# Section 4 — UI wiring
# ────────────────────────────────────────────────────────────────────

def test_v10416_cascade_imports_retain_engine():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "from utils.cascade_retain_engine import" in text


def test_v10416_f3_ui_present_in_set_team_targets():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "F3 Retain authorizations" in text
    assert "set_retain_authorization(" in text
    assert "🎯 Step 4" in text


def test_v10416_retention_badge_in_my_targets():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "Retention authorized" in text
    assert "Retention explicitly revoked" in text


# ────────────────────────────────────────────────────────────────────
# Section 5 — FastAPI endpoints + Gate
# ────────────────────────────────────────────────────────────────────

def test_v10416_retain_endpoints_registered():
    for k in list(sys.modules):
        if "api_cascade" in k:
            del sys.modules[k]
    from utils.api_cascade import router
    retain_routes = [r for r in router.routes if "/retain" in r.path]
    # v10.416 shipped 4 routes; v10.418 adds /retain/compliance (5th)
    assert len(retain_routes) >= 4, f"Expected >=4 retain routes, got {len(retain_routes)}"

    paths = {r.path for r in retain_routes}
    expected = {
        "/api/v1/cascade/retain/{staff_code}/{period}",
        "/api/v1/cascade/retain/summary/{period}",
    }
    assert expected.issubset(paths)


def test_v10416_g302_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10416_per_line_manager_retain_authorization
    r = gate_v10416_per_line_manager_retain_authorization()
    assert r["passed"], r.get("violations")
