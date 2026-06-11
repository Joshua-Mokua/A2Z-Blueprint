// v10.522 Phase 4 Batch β6 — useCreditAdminCases list hook.
//
// Plain useState/useEffect pattern mirroring useLmsApplications (β5).

import { useState, useEffect, useCallback } from 'react';
import { fetchCreditAdminCases, AuthExpiredError } from '@/lib/api';
import type { CreditAdminCase } from '@/types/creditAdmin';


interface UseCreditAdminCasesValue {
  cases:    CreditAdminCase[];
  count:    number;
  loading:  boolean;
  error:    string | null;
  refetch:  () => Promise<void>;
}


export function useCreditAdminCases(): UseCreditAdminCasesValue {
  const [cases,   setCases]   = useState<CreditAdminCase[]>([]);
  const [count,   setCount]   = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error,   setError]   = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchCreditAdminCases();
      setCases(response.cases);
      setCount(response.count);
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      const msg = e instanceof Error ? e.message : 'Failed to load cases.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch().catch(() => { /* AuthExpiredError handled globally */ });
  }, [refetch]);

  return { cases, count, loading, error, refetch };
}
