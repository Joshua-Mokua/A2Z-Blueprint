"""Integration tests for v10.470 — CERTIFIED Revival × 13 organs.

Per Joshua mantra: 'No organ left disconnected. No process left
fragmented. The mission is to restore and sustain a living enterprise
organism where every revived organ strengthens the intelligence,
resilience, efficiency, adaptability, and longevity of the entire body.'

v10.470 moves all 13 organs from REVIVED to CERTIFIED REVIVED STABLE
by closing the final 14-criteria doctrine cert checklist.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ── 1. ALL 13 ORGANS CERTIFIED ──────────────────────────────────────

def test_v10470_all_13_organs_certified():
    for k in list(sys.modules):
        if 'module_doctrine_audit' in k: del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    a = all_modules_audit()
    not_cert = [(k, m.criteria_fully_met)
               for k, m in a.modules.items() if not m.certified]
    assert not not_cert, f"Not certified: {not_cert}"
    assert sum(1 for m in a.modules.values() if m.certified) == 13


def test_v10470_avg_health_above_90():
    for k in list(sys.modules):
        if 'module_doctrine_audit' in k: del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    a = all_modules_audit()
    assert a.avg_doctrine_health_pct >= 90.0


def test_v10470_zero_crisis_modules():
    for k in list(sys.modules):
        if 'module_doctrine_audit' in k: del sys.modules[k]
    from utils.module_doctrine_audit import all_modules_audit
    a = all_modules_audit()
    assert a.crisis_modules == []


# ── 2. 13 module_revival.md DOCS ────────────────────────────────────

def test_v10470_all_organ_revival_docs_exist():
    for k in list(sys.modules):
        if 'module_doctrine_audit' in k: del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY, _doc_exists
    missing = [k for k in MODULE_REGISTRY
              if not _doc_exists(MODULE_REGISTRY[k], "module_revival")]
    assert not missing, f"Missing revival docs: {missing}"


# ── 3. DOCKERFILE ───────────────────────────────────────────────────

def test_v10470_dockerfile_exists():
    assert (REPO / "Dockerfile").exists()


def test_v10470_dockerfile_is_valid():
    text = (REPO / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python" in text
    assert "EXPOSE" in text
    assert "HEALTHCHECK" in text


# ── 4. API ENGINE COVERAGE ──────────────────────────────────────────

def test_v10470_api_coverage_per_organ():
    for k in list(sys.modules):
        if 'module_doctrine_audit' in k: del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY
    api_text = (REPO / "utils" / "api.py").read_text(encoding="utf-8")
    for organ_key, cfg in MODULE_REGISTRY.items():
        if not cfg.engines:
            continue
        api_engines = sum(1 for e in cfg.engines if e in api_text)
        pct = api_engines / len(cfg.engines) * 100
        assert pct >= 90.0, f"{organ_key} API coverage {pct:.0f}% <90%"


# ── 5. PHASE 3 AT ≥90% PER ORGAN ────────────────────────────────────

def test_v10470_phase_3_recovery_at_90_each():
    for k in list(sys.modules):
        if 'module_doctrine_audit' in k: del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY, _phase_3
    failing = []
    for organ_key, cfg in MODULE_REGISTRY.items():
        p3 = _phase_3(cfg)
        if p3.score_pct < 90:
            failing.append((organ_key, p3.score_pct))
    assert not failing, f"Phase 3 <90%: {failing}"


def test_v10470_phase_2_qa_at_90_each():
    for k in list(sys.modules):
        if 'module_doctrine_audit' in k: del sys.modules[k]
    from utils.module_doctrine_audit import MODULE_REGISTRY, _phase_2
    failing = []
    for organ_key, cfg in MODULE_REGISTRY.items():
        p2 = _phase_2(cfg)
        if p2.score_pct < 90:
            failing.append((organ_key, p2.score_pct))
    assert not failing


# ── 6. NEW MODULE-SPECIFIC GATES ────────────────────────────────────

def test_v10470_organ_specific_gates_pass():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    import audit
    gates = dict(audit.GATES)
    for gid in ("G356", "G356a", "G356b", "G356c",
                "G356d", "G356e", "G356f",
                "G356g", "G356h", "G356i"):
        assert gid in gates, f"{gid} not registered"
        r = gates[gid]()
        assert r["passed"], f"{gid}: {r.get('violations')}"


# ── 7. NO REGRESSION ────────────────────────────────────────────────

def test_v10470_g354_still_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10468_revival_data_population
    r = gate_v10468_revival_data_population()
    assert r["passed"], r.get("violations")


def test_v10470_g355_still_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10469_doctrine_certification
    r = gate_v10469_doctrine_certification()
    assert r["passed"], r.get("violations")


def test_v10470_360_harmony_100():
    for k in list(sys.modules):
        if 'cascade_bsc_360' in k: del sys.modules[k]
    from utils.cascade_bsc_360_engine import cascade_bsc_360_audit
    assert cascade_bsc_360_audit().overall_harmony_pct == 100.0


def test_v10470_bsc_rescue_100():
    for k in list(sys.modules):
        if 'bsc_audit_engine' in k: del sys.modules[k]
    from utils.bsc_audit_engine import bsc_full_audit
    assert bsc_full_audit().overall_health_pct == 100.0


def test_v10470_zero_unwired_standards():
    for k in list(sys.modules):
        if 'standards' in k: del sys.modules[k]
    from utils.standards_wiring_per_module import audit_all_module_standards
    a = audit_all_module_standards()
    assert sum(r.unwired_count for r in a.by_module.values()) == 0


def test_v10470_g356_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"): del sys.modules[k]
    from audit import gate_v10470_certified_13_organs
    r = gate_v10470_certified_13_organs()
    assert r["passed"], r.get("violations")


# ── 8. PER-ORGAN CERTIFICATION ──────────────────────────────────────

@pytest.mark.parametrize("organ_key", [
    "admin", "hr", "bsc_cascade", "credit", "ict", "finance", "treasury",
    "legal", "risk", "compliance", "operations", "crm", "reporting_analytics",
])
def test_v10470_organ_certified(organ_key):
    for k in list(sys.modules):
        if 'module_doctrine_audit' in k: del sys.modules[k]
    from utils.module_doctrine_audit import audit_module
    a = audit_module(organ_key)
    assert a.certified, f"{organ_key} not certified ({a.criteria_fully_met}/14)"
