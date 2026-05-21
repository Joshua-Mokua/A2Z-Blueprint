"""scripts/run_engine_self_tests.py — v10.74 ops hygiene.

Discovers every utils/*.py module that defines a self_test function
and runs each one. Prints one line per engine showing pass/fail,
captures full output for failures, and exits 0 if all pass / 1 if
any fail.

Used by:
  - GitHub Actions CI (.github/workflows/ci.yml) — fail build on
    any engine regression
  - pages/98_platform_health.py — green/red dashboard for operators

Optional flags:
  --json           emit JSON summary to stdout (suppresses per-engine
                   pass lines; failure detail still goes to stderr)
  --filter PATTERN substring filter on engine name; e.g. --filter
                   trade_finance runs only the 4 TF engines

Pure stdlib. No third-party dependencies. Per Rule 1, every
{passed,failed} entry surfaces engine_name + duration_seconds +
captured_output (on failure) + framework_ref to ENH-Engine §self_test.
"""
from __future__ import annotations

import argparse
import importlib
import io
import json
import sys
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
UTILS_DIR = REPO_ROOT / "utils"

# Ensure repo root is on sys.path so `import utils.X` works regardless
# of cwd (CI runs from repo root; the health page may run from
# elsewhere). Idempotent: only add if not already present.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def discover_engines() -> List[str]:
    """Return module names (utils.X) for engines with self_test()."""
    if not UTILS_DIR.exists():
        return []
    found: List[str] = []
    for path in sorted(UTILS_DIR.glob("*.py")):
        if path.stem.startswith("_") or path.stem == "__init__":
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        # Quick text check before importing — avoids importing every
        # utils module just to find the self-testing ones
        if "def self_test(" in text:
            found.append(path.stem)
    return found


def run_one(name: str) -> Dict[str, object]:
    """Import and execute utils.{name}.self_test(). Capture all
    stdout/stderr. Return a structured result dict."""
    started = time.perf_counter()
    out = io.StringIO()
    err = io.StringIO()
    status = "passed"
    detail = ""
    try:
        with redirect_stdout(out), redirect_stderr(err):
            mod = importlib.import_module(f"utils.{name}")
            if not hasattr(mod, "self_test"):
                status = "skipped"
                detail = "no self_test() function"
            else:
                mod.self_test()
    except SystemExit as e:
        status = "failed"
        code = getattr(e, "code", 1)
        detail = f"SystemExit({code})"
    except KeyboardInterrupt:
        raise
    except Exception as e:  # pragma: no cover
        status = "failed"
        detail = f"{type(e).__name__}: {e}"
    duration = time.perf_counter() - started
    return {
        "engine": name,
        "status": status,
        "duration_seconds": round(duration, 3),
        "detail": detail,
        "stdout": out.getvalue(),
        "stderr": err.getvalue(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run engine self-tests across utils/")
    parser.add_argument(
        "--json", action="store_true",
        help="emit JSON summary on stdout")
    parser.add_argument(
        "--filter", default="",
        help="substring filter on engine name")
    args = parser.parse_args()

    engines = discover_engines()
    if args.filter:
        engines = [e for e in engines if args.filter in e]

    if not engines:
        if args.json:
            print(json.dumps({
                "total": 0, "passed": 0, "failed": 0,
                "skipped": 0, "results": [],
                "framework_ref": (
                    "ENH-Engine §self_test orchestrator "
                    "(scripts/run_engine_self_tests.py)"),
            }))
        else:
            print("No engines with self_test() found", file=sys.stderr)
        return 0

    results: List[Dict[str, object]] = []
    passed = failed = skipped = 0
    if not args.json:
        print(
            f"▶ Running {len(engines)} engine self-tests...",
            file=sys.stderr)
    for name in engines:
        r = run_one(name)
        results.append(r)
        status = r["status"]
        if status == "passed":
            passed += 1
            if not args.json:
                print(
                    f"  ✓ {name}  ({r['duration_seconds']}s)",
                    file=sys.stderr)
        elif status == "failed":
            failed += 1
            if not args.json:
                print(
                    f"  ✗ {name}: {r['detail']} "
                    f"({r['duration_seconds']}s)",
                    file=sys.stderr)
                # Show captured output for failures
                if r["stdout"]:
                    print(
                        "    stdout:", file=sys.stderr)
                    for line in str(r["stdout"]).splitlines():
                        print(f"      {line}", file=sys.stderr)
                if r["stderr"]:
                    print(
                        "    stderr:", file=sys.stderr)
                    for line in str(r["stderr"]).splitlines():
                        print(f"      {line}", file=sys.stderr)
        else:
            skipped += 1
            if not args.json:
                print(
                    f"  ⊘ {name}: {r['detail']}",
                    file=sys.stderr)

    if args.json:
        # Strip captured stdout/stderr for passing engines to keep
        # JSON small — full detail only for failures
        for r in results:
            if r["status"] == "passed":
                r["stdout"] = ""
                r["stderr"] = ""
        print(json.dumps({
            "total": len(engines),
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "results": results,
            "framework_ref": (
                "ENH-Engine §self_test orchestrator "
                "(scripts/run_engine_self_tests.py)"),
        }))
    else:
        print("=" * 60, file=sys.stderr)
        print(
            f"  {passed} passed · {failed} failed · "
            f"{skipped} skipped of {len(engines)} engines",
            file=sys.stderr)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
