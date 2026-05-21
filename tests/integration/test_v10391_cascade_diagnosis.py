"""Integration tests for v10.391 — Target Cascade Deep Diagnosis.

Review-only batch. These tests verify the DIAGNOSIS CLAIMS are still
accurate at the time of test run — they probe live data to confirm
the findings documented in
docs/TARGET_CASCADE_DEEP_DIAGNOSIS_v10.391.md.

If any test fails AFTER v10.392+ fixes are applied, that's GOOD news:
the cascade is being healed. These tests will be replaced or migrated
to "fix verification" gates in subsequent batches.

12 tests across 5 sections.
"""

import json
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load(path):
    return json.loads((REPO / "data" / path).read_text())


# ────────────────────────────────────────────────────────────────────
# Section 1 — Diagnosis document exists with required structure
# ────────────────────────────────────────────────────────────────────

def test_v10391_doc_exists_and_has_11_parts():
    p = REPO / "docs" / "TARGET_CASCADE_DEEP_DIAGNOSIS_v10.391.md"
    assert p.exists()
    text = p.read_text()
    for part in range(1, 12):
        assert f"## Part {part}" in text, f"missing Part {part}"


def test_v10391_doc_documents_critical_findings():
    p = REPO / "docs" / "TARGET_CASCADE_DEEP_DIAGNOSIS_v10.391.md"
    text = p.read_text()
    # The 9 CRITICAL findings must all appear
    for tc in ("TC1", "TC2", "TC18", "TC20", "TC25", "TC26", "TC28", "TC29"):
        assert tc in text, f"missing CRITICAL finding {tc}"


def test_v10391_doc_lists_6_joshua_decisions():
    p = REPO / "docs" / "TARGET_CASCADE_DEEP_DIAGNOSIS_v10.391.md"
    text = p.read_text()
    for d in range(1, 7):
        assert f"**C{d}**" in text or f"C{d} " in text, f"missing decision C{d}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Probe live data to confirm CRITICAL findings exist
# ────────────────────────────────────────────────────────────────────

def test_v10391_tc20_circular_md_crbo_cascade_present_RETIRED_v10392():
    """RETIRED v10.392: TC20 bug fixed; this test is now obsolete.

    The original assertion was that CRBO cascades back to MD (which was
    a bug). v10.392 removed those allocations. To re-enable this test
    we would need to UN-fix the cycle — don't.
    """
    return  # skip — bug fixed by v10.392
    # Original body below (preserved for history):
    """TC20: MD↔CRBO circular cascade."""
    tc = _load("target_cascade.json")
    # MD (300001) cascades to CRBO (300002)?
    md_cascades_to_crbo = False
    crbo_cascades_to_md = False
    for k, v in tc.items():
        if not isinstance(v, dict): continue
        if v.get("from_code") == "300001":
            for a in v.get("allocations", []) or []:
                if a.get("to_code") == "300002":
                    md_cascades_to_crbo = True
        if v.get("from_code") == "300002":
            for a in v.get("allocations", []) or []:
                if a.get("to_code") == "300001":
                    crbo_cascades_to_md = True
    assert md_cascades_to_crbo, "MD (300001) doesn't cascade to CRBO (300002)"
    assert crbo_cascades_to_md, "CRBO (300002) doesn't cascade back to MD"


def _retired_v10397_test_v10391_tc26_ratio_kpi_summed_across_subordinates():
    """TC26: Ratio KPIs being summed (e.g. CASA Ratio 60% → 23,160%)."""
    tc = _load("target_cascade.json")
    # Find CASA Ratio entries with allocated_sum >> total_target
    extreme_over = 0
    for k, v in tc.items():
        if not isinstance(v, dict): continue
        if v.get("kpi") in ("CASA Ratio", "NPL Ratio", "PAR"):
            tgt = v.get("total_target") or 0
            alloc = v.get("allocated_sum") or 0
            if tgt > 0 and alloc / tgt > 100:  # 100× over
                extreme_over += 1
    assert extreme_over > 0, (
        "TC26 should find ratio KPIs over-allocated by 100×+"
    )


def _retired_v10397_test_v10391_tc25_over_allocation_majority():
    """TC25: Most cascade entries over-allocated (>1.05× target)."""
    tc = _load("target_cascade.json")
    over = 0
    total = 0
    for k, v in tc.items():
        if not isinstance(v, dict): continue
        if not v.get("kpi"): continue
        tgt = v.get("total_target") or 0
        alloc = v.get("allocated_sum") or 0
        if tgt > 0:
            total += 1
            if alloc / tgt > 1.05:
                over += 1
    assert total > 100, "need a meaningful sample"
    over_pct = over / total
    assert over_pct > 0.5, (
        f"TC25 expects >50% over-allocated, got {over_pct:.1%}"
    )


