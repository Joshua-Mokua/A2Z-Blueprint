#!/usr/bin/env python3
"""scripts/repair_pipeline_settings.py — diagnose + repair a byte-corrupted
data/pipeline_settings.json.

The file picked up a non-UTF-8 byte (e.g. 0x9d, a stray Windows smart-quote
fragment) that makes json.load crash with UnicodeDecodeError, which in turn
500s the product-flows endpoint (save_pipeline_settings can't read-modify-write).

This script:
  1. Reads the file as RAW BYTES (never assumes an encoding).
  2. Reports every non-UTF-8 / control byte and its surrounding context.
  3. DRY-RUN by default: shows what it would fix, writes nothing.
  4. With --apply: backs up to .pre_repair_<ts>, then either
       (a) --from-backup <path>: restores a known-good backup, OR
       (b) auto-repair: maps common cp1252 smart-quote bytes to ASCII and
           drops un-mappable control bytes, then validates the result parses.
  5. Refuses to write anything that doesn't parse as JSON (fail-safe).

Usage (run from project root, venv active):
  python scripts/repair_pipeline_settings.py                       # diagnose only
  python scripts/repair_pipeline_settings.py --apply               # auto-repair bytes
  python scripts/repair_pipeline_settings.py --apply --from-backup data/pipeline_settings.json.pre_p4a_20260624-170723
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime

TARGET = os.path.join("data", "pipeline_settings.json")

# cp1252 "smart" bytes -> safe ASCII. These are the usual corruption culprits
# when a JSON file is touched by a Windows editor / copy-paste.
CP1252_FIXUPS = {
    0x91: b"'", 0x92: b"'",        # ' '  curly single quotes
    0x93: b'"', 0x94: b'"',        # " "  curly double quotes
    0x96: b"-", 0x97: b"-",        # – —  en/em dash
    0x85: b"...",                  # … ellipsis
    0xa0: b" ",                    # nbsp
    0x9d: b'"',                    # lone 0x94 high-half / stray -> closest is "
    0x9c: b"'",
}


def find_bad_bytes(raw: bytes):
    """Return list of (index, byte, context) for bytes that break UTF-8 decode."""
    bad = []
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if b < 0x80:
            i += 1
            continue
        # try to decode a short window starting here as utf-8
        chunk = raw[i:i + 4]
        ok = False
        for length in (2, 3, 4):
            try:
                chunk[:length].decode("utf-8")
                if len(chunk) >= length:
                    ok = True
                    i += length
                    break
            except Exception:
                continue
        if not ok:
            ctx = raw[max(0, i - 30):i + 30]
            bad.append((i, b, ctx))
            i += 1
    return bad


def auto_repair(raw: bytes) -> bytes:
    out = bytearray()
    i = 0
    n = len(raw)
    while i < n:
        b = raw[i]
        if b < 0x80:
            out.append(b)
            i += 1
            continue
        chunk = raw[i:i + 4]
        consumed = 0
        for length in (2, 3, 4):
            try:
                chunk[:length].decode("utf-8")
                if len(chunk) >= length:
                    out.extend(chunk[:length])
                    consumed = length
                    break
            except Exception:
                continue
        if consumed:
            i += consumed
            continue
        # un-decodable single byte -> map or drop
        rep = CP1252_FIXUPS.get(b)
        if rep is not None:
            out.extend(rep)
        # else drop it silently (control/garbage)
        i += 1
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write the repair (default: dry-run)")
    ap.add_argument("--from-backup", default=None,
                    help="restore this backup file instead of auto-repairing bytes")
    args = ap.parse_args()

    if not os.path.exists(TARGET):
        print(f"FATAL: {TARGET} not found (run from project root).")
        sys.exit(2)

    raw = open(TARGET, "rb").read()
    print(f"{TARGET}: {len(raw)} bytes")

    # Does it already parse?
    try:
        json.loads(raw.decode("utf-8"))
        print("Already valid UTF-8 JSON — nothing to repair.")
        return
    except Exception as e:
        print(f"Does NOT parse: {type(e).__name__}: {e}")

    bad = find_bad_bytes(raw)
    print(f"\nFound {len(bad)} bad byte(s):")
    for idx, b, ctx in bad[:20]:
        print(f"  @ {idx}: 0x{b:02x}   ...{ctx!r}...")
    if len(bad) > 20:
        print(f"  ... and {len(bad) - 20} more")

    # Decide repaired content
    if args.from_backup:
        if not os.path.exists(args.from_backup):
            print(f"\nFATAL: backup {args.from_backup} not found.")
            sys.exit(2)
        repaired = open(args.from_backup, "rb").read()
        source = f"backup {args.from_backup}"
    else:
        repaired = auto_repair(raw)
        source = "auto byte-repair"

    # Validate the repaired content parses
    try:
        parsed = json.loads(repaired.decode("utf-8"))
    except Exception as e:
        print(f"\nREFUSING TO WRITE: repaired content ({source}) still doesn't parse: {e}")
        sys.exit(3)

    keys = sorted(parsed.keys()) if isinstance(parsed, dict) else []
    pf = len(parsed.get("product_flows", {})) if isinstance(parsed, dict) else 0
    print(f"\nRepaired content ({source}) parses OK.")
    print(f"  top-level keys: {keys}")
    print(f"  product_flows: {pf}")

    # Structural sanity — refuse a thin config (anti-thinning, mirrors save guard)
    CORE = {"product_catalogue", "stage_flows", "required_fields"}
    if isinstance(parsed, dict) and not (CORE & set(parsed.keys())):
        print(f"\nWARNING: repaired config is missing ALL core keys {CORE} — looks thin.")
        print("Prefer --from-backup with a known-good file instead of auto-repair.")
        if args.apply:
            print("Refusing to --apply a thin config. Aborting.")
            sys.exit(4)

    if not args.apply:
        print("\n[DRY-RUN] No file written. Re-run with --apply to back up + write.")
        return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = f"{TARGET}.pre_repair_{ts}"
    shutil.copy2(TARGET, backup)
    print(f"\nBacked up corrupt file -> {backup}")
    with open(TARGET, "w", encoding="utf-8") as f:
        json.dump(parsed, f, ensure_ascii=False, indent=2)
    print(f"Wrote repaired {TARGET} ({source}).")
    print("Restart the API, then re-run the harness.")


if __name__ == "__main__":
    main()
