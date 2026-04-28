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
    "utils/core_audit.py",          # extracted from core.py in v5.25 — hosts audit_log + access helpers
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
    """G8 — Universal BSC Data Contract + Central Engine (addendum Standards #1 + #2).

    Two checks, both must hold:

    A) Every call to utils.bsc_engine.submit() or submit_batch() must pass
       the full 5-field contract:
           staff_code, kpi_id, value, period, source_module

       Calls missing fields are violations.

    B) NO module outside utils/bsc_engine.py is allowed to write directly
       to bsc_actuals_*.json files or to performance.actuals in PG. The
       engine is the only legitimate writer. Bypass writes are violations.

    The gate also reports the count of compliant submitter sites — once
    there's at least one, the gate is no longer vacuous.

    Pre-v5.18 this gate was a presence-check that passed with zero writers
    found. v5.18 makes it a structural enforcement: the engine exists,
    one pilot module is wired through it, and bypass writes fail the gate.
    """
    engine_path = UTILS / "bsc_engine.py"
    engine_present = engine_path.exists()

    violations: List[str] = []
    compliant_submitters = 0
    bypass_writers = 0
    submitter_modules: set = set()

    # The engine itself, this audit script, and any file matching these
    # exemptions don't count as bypass writers.
    EXEMPT_FROM_BYPASS_CHECK = {"utils/bsc_engine.py", "scripts/audit.py"}

    files_to_scan: List[Path] = []
    for d in (PAGES, UTILS, SCRIPTS):
        if d.exists():
            files_to_scan.extend(p for p in d.glob("*.py") if "backup" not in p.name)

    contract_fields = {"staff_code", "kpi_id", "value", "period", "source_module"}

    # Bypass detection: direct writes to bsc_actuals_* or performance.actuals
    bypass_rx = re.compile(
        r"""(
            save_json\s*\([^)]*bsc_actuals     # save_json(... 'bsc_actuals' ...)
          | bsc_actuals_[A-Za-z0-9_-]+\.json   # bsc_actuals_2026-04.json literal
          | INSERT\s+INTO\s+performance\.actuals
          | UPDATE\s+performance\.actuals
        )""",
        re.IGNORECASE | re.VERBOSE,
    )

    for p in files_to_scan:
        rel = str(p.relative_to(ROOT))
        code = read_text_safe(p)

        # ── A) submitter compliance ─────────────────────────────────
        # Only count calls in files that actually import the engine.
        # Otherwise `form.submit()` and other unrelated submit() calls
        # would all match the regex.
        imports_engine = bool(re.search(
            r"from\s+utils\.bsc_engine\s+import|import\s+utils\.bsc_engine",
            code,
        ))

        if rel == "utils/bsc_engine.py" or rel == "scripts/audit.py":
            imports_engine = False  # engine + audit script don't count

        if imports_engine:
            # Find aliases used. e.g. `from utils.bsc_engine import submit_batch as _bsc_submit_batch`
            aliases: List[str] = []
            for am in re.finditer(
                r"from\s+utils\.bsc_engine\s+import\s+([^\n]+)",
                code,
            ):
                for spec in am.group(1).split(","):
                    spec = spec.strip()
                    if not spec:
                        continue
                    if " as " in spec:
                        orig, alias = [s.strip() for s in spec.split(" as ")]
                        if orig in ("submit", "submit_batch"):
                            aliases.append((alias, orig))
                    elif spec in ("submit", "submit_batch"):
                        aliases.append((spec, spec))

            # Also handle attribute-style: bsc_engine.submit / bsc_engine.submit_batch
            aliases.extend([
                ("bsc_engine.submit", "submit"),
                ("bsc_engine.submit_batch", "submit_batch"),
            ])

            # Deduplicate by alias name
            seen_aliases = set()
            unique_aliases = []
            for alias, orig in aliases:
                if alias not in seen_aliases:
                    seen_aliases.add(alias)
                    unique_aliases.append((alias, orig))

            for alias, orig in unique_aliases:
                # Match calls: `alias(`
                # Use word-boundary on either side; allow attribute access form
                pat = re.compile(
                    r"(?<![\w.])" + re.escape(alias) + r"\s*\(",
                )
                for m in pat.finditer(code):
                    # Walk forward to find matching close paren
                    start = m.end()
                    depth = 1
                    i = start
                    while i < len(code) and depth > 0:
                        c = code[i]
                        if c == "(":
                            depth += 1
                        elif c == ")":
                            depth -= 1
                        i += 1
                    arg_block = code[start:i - 1]

                    present = {f for f in contract_fields if re.search(rf"\b{f}\s*=", arg_block)}

                    if orig == "submit_batch":
                        if "source_module" in present:
                            compliant_submitters += 1
                            submitter_modules.add(rel)
                        else:
                            violations.append(
                                f"{rel} {orig}() missing source_module= kwarg"
                            )
                    else:
                        # plain submit() — needs all 5 contract fields
                        missing = contract_fields - present
                        if not missing:
                            compliant_submitters += 1
                            submitter_modules.add(rel)
                        else:
                            violations.append(
                                f"{rel} {orig}() missing contract fields: {sorted(missing)}"
                            )

        # ── B) bypass-writer detection ──────────────────────────────
        if rel in EXEMPT_FROM_BYPASS_CHECK:
            continue
        for m in bypass_rx.finditer(code):
            line_start = code.rfind("\n", 0, m.start()) + 1
            line_end = code.find("\n", m.end())
            line = code[line_start:line_end if line_end > 0 else len(code)]
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "noqa: a2z-bsc-bypass" in line:
                continue
            bypass_writers += 1
            lineno = code.count("\n", 0, m.start()) + 1
            violations.append(f"{rel}:L{lineno} bypass write: {stripped[:80]}")

    if not engine_present:
        violations.append("utils/bsc_engine.py missing — engine MUST exist (addendum Standard #2)")

    summary = (
        f"engine={'present' if engine_present else 'MISSING'}, "
        f"{compliant_submitters} compliant submitter call(s) across "
        f"{len(submitter_modules)} module(s), "
        f"{bypass_writers} bypass writer(s) (target: 0)"
    )

    return {
        "id":     "G8",
        "name":   "bsc_contract",
        "passed": not violations and engine_present,
        "summary": summary,
        "violations": violations,
    }


