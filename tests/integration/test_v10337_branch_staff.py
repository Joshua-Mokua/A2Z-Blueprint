"""Integration tests for v10.337 — Branch-level individual scorecards
+ Pipeline activity bridge.

14 tests across 6 sections:
  Section 1 — branch_staff_generator surface (2 tests)
  Section 2 — Staff coverage (3 tests)
  Section 3 — Canonical KPIs + role_kpi migration (3 tests)
  Section 4 — pipeline_activity_bridge (3 tests)
  Section 5 — End-to-end cascade (2 tests)
  Section 6 — Audit gate G226 (1 test)
"""

import json
import sys
from pathlib import Path


REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(modname):
    for k in list(sys.modules):
        if k.startswith(modname):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — branch_staff_generator surface
# ────────────────────────────────────────────────────────────────────

def test_v10337_module_imports_and_surface():
    """Generator exposes the required public surface."""
    _reimport("utils.branch_staff_generator")
    from utils import branch_staff_generator as bg
    for sym in (
        "generate_for_period",
        "find_branch_staff",
        "get_branch_staff_count",
        "list_buckets_covered",
        "load_config",
    ):
        assert hasattr(bg, sym), f"Missing surface: {sym}"


def test_v10337_two_buckets_listed():
    """Generator covers exactly CUSTOMER_SERVICE + BRANCH_SALES."""
    _reimport("utils.branch_staff_generator")
    from utils.branch_staff_generator import list_buckets_covered
    buckets = set(list_buckets_covered())
    assert buckets == {"CUSTOMER_SERVICE", "BRANCH_SALES"}, buckets


# ────────────────────────────────────────────────────────────────────
# Section 2 — Staff coverage
# ────────────────────────────────────────────────────────────────────

def test_v10337_at_least_480_branch_staff_covered():
    """Generator picks up ≥480 staff across the 2 buckets."""
    _reimport("utils.branch_staff_generator")
    from utils.branch_staff_generator import find_branch_staff
    staff = find_branch_staff()
    assert len(staff) >= 480, f"only {len(staff)} branch staff"


def test_v10337_at_least_140_csos_covered():
    """≥140 Customer Service Officers in CUSTOMER_SERVICE bucket."""
    _reimport("utils.branch_staff_generator")
    from utils.branch_staff_generator import find_branch_staff
    csos = [s for s in find_branch_staff() if s[2] == "CUSTOMER_SERVICE"]
    assert len(csos) >= 140, f"only {len(csos)} CSOs"


def test_v10337_branch_sales_split_correct():
    """BRANCH_SALES includes all 5 sales role variants."""
    _reimport("utils.branch_staff_generator")
    from utils.branch_staff_generator import find_branch_staff
    sales = [s for s in find_branch_staff() if s[2] == "BRANCH_SALES"]
    roles = {s[1] for s in sales}
    expected_roles = {
        "Relationship Officer-Business Banker",
        "Relationship Officer-Personal Banker",
        "Branch Relationship Manager",
        "Branch Senior Relationship Officer",
        "Direct Sales Representative - Assets & Liabilities",
    }
    missing = expected_roles - roles
    assert not missing, f"missing roles: {missing}"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Canonical KPIs + role_kpi migration
# ────────────────────────────────────────────────────────────────────

def test_v10337_five_canonical_kpis_registered():
    """5 new canonical KPIs present in kpi_library."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    ids = {k.get("id") for k in lib.get("kpis", [])}
    expected = {
        "ACCOUNT_OPENING_TAT",
        "COMPLAINT_RESOLUTION_RATE",
        "PIPELINE_DEALS_WON",
        "PIPELINE_CONVERSION_RATE",
        "NEW_CUSTOMERS_ACQUIRED",
    }
    missing = expected - ids
    assert not missing, f"missing canonical KPIs: {missing}"


def test_v10337_role_kpi_migration_tag_complete():
    """Migration tag records ≥6 roles with rollback data."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    mig = lib.get("_v10337_branch_staff_canonical_migration")
    assert mig, "migration tag absent"
    assert mig.get("shipped") == "v10.337"
    roles = mig.get("roles_migrated", [])
    assert len(roles) >= 6, f"only {len(roles)} roles tagged"
    prev = mig.get("previous_kpis", {})
    assert prev, "previous_kpis (rollback) missing"


