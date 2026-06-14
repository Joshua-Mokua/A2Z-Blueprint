"""Phase P Batch P-AUTH-c regression — login resilience.

Proves (1) DATA_DIR is an absolute, CWD-independent path, so the launch
folder can never again decide which users.json is used, and (2) the
UserManager self-heal guarantees the canonical CEO test login exists after
construction and is a zero-write no-op when already present.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ── source-scan (always runs) ───────────────────────────────────────────
def test_data_dir_anchored_to_file_not_cwd():
    src = (ROOT / "utils" / "core.py").read_text(encoding="utf-8")
    assert 'DATA_DIR = (Path(__file__).resolve().parent.parent / "data")' in src, \
        "DATA_DIR must be anchored to core.py's location, not the CWD"
    assert 'DATA_DIR = Path("data")' not in src, "the relative DATA_DIR must be gone"


def test_self_heal_present_and_called():
    src = (ROOT / "utils" / "core.py").read_text(encoding="utf-8")
    assert "def ensure_test_logins" in src
    assert "self.ensure_test_logins()" in src, "must be called from __init__"
    assert "william001" in src, "canonical CEO login must be defined"


# ── behavioral (needs utils.core importable) ────────────────────────────
def test_data_dir_is_absolute():
    from utils.core import DATA_DIR
    assert DATA_DIR.is_absolute()
    assert DATA_DIR.name == "data"


def test_canonical_login_present_after_construction():
    from utils.core import UserManager
    um = UserManager()
    assert "william001" in um.users
    assert um.users["william001"]["active"] is True
    assert um.users["william001"].get("must_change_password") is False


def test_ensure_test_logins_idempotent_when_present():
    from utils.core import UserManager
    um = UserManager()
    assert um.ensure_test_logins() == 0  # already present -> no restore


def test_ensure_test_logins_restores_when_missing():
    from utils.core import UserManager
    um = UserManager()
    um.users.pop("william001", None)
    assert um.ensure_test_logins() == 1
    assert "william001" in um.users
