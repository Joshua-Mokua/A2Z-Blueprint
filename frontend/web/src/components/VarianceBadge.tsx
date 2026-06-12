// v10.543 Phase P Batch P3a — VarianceBadge primitive.
//
// Shows the gap between an actual and its target as a signed percentage,
// colored by whether the gap is FAVORABLE or ADVERSE — not merely by
// sign. This matters because for some KPIs lower is better (NPL, PAR,
// Dormancy): being below target is GOOD. Pass `invert` for those.
//
// Variance is computed as (actual − target) / |target| × 100.
//   • Normal KPI (higher is better): actual ≥ target → favorable (green)
//   • Inverted KPI (lower is better): actual ≤ target → favorable (green)
//
// API:
//   <VarianceBadge actual={92}  target={100} />            → −8.0%  (red)
//   <VarianceBadge actual={108} target={100} />            → +8.0%  (green)
//   <VarianceBadge actual={9.5} target={11} invert />      → −13.6% (green: NPL down)
//   <VarianceBadge actual={...} target={0} />              → "—"    (no target)
//   <VarianceBadge variancePct={-16} status-driven... />   ← or pass a precomputed %
//
// You can pass a precomputed `variancePct` instead of actual/target when
// the backend already did the math (e.g. BSC summary rows).

import { cn } from '@/lib/cn';

export interface VarianceBadgeProps {
  actual?: number;
  target?: number;
  /** Precomputed variance percentage; used when actual/target absent. */
  variancePct?: number;
  /** For KPIs where lower-than-target is favorable (NPL, PAR, Dormancy). */
  invert?: boolean;
  size?: 'sm' | 'md';
  className?: string;
}

function computePct(
  actual?: number, target?: number, variancePct?: number,
): number | null {
  if (variancePct !== undefined && !Number.isNaN(variancePct)) return variancePct;
  if (actual === undefined || target === undefined) return null;
  if (target === 0) return null; // can't express variance against a zero target
  return ((actual - target) / Math.abs(target)) * 100;
}

export function VarianceBadge({
  actual, target, variancePct, invert = false, size = 'md', className,
}: VarianceBadgeProps) {
  const pct = computePct(actual, target, variancePct);

  if (pct === null) {
    return (
      <span className={cn('text-gray-400 font-medium', className)}>—</span>
    );
  }

  // Favorable when the gap points the "good" direction for this KPI.
  const favorable = invert ? pct <= 0 : pct >= 0;
  const sign = pct > 0 ? '+' : ''; // negatives already carry their '−'

  return (
    <span
      className={cn(
        'inline-flex items-center font-semibold tabular-nums',
        size === 'sm' ? 'text-xs' : 'text-sm',
        favorable ? 'text-green-600' : 'text-red-600',
        className,
      )}
    >
      <span aria-hidden="true" className="mr-0.5">
        {favorable ? '▲' : '▼'}
      </span>
      {sign}{pct.toFixed(1)}%
    </span>
  );
}
