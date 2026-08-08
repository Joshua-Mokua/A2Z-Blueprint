#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TZ-1 — stop date-only timestamps rendering as 03:00 AM.

ROOT CAUSE (proven, not theorised):
  * pipeline_deals in Postgres has no created_at column — only open_date DATE.
    diag_timezone.py section C confirmed metadata->>'created_at' returns NO ROWS.
  * api_lms_journey._events_from_deal:121 falls back:
        created = deal.get("created_at") or deal.get("open_date")
    so a DB-sourced deal's "deal_created" event carries a DATE, e.g. "2026-08-08".
  * Timeline.fmtWhen does new Date("2026-08-08").toLocaleString(). Per the
    ECMAScript spec a DATE-ONLY ISO string is parsed as UTC midnight, so in EAT
    it renders "8/8/2026, 3:00:00 AM" — a fabricated small-hours timestamp on a
    deal that was actually created during the working day.

  Verified in node under TZ=Africa/Nairobi:
      "2026-08-08"                -> 8/8/2026, 3:00:00 AM     (UTC midnight, +3)
      "2026-08-08T14:30:00"       -> 8/8/2026, 2:30:00 PM     (local, correct)
      "2026-08-08T14:30:00+03:00" -> 8/8/2026, 2:30:00 PM     (aware, correct)

This patch fixes the RENDERING half only — the honest half. A date-only value
carries no clock time, so we stop inventing one. The storage half (giving
pipeline_deals a real created_at) is a separate, larger batch.

Changes:
  1. NEW  lib/datetime.ts — isDateOnly / fmtWhen / fmtDate / parseTs, one place
          for the date-only rule. Phase 3's history grid will want this too.
  2. Timeline.tsx  — local fmtWhen replaced by the shared one.
  3. Referrals.tsx — local formatDate replaced by the shared fmtDate.
  4. Pipeline.tsx  — daysOpen parses via parseTs, so a date-only open_date is
     measured from local midnight rather than 03:00, which could previously
     round a deal's age down across a day boundary.

Usage (from project root, .venv active):
    python scripts\\patch_tz1_dateonly.py            # dry run
    python scripts\\patch_tz1_dateonly.py --apply    # write + .pre_tz1 backups
"""
import os
import shutil
import sys

LIB = os.path.join("frontend", "web", "src", "lib", "datetime.ts")
TIMELINE = os.path.join("frontend", "web", "src", "components", "Timeline.tsx")
REFERRALS = os.path.join("frontend", "web", "src", "pages", "Referrals.tsx")
PIPELINE = os.path.join("frontend", "web", "src", "pages", "Pipeline.tsx")
BACKUP_SUFFIX = ".pre_tz1"

NEW_LIB = """// Date/time rendering rules for A2Z MIS 360.
//
// THE DATE-ONLY TRAP
// ------------------
// Per the ECMAScript spec, `new Date("2026-08-08")` — a date-only ISO string —
// is parsed as UTC midnight, whereas `new Date("2026-08-08T14:30:00")` — with a
// time part and no offset — is parsed as LOCAL time. So in Nairobi (UTC+3) a
// bare date silently becomes 03:00 AM local:
//
//     "2026-08-08"                -> 8/8/2026, 3:00:00 AM   <-- fabricated
//     "2026-08-08T14:30:00"       -> 8/8/2026, 2:30:00 PM
//     "2026-08-08T14:30:00+03:00" -> 8/8/2026, 2:30:00 PM
//
// This matters because several backend records carry DATE columns, not
// timestamps (pipeline_deals.open_date and .last_updated among them), and the
// case-journey builder falls back to open_date when a deal has no created_at.
// Rendering those with toLocaleString() invents a small-hours clock time and
// makes deals look as though they were opened after midnight.
//
// The rule here: a value with no time part is displayed as a DATE. We never
// invent a clock time we were not given.

/** True for "2026-08-08" — a date with no time component. */
export function isDateOnly(value: string): boolean {
  return /^\\d{4}-\\d{2}-\\d{2}$/.test(value.trim());
}

/** Parse any timestamp form this codebase produces, without the UTC-midnight
 *  trap: date-only values are anchored to LOCAL midnight. Returns null when
 *  the value is missing or unparseable. */
export function parseTs(value: string | undefined | null): Date | null {
  if (!value) return null;
  const s = String(value).trim();
  if (!s) return null;
  if (isDateOnly(s)) {
    const [y, m, d] = s.split('-').map(Number);
    return new Date(y, m - 1, d);          // local midnight, not UTC midnight
  }
  const d = new Date(s.includes('T') ? s : s.replace(' ', 'T'));
  return Number.isNaN(d.getTime()) ? null : d;
}

/** Timestamp for display. Date-only values render as a date with no invented
 *  clock time; full timestamps render date + time. Falls back to the raw
 *  string when it cannot be parsed, so nothing silently disappears. */
export function fmtWhen(value: string | undefined | null): string {
  if (!value) return '';
  const s = String(value).trim();
  const d = parseTs(s);
  if (!d) return s;
  return isDateOnly(s) ? d.toLocaleDateString() : d.toLocaleString();
}