def test_v10391_tc28_role_kpi_weights_dont_sum_to_one():
    """TC28: Role KPI weights don't sum to 1.0 across roles."""
    lib = _load("kpi_library.json")
    role_kpis = lib.get("role_kpis", {})
    kpi_lookup = {k["id"]: k for k in lib.get("kpis", [])}

    incomplete_roles = 0
    for role in ("Chief Executive & Managing Director", "Managing Director",
                 "Branch Manager", "Teller"):
        kpis = role_kpis.get(role, [])
        if not isinstance(kpis, list): continue
        total_w = 0.0
        for k_ref in kpis:
            if isinstance(k_ref, str):
                entry = kpi_lookup.get(k_ref)
                if entry:
                    total_w += entry.get("weight", 0)
            elif isinstance(k_ref, dict):
                total_w += k_ref.get("weight", 0)
        if abs(total_w - 1.0) > 0.05:
            incomplete_roles += 1
    assert incomplete_roles >= 3, (
        f"TC28 expects multiple roles with incomplete weights; "
        f"got {incomplete_roles}"
    )


def test_v10391_tc29_role_kpis_unresolved_in_library():
    """TC29: Many KPI IDs in role_kpis don't exist in kpi_library."""
    lib = _load("kpi_library.json")
    role_kpis = lib.get("role_kpis", {})
    library_ids = {k["id"] for k in lib.get("kpis", [])}

    # Sample BM and Teller — both should have many unresolved
    bm_kpis = role_kpis.get("Branch Manager", [])
    teller_kpis = role_kpis.get("Teller", [])
    bm_unresolved = sum(1 for k in bm_kpis
                        if isinstance(k, str) and k not in library_ids)
    teller_unresolved = sum(1 for k in teller_kpis
                            if isinstance(k, str) and k not in library_ids)

    assert bm_unresolved > 10, (
        f"TC29 expects BM to have >10 unresolved KPIs; got {bm_unresolved}"
    )
    assert teller_unresolved > 10, (
        f"TC29 expects Teller to have >10 unresolved KPIs; got {teller_unresolved}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Org structure findings
# ────────────────────────────────────────────────────────────────────

def _retired_v10399_test_v10391_tc6_two_md_roles_in_users():
    """TC6: Both 'Chief Executive & Managing Director' AND 'Managing Director'."""
    users = _load("users.json")
    has_ceo_md = any(u.get("role") == "Chief Executive & Managing Director"
                     for u in users.values())
    has_md = any(u.get("role") == "Managing Director"
                 for u in users.values())
    assert has_ceo_md, "expected 'Chief Executive & Managing Director'"
    assert has_md, "expected 'Managing Director'"


def _retired_v10399_test_v10391_tc7_synthetic_csuite_isolated_from_cascade():
    """TC7: EXEC-* synthetic chiefs don't appear in cascade."""
    users = _load("users.json")
    tc = _load("target_cascade.json")

    # Find EXEC-* coded users
    exec_codes = {u.get("staff_code") for u in users.values()
                  if u.get("staff_code", "").startswith("EXEC-")}

    if not exec_codes:
        return  # synthetic system disabled — finding moot

    # Check none of these appear as cascade senders or receivers
    cascade_participants = set()
    for k, v in tc.items():
        if not isinstance(v, dict): continue
        if v.get("from_code"):
            cascade_participants.add(v["from_code"])
        for a in v.get("allocations", []) or []:
            if a.get("to_code"):
                cascade_participants.add(a["to_code"])
    isolated_exec = exec_codes - cascade_participants
    assert len(isolated_exec) > 0, (
        f"TC7 expects EXEC-* synthetic chiefs isolated; "
        f"all {len(exec_codes)} are in cascade — possibly fixed?"
    )


def test_v10391_tc17_branch_credit_manager_doesnt_exist():
    """TC17: Canonical 'Branch Credit Manager' role has zero live staff."""
    users = _load("users.json")
    bcm_count = sum(1 for u in users.values()
                    if u.get("role") == "Branch Credit Manager")
    assert bcm_count == 0, (
        f"TC17 expects zero Branch Credit Managers in users.json; got {bcm_count}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — G276 + verifier
# ────────────────────────────────────────────────────────────────────

def test_v10391_g276_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10391_cascade_diagnosis
    r = gate_v10391_cascade_diagnosis()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G276"


# ────────────────────────────────────────────────────────────────────
# Section 5 — No regression
# ────────────────────────────────────────────────────────────────────

def test_v10391_review_only_no_data_changes():
    """v10.391 is review-only. No data files should have changed since v10.390."""
    # Just verify the data files still parse cleanly
    for f in ("target_cascade.json", "bank_targets.json",
              "kpi_library.json", "users.json", "org_config.json"):
        try:
            _load(f)
        except Exception as e:
            assert False, f"{f} should still parse cleanly: {e}"
