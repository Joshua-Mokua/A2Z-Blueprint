// v10.500 Phase 1 Batch 3a — useAuth hook.
//
// Returns the AuthContext value: status, token, expiresAt, error, plus
// login/logout actions. Mirrors useRole and useBranding patterns — a
// pure context consumer with no logic of its own.
//
// Usage:
//   const { status, login, logout, error } = useAuth();
//
//   if (status === 'authenticated') return <Dashboard />;
//   if (status === 'unauthenticated') return <Navigate to="/login" />;
//
// Scope: token lifecycle ONLY. For user identity, role classification,
// or RBAC helpers, use useRole(). The two providers are deliberately
// separated for capability layering (OI-59 through OI-65).

import { useContext } from 'react';
import { AuthContext } from '@/providers/AuthProvider';

export function useAuth() {
  return useContext(AuthContext);
}
