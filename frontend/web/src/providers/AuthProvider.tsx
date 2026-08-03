// v10.500 Phase 1 Batch 3a — Real AuthProvider.
// v10.500 Phase 1 Batch 3b — extended with must_rotate state + changePassword action.
//
// Replaces the v10.495 no-op stub. Owns the JWT token lifecycle for the
// React SPA. Scope is strictly token-level per separation-of-concerns:
// identity, role, and RBAC helpers remain authority of RoleProvider,
// which hydrates from /api/auth/whoami-detailed only once
// auth.status === 'authenticated'.
//
// Doctrine context (CGR1-grounded, see REVIVAL_LEDGER batch 3a/3b):
//   - useRole (Batch 2d) and ProtectedRoute (Batch 2e) were structurally
//     correct shipments operationally completed by Batch 3a. They remain
//     VALID under CGR1.
//   - Batch 3b adds the rotation contract: when /api/auth/login returns
//     must_change_password=true, the access_token has scope='must_rotate'
//     and AuthProvider transitions to status='must_rotate'. The user is
//     confined to /change-password until they successfully rotate.
//     ProtectedRoute is path-aware: it permits /change-password under
//     must_rotate and redirects every other route there.
//
// Architecture:
//   - Bearer-header JWT (no cookies — CSRF deferred to Phase 2)
//   - In-memory primary state via React useState
//   - localStorage persistence fallback for page-refresh continuity
//   - No refresh tokens (backend forbids; utils/auth_jwt.py:17-18)
//   - Central Authorization-header injection happens in lib/api.ts
//     via the token-accessor pattern (setCurrentToken, setOn401Callback)
//
// CRITICAL — effect ordering discipline (from Batch 3a hotfix):
//   React effects fire bottom-up (child before parent). RoleProvider
//   is a CHILD of AuthProvider; its auth-status effect therefore fires
//   BEFORE AuthProvider's [state.token] effect can push the new token
//   into api.ts. To prevent the resulting "first whoami fires with no
//   Authorization header → 401 → spurious 'expired' transition" race,
//   every state path that updates the token MUST call setCurrentToken
//   synchronously BEFORE setState. The five affected paths are:
//     1. mount-time rehydration when localStorage has a valid token
//     2. login() success
//     3. changePassword() success  (Batch 3b)
//     4. logout()
//     5. the on401 callback (clears the dead token immediately)
//   The [state.token] useEffect remains as defense-in-depth, but the
//   sync calls are load-bearing.
//
// State machine:
//   'initializing'    → 'authenticated' | 'unauthenticated' | 'must_rotate' (on mount)
//   'unauthenticated' → 'authenticated' (login) | 'must_rotate' (login + flag)
//   'must_rotate'     → 'authenticated' (changePassword success)
//                     → 'unauthenticated' (logout) | 'expired' (401)
//   'authenticated'   → 'unauthenticated' (logout) | 'expired' (401)
//   'expired'         → any login attempt path
//
// Storage keys (single source of truth, do not duplicate elsewhere):
//   localStorage['a2z_token']             — JWT string
//   localStorage['a2z_token_expires_at']  — ms-since-epoch as string
//   localStorage['a2z_must_rotate']       — 'true' when token is must_rotate-scope
//                                           (Batch 3b; absent or 'false' = full)
//
// Expiry safety margin: 30 seconds.

import {
  createContext, useCallback, useEffect, useState, type ReactNode,
} from 'react';
import type {
  AuthContextValue, AuthStatus, TokenResponse,
} from '@/types/auth';
import { setCurrentToken, setOn401Callback } from '@/lib/api';


// ── Storage keys + tunables (single source of truth) ────────────────────

const STORAGE_KEY_TOKEN           = 'a2z_token';
const STORAGE_KEY_EXPIRES         = 'a2z_token_expires_at';
const STORAGE_KEY_MUST_ROTATE     = 'a2z_must_rotate';
const STORAGE_KEY_MUST_SET_STAFF  = 'a2z_must_set_staff_id';
const EXPIRY_SAFETY_MARGIN_MS   = 30_000;
const LOGIN_ENDPOINT            = '/api/auth/login';
const CHANGE_PASSWORD_ENDPOINT  = '/api/auth/change-password';
const SET_STAFF_ID_ENDPOINT     = '/api/auth/set-staff-id';


