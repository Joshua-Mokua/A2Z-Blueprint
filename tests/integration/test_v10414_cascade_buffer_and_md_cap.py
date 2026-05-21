"""Integration tests for v10.414 — F2 part A: Cascade Buffer Engine + MD cap.

15 tests across 5 sections.
"""

import sys
import tempfile
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Engine module
# ────────────────────────────────────────────────────────────────────

def test_v10414_engine_module_exists():
    path = REPO / "utils" / "cascade_buffer_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def set_buffer_cap",
        "def get_buffer_cap",
        "def get_all_buffer_caps",
        "def remove_buffer_cap",
        "def validate_buffer",
        "def is_within_cap",
        "def compute_effective_amount",
        "def extract_base_from_amount",
        "def summarize_cascade_buffer",
        "class BufferCapConfig",
        "class BufferValidation",
        "class BufferSummary",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10414_zero_streamlit_imports():
    text = (REPO / "utils" / "cascade_buffer_engine.py").read_text()
    import re
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0, (
        f"Engine has {len(streamlit_imports)} streamlit imports — must be ZERO"
    )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Engine behavior
# ────────────────────────────────────────────────────────────────────

def _isolated_engine():
    """Fresh engine module pointing at a temp file."""
    for k in list(sys.modules):
        if "cascade_buffer" in k:
            del sys.modules[k]
    import importlib
    mod = importlib.import_module("utils.cascade_buffer_engine")
    tmp_dir = Path(tempfile.mkdtemp())
    mod.BUFFER_CAPS_FILE = tmp_dir / "test.json"
    return mod


def test_v10414_set_and_get_cap():
    mod = _isolated_engine()
    cfg = mod.set_buffer_cap("PBT", 0.20, "MD001", note="Q1 review")
    assert cfg is not None
    assert cfg.kpi == "PBT"
    assert cfg.max_stretch_pct == 0.20
    assert cfg.set_by == "MD001"
    assert cfg.note == "Q1 review"

    got = mod.get_buffer_cap("PBT")
    assert got is not None
    assert got.max_stretch_pct == 0.20


def test_v10414_rejects_invalid_caps():
    mod = _isolated_engine()
    # Exceeds absolute max
    assert mod.set_buffer_cap("PBT", 0.99, "MD") is None
    # Negative
    assert mod.set_buffer_cap("PBT", -0.1, "MD") is None
    # Empty KPI
    assert mod.set_buffer_cap("", 0.1, "MD") is None
    # No set_by
    assert mod.set_buffer_cap("PBT", 0.1, "") is None
    # Non-numeric
    assert mod.set_buffer_cap("PBT", "abc", "MD") is None


def test_v10414_validate_within_cap():
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    v = mod.validate_buffer("PBT", 0.15)
    assert v.ok is True
    assert v.kpi == "PBT"
    assert v.cap_pct == 0.20


def test_v10414_validate_over_cap():
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    v = mod.validate_buffer("PBT", 0.30)
    assert v.ok is False
    assert "exceeds" in v.reason.lower()


def test_v10414_validate_uncapped_kpi():
    mod = _isolated_engine()
    # Non-zero stretch on uncapped KPI fails
    v1 = mod.validate_buffer("UNSET_KPI", 0.10)
    assert v1.ok is False
    assert "no cap" in v1.reason.lower()
    # Zero stretch on uncapped KPI passes
    v2 = mod.validate_buffer("UNSET_KPI", 0.0)
    assert v2.ok is True


def test_v10414_compute_effective_amount():
    from utils.cascade_buffer_engine import compute_effective_amount, extract_base_from_amount
    assert compute_effective_amount(100, 0.20) == 120.0
    assert compute_effective_amount(100, 0) == 100.0
    assert compute_effective_amount(0, 0.5) == 0.0
    # Reverse
    assert extract_base_from_amount(120, 0.20) == 100.0
    assert extract_base_from_amount(100, 0) == 100.0


def test_v10414_summary_with_violations():
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    entries = [{
        "kpi": "PBT", "period": "2026",
        "allocations": [
            {"to_name": "OK", "amount": 100, "stretch_pct": 0.10},
            {"to_name": "BAD", "amount": 100, "stretch_pct": 0.30},
        ],
    }]
    s = mod.summarize_cascade_buffer("PBT", "2026", entries)
    assert s.cap_pct == 0.20
    assert s.total_allocations == 2
    assert s.allocations_with_stretch == 2
    assert s.max_stretch_observed_pct == 0.30
    assert len(s.notes) == 1
    assert "VIOLATION" in s.notes[0]


def test_v10414_remove_cap():
    mod = _isolated_engine()
    mod.set_buffer_cap("PBT", 0.20, "MD")
    assert mod.get_buffer_cap("PBT") is not None
    assert mod.remove_buffer_cap("PBT", "MD") is True
    assert mod.get_buffer_cap("PBT") is None
    # Removing nonexistent fails gracefully
    assert mod.remove_buffer_cap("NONEXISTENT", "MD") is False


def test_v10414_dataclasses_json_serializable():
    """All dataclasses must round-trip through asdict for React JSON."""
    mod = _isolated_engine()
    cfg = mod.set_buffer_cap("PBT", 0.15, "MD")
    v = mod.validate_buffer("PBT", 0.10)
    s = mod.summarize_cascade_buffer("PBT", "2026", [])

    import json
    json.dumps(cfg.to_dict())
    json.dumps(v.to_dict())
    json.dumps(s.to_dict())


# ────────────────────────────────────────────────────────────────────
# Section 3 — UI wiring
# ────────────────────────────────────────────────────────────────────

def test_v10414_cascade_imports_engine():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "from utils.cascade_buffer_engine import" in text


def test_v10414_f2_ui_present():
    text = (REPO / "pages" / "12_cascade.py").read_text()
    assert "F2: Per-KPI stretch caps" in text
    assert "set_buffer_cap(" in text


# ────────────────────────────────────────────────────────────────────
# Section 4 — FastAPI endpoints
# ────────────────────────────────────────────────────────────────────

def test_v10414_buffer_endpoints_registered():
    for k in list(sys.modules):
        if "api_cascade" in k:
            del sys.modules[k]
    from utils.api_cascade import router
    buffer_routes = [r for r in router.routes if "/buffer" in r.path]
    # v10.414 shipped 6 routes; subsequent batches may add more (v10.415 adds /apply)
    assert len(buffer_routes) >= 6, f"Expected >=6 buffer routes, got {len(buffer_routes)}"

    paths = {r.path for r in buffer_routes}
    expected = {
        "/api/v1/cascade/buffer/caps",
        "/api/v1/cascade/buffer/cap/{kpi}",
        "/api/v1/cascade/buffer/validate",
        "/api/v1/cascade/buffer/summary/{kpi}/{period}",
    }
    assert expected.issubset(paths), f"Missing: {expected - paths}"


# ────────────────────────────────────────────────────────────────────
# Section 5 — Gate
# ────────────────────────────────────────────────────────────────────

def test_v10414_g300_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10414_cascade_buffer_engine_and_md_cap
    r = gate_v10414_cascade_buffer_engine_and_md_cap()
    assert r["passed"], r.get("violations")
