#!/usr/bin/env python3
"""scripts/verify_bcrypt.py — Audit and migrate users.json hash distribution.

Part of v10.500 Phase 1 Batch 3c (Phase 1 closure gate #8).

USAGE
-----
    python -m scripts.verify_bcrypt                # audit-only (default)
    python -m scripts.verify_bcrypt --upgrade      # dry-run + confirmation prompt + write
    python -m scripts.verify_bcrypt --upgrade --yes  # write without prompt (automation)
    python -m scripts.verify_bcrypt --upgrade --dry-run  # never write, even with --yes
    python -m scripts.verify_bcrypt --help

OPERATIONS
----------
Audit mode (default): scans data/users.json, classifies every record's
password field into one of five buckets, prints the distribution. Read-
only — never modifies anything.

Upgrade mode (--upgrade): wraps every legacy-SHA-256 hash in envelope
form: bcrypt(sha256_hex). The bcrypt-wrapped envelope is indistinguish-
able at-rest from a direct-bcrypt hash, but utils/core.UserManager.
verify_pw (post-Batch-3c) recognises the envelope path and verifies
correctly when users authenticate with their original plaintext password.

Direct-bcrypt hashes (already $2b$/$2a$/$2y$) are LEFT UNCHANGED.
Malformed/empty/unknown entries are LEFT UNCHANGED and reported.

By default --upgrade performs a dry-run first, prints the planned
operations summary, and prompts for confirmation before writing. Pass
--yes to skip the prompt (automation contexts). Pass --dry-run with
--upgrade to NEVER write (planning preview).

SECURITY
--------
This script NEVER prints:
  - password plaintext or any derivation
  - bcrypt hash strings
  - sha256 hex strings
  - tokens, credentials, or stack locals containing auth material

Sample usernames are printed only for diagnostic counts (e.g. "5
malformed records: 'foo', 'bar', 'baz', ..." — the count comes first,
sample names are advisory only).

CGR1 doctrine: envelope is a TRANSITIONAL stabilization layer, NOT
canonical end-state. Phase 2 hardening may add forced normalization
to direct bcrypt, Argon2 migration, etc. This script's --upgrade is
a one-time bulk migration mechanism; future runs should report "0
legacy SHA-256 found" as the steady-state.

EXIT CODES
----------
    0   audit completed OR upgrade applied successfully (or dry-run)
    1   confirmation prompt declined
    2   data/users.json not found or unreadable
    3   data/users.json malformed JSON
    4   bcrypt unavailable (required for --upgrade)
    5   internal error during upgrade (file write failed, etc.)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Tuple

# ── Constants ────────────────────────────────────────────────────────────
USERS_FILE_DEFAULT = Path("data") / "users.json"
SAMPLE_USERNAMES_LIMIT = 5

# Hash classification labels — also keys in the count dict.
HASH_BCRYPT_DIRECT  = "bcrypt_direct"     # $2b$ / $2a$ / $2y$ prefix
HASH_SHA256_LEGACY  = "sha256_legacy"     # 64-char lowercase hex
HASH_EMPTY          = "empty"             # blank or missing password field
HASH_MALFORMED      = "malformed"         # something else


def classify_hash(stored: str) -> str:
    """Classify a stored password field into one of four buckets.

    Returns one of: HASH_BCRYPT_DIRECT, HASH_SHA256_LEGACY, HASH_EMPTY,
    HASH_MALFORMED.

    NOTE: envelope-wrapped hashes (bcrypt(sha256_hex)) are
    INDISTINGUISHABLE from direct-bcrypt at the at-rest level — both
    use bcrypt prefix. This is by design (no schema drift). Envelope
    population is tracked at runtime via verify_pw's INFO log, not
    via at-rest classification.
    """
    if not stored:
        return HASH_EMPTY
    if stored.startswith("$2b$") or stored.startswith("$2a$") or stored.startswith("$2y$"):
        return HASH_BCRYPT_DIRECT
    # Pure SHA-256 hex: 64 chars, all 0-9a-f
    if len(stored) == 64 and all(c in "0123456789abcdef" for c in stored.lower()):
        return HASH_SHA256_LEGACY
    return HASH_MALFORMED


def envelope_wrap(sha256_hex: str, bcrypt_module) -> str:
    """Wrap a SHA-256 hex string in a bcrypt envelope.

    The bcrypt input IS the sha256_hex string itself (not the plaintext
    password — which we don't have). verify_pw's envelope path will
    reproduce this transformation at auth time:
        sha_hex = sha256(plaintext).hex
        bcrypt.checkpw(sha_hex, envelope_stored)
    """
    return bcrypt_module.hashpw(
        sha256_hex.encode("utf-8"),
        bcrypt_module.gensalt(rounds=12),
    ).decode("utf-8")


def load_users(path: Path) -> dict:
    """Load and validate users.json. Returns the parsed dict or exits."""
    if not path.exists():
        print(f"ERROR: users file not found: {path}")
        sys.exit(2)
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"ERROR: could not read {path}: {type(e).__name__}: {e}")
        sys.exit(2)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: malformed JSON in {path}: {e}")
        sys.exit(3)
    if not isinstance(data, dict):
        print(f"ERROR: {path} top-level is not a dict (got {type(data).__name__})")
        sys.exit(3)
    return data


def audit(users: dict) -> dict:
    """Build classification counts + sample usernames per bucket.

    Returns {bucket: {'count': int, 'samples': [usernames]}}.
    Samples are limited to SAMPLE_USERNAMES_LIMIT per bucket.
    """
    buckets: dict = {
        HASH_BCRYPT_DIRECT:  {"count": 0, "samples": []},
        HASH_SHA256_LEGACY:  {"count": 0, "samples": []},
        HASH_EMPTY:          {"count": 0, "samples": []},
        HASH_MALFORMED:      {"count": 0, "samples": []},
    }
    for username, record in users.items():
        if not isinstance(record, dict):
            buckets[HASH_MALFORMED]["count"] += 1
            if len(buckets[HASH_MALFORMED]["samples"]) < SAMPLE_USERNAMES_LIMIT:
                buckets[HASH_MALFORMED]["samples"].append(username)
            continue
        stored = record.get("password", "") or ""
        bucket = classify_hash(stored)
        buckets[bucket]["count"] += 1
        if len(buckets[bucket]["samples"]) < SAMPLE_USERNAMES_LIMIT:
            buckets[bucket]["samples"].append(username)
    return buckets


def print_audit(buckets: dict, total: int, header: str = "Hash distribution") -> None:
    """Print audit summary in a fixed, scannable format.

    NEVER prints any hash, password, or token material — only counts
    and (advisory) usernames.
    """
    print(f"\n{header}")
    print("=" * len(header))
    print(f"  Total user records:      {total}")
    print(f"  Direct bcrypt:           {buckets[HASH_BCRYPT_DIRECT]['count']}")
    print(f"  Legacy SHA-256:          {buckets[HASH_SHA256_LEGACY]['count']}")
    print(f"  Empty / no password:     {buckets[HASH_EMPTY]['count']}")
    print(f"  Malformed / unknown:     {buckets[HASH_MALFORMED]['count']}")
    print()
    for bucket_name, label in [
        (HASH_SHA256_LEGACY, "Legacy SHA-256 (eligible for envelope upgrade)"),
        (HASH_MALFORMED,     "Malformed / unknown (will NOT be touched)"),
        (HASH_EMPTY,         "Empty password fields (will NOT be touched)"),
    ]:
        info = buckets[bucket_name]
        if info["count"] > 0:
            samples = ", ".join(repr(s) for s in info["samples"])
            more = (f" (+{info['count'] - len(info['samples'])} more)"
                    if info["count"] > len(info["samples"]) else "")
            print(f"  {label}:")
            print(f"    sample usernames: {samples}{more}")
            print()
    print("NOTE: Envelope-wrapped vs direct bcrypt are INDISTINGUISHABLE at-rest")
    print("      (both use $2b$/$2a$/$2y$ prefix). Envelope population is tracked")
    print("      at runtime via the INFO log in UserManager.verify_pw.")
    print()


def upgrade(users: dict, dry_run: bool) -> Tuple[dict, int]:
    """Wrap every HASH_SHA256_LEGACY record in envelope form.

    Returns (modified_users_dict, count_upgraded). When dry_run=True,
    returns a deep copy with the upgrades applied conceptually but the
    caller will NOT persist it.

    Direct-bcrypt, empty, and malformed records are left unchanged.
    """
    try:
        import bcrypt
    except ImportError:
        print("ERROR: bcrypt module not available. Install via:")
        print("       pip install bcrypt")
        sys.exit(4)

    # Operate on a copy to avoid mutating the caller's dict if dry_run.
    upgraded = {u: dict(r) if isinstance(r, dict) else r
                for u, r in users.items()}
    count = 0
    for username, record in upgraded.items():
        if not isinstance(record, dict):
            continue
        stored = record.get("password", "") or ""
        if classify_hash(stored) != HASH_SHA256_LEGACY:
            continue
        # Wrap the existing sha256_hex in bcrypt envelope. The
        # plaintext password is NOT required — that's the entire
        # point of the envelope strategy.
        record["password"] = envelope_wrap(stored, bcrypt)
        count += 1
    return upgraded, count


def write_users(path: Path, users: dict) -> None:
    """Persist updated users.json. Writes via temp file + atomic
    rename for safety on Windows + Unix."""
    tmp = path.with_suffix(path.suffix + ".batch3c_tmp")
    try:
        tmp.write_text(json.dumps(users, indent=2), encoding="utf-8")
        # Atomic on POSIX, near-atomic on Windows (replace handles dest-exists).
        tmp.replace(path)
    except Exception as e:
        print(f"ERROR: could not write {path}: {type(e).__name__}: {e}")
        # Best-effort cleanup
        if tmp.exists():
            try: tmp.unlink()
            except Exception: pass
        sys.exit(5)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify_bcrypt",
        description="Audit and migrate hash distribution in data/users.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="See module docstring for security and doctrine notes.",
    )
    parser.add_argument(
        "--upgrade", action="store_true",
        help="Wrap all legacy SHA-256 hashes in bcrypt envelope. "
             "Default action is audit-only.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="With --upgrade: report planned operations but never "
             "write to disk. Implies the user is exploring.",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="With --upgrade: skip interactive confirmation prompt. "
             "Suitable for automation contexts.",
    )
    parser.add_argument(
        "--users-file", default=str(USERS_FILE_DEFAULT),
        help=f"Path to users.json (default: {USERS_FILE_DEFAULT})",
    )
    args = parser.parse_args(argv)

    users_path = Path(args.users_file)
    users = load_users(users_path)
    total = len(users)
    buckets = audit(users)

    # Always print the audit first.
    print_audit(buckets, total, header="Hash distribution (before)")

    if not args.upgrade:
        # Audit-only mode — done.
        return 0

    # ── Upgrade path ─────────────────────────────────────────────────
    eligible = buckets[HASH_SHA256_LEGACY]["count"]
    if eligible == 0:
        print("Nothing to do — no legacy SHA-256 hashes found.")
        return 0

    # Dry-run preview (always shown, even with --yes — operator should
    # see what would happen before automation flags consent).
    print(f"PLAN: wrap {eligible} legacy SHA-256 hash(es) in bcrypt envelope.")
    print(f"      Direct-bcrypt, empty, malformed records will NOT be modified.")
    print()

    if args.dry_run:
        print("--dry-run set — NO changes will be written.")
        return 0

    # Confirmation gate (skipped only with --yes).
    if not args.yes:
        try:
            response = input(
                f"Proceed with envelope upgrade for {eligible} record(s)? [y/N] "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted (no input).")
            return 1
        if response not in ("y", "yes"):
            print("Aborted.")
            return 1

    # Apply upgrade.
    upgraded_users, count = upgrade(users, dry_run=False)
    write_users(users_path, upgraded_users)
    print(f"\nWrote {users_path} with {count} envelope-wrapped record(s).")

    # Final audit to confirm.
    final_buckets = audit(upgraded_users)
    print_audit(final_buckets, total, header="Hash distribution (after)")

    if final_buckets[HASH_SHA256_LEGACY]["count"] != 0:
        print(f"WARNING: {final_buckets[HASH_SHA256_LEGACY]['count']} legacy "
              "SHA-256 record(s) remain after upgrade. Inspect manually.")
        return 5

    print("Migration complete. All eligible hashes are now bcrypt-backed.")
    print("Envelope-vs-direct distinction is observable at runtime via the")
    print("a2z.core 'Envelope-backed credential authenticated' INFO log.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
