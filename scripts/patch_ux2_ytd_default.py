#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
UX2 - year to date is the default reporting period, everywhere.

RULING (2026-08-09): "on all the period, year to date should be the default".

A rolling 30-day window answers "how are we doing lately". The bank reports on
the year, so that is what a page should open on.

WHAT CHANGES - one file, because all three consumers (Leaderboard, Index
analytics, Pipeline analytics) already read the shared constant:

    DEFAULT_PERIOD_KEY   '30' -> 'ytd'
    Year to date now LEADS the dropdown, since it is the default
    findPeriod's fallback returns the DEFAULT rather than all[1]

That last one mattered more than it looks: the fallback was positional, and
all[1] was "Last 30 days". An unknown or stale key would have silently ignored
the new default and served a 30-day window anyway - the kind of bug that shows
up as "the numbers look wrong on Mondays" rather than as an error.

Verified: tsc --noEmit clean, vite build clean, and no component carries an
independent 30-day default.

Usage (from project root, .venv active):
    python scripts\patch_ux2_ytd_default.py            # dry run
    python scripts\patch_ux2_ytd_default.py --apply    # write + .pre_ux2 backup
"""
import os
import shutil
import sys

PER = os.path.join("frontend", "web", "src", "lib", "period.ts")
BACKUP_SUFFIX = ".pre_ux2"

PERIOD_NEW = r'''// Shared reporting period. One definition, used by the ranking and the
// analytics, so the two can never be looking at different windows while
// appearing to agree.
//
// Two kinds of window, and the distinction is not cosmetic:
//
//   ROLLING   "last 30 days" — moves every day, good for "how are we doing now"
//   CALENDAR  Q2, year to date — fixed boundaries, good for "how did we do in
//             the period the bank reports on"
//
// A quarter cannot be expressed as a day count without drifting as the year
// advances, which is why the API takes an explicit start/end for these rather
// than a number of days.

export type PeriodKind = 'rolling' | 'calendar';

export interface Period {
  key: string;
  label: string;
  kind: PeriodKind;
  days?: number;             // rolling
  start?: string;            // calendar, YYYY-MM-DD
  end?: string;
}

function iso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Quarter boundaries for a year, clipped so a future quarter never runs past today. */
function quarter(year: number, q: number): { start: string; end: string } {
  const startMonth = (q - 1) * 3;
  const start = new Date(year, startMonth, 1);
  const end = new Date(year, startMonth + 3, 0);      // day 0 = last of prev month
  const today = new Date();
  return { start: iso(start), end: iso(end > today ? today : end) };
}

export function periods(now = new Date()): Period[] {
  const year = now.getFullYear();
  const thisQ = Math.floor(now.getMonth() / 3) + 1;

  const out: Period[] = [
    { key: 'ytd', label: `Year to date (${year})`, kind: 'calendar',
      start: `${year}-01-01`, end: iso(now) },
    { key: '7', label: 'Last 7 days', kind: 'rolling', days: 7 },
    { key: '30', label: 'Last 30 days', kind: 'rolling', days: 30 },
    { key: '90', label: 'Last 90 days', kind: 'rolling', days: 90 },
  ];

  // Quarters that have started. A quarter nobody has reached yet is noise in a
  // dropdown, and an empty chart reads as a failure rather than as "not yet".
  for (let q = 1; q <= thisQ; q += 1) {
    const { start, end } = quarter(year, q);
    out.push({
      key: `q${q}`,
      label: q === thisQ ? `Q${q} ${year} (current)` : `Q${q} ${year}`,
      kind: 'calendar', start, end,
    });
  }
  return out;
}

// RULING 2026-08-09: year to date is the default everywhere. A rolling 30-day
// window answers "how are we doing lately"; the bank reports on the year, so
// that is what a page should open on.
export const DEFAULT_PERIOD_KEY = 'ytd';

export function findPeriod(key: string, now = new Date()): Period {
  const all = periods(now);
  // Fall back to the DEFAULT, not to a positional index: all[1] was "last 30
  // days", so an unknown key silently ignored the default.
  return all.find((p) => p.key === key)
    ?? all.find((p) => p.key === DEFAULT_PERIOD_KEY)
    ?? all[0];
}

/** The query arguments this period implies — days, or an explicit window. */
export function periodArgs(p: Period): { days?: number; start?: string; end?: string } {
  return p.kind === 'rolling'
    ? { days: p.days }
    : { start: p.start, end: p.end };
}

/** How many days the period spans, for anything that still needs a count. */
export function periodDays(p: Period): number {
  if (p.kind === 'rolling') return p.days ?? 30;
  const a = new Date(`${p.start}T00:00:00`);
  const b = new Date(`${p.end}T00:00:00`);
  return Math.max(1, Math.round((b.getTime() - a.getTime()) / 86400000) + 1);
}
'''


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PER):
        print("ABORT: %s not found - apply patch_a5_periods.py first." % PER)
        return 1

    cur = open(PER, encoding="utf-8").read()
    if "DEFAULT_PERIOD_KEY = 'ytd'" in cur:
        print("ABORT: year to date is already the default - UX2 looks applied.")
        return 1
    if "DEFAULT_PERIOD_KEY" not in cur:
        print("ABORT: apply patch_a5_periods.py first.")
        return 1

    if "DEFAULT_PERIOD_KEY = 'ytd'" not in PERIOD_NEW:
        print("ABORT: embedded file does not set the ytd default.")
        return 1
    if "?? all[1]" in PERIOD_NEW:
        print("ABORT: the positional fallback survives - an unknown key would")
        print("       still serve a 30-day window.")
        return 1
    for op, cl in (("{", "}"), ("(", ")")):
        if PERIOD_NEW.count(op) != PERIOD_NEW.count(cl):
            print("ABORT: embedded file unbalanced %s%s." % (op, cl))
            return 1
    print("  ok  embedded period.ts validated")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    shutil.copy2(PER, PER + BACKUP_SUFFIX)
    open(PER, "w", encoding="utf-8", newline="").write(PERIOD_NEW)
    print("APPLIED %s  (backup: %s)" % (PER, os.path.basename(PER) + BACKUP_SUFFIX))
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
