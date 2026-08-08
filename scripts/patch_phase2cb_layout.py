#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 2c-b — layout pass on the Daily Log.

1. BranchLog.tsx : max-w-5xl -> max-w-7xl 2xl:max-w-[1680px] (the convention
                   already used by CreditAnalytics / RolesAdmin). Phase 3's wide
                   history grid lands on this same page, so widen once, here.

2. DayPlanner.tsx: the 24-hour cycle no longer dominates. The timeline becomes a
                   scroll box parked on the working day (08:00-19:00 by default,
                   configurable via dayStart/dayEnd props). Off-hours are still
                   present and editable — one scroll away, visually de-emphasised.
                   Adds a "Jump to now" control and a 4-column editor grid on wide
                   screens now that there is room for it.

Usage (from project root, .venv active):
    python scripts\\patch_phase2cb_layout.py            # dry run
    python scripts\\patch_phase2cb_layout.py --apply    # write + .pre_phase2cb backups
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "BranchLog.tsx")
PLANNER = os.path.join("frontend", "web", "src", "components", "DayPlanner.tsx")
BACKUP_SUFFIX = ".pre_phase2cb"

# ── BranchLog.tsx ─────────────────────────────────────────────────────────────
PAGE_OLD_WIDTH = """    <div className="mx-auto max-w-5xl px-4 py-6">"""
PAGE_NEW_WIDTH = """    <div className="mx-auto max-w-7xl px-4 py-6 2xl:max-w-[1680px]">"""

# ── DayPlanner.tsx ────────────────────────────────────────────────────────────
PL_OLD_IMPORT = """import { useMemo, useState } from 'react';"""
PL_NEW_IMPORT = """import { useEffect, useMemo, useRef, useState } from 'react';"""

PL_OLD_PROPS = """export interface DayPlannerProps {
  fields: BranchLogField[];            // metric fields (type !== 'text')
  hourly: HourlyMap;                   // current hourly state
  onChange: (next: HourlyMap) => void; // called on any edit (parent autosaves)
  target?: number;                     // daily index target (0 = none)
  dateLabel?: string;                  // e.g. "Thursday 8 August"
  currentHour?: number;                // highlight (defaults to local hour)
  readOnly?: boolean;
}

export default function DayPlanner({
  fields, hourly, onChange, target = 0, dateLabel, currentHour, readOnly = false,
}: DayPlannerProps) {
  const nowHour = currentHour ?? new Date().getHours();
  const [openHour, setOpenHour] = useState<number | null>(nowHour);"""

PL_NEW_PROPS = """export interface DayPlannerProps {
  fields: BranchLogField[];            // metric fields (type !== 'text')
  hourly: HourlyMap;                   // current hourly state
  onChange: (next: HourlyMap) => void; // called on any edit (parent autosaves)
  target?: number;                     // daily index target (0 = none)
  dateLabel?: string;                  // e.g. "Thursday 8 August"
  currentHour?: number;                // highlight (defaults to local hour)
  readOnly?: boolean;
  dayStart?: number;                   // first prominent hour (default 08)
  dayEnd?: number;                     // last prominent hour, inclusive (default 19)
}

export default function DayPlanner({
  fields, hourly, onChange, target = 0, dateLabel, currentHour, readOnly = false,
  dayStart = 8, dayEnd = 19,
}: DayPlannerProps) {
  const nowHour = currentHour ?? new Date().getHours();
  const [openHour, setOpenHour] = useState<number | null>(nowHour);

  // All 24 hours stay mounted and editable; the box just starts parked on the
  // working day so the graveyard hours don't eat the page.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const rowRefs = useRef<Record<number, HTMLDivElement | null>>({});

  function scrollToHour(h: number, smooth = false) {
    const el = rowRefs.current[h];
    const box = scrollRef.current;
    if (!el || !box) return;
    if (smooth) box.scrollTo({ top: el.offsetTop, behavior: 'smooth' });
    else box.scrollTop = el.offsetTop;
  }

  // Mount only. Re-anchoring mid-edit would yank the view out from under the user.
  useEffect(() => {
    const outside = nowHour < dayStart || nowHour > dayEnd;
    scrollToHour(outside ? nowHour : dayStart);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function jumpToNow() {
    setOpenHour(nowHour);
    scrollToHour(nowHour, true);
  }"""

