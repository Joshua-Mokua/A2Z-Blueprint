// PipelineFunnel — validated-only stage funnel (B-frontend).
//
// Horizontal bars sized by deal count per stage, with the value alongside.
// Built from plain divs (no chart library) so it's dependency-free and
// type-stable. Consumes the analytics endpoint's `funnel` array, which is
// already validated-only (matches the assured headline).

import type { FunnelStage } from '@/types/pipeline';

function fmtValue(v: number, symbol: string): string {
  if (!Number.isFinite(v) || v === 0) return '—';
  if (v >= 1e9) return `${symbol} ${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${symbol} ${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${symbol} ${(v / 1e3).toFixed(0)}K`;
  return `${symbol} ${v.toLocaleString()}`;
}

export interface PipelineFunnelProps {
  stages: FunnelStage[];
  currencySymbol?: string;
  emptyHint?: string;
}

export function PipelineFunnel({
  stages,
  currencySymbol = '',
  emptyHint,
}: PipelineFunnelProps) {
  if (!stages || stages.length === 0) {
    return (
      <div className="py-8 text-center text-sm text-gray-500">
        {emptyHint ?? 'No validated deals to chart yet.'}
      </div>
    );
  }

  const maxCount = Math.max(...stages.map((s) => s.count), 1);

  return (
    <div className="space-y-2">
      {stages.map((s) => {
        const pct = Math.max(6, Math.round((s.count / maxCount) * 100));
        return (
          <div key={s.stage} className="flex items-center gap-3">
            <div className="w-36 shrink-0 text-sm text-gray-700 text-right truncate">
              {s.stage}
            </div>
            <div className="flex-1">
              <div
                className="h-7 rounded-md flex items-center px-2 text-xs font-semibold text-white"
                style={{
                  width: `${pct}%`,
                  minWidth: 36,
                  background: 'var(--brand-primary)',
                }}
              >
                {s.count}
              </div>
            </div>
            <div className="w-28 shrink-0 text-xs text-gray-500 text-right">
              {fmtValue(s.value, currencySymbol)}
            </div>
          </div>
        );
      })}
    </div>
  );
}
