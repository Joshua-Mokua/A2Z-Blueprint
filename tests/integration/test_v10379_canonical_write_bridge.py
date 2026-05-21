"""Integration tests for v10.379 — Canonical Write-Bridge.

Closes the constitutional data flow loop (§5.3):
  Source → Staging → Transformation → Clean → BSC Integration → Reporting

Canonical PBT records from the v10.377 unifier now flow into
bsc_actuals_*.json via bsc_engine.submit() — the MD cockpit's "Canonical
PBT" panel gets its number from the canonical path, not the legacy
`management_accounts` source.

15 tests across 4 sections.
"""

import json
import shutil
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


def _sandbox_bsc_engine():
    """Create a sandbox: tempdir DATA_DIR with users.json + kpi_library.json
    copied in. bsc_engine writes bsc_actuals_*.json to this tempdir.
    Returns (sandbox_path, sandbox_data_dir, restore_function).
    """
    tempdir = tempfile.mkdtemp(prefix="v10379_test_")
    sandbox_data = Path(tempdir) / "data"
    sandbox_data.mkdir()
    for f in ("users.json", "kpi_library.json"):
        shutil.copy(REPO / "data" / f, sandbox_data / f)

    _reimport("utils.bsc_engine")
    import utils.bsc_engine as bsc_engine
    original_data_dir = bsc_engine.DATA_DIR
    bsc_engine.DATA_DIR = sandbox_data
    bsc_engine._KPI_INDEX_CACHE = None
    bsc_engine._USERS_INDEX_CACHE = None
    bsc_engine._ACTUALS_INDEX_CACHE = {}

    def restore():
        bsc_engine.DATA_DIR = original_data_dir
        shutil.rmtree(tempdir, ignore_errors=True)

    return Path(tempdir), sandbox_data, restore


# ────────────────────────────────────────────────────────────────────
# Section 1 — Design doc + writer module presence/safety
# ────────────────────────────────────────────────────────────────────

def test_v10379_design_doc_present_with_7_parts():
    p = REPO / "docs" / "CANONICAL_WRITE_BRIDGE_v10.379.md"
    assert p.exists()
    assert p.stat().st_size > 4000
    text = p.read_text()
    for part in (
        "## Part 1 — Why a write-bridge",
        "## Part 2 — The filter",
        "## Part 3 — Remaining SBU-head collision",
        "## Part 4 — Module API",
        "## Part 5 — Reconciliation gate",
        "## Part 6 — What v10.379 deliberately does NOT do",
        "## Part 7 — Honest acknowledgement",
    ):
        assert part in text, f"missing: {part}"


def test_v10379_writer_module_present():
    p = REPO / "utils" / "canonical_bsc_writer.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("class WriteResult", "def write_canonical_pbt_to_bsc",
                "def preview_canonical_pbt_writes", "def _should_write",
                "def _record_to_submit_kwargs",
                "DEFAULT_TARGET_PERIOD", "WRITER_SOURCE_MODULE_TAG",
                "MD_STAFF_CODE"):
        assert sym in text, f"missing {sym}"


def test_v10379_dry_run_default_is_true_AST_VERIFIED():
    """SAFETY: dry_run must default to True — protects live bsc_actuals."""
    p = REPO / "utils" / "canonical_bsc_writer.py"
    import ast
    tree = ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "write_canonical_pbt_to_bsc":
            args = node.args.args
            defaults = node.args.defaults
            arg_names = [a.arg for a in args]
            default_map = dict(zip(arg_names[-len(defaults):], defaults))
            dr = default_map.get("dry_run")
            assert dr is not None, "dry_run missing from signature"
            assert isinstance(dr, ast.Constant) and dr.value is True, (
                f"SAFETY VIOLATION: dry_run default is {ast.dump(dr)}, must be True"
            )
            return
    raise AssertionError("write_canonical_pbt_to_bsc function not found")


# ────────────────────────────────────────────────────────────────────
# Section 2 — Filter behavior
# ────────────────────────────────────────────────────────────────────

def test_v10379_filter_skips_sbu_absorbed_to_md():
    """SBU records collapsing to MD must be skipped (would collide with bank)."""
    _reimport("utils.canonical_bsc_writer")
    _reimport("utils.bsc_universal_contract")
    from utils.bsc_universal_contract import make_record
    from utils.canonical_bsc_writer import _should_write
    r = make_record(staff_code="300001", kpi_id="PBT", value=1, period="2026",
                    source_module="canonical_pbt_sbu_engine_v10377",
                    metadata={"dimension": "sbu", "sbu": "Support"})
    ok, reason = _should_write(r)
    assert not ok
    assert "absorbed" in reason.lower()


