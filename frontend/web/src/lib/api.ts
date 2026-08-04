// v10.500 Phase 1 Batch 3a — Typed API client.
// v10.510 Phase 4 Batch β1 — extended with pipeline fetchers.
// v10.511 Phase 4 Batch β2 — extended with postJson + pipeline mutations.
// v10.512 Phase 4 Batch β3 — extended with create + refer mutations.
// v10.513 Phase 4 Batch β4 — extended with manager queues + validate +
//                              cancel-approve mutations.
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
  PipelineConfig,
  AdvanceDealRequest, AdvanceDealResponse,
  RequestCancelRequest, RequestCancelResponse,
  CreateDealRequest, CreateDealResponse,
  ReferDealRequest, ReferDealResponse,
  ValidationQueueResponse, CancellationQueueResponse,
  ValidateDealRequest, ValidateDealResponse,
  ApproveCancelRequest, ApproveCancelResponse,
  CreditChecklistResponse, SubmitToCreditResponse,
  PipelineAnalyticsResponse,
  PipelineDrillResponse,
  FunnelDrillResponse,
  DealCategoryConfig,
} from '@/types/pipeline';
import type {
  CreditAnalyticsResponse,
  CreditDrillResponse,
} from '@/types/creditAnalytics';
import type { ExceptionsResponse } from '@/types/exceptions';

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
let _blobTokenRef: string | null = null;
export function getCurrentTokenForBlob(): string | null { return _blobTokenRef; }
export function setCurrentToken(token: string | null): void {
  _currentToken = token;
  _blobTokenRef = token;
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

export interface PortfolioAccount { account_number: string; cif: string; account_type_name: string; current_balance: number; available_balance: number; account_status: string; dormancy_status: string; npl_status: string; branch_code: string; introducer_code?: string; relationship_manager_code?: string; managed_by_code?: string; managed_by_name?: string; }
export interface PortfolioSummary { accounts: number; customers: number; total_balance: number; deposits: number; loans: number; dormant_accounts: number; dormant_pct: number; npl_accounts: number; by_type: { type: string; count: number; balance: number }[]; deposit_movement: { baseline: number; current: number; delta: number; pct: number | null } | null; baseline_date: string | null; pipeline_deposits: number; pipeline_loans: number; pipeline_value: number; }
export interface PortfolioTeamMember { staff_code: string; name: string; }
export interface PortfolioResponse { rm_code: string; accounts: PortfolioAccount[]; summary: PortfolioSummary; introduced?: { accounts: PortfolioAccount[]; summary: PortfolioSummary } | null; team: PortfolioTeamMember[]; view: string; selected: string; is_manager: boolean; branch_unallocated?: { accounts: number; deposits: number; loans: number; branch_codes: string[] } | null; }
export async function fetchMyPortfolio(staffCode = ''): Promise<PortfolioResponse> {
  const q = staffCode ? `?staff_code=${encodeURIComponent(staffCode)}` : '';
  return getJson<PortfolioResponse>(`/cbs/portfolio${q}`);
}

export async function getJson<T>(path: string): Promise<T> {
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


// ── Authenticated binary download (xlsx / pdf / pptx exports) ───────────
// Mirrors getJson's auth-header + 401 handling, but streams the response as
// a Blob and triggers a browser download with the server-provided filename.
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  const headers: Record<string, string> = {};
  if (_currentToken) headers['Authorization'] = `Bearer ${_currentToken}`;
  const res = await fetch(`${API_BASE}${path}`, { headers });
  if (res.status === 401) {
    if (_on401Callback) _on401Callback();
    throw new AuthExpiredError(path);
  }
  if (!res.ok) throw new Error(`Export ${path} failed: ${res.status} ${res.statusText}`);

  // Prefer the filename from Content-Disposition when present.
  let filename = fallbackName;
  const cd = res.headers.get('Content-Disposition') || '';
  const m = /filename="?([^"]+)"?/.exec(cd);
  if (m && m[1]) filename = m[1];

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


// ── Central JSON POST/PUT wrapper (v10.511 Phase 4 Batch β2) ────────────
// Mirrors getJson semantics — same auth header injection, same 401
// callback dispatch — but for write operations. Body is JSON-serialized
// from the second argument. The method defaults to POST; pass 'PUT' for
// update operations.
//
// Error handling shape:
//   - 401: dispatch on401, throw AuthExpiredError (same as getJson)
//   - 400 with JSON body containing `detail`: throw Error with the
//     server's detail message (so the UI can show "Reason too short"
//     rather than a generic "Bad Request")
//   - 403/404/5xx: throw Error with status code + statusText
//
// The 400-with-detail handling is load-bearing for β2's UX. The
// FastAPI HTTPException machinery returns {"detail": "..."} on
// validation failure; surfacing that detail to the user is what
// makes the form interactions feel responsive.

export class ApiValidationError extends Error {
  constructor(public readonly detail: string, public readonly status: number) {
    super(detail);
    this.name = 'ApiValidationError';
  }
}

async function postJson<TResponse, TBody = unknown>(
  path: string,
  body: TBody,
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'POST',
): Promise<TResponse> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  };
  if (_currentToken) {
    headers['Authorization'] = `Bearer ${_currentToken}`;
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: JSON.stringify(body),
  });

  if (res.status === 401) {
    if (_on401Callback) _on401Callback();
    throw new AuthExpiredError(path);
  }

  if (res.status === 400 || res.status === 422) {
    // Try to extract the server's detail message
    let detail = `Validation failed (${res.status})`;
    try {
      const errBody = await res.json();
      if (errBody && typeof errBody.detail === 'string') {
        detail = errBody.detail;
      } else if (errBody && Array.isArray(errBody.detail)) {
        // Pydantic 422 errors come as array of {loc, msg, type}
        const first = errBody.detail[0];
        if (first && first.msg) detail = String(first.msg);
      }
    } catch { /* keep default */ }
    throw new ApiValidationError(detail, res.status);
  }

  if (!res.ok) {
    throw new Error(
      `API ${path} failed: ${res.status} ${res.statusText}`,
    );
  }

  return res.json() as Promise<TResponse>;
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
 * Fetch the admin-configured pipeline config (categories, stages, sectors,
 * decision levels) from /api/pipeline/stages. Single source for the filter
 * + create-form dropdowns so the UI matches the bank's configured workflow.
 */
export async function fetchPipelineConfig(): Promise<PipelineConfig> {
  return getJson<PipelineConfig>('/pipeline/stages');
}

/** Editable reference-config slice returned by the admin write endpoint. */
export interface AdminConfigPatch {
  segment_labels?:     Record<string, string>;
  customer_segments?:  Record<string, string[]>;
  client_types?:       { key: string; label: string; field: 'mou' | 'sector' }[];
  product_catalogue?:  Record<string, string[]>;
  individual_mous?:    { id: string; title: string; partner_name?: string; active?: boolean }[];
  business_sectors?:   string[];
  sectors?:            string[];
  required_fields?:    string[];
  allow_other_sector?: boolean;
  allow_other_mou?:    boolean;
  deal_categories?:    DealCategoryConfig[];
}
export interface AdminConfigResponse {
  status: 'saved' | 'noop';
  applied: string[];
  config: AdminConfigPatch;
}

/** PATCH reference config (CEO/MD only — gated server-side by require_config_admin). */
export async function updatePipelineConfig(patch: AdminConfigPatch): Promise<AdminConfigResponse> {
  return postJson<AdminConfigResponse, AdminConfigPatch>('/admin/pipeline-config', patch);
}

/** SW-1 — admin branches / regions panel. */
export interface AdminBranch {
  id?: string; name: string; region?: string; area_name?: string;
  branch_code?: string; active?: boolean;
}
export async function getAdminBranches(): Promise<{ branches: AdminBranch[]; regions: string[]; areas: string[] }> {
  return getJson<{ branches: AdminBranch[]; regions: string[]; areas: string[] }>('/admin/branches');
}
export async function saveAdminBranches(branches: AdminBranch[]): Promise<{ status: string; added: number; updated: number; branches: AdminBranch[] }> {
  return postJson<{ status: string; added: number; updated: number; branches: AdminBranch[] }, { branches: AdminBranch[] }>('/admin/branches', { branches });
}

/** Add / edit / deactivate a single MOU in the partnership register
 * (CEO/MD only). Add: pass partner_name (+ optional mou_type/department) with no
 * id. Deactivate: pass the id with status 'Inactive'. Writes the file the deal
 * picker reads, so a newly added partner is immediately selectable. */
export interface MouUpsertInput {
  id?: string;
  partner_name?: string;
  mou_type?: string;
  department?: string;
  status?: 'Active' | 'Inactive';
}
export interface MouUpsertResponse {
  status: 'saved';
  mou: { id: string; title: string; partner_name: string; status: string };
  active_count: number;
  total: number;
}
export async function upsertMou(input: MouUpsertInput): Promise<MouUpsertResponse> {
  return postJson<MouUpsertResponse, MouUpsertInput>('/admin/mous', input);
}

/** Author one product's process flow (CEO/MD only). Pass `product` plus its
 * ordered `stages` (each {stage, target_days}) and the `client_types` that offer
 * it (empty = all). Pass `delete: true` with a `product` to revert it to its
 * class flow. Writes pipeline_settings.product_flows; the deal form picks it up. */
export interface ProductFlowStageInput { stage: string; target_days: number; }
export interface ProductFlowUpsertInput {
  product: string;
  stages?: ProductFlowStageInput[];
  client_types?: string[];
  required_documents?: string[];
  documents_required_at_stage?: string;
  committee_journey?: string[];
  delete?: boolean;
}
export interface ProductFlowUpsertResponse {
  status: 'saved';
  product?: string;
  flow?: { client_types: string[]; stages: ProductFlowStageInput[] };
  deleted?: string;
  total: number;
}
export async function upsertProductFlow(
  input: ProductFlowUpsertInput,
): Promise<ProductFlowUpsertResponse> {
  return postJson<ProductFlowUpsertResponse, ProductFlowUpsertInput>('/admin/product-flows', input);
}


// ── Role registry (admin) ────────────────────────────────────────────────
// The full role-definition registry (kpi_library.json -> role_kpis): every
// role with its KPI count, resolved pillar mix, and capabilities. Distinct
// from `RoleRegistry` in types/role.ts, which is the RBAC tier registry.

export interface AdminRoleRow {
  role: string;
  kpi_count: number;
  pillars: Record<string, number>;
  can_disburse: boolean;
}

export interface AdminRolesResponse {
  roles: AdminRoleRow[];
  count: number;
  disbursement_roles: string[];
}

export interface AdminRoleKpi {
  ref: string | number;
  id?: string;
  name?: string;
  pillar?: string;
  weight?: number;
  mapped: boolean;
}

export interface AdminRoleDetailResponse {
  role: string;
  kpis: AdminRoleKpi[];
  kpi_count: number;
  unmapped: number;
  can_disburse: boolean;
}

export interface RoleCapabilityResponse {
  role: string;
  can_disburse: boolean;
  disbursement_roles: string[];
}

