"""utils/dynamic_smoke.py — v10.353 Dynamic render-function smoke.

Module-load smoke (v10.344) catches bugs that fire at import time.
Static AST checks (v10.352) catch undefined names + shadowing imports.
This adds the third layer: actually CALL render functions with a
synthetic actor and report which succeed, which fail, and what kind
of failure.

WHAT IT CATCHES
---------------
- KeyError when dict-like data structures lack expected fields
- TypeError on operations (Decimal/float, etc.) inside render bodies
- AttributeError on dynamic attribute access against engines/managers
- Any runtime error that fires when the render code actually executes

WHAT IT CLASSIFIES
------------------
- PASS:        render returned cleanly
- STOP:        st.stop() raised (intentional access gating; not a bug)
- TIMEOUT:     render took > timeout_seconds; usually a subprocess /
               external call (skip from dynamic smoke or shorter
               timeout if interrupted)
- SKIP_KNOWN:  documented exemption (render runs heavy diagnostics)
- FAIL:        any other exception — classify subtype for triage

The result struct gives Joshua a per-render signal. Failures with
"unsupported format string" or "_MockProxy" in the message are
flagged as mock-incomplete; others are flagged as likely real bugs.
"""

from __future__ import annotations

import signal
import sys
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


REPO = Path(__file__).resolve().parent.parent
DEFAULT_ACTOR = "md001"
DEFAULT_TIMEOUT = 10  # seconds — generous for normal renders


# Registry of render functions to dynamically smoke-test.
# Add new ones as render functions are introduced.
RENDER_REGISTRY: List[Tuple[str, str]] = [
    ("utils.live_cockpit_render", "render_cims_cockpit"),
    ("utils.live_cockpit_render", "render_treasury_cockpit"),
    ("utils.live_cockpit_render", "render_credit_cockpit"),
    ("utils.live_cockpit_render", "render_compliance_cockpit"),
    ("utils.finance_hub_render", "render_sbu_performance"),
    ("utils.finance_hub_render", "render_sbu_drilldown"),
    ("utils.finance_hub_render", "render_opex"),
    ("utils.finance_hub_render", "render_mgmt_accounts"),
    ("utils.propositions_hub_render", "render_propositions_performance"),
    ("utils.propositions_hub_render", "render_propositions_workbench"),
    ("utils.competitor_hub_render", "render_competitor_overview"),
    ("utils.competitor_hub_render", "render_competitor_workbench"),
    ("utils.platform_hub_render", "render_systems_view"),
    ("utils.platform_hub_render", "render_it_digital_pt1"),
    ("utils.platform_hub_render", "render_it_digital_pt2"),
    ("utils.platform_hub_render", "render_platform_health"),
]


# Known-skip renders with documented reasons. These are NOT failures —
# they're explicitly out of scope for dynamic smoke because the render
# does something the mock environment can't safely run.
KNOWN_SKIP: Dict[str, str] = {
    "render_platform_health": (
        "spawns subprocess.run() for live audit/structure/test "
        "diagnostics — heavy by design; module-load smoke + static "
        "checks cover the import path; G238 already catches its "
        "function-body issues"
    ),
}


@contextmanager
def _alarm(seconds: int):
    """SIGALRM-based timeout. Works only on POSIX, only on main thread."""
    if sys.platform == "win32":
        yield
        return
    def handler(signum, frame):
        raise TimeoutError(f"render exceeded {seconds}s")
    prev = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, prev)


def _classify_failure(exc: BaseException) -> str:
    """Categorize a failure: real bug vs mock-incomplete vs env-missing."""
    msg = str(exc)
    exc_name = type(exc).__name__

    # Mock incompleteness — render hit a part of streamlit our mock
    # doesn't fully implement
    mock_indicators = (
        "_MockProxy",
        "unsupported format string",
        "unsupported operand type",
    )
    if any(ind in msg for ind in mock_indicators):
        return "MOCK_GAP"

    # Environment/data missing — render couldn't find a data file
    if exc_name in ("FileNotFoundError", "PermissionError"):
        return "DATA_MISSING"

    # Likely real bugs — runtime errors in render logic itself
    real_bug_types = (
        "KeyError", "AttributeError", "TypeError",
        "ValueError", "IndexError", "NameError",
        "UnboundLocalError", "ZeroDivisionError",
    )
    if exc_name in real_bug_types:
        return "REAL_BUG"

    return "UNKNOWN"


def _install_dynamic_mock():
    """Switch the streamlit mock into dynamic mode.

    Important: we don't delete + reinstall streamlit, because modules
    that already did `import streamlit as st` hold a reference to the
    OLD module object — they wouldn't see the new one. Instead we
    update the existing mock's session_state in place, which all
    importers can see via attribute access at call time.
    """
    sys.path.insert(0, str(REPO))
    if "streamlit" not in sys.modules:
        # Fresh install
        from tests.helpers.streamlit_mock import install
        install(dynamic=True)
        return

    # Update existing mock to dynamic mode
    st = sys.modules["streamlit"]
    from tests.helpers.streamlit_mock import _MockProxy
    for key in (
        "user_manager", "execute_manager", "ri_pipeline_manager",
        "product_manager", "pipeline_manager", "leave_manager",
        "hr_manager", "cascade_manager", "validation_manager",
        "reporting_line_manager",
    ):
        st.session_state[key] = _MockProxy()
    st.session_state["user_data"] = {
        "username": "test_user",
        "full_name": "Test User",
        "role": "Managing Director",
        "staff_code": "EXEC-MD-001",
        "active": True,
        "permissions": [],
    }
    st.session_state["username"] = "test_user"
    st._is_dynamic_mode = True

    # Also re-import hub_render modules in case they cached anything
    # from the previous static-only state
    for k in list(sys.modules):
        if k.endswith("_hub_render"):
            del sys.modules[k]


