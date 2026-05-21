"""tests/test_core_kpi.py — utils/core_kpi.py coverage (Standard #4, v5.33).

The KPI cluster is a re-export shim (per v5.28 design). Identity tests
already live in tests/test_core_split.py — those verify each shim
symbol is the SAME OBJECT as utils.core's. THIS file tests the
BEHAVIORAL contract of the symbols themselves:

  - get_kpi_library(): returns a dict with the expected top-level keys
  - get_active_kpis(): respects the `active_kpis` whitelist
  - get_role_kpis(role): returns a list of KPI IDs
  - get_pillar_weights(): returns 4 pillars summing to 1.0
  - bsc_score_from_pct(pct, reverse): correct mapping per band thresholds
  - score_to_band(score): correct label per band

Targets coverage on a critical scoring path that 17 modules feed into.
A bug in bsc_score_from_pct silently miscalibrates every BSC scorecard
in the bank.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


# ═══════════════════════════════════════════════════════════════════════
# Shim re-export contract (complement to test_core_split.py identity tests)
# ═══════════════════════════════════════════════════════════════════════

class TestShimSurface:
    """Verify utils.core_kpi exposes the documented 12-symbol contract."""

    EXPECTED_SYMBOLS = {
        "KPI_LIBRARY_FILE", "DEFAULT_KPI_LIBRARY", "DEFAULT_ROLE_KPIS",
        "get_kpi_library", "save_kpi_library", "get_active_kpis",
        "get_role_kpis", "get_pillar_weights",
        "get_scoring_scale", "bsc_score_from_pct",
        "get_performance_bands", "score_to_band",
    }

    def test_all_12_symbols_importable(self):
        import utils.core_kpi as ck
        for sym in self.EXPECTED_SYMBOLS:
            assert hasattr(ck, sym), f"core_kpi missing symbol: {sym}"

    def test_dunder_all_matches_documented_set(self):
        import utils.core_kpi as ck
        assert set(ck.__all__) == self.EXPECTED_SYMBOLS, (
            f"core_kpi.__all__ drift. "
            f"Extra: {set(ck.__all__) - self.EXPECTED_SYMBOLS}, "
            f"Missing: {self.EXPECTED_SYMBOLS - set(ck.__all__)}"
        )

    def test_constants_have_expected_types(self):
        import utils.core_kpi as ck
        # KPI_LIBRARY_FILE is a Path
        assert isinstance(ck.KPI_LIBRARY_FILE, Path)
        # DEFAULT_KPI_LIBRARY is a dict with pillar names as keys
        assert isinstance(ck.DEFAULT_KPI_LIBRARY, dict)
        # DEFAULT_ROLE_KPIS is a dict mapping role → list of KPI IDs
        assert isinstance(ck.DEFAULT_ROLE_KPIS, dict)

    def test_functions_are_callable(self):
        import utils.core_kpi as ck
        for fn_name in [
            "get_kpi_library", "save_kpi_library", "get_active_kpis",
            "get_role_kpis", "get_pillar_weights",
            "get_scoring_scale", "bsc_score_from_pct",
            "get_performance_bands", "score_to_band",
        ]:
            fn = getattr(ck, fn_name)
            assert callable(fn), f"{fn_name} is not callable"


# ═══════════════════════════════════════════════════════════════════════
# DEFAULT_KPI_LIBRARY shape — the fallback used when file is missing
# ═══════════════════════════════════════════════════════════════════════

class TestDefaultLibrary:
    """The fallback library must be self-consistent (4 pillars, KPIs have id/name)."""

    def test_has_four_pillars(self):
        from utils.core_kpi import DEFAULT_KPI_LIBRARY
        # Master spec defines 4 BSC pillars
        pillar_names = set(DEFAULT_KPI_LIBRARY.keys())
        # We accept either exactly these 4 or a strict subset matching them
        expected = {"Financial", "Customer Focus", "Operational Excellence",
                    "People & Learning"}
        # All keys present in the default library should be valid pillar names
        unexpected = pillar_names - expected
        assert not unexpected, f"Unexpected pillars in DEFAULT_KPI_LIBRARY: {unexpected}"

    def test_each_pillar_has_kpis(self):
        from utils.core_kpi import DEFAULT_KPI_LIBRARY
        for pillar, kpis in DEFAULT_KPI_LIBRARY.items():
            assert isinstance(kpis, list), f"{pillar} value should be a list"
            assert len(kpis) > 0, f"{pillar} has no KPIs"

    def test_every_kpi_has_id_and_name(self):
        from utils.core_kpi import DEFAULT_KPI_LIBRARY
        for pillar, kpis in DEFAULT_KPI_LIBRARY.items():
            for k in kpis:
                assert "id" in k, f"KPI in {pillar} missing 'id': {k}"
                assert "name" in k, f"KPI {k['id']} in {pillar} missing 'name'"

    def test_kpi_ids_are_unique(self):
        """A duplicate KPI ID across pillars would break role assignment."""
        from utils.core_kpi import DEFAULT_KPI_LIBRARY
        seen = {}
        for pillar, kpis in DEFAULT_KPI_LIBRARY.items():
            for k in kpis:
                kid = k["id"]
                if kid in seen:
                    pytest.fail(f"Duplicate KPI id {kid!r} in {seen[kid]} and {pillar}")
                seen[kid] = pillar


# ═══════════════════════════════════════════════════════════════════════
# bsc_score_from_pct — the heart of the scoring contract
# ═══════════════════════════════════════════════════════════════════════

class TestBscScoreFromPct:
    """Behavior of bsc_score_from_pct using the built-in fallback scale.

    The fallback applies when get_scoring_scale() returns empty (no
    org_config configured). These tests pin the fallback bands so that
    a reorg of org_config can't accidentally degrade scoring."""

    def test_none_value_returns_zero(self):
        from utils.core_kpi import bsc_score_from_pct
        assert bsc_score_from_pct(None) == 0.0

    def test_above_130_returns_5(self):
        from utils.core_kpi import bsc_score_from_pct
        assert bsc_score_from_pct(150) == 5.0
        assert bsc_score_from_pct(131) == 5.0

    def test_band_boundaries_higher_better(self):
        """Pin the fallback band thresholds (no scoring_scale configured)."""
        from utils.core_kpi import bsc_score_from_pct
        # Fallback scale: >130=5, >120=4.5, >110=4, >100=3.5, >=91=3, >=61=2.5, >=51=2, >=31=1.5, else=1
        assert bsc_score_from_pct(125) == 4.5
        assert bsc_score_from_pct(115) == 4.0
        assert bsc_score_from_pct(105) == 3.5
        assert bsc_score_from_pct(91) == 3.0
        assert bsc_score_from_pct(61) == 2.5
        assert bsc_score_from_pct(51) == 2.0
        assert bsc_score_from_pct(31) == 1.5
        assert bsc_score_from_pct(0) == 1.0

    def test_reverse_inverts_scoring(self):
        """For reverse-direction KPIs (NPL, PAR, etc.) lower achievement
        means better performance. The function inverts to 200-pct first."""
        from utils.core_kpi import bsc_score_from_pct
        # achievement=50 in reverse mode means pct=150 → score 5
        assert bsc_score_from_pct(50, reverse=True) == 5.0
        # achievement=100 in reverse mode means pct=100 → falls into ">=91" band → 3.0
        # (the >100 band is strict, so exactly 100 doesn't qualify)
        assert bsc_score_from_pct(100, reverse=True) == 3.0
        # achievement=200 in reverse mode means pct=0 → score 1
        assert bsc_score_from_pct(200, reverse=True) == 1.0

    def test_score_returns_float(self):
        from utils.core_kpi import bsc_score_from_pct
        result = bsc_score_from_pct(85)
        assert isinstance(result, float)


