"""Integration tests for v10.417 — F5: dual-view BSC render.

14 tests across 4 sections.
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Engine
# ────────────────────────────────────────────────────────────────────

def test_v10417_engine_has_dual_view():
    text = (REPO / "utils" / "cascade_buffer_engine.py").read_text()
    for needed in (
        "def compute_dual_view",
        "def get_dual_view_summary",
        "class DualViewEntry",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10417_engine_zero_streamlit():
    """v10.412 discipline must hold."""
    text = (REPO / "utils" / "cascade_buffer_engine.py").read_text()
    import re
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


# ────────────────────────────────────────────────────────────────────
# Section 2 — compute_dual_view behavior
# ────────────────────────────────────────────────────────────────────

def _import_engine():
    for k in list(sys.modules):
        if "cascade_buffer" in k:
            del sys.modules[k]
    import importlib
    return importlib.import_module("utils.cascade_buffer_engine")


def test_v10417_dual_view_with_stretch():
    mod = _import_engine()
    synth = [{
        "from_code": "MGR1", "from_name": "Boss A",
        "kpi": "PBT", "period": "2026",
        "allocations": [
            {"to_code": "S1", "to_name": "Staff One",
             "amount": 110.0, "stretch_pct": 0.10, "base_amount": 100.0},
        ],
    }]
    dv = mod.compute_dual_view("S1", "2026", synth)
    assert len(dv) == 1
    assert dv[0].kpi == "PBT"
    assert dv[0].has_stretch is True
    assert abs(dv[0].base_amount - 100.0) < 1e-6
    assert abs(dv[0].stretch_amount - 10.0) < 1e-6
    assert dv[0].effective_amount == 110.0
    assert dv[0].from_name == "Boss A"


def test_v10417_dual_view_without_stretch():
    mod = _import_engine()
    synth = [{
        "from_code": "MGR1", "from_name": "Boss",
        "kpi": "PBT", "period": "2026",
        "allocations": [
            {"to_code": "S1", "to_name": "Staff", "amount": 200.0},  # no stretch
        ],
    }]
    dv = mod.compute_dual_view("S1", "2026", synth)
    assert len(dv) == 1
    assert dv[0].has_stretch is False
    assert dv[0].base_amount == 200.0
    assert dv[0].stretch_amount == 0.0
    assert dv[0].effective_amount == 200.0


def test_v10417_dual_view_multiple_kpis():
    mod = _import_engine()
    synth = [
        {
            "from_code": "M", "from_name": "M",
            "kpi": "PBT", "period": "2026",
            "allocations": [{"to_code": "S1", "to_name": "S1",
                             "amount": 110.0, "stretch_pct": 0.10, "base_amount": 100.0}],
        },
        {
            "from_code": "M", "from_name": "M",
            "kpi": "DEPOSITS", "period": "2026",
            "allocations": [{"to_code": "S1", "to_name": "S1", "amount": 500.0}],
        },
    ]
    dv = mod.compute_dual_view("S1", "2026", synth)
    assert len(dv) == 2
    kpis = {e.kpi for e in dv}
    assert kpis == {"PBT", "DEPOSITS"}


def test_v10417_dual_view_ignores_other_staff():
    """Staff S1 should only see their own allocations."""
    mod = _import_engine()
    synth = [{
        "from_code": "M", "from_name": "M",
        "kpi": "PBT", "period": "2026",
        "allocations": [
            {"to_code": "S1", "to_name": "S1", "amount": 100.0},
            {"to_code": "S2", "to_name": "S2", "amount": 200.0},
        ],
    }]
    dv = mod.compute_dual_view("S1", "2026", synth)
    assert len(dv) == 1
    assert dv[0].effective_amount == 100.0


def test_v10417_dual_view_empty_input():
    mod = _import_engine()
    assert mod.compute_dual_view("S1", "2026", []) == []
    assert mod.compute_dual_view("", "2026", [{"foo": "bar"}]) == []
    assert mod.compute_dual_view("S1", "", [{"foo": "bar"}]) == []


def test_v10417_summary_rollup():
    mod = _import_engine()
    synth = [
        {
            "from_code": "M", "from_name": "M",
            "kpi": "PBT", "period": "2026",
            "allocations": [{"to_code": "S1", "to_name": "S1",
                             "amount": 110.0, "stretch_pct": 0.10, "base_amount": 100.0}],
        },
        {
            "from_code": "M", "from_name": "M",
            "kpi": "DEPOSITS", "period": "2026",
            "allocations": [{"to_code": "S1", "to_name": "S1", "amount": 500.0}],
        },
    ]
    s = mod.get_dual_view_summary("S1", "2026", synth)
    assert s["kpi_count"] == 2
    assert s["stretched_kpi_count"] == 1
    assert abs(s["total_base"] - 600.0) < 1e-6   # 100 + 500
    assert abs(s["total_effective"] - 610.0) < 1e-6  # 110 + 500
    assert abs(s["total_stretch"] - 10.0) < 1e-6


def test_v10417_dataclass_json_serializable():
    mod = _import_engine()
    synth = [{"from_code": "M", "from_name": "M",
              "kpi": "PBT", "period": "2026",
              "allocations": [{"to_code": "S1", "to_name": "S1", "amount": 100.0}]}]
    dv = mod.compute_dual_view("S1", "2026", synth)
    import json
    json.dumps(dv[0].to_dict())


# ────────────────────────────────────────────────────────────────────
# Section 3 — UI wiring
# ────────────────────────────────────────────────────────────────────

def test_v10417_cascade_imports_dual_view():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "compute_dual_view" in text
    assert "get_dual_view_summary" in text


def test_v10417_dual_view_render_in_my_targets():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "_dual_view_map" in text
    assert "Stretch on your cascade" in text
    assert "F5 dual-view" in text  # marker comment


# ────────────────────────────────────────────────────────────────────
# Section 4 — FastAPI endpoints + Gate
# ────────────────────────────────────────────────────────────────────

def test_v10417_dual_view_endpoints_registered():
    for k in list(sys.modules):
        if "api_cascade" in k:
            del sys.modules[k]
    from utils.api_cascade import router
    dv_routes = [r for r in router.routes if "dual-view" in r.path]
    assert len(dv_routes) == 2, f"Expected 2 dual-view routes, got {len(dv_routes)}"

    paths = {r.path for r in dv_routes}
    expected = {
        "/api/v1/cascade/dual-view/{staff_code}/{period}",
        "/api/v1/cascade/dual-view/{staff_code}/{period}/summary",
    }
    assert expected == paths


def test_v10417_dual_view_pydantic_models():
    text = (REPO / "utils" / "api_cascade.py").read_text()
    assert "class DualViewEntryResponse" in text
    assert "class DualViewSummaryResponse" in text


def test_v10417_g303_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10417_dual_view_bsc
    r = gate_v10417_dual_view_bsc()
    assert r["passed"], r.get("violations")