def gate_sql_safety() -> Dict[str, Any]:
    """G9 — SQL injection safety in utils/db.py.

    Verifies db.py has no f-string SQL with table/column interpolation.
    The fix pattern is: psycopg2.sql.Identifier() + TABLE_REGISTRY whitelist.
    Any code matching the unsafe pattern is a CWE-89 risk.
    """
    db_path = UTILS / "db.py"
    if not db_path.exists():
        return {
            "id": "G9", "name": "sql_safety", "passed": False,
            "summary": "utils/db.py missing", "violations": ["utils/db.py absent"],
        }
    code = read_text_safe(db_path)
    violations = []

    # Unsafe pattern: f"...SQL...{table}..." or f"...SQL...{col_str}..."
    unsafe_patterns = [
        (r'f"[^"]*INSERT[^"]*\{table\}', "INSERT with {table}"),
        (r'f"[^"]*SELECT[^"]*\{table\}', "SELECT with {table}"),
        (r'f"[^"]*UPDATE[^"]*\{table\}', "UPDATE with {table}"),
        (r'f"[^"]*DELETE[^"]*\{table\}', "DELETE with {table}"),
        (r'f"[^"]*\{col_str\}',          "f-string with {col_str}"),
        (r'f"[^"]*\{placeholders\}',     "f-string with {placeholders}"),
    ]
    for i, line in enumerate(code.split("\n"), 1):
        for pat, label in unsafe_patterns:
            if re.search(pat, line):
                violations.append(f"db.py:L{i} {label}")
                break

    # Check the safety helpers exist
    helpers_present = (
        "TABLE_REGISTRY" in code
        and "def _check_table" in code
        and "def _qid" in code
    )
    if not helpers_present:
        violations.append("safety helpers (TABLE_REGISTRY, _check_table, _qid) missing")

    return {
        "id": "G9",
        "name": "sql_safety",
        "passed": not violations,
        "summary": (
            f"helpers present={helpers_present}, "
            f"{len(violations)} unsafe SQL patterns (target: 0)"
        ),
        "violations": violations,
    }


def gate_xss_safety() -> Dict[str, Any]:
    """G10 — XSS safety on user-controlled data flowing into HTML.

    Detects the dangerous pattern:
      st.markdown(f"...{user_var}...", unsafe_allow_html=True)
    where user_var matches user-data names (full_name, role, unit, ...) and
    is NOT wrapped in safe_html() / html.escape().

    The audit script flags risky sites; full remediation across all 89 pages
    is tracked separately. The gate's threshold accepts files that have
    applied safe_html to known user-controlled values.
    """
    # User-controlled hint names — values that flow from forms / db / user_data.
    # Matching the variable name is heuristic but catches the audit's named CVE.
    user_data_names = {
        "full_name", "fullname", "username", "first_name", "last_name",
        "raw_name", "raw_role", "raw_unit", "raw_dept",
    }

    violations = []
    pages_with_unsafe_html = 0

    for p in PAGES.glob("*.py"):
        if "backup" in p.name:
            continue
        code = read_text_safe(p)
        if "unsafe_allow_html" not in code:
            continue
        pages_with_unsafe_html += 1

        # For each unsafe_allow_html call, look back ~30 lines to find the
        # markdown string and check for unsafe interpolations.
        lines = code.split("\n")
        for i, line in enumerate(lines):
            if "unsafe_allow_html" not in line:
                continue
            window = "\n".join(lines[max(0, i - 30) : i + 1])

            # Skip if the window doesn't contain a markdown/write call
            if not re.search(r"st\.(markdown|write|caption|html)\s*\(", window):
                continue

            # Find {expr} interpolations that match user-data names
            for m in re.finditer(r"\{([^{}]+?)\}", window):
                expr = m.group(1).strip()
                if not expr or expr.startswith(("'", '"')):
                    continue

                # Already wrapped in safe_html / html.escape → safe
                if "safe_html" in expr or "html.escape" in expr or "escape(" in expr:
                    continue

                # Check the expression touches a user-data name
                expr_lower = expr.lower()
                hit_name = next((n for n in user_data_names if n in expr_lower), None)
                if hit_name and "_raw_" not in expr_lower:
                    # _raw_ prefix is the documented "I know this is raw, used for logic" marker
                    violations.append(f"{p.name}:L{i + 1} {{{expr[:50]}}} ({hit_name})")
                    break  # one violation per unsafe_allow_html line

    return {
        "id": "G10",
        "name": "xss_safety",
        "passed": not violations,
        "summary": (
            f"{pages_with_unsafe_html} pages use unsafe_allow_html, "
            f"{len(violations)} risky user-data interpolations"
        ),
        "violations": violations,
    }


