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
  /** Caller can record decision. Manager-tier, status=submitted|assigned. */
  can_record_decision:    boolean;
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


// ── LoanApplication shape ───────────────────────────────────────────────
// Matches LoanApplication Pydantic model with extra="allow". Known fields
// are explicit here; future backend additions tolerated via index signature.

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

  // Categorization
  proposition_tag?:       string;
  deal_category?:         string;

  // Provenance (α4 handoff)
  created_by?:            string;
  created_via?:           string;

  // Free text
  appraisal_notes?:       string;

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
  'credit_admin',
  'disbursed',
] as const;

export type ApplicationStatus = typeof APPLICATION_STATUSES[number];

/**
 * Visual tone mapping for status badges (mirrors stageTone in
 * types/pipeline.ts). Used by list and detail pages.
 */
export function statusTone(status: string | undefined): 'gray' | 'brand' | 'warning' | 'success' | 'danger' {
  if (!status) return 'gray';
  const s = status.toLowerCase();
  if (s === 'submitted')   return 'gray';
  if (s === 'assigned')    return 'brand';
  if (s === 'approved')    return 'success';
  if (s === 'disbursed')   return 'success';
  if (s === 'returned')    return 'warning';
  if (s === 'declined')    return 'danger';
  if (s === 'credit_admin') return 'brand';
  return 'gray';
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
