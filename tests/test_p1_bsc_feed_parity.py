"""Phase P Batch P1 regression — LMS + Credit-Admin BSC-feed parity.

Asserts the two React-facing mutation routes that close the credit chain
recompute BSC actuals after a successful mutation, matching the Pipeline
routes. Source-scan style (no live server / no heavy imports) mirrors
tests/test_bsc_engine_breadth.py so it runs in any environment.

Closes the integration-parity gap recorded as M1 (LMS) and M2
(Credit Admin) in PARITY_UX_ASSESSMENT_2026_06_12.md.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_bsc_bridge_module_exists():
    """The shared bridge must exist and wrap the canonical recompute."""
    src = _src("utils/api_bsc_bridge.py")
    assert "def emit_bsc_trigger" in src, "emit_bsc_trigger must be defined"
    assert "update_bsc_from_modules" in src, (
        "bridge must call the canonical utils.core.update_bsc_from_modules"
    )


def test_bsc_bridge_is_best_effort():
    """A recompute failure must not propagate (best-effort contract)."""
    src = _src("utils/api_bsc_bridge.py")
    assert "except Exception" in src, (
        "emit_bsc_trigger must swallow recompute failures so a BSC error "
        "never rolls back a successful mutation"
    )


def test_lms_decision_feeds_bsc():
    src = _src("utils/api_lms_routes.py")
    assert "emit_bsc_trigger" in src, (
        "LMS routes must recompute BSC after a decision (Phase P Batch P1)."
    )


def test_credit_admin_disburse_feeds_bsc():
    src = _src("utils/api_credit_admin_routes.py")
    assert "emit_bsc_trigger" in src, (
        "Credit-Admin routes must recompute BSC after disbursement "
        "clearance (Phase P Batch P1)."
    )


def test_pipeline_bsc_wiring_untouched():
    """P1 must not have disturbed the working pipeline BSC wiring."""
    src = _src("utils/api_pipeline_mutations.py")
    assert "update_bsc_from_modules" in src, (
        "Pipeline's existing BSC wiring must remain intact (zero blast "
        "radius on the G381-protected path)."
    )
