#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 2c-c — fit the Entry tab in one viewport, and give the timeline some life.

1. Two-column Entry (lg+): planner left, sidebar right holding the auto-activity
   feed, remarks, save status and the two action buttons. Save/Submit now sit
   beside the timeline instead of below it, so they are reachable without
   scrolling the page.

2. Timeline height follows the viewport — calc(100vh - 21rem) with a 17rem floor
   — instead of a fixed 31rem, so the card fits whatever screen it lands on.

3. Time-of-day colour coding: each hour carries a 3px left rail and a coloured
   time pill by period (morning / afternoon / evening / night), and hours with
   activity pick up a matching tint. Brand palette only — #0082BB, #669438,
   #005B82, grays. Period boundaries are wall-clock, independent of dayStart/End.

4. Removes the footer hint line, the "Jump to now" button and the empty-state
   tip — reclaiming three lines of vertical space for the additions still coming.
   (Dead code goes with them: jumpToNow, hasAnyContent, scrollToHour's smooth arg.)

Usage (from project root, .venv active):
    python scripts\\patch_phase2cc_compact.py            # dry run
    python scripts\\patch_phase2cc_compact.py --apply    # write + .pre_phase2cc backups
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "BranchLog.tsx")
PLANNER = os.path.join("frontend", "web", "src", "components", "DayPlanner.tsx")
BACKUP_SUFFIX = ".pre_phase2cc"

# ── DayPlanner: period palette ───────────────────────────────────────────────
PL_OLD_CHIPFN = """function chipClass(key: string): string {
  return CHIP[FAMILY[key] ?? 'gray'];
}"""

PL_NEW_CHIPFN = """function chipClass(key: string): string {
  return CHIP[FAMILY[key] ?? 'gray'];
}

// Time-of-day colouring. Deliberately wall-clock and independent of
// dayStart/dayEnd — those control what the scroll box parks on, whereas
// morning/afternoon/evening are what the hour actually IS. Brand palette only.
type Period = 'night' | 'morning' | 'afternoon' | 'evening';

function periodOf(h: number): Period {
  if (h >= 8 && h <= 11) return 'morning';
  if (h >= 12 && h <= 16) return 'afternoon';
  if (h >= 17 && h <= 19) return 'evening';
  return 'night';
}

const PERIOD: Record<Period, { rail: string; pill: string; tint: string }> = {
  morning:   { rail: '#0082BB', pill: 'bg-[#E6F1FB] text-[#0C447C]', tint: 'bg-[#0082BB]/[0.04]' },
  afternoon: { rail: '#669438', pill: 'bg-[#EAF3DE] text-[#3B6D11]', tint: 'bg-[#669438]/[0.05]' },
  evening:   { rail: '#005B82', pill: 'bg-[#DDEAF1] text-[#004965]', tint: 'bg-[#005B82]/[0.04]' },
  night:     { rail: '#EDEDED', pill: 'bg-gray-100 text-gray-400',   tint: 'bg-gray-100/80' },
};"""

# ── DayPlanner: drop the smooth-scroll arg (only jumpToNow used it) ──────────
PL_OLD_SCROLLFN = """  function scrollToHour(h: number, smooth = false) {
    const el = rowRefs.current[h];
    const box = scrollRef.current;
    if (!el || !box) return;
    if (smooth) box.scrollTo({ top: el.offsetTop, behavior: 'smooth' });
    else box.scrollTop = el.offsetTop;
  }"""

PL_NEW_SCROLLFN = """  function scrollToHour(h: number) {
    const el = rowRefs.current[h];
    const box = scrollRef.current;
    if (el && box) box.scrollTop = el.offsetTop;
  }"""

PL_OLD_JUMP = """  }, []);

  function jumpToNow() {
    setOpenHour(nowHour);
    scrollToHour(nowHour, true);
  }"""

PL_NEW_JUMP = """  }, []);"""

# ── DayPlanner: viewport-relative height ────────────────────────────────────
PL_OLD_BOX = """        className="relative max-h-[31rem] overflow-y-auto overflow-x-hidden rounded-xl border border-gray-200\""""

PL_NEW_BOX = """        className="relative max-h-[calc(100vh_-_21rem)] min-h-[17rem] overflow-y-auto overflow-x-hidden rounded-xl border border-gray-200\""""

# ── DayPlanner: per-row period + content flags ──────────────────────────────
PL_OLD_FLAGS = """          const offHours = h < dayStart || h > dayEnd;"""

PL_NEW_FLAGS = """          const offHours = h < dayStart || h > dayEnd;
          const period = PERIOD[periodOf(h)];
          const hasContent = entries.length > 0 || (block.meetings?.length ?? 0) > 0 || !!block.note;"""

PL_OLD_ROW = """              key={h}
              ref={(el) => { rowRefs.current[h] = el; }}
              className={'border-b border-gray-100 last:border-b-0 '
                + (isNow ? 'bg-[#F7FBFD]' : offHours ? 'bg-gray-50/70' : '')}
            >"""

