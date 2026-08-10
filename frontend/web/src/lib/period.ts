// Shared reporting period. One definition, used by the ranking and the
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
