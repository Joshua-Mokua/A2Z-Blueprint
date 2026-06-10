// v10.500 Phase 1 Batch 3a — Typed API client.
// v10.510 Phase 4 Batch β1 — extended with pipeline fetchers.
//
// Single source for talking to the FastAPI backend. The Vite dev proxy
// (vite.config.ts) transparently forwards /api/* to localhost:8502 in
// dev; production deployment should put React behind the same origin.
//
// Auth integration (Batch 3a):
//   - AuthProvider calls setCurrentToken(token) on every token-state
//     change. getJson reads from the module-level holder and attaches
//     `Authorization: Bearer <token>` when the token is non-null.
//   - AuthProvider also calls setOn401Callback(fn) on mount. When any
//     authenticated fetch returns 401, getJson invokes the callback
//     before throwing — this is how a server-side expired or invalidated
//     token propagates back into React auth state.
//
// CSRF is intentionally NOT addressed here. The architecture is
// Bearer-header JWT, not cookie-auth, so CSRF is not the threat model
// for Phase 1. CSRF reconsideration is deferred to a future Phase 2
// security arc tied to any httpOnly-cookie migration. See REVIVAL_LEDGER
// Batch 3a doctrine note.

import type { Branding } from '@/types/branding';
import type { UserIdentity, RoleRegistry } from '@/types/role';
import type {
  PipelineDealsListResponse, PipelineDealDetailResponse,
  PipelineDealsQuery,
} from '@/types/pipeline';

const API_BASE = '/api';


// ── Auth integration (module-level holders) ─────────────────────────────
// AuthProvider is the only writer; getJson is the only reader. Keeping
// these at module scope (instead of in a React context) lets api.ts stay
// callable from non-React code paths (e.g. future service workers,
// background sync) without forcing every fetch site to become a hook.

let _currentToken:  string | null              = null;
let _on401Callback: (() => void) | null        = null;

/**
 * Update the JWT used for subsequent authenticated requests. Called by
 * AuthProvider whenever its token state changes (login, logout, expiry).
 * Pass null to clear.
 */
export function setCurrentToken(token: string | null): void {
  _currentToken = token;
}

/**
 * Register a callback fired when any authenticated request returns 401.
 * Called once by AuthProvider on mount; passes null on unmount.
 */
export function setOn401Callback(callback: (() => void) | null): void {
  _on401Callback = callback;
}


// ── Typed error for auth-expiry detection at fetch sites ────────────────
// Distinct from generic Error so callers (e.g. RoleProvider) can decide
// whether to treat the failure as transient or as auth-state change.

export class AuthExpiredError extends Error {
  constructor(public readonly path: string) {
    super(`Authentication expired or invalid (path: ${path})`);
    this.name = 'AuthExpiredError';
  }
}


// ── Central JSON fetch wrapper ──────────────────────────────────────────
// Attaches Authorization header when a token is registered. Invokes the
// 401 callback before throwing so AuthProvider state flips synchronously
// with the failure. Other non-OK responses throw a generic Error.

