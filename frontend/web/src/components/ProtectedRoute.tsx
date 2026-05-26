// v10.500 Phase 1 Batch 3a — ProtectedRoute with real redirect.
// v10.500 Phase 1 Batch 3b — extended with path-aware must_rotate gate.
//
// Gates a route's content based on auth status and role classification.
// Renders one of: loading, redirect-to-login, redirect-to-rotation,
// unauthorized, or children.
//
// CGR1 note: Batch 2e's ProtectedRoute was structurally correct; the
// auth-status redirect (Batch 3a) and the must_rotate path gate (Batch
// 3b) are completions, not corrections. The role/admin/tier
// authorization branches are unchanged.
//
// Batch 3b must_rotate semantics:
//   When auth.status === 'must_rotate', the user has a scope-limited
//   token that only the change-password endpoint accepts. ProtectedRoute
//   keeps them on /change-password and bounces every other route there.
//   This pairs with the backend: utils/auth_jwt.get_current_user rejects
//   must_rotate tokens with 403, so even if a user bypasses this
//   frontend gate (devtools, direct URL), every API call other than
//   change-password will fail server-side. Frontend gate is UX; backend
//   gate is mechanism.
//
// Usage (unchanged from Batch 3a):
//   <Route path="/admin"
//          element={<ProtectedRoute requireAdmin><AdminPanel /></ProtectedRoute>} />
//   <Route path="/dashboard"
//          element={<ProtectedRoute requireAuth><Dashboard /></ProtectedRoute>} />
//   <Route path="/change-password"
//          element={<ProtectedRoute requireAuth><ChangePassword /></ProtectedRoute>} />

import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useRole } from '../hooks/useRole';
import { useAuth } from '../hooks/useAuth';
import type { Tier } from '../types/role';

interface ProtectedRouteProps {
  children: ReactNode;
  requireAuth?:     boolean;
  requireAdmin?:    boolean;
  requireTier?:     Tier;
  requireAnyRole?:  string[];
}

const CHANGE_PASSWORD_PATH = '/change-password';

export function ProtectedRoute({
  children,
  requireAuth,
  requireAdmin,
  requireTier,
  requireAnyRole,
}: ProtectedRouteProps) {
  const auth = useAuth();
  const role = useRole();
  const location = useLocation();

  const needsAuth =
    requireAuth || requireAdmin || requireTier
    || (requireAnyRole && requireAnyRole.length > 0);

  // ── Auth still initializing (reading localStorage) ────────────────────
  if (auth.status === 'initializing') {
    return null;
  }

  // ── must_rotate (Batch 3b) — confine user to /change-password ─────────
  // If the user has a must_rotate-scope token, they may ONLY render
  // /change-password. Every other protected (or unprotected) route
  // bounces them there. Hard navigation guard.
  //
  // /change-password is the only legitimate destination — when the user
  // is on it, render the children even though role.isAuthenticated is
  // false (RoleProvider deliberately does not hydrate identity until
  // status === 'authenticated', because the must_rotate token is 403'd
  // by whoami-detailed).
  if (auth.status === 'must_rotate') {
    if (location.pathname !== CHANGE_PASSWORD_PATH) {
      return <Navigate to={CHANGE_PASSWORD_PATH} replace />;
    }
    return <>{children}</>;
  }

  // ── Loading state for authenticated users (role hydration) ────────────
  if (needsAuth && role.loading) {
    return null;
  }

  // ── Unauthenticated → redirect to /login ──────────────────────────────
  // Preserves original location so Login.tsx can navigate back after
  // successful auth. Covers both 'unauthenticated' and 'expired'.
  if (needsAuth && auth.status !== 'authenticated') {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // ── Edge case: authenticated but hydration produced no user ───────────
  if (needsAuth && !role.isAuthenticated) {
    return (
      <Unauthorized reason="Unable to load your identity. Please try refreshing or signing in again." />
    );
  }

  // ── Authorization checks (AND semantics) ──────────────────────────────

  if (requireAdmin && !role.isAdmin) {
    return <Unauthorized reason="This page requires administrator access." />;
  }

  if (requireTier && !role.userHasTier(requireTier)) {
    return <Unauthorized reason={`This page requires tier: ${requireTier}.`} />;
  }

  if (requireAnyRole && requireAnyRole.length > 0
      && !role.userHasAnyRole(requireAnyRole)) {
    return <Unauthorized reason="Your role doesn't have access to this page." />;
  }

  return <>{children}</>;
}


function Unauthorized({ reason }: { reason: string }) {
  return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <h2>Access denied</h2>
      <p>{reason}</p>
      <p>If you believe this is an error, contact your system administrator.</p>
    </div>
  );
}
