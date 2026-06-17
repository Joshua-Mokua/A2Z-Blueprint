// PipelineFunnel — a real funnel-shaped, vivid, interactive stage chart.
//
// • Category filter (All / Asset / Liability / Insurance / Other). When a class
//   is selected the funnel renders that class's DEFINED stage flow from admin
//   config (stage_flows) — so it follows the stages the bank actually configured
//   per product class, showing even the stages that hold no assured deals yet.
// • Size-by toggle (deal count or value) rescales the bands.
// • Hover highlights a band and reveals a detail tooltip.
//
// Dependency-free: vivid multi-hue gradient via CSS clip-path bands.

import { useMemo, useState } from 'react';
import type { FunnelStage } from '@/types/pipeline';

function fmtValue(v: number, symbol: string): string {
  if (!Number.isFinite(v) || v === 0) return '—';
  if (v >= 1e9) return `${symbol} ${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${symbol} ${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${symbol} ${(v / 1e3).toFixed(0)}K`;
  return `${symbol} ${Math.round(v).toLocaleString()}`;
}

// Vivid cool→warm sweep — distinct per stage but cohesive across the funnel.
const PALETTE = ['#06b6d4', '#3b82f6', '#6366f1', '#a855f7', '#ec4899', '#f59e0b', '#10b981'];
function hexToRgb(h: string): [number, number, number] {
  const n = parseInt(h.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function lerp(a: number, b: number, t: number): number { return Math.round(a + (b - a) * t); }
function stageColor(i: number, n: number): string {
  if (n <= 1) return PALETTE[0];
  const seg = (i / (n - 1)) * (PALETTE.length - 1);
  const idx = Math.min(Math.floor(seg), PALETTE.length - 2);
  const t = seg - idx;
  const [r1, g1, b1] = hexToRgb(PALETTE[idx]);
  const [r2, g2, b2] = hexToRgb(PALETTE[idx + 1]);
  return `rgb(${lerp(r1, r2, t)}, ${lerp(g1, g2, t)}, ${lerp(b1, b2, t)})`;
}

const CLOSED = new Set(['Closed Won', 'Closed Lost', 'Closed-Won', 'Closed-Lost']);

export interface FunnelCategory {
  key: string;
  label: string;
  stages: FunnelStage[];
  activeCount?: number;
}

export interface PipelineFunnelProps {
  overall: FunnelStage[];
  categories?: FunnelCategory[];
  /** Admin-configured defined stage flow per class (asset/liability/…). */
  stageFlows?: Record<string, string[]>;
  /** Drill: fired when a non-empty stage band is clicked (class key, stage). */
  onStageClick?: (cls: string, stage: string) => void;
  currencySymbol?: string;
  emptyHint?: string;
}

const BAND_H = 58;

export function PipelineFunnel({
  overall,
  categories = [],
  stageFlows,
  onStageClick,
  currencySymbol = '',
  emptyHint,
}: PipelineFunnelProps) {
  const [catKey, setCatKey] = useState<string>('all');
  const [metric, setMetric] = useState<'count' | 'value'>('count');
  const [hover, setHover] = useState<number | null>(null);

  const tabs = useMemo(
    () => [
      { key: 'all', label: 'All', stages: overall, activeCount: undefined as number | undefined },
      ...categories,
    ],
    [overall, categories],
  );

  const active = tabs.find((t) => t.key === catKey) ?? tabs[0];

  // For a specific class, lay the data over the class's DEFINED flow (config),
  // so configured-but-empty stages still appear. For "All", use what's present.
  const stages = useMemo<FunnelStage[]>(() => {
    const data = active?.stages ?? [];
    const flow = catKey !== 'all' ? stageFlows?.[catKey] : undefined;
    if (!flow) return data;
    const byStage = new Map(data.map((s) => [s.stage, s]));
    return flow
      .filter((s) => !CLOSED.has(s))
      .map((s) => byStage.get(s) ?? { stage: s, count: 0, value: 0 });
  }, [active, catKey, stageFlows]);

  const totalCount = stages.reduce((a, s) => a + s.count, 0);
  const totalValue = stages.reduce((a, s) => a + s.value, 0);
  const maxMetric = stages.length
    ? Math.max(...stages.map((s) => (metric === 'count' ? s.count : s.value)), 1)
    : 1;

  const FLOOR = 14;
  const widthPct = (s: FunnelStage): number => {
    const m = metric === 'count' ? s.count : s.value;
    return FLOOR + (100 - FLOOR) * (m / maxMetric);
  };

  const anyData = stages.some((s) => s.count > 0);

  return (
    <div>
      {/* Controls */}
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex flex-wrap gap-1 rounded-lg bg-gray-100 p-1">
          {tabs.map((t) => {
            const on = t.key === catKey;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => { setCatKey(t.key); setHover(null); }}
                className={[
                  'rounded-md px-3 py-1.5 text-xs font-semibold transition-colors',
                  on ? 'bg-white text-[var(--brand-secondary)] shadow-sm'
                     : 'text-gray-500 hover:text-gray-800',
                ].join(' ')}
              >
                {t.label}
                {typeof t.activeCount === 'number' && (
                  <span className="ml-1.5 text-gray-400">{t.activeCount}</span>
                )}
              </button>
            );
          })}
        </div>

        <div className="inline-flex items-center gap-2 text-xs text-gray-500">
          <span>Size by</span>
          <div className="inline-flex rounded-md border border-gray-200">
            {(['count', 'value'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMetric(m)}
                className={[
                  'px-2.5 py-1 text-xs font-medium capitalize transition-colors',
                  metric === m ? 'bg-[var(--brand-primary)] text-white' : 'text-gray-600 hover:bg-gray-50',
                  m === 'count' ? 'rounded-l-md' : 'rounded-r-md',
                ].join(' ')}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
      </div>

      {stages.length === 0 || !anyData ? (
        <div className="py-10 text-center text-sm text-gray-500">
          {catKey === 'all'
            ? (emptyHint ?? 'No validated deals to chart yet.')
            : `No assured deals in ${active?.label ?? 'this class'} yet — its defined stages are ${
                (stageFlows?.[catKey] ?? []).filter((s) => !CLOSED.has(s)).join(' → ') || 'not configured'
              }.`}
        </div>
      ) : (
        <>
          <div className="relative" style={{ height: stages.length * BAND_H }}>
            {stages.map((s, i) => {
              const wTop = widthPct(s);
              const next = stages[i + 1];
              const wBot = next ? widthPct(next) : wTop * 0.5;
              const color = stageColor(i, stages.length);
              const isHover = hover === i;
              const empty = s.count === 0;
              const shareTop = stages[0] && stages[0].count
                ? Math.round((s.count / stages[0].count) * 100) : 0;
              const prev = stages[i - 1];
              const conv = prev && prev.count ? Math.round((s.count / prev.count) * 100) : null;
              const inside = metric === 'count' ? String(s.count) : fmtValue(s.value, currencySymbol);

              const clickable = !empty && !!onStageClick;
              return (
                <div
                  key={s.stage}
                  className={[
                    'absolute inset-x-0 grid grid-cols-[160px_1fr_150px] items-center gap-3',
                    clickable ? 'cursor-pointer' : '',
                  ].join(' ')}
                  style={{ top: i * BAND_H, height: BAND_H }}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover((h) => (h === i ? null : h))}
                  onClick={() => { if (clickable) onStageClick!(catKey, s.stage); }}
                >
                  <div className={['truncate text-right text-sm', empty ? 'text-gray-400' : 'text-gray-700'].join(' ')}>
                    {s.stage}
                  </div>

                  <div className="relative h-full">
                    <div
                      className="absolute inset-0 transition-[filter,transform] duration-150"
                      style={{
                        background: `linear-gradient(180deg, ${color} 0%, ${color} 60%, rgba(0,0,0,0.14) 320%)`,
                        clipPath: `polygon(${50 - wTop / 2}% 6%, ${50 + wTop / 2}% 6%, ${50 + wBot / 2}% 94%, ${50 - wBot / 2}% 94%)`,
                        opacity: empty ? 0.28 : 1,
                        filter: isHover ? 'brightness(1.12) drop-shadow(0 4px 10px rgba(0,0,0,0.18))' : 'none',
                        transform: isHover ? 'scaleY(1.05)' : 'none',
                      }}
                    />
                    <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                      <span className={['text-sm font-bold drop-shadow', empty ? 'text-gray-500' : 'text-white'].join(' ')}>
                        {inside}
                      </span>
                    </div>
                  </div>

                  <div className="text-xs text-gray-500">
                    <div className="font-medium text-gray-700">
                      {metric === 'count' ? fmtValue(s.value, currencySymbol) : `${s.count} deals`}
                    </div>
                    <div className="text-[11px] text-gray-400">
                      {i === 0 ? `${shareTop}% of top` : conv === null ? '—' : `${conv}% of prior`}
                    </div>
                  </div>

                  {isHover && !empty && (
                    <div
                      className="pointer-events-none absolute left-1/2 z-10 -translate-x-1/2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs shadow-lg"
                      style={{ top: -4 }}
                    >
                      <div className="mb-0.5 font-semibold text-[var(--brand-secondary)]">{s.stage}</div>
                      <div className="text-gray-600">{s.count} deals · {fmtValue(s.value, currencySymbol)}</div>
                      <div className="text-gray-400">
                        {shareTop}% of top{conv !== null ? ` · ${conv}% from prior` : ''}
                      </div>
                      {onStageClick && <div className="mt-0.5 text-[var(--brand-primary)]">Click to drill →</div>}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-3 text-xs text-gray-500">
            <span>{active?.label ?? 'All'} · assured deals by stage</span>
            <span className="font-medium text-gray-700">
              {totalCount} deals · {fmtValue(totalValue, currencySymbol)}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
