"""Integration tests for v10.445 — Vital Signs Doctrine codification."""

import re
import sys
from pathlib import Path

import pytest

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


@pytest.fixture(scope="module")
def anatomy():
    from utils.body_health_engine import audit_anatomy
    return audit_anatomy()


@pytest.fixture(scope="module")
def vitals():
    from utils.body_health_engine import audit_vital_questions
    return audit_vital_questions()


def test_v10445_anatomy_map_has_ten_body_parts():
    from utils.body_health_engine import ANATOMY_MAP
    assert len(ANATOMY_MAP) >= 10


def test_v10445_anatomy_includes_three_revived():
    from utils.body_health_engine import ANATOMY_MAP
    revived = [m for m, meta in ANATOMY_MAP.items()
               if meta.get("status") == "revived"]
    assert "admin_module" in revived
    assert "hr_module" in revived
    assert "bsc_target_cascade" in revived


def test_v10445_anatomy_includes_six_awaiting_er():
    from utils.body_health_engine import ANATOMY_MAP
    pending = [m for m, meta in ANATOMY_MAP.items()
               if meta.get("status") == "awaiting_er"]
    for required in ("credit", "pipeline", "finance", "operations",
                     "risk_compliance", "crm_customer"):
        assert required in pending, f"Missing pending organ: {required}"


def test_v10445_er_queue_has_priorities():
    """Every awaiting_er entry must have er_priority set."""
    from utils.body_health_engine import ANATOMY_MAP
    for module, meta in ANATOMY_MAP.items():
        if meta.get("status") == "awaiting_er":
            assert meta.get("er_priority") is not None, (
                f"{module} missing er_priority"
            )


def test_v10445_credit_is_top_er_priority():
    """Credit = heart = #1 in ER queue (per doctrine)."""
    from utils.body_health_engine import ANATOMY_MAP
    assert ANATOMY_MAP["credit"]["er_priority"] == 1


def test_v10445_vital_questions_count_ten():
    from utils.body_health_engine import VITAL_QUESTIONS
    assert len(VITAL_QUESTIONS) == 10
    # IDs Q1 through Q10
    ids = [q["id"] for q in VITAL_QUESTIONS]
    assert ids == [f"Q{i}" for i in range(1, 11)]


def test_v10445_diagnostic_pillars_count_five():
    from utils.body_health_engine import DIAGNOSTIC_PILLARS
    assert len(DIAGNOSTIC_PILLARS) == 5
    ids = [p["id"] for p in DIAGNOSTIC_PILLARS]
    assert ids == ["P1", "P2", "P3", "P4", "P5"]


def test_v10445_anatomy_audit_runs(anatomy):
    assert anatomy.body_parts_total >= 10
    assert anatomy.revived >= 3
    assert anatomy.awaiting_er >= 6


def test_v10445_anatomy_revival_pct_reasonable(anatomy):
    """3 revived + 1 partial out of 10 = 35%."""
    assert 30.0 <= anatomy.revival_pct <= 50.0


def test_v10445_er_queue_sorted_by_priority(anatomy):
    priorities = [q["er_priority"] for q in anatomy.next_in_er]
    assert priorities == sorted(priorities)


def test_v10445_vital_questions_audit_runs(vitals):
    assert vitals.total == 10


def test_v10445_vital_questions_pass_floor(vitals):
    """At least 80% of vital questions should pass."""
    assert vitals.pct_passing >= 80.0


def test_v10445_organ_id_consistency():
    """Every ANATOMY_MAP revived entry's organ_id must exist in ORGAN_REGISTRY."""
    from utils.body_health_engine import ANATOMY_MAP, ORGAN_REGISTRY
    for module, meta in ANATOMY_MAP.items():
        if meta.get("status") == "revived" and meta.get("organ_id"):
            assert meta["organ_id"] in ORGAN_REGISTRY, (
                f"{module} -> {meta['organ_id']} not in ORGAN_REGISTRY"
            )


def test_v10445_g331_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    for k in list(sys.modules):
        if k.startswith("audit"):
            del sys.modules[k]
    from audit import gate_v10445_vital_signs_doctrine
    r = gate_v10445_vital_signs_doctrine()
    assert r["passed"], r.get("violations")
