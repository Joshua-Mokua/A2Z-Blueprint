"""
tests/integration/test_pg_ready_composers_v10308.py
================================================================================
v10.308 — Route the remaining 4 v10.306-migrated tables through
_load_table_via_shim, exposing each as a PG-ready cockpit composer
and HTTP endpoint.

v10.307 shipped:
  - _load_table_via_shim helper bridging cockpit_read to the
    v10.116 _data_source shim
  - compliance_regulatory_returns composer rewired through it
    (first PG-routed composer)

This batch applies the same pattern to the other 4 v10.306-
migrated tables. After this batch, all 5 v10.306 tables have
PG-routed composers + HTTP endpoints, so they can each be
flipped from JSON to PG independently via the
`_data_source.per_table` config.

The four:
  1. audit_reviews        → audit_reviews_records composer +
                             /api/cockpit/audit/reviews
  2. incidents            → incidents_records composer +
                             /api/cockpit/ops/incidents
  3. nps_responses        → nps_responses_records composer +
                             /api/cockpit/cx/nps
  4. rcsa_register        → rcsa_register_records composer +
                             /api/cockpit/risk/rcsa

Note: nps_responses' JSON file is data/nps.json — same
file/table name mismatch as compliance_regulatory_returns →
compliance.json. The shim handles it via the json_filename
parameter.

Test sections:
  1. Each composer exists and is callable
  2. Each composer routes through _load_table_via_shim
  3. Each composer returns list-of-dict shape
  4. Each composer is documented in the cockpit_read module
  5. Each HTTP endpoint is registered + documented
  6. EXPECTED_ENDPOINTS extended to cover all 4
  7. G198 audit gate passes
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_data_dir():
    d = tempfile.mkdtemp(prefix="pg_ready_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# Composer name → (json file, expected return list type)
COMPOSERS = {
    "audit_reviews_records":        "audit_reviews.json",
    "incidents_records":            "incidents.json",
    "nps_responses_records":        "nps.json",   # file mismatch
    "rcsa_register_records":        "rcsa_register.json",
}


# ============================================================
# Section 1 — Each composer exists
# ============================================================

def test_audit_reviews_composer_exists():
    from utils import cockpit_read
    assert hasattr(cockpit_read, "audit_reviews_records")


def test_incidents_composer_exists():
    from utils import cockpit_read
    assert hasattr(cockpit_read, "incidents_records")


def test_nps_responses_composer_exists():
    from utils import cockpit_read
    assert hasattr(cockpit_read, "nps_responses_records")


def test_rcsa_register_composer_exists():
    from utils import cockpit_read
    assert hasattr(cockpit_read, "rcsa_register_records")


# ============================================================
# Section 2 — Each composer routes through the shim
# ============================================================

def test_each_composer_routes_through_shim():
    """Greppable wiring proof — each composer body must
    reference _load_table_via_shim so the cutover config
    actually takes effect."""
    import re
    src = (REPO_ROOT / "utils" / "cockpit_read.py").read_text()
    for composer_name in COMPOSERS:
        # Match the def line and grab the body up to the next
        # top-level def. Tolerant of return annotations.
        match = re.search(
            rf"def {composer_name}\([^)]*\)"
            rf"\s*(?:->[^:]+)?:"
            rf"(.*?)(?=\ndef\s|\Z)",
            src, re.DOTALL,
        )
        assert match, (
            f"Could not locate {composer_name} composer body"
        )
        body = match.group(1)
        assert "_load_table_via_shim" in body, (
            f"{composer_name} composer must route through "
            f"_load_table_via_shim for the cutover to work"
        )


# ============================================================
# Section 3 — Each composer returns list-of-dict
# ============================================================

def test_audit_reviews_returns_list(tmp_data_dir):
    from utils.cockpit_read import audit_reviews_records
    (tmp_data_dir / "audit_reviews.json").write_text(json.dumps([
        {"id": "AR1", "audit_title": "Q1 Branch Audit"},
    ]))
    result = audit_reviews_records(data_dir=tmp_data_dir)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == "AR1"


def test_incidents_returns_list(tmp_data_dir):
    from utils.cockpit_read import incidents_records
    (tmp_data_dir / "incidents.json").write_text(json.dumps([
        {"id": "INC1", "title": "Auth service down"},
    ]))
    result = incidents_records(data_dir=tmp_data_dir)
    assert isinstance(result, list)
    assert len(result) == 1


def test_nps_responses_returns_list_from_nps_json(tmp_data_dir):
    """nps.json file → nps_responses table — the
    file/table name mismatch must be handled."""
    from utils.cockpit_read import nps_responses_records
    (tmp_data_dir / "nps.json").write_text(json.dumps([
        {"id": "NPS1", "score": 9, "band": "promoter"},
    ]))
    result = nps_responses_records(data_dir=tmp_data_dir)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["score"] == 9


def test_rcsa_register_returns_list(tmp_data_dir):
    from utils.cockpit_read import rcsa_register_records
    (tmp_data_dir / "rcsa_register.json").write_text(json.dumps([
        {"id": "RCSA1", "category": "operational"},
    ]))
    result = rcsa_register_records(data_dir=tmp_data_dir)
    assert isinstance(result, list)
    assert len(result) == 1


# ============================================================
# Section 4 — Missing file returns empty list (defensive)
# ============================================================

def test_each_composer_handles_missing_file(tmp_data_dir):
    """Each composer must return [] on missing source file.
    Cockpit consumers don't get exceptions, just empty data."""
    from utils.cockpit_read import (
        audit_reviews_records, incidents_records,
        nps_responses_records, rcsa_register_records,
    )
    for fn in (
        audit_reviews_records, incidents_records,
        nps_responses_records, rcsa_register_records,
    ):
        result = fn(data_dir=tmp_data_dir)
        assert result == [], (
            f"{fn.__name__} on empty dir returned "
            f"{result!r}; expected []"
        )


