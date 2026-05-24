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
import type { UserIdentity, RoleRegistry } from '@/types/role';

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

/**
 * Fetch the caller's detailed identity from /api/auth/whoami-detailed.
 *
 * Auth: required (the endpoint sits behind Depends(get_current_user) on
 * the backend). The JWT cookie set at login is sent automatically by
 * the browser; no token-handling code needed here.
 *
 * Returns the full UserIdentity shape: identity fields (username,
 * staff_code, full_name, department, email), role classification (tier,
 * sbu, branch_scope, can_be_tagged), capability flags (is_admin,
 * can_view_all), Streamlit RBAC modules, and token expiry.
 *
 * Called once on RoleProvider mount in parallel with fetchRoleRegistry.
 */
export async function fetchWhoamiDetailed(): Promise<UserIdentity> {
  return getJson<UserIdentity>('/auth/whoami-detailed');
}


/**
 * Fetch the canonical role registry from /api/roles/registry.
 *
 * Auth: required. Returns the system-wide role schema: enum constants
 * (tiers, sbus, scopes) plus an array of 49 explicit role classifications.
 * The registry is system schema, not per-user data — every authenticated
 * user receives the same response.
 *
 * Called once on RoleProvider mount in parallel with fetchWhoamiDetailed.
 */
export async function fetchRoleRegistry(): Promise<RoleRegistry> {
  return getJson<RoleRegistry>('/roles/registry');
}
