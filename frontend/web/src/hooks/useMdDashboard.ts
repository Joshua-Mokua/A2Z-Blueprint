// v10.545 Phase P Batch P4 — useMdDashboard hook.
//
// Wraps fetchMdDashboard in the project's established hook pattern
// (useState/useEffect, returns {data, loading, error, refetch}, re-throws
// AuthExpiredError so the global 401 handler can flip auth state).
// Mirrors usePortfolioSummary.

import { useState, useEffect, useCallback } from 'react';
import { fetchMdDashboard, AuthExpiredError } from '@/lib/api';
import type { MdDashboardResponse } from '@/types/dashboard';

interface UseMdDashboardValue {
  data:    MdDashboardResponse | null;
  loading: boolean;
  error:   string | null;
  refetch: () => Promise<void>;
}

export function useMdDashboard(): UseMdDashboardValue {
  const [data,    setData]    = useState<MdDashboardResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetchMdDashboard();
      setData(resp);
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      const msg = e instanceof Error ? e.message : 'Failed to load dashboard.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch(() => { /* AuthExpiredError handled globally */ });
  }, [load]);

  return { data, loading, error, refetch: load };
}
