#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
WC-2a — "day context": make the Daily Log header say something worth reading.

First live consumer of utils/workcal.py. Replaces the static "Today's activity"
heading with a personalised line plus real calendar facts:

    Dear Josh, the day is all yours — make every activity count.
    Saturday · day 220 of 365
    [Half day · 4h] [146 days left in 2026] [121 working days] [968 working hours]

Files touched:
  1. data/work_calendar.json  — adds hours_per_day (8.0) so "working hours"
                                is configurable rather than a magic number.
  2. utils/workcal.py         — hours_per_day(), working_hours(), day_context()
  3. utils/api_branch_log.py  — GET /api/branch-log/day-context
  4. frontend/.../lib/api.ts  — DayContext type + fetchDayContext()
  5. frontend/.../BranchLog.tsx — the header itself

Counts INCLUDE today, which is what people mean by "days left in the year".
Working hours weight Saturdays at 0.5, so a Saturday contributes 4h not 8h, and
Sundays/holidays contribute nothing.

Usage (from project root, .venv active):
    python scripts\\patch_wc2a_daycontext.py            # dry run
    python scripts\\patch_wc2a_daycontext.py --apply    # write + .pre_wc2a backups
"""
import json
import os
import shutil
import sys

CFG = os.path.join("data", "work_calendar.json")
WORKCAL = os.path.join("utils", "workcal.py")
API = os.path.join("utils", "api_branch_log.py")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
PAGE = os.path.join("frontend", "web", "src", "pages", "BranchLog.tsx")
BACKUP_SUFFIX = ".pre_wc2a"

# ── 1. workcal additions ─────────────────────────────────────────────────────
WC_OLD = '''def describe(d) -> dict:
    """Everything a UI needs about one date, in one call."""
    d = _as_date(d)
    return {
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "working": is_working_day(d),
        "weight": target_weight(d),
        "holiday": is_holiday(d),
        "label": holiday_label(d),
        "half_day": target_weight(d) == 0.5,
    }'''

WC_NEW = '''def describe(d) -> dict:
    """Everything a UI needs about one date, in one call."""
    d = _as_date(d)
    return {
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "working": is_working_day(d),
        "weight": target_weight(d),
        "holiday": is_holiday(d),
        "label": holiday_label(d),
        "half_day": target_weight(d) == 0.5,
    }


# ── working time ─────────────────────────────────────────────────────────────
def hours_per_day() -> float:
    """Hours in a FULL working day. Saturday inherits this at its 0.5 weight.

    The Employment Act 2007 s.27 caps the general working week at 52 hours over
    six days; the standard banking week runs 8-9 hours Monday to Friday. 8.0 is
    the default here and is configurable per deployment.
    """
    try:
        return float(_load().get("hours_per_day", 8.0))
    except (TypeError, ValueError):
        return 8.0


def working_hours(d) -> float:
    """Expected working hours on this date (0 on Sundays and holidays)."""
    return round(target_weight(d) * hours_per_day(), 2)


def day_context(d=None) -> dict:
    """Where this date sits in the year, and how much working time is left.

    All "remaining" figures INCLUDE the date itself — that is what people mean
    by "days left in the year". working_hours_remaining weights Saturdays at
    0.5, so it is real capacity rather than a calendar-day count.
    """
    d = _as_date(d) if d is not None else date.today()
    jan1 = date(d.year, 1, 1)
    dec31 = date(d.year, 12, 31)
    remaining = working_days_in(d, dec31)
    weight = target_weight(d)
    return {
        "date": d.isoformat(),
        "weekday": d.strftime("%A"),
        "day_of_year": (d - jan1).days + 1,
        "days_in_year": (dec31 - jan1).days + 1,
        "days_remaining": (dec31 - d).days + 1,
        "working_days_remaining": len(remaining),
        "working_hours_remaining": round(
            sum(target_weight(x) for x in remaining) * hours_per_day(), 1),
        "working": weight > 0.0,
        "half_day": weight == 0.5,
        "weight": weight,
        "hours_today": working_hours(d),
        "holiday": is_holiday(d),
        "holiday_label": holiday_label(d),
        "next_working_day": next_working_day(d).isoformat(),
    }'''

# ── 2. API route ─────────────────────────────────────────────────────────────
API_OLD = '''@router.get("/fields")'''

API_NEW = '''@router.get("/day-context")
def branch_log_day_context(user: dict = Depends(get_current_user)):
    """Calendar context for today: position in the year, what remains of it, and
    how much of that is actually working time under the Kenya work calendar.

    Read-only and cheap; the Daily Log header calls it once on mount.
    """
    me = _identity(user)
    try:
        from utils import workcal
        ctx = dict(workcal.day_context())
    except Exception as exc:
        raise HTTPException(status_code=500,
                            detail=f"Work calendar unavailable: {exc}")
    ctx["staff_name"] = me.get("staff_name", "")
    ctx["staff_code"] = me.get("staff_code", "")
    return ctx


@router.get("/fields")'''

# ── 3. api.ts client ─────────────────────────────────────────────────────────
TS_OLD = '''export async function fetchBranchLogFields(): Promise<{ fields: BranchLogField[] }> {'''

TS_NEW = '''// Calendar context for today (Kenya work calendar: weekends, half-day Saturdays,
// gazetted holidays). Counts include today.
export interface DayContext {
  date: string; weekday: string;
  day_of_year: number; days_in_year: number; days_remaining: number;
  working_days_remaining: number; working_hours_remaining: number;
  working: boolean; half_day: boolean; weight: number; hours_today: number;
  holiday: boolean; holiday_label: string; next_working_day: string;
  staff_name?: string; staff_code?: string;
}
export async function fetchDayContext(): Promise<DayContext> {
  return getJson<DayContext>('/branch-log/day-context');
}

export async function fetchBranchLogFields(): Promise<{ fields: BranchLogField[] }> {'''

# ── 4. BranchLog imports ─────────────────────────────────────────────────────
PG_OLD_IMPORT = '''  type BranchLogField, type BranchLogEntry, type BranchLogActivity, type BranchLogRankRow, type ExtraActivity,
  type HourlyMap,
} from '@/lib/api';'''

PG_NEW_IMPORT = '''  fetchDayContext,
  type BranchLogField, type BranchLogEntry, type BranchLogActivity, type BranchLogRankRow, type ExtraActivity,
  type HourlyMap, type DayContext,
} from '@/lib/api';
import { displayName } from '@/lib/names';'''

# ── 5. state + loader ────────────────────────────────────────────────────────
PG_OLD_STATE = '''  const [lastSaved, setLastSaved] = useState<Date | null>(null);'''

PG_NEW_STATE = '''  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [dayCtx, setDayCtx] = useState<DayContext | null>(null);'''

PG_OLD_LOADER = '''  const loadActs = useCallback(async () => {
    try { const r = await fetchBranchLogActivities(); setExtraActs(r.extra); } catch { /* ignore */ }
  }, []);'''

PG_NEW_LOADER = '''  const loadActs = useCallback(async () => {
    try { const r = await fetchBranchLogActivities(); setExtraActs(r.extra); } catch { /* ignore */ }
  }, []);
  // Calendar context for the header. Failure is silent: a missing work calendar
  // must not stop anyone logging their day.
  const loadDayCtx = useCallback(async () => {
    try { setDayCtx(await fetchDayContext()); } catch { /* header falls back */ }
  }, []);'''

PG_OLD_EFFECT = '''  useEffect(() => { void loadFields(); void loadMine(); void loadAuto(); void loadCfg(); }, [loadFields, loadMine, loadAuto, loadCfg]);'''

PG_NEW_EFFECT = '''  useEffect(() => { void loadFields(); void loadMine(); void loadAuto(); void loadCfg(); void loadDayCtx(); }, [loadFields, loadMine, loadAuto, loadCfg, loadDayCtx]);'''

# ── 6. the header itself ─────────────────────────────────────────────────────
PG_OLD_HEADER = '''          <Card.Header><h2 className="text-base font-semibold text-gray-900">Today&apos;s activity</h2></Card.Header>'''

PG_NEW_HEADER = '''          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-base font-semibold text-gray-900">
                  {firstName ? `Dear ${firstName}, the day is all yours — make every activity count.`
                             : 'The day is all yours — make every activity count.'}
                </h2>
                <p className="mt-0.5 text-xs text-gray-500">
                  {dayCtx
                    ? `${dayCtx.weekday} · day ${dayCtx.day_of_year} of ${dayCtx.days_in_year}`
                    : 'Today\\u2019s activity'}
                </p>
              </div>
              {dayCtx && (
                <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                  {dayCtx.holiday && (
                    <span className="rounded-full bg-[#FAEEDA] px-2.5 py-1 font-medium text-[#854F0B]">
                      {dayCtx.holiday_label || 'Public holiday'}
                    </span>
                  )}
                  {!dayCtx.holiday && dayCtx.half_day && (
                    <span className="rounded-full bg-[#EAF3DE] px-2.5 py-1 font-medium text-[#3B6D11]">
                      Half day · {dayCtx.hours_today}h
                    </span>
                  )}
                  {!dayCtx.working && !dayCtx.holiday && (
                    <span className="rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-500">
                      Rest day
                    </span>
                  )}
                  <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                    {dayCtx.days_remaining.toLocaleString()} days left in {dayCtx.date.slice(0, 4)}
                  </span>
                  <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                    {dayCtx.working_days_remaining.toLocaleString()} working days
                  </span>
                  <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[#0C447C]">
                    {dayCtx.working_hours_remaining.toLocaleString()} working hours
                  </span>
                </div>
              )}
            </div>
          </Card.Header>'''

# ── 7. firstName derivation ──────────────────────────────────────────────────
PG_OLD_DATELABEL = '''  // DayPlanner renders the live day index itself (sum of count x weight over hours).
  const dateLabel = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });'''

PG_NEW_DATELABEL = '''  // DayPlanner renders the live day index itself (sum of count x weight over hours).
  const dateLabel = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });
  // Greeting name: prefer the server-resolved staff name, fall back to the JWT
  // identity, and render an impersonal greeting rather than "Dear ," if neither.
  const firstName = displayName(dayCtx?.staff_name || user?.full_name || '');'''

EDITS = [
    (WORKCAL, "workcal — hours_per_day / working_hours / day_context", WC_OLD, WC_NEW),
    (API, "api_branch_log — GET /day-context", API_OLD, API_NEW),
    (APITS, "api.ts — DayContext + fetchDayContext", TS_OLD, TS_NEW),
    (PAGE, "BranchLog — imports", PG_OLD_IMPORT, PG_NEW_IMPORT),
    (PAGE, "BranchLog — dayCtx state", PG_OLD_STATE, PG_NEW_STATE),
    (PAGE, "BranchLog — loadDayCtx", PG_OLD_LOADER, PG_NEW_LOADER),
    (PAGE, "BranchLog — mount effect", PG_OLD_EFFECT, PG_NEW_EFFECT),
    (PAGE, "BranchLog — firstName", PG_OLD_DATELABEL, PG_NEW_DATELABEL),
    (PAGE, "BranchLog — informative Card.Header", PG_OLD_HEADER, PG_NEW_HEADER),
]

FILES = [WORKCAL, API, APITS, PAGE]


def main():
    apply = "--apply" in sys.argv

    for path in FILES + [CFG]:
        if not os.path.isfile(path):
            print("ABORT: %s not found." % path)
            if path in (CFG, WORKCAL):
                print("       Run install_wc1_workcal.py --apply first.")
            return 1

    srcs = {}
    for path in FILES:
        with open(path, "r", encoding="utf-8") as fh:
            srcs[path] = fh.read()

    if "def day_context" in srcs[WORKCAL]:
        print("ABORT: workcal already has day_context — WC-2a looks applied.")
        return 1

    for path, name, old, new in EDITS:
        n = srcs[path].count(old)
        if n != 1:
            print("ABORT: anchor '%s' matched %d times in %s (expected 1)."
                  % (name, n, os.path.basename(path)))
            return 1
        srcs[path] = srcs[path].replace(old, new, 1)
        print("  ok  %s" % name)

    # config: add hours_per_day without disturbing anything else
    with open(CFG, "r", encoding="utf-8") as fh:
        cfg = json.load(fh)
    if not isinstance(cfg, dict) or "weekly_pattern" not in cfg:
        print("ABORT: %s is not a valid work calendar — refusing to write." % CFG)
        return 1
    cfg_changed = "hours_per_day" not in cfg
    if cfg_changed:
        cfg["hours_per_day"] = 8.0
        print("  ok  work_calendar.json — hours_per_day: 8.0")
    else:
        print("  ..  work_calendar.json already has hours_per_day")

    for path in (APITS, PAGE):
        for opener, closer in (("{", "}"), ("(", ")"), ("[", "]")):
            if srcs[path].count(opener) != srcs[path].count(closer):
                print("ABORT: unbalanced %s%s in %s." % (opener, closer, os.path.basename(path)))
                return 1

    print("\n%d/%d anchors matched across %d files, post-checks clean."
          % (len(EDITS), len(EDITS), len(FILES)))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return 0

    for path in FILES:
        shutil.copy2(path, path + BACKUP_SUFFIX)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(srcs[path])
        print("APPLIED %s" % path)

    if cfg_changed:
        shutil.copy2(CFG, CFG + BACKUP_SUFFIX)
        tmp = CFG + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, CFG)
        print("APPLIED %s" % CFG)

    print("\nNext, in this order:")
    print("  1. python -c \"import sys;sys.path.insert(0,'.');"
          "from utils import workcal;import json;print(json.dumps(workcal.day_context(),indent=2))\"")
    print("  2. pushd frontend\\web && pnpm tsc --noEmit && popd && "
          "echo TSC_PASSED_PROCEED_WITH_COMMIT")
    print("  3. restart the API (uvicorn) so the new route is mounted")
    return 0


if __name__ == "__main__":
    sys.exit(main())
