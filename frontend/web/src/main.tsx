// v10.495 — React DOM mount point.
//
// This file was missing from the original April-29 scaffolding;
// Vite needs main.tsx (or src/main.ts) to bootstrap the app.
//
// StrictMode runs effects twice in development to catch bugs
// (intentional React 18 behavior — production runs once).

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './index.css';

const rootElement = document.getElementById('root');
if (!rootElement) {
  throw new Error('Root element #root not found in index.html');
}

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
