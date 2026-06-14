// v10.551 Phase P Batch P5 — useCreditOpenWork hook.
// Same fetch-wrap pattern as useMdDashboard.

import { useState, useEffect, useCallback } from 'react';
import { fetchCreditOpenWork, AuthExpiredError } from '@/lib/api';
import type { CreditOpenWork } from '@/types/cockpit';

interface UseCreditOpenWorkValue {
  data:    CreditOpenWork | null;
  loading: boolean;
  error:   string | null;
  refetch: () => Promise<void>;
}

export function useCreditOpenWork(): UseCreditOpenWorkValue {
  const [data,    setData]    = useState<CreditOpenWork | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error,   setError]   = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchCreditOpenWork());
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      setError(e instanceof Error ? e.message : 'Failed to load credit data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load().catch(() => { /* AuthExpiredError handled globally */ });
  }, [load]);

  return { data, loading, error, refetch: load };
}
