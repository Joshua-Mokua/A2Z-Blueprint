"""Integration tests for v10.444 — Body Health Engine (operating mantra).

Uses session-scoped fixture so the body audit runs ONCE for the whole
test module (audit is ~95s; without fixture would be 30+ minutes).
"""

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def body_report():
    from utils.body_health_engine import body_full_audit
    return body_full_audit()


@pytest.fixture(scope="module")
def organ_snap():
    from utils.body_health_engine import audit_organ_health
    return audit_organ_health()


@pytest.fixture(scope="module")
def circulation():
    from utils.body_health_engine import audit_circulation_flows
    return audit_circulation_flows()


@pytest.fixture(scope="module")
def deterioration():
    from utils.body_health_engine import audit_deterioration_risks
    return audit_deterioration_risks()


def test_v10444_engine_exists():
    p = REPO / "utils" / "body_health_engine.py"
    assert p.exists()
    text = p.read_text()
    for needed in (
        "ORGAN_REGISTRY",
        "CIRCULATION_FLOWS",
        "DETERIORATION_CATALOGUE",
        "def audit_organ_health",
        "def audit_circulation_flows",
        "def audit_deterioration_risks",
        "def body_full_audit",
        "def record_health_snapshot",
        "def audit_health_trend",
        "class OrganHealth",
        "class CirculationAudit",
        "class DeteriorationAudit",
        "class BodyHealthReport",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10444_zero_streamlit():
    text = (REPO / "utils" / "body_health_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10444_organ_registry_has_seven():
    from utils.body_health_engine import ORGAN_REGISTRY
    assert len(ORGAN_REGISTRY) >= 7
    for required in ("bsc", "cascade_bsc_360", "target_cascade",
                     "hr_section", "standards_wiring",
                     "hr_auto_actuals", "engine_baseline"):
        assert required in ORGAN_REGISTRY


def test_v10444_circulation_flows_categorized():
    from utils.body_health_engine import CIRCULATION_FLOWS
    linear = [f for f in CIRCULATION_FLOWS if f["kind"] == "linear"]
    non_linear = [f for f in CIRCULATION_FLOWS if f["kind"] == "non_linear"]
    assert len(linear) >= 3
    assert len(non_linear) >= 6


def test_v10444_deterioration_catalogue_complete():
    from utils.body_health_engine import DETERIORATION_CATALOGUE
    assert len(DETERIORATION_CATALOGUE) >= 9


def test_v10444_organ_health_runs(organ_snap):
    assert organ_snap.overall_health_pct > 80.0
    assert len(organ_snap.organs) >= 7


def test_v10444_bsc_organ_healthy(organ_snap):
    bsc = next((o for o in organ_snap.organs if o.organ_id == "bsc"), None)
    assert bsc is not None
    assert bsc.health_pct == 100.0


def test_v10444_cascade_360_organ_healthy(organ_snap):
    o = next((o for o in organ_snap.organs if o.organ_id == "cascade_bsc_360"), None)
    assert o is not None
    assert o.health_pct == 100.0


def test_v10444_engine_baseline_intact(organ_snap):
    bl = next((o for o in organ_snap.organs if o.organ_id == "engine_baseline"), None)
    assert bl is not None
    assert bl.health_pct == 100.0


def test_v10444_hr_organ_at_floor(organ_snap):
    hr = next((o for o in organ_snap.organs if o.organ_id == "hr_section"), None)
    assert hr is not None
    assert hr.health_pct >= 85.0


def test_v10444_circulation_audit_runs(circulation):
    assert circulation.overall_flow_pct >= 80.0
    assert circulation.linear_flowing >= 3


def test_v10444_all_linear_flows_active(circulation):
    linear = [f for f in circulation.flows if f.kind == "linear"]
    flowing = [f for f in linear if f.flowing]
    assert len(flowing) == len(linear)


def test_v10444_no_critical_deterioration(deterioration):
    critical_active = [r for r in deterioration.risks
                      if r.detected and r.severity == "critical"]
    assert len(critical_active) == 0


def test_v10444_body_audit_runs(body_report):
    from utils.body_health_engine import BodyHealthReport
    assert isinstance(body_report, BodyHealthReport)
    assert body_report.overall_body_pct >= 85.0


def test_v10444_body_health_above_90(body_report):
    assert body_report.overall_body_pct >= 90.0


def test_v10444_mantra_status(body_report):
    assert body_report.mantra_status in ("100%", "below_100")


def test_v10444_serializable(body_report):
    json.dumps(body_report.to_dict())


def test_v10444_history_trend_accessible():
    from utils.body_health_engine import audit_health_trend
    trend = audit_health_trend(n=5)
    assert isinstance(trend, list)


def test_v10444_record_snapshot():
    from utils.body_health_engine import record_health_snapshot
    entry = record_health_snapshot()
    assert "body_pct" in entry
    assert "timestamp" in entry


def test_v10444_g330_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10444_body_health_mantra
    r = gate_v10444_body_health_mantra()
    assert r["passed"], r.get("violations")
