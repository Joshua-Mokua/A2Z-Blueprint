// v10.495 — Typed API client for A2Z Blueprint.
//
// Single source for talking to the FastAPI backend. Currently
// only fetches branding; future batches will add /api/auth,
// /api/bsc, etc as the React UI expands.
//
// Uses native fetch with the Vite dev proxy (vite.config.ts)
// transparently forwarding /api/* to localhost:8502. No CORS
// dance required at dev time.

import type { Branding } from '@/types/branding';

const API_BASE = '/api';

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(
      `API ${path} failed: ${res.status} ${res.statusText}`,
    );
  }
  return res.json() as Promise<T>;
}

/**
 * Fetch tenant branding from /api/branding.
 *
 * Returns bank name, app name, brand colors, regulator name,
 * and the IP notice text. Called once on app mount by
 * BrandingProvider.
 */
export async function fetchBranding(): Promise<Branding> {
  return getJson<Branding>('/branding');
}
