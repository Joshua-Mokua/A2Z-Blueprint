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

export interface DealSlaStatus {
  state?:                  'on_track' | 'due_soon' | 'breached';
  clock?:                  'step' | 'age';
  step?:                   string | null;
  elapsed_business_days?:  number;
  target_days?:            number;
  remaining_business_days?: number;
  overdue_business_days?:  number;
  breached?:               boolean;
  escalate_to?:            string | null;
  commitment_status?:      'active' | 'unfulfilled' | null;
}

export interface PipelineDeal {
  // Identity
  id:                   string;
  client_name:          string;
  client_cif?:          string;     // δ2: CBS CIF when matched to a CBS customer
  client_type?:         string;
  is_ntb?:              boolean;
  is_referral?:         boolean;

  // Per-deal SLA status (attached by GET /api/pipeline/deals — Phase 4 #81)
  sla?:                 DealSlaStatus | null;

  /** Admin-authored win probability (0–100) DERIVED from the deal's current
   *  stage in its product flow (P-WP). Derived on read, never stored, so it
   *  auto-updates as the deal advances. Null when the stage has none set.
   *  Distinct from `probability` (the generic stage-weight forecast). */
  win_probability?:     number | null;

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
  /** KES-equivalent of deal_value (FCY deals); equals deal_value for LCY.
   * The pipeline reports in KES, so DISPLAY this, not the native deal_value. */
  amount_kes?:          number;
  currency_book?:       string;       // 'LCY' | 'FCY'
  probability?:         number;
  currency?:            string;

  // Workflow timestamps
  created_at?:          string;
  open_date?:           string;      // DB-sourced deals carry this (aging)
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

  // Referral lifecycle (A1 — refer an existing deal to another person)
  referral_status?:            string;   // 'pending' | 'accepted' | 'declined'
  referred_to?:                string;
  referred_to_code?:           string;
  referred_by_name?:           string;
  referred_by_code?:           string;
  referral_note?:              string;
  decline_reason?:             string;

