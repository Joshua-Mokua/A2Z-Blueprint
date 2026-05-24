// v10.499 Stage C Batch 2d — useRole hook.
//
// Returns the caller's identity, the canonical role registry, and a set
// of derived capability flags + helper predicates from RoleContext. Used
// by any React component that needs to make role-aware UI decisions
// without re-fetching the underlying API endpoints.
//
// Usage:
//   const { user, loading, isAdmin, userHasTier } = useRole();
//   if (loading) return <Spinner />;
//   if (isAdmin) return <AdminPanel />;
//   if (userHasTier('structural_owner')) return <StructuralView />;
//
// The hook is a pure context consumer (mirrors useBranding pattern). All
// state, fetching, and derivation lives in RoleProvider.

import { useContext } from 'react';
import { RoleContext } from '@/providers/RoleProvider';

export function useRole() {
  return useContext(RoleContext);
}