/** Full role registry — config-admin only (server-gated). */
export async function fetchAdminRoles(): Promise<AdminRolesResponse> {
  return getJson<AdminRolesResponse>('/admin/roles');
}

/** One role's resolved KPI breakdown + capabilities. */
export async function fetchAdminRoleDetail(role: string): Promise<AdminRoleDetailResponse> {
  return getJson<AdminRoleDetailResponse>(`/admin/role-detail?role=${encodeURIComponent(role)}`);
}

/** Grant/revoke a role's disbursement capability. */
export async function setRoleCapability(
  role: string, canDisburse: boolean,
): Promise<RoleCapabilityResponse> {
  return postJson<RoleCapabilityResponse, { role: string; can_disburse: boolean }>(
    '/admin/roles/capabilities', { role, can_disburse: canDisburse });
}


// ── Referral inbox / lifecycle (refer-existing-deal flow) ────────────────
// Distinct from referPipelineDeal above (the legacy create-referral-deal
// endpoint). These drive the Incoming / Returned / Following inbox.

export interface ReferralView {
  id: string;
  client_name?: string;
  deal_value?: number;
  amount_kes?: number;   // KES-equivalent; display this, not native deal_value
  product_type?: string;
  stage?: string;
  segment?: string;
  referral_status?: string;
  referred_to?: string;
  referred_to_code?: string;
  referred_by_name?: string;
  referred_by_code?: string;
  referral_note?: string;
  decline_reason?: string;
  referred_at?: string;
  accepted_at?: string;
  declined_at?: string;
  referral_tier?: 'B2B' | 'S2B';
  cross_unit?: boolean;
  referrer_department?: string | null;
  recipient_department?: string | null;
  referral_chain?: Array<{
    seq: number; from_code?: string; from_name?: string; from_dept?: string;
    to_code?: string; to_name?: string; to_dept?: string; note?: string;
    at?: string; status?: string; resolved_at?: string; decline_reason?: string;
  }>;
  credit_stage?: { key: string; label: string; status: string; declined: boolean } | null;
}

export interface ReferralListResponse {
  deals: ReferralView[];
  count: number;
}

/** Pending referrals addressed to the caller (accept / decline). */
export async function fetchIncomingReferrals(): Promise<ReferralListResponse> {
  return getJson<ReferralListResponse>('/pipeline/referrals/incoming');
}

/** Declined referrals the caller made (reassign pool). */
export async function fetchReturnedReferrals(): Promise<ReferralListResponse> {
  return getJson<ReferralListResponse>('/pipeline/referrals/returned');
}

/** Live referrals the caller made — pending + accepted (follow progress). */
export async function fetchOutgoingReferrals(): Promise<ReferralListResponse> {
  return getJson<ReferralListResponse>('/pipeline/referrals/outgoing');
}

export interface ReferralAlert {
  id?: string;
  client_name?: string;
  referred_to?: string;
  kind: string;
  days?: number;
  message: string;
}

export interface OutgoingReferralAnalytics {
  total: number;
  by_status: { pending: number; accepted: number; declined: number };
  by_stage: Record<string, number>;
  closed: { won: number; lost: number };
  alerts: ReferralAlert[];
  alert_count: number;
}

export async function fetchOutgoingReferralAnalytics(): Promise<OutgoingReferralAnalytics> {
  return getJson<OutgoingReferralAnalytics>('/pipeline/referrals/outgoing/analytics');
}

export interface ReferralDepartmentRow {
  department: string;
  total: number;
  by_status: { pending: number; accepted: number; declined: number };
  closed: { won: number; lost: number };
}

export interface ReferralsByDepartment {
  departments: ReferralDepartmentRow[];
  total: number;
  department_count: number;
  scope?: string;
}

export async function fetchReferralsByDepartment(): Promise<ReferralsByDepartment> {
  return getJson<ReferralsByDepartment>('/pipeline/referrals/analytics/by-department');
}

export interface TeamReferralsResponse {
  deals: ReferralView[];
  count: number;
  summary: {
    total: number;
    by_status: { pending: number; accepted: number; declined: number };
    by_tier: { B2B: number; S2B: number };
    closed: { won: number; lost: number };
  };
}

export async function fetchTeamReferrals(): Promise<TeamReferralsResponse> {
  return getJson<TeamReferralsResponse>('/pipeline/referrals/team');
}

// ── SLA (Phase 4 S1/S2) ──────────────────────────────────────────────
export interface SlaStep { key: string; label: string; owner_role: string; target_days: number; }
export interface SlaTier { after_days: number; escalate_to: string; }
export interface SlaConfig {
  steps: SlaStep[];
  escalation_ladder: SlaTier[];
  product_promise: Record<string, number>;
  due_soon_days?: number;
  stage_step_map?: Record<string, string>;
}
export async function fetchSlaConfig(): Promise<{ sla_config: SlaConfig; is_default: boolean }> {
  return getJson<{ sla_config: SlaConfig; is_default: boolean }>('/admin/sla-config');
}
export async function saveSlaConfig(cfg: SlaConfig): Promise<{ status: string; sla_config: SlaConfig }> {
  return postJson<{ status: string; sla_config: SlaConfig }, { sla_config: SlaConfig }>(
    '/admin/sla-config', { sla_config: cfg });
}

export interface SlaCommitment {
  reason: string;
  committed_date: string;
  recorded_by?: string;
  recorded_by_name?: string;
  recorded_at?: string;
}
export interface SlaViolation {
  deal_id: string;
  client_name?: string;
  product_type?: string | null;
  stage?: string;
  owner_code?: string;
  clock: 'step' | 'age';
  step?: string | null;
  elapsed_business_days: number;
  target_days: number;
  remaining_business_days?: number;
  overdue_business_days: number;
  breached: boolean;
  state?: 'on_track' | 'due_soon' | 'breached';
  escalate_to?: string | null;
  commitment?: SlaCommitment | null;
  commitment_status?: 'active' | 'unfulfilled' | null;
}
export interface SlaViolations {
  violations: SlaViolation[];
  count: number;
  open_deals: number;
  by_escalation: Record<string, number>;
  by_clock: { step: number; age: number };
  by_step?: Record<string, number>;
  by_state?: { on_track: number; due_soon: number; breached: number };
}
export async function fetchSlaViolations(): Promise<SlaViolations> {
  return getJson<SlaViolations>('/pipeline/sla/violations');
}
export async function fetchDealSla(dealId: string): Promise<{ deal_id: string; sla: SlaViolation | null }> {
  return getJson<{ deal_id: string; sla: SlaViolation | null }>(`/pipeline/deals/${dealId}/sla`);
}
export async function recordSlaCommitment(
  dealId: string, reason: string, committedDate: string,
): Promise<{ deal_id: string; step: string; commitment: SlaCommitment }> {
  return postJson<
    { deal_id: string; step: string; commitment: SlaCommitment },
    { reason: string; committed_date: string }
  >(`/pipeline/deals/${dealId}/sla/commitment`, { reason, committed_date: committedDate });
}

export async function acceptReferral(dealId: string): Promise<{ status?: string }> {
  return postJson<{ status?: string }, Record<string, never>>(
    `/pipeline/deals/${dealId}/referral/accept`, {});
}

export async function reReferReferral(dealId: string, referredToCode: string, referredTo: string, note?: string): Promise<{ referral_status?: string }> {
  return postJson<{ referral_status?: string }, { referred_to_code: string; referred_to: string; note?: string }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/referral/re-refer`,
    { referred_to_code: referredToCode, referred_to: referredTo, note });
}
export async function declineReferral(dealId: string, reason: string): Promise<{ status?: string }> {
  return postJson<{ status?: string }, { reason: string }>(
    `/pipeline/deals/${dealId}/referral/decline`, { reason });
}

// ── Phase V: line-manager validation requests (reopen / hold) ──────────
export interface ValidationRequest {
  id: string;
  kind: 'reopen' | 'hold';
  requested_by?: string;
  requested_by_name?: string;
  reason?: string;
  at?: string;
  status: 'pending' | 'approved' | 'rejected';
  validator_code?: string | null;
  validator_name?: string | null;
  validator_role?: string | null;
  admin_fallback?: boolean;
  validated_by?: string | null;
  validated_by_name?: string | null;
  validated_at?: string | null;
  note?: string | null;
}

export async function createValidationRequest(
  dealId: string, kind: 'reopen' | 'hold', reason: string,
): Promise<ValidationRequest> {
  return postJson<ValidationRequest, { kind: string; reason: string }>(
    `/pipeline/deals/${dealId}/validation-requests`, { kind, reason });
}

export async function resolveValidationRequest(
  dealId: string, reqId: string, decision: 'approved' | 'rejected', note: string,
): Promise<ValidationRequest> {
  return postJson<ValidationRequest, { decision: string; note: string }>(
    `/pipeline/deals/${dealId}/validation-requests/${reqId}/resolve`, { decision, note });
}

export async function liftDealHold(dealId: string, note: string): Promise<{ deal_id: string; on_hold: boolean }> {
  return postJson<{ deal_id: string; on_hold: boolean }, { note: string }>(
    `/pipeline/deals/${dealId}/unhold`, { note });
}

export async function fetchDealJourney(dealId: string): Promise<{ journey: LoanAppHistoryEvent[]; linked_application_id: string | null }> {
  return getJson<{ journey: LoanAppHistoryEvent[]; linked_application_id: string | null }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/journey`);
}

// ── Daily Branch Log ───────────────────────────────────────────
export interface BranchLogField { key: string; label: string; type: string; unit: string; bsc_kpi: string | null; weight?: number; }
export interface BranchLogEntry {
  id: string; log_date: string; staff_code: string; staff_name: string; unit: string; role: string;
  submitted_at?: string; updated_at?: string; validated?: boolean; rejected?: boolean;
  validated_by?: string; validated_at?: string; manager_note?: string; remarks?: string;
  [metric: string]: unknown;
}
export async function fetchBranchLogFields(): Promise<{ fields: BranchLogField[] }> {
  return getJson<{ fields: BranchLogField[] }>('/branch-log/fields');
}

export interface BranchLogActivity { at: string; time: string; kind: string; detail: string; }
export async function fetchBranchLogAutoActivities(): Promise<{ activities: BranchLogActivity[]; date: string }> {
  return getJson<{ activities: BranchLogActivity[]; date: string }>('/branch-log/auto-activities');
}

