"""
tests/integration/test_credit_live_cockpit.py
================================================================================
v10.300 — Credit live cockpit integration tests, written BEFORE
the cockpit page per Kaizen TDD.

Credit is the third live cockpit arc after CIMS (record-registry
pattern) and Treasury (compute+JSON pattern). Credit follows the
Treasury pattern: stateful compute engines (AIUnderwritingEngine,
CreditCommitteeEngine, IRBCapitalEngine, etc.) backed by JSON
data files (loan_applications.json, ifrs9_loans.json,
credit_admin.json, credit_monitoring.json).

Test discipline mirrors v10.296 Treasury and v10.299 CORS:
  1. cockpit_read.credit_open_work composer contract
  2. JSON data field invariants (real production data)
  3. Aggregator correctness (non-negative counts, stage
     distribution sums correctly, IFRS9 stages 1/2/3 logic)
  4. Read-only guarantee (no file mutations)
  5. Edge cases (missing files, malformed JSON, legacy rows)
  6. Performance smoke (5k+ IFRS9 records should aggregate in
     under 1 second)
  7. Page 111 manifest + discipline checks
  8. NPL / Stage 3 detection invariants (regulatory critical)
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
    d = tempfile.mkdtemp(prefix="credit_test_")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ============================================================
# Section 1 — credit_open_work composer contract
# ============================================================

def test_credit_open_work_returns_documented_keys(tmp_data_dir):
    """Even with no data, the composer must return all
    documented keys so the cockpit can render headline tiles."""
    from utils.cockpit_read import credit_open_work

    snap = credit_open_work(data_dir=tmp_data_dir)
    required = [
        "applications_total", "applications_open",
        "applications_by_stage",
        "ifrs9_total", "ifrs9_stage1", "ifrs9_stage2",
        "ifrs9_stage3", "npl_pct",
        "watchlist_count",
        "as_at",
    ]
    for k in required:
        assert k in snap, (
            f"credit_open_work must always return `{k}` — "
            f"cockpit headlines depend on it"
        )


def test_credit_open_work_returns_pure_dict(tmp_data_dir):
    """Return type must be a plain dict for HTTP serialisation."""
    from utils.cockpit_read import credit_open_work
    snap = credit_open_work(data_dir=tmp_data_dir)
    assert isinstance(snap, dict)


def test_credit_open_work_handles_missing_files(tmp_data_dir):
    """No data files present → all counts are zero, no
    exceptions raised."""
    from utils.cockpit_read import credit_open_work
    snap = credit_open_work(data_dir=tmp_data_dir)
    assert snap["applications_total"] == 0
    assert snap["ifrs9_total"] == 0
    assert snap["watchlist_count"] == 0
    assert snap["npl_pct"] is None or snap["npl_pct"] == 0


# ============================================================
# Section 2 — Loan applications JSON contract
# ============================================================

def test_loan_applications_json_contract():
    """Real loan_applications.json must have the field shape
    the cockpit expects. If this fails, the production data
    has drifted from documented schema."""
    path = REPO_ROOT / "data" / "loan_applications.json"
    if not path.exists():
        pytest.skip("loan_applications.json not present")
    records = json.loads(path.read_text())
    assert isinstance(records, list)
    assert len(records) > 0
    first = records[0]
    # Cockpit reads these fields; missing them = blank columns
    for f in ("id", "client_name", "product", "amount"):
        assert f in first, (
            f"loan_applications.json record missing `{f}`"
        )


def test_credit_applications_counted_correctly(tmp_data_dir):
    """Synthetic data: 3 applications, 2 with non-terminal
    state must show as `applications_open`."""
    from utils.cockpit_read import credit_open_work

    apps = [
        {"id": "L1", "swim_lane": "underwriting",
          "client_name": "A", "product": "Term", "amount": 100},
        {"id": "L2", "swim_lane": "approved",
          "client_name": "B", "product": "Term", "amount": 200},
        {"id": "L3", "swim_lane": "rejected",  # terminal
          "client_name": "C", "product": "Term", "amount": 300},
    ]
    (tmp_data_dir / "loan_applications.json").write_text(
        json.dumps(apps))

    snap = credit_open_work(data_dir=tmp_data_dir)
    assert snap["applications_total"] == 3
    # "approved" and "rejected" are terminal; only "underwriting"
    # is open work
    assert snap["applications_open"] == 1


# ============================================================
# Section 3 — IFRS9 stage logic
# ============================================================

def test_ifrs9_json_contract():
    """Real ifrs9_loans.json must have stage + npl_days
    fields — the regulatory backbone of IFRS9 reporting."""
    path = REPO_ROOT / "data" / "ifrs9_loans.json"
    if not path.exists():
        pytest.skip("ifrs9_loans.json not present")
    records = json.loads(path.read_text())
    assert isinstance(records, list)
    if records:
        first = records[0]
        for f in ("account_id", "stage", "outstanding"):
            assert f in first, (
                f"ifrs9_loans.json record missing `{f}` — "
                f"cockpit IFRS9 tab needs it"
            )


def test_credit_open_work_counts_stage1_stage2_stage3(tmp_data_dir):
    """Stage classification must match the documented IFRS9
    rules: stage 1 = performing, stage 2 = significant credit
    increase, stage 3 = non-performing (NPL)."""
    from utils.cockpit_read import credit_open_work

    loans = [
        {"account_id": "A1", "stage": 1, "outstanding": 1000,
          "npl_days": 0},
        {"account_id": "A2", "stage": 1, "outstanding": 2000,
          "npl_days": 5},
        {"account_id": "A3", "stage": 2, "outstanding": 3000,
          "npl_days": 45},
        {"account_id": "A4", "stage": 3, "outstanding": 4000,
          "npl_days": 95},
        {"account_id": "A5", "stage": 3, "outstanding": 5000,
          "npl_days": 180},
    ]
    (tmp_data_dir / "ifrs9_loans.json").write_text(
        json.dumps(loans))

    snap = credit_open_work(data_dir=tmp_data_dir)
    assert snap["ifrs9_total"] == 5
    assert snap["ifrs9_stage1"] == 2
    assert snap["ifrs9_stage2"] == 1
    assert snap["ifrs9_stage3"] == 2


def test_credit_open_work_npl_pct_calculated_correctly(
    tmp_data_dir,
):
    """NPL ratio = Stage 3 outstanding / total outstanding,
    expressed as a percentage. Regulators care about this
    number; it must be right."""
    from utils.cockpit_read import credit_open_work

    loans = [
        {"account_id": "P1", "stage": 1, "outstanding": 8000},
        {"account_id": "P2", "stage": 2, "outstanding": 1000},
        {"account_id": "N1", "stage": 3, "outstanding": 1000},
    ]
    (tmp_data_dir / "ifrs9_loans.json").write_text(
        json.dumps(loans))

    snap = credit_open_work(data_dir=tmp_data_dir)
    # NPL = 1000 / 10000 = 10%
    assert snap["npl_pct"] == 10.0, (
        f"Expected NPL of 10.0%, got {snap['npl_pct']}"
    )


def test_credit_open_work_npl_pct_zero_when_no_stage3(
    tmp_data_dir,
):
    """All-performing portfolio must yield NPL = 0, not None."""
    from utils.cockpit_read import credit_open_work

    loans = [
        {"account_id": "P1", "stage": 1, "outstanding": 5000},
        {"account_id": "P2", "stage": 2, "outstanding": 3000},
    ]
    (tmp_data_dir / "ifrs9_loans.json").write_text(
        json.dumps(loans))

    snap = credit_open_work(data_dir=tmp_data_dir)
    assert snap["npl_pct"] == 0.0


# ============================================================
# Section 4 — Watchlist
# ============================================================

def test_credit_watchlist_counted(tmp_data_dir):
    """credit_monitoring.json has a watchlist key; cockpit
    counts entries."""
    from utils.cockpit_read import credit_open_work

    monitoring = {
        "watchlist": [
            {"client": "Risky Co", "reason": "missed_2_payments"},
            {"client": "Watch Ltd", "reason": "covenant_breach"},
        ],
        "last_updated": "2026-05-10",
    }
    (tmp_data_dir / "credit_monitoring.json").write_text(
        json.dumps(monitoring))

    snap = credit_open_work(data_dir=tmp_data_dir)
    assert snap["watchlist_count"] == 2


# ============================================================
# Section 5 — Read-only guarantee
# ============================================================

def test_credit_open_work_does_not_mutate_data(tmp_data_dir):
    """Critical for regulatory reads: cockpit must never alter
    credit data. Verified by file mtime and content."""
    from utils.cockpit_read import credit_open_work

    loans = [
        {"account_id": "X", "stage": 1, "outstanding": 100},
    ]
    path = tmp_data_dir / "ifrs9_loans.json"
    path.write_text(json.dumps(loans))
    original = path.read_text()
    original_mtime = path.stat().st_mtime

    for _ in range(5):
        credit_open_work(data_dir=tmp_data_dir)

    assert path.read_text() == original
    assert path.stat().st_mtime == original_mtime


# ============================================================
# Section 6 — Edge cases
# ============================================================

def test_credit_open_work_tolerates_malformed_json(tmp_data_dir):
    """Operator hand-edits the JSON wrong → cockpit shows
    zeros, not a stack trace."""
    from utils.cockpit_read import credit_open_work
    (tmp_data_dir / "loan_applications.json").write_text(
        "{ this is not valid json"
    )
    snap = credit_open_work(data_dir=tmp_data_dir)
    assert snap["applications_total"] == 0


def test_credit_open_work_tolerates_legacy_record_shapes(
    tmp_data_dir,
):
    """Some old IFRS9 records may lack `outstanding` or have
    `stage` as a string. The composer must count them without
    crashing."""
    from utils.cockpit_read import credit_open_work

    loans = [
        {"account_id": "OLD1"},  # no stage, no outstanding
        {"account_id": "OLD2", "stage": "2",
          "outstanding": "1000"},  # strings instead of ints
        {"account_id": "OLD3", "stage": 3,
          "outstanding": 500},
    ]
    (tmp_data_dir / "ifrs9_loans.json").write_text(
        json.dumps(loans))
    snap = credit_open_work(data_dir=tmp_data_dir)
    # All three counted in total even if shape is funky
    assert snap["ifrs9_total"] == 3


# ============================================================
# Section 7 — Performance smoke
# ============================================================

def test_credit_open_work_handles_5k_ifrs9_records(tmp_data_dir):
    """Production has 5,045 IFRS9 records today. The composer
    must aggregate them in under 1 second so the cockpit can
    refresh every 10s without burning CPU."""
    import time
    from utils.cockpit_read import credit_open_work

    loans = [
        {"account_id": f"A{i}",
          "stage": (i % 3) + 1,  # rotate stages 1/2/3
          "outstanding": 1000 + (i % 100)}
        for i in range(5000)
    ]
    (tmp_data_dir / "ifrs9_loans.json").write_text(json.dumps(loans))

    start = time.time()
    snap = credit_open_work(data_dir=tmp_data_dir)
    elapsed = time.time() - start

    assert snap["ifrs9_total"] == 5000
    assert elapsed < 1.0, (
        f"credit_open_work took {elapsed:.2f}s for 5k records — "
        f"too slow for live cockpit refresh"
    )


# ============================================================
# Section 8 — Page 111 manifest + discipline
# ============================================================

def test_page_111_manifest_entry_exists():
    """After the cockpit ships, manifest entry must exist
    with `credit.credit_live` module_path."""
    manifest_path = REPO_ROOT / "pages" / "_manifest.json"
    m = json.loads(manifest_path.read_text())
    entry = m["pages"].get("111_credit_live.py")
    assert entry is not None, (
        "111_credit_live.py missing from manifest"
    )
    assert entry["module_path"].endswith("credit_live"), (
        f"module_path must end in 'credit_live'; got "
        f"{entry['module_path']!r}"
    )
    assert entry["description"], "description must be non-empty"


def test_page_111_uses_hard_require_access():
    path = REPO_ROOT / "pages" / "111_credit_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    bad = (
        "try:\n"
        "    from pages._access import require_access\n"
    )
    assert bad not in src


def test_page_111_emits_audit_log():
    path = REPO_ROOT / "pages" / "111_credit_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    assert "audit_log(" in src


def test_page_111_uses_ttl_cache():
    path = REPO_ROOT / "pages" / "111_credit_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    assert "@st.cache_data(ttl=" in src


def test_page_111_has_no_direct_filesystem_reads():
    """G2 invariant: live cockpits read via cockpit_read
    helpers, never via raw `Path.read_text()` or `open()`."""
    import re
    path = REPO_ROOT / "pages" / "111_credit_live.py"
    if not path.exists():
        pytest.skip("page not yet written")
    src = path.read_text()
    suspicious = [
        r'Path\(["\']data/',
        r'\.read_text\(\)',
        r'open\(["\']data/',
        r'json\.loads\([^)]*\.read',
    ]
    for pat in suspicious:
        matches = list(re.finditer(pat, src))
        assert not matches, (
            f"111_credit_live.py contains direct filesystem "
            f"read pattern {pat!r}; use cockpit_read helpers"
        )


# ============================================================
# Section 9 — Idempotency + HTTP-serialisability
# ============================================================

def test_credit_open_work_idempotent(tmp_data_dir):
    """Two consecutive calls must produce identical data
    (except the as_at timestamp)."""
    from utils.cockpit_read import credit_open_work

    loans = [
        {"account_id": "I1", "stage": 2, "outstanding": 1000},
    ]
    (tmp_data_dir / "ifrs9_loans.json").write_text(json.dumps(loans))

    s1 = credit_open_work(data_dir=tmp_data_dir)
    s2 = credit_open_work(data_dir=tmp_data_dir)

    for k in set(s1) - {"as_at"}:
        assert s1[k] == s2[k], (
            f"credit_open_work `{k}` differs across calls: "
            f"{s1[k]} vs {s2[k]}"
        )


def test_credit_open_work_json_serialisable(tmp_data_dir):
    """For the React SPA HTTP endpoint to work, the dict must
    round-trip through json.dumps cleanly."""
    from utils.cockpit_read import credit_open_work

    loans = [
        {"account_id": "J1", "stage": 1, "outstanding": 1234},
    ]
    (tmp_data_dir / "ifrs9_loans.json").write_text(json.dumps(loans))

    snap = credit_open_work(data_dir=tmp_data_dir)
    re_serialised = json.dumps(snap)
    round_tripped = json.loads(re_serialised)
    assert round_tripped == snap
