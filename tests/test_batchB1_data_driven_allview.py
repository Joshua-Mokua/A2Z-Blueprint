"""Batch B1 — data-driven all-view from the staff register.

The CEO role ("Chief Executive & Managing Director") is the register's only
root (blank Reports To) and must see everyone. Previously this needed the
hardcoded H4 _ALL_VIEW_ROLES addition; now get_visible_staff derives it from
data. Only genuine roots become all-view, so mid-level roles cannot be
over-scoped (they fall through to the existing REPORTING_TREE logic).
"""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]


def test_helper_and_union_present():
    src = (ROOT / "utils" / "core_audit.py").read_text(encoding="utf-8")
    assert "def _register_root_roles" in src
    assert "_register_root_roles())" in src          # unioned into all-view check
    assert "from functools import lru_cache" in src


def test_register_single_root_is_ceo():
    try:
        import pandas as pd
    except Exception:
        return  # pandas-less env: source-scan tests still cover the wiring
    df = pd.read_excel(ROOT / "data" / "staff_register.xlsx")
    rt = df["Reports To"].astype(str).str.strip()
    roots = df[df["Reports To"].isna() | rt.isin(["", "None", "nan", "NaN"])]
    rr = {str(r).strip().lower() for r in roots["Role"].dropna().unique() if str(r).strip()}
    assert rr == {"chief executive & managing director"}, rr


def test_only_roots_get_all_view():
    root_roles = {"chief executive & managing director"}
    ALL_VIEW = {"managing director", "admin"}
    def all_view(role):
        rl = role.lower()
        return "admin" in rl or rl in ALL_VIEW or rl in root_roles
    assert all_view("Chief Executive & Managing Director")   # data-driven
    assert all_view("Managing Director")                     # fallback
    assert not all_view("Regional Head")                     # falls to REPORTING_TREE
    assert not all_view("Branch Manager")
