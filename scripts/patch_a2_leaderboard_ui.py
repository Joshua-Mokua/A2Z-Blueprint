#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
A2 - the cumulative ranking UI. Replaces the flat staff list on the Ranking tab.

WHAT YOU ASKED FOR: ranking from the individual up through branch and unit to
the MD, drillable like the daily log, plus ranking within a ROLE - tellers at a
branch in particular.

FOUR LEVELS, one click apart: Units / Branches / Roles / Individuals.

FILTERS COMPOSE DOWNWARD. Pick a unit and the branch list narrows to it; pick a
branch and the role list narrows to that branch. So "rank the tellers in Fortis"
is two clicks, and "rank branches inside CCB" is one.

ROLES RANK ON INDEX PER HEAD, not raw index - otherwise the largest role always
wins and the ranking says nothing except how many people hold a title.

THE PROPERTY THAT MAKES IT TRUSTWORTHY: every person is counted exactly ONCE at
every level, so switching lens never changes the bank total - only how it is
divided. If the totals moved when you changed the view, nobody could tell which
number was real. The footer states this on screen rather than leaving it as a
private assumption.

Per-staff totals come from carried_forward() server-side, the same read-time
engine the history grid uses, so the ranking cannot disagree with the history a
manager is looking at.

Bars are scaled against the top row and coloured by achievement against target,
so length reads as volume and colour reads as performance - a small unit hitting
target is green with a short bar, which is the honest picture.

Also removes the dead ranking state from BranchLog.tsx. The fetch survives
because it carries the daily index target the Day Planner header needs; only the
list it populated is gone.

Verified: tsc --noEmit clean, vite build clean.

Usage (from project root, .venv active):
    python scripts\\patch_a2_leaderboard_ui.py            # dry run
    python scripts\\patch_a2_leaderboard_ui.py --apply    # write + .pre_a2 backups
