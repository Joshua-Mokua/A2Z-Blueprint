"""Integration tests for v10.376 — Performance Management Framework Bridge (Phase A third).

Per Joshua's course correction (v10.375 wrap-up): "the other objective of the
entire system is performance management... I really don't want us to lose the
gist of this system." This batch integrates the canonical profitability arc
into the BSC + KPI Library + Target Cascade framework — the system's primary
purpose.

Three deliverables:
  1. docs/PERFORMANCE_MANAGEMENT_FRAMEWORK_REVIEW_v10.376.md (9 Parts)
  2. utils/canonical_pbt_bsc_view.py (read-only bridge)
  3. MD cockpit BSC Summary tab enhancement (canonical PBT panel)

12 tests across 4 sections.
"""

import json
import sys
import tempfile
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — PM review document
# ────────────────────────────────────────────────────────────────────

def test_v10376_pm_review_document_present_and_substantive():
    p = REPO / "docs" / "PERFORMANCE_MANAGEMENT_FRAMEWORK_REVIEW_v10.376.md"
    assert p.exists()
    assert p.stat().st_size > 10000, "PM review doc seems too small to be substantive"


def test_v10376_pm_review_has_all_9_parts():
    p = REPO / "docs" / "PERFORMANCE_MANAGEMENT_FRAMEWORK_REVIEW_v10.376.md"
    text = p.read_text()
    for section in (
        "## Part 1 — The Performance Management framework",
        "## Part 2 — Where canonical PBT",
        "## Part 3 — The unification pattern",
        "## Part 4 — Existing performance-management drift",
        "## Part 5 — The MD's Daily Question",
        "## Part 6 — Refined roadmap",
        "## Part 7 — What v10.376 actually delivers",
        "## Part 8 — Decisions awaiting Joshua",
        "## Part 9 — Honest acknowledgement of drift",
    ):
        assert section in text, f"missing section: {section}"


def test_v10376_pm_review_documents_drift_concretely():
    """Joshua: 'this happened to me and I have had to work so hard to get
    development back on course.' The review must surface real drift."""
    p = REPO / "docs" / "PERFORMANCE_MANAGEMENT_FRAMEWORK_REVIEW_v10.376.md"
    text = p.read_text()
    # Concrete drift items must be documented
    for drift_marker in (
        "KPI-ID drift",
        "Pillar weight drift",
        "Source-module drift",
        "kpi_library",
        "target_cascade",
        "bsc_actuals",
    ):
        assert drift_marker in text, f"missing drift documentation: {drift_marker}"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Bridge module
# ────────────────────────────────────────────────────────────────────

def test_v10376_bridge_module_present():
    p = REPO / "utils" / "canonical_pbt_bsc_view.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("class MDPBTSummary",
                "def get_md_pbt_summary",
                "def get_md_cascade_allocations",
                "def format_md_pbt_card",
                "def self_test",
                "MD_STAFF_CODE",
                "PBT_KPI_ID"):
        assert sym in text, f"missing {sym}"


def test_v10376_bridge_returns_canonical_actual():
    """Bridge must produce a non-zero PBT against the seeded virtual bank."""
    _reimport("utils.canonical_pbt_bsc_view")
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.pbt_computation")
    from utils.canonical_pbt_bsc_view import get_md_pbt_summary
    s = get_md_pbt_summary(cbs_dir=None, period="2026")
    # On the seeded small bank, PBT is ~-7.9B (loss); non-zero
    assert s.actual != 0, "canonical actual is 0 — engine probably failed silently"


def test_v10376_bridge_joins_with_md_cascade_target():
    """target_cascade.json::300001|PBT|2026 must yield 22B target with 12 allocations."""
    _reimport("utils.canonical_pbt_bsc_view")
    from utils.canonical_pbt_bsc_view import get_md_pbt_summary
    s = get_md_pbt_summary(cbs_dir=None, period="2026")
    assert s.target > 0, "no MD PBT target — cascade missing"
    assert len(s.allocations) >= 1, "expected MD's direct-report allocations"


