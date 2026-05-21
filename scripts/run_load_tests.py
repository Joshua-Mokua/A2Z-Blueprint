"""scripts/run_load_tests.py — Run the Standard #5 k6 load test suite.

Purpose: drive the four k6 scripts in tests/load/, collect their JSON
summaries, and aggregate them into a single load_results.json that the
G19 audit gate parses.

Pre-requisites:
  - k6 binary installed and on PATH
       https://grafana.com/docs/k6/latest/set-up/install-k6/
  - The A2Z FastAPI server running and reachable (default http://localhost:8502)
  - A test user able to log in (default william001 / ECOStaff001)

Environment variables:
  A2Z_API_BASE       Target API base URL (default: http://localhost:8502)
  A2Z_TEST_USER      Login username     (default: william001)
  A2Z_TEST_PASS      Login password     (default: ECOStaff001)
  A2Z_LOAD_TESTS     Comma-separated subset to run, e.g.
                     "baseline_smoke,api_p95"
                     (default: all four)
  A2Z_SKIP_HEAVY     If "1", skip concurrent_users (the 1k VU test)

Usage:
  # Local dev, all tests:
  python scripts/run_load_tests.py

  # Only the API p95 test against a remote staging:
  A2Z_API_BASE=https://staging.example.com \\
  A2Z_LOAD_TESTS=api_p95 \\
  python scripts/run_load_tests.py

  # Skip the 1k VU test (e.g. running on a laptop):
  A2Z_SKIP_HEAVY=1 python scripts/run_load_tests.py

Output:
  results/<test>.json       — k6's per-test summary export
  load_results.json         — aggregated audit-friendly summary

Exit code: 0 on success (all tests passed their thresholds),
           1 if any test failed thresholds OR k6 isn't installed,
           2 if the API is unreachable.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOAD_DIR = ROOT / "tests" / "load"
RESULTS_DIR = ROOT / "results"
SUMMARY_PATH = ROOT / "load_results.json"

# Tests in order. Each tuple is (script_name, description, target_metric,
# threshold_ms_or_None_for_pass_fail).
TESTS = [
    ("baseline_smoke",     "Sanity: 1 VU, 10s, /api/health",       None),
    ("api_p95",            "Standard #5: API p95 < 200ms",         200),
    ("export_10k",         "Standard #5: Export 10k rows < 10s",   10000),
    ("concurrent_users",   "Standard #5: 1,000+ concurrent users", None),
]


def _check_k6_available() -> bool:
    """k6 is a binary, not a Python lib. Verify it's on PATH."""
    return shutil.which("k6") is not None