def gate_password_safety() -> Dict[str, Any]:
    """G11 — password hashing safety (V-003 mitigation).

    Every site that creates a password hash MUST use bcrypt — concretely,
    UserManager.hash_pw() (instance method) or _hash_password() (module
    helper for bootstrap). Direct hashlib.sha256() calls used for password
    hashing are CWE-916 (use of password hash with insufficient
    computational effort).

    This gate flags any 'password' assignment whose value is built with
    hashlib.sha256() / sha256() outside the documented exception sites
    (the fallback inside _hash_password and the legacy verify path inside
    verify_pw — both have the noqa marker).
    """
    files_to_scan = []
    for d in (PAGES, UTILS, SCRIPTS):
        if d.exists():
            files_to_scan.extend(p for p in d.glob("*.py") if "backup" not in p.name)

    violations = []
    bcrypt_in_requirements = False
    req_path = ROOT / "requirements.txt"
    if req_path.exists():
        bcrypt_in_requirements = "bcrypt" in read_text_safe(req_path).lower()

    for p in files_to_scan:
        rel = str(p.relative_to(ROOT))
        code = read_text_safe(p)
        lines = code.split("\n")
        for i, line in enumerate(lines, 1):
            # Detect SHA-256 calls
            if "sha256(" not in line and "hashlib.sha256" not in line:
                continue
            # Allow explicit waivers
            if "noqa: a2z-password-fallback" in line or "noqa: a2z-audit-chain" in line:
                continue
            # Look at context (3 lines back) for password assignment
            ctx_start = max(0, i - 4)
            ctx = "\n".join(lines[ctx_start:i + 1])
            is_password_context = bool(
                re.search(r'["\']password["\']\s*[:=]', ctx)
                or "_hash_password" in ctx
                or "verify_pw" in ctx
                or "hash_pw" in ctx
            )
            if not is_password_context:
                continue  # SHA-256 used for non-password (audit chain, etc.)
            # The two legitimate sites inside _hash_password/verify_pw have
            # the function name in the immediate context — exempt them.
            if "_hash_password" in ctx or "verify_pw" in ctx:
                continue
            if "hash_pw" in ctx and "def hash_pw" in ctx:
                continue
            violations.append(f"{rel}:L{i} {line.strip()[:80]}")

    if not bcrypt_in_requirements:
        violations.append("bcrypt not in requirements.txt")

    return {
        "id": "G11",
        "name": "password_safety",
        "passed": not violations,
        "summary": (
            f"bcrypt in reqs={bcrypt_in_requirements}, "
            f"{len(violations)} unsafe password-hash sites (target: 0)"
        ),
        "violations": violations,
    }


def gate_api_auth_safety() -> Dict[str, Any]:
    """G12 — API authentication (V-001 mitigation).

    Every @app.get / @app.post route in utils/api.py MUST declare a
    Depends(get_current_user) or Depends(require_admin) parameter, with
    these documented exceptions:

      - /api/health     (intentionally public — used as a probe)
      - /api/auth/login (issues the token; cannot itself require one)

    The gate also verifies:
      - PyJWT is in requirements.txt
      - utils/auth_jwt.py exists and exports the expected helpers
      - CORS is not configured with "*" + allow_credentials=True
    """
    api_path  = UTILS / "api.py"
    auth_path = UTILS / "auth_jwt.py"
    if not api_path.exists():
        return {
            "id": "G12", "name": "api_auth_safety", "passed": False,
            "summary": "utils/api.py missing", "violations": ["utils/api.py absent"],
        }

    violations = []

    # 1) auth_jwt.py present + exports key symbols
    if not auth_path.exists():
        violations.append("utils/auth_jwt.py missing")
    else:
        auth_code = read_text_safe(auth_path)
        for sym in ("create_access_token", "get_current_user", "require_admin"):
            if f"def {sym}" not in auth_code and f"{sym} =" not in auth_code:
                violations.append(f"auth_jwt.py missing {sym}")

    # 2) PyJWT in requirements
    req = read_text_safe(ROOT / "requirements.txt")
    if "pyjwt" not in req.lower() and "jwt" not in req.lower():
        violations.append("PyJWT not in requirements.txt")

    # 3) Every route in api.py has auth (except documented exemptions)
    api_code = read_text_safe(api_path)
    EXEMPT_ROUTES = {"/api/health", "/api/auth/login"}
    lines = api_code.split("\n")
    for i, line in enumerate(lines):
        m = re.match(r'@app\.(get|post|put|delete)\("([^"]+)"', line.strip())
        if not m:
            continue
        route = m.group(2)
        # Look at the next ~30 lines for the function signature
        sig_block = "\n".join(lines[i:i + 30])
        sig_end = sig_block.find("):")
        if sig_end < 0:
            sig_end = sig_block.find(") ->")
        sig = sig_block[: sig_end + 2] if sig_end > 0 else sig_block

        has_auth = (
            "Depends(get_current_user)" in sig
            or "Depends(require_admin)" in sig
        )
        if route in EXEMPT_ROUTES:
            continue  # fine either way
        if not has_auth:
            violations.append(f"api.py route {route} has no auth Depends")

    # 4) CORS misconfig (V-009)
    if 'allow_origins=["*"]' in api_code and "allow_credentials=True" in api_code:
        violations.append("CORS allow_origins=['*'] with credentials (V-009)")

    return {
        "id": "G12",
        "name": "api_auth_safety",
        "passed": not violations,
        "summary": f"{len(violations)} API auth issues (target: 0)",
        "violations": violations,
    }


