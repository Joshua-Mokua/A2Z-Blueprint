// v10.496 — Shared component prop types.
//
// Re-export the union types from tokens.ts plus React-specific
// helpers used by multiple components. Keeping these here means
// individual component files import from one place.

export type { Size, Variant, Tone } from '@/lib/tokens';

import type { ReactNode, HTMLAttributes } from 'react';

/**
 * Standard component base props. Most components accept these on
 * top of their specific props. Extends standard HTML div attrs so
 * users can pass arbitrary handlers / aria-* / data-* through.
 */
export interface BaseProps extends Omit<HTMLAttributes<HTMLElement>, 'className'> {
  className?: string;
  children?: ReactNode;
}

/**
 * Props for any component that has a "tone" (success/warning/etc).
 * Used by Badge, Toast, and form-field validation states.
 */
export interface ToneProps {
  tone?: 'success' | 'warning' | 'danger' | 'info' | 'neutral';
}
