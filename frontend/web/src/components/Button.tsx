// v10.496 — Button primitive.
//
// The most-used interactive control. Four variants, three sizes,
// loading state, disabled state, full-width modifier.
//
// VARIANT visual mapping:
//   primary    — solid brand-primary (cyan) bg, white text.
//                Used for the single dominant CTA on a screen.
//   secondary  — solid brand-secondary (navy) bg, white text.
//                Used for second-most important action.
//   ghost      — transparent bg, gray text + border. Used for
//                tertiary actions, "Cancel", filters.
//   danger     — solid semantic-danger red. "Delete", "Cancel deal".
//                Use sparingly. Confirmations only.
//
// Brand colors are consumed via Tailwind's `bg-brand-primary` etc.
// utilities (defined in tailwind.config.js → theme.extend.colors.brand,
// which resolves to CSS vars set by BrandingProvider).
//
// API:
//   <Button variant="primary" size="lg" loading>Save</Button>
//   <Button variant="ghost" onClick={handleCancel}>Cancel</Button>
//   <Button variant="danger" disabled>Delete</Button>

import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/cn';
import type { Size, Variant } from '@/lib/tokens';

export interface ButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'children'> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: 'bg-brand-primary text-white hover:opacity-90 ' +
           'active:opacity-80',
  secondary: 'bg-brand-secondary text-white hover:opacity-90 ' +
             'active:opacity-80',
  ghost: 'bg-transparent text-gray-700 border border-gray-300 ' +
         'hover:bg-gray-50 active:bg-gray-100',
  danger: 'bg-red-600 text-white hover:bg-red-700 active:bg-red-800',
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-4 text-base',
  lg: 'h-12 px-6 text-lg',
};

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  fullWidth = false,
  disabled = false,
  className,
  children,
  ...rest
}: ButtonProps) {
  const isDisabled = disabled || loading;
  return (
    <button
      type="button"
      disabled={isDisabled}
      className={cn(
        // Base
        'inline-flex items-center justify-center gap-2 rounded-md ' +
          'font-medium transition-opacity duration-150 ' +
          'focus:outline-none focus:ring-2 focus:ring-offset-2 ' +
          'focus:ring-brand-primary',
        // Variant
        VARIANT_CLASSES[variant],
        // Size
        SIZE_CLASSES[size],
        // Disabled / loading
        isDisabled && 'opacity-60 cursor-not-allowed',
        // Full width
        fullWidth && 'w-full',
        // User overrides
        className,
      )}
      {...rest}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="inline-block h-4 w-4 animate-spin rounded-full
                     border-2 border-current border-t-transparent"
        />
      )}
      {children}
    </button>
  );
}