export interface BranchLogConfig { activity_weights: Record<string, number>; daily_index_target: number; fields: BranchLogField[]; }
export async function fetchBranchLogConfig(): Promise<BranchLogConfig> {
  return getJson<BranchLogConfig>('/branch-log/config');
}
export async function saveBranchLogConfig(activity_weights: Record<string, number>, daily_index_target: number): Promise<{ status: string }> {
  return postJson<{ status: string }, { activity_weights: Record<string, number>; daily_index_target: number }>(
    '/branch-log/config', { activity_weights, daily_index_target });
}
export interface ExtraActivity { key: string; label: string; type: string; unit: string; weight: number; roles: string[]; }
export async function fetchBranchLogActivities(): Promise<{ base: BranchLogField[]; extra: ExtraActivity[] }> {
  return getJson<{ base: BranchLogField[]; extra: ExtraActivity[] }>('/branch-log/activities');
}
export async function saveBranchLogActivities(extra_activities: ExtraActivity[]): Promise<{ status: string }> {
  return postJson<{ status: string }, { extra_activities: ExtraActivity[] }>('/branch-log/activities', { extra_activities });
}
export interface BranchLogRankRow { rank: number; staff_code: string; staff_name: string; unit: string; index: number; days: number; avg_per_day: number; target: number; }
export async function fetchBranchLogRanking(days = 30): Promise<{ ranking: BranchLogRankRow[]; days: number; daily_index_target: number }> {
  return getJson<{ ranking: BranchLogRankRow[]; days: number; daily_index_target: number }>(`/branch-log/ranking?days=${days}`);
}
export async function fetchMyBranchLogs(days = 14): Promise<{ logs: BranchLogEntry[]; identity: Record<string, string> }> {
  return getJson<{ logs: BranchLogEntry[]; identity: Record<string, string> }>(`/branch-log/mine?days=${days}`);
}
export async function fetchPendingBranchLogs(): Promise<{ logs: BranchLogEntry[] }> {
  return getJson<{ logs: BranchLogEntry[] }>('/branch-log/pending');
}
export async function submitBranchLog(values: Record<string, number | string>): Promise<{ log: BranchLogEntry }> {
  return postJson<{ log: BranchLogEntry }, { values: Record<string, number | string> }>('/branch-log', { values });
}
export async function validateBranchLog(logId: string, approved: boolean, note: string): Promise<{ log: BranchLogEntry }> {
  return postJson<{ log: BranchLogEntry }, { approved: boolean; note: string }>(
    `/branch-log/${encodeURIComponent(logId)}/validate`, { approved, note });
}


export async function reassignReferral(
  dealId: string, code: string, name: string, note: string,
): Promise<{ status?: string }> {
  return postJson<{ status?: string },
    { referred_to_code: string; referred_to_name: string; referral_note: string }>(
    `/pipeline/deals/${dealId}/referral/reassign`,
    { referred_to_code: code, referred_to_name: name, referral_note: note });
}


// ── Staff picker (referral recipient) ────────────────────────────────────

export interface StaffMember {
  staff_code: string;
  name: string;
  role?: string;
  unit?: string;
  region?: string;
  segment?: string;
}

export interface StaffSearchResponse {
  staff: StaffMember[];
  count: number;
}

export interface StaffSegment {
  segment: string;
  count: number;
}

export interface StaffSegmentsResponse {
  segments: StaffSegment[];
  count: number;
}

/** Distinct staff segments (Department) for the picker's first step. */
export async function fetchStaffSegments(): Promise<StaffSegmentsResponse> {
  return getJson<StaffSegmentsResponse>('/staff/segments');
}

/** Search the roster, optionally within one segment. */
export async function searchStaff(q: string, segment: string, branch?: string): Promise<StaffSearchResponse> {
  const params = new URLSearchParams();
  if (q) params.set('q', q);
  if (segment) params.set('segment', segment);
  if (branch) params.set('branch', branch);
  const qs = params.toString();
  return getJson<StaffSearchResponse>(`/staff/search${qs ? `?${qs}` : ''}`);
}

export interface ReferExistingResponse {
  status?: string;
  referred_to?: string;
  referred_to_code?: string;
}

/** Refer an EXISTING deal to a chosen recipient (-> pending). */
export async function referExistingDeal(
  dealId: string,
  body: { referred_to_code: string; referred_to_name: string; referral_note: string },
): Promise<ReferExistingResponse> {
  return postJson<ReferExistingResponse,
    { referred_to_code: string; referred_to_name: string; referral_note: string }>(
    `/pipeline/deals/${dealId}/refer`, body);
}


// ── CBS portfolio owner (mapped relationship manager) ────────────────────

export interface CustomerPortfolioOwner {
  cif: string;
  customer_name: string;
  is_mapped: boolean;
  portfolio_owner_code: string | null;
  portfolio_owner_name: string | null;
  owner_in_roster: boolean;
  relationship_manager_code: string;
}

/** Resolve the portfolio owner (relationship manager) mapped to a CIF. */
export async function fetchCustomerPortfolioOwner(cif: string): Promise<CustomerPortfolioOwner> {
  return getJson<CustomerPortfolioOwner>(
    `/cbs/customers/${encodeURIComponent(cif)}/portfolio-owner`);
}


/**
 * Fetch pipeline analytics from /api/pipeline/analytics — validated/pending
 * value split, per-class buckets (asset/liability/insurance/other), the
 * validated funnel, and the scope-aware pending-validation count.
 */
export async function fetchPipelineAnalytics(): Promise<PipelineAnalyticsResponse> {
  return getJson<PipelineAnalyticsResponse>('/pipeline/analytics');
}

export async function fetchPipelineDrill(
  unit?: string, rm?: string,
): Promise<PipelineDrillResponse> {
  const p = new URLSearchParams();
  if (unit) p.set('unit', unit);
  if (rm) p.set('rm', rm);
  const qs = p.toString();
  return getJson<PipelineDrillResponse>(`/pipeline/drill${qs ? `?${qs}` : ''}`);
}

export async function fetchFunnelDrill(
  cls: string, stage: string,
): Promise<FunnelDrillResponse> {
  const p = new URLSearchParams();
  p.set('cls', cls || 'all');
  if (stage) p.set('stage', stage);
  return getJson<FunnelDrillResponse>(`/pipeline/funnel/drill?${p.toString()}`);
}

export async function fetchCreditAnalytics(): Promise<CreditAnalyticsResponse> {
  return getJson<CreditAnalyticsResponse>('/credit/analytics');
}

export async function fetchDashboardExceptions(): Promise<ExceptionsResponse> {
  return getJson<ExceptionsResponse>('/dashboard/exceptions');
}

export async function fetchCreditDrill(
  region?: string, branch?: string, rm?: string,
): Promise<CreditDrillResponse> {
  const p = new URLSearchParams();
  if (region) p.set('region', region);
  if (branch) p.set('branch', branch);
  if (rm) p.set('rm', rm);
  const qs = p.toString();
  return getJson<CreditDrillResponse>(`/credit/drill${qs ? `?${qs}` : ''}`);
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


/**
 * Fetch the credit-submission checklist for a deal
 * (GET /api/pipeline/deals/{id}/credit-checklist).
 *
 * Returns the required documents (from lms_config's tiered checklist),
 * which are already provided, which are still missing, whether the deal
 * has already been submitted, and whether the caller may submit it.
 */
export async function fetchCreditChecklist(
  dealId: string,
): Promise<CreditChecklistResponse> {
  return getJson<CreditChecklistResponse>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/credit-checklist`,
  );
}


/**
 * Submit a deal to credit analysis
 * (POST /api/pipeline/deals/{id}/submit-to-credit).
 *
 * Auth: REQUIRED. Owner or admin only. Throws ApiValidationError (400)
 * when required documents are missing — the message lists them. On
 * success the deal is linked to a new loan application.
 */
export async function submitDealToCredit(
  dealId: string,
  documentsProvided: string[],
): Promise<SubmitToCreditResponse> {
  return postJson<SubmitToCreditResponse, { documents_provided: string[] }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/submit-to-credit`,
    { documents_provided: documentsProvided },
  );
}


// ── Pipeline mutation fetchers (v10.511 Phase 4 Batch β2) ───────────────
//
// Wraps the α3 advance + α6 cancel-request endpoints. Server enforces
// the load-bearing rules (authorization, scope, stage transitions,
// minimum reason length); these fetchers just shape the request/
// response.


/**
 * Advance a deal to a new stage via POST /api/pipeline/deals/{id}/advance.
 *
 * Auth: REQUIRED. Server enforces α3 + α4 logic — only valid stage
 * transitions allowed, LMS handoff triggered automatically when
 * advancing into Compliance, scope check applied (caller must own
 * the deal, back it up, or be a manager-in-scope).
 *
 * Throws ApiValidationError (400) on:
 *   - invalid target stage
 *   - terminal-stage deal (cannot advance Closed Won/Lost)
 *   - scope violation
 *
 * Response includes the updated deal + LMS handoff metadata when
 * the advance crossed into a credit-stage.
 */
export async function advancePipelineDeal(
  dealId: string,
  body: AdvanceDealRequest,
): Promise<AdvanceDealResponse> {
  return postJson<AdvanceDealResponse, AdvanceDealRequest>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/advance`,
    body,
  );
}


/**
 * Request cancellation of a deal via POST /api/pipeline/deals/{id}/cancel/request.
 *
 * Auth: REQUIRED. Any authenticated user with scope access — the
 * asymmetric authorization model from α6 (anyone can request, only
 * managers can approve). Reason must be ≥ MIN_CANCEL_REASON_LEN (5)
 * chars per server validation.
 *
 * Throws ApiValidationError (400) on:
 *   - missing or too-short reason
 *   - terminal-stage deal
 *   - already-pending cancel request
 *
 * After success, the deal carries `cancel_requested: true` and
 * `awaiting_manager: true` — surfaces in the manager's cancellation
 * queue (α6) for approve/reject decision.
 */
export async function requestPipelineDealCancel(
  dealId: string,
  body: RequestCancelRequest,
): Promise<RequestCancelResponse> {
  return postJson<RequestCancelResponse, RequestCancelRequest>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/cancel/request`,
    body,
  );
}


// ── Pipeline create + refer fetchers (v10.512 Phase 4 Batch β3) ─────────
//
// The two creation paths. Server enforces the load-bearing rules:
//   - REQUIRED_CREATE_FIELDS presence + non-empty
//   - deal_value non-negative number
//   - stage in ALLOWED_ADVANCE_STAGES (LMS stages rejected)
//   - is_override_semantics → manager_override_note required (>=10 chars)
//   - REQUIRED_REFER_FIELDS presence + non-empty
//   - refer: staff_code != portfolio_owner_code (no self-referral)


/**
 * Create a new pipeline deal via POST /api/pipeline/deals.
 *
 * Auth: REQUIRED. Server validates payload via validate_create_payload
 * in utils/api_pipeline_mutations.py.
 *
 * Conflict resolution (α5):
 *   - "Seek permission" path:    bsc_credit_to = portfolio_owner_name (or unset)
 *                                NO manager_override_note required
 *   - "Override" path:           bsc_credit_to = caller's own name
 *                                manager_override_note REQUIRED, ≥10 chars
 *
 * Throws ApiValidationError on:
 *   - Missing required fields
 *   - deal_value negative or not numeric
 *   - Stage not in allowlist
 *   - Override semantics detected without sufficient note
 */
export async function createPipelineDeal(
  body: CreateDealRequest,
): Promise<CreateDealResponse> {
  return postJson<CreateDealResponse, CreateDealRequest>(
    '/pipeline/deals',
    body,
  );
}

// ─── Initiatives authoring (Phase 1) ──────────────────────────────────
export interface CreateInitiativeBody {
  name: string; objective: string; category: string;
  workstream: string; io: string; sub_workstream?: string;
}
export async function createInitiative(
  body: CreateInitiativeBody,
): Promise<{ status: string; id?: string }> {
  return postJson<{ status: string; id?: string }, CreateInitiativeBody>(
    '/initiatives', body,
  );
}