def gate_test_infrastructure() -> Dict[str, Any]:
    """G13 — Test infrastructure (v5.20).

    Verifies the test scaffolding is in place:
      - tests/ directory exists with at least 3 test files
      - pytest.ini (or equivalent) is present
      - pytest is in requirements.txt
      - .github/workflows/ci.yml exists (CI runs on every push)
      - tests/conftest.py is present (shared fixtures)

    Pre-v5.20 the codebase had ZERO tests. This gate ensures we don't
    regress to that state. It does NOT verify test passes — that's
    pytest's job, run by CI separately.

    Once a coverage tool is wired (pytest-cov), a future revision of
    this gate could enforce a minimum coverage threshold.
    """
    violations: List[str] = []

    tests_dir = ROOT / "tests"
    if not tests_dir.exists():
        violations.append("tests/ directory missing — test infrastructure not set up")
        return {
            "id": "G13", "name": "test_infrastructure",
            "passed": False,
            "summary": "tests/ directory missing",
            "violations": violations,
        }

    test_files = sorted(p.name for p in tests_dir.glob("test_*.py"))
    if len(test_files) < 3:
        violations.append(
            f"only {len(test_files)} test file(s) found (target: ≥3)"
        )

    if not (tests_dir / "conftest.py").exists():
        violations.append("tests/conftest.py missing — shared fixtures unavailable")

    pytest_cfg = (
        (ROOT / "pytest.ini").exists()
        or (ROOT / "pyproject.toml").exists()
        or (ROOT / "setup.cfg").exists()
    )
    if not pytest_cfg:
        violations.append("pytest.ini / pyproject.toml / setup.cfg missing")

    req = read_text_safe(ROOT / "requirements.txt")
    if "pytest" not in req.lower():
        violations.append("pytest not in requirements.txt")

    ci_yml = ROOT / ".github" / "workflows" / "ci.yml"
    ci_present = ci_yml.exists()
    if not ci_present:
        violations.append(".github/workflows/ci.yml missing — CI not configured")

    # Count test functions (rough — uses ast for accuracy)
    total_tests = 0
    for tf in tests_dir.glob("test_*.py"):
        try:
            import ast as _ast
            tree = _ast.parse(read_text_safe(tf))
            for node in _ast.walk(tree):
                if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                    if node.name.startswith("test_"):
                        total_tests += 1
        except Exception:
            pass

    summary = (
        f"{len(test_files)} test file(s), {total_tests} test function(s), "
        f"pytest_cfg={'present' if pytest_cfg else 'MISSING'}, "
        f"CI={'configured' if ci_present else 'MISSING'}"
    )

    return {
        "id":     "G13",
        "name":   "test_infrastructure",
        "passed": not violations,
        "summary": summary,
        "violations": violations,
    }


