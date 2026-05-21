"""Audit + archive retired tests using the _retired_ prefix convention.

Per v10.422 (Phase 2d):
The codebase soft-retires obsolete tests by renaming them from
`test_v10XXX_...` to `_retired_v10YYY_test_v10XXX_...`. Pytest skips
them, but they remain in source for in-context historical reference.

This script:
  - Audits all _retired_ functions across tests/integration/
  - Reports per-file + per-version aggregates
  - Optionally writes data/_retired_tests_archive.json (searchable history)

Default behaviour is dry-run audit (no FS changes). To write the
archive, pass --archive.

Examples:
    # Just audit (no FS changes)
    python scripts/audit_retired_tests.py

    # Audit + write archive
    python scripts/audit_retired_tests.py --archive
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--archive", action="store_true",
                   help="Write data/_retired_tests_archive.json (default: audit only)")
    args = p.parse_args()

    from utils.test_cleanup_engine import audit_retired_tests, archive_retired_tests

    print("Retired Test Audit (v10.422)")
    print("=" * 60)

    audit = audit_retired_tests()
    print(f"\nAUDIT:")
    print(f"  Total retired functions:  {audit.total_retired}")
    print(f"  Files affected:           {audit.files_affected}")

    if audit.by_retired_version:
        print(f"\nBy retiring batch:")
        for v, n in sorted(audit.by_retired_version.items()):
            print(f"  {v}: {n} test(s) retired")

    if audit.by_original_version:
        print(f"\nBy original test batch:")
        for v, n in sorted(audit.by_original_version.items()):
            print(f"  {v}: {n} test(s) had retirements")

    if audit.by_file:
        print(f"\nBy file:")
        for f, n in sorted(audit.by_file.items(), key=lambda x: -x[1]):
            print(f"  {n:3d}  {f}")

    if audit.tests:
        print(f"\nIndividual retired tests:")
        for t in audit.tests:
            print(f"  {t.original_test}")
            print(f"    retired_by={f'v{t.retired_by_version}'}, "
                  f"file={t.file_path}:{t.line_number}, "
                  f"body_lines={t.body_lines}")

    if not args.archive:
        print(f"\n[AUDIT ONLY] To write data/_retired_tests_archive.json, re-run with --archive")
        return 0

    print(f"\nWriting archive...")
    result = archive_retired_tests(dry_run=False)
    print(f"  Path:     {result.archive_path}")
    print(f"  Tests:    {result.tests_archived}")
    print(f"  Size:     {result.archive_size_bytes} bytes")
    print(f"  Status:   {result.note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