  // LMS handoff (α4)
  lms_application_id?:         string;
  loss_reason?:                string;
  // Phase L — origination lock (submitted to credit; unless returned/info-requested)
  locked?:                     boolean;
  lock_reason?:                string;

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
  /** B17: this deal's product-class stage flow (admin config). The advance
   *  dropdown reads this instead of a flat hardcoded list. */
  stage_flow?:  string[];
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


// ── Admin-configured pipeline config (from /api/pipeline/stages) ─────────
// Single source of truth for category/stage/sector/decision-level dropdowns.
// Driven by data/pipeline_settings.json (Batch A2).

export interface PipelineStageConfig {
  stage:         string;
  description?:  string;
  color?:        string;
  prob_default?: number;
}

export interface DealCategoryConfig {
  category:     string;
  description?: string;
  stages:       string[];
  /** A2a: which product classes this category filters to (asset/liability/insurance/other). */
  product_class?: string[];
  /** A2a: "pipeline" = shown in create-deal dropdown; "dormant" = kept but hidden. */
  surface?:     string;
}

/** P4a: one stage in a product's flow, carrying its own SLA target (days). */
export interface ProductFlowStage {
  stage: string;
  target_days: number;
  /** P-WP: admin-authored win probability (0–100) for deals at this stage.
   *  Optional — a stage without it yields no derived probability. */
  win_probability?: number | null;
}
/** P4a: a single product's process flow — ordered stages (each with a target)
 * plus the client types that offer it (empty list = offered to all). */
export interface ProductFlow {
  client_types: string[];
  stages: ProductFlowStage[];
  required_documents?: string[];
  documents_required_at_stage?: string;
  committee_journey?: string[];
}

export interface PipelineConfig {
  stages:            PipelineStageConfig[];
  deal_categories:   DealCategoryConfig[];
  sectors:           string[];
  decision_levels:   string[];
  probability_map:   Record<string, number>;
  deal_types:        string[];
  product_catalogue: Record<string, string[]>;
  /** B17: per-product-class stage flows (asset/liability/insurance/other). */
  stage_flows?:      Record<string, string[]>;
  /** P4a: per-PRODUCT flows — each product's own stage sequence (with a
   * per-stage target_days) and the client types that offer it (empty = all). */
  product_flows?:    Record<string, ProductFlow>;
  /** Admin display-name map for segments (e.g. Ecobank: Mass/Retail→Direct). */
  segment_labels?:   Record<string, string>;
  /** Segment options per client type (Individual / Business). */
  customer_segments?: Record<string, string[]>;
  /** Client business lines (Consumer / Commercial / CIB), admin-configurable. */
  client_types?: { key: string; label: string; field: 'mou' | 'sector' }[];
  /** CBK economic-sector classification for BUSINESS clients (admin config). */
  business_sectors?: string[];
  /** Active partnership/MOU register for INDIVIDUAL clients. */
  individual_mous?: { id: string; title: string; partner_name?: string }[];
  /** Allow an "Other…" free-text fallback on the sector / MOU field. */
  allow_other_sector?: boolean;
  allow_other_mou?:    boolean;
  /** Deal-create fields the bank requires (admin-configured). */
  required_fields?:    string[];
  currency:          string;
}


// ── Mutation request bodies (v10.511 Phase 4 Batch β2) ──────────────────
// Match the FastAPI Pydantic models in utils/api_pipeline_models.py.

/** POST /api/pipeline/deals/{id}/advance — body shape. */
export interface AdvanceDealRequest {
  /** Target stage to advance to. Server validates against allowed stages. */
  target_stage: string;
  /** Optional probability override (server uses default if omitted). */
  probability?: number;
  /** Optional note recorded on the deal. */
  note?: string;
}

/** POST /api/pipeline/deals/{id}/cancel/request — body shape (α6). */
export interface RequestCancelRequest {
  /** Why the deal should be cancelled. Min 5 chars per server validation. */
  reason: string;
}


// ── Mutation response envelopes ────────────────────────────────────────
// Mutation endpoints return the updated deal + status metadata. Per α7
// design note, mutation responses do NOT carry a permissions object —
// the React UI refetches the list (or single deal) after mutation.

export interface AdvanceDealResponse {
  deal:                  PipelineDeal;
  status:                string;       // 'advanced' on success
  bsc_triggered?:        boolean;
  lms_triggered?:        boolean;
  lms_application_id?:   string;
  lms_error?:            string;
}

export interface RequestCancelResponse {
  deal:               PipelineDeal;
  status:             string;          // 'cancel_requested'
  cancel_requested:   boolean;
  awaiting_manager:   boolean;
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


/** Common target stages a user can advance a deal to.
 *
 * Conservative subset — the server validates the actual transition,
 * so this list doesn't need to encode the full stage graph (which is
 * a server-side concern per α3 doctrine). LMS-handoff stages (Credit
 * Review, Approval, etc.) are reachable via α4's allowlist but are
 * intentionally omitted from this dropdown — those transitions are
 * triggered server-side as side effects of advancing TO Compliance,
 * not by manually selecting them.
 *
 * If the server rejects an advance with 400, the React UI surfaces
 * the error message rather than pre-filtering options here.
 */
export const ADVANCE_TARGET_STAGES: readonly string[] = [
  'Contacted',
  'Qualified',
  'Proposal',
  'Negotiation',
  'Compliance',
  'Closed Won',
  'Closed Lost',
] as const;


// ── Pipeline category + stage scaffolding (v10.512 Phase 4 Batch β3) ────
//
// Mirrors the backend's ALLOWED_ADVANCE_STAGES set from
// utils/api_pipeline_mutations.py. Grouping by pipeline category so
// the create form can offer a sensible default stage dropdown.
//
// Drift warning: these constants are duplicated from the backend.
// A future batch SHOULD replace this with a GET /api/pipeline/stages
// endpoint that returns the canonical stage list. For β3 the duplication
// is accepted — the backend rejects invalid stages anyway, so drift
// would surface as a 400 error rather than a silent bug.

export const PIPELINE_CATEGORIES = ['Loan', 'Deposit', 'Account'] as const;
export type PipelineCategory = typeof PIPELINE_CATEGORIES[number];

/** Initial stages a deal can be created at, grouped by category.
 *  Subset of ALLOWED_ADVANCE_STAGES that excludes terminal stages
 *  (Closed Won / Closed Lost). */
export const INITIAL_STAGES_BY_CATEGORY: Record<PipelineCategory, readonly string[]> = {
  Loan:    ['Lead', 'Contacted', 'Qualified', 'Proposal', 'Negotiation', 'Compliance'],
  Deposit: ['Lead', 'Pitched', 'Negotiating', 'Funded'],
  Account: ['Lead', 'Information Gathered', 'Documentation Complete', 'Account Opened'],
} as const;

/** Common products as quick-pick suggestions for the create form.
 *  NOT exhaustive — the create form accepts arbitrary product_type
 *  strings and the server doesn't currently validate against a
 *  canonical list. β4 candidate: add GET /api/pipeline/products. */
export const COMMON_PRODUCTS_BY_CATEGORY: Record<PipelineCategory, readonly string[]> = {
  Loan: [
    'Business Loan',
    'Personal Loan',
    'Mortgage / Home Loan',
    'Overdraft',
    'Trade Finance',
    'Asset Finance',
    'LPO Finance',
    'Bancassurance',
  ],
  Deposit: [
    'Current Account (CASA)',
    'Savings Account (CASA)',
    'Fixed Deposit',
    'Call Deposit',
    'Business Current Account',
    'Business Savings',
  ],
  Account: [
    'Account Opening',
  ],
} as const;

/** Lead source options — mirrors Streamlit's source dropdown. */
export const SOURCE_OPTIONS: readonly string[] = [
  'Referral',
  'Existing relationship',
  'Walk-in',
  'Cold call',
  'Branch campaign',
  'Digital / online',
  'Partner / broker',
  'Other',
] as const;

/** Minimum length of manager override note when override semantics
 *  detected. Matches MIN_OVERRIDE_NOTE_LEN in
 *  utils/api_pipeline_mutations.py — kept in sync so client-side
 *  validation provides the same hint the server enforces. */
export const MIN_OVERRIDE_NOTE_LEN = 10;


// ── Create mutation request/response (β3) ───────────────────────────────
// Matches PipelineDealCreate from utils/api_pipeline_models.py.

export interface CreateDealRequest {
  // Required
  client_name:           string;
  staff_code:            string;
  staff_name:            string;
  deal_value:            number;
  product_type:          string;
  stage:                 string;

