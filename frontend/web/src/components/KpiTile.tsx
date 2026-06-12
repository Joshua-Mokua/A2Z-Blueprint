// v10.543 Phase P Batch P3a — KpiTile primitive.
//
// The executive KPI tile: a single metric shown as actual-vs-target with
// variance and RAG status. This is the workhorse of the CEO Dashboard
// (Phase P4) and the BSC scorecard (Perform). Where <Stat> shows a value
// + optional delta, KpiTile is the richer "are we on target?" card.
//
// Composes existing primitives only: Card (stripe) + VarianceBadge +
// RagChip. No new visual vocabulary.
//
// API:
//   <KpiTile
//     label="Profit Before Tax"
//     actual="KES 4.2B"          ← display string (already formatted)
//     target="KES 5.0B"
//     variancePct={-16}
//     status="at_risk"
//   />
//
//   <KpiTile label="NPL Ratio" actual="9.5%" target="11.0%"
//            variancePct={-13.6} invert status="on_track" />
//   <KpiTile label="New Accounts" actual={1820} target={2000} loading />
//
// `actual`/`target` accept ReactNode so callers pass pre-formatted
// currency/percent strings. `variancePct`/`invert` drive the variance
// badge; `status` drives the RAG chip. All optional except label+actual.

import type { ReactNode } from 'react';
import { Card } from '@/components/Card';
import { VarianceBadge } from '@/components/VarianceBadge';
import { RagChip, type RagStatus } from '@/components/RagChip';
import { cn } from '@/lib/cn';

export interface KpiTileProps {
  label: ReactNode;
  actual: ReactNode;
  target?: ReactNode;
  variancePct?: number;
  invert?: boolean;
  status?: RagStatus;
  loading?: boolean;
  stripe?: boolean | 'primary' | 'secondary' | 'accent';
  className?: string;
}

export function KpiTile({
  label, actual, target, variancePct, invert = false,
  status, loading = false, stripe = 'primary', className,
}: KpiTileProps) {
  return (
    <Card stripe={stripe} padding="md" className={className}>
      <div className="flex items-start justify-between gap-2">
        <div className="text-xs font-semibold uppercase tracking-wider text-gray-500">
          {label}
        </div>
        {!loading && status && <RagChip status={status} size="sm" dot />}
      </div>

      <div className="mt-2 flex items-baseline gap-3">
        {loading ? (
          <span className="inline-block h-9 w-28 rounded bg-gray-100 animate-pulse" />
        ) : (
          <span className="text-3xl font-bold text-brand-secondary tabular-nums">
            {actual}
          </span>
        )}
        {!loading && variancePct !== undefined && (
          <VarianceBadge variancePct={variancePct} invert={invert} />
        )}
      </div>

      {!loading && target !== undefined && (
        <div className={cn('mt-2 text-xs text-gray-400')}>
          Target: <span className="font-medium text-gray-500">{target}</span>
        </div>
      )}
    </Card>
  );
}
