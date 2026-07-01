// v10.520 Phase 4 Batch β5 — TypeScript types for the LMS domain.
//
// These interfaces mirror the FastAPI backend's response shapes from:
//   - GET  /api/lms/applications        (α8 — list, cascade-scoped)
//   - GET  /api/lms/applications/{id}   (α8 — single + permissions)
//   - POST /api/lms/applications/{id}/assign   (α8)
//   - PUT  /api/lms/applications/{id}          (α8)
//   - POST /api/lms/applications/{id}/decision (α8)
//
// Backend shape is defined by:
//   - utils/api_lms_models.py::LoanApplication           (data shape, extra="allow")
//   - utils/api_lms_permissions.py::resolve_application_permissions
//
// If backend changes, this file changes. Cross-reference:
// docs/architecture/PIPELINE_DOMAIN_AUDIT.md Section 18 for the
// α8 doctrine, and docs/architecture/API_CONTRACTS.md for the
// endpoint contracts.


// ── Permissions (α8 contract — audit Section 18.2) ──────────────────────
// Four booleans resolved server-side per (caller, application) pair.
// React reads these to decide which buttons to render — server still
// enforces the same checks on every mutation.

export interface LoanApplicationPermissions {
  /** Caller can fetch detail. False → page should not load. */
  can_view:               boolean;
  /** Caller can PUT field updates. False if status terminal or no stake. */
  can_update:             boolean;
  /** Caller can assign analyst. Manager-tier only, status=submitted. */
  can_assign:             boolean;
  /** Caller can record decision. Assigned analyst, manager-tier, or admin. */
  can_record_decision:    boolean;
  /** Assigned analyst can escalate / seek guidance to their line manager. */
  can_escalate?:          boolean;
  // Credit workflow (v10.587)
  can_request_info?:           boolean;
  can_provide_info?:           boolean;
  can_sign_offer?:             boolean;
  can_validate_offer?:         boolean;
  can_confirm_to_credit_admin?: boolean;
  can_refer_committee?:        boolean;
  can_vote_committee?:         boolean;
  can_resolve_committee?:      boolean;
}


// ── Nested objects ──────────────────────────────────────────────────────

export interface LoanApplicationAnalyst {
  code?:                  string;
  name?:                  string;
}

export interface LoanApplicationDecisionRecord {
  verdict?:               string;
  date?:                  string;
  authority?:             string;
  reason?:                string;
  conditions?:            string[];
  comments?:              string;
}


export interface LoanAppHistoryEvent {
  event:    string;
  by?:      string;
  at?:      string;
  note?:    string;
  [key: string]: unknown;
}

export interface LoanAppOffer {
  issued_by?:    string;
  issued_at?:    string;
  signed?:       boolean;
  signed_by?:    string;
  signed_at?:    string;
  validated?:    boolean | null;
  validated_by?: string;
  validated_at?: string;
  signed_attachment?: {
    mode?: string; filename?: string; ref?: string;
    uploaded_by?: string; uploaded_at?: string | null;
  } | null;
  note?:         string;
}

export interface LoanAppInfoRequest {
  by?:        string;
  at?:        string;
  reasons?:   string[];
  documents?: string[];
  note?:      string;
  resolved?:  boolean;
  resolved_by?: string;
  resolved_at?: string;
  provided_documents?: string[];
}

export interface LoanAppCommitteeVote {
  member_id: string;
  vote:      string;
  rationale?: string;
  by?:       string;
  at?:       string;
}

export interface LoanAppCommittee {
  votes?:        LoanAppCommitteeVote[];
  referred_by?:  string;
  referred_at?:  string;
  resolved?:     boolean;
  current_tier?:      number;
  current_tier_name?: string;
  entry_tier?:        number;
  tier_history?:      Array<{
    tier: number;
    tier_name?: string;
    votes?: LoanAppCommitteeVote[];
    submitted_by?: string;
    submitted_at?: string;
    note?: string;
  }>;
  resolved_by?:  string;
  resolved_at?:  string;
  result?:       Record<string, unknown> | null;
  note?:         string;
}


// ── LoanApplication shape ───────────────────────────────────────────────
// Matches LoanApplication Pydantic model with extra="allow". Known fields
// are explicit here; future backend additions tolerated via index signature.

export interface AssignmentRequest {
  by_code: string;
  by_name: string;
  at:      string;
  note?:   string;
}

export interface AppSlaClock {
  state: 'on_track' | 'due_soon' | 'breached';
  step_key?: string;
  elapsed_business_days: number;
  target_days: number;
  remaining_business_days: number;
  overdue_business_days: number;
  breached: boolean;
}
export interface AppSla extends AppSlaClock {
  // C-SLA2: two-level — overall (customer promise) + stage ("My SLA").
  overall?: AppSlaClock;
  stage?: AppSlaClock | null;
}

export interface LoanApplication {
  // Identity
  id:                     string;
  pipeline_deal_id?:      string;

  // Customer
  client_name:            string;
  client_cif?:            string;

  // Money
  amount?:                number;
  currency?:              string;

  // Product
  product?:               string;
  swim_lane?:             string;

  // Status / lifecycle
  status:                 string;
  application_date?:      string;
  last_updated?:          string;

  // Ownership
  rm_code?:               string;
  rm_name?:               string;
  rm_unit?:               string;
  analyst?:               LoanApplicationAnalyst | null;
  assignment_requests?:   AssignmentRequest[];

  // Decision
  decision?:              LoanApplicationDecisionRecord | null;

  // Underwriting flags
  is_repeat_borrower?:    boolean;
  clean_repayment_history?: boolean;

