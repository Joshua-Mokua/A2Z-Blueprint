"""tests/test_actuals_engine_module.py — Targeted unit tests for
utils/actuals_engine.py.

v10.103 — Phase 1C continuation. utils/actuals_engine.py is the
existing BSC autofit pipeline (CBS data → per-RM aggregates →
KPI submission via bsc_engine). Phase 1D will extend this same
pipeline to operational-table sources, so verifying the existing
pure-function surface is a prerequisite.

Coverage situation pre-v10.103:
  - Module: 685 statements, 21 covered (3.2%)
  - 663 uncovered statements is the 3rd-largest gap in utils/

What this file exercises:
  - _map_cbs_to_kpi()      pure function, ID and name-fallback paths
  - _period_to_engine_format()   period normalization
  - get_cbs_paths()        path resolution
  - _root()                project root resolution
  - get_period_label()     period label derivation
  - module-level imports   (just importing exercises ~80 statements)

What this file deliberately does NOT exercise:
  - compute_actuals_from_cbs()   needs full CBS file fixtures
  - aggregate_cbs_by_rm()        same — fixture-heavy
  - _build_from_cbs()            depends on staff list + KPI library
  - inject_cascade_targets()     needs an XLSX fixture

Those need integration-test scope (fixture CBS dir + KPI library) which
is a follow-up. For now, the pure-function surface plus import-time
coverage gives a meaningful jump in line coverage for the module.

Coverage gain estimate: 663 uncovered → ~400-450 uncovered
(line-coverage 3.2% → ~35-40%) just from import + pure-function tests.
Closing the gap to 90% needs the integration tests later.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ── Fixture: stub streamlit so module-level imports succeed ────────

@pytest.fixture(scope="module")
def actuals_engine():
    """Import utils.actuals_engine with streamlit stubbed.

    actuals_engine doesn't use streamlit directly, but it imports
    utils.core which does. Stubbing keeps the test environment-
    independent and avoids requiring streamlit as a hard test dep.
    """
    if "streamlit" not in sys.modules:
        st = types.ModuleType("streamlit")
        st.cache_data = lambda *a, **k: (lambda f: f)
        st.cache_resource = lambda *a, **k: (lambda f: f)
        st.session_state = {}
        sys.modules["streamlit"] = st
    for m in ("plotly", "plotly.express",
              "plotly.graph_objects", "plotly.subplots"):
        sys.modules.setdefault(m, types.ModuleType(m))

    import utils.actuals_engine as mod
    return mod


# ── _map_cbs_to_kpi — primary KPI lookup function ─────────────────

class TestMapCbsToKpi:
    """The KPI ID → rm_data field mapper. The most-called function in
    the actuals pipeline — every staff × every KPI row passes through
    here. Two paths: exact ID match (ID_MAP) and name-fallback (text
    matching against KPI name)."""

    def test_exact_id_match_loan_disb(self, actuals_engine):
        result = actuals_engine._map_cbs_to_kpi(
            "LOAN_DISB", "anything", {"loan_disbursed": 1500.0})
        assert result == 1500.0

    def test_exact_id_match_dep_growth(self, actuals_engine):
        result = actuals_engine._map_cbs_to_kpi(
            "DEP_GROWTH", "anything", {"total_deposits": 50000.0})
        assert result == 50000.0

    def test_exact_id_match_npl_ratio(self, actuals_engine):
        result = actuals_engine._map_cbs_to_kpi(
            "NPL_RATIO", "anything", {"npl_ratio": 0.05})
        assert result == 0.05

    def test_id_match_case_insensitive(self, actuals_engine):
        """ID lookup uses .upper() so lowercase IDs still match."""
        result = actuals_engine._map_cbs_to_kpi(
            "loan_disb", "anything", {"loan_disbursed": 100.0})
        assert result == 100.0

    def test_missing_field_returns_zero(self, actuals_engine):
        """If the ID maps to a field not present in rm_data, return
        0.0 (NOT raise) — silent zero is the documented contract for
        missing data."""
        result = actuals_engine._map_cbs_to_kpi(
            "LOAN_DISB", "x", {})
        assert result == 0.0

    def test_none_field_returns_zero(self, actuals_engine):
        """If the field is present but None (CBS returned null),
        return 0.0 — not raise."""
        result = actuals_engine._map_cbs_to_kpi(
            "LOAN_DISB", "x", {"loan_disbursed": None})
        assert result == 0.0

    def test_name_fallback_retail_deposits(self, actuals_engine):
        """Unknown ID falls through to name matching — 'retail
        deposits' in name → retail_deposits field."""
        result = actuals_engine._map_cbs_to_kpi(
            "UNKNOWN", "Retail Deposits Volume",
            {"retail_deposits": 2000.0})
        assert result == 2000.0

    def test_name_fallback_npl(self, actuals_engine):
        """Unknown ID + 'NPL' in name → npl_ratio field."""
        result = actuals_engine._map_cbs_to_kpi(
            "UNKNOWN", "NPL Ratio Performance",
            {"npl_ratio": 0.06})
        assert result == 0.06

    def test_name_fallback_fee_income(self, actuals_engine):
        """Unknown ID + 'fee' in name → fee_income field."""
        result = actuals_engine._map_cbs_to_kpi(
            "UNKNOWN", "Fee and Commission Income",
            {"fee_income": 800.0})
        assert result == 800.0

    def test_name_fallback_pbt(self, actuals_engine):
        """Unknown ID + 'pbt' in name → pbt field."""
        result = actuals_engine._map_cbs_to_kpi(
            "UNKNOWN", "PBT Achievement", {"pbt": 1200.0})
        assert result == 1200.0

    def test_name_fallback_dormancy(self, actuals_engine):
        """Unknown ID + 'dormancy'/'dormant' in name → dormancy_pct."""
        result = actuals_engine._map_cbs_to_kpi(
            "UNKNOWN", "Account Dormancy Rate",
            {"dormancy_pct": 0.12})
        assert result == 0.12

    def test_name_fallback_no_match_returns_zero(self, actuals_engine):
        """Unknown ID + name that matches nothing in fallback → 0.0."""
        result = actuals_engine._map_cbs_to_kpi(
            "UNKNOWN", "Completely Unrecognized Metric",
            {"loan_disbursed": 9999.0})  # data present but irrelevant
        assert result == 0.0

    def test_id_takes_precedence_over_name(self, actuals_engine):
        """If both ID and name match different fields, ID wins."""
        # LOAN_DISB → loan_disbursed; name says 'deposits' → would map
        # to total_deposits. ID match should win.
        result = actuals_engine._map_cbs_to_kpi(
            "LOAN_DISB", "Customer Deposits",
            {"loan_disbursed": 100.0, "total_deposits": 999.0})
        assert result == 100.0  # not 999.0

    def test_returns_float_type(self, actuals_engine):
        """Return type is always float, even when input is int."""
        result = actuals_engine._map_cbs_to_kpi(
            "LOAN_DISB", "x", {"loan_disbursed": 100})  # int
        assert isinstance(result, float)
        assert result == 100.0

    def test_business_borrowers_id(self, actuals_engine):
        """BUSINESS_BORROWERS → business_borrowers field."""
        result = actuals_engine._map_cbs_to_kpi(
            "BUSINESS_BORROWERS", "x", {"business_borrowers": 250})
        assert result == 250.0

    def test_par_id(self, actuals_engine):
        """PAR → par_ratio field."""
        result = actuals_engine._map_cbs_to_kpi(
            "PAR", "x", {"par_ratio": 0.08})
        assert result == 0.08

    def test_collection_throughput_aliased(self, actuals_engine):
        """COLLECTION_THROUGHPUT shares npl_ratio field per the ID
        mapping (documented platform behaviour — the throughput KPI
        uses NPL inverse)."""
        result = actuals_engine._map_cbs_to_kpi(
            "COLLECTION_THROUGHPUT", "x", {"npl_ratio": 0.04})
        assert result == 0.04

    def test_nim_aliases_to_nfi(self, actuals_engine):
        """NIM and NFI both map to nfi field."""
        nim = actuals_engine._map_cbs_to_kpi(
            "NIM", "x", {"nfi": 500})
        nfi = actuals_engine._map_cbs_to_kpi(
            "TOTAL_NFI", "x", {"nfi": 500})
        assert nim == nfi == 500.0


