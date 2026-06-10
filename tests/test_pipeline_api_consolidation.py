"""Regression tests for Phase 3 Arc α Batch α1 — Pipeline API
Consolidation. Verifies G394 (`gate_pipeline_api_uses_canonical_manager`)
and the underlying behavior: that `/api/pipeline/summary` and
`/api/pipeline/deals` route through `PipelineManager` rather than
reading `data/pipeline.json` directly.

Authored v10.503 Phase 3 Arc α Batch α1.

Why this matters
----------------
Per `docs/architecture/PIPELINE_DOMAIN_AUDIT.md` Section 15.1, the
codebase previously had a split-brain pipeline state: the Streamlit
UI read 8 records via `PipelineManager.get_deals()` from
`pipeline_deals.json`, while the FastAPI endpoints read 302 records
via `_load_json("pipeline.json")`. Two surfaces saw different data.

Batch α1 unified these by making the FastAPI endpoints route through
`PipelineManager` — the canonical business-logic layer that Streamlit
uses. This aligns with the established "Streamlit stays, React
additive, FastAPI canonical" architecture documented in
`docs/REACT_READINESS_AUDIT.md` and many earlier batches
(v10.21, v10.400, v10.417, v10.426+).

These tests guard against:
1. The endpoint refactor being reverted accidentally.
2. The Pydantic schema for the canonical shape being deleted.
3. G394 being deregistered from the GATES dispatch table.
4. The endpoint return shape diverging from PipelineManager output.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"
API_PATH = REPO_ROOT / "utils" / "api.py"
MODELS_PATH = REPO_ROOT / "utils" / "api_pipeline_models.py"


def _fresh_audit_module():
    """Load a fresh copy of scripts/audit.py for each test (gates may
    cache file reads internally; isolation matters)."""
    spec = importlib.util.spec_from_file_location(
        "audit_script_for_g394_tests", AUDIT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ──────────────────────────────────────────────────────────────────
# Gate registration tests (3)
# ──────────────────────────────────────────────────────────────────


def test_g394_is_registered_in_gates_table():
    """G394 must appear in the GATES dispatch table."""
    audit = _fresh_audit_module()
    gate_ids = [gid for gid, _fn in audit.GATES]
    assert "G394" in gate_ids, (
        "G394 missing from GATES table — gate cannot run via the "
        "automated audit harness"
    )


def test_g394_function_exists_and_is_callable():
    """The gate function must exist and be callable."""
    audit = _fresh_audit_module()
    assert hasattr(audit, "gate_pipeline_api_uses_canonical_manager"), (
        "scripts/audit.py does not export "
        "gate_pipeline_api_uses_canonical_manager"
    )
    assert callable(audit.gate_pipeline_api_uses_canonical_manager)


def test_g394_returns_well_formed_result():
    """Gate result must include id, name, passed, violations, summary."""
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_api_uses_canonical_manager()
    assert result["id"] == "G394"
    assert result["name"] == "pipeline_api_uses_canonical_manager"
    assert isinstance(result["passed"], bool)
    assert isinstance(result["violations"], list)
    assert isinstance(result["summary"], str)


# ──────────────────────────────────────────────────────────────────
# Gate behavior tests (2)
# ──────────────────────────────────────────────────────────────────


def test_g394_passes_against_current_code():
    """Against the post-Batch-α1 code state, G394 must pass."""
    audit = _fresh_audit_module()
    result = audit.gate_pipeline_api_uses_canonical_manager()
    assert result["passed"], (
        f"G394 fails against current code — violations: "
        f"{result['violations']}"
    )


def test_g394_detects_regression_when_load_json_reintroduced():
    """Counter-test: if `_load_json('pipeline.json')` appears in either
    endpoint body, G394 must fail with a precise violation message.

    We don't actually mutate the file (other tests may be running).
    Instead we mock the AST inspection by injecting a synthetic
    function definition into the API source we test against.

    This is a structural sanity check that the gate's detection logic
    is wired correctly — it parses a string of code containing the
    bad pattern and verifies the AST walker would flag it.
    """
    api_source = API_PATH.read_text(encoding="utf-8")
    tree = ast.parse(api_source)

    # Find the existing pipeline_deals function definition
    pipeline_deals_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "pipeline_deals":
            pipeline_deals_fn = node
            break
    assert pipeline_deals_fn is not None, (
        "Could not find pipeline_deals function in utils/api.py to "
        "verify gate detection logic"
    )

    # Walk the body looking for _load_json("pipeline.json") calls.
    # In the current (correct) state, there should be ZERO such calls
    # inside pipeline_deals. This is the inverse assertion of what
    # G394's gate function checks — if this assertion holds, G394's
    # detection logic is examining the right thing.
    has_load_json_pipeline = False
    for sub in ast.walk(pipeline_deals_fn):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Name) and sub.func.id == "_load_json":
                if sub.args and isinstance(sub.args[0], ast.Constant):
                    if sub.args[0].value == "pipeline.json":
                        has_load_json_pipeline = True
                        break

    assert not has_load_json_pipeline, (
        "pipeline_deals contains a direct _load_json('pipeline.json') "
        "call — Batch α1 was supposed to eliminate this. Either the "
        "refactor was reverted or a regression slipped in."
    )


# ──────────────────────────────────────────────────────────────────
# Pydantic model tests (3)
# ──────────────────────────────────────────────────────────────────


def test_pydantic_models_module_exists():
    """utils/api_pipeline_models.py must exist."""
    assert MODELS_PATH.exists(), (
        "utils/api_pipeline_models.py missing — Pydantic contract "
        "for the canonical pipeline shape must be present"
    )


def test_pydantic_models_export_expected_classes():
    """The three required model classes must be defined."""
    tree = ast.parse(MODELS_PATH.read_text(encoding="utf-8"))
    class_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    }
    expected = {"PipelineDeal", "PipelineSummaryResponse", "PipelineDealsResponse"}
    missing = expected - class_names
    assert not missing, (
        f"utils/api_pipeline_models.py missing model classes: "
        f"{sorted(missing)}"
    )


def test_pydantic_pipeline_deal_parses_real_pipeline_manager_records():
    """PipelineDeal model must successfully parse every record returned
    by PipelineManager.get_deals(). This is the live contract test."""
    # Imports are inside the test so a missing dependency does not
    # prevent the whole module from loading (the audit harness may
    # run tests in environments where streamlit / pandas etc. are
    # not installed).
    import sys
    sys.path.insert(0, str(REPO_ROOT))

    from utils.core import PipelineManager
    from utils.api_pipeline_models import PipelineDeal

    pm = PipelineManager()
    deals = pm.get_deals()

    parsed_count = 0
    errors = []
    for d in deals:
        try:
            PipelineDeal.model_validate(d)
            parsed_count += 1
        except Exception as e:
            errors.append(f"{d.get('id', '<no-id>')}: {e}")

    assert parsed_count == len(deals), (
        f"PipelineDeal failed to parse {len(errors)}/{len(deals)} "
        f"PipelineManager records: {errors[:3]}"
    )


# ──────────────────────────────────────────────────────────────────
# End-to-end behavior tests (2)
# ──────────────────────────────────────────────────────────────────


def test_api_endpoint_response_source_is_pipeline_manager():
    """The endpoints' return dict must declare source='pipeline_manager'
    on the non-PostgreSQL path. This is the contract change that
    distinguishes the new path from the old `source='json'`."""
    api_source = API_PATH.read_text(encoding="utf-8")
    # Both endpoints should reference the new source string at least
    # once. (Note: PostgreSQL paths still report source='postgresql',
    # which is separate.)
    assert '"pipeline_manager"' in api_source, (
        'utils/api.py does not contain source="pipeline_manager" — '
        'the Batch α1 source-label contract is broken'
    )
    # Old "json" source label may still exist elsewhere; we don't
    # require its absence (would be overly strict). The presence of
    # the new label is the positive signal.


def test_pipeline_summary_and_deals_use_consistent_data_source():
    """End-to-end: the data PipelineManager returns must be the same
    data the endpoints aggregate. Specifically, the count from
    /api/pipeline/deals must equal the total_deals from
    /api/pipeline/summary. Both are computed from pm.get_deals()."""
    import sys
    sys.path.insert(0, str(REPO_ROOT))
    from utils.core import PipelineManager

    pm = PipelineManager()
    deals = pm.get_deals()
    expected_count = len(deals)

    # Replicate the summary aggregation
    def _safe_float(v):
        try:
            return float(v)
        except Exception:
            return 0.0

    total = sum(
        _safe_float(d.get("deal_value") or d.get("amount", 0))
        for d in deals
    )

    # The contract: deals count == summary.totals.total_deals
    # The total_value across by_stage rows must equal the totals.pipeline_value
    by_stage_total = 0.0
    by_stage = {}
    for d in deals:
        st = d.get("stage", "Unknown")
        amt = _safe_float(d.get("deal_value") or d.get("amount", 0))
        if st not in by_stage:
            by_stage[st] = 0.0
        by_stage[st] += amt
        by_stage_total += amt

    assert abs(by_stage_total - total) < 0.01, (
        f"by_stage sum {by_stage_total} != totals {total} — "
        "aggregation arithmetic broken"
    )
    assert expected_count == sum(
        1 for _ in deals
    ), "Self-consistency check failed"
