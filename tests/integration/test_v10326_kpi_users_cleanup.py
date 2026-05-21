"""tests/integration/test_v10326_kpi_users_cleanup.py

v10.326 — Credit KPI definitions + synthetic Exec users.

Closes B-020 (Credit KPI ALL_KPIS_DANGLING) and B-021 (EXEC-*
not in users registry). After this batch, verify_bsc_submission_path
should return 22 of 22 clean departments (was 19).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ────────────────────────────────────────────────────────────────────
# Section 1 — Credit KPI definitions (B-020)
# ────────────────────────────────────────────────────────────────────

EXPECTED_CREDIT_KPIS = {
    "CREDIT_APPROVAL_RATE",
    "CREDIT_DECLINE_RATE",
    "CREDIT_REWORK_RATE",
    "CREDIT_TAT_STANDARD",
    "CREDIT_TAT_COMPLEX",
    "CREDIT_TAT_EXPRESS",
    "LOAN_DISBURSEMENT_TAT",
    "INIT_STATUS",
    "INIT_COUNT",
    "COMPLIANCE_SCORE",
    "DILIGENCE",
}


def test_all_credit_kpis_defined_in_library():
    lib = json.loads(
        (REPO_ROOT / "data" / "kpi_library.json").read_text())
    ids = {k.get("id") for k in lib.get("kpis", [])}
    missing = EXPECTED_CREDIT_KPIS - ids
    assert not missing, f"Credit KPIs missing from library: {missing}"


def test_credit_kpis_have_required_fields():
    lib = json.loads(
        (REPO_ROOT / "data" / "kpi_library.json").read_text())
    by_id = {k.get("id"): k for k in lib.get("kpis", [])}
    required = {"id", "name", "pillar", "unit",
                "direction", "active"}
    for kpi_id in EXPECTED_CREDIT_KPIS:
        kpi = by_id.get(kpi_id)
        assert kpi is not None
        missing = required - set(kpi.keys())
        assert not missing, (
            f"{kpi_id} missing fields: {missing}"
        )


def test_credit_kpis_all_active():
    lib = json.loads(
        (REPO_ROOT / "data" / "kpi_library.json").read_text())
    by_id = {k.get("id"): k for k in lib.get("kpis", [])}
    for kpi_id in EXPECTED_CREDIT_KPIS:
        assert by_id[kpi_id]["active"] is True, (
            f"{kpi_id} is not active"
        )


def test_credit_kpis_in_process_pillar():
    """All credit operational KPIs belong to Process pillar."""
    lib = json.loads(
        (REPO_ROOT / "data" / "kpi_library.json").read_text())
    by_id = {k.get("id"): k for k in lib.get("kpis", [])}
    for kpi_id in EXPECTED_CREDIT_KPIS:
        assert by_id[kpi_id]["pillar"] == "Process", (
            f"{kpi_id} pillar is {by_id[kpi_id]['pillar']}, "
            f"expected Process"
        )


def test_tat_kpis_use_days_unit():
    """TAT KPIs measured in days."""
    lib = json.loads(
        (REPO_ROOT / "data" / "kpi_library.json").read_text())
    by_id = {k.get("id"): k for k in lib.get("kpis", [])}
    tat_kpis = ("CREDIT_TAT_STANDARD", "CREDIT_TAT_COMPLEX",
                "CREDIT_TAT_EXPRESS", "LOAN_DISBURSEMENT_TAT")
    for kpi_id in tat_kpis:
        assert by_id[kpi_id]["unit"] == "days"
        # Lower TAT = better
        assert by_id[kpi_id]["direction"] == "lower"


def test_rate_kpis_use_percent_unit():
    lib = json.loads(
        (REPO_ROOT / "data" / "kpi_library.json").read_text())
    by_id = {k.get("id"): k for k in lib.get("kpis", [])}
    rate_kpis = ("CREDIT_APPROVAL_RATE", "CREDIT_DECLINE_RATE",
                 "CREDIT_REWORK_RATE")
    for kpi_id in rate_kpis:
        assert by_id[kpi_id]["unit"] == "%"


def test_v10326_addition_tag():
    lib = json.loads(
        (REPO_ROOT / "data" / "kpi_library.json").read_text())
    additions = lib.get("_v10326_credit_kpi_additions", [])
    assert len(additions) >= 11, (
        f"Expected ≥11 v10.326 credit KPI additions, got "
        f"{len(additions)}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Synthetic Exec users (B-021)
# ────────────────────────────────────────────────────────────────────

EXPECTED_EXEC_USERS = {
    "exec_md_001",
    "exec_cro_001",
    "exec_cco_001",
    "exec_coo_001",
    "exec_cfo_001",
    "exec_cio_001",
    "exec_crso_001",
    "exec_ccmp_001",
    "exec_cia_001",
    "exec_chro_001",
    "exec_ccmo_001",
}


def test_all_exec_users_present():
    users = json.loads(
        (REPO_ROOT / "data" / "users.json").read_text())
    missing = EXPECTED_EXEC_USERS - set(users)
    assert not missing, f"Synthetic Exec users missing: {missing}"


def test_exec_users_tagged_synthetic():
    users = json.loads(
        (REPO_ROOT / "data" / "users.json").read_text())
    for username in EXPECTED_EXEC_USERS:
        u = users[username]
        assert u.get("_v10326_synthetic_user") is True, (
            f"{username} missing _v10326_synthetic_user tag"
        )


def test_exec_users_have_synthetic_password():
    """Synthetic users have a non-login password (cannot authenticate)."""
    users = json.loads(
        (REPO_ROOT / "data" / "users.json").read_text())
    for username in EXPECTED_EXEC_USERS:
        u = users[username]
        # Should be the literal "synthetic_no_login" sentinel
        assert u["password"] == "synthetic_no_login", (
            f"{username} has unexpected password — should be "
            f"sentinel to prevent login"
        )


def test_exec_users_map_to_canonical_codes():
    users = json.loads(
        (REPO_ROOT / "data" / "users.json").read_text())
    for username in EXPECTED_EXEC_USERS:
        sc = users[username].get("staff_code", "")
        assert sc.startswith("EXEC-"), (
            f"{username} staff_code '{sc}' must start with EXEC-"
        )
        # Username derives from staff_code
        derived = sc.lower().replace("-", "_")
        assert derived == username, (
            f"{username} doesn't match canonical derivation "
            f"from staff_code {sc}"
        )


def test_md_user_has_can_view_all():
    users = json.loads(
        (REPO_ROOT / "data" / "users.json").read_text())
    md = users.get("exec_md_001")
    assert md is not None
    assert md.get("can_view_all") is True
    assert md.get("is_admin") is True


# ────────────────────────────────────────────────────────────────────
# Section 3 — End-to-end: BSC submission path
# ────────────────────────────────────────────────────────────────────

def test_bsc_verification_now_at_22_of_22():
    """The smoking gun for B-020 + B-021."""
    from utils.virtual_bank import verify_bsc_submission_path
    r = verify_bsc_submission_path()
    clean = r["departments_clean"]
    tested = r["departments_tested"]
    assert clean == 22, (
        f"Expected all 22 of {tested} clean, got {clean}. "
        f"Failures: "
        f"{[(d, rr.get('status')) for d, rr in r['results'].items() if rr.get('status') != 'OK']}"
    )


def test_credit_dept_no_longer_dangling():
    """The original B-020 symptom — Credit dept reaches clean state."""
    from utils.virtual_bank import verify_bsc_submission_path
    r = verify_bsc_submission_path()
    credit = r["results"].get("Credit")
    assert credit is not None
    assert credit["status"] == "OK", (
        f"Credit dept still failing: {credit}"
    )


def test_executive_dept_submission_succeeds():
    """The original B-021 symptom — Executive dept can submit."""
    from utils.virtual_bank import verify_bsc_submission_path
    r = verify_bsc_submission_path()
    execu = r["results"].get("Executive")
    assert execu is not None
    assert execu["status"] == "OK", (
        f"Executive dept still failing: {execu}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Audit gate G217
# ────────────────────────────────────────────────────────────────────

def test_g217_gate_passes():
    from scripts.audit import GATES
    g = None
    for gid, fn in GATES:
        if gid == "G217":
            g = fn()
            break
    assert g is not None, "G217 not registered"
    assert g["passed"], (
        f"G217 failed: violations={g.get('violations', [])}"
    )
