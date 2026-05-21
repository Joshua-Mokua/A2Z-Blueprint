"""Integration tests for v10.425 — BSC pillar canonical merge."""

import re
import sys
import tempfile
import shutil
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10425_engine_exists():
    path = REPO / "utils" / "bsc_pillar_normalize_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_actuals_pillars",
        "def migrate_actuals_pillars",
        "class ActualsPillarAudit",
        "class PillarMigrationResult",
        "ALIAS_MAP",
        "CANONICAL_PILLARS",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10425_zero_streamlit():
    text = (REPO / "utils" / "bsc_pillar_normalize_engine.py").read_text()
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10425_alias_map_correct():
    for k in list(sys.modules):
        if "bsc_pillar" in k:
            del sys.modules[k]
    from utils.bsc_pillar_normalize_engine import ALIAS_MAP, CANONICAL_PILLARS
    assert ALIAS_MAP == {"Operational": "Operational Excellence"}
    assert "Operational Excellence" in CANONICAL_PILLARS
    assert "Operational" not in CANONICAL_PILLARS


def test_v10425_safety_dry_run_default():
    """Critical: migrate must default to dry_run=True."""
    text = (REPO / "utils" / "bsc_pillar_normalize_engine.py").read_text()
    assert "dry_run: bool = True" in text


def _build_synth_actuals(path: Path):
    import pandas as pd
    synth = pd.DataFrame({
        "Staff Name":     ["Alice", "Bob", "Carol"],
        "Staff Code":     ["S1", "S2", "S3"],
        "Role":           ["Mgr", "Off", "Off"],
        "Unit":           ["A", "A", "B"],
        "Category":       ["X", "X", "Y"],
        "Staff Status":   ["Active"] * 3,
        "KPI":            ["K1", "K2", "K3"],
        "Pillar":         ["Financial", "Operational", "Customer Focus"],
        "Weight":         [0.5, 0.5, 0.5],
        "Annual Target":  [100] * 3,
        "YTD_Actual":     [50] * 3,
        "Dec-25":         [10] * 3,
        "Annual Actual":  [60] * 3,
    })
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame([[""] * len(synth.columns)],
                     columns=synth.columns).to_excel(
            w, sheet_name="KPI Data", index=False, header=False)
        synth.to_excel(w, sheet_name="KPI Data",
                      startrow=1, index=False)


def test_v10425_audit_synthetic():
    from utils.bsc_pillar_normalize_engine import audit_actuals_pillars
    tmp = Path(tempfile.mkdtemp())
    try:
        path = tmp / "actuals_test.xlsx"
        _build_synth_actuals(path)
        audit = audit_actuals_pillars(actuals_path=path)
        assert audit.total_rows == 3
        assert audit.non_canonical_counts == {"Operational": 1}
        assert audit.rows_to_migrate == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10425_dry_run_no_fs_change():
    from utils.bsc_pillar_normalize_engine import (
        audit_actuals_pillars, migrate_actuals_pillars,
    )
    tmp = Path(tempfile.mkdtemp())
    try:
        path = tmp / "actuals_test.xlsx"
        _build_synth_actuals(path)
        result = migrate_actuals_pillars(actuals_path=path)  # dry_run default
        assert result.dry_run is True
        # Audit still shows the non-canonical
        audit = audit_actuals_pillars(actuals_path=path)
        assert audit.rows_to_migrate == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10425_migration_flips_rows():
    import utils.bsc_pillar_normalize_engine as eng
    tmp = Path(tempfile.mkdtemp())
    original_data_dir = eng.DATA_DIR
    try:
        path = tmp / "actuals_test.xlsx"
        _build_synth_actuals(path)
        eng.DATA_DIR = tmp  # backups go to tmp/_v10425_backups
        result = eng.migrate_actuals_pillars(actuals_path=path, dry_run=False)
        assert result.dry_run is False
        assert result.rows_migrated == 1
        assert "_v10425_backups" in result.backup_path
        # Re-audit: clean now
        audit = eng.audit_actuals_pillars(actuals_path=path)
        assert audit.rows_to_migrate == 0
        assert "Operational" not in audit.non_canonical_counts
    finally:
        eng.DATA_DIR = original_data_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10425_idempotent():
    import utils.bsc_pillar_normalize_engine as eng
    tmp = Path(tempfile.mkdtemp())
    original_data_dir = eng.DATA_DIR
    try:
        path = tmp / "actuals_test.xlsx"
        _build_synth_actuals(path)
        eng.DATA_DIR = tmp
        eng.migrate_actuals_pillars(actuals_path=path, dry_run=False)
        # Re-run
        r2 = eng.migrate_actuals_pillars(actuals_path=path, dry_run=False)
        assert r2.rows_migrated == 0
    finally:
        eng.DATA_DIR = original_data_dir
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10425_dataclasses_json_serializable():
    from utils.bsc_pillar_normalize_engine import (
        audit_actuals_pillars, migrate_actuals_pillars,
    )
    import json
    a = audit_actuals_pillars()
    r = migrate_actuals_pillars()
    json.dumps(a.to_dict())
    json.dumps(r.to_dict())


def test_v10425_runner_script_exists():
    path = REPO / "scripts" / "normalize_pillars.py"
    assert path.exists()
    text = path.read_text()
    assert "--confirm" in text


def test_v10425_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    for endpoint in (
        "/api/v1/bsc-pillar/audit",
        "/api/v1/bsc-pillar/migrate",
    ):
        assert endpoint in text, f"Missing: {endpoint}"


def test_v10425_simulate_v2_source_clean():
    """simulate_v2.py source fix: no 'pillar':'Operational' (without Excellence)."""
    sim = REPO / "simulate_v2.py"
    assert sim.exists()
    text = sim.read_text()
    nc = re.findall(r'"pillar":\s*"Operational"', text)
    assert len(nc) == 0, f"{len(nc)} non-canonical pillar definitions remain"
    # Verify the canonical ones exist (the fix replaced them)
    oe = re.findall(r'"pillar":\s*"Operational Excellence"', text)
    assert len(oe) >= 19, f"Expected ≥19 Operational Excellence, got {len(oe)}"


def test_v10425_real_actuals_clean():
    """After v10.425 migration, the real actuals file has no non-canonical pillars."""
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import audit_pillar_canonical
    a = audit_pillar_canonical()
    assert not a.non_canonical_pillars, (
        f"Real actuals still have non-canonical: {a.non_canonical_pillars}"
    )


def test_v10425_g311_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10425_pillar_canonical_merge
    r = gate_v10425_pillar_canonical_merge()
    assert r["passed"], r.get("violations")
