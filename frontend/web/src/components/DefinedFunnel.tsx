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

import { useEffect, useMemo, useState, type ReactNode } from 'react';
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
  /** THE JOURNEY FOLLOWS THE SELECTION. Without this the funnel showed the
   *  whole book while the list beneath it showed one line - two panels on one
   *  screen describing different things. `unit` is a whole line (Consumer),
   *  `segment` one sub-segment (Premier). */
  unit?: string;
  segment?: string;
  /** Rendered beside the bands, where the funnel leaves space. */
  aside?: ReactNode;
}

export default function DefinedFunnel({ onStageClick, unit, segment, aside }: DefinedFunnelProps = {}) {
  const { toast } = useToast();
  const [data, setData] = useState<FunnelData | null>(null);
  const [loading, setLoading] = useState(false);
  const [flowKey, setFlowKey] = useState('');
  const [hover, setHover] = useState('');

  useEffect(() => {
    let alive = true;
    setLoading(true);
    void (async () => {
      try {
        const r = await fetchPipelineDefinedFunnel({ unit, segment });
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
  }, [toast, unit, segment]);

  const flow: DefinedFlow | undefined = useMemo(
    () => data?.flows.find((f) => f.flow === flowKey) ?? data?.flows[0],
    [data, flowKey]);

  const buckets = flow?.buckets ?? [];
  // Micro-steps open on demand: management reads the six buckets, an officer
  // opens the one they work in.
  const [openBucket, setOpenBucket] = useState('');

  return (
    <Card>
      <Card.Header>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Pipeline journey</h2>
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

        {/* THE BANDS AND THE SELECTOR SIDE BY SIDE. The funnel is a narrowing
            shape, so the right-hand side of the card was empty space while the
            business-line selector sat above the deal list in a wrapped row of
            chips. Putting the selector where the space already is reads better
            and, more importantly, puts the thing you are filtering BY next to
            the thing it filters. On a narrow screen it stacks. */}
        {!loading && data && data.flows.length > 0 && (
          <div className={aside ? 'lg:flex lg:items-start lg:gap-6' : ''}>
          <div className={aside ? 'min-w-0 lg:flex-1' : ''}>
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

            {/* A TRUE FUNNEL: each band is a trapezoid whose top edge matches
                the band above, so the silhouette is continuous from Initiation
                to disbursement rather than a stack of separate bars. Width
                follows the ideal taper — what a healthy pipeline SHOULD look
                like — while the RAG rail on the left reports what it is
                actually doing. Shape shows the plan; colour shows the truth. */}
            <div className="mx-auto" style={{ maxWidth: 760 }}>
              {buckets.map((b, i) => {
                const wTop = 100 - (i / Math.max(buckets.length, 1)) * 62;
                const wBot = 100 - ((i + 1) / Math.max(buckets.length, 1)) * 62;
                const colour = bandColour(i, buckets.length);
                const empty = b.count === 0;
                const on = hover === b.key;
                const open = openBucket === b.key;
                const h = b.health;
                const rag = h.status === 'red' ? '#C4536F'
                  : h.status === 'amber' ? '#E0A02B'
                  : h.status === 'green' ? '#669438' : '#D8DBDF';
                return (
                  <div key={b.key}>
                    <div
                      onMouseEnter={() => setHover(b.key)}
                      onMouseLeave={() => setHover('')}
                      onClick={() => setOpenBucket(open ? '' : b.key)}
                      className="relative flex cursor-pointer items-stretch gap-2"
                    >
                      {/* the health rail — red/amber/green, per stage */}
                      <div className="w-1.5 shrink-0 rounded-full transition-all"
                           style={{ background: rag, opacity: on ? 1 : 0.85 }}
                           title={h.status === 'idle'
                             ? 'No deals at this stage'
                             : `${h.avg_days} working days on average against a ${h.target_days}-day target`} />

                      <div className="relative flex-1" style={{ height: 58 }}>
                        {/* the trapezoid */}
                        <div
                          className="absolute inset-0 transition-transform duration-200"
                          style={{
                            clipPath: `polygon(${(100 - wTop) / 2}% 0%, ${100 - (100 - wTop) / 2}% 0%, ${100 - (100 - wBot) / 2}% 100%, ${(100 - wBot) / 2}% 100%)`,
                            background: empty
                              ? 'repeating-linear-gradient(45deg,#F4F5F7,#F4F5F7 7px,#E9EBEE 7px,#E9EBEE 14px)'
                              : `linear-gradient(180deg, rgba(255,255,255,0.30) 0%, ${colour} 34%, ${colour} 62%, rgba(0,0,0,0.26) 100%), ${colour}`,
                            transform: on ? 'scaleY(1.04)' : 'none',
                            filter: on ? 'brightness(1.06)' : 'none',
                          }}
                        />
                        {/* fill: how much of this band the deals occupy */}
                        {!empty && (
                          <div className="absolute inset-y-0 left-0 flex items-center justify-center"
                               style={{ width: '100%' }}>
                            <div className="flex items-baseline gap-2 text-white drop-shadow">
                              <span className="text-lg font-semibold tabular-nums">{b.count}</span>
                              <span className="text-[11px] opacity-90">KES {kes(b.value)}</span>
                            </div>
                          </div>
                        )}
                        {empty && (
                          <div className="absolute inset-0 flex items-center justify-center">
                            <span className="text-[11px] text-gray-400">nothing here</span>
                          </div>
                        )}
                      </div>

                      <div className="w-52 shrink-0 self-center">
                        <div className={'truncate text-xs font-semibold ' + (empty ? 'text-gray-400' : 'text-gray-800')}
                             title={b.label}>
                          <span className="mr-1 text-gray-400">{open ? '▾' : '▸'}</span>
                          {b.label}
                        </div>
                        <div className="text-[10px] text-gray-400">
                          {b.weight}% · {Math.round(b.probability * 100)}% at exit
                        </div>
                        <div className="text-[10px]" style={{ color: rag }}>
                          {h.status === 'idle'
                            ? 'no deals'
                            : `${h.avg_days}d avg / ${h.target_days}d target`
                              + (h.at_risk ? ` · ${h.at_risk} over` : '')}
                        </div>
                      </div>
                    </div>

                    {open && (
                      <div className="mb-1 ml-4 space-y-1 border-l-2 border-gray-200 pl-3">
                        {b.steps.map((st) => (
                          <div key={st.stage}
                               onClick={(e) => {
                                 e.stopPropagation();
                                 if (st.count && onStageClick && flow) onStageClick(flow.flow, st.stage);
                               }}
                               className={'flex items-center gap-3 text-xs '
                                 + (st.count && onStageClick ? 'cursor-pointer hover:bg-gray-50' : '')}>
                            <span className="w-56 truncate text-gray-600" title={st.stage}>{st.stage}</span>
                            <span className="w-14 text-right tabular-nums text-gray-400">
                              {Math.round(st.probability * 100)}%
                            </span>
                            <div className="h-2 flex-1 overflow-hidden rounded-full bg-gray-100">
                              <div className="h-full rounded-full"
                                   style={{ width: `${b.count ? (st.count / Math.max(b.count, 1)) * 100 : 0}%`,
                                            background: colour }} />
                            </div>
                            <span className="w-10 text-right tabular-nums text-gray-700">{st.count}</span>
                            <span className="w-28 text-right tabular-nums text-gray-500">KES {kes(st.value)}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* What the colours mean — three words, not a paragraph. */}
            <div className="mt-3 flex items-center justify-center gap-4 text-[10px] text-gray-500">
              {[['#669438', 'within target'], ['#E0A02B', 'slipping'],
                ['#C4536F', 'stalled'], ['#D8DBDF', 'no deals']].map(([c, l]) => (
                <span key={l} className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full" style={{ background: c }} />
                  {l}
                </span>
              ))}
            </div>

            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-gray-100 pt-3 text-xs">
              <span className="text-gray-500">
                {flow?.deals ?? 0} deals · KES {kes(flow?.value ?? 0)} ·{' '}
                <span className="font-semibold text-gray-800">
                  KES {kes(flow?.weighted ?? 0)} weighted
                </span>
              </span>
            </div>
          </div>

          {aside && (
            /* The selector column. Fixed width so the bands keep a sensible
               shape - a funnel that reflows as the sidebar grows stops looking
               like a funnel. Sticky so it stays put while somebody reads down
               a long journey. */
            <div className="mt-6 shrink-0 lg:mt-0 lg:w-64 lg:self-start lg:sticky lg:top-4">
              {aside}
            </div>
          )}
          </div>
        )}
      </Card.Body>
    </Card>
  );
}
