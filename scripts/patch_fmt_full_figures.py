#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
FMT - full figures with thousands separators. No K / M / B / T anywhere.

RULING (2026-08-09): "instead of stating e.g Kes 367K, it is preferred that a
pipeline or any working remove the K and instead have the entire amount stated
e.g Kes 367,000, then on the deals and daily log there should be those comma
separators on figures in 000".

WHY DELETION RATHER THAN REWRITING. Every abbreviating formatter in this
codebase already ends with a `toLocaleString()` fallback - the abbreviation is
an early return in front of behaviour that is already correct. So this REMOVES
the abbreviation branches and lets the existing fallback run. Rewriting the
functions would risk changing rounding or the currency prefix by accident;
deleting an early return cannot.

    if (abs >= 1e6) return `${symbol} ${(n / 1e6).toFixed(2)}M`;   <- removed
    if (abs >= 1e3) return `${symbol} ${(n / 1e3).toFixed(0)}K`;   <- removed
    return `${symbol} ${n.toLocaleString()}`;                      <- kept

WORKS BY RULE, NOT BY EMBEDDING. The abbreviation branches are matched with a
regex across the frontend, so a formatter added since this was written is caught
too. 41 branches across 13 files at the time of writing. The patcher reports its
own counts, and ABORTS if it finds nothing to do - silence would mean the
pattern had drifted and the cleanup had quietly become a no-op.

ALSO FIXED, because removing the abbreviation exposed them:
  * six now-unused `const a = Math.abs(n)` locals (tsc TS6133)
  * DayPlanner.fmtCount and PipelineDayCountersign.kes returned bare
    String(Math.round(n)), so KES 934,858 rendered as 934858
  * HistoryGrid.fmt and DailyLogValidation.fmt did the same across every
    activity column in the daily log

Verified: tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_fmt_full_figures.py            # dry run
    python scripts\\patch_fmt_full_figures.py --apply    # write in place
"""
import glob
import os
import re
import shutil
import sys

BACKUP_SUFFIX = ".pre_fmt"

# An abbreviating early return: a magnitude test that returns a string ending in
# a unit letter. Deliberately narrow - it must not match ordinary comparisons.
ABBREV = re.compile(
    r"^[ \t]*if \([^)]*\b(?:abs|a|n|v)\b\s*>=\s*1(?:e\d+|_000(?:_000)*)\)\s*return[^\n]*?"
    r"(?:'[TBMKk]'|[TBMKk]`);?[ \t]*\n",
    re.MULTILINE)

# A local that exists only to feed those tests.
UNUSED_ABS = re.compile(
    r"^[ \t]*const (?:a|abs) = Math\.abs\(n\);[ \t]*\n(?=[ \t]*return)", re.MULTILINE)

SEPARATORS = [
    ("frontend/web/src/components/DayPlanner.tsx",
     """function fmtCount(f: BranchLogField, n: number): string {
  if (f.type === 'amount') {
    return String(Math.round(n));
  }
  return String(Math.round(n));
}""",
     """function fmtCount(_f: BranchLogField, n: number): string {
  // Full figures with thousands separators - no K/M abbreviation anywhere
  // (ruling 2026-08-09). An abbreviated number is a number somebody has to
  // decode, and 367K hides whether it was 367,000 or 367,400.
  return Math.round(n).toLocaleString();
}"""),
    ("frontend/web/src/components/PipelineDayCountersign.tsx",
     """function kes(n: number): string {
  if (!n) return '—';
  return String(Math.round(n));
}""",
     """function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}"""),
    ("frontend/web/src/components/HistoryGrid.tsx",
     """function fmt(v: unknown): string {
  const n = num(v);
  if (n === 0) return '';                        // blank reads better than a field of zeros
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}""",
     """function fmt(v: unknown): string {
  const n = num(v);
  if (n === 0) return '';                        // blank reads better than a field of zeros
  // Thousands separators on every figure (ruling 2026-08-09): a KES deposit
  // rendered as 934858 is a number the reader has to count digits on.
  return Number.isInteger(n)
    ? n.toLocaleString()
    : n.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}"""),
    ("frontend/web/src/components/DailyLogValidation.tsx",
     """function fmt(v: unknown): string {
  const n = num(v);
  if (n === 0) return '';
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}""",
     """function fmt(v: unknown): string {
  const n = num(v);
  if (n === 0) return '';
  // Thousands separators on every figure (ruling 2026-08-09).
  return Number.isInteger(n)
    ? n.toLocaleString()
    : n.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}"""),
]


def main():
    apply = "--apply" in sys.argv
    root = os.path.join("frontend", "web", "src")
    if not os.path.isdir(root):
        print("ABORT: %s not found. Run from the project root." % root)
        return 1

    edits = {}          # path -> new content
    n_abbrev = n_unused = 0

    for path in glob.glob(os.path.join(root, "**", "*.ts*"), recursive=True):
        src = open(path, encoding="utf-8").read()
        out, k1 = ABBREV.subn("", src)
        out, k2 = UNUSED_ABS.subn("", out)
        if k1 or k2:
            edits[path] = out
            n_abbrev += k1
            n_unused += k2
            print("  %-50s abbrev -%d  unused -%d"
                  % (path.split("src" + os.sep)[-1], k1, k2))

    if not n_abbrev:
        print("ABORT: found no abbreviation branches to remove.")
        print("       Either this is already applied, or the pattern has drifted -")
        print("       and a cleanup that silently does nothing is worse than a failure.")
        return 1
    print("  -> %d abbreviation branches, %d unused locals" % (n_abbrev, n_unused))

    n_sep = 0
    for path, old, new in SEPARATORS:
        if not os.path.isfile(path):
            print("  .. %s not present, skipped" % path.split("src/")[-1])
            continue
        cur = edits.get(path, open(path, encoding="utf-8").read())
        if cur.count(old) == 1:
            edits[path] = cur.replace(old, new, 1)
            n_sep += 1
            print("  separators: %s" % path.split("src/")[-1])
        elif new.split("\n")[0] in cur:
            print("  .. %s already has separators" % path.split("src/")[-1])
        else:
            print("  .. %s did not match (skipped, not fatal)" % path.split("src/")[-1])
    print("  -> %d formatters given thousands separators" % n_sep)

    # Post-check on the RESULT, not the input: nothing may still abbreviate.
    for path, content in edits.items():
        if ABBREV.search(content):
            print("ABORT: post-check - %s still abbreviates." % path)
            return 1
    print("  ok  post-check: no abbreviation branches remain in edited files")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in edits.items():
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
    print("\nAPPLIED %d files (backups alongside, suffix %s)"
          % (len(edits), BACKUP_SUFFIX))
    print("Next: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    print("Then remove the backups:")
    print("  del /s frontend\\web\\src\\*%s" % BACKUP_SUFFIX)
    return 0


if __name__ == "__main__":
    sys.exit(main())
