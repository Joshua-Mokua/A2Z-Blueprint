"""Batch B24 — runtime defect caught by simulation.

The B19-B21 LMS workflow endpoints called is_app_in_scope(app, user) — passing
the user dict where a Set of visible codes was expected — so every offer-loop,
confirm and committee call 403'd for legitimate owners/managers. This test
guards the corrected 3-arg call signature with admin bypass.
"""
from pathlib import Path


def test_no_wrong_signature_scope_calls_remain():
    src = (Path(__file__).resolve().parent.parent / "utils" / "api_lms_routes.py").read_text(encoding="utf-8")
    assert "is_app_in_scope(app, user)" not in src, \
        "wrong 2-arg is_app_in_scope(app, user) call must not exist"


def test_workflow_endpoints_use_visible_codes_and_admin_bypass():
    src = (Path(__file__).resolve().parent.parent / "utils" / "api_lms_routes.py").read_text(encoding="utf-8")
    # the corrected form computes visible codes + bypasses for admin
    assert "app, get_visible_staff_codes(user), str(user.get('staff_code', '') or '')" in src
    assert src.count("not user.get('is_admin') and not is_app_in_scope(") >= 8