def smoke_one_render(
    module_path: str,
    fn_name: str,
    actor: str = DEFAULT_ACTOR,
    timeout: int = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    """Run a single render function and report its status."""
    result: Dict[str, Any] = {
        "module": module_path,
        "function": fn_name,
        "status": "PASS",
        "category": None,
        "error": None,
        "traceback": None,
    }

    if fn_name in KNOWN_SKIP:
        result["status"] = "SKIP_KNOWN"
        result["category"] = "documented_exemption"
        result["error"] = KNOWN_SKIP[fn_name]
        return result

    try:
        mod = __import__(module_path, fromlist=[fn_name])
        fn: Callable = getattr(mod, fn_name)
    except Exception as exc:
        result["status"] = "FAIL"
        result["category"] = "IMPORT_FAIL"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()
        return result

    try:
        with _alarm(timeout):
            fn(actor)
    except TimeoutError:
        result["status"] = "TIMEOUT"
        result["category"] = "timeout"
        result["error"] = f"exceeded {timeout}s"
    except BaseException as exc:
        # Catch _StreamlitStop and similar — intentional gating
        exc_name = type(exc).__name__
        if "Stop" in exc_name or "stop" in str(exc).lower()[:30]:
            result["status"] = "STOP"
            result["category"] = "access_gating"
            result["error"] = f"{exc_name}: {exc}"
            return result
        result["status"] = "FAIL"
        result["category"] = _classify_failure(exc)
        result["error"] = f"{exc_name}: {str(exc)[:200]}"
        result["traceback"] = traceback.format_exc()

    return result


def smoke_test_renders(
    timeout: int = DEFAULT_TIMEOUT,
    actor: str = DEFAULT_ACTOR,
) -> Dict[str, Any]:
    """Run dynamic smoke on every render in RENDER_REGISTRY.

    Returns a summary dict with per-render results, aggregates, and
    classification breakdown.
    """
    _install_dynamic_mock()

    results: List[Dict[str, Any]] = []
    for module_path, fn_name in RENDER_REGISTRY:
        results.append(smoke_one_render(module_path, fn_name, actor, timeout))

    # Aggregates
    summary: Dict[str, Any] = {
        "total": len(results),
        "passed": sum(1 for r in results if r["status"] == "PASS"),
        "stopped": sum(1 for r in results if r["status"] == "STOP"),
        "timeout": sum(1 for r in results if r["status"] == "TIMEOUT"),
        "skipped": sum(1 for r in results if r["status"] == "SKIP_KNOWN"),
        "failed": sum(1 for r in results if r["status"] == "FAIL"),
        "results": results,
    }

    # Of failures, classify
    summary["real_bugs"] = sum(
        1 for r in results if r["status"] == "FAIL" and r["category"] == "REAL_BUG"
    )
    summary["mock_gaps"] = sum(
        1 for r in results if r["status"] == "FAIL" and r["category"] == "MOCK_GAP"
    )
    summary["data_missing"] = sum(
        1 for r in results if r["status"] == "FAIL" and r["category"] == "DATA_MISSING"
    )

    # Effective pass rate excludes intentional STOP and documented SKIP
    effective_total = summary["total"] - summary["stopped"] - summary["skipped"]
    summary["effective_total"] = effective_total
    summary["effective_pass_rate"] = (
        summary["passed"] / effective_total if effective_total else 1.0
    )

    summary["failures"] = [
        {
            "function": r["function"],
            "module": r["module"],
            "status": r["status"],
            "category": r["category"],
            "error": r["error"],
        }
        for r in results
        if r["status"] in ("FAIL", "TIMEOUT")
    ]

    return summary


def format_dynamic_summary(report: Dict[str, Any]) -> str:
    """Human-readable dynamic smoke summary."""
    lines = []
    lines.append(
        f"Dynamic render smoke — {report['total']} renders "
        f"(effective {report['effective_total']})"
    )
    lines.append(f"  PASS:        {report['passed']}")
    lines.append(f"  STOP:        {report['stopped']}  (intentional access gating)")
    lines.append(f"  SKIP_KNOWN:  {report['skipped']}  (documented exemptions)")
    lines.append(f"  TIMEOUT:     {report['timeout']}")
    lines.append(f"  FAIL:        {report['failed']}")
    if report["failed"]:
        lines.append(f"    of which REAL_BUG:     {report['real_bugs']}")
        lines.append(f"    of which MOCK_GAP:     {report['mock_gaps']}")
        lines.append(f"    of which DATA_MISSING: {report['data_missing']}")
    lines.append(f"  effective pass rate:  {report['effective_pass_rate']:.1%}")

    if report["failures"]:
        lines.append("")
        lines.append("Failures:")
        for f in report["failures"][:15]:
            lines.append(
                f"  {f['function']:40s}  [{f['category'] or f['status']}]  "
                f"{(f['error'] or '')[:60]}"
            )

    return "\n".join(lines)


if __name__ == "__main__":
    report = smoke_test_renders()
    print(format_dynamic_summary(report))
    sys.exit(0 if report["effective_pass_rate"] == 1.0 else 1)
