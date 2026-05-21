"""
Builds utils/live_cockpit_render.py from the 4 existing cockpit pages.

Output is a single helper module exposing:
    render_cims_cockpit(actor)
    render_treasury_cockpit(actor)
    render_credit_cockpit(actor)
    render_compliance_cockpit(actor)

Each render function contains the same logic as the original page's
main() body. Module-level _cached_*() helpers are renamed with a
domain prefix to avoid Streamlit cache key collisions.

Run from repo root:  python scripts/build_live_cockpit_render.py
"""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGES = REPO / "pages"
OUT = REPO / "utils" / "live_cockpit_render.py"

SOURCES = [
    ("cims",       PAGES / "109_cims_live.py"),
    ("treasury",   PAGES / "110_treasury_live.py"),
    ("credit",     PAGES / "111_credit_live.py"),
    ("compliance", PAGES / "112_compliance_live.py"),
]


def extract_page(domain: str, src: Path) -> tuple[str, str, set[str]]:
    """Return (cache_helpers_block, render_body_block, imports_block).

    cache_helpers_block: All module-level `@st.cache_data` decorated
      helper functions, with `_cached_*` renamed to `_<domain>_cached_*`.
    render_body_block: The body of `main()` (everything between the
      opening line and the trailing `main()` call), with internal
      references to the renamed cache helpers also patched.
    imports_block: Whole-import statements parsed via ast, returned as
      a set of source-text snippets.
    """
    import ast
    text = src.read_text()
    tree = ast.parse(text)

    # 1. Extract imports — only those from utils.* (we'll add streamlit
    #    + datetime ourselves). Use ast to handle multi-line imports.
    imports: set[str] = set()
    lines = text.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and node.module.startswith("utils."):
                names = ", ".join(
                    a.asname or a.name for a in node.names
                )
                imports.add(f"from {node.module} import {names}")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("utils."):
                    if a.asname:
                        imports.add(f"import {a.name} as {a.asname}")
                    else:
                        imports.add(f"import {a.name}")

    # 2. Identify _cached_* helper names + their replacements
    cache_names = re.findall(r"^def (_cached_\w+)", text, re.MULTILINE)
    rename_map = {old: f"_{domain}{old}" for old in cache_names}

    # 3. Extract cache-helper block — everything from first @st.cache_data
    #    line until the `def main()` line
    cache_start_match = re.search(r"^@st\.cache_data", text, re.MULTILINE)
    main_def_match = re.search(r"^def main\(\):", text, re.MULTILINE)
    if not cache_start_match or not main_def_match:
        raise RuntimeError(f"Couldn't locate cache or main() in {src}")
    cache_block = text[cache_start_match.start():main_def_match.start()].rstrip() + "\n"

    # 4. Extract main() body — from after `def main():` line to the
    #    bottom of the file, minus the trailing `main()` call line
    main_body_start = text.index("def main():", main_def_match.start())
    body_lines = text[main_body_start:].splitlines()
    body_lines = body_lines[1:]  # drop `def main():` line
    while body_lines and body_lines[-1].strip() in ("", "main()"):
        body_lines.pop()
    body = "\n".join(body_lines)
    body = textwrap.dedent(body)

    # 5. Apply rename map across cache block and body
    for old, new in rename_map.items():
        cache_block = re.sub(rf"\b{re.escape(old)}\b", new, cache_block)
        body = re.sub(rf"\b{re.escape(old)}\b", new, body)

    return cache_block, body, imports


def build() -> None:
    all_imports: set[str] = set()
    domain_blocks: list[tuple[str, str, str]] = []

    for domain, src in SOURCES:
        cache_block, body, imports = extract_page(domain, src)
        all_imports |= imports
        domain_blocks.append((domain, cache_block, body))

    # Compose the output module
    lines: list[str] = []
    lines.append('"""')
    lines.append('utils/live_cockpit_render.py — v10.345 (Option E, sub-batch 1).')
    lines.append('')
    lines.append('Single source of truth for the 4 Live Cockpit render functions.')
    lines.append('Extracted from pages/109_cims_live, 110_treasury_live, 111_credit_live,')
    lines.append('112_compliance_live. The original 4 pages now import their render')
    lines.append('function from here; the consolidated page (115_live_cockpits) imports')
    lines.append('all 4 and routes via domain selector.')
    lines.append('')
    lines.append('Cache helpers are namespaced with a domain prefix to avoid Streamlit')
    lines.append('cache key collisions between domains.')
    lines.append('"""')
    lines.append('')
    lines.append('from __future__ import annotations')
    lines.append('')
    lines.append('from datetime import datetime, timedelta')
    lines.append('')
    lines.append('import streamlit as st')
    lines.append('')
    for imp in sorted(all_imports):
        lines.append(imp)
    lines.append('')
    lines.append('')

    for domain, cache_block, body in domain_blocks:
        lines.append(f"# {'═' * 64}")
        lines.append(f"# {domain.upper()} — render + cache helpers")
        lines.append(f"# {'═' * 64}")
        lines.append('')
        lines.append(cache_block)
        lines.append('')
        lines.append(f"def render_{domain}_cockpit(actor: str) -> None:")
        lines.append(f'    """Render the {domain.upper()} live cockpit. Body extracted from')
        lines.append(f'    pages/<original>_{domain}_live.py main()."""')
        # Re-indent the body by 4 spaces
        indented_body = textwrap.indent(body, "    ")
        lines.append(indented_body)
        lines.append('')
        lines.append('')

    OUT.write_text("\n".join(lines))
    print(f"Wrote {OUT} ({OUT.stat().st_size:,} bytes, {OUT.read_text().count(chr(10)):,} lines)")


if __name__ == "__main__":
    build()
