// PipelineLeaderboard — pipeline ranking in two levels: referral and direct.
//
// A deal's value counts once, for whoever owns it. Under "Referred" the same
// deals are attributed to the REFERRER instead, so a referred deal is never
// counted twice as though the bank booked it twice — the two views answer
// different questions about the same book.

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineLeaderboard, type PipelineLeaderboard as Board,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

type Level = 'unit' | 'branch' | 'role' | 'staff';
type Origin = 'all' | 'direct' | 'referred';

const LEVELS: { key: Level; label: string }[] = [
  { key: 'unit', label: 'Units' },
  { key: 'branch', label: 'Branches' },
  { key: 'role', label: 'Roles' },
  { key: 'staff', label: 'Individuals' },
];

const ORIGINS: { key: Origin; label: string }[] = [
  { key: 'all', label: 'All deals' },
  { key: 'direct', label: 'Direct' },
  { key: 'referred', label: 'Referred' },
];

const MEDAL = ['bg-[#BED600] text-[#3B6D11]', 'bg-[#E6F1FB] text-[#0C447C]', 'bg-[#FAEEDA] text-[#854F0B]'];

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export default function PipelineLeaderboard() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [level, setLevel] = useState<Level>('branch');
  const [origin, setOrigin] = useState<Origin>('all');
  const [data, setData] = useState<Board | null>(null);
  const [loading, setLoading] = useState(false);
  // Drill: clicking a unit / branch / role opens the INDIVIDUALS INSIDE IT,
  // ranked against each other. Ruling 2026-08-09: an individual is ranked
  // within their unit, not against the whole bank — a teller in Fortis and an
  // RM in Corporate are not competing, and a flat bank-wide list of 363 people
  // says nothing a manager can act on. The consolidated view stays available
  // to the MD's office through the tree itself.
  const [openRow, setOpenRow] = useState('');
  const [drill, setDrill] = useState<Board['rows'] | null>(null);
  const [drillLoading, setDrillLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      setData(await fetchPipelineLeaderboard({ ...a, level, origin }));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the pipeline ranking.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, level, origin, toast]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setOpenRow(''); setDrill(null); }, [level, origin, periodKey]);

  async function expand(key: string) {
    if (openRow === key) { setOpenRow(''); setDrill(null); return; }
    setOpenRow(key);
    setDrill(null);
    setDrillLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      // Narrow by whichever dimension this row is, then ask for the people.
      const extra = level === 'unit' ? { unit: key }
        : level === 'branch' ? { branch: key }
        : {};
      const r = await fetchPipelineLeaderboard({
        ...a, level: 'staff', origin, ...extra,
      });
      setDrill(r.rows);
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not open that row.' });
      setOpenRow('');
    } finally {
      setDrillLoading(false);
    }
  }

  const rows = data?.rows ?? [];
  const isStaff = level === 'staff';
  const max = Math.max(1, ...rows.map((r) => r.value));

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-gray-900">Pipeline ranking</h2>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            {LEVELS.map((l) => (
              <button key={l.key} type="button" onClick={() => setLevel(l.key)}
                className={'rounded-full px-3 py-1 font-medium '
                  + (level === l.key ? 'bg-[#0082BB] text-white'
                                     : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                {l.label}
              </button>
            ))}
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="ml-2 rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <span className="inline-flex overflow-hidden rounded-lg border border-gray-200">
            {ORIGINS.map((o) => (
              <button key={o.key} type="button" onClick={() => setOrigin(o.key)}
                className={'px-3 py-1 font-medium '
                  + (origin === o.key ? 'bg-[#005B82] text-white'
                                      : 'bg-white text-gray-600 hover:bg-gray-50')}>
                {o.label}
              </button>
            ))}
          </span>
          {origin === 'referred' && (
            <span className="text-[11px] text-gray-500">credited to the referrer</span>
          )}
          {data && (
            <span className="ml-auto text-gray-500">
              {data.total_deals} deals · KES{' '}
              <span className="font-semibold text-gray-800">{kes(data.total_value)}</span>
              {' · '}KES {kes(data.total_weighted)} weighted
            </span>
          )}
        </div>

        {loading && <p className="py-8 text-center text-sm text-gray-400">Ranking…</p>}

        {!loading && rows.length === 0 && (
          <p className="py-8 text-center text-sm text-gray-400">
            {origin === 'referred'
              ? 'No accepted referrals in this period.'
              : 'Nothing to rank for this period.'}
          </p>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-auto rounded-lg border border-gray-200">
            <table className="w-full table-fixed border-separate" style={{ borderSpacing: 0 }}>
              <colgroup>
                <col style={{ width: 44 }} />
                <col />
                {isStaff && <col style={{ width: '20%' }} />}
                {isStaff && <col style={{ width: '14%' }} />}
                <col style={{ width: 70 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 130 }} />
                <col style={{ width: 150 }} />
                <col style={{ width: 70 }} />
              </colgroup>
              <thead>
                <tr>
                  {['#', isStaff ? 'Staff' : LEVELS.find((l) => l.key === level)?.label,
                    ...(isStaff ? ['Role', 'Branch'] : []),
                    'Deals', 'Value (KES)', 'Weighted (KES)', 'Share', 'Win %'].map((h, i) => (
                    <th key={i}
                        className={'px-2 py-2 text-[11px] font-semibold uppercase '
                          + (i >= 4 ? 'text-right ' : 'text-left ')
                          + (h === 'Value (KES)' ? 'bg-[#0082BB] text-white' : 'bg-gray-100 text-gray-600')}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => {
                  const bg = i % 2 === 1 ? 'bg-gray-50/40' : 'bg-white';
                  const expanded = !isStaff && openRow === r.key;
                  return (
                    <>
                    <tr key={r.key}>
                      <td className={`${bg} px-2 py-1.5 text-xs`}>
                        <span className={'inline-flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-semibold '
                          + (r.rank <= 3 ? MEDAL[r.rank - 1] : 'text-gray-400')}>
                          {r.rank}
                        </span>
                      </td>
                      <td className={`${bg} truncate px-2 py-1.5 text-xs font-medium text-gray-900`}
                          title={r.name}>
                        {isStaff ? r.name : (
                          <button type="button" onClick={() => void expand(r.key)}
                                  className="flex items-center gap-1.5 text-left hover:text-brand-primary">
                            <span className="text-gray-400">{openRow === r.key ? '▾' : '▸'}</span>
                            {r.name}
                          </button>
                        )}
                      </td>
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.role}>
                          {r.role}
                        </td>
                      )}
                      {isStaff && (
                        <td className={`${bg} truncate px-2 py-1.5 text-xs text-gray-500`} title={r.branch}>
                          {r.branch}
                        </td>
                      )}
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-700`}>
                        {r.deals}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs font-semibold tabular-nums text-gray-900`}>
                        {kes(r.value)}
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums text-gray-600`}>
                        {kes(r.weighted)}
                      </td>
                      <td className={`${bg} px-2 py-1.5`}>
                        <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
                          <div className="h-full rounded-full bg-[#0082BB]"
                               style={{ width: `${(r.value / max) * 100}%` }} />
                        </div>
                      </td>
                      <td className={`${bg} px-2 py-1.5 text-right text-xs tabular-nums`}>
                        <span className={r.win_rate >= 50 ? 'text-[#3B6D11]' : 'text-gray-500'}>
                          {r.win_rate}%
                        </span>
                      </td>
                    </tr>
                    {expanded && (
                      <tr key={`${r.key}-drill`}>
                        <td colSpan={9} className="bg-[#F7FBFD] px-6 py-3">
                          {drillLoading && (
                            <p className="text-xs text-gray-400">Opening {r.key}…</p>
                          )}
                          {!drillLoading && drill && drill.length === 0 && (
                            <p className="text-xs text-gray-400">Nobody to show here.</p>
                          )}
                          {!drillLoading && drill && drill.length > 0 && (
                            <table className="w-full">
                              <thead>
                                <tr className="border-b border-gray-200">
                                  {['#', 'Staff', 'Name', 'Role', 'Deals',
                                    'Value (KES)', 'Weighted (KES)', 'Win %'].map((h, k) => (
                                    <th key={k}
                                        className={'py-1 pr-3 text-[10px] font-semibold uppercase tracking-wide text-gray-500 '
                                          + (k >= 4 ? 'text-right' : 'text-left')}>
                                      {h}
                                    </th>
                                  ))}
                                </tr>
                              </thead>
                              <tbody>
                                {drill.slice(0, 40).map((m) => (
                                  <tr key={m.key} className="border-b border-gray-100 last:border-0">
                                    <td className="w-8 py-1 pr-2 text-[11px] tabular-nums text-gray-400">{m.rank}</td>
                                    <td className="py-1 pr-3 text-xs tabular-nums text-gray-500" style={{ width: 80 }}>
                                      {m.staff_code}
                                    </td>
                                    <td className="py-1 pr-3 text-xs text-gray-800">{m.name}</td>
                                    <td className="truncate py-1 pr-3 text-xs text-gray-500" title={m.role}>
                                      {m.role}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-700" style={{ width: 60 }}>
                                      {m.deals}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs font-semibold tabular-nums text-gray-900" style={{ width: 120 }}>
                                      {kes(m.value)}
                                    </td>
                                    <td className="py-1 pr-3 text-right text-xs tabular-nums text-gray-600" style={{ width: 120 }}>
                                      {kes(m.weighted)}
                                    </td>
                                    <td className="py-1 text-right text-xs tabular-nums" style={{ width: 60 }}>
                                      <span className={m.win_rate >= 50 ? 'text-[#3B6D11]' : 'text-gray-500'}>
                                        {m.win_rate}%
                                      </span>
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                          {!drillLoading && (drill?.length ?? 0) > 40 && (
                            <p className="mt-1 text-[11px] text-gray-400">
                              showing the top 40 of {drill?.length}
                            </p>
                          )}
                        </td>
                      </tr>
                    )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
