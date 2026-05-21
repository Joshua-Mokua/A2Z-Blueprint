"""scripts/run_dependency_audit.py — Run the Standard #9 dependency scan.

Purpose: drive `pip-audit` and `safety` against requirements.txt,
honour `.cve-ignore.json` suppressions, write an audit-friendly
artifact at `dependency_audit_results.json` for G21 to read.

Pre-requisites:
  - `pip-audit` and `safety` installed:
       pip install -r requirements-dev.txt
  - Python 3.11+

Environment variables:
  A2Z_DEP_AUDIT_TARGET    Path to the requirements file to scan
                          (default: requirements.txt)
  A2Z_DEP_AUDIT_SCANNERS  Comma-separated subset, e.g.
                          "pip-audit" or "safety" or "pip-audit,safety"
                          (default: both)

Usage:
  # Scan runtime requirements (the default)
  python scripts/run_dependency_audit.py

  # Scan dev requirements
  A2Z_DEP_AUDIT_TARGET=requirements-dev.txt \\
  python scripts/run_dependency_audit.py

  # Run only pip-audit (e.g. in fast feedback loops)
  A2Z_DEP_AUDIT_SCANNERS=pip-audit \\
  python scripts/run_dependency_audit.py

Output:
  dependency_audit_results.json   — aggregated audit-friendly summary

Exit code: 0 if zero unsuppressed CRITICAL CVEs across all scanners,
           1 if any unsuppressed CRITICAL CVE found,
           2 if neither scanner is installed (sandbox / missing deps).

Suppressions:
  .cve-ignore.json at the project root may contain a list of
  suppressions:
    [
      {
        "id":      "GHSA-xxxx",
        "package": "some-pkg",
        "reason":  "False positive — A2Z does not use the affected method",
        "expires": "2026-12-31"
      }
    ]
  An expired suppression is ignored (the CVE re-fails the gate).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).parent.parent
SUMMARY_PATH = ROOT / "dependency_audit_results.json"
IGNORE_PATH  = ROOT / ".cve-ignore.json"
RAW_DIR      = ROOT / "results" / "depaudit"


# ═══════════════════════════════════════════════════════════════════════
# Suppression handling
# ═══════════════════════════════════════════════════════════════════════

def _load_suppressions() -> List[dict]:
    """Load .cve-ignore.json, drop expired entries, return active list."""
    if not IGNORE_PATH.exists():
        return []
    try:
        raw = json.loads(IGNORE_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"  WARNING: .cve-ignore.json unparseable: {e}", file=sys.stderr)
        return []

    if not isinstance(raw, list):
        print("  WARNING: .cve-ignore.json is not a list — ignoring",
              file=sys.stderr)
        return []

    today = date.today()
    active: List[dict] = []
    expired: List[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        # Required fields: id, reason. Optional: package, expires.
        if "id" not in item or "reason" not in item:
            continue
        exp_str = item.get("expires")
        if exp_str:
            try:
                exp = datetime.strptime(exp_str, "%Y-%m-%d").date()
                if exp < today:
                    expired.append(item)
                    continue
            except ValueError:
                # Bad date format — treat as not-expired (conservative)
                pass
        active.append(item)

    if expired:
        ids = ", ".join(e["id"] for e in expired)
        print(f"  NOTE: {len(expired)} suppression(s) expired and now active: {ids}",
              file=sys.stderr)

    return active


def _is_suppressed(vuln_id: str, package: str, suppressions: List[dict]) -> Optional[dict]:
    """Return the matching suppression dict, or None."""
    for s in suppressions:
        if s.get("id", "").lower() == vuln_id.lower():
            # Match on id alone (canonical), or also verify package if specified
            if "package" in s and s["package"].lower() != package.lower():
                continue
            return s
    return None


# ═══════════════════════════════════════════════════════════════════════
# Tool runners
# ═══════════════════════════════════════════════════════════════════════

def _run_pip_audit(target: Path) -> dict:
    """Run pip-audit, return a dict of {ok, findings, raw_path, error}."""
    if shutil.which("pip-audit") is None:
        return {"ok": False, "error": "pip-audit not on PATH", "findings": []}

    raw_path = RAW_DIR / "pip-audit.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "pip-audit",
        "--requirement", str(target),
        "--format", "json",
        "--output", str(raw_path),
    ]
    print(f"\n  Running pip-audit ...")
    print(f"    cmd: {' '.join(cmd)}")

    try:
        # pip-audit exits 1 when vulns found — that's not a runner error
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                timeout=300)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "pip-audit timed out (5 min)", "findings": []}
    except FileNotFoundError as e:
        return {"ok": False, "error": f"pip-audit not executable: {e}",
                "findings": []}

    if not raw_path.exists():
        return {
            "ok": False,
            "error": f"pip-audit did not produce {raw_path.name}; stderr: {result.stderr[:300]}",
            "findings": [],
        }

    try:
        raw = json.loads(raw_path.read_text())
    except json.JSONDecodeError as e:
        return {"ok": False, "error": f"pip-audit output unparseable: {e}",
                "findings": []}

    # pip-audit JSON format:
    #   {"dependencies": [{"name": ..., "version": ..., "vulns": [{"id": ..., "fix_versions": [...]}]}]}
    findings: List[dict] = []
    deps = raw.get("dependencies", []) if isinstance(raw, dict) else raw
    for dep in deps if isinstance(deps, list) else []:
        pkg = dep.get("name", "?")
        ver = dep.get("version", "?")
        for v in dep.get("vulns", []) or []:
            findings.append({
                "scanner":      "pip-audit",
                "id":           v.get("id", "?"),
                "package":      pkg,
                "version":      ver,
                "fix_versions": v.get("fix_versions", []),
                "description":  v.get("description", ""),
                "severity":     _classify_severity_pip_audit(v),
                "raw":          v,
            })

    return {"ok": True, "findings": findings, "raw_path": str(raw_path),
            "exit_code": result.returncode}


def _classify_severity_pip_audit(v: dict) -> str:
    """pip-audit doesn't always populate severity. Best-effort:
       - explicit aliases CVE-* and CVSS in description → parse score
       - OSV records sometimes ship a `severity` field
       Fallback: 'unknown' (NOT counted as critical)."""
    sev = v.get("severity")
    if sev:
        return str(sev).upper()
    # Some pip-audit JSON shapes include CVSSv3 score in raw form
    aliases = v.get("aliases", []) or []
    cvss = None
    for a in aliases:
        if isinstance(a, str) and a.startswith("CVSS:"):
            try:
                cvss = float(a.split("/")[0].split(":")[1])
                break
            except (ValueError, IndexError):
                pass
    if cvss is not None:
        if cvss >= 9.0:
            return "CRITICAL"
        if cvss >= 7.0:
            return "HIGH"
        if cvss >= 4.0:
            return "MEDIUM"
        return "LOW"
    return "UNKNOWN"


def _run_safety(target: Path) -> dict:
    """Run safety, return a dict similar to _run_pip_audit's."""
    if shutil.which("safety") is None:
        return {"ok": False, "error": "safety not on PATH", "findings": []}

    raw_path = RAW_DIR / "safety.json"
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "safety", "check",
        "--file", str(target),
        "--json",
        "--output", str(raw_path),
    ]
    print(f"\n  Running safety ...")
    print(f"    cmd: {' '.join(cmd)}")

    try:
        # safety exits non-zero when vulns found — not a runner error
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                                timeout=300)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "safety timed out (5 min)", "findings": []}
    except FileNotFoundError as e:
        return {"ok": False, "error": f"safety not executable: {e}",
                "findings": []}

    if not raw_path.exists():
        # safety also accepts stdout output; try parsing stdout as fallback
        if result.stdout:
            try:
                raw = json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"ok": False,
                        "error": f"safety did not produce {raw_path.name} and stdout not JSON; stderr: {result.stderr[:300]}",
                        "findings": []}
        else:
            return {"ok": False,
                    "error": f"safety did not produce {raw_path.name}; stderr: {result.stderr[:300]}",
                    "findings": []}
    else:
        try:
            raw = json.loads(raw_path.read_text())
        except json.JSONDecodeError as e:
            return {"ok": False, "error": f"safety output unparseable: {e}",
                    "findings": []}

    # safety JSON format (v3.x):
    #   {"vulnerabilities": [{"vulnerability_id": ..., "package_name": ..., "analyzed_version": ..., "advisory": ..., "severity": ...}]}
    # (older formats use different keys; handle both)
    findings: List[dict] = []
    vulns = []
    if isinstance(raw, dict):
        vulns = raw.get("vulnerabilities", raw.get("vulns", []))
    elif isinstance(raw, list):
        vulns = raw  # legacy 2.x format

    for v in vulns or []:
        vuln_id = v.get("vulnerability_id") or v.get("id") or v.get("CVE") or "?"
        pkg = v.get("package_name") or v.get("package") or "?"
        ver = v.get("analyzed_version") or v.get("installed_version") or "?"
        sev = v.get("severity") or _classify_severity_safety(v)
        findings.append({
            "scanner":      "safety",
            "id":           vuln_id,
            "package":      pkg,
            "version":      ver,
            "fix_versions": v.get("fixed_versions", []),
            "description":  v.get("advisory") or v.get("description") or "",
            "severity":     str(sev).upper() if sev else "UNKNOWN",
            "raw":          v,
        })

    return {"ok": True, "findings": findings, "raw_path": str(raw_path),
            "exit_code": result.returncode}


