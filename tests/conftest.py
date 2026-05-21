"""tests/conftest.py — pytest fixtures and import-time setup.

Stubs streamlit so utils.core (which imports streamlit at module top) can
be imported without the actual streamlit installed. This is necessary for
tests that touch core.py — production environments always have streamlit,
but isolated unit tests don't need its full feature set.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

import pytest


# ── Streamlit stub — runs at collection time ────────────────────────────
# Some modules (utils.core, pages/*) import streamlit at module top.
# For unit tests we don't need real streamlit — just enough surface for
# the imports to succeed. Real integration tests would deselect this stub.
def _install_streamlit_stub() -> None:
    if "streamlit" in sys.modules:
        return  # already real or already stubbed

    st = types.ModuleType("streamlit")

    class _Noop:
        def __init__(self, *_a, **_k): pass
        def __call__(self, *_a, **_k): return self
        def __getattr__(self, _n): return _Noop()
        def __enter__(self): return self
        def __exit__(self, *_a): return False

    # Common streamlit surface used by importers
    st.cache_data = lambda *a, **k: (lambda f: f)
    st.cache_resource = lambda *a, **k: (lambda f: f)
    st.session_state = {}
    st.markdown = st.write = st.error = st.success = st.info = st.warning = lambda *a, **k: None
    st.columns = lambda *a, **k: tuple(_Noop() for _ in range(int(a[0]) if a else 1))
    st.tabs = lambda labels, *a, **k: tuple(_Noop() for _ in labels)
    st.expander = st.container = st.empty = lambda *a, **k: _Noop()
    st.button = st.checkbox = lambda *a, **k: False
    st.text_input = st.text_area = st.selectbox = lambda *a, **k: ""
    st.dataframe = st.table = st.metric = st.json = lambda *a, **k: None
    sys.modules["streamlit"] = st


_install_streamlit_stub()


# ── Path setup ──────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


# ── Fixtures ────────────────────────────────────────────────────────────
@pytest.fixture
def tmp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fresh temporary data directory for any test that writes to disk.

    Patches utils.bsc_engine.DATA_DIR so the engine writes here instead of
    the real data/ folder. Also seeds a minimal kpi_library.json and
    users.json so validation has something to look up against.
    """
    import json as _json

    # Seed minimal users registry
    users = {
        "william001":   {"staff_code": "300001", "role": "Admin",   "active": True, "full_name": "William"},
        "jane002":      {"staff_code": "300002", "role": "Staff",   "active": True, "full_name": "Jane"},
        "manager003":   {"staff_code": "300003", "role": "Manager", "active": True, "full_name": "Mgr"},
    }
    (tmp_path / "users.json").write_text(_json.dumps(users))

    # Seed minimal kpi_library
    lib = {
        "pillars": [
            {"id": "Financial",        "weight": 0.4},
            {"id": "Customer Focus",   "weight": 0.25},
        ],
        "active_kpis": ["DEP_GROWTH", "LOAN_GROWTH"],
        "kpis": [
            {"id": "K001", "name": "Loans Disbursed",      "pillar": "Financial"},
            {"id": "K039", "name": "CIMS Tickets in SLA",  "pillar": "Operational Excellence"},
        ],
    }
    (tmp_path / "kpi_library.json").write_text(_json.dumps(lib))

    # Point the engine at our tmp dir
    import utils.bsc_engine as _bsc
    monkeypatch.setattr(_bsc, "DATA_DIR", tmp_path)
    # Force index reload so the new files are picked up
    _bsc._refresh_indexes()

    yield tmp_path

    # Cleanup: clear the engine's caches so the next test starts fresh
    _bsc._refresh_indexes()


@pytest.fixture
def jwt_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    """A deterministic JWT secret for auth tests. Sets A2Z_JWT_SECRET in
    the env BEFORE utils.auth_jwt is imported (the secret is resolved at
    import time)."""
    secret = "test_secret_for_unit_tests_only_xxxxxxxxxxxx"
    monkeypatch.setenv("A2Z_JWT_SECRET", secret)
    # Reload auth_jwt so the new secret takes effect
    if "utils.auth_jwt" in sys.modules:
        import importlib
        importlib.reload(sys.modules["utils.auth_jwt"])
    return secret