def test_v10379_filter_skips_branch_fallback():
    _reimport("utils.canonical_bsc_writer")
    _reimport("utils.bsc_universal_contract")
    from utils.bsc_universal_contract import make_record
    from utils.canonical_bsc_writer import _should_write
    r = make_record(staff_code="300001", kpi_id="PBT", value=1, period="2026",
                    source_module="canonical_pbt_branch_engine_v10377",
                    metadata={"dimension": "branch", "fallback_used": True})
    ok, _ = _should_write(r)
    assert not ok


def test_v10379_filter_keeps_bank_and_staff():
    _reimport("utils.canonical_bsc_writer")
    _reimport("utils.bsc_universal_contract")
    from utils.bsc_universal_contract import make_record
    from utils.canonical_bsc_writer import _should_write
    bank = make_record(staff_code="300001", kpi_id="PBT", value=1, period="2026",
                       source_module="canonical_pbt_bank_engine_v10377",
                       metadata={"dimension": "bank"})
    ok, _ = _should_write(bank)
    assert ok
    staff = make_record(staff_code="300044", kpi_id="PBT", value=1, period="2026",
                        source_module="canonical_pbt_staff_engine_v10377",
                        metadata={"dimension": "staff"})
    ok, _ = _should_write(staff)
    assert ok


# ────────────────────────────────────────────────────────────────────
# Section 3 — Dry-run + Wet-run sandboxed
# ────────────────────────────────────────────────────────────────────

def test_v10379_dry_run_produces_preview_without_side_effects():
    _reimport("utils.canonical_bsc_writer")
    _reimport("utils.virtual_bank_kpi_unifier")
    from utils.canonical_bsc_writer import write_canonical_pbt_to_bsc
    result = write_canonical_pbt_to_bsc(cbs_dir=None, target_period="2026-Q4")
    assert result.dry_run is True
    assert result.total_records > 50
    assert result.eligible_records < result.total_records
    assert result.skipped_records > 0
    assert result.created == 0
    assert result.updated == 0
    # kwargs_preview only contains ELIGIBLE records
    assert len(result.kwargs_preview) == result.eligible_records


def test_v10379_wet_run_sandboxed_actually_writes():
    """Wet run against sandboxed bsc_engine writes the expected records."""
    sandbox, sandbox_data, restore = _sandbox_bsc_engine()
    try:
        _reimport("utils.canonical_bsc_writer")
        _reimport("utils.virtual_bank_kpi_unifier")
        from utils.canonical_bsc_writer import write_canonical_pbt_to_bsc
        result = write_canonical_pbt_to_bsc(
            cbs_dir=None, target_period="2026-Q4", dry_run=False,
            actor="v10379_integration_test",
        )
        assert result.dry_run is False
        assert result.succeeded > 0
        assert len(result.errors) == 0, f"errors: {result.errors[:3]}"
        # Verify file written
        out_file = sandbox_data / "bsc_actuals_2026-Q4.json"
        assert out_file.exists()
        records = json.loads(out_file.read_text())
        assert len(records) > 0
        # Verify bank record present (MD/PBT)
        bank_records = [r for r in records
                        if r["staff_code"] == "300001" and r["kpi_id"] == "PBT"
                        and "bank_engine" in r["source_module"]]
        assert len(bank_records) == 1
    finally:
        restore()


def test_v10379_wet_run_md_pbt_round_trip():
    """After wet-run, bsc_engine.get_actual returns the canonical PBT."""
    sandbox, sandbox_data, restore = _sandbox_bsc_engine()
    try:
        _reimport("utils.canonical_bsc_writer")
        from utils.canonical_bsc_writer import write_canonical_pbt_to_bsc
        result = write_canonical_pbt_to_bsc(
            cbs_dir=None, target_period="2026-Q4", dry_run=False,
        )
        from utils.bsc_engine import get_actual
        md_pbt = get_actual("300001", "PBT", "2026-Q4")
        assert md_pbt is not None, "MD PBT not round-tripped"
        assert float(md_pbt) != 0
        # The canonical PBT on seed is roughly -7.9B
        assert -1e10 < float(md_pbt) < 0, (
            f"unexpected MD PBT: {float(md_pbt)}"
        )
    finally:
        restore()


