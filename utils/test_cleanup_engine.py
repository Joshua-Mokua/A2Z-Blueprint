"""Test Cleanup Audit Engine — v10.422 (Phase 2d).

Per Joshua's locked backlog: "Retired test cleanup (11 stale across 3 files)".

The codebase uses a soft-retirement convention: stale tests are renamed
from `test_v10XXX_...` to `_retired_v10YYY_test_v10XXX_...` where YYY is
the batch that retired them. Pytest doesn't run functions not starting
with `test_`, so this is a clean "no-execute" path that preserves the
history of WHY a test was retired (the version-prefix encodes it).

Live audit: 12 retired functions across 4 files.

This engine:
  - Audits the codebase for `_retired_` prefix functions
  - Parses each: file, line_number, retired_by, original_test, body_size
  - Optionally extracts into data/_retired_tests_archive.json for searchable
    historical record (then they can be safely deleted from source)
  - Does NOT auto-delete from source. Deletion is a separate explicit step.

ARCHITECTURAL NOTE: API-first per v10.412. ZERO streamlit imports.
This engine reads files only; writing happens via explicit extract path.

Shipped: v10.422.
"""
from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
TESTS_DIR = REPO_ROOT / "tests" / "integration"
ARCHIVE_FILE = REPO_ROOT / "data" / "_retired_tests_archive.json"

# Pattern: _retired_v10XXX_test_v10YYY_<descriptive_name>
RETIRED_PATTERN = re.compile(
    r"^_retired_v(\d+)_test_v(\d+)_(.+)$"
)


# ════════════════════════════════════════════════════════════════════
# Types
# ════════════════════════════════════════════════════════════════════

@dataclass
class RetiredTestInfo:
    """One retired test function's metadata."""
    function_name: str           # _retired_v10403_test_v10397_total_unique_codes_increased
    original_test: str           # test_v10397_total_unique_codes_increased
    retired_by_version: int      # 10403 (batch that retired it)
    original_version: int        # 10397 (batch the test belonged to)
    file_path: str               # relative path
    line_number: int             # where def starts
    body_lines: int              # # of lines in the function
    docstring: str               # first line of docstring if present

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TestCleanupAudit:
    """Bank-wide audit of retired tests."""
    total_retired: int
    files_affected: int
    by_retired_version: Dict[str, int]   # {version: count} - who retired what
    by_original_version: Dict[str, int]  # {version: count} - what was retired
    by_file: Dict[str, int]              # {file: count}
    tests: List[RetiredTestInfo] = field(default_factory=list)
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArchiveResult:
    """Result of extracting retired tests into archive."""
    dry_run: bool
    tests_archived: int
    archive_path: str
    archive_size_bytes: int
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ════════════════════════════════════════════════════════════════════
# Public API — Audit
# ════════════════════════════════════════════════════════════════════

