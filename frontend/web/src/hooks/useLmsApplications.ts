// v10.520 Phase 4 Batch β5 — useLmsApplications list hook.
//
// Plain useState/useEffect pattern. Simpler than PipelineProvider because
// LMS list has no shared filter state — it's a page-local list.
// When OI-63 (TanStack Query adoption) lands, this becomes useQuery.

import { useState, useEffect, useCallback } from 'react';
import { fetchLmsApplications, AuthExpiredError } from '@/lib/api';
import type { LoanApplication } from '@/types/lms';


interface UseLmsApplicationsValue {
  applications:  LoanApplication[];
  count:         number;
  loading:       boolean;
  error:         string | null;
  refetch:       () => Promise<void>;
}


export function useLmsApplications(): UseLmsApplicationsValue {
  const [applications, setApplications] = useState<LoanApplication[]>([]);
  const [count, setCount]   = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError]     = useState<string | null>(null);

  const refetch = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchLmsApplications();
      setApplications(response.applications);
      setCount(response.count);
    } catch (e) {
      // AuthExpiredError is handled by global on401 — let it propagate
      // (the user gets redirected to /login). For other errors, surface
      // to the page.
      if (e instanceof AuthExpiredError) {
        throw e;
      }
      const msg = e instanceof Error ? e.message : 'Failed to load applications.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch().catch(() => { /* AuthExpiredError handled globally */ });
  }, [refetch]);

  return { applications, count, loading, error, refetch };
}
