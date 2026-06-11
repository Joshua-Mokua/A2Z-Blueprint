// v10.522 Phase 4 Batch β6 — TypeScript types for the Credit Admin (CALMS) domain.
//
// Mirrors utils/api_credit_admin_models.py (α9). Cross-reference:
// docs/architecture/PIPELINE_DOMAIN_AUDIT.md Section 19 for the α9
// doctrine, docs/architecture/API_CONTRACTS.md for endpoint contracts.
//
// Type-check discipline (β5-hotfix lesson): all tone/stripe/variant
// values referenced here must come from the primitive type unions
// declared in components/{Badge,Card,Button}.tsx and lib/tokens.ts.


// ── Permissions (α9 contract — Section 19.3) ────────────────────────────

export interface CreditAdminPermissions {
  can_view:                boolean;
  can_fulfill_condition:   boolean;
  can_disburse:            boolean;
}


// ── Condition (nested in case) ──────────────────────────────────────────

export interface CreditAdminCondition {
  type:        string;
  required?:   boolean;
  fulfilled?:  boolean;
  date_set?:   string;
  date_met?:   string | null;
  officer?:    string;
  notes?:      string;
}


// ── CreditAdminCase shape ───────────────────────────────────────────────

export interface CreditAdminCase {
  // Identity
  id:                    string;
  application_id:        string;

  // Denormalized from LMS
  client_name:           string;
  product?:              string;
  amount?:               number;

  // Ownership
  rm_code?:              string;
  rm_name?:              string;

  // Lifecycle
  approval_date?:        string;
  last_updated?:         string;

  // Conditions
  conditions:            CreditAdminCondition[];

  // Computed gates
  all_conditions_met?:       boolean;
  ready_for_disbursement?:   boolean;
  disbursed?:                boolean;
  disbursement_date?:        string | null;

  // Extra tolerated
  [key: string]:         unknown;
}


// ── Response shapes ─────────────────────────────────────────────────────

export interface CreditAdminCasesResponse {
  cases:                 CreditAdminCase[];
  count:                 number;
  source:                string;
}

export interface CreditAdminCaseDetailResponse {
  case:                  CreditAdminCase;
  permissions:           CreditAdminPermissions;
  source:                string;
}

export interface CreditAdminMutationResponse {
  case:                  CreditAdminCase;
  status:                string;
}


// ── Request body shapes ─────────────────────────────────────────────────

export interface FulfillConditionRequest {
  condition_type:        string;
  officer_name:          string;
  notes?:                string;
}

export interface DisburseCaseRequest {
  authority:             string;
  comments?:             string;
}


// ── Helper constants ─────────────────────────────────────────────────────

/**
 * Status categories used by the list page filter chips.
 * Cases don't have a single 'status' string like LMS does — they have
 * a combination of {all_conditions_met, ready_for_disbursement, disbursed}.
 * The list page maps cases into one of these UX categories for filtering.
 */
export const CASE_CATEGORIES = [
  'all',
  'pending_conditions',      // !all_conditions_met
  'ready_for_disbursement',  // all_conditions_met && !ready_for_disbursement
  'cleared',                 // ready_for_disbursement && !disbursed
  'disbursed',               // disbursed
] as const;

export type CaseCategory = typeof CASE_CATEGORIES[number];

export function caseCategoryLabel(cat: CaseCategory): string {
  switch (cat) {
    case 'all':                    return 'All';
    case 'pending_conditions':     return 'Pending conditions';
    case 'ready_for_disbursement': return 'Ready for clearance';
    case 'cleared':                return 'Cleared (awaiting funds)';
    case 'disbursed':              return 'Disbursed';
  }
}

/** Categorize a single case for the list-page filter. */
export function categorizeCase(c: CreditAdminCase): Exclude<CaseCategory, 'all'> {
  if (c.disbursed)               return 'disbursed';
  if (c.ready_for_disbursement)  return 'cleared';
  if (c.all_conditions_met)      return 'ready_for_disbursement';
  return 'pending_conditions';
}

/**
 * Visual tone for case-status badges. Returns BadgeTone-compatible
 * values only (no 'gray' — use 'neutral').
 */
export function caseStatusTone(c: CreditAdminCase): 'neutral' | 'brand' | 'success' | 'warning' {
  if (c.disbursed)               return 'success';
  if (c.ready_for_disbursement)  return 'brand';
  if (c.all_conditions_met)      return 'warning';   // ready but not yet cleared by manager
  return 'neutral';
}

export function caseStatusLabel(c: CreditAdminCase): string {
  if (c.disbursed)               return 'disbursed';
  if (c.ready_for_disbursement)  return 'cleared';
  if (c.all_conditions_met)      return 'awaiting clearance';
  return 'pending conditions';
}

/** Common authority labels for the Disburse form. */
export const COMMON_DISBURSE_AUTHORITIES = [
  'Credit Manager',
  'Branch Credit Manager',
  'Branch Manager',
  'Head Of Retail',
  'Head Of SME',
  'Head Of Corporate',
  'Director Retail Banking',
  'Director Commercial Banking',
  'Managing Director',
] as const;
