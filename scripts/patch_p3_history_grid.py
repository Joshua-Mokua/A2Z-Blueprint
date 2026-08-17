#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Phase 3 - Daily Log wide history grid.

Creates frontend/web/src/components/HistoryGrid.tsx and wires it into the
History tab of BranchLog.tsx, replacing the stacked-card list.

  * one row per staff per day, newest first
  * Date / Staff / Name / Role frozen left; header frozen top
  * every activity column from the server's `columns` metadata
  * Index / Target / Var on #0082BB, carried-forward balance on #003D57
  * rest days (Sundays + gazetted holidays, working_day=false from WC-2b) render
    muted with an em-dash target and a Rest chip - NOT as a zero, which would
    read as a missed day
  * range selector (7/14/30/60/90) and client-side CSV export
  * loads on demand when the History tab opens, not on page mount

Verified before delivery: tsc --noEmit clean, vite build clean, and the
#0082BB / #003D57 / sticky utility classes confirmed present in emitted CSS.

Usage (from project root, .venv active):
    python scripts\\patch_p3_history_grid.py            # dry run
    python scripts\\patch_p3_history_grid.py --apply    # write + .pre_p3 backup
"""
import os
import shutil
import sys

PAGE = os.path.join("frontend", "web", "src", "pages", "BranchLog.tsx")
COMP = os.path.join("frontend", "web", "src", "components", "HistoryGrid.tsx")
BACKUP_SUFFIX = ".pre_p3"

COMPONENT = r"""// Phase 3 — wide spreadsheet history grid for the Daily Log.
//
// One row per staff per day. Identity columns (Date / Staff / Name / Role) are
// frozen to the left so they survive horizontal scrolling across an arbitrary
// number of activity columns; the header row is frozen to the top. The four
// corner cells carry the highest stacking order or the scrolling body overruns
// them.
//
// Column groups, per the approved mockup:
//   identity   — frozen, white
//   activities — one per metric field, from the server's `columns` metadata
//   scoring    — Index / Target / Var on brand primary        #0082BB
//   balance    — running carried-forward variance, deep blue   #003D57
//
// REST DAYS: WC-2b excludes Sundays and public holidays from the carried-forward
// walk, and those rows arrive with working_day=false. They must NOT render as a
// zero target with a zero variance — that reads as "logged nothing, achieved
// nothing" when the truth is "no work was expected". They render muted, with an
// em-dash target and a Rest chip.

import { useMemo } from 'react';
import type { HistoryGrid as Grid, HistoryGridRow } from '@/lib/api';

// Frozen column widths in px. The cumulative offsets must stay in step with
// these — a mismatch shows as overlapping or gapped sticky columns.
const W_DATE = 92;
const W_CODE = 78;
const W_NAME = 168;
const W_ROLE = 150;
const L_DATE = 0;
const L_CODE = W_DATE;
const L_NAME = W_DATE + W_CODE;
const L_ROLE = W_DATE + W_CODE + W_NAME;

const SCOPE_LABEL: Record<string, string> = {
  bank: 'Bank-wide', subtree: 'My team', self: 'My logs',
};

