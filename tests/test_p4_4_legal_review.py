"""Phase 4-4 — Legal Review workflow + gate helper."""
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


def _mgr(secured=True):
    from utils.core import CreditAdminManager
    cam = CreditAdminManager.__new__(CreditAdminManager)
    cam.cases = [{"id": "CALMS00001",
                  "facility_security_type": "secured" if secured else "unsecured"}]
    cam.save = lambda: None
    return cam


def test_legal_flow_assign_comment_outcome():
    from utils.core import CreditAdminManager
    cam = _mgr()
    assert cam.assign_legal_officer("CALMS00001", "LO001", "Jane Legal") is True
    lr = cam.cases[0]["legal_review"]
    assert lr["status"] == "in_review"
    assert lr["assigned_officer_code"] == "LO001"

    assert cam.add_legal_comment("CALMS00001", "LO001", "Need updated title", raises_query=True)
    assert cam.cases[0]["legal_review"]["status"] == "queries_raised"
    assert len(cam.cases[0]["legal_review"]["comments"]) == 1

    # empty comment rejected
    assert cam.add_legal_comment("CALMS00001", "LO001", "   ") is False

    assert cam.set_legal_outcome("CALMS00001", "approved_with_conditions", by="LO001")
    assert cam.cases[0]["legal_review"]["status"] == "cleared"
    assert cam.cases[0]["legal_review"]["outcome"] == "approved_with_conditions"

    # invalid outcome rejected
    assert cam.set_legal_outcome("CALMS00001", "maybe") is False


def test_legal_blocks_disbursement_for_secured_until_cleared():
    from utils.core import CreditAdminManager
    cam = _mgr(secured=True)
    case = cam.cases[0]
    # no legal review yet -> blocks
    assert CreditAdminManager.legal_blocks_disbursement(case) is True
    cam.assign_legal_officer("CALMS00001", "LO001")
    assert CreditAdminManager.legal_blocks_disbursement(case) is True  # in_review, no outcome
    cam.set_legal_outcome("CALMS00001", "rejected")
    assert CreditAdminManager.legal_blocks_disbursement(case) is True  # rejected still blocks
    cam.set_legal_outcome("CALMS00001", "approved")
    assert CreditAdminManager.legal_blocks_disbursement(case) is False  # cleared


def test_legal_never_blocks_unsecured():
    from utils.core import CreditAdminManager
    cam = _mgr(secured=False)
    assert CreditAdminManager.legal_blocks_disbursement(cam.cases[0]) is False
