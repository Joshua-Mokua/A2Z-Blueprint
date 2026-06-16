"""Phase 4-2 — CP/CS first-class objects + facility classification.

Tests the pure CreditAdminManager logic without DB/streamlit by constructing a
manager and operating on an in-memory case (the manager stores cases in a list).
"""
import sys, types

# Stub heavy optional deps before importing core (core imports them at load).
for _name in ("streamlit", "plotly", "plotly.express", "plotly.graph_objects",
              "plotly.subplots", "plotly.io"):
    if _name not in sys.modules:
        _m = types.ModuleType(_name)
        if _name == "streamlit":
            _m.cache_data = lambda *a, **k: (lambda f: f)
            _m.cache_resource = lambda *a, **k: (lambda f: f)
            _m.session_state = {}
        sys.modules[_name] = _m


def _make_case():
    return {
        "id": "CALMS00001",
        "conditions": [
            {"type": "Legal charge",  "fulfilled": False, "classification": "precedent", "mandatory": True},
            {"type": "Title deed registration", "fulfilled": False, "classification": "precedent", "mandatory": True},
            {"type": "Insurance certificate", "fulfilled": False, "classification": "precedent", "mandatory": True},
        ],
        "facility_security_type": "unsecured",
    }


def test_outstanding_mandatory_cp_static_helper():
    from utils.core import CreditAdminManager
    case = _make_case()
    out = CreditAdminManager.outstanding_mandatory_cp(case)
    assert set(out) == {"Legal charge", "Title deed registration", "Insurance certificate"}

    # Fulfil one -> drops out of the outstanding list
    case["conditions"][0]["fulfilled"] = True
    out = CreditAdminManager.outstanding_mandatory_cp(case)
    assert "Legal charge" not in out and len(out) == 2

    # Reclassify one to subsequent -> never blocks (drops out even if unfulfilled)
    case["conditions"][1]["classification"] = "subsequent"
    out = CreditAdminManager.outstanding_mandatory_cp(case)
    assert "Title deed registration" not in out and out == ["Insurance certificate"]

    # Non-mandatory CP -> doesn't block either
    case["conditions"][2]["mandatory"] = False
    out = CreditAdminManager.outstanding_mandatory_cp(case)
    assert out == []


def test_outstanding_defaults_safe_when_fields_absent():
    """Legacy conditions without classification/mandatory default to mandatory
    precedent (safe — they block until classified)."""
    from utils.core import CreditAdminManager
    case = {"conditions": [{"type": "Board resolution", "fulfilled": False}]}
    out = CreditAdminManager.outstanding_mandatory_cp(case)
    assert out == ["Board resolution"]


def test_classify_condition_mutates_in_place():
    from utils.core import CreditAdminManager
    cam = CreditAdminManager.__new__(CreditAdminManager)   # bypass __init__/IO
    cam.cases = [_make_case()]
    cam.save = lambda: None                                # no-op persistence

    assert cam.classify_condition("CALMS00001", "Legal charge",
                                  classification="subsequent", mandatory=False,
                                  due_date="2026-12-31") is True
    cond = cam.cases[0]["conditions"][0]
    assert cond["classification"] == "subsequent"
    assert cond["mandatory"] is False
    assert cond["due_date"] == "2026-12-31"

    # bad classification rejected
    assert cam.classify_condition("CALMS00001", "Legal charge",
                                  classification="bogus") is False
    # unknown condition rejected
    assert cam.classify_condition("CALMS00001", "No Such Condition",
                                  classification="precedent") is False


def test_set_facility_classification():
    from utils.core import CreditAdminManager
    cam = CreditAdminManager.__new__(CreditAdminManager)
    cam.cases = [_make_case()]
    cam.save = lambda: None

    assert cam.set_facility_classification("CALMS00001", "secured", "debenture") is True
    assert cam.cases[0]["facility_security_type"] == "secured"
    assert cam.cases[0]["security_subtype"] == "debenture"

    # invalid type rejected
    assert cam.set_facility_classification("CALMS00001", "kinda-secured") is False
