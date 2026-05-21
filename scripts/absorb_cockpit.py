"""scripts/absorb_cockpit.py — cockpit absorption helper module.

Codifies the 6 cockpit pattern variants observed across the
v10.202-v10.212 absorption sub-campaign (13 cockpits, 11 batches).
Single-purpose tooling for any future similar work — page
consolidations, deprecation absorptions, or architectural
reorganizations that follow the same shape.

The helper exposes building blocks (not a one-shot CLI) because
each absorption has cockpit-specific quirks (different headers,
different engine constructors, different sub-tab themes) that
benefit from explicit per-batch composition rather than
parameterized inputs.

═══════════════════════════════════════════════════════════════════
SIX PATTERN VARIANTS DOCUMENTED
═══════════════════════════════════════════════════════════════════

1. Hand-paste (v10.202 Treasury)
   First absorption; no programmatic extraction. Body copy-pasted
   manually with care. Subsequent variants automated this.

2. Named descriptive (v10.203 Strategy)
   Cockpit uses `with tab_form: ... with tab_cascade: ...` etc.
   Body indentation: cockpit col 4 -> target col 12 (+8 spaces).
   Helper: extract_tab_blocks_named()

3. Indexed inline (v10.204 Product, v10.205 Compliance,
                   v10.210 Revenue Assurance)
   Cockpit uses `with tabs[N]: ...` at module level OR inside
   `if STREAMLIT_AVAILABLE:` block. Body at col 4 (module-level)
   or col 8 (inside if-block).
   Helper: extract_tab_blocks_indexed()

4. Numbered named (v10.206 Legal, v10.212 ML Gov + Integration)
   Cockpit uses `with tab1: ... with tab7:` (often inside
   `def render():`). Same extraction logic as indexed.
   Helper: extract_tab_blocks_named() with custom var map

5. Render-funcs-per-tab (v10.207 Resource Optimization)
   Cockpit defines `def render_X_tab(engines): ...` at module
   level; tab body is wholly inside these functions. Absorption
   preserves the functions and inserts call sites in arc_tabs.
   Helper: extract_render_functions()

6. Indexed multi-line strings (v10.211 Finance + Trade Finance)
   Same as indexed inline BUT cockpit body contains
   `st.markdown(\"\"\"...\"\"\")` blocks where string content lines
   are at col 0. Naive extraction terminated at first col-0 line;
   naive re-indent broke string content.
   Fix: triple-quote-aware extraction + re-indentation that
   preserves multi-line string content unchanged.
   Helper: extract_tab_blocks_indexed() + reindent() are both
   string-aware by default.

═══════════════════════════════════════════════════════════════════
CLOSURE GATE REFACTOR TEMPLATES
═══════════════════════════════════════════════════════════════════

Two variants observed across 13 gate refactors:

- Simple variant (8 gates: G149, G151, G159, G148, G153, G155,
  G157, G140): searches a department for required imports +
  constructor presence + require_access + audit_log.

- Strict variant (5 gates: G130, G132, G134, G136, G138): adds
  per-engine method invocation check (each engine must have at
  least one named compute-style method invoked, not just imported).

Both use manifest.json as source of truth for which department to
search. Pages move between departments via JSON edit; gates follow
automatically.

Helper: build_manifest_aware_gate() generates either variant.

═══════════════════════════════════════════════════════════════════
TYPICAL ABSORPTION SCRIPT (10 lines using helpers)
═══════════════════════════════════════════════════════════════════

    from scripts.absorb_cockpit import (
        extract_tab_blocks_indexed,
        extract_tab_labels,
        reindent,
    )

    cockpit = Path("pages/XX_arc_cockpit.py").read_text()
    target = Path("pages/YY_target.py").read_text()

    # 1. Update top-level tabs
    target = target.replace(OLD_TABS, NEW_TABS)

    # 2. Extract cockpit tab bodies
    blocks = extract_tab_blocks_indexed(cockpit)
    labels = extract_tab_labels(cockpit)

    # 3. Build absorbed section
    section = "with tabs[N]:\\n    arc_tabs = st.tabs(...)..."
    for idx in range(len(labels)):
        body = reindent(blocks[idx], "        ")  # +8 spaces
        section += f"    with arc_tabs[{idx}]:\\n" + "\\n".join(body)

    # 4. Pre-flight syntax check + write
    ast.parse(target + section)
    Path("pages/YY_target.py").write_text(target + section)
"""
from __future__ import annotations
import re
from typing import Dict, List, Optional, Tuple


