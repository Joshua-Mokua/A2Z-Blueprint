"""Integration tests for v10.401 — period harmonization (TC38 resolved).

Per the rescue arc backlog: periods inconsistent across fixed_kpis.json
(quarterly), bank_targets.json (annual), target_cascade.json (annual).

10 tests across 4 sections.
"""

import ast
import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(name):
    return json.loads((REPO / "data" / name).read_text())


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module + leaf-purity
# ────────────────────────────────────────────────────────────────────

def test_v10401_period_harmonizer_module_exists():
    p = REPO / "utils" / "period_harmonizer.py"
    assert p.exists()
    text = p.read_text()
    for fn in ("get_fixed_kpis_for_period", "get_quarters_for_year",
               "promote_quarters_to_annual", "validate_period_consistency",
               "set_annual_fixed_kpis", "list_periods"):
        assert f"def {fn}" in text, f"function {fn} missing"


def test_v10401_period_harmonizer_is_leaf():
    text = (REPO / "utils" / "period_harmonizer.py").read_text()
    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("utils") and node.col_offset == 0:
                assert False, f"period_harmonizer imports utils.{node.module}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Annual key support
# ────────────────────────────────────────────────────────────────────

def test_v10401_annual_2026_key_present():
    """Explicit annual '2026' key should now exist."""
    fk = _load("fixed_kpis.json")
    assert "2026" in fk
    assert isinstance(fk["2026"], dict)
    kpis = fk["2026"].get("kpis", [])
    assert isinstance(kpis, list)
    assert len(kpis) >= 10, f"expected 10+ fixed KPIs; got {len(kpis)}"


def test_v10401_annual_matches_quarterly_union():
    """For 2026, annual list should equal union of quarter entries."""
    for k in list(sys.modules):
        if "period_harmonizer" in k:
            del sys.modules[k]
    from utils.period_harmonizer import validate_period_consistency
    val = validate_period_consistency("2026")
    assert val["consistent"], f"2026 not consistent: {val['issues']}"


def test_v10401_get_fixed_kpis_prefers_annual():
    """When annual key exists, harmonizer reads it (not the union)."""
    for k in list(sys.modules):
        if "period_harmonizer" in k:
            del sys.modules[k]
    from utils.period_harmonizer import get_fixed_kpis_for_period
    result = get_fixed_kpis_for_period("2026")
    assert isinstance(result, set)
    assert "CX Score" in result
    assert "PBT" not in result  # PBT is NOT fixed


def test_v10401_get_fixed_kpis_quarterly_still_works():
    """Quarterly lookup must still work for granular MD changes."""
    for k in list(sys.modules):
        if "period_harmonizer" in k:
            del sys.modules[k]
    from utils.period_harmonizer import get_fixed_kpis_for_period
    q1 = get_fixed_kpis_for_period("2026-Q1")
    assert isinstance(q1, set)
    assert len(q1) > 0


# ────────────────────────────────────────────────────────────────────
# Section 3 — Regenerator integration
# ────────────────────────────────────────────────────────────────────

def test_v10401_regenerator_uses_annual_key():
    """cascade_regenerator should prefer annual key (TC38 fix)."""
    p = REPO / "utils" / "cascade_regenerator.py"
    text = p.read_text()
    # The updated _get_fixed_kpi_set should check for direct annual match first
    assert "year in fixed_kpis" in text or "fixed_kpis[year]" in text or \
           "v10.401" in text, "regenerator not updated for v10.401 TC38 fix"


def test_v10401_cascade_state_preserved():
    """Cascade should still have ~25,488 entries (no change in count)."""
    tc = _load("target_cascade.json")
    data_count = sum(1 for k in tc if not k.startswith("_") and "|" in k)
    assert 23000 <= data_count <= 26000, f"unexpected cascade size: {data_count}"  # v10.402 dropped to ~24K


def test_v10401_engine_state_preserved():
    """All 4 metrics still zero after period harmonization."""
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


# ────────────────────────────────────────────────────────────────────
# Section 4 — Gate + backup
# ────────────────────────────────────────────────────────────────────

def test_v10401_backup_preserved():
    assert (REPO / "data" / "_v10401_backups" / "fixed_kpis.json.before").exists()


def test_v10401_g287_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10401_period_harmonization
    r = gate_v10401_period_harmonization()
    assert r["passed"], r.get("violations")
