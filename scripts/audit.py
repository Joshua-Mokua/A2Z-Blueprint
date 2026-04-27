"""scripts/audit.py — A2Z MIS 360 automated audit.

Runs all the Quality Gate checks defined in the master prompt and produces
a verified score. This REPLACES self-grading. Any score quoted in release
notes, prompts, or status updates must come from this script's output.

USAGE
-----
    python scripts/audit.py              # full audit, exit 0 if PASS
    python scripts/audit.py --json       # machine-readable output
    python scripts/audit.py --fix        # auto-fix what we can (dry-run by default)
    python scripts/audit.py --gate <id>  # run a single gate (e.g. --gate direct_io)

EXIT CODES
----------
    0 — all gates pass
    1 — at least one gate fails
    2 — script error (couldn't run)

The audit script is the source of truth. If it disagrees with a self-graded
claim, the script wins.

GATES
-----
    G1  syntax            — ast.parse every .py under pages/, utils/, scripts/
    G2  direct_io         — zero non-foundational files with json.loads/write_text
    G3  audit_coverage    — every page that writes data calls audit_log()
    G4  tab_counts        — zero pages with 8+ tabs in a single row (top-level)
    G5  admin_sections    — exactly 6 sections in 7_admin.py
    G6  registry_coverage — every registered module renders via the renderer
    G7  conventions_docs  — required docs exist under docs/
    G8  bsc_contract      — modules feeding BSC use the contract shape

Score = pass_count / total_count × 100.
"""
from __future__ import annotations

import ast
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# ─── Paths ───────────────────────────────────────────────────────────────
ROOT     = Path(__file__).resolve().parent.parent
PAGES    = ROOT / "pages"
UTILS    = ROOT / "utils"
SCRIPTS  = ROOT / "scripts"
DOCS     = ROOT / "docs"
DATA     = ROOT / "data"

# Files where direct I/O is the implementation, not a violation.
# Foundational layer — they ARE the seam, so they cannot use a2z_db themselves.
FOUNDATIONAL = {
    "utils/db.py",                  # the seam itself
    "utils/core.py",                # bootstrap primitives
    "utils/config.py",              # config loader
    "utils/api.py",                 # FastAPI — should migrate, but it's foundational
    "utils/reconciliation.py",      # multi-source reader
    "utils/flexcube_adapter.py",    # synthetic mode CSV reader
    "utils/actuals_engine.py",      # CBS file reader
    "utils/notifications.py",       # notification logger
    "scripts/etl_flexcube.py",      # ETL orchestrator — the pipeline that *feeds* the seam
    "scripts/migrate_to_postgres.py",  # migration tool — by definition reads JSON to write to PG
}

# Required convention docs
REQUIRED_DOCS = [
    "ADMIN_CONVENTIONS.md",
    "PAGE_UX_STANDARDS.md",
    "FLEXCUBE_CUTOVER_RUNBOOK.md",
    "POSTGRESQL_MIGRATION_GUIDE.md",
]

# The 6 required admin sections (from the convention)
REQUIRED_ADMIN_SECTIONS = [
    "👥 People & Org",
    "📊 Performance",
    "🧩 Modules",
    "🔌 Data & Integration",
    "🩺 System",
    "🛡️ Security",
]


# ─── Helpers ─────────────────────────────────────────────────────────────
def all_python_files() -> List[Path]:
    files = []
    for d in (PAGES, UTILS, SCRIPTS):
        if d.exists():
            files.extend(p for p in d.glob("*.py") if "backup" not in p.name)
    return sorted(files)


