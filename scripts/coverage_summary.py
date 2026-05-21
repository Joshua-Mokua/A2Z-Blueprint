"""scripts/coverage_summary.py — Print a UTF-8-safe summary of
coverage.xml's contents for direction-setting.

Why this script exists:
  - audit.py's G18 gate produces structured details, but the audit's
    human-readable rendering uses UTF-8 characters that crash
    Windows/cp1252 consoles when piped through PowerShell's
    Select-String filter.
  - audit_completion_state.py also has the encoding-on-print bug
    (fixed in v10.101 alongside the v10.100 audit.py fix, but for
    this drop we want a script that works NOW without depending on
    that fix).
  - This script uses ASCII-only output. It runs anywhere coverage.xml
    exists, no patching of other scripts needed.

Usage:
    python scripts/coverage_summary.py
    python scripts/coverage_summary.py --top 30      # show top N gaps
    python scripts/coverage_summary.py --threshold-spec  # only spec targets

Output sections:
  1. Overall line coverage
  2. Per-spec-module status (Standard #4 thresholds)
  3. Top N biggest coverage gaps in utils/ by uncovered-lines
  4. Pages/ aggregate
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.etree import ElementTree as ET


# Force ASCII so this script never crashes on cp1252.
def _safe_print(s: str) -> None:
    """Print with errors='replace' fallback for older streams."""
    try:
        print(s)
    except UnicodeEncodeError:
        # Last-resort: encode to ASCII with replacement
        print(s.encode("ascii", errors="replace").decode("ascii"))


# Standard #4 thresholds (mirror G18 in scripts/audit.py).
# `aspirational` markers are scoping decisions documented in v10.106:
# the target is preserved for future work but not enforced.
THRESHOLDS = {
    "utils/bsc_engine.py": {"threshold": 95, "aspirational": False},
    "utils/db.py":         {"threshold": 90, "aspirational": True},
    "utils/auth_jwt.py":   {"threshold": 95, "aspirational": False},
    "utils/core_kpi.py":   {"threshold": 85, "aspirational": False},
    "pages/":              {"threshold": 70, "aspirational": True},
}


def _parse_coverage_xml(path: Path):
    """Return (overall_pct, per_file_pct_dict, per_dir_pcts_dict).

    Cobertura coverage.xml stores filenames RELATIVE to a <source> root
    (e.g., "db.py" not "utils/db.py"), with the actual root paths in a
    <sources> block at the top. We resolve each class's filename by
    finding which source root contains it on disk. After resolution,
    paths look like "utils/db.py" so they match Standard #4 thresholds.
    """
    import os
    tree = ET.parse(path)
    root = tree.getroot()
    overall_pct = round(float(root.get("line-rate", "0")) * 100, 1)

    # Extract source-root basenames (pages, scripts, utils, ...).
    # Manual split handles both forward and back slashes regardless of
    # what platform the script runs on (audit may run on Linux against
    # a coverage.xml produced on Windows; os.path.basename's behaviour
    # depends on the runtime OS, not the path origin).
    source_dirs = []
    for src_el in root.iter("source"):
        if not src_el.text:
            continue
        normalized = src_el.text.replace("\\", "/").rstrip("/")
        base = normalized.rsplit("/", 1)[-1] if "/" in normalized else normalized
        if base:
            source_dirs.append(base)

    # The script file is in scripts/, so project root is its parent
    project_root = Path(__file__).resolve().parent.parent

    def _resolve(raw_filename: str) -> str:
        """Map cobertura's source-root-relative filename to project-relative."""
        rel = raw_filename.replace("\\", "/")
        if "/" in rel and rel.split("/", 1)[0] in source_dirs:
            return rel
        for sd in source_dirs:
            if (project_root / sd / rel).exists():
                return f"{sd}/{rel}"
        return rel

    per_file = {}
    per_dir = {}
    for cls in root.iter("class"):
        raw_filename = cls.get("filename", "")
        if not raw_filename:
            continue
        filename = _resolve(raw_filename)
        try:
            rate = float(cls.get("line-rate", "0")) * 100
        except ValueError:
            continue

        # Also capture line counts so we can rank by uncovered-lines.
        lines = list(cls.iter("line"))
        total_lines = len(lines)
        covered = sum(
            1 for ln in lines if int(ln.get("hits", "0")) > 0)

        per_file[filename] = {
            "pct": round(rate, 1),
            "total_lines": total_lines,
            "covered_lines": covered,
            "uncovered_lines": total_lines - covered,
        }

        # Track aggregates per top-level directory
        top = filename.split("/")[0] if "/" in filename else "(root)"
        per_dir.setdefault(top, []).append(rate)

    per_dir_avg = {
        d: round(sum(rates) / len(rates), 1)
        for d, rates in per_dir.items()
        if rates
    }
    return overall_pct, per_file, per_dir_avg


