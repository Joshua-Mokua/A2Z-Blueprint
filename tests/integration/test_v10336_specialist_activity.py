"""Integration tests for v10.336 — Specialist department integration.

13 tests across 5 sections:
  Section 1 — Module surface (3 tests)
  Section 2 — Staff coverage (3 tests)
  Section 3 — Canonical KPIs + role_kpi migration (3 tests)
  Section 4 — End-to-end cascade (3 tests)
  Section 5 — Audit gate G225 (1 test)
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
# Section 1 — Module surface
# ────────────────────────────────────────────────────────────────────

def test_v10336_module_imports_and_surface():
    """Generator exposes the required public surface."""
    _reimport("utils.specialist_activity_generator")
    from utils import specialist_activity_generator as sg
    for sym in (
        "generate_for_period",
        "find_specialist_staff",
        "get_specialist_staff_count",
        "list_departments_covered",
        "load_config",
    ):
        assert hasattr(sg, sym), f"Missing surface: {sym}"


def test_v10336_three_departments_listed():
    """Generator covers exactly Treasury + Trade Finance + Marketing."""
    _reimport("utils.specialist_activity_generator")
    from utils.specialist_activity_generator import list_departments_covered
    depts = set(list_departments_covered())
    assert depts == {"TREASURY", "TRADE_FINANCE", "MARKETING"}, depts


def test_v10336_config_loads_with_required_keys():
    """Config has performance_bands + departments + role_kpi_bases."""
    _reimport("utils.specialist_activity_generator")
    from utils.specialist_activity_generator import load_config
    cfg = load_config()
    for k in ("performance_bands", "departments", "role_kpi_bases"):
        assert k in cfg, f"config missing top-level: {k}"
    for band in ("HIGH", "MID", "LOW"):
        assert band in cfg["performance_bands"]


# ────────────────────────────────────────────────────────────────────
# Section 2 — Staff coverage
# ────────────────────────────────────────────────────────────────────

def test_v10336_at_least_twenty_specialists_covered():
    """Generator picks up ≥20 staff across the 3 departments."""
    _reimport("utils.specialist_activity_generator")
    from utils.specialist_activity_generator import find_specialist_staff
    staff = find_specialist_staff()
    assert len(staff) >= 20, f"only {len(staff)} specialists"


def test_v10336_excludes_upstream_covered_heads():
    """Head of Treasury (300164) + Head Corp & TF (300017) are
    excluded — they're already scoring via upstream producers."""
    _reimport("utils.specialist_activity_generator")
    from utils.specialist_activity_generator import find_specialist_staff
    codes = {c for c, _, _ in find_specialist_staff()}
    assert "300164" not in codes, "300164 should be excluded (support_function)"
    assert "300017" not in codes, "300017 should be excluded (products_to_bsc)"


def test_v10336_department_split_correct():
    """Treasury ≥6, Trade Finance ≥10, Marketing = 4."""
    _reimport("utils.specialist_activity_generator")
    from utils.specialist_activity_generator import find_specialist_staff
    from collections import Counter
    counter = Counter(d for _, _, d in find_specialist_staff())
    assert counter["TREASURY"] >= 6, counter
    assert counter["TRADE_FINANCE"] >= 10, counter
    assert counter["MARKETING"] == 4, counter


# ────────────────────────────────────────────────────────────────────
# Section 3 — Canonical KPIs + role_kpi migration
# ────────────────────────────────────────────────────────────────────

