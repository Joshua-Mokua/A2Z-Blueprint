"""
tests/integration/test_cims_live_cockpit.py
================================================================================
End-to-end integration tests for the Phase 3 CIMS live cockpit
(v10.295). Validates that cockpit_read composers actually join data
across the 15 CIMS engines correctly, and that the cockpit pages
render their data the same way the engines wrote it.

This test would catch the field-name mismatches that surfaced
during v10.295 build (e.g. cockpit reading `channel` but engine
writing `originating_channel`) and the CIMS instruction-type
vocabulary inconsistencies across engines.

Run: pytest tests/integration/test_cims_live_cockpit.py -v
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def tmp_data_dir():
    """Isolated data directory so the test never touches real data."""
    d = tempfile.mkdtemp(prefix="cims_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


def _path_for(tmp_dir: Path, filename: str) -> Path:
    return tmp_dir / filename


# ============================================================
# Capture engine field contract
# ============================================================

def test_capture_engine_writes_originating_channel_field(tmp_data_dir):
    """The capture engine must store records under
    `originating_channel`, NOT `channel`. The cockpit reads
    `originating_channel`; if this contract breaks, the cockpit
    will silently show '?' for channel everywhere.
    """
    from utils.cims_omnichannel_capture import OmnichannelCaptureEngine

    cap = OmnichannelCaptureEngine(
        sessions_path=_path_for(tmp_data_dir, "cims_capture_sessions.json"),
        touches_path=_path_for(tmp_data_dir, "cims_channel_touches.json"),
        handoffs_path=_path_for(tmp_data_dir, "cims_capture_handoffs.json"),
    )
    r = cap.register_capture_session(
        {"session_id": "T-001",
          "originating_channel": "MOBILE_APP",
          "instruction_type": "COMPLAINT",
          "customer_id": "C-001"},
        actor="test", reason="contract test",
    )
    assert r["registered"], f"Registration failed: {r}"

    # Read it back via the cockpit's read helper
    from utils.cockpit_read import load_records

    records = load_records(
        tmp_data_dir / "cims_capture_sessions.json",
        "cims_capture_sessions", ("session_id",),
    )
    assert len(records) == 1
    rec = records[0]
    # The contract: cockpit reads originating_channel
    assert "originating_channel" in rec, (
        "Capture engine must write `originating_channel`. If this "
        "fails, the cockpit's channel column will be empty."
    )
    assert rec["originating_channel"] == "MOBILE_APP"


# ============================================================
# Instruction trace cross-engine composition
# ============================================================

def test_instruction_trace_joins_capture_and_history(tmp_data_dir):
    """Given a session and a history record sharing the same
    linked_session_id, `cims_instruction_trace` must surface both.
    """
    from utils.cims_omnichannel_capture import OmnichannelCaptureEngine
    from utils.cims_audit_ready_history import AuditReadyHistoryEngine
    from utils.cockpit_read import cims_instruction_trace

    cap = OmnichannelCaptureEngine(
        sessions_path=_path_for(tmp_data_dir, "cims_capture_sessions.json"),
        touches_path=_path_for(tmp_data_dir, "cims_channel_touches.json"),
        handoffs_path=_path_for(tmp_data_dir, "cims_capture_handoffs.json"),
    )
    cap.register_capture_session(
        {"session_id": "T-002",
          "originating_channel": "BRANCH",
          "instruction_type": "FUNDS_TRANSFER",
          "customer_id": "C-002"},
        actor="test", reason="trace test",
    )

    hist = AuditReadyHistoryEngine(
        history_path=_path_for(tmp_data_dir, "cims_audit_history.json"),
        corrections_path=_path_for(
            tmp_data_dir, "cims_history_corrections.json"),
        examiner_queries_path=_path_for(
            tmp_data_dir, "cims_examiner_queries.json"),
        compliance_reviews_path=_path_for(
            tmp_data_dir, "cims_compliance_reviews.json"),
    )
    hist.register_history_record(
        {"record_id": "H-001", "kind": "INSTRUCTION_LIFECYCLE",
          "linked_session_id": "T-002",
          "subject_id": "T-002",
          "narrative": "Session received at branch teller"},
        actor="test", reason="trace test",
    )

    trace = cims_instruction_trace("T-002", data_dir=tmp_data_dir)

    assert trace["capture"] is not None
    assert trace["capture"]["session_id"] == "T-002"
    assert trace["capture"]["originating_channel"] == "BRANCH"
    assert len(trace["history"]) == 1
    assert trace["history"][0]["record_id"] == "H-001"


def test_instruction_trace_returns_empty_for_unknown_session(tmp_data_dir):
    """An unknown session ID must return a well-formed empty trace,
    not crash. Cockpit users will type IDs that don't exist."""
    from utils.cockpit_read import cims_instruction_trace

    trace = cims_instruction_trace(
        "NEVER-CREATED", data_dir=tmp_data_dir,
    )
    assert trace["capture"] is None
    assert trace["classification_requests"] == []
    assert trace["stp_requests"] == []
    assert trace["exceptions"] == []
    assert trace["sla_obligations"] == []
    assert trace["history"] == []