def _check_api_reachable(base: str, timeout: float = 5.0) -> bool:
    """Quick HEAD on /api/health. If this fails, no point starting tests."""
    import urllib.request
    import urllib.error
    try:
        req = urllib.request.Request(f"{base}/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as e:
        print(f"  API not reachable at {base}: {e}")
        return False


def _run_one_test(name: str, base: str, env: dict) -> dict:
    """Run a single k6 script, return a dict of {ok, duration_s, summary_path,
    thresholds_passed, error}.

    k6's --summary-export emits a JSON file with the summary metrics.
    Exit code 0 means all thresholds passed; nonzero means at least one failed.
    """
    script = LOAD_DIR / f"{name}.js"
    if not script.exists():
        return {"ok": False, "error": f"script missing: {script}"}

    summary_file = RESULTS_DIR / f"{name}.json"
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    if summary_file.exists():
        summary_file.unlink()

    cmd = [
        "k6", "run",
        "--summary-export", str(summary_file),
        "--quiet",
        str(script),
    ]

    print(f"\n  Running {name} ...")
    print(f"    cmd: {' '.join(cmd)}")
    print(f"    target: {base}")

    start = time.time()
    try:
        result = subprocess.run(
            cmd,
            env=env,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=600,  # 10 min hard cap per test (concurrent_users is ~6 min)
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "k6 process exceeded 10-minute timeout"}

    elapsed = time.time() - start
    thresholds_passed = result.returncode == 0

    out = {
        "ok":                thresholds_passed,
        "duration_s":        round(elapsed, 1),
        "summary_path":      str(summary_file.relative_to(ROOT)),
        "thresholds_passed": thresholds_passed,
        "exit_code":         result.returncode,
    }

    # Capture k6's own threshold breakdown if the summary file was written
    if summary_file.exists():
        try:
            summary = json.loads(summary_file.read_text())
            metrics = summary.get("metrics", {})
            # Pull p95 of http_req_duration (the headline metric)
            req_dur = metrics.get("http_req_duration", {})
            out["http_req_duration_p95_ms"] = round(req_dur.get("p(95)", 0), 1)
            out["http_req_duration_avg_ms"] = round(req_dur.get("avg",   0), 1)
            failed = metrics.get("http_req_failed", {})
            out["http_req_failed_rate"]     = round(failed.get("rate",    0), 4)
            out["iterations"]               = int(metrics.get("iterations", {}).get("count", 0))
            out["vus_max"]                  = int(metrics.get("vus_max",   {}).get("value", 0))
        except Exception as e:
            out["summary_parse_error"] = str(e)

    if result.stdout:
        # Show the last few lines of k6's output (it has its own pretty-printer)
        tail = "\n".join(result.stdout.strip().split("\n")[-10:])
        print(f"    k6 output (last 10 lines):\n{tail}")
    if not thresholds_passed and result.stderr:
        print(f"    k6 stderr:\n{result.stderr.strip()[:500]}")

    return out


def main() -> int:
    base = os.environ.get("A2Z_API_BASE", "http://localhost:8502")
    requested = os.environ.get("A2Z_LOAD_TESTS", "").strip()
    skip_heavy = os.environ.get("A2Z_SKIP_HEAVY") == "1"

    print(f"A2Z MIS 360 — Standard #5 load test runner")
    print(f"  Target:    {base}")
    print(f"  Tests dir: {LOAD_DIR.relative_to(ROOT)}")

    # Pre-flight checks
    if not _check_k6_available():
        print("\n  ERROR: k6 binary not found on PATH.")
        print("  Install: https://grafana.com/docs/k6/latest/set-up/install-k6/")
        return 1
    if not _check_api_reachable(base):
        print(f"\n  ERROR: cannot reach {base}/api/health")
        print("  Start the API: python -m utils.api")
        return 2

    # Build the test list
    selected = TESTS
    if requested:
        wanted = {t.strip() for t in requested.split(",") if t.strip()}
        selected = [t for t in TESTS if t[0] in wanted]
    if skip_heavy:
        selected = [t for t in selected if t[0] != "concurrent_users"]
    if not selected:
        print("  ERROR: no tests selected")
        return 1

    print(f"  Will run:  {', '.join(t[0] for t in selected)}")

    # Inherit + augment env so k6 scripts see A2Z_API_BASE etc.
    env = os.environ.copy()
    env["A2Z_API_BASE"] = base

    overall_start = time.time()
    results = []
    for name, desc, _target, _threshold in selected:
        result = _run_one_test(name, base, env)
        result["test"]        = name
        result["description"] = desc
        results.append(result)

    overall_elapsed = time.time() - overall_start

    # Aggregate
    summary = {
        "schema_version":     1,
        "run_at":              datetime.now(timezone.utc).isoformat(),
        "target_base":         base,
        "overall_duration_s":  round(overall_elapsed, 1),
        "tests":               results,
        "all_passed":          all(r.get("ok", False) for r in results),
        "summary":             {
            "total_tests":   len(results),
            "passed":        sum(1 for r in results if r.get("ok")),
            "failed":        sum(1 for r in results if not r.get("ok")),
        },
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, default=str))

    # Console summary
    print("\n" + "=" * 72)
    print(f"Load test summary — {summary['summary']['passed']}/{summary['summary']['total_tests']} passed")
    print("=" * 72)
    for r in results:
        mark = "✅" if r.get("ok") else "❌"
        p95  = r.get("http_req_duration_p95_ms")
        p95_str = f"  p95={p95}ms" if p95 is not None else ""
        print(f"  {mark} {r['test']:<22} {r['duration_s']:>6}s{p95_str}")
        if not r.get("ok") and r.get("error"):
            print(f"     error: {r['error']}")
    print(f"\n  Aggregated summary written to: {SUMMARY_PATH.relative_to(ROOT)}")
    print(f"  Per-test details in:           {RESULTS_DIR.relative_to(ROOT)}/")

    return 0 if summary["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