export interface AddMilestoneBody {
  name: string; owner: string; due_date: string;
  type?: string; start_date?: string; description?: string;
}
export async function addMilestone(
  initiativeId: string, body: AddMilestoneBody,
): Promise<{ status: string; milestone_id?: string }> {
  return postJson<{ status: string; milestone_id?: string }, AddMilestoneBody>(
    `/initiatives/${encodeURIComponent(initiativeId)}/milestones`, body,
  );
}

export interface MilestoneStatusBody {
  status: string; note?: string; started?: boolean;
}
export async function setMilestoneStatus(
  initiativeId: string, msId: string, body: MilestoneStatusBody,
): Promise<{ status: string }> {
  return postJson<{ status: string }, MilestoneStatusBody>(
    `/initiatives/${encodeURIComponent(initiativeId)}/milestones/${encodeURIComponent(msId)}/status`,
    body, 'PATCH',
  );
}


/**
 * Refer a deal to its portfolio owner via POST /api/pipeline/deals/refer.
 *
 * Auth: REQUIRED. Server validates via validate_refer_payload.
 * Server auto-sets: is_referral=true, product_type="Referral",
 * stage="Lead", deal_value=0, probability=0.05.
 *
 * Throws ApiValidationError on:
 *   - Missing required fields (REQUIRED_REFER_FIELDS)
 *   - staff_code === portfolio_owner_code (cannot refer to self)
 */
export async function referPipelineDeal(
  body: ReferDealRequest,
): Promise<ReferDealResponse> {
  return postJson<ReferDealResponse, ReferDealRequest>(
    '/pipeline/deals/refer',
    body,
  );
}


// ── Manager queue + action fetchers (v10.513 Phase 4 Batch β4) ──────────
//
// Wraps the α6 manager-only endpoints. Server enforces is_manager()
// authorization via utils/api_pipeline_manager_actions.py — non-managers
// get 403 (not 401). The React UI uses lib/role.ts::isManager to avoid
// surfacing these endpoints to non-managers in the first place, but the
// server is the security boundary.


/**
 * Fetch the validation queue from /api/pipeline/queues/validation.
 *
 * Auth: REQUIRED + manager-only. Returns deals past Lead stage that
 * haven't been validated yet (and aren't pending cancellation), scoped
 * to the caller's cascade.
 *
 * 403 here means the caller isn't a manager. The page handles this
 * gracefully by checking isManager(user) before fetch.
 */
export async function fetchValidationQueue(): Promise<ValidationQueueResponse> {
  return getJson<ValidationQueueResponse>('/pipeline/queues/validation');
}


/**
 * Fetch the cancellation queue from /api/pipeline/queues/cancellation.
 *
 * Auth: REQUIRED + manager-only. Returns deals with pending cancellation
 * requests awaiting manager decision, scoped to caller's cascade.
 */
export async function fetchCancellationQueue(): Promise<CancellationQueueResponse> {
  return getJson<CancellationQueueResponse>('/pipeline/queues/cancellation');
}


/**
 * Validate or query a deal via POST /api/pipeline/deals/{id}/validate.
 *
 * Auth: REQUIRED + manager-only + deal must be in caller's cascade scope.
 *
 * Two outcomes based on body.approved:
 *   true  → DEAL_VALIDATED, deal joins forecast (manager_validated:true)
 *   false → DEAL_QUERIED, deal returns to owner with note (still
 *           manager_validated:false; the note is visible to owner)
 *
 * Throws ApiValidationError on validation failure (rare — server
 * accepts any boolean+note).
 */
export async function validatePipelineDeal(
  dealId: string,
  body: ValidateDealRequest,
): Promise<ValidateDealResponse> {
  return postJson<ValidateDealResponse, ValidateDealRequest>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/validate`,
    body,
  );
}


/**
 * Approve or reject a cancellation request via
 * POST /api/pipeline/deals/{id}/cancel/approve.
 *
 * Auth: REQUIRED + manager-only + deal must have pending cancel_requested.
 *
 * Two outcomes based on body.approve:
 *   true  → CANCEL_APPROVED, deal transitions to Closed Lost
 *   false → CANCEL_REJECTED, deal continues, cancel_requested cleared
 *
 * Throws ApiValidationError if the deal has no pending cancel request
 * (server rejects with 400).
 */
export async function approvePipelineDealCancel(
  dealId: string,
  body: ApproveCancelRequest,
): Promise<ApproveCancelResponse> {
  return postJson<ApproveCancelResponse, ApproveCancelRequest>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/cancel/approve`,
    body,
  );
}


// ──────────────────────────────────────────────────────────────────────
// LMS (Loan Application Management System) fetchers
// β5 Phase 4 — consumes α8 backend (utils/api_lms_routes.py)
//
// 5 endpoints under /api/lms/applications. All require Bearer JWT.
// Cascade-scoped (rm_code + analyst-override). Audit emission per α8.
// ──────────────────────────────────────────────────────────────────────

import type {
  LoanApplicationsResponse,
  LoanApplicationDetailResponse,
  LoanAppMutationResponse,
  AssignAnalystRequest,
  LoanAppUpdateRequest,
  RecordDecisionRequest,
  RequestInfoRequest,
  ProvideInfoRequest,
  SignOfferRequest,
  ValidateOfferRequest,
  ConfirmToCreditAdminRequest,
  CommitteeVoteRequest,
  ResolveCommitteeRequest,
  AppSla,
  LoanAppHistoryEvent,
} from '@/types/lms';


/**
 * Fetch the cascade-scoped list of loan applications.
 *
 * Auth: REQUIRED. Server filters by caller's visible_codes (cascade
 * walk) PLUS analyst-override (caller's staff_code matches
 * application.analyst.code). Admins see everything.
 *
 * Returns: { applications: [], count: N, source: 'loan_application_manager' }
 */
export async function fetchLmsApplications(): Promise<LoanApplicationsResponse> {
  return getJson<LoanApplicationsResponse>('/lms/applications');
}

// Pipeline-origin credit flow grouped by workflow stage — the live credit
// workload (NOT the loan book / NPL view, which is deferred to Phase-2 Credit
// Monitoring). Scoped to the caller's cascade.
export interface CreditFlowStage {
  key: string;
  label: string;
  count: number;
  value: number;
}
export interface CreditFlowByStageResponse {
  stages: CreditFlowStage[];
  totals: {
    count: number;
    value: number;
    in_flight_count: number;
    in_flight_value: number;
  };
  source: string;
}
export async function fetchCreditFlowByStage(): Promise<CreditFlowByStageResponse> {
  return getJson<CreditFlowByStageResponse>('/lms/flow-by-stage');
}

// Troops (Treasury Back Office) disbursement flow grouped by stage — the live
// disbursement workload (cleared → booked → value-dated → disbursed). Bank-wide,
// role-gated to Treasury Back Office.
export interface TroopsFlowStage {
  key: string;
  label: string;
  count: number;
  value: number;
}
export interface TroopsFlowByStageResponse {
  stages: TroopsFlowStage[];
  totals: {
    count: number;
    value: number;
    pending_count: number;
    pending_value: number;
  };
  source: string;
}
export async function fetchTroopsFlowByStage(): Promise<TroopsFlowByStageResponse> {
  return getJson<TroopsFlowByStageResponse>('/credit-admin/troops/flow-by-stage');
}


/**
 * Fetch a single application by id.
 *
 * Auth: REQUIRED. Returns 404 if not found, 403 if out-of-scope.
 * Response includes per-caller permissions object that React uses
 * to decide which action buttons to enable.
 */
export async function fetchLmsApplicationDetail(
  appId: string,
): Promise<LoanApplicationDetailResponse> {
  return getJson<LoanApplicationDetailResponse>(
    `/lms/applications/${encodeURIComponent(appId)}`,
  );
}


/**
 * Assign a credit analyst to a submitted application. Manager-tier only.
 *
 * Throws ApiValidationError (400) on:
 *   - Missing analyst_code or analyst_name
 *   - Application status != 'submitted' (re-assignment not allowed)
 * Server returns 403 if caller is not manager-tier.
 */
export async function assignLmsAnalyst(
  appId: string,
  body: AssignAnalystRequest,
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, AssignAnalystRequest>(
    `/lms/applications/${encodeURIComponent(appId)}/assign`,
    body,
  );
}

/**
 * Self-pick: an analyst pulls an unallocated case to themselves (no manager
 * assignment). Gated server-side by can_self_pick.
 */
export async function pickLmsApplication(
  appId: string,
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, Record<string, never>>(
    `/lms/applications/${encodeURIComponent(appId)}/pick`,
    {},
  );
}

/**
 * Department Analyst: voice support + submit the case to the Department Credit
 * Committee. Records opinion + PEP confirmation and refers onward. Gated
 * server-side by can_submit_to_dcc; enforces the completeness gate (required
 * attachments + PEP) with a 400 on failure.
 */
export async function submitLmsToDcc(
  appId: string,
  body: { opinion: string; pep_confirmed: boolean },
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { opinion: string; pep_confirmed: boolean }>(
    `/lms/applications/${encodeURIComponent(appId)}/submit-to-dcc`,
    body,
  );
}