# ============================================================
# Section 5 — HTTP endpoints registered
# ============================================================

def test_each_endpoint_registered_in_api_cockpit():
    """All 4 endpoints must appear in utils/api_cockpit.py."""
    src = (REPO_ROOT / "utils" / "api_cockpit.py").read_text()
    expected_paths = [
        "/audit/reviews",
        "/ops/incidents",
        "/cx/nps",
        "/risk/rcsa",
    ]
    for path in expected_paths:
        assert path in src, (
            f"api_cockpit.py missing endpoint path: {path}"
        )


def test_each_endpoint_documented_in_module_docstring():
    """Module docstring must list each new endpoint per the
    G188 documentation contract."""
    src = (REPO_ROOT / "utils" / "api_cockpit.py").read_text()
    docstring_end = src.find("\"\"\"", 100)
    docstring = src[:docstring_end + 3]
    for path in (
        "/api/cockpit/audit/reviews",
        "/api/cockpit/ops/incidents",
        "/api/cockpit/cx/nps",
        "/api/cockpit/risk/rcsa",
    ):
        assert path in docstring, (
            f"Module docstring missing endpoint: {path}"
        )


# ============================================================
# Section 6 — EXPECTED_ENDPOINTS extended
# ============================================================

def test_api_cockpit_test_expected_endpoints_updated():
    """The api_cockpit test's EXPECTED_ENDPOINTS list must
    include the 4 new endpoints so future drift fires the
    discipline test."""
    src = (REPO_ROOT / "tests" / "integration"
           / "test_api_cockpit.py").read_text()
    for path in (
        "/api/cockpit/audit/reviews",
        "/api/cockpit/ops/incidents",
        "/api/cockpit/cx/nps",
        "/api/cockpit/risk/rcsa",
    ):
        assert path in src, (
            f"test_api_cockpit.py EXPECTED_ENDPOINTS missing: "
            f"{path}"
        )


# ============================================================
# Section 7 — pg_capable_tables unchanged
# ============================================================

def test_pg_capable_tables_unchanged():
    """The 5-table registry from v10.307 isn't expanded by
    this batch — the same 5 tables are now composer-backed.
    Future PG migrations would add to this list."""
    from utils.cockpit_read import pg_capable_tables
    tables = set(pg_capable_tables())
    expected = {
        "audit_reviews",
        "compliance_regulatory_returns",
        "incidents",
        "nps_responses",
        "rcsa_register",
    }
    assert tables == expected, (
        f"pg_capable_tables drifted: {tables ^ expected}"
    )


# ============================================================
# Section 8 — G198 audit gate
# ============================================================

def test_g198_gate_exists_and_passes():
    from scripts.audit import GATES
    g198 = None
    for gid, fn in GATES:
        if gid == "G198":
            g198 = fn()
            break
    assert g198 is not None, "G198 not registered"
    assert g198["passed"], (
        f"G198 failed. Summary: {g198.get('summary', '')}. "
        f"Violations: {g198.get('violations', [])[:5]}"
    )


# ============================================================
# Section 9 — Default-config behavior unchanged
# ============================================================

def test_default_config_no_integration_layer_config(tmp_data_dir):
    """With no integration_layer_config.json at all, each
    composer reads from JSON exactly. This is the default
    deployment state — must remain unchanged."""
    from utils.cockpit_read import (
        audit_reviews_records, incidents_records,
        nps_responses_records, rcsa_register_records,
    )
    (tmp_data_dir / "audit_reviews.json").write_text(
        json.dumps([{"id": "X"}]))
    (tmp_data_dir / "incidents.json").write_text(
        json.dumps([{"id": "Y"}]))
    (tmp_data_dir / "nps.json").write_text(
        json.dumps([{"id": "Z"}]))
    (tmp_data_dir / "rcsa_register.json").write_text(
        json.dumps([{"id": "W"}]))

    assert audit_reviews_records(
        data_dir=tmp_data_dir)[0]["id"] == "X"
    assert incidents_records(
        data_dir=tmp_data_dir)[0]["id"] == "Y"
    assert nps_responses_records(
        data_dir=tmp_data_dir)[0]["id"] == "Z"
    assert rcsa_register_records(
        data_dir=tmp_data_dir)[0]["id"] == "W"
