// v10.496 — Card primitive.
// v10.510 β1 type fix — Omit native 'title' from extended HTMLAttributes
//   so the bespoke ReactNode title prop type-checks without clashing
//   with the native div title="..." tooltip attribute.
//
// The wrapper for almost every dashboard panel. White background,
// subtle shadow, rounded corners, internal padding. Optional
// header/footer slots, optional brand-color stripe at top
// (used by Stat for KPI tiles).
//
// API:
//   <Card>plain content</Card>
//   <Card title="Pipeline by Stage">...</Card>
//   <Card stripe>...</Card>            ← cyan top border
//   <Card stripe="secondary">...</Card> ← navy top border
//   <Card stripe="accent">...</Card>    ← yellow top border
//
// Composition helpers (Card.Header, Card.Footer) let pages compose
// custom layouts without prop explosion:
//   <Card>
//     <Card.Header>
//       <h3>Title</h3>
//       <Badge tone="success">Live</Badge>
//     </Card.Header>
//     <Card.Body>main content</Card.Body>
//     <Card.Footer>actions row</Card.Footer>
//   </Card>

import type { ReactNode, HTMLAttributes } from 'react';
import { cn } from '@/lib/cn';

type Stripe = boolean | 'primary' | 'secondary' | 'accent';

export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, 'title'> {
  title?: ReactNode;
  stripe?: Stripe;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  children: ReactNode;
}

const PADDING_CLASSES = {
  none: 'p-0',
  sm:   'p-3',
  md:   'p-5',
  lg:   'p-6',
} as const;

function resolveStripeColor(stripe: Stripe | undefined): string | undefined {
  if (!stripe) return undefined;
  if (stripe === true || stripe === 'primary') return 'var(--brand-primary)';
  if (stripe === 'secondary') return 'var(--brand-secondary)';
  if (stripe === 'accent') return 'var(--brand-accent)';
  return undefined;
}

export function Card({
  title,
  stripe,
  padding = 'md',
  className,
  children,
  style,
  ...rest
}: CardProps) {
  const stripeColor = resolveStripeColor(stripe);
  return (
    <div
      className={cn(
        'bg-white rounded-lg shadow-sm border border-gray-200',
        className,
      )}
      style={{
        ...(stripeColor && {
          borderTop: `4px solid ${stripeColor}`,
        }),
        ...style,
      }}
      {...rest}
    >
      {title !== undefined && (
        <div className="px-5 pt-5">
          {typeof title === 'string' ? (
            <h3 className="text-base font-semibold text-gray-900">
              {title}
            </h3>
          ) : (
            title
          )}
        </div>
      )}
      <div className={cn(PADDING_CLASSES[padding])}>
        {children}
      </div>
    </div>
  );
}

// ─── Composition slots ──────────────────────────────────────────

Card.Header = function CardHeader({
  className, children,
}: { className?: string; children: ReactNode }) {
  return (
    <div className={cn(
      'flex items-center justify-between gap-3 ' +
      'border-b border-gray-200 px-5 py-3',
      className,
    )}>
      {children}
    </div>
  );
};

Card.Body = function CardBody({
  className, children,
}: { className?: string; children: ReactNode }) {
  return <div className={cn('px-5 py-4', className)}>{children}</div>;
};

Card.Footer = function CardFooter({
  className, children,
}: { className?: string; children: ReactNode }) {
  return (
    <div className={cn(
      'flex items-center justify-end gap-2 ' +
      'border-t border-gray-200 px-5 py-3',
      className,
    )}>
      {children}
    </div>
  );
};
