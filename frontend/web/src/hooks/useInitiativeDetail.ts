// v10.541 Phase 8 Batch γ4b — useInitiativeDetail hook.

import { useState, useEffect, useCallback } from 'react';
import { fetchInitiativeDetail, AuthExpiredError, ApiValidationError } from '@/lib/api';
import type { Initiative } from '@/types/initiatives';


interface UseInitiativeDetailValue {
  initiative:  Initiative | null;
  loading:     boolean;
  error:       string | null;
  notFound:    boolean;
  refetch:     () => Promise<void>;
}


export function useInitiativeDetail(initiativeId: string | undefined): UseInitiativeDetailValue {
  const [initiative, setInitiative] = useState<Initiative | null>(null);
  const [loading,    setLoading]    = useState<boolean>(true);
  const [error,      setError]      = useState<string | null>(null);
  const [notFound,   setNotFound]   = useState<boolean>(false);

  const load = useCallback(async () => {
    if (!initiativeId) {
      setLoading(false);
      setError('No initiative id provided.');
      return;
    }
    setLoading(true);
    setError(null);
    setNotFound(false);
    try {
      const resp = await fetchInitiativeDetail(initiativeId);
      setInitiative(resp.initiative || null);
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      if (e instanceof ApiValidationError && e.status === 404) {
        setNotFound(true);
      } else {
        const msg = e instanceof Error ? e.message : 'Failed to load initiative.';
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [initiativeId]);

  useEffect(() => {
    load().catch(() => { /* AuthExpiredError handled globally */ });
  }, [load]);

  return { initiative, loading, error, notFound, refetch: load };
}
