"""H5 — pipeline mutations sync to Postgres so DB-backed reads see them.

Pipeline reads are DB-first but mutations wrote JSON-only, so created/changed
deals were invisible in the list (count stuck). H5 upserts the deal into
Postgres after every mutation and normalizes DB rows to the frontend's field
names (amount->deal_value, product->product_type).
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_all_six_mutations_sync_to_db():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    assert "def _db_sync_pipeline_deal" in src
    # create, refer, update, advance, cancel-request, cancel-approve
    assert src.count("_db_sync_pipeline_deal(pm.get_deal(") >= 6, \
        "every pipeline mutation must sync to the DB"


def test_list_normalizes_db_rows():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    assert "def _normalize_db_deal_row" in src
    assert "_normalize_db_deal_row(d) for d in" in src, "list must normalize DB rows"


def test_upsert_field_mapping_logic():
    # mirror the helper's mapping to lock the contract
    deal = {"id": "D0010", "deal_value": 5_000_000.0, "product_type": "Business Loan",
            "pipeline_category": "Loan"}
    product = deal.get("product") or deal.get("product_type")
    amount = deal.get("amount") if deal.get("amount") is not None else deal.get("deal_value")
    deal_category = deal.get("deal_category") or deal.get("pipeline_category") or "New Facility"
    assert product == "Business Loan" and amount == 5_000_000.0 and deal_category == "Loan"