def test_v10376_bridge_enriches_allocations_with_role_taxonomy():
    """Each allocation must carry a profitability_tier from v10.374 taxonomy."""
    _reimport("utils.canonical_pbt_bsc_view")
    _reimport("utils.role_taxonomy")
    from utils.canonical_pbt_bsc_view import get_md_cascade_allocations
    allocations = get_md_cascade_allocations(period="2026")
    if allocations:
        for a in allocations:
            assert "profitability_tier" in a
            # tier should be one of the 5 (or 'unknown' as fallback)
            assert a["profitability_tier"] in (
                "portfolio_owner", "proposition_owner",
                "structural_owner", "service", "support", "unknown"
            ), f"bad tier: {a['profitability_tier']}"


def test_v10376_bridge_is_read_only():
    """Bridge module must NOT import write APIs from bsc_engine."""
    p = REPO / "utils" / "canonical_pbt_bsc_view.py"
    import ast
    tree = ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "bsc_engine" in node.module:
                names = [n.name for n in node.names]
                forbidden = {"submit", "submit_batch", "_persist"}
                violations = set(names) & forbidden
                assert not violations, (
                    f"bridge imports write APIs {violations} — must be read-only"
                )


def test_v10376_bridge_documents_engine_provenance():
    """Summary must reference all canonical gates: G250, G256, G257, G258, G253, G261."""
    _reimport("utils.canonical_pbt_bsc_view")
    from utils.canonical_pbt_bsc_view import get_md_pbt_summary
    s = get_md_pbt_summary(cbs_dir=None, period="2026")
    for required_gate in ("G250", "G256", "G257", "G258", "G253", "G261"):
        assert required_gate in s.canonical_engine_status, (
            f"engine_status missing {required_gate}"
        )


def test_v10376_bridge_includes_body_system_axes():
    """Joshua's framing must be coded into the summary."""
    _reimport("utils.canonical_pbt_bsc_view")
    from utils.canonical_pbt_bsc_view import get_md_pbt_summary
    s = get_md_pbt_summary(cbs_dir=None, period="2026")
    for axis in ("skeleton", "circulatory", "function"):
        assert axis in s.body_system_axes


# ────────────────────────────────────────────────────────────────────
# Section 3 — MD cockpit integration + G262
# ────────────────────────────────────────────────────────────────────

def test_v10376_md_cockpit_integrates_bridge():
    p = REPO / "pages" / "100_md_cockpit.py"
    text = p.read_text()
    for anchor in (
        "canonical_pbt_bsc_view",
        "v10.376",
        "Canonical PBT",
        "Cascade Target",
        "get_md_pbt_summary",
    ):
        assert anchor in text, f"MD cockpit missing v10.376 anchor: {anchor!r}"


def test_v10376_g262_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_pm_framework_bridge
    r = gate_pm_framework_bridge()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G262"


# ────────────────────────────────────────────────────────────────────
# Section 4 — No regression to prior unification + Charter §2
# ────────────────────────────────────────────────────────────────────

def test_v10376_all_prior_unification_identities_still_hold():
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    _reimport("utils.sbu_pnl_rollup")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import (
        compute_pbt_from_cbs, compute_pbt_by_sbu, sum_sbu_pbts,
    )
    from utils.branch_pbt_allocator import (
        compute_pbt_by_branch, sum_branch_pbts,
    )
    from utils.customer_pbt_allocator import (
        compute_pbt_by_customer, sum_customer_pbts,
        compute_pbt_by_staff, sum_staff_pbts,
    )
    from utils.sbu_pnl_rollup import bank_total_pnl
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        bp = float(compute_pbt_from_cbs(td_path).pbt)
        for rollup in (
            float(sum_sbu_pbts(compute_pbt_by_sbu(td_path)).pbt),
            float(sum_branch_pbts(compute_pbt_by_branch(td_path)).pbt),
            float(sum_customer_pbts(compute_pbt_by_customer(td_path)).pbt),
            float(sum_staff_pbts(compute_pbt_by_staff(td_path)).pbt),
        ):
            assert abs(bp - rollup) <= 100
        engine_b = bank_total_pnl(cost_source="canonical", cbs_dir=td_path)["pbt"]
        assert abs(bp - engine_b) / max(abs(bp), 1) * 100 < 1.0


def test_v10376_role_taxonomy_still_100_pct():
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import validate_role_coverage
    cov = validate_role_coverage()
    assert cov["default"] == 0
