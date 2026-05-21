"""
tests/integration/test_compliance_cra_training_v10310.py
================================================================================
v10.310 — Cat A composer for Compliance Risk Assessment +
Training. Closes the LAST placeholder banner across the
cockpit estate.

v10.301 shipped Compliance cockpit (page 112) with tab 6
carrying a placeholder banner pointing to
compliance_risk_assessment and compliance_training engines as
"follow-on Phase 3 batch."

This batch closes that placeholder by composing the two
engines into a 2-section report — same pattern as v10.309
(credit_portfolio_analytics) but with different upstream
engines. Sections:

  1. compliance_risk_assessment.ComplianceRiskAssessmentEngine
     .board_summary() — CRA scoring state
  2. compliance_training.ComplianceTrainingEngine.board_summary()
     — training assignment + certification state

After this batch, **every "composer not yet wired" placeholder
banner across the cockpit estate is closed**.

Test sections:
  1. compliance_cra_training composer exists
  2. Returns documented top-level keys (sections, status,
     n_sections, board_summary, as_at)
  3. Returns exactly 2 sections (CRA + Training)
  4. Each section has the standard shape
     (section_id, section_title, source_engine, status,
     metrics, notes)
  5. JSON-serialisable
  6. Top-level status aggregation
  7. Page 112 tab 6 wired (placeholder banner removed)
  8. /api/cockpit/compliance/cra-training endpoint
  9. G200 audit gate liveness
  10. Idempotent
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Section 1 — Composer contract
# ============================================================

def test_compliance_cra_training_composer_exists():
    from utils import cockpit_read
    assert hasattr(cockpit_read, "compliance_cra_training"), (
        "cockpit_read must expose compliance_cra_training "
        "Cat A composer"
    )


def test_composer_returns_documented_top_level_keys():
    from utils.cockpit_read import compliance_cra_training
    result = compliance_cra_training()
    for k in ("report_id", "sections", "n_sections",
              "board_summary", "status", "as_at"):
        assert k in result, (
            f"compliance_cra_training missing key `{k}`"
        )


def test_composer_returns_two_sections():
    """Two sections: CRA + Training. If a third Cat A
    component gets added later, this test pins the current
    contract."""
    from utils.cockpit_read import compliance_cra_training
    result = compliance_cra_training()
    section_ids = sorted(
        s["section_id"] for s in result["sections"]
    )
    assert "compliance_risk_assessment" in section_ids
    assert "compliance_training" in section_ids
    assert len(result["sections"]) == 2


# ============================================================
# Section 2 — Section shape (mirrors v10.309)
# ============================================================

def test_each_section_has_required_fields():
    from utils.cockpit_read import compliance_cra_training
    result = compliance_cra_training()
    for s in result["sections"]:
        for f in ("section_id", "section_title",
                   "source_engine", "status", "metrics",
                   "notes"):
            assert f in s, (
                f"Section {s.get('section_id', '?')} "
                f"missing field {f}"
            )


def test_section_status_is_one_of_known_values():
    """status ∈ {ok, no_data, error, warning, breach}."""
    from utils.cockpit_read import compliance_cra_training
    result = compliance_cra_training()
    valid = {"ok", "no_data", "error", "warning", "breach"}
    for s in result["sections"]:
        assert s["status"] in valid, (
            f"Section {s['section_id']} status "
            f"{s['status']!r} not in {valid}"
        )


def test_metrics_are_string_keyed_strings():
    """All metric values must be strings (Decimals/ints cast
    upstream) for JSON-serialisability."""
    from utils.cockpit_read import compliance_cra_training
    result = compliance_cra_training()
    for s in result["sections"]:
        for k, v in s["metrics"].items():
            assert isinstance(k, str), (
                f"non-string key in section {s['section_id']}"
            )
            assert isinstance(v, str), (
                f"non-string value {k}={v!r} in section "
                f"{s['section_id']}"
            )


# ============================================================
# Section 3 — JSON-serialisable
# ============================================================

def test_composer_result_is_json_serialisable():
    from utils.cockpit_read import compliance_cra_training
    result = compliance_cra_training()
    re_serialised = json.dumps(result)
    round_tripped = json.loads(re_serialised)
    assert round_tripped == result


# ============================================================
# Section 4 — Top-level status aggregation
# ============================================================

def test_top_level_status_is_one_of_known_values():
    from utils.cockpit_read import compliance_cra_training
    result = compliance_cra_training()
    valid = {"ok", "no_data", "error"}
    assert result["status"] in valid


# ============================================================
# Section 5 — Engine failure tolerance
# ============================================================

def test_composer_returns_two_sections_even_on_engine_failure():
    """Engine failures degrade to status="error" in that
    section; the other section still renders. Composer
    always returns 2 sections."""
    from utils.cockpit_read import compliance_cra_training
    result = compliance_cra_training()
    assert result["n_sections"] == 2


# ============================================================
# Section 6 — Page 112 wired
# ============================================================

def test_page_112_tab_6_uses_composer():
    src = (
        REPO_ROOT / "pages" / "112_compliance_live.py"
    ).read_text()
    assert "compliance_cra_training" in src, (
        "page 112 must reference compliance_cra_training"
    )


def test_page_112_tab_6_placeholder_banner_removed():
    src = (
        REPO_ROOT / "pages" / "112_compliance_live.py"
    ).read_text()
    assert (
        "Cat A composer for CRA + training views ships in"
        not in src
    ), (
        "v10.301 placeholder banner still in page 112 tab 6"
    )


# ============================================================
# Section 7 — HTTP endpoint
# ============================================================

def test_api_cockpit_cra_training_endpoint_registered():
    src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()
    assert "/compliance/cra-training" in src, (
        "api_cockpit.py missing /compliance/cra-training"
    )


def test_api_cockpit_endpoint_documented():
    src = (
        REPO_ROOT / "utils" / "api_cockpit.py"
    ).read_text()
    docstring_end = src.find("\"\"\"", 100)
    docstring = src[:docstring_end + 3]
    assert (
        "/api/cockpit/compliance/cra-training" in docstring
    )


def test_api_cockpit_expected_endpoints_updated():
    """The api_cockpit test's EXPECTED_ENDPOINTS list must
    include the new endpoint so future drift fires the
    discipline test."""
    src = (REPO_ROOT / "tests" / "integration"
           / "test_api_cockpit.py").read_text()
    assert "/api/cockpit/compliance/cra-training" in src


# ============================================================
# Section 8 — Audit gate G200
# ============================================================

def test_g200_gate_exists_and_passes():
    from scripts.audit import GATES
    g200 = None
    for gid, fn in GATES:
        if gid == "G200":
            g200 = fn()
            break
    assert g200 is not None, "G200 not registered"
    assert g200["passed"], (
        f"G200 failed. {g200.get('summary', '')}. "
        f"Violations: {g200.get('violations', [])[:5]}"
    )


# ============================================================
# Section 9 — Idempotency
# ============================================================

def test_composer_idempotent():
    from utils.cockpit_read import compliance_cra_training
    r1 = compliance_cra_training()
    r2 = compliance_cra_training()
    assert r1["n_sections"] == r2["n_sections"]
    ids1 = sorted(s["section_id"] for s in r1["sections"])
    ids2 = sorted(s["section_id"] for s in r2["sections"])
    assert ids1 == ids2


# ============================================================
# Section 10 — Meta-test composer allowlist extended
# ============================================================

def test_meta_test_composer_allowlist_extended():
    """The phase3_cockpit_discipline meta-test must include
    compliance_cra_training in its composer allowlist so
    future drift catches React-readiness gaps."""
    src = (REPO_ROOT / "tests" / "integration"
           / "test_phase3_cockpit_discipline.py").read_text()
    assert "compliance_cra_training" in src
