"""Phase 4-1 — FX foundation regression suite."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from utils.fx_engine import (
    FxRateStore, FxRateError, normalize_money, currency_book, BASE_CURRENCY,
)


@pytest.fixture
def store(tmp_path):
    p = tmp_path / "fx_rates.json"
    p.write_text(json.dumps({
        "base_currency": "KES",
        "rates": [
            {"currency": "KES", "rate_to_kes": 1.0,    "rate_type": "mid",  "effective_date": "2026-01-01", "active": True},
            {"currency": "USD", "rate_to_kes": 120.00, "rate_type": "mid",  "effective_date": "2026-01-01", "active": True},
            {"currency": "USD", "rate_to_kes": 129.50, "rate_type": "mid",  "effective_date": "2026-06-01", "active": True},
            {"currency": "USD", "rate_to_kes": 130.10, "rate_type": "sell", "effective_date": "2026-06-01", "active": True},
            {"currency": "EUR", "rate_to_kes": 999.00, "rate_type": "mid",  "effective_date": "2026-06-01", "active": False},
        ],
    }), encoding="utf-8")
    return FxRateStore(p)


def test_base_currency_always_one():
    assert FxRateStore(Path("/nonexistent.json")).resolve_rate("KES") == Decimal("1")


def test_lcy_fcy_classification():
    assert currency_book("KES") == "LCY"
    assert currency_book("kes") == "LCY"
    assert currency_book("USD") == "FCY"
    assert currency_book("") == "LCY"      # defaults to base
    assert currency_book(None) == "LCY"


def test_resolver_picks_latest_effective_on_or_before_asof(store):
    # As of mid-2026 the June rate wins; early 2026 still sees the Jan rate.
    assert store.resolve_rate("USD", as_of="2026-06-15") == Decimal("129.50")
    assert store.resolve_rate("USD", as_of="2026-03-01") == Decimal("120.00")
    # Before any rate exists -> error (no rate on/before date)
    with pytest.raises(FxRateError):
        store.resolve_rate("USD", as_of="2025-12-31")


def test_rate_type_separation(store):
    assert store.resolve_rate("USD", as_of="2026-06-15", rate_type="sell") == Decimal("130.10")
    with pytest.raises(FxRateError):
        store.resolve_rate("USD", rate_type="bogus")


def test_inactive_rate_ignored(store):
    with pytest.raises(FxRateError):
        store.resolve_rate("EUR", as_of="2026-06-15")   # only EUR row is inactive


def test_missing_currency_raises_loudly(store):
    with pytest.raises(FxRateError):
        store.resolve_rate("JPY", as_of="2026-06-15")


def test_normalize_money_stamps_rate_and_kes(store):
    m = normalize_money("1000", "USD", as_of="2026-06-15", store=store)
    assert m.currency == "USD"
    assert m.fx_rate == Decimal("129.50")
    assert m.amount_kes == Decimal("129500.00")
    assert m.currency_book == "FCY"
    assert m.fx_rate_source == "admin_table"
    d = m.as_dict()
    assert d["amount_kes"] == 129500.0 and d["currency_book"] == "FCY"


def test_normalize_money_kes_passthrough(store):
    m = normalize_money("5000", "KES", store=store)
    assert m.fx_rate == Decimal("1") and m.amount_kes == Decimal("5000.00")
    assert m.currency_book == "LCY" and m.fx_rate_source == "system"


def test_upsert_keeps_history_and_replaces_same_key(store):
    n_before = len(store.list_rates("USD"))
    store.upsert_rate("USD", 131.00, "2026-07-01", rate_type="mid")  # new date -> history
    assert len(store.list_rates("USD")) == n_before + 1
    store.upsert_rate("USD", 131.50, "2026-07-01", rate_type="mid")  # same key -> replace
    assert len(store.list_rates("USD")) == n_before + 1
    assert store.resolve_rate("USD", as_of="2026-07-15") == Decimal("131.50")


def test_upsert_rejects_nonpositive(store):
    with pytest.raises(FxRateError):
        store.upsert_rate("USD", 0, "2026-07-01")
    with pytest.raises(FxRateError):
        store.upsert_rate("USD", -5, "2026-07-01")


def test_corrupt_file_raises_not_silently_defaults(tmp_path):
    p = tmp_path / "fx_rates.json"
    p.write_text("{ this is not json", encoding="utf-8")
    with pytest.raises(Exception):   # json.JSONDecodeError — loud, by design
        FxRateStore(p)


def test_absent_file_is_first_run_not_error(tmp_path):
    st = FxRateStore(tmp_path / "does_not_exist.json")
    assert st.list_rates() == []
    assert st.resolve_rate("KES") == Decimal("1")
