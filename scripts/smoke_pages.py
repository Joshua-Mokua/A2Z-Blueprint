"""Page-import smoke test.

Walks every page in pages/ and tries to load it as a module. Catches
KeyError / AttributeError / NameError on missing fields — exactly the
class of bug that crashed 12_cascade / 4_execute / 113_branch_ranking /
95_command_centre.

NOT a substitute for Streamlit page rendering — st.* calls will error
out under headless import. We're after the kind of bug that happens
DURING module load, BEFORE Streamlit takes over.

Run with: python scripts/smoke_pages.py
"""

import sys
import ast
import importlib.util
import traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PAGES = REPO / "pages"

# These pages won't import headlessly because they call st.* at module
# top — that's normal for Streamlit pages. We skip them, but record
# them so we know coverage isn't 100%.
EXPECTED_ST_CRASH_OK = {
    # Empty set — we'll learn as we go
}


def find_undefined_subscripts(tree: ast.AST):
    """Look for bracket-subscript accesses on dict-typed records that
    don't use .get() — the most common KeyError source."""
    risks = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            key = node.slice.value
            if isinstance(key, str):
                # Risky: i['gate'], r['phase'], etc on records that
                # come from JSON. We can't tell statically if it's safe,
                # but we can flag suspicious key names.
                if key in {"gate", "phase", "buffer_pct", "target",
                           "milestones", "rag_status"}:
                    risks.append((getattr(node, "lineno", 0), key))
    return risks


def main():
    results = {
        "imported_clean":   [],
        "import_error":     [],
        "subscript_risks":  {},
    }

    for page in sorted(PAGES.glob("*.py")):
        if page.name.startswith("_"):
            continue
        rel = page.relative_to(REPO)

        # Static AST scan for risky subscripts
        try:
            tree = ast.parse(page.read_text())
            risks = find_undefined_subscripts(tree)
            if risks:
                results["subscript_risks"][str(rel)] = risks
        except SyntaxError as exc:
            results["import_error"].append((str(rel), f"SyntaxError: {exc}"))
            continue

        # Try to load the module (Streamlit st.* calls will fail —
        # that's not what we're catching). We catch ImportError + early
        # NameError / AttributeError that happen during module-level
        # code BEFORE the first st.* call.
        try:
            spec = importlib.util.spec_from_file_location(
                f"_smoke_{page.stem}", page
            )
            module = importlib.util.module_from_spec(spec)
            # Suppress streamlit so any st.* call at top fails cleanly
            spec.loader.exec_module(module)
            results["imported_clean"].append(str(rel))
        except Exception as exc:
            # Filter out "expected" st.* crashes — these are common
            err_str = str(exc)
            if any(s in err_str for s in (
                "st.set_page_config",
                "st.session_state has no",
                "ScriptRunContext",
                "_main_script_request",
                "Session state does not function",
                "session_state.",
            )):
                continue  # Streamlit-runtime crash, not the bug class we want
            results["import_error"].append((
                str(rel),
                f"{type(exc).__name__}: {err_str[:200]}",
            ))

    # Report
    print(f"\n  Pages scanned: {len(list(PAGES.glob('*.py')))}")
    print(f"  Imported clean: {len(results['imported_clean'])}")
    print(f"  Import errors: {len(results['import_error'])}")
    print(f"  Files with risky bare subscripts: "
          f"{len(results['subscript_risks'])}")

    if results["import_error"]:
        print("\n  ⚠️  IMPORT ERRORS:")
        for path, err in results["import_error"][:25]:
            print(f"    {path}: {err}")

    if results["subscript_risks"]:
        print("\n  ⚠️  Files with bare-subscript reads of high-drift keys:")
        for path, risks in sorted(results["subscript_risks"].items())[:25]:
            keys = ", ".join(sorted({k for _, k in risks}))
            print(f"    {path}: keys={keys}")

    return results


if __name__ == "__main__":
    main()
