"""Batch B2 — register-driven branch-head scope.

A branch head sees everyone in their OWN branch Unit (resolved from the staff
register by staff_code), bounded to that single Unit. Proves:
  - a branch head is scoped to exactly their branch (no cross-branch leakage),
  - two different branch heads see two different branches,
  - a non-branch-head (Teller) stays self-only,
  - an Area Manager is NOT branch-scoped (the 1203-staff over-scope is avoided).
"""
import pandas as pd
from utils.core_audit import get_visible_staff


def _scores():
    return pd.DataFrame([
        {"Staff Name": "Immaculate Njoroge", "Role": "Senior Branch Manager", "Unit": "Thika", "Region": "Mt Kenya West"},
        {"Staff Name": "Oscar Abdullahi", "Role": "Teller", "Unit": "Thika", "Region": "Mt Kenya West"},
        {"Staff Name": "Gilbert Wanjala", "Role": "Customer Service Officer", "Unit": "Thika", "Region": "Mt Kenya West"},
        {"Staff Name": "KenAv Head", "Role": "Senior Branch Manager", "Unit": "Kenyatta Avenue", "Region": "Nairobi CBD"},
        {"Staff Name": "KenAv Teller", "Role": "Teller", "Unit": "Kenyatta Avenue", "Region": "Nairobi CBD"},
        {"Staff Name": "Beatrice Musyoka", "Role": "Area Manager", "Unit": "Head Office", "Region": "Head Office"},
    ])


def test_branch_head_sees_only_own_branch():
    user = {"role": "Senior Branch Manager", "staff_code": "300716",
            "full_name": "Immaculate Njoroge", "unit": "Thika"}
    out = get_visible_staff(user, _scores())
    assert set(out["Unit"]) == {"Thika"}              # bounded to one branch
    assert "KenAv Head" not in set(out["Staff Name"])  # no cross-branch leakage


def test_two_branch_heads_see_different_branches():
    thika = get_visible_staff(
        {"role": "Senior Branch Manager", "staff_code": "300716",
         "full_name": "Immaculate Njoroge", "unit": "Thika"}, _scores())
    kenav = get_visible_staff(
        {"role": "Senior Branch Manager", "staff_code": "300226",
         "full_name": "KenAv Head", "unit": "Kenyatta Avenue"}, _scores())
    assert set(thika["Unit"]) == {"Thika"}
    assert set(kenav["Unit"]) == {"Kenyatta Avenue"}


def test_teller_stays_self_only():
    out = get_visible_staff(
        {"role": "Teller", "staff_code": "300720",
         "full_name": "Oscar Abdullahi", "unit": "Thika"}, _scores())
    assert set(out["Staff Name"]) == {"Oscar Abdullahi"}


def test_area_manager_not_branch_scoped():
    # Must NOT pull the whole branch network (the 1203-staff over-scope).
    out = get_visible_staff(
        {"role": "Area Manager", "staff_code": "301501",
         "full_name": "Beatrice Musyoka", "unit": "Head Office"}, _scores())
    assert len(out) < len(_scores())          # not all-view
    assert set(out["Staff Name"]) <= {"Beatrice Musyoka"}  # self-only fallback
