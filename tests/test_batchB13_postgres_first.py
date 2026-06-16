"""Batch B13 — pipeline reads are Postgres-first (the all-on-Postgres rule).

Safe because the write path is now atomic: _db_sync_pipeline_deal raises on a
real failure (no silent swallow) and pipeline_deal_create verifies the row
landed in Postgres and rolls back the JSON add otherwise — so a deal is in both
stores or neither.
"""
from utils import api


def test_pipeline_reads_are_postgres_first():
    assert api._PIPELINE_READ_DB_FIRST is True