# ============================================================
# Open work composer
# ============================================================

def test_open_work_snapshot_counts_open_sessions(tmp_data_dir):
    """The open-work snapshot must count sessions that are NOT
    in a terminal state (COMPLETED/ABANDONED/CANCELLED).
    """
    from utils.cims_omnichannel_capture import OmnichannelCaptureEngine
    from utils.cockpit_read import cims_open_work

    cap = OmnichannelCaptureEngine(
        sessions_path=_path_for(tmp_data_dir, "cims_capture_sessions.json"),
        touches_path=_path_for(tmp_data_dir, "cims_channel_touches.json"),
        handoffs_path=_path_for(tmp_data_dir, "cims_capture_handoffs.json"),
    )
    # Three sessions
    for i, ch in enumerate(["MOBILE_APP", "BRANCH", "USSD"], 1):
        cap.register_capture_session(
            {"session_id": f"T-10{i}",
              "originating_channel": ch,
              "instruction_type": "GENERAL_INQUIRY",
              "customer_id": f"C-10{i}"},
            actor="test", reason="open work test",
        )

    snap = cims_open_work(data_dir=tmp_data_dir)
    # All three are in INITIATED state, which is not terminal
    assert snap["open_capture_sessions"] == 3
    assert len(snap["recent_open_sessions"]) == 3


def test_open_work_snapshot_excludes_terminal_states(tmp_data_dir):
    """Sessions in COMPLETED/ABANDONED/CANCELLED must NOT appear
    in open work counts.
    """
    from utils.cims_omnichannel_capture import OmnichannelCaptureEngine
    from utils.cockpit_read import cims_open_work

    cap = OmnichannelCaptureEngine(
        sessions_path=_path_for(tmp_data_dir, "cims_capture_sessions.json"),
        touches_path=_path_for(tmp_data_dir, "cims_channel_touches.json"),
        handoffs_path=_path_for(tmp_data_dir, "cims_capture_handoffs.json"),
    )
    cap.register_capture_session(
        {"session_id": "T-201",
          "originating_channel": "MOBILE_APP",
          "instruction_type": "GENERAL_INQUIRY",
          "customer_id": "C-201"},
        actor="test", reason="completed test",
    )
    # Walk it through to COMPLETED — terminal
    # IN_PROGRESS first, then COMPLETED (state machine rules)
    cap.transition_capture_state(
        "T-201", "IN_PROGRESS",
        actor="test", reason="processing",
    )
    cap.transition_capture_state(
        "T-201", "COMPLETED",
        actor="test", reason="done",
    )

    snap = cims_open_work(data_dir=tmp_data_dir)
    assert snap["open_capture_sessions"] == 0, (
        "COMPLETED session should not count as open work"
    )