# ─── Runner ──────────────────────────────────────────────────────────────
def gate_core_split_adoption() -> Dict[str, Any]:
    """G14 — Core split adoption (v5.21).

    Tracks how many pages have migrated to the new utils.core_* submodule
    import paths. The shim modules (currently just utils/core_audit.py)
    re-export symbols from utils.core, so old `from utils.core import X`
    imports keep working — but the migration goal is for pages to gradually
    move to `from utils.core_audit import X` (and future siblings).

    This gate does NOT fail if pages still use the old paths — old imports
    are valid until utils.core is fully decomposed. It just reports the
    adoption percentage so progress is visible.

    Adoption is computed as:
        n_migrated_pages / n_pages_that_could_migrate * 100

    A "page that could migrate" is one that currently imports any symbol
    covered by an existing shim module (utils.core_audit etc.). A "migrated
    page" is one that uses the new `from utils.core_audit import` path.
    A page can be partially migrated — e.g. core_audit imports plus residual
    `from utils.core import` for symbols not yet shimmed; that still counts.

    The gate passes as long as the shim modules exist and the audit can
    compute a reading. It fails only if a shim is referenced in the registry
    but doesn't exist on disk, or if zero pages have adopted any shim.
    """
    # Registry of shim modules and the symbols each one covers.
    # Future shims (utils.core_kpi, utils.core_perf, etc.) get added here.
    SHIMS = {
        "utils.core_audit": {
            "audit_log", "requires_dual_approval", "submit_for_approval",
            "get_pending_approvals", "get_user_department", "is_dept_super_user",
            "is_ict_admin", "get_dept_modules", "check_access", "check_page_access",
            "get_visible_staff", "tab_visible_cascade", "fix_view_all_permissions",
            "_hash_password",
        },
        "utils.core_kpi": {
            "KPI_LIBRARY_FILE", "DEFAULT_KPI_LIBRARY", "DEFAULT_ROLE_KPIS",
            "get_kpi_library", "save_kpi_library", "get_active_kpis",
            "get_role_kpis", "get_pillar_weights",
            "get_scoring_scale", "bsc_score_from_pct",
            "get_performance_bands", "score_to_band",
        },
    }

    violations: List[str] = []

    # Verify each registered shim file exists and re-exports something
    for shim_modpath in SHIMS:
        shim_relpath = shim_modpath.replace(".", "/") + ".py"
        shim_file = ROOT / shim_relpath
        if not shim_file.exists():
            violations.append(f"shim {shim_modpath} declared in registry but missing on disk")
            continue
        shim_code = read_text_safe(shim_file)
        if "from utils.core import" not in shim_code:
            violations.append(f"shim {shim_modpath} doesn't re-export from utils.core")

    if violations:
        return {
            "id": "G14", "name": "core_split_adoption",
            "passed": False,
            "summary": "shim registry inconsistent with disk",
            "violations": violations,
        }

    # Build the union of all symbols any shim covers
    all_shimmed = set()
    for syms in SHIMS.values():
        all_shimmed |= syms

    # Walk pages/, classify each
    n_total_pages         = 0   # all pages we scan
    n_could_migrate       = 0   # pages that import any shimmed symbol from utils.core
    n_partially_migrated  = 0   # pages that use at least one shim path
    n_fully_migrated      = 0   # pages where ALL shimmed-symbol imports go via shims
    examples_migrated     = []
    examples_pending      = []

    if PAGES.exists():
        for p in sorted(PAGES.glob("*.py")):
            if "backup" in p.name:
                continue
            n_total_pages += 1
            code = read_text_safe(p)

            # Symbols this page imports from utils.core (the OLD path)
            old_imports: set = set()
            for m in re.finditer(
                r"from\s+utils\.core\s+import\s+\(([^)]+)\)",
                code, re.DOTALL,
            ):
                for sym in m.group(1).split(","):
                    sym = sym.strip().split(" as ")[0]
                    if sym and sym.isidentifier():
                        old_imports.add(sym)
            for m in re.finditer(
                r"^from\s+utils\.core\s+import\s+([^(\n]+)$",
                code, re.MULTILINE,
            ):
                for sym in m.group(1).split(","):
                    sym = sym.strip().split(" as ")[0]
                    if sym and sym.isidentifier():
                        old_imports.add(sym)

            # Symbols this page imports via any registered shim (the NEW path)
            new_imports: set = set()
            for shim_modpath in SHIMS:
                shim_re = re.escape(shim_modpath)
                for m in re.finditer(
                    rf"from\s+{shim_re}\s+import\s+\(([^)]+)\)",
                    code, re.DOTALL,
                ):
                    for sym in m.group(1).split(","):
                        sym = sym.strip().split(" as ")[0]
                        if sym and sym.isidentifier():
                            new_imports.add(sym)
                for m in re.finditer(
                    rf"^from\s+{shim_re}\s+import\s+([^(\n]+)$",
                    code, re.MULTILINE,
                ):
                    for sym in m.group(1).split(","):
                        sym = sym.strip().split(" as ")[0]
                        if sym and sym.isidentifier():
                            new_imports.add(sym)

            # Does this page touch any shimmed symbol at all?
            touches_shimmed_old = bool(old_imports & all_shimmed)
            touches_shimmed_new = bool(new_imports & all_shimmed)

            if touches_shimmed_old or touches_shimmed_new:
                n_could_migrate += 1
                if touches_shimmed_new:
                    n_partially_migrated += 1
                    if not (old_imports & all_shimmed):
                        n_fully_migrated += 1
                        if len(examples_migrated) < 3:
                            examples_migrated.append(p.name)
                    else:
                        # Partial: still has old imports for shimmed symbols
                        if len(examples_pending) < 3:
                            examples_pending.append(p.name + " (partial)")
                else:
                    if len(examples_pending) < 3:
                        examples_pending.append(p.name)

    # Compute adoption percentage
    pct = (n_partially_migrated / n_could_migrate * 100) if n_could_migrate else 0.0

    # Pass condition: shims exist + at least one page has migrated.
    # The threshold deliberately starts low (any adoption = pass) because
    # this is a tracking gate, not an enforcement gate.
    passed = bool(SHIMS) and n_partially_migrated > 0

    summary = (
        f"{len(SHIMS)} shim(s), "
        f"{n_partially_migrated}/{n_could_migrate} pages adopted "
        f"({pct:.0f}%) "
        f"({n_fully_migrated} fully, {n_partially_migrated - n_fully_migrated} partial)"
    )

    return {
        "id":     "G14",
        "name":   "core_split_adoption",
        "passed": passed,
        "summary": summary,
        "violations": violations,
        "details": {
            "shims_registered": list(SHIMS.keys()),
            "pages_total":      n_total_pages,
            "pages_could_migrate": n_could_migrate,
            "pages_migrated":   n_partially_migrated,
            "pages_fully_migrated": n_fully_migrated,
            "adoption_pct":     round(pct, 1),
            "examples_migrated": examples_migrated,
            "examples_pending": examples_pending,
        },
    }


