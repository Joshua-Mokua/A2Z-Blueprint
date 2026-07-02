/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // TSquads / Ecobank palette
        eco: {
          blue:   '#0082BB',
          dark:   '#005B82',
          darker: '#00415C',
          lime:   '#BED600',
          dgreen: '#669438',
          bg:     '#EEF2F5',
          gray:   '#464646',
          mgray:  '#979797',
          lgray:  '#EDEDED',
          off:    '#F8F9FA',
        },
        // Legacy brand tokens — still read from CSS vars at runtime via BrandingProvider
        brand: {
          primary:   'var(--brand-primary,   #0082BB)',
          secondary: 'var(--brand-secondary, #005B82)',
          accent:    'var(--brand-accent,    #BED600)',
        },
      },
      fontFamily: {
        sans: ['Quicksand', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      borderRadius: {
        eco:    '20px',
        'eco-m': '16px',
        'eco-s': '12px',
      },
      boxShadow: {
        eco:    '0 4px 24px rgba(0,91,130,.10), 0 1px 4px rgba(0,0,0,.05)',
        'eco-sm': '0 2px 8px rgba(0,91,130,.07)',
        'eco-lg': '0 16px 48px rgba(0,91,130,.14), 0 4px 12px rgba(0,0,0,.06)',
      },
    },
  },
  plugins: [],
};
