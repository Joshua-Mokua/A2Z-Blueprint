// v10.497 Phase 0 — StatCard (composition over shadcn Card).
// ─────────────────────────────────────────────────────────────────
// Replaces v10.496's bespoke Stat.tsx. The KPI tile pattern stays;
// the foundation is now shadcn Card so we get a single component
// system (doctrine: no architectural entropy).
//
// API (same as v10.496 Stat for migration ease):
//   <StatCard label="Total Deposits" value="KES 1.42T" />
//   <StatCard label="NPL Ratio"      value="11.1%" delta={-0.4} invertDelta />
//   <StatCard label="Active RMs"     value={232}  sub="Target: 250" />
//   <StatCard label="Pipeline"       value="—"    loading />
//   <StatCard label="..." stripe="warning" />
//
// Semantics:
//   - delta = percentage-point change; sign drives color (up=green,
//     down=red). invertDelta swaps the polarity for KPIs where down
//     is good (NPL, CIR, time-to-decision).
//   - stripe = optional left-edge color bar for severity at a glance.
//     "none" (default) | "primary" | "success" | "warning" | "danger"
//   - loading = render placeholder shimmer; for skeleton states
//     during initial data fetch.
//
// Built from: Card + CardHeader + CardContent (shadcn), plus a
// stripe div for the left bar. No bespoke styles beyond the stripe.

import type { ReactNode } from 'react';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/cn';

type Stripe = 'none' | 'primary' | 'success' | 'warning' | 'danger';

export interface StatCardProps {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
  delta?: number;
  /** When true, negative delta = good (e.g. NPL ratio falling). */
  invertDelta?: boolean;
  loading?: boolean;
  /** Left-edge color bar for severity-at-a-glance. */
  stripe?: Stripe;
  className?: string;
}

const stripeClass: Record<Stripe, string> = {
  none:    '',
  primary: 'before:bg-brand-primary',
  success: 'before:bg-emerald-500',
  warning: 'before:bg-amber-500',
  danger:  'before:bg-red-500',
};

function formatDelta(delta: number): string {
  const sign = delta > 0 ? '+' : '';
  return `${sign}${delta.toFixed(1)}`;
}

export function StatCard({
  label, value, sub, delta, invertDelta = false,
  loading = false, stripe = 'primary', className,
}: StatCardProps) {
  // When invertDelta is true (e.g. NPL ratio), down is good.
  const isGood = delta === undefined
    ? null
    : invertDelta ? delta < 0 : delta > 0;
  const isBad = delta === undefined
    ? null
    : invertDelta ? delta > 0 : delta < 0;

  // The stripe is implemented as a ::before pseudo-element so it
  // doesn't affect the card's internal layout. relative + before:
  // gives a 4px-wide bar pinned to the left edge.
  const hasStripe = stripe !== 'none';
  const stripeStyles = hasStripe
    ? cn(
        'relative overflow-hidden',
        "before:content-[''] before:absolute before:left-0 before:top-0 before:bottom-0 before:w-1",
        stripeClass[stripe],
      )
    : '';

  return (
    <Card className={cn(stripeStyles, className)}>
      <CardHeader className="pb-2">
        <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </div>
      </CardHeader>
      <CardContent className="pt-0">
        <div className="flex items-baseline gap-3">
          {loading ? (
            <Skeleton className="h-9 w-24" />
          ) : (
            <span className="text-3xl font-bold text-foreground">
              {value}
            </span>
          )}
          {!loading && delta !== undefined && (
            <span className={cn(
              'inline-flex items-center text-sm font-medium',
              isGood && 'text-emerald-600',
              isBad && 'text-red-600',
              !isGood && !isBad && 'text-muted-foreground',
            )}>
              {isGood && <span aria-hidden="true">↑</span>}
              {isBad && <span aria-hidden="true">↓</span>}
              {formatDelta(delta)}%
            </span>
          )}
        </div>
        {sub && (
          <div className="mt-2 text-xs text-muted-foreground">
            {sub}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
