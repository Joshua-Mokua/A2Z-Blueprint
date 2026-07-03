// v10.531 Phase 5 Batch γ2 — TypeScript types for CBS domain.
//
// Mirrors utils/cbs_manager.py row-to-dict serializers (γ1).
// Cross-reference: utils/api_cbs_routes.py endpoint contracts.


// ── Customer ─────────────────────────────────────────────────────────────

export interface CbsCustomer {
  cif:                          string;
  full_name:                    string;
  customer_type:                string;
  segment:                      string;
  sub_segment:                  string;
  sector:                       string;
  phone:                        string;
  email:                        string;
  date_onboarded:               string;
  branch_code:                  string;
  branch_name:                  string;
  region:                       string;
  county:                       string;
  relationship_manager_code:    string;
  kyc_status:                   string;
  risk_rating:                  string;
  is_dormant_customer:          boolean;
  preferred_currency:           string;
  total_deposit_balance:        number;
  total_loan_balance:           number;
  total_accounts:               number;
  aml_flag:                     boolean;
  fatf_flag:                    boolean;
  pep_flag:                     boolean;
}


// ── Account ──────────────────────────────────────────────────────────────

export interface CbsAccount {
  account_number:     string;
  cif:                string;
  branch_code:        string;
  branch_name:        string;
  account_type_name:  string;
  category:           string;
  currency:           string;
  date_opened:        string;
  current_balance:    number;
  available_balance:  number;
  account_status:     string;
  dormancy_status:    string;
  interest_rate:      number;
  loan_outstanding:   number;
  npl_status:         string;
  npl_days:           number;
}


// ── Branch (35 rows) ─────────────────────────────────────────────────────

export interface CbsBranch {
  branch_code:   string;
  branch_name:   string;
  region:        string;
  county:        string;
  town:          string;
  branch_type:   string;
  tier:          number;
}


// ── Response shapes ──────────────────────────────────────────────────────

export interface CbsCustomerSearchResponse {
  customers:  CbsCustomer[];
  count:      number;
  query:      string;
  source:     string;
}

export interface CbsCustomerResponse {
  customer:   CbsCustomer;
  source:     string;
}

export interface CbsAccountsResponse {
  accounts:   CbsAccount[];
  count:      number;
  cif:        string;
  source:     string;
}

export interface CbsBranchesResponse {
  branches:   CbsBranch[];
  count:      number;
  source:     string;
}

export interface CbsAggregatesResponse {
  aggregates: Record<string, unknown>;
  source:     string;
}


// ── Helper: customer_type derivation for Pipeline autofill ───────────────

/**
 * Maps CBS segment → Pipeline customer_type.
 * Pipeline distinguishes only Individual vs Business; CBS has finer
 * segments (RETAIL_INDIVIDUAL, SME, CORPORATE, STAFF). Staff is a
 * weird edge case — defaulting to Individual since it's a person.
 */
export function segmentToCustomerType(segment: string): 'Individual' | 'Business' {
  const s = segment.toUpperCase();
  if (s === 'SME' || s === 'CORPORATE') return 'Business';
  return 'Individual';
}


/** Color tone for risk_rating badges. */
export function riskRatingTone(risk: string): 'success' | 'warning' | 'danger' | 'neutral' {
  const r = risk.toUpperCase();
  if (r === 'LOW')        return 'success';
  if (r === 'MEDIUM')     return 'warning';
  if (r === 'HIGH')       return 'danger';
  if (r === 'PROHIBITED') return 'danger';
  return 'neutral';
}


// ── Account-number lookup (live FlexCube or CSV fallback) ────────────────

/**
 * Fields added by the live FlexCube path (CUSTOMERACCOUNTDETAILS script).
 * All optional so the shape stays valid when the CSV fallback is used.
 */
export interface CbsAccountFlexcubeFields {
  f7_cif?:       string;  // ext_ref_no — key for CUSTOMERACTIVELOANS
  f12_cif?:      string;  // internal customer_no
  customer_name?: string;
  segment?:       string;
  kyc_status?:    string;
  risk_rating?:   string;
  aml_flag?:      boolean;
  pep_flag?:      boolean;
  rm_code?:       string;
}

export interface CbsActiveLoan {
  account_number:    string;
  loan_status_label: string;
  total_outstanding: number | string;
  currency?:         string;
  product_name?:     string;
  npl_days?:         number;
  [key: string]:     unknown;
}

/** Account + customer summary from /api/cbs/accounts/{num} */
export type CbsAccountDetail = CbsAccount & CbsAccountFlexcubeFields;

/** Combined payload from /api/cbs/accounts/{num}/360 */
export type CbsAccount360 = CbsAccountDetail & {
  active_loans:           CbsActiveLoan[];
  active_loans_count:     number;
  total_loan_outstanding: number;
};

export interface CbsAccountDetailResponse {
  account: CbsAccountDetail;
  source:  string;
}

export interface CbsAccount360Response {
  account: CbsAccount360;
  source:  string;
}


/** Color tone for kyc_status badges. */
export function kycStatusTone(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
  const s = status.toUpperCase();
  if (s === 'COMPLETE' || s === 'COMPLIANT' || s === 'OK') return 'success';
  if (s === 'PENDING' || s === 'EXPIRING')                  return 'warning';
  if (s === 'EXPIRED' || s === 'REJECTED')                  return 'danger';
  return 'neutral';
}
