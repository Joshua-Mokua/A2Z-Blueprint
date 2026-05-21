// v10.496 — Badge primitive.
//
// Small inline status indicator. Used for:
//   • BSC pillar tags ("Financial", "Customer Focus")
//   • Status labels ("Active", "Pending", "Closed Won")
//   • Risk tone indicators ("High Risk", "Watch")
//
// API:
//   <Badge>Default</Badge>                       ← neutral grey
//   <Badge tone="success">Achieved</Badge>       ← green
//   <Badge tone="warning">At Risk</Badge>        ← amber
//   <Badge tone="danger">NPL</Badge>             ← red
//   <Badge tone="info">New</Badge>               ← blue
//   <Badge tone="brand">v10.495</Badge>          ← brand cyan
//   <Badge size="sm">XS</Badge>
//
// Pill-shaped by default (rounded-full); pass shape="rect" for
// rectangular tags (used in table cells).

import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export type BadgeTone =
  | 'neutral' | 'success' | 'warning' | 'danger' | 'info' | 'brand';

export interface BadgeProps {
  tone?: BadgeTone;
  size?: 'sm' | 'md';
  shape?: 'pill' | 'rect';
  children: ReactNode;
  className?: string;
}

const TONE_CLASSES: Record<BadgeTone, string> = {
  neutral: 'bg-gray-100 text-gray-700 border-gray-200',
  success: 'bg-green-50 text-green-700 border-green-200',
  warning: 'bg-amber-50 text-amber-700 border-amber-200',
  danger:  'bg-red-50 text-red-700 border-red-200',
  info:    'bg-blue-50 text-blue-700 border-blue-200',
  // For brand tone we tint with the CSS var. Inline style — not a
  // Tailwind class — because the var resolves at runtime.
  brand:   '',  // applied via style below
};

const SIZE_CLASSES = {
  sm: 'text-[10px] px-1.5 py-0.5',
  md: 'text-xs px-2 py-0.5',
} as const;

export function Badge({
  tone = 'neutral', size = 'md', shape = 'pill',
  className, children,
}: BadgeProps) {
  const brandStyle = tone === 'brand'
    ? {
        backgroundColor: 'color-mix(in srgb, var(--brand-primary) 12%, white)',
        color: 'var(--brand-secondary)',
        borderColor: 'color-mix(in srgb, var(--brand-primary) 30%, white)',
      }
    : undefined;

  return (
    <span
      className={cn(
        'inline-flex items-center font-medium border',
        shape === 'pill' ? 'rounded-full' : 'rounded',
        SIZE_CLASSES[size],
        TONE_CLASSES[tone],
        className,
      )}
      style={brandStyle}
    >
      {children}
    </span>
  );
}
