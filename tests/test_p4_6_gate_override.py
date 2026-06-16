"""Phase 4-6 — disbursement hard-gate + tiered override."""
import sys, types, datetime as dt
for _n in ("streamlit", "plotly", "plotly.express", "plotly.graph_objects",
           "plotly.subplots", "plotly.io"):
    if _n not in sys.modules:
        _m = types.ModuleType(_n)
        if _n == "streamlit":
            _m.cache_data = lambda *a, **k: (lambda f: f)
            _m.cache_resource = lambda *a, **k: (lambda f: f)
            _m.session_state = {}
        sys.modules[_n] = _m


def _mgr(case):
    from utils.core import CreditAdminManager
    cam = CreditAdminManager.__new__(CreditAdminManager)
    cam.cases = [case]
    cam.save = lambda: None
    return cam


def _fully_ready_secured(amount_kes=5_000_000):
    """A secured case that should PASS the gate."""
    future = (dt.date.today() + dt.timedelta(days=300)).isoformat()
    return {
        "id": "CALMS1", "facility_security_type": "secured",
        "amount_kes": amount_kes, "amount": amount_kes,
        "conditions": [],  # no outstanding CP
        "security_classification": "fully_secured",
        "coverage_ratio": 1.6, "required_ratio": 1.5,
        "legal_review": {"outcome": "approved"},
        "security_perfections": [{"id": "P1", "perfection_status": "perfected"}],
        "insurance_policies": [{"id": "I1", "status": "active",
                                "bank_interest_noted": True, "expiry_date": future}],
        "linked_collateral": [{"collateral_id": "C1", "collateral_type": "Debenture"}],
    }


def test_unsecured_only_checks_cp():
    from utils.core import CreditAdminManager
    case = {"id": "U1", "facility_security_type": "unsecured",
            "conditions": [{"type": "CRB", "fulfilled": False}]}
    cam = _mgr(case)
    g = cam.evaluate_disbursement_gate(case)
    assert g["passed"] is False
    assert [f["check"] for f in g["failures"]] == ["conditions_precedent"]
    # fulfil -> passes
    case["conditions"][0]["fulfilled"] = True
    assert cam.evaluate_disbursement_gate(case)["passed"] is True


def test_secured_ready_passes():
    cam = _mgr(_fully_ready_secured())
    g = cam.evaluate_disbursement_gate(cam.cases[0])
    assert g["passed"] is True, g["failures"]


def test_secured_missing_each_requirement_blocks():
    cam = _mgr(_fully_ready_secured())
    case = cam.cases[0]
    # break legal
    case["legal_review"] = {"outcome": None}
    checks = {f["check"] for f in cam.evaluate_disbursement_gate(case)["failures"]}
    assert "legal_review" in checks
    case["legal_review"] = {"outcome": "approved"}
    # break perfection
    case["security_perfections"] = [{"id": "P1", "perfection_status": "unperfected"}]
    assert "security_perfection" in {f["check"] for f in cam.evaluate_disbursement_gate(case)["failures"]}
    case["security_perfections"] = [{"id": "P1", "perfection_status": "perfected"}]
    # break coverage
    case["security_classification"] = "partially_secured"
    assert "coverage" in {f["check"] for f in cam.evaluate_disbursement_gate(case)["failures"]}


def test_standard_override_single_authority_unblocks():
    cam = _mgr(_fully_ready_secured(amount_kes=5_000_000))  # below HV threshold
    case = cam.cases[0]
    case["legal_review"] = {"outcome": None}   # force a failure
    g = cam.evaluate_disbursement_gate(case)
    assert g["passed"] is False
    cam.request_perfection_override("CALMS1", "mgr1", "client deadline; charge in progress",
                                    g["failures"])
    res = cam.add_override_approval("CALMS1", "cro", "cro_user")  # single authority
    assert res["status"] == "authorized"
    g2 = cam.evaluate_disbursement_gate(case)
    assert g2["passed"] is True and g2["overridden"] is True


def test_high_value_override_needs_all_three():
    cam = _mgr(_fully_ready_secured(amount_kes=150_000_000))  # >= HV threshold
    case = cam.cases[0]
    case["legal_review"] = {"outcome": None}
    g = cam.evaluate_disbursement_gate(case)
    cam.request_perfection_override("CALMS1", "mgr1", "board pressure", g["failures"])
    assert cam.add_override_approval("CALMS1", "head_of_credit", "hoc")["status"] == "pending"
    assert cam.add_override_approval("CALMS1", "cro", "cro")["status"] == "pending"
    r = cam.add_override_approval("CALMS1", "md", "md")
    assert r["status"] == "authorized"
    assert cam.evaluate_disbursement_gate(case)["overridden"] is True


def test_admin_override_satisfies_any_tier():
    cam = _mgr(_fully_ready_secured(amount_kes=150_000_000))  # high value
    case = cam.cases[0]
    case["legal_review"] = {"outcome": None}
    g = cam.evaluate_disbursement_gate(case)
    cam.request_perfection_override("CALMS1", "mgr1", "regulator deadline", g["failures"])
    # single admin approval authorizes even a high-value facility (pilot superuser)
    res = cam.add_override_approval("CALMS1", "admin", "william001")
    assert res["status"] == "authorized"
    assert cam.evaluate_disbursement_gate(case)["overridden"] is True
