"""Integration tests for v10.415 — F2 part B: per-allocation stretch tuner.

15 tests across 4 sections.
"""

import sys
import tempfile
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Engine extensions
# ────────────────────────────────────────────────────────────────────

def test_v10415_engine_has_new_functions():
    text = (REPO / "utils" / "cascade_buffer_engine.py").read_text()
    for needed in (
        "def apply_stretch_to_allocations",
        "def derive_base_for_allocation",
        "def cascade_stretch_breakdown",
        "class StretchApplicationResult",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10415_engine_still_zero_streamlit():
    """v10.414 discipline must hold after v10.415 extensions."""
    text = (REPO / "utils" / "cascade_buffer_engine.py").read_text()
    import re
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


# ────────────────────────────────────────────────────────────────────
# Section 2 — apply_stretch_to_allocations behavior
# ────────────────────────────────────────────────────────────────────

def _isolated_engine():
    for k in list(sys.modules):
        if "cascade_buffer" in k:
            del sys.modules[k]
    import importlib
    mod = importlib.import_module("utils.cascade_buffer_engine")
    tmp_dir = Path(tempfile.mkdtemp())
    mod.BUFFER_CAPS_FILE = tmp_dir / "test.json"
    return mod


def test_v10415_apply_valid_stretch():
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    allocs = [
        {"to_code": "X", "to_name": "X", "amount": 100.0},
        {"to_code": "Y", "to_name": "Y", "amount": 200.0},
    ]
    r = mod.apply_stretch_to_allocations(
        allocs, {"X": 0.10, "Y": 0.15}, "PBT",
    )
    assert len(r.violations) == 0
    assert r.updated_count == 2
    x = next(a for a in r.new_allocations if a["to_code"] == "X")
    y = next(a for a in r.new_allocations if a["to_code"] == "Y")
    assert abs(x["amount"] - 110.0) < 1e-6
    assert abs(y["amount"] - 230.0) < 1e-6
    assert x["stretch_pct"] == 0.10
    assert "base_amount" in x


def test_v10415_apply_over_cap_violates():
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    allocs = [{"to_code": "X", "to_name": "X", "amount": 100.0}]
    r = mod.apply_stretch_to_allocations(allocs, {"X": 0.30}, "PBT")
    assert len(r.violations) == 1
    assert r.violations[0]["to_code"] == "X"
    # Original allocation unchanged (no mutation on violation)
    assert r.new_allocations[0]["amount"] == 100.0
    assert "stretch_pct" not in r.new_allocations[0] or r.new_allocations[0].get("stretch_pct", 0) == 0


def test_v10415_apply_preserves_unchanged():
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    allocs = [
        {"to_code": "X", "to_name": "X", "amount": 100.0},
        {"to_code": "Y", "to_name": "Y", "amount": 200.0},
    ]
    # Only update X; Y has no entry in map
    r = mod.apply_stretch_to_allocations(allocs, {"X": 0.10}, "PBT")
    assert r.updated_count == 1
    y = next(a for a in r.new_allocations if a["to_code"] == "Y")
    assert y["amount"] == 200.0  # unchanged


def test_v10415_apply_handles_existing_stretch():
    """Base must be re-derived correctly when allocation already has stretch."""
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    # Allocation already has 10% stretch → amount 110 means base 100
    allocs = [{
        "to_code": "X", "to_name": "X",
        "amount": 110.0, "stretch_pct": 0.10,
    }]
    # Re-stretch to 5%
    r = mod.apply_stretch_to_allocations(allocs, {"X": 0.05}, "PBT")
    assert len(r.violations) == 0
    x = next(a for a in r.new_allocations if a["to_code"] == "X")
    # base ≈ 100, new amount ≈ 105
    assert abs(x["amount"] - 105.0) < 1e-6
    assert x["stretch_pct"] == 0.05


def test_v10415_apply_with_invalid_input():
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    allocs = [{"to_code": "X", "to_name": "X", "amount": 100.0}]
    # Non-numeric stretch
    r = mod.apply_stretch_to_allocations(allocs, {"X": "not a number"}, "PBT")
    assert len(r.violations) == 1
    assert "not a number" in r.violations[0]["reason"].lower() or "number" in r.violations[0]["reason"].lower()


def test_v10415_derive_base_helper():
    from utils.cascade_buffer_engine import derive_base_for_allocation
    # No stretch
    assert derive_base_for_allocation({"amount": 100.0}) == 100.0
    # With stretch
    assert abs(derive_base_for_allocation({"amount": 110.0, "stretch_pct": 0.10}) - 100.0) < 1e-6
    # Zero stretch
    assert derive_base_for_allocation({"amount": 50.0, "stretch_pct": 0}) == 50.0
    # Invalid
    assert derive_base_for_allocation({"amount": "x"}) == 0.0


def test_v10415_cascade_breakdown():
    from utils.cascade_buffer_engine import cascade_stretch_breakdown
    entries = [
        {
            "kpi": "PBT",
            "allocations": [
                {"to_code": "A", "amount": 110.0, "stretch_pct": 0.10},
                {"to_code": "B", "amount": 220.0, "stretch_pct": 0.10},
            ],
        },
        {
            "kpi": "DEPOSITS",
            "allocations": [
                {"to_code": "C", "amount": 500.0},  # no stretch
            ],
        },
    ]
    b = cascade_stretch_breakdown(entries)
    # PBT: base 100+200=300, effective 110+220=330, stretch 30
    # DEPOSITS: base 500, effective 500, stretch 0
    assert abs(b["total_base"] - 800.0) < 1e-6
    assert abs(b["total_effective"] - 830.0) < 1e-6
    assert abs(b["total_stretch_added"] - 30.0) < 1e-6
    assert "PBT" in b["per_kpi"]
    assert "DEPOSITS" in b["per_kpi"]


def test_v10415_result_dataclass_serializable():
    """StretchApplicationResult must round-trip through JSON."""
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    allocs = [{"to_code": "X", "to_name": "X", "amount": 100.0}]
    r = mod.apply_stretch_to_allocations(allocs, {"X": 0.10}, "PBT")
    import json
    d = r.to_dict()
    json.dumps(d)
    assert d["kpi"] == "PBT"
    assert d["cap_pct"] == 0.20


# ────────────────────────────────────────────────────────────────────
# Section 3 — UI wiring
# ────────────────────────────────────────────────────────────────────

def test_v10415_cascade_imports_stretch_helpers():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "apply_stretch_to_allocations" in text
    assert "derive_base_for_allocation" in text
    assert "cascade_stretch_breakdown" in text


def test_v10415_stretch_tuning_ui_present():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "F2 stretch tuning" in text
    assert "🛡️ Step 3" in text
    assert "Apply stretch" in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — FastAPI endpoint
# ────────────────────────────────────────────────────────────────────

def test_v10415_apply_endpoint_registered():
    for k in list(sys.modules):
        if "api_cascade" in k:
            del sys.modules[k]
    from utils.api_cascade import router
    apply_routes = [r for r in router.routes if r.path == "/api/v1/cascade/buffer/apply"]
    assert len(apply_routes) == 1
    assert "POST" in apply_routes[0].methods


def test_v10415_stretch_pydantic_models():
    text = (REPO / "utils" / "api_cascade.py").read_text()
    assert "class StretchApplyRequest" in text
    assert "class StretchApplyResponse" in text


# ────────────────────────────────────────────────────────────────────
# Section 5 — Gate
# ────────────────────────────────────────────────────────────────────

def test_v10415_g301_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10415_per_allocation_stretch_tuner
    r = gate_v10415_per_allocation_stretch_tuner()
    assert r["passed"], r.get("violations")