"""
import os
import shutil
import sys

COMP = os.path.join("frontend", "web", "src", "components", "Leaderboard.tsx")
APITS = os.path.join("frontend", "web", "src", "lib", "api.ts")
PAGE = os.path.join("frontend", "web", "src", "pages", "BranchLog.tsx")
BACKUP_SUFFIX = ".pre_a2"

TS_ANCHOR = "export async function fetchBranchLogRanking("

IMPORT_OLD = "import HistoryGrid from '@/components/HistoryGrid';"
IMPORT_NEW = ("import HistoryGrid from '@/components/HistoryGrid';\n"
              "import Leaderboard from '@/components/Leaderboard';")

STATE_OLD = "  const [ranking, setRanking] = useState<BranchLogRankRow[]>([]);\n"

LOAD_OLD = ("    try { const r = await fetchBranchLogRanking(30); setRanking(r.ranking); "
            "setIndexTarget(r.daily_index_target || 0); } catch { /* ignore */ }")
LOAD_NEW = ("    // The Leaderboard component owns the ranking now; this call survives only to\n"
            "    // pick up the daily index target, which the Day Planner header needs.\n"
            "    try { const r = await fetchBranchLogRanking(30); "
            "setIndexTarget(r.daily_index_target || 0); } catch { /* ignore */ }")

TYPE_OLD = ("  type BranchLogField, type BranchLogEntry, type BranchLogActivity, "
            "type BranchLogRankRow, type ExtraActivity,")
TYPE_NEW = ("  type BranchLogField, type BranchLogEntry, type BranchLogActivity, "
            "type ExtraActivity,")

TAB_START = "      {tab === 'ranking' && ("
TAB_END = "      {tab === 'setup' && isAdmin && ("
TAB_NEW = "      {tab === 'ranking' && <Leaderboard />}\n\n"

TS_NEW = r'''// ── Cumulative leaderboard (staff / role / branch / unit) ─────────────────
export interface LeaderboardRow {
  rank?: number;
  name?: string;                       // role / branch / unit rows
  staff_code?: string; staff_name?: string; role?: string; branch?: string; unit?: string;
  index: number; target: number; achievement?: number;
  headcount?: number; index_per_head?: number;
  days_filed: number; validated: number; cf_variance?: number;
}
export interface Leaderboard {
  level: string; days: number; rows: LeaderboardRow[];
  total_index: number; total_headcount: number;
  filters: { role: string; branch: string; unit: string };
  roles: string[]; branches: string[]; units: string[];
}
export async function fetchBranchLogLeaderboard(opts: {
  days?: number; level?: string; role?: string; branch?: string; unit?: string;
} = {}): Promise<Leaderboard> {
  const q = new URLSearchParams();
  if (opts.days) q.set('days', String(opts.days));
  if (opts.level) q.set('level', opts.level);
  if (opts.role) q.set('role', opts.role);
  if (opts.branch) q.set('branch', opts.branch);
  if (opts.unit) q.set('unit', opts.unit);
  const s = q.toString();
  return getJson<Leaderboard>(`/branch-log/leaderboard${s ? `?${s}` : ''}`);
}

'''

COMPONENT = r'''// A2 — cumulative ranking, drillable: unit → branch → role → individual.
//
// Every person is counted exactly once at each level, so switching level never
// changes the bank total — only how it is partitioned. That is the property
// that makes a leaderboard trustworthy: if the totals moved when you changed
// the lens, nobody could tell which number was real.
//
// Filters compose downward. Pick a unit and the branch list narrows to that
// unit; pick a branch and the role list narrows to that branch. So "rank the
// tellers in Fortis" is two clicks, and "rank branches inside CCB" is one.
//
// Per-staff totals come from carried_forward() server-side — the same engine
// the history grid uses — so this can never disagree with the history.

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import { fetchBranchLogLeaderboard, type Leaderboard, type LeaderboardRow } from '@/lib/api';

type Level = 'unit' | 'branch' | 'role' | 'staff';

const LEVELS: { key: Level; label: string; hint: string }[] = [
  { key: 'unit',   label: 'Units',       hint: 'Everything beneath each MD-reporting unit' },
  { key: 'branch', label: 'Branches',    hint: 'The 16 branches and Head Office' },
  { key: 'role',   label: 'Roles',       hint: 'Ranked by index per head, so a big role cannot win on size' },
  { key: 'staff',  label: 'Individuals', hint: 'Every person you can see' },
];

// Medal tint for the top three, brand palette only.
const MEDAL = ['bg-[#BED600] text-[#3B6D11]', 'bg-[#E6F1FB] text-[#0C447C]', 'bg-[#FAEEDA] text-[#854F0B]'];

function bar(pct: number): string {
  if (pct >= 100) return 'bg-[#669438]';
  if (pct >= 75) return 'bg-[#BED600]';
  if (pct >= 50) return 'bg-[#E0A02B]';
  return 'bg-[#C4536F]';
}

export default function Leaderboard() {
  const { toast } = useToast();
  const [level, setLevel] = useState<Level>('branch');
  const [days, setDays] = useState(30);
  const [unit, setUnit] = useState('');
  const [branch, setBranch] = useState('');
  const [role, setRole] = useState('');
  const [data, setData] = useState<Leaderboard | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await fetchBranchLogLeaderboard({ days, level, unit, branch, role }));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the ranking.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [days, level, unit, branch, role, toast]);

  useEffect(() => { void load(); }, [load]);

  const rows = data?.rows ?? [];
  const max = useMemo(
    () => Math.max(1, ...rows.map((r) => Number(r.index) || 0)), [rows]);

  const isStaff = level === 'staff';
  const nameOf = (r: LeaderboardRow) =>
    isStaff ? String(r.staff_name || r.staff_code || '') : String(r.name || '');

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Cumulative ranking</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              {LEVELS.find((l) => l.key === level)?.hint}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {LEVELS.map((l) => (
              <button key={l.key} type="button" onClick={() => setLevel(l.key)}
                className={'rounded-full px-3 py-1 font-medium transition-colors '
                  + (level === l.key ? 'bg-[#0082BB] text-white'
                                     : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                {l.label}
              </button>
            ))}
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}
                    className="ml-2 rounded border border-gray-200 px-2 py-1 text-xs">
              {[7, 14, 30, 60, 90].map((d) => <option key={d} value={d}>last {d} days</option>)}
            </select>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {/* Filters compose downward: unit narrows branches, branch narrows roles. */}
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <select value={unit} onChange={(e) => { setUnit(e.target.value); setBranch(''); setRole(''); }}
                  className="max-w-[240px] rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="">All units</option>
            {(data?.units ?? []).map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
          <select value={branch} onChange={(e) => { setBranch(e.target.value); setRole(''); }}
                  className="max-w-[180px] rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="">All branches</option>
            {(data?.branches ?? []).map((b) => <option key={b} value={b}>{b}</option>)}
          </select>
          <select value={role} onChange={(e) => setRole(e.target.value)}
                  className="max-w-[240px] rounded border border-gray-200 px-2 py-1 text-xs">
            <option value="">All roles</option>
            {(data?.roles ?? []).map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          {(unit || branch || role) && (
            <button type="button"
                    onClick={() => { setUnit(''); setBranch(''); setRole(''); }}
                    className="rounded px-1.5 py-0.5 text-[11px] text-brand-primary hover:bg-[#0082BB]/10">
              Clear
            </button>
          )}
          {data && (
            <span className="ml-auto text-gray-500">
              {data.total_headcount} staff · total index{' '}
              <span className="font-semibold text-gray-800">{data.total_index.toLocaleString()}</span>
            </span>
          )}
        </div>

        {loading && <p className="py-8 text-center text-sm text-gray-400">Ranking…</p>}

        {!loading && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            Nothing to rank for this period and filter.
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full border-separate" style={{ borderSpacing: 0 }}>
              <thead>
                <tr>
                  <th className="w-10 bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">#</th>
                  <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">
                    {isStaff ? 'Staff' : LEVELS.find((l) => l.key === level)?.label}
                  </th>
                  {isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Role</th>
                  )}
                  {isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Branch</th>
                  )}
                  {!isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Staff</th>
                  )}
                  <th className="bg-[#0082BB] px-2 py-2 text-right text-[11px] font-semibold uppercase text-white">Index</th>
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Target</th>
                  <th className="bg-gray-100 px-2 py-2 text-left text-[11px] font-semibold uppercase text-gray-600">Achievement</th>
                  {!isStaff && (
                    <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Per head</th>
                  )}
                  <th className="bg-gray-100 px-2 py-2 text-right text-[11px] font-semibold uppercase text-gray-600">Filed</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const pct = Number(r.achievement) || 0;
                  const idx = Number(r.index) || 0;
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  return (
                    <tr key={String(r.staff_code || r.name || i)}>
                      <td className={`${bg} px-2 py-1.5 text-xs`}>
                        <span className={'inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold '
                          + (r.rank && r.rank <= 3 ? MEDAL[r.rank - 1] : 'text-gray-400')}>
                          {r.rank}
                        </span>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-xs font-medium text-gray-900`}>
                        {nameOf(r)}
                      </td>
                      {isStaff && <td className={`${bg} px-2 py-1.5 text-xs text-gray-500`}>{r.role}</td>}
                      {isStaff && <td className={`${bg} px-2 py-1.5 text-xs text-gray-500`}>{r.branch}</td>}
                      {!isStaff && (
                        <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                          {r.headcount}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs font-semibold tabular-nums text-gray-900`}>
                        {idx.toLocaleString()}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                        {(Number(r.target) || 0).toLocaleString()}
                      </td>
                      <td className={`${bg} px-2 py-1.5`}>
                        <div className="flex items-center gap-2">
                          <div className="h-2 w-24 overflow-hidden rounded-full bg-gray-100">
                            <div className={`h-full ${bar(pct)}`}
                                 style={{ width: `${Math.min(Math.max(idx / max, 0), 1) * 100}%` }} />
                          </div>
                          <span className={'text-[11px] tabular-nums '
                            + (pct >= 100 ? 'text-[#3B6D11]' : pct >= 50 ? 'text-gray-600' : 'text-rose-600')}>
                            {pct}%
                          </span>
                        </div>
                      </td>
                      {!isStaff && (
                        <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-700`}>
                          {r.index_per_head}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-500`}>
                        {r.days_filed}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <p className="mt-2 text-[11px] text-gray-400">
          Each person is counted once at every level, so the total index does not change
          when you switch lens — only how it is divided. Roles rank on index per head so a
          large role cannot win on size alone.
        </p>
      </Card.Body>
    </Card>
  );
}
'''


def main():
    apply = "--apply" in sys.argv
    for p in (APITS, PAGE):
        if not os.path.isfile(p):
            print("ABORT: %s not found. Run from the project root." % p)
            return 1
    if os.path.exists(COMP):
        print("ABORT: %s already exists - A2 looks applied." % COMP)
        return 1

    ts = open(APITS, encoding="utf-8").read()
    page = open(PAGE, encoding="utf-8").read()

    if "fetchBranchLogLeaderboard" in ts:
        print("ABORT: api.ts already has the leaderboard client.")
        return 1
    for label, hay, mark in (("api.ts anchor", ts, TS_ANCHOR),
                             ("import", page, IMPORT_OLD),
                             ("ranking state", page, STATE_OLD),
                             ("loadRanking", page, LOAD_OLD),
                             ("type import", page, TYPE_OLD),
                             ("tab start", page, TAB_START),
                             ("tab end", page, TAB_END)):
        if hay.count(mark) != 1:
            print("ABORT: %s matched %d times (expected 1)." % (label, hay.count(mark)))
            return 1

    ts = ts.replace(TS_ANCHOR, TS_NEW + TS_ANCHOR, 1)
    print("  ok  api.ts - Leaderboard types + fetchBranchLogLeaderboard")

    page = page.replace(IMPORT_OLD, IMPORT_NEW, 1)
    page = page.replace(STATE_OLD, "", 1)
    page = page.replace(LOAD_OLD, LOAD_NEW, 1)
    page = page.replace(TYPE_OLD, TYPE_NEW, 1)
    a = page.index(TAB_START)
    b = page.index(TAB_END, a)
    page = page[:a] + TAB_NEW + page[b:]
    print("  ok  BranchLog - Ranking tab replaced, dead state removed")

    if "BranchLogRankRow" in page:
        print("ABORT: post-check - the dead rank type is still referenced.")
        return 1
    if "setRanking" in page:
        print("ABORT: post-check - dead ranking state survived.")
        return 1
    if "setIndexTarget" not in page:
        print("ABORT: post-check - the index target fetch was lost.")
        return 1
    if "fetchBranchLogHistoryGrid" not in ts:
        print("ABORT: post-check - api.ts lost fetchBranchLogHistoryGrid.")
        return 1
    for o, c in (("{", "}"), ("(", ")")):
        if COMPONENT.count(o) != COMPONENT.count(c):
            print("ABORT: embedded component unbalanced %s%s." % (o, c))
            return 1
    print("  ok  post-checks clean")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    open(COMP, "w", encoding="utf-8", newline="").write(COMPONENT)
    print("CREATED %s" % COMP)
    for path, content in ((APITS, ts), (PAGE, page)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    print("\nNext: pushd frontend\\web && pnpm tsc --noEmit && popd && echo TSC_PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
