// v10.499 Stage C Batch 2e — ProtectedRoute wrapper.
//
// Gates a route's content based on the caller's role and capabilities.
// Consumes useRole() for the access decision; renders different states
// depending on whether the user is loading, unauthenticated, unauthorized,
// or authorized.
//
// Usage:
//   <Route path="/admin"
//          element={<ProtectedRoute requireAdmin><AdminPanel /></ProtectedRoute>} />
//   <Route path="/dashboard"
//          element={<ProtectedRoute requireAuth><Dashboard /></ProtectedRoute>} />
//   <Route path="/leadership"
//          element={<ProtectedRoute requireTier="structural_owner"><LeadershipView /></ProtectedRoute>} />
//   <Route path="/exec"
//          element={<ProtectedRoute requireAnyRole={["Managing Director", "Director Retail Banking"]}><ExecView /></ProtectedRoute>} />
//
// Each access-requirement prop is optional. When multiple are provided,
// they are combined with AND semantics — the user must satisfy all
// stated requirements. requireAuth is implicit when any other requirement
// is set (you can't be admin if you're not authenticated).
//
// State rendering:
//   loading        → null (don't flash content during the typically
//                    sub-second initial fetch)
//   unauthenticated → "Please log in" message (v1; real redirect to
//                    /login lands when AuthProvider becomes real)
//   unauthorized   → "You don't have permission" message (logged in
//                    but doesn't satisfy role requirements)
//   authorized     → renders children

import type { ReactNode } from 'react';
import { useRole } from '../hooks/useRole';
import type { Tier } from '../types/role';

interface ProtectedRouteProps {
  children: ReactNode;
  requireAuth?:     boolean;          // any authenticated user
  requireAdmin?:    boolean;          // user.is_admin === true
  requireTier?:     Tier;             // user.tier === <tier>
  requireAnyRole?:  string[];         // user.role matches one of these (case-insensitive)
}

export function ProtectedRoute({
  children,
  requireAuth,
  requireAdmin,
  requireTier,
  requireAnyRole,
}: ProtectedRouteProps) {
  const {
    loading,
    isAuthenticated,
    isAdmin,
    userHasTier,
    userHasAnyRole,
  } = useRole();

  // ── Loading ───────────────────────────────────────────────────────────
  // While useRole() is still fetching, render nothing. Avoid flashing
  // "Please log in" briefly during the initial sub-second fetch.

  if (loading) {
    return null;
  }

  // ── Unauthenticated ───────────────────────────────────────────────────
  // No user loaded (either fetch failed with 401 or no JWT cookie yet).
  // Any of the requirement props implies requireAuth, so we check this
  // gate first regardless of which specific requirement was passed.

  const needsAuth =
    requireAuth || requireAdmin || requireTier || (requireAnyRole && requireAnyRole.length > 0);

  if (needsAuth && !isAuthenticated) {
    return (
      <div style={{ padding: '2rem', textAlign: 'center' }}>
        <h2>Please log in</h2>
        <p>You must be signed in to view this page.</p>
      </div>
    );
  }

  // ── Authorization checks (AND semantics) ──────────────────────────────
  // User is authenticated; verify each stated requirement.

  if (requireAdmin && !isAdmin) {
    return <Unauthorized reason="This page requires administrator access." />;
  }

  if (requireTier && !userHasTier(requireTier)) {
    return <Unauthorized reason={`This page requires tier: ${requireTier}.`} />;
  }

  if (requireAnyRole && requireAnyRole.length > 0 && !userHasAnyRole(requireAnyRole)) {
    return <Unauthorized reason="Your role doesn't have access to this page." />;
  }

  // ── Authorized ────────────────────────────────────────────────────────
  // All requirements satisfied (or none were specified). Render children.

  return <>{children}</>;
}

// ── Internal helper ─────────────────────────────────────────────────────

function Unauthorized({ reason }: { reason: string }) {
  return (
    <div style={{ padding: '2rem', textAlign: 'center' }}>
      <h2>Access denied</h2>
      <p>{reason}</p>
      <p>If you believe this is an error, contact your system administrator.</p>
    </div>
  );
}