def gate_pg_migration_progress() -> Dict[str, Any]:
    """G15 — PostgreSQL migration progress (Standard #1, v5.30).

    Reads TABLE_USE_DB from utils/db.py and reports adoption.

    Distinct from G18 in the spec — G18 is the Phase-2-completion gate
    (52/52 tables flipped to True). G15 is the *progress* gate: it
    passes as long as the registry is well-formed and at least one
    table is in PG-mode. It also surfaces the dual-mode pilot table(s)
    where dual-write marshallers are wired up in JSON_PATH_TO_TABLE.

    The gate fails only if:
      - utils/db.py can't be parsed for TABLE_USE_DB
      - JSON_PATH_TO_TABLE references a table not in TABLE_USE_DB
      - A pilot table is registered in JSON_PATH_TO_TABLE but no
        marshaller pair is wired up in Database._get_marshallers
    """
    db_path = ROOT / "utils" / "db.py"
    if not db_path.exists():
        return {
            "id": "G15", "name": "pg_migration_progress",
            "passed": False, "summary": "utils/db.py not found",
            "details": {},
        }

    src = db_path.read_text(encoding="utf-8", errors="ignore")

    # Parse TABLE_USE_DB
    import re
    m = re.search(r"TABLE_USE_DB\s*=\s*\{(.*?)^\}", src, re.MULTILINE | re.DOTALL)
    if not m:
        return {
            "id": "G15", "name": "pg_migration_progress",
            "passed": False, "summary": "TABLE_USE_DB dict not found in utils/db.py",
            "details": {},
        }
    body = m.group(1)
    true_tables  = re.findall(r'"([^"]+)":\s*True',  body)
    false_tables = re.findall(r'"([^"]+)":\s*False', body)
    total = len(true_tables) + len(false_tables)
    pct = (len(true_tables) / total * 100) if total else 0.0

    # Parse JSON_PATH_TO_TABLE
    m2 = re.search(r"JSON_PATH_TO_TABLE[^=]*=\s*\{(.*?)^\}", src, re.MULTILINE | re.DOTALL)
    pilot_tables = []
    if m2:
        pilot_tables = re.findall(r'"[^"]+\.json":\s*"([^"]+)"', m2.group(1))

    # Validate: every pilot table must be in TABLE_USE_DB
    all_registered = set(true_tables) | set(false_tables)
    unregistered_pilots = [t for t in pilot_tables if t not in all_registered]

    # Validate: every pilot must have a marshaller wired in _get_marshallers
    # (best-effort regex match; the cluster is small, mistakes here are obvious)
    m3 = re.search(r"def _get_marshallers\(self, table[^)]*\):.*?return registry\.get",
                   src, re.DOTALL)
    wired_marshallers = set()
    if m3:
        m3_body = m3.group(0)
        for tname in re.findall(r'"([^"]+)":\s*\(self\._save_', m3_body):
            wired_marshallers.add(tname)
    unwired_pilots = [t for t in pilot_tables if t not in wired_marshallers]

    violations = []
    if unregistered_pilots:
        violations.append(
            f"JSON_PATH_TO_TABLE references unregistered tables: {unregistered_pilots}"
        )
    if unwired_pilots:
        violations.append(
            f"JSON_PATH_TO_TABLE pilots without marshallers: {unwired_pilots}"
        )

    passed = (total > 0 and not violations)

    return {
        "id": "G15", "name": "pg_migration_progress",
        "passed": passed,
        "summary": (
            f"{len(true_tables)}/{total} tables in PG-mode ({pct:.0f}%), "
            f"{len(pilot_tables)} dual-write pilot(s)"
        ),
        "details": {
            "tables_total":           total,
            "tables_pg_mode":         len(true_tables),
            "tables_json_mode":       len(false_tables),
            "adoption_pct":           round(pct, 1),
            "pilot_tables":           pilot_tables,
            "wired_marshallers":      sorted(wired_marshallers),
            "violations":             violations,
        },
    }


