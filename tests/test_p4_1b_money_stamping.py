"""Phase 4-1b — money stamping at booking (resilient, additive)."""
import json
from pathlib import Path
import pytest
from utils.fx_engine import FxRateStore, stamp_money_fields


@pytest.fixture
def store(tmp_path):
    p = tmp_path / "fx_rates.json"
    p.write_text(json.dumps({"base_currency": "KES", "rates": [
        {"currency": "KES", "rate_to_kes": 1.0,    "rate_type": "mid", "effective_date": "2026-01-01", "active": True},
        {"currency": "USD", "rate_to_kes": 129.50, "rate_type": "mid", "effective_date": "2026-06-01", "active": True},
    ]}), encoding="utf-8")
    return FxRateStore(p)


def test_stamp_usd_deal(store):
    deal = {"client_name": "Acme", "deal_value": 1000.0, "currency": "USD"}
    stamp_money_fields(deal, amount_key="deal_value", as_of="2026-06-15", store=store)
    assert deal["currency"] == "USD"
    assert deal["currency_book"] == "FCY"
    assert deal["fx_rate"] == 129.50
    assert deal["amount_kes"] == 129500.0
    assert deal["fx_rate_source"] == "admin_table"


def test_stamp_kes_deal_defaults(store):
    deal = {"client_name": "Local", "deal_value": 5000.0}  # no currency -> KES
    stamp_money_fields(deal, amount_key="deal_value", store=store)
    assert deal["currency"] == "KES"
    assert deal["currency_book"] == "LCY"
    assert deal["fx_rate"] == 1.0
    assert deal["amount_kes"] == 5000.0


def test_stamp_unconfigured_currency_is_resilient(store):
    # JPY has no rate — must NOT raise; currency_book still set, fx unresolved.
    deal = {"client_name": "Tokyo", "deal_value": 1000.0, "currency": "JPY"}
    stamp_money_fields(deal, amount_key="deal_value", as_of="2026-06-15", store=store)
    assert deal["currency"] == "JPY"
    assert deal["currency_book"] == "FCY"     # always computable
    assert deal["fx_rate"] is None
    assert deal["amount_kes"] is None
    assert deal["fx_rate_source"] == "unresolved"


def test_stamp_does_not_clobber_other_fields(store):
    deal = {"client_name": "Acme", "deal_value": 1000.0, "currency": "USD",
            "stage": "Lead", "staff_code": "300731"}
    stamp_money_fields(deal, amount_key="deal_value", as_of="2026-06-15", store=store)
    assert deal["stage"] == "Lead" and deal["staff_code"] == "300731"
    assert deal["client_name"] == "Acme"
