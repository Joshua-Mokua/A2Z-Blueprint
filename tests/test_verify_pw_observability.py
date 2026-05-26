"""tests/test_verify_pw_observability.py — Verify the envelope INFO log
actually fires.

Phase 1 Batch 3c shipped a multi-path verify_pw with an INFO log on the
envelope-success path. The Batch 3c verification at commit 216171d did
NOT confirm the log actually emits, because the test user available
(`william001`) had a direct-bcrypt hash, not envelope, so the envelope
path was never entered.

This test closes that observability gap:
  1. Manufactures an envelope-wrapped hash directly (no users.json
     dependency), passes it through verify_pw, and asserts the
     INFO log fires with the username.
  2. Manufactures a direct-bcrypt hash, passes it through verify_pw,
     and asserts the INFO log does NOT fire (no log noise on the
     common path).
  3. Manufactures a failing verification, and asserts the INFO log
     does NOT fire (envelope log is only for success).

The envelope INFO log is the observability signal Phase 2 will use to
plan retirement of the envelope verify path — when the log no longer
fires in production, the envelope branch is dead code and can be
removed. Without this signal, Phase 2 has no measurement.

CGR1 doctrine: envelope is a TRANSITIONAL stabilization layer. This
test guards the observability mechanism that supports the eventual
transition off envelope.

USAGE:
    cd <repo root>
    python -m pytest tests/test_verify_pw_observability.py -v

Or as part of the full test suite:
    python -m pytest tests/ -v
"""
from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# conftest.py installs the streamlit stub at collection time, so this
# import succeeds even without real streamlit.
from utils.core import UserManager


# ── Helper: build envelope-wrapped hash for a known password ────────────
# Mirrors what scripts/verify_bcrypt.py does internally during --upgrade,
# without touching the filesystem.
def _envelope_wrap(plaintext: str) -> str:
    import bcrypt as _bc
    sha_hex = hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
    return _bc.hashpw(sha_hex.encode("utf-8"), _bc.gensalt(rounds=12)) \
              .decode("utf-8")


def _direct_bcrypt(plaintext: str) -> str:
    import bcrypt as _bc
    return _bc.hashpw(plaintext.encode("utf-8"), _bc.gensalt(rounds=12)) \
              .decode("utf-8")


# ── The logger name the production code emits under ────────────────────
# utils/core.py uses `logger = logging.getLogger("a2z.core")` at module top.
# We attach our capture handler to that specific logger name.
_CORE_LOGGER_NAME = "a2z.core"


@pytest.fixture
def captured_logs():
    """Capture INFO+ records from the utils.core logger.

    Yields a list that will be populated with LogRecord instances during
    the test. The fixture installs a handler at INFO level and removes
    it afterwards, leaving the logger configuration unchanged.
    """
    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _ListHandler(level=logging.INFO)
    handler.setLevel(logging.INFO)

    logger = logging.getLogger(_CORE_LOGGER_NAME)
    original_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(original_level)


# ── Tests ──────────────────────────────────────────────────────────────

def test_envelope_path_emits_info_log_with_username(captured_logs):
    """Envelope-verify success MUST emit an INFO log identifying the
    user — this is Phase 2's only signal for envelope-population
    decay tracking."""
    password = "EnvelopeTestPassword2026"
    envelope_hash = _envelope_wrap(password)

    um = UserManager()
    result = um.verify_pw(password, envelope_hash, username="envelope_user")

    assert result is True, (
        "Envelope verify should succeed against an envelope-wrapped hash. "
        "If this fails, verify_pw's path-2 (envelope) is broken."
    )

    envelope_records = [
        r for r in captured_logs
        if "Envelope-backed credential authenticated" in r.getMessage()
    ]
    assert len(envelope_records) == 1, (
        f"Expected exactly 1 envelope INFO log, got {len(envelope_records)}. "
        f"All captured records: {[r.getMessage() for r in captured_logs]}"
    )

    msg = envelope_records[0].getMessage()
    assert "envelope_user" in msg, (
        f"Envelope INFO log should identify the user. Got: {msg!r}"
    )
    assert envelope_records[0].levelno == logging.INFO, (
        f"Expected INFO level, got {envelope_records[0].levelname}"
    )


def test_envelope_path_emits_info_log_without_username(captured_logs):
    """When verify_pw is called without a username kwarg, the log still
    fires — just without the user identifier. Backward-compat call sites
    that don't pass username retain their behavior."""
    password = "AnotherEnvelopeTest2026"
    envelope_hash = _envelope_wrap(password)

    um = UserManager()
    result = um.verify_pw(password, envelope_hash)

    assert result is True
    envelope_records = [
        r for r in captured_logs
        if "Envelope-backed credential authenticated" in r.getMessage()
    ]
    assert len(envelope_records) == 1


def test_direct_bcrypt_does_NOT_emit_envelope_log(captured_logs):
    """Direct-bcrypt verify success must be QUIET — the envelope INFO log
    is reserved for the envelope path only. If direct bcrypt also fired
    the log, the signal would lose meaning (every successful login would
    log, making envelope-vs-direct ratio unobservable)."""
    password = "DirectBcryptTest2026"
    direct_hash = _direct_bcrypt(password)

    um = UserManager()
    result = um.verify_pw(password, direct_hash, username="direct_user")

    assert result is True, "Direct bcrypt verify should succeed."

    envelope_records = [
        r for r in captured_logs
        if "Envelope-backed credential authenticated" in r.getMessage()
    ]
    assert len(envelope_records) == 0, (
        f"Direct bcrypt path should NOT emit envelope log. Got "
        f"{len(envelope_records)} envelope records: "
        f"{[r.getMessage() for r in envelope_records]}"
    )


def test_wrong_password_against_envelope_does_NOT_emit_log(captured_logs):
    """Failed verifies must be quiet too. The envelope log is success-
    only — emitting on failure would conflate signal and noise."""
    password = "CorrectPassword2026"
    envelope_hash = _envelope_wrap(password)

    um = UserManager()
    # Verify with WRONG password
    result = um.verify_pw("WrongPassword2026", envelope_hash, username="bob")

    assert result is False, "Wrong password should fail verification."

    envelope_records = [
        r for r in captured_logs
        if "Envelope-backed credential authenticated" in r.getMessage()
    ]
    assert len(envelope_records) == 0, (
        f"Failed verify should NOT emit envelope log. Got: "
        f"{[r.getMessage() for r in envelope_records]}"
    )


def test_wrong_password_against_direct_bcrypt_does_NOT_emit_log(captured_logs):
    """Symmetry check for the direct-bcrypt failure path."""
    password = "CorrectPassword2026"
    direct_hash = _direct_bcrypt(password)

    um = UserManager()
    result = um.verify_pw("WrongPassword2026", direct_hash, username="bob")

    assert result is False
    envelope_records = [
        r for r in captured_logs
        if "Envelope-backed credential authenticated" in r.getMessage()
    ]
    assert len(envelope_records) == 0