# ──────────────────────────────────────────────────────────────────
# Triple-quote state tracking (used by string-aware extract + reindent)
# ──────────────────────────────────────────────────────────────────

# Defined as concatenation to avoid nested triple-quote escaping in this docstring.
TRIPLE = '"' + '"' + '"'


def _toggle_state(line: str, in_string: bool) -> bool:
    """Toggle triple-quote state if line has odd count of TRIPLE."""
    n = line.count(TRIPLE)
    if n % 2 == 1:
        return not in_string
    return in_string


# ──────────────────────────────────────────────────────────────────
# Tab body extraction (string-aware, handles all variants)
# ──────────────────────────────────────────────────────────────────

def extract_tab_blocks_indexed(
    cockpit_text: str,
    pattern: str = r'^with tabs\[(\d+)\]:\s*$',
) -> Dict[int, List[str]]:
    """Extract tab body blocks from indexed-style cockpits.

    Default pattern matches `with tabs[N]:` at module level (col 0).
    Pass a custom pattern for variants like `^    with tabs\\[(\\d+)\\]:`
    (cockpit-with-render() function wrapper) or for named variants
    use extract_tab_blocks_named().

    Returns dict {idx: [body_lines]} string-aware: lines inside
    multi-line `\"\"\"...\"\"\"` strings are always included regardless
    of their indentation.
    """
    return _extract_with_regex(cockpit_text, pattern, lambda m: int(m.group(1)))


def extract_tab_blocks_named(
    cockpit_text: str,
    var_to_idx: Dict[str, int],
) -> Dict[int, List[str]]:
    """Extract tab body blocks from named-variable cockpits.

    For cockpits like `with tab_form: ... with tab_cascade: ...`
    pass var_to_idx={"tab_form": 0, "tab_cascade": 1, ...}.
    Returns dict {idx: [body_lines]}.
    """
    pattern = r'^with (\w+):\s*$'

    def match_to_idx(m: re.Match) -> Optional[int]:
        return var_to_idx.get(m.group(1))

    return _extract_with_regex(cockpit_text, pattern, match_to_idx)


def _extract_with_regex(
    cockpit_text: str,
    pattern: str,
    match_to_idx,
) -> Dict[int, List[str]]:
    """Generic body extraction with custom regex + index resolver.

    Tracks triple-quote state to handle multi-line string content
    that may appear at col 0 (would otherwise terminate extraction
    prematurely).
    """
    lines = cockpit_text.splitlines()
    tab_blocks: Dict[int, List[str]] = {}
    current_idx: Optional[int] = None
    current_lines: List[str] = []
    in_string = False

    for line in lines:
        was_in_string = in_string
        in_string = _toggle_state(line, in_string)

        # Tab-boundary detection only when NOT inside a string
        if not was_in_string:
            m = re.match(pattern, line)
            if m:
                idx = match_to_idx(m)
                if idx is not None:
                    if current_idx is not None:
                        tab_blocks[current_idx] = current_lines
                    current_idx = idx
                    current_lines = []
                    continue

        if current_idx is None:
            continue

        # Currently collecting body for current_idx
        if was_in_string or in_string:
            # Inside (or transitioning) a multi-line string — always include
            current_lines.append(line)
        elif line.strip() == "":
            current_lines.append(line)
        elif line.startswith("    "):
            current_lines.append(line)
        elif line.startswith("#"):
            tab_blocks[current_idx] = current_lines
            current_idx = None
        elif line.strip():
            tab_blocks[current_idx] = current_lines
            current_idx = None

    if current_idx is not None:
        tab_blocks[current_idx] = current_lines

    # Strip trailing blank lines from each block
    for k in tab_blocks:
        while tab_blocks[k] and tab_blocks[k][-1].strip() == "":
            tab_blocks[k].pop()
    return tab_blocks