// Department Credit Committee (P4b) — self-contained, distinct from the
// authority-tier charter. Roster + votes live on the application.
export interface DccMember { id?: string; member_id?: string; name?: string; role?: string }
export interface DccVote { member_id: string; vote: string; rationale?: string; by?: string; at?: string }
export interface DccOutcome {
  recommendation: string;
  tally: { yes: number; no: number; abstain: number };
  by?: string; by_name?: string; at?: string; note?: string;
}
export interface DccRosterResponse {
  enabled: boolean; name: string; is_dcc_case: boolean;
  members: DccMember[]; votes: DccVote[]; outcome?: DccOutcome | null;
}
export async function getDccRoster(appId: string): Promise<DccRosterResponse> {
  return getJson<DccRosterResponse>(
    `/lms/applications/${encodeURIComponent(appId)}/dcc/roster`);
}
export async function recordDccVote(
  appId: string,
  body: { member_id: string; vote: string; rationale: string },
): Promise<{ dcc_votes: DccVote[] }> {
  return postJson<{ dcc_votes: DccVote[] }, { member_id: string; vote: string; rationale: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/dcc/vote`,
    body,
  );
}
export async function resolveDcc(
  appId: string,
  body: { note?: string },
): Promise<{ dcc_outcome: DccOutcome }> {
  return postJson<{ dcc_outcome: DccOutcome }, { note?: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/dcc/resolve`,
    body,
  );
}
export async function handToCreditAnalyst(appId: string): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, Record<string, never>>(
    `/lms/applications/${encodeURIComponent(appId)}/hand-to-credit-analyst`,
    {},
  );
}
export async function uploadCallbackMemo(
  appId: string,
  body: { filename: string; content_b64: string },
): Promise<{ document_files: Record<string, unknown> }> {
  return postJson<{ document_files: Record<string, unknown> }, { filename: string; content_b64: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/callback-memo`,
    body,
  );
}


/**
 * Partial update to application fields.
 *
 * Throws ApiValidationError (400) on:
 *   - Status not in {submitted, assigned} (no edits after decision)
 *   - completeness_score out of 0..100 range
 *   - No updatable fields provided (empty body)
 * Server returns 403 if caller has no stake (not owner/analyst/manager).
 *
 * Uses PUT method via postJson's 3rd arg.
 */
export async function updateLmsApplication(
  appId: string,
  body: LoanAppUpdateRequest,
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, LoanAppUpdateRequest>(
    `/lms/applications/${encodeURIComponent(appId)}`,
    body,
    'PUT',
  );
}


/**
 * Record approve/decline/return decision. Manager-tier only.
 *
 * Throws ApiValidationError (400) on:
 *   - Missing verdict or authority
 *   - verdict not in {approve, approved, decline, declined, return, returned}
 *   - Status not in {submitted, assigned}
 * Server returns 403 if caller not manager-tier.
 *
 * Verdict normalized server-side to canonical {approved|declined|returned}.
 */
export async function recordLmsDecision(
  appId: string,
  body: RecordDecisionRequest,
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, RecordDecisionRequest>(
    `/lms/applications/${encodeURIComponent(appId)}/decision`,
    body,
  );
}

// ── Credit workflow fetchers (v10.587) ──
const lmsAction = (appId: string, action: string) =>
  `/lms/applications/${encodeURIComponent(appId)}/${action}`;

export async function requestLmsInfo(appId: string, body: RequestInfoRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, RequestInfoRequest>(lmsAction(appId, 'request-info'), body);
}
export async function provideLmsInfo(appId: string, body: ProvideInfoRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, ProvideInfoRequest>(lmsAction(appId, 'provide-info'), body);
}
export async function escalateLmsApplication(appId: string, body: { reason: string; to_manager?: string }): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { reason: string; to_manager?: string }>(lmsAction(appId, 'escalate'), body);
}
export async function addLmsManagerView(appId: string, body: { view: string }): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { view: string }>(lmsAction(appId, 'manager-view'), body);
}
export interface LmsAttachment {
  id: string; kind: string; filename?: string; ref?: string;
  added_by?: string; added_at?: string; meta?: Record<string, unknown>;
}
export async function listLmsAttachments(appId: string): Promise<{ attachments: LmsAttachment[]; bcc?: Record<string, unknown> | null }> {
  return getJson<{ attachments: LmsAttachment[]; bcc?: Record<string, unknown> | null }>(`/lms/applications/${appId}/attachments`);
}
export async function addLmsAttachment(appId: string, body: { kind: string; filename?: string; ref?: string }): Promise<{ attachment: LmsAttachment; attachments: LmsAttachment[] }> {
  return postJson<{ attachment: LmsAttachment; attachments: LmsAttachment[] }, typeof body>(lmsAction(appId, 'attachments'), body);
}
export async function recordLmsBcc(appId: string, body: { verdict: string; branch?: string; chaired_by?: string; attendees?: string[]; minutes?: string; filename?: string; ref?: string }): Promise<Record<string, unknown>> {
  return postJson<Record<string, unknown>, typeof body>(lmsAction(appId, 'bcc'), body);
}
export interface CrField { key: string; label: string; source: 'auto' | 'cbs' | 'rm'; required?: boolean; type?: 'table'; }
export interface CrSection { key: string; title: string; fields: CrField[]; }
export interface CrView {
  template: { sections: CrSection[] };
  values: Record<string, unknown>;
  auto_values: Record<string, unknown>;
  saved_values: Record<string, unknown>;
  cbs_available: boolean;
  completed: boolean;
  updated_by?: string | null;
  updated_at?: string | null;
}
export async function getLmsCr(appId: string): Promise<{ cr: CrView }> {
  return getJson<{ cr: CrView }>(`/lms/applications/${appId}/cr`);
}
export async function saveLmsCr(appId: string, body: { values: Record<string, unknown>; completed?: boolean }): Promise<{ cr: CrView }> {
  return postJson<{ cr: CrView }, typeof body>(lmsAction(appId, 'cr'), body);
}
export interface CommitteeMember { member_id: string; name: string; role: string; is_independent: boolean; }
export interface CommitteeCharter {
  committee_id: string; name: string; members: CommitteeMember[];
  voting_rule: string; min_quorum_count: number; independent_member_min: number;
  authority_limit_kes: number; escalation_target: string;
}
export async function getCommitteeCharter(): Promise<CommitteeCharter> {
  return getJson<CommitteeCharter>('/lms/committee/charter');
}
export async function signLmsOffer(appId: string, body: SignOfferRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, SignOfferRequest>(lmsAction(appId, 'sign-offer'), body);
}
export async function validateLmsOffer(appId: string, body: ValidateOfferRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, ValidateOfferRequest>(lmsAction(appId, 'validate-offer'), body);
}
export async function confirmLmsToCreditAdmin(appId: string, body: ConfirmToCreditAdminRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, ConfirmToCreditAdminRequest>(lmsAction(appId, 'confirm-to-credit-admin'), body);
}
export async function referLmsCommittee(appId: string, entryTier?: number): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { entry_tier?: number }>(lmsAction(appId, 'committee/refer'),
    entryTier != null ? { entry_tier: entryTier } : {});
}
export interface CommitteeTier { tier: number; key: string; name: string; authority_limit_kes: number | null; can_be_entry: boolean; }
export async function getCommitteeTiers(): Promise<{ tiers: CommitteeTier[] }> {
  return getJson<{ tiers: CommitteeTier[] }>('/lms/committee/tiers');
}
export async function saveCommitteeTiers(tiers: CommitteeTier[]): Promise<{ tiers: CommitteeTier[] }> {
  return postJson<{ tiers: CommitteeTier[] }, { tiers: CommitteeTier[] }>('/lms/committee/tiers', { tiers });
}
export async function submitCommitteeUpward(appId: string, note?: string): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { note?: string }>(lmsAction(appId, 'committee/submit-upward'), { note: note || '' });
}
export async function voteLmsCommittee(appId: string, body: CommitteeVoteRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, CommitteeVoteRequest>(lmsAction(appId, 'committee/vote'), body);
}
export async function resolveLmsCommittee(appId: string, body: ResolveCommitteeRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, ResolveCommitteeRequest>(lmsAction(appId, 'committee/resolve'), body);
}


// ──────────────────────────────────────────────────────────────────────
// Credit Admin (CALMS) fetchers
// β6 Phase 4 — consumes α9 backend (utils/api_credit_admin_routes.py)
//
// 4 endpoints under /api/credit-admin/cases. All require Bearer JWT.
// Cascade-scoped (rm_code-based). Audit emission per α9.
// ──────────────────────────────────────────────────────────────────────

import type {
  CreditAdminCasesResponse,
  CreditAdminCaseDetailResponse,
  CreditAdminMutationResponse,
  FulfillConditionRequest,
  DisburseCaseRequest,
  RequestAuthorizationRequest,
  AuthorizeRequest,
} from '@/types/creditAdmin';


/**
 * Fetch cascade-scoped list of credit-admin cases.
 *
 * Auth: REQUIRED. Server filters by caller's visible_codes against
 * case.rm_code. No analyst-override layer (per Section 19.3) — credit
 * admin officers typically have department-level role widening.
 */
export async function fetchCreditAdminCases(): Promise<CreditAdminCasesResponse> {
  return getJson<CreditAdminCasesResponse>('/credit-admin/cases');
}


/**
 * Fetch single case detail + permissions.
 *
 * Auth: REQUIRED. 404 if not found, 403 if out-of-scope.
 */
export async function fetchCreditAdminCaseDetail(
  caseId: string,
): Promise<CreditAdminCaseDetailResponse> {
  return getJson<CreditAdminCaseDetailResponse>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}`,
  );
}


/**
 * Mark a condition fulfilled on a case. Anyone in scope, case not disbursed.
 *
 * Throws ApiValidationError (400) on:
 *   - condition_type or officer_name missing
 *   - Case is already disbursed
 *   - Condition with given type doesn't exist on the case
 * Server returns 403 if caller out-of-scope.
 */
export async function fulfillCreditAdminCondition(
  caseId: string,
  body: FulfillConditionRequest,
): Promise<CreditAdminMutationResponse> {
  return postJson<CreditAdminMutationResponse, FulfillConditionRequest>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/conditions/fulfill`,
    body,
  );
}


/**
 * Clear case for disbursement. Manager-tier only; requires all conditions met.
 *
 * Calls cam.clear_for_disbursement() under the hood — sets
 * ready_for_disbursement=True. The actual fund transfer (disbursed=True)
 * is OUT OF SCOPE (finance system handles it).
 *
 * Throws ApiValidationError (400) on:
 *   - Missing authority
 *   - all_conditions_met is False (returns list of unmet)
 *   - Case is already disbursed
 * Server returns 403 if caller not manager-tier.
 */
export async function disburseCreditAdminCase(
  caseId: string,
  body: DisburseCaseRequest,
): Promise<CreditAdminMutationResponse> {
  return postJson<CreditAdminMutationResponse, DisburseCaseRequest>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/disburse`,
    body,
  );
}

// ── Two-layer authorization fetchers (v10.585 / B20) ──
export async function requestCreditAdminAuthorization(
  caseId: string,
  body: RequestAuthorizationRequest,
): Promise<CreditAdminMutationResponse> {
  return postJson<CreditAdminMutationResponse, RequestAuthorizationRequest>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/request-authorization`,
    body,
  );
}

export async function authorizeCreditAdminCase(
  caseId: string,
  body: AuthorizeRequest,
): Promise<CreditAdminMutationResponse> {
  return postJson<CreditAdminMutationResponse, AuthorizeRequest>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/authorize`,
    body,
  );
}

// ── P4 secured-lending fetchers ──
import type {
  ClassifyConditionRequest, ClassifyFacilityRequest, LinkCollateralRequest,
  LegalAssignRequest, LegalCommentRequest, LegalOutcomeRequest,
  AddPerfectionRequest, UpdatePerfectionRequest, AddInsuranceRequest,
  OverrideRequestBody, DisbursementGate,
} from '@/types/creditAdmin';

