#!/usr/bin/env python3
"""scripts/harden_json_encoding.py — add encoding="utf-8" to bare read_text()
and write_text() calls so JSON I/O stops defaulting to cp1252 on Windows.

Root cause of recurring corruption (mojibake 'â€"' where '—' belongs, and the
users.json.corrupt-* files): I/O without an explicit encoding uses the platform
default (cp1252 on Windows), mangling non-ASCII on round-trips. utf-8 fixes it.

PAREN-AWARE: write_text(...) arguments often contain nested parens
(json.dumps(...)), so this walks characters to find the matching close paren
rather than using a naive regex. Lines that ALREADY have encoding= are skipped.
Idempotent + verifies the result still compiles before writing.

  read_text()         -> read_text(encoding="utf-8")
  write_text(<args>)  -> write_text(<args>, encoding="utf-8")   [if no encoding]

Usage (project root, venv active):
  python scripts/harden_json_encoding.py            # dry-run
  python scripts/harden_json_encoding.py --apply    # back up + rewrite
"""
from __future__ import annotations
import argparse, os, shutil, sys
from datetime import datetime

TARGETS = [os.path.join("utils", "core.py"), os.path.join("utils", "db.py")]


def _find_matching_paren(s: str, open_idx: int) -> int:
    """Given index of '(', return index of the matching ')', respecting nesting
    and skipping over string literals. -1 if unbalanced."""
    depth = 0
    i = open_idx
    n = len(s)
    quote = None
    while i < n:
        c = s[i]
        if quote:
            if c == "\\":
                i += 2
                continue
            if c == quote:
                quote = None
            i += 1
            continue
        if c in ("'", '"'):
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _process_call(src: str, method: str) -> tuple[str, int]:
    """Add encoding="utf-8" to every `.<method>(...)` call lacking it."""
    out = []
    i = 0
    n = len(src)
    token = "." + method + "("
    count = 0
    while i < n:
        j = src.find(token, i)
        if j == -1:
            out.append(src[i:])
            break
        open_idx = j + len(token) - 1  # index of '('
        close_idx = _find_matching_paren(src, open_idx)
        if close_idx == -1:
            out.append(src[i:])
            break
        args = src[open_idx + 1:close_idx]
        out.append(src[i:open_idx + 1])  # up to and including '('
        if "encoding=" in args:
            out.append(args)  # already has encoding; leave untouched
        elif args.strip() == "":
            out.append('encoding="utf-8"')
            count += 1
        else:
            out.append(args + ', encoding="utf-8"')
            count += 1
        out.append(")")
        i = close_idx + 1
    return "".join(out), count


def transform(src: str):
    src, nr = _process_call(src, "read_text")
    src, nw = _process_call(src, "write_text")
    return src, nr, nw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    plans = []
    tr = tw = 0
    for path in TARGETS:
        if not os.path.exists(path):
            print(f"  (skip, absent) {path}")
            continue
        src = open(path, encoding="utf-8").read()
        new, nr, nw = transform(src)
        plans.append((path, src, new, nr, nw))
        tr += nr; tw += nw
        print(f"  {path}: +{nr} read_text, +{nw} write_text")

    print(f"\nTOTAL: {tr} reads + {tw} writes hardened to utf-8")

    # show first 3 sample diffs
    shown = 0
    for path, src, new, nr, nw in plans:
        if not (nr or nw):
            continue
        for o, nline in zip(src.splitlines(), new.splitlines()):
            if o != nline and shown < 3:
                print(f"\nsample ({path}):\n  - {o.strip()}\n  + {nline.strip()}")
                shown += 1

    if not args.apply:
        print("\n[DRY-RUN] No files written. Re-run with --apply.")
        return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    for path, src, new, nr, nw in plans:
        if not (nr or nw):
            continue
        try:
            compile(new, path, "exec")
        except SyntaxError as e:
            print(f"REFUSING: transform broke {path} syntax: {e}")
            sys.exit(3)
        bak = f"{path}.pre_utf8_{ts}"
        shutil.copy2(path, bak)
        open(path, "w", encoding="utf-8").write(new)
        print(f"  wrote {path} (backup {bak})")
    print("\nDone.")


if __name__ == "__main__":
    main()
