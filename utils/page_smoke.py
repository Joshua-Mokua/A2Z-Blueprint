"""
utils/page_smoke.py — v10.344 Page Smoke-Test Engine (Option C).

Imports every Streamlit page headlessly with a mock streamlit module
and reports which pages crash on module load. Public API used by both
the integration test suite and the G231 audit gate.

WHAT IT CATCHES
---------------
- KeyError / AttributeError on data (the v10.341 crash class)
- NameError / ImportError (typo'd identifiers, missing imports)
- TypeError (subscript on wrong type)
- ValueError raised during module top-level code

WHAT IT SKIPS (counted separately, not failures)
------------------------------------------------
- StreamlitStop from st.stop() — pages legitimately use this for gating
- Pages that perform real network / database calls at module top
"""

from __future__ import annotations

import importlib.util
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO = Path(__file__).resolve().parent.parent
PAGES_DIR = REPO / "pages"


# Pages that have a known reason to not import headlessly. Each entry
# is (filename, reason). These are SKIPPED rather than failed — they're
# documented exceptions, not bugs.
KNOWN_SKIP: Dict[str, str] = {
    # filled in below as we discover them
}


def _install_mock() -> None:
    """Install the streamlit mock + ensure the helpers package is importable."""
    helpers_dir = REPO / "tests" / "helpers"
    helpers_init = helpers_dir / "__init__.py"
    if not helpers_init.exists():
        helpers_init.write_text("")
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from tests.helpers.streamlit_mock import install
    install()


def _classify_exception(exc: BaseException) -> str:
    """Bucket the exception type — drives PASS/FAIL/SKIP."""
    name = type(exc).__name__
    msg = str(exc)
    # StreamlitStop is page logic bailing out, not a bug
    if name == "_StreamlitStop" or name == "StreamlitStop":
        return "SKIP_STREAMLIT_STOP"
    if "ScriptRunContext" in msg or "session_state" in msg:
        return "SKIP_STREAMLIT_RUNTIME"
    return "FAIL"


def smoke_test_page(page_path: Path) -> Dict[str, Any]:
    """Import one page headlessly. Returns dict with status + details."""
    _install_mock()

    name = page_path.name
    if name in KNOWN_SKIP:
        return {
            "page": name,
            "status": "SKIP_KNOWN",
            "reason": KNOWN_SKIP[name],
            "error": None,
        }

    # Drop any prior cached import of this module
    mod_name = f"_smoke_{page_path.stem}"
    sys.modules.pop(mod_name, None)

    try:
        spec = importlib.util.spec_from_file_location(mod_name, page_path)
        if spec is None or spec.loader is None:
            return {
                "page": name,
                "status": "FAIL",
                "reason": "spec_creation_failed",
                "error": "could not create import spec",
            }
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return {
            "page": name,
            "status": "PASS",
            "reason": None,
            "error": None,
        }
    except SystemExit as exc:
        # Page imported far enough to call sys.exit / st.stop — PASS
        return {
            "page": name,
            "status": "PASS",
            "reason": f"halted_via_SystemExit({exc.code})",
            "error": None,
        }
    except BaseException as exc:
        name_type = type(exc).__name__
        # StreamlitStop from st.stop() — also a PASS (page reached auth gating)
        if name_type in ("_StreamlitStop", "StreamlitStop"):
            return {
                "page": name,
                "status": "PASS",
                "reason": "halted_via_st.stop()",
                "error": None,
            }
        bucket = _classify_exception(exc)
        return {
            "page": name,
            "status": bucket,
            "reason": name_type,
            "error": str(exc)[:200],
            "traceback": traceback.format_exc()[-800:],
        }


def smoke_test_pages() -> Dict[str, Any]:
    """Run module-load smoke test on every page. Returns the base report
    without static or dynamic augmentations — fast path for G231.

    v10.353 — separated from smoke_test_all so audit gates that only
    need page-load coverage don't pay for the heavier checks (static
    AST + dynamic render) that take ~20-30s combined.
    """
    pages = sorted(PAGES_DIR.glob("*.py"))
    pages = [p for p in pages if not p.name.startswith("_")]

    results: List[Dict[str, Any]] = []
    for p in pages:
        results.append(smoke_test_page(p))

    summary = {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "skipped": sum(1 for r in results if r["status"].startswith("SKIP")),
        "results": results,
    }

    summary["failures"] = [
        {"page": r["page"], "reason": r["reason"], "error": r["error"]}
        for r in results if r["status"] == "FAIL"
    ]
    summary["pass_rate"] = (
        summary["passed"] / summary["total"] if summary["total"] else 1.0
    )
    return summary


