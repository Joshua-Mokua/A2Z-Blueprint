"""Integration tests for v10.428 — BSC weight renormalization."""

import re
import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def test_v10428_engine_exists():
    path = REPO / "utils" / "bsc_weight_normalize_engine.py"
    assert path.exists()
    text = path.read_text()
    for needed in (
        "def audit_actuals_weights",
        "def renormalize_actuals_weights",
        "class StaffWeightProfile",
        "class WeightAuditResult",
        "class WeightNormResult",
        "WEIGHT_TOLERANCE",
    ):
        assert needed in text, f"Missing: {needed}"


def test_v10428_zero_streamlit():
    text = (REPO / "utils" / "bsc_weight_normalize_engine.py").read_text()
    streamlit_imports = re.findall(
        r'^\s*(?:import\s+streamlit|from\s+streamlit)\b',
        text, re.MULTILINE,
    )
    assert len(streamlit_imports) == 0


def test_v10428_safety_dry_run_default():
    text = (REPO / "utils" / "bsc_weight_normalize_engine.py").read_text()
    assert "dry_run: bool = True" in text


def test_v10428_tolerance_correct():
    for k in list(sys.modules):
        if "bsc_weight_normalize" in k:
            del sys.modules[k]
    from utils.bsc_weight_normalize_engine import WEIGHT_TOLERANCE
    assert WEIGHT_TOLERANCE == 0.01


def test_v10428_audit_returns_proper_shape():
    from utils.bsc_weight_normalize_engine import (
        audit_actuals_weights, WeightAuditResult,
    )
    result = audit_actuals_weights()
    assert isinstance(result, WeightAuditResult)
    # Post-v10.428: should be 0 not normalized
    assert result.not_normalized_count == 0


def test_v10428_all_weights_sum_to_one():
    """Every staff in actuals should have weights summing to 1.0."""
    import pandas as pd
    df = pd.read_excel(REPO / "data" / "actuals_2025_Dec_25.xlsx", skiprows=1)
    per_staff = df.groupby("Staff Name")["Weight"].sum()
    bad = per_staff[(per_staff - 1.0).abs() > 0.01]
    assert len(bad) == 0, (
        f"{len(bad)} staff have weight sums != 1.0: "
        f"{bad.head(5).to_dict()}"
    )


def test_v10428_weight_normalization_audit_clean():
    """v10.424 audit's weight_normalization category now clean."""
    for k in list(sys.modules):
        if "bsc_audit" in k:
            del sys.modules[k]
    from utils.bsc_audit_engine import audit_weight_normalization
    wa = audit_weight_normalization()
    assert wa.not_normalized_count == 0


def test_v10428_relative_ratios_preserved():
    """Renormalization should preserve relative ratios within a staff."""
    # We use a synthetic to verify the math, since the real data has been
    # transformed.
    import tempfile
    import shutil
    import pandas as pd
    from utils.bsc_weight_normalize_engine import renormalize_actuals_weights
    import utils.bsc_weight_normalize_engine as eng_mod

    tmp = Path(tempfile.mkdtemp())
    original_dd = eng_mod.DATA_DIR
    try:
        path = tmp / "actuals_test.xlsx"
        synth = pd.DataFrame({
            "Staff Name":     ["Charlie", "Charlie", "Charlie"],
            "Staff Code":     ["S99"] * 3,
            "Role":           ["Test"] * 3,
            "Unit":           ["A"] * 3,
            "Category":       ["X"] * 3,
            "Staff Status":   ["Active"] * 3,
            "KPI":            ["KA", "KB", "KC"],
            "Pillar":         ["Financial"] * 3,
            # Ratio 1:2:3, sum=3.0
            "Weight":         [0.5, 1.0, 1.5],
            "Annual Target":  [100] * 3,
            "YTD_Actual":     [50] * 3,
            "Dec-25":         [10] * 3,
            "Annual Actual":  [60] * 3,
        })
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            pd.DataFrame([[""] * len(synth.columns)],
                         columns=synth.columns).to_excel(
                w, sheet_name="KPI Data", index=False, header=False)
            synth.to_excel(w, sheet_name="KPI Data",
                          startrow=1, index=False)

        eng_mod.DATA_DIR = tmp
        result = renormalize_actuals_weights(actuals_path=path, dry_run=False)
        assert result.staff_renormalized == 1

        post = pd.read_excel(path, skiprows=1)
        weights = post[post["Staff Name"] == "Charlie"]["Weight"].tolist()
        # 0.5/3.0, 1.0/3.0, 1.5/3.0 = ~0.167, ~0.333, ~0.500
        assert abs(weights[0] - 1/6) < 0.001
        assert abs(weights[1] - 2/6) < 0.001
        assert abs(weights[2] - 3/6) < 0.001
        # Ratio preserved: 1:2:3
        assert abs(weights[1] / weights[0] - 2.0) < 0.001
        assert abs(weights[2] / weights[0] - 3.0) < 0.001
    finally:
        eng_mod.DATA_DIR = original_dd
        shutil.rmtree(tmp, ignore_errors=True)


def test_v10428_idempotent():
    """Re-running renormalization yields 0 changes."""
    from utils.bsc_weight_normalize_engine import renormalize_actuals_weights
    result = renormalize_actuals_weights(dry_run=False)
    assert result.staff_renormalized == 0
    assert result.rows_modified == 0


def test_v10428_runner_script_exists():
    path = REPO / "scripts" / "renormalize_bsc_weights.py"
    assert path.exists()
    assert "--confirm" in path.read_text()


def test_v10428_api_endpoints_registered():
    text = (REPO / "utils" / "api.py").read_text()
    assert "/api/v1/bsc-weights/audit" in text
    assert "/api/v1/bsc-weights/renormalize" in text


def test_v10428_dataclasses_json_serializable():
    from utils.bsc_weight_normalize_engine import (
        audit_actuals_weights, renormalize_actuals_weights,
    )
    import json
    a = audit_actuals_weights()
    r = renormalize_actuals_weights(dry_run=True)
    json.dumps(a.to_dict())
    json.dumps(r.to_dict())


def test_v10428_g314_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10428_weight_normalize
    r = gate_v10428_weight_normalize()
    assert r["passed"], r.get("violations")
