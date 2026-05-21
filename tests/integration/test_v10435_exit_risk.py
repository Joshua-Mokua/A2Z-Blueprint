"""Integration tests for v10.435 — staff exit risk detection."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10435_engine_exists():
    path = REPO / "utils" / "staff_exit_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_exit_risk",
        "def audit_all_exit_risks",
        "def simulate_redistribution",
        "def simulate_exit",
        "class StaffExitRisk",
        "class BankWideExitAudit",
        "class RedistributionPlan",
        "class ExitSimulation",
        "ALLOWED_REDISTRIBUTION_STRATEGIES",
        "RISK_BAND_CRITICAL",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10435_zero_streamlit():
    text = (REPO / "utils" / "staff_exit_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10435_risk_score_caps_sum_100():
    for k in list(sys.modules):
        if "staff_exit_engine" in k:
            del sys.modules[k]
    from utils.staff_exit_engine import (
        SCORE_OUTGOING_CASCADE_MAX, SCORE_OUTGOING_VALUE_MAX,
        SCORE_ROLE_UNIQUENESS_MAX, SCORE_PILLAR_CRITICALITY_MAX,
        SCORE_INCOMING_RELIANCE_MAX,
    )
    total = (
        SCORE_OUTGOING_CASCADE_MAX + SCORE_OUTGOING_VALUE_MAX
        + SCORE_ROLE_UNIQUENESS_MAX + SCORE_PILLAR_CRITICALITY_MAX
        + SCORE_INCOMING_RELIANCE_MAX
    )
    assert total == 100, f"Score caps sum to {total}, expected 100"


def test_v10435_risk_bands():
    from utils.staff_exit_engine import _risk_band
    assert _risk_band(80) == "Critical"
    assert _risk_band(75) == "Critical"
    assert _risk_band(60) == "High"
    assert _risk_band(50) == "High"
    assert _risk_band(30) == "Medium"
    assert _risk_band(25) == "Medium"
    assert _risk_band(10) == "Low"
    assert _risk_band(0) == "Low"


def test_v10435_md_exit_risk_is_high():
    """MD should be high risk (18 cascade entries, 1 of role)."""
    from utils.staff_exit_engine import audit_exit_risk
    md = audit_exit_risk("300001")
    assert md.outgoing_cascade_entries >= 15
    assert md.role_peer_count == 0  # MD is the only one
    # Should be High or Critical (score >= 50)
    assert md.risk_score >= 50
    assert md.risk_band in ("High", "Critical")


def test_v10435_teller_exit_risk_is_low():
    """Tellers should be low risk (many peers, no outgoing cascade)."""
    import pandas as pd
    df = pd.read_excel(REPO / "data/actuals_2025_Dec_25.xlsx", skiprows=1)
    df["_c"] = df["Staff Code"].astype(str).str.strip()
    teller_codes = df[df["Role"] == "Teller"]["_c"].unique()
    if len(teller_codes) == 0:
        return  # skip
    from utils.staff_exit_engine import audit_exit_risk
    t = audit_exit_risk(teller_codes[0])
    assert t.role_peer_count >= 100  # many peers
    assert t.risk_score < 30  # should be Low or Medium


def test_v10435_redistribution_peer_split():
    from utils.staff_exit_engine import simulate_redistribution
    # Branch Manager has peers
    plan = simulate_redistribution("300277", "peer_split")
    # Should be valid OR fall back gracefully
    assert plan.strategy == "peer_split"


def test_v10435_redistribution_hold_open_always_valid():
    """hold_open is always valid - just creates unassigned value."""
    from utils.staff_exit_engine import simulate_redistribution
    plan = simulate_redistribution("300001", "hold_open")
    assert plan.valid
    assert plan.unassigned_value > 0  # MD has significant target value


def test_v10435_redistribution_invalid_strategy():
    from utils.staff_exit_engine import simulate_redistribution
    plan = simulate_redistribution("300001", "bogus_strategy")
    assert not plan.valid
    assert any("not allowed" in w for w in plan.warnings)


def test_v10435_full_exit_simulation():
    from utils.staff_exit_engine import simulate_exit
    sim = simulate_exit("300001")
    assert sim.staff_code == "300001"
    assert sim.risk.staff_name  # has name
    assert len(sim.redistribution_options) == 3
    assert sim.recommended_strategy in {
        "peer_split", "manager_absorb", "hold_open",
    }


def test_v10435_bank_wide_audit():
    from utils.staff_exit_engine import audit_all_exit_risks
    a = audit_all_exit_risks()
    assert a.total_staff > 1000
    # Counts sum to total
    total_counted = (
        a.critical_risk_count + a.high_risk_count
        + a.medium_risk_count + a.low_risk_count
    )
    assert total_counted == a.total_staff
    # Should have some risk diversity
    assert a.high_risk_count > 0
    assert a.low_risk_count > 0


def test_v10435_admin_panel_has_exit_risk():
    text = (REPO / "utils" / "bsc_admin_panel.py").read_text()
    assert "def render_exit_risk_panel" in text


def test_v10435_admin_page_wires_exit_risk():
    text = (REPO / "pages" / "7_admin.py").read_text()
    assert "render_exit_risk_panel" in text


def test_v10435_admin_page_syntax_valid():
    import ast
    text = (REPO / "pages" / "7_admin.py").read_text()
    ast.parse(text)


def test_v10435_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/exit-risk/audit" in text
    assert "/api/v1/exit-risk/simulate" in text


def test_v10435_dataclasses_json_serializable():
    import json
    from utils.staff_exit_engine import (
        audit_exit_risk, audit_all_exit_risks,
        simulate_redistribution, simulate_exit,
    )
    json.dumps(audit_exit_risk("300001").to_dict())
    json.dumps(audit_all_exit_risks().to_dict())
    json.dumps(simulate_redistribution("300001", "hold_open").to_dict())
    json.dumps(simulate_exit("300001").to_dict())


def test_v10435_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10435_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10435_g321_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10435_exit_risk
    r = gate_v10435_exit_risk()
    assert r["passed"], r.get("violations")
