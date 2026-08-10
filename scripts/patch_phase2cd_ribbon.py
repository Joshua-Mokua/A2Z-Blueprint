#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 2c-d — fold the tabs into a sticky ribbon.

1. PageHeader.tsx : new opt-in `sticky` prop (sticky top-0 z-30). Strictly
                    opt-in — PageHeader is used on 22 pages and none of them
                    change behaviour unless they pass the prop.

2. BranchLog.tsx  : - drops the "Log your daily activity; supervisors validate."
                      subtitle; the ribbon now carries today's date instead.
                    - PageHeader moves OUT of the max-w wrapper so the ribbon is
                      full-bleed (it already has its own inner max-w container).
                    - the tab strip moves INTO the ribbon's actions slot, as
                      pill tabs with a per-tab accent colour and a colour dot
                      that stays visible when the tab is inactive.
                    - DayPlanner no longer receives dateLabel, so the date is
                      stated once (in the ribbon) rather than twice.

The ribbon has room to grow: anything added to `actions` sits beside the tabs,
and the left of the bar is free for a deadline countdown / day-index summary.

Usage (from project root, .venv active):
    python scripts\\patch_phase2cd_ribbon.py            # dry run
    python scripts\\patch_phase2cd_ribbon.py --apply    # write + .pre_phase2cd backups
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "BranchLog.tsx")
HEADER = os.path.join("frontend", "web", "src", "components", "PageHeader.tsx")
BACKUP_SUFFIX = ".pre_phase2cd"

# ── PageHeader: opt-in sticky ────────────────────────────────────────────────
HD_OLD_PROPS = """  /** Opt-in Ecobank-blue ribbon (matches the credit WorkbenchShell) for
   *  visual consistency across the app. Defaults to the white header. */
  ribbon?:      boolean;
}

export function PageHeader({ title, subtitle, breadcrumbs, actions, ribbon }: PageHeaderProps) {
  const navigate = useNavigate();
  const hasRow = Boolean(subtitle) || Boolean(actions);
  const headerCls = ribbon
    ? 'bg-gradient-to-r from-[#0082BB] to-[#005B82] shadow-sm'
    : 'bg-white border-b border-gray-200';"""

HD_NEW_PROPS = """  /** Opt-in Ecobank-blue ribbon (matches the credit WorkbenchShell) for
   *  visual consistency across the app. Defaults to the white header. */
  ribbon?:      boolean;
  /** Opt-in: pin the header to the top of the scrolling area (AppShell's <main>)
   *  so it stays put as the page scrolls. Off by default — every other page
   *  keeps its existing scroll-away behaviour. */
  sticky?:      boolean;
}

export function PageHeader({ title, subtitle, breadcrumbs, actions, ribbon, sticky }: PageHeaderProps) {
  const navigate = useNavigate();
  const hasRow = Boolean(subtitle) || Boolean(actions);
  const headerCls = (ribbon
    ? 'bg-gradient-to-r from-[#0082BB] to-[#005B82] shadow-sm'
    : 'bg-white border-b border-gray-200')
    + (sticky ? ' sticky top-0 z-30' : '');"""

# ── BranchLog: per-tab accent palette ───────────────────────────────────────
PG_OLD_TABTYPE = """type Tab = 'entry' | 'history' | 'review' | 'ranking' | 'setup';"""

PG_NEW_TABTYPE = """type Tab = 'entry' | 'history' | 'review' | 'ranking' | 'setup';

// Per-tab accent. `text` colours the label when the tab is active (white pill on
// the blue ribbon); `dot` keeps the colour legible while the tab is inactive.
const TAB_TONE: Record<Tab, { text: string; dot: string }> = {
  entry:   { text: 'text-[#0082BB]', dot: 'bg-[#0082BB]' },
  history: { text: 'text-[#005B82]', dot: 'bg-[#005B82]' },
  review:  { text: 'text-[#854F0B]', dot: 'bg-[#E0A02B]' },
  ranking: { text: 'text-[#3B6D11]', dot: 'bg-[#BED600]' },
  setup:   { text: 'text-[#464646]', dot: 'bg-[#979797]' },
};"""

