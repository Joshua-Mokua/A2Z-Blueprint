"""Integration tests for v10.410 — Tab consolidation (10→6) + Co-KPI pairing.

Per Joshua's two directives:
1. Tab count >6 violates the "after six we start a new" rule
2. MD pairing dropdown — Commercial + Retail chiefs share PBT etc.

13 tests across 4 sections.
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _cascade_text():
    return (REPO / "pages" / "12_cascade.py").read_text()


# ────────────────────────────────────────────────────────────────────
# Section 1 — Tab consolidation
# ────────────────────────────────────────────────────────────────────

def test_v10410_six_top_level_tabs():
    """Top-level tabs reduced to exactly 6."""
    text = _cascade_text()
    # Count tuples in _tab_defs (each ("...", "...") on its own line)
    import re
    # Find _tab_defs block
    m = re.search(r"_tab_defs = \[(.*?)\]", text, re.DOTALL)
    assert m, "_tab_defs not found"
    block = m.group(1)
    # Count entries: each starts with `    ("`
    entries = re.findall(r'^\s*\("[^"]+",\s*"[^"]+"\)', block, re.MULTILINE)
    assert len(entries) == 6, f"Expected 6 top-level tabs, got {len(entries)}"


def test_v10410_top_level_keys_are_new():
    """The 6 top-level keys are the consolidated ones."""
    text = _cascade_text()
    for key in ("bank_setup", "cascade_alloc", "my_view",
                "team_analytics", "health", "negotiation"):
        assert f'"{key}"' in text, f"Missing top-level key: {key}"


def test_v10410_subtab_map_exists():
    text = _cascade_text()
    assert "_SUBTAB_MAP = {" in text
    assert "_build_sub_tabs" in text


def test_v10410_handler_blocks_use_containers():
    """Existing handler blocks use `with _tab_idx_xxx:` (container) not index."""
    text = _cascade_text()
    # Old pattern should be gone
    assert "with tabs[_tab_idx_" not in text
    # New pattern present
    assert "with _tab_idx_bank_targets:" in text
    assert "with _tab_idx_set_targets:" in text


def test_v10410_kpi_pairing_subtab_in_map():
    """Co-KPI pairing has its own sub-tab key in SUBTAB_MAP."""
    text = _cascade_text()
    assert '"kpi_pairing"' in text
    assert "🤝 Co-KPI pairing" in text


# ────────────────────────────────────────────────────────────────────
# Section 2 — Tab visibility
# ────────────────────────────────────────────────────────────────────

def test_v10410_tab_visible_new_keys():
    text = (REPO / "utils" / "core_audit.py").read_text()
    for key in ("bank_setup", "cascade_alloc", "my_view",
                "team_analytics", "health", "negotiation"):
        assert f'"{key}"' in text


def test_v10410_tab_visible_legacy_keys_retained():
    """Legacy sub-tab keys retained for backward compat."""
    text = (REPO / "utils" / "core_audit.py").read_text()
    for key in ("bank_targets", "fixed_kpis", "set_targets",
                "my_targets", "team_progress", "cascade_tree",
                "coverage", "review_requests"):
        assert f'"{key}"' in text, f"Legacy key missing: {key}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Co-KPI pairing engine
# ────────────────────────────────────────────────────────────────────

def test_v10410_pairing_engine_exists():
    path = REPO / "utils" / "kpi_ownership_pairing.py"
    assert path.exists()
    text = path.read_text()
    for needed in ("def get_co_owners", "def list_shared_kpis",
                   "def apply_pairing_strategy", "def is_shared_kpi",
                   "class CoOwnership", "class PairingResult"):
        assert needed in text, f"Missing: {needed}"


def test_v10410_ownership_map_has_shared_kpis():
    """JSON file has ≥5 shared KPIs."""
    import json as _j
    raw = _j.loads((REPO / "data" / "kpi_ownership_map.json").read_text())
    shared = [k for k, v in raw.items()
              if not k.startswith("_")
              and isinstance(v, dict)
              and len(v.get("primary_owners", [])) >= 2]
    assert len(shared) >= 5
    # PBT must be in there
    assert "PBT" in shared


def test_v10410_pairing_equal_split_math():
    for k in list(sys.modules):
        if "kpi_ownership_pairing" in k:
            del sys.modules[k]
    from utils.kpi_ownership_pairing import apply_pairing_strategy
    r = apply_pairing_strategy(
        "PBT", 10000.0,
        ["Director Retail Banking", "Director Commercial Banking"],
        "equal_split",
    )
    assert all(v == 5000.0 for v in r.allocations.values())


def test_v10410_pairing_manual_normalizes():
    for k in list(sys.modules):
        if "kpi_ownership_pairing" in k:
            del sys.modules[k]
    from utils.kpi_ownership_pairing import apply_pairing_strategy
    # Shares 60/40 → 6000/4000
    r = apply_pairing_strategy(
        "PBT", 10000.0,
        ["Director Retail Banking", "Director Commercial Banking"],
        "manual",
        manual_shares={"Director Retail Banking": 60,
                       "Director Commercial Banking": 40},
    )
    assert r.allocations["Director Retail Banking"] == 6000.0
    assert r.allocations["Director Commercial Banking"] == 4000.0


# ────────────────────────────────────────────────────────────────────
# Section 4 — State + Gate
# ────────────────────────────────────────────────────────────────────

def test_v10410_engine_state_preserved():
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10410_g296_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10410_tab_consolidation_and_pairing
    r = gate_v10410_tab_consolidation_and_pairing()
    assert r["passed"], r.get("violations")
