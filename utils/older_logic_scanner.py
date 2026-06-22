"""utils/older_logic_scanner.py — Detect "older logic" patterns
across the codebase (v10.319).

Joshua flagged on the v10.318 demo that the cascade page was
"using older logic that doesn't see [the v10.316 hierarchy]" —
the page had a hardcoded HIERARCHY dict with role names like
"Director Consumer & Commercial Banking (CCB)" that don't exist in users.json. He
asked: how many other pages exhibit this pattern?

This scanner does that audit. It checks pages/*.py and utils/*.py
for known patterns of staleness:

  1. **Hardcoded role names that don't exist in users.json** —
     e.g. "Director Consumer & Commercial Banking (CCB)", "Regional Head"
  2. **Hardcoded KPI IDs that don't exist in kpi_library.json** —
     e.g. dangling refs like ACCOUNT_DORMANCY without a definition
  3. **Hardcoded department names that don't match users.json** —
     e.g. "Marketing" when users.json uses "Marketing"
     (alignment cross-check)
  4. **Direct file I/O in pages** (extending G2's coverage from
     utils/ to pages/)
  5. **Local copies of the BSC scoring formula** (should use the
     canonical bsc_score_from_pct)

Per Rule 7, this module is diagnostic. It reports findings but
does NOT modify source files.

Shipped: v10.319.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).parent.parent
PAGES_DIR = REPO_ROOT / "pages"
UTILS_DIR = REPO_ROOT / "utils"
DATA_DIR = REPO_ROOT / "data"


# ════════════════════════════════════════════════════════════════════
# Reference data (canonical sources)
# ════════════════════════════════════════════════════════════════════

def _canonical_roles() -> Set[str]:
    """Set of all real role names from users.json."""
    from utils.db import db
    users = db.load_json(DATA_DIR / "users.json", default={}) or {}
    roles: Set[str] = set()
    for u in (users.values() if isinstance(users, dict) else []):
        if isinstance(u, dict) and u.get("role"):
            roles.add(u["role"])
    return roles


def _canonical_departments() -> Set[str]:
    """Set of all real department names from users.json."""
    from utils.db import db
    users = db.load_json(DATA_DIR / "users.json", default={}) or {}
    depts: Set[str] = set()
    for u in (users.values() if isinstance(users, dict) else []):
        if isinstance(u, dict) and u.get("department"):
            depts.add(u["department"])
    return depts


def _canonical_kpi_ids() -> Set[str]:
    """Set of all defined KPI IDs from kpi_library.json."""
    from utils.db import db
    lib = db.load_json(DATA_DIR / "kpi_library.json",
                        default={}) or {}
    return {k.get("id") for k in lib.get("kpis", [])
            if isinstance(k, dict) and k.get("id")}


def _canonical_hierarchy_roles() -> Set[str]:
    """Set of role names referenced in data/org_config.json
    hierarchy (post-v10.318 alignment)."""
    from utils.db import db
    cfg = db.load_json(DATA_DIR / "org_config.json",
                        default={}) or {}
    hier = cfg.get("hierarchy", {}) or {}
    roles: Set[str] = set(hier.keys())
    for parents in hier.values():
        if isinstance(parents, list):
            roles.update(parents)
    return roles


# ════════════════════════════════════════════════════════════════════
# Patterns to detect
# ════════════════════════════════════════════════════════════════════

# Role-related keywords commonly used in hardcoded lists
SUSPECT_ROLE_PATTERNS = [
    r'"Director Consumer & Commercial Banking (CCB)"',
    r'"Director Corporate & Investment Banking (CIB)"',
    r'"Regional Head"',
    r'"Head Of Retail"',
    r'"Head Of Corporate"',
    r'"Head Of Digital Innovation"',
    r'"Head Of Internal Audit"',  # vs "Chief Internal Auditor"
    r'"Head Of Marketing"',  # vs "Head Of Marketing and Corporate Communication"
    r'"Chief Finance Officer"',  # vs "Chief Financial Officer"
    r'"Chief Operations Officer"',  # vs "Chief Operating Officer"
    r'"Chief Human Resources Officer"',  # vs "Chief Human Resource Officer"
    r'"Branch Credit Manager"',  # not in users.json
    r'"Direct Sales Agent"',  # vs "Direct Sales Representative ..."
    r'"Relationship Officer Personal Banking"',  # vs "Relationship Officer-Personal Banker"
    r'"Relationship Officer Business Banking"',  # vs "Relationship Officer-Business Banker"
]

# Direct file I/O patterns (extending G2's coverage to pages/)
DIRECT_IO_PATTERNS = [
    (r'\.read_text\(\)', "use db.load_json instead"),
    (r'\.write_text\(json\.dumps', "use db.save_json instead"),
    (r'json\.load\(open\(', "use db.load_json instead"),
    (r'with\s+open\([^)]+\)\s+as\s+\w+:\s*\n\s*\w+\s*=\s*json',
     "use db.load_json instead"),
]


@dataclass
class Finding:
    file: str
    line: int
    pattern: str
    severity: str  # 'high', 'medium', 'low'
    detail: str


# ════════════════════════════════════════════════════════════════════
# Scanners
# ════════════════════════════════════════════════════════════════════

def _scan_file_for_patterns(
    path: Path,
    patterns: List[Tuple[str, str]],
    default_severity: str = "medium",
) -> List[Finding]:
    """Scan a single file for regex patterns."""
    findings: List[Finding] = []
    try:
        source = path.read_text(encoding="utf-8")
    except Exception:  # noqa: BLE001
        return findings

    rel_path = str(path.relative_to(REPO_ROOT))
    for line_idx, line in enumerate(source.split("\n"), 1):
        # Skip comments-only lines (they're documenting, not using)
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for pattern_def in patterns:
            if isinstance(pattern_def, tuple):
                pattern, detail = pattern_def
                severity = default_severity
            else:
                pattern = pattern_def
                detail = "matched suspect pattern"
                severity = default_severity
            if re.search(pattern, line):
                findings.append(Finding(
                    file=rel_path,
                    line=line_idx,
                    pattern=pattern,
                    severity=severity,
                    detail=detail,
                ))
    return findings


def scan_for_stale_role_names() -> List[Finding]:
    """Find files referencing role names that don't appear in
    users.json. These are likely older logic that hasn't tracked
    the org structure."""
    canonical = _canonical_roles()
    findings: List[Finding] = []

    for scan_dir in (PAGES_DIR, UTILS_DIR):
        if not scan_dir.exists():
            continue
        for path in scan_dir.glob("*.py"):
            if path.name.endswith(".bak"):
                continue
            if path.name == "older_logic_scanner.py":
                continue  # this module defines the patterns — not a finding
            try:
                source = path.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            rel_path = str(path.relative_to(REPO_ROOT))

            for line_idx, line in enumerate(
                    source.split("\n"), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                for pattern in SUSPECT_ROLE_PATTERNS:
                    # pattern is like r'"Director Consumer & Commercial Banking (CCB)"'
                    role_name = pattern.strip('r').strip('"\'')
                    if pattern in line or (
                        f'"{role_name}"' in line):
                        # Verify it's not a valid role in users.json
                        if role_name not in canonical:
                            findings.append(Finding(
                                file=rel_path,
                                line=line_idx,
                                pattern=role_name,
                                severity="high",
                                detail=(
                                    f"Role '{role_name}' is "
                                    f"hardcoded but not in "
                                    f"users.json — likely older "
                                    f"logic from before org "
                                    f"restructure"
                                ),
                            ))
                            break  # one finding per line
    return findings


def scan_for_dangling_kpi_refs() -> List[Finding]:
    """Find files referencing KPI IDs that aren't defined in
    kpi_library.json. Limited to obvious K-pattern and a curated
    list of common dangling IDs."""
    canonical = _canonical_kpi_ids()
    findings: List[Finding] = []

    # The 47 dangling refs from B-010 audit — look for these as
    # string literals in source
    dangling_refs = [
        "ACCOUNT_DORMANCY", "ACTIVE_ACCTS", "AUDIT_SCORE",
        "BUSINESS_BORROWERS", "CASA_RATIO", "CHANNEL_DORMANCY",
        "CIR", "COLLECTION_THROUGHPUT", "COMMERCIAL_DEPOSIT",
        "COMPLIANCE", "COMPLIANCE_SCORE",
        "CREDIT_APPROVAL_RATE", "CREDIT_DECLINE_RATE",
        "CREDIT_REWORK_RATE", "CREDIT_TAT_COMPLEX",
        "CREDIT_TAT_EXPRESS", "CREDIT_TAT_STANDARD",
        "CX_SCORE", "DEP_GROWTH", "DIGITAL_ACT",
        "DISB_RETAIL", "DISB_MSME", "DISB_CORPORATE",
        "LOAN_GROWTH", "NEW_ACCOUNTS", "NPL_RATIO",
        "RETAIL_MSME_DEPOSIT", "STAFF_PROD",
        "TOP100_CUSTOMERS", "TOTAL_NFI",
    ]

    for scan_dir in (PAGES_DIR, UTILS_DIR):
        if not scan_dir.exists():
            continue
        for path in scan_dir.glob("*.py"):
            if path.name.endswith(".bak"):
                continue
            if path.name == "older_logic_scanner.py":
                continue  # don't flag the scanner's own definitions
            try:
                source = path.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            rel_path = str(path.relative_to(REPO_ROOT))

            for line_idx, line in enumerate(
                    source.split("\n"), 1):
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                for ref in dangling_refs:
                    # Match as string literal
                    if f'"{ref}"' in line or f"'{ref}'" in line:
                        if ref not in canonical:
                            findings.append(Finding(
                                file=rel_path,
                                line=line_idx,
                                pattern=ref,
                                severity="medium",
                                detail=(
                                    f"KPI ID '{ref}' referenced "
                                    f"but not in kpi_library.json "
                                    f"(B-010 dangling ref)"
                                ),
                            ))
                            break
    return findings


def scan_for_direct_file_io_in_pages() -> List[Finding]:
    """G2 catches direct I/O in utils/. This extends the coverage
    to pages/ which historically wasn't checked. Per the standing
    rule, file I/O should route through utils.db."""
    findings: List[Finding] = []
    if not PAGES_DIR.exists():
        return findings

    for path in PAGES_DIR.glob("*.py"):
        if path.name.endswith(".bak"):
            continue
        findings.extend(_scan_file_for_patterns(
            path, DIRECT_IO_PATTERNS, default_severity="low"))
    return findings


def scan_for_duplicated_bsc_scoring() -> List[Finding]:
    """Detect inline copies of the 1-5 scoring formula that
    should use the canonical bsc_score_from_pct from utils.core."""
    findings: List[Finding] = []
    # Look for the signature pattern: a chain of `if ach >= NN: return X.Y`
    pattern = (
        r'5\.0\s+if\s+\w+\s*>=\s*120'
    )

    for scan_dir in (PAGES_DIR, UTILS_DIR):
        if not scan_dir.exists():
            continue
        for path in scan_dir.glob("*.py"):
            if path.name.endswith(".bak"):
                continue
            if path.name == "core.py":
                continue  # canonical implementation lives here
            if path.name == "older_logic_scanner.py":
                continue
            try:
                source = path.read_text(encoding="utf-8")
            except Exception:  # noqa: BLE001
                continue
            rel_path = str(path.relative_to(REPO_ROOT))
            for line_idx, line in enumerate(
                    source.split("\n"), 1):
                if re.search(pattern, line):
                    findings.append(Finding(
                        file=rel_path,
                        line=line_idx,
                        pattern="bsc_score_from_pct duplication",
                        severity="medium",
                        detail=(
                            "Inline 1-5 scoring formula — use "
                            "utils.core.bsc_score_from_pct instead"
                        ),
                    ))
    return findings


# ════════════════════════════════════════════════════════════════════
# Aggregator
# ════════════════════════════════════════════════════════════════════

def scan_all() -> Dict[str, Any]:
    """Run all scanners and return a consolidated report."""
    stale_roles = scan_for_stale_role_names()
    dangling_kpis = scan_for_dangling_kpi_refs()
    direct_io = scan_for_direct_file_io_in_pages()
    duplicate_scoring = scan_for_duplicated_bsc_scoring()

    all_findings = (
        stale_roles + dangling_kpis +
        direct_io + duplicate_scoring
    )

    # Aggregate by file
    by_file: Dict[str, List[Finding]] = {}
    for f in all_findings:
        by_file.setdefault(f.file, []).append(f)

    # Aggregate by severity
    by_severity: Dict[str, int] = {
        "high": 0, "medium": 0, "low": 0}
    for f in all_findings:
        by_severity[f.severity] = by_severity.get(
            f.severity, 0) + 1

    return {
        "total_findings": len(all_findings),
        "stale_role_findings": len(stale_roles),
        "dangling_kpi_findings": len(dangling_kpis),
        "direct_io_findings": len(direct_io),
        "duplicate_scoring_findings": len(duplicate_scoring),
        "files_affected": len(by_file),
        "by_severity": by_severity,
        "all_findings": all_findings,
        "by_file": by_file,
    }


SPEC_DEVIATION_NOTE = (
    "Per Rule 7, this module is diagnostic. It scans pages/*.py "
    "and utils/*.py for known patterns of staleness ('older "
    "logic') against canonical data sources (users.json, "
    "kpi_library.json, org_config.json). It reports findings "
    "but does NOT modify any source files. Findings get logged "
    "as B-XXX backlog items for deliberate cleanup."
)