  // Documentation
  docs_required?:         string[];
  docs_submitted?:        string[];
  completeness_score?:    number;

  // Compliance
  compliance_flag?:       boolean;
  compliance_type?:       string;

  // SLA
  tat_days?:              number;
  sla_target_days?:       number;
  sla?:                   AppSla | null;

  // Categorization
  proposition_tag?:       string;
  deal_category?:         string;

  // Provenance (α4 handoff)
  created_by?:            string;
  created_via?:           string;

  // Free text
  appraisal_notes?:       string;

  // Credit workflow (v10.584+)
  history?:               LoanAppHistoryEvent[];
  offer?:                 LoanAppOffer | null;
  info_request?:          LoanAppInfoRequest | null;
  escalation?:            {
    escalated?: boolean;
    by?: string;
    at?: string;
    reason?: string;
    to_manager?: string;
    resolved?: boolean;
    manager_view?: string;
    view_by?: string;
    view_at?: string;
  } | null;
  committee?:             LoanAppCommittee | null;
  credit_admin_case_id?:  string;

  // Extra fields tolerated
  [key: string]:          unknown;
}


// ── Response shapes ─────────────────────────────────────────────────────

export interface LoanApplicationsResponse {
  applications:           LoanApplication[];
  count:                  number;
  source:                 string;
}

export interface LoanApplicationDetailResponse {
  application:            LoanApplication;
  permissions:            LoanApplicationPermissions;
  source:                 string;
}

export interface LoanAppMutationResponse {
  application:            LoanApplication;
  status:                 string;
}


// ── Request body shapes ─────────────────────────────────────────────────

export interface AssignAnalystRequest {
  analyst_code:           string;
  analyst_name:           string;
}

export interface LoanAppUpdateRequest {
  docs_submitted?:        string[];
  docs_required?:         string[];
  completeness_score?:    number;
  compliance_flag?:       boolean;
  compliance_type?:       string;
  appraisal_notes?:       string;
  is_repeat_borrower?:    boolean;
  clean_repayment_history?: boolean;
}

export interface RecordDecisionRequest {
  verdict:                string;       // 'approved' | 'declined' | 'returned' (case-insensitive)
  authority:              string;
  reason?:                string;
  conditions?:            string[];
  comments?:              string;
}


// ── Helper constants ─────────────────────────────────────────────────────

/**
 * Canonical status values (lowercase, per α8 data file).
 * See PIPELINE_DOMAIN_AUDIT Section 18.5 for the enum-vs-data
 * discrepancy (candidate GAP-017).
 */
export const APPLICATION_STATUSES = [
  'submitted',
  'assigned',
  'approved',
  'declined',
  'returned',
  'info_requested',
  'referred_to_committee',
  'offer_issued',
  'offer_signed',
  'offer_validated',
  'analyst_confirmed',
  'credit_admin',
  'disbursed',
] as const;

export type ApplicationStatus = typeof APPLICATION_STATUSES[number];

/**
 * Visual tone mapping for status badges (mirrors stageTone in
 * types/pipeline.ts). Used by list and detail pages.
 *
 * Returns BadgeTone-compatible values only. 'neutral' is the BadgeTone
 * name for the gray/default tone.
 */
export function statusTone(status: string | undefined): 'neutral' | 'brand' | 'warning' | 'success' | 'danger' {
  if (!status) return 'neutral';
  const s = status.toLowerCase();
  if (s === 'submitted')   return 'neutral';
  if (s === 'assigned')    return 'brand';
  if (s === 'approved')    return 'success';
  if (s === 'disbursed')   return 'success';
  if (s === 'returned')    return 'warning';
  if (s === 'declined')    return 'danger';
  if (s === 'credit_admin') return 'brand';
  if (s === 'info_requested') return 'warning';
  if (s === 'referred_to_committee') return 'brand';
  if (s === 'offer_issued')   return 'warning';
  if (s === 'offer_signed')   return 'brand';
  if (s === 'offer_validated') return 'brand';
  if (s === 'analyst_confirmed') return 'brand';
  return 'neutral';
}

/**
 * Allowed decision verdicts the form will let user pick.
 * Backend accepts both short and long form — we display the long form.
 */
export const DECISION_VERDICTS = ['approved', 'declined', 'returned'] as const;
export type DecisionVerdict = typeof DECISION_VERDICTS[number];

/**
 * Common decision-authority labels for the dropdown. Backend accepts
 * any non-empty string (it's recorded as audit attribution), so this
 * is just a convenience list — the form allows free-text override.
 */
export const COMMON_AUTHORITIES = [
  'Branch Manager',
  'Branch Credit Manager',
  'Credit Manager',
  'Head Of Retail',
  'Head Of SME',
  'Head Of Corporate',
  'Director Retail Banking',
  'Director Commercial Banking',
  'Managing Director',
] as const;


// ── Credit workflow request bodies (v10.587) ────────────────────────────

export interface RequestInfoRequest {
  reasons?:   string[];
  documents?: string[];
  note?:      string;
}

export interface ProvideInfoRequest {
  documents?: string[];
  note?:      string;
}

export interface SignOfferRequest {
  note?:                string;
  attachment_filename?: string;
  attachment_ref?:      string;
}

export interface ValidateOfferRequest {
  approve: boolean;
  note?:   string;
}

export interface ConfirmToCreditAdminRequest {
  note?: string;
}

export interface CommitteeVoteRequest {
  member_id: string;
  vote:      string;   // YES | NO | ABSTAIN | RECUSED
  rationale?: string;
}

export interface ResolveCommitteeRequest {
  attending_member_ids?: string[];
  note?:                 string;
}
