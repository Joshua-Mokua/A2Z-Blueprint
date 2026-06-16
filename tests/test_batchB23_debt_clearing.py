"""Batch B23 — debt-clearing regression tests.

#1 Dashboard pipeline alignment: md_dashboard must surface the assured
   (validated) split, not just the consolidated sum.
#2 Pipeline->credit lifecycle: the stage after 'Credit Assessment' in the
   asset flow is a real next stage (not terminal), so auto-advance on submit
   moves the deal forward rather than into a Closed stage.

Runs in Josh's venv (full deps). py_compile-only in the sandbox.
"""
import json
from pathlib import Path


def _settings():
    p = Path(__file__).resolve().parent.parent / "data" / "pipeline_settings.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_asset_flow_has_next_stage_after_credit_assessment():
    flow = _settings().get("stage_flows", {}).get("asset", [])
    assert "Credit Assessment" in flow, "asset flow must contain Credit Assessment"
    i = flow.index("Credit Assessment")
    assert i < len(flow) - 1, "Credit Assessment must not be the terminal stage"
    nxt = flow[i + 1]
    assert not nxt.lower().startswith("closed"), \
        f"auto-advance target '{nxt}' must not be a Closed stage"


def test_md_dashboard_exposes_validated_split():
    src = (Path(__file__).resolve().parent.parent / "utils" / "api.py").read_text(encoding="utf-8")
    # the md_dashboard pipeline block must now carry the assured split keys
    assert '"validated_value":pipe.get("totals",{}).get("validated_value"' in src
    assert '"pending_value":pipe.get("totals",{}).get("pending_value"' in src


def test_submit_advances_stage_logic_present():
    src = (Path(__file__).resolve().parent.parent / "utils" / "api.py").read_text(encoding="utf-8")
    assert "Auto-advanced on submit to credit" in src, \
        "submit-to-credit must advance the pipeline stage (debt #2)"
