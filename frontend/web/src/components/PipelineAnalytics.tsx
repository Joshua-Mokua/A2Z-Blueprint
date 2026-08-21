// PipelineAnalytics — the pipeline counterpart to the index analytics.
//
// Same period model, same scope read, so the two pages cannot disagree about
// the same population. Three questions, in the order management asks them:
//
//   Where is the money        open / weighted / won, and the win rate
//   Where does it stall       conversion through the journey, RAG per bucket
//   Where does it come from   referred versus direct

import { useCallback, useEffect, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import {
  fetchPipelineAnalyticsSummary, type PipelineAnalyticsSummary,
} from '@/lib/api';
import { periods, findPeriod, periodArgs, DEFAULT_PERIOD_KEY } from '@/lib/period';

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

// One colour per origin, in configured order - seven now, more later.
const ORIGIN_COLOURS = ['#0082BB', '#669438', '#E0A02B', '#9455B0',
                        '#C4536F', '#005B82', '#979797', '#3F6FC4'];

const RAG: Record<string, string> = {
  green: '#669438', amber: '#E0A02B', red: '#C4536F', idle: '#D8DBDF',
};

export default function PipelineAnalytics() {
  const { toast } = useToast();
  const [periodKey, setPeriodKey] = useState(DEFAULT_PERIOD_KEY);
  const [data, setData] = useState<PipelineAnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const a = periodArgs(findPeriod(periodKey));
      setData(await fetchPipelineAnalyticsSummary(a.days ?? 0, a.start ?? '', a.end ?? ''));
    } catch (e) {
      toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load pipeline analytics.' });
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [periodKey, toast]);

  useEffect(() => { void load(); }, [load]);

  const t = data?.totals;
  const originTotal = (data?.origin ?? []).reduce((a, o) => a + o.count, 0);

  return (
    <div className="space-y-4">
      <Card>
        <Card.Header>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-base font-semibold text-gray-900">Pipeline analytics</h2>
            <select value={periodKey} onChange={(e) => setPeriodKey(e.target.value)}
                    className="rounded border border-gray-200 px-2 py-1 text-xs">
              {periods().map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </div>
        </Card.Header>
        <Card.Body>
          {loading && <p className="py-8 text-center text-sm text-gray-400">Loading…</p>}

          {!loading && !t && (
            <p className="py-8 text-center text-sm text-gray-400">No pipeline data for this period.</p>
          )}

          {!loading && t && (
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[
                { label: 'Open deals', value: t.open.toLocaleString(), tone: 'text-gray-900' },
                { label: 'Open value (KES)', value: kes(t.open_value), tone: 'text-[#0082BB]' },
                { label: 'Weighted (KES)', value: kes(t.weighted), tone: 'text-[#005B82]' },
                { label: 'Won (KES)', value: kes(t.won_value), tone: 'text-[#3B6D11]' },
                { label: 'Won', value: t.won.toLocaleString(), tone: 'text-[#3B6D11]' },
                { label: 'Lost', value: t.lost.toLocaleString(), tone: 'text-rose-600' },
                { label: 'Win rate', value: `${t.win_rate}%`, tone: 'text-gray-900' },
                { label: 'Deals in period', value: t.deals.toLocaleString(), tone: 'text-gray-900' },
              ].map((s) => (
                <div key={s.label} className="rounded-lg border border-gray-200 p-3">
                  <div className={`text-xl font-semibold tabular-nums ${s.tone}`}>{s.value}</div>
                  <div className="mt-0.5 text-[11px] text-gray-500">{s.label}</div>
                </div>
              ))}
            </div>
          )}
        </Card.Body>
      </Card>

      {!loading && (data?.journey ?? []).length > 0 && (
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Conversion through the journey</h2>
          </Card.Header>
          <Card.Body>
            <div className="space-y-5">
              {(data?.journey ?? []).map((f) => {
                const max = Math.max(1, ...f.buckets.map((b) => b.count));
                return (
                  <div key={f.flow}>
                    <div className="mb-1.5 flex items-baseline gap-2">
                      <span className="text-xs font-semibold capitalize text-gray-800">{f.flow}</span>
                      <span className="text-[11px] text-gray-400">{f.deals} open</span>
                    </div>
                    <div className="space-y-1">
                      {f.buckets.map((b) => (
                        <div key={b.key} className="flex items-center gap-2">
                          <span className="w-44 shrink-0 truncate text-[11px] text-gray-600"
                                title={b.label}>{b.label}</span>
                          <div className="h-4 flex-1 overflow-hidden rounded bg-gray-100">
                            <div className="h-full rounded"
                                 style={{ width: `${(b.count / max) * 100}%`,
                                          background: RAG[b.health.status] || RAG.idle }} />
                          </div>
                          <span className="w-10 shrink-0 text-right text-[11px] tabular-nums text-gray-700">
                            {b.count || '—'}
                          </span>
                          <span className="w-28 shrink-0 text-right text-[11px] tabular-nums text-gray-500">
                            {kes(b.value)}
                          </span>
                          <span className="w-24 shrink-0 text-right text-[10px] tabular-nums"
                                style={{ color: RAG[b.health.status] || RAG.idle }}>
                            {b.health.status === 'idle'
                              ? '—'
                              : `${b.health.avg_days}d / ${b.health.target_days}d`}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </Card.Body>
        </Card>
      )}

      {!loading && (data?.origin ?? []).length > 0 && (
        <Card>
          <Card.Header>
            <h2 className="text-base font-semibold text-gray-900">Where deals came from</h2>
          </Card.Header>
          <Card.Body>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {(data?.origin ?? []).map((o, i) => (
                <div key={o.origin} className="rounded-lg border border-gray-200 p-3">
                  <div className="flex items-baseline justify-between">
                    <span className="text-sm font-semibold text-gray-800">
                      {o.label || o.origin}
                    </span>
                    <span className="text-xs tabular-nums text-gray-500">
                      {originTotal ? Math.round((o.count / originTotal) * 100) : 0}%
                    </span>
                  </div>
                  <div className="mt-1 h-2 overflow-hidden rounded-full bg-gray-100">
                    <div className="h-full rounded-full"
                         style={{ width: `${originTotal ? (o.count / originTotal) * 100 : 0}%`,
                                  background: ORIGIN_COLOURS[i % ORIGIN_COLOURS.length] }} />
                  </div>
                  <div className="mt-2 flex gap-4 text-[11px] tabular-nums text-gray-600">
                    <span>{o.count} deals</span>
                    <span>KES {kes(o.value)}</span>
                    <span className="text-[#3B6D11]">{o.won} won</span>
                  </div>
                </div>
              ))}
            </div>
          </Card.Body>
        </Card>
      )}
    </div>
  );
}