def _parse_retired_functions(file_path: Path) -> List[RetiredTestInfo]:
    """Parse a test file for _retired_ functions using AST."""
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    source_lines = source.splitlines()
    out: List[RetiredTestInfo] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        m = RETIRED_PATTERN.match(node.name)
        if not m:
            continue

        retired_by = int(m.group(1))
        original_v = int(m.group(2))
        descriptive = m.group(3)

        # Body span
        start_line = node.lineno
        end_line = (
            node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno
            else start_line
        )
        body_lines = end_line - start_line + 1

        # First line of docstring if present
        docstring = ""
        if (node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
            doc = node.body[0].value.value.strip()
            docstring = doc.split("\n")[0][:200]  # cap length

        # File path - relative to REPO_ROOT if possible, else absolute
        try:
            rel_path = str(file_path.relative_to(REPO_ROOT))
        except ValueError:
            rel_path = str(file_path)

        out.append(RetiredTestInfo(
            function_name=node.name,
            original_test=f"test_v{original_v}_{descriptive}",
            retired_by_version=retired_by,
            original_version=original_v,
            file_path=rel_path,
            line_number=start_line,
            body_lines=body_lines,
            docstring=docstring,
        ))

    return out


def audit_retired_tests(
    tests_dir: Optional[Path] = None,
) -> TestCleanupAudit:
    """Audit all retired test functions across the integration test dir."""
    if tests_dir is None:
        tests_dir = TESTS_DIR
    if not tests_dir.exists():
        return TestCleanupAudit(
            total_retired=0, files_affected=0,
            by_retired_version={}, by_original_version={}, by_file={},
            tests=[], timestamp=datetime.now().isoformat(),
        )

    all_tests: List[RetiredTestInfo] = []
    for f in sorted(tests_dir.glob("test_*.py")):
        all_tests.extend(_parse_retired_functions(f))

    by_retired: Dict[str, int] = {}
    by_original: Dict[str, int] = {}
    by_file: Dict[str, int] = {}

    for t in all_tests:
        rv = f"v{t.retired_by_version}"
        ov = f"v{t.original_version}"
        by_retired[rv] = by_retired.get(rv, 0) + 1
        by_original[ov] = by_original.get(ov, 0) + 1
        by_file[t.file_path] = by_file.get(t.file_path, 0) + 1

    return TestCleanupAudit(
        total_retired=len(all_tests),
        files_affected=len(by_file),
        by_retired_version=by_retired,
        by_original_version=by_original,
        by_file=by_file,
        tests=all_tests,
        timestamp=datetime.now().isoformat(),
    )


# ════════════════════════════════════════════════════════════════════
# Public API — Archive (additive — no deletion from source)
# ════════════════════════════════════════════════════════════════════

def archive_retired_tests(
    tests_dir: Optional[Path] = None,
    archive_path: Optional[Path] = None,
    dry_run: bool = True,
) -> ArchiveResult:
    """Extract retired tests into a JSON archive for posterity.

    The archive contains metadata + bodies of each retired test, indexed
    by function name. Multiple runs are idempotent (overwrites).

    Default dry_run=True means no file is written; ArchiveResult shows
    what would be archived.

    This does NOT delete retired functions from test source files.
    Deletion is a separate explicit operation (not in v10.422 — preserving
    the _retired_ functions in-place gives readable historical context).
    """
    if tests_dir is None:
        tests_dir = TESTS_DIR
    if archive_path is None:
        archive_path = ARCHIVE_FILE

    audit = audit_retired_tests(tests_dir)

    # Build archive payload with function bodies
    archive: Dict[str, Any] = {
        "_doc": (
            "v10.422 - Retired test archive. Tests retired via the "
            "_retired_v10XXX_ prefix convention. This archive preserves "
            "metadata for searchability; the original functions remain "
            "in their source files for in-context historical reference."
        ),
        "shipped": "v10.422",
        "generated_at": datetime.now().isoformat(),
        "total_retired": audit.total_retired,
        "by_retired_version": audit.by_retired_version,
        "by_original_version": audit.by_original_version,
        "by_file": audit.by_file,
        "tests": {},
    }

    for t in audit.tests:
        # Extract body from source
        body_text = ""
        try:
            # t.file_path may be relative (under REPO_ROOT) or absolute
            t_path = Path(t.file_path)
            if not t_path.is_absolute():
                t_path = REPO_ROOT / t_path
            src_lines = t_path.read_text(encoding="utf-8").splitlines()
            start = t.line_number - 1
            end = start + t.body_lines
            body_text = "\n".join(src_lines[start:end])
        except OSError:
            body_text = "[body extraction failed]"

        archive["tests"][t.function_name] = {
            **t.to_dict(),
            "body": body_text,
        }

    # Archive path relative for display when possible
    try:
        rel_archive = str(archive_path.relative_to(REPO_ROOT))
    except ValueError:
        rel_archive = str(archive_path)

    note = "Archive built but not written (dry_run)"
    archive_size = 0
    if not dry_run:
        try:
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text(
                json.dumps(archive, indent=2, default=str),
                encoding="utf-8",
            )
            archive_size = archive_path.stat().st_size
            note = "Archive written successfully"
        except OSError as exc:
            note = f"Archive write failed: {exc}"

    return ArchiveResult(
        dry_run=dry_run,
        tests_archived=audit.total_retired,
        archive_path=rel_archive,
        archive_size_bytes=archive_size,
        note=note,
    )


# ════════════════════════════════════════════════════════════════════
# Self-test
# ════════════════════════════════════════════════════════════════════

def self_test() -> None:
    print("─ test_cleanup_engine self-test ─")
    import tempfile

    tmp = Path(tempfile.mkdtemp())
    try:
        # Create a synthetic test file with mixed test + retired functions
        synth = tmp / "test_synthetic.py"
        synth.write_text("""
def test_normal_function():
    '''A normal active test.'''
    assert True

def _retired_v10300_test_v10200_obsolete_count_check():
    '''Was retired in v10.300 because count drifted.'''
    assert True

def _retired_v10350_test_v10250_renamed_endpoint():
    '''Obsolete after API rename.'''
    pass

def not_a_test():
    pass
""")
        # Audit it
        audit = audit_retired_tests(tests_dir=tmp)
        assert audit.total_retired == 2, f"Got {audit.total_retired} retired"
        assert audit.files_affected == 1
        print(f"  ✓ Audit found {audit.total_retired} retired functions in {audit.files_affected} files")

        # Verify per-version aggregation
        assert audit.by_retired_version == {"v10300": 1, "v10350": 1}
        assert audit.by_original_version == {"v10200": 1, "v10250": 1}
        print(f"  ✓ Per-version aggregation correct")

        # Verify individual parse
        first = audit.tests[0]
        assert first.function_name.startswith("_retired_")
        assert first.original_test.startswith("test_v10")
        assert first.retired_by_version in (10300, 10350)
        assert first.body_lines > 0
        assert first.docstring  # parsed
        print(f"  ✓ Individual parse: {first.function_name}")

        # Dry-run archive
        archive_path = tmp / "archive.json"
        result_dry = archive_retired_tests(
            tests_dir=tmp, archive_path=archive_path, dry_run=True,
        )
        assert result_dry.dry_run is True
        assert result_dry.tests_archived == 2
        assert not archive_path.exists()
        print(f"  ✓ Dry-run archive: {result_dry.tests_archived} tests (no FS change)")

        # Real archive
        result = archive_retired_tests(
            tests_dir=tmp, archive_path=archive_path, dry_run=False,
        )
        assert result.dry_run is False
        assert archive_path.exists()
        archive = json.loads(archive_path.read_text())
        assert archive["total_retired"] == 2
        assert len(archive["tests"]) == 2
        # Body extraction
        sample = next(iter(archive["tests"].values()))
        assert "def " in sample["body"]
        print(f"  ✓ Archive written: {result.archive_size_bytes} bytes, {len(archive['tests'])} tests with bodies")

        # Idempotency
        result2 = archive_retired_tests(
            tests_dir=tmp, archive_path=archive_path, dry_run=False,
        )
        assert result2.tests_archived == 2  # same content
        print(f"  ✓ Idempotent: re-archive yields same count")

        # Edge: empty dir
        empty = Path(tempfile.mkdtemp())
        try:
            a = audit_retired_tests(tests_dir=empty)
            assert a.total_retired == 0
            assert a.files_affected == 0
        finally:
            empty.rmdir()
        print("  ✓ Empty dir handled gracefully")

        # Zero streamlit imports
        text = Path(__file__).read_text()
        streamlit_imports = re.findall(
            r"^\s*(?:import\s+streamlit|from\s+streamlit)\b",
            text, re.MULTILINE,
        )
        assert len(streamlit_imports) == 0
        print("  ✓ Zero streamlit imports (React-ready)")

        print("✓ self_test passed")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    self_test()
