"""
Builds utils/platform_hub_render.py from the 4 Platform/IT pages.

Output exposes:
    render_systems_view(actor)       — from pages/91_systems_view.py
    render_it_digital_pt1(actor)     — from pages/96_it_digital_pt1.py
    render_it_digital_pt2(actor)     — from pages/97_it_digital_pt2.py
    render_platform_health(actor)    — from pages/98_platform_health.py

Mixed structures across the 4 source pages:
  - 91 and 98 use module-level code (no def main())
  - 96 and 97 have a def main() function (extract its body)

Cache helpers are namespaced by domain prefix. `_load()` style names
in any page get a domain prefix to avoid collisions.

Run: python scripts/build_platform_hub_render.py
"""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "utils" / "platform_hub_render.py"


# When the build script runs after a page has already been refactored
# to a thin wrapper, read from the pre-refactor backup instead.
def _src(filename: str) -> Path:
    """Find the canonical source — backup if it exists, page otherwise."""
    backup = REPO / "data" / "_v10349_backups" / f"{filename}.before"
    if backup.exists():
        return backup
    return REPO / "pages" / filename


SOURCES = [
    {
        "domain":     "systems_view",
        "src":        _src("91_systems_view.py"),
        "render_fn":  "render_systems_view",
        "has_main":   False,
        "rename":     [],
    },
    {
        "domain":     "it_digital_pt1",
        "src":        _src("96_it_digital_pt1.py"),
        "render_fn":  "render_it_digital_pt1",
        "has_main":   True,
        "rename":     [],
    },
    {
        "domain":     "it_digital_pt2",
        "src":        _src("97_it_digital_pt2.py"),
        "render_fn":  "render_it_digital_pt2",
        "has_main":   True,
        "rename":     [],
    },
    {
        "domain":     "platform_health",
        "src":        _src("98_platform_health.py"),
        "render_fn":  "render_platform_health",
        "has_main":   False,
        "rename":     [],
    },
]


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
    has_main = spec["has_main"]
    text = src_path.read_text()

    if has_main:
        # Extract def main():'s body
        m_def = re.search(r"^def main\(\):", text, re.MULTILINE)
        if not m_def:
            raise RuntimeError(f"def main(): not found in {src_path}")
        # Preamble = everything before def main()
        preamble = text[:m_def.start()]
        # Body = inside def main()
        after_main = text[m_def.end():]
        # find end of main() — look for end of file or next top-level def
        body_lines = after_main.splitlines()
        # Drop trailing `main()` call line + `if __name__ == "__main__":` block
        # + any blanks. Such trailers can be 0-indent which breaks dedent.
        while body_lines and (
            body_lines[-1].strip() in ("", "main()")
            or body_lines[-1].strip().startswith("main()")
            or body_lines[-1].lstrip().startswith("if __name__")
            or (body_lines[-1].startswith("    ")
                and len(body_lines) >= 2
                and body_lines[-2].lstrip().startswith("if __name__"))
        ):
            body_lines.pop()
        body = "\n".join(body_lines)
        body = textwrap.dedent(body)
    else:
        # Module-level code structure — split on require_access(...)
        lines = text.splitlines()
        ra_idx = None
        for i, line in enumerate(lines):
            if re.match(r"^\s*(if not )?require_access\(", line):
                ra_idx = i
                break
        if ra_idx is None:
            raise RuntimeError(f"require_access() not found in {src_path}")
        # Skip the require_access line AND any contiguous follow-up lines
        # (e.g. the if-not-require_access fallback pattern in 98)
        ra_end = ra_idx
        while ra_end + 1 < len(lines) and (
            lines[ra_end + 1].strip().startswith("require_access(")
            or (lines[ra_end + 1].strip() == ""
                and ra_end + 2 < len(lines)
                and lines[ra_end + 2].strip().startswith("require_access("))
        ):
            ra_end += 1
        preamble = "\n".join(lines[:ra_idx])
        body = "\n".join(lines[ra_end + 1:])

    # Collect imports from preamble + filter pages.* → utils.page_*
    imports: set[str] = set()
    try:
        preamble_tree = ast.parse(preamble)
    except SyntaxError:
        preamble_tree = None

    helpers_lines = []
    if preamble_tree is not None:
        skip_ranges: list[tuple[int, int]] = []
        for node in preamble_tree.body:
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
        preamble_lines_split = preamble.splitlines()
        for i, line in enumerate(preamble_lines_split):
            if i not in skipped:
                helpers_lines.append(line)
    else:
        helpers_lines = preamble.splitlines()

    # Drop require_access lines from helpers
    helpers_lines = [
        l for l in helpers_lines
        if not re.match(r"^\s*(if not )?require_access\(", l)
    ]
    helpers_block = "\n".join(helpers_lines).rstrip() + "\n"

    # Apply rename map
    rename_map = {name: f"_{domain}{name}" for name in rename}
    for old, new in rename_map.items():
        helpers_block = re.sub(rf"\b{re.escape(old)}\b", new, helpers_block)
        body = re.sub(rf"\b{re.escape(old)}\b", new, body)

    return helpers_block, body, imports


def build() -> None:
    all_imports: set[str] = set()
    domain_blocks: list[tuple[dict, str, str]] = []
    for spec in SOURCES:
        helpers_block, body_block, imports = extract_page(spec)
        all_imports |= imports
        domain_blocks.append((spec, helpers_block, body_block))

    lines: list[str] = []
    lines.append('"""')
    lines.append('utils/platform_hub_render.py — v10.349 (Option E, sub-batch 5).')
    lines.append('')
    lines.append('Single source of truth for the 4 Platform/IT render functions.')
    lines.append('Extracted from pages/91_systems_view, 96_it_digital_pt1,')
    lines.append('97_it_digital_pt2, 98_platform_health. The original 4 pages now')
    lines.append('import their render function from here; pages/119_platform_hub.py')
    lines.append('is the consolidated entry with area selector.')
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
    if pages_imports:
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
        lines.append(f'    """Render the {domain} view. Body extracted from')
        lines.append(f'    the original page."""')
        indented = textwrap.indent(body_block, "    ")
        lines.append(indented)
        lines.append('')
        lines.append('')

    OUT.write_text("\n".join(lines))
    n_lines = OUT.read_text().count("\n")
    n_bytes = OUT.stat().st_size
    print(f"Wrote {OUT} ({n_bytes:,} bytes, {n_lines:,} lines)")


if __name__ == "__main__":
    build()
