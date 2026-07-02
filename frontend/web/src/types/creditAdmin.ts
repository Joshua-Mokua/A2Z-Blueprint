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
  // Two-layer authorization (v10.585 / B20)
  can_request_authorization?: boolean;
  can_authorize?:             boolean;
}


// ── Condition (nested in case) ──────────────────────────────────────────

export interface CreditAdminCondition {
  type:        string;
  required?:   boolean;
  fulfilled?:  boolean;
  // P4-2: CP/CS first-class
  classification?: 'precedent' | 'subsequent';
  mandatory?:  boolean;
  due_date?:   string | null;
  date_set?:   string;
  date_met?:   string | null;
  officer?:    string;
  notes?:      string;
}


// ── P4 secured-lending structures ───────────────────────────────────────

export type SecurityClassification =
  | 'unsecured' | 'partially_secured' | 'fully_secured' | 'over_secured';

export interface LinkedCollateral {
  collateral_id:        string;
  collateral_type:      string;
  forced_sale_value?:   number;
  market_value?:        number | null;
  currency?:            string;
  allocated_value_kes?: number | null;
  valuation_date?:      string | null;
  linked_at?:           string;
}

export interface LegalReview {
  status:                 'not_started' | 'in_review' | 'queries_raised' | 'cleared' | 'rejected' | 'submitted_for_charging';
  assigned_officer_code?: string | null;
  assigned_officer_name?: string | null;
  outcome?:               'approved' | 'approved_with_conditions' | 'rejected' | null;
  comments?:              { author_code: string; text: string; at: string }[];
  started_at?:            string | null;
  completed_at?:          string | null;
  completed_by?:          string;
  submitted_for_charging_by?: string;
  submitted_for_charging_at?: string;
}

export interface SecurityPerfection {
  id:                      string;
  security_type:           string;
  registration_status:     'pending' | 'lodged' | 'registered' | 'failed';
  registration_reference?: string;
  registration_date?:      string | null;
  perfection_status:       'unperfected' | 'in_progress' | 'perfected' | 'lapsed';
  perfecting_officer_code?: string;
  notes?:                  string;
}

export interface InsurancePolicy {
  id:                   string;
  collateral_id?:       string;
  insurer:              string;
  policy_number:        string;
  sum_insured?:         number | null;
  currency?:            string;
  effective_date?:      string | null;
  expiry_date?:         string | null;
  bank_interest_noted?: boolean;
  status:               'active' | 'expired' | 'cancelled' | 'pending';
  renewal_alert_days?:  number;
}

export interface PerfectionOverride {
  status:             'pending' | 'authorized';
  requested_by?:      string;
  requested_at?:      string;
  justification?:     string;
  failures_bypassed?: GateFailure[];
  approvals?:         { role: string; approver: string; at: string }[];
  authorized_at?:     string;
}

export interface GateFailure {
  check:           string;
  reason:          string;
  needed?:         unknown;
  coverage_ratio?: number;
  required_ratio?: number;
  items?:          string[];
}

export interface DisbursementGate {
  passed:      boolean;
  failures:    GateFailure[];
  secured:     boolean;
  overridden:  boolean;
  high_value?: boolean;
  override?:   PerfectionOverride | null;
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

  // Two-layer authorization (v10.585 / B20)
  authorization_requested?:     boolean;
  authorization_requested_by?:  string;
  authorization_requested_at?:  string;
  authorized?:                  boolean;
  authorized_by?:               string;
  authorized_at?:               string;

  // P4 secured-lending (optional — present once classified/populated)
  facility_security_type?:   'unsecured' | 'secured';
  security_subtype?:         string | null;
  security_classification?:  SecurityClassification;
  coverage_ratio?:           number;
  required_ratio?:           number;
  security_total_kes?:       number;
  currency?:                 string;
  currency_book?:            'LCY' | 'FCY';
  amount_kes?:               number | null;
  linked_collateral?:        LinkedCollateral[];
  legal_review?:             LegalReview;
  security_perfections?:     SecurityPerfection[];
  insurance_policies?:       InsurancePolicy[];
  perfection_override?:      PerfectionOverride | null;
  disbursed_under_override?: boolean;

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


// ── Authorization request bodies (v10.585 / B20) ────────────────────────

export interface RequestAuthorizationRequest {
  note?: string;
}

export interface AuthorizeRequest {
  note?: string;
}


// ── P4 request bodies ───────────────────────────────────────────────────

export interface ClassifyConditionRequest {
  condition_type:  string;
  classification?: 'precedent' | 'subsequent';
  mandatory?:      boolean;
  due_date?:       string;
}

export interface ClassifyFacilityRequest {
  facility_security_type: 'unsecured' | 'secured';
  security_subtype?:      string;
}

export interface LinkCollateralRequest {
  collateral_id:        string;
  collateral_type:      string;
  forced_sale_value:    number;
  currency?:            string;
  market_value?:        number;
  allocated_value_kes?: number;
  valuation_date?:      string;
}

export interface LegalAssignRequest { officer_code: string; officer_name?: string }
export interface LegalCommentRequest { text: string; raises_query?: boolean }
export interface LegalOutcomeRequest {
  outcome: 'approved' | 'approved_with_conditions' | 'rejected';
  note?:   string;
}

export interface AddPerfectionRequest {
  security_type:           string;
  registration_reference?: string;
  registration_status?:    string;
  registration_date?:      string;
  perfection_status?:      string;
  officer_code?:           string;
  notes?:                  string;
}
export interface UpdatePerfectionRequest {
  registration_status?:    string;
  registration_reference?: string;
  registration_date?:      string;
  perfection_status?:      string;
  notes?:                  string;
}

export interface AddInsuranceRequest {
  insurer:              string;
  policy_number:        string;
  sum_insured?:         number;
  currency?:            string;
  effective_date?:      string;
  expiry_date?:         string;
  bank_interest_noted?: boolean;
  collateral_id?:       string;
  status?:              string;
  renewal_alert_days?:  number;
}

export interface OverrideRequestBody { justification: string }
