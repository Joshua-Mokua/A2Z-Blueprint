"""
tests/integration/test_treasury_live_cockpit.py
================================================================================
v10.296 — Treasury live cockpit integration tests, written BEFORE the
cockpit page (TDD / Kaizen).

The tests define what "live" means for Treasury before the
implementation can pretend otherwise.

Test discipline tighter than v10.295:
  1. Contract tests for every cockpit_read helper used by the page
  2. End-to-end test of TreasuryDashboardEngine driven by real JSON
  3. Invariant tests (sums match, no negative counts, etc.)
  4. Edge-case tests (empty data, malformed records, missing files,
     mixed legacy/current shapes)
  5. Read-only guarantee (cockpit must not mutate engine state)
  6. Audit-trail tests (every cockpit refresh emits audit_log)
  7. Access-control tests (silent try/except is a bug)
  8. Performance smoke (must handle 1000+ records without crashing)

Run: pytest tests/integration/test_treasury_live_cockpit.py -v
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_data_dir():
    d = tempfile.mkdtemp(prefix="treasury_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ============================================================
# Section 1 — TreasuryDashboardEngine contract
# ============================================================

def test_treasury_dashboard_zero_args_works():
    """The engine must be instantiable with no upstream engines.
    The cockpit will sometimes load with partial data; the engine
    must not crash."""
    from utils.treasury_dashboard import TreasuryDashboardEngine

    e = TreasuryDashboardEngine()
    r = e.generate_daily_treasury(
        report_id="T-001", as_of_date="2026-05-11",
    )
    assert r is not None
    # With no upstream engines, sections should be empty (not None)
    assert hasattr(r, "sections")


def test_treasury_dashboard_board_summary_returns_wired_flags():
    """`board_summary` must report which upstream engines are
    wired, so the cockpit can show 'data not connected' messages
    where appropriate."""
    from utils.treasury_dashboard import TreasuryDashboardEngine

    e = TreasuryDashboardEngine()
    b = e.board_summary()
    assert "alm_wired" in b
    assert "products_wired" in b
    assert "rwa_wired" in b
    assert "ftp_wired" in b
    assert "forecast_wired" in b
    # All False initially
    assert all(b[f"{k}_wired"] is False
                  for k in ["alm", "products", "rwa", "ftp", "forecast"])


def test_treasury_dashboard_with_alm_engine_wired():
    """When ALM engine is wired, dashboard.board_summary()
    must reflect it."""
    from utils.treasury_dashboard import TreasuryDashboardEngine
    from utils.treasury_alm import TreasuryALMEngine

    alm = TreasuryALMEngine()
    e = TreasuryDashboardEngine(alm_engine=alm)
    b = e.board_summary()
    assert b["alm_wired"] is True
    assert b["products_wired"] is False


# ============================================================
# Section 2 — JSON data loading + engine seeding
# ============================================================

def test_treasury_fx_json_loads_via_cockpit_read():
    """Real treasury_fx.json must load through the cockpit_read
    helper. Cockpit needs this for FX position summaries."""
    from utils.cockpit_read import load_records

    fx_path = REPO_ROOT / "data" / "treasury_fx.json"
    if not fx_path.exists():
        pytest.skip("treasury_fx.json not present in test env")

    records = load_records(
        fx_path, "treasury_fx", ("id",),
    )
    # Real data has 200 records (per pre-flight); test for
    # any reasonable count
    assert isinstance(records, list)
    if records:
        first = records[0]
        # Field contract — these must exist for the cockpit to
        # display rows
        for required_field in ("id", "deal_type", "currency"):
            assert required_field in first, (
                f"treasury_fx.json record missing `{required_field}` "
                f"— cockpit display will be broken"
            )


def test_treasury_dashboard_loads_real_irrbb_json():
    """If irrbb.json exists with current shape, the cockpit
    must be able to extract key ratios."""
    irrbb_path = REPO_ROOT / "data" / "irrbb.json"
    if not irrbb_path.exists():
        pytest.skip("irrbb.json not present")
    d = json.loads(irrbb_path.read_text())
    # Document the contract the cockpit relies on
    assert isinstance(d, dict)
    for required_field in (
        "as_at", "cbk_limit_ear_pct", "cbk_limit_eve_pct",
        "scenarios",
    ):
        assert required_field in d, (
            f"irrbb.json missing `{required_field}` — cockpit "
            f"IRRBB tab will break"
        )


def test_treasury_dashboard_loads_real_liquidity_json():
    """liquidity_metrics.json must provide LCR for the cockpit."""
    path = REPO_ROOT / "data" / "liquidity_metrics.json"
    if not path.exists():
        pytest.skip("liquidity_metrics.json not present")
    d = json.loads(path.read_text())
    assert "lcr" in d
    assert "lcr_minimum_pct" in d


# ============================================================
# Section 3 — Cockpit aggregator invariants (cockpit_treasury_read)
# ============================================================

def test_treasury_open_work_returns_well_formed_dict(tmp_data_dir):
    """Treasury open-work composer must always return the
    documented keys, even with no data."""
    # This will exist after cockpit_read is extended;
    # the test asserts the contract.
    from utils.cockpit_read import treasury_open_work

    snap = treasury_open_work(data_dir=tmp_data_dir)
    required_keys = [
        "fx_positions_count",
        "irrbb_breaches",
        "lcr_pct",
        "lcr_min_pct",
        "lcr_breached",
        "open_fx_deals",
        "as_at",
    ]
    for k in required_keys:
        assert k in snap, (
            f"treasury_open_work must always return `{k}` "
            f"— cockpit headlines depend on it"
        )


def test_treasury_open_work_counts_are_non_negative(tmp_data_dir):
    """Invariant: all counts must be >= 0. A negative count
    means a sum got off-by-one or a wrong filter."""
    from utils.cockpit_read import treasury_open_work

    snap = treasury_open_work(data_dir=tmp_data_dir)
    for k, v in snap.items():
        if isinstance(v, (int, float)):
            assert v >= 0, (
                f"treasury_open_work returned negative `{k}` = {v}"
            )


def test_treasury_open_work_handles_missing_files(tmp_data_dir):
    """If data files don't exist, snapshot must still return
    sensible defaults rather than crashing."""
    from utils.cockpit_read import treasury_open_work
    # tmp_data_dir is empty; no JSON files
    snap = treasury_open_work(data_dir=tmp_data_dir)
    assert snap["fx_positions_count"] == 0
    assert snap["open_fx_deals"] == 0
    assert snap["lcr_breached"] is False  # no breach if no data


def test_treasury_open_work_lcr_breach_detection(tmp_data_dir):
    """If LCR < minimum, lcr_breached must be True."""
    from utils.cockpit_read import treasury_open_work

    # Seed a breached LCR
    liq = {
        "as_at": "2026-05-11",
        "currency": "KES",
        "lcr": 95.0,  # below 100% threshold
        "lcr_minimum_pct": 100.0,
        "lcr_internal_target_pct": 110.0,
    }
    (tmp_data_dir / "liquidity_metrics.json").write_text(
        json.dumps(liq))

    snap = treasury_open_work(data_dir=tmp_data_dir)
    assert snap["lcr_pct"] == 95.0
    assert snap["lcr_min_pct"] == 100.0
    assert snap["lcr_breached"] is True


def test_treasury_open_work_lcr_no_breach_when_compliant(tmp_data_dir):
    """When LCR >= minimum, breached must be False."""
    from utils.cockpit_read import treasury_open_work

    liq = {
        "as_at": "2026-05-11",
        "currency": "KES",
        "lcr": 120.0,
        "lcr_minimum_pct": 100.0,
        "lcr_internal_target_pct": 110.0,
    }
    (tmp_data_dir / "liquidity_metrics.json").write_text(
        json.dumps(liq))

    snap = treasury_open_work(data_dir=tmp_data_dir)
    assert snap["lcr_breached"] is False


def test_treasury_open_work_irrbb_breach_count(tmp_data_dir):
    """When IRRBB scenarios exceed CBK limits, breach count
    must reflect it."""
    from utils.cockpit_read import treasury_open_work

    irrbb = {
        "as_at": "2026-05-11",
        "cbk_limit_ear_pct": 20.0,
        "cbk_limit_eve_pct": 25.0,
        "scenarios": [
            {"scenario": "PARALLEL_UP_200BP", "ear_pct": 15.0,
              "eve_pct": 10.0},  # within limits
            {"scenario": "PARALLEL_DOWN_200BP", "ear_pct": 25.0,
              "eve_pct": 5.0},  # ear breach
            {"scenario": "STEEPENER", "ear_pct": 10.0,
              "eve_pct": 30.0},  # eve breach
        ],
    }
    (tmp_data_dir / "irrbb.json").write_text(json.dumps(irrbb))

    snap = treasury_open_work(data_dir=tmp_data_dir)
    assert snap["irrbb_breaches"] == 2, (
        "Two scenarios breach (one EAR, one EVE)"
    )


# ============================================================
# Section 4 — Read-only guarantee
# ============================================================

def test_treasury_open_work_does_not_mutate_data(tmp_data_dir):
    """Critical: the cockpit must never modify upstream data.
    This is a regulatory requirement (every read of regulatory
    state must leave that state untouched)."""
    from utils.cockpit_read import treasury_open_work

    liq = {
        "as_at": "2026-05-11",
        "currency": "KES",
        "lcr": 120.0,
        "lcr_minimum_pct": 100.0,
        "lcr_internal_target_pct": 110.0,
    }
    path = tmp_data_dir / "liquidity_metrics.json"
    path.write_text(json.dumps(liq))
    original_content = path.read_text()
    original_mtime = path.stat().st_mtime

    # Call the cockpit composer multiple times
    for _ in range(5):
        treasury_open_work(data_dir=tmp_data_dir)

    assert path.read_text() == original_content
    # mtime check belt-and-braces — file shouldn't be touched
    assert path.stat().st_mtime == original_mtime


# ============================================================
# Section 5 — Edge cases & malformed input
# ============================================================

def test_treasury_open_work_tolerates_malformed_json(tmp_data_dir):
    """Malformed JSON in data files must not crash the cockpit.
    Operators will sometimes hand-edit these files; the cockpit
    must degrade gracefully."""
    from utils.cockpit_read import treasury_open_work

    (tmp_data_dir / "liquidity_metrics.json").write_text(
        "{ this is not valid json")
    # Should not raise
    snap = treasury_open_work(data_dir=tmp_data_dir)
    # And should return defaults for the broken file
    assert snap["lcr_pct"] is None or snap["lcr_pct"] == 0


def test_treasury_open_work_tolerates_extra_fields(tmp_data_dir):
    """If new fields appear in data files (forward compat),
    cockpit must still work."""
    from utils.cockpit_read import treasury_open_work

    liq = {
        "as_at": "2026-05-11",
        "currency": "KES",
        "lcr": 110.0,
        "lcr_minimum_pct": 100.0,
        "lcr_internal_target_pct": 110.0,
        # Future fields
        "lcr_v2_intraday": 105.0,
        "stress_scenario": "BASEL_4_DRAFT",
        "metadata": {"introduced_in": "v10.999"},
    }
    (tmp_data_dir / "liquidity_metrics.json").write_text(
        json.dumps(liq))

    snap = treasury_open_work(data_dir=tmp_data_dir)
    # Existing fields still work
    assert snap["lcr_pct"] == 110.0
    assert snap["lcr_breached"] is False


def test_treasury_open_work_handles_fx_records_with_legacy_shapes(
    tmp_data_dir,
):
    """Some FX records may be legacy and lack newer fields.
    The cockpit must count them without skipping silently."""
    from utils.cockpit_read import treasury_open_work

    # Mix of current + legacy records
    fx = [
        {"id": 1, "deal_type": "SPOT", "direction": "BUY",
         "currency": "USD", "fcy_amount": 100000, "rate": 130.0,
         "kes_amount": 13000000, "counterparty": "BANK_A",
         "status": "OPEN"},
        {"id": 2, "deal_type": "FORWARD",
         "currency": "EUR", "fcy_amount": 50000},  # legacy
        {"deal_type": "SWAP"},  # very legacy — no id, no status
    ]
    (tmp_data_dir / "treasury_fx.json").write_text(json.dumps(fx))

    snap = treasury_open_work(data_dir=tmp_data_dir)
    # All three records counted, even legacy ones
    assert snap["fx_positions_count"] == 3


# ============================================================
# Section 6 — Performance smoke
# ============================================================

def test_treasury_open_work_handles_1k_records(tmp_data_dir):
    """The cockpit will run against production data eventually
    (1000+ records). Must complete in reasonable time."""
    from utils.cockpit_read import treasury_open_work
    import time

    # 1000 fx records
    fx = [
        {"id": i, "deal_type": "SPOT",
         "currency": ["USD", "EUR", "GBP"][i % 3],
         "fcy_amount": i * 1000,
         "status": "OPEN" if i % 2 == 0 else "SETTLED"}
        for i in range(1000)
    ]
    (tmp_data_dir / "treasury_fx.json").write_text(json.dumps(fx))

    start = time.time()
    snap = treasury_open_work(data_dir=tmp_data_dir)
    elapsed = time.time() - start

    assert snap["fx_positions_count"] == 1000
    # 1 second is generous for 1k records
    assert elapsed < 1.0, (
        f"treasury_open_work took {elapsed:.2f}s for 1k records "
        f"— too slow for live cockpit refresh"
    )


# ============================================================
# Section 7 — Page 110 manifest contract
# ============================================================

def test_page_110_manifest_entry_exists():
    """After the cockpit ships, the manifest entry must be
    present with the right module_path."""
    manifest_path = REPO_ROOT / "pages" / "_manifest.json"
    m = json.loads(manifest_path.read_text())
    entry = m["pages"].get("110_treasury_live.py")
    assert entry is not None, (
        "110_treasury_live.py missing from manifest"
    )
    assert entry["module_path"] == "treasury_alm.treasury_live"
    assert entry["department_primary"] == "treasury_alm"
    assert entry["description"], "description must be non-empty"


def test_page_110_uses_hard_require_access():
    """Per Phase 3 standing rule: no silent try/except around
    require_access."""
    path = REPO_ROOT / "pages" / "110_treasury_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    bad_pattern = (
        "try:\n"
        "    from pages._access import require_access\n"
    )
    assert bad_pattern not in src, (
        "110_treasury_live.py uses silent try/except — "
        "Phase 3 standing rule requires hard import"
    )


def test_page_110_emits_audit_log():
    """Per Phase 3 rule: cockpits emit real audit trail."""
    path = REPO_ROOT / "pages" / "110_treasury_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    assert "audit_log(" in src, (
        "110_treasury_live.py must call audit_log() at least once"
    )


def test_page_110_uses_ttl_cache():
    """Per Phase 3 rule: live cockpits use TTL caching."""
    path = REPO_ROOT / "pages" / "110_treasury_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    assert "@st.cache_data(ttl=" in src, (
        "110_treasury_live.py must use @st.cache_data(ttl=...) "
        "decorator for live refresh"
    )


# ============================================================
# Section 8 — cockpit_read.treasury_open_work API discipline
# ============================================================

def test_treasury_open_work_returns_pure_dict(tmp_data_dir):
    """Return type must be a plain dict, not a dataclass or
    custom type. Streamlit serialization expects dicts."""
    from utils.cockpit_read import treasury_open_work
    snap = treasury_open_work(data_dir=tmp_data_dir)
    assert isinstance(snap, dict)


def test_treasury_open_work_idempotent(tmp_data_dir):
    """Calling twice with same data must produce identical
    results (modulo the `as_at` timestamp if set to now)."""
    from utils.cockpit_read import treasury_open_work
    liq = {
        "as_at": "2026-05-11",
        "currency": "KES",
        "lcr": 120.0,
        "lcr_minimum_pct": 100.0,
        "lcr_internal_target_pct": 110.0,
    }
    (tmp_data_dir / "liquidity_metrics.json").write_text(
        json.dumps(liq))

    s1 = treasury_open_work(data_dir=tmp_data_dir)
    s2 = treasury_open_work(data_dir=tmp_data_dir)

    # Compare everything except as_at (which is the read-time
    # timestamp)
    keys_to_compare = set(s1.keys()) - {"as_at"}
    for k in keys_to_compare:
        assert s1[k] == s2[k], (
            f"treasury_open_work `{k}` differs across two "
            f"identical calls: {s1[k]} vs {s2[k]}"
        )
