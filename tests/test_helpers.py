"""tests/test_helpers.py — small targeted tests for translation helpers.

These are pure-function tests for the small bits of glue that hold the
system together. They run fast and don't need fixtures.
"""
from __future__ import annotations

from datetime import datetime

import pytest


# ── _legacy_period_to_engine (utils/core.py) ────────────────────────────
class TestLegacyPeriodTranslator:
    """Translate the various legacy period strings used across the
    codebase into the BSC engine's canonical 'YYYY-MM' / 'YYYY-Q[1-4]'."""

    @pytest.mark.parametrize("legacy,expected", [
        ("Feb 2026",       "2026-02"),  # update_bsc_from_modules default
        ("Mar 2026",       "2026-03"),
        ("Feb-26",         "2026-02"),  # actuals_engine label format
        ("Dec-25",         "2025-12"),
        ("February 2026",  "2026-02"),  # full month name
        ("2026-04",        "2026-04"),  # already canonical
        ("2026-Q2",        "2026-Q2"),  # quarterly canonical
    ])
    def test_known_formats_translate(self, legacy, expected):
        from utils.core import _legacy_period_to_engine
        assert _legacy_period_to_engine(legacy) == expected

    @pytest.mark.parametrize("legacy", ["", "  ", "garbage", "2026", None, 42])
    def test_garbage_returns_well_formed_fallback(self, legacy):
        """Garbage in → today's YYYY-MM fallback. Always 7 chars and
        parseable. Critical: must NEVER raise (the engine pipeline
        would break if the translator could throw)."""
        from utils.core import _legacy_period_to_engine
        got = _legacy_period_to_engine(legacy)
        assert isinstance(got, str)
        assert len(got) == 7
        assert got[4] == "-"
        assert got[:4].isdigit()
        # Round-trip via strptime to confirm parseable
        datetime.strptime(got, "%Y-%m")  # raises if malformed


# ── Period roundtrip with bsc_engine ────────────────────────────────────
class TestPeriodRoundTrip:
    """The translator output should be ACCEPTED by bsc_engine._normalise_period.
    This is the contract between the bridge function and the engine."""

    @pytest.mark.parametrize("legacy", [
        "Feb 2026", "Mar 2026", "Feb-26", "Dec-25", "February 2026",
        "2026-04", "2026-Q2", "", "garbage",
    ])
    def test_translator_output_accepted_by_engine(self, legacy):
        from utils.core import _legacy_period_to_engine
        from utils.bsc_engine import _normalise_period
        translated = _legacy_period_to_engine(legacy)
        # The engine MUST accept whatever the translator produces
        normalised = _normalise_period(translated)
        assert normalised is not None, (
            f"Translator → engine roundtrip broken for {legacy!r}: "
            f"translator returned {translated!r} which engine rejects."
        )