# ── _period_to_engine_format ──────────────────────────────────────

class TestPeriodConversion:
    """The period format converter for legacy → engine format."""

    def test_returns_string(self, actuals_engine):
        result = actuals_engine._period_to_engine_format("2025-Q1")
        assert isinstance(result, str)

    def test_format_is_yyyy_mm(self, actuals_engine):
        """Output is YYYY-MM format regardless of input."""
        result = actuals_engine._period_to_engine_format("2025-Q1")
        # YYYY-MM pattern: 4 digits, dash, 2 digits
        assert len(result) == 7
        assert result[4] == "-"
        year = int(result[:4])
        month = int(result[5:])
        assert 2020 <= year <= 2050
        assert 1 <= month <= 12

    def test_handles_quarterly_input(self, actuals_engine):
        """Q1, Q2, Q3, Q4 inputs all resolve to a YYYY-MM."""
        for q in ("Q1", "Q2", "Q3", "Q4"):
            result = actuals_engine._period_to_engine_format(
                f"2025-{q}")
            assert result is not None

    def test_handles_monthly_input(self, actuals_engine):
        """Monthly (YYYY-MM) input passes through gracefully."""
        result = actuals_engine._period_to_engine_format("2025-06")
        # Documented behaviour: returns current-month — not a strict
        # parser. Test asserts no exception, not a specific value.
        assert isinstance(result, str)