def test_v10337_csos_have_service_kpis_not_pipeline():
    """CSOs get the service KPI set, no pipeline KPIs."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    cso_kpis = lib.get("role_kpis", {}).get("Customer Service Officer", [])
    expected_service = {
        "NEW_ACCOUNTS", "ACCOUNT_OPENING_TAT",
        "COMPLAINT_RESOLUTION_RATE", "Account Dormancy",
        "CX Score", "COMPLIANCE_SCORE", "Staff Productivity",
    }
    assert set(cso_kpis) == expected_service, cso_kpis
    # Verify CSOs do NOT have pipeline KPIs (cleanly separated)
    pipeline_kpis = {"PIPELINE_DEALS_WON", "PIPELINE_CONVERSION_RATE",
                     "NEW_CUSTOMERS_ACQUIRED"}
    overlap = set(cso_kpis) & pipeline_kpis
    assert not overlap, f"CSO incorrectly has pipeline KPIs: {overlap}"


# ────────────────────────────────────────────────────────────────────
# Section 4 — pipeline_activity_bridge
# ────────────────────────────────────────────────────────────────────

def test_v10337_pipeline_activity_bridge_surface():
    """pipeline_to_bsc exposes the v10.337 activity-bridge surface."""
    _reimport("utils.pipeline_to_bsc")
    from utils import pipeline_to_bsc as pb
    for sym in (
        "sync_pipeline_activity_to_bsc",
        "compute_pipeline_activity",
        "_classify_deal_state",
    ):
        assert hasattr(pb, sym), f"pipeline_to_bsc missing: {sym}"


def test_v10337_pipeline_activity_classification():
    """Stage classifier returns 'won'/'lost'/'active'/'unknown'."""
    _reimport("utils.pipeline_to_bsc")
    from utils.pipeline_to_bsc import _classify_deal_state
    mapping = {
        "_meta": {
            "stages_treated_as_won": ["Disbursed", "Closed Won"],
            "stages_treated_as_lost": ["Closed Lost"],
        }
    }
    assert _classify_deal_state("Disbursed", mapping) == "won"
    assert _classify_deal_state("Closed Won", mapping) == "won"
    assert _classify_deal_state("Closed Lost", mapping) == "lost"
    assert _classify_deal_state("Proposal", mapping) == "active"
    assert _classify_deal_state("", mapping) == "unknown"


def test_v10337_pipeline_activity_actuals_present_q2():
    """≥400 pipeline_activity_bridge actuals in 2026-Q2."""
    actuals = json.loads(
        (REPO / "data" / "bsc_actuals_2026-Q2.json").read_text()
    )
    from_bridge = [
        a for a in actuals
        if isinstance(a, dict)
        and a.get("source_module") == "pipeline_activity_bridge"
    ]
    assert len(from_bridge) >= 400, (
        f"only {len(from_bridge)} pipeline_activity_bridge actuals"
    )
    # Validate the 3 expected KPIs
    kpis_emitted = {a.get("kpi_id") for a in from_bridge}
    assert "PIPELINE_DEALS_WON" in kpis_emitted
    assert "PIPELINE_CONVERSION_RATE" in kpis_emitted
    assert "NEW_CUSTOMERS_ACQUIRED" in kpis_emitted


# ────────────────────────────────────────────────────────────────────
# Section 5 — End-to-end cascade
# ────────────────────────────────────────────────────────────────────

def test_v10337_branch_staff_actuals_in_bsc_store():
    """≥2,800 branch_staff_generator actuals in 2026-Q2."""
    actuals = json.loads(
        (REPO / "data" / "bsc_actuals_2026-Q2.json").read_text()
    )
    from_gen = [
        a for a in actuals
        if isinstance(a, dict)
        and a.get("source_module") == "branch_staff_generator"
    ]
    assert len(from_gen) >= 2800, (
        f"only {len(from_gen)} branch_staff_generator actuals"
    )


def test_v10337_branch_staff_scoring_in_q2_cascade():
    """≥450 branch staff have a score in 2026-Q2 cascade."""
    cs = json.loads(
        (REPO / "data" / "cascade_scores_2026-Q2.json").read_text()
    )
    scores = cs.get("scores", {})
    _reimport("utils.branch_staff_generator")
    from utils.branch_staff_generator import find_branch_staff
    codes = {c for c, _, _ in find_branch_staff()}
    scoring = sum(1 for c in codes if c in scores)
    assert scoring >= 450, (
        f"only {scoring} branch staff scoring of {len(codes)}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 6 — Audit gate G226
# ────────────────────────────────────────────────────────────────────

def test_v10337_g226_gate_passes():
    """G226 audit gate registered and passing."""
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_branch_staff_integration
    result = gate_branch_staff_integration()
    assert result["passed"], (
        f"G226 violations: {result.get('violations')}"
    )
    assert result["id"] == "G226"
    assert result["name"] == "branch_staff_integration"
