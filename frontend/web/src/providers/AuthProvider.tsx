// v10.500 Phase 1 Batch 3a — Real AuthProvider.
//
// Replaces the v10.495 no-op stub. Owns the JWT token lifecycle for the
// React SPA. Scope is strictly token-level per separation-of-concerns:
// identity, role, and RBAC helpers remain authority of RoleProvider,
// which hydrates from /api/auth/whoami-detailed only once
// auth.status === 'authenticated'.
//
// Doctrine context (CGR1-grounded, see REVIVAL_LEDGER batch 3a):
//   - useRole (Batch 2d) and ProtectedRoute (Batch 2e) were structurally
//     correct shipments; they were operationally disconnected because
//     the auth substrate they assumed (this file) was a stub. Batch 3a
//     completes the circulation layer they depend on. 2d/2e remain
//     VALID under CGR1, not rollbacks.
//
// Architecture:
//   - Bearer-header JWT (no cookies — CSRF deferred to Phase 2)
//   - In-memory primary state via React useState
//   - localStorage persistence fallback for page-refresh continuity
//   - No refresh tokens (backend forbids; utils/auth_jwt.py:17-18)
//   - Central Authorization-header injection happens in lib/api.ts
//     via the token-accessor pattern wired below (setCurrentToken,
//     setOn401Callback). AuthProvider does not touch fetch directly
//     except for the login POST itself.
//
// CRITICAL — effect ordering discipline (hotfix from initial operator
// verification):
//   React effects fire bottom-up (child before parent). RoleProvider
//   is a CHILD of AuthProvider; its auth-status effect therefore fires
//   BEFORE AuthProvider's [state.token] effect can push the new token
//   into api.ts. To prevent the resulting "first whoami fires with no
//   Authorization header → 401 → spurious 'expired' transition" race,
//   every state path that updates the token MUST call setCurrentToken
//   synchronously BEFORE setState. The four affected paths are:
//     1. mount-time rehydration when localStorage has a valid token
//     2. login() success
//     3. logout()
//     4. the on401 callback (clears the dead token immediately)
//   The [state.token] useEffect remains as defense-in-depth, but the
//   sync calls are load-bearing. Any future code path that touches
//   token state MUST follow the same discipline.
//
// State machine:
//   'initializing'    → 'authenticated' | 'unauthenticated'  (on mount)
//   'authenticated'   → 'unauthenticated' (logout) | 'expired' (401)
//   'expired'         → 'authenticated' (next login)
//   'unauthenticated' → 'authenticated' (login)
//
// Storage keys (single source of truth, do not duplicate elsewhere):
//   localStorage['a2z_token']             — JWT string
//   localStorage['a2z_token_expires_at']  — ms-since-epoch as string
//
// Expiry safety margin: 30 seconds. A token expiring within 30s of
// now is treated as already expired, to avoid issuing a request the
// backend will reject mid-flight.

import {
  createContext, useCallback, useEffect, useState, type ReactNode,
} from 'react';
import type {
  AuthContextValue, AuthStatus, TokenResponse,
} from '@/types/auth';
import { setCurrentToken, setOn401Callback } from '@/lib/api';


// ── Storage keys + tunables (single source of truth) ────────────────────

const STORAGE_KEY_TOKEN       = 'a2z_token';
const STORAGE_KEY_EXPIRES     = 'a2z_token_expires_at';
const EXPIRY_SAFETY_MARGIN_MS = 30_000;
const LOGIN_ENDPOINT          = '/api/auth/login';


// ── Safe storage helpers ────────────────────────────────────────────────
// localStorage can throw in private mode, when quota is exceeded, or
// when disabled by policy. Silent degradation to in-memory-only is the
// correct fallback — the user simply loses F5 session continuity.

function safeStorageGet(key: string): string | null {
  try { return window.localStorage.getItem(key); }
  catch { return null; }
}
function safeStorageSet(key: string, value: string): void {
  try { window.localStorage.setItem(key, value); }
  catch { /* silent — degrade to in-memory */ }
}
function safeStorageRemove(key: string): void {
  try { window.localStorage.removeItem(key); }
  catch { /* silent */ }
}


// ── Context with a safe default ─────────────────────────────────────────
// Default 'initializing' status keeps RoleProvider's auth-gated fetch
// disarmed until the real provider mounts and resolves localStorage.
// If consumers ever appear above the provider in the tree (they
// shouldn't), the defaults fail safe: never authenticated, login/logout
// are no-ops.

export const AuthContext = createContext<AuthContextValue>({
  status:    'initializing',
  token:     null,
  expiresAt: null,
  error:     null,
  login:  async () => { /* no-op default */ },
  logout: () => { /* no-op default */ },
});


// ── Internal state shape ────────────────────────────────────────────────

interface AuthState {
  status:    AuthStatus;
  token:     string | null;
  expiresAt: number | null;
  error:     string | null;
}

const INITIAL_STATE: AuthState = {
  status:    'initializing',
  token:     null,
  expiresAt: null,
  error:     null,
};


