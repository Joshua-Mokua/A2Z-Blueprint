// A2 — cumulative ranking, drillable: unit → branch → role → individual.
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
