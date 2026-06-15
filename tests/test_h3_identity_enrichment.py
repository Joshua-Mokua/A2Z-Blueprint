"""Hardening Batch H3 — get_current_user identity enrichment.

Root cause of "deal created but not visible": get_current_user returned only
JWT claims (no staff_code), so get_visible_staff_codes computed an EMPTY
visible set and the creator's own deal was out-of-scope (404, absent from
list + queues). H3 enriches the user dict from users.json so every consumer
of identity (scope, create, queues) gets the real staff_code/full_name.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ── source-scan (always runs) ───────────────────────────────────────────
def test_get_current_user_enriches_identity():
    src = (ROOT / "utils" / "auth_jwt.py").read_text(encoding="utf-8")
    assert "def _enrich_identity_from_store" in src
    assert "_enrich_identity_from_store(user)" in src, "must be called in get_current_user"


# ── behavioral (needs utils importable) ─────────────────────────────────
def test_enrichment_fills_staff_code_for_known_user():
    from utils.auth_jwt import _enrich_identity_from_store
    u = {"username": "william001", "role": "Chief Executive & Managing Director",
         "scope": "full"}
    _enrich_identity_from_store(u)
    assert u.get("staff_code"), "william001 staff_code must be filled from users.json"
    # role (a JWT claim) must NOT be overwritten
    assert u["role"] == "Chief Executive & Managing Director"


def test_enrichment_is_safe_for_unknown_user():
    from utils.auth_jwt import _enrich_identity_from_store
    u = {"username": "no_such_user_xyz", "role": "X", "scope": "full"}
    _enrich_identity_from_store(u)         # must not raise
    assert "staff_code" not in u or not u["staff_code"]
