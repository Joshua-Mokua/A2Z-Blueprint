"""Integration tests for v10.367 — Profitability Reconciliation Diagnostic.

v10.367 ships a measurement-first batch:
- utils/profitability_reconciliation.py — diagnostic module
- docs/PROFITABILITY_ARCHITECTURE_REVIEW.md — structural review + unification arc
- G253 — informational gate (passes; reports delta as metric)

No engine changes. v10.368-v10.372 close the divergence batch by batch.

13 tests across 4 sections.
"""

import json
import sys
import tempfile
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
# Section 1 — Module surface + architecture review doc
# ────────────────────────────────────────────────────────────────────

def test_v10367_module_present():
    p = REPO / "utils" / "profitability_reconciliation.py"
    assert p.exists()
    text = p.read_text()
    for sym in ("class EngineSnapshot",
                "class ReconciliationReport",
                "def _snapshot_engine_a",
                "def _snapshot_engine_b",
                "def _normalize_to_annual",
                "def reconcile",
                "def format_report",
                "def self_test"):
        assert sym in text, f"profitability_reconciliation missing {sym}"


def test_v10367_module_imports_only_legitimate_engines():
    """Only utils.pbt_computation + utils.sbu_pnl_rollup allowed —
    those are this module's consumers-of-consumers."""
    import ast
    text = (REPO / "utils" / "profitability_reconciliation.py").read_text()
    tree = ast.parse(text)
    utils_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("utils"):
                utils_imports.add(node.module)
    allowed = {"utils.pbt_computation", "utils.sbu_pnl_rollup"}
    unexpected = utils_imports - allowed
    assert not unexpected, (
        f"profitability_reconciliation has unexpected utils.* imports: "
        f"{unexpected} (allowed: {allowed})"
    )


