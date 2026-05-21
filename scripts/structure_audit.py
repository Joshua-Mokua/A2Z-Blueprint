"""scripts/structure_audit.py — v10.38: Structural Hygiene CLI.

Wraps utils.structure_audit_core. Two modes:

  python3 scripts/structure_audit.py
      Prints summary to stdout, writes report.md + JSON,
      exits 0 if HARD count <= baseline, 1 if regression.

  python3 scripts/structure_audit.py --capture-baseline
      Writes the current state of HARD findings to
      docs/structure_audit_baseline.json. Use after intentional
      improvements to update the gate.

The G128 audit gate calls this same baseline-comparison logic.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Project root = parent of scripts/
_SCRIPT = Path(__file__).resolve()
_PROJECT_ROOT = _SCRIPT.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from utils.structure_audit_core import (    # noqa: E402
    StructureAuditEngine, compute_baseline, compare_to_baseline,
    FindingSeverity)

BASELINE_PATH = _PROJECT_ROOT / "docs" / "structure_audit_baseline.json"
REPORT_PATH = _PROJECT_ROOT / "docs" / "structure_audit_report.md"
DEPS_JSON_PATH = _PROJECT_ROOT / "docs" / "module_deps.json"


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(
        description="Structural hygiene audit (v10.38).")
    parser.add_argument(
        "--capture-baseline",
        action="store_true",
        help="Snapshot current HARD findings as baseline.")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress summary output.")
    args = parser.parse_args(argv)

    engine = StructureAuditEngine(project_root=_PROJECT_ROOT)
    result = engine.audit()

    # Always write fresh markdown report + deps.json
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    md = engine.render_markdown_report(result)
    REPORT_PATH.write_text(md, encoding="utf-8")

    # Module-level deps for the docs site
    deps_payload = {
        "n_modules_scanned": result.n_modules_scanned,
        "n_imports": result.n_total_imports,
        "summary": dict(result.summary),
    }
    DEPS_JSON_PATH.write_text(
        json.dumps(deps_payload, indent=2), encoding="utf-8")

    if args.capture_baseline:
        baseline = compute_baseline(result)
        BASELINE_PATH.write_text(
            json.dumps(baseline, indent=2), encoding="utf-8")
        if not args.quiet:
            n_hard = len(result.hard_failures())
            print(
                f"Captured baseline: {n_hard} HARD findings "
                f"recorded as the new floor.")
            print(f"Baseline saved → {BASELINE_PATH}")
        return 0

    # Compare against existing baseline (if any)
    if not BASELINE_PATH.exists():
        if not args.quiet:
            print(
                "No baseline found. Run with --capture-baseline "
                "to establish one.")
            print(
                f"Current HARD findings: "
                f"{len(result.hard_failures())}")
        # Without a baseline, treat as informational only
        return 0

    baseline = json.loads(
        BASELINE_PATH.read_text(encoding="utf-8"))
    comparison = compare_to_baseline(result, baseline)

    if not args.quiet:
        print(
            f"Modules scanned: {result.n_modules_scanned} | "
            f"Imports: {result.n_total_imports} | "
            f"Findings: {len(result.findings)} "
            f"(HARD={len(result.hard_failures())})")
        print(comparison.summary)
        if comparison.is_regression:
            print()
            print("New HARD findings:")
            for f in comparison.new_findings:
                print(
                    f"  {f.category.value} @ {f.module_path}: "
                    f"{f.description}")
                if f.observed_value:
                    print(f"    {f.observed_value}")

    return 1 if comparison.is_regression else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
