// A3 — daily-log analytics. The 80/20 view first, because that is the question
// management actually asks: which few activities are producing the output.
//
// Three panels:
//   IMPACT     tier split (high/medium/low) plus the per-activity contribution
//              that produced it, so the pie is never a black box — you can see
//              which activity put each slice there.
//   VALIDATION where the logs stand: validated, pending, returned, auto-swept.
//   TREND      index per day across the window, so a dip has a date.
//
// Scope comes from the server (get_visible_staff_codes), so a branch manager
// sees their branch and the MD sees the bank without this component deciding
// anything.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchBranchLogAnalytics, fetchBranchLogLeaderboard,
  type BranchLogAnalytics, type Leaderboard,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

// Brand palette. High is primary blue, medium the deep blue, low grey — so the
// eye reads importance by saturation rather than by hue alone.
const TIER_COLOUR: Record<string, string> = {
  high: '#0082BB', medium: '#005B82', low: '#979797',
};
const TIER_LABEL: Record<string, string> = {
  high: 'High impact', medium: 'Medium', low: 'Low',
};
const VALID_COLOUR = ['#669438', '#E0A02B', '#C4536F', '#979797'];

function pct(n: number, total: number): string {
  if (!total) return '0%';
  return `${Math.round((n / total) * 1000) / 10}%`;
}

