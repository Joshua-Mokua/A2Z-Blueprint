"""
tests/helpers/streamlit_mock.py — Headless Streamlit mock for the
v10.344 page smoke-test suite.

PURPOSE
-------
Streamlit pages call `st.*` at module top. To smoke-test page imports
headlessly, we replace the `streamlit` module with this mock so every
`st.*` call is a no-op that returns a chainable proxy. Real bugs
(KeyError on data, AttributeError on dict, NameError) still surface;
runtime-only failures (missing ScriptRunContext, session_state writes
needing a real server) do not.

WHAT THIS DOES NOT DO
---------------------
- Does not run the actual Streamlit page lifecycle (no widget state)
- Does not render anything
- Does not detect runtime-only bugs that depend on real session state

WHAT IT CATCHES
---------------
- KeyError / AttributeError on data during module import
- NameError / ImportError
- Subscript-on-wrong-type errors (e.g. the v10.341 crashes)
- Anything raised by module-top code BEFORE Streamlit takes over
"""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from typing import Any


class _MockProxy:
    """A chainable no-op proxy. Any attribute returns another proxy;
    any call returns a proxy. Iteration / indexing return safe defaults."""

    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name: str) -> Any:
        return _MockProxy()

    def __call__(self, *args, **kwargs) -> Any:
        return _MockProxy()

    def __enter__(self) -> "_MockProxy":
        return self

    def __exit__(self, *args) -> bool:
        return False

    def __iter__(self):
        return iter([])

    def __next__(self):
        raise StopIteration

    def __bool__(self) -> bool:
        return False

    def __getitem__(self, key) -> Any:
        return _MockProxy()

    def __setitem__(self, key, value) -> None:
        pass

    def __contains__(self, item) -> bool:
        return False

    def __len__(self) -> int:
        return 0

    def __str__(self) -> str:
        return ""

    def __int__(self) -> int:
        return 0

    def __float__(self) -> float:
        return 0.0

    def __index__(self) -> int:
        # supports list/dict subscript with proxy as index
        return 0

    def __add__(self, other):
        return _MockProxy()

    def __radd__(self, other):
        return _MockProxy()

    def __sub__(self, other):
        return _MockProxy()

    def __rsub__(self, other):
        return _MockProxy()

    def __mul__(self, other):
        return _MockProxy()

    def __rmul__(self, other):
        return _MockProxy()

    def __truediv__(self, other):
        return _MockProxy()

    def __rtruediv__(self, other):
        return _MockProxy()

    def __lt__(self, other):
        return False

    def __le__(self, other):
        return False

    def __gt__(self, other):
        return False

    def __ge__(self, other):
        return False

    def __eq__(self, other):
        return False

    def __ne__(self, other):
        return True

    def __hash__(self):
        return 0

    def __repr__(self) -> str:
        return "<MockProxy>"


class _SessionState(dict):
    """Dict-like session state with attribute access + default proxy."""

    def __getattr__(self, name: str) -> Any:
        if name in self:
            return self[name]
        return _MockProxy()

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value


def _columns_proxy(spec, *_, **__):
    """st.columns returns N proxies — common usage is `c1, c2 = st.columns(2)`."""
    n = spec if isinstance(spec, int) else (len(spec) if hasattr(spec, "__len__") else 2)
    return [_MockProxy() for _ in range(n)]


def _tabs_proxy(labels, *_, **__):
    """st.tabs returns N proxies, one per label."""
    n = len(labels) if hasattr(labels, "__len__") else 2
    return [_MockProxy() for _ in range(n)]


def _cache_passthrough(func=None, **kwargs):
    """st.cache_data / st.cache_resource — return function unchanged or
    a decorator that does the same."""
    if func is None:
        return lambda f: f
    return func


# v10.353 — widget defaults: real Streamlit returns one of the options.
# The mock now mirrors that so render functions that pattern-match on
# the returned value (e.g. `next(t for t,p in items if name == sel_tab)`)
# don't crash with StopIteration.

def _first_option(options, default=None):
    """Extract the first concrete option from a list/tuple/dict-keys.
    Returns `default` if options is empty or not iterable."""
    if options is None:
        return default
    if hasattr(options, "__iter__"):
        try:
            return next(iter(options))
        except StopIteration:
            return default
    return default


def _selectbox_proxy(label, options=None, *args, **kwargs):
    """Returns the first option, mirroring real Streamlit behavior."""
    return _first_option(options)


def _radio_proxy(label, options=None, *args, **kwargs):
    return _first_option(options)


def _segmented_control_proxy(label, options=None, *args, **kwargs):
    return _first_option(options)


def _pills_proxy(label, options=None, *args, **kwargs):
    return _first_option(options)


def _select_slider_proxy(label, options=None, *args, **kwargs):
    return _first_option(options)


