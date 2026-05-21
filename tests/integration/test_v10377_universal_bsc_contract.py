"""Integration tests for v10.377 — Universal BSC Data Contract + Virtual
Bank KPI Flow Unifier.

Per Technical Governance Framework §5.1 (universal contract) + Joshua's
v10.376 wrap-up directive ("have our virtual bank unify how all KPIs flow,
test all modules and ensure every staff works and is measured").

Phase B opens. Establishes the nervous-system layer of the body-system
framing — the signal-carrying contract that every canonical engine output
flows through.

14 tests across 4 sections.
"""

import sys
from decimal import Decimal
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Constitution doc + Universal contract module
# ────────────────────────────────────────────────────────────────────

def test_v10377_constitution_doc_present_and_substantive():
    p = REPO / "docs" / "A2Z_GOVERNANCE_CONSTITUTION_INTERNAL_v10.377.md"
    assert p.exists()
    assert p.stat().st_size > 8000, "constitution doc seems too small"
    text = p.read_text()
    # 8 parts must be present
    for part in (
        "## Part 1 — The constitutional mandates",
        "## Part 2 — The five problems",
        "## Part 3 — The body-system framing",
        "## Part 4 — Today's specific directive",
        "## Part 5 — What v10.377 deliberately does NOT do",
        "## Part 6 — The next 10 batches",
        "## Part 7 — Migration arc to PostgreSQL",
        "## Part 8 — Honest acknowledgement",
    ):
        assert part in text, f"missing section: {part}"


def test_v10377_universal_contract_module_present():
    p = REPO / "utils" / "bsc_universal_contract.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("class UniversalBSCRecord",
                "class ContractViolation",
                "def make_record",
                "def validate_universal_record",
                "def validate_batch",
                "def records_summary",
                "def to_submit_kwargs",
                "PERIOD_FORMATS",
                "SOURCE_MODULE_PATTERN"):
        assert sym in text, f"missing {sym}"


def test_v10377_contract_module_is_leaf():
    """v10.364 module-purity lesson: contract is a leaf — no upward utils imports."""
    p = REPO / "utils" / "bsc_universal_contract.py"
    import ast
    tree = ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("utils"):
                raise AssertionError(
                    f"contract has upward utils.* import: {node.module}"
                )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Contract validation behavior
# ────────────────────────────────────────────────────────────────────

def test_v10377_valid_record_constructs():
    _reimport("utils.bsc_universal_contract")
    from utils.bsc_universal_contract import make_record
    r = make_record(
        staff_code="300001",
        kpi_id="PBT",
        value=22_000_000_000.0,
        period="2026",
        source_module="canonical_pbt_bank_engine_v10377",
    )
    assert r.staff_code == "300001"
    assert r.kpi_id == "PBT"
    assert r.value == 22_000_000_000.0


def test_v10377_contract_rejects_empty_fields():
    _reimport("utils.bsc_universal_contract")
    from utils.bsc_universal_contract import make_record, ContractViolation
    # empty staff_code
    try:
        make_record(staff_code="", kpi_id="PBT", value=1, period="2026",
                    source_module="canonical_pbt_bank_engine_v10377")
        assert False
    except ContractViolation:
        pass
    # empty kpi_id
    try:
        make_record(staff_code="X", kpi_id="", value=1, period="2026",
                    source_module="canonical_pbt_bank_engine_v10377")
        assert False
    except ContractViolation:
        pass


def test_v10377_contract_rejects_nan_and_inf():
    _reimport("utils.bsc_universal_contract")
    from utils.bsc_universal_contract import make_record, ContractViolation
    for bad_value in (float("nan"), float("inf"), float("-inf")):
        try:
            make_record(staff_code="X", kpi_id="PBT", value=bad_value, period="2026",
                        source_module="canonical_pbt_bank_engine_v10377")
            assert False, f"should reject {bad_value}"
        except ContractViolation:
            pass


def test_v10377_contract_validates_period_formats():
    _reimport("utils.bsc_universal_contract")
    from utils.bsc_universal_contract import make_record, ContractViolation
    # Valid formats
    for period in ("2026", "2026-Q2", "2026-04", "2026-04-15"):
        r = make_record(staff_code="X", kpi_id="PBT", value=1, period=period,
                        source_module="canonical_pbt_bank_engine_v10377")
        assert r.period == period
    # Invalid formats
    for bad in ("Q2-2026", "2026Q2", "2026/04", "April 2026"):
        try:
            make_record(staff_code="X", kpi_id="PBT", value=1, period=bad,
                        source_module="canonical_pbt_bank_engine_v10377")
            assert False, f"should reject period {bad!r}"
        except ContractViolation:
            pass


