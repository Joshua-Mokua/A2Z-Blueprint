// v10.548 Phase P Batch P3b — ChartCard.
//
// Titled card chrome + loading/empty states for any chart. Compose a
// chart inside it:  <ChartCard title="…"><TrendChart …/></ChartCard>

import type { ReactNode } from 'react';
import { Card } from '@/components/Card';
import { EmptyState } from '@/components/EmptyState';

export interface ChartCardProps {
  title: ReactNode;
  subtitle?: ReactNode;
  toolbar?: ReactNode;
  loading?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  height?: number;
  children: ReactNode;
  className?: string;
}

export function ChartCard({
  title, subtitle, toolbar, loading = false, empty = false,
  emptyMessage, height = 260, children, className,
}: ChartCardProps) {
  return (
    <Card padding="md" className={className}>
      <div className="flex items-start justify-between gap-2 mb-3">
        <div>
          <div className="text-sm font-semibold text-brand-secondary">{title}</div>
          {subtitle && <div className="text-xs text-gray-400 mt-0.5">{subtitle}</div>}
        </div>
        {toolbar}
      </div>
      <div style={{ height }}>
        {loading ? (
          <div className="h-full w-full rounded bg-gray-100 animate-pulse" />
        ) : empty ? (
          <EmptyState compact title="No data" message={emptyMessage} />
        ) : (
          children
        )}
      </div>
    </Card>
  );
}