PL_NEW_ROW = """              key={h}
              ref={(el) => { rowRefs.current[h] = el; }}
              style={{ borderLeft: `3px solid ${period.rail}` }}
              className={'border-b border-gray-100 last:border-b-0 '
                + (isNow ? 'bg-[#F7FBFD]' : hasContent ? period.tint : offHours ? 'bg-gray-50/70' : '')}
            >"""

PL_OLD_LABEL = """                <span className={'py-2.5 pr-2 text-right text-xs tabular-nums '
                  + (isNow ? 'font-medium text-brand-primary' : offHours ? 'text-gray-300' : 'text-gray-400')}>
                  {hh(h)}
                </span>"""

PL_NEW_LABEL = """                <span className="flex justify-end py-2 pr-2">
                  <span className={'rounded px-1.5 py-0.5 text-[11px] tabular-nums '
                    + (isNow ? 'bg-brand-primary font-medium text-white' : period.pill)}>
                    {hh(h)}
                  </span>
                </span>"""

# ── DayPlanner: strip the footer + now-dead helper ──────────────────────────
PL_OLD_TAIL = """      <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-gray-400">
        <span>
          Showing {hh(dayStart)}–{hh(dayEnd)} · scroll the timeline for earlier or later hours.
        </span>
        <button
          type="button"
          onClick={jumpToNow}
          className="shrink-0 rounded px-2 py-0.5 text-brand-primary transition-colors hover:bg-[#0082BB]/10"
        >
          Jump to now
        </button>
      </div>
      {!hasAnyContent(hourly) && (
        <p className="mt-1 text-center text-[11px] text-gray-400">
          Tap an hour to log what you accomplished. Your day index updates as you go.
        </p>
      )}
    </div>
  );
}

function hasAnyContent(hourly: HourlyMap): boolean {
  return Object.values(hourly).some(
    (b) => Object.keys(b.counts || {}).length > 0 || (b.meetings?.length ?? 0) > 0 || !!b.note,
  );
}"""

PL_NEW_TAIL = """    </div>
  );
}"""

# ── BranchLog: two-column Entry ─────────────────────────────────────────────
PAGE_OLD_ENTRY = """            {autoActs.length > 0 && (
              <div className="mb-4 rounded-md border border-gray-200 bg-gray-50 p-3">
                <div className="text-sm font-semibold text-gray-800">Tracked automatically today</div>
                <p className="mb-2 text-xs text-gray-400">Pulled from your pipeline actions — no need to key these.</p>
                <ol className="space-y-1">
                  {autoActs.map((a, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm">
                      <span className="tabular-nums text-gray-400">{a.time}</span>
                      <span className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-xs text-gray-600">{a.kind}</span>
                      <span className="text-gray-700">{a.detail}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            <DayPlanner
              fields={metricFields}
              hourly={hourly}
              onChange={(next) => { setDirty(true); setHourly(next); }}
              target={indexTarget}
              dateLabel={dateLabel}
            />

            <label className="mt-4 block text-sm">
              <span className="mb-1 block text-gray-700">Remarks / challenges (whole day)</span>
              <textarea rows={3} className="w-full rounded border px-2 py-1.5 text-sm"
                placeholder="Context your manager should know — blockers, escalations, anything the hours don't say."
                value={remarks} onChange={(e) => { setDirty(true); setRemarks(e.target.value); }} />
            </label>

            <div className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3">
              <div className="text-xs text-gray-400">
                {savingDraft
                  ? 'Saving…'
                  : dirty
                    ? 'Unsaved changes — autosaves every 30 seconds.'
                    : lastSaved
                      ? `All changes saved ${lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                      : 'Autosaves every 30 seconds.'}
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={() => void saveDraft()} disabled={busy || savingDraft}>
                  {savingDraft ? 'Saving…' : 'Save draft'}
                </Button>
                <Button onClick={() => void submit()} disabled={busy}>Submit daily log</Button>
              </div>
            </div>"""

