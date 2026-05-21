"""Integration tests for v10.344 — Page smoke-test suite (Option C).

12 tests across 4 sections:
  Section 1 — Streamlit mock mechanics (4 tests)
  Section 2 — Smoke engine API (3 tests)
  Section 3 — Full smoke run results (3 tests)
  Section 4 — G231 audit gate (2 tests)
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Streamlit mock
# ────────────────────────────────────────────────────────────────────

def test_v10344_mock_installs_and_uninstalls():
    """install() injects mock streamlit; uninstall() removes it."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install, uninstall, is_installed
    install()
    assert is_installed()
    import streamlit as st
    assert hasattr(st, "_is_a2z_mock") and st._is_a2z_mock
    uninstall()
    assert not is_installed()


def test_v10344_mock_session_state_supports_dict_and_attr():
    """session_state works as both dict and namespace."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    import streamlit as st
    st.session_state["foo"] = "bar"
    assert st.session_state["foo"] == "bar"
    assert st.session_state.foo == "bar"
    # Default keys present
    assert st.session_state.get("user")
    assert st.session_state.get("logged_in") is True


def test_v10344_mock_proxy_is_callable_and_coercible():
    """MockProxy supports calls, attribute access, int/float/str coercion."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    import streamlit as st
    btn = st.button("X")
    assert btn.some_attr() is not None
    # Coercions used in real page code like int(st.slider(...))
    proxy = st.slider("X", 0, 100)
    assert int(proxy) == 0
    assert float(proxy) == 0.0
    assert str(proxy) == ""
    assert not bool(proxy)


def test_v10344_mock_columns_returns_proxy_list():
    """st.columns(3) returns 3 proxies (unpackable as c1, c2, c3 = ...)."""
    _reimport("streamlit")
    from tests.helpers.streamlit_mock import install
    install()
    import streamlit as st
    cols = st.columns(3)
    assert len(cols) == 3
    c1, c2, c3 = st.columns(3)
    assert c1 is not None and c2 is not None and c3 is not None


# ────────────────────────────────────────────────────────────────────
# Section 2 — Smoke engine API
# ────────────────────────────────────────────────────────────────────

def test_v10344_smoke_engine_imports():
    """utils/page_smoke.py has the public surface."""
    _reimport("utils.page_smoke")
    import utils.page_smoke as psm
    assert hasattr(psm, "smoke_test_all")
    assert hasattr(psm, "smoke_test_page")
    assert hasattr(psm, "format_summary")


def test_v10344_smoke_st_stop_is_pass_not_fail():
    """st.stop() during import is reclassified as PASS."""
    _reimport("utils.page_smoke")
    from utils.page_smoke import smoke_test_page
    # 12_cascade.py calls st.stop() in some flows — should still PASS
    r = smoke_test_page(REPO / "pages" / "12_cascade.py")
    assert r["status"] == "PASS"


def test_v10344_smoke_single_page_returns_status_dict():
    """smoke_test_page returns {page, status, reason, error}."""
    _reimport("utils.page_smoke")
    from utils.page_smoke import smoke_test_page
    r = smoke_test_page(REPO / "pages" / "0_home.py")
    assert "page" in r
    assert "status" in r
    assert r["status"] in {"PASS", "FAIL"}


# ────────────────────────────────────────────────────────────────────
# Section 3 — Full smoke run
# ────────────────────────────────────────────────────────────────────

def test_v10344_full_smoke_zero_failures():
    """Every Streamlit page imports cleanly with the mock."""
    _reimport("utils.page_smoke")
    from utils.page_smoke import smoke_test_all
    report = smoke_test_all()
    if report["failed"] > 0:
        details = " | ".join(
            f"{f['page']}: {f['reason']}={f['error'][:60]}"
            for f in report["failures"][:5]
        )
        assert False, f"Smoke failures: {details}"


def test_v10344_full_smoke_pass_rate_above_threshold():
    """Pass rate must be ≥95% for the smoke gate to fire green."""
    _reimport("utils.page_smoke")
    from utils.page_smoke import smoke_test_all
    report = smoke_test_all()
    assert report["pass_rate"] >= 0.95, (
        f"Pass rate {report['pass_rate']:.1%} — "
        f"{report['failed']}/{report['total']} fail"
    )


def test_v10344_v10341_crash_pages_now_pass():
    """The 4 pages that crashed in v10.341 now smoke-test PASS."""
    _reimport("utils.page_smoke")
    from utils.page_smoke import smoke_test_page
    crashed = [
        "12_cascade.py",
        "4_execute.py",
        "113_branch_ranking.py",
        "95_command_centre.py",
    ]
    for name in crashed:
        r = smoke_test_page(REPO / "pages" / name)
        assert r["status"] == "PASS", (
            f"{name} regressed: {r.get('reason')} — {r.get('error')}"
        )


# ────────────────────────────────────────────────────────────────────
# Section 4 — G231 audit gate
# ────────────────────────────────────────────────────────────────────

def test_v10344_g231_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_page_smoke_test
    result = gate_page_smoke_test()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G231"


def test_v10344_g231_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G231", gate_page_smoke_test)' in text
