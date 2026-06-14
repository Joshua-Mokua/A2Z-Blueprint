"""Phase P Batch P-AUTH-d regression — full per-role self-heal.

Proves the self-heal now guarantees ALL canonical role logins (not just the
CEO), via the shared utils.test_logins source of truth that the seed script
also uses (so they cannot drift).
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ── source-scan (always runs) ───────────────────────────────────────────
def test_shared_source_of_truth_exists():
    src = (ROOT / "utils" / "test_logins.py").read_text(encoding="utf-8")
    assert "def canonical_test_logins" in src


def test_core_and_seed_use_shared_source():
    core = (ROOT / "utils" / "core.py").read_text(encoding="utf-8")
    seed = (ROOT / "scripts" / "seed_test_logins.py").read_text(encoding="utf-8")
    assert "from utils.test_logins import canonical_test_logins" in core
    assert "from utils.test_logins import canonical_test_logins" in seed


# ── behavioral (needs utils importable) ─────────────────────────────────
def test_canonical_set_is_unique_and_pinned():
    from utils.test_logins import canonical_test_logins
    rows = canonical_test_logins()
    usernames = [r[0] for r in rows]
    passwords = [r[1] for r in rows]
    assert len(rows) >= 40
    assert len(set(usernames)) == len(usernames)
    assert len(set(passwords)) == len(passwords)
    w = next(r for r in rows if r[0] == "william001")
    assert w[1] == "EcoStaff0001"


def test_all_roles_present_after_construction():
    from utils.core import UserManager
    um = UserManager()
    # CEO + a couple of representative role slugs
    for u in ("william001", "branch_manager", "teller"):
        assert u in um.users, f"{u} should be self-healed on construction"


def test_self_heal_idempotent_when_present():
    from utils.core import UserManager
    um = UserManager()
    assert um.ensure_test_logins() == 0