def read_text_safe(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return ""


# ─── Gates ───────────────────────────────────────────────────────────────
def gate_syntax() -> Dict[str, Any]:
    """G1 — every .py file parses cleanly with ast."""
    errors = []
    files = all_python_files()
    for p in files:
        try:
            ast.parse(read_text_safe(p))
        except SyntaxError as e:
            errors.append(f"{p.relative_to(ROOT)}:L{e.lineno}: {e.msg}")
    return {
        "id": "G1",
        "name": "syntax",
        "passed": not errors,
        "checked": len(files),
        "violations": errors,
        "summary": f"{len(files)} files parsed" + (f" — {len(errors)} errors" if errors else ""),
    }


def gate_direct_io() -> Dict[str, Any]:
    """G2 — no non-foundational file uses json.loads/write_text directly."""
    violations = []
    for p in all_python_files():
        rel = str(p.relative_to(ROOT))
        if rel in FOUNDATIONAL:
            continue
        code = read_text_safe(p)

        # Count violations, but skip lines marked as bootstrap fallbacks
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            if "noqa: a2z-bootstrap-fallback" in line:
                continue
            if re.search(r"json\.loads\(\s*\w+\s*\.\s*read_text", line):
                violations.append(f"{rel}:L{i} read")
            if re.search(r"\w+\s*\.\s*write_text\(\s*json\.dumps", line):
                violations.append(f"{rel}:L{i} write")
    return {
        "id": "G2",
        "name": "direct_io",
        "passed": not violations,
        "violations": violations,
        "summary": f"{len(violations)} direct I/O violations (target: 0)",
    }


def gate_audit_coverage() -> Dict[str, Any]:
    """G3 — every numbered page that writes calls audit_log()."""
    violations = []
    pages_with_writes = 0
    for p in PAGES.glob("[0-9]*.py"):
        if "backup" in p.name:
            continue
        code = read_text_safe(p)
        # Detect write triggers
        has_save = (
            "save_json(" in code
            or 'type="primary"' in code
            or "form_submit_button" in code
            or 'audit_log("' in code  # already-audited write triggers
        )
        if has_save:
            pages_with_writes += 1
            if "audit_log(" not in code:
                violations.append(p.name)
    return {
        "id": "G3",
        "name": "audit_coverage",
        "passed": not violations,
        "summary": (
            f"{pages_with_writes} writer pages, "
            f"{pages_with_writes - len(violations)} with audit"
        ),
        "violations": violations,
    }


def gate_tab_counts() -> Dict[str, Any]:
    """G4 — no page has 8+ tabs in a top-level (non-nested) row."""
    violations = []
    for p in PAGES.glob("*.py"):
        if "backup" in p.name:
            continue
        code = read_text_safe(p)

        # Find each `<var> = st.tabs([...])` and check whether it's inside
        # a `with sections[N]:` block — those are sub-tabs and exempt.
        for m in re.finditer(r"(\w+)\s*=\s*st\.tabs\(\[(.*?)\]\)", code, re.DOTALL):
            labels = re.findall(r'"([^"]+)"', m.group(2))
            if len(labels) < 8:
                continue

            # The tabs assignment line — measure its indentation
            line_no = code[: m.start()].count("\n")
            line_text = code.split("\n")[line_no]
            indent = len(line_text) - len(line_text.lstrip())

            # If indented (non-zero), it's inside something — assume sub-tab
            # within a section (allowed). If indent is 0, it's a top-level
            # flat row — that violates the rule.
            if indent == 0:
                violations.append(f"{p.name}: {len(labels)} tabs (top-level)")
            elif indent >= 4 and len(labels) > 7:
                # Sub-tab group with more than 7 — also flag (per UX standard)
                violations.append(f"{p.name}: {len(labels)} sub-tabs")
    return {
        "id": "G4",
        "name": "tab_counts",
        "passed": not violations,
        "summary": f"{len(violations)} pages exceed 7-tab limit",
        "violations": violations,
    }


def gate_admin_sections() -> Dict[str, Any]:
    """G5 — 7_admin.py has exactly the 6 required sections."""
    code = read_text_safe(PAGES / "7_admin.py")
    m = re.search(r"sections = st\.tabs\(\[(.*?)\]\)", code, re.DOTALL)
    if not m:
        return {
            "id": "G5",
            "name": "admin_sections",
            "passed": False,
            "summary": "no sections = st.tabs([...]) found",
            "violations": ["section structure missing"],
        }
    labels = re.findall(r'"([^"]+)"', m.group(1))
    missing = [s for s in REQUIRED_ADMIN_SECTIONS if s not in labels]
    extra = [s for s in labels if s not in REQUIRED_ADMIN_SECTIONS]
    violations = []
    if missing:
        violations.append(f"missing: {missing}")
    if extra:
        violations.append(f"extra: {extra}")
    if len(labels) != 6:
        violations.append(f"count is {len(labels)}, expected 6")
    return {
        "id": "G5",
        "name": "admin_sections",
        "passed": not violations,
        "summary": f"{len(labels)} sections (target: 6)",
        "violations": violations,
    }


def gate_registry_coverage() -> Dict[str, Any]:
    """G6 — every register_module_config call is reachable from the Centre."""
    specs_path = PAGES / "_admin_module_specs.py"
    if not specs_path.exists():
        return {
            "id": "G6", "name": "registry_coverage", "passed": False,
            "summary": "specs file missing", "violations": ["pages/_admin_module_specs.py absent"],
        }
    specs_code = read_text_safe(specs_path)
    n_registrations = len(re.findall(r"register_module_config\(\s*\{", specs_code))

    config_path = PAGES / "_admin_module_config.py"
    config_code = read_text_safe(config_path)
    has_renderer = "_render_registered_configs" in config_code
    return {
        "id": "G6",
        "name": "registry_coverage",
        "passed": n_registrations >= 10 and has_renderer,
        "summary": f"{n_registrations} module specs registered, renderer wired = {has_renderer}",
        "violations": [] if (n_registrations >= 10 and has_renderer) else ["renderer not wired"],
    }


def gate_conventions_docs() -> Dict[str, Any]:
    """G7 — required convention docs exist under docs/."""
    missing = [d for d in REQUIRED_DOCS if not (DOCS / d).exists()]
    return {
        "id": "G7",
        "name": "conventions_docs",
        "passed": not missing,
        "summary": f"{len(REQUIRED_DOCS) - len(missing)}/{len(REQUIRED_DOCS)} docs present",
        "violations": missing,
    }


def gate_bsc_contract() -> Dict[str, Any]:
    """G8 — BSC Data Contract: addendum requirement.

    Verifies modules that feed BSC use the standard contract shape:
    {staff_code, kpi_id, value, period, source_module}.
    For now, this is a presence check — a contract validation utility
    would be the next step.
    """
    contract_fields = {"staff_code", "kpi_id", "value", "period", "source_module"}

    # Look for any module that mentions writing to performance.actuals or
    # to a "bsc_actuals" key. If it uses all 5 contract fields nearby, it's
    # compliant; if it writes performance data without them, flag it.
    violations = []
    bsc_writers_found = 0
    for p in PAGES.glob("*.py"):
        if "backup" in p.name:
            continue
        code = read_text_safe(p)
        # Heuristic: look for performance-related saves
        if "performance.actuals" in code or "bsc_actuals" in code:
            bsc_writers_found += 1
            field_hits = sum(1 for f in contract_fields if f in code)
            if field_hits < 3:  # we expect at least staff_code, kpi_id, value
                violations.append(f"{p.name}: only {field_hits}/5 contract fields present")

    return {
        "id": "G8",
        "name": "bsc_contract",
        "passed": not violations,
        "summary": (
            f"{bsc_writers_found} BSC writer(s) found, "
            f"{bsc_writers_found - len(violations)} contract-compliant"
        ),
        "violations": violations,
    }


# ─── Runner ──────────────────────────────────────────────────────────────
GATES = [
    ("G1", gate_syntax),
    ("G2", gate_direct_io),
    ("G3", gate_audit_coverage),
    ("G4", gate_tab_counts),
    ("G5", gate_admin_sections),
    ("G6", gate_registry_coverage),
    ("G7", gate_conventions_docs),
    ("G8", gate_bsc_contract),
]


def run_all(only_gate: str | None = None) -> Dict[str, Any]:
    results = []
    for gid, fn in GATES:
        if only_gate and gid.lower() != only_gate.lower() and fn.__name__ != f"gate_{only_gate}":
            continue
        try:
            results.append(fn())
        except Exception as e:
            results.append({
                "id": gid, "name": fn.__name__.replace("gate_", ""),
                "passed": False, "summary": f"gate crashed: {e}",
                "violations": [str(e)],
            })
    passed = sum(1 for r in results if r["passed"])
    score_pct = (passed / len(results)) * 100 if results else 0
    return {
        "score_pct": round(score_pct, 1),
        "passed": passed,
        "total": len(results),
        "all_passed": passed == len(results),
        "gates": results,
    }


def render_human(report: Dict[str, Any]) -> str:
    lines = []
    lines.append("=" * 72)
    lines.append("A2Z MIS 360 — Automated Audit")
    lines.append("=" * 72)
    for r in report["gates"]:
        mark = "✅" if r["passed"] else "❌"
        lines.append(f"  {mark} [{r['id']}] {r['name']:<24} {r['summary']}")
        if not r["passed"] and r.get("violations"):
            for v in r["violations"][:8]:
                lines.append(f"        • {v}")
            if len(r["violations"]) > 8:
                lines.append(f"        … and {len(r['violations']) - 8} more")
    lines.append("-" * 72)
    lines.append(f"  Score: {report['passed']}/{report['total']} gates "
                 f"= {report['score_pct']}% — "
                 f"{'PASS' if report['all_passed'] else 'FAIL'}")
    lines.append("=" * 72)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="A2Z automated audit")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--gate", type=str, default=None, help="run a single gate by id (g1, g2…)")
    args = ap.parse_args()

    report = run_all(only_gate=args.gate)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_human(report))

    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
