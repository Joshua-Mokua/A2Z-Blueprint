"""
Builds utils/finance_hub_render.py from the 4 finance pages.

Output module exposes:
    render_sbu_performance(actor)   — from pages/9_sbu.py
    render_sbu_drilldown(actor)     — from pages/114_sbu_drilldown.py
    render_opex(actor)              — from pages/10_opex.py
    render_mgmt_accounts(actor)     — from pages/52_mgmt_accounts.py

Source-page bodies (everything after require_access) become the bodies
of the render functions. Module-level helper functions defined BEFORE
require_access become helpers in the helper module with domain prefix
(some, like _load(), collide across pages).

Run: python scripts/build_finance_hub_render.py
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGES = REPO / "pages"
OUT = REPO / "utils" / "finance_hub_render.py"


SOURCES = [
    {
        "domain":     "sbu_performance",
        "src":        REPO / "data" / "_v10346_backups" / "9_sbu.py.before",
        "render_fn":  "render_sbu_performance",
        "rename":     ["_safe_date", "_to_float_safe", "_bsc_trigger"],
    },
    {
        "domain":     "sbu_drilldown",
        "src":        REPO / "data" / "_v10346_backups" / "114_sbu_drilldown.py.before",
        "render_fn":  "render_sbu_drilldown",
        "rename":     [
            "_seg_rollup", "_sector_rollup", "_rm_rollup",
            "_prop_rollup", "_bank_pnl", "_bs", "_fmt_b",
        ],
    },
    {
        "domain":     "opex",
        "src":        REPO / "data" / "_v10346_backups" / "10_opex.py.before",
        "render_fn":  "render_opex",
        "rename":     ["_load"],
    },
    {
        "domain":     "mgmt_accounts",
        "src":        REPO / "data" / "_v10346_backups" / "52_mgmt_accounts.py.before",
        "render_fn":  "render_mgmt_accounts",
        "rename":     ["_load"],
    },
]


def extract_page(spec: dict) -> tuple[str, str, set[str]]:
    """Return (helpers_block, body_block, imports_set).

    helpers_block: lines BEFORE require_access(...), excluding bare
      module imports (those are returned in imports_set instead).
    body_block: lines AFTER require_access(...), de-indented to top
      level. Will be re-indented when wrapped in a render function.
    imports_set: every import statement collected so the helper module
      can declare them once.
    """
    src_path = spec["src"]
    domain = spec["domain"]
    rename = spec["rename"]
    text = src_path.read_text()
    lines = text.splitlines()

    # Find the line index of `require_access(...)`
    ra_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^\s*require_access\(", line):
            ra_idx = i
            break
    if ra_idx is None:
        raise RuntimeError(f"require_access() not found in {src_path}")

    # Split: preamble = lines[:ra_idx]; body = lines[ra_idx+1:]
    preamble_lines = lines[:ra_idx]
    body_lines = lines[ra_idx + 1:]

    # 1. Collect imports out of the preamble, leave the rest as helpers
    imports: set[str] = set()
    helpers_lines: list[str] = []

    # Use AST to enumerate import statements (handles multi-line cleanly)
    try:
        preamble_tree = ast.parse("\n".join(preamble_lines))
    except SyntaxError:
        # If preamble alone isn't valid Python, just keep everything
        # as helpers (best-effort)
        preamble_tree = None

    if preamble_tree is not None:
        # Capture top-level import statements only (not nested inside
        # functions or classes). Track their line spans so we can
        # exclude those lines from the helpers block.
        skip_ranges: list[tuple[int, int]] = []
        for node in preamble_tree.body:  # top-level only
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                # v10.346 — pages._shared / pages._access / pages._cockpit_render
                # have canonical homes in utils/ now. Rewrite the helper's
                # imports to point at the canonical paths so utils/ doesn't
                # cross the layer boundary into pages/.
                _PAGES_SHIM_MAP = {
                    "pages._shared":         "utils.page_shared",
                    "pages._access":         "utils.page_access",
                    "pages._cockpit_render": "utils.page_cockpit_render",
                }
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

        # Build helpers_lines by keeping every line NOT in a skip range
        skipped = set()
        for lo, hi in skip_ranges:
            for i in range(lo, hi + 1):
                skipped.add(i)
        for i, line in enumerate(preamble_lines):
            if i not in skipped:
                helpers_lines.append(line)
    else:
        helpers_lines = list(preamble_lines)

    # Drop any line that's only `require_access(...)` (defensive)
    helpers_lines = [
        l for l in helpers_lines
        if not re.match(r"^\s*require_access\(", l)
    ]

    helpers_block = "\n".join(helpers_lines).rstrip() + "\n"
    body_block = "\n".join(body_lines)
    body_block = textwrap.dedent(body_block)

    # 2a. Apply shim-path rewrites to NESTED imports inside the body
    # (the import-skip pass only catches top-level imports; inline
    # imports inside try/except, conditionals, or function bodies
    # would still target the pages/ namespace and trigger G128).
    _NESTED_IMPORT_REWRITES = [
        ("from pages._shared",         "from utils.page_shared"),
        ("from pages._access",         "from utils.page_access"),
        ("from pages._cockpit_render", "from utils.page_cockpit_render"),
        ("from pages._manifest_loader", "from utils.page_manifest_loader"),
    ]
    for old, new in _NESTED_IMPORT_REWRITES:
        helpers_block = helpers_block.replace(old, new)
        body_block = body_block.replace(old, new)

    # 2. Apply rename map across helpers + body
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

    # Compose the output
    lines: list[str] = []
    lines.append('"""')
    lines.append('utils/finance_hub_render.py — v10.346 (Option E, sub-batch 2).')
    lines.append('')
    lines.append('Single source of truth for the 4 Finance render functions.')
    lines.append('Extracted from pages/9_sbu, 10_opex, 52_mgmt_accounts, and')
    lines.append('114_sbu_drilldown. The original 4 pages now import their render')
    lines.append('function from here; pages/116_finance_hub.py is the consolidated')
    lines.append('entry point with an area selector at top.')
    lines.append('')
    lines.append('Helper functions like _load() that collided across pages have been')
    lines.append('renamed with a domain prefix (_opex_load, _mgmt_accounts_load).')
    lines.append('"""')
    lines.append('')
    lines.append('from __future__ import annotations')
    lines.append('')

    # Sort: stdlib first, then utils, then pages
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
        lines.append(f"# {domain.upper()} — render + helpers")
        lines.append(f"# {'═' * 64}")
        lines.append('')
        if helpers_block.strip():
            lines.append(helpers_block)
        lines.append('')
        lines.append(f"def {fn}(actor: str) -> None:")
        lines.append(f'    """Render the {domain} finance view. Body extracted from')
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
