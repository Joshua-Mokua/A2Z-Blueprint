// v10.500 Phase 1 Batch 3a — RoleProvider with auth-state gating.
//
// Originally shipped at v10.499 Stage C Batch 2d as a fetcher that fired
// /api/auth/whoami-detailed + /api/roles/registry on mount, on the
// assumption that an auth substrate would attach credentials by then.
// Batch 3a closes that loop: this provider now waits for
// auth.status === 'authenticated' before firing either fetch, and
// resets state when auth transitions away from 'authenticated'.
//
// CGR1 note: Batch 2d's RoleProvider was structurally correct — its
// shape, error handling, and derived-value pattern are unchanged here.
// The only meaningful difference is the useEffect gating + dependency.
// Batch 2d remains a VALID shipment, not a rollback.
//
// Separation of concerns (per Batch 3a doctrine):
//   - AuthProvider owns: token, expiry, login/logout, auth status
//   - RoleProvider owns: user identity, role classification, RBAC helpers
//   - The two providers do NOT share state; they communicate only via
//     auth.status, with RoleProvider reading and reacting.
//
// Provider chain placement (App.tsx):
//   QueryClient → Branding → Toast → Auth → Role → WebSocket → Router

import {
  createContext, useEffect, useState, type ReactNode,
} from 'react';
import { fetchWhoamiDetailed, fetchRoleRegistry } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import type { UserIdentity, RoleRegistry, Tier } from '@/types/role';


// ── Context value shape ─────────────────────────────────────────────────

interface RoleContextValue {
  // Raw data
  user:      UserIdentity | null;
  registry:  RoleRegistry | null;
  loading:   boolean;
  error:     string | null;

  // Derived flags
  isAdmin:        boolean;
  canViewAll:     boolean;
  canBeTagged:    boolean;
  isAuthenticated: boolean;

  // Derived helpers
  userHasTier:    (tier: Tier) => boolean;
  userHasAnyRole: (roles: string[]) => boolean;
}


// ── Context with a safe default ─────────────────────────────────────────

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
  const auth = useAuth();

  const [user, setUser]         = useState<UserIdentity | null>(null);
  const [registry, setRegistry] = useState<RoleRegistry | null>(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);

  // ── Auth-gated fetch ──────────────────────────────────────────────────
  // Fires whoami + registry only when authenticated. Resets state when
  // auth transitions to any non-authenticated status (logout, expiry).
  //
  // Why dep is auth.status only (not auth.token): the role hydration
  // doesn't depend on the token value, only on whether we are
  // authenticated. A token refresh (if ever added in Phase 2) shouldn't
  // re-trigger a whoami round trip.
  useEffect(() => {
    if (auth.status !== 'authenticated') {
      // Reset on transition out of authenticated state
      setUser(null);
      setRegistry(null);
      setError(null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    // Parallel fetch — endpoints are independent. Total wait time =
    // max(latency_whoami, latency_registry), not sum.
    Promise.all([fetchWhoamiDetailed(), fetchRoleRegistry()])
      .then(([userData, registryData]) => {
        if (cancelled) return;
        setUser(userData);
        setRegistry(registryData);
      })
      .catch((e) => {
        if (cancelled) return;
        // A 401 here is handled by api.ts (it fires the AuthProvider's
        // on401 callback before throwing AuthExpiredError). Re-render
        // will see auth.status !== 'authenticated' and the reset branch
        // will fire. Other errors (5xx, network) we surface as `error`.
        setError(String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [auth.status]);

  // ── Derived values (computed each render from `user`) ─────────────────

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