def test_v10377_contract_validates_source_module_convention():
    """source_module must be snake_case per §5.2 traceability."""
    _reimport("utils.bsc_universal_contract")
    from utils.bsc_universal_contract import make_record, ContractViolation
    # Valid
    for src in ("canonical_pbt_bank_engine_v10377", "manual_upload",
                "etl_flexcube_loans", "verification_test"):
        r = make_record(staff_code="X", kpi_id="PBT", value=1, period="2026",
                        source_module=src)
        assert r.source_module == src
    # Invalid (uppercase, spaces, etc.)
    for bad in ("Canonical Engine", "PBT-Engine", "engine.v1", "1engine"):
        try:
            make_record(staff_code="X", kpi_id="PBT", value=1, period="2026",
                        source_module=bad)
            assert False, f"should reject source_module {bad!r}"
        except ContractViolation:
            pass


# ────────────────────────────────────────────────────────────────────
# Section 3 — Virtual bank KPI unifier end-to-end
# ────────────────────────────────────────────────────────────────────

def test_v10377_unifier_module_present():
    p = REPO / "utils" / "virtual_bank_kpi_unifier.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("def unify_bank_pbt",
                "def unify_sbu_pbt",
                "def unify_branch_pbt",
                "def unify_staff_pbt",
                "def unify_all_kpi_flow",
                "SBU_HEAD_STAFF_CODE",
                "MD_STAFF_CODE"):
        assert sym in text, f"missing {sym}"


def test_v10377_unifier_end_to_end_produces_universal_records():
    """The headline test: virtual bank → all canonical engines → universal records."""
    _reimport("utils.bsc_universal_contract")
    _reimport("utils.virtual_bank_kpi_unifier")
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.pbt_computation")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.customer_pbt_allocator")
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
    result = unify_all_kpi_flow(cbs_dir=None, period="2026")
    # Should produce records at every dimension
    assert result["bank_record"] is not None
    assert len(result["sbu_records"]) >= 4   # at least Retail, Commercial, Treasury, Unallocated
    assert len(result["branch_records"]) > 0
    assert len(result["staff_records"]) > 0
    # Total ≥ 50 records
    assert len(result["all_records"]) >= 50, (
        f"only {len(result['all_records'])} records produced"
    )


def test_v10377_unifier_records_all_validate():
    """0 contract violations per §5.4 (no silent failures)."""
    _reimport("utils.virtual_bank_kpi_unifier")
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
    result = unify_all_kpi_flow(cbs_dir=None, period="2026")
    assert result["validation"]["violations"] == 0, (
        f"violations: {result['validation']['violation_detail'][:3]}"
    )


def test_v10377_unifier_reconciliation_holds_at_every_dimension():
    """Σ(SBU records) = Σ(Branch records) = Σ(Staff records) = Bank PBT within KES 100."""
    _reimport("utils.virtual_bank_kpi_unifier")
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
    result = unify_all_kpi_flow(cbs_dir=None, period="2026")
    recon = result["reconciliation"]
    assert recon["all_within_kes_100"], (
        f"reconciliation tolerances exceeded: {recon['tolerances_kes']}"
    )


def test_v10377_unifier_records_carry_engine_gate_provenance():
    """Per §5.2: every record traceable to producing module + engine gate."""
    _reimport("utils.virtual_bank_kpi_unifier")
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
    result = unify_all_kpi_flow(cbs_dir=None, period="2026")
    seen_gates = set()
    for r in result["all_records"]:
        assert "engine_gate" in r.metadata, (
            f"missing engine_gate: {r.staff_code}/{r.kpi_id}"
        )
        seen_gates.add(r.metadata["engine_gate"])
    # Should see all 4 dimension gates
    for required in ("G250", "G254", "G255", "G257"):
        assert required in seen_gates, f"engine_gate {required} not in any record"


def test_v10377_unifier_staff_records_carry_role_taxonomy():
    """Per v10.374 nervous-system spec: every staff record carries profitability_tier."""
    _reimport("utils.virtual_bank_kpi_unifier")
    _reimport("utils.role_taxonomy")
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
    result = unify_all_kpi_flow(cbs_dir=None, period="2026")
    valid_tiers = {"portfolio_owner", "proposition_owner", "structural_owner",
                   "service", "support", "unknown"}
    for r in result["staff_records"]:
        assert "profitability_tier" in r.metadata
        assert r.metadata["profitability_tier"] in valid_tiers


# ────────────────────────────────────────────────────────────────────
# Section 4 — G263 + alignment with prior unification
# ────────────────────────────────────────────────────────────────────

def test_v10377_g263_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_universal_bsc_contract
    r = gate_universal_bsc_contract()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G263"