def extract_render_functions(
    cockpit_text: str,
    fn_names: List[str],
) -> Dict[str, List[str]]:
    """Extract `def render_X_tab(engines):` functions from cockpits
    that use the render-funcs-per-tab pattern (v10.207 Resource Opt).

    Each function is captured as a list of lines INCLUDING the def line.
    Returns dict {fn_name: [function_lines]}.

    Caller is responsible for re-indenting these functions to fit the
    target's nesting level (typically col 0 -> col 4 inside `with sections[N]:`).
    """
    lines = cockpit_text.splitlines()
    result: Dict[str, List[str]] = {}
    current_fn: Optional[str] = None
    current_lines: List[str] = []

    fn_set = set(fn_names)

    for line in lines:
        m = re.match(r'^def (render_\w+_tab)\(engines\):\s*$', line)
        if m and m.group(1) in fn_set:
            if current_fn is not None:
                result[current_fn] = current_lines
            current_fn = m.group(1)
            current_lines = [line]
            continue

        if current_fn is None:
            continue

        # Continue collecting until we hit a non-indented non-empty line
        if line and not line.startswith(" ") and not line.startswith("\t"):
            result[current_fn] = current_lines
            current_fn = None
            current_lines = []
        else:
            current_lines.append(line)

    if current_fn is not None:
        result[current_fn] = current_lines
    return result


# ──────────────────────────────────────────────────────────────────
# Tab labels — pull from `tabs = st.tabs([...])`
# ──────────────────────────────────────────────────────────────────

def extract_tab_labels(cockpit_text: str) -> List[str]:
    """Pull tab labels from the cockpit's `tabs = st.tabs([...])` call.

    Handles both single-line and multi-line forms. Returns list of
    quoted strings in their declaration order.
    """
    m = re.search(r'tabs = st\.tabs\(\[\s*(.*?)\s*\]\)',
                   cockpit_text, re.DOTALL)
    if not m:
        # Try alternate forms
        m = re.search(r'st\.tabs\(\[\s*(.*?)\s*\]\)',
                       cockpit_text, re.DOTALL)
    if not m:
        return []
    return re.findall(r'"([^"]+)"', m.group(1))


# ──────────────────────────────────────────────────────────────────
# String-aware re-indentation
# ──────────────────────────────────────────────────────────────────

def reindent(lines: List[str], prepend: str) -> List[str]:
    """Re-indent body lines by prepending `prepend` spaces, string-aware.

    Lines that BEGIN inside a multi-line `\"\"\"...\"\"\"` string are
    emitted as-is (no prepend). This preserves markdown content
    formatting and avoids breaking string syntax.

    Empty lines are also emitted as-is.
    """
    out: List[str] = []
    in_string = False
    for line in lines:
        was_in_string = in_string
        in_string = _toggle_state(line, in_string)

        if line.strip() == "":
            out.append(line)
        elif was_in_string:
            # Line begins inside a string — DO NOT re-indent
            out.append(line)
        else:
            # Line begins outside a string — re-indent normally
            out.append(prepend + line)
    return out


# ──────────────────────────────────────────────────────────────────
# Closure gate refactor template (manifest-aware, simple + strict)
# ──────────────────────────────────────────────────────────────────

