// #3b — useAnalytics hook. Mirrors useMdDashboard: useState/useEffect,
// returns {data, loading, error, refetch}, re-throws AuthExpiredError.

import { useState, useEffect, useCallback } from 'react';
import { fetchPipelineAnalytics, AuthExpiredError } from '@/lib/api';
import type { PipelineAnalyticsResponse } from '@/types/pipeline';

interface UseAnalyticsValue {
  data:    PipelineAnalyticsResponse | null;
  loading: boolean;
  error:   string | null;
  refetch: () => Promise<void>;
}

export function useAnalytics(): UseAnalyticsValue {
  const [data,    setData]    = useState<PipelineAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchPipelineAnalytics());
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      setError(e instanceof Error ? e.message : 'Failed to load analytics.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch(() => { /* AuthExpiredError handled globally */ });
  }, [load]);

  return { data, loading, error, refetch: load };
}
