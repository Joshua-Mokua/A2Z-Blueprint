"""Phase P Batch P-AUTH-b regression — UserManager._load hardening.

Proves a corrupt/unreadable users.json is NEVER silently overwritten with
the 3 default accounts (the root cause that wiped the seeded test logins).

Behavioral tests construct a UserManager (reads the real DATA_DIR file
harmlessly) then redirect `users_file` to a tmp path and call _load directly.
A source-scan test guarantees the hardening markers stay present even in
environments where utils.core can't be imported.
"""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


# ── source-scan (always runs) ───────────────────────────────────────────
def test_load_no_longer_has_bare_silent_default_fallback():
    src = (ROOT / "utils" / "core.py").read_text(encoding="utf-8")
    assert "_backup_unreadable" in src, "hardened backup helper must exist"
    # the old silent pattern must be gone from _load
    assert "except:\n            return self._defaults()" not in src, (
        "the bare `except: return self._defaults()` in _load must be gone"
    )


# ── behavioral (needs utils.core importable) ────────────────────────────
def _um():
    from utils.core import UserManager
    return UserManager()


def test_corrupt_users_json_is_preserved_not_overwritten(tmp_path):
    um = _um()
    f = tmp_path / "users.json"
    f.write_text('{"william001": {"active": true},,,BROKEN', encoding="utf-8")
    um.users_file = f
    before = f.read_text(encoding="utf-8")
    with pytest.raises(RuntimeError):
        um._load()
    assert f.read_text(encoding="utf-8") == before, "corrupt file must be preserved"
    assert any(p.name.startswith("users.json.corrupt-") for p in tmp_path.iterdir()), \
        "a .corrupt-* backup must be written"


def test_empty_users_json_returns_defaults(tmp_path):
    um = _um()
    f = tmp_path / "users.json"
    f.write_text("   ", encoding="utf-8")
    um.users_file = f
    out = um._load()
    assert {"admin", "manager1", "staff1"}.issubset(out.keys())


def test_valid_users_json_real_accounts_survive(tmp_path):
    um = _um()
    f = tmp_path / "users.json"
    f.write_text(json.dumps({"william001": {"active": True}, "admin": {"x": 1}}),
                 encoding="utf-8")
    um.users_file = f
    out = um._load()
    assert "william001" in out, "real accounts must survive a normal load"