def build_manifest_aware_gate(
    gate_id: str,
    gate_name: str,
    department: str,
    expected_imports: List[str],
    expected_constructors: List[Tuple[str, Optional[List[str]]]],
    require_access_check: bool = True,
    audit_log_check: bool = True,
    docstring_extra: str = "",
) -> str:
    """Generate a manifest-aware closure gate function as a Python source string.

    Caller writes the result to scripts/audit.py (replacing the
    original location-locked gate via str_replace).

    Args:
      gate_id: e.g. "G130"
      gate_name: e.g. "risk_arc_ui_integrated"
      department: e.g. "risk", "finance", "compliance_regulatory"
      expected_imports: e.g. ["from utils.market_risk_var import"]
      expected_constructors: list of (ctor_string, methods_or_None) tuples.
        - If methods is None: simple variant (no per-engine method check)
        - If methods is List[str]: strict variant — at least one of these
          method names must be invoked somewhere in the searched dept.
      require_access_check: emit require_access(...) check
      audit_log_check: emit audit_log(...) check
      docstring_extra: additional context to include in the gate's docstring

    Returns: source code for `def gate_<gate_name>() -> Dict[str, Any]: ...`
    """
    is_strict = any(methods is not None for _, methods in expected_constructors)
    variant_label = "strict variant" if is_strict else "simple variant"

    # Build the imports list as a Python tuple-of-strings literal
    imports_lit = "(\n        " + ",\n        ".join(
        repr(i) for i in expected_imports) + ",\n    )"

    # Build the constructors list
    if is_strict:
        ctor_lit_lines = []
        for ctor, methods in expected_constructors:
            if methods is None:
                # Strict gate but this engine has no method check — degenerate
                # to "any method" (match anything by passing empty tuple)
                ctor_lit_lines.append(f"        ({ctor!r}, ()),")
            else:
                methods_lit = "(" + ", ".join(repr(m) for m in methods) + (
                    ",)" if len(methods) == 1 else ")")
                ctor_lit_lines.append(f"        ({ctor!r}, {methods_lit}),")
        ctors_lit = "(\n" + "\n".join(ctor_lit_lines) + "\n    )"
    else:
        ctors_lit = "(\n        " + ",\n        ".join(
            repr(c) for c, _ in expected_constructors) + ",\n    )"

    template = TEMPLATE_STRICT if is_strict else TEMPLATE_SIMPLE
    return template.format(
        gate_id=gate_id,
        gate_name=gate_name,
        department=department,
        variant_label=variant_label,
        imports_lit=imports_lit,
        ctors_lit=ctors_lit,
        docstring_extra=docstring_extra,
    )


TEMPLATE_SIMPLE = '''def gate_{gate_name}() -> Dict[str, Any]:
    """{gate_id} — {gate_name} (manifest-aware, {variant_label}).

    Searches the {department} department for required imports +
    engine constructors + require_access + audit_log.
    {docstring_extra}
    """
    import json as _gjson

    violations: List[str] = []
    manifest_path = ROOT / "pages/_manifest.json"
    if not manifest_path.exists():
        return {{"id": "{gate_id}", "name": "{gate_name}",
                 "passed": False,
                 "violations": ["manifest missing"],
                 "summary": "{gate_name}: manifest missing"}}

    manifest = _gjson.loads(manifest_path.read_text(encoding="utf-8"))
    pages = [
        fname for fname, e in manifest.get("pages", {{}}).items()
        if e.get("department_primary") == "{department}"
        and not e.get("deprecated")
    ]

    src = ""
    for fname in pages:
        page_path = ROOT / "pages" / fname
        if page_path.exists():
            try:
                src += page_path.read_text(encoding="utf-8") + "\\n"
            except Exception:
                pass

    required_imports = {imports_lit}
    for imp in required_imports:
        if imp not in src:
            violations.append(f"no {department} page has import {{imp!r}}")

    required_constructors = {ctors_lit}
    for ctor in required_constructors:
        if ctor not in src:
            violations.append(f"no {department} page constructs {{ctor!r}}")

    if "require_access(" not in src:
        violations.append("no {department} page calls require_access()")
    if "audit_log(" not in src:
        violations.append("no {department} page calls audit_log()")

    return {{
        "id": "{gate_id}", "name": "{gate_name}",
        "passed": not violations,
        "violations": violations[:10],
        "summary": (
            f"{gate_name}: integrated in {department} ({{len(pages)}} pages); "
            f"{{len(violations)}} violations"
            if violations else
            f"{gate_name}: integrated in {department} "
            f"({{len(pages)}} pages) — PASS"
        ),
    }}
'''


