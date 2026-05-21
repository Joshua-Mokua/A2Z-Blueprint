"""Integration tests for v10.427 — BSC completeness."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10427_engine_exists():
    path = REPO / "utils" / "bsc_completeness_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_bsc_completeness",
        "def repair_bsc_completeness",
        "def repair_code_alias_artifacts",
        "class MissingKPI",
        "class StaffCompletenessGap",
        "class CompletenessAudit",
        "class CompletenessRepairResult",
        "CODE_ALIAS_MAP",
        "DEFAULT_ACHIEVEMENT",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10427_zero_streamlit():
    text = (REPO / "utils" / "bsc_completeness_engine.py").read_text()
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10427_safety_dry_run_default():
    text = (REPO / "utils" / "bsc_completeness_engine.py").read_text()
    assert "dry_run: bool = True" in text


def test_v10427_code_alias_map():
    for k in list(sys.modules):
        if "bsc_completeness" in k:
            del sys.modules[k]
    from utils.bsc_completeness_engine import CODE_ALIAS_MAP
    assert CODE_ALIAS_MAP["LOAN_GROWTH"] == "Loan Book Growth"
    assert CODE_ALIAS_MAP["AUDIT_SCORE"] == "Audit Score"
    assert "LEGAL_SLA_DOCS" in CODE_ALIAS_MAP
    assert "LEGAL_SLA_ATTORNEY" in CODE_ALIAS_MAP
    assert "LEGAL_SLA_VALUATION" in CODE_ALIAS_MAP
    assert "LEGAL_SLA_SECURITY" in CODE_ALIAS_MAP


def test_v10427_audit_returns_proper_shape():
    from utils.bsc_completeness_engine import (
        audit_bsc_completeness, CompletenessAudit,
    )
    a = audit_bsc_completeness()
    assert isinstance(a, CompletenessAudit)
    # After v10.427 migration, no incomplete BSCs should remain
    assert a.incomplete_count == 0
    assert a.rows_would_be_added == 0


def test_v10427_kpi_completeness_now_clean():
    """Post-migration: bsc_audit kpi_completeness reports 0 incomplete."""
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import audit_kpi_completeness
    kc = audit_kpi_completeness()
    assert kc.incomplete_count == 0


def test_v10427_no_duplicate_rows():
    """Post-migration: dedup left zero duplicate (staff, KPI) pairs."""
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import audit_duplicate_rows
    dr = audit_duplicate_rows()
    assert dr.duplicate_count == 0


def test_v10427_library_alignment_still_100():
    """v10.427 cleanup should preserve v10.426's 100% library alignment."""
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import audit_library_alignment
    la = audit_library_alignment()
    assert la.alignment_pct == 100.0


def test_v10427_no_snake_case_artifacts_in_actuals():
    """No BSC rows should have SNAKE_CASE codes as KPI names."""
    import pandas as pd
    df = pd.read_excel(REPO / "data" / "actuals_2025_Dec_25.xlsx", skiprows=1)
    bsc_kpis = set(df["KPI"].dropna().astype(str).str.strip().unique())
    from utils.bsc_completeness_engine import CODE_ALIAS_MAP
    for code in CODE_ALIAS_MAP:
        assert code not in bsc_kpis, (
            f"BSC actuals still contains SNAKE_CASE code: {code}"
        )


def test_v10427_chiefs_now_complete():
    """The 9 chiefs should each have ≥8 KPIs."""
    import pandas as pd
    df = pd.read_excel(REPO / "data" / "actuals_2025_Dec_25.xlsx", skiprows=1)
    chiefs = df[df["Role"].str.contains("Chief|Company Secretary", case=False, na=False)]
    per_chief = chiefs.groupby(["Staff Name", "Role"])["KPI"].nunique()
    for (name, role), count in per_chief.items():
        assert count >= 8, f"Chief {name} ({role}) has only {count} KPIs"


def test_v10427_library_has_code_aliases():
    """Post-migration: library has the 6 SNAKE_CASE codes as aliases."""
    import json
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    all_aliases = set()
    for k in lib.get("kpis", []):
        if isinstance(k, dict):
            for a in k.get("aliases", []) or []:
                all_aliases.add(str(a))
    from utils.bsc_completeness_engine import CODE_ALIAS_MAP
    for code in CODE_ALIAS_MAP:
        assert code in all_aliases, f"Library missing code alias: {code}"


def test_v10427_chief_weights_normalized():
    """The 9 chiefs should have weight sums = 1.0 after v10.427."""
    import pandas as pd
    df = pd.read_excel(REPO / "data" / "actuals_2025_Dec_25.xlsx", skiprows=1)
    chiefs = df[df["Role"].str.contains("Chief|Company Secretary", case=False, na=False)]
    per_chief = chiefs.groupby("Staff Name")["Weight"].sum()
    for name, total in per_chief.items():
        assert abs(total - 1.0) < 0.01, (
            f"Chief {name} weight sum is {total:.4f}, expected 1.0"
        )


def test_v10427_runner_script_exists():
    path = REPO / "scripts" / "repair_bsc_completeness.py"
    assert path.exists()
    assert "--confirm" in path.read_text()


def test_v10427_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/bsc-completeness/audit" in text
    assert "/api/v1/bsc-completeness/repair" in text


def test_v10427_dataclasses_json_serializable():
    from utils.bsc_completeness_engine import (
        audit_bsc_completeness, repair_bsc_completeness,
    )
    import json
    a = audit_bsc_completeness()
    r = repair_bsc_completeness(dry_run=True)
    json.dumps(a.to_dict())
    json.dumps(r.to_dict())


def test_v10427_idempotent_repair():
    """Running repair on clean state yields 0 changes."""
    from utils.bsc_completeness_engine import repair_bsc_completeness
    result = repair_bsc_completeness(dry_run=True)
    assert result.rows_added == 0


def test_v10427_idempotent_cleanup():
    """Running cleanup on clean state yields 0 changes."""
    from utils.bsc_completeness_engine import repair_code_alias_artifacts
    result = repair_code_alias_artifacts(dry_run=True)
    assert result.rows_added == 0


def test_v10427_g313_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10427_bsc_completeness
    r = gate_v10427_bsc_completeness()
    assert r["passed"], r.get("violations")
