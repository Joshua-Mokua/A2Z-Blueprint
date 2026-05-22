/** @type {import('tailwindcss').Config} */

// v10.497 Phase 0 — Tailwind config extended for shadcn/ui.
// ─────────────────────────────────────────────────────────────────────
// Two color systems coexist:
//
//   1. brand.* (cyan / navy / yellow):
//      Existing v10.495 brand tokens. Tenant-specific, runtime-injected
//      by BrandingProvider via /api/branding. Untouched.
//
//   2. shadcn semantic tokens (background, foreground, primary, etc.):
//      New in v10.497. Read from CSS variables set in src/index.css.
//      Those CSS variables in turn source their values from
//      src/lib/tokens.ts (the G382-enforced single source of non-brand
//      hex). This means shadcn components never hardcode colors —
//      they all flow through the design token system.
//
// Plugin: tailwindcss-animate. Required by shadcn for dialog,
// dropdown, accordion, and sheet animations. No-op for components
// that don't use animations.

import animate from 'tailwindcss-animate';

export default {
  // Dark mode disabled for v10.497. Banking MIS contexts are
  // overwhelmingly day-time desktop use; dark mode is a future batch
  // (post-feature-parity) when it can be tested across all dashboards.
  darkMode: ['class'],

  content: ['./index.html', './src/**/*.{ts,tsx}'],

  theme: {
    extend: {
      // ─── Brand colors (v10.495, unchanged) ───
      // Reference runtime CSS variables; BrandingProvider overrides
      // these on first paint. Tailwind utility: bg-brand-primary, etc.
      colors: {
        brand: {
          primary:   'var(--brand-primary, #1797ce)',
          secondary: 'var(--brand-secondary, #0e2440)',
          accent:    'var(--brand-accent, #ffd200)',
        },

        // ─── shadcn semantic tokens (v10.497) ───
        // Tailwind reads these as `bg-primary`, `text-foreground`, etc.
        // The CSS variables they reference are set in src/index.css
        // and derived from src/lib/tokens.ts.
        border: 'var(--border)',
        input:  'var(--input)',
        ring:   'var(--ring)',

        background: 'var(--background)',
        foreground: 'var(--foreground)',

        primary: {
          DEFAULT:    'var(--primary)',
          foreground: 'var(--primary-foreground)',
        },
        secondary: {
          DEFAULT:    'var(--secondary)',
          foreground: 'var(--secondary-foreground)',
        },
        destructive: {
          DEFAULT:    'var(--destructive)',
          foreground: 'var(--destructive-foreground)',
        },
        muted: {
          DEFAULT:    'var(--muted)',
          foreground: 'var(--muted-foreground)',
        },
        accent: {
          DEFAULT:    'var(--accent)',
          foreground: 'var(--accent-foreground)',
        },
        popover: {
          DEFAULT:    'var(--popover)',
          foreground: 'var(--popover-foreground)',
        },
        card: {
          DEFAULT:    'var(--card)',
          foreground: 'var(--card-foreground)',
        },

        // Chart palette — used by shadcn's chart components (added later)
        chart: {
          1: 'var(--chart-1)',
          2: 'var(--chart-2)',
          3: 'var(--chart-3)',
          4: 'var(--chart-4)',
          5: 'var(--chart-5)',
        },
      },

      // ─── Border radius (drives Card, Button, Input rounded corners) ───
      // shadcn convention: --radius is the base, and components compute
      // sm/md/lg as offsets from it. Keeping that pattern lets us tune
      // the whole UI's "softness" by changing one CSS variable.
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)',
      },

      // ─── Typography (v10.495, unchanged) ───
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto',
               'Inter', 'sans-serif'],
      },

      // ─── shadcn animation keyframes ───
      // Required by Dialog, Dropdown, Accordion, Sheet components.
      // tailwindcss-animate plugin reads these.
      keyframes: {
        'accordion-down': {
          from: { height: '0' },
          to:   { height: 'var(--radix-accordion-content-height)' },
        },
        'accordion-up': {
          from: { height: 'var(--radix-accordion-content-height)' },
          to:   { height: '0' },
        },
      },
      animation: {
        'accordion-down': 'accordion-down 200ms ease-out',
        'accordion-up':   'accordion-up 200ms ease-out',
      },
    },
  },

  plugins: [animate],
};