def _classify_severity_safety(v: dict) -> str:
    """Safety's severity field varies. Best-effort fallback via CVSS."""
    cvss = v.get("cvssv3_score") or v.get("cvssv2_score")
    if cvss is not None:
        try:
            cvss_f = float(cvss)
            if cvss_f >= 9.0:
                return "CRITICAL"
            if cvss_f >= 7.0:
                return "HIGH"
            if cvss_f >= 4.0:
                return "MEDIUM"
            return "LOW"
        except (ValueError, TypeError):
            pass
    return "UNKNOWN"


# ═══════════════════════════════════════════════════════════════════════
# Aggregation
# ═══════════════════════════════════════════════════════════════════════

def main() -> int:
    target_str = os.environ.get("A2Z_DEP_AUDIT_TARGET", "requirements.txt")
    target = (ROOT / target_str).resolve()
    requested = os.environ.get("A2Z_DEP_AUDIT_SCANNERS", "pip-audit,safety")
    scanners = {s.strip() for s in requested.split(",") if s.strip()}

    print("A2Z MIS 360 — Standard #9 dependency audit")
    print(f"  Target:     {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}")
    print(f"  Scanners:   {', '.join(sorted(scanners))}")

    if not target.exists():
        print(f"\n  ERROR: target file not found: {target}")
        return 1

    # Suppressions
    suppressions = _load_suppressions()
    print(f"  Suppressions (active): {len(suppressions)}")

    # Run scanners
    results: List[dict] = []
    if "pip-audit" in scanners:
        results.append({"scanner": "pip-audit", **_run_pip_audit(target)})
    if "safety" in scanners:
        results.append({"scanner": "safety", **_run_safety(target)})

    if not any(r.get("ok") for r in results):
        # Neither scanner ran — sandbox / missing deps. Exit 2 (informational).
        print("\n  Neither scanner ran successfully.")
        for r in results:
            if r.get("error"):
                print(f"    {r['scanner']}: {r['error']}")
        # Still write an artifact so G21 sees "scanners unavailable" cleanly
        summary = {
            "schema_version": 1,
            "run_at":         datetime.now(timezone.utc).isoformat(),
            "target":         str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
            "scanners_run":   [r["scanner"] for r in results if r.get("ok")],
            "scanners_failed": [{"scanner": r["scanner"], "error": r.get("error", "?")}
                                for r in results if not r.get("ok")],
            "suppressions":   suppressions,
            "findings":       [],
            "by_severity":    {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0},
            "suppressed_count": 0,
            "unsuppressed_critical": 0,
            "all_passed":     False,  # we can't claim pass without running
            "status":         "scanner_unavailable",
        }
        SUMMARY_PATH.write_text(json.dumps(summary, indent=2))
        return 2

    # Aggregate findings
    all_findings: List[dict] = []
    for r in results:
        if r.get("ok"):
            all_findings.extend(r.get("findings", []))

    # Apply suppressions
    suppressed_count = 0
    final_findings: List[dict] = []
    for f in all_findings:
        s = _is_suppressed(f["id"], f["package"], suppressions)
        if s is not None:
            f = dict(f)
            f["suppressed"] = True
            f["suppression_reason"] = s.get("reason", "")
            suppressed_count += 1
        else:
            f["suppressed"] = False
        final_findings.append(f)

    # Severity histogram
    by_severity = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    unsuppressed_critical = 0
    for f in final_findings:
        sev = f.get("severity", "UNKNOWN")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        if sev == "CRITICAL" and not f.get("suppressed", False):
            unsuppressed_critical += 1

    summary = {
        "schema_version":  1,
        "run_at":           datetime.now(timezone.utc).isoformat(),
        "target":           str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
        "scanners_run":     [r["scanner"] for r in results if r.get("ok")],
        "scanners_failed":  [{"scanner": r["scanner"], "error": r.get("error", "?")}
                             for r in results if not r.get("ok")],
        "suppressions":     suppressions,
        "findings":         final_findings,
        "by_severity":      by_severity,
        "suppressed_count": suppressed_count,
        "unsuppressed_critical": unsuppressed_critical,
        "all_passed":       unsuppressed_critical == 0,
        "status":           "ok" if unsuppressed_critical == 0 else "critical_cves_found",
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    # Console summary
    print("\n" + "=" * 72)
    print(f"Dependency audit — {len(final_findings)} finding(s) total")
    print("=" * 72)
    print(f"  Scanners run:       {', '.join(summary['scanners_run']) or '(none)'}")
    if summary["scanners_failed"]:
        for sf in summary["scanners_failed"]:
            print(f"  Scanner failed:     {sf['scanner']}: {sf['error']}")
    print(f"  Suppressed:         {suppressed_count}")
    print(f"  By severity:")
    for sev in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"):
        print(f"    {sev:<10} {by_severity.get(sev, 0)}")
    print(f"  Unsuppressed CRITICAL: {unsuppressed_critical} (target: 0)")
    print(f"\n  Aggregated summary written to: {SUMMARY_PATH.relative_to(ROOT)}")

    return 0 if unsuppressed_critical == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
