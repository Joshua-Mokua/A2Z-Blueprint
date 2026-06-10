// v10.510 Phase 4 Batch β1 — TypeScript types for pipeline domain.
//
// These interfaces mirror the FastAPI backend's response shapes from:
//   - GET /api/pipeline/deals       (α1 — list, α2 — scope-filtered, α7 — permissions-enriched)
//   - GET /api/pipeline/deals/{id}  (α7 — single deal + permissions)
//
// Backend shape is defined by:
//   - utils/api_pipeline_models.py::PipelineDeal       (data shape, extra="allow")
//   - utils/api_pipeline_permissions.py::PERMISSION_KEYS  (the 6 permission booleans)
//
// If backend changes, this file changes. A future Stage C gate
// (gate_pipeline_types_contract_match) will enforce alignment by
// comparing TypeScript schema against backend Pydantic output.

// ── Permissions (α7 contract — audit Section 15.6 + GAP-012) ────────────
// Six booleans resolved server-side per (caller, deal) relationship.
// React reads these to decide which buttons to render — never duplicates
// the authorization logic in TypeScript.

export interface DealPermissions {
  /** Caller can see the deal at all. False → deal shouldn't appear. */
  can_view:             boolean;
  /** Edit deal fields. False for backup-only callers (Section 15.6:656). */
  can_edit:             boolean;
  /** Move stage forward. False on terminal stages (Closed Won/Lost). */
  can_advance_stage:    boolean;
  /** Request cancellation. False if already requested or terminal. */
  can_request_cancel:   boolean;
  /** Approve/reject pending cancel. Manager-only + needs pending request. */
  can_approve_cancel:   boolean;
  /** Validate or query the deal. Manager-only + must be validation stage. */
  can_validate:         boolean;
}

// ── Pipeline deal shape ─────────────────────────────────────────────────
// Matches PipelineDeal Pydantic model. Extra fields are tolerated
// (model has extra="allow") — TypeScript "[key: string]: unknown"
// index signature would catch them but reduces type safety for the
// known fields. Trade-off: explicit known fields, additional fields
// accessed by string keys when needed.

export interface PipelineDeal {
  // Identity
  id:                   string;
  client_name:          string;
  client_type?:         string;
  is_ntb?:              boolean;
  is_referral?:         boolean;

  // Staff attribution
  staff_code:           string;
  staff_name?:          string;
  backup_staff_codes?:  string[];

  // Pipeline classification
  stage:                string;
  pipeline_category?:   string;
  deal_category?:       string;       // legacy field, transitional compat
  product_type?:        string;
  product?:             string;
  unit?:                string;
  source?:              string;

  // Financials
  deal_value:           number;
  probability?:         number;
  currency?:            string;

  // Workflow timestamps
  created_at?:          string;
  updated_at?:          string;
  next_action?:         string;
  next_action_date?:    string;
  expected_close?:      string;

  // Manager validation
  manager_validated?:   boolean;
  validated_by?:        string;
  validated_at?:        string;
  validation_note?:     string;
  draft?:               boolean;

  // Cancellation lifecycle
  cancel_requested?:           boolean;
  cancel_requested_by?:        string;
  cancel_requested_at?:        string;
  cancel_reason?:              string;
  cancel_approved?:            boolean | null;
  cancel_approved_by?:         string;
  cancel_approved_at?:         string;
  cancel_note?:                string;

  // Portfolio conflict resolution (α5)
  portfolio_owner_code?:       string;
  portfolio_owner_name?:       string;
  bsc_credit_to?:              string;
  manager_override_note?:      string;

  // LMS handoff (α4)
  lms_application_id?:         string;
  loss_reason?:                string;

  // α7 per-deal permissions — added by the API enrichment layer
  permissions?:         DealPermissions;
}


// ── Response envelopes ──────────────────────────────────────────────────

export interface PipelineDealsListResponse {
  deals:    PipelineDeal[];
  count:    number;
  source:   string;   // 'pipeline_manager' per α1
}

export interface PipelineDealDetailResponse {
  deal:         PipelineDeal;
  permissions:  DealPermissions;
}


// ── Query parameter helpers ─────────────────────────────────────────────
// The list endpoint supports stage/category/unit filters + pagination.

export interface PipelineDealsQuery {
  stage?:     string;
  category?:  string;
  unit?:      string;
  offset?:    number;
  limit?:     number;
}


// ── Display helpers — pure data, no React ───────────────────────────────

/** Stage → Badge tone mapping. Drives PermissionBadges and DealCard. */
export const STAGE_TONE: Record<string, 'neutral' | 'info' | 'warning' | 'success' | 'danger'> = {
  // Early stages
  'Lead':         'neutral',
  'Contacted':    'info',
  'Qualified':    'info',
  'Proposal':     'info',
  'Negotiation':  'warning',
  'Compliance':   'warning',
  // LMS / credit stages
  'Credit Review':     'warning',
  'Approval':          'warning',
  'Bank Approval':     'warning',
  'Credit Committee':  'warning',
  'Documentation':     'info',
  'Vetting':           'info',
  'Disbursed':         'success',
  // Account / Deposit stages
  'Documentation Complete':  'info',
  'Negotiating':             'warning',
  'Account Opened':          'success',
  'Funded':                  'success',
  // Terminal
  'Closed Won':   'success',
  'Closed Lost':  'danger',
};

/** Get tone for an unknown stage — falls back to neutral. */
export function stageTone(stage: string): 'neutral' | 'info' | 'warning' | 'success' | 'danger' {
  return STAGE_TONE[stage] ?? 'neutral';
}
