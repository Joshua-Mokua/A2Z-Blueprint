"""Integration tests for v10.429 — BSC cascade-linkage fix (CLOSING)."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10429_engine_exists():
    path = REPO / "utils" / "bsc_cascade_linkage_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_bsc_code_alignment",
        "def fix_bsc_codes",
        "class CodeMismatch",
        "class CodeAlignmentAudit",
        "class CodeAlignmentResult",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10429_zero_streamlit():
    text = (REPO / "utils" / "bsc_cascade_linkage_engine.py").read_text()
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10429_safety_dry_run_default():
    text = (REPO / "utils" / "bsc_cascade_linkage_engine.py").read_text()
    assert "dry_run: bool = True" in text


def test_v10429_audit_returns_proper_shape():
    for k in list(sys.modules):
        if "bsc_cascade_linkage" in k:
            del sys.modules[k]
    from utils.bsc_cascade_linkage_engine import (
        audit_bsc_code_alignment, CodeAlignmentAudit,
    )
    result = audit_bsc_code_alignment()
    assert isinstance(result, CodeAlignmentAudit)
    # Post-v10.429: no mismatches
    assert len(result.mismatches) == 0


def test_v10429_no_missing_register_codes():
    """Every register code should appear in BSC."""
    from utils.bsc_cascade_linkage_engine import audit_bsc_code_alignment
    result = audit_bsc_code_alignment()
    assert len(result.register_codes_not_in_bsc) == 0


def test_v10429_cascade_linkage_audit_clean():
    """v10.424 audit's cascade_linkage category now clean."""
    for k in list(sys.modules):
        if "bsc_audit" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import audit_cascade_linkage
    cl = audit_cascade_linkage()
    assert len(cl.cascaded_targets_not_in_bsc) == 0


def test_v10429_bsc_health_100():
    """The full BSC audit reports 100% health."""
    for k in list(sys.modules):
        if "bsc_audit" in k or "bsc_cascade" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    audit = bsc_full_audit()
    assert audit.overall_health_pct == 100.0, (
        f"BSC health is {audit.overall_health_pct}%, expected 100%"
    )
    assert audit.issues_by_severity["critical"] == 0
    assert audit.issues_by_severity["warning"] == 0


def test_v10429_all_seven_categories_clean():
    """All 7 audit categories should report 'clean' state."""
    from utils.bsc_audit_engine import bsc_full_audit
    audit = bsc_full_audit()
    # 1. Staff coverage
    assert audit.staff_coverage.coverage_pct == 100.0
    # 2. KPI completeness
    assert audit.kpi_completeness.incomplete_count == 0
    # 3. Pillar canonical
    assert not audit.pillar_canonical.non_canonical_pillars
    # 4. Weight normalization
    assert audit.weight_normalization.not_normalized_count == 0
    # 5. Library alignment
    assert audit.library_alignment.alignment_pct == 100.0
    # 6. Cascade linkage
    assert len(audit.cascade_linkage.cascaded_targets_not_in_bsc) == 0
    # 7. Duplicate rows
    assert audit.duplicate_rows.duplicate_count == 0


def test_v10429_idempotent():
    """Re-running fix on aligned state yields 0 changes."""
    from utils.bsc_cascade_linkage_engine import fix_bsc_codes
    result = fix_bsc_codes(dry_run=False)
    assert result.staff_corrected == 0
    assert result.rows_updated == 0


def test_v10429_runner_script_exists():
    path = REPO / "scripts" / "fix_bsc_codes.py"
    assert path.exists()
    assert "--confirm" in path.read_text()


def test_v10429_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/bsc-codes/audit" in text
    assert "/api/v1/bsc-codes/fix" in text


def test_v10429_dataclasses_json_serializable():
    from utils.bsc_cascade_linkage_engine import (
        audit_bsc_code_alignment, fix_bsc_codes,
    )
    import json
    a = audit_bsc_code_alignment()
    r = fix_bsc_codes(dry_run=True)
    json.dumps(a.to_dict())
    json.dumps(r.to_dict())


def test_v10429_g315_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10429_cascade_linkage
    r = gate_v10429_cascade_linkage()
    assert r["passed"], r.get("violations")