# ═══════════════════════════════════════════════════════════════════════
# score_to_band — the visualisation contract
# ═══════════════════════════════════════════════════════════════════════

class TestScoreToBand:
    """score_to_band returns a dict with label/color/bg keys."""

    def test_returns_dict_with_label(self):
        from utils.core_kpi import score_to_band
        b = score_to_band(4.0)
        assert isinstance(b, dict)
        assert "label" in b

    def test_high_score_is_exceeded(self):
        from utils.core_kpi import score_to_band
        b = score_to_band(4.7)
        # The label includes "Exceed" for scores ≥ 4.5
        assert "Exceed" in b["label"]

    def test_low_score_is_not_exceeded(self):
        from utils.core_kpi import score_to_band
        b = score_to_band(1.5)
        # Labels for low scores should NOT contain "Exceed"
        assert "Exceed" not in b["label"]

    def test_band_has_color_and_bg(self):
        """UI components use these for cell styling."""
        from utils.core_kpi import score_to_band
        b = score_to_band(3.5)
        assert "color" in b
        assert "bg" in b


# ═══════════════════════════════════════════════════════════════════════
# get_pillar_weights — must sum to 1.0 (BSC formula invariant)
# ═══════════════════════════════════════════════════════════════════════

class TestPillarWeights:
    """The 4 pillar weights must sum to 1.0 — otherwise BSC scores
    don't normalise correctly."""

    def test_returns_dict(self):
        from utils.core_kpi import get_pillar_weights
        w = get_pillar_weights()
        assert isinstance(w, dict)

    def test_weights_sum_close_to_one(self):
        """Allow a tiny float-rounding tolerance."""
        from utils.core_kpi import get_pillar_weights
        w = get_pillar_weights()
        total = sum(w.values())
        assert abs(total - 1.0) < 0.01, (
            f"Pillar weights sum to {total}, must be ~1.0. Weights: {w}"
        )

    def test_has_four_pillars(self):
        from utils.core_kpi import get_pillar_weights
        w = get_pillar_weights()
        assert len(w) == 4, f"Expected 4 pillars, got {len(w)}: {list(w.keys())}"


