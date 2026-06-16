"""Phase 4-5 — Security Perfection + Insurance workflows + gate helpers."""
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


def _mgr(secured=True):
    from utils.core import CreditAdminManager
    cam = CreditAdminManager.__new__(CreditAdminManager)
    cam.cases = [{"id": "CALMS00001",
                  "facility_security_type": "secured" if secured else "unsecured"}]
    cam.save = lambda: None
    return cam


def test_perfection_add_update_and_gate():
    from utils.core import CreditAdminManager
    cam = _mgr()
    case = cam.cases[0]
    # secured, no perfection yet -> blocks
    assert CreditAdminManager.perfection_blocks_disbursement(case) is True
    pid = cam.add_security_perfection("CALMS00001", "Debenture",
                                      registration_reference="CR/12345")
    assert pid
    # still unperfected -> blocks
    assert CreditAdminManager.perfection_blocks_disbursement(case) is True
    # mark registered + perfected -> clears
    assert cam.update_security_perfection("CALMS00001", pid,
                                          registration_status="registered",
                                          perfection_status="perfected") is True
    assert CreditAdminManager.perfection_blocks_disbursement(case) is False
    # invalid status rejected
    assert cam.update_security_perfection("CALMS00001", pid,
                                          perfection_status="bogus") is False


def test_perfection_never_blocks_unsecured():
    from utils.core import CreditAdminManager
    cam = _mgr(secured=False)
    assert CreditAdminManager.perfection_blocks_disbursement(cam.cases[0]) is False


def test_insurance_validity_and_gate():
    from utils.core import CreditAdminManager
    cam = _mgr()
    case = cam.cases[0]
    future = (dt.date.today() + dt.timedelta(days=200)).isoformat()
    past = (dt.date.today() - dt.timedelta(days=5)).isoformat()

    # no policy -> required gate blocks
    assert CreditAdminManager.insurance_blocks_disbursement(case, required=True) is True
    # add a policy but bank interest NOT noted -> still invalid
    cam.add_insurance_policy("CALMS00001", "Jubilee", "POL1",
                             expiry_date=future, bank_interest_noted=False)
    assert CreditAdminManager.has_valid_insurance(case) is False
    # note bank interest -> valid
    iid = case["insurance_policies"][0]["id"]
    cam.update_insurance_policy("CALMS00001", iid, bank_interest_noted=True)
    assert CreditAdminManager.has_valid_insurance(case) is True
    assert CreditAdminManager.insurance_blocks_disbursement(case, required=True) is False

    # expired policy -> invalid again
    cam.update_insurance_policy("CALMS00001", iid, expiry_date=past)
    assert CreditAdminManager.has_valid_insurance(case) is False
    # required=False -> never blocks regardless
    assert CreditAdminManager.insurance_blocks_disbursement(case, required=False) is False


def test_insurance_never_blocks_unsecured():
    from utils.core import CreditAdminManager
    cam = _mgr(secured=False)
    assert CreditAdminManager.insurance_blocks_disbursement(cam.cases[0], required=True) is False
