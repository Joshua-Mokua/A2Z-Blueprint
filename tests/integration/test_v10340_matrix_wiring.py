"""Integration tests for v10.340 — Cost matrix wired into SBU rollup.

13 tests across 5 sections:
  Section 1 — Matrix-mode rollup mechanics (3 tests)
  Section 2 — Reconciliation in both modes (3 tests)
  Section 3 — Matrix total integrity (2 tests)
  Section 4 — Recursion safety (2 tests)
  Section 5 — Audit gate G229 (3 tests)
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(modname):
    for k in list(sys.modules):
        if k.startswith(modname):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Matrix-mode rollup mechanics
# ────────────────────────────────────────────────────────────────────

def test_v10340_default_cost_source_is_matrix():
    """rollup_by_segment without args uses matrix mode."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import rollup_by_segment, clear_matrix_cache
    clear_matrix_cache()
    default = rollup_by_segment("2026-Q2")
    explicit_matrix = rollup_by_segment("2026-Q2", cost_source="matrix")
    # Same indirect totals
    for seg in ("AFFLUENT", "CORE_MIDDLE", "MASS", "CORPORATE"):
        assert (
            default.get(seg, {}).get("indirect_cost", 0)
            == explicit_matrix.get(seg, {}).get("indirect_cost", 0)
        )


def test_v10340_matrix_mode_indirect_differs_from_proxy():
    """Matrix mode produces meaningfully different indirect costs than proxy."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import rollup_by_segment, clear_matrix_cache
    clear_matrix_cache()
    matrix = rollup_by_segment("2026-Q2", cost_source="matrix")
    proxy  = rollup_by_segment("2026-Q2", cost_source="proxy")
    # On the canonical retail tiers, the two should differ noticeably
    for seg in ("AFFLUENT", "CORE_MIDDLE", "MASS"):
        m_ind = matrix.get(seg, {}).get("indirect_cost", 0)
        p_ind = proxy.get(seg, {}).get("indirect_cost", 0)
        assert m_ind != p_ind, f"{seg} indirect identical in both modes"


def test_v10340_invalid_cost_source_rejected():
    """rollup_by_segment rejects unknown cost_source values."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import rollup_by_segment
    try:
        rollup_by_segment("2026-Q2", cost_source="magic")
    except ValueError as exc:
        assert "matrix" in str(exc) or "proxy" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown cost_source")


# ────────────────────────────────────────────────────────────────────
# Section 2 — Reconciliation
# ────────────────────────────────────────────────────────────────────

def test_v10340_matrix_mode_reconciles():
    """Segment totals = bank total in matrix mode."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import reconcile_to_bank, clear_matrix_cache
    clear_matrix_cache()
    rec = reconcile_to_bank("2026-Q2", cost_source="matrix")
    assert rec["reconciles"], (
        f"matrix mode delta={rec['delta_kes']}, "
        f"tolerance={rec['tolerance_kes']}"
    )
    assert rec["cost_source"] == "matrix"


def test_v10340_proxy_mode_still_reconciles():
    """Backward compatibility — proxy mode reconciliation unchanged."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import reconcile_to_bank
    rec = reconcile_to_bank("2026-Q2", cost_source="proxy")
    assert rec["reconciles"], rec
    assert rec["cost_source"] == "proxy"


def test_v10340_meta_reflects_cost_source_mode():
    """rollup_meta exposes which mode is being run."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import rollup_meta
    m = rollup_meta("matrix")
    assert m["cost_source_mode"] == "matrix"
    assert "MATRIX" in m["cost_source"]
    p = rollup_meta("proxy")
    assert p["cost_source_mode"] == "proxy"
    assert "PROXY" in p["cost_source"]


# ────────────────────────────────────────────────────────────────────
# Section 3 — Matrix total integrity
# ────────────────────────────────────────────────────────────────────

def test_v10340_segment_indirect_sums_to_matrix_total():
    """Sum of matrix-mode segment indirect = apply_rules non-direct total."""
    _reimport("utils.sbu_pnl_rollup")
    _reimport("utils.cost_allocation")
    from utils.sbu_pnl_rollup import rollup_by_segment, clear_matrix_cache
    from utils.cost_allocation import apply_rules
    clear_matrix_cache()
    matrix_total = 0
    for cost_item, dist in apply_rules().items():
        if cost_item.startswith("_"):
            continue
        if isinstance(dist, dict):
            matrix_total += sum(dist.values())
    segs = rollup_by_segment("2026-Q2", cost_source="matrix")
    rollup_total = sum(b["indirect_cost"] for b in segs.values())
    # Within rounding (Decimal quantize at 2dp)
    assert abs(matrix_total - rollup_total) < 100.0, (
        f"matrix={matrix_total}, rollup={rollup_total}"
    )


def test_v10340_cbk_sector_indirect_sums_to_business_segment_indirect():
    """Sector-level indirect (matrix) sums to segment-level indirect."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import (
        rollup_by_segment, rollup_by_cbk_sector, clear_matrix_cache,
    )
    clear_matrix_cache()
    segs = rollup_by_segment("2026-Q2", cost_source="matrix")
    sectors = rollup_by_cbk_sector("2026-Q2", cost_source="matrix")
    for biz_seg in ("MICRO", "SMALL", "MEDIUM", "CORPORATE"):
        seg_indirect = segs.get(biz_seg, {}).get("indirect_cost", 0)
        sector_sum = sum(
            b["indirect_cost"]
            for (s, _sector), b in sectors.items() if s == biz_seg
        )
        # Tolerance widens because Decimal rounding compounds per sector
        assert abs(seg_indirect - sector_sum) < 100.0, (
            f"{biz_seg}: seg={seg_indirect}, sectors_sum={sector_sum}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Recursion safety
# ────────────────────────────────────────────────────────────────────

def test_v10340_cost_allocation_no_longer_imports_rollup():
    """_default_driver_values reads customer data directly — no recursion."""
    text = (REPO / "utils" / "cost_allocation.py").read_text()
    # The OLD recursion path must not exist
    assert "from utils.sbu_pnl_rollup import rollup_by_segment" not in text
    # New direct customer read must exist
    assert "customer_intelligence_business.json" in text


def test_v10340_clear_matrix_cache_callable():
    """clear_matrix_cache exposed + actually clears the cache."""
    _reimport("utils.sbu_pnl_rollup")
    from utils.sbu_pnl_rollup import (
        clear_matrix_cache, _MATRIX_INDIRECT_CACHE,
        _matrix_indirect_by_segment,
    )
    _matrix_indirect_by_segment("2026-Q2")
    assert "2026-Q2" in _MATRIX_INDIRECT_CACHE
    clear_matrix_cache()
    assert "2026-Q2" not in _MATRIX_INDIRECT_CACHE


# ────────────────────────────────────────────────────────────────────
# Section 5 — G229 gate
# ────────────────────────────────────────────────────────────────────

def test_v10340_g229_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_matrix_rollup_wiring
    result = gate_matrix_rollup_wiring()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G229"


def test_v10340_g229_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G229", gate_matrix_rollup_wiring)' in text


def test_v10340_drilldown_page_carries_matrix_banner():
    """114_sbu_drilldown surfaces the v10.340 matrix banner."""
    text = (REPO / "pages" / "114_sbu_drilldown.py").read_text()
    assert "v10.340" in text
    assert "MATRIX" in text or "matrix" in text
    # Must explain negative PBT is honest
    assert "honest" in text.lower() or "undersized" in text.lower()
