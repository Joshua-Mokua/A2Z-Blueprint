"""
Builds utils/propositions_hub_render.py from the 2 propositions pages.

Output module exposes:
    render_propositions_performance(actor)  — from pages/27_propositions.py
    render_propositions_workbench(actor)    — from pages/92_propositions_workbench.py

Source-page bodies (everything after require_access) become the bodies
of the render functions. Module-level helper functions defined BEFORE
require_access become helpers in the helper module with domain prefix.

This script reads from data/_v10347_backups/ so it remains repeatable
even after the original pages have been refactored to thin wrappers.

Run: python scripts/build_propositions_hub_render.py
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "utils" / "propositions_hub_render.py"


SOURCES = [
    {
        "domain":     "propositions_performance",
        "src":        REPO / "data" / "_v10347_backups" / "27_propositions.py.before",
        "render_fn":  "render_propositions_performance",
        "rename":     ["_load_props", "_load_tags", "_load_period"],
    },
    {
        "domain":     "propositions_workbench",
        "src":        REPO / "data" / "_v10347_backups" / "92_propositions_workbench.py.before",
        "render_fn":  "render_propositions_workbench",
        "rename":     [],
    },
]


# v10.346 shim mapping: when source pages import from pages._shared,
# pages._access, or pages._cockpit_render, the helper module must
# import from the canonical utils/page_* paths instead so utils/
# doesn't cross the layer boundary into pages/.
_PAGES_SHIM_MAP = {
    "pages._shared":         "utils.page_shared",
    "pages._access":         "utils.page_access",
    "pages._cockpit_render": "utils.page_cockpit_render",
}


def extract_page(spec: dict) -> tuple[str, str, set[str]]:
    """Return (helpers_block, body_block, imports_set)."""
    src_path = spec["src"]
    domain = spec["domain"]
    rename = spec["rename"]
    text = src_path.read_text()
    lines = text.splitlines()

    # Find `require_access(...)` line
    ra_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*require_access\(", line):
            ra_idx = i
            break
    if ra_idx is None:
        raise RuntimeError(f"require_access() not found in {src_path}")

    preamble_lines = lines[:ra_idx]
    body_lines = lines[ra_idx + 1:]

    imports: set[str] = set()
    helpers_lines: list[str] = []

    try:
        preamble_tree = ast.parse("\n".join(preamble_lines))
    except SyntaxError:
        preamble_tree = None

    if preamble_tree is not None:
        skip_ranges: list[tuple[int, int]] = []
        for node in preamble_tree.body:  # top-level only
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module in _PAGES_SHIM_MAP:
                    module = _PAGES_SHIM_MAP[module]
                if module:
                    parts = []
                    for a in node.names:
                        if a.name == "*":
                            parts.append("*")
                        elif a.asname:
                            parts.append(f"{a.name} as {a.asname}")
                        else:
                            parts.append(a.name)
                    names = ", ".join(parts)
                    imports.add(f"from {module} import {names}")
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    skip_ranges.append(
                        (node.lineno - 1, (node.end_lineno or node.lineno) - 1)
                    )
            elif isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        imports.add(f"import {a.name} as {a.asname}")
                    else:
                        imports.add(f"import {a.name}")
                if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                    skip_ranges.append(
                        (node.lineno - 1, (node.end_lineno or node.lineno) - 1)
                    )

        skipped = set()
        for lo, hi in skip_ranges:
            for i in range(lo, hi + 1):
                skipped.add(i)
        for i, line in enumerate(preamble_lines):
            if i not in skipped:
                helpers_lines.append(line)
    else:
        helpers_lines = list(preamble_lines)

    helpers_lines = [
        l for l in helpers_lines
        if not re.match(r"^\s*require_access\(", l)
    ]

    helpers_block = "\n".join(helpers_lines).rstrip() + "\n"
    body_block = "\n".join(body_lines)
    body_block = textwrap.dedent(body_block)

    rename_map = {name: f"_{domain}{name}" for name in rename}
    for old, new in rename_map.items():
        helpers_block = re.sub(rf"\b{re.escape(old)}\b", new, helpers_block)
        body_block = re.sub(rf"\b{re.escape(old)}\b", new, body_block)

    return helpers_block, body_block, imports


def build() -> None:
    all_imports: set[str] = set()
    domain_blocks: list[tuple[dict, str, str]] = []
    for spec in SOURCES:
        helpers_block, body_block, imports = extract_page(spec)
        all_imports |= imports
        domain_blocks.append((spec, helpers_block, body_block))

    lines: list[str] = []
    lines.append('"""')
    lines.append('utils/propositions_hub_render.py — v10.347 (Option E, sub-batch 3).')
    lines.append('')
    lines.append('Single source of truth for the 2 Propositions render functions.')
    lines.append('Extracted from pages/27_propositions and pages/92_propositions_workbench.')
    lines.append('The original 2 pages now import their render function from here;')
    lines.append('pages/117_propositions_hub.py is the consolidated entry point with')
    lines.append('an area selector at top.')
    lines.append('')
    lines.append('Helper functions like _load_props() that needed namespacing have been')
    lines.append('renamed with a domain prefix to avoid cache key collisions.')
    lines.append('"""')
    lines.append('')
    lines.append('from __future__ import annotations')
    lines.append('')

    stdlib_pat = re.compile(r"^(?:import|from)\s+(?!utils\.|pages\.)")
    utils_pat = re.compile(r"^(?:import|from)\s+utils[\.\s]")

    stdlib_imports = sorted(i for i in all_imports if stdlib_pat.match(i))
    utils_imports = sorted(i for i in all_imports if utils_pat.match(i))

    for imp in stdlib_imports:
        lines.append(imp)
    lines.append('')
    for imp in utils_imports:
        lines.append(imp)
    lines.append('')
    lines.append('')

    for spec, helpers_block, body_block in domain_blocks:
        domain = spec["domain"]
        fn = spec["render_fn"]
        lines.append(f"# {'═' * 64}")
        lines.append(f"# {domain.upper()} — render + helpers")
        lines.append(f"# {'═' * 64}")
        lines.append('')
        if helpers_block.strip():
            lines.append(helpers_block)
        lines.append('')
        lines.append(f"def {fn}(actor: str) -> None:")
        lines.append(f'    """Render the {domain} view. Body extracted from')
        lines.append(f'    pages/<original>.py."""')
        indented_body = textwrap.indent(body_block, "    ")
        lines.append(indented_body)
        lines.append('')
        lines.append('')

    OUT.write_text("\n".join(lines))
    n_lines = OUT.read_text().count("\n")
    n_bytes = OUT.stat().st_size
    print(f"Wrote {OUT} ({n_bytes:,} bytes, {n_lines:,} lines)")


if __name__ == "__main__":
    build()
