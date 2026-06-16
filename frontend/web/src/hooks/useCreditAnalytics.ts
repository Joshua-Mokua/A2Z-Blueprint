// useCreditAnalytics — mirrors useAnalytics: {data, loading, error, refetch}.

import { useState, useEffect, useCallback } from 'react';
import { fetchCreditAnalytics, AuthExpiredError } from '@/lib/api';
import type { CreditAnalyticsResponse } from '@/types/creditAnalytics';

interface UseCreditAnalyticsValue {
  data:    CreditAnalyticsResponse | null;
  loading: boolean;
  error:   string | null;
  refetch: () => Promise<void>;
}

export function useCreditAnalytics(): UseCreditAnalyticsValue {
  const [data,    setData]    = useState<CreditAnalyticsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchCreditAnalytics());
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      setError(e instanceof Error ? e.message : 'Failed to load credit analytics.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch(() => { /* AuthExpiredError handled globally */ });
  }, [load]);

  return { data, loading, error, refetch: load };
}
