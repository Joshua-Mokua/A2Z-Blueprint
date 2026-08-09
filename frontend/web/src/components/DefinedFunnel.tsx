// DefinedFunnel — the pipeline centrepiece, drawn from ADMIN CONFIG.
//
// Ruling 2026-08-09: stages are never hardcoded. Every band here is a stage the
// bank configured in that product's flow, in the order it configured them, with
// the win probability it set for that stage WITHIN THAT FLOW.
//
// EMPTY STAGES ARE DRAWN. A funnel that hides the steps holding nothing is a bar
// chart of whatever happened to be busy — and the empty step is usually the
// finding: it is where deals stop arriving.
//
// THE CREDIT LAYER IS A SECOND AXIS, not a stage. Documentation / Branch Credit /
// Department / Credit Analysis / Credit Administration / TROPS say where a deal
// probably sits inside the bank, inferred from its probability. It sits beneath
// the journey and never filters it.

import { useEffect, useMemo, useState } from 'react';
import { Card } from '@/components/Card';
import { useToast } from '@/components/Toast';
import { fetchPipelineDefinedFunnel, type DefinedFunnel as FunnelData, type DefinedFlow } from '@/lib/api';

// Cool→warm sweep: early stages cool, closing stages warm. Depth comes from a
// vertical gradient plus a soft inner highlight, so a band reads as a solid
// object rather than a coloured rectangle.
const PALETTE = ['#0082BB', '#0C7BC0', '#3F6FC4', '#6A61C0', '#9455B0', '#BE4E93', '#D75A72', '#E0A02B', '#669438'];

function bandColour(i: number, n: number): string {
  if (n <= 1) return PALETTE[0];
  const seg = (i / (n - 1)) * (PALETTE.length - 1);
  const idx = Math.min(Math.floor(seg), PALETTE.length - 2);
  const t = seg - idx;
  const hex = (h: string) => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];
  const [r1, g1, b1] = hex(PALETTE[idx]);
  const [r2, g2, b2] = hex(PALETTE[idx + 1]);
  const m = (a: number, b: number) => Math.round(a + (b - a) * t);
  return `rgb(${m(r1, r2)}, ${m(g1, g2)}, ${m(b1, b2)})`;
}

function kes(n: number): string {
  if (!n) return '—';
  return Math.round(n).toLocaleString();
}

export interface DefinedFunnelProps {
  /** Clicking a non-empty band drills into that flow + stage. Preserved from the
   *  previous funnel: dropping it would have removed a working feature quietly. */
  onStageClick?: (flow: string, stage: string) => void;
}

