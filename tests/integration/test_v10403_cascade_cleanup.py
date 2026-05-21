"""Integration tests for v10.403 — cascade cleanup batch.

Pure data cleanup per Joshua's deep-review findings:
  A1. Delete 10 EXEC-* synthetic chiefs
  A4. Add Admin to cascade exclusion
  A5. Clean canonical_change_log test entries
  D1. Retire stale v10.397 staff_code test
  B1-B4. Mark KPI library duplicates

12 tests across 4 sections.
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(name):
    return json.loads((REPO / "data" / name).read_text())


# ────────────────────────────────────────────────────────────────────
# Section 1 — Synthetic chiefs deletion (A1)
# ────────────────────────────────────────────────────────────────────

def test_v10403_exec_chiefs_deleted_from_users():
    """No EXEC-* users in users.json."""
    users = _load("users.json")
    exec_users = [un for un, u in users.items()
                 if isinstance(u, dict)
                 and str(u.get("staff_code", "")).startswith("EXEC-")]
    assert not exec_users, f"EXEC-* users still in users.json: {exec_users}"


def test_v10403_real_chiefs_preserved():
    """All 10 real chiefs (300002-300010 + 300178) still in users.json."""
    users = _load("users.json")
    real_chief_codes = {"300002", "300003", "300004", "300005", "300006",
                       "300007", "300008", "300009", "300010", "300178"}
    found = set()
    for un, u in users.items():
        if isinstance(u, dict):
            sc = str(u.get("staff_code", ""))
            if sc in real_chief_codes:
                found.add(sc)
    missing = real_chief_codes - found
    assert not missing, f"Real chiefs missing: {missing}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Regenerator exclusion (A4 + E-C5)
# ────────────────────────────────────────────────────────────────────

def test_v10403_regenerator_excludes_admin_and_exec():
    """Regenerator has EXCLUDED_ROLES + EXEC-* filter."""
    text = (REPO / "utils" / "cascade_regenerator.py").read_text()
    assert "EXCLUDED_ROLES" in text
    assert '"Admin"' in text
    assert 'startswith("EXEC-")' in text


def test_v10403_no_cascade_to_admin_or_exec():
    """target_cascade has zero allocations to Admin or EXEC-*."""
    tc = _load("target_cascade.json")
    bad_count = 0
    for k, v in tc.items():
        if k.startswith("_") or "|" not in k:
            continue
        if not isinstance(v, dict):
            continue
        for a in v.get("allocations", []):
            to = str(a.get("to_code", ""))
            if to.startswith("EXEC-") or to == "ADMIN001":
                bad_count += 1
    assert bad_count == 0, f"{bad_count} cascade allocations to EXEC-*/ADMIN001"


def test_v10403_md_has_exactly_10_chief_recipients():
    """MD's NPL Ratio|2026 cascade goes to exactly 10 chiefs (was 20)."""
    tc = _load("target_cascade.json")
    md_entry = tc.get("300001|NPL Ratio|2026")
    assert md_entry is not None, "MD's NPL Ratio|2026 cascade missing"
    allocations = md_entry.get("allocations", [])
    assert len(allocations) == 10, (
        f"MD allocates to {len(allocations)} recipients; expected 10 chiefs only"
    )
    # All recipients should have numeric staff_codes (real, not EXEC-*)
    for a in allocations:
        to = str(a.get("to_code", ""))
        assert not to.startswith("EXEC-"), f"EXEC-* recipient: {to}"
        assert to != "ADMIN001", "Admin still a recipient"


def test_v10403_no_phantom_cascade_from_synthetic_chiefs():
    """No cascade entries FROM EXEC-* codes (no phantom senders)."""
    tc = _load("target_cascade.json")
    phantom = []
    for k in tc:
        if k.startswith("_") or "|" not in k:
            continue
        parts = k.split("|")
        if parts[0].startswith("EXEC-"):
            phantom.append(k)
    assert not phantom, f"Phantom cascade entries from EXEC-* still exist: {phantom[:3]}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Change log cleaned (A5) + KPI duplicates marked (B1-B4)
# ────────────────────────────────────────────────────────────────────

def test_v10403_change_log_no_test_entries():
    """canonical_change_log.json has no test_user/deep_test entries."""
    log = _load("canonical_change_log.json")
    test_entries = [e for e in log
                   if "test_user" in str(e.get("who", ""))
                   or "deep_test" in str(e.get("who", ""))]
    assert not test_entries, f"{len(test_entries)} test entries remain"


def test_v10403_kpi_library_duplicates_marked():
    """4 KPI library duplicates marked with _v10403_alias_of.

    Forward-compatible: after v10.420 the duplicates are actually removed
    (consolidated into canonical IDs), so this test accepts either:
      (a) all 4 still present with _v10403_alias_of marker (pre-v10.420)
      (b) all 4 gone, AND v10.420 dedup metadata present (post-v10.420)
    """
    kpi_lib = _load("kpi_library.json")
    marked = []
    for entry in kpi_lib.get("kpis", []):
        if isinstance(entry, dict) and "_v10403_alias_of" in entry:
            marked.append(entry.get("id"))
    expected = {"NEW_ACCOUNTS", "K069", "K048", "NIM"}

    # Either: all 4 marked (pre-v10.420)
    if set(marked) >= expected:
        return

    # Or: all 4 consolidated (post-v10.420)
    completed = kpi_lib.get("_v10420_dedup_complete")
    if completed:
        pairs = completed.get("pairs_migrated", {})
        assert set(pairs.keys()) >= expected, (
            f"v10.420 metadata present but missing pairs: {pairs}"
        )
        # Verify duplicates are actually gone from kpis list
        all_ids = {k.get("id") for k in kpi_lib.get("kpis", []) if isinstance(k, dict)}
        for dup in expected:
            assert dup not in all_ids, f"{dup} still in kpis list after v10.420"
        return

    raise AssertionError(
        f"Neither v10.403 markers nor v10.420 completion found. "
        f"Marked: {marked}"
    )


def test_v10403_kpi_library_provenance_present():
    """Top-level _v10403_dedup_pending note present."""
    kpi_lib = _load("kpi_library.json")
    assert "_v10403_dedup_pending" in kpi_lib


# ────────────────────────────────────────────────────────────────────
# Section 4 — State preservation + Gate
# ────────────────────────────────────────────────────────────────────

def test_v10403_engine_state_preserved():
    """All 4 metrics still zero."""
    for k in list(sys.modules):
        if "cascade" in k:
            del sys.modules[k]
    from utils.cascade_structure_engine import full_audit
    s = full_audit().summary
    assert s["cycles_count"] == 0
    assert s["cross_branch_count"] == 0
    assert s["multi_sender_count"] == 0
    assert s["rep_critical_count"] == 0


def test_v10403_backups_preserved():
    backup_dir = REPO / "data" / "_v10403_backups"
    for f in ("users.json.before", "target_cascade.json.before",
              "canonical_change_log.json.before", "kpi_library.json.before"):
        assert (backup_dir / f).exists()


def test_v10403_g289_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10403_cascade_cleanup
    r = gate_v10403_cascade_cleanup()
    assert r["passed"], r.get("violations")
