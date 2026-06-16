"""Phase 4-3 — collateral link recomputes coverage + classification on the case."""
import sys, types
for _n in ("streamlit", "plotly", "plotly.express", "plotly.graph_objects",
           "plotly.subplots", "plotly.io"):
    if _n not in sys.modules:
        _m = types.ModuleType(_n)
        if _n == "streamlit":
            _m.cache_data = lambda *a, **k: (lambda f: f)
            _m.cache_resource = lambda *a, **k: (lambda f: f)
            _m.session_state = {}
        sys.modules[_n] = _m


def _mgr_with_case(amount_kes):
    from utils.core import CreditAdminManager
    cam = CreditAdminManager.__new__(CreditAdminManager)
    cam.cases = [{"id": "CALMS00001", "amount_kes": amount_kes, "amount": amount_kes,
                  "security_subtype": None, "conditions": [], "linked_collateral": []}]
    cam.save = lambda: None
    return cam


def test_link_recomputes_partial_then_full():
    cam = _mgr_with_case(100_000_000)
    # Residential 125% required. Link 120M FSV -> 1.20 -> partially.
    assert cam.link_collateral("CALMS00001", "COL1", "Residential Property",
                               forced_sale_value=120_000_000) is True
    case = cam.cases[0]
    assert case["coverage_ratio"] == 1.20
    assert case["required_ratio"] == 1.25
    assert case["security_classification"] == "partially_secured"

    # Link more -> 130M total / 100M = 1.30 -> fully (>=1.25, <=1.5625)
    cam.link_collateral("CALMS00001", "COL2", "Residential Property",
                        forced_sale_value=10_000_000)
    assert cam.cases[0]["coverage_ratio"] == 1.30
    assert cam.cases[0]["security_classification"] == "fully_secured"


def test_unlink_recomputes_to_unsecured():
    cam = _mgr_with_case(100_000_000)
    cam.link_collateral("CALMS00001", "COL1", "Motor Vehicle", forced_sale_value=130_000_000)
    assert cam.cases[0]["security_classification"] == "fully_secured"
    assert cam.unlink_collateral("CALMS00001", "COL1") is True
    assert cam.cases[0]["coverage_ratio"] == 0.0
    assert cam.cases[0]["security_classification"] == "unsecured"
    # unlink unknown -> False
    assert cam.unlink_collateral("CALMS00001", "NOPE") is False
