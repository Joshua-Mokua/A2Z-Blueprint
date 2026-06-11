// v10.522 Phase 4 Batch β6 — useCreditAdminCase detail hook.
//
// Mirrors useLmsApplication. Refetch after mutations keeps the
// permissions object in sync.

import { useState, useEffect, useCallback } from 'react';
import { fetchCreditAdminCaseDetail, AuthExpiredError } from '@/lib/api';
import type { CreditAdminCase, CreditAdminPermissions } from '@/types/creditAdmin';


interface UseCreditAdminCaseValue {
  caseRecord:  CreditAdminCase | null;
  permissions: CreditAdminPermissions | null;
  loading:     boolean;
  error:       string | null;
  refetch:     () => Promise<void>;
}


export function useCreditAdminCase(caseId: string | undefined): UseCreditAdminCaseValue {
  const [caseRecord,  setCaseRecord]  = useState<CreditAdminCase | null>(null);
  const [permissions, setPermissions] = useState<CreditAdminPermissions | null>(null);
  const [loading,     setLoading]     = useState<boolean>(true);
  const [error,       setError]       = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!caseId) {
      setCaseRecord(null);
      setPermissions(null);
      setLoading(false);
      setError('No case id provided.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await fetchCreditAdminCaseDetail(caseId);
      // Backend's response shape has the case at `case` (a reserved
      // word in JS but valid as a property). Reading it as bracket
      // access for clarity even though dot works at runtime.
      setCaseRecord(response.case);
      setPermissions(response.permissions);
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      const msg = e instanceof Error ? e.message : 'Failed to load case.';
      setError(msg);
      setCaseRecord(null);
      setPermissions(null);
    } finally {
      setLoading(false);
    }
  }, [caseId]);

  useEffect(() => {
    refetch().catch(() => { /* AuthExpiredError handled globally */ });
  }, [refetch]);

  return { caseRecord, permissions, loading, error, refetch };
}