/** Date-only display, whatever the input carries. */
export function fmtDate(value: string | undefined | null): string {
  const d = parseTs(value);
  return d ? d.toLocaleDateString() : '';
}
"""

# ── Timeline.tsx ─────────────────────────────────────────────────────────────
TL_OLD_FN = """function fmtWhen(at?: string): string {
  if (!at) return '';
  const d = new Date(at);
  if (Number.isNaN(d.getTime())) return at;
  return d.toLocaleString();
}

"""
TL_NEW_FN = ""

TL_OLD_IMPORT = """import type { LoanAppHistoryEvent } from '@/types/lms';"""
TL_NEW_IMPORT = """import type { LoanAppHistoryEvent } from '@/types/lms';
import { fmtWhen } from '@/lib/datetime';"""

# ── Referrals.tsx ────────────────────────────────────────────────────────────
RF_OLD_FN = """function formatDate(s: string | undefined): string {
  if (!s) return '';
  const d = new Date(s);
  return isNaN(d.getTime()) ? '' : d.toLocaleDateString();
}"""
RF_NEW_FN = """const formatDate = fmtDate;"""

# ── Pipeline.tsx ─────────────────────────────────────────────────────────────
PP_OLD_FN = """  const raw = deal.created_at || deal.open_date || deal.updated_at;
  if (!raw) return null;
  const start = new Date(raw).getTime();
  if (!Number.isFinite(start)) return null;"""
PP_NEW_FN = """  const raw = deal.created_at || deal.open_date || deal.updated_at;
  if (!raw) return null;
  // parseTs, not new Date: a date-only open_date must anchor to LOCAL midnight,
  // otherwise the age is measured from 03:00 and can round down a whole day.
  const parsed = parseTs(raw);
  if (!parsed) return null;
  const start = parsed.getTime();
  if (!Number.isFinite(start)) return null;"""


def find_import_anchor(src, path):
    """Insert a lib/datetime import after the last existing @/ import line."""
    lines = src.split("\n")
    last = -1
    for i, ln in enumerate(lines):
        if ln.startswith("import ") and "'@/" in ln:
            last = i
    if last < 0:
        return None
    return lines[last]


def main():
    apply = "--apply" in sys.argv

    for path in (TIMELINE, REFERRALS, PIPELINE):
        if not os.path.isfile(path):
            print("ABORT: %s not found. Run from the project root." % path)
            return 1
    if os.path.exists(LIB):
        print("ABORT: %s already exists — TZ-1 looks applied." % LIB)
        return 1

    srcs = {}
    for path in (TIMELINE, REFERRALS, PIPELINE):
        with open(path, "r", encoding="utf-8") as fh:
            srcs[path] = fh.read()

    edits = [
        (TIMELINE, "Timeline — import shared fmtWhen", TL_OLD_IMPORT, TL_NEW_IMPORT),
        (TIMELINE, "Timeline — drop local fmtWhen", TL_OLD_FN, TL_NEW_FN),
        (REFERRALS, "Referrals — formatDate -> fmtDate", RF_OLD_FN, RF_NEW_FN),
        (PIPELINE, "Pipeline — daysOpen via parseTs", PP_OLD_FN, PP_NEW_FN),
    ]

    for path, name, old, new in edits:
        n = srcs[path].count(old)
        if n != 1:
            print("ABORT: anchor '%s' matched %d times in %s (expected 1)."
                  % (name, n, os.path.basename(path)))
            return 1
        srcs[path] = srcs[path].replace(old, new, 1)
        print("  ok  %s" % name)

    # Import injection — check for the import STATEMENT, never the symbol name.
    for path, stmt in ((REFERRALS, "import { fmtDate } from '@/lib/datetime';"),
                       (PIPELINE, "import { parseTs } from '@/lib/datetime';")):
        if stmt in srcs[path]:
            print("  ..  import already present in %s" % os.path.basename(path))
            continue
        anchor = find_import_anchor(srcs[path], path)
        if not anchor:
            print("ABORT: no '@/' import line to anchor on in %s" % os.path.basename(path))
            return 1
        srcs[path] = srcs[path].replace(anchor, anchor + "\n" + stmt, 1)
        print("  ok  import injected into %s" % os.path.basename(path))

    for path in (TIMELINE, REFERRALS, PIPELINE):
        for opener, closer in (("{", "}"), ("(", ")"), ("[", "]")):
            if srcs[path].count(opener) != srcs[path].count(closer):
                print("ABORT: unbalanced %s%s in %s." % (opener, closer, os.path.basename(path)))
                return 1

    print("\nAll anchors matched, post-checks clean.")

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return 0

    with open(LIB, "w", encoding="utf-8", newline="") as fh:
        fh.write(NEW_LIB)
    print("CREATED %s" % LIB)
    for path in (TIMELINE, REFERRALS, PIPELINE):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(srcs[path])
        print("APPLIED %s  (backup: %s)" % (path, os.path.basename(path) + BACKUP_SUFFIX))

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED_PROCEED_WITH_COMMIT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