def _multiselect_proxy(label, options=None, *args, default=None, **kwargs):
    """Multiselect returns a list. If `default` provided, return it;
    otherwise return [first_option] or []."""
    if default is not None:
        if isinstance(default, list):
            return default
        return [default]
    first = _first_option(options)
    return [first] if first is not None else []


def _slider_proxy(label, min_value=None, max_value=None, value=None, *args, **kwargs):
    """Slider returns value or min_value. Tuple ranges return a tuple."""
    if value is not None:
        return value
    if min_value is not None:
        return min_value
    return 0


def _number_input_proxy(label, min_value=None, max_value=None, value=None, *args, **kwargs):
    if value is not None:
        return value
    if min_value is not None:
        return min_value
    return 0


def _text_input_proxy(label, value="", *args, **kwargs):
    return value


def _text_area_proxy(label, value="", *args, **kwargs):
    return value


def _checkbox_proxy(label, value=False, *args, **kwargs):
    return value


def _toggle_proxy(label, value=False, *args, **kwargs):
    return value


def _button_proxy(label, *args, **kwargs):
    """Buttons return False at smoke time — no click."""
    return False


def _date_input_proxy(label, value=None, *args, **kwargs):
    import datetime
    return value if value is not None else datetime.date.today()


def _time_input_proxy(label, value=None, *args, **kwargs):
    import datetime
    return value if value is not None else datetime.time(0, 0)


def _file_uploader_proxy(label, *args, **kwargs):
    """No file uploaded at smoke time."""
    return None


def install(dynamic: bool = False) -> ModuleType:
    """Install the mock streamlit module into sys.modules.

    Args:
      dynamic: When True, also populates session_state with synthetic
        manager proxies (user_manager, execute_manager, etc.) so render
        functions called dynamically don't crash on
        `um.users.items()` patterns. The default (False) keeps the
        minimal mock used by module-load smoke — pages see None for
        managers and short-circuit early on access checks.

    Returns the mock module so tests can introspect it.
    """
    if "streamlit" in sys.modules:
        existing = sys.modules["streamlit"]
        if getattr(existing, "_is_a2z_mock", False):
            # If existing mock has different dynamic mode, reinstall
            if getattr(existing, "_is_dynamic_mode", False) != dynamic:
                uninstall()
            else:
                return existing

    st = ModuleType("streamlit")
    st._is_a2z_mock = True  # type: ignore[attr-defined]
    st._is_dynamic_mode = dynamic  # type: ignore[attr-defined]

    # Session state — supports both st.session_state['x'] and .x
    st.session_state = _SessionState()  # type: ignore[attr-defined]
    # Common default keys that pages assume present
    st.session_state["user"] = {
        "username": "test_user",
        "full_name": "Test User",
        "role": "Managing Director",
        "staff_code": "EXEC-MD-001",
        "active": True,
    }
    st.session_state["logged_in"] = True
    st.session_state["role"] = "Managing Director"

    # v10.353 — dynamic mode only: synthetic manager proxies. In default
    # mode these stay None, which makes render functions short-circuit
    # early via `if um is None: return` patterns. In dynamic mode we
    # want renders to actually run, so we provide mock managers that
    # iterate empty without crashing.
    if dynamic:
        st.session_state["user_manager"] = _MockProxy()
        st.session_state["execute_manager"] = _MockProxy()
        st.session_state["ri_pipeline_manager"] = _MockProxy()
        st.session_state["product_manager"] = _MockProxy()
        st.session_state["pipeline_manager"] = _MockProxy()
        st.session_state["leave_manager"] = _MockProxy()
        st.session_state["hr_manager"] = _MockProxy()
        st.session_state["cascade_manager"] = _MockProxy()
        st.session_state["validation_manager"] = _MockProxy()
        st.session_state["reporting_line_manager"] = _MockProxy()
        st.session_state["user_data"] = {
            "username": "test_user",
            "full_name": "Test User",
            "role": "Managing Director",
            "staff_code": "EXEC-MD-001",
            "active": True,
            "permissions": [],
        }
        st.session_state["username"] = "test_user"

    # Layout primitives that return multi-proxy lists
    st.columns = _columns_proxy  # type: ignore[attr-defined]
    st.tabs = _tabs_proxy  # type: ignore[attr-defined]
    st.cache_data = _cache_passthrough  # type: ignore[attr-defined]
    st.cache_resource = _cache_passthrough  # type: ignore[attr-defined]

    # v10.353 — widget defaults that return option values, not MockProxies
    st.selectbox = _selectbox_proxy  # type: ignore[attr-defined]
    st.radio = _radio_proxy  # type: ignore[attr-defined]
    st.segmented_control = _segmented_control_proxy  # type: ignore[attr-defined]
    st.pills = _pills_proxy  # type: ignore[attr-defined]
    st.select_slider = _select_slider_proxy  # type: ignore[attr-defined]
    st.multiselect = _multiselect_proxy  # type: ignore[attr-defined]
    st.slider = _slider_proxy  # type: ignore[attr-defined]
    st.number_input = _number_input_proxy  # type: ignore[attr-defined]
    st.text_input = _text_input_proxy  # type: ignore[attr-defined]
    st.text_area = _text_area_proxy  # type: ignore[attr-defined]
    st.checkbox = _checkbox_proxy  # type: ignore[attr-defined]
    st.toggle = _toggle_proxy  # type: ignore[attr-defined]
    st.button = _button_proxy  # type: ignore[attr-defined]
    st.date_input = _date_input_proxy  # type: ignore[attr-defined]
    st.time_input = _time_input_proxy  # type: ignore[attr-defined]
    st.file_uploader = _file_uploader_proxy  # type: ignore[attr-defined]

    # Catch-all — any other st.* returns the proxy
    def _getattr(name: str) -> Any:
        return _MockProxy()
    st.__getattr__ = _getattr  # type: ignore[attr-defined]

    # stop() / rerun() / switch_page() raise so they bail out of the
    # page's execution flow without errors — pages expect these to
    # halt further execution
    class _StreamlitStop(Exception):
        pass
    st.StreamlitStop = _StreamlitStop  # type: ignore[attr-defined]

    def _stop(*_, **__):
        raise _StreamlitStop("st.stop()")

    st.stop = _stop  # type: ignore[attr-defined]

    # Errors module — pages might import from streamlit.errors
    errors_mod = ModuleType("streamlit.errors")
    errors_mod.StreamlitAPIException = type("StreamlitAPIException", (Exception,), {})
    errors_mod.StreamlitDuplicateElementId = type("StreamlitDuplicateElementId", (Exception,), {})
    errors_mod.StreamlitDuplicateElementKey = type("StreamlitDuplicateElementKey", (Exception,), {})
    sys.modules["streamlit.errors"] = errors_mod

    # Components module
    components_mod = ModuleType("streamlit.components")
    components_v1 = ModuleType("streamlit.components.v1")
    components_v1.html = lambda *a, **k: _MockProxy()  # type: ignore[attr-defined]
    components_v1.iframe = lambda *a, **k: _MockProxy()  # type: ignore[attr-defined]
    components_mod.v1 = components_v1  # type: ignore[attr-defined]
    sys.modules["streamlit.components"] = components_mod
    sys.modules["streamlit.components.v1"] = components_v1

    sys.modules["streamlit"] = st

    # ────────────────────────────────────────────────────────────
    # Third-party viz libraries pages may import at module top.
    # We mock these too — page smoke is about LOGIC, not whether
    # plotly/altair/etc are installed in the sandbox.
    # ────────────────────────────────────────────────────────────
    _install_viz_mocks()
    return st