TEMPLATE_STRICT = '''def gate_{gate_name}() -> Dict[str, Any]:
    """{gate_id} — {gate_name} (manifest-aware, {variant_label}).

    Searches the {department} department for required imports +
    engine constructors + per-engine method invocation +
    require_access + audit_log. Strict variant: each engine must
    be both constructed AND have at least one of its named methods
    invoked somewhere in the dept.
    {docstring_extra}
    """
    import json as _gjson

    violations: List[str] = []
    manifest_path = ROOT / "pages/_manifest.json"
    if not manifest_path.exists():
        return {{"id": "{gate_id}", "name": "{gate_name}",
                 "passed": False,
                 "violations": ["manifest missing"],
                 "summary": "{gate_name}: manifest missing"}}

    manifest = _gjson.loads(manifest_path.read_text(encoding="utf-8"))
    pages = [
        fname for fname, e in manifest.get("pages", {{}}).items()
        if e.get("department_primary") == "{department}"
        and not e.get("deprecated")
    ]

    src = ""
    for fname in pages:
        page_path = ROOT / "pages" / fname
        if page_path.exists():
            try:
                src += page_path.read_text(encoding="utf-8") + "\\n"
            except Exception:
                pass

    required_imports = {imports_lit}
    for imp in required_imports:
        if imp not in src:
            violations.append(f"no {department} page has import {{imp!r}}")

    required_engine_invocations = {ctors_lit}
    for ctor, methods in required_engine_invocations:
        if ctor not in src:
            violations.append(
                f"no {department} page constructs {{ctor!r}}")
            continue
        if methods and not any(m in src for m in methods):
            violations.append(
                f"{department} pages construct {{ctor!r}} but never "
                f"invoke any of {{methods}} — UI must be interactive")

    if "require_access(" not in src:
        violations.append("no {department} page calls require_access()")
    if "audit_log(" not in src:
        violations.append("no {department} page calls audit_log()")

    return {{
        "id": "{gate_id}", "name": "{gate_name}",
        "passed": not violations,
        "violations": violations[:10],
        "summary": (
            f"{gate_name}: integrated in {department} ({{len(pages)}} pages); "
            f"{{len(violations)}} violations"
            if violations else
            f"{gate_name}: integrated in {department} "
            f"({{len(pages)}} pages) — PASS"
        ),
    }}
'''


# ──────────────────────────────────────────────────────────────────
# Smoke test (run this file directly to verify helpers work)
# ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Minimal sanity check on the toggle-state helper
    assert _toggle_state('hello', False) is False
    assert _toggle_state(TRIPLE + 'open', False) is True
    assert _toggle_state(TRIPLE + 'open' + TRIPLE, False) is False
    assert _toggle_state('mid string', True) is True
    assert _toggle_state('close ' + TRIPLE, True) is False

    # Round-trip test on a tiny synthetic cockpit
    SAMPLE = (
        'tabs = st.tabs(["A", "B"])\n'
        'with tabs[0]:\n'
        '    st.write("hello")\n'
        'with tabs[1]:\n'
        '    st.markdown(' + TRIPLE + '\n'
        '# heading\n'
        'content at col 0\n'
        + TRIPLE + ')\n'
    )
    blocks = extract_tab_blocks_indexed(SAMPLE)
    assert sorted(blocks.keys()) == [0, 1], f"expected [0,1] got {sorted(blocks.keys())}"
    assert len(blocks[0]) == 1, f"tab[0] should have 1 line, got {len(blocks[0])}"
    # tab[1] body should include the multi-line string content (3 lines for the
    # markdown call: opening line + 2 content lines + closing line = 4 actually)
    # The closing TRIPLE-paren line is included; the 3 content lines too.
    assert len(blocks[1]) == 4, (
        f"tab[1] should have 4 lines (open + 2 content + close), "
        f"got {len(blocks[1])}: {blocks[1]}")

    labels = extract_tab_labels(SAMPLE)
    assert labels == ["A", "B"], f"expected ['A','B'] got {labels}"

    # Round-trip reindent: non-string lines get prepend, string lines don't
    body = blocks[1]
    reindented = reindent(body, "    ")
    # The opening line (st.markdown call) gets prepended
    assert reindented[0].startswith("        st.markdown(" + TRIPLE), reindented[0]
    # The closing TRIPLE)' line begins inside the string (was_in_string=True),
    # so it should NOT be prepended — preserved at col 0
    assert reindented[-1] == TRIPLE + ")", (
        f"closing line should be unchanged, got: {reindented[-1]!r}")

    # Gate template smoke test
    gate_src = build_manifest_aware_gate(
        gate_id="G999",
        gate_name="example_arc_ui_integrated",
        department="example",
        expected_imports=["from utils.example import"],
        expected_constructors=[("ExampleEngine()", None)],  # simple variant
    )
    assert "def gate_example_arc_ui_integrated()" in gate_src
    assert "department_primary" in gate_src  # references the manifest
    assert "example" in gate_src

    print("✅ All absorb_cockpit.py smoke tests passed")
