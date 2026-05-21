"""A2Z MIS 360 test suite.

Tests are organised by the unit they exercise:
  test_bsc_engine.py   — utils/bsc_engine.py (Standards #1+#2)
  test_auth_jwt.py     — utils/auth_jwt.py (V-001 mitigation)
  test_audit_smoke.py  — meta-test that scripts/audit.py runs and reports 12/12
  test_helpers.py      — small targeted tests for translation helpers, etc.

Conventions:
  - Tests are pure pytest (no unittest classes) unless grouping makes sense.
  - Tests for security-critical code (auth, password hashing, SQL safety,
    XSS safety) carry the @pytest.mark.security marker.
  - Tests that need a tmp data directory use the `tmp_data_dir` fixture
    from conftest.py rather than mutating ./data.
  - Tests do NOT import streamlit. If a tested module imports streamlit
    at module top, conftest stubs it out before collection.
"""
