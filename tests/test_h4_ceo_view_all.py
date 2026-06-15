"""H4 — CEO/MD all-deals visibility. The canonical top role
('Chief Executive & Managing Director') must be in _ALL_VIEW_ROLES."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def test_ceo_role_in_all_view_roles():
    src = (ROOT / "utils" / "core.py").read_text(encoding="utf-8")
    assert '"chief executive & managing director"' in src

def test_behavioral_all_view():
    from utils.core import _ALL_VIEW_ROLES
    assert "chief executive & managing director" in _ALL_VIEW_ROLES
    assert "managing director" in _ALL_VIEW_ROLES
    assert "branch manager" not in _ALL_VIEW_ROLES