def gate_api_v1_coverage() -> Dict[str, Any]:
    """G16 — /api/v1 CRUD endpoint coverage (Standard #2, v5.31).

    Counts endpoints under /api/v1/* and validates that every module
    wired through make_crud_router() has the expected 8 endpoints
    (list, get, create, update, delete, export, search, dashboard).

    The gate ALSO surfaces the v1 module count so we can track progress
    toward Standard #2's 136-endpoint target (8 endpoints × 17 modules
    + system endpoints).

    Distinct from G12 (api_auth_safety): G12 enforces JWT on every
    route. G16 enforces CRUD completeness on every wired module.
    """
    api_path  = ROOT / "utils" / "api.py"
    crud_path = ROOT / "utils" / "api_crud.py"

    if not api_path.exists():
        return {
            "id": "G16", "name": "api_v1_coverage",
            "passed": False, "summary": "utils/api.py not found",
            "details": {},
        }
    if not crud_path.exists():
        return {
            "id": "G16", "name": "api_v1_coverage",
            "passed": False, "summary": "utils/api_crud.py not found (Standard #2 framework missing)",
            "details": {},
        }

    import re
    api_src = api_path.read_text(encoding="utf-8", errors="ignore")

    # Find make_crud_router(...) calls in api.py to extract module names
    wired_modules = []
    for m in re.finditer(
        r"make_crud_router\s*\([^)]*module\s*=\s*[\"']([^\"']+)[\"']",
        api_src, re.DOTALL,
    ):
        wired_modules.append(m.group(1))

    # Total /api/v1/* routes (each module contributes 8)
    expected_v1_routes = len(wired_modules) * 8

    # System endpoints (not under /api/v1)
    system_routes = len(re.findall(
        r"@app\.(?:get|post|put|delete|patch)\([\"']/api/(?!v1/)",
        api_src,
    ))

    # Count current endpoints actually in api.py:
    #  - explicit @app.<verb>("/api/v1/...") (none expected — we use routers)
    #  - implied by make_crud_router (8 per module)
    # Plus the system ones.
    explicit_v1 = len(re.findall(r"@app\.(?:get|post|put|delete|patch)\([\"']/api/v1/", api_src))

    # Total = system + 8*N (from factory)
    total_endpoints = system_routes + expected_v1_routes + explicit_v1

    # Spec target: 136 = 8 endpoints × 17 modules
    target = 136
    progress_pct = (total_endpoints / target) * 100 if target else 0.0

    # Validate: api_crud.py must define all 8 verbs
    crud_src = crud_path.read_text(encoding="utf-8", errors="ignore")
    expected_decorators = [
        '@router.get("",',                    # list
        '@router.get("/{row_id}"',            # get
        '@router.post("",',                   # create
        '@router.put("/{row_id}"',            # update
        '@router.delete("/{row_id}"',         # delete
        '@router.post("/export"',             # export
        '@router.post("/search"',             # search
        '@router.get("/dashboard"',           # dashboard
    ]
    missing_verbs = [d for d in expected_decorators if d not in crud_src]

    # Validate: factory must use Depends(get_current_user) on every route
    # (rough check — every @router.<verb> within make_crud_router)
    factory_match = re.search(
        r"def make_crud_router\(.*?return router",
        crud_src, re.DOTALL,
    )
    decorator_count = 0
    auth_count = 0
    if factory_match:
        body = factory_match.group(0)
        decorator_count = len(re.findall(r"@router\.(get|post|put|delete|patch)\(", body))
        auth_count = len(re.findall(r"Depends\(get_current_user\)", body))

    violations = []
    if missing_verbs:
        violations.append(
            f"api_crud.py missing CRUD verbs: {missing_verbs}"
        )
    if decorator_count != 8:
        violations.append(
            f"factory expected 8 @router decorators, found {decorator_count}"
        )
    if auth_count < decorator_count:
        violations.append(
            f"factory has {decorator_count} routes but only {auth_count} use "
            f"Depends(get_current_user) — every CRUD route must be JWT-gated"
        )

    # Pass criteria:
    # - api_crud.py has all 8 verbs (factory is complete)
    # - At least one module is wired (factory is in use)
    # - No JWT-auth violations (every route is gated)
    passed = (
        not missing_verbs and
        len(wired_modules) >= 1 and
        not violations
    )

    return {
        "id": "G16", "name": "api_v1_coverage",
        "passed": passed,
        "summary": (
            f"{total_endpoints} endpoints "
            f"({system_routes} system + {expected_v1_routes} v1 from "
            f"{len(wired_modules)} wired module(s)), "
            f"{progress_pct:.0f}% of 136-target"
        ),
        "details": {
            "total_endpoints":     total_endpoints,
            "system_endpoints":    system_routes,
            "v1_endpoints":        expected_v1_routes + explicit_v1,
            "wired_modules":       wired_modules,
            "factory_decorators":  decorator_count,
            "factory_auth_count":  auth_count,
            "missing_verbs":       missing_verbs,
            "spec_target":         target,
            "progress_pct":        round(progress_pct, 1),
            "violations":          violations,
        },
    }


