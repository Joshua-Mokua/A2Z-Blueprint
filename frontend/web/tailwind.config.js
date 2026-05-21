/** @type {import('tailwindcss').Config} */

// v10.495 — Tailwind config for A2Z Blueprint.
// Brand colors are exposed as CSS variables (--brand-primary etc.)
// at runtime by BrandingProvider, which reads them from
// GET /api/branding. This keeps the React code tenant-agnostic.
//
// The Tailwind tokens here reference those CSS variables, so
// utility classes like `bg-brand-primary` resolve to whatever
// color the backend reports. Multi-tenant from day 1.
//
// Fallback values (#1797ce etc.) mirror Ecobank corporate brand
// and only appear briefly before /api/branding resolves on first
// page load (and as a safety net if the backend is down).

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: 'var(--brand-primary, #1797ce)',
          secondary: 'var(--brand-secondary, #0e2440)',
          accent: 'var(--brand-accent, #ffd200)',
        },
      },
      fontFamily: {
        sans: ['system-ui', '-apple-system', 'Segoe UI', 'Roboto',
               'Inter', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
