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
  method: 'POST' | 'PUT' = 'POST',
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


/**
 * Fetch pipeline analytics from /api/pipeline/analytics — validated/pending
 * value split, per-class buckets (asset/liability/insurance/other), the
 * validated funnel, and the scope-aware pending-validation count.
 */
export async function fetchPipelineAnalytics(): Promise<PipelineAnalyticsResponse> {
  return getJson<PipelineAnalyticsResponse>('/pipeline/analytics');
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
export async function signLmsOffer(appId: string, body: SignOfferRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, SignOfferRequest>(lmsAction(appId, 'sign-offer'), body);
}
export async function validateLmsOffer(appId: string, body: ValidateOfferRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, ValidateOfferRequest>(lmsAction(appId, 'validate-offer'), body);
}
export async function confirmLmsToCreditAdmin(appId: string, body: ConfirmToCreditAdminRequest): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, ConfirmToCreditAdminRequest>(lmsAction(appId, 'confirm-to-credit-admin'), body);
}
export async function referLmsCommittee(appId: string): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, Record<string, never>>(lmsAction(appId, 'committee/refer'), {});
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