PL_OLD_CONTAINER = """      {/* 24-hour vertical timeline */}
      <div className="overflow-hidden rounded-xl border border-gray-200">
        {HOURS.map((h) => {
          const block = blockFor(h);
          const entries = Object.entries(block.counts || {});
          const isNow = h === nowHour;
          const isOpen = openHour === h;
          return (
            <div key={h} className={'border-b border-gray-100 last:border-b-0 ' + (isNow ? 'bg-[#F7FBFD]' : '')}>"""

PL_NEW_CONTAINER = """      {/* 24-hour vertical timeline, scrolled to the working day */}
      <div
        ref={scrollRef}
        className="relative max-h-[31rem] overflow-y-auto overflow-x-hidden rounded-xl border border-gray-200"
      >
        {HOURS.map((h) => {
          const block = blockFor(h);
          const entries = Object.entries(block.counts || {});
          const isNow = h === nowHour;
          const isOpen = openHour === h;
          const offHours = h < dayStart || h > dayEnd;
          return (
            <div
              key={h}
              ref={(el) => { rowRefs.current[h] = el; }}
              className={'border-b border-gray-100 last:border-b-0 '
                + (isNow ? 'bg-[#F7FBFD]' : offHours ? 'bg-gray-50/70' : '')}
            >"""

PL_OLD_HOURLABEL = """                <span className={'py-2.5 pr-2 text-right text-xs tabular-nums ' + (isNow ? 'font-medium text-brand-primary' : 'text-gray-400')}>
                  {hh(h)}
                </span>"""

PL_NEW_HOURLABEL = """                <span className={'py-2.5 pr-2 text-right text-xs tabular-nums '
                  + (isNow ? 'font-medium text-brand-primary' : offHours ? 'text-gray-300' : 'text-gray-400')}>
                  {hh(h)}
                </span>"""

PL_OLD_GRID = """                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">"""
PL_NEW_GRID = """                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">"""

PL_OLD_FOOTER = """      {!hasAnyContent(hourly) && (
        <p className="mt-2 text-center text-[11px] text-gray-400">
          Tap an hour to log what you accomplished. Your day index updates as you go.
        </p>
      )}"""

PL_NEW_FOOTER = """      <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-gray-400">
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
      )}"""

EDITS = [
    (PAGE, "page width -> max-w-7xl 2xl:max-w-[1680px]", PAGE_OLD_WIDTH, PAGE_NEW_WIDTH),
    (PLANNER, "react imports (useEffect + useRef)", PL_OLD_IMPORT, PL_NEW_IMPORT),
    (PLANNER, "dayStart/dayEnd props + scroll anchoring + jumpToNow", PL_OLD_PROPS, PL_NEW_PROPS),
    (PLANNER, "timeline -> scroll box, off-hour row tint", PL_OLD_CONTAINER, PL_NEW_CONTAINER),
    (PLANNER, "hour label muting for off-hours", PL_OLD_HOURLABEL, PL_NEW_HOURLABEL),
    (PLANNER, "editor grid -> 4 columns on xl", PL_OLD_GRID, PL_NEW_GRID),
    (PLANNER, "footer legend + Jump to now", PL_OLD_FOOTER, PL_NEW_FOOTER),
]

REQUIRED_AFTER = {
    PAGE: ["max-w-7xl"],
    PLANNER: ["dayStart = 8", "scrollToHour(", "rowRefs.current[h] = el", "Jump to now",
              "useRef", "useEffect"],
}
FORBIDDEN_AFTER = {
    PAGE: ["max-w-5xl"],
    PLANNER: ['className="overflow-hidden rounded-xl border border-gray-200"'],
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

    if "dayStart = 8" in srcs[PLANNER]:
        print("ABORT: DayPlanner already has dayStart — Phase 2c-b looks applied.")
        return 1
    if "import DayPlanner from '@/components/DayPlanner';" not in srcs[PAGE]:
        print("ABORT: BranchLog.tsx does not import DayPlanner. Apply Phase 2c first.")
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
