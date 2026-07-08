// v10.496 — Stat primitive.
//
// The reusable KPI tile. v10.495's Dashboard.tsx inlined this layout;
// v10.496 extracts it as a real component so every page that shows
// numeric metrics (MD Cockpit, RM dashboards, branch ops, etc.) uses
// the same visual + accessibility contract.
//
// API:
//   <Stat label="Total Deposits" value="KES 1.42T" />
//   <Stat label="NPL Ratio" value="11.1%" delta={-0.4} />
//   <Stat label="Active RMs" value={232} sub="Target: 250" />
//   <Stat label="Pipeline" value="..." loading />
//
// `delta` is interpreted as a percentage-point change; positive shows
// in green (with up arrow), negative in red (with down arrow). To
// invert the polarity (e.g. NPL going DOWN is good), pass
// `invertDelta`.

import type { ReactNode } from 'react';
import { Card } from './Card';
import { cn } from '@/lib/cn';

export interface StatProps {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  delta?: number;
  invertDelta?: boolean;
  loading?: boolean;
  stripe?: boolean | 'primary' | 'secondary' | 'accent';
  /** Subtle tinted background + coloured left accent — colour-codes the tile. */
  tone?: 'primary' | 'secondary' | 'accent' | 'neutral' | 'success' | 'lime' | 'teal' | 'violet';
  /** When set, the tile becomes a clickable drill-through. */
  onClick?: () => void;
  className?: string;
}

const TONE_BG: Record<string, string> = {
  primary:   'bg-sky-50 border-l-[3px] border-l-[#0082BB]',
  secondary: 'bg-slate-50 border-l-[3px] border-l-[#005B82]',
  accent:    'bg-amber-50 border-l-[3px] border-l-amber-400',
  success:   'bg-emerald-50 border-l-[3px] border-l-[#669438]',
  lime:      'bg-lime-50 border-l-[3px] border-l-[#8ba700]',
  teal:      'bg-teal-50 border-l-[3px] border-l-teal-500',
  violet:    'bg-violet-50 border-l-[3px] border-l-violet-400',
  neutral:   '',
};

function formatDelta(delta: number): string {
  const sign = delta > 0 ? '+' : '';
  return `${sign}${delta.toFixed(1)}`;
}

export function Stat({
  label, value, sub, delta, invertDelta = false,
  loading = false, stripe = 'primary', tone, onClick, className,
}: StatProps) {
  // When invertDelta is true (e.g. NPL ratio), down is good.
  const isGood = delta === undefined
    ? null
    : invertDelta ? delta < 0 : delta > 0;

  const isBad = delta === undefined
    ? null
    : invertDelta ? delta > 0 : delta < 0;

  const clickable = typeof onClick === 'function';

  return (
    <Card
      stripe={stripe}
      padding="md"
      onClick={onClick}
      className={cn(
        'relative',
        tone && TONE_BG[tone],
        clickable && 'cursor-pointer hover:shadow-md hover:border-gray-300 transition-all',
        className,
      )}
    >
      <div className="text-xs font-semibold uppercase tracking-wider
                       text-gray-500">
        {label}
      </div>
      <div className="mt-2 flex items-baseline gap-3">
        {loading ? (
          <span className="inline-block h-9 w-24 rounded
                            bg-gray-100 animate-pulse" />
        ) : (
          <span className="text-3xl font-bold text-brand-secondary">
            {value}
          </span>
        )}
        {!loading && delta !== undefined && (
          <span className={cn(
            'inline-flex items-center text-sm font-medium',
            isGood && 'text-green-600',
            isBad && 'text-red-600',
            !isGood && !isBad && 'text-gray-500',
          )}>
            {isGood && <span aria-hidden="true">↑</span>}
            {isBad && <span aria-hidden="true">↓</span>}
            {formatDelta(delta)}%
          </span>
        )}
      </div>
      {sub && (
        <div className="mt-2 text-xs text-gray-400">{sub}</div>
      )}
      {clickable && (
        <span className="absolute top-3 right-3 text-gray-300 text-sm" aria-hidden="true">→</span>
      )}
    </Card>
  );
}
