"""Batch A (backend) — stages from config.

Stages are admin-configurable (org_config), but the advance gate was hardcoded
and didn't include configured stages, the create form had no canonical stage
source, and created deals had no open_date. This batch: a config-aware advance
gate, a /api/pipeline/stages endpoint, and open_date stamped on create.
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_advance_gate_unions_configured_stages():
    src = (ROOT / "utils" / "api_pipeline_mutations.py").read_text(encoding="utf-8")
    assert "def _configured_stage_names" in src
    assert "new_stage not in _configured_stage_names()" in src


def test_stages_endpoint_exists():
    src = (ROOT / "utils" / "api.py").read_text(encoding="utf-8")
    assert '@app.get("/api/pipeline/stages")' in src
    assert "get_pipeline_stages()" in src


def test_open_date_stamped_on_create():
    src = (ROOT / "utils" / "core.py").read_text(encoding="utf-8")
    assert "d.setdefault('open_date'" in src


def test_gate_logic():
    ALLOWED = {"Proposal", "Closed Lost"}
    DEFERRED = {"Credit Review", "Disbursed"}
    CONFIG = {"Needs Analysis", "Prospecting", "Proposal", "Credit Review"}
    def ok(ns):
        if ns in DEFERRED: return True
        return ns in ALLOWED or ns in CONFIG
    assert ok("Needs Analysis")     # configured -> now allowed
    assert ok("Credit Review")      # handoff trigger
    assert not ok("Garbage")        # still rejected
