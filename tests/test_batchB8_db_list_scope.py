"""Batch B8 — the Postgres pipeline-list branch must enforce cascade scope.

The DB read path previously returned SELECT * with no scope filter and no
permission enrichment (the JSON path did both). These lock the two behaviours
the DB branch now relies on: normalized rows keep staff_code, and the scope
filter drops out-of-scope deals.
"""
from utils.api import _normalize_db_deal_row
from utils.api_pipeline_scope import filter_deals_by_visible_codes


def test_db_row_keeps_staff_code_for_scoping():
    row = {"id": "DEAL00001", "staff_code": "300731", "amount": 5_000_000,
           "stage": "Lead", "metadata": "{}"}
    n = _normalize_db_deal_row(row)
    assert n["staff_code"] == "300731"
    assert n["deal_value"] == 5_000_000   # amount mapped through


def test_scope_filter_excludes_out_of_scope_db_rows():
    rows = [
        _normalize_db_deal_row({"id": "D1", "staff_code": "300731", "stage": "Lead"}),
        _normalize_db_deal_row({"id": "D2", "staff_code": "999999", "stage": "Lead"}),
    ]
    out = filter_deals_by_visible_codes(rows, {"300731"})
    assert {d["id"] for d in out} == {"D1"}
