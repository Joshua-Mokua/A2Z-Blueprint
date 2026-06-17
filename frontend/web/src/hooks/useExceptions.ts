// useExceptions — wraps fetchDashboardExceptions in the project's hook
// pattern (returns {data, loading, error, refetch}; re-throws AuthExpiredError
// for the global 401 handler). Mirrors useMdDashboard.

import { useState, useEffect, useCallback } from 'react';
import { fetchDashboardExceptions, AuthExpiredError } from '@/lib/api';
import type { ExceptionsResponse } from '@/types/exceptions';

interface UseExceptionsValue {
  data:    ExceptionsResponse | null;
  loading: boolean;
  error:   string | null;
  refetch: () => Promise<void>;
}

export function useExceptions(): UseExceptionsValue {
  const [data,    setData]    = useState<ExceptionsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchDashboardExceptions());
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      setError(e instanceof Error ? e.message : 'Failed to load exceptions.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch(() => { /* AuthExpiredError handled globally */ });
  }, [load]);

  return { data, loading, error, refetch: load };
}
