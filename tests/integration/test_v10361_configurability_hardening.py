"""Integration tests for v10.361 — Configurability hardening.

Joshua's ask: "branches are not to be hardcoded, even the bank. We are
guided that since this is a system we are building that can be adopted
by any bank we moved this to be configurable... You need to confirm that
the admin is able to configure branches including new branches and even
delete, same to staff. important is to also remember we shall be
integrating to either flexcube core banking which hosts this branch
data and therefore we want to make the system seamlessly integrate."

What v10.361 enforces:
1. NO hardcoded fallback branch lists (_BRANCH_REGION_FALLBACK +
   _FALLBACK_BRANCHES deleted)
2. Missing config returns empty dict (configuration error surfaces)
3. FLEXCUBE adapter exposes fetch_branches_from_flexcube +
   fetch_staff_from_flexcube as integration seams
4. Admin module has Branch + Staff CRUD with audit log + protection
5. utils.virtual_bank_seed.get_ecobank_branches priority order:
   FLEXCUBE → org_config → empty (no fallback)

14 tests across 5 sections.
"""

import json
import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Hardcoded fallbacks deleted
# ────────────────────────────────────────────────────────────────────

def test_v10361_core_has_no_branch_fallback_assignment():
    """utils/core.py must NOT assign _BRANCH_REGION_FALLBACK."""
    core_text = (REPO / "utils" / "core.py").read_text()
    assert not re.search(
        r"^_BRANCH_REGION_FALLBACK\s*[:=]\s*(?:dict\s*)?=",
        core_text, re.MULTILINE
    ), "Rule N1: no hardcoded tenant branch data permitted, even as fallback"


def test_v10361_seed_has_no_branch_fallback_assignment():
    """utils/virtual_bank_seed.py must NOT assign _FALLBACK_BRANCHES."""
    seed_text = (REPO / "utils" / "virtual_bank_seed.py").read_text()
    assert not re.search(
        r"^_FALLBACK_BRANCHES\s*[:=]\s*(?:Dict\[[^\]]+\]\s*)?=",
        seed_text, re.MULTILINE
    ), "Rule N1: no hardcoded tenant branch data permitted"


def test_v10361_regions_has_no_hardcoded_fallback():
    """utils/core.py REGIONS builder no longer returns ['South','Central','North']."""
    core_text = (REPO / "utils" / "core.py").read_text()
    # The legacy fallback regex
    assert not re.search(
        r"return\s*\[\s*['\"]South['\"]\s*,\s*['\"]Central['\"]\s*,\s*['\"]North['\"]\s*\]",
        core_text
    ), "v10.361: _build_regions_from_org_config must return empty [] on failure"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Graceful degradation
# ────────────────────────────────────────────────────────────────────

def test_v10361_missing_config_returns_empty(tmp_path, monkeypatch):
    """If org_config.json is missing, get_ecobank_branches returns empty dict."""
    # Move config away temporarily
    orig = REPO / "data" / "org_config.json"
    backup = REPO / "data" / "org_config.json.test_bak"
    orig.rename(backup)
    try:
        _reimport("utils.virtual_bank_seed")
        from utils.virtual_bank_seed import get_ecobank_branches
        result = get_ecobank_branches()
        assert result == {}, (
            f"Missing config should return empty dict, got {len(result)} entries"
        )
    finally:
        backup.rename(orig)
        _reimport("utils.virtual_bank_seed")


def test_v10361_corrupt_config_returns_empty(tmp_path):
    """Malformed org_config.json → empty dict (no hardcoded fallback masks the error)."""
    orig = REPO / "data" / "org_config.json"
    backup = REPO / "data" / "org_config.json.test_bak2"
    orig.rename(backup)
    try:
        orig.write_text("{not valid json")
        _reimport("utils.virtual_bank_seed")
        from utils.virtual_bank_seed import get_ecobank_branches
        result = get_ecobank_branches()
        assert result == {}
    finally:
        orig.unlink(missing_ok=True)
        backup.rename(orig)
        _reimport("utils.virtual_bank_seed")


# ────────────────────────────────────────────────────────────────────
# Section 3 — FLEXCUBE integration seam
# ────────────────────────────────────────────────────────────────────

def test_v10361_flexcube_adapter_exposes_fetch_branches():
    _reimport("utils.flexcube_adapter")
    from utils.flexcube_adapter import fetch_branches_from_flexcube
    assert callable(fetch_branches_from_flexcube)
    # Synthetic mode → returns None (caller falls back to org_config)
    result = fetch_branches_from_flexcube()
    assert result is None, (
        f"Synthetic mode should return None for FLEXCUBE caller fall-through, "
        f"got {result}"
    )


def test_v10361_flexcube_adapter_exposes_fetch_staff():
    _reimport("utils.flexcube_adapter")
    from utils.flexcube_adapter import fetch_staff_from_flexcube
    assert callable(fetch_staff_from_flexcube)
    assert fetch_staff_from_flexcube() is None


def test_v10361_seed_consults_flexcube_first():
    """utils/virtual_bank_seed.py source must reference FLEXCUBE before falling
    back to org_config — the integration seam must be wired."""
    seed_text = (REPO / "utils" / "virtual_bank_seed.py").read_text()
    # FLEXCUBE call must appear before the org_config.json read
    fc_pos = seed_text.find("fetch_branches_from_flexcube")
    org_pos = seed_text.find("org_config.json")
    assert fc_pos > 0, "FLEXCUBE seam missing from seed module"
    assert org_pos > 0, "org_config seam missing"
    assert fc_pos < org_pos, (
        f"FLEXCUBE check must come BEFORE org_config fallback "
        f"(fc at {fc_pos}, org at {org_pos})"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Admin CRUD coverage
# ────────────────────────────────────────────────────────────────────

def test_v10361_admin_branch_crud_present():
    admin_org_text = (REPO / "pages" / "_admin_org.py").read_text()
    assert "def render_branch_manager" in admin_org_text
    assert "Add branch" in admin_org_text
    assert "save_org_config" in admin_org_text
    assert 'audit_log("BRANCH_ADDED"' in admin_org_text
    assert 'audit_log("BRANCH_EDITED"' in admin_org_text


def test_v10361_admin_staff_crud_present():
    admin_text = (REPO / "pages" / "7_admin.py").read_text()
    assert "create_user_form" in admin_text
    assert "edit_user_form" in admin_text
    assert "um.delete_user" in admin_text or "delete_user(" in admin_text
    assert "can_delete_user" in admin_text


def test_v10361_user_manager_crud_methods_present():
    core_text = (REPO / "utils" / "core.py").read_text()
    for method in ("def add_user", "def delete_user",
                   "def can_delete_user", "def save_users"):
        assert method in core_text, f"UserManager.{method} missing"


# ────────────────────────────────────────────────────────────────────
# Section 5 — G246 strengthened + G247
# ────────────────────────────────────────────────────────────────────

def test_v10361_g246_strengthened_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_branch_single_source
    result = gate_branch_single_source()
    assert result["passed"], result.get("violations")


def test_v10361_g247_admin_crud_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_admin_crud_coverage
    result = gate_admin_crud_coverage()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G247"


def test_v10361_g247_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G247", gate_admin_crud_coverage)' in text