// ── Provider component ──────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(INITIAL_STATE);

  // ── Mount: rehydrate from localStorage ────────────────────────────────
  // Runs exactly once. Reads stored token + expiry, validates the expiry
  // is still in the future (with safety margin), and transitions to
  // 'authenticated' or 'unauthenticated' accordingly.
  useEffect(() => {
    const storedToken   = safeStorageGet(STORAGE_KEY_TOKEN);
    const storedExpires = safeStorageGet(STORAGE_KEY_EXPIRES);

    if (!storedToken || !storedExpires) {
      setState({ ...INITIAL_STATE, status: 'unauthenticated' });
      return;
    }
    const expiresAt = Number(storedExpires);
    if (!Number.isFinite(expiresAt)
        || expiresAt <= Date.now() + EXPIRY_SAFETY_MARGIN_MS) {
      // Stale or unparseable — clean up and start fresh.
      safeStorageRemove(STORAGE_KEY_TOKEN);
      safeStorageRemove(STORAGE_KEY_EXPIRES);
      setState({ ...INITIAL_STATE, status: 'unauthenticated' });
      return;
    }
    // CRITICAL: register the token with api.ts BEFORE setState. React
    // effects fire bottom-up (child before parent) — without this sync
    // call, RoleProvider's auth-status effect fires before the
    // [state.token] safety-net effect below, sending its whoami fetch
    // with no Authorization header → 401 → spurious 'expired' transition.
    setCurrentToken(storedToken);
    setState({
      status:    'authenticated',
      token:     storedToken,
      expiresAt,
      error:     null,
    });
  }, []);

  // ── Defense-in-depth: token sync on every state change ────────────────
  // The login/logout/rehydration paths above call setCurrentToken
  // synchronously before setState — this is the load-bearing sync. This
  // effect catches any future code path that updates state.token without
  // remembering to sync. Idempotent: re-pushing the same value is free.
  useEffect(() => {
    setCurrentToken(state.token);
  }, [state.token]);

  // ── Register 401 callback once on mount ───────────────────────────────
  // When any authenticated fetch in api.ts receives a 401, it invokes
  // this callback to flip state to 'expired'. Re-render propagates to
  // ProtectedRoute which Navigates to /login.
  //
  // Functional setState ensures the only meaningful transition fired is
  // authenticated → expired. Other states already represent "no valid
  // token" so a 401 there is a no-op.
  useEffect(() => {
    setOn401Callback(() => {
      safeStorageRemove(STORAGE_KEY_TOKEN);
      safeStorageRemove(STORAGE_KEY_EXPIRES);
      // Clear api.ts token holder synchronously — any fetch firing
      // before the [state.token] effect runs would otherwise still
      // carry the dead token and produce a second redundant 401.
      setCurrentToken(null);
      setState((s) => (
        s.status === 'authenticated'
          ? { status: 'expired', token: null, expiresAt: null, error: null }
          : s
      ));
    });
    return () => setOn401Callback(null);
  }, []);

  // ── login action ──────────────────────────────────────────────────────
  // POST /api/auth/login → store token + expiry → transition to
  // 'authenticated'. Throws on failure so the Login form can render
  // the message inline; also stores the message in state so other
  // consumers (e.g. a logout-toast pattern) can render it too.
  //
  // Deliberately uses raw fetch here, NOT lib/api.ts's wrapper —
  // login is the bootstrap moment, it cannot depend on token
  // accessor state that doesn't exist yet.
  const login = useCallback(async (username: string, password: string) => {
    setState((s) => ({ ...s, error: null }));

    let res: Response;
    try {
      res = await fetch(LOGIN_ENDPOINT, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ username, password }),
      });
    } catch {
      const msg = 'Cannot reach authentication server. Please try again.';
      setState((s) => ({ ...s, error: msg }));
      throw new Error(msg);
    }

    if (res.status === 401) {
      const msg = 'Invalid username or password.';
      setState((s) => ({ ...s, error: msg }));
      throw new Error(msg);
    }
    if (res.status >= 500) {
      const msg = 'Authentication system unavailable. Please try again later.';
      setState((s) => ({ ...s, error: msg }));
      throw new Error(msg);
    }
    if (!res.ok) {
      const msg = `Login failed (HTTP ${res.status}).`;
      setState((s) => ({ ...s, error: msg }));
      throw new Error(msg);
    }

    let body: TokenResponse;
    try {
      body = await res.json() as TokenResponse;
    } catch {
      const msg = 'Authentication server returned an invalid response.';
      setState((s) => ({ ...s, error: msg }));
      throw new Error(msg);
    }

    if (!body.access_token
        || typeof body.expires_in_seconds !== 'number'
        || body.expires_in_seconds <= 0) {
      const msg = 'Authentication server returned an incomplete response.';
      setState((s) => ({ ...s, error: msg }));
      throw new Error(msg);
    }

    const expiresAt = Date.now() + body.expires_in_seconds * 1000;
    safeStorageSet(STORAGE_KEY_TOKEN,   body.access_token);
    safeStorageSet(STORAGE_KEY_EXPIRES, String(expiresAt));
    // CRITICAL: register the token with api.ts BEFORE setState. React
    // effects fire bottom-up (child before parent), so RoleProvider's
    // auth-status effect would otherwise fire fetchWhoamiDetailed
    // before the [state.token] safety-net effect runs — the request
    // would go out with no Authorization header, return 401, and
    // trigger a spurious 'expired' transition. This sync call closes
    // the race.
    setCurrentToken(body.access_token);
    setState({
      status:    'authenticated',
      token:     body.access_token,
      expiresAt,
      error:     null,
    });
  }, []);

  // ── logout action ─────────────────────────────────────────────────────
  // Client-side only. JWT is stateless; there is no server-side session
  // to invalidate (matches utils/auth_jwt.py contract). Clears storage,
  // clears state. ProtectedRoute will re-render and Navigate to /login.
  const logout = useCallback(() => {
    safeStorageRemove(STORAGE_KEY_TOKEN);
    safeStorageRemove(STORAGE_KEY_EXPIRES);
    // Sync-clear api.ts token holder; symmetric with the login sync.
    setCurrentToken(null);
    setState({
      status:    'unauthenticated',
      token:     null,
      expiresAt: null,
      error:     null,
    });
  }, []);

  // ── Assemble context value ────────────────────────────────────────────

  const value: AuthContextValue = {
    status:    state.status,
    token:     state.token,
    expiresAt: state.expiresAt,
    error:     state.error,
    login,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}
