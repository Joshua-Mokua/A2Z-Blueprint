// v10.499 Stage C Batch 2d — RoleProvider for the React SPA.
//
// Fetches the caller's identity from /api/auth/whoami-detailed and the
// canonical role registry from /api/roles/registry in parallel, exposes
// both via RoleContext so any descendant component can read them via
// the useRole() hook.
//
// Pattern: mirrors BrandingProvider exactly. Single useEffect fires
// once on mount, Promise.all runs both fetches in parallel, .finally
// flips loading false regardless of success/failure.
//
// Provider chain placement (App.tsx):
//   QueryClient → Branding → Auth → Role → WebSocket → Router
// Role sits AFTER Auth because the endpoints it fetches require an
// authenticated JWT cookie. Until real auth lands (v10.497 milestone
// for AuthProvider), unauthenticated boots will see the endpoints
// return 401 — the .catch handler surfaces this as a non-fatal error
// state, keeping the UI alive.
//
// Derived values (isAdmin, helper predicates) are computed in the
// context value object rather than stored as separate state. Single
// source of truth: the `user` state holds the canonical data, derived
// fields are calculated on each render. This avoids the synchronisation
// bug class where stored derivations drift out of sync with their
// source.

import {
  createContext, useEffect, useState, type ReactNode,
} from 'react';
import { fetchWhoamiDetailed, fetchRoleRegistry } from '@/lib/api';
import type { UserIdentity, RoleRegistry, Tier } from '@/types/role';


// ── Context value shape ─────────────────────────────────────────────────
// What useRole() returns. Includes raw state plus derived helpers.

interface RoleContextValue {
  // Raw data (from React state)
  user:      UserIdentity | null;
  registry:  RoleRegistry | null;
  loading:   boolean;
  error:     string | null;

  // Derived flags (computed from user, not stored)
  isAdmin:        boolean;
  canViewAll:     boolean;
  canBeTagged:    boolean;
  isAuthenticated: boolean;   // true iff user is loaded (no 401 / no error)

  // Derived helpers (functions that close over user)
  userHasTier:    (tier: Tier) => boolean;
  userHasAnyRole: (roles: string[]) => boolean;
}


// ── Context with a sensible default ─────────────────────────────────────
// The default value is what useContext returns when there's no Provider
// above the consumer in the tree. We use a "not loaded, not authenticated"
// shape so consumers fail safe rather than crash.

export const RoleContext = createContext<RoleContextValue>({
  user:     null,
  registry: null,
  loading:  true,
  error:    null,

  isAdmin:         false,
  canViewAll:      false,
  canBeTagged:     false,
  isAuthenticated: false,

  userHasTier:    () => false,
  userHasAnyRole: () => false,
});


// ── Provider component ──────────────────────────────────────────────────

export function RoleProvider({ children }: { children: ReactNode }) {
  const [user, setUser]         = useState<UserIdentity | null>(null);
  const [registry, setRegistry] = useState<RoleRegistry | null>(null);
  const [loading, setLoading]   = useState(true);
  const [error, setError]       = useState<string | null>(null);

  useEffect(() => {
    // Parallel fetch — both endpoints are independent, so Promise.all
    // kicks them off simultaneously and resolves when both arrive.
    // Total wait time = max(latency_whoami, latency_registry), not sum.
    Promise.all([fetchWhoamiDetailed(), fetchRoleRegistry()])
      .then(([userData, registryData]) => {
        setUser(userData);
        setRegistry(registryData);
      })
      .catch((e) => {
        // 401 (no JWT cookie) is expected before login. Network errors
        // are also captured here. Either way, we surface the error to
        // consumers so they can render an unauthenticated state, but
        // we don't crash the app — the BrandingProvider continues to
        // work, branded login pages can render.
        setError(String(e));
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);  // Empty deps — fetch once on mount, never again.

  // ── Derived values (computed each render from `user`) ─────────────────
  // Cheap to compute, always in sync with `user`. Storing these as
  // separate state would create a synchronisation problem.

  const isAdmin         = user?.is_admin     ?? false;
  const canViewAll      = user?.can_view_all ?? false;
  const canBeTagged     = user?.can_be_tagged ?? false;
  const isAuthenticated = user !== null && error === null;

  const userHasTier = (tier: Tier): boolean => {
    return user?.tier === tier;
  };

  const userHasAnyRole = (roles: string[]): boolean => {
    if (!user) return false;
    const userRole = user.role.toLowerCase();
    return roles.some((r) => r.toLowerCase() === userRole);
  };

  // ── Assemble context value and provide it to children ─────────────────

  const value: RoleContextValue = {
    user,
    registry,
    loading,
    error,
    isAdmin,
    canViewAll,
    canBeTagged,
    isAuthenticated,
    userHasTier,
    userHasAnyRole,
  };

  return (
    <RoleContext.Provider value={value}>
      {children}
    </RoleContext.Provider>
  );
}