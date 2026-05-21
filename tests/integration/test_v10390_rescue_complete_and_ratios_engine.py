"""Integration tests for v10.390 — bundle (orphan removal + financial ratios engine).

Joshua-approved bundle:
- Concern A: org_config.json::pillar_weights orphan REMOVED (rescue 5/5 complete)
- Concern B: utils/financial_ratios_engine.py foundation + 4 KPI library entries

13 tests across 4 sections.
"""

import json
import sys
from decimal import Decimal
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Concern A: orphan removal
# ────────────────────────────────────────────────────────────────────

def test_v10390_org_config_orphan_removed():
    org = json.loads((REPO / "data" / "org_config.json").read_text())
    assert "pillar_weights" not in org, (
        "org_config.pillar_weights still present"
    )


def test_v10390_backup_preserved():
    backup = REPO / "data" / "_v10390_backups" / "org_config.json.before"
    assert backup.exists()
    # Backup should still have the orphan (it was removed AFTER backup)
    pre = json.loads(backup.read_text())
    assert "pillar_weights" in pre


def test_v10390_health_check_orphan_none():
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import health_check
    hc = health_check()
    assert hc["orphan_detected"] is None, (
        f"orphan_detected should be None, got {hc['orphan_detected']!r}"
    )
    # Shadow also still removed (from v10.389)
    assert hc["shadow_pillars_field"] is False


def test_v10390_rescue_fully_complete():
    """Both v10.389 shadow AND v10.390 orphan are removed."""
    _reimport("utils.pillar_weights_canonical")
    from utils.pillar_weights_canonical import health_check
    hc = health_check()
    assert hc["shadow_pillars_field"] is False
    assert hc["orphan_detected"] is None
    # Canonical weights still functional
    assert hc["canonical_valid"] is True
    assert hc["canonical_sum"] == 1.0


# ────────────────────────────────────────────────────────────────────
# Section 2 — Concern B: financial ratios engine module
# ────────────────────────────────────────────────────────────────────

def test_v10390_engine_module_exists():
    p = REPO / "utils" / "financial_ratios_engine.py"
    assert p.exists()


def test_v10390_engine_is_leaf_module():
    """AST check: no top-level upward utils.* imports."""
    import ast
    p = REPO / "utils" / "financial_ratios_engine.py"
    tree = ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if (node.module and node.module.startswith("utils") and
                    node.col_offset == 0):
                raise AssertionError(
                    f"engine not leaf — imports {node.module}"
                )


def test_v10390_engine_exports_required_functions():
    p = REPO / "utils" / "financial_ratios_engine.py"
    text = p.read_text()
    for sym in ("def compute_nim", "def compute_cir",
                "def compute_roe", "def compute_total_deposit_growth",
                "def compute_all_financial_ratios",
                "class NIMResult", "class CIRResult",
                "class ROEResult", "class DepGrowthResult"):
        assert sym in text, f"missing {sym}"


def test_v10390_engine_self_tests_pass():
    """Run the engine's self_test() directly."""
    _reimport("utils.financial_ratios_engine")
    from utils.financial_ratios_engine import self_test
    # If this raises, the test fails
    self_test()


def test_v10390_compute_all_returns_4_results():
    _reimport("utils.financial_ratios_engine")
    from utils.financial_ratios_engine import compute_all_financial_ratios
    results = compute_all_financial_ratios()
    assert set(results.keys()) == {"NIM", "CIR", "ROE", "DEP_GROWTH"}
    for kpi_id, r in results.items():
        assert r is not None, f"{kpi_id} returned None"


def test_v10390_cir_matches_published_key_ratio():
    """Independent validation: engine CIR == bank's published key_ratio (±0.5)."""
    _reimport("utils.financial_ratios_engine")
    from utils.financial_ratios_engine import compute_cir
    mgmt = json.loads((REPO / "data" / "mgmt_accounts.json").read_text())
    published_cir = float(mgmt["key_ratios"]["cir_pct"])
    computed_cir = float(compute_cir().cir_pct)
    assert abs(published_cir - computed_cir) < 0.5, (
        f"CIR mismatch: computed {computed_cir:.2f}% vs published "
        f"{published_cir:.2f}%"
    )


def test_v10390_roe_caveat_captured_in_note():
    """ROEResult.note must explain the PBT-vs-net-income caveat."""
    _reimport("utils.financial_ratios_engine")
    from utils.financial_ratios_engine import compute_roe
    r = compute_roe()
    assert r is not None
    assert "PBT" in r.note, f"ROE caveat missing from note: {r.note}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — KPI library entries (inactive)
# ────────────────────────────────────────────────────────────────────

def test_v10390_4_new_kpis_in_library_all_inactive():
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    kpis = lib.get("kpis", [])
    expected = {"NIM", "CIR", "ROE", "DEP_GROWTH"}
    found = {}
    for k in kpis:
        if isinstance(k, dict) and k.get("id") in expected:
            found[k["id"]] = k
    assert set(found.keys()) == expected, (
        f"missing KPI entries: {expected - set(found.keys())}"
    )
    for kpi_id, k in found.items():
        assert k.get("active") is False, (
            f"{kpi_id} should be inactive, got active={k.get('active')!r}"
        )
        assert k.get("_added") == "v10.390", (
            f"{kpi_id} missing v10.390 _added marker"
        )
        assert k.get("pillar") == "Financial", (
            f"{kpi_id} should be in Financial pillar"
        )


# ────────────────────────────────────────────────────────────────────
# Section 4 — G275 + no regression
# ────────────────────────────────────────────────────────────────────

def test_v10390_g275_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_v10390_rescue_complete_and_ratios_engine
    r = gate_v10390_rescue_complete_and_ratios_engine()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G275"
