// PipelineFunnel — a real funnel-shaped, colored, interactive stage chart.
//
// Renders validated ("assured") deals by stage as continuous trapezoidal bands
// (a true funnel silhouette, not horizontal bars), with:
//   • a category filter (All / Asset / Liability / Insurance / Other) — the
//     analytics endpoint already returns a per-bucket funnel, so this is a
//     pure client-side switch, no extra round-trip.
//   • a sizing toggle (by deal count or by value).
//   • hover highlighting + a detail tooltip (count, value, share of the top
//     stage, conversion from the prior stage).
//
// Dependency-free: brand-coloured CSS clip-path bands, no chart library.

import { useMemo, useState } from 'react';
import type { FunnelStage } from '@/types/pipeline';

function fmtValue(v: number, symbol: string): string {
  if (!Number.isFinite(v) || v === 0) return '—';
  if (v >= 1e9) return `${symbol} ${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${symbol} ${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${symbol} ${(v / 1e3).toFixed(0)}K`;
  return `${symbol} ${Math.round(v).toLocaleString()}`;
}

// Brand gradient across stages: cyan (#1797ce) → navy (#0e2440).
const CYAN = [23, 151, 206] as const;
const NAVY = [14, 36, 64] as const;
function stageColor(i: number, n: number): string {
  const t = n <= 1 ? 0 : i / (n - 1);
  const r = Math.round(CYAN[0] + (NAVY[0] - CYAN[0]) * t);
  const g = Math.round(CYAN[1] + (NAVY[1] - CYAN[1]) * t);
  const b = Math.round(CYAN[2] + (NAVY[2] - CYAN[2]) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

export interface FunnelCategory {
  key: string;
  label: string;
  stages: FunnelStage[];
  activeCount?: number;
}

export interface PipelineFunnelProps {
  overall: FunnelStage[];
  categories?: FunnelCategory[];
  currencySymbol?: string;
  emptyHint?: string;
}

const BAND_H = 56; // px per stage band

export function PipelineFunnel({
  overall,
  categories = [],
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
  const stages = active?.stages ?? [];

  const totalCount = stages.reduce((a, s) => a + s.count, 0);
  const totalValue = stages.reduce((a, s) => a + s.value, 0);
  const topMetric = stages.length
    ? Math.max(...stages.map((s) => (metric === 'count' ? s.count : s.value)), 1)
    : 1;
  const maxMetric = topMetric;

  // Width (%) per band — floor so the smallest stage stays legible/hoverable.
  const FLOOR = 16;
  const widthPct = (s: FunnelStage): number => {
    const m = metric === 'count' ? s.count : s.value;
    return FLOOR + (100 - FLOOR) * (m / maxMetric);
  };

  return (
    <div>
      {/* Controls */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
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
                  <span className={on ? 'ml-1.5 text-gray-400' : 'ml-1.5 text-gray-400'}>
                    {t.activeCount}
                  </span>
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

      {stages.length === 0 ? (
        <div className="py-10 text-center text-sm text-gray-500">
          {catKey === 'all'
            ? (emptyHint ?? 'No validated deals to chart yet.')
            : `No validated deals in ${active?.label ?? 'this category'} yet.`}
        </div>
      ) : (
        <>
          {/* Funnel */}
          <div className="relative" style={{ height: stages.length * BAND_H }}>
            {stages.map((s, i) => {
              const wTop = widthPct(s);
              const next = stages[i + 1];
              const wBot = next ? widthPct(next) : wTop * 0.5; // taper to a tip
              const color = stageColor(i, stages.length);
              const isHover = hover === i;
              const shareTop = stages[0]
                ? Math.round((s.count / Math.max(stages[0].count, 1)) * 100)
                : 0;
              const prev = stages[i - 1];
              const conv = prev ? Math.round((s.count / Math.max(prev.count, 1)) * 100) : null;
              const inside = metric === 'count' ? String(s.count) : fmtValue(s.value, currencySymbol);

              return (
                <div
                  key={s.stage}
                  className="absolute inset-x-0 grid grid-cols-[150px_1fr_150px] items-center gap-3"
                  style={{ top: i * BAND_H, height: BAND_H }}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover((h) => (h === i ? null : h))}
                >
                  {/* Stage label */}
                  <div className="truncate text-right text-sm text-gray-600">{s.stage}</div>

                  {/* Funnel band */}
                  <div className="relative h-full">
                    <div
                      className="absolute inset-0 transition-[filter,transform] duration-150"
                      style={{
                        background: color,
                        clipPath: `polygon(${50 - wTop / 2}% 0, ${50 + wTop / 2}% 0, ${50 + wBot / 2}% 100%, ${50 - wBot / 2}% 100%)`,
                        filter: isHover ? 'brightness(1.12)' : 'none',
                        transform: isHover ? 'scaleY(1.04)' : 'none',
                      }}
                    />
                    <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
                      <span className="text-sm font-bold text-white drop-shadow">{inside}</span>
                    </div>
                  </div>

                  {/* Right gutter: the other metric + conversion */}
                  <div className="text-xs text-gray-500">
                    <div className="font-medium text-gray-700">
                      {metric === 'count' ? fmtValue(s.value, currencySymbol) : `${s.count} deals`}
                    </div>
                    <div className="text-[11px] text-gray-400">
                      {conv === null ? `${shareTop}% of top` : `${conv}% of prior`}
                    </div>
                  </div>

                  {/* Hover tooltip */}
                  {isHover && (
                    <div
                      className="pointer-events-none absolute left-1/2 z-10 -translate-x-1/2 rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs shadow-lg"
                      style={{ top: -6 }}
                    >
                      <div className="mb-0.5 font-semibold text-[var(--brand-secondary)]">{s.stage}</div>
                      <div className="text-gray-600">{s.count} deals · {fmtValue(s.value, currencySymbol)}</div>
                      <div className="text-gray-400">
                        {shareTop}% of top stage{conv !== null ? ` · ${conv}% from prior` : ''}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Caption */}
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
