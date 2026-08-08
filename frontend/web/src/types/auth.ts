// v10.500 Phase 1 Batch 3a — TypeScript types for the FastAPI auth contract.
// v10.500 Phase 1 Batch 3b — extended with must_change_password rotation
//                            contract + 'must_rotate' AuthStatus.
//
// These interfaces are the contract between utils/api.py (auth endpoints)
// and the React auth substrate (AuthProvider, Login page, ChangePassword
// page, lib/api.ts).
//
// Backend Python returns dicts matching TokenResponse. If the FastAPI
// side changes (LoginRequest / TokenResponse / ChangePasswordRequest
// pydantic models in utils/api.py), this file must change in the same
// commit.
//
// Doctrine context (REVIVAL_LEDGER):
//   - Bearer-header JWT, no cookies (CSRF deferred to Phase 2)
//   - 30-minute token lifetime per utils/auth_jwt.py:52
//   - No refresh tokens per utils/auth_jwt.py:17-18 — re-login on expiry
//   - Token scopes (Batch 3b): "full" = full access; "must_rotate" = only
//     /api/auth/change-password is reachable. Full-scope tokens omit the
//     scope claim entirely for backward compat with pre-3b tokens still
//     in client localStorage.

// ── /api/auth/login request shape ───────────────────────────────────────
// Matches LoginRequest at utils/api.py:263-265.
export interface LoginRequest {
  username: string;
  password: string;
}

// ── /api/auth/login + /api/auth/change-password response shape ──────────
// Matches TokenResponse at utils/api.py. Both endpoints return the same
// shape so the React side can treat them uniformly. The `username` and
// `role` fields are present but AuthProvider deliberately does NOT
// persist them — identity remains RoleProvider's authority.
//
// `must_change_password` (Batch 3b):
//   - true  → access_token has scope='must_rotate'; only the
//             change-password endpoint will accept it; React routes the
//             user to /change-password and refuses other navigation.
//   - false → access_token has full scope (no scope claim on the wire);
//             normal authenticated flow.
export interface TokenResponse {
  access_token:          string;
  token_type:            'bearer';
  expires_in_seconds:    number;
  username:              string;
  role:                  string;
  must_change_password:  boolean;
}

// ── /api/auth/change-password request shape (Batch 3b) ──────────────────
// Matches ChangePasswordRequest pydantic model in utils/api.py. Both
// fields are required by the backend; client-side validation should
// pre-check before submission.
export interface ChangePasswordRequest {
  current_password: string;
  new_password:     string;
}

// ── AuthProvider state machine ──────────────────────────────────────────
// Five explicit states. RoleProvider must only fire its fetches while
// status === 'authenticated' (Batch 3a wiring) — 'must_rotate' tokens
// would be rejected by whoami-detailed with 403, so role hydration is
// deliberately deferred until rotation completes.
//
//   'initializing'    — provider just mounted, reading localStorage
//   'unauthenticated' — no valid token; user belongs on /login
//   'authenticated'   — full-scope token; protected routes open
//   'must_rotate'     — must_rotate-scope token; user confined to
//                       /change-password (Batch 3b)
//   'expired'         — was authenticated, but a 401 or stored-expiry
//                       check downgraded us; UX hint "session expired"
export type AuthStatus =
  | 'initializing'
  | 'unauthenticated'
  | 'authenticated'
  | 'must_rotate'
  | 'expired';

// ── AuthContext value shape ─────────────────────────────────────────────
// Strict token-lifecycle scope per separation-of-concerns doctrine.
// Do NOT add identity, role, or RBAC fields here — those belong on the
// RoleProvider side. `changePassword` (Batch 3b) rotates the password
// and transitions auth state from 'must_rotate' to 'authenticated' on
// success.
export interface AuthContextValue {
  status:    AuthStatus;
  token:     string | null;
  expiresAt: number | null;   // ms since epoch (Date.now() compatible)
  error:     string | null;   // last login OR rotation error

  login:          (username: string, password: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  logout:         () => void;
}
