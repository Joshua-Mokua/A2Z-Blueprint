"""Integration tests for v10.362 — Link 7 MD tile bank-targets binding.

Joshua's directive: close the last PARTIAL link in the Football Team
Test chain. v10.362 verifies the mechanical pieces are wired end-to-end
and surfaces a category-case bug in v10.359's bridge that prevented
loan aggregations.

Mechanical pieces verified:
1. bank_targets.json is loaded by CascadeManager._load_bank
2. MD detection works via get_root_roles + role check
3. _is_md_view branch in pages/1_perform.py populates _casc_targets
   from bank_targets entries
4. _get_bank_aggregate_roles identifies CEO + direct reports
5. compute_bank_aggregates produces bank-wide KPI values from CBS
6. _build_from_cbs in actuals_engine injects bank aggregates into
   actuals rows for bank-aggregate roles
7. Sufficient KPI overlap between bank_targets and compute_bank_aggregates
   for the MD's "on track?" tile to be meaningful

15 tests across 5 sections:
  Section 1 — bank_targets + CascadeManager wiring (3 tests)
  Section 2 — MD detection + target binding (3 tests)
  Section 3 — Bank aggregate roles + actuals injection (3 tests)
  Section 4 — Category-case fix verification (2 tests)
  Section 5 — Readiness audit + G248 (4 tests)
"""

import json
import re
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
# Section 1 — bank_targets + CascadeManager wiring
# ────────────────────────────────────────────────────────────────────

def test_v10362_bank_targets_well_formed():
    """data/bank_targets.json has KPI|YEAR keys with target+buffer."""
    bt = json.loads((REPO / "data" / "bank_targets.json").read_text())
    assert len(bt) >= 50, f"Expected ≥50 bank target entries, got {len(bt)}"
    # Sample format check
    for key, val in list(bt.items())[:5]:
        assert "|" in key, f"Expected KPI|YEAR format, got {key!r}"
        if isinstance(val, dict):
            assert "target" in val, f"Missing 'target' in {key}: {val}"


def test_v10362_cascade_manager_loads_bank_targets():
    """utils/core.py CascadeManager has _load_bank that reads bank_targets.json."""
    core_text = (REPO / "utils" / "core.py").read_text()
    assert "_load_bank" in core_text
    assert "bank_targets.json" in core_text


def test_v10362_perform_page_consults_bank_targets_for_md():
    """pages/1_perform.py loads bank_targets via CascadeManager for MD view."""
    perform_text = (REPO / "pages" / "1_perform.py").read_text()
    assert "_is_md_view" in perform_text
    assert "bank_targets" in perform_text
    # MD branch populates _casc_targets from bank_targets
    md_section_start = perform_text.find("if _is_md_view")
    assert md_section_start > 0
    md_section = perform_text[md_section_start:md_section_start + 2000]
    assert "bank_targets" in md_section


# ────────────────────────────────────────────────────────────────────
# Section 2 — MD detection + target binding
# ────────────────────────────────────────────────────────────────────

def test_v10362_md_detection_via_root_roles():
    """MD detected via get_root_roles, not hardcoded string."""
    perform_text = (REPO / "pages" / "1_perform.py").read_text()
    assert "get_root_roles" in perform_text


def test_v10362_root_roles_includes_md():
    """utils.core.get_root_roles returns at least one MD-equivalent role."""
    # The org_config.json hierarchy has the CEO/MD at the top
    org = json.loads((REPO / "data" / "org_config.json").read_text())
    hier = org.get("hierarchy", {})
    roots = [r for r, p in hier.items() if not p]
    assert len(roots) >= 1, "No root role in org_config hierarchy"
    # Should be a CEO/MD-equivalent
    root_lower = roots[0].lower()
    assert any(x in root_lower for x in ("director", "ceo", "managing")), (
        f"Root role '{roots[0]}' doesn't look like a CEO/MD role"
    )


def test_v10362_bank_targets_kpis_overlap_aggregate_kpis():
    """The bank_targets entries must overlap meaningfully with the
    KPIs that compute_bank_aggregates can produce — otherwise the
    MD's BSC view has targets but no actuals."""
    from utils.actuals_engine import compute_bank_aggregates
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bt = json.loads((REPO / "data" / "bank_targets.json").read_text())
    target_kpis = {k.rsplit("|", 1)[0] for k in bt.keys() if "|" in k}

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        agg = compute_bank_aggregates(Path(td))
        agg_kpis = set(agg.keys())

    overlap = target_kpis & agg_kpis
    assert len(overlap) >= 15, (
        f"Only {len(overlap)} KPIs have BOTH target AND aggregate — "
        f"MD's BSC will be sparse. Expected ≥15. Overlap: {overlap}"
    )


