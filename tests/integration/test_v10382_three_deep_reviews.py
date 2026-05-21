"""Integration tests for v10.382 — Three Deep Reviews.

Per Joshua's layered directive at v10.381 wrap-up. v10.382 = REVIEWS ONLY
(no code changes). rm_profitability commitment deferred to v10.383.

Three reviews:
- Customer 360 (3,314 lines, 7 tabs, v10.378 disconnection identified)
- KPI Implementation Plan (9 new KPIs spec'd + data sources + schedule)
- Pillar Weights Admin Module (3 storage locations, 1 orphan, 6 defects)

10 tests across 4 sections.
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — All three reviews present
# ────────────────────────────────────────────────────────────────────

def test_v10382_customer_360_review_present():
    p = REPO / "docs" / "CUSTOMER_360_DEEP_REVIEW_v10.382.md"
    assert p.exists()
    assert p.stat().st_size > 6000, "Customer 360 review too small"
    text = p.read_text()
    for part_num in range(1, 9):
        assert f"## Part {part_num}" in text, f"missing Part {part_num}"


def test_v10382_kpi_implementation_plan_present():
    p = REPO / "docs" / "KPI_IMPLEMENTATION_PLAN_v10.382.md"
    assert p.exists()
    assert p.stat().st_size > 10000, "KPI plan too small"
    text = p.read_text()
    for part_num in range(1, 9):
        assert f"## Part {part_num}" in text, f"missing Part {part_num}"


def test_v10382_pillar_weights_review_present():
    p = REPO / "docs" / "PILLAR_WEIGHTS_ADMIN_MODULE_REVIEW_v10.382.md"
    assert p.exists()
    assert p.stat().st_size > 5000, "Pillar weights review too small"
    text = p.read_text()
    for part_num in range(1, 9):
        assert f"## Part {part_num}" in text, f"missing Part {part_num}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Content coverage
# ────────────────────────────────────────────────────────────────────

def test_v10382_customer_360_covers_all_7_tabs_and_v10378_gap():
    p = REPO / "docs" / "CUSTOMER_360_DEEP_REVIEW_v10.382.md"
    text = p.read_text()
    # Each of the 7 tabs should be referenced
    for tab in ("Customer Lookup", "Portfolio Intelligence", "Churn Risk",
                "Next Best Action", "Segment Analytics",
                "Customer Lifetime Value", "IFRS 7"):
        assert tab in text, f"Customer 360 review missing tab: {tab}"
    # v10.378 disconnection identified
    assert "v10.378" in text
    # 3,314 line count noted
    assert "3,314" in text or "3314" in text
    # Body-system framing
    assert "body" in text.lower()
    assert "organ" in text.lower()


def test_v10382_kpi_plan_covers_all_9_new_kpis():
    p = REPO / "docs" / "KPI_IMPLEMENTATION_PLAN_v10.382.md"
    text = p.read_text()
    # All 9 new KPIs (5 Tier 1 + 4 Tier 2)
    for kpi in ("NIM", "CIR", "ROE", "NPS", "DEP_GROWTH", "DIGITAL_ACT",
                "LEGAL_OVERDUE_RATE", "LEGAL_SLA_ATTORNEY",
                "LEGAL_SLA_DOCS", "LEGAL_SLA_SECURITY",
                "LEGAL_SLA_VALUATION"):
        assert kpi in text, f"KPI plan missing: {kpi}"
    # New modules proposed
    assert "financial_ratios_engine" in text
    assert "customer_focus_engine" in text
    # Body-system framing
    assert "body" in text.lower()
    assert "organ" in text.lower()


def test_v10382_pillar_weights_surfaces_drift():
    p = REPO / "docs" / "PILLAR_WEIGHTS_ADMIN_MODULE_REVIEW_v10.382.md"
    text = p.read_text()
    # Three storage locations identified
    assert "kpi_library.json::pillar_weights" in text
    assert "org_config.json::pillar_weights" in text
    assert "pillars[]" in text or "pillars[].weight" in text
    # Orphan identified
    assert "orphan" in text.lower() or "ORPHAN" in text
    # Two admin UIs
    assert "Bank Identity" in text
    assert "KPI Library" in text
    # 6 defects
    assert "Defect 1" in text or "Defect 6" in text
    # Body-system framing
    assert "body" in text.lower()
    assert "organ" in text.lower()


# ────────────────────────────────────────────────────────────────────
# Section 3 — Decisions queued for Joshua
# ────────────────────────────────────────────────────────────────────

def test_v10382_each_review_queues_decisions():
    docs = [
        "CUSTOMER_360_DEEP_REVIEW_v10.382.md",
        "KPI_IMPLEMENTATION_PLAN_v10.382.md",
        "PILLAR_WEIGHTS_ADMIN_MODULE_REVIEW_v10.382.md",
    ]
    for d in docs:
        text = (REPO / "docs" / d).read_text()
        assert ("decisions queued" in text.lower() or
                "Joshua decisions" in text), f"{d} doesn't queue decisions"


# ────────────────────────────────────────────────────────────────────
# Section 4 — G268 + no regression + reviews are read-only
# ────────────────────────────────────────────────────────────────────

def test_v10382_g268_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_v10382_three_reviews
    r = gate_v10382_three_reviews()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G268"


def test_v10382_no_code_changes_in_v10382():
    """v10.382 ships REVIEW DOCS ONLY — no utility module touched."""
    # We can detect by checking no v10.382 stamps in utils/
    for mod in (REPO / "utils").glob("*.py"):
        text = mod.read_text()
        # No utility should have a v10.382 implementation marker
        # (v10.382 markers in docstrings/comments referring to plans are ok;
        #  what we forbid is implementation tagging)
        if "_v10382" in text or "v10382_" in text:
            # Allow it only if it's a comment, not a function/class
            for line in text.split("\n"):
                stripped = line.strip()
                if stripped.startswith("def ") or stripped.startswith("class "):
                    assert "v10382" not in stripped, (
                        f"v10.382 should be REVIEWS ONLY but found "
                        f"implementation in {mod.name}: {stripped}"
                    )


def test_v10382_no_regression_prior_canonical_identities():
    """All prior G250-G267 still hold."""
    import tempfile
    _reimport("utils")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
    from utils.customer_master_canonical import (
        compute_unified_customer_master, reconciliation_summary,
    )
    from utils.kpi_alias_resolver import scan_role_kpis_coverage
    from utils.customer_profitability import (
        _canonical_customer_lookup_v10381, reset_canonical_customer_cache,
    )
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bp = float(compute_pbt_from_cbs(td_path).pbt)
        assert bp != 0
        u = unify_all_kpi_flow(cbs_dir=td_path, period="2026")
        assert u["validation"]["violations"] == 0
        unified = compute_unified_customer_master(cbs_dir=td_path)
        s = reconciliation_summary(unified, cbs_dir=td_path)
        assert s["identity_holds"]
    cov = scan_role_kpis_coverage()
    assert cov["unknown_orphans"] == 0
    # v10.381 still works
    reset_canonical_customer_cache()
    import json
    raw = json.loads((REPO / "data" / "customer_intelligence.json").read_text())
    real_cif = next(iter(raw.keys()))
    rec = _canonical_customer_lookup_v10381(real_cif)
    assert rec is not None
    assert "sources" in rec
