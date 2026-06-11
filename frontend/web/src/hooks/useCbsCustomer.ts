// v10.531 Phase 5 Batch γ2 — useCbsCustomer hook.
//
// Single-customer detail fetcher. Loads BOTH the customer record and
// their accounts in parallel — combined into one hook because the CBS
// detail page always shows both.

import { useState, useEffect, useCallback } from 'react';
import { fetchCbsCustomer, fetchCbsCustomerAccounts, AuthExpiredError } from '@/lib/api';
import type { CbsCustomer, CbsAccount } from '@/types/cbs';


interface UseCbsCustomerValue {
  customer:    CbsCustomer | null;
  accounts:    CbsAccount[];
  loading:     boolean;
  error:       string | null;
  refetch:     () => Promise<void>;
}


export function useCbsCustomer(cif: string | undefined): UseCbsCustomerValue {
  const [customer, setCustomer] = useState<CbsCustomer | null>(null);
  const [accounts, setAccounts] = useState<CbsAccount[]>([]);
  const [loading,  setLoading]  = useState<boolean>(true);
  const [error,    setError]    = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!cif) {
      setCustomer(null);
      setAccounts([]);
      setLoading(false);
      setError('No CIF provided.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      // Parallel fetches: customer + accounts can race; both are
      // independent server-side. If customer 404s, the accounts call
      // would also 404 — Promise.all rejects either way.
      const [custResp, acctResp] = await Promise.all([
        fetchCbsCustomer(cif),
        fetchCbsCustomerAccounts(cif),
      ]);
      setCustomer(custResp.customer);
      setAccounts(acctResp.accounts);
    } catch (e) {
      if (e instanceof AuthExpiredError) throw e;
      const msg = e instanceof Error ? e.message : 'Failed to load customer.';
      setError(msg);
      setCustomer(null);
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, [cif]);

  useEffect(() => {
    refetch().catch(() => { /* AuthExpiredError handled globally */ });
  }, [refetch]);

  return { customer, accounts, loading, error, refetch };
}