def _install_viz_mocks() -> None:
    """Install mocks for plotly, altair, and other common viz libs."""

    def _make_mock_module(name: str) -> ModuleType:
        mod = ModuleType(name)
        mod._is_a2z_mock = True  # type: ignore[attr-defined]
        def _getattr_proxy(attr_name: str) -> Any:
            return _MockProxy()
        mod.__getattr__ = _getattr_proxy  # type: ignore[attr-defined]
        return mod

    # plotly + submodules — heavily used in pages for charts
    for name in (
        "plotly",
        "plotly.express",
        "plotly.graph_objects",
        "plotly.subplots",
        "plotly.io",
        "plotly.figure_factory",
        "plotly.colors",
    ):
        if name not in sys.modules or not getattr(sys.modules.get(name), "_is_a2z_mock", False):
            sys.modules[name] = _make_mock_module(name)

    # altair (less common but used in some pages)
    if "altair" not in sys.modules:
        sys.modules["altair"] = _make_mock_module("altair")

    # pydeck (used for maps in a few pages)
    if "pydeck" not in sys.modules:
        sys.modules["pydeck"] = _make_mock_module("pydeck")

    # folium (geographic viz)
    if "folium" not in sys.modules:
        sys.modules["folium"] = _make_mock_module("folium")
    if "streamlit_folium" not in sys.modules:
        sys.modules["streamlit_folium"] = _make_mock_module("streamlit_folium")


def uninstall() -> None:
    """Remove the mock from sys.modules. Useful between test runs."""
    for mod_name in list(sys.modules):
        if mod_name == "streamlit" or mod_name.startswith("streamlit."):
            del sys.modules[mod_name]


def is_installed() -> bool:
    """Check if the mock is currently installed."""
    st = sys.modules.get("streamlit")
    return st is not None and getattr(st, "_is_a2z_mock", False)
