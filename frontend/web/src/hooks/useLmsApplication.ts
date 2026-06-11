// v10.520 Phase 4 Batch β5 — useLmsApplication detail hook.
//
// Single-application fetcher. Same plain-hook pattern as useLmsApplications.
// Returns both the application and the permissions object the backend
// resolved for this caller.
//
// Refetch is called by detail page after each successful mutation, so
// the permissions object reflects the new state (e.g. after assign,
// can_assign flips false because status is now 'assigned').

import { useState, useEffect, useCallback } from 'react';
import { fetchLmsApplicationDetail, AuthExpiredError } from '@/lib/api';
import type { LoanApplication, LoanApplicationPermissions } from '@/types/lms';


interface UseLmsApplicationValue {
  application:   LoanApplication | null;
  permissions:   LoanApplicationPermissions | null;
  loading:       boolean;
  error:         string | null;
  refetch:       () => Promise<void>;
}


export function useLmsApplication(appId: string | undefined): UseLmsApplicationValue {
  const [application, setApplication] = useState<LoanApplication | null>(null);
  const [permissions, setPermissions] = useState<LoanApplicationPermissions | null>(null);
  const [loading, setLoading]         = useState<boolean>(true);
  const [error, setError]             = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!appId) {
      setApplication(null);
      setPermissions(null);
      setLoading(false);
      setError('No application id provided.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetchLmsApplicationDetail(appId);
      setApplication(response.application);
      setPermissions(response.permissions);
    } catch (e) {
      if (e instanceof AuthExpiredError) {
        throw e;
      }
      const msg = e instanceof Error ? e.message : 'Failed to load application.';
      setError(msg);
      setApplication(null);
      setPermissions(null);
    } finally {
      setLoading(false);
    }
  }, [appId]);

  useEffect(() => {
    refetch().catch(() => { /* AuthExpiredError handled globally */ });
  }, [refetch]);

  return { application, permissions, loading, error, refetch };
}
