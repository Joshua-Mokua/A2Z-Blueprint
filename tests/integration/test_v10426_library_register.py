"""Integration tests for v10.426 — BSC library register."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10426_engine_exists():
    path = REPO / "utils" / "bsc_library_register_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_unregistered_bsc_kpis",
        "def apply_full_registration",
        "class UnregisteredKPI",
        "class RegistrationAudit",
        "class RegistrationResult",
        "KNOWN_ALIAS_MAP",
        "LIBRARY_PILLAR_FIX_MAP",
        "MULTI_PILLAR_RESOLUTION",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10426_zero_streamlit():
    text = (REPO / "utils" / "bsc_library_register_engine.py").read_text()
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10426_safety_dry_run_default():
    text = (REPO / "utils" / "bsc_library_register_engine.py").read_text()
    assert "dry_run: bool = True" in text


def test_v10426_constants_correct():
    for k in list(sys.modules):
        if "bsc_library_register" in k:
            del sys.modules[k]
    from utils.bsc_library_register_engine import (
        KNOWN_ALIAS_MAP, LIBRARY_PILLAR_FIX_MAP, MULTI_PILLAR_RESOLUTION,
    )
    # Aliases
    assert KNOWN_ALIAS_MAP["Bancassurance Premium"] == "K023"
    assert KNOWN_ALIAS_MAP["Credit TAT — Standard Lane"] == "CREDIT_TAT_STANDARD"
    # Pillar fix
    assert LIBRARY_PILLAR_FIX_MAP["Process"] == "Operational Excellence"
    # Multi-pillar
    assert MULTI_PILLAR_RESOLUTION["Net Interest Margin"] == "Financial"
    assert MULTI_PILLAR_RESOLUTION["FD Approval Rate"] == "Operational Excellence"


def test_v10426_name_to_id_conversion():
    from utils.bsc_library_register_engine import _name_to_id
    assert _name_to_id("New Customers Acquired") == "NEW_CUSTOMERS_ACQUIRED"
    assert _name_to_id("FD Approval Rate") == "FD_APPROVAL_RATE"
    assert _name_to_id("Credit TAT — Standard Lane") == "CREDIT_TAT_STANDARD_LANE"


def test_v10426_audit_returns_proper_shape():
    from utils.bsc_library_register_engine import (
        audit_unregistered_bsc_kpis, RegistrationAudit, UnregisteredKPI,
    )
    a = audit_unregistered_bsc_kpis()
    assert isinstance(a, RegistrationAudit)
    # Post-v10.426 migration: should be 0 to register, 0 aliases to add
    # (re-running on already-clean state)
    if a.to_register:
        # If somehow still not clean, verify shape
        for u in a.to_register[:1]:
            assert isinstance(u, UnregisteredKPI)
            assert u.pillar in {"Financial", "Customer Focus",
                               "Operational Excellence", "People & Learning"}


def test_v10426_dry_run_no_fs_change():
    from utils.bsc_library_register_engine import apply_full_registration
    import json
    # Snapshot library state
    lib_path = REPO / "data" / "kpi_library.json"
    before = json.loads(lib_path.read_text())
    n_before = len(before.get("kpis", []))

    result = apply_full_registration(dry_run=True)
    assert result.dry_run is True
    assert result.backup_path_library == ""

    after = json.loads(lib_path.read_text())
    assert len(after.get("kpis", [])) == n_before  # No additions


def test_v10426_library_alignment_now_100():
    """Post-migration: BSC audit library_alignment should be 100%."""
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import audit_library_alignment
    la = audit_library_alignment()
    assert la.alignment_pct == 100.0, (
        f"Library alignment is {la.alignment_pct}%, expected 100%"
    )


def test_v10426_audit_considers_aliases():
    """The v10.424 audit engine should now look at the aliases field."""
    text = (REPO / "utils" / "bsc_audit_engine.py").read_text()
    assert "lib_aliases" in text, "audit_library_alignment must consider aliases"


def test_v10426_no_process_pillar_in_library():
    """After migration: no library KPI has pillar='Process'."""
    import json
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    process_kpis = [
        k for k in lib.get("kpis", [])
        if isinstance(k, dict) and k.get("pillar") == "Process"
    ]
    assert len(process_kpis) == 0, (
        f"{len(process_kpis)} library KPIs still have pillar='Process'"
    )


def test_v10426_no_multipillar_in_actuals():
    """After migration: no BSC KPI tagged with multiple pillars."""
    import pandas as pd
    df = pd.read_excel(REPO / "data" / "actuals_2025_Dec_25.xlsx", skiprows=1)
    pillar_per_kpi = df.groupby("KPI")["Pillar"].nunique()
    multi = pillar_per_kpi[pillar_per_kpi > 1]
    assert len(multi) == 0, f"Multi-pillar KPIs remain: {dict(multi)}"


def test_v10426_v10426_migration_stamp_present():
    """Library should have the migration metadata."""
    import json
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    assert "_v10426_bsc_library_register" in lib
    stamp = lib["_v10426_bsc_library_register"]
    assert stamp["shipped"] == "v10.426"
    assert stamp["new_kpis_registered"] > 0


def test_v10426_new_kpis_have_canonical_pillars():
    """All v10.426-registered KPIs use canonical pillars."""
    import json
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    canonical = {"Financial", "Customer Focus",
                 "Operational Excellence", "People & Learning"}
    v10426_kpis = [
        k for k in lib.get("kpis", [])
        if isinstance(k, dict) and k.get("_origin") == "v10.426_bsc_library_register"
    ]
    assert len(v10426_kpis) > 0, "No v10.426-registered KPIs found"
    for k in v10426_kpis:
        assert k.get("pillar") in canonical, (
            f"{k.get('name')}: non-canonical pillar {k.get('pillar')}"
        )


def test_v10426_no_duplicate_ids_in_library():
    """Library has no duplicate IDs after migration."""
    import json
    from collections import Counter
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    ids = [
        k.get("id") for k in lib.get("kpis", [])
        if isinstance(k, dict) and k.get("id")
    ]
    counts = Counter(ids)
    dupes = {k: c for k, c in counts.items() if c > 1}
    assert not dupes, f"Duplicate IDs found: {dupes}"


def test_v10426_no_duplicate_names_in_library():
    """Library has no duplicate names after migration."""
    import json
    from collections import Counter
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    names = [
        k.get("name") for k in lib.get("kpis", [])
        if isinstance(k, dict) and k.get("name")
    ]
    counts = Counter(names)
    dupes = {k: c for k, c in counts.items() if c > 1}
    assert not dupes, f"Duplicate names found: {dupes}"


def test_v10426_runner_script_exists():
    path = REPO / "scripts" / "register_bsc_library.py"
    assert path.exists()
    assert "--confirm" in path.read_text()


def test_v10426_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/bsc-library/audit" in text
    assert "/api/v1/bsc-library/register" in text


def test_v10426_dataclasses_json_serializable():
    from utils.bsc_library_register_engine import (
        audit_unregistered_bsc_kpis, apply_full_registration,
    )
    import json
    a = audit_unregistered_bsc_kpis()
    r = apply_full_registration(dry_run=True)
    json.dumps(a.to_dict())
    json.dumps(r.to_dict())


def test_v10426_g312_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10426_library_alignment
    r = gate_v10426_library_alignment()
    assert r["passed"], r.get("violations")