async function getJson<T>(path: string): Promise<T> {
  const headers: Record<string, string> = {};
  if (_currentToken) {
    headers['Authorization'] = `Bearer ${_currentToken}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { headers });

  if (res.status === 401) {
    // Notify AuthProvider BEFORE throwing — synchronous invocation
    // ensures the React state transition (authenticated → expired) is
    // queued in the same task as the failed request.
    if (_on401Callback) _on401Callback();
    throw new AuthExpiredError(path);
  }
  if (!res.ok) {
    throw new Error(
      `API ${path} failed: ${res.status} ${res.statusText}`,
    );
  }
  return res.json() as Promise<T>;
}


// ── Public endpoint fetchers ────────────────────────────────────────────

/**
 * Fetch tenant branding from /api/branding.
 *
 * Auth: NOT required (endpoint is public per utils/api_branding.py:11 —
 * the login page needs branding before authentication). Returns bank
 * name, app name, brand colors, regulator name, and the IP notice text.
 * Called once on app mount by BrandingProvider.
 */
export async function fetchBranding(): Promise<Branding> {
  return getJson<Branding>('/branding');
}


// ── Authenticated endpoint fetchers ─────────────────────────────────────

/**
 * Fetch the caller's detailed identity from /api/auth/whoami-detailed.
 *
 * Auth: REQUIRED (Depends(get_current_user) at utils/api.py:328). The
 * Authorization: Bearer header is attached automatically from the
 * current token registered by AuthProvider.
 *
 * Returns the full UserIdentity shape: identity fields (username,
 * staff_code, full_name, department, email), role classification (tier,
 * sbu, branch_scope, can_be_tagged), capability flags (is_admin,
 * can_view_all), Streamlit RBAC modules, and token expiry.
 *
 * Called by RoleProvider once auth.status === 'authenticated'.
 */
export async function fetchWhoamiDetailed(): Promise<UserIdentity> {
  return getJson<UserIdentity>('/auth/whoami-detailed');
}


/**
 * Fetch the canonical role registry from /api/roles/registry.
 *
 * Auth: REQUIRED (Depends(get_current_user) at utils/api_roles.py:51).
 * Returns system-wide role schema: enum constants (tiers/sbus/scopes)
 * plus the array of explicit role classifications. The registry is
 * system schema, not per-user data — every authenticated user receives
 * the same response.
 *
 * Called by RoleProvider in parallel with fetchWhoamiDetailed once
 * auth.status === 'authenticated'.
 */
export async function fetchRoleRegistry(): Promise<RoleRegistry> {
  return getJson<RoleRegistry>('/roles/registry');
}


// ── Pipeline endpoint fetchers (v10.510 Phase 4 Batch β1) ───────────────
//
// Consumes the FastAPI pipeline domain surface built in Arc α (α1-α7).
// Cascade scoping is applied server-side; each deal carries a per-caller
// permissions object that the React UI uses to decide button rendering.
// No client-side authorization logic — the API tells us what's allowed.


/**
 * Fetch the cascade-scoped list of pipeline deals from /api/pipeline/deals.
 *
 * Auth: REQUIRED. Server applies the caller's cascade visibility — a
 * teller sees only own deals; a branch manager sees branch deals; an
 * admin sees everything. (α2 / G395.)
 *
 * Each returned deal carries a `permissions` object (α7 / G400) with
 * 6 booleans the React UI reads to decide which actions to render.
 *
 * Filter params (all optional):
 *   stage    — exact-match filter on deal.stage
 *   category — pipeline category (Loans / Accounts / Deposits)
 *   unit     — organizational unit filter
 *   offset, limit — server-side pagination
 */
export async function fetchPipelineDeals(
  query: PipelineDealsQuery = {},
): Promise<PipelineDealsListResponse> {
  const params = new URLSearchParams();
  if (query.stage)    params.set('stage',    query.stage);
  if (query.category) params.set('category', query.category);
  if (query.unit)     params.set('unit',     query.unit);
  if (query.offset !== undefined) params.set('offset', String(query.offset));
  if (query.limit  !== undefined) params.set('limit',  String(query.limit));
  const qs = params.toString();
  const path = qs ? `/pipeline/deals?${qs}` : '/pipeline/deals';
  return getJson<PipelineDealsListResponse>(path);
}


/**
 * Fetch a single deal by id from /api/pipeline/deals/{deal_id}.
 *
 * Auth: REQUIRED. Returns 404 (not 403) when the deal exists but is
 * outside the caller's cascade scope — deliberate to avoid leaking
 * deal existence (α7 / G400 design decision).
 *
 * Response shape differs from the list: the deal is at `response.deal`
 * and permissions live at `response.permissions` (not embedded in deal).
 */
export async function fetchPipelineDealDetail(
  dealId: string,
): Promise<PipelineDealDetailResponse> {
  return getJson<PipelineDealDetailResponse>(
    `/pipeline/deals/${encodeURIComponent(dealId)}`,
  );
}