# ── BranchLog: ribbon replaces header + loose tab strip ─────────────────────
PG_OLD_HEAD = """  return (
    <div className="mx-auto max-w-7xl px-4 py-6 2xl:max-w-[1680px]">
      <PageHeader ribbon title="Daily Log" subtitle="Log your daily activity; supervisors validate." />

      <div className="mb-4 flex gap-1 text-sm">
        {tabs.map(([id, lbl]) => (
          <button key={id} onClick={() => setTab(id)}
            className={`rounded px-3 py-1.5 font-medium transition-colors ${
              tab === id ? 'bg-[#0082BB] text-white' : 'text-[#005B82] hover:bg-[#0082BB]/10'}`}>
            {lbl}{id === 'review' && pending.length ? ` (${pending.length})` : ''}
          </button>
        ))}
      </div>
"""

PG_NEW_HEAD = """  return (
    <div>
      <PageHeader
        ribbon
        sticky
        title="Daily Log"
        subtitle={dateLabel}
        actions={
          <div className="flex flex-wrap items-center justify-end gap-1.5">
            {tabs.map(([id, lbl]) => (
              <button key={id} onClick={() => setTab(id)}
                className={'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors '
                  + (tab === id ? `bg-white shadow-sm ${TAB_TONE[id].text}` : 'text-white/80 hover:bg-white/15')}>
                <span className={'h-1.5 w-1.5 rounded-full ' + (tab === id ? TAB_TONE[id].dot : 'bg-white/50')} />
                {lbl}{id === 'review' && pending.length ? ` (${pending.length})` : ''}
              </button>
            ))}
          </div>
        }
      />

      <div className="mx-auto max-w-7xl px-4 py-6 2xl:max-w-[1680px]">
"""

# ── BranchLog: date stated once — drop it from the planner ──────────────────
PG_OLD_PLANNER = """                onChange={(next) => { setDirty(true); setHourly(next); }}
                target={indexTarget}
                dateLabel={dateLabel}
              />"""

PG_NEW_PLANNER = """                onChange={(next) => { setDirty(true); setHourly(next); }}
                target={indexTarget}
              />"""

# ── BranchLog: close the extra wrapper ──────────────────────────────────────
PG_OLD_TAIL = """          </Card.Body>
        </Card>
      )}
    </div>
  );
}"""

PG_NEW_TAIL = """          </Card.Body>
        </Card>
      )}
      </div>
    </div>
  );
}"""

EDITS = [
    (HEADER, "PageHeader — opt-in sticky prop", HD_OLD_PROPS, HD_NEW_PROPS),
    (PAGE, "per-tab accent palette", PG_OLD_TABTYPE, PG_NEW_TABTYPE),
    (PAGE, "sticky full-bleed ribbon with embedded tabs", PG_OLD_HEAD, PG_NEW_HEAD),
    (PAGE, "drop duplicate dateLabel from DayPlanner", PG_OLD_PLANNER, PG_NEW_PLANNER),
    (PAGE, "close the ribbon/content wrapper", PG_OLD_TAIL, PG_NEW_TAIL),
]

REQUIRED_AFTER = {
    HEADER: ["sticky?:", "sticky top-0 z-30", "ribbon, sticky }"],
    PAGE: ["TAB_TONE", "subtitle={dateLabel}", "actions={", "sticky"],
}
FORBIDDEN_AFTER = {
    HEADER: [],
    PAGE: ["supervisors validate", "dateLabel={dateLabel}"],
}


def main():
    apply = "--apply" in sys.argv

    for path in (PAGE, HEADER):
        if not os.path.isfile(path):
            print("ABORT: %s not found. Run from the project root." % path)
            return 1

    srcs = {}
    for path in (PAGE, HEADER):
        with open(path, "r", encoding="utf-8") as fh:
            srcs[path] = fh.read()

    if "TAB_TONE" in srcs[PAGE]:
        print("ABORT: BranchLog already has TAB_TONE — Phase 2c-d looks applied.")
        return 1
    if "periodOf(" not in open(
            os.path.join("frontend", "web", "src", "components", "DayPlanner.tsx"),
            "r", encoding="utf-8").read():
        print("ABORT: DayPlanner has no periodOf. Apply Phase 2c-c first.")
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
    for path in (PAGE, HEADER):
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

    for path in (PAGE, HEADER):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(srcs[path])
        print("APPLIED %s  (backup: %s)" % (path, os.path.basename(path) + BACKUP_SUFFIX))

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED_PROCEED_WITH_COMMIT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