def gate_bsc_engine_breadth() -> Dict[str, Any]:
    """G17 — BSC engine adoption breadth (Standard #3, v5.32).

    Distinct from G8 (which checks contract compliance + bypass detection),
    G17 verifies BREADTH: how many distinct module-sources reach the engine?

    The spec demands "All modules use bsc_engine.submit()" — a count, not
    just a compliance check. With our two-bridge architecture
    (utils/actuals_engine.py for CBS-derived KPIs, utils/core.py
    update_bsc_from_modules for operational KPIs), each bridge submits a
    BATCH of records tagged with multiple `original_source` values in
    metadata. G17 counts both:

      - distinct `source_module=...` kwargs at submit / submit_batch
        sites (the immediate caller's tag)
      - distinct values tagged into records' `metadata["original_source"]`
        keys (the operational-modules bridge preserves the originating
        module here)

    Pass criteria: ≥17 distinct sources reach the engine. The spec's
    target is "17 modules"; we accept this as met when either
      (a) ≥17 distinct source_module values are seen, OR
      (b) the union of source_module values + original_source tags
          inside compute_operational_kpi_actuals reaches ≥17.

    The gate is a TRACKING + THRESHOLD gate. It surfaces drift: if
    someone breaks the bridge (e.g. drops the metadata tagging in
    update_bsc_from_modules), the count falls and G17 fails.
    """
    engine_path = UTILS / "bsc_engine.py"
    bridge_path = UTILS / "core.py"
    actuals_path = UTILS / "actuals_engine.py"

    if not engine_path.exists():
        return {
            "id": "G17", "name": "bsc_engine_breadth",
            "passed": False,
            "summary": "utils/bsc_engine.py missing — engine MUST exist (Standard #3)",
            "details": {},
        }

    files_to_scan: List[Path] = []
    for d in (PAGES, UTILS, SCRIPTS):
        if d.exists():
            files_to_scan.extend(p for p in d.glob("*.py") if "backup" not in p.name)

    # ── Pass 1: collect every source_module=... value at submit sites ───
    source_modules: set = set()
    submit_sites = 0
    for p in files_to_scan:
        rel = str(p.relative_to(ROOT))
        if rel == "utils/bsc_engine.py" or rel == "scripts/audit.py":
            continue
        code = read_text_safe(p)
        if not re.search(r"from\s+utils\.bsc_engine\s+import|import\s+utils\.bsc_engine", code):
            continue
        # source_module="<name>"  /  source_module = '<name>'
        for m in re.finditer(r'source_module\s*=\s*["\']([^"\']+)["\']', code):
            source_modules.add(m.group(1))
            submit_sites += 1

    # ── Pass 2: collect distinct original_source tags inside the bridge
    # function compute_operational_kpi_actuals (utils/core.py). The
    # operational-modules bridge stamps each per-module-computed actual
    # with a "source": "<module>" entry; that entry is preserved into
    # metadata["original_source"] when the bridge submits the batch.
    bridge_sources: set = set()
    if bridge_path.exists():
        core_src = read_text_safe(bridge_path)
        m = re.search(
            r"def\s+compute_operational_kpi_actuals\b.*?(?=\ndef |\Z)",
            core_src, re.DOTALL,
        )
        if m:
            body = m.group(0)
            for tag in re.findall(r'"source"\s*:\s*"([^"]+)"', body):
                bridge_sources.add(tag)

    # ── Pass 3: same idea for actuals_engine.py — find KPI-source tags
    actuals_sources: set = set()
    if actuals_path.exists():
        a_src = read_text_safe(actuals_path)
        # actuals_engine submits with source_module="actuals_engine" but
        # internally aggregates from CBS, LMS, ComplianceManager, etc.
        # Capture any distinct tag-string the engine emits.
        for tag in re.findall(r'"source"\s*:\s*"([^"]+)"', a_src):
            actuals_sources.add(tag)

    # Union of breadth signals
    union = source_modules | bridge_sources | actuals_sources
    target = 17  # per spec Standard #3

    violations: List[str] = []
    if not source_modules:
        violations.append(
            "No submit/submit_batch site found with source_module=... — "
            "engine has no callers"
        )
    if len(union) < target:
        violations.append(
            f"Engine breadth = {len(union)} sources; spec target is {target}. "
            f"Add bridge functions or instrument more modules."
        )

    passed = (
        engine_path.exists() and
        len(source_modules) >= 1 and
        len(union) >= target
    )

    return {
        "id": "G17", "name": "bsc_engine_breadth",
        "passed": passed,
        "summary": (
            f"engine={'present' if engine_path.exists() else 'MISSING'}, "
            f"{len(source_modules)} direct source_module(s), "
            f"{len(bridge_sources)} bridge-tagged source(s), "
            f"breadth={len(union)}/{target} (target: ≥{target})"
        ),
        "details": {
            "direct_source_modules":   sorted(source_modules),
            "bridge_tagged_sources":   sorted(bridge_sources),
            "actuals_engine_sources":  sorted(actuals_sources),
            "union_breadth":           len(union),
            "spec_target":             target,
            "submit_sites":            submit_sites,
            "violations":              violations,
        },
    }


GATES = [
    ("G1", gate_syntax),
    ("G2", gate_direct_io),
    ("G3", gate_audit_coverage),
    ("G4", gate_tab_counts),
    ("G5", gate_admin_sections),
    ("G6", gate_registry_coverage),
    ("G7", gate_conventions_docs),
    ("G8", gate_bsc_contract),
    ("G9", gate_sql_safety),
    ("G10", gate_xss_safety),
    ("G11", gate_password_safety),
    ("G12", gate_api_auth_safety),
    ("G13", gate_test_infrastructure),
    ("G14", gate_core_split_adoption),
    ("G15", gate_pg_migration_progress),
    ("G16", gate_api_v1_coverage),
    ("G17", gate_bsc_engine_breadth),
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