def main():
    ap = argparse.ArgumentParser(
        description="UTF-8-safe coverage summary")
    ap.add_argument(
        "--top", type=int, default=20,
        help="Number of biggest gaps to show (default: 20)")
    ap.add_argument(
        "--threshold-spec", action="store_true",
        help="Only show Standard #4 spec-target modules")
    args = ap.parse_args()

    cov_xml = Path(__file__).resolve().parent.parent / "coverage.xml"
    if not cov_xml.exists():
        _safe_print(
            f"ERROR: {cov_xml} not found.\n"
            f"Run `pytest --cov --cov-report=xml tests/` first."
        )
        sys.exit(1)

    overall, per_file, per_dir = _parse_coverage_xml(cov_xml)

    _safe_print("")
    _safe_print("=" * 70)
    _safe_print("  COVERAGE SUMMARY (Standard #4 / G18 thresholds)")
    _safe_print("=" * 70)
    _safe_print("")
    _safe_print(f"  OVERALL:  {overall}%  ({len(per_file)} files measured)")
    _safe_print("")

    # --- Spec target modules ---
    _safe_print("  STANDARD #4 SPEC TARGETS:")
    _safe_print(
        f"  {'module':40s}  {'pct':>6s}  {'target':>6s}  status")
    _safe_print(f"  {'-'*40}  {'-'*6}  {'-'*6}  {'-'*7}")

    for target_path, spec in sorted(THRESHOLDS.items()):
        target_pct = spec["threshold"]
        aspirational = spec.get("aspirational", False)

        if target_path.endswith("/"):
            # Directory aggregate
            dir_name = target_path.rstrip("/")
            actual = per_dir.get(dir_name, 0.0)
        else:
            entry = per_file.get(target_path)
            actual = entry["pct"] if entry else 0.0

        if actual >= target_pct:
            status = "PASS"
        elif aspirational:
            status = "ASPIRE"  # deferred per scoping decision; not a failure
        else:
            status = "FAIL"
        gap = target_pct - actual if actual < target_pct else 0
        gap_str = f"  (-{gap:.1f}pp)" if gap > 0 else ""
        if aspirational and status != "PASS":
            gap_str += "  [deferred]"
        _safe_print(
            f"  {target_path:40s}  {actual:>5.1f}%  "
            f"{target_pct:>5d}%  {status}{gap_str}"
        )

    _safe_print("")
    if args.threshold_spec:
        return

    # --- Per-directory aggregates ---
    _safe_print("  PER-DIRECTORY AGGREGATES:")
    for d in sorted(per_dir):
        rate = per_dir[d]
        n_files = sum(
            1 for f in per_file if f.startswith(d + "/")
            or f == d
        )
        _safe_print(
            f"    {d:30s}  {rate:>5.1f}%  ({n_files} files)")
    _safe_print("")

    # --- Biggest gaps in utils/ by uncovered lines ---
    _safe_print(f"  TOP {args.top} BIGGEST GAPS IN utils/ "
                f"(by uncovered-line count):")
    utils_files = [
        (f, info) for f, info in per_file.items()
        if f.startswith("utils/")
    ]
    utils_files.sort(
        key=lambda x: -x[1]["uncovered_lines"])
    _safe_print(
        f"  {'file':50s}  {'pct':>6s}  "
        f"{'uncov':>6s}  {'total':>6s}")
    _safe_print(f"  {'-'*50}  {'-'*6}  {'-'*6}  {'-'*6}")
    for f, info in utils_files[:args.top]:
        _safe_print(
            f"  {f:50s}  {info['pct']:>5.1f}%  "
            f"{info['uncovered_lines']:>6d}  "
            f"{info['total_lines']:>6d}"
        )
    _safe_print("")


if __name__ == "__main__":
    main()
