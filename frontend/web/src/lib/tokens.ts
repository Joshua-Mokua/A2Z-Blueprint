// v10.496 — Canonical design tokens for the A2Z Blueprint UI.
//
// THIS FILE IS THE ONLY PLACE NON-BRAND HEX COLORS ARE PERMITTED.
// G382 (audit gate) enforces this: greys, success-green, danger-red,
// etc. live here and only here. All other component files reference
// these tokens or the brand CSS variables from BrandingProvider.
//
// Brand colors (cyan-blue, deep navy, yellow) are NOT in this file
// — they live in BrandingProvider as CSS variables fetched from
// /api/branding. This separation is intentional:
//   • Brand = tenant-specific (changes per bank deployment)
//   • Tokens = product-wide (greys, semantic colors, spacing,
//     elevations — these never vary by tenant)
//
// When you need a brand color, use the `bg-brand-primary`,
// `text-brand-secondary`, etc. Tailwind classes (defined in
// tailwind.config.js → theme.extend.colors.brand).

// ─────────────────────────────────────────────────────────────────
// Semantic colors — fixed across all tenants
// ─────────────────────────────────────────────────────────────────

export const semantic = {
  // Neutral greys — the workhorse of UI chrome
  gray: {
    50:  '#f9fafb',
    100: '#f3f4f6',
    200: '#e5e7eb',
    300: '#d1d5db',
    400: '#9ca3af',
    500: '#6b7280',
    600: '#4b5563',
    700: '#374151',
    800: '#1f2937',
    900: '#111827',
  },

  // Success — green for "Saved", "Achieved", "On Target"
  success: {
    50:  '#ecfdf5',
    100: '#d1fae5',
    500: '#10b981',
    600: '#059669',
    700: '#047857',
  },

  // Warning — amber for "At Risk", "Behind", "Action Needed"
  warning: {
    50:  '#fffbeb',
    100: '#fef3c7',
    500: '#f59e0b',
    600: '#d97706',
    700: '#b45309',
  },

  // Danger — red for "Failed", "NPL", "Breach"
  danger: {
    50:  '#fef2f2',
    100: '#fee2e2',
    500: '#ef4444',
    600: '#dc2626',
    700: '#b91c1c',
  },

  // Info — neutral blue (NOT brand blue) for informational toasts
  // and badges where brand cyan would compete with actual brand uses
  info: {
    50:  '#eff6ff',
    100: '#dbeafe',
    500: '#3b82f6',
    600: '#2563eb',
    700: '#1d4ed8',
  },
} as const;

// ─────────────────────────────────────────────────────────────────
// Spacing scale — Tailwind-compatible (4px base unit)
// ─────────────────────────────────────────────────────────────────
// We don't actually use this in code (we use Tailwind utility
// classes p-2, m-4, etc.), but it documents the system for any
// hand-written CSS or inline style cases.

export const spacing = {
  0:  '0',
  1:  '4px',
  2:  '8px',
  3:  '12px',
  4:  '16px',
  5:  '20px',
  6:  '24px',
  8:  '32px',
  10: '40px',
  12: '48px',
  16: '64px',
} as const;

// ─────────────────────────────────────────────────────────────────
// Border radius — used by Card, Button, Input, Badge
// ─────────────────────────────────────────────────────────────────

export const radius = {
  none: '0',
  sm:   '4px',
  md:   '6px',
  lg:   '8px',
  xl:   '12px',
  full: '9999px',  // pill shape for badges
} as const;

// ─────────────────────────────────────────────────────────────────
// Elevation (shadows) — used by Card, Toast, Dropdown
// ─────────────────────────────────────────────────────────────────

export const elevation = {
  none: 'none',
  sm:   '0 1px 2px rgba(0,0,0,0.05)',
  md:   '0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04)',
  lg:   '0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.04)',
  xl:   '0 10px 15px rgba(0,0,0,0.08), 0 4px 6px rgba(0,0,0,0.05)',
} as const;

// ─────────────────────────────────────────────────────────────────
// Component sizing — used across Button, Input, Badge
// ─────────────────────────────────────────────────────────────────

export const sizing = {
  // Button + Input heights (px)
  height: {
    sm: 32,
    md: 40,
    lg: 48,
  },
  // Horizontal padding (Tailwind class names)
  px: {
    sm: 'px-3',
    md: 'px-4',
    lg: 'px-6',
  },
  // Font sizes (Tailwind class names)
  text: {
    sm: 'text-sm',
    md: 'text-base',
    lg: 'text-lg',
  },
} as const;

// ─────────────────────────────────────────────────────────────────
// Animation durations
// ─────────────────────────────────────────────────────────────────

export const motion = {
  fast:   '120ms',
  base:   '200ms',
  slow:   '320ms',
  toast:  '4000ms',  // toast auto-dismiss
} as const;

// Type exports for component prop typing
export type Size = 'sm' | 'md' | 'lg';
export type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type Tone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';