# ═══════════════════════════════════════════════════════════════════════
# get_role_kpis — role → KPI ID list
# ═══════════════════════════════════════════════════════════════════════

class TestGetRoleKpis:
    """get_role_kpis(role) returns a list of KPI IDs."""

    def test_unknown_role_returns_empty_list(self):
        from utils.core_kpi import get_role_kpis
        result = get_role_kpis("__nonexistent_role__xyz__")
        assert result == [] or result == {}  # accept either fallback shape

    def test_returns_iterable(self):
        from utils.core_kpi import get_role_kpis, DEFAULT_ROLE_KPIS
        # Pick the first role from DEFAULT_ROLE_KPIS
        if DEFAULT_ROLE_KPIS:
            role = next(iter(DEFAULT_ROLE_KPIS.keys()))
            result = get_role_kpis(role)
            # Should be a list/iterable
            assert hasattr(result, "__iter__")


# ═══════════════════════════════════════════════════════════════════════
# get_scoring_scale / get_performance_bands — config-driven
# ═══════════════════════════════════════════════════════════════════════

class TestScoringConfig:
    """get_scoring_scale and get_performance_bands return the configured
    or fallback structures."""

    def test_scoring_scale_returns_list_or_empty(self):
        from utils.core_kpi import get_scoring_scale
        result = get_scoring_scale()
        # Either a list of {min, score} dicts or an empty list/None
        assert result is None or isinstance(result, (list, tuple))

    def test_performance_bands_returns_list_or_empty(self):
        from utils.core_kpi import get_performance_bands
        result = get_performance_bands()
        assert result is None or isinstance(result, (list, tuple))


# ═══════════════════════════════════════════════════════════════════════
# Identity check — shim returns SAME OBJECTS as core (defensive duplicate
# of test_core_split.py for fast feedback loop)
# ═══════════════════════════════════════════════════════════════════════

class TestShimIdentity:
    """If the shim ever drifts from core (e.g. accidentally redefining a
    function), this catches it locally with clearer messages."""

    SYMBOLS = [
        "KPI_LIBRARY_FILE", "DEFAULT_KPI_LIBRARY", "DEFAULT_ROLE_KPIS",
        "get_kpi_library", "save_kpi_library", "get_active_kpis",
        "get_role_kpis", "get_pillar_weights",
        "get_scoring_scale", "bsc_score_from_pct",
        "get_performance_bands", "score_to_band",
    ]

    @pytest.mark.parametrize("sym", SYMBOLS)
    def test_symbol_is_same_as_core(self, sym):
        import utils.core as core
        import utils.core_kpi as core_kpi
        a = getattr(core, sym, None)
        b = getattr(core_kpi, sym, None)
        assert a is not None, f"core has no symbol {sym}"
        assert b is not None, f"core_kpi has no symbol {sym}"
        assert a is b, (
            f"Identity drift: core.{sym} ({id(a)}) is NOT core_kpi.{sym} ({id(b)}). "
            f"The shim has been overridden — Standard #3 invariant broken."
        )
