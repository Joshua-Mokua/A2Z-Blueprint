// v10.499 Stage C Batch 2d — TypeScript types for role-related API responses.
//
// These interfaces are the contract between the FastAPI backend
// (utils/api.py::whoami_detailed and utils/api_roles.py::get_role_registry)
// and the React frontend (providers/RoleProvider, hooks/useRole).
//
// Backend Python returns dicts matching these shapes. If you change one
// side, change the other. Audit gates (future) will enforce alignment.
//
// Validated against actual runtime output captured 2026-05-24:
//   whoami-detailed: 17 fields, email nullable, accessible/hidden_modules
//                    are arrays of strings, expires_at is ISO 8601 string
//   registry: enums has 3 arrays (tiers/sbus/scopes), roles is array of
//             6-field objects, total_classified_roles is number


// ── Constants matching role_taxonomy.py ─────────────────────────────────
// These string unions document the canonical enum values. The runtime
// arrays from /api/roles/registry are the source of truth at runtime;
// these compile-time unions catch typos during development.

export type Tier =
  | 'portfolio_owner'
  | 'proposition_owner'
  | 'structural_owner'
  | 'service'
  | 'support';

export type BranchScope =
  | 'branch_bound'
  | 'head_office'
  | 'national';

export type Sbu =
  | 'Retail Banking'
  | 'Commercial Banking'
  | 'Corporate Banking'
  | 'Treasury'
  | 'Digital_Agency'
  | 'Support'
  | 'Executive';


// ── /api/auth/whoami-detailed response shape ────────────────────────────
// Returned by GET /api/auth/whoami-detailed (utils/api.py).
// Auth: any authenticated user. Returns the caller's own identity.

export interface UserIdentity {
  // Identity (from users.json)
  username:   string;
  staff_code: string;
  full_name:  string;
  department: string;
  email:      string | null;   // optional in users.json; serialises to null when missing
  active:     boolean;

  // Role (raw + classified via role_taxonomy)
  role:           string;
  tier:           Tier;
  sbu:            Sbu;
  branch_scope:   BranchScope;
  matched_via:    string;       // 'explicit' or 'keyword_fallback:<keyword>'
  can_be_tagged:  boolean;

  // Capability flags
  is_admin:      boolean;
  can_view_all:  boolean;

  // Streamlit RBAC migration-compat (React will phase these out)
  accessible_modules: string[];
  hidden_modules:     string[];

  // Token timing
  expires_at: string | null;    // ISO 8601 string; null if no exp claim
}


// ── /api/roles/registry response shape ──────────────────────────────────
// Returned by GET /api/roles/registry (utils/api_roles.py).
// Auth: any authenticated user. Returns the canonical role schema.

export interface RoleClassification {
  role:           string;
  tier:           Tier;
  branch_scope:   BranchScope;
  sbu:            Sbu;
  matched_via:    string;       // always 'explicit' in this endpoint
  can_be_tagged:  boolean;
}

export interface RoleRegistry {
  enums: {
    tiers:  Tier[];
    sbus:   Sbu[];
    scopes: BranchScope[];
  };
  roles: RoleClassification[];
  total_classified_roles: number;
}