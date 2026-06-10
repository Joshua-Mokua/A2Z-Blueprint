// v10.510 Phase 4 Batch β1 — PipelineProvider.
//
// Provider for the cascade-scoped list of pipeline deals visible to
// the caller. Matches the RoleProvider / BrandingProvider context-
// Provider pattern. (TanStack Query adoption deferred — OI-63.)
//
// Hydration policy:
//   - Mount-time fetch when auth.status === 'authenticated'
//   - Deliberately holds back the fetch until auth is settled to
//     avoid the same race AuthProvider documented: an unauthenticated
//     fetch would 401, trip the on401 callback, and flip the user
//     to 'expired' on app boot
//   - Manual refetch via the `refetch` callback in context (called
//     by Pipeline page when user pulls to refresh, or by future
//     mutation hooks after a successful POST/PUT)
//   - No automatic polling, no stale-while-revalidate — this matches
//     the existing Provider doctrine (v10.495 useBranding pattern)
//
// Why this is a Provider rather than a hook-with-useEffect:
//   - Multiple components on the Pipeline page (header KPIs, the
//     deal table, eventually queue panels) all read the same list.
//     Hoisting state to a Provider avoids duplicate fetches.
//   - Future batches (β2 mutations) will dispatch refetch from
//     deep in the tree — Provider context surfaces that handle
//     without prop-drilling.
//
// Scope boundary (intentional):
//   - This Provider holds ONLY the list. Single-deal detail
//     (/api/pipeline/deals/{id}) is fetched ad-hoc by the detail
//     page itself in a future batch.
//   - Manager queues (/api/pipeline/queues/...) get their own
//     Provider when β5 ships, not folded in here.

import {
  createContext, useCallback, useEffect, useState, type ReactNode,
} from 'react';
import { fetchPipelineDeals, AuthExpiredError } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import type { PipelineDeal, PipelineDealsQuery } from '@/types/pipeline';


// ── Context shape ───────────────────────────────────────────────────────

export interface PipelineContextValue {
  /** Deals visible to the caller (cascade-scoped server-side). */
  deals:     PipelineDeal[];
  /** Total count from server (may exceed deals.length under pagination). */
  count:     number;
  /** True until the first fetch resolves or fails. */
  loading:   boolean;
  /** Surface fetch failure to UI; null when no error. */
  error:     string | null;
  /** Trigger a fresh fetch with the same (or new) query params. */
  refetch:   (query?: PipelineDealsQuery) => Promise<void>;
}

export const PipelineContext = createContext<PipelineContextValue>({
  deals:   [],
  count:   0,
  loading: true,
  error:   null,
  refetch: async () => { /* no-op default */ },
});


// ── Internal state ──────────────────────────────────────────────────────

interface PipelineState {
  deals:   PipelineDeal[];
  count:   number;
  loading: boolean;
  error:   string | null;
}

const INITIAL_STATE: PipelineState = {
  deals:   [],
  count:   0,
  loading: true,
  error:   null,
};


// ── Provider component ──────────────────────────────────────────────────

export function PipelineProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<PipelineState>(INITIAL_STATE);
  const [lastQuery, setLastQuery] = useState<PipelineDealsQuery>({});
  const auth = useAuth();

  // ── The fetch routine, memoized so callers don't trigger re-renders ──

  const doFetch = useCallback(async (query: PipelineDealsQuery) => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const response = await fetchPipelineDeals(query);
      setState({
        deals:   response.deals,
        count:   response.count,
        loading: false,
        error:   null,
      });
    } catch (e) {
      // Auth-expired errors are handled by AuthProvider's 401 callback
      // (it flips status to 'expired' before this throw reaches us).
      // We still surface the error so the UI doesn't show stale data.
      const msg = e instanceof AuthExpiredError
        ? 'Your session has expired.'
        : e instanceof Error
          ? e.message
          : 'Failed to load deals.';
      setState({
        deals:   [],
        count:   0,
        loading: false,
        error:   msg,
      });
    }
  }, []);

  // ── refetch callback exposed via context ─────────────────────────────
  // Accepts optional query overrides; remembers them for subsequent
  // refetches so users don't lose filter state across mutations.

  const refetch = useCallback(async (query?: PipelineDealsQuery) => {
    const next = query ?? lastQuery;
    setLastQuery(next);
    await doFetch(next);
  }, [doFetch, lastQuery]);

  // ── Mount + auth-status effect: fetch when authenticated ─────────────
  // Guard against the race where the Provider mounts before AuthProvider
  // finishes localStorage rehydration. Only fetch when status is the
  // settled 'authenticated' state — initializing/must_rotate/unauth/expired
  // states all leave the deals list empty.

  useEffect(() => {
    if (auth.status === 'authenticated') {
      void doFetch(lastQuery);
    } else if (auth.status === 'unauthenticated'
            || auth.status === 'expired'
            || auth.status === 'must_rotate') {
      // Wipe deals so a logged-out user briefly seeing the previous
      // mount doesn't continue to display sensitive deal data.
      setState({ deals: [], count: 0, loading: false, error: null });
    }
    // intentionally not depending on lastQuery — query changes are
    // routed through refetch(), not through this auth-change effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.status, doFetch]);

  // ── Assemble context value ───────────────────────────────────────────

  const value: PipelineContextValue = {
    deals:   state.deals,
    count:   state.count,
    loading: state.loading,
    error:   state.error,
    refetch,
  };

  return (
    <PipelineContext.Provider value={value}>
      {children}
    </PipelineContext.Provider>
  );
}
