"""Batch B6 — register branch test logins self-heal like the canonical set.

The canonical role logins are restored on every UserManager init; the register
branch chain (300xxx) was not, so any users.json reset wiped them while the
canonical set returned (only william worked). Now they self-heal too.
"""
from utils.test_logins import branch_test_logins
from utils.core import UserManager


def test_branch_list_shape_and_scope():
    chain = branch_test_logins()
    assert len(chain) == 11
    # password convention EcoStaff + last-4 of staff_code
    for uname, pw, full, role, code, unit, region, cva in chain:
        assert pw == "EcoStaff" + code[-4:]
    # only the register root (CEO) is all-view; every other level is scoped
    allview = [u for (u, p, f, r, c, un, rg, cva) in chain if cva]
    assert allview == ["william0001"]


def test_self_heal_restores_missing_branch_account():
    um = UserManager()                      # init already self-heals
    assert "immaculate0716" in um.users      # present after init
    um.users.pop("immaculate0716", None)     # simulate a wipe
    restored = um.ensure_branch_test_logins()
    assert restored >= 1
    assert "immaculate0716" in um.users
    assert um.users["immaculate0716"].get("staff_code") == "300716"
    # and it authenticates
    ok, _ = um.authenticate("immaculate0716", "EcoStaff0716")
    assert ok is True
