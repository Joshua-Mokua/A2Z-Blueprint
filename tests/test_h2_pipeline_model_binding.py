"""Hardening Batch H2 — pipeline route model binding.

The 7 pipeline routes annotate their body as forward-ref strings
(payload: "PipelineDealCreate" etc.) but the models were never imported
into utils/api.py — so FastAPI could not bind the real (patched) classes
and a clean start would NameError at route setup. H2 imports them at module
level so the forward-refs resolve to the current classes.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_models_imported_at_module_level():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    assert "from utils.api_pipeline_models import (" in src
    for m in ("PipelineDealCreate", "PipelineDealRefer", "PipelineDealUpdate",
              "PipelineDealAdvance", "PipelineDealValidate",
              "PipelineDealCancelRequest", "PipelineDealCancelApprove"):
        assert m in src, f"{m} must be importable in api.py namespace"


def test_forward_refs_resolve_and_staff_code_optional():
    from utils.api_pipeline_models import PipelineDealCreate, PipelineDealRefer
    assert PipelineDealCreate.model_fields["staff_code"].is_required() is False
    assert PipelineDealCreate.model_fields["staff_name"].is_required() is False
    assert PipelineDealRefer.model_fields["staff_code"].is_required() is False
    # a body without identity must now construct (no 422)
    m = PipelineDealCreate(client_name="Test", deal_value=1000.0,
                           product_type="Business Loan", stage="Lead")
    assert m.staff_code is None
