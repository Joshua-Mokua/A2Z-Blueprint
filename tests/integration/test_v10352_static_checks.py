"""Integration tests for v10.352 — Smoke Test Enhancement (Static AST checks).

The static AST analyzer in utils/static_check.py catches two bug classes
that pure module-load smoke tests can't detect:

  CLASS 1: undefined ALL_CAPS constants used inside function bodies
           (the v10.350 STREAMLIT_AVAILABLE pattern)
  CLASS 2: shadowing local imports producing UnboundLocalError
           (the v10.351 get_stock_snapshot pattern)

15 tests across 5 sections:
  Section 1 — Synthetic CLASS 1 detection (3 tests)
  Section 2 — Synthetic CLASS 2 detection (3 tests)
  Section 3 — False positive suppression (4 tests)
  Section 4 — Real codebase clean (2 tests)
  Section 5 — G238 + integration (3 tests)
"""

import sys
import tempfile
import textwrap
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


def _write_temp_module(code: str) -> Path:
    """Helper — write a synthetic test module to a temp file."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    )
    tmp.write(textwrap.dedent(code).strip() + "\n")
    tmp.close()
    return Path(tmp.name)


# ────────────────────────────────────────────────────────────────────
# Section 1 — Synthetic CLASS 1 detection (undefined ALL_CAPS)
# ────────────────────────────────────────────────────────────────────

def test_v10352_detects_v10350_streamlit_available_pattern():
    """Recreates v10.350 STREAMLIT_AVAILABLE bug — must be flagged."""
    from utils.static_check import find_undefined_caps_constants
    code = """
        import streamlit as st

        def render_executive_tab(engines):
            if not STREAMLIT_AVAILABLE:
                return
            st.write("hi")
    """
    p = _write_temp_module(code)
    findings = find_undefined_caps_constants(p)
    p.unlink()
    assert any(f.name == "STREAMLIT_AVAILABLE" for f in findings), (
        "Failed to detect v10.350-style undefined ALL_CAPS constant"
    )


def test_v10352_detects_top_level_caps_constant_missing():
    """Module has SOME_CONST in function, but it's never defined."""
    from utils.static_check import find_undefined_caps_constants
    code = """
        def do_thing():
            return SOME_CONST + 1
    """
    p = _write_temp_module(code)
    findings = find_undefined_caps_constants(p)
    p.unlink()
    assert any(f.name == "SOME_CONST" for f in findings)


def test_v10352_caps_resolved_via_module_top_not_flagged():
    """ALL_CAPS that IS defined at module top should NOT be flagged."""
    from utils.static_check import find_undefined_caps_constants
    code = """
        MAX_RETRIES = 5

        def attempt(n):
            for _ in range(MAX_RETRIES):
                pass
    """
    p = _write_temp_module(code)
    findings = find_undefined_caps_constants(p)
    p.unlink()
    assert not any(f.name == "MAX_RETRIES" for f in findings)


# ────────────────────────────────────────────────────────────────────
# Section 2 — Synthetic CLASS 2 detection (UnboundLocalError trap)
# ────────────────────────────────────────────────────────────────────

def test_v10352_detects_v10351_get_stock_snapshot_pattern():
    """Recreates v10.351 UnboundLocalError bug."""
    from utils.static_check import find_unbound_local_imports
    code = """
        from utils.system_stocks import get_stock_snapshot

        def render_systems_view(actor):
            snapshot = get_stock_snapshot("x")  # ← use first
            print(snapshot)
            # 100 lines later...
            from utils.system_stocks import get_stock_snapshot  # ← shadow
    """
    p = _write_temp_module(code)
    findings = find_unbound_local_imports(p)
    p.unlink()
    assert any(f.name == "get_stock_snapshot" for f in findings), (
        "Failed to detect v10.351-style shadowing local import"
    )


def test_v10352_local_import_before_use_not_flagged():
    """Local import that comes BEFORE any use is wasteful but not a bug."""
    from utils.static_check import find_unbound_local_imports
    code = """
        from utils.x import helper

        def f():
            from utils.x import helper  # redundant but before use
            return helper()
    """
    p = _write_temp_module(code)
    findings = find_unbound_local_imports(p)
    p.unlink()
    # No use BEFORE the local import — not flagged
    assert not findings


def test_v10352_no_module_top_import_no_flag():
    """Local imports that don't shadow anything are fine."""
    from utils.static_check import find_unbound_local_imports
    code = """
        def f():
            x = something  # not relevant
            from os.path import basename
            return basename(x)
    """
    p = _write_temp_module(code)
    findings = find_unbound_local_imports(p)
    p.unlink()
    assert not findings


# ────────────────────────────────────────────────────────────────────
# Section 3 — False positive suppression
# ────────────────────────────────────────────────────────────────────

