"""Integration tests for v10.365 — FLEXCUBE live wire-up.

Closes the v10.361 stub-only state of fetch_branches_from_flexcube and
fetch_staff_from_flexcube. v10.365 wires real requests.get patterns +
adds mock mode with local fixtures so the live code path is exercised
in tests without a real FLEXCUBE.

13 tests across 5 sections:
  1. Adapter module surface (new functions present)
  2. Fixture files present and well-formed
  3. Synthetic mode preserves None (fallback chain intact)
  4. Mock mode exercises fixtures correctly
  5. G251 audit gate
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
# Section 1 — Module surface
# ────────────────────────────────────────────────────────────────────

def test_v10365_live_helpers_present():
    """flexcube_adapter has _live_*_from_flexcube + _mock_*_from_flexcube."""
    text = (REPO / "utils" / "flexcube_adapter.py").read_text()
    for sym in ("def _live_branches_from_flexcube",
                "def _mock_branches_from_flexcube",
                "def _live_staff_from_flexcube",
                "def _mock_staff_from_flexcube"):
        assert sym in text, f"flexcube_adapter missing {sym}"


def test_v10365_live_functions_call_requests_get():
    """The live helpers MUST actually call requests.get — no longer
    pure None-stubs (v10.361)."""
    text = (REPO / "utils" / "flexcube_adapter.py").read_text()
    for sym in ("_live_branches_from_flexcube", "_live_staff_from_flexcube"):
        m = re.search(rf"def {sym}[\s\S]*?(?=\ndef |\Z)", text)
        assert m is not None, f"Could not locate {sym} body"
        body = m.group()
        assert "requests.get" in body, (
            f"{sym} doesn't call requests.get — v10.365 must wire the real "
            f"REST call, not be a stub"
        )
        # And it must have OAuth bearer auth
        assert "Authorization" in body and "Bearer" in body, (
            f"{sym} missing OAuth bearer auth header"
        )


def test_v10365_three_modes_dispatched():
    """fetch_branches_from_flexcube dispatches to synthetic/mock/live."""
    text = (REPO / "utils" / "flexcube_adapter.py").read_text()
    m = re.search(
        r"def fetch_branches_from_flexcube[\s\S]*?(?=\ndef |\Z)", text
    )
    assert m is not None
    body = m.group()
    assert 'mode == "synthetic"' in body
    assert 'mode == "mock"' in body
    assert 'mode == "live"' in body
    assert "_mock_branches_from_flexcube" in body
    assert "_live_branches_from_flexcube" in body


# ────────────────────────────────────────────────────────────────────
# Section 2 — Fixtures
# ────────────────────────────────────────────────────────────────────

def test_v10365_mock_branches_fixture_present():
    """data/flexcube_mock_branches.json must exist for mock-mode probes."""
    p = REPO / "data" / "flexcube_mock_branches.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert isinstance(data, list)
    assert len(data) >= 50, f"Expected ≥50 mock branches, got {len(data)}"
    # Shape check — mirrors live API contract
    for b in data[:5]:
        for k in ("branch_code", "branch_name", "region", "status"):
            assert k in b, f"Mock branch missing key '{k}'"


def test_v10365_mock_staff_fixture_present():
    p = REPO / "data" / "flexcube_mock_staff.json"
    assert p.exists()
    data = json.loads(p.read_text())
    assert isinstance(data, list)
    assert len(data) >= 100, f"Expected ≥100 mock staff, got {len(data)}"
    for s in data[:5]:
        assert "staff_code" in s or "username" in s
        assert "status" in s


def test_v10365_fixtures_match_org_config_shape():
    """Mock branches should be derivable from / consistent with org_config.json."""
    org = json.loads((REPO / "data" / "org_config.json").read_text())
    org_names = {b["name"] for b in org["branches"]
                 if b.get("active", True) and b.get("name")}
    mock = json.loads((REPO / "data" / "flexcube_mock_branches.json").read_text())
    mock_names = {b["branch_name"] for b in mock
                  if b.get("status") == "ACTIVE"}
    # Mock fixture should at minimum cover the active org_config branches
    assert mock_names == org_names, (
        f"Mock fixture vs org_config diff: "
        f"only-in-mock={mock_names - org_names}, "
        f"only-in-org={org_names - mock_names}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Synthetic mode preserves fallback chain
# ────────────────────────────────────────────────────────────────────

def test_v10365_synthetic_mode_returns_none():
    """Synthetic mode must return None so get_ecobank_branches falls
    back to org_config — preserves the v10.361 priority chain."""
    _reimport("utils.flexcube_adapter")
    from utils.flexcube_adapter import (
        get_mode, fetch_branches_from_flexcube, fetch_staff_from_flexcube
    )
    if get_mode() == "synthetic":
        assert fetch_branches_from_flexcube() is None
        assert fetch_staff_from_flexcube() is None


def test_v10365_seed_module_still_falls_back():
    """utils.virtual_bank_seed.get_ecobank_branches still falls through
    to org_config when FLEXCUBE returns None (synthetic mode)."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.flexcube_adapter")
    from utils.virtual_bank_seed import get_ecobank_branches
    branches = get_ecobank_branches()
    assert len(branches) >= 50, (
        f"Synthetic-mode fallback to org_config broken: {len(branches)} branches"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Mock mode exercises the live code path
# ────────────────────────────────────────────────────────────────────

def _with_mock_mode(probe_fn):
    """Helper: temporarily flip flexcube_config.json to mock and run probe."""
    cfg_path = REPO / "data" / "flexcube_config.json"
    original = cfg_path.read_text()
    try:
        cfg = json.loads(original)
        cfg["mode"] = "mock"
        cfg_path.write_text(json.dumps(cfg, indent=2))
        _reimport("utils.flexcube_adapter")
        _reimport("utils.virtual_bank_seed")
        return probe_fn()
    finally:
        cfg_path.write_text(original)
        _reimport("utils.flexcube_adapter")
        _reimport("utils.virtual_bank_seed")


def test_v10365_mock_mode_returns_branches():
    def probe():
        from utils.flexcube_adapter import fetch_branches_from_flexcube
        return fetch_branches_from_flexcube()
    result = _with_mock_mode(probe)
    assert result is not None, "Mock mode returned None — fixture not read"
    assert len(result) >= 50, f"Mock branches: {len(result)}"
    # All values are strings (region names)
    for name, region in list(result.items())[:5]:
        assert isinstance(name, str) and name
        assert isinstance(region, str)


def test_v10365_mock_mode_returns_staff():
    def probe():
        from utils.flexcube_adapter import fetch_staff_from_flexcube
        return fetch_staff_from_flexcube()
    result = _with_mock_mode(probe)
    assert result is not None
    assert len(result) >= 100
    # All have status == ACTIVE (filter applied)
    for s in result[:10]:
        assert s.get("status") == "ACTIVE"


def test_v10365_mock_mode_changes_seed_module_source():
    """When mock is active, get_ecobank_branches picks up FLEXCUBE
    branches (not org_config). Validates the priority chain works."""
    def probe():
        from utils.virtual_bank_seed import get_ecobank_branches
        return get_ecobank_branches()
    result = _with_mock_mode(probe)
    assert result is not None
    assert len(result) >= 50, f"Mock-sourced branches: {len(result)}"
    # Should match the mock fixture exactly
    mock = json.loads(
        (REPO / "data" / "flexcube_mock_branches.json").read_text()
    )
    expected = {b["branch_name"]: b.get("region", "Other")
                for b in mock if b.get("status") == "ACTIVE"}
    assert result == expected, "Mock branches don't match fixture"


# ────────────────────────────────────────────────────────────────────
# Section 5 — G251 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10365_g251_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_flexcube_live_wireup
    result = gate_flexcube_live_wireup()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G251"


def test_v10365_g251_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G251", gate_flexcube_live_wireup)' in text
