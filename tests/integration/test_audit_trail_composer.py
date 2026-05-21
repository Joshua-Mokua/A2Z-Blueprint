"""
tests/integration/test_audit_trail_composer.py
================================================================================
v10.305 — Single audit trail composer reading data/audit_log.json,
wired into the Credit + Compliance cockpits' last tabs.

v10.300 (Credit) and v10.301 (Compliance) shipped tab 7 with
placeholder banners pointing operators to data/audit_log.json
manually. This batch ships a real composer that reads the file
with filtering (by action, module, user, date range), wires it
into both cockpit tabs, and exposes it via HTTP for the React
SPA.

CIMS tab 7 is already wired to its module-specific audit
history (#176, `cims_audit_history.json`) — different file,
different schema. Out of scope here.

Treasury tab 7 is the dashboard report — also out of scope.

Test sections:
  1. audit_log_records composer contract
  2. Filter by action / module / user / date range
  3. Sort + pagination (latest_n style)
  4. Empty-state graceful (missing file → empty list)
  5. Read-only guarantee
  6. Page 111 + 112 wired (no more placeholder banners)
  7. /api/cockpit/audit/log endpoint registered
  8. G196 audit gate liveness
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
    d = tempfile.mkdtemp(prefix="audit_trail_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ============================================================
# Section 1 — Composer contract
# ============================================================

def test_audit_log_records_composer_exists():
    from utils import cockpit_read
    assert hasattr(cockpit_read, "audit_log_records"), (
        "cockpit_read must expose audit_log_records composer"
    )


def test_audit_log_records_returns_documented_shape(
    tmp_data_dir,
):
    from utils.cockpit_read import audit_log_records
    result = audit_log_records(data_dir=tmp_data_dir)
    for k in ("records", "count", "filters", "as_at"):
        assert k in result, (
            f"audit_log_records missing key `{k}`"
        )


def test_audit_log_records_returns_list_in_records_key(
    tmp_data_dir,
):
    from utils.cockpit_read import audit_log_records
    result = audit_log_records(data_dir=tmp_data_dir)
    assert isinstance(result["records"], list)
    # Empty data → empty records list, count == 0
    assert result["count"] == 0


def test_audit_log_records_handles_missing_file(tmp_data_dir):
    """If audit_log.json doesn't exist (fresh deploy),
    composer returns empty list rather than crashing."""
    from utils.cockpit_read import audit_log_records
    result = audit_log_records(data_dir=tmp_data_dir)
    assert result["records"] == []


# ============================================================
# Section 2 — Reads real data
# ============================================================

def test_audit_log_records_reads_synthetic_data(tmp_data_dir):
    from utils.cockpit_read import audit_log_records

    records = [
        {"ts": "2026-05-11T10:00:00", "user": "alice",
         "action": "login", "detail": "", "module": "auth",
         "before": "", "after": ""},
        {"ts": "2026-05-11T10:05:00", "user": "bob",
         "action": "credit_audit_view", "detail": "",
         "module": "credit_live",
         "before": "", "after": ""},
    ]
    (tmp_data_dir / "audit_log.json").write_text(
        json.dumps(records))

    result = audit_log_records(data_dir=tmp_data_dir)
    assert result["count"] == 2
    assert len(result["records"]) == 2


# ============================================================
# Section 3 — Filters
# ============================================================

def test_audit_log_records_filter_by_action(tmp_data_dir):
    from utils.cockpit_read import audit_log_records

    records = [
        {"ts": "2026-05-11T10:00:00", "user": "alice",
         "action": "login", "module": "auth"},
        {"ts": "2026-05-11T10:05:00", "user": "bob",
         "action": "credit_audit_view",
         "module": "credit_live"},
        {"ts": "2026-05-11T10:10:00", "user": "carol",
         "action": "credit_audit_view",
         "module": "credit_live"},
    ]
    (tmp_data_dir / "audit_log.json").write_text(
        json.dumps(records))

    result = audit_log_records(
        data_dir=tmp_data_dir, action="credit_audit_view")
    assert result["count"] == 2
    for r in result["records"]:
        assert r["action"] == "credit_audit_view"


def test_audit_log_records_filter_by_module(tmp_data_dir):
    from utils.cockpit_read import audit_log_records

    records = [
        {"ts": "2026-05-11T10:00:00", "action": "x",
         "module": "auth"},
        {"ts": "2026-05-11T10:05:00", "action": "y",
         "module": "credit_live"},
        {"ts": "2026-05-11T10:10:00", "action": "z",
         "module": "compliance_live"},
    ]
    (tmp_data_dir / "audit_log.json").write_text(
        json.dumps(records))

    result = audit_log_records(
        data_dir=tmp_data_dir, module="credit_live")
    assert result["count"] == 1
    assert result["records"][0]["module"] == "credit_live"


def test_audit_log_records_filter_by_user(tmp_data_dir):
    from utils.cockpit_read import audit_log_records

    records = [
        {"ts": "2026-05-11T10:00:00", "user": "alice",
         "action": "x"},
        {"ts": "2026-05-11T10:05:00", "user": "bob",
         "action": "y"},
        {"ts": "2026-05-11T10:10:00", "user": "alice",
         "action": "z"},
    ]
    (tmp_data_dir / "audit_log.json").write_text(
        json.dumps(records))

    result = audit_log_records(
        data_dir=tmp_data_dir, user="alice")
    assert result["count"] == 2


def test_audit_log_records_filter_records_filters_metadata(
    tmp_data_dir,
):
    """The filters dict in the response must reflect what was
    applied — operators can confirm at-a-glance."""
    from utils.cockpit_read import audit_log_records

    (tmp_data_dir / "audit_log.json").write_text(json.dumps([]))
    result = audit_log_records(
        data_dir=tmp_data_dir,
        action="credit_audit_view",
        module="credit_live",
        user="alice",
    )
    assert result["filters"]["action"] == "credit_audit_view"
    assert result["filters"]["module"] == "credit_live"
    assert result["filters"]["user"] == "alice"


def test_audit_log_records_filter_combined(tmp_data_dir):
    """Multiple filters apply AND-wise."""
    from utils.cockpit_read import audit_log_records

    records = [
        {"ts": "1", "user": "alice", "action": "x",
         "module": "credit"},
        {"ts": "2", "user": "alice", "action": "y",
         "module": "credit"},
        {"ts": "3", "user": "bob", "action": "x",
         "module": "credit"},
        {"ts": "4", "user": "alice", "action": "x",
         "module": "compliance"},
    ]
    (tmp_data_dir / "audit_log.json").write_text(
        json.dumps(records))

    result = audit_log_records(
        data_dir=tmp_data_dir,
        action="x", module="credit", user="alice")
    assert result["count"] == 1


# ============================================================
# Section 4 — Limit + sort
# ============================================================

def test_audit_log_records_sorted_most_recent_first(
    tmp_data_dir,
):
    """Default sort: most recent first by `ts`. Operators want
    to see latest activity, not the oldest."""
    from utils.cockpit_read import audit_log_records

    records = [
        {"ts": "2026-05-11T10:00:00", "action": "a"},
        {"ts": "2026-05-11T10:05:00", "action": "b"},
        {"ts": "2026-05-11T10:10:00", "action": "c"},
    ]
    (tmp_data_dir / "audit_log.json").write_text(
        json.dumps(records))
    result = audit_log_records(data_dir=tmp_data_dir)
    timestamps = [r["ts"] for r in result["records"]]
    assert timestamps == [
        "2026-05-11T10:10:00",
        "2026-05-11T10:05:00",
        "2026-05-11T10:00:00",
    ]


def test_audit_log_records_limit_caps_output(tmp_data_dir):
    """Default limit caps the response so the API doesn't
    return 1M records to a React component."""
    from utils.cockpit_read import audit_log_records

    records = [
        {"ts": f"2026-05-11T10:{i:02d}:00", "action": "x"}
        for i in range(50)
    ]
    (tmp_data_dir / "audit_log.json").write_text(
        json.dumps(records))
    result = audit_log_records(data_dir=tmp_data_dir, limit=10)
    assert len(result["records"]) == 10
    # count reflects the FILTERED total, not the limited
    # response — distinct fields matter
    assert result["count"] == 50


# ============================================================
# Section 5 — Read-only guarantee
# ============================================================

def test_audit_log_records_does_not_mutate_file(tmp_data_dir):
    from utils.cockpit_read import audit_log_records

    records = [
        {"ts": "1", "user": "alice", "action": "x"},
    ]
    path = tmp_data_dir / "audit_log.json"
    path.write_text(json.dumps(records))
    original = path.read_text()
    original_mtime = path.stat().st_mtime

    for _ in range(5):
        audit_log_records(data_dir=tmp_data_dir)

    assert path.read_text() == original
    assert path.stat().st_mtime == original_mtime


# ============================================================
# Section 6 — Page wiring
# ============================================================

def test_page_111_uses_audit_log_composer():
    """Credit cockpit tab 7 must use audit_log_records and the
    placeholder banner must be gone."""
    src = (
        REPO_ROOT / "pages" / "111_credit_live.py"
    ).read_text()
    assert "audit_log_records" in src, (
        "page 111 must reference audit_log_records composer"
    )
    assert (
        "Credit decision audit trail composer ships in a "
        not in src
    ), (
        "v10.300 placeholder banner still in page 111 — "
        "should be removed in v10.305"
    )


def test_page_112_uses_audit_log_composer():
    """Compliance cockpit tab 7 must use audit_log_records and
    the placeholder banner must be gone."""
    src = (
        REPO_ROOT / "pages" / "112_compliance_live.py"
    ).read_text()
    assert "audit_log_records" in src, (
        "page 112 must reference audit_log_records composer"
    )
    assert (
        "Compliance decision audit trail composer ships in"
        not in src
    ), (
        "v10.301 placeholder banner still in page 112 — "
        "should be removed in v10.305"
    )


# ============================================================
# Section 7 — HTTP endpoint
# ============================================================

def test_api_cockpit_audit_log_endpoint_registered():
    """/api/cockpit/audit/log must be in api_cockpit.py and
    documented in the module docstring."""
    src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()
    assert "/audit/log" in src, (
        "api_cockpit.py missing /audit/log endpoint"
    )
    # Docstring documentation
    docstring_end = src.find("\"\"\"", 100)
    docstring = src[:docstring_end + 3]
    assert "/api/cockpit/audit/log" in docstring


# ============================================================
# Section 8 — Audit gate G196
# ============================================================

def test_g196_gate_exists_and_passes():
    from scripts.audit import GATES
    g196 = None
    for gid, fn in GATES:
        if gid == "G196":
            g196 = fn()
            break
    assert g196 is not None, "G196 not registered"
    assert g196["passed"], (
        f"G196 failed. {g196.get('summary', '')}. "
        f"Violations: {g196.get('violations', [])[:5]}"
    )


# ============================================================
# Section 9 — JSON-serialisability
# ============================================================

def test_audit_log_records_json_serialisable(tmp_data_dir):
    from utils.cockpit_read import audit_log_records

    records = [
        {"ts": "1", "user": "a", "action": "x"},
    ]
    (tmp_data_dir / "audit_log.json").write_text(
        json.dumps(records))
    result = audit_log_records(data_dir=tmp_data_dir)
    re_serialised = json.dumps(result)
    assert json.loads(re_serialised) == result