# ============================================================
# Filter and sort behaviour
# ============================================================

def test_filter_records_by_date_window():
    """filter_records date filtering must be inclusive of the
    `since_iso` boundary and exclusive of records before it.
    """
    from utils.cockpit_read import filter_records

    now = datetime.utcnow()
    records = [
        {"id": "a",
          "registered_at": (now - timedelta(days=10)).isoformat()},
        {"id": "b",
          "registered_at": (now - timedelta(days=5)).isoformat()},
        {"id": "c",
          "registered_at": (now - timedelta(days=1)).isoformat()},
    ]
    cutoff = (now - timedelta(days=7)).isoformat()
    filtered = filter_records(records, since_iso=cutoff)
    ids = sorted(r["id"] for r in filtered)
    assert ids == ["b", "c"], (
        f"Expected only b and c (within last 7 days), got {ids}"
    )


def test_filter_records_tolerates_missing_date_field():
    """When the date_field is missing, the record must be EXCLUDED
    if a date filter is applied (we can't compare missing dates).
    But records must NOT be excluded if no date filter is applied.
    """
    from utils.cockpit_read import filter_records

    records = [
        {"id": "a"},  # no date field
        {"id": "b", "registered_at": "2026-01-01T00:00:00"},
    ]

    # No filter — both pass
    assert len(filter_records(records)) == 2

    # Date filter applied — only b qualifies
    filtered = filter_records(records, since_iso="2025-01-01T00:00:00")
    assert len(filtered) == 1
    assert filtered[0]["id"] == "b"


def test_count_by_handles_missing_field():
    """count_by must put records with missing field under the
    empty-string key, not crash.
    """
    from utils.cockpit_read import count_by

    records = [
        {"channel": "A"},
        {"channel": "A"},
        {"channel": "B"},
        {},  # missing
    ]
    counts = count_by(records, "channel")
    assert counts["A"] == 2
    assert counts["B"] == 1
    assert counts[""] == 1


# ============================================================
# Manifest contract
# ============================================================

def test_page_109_manifest_entry_exists():
    """Page 109 must be registered with the right module_path."""
    import json

    manifest_path = REPO_ROOT / "pages" / "_manifest.json"
    m = json.loads(manifest_path.read_text())
    entry = m["pages"].get("109_cims_live.py")
    assert entry is not None, "109_cims_live.py missing from manifest"
    assert entry["module_path"] == "operations.cims_live"
    assert entry["department_primary"] == "operations"
    assert entry["description"], "description must be non-empty"


# ============================================================
# require_access discipline
# ============================================================

def test_cims_pages_use_hard_require_access():
    """Phase 3 standing rule: pages must fail loud on missing
    access. No try/except swallow around require_access.
    """
    cims_pages = [
        "105_cims_capture.py", "106_cims_process.py",
        "107_cims_compliance.py", "108_cims_closure.py",
        "109_cims_live.py",
    ]
    bad_pattern = (
        "try:\n"
        "    from pages._access import require_access\n"
    )
    for pname in cims_pages:
        path = REPO_ROOT / "pages" / pname
        if not path.exists():
            continue
        src = path.read_text()
        assert bad_pattern not in src, (
            f"{pname} uses silent try/except around require_access; "
            f"Phase 3 rule requires hard import"
        )


# ============================================================
# Cockpit read API surface
# ============================================================

def test_cockpit_read_exposes_documented_api():
    """The G186 gate enforces this; the test makes the failure
    mode obvious when developers refactor cockpit_read.
    """
    import utils.cockpit_read as cr

    required_api = [
        "load_records", "filter_records", "sort_records",
        "group_by", "count_by", "find_by_id", "latest_n",
        "cims_instruction_trace", "cims_open_work",
    ]
    for name in required_api:
        assert hasattr(cr, name), (
            f"utils.cockpit_read.{name} is documented public API "
            f"and missing — will break the live cockpit"
        )