export default function DefinedFunnel({ onStageClick }: DefinedFunnelProps = {}) {
  const { toast } = useToast();
  const [data, setData] = useState<FunnelData | null>(null);
  const [loading, setLoading] = useState(false);
  const [flowKey, setFlowKey] = useState('');
  const [sizeBy, setSizeBy] = useState<'count' | 'value'>('count');
  const [hover, setHover] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void (async () => {
      try {
        const r = await fetchPipelineDefinedFunnel();
        if (!alive) return;
        setData(r);
        setFlowKey((k) => k || (r.flows[0]?.flow ?? ''));
      } catch (e) {
        if (alive) toast({ tone: 'danger', message: e instanceof Error ? e.message : 'Could not load the funnel.' });
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [toast]);

  const flow: DefinedFlow | undefined = useMemo(
    () => data?.flows.find((f) => f.flow === flowKey) ?? data?.flows[0],
    [data, flowKey]);

  const stages = flow?.stages ?? [];
  const max = Math.max(1, ...stages.map((s) => (sizeBy === 'count' ? s.count : s.value)));
  const creditMax = Math.max(1, ...(data?.credit_layer ?? []).map((c) => c.count));

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Pipeline journey</h2>
            <p className="mt-0.5 text-xs text-gray-500">
              Each product's defined stages, in the order the bank configured them.
            </p>
          </div>
          <div className="flex items-center gap-1 text-[11px]">
            {(['count', 'value'] as const).map((s) => (
              <button key={s} type="button" onClick={() => setSizeBy(s)}
                className={'rounded-full px-2.5 py-1 font-medium '
                  + (sizeBy === s ? 'bg-[#0082BB] text-white' : 'text-[#005B82] hover:bg-[#0082BB]/10')}>
                by {s}
              </button>
            ))}
          </div>
        </div>
      </Card.Header>

      <Card.Body>
        {loading && <p className="py-10 text-center text-sm text-gray-400">Loading the journey…</p>}

        {!loading && data && data.flows.length === 0 && (
          <p className="py-10 text-center text-sm text-gray-400">
            No product flows configured. Define them in Administration.
          </p>
        )}

        {!loading && data && data.flows.length > 0 && (
          <>
            <div className="mb-3 flex flex-wrap gap-1.5">
              {data.flows.map((f) => (
                <button key={f.flow} type="button" onClick={() => setFlowKey(f.flow)}
                  className={'rounded-full px-3 py-1 text-xs font-medium capitalize transition-colors '
                    + (flow?.flow === f.flow ? 'bg-[#005B82] text-white'
                                             : 'bg-gray-100 text-gray-600 hover:bg-[#0082BB]/10')}>
                  {f.flow}
                  <span className="ml-1.5 opacity-70">{f.deals}</span>
                </button>
              ))}
            </div>

            {/* The journey. Bands taper by position so the shape reads as a
                funnel even where the numbers do not decline monotonically —
                real pipelines rarely do, and a mis-shaped funnel invites the
                reader to think the data is wrong when it is not. */}
            <div className="space-y-1.5">
              {stages.map((s, i) => {
                const metric = sizeBy === 'count' ? s.count : s.value;
                const fill = Math.max(metric / max, metric > 0 ? 0.06 : 0);
                const taper = 1 - (i / Math.max(stages.length, 2)) * 0.34;
                const colour = bandColour(i, stages.length);
                const empty = s.count === 0;
                const on = hover === s.stage;
                return (
                  <div key={s.stage}
                       onMouseEnter={() => setHover(s.stage)}
                       onMouseLeave={() => setHover('')}
                       onClick={() => {
                         if (!empty && onStageClick && flow) onStageClick(flow.flow, s.stage);
                       }}
                       className={'group relative flex items-center gap-3 '
                         + (!empty && onStageClick ? 'cursor-pointer' : '')}>
                    <div className="w-40 shrink-0 text-right">
                      <div className={'truncate text-xs font-medium ' + (empty ? 'text-gray-400' : 'text-gray-800')}
                           title={s.stage}>
                        {s.stage}
                      </div>
                      <div className="text-[10px] text-gray-400">
                        {Math.round(s.probability * 100)}% win
                      </div>
                    </div>

                    <div className="relative h-11 flex-1" style={{ paddingInline: `${(1 - taper) * 50}%` }}>
                      <div className="absolute inset-y-0 left-0 right-0 rounded-md bg-gray-100/70"
                           style={{ marginInline: `${(1 - taper) * 50}%` }} />
                      <div
                        className={'relative h-full rounded-md transition-all duration-200 '
                          + (on ? 'shadow-lg' : 'shadow-sm')}
                        style={{
                          width: `${Math.max(fill * 100, 0)}%`,
                          background: empty
                            ? 'repeating-linear-gradient(45deg,#F3F4F6,#F3F4F6 6px,#E9EBEE 6px,#E9EBEE 12px)'
                            : `linear-gradient(180deg, ${colour} 0%, ${colour} 42%, rgba(0,0,0,0.18) 100%), ${colour}`,
                          boxShadow: empty ? 'none'
                            : `inset 0 1px 0 rgba(255,255,255,0.45), inset 0 -2px 6px rgba(0,0,0,0.18)`,
                          transform: on ? 'translateY(-1px)' : 'none',
                        }}
                      >
                        {!empty && (
                          <div className="flex h-full items-center gap-2 px-3 text-white">
                            <span className="text-sm font-semibold tabular-nums drop-shadow">{s.count}</span>
                            <span className="truncate text-[11px] opacity-90">
                              KES {kes(s.value)}
                            </span>
                          </div>
                        )}
                      </div>
                      {empty && (
                        <div className="pointer-events-none absolute inset-0 flex items-center px-3">
                          <span className="text-[11px] text-gray-400">no deals at this stage</span>
                        </div>
                      )}
                    </div>

                    <div className="w-32 shrink-0 text-right">
                      <div className="text-[11px] tabular-nums text-gray-600">
                        KES {kes(s.weighted)}
                      </div>
                      <div className="text-[10px] text-gray-400">weighted</div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3 text-xs">
              <span className="text-gray-500">
                {flow?.deals ?? 0} deals · KES {kes(flow?.value ?? 0)} ·{' '}
                <span className="font-semibold text-gray-800">
                  KES {kes(flow?.weighted ?? 0)} weighted
                </span>
              </span>
              {(data.unplaced_deals ?? 0) > 0 && (
                <span className="rounded-full bg-[#FBEAF0] px-2.5 py-1 text-[11px] text-[#993556]">
                  {data.unplaced_deals} deal(s) sit at a stage no configured flow contains —
                  they are counted nowhere above
                </span>
              )}
            </div>

            {/* The side layer. A second axis over the same deals, never a filter. */}
            {(data.credit_layer ?? []).length > 0 && (
              <div className="mt-5">
                <div className="mb-1.5 text-xs font-semibold text-gray-600">
                  Where these deals sit inside the bank
                  <span className="ml-1 font-normal text-gray-400">
                    — inferred from win probability, not a sales stage
                  </span>
                </div>
                <div className="flex gap-1.5 overflow-x-auto pb-1">
                  {data.credit_layer.map((c, i) => (
                    <div key={c.label}
                         className="min-w-[132px] flex-1 rounded-lg border border-gray-200 p-2">
                      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                        <div className="h-full rounded-full"
                             style={{ width: `${(c.count / creditMax) * 100}%`,
                                      background: bandColour(i, data.credit_layer.length) }} />
                      </div>
                      <div className="mt-1.5 truncate text-[11px] font-medium text-gray-700"
                           title={c.label}>{c.label}</div>
                      <div className="text-[10px] text-gray-400">
                        {Math.round(c.min * 100)}–{Math.round(Math.min(c.max, 1) * 100)}%
                      </div>
                      <div className="mt-0.5 text-sm font-semibold tabular-nums text-gray-900">
                        {c.count}
                      </div>
                      <div className="text-[10px] tabular-nums text-gray-500">
                        KES {kes(c.value)}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </Card.Body>
    </Card>
  );
}