def test_v10352_class_attribute_in_default_arg_not_flagged():
    """DEFAULT_X as a class attribute used in method default arg should
    NOT be flagged — Python evaluates defaults in class scope."""
    from utils.static_check import find_undefined_caps_constants
    code = """
        class Foo:
            DEFAULT_LIMIT = 100

            def method(self, n: int = DEFAULT_LIMIT):
                return n
    """
    p = _write_temp_module(code)
    findings = find_undefined_caps_constants(p)
    p.unlink()
    assert not any(f.name == "DEFAULT_LIMIT" for f in findings)


def test_v10352_closure_access_not_flagged():
    """Inner function accessing enclosing function's local — closure."""
    from utils.static_check import find_undefined_caps_constants
    code = """
        def outer():
            CONFIG_DATA = {"x": 1}

            def inner():
                return CONFIG_DATA["x"]

            return inner
    """
    p = _write_temp_module(code)
    findings = find_undefined_caps_constants(p)
    p.unlink()
    assert not any(f.name == "CONFIG_DATA" for f in findings), (
        "Closure access falsely flagged as undefined"
    )


def test_v10352_subscript_assign_not_treated_as_binding():
    """`st.session_state[\"x\"] = y` should NOT make `st` local."""
    from utils.static_check import find_unbound_local_imports
    code = """
        import streamlit as st

        def main():
            st.write("before")
            st.session_state["selected"] = "value"  # NOT a binding of `st`
    """
    p = _write_temp_module(code)
    findings = find_unbound_local_imports(p)
    p.unlink()
    assert not findings, (
        "Subscript assignment falsely treated as binding the receiver"
    )


def test_v10352_redundant_local_imports_after_first_not_flagged():
    """If function has 2 local imports of same name, only the FIRST matters
    for use-before-bind. Subsequent ones are redundant but not bugs."""
    from utils.static_check import find_unbound_local_imports
    code = """
        from datetime import datetime

        def f():
            from datetime import datetime  # first — line 4
            x = datetime.now()              # use after first — OK
            from datetime import datetime  # redundant second
            y = datetime.now()              # use after redundant — also OK
    """
    p = _write_temp_module(code)
    findings = find_unbound_local_imports(p)
    p.unlink()
    assert not findings


# ────────────────────────────────────────────────────────────────────
# Section 4 — Real codebase clean
# ────────────────────────────────────────────────────────────────────

def test_v10352_real_codebase_static_clean():
    """The current codebase must report 0 findings — proves the
    v10.350 + v10.351 fixes locked in plus the v10.352 DATA_DIR fix."""
    from utils.static_check import static_check_paths
    paths = sorted((REPO / "utils").glob("*.py")) + sorted(
        (REPO / "pages").glob("[0-9]*.py")
    )
    findings = static_check_paths(paths)
    assert not findings, (
        f"Real codebase has {len(findings)} static findings: "
        f"{[(f.file, f.line, f.name, f.category) for f in findings[:5]]}"
    )


def test_v10352_data_dir_typo_fixed():
    """v10.352 fixed DATA_DIR typo in actuals_engine._add_initiative_kpis.
    Allow the name to appear in a comment (explaining the fix), but not
    in executable code."""
    text = (REPO / "utils" / "actuals_engine.py").read_text()
    # Strip comments before searching
    code_only = "\n".join(
        line.split("#")[0] for line in text.splitlines()
    )
    import re
    bare_uses = re.findall(r"\bDATA_DIR\b", code_only)
    assert not bare_uses, (
        f"Found {len(bare_uses)} remaining DATA_DIR code references — "
        f"v10.352 fix not applied"
    )


# ────────────────────────────────────────────────────────────────────
# Section 5 — G238 + integration
# ────────────────────────────────────────────────────────────────────

def test_v10352_g238_gate_passes():
    _reimport("scripts.audit")
    sys.path.insert(0, str(REPO / "scripts"))
    from audit import gate_static_function_checks
    result = gate_static_function_checks()
    assert result["passed"], result.get("violations")
    assert result["id"] == "G238"


def test_v10352_g238_in_gates_list():
    text = (REPO / "scripts" / "audit.py").read_text()
    assert '("G238", gate_static_function_checks)' in text


def test_v10352_smoke_test_includes_static_findings():
    """smoke_test_all() returns a report with static_findings + static_clean."""
    _reimport("utils.page_smoke")
    _reimport("utils.static_check")
    from utils.page_smoke import smoke_test_all
    r = smoke_test_all()
    assert "static_findings" in r
    assert "static_clean" in r
    assert r["static_clean"] is True
    assert isinstance(r["static_findings"], list)
    assert len(r["static_findings"]) == 0