const caPost = <B,>(caseId: string, path: string, body: B) =>
  postJson<CreditAdminMutationResponse, B>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/${path}`, body);

export const classifyCondition = (id: string, b: ClassifyConditionRequest) => caPost(id, 'conditions/classify', b);
export const classifyFacility  = (id: string, b: ClassifyFacilityRequest)  => caPost(id, 'classify-facility', b);
export const linkCollateral    = (id: string, b: LinkCollateralRequest)    => caPost(id, 'collateral/link', b);
export const unlinkCollateral  = (id: string, collateral_id: string)       => caPost(id, 'collateral/unlink', { collateral_id });
export const legalAssign       = (id: string, b: LegalAssignRequest)       => caPost(id, 'legal/assign', b);
export const legalComment      = (id: string, b: LegalCommentRequest)      => caPost(id, 'legal/comment', b);
export const legalOutcome      = (id: string, b: LegalOutcomeRequest)      => caPost(id, 'legal/outcome', b);
export const addPerfection     = (id: string, b: AddPerfectionRequest)     => caPost(id, 'perfection', b);
export const updatePerfection  = (id: string, pid: string, b: UpdatePerfectionRequest) => caPost(id, `perfection/${encodeURIComponent(pid)}/update`, b);
export const addInsurance      = (id: string, b: AddInsuranceRequest)      => caPost(id, 'insurance', b);
export const updateInsurance   = (id: string, iid: string, b: Record<string, unknown>) => caPost(id, `insurance/${encodeURIComponent(iid)}/update`, b);
export const requestOverride   = (id: string, b: OverrideRequestBody)      => caPost(id, 'perfection-override/request', b);
export const approveOverride   = (id: string)                             => caPost(id, 'perfection-override/approve', {});

export async function fetchDisbursementGate(caseId: string): Promise<DisbursementGate> {
  return getJson<DisbursementGate>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/disbursement-gate`);
}


// ──────────────────────────────────────────────────────────────────────
// CBS (Core Banking System) lookup fetchers
// γ2 Phase 5 — consumes γ1 backend (utils/api_cbs_routes.py)
//
// 5 endpoints under /api/cbs. All require Bearer JWT. Bank-wide scope
// (no cascade filter). Read-only.
// ──────────────────────────────────────────────────────────────────────

import type {
  CbsCustomerSearchResponse,
  CbsCustomerResponse,
  CbsAccountsResponse,
  CbsBranchesResponse,
  CbsAggregatesResponse,
  CbsAccountDetailResponse,
  CbsAccount360Response,
} from '@/types/cbs';


/**
 * Search customers by name substring (min 3 chars activates server-side).
 * Empty query returns empty list (debounce safety).
 */
export async function searchCbsCustomers(
  query: string,
  limit: number = 10,
): Promise<CbsCustomerSearchResponse> {
  const params = new URLSearchParams();
  params.set('q',     query);
  params.set('limit', String(limit));
  return getJson<CbsCustomerSearchResponse>(`/cbs/customers?${params.toString()}`);
}


/**
 * Exact CIF lookup. 404 if not found.
 * Server emits CBS_CUSTOMER_LOOKUP audit event.
 */
export async function fetchCbsCustomer(cif: string): Promise<CbsCustomerResponse> {
  return getJson<CbsCustomerResponse>(`/cbs/customers/${encodeURIComponent(cif)}`);
}


/**
 * All accounts for a CIF. 404 if CIF not found. Empty array if customer
 * has zero accounts (rare but possible). Server emits CBS_ACCOUNTS_LOOKUP.
 */
export async function fetchCbsCustomerAccounts(cif: string): Promise<CbsAccountsResponse> {
  return getJson<CbsAccountsResponse>(`/cbs/customers/${encodeURIComponent(cif)}/accounts`);
}


/** 35-branch reference. Not audited. */
export async function fetchCbsBranches(): Promise<CbsBranchesResponse> {
  return getJson<CbsBranchesResponse>('/cbs/branches');
}


/** Bundled bank-level aggregates. Not audited. */
export async function fetchCbsAggregates(): Promise<CbsAggregatesResponse> {
  return getJson<CbsAggregatesResponse>('/cbs/aggregates');
}


/**
 * Exact account-number lookup.
 * Live: CUSTOMERACCOUNTDETAILS via FlexCube script API.
 * Fallback: CSV when FLEXCUBE_SCRIPTS_URL is not configured on the server.
 * Audited (CBS_ACCOUNT_LOOKUP). 404 if not found.
 */
export async function fetchCbsAccountByNumber(
  accountNumber: string,
): Promise<CbsAccountDetailResponse> {
  return getJson<CbsAccountDetailResponse>(
    `/cbs/accounts/${encodeURIComponent(accountNumber)}`,
  );
}


/**
 * Combined account + active loans payload.
 * Calls CUSTOMERACCOUNTDETAILS then CUSTOMERACTIVELOANS on the server.
 * Audited (CBS_ACCOUNT_360_LOOKUP). 404 if account not found.
 */
export async function fetchCbsAccount360(
  accountNumber: string,
): Promise<CbsAccount360Response> {
  return getJson<CbsAccount360Response>(
    `/cbs/accounts/${encodeURIComponent(accountNumber)}/360`,
  );
}


// ──────────────────────────────────────────────────────────────────────
// Target Cascade fetchers
// γ3b Phase 5 — consumes γ3a backend (utils/api_cascade_routes.py)
//
// 4 endpoints under /api/cascade. Read-only. All require Bearer JWT.
// ──────────────────────────────────────────────────────────────────────

import type {
  BankTargetsResponse,
  MyAllocationsResponse,
  GivenToMeResponse,
  CoverageResponse,
} from '@/types/cascade';


export async function fetchBankTargets(period: string = '2026'): Promise<BankTargetsResponse> {
  return getJson<BankTargetsResponse>(`/cascade/bank-targets?period=${encodeURIComponent(period)}`);
}


export async function fetchMyCascadeAllocations(period: string = '2026'): Promise<MyAllocationsResponse> {
  return getJson<MyAllocationsResponse>(`/cascade/my-allocations?period=${encodeURIComponent(period)}`);
}


export async function fetchGivenToMe(period: string = '2026'): Promise<GivenToMeResponse> {
  return getJson<GivenToMeResponse>(`/cascade/given-to-me?period=${encodeURIComponent(period)}`);
}


export async function fetchCascadeCoverage(
  fromCode: string,
  kpi: string,
  period: string = '2026',
): Promise<CoverageResponse> {
  const params = new URLSearchParams();
  params.set('from_code', fromCode);
  params.set('kpi',       kpi);
  params.set('period',    period);
  return getJson<CoverageResponse>(`/cascade/coverage?${params.toString()}`);
}


// ──────────────────────────────────────────────────────────────────────
// Target Cascade WRITE fetchers (γ5a)
// ──────────────────────────────────────────────────────────────────────

import type {
  SetBankTargetRequest,
  SetBankTargetResponse,
  SetAllocationRequest,
  SetAllocationResponse,
} from '@/types/cascade';


export async function setBankTarget(req: SetBankTargetRequest): Promise<SetBankTargetResponse> {
  return postJson<SetBankTargetResponse, SetBankTargetRequest>(
    '/cascade/bank-targets',
    req,
    'PUT',
  );
}


export async function setCascadeAllocations(req: SetAllocationRequest): Promise<SetAllocationResponse> {
  return postJson<SetAllocationResponse, SetAllocationRequest>(
    '/cascade/allocations',
    req,
    'PUT',
  );
}


// ──────────────────────────────────────────────────────────────────────
// Strategic Initiatives fetchers (γ4b)
// ──────────────────────────────────────────────────────────────────────

import type {
  PortfolioSummaryResponse,
  InitiativeDetailResponse,
} from '@/types/initiatives';


export async function fetchPortfolioSummary(): Promise<PortfolioSummaryResponse> {
  return getJson<PortfolioSummaryResponse>('/initiatives/portfolio-summary');
}


export async function fetchInitiativeDetail(initiativeId: string): Promise<InitiativeDetailResponse> {
  return getJson<InitiativeDetailResponse>(`/initiatives/${encodeURIComponent(initiativeId)}`);
}


// ──────────────────────────────────────────────────────────────────────
// MD / CEO Dashboard fetcher (P4)
// Consumes /api/dashboard/md (utils/api.py::md_dashboard) — the single
// executive aggregate (bsc + pipeline + credit + aml + org). Cached
// server-side. Any authenticated user; bank-wide (not cascade-scoped).
// ──────────────────────────────────────────────────────────────────────

import type { MdDashboardResponse } from '@/types/dashboard';

export async function fetchMdDashboard(): Promise<MdDashboardResponse> {
  return getJson<MdDashboardResponse>('/dashboard/md');
}


// ──────────────────────────────────────────────────────────────────────
// Credit cockpit fetcher (P5)
// Consumes /api/cockpit/credit/open-work — bank-wide applications-by-lane +
// IFRS9 stage distribution + NPL%. Feeds the dashboard Credit Risk panel.
// ──────────────────────────────────────────────────────────────────────

import type { CreditOpenWork } from '@/types/cockpit';

export async function fetchCreditOpenWork(): Promise<CreditOpenWork> {
  return getJson<CreditOpenWork>('/cockpit/credit/open-work');
}


// ──────────────────────────────────────────────────────────────────────
// FX rates (P4-1c) — operational FX rate table. List/resolve for any authed
// user (dashboards need the LCY/FCY rate); upsert is admin-only server-side.
// ──────────────────────────────────────────────────────────────────────

import type {
  FxRatesResponse,
  FxResolveResponse,
  FxRateUpsertRequest,
  FxRateUpsertResponse,
} from '@/types/fx';

export async function fetchFxRates(
  currency?: string,
  activeOnly = false,
): Promise<FxRatesResponse> {
  const qs = new URLSearchParams();
  if (currency) qs.set('currency', currency);
  if (activeOnly) qs.set('active_only', 'true');
  const suffix = qs.toString() ? `?${qs.toString()}` : '';
  return getJson<FxRatesResponse>(`/fx/rates${suffix}`);
}

export async function resolveFxRate(
  currency: string,
  asOf?: string,
  rateType: 'mid' | 'buy' | 'sell' = 'mid',
): Promise<FxResolveResponse> {
  const qs = new URLSearchParams({ currency, rate_type: rateType });
  if (asOf) qs.set('as_of', asOf);
  return getJson<FxResolveResponse>(`/fx/resolve?${qs.toString()}`);
}

export async function upsertFxRate(
  body: FxRateUpsertRequest,
): Promise<FxRateUpsertResponse> {
  return postJson<FxRateUpsertResponse, FxRateUpsertRequest>('/fx/rates', body);
}


// ── Staff administration (Postgres users table) ──────────────────────────
export interface StaffRow {
  display_name?: string; analytics_name?: string; preferred_name?: string;
  accessible_modules?: string[];
  username: string;
  staff_code: string | null;
  full_name: string | null;
  role: string | null;
  department: string | null;
  unit: string | null;
  email: string;
  active: boolean;
  is_admin: boolean;
  can_view_all: boolean;
  must_change_password: boolean;
  last_login: string | null;
  reports_to?: string | null;
  managed_staff_codes?: string[];
  managed_units?: string[];
  managed_roles?: string[];
  region?: string | null;
}

export interface StaffListResponse { staff: StaffRow[]; count: number; }

export interface StaffCreateInput {
  username?: string; staff_code?: string; password: string; full_name: string;
  email?: string; role?: string; department?: string; unit?: string;
  band?: string; gender?: string; can_view_all?: boolean; is_admin?: boolean;
}

export interface StaffPatchInput {
  accessible_modules?: string[];
  full_name?: string; preferred_name?: string; email?: string; role?: string;
  department?: string; unit?: string; staff_code?: string; band?: string;
  gender?: string; can_view_all?: boolean; is_admin?: boolean; active?: boolean;
}