# ── Path helpers ──────────────────────────────────────────────────

class TestPathHelpers:
    """get_cbs_paths and _root resolve to project-relative paths."""

    def test_root_returns_path(self, actuals_engine):
        root = actuals_engine._root()
        assert isinstance(root, Path)

    def test_root_exists(self, actuals_engine):
        root = actuals_engine._root()
        assert root.exists(), (
            f"_root() returned {root} which doesn't exist")

    def test_get_cbs_paths_returns_tuple(self, actuals_engine):
        paths = actuals_engine.get_cbs_paths()
        assert isinstance(paths, tuple)
        assert len(paths) == 2  # (cbs_dir, override_dir)

    def test_get_cbs_paths_first_is_path(self, actuals_engine):
        paths = actuals_engine.get_cbs_paths()
        assert isinstance(paths[0], Path)

    def test_get_period_label_returns_string(self, actuals_engine):
        label = actuals_engine.get_period_label()
        assert isinstance(label, str)
        assert len(label) > 0


# ── Module-level imports & exports ────────────────────────────────

class TestModuleExports:
    """The module exposes the documented public API."""

    def test_compute_actuals_from_cbs_callable(self, actuals_engine):
        """The main entry point exists and is callable."""
        assert callable(actuals_engine.compute_actuals_from_cbs)

    def test_aggregate_cbs_by_rm_callable(self, actuals_engine):
        assert callable(actuals_engine.aggregate_cbs_by_rm)

    def test_aggregate_cbs_by_branch_callable(self, actuals_engine):
        assert callable(actuals_engine.aggregate_cbs_by_branch)

    def test_compute_bank_aggregates_callable(self, actuals_engine):
        assert callable(actuals_engine.compute_bank_aggregates)

    def test_inject_cascade_targets_callable(self, actuals_engine):
        assert callable(actuals_engine.inject_cascade_targets)
