"""Integration tests for v10.355 — Live Actuals Engine + YoY Growth.

Builds on v10.354's CBS baseline. Wires the baseline into the actuals
pipeline by computing YoY deltas and writing data/actuals_yoy.json
keyed by '<staff_code>__<kpi_name>'.

16 tests across 6 sections:
  Section 1 — Module + schema (3 tests)
  Section 2 — KPI → baseline mapping logic (3 tests)
  Section 3 — YoY computation (3 tests)
  Section 4 — Sidecar save/load (3 tests)
  Section 5 — refresh_yoy orchestrator (2 tests)
  Section 6 — G241 + actuals_engine integration (2 tests)
"""

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Module + schema
# ────────────────────────────────────────────────────────────────────

def test_v10355_module_present():
    path = REPO / "utils" / "live_actuals.py"
    assert path.exists()
    text = path.read_text()
    for sym in (
        "def compute_yoy_for_rows", "def save_yoy_sidecar",
        "def load_yoy_sidecar", "def get_yoy_for",
        "def refresh_yoy", "def discover_newest_actuals",
        "def format_yoy_label", "DEFAULT_MAPPINGS",
    ):
        assert sym in text, f"Missing: {sym}"


def test_v10355_schema_registered():
    schema_path = REPO / "data" / "_schemas" / "actuals_yoy.schema.json"
    assert schema_path.exists()
    schema = json.loads(schema_path.read_text())
    assert schema["title"] == "Actuals YoY Sidecar"
    required = set(schema["required"])
    assert {"computed_at", "baseline_date", "mapped_count", "entries"}.issubset(required)


def test_v10355_sidecar_in_protected_files():
    _reimport("utils.schema_validator")
    from utils.schema_validator import list_protected_files
    assert "actuals_yoy.json" in list_protected_files()


# ────────────────────────────────────────────────────────────────────
# Section 2 — Mapping logic
# ────────────────────────────────────────────────────────────────────

def test_v10355_default_mappings_cover_main_kpis():
    """Default mappings include patterns for all core KPI categories."""
    _reimport("utils.live_actuals")
    from utils.live_actuals import DEFAULT_MAPPINGS
    patterns = [m["kpi_pattern"] for m in DEFAULT_MAPPINGS]
    # Must include deposit, loan, npl, customer-count patterns
    assert any("deposit" in p for p in patterns)
    assert any("loan" in p for p in patterns)
    assert any("npl" in p for p in patterns)
    assert any("customer" in p for p in patterns)


def test_v10355_find_mapping_returns_most_specific():
    """First-match semantics: specific patterns precede generic ones."""
    _reimport("utils.live_actuals")
    from utils.live_actuals import _find_mapping_for_kpi, DEFAULT_MAPPINGS
    # "SME Loan Book" should match the segment-specific entry,
    # not the generic "loan book" entry
    m = _find_mapping_for_kpi("SME Loan Book", DEFAULT_MAPPINGS)
    assert m is not None
    assert "SME" in m["baseline_path"], (
        f"Expected segment-specific path, got {m['baseline_path']}"
    )


def test_v10355_unmapped_kpi_returns_none():
    _reimport("utils.live_actuals")
    from utils.live_actuals import _find_mapping_for_kpi, DEFAULT_MAPPINGS
    m = _find_mapping_for_kpi("Audit Score", DEFAULT_MAPPINGS)
    assert m is None


# ────────────────────────────────────────────────────────────────────
# Section 3 — YoY computation
# ────────────────────────────────────────────────────────────────────

def test_v10355_compute_yoy_with_synthetic_data():
    """compute_yoy_for_rows produces sane growth percentages."""
    _reimport("utils.live_actuals")
    from utils.live_actuals import compute_yoy_for_rows
    baseline = {
        "snapshot_date": "2025-12-31",
        "bank_aggregates": {
            "deposits_aggregate": {"total_deposits_kes": 100.0},
            "loans_aggregate": {"gross_outstanding_kes": 80.0},
        },
    }
    rows = [
        {"Staff Code": "RM1", "KPI": "Total Deposits", "Annual Actual": 112.0},
        {"Staff Code": "RM2", "KPI": "Loan Book", "Annual Actual": 88.0},
    ]
    r = compute_yoy_for_rows(rows, baseline)
    assert r["mapped_count"] == 2
    e1 = r["entries"]["RM1__Total Deposits"]
    assert e1["growth_pct"] == 12.0
    assert e1["direction"] == "higher_is_better"
    e2 = r["entries"]["RM2__Loan Book"]
    assert e2["growth_pct"] == 10.0


def test_v10355_compute_yoy_handles_string_baseline_values():
    """Real CBS JSON aggregates store huge ints as strings — compute_yoy
    must coerce them."""
    _reimport("utils.live_actuals")
    from utils.live_actuals import compute_yoy_for_rows
    baseline = {
        "snapshot_date": "2025-12-31",
        "bank_aggregates": {
            "deposits_aggregate": {"total_deposits_kes": "110000000000"},  # string
        },
    }
    rows = [{"Staff Code": "X", "KPI": "Total Deposits", "Annual Actual": 123_200_000_000}]
    r = compute_yoy_for_rows(rows, baseline)
    assert r["mapped_count"] == 1
    e = r["entries"]["X__Total Deposits"]
    assert abs(e["growth_pct"] - 12.0) < 0.01