export async function fetchAdminStaff(): Promise<StaffListResponse> {
  return getJson<StaffListResponse>('/admin/staff');
}
export async function createAdminStaff(
  input: StaffCreateInput,
): Promise<{ status: string; username: string; staff_code: string }> {
  return postJson('/admin/staff', input, 'POST');
}
export async function updateAdminStaff(
  username: string, patch: StaffPatchInput,
): Promise<{ status: string; username: string }> {
  return postJson(`/admin/staff/${encodeURIComponent(username)}`, patch, 'PATCH');
}
export async function deactivateAdminStaff(
  username: string,
): Promise<{ status: string; username: string }> {
  return postJson(`/admin/staff/${encodeURIComponent(username)}/deactivate`, {}, 'POST');
}
export async function reactivateAdminStaff(
  username: string,
): Promise<{ status: string; username: string }> {
  return postJson(`/admin/staff/${encodeURIComponent(username)}/reactivate`, {}, 'POST');
}

// staff module-access (module-level RBAC)
export interface AccessModule { key: string; label: string; min: string; }
export async function fetchAccessModules(): Promise<AccessModule[]> {
  const res = await getJson<{ modules: AccessModule[] }>('/admin/modules');
  return res.modules ?? [];
}

// staff Excel upload (preview + apply)
export interface StaffUploadPreview {
  ok: boolean;
  errors: string[];
  summary: {
    total: number;
    root: { code: string; name: string; role: string } | null;
    reporting_to_md: { code: string; name: string; role: string }[];
    staff_per_branch: Record<string, number>;
    roles: Record<string, number>;
  } | null;
}
export interface StaffUploadResult {
  ok: boolean; applied: number; before: number; after: number; preserved: string[];
}
export async function previewStaffUpload(contentB64: string): Promise<StaffUploadPreview> {
  return postJson<StaffUploadPreview, { content_b64: string }>(
    '/admin/staff/upload/preview', { content_b64: contentB64 });
}
export async function applyStaffUpload(contentB64: string, keep: string[]): Promise<StaffUploadResult> {
  return postJson<StaffUploadResult, { content_b64: string; keep: string[] }>(
    '/admin/staff/upload/apply', { content_b64: contentB64, keep });
}

// reporting hierarchy (role -> parent roles)
export interface HierarchyResponse {
  roles: string[];
  hierarchy: Record<string, string[]>;
  functional_hierarchy?: Record<string, string[]>;
  top: string[];
}
export async function fetchHierarchy(): Promise<HierarchyResponse> {
  return getJson<HierarchyResponse>('/admin/hierarchy');
}
export async function saveHierarchy(
  body: { action: string; role?: string; parents?: string[]; new_name?: string },
): Promise<{ status: string; hierarchy: Record<string, string[]> }> {
  return postJson<{ status: string; hierarchy: Record<string, string[]> }, typeof body>(
    '/admin/hierarchy', body);
}

// document catalog (master list for per-product required documents)
export async function fetchDocumentCatalog(): Promise<string[]> {
  const res = await getJson<{ documents: string[] }>('/admin/document-catalog');
  return res.documents ?? [];
}

// deal document upload/attach (Batch 3)
export interface DealDocumentMeta {
  filename: string; path: string; sha256: string; size: number;
  uploaded_by: string; uploaded_at: string;
}
export interface DealDocumentsResponse {
  files: Record<string, DealDocumentMeta>;
  required: string[];
  provided: string[];
}
export async function listDealDocuments(dealId: string): Promise<DealDocumentsResponse> {
  return getJson<DealDocumentsResponse>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/documents`);
}
export async function uploadDealDocument(
  dealId: string, docName: string, filename: string, contentB64: string,
): Promise<{ status: string; doc_name: string; meta: DealDocumentMeta }> {
  return postJson<{ status: string; doc_name: string; meta: DealDocumentMeta },
    { doc_name: string; filename: string; content_b64: string }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/documents`,
    { doc_name: docName, filename, content_b64: contentB64 });
}
export async function deleteDealDocument(dealId: string, docName: string): Promise<{ status: string }> {
  return postJson<{ status: string }, Record<string, never>>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/documents/${encodeURIComponent(docName)}`,
    {}, 'DELETE');
}
export async function downloadDealDocument(dealId: string, docName: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const tok = getCurrentTokenForBlob();
  if (tok) headers['Authorization'] = `Bearer ${tok}`;
  const res = await fetch(
    `/api/pipeline/deals/${encodeURIComponent(dealId)}/documents/${encodeURIComponent(docName)}`,
    { headers });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  return res.blob();
}

// LMS-side document access: the documents that TRAVELLED with the case from the
// pipeline deal, served under LMS view permission (the credit side has no deal
// scope). Used by the analyst / DCC / BCC / Chief Credit to read every file.
export interface LmsDocumentsResponse {
  files: Record<string, DealDocumentMeta>;
  provided: string[];
}
export async function listLmsDocuments(appId: string): Promise<LmsDocumentsResponse> {
  return getJson<LmsDocumentsResponse>(
    `/lms/applications/${encodeURIComponent(appId)}/documents`);
}
export async function downloadLmsDocument(appId: string, docName: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const tok = getCurrentTokenForBlob();
  if (tok) headers['Authorization'] = `Bearer ${tok}`;
  const res = await fetch(
    `/api/lms/applications/${encodeURIComponent(appId)}/documents/${encodeURIComponent(docName)}`,
    { headers });
  if (!res.ok) throw new Error(`Download failed (${res.status})`);
  return res.blob();
}

// credit committee palette (4b-1)
export interface CommitteeMemberDef { name: string; role: string; staff_code?: string; full_funnel?: boolean; }
export interface CommitteeDef {
  code: string;
  name: string;
  kind?: string;
  branch?: string;
  chaired_by?: string;
  recording_mode: string;
  voting_rule: string;
  amount_threshold_kes: number;
  members: CommitteeMemberDef[];
}
export interface CommitteePaletteResponse {
  committees: CommitteeDef[];
  recording_modes: string[];
  voting_rules: string[];
}
export async function fetchCommitteePalette(): Promise<CommitteePaletteResponse> {
  return getJson<CommitteePaletteResponse>('/admin/committee-palette');
}
export async function upsertCommittee(committee: CommitteeDef): Promise<{ status: string; committees: CommitteeDef[] }> {
  return postJson<{ status: string; committees: CommitteeDef[] }, { committee: CommitteeDef }>(
    '/admin/committee-palette', { committee });
}
export async function deleteCommittee(code: string): Promise<{ status: string; committees: CommitteeDef[] }> {
  return postJson<{ status: string; committees: CommitteeDef[] }, { delete: string }>(
    '/admin/committee-palette', { delete: code });
}
export async function seedCommitteePalette(): Promise<{ status: string; committees: CommitteeDef[] }> {
  return postJson<{ status: string; committees: CommitteeDef[] }, Record<string, never>>(
    '/admin/committee-palette/seed', {});
}

export async function generateBranchCommittees(): Promise<{ status: string; created: string[]; count: number; committees: CommitteeDef[] }> {
  return postJson<{ status: string; created: string[]; count: number; committees: CommitteeDef[] }, Record<string, never>>(
    '/admin/committee-palette/generate-branch', {});
}

// deal-level CR (4b-3): the CR originates at the branch on the deal.
export async function getDealCr(dealId: string): Promise<CrView> {
  return getJson<CrView>(`/pipeline/deals/${encodeURIComponent(dealId)}/cr`);
}
export async function saveDealCr(
  dealId: string, body: { values: Record<string, unknown>; completed?: boolean },
): Promise<CrView> {
  return postJson<CrView, typeof body>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/cr`, body);
}

// committee decision capture on the deal (4b-4)
export interface CommitteeVote { name: string; role: string; vote: string; documents_validated?: boolean; comment?: string; }
export interface CommitteeRecord {
  outcome: string; mode: string; votes: CommitteeVote[];
  note?: string; recorded_by?: string; recorded_at?: string;
}
export interface CommitteeGate {
  code: string; name: string; recording_mode: string; voting_rule: string;
  members: { name: string; role: string }[];
  record: CommitteeRecord | null;
}
export interface CommitteeRecordsResponse { gates: CommitteeGate[]; cr_only: boolean; }
export async function getDealCommitteeRecords(dealId: string): Promise<CommitteeRecordsResponse> {
  return getJson<CommitteeRecordsResponse>(`/pipeline/deals/${encodeURIComponent(dealId)}/committee-records`);
}
export async function recordDealCommitteeDecision(
  dealId: string,
  body: { code: string; outcome?: string; votes?: CommitteeVote[]; note?: string },
): Promise<{ status: string; code: string; record: CommitteeRecord }> {
  return postJson<{ status: string; code: string; record: CommitteeRecord }, typeof body>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/committee-records`, body);
}

// reject -> owner fallback (4b-6)
export async function appealCommitteeDecision(
  dealId: string, code: string, reason: string,
): Promise<{ status: string; message: string }> {
  return postJson<{ status: string; message: string }, { code: string; reason: string }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/committee-appeal`, { code, reason });
}
export async function closeDealAsLost(dealId: string, reason: string): Promise<{ status: string }> {
  return postJson<{ status: string }, { reason: string }>(
    `/pipeline/deals/${encodeURIComponent(dealId)}/close-lost`, { reason });
}

// analyst read-only view of branch committee decisions (4b-7b)
export interface LmsCommitteeRecordsResponse {
  committee_records: Record<string, {
    outcome: string; mode: string;
    votes: { name: string; role: string; vote: string }[];
    note?: string; recorded_by?: string; recorded_at?: string;
  }>;
  committee_appeals: { code: string; reason: string; outcome: string; by: string; at: string }[];
  cr_origin: string;
}
export async function getLmsCommitteeRecords(appId: string): Promise<LmsCommitteeRecordsResponse> {
  return getJson<LmsCommitteeRecordsResponse>(`/lms/applications/${appId}/committee-records`);
}

// assignable analysts for the current manager (assign-analyst dropdown)
export interface AssignableAnalyst { staff_code: string; name: string; role: string; unit: string; }
export async function fetchMyAnalysts(): Promise<{ analysts: AssignableAnalyst[]; count: number }> {
  return getJson<{ analysts: AssignableAnalyst[]; count: number }>('/lms/my-analysts');
}