  // Optional but commonly supplied
  client_type?:          string;     // 'Individual' or 'Business'
  currency?:             string;     // ISO code; defaults KES (admin FX table)
  segment?:              string;     // segment within client type (cascade)
  sector?:               string;     // CBK economic sector (Business clients)
  mou_id?:               string;     // partnership/MOU id (Individual clients)
  mou_title?:            string;     // MOU title or free-text partner ("Other")
  client_cif?:           string;     // δ2: CBS CIF when client matched in CBS lookup
  is_ntb?:               boolean;
  pipeline_category?:    string;
  is_top_up?:            boolean;   // true if topping up an existing facility
  top_up_amount?:        number;    // the increment (becomes pipeline value)
  original_facility_amount?: number; // existing facility size (context only)
  probability?:          number;     // 0..1 (NOT 0..100)
  next_action?:          string;
  next_action_date?:     string;     // YYYY-MM-DD
  expected_close?:       string;     // YYYY-MM-DD
  notes?:                string;
  source?:               string;
  unit?:                 string;
  account_number?:       string;

  // Conflict resolution fields (β3)
  portfolio_owner_code?:    string;
  portfolio_owner_name?:    string;
  bsc_credit_to?:           string;
  manager_override_note?:   string;
}

export interface CreateDealResponse {
  deal:           PipelineDeal;
  status:         string;  // 'created'
  bsc_triggered:  boolean;
  // LMS fields are not populated for create (only advance), but
  // the server's response schema may include them as null.
  lms_triggered?:        boolean | null;
  lms_application_id?:   string | null;
  lms_error?:            string | null;
}


// ── Refer endpoint request/response (β3) ────────────────────────────────
// Matches PipelineDealRefer from utils/api_pipeline_models.py.

export interface ReferDealRequest {
  // Required
  client_name:            string;
  staff_code:             string;  // the referring RM
  staff_name:             string;
  portfolio_owner_code:   string;  // who's being referred TO
  portfolio_owner_name:   string;
  referred_to:            string;  // named recipient (often == portfolio_owner_name)