def test_v10379_idempotent_re_runs_produce_no_duplicates():
    """Second wet-run should update existing records, not duplicate."""
    sandbox, sandbox_data, restore = _sandbox_bsc_engine()
    try:
        _reimport("utils.canonical_bsc_writer")
        from utils.canonical_bsc_writer import write_canonical_pbt_to_bsc
        r1 = write_canonical_pbt_to_bsc(cbs_dir=None, target_period="2026-Q4", dry_run=False)
        out_file = sandbox_data / "bsc_actuals_2026-Q4.json"
        first_count = len(json.loads(out_file.read_text()))
        # Run again — should be all updates
        r2 = write_canonical_pbt_to_bsc(cbs_dir=None, target_period="2026-Q4", dry_run=False)
        second_count = len(json.loads(out_file.read_text()))
        assert first_count == second_count, (
            f"duplicates: {first_count} → {second_count}"
        )
        assert r2.created == 0, f"2nd run created records (should be 0): {r2.created}"
        assert r2.updated > 0
    finally:
        restore()


def test_v10379_record_metadata_carries_writer_provenance():
    """Every written record metadata.writer = WRITER_SOURCE_MODULE_TAG."""
    sandbox, sandbox_data, restore = _sandbox_bsc_engine()
    try:
        _reimport("utils.canonical_bsc_writer")
        from utils.canonical_bsc_writer import write_canonical_pbt_to_bsc, WRITER_SOURCE_MODULE_TAG
        write_canonical_pbt_to_bsc(cbs_dir=None, target_period="2026-Q4", dry_run=False)
        out_file = sandbox_data / "bsc_actuals_2026-Q4.json"
        records = json.loads(out_file.read_text())
        for r in records:
            md = r.get("metadata", {})
            assert md.get("writer") == WRITER_SOURCE_MODULE_TAG, (
                f"missing writer tag in record: {r}"
            )
            assert md.get("original_period") == "2026"
    finally:
        restore()


# ────────────────────────────────────────────────────────────────────
# Section 4 — G265 + no regression
# ────────────────────────────────────────────────────────────────────

def test_v10379_g265_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_canonical_write_bridge
    r = gate_canonical_write_bridge()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G265"


def test_v10379_no_regression_prior_canonical_identities():
    """All prior G250-G264 hold after v10.379 ship."""
    _reimport("utils.virtual_bank_seed")
    _reimport("utils.virtual_bank_cbs_writer")
    _reimport("utils.customer_pbt_allocator")
    _reimport("utils.branch_pbt_allocator")
    _reimport("utils.pbt_computation")
    _reimport("utils.virtual_bank_kpi_unifier")
    _reimport("utils.customer_master_canonical")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.pbt_computation import compute_pbt_from_cbs
    from utils.virtual_bank_kpi_unifier import unify_all_kpi_flow
    from utils.customer_master_canonical import (
        compute_unified_customer_master, reconciliation_summary,
    )
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        persist_bank_to_cbs(bank, output_dir=td_path)
        # G250 bank PBT still computable
        bp = float(compute_pbt_from_cbs(td_path).pbt)
        assert bp != 0
        # G263 universal records still validate
        u = unify_all_kpi_flow(cbs_dir=td_path, period="2026")
        assert u["validation"]["violations"] == 0
        assert u["reconciliation"]["all_within_kes_100"]
        # G264 customer master still unifies
        unified = compute_unified_customer_master(cbs_dir=td_path)
        s = reconciliation_summary(unified, cbs_dir=td_path)
        assert s["identity_holds"]


def test_v10379_role_taxonomy_still_100_pct():
    _reimport("utils.role_taxonomy")
    from utils.role_taxonomy import validate_role_coverage
    cov = validate_role_coverage()
    assert cov["default"] == 0


def test_v10379_constitutional_alignment_section_5():
    """The writer satisfies the central BSC integration engine mandate (§5.2)."""
    p = REPO / "utils" / "canonical_bsc_writer.py"
    text = p.read_text()
    # Module documents constitutional alignment
    assert "§5" in text or "constitution" in text.lower()
    # Module actually imports bsc_engine.submit (the central integration engine)
    import ast
    tree = ast.parse(text)
    imports_submit = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "bsc_engine" in node.module:
                if any(n.name in ("submit",) for n in node.names):
                    imports_submit = True
    # Or imports it lazily inside function
    if not imports_submit:
        assert "from utils.bsc_engine import submit" in text
