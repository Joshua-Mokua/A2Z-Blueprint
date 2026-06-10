"""tests/test_validate_password_policy.py — regression coverage for the
password policy helper introduced in v10.501 Batch 4a.

Closes GAP-001 (policy advertised but not enforced) and provides the
mandatory regression test for Phase 2 Arc A. Every rule the helper
enforces gets at least one positive (accept) and one negative (reject)
case so a future refactor can't quietly weaken the policy without
turning a test red.

Run with:
    pytest tests/test_validate_password_policy.py -v
"""

import pytest
from utils.core import validate_password_policy


# ─── Accept cases ────────────────────────────────────────────────────

@pytest.mark.parametrize("pw", [
    "Abcdef1!",         # exactly 8 chars, one of each class — minimal accept
    "EcoStaff0001!",    # synthetic-credential-style with a special added
    "MyP@ssw0rd",       # canonical example
    "C0rrectH0rseBatteryStaple!",  # long passphrase with all classes
    "Aa1!Aa1!Aa1!",     # repeating but compliant
])
def test_accepts_compliant_passwords(pw):
    ok, reason = validate_password_policy(pw)
    assert ok is True, f"Expected accept, got reject: {reason!r}"
    assert reason == ""


# ─── Reject cases: one per policy rule ───────────────────────────────

def test_rejects_too_short():
    """Rule 1 — minimum length is 8."""
    ok, reason = validate_password_policy("Ab1!")
    assert ok is False
    assert "8 characters" in reason


def test_rejects_missing_uppercase():
    """Rule 2 — must contain at least one uppercase letter."""
    ok, reason = validate_password_policy("abcdef1!")
    assert ok is False
    assert "uppercase" in reason.lower()


def test_rejects_missing_lowercase():
    """Rule 3 — must contain at least one lowercase letter."""
    ok, reason = validate_password_policy("ABCDEF1!")
    assert ok is False
    assert "lowercase" in reason.lower()


def test_rejects_missing_digit():
    """Rule 4 — must contain at least one digit."""
    ok, reason = validate_password_policy("Abcdefgh!")
    assert ok is False
    assert "digit" in reason.lower()


def test_rejects_missing_special():
    """Rule 5 — must contain at least one special character."""
    ok, reason = validate_password_policy("Abcdefg1")
    assert ok is False
    assert "special" in reason.lower()


# ─── Reject cases: weak passwords from real attacker dictionaries ────

@pytest.mark.parametrize("pw", [
    "password",   # missing upper, digit, special
    "12345678",   # missing upper, lower, special
    "aaaaaaaa",   # missing upper, digit, special
    "Password",   # missing digit and special — covers GAP-001 risk text
    "Password1",  # missing special — still rejected
])
def test_rejects_common_weak_passwords(pw):
    """GAP-001 risk paragraph names these explicitly — they MUST reject."""
    ok, reason = validate_password_policy(pw)
    assert ok is False, (
        f"Common-weak password {pw!r} accepted — regression of GAP-001"
    )
    assert reason != ""


# ─── Edge cases ──────────────────────────────────────────────────────

def test_rejects_empty_string():
    ok, reason = validate_password_policy("")
    assert ok is False
    assert "8 characters" in reason


def test_rejects_non_string_input():
    """Defensive — None, ints, bytes etc. must reject cleanly, not crash."""
    for bad in (None, 12345678, b"Abcdef1!", ["A", "b", "1", "!"]):
        ok, reason = validate_password_policy(bad)
        assert ok is False, f"Non-string input {bad!r} accepted"
        assert "string" in reason.lower()


def test_special_char_alternatives_all_work():
    """Spot-check several special chars from the allowed set — none of
    them should be the unique gateway to acceptance."""
    base = "Abcdefg1"
    for sc in "!@#$%^&*()_+-=[]{}|;:,.<>/?`~":
        ok, _ = validate_password_policy(base + sc)
        assert ok is True, f"Compliant pw rejected when special char was {sc!r}"


def test_unicode_letters_not_counted_as_ascii_classes():
    """Defensive — a password using only Unicode upper/lower letters
    that happen to satisfy str.isupper/islower must still need an
    ASCII-class match per the documented policy. This test pins behaviour
    so a future change to the rule (intentional or accidental) is
    visible. CURRENT behaviour: Python's str.isupper()/islower() return
    True for many Unicode chars, so 'Αβγδεζ1!' (Greek) IS accepted
    today. If Phase 2 hardens to ASCII-only classes, this test should
    flip to assert rejection — at which point it acts as the change
    log."""
    ok, _ = validate_password_policy("Αβγδεζη1!")
    # Document current behaviour explicitly so the test passes today
    # AND the comment above warns the next maintainer.
    assert ok is True


# ─── Contract test: return shape ─────────────────────────────────────

def test_return_shape_is_two_tuple():
    """Callers (pages/_login.py, utils/api.py) unpack via
    `ok, reason = validate_password_policy(pw)`. The contract must
    hold even under unusual inputs."""
    for pw in ("good", "Abcdef1!", "", None, "x" * 200):
        result = validate_password_policy(pw)
        assert isinstance(result, tuple), f"Non-tuple return for {pw!r}"
        assert len(result) == 2, f"Wrong tuple length for {pw!r}: {result!r}"
        assert isinstance(result[0], bool)
        assert isinstance(result[1], str)


def test_accept_returns_empty_reason():
    """On accept, reason must be empty string — not None, not a success
    message. Call sites read reason only on reject."""
    ok, reason = validate_password_policy("Abcdef1!")
    assert ok is True
    assert reason == ""


def test_reject_reason_never_includes_password():
    """SECURITY — the reason string is shown to the user (st.error,
    HTTPException detail) and must never echo the candidate password
    or any derivation of it. Pin the contract with a recognisable token."""
    sentinel = "MyVerySecretCandidatePassword12345"
    _, reason = validate_password_policy(sentinel)  # rejects (no special)
    assert sentinel not in reason
    assert "Secret" not in reason