  // Optional
  referral_note?:         string;
  account_number?:        string;
  unit?:                  string;
}

export interface ReferDealResponse {
  deal:           PipelineDeal;
  status:         string;  // 'referred'
  bsc_triggered:  boolean;
}


// ── Manager queue types (v10.513 Phase 4 Batch β4) ──────────────────────
// Manager-only endpoints. Server enforces 403 on these for non-managers
// (per utils/api_pipeline_manager_actions.py::is_manager). React uses
// lib/role.ts::isManager to hide nav links + page guards as UX.

/** Validation queue: deals past Lead stage awaiting manager validation
 *  (manager_validated:false, stage in active set, not cancel_requested). */
export interface ValidationQueueResponse {
  deals:  PipelineDeal[];
  count:  number;
  queue:  'validation';
}

/** Cancellation queue: deals with cancel_requested:true AND
 *  cancel_approved:null/false (awaiting manager decision). */
export interface CancellationQueueResponse {
  deals:  PipelineDeal[];
  count:  number;
  queue:  'cancellation';
}


// ── Validate deal mutation (v10.513 Phase 4 Batch β4) ──────────────────
// POST /api/pipeline/deals/{id}/validate. Manager either VALIDATES
// (approved:true → deal joins forecast) or QUERIES (approved:false →
// deal returns to owner with note). Mirrors Streamlit pages/3_pipeline.py.

export interface ValidateDealRequest {
  /** True = validate (include in forecast); False = query (return to owner). */
  approved:  boolean;
  /** Manager's note. Server doesn't enforce length, matching Streamlit. */
  note?:     string;
}

export interface ValidateDealResponse {
  deal:           PipelineDeal;
  status:         string;  // 'validated' | 'queried' depending on approved
  bsc_triggered:  boolean;
}


// ── Approve/reject cancellation (v10.513 Phase 4 Batch β4) ──────────────
// POST /api/pipeline/deals/{id}/cancel/approve. Manager either APPROVES
// (approve:true → deal moves to Closed Lost) or REJECTS (approve:false →
// deal continues, cancel_requested flag cleared).

export interface ApproveCancelRequest {
  /** True = approve cancellation; False = reject (deal continues). */
  approve:   boolean;
  /** Manager's decision note. Visible on the deal for audit. */
  note?:     string;
}

export interface ApproveCancelResponse {
  deal:           PipelineDeal;
  status:         string;  // 'cancel_approved' | 'cancel_rejected'
  bsc_triggered:  boolean;
}


// ── Credit submission gate (v10.574 Batch B10) ─────────────────────────
// GET /api/pipeline/deals/{id}/credit-checklist response, and the
// POST /api/pipeline/deals/{id}/submit-to-credit response.

export interface CreditChecklistResponse {
  required:            string[];
  provided:            string[];
  missing:             string[];
  already_submitted:   boolean;
  lms_application_id:   string | null;
  can_submit:          boolean;
  current_stage?:      string;
  stage_required?:     string;
  stage_ok?:           boolean;
  cr_required?:        boolean;
  cr_ok?:              boolean;
  committee_ok?:       boolean;
  committee_pending?:  string[];
  committee_rejected?: string[];
}

export interface SubmitToCreditResponse {
  application_id:  string;
  status:          string;   // 'submitted_to_credit'
  missing:         string[];
}


// ── Pipeline analytics (B14/B15 backend) ────────────────────────────────
// GET /api/pipeline/analytics. Headline value is VALIDATED (manager-assured);
// pending_value is unvalidated active ("pending assurance"). Funnel is
// validated-only. Buckets sourced from admin product_catalogue.

export interface FunnelStage {
  stage:  string;
  count:  number;
  value:  number;
}

export interface OtherProduct {
  product:  string;
  value:    number;
  count:    number;
}

export interface OtherSubclass {
  subclass:  string;
  value:     number;
  count:     number;
  products:  OtherProduct[];
}

export interface PipelineBucket {
  label:          string;
  value:          number;        // assured (validated active)
  pending_value:  number;        // pending assurance (unvalidated active)
  weighted:       number;
  active_count:   number;
  pending_count:  number;
  won_value:      number;
  funnel:         FunnelStage[];
  breakdown?:     OtherSubclass[];   // only on the "other" bucket
}

export interface PipelineAnalyticsTotals {
  total_value:        number;    // validated active (assured)
  pending_value:      number;    // pending assurance
  weighted_value:     number;
  won_value:          number;
  active_count:       number;
  pending_count:      number;
  won_count:          number;
  lost_count:         number;
  live_count:         number;
  win_rate:           number;
  pending_validation: number;    // scope-aware: deals awaiting this manager
  pending_cancel:     number;
}

export interface ProductBreakdown { product: string; value: number; count: number; won_value: number }
export interface SectorBreakdown  { sector: string; value: number; count: number }
export interface SegmentBreakdown { segment: string; value: number; count: number }
export interface SegmentFunnel { segment: string; active_count: number; value: number; funnel: FunnelStage[] }
export interface UnitBreakdown    { unit: string; value: number; count: number }
export interface RmBreakdown      { rm: string; value: number; count: number }
export interface DrillDeal {
  id: string;
  client_name: string;
  product_type: string;
  stage: string;
  amount_kes: number;
  currency: string;
  staff_name: string;
  unit: string;
  expected_close: string | null;
  probability: number | null;
}
export interface PipelineDrillResponse {
  unit: string | null;
  rm: string | null;
  by_rm: RmBreakdown[];
  deals: DrillDeal[];
  totals: { value: number; count: number };
}
export interface CurrencyBookSplit { value: number; count: number }

export interface FunnelDrillDeal {
  id: string;
  client_name: string;
  product_type: string;
  segment: string;
  stage: string;
  amount_kes: number;
  staff_name: string;
  unit: string | null;
}
export interface FunnelDrillResponse {
  cls: string;
  stage: string;
  totals: { value: number; count: number };
  by_product: ProductBreakdown[];
  by_segment: SegmentBreakdown[];
  by_sector: SectorBreakdown[];
  deals: FunnelDrillDeal[];
}

export interface PipelineAnalyticsResponse {
  totals:       PipelineAnalyticsTotals;
  pipelines: {
    asset:      PipelineBucket;
    liability:  PipelineBucket;
    insurance:  PipelineBucket;
    other:      PipelineBucket;
  };
  funnel:       FunnelStage[];
  by_category:  unknown[];
  by_product?:        ProductBreakdown[];
  by_sector?:         SectorBreakdown[];
  by_segment?:        SegmentBreakdown[];
  by_segment_funnel?: SegmentFunnel[];
  by_currency_book?:  { LCY: CurrencyBookSplit; FCY: CurrencyBookSplit };
  by_unit?:           UnitBreakdown[];
  by_rm?:             RmBreakdown[];
}