def test_v10355_compute_yoy_zero_baseline_growth_is_none():
    _reimport("utils.live_actuals")
    from utils.live_actuals import compute_yoy_for_rows
    baseline = {
        "snapshot_date": "2025-12-31",
        "bank_aggregates": {
            "deposits_aggregate": {"total_deposits_kes": 0},
        },
    }
    rows = [{"Staff Code": "X", "KPI": "Total Deposits", "Annual Actual": 100}]
    r = compute_yoy_for_rows(rows, baseline)
    e = r["entries"]["X__Total Deposits"]
    assert e["growth_pct"] is None


# ────────────────────────────────────────────────────────────────────
# Section 4 — Save/load
# ────────────────────────────────────────────────────────────────────

def test_v10355_save_and_load_round_trip(tmp_path):
    _reimport("utils.live_actuals")
    from utils.live_actuals import save_yoy_sidecar, load_yoy_sidecar
    sidecar = {
        "_doc": "test",
        "_schema_version": "1.0",
        "computed_at": "2026-05-12T00:00:00+00:00",
        "baseline_date": "2025-12-31",
        "mapped_count": 1,
        "entries": {
            "RM1__Total Deposits": {
                "staff_code": "RM1",
                "kpi_name": "Total Deposits",
                "current_value": 112.0,
                "baseline_value": 100.0,
                "growth_pct": 12.0,
                "direction": "higher_is_better",
                "baseline_path": "deposits_aggregate.total_deposits_kes",
            }
        },
    }
    p = tmp_path / "actuals_yoy.json"
    save_yoy_sidecar(sidecar, path=p)
    loaded = load_yoy_sidecar(path=p)
    assert loaded == sidecar


def test_v10355_get_yoy_for_returns_entry():
    _reimport("utils.live_actuals")
    from utils.live_actuals import get_yoy_for, load_yoy_sidecar
    # Use the actual sidecar that exists in the repo
    sc = load_yoy_sidecar()
    assert sc is not None, "Repo sidecar should exist"
    if sc["entries"]:
        first_key = next(iter(sc["entries"]))
        first_entry = sc["entries"][first_key]
        result = get_yoy_for(first_entry["staff_code"], first_entry["kpi_name"])
        assert result is not None
        assert result == first_entry


def test_v10355_get_yoy_for_unknown_returns_none():
    _reimport("utils.live_actuals")
    from utils.live_actuals import get_yoy_for
    assert get_yoy_for("NONEXISTENT", "ALSO NONEXISTENT") is None


# ────────────────────────────────────────────────────────────────────
# Section 5 — refresh_yoy orchestrator
# ────────────────────────────────────────────────────────────────────

def test_v10355_refresh_yoy_produces_sidecar():
    _reimport("utils.live_actuals")
    from utils.live_actuals import refresh_yoy
    result = refresh_yoy()
    assert "_schema_version" in result
    assert "mapped_count" in result
    assert isinstance(result["mapped_count"], int)


def test_v10355_format_yoy_label_includes_growth_pct():
    _reimport("utils.live_actuals")
    from utils.live_actuals import format_yoy_label
    entry = {
        "current_value": 112.0,
        "baseline_value": 100.0,
        "growth_pct": 12.0,
        "direction": "higher_is_better",
    }
    label = format_yoy_label(entry)
    assert "12.0%" in label or "+12.0%" in label
    assert "baseline" in label.lower()


# ────────────────────────────────────────────────────────────────────
# Section 6 — G241 + actuals_engine integration
# ────────────────────────────────────────────────────────────────────

def test_v10355_g241_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_live_actuals
    result = gate_live_actuals()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G241"


def test_v10355_compute_actuals_calls_refresh_yoy():
    """v10.356 (cycle-break correction): the original v10.355 placed
    refresh_yoy() INSIDE compute_actuals_from_cbs, which created a
    actuals_engine → live_actuals → cbs_baseline → actuals_engine
    cycle that G128 flagged. v10.356 inverts: callers (app.py /
    7_admin.py admin refresh) now call refresh_yoy AFTER
    compute_actuals_from_cbs returns. This test asserts:
      1. actuals_engine.py does NOT import live_actuals (cycle gone)
      2. 7_admin.py DOES call refresh_yoy after compute_actuals_from_cbs
    """
    ae_text = (REPO / "utils" / "actuals_engine.py").read_text()
    assert "from utils.live_actuals import refresh_yoy" not in ae_text, (
        "actuals_engine must NOT import live_actuals (creates cycle)"
    )
    admin_text = (REPO / "pages" / "7_admin.py").read_text()
    assert "from utils.live_actuals import refresh_yoy" in admin_text
    assert "refresh_yoy(actuals_path=" in admin_text or \
           "refresh_yoy(" in admin_text
