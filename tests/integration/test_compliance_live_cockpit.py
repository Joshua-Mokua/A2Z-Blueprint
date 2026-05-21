"""
tests/integration/test_compliance_live_cockpit.py
================================================================================
v10.301 — Compliance live cockpit integration tests, written
BEFORE the cockpit page per Kaizen TDD.

Compliance is the FOURTH live cockpit arc. Pattern:
record-registry (CIMS-style), not compute+JSON (Treasury/Credit).
Compliance work is "counts of open registry entries" across
KYC cases, AML alerts, sanctions screening hits, and regulatory
filings — exactly the CIMS shape (which composed across capture
sessions, classification requests, STP runs, exception cases,
SLA obligations, audit history).

Test sections:
  1. compliance_open_work composer contract (documented keys)
  2. Real production data shape checks
  3. Aggregator correctness (status filters, risk-level
     counts, overdue regulatory returns)
  4. Read-only guarantee
  5. Edge cases (missing files, malformed JSON, legacy rows)
  6. Performance smoke (1000+ records in <1s)
  7. Page 112 manifest + discipline
  8. SAR / sanctions hit invariants (regulatory critical)
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
    d = tempfile.mkdtemp(prefix="compliance_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ============================================================
# Section 1 — compliance_open_work composer contract
# ============================================================

def test_compliance_open_work_returns_documented_keys(
    tmp_data_dir,
):
    """All documented keys must be returned, even on empty
    data dir. Cockpit headlines depend on every key being
    present."""
    from utils.cockpit_read import compliance_open_work

    snap = compliance_open_work(data_dir=tmp_data_dir)
    required = [
        "compliance_cases_total",
        "compliance_cases_open",
        "compliance_cases_by_risk",
        "aml_alerts_total",
        "aml_alerts_open",
        "aml_alerts_high_risk",
        "sanctions_screening_total",
        "sanctions_hits_pending_review",
        "regulatory_returns_total",
        "regulatory_returns_overdue",
        "regulatory_returns_on_time_pct",
        "as_at",
    ]
    for k in required:
        assert k in snap, (
            f"compliance_open_work must always return `{k}` — "
            f"cockpit headline depends on it"
        )


def test_compliance_open_work_returns_pure_dict(tmp_data_dir):
    from utils.cockpit_read import compliance_open_work
    snap = compliance_open_work(data_dir=tmp_data_dir)
    assert isinstance(snap, dict)


def test_compliance_open_work_handles_missing_files(
    tmp_data_dir,
):
    """No data → all zeros, no crash. The cockpit can run
    on a fresh deploy."""
    from utils.cockpit_read import compliance_open_work
    snap = compliance_open_work(data_dir=tmp_data_dir)
    assert snap["compliance_cases_total"] == 0
    assert snap["aml_alerts_total"] == 0
    assert snap["sanctions_screening_total"] == 0
    assert snap["regulatory_returns_total"] == 0


# ============================================================
# Section 2 — Real production data shape
# ============================================================

def test_real_compliance_cases_json_contract():
    """The real compliance_cases.json must have the fields the
    cockpit reads (status, risk_level, flag_type). If
    production data has drifted, fail loudly."""
    path = REPO_ROOT / "data" / "compliance_cases.json"
    if not path.exists():
        pytest.skip("compliance_cases.json not present")
    rec = json.loads(path.read_text())
    assert isinstance(rec, list) and len(rec) > 0
    for f in ("status", "risk_level", "flag_type"):
        assert f in rec[0], (
            f"compliance_cases record missing `{f}`"
        )


def test_real_aml_alerts_json_contract():
    path = REPO_ROOT / "data" / "aml_alerts.json"
    if not path.exists():
        pytest.skip("aml_alerts.json not present")
    rec = json.loads(path.read_text())
    assert isinstance(rec, list) and len(rec) > 0
    for f in ("status", "risk_level", "rule_triggered"):
        assert f in rec[0], (
            f"aml_alerts record missing `{f}`"
        )


def test_real_sanctions_register_json_contract():
    path = REPO_ROOT / "data" / "sanctions_register.json"
    if not path.exists():
        pytest.skip("sanctions_register.json not present")
    rec = json.loads(path.read_text())
    assert isinstance(rec, list) and len(rec) > 0
    for f in ("status", "match_score", "list_matched"):
        assert f in rec[0], (
            f"sanctions_register record missing `{f}`"
        )


# ============================================================
# Section 3 — Aggregator correctness
# ============================================================

def test_compliance_cases_open_excludes_closed(tmp_data_dir):
    """Cases with status 'closed' / 'resolved' / 'cleared'
    must NOT count toward compliance_cases_open. Operators
    track this to size daily workload."""
    from utils.cockpit_read import compliance_open_work

    cases = [
        {"id": "C1", "status": "open", "risk_level": "high"},
        {"id": "C2", "status": "investigating",
         "risk_level": "medium"},
        {"id": "C3", "status": "closed", "risk_level": "low"},
        {"id": "C4", "status": "resolved", "risk_level": "high"},
        {"id": "C5", "status": "cleared", "risk_level": "low"},
    ]
    (tmp_data_dir / "compliance_cases.json").write_text(
        json.dumps(cases))

    snap = compliance_open_work(data_dir=tmp_data_dir)
    assert snap["compliance_cases_total"] == 5
    # Only C1 and C2 are open
    assert snap["compliance_cases_open"] == 2


def test_compliance_cases_by_risk_groups_correctly(
    tmp_data_dir,
):
    from utils.cockpit_read import compliance_open_work

    cases = [
        {"id": "C1", "status": "open", "risk_level": "high"},
        {"id": "C2", "status": "open", "risk_level": "high"},
        {"id": "C3", "status": "open", "risk_level": "medium"},
        {"id": "C4", "status": "open", "risk_level": "low"},
    ]
    (tmp_data_dir / "compliance_cases.json").write_text(
        json.dumps(cases))

    snap = compliance_open_work(data_dir=tmp_data_dir)
    by_risk = snap["compliance_cases_by_risk"]
    assert by_risk.get("high") == 2
    assert by_risk.get("medium") == 1
    assert by_risk.get("low") == 1


def test_aml_alerts_high_risk_counted(tmp_data_dir):
    """High-risk AML alerts are escalation candidates. Cockpit
    surfaces the count as a triage signal."""
    from utils.cockpit_read import compliance_open_work

    alerts = [
        {"id": "A1", "status": "open", "risk_level": "HIGH"},
        {"id": "A2", "status": "open", "risk_level": "high"},
        {"id": "A3", "status": "open", "risk_level": "medium"},
        {"id": "A4", "status": "closed", "risk_level": "high"},
    ]
    (tmp_data_dir / "aml_alerts.json").write_text(
        json.dumps(alerts))

    snap = compliance_open_work(data_dir=tmp_data_dir)
    # Case-insensitive: 2 open + high-risk
    assert snap["aml_alerts_high_risk"] == 2


def test_sanctions_hits_pending_review_counted(tmp_data_dir):
    """Sanctions matches that haven't been cleared yet are the
    most regulatorily sensitive items — cockpit must surface
    them clearly."""
    from utils.cockpit_read import compliance_open_work

    screenings = [
        {"id": "S1", "status": "pending", "match_score": 95},
        {"id": "S2", "status": "review", "match_score": 80},
        {"id": "S3", "status": "cleared", "match_score": 60},
        {"id": "S4", "status": "confirmed", "match_score": 100},
    ]
    (tmp_data_dir / "sanctions_register.json").write_text(
        json.dumps(screenings))

    snap = compliance_open_work(data_dir=tmp_data_dir)
    # Pending + review = 2 awaiting human action; cleared and
    # confirmed are terminal.
    assert snap["sanctions_hits_pending_review"] == 2


def test_regulatory_returns_overdue_detected(tmp_data_dir):
    """Returns past due_date with no filed_date are overdue.
    Regulators care — this is what CBK quarterly returns
    tracking is for."""
    from utils.cockpit_read import compliance_open_work

    returns = [
        # Overdue: past due_date and not filed
        {"id": "R1", "due_date": "2025-01-31",
         "filed_date": None, "status": "pending"},
        # On-time: filed before due_date
        {"id": "R2", "due_date": "2025-03-31",
         "filed_date": "2025-03-25", "status": "filed",
         "on_time": True},
        # Filed late but filed
        {"id": "R3", "due_date": "2025-02-28",
         "filed_date": "2025-03-05", "status": "filed",
         "on_time": False},
        # Future filing
        {"id": "R4", "due_date": "2099-12-31",
         "filed_date": None, "status": "pending"},
    ]
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(returns))

    snap = compliance_open_work(data_dir=tmp_data_dir)
    assert snap["regulatory_returns_total"] == 4
    # R1 overdue (past 2025-01-31, not filed); R4 not yet due
    assert snap["regulatory_returns_overdue"] == 1


def test_regulatory_on_time_pct_correctly_calculated(
    tmp_data_dir,
):
    """on_time_pct = filed-on-time / filed-total × 100.
    A bank with 50% on-time filing is in trouble; that's the
    KPI."""
    from utils.cockpit_read import compliance_open_work

    returns = [
        {"id": "R1", "status": "filed", "on_time": True},
        {"id": "R2", "status": "filed", "on_time": True},
        {"id": "R3", "status": "filed", "on_time": False},
        {"id": "R4", "status": "filed", "on_time": False},
        # Pending returns don't count toward on-time math
        {"id": "R5", "status": "pending", "on_time": None},
    ]
    (tmp_data_dir / "compliance.json").write_text(
        json.dumps(returns))

    snap = compliance_open_work(data_dir=tmp_data_dir)
    # 2 of 4 filed on time = 50.0%
    assert snap["regulatory_returns_on_time_pct"] == 50.0


# ============================================================
# Section 4 — Read-only guarantee
# ============================================================

def test_compliance_open_work_does_not_mutate_data(
    tmp_data_dir,
):
    """Regulatory invariant: cockpit must never alter
    compliance state. Verified by mtime + content."""
    from utils.cockpit_read import compliance_open_work

    cases = [
        {"id": "X", "status": "open", "risk_level": "high"},
    ]
    path = tmp_data_dir / "compliance_cases.json"
    path.write_text(json.dumps(cases))
    original = path.read_text()
    original_mtime = path.stat().st_mtime

    for _ in range(5):
        compliance_open_work(data_dir=tmp_data_dir)

    assert path.read_text() == original
    assert path.stat().st_mtime == original_mtime


# ============================================================
# Section 5 — Edge cases
# ============================================================

def test_compliance_open_work_tolerates_malformed_json(
    tmp_data_dir,
):
    from utils.cockpit_read import compliance_open_work
    (tmp_data_dir / "compliance_cases.json").write_text(
        "{ not valid json"
    )
    snap = compliance_open_work(data_dir=tmp_data_dir)
    assert snap["compliance_cases_total"] == 0


def test_compliance_open_work_tolerates_missing_fields(
    tmp_data_dir,
):
    """Some legacy compliance records lack status or
    risk_level. Cockpit counts them in totals but skips them
    in status/risk aggregates rather than crashing."""
    from utils.cockpit_read import compliance_open_work

    cases = [
        {"id": "L1"},  # no status, no risk
        {"id": "L2", "status": "open"},  # no risk
        {"id": "L3", "status": "open", "risk_level": "high"},
    ]
    (tmp_data_dir / "compliance_cases.json").write_text(
        json.dumps(cases))

    snap = compliance_open_work(data_dir=tmp_data_dir)
    assert snap["compliance_cases_total"] == 3
    # L2 and L3 have status open; L1 has no status (unknown)
    assert snap["compliance_cases_open"] == 2


# ============================================================
# Section 6 — Performance smoke
# ============================================================

def test_compliance_open_work_handles_large_dataset(
    tmp_data_dir,
):
    """1000 records across 4 registries must aggregate in <1s
    so the cockpit's 10s TTL refresh stays smooth."""
    import time
    from utils.cockpit_read import compliance_open_work

    cases = [
        {"id": f"C{i}", "status": "open" if i % 2 == 0
         else "closed",
         "risk_level": ["high", "medium", "low"][i % 3]}
        for i in range(1000)
    ]
    alerts = [
        {"id": f"A{i}", "status": "open", "risk_level": "HIGH"}
        for i in range(500)
    ]
    (tmp_data_dir / "compliance_cases.json").write_text(
        json.dumps(cases))
    (tmp_data_dir / "aml_alerts.json").write_text(
        json.dumps(alerts))

    start = time.time()
    snap = compliance_open_work(data_dir=tmp_data_dir)
    elapsed = time.time() - start

    assert snap["compliance_cases_total"] == 1000
    assert elapsed < 1.0, (
        f"compliance_open_work took {elapsed:.2f}s for 1500 "
        f"records — too slow for live cockpit refresh"
    )