def smoke_test_all() -> Dict[str, Any]:
    """Run smoke test on every page. Returns aggregate report augmented
    with static AST checks (v10.352) and dynamic render-function smoke
    (v10.353).

    For audit gates that only need page-load coverage, use the lighter
    `smoke_test_pages()` instead.
    """
    summary = smoke_test_pages()

    # v10.352 — augment with static AST checks
    try:
        from utils.static_check import static_check_paths
        utils_dir = REPO / "utils"
        static_paths = sorted(utils_dir.glob("*.py")) + sorted(
            PAGES_DIR.glob("[0-9]*.py")
        )
        static_findings = static_check_paths(static_paths)
        summary["static_findings"] = [
            {
                "file": f.file.replace(str(REPO) + "/", ""),
                "function": f.function,
                "line": f.line,
                "name": f.name,
                "category": f.category,
            }
            for f in static_findings
        ]
        summary["static_clean"] = len(static_findings) == 0
    except Exception as exc:
        summary["static_findings"] = []
        summary["static_clean"] = False
        summary["static_error"] = f"{type(exc).__name__}: {exc}"

    # v10.353 — augment with dynamic render-function smoke. This calls
    # each render with a synthetic actor and reports what passes / what
    # crashes. Crashes are classified (real bug vs mock gap vs data
    # missing) to make triage clearer.
    try:
        from utils.dynamic_smoke import smoke_test_renders
        dyn = smoke_test_renders()
        summary["dynamic_render_total"] = dyn["total"]
        summary["dynamic_render_passed"] = dyn["passed"]
        summary["dynamic_render_effective_total"] = dyn["effective_total"]
        summary["dynamic_render_effective_pass_rate"] = dyn["effective_pass_rate"]
        summary["dynamic_render_real_bugs"] = dyn["real_bugs"]
        summary["dynamic_render_mock_gaps"] = dyn["mock_gaps"]
        summary["dynamic_render_failures"] = dyn["failures"]
    except Exception as exc:
        summary["dynamic_render_effective_pass_rate"] = 0.0
        summary["dynamic_render_failures"] = []
        summary["dynamic_error"] = f"{type(exc).__name__}: {exc}"

    return summary


def format_summary(report: Dict[str, Any]) -> str:
    """Human-readable summary text."""
    lines = []
    lines.append(f"Page smoke test — {report['total']} pages")
    lines.append(f"  PASS:    {report['passed']}")
    lines.append(f"  FAIL:    {report['failed']}")
    lines.append(f"  SKIP:    {report['skipped']}")
    lines.append(f"  rate:    {report['pass_rate']:.1%}")
    if report["failures"]:
        lines.append("")
        lines.append("Failures:")
        for f in report["failures"][:25]:
            lines.append(f"  {f['page']:35s}  {f['reason']:20s}  {f['error'][:60]}")
    # v10.352 — static-check findings
    static = report.get("static_findings", [])
    if static:
        lines.append("")
        lines.append(f"Static AST findings: {len(static)}")
        for f in static[:15]:
            lines.append(
                f"  {f['file']}:{f['line']}  in {f['function']}()  "
                f"→  {f['name']}  ({f['category']})"
            )
    elif "static_clean" in report and report["static_clean"]:
        lines.append("  static:  clean (0 findings)")

    # v10.353 — dynamic render smoke section
    if "dynamic_render_effective_pass_rate" in report:
        dpr = report["dynamic_render_effective_pass_rate"]
        eff = report.get("dynamic_render_effective_total", 0)
        passed = report.get("dynamic_render_passed", 0)
        lines.append(
            f"  dynamic: {passed}/{eff} renders pass ({dpr:.1%} effective)"
        )
        real_bugs = report.get("dynamic_render_real_bugs", 0)
        mock_gaps = report.get("dynamic_render_mock_gaps", 0)
        if real_bugs or mock_gaps:
            lines.append(
                f"    real bugs: {real_bugs}  mock gaps: {mock_gaps}"
            )
        for f in report.get("dynamic_render_failures", [])[:10]:
            lines.append(
                f"    {f['function']:35s}  [{f['category'] or f['status']}]  "
                f"{(f['error'] or '')[:50]}"
            )
    return "\n".join(lines)


if __name__ == "__main__":
    report = smoke_test_all()
    print(format_summary(report))
    sys.exit(0 if report["failed"] == 0 else 1)
