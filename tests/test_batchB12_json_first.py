"""Batch B12 — pipeline reads are JSON-first.

The JSON store is written synchronously on every create/mutation; Postgres is a
best-effort mirror that lagged (15 of 17 deals were JSON-only, invisible to the
DB-first list/analytics/summary). This guards the demo-safe default so it isn't
flipped back accidentally.
"""
from utils import api


def test_pipeline_reads_are_json_first():
    assert api._PIPELINE_READ_DB_FIRST is False