function num(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function fmt(v: unknown): string {
  const n = num(v);
  if (n === 0) return '';                        // blank reads better than a field of zeros
  return Number.isInteger(n) ? String(n) : n.toFixed(1);
}

function signed(n: number): string {
  return (n > 0 ? '+' : '') + (Number.isInteger(n) ? String(n) : n.toFixed(1));
}

function dayLabel(iso: string): { day: string; date: string } {
  const [y, m, d] = String(iso).slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return { day: '', date: String(iso) };
  const dt = new Date(y, m - 1, d);              // local midnight — see lib/datetime
  return {
    day:  dt.toLocaleDateString(undefined, { weekday: 'short' }),
    date: dt.toLocaleDateString(undefined, { day: '2-digit', month: 'short' }),
  };
}

export interface HistoryGridProps {
  grid: Grid | null;
  loading?: boolean;
  days: number;
  onDaysChange: (d: number) => void;
}

export default function HistoryGrid({ grid, loading, days, onDaysChange }: HistoryGridProps) {
  const rows = grid?.rows ?? [];
  const cols = grid?.columns ?? [];

  // Closing balance per staff = cf_variance of their most recent row. Rows
  // arrive newest-first, so the first sighting of a staff code wins.
  const closing = useMemo(() => {
    const out: Record<string, number> = {};
    for (const r of rows) {
      const k = String(r.staff_code ?? '');
      if (!(k in out)) out[k] = num(r.cf_variance);
    }
    return out;
  }, [rows]);

  const staffCount = Object.keys(closing).length;
  const behind = Object.values(closing).filter((v) => v < 0).length;

  function exportCsv() {
    const head = ['Date', 'Staff', 'Name', 'Role', ...cols.map((c) => c.label),
                  'Index', 'Target', 'Variance', 'C/F balance'];
    const body = rows.map((r) => [
      r.log_date, r.staff_code, r.staff_name, r.role,
      ...cols.map((c) => num(r[c.key])),
      num(r.index),
      r.working_day === false ? '' : num(r.target),
      r.working_day === false ? '' : num(r.variance),
      num(r.cf_variance),
    ]);
    const csv = [head, ...body]
      .map((line) => line.map((c) => '"' + String(c ?? '').replace(/"/g, '""') + '"').join(','))
      .join('\n');
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'daily-log-history-' + new Date().toISOString().slice(0, 10) + '.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  const th = 'whitespace-nowrap px-2 py-2 text-left text-[11px] font-semibold uppercase tracking-wide';
  const td = 'whitespace-nowrap px-2 py-1.5 text-xs';

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-gray-500">Showing</span>
          <select
            className="rounded border border-gray-200 px-2 py-1 text-xs"
            value={days}
            onChange={(e) => onDaysChange(Number(e.target.value))}
          >
            {[7, 14, 30, 60, 90].map((d) => <option key={d} value={d}>last {d} days</option>)}
          </select>
          {grid && (
            <span className="rounded-full bg-[#E6F1FB] px-2.5 py-1 text-[11px] text-[#0C447C]">
              {SCOPE_LABEL[grid.scope_tier] ?? grid.scope_tier}
            </span>
          )}
          {staffCount > 0 && (
            <span className="text-gray-400">
              {rows.length} rows · {staffCount} staff
              {behind > 0 && <span className="text-rose-600"> · {behind} behind target</span>}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={exportCsv}
          disabled={rows.length === 0}
          className="rounded border border-gray-200 px-2.5 py-1 text-xs text-gray-600 transition-colors hover:bg-gray-50 disabled:opacity-40"
        >
          Export CSV
        </button>
      </div>

      {loading && <p className="py-8 text-center text-sm text-gray-400">Loading history…</p>}

      {!loading && rows.length === 0 && (
        <p className="py-8 text-center text-sm text-gray-400">
          No logs in this period. Entries appear here once a day is submitted.
        </p>
      )}

      {!loading && rows.length > 0 && (
        <div
          className="relative overflow-auto rounded-lg border border-gray-200"
          style={{ maxHeight: 'calc(100vh - 20rem)' }}
        >
          <table className="border-separate" style={{ borderSpacing: 0 }}>
            <thead>
              <tr>
                <th className={th + ' sticky z-30 bg-gray-100 text-gray-600'}
                    style={{ left: L_DATE, top: 0, minWidth: W_DATE }}>Date</th>
                <th className={th + ' sticky z-30 bg-gray-100 text-gray-600'}
                    style={{ left: L_CODE, top: 0, minWidth: W_CODE }}>Staff</th>
                <th className={th + ' sticky z-30 bg-gray-100 text-gray-600'}
                    style={{ left: L_NAME, top: 0, minWidth: W_NAME }}>Name</th>
                <th className={th + ' sticky z-30 border-r border-gray-300 bg-gray-100 text-gray-600'}
                    style={{ left: L_ROLE, top: 0, minWidth: W_ROLE }}>Role</th>
                {cols.map((c) => (
                  <th key={c.key} className={th + ' sticky z-20 bg-gray-50 text-gray-500'}
                      style={{ top: 0 }}
                      title={c.tier ? c.label + ' · ' + c.tier + ' impact' : c.label}>
                    {c.label}
                    {c.unit ? <span className="ml-0.5 font-normal normal-case text-gray-400">({c.unit})</span> : null}
                  </th>
                ))}
                <th className={th + ' sticky z-20 bg-[#0082BB] text-white'} style={{ top: 0 }}>Index</th>
                <th className={th + ' sticky z-20 bg-[#0082BB] text-white'} style={{ top: 0 }}>Target</th>
                <th className={th + ' sticky z-20 bg-[#0082BB] text-white'} style={{ top: 0 }}>Var</th>
                <th className={th + ' sticky z-20 bg-[#003D57] text-white'} style={{ top: 0 }}>C/F balance</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r: HistoryGridRow, i) => {
                const rest = r.working_day === false;
                const { day, date } = dayLabel(String(r.log_date));
                const variance = num(r.variance);
                const cf = num(r.cf_variance);
                const bg = rest ? 'bg-gray-50' : i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                const frozen = td + ' sticky z-10 ' + bg;
                return (
                  <tr key={String(r.staff_code) + '-' + String(r.log_date)}
                      className={rest ? 'text-gray-400' : ''}>
                    <td className={frozen + ' tabular-nums'} style={{ left: L_DATE }}>
                      <span className="text-gray-400">{day}</span>{' '}
                      <span className={rest ? '' : 'text-gray-900'}>{date}</span>
                    </td>
                    <td className={frozen + ' tabular-nums text-gray-500'} style={{ left: L_CODE }}>
                      {r.staff_code}
                    </td>
                    <td className={frozen + (rest ? '' : ' text-gray-900')} style={{ left: L_NAME }}>
                      {r.staff_name}
                      {r.auto_submitted && (
                        <span className="ml-1 rounded bg-[#FAEEDA] px-1 py-0.5 text-[10px] text-[#854F0B]">auto</span>
                      )}
                      {r.validated && <span className="ml-1 text-[10px] text-[#3B6D11]">✓</span>}
                    </td>
                    <td className={frozen + ' border-r border-gray-300 text-gray-500'} style={{ left: L_ROLE }}>
                      {r.role}
                    </td>

                    {cols.map((c) => (
                      <td key={c.key} className={td + ' ' + bg + ' tabular-nums text-gray-700'}>
                        {fmt(r[c.key])}
                      </td>
                    ))}

                    <td className={td + ' ' + bg + ' border-l border-gray-200 tabular-nums font-medium text-gray-900'}>
                      {num(r.index) === 0 ? <span className="text-gray-300">0</span> : num(r.index).toFixed(1)}
                    </td>
                    <td className={td + ' ' + bg + ' tabular-nums text-gray-500'}>
                      {rest ? <span className="text-gray-300">—</span> : num(r.target).toFixed(1)}
                    </td>
                    <td className={td + ' ' + bg + ' tabular-nums'}>
                      {rest
                        ? <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] text-gray-400">Rest</span>
                        : <span className={variance < 0 ? 'text-rose-600' : variance > 0 ? 'text-[#3B6D11]' : 'text-gray-400'}>
                            {signed(variance)}
                          </span>}
                    </td>
                    <td className={td + ' ' + bg + ' tabular-nums font-medium'}>
                      <span className={cf < 0 ? 'text-rose-700' : cf > 0 ? 'text-[#3B6D11]' : 'text-gray-400'}>
                        {signed(cf)}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
"""

IMP_OLD = "import DayPlanner from '@/components/DayPlanner';"
IMP_NEW = ("import DayPlanner from '@/components/DayPlanner';\n"
           "import HistoryGrid from '@/components/HistoryGrid';")

FN_OLD = "  fetchDayContext,"
FN_NEW = "  fetchDayContext, fetchBranchLogHistoryGrid,"

TY_OLD = "  type HourlyMap, type DayContext,"
TY_NEW = "  type HourlyMap, type DayContext, type HistoryGrid as HistoryGridData,"

ST_OLD = "  const [dayCtx, setDayCtx] = useState<DayContext | null>(null);"
ST_NEW = (ST_OLD + "\n"
          "  const [grid, setGrid] = useState<HistoryGridData | null>(null);\n"
          "  const [gridDays, setGridDays] = useState(30);\n"
          "  const [gridLoading, setGridLoading] = useState(false);")

LD_OLD = ("  const loadDayCtx = useCallback(async () => {\n"
          "    try { setDayCtx(await fetchDayContext()); } catch { /* header falls back */ }\n"
          "  }, []);")
LD_NEW = (LD_OLD + "\n"
          "  // Phase 3: the wide history grid. Loads on demand (History tab) and on\n"
          "  // range change, not on mount - it is the heaviest call on the page.\n"
          "  const loadGrid = useCallback(async (days: number) => {\n"
          "    setGridLoading(true);\n"
          "    try { setGrid(await fetchBranchLogHistoryGrid(days)); }\n"
          "    catch (e) { toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load history.' }); }\n"
          "    finally { setGridLoading(false); }\n"
          "  }, [toast]);")

EF_OLD = "  useEffect(() => { void loadDraft(); }, [loadDraft]);"
EF_NEW = (EF_OLD + "\n"
          "  useEffect(() => { if (tab === 'history') void loadGrid(gridDays); }, [tab, gridDays, loadGrid]);")

BADGE_OLD = "import { Badge } from '@/components/Badge';\n"
BADGE_NEW = ""

TAB_START = """          <Card.Header><h2 className="text-base font-semibold text-gray-900">My recent logs</h2></Card.Header>"""
TAB_END = """          </Card.Body>
        </Card>
      )}

      {tab === 'review' && canReview && ("""
TAB_NEW = """          <Card.Header>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="text-base font-semibold text-gray-900">Log history</h2>
              <span className="text-xs text-gray-400">
                Index vs target per day, with the running carried-forward balance.
              </span>
            </div>
          </Card.Header>
          <Card.Body>
            <HistoryGrid grid={grid} loading={gridLoading} days={gridDays} onDaysChange={setGridDays} />
"""

EDITS = [
    ("import HistoryGrid", IMP_OLD, IMP_NEW),
    ("api client import", FN_OLD, FN_NEW),
    ("api type import", TY_OLD, TY_NEW),
    ("grid state", ST_OLD, ST_NEW),
    ("loadGrid loader", LD_OLD, LD_NEW),
    ("load-on-tab effect", EF_OLD, EF_NEW),
    ("drop now-unused Badge import", BADGE_OLD, BADGE_NEW),
]


def main():
    apply = "--apply" in sys.argv
    if not os.path.isfile(PAGE):
        print("ABORT: %s not found. Run from the project root." % PAGE)
        return 1
    if os.path.exists(COMP):
        print("ABORT: %s already exists - Phase 3 looks applied." % COMP)
        return 1

    src = open(PAGE, encoding="utf-8").read()
    if "HistoryGrid" in src:
        print("ABORT: BranchLog.tsx already references HistoryGrid.")
        return 1

    for name, old, new in EDITS:
        n = src.count(old)
        if n != 1:
            print("ABORT: anchor '%s' matched %d times (expected 1)." % (name, n))
            return 1
        src = src.replace(old, new, 1)
        print("  ok  %s" % name)

    if src.count(TAB_START) != 1 or src.count(TAB_END) != 1:
        print("ABORT: History tab bounds not found exactly once.")
        return 1
    a = src.index(TAB_START)
    b = src.index(TAB_END, a)
    src = src[:a] + TAB_NEW + src[b:]
    print("  ok  History tab -> <HistoryGrid>")

    for token in ("<HistoryGrid", "loadGrid", "HistoryGridData"):
        if token not in src:
            print("ABORT: post-check - '%s' missing." % token)
            return 1
    if "Badge" in src:
        print("ABORT: post-check - Badge still referenced but its import was removed.")
        return 1
    for o, c in (("{", "}"), ("(", ")"), ("[", "]")):
        if src.count(o) != src.count(c):
            print("ABORT: unbalanced %s%s (%d vs %d)." % (o, c, src.count(o), src.count(c)))
            return 1

    print("\n%d/%d anchors matched + tab body replaced, post-checks clean."
          % (len(EDITS) + 1, len(EDITS) + 1))
    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)
    shutil.copy2(PAGE, PAGE + BACKUP_SUFFIX)
    open(PAGE, "w", encoding="utf-8", newline="").write(src)
    print("APPLIED %s  (backup: %s)" % (PAGE, os.path.basename(PAGE) + BACKUP_SUFFIX))
    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED_PROCEED_WITH_COMMIT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