# ============================================================
# Section 7 — Page 112 manifest + discipline
# ============================================================

def test_page_112_exists():
    path = REPO_ROOT / "pages" / "112_compliance_live.py"
    assert path.exists(), (
        "pages/112_compliance_live.py is missing"
    )


def test_page_112_manifest_entry():
    manifest_path = REPO_ROOT / "pages" / "_manifest.json"
    m = json.loads(manifest_path.read_text())
    entry = m["pages"].get("112_compliance_live.py")
    assert entry, "112_compliance_live.py missing from manifest"
    assert entry["module_path"].endswith("compliance_live"), (
        f"module_path must end in 'compliance_live'; got "
        f"{entry['module_path']!r}"
    )
    assert entry["description"], "description required"


def test_page_112_uses_hard_require_access():
    path = REPO_ROOT / "pages" / "112_compliance_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    bad = (
        "try:\n"
        "    from pages._access import require_access\n"
    )
    assert bad not in src


def test_page_112_emits_audit_log():
    path = REPO_ROOT / "pages" / "112_compliance_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    assert "audit_log(" in src


def test_page_112_uses_ttl_cache():
    path = REPO_ROOT / "pages" / "112_compliance_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    assert "@st.cache_data(ttl=" in src


def test_page_112_no_direct_filesystem_reads():
    import re
    path = REPO_ROOT / "pages" / "112_compliance_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    for pat in (
        r'Path\(["\']data/', r'\.read_text\(\)',
        r'open\(["\']data/', r'json\.loads\([^)]*\.read',
    ):
        matches = list(re.finditer(pat, src))
        assert not matches, (
            f"112_compliance_live.py contains direct "
            f"filesystem read pattern {pat!r}; use cockpit_read"
        )


# ============================================================
# Section 8 — Idempotency + serialisability
# ============================================================

def test_compliance_open_work_idempotent(tmp_data_dir):
    from utils.cockpit_read import compliance_open_work

    cases = [
        {"id": "C", "status": "open", "risk_level": "high"},
    ]
    (tmp_data_dir / "compliance_cases.json").write_text(
        json.dumps(cases))

    s1 = compliance_open_work(data_dir=tmp_data_dir)
    s2 = compliance_open_work(data_dir=tmp_data_dir)

    for k in set(s1) - {"as_at"}:
        assert s1[k] == s2[k]


def test_compliance_open_work_json_serialisable(tmp_data_dir):
    from utils.cockpit_read import compliance_open_work

    cases = [
        {"id": "C", "status": "open", "risk_level": "high"},
    ]
    (tmp_data_dir / "compliance_cases.json").write_text(
        json.dumps(cases))

    snap = compliance_open_work(data_dir=tmp_data_dir)
    re_serialised = json.dumps(snap)
    assert json.loads(re_serialised) == snap
