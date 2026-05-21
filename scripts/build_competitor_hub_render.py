"""
Builds utils/competitor_hub_render.py from the 2 competitor pages.

Output module exposes:
    render_competitor_overview(actor)    — from pages/11_competitor.py
    render_competitor_workbench(actor)   — from pages/93_competitor_intelligence.py

Run: python scripts/build_competitor_hub_render.py
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGES = REPO / "pages"
OUT = REPO / "utils" / "competitor_hub_render.py"


SOURCES = [
    {
        "domain":     "overview",
        "src":        REPO / "data" / "_v10348_backups" / "11_competitor.py.before",
        "render_fn":  "render_competitor_overview",
        "rename":     ["_load"],
    },
    {
        "domain":     "workbench",
        "src":        REPO / "data" / "_v10348_backups" / "93_competitor_intelligence.py.before",
        "render_fn":  "render_competitor_workbench",
        "rename":     ["_bootstrap_engines"],
    },
]


def extract_page(spec: dict) -> tuple[str, str, set[str]]:
    """Same extraction logic as v10.346/v10.347 build scripts."""
    src_path = spec["src"]
    domain = spec["domain"]
    rename = spec["rename"]
    text = src_path.read_text()
    lines = text.splitlines()

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
        for node in preamble_tree.body:
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                _SHIM_MAP = {
                    "pages._shared":         "utils.page_shared",
                    "pages._access":         "utils.page_access",
                    "pages._cockpit_render": "utils.page_cockpit_render",
                }
                if module in _SHIM_MAP:
                    module = _SHIM_MAP[module]
                if module:
                    parts = []
                    for a in node.names:
                        if a.name == "*":
                            parts.append("*")
                        elif a.asname:
                            parts.append(f"{a.name} as {a.asname}")
                        else:
                            parts.append(a.name)
                    imports.add(f"from {module} import {', '.join(parts)}")
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
    lines.append('utils/competitor_hub_render.py — v10.348 (Option E sub-batch 4).')
    lines.append('')
    lines.append('Single source of truth for the 2 Competitor render functions.')
    lines.append('Extracted from pages/11_competitor (Market Overview) and pages/')
    lines.append('93_competitor_intelligence (Workbench).')
    lines.append('')
    lines.append('Helper functions like _load() that collided across pages have been')
    lines.append('renamed with a domain prefix.')
    lines.append('"""')
    lines.append('')
    lines.append('from __future__ import annotations')
    lines.append('')

    stdlib_pat = re.compile(r"^(?:import|from)\s+(?!utils\.|pages\.)")
    utils_pat = re.compile(r"^(?:import|from)\s+utils[\.\s]")
    pages_pat = re.compile(r"^(?:import|from)\s+pages[\.\s]")

    stdlib_imports = sorted(i for i in all_imports if stdlib_pat.match(i))
    utils_imports = sorted(i for i in all_imports if utils_pat.match(i))
    pages_imports = sorted(i for i in all_imports if pages_pat.match(i))

    for imp in stdlib_imports:
        lines.append(imp)
    lines.append('')
    for imp in utils_imports:
        lines.append(imp)
    lines.append('')
    for imp in pages_imports:
        lines.append(imp)
    lines.append('')
    lines.append('')

    for spec, helpers_block, body_block in domain_blocks:
        domain = spec["domain"]
        fn = spec["render_fn"]
        lines.append(f"# {'═' * 64}")
        lines.append(f"# COMPETITOR — {domain.upper()} render + helpers")
        lines.append(f"# {'═' * 64}")
        lines.append('')
        if helpers_block.strip():
            lines.append(helpers_block)
        lines.append('')
        lines.append(f"def {fn}(actor: str) -> None:")
        lines.append(f'    """Render the competitor {domain} view. Body extracted from')
        lines.append(f'    the original page."""')
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