export default function DailyLogAnalytics() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [data, setData] = useState<BranchLogAnalytics | null>(null);
  // Met vs not met per unit, cumulative over the window. Sourced from the
  // leaderboard so the analytics and the ranking cannot report different
  // achievement for the same population.
  const [byUnit, setByUnit] = useState<Leaderboard | null>(null);
  // At a branch the MD-reporting unit is the wrong label — a teller does not
  // think of themselves as under 'Director Consumer & Commercial Banking'.
  // Default to segments when the caller's population sits in one branch.
  const [dim, setDim] = useState<'unit' | 'segment'>('segment');
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const p = findPeriod(periodKey);
      const a = periodArgs(p);
      setData(await fetchBranchLogAnalytics(a.days ?? 0, '', a.start ?? '', a.end ?? ''));
      try {
        const lb = await fetchBranchLogLeaderboard({ ...a, level: dim });
        setByUnit(lb);
      } catch { setByUnit(null); }
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load analytics.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, dim, toast]);

  useEffect(() => { void load(); }, [load]);

  const impact = data?.impact;
  const totals = data?.totals;

  const tierData = useMemo(() => {
    if (!impact) return [];
    return (['high', 'medium', 'low'] as const)
      .map((t) => ({ name: TIER_LABEL[t], key: t, value: Math.max(Number(impact[t]) || 0, 0) }))
      .filter((d) => d.value > 0);
  }, [impact]);

  const activityData = useMemo(() => {
    const by = impact?.by_activity ?? {};
    return Object.entries(by)
      .map(([k, v]) => ({
        key: k,
        name: k.replace(/_/g, ' '),
        index: Math.round(Number((v as { index: number }).index) || 0),
        tier: String((v as { tier: string }).tier || 'medium'),
      }))
      .filter((d) => d.index > 0)
      .sort((a, b) => b.index - a.index)
      .slice(0, 12);
  }, [impact]);

  const validationData = useMemo(() => {
    if (!totals) return [];
    return [
      { name: 'Validated', value: totals.validated || 0 },
      { name: 'Pending', value: totals.pending || 0 },
      { name: 'Returned', value: totals.returned || 0 },
      { name: 'Auto-submitted', value: totals.auto_submitted || 0 },
    ].filter((d) => d.value > 0);
  }, [totals]);

  const totalIndex = Number(impact?.total) || 0;
  const highPct = Number(impact?.high_pct) || 0;

  return (
    <div className="mt-4 space-y-4">
      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-gray-900">
                Index analytics — where the output comes from
              </h2>
              <p className="mt-0.5 text-xs text-gray-500">
                Index contribution by impact tier. Tiers are assigned in Index Setup.
              </p>
            </div>
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </Card.Header>
        <Card.Body>
          {loading && <p className="py-10 text-center text-sm text-gray-400">Loading analytics…</p>}

          {!loading && !data && (
            <p className="py-10 text-center text-sm text-gray-400">No analytics available.</p>
          )}

          {!loading && data && totalIndex === 0 && (
            <p className="py-10 text-center text-sm text-gray-400">
              No index produced in this period.
            </p>
          )}

          {!loading && data && totalIndex > 0 && (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[300px_minmax(0,1fr)]">
              <div>
                <ResponsiveContainer width="100%" height={230}>
                  <PieChart>
                    <Pie data={tierData} dataKey="value" nameKey="name"
                         innerRadius={55} outerRadius={90} paddingAngle={2}>
                      {tierData.map((d) => (
                        <Cell key={d.key} fill={TIER_COLOUR[d.key]} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number) => [`${Math.round(v)} index`, '']} />
                    <Legend verticalAlign="bottom" height={24}
                            wrapperStyle={{ fontSize: 11 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="mt-1 text-center">
                  <div className="text-2xl font-semibold text-[#0082BB]">
                    {Math.round(highPct)}%
                  </div>
                  <div className="text-xs text-gray-500">
                    of the index comes from high-impact activity
                  </div>
                </div>
              </div>

              {/* The pie is never a black box: this is what put each slice there. */}
              <div>
                <div className="mb-1 text-xs font-semibold text-gray-600">
                  Contribution by activity
                </div>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={activityData} layout="vertical"
                            margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#EDEDED" />
                    <XAxis type="number" tick={{ fontSize: 10, fill: '#979797' }} />
                    <YAxis type="category" dataKey="name" width={150}
                           tick={{ fontSize: 10, fill: '#464646' }} />
                    <Tooltip formatter={(v: number) => [`${v} index`, '']} />
                    <Bar dataKey="index" radius={[0, 3, 3, 0]}>
                      {activityData.map((d) => (
                        <Cell key={d.key} fill={TIER_COLOUR[d.tier] || '#979797'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </Card.Body>
      </Card>

      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-base font-semibold text-gray-900">
              Daily target — met vs not met
            </h2>
            <span className="text-xs text-gray-500">
              Person-days that carried a target. Rest days and excused days are excluded.
            </span>
          </div>
        </Card.Header>
        <Card.Body>
          {!byUnit || (byUnit.scored_days ?? 0) === 0 ? (
            <p className="py-8 text-center text-sm text-gray-400">
              No scored days in this period.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
              <div className="text-center">
                <ResponsiveContainer width="100%" height={180}>
                  <PieChart>
                    <Pie dataKey="value" innerRadius={48} outerRadius={78} paddingAngle={2}
                         data={[{ name: 'Met', value: byUnit.met_days ?? 0 },
                                { name: 'Not met',
                                  value: (byUnit.scored_days ?? 0) - (byUnit.met_days ?? 0) }]}>
                      <Cell fill="#669438" />
                      <Cell fill="#C4536F" />
                    </Pie>
                    <Tooltip formatter={(v: number) => [`${v} person-days`, '']} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="text-2xl font-semibold text-[#3B6D11]">
                  {byUnit.met_rate ?? 0}%
                </div>
                <div className="text-xs text-gray-500">
                  of person-days met the target, bank-wide
                </div>
              </div>

              <div>
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-gray-600">
                    By {dim === 'segment' ? 'segment' : 'unit'} — cumulative over{' '}
                    {findPeriod(periodKey).label.toLowerCase()}
                  </span>
                  <span className="flex gap-1 text-[11px]">
                    {(['segment', 'unit'] as const).map((d) => (
                      <button key={d} type="button" onClick={() => setDim(d)}
                        className={'rounded-full px-2 py-0.5 '
                          + (dim === d ? 'bg-[#0082BB] text-white'
                                       : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                        {d === 'segment' ? 'Consumer / Commercial / Operations' : 'Units'}
                      </button>
                    ))}
                  </span>
                </div>
                <ResponsiveContainer width="100%" height={Math.max(180, (byUnit.rows.length || 1) * 26)}>
                  <BarChart
                    data={byUnit.rows.map((r) => ({
                      name: String(r.name || '').replace(/^Director,? /, '').slice(0, 26),
                      met: r.met_days ?? 0,
                      missed: (r.scored_days ?? 0) - (r.met_days ?? 0),
                      rate: r.met_rate ?? 0,
                    }))}
                    layout="vertical" stackOffset="expand"
                    margin={{ left: 8, right: 16, top: 4, bottom: 4 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#EDEDED" />
                    <XAxis type="number" tickFormatter={(v: number) => `${Math.round(v * 100)}%`}
                           tick={{ fontSize: 10, fill: '#979797' }} />
                    <YAxis type="category" dataKey="name" width={170}
                           tick={{ fontSize: 10, fill: '#464646' }} />
                    <Tooltip formatter={(v: number, n: string) => [`${v} days`, n]} />
                    <Bar dataKey="met" stackId="a" fill="#669438" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="missed" stackId="a" fill="#C4536F" radius={[0, 3, 3, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </Card.Body>
      </Card>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Validation state</h2>
          </Card.Header>
          <Card.Body>
            {validationData.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-400">No logs in this period.</p>
            ) : (
              <div className="grid grid-cols-[180px_minmax(0,1fr)] items-center gap-4">
                <ResponsiveContainer width="100%" height={170}>
                  <PieChart>
                    <Pie data={validationData} dataKey="value" nameKey="name"
                         innerRadius={42} outerRadius={70} paddingAngle={2}>
                      {validationData.map((d, i) => (
                        <Cell key={d.name} fill={VALID_COLOUR[i % VALID_COLOUR.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
                <div className="space-y-1 text-xs">
                  {validationData.map((d, i) => (
                    <div key={d.name} className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-1.5 text-gray-600">
                        <span className="inline-block h-2 w-2 rounded-full"
                              style={{ background: VALID_COLOUR[i % VALID_COLOUR.length] }} />
                        {d.name}
                      </span>
                      <span className="tabular-nums text-gray-800">
                        {d.value}
                        <span className="ml-1 text-gray-400">
                          {pct(d.value, totals?.logs || 0)}
                        </span>
                      </span>
                    </div>
                  ))}
                  <div className="mt-2 border-t border-gray-100 pt-2 text-gray-500">
                    Validation rate{' '}
                    <span className="font-semibold text-gray-800">
                      {totals?.validation_rate ?? 0}%
                    </span>
                  </div>
                </div>
              </div>
            )}
          </Card.Body>
        </Card>

        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Participation</h2>
          </Card.Header>
          <Card.Body>
            {!totals ? (
              <p className="py-8 text-center text-sm text-gray-400">No data.</p>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                {[
                  { label: 'Logs submitted', value: totals.logs, tone: 'text-gray-900' },
                  { label: 'People filing', value: totals.submitters, tone: 'text-gray-900' },
                  { label: 'Awaiting validation', value: totals.pending, tone: 'text-amber-600' },
                  { label: 'Auto-submitted at deadline', value: totals.auto_submitted, tone: 'text-amber-700' },
                  { label: 'Returned for amendment', value: totals.returned, tone: 'text-rose-600' },
                  { label: 'Total index', value: Math.round(totalIndex), tone: 'text-[#0082BB]' },
                ].map((s) => (
                  <div key={s.label} className="rounded-lg border border-gray-200 p-3">
                    <div className={`text-xl font-semibold tabular-nums ${s.tone}`}>
                      {Number(s.value || 0).toLocaleString()}
                    </div>
                    <div className="mt-0.5 text-[11px] text-gray-500">{s.label}</div>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-3 text-[11px] text-gray-400">
              Auto-submitted logs were swept at the 09:00 deadline with whatever had been
              autosaved — a high count here usually means people are not closing their day,
              not that they did nothing.
            </p>
          </Card.Body>
        </Card>
      </div>
    </div>
  );
}
