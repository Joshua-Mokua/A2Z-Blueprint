#!/usr/bin/env python3
"""scripts/fix_mojibake.py — repair double-encoded (mojibake) text in a JSON
data file, e.g. 'â€"' where an em-dash '—' belongs.

Mechanism of the corruption: utf-8 bytes were once read as cp1252 and re-saved
as utf-8, producing garbage sequences. This reverses the common cases by
re-interpreting the mojibake back through latin-1/cp1252.

Targets data/pipeline_settings.json by default. Backs up, validates JSON parses
both before and after, refuses to write if parse fails. Dry-run by default.

Usage (project root, venv active):
  python scripts/fix_mojibake.py
  python scripts/fix_mojibake.py --apply
  python scripts/fix_mojibake.py --file data/some_other.json --apply
"""
from __future__ import annotations
import argparse, json, os, shutil
from datetime import datetime

# Common mojibake -> correct character. These are the usual suspects from a
# utf-8 -> cp1252 -> utf-8 round trip.
MOJIBAKE = {
    "\u00e2\u20ac\u201d": "\u2014",  # â€" -> — em dash
    "\u00e2\u20ac\u201c": "\u2013",  # â€" -> – en dash
    "\u00e2\u20ac\u2122": "\u2019",  # â€™ -> ' right single quote
    "\u00e2\u20ac\u0153": "\u201c",  # â€œ -> " left double quote
    "\u00e2\u20ac\u009d": "\u201d",  # â€<9d> -> " right double quote
    "\u00e2\u20ac\u00a6": "\u2026",  # â€¦ -> … ellipsis
    "\u00c3\u00a9": "\u00e9",        # Ã© -> é
    "\u00c2\u00a0": " ",             # Â  -> nbsp -> space
}


def fix(text: str):
    n = 0
    for bad, good in MOJIBAKE.items():
        if bad in text:
            n += text.count(bad)
            text = text.replace(bad, good)
    return text, n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=os.path.join("data", "pipeline_settings.json"))
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    path = args.file

    if not os.path.exists(path):
        print(f"FATAL: {path} not found"); return

    text = open(path, encoding="utf-8").read()
    # must currently parse (we only sanitize text, not fix broken JSON)
    try:
        json.loads(text)
    except Exception as e:
        print(f"FATAL: {path} does not parse as JSON ({e}). Use the repair tool first.")
        return

    fixed, n = fix(text)
    print(f"{path}: {n} mojibake sequence(s) found")
    if n == 0:
        print("Nothing to fix.")
        return

    # show samples
    for bad, good in MOJIBAKE.items():
        if bad in text:
            print(f"  {bad!r} -> {good!r}  (x{text.count(bad)})")

    # validate fixed still parses
    try:
        json.loads(fixed)
    except Exception as e:
        print(f"REFUSING: fixed text no longer parses: {e}")
        return

    if not args.apply:
        print("\n[DRY-RUN] No file written. Re-run with --apply.")
        return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = f"{path}.pre_mojibake_{ts}"
    shutil.copy2(path, bak)
    open(path, "w", encoding="utf-8").write(fixed)
    print(f"\nFixed {path} (backup {bak}). Restart API.")


if __name__ == "__main__":
    main()
