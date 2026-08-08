// Date/time rendering rules for A2Z MIS 360.
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
  return /^\d{4}-\d{2}-\d{2}$/.test(value.trim());
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
