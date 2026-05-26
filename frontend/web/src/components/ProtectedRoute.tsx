// v10.500 Phase 1 Batch 3a — ProtectedRoute with real redirect.
//
// Originally shipped at v10.499 Stage C Batch 2e as a wrapper that
// rendered a "Please log in" message under unauthenticated conditions —
// a dead-end with no path forward because /login did not exist yet.
// Batch 3a closes the loop: now redirects to /login via <Navigate />,
// preserving the originally requested location so post-login can
// return the user to where they were going.
//
// CGR1 note: Batch 2e's ProtectedRoute was structurally correct — the
// role/admin/tier authorization branches below are unchanged. Only the
// unauthenticated branch swapped from a div to a Navigate. Batch 2e
// remains a VALID shipment, not a rollback.
//
// Gating logic now considers both:
//   - auth.status from AuthProvider (token-level state)
//   - isAuthenticated from RoleProvider (hydration-level state)
//
// During the authenticated-but-still-hydrating window, we render null
// (avoid flashing "Please log in" while whoami is in flight). Once
// hydration completes the user sees protected content; if the token is
// rejected during hydration, AuthProvider flips to 'expired' via the
// api.ts 401 callback, and the next render sees auth.status !==
// 'authenticated' and Navigates to /login.
//
// Usage (unchanged from Batch 2e):
//   <Route path="/admin"
//          element={<ProtectedRoute requireAdmin><AdminPanel /></ProtectedRoute>} />
//   <Route path="/dashboard"
//          element={<ProtectedRoute requireAuth><Dashboard /></ProtectedRoute>} />
//   <Route path="/leadership"
//          element={<ProtectedRoute requireTier="structural_owner"><LeadershipView /></ProtectedRoute>} />

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
  // Or hydration still in flight after we know we're authenticated.
  // Render null to avoid flashing intermediate states.
  if (auth.status === 'initializing' || (needsAuth && role.loading)) {
    return null;
  }

  // ── Unauthenticated → redirect to /login ──────────────────────────────
  // Preserve the originally requested location so Login can navigate
  // the user back after a successful auth.
  if (needsAuth && auth.status !== 'authenticated') {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // ── Edge case: authenticated but hydration produced no user ───────────
  // RoleProvider failed to fetch whoami (e.g. transient backend error
  // that wasn't a 401). Surface this as an unauthorized state rather
  // than render protected content with null user — fail safe.
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
