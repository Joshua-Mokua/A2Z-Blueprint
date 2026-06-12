// v10.543 Phase P Batch P3a — EmptyState primitive.
//
// The standard "there's nothing here (yet)" panel. Replaces the ad-hoc
// "No results" strings scattered across list pages (CBS search, queues,
// initiatives) with one consistent, calm, centered treatment.
//
// API:
//   <EmptyState title="No customers found" />
//   <EmptyState
//     title="No customers found"
//     message="Try a different name or check the spelling."
//   />
//   <EmptyState
//     title="No pending validations"
//     message="Deals you validate will appear here."
//     icon={<SomeIcon />}
//     action={<Button onClick={...}>Create a deal</Button>}
//   />
//
// `icon` is any ReactNode (an SVG, an emoji span, a lucide icon if the
// project adds one later). Kept dependency-free on purpose.

import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface EmptyStateProps {
  title: ReactNode;
  message?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  /** Tighter vertical padding for inline/in-card use. */
  compact?: boolean;
  className?: string;
}

export function EmptyState({
  title, message, icon, action, compact = false, className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center text-center',
        compact ? 'py-8' : 'py-16',
        className,
      )}
    >
      {icon && (
        <div className="mb-3 text-gray-300 [&>svg]:w-10 [&>svg]:h-10 text-4xl">
          {icon}
        </div>
      )}
      <div className="text-sm font-semibold text-gray-700">{title}</div>
      {message && (
        <div className="mt-1 max-w-sm text-sm text-gray-400">{message}</div>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
