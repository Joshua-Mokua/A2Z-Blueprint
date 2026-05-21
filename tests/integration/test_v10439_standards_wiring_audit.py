"""Integration tests for v10.439 — standards-wide engine wiring diagnostic."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10439_engine_exists():
    p = REPO / "utils" / "standards_wiring_audit_engine.py"
    assert p.exists()
    text = p.read_text()
    for needed in (
        "def audit_engine_inventory",
        "def audit_standards_wiring",
        "def audit_unwired_standalone",
        "def audit_orphan_standards",
        "def standards_full_audit",
        "class EngineInventoryAudit",
        "class StandardsWiringAudit",
        "class UnwiredStandaloneAudit",
        "class OrphanStandardsAudit",
        "class StandardsFullAudit",
        "AGGREGATOR_ENGINES",
        "EXPECTED_INFRASTRUCTURE",
        "DOMAIN_PREFIXES",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10439_zero_streamlit():
    text = (REPO / "utils" / "standards_wiring_audit_engine.py").read_text()
    streamlit_imports = re.findall(
        r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10439_engine_inventory_runs():
    for k in list(sys.modules):
        if "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_audit_engine import audit_engine_inventory
    inv = audit_engine_inventory()
    assert inv.total_engines > 400
    # The 5 classifications should sum to total
    total = (inv.wired_direct + inv.wired_via_aggregator
             + inv.wired_infrastructure + inv.expected_infrastructure
             + inv.unwired_standalone)
    assert total == inv.total_engines


def test_v10439_aggregator_engines_set():
    from utils.standards_wiring_audit_engine import AGGREGATOR_ENGINES
    # Critical aggregators present
    assert "finance_hub_render" in AGGREGATOR_ENGINES
    assert "platform_hub_render" in AGGREGATOR_ENGINES
    assert "scenario_simulator" in AGGREGATOR_ENGINES


def test_v10439_expected_infrastructure_set():
    from utils.standards_wiring_audit_engine import EXPECTED_INFRASTRUCTURE
    # bsc_engine is the critical one Joshua asked about
    assert "bsc_engine" in EXPECTED_INFRASTRUCTURE
    assert "flexcube_adapter" in EXPECTED_INFRASTRUCTURE


def test_v10439_bsc_engine_correctly_classified_infrastructure():
    """The BSC engine asked about - should be classified as
    expected_infrastructure, not as unwired needing rescue."""
    for k in list(sys.modules):
        if "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_audit_engine import audit_engine_inventory
    inv = audit_engine_inventory()
    bsc = [c for c in inv.classifications if c.name == "bsc_engine"]
    assert len(bsc) == 1
    assert bsc[0].classification == "expected_infrastructure"


def test_v10439_standards_wiring_detects_330_standards():
    for k in list(sys.modules):
        if "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_audit_engine import audit_standards_wiring
    sw = audit_standards_wiring()
    assert sw.total_standards >= 300


def test_v10439_standards_wiring_coverage_above_70_pct():
    for k in list(sys.modules):
        if "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_audit_engine import audit_standards_wiring
    sw = audit_standards_wiring()
    assert sw.wiring_coverage_pct >= 70.0


def test_v10439_unwired_standalone_surfaces_rescue_targets():
    for k in list(sys.modules):
        if "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_audit_engine import audit_unwired_standalone
    uw = audit_unwired_standalone()
    # Should detect ~23 registry-backed unwired engines
    assert 15 <= uw.total_unwired <= 50
    # Top rescue priorities present
    assert len(uw.rescue_priority_estimates) > 0
    top = [p["engine"] for p in uw.rescue_priority_estimates]
    # reconciliation should be in top (18 standards reference it)
    assert "reconciliation" in top


def test_v10439_orphan_standards_audit():
    for k in list(sys.modules):
        if "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_audit_engine import audit_orphan_standards
    orph = audit_orphan_standards()
    assert orph.orphan_count >= 0  # may be 0 or some


def test_v10439_master_audit_runs():
    for k in list(sys.modules):
        if "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_audit_engine import (
        standards_full_audit, StandardsFullAudit,
    )
    f = standards_full_audit()
    assert isinstance(f, StandardsFullAudit)
    assert f.wiring_health_pct >= 0


def test_v10439_dataclasses_json_serializable():
    import json
    for k in list(sys.modules):
        if "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_audit_engine import (
        audit_engine_inventory, audit_standards_wiring,
        audit_unwired_standalone, audit_orphan_standards,
        standards_full_audit,
    )
    for fn in (audit_engine_inventory, audit_standards_wiring,
               audit_unwired_standalone, audit_orphan_standards,
               standards_full_audit):
        r = fn()
        json.dumps(r.to_dict())


def test_v10439_domain_classification_helper():
    for k in list(sys.modules):
        if "standards_wiring_audit_engine" in k:
            del sys.modules[k]
    from utils.standards_wiring_audit_engine import _domain_of
    assert _domain_of("market_risk_factors") == "Market Risk & Treasury"
    assert _domain_of("mlops_model_registry") == "MLOps & Model Governance"
    assert _domain_of("audit_universe") == "Audit & Compliance"
    assert _domain_of("nonexistent_xyz") == "Other"


def test_v10439_360_harmony_preserved():
    for k in list(sys.modules):
        if "cascade_bsc_360_engine" in k:
            del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    m = cascade_bsc_360_audit()
    assert m.overall_harmony_pct == 100.0


def test_v10439_bsc_rescue_preserved():
    for k in list(sys.modules):
        if "bsc_audit_engine" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    h = bsc_full_audit()
    assert h.overall_health_pct == 100.0


def test_v10439_g325_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10439_standards_wiring_audit
    r = gate_v10439_standards_wiring_audit()
    assert r["passed"], r.get("violations")