def test_v10336_eleven_canonical_kpis_registered():
    """All 11 new canonical KPIs present in kpi_library."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    ids = {k.get("id") for k in lib.get("kpis", [])}
    expected = {
        "LIQUIDITY_COVERAGE_RATIO", "NET_STABLE_FUNDING_RATIO",
        "NET_INTEREST_MARGIN", "FX_TRADING_INCOME",
        "TRADE_FINANCE_REVENUE", "TRADE_DOC_TAT", "LC_VOLUME",
        "CAMPAIGN_ROI", "BRAND_AWARENESS",
        "MARKETING_QUALIFIED_LEADS", "MARKETING_DRIVEN_REVENUE",
    }
    missing = expected - ids
    assert not missing, f"missing canonical KPIs: {missing}"


def test_v10336_role_kpi_migration_tag_complete():
    """_v10336_specialist_canonical_migration records ≥13 roles
    with full rollback metadata."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    mig = lib.get("_v10336_specialist_canonical_migration")
    assert mig, "migration tag absent"
    assert mig.get("shipped") == "v10.336"
    roles = mig.get("roles_migrated", [])
    assert len(roles) >= 13, f"only {len(roles)} roles tagged"
    prev = mig.get("previous_kpis", {})
    assert prev, "previous_kpis (rollback) missing"


def test_v10336_migrated_roles_have_canonical_kpis():
    """Sample migrated roles now hold canonical KPI names
    (not K-codes) — verifies the migration actually happened."""
    lib = json.loads((REPO / "data" / "kpi_library.json").read_text())
    rk = lib.get("role_kpis", {})
    for role in (
        "Senior Manager Treasury",
        "Trade Finance Officer",
        "Head Of Marketing and Corporate Communication",
    ):
        kpis = rk.get(role, [])
        k_codes = [k for k in kpis if isinstance(k, str)
                   and k.startswith("K") and k[1:].isdigit()]
        assert not k_codes, (
            f"{role} still has K-codes after migration: {k_codes}"
        )
        assert len(kpis) >= 5, f"{role} has too few KPIs"


# ────────────────────────────────────────────────────────────────────
# Section 4 — End-to-end cascade
# ────────────────────────────────────────────────────────────────────

def test_v10336_q2_actuals_present_in_bsc_store():
    """≥120 specialist_activity_generator actuals in 2026-Q2."""
    actuals = json.loads(
        (REPO / "data" / "bsc_actuals_2026-Q2.json").read_text()
    )
    from_gen = [
        a for a in actuals
        if isinstance(a, dict)
        and a.get("source_module") == "specialist_activity_generator"
    ]
    assert len(from_gen) >= 120, (
        f"only {len(from_gen)} specialist actuals in Q2"
    )


def test_v10336_specialists_scoring_in_q2_cascade():
    """≥18 of 20 specialist staff have a computed score in Q2 cascade."""
    cs = json.loads(
        (REPO / "data" / "cascade_scores_2026-Q2.json").read_text()
    )
    scores = cs.get("scores", {})
    specialist_codes = [
        "300165", "300166", "300167", "300168", "300169", "300170",
        "300041", "300042", "300044", "300171", "300172", "300173",
        "300174", "300175", "300176", "300177",
        "300222", "300223", "300224", "300225",
    ]
    scoring = sum(1 for c in specialist_codes if scores.get(c) is not None)
    assert scoring >= 18, (
        f"only {scoring}/{len(specialist_codes)} specialist staff scoring"
    )


def test_v10336_actuals_present_across_four_quarters():
    """≥480 specialist actuals total across Q3'25, Q4'25, Q1'26, Q2'26."""
    total = 0
    for q in ("2025-Q3", "2025-Q4", "2026-Q1", "2026-Q2"):
        actuals = json.loads(
            (REPO / "data" / f"bsc_actuals_{q}.json").read_text()
        )
        total += sum(
            1 for a in actuals
            if isinstance(a, dict)
            and a.get("source_module") == "specialist_activity_generator"
        )
    assert total >= 480, f"only {total} across 4 quarters"


# ────────────────────────────────────────────────────────────────────
# Section 5 — Audit gate G225
# ────────────────────────────────────────────────────────────────────

def test_v10336_g225_gate_passes():
    """G225 audit gate registered and passing."""
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_specialist_activity_integration
    result = gate_specialist_activity_integration()
    assert result["passed"], (
        f"G225 violations: {result.get('violations')}"
    )
    assert result["id"] == "G225"
    assert result["name"] == "specialist_activity_integration"