// B2: assignment requests (analyst pull + manager resolve)
export interface AssignmentRequestCase {
  id: string; client_name?: string; product?: string; amount?: number;
  rm_name?: string; status?: string;
  requests: { by_code: string; by_name: string; at: string; note?: string }[];
}
export async function requestLmsAssignment(
  appId: string, note?: string,
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { note?: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/request-assignment`, { note });
}
export async function fetchAssignmentRequests(): Promise<{ cases: AssignmentRequestCase[]; count: number }> {
  return getJson<{ cases: AssignmentRequestCase[]; count: number }>(
    '/lms/applications/assignment-requests');
}

// C1: committee routing suggestion (Chief routes by limit)
export interface CommitteeRouting {
  tiers: CommitteeTier[];
  amount: number;
  suggested_tier: number | null;
  suggested_name: string | null;
  entry_tier?: number | null;
  entry_name?: string | null;
  final_tier?: number | null;
  final_name?: string | null;
  require_mcc?: boolean;
  must_climb?: boolean;
  can_refer: boolean;
  current_status: string;
}
export async function fetchCommitteeRouting(appId: string): Promise<CommitteeRouting> {
  return getJson<CommitteeRouting>(`/lms/applications/${encodeURIComponent(appId)}/committee-routing`);
}

// C1b: require-MCC-before-higher admin toggle
export async function setRequireMcc(enabled: boolean): Promise<{ status: string; require_mcc_before_higher: boolean }> {
  return postJson<{ status: string; require_mcc_before_higher: boolean }, { enabled: boolean }>(
    '/lms/committee/require-mcc', { enabled });
}

// C2: correctness-staging readiness (ready for committee / return for rework)
export async function setCommitteeReadiness(
  appId: string, decision: 'ready' | 'rework', opinion?: string, reasons?: string[],
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { decision: string; opinion?: string; reasons?: string[] }>(
    `/lms/applications/${encodeURIComponent(appId)}/committee-readiness`,
    { decision, opinion, reasons });
}

// C2: the configured rework reason codes (lms_config -> rework_reasons)
export async function fetchReworkReasons(): Promise<string[]> {
  const r = await getJson<{ rework_reasons: string[] }>('/lms/rework-reasons');
  return r.rework_reasons ?? [];
}

// Decline appeal: file (originator) + review (manager grant/uphold)
export async function appealDecline(appId: string, reason: string): Promise<{ status: string }> {
  return postJson<{ status: string }, { reason: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/appeal`, { reason });
}
export async function decideAppeal(appId: string, outcome: 'grant' | 'uphold', note?: string): Promise<{ status: string; reopened: boolean }> {
  return postJson<{ status: string; reopened: boolean }, { outcome: string; note?: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/appeal-decision`, { outcome, note });
}

// C3b: committee pre-read (member non-binding view)
export interface CommitteePreRead {
  by_code: string; by_name: string; view: 'leaning_approve' | 'leaning_decline' | 'questions';
  note?: string; at: string; tier?: number | null;
}
export interface CommitteePreReadsResponse {
  pre_reads: CommitteePreRead[]; all: CommitteePreRead[];
  tally: Record<string, number>; current_tier: number | null;
}
export async function recordCommitteePreRead(
  appId: string, view: 'leaning_approve' | 'leaning_decline' | 'questions', note?: string,
): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, { view: string; note?: string }>(
    `/lms/applications/${encodeURIComponent(appId)}/committee/pre-read`, { view, note });
}
export async function fetchCommitteePreReads(appId: string): Promise<CommitteePreReadsResponse> {
  return getJson<CommitteePreReadsResponse>(
    `/lms/applications/${encodeURIComponent(appId)}/committee/pre-reads`);
}

// C4: MD convening queue
export interface ConveningCase {
  id: string; client_name?: string; product?: string; amount?: number;
  pre_read_count: number; pre_read_tally: Record<string, number>;
  convened: boolean; sla?: AppSla | null;
}
export interface ConveningTier { tier: number | null; name: string | null; count: number; cases: ConveningCase[]; }
export interface ConveningQueueResponse { tiers: ConveningTier[]; total: number; awaiting: number; }
export async function fetchConveningQueue(): Promise<ConveningQueueResponse> {
  return getJson<ConveningQueueResponse>('/lms/committee/convening-queue');
}
export async function convokeCommittee(appId: string): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, Record<string, never>>(
    `/lms/applications/${encodeURIComponent(appId)}/committee/convene`, {});
}

// CA1: Troops disbursement queue + the 3 actions (book -> value-date -> disburse)
export interface TroopsQueueCase {
  case_id: string; application_id?: string; client_name?: string; amount?: number;
  rm_code?: string; troops_status: string; cbs_account_no?: string | null;
  value_date?: string | null; disbursed: boolean; disbursement_date?: string | null;
}
export interface TroopsQueueResponse { cases: TroopsQueueCase[]; count: number; source: string; }
export async function fetchTroopsQueue(): Promise<TroopsQueueResponse> {
  return getJson<TroopsQueueResponse>('/credit-admin/troops/queue');
}
export async function troopsBook(caseId: string, cbsAccountNo?: string): Promise<{ troops_status: string }> {
  return postJson<{ troops_status: string }, { cbs_account_no?: string }>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/troops/book`, { cbs_account_no: cbsAccountNo });
}
export async function troopsValueDate(caseId: string, valueDate: string): Promise<{ troops_status: string }> {
  return postJson<{ troops_status: string }, { value_date: string }>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/troops/value-date`, { value_date: valueDate });
}
export async function troopsDisburse(caseId: string, glReference?: string): Promise<{ troops_status: string }> {
  return postJson<{ troops_status: string }, { gl_reference?: string }>(
    `/credit-admin/cases/${encodeURIComponent(caseId)}/troops/disburse`, { gl_reference: glReference });
}

// CA2: submit-to-legal-for-charging + Legal Chief queue + officer pool
export const submitForCharging = (id: string, note?: string) =>
  caPost(id, 'legal/submit-for-charging', { note: note ?? '' });
export interface ChargingQueueCase {
  case_id: string; client_name?: string; amount?: number;
  submitted_at?: string; submitted_by?: string;
  assigned_officer_code?: string | null; assigned_officer_name?: string | null;
}
export interface ChargingQueueResponse { cases: ChargingQueueCase[]; count: number; }
export async function fetchChargingQueue(): Promise<ChargingQueueResponse> {
  return getJson<ChargingQueueResponse>('/credit-admin/legal/charging-queue');
}
export interface LegalOfficer { staff_code: string; name: string; role: string; unit: string; }
export interface LegalOfficersResponse { officers: LegalOfficer[]; count: number; }
export async function fetchMyLegalOfficers(): Promise<LegalOfficersResponse> {
  return getJson<LegalOfficersResponse>('/credit-admin/my-legal-officers');
}


// ── Credit Analyst Workbench (P1/P2/P3) ──────────────────────────────
export interface WorkbenchPull { data_source: string; recorded?: boolean; decision?: string; }
export interface WorkbenchSummary {
  found: boolean; session_id?: string; state?: string;
  customer_id?: string; loan_application_id?: string;
  data_pulls_count?: number; sources_pulled?: string[]; sources_missing?: string[];
  notes_count?: number; notes_by_category?: Record<string, number>;
}
export interface WorkbenchConflict { decision: string; sources: string[]; pull_count: number; }
export interface WorkbenchConflictReport {
  session_id: string; total_pulls: number; distinct_decisions: number;
  conflict_count: number; conflicts: WorkbenchConflict[];
}
export interface WorkbenchRoleLens {
  cr: { completed: boolean | null };
  credit_admin: {
    linked: boolean; conditions_total: number | null; conditions_met: number | null;
    all_conditions_met: boolean | null; cleared: boolean | null; disbursed: boolean | null;
  };
}
export interface WorkbenchView {
  session_id: string; summary: WorkbenchSummary;
  conflict_report: WorkbenchConflictReport; states: string[];
  role_lens?: WorkbenchRoleLens;
}
export async function getApplicationWorkbench(appId: string): Promise<WorkbenchView> {
  return getJson<WorkbenchView>(`/lms/applications/${encodeURIComponent(appId)}/workbench`);
}
export async function refreshWorkbench(appId: string): Promise<{ refreshed: WorkbenchPull[]; summary: WorkbenchSummary; conflict_report: WorkbenchConflictReport; }> {
  return postJson(`/lms/applications/${encodeURIComponent(appId)}/workbench/refresh`, {});
}
export async function addWorkbenchNote(appId: string, category: string, body: string): Promise<{ note_id: string; summary: WorkbenchSummary; }> {
  return postJson(`/lms/applications/${encodeURIComponent(appId)}/workbench/note`, { category, body });
}
export async function transitionWorkbench(appId: string, new_state: string, reason?: string): Promise<{ summary: WorkbenchSummary; states: string[]; }> {
  return postJson(`/lms/applications/${encodeURIComponent(appId)}/workbench/transition`, { new_state, reason });
}


// ── Affordability appraisal (multi-source, deterministic, no AI) ──────
export interface SourceAffordability {
  dsr_limit_pct?: number; dsr_is_override?: boolean; dsr_default_pct?: number;
  basis?: number; months_in_basis?: number; months_window?: number | null;
  months_excluded?: { month: string; reason: string }[];
  anomaly_hints?: string[]; affordable_installment?: number; verdict?: string;
}
export interface SourceLine {
  label?: string; ok?: boolean; months?: number;
  summary?: { avg_monthly_credit?: number; avg_monthly_debit?: number; avg_monthly_net?: number };
  affordability?: SourceAffordability;
}
export interface MultiSourceResult {
  sources: SourceLine[];
  consolidation: { method: string; total_affordable_installment: number; source_count: number; source_labels: string[] };
}
export interface AmortizationResult {
  amount: number; monthly_rate_pct: number; tenor_months: number;
  monthly_instalment: number; total_repayable: number; total_interest: number;
}
export interface MultiSourceInput {
  label: string; cif?: string; transactions?: { txn_date: string; amount: number; dr_cr: string }[];
  dsr_pct?: number; months_window?: number; excluded_months?: { month: string; reason: string }[];
}
export async function analyzeMultiSource(sources: MultiSourceInput[], scenarioName?: string): Promise<MultiSourceResult> {
  return postJson('/credit/analyze-multi-source', { sources, ...(scenarioName ? { scenario_name: scenarioName } : {}) });
}
export async function computeAmortization(body: { amount: number; monthly_rate_pct?: number; annual_rate_pct?: number; tenor_months: number }): Promise<AmortizationResult> {
  return postJson('/credit/amortization', body);
}


// ── Appraisal persistence ────────────────────────────────────────────
export interface SavedAppraisal {
  sources?: unknown[]; scenarios?: unknown[]; custom_sections?: unknown[];
  updated_by?: string; updated_at?: string;
}
export async function getDealAppraisal(dealId: string): Promise<SavedAppraisal> {
  return getJson(`/pipeline/deals/${encodeURIComponent(dealId)}/appraisal`);
}
export async function saveDealAppraisal(dealId: string, body: SavedAppraisal): Promise<SavedAppraisal> {
  return postJson(`/pipeline/deals/${encodeURIComponent(dealId)}/appraisal`, body);
}
export async function getAppAppraisal(appId: string): Promise<SavedAppraisal> {
  return getJson(`/lms/applications/${encodeURIComponent(appId)}/appraisal`);
}
export async function saveAppAppraisal(appId: string, body: SavedAppraisal): Promise<SavedAppraisal> {
  return postJson(`/lms/applications/${encodeURIComponent(appId)}/appraisal`, body);
}


export interface QualifyingResult {
  affordable_installment: number; monthly_rate_pct: number; tenor_months: number; qualifying_amount: number;
}
export async function computeQualifyingAmount(body: { affordable_installment: number; monthly_rate_pct?: number; annual_rate_pct?: number; tenor_months: number }): Promise<QualifyingResult> {
  return postJson('/credit/qualifying-amount', body);
}