def test_v10367_architecture_review_doc_present():
    p = REPO / "docs" / "PROFITABILITY_ARCHITECTURE_REVIEW.md"
    assert p.exists(), "Architecture review doc missing — v10.367 deliverable"
    text = p.read_text()
    # Required sections
    for section in ("Current state — the four engines",
                    "The reconciliation identity",
                    "The unification arc — five batches",
                    "v10.368",
                    "v10.369",
                    "v10.370",
                    "v10.371",
                    "v10.372"):
        assert section in text, (
            f"Architecture review missing section: {section}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 2 — Engine snapshots + normalization
# ────────────────────────────────────────────────────────────────────

def test_v10367_engine_a_snapshot():
    _reimport("utils.profitability_reconciliation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.profitability_reconciliation import (
        _snapshot_engine_a, EngineSnapshot,
    )
    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        snap = _snapshot_engine_a(Path(td))
    assert isinstance(snap, EngineSnapshot)
    assert snap.engine_id == "A_pbt_computation"
    assert snap.time_horizon == "ytd"
    assert snap.customer_basis == "cbs_accounts"
    # OpEx must be the full bank-wide ~7.9B (from opex_data.json)
    assert snap.indirect_cost > Decimal("7_000_000_000")


def test_v10367_engine_b_snapshot():
    _reimport("utils.profitability_reconciliation")
    from utils.profitability_reconciliation import (
        _snapshot_engine_b, EngineSnapshot,
    )
    snap = _snapshot_engine_b(period="2026-Q2", cost_source="matrix")
    assert isinstance(snap, EngineSnapshot)
    assert snap.engine_id == "B_sbu_pnl_rollup"
    assert snap.time_horizon == "quarterly"
    assert snap.customer_basis == "customer_intelligence"
    assert snap.revenue > 0
    assert snap.indirect_cost > 0


def test_v10367_normalize_quarterly_to_annual():
    _reimport("utils.profitability_reconciliation")
    from utils.profitability_reconciliation import (
        _normalize_to_annual, EngineSnapshot,
    )
    q = EngineSnapshot(
        engine_id="Q",
        revenue=Decimal("100"),
        pbt=Decimal("50"),
        time_horizon="quarterly",
    )
    n = _normalize_to_annual(q)
    assert n.revenue == Decimal("400")
    assert n.pbt == Decimal("200")
    assert n.time_horizon == "annual"


# ────────────────────────────────────────────────────────────────────
# Section 3 — Full reconcile()
# ────────────────────────────────────────────────────────────────────

def test_v10367_reconcile_returns_structured_report():
    _reimport("utils.profitability_reconciliation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.profitability_reconciliation import reconcile, ReconciliationReport

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        report = reconcile(Path(td))
    assert isinstance(report, ReconciliationReport)
    assert report.status in ("CONVERGED", "TOLERANCE", "DIVERGENT")
    # The two engines have different data sources — divergence is expected
    # in v10.367 (this is what the unification arc closes)
    assert report.delta_pbt_pct >= 0  # always non-negative


def test_v10367_reconcile_normalizes_time_horizons():
    """Engine B is quarterly; report's engine_b should be annualized."""
    _reimport("utils.profitability_reconciliation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.profitability_reconciliation import reconcile

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        report = reconcile(Path(td))
    # Both snapshots should be annual after normalization
    assert report.engine_a.time_horizon == "annual" or \
           report.engine_a.time_horizon == "ytd"  # YTD passes through
    assert report.engine_b.time_horizon == "annual"


def test_v10367_format_report_human_readable():
    _reimport("utils.profitability_reconciliation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.profitability_reconciliation import reconcile, format_report

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        report = reconcile(Path(td))
    s = format_report(report)
    for keyword in ("Profitability Reconciliation", "Engine A", "Engine B",
                    "Revenue", "PBT", "ΔPBT", "Status"):
        assert keyword in s, f"format_report missing '{keyword}'"


def test_v10367_report_serializes_to_json():
    _reimport("utils.profitability_reconciliation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.profitability_reconciliation import reconcile

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        report = reconcile(Path(td))
    d = report.to_dict()
    # Must be JSON-serializable
    s = json.dumps(d)
    assert "engine_a" in d and "engine_b" in d
    assert isinstance(d["delta_pbt_kes"], float)


def test_v10367_reasons_surface_divergence_causes():
    """When engines diverge, reasons list should explain why."""
    _reimport("utils.profitability_reconciliation")
    from utils.virtual_bank_seed import seed_virtual_bank, SeedConfig
    from utils.virtual_bank_cbs_writer import persist_bank_to_cbs
    from utils.profitability_reconciliation import reconcile

    bank, _ = seed_virtual_bank(config=SeedConfig.small())
    with tempfile.TemporaryDirectory() as td:
        persist_bank_to_cbs(bank, output_dir=Path(td))
        report = reconcile(Path(td))
    if report.status == "DIVERGENT":
        assert len(report.reasons) > 0, (
            "DIVERGENT but no reasons listed — diagnostic isn't surfacing causes"
        )
        joined = " ".join(report.reasons)
        # Expected divergence reasons in v10.367's pre-unification state
        assert ("customer basis" in joined.lower() or
                "revenue" in joined.lower()), (
            "Reasons should mention customer basis or revenue divergence"
        )


# ────────────────────────────────────────────────────────────────────
# Section 4 — G253 audit gate (informational)
# ────────────────────────────────────────────────────────────────────

def test_v10367_g253_passes():
    """G253 is INFORMATIONAL — passes whenever the diagnostic runs cleanly.
    The delta is reported in summary but doesn't fail."""
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_profitability_reconciliation
    result = gate_profitability_reconciliation()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G253"


def test_v10367_g253_reports_delta_in_summary():
    """G253's summary must include the current ΔPBT as metadata."""
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_profitability_reconciliation
    result = gate_profitability_reconciliation()
    assert "ΔPBT" in result["summary"] or "delta" in result["summary"].lower()


def test_v10367_g253_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G253", gate_profitability_reconciliation)' in text


# ────────────────────────────────────────────────────────────────────
# Section 5 — Self-test (hand-rolled fixtures, no upward import chain)
# ────────────────────────────────────────────────────────────────────

def test_v10367_self_test_passes():
    _reimport("utils.profitability_reconciliation")
    from utils.profitability_reconciliation import self_test
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        self_test()
    assert "self-test passed" in buf.getvalue()