PAGE_NEW_ENTRY = """            <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]">
              <DayPlanner
                fields={metricFields}
                hourly={hourly}
                onChange={(next) => { setDirty(true); setHourly(next); }}
                target={indexTarget}
                dateLabel={dateLabel}
              />

              {/* Context in, actions out. Keeps Save/Submit beside the timeline
                  rather than below it, so they stay above the fold. */}
              <aside className="flex flex-col gap-4">
                {autoActs.length > 0 && (
                  <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
                    <div className="text-sm font-semibold text-gray-800">Tracked automatically today</div>
                    <p className="mb-2 text-xs text-gray-400">Pulled from your pipeline actions — no need to key these.</p>
                    <ol className="max-h-40 space-y-1 overflow-y-auto">
                      {autoActs.map((a, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm">
                          <span className="tabular-nums text-gray-400">{a.time}</span>
                          <span className="rounded border border-gray-200 bg-white px-1.5 py-0.5 text-xs text-gray-600">{a.kind}</span>
                          <span className="text-gray-700">{a.detail}</span>
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                <label className="block text-sm">
                  <span className="mb-1 block text-gray-700">Remarks / challenges</span>
                  <textarea rows={4} className="w-full rounded border px-2 py-1.5 text-sm"
                    placeholder="Blockers, escalations, anything the hours don't say."
                    value={remarks} onChange={(e) => { setDirty(true); setRemarks(e.target.value); }} />
                </label>

                <div className="mt-auto border-t border-gray-100 pt-3">
                  <div className="mb-2 text-xs text-gray-400">
                    {savingDraft
                      ? 'Saving…'
                      : dirty
                        ? 'Unsaved changes — autosaves every 30 seconds.'
                        : lastSaved
                          ? `All changes saved ${lastSaved.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`
                          : 'Autosaves every 30 seconds.'}
                  </div>
                  <div className="flex flex-col gap-2">
                    <Button fullWidth onClick={() => void submit()} disabled={busy}>Submit daily log</Button>
                    <Button fullWidth variant="ghost" onClick={() => void saveDraft()} disabled={busy || savingDraft}>
                      {savingDraft ? 'Saving…' : 'Save draft'}
                    </Button>
                  </div>
                </div>
              </aside>
            </div>"""

EDITS = [
    (PLANNER, "period palette (rail / pill / tint)", PL_OLD_CHIPFN, PL_NEW_CHIPFN),
    (PLANNER, "scrollToHour — drop unused smooth arg", PL_OLD_SCROLLFN, PL_NEW_SCROLLFN),
    (PLANNER, "remove jumpToNow", PL_OLD_JUMP, PL_NEW_JUMP),
    (PLANNER, "timeline height follows viewport", PL_OLD_BOX, PL_NEW_BOX),
    (PLANNER, "per-row period + hasContent flags", PL_OLD_FLAGS, PL_NEW_FLAGS),
    (PLANNER, "row left rail + activity tint", PL_OLD_ROW, PL_NEW_ROW),
    (PLANNER, "hour label -> coloured time pill", PL_OLD_LABEL, PL_NEW_LABEL),
    (PLANNER, "strip footer hints + dead hasAnyContent", PL_OLD_TAIL, PL_NEW_TAIL),
    (PAGE, "Entry tab -> two-column with action sidebar", PAGE_OLD_ENTRY, PAGE_NEW_ENTRY),
]

REQUIRED_AFTER = {
    PLANNER: ["periodOf(", "period.rail", "period.tint", "period.pill",
              "calc(100vh_-_21rem)"],
    PAGE: ["<aside", "fullWidth", "lg:grid-cols-[minmax(0,1fr)_20rem]"],
}
FORBIDDEN_AFTER = {
    PLANNER: ["jumpToNow", "hasAnyContent", "Jump to now", "max-h-[31rem]",
              "Tap an hour to log"],
    PAGE: [],
}


def main():
    apply = "--apply" in sys.argv

    for path in (PAGE, PLANNER):
        if not os.path.isfile(path):
            print("ABORT: %s not found. Run from the project root." % path)
            return 1

    srcs = {}
    for path in (PAGE, PLANNER):
        with open(path, "r", encoding="utf-8") as fh:
            srcs[path] = fh.read()

    if "periodOf(" in srcs[PLANNER]:
        print("ABORT: DayPlanner already has periodOf — Phase 2c-c looks applied.")
        return 1
    if "dayStart = 8" not in srcs[PLANNER]:
        print("ABORT: DayPlanner has no dayStart. Apply Phase 2c-b first.")
        return 1

    for path, name, old, new in EDITS:
        n = srcs[path].count(old)
        if n != 1:
            print("ABORT: anchor '%s' matched %d times in %s (expected exactly 1)."
                  % (name, n, os.path.basename(path)))
            print("       Nothing written.")
            return 1
        srcs[path] = srcs[path].replace(old, new, 1)
        print("  ok  %s" % name)

    for path, tokens in REQUIRED_AFTER.items():
        for t in tokens:
            if t not in srcs[path]:
                print("ABORT: post-check — '%s' missing from %s." % (t, os.path.basename(path)))
                return 1
    for path, tokens in FORBIDDEN_AFTER.items():
        for t in tokens:
            if t in srcs[path]:
                print("ABORT: post-check — '%s' still present in %s."
                      % (t, os.path.basename(path)))
                return 1
    for path in (PAGE, PLANNER):
        for opener, closer in (("{", "}"), ("(", ")"), ("[", "]")):
            if srcs[path].count(opener) != srcs[path].count(closer):
                print("ABORT: unbalanced %s%s in %s (%d vs %d)."
                      % (opener, closer, os.path.basename(path),
                         srcs[path].count(opener), srcs[path].count(closer)))
                return 1

    print("\n%d/%d anchors matched across 2 files, post-checks clean." % (len(EDITS), len(EDITS)))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        return 0

    for path in (PAGE, PLANNER):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(srcs[path])
        print("APPLIED %s  (backup: %s)" % (path, os.path.basename(path) + BACKUP_SUFFIX))

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED_PROCEED_WITH_COMMIT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
