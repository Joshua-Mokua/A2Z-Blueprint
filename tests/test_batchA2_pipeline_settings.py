"""Batch A2 — pipeline config from pipeline_settings.json (the authoritative
admin config), correcting Batch A which read org_config (7-stage fallback).

The seeded data uses 17 stages across 9 deal categories defined in
pipeline_settings.json. The advance gate, stage validation, and the
/api/pipeline/stages endpoint must read THAT, or configured stages get
rejected (the mismatch).
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_core_reads_all_pipeline_stages():
    src = (ROOT / "utils" / "core.py").read_text(encoding="utf-8")
    assert "def get_all_pipeline_stage_names" in src
    assert "deal_categories" in src  # collects per-category flows


def test_gate_uses_all_configured_stages():
    src = (ROOT / "utils" / "api_pipeline_mutations.py").read_text(encoding="utf-8")
    assert "get_all_pipeline_stage_names" in src


def test_endpoint_returns_rich_config():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    for key in ['"deal_categories"', '"sectors"', '"decision_levels"',
                '"probability_map"', '"product_catalogue"']:
        assert key in src, f"endpoint must expose {key}"


def test_all_category_stages_collected():
    import json
    cfg = json.load(open(ROOT / "data" / "pipeline_settings.json"))
    names = set()
    for st in cfg.get("stages", []):
        n = st.get("stage", "").strip() if isinstance(st, dict) else str(st).strip()
        if n: names.add(n)
    for cat in cfg.get("deal_categories", []):
        for st in cat.get("stages", []):
            if str(st).strip(): names.add(str(st).strip())
    # previously-rejected stages must now be present
    for s in ["Term Sheet", "Due Diligence", "Valuation", "Credit Committee"]:
        assert s in names