// ── Safe storage helpers ────────────────────────────────────────────────

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

function clearAllAuthStorage(): void {
  safeStorageRemove(STORAGE_KEY_TOKEN);
  safeStorageRemove(STORAGE_KEY_EXPIRES);
  safeStorageRemove(STORAGE_KEY_MUST_ROTATE);
  safeStorageRemove(STORAGE_KEY_MUST_SET_STAFF);
}


// ── Context with a safe default ─────────────────────────────────────────

export const AuthContext = createContext<AuthContextValue>({
  status:    'initializing',
  token:     null,
  expiresAt: null,
  error:     null,
  mustSetStaffId:  false,
  login:           async () => { /* no-op default */ },
  changePassword:  async () => { /* no-op default */ },
  setStaffId:      async () => { /* no-op default */ },
  logout:          () => { /* no-op default */ },
});


// ── Internal state shape ────────────────────────────────────────────────

interface AuthState {
  status:    AuthStatus;
  token:     string | null;
  expiresAt: number | null;
  error:     string | null;
  mustSetStaffId: boolean;
}

const INITIAL_STATE: AuthState = {
  status:    'initializing',
  token:     null,
  expiresAt: null,
  error:     null,
  mustSetStaffId: false,
};


// ── Provider component ──────────────────────────────────────────────────

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(INITIAL_STATE);

  // ── Mount: rehydrate from localStorage ────────────────────────────────
  useEffect(() => {
    const storedToken     = safeStorageGet(STORAGE_KEY_TOKEN);
    const storedExpires   = safeStorageGet(STORAGE_KEY_EXPIRES);
    const storedMustRotate = safeStorageGet(STORAGE_KEY_MUST_ROTATE) === 'true';
    const storedMustSetStaffId = safeStorageGet(STORAGE_KEY_MUST_SET_STAFF) === 'true';

    if (!storedToken || !storedExpires) {
      setState({ ...INITIAL_STATE, status: 'unauthenticated' });
      return;
    }
    const expiresAt = Number(storedExpires);
    if (!Number.isFinite(expiresAt)
        || expiresAt <= Date.now() + EXPIRY_SAFETY_MARGIN_MS) {
      clearAllAuthStorage();
      setState({ ...INITIAL_STATE, status: 'unauthenticated' });
      return;
    }
    // CRITICAL: sync setCurrentToken BEFORE setState (effect ordering).
    setCurrentToken(storedToken);
    setState({
      status:    storedMustRotate ? 'must_rotate' : 'authenticated',
      token:     storedToken,
      expiresAt,
      error:     null,
      mustSetStaffId: storedMustSetStaffId,
    });
  }, []);

  // ── Defense-in-depth: token sync on every state change ────────────────
  useEffect(() => {
    setCurrentToken(state.token);
  }, [state.token]);

  // ── Register 401 callback once on mount ───────────────────────────────
  useEffect(() => {
    setOn401Callback(() => {
      clearAllAuthStorage();
      setCurrentToken(null);
      setState((s) => (
        (s.status === 'authenticated' || s.status === 'must_rotate')
          ? { status: 'expired', token: null, expiresAt: null, error: null, mustSetStaffId: false }
          : s
      ));
    });
    return () => setOn401Callback(null);
  }, []);

  // ── login action ──────────────────────────────────────────────────────
  // POST /api/auth/login. On success, transitions to 'authenticated' OR
  // 'must_rotate' based on the must_change_password flag in the response
  // (Batch 3b). Token is stored either way; only the status differs.
  const login = useCallback(async (username: string, password: string) => {
    setState((s) => ({ ...s, error: null }));

    // AD auth (utils/external_auth.py) waits up to ad_timeout_seconds
    // (default 20s) before falling back to local auth, which then also has
    // to run — a slow AD server can legitimately take 20+ seconds to fail.
    // 30s gives that headroom before the CLIENT gives up and reports a
    // network error, rather than the request hanging indefinitely on a
    // truly dead connection.
    const LOGIN_TIMEOUT_MS = 30_000;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), LOGIN_TIMEOUT_MS);

    let res: Response;
    try {
      res = await fetch(LOGIN_ENDPOINT, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ username, password }),
        signal:  controller.signal,
      });
    } catch (err) {
      const msg = (err instanceof DOMException && err.name === 'AbortError')
        ? 'The authentication server took too long to respond. Please try again.'
        : 'Cannot reach authentication server. Please try again.';
      setState((s) => ({ ...s, error: msg }));
      throw new Error(msg);
    } finally {
      clearTimeout(timer);
    }

    if (res.status === 401) {
      const msg = 'Invalid username or password.';
      setState((s) => ({ ...s, error: msg }));
      throw new Error(msg);
    }
    if (res.status === 504) {
      // Backend distinguishes "AD server didn't respond in time" from
      // "credentials were checked and rejected" — surface its own message
      // rather than the generic 5xx one below, since the fix is "try again",
      // not "check your password".
      let msg = 'The authentication server did not respond in time. Please try again.';
      try {
        const body = await res.json();
        if (body && typeof body.detail === 'string') msg = body.detail;
      } catch { /* keep default */ }
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
    const mustRotate = body.must_change_password === true;
    const mustSetStaffId = body.must_set_staff_id === true;

    safeStorageSet(STORAGE_KEY_TOKEN,   body.access_token);
    safeStorageSet(STORAGE_KEY_EXPIRES, String(expiresAt));
    if (mustRotate) {
      safeStorageSet(STORAGE_KEY_MUST_ROTATE, 'true');
    } else {
      safeStorageRemove(STORAGE_KEY_MUST_ROTATE);
    }
    if (mustSetStaffId) {
      safeStorageSet(STORAGE_KEY_MUST_SET_STAFF, 'true');
    } else {
      safeStorageRemove(STORAGE_KEY_MUST_SET_STAFF);
    }
    // CRITICAL: sync token BEFORE setState (race fix).
    setCurrentToken(body.access_token);
    setState({
      status:    mustRotate ? 'must_rotate' : 'authenticated',
      token:     body.access_token,
      expiresAt,
      error:     null,
      mustSetStaffId,
    });
  }, []);

  // ── changePassword action (Batch 3b) ──────────────────────────────────
  // POST /api/auth/change-password. Accepts BOTH must_rotate-scope (the
  // forced-rotation path) and full-scope (future voluntary path) tokens.
  // On success the backend returns a fresh full-scope token; we swap it
  // in and transition to 'authenticated'.
  //
  // The fetch uses raw fetch + manual Authorization header rather than
  // going through lib/api.ts's getJson, because (a) getJson is GET-only
  // and (b) we want explicit control over the request shape for this
  // bootstrap-adjacent flow. The token from state is attached directly.
  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) => {
      setState((s) => ({ ...s, error: null }));

      const currentToken = state.token;
      if (!currentToken) {
        const msg = 'You must be signed in to change your password.';
        setState((s) => ({ ...s, error: msg }));
        throw new Error(msg);
      }

      let res: Response;
      try {
        res = await fetch(CHANGE_PASSWORD_ENDPOINT, {
          method:  'POST',
          headers: {
            'Content-Type':  'application/json',
            'Authorization': `Bearer ${currentToken}`,
          },
          body: JSON.stringify({
            current_password: currentPassword,
            new_password:     newPassword,
          }),
        });
      } catch {
        const msg = 'Cannot reach authentication server. Please try again.';
        setState((s) => ({ ...s, error: msg }));
        throw new Error(msg);
      }

      if (res.status === 401) {
        // Backend says current_password is wrong OR token is invalid.
        // We can't easily distinguish — surface the most likely cause.
        const msg = 'Current password is incorrect.';
        setState((s) => ({ ...s, error: msg }));
        throw new Error(msg);
      }
      if (res.status === 400) {
        // Validation failure — read the detail string from the response.
        let detail = 'Password does not meet requirements.';
        try {
          const body = await res.json();
          if (body && typeof body.detail === 'string') detail = body.detail;
        } catch { /* keep default */ }
        setState((s) => ({ ...s, error: detail }));
        throw new Error(detail);
      }
      if (res.status >= 500) {
        const msg = 'Authentication system unavailable. Please try again later.';
        setState((s) => ({ ...s, error: msg }));
        throw new Error(msg);
      }
      if (!res.ok) {
        const msg = `Password change failed (HTTP ${res.status}).`;
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

      // Success — swap in the fresh full-scope token. Clear the
      // must_rotate flag in storage so a subsequent F5 lands in
      // 'authenticated', not 'must_rotate'.
      const expiresAt = Date.now() + body.expires_in_seconds * 1000;
      const mustSetStaffId = body.must_set_staff_id === true;
      safeStorageSet(STORAGE_KEY_TOKEN,   body.access_token);
      safeStorageSet(STORAGE_KEY_EXPIRES, String(expiresAt));
      safeStorageRemove(STORAGE_KEY_MUST_ROTATE);
      if (mustSetStaffId) {
        safeStorageSet(STORAGE_KEY_MUST_SET_STAFF, 'true');
      } else {
        safeStorageRemove(STORAGE_KEY_MUST_SET_STAFF);
      }
      // CRITICAL: sync token BEFORE setState (race fix — same discipline
      // as login). On the must_rotate → authenticated transition,
      // RoleProvider's auth-status effect fires whoami immediately;
      // without this sync, that whoami sees the stale must_rotate token
      // and gets 403'd.
      setCurrentToken(body.access_token);
      setState({
        status:    'authenticated',
        token:     body.access_token,
        expiresAt,
        error:     null,
        mustSetStaffId,
      });
    },
    [state.token],
  );

  // ── setStaffId action ─────────────────────────────────────────────────
  // POST /api/auth/set-staff-id. Takes a normal full-scope token (unlike
  // changePassword, missing staff_code doesn't restrict the token) and
  // returns a fresh token with must_set_staff_id cleared. Same manual
  // fetch + Authorization header pattern as changePassword.
  const setStaffId = useCallback(
    async (staffCode: string) => {
      setState((s) => ({ ...s, error: null }));

      const currentToken = state.token;
      if (!currentToken) {
        const msg = 'You must be signed in to set your staff ID.';
        setState((s) => ({ ...s, error: msg }));
        throw new Error(msg);
      }

      let res: Response;
      try {
        res = await fetch(SET_STAFF_ID_ENDPOINT, {
          method:  'POST',
          headers: {
            'Content-Type':  'application/json',
            'Authorization': `Bearer ${currentToken}`,
          },
          body: JSON.stringify({ staff_code: staffCode }),
        });
      } catch {
        const msg = 'Cannot reach the server. Please try again.';
        setState((s) => ({ ...s, error: msg }));
        throw new Error(msg);
      }

      if (res.status === 400) {
        let detail = 'Staff ID is invalid.';
        try {
          const body = await res.json();
          if (body && typeof body.detail === 'string') detail = body.detail;
        } catch { /* keep default */ }
        setState((s) => ({ ...s, error: detail }));
        throw new Error(detail);
      }
      if (!res.ok) {
        const msg = `Failed to set staff ID (HTTP ${res.status}).`;
        setState((s) => ({ ...s, error: msg }));
        throw new Error(msg);
      }

      let body: TokenResponse;
      try {
        body = await res.json() as TokenResponse;
      } catch {
        const msg = 'Server returned an invalid response.';
        setState((s) => ({ ...s, error: msg }));
        throw new Error(msg);
      }

      const expiresAt = Date.now() + body.expires_in_seconds * 1000;
      safeStorageSet(STORAGE_KEY_TOKEN,   body.access_token);
      safeStorageSet(STORAGE_KEY_EXPIRES, String(expiresAt));
      safeStorageRemove(STORAGE_KEY_MUST_SET_STAFF);
      setCurrentToken(body.access_token);
      setState((s) => ({
        ...s,
        status:    'authenticated',
        token:     body.access_token,
        expiresAt,
        error:     null,
        mustSetStaffId: false,
      }));
    },
    [state.token],
  );

  // ── logout action ─────────────────────────────────────────────────────
  const logout = useCallback(() => {
    clearAllAuthStorage();
    setCurrentToken(null);
    setState({
      status:    'unauthenticated',
      token:     null,
      expiresAt: null,
      error:     null,
      mustSetStaffId: false,
    });
  }, []);

  // ── Assemble context value ────────────────────────────────────────────

  const value: AuthContextValue = {
    status:    state.status,
    token:     state.token,
    expiresAt: state.expiresAt,
    error:     state.error,
    mustSetStaffId: state.mustSetStaffId,
    login,
    changePassword,
    setStaffId,
    logout,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}