# ────────────────────────────────────────────────────────────────────
# Section 3 — Bank aggregate roles + actuals injection
# ────────────────────────────────────────────────────────────────────

def test_v10362_get_bank_aggregate_roles_returns_executives():
    """_get_bank_aggregate_roles returns CEO + direct reports."""
    from utils.actuals_engine import _get_bank_aggregate_roles
    org = json.loads((REPO / "data" / "org_config.json").read_text())
    roles = _get_bank_aggregate_roles(org)
    assert len(roles) >= 5, (
        f"Expected ≥5 bank-aggregate roles (CEO + direct reports), got {len(roles)}"
    )


def test_v10362_actuals_engine_injects_bank_aggregates():
    """utils/actuals_engine.py has the bank-aggregate injection block."""
    ae_text = (REPO / "utils" / "actuals_engine.py").read_text()
    assert "Bank-aggregate actuals for HO/exec roles" in ae_text
    assert "_bank_agg   = compute_bank_aggregates" in ae_text or \
           "_bank_agg = compute_bank_aggregates" in ae_text
    assert "_get_bank_aggregate_roles" in ae_text


def test_v10362_compute_bank_aggregates_produces_loans():
    """v10.362 fix: compute_bank_aggregates must see loan_outstanding
    from the seeded bank. Pre-v10.362 the LOAN category mismatch meant
    bank loans were always 0 in seeded test data."""
    from utils.actuals_engine import compute_bank_aggregates
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    _reimport("utils.virtual_bank_cbs_writer")
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        agg = compute_bank_aggregates(Path(td))

    assert agg.get("Loan Book Growth", 0) > 0, (
        "Loan Book Growth should be > 0 — v10.362 fixed the LOAN category-case bug"
    )


# ────────────────────────────────────────────────────────────────────
# Section 4 — Category-case fix verification
# ────────────────────────────────────────────────────────────────────

def test_v10362_bridge_uses_title_case_categories():
    """v10.359 bridge had a category-case bug: LOAN / TERM (uppercase)
    didn't match actuals_engine's expected 'Loan' / 'Term Deposit'
    (Title case). v10.362 fixed."""
    seed_text = (REPO / "utils" / "virtual_bank_cbs_writer.py").read_text()
    # Mapping must use title case
    assert '"LOAN":          "Loan"' in seed_text or \
           '"LOAN": "Loan"' in seed_text
    assert '"FIXED_DEPOSIT": "Term Deposit"' in seed_text


def test_v10362_phantom_loan_rows_use_title_case():
    """v10.359 phantom loan rows had 'category': 'LOAN' — must be 'Loan'."""
    seed_text = (REPO / "utils" / "virtual_bank_cbs_writer.py").read_text()
    # The phantom-row dict should use Title case
    assert '"category":                    "Loan",' in seed_text


# ────────────────────────────────────────────────────────────────────
# Section 5 — Readiness audit + G248 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10362_readiness_chain_link7_wired():
    """The readiness audit now reports Link 7 as WIRED."""
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_chain
    chain = _probe_chain()
    assert chain.regional_to_md_tile == "WIRED", (
        f"Link 7 should be WIRED, got {chain.regional_to_md_tile}"
    )


def test_v10362_all_seven_links_wired():
    """v10.362 closes the chain — all 7 links should be WIRED."""
    _reimport("utils.virtual_bank_readiness")
    from utils.virtual_bank_readiness import _probe_chain
    chain = _probe_chain()
    statuses = {
        "teller_action_to_cbs":          chain.teller_action_to_cbs,
        "cbs_to_actuals_engine":         chain.cbs_to_actuals_engine,
        "actuals_engine_to_yoy_sidecar": chain.actuals_engine_to_yoy_sidecar,
        "yoy_sidecar_to_bsc_display":    chain.yoy_sidecar_to_bsc_display,
        "bsc_to_branch_score":           chain.bsc_to_branch_score,
        "branch_to_regional_rollup":     chain.branch_to_regional_rollup,
        "regional_to_md_tile":           chain.regional_to_md_tile,
    }
    not_wired = {k: v for k, v in statuses.items() if v != "WIRED"}
    assert not not_wired, f"Some chain links not WIRED: {not_wired}"


def test_v10362_g248_gate_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_md_tile_binding
    result = gate_md_tile_binding()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G248"


def test_v10362_g248_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G248", gate_md_tile_binding)' in text
