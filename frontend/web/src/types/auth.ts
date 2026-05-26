// v10.500 Phase 1 Batch 3a — TypeScript types for the FastAPI auth contract.
//
// These interfaces are the contract between utils/api.py (auth endpoints)
// and the React auth substrate (AuthProvider, Login page, lib/api.ts).
//
// Backend Python returns dicts matching TokenResponse. If the FastAPI
// side changes (LoginRequest / TokenResponse pydantic models in
// utils/api.py:263-273), this file must change in the same commit.
//
// Doctrine context (REVIVAL_LEDGER batch 3a):
//   - Bearer-header JWT, no cookies (CSRF deferred to Phase 2)
//   - 30-minute token lifetime per utils/auth_jwt.py:52
//   - No refresh tokens per utils/auth_jwt.py:17-18 — re-login on expiry

// ── /api/auth/login request shape ───────────────────────────────────────
// Matches LoginRequest at utils/api.py:263-265.
export interface LoginRequest {
  username: string;
  password: string;
}

// ── /api/auth/login success response shape ──────────────────────────────
// Matches TokenResponse at utils/api.py:268-273. The `username` and
// `role` fields are present in the response but AuthProvider deliberately
// does NOT persist them — identity is the authority of RoleProvider,
// which hydrates from /api/auth/whoami-detailed once authenticated.
export interface TokenResponse {
  access_token:        string;
  token_type:          'bearer';
  expires_in_seconds:  number;
  username:            string;
  role:                string;
}

// ── AuthProvider state machine ──────────────────────────────────────────
// Four explicit states. RoleProvider must only fire its fetches while
// status === 'authenticated' (Batch 3a wiring).
//
//   'initializing'    — provider just mounted, reading localStorage
//   'unauthenticated' — no valid token; user belongs on /login
//   'authenticated'   — valid token in state; protected routes open
//   'expired'         — was authenticated, but a 401 or stored-expiry
//                       check downgraded us; UX hint "session expired"
//                       vs cold "please log in"
export type AuthStatus =
  | 'initializing'
  | 'unauthenticated'
  | 'authenticated'
  | 'expired';

// ── AuthContext value shape ─────────────────────────────────────────────
// Strict token-lifecycle scope per the separation-of-concerns doctrine.
// Do NOT add identity, role, or RBAC fields here — those belong on the
// RoleProvider side.
export interface AuthContextValue {
  status:    AuthStatus;
  token:     string | null;
  expiresAt: number | null;   // ms since epoch (Date.now() compatible)
  error:     string | null;   // last login error, cleared on next attempt

  login:  (username: string, password: string) => Promise<void>;
  logout: () => void;
}
