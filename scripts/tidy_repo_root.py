#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tidy the repository root. DRY RUN by default; nothing tracked is touched.

WHY THIS MATTERS MORE THAN IT LOOKS. Several hundred one-off forensic scripts
sit at the project root - diagnose_*, probe_*, check_*, dump_*, plus tarballs,
backup JSONs and stray files literally named `bool`, `the`, `triad`. They make
`git status` unreadable, and an unreadable git status is why:

  * a TZ-1 commit slipped through unnoticed days ago
  * several `git add` chains aborted today on ignored paths, silently skipping
    the commit that followed the &&
  * a patcher's --apply was skipped without anyone noticing, because the commit
    output looked normal

This is a system heading to production in a bank. Someone else will read this
repository.

WHAT IT DOES
  * moves matching UNTRACKED files at the ROOT ONLY into forensics/
  * never touches anything git tracks, anything in a subdirectory, or anything
    that does not match a listed pattern
  * appends the patterns to .gitignore so they stay out

MOVED, NOT DELETED. These are your working history and several were genuinely
useful today. They just do not belong at the root of a banking repository.

    python scripts\\tidy_repo_root.py            # list what would move
    python scripts\\tidy_repo_root.py --apply
"""
import os
import shutil
import subprocess
import sys

DEST = "forensics"

PREFIXES = ("diagnose_", "probe_", "check_", "dump_", "find_", "verify_",
            "inspect_", "trace_", "test_", "fix_", "scan_", "audit_",
            "explore_", "list_", "show_", "count_", "compare_", "repair_")
SUFFIXES = (".tar.gz", ".zip", ".bak", ".orig", ".rej", ".log")
CONTAINS = ("_backup_", "_snapshot_", ".pre_")

# Files with no extension and a lowercase word for a name - shell redirects that
# went astray (`bool`, `the`, `triad`, `returned`, `validated_at`).
def _looks_like_stray(name: str) -> bool:
    return ("." not in name and name.islower() and name.isascii()
            and name.replace("_", "").isalpha() and len(name) <= 24)


GITIGNORE_BLOCK = """
# ── Forensic and one-off scripts (tidied 2026-08-09) ────────────────────────
# Kept out of the repository root so `git status` stays readable. An unreadable
# status is how commits go wrong unnoticed.
/forensics/
/diagnose_*.py
/probe_*.py
/check_*.py
/dump_*.py
/find_*.py
/verify_*.py
/inspect_*.py
/trace_*.py
/fix_*.py
/scan_*.py
/audit_*.py
/*.tar.gz
/*.zip
/*_backup_*.json
/*_snapshot_*.json
*.pre_*
"""


def tracked_files() -> set:
    try:
        out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                             check=True).stdout
        return set(out.splitlines())
    except Exception as exc:
        print("ABORT: could not read the git index (%s)." % exc)
        print("       Refusing to move anything without knowing what is tracked.")
        return None


def main():
    apply = "--apply" in sys.argv
    if not os.path.isdir(".git"):
        print("ABORT: no .git here. Run from the project root.")
        return 1

    tracked = tracked_files()
    if tracked is None:
        return 1

    candidates = []
    for name in sorted(os.listdir(".")):
        if not os.path.isfile(name):
            continue
        if name in tracked:
            continue                      # NEVER touch a tracked file
        if name in (".gitignore", ".gitattributes", ".env"):
            continue
        low = name.lower()
        if (low.startswith(PREFIXES) or low.endswith(SUFFIXES)
                or any(c in low for c in CONTAINS) or _looks_like_stray(name)):
            candidates.append(name)

    if not candidates:
        print("Root is already tidy - nothing untracked matches.")
        return 0

    total = sum(os.path.getsize(f) for f in candidates)
    print("=" * 72)
    print("WOULD MOVE %d untracked files (%.1f MB) -> %s/"
          % (len(candidates), total / 1e6, DEST))
    print("=" * 72)
    for n in candidates[:60]:
        print("   %s" % n)
    if len(candidates) > 60:
        print("   ... and %d more" % (len(candidates) - 60))

    still = [f for f in os.listdir(".")
             if os.path.isfile(f) and f not in tracked and f not in candidates]
    if still:
        print("\nLEFT ALONE (untracked, but not matching any pattern):")
        for n in sorted(still)[:25]:
            print("   %s" % n)
        if len(still) > 25:
            print("   ... and %d more" % (len(still) - 25))
        print("Review these yourself - the script will not guess at them.")

    if not apply:
        print("\nDRY RUN - nothing moved. Re-run with --apply.")
        return 0

    os.makedirs(DEST, exist_ok=True)
    moved = 0
    for n in candidates:
        target = os.path.join(DEST, n)
        if os.path.exists(target):
            base, ext = os.path.splitext(n)
            target = os.path.join(DEST, "%s_dup%s" % (base, ext))
        try:
            shutil.move(n, target)
            moved += 1
        except Exception as exc:
            print("   could not move %s: %s" % (n, exc))
    print("\nmoved %d files into %s/" % (moved, DEST))

    gi = ".gitignore"
    cur = open(gi, encoding="utf-8").read() if os.path.isfile(gi) else ""
    if "/forensics/" not in cur:
        with open(gi, "a", encoding="utf-8") as fh:
            fh.write(GITIGNORE_BLOCK)
        print("appended the ignore block to .gitignore")
    else:
        print(".gitignore already carries the block")

    print("\nNow `git status` should be readable. Check with:")
    print("  git status --short | head -20")
    return 0


if __name__ == "__main__":
    sys.exit(main())
