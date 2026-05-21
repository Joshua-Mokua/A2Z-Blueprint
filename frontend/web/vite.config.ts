import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// v10.495 — Vite config for A2Z Blueprint React SPA.
//
// Path alias `@/...` lets us write `import { x } from '@/lib/api'`
// instead of `../../lib/api`. Standard React/TS convention.
//
// Dev server proxies /api/* to the FastAPI backend on port 8502
// so the browser hits localhost:5173 for everything and Vite
// transparently forwards API calls. No CORS dance required at
// dev time. Production deployment should put React behind the
// same origin or extend A2Z_CORS_ORIGINS in the FastAPI config.

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8502',
        changeOrigin: true,
      },
    },
  },
